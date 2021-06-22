from rest_framework import serializers
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _
from BaseBillet.models import OptionGenerale, Configuration, Event


class ReservationValidator(serializers.Serializer):

    nom = serializers.CharField(max_length=100, required=True)
    prenom = serializers.CharField(max_length=100, required=True)
    email = serializers.EmailField(required=True)
    phone = serializers.CharField(max_length=100, required=True)
    qty = serializers.IntegerField(required=True)
    radio_generale = serializers.PrimaryKeyRelatedField(queryset=OptionGenerale.objects.all(), many=True)

    def validate_qty(self, value):
        configuration = Configuration.get_solo()
        if value <= configuration.reservation_par_user_max :
            return value
        else :
            raise serializers.ValidationError(_(f"Pas plus de {configuration.reservation_par_user_max} places en même temps."))

