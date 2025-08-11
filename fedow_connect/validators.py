from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from AuthBillet.models import Wallet
from BaseBillet.models import FedowTransaction


class PlaceValidator(serializers.Serializer):
    uuid = serializers.UUIDField()
    name = serializers.CharField()
    wallet = serializers.UUIDField()
    # stripe_connect_valid = serializers.BooleanField()
    dokos_id = serializers.CharField(max_length=50, allow_null=True, required=False)
    lespass_domain = serializers.CharField(max_length=100, allow_null=True, required=False)


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
        (TOKEN_LOCAL_FIAT, _('Local currency')),
        (TOKEN_LOCAL_NOT_FIAT, _('Gift currency')),
        (STRIPE_FED_FIAT, _('TiBillets')),
        (TIME, _("Time-based currency")),
        (FIDELITY, _("Loyalty points")),
        (BADGE, _("Punchclock")),
        (SUBSCRIPTION, _('Subscription')),
    ]

    category = serializers.ChoiceField(choices=CATEGORIES)
    get_category_display = serializers.CharField()

    created_at = serializers.DateTimeField()
    last_update = serializers.DateTimeField()
    is_stripe_primary = serializers.BooleanField()

    place_uuid_federated_with = serializers.ListField(child=serializers.UUIDField(), required=False, allow_null=True)

    total_token_value = serializers.IntegerField(required=False, allow_null=True)
    total_in_place = serializers.IntegerField(required=False, allow_null=True)
    total_in_wallet_not_place = serializers.IntegerField(required=False, allow_null=True)


class TransactionSimpleValidator(serializers.Serializer):
    # IDEM que TransactionValidator mais sans les objets associés
    uuid = serializers.UUIDField()
    hash = serializers.CharField(min_length=64, max_length=64)

    datetime = serializers.DateTimeField()
    subscription_start_datetime = serializers.DateTimeField(required=False, allow_null=True)
    sender = serializers.UUIDField()
    receiver = serializers.UUIDField()

    asset = serializers.UUIDField()

    amount = serializers.IntegerField()
    primary_card = serializers.UUIDField(required=False, allow_null=True)
    previous_transaction = serializers.UUIDField()

    FIRST, SALE, CREATION, REFILL, TRANSFER, SUBSCRIBE, BADGE, FUSION, REFUND, VOID = 'FST', 'SAL', 'CRE', 'REF', 'TRF', 'SUB', 'BDG', 'FUS', 'RFD', 'VID'
    QRCODE_SALE = 'QRS'

    TYPE_ACTION = (
        (FIRST, _("First block")),
        (SALE, _("Product sale")),
        (QRCODE_SALE, "Vente via QrCode"),
        (CREATION, _('Currency creation')),
        (REFILL, _('Refill')),
        (TRANSFER, _('Transfer')),
        (SUBSCRIBE, _('Subscription')),
        (BADGE, _('Punchclock')),
        (FUSION, _('Wallet merge')),
        (REFUND, _('Refund')),
        (VOID, 'Pass card / wallet dissociation'),
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

class TokenValidator(serializers.Serializer):
    uuid = serializers.UUIDField()
    name = serializers.CharField()
    value = serializers.IntegerField()
    asset = AssetValidator(many=False)

    asset_uuid = serializers.UUIDField()
    asset_name = serializers.CharField()
    asset_category = serializers.ChoiceField(choices=AssetValidator.CATEGORIES)

    is_primary_stripe_token = serializers.BooleanField()

    last_transaction = TransactionSimpleValidator(many=False, required=False, allow_null=True)

    #TODO: a virer, tout est dans last_transaction
    last_transaction_datetime = serializers.DateTimeField(allow_null=True, required=False)
    start_membership_date = serializers.DateTimeField(allow_null=True, required=False)

    def validate(self, attrs):
        # On check ici les tokens adhésions pour entrer en db s'il n'existe pas :
        # il peut avoir été créé sur laboutik
        if attrs['asset_category'] == AssetValidator.SUBSCRIPTION:
            last_transaction = attrs.get('last_transaction')
            if last_transaction :
                pass
                # import ipdb; ipdb.set_trace()
        return attrs

class WalletValidator(serializers.Serializer):
    uuid = serializers.UUIDField()
    tokens = TokenValidator(many=True)
    get_name = serializers.CharField()
    has_user_card = serializers.BooleanField()

    def validate(self, attrs):
        self.wallet, created = Wallet.objects.get_or_create(uuid=attrs['uuid'])
        return attrs


class QrCardValidator(serializers.Serializer):
    wallet_uuid = serializers.UUIDField()
    is_wallet_ephemere = serializers.BooleanField()
    origin = OriginValidator()


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

    FIRST, SALE, CREATION, REFILL, TRANSFER, SUBSCRIBE, BADGE, FUSION, REFUND, VOID, DEPOSIT = 'FST', 'SAL', 'CRE', 'REF', 'TRF', 'SUB', 'BDG', 'FUS', 'RFD', 'VID', 'BNK'
    QRCODE_SALE = 'QRS'

    TYPE_ACTION = (
        (FIRST, _("First block")),
        (SALE, _("Product sale")),
        (QRCODE_SALE, "Vente via QrCode"),
        (CREATION, _('Currency creation')),
        (REFILL, _('Refill')),
        (TRANSFER, _('Transfer')),
        (SUBSCRIBE, _('Subscription')),
        (BADGE, _('Punchclock')),
        (FUSION, _('Wallet merge')),
        (REFUND, _('Refund')),
        (VOID, 'Pass card / wallet dissociation'),
        (DEPOSIT, 'Remise en banque'),
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
