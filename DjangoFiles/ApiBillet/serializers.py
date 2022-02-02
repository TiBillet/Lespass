import datetime

from django.contrib.auth import get_user_model
from django.db import connection
from django.utils.text import slugify
from rest_framework import serializers
import json
from django.utils.translation import gettext, gettext_lazy as _
from rest_framework.generics import get_object_or_404

from AuthBillet.models import TibilletUser, HumanUser
from BaseBillet.models import Event, Price, Product, Reservation, Configuration, LigneArticle, Ticket, Paiement_stripe, \
    PriceSold, ProductSold
from PaiementStripe.views import creation_paiement_stripe

import logging

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
            "short_description",
            "long_description",
            "adress",
            "phone",
            "email",
            "site_web",
            "twitter",
            "facebook",
            "instagram",
            "adhesion_obligatoire",
            "button_adhesion",
            "name_required_for_ticket",
            "map_img",
            "carte_restaurant",
            "img_variations",
            "logo",
        ]
        read_only_fields = fields

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        # import ipdb;ipdb.set_trace()
        return representation


class EventSerializer(serializers.ModelSerializer):
    products = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all(), many=True)
    # products = ProductSerializer(
    #     many=True,
    #     read_only=True
    # )

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
            'img',
            'reservations',
            'complet',
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

    '''
    
    products = [
        {"uuid":"9340a9a1-1b90-488e-ab68-7b358b213dd7"},
        {"uuid":"60db1531-fd0a-4d92-a785-f384e77cd213"}
    ]
    
    
    '''


class ReservationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reservation
        fields = [
            'uuid',
            'datetime',
            'user_commande',
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
        depth = 1


class MembreshipValidator(serializers.Serializer):
    email = serializers.EmailField()

    first_name = serializers.CharField(max_length=200, )
    last_name = serializers.CharField(max_length=200, )

    phone = serializers.CharField(max_length=20, required=False)
    postal_code = serializers.IntegerField(required=False)
    birth_date = serializers.DateField(required=False)

    contribution_value = serializers.FloatField()

    def validate_email(self, value):
        User: TibilletUser = get_user_model()
        user_paiement, created = User.objects.get_or_create(
            email=value, username=value)

        if created:
            user_paiement: HumanUser
            user_paiement.client_source = connection.tenant
            user_paiement.client_achat.add(connection.tenant)
            user_paiement.is_active = False
        else:
            user_paiement.client_achat.add(connection.tenant)

        user_paiement.save()
        return user_paiement.email

def get_near_event_by_date():
    try:
        return Event.objects.get(datetime__date=datetime.datetime.now().date())
    except Event.MultipleObjectsReturned :
        return Event.objects.filter(datetime__date=datetime.datetime.now().date()).first()
    except Event.DoesNotExist :
        return Event.objects.filter(datetime__gte=datetime.datetime.now()).first()
    except:
        return None

def create_ticket(pricesold, customer, reservation):
    ticket = Ticket.objects.create(
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

    On va chercher l'objets prix générique.
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


def validate_email_and_return_user(email):
    """

    :param email: email à vérifier
    :type email: str
    :return: TibilletUser
    :rtype: TibilletUser
    """
    User: TibilletUser = get_user_model()
    user, created = User.objects.get_or_create(
        email=email, username=email)

    if created:
        user: HumanUser
        user.client_source = connection.tenant
        user.is_active = False

    user.client_achat.add(connection.tenant)

    user.save()
    return user


class ReservationValidator(serializers.Serializer):
    email = serializers.EmailField()
    event = serializers.PrimaryKeyRelatedField(queryset=Event.objects.all())
    prices = serializers.JSONField(required=True)

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

                if price.product.categorie_article in [Product.BILLET]:
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
        if event.complet():
            raise serializers.ValidationError(_(f'Jauge atteinte : Evenement complet.'))

        # Les articles semblent bon,
        # on construit l'object reservation.
        reservation = Reservation.objects.create(
            user_commande=self.user_commande,
            event=event,
        )

        # Ici on construit :
        #   price_sold pour lier l'event à la vente
        #   ligne article pour envoie en paiement
        #   Ticket nominatif
        list_line_article_sold = []
        for line_price in self.prices_list:
            price_generique: Price = line_price['price']
            qty = line_price.get('qty')
            pricesold: PriceSold = get_or_create_price_sold(price_generique, event)

            # les lignes articles pour la vente
            line_article = LigneArticle.objects.create(
                pricesold=pricesold,
                qty=qty,
            )
            list_line_article_sold.append(line_article)

            # import ipdb; ipdb.set_trace()
            # Les Tickets si article est un billet
            if price_generique.product.categorie_article == Product.BILLET:
                for customer in line_price.get('customers'):
                    create_ticket(pricesold, customer, reservation)

        metadata = {'reservation': f'{reservation.uuid}'}
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

            return super().validate(attrs)

        else:
            raise serializers.ValidationError(_(f'checkout strip not valid'))

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        logger.info(f"{self.checkout_session.url}")
        representation['checkout_url'] = self.checkout_session.url
        # import ipdb;ipdb.set_trace()
        return representation
