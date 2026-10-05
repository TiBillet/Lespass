import datetime
import logging
import json
from decimal import Decimal

import requests
import stripe
from PIL import Image
from django.db.transaction import atomic
from django.utils.translation import gettext_lazy as _
from django_tenants.utils import tenant_context
from rest_framework import serializers
from rest_framework.generics import get_object_or_404
from BaseBillet.models import Event, Price, Product, Reservation, Configuration, LigneArticle, Ticket, \
    PriceSold, ProductSold, Artist_on_event, OptionGenerale, Tag, Membership, PostalAddress, PromotionalCode, \
    MembershipProduct, PaymentMethod
from Customers.models import Client
from fedow_connect.utils import dround

logger = logging.getLogger(__name__)


def dec_to_int(value):
    if value is None:
        return 0
    return int(value * 100)


def get_img_from_url(url):
    try:
        res = requests.get(url, stream=True)
        file_name = url.split('/')[-1]
        file_img = Image.open(res.raw)
    except Exception as e:
        raise serializers.ValidationError(_(f"{url} must be a valid image URL: {e}"))
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


# class WeekdaySerializer(serializers.ModelSerializer):
#     class Meta:
#         model = Weekday
#         fields = [
#             'day',
#         ]


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
            # "send_to_cashless",
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

    def to_representation(self, instance):
        # depth = 1 renvoie tous les tarifs du produit.
        # On retire les tarifs archivés (« supprimés ») : ils ne sont plus jamais affichés.
        # / depth = 1 returns every price: remove the archived ("deleted") ones.
        representation = super().to_representation(instance)
        tarifs_non_archives = []
        for tarif in representation.get("prices", []):
            if not tarif.get("archived"):
                tarifs_non_archives.append(tarif)
        representation["prices"] = tarifs_non_archives
        return representation

    def validate_option_generale_radio(self, value):
        self.option_generale_radio = []
        for uuid in value:
            try:
                option = OptionGenerale.objects.get(pk=uuid)
                self.option_generale_radio.append(option)
            except OptionGenerale.DoesNotExist as e:
                raise serializers.ValidationError(_(f'{uuid} Option not found'))
        return self.option_generale_radio

    def validate_option_generale_checkbox(self, value):
        self.option_generale_checkbox = []
        for uuid in value:
            try:
                option = OptionGenerale.objects.get(pk=uuid)
                self.option_generale_checkbox.append(option)
            except OptionGenerale.DoesNotExist as e:
                raise serializers.ValidationError(_(f'{uuid} Option not found'))
        return self.option_generale_checkbox

    def validate(self, attrs):
        logger.info(f"validate : {attrs}")

        # On cherche la source de l'image principale :
        img_url = self.initial_data.get('img_url')
        if not attrs.get('img') and not img_url:
            raise serializers.ValidationError(
                _(f'img field must contain a file, or img_url a valid URL'))
        if not attrs.get('img') and img_url:
            self.img_name, self.img_img = get_img_from_url(img_url)

        # if attrs.get('send_to_cashless') and attrs.get('categorie_article') == Product.ADHESION:
        #     adhesion_to_cashless = Product.objects.filter(
        #         categorie_article=Product.ADHESION,
        #         send_to_cashless=True
        #     )
        #     if len(adhesion_to_cashless) > 0:
        #         raise serializers.ValidationError(
        #             _(f"Un article d'adhésion vers le cashless existe déja."))

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

    def to_representation(self, instance):
        # depth = 1 renvoie tous les tarifs du produit.
        # On retire les tarifs archivés (« supprimés ») : ils ne sont plus jamais affichés.
        # / depth = 1 returns every price: remove the archived ("deleted") ones.
        representation = super().to_representation(instance)
        tarifs_non_archives = []
        for tarif in representation.get("prices", []):
            if not tarif.get("archived"):
                tarifs_non_archives.append(tarif)
        representation["prices"] = tarifs_non_archives
        return representation


class PriceSerializer(serializers.ModelSerializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    adhesions_obligatoires = serializers.PrimaryKeyRelatedField(
        queryset=MembershipProduct.objects.filter(),
        required=False,
        many=True,
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
            'free_price',
            'vat',
            'stock',
            'max_per_user',
            'adhesions_obligatoires',
            'subscription_type',
            'recurring_payment',
            'publish',
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
                    _(f'Subscriptions are required to have a duration.'))
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
            raise serializers.ValidationError(_(f'{value} Artist not found'))
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
                raise serializers.ValidationError(_(f'{uuid} Product not found'))
        return self.products_db

    def validate_tags(self, value):
        self.tags_db = []
        for name in value:
            try:
                tag, created = Tag.objects.get_or_create(name=name)
                self.tags_db.append(tag)
            except Product.DoesNotExist as e:
                raise serializers.ValidationError(_(f'Tag creation error'))
        return self.tags_db

    def validate_options_radio(self, value):
        self.options_radio = []
        for uuid in value:
            try:
                option = OptionGenerale.objects.get(pk=uuid)
                self.options_radio.append(option)
            except OptionGenerale.DoesNotExist as e:
                raise serializers.ValidationError(_(f'{uuid} Option not found'))
        return self.options_radio

    def validate_options_checkbox(self, value):
        self.options_checkbox = []
        for uuid in value:
            try:
                option = OptionGenerale.objects.get(pk=uuid)
                self.options_checkbox.append(option)
            except OptionGenerale.DoesNotExist as e:
                raise serializers.ValidationError(_(f'{uuid} Option not found'))
        return self.options_checkbox

    def validate_minimum_cashless_required(self, value):
        if value:
            try:
                return int(value)
            except Exception as e:
                raise serializers.ValidationError(_(f'{value} below minimum cashless value.'))

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
    # products = ProductSerializer(many=True)
    # options_radio = OptionsSerializer(many=True)
    # options_checkbox = OptionsSerializer(many=True)
    # artists = Artist_on_eventSerializer(many=True)
    # tag = TagSerializer(many=True)
    # recurrent = WeekdaySerializer(many=True)
    # Mappage des champs du modèle aux propriétés de Schema.org
    name = serializers.CharField(read_only=True)
    startDate = serializers.DateTimeField(source='datetime', read_only=True)
    endDate = serializers.DateTimeField(source='end_datetime', read_only=True)
    disambiguatingDescription = serializers.CharField(source='short_description', read_only=True)
    description = serializers.CharField(source='long_description', read_only=True)
    url = serializers.URLField(source='full_url', read_only=True)
    eventStatus = serializers.SerializerMethodField()
    publicKeyPem = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()
    location = serializers.SerializerMethodField()
    organizer = serializers.SerializerMethodField()
    childrens = serializers.SerializerMethodField()
    # offers = serializers.SerializerMethodField()

    def get_eventStatus(self, obj):
        if obj.published:
            return "https://schema.org/EventScheduled"
        return "https://schema.org/EventCancelled"

    def get_publicKeyPem(self, obj):
        return obj.get_public_pem()

    def get_image(self, obj):
        try:
            img = obj.get_img()
            if img:
                return img.url
        except Exception:
            pass
        return None

    def get_location(self, obj):
        pa = getattr(obj, 'postal_address', None)
        if not pa:
            return None
        address = {
            "@type": "PostalAddress",
            "streetAddress": pa.street_address,
            "addressLocality": pa.address_locality,
            "postalCode": pa.postal_code,
            "addressCountry": pa.address_country,
        }
        if pa.address_region:
            address["addressRegion"] = pa.address_region
        place = {
            "@type": "Place",
            "address": address,
        }
        if pa.latitude is not None and pa.longitude is not None:
            try:
                place["geo"] = {
                    "@type": "GeoCoordinates",
                    "latitude": float(pa.latitude),
                    "longitude": float(pa.longitude),
                }
            except Exception:
                pass
        return place

    def get_organizer(self, obj):
        try:
            config = Configuration.get_solo()
            organizer = {"@type": "Organization", "name": config.organisation}
            if getattr(config, 'site_web', None):
                organizer["url"] = config.site_web
            return organizer
        except Exception:
            return None

    def get_childrens(self, obj):
        try:
            children_qs = obj.children.filter(published=True).order_by('datetime')
        except Exception:
            return []
        data = []
        for c in children_qs:
            data.append({
                "uuid": str(c.uuid),
                "name": c.name,
                "slug": c.slug,
                "startDate": c.datetime.isoformat() if c.datetime else None,
                "endDate": c.end_datetime.isoformat() if c.end_datetime else None,
                "url": c.full_url,
            })
        return data

    class Meta:
        model = Event
        fields = [
            'uuid',
            'name',
            'slug',
            'startDate',
            'endDate',
            'disambiguatingDescription',
            'description',
            'url',
            'eventStatus',
            'publicKeyPem',
            'image',
            'location',
            'organizer',
            'childrens',
        ]


    def to_representation(self, instance):
        # Appel de la méthode parente pour obtenir la représentation par défaut
        representation = super().to_representation(instance)

        # Ajout du contexte et du type au niveau supérieur
        return {
            "@context": "https://schema.org",
            "@type": "Event",
            **representation
        }


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


#
# class NewAdhesionValidator(serializers.Serializer):
#     adhesion = serializers.PrimaryKeyRelatedField(
#         queryset=Price.objects.filter(product__categorie_article=Product.ADHESION))
#     email = serializers.EmailField()
#     gift = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
#
#     # def validate_adhesion(self, value: Price):
#         # Si c'est une adhésion à envoyer au serveur cashless, on vérifie qu'il soit up
#         # if value.product.send_to_cashless:
#         #     config = Configuration.get_solo()
#         #     if not config.check_serveur_cashless():
#         #         raise serializers.ValidationError(
#         #             _(f"Le serveur cashless n'est pas disponible ( check serveur false ). Merci d'essayer ultérieurement"))
#         # return value
#
#     def validate_email(self, value):
#         # logger.info(f"NewAdhesionValidator validate email : {value}")
#         user_paiement: TibilletUser = get_or_create_user(value, send_mail=False)
#         self.user = user_paiement
#         return user_paiement.email
#
#     def validate(self, attrs):
#         price_adhesion: Price = attrs.get('adhesion')
#
#         user: TibilletUser = self.user
#
#         metadata = {
#             'tenant': f'{connection.tenant.uuid}',
#             'pk_adhesion': f"{price_adhesion.pk}",
#         }
#         self.metadata = metadata
#
#         ligne_article_adhesion = LigneArticle.objects.create(
#             pricesold=get_or_create_price_sold(price_adhesion, None, gift=attrs.get('gift')),
#             qty=1,
#         )
#
#         new_paiement_stripe = CreationPaiementStripe(
#             user=user,
#             liste_ligne_article=[ligne_article_adhesion, ],
#             metadata=metadata,
#             reservation=None,
#             source=Paiement_stripe.API_BILLETTERIE,
#             absolute_domain=self.context.get('request').build_absolute_uri().partition('/api')[0],
#         )
#
#         if new_paiement_stripe.is_valid():
#             paiement_stripe: Paiement_stripe = new_paiement_stripe.paiement_stripe_db
#             paiement_stripe.lignearticles.all().update(status=LigneArticle.UNPAID)#
# class NewAdhesionValidator(serializers.Serializer):
#     adhesion = serializers.PrimaryKeyRelatedField(
#         queryset=Price.objects.filter(product__categorie_article=Product.ADHESION))
#     email = serializers.EmailField()
#     gift = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
#
#     # def validate_adhesion(self, value: Price):
#         # Si c'est une adhésion à envoyer au serveur cashless, on vérifie qu'il soit up
#         # if value.product.send_to_cashless:
#         #     config = Configuration.get_solo()
#         #     if not config.check_serveur_cashless():
#         #         raise serializers.ValidationError(
#         #             _(f"Le serveur cashless n'est pas disponible ( check serveur false ). Merci d'essayer ultérieurement"))
#         # return value
#
#     def validate_email(self, value):
#         # logger.info(f"NewAdhesionValidator validate email : {value}")
#         user_paiement: TibilletUser = get_or_create_user(value, send_mail=False)
#         self.user = user_paiement
#         return user_paiement.email
#
#     def validate(self, attrs):
#         price_adhesion: Price = attrs.get('adhesion')
#
#         user: TibilletUser = self.user
#
#         metadata = {
#             'tenant': f'{connection.tenant.uuid}',
#             'pk_adhesion': f"{price_adhesion.pk}",
#         }
#         self.metadata = metadata
#
#         ligne_article_adhesion = LigneArticle.objects.create(
#             pricesold=get_or_create_price_sold(price_adhesion, None, gift=attrs.get('gift')),
#             qty=1,
#         )
#
#         new_paiement_stripe = CreationPaiementStripe(
#             user=user,
#             liste_ligne_article=[ligne_article_adhesion, ],
#             metadata=metadata,
#             reservation=None,
#             source=Paiement_stripe.API_BILLETTERIE,
#             absolute_domain=self.context.get('request').build_absolute_uri().partition('/api')[0],
#         )
#
#         if new_paiement_stripe.is_valid():
#             paiement_stripe: Paiement_stripe = new_paiement_stripe.paiement_stripe_db
#             paiement_stripe.lignearticles.all().update(status=LigneArticle.UNPAID)
#             self.checkout_session = new_paiement_stripe.checkout_session
#
#             return super().validate(attrs)
#
#         raise serializers.ValidationError(_(f'new_paiement_stripe not valid'))
#
#     def to_representation(self, instance):
#         representation = super().to_representation(instance)
#         logger.info(f"{self.checkout_session.url}")
#         representation['checkout_url'] = self.checkout_session.url
#         return representation

#             self.checkout_session = new_paiement_stripe.checkout_session
#
#             return super().validate(attrs)
#
#         raise serializers.ValidationError(_(f'new_paiement_stripe not valid'))
#
#     def to_representation(self, instance):
#         representation = super().to_representation(instance)
#         logger.info(f"{self.checkout_session.url}")
#         representation['checkout_url'] = self.checkout_session.url
#         return representation

#
# class MembreValidator(serializers.Serializer):
#     adhesion = serializers.PrimaryKeyRelatedField(
#         queryset=Price.objects.filter(product__categorie_article=Product.ADHESION)
#     )
#     email = serializers.EmailField()
#     first_name = serializers.CharField(max_length=200, required=False)
#     last_name = serializers.CharField(max_length=200, required=False)
#
#     options = serializers.PrimaryKeyRelatedField(queryset=OptionGenerale.objects.all(),
#                                                  many=True, allow_null=True, required=False)
#
#     phone = serializers.CharField(max_length=20, required=False)
#     postal_code = serializers.IntegerField(required=False)
#     birth_date = serializers.DateField(required=False)
#
#     newsletter = serializers.BooleanField(required=False)
#
#     def validate_adhesion(self, value):
#         self.price = value
#         return value
#
#     def validate_email(self, value):
#         if not getattr(self, 'price', None):
#             raise serializers.ValidationError(
#                 _(f"Pas de prix d'adhésion"))
#
#         user_paiement: TibilletUser = get_or_create_user(value)
#         self.user = user_paiement
#
#         self.fiche_membre, created = Membership.objects.get_or_create(
#             user=user_paiement,
#             price=self.price,
#         )
#
#         # Si une adhésion existe déja
#         if not created:
#             # Si elle est encore valide
#             if self.fiche_membre.is_valid():
#                 raise serializers.ValidationError(
#                     _(f"Un abonnement sur ce mail existe déjà et est valide jusque : {self.fiche_membre.deadline()}"))
#
#         if not self.fiche_membre.first_name:
#             if not self.initial_data.get('first_name'):
#                 raise serializers.ValidationError(_(f'first_name est obligatoire'))
#             self.fiche_membre.first_name = self.initial_data.get('first_name')
#         if not self.fiche_membre.last_name:
#             if not self.initial_data.get('last_name'):
#                 raise serializers.ValidationError(_(f'last_name est obligatoire'))
#             self.fiche_membre.last_name = self.initial_data.get('last_name')
#         if not self.fiche_membre.phone:
#             if not self.initial_data.get('phone'):
#                 raise serializers.ValidationError(_(f'phone est obligatoire'))
#             self.fiche_membre.phone = self.initial_data.get('phone')
#         if not self.fiche_membre.postal_code:
#             self.fiche_membre.postal_code = self.initial_data.get('postal_code')
#         if not self.fiche_membre.birth_date:
#             self.fiche_membre.birth_date = self.initial_data.get('birth_date')
#         if not self.fiche_membre.newsletter:
#             self.fiche_membre.newsletter = self.initial_data.get('newsletter')
#
#         self.fiche_membre.save()
#
#         return self.fiche_membre.user.email
#
#     def validate_options(self, value):
#         self.options = value
#         for option in value:
#             product = self.price.product
#             option: OptionGenerale
#             if option not in list(
#                     set(product.option_generale_radio.all()) | set(product.option_generale_checkbox.all())):
#                 raise serializers.ValidationError(_(f'Option {option.name} non disponible dans product'))
#
#         for option in self.options:
#             self.fiche_membre.option_generale.add(option)
#
#         return value


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

@atomic
def get_or_create_price_sold(price: Price, event: Event = None,
                             promo_code:PromotionalCode = None,
                             custom_amount: Decimal = None,):
    """
    Générateur des objets PriceSold pour envoi à Stripe.
    Price + Event = PriceSold

    On va chercher l'objet prix générique.
    On lie le prix générique à l'event
    pour générer la clé et afficher le bon nom sur stripe
    """
    prix = price.prix
    # `is not None` et pas `if custom_amount` : un montant saisi à 0 € est un montant, et
    # Decimal("0") est faux en Python. Le prix du tarif ne sert que sans montant saisi.
    # / `is not None`, never `if custom_amount`: a typed 0 € is an amount, and Decimal("0") is
    # falsy in Python. The price is the fallback only when no amount is given.
    if custom_amount is not None:
        prix = dround(custom_amount)
    if promo_code:
        prix = dround(prix - (prix * promo_code.discount_rate / 100))

    try :
        pricesold = PriceSold.objects.get(
            productsold__product=price.product,
            productsold__event=event,
            prix=prix, price=price)
    except PriceSold.MultipleObjectsReturned:
        pricesold = PriceSold.objects.filter(
            productsold__product=price.product,
            productsold__event=event,
            prix=prix, price=price).first()
    except PriceSold.DoesNotExist:
        try :
            productsold = ProductSold.objects.get(product=price.product, event=event)
        except ProductSold.DoesNotExist:
            productsold = ProductSold.objects.create(
                event=event,
                product=price.product
            )
        pricesold = PriceSold.objects.create(
            productsold=productsold,
            prix=prix,
            price=price,
        )

    if not pricesold.id_price_stripe and price.product.categorie_article not in [Product.FREERES, Product.BADGE]:
        pricesold.get_id_price_stripe()

    logger.info(f"GET_OR_CREATE_PRICESOLD {price.product.categorie_article} - prix : {pricesold.prix}, id_price_stripe : {pricesold.id_price_stripe}")
    return pricesold




"""
class DetailCashlessCardsValidator(serializers.ModelSerializer):
    class Meta:
        model = Detail
        fields = [
            "base_url",
            "origine",
            "generation",
        ]
"""

"""
class DetailCashlessCardsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Detail
        fields = [
            "base_url",
            "origine",
            "generation",
            "uuid",
        ]
"""

"""
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
"""

"""
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
"""


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


def moyen_monnaie_et_portefeuille_envoyes_a_l_ancien_laboutik(ligne):
    """
    Le moyen, la monnaie (`asset`) et le portefeuille (`wallet`) d'une ligne, tels que
    l'ancien LaBoutik (V1) les reçoit.
    / The method, currency and wallet of a line, as legacy LaBoutik (V1) receives them.

    LOCALISATION : ApiBillet/serializers.py
    LU PAR : `LigneArticleSerializer` (ce module), envoyé par BaseBillet/tasks.py
    `send_sale_to_laboutik` et `send_refund_to_laboutik`.

    LA RÈGLE :
    - la ligne a une vente : on lit LE règlement d'argent de la vente, hors offert
      (FREE). Une vente envoyée n'en a qu'un ; s'il y en avait plusieurs, le premier
      écrit est pris. Une vente gratuite, réglée sans aucun règlement d'argent : moyen
      « offert » (NA), monnaie et portefeuille vides, comme ses lignes l'ont toujours
      dit ;
    - la ligne n'a pas de vente : c'est une ligne HÉRITÉE, écrite avant le chantier.
      Elle garde ses propres champs (moyen, monnaie, portefeuille). Retiré en fiche H,
      avec ces champs de la ligne.
    / With a sale: the sale's money payment (offered left out); a free sale without
    any payment says "NA", empty currency and wallet. Without a sale (legacy line,
    removed in sheet H): the line's own fields.

    La tâche d'envoi n'appelle ce sérialiseur que pour une vente RÉGLÉE (elle se relance
    tant que la vente est en attente) : les règlements sont alors tous écrits.
    / The sending task only serializes a SETTLED sale's line.

    :param ligne: la `LigneArticle` envoyée
    :return: dict {payment_method (code), asset (uuid en texte ou None), wallet (uuid
        en texte ou None)}
    """
    ligne_heritee_sans_vente = ligne.vente_id is None
    if ligne_heritee_sans_vente:
        asset_de_la_ligne = None
        if ligne.asset is not None:
            asset_de_la_ligne = str(ligne.asset)
        wallet_de_la_ligne = None
        if ligne.wallet_id is not None:
            wallet_de_la_ligne = str(ligne.wallet_id)
        return {
            "payment_method": ligne.payment_method,
            "asset": asset_de_la_ligne,
            "wallet": wallet_de_la_ligne,
        }

    reglements_d_argent = []
    for reglement in ligne.vente.reglements.order_by("datetime", "pk"):
        if reglement.moyen != PaymentMethod.FREE:
            reglements_d_argent.append(reglement)

    vente_sans_reglement_d_argent = len(reglements_d_argent) == 0
    if vente_sans_reglement_d_argent:
        return {
            "payment_method": PaymentMethod.FREE.value,
            "asset": None,
            "wallet": None,
        }

    reglement_d_argent = reglements_d_argent[0]
    asset_du_reglement = None
    if reglement_d_argent.asset is not None:
        asset_du_reglement = str(reglement_d_argent.asset)
    wallet_du_reglement = None
    if reglement_d_argent.wallet_id is not None:
        wallet_du_reglement = str(reglement_d_argent.wallet_id)
    return {
        "payment_method": reglement_d_argent.moyen,
        "asset": asset_du_reglement,
        "wallet": wallet_du_reglement,
    }


class LigneArticleSerializer(serializers.ModelSerializer):
    """
    La charge utile d'UNE ligne envoyée à l'ancien LaBoutik (V1).
    / The payload of ONE line sent to legacy LaBoutik (V1).

    LOCALISATION : ApiBillet/serializers.py
    Envoyée par BaseBillet/tasks.py `send_sale_to_laboutik` et `send_refund_to_laboutik`.

    Les champs et leur forme sont un CONTRAT avec l'ancien LaBoutik : ils ne changent
    pas. Seule leur source change pour trois d'entre eux : le moyen, la monnaie et le
    portefeuille se lisent dans le règlement de la vente
    (`moyen_monnaie_et_portefeuille_envoyes_a_l_ancien_laboutik`).
    / Fields and shape are a CONTRACT with legacy LaBoutik; method, currency and wallet
    are read from the sale's payment.
    """
    pricesold = PriceSoldSerializer(many=False)
    payment_method = serializers.SerializerMethodField()
    asset = serializers.SerializerMethodField()
    wallet = serializers.SerializerMethodField()

    def _moyen_monnaie_et_portefeuille(self, ligne):
        """
        Lit le moyen, la monnaie et le portefeuille UNE seule fois par ligne : les trois
        champs ci-dessous les demandent, une seule lecture des règlements suffit.
        / Reads method, currency and wallet ONCE per line (three fields, one query).
        """
        if not hasattr(self, "_lectures_par_ligne"):
            self._lectures_par_ligne = {}
        if ligne.pk not in self._lectures_par_ligne:
            self._lectures_par_ligne[ligne.pk] = (
                moyen_monnaie_et_portefeuille_envoyes_a_l_ancien_laboutik(ligne)
            )
        return self._lectures_par_ligne[ligne.pk]

    def get_payment_method(self, ligne):
        return self._moyen_monnaie_et_portefeuille(ligne)["payment_method"]

    def get_asset(self, ligne):
        return self._moyen_monnaie_et_portefeuille(ligne)["asset"]

    def get_wallet(self, ligne):
        return self._moyen_monnaie_et_portefeuille(ligne)["wallet"]

    class Meta:
        model = LigneArticle
        fields = [
            'uuid',
            'pricesold',
            'qty',
            'vat',
            'datetime',
            'payment_method',
            'amount',
            'metadata',
            'asset',
            'wallet',
            'status',
            # 'paiement_stripe_uuid',
            # 'user_uuid_wallet',
        ]


class EmailSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)



class MembershipSerializer(serializers.ModelSerializer):
    option_generale = OptionsSerializer(many=True, read_only=True)
    object = serializers.CharField(read_only=True, default='membership')
    pk = serializers.SerializerMethodField()
    state = serializers.SerializerMethodField()
    state_display = serializers.SerializerMethodField()
    datetime = serializers.SerializerMethodField()
    deadline = serializers.SerializerMethodField()
    email = serializers.SerializerMethodField()
    comment = serializers.SerializerMethodField()
    price_name = serializers.SerializerMethodField()
    price_uuid = serializers.SerializerMethodField()
    product_name = serializers.SerializerMethodField()
    product_uuid = serializers.SerializerMethodField()
    organisation = serializers.SerializerMethodField()
    organisation_id = serializers.SerializerMethodField()
    payment_method_name = serializers.SerializerMethodField()
    member_name = serializers.SerializerMethodField()
    is_valid = serializers.SerializerMethodField()
    contribution_value = serializers.SerializerMethodField()
    product_img = serializers.SerializerMethodField()
    option_names = serializers.SerializerMethodField()
    # Ensure empty or null values do not break API consumers/writes
    custom_form = serializers.JSONField(required=False, allow_null=True, default=dict)

    class Meta:
        model = Membership
        fields = [
            # Legacy webhook fields
            'object', 'pk', 'uuid', 'state', 'datetime', 'deadline', 'email', 'comment',
            'first_name', 'last_name', 'pseudo', 'price_name', 'price_uuid', 'product_name', 'product_uuid',
            'organisation', 'organisation_id',
            # Useful extra fields
            'user', 'card_number', 'date_added', 'last_action', 'last_contribution',
            'contribution_value', 'payment_method', 'payment_method_name', 'newsletter', 'postal_code', 'birth_date',
            'phone', 'is_valid', 'asset_fedow', 'stripe_id_subscription', 'last_stripe_invoice',
            'member_name', 'product_img', 'option_generale', 'option_names', 'state_display',
            # Dynamic membership form data
            'custom_form',
        ]
        read_only_fields = (
            'uuid', 'date_added', 'last_action', 'last_contribution', 'deadline',
            'payment_method_name', 'state', 'email', 'price_name', 'price_uuid', 'product_name', 'product_uuid',
            'organisation', 'organisation_id', 'member_name', 'product_img', 'is_valid', 'option_generale',
            'option_names', 'object', 'pk', 'comment', 'state_display'
        )

    def validate_custom_form(self, value):
        """
        Accepts dict/list/null. Coerces empty values to None. If a JSON string is provided,
        attempts to parse it. This prevents crashes when frontends send "" or invalid empties.
        """
        if value in (None, ""):
            return None
        # If it's already a dict or list, keep it; also coerce empty containers to None
        if isinstance(value, (dict, list)):
            return value if value else None
        # If it's a string, try to parse JSON and validate result
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except Exception:
                raise serializers.ValidationError("Invalid JSON for custom_form")
            if parsed in (None, ""):
                return None
            if not isinstance(parsed, (dict, list)):
                raise serializers.ValidationError("custom_form must be a JSON object or array")
            return parsed if parsed else None
        raise serializers.ValidationError("custom_form must be a JSON object, array, stringified JSON, or null")

    def get_pk(self, obj):
        return str(obj.pk) if obj.pk is not None else None

    def get_state(self, obj):
        return obj.status if obj.status else None

    def get_state_display(self, obj):
        return obj.get_status_display() if obj.status else None

    def get_datetime(self, obj):
        return obj.date_added.isoformat() if obj.date_added else None

    def get_deadline(self, obj):
        return obj.deadline.isoformat() if obj.deadline else None

    def get_email(self, obj):
        return str(obj.email()) if obj else None

    def get_comment(self, obj):
        return obj.commentaire

    def get_price_name(self, obj):
        return obj.price.name if obj.price else None

    def get_price_uuid(self, obj):
        return str(obj.price.uuid) if obj.price else None

    def get_product_name(self, obj):
        if obj.price and obj.price.product:
            return obj.price.product.name
        return None

    def get_product_uuid(self, obj):
        if obj.price and obj.price.product:
            return str(obj.price.product.uuid)
        return None

    def get_organisation(self, obj):
        configuration = Configuration.get_solo()
        return f"{configuration.organisation}" if configuration else None

    def get_organisation_id(self, obj):
        configuration = Configuration.get_solo()
        return f"{configuration.uuid()}" if configuration else None

    def get_payment_method_name(self, obj):
        return obj.get_payment_method_display() if obj.payment_method else None

    def get_member_name(self, obj):
        return obj.member_name()

    def get_is_valid(self, obj):
        try:
            return bool(obj.is_valid())
        except Exception:
            return False

    def get_contribution_value(self, obj):
        return float(obj.contribution_value) if obj.contribution_value is not None else None

    def get_product_img(self, obj):
        try:
            img = obj.product_img()
            return str(img.url) if img is not None else None
        except Exception:
            return None

    def get_option_names(self, obj):
        return [opt.name for opt in obj.option_generale.all()]


class EventWriteSerializer(serializers.Serializer):
    """
    Write/validation serializer for creating and updating Event via API using schema.org-like input names
    aligned with the read EventSerializer.
    Accepts:
      - name: string
      - startDate: datetime -> Event.datetime
      - endDate: datetime (optional) -> Event.end_datetime
      - disambiguatingDescription: string (optional) -> Event.short_description
      - description: string (optional) -> Event.long_description
      - image: URL string (optional) -> saved to Event.img
      - location: dict Place with address (PostalAddress) and optional geo -> Event.postal_address
      - superEvent: string (uuid or slug) to set parent event (enables ACTION children automatically via model)
    Notes:
      - This serializer is separate from the read serializer for stricter control on inputs.
    """

    name = serializers.CharField(required=False, max_length=200)
    startDate = serializers.DateTimeField(required=False)
    endDate = serializers.DateTimeField(required=False, allow_null=True)
    disambiguatingDescription = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=250)
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    image = serializers.CharField(required=False, allow_blank=True)
    location = serializers.DictField(required=False)
    superEvent = serializers.CharField(required=False, allow_blank=True)

    def _require_on_create(self, attrs, field_name):
        if self.instance is None and not attrs.get(field_name):
            raise serializers.ValidationError({field_name: 'This field is required.'})

    def validate_image(self, value: str):
        if value:
            try:
                self.img_name, self.img_img = get_img_from_url(value)
            except Exception as e:
                raise serializers.ValidationError(f'Unable to download image: {e}')
        return value

    def validate_location(self, value: dict):
        if not isinstance(value, dict):
            raise serializers.ValidationError('location must be an object')
        address = value.get('address') or {}
        if not isinstance(address, dict):
            raise serializers.ValidationError('location.address must be an object')
        street = address.get('streetAddress')
        locality = address.get('addressLocality')
        postal = address.get('postalCode')
        country = address.get('addressCountry')
        if not all([street, locality, postal, country]):
            raise serializers.ValidationError('location.address missing required fields')
        address_region = address.get('addressRegion')
        name = value.get('name')
        geo = value.get('geo') or {}
        lat = geo.get('latitude') if isinstance(geo, dict) else None
        lng = geo.get('longitude') if isinstance(geo, dict) else None

        # Build defaults for get_or_create
        pa_defaults = {
            'name': name,
            'address_region': address_region,
            'latitude': lat,
            'longitude': lng,
        }
        self._postal_address, _ = PostalAddress.objects.get_or_create(
            street_address=street,
            address_locality=locality,
            postal_code=postal,
            address_country=country,
            defaults=pa_defaults
        )
        # If exists, optionally update optional fields if provided
        updated = False
        for field, val in pa_defaults.items():
            if val is not None and getattr(self._postal_address, field) != val:
                setattr(self._postal_address, field, val)
                updated = True
        if updated:
            self._postal_address.save()
        return value

    def validate_superEvent(self, value: str):
        if not value:
            return value
        parent = None
        # Try by UUID
        try:
            parent = Event.objects.get(pk=value)
        except Exception:
            # Try by slug
            try:
                parent = Event.objects.get(slug=value)
            except Event.DoesNotExist:
                raise serializers.ValidationError(f'superEvent not found: {value}')
        self._parent_event = parent
        return value

    def validate(self, attrs):
        # Enforce required on create
        self._require_on_create(attrs, 'name')
        self._require_on_create(attrs, 'startDate')

        # La fin ne peut pas etre avant le debut. Meme regle que Event.clean(),
        # que DRF n'appelle pas.
        # En modification partielle, une date absente de la requete est lue
        # sur l'evenement existant : envoyer seulement endDate doit aussi etre verifie.
        # / End cannot be before start. On partial update, a missing date is read
        # from the existing event.
        date_de_debut = attrs.get('startDate')
        if 'startDate' not in attrs and self.instance is not None:
            date_de_debut = self.instance.datetime

        date_de_fin = attrs.get('endDate')
        if 'endDate' not in attrs and self.instance is not None:
            date_de_fin = self.instance.end_datetime

        if date_de_debut and date_de_fin and date_de_fin < date_de_debut:
            raise serializers.ValidationError({
                'endDate': _("La fin de l'évènement doit être après son début."),
            })
        return attrs

    def create(self, validated_data):
        event_data = {
            'name': validated_data.get('name'),
            'datetime': validated_data.get('startDate'),
            'end_datetime': validated_data.get('endDate'),
            'short_description': validated_data.get('disambiguatingDescription'),
            'long_description': validated_data.get('description'),
        }
        if hasattr(self, '_postal_address'):
            event_data['postal_address'] = self._postal_address
        if hasattr(self, '_parent_event'):
            event_data['parent'] = self._parent_event
        event = Event.objects.create(**event_data)
        if getattr(self, 'img_img', None):
            event.img.save(self.img_name, self.img_img.fp)
        return event

    def update(self, instance: Event, validated_data):
        if 'name' in validated_data:
            instance.name = validated_data.get('name')
        if 'startDate' in validated_data:
            instance.datetime = validated_data.get('startDate')
        if 'endDate' in validated_data:
            instance.end_datetime = validated_data.get('endDate')
        if 'disambiguatingDescription' in validated_data:
            instance.short_description = validated_data.get('disambiguatingDescription')
        if 'description' in validated_data:
            instance.long_description = validated_data.get('description')
        if hasattr(self, '_postal_address') and 'location' in validated_data:
            instance.postal_address = self._postal_address
        if hasattr(self, '_parent_event') and 'superEvent' in validated_data:
            instance.parent = self._parent_event
        instance.save()
        if getattr(self, 'img_img', None) and 'image' in validated_data:
            instance.img.save(self.img_name, self.img_img.fp)
        return instance
