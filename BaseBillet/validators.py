import logging
import os
import re
import uuid
from datetime import timedelta
from decimal import Decimal
from itertools import product

import stripe
from django.db import connection
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from django_tenants.utils import tenant_context, schema_context
from rest_framework import serializers
from rest_framework.generics import get_object_or_404

from ApiBillet.serializers import get_or_create_price_sold, dec_to_int, create_ticket
from AuthBillet.models import TibilletUser
from AuthBillet.utils import get_or_create_user
from BaseBillet.models import Price, Product, OptionGenerale, Membership, Paiement_stripe, LigneArticle, Tag, Event, \
    Reservation, PriceSold, Ticket, ProductSold
from Customers.models import Client, Domain
from MetaBillet.models import WaitingConfiguration
from PaiementStripe.views import CreationPaiementStripe
from root_billet.models import RootConfiguration

logger = logging.getLogger(__name__)


class TagValidator(serializers.Serializer):
    tags = serializers.PrimaryKeyRelatedField(source="slug", queryset=Tag.objects.all(), many=True)

class LinkQrCodeValidator(serializers.Serializer):
    email = serializers.EmailField(required=True, allow_null=False)
    emailConfirmation = serializers.EmailField(required=True, allow_null=False)
    firstname = serializers.CharField(max_length=500, required=False, allow_blank=True)
    lastname = serializers.CharField(max_length=500, required=False, allow_blank=True)
    # data=request.POST.dict() in the controler for boolean
    cgu = serializers.BooleanField(required=True, allow_null=False)
    qrcode_uuid = serializers.UUIDField()


class LoginEmailValidator(serializers.Serializer):
    email = serializers.EmailField()


class TicketCreator():

    def __init__(self, reservation:Reservation, products_dict:dict):
        self.products_dict = products_dict
        self.reservation = reservation
        self.user = reservation.user_commande

        for product, prices_dict in products_dict.items():
            product: Product
            trigger_name = f"method_{product.categorie_article}"
            trigger = getattr(self, trigger_name)
            trigger(prices_dict)


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


class ReservationValidator(serializers.Serializer):
    email = serializers.EmailField()
    # to_mail = serializers.BooleanField(default=True, required=False)
    event = serializers.PrimaryKeyRelatedField(queryset=Event.objects.filter(datetime__gte=timezone.now() - timedelta(days=1)))
    options = serializers.PrimaryKeyRelatedField(queryset=OptionGenerale.objects.all(), many=True, allow_null=True)
    datetime = serializers.DateTimeField(required=False)

    def extract_products(self):
        """
        On vérifie ici :
            input dans template ressemble à ça : name="products[{{ product.uuid }}][{{ price.uuid }}]"
            les objets produit et prix existent bien en DB et a une quantité valide
        """
        # Rercher des produits potentiels
        event = self.event
        products_dict = {}
        for product in event.products.all():
            for price in product.prices.all():
                # Un input possède l'uuid du prix ?
                if self.initial_data.get(str(price.uuid)):
                    qty = int(self.initial_data.get(str(price.uuid)))
                    products_dict[product] = { price : qty }

        return products_dict


    def validate_event(self, value):
        logger.info(f"validate event : {value}")
        self.event: Event = value
        if self.event.complet():
            raise serializers.ValidationError(_(f'Jauge atteinte : Evenement complet.'))
        return value

    def validate_email(self, value):
        logger.info(f"validate email : {value}")
        # On vérifie que l'utilisateur connecté et l'email correspondent bien.
        request = self.context.get('request')

        if request.user.is_authenticated:
            if request.user.email != value :
                raise serializers.ValidationError(_(f"L'email ne correspond pas à l'utilisateur connecté."))
            user = request.user

        else :
            user = get_or_create_user(value)

        self.user = user
        return value

    def validate_options(self, value):
        # On check que les options sont bien dans l'event original.
        event: Event = self.event
        if value:
            for option in value:
                option: OptionGenerale
                if option not in list(set(event.options_checkbox.all()) | set(event.options_radio.all())):
                    raise serializers.ValidationError(_(f'Option {option.name} non disponible dans event'))
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
        products_dict = self.extract_products()
        user = self.user
        options = attrs.get('options')
        total_ticket_qty = 0

        # existe au moins un billet pour la reservation ?
        if not products_dict or len(products_dict) < 1 :
            raise serializers.ValidationError(_(f'Pas de produits.'))

        for product, price_dict in products_dict.items():
            # les produits sont prévu par l'évent ?
            if product not in event.products.all():
                raise serializers.ValidationError(_(f'Produit non valide.'))

            # chaque maximum par user est respecté ?
            for price, qty in price_dict.items():
                if qty > price.max_per_user:
                    raise serializers.ValidationError(
                        _(f'Quantitée de réservations suppérieure au maximum autorisé pour ce tarif'))
                total_ticket_qty += qty

        # existe au moins un ticket validable pour la reservation ?
        if not total_ticket_qty > 0 :
            raise serializers.ValidationError(_(f'Pas de ticket.'))

        # Vérification du max par user sur l'event
        if total_ticket_qty > event.max_per_user:
            raise serializers.ValidationError(_(f'Quantitée de réservations suppérieure au maximum autorisé'))

        # Vérification de la jauge
        valid_tickets_count = event.valid_tickets_count()
        if valid_tickets_count + total_ticket_qty > event.jauge_max:
            remains = event.jauge_max - valid_tickets_count
            raise serializers.ValidationError(_(f'Il ne reste que {remains} places disponibles'))

        """
        TODO: Verifier l'adhésion
        # si un tarif à une adhésion obligatoire, on confirme que :
        # Soit l'utilisateur est membre,
        # Soit il paye l'adhésion en même temps que le billet :
        all_price_buy = [price_object['price'] for price_object in self.prices_list]
        all_product_buy = [price.product for price in all_price_buy]
        for price_object in self.prices_list:
            price: Price = price_object['price']
            if price.adhesion_obligatoire:
                membership_products = [membership.price.product for membership in
                                       self.user_commande.membership.all()]
                if (price.adhesion_obligatoire not in membership_products
                        and price.adhesion_obligatoire not in all_product_buy):
                    logger.warning(_(f"L'utilisateur n'est pas membre"))
                    raise serializers.ValidationError(_(f"L'utilisateur n'est pas membre"))
        """

        # On fabrique l'objet reservation
        reservation = Reservation.objects.create(
            user_commande=user,
            event=event,
        )

        if options:
            for option in options:
                reservation.options.add(option)

        self.reservation = reservation

        # Fabrication de la reservation et des tickets en fonction du type de produit
        tickets = TicketCreator(
            reservation=reservation,
            products_dict=products_dict,
        )
        return attrs




class MembershipValidator(serializers.Serializer):
    acknowledge = serializers.BooleanField()
    price = serializers.PrimaryKeyRelatedField(
        queryset=Price.objects.filter(product__categorie_article=Product.ADHESION)
    )

    email = serializers.EmailField()
    firstname = serializers.CharField(max_length=200)
    lastname = serializers.CharField(max_length=200)

    options = serializers.PrimaryKeyRelatedField(queryset=OptionGenerale.objects.all(), many=True,
                                                          allow_null=True, required=False)

    newsletter = serializers.BooleanField()

    def validate_email(self, email):
        self.user = get_or_create_user(email)
        return email

    def validate_price(self, price):
        self.price = price
        return price

    def checkout_stripe(self):
        # Fiche membre créée, si price payant, on crée le checkout stripe :
        membership: Membership = self.membership
        price: Price = membership.price
        user: TibilletUser = membership.user
        tenant = connection.tenant

        metadata = {
            'tenant': f'{tenant.uuid}',
            'price': f"{price.pk}",
            'membership': f"{membership.pk}",
            'user': f"{user.pk}",
        }
        ligne_article_adhesion = LigneArticle.objects.create(
            pricesold=get_or_create_price_sold(price),
            membership=membership,
            amount=int(price.prix*100),
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


        membership.save()
        self.membership = membership
        # Création du lien de paiement
        self.checkout_stripe_url = self.checkout_stripe()

        return attrs


class TenantCreateValidator(serializers.Serializer):
    email = serializers.EmailField()
    name = serializers.CharField(max_length=200)
    laboutik = serializers.BooleanField(required=True)
    cgu = serializers.BooleanField(required=True)
    dns_choice = serializers.ChoiceField(choices=["tibillet.coop", "tibillet.re"])

    def validate_cgu(self, value):
        if not value:
            raise serializers.ValidationError(_('Please accept terms and conditions.'))
        return value

    def validate_name(self, value):
        try:
            Client.objects.get(schema_name=slugify(value))
            raise serializers.ValidationError(_('Tenant name exist'))
        except Client.DoesNotExist:
            return value

    @staticmethod
    def create_tenant(waiting_config: WaitingConfiguration):
        name = waiting_config.organisation
        admin_email = waiting_config.email.lower()

        with schema_context('public'):
            slug = slugify(name)
            domain = os.getenv("DOMAIN")
            tenant, created = Client.objects.get_or_create(
                schema_name=slug,
                name=name,
                on_trial=False,
                categorie=Client.SALLE_SPECTACLE,
            )
            Domain.objects.create(
                domain=f'{slug}.{waiting_config.dns_choice}',
                tenant=tenant,
                is_primary=True
            )

        with tenant_context(tenant):
            ## Création du premier admin:
            from django.contrib.auth.models import Group
            staff_group, created = Group.objects.get_or_create(name="staff")

            # Sans envoie d'email pour l'instant, on l'envoie quand tout sera bien terminé
            user: TibilletUser = get_or_create_user(admin_email, send_mail=False)
            user.client_admin.add(tenant)
            user.is_staff = True
            user.groups.add(staff_group)
            user.save()

            from BaseBillet.models import Configuration
            config = Configuration.get_solo()
            config.organisation = name
            config.slug = slugify(name)
            config.email = user.email

            rootConf = RootConfiguration.get_solo()
            config.stripe_mode_test = rootConf.stripe_mode_test

            if waiting_config.id_acc_connect:
                info_stripe = stripe.Account.retrieve(waiting_config.id_acc_connect)
                config.site_web = info_stripe.business_profile.url
                config.phone = info_stripe.business_profile.support_phone
                if rootConf.stripe_mode_test:
                    config.stripe_connect_account_test = info_stripe.id
                else:
                    config.stripe_connect_account = info_stripe.id

            config.save()

            # Liaison / création du lieu coté Fedow :
            from fedow_connect.fedow_api import FedowAPI
            from fedow_connect.models import FedowConfig
            FedowAPI()
            if not FedowConfig.get_solo().can_fedow():
                raise Exception('Erreur on install : can_fedow = False')

            # Envoie du mail de connection et validation
            get_or_create_user(admin_email, force_mail=True)

        return tenant
