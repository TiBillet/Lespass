"""
Administration/serializers.py — DRF serializers pour les vues admin custom.
Administration/serializers.py — DRF serializers for custom admin views.
"""
from decimal import Decimal

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from Customers.models import Client
from fedow_core.models import Asset


class CardRefundConfirmSerializer(serializers.Serializer):
    """
    Valide le formulaire POST de confirmation d'un remboursement de carte.
    Validates the POST form for confirming a card refund.

    Champs :
    - vider_carte (bool) : si True, reset user + wallet_ephemere + CartePrimaire (action VV).
    """
    vider_carte = serializers.BooleanField(
        required=False,
        default=False,
        help_text=_("Si coche, reinitialise la carte apres remboursement (VV)."),
    )


class BankTransferCreateSerializer(serializers.Serializer):
    """
    Valide le formulaire POST de saisie d'un virement bancaire pot central -> tenant.
    Validates the POST form for recording a central pot bank transfer to a tenant.
    """
    tenant_uuid = serializers.UUIDField()
    asset_uuid = serializers.UUIDField()
    montant_euros = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal("0.01"),
    )
    date_virement = serializers.DateField()
    reference = serializers.CharField(max_length=100)
    comment = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_tenant_uuid(self, value):
        try:
            return Client.objects.get(uuid=value)
        except Client.DoesNotExist:
            raise serializers.ValidationError(_("Tenant introuvable."))

    def validate_asset_uuid(self, value):
        try:
            return Asset.objects.get(uuid=value, category=Asset.FED)
        except Asset.DoesNotExist:
            raise serializers.ValidationError(_("Asset FED introuvable."))

    def validate(self, attrs):
        from fedow_core.services import BankTransferService

        # Conversion euros -> centimes
        attrs["montant_centimes"] = int(round(attrs["montant_euros"] * 100))

        # Validation cross-fields : montant <= dette
        dette = BankTransferService.calculer_dette(
            tenant=attrs["tenant_uuid"], asset=attrs["asset_uuid"],
        )
        if attrs["montant_centimes"] > dette:
            raise serializers.ValidationError(
                _("Montant superieur a la dette actuelle (%(dette)s EUR).") % {
                    "dette": dette / 100,
                }
            )
        return attrs
