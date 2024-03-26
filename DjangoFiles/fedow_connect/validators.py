from rest_framework import serializers
from django.core.cache import cache
from django.utils.translation import gettext_lazy as _

from AuthBillet.models import Wallet


class PlaceValidator(serializers.Serializer):
    uuid = serializers.UUIDField()
    name = serializers.CharField()
    wallet = serializers.UUIDField()
    stripe_connect_valid = serializers.BooleanField()
    dokos_id = serializers.CharField(max_length=50, allow_null=True, required=False)


class OriginValidator(serializers.Serializer):
    place = PlaceValidator(many=False, required=True)
    generation = serializers.IntegerField()
    img = serializers.ImageField(required=False, allow_null=True)


### SERIALIZER DE DONNEE RECEPTIONEES DEPUIS FEDOW ###
class AssetValidator(serializers.Serializer):
    uuid = serializers.UUIDField()
    name = serializers.CharField()
    currency_code = serializers.CharField(max_length=3)
    place_origin = PlaceValidator(many=False, required=False, allow_null=True)

    STRIPE_FED_FIAT = 'FED'
    TOKEN_LOCAL_FIAT = 'TLF'
    TOKEN_LOCAL_NOT_FIAT = 'TNF'
    TIME = 'TIM'
    BADGE = 'BDG'
    SUBSCRIPTION = 'SUB'
    FIDELITY = 'FID'

    CATEGORIES = [
        (TOKEN_LOCAL_FIAT, _('Token équivalent euro')),
        (TOKEN_LOCAL_NOT_FIAT, _('Non fiduciaire')),
        (STRIPE_FED_FIAT, _('Stripe Connect')),
        (TIME, _("Monnaie temps, decompte d'utilisation")),
        (BADGE, _("Badgeuse/Pointeuse")),
        (SUBSCRIPTION, _('Adhésion ou abonnement')),
        (FIDELITY, _('Points de fidélités')),
    ]
    category = serializers.ChoiceField(choices=CATEGORIES)

    created_at = serializers.DateTimeField()
    last_update = serializers.DateTimeField()
    is_stripe_primary = serializers.BooleanField()

    total_token_value = serializers.IntegerField(required=False, allow_null=True)
    total_in_place = serializers.IntegerField(required=False, allow_null=True)
    total_in_wallet_not_place = serializers.IntegerField(required=False, allow_null=True)


class TokenValidator(serializers.Serializer):
    uuid = serializers.UUIDField()
    name = serializers.CharField()
    value = serializers.IntegerField()
    asset = AssetValidator(many=False)

    asset_uuid = serializers.UUIDField()
    asset_name = serializers.CharField()
    asset_category = serializers.ChoiceField(choices=AssetValidator.CATEGORIES)

    is_primary_stripe_token = serializers.BooleanField()
    last_transaction_datetime = serializers.DateTimeField(allow_null=True, required=False)


class WalletValidator(serializers.Serializer):
    uuid = serializers.UUIDField()
    tokens = TokenValidator(many=True)

    def validate(self, attrs):
        self.wallet, created = Wallet.objects.get_or_create(uuid=attrs['uuid'])
        return attrs

class CardValidator(serializers.Serializer):
    wallet = WalletValidator(many=False)
    origin = OriginValidator()
    uuid = serializers.UUIDField()
    qrcode_uuid = serializers.UUIDField()
    first_tag_id = serializers.CharField(min_length=8, max_length=8)
    number_printed = serializers.CharField()
    is_wallet_ephemere = serializers.BooleanField()
