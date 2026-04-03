"""
Serializers DRF pour la validation des actions de stock.
Jamais de Django Forms — toujours DRF Serializer.
/ DRF serializers for stock action validation. Never Django Forms.

LOCALISATION : inventaire/serializers.py
"""

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers


class MouvementRapideSerializer(serializers.Serializer):
    """
    Validation pour les actions rapides POS (réception, perte, offert).
    La quantité est saisie en unité pratique et convertie côté serveur.
    / Validation for quick POS actions. Quantity converted server-side.
    """

    quantite = serializers.IntegerField(
        min_value=1,
        error_messages={
            "min_value": _("Quantity must be greater than 0."),
            "required": _("Quantity is required."),
        },
    )
    motif = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=200,
    )


class AjustementSerializer(serializers.Serializer):
    """
    Validation pour l'ajustement inventaire (admin).
    L'utilisateur saisit le stock réel compté.
    / Validation for inventory adjustment. User enters real counted stock.
    """

    stock_reel = serializers.IntegerField(
        error_messages={
            "required": _("Real stock is required."),
        },
    )
    motif = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=200,
    )


class DebitMetreSerializer(serializers.Serializer):
    """
    Validation pour l'endpoint capteur débit mètre (Raspberry Pi).
    / Validation for flow meter sensor endpoint (Raspberry Pi).
    """

    product_uuid = serializers.UUIDField(
        error_messages={
            "required": _("Product UUID is required."),
        },
    )
    quantite_cl = serializers.IntegerField(
        min_value=1,
        error_messages={
            "min_value": _("Quantity must be greater than 0."),
        },
    )
    capteur_id = serializers.CharField(
        max_length=100,
        error_messages={
            "required": _("Sensor ID is required."),
        },
    )
