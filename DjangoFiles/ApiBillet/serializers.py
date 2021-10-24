from rest_framework import serializers
import json
from django.utils.translation import gettext, gettext_lazy as _
from rest_framework.generics import get_object_or_404

from BaseBillet.models import Event, Price, Product




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