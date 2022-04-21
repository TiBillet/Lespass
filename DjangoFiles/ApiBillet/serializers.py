import datetime

from django.contrib.auth import get_user_model
from django.contrib.sites import requests
from django.db import connection
from django.utils.text import slugify
from rest_framework import serializers
import json
from django.utils.translation import gettext, gettext_lazy as _
from rest_framework.generics import get_object_or_404
from django_tenants.utils import schema_context, tenant_context

from AuthBillet.models import TibilletUser, HumanUser
from AuthBillet.utils import validate_email_and_return_user

from BaseBillet.models import Event, Price, Product, Reservation, Configuration, LigneArticle, Ticket, Paiement_stripe, \
    PriceSold, ProductSold, Artist_on_event, OptionGenerale, Membership
from Customers.models import Client
from PaiementStripe.views import creation_paiement_stripe

import logging

from QrcodeCashless.models import CarteCashless

logger = logging.getLogger(__name__)


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = [
            "uuid",
            "name",
            "publish",
            "img",
            "categorie_article",
            "prices",
        ]
        depth = 1
        read_only_fields = [
            'uuid',
            'prices',
        ]


class PriceSerializer(serializers.ModelSerializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())

    class Meta:
        model = Price
        fields = [
            'uuid',
            'product',
            'name',
            'prix',
            'vat',
            'stock',
            'max_per_user',
        ]

        read_only_fields = [
            'uuid',
        ]
        depth = 1


class ConfigurationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Configuration
        fields = [
            "organisation",
            "slug",
            "short_description",
            "long_description",
            "adress",
            "postal_code",
            "city",
            "phone",
            "email",
            "site_web",
            "twitter",
            "facebook",
            "instagram",
            "adhesion_obligatoire",
            "button_adhesion",
            "map_img",
            "carte_restaurant",
            "img_variations",
            "logo_variations",
        ]
        read_only_fields = fields

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        # import ipdb;ipdb.set_trace()
        return representation


# class NewConfigSerializer(serializers.Serializer):
#     email = serializers.EmailField()
#     name = serializers.CharField(max_length=50)
#     short_description = serializers.CharField(max_length=250)
#
#     adress = serializers.CharField(max_length=250)
#     city = serializers.CharField(max_length=250)
#     # img
#     # logo
#
#     phone = serializers.CharField(max_length=20, required=True)
#     postal_code = serializers.IntegerField(required=True)
#
#     contribution_value = serializers.FloatField()


class NewConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = Configuration
        fields = [
            "organisation",
            "slug",
            "short_description",
            "long_description",
            "adress",
            "postal_code",
            "city",
            "phone",
            "email",
            "site_web",
            "twitter",
            "facebook",
            "instagram",
            "adhesion_obligatoire",
            "button_adhesion",
            "map_img",
            "carte_restaurant",
            "img",
            "logo",
        ]
        read_only_fields = ("slug",)


class ArtistEventCreateSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    datetime = serializers.DateTimeField()

    def validate_uuid(self, value):
        self.artiste_event_db = {}
        try:
            tenant = Client.objects.get(pk=value, categorie=Client.ARTISTE)
            self.artiste_event_db['tenant'] = tenant
            with tenant_context(tenant):
                self.artiste_event_db['config'] = Configuration.get_solo()
        except Client.DoesNotExist as e:
            raise serializers.ValidationError(_(f'{value} Artiste non trouvé'))
        return value

    def validate_datetime(self, value):
        self.artiste_event_db['datetime'] = value
        return value

    def validate(self, attrs):
        return self.artiste_event_db


class Artist_on_eventSerializer(serializers.ModelSerializer):
    configuration = ConfigurationSerializer()

    class Meta:
        model = Artist_on_event
        fields = [
            'datetime',
            'configuration',
        ]


class OptionTicketSerializer(serializers.ModelSerializer):
    class Meta:
        model = OptionGenerale
        fields = [
            'uuid',
            'name',
            'poids',
        ]
        read_only_fields = ('uuid', 'poids')


class EventCreateSerializer(serializers.Serializer):
    date = serializers.DateField()
    artists = ArtistEventCreateSerializer(many=True)
    products = serializers.ListField(required=False)
    options_radio = serializers.ListField(required=False)
    options_checkbox = serializers.ListField(required=False)

    def validate_products(self, value):
        self.products_db = []
        for uuid in value:
            try:
                product = Product.objects.get(pk=uuid)
                self.products_db.append(product)
            except Product.DoesNotExist as e:
                raise serializers.ValidationError(_(f'{uuid} Produit non trouvé'))
        return self.products_db

    def validate_options_radio(self, value):
        self.options_radio = []
        for uuid in value:
            try:
                option = OptionGenerale.objects.get(pk=uuid)
                self.options_radio.append(option)
            except Product.DoesNotExist as e:
                raise serializers.ValidationError(_(f'{uuid} Option non trouvé'))
        return self.options_radio

    def validate_options_checkbox(self, value):
        self.options_checkbox = []
        for uuid in value:
            try:
                option = OptionGenerale.objects.get(pk=uuid)
                self.options_checkbox.append(option)
            except Product.DoesNotExist as e:
                raise serializers.ValidationError(_(f'{uuid} Option non trouvé'))
        return self.options_checkbox

    def validate(self, attrs):
        # import ipdb; ipdb.set_trace()
        names = [artist.get('config').organisation for artist in attrs.get('artists')]
        print(names)
        list_datetime = [artist.get('datetime') for artist in attrs.get('artists')]
        list_datetime.sort()
        first_datetime = list_datetime[0]

        event, created = Event.objects.get_or_create(
            name=(" & ").join(names),
            datetime=first_datetime,
            categorie=Event.CONCERT,
        )

        event.products.clear()
        if attrs.get('products'):
            for product in attrs.get('products'):
                event.products.add(product)

        event.options_radio.clear()
        if attrs.get('options_radio'):
            for option in attrs.get('options_radio'):
                event.options_radio.add(option)

        event.options_checkbox.clear()
        if attrs.get('options_checkbox'):
            for option in attrs.get('options_checkbox'):
                event.options_checkbox.add(option)

        for artist_input in attrs.get('artists'):
            prog, created = Artist_on_event.objects.get_or_create(
                artist=artist_input.get('tenant'),
                datetime=artist_input.get('datetime'),
                event=event
            )

        print(attrs)
        return event


class EventSerializer(serializers.ModelSerializer):
    products = ProductSerializer(many=True)
    options_radio = OptionTicketSerializer(many=True)
    options_checkbox = OptionTicketSerializer(many=True)
    artists = Artist_on_eventSerializer(many=True)

    class Meta:
        model = Event
        fields = [
            'uuid',
            'name',
            'slug',
            'short_description',
            'long_description',
            'event_facebook_url',
            'datetime',
            'products',
            'options_radio',
            'options_checkbox',
            'img_variations',
            'reservations',
            'complet',
            'artists',
        ]
        read_only_fields = ['uuid', 'reservations']
        depth = 1

    def validate(self, attrs):
        products = self.initial_data.getlist('products')

        if products:
            self.products_to_db = []
            for product in products:
                self.products_to_db.append(get_object_or_404(Product, uuid=product))
            return super().validate(attrs)
        else:
            raise serializers.ValidationError(_('products doit être un json valide'))

    def save(self, **kwargs):
        instance = super().save(**kwargs)
        instance.products.clear()
        for product in self.products_to_db:
            instance.products.add(product)
        return instance

    def to_representation(self, instance):
        article_payant = False
        reservation_free = True
        for product in instance.products.all():
            if product.categorie_article == Product.BILLET:
                reservation_free = False
            for price in product.prices.all():
                if price.prix > 0:
                    article_payant = True

        if article_payant:
            gift_product, created = Product.objects.get_or_create(categorie_article=Product.DON, name="Don")
            gift_price, created = Price.objects.get_or_create(product=gift_product, prix=1, name="Don")
            instance.products.add(gift_product)

        if reservation_free:
            free_reservation, created = Product.objects.get_or_create(categorie_article=Product.FREERES,
                                                                      name="Reservation")
            free_reservation_price, created = Price.objects.get_or_create(product=free_reservation, prix=0,
                                                                          name="Reservation")
            instance.products.add(free_reservation)

        representation = super().to_representation(instance)
        return representation



class ReservationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reservation
        fields = [
            'uuid',
            'datetime',
            'user_mail',
            'event',
            'status',
            'options',
            'tickets',
            'paiements',
        ]
        read_only_fields = [
            'uuid',
            'datetime',
            'status',
        ]
        # depth = 1


class OptionResaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reservation
        fields = [
            'options'
        ]
        read_only_fields = fields

class TicketSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ticket
        fields = [
            'uuid',
            'first_name',
            'last_name',
            # 'pricesold',
            'status',
            'seat',
            # 'event_name',
            # 'pdf_url',
        ]
        read_only_fields = fields

    # on rajoute les options directement.
    def to_representation(self, instance: Ticket):
        representation = super().to_representation(instance)
        representation['options'] = [option.name for option in instance.reservation.options.all()]
        return representation



class NewAdhesionValidator(serializers.Serializer):
    adhesion = serializers.PrimaryKeyRelatedField(
        queryset=Price.objects.filter(product__categorie_article=Product.ADHESION))
    email = serializers.EmailField()

    def validate_email(self, value):
        logger.info(f"NewAdhesionValidator validate email : {value}")
        user_paiement: TibilletUser = validate_email_and_return_user(value)
        self.user = user_paiement

    def validate(self, attrs):
        price_adhesion: Price = attrs.get('adhesion')
        user: TibilletUser = self.user

        metadata = {
            'tenant': f'{connection.tenant.uuid}',
            'pk_adhesion': f"{price_adhesion.pk}",
        }
        self.metadata = metadata

        ligne_article_adhesion = LigneArticle.objects.create(
            pricesold=get_or_create_price_sold(price_adhesion, None),
            qty=1,
        )

        new_paiement_stripe = creation_paiement_stripe(
            user=user,
            liste_ligne_article=[ligne_article_adhesion, ],
            metadata=metadata,
            reservation=None,
            source=Paiement_stripe.API_BILLETTERIE,
            absolute_domain=self.context.get('request').build_absolute_uri().partition('/api')[0],
        )

        if new_paiement_stripe.is_valid():
            paiement_stripe: Paiement_stripe = new_paiement_stripe.paiement_stripe_db
            paiement_stripe.lignearticle_set.all().update(status=LigneArticle.UNPAID)
            self.checkout_session = new_paiement_stripe.checkout_session

            return super().validate(attrs)

        raise serializers.ValidationError(_(f'new_paiement_stripe not valid'))

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        logger.info(f"{self.checkout_session.url}")
        representation['checkout_url'] = self.checkout_session.url
        return representation


class MembreValidator(serializers.Serializer):
    email = serializers.EmailField()

    first_name = serializers.CharField(max_length=200, required=False)
    last_name = serializers.CharField(max_length=200, required=False)

    phone = serializers.CharField(max_length=20, required=False)
    postal_code = serializers.IntegerField(required=False)
    birth_date = serializers.DateField(required=False)
    newsletter = serializers.BooleanField(required=False)

    adhesion = serializers.PrimaryKeyRelatedField(
        queryset=Price.objects.filter(product__categorie_article=Product.ADHESION))

    def validate_email(self, value):
        user_paiement: TibilletUser = validate_email_and_return_user(value)
        self.user = user_paiement

        self.fiche_membre, created = Membership.objects.get_or_create(
            user=user_paiement
        )

        if not self.fiche_membre.first_name:
            if not self.initial_data.get('first_name'):
                raise serializers.ValidationError(_(f'first_name est obligatoire'))
            self.fiche_membre.first_name = self.initial_data.get('first_name')
        if not self.fiche_membre.last_name:
            if not self.initial_data.get('last_name'):
                raise serializers.ValidationError(_(f'last_name est obligatoire'))
            self.fiche_membre.last_name = self.initial_data.get('last_name')
        if not self.fiche_membre.phone:
            if not self.initial_data.get('phone'):
                raise serializers.ValidationError(_(f'phone est obligatoire'))
            self.fiche_membre.phone = self.initial_data.get('phone')
        if not self.fiche_membre.postal_code:
            self.fiche_membre.postal_code = self.initial_data.get('postal_code')
        if not self.fiche_membre.birth_date:
            self.fiche_membre.birth_date = self.initial_data.get('birth_date')
        if not self.fiche_membre.newsletter:
            self.fiche_membre.newsletter = self.initial_data.get('newsletter')

        self.fiche_membre.save()

        return self.fiche_membre.user.email


def get_near_event_by_date():
    try:
        return Event.objects.get(datetime__date=datetime.datetime.now().date())
    except Event.MultipleObjectsReturned:
        return Event.objects.filter(datetime__date=datetime.datetime.now().date()).first()
    except Event.DoesNotExist:
        return Event.objects.filter(datetime__gte=datetime.datetime.now()).first()
    except:
        return None


def create_ticket(pricesold, customer, reservation):
    statut = Ticket.CREATED

    if pricesold.price.product.categorie_article == Product.FREERES:
        statut = Ticket.NOT_ACTIV

    ticket = Ticket.objects.create(
        status=statut,
        reservation=reservation,
        pricesold=pricesold,
        first_name=customer.get('first_name'),
        last_name=customer.get('last_name'),
    )

    return ticket


def get_or_create_price_sold(price: Price, event: Event):
    """
    Générateur des objets PriceSold pour envoi à Stripe.
    Price + Event = PriceSold

    On va chercher l'objet prix générique.
    On lie le prix générique a l'event
    pour générer la clé et afficher le bon nom sur stripe
    """

    productsold, created = ProductSold.objects.get_or_create(
        event=event,
        product=price.product
    )

    if created:
        productsold.get_id_product_stripe()
    logger.info(f"productsold {productsold.nickname()} created : {created} - {productsold.get_id_product_stripe()}")

    pricesold, created = PriceSold.objects.get_or_create(
        productsold=productsold,
        prix=price.prix,
        price=price,
    )

    if created:
        pricesold.get_id_price_stripe()
    logger.info(f"pricesold {pricesold.price.name} created : {created} - {pricesold.get_id_price_stripe()}")

    return pricesold


def line_article_recharge(carte, qty):
    product, created = Product.objects.get_or_create(
        name=f"Recharge Carte {carte.detail.origine.name} v{carte.detail.generation}",
        categorie_article=Product.RECHARGE_CASHLESS,
        img=carte.detail.img,
    )

    price, created = Price.objects.get_or_create(
        product=product,
        name=f"{qty}€",
        prix=int(qty),
    )

    # noinspection PyTypeChecker
    ligne_article_recharge = LigneArticle.objects.create(
        pricesold=get_or_create_price_sold(price, None),
        qty=1,
        carte=carte,
    )
    return ligne_article_recharge


class ChargeCashlessValidator(serializers.Serializer):
    uuid = serializers.UUIDField()
    qty = serializers.IntegerField()

    def validate_uuid(self, value):
        self.card = get_object_or_404(CarteCashless, uuid=f"{value}")
        return self.card.uuid

    def validate(self, attrs):
        request = self.context.get('request')
        qty = attrs.get('qty')
        if not request:
            raise serializers.ValidationError(_(f'No request'))
            # noinspection PyUnreachableCode
            if not request.user:
                raise serializers.ValidationError(_(f'No user. Auth first.'))
        user: TibilletUser = request.user

        metadata = {
            'tenant': f'{connection.tenant.uuid}',
            'recharge_carte_uuid': f"{self.card.uuid}",
            'recharge_carte_montant': f"{qty}",
        }
        self.metadata = metadata

        new_paiement_stripe = creation_paiement_stripe(
            user=user,
            liste_ligne_article=[line_article_recharge(self.card, qty)],
            metadata=metadata,
            reservation=None,
            source=Paiement_stripe.API_BILLETTERIE,
            absolute_domain=self.context.get('request').build_absolute_uri().partition('/api')[0],
        )

        if new_paiement_stripe.is_valid():
            paiement_stripe: Paiement_stripe = new_paiement_stripe.paiement_stripe_db
            paiement_stripe.lignearticle_set.all().update(status=LigneArticle.UNPAID)
            self.checkout_session = new_paiement_stripe.checkout_session

            return super().validate(attrs)

        raise serializers.ValidationError(_(f'new_paiement_stripe not valid'))

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        logger.info(f"{self.checkout_session.url}")
        representation['checkout_url'] = self.checkout_session.url
        return representation


class ReservationValidator(serializers.Serializer):
    email = serializers.EmailField()
    to_mail = serializers.BooleanField(default=True, required=False)
    event = serializers.PrimaryKeyRelatedField(queryset=Event.objects.all())
    options = serializers.PrimaryKeyRelatedField(queryset=OptionGenerale.objects.all(), many=True, allow_null=True)
    prices = serializers.JSONField(required=True)


    def validate_event(self, value):
        event: Event = value
        if event.complet():
            raise serializers.ValidationError(_(f'Jauge atteinte : Evenement complet.'))
        return value

    def validate_email(self, value):
        self.user_commande = validate_email_and_return_user(value)
        return self.user_commande.email

    def validate_prices(self, value):
        """
        On vérifie ici :
          que chaque article existe et a une quantité valide.
          qu'il existe au moins un billet pour la reservation.
          que chaque billet possède un nom/prenom

        On remplace le json reçu par une liste de dictionnaire
        qui comporte les objets de la db a la place des strings.
        """

        nbr_ticket = 0
        self.prices_list = []
        for entry in value:
            try:
                price = Price.objects.get(pk=entry['uuid'])
                price_object = {
                    'price': price,
                    'qty': float(entry['qty']),
                }

                if price.product.categorie_article in [Product.BILLET, Product.FREERES]:
                    nbr_ticket += entry['qty']

                    # les noms sont requis pour la billetterie
                    if not entry.get('customers'):
                        raise serializers.ValidationError(_(f'customers name not find in ticket'))
                    if len(entry.get('customers')) != entry['qty']:
                        raise serializers.ValidationError(_(f'customers number not equal to ticket qty'))

                    price_object['customers'] = entry.get('customers')

                self.prices_list.append(price_object)

            except Price.DoesNotExist as e:
                raise serializers.ValidationError(_(f'price non trouvé : {e}'))
            except ValueError as e:
                raise serializers.ValidationError(_(f'qty doit être un entier ou un flottant : {e}'))

        if nbr_ticket == 0:
            raise serializers.ValidationError(_(f'pas de billet dans la reservation'))

        return value

    def validate(self, attrs):
        event: Event = attrs.get('event')
        options = attrs.get('options')
        to_mail: bool = attrs.get('to_mail')

        # On check que les prices sont bien dans l'event original.
        for price_object in self.prices_list:
            if price_object['price'].product not in event.products.all():
                raise serializers.ValidationError(_(f'Article non disponible'))

        # On check que les options sont bien dans l'event original.
        if options:
            for option in options:
                option: OptionGenerale
                if option not in list(set(event.options_checkbox.all()) | set(event.options_radio.all())) :
                    raise serializers.ValidationError(_(f'Option {option.name} non disponible dans event'))


        # on construit l'object reservation.
        reservation = Reservation.objects.create(
            user_commande=self.user_commande,
            to_mail=to_mail,
            event=event,
        )

        if options:
            for option in options:
                reservation.options.add(option)

        self.reservation = reservation
        # Ici on construit :
        #   price_sold pour lier l'event à la vente
        #   ligne article pour envoi en paiement
        #   Ticket nominatif

        list_line_article_sold = []
        total_checkout = 0
        for price_object in self.prices_list:
            price_generique: Price = price_object['price']
            qty = price_object.get('qty')
            total_checkout += qty * price_generique.prix

            pricesold: PriceSold = get_or_create_price_sold(price_generique, event)

            # les lignes articles pour la vente
            line_article = LigneArticle.objects.create(
                pricesold=pricesold,
                qty=qty,
            )
            list_line_article_sold.append(line_article)

            # import ipdb; ipdb.set_trace()
            # Les Tickets si article est un billet
            if price_generique.product.categorie_article in [Product.BILLET, Product.FREERES]:
                for customer in price_object.get('customers'):
                    create_ticket(pricesold, customer, reservation)

        print(f"total_checkout : {total_checkout}")
        self.checkout_session = None
        if total_checkout > 0:

            metadata = {
                'reservation': f'{reservation.uuid}',
                'tenant': f'{connection.tenant.uuid}',
            }

            new_paiement_stripe = creation_paiement_stripe(
                user=self.user_commande,
                liste_ligne_article=list_line_article_sold,
                metadata=metadata,
                source=Paiement_stripe.API_BILLETTERIE,
                reservation=reservation,
                absolute_domain=self.context.get('request').build_absolute_uri().partition('/api')[0],
            )

            if new_paiement_stripe.is_valid():
                paiement_stripe: Paiement_stripe = new_paiement_stripe.paiement_stripe_db
                paiement_stripe.lignearticle_set.all().update(status=LigneArticle.UNPAID)

                reservation.tickets.all().update(status=Ticket.NOT_ACTIV)

                reservation.paiement = paiement_stripe
                reservation.status = Reservation.UNPAID
                reservation.save()

                print(new_paiement_stripe.checkout_session.stripe_id)
                # return new_paiement_stripe.redirect_to_stripe()
                self.checkout_session = new_paiement_stripe.checkout_session
                self.paiement_stripe_uuid = paiement_stripe.uuid

                return super().validate(attrs)
            else:
                raise serializers.ValidationError(_(f'checkout strip not valid'))

        # La validation de la reservation doit se fait uniquement si l'user possède un mail vérifié
        elif total_checkout == 0:
            # On passe les reservations gratuites en payées automatiquement :
            for line_price in list_line_article_sold:
                line_price: LigneArticle
                if line_price.pricesold.productsold.product.categorie_article == Product.FREERES:
                    if line_price.status != LigneArticle.VALID:
                        line_price.status = LigneArticle.FREERES
                        line_price.save()

            if reservation:
                # Si l'utilisateur est actif, il a vérifié son email.
                if self.user_commande.is_active :
                    reservation.status = Reservation.FREERES_USERACTIV
                # Sinon on attend que l'user ai vérifié son email.
                # La fonctione presave du fichier BaseBillet.signals
                # mettra a jour le statut de la réservation et enverra le billet dés validation de l'email
                else :
                    reservation.status = Reservation.FREERES
                reservation.save()



            return super().validate(attrs)

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        if self.reservation:
            representation['reservation'] = ReservationSerializer(self.reservation, read_only=True).data
        if self.checkout_session:
            logger.info(f"{self.checkout_session.url}")
            representation['checkout_url'] = self.checkout_session.url
            representation['paiement_stripe_uuid'] = self.paiement_stripe_uuid
        # import ipdb;ipdb.set_trace()
        return representation
