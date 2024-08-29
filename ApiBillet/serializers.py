import datetime
import logging
import uuid
from decimal import Decimal

import requests
import stripe
from PIL import Image
from django.db import connection
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from django_tenants.utils import tenant_context
from rest_framework import serializers
from rest_framework.generics import get_object_or_404

from AuthBillet.models import TibilletUser
from AuthBillet.utils import get_or_create_user
from BaseBillet.models import Event, Price, Product, Reservation, Configuration, LigneArticle, Ticket, Paiement_stripe, \
    PriceSold, ProductSold, Artist_on_event, OptionGenerale, Membership, Tag, Weekday
from Customers.models import Client
from MetaBillet.models import WaitingConfiguration
from PaiementStripe.views import CreationPaiementStripe
from QrcodeCashless.models import CarteCashless, Detail
from root_billet.models import RootConfiguration

logger = logging.getLogger(__name__)


def get_img_from_url(url):
    try:
        res = requests.get(url, stream=True)
        file_name = url.split('/')[-1]
        file_img = Image.open(res.raw)
    except Exception as e:
        raise serializers.ValidationError(_(f"{url} doit contenir une url d'image valide : {e}"))
    return file_name, file_img


class OptionsSerializer(serializers.ModelSerializer):
    class Meta:
        model = OptionGenerale
        fields = [
            'uuid',
            'name',
            'description',
            'poids',
        ]
        read_only_fields = ('uuid', 'poids')


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = [
            'uuid',
            'name',
            'color',
        ]
        read_only_fields = ('uuid',)


class WeekdaySerializer(serializers.ModelSerializer):
    class Meta:
        model = Weekday
        fields = [
            'day',
        ]


class ProductCreateSerializer(serializers.ModelSerializer):
    option_generale_radio = serializers.ListField(required=False)
    option_generale_checkbox = serializers.ListField(required=False)
    tag = TagSerializer(many=True, required=False)

    class Meta:
        model = Product
        fields = [
            "uuid",
            "name",
            'short_description',
            'long_description',
            'terms_and_conditions_document',
            "publish",
            "img",
            "categorie_article",
            "send_to_cashless",
            "prices",
            "tag",
            "option_generale_radio",
            "option_generale_checkbox",
            "legal_link",
            "nominative",
        ]
        depth = 1
        read_only_fields = [
            'uuid',
            'prices',
        ]

    def validate_option_generale_radio(self, value):
        self.option_generale_radio = []
        for uuid in value:
            try:
                option = OptionGenerale.objects.get(pk=uuid)
                self.option_generale_radio.append(option)
            except OptionGenerale.DoesNotExist as e:
                raise serializers.ValidationError(_(f'{uuid} Option non trouvé'))
        return self.option_generale_radio

    def validate_option_generale_checkbox(self, value):
        self.option_generale_checkbox = []
        for uuid in value:
            try:
                option = OptionGenerale.objects.get(pk=uuid)
                self.option_generale_checkbox.append(option)
            except OptionGenerale.DoesNotExist as e:
                raise serializers.ValidationError(_(f'{uuid} Option non trouvé'))
        return self.option_generale_checkbox

    def validate(self, attrs):
        logger.info(f"validate : {attrs}")

        # On cherche la source de l'image principale :
        img_url = self.initial_data.get('img_url')
        if not attrs.get('img') and not img_url:
            raise serializers.ValidationError(
                _(f'img doit contenir un fichier, ou img_url doit contenir une url valide'))
        if not attrs.get('img') and img_url:
            self.img_name, self.img_img = get_img_from_url(img_url)

        if attrs.get('send_to_cashless') and attrs.get('categorie_article') == Product.ADHESION:
            adhesion_to_cashless = Product.objects.filter(
                categorie_article=Product.ADHESION,
                send_to_cashless=True
            )
            if len(adhesion_to_cashless) > 0:
                raise serializers.ValidationError(
                    _(f"Un article d'adhésion vers le cashless existe déja."))

        return super().validate(attrs)


class ProductSerializer(serializers.ModelSerializer):
    option_generale_radio = OptionsSerializer(many=True)
    option_generale_checkbox = OptionsSerializer(many=True)
    tag = TagSerializer(many=True, required=False)

    class Meta:
        model = Product
        fields = [
            "uuid",
            "name",
            'short_description',
            'long_description',
            'terms_and_conditions_document',
            "publish",
            "img",
            "categorie_article",
            "send_to_cashless",
            "prices",
            "tag",
            "option_generale_radio",
            "option_generale_checkbox",
            "legal_link",
            "nominative",
        ]
        depth = 1
        read_only_fields = [
            'uuid',
            'prices',
        ]


class PriceSerializer(serializers.ModelSerializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    adhesion_obligatoire = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.filter(categorie_article=Product.ADHESION),
        required=False
    )

    class Meta:
        model = Price
        fields = [
            'uuid',
            'product',
            'name',
            'short_description',
            'long_description',
            'prix',
            'vat',
            'stock',
            'max_per_user',
            'adhesion_obligatoire',
            'subscription_type',
            'recurring_payment'
        ]

        read_only_fields = [
            'uuid',
        ]
        depth = 1

    def validate(self, attrs):
        product = attrs.get('product')
        if product.categorie_article == Product.ADHESION:
            sub_type_novalid = [None, Price.NA]
            if attrs.get('subscription_type') in sub_type_novalid:
                raise serializers.ValidationError(
                    _(f'error fields subscription_type - Une adhésion doit avoir une durée de validité.'))
        return super().validate(attrs)


# Utilisé par /here
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
            "legal_documents",
            "twitter",
            "facebook",
            "instagram",
            # "activer_billetterie",
            # "adhesion_obligatoire",
            # "button_adhesion",
            "map_img",
            "carte_restaurant",
            "img_variations",
            "logo_variations",
            "domain",
            "categorie",
        ]
        read_only_fields = fields

    # def to_representation(self, instance):
    #     representation = super().to_representation(instance)
    #     representation['domain'] = connection.tenant.get_primary_domain().domain
    #     representation['categorie'] = connection.tenant.categorie
    #     return representation


# class WaitingConfigSerializer(serializers.Serializer):
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


def create_account_link_for_onboard(id_acc_connect=None):
    rootConf = RootConfiguration.get_solo()
    stripe.api_key = rootConf.get_stripe_api()

    meta = Client.objects.filter(categorie=Client.META)[0]
    meta_url = meta.get_primary_domain().domain

    if not id_acc_connect:
        acc_connect = stripe.Account.create(
            type="standard",
            country="FR",
        )
        id_acc_connect = acc_connect.get('id')

    account_link = stripe.AccountLink.create(
        account=id_acc_connect,
        refresh_url=f"https://{meta_url}/onboard_stripe_return/{id_acc_connect}",
        return_url=f"https://{meta_url}/onboard_stripe_return/{id_acc_connect}",
        type="account_onboarding",
    )

    url_onboard = account_link.get('url')
    return url_onboard

class CheckMailSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        self.user = get_or_create_user(value, send_mail=False)
        return value

"""
Ex Methode
"""
class WaitingConfigSerializer(serializers.ModelSerializer):
    stripe = serializers.BooleanField()

    class Meta:
        model = WaitingConfiguration
        fields = [
            "organisation",
            "short_description",
            "long_description",
            # "stripe_connect_account",
            "img",
            "logo",
            "email",
            "stripe",
        ]

    def create(self, validated_data):
        stripe = validated_data.pop('stripe', None)
        waiting_config = WaitingConfiguration.objects.create(**validated_data)

        # Pour le cas ou les images sont des url, on a créé nous même les binaires.
        if getattr(self, 'img_img', None):
            waiting_config.img.save(self.img_name, self.img_img.fp)
        if getattr(self, 'logo_img', None):
            waiting_config.logo.save(self.logo_name, self.logo_img.fp)

        return waiting_config

    def validate_stripe(self, value):
        if value:
            self.stripe_onboard = create_account_link_for_onboard()
        return value

    def validate_organisation(self, value):
        # Le slug est-il disponible ?
        slug = slugify(value)
        if Client.objects.filter(schema_name=slug).exists():
            logger.warning(f"{slug} exist : Conflict")
            raise serializers.ValidationError({f"{slug} existe déja : Conflit de nom"})

        if WaitingConfiguration.objects.filter(slug=slug).exists():
            logger.warning(f"{slug} exist : Conflict")
            raise serializers.ValidationError({f"{slug} existe déja : Conflit de nom"})

        return value

    def validate_email(self, value):
        self.user = get_or_create_user(value, send_mail=True)
        return value

    def validate_stripe_connect_account(self, value):
        rootConf = RootConfiguration.get_solo()
        stripe.api_key = rootConf.get_stripe_api()

        try:
            info_stripe = stripe.Account.retrieve(value)
            details_submitted = info_stripe.details_submitted

            if not details_submitted:

                meta = Client.objects.filter(categorie=Client.META)[0]
                meta_url = meta.get_primary_domain().domain

                try:
                    account_link = stripe.AccountLink.create(
                        account=value,
                        refresh_url=f"https://{meta_url}/api/onboard_stripe_return/{value}",
                        return_url=f"https://{meta_url}/api/onboard_stripe_return/{value}",
                        type="account_onboarding",
                    )

                    url_onboard = account_link.get('url')
                    raise serializers.ValidationError(
                        _(f'{url_onboard}'))
                except:
                    raise serializers.ValidationError(
                        _(f'stripe account valid but no detail submitted'))

            # un seul tenant par compte stripe, sauf en test
            if not rootConf.stripe_mode_test:
                for tenant in Client.objects.all().exclude(categorie__in=[Client.META, Client.ROOT]):
                    with tenant_context(tenant):
                        config = Configuration.get_solo()
                        if config.stripe_connect_account == value:
                            raise serializers.ValidationError(
                                _(f'Stripe account already connected to one Tenant. Please send mail to contact@tibillet.re to upgrade your plan.'))

            if not info_stripe.email:
                raise serializers.ValidationError(
                    _(f'Please set email in your stripe account'))
            if not info_stripe.business_profile.support_phone:
                raise serializers.ValidationError(
                    _(f'Please set phone number in your stripe account'))
            if not info_stripe.business_profile.url:
                raise serializers.ValidationError(
                    _(f'Please set website in your stripe account'))

            self.info_stripe = info_stripe

            return value

        except Exception as e:
            raise serializers.ValidationError(
                _(f'stripe account not valid : {e}'))

    def validate(self, attrs):
        logger.info(f"validate : {attrs}")

        # if not attrs.get('stripe_connect_account') or not getattr(self, 'info_stripe', None):
        #     raise serializers.ValidationError(
        #         _(f'stripe account not send nor valid'))


        # On cherche la source de l'image principale :
        img_url = self.initial_data.get('img_url')
        if not attrs.get('img') and img_url:
            self.img_name, self.img_img = get_img_from_url(img_url)
        if not attrs.get('img') and not img_url:
            raise serializers.ValidationError(
                _(f'img doit contenir un fichier, ou img_url doit contenir une url valide'))


        # On cherche la source de l'image du logo :
        logo_url = self.initial_data.get('logo_url')
        if not attrs.get('logo') and logo_url:
            self.logo_name, self.logo_img = get_img_from_url(logo_url)
        if not attrs.get('logo') and not logo_url:
            raise serializers.ValidationError(
                _(f'img doit contenir un fichier, ou logo_url doit contenir une url valide'))

        return super().validate(attrs)


class ArtistEventCreateSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    datetime = serializers.DateTimeField()

    def validate_uuid(self, value):
        self.artiste_event_db = getattr(self, "artiste_event_db", {})
        try:
            tenant = Client.objects.get(pk=value, categorie=Client.ARTISTE)
            self.artiste_event_db['tenant'] = tenant
            with tenant_context(tenant):
                self.artiste_event_db['config'] = Configuration.get_solo()
        except Client.DoesNotExist as e:
            raise serializers.ValidationError(_(f'{value} Artiste non trouvé'))
        return value

    def validate_datetime(self, value):
        self.artiste_event_db = getattr(self, "artiste_event_db", {})
        self.artiste_event_db['datetime'] = value
        return value

    def validate(self, attrs):
        # logger.info(f"ArtistEventCreateSerializer : {self.artiste_event_db}")
        return self.artiste_event_db


class Artist_on_eventSerializer(serializers.ModelSerializer):
    configuration = ConfigurationSerializer()

    class Meta:
        model = Artist_on_event
        fields = [
            'datetime',
            'configuration',
        ]


class EventCreateSerializer(serializers.Serializer):
    name = serializers.CharField(required=False, max_length=200)
    datetime = serializers.DateTimeField()
    artists = ArtistEventCreateSerializer(many=True, required=False)
    products = serializers.ListField(required=False)
    options_radio = serializers.ListField(required=False)
    options_checkbox = serializers.ListField(required=False)
    tags = serializers.ListField(required=False)
    long_description = serializers.CharField(required=False)
    short_description = serializers.CharField(required=False, max_length=100)
    img_url = serializers.URLField(required=False)
    # cashless = serializers.BooleanField(required=False)
    minimum_cashless_required = serializers.IntegerField(required=False)
    max_per_user = serializers.IntegerField(required=False)

    def validate_artists(self, value):
        # logger.info(f"validate_artists : {value}")
        return value

    def validate_products(self, value):
        self.products_db = []
        for uuid in value:
            try:
                product = Product.objects.get(pk=uuid)
                self.products_db.append(product)
            except Product.DoesNotExist as e:
                raise serializers.ValidationError(_(f'{uuid} Produit non trouvé'))
        return self.products_db

    def validate_tags(self, value):
        self.tags_db = []
        for name in value:
            try:
                tag, created = Tag.objects.get_or_create(name=name)
                self.tags_db.append(tag)
            except Product.DoesNotExist as e:
                raise serializers.ValidationError(_(f'Erreur création du Tag'))
        return self.tags_db

    def validate_options_radio(self, value):
        self.options_radio = []
        for uuid in value:
            try:
                option = OptionGenerale.objects.get(pk=uuid)
                self.options_radio.append(option)
            except OptionGenerale.DoesNotExist as e:
                raise serializers.ValidationError(_(f'{uuid} Option non trouvé'))
        return self.options_radio

    def validate_options_checkbox(self, value):
        self.options_checkbox = []
        for uuid in value:
            try:
                option = OptionGenerale.objects.get(pk=uuid)
                self.options_checkbox.append(option)
            except OptionGenerale.DoesNotExist as e:
                raise serializers.ValidationError(_(f'{uuid} Option non trouvé'))
        return self.options_checkbox

    def validate_minimum_cashless_required(self, value):
        if value:
            try:
                return int(value)
            except Exception as e:
                raise serializers.ValidationError(_(f'{value} minimum_cashless non valide'))

    def validate_img_url(self, value):
        if value:
            self.file_name, self.file_img = get_img_from_url(value)
        return value

    def validate(self, attrs):
        # import ipdb; ipdb.set_trace()
        name = None
        if attrs.get('artists'):
            name = (" & ").join([artist.get('config').organisation for artist in attrs.get('artists')])

        # Name prend le dessus sur le join artist
        if attrs.get('name'):
            name = attrs.get('name')

        if not name:
            raise serializers.ValidationError(f"if not 'artist', 'name' is required")

        event_data = {
            "name": name,
            "datetime": attrs.get('datetime'),
            "categorie": Event.CONCERT,
            "long_description": attrs.get('long_description'),
            "short_description": attrs.get('short_description'),
            # "cashless" : attrs.get('cashless', False),
            "minimum_cashless_required": attrs.get('minimum_cashless_required', 0),
        }

        event, created = Event.objects.get_or_create(**event_data)

        if attrs.get('img_url'):
            event.img.save(self.file_name, self.file_img.fp)

        # import ipdb; ipdb.set_trace()

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

        event.tag.clear()
        if attrs.get('tags'):
            for tag in self.tags_db:
                event.tag.add(tag)

        if attrs.get('artists'):
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
    options_radio = OptionsSerializer(many=True)
    options_checkbox = OptionsSerializer(many=True)
    artists = Artist_on_eventSerializer(many=True)
    tag = TagSerializer(many=True)
    recurrent = WeekdaySerializer(many=True)

    class Meta:
        model = Event
        fields = [
            'uuid',
            'name',
            'slug',
            'short_description',
            'long_description',
            'categorie',
            'tag',
            'is_external',
            'url_external',
            'datetime',
            'products',
            'options_radio',
            'options_checkbox',
            'img_variations',
            'reservations',
            'complet',
            'artists',
            'minimum_cashless_required',
            'max_per_user',
            'reservation_solo',
            'recurrent',
            'booking',
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
            gift_product, created = Product.objects.get_or_create(categorie_article=Product.DON,
                                                                  name="Don pour la coopérative")
            gift_price, created = Price.objects.get_or_create(product=gift_product, prix=1, name="Coopérative TiBillet")
            instance.products.add(gift_product)


        # if instance.recharge_cashless :
        #     recharge_suspendue, created = Product.objects.get_or_create(categorie_article=Product.RECHARGE_SUSPENDUE, name="Recharge cashless")
        #     recharge_suspendue_price, created = Price.objects.get_or_create(product=recharge_suspendue, prix=1, name="charge")
        #     instance.products.add(recharge_suspendue)

        # if reservation_free:
        #     free_reservation, created = Product.objects.get_or_create(categorie_article=Product.FREERES,
        #                                                               name="Reservation")
        #     free_reservation_price, created = Price.objects.get_or_create(product=free_reservation, prix=0,
        #                                                                   name="gratuite")
        #     instance.products.add(free_reservation)

        representation = super().to_representation(instance)

        representation['next_datetime'] = [date_time.isoformat() for date_time in instance.next_datetime()]

        representation['url'] = f"https://{connection.tenant.get_primary_domain().domain}/event/{instance.slug}/"
        representation['place'] = Configuration.get_solo().organisation

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
    gift = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)

    def validate_adhesion(self, value: Price):

        # Si c'est une adhésion à envoyer au serveur cashless, on vérifie qu'il soit up
        if value.product.send_to_cashless:
            config = Configuration.get_solo()
            if not config.check_serveur_cashless():
                raise serializers.ValidationError(
                    _(f"Le serveur cashless n'est pas disponible ( check serveur false ). Merci d'essayer ultérieurement"))

        return value

    def validate_email(self, value):
        # logger.info(f"NewAdhesionValidator validate email : {value}")
        user_paiement: TibilletUser = get_or_create_user(value, send_mail=False)
        self.user = user_paiement
        return user_paiement.email

    def validate(self, attrs):
        price_adhesion: Price = attrs.get('adhesion')

        user: TibilletUser = self.user

        metadata = {
            'tenant': f'{connection.tenant.uuid}',
            'pk_adhesion': f"{price_adhesion.pk}",
        }
        self.metadata = metadata

        ligne_article_adhesion = LigneArticle.objects.create(
            pricesold=get_or_create_price_sold(price_adhesion, None, gift=attrs.get('gift')),
            qty=1,
        )

        new_paiement_stripe = CreationPaiementStripe(
            user=user,
            liste_ligne_article=[ligne_article_adhesion, ],
            metadata=metadata,
            reservation=None,
            source=Paiement_stripe.API_BILLETTERIE,
            absolute_domain=self.context.get('request').build_absolute_uri().partition('/api')[0],
        )

        if new_paiement_stripe.is_valid():
            paiement_stripe: Paiement_stripe = new_paiement_stripe.paiement_stripe_db
            paiement_stripe.lignearticles.all().update(status=LigneArticle.UNPAID)
            self.checkout_session = new_paiement_stripe.checkout_session

            return super().validate(attrs)

        raise serializers.ValidationError(_(f'new_paiement_stripe not valid'))

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        logger.info(f"{self.checkout_session.url}")
        representation['checkout_url'] = self.checkout_session.url
        return representation


class MembreValidator(serializers.Serializer):
    adhesion = serializers.PrimaryKeyRelatedField(
        queryset=Price.objects.filter(product__categorie_article=Product.ADHESION)
    )
    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=200, required=False)
    last_name = serializers.CharField(max_length=200, required=False)

    options = serializers.PrimaryKeyRelatedField(queryset=OptionGenerale.objects.all(),
                                                 many=True, allow_null=True, required=False)

    phone = serializers.CharField(max_length=20, required=False)
    postal_code = serializers.IntegerField(required=False)
    birth_date = serializers.DateField(required=False)

    newsletter = serializers.BooleanField(required=False)

    def validate_adhesion(self, value):
        self.price = value
        return value

    def validate_email(self, value):
        if not getattr(self, 'price', None):
            raise serializers.ValidationError(
                _(f"Pas de prix d'adhésion"))

        user_paiement: TibilletUser = get_or_create_user(value)
        self.user = user_paiement

        self.fiche_membre, created = Membership.objects.get_or_create(
            user=user_paiement,
            price=self.price,
        )

        # Si une adhésion existe déja
        if not created:
            # Si elle est encore valide
            if self.fiche_membre.is_valid():
                raise serializers.ValidationError(
                    _(f"Un abonnement sur ce mail existe déjà et est valide jusque : {self.fiche_membre.deadline()}"))

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

    def validate_options(self, value):
        self.options = value
        for option in value:
            product = self.price.product
            option: OptionGenerale
            if option not in list(
                    set(product.option_generale_radio.all()) | set(product.option_generale_checkbox.all())):
                raise serializers.ValidationError(_(f'Option {option.name} non disponible dans product'))

        for option in self.options:
            self.fiche_membre.option_generale.add(option)

        return value


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


def get_or_create_price_sold(price: Price, event: Event, gift=None):
    """
    Générateur des objets PriceSold pour envoi à Stripe.
    Price + Event = PriceSold

    On va chercher l'objet prix générique.
    On lie le prix générique à l'event
    pour générer la clé et afficher le bon nom sur stripe
    """

    productsold, created = ProductSold.objects.get_or_create(
        event=event,
        product=price.product
    )

    if created:
        productsold.get_id_product_stripe()
    logger.info(f"productsold {productsold.nickname()} created : {created}")

    prix = price.prix
    if gift:
        prix = price.prix + gift

    pricesold, created = PriceSold.objects.get_or_create(
        productsold=productsold,
        prix=prix,
        price=price,
        gift=gift
    )

    if created:
        pricesold.get_id_price_stripe()
    logger.info(f"pricesold {pricesold.price.name} created : {created}")

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


class DetailCashlessCardsValidator(serializers.ModelSerializer):
    class Meta:
        model = Detail
        fields = [
            "base_url",
            "origine",
            "generation",
        ]


class DetailCashlessCardsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Detail
        fields = [
            "base_url",
            "origine",
            "generation",
            "uuid",
        ]


class CashlessCardsValidator(serializers.Serializer):
    # detail_uuid = serializers.UUIDField()
    generation = serializers.IntegerField(required=True)
    url = serializers.URLField(required=True)
    detail = serializers.UUIDField(required=False)
    tag_id = serializers.CharField(required=True)
    number = serializers.CharField(required=True)

    def validate_generation(self, value):
        self.generation = int(value)
        return value

    def validate_url(self, value):

        part = value.partition('/qr/')
        base_url = f"{part[0]}{part[1]}"
        uuid_qrcode = part[2]

        # On teste si l'uuid est valide
        assert uuid.UUID(uuid_qrcode, version=4)

        # On teste que la db Detail existe bien en amont
        self.detail_from_db = get_object_or_404(Detail, base_url=base_url, generation=self.generation)

        return value

    def validate_detail(self, value):
        detailDb = get_object_or_404(Detail, uuid=value)

        if self.detail_from_db != detailDb:
            raise serializers.ValidationError(_(f'erreur url carte != detail uuid'))

        return value

    def validate(self, attrs):
        if not attrs.get('detail') and self.detail_from_db:
            attrs['detail'] = self.detail_from_db.uuid
        validation = super().validate(attrs)
        return validation



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

        new_paiement_stripe = CreationPaiementStripe(
            user=user,
            liste_ligne_article=[line_article_recharge(self.card, qty)],
            metadata=metadata,
            reservation=None,
            source=Paiement_stripe.API_BILLETTERIE,
            absolute_domain=self.context.get('request').build_absolute_uri().partition('/api')[0],
        )

        if new_paiement_stripe.is_valid():
            paiement_stripe: Paiement_stripe = new_paiement_stripe.paiement_stripe_db
            paiement_stripe.lignearticles.all().update(status=LigneArticle.UNPAID)
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
    datetime = serializers.DateTimeField(required=False)

    def validate_event(self, value):
        event: Event = value
        if event.complet():
            raise serializers.ValidationError(_(f'Jauge atteinte : Evenement complet.'))
        return value

    def validate_email(self, value):
        # On vérifie que l'utilisateur connecté et l'email correspondent bien.
        request = self.context.get('request')
        self.user_commande = get_or_create_user(value)

        if request.user.is_authenticated:
            if request.user.email != request.user:
                raise serializers.ValidationError(_(f"L'email ne correspond pas à l'utilisateur connecté."))

        return self.user_commande.email

    def validate_prices(self, value):
        """
        On vérifie ici :
          que chaque article existe et a une quantité valide.
          Qu'il existe au moins un billet pour la reservation.
          Que chaque billet possède un nom/prenom si le billet doit être nominatif

        On remplace le json reçu par une liste de dictionnaire
        qui comporte les objets de la db à la place des strings.
        """

        self.nbr_ticket = 0
        self.prices_list = []
        for entry in value:
            logger.info(f"price entry : {entry}")
            try:
                price = Price.objects.get(pk=entry['uuid'])
                product = price.product
                price_object = {
                    'price': price,
                    'qty': float(entry['qty']),
                }

                if entry['qty'] > price.max_per_user:
                    raise serializers.ValidationError(
                        _(f'Quantitée de réservations suppérieure au maximum autorisé pour ce prix'))

                if product.categorie_article in [Product.BILLET, Product.FREERES]:
                    self.nbr_ticket += entry['qty']

                    # les noms sont requis pour la billetterie.
                    if product.nominative:
                        if not entry.get('customers'):
                            raise serializers.ValidationError(_(f'customers not find in ticket'))
                        if len(entry.get('customers')) != entry['qty']:
                            raise serializers.ValidationError(_(f'customers number not equal to ticket qty'))
                        for customer in entry.get('customers'):
                            if not customer.get('first_name') or not customer.get('last_name'):
                                raise serializers.ValidationError(_(f'first_name and last_name are required'))

                        price_object['customers'] = entry.get('customers')

                self.prices_list.append(price_object)

            except Price.DoesNotExist as e:
                raise serializers.ValidationError(_(f'price non trouvé : {e}'))
            except ValueError as e:
                raise serializers.ValidationError(_(f'qty doit être un entier ou un flottant : {e}'))

        if self.nbr_ticket == 0:
            raise serializers.ValidationError(_(f'pas de billet dans la reservation'))

        # import ipdb; ipdb.set_trace()

        return value

    # def validate_chargeCashless(self, value):
    #     if value > 0 :
    #         recharge_suspendue, created = Product.objects.get_or_create(categorie_article=Product.RECHARGE_SUSPENDUE,
    #                                                                     name="Recharge cashless")
    #         recharge_suspendue_price = Price.objects.get(product=recharge_suspendue, prix=1,
    #                                                                         name="On ticket")
    #         price_object = {
    #             'price': recharge_suspendue_price,
    #             'qty': float(value),
    #         }
    #         self.prices_list.append(price_object)
    #
    #     return value

    def validate(self, attrs):
        event: Event = attrs.get('event')
        options = attrs.get('options')
        to_mail: bool = attrs.get('to_mail')

        resas = event.reservations()

        if self.nbr_ticket > event.max_per_user:
            raise serializers.ValidationError(_(f'Quantitée de réservations suppérieure au maximum autorisé'))

        if resas + self.nbr_ticket > event.jauge_max:
            raise serializers.ValidationError(_(f'Il ne reste que {resas} places disponibles'))

        # On check que les prices sont bien dans l'event original.
        product_list = [product for product in event.products.all()]
        for product in product_list:
            for price in product.prices.all():
                if price.adhesion_obligatoire:
                    product_list.append(price.adhesion_obligatoire)

        for price_object in self.prices_list:
            if price_object['price'].product not in product_list:
                import ipdb;
                ipdb.set_trace()
                logger.error(f'Article non présent dans event : {price_object["price"].product.name}')
                raise serializers.ValidationError(_(f'Article non disponible'))

        # On check que les options sont bien dans l'event original.
        if options:
            for option in options:
                option: OptionGenerale
                if option not in list(set(event.options_checkbox.all()) | set(event.options_radio.all())):
                    raise serializers.ValidationError(_(f'Option {option.name} non disponible dans event'))

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
        # Ici, on construit :
        #   price_sold pour lier l'event à la vente
        #   ligne article pour envoi en paiement
        #   Ticket nominatif

        list_line_article_sold = []
        total_checkout = 0
        for price_object in self.prices_list:
            price_generique: Price = price_object['price']
            product: Product = price_generique.product
            qty = price_object.get('qty')
            total_checkout += Decimal(qty) * price_generique.prix

            pricesold: PriceSold = get_or_create_price_sold(price_generique, event)

            # les lignes articles pour la vente
            line_article = LigneArticle.objects.create(
                pricesold=pricesold,
                qty=qty,
            )
            list_line_article_sold.append(line_article)

            # Création de tickets si article est un billet
            if product.categorie_article in [Product.BILLET, Product.FREERES]:
                if product.nominative:
                    for customer in price_object.get('customers'):
                        create_ticket(pricesold, customer, reservation)
                else:
                    for i in range(int(qty)):
                        create_ticket(
                            pricesold,
                            {'first_name': f'{self.user_commande.email}', 'last_name': f'Billet non nominatif {i}'},
                            reservation)

        print(f"total_checkout : {total_checkout}")
        self.checkout_session = None
        if total_checkout > 0:

            metadata = {
                'reservation': f'{reservation.uuid}',
                'tenant': f'{connection.tenant.uuid}',
            }

            new_paiement_stripe = CreationPaiementStripe(
                user=self.user_commande,
                liste_ligne_article=list_line_article_sold,
                metadata=metadata,
                source=Paiement_stripe.API_BILLETTERIE,
                reservation=reservation,
                absolute_domain=self.context.get('request').build_absolute_uri().partition('/api')[0],
            )

            if new_paiement_stripe.is_valid():
                paiement_stripe: Paiement_stripe = new_paiement_stripe.paiement_stripe_db
                paiement_stripe.lignearticles.all().update(status=LigneArticle.UNPAID)

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
                if self.user_commande.is_active:
                    reservation.status = Reservation.FREERES_USERACTIV
                # Sinon, on attend que l'user ait vérifié son email.
                # La fonctione presave du fichier BaseBillet.signals
                # mettra à jour le statut de la réservation et enverra le billet dés validation de l'email
                else:
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


# class PaiementStripeSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = Paiement_stripe
#         fields = [
#             'price',
#         ]

class PriceSoldSerializer(serializers.ModelSerializer):
    price = PriceSerializer(many=False)
    class Meta:
        model = PriceSold
        fields = [
            'price',
            'prix',
        ]

class LigneArticleSerializer(serializers.ModelSerializer):
    pricesold = PriceSoldSerializer(many=False)
    class Meta:
        model = LigneArticle
        fields = [
            'uuid',
            'pricesold',
            'qty',
            'vat',
            'user_uuid_wallet'
        ]
