from rest_framework import serializers
import json
from django.utils.translation import gettext, gettext_lazy as _
from rest_framework.generics import get_object_or_404

from BaseBillet.models import Event, TarifBillet, Article


class TarifsSerializer(serializers.ModelSerializer):
    class Meta:
        model = TarifBillet
        fields = [
            'uuid',
            "name",
            "prix",
            "reservation_par_user_max",
        ]
        read_only_fields = ['uuid']


class ArticleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Article
        fields = [
            'uuid',
            'name',
            'prix',
            'stock',
            'reservation_par_user_max',
            'vat',
            'publish',
            'img',
            'categorie_article',
            'id_product_stripe',
            'id_price_stripe',
        ]
        read_only_fields = [
            'uuid',
            'id_product_stripe',
            'id_price_stripe',
        ]
        depth = 1


class EventSerializer(serializers.ModelSerializer):
    tarifs = TarifsSerializer(
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
            'tarifs',
            'articles',
            'img',
            'reservations',
            'complet',
        ]
        read_only_fields = ['uuid', 'reservations']
        depth = 1

    def validate(self, attrs):

        tarifs = self.initial_data.get('tarifs')
        if tarifs:
            try:
                tarifs_list = json.loads(tarifs)
            except json.decoder.JSONDecodeError as e:
                raise serializers.ValidationError(_(f'tarifs doit être un json valide : {e}'))

            self.tarif_to_db = []
            for tarif in tarifs_list:
                self.tarif_to_db.append(get_object_or_404(TarifBillet, uuid=tarif.get('uuid')))
            return super().validate(attrs)
        else:
            raise serializers.ValidationError(_('tarifs doit être un json valide'))

    def save(self, **kwargs):
        instance = super().save(**kwargs)
        instance.tarifs.clear()
        for tarif in self.tarif_to_db:
            instance.tarifs.add(tarif)
        return instance


'''
[
    {
        "uuid": "37a1093f-565d-4b38-858d-680568269d43",
    },
    {
        "uuid": "94d36be2-9bb9-4aa6-ab60-fc76287a1290",
    }
]
'''
