from django.contrib.auth import get_user_model
from django.db import connection
from rest_framework import serializers
import json
from django.utils.translation import gettext, gettext_lazy as _
from rest_framework.generics import get_object_or_404

import PaiementStripe
from AuthBillet.models import TibilletUser, HumanUser
from BaseBillet.models import Event, Price, Product, Reservation, Configuration, LigneArticle, Ticket
from PaiementStripe.models import Paiement_stripe
from PaiementStripe.views import creation_paiement_stripe


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
            "id_product_stripe",
        ]
        depth = 1
        read_only_fields = [
            'uuid',
            'id_product_stripe',
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
            'id_price_stripe',
            'stock',
            'max_per_user',
        ]

        read_only_fields = [
            'uuid',
            'id_price_stripe',
        ]
        depth = 1


class EventSerializer(serializers.ModelSerializer):
    products = ProductSerializer(
        many=True,
        read_only=True
    )

    class Meta:
        model = Event
        fields = [
            'uuid',
            'name',
            'short_description',
            'long_description',
            'datetime',
            'products',
            'img',
            'reservations',
            'complet',
        ]
        read_only_fields = ['uuid', 'reservations']
        depth = 1

    def validate(self, attrs):

        products = self.initial_data.get('products')
        if products:
            try:
                products_list = json.loads(products)
            except json.decoder.JSONDecodeError as e:
                raise serializers.ValidationError(_(f'products doit être un json valide : {e}'))

            self.products_to_db = []
            for product in products_list:
                self.products_to_db.append(get_object_or_404(Product, uuid=product.get('uuid')))
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


class ReservationValidator(serializers.Serializer):
    email = serializers.EmailField()
    event = serializers.PrimaryKeyRelatedField(queryset=Event.objects.all())
    prices = serializers.JSONField(required=True)

    def validate_email(self, value):
        User: TibilletUser = get_user_model()
        user_paiement, created = User.objects.get_or_create(
            email=value)

        if created:
            user_paiement: HumanUser
            user_paiement.client_source = connection.tenant
            user_paiement.client_achat.add(connection.tenant)
            user_paiement.is_active = False
        else:
            user_paiement.client_achat.add(connection.tenant)
        user_paiement.save()
        self.user_commande = user_paiement
        return user_paiement.email

    def validate_prices(self, value):
        print(value)

        # on vérifie que chaque article existe et a sa quantité.
        # et qu'il y ai au moins un billet pour la reservation.
        config = Configuration.get_solo()
        self.nbr_ticket = 0
        self.prices_list = []
        for entry in value:
            try:
                price = Price.objects.get(pk=entry['uuid'])
                price_object = {
                    'price': price,
                    'qty': float(entry['qty']),
                }

                if price.product.categorie_article == Product.BILLET:
                    self.nbr_ticket += entry['qty']

                    # Si les noms sont requis pour la billetterie
                    if config.name_required_for_ticket and entry['qty'] > 0:
                        if not entry.get('customers'):
                            raise serializers.ValidationError(_(f'customers non trouvés'))
                        if len(entry.get('customers')) != entry['qty']:
                            raise serializers.ValidationError(_(f'nombre customers non conforme'))

                        price_object['customers'] = entry.get('customers')

                self.prices_list.append(price_object)

            except Price.DoesNotExist as e:
                raise serializers.ValidationError(_(f'price non trouvé : {e}'))
            except ValueError as e:
                raise serializers.ValidationError(_(f'qty doit être un entier ou un flottant : {e}'))

        '''
        products = [
                      {
                        "uuid": "8c419d35-11a1-43b6-b500-b79db665d560",
                        "qty": 2,
                        "customers": [
                          {
                            "first_name": "Jean-Michel",
                            "last_name": "Amoitié"
                          },
                          {
                            "first_name": "Ellen",
                            "last_name": "Ripley"
                          }
                        ]
                      },
                      {
                        "uuid": "c6e847d4-baaa-4d21-a4f0-a572b8319615",
                        "qty": 1,
                        "customers": [
                          {
                            "first_name": "Douglas",
                            "last_name": "Adams"
                          }
                        ]
                      }
                    ]
                    
                products = [
                      {
                        "uuid": "8c419d35-11a1-43b6-b500-b79db665d560",
                        "qty": 2
                      },
                      {
                        "uuid": "c6e847d4-baaa-4d21-a4f0-a572b8319615",
                        "qty": 1
                      }
                    ]
        '''
        return value

    def validate(self, attrs):
        if self.nbr_ticket == 0:
            raise serializers.ValidationError(_(f'pas de billet dans la reservation'))

        config = Configuration.get_solo()
        reservation = Reservation.objects.create(
            user_commande=self.user_commande,
            event=attrs.get('event'),
        )

        lignes_article = []
        for price in self.prices_list:
            ligne_article = LigneArticle.objects.create(
                price=price.get('price'),
                qty=price.get('qty'),
            )
            lignes_article.append(ligne_article)

            if config.name_required_for_ticket and price.get('customers'):
                for customer in price.get('customers'):
                    ticket = Ticket.objects.create(
                        reservation=reservation,
                        first_name=customer.get('first_name'),
                        last_name=customer.get('last_name'),
                    )

        metadata = {'reservation':f'{reservation.uuid}'}
        new_paiement_stripe = creation_paiement_stripe(
            email_paiement=self.user_commande.email,
            liste_ligne_article=lignes_article,
            metadata=metadata,
            source=Paiement_stripe.BILLETTERIE,
            absolute_domain=self.context.get('request').build_absolute_uri().partition('/api')[0],
        )

        if new_paiement_stripe.is_valid():
            reservation.paiement = new_paiement_stripe.paiement_stripe_db
            reservation.save()
            print(new_paiement_stripe.checkout_session.stripe_id)
            # return new_paiement_stripe.redirect_to_stripe()
            self.checkout_session = new_paiement_stripe.checkout_session
            return super().validate(attrs)

        else:
            raise serializers.ValidationError(_(f'checkout strip not valid'))

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['checkout_url'] = self.checkout_session.url
        # import ipdb;ipdb.set_trace()
        return representation


