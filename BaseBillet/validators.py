import logging
import re
from datetime import timedelta
from decimal import Decimal
from typing import Any, Dict, Optional, List

import stripe
from django.conf import settings
from django.db import connection
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _, activate
from django_tenants.utils import tenant_context, schema_context
from rest_framework import serializers

from Administration.utils import clean_html as admin_clean_html
from ApiBillet.serializers import get_or_create_price_sold, dec_to_int
from AuthBillet.models import TibilletUser, Wallet
from AuthBillet.utils import get_or_create_user
from BaseBillet.models import Event, PostalAddress, Tag, Configuration
from BaseBillet.models import Price, Product, OptionGenerale, Membership, Paiement_stripe, LigneArticle, Reservation, \
    PriceSold, Ticket, ProductSold, ProductFormField, PromotionalCode, PaymentMethod
from BaseBillet.tasks import send_membership_pending_admin, send_membership_pending_user
from Customers.models import Client, Domain
from MetaBillet.models import WaitingConfiguration
from PaiementStripe.views import CreationPaiementStripe
from fedow_connect.fedow_api import FedowAPI
from fedow_connect.utils import dround
from root_billet.models import RootConfiguration

logger = logging.getLogger(__name__)


def build_custom_form_from_request(req_data, products, prefix: str = 'form__'):
    """
    Factorized validator for dynamic custom forms based on ProductFormField.
    - req_data: request.data or a plain dict-like object; may be a QueryDict with getlist().
    - products: iterable of Product for which to load ProductFormField definitions.
    - prefix: key prefix expected in the payload (default: 'form__').
    Returns: dict of validated values; raises serializers.ValidationError with field-key mapping on error.
    """
    # Collect ProductFormField for the provided products
    custom_form = {}
    try:
        product_fields_qs = ProductFormField.objects.filter(product__in=list(products))
        product_fields = {ff.name: ff for ff in product_fields_qs}
    except Exception:
        product_fields = {}

    for name, ff in product_fields.items():
        key = f"{prefix}{name}"
        # Use label as the JSON key; fallback to name if label is empty
        label_key = (ff.label or '').strip() or name
        # MULTI SELECT → normalize to list
        if ff.field_type == ProductFormField.FieldType.MULTI_SELECT:
            if hasattr(req_data, 'getlist'):
                value_list = req_data.getlist(key)
            else:
                v = req_data.get(key)
                if v in [None, '']:
                    value_list = []
                elif isinstance(v, list):
                    value_list = v
                else:
                    value_list = [v]

            # Required
            if ff.required and not value_list:
                raise serializers.ValidationError({key: [_('This field is required.')]})

            # Validate options
            if value_list:
                invalid = [val for val in value_list if ff.options and val not in ff.options]
                if invalid:
                    raise serializers.ValidationError({key: [_('Invalid choice.')]})

            if value_list:
                if label_key in custom_form:
                    # Duplicate label collision across fields -> put error on current request key
                    raise serializers.ValidationError({key: [_('Duplicate field label. Please change the label.')]})
                custom_form[label_key] = value_list
            continue

        # SINGLE SELECT (dropdown) or RADIO SELECT → scalar
        if ff.field_type in (ProductFormField.FieldType.SINGLE_SELECT, ProductFormField.FieldType.RADIO_SELECT):
            value = req_data.get(key)
            if ff.required and value in [None, '']:
                raise serializers.ValidationError({key: [_('This field is required.')]})
            if value not in [None, '']:
                if ff.options and value not in ff.options:
                    raise serializers.ValidationError({key: [_('Invalid choice.')]})
                if label_key in custom_form:
                    raise serializers.ValidationError({key: [_('Duplicate field label. Please change the label.')]})
                custom_form[label_key] = value
            continue

        # BOOLEAN → always store boolean (default False if not sent)
        if ff.field_type == ProductFormField.FieldType.BOOLEAN:
            raw = req_data.get(key)
            bool_val = False
            if raw is not None:
                sval = str(raw).lower()
                bool_val = sval in ('1', 'true', 'on', 'yes', 'y')
            if ff.required and not bool_val:
                raise serializers.ValidationError({key: [_('This field is required.')]})
            if label_key in custom_form:
                raise serializers.ValidationError({key: [_('Duplicate field label. Please change the label.')]})
            custom_form[label_key] = bool_val
            continue

        # Default (text areas, etc.) → scalar
        value = req_data.get(key)
        if ff.required and value in [None, '']:
            raise serializers.ValidationError({key: [_('This field is required.')]})
        if value not in [None, '']:
            if label_key in custom_form:
                raise serializers.ValidationError({key: [_('Duplicate field label. Please change the label.')]})
            custom_form[label_key] = value

    return custom_form


class ContactValidator(serializers.Serializer):
    email = serializers.EmailField()
    subject = serializers.CharField()
    message = serializers.CharField()
    # Captcha arithmétique très simple: x + y == answer
    x = serializers.IntegerField(required=True, min_value=0)
    y = serializers.IntegerField(required=True, min_value=0)
    answer = serializers.IntegerField(required=True)

    def validate(self, attrs):
        # Vérifie que la réponse correspond à la somme x + y
        try:
            x = int(attrs.get('x', 0))
            y = int(attrs.get('y', 0))
            answer = int(attrs.get('answer', -1))
        except (TypeError, ValueError):
            raise serializers.ValidationError({'answer': [_('Please answer the anti-spam question.')]})

        if x + y != answer:
            raise serializers.ValidationError({'answer': [_('Wrong answer to the anti-spam question.')]})

        return attrs


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
            raise serializers.ValidationError(
                _(f"Email confirmation failed: the email and its confirmation are different. A typo, maybe?"))
        return attrs


class LoginEmailValidator(serializers.Serializer):
    email = serializers.EmailField()


class TicketCreator():

    def __init__(self, reservation: Reservation, products_dict: dict, promo_code: PromotionalCode = None):
        self.products_dict = products_dict
        self.reservation = reservation
        self.user = reservation.user_commande
        self.promo_code = promo_code
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
        return [ticket, ]

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
            pricesold: PriceSold = get_or_create_price_sold(
                price_generique,
                event=event,
                promo_code=self.promo_code)

            # les lignes articles pour la vente
            line_article = LigneArticle.objects.create(
                pricesold=pricesold,
                amount=dec_to_int(pricesold.prix),
                payment_method=PaymentMethod.STRIPE_NOFED,
                qty=qty,
                promotional_code=self.promo_code,
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

        logger.debug(f"get_checkout_stripe OK : {new_paiement_stripe.checkout_session.stripe_id}")
        return new_paiement_stripe.checkout_session.url


class ReservationValidator(serializers.Serializer):
    email = serializers.EmailField()
    # to_mail = serializers.BooleanField(default=True, required=False)
    event = serializers.PrimaryKeyRelatedField(
        queryset=Event.objects.filter(datetime__gte=timezone.now() - timedelta(days=1)))
    options = serializers.PrimaryKeyRelatedField(queryset=OptionGenerale.objects.all(), many=True, allow_null=True,
                                                 required=False)
    datetime = serializers.DateTimeField(required=False)
    promotional_code = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def extract_products(self):
        """
        On vérifie ici :
            les objets produit et prix existent bien en DB et a une quantité valide
        """
        # Rercher des produits potentiels
        event = self.event
        products_dict = {}
        self.products = []  # Pour checker si un formulaire forbricks est présent
        self.free_price = False  # Pour vérification plus bas que le prix libre est bien seul

        for product in event.products.all():
            for price in product.prices.all():
                # Un input possède l'uuid du prix ?
                raw_val = self.initial_data.get(str(price.uuid))
                if raw_val not in [None, '']:
                    # Certains frontends envoient des nombres comme "15.00" → normaliser en int de manière sûre
                    try:
                        # Depuis une QueryDict, la valeur peut être une liste
                        if isinstance(raw_val, list):
                            raw_val = raw_val[-1] if raw_val else ''
                        sval = str(raw_val).strip().replace(',', '.')
                        # Autoriser les décimales mais caster en entier (quantité)
                        qty = int(Decimal(sval))
                    except Exception:
                        raise serializers.ValidationError({str(price.uuid): [_('Invalid quantity.')]})

                    if qty <= 0:  # Skip zero or negative quantities
                        continue

                    if price.free_price:  # Pour vérification plus bas que le prix libre est bien seul
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
        if not hasattr(self, 'admin_created'):  # Si ça n'est pas un ticket créé dans l'admin :
            # On vérifie que l'utilisateur connecté et l'email correspondent bien.
            request = self.context.get('request')
            if request.user.is_authenticated:
                if request.user.email != value:
                    raise serializers.ValidationError(_(f"Email does not match logged-in user."))

        self.user = get_or_create_user(value)
        return value

    def validate_options(self, value):
        # On check que les options sont bien dans l'event original.
        try:
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

    def validate_promotional_code(self, value):
        """
        Validate promotional code if provided.
        The code must exist by name and will be fully validated in validate() 
        to ensure it's linked to a selected product.
        """
        # If empty or None, no validation needed (it's optional)
        if not value:
            return value

        # Check if promotional code exists by name
        try:
            promo_code = PromotionalCode.objects.get(name=value, is_active=True)
            if not promo_code.is_usable():
                raise serializers.ValidationError(_(f'Invalid or inactive promotional code.'))

            # Store for later validation in validate() method
            self.promo_code = promo_code
            logger.info(f"validate_promotional_code : {promo_code.name} found for product {promo_code.product.name}")
            return value
        except PromotionalCode.DoesNotExist:
            logger.warning(f"validate_promotional_code : {value} not found or inactive")
            raise serializers.ValidationError(_(f'Invalid or inactive promotional code.'))
        except PromotionalCode.MultipleObjectsReturned:
            logger.warning(f"validate_promotional_code : multiple codes with name {value}")
            raise serializers.ValidationError(_(f'Invalid promotional code.'))

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

        if not hasattr(self, 'admin_created'):
            # Si ça n'est pas un ticket créé dans l'admin, on va chercher les produits dans le POST
            products_dict = self.extract_products()
        else:
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

        # Validate promotional code is linked to a selected product
        if hasattr(self, 'promo_code'):
            promo_code = self.promo_code
            selected_products = list(products_dict.keys())
            if promo_code.product not in selected_products:
                logger.warning(f"Promotional code {promo_code.name} not linked to selected products")
                raise serializers.ValidationError(
                    _(f'The promotional code is not valid for the selected products.')
                )
            logger.info(f"Promotional code {promo_code.name} validated for product {promo_code.product.name}")

        for product, price_dict in products_dict.items():
            # Si le maximum par user produit est déja atteint :
            if product.max_per_user_reached(user, event=event):
                raise serializers.ValidationError(_(f'Maximum capacity reached for this product.'))

            # les produits sont prévu par l'évent ?
            if product not in event.products.all():
                raise serializers.ValidationError(_(f'Invalid product.'))

            # chaque maximum par user est respecté ?
            for price, qty in price_dict.items():
                # Si l'user a déja reservé avant :
                if price.max_per_user_reached(user, event=event):
                    raise serializers.ValidationError(_(f'Maximum capacity reached for this price.'))

                # Si la jauge de ce prix est atteinte
                if price.out_of_stock(event=event):
                    raise serializers.ValidationError(_(f'Maximum capacity reached for this price.'))

                if price.max_per_user:
                    if qty > price.max_per_user:
                        raise serializers.ValidationError(
                            _(f'Bookings exceed capacity for this rate.'))
                total_ticket_qty += qty

                # Check adhésion
                if price.adhesion_obligatoire:
                    if not user.memberships.filter(price__product=price.adhesion_obligatoire,
                                                   deadline__gte=timezone.now()).exists():
                        logger.warning(_(f"User is not subscribed."))
                        raise serializers.ValidationError(_(f"User is not subscribed."))

        # existe au moins un ticket validable pour la reservation ?
        if not total_ticket_qty > 0:
            raise serializers.ValidationError(_(f'No ticket.'))

        # Vérification du max par user sur l'event
        if event.max_per_user:
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
            raise serializers.ValidationError(_('Number of places available : ') + f"{remains}")

        # Vérification que l'utilisateur peut reserer une place s'il est déja inscrit sur un horaire
        if not Configuration.get_solo().allow_concurrent_bookings:
            start_this_event = event.datetime
            end_this_event = event.end_datetime
            if not end_this_event:
                end_this_event = start_this_event + timedelta(
                    hours=1)  # Si ya pas de fin sur l'event, on rajoute juste une heure.

            if Reservation.objects.filter(
                    user_commande=user,
            ).filter(
                Q(event__datetime__range=(start_this_event, end_this_event)) |
                Q(event__end_datetime__range=(start_this_event, end_this_event)) |
                Q(event__datetime__lte=start_this_event, event__end_datetime__gte=end_this_event)
            ).exists():
                raise serializers.ValidationError(_(f'You have already booked this slot.'))

        # Build validated custom_form from dynamic fields (prefixed with 'form__') across selected products
        request = self.context.get('request')
        req_data = request.data if request is not None else self.initial_data
        selected_products = list(products_dict.keys())
        custom_form = build_custom_form_from_request(req_data, selected_products, prefix='form__')

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
            promo_code=self.promo_code if hasattr(self, 'promo_code') else None,
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
    custom_amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
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

        amount = int(membership.contribution_value * 100)

        ligne_article_adhesion = LigneArticle.objects.create(
            pricesold=get_or_create_price_sold(price, custom_amount=membership.contribution_value),
            membership=membership,
            payment_method=PaymentMethod.STRIPE_NOFED,
            amount=amount,
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
        self.price: Price = attrs['price']

        # On va chercher le montant si c'est un prix libre
        amount: Decimal = self.price.prix
        if self.price.free_price:
            amount = attrs.get('custom_amount', None)

            if self.price.prix:  # on a un tarif minimum, on vérifie que le montant est bien supérieur :
                contribution: Decimal = amount or self.price.prix
                if contribution < self.price.prix:
                    logger.info("prix inférieur au minimum")
                    raise serializers.ValidationError(_('The amount must be greater than the minimum amount.'))

        # Création de l'user après les validation champs par champ ( un robot peut spammer le POST et créer des user a la volée sinon )
        self.user = get_or_create_user(attrs['email'])

        # Vérififaction du max par user sur le produit :
        # import ipdb; ipdb.set_trace()
        if self.price.product.max_per_user_reached(user=self.user):
                raise serializers.ValidationError(_(f'This product is limited in quantity per person.'))

        # Vérification du max per user
        if self.price.max_per_user:
            user_membeshipr_count = Membership.objects.filter(
                user=self.user,
                price=self.price,
                deadline__gt=timezone.localtime()).exclude(
                status__in=[Membership.CANCELED, Membership.ADMIN_CANCELED]
            ).count()
            if user_membeshipr_count >= self.price.max_per_user:
                logger.info("max per user")
                raise serializers.ValidationError(_(f'This product is limited in quantity per person.'))


        ### CREATION DE LA FICHE MEMBRE
        # On fait create, car il peut y avoir plusieurs adhésions pour le même user (ex : parent/enfant)
        membership = Membership.objects.create(
            user=self.user,
            price=self.price,
            contribution_value=amount,
            status=Membership.WAITING_PAYMENT,
            first_name = attrs['firstname'],
            last_name = attrs['lastname'],
            newsletter = not attrs.get('newsletter'), # TODO: A virer, utiliser les options ou les formulaires dynamiques : laisser le choix à l'admin
        )

        # Vérification de la validation manuelle
        if self.price.manual_validation:
            logger.info(f"membership_validator.price.manual_validation")
            # Marque la fiche comme nécessitant une validation manuelle et place l'état sur "en attente"
            membership.status = Membership.ADMIN_WAITING
            # Envoi des mails pour prévenir les users
            send_membership_pending_admin.delay(str(membership.uuid))
            send_membership_pending_user.delay(str(membership.uuid))

        # Inititation des itérations de récurrence maximales
        if self.price.recurring_payment and self.price.iteration :
            membership.max_iteration = self.price.iteration

        # Set remplace les options existantes, accepte les listes
        options = attrs.get('options', [])
        if options:
            membership.option_generale.set(attrs['options'])

        # Build validated custom_form from dynamic fields (prefixed with 'form__') for the membership product
        request = self.context.get('request')
        req_data = request.data if request else {}
        product = self.price.product
        custom_form = build_custom_form_from_request(req_data, [product], prefix='form__')
        membership.custom_form = custom_form or None

        membership.save()
        self.membership = membership

        # Création du lien de paiement
        self.checkout_stripe_url = None
        if membership.status == Membership.WAITING_PAYMENT:
            self.checkout_stripe_url = self.get_checkout_stripe(membership)

        return attrs


class TenantCreateValidator(serializers.Serializer):
    email = serializers.EmailField()
    emailConfirmation = serializers.EmailField()
    name = serializers.CharField(max_length=200)
    cgu = serializers.BooleanField(required=True)
    dns_choice = serializers.ChoiceField(choices=["tibillet.coop", "tibillet.re"])
    short_description = serializers.CharField(max_length=250)
    # Anti-spam très léger (même mécanisme que le formulaire de contact): x + y == answer
    x = serializers.IntegerField(required=True, min_value=0)
    y = serializers.IntegerField(required=True, min_value=0)
    answer = serializers.IntegerField(required=True)

    def validate_cgu(self, value):
        if not value:
            raise serializers.ValidationError(_('Please accept terms and conditions.'))
        return value

    def validate_name(self, value):
        if WaitingConfiguration.objects.filter(slug=slugify(value)).exists():
            raise serializers.ValidationError(f"{value}. " + _('This name is not available'))
        if Client.objects.filter(name=value).exists():
            raise serializers.ValidationError(f"{value}. " + _('This name is not available'))
        if Domain.objects.filter(domain__icontains=f'{slugify(value)}').exists():
            raise serializers.ValidationError(f"{value}. " + _('This name is not available'))

        return value

    def validate(self, attrs):
        # Validation anti-spam: vérifier que answer == x + y (identique à ContactValidator)
        try:
            x = int(attrs.get('x', 0))
            y = int(attrs.get('y', 0))
            answer = int(attrs.get('answer', -1))
        except (TypeError, ValueError):
            raise serializers.ValidationError({'answer': [_('Please answer the anti-spam question.')]})

        if x + y != answer:
            raise serializers.ValidationError({'answer': [_('Wrong answer to the anti-spam question.')]})

        return attrs

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
            if settings.DEBUG:
                dns = "tibillet.localhost"

            tenant.name = name
            tenant.on_trial = False
            tenant.categorie = Client.SALLE_SPECTACLE
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

            try:
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
            # get_or_create_user(admin_email, force_mail=True)

            # Création des articles par default :
            activate(config.language)
            if not Product.objects.filter(categorie_article=Product.FREERES).exists():
                freeres, created = Product.objects.get_or_create(
                    name=_("Free booking"),
                    categorie_article=Product.FREERES,
                ) # le post save créera le price 0

        waiting_config.tenant = tenant
        waiting_config.created = True
        waiting_config.save()

        return tenant


from uuid import UUID


class QrCodeScanPayNfcValidator(serializers.Serializer):
    """
    Valide la lecture NFC pour le paiement par QR Code.

    Attend un payload JSON de type:
      {
        "tagSerial": "62:fe:16:01",
        "ligne_article_uuid_hex": "c351ccd3a07b477ba1dcc8d5bcae72df"
      }

    Erreurs attendues:
      - La carte n'existe pas
      - le format du tag n'est pas bon
      - Il n'y a pas assez de crédit sur la carte
    """
    tagSerial = serializers.CharField(allow_blank=False)
    ligne_article_uuid_hex = serializers.CharField(allow_blank=False)

    def _normalize_tag(self, value: str) -> str:
        if value is None:
            return ''
        v = value.strip().lower().replace(':', '').replace('-', '')

        # Doit être exactement 8 caractères hexadécimaux (4 octets)
        if not re.match(r'^[0-9A-Fa-f]{8}$', v):
            raise serializers.ValidationError(_("le format du tag NFC n\'est pas bon"))

        return v.upper()

    def validate_tagSerial(self, value: str):
        tag_id = self._normalize_tag(value)
        # stocke pour validate()
        self.tag_id = tag_id

        self.fedowAPI = FedowAPI()
        card_serialized = self.fedowAPI.NFCcard.card_tag_id_retrieve(tag_id)
        if not card_serialized:
            raise serializers.ValidationError(_("La carte n'existe pas"))

        if card_serialized.get('is_wallet_ephemere'):
            raise serializers.ValidationError(
                _("La carte n'est pas liée à un.e utilisateur.ice. Merci de demander à la personne propriétaire de la lier en flashant le qrcode au dos de la carte."))

        wallet = Wallet.objects.get(uuid=card_serialized['wallet_uuid'])
        if not wallet.user:
            raise serializers.ValidationError(
                _("Le portefeuille n'est pas liée à un.e utilisateur.ice. Merci de demander à la personne propriétaire de la lier en flashant le qrcode au dos de la carte."))

        self.wallet = wallet
        return value

    def validate_ligne_article_uuid_hex(self, value: str):
        try:
            la_uuid = UUID(value)
            la = LigneArticle.objects.get(uuid=la_uuid, status=LigneArticle.CREATED,
                                          payment_method=PaymentMethod.QRCODE_MA)
        except Exception:
            raise serializers.ValidationError(_('Paiement introuvable.'))
        self.ligne_article = la
        return value

    def validate(self, attrs):
        self.user_balance = self.fedowAPI.wallet.get_total_fiducial_and_all_federated_token(self.wallet.user)
        if self.user_balance < self.ligne_article.amount:
            raise serializers.ValidationError(_(f'Solde insuffisant. Il reste {dround(self.user_balance)} sur le portefeuille.'))

        return attrs





class EventQuickCreateSerializer(serializers.Serializer):
    """Serializer DRF pour la création rapide d'un évènement simple via l'offcanvas HTMX.

    Champs en entrée (POST):
      - name: str (obligatoire)
      - datetime_start: str (input type="datetime-local") (obligatoire)
      - datetime_end: str (optionnel)
      - short_description: str (optionnel, 250 char max côté modèle)
      - long_description: str (optionnel, HTML autorisé mais nettoyé comme dans l'admin)
      - postal_address: pk (optionnel)
      - tags: str (liste séparée par virgules/point-virgule)
      - img: InMemoryUploadedFile (optionnel) — doit être passé via request.FILES

    Comportements:
      - Parse les datetimes comme des dates locales (naïves) et les localise dans le fuseau de Configuration.
      - Valide que datetime_end >= datetime_start si renseigné.
      - Nettoie long_description via l'utilitaire d'admin pour éviter les injections JS/HTML.
      - Crée l'Event publié et rattache les tags (création automatique si nécessaires).
      - Utilise request.user (contexte) pour remplir created_by.
    """

    name = serializers.CharField(allow_blank=False, trim_whitespace=True, max_length=200)
    datetime_start = serializers.CharField(allow_blank=False)
    datetime_end = serializers.CharField(required=False, allow_blank=True)
    short_description = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=250)
    long_description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    postal_address = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    tags = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    jauge_max = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    # L'image arrive dans files; on la récupère dans create via self.context

    def _get_tz(self):
        config = Configuration.get_solo()
        import pytz
        return pytz.timezone(getattr(config, 'fuseau_horaire', 'UTC'))

    def _parse_dt_local(self, raw: Optional[str]):
        if not raw:
            return None
        from datetime import datetime
        dt = datetime.fromisoformat(raw)
        # Si naïf, on localise dans le fuseau horaire de la configuration
        if dt.tzinfo is None:
            tz = self._get_tz()
            dt = tz.localize(dt)
        return dt

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        errors: Dict[str, List[str]] = {}

        # Datetimes
        try:
            dt_start = self._parse_dt_local(attrs.get('datetime_start'))
        except Exception:
            errors.setdefault('datetime_start', []).append("Format de date invalide. Veuillez utiliser le sélecteur de date.")
            dt_start = None

        try:
            dt_end = self._parse_dt_local(attrs.get('datetime_end')) if attrs.get('datetime_end') else None
        except Exception:
            errors.setdefault('datetime_end', []).append("Format de date invalide. Veuillez utiliser le sélecteur de date.")
            dt_end = None

        if dt_start and dt_end and dt_end < dt_start:
            errors.setdefault('datetime_end', []).append("La fin doit être postérieure au début.")

        # Adresse
        postal_address = None
        addr_pk = attrs.get('postal_address')
        if addr_pk:
            try:
                postal_address = PostalAddress.objects.get(pk=addr_pk)
            except PostalAddress.DoesNotExist:
                errors.setdefault('postal_address', []).append("Adresse sélectionnée introuvable.")

        # Long description sanitation
        ld = attrs.get('long_description')
        attrs['long_description'] = admin_clean_html(ld)

        # Jauge maximale (capacité)
        raw_jauge = attrs.get('jauge_max')
        jauge_value: Optional[int] = None
        if raw_jauge not in (None, ""):
            try:
                jauge_value = int(str(raw_jauge).strip())
                if jauge_value < 1:
                    raise ValueError()
            except Exception:
                errors.setdefault('jauge_max', []).append("Veuillez indiquer un nombre entier positif pour la jauge ou laisser vide.")

        # Si une jauge est renseignée, on exige l'existence d'un produit "réservation gratuite"
        free_res_product = None
        if jauge_value is not None:
            try:
                free_res_product = Product.objects.filter(
                    categorie_article=Product.FREERES,
                    publish=True,
                    archive=False,
                ).first()
            except Exception:
                free_res_product = None

            if not free_res_product:
                errors.setdefault('jauge_max', []).append(
                    "Aucun produit de réservation gratuite n'a été trouvé. Merci de créer d'abord un produit de réservation gratuite dans l'administration."
                )

        if errors:
            raise serializers.ValidationError(errors)

        attrs['datetime'] = dt_start
        attrs['end_datetime'] = dt_end
        attrs['postal_address_obj'] = postal_address
        attrs['jauge_value'] = jauge_value
        attrs['free_res_product'] = free_res_product
        return attrs

    def create(self, validated_data: Dict[str, Any]) -> Event:
        request = self.context.get('request')
        name = validated_data.get('name').strip()
        short_desc = (validated_data.get('short_description') or '').strip() or None
        long_desc = validated_data.get('long_description') or None
        postal_address = validated_data.get('postal_address_obj')  # peut être None -> remplacé au save
        jauge_value = validated_data.get('jauge_value')
        free_res_product: Optional[Product] = validated_data.get('free_res_product')

        event = Event(
            name=name,
            datetime=validated_data['datetime'],
            end_datetime=validated_data.get('end_datetime') or None,
            short_description=short_desc,
            long_description=long_desc,
            postal_address=postal_address,
            created_by=(request.user if request and getattr(request, 'user', None) and request.user.is_authenticated else None),
            published=True,
        )

        # Image (si transmise)
        if request and hasattr(request, 'FILES') and request.FILES.get('img'):
            event.img = request.FILES['img']

        # Capacité / jauge: si fournie, on l'applique et on affiche la jauge
        if jauge_value is not None:
            event.jauge_max = jauge_value
            event.show_gauge = True

        event.save()

        # Tags
        tags_input = self.initial_data.get('tags') if hasattr(self, 'initial_data') else None
        if tags_input:
            names = [t.strip() for t in re.split(r",|;", str(tags_input)) if t and t.strip()]
            for tname in names:
                # Ne pas utiliser "_" pour éviter d'écraser _() de traduction
                tag_obj, created = Tag.objects.get_or_create(name=tname)
                event.tag.add(tag_obj)

        # Si jauge -> rattacher le produit de réservation gratuite à l'évènement
        if jauge_value is not None and free_res_product:
            event.products.add(free_res_product)

        return event
