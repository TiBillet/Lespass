import logging
from datetime import timedelta

import stripe
from django.conf import settings
from django.db import connection
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from django_tenants.utils import tenant_context, schema_context
from rest_framework import serializers

from ApiBillet.serializers import get_or_create_price_sold, dec_to_int
from AuthBillet.models import TibilletUser
from AuthBillet.utils import get_or_create_user
from BaseBillet.models import Price, Product, OptionGenerale, Membership, Paiement_stripe, LigneArticle, Tag, Event, \
    Reservation, PriceSold, Ticket, ProductSold, Configuration, ProductFormField
from Customers.models import Client, Domain
from MetaBillet.models import WaitingConfiguration
from PaiementStripe.views import CreationPaiementStripe
from root_billet.models import RootConfiguration

logger = logging.getLogger(__name__)


class ContactValidator(serializers.Serializer):
    email = serializers.EmailField()
    subject = serializers.CharField()
    message = serializers.CharField()


class TagValidator(serializers.Serializer):
    tags = serializers.PrimaryKeyRelatedField(source="slug", queryset=Tag.objects.all(), many=True)


class LinkQrCodeValidator(serializers.Serializer):
    email = serializers.EmailField(required=True, allow_null=False)
    emailConfirmation = serializers.EmailField(required=True, allow_null=False)
    firstname = serializers.CharField(max_length=500, required=False, allow_blank=True)
    lastname = serializers.CharField(max_length=500, required=False, allow_blank=True)
    # data=request.POST.dict() in the controler for boolean
    cgu = serializers.BooleanField(required=True, allow_null=False)
    newsletter = serializers.BooleanField(required=False, allow_null=True)
    qrcode_uuid = serializers.UUIDField()

    def validate(self, attrs):
        email = attrs['email']
        emailConfirmation = attrs['emailConfirmation']
        if emailConfirmation != email:
            logger.error(_(f"Email confirmation failed: the email and its confirmation are different. A typo, maybe?"))
            raise serializers.ValidationError(_(f"Email confirmation failed: the email and its confirmation are different. A typo, maybe?"))
        return attrs

class LoginEmailValidator(serializers.Serializer):
    email = serializers.EmailField()


class TicketCreator():

    def __init__(self, reservation: Reservation, products_dict: dict):
        self.products_dict = products_dict
        self.reservation = reservation
        self.user = reservation.user_commande

        # La liste des objets a vendre pour la création du paiement stripe
        self.list_line_article_sold = []

        # Si checkout existe, on va demander le paiement en front.
        # Sinon, on envoie la confirmation par mail
        self.checkout_link = None
        self.tickets = []

        for product, prices_dict in products_dict.items():
            product: Product
            trigger_name = f"method_{product.categorie_article}"
            trigger = getattr(self, trigger_name)
            self.tickets = trigger(prices_dict)

        # Methode Action : On a pas de produit
        if reservation.event.categorie == Event.ACTION:
            self.tickets = self.method_A()

    # Methode ACTION
    def method_A(self):
        reservation: Reservation = self.reservation
        #     import ipdb; ipdb.set_trace()
        ticket = Ticket.objects.create(
            status=Ticket.NOT_ACTIV,
            reservation=reservation,
            first_name=self.user.first_name,
            last_name=self.user.last_name,
        )
        reservation.status = Reservation.FREERES_USERACTIV if reservation.user_commande.is_active else Reservation.FREERES
        reservation.save()
        return [ticket,]

    # FREERES : réservation gratuite
    def method_F(self, prices_dict):
        reservation: Reservation = self.reservation
        tickets = []

        for price, qty in prices_dict.items():
            price: Price
            qty: int

            # Recherche ou création du produit vendu
            # On est sur une reservation gratuite, on va pas chercher de paiement
            productsold, created = ProductSold.objects.get_or_create(
                event=reservation.event,
                product=price.product
            )
            pricesold, created = PriceSold.objects.get_or_create(
                productsold=productsold,
                prix=price.prix,
                price=price,
            )

            # Fabrication d'un ticket par qty
            # Dans la méthode reservation gratuite, le ticket est créé non pas en non payé mais en non actif
            # Il sera actif une fois le mail de l'user vérifié
            # La fonctione presave du fichier BaseBillet.signals
            # mettra à jour le statut de la réservation et enverra le billet dés validation de l'email
            for i in range(int(qty)):
                ticket = Ticket.objects.create(
                    status=Ticket.NOT_ACTIV,
                    reservation=reservation,
                    pricesold=pricesold,
                    # first_name=customer.get('first_name'),
                    # last_name=customer.get('last_name'),
                )
                tickets.append(ticket)

        reservation.status = Reservation.FREERES_USERACTIV if reservation.user_commande.is_active else Reservation.FREERES
        reservation.save()
        return tickets

    def method_B(self, prices_dict):
        reservation: Reservation = self.reservation
        tickets = []
        for price_generique, qty in prices_dict.items():
            price_generique: Price
            qty: int

            # Gerer les produits nominatifs ?
            # product: Product = price_generique.product
            # if product.nominative:
            #     for customer in price_object.get('customers'):

            event = reservation.event
            # Création de l'objet article à vendre, avec la liaison event.
            # On passe de prix générique (ex : Billet a 10€ a l'objet Billet pour evenement a 10€)
            pricesold: PriceSold = get_or_create_price_sold(price_generique, event=event)

            # les lignes articles pour la vente
            line_article = LigneArticle.objects.create(
                pricesold=pricesold,
                amount=dec_to_int(pricesold.prix),
                # pas d'objet reservation ?
                qty=qty,
            )
            self.list_line_article_sold.append(line_article)

            # Création des tickets en mode non payé
            for i in range(int(qty)):
                ticket = Ticket.objects.create(
                    status=Ticket.CREATED,  # not yet paid
                    reservation=reservation,
                    pricesold=pricesold,
                    # first_name=customer.get('first_name'),
                    # last_name=customer.get('last_name'),
                )
                tickets.append(ticket)

        self.checkout_link = self.get_checkout_stripe()
        return tickets

    def get_checkout_stripe(self):
        reservation: Reservation = self.reservation
        tenant = connection.tenant
        # Création du checkout stripe
        metadata = {
            'reservation': f'{reservation.uuid}',
            'tenant': f'{tenant.uuid}',
        }

        # Création de l'objet paiement stripe en base de donnée
        new_paiement_stripe = CreationPaiementStripe(
            user=reservation.user_commande,
            liste_ligne_article=self.list_line_article_sold,
            metadata=metadata,
            reservation=reservation,
            source=Paiement_stripe.FRONT_BILLETTERIE,
            success_url=f"stripe_return/",
            cancel_url=f"stripe_return/",
            absolute_domain=f"https://{tenant.get_primary_domain()}/event/",
        )

        if not new_paiement_stripe.is_valid():
            raise serializers.ValidationError(_(f'checkout strip not valid'))

        paiement_stripe: Paiement_stripe = new_paiement_stripe.paiement_stripe_db
        paiement_stripe.lignearticles.all().update(status=LigneArticle.UNPAID)

        reservation.tickets.all().update(status=Ticket.NOT_ACTIV)

        reservation.paiement = paiement_stripe
        reservation.status = Reservation.UNPAID
        reservation.save()

        print(f"get_checkout_stripe OK : {new_paiement_stripe.checkout_session.stripe_id}")
        return new_paiement_stripe.checkout_session.url


class ReservationValidator(serializers.Serializer):
    email = serializers.EmailField()
    # to_mail = serializers.BooleanField(default=True, required=False)
    event = serializers.PrimaryKeyRelatedField(
        queryset=Event.objects.filter(datetime__gte=timezone.now() - timedelta(days=1)))
    options = serializers.PrimaryKeyRelatedField(queryset=OptionGenerale.objects.all(), many=True, allow_null=True,
                                                 required=False)
    datetime = serializers.DateTimeField(required=False)

    def extract_products(self):
        """
        On vérifie ici :
            les objets produit et prix existent bien en DB et a une quantité valide
        """
        # Rercher des produits potentiels
        event = self.event
        products_dict = {}
        self.products = [] # Pour checker si un formulaire forbricks est présent
        self.free_price = False # Pour vérification plus bas que le prix libre est bien seul

        for product in event.products.all():
            for price in product.prices.all():
                # Un input possède l'uuid du prix ?
                if self.initial_data.get(str(price.uuid)):
                    qty = int(self.initial_data.get(str(price.uuid)))

                    if qty <= 0 : # Skip zero or negative quantities
                        continue

                    if price.free_price: # Pour vérification plus bas que le prix libre est bien seul
                        self.free_price = True
                    self.products.append(product)
                    if products_dict.get(product):
                        # On ajoute le prix a la liste des articles choisi
                        products_dict[product][price] = qty
                    else:
                        # Si le dict product n'existe pas :
                        products_dict[product] = {price: qty}
        
        return products_dict

    def validate_event(self, value):
        logger.info(f"validate event : {value}")
        self.event: Event = value
        if self.event.complet():
            raise serializers.ValidationError(_(f'Max capacity reached: event full.'))
        return value

    def validate_email(self, value):
        logger.info(f"validate email : {value}")
        if not hasattr(self, 'admin_created'): # Si ça n'est pas un ticket créé dans l'admin :
            # On vérifie que l'utilisateur connecté et l'email correspondent bien.
            request = self.context.get('request')
            if request.user.is_authenticated:
                if request.user.email != value:
                    raise serializers.ValidationError(_(f"Email does not match logged-in user."))

        self.user = get_or_create_user(value)
        return value

    def validate_options(self, value):
        # On check que les options sont bien dans l'event original.
        try :
            event: Event = self.event
        except Exception as e:
            logger.error(f"validate_options : {e}")
            raise serializers.ValidationError(_(f'No event selected. Please retry.'))
        if value:
            for option in value:
                option: OptionGenerale
                if option not in list(set(event.options_checkbox.all()) | set(event.options_radio.all())):
                    raise serializers.ValidationError(_(f'Option {option.name} unavailable for event'))
        return value

    def validate(self, attrs):
        """
        On vérifie ici :
            Qu'il existe au moins un billet pour la reservation.
            Que les produits sont prévu par l'évent
            Que chaque maximum par user est respecté
            TODO: Que chaque billet possède un nom/prenom si le billet doit être nominatif
        """
        logger.info(f"validate : {attrs}")
        event = self.event

        if not hasattr(self, 'admin_created') :
            # Si ça n'est pas un ticket créé dans l'admin, on va chercher les produits dans le POST
            products_dict = self.extract_products()
        else :
            # c'est appellé depuis ADD de l'admin ticket
            products_dict = getattr(self, 'products_dict')

        user = self.user
        options = attrs.get('options')

        # Si c'est un event en mode resa en un clic
        total_ticket_qty = 1 if event.easy_reservation else 0

        # existe au moins un billet pour la reservation ?
        if not event.easy_reservation:
            if not products_dict or len(products_dict) < 1:
                raise serializers.ValidationError(_(f'No products.'))

        for product, price_dict in products_dict.items():
            # les produits sont prévu par l'évent ?
            if product not in event.products.all():
                raise serializers.ValidationError(_(f'Invalid product.'))

            # chaque maximum par user est respecté ?
            for price, qty in price_dict.items():
                if qty > price.max_per_user:
                    raise serializers.ValidationError(
                        _(f'Bookings exceed capacity for this rate.'))
                total_ticket_qty += qty

                # Check adhésion
                if price.adhesion_obligatoire:
                    if not user.memberships.filter(price__product=price.adhesion_obligatoire, deadline__gte=timezone.now()).exists():
                        logger.warning(_(f"User is not subscribed."))
                        raise serializers.ValidationError(_(f"User is not subscribed."))

        # existe au moins un ticket validable pour la reservation ?
        if not total_ticket_qty > 0:
            raise serializers.ValidationError(_(f'No ticket.'))

        # Vérification du max par user sur l'event
        if total_ticket_qty > event.max_per_user:
            raise serializers.ValidationError(_(f'Order quantity surpasses maximum allowed per user.'))

        # Pour vérification plus bas que le prix libre est bien seul
        if hasattr(self, 'free_price'):
            if self.free_price:
                if len(self.products) > 1:
                    raise serializers.ValidationError(_(f'A free price must be selected alone.'))

        # Vérification de la jauge
        valid_tickets_count = event.valid_tickets_count()
        under_purchase = event.under_purchase()
        if valid_tickets_count + total_ticket_qty + under_purchase > event.jauge_max:
            remains = event.jauge_max - valid_tickets_count - under_purchase
            raise serializers.ValidationError(_('Number of places available : ')+ f"{remains}")

        # Vérification que l'utilisateur peut reserer une place s'il est déja inscrit sur un horaire
        if not Configuration.get_solo().allow_concurrent_bookings:
            start_this_event = event.datetime
            end_this_event = event.end_datetime
            if not end_this_event:
                end_this_event = start_this_event + timedelta(hours=1) # Si ya pas de fin sur l'event, on rajoute juste une heure.

            if Reservation.objects.filter(
                user_commande=user,
            ).filter(
                Q(event__datetime__range=(start_this_event, end_this_event)) |
                Q(event__end_datetime__range=(start_this_event, end_this_event)) |
                Q(event__datetime__lte=start_this_event, event__end_datetime__gte=end_this_event)
            ).exists():
                raise serializers.ValidationError(_(f'You have already booked this slot.'))


        # Collect dynamic custom form fields from request (names prefixed with 'form__')
        request = self.context.get('request')
        req_data = request.data if request is not None else self.initial_data

        # Build map of expected dynamic fields across all selected products
        custom_form = {}
        try:
            selected_products = list(products_dict.keys())
            product_fields_qs = ProductFormField.objects.filter(product__in=selected_products)
            product_fields = {ff.name: ff for ff in product_fields_qs}
        except Exception:
            product_fields = {}

        for name, ff in product_fields.items():
            key = f"form__{name}"
            if hasattr(req_data, 'getlist') and ff.field_type == ProductFormField.FieldType.MULTI_SELECT:
                value = req_data.getlist(key)
            else:
                value = req_data.get(key)
                if ff.field_type == ProductFormField.FieldType.MULTI_SELECT:
                    if value in [None, '']:
                        value = []
                    elif not isinstance(value, list):
                        value = [value]

            # Enforce required
            if ff.required:
                if ff.field_type == ProductFormField.FieldType.MULTI_SELECT:
                    if not value:
                        raise serializers.ValidationError({key: [_('This field is required.')]})
                else:
                    if value in [None, '']:
                        raise serializers.ValidationError({key: [_('This field is required.')]})

            # Only store non-empty values
            if ff.field_type == ProductFormField.FieldType.MULTI_SELECT:
                if value:
                    custom_form[name] = value
            else:
                if value not in [None, '']:
                    custom_form[name] = value

        # On fabrique l'objet reservation
        reservation = Reservation.objects.create(
            user_commande=user,
            event=event,
            custom_form=custom_form or None,
        )

        if options:
            for option in options:
                reservation.options.add(option)

        self.reservation = reservation

        # Fabrication de la reservation et des tickets en fonction du type de produit
        self.tickets = TicketCreator(
            reservation=reservation,
            products_dict=products_dict,
        )
        self.reservation = reservation
        # On récupère le lien de paiement fabriqué dans le TicketCreator si besoin :
        self.checkout_link = self.tickets.checkout_link if self.tickets.checkout_link else None

        return attrs


class MembershipValidator(serializers.Serializer):
    """
    Validator reclamé lors de la réclamation d'une adhésion depuis le front Lespass
    """
    acknowledge = serializers.BooleanField()
    price = serializers.PrimaryKeyRelatedField(
        queryset=Price.objects.filter(product__categorie_article=Product.ADHESION)
    )

    firstname = serializers.CharField(max_length=200)
    lastname = serializers.CharField(max_length=200)
    email = serializers.EmailField()

    options = serializers.PrimaryKeyRelatedField(queryset=OptionGenerale.objects.all(), many=True,
                                                 allow_null=True, required=False)

    newsletter = serializers.BooleanField()


    @staticmethod
    def get_checkout_stripe(membership: Membership):
        # Fiche membre créée, si price payant, on crée le checkout stripe :
        price: Price = membership.price
        user: TibilletUser = membership.user
        tenant: Client = connection.tenant

        # besoin pour le retour webhook classique et renouvellement abonnement : ApiBillet.views.Webhook_stripe.post
        metadata = {
            'tenant': f'{tenant.uuid}',
            'tenant_name': f'{tenant.name}',
            'price_uuid': f"{price.uuid}",
            'product_price_name': f"{membership.price.product.name} {membership.price.name}",
            'membership_uuid': f"{membership.uuid}",
            'user': f"{user.email}",
        }

        ligne_article_adhesion = LigneArticle.objects.create(
            pricesold=get_or_create_price_sold(price),
            membership=membership,
            amount=int(price.prix * 100),
            qty=1,
        )

        # Création de l'objet paiement stripe en base de donnée
        new_paiement_stripe = CreationPaiementStripe(
            user=user,
            liste_ligne_article=[ligne_article_adhesion, ],
            metadata=metadata,
            reservation=None,
            source=Paiement_stripe.FRONT_BILLETTERIE,
            success_url=f"stripe_return/",
            cancel_url=f"stripe_return/",
            absolute_domain=f"https://{tenant.get_primary_domain()}/memberships/",
        )

        # Passage du status en UNPAID
        if not new_paiement_stripe.is_valid():
            raise serializers.ValidationError(new_paiement_stripe.errors)

        paiement_stripe: Paiement_stripe = new_paiement_stripe.paiement_stripe_db
        paiement_stripe.lignearticles.all().update(status=LigneArticle.UNPAID)

        # On ajoute le paiement dans l'objet membership
        membership.stripe_paiement.add(paiement_stripe)

        # Retour de l'url vers qui rediriger
        checkout_stripe_url = new_paiement_stripe.checkout_session.url
        return checkout_stripe_url

    def validate(self, attrs):
        self.price = attrs['price']

        # Création de l'user après les validation champs par champ ( un robot peut spammer le POST et créer des user a la volée sinon )
        self.user = get_or_create_user(attrs['email'])

        ### CREATION DE LA FICHE MEMBRE
        # Il peut y avoir plusieurs adhésions pour le même user (ex : parent/enfant)
        membership = Membership.objects.create(
            user=self.user,
            price=self.price
        )

        membership.first_name = attrs['firstname']
        membership.last_name = attrs['lastname']

        # Sur le form, on coche pour NE PAS recevoir la news
        membership.newsletter = not attrs.get('newsletter')

        # Set remplace les options existantes, accepte les listes
        options = attrs.get('options', [])
        if options:
            membership.option_generale.set(attrs['options'])

        # Collect dynamic custom form fields from request (names prefixed with 'form__')
        request = self.context.get('request')
        req_data = request.data if request else {}

        # Build a map of expected fields for this product to validate types/required
        custom_form = {}
        try:
            product = self.price.product
            product_fields = {ff.name: ff for ff in ProductFormField.objects.filter(product=product)}
        except Exception:
            product_fields = {}

        for name, ff in product_fields.items():
            key = f"form__{name}"
            value = None
            if hasattr(req_data, 'getlist') and ff.field_type == ProductFormField.FieldType.MULTI_SELECT:
                value = req_data.getlist(key)
            else:
                value = req_data.get(key)
                # If MULTI_SELECT but parser gave a scalar, normalize to list
                if ff.field_type == ProductFormField.FieldType.MULTI_SELECT:
                    if value in [None, '']:
                        value = []
                    elif not isinstance(value, list):
                        value = [value]

            # Enforce required
            if ff.required:
                if ff.field_type == ProductFormField.FieldType.MULTI_SELECT:
                    if not value:
                        raise serializers.ValidationError({key: [_('This field is required.')]})
                else:
                    if value in [None, '']:
                        raise serializers.ValidationError({key: [_('This field is required.')]})

            # Only store non-empty values
            if ff.field_type == ProductFormField.FieldType.MULTI_SELECT:
                if value:
                    custom_form[name] = value
            else:
                if value not in [None, '']:
                    custom_form[name] = value

        membership.custom_form = custom_form or None

        membership.save()
        self.membership = membership
        # Création du lien de paiement
        self.checkout_stripe_url = self.get_checkout_stripe(membership)

        return attrs


class TenantCreateValidator(serializers.Serializer):
    email = serializers.EmailField()
    emailConfirmation = serializers.EmailField()
    name = serializers.CharField(max_length=200)
    laboutik = serializers.BooleanField(required=True)
    cgu = serializers.BooleanField(required=True)
    payment_wanted = serializers.BooleanField(required=True)
    dns_choice = serializers.ChoiceField(choices=["tibillet.coop", "tibillet.re"])
    website = serializers.URLField(required=True)
    short_description = serializers.CharField(max_length=250)

    def validate_cgu(self, value):
        if not value:
            raise serializers.ValidationError(_('Please accept terms and conditions.'))
        return value

    def validate_name(self, value):
        if WaitingConfiguration.objects.filter(slug=slugify(value)).exists():
            raise serializers.ValidationError(f"{value}. "+ _('This name is not available'))
        if Client.objects.filter(name=value).exists():
            raise serializers.ValidationError(f"{value}. "+ _('This name is not available'))
        if Domain.objects.filter(domain__icontains=f'{slugify(value)}').exists():
            raise serializers.ValidationError(f"{value}. "+ _('This name is not available'))

        return value

    @staticmethod
    def create_tenant(waiting_config: WaitingConfiguration):
        name = waiting_config.organisation
        admin_email = waiting_config.email.lower()
        if waiting_config.tenant:
            raise Exception("Tenant already exists. ")

        with schema_context('public'):
            tenant = Client.objects.filter(categorie=Client.WAITING_CONFIG).first()
            if not tenant:
                raise Exception("No waiting tenant. ")

            slug = slugify(name)
            dns = waiting_config.dns_choice if waiting_config.dns_choice else 'tibillet.coop'
            if settings.DEBUG :
                dns = "tibillet.localhost"

            tenant.name=name
            tenant.on_trial=False
            tenant.categorie=Client.SALLE_SPECTACLE
            tenant.save()

            Domain.objects.get_or_create(
                domain=f'{slug}.{dns}',
                tenant=tenant,
                is_primary=True
            )


        with tenant_context(tenant):
            ## Création du premier admin:
            from django.contrib.auth.models import Group
            staff_group, created = Group.objects.get_or_create(name="staff")

            # Sans envoi d'email pour l'instant, on l'envoie quand tout sera bien terminé
            user: TibilletUser = get_or_create_user(admin_email, send_mail=False)
            user.client_admin.add(tenant)
            user.is_staff = True
            user.groups.add(staff_group)
            user.save()

            from BaseBillet.models import Configuration
            config = Configuration.get_solo()
            config.organisation = name
            config.site_web = waiting_config.site_web
            config.short_description = waiting_config.short_description
            config.long_description = """<div><strong>Bienvenue dans votre nouvel espace !</strong><br>Pour changer ce texte visible par tout le monde, allez découvrir votre panneau d\'administration dans votre espace "Mon Compte".<br><br>Hésitez surtout pas à venir discuter avec nous sur l\'un de nos canaux :<br>- <a href="https://discord.gg/7FJvtYx">Discord</a><br>- <a href="https://matrix.to/#/#tibillet:tiers-lieux.org">Matrix</a><br>- <a href="https://pouet.chapril.org/@tibillet">Mastodon</a><br><br>Nous vous accompagnerons avec plaisir !</div>"""
            config.slug = slugify(name)
            config.email = user.email

            try :
                rootConf = RootConfiguration.get_solo()
                stripe.api_key = rootConf.get_stripe_api()
                config.stripe_mode_test = rootConf.stripe_mode_test
                info_stripe = stripe.Account.retrieve(waiting_config.id_acc_connect)
                config.site_web = info_stripe.business_profile.url
                config.phone = info_stripe.business_profile.support_phone
                if rootConf.stripe_mode_test:
                    config.stripe_connect_account_test = info_stripe.id
                else:
                    config.stripe_connect_account = info_stripe.id
            except Exception as e:
                logger.info("Stripe non ok")
                pass

            config.save()

            # Liaison / création du lieu coté Fedow :
            from fedow_connect.fedow_api import FedowAPI
            from fedow_connect.models import FedowConfig
            FedowAPI()
            if not FedowConfig.get_solo().can_fedow():
                raise Exception('Error on install : can_fedow = False')

            # Envoie du mail de connection et validation
            get_or_create_user(admin_email, force_mail=True)

            # Création des articles par default :
            freeres, created = Product.objects.get_or_create(
                name="Réservation gratuite",
                categorie_article=Product.FREERES,
            )

            freeres_p, created = Price.objects.get_or_create(
                name="Tarif gratuit",
                prix=0,
                product=freeres,
                max_per_user=10,
            )

        waiting_config.tenant = tenant
        waiting_config.created = True
        waiting_config.save()

        return tenant
