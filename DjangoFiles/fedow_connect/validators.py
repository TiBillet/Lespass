from rest_framework import serializers
from django.core.cache import cache
from django.utils.translation import gettext_lazy as _

from AuthBillet.models import Wallet
from BaseBillet.models import FedowTransaction


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
    FIDELITY = 'FID'
    BADGE = 'BDG'
    SUBSCRIPTION = 'SUB'

    CATEGORIES = [
        (TOKEN_LOCAL_FIAT, _('Fiduciaire')),
        (TOKEN_LOCAL_NOT_FIAT, _('Cadeau')),
        (STRIPE_FED_FIAT, _('Fiduciaire fédérée')),
        (TIME, _("Monnaie temps")),
        (FIDELITY, _("Points de fidélité")),
        (BADGE, _("Badgeuse/Pointeuse")),
        (SUBSCRIPTION, _('Adhésion ou abonnement')),
    ]

    category = serializers.ChoiceField(choices=CATEGORIES)
    get_category_display = serializers.CharField()

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
    get_name = serializers.CharField()

    def validate(self, attrs):
        self.wallet, created = Wallet.objects.get_or_create(uuid=attrs['uuid'])
        return attrs

    # Ne s'execute que si on va chercher .data
    # et non pas validated_data
    # def to_representation(self, instance):
    #     # Add apikey user to representation
    #     rep = super().to_representation(instance)
    #     rep['custom_representation'] = {}
    #     #TODO: aller voir dans toute les config de lieux pour trouver le nom
    #
    #     if hasattr(self.wallet, 'user'):
    #         rep['custom_representation']['display_name'] = self.wallet.user.email
    #     elif self.wallet.display_name:
    #         rep['custom_representation']['display_name'] = self.wallet.display_name
    #     else :
    #         rep['custom_representation']['display_name'] = f"{str(self.wallet.uuid)[:8]}"
    #
    #     return rep

class CardValidator(serializers.Serializer):
    wallet = WalletValidator(many=False)
    origin = OriginValidator()
    uuid = serializers.UUIDField()
    qrcode_uuid = serializers.UUIDField()
    first_tag_id = serializers.CharField(min_length=8, max_length=8)
    number_printed = serializers.CharField()
    is_wallet_ephemere = serializers.BooleanField()



class TransactionValidator(serializers.Serializer):
    uuid = serializers.UUIDField()
    hash = serializers.CharField(min_length=64, max_length=64)

    datetime = serializers.DateTimeField()
    subscription_start_datetime = serializers.DateTimeField(required=False, allow_null=True)
    sender = serializers.UUIDField()
    receiver = serializers.UUIDField()

    asset = serializers.UUIDField()
    serialized_asset = AssetValidator(required=False, allow_null=True)
    serialized_sender = WalletValidator(required=False, allow_null=True)
    serialized_receiver = WalletValidator(required=False, allow_null=True)

    amount = serializers.IntegerField()
    card = CardValidator(required=False, many=False, allow_null=True)
    primary_card = serializers.UUIDField(required=False, allow_null=True)
    previous_transaction = serializers.UUIDField()

    FIRST, SALE, CREATION, REFILL, TRANSFER, SUBSCRIBE, BADGE, FUSION, REFUND, VOID = 'FST', 'SAL', 'CRE', 'REF', 'TRF', 'SUB', 'BDG', 'FUS', 'RFD', 'VID'
    TYPE_ACTION = (
        (FIRST, "Premier bloc"),
        (SALE, "Vente d'article"),
        (CREATION, 'Creation monétaire'),
        (REFILL, 'Recharge'),
        (TRANSFER, 'Transfert'),
        (SUBSCRIBE, 'Abonnement ou adhésion'),
        (BADGE, 'Badgeuse'),
        (FUSION, 'Fusion de deux wallets'),
        (REFUND, 'Remboursement'),
        (VOID, 'Dissocciation de la carte et du wallet user'),
    )
    action = serializers.ChoiceField(choices=TYPE_ACTION)
    get_action_display = serializers.CharField()

    comment = serializers.CharField(required=False, allow_null=True)
    metadata = serializers.JSONField(required=False, allow_null=True)
    verify_hash = serializers.BooleanField()

    def validate(self, attrs):
        uuid = attrs['uuid']
        hash = attrs['hash']
        datetime = attrs['datetime']
        self.fedow_transaction, created = FedowTransaction.objects.get_or_create(uuid=uuid, hash=hash,
                                                                                 datetime=datetime)
        return attrs


class PaginatedTransactionValidator(serializers.Serializer):
    next = serializers.URLField(required=False, allow_null=True)
    previous = serializers.URLField(required=False, allow_null=True)
    results = TransactionValidator(many=True)
