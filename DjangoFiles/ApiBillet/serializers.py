from rest_framework import serializers
from BaseBillet.models import Event

class EventSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Event
        fields = [
            'name',
            'short_description',
            'long_description',
            'datetime',
            # 'billets',
            # 'articles',
            'img',
            # 'reservations',
            # 'complet',
            ]
