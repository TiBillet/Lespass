"""
Serializers DRF pour le module tireuse connectée (controlvanne).
/ DRF serializers for the connected tap module (controlvanne).

LOCALISATION : controlvanne/serializers.py

Validation des données entrantes du Raspberry Pi.
Pas de ModelSerializer — serializers explicites (règle FALC).
/ Validation of incoming Raspberry Pi data.
No ModelSerializer — explicit serializers (FALC rule).
"""

from rest_framework import serializers
from django.utils.translation import gettext_lazy as _


class PingSerializer(serializers.Serializer):
    """
    Données du ping de connectivité.
    / Connectivity ping data.

    Le Pi envoie son UUID de tireuse pour confirmer l'association.
    / The Pi sends its tap UUID to confirm the association.
    """

    tireuse_uuid = serializers.UUIDField(
        required=False,
        help_text=_("UUID of the tap (optional, for association check)."),
    )


class AuthorizeSerializer(serializers.Serializer):
    """
    Données d'autorisation NFC : le Pi badge une carte et demande l'autorisation.
    / NFC authorization data: the Pi scans a card and requests authorization.
    """

    tireuse_uuid = serializers.UUIDField(
        help_text=_("UUID of the tap where the card was scanned."),
    )
    uid = serializers.CharField(
        max_length=32,
        help_text=_("NFC card UID (hex string from the reader)."),
    )


# Les types d'événement possibles pendant un service
# / Possible event types during a pour
EVENEMENT_CHOICES = [
    ("pour_start", _("Pour started")),
    ("pour_update", _("Pour update (volume)")),
    ("pour_end", _("Pour ended")),
    ("card_removed", _("Card removed")),
]


class EventSerializer(serializers.Serializer):
    """
    Événement en temps réel pendant un service (tirage de bière).
    / Real-time event during a pour (beer dispensing).

    Le Pi envoie des mises à jour de volume et de statut.
    / The Pi sends volume and status updates.
    """

    tireuse_uuid = serializers.UUIDField(
        help_text=_("UUID of the tap."),
    )
    uid = serializers.CharField(
        max_length=32,
        help_text=_("NFC card UID of the active session."),
    )
    event_type = serializers.ChoiceField(
        choices=EVENEMENT_CHOICES,
        help_text=_("Type of event."),
    )
    volume_ml = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        default=0,
        help_text=_("Cumulative volume served since session start (ml)."),
    )
