from rest_framework import serializers
import json

from BaseBillet.models import Event, Price

class BilletSerializer(serializers.ModelSerializer):
    class Meta:
        model = Price
        fields = [
            'uuid',
            "name",
            "prix",
            "max_per_user",
        ]



class EventSerializer(serializers.ModelSerializer):
    billets = BilletSerializer(
        many=True,
        read_only=True,
    )
    # billets = serializers.PrimaryKeyRelatedField(queryset=Price.objects.all(), many=True)

    class Meta:
        model = Event
        fields = [
            'uuid',
            'name',
            'short_description',
            'long_description',
            'datetime',
            'billets',
            # 'products',
            'img',
            # 'reservations',
            'complet',
            ]
        # depth = 1

    def save(self, **kwargs):
        return super().save(**kwargs)

    # def validate(self, value):
    #     pass
    #     billets = self.initial_data.get('billets')
    #     if billets:
    #         billets_list = json.loads(billets)
    #         billet_to_db = []
    #         for billet in billets_list :
    #             billet_to_db.append(billet.get('uuid'))
            # value['billets'] = serializers.ManyRelatedField(queryset=Price.objects.filter(uuid__in=billet_to_db), many=True)
        # return value

