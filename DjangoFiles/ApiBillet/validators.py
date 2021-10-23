from rest_framework import serializers
import json

from BaseBillet.models import Event, TarifBillet

class BilletSerializer(serializers.ModelSerializer):
    class Meta:
        model = TarifBillet
        fields = [
            'uuid',
            "name",
            "prix",
            "reservation_par_user_max",
        ]



class EventSerializer(serializers.ModelSerializer):
    billets = BilletSerializer(
        many=True,
        read_only=True,
    )
    # billets = serializers.PrimaryKeyRelatedField(queryset=TarifBillet.objects.all(), many=True)

    class Meta:
        model = Event
        fields = [
            'uuid',
            'name',
            'short_description',
            'long_description',
            'datetime',
            'billets',
            # 'articles',
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
            # value['billets'] = serializers.ManyRelatedField(queryset=TarifBillet.objects.filter(uuid__in=billet_to_db), many=True)
        # return value

