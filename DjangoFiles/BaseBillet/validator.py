from rest_framework import serializers
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _
from BaseBillet.models import OptionGenerale, Configuration, Event, Article, Billet


class ReservationValidator(serializers.Serializer):
    nom = serializers.CharField(max_length=100, required=True)
    prenom = serializers.CharField(max_length=100, required=True)
    email = serializers.EmailField(required=True)
    phone = serializers.CharField(max_length=20, required=True)
    radio_generale = serializers.PrimaryKeyRelatedField(queryset=OptionGenerale.objects.all(), many=True)
    option_checkbox = serializers.PrimaryKeyRelatedField(queryset=OptionGenerale.objects.all(), many=True)
    articles = serializers.ListField()
    billets = serializers.ListField()

    def validate_articles(self, value):
        value_dict = {}
        art_obj = Article.objects.all()
        for couple in value:
            pk, qty = art_obj.get(pk=couple.split(',')[0]), int(couple.split(',')[1])
            value_dict[pk] = qty

        return value_dict

    def validate_billets(self, value):
        value_dict = {}
        billet_obj = Billet.objects.all()
        for couple in value:
            pk, qty = billet_obj.get(pk=couple.split(',')[0]), int(couple.split(',')[1])
            value_dict[pk] = qty

        return value_dict
    #
    # #     if value <= configuration.reservation_par_user_max :
    #         return value
    #     else :
    #         raise serializers.ValidationError(_(f"Pas plus de {configuration.reservation_par_user_max} places en même temps."))
