"""
Serializers DRF pour l'app PaiementStripe.
DRF serializers for the PaiementStripe app.

LOCALISATION : PaiementStripe/serializers.py

Regle du projet (stack djc) :
- Utiliser serializers.Serializer, jamais Django Forms.
- Bornes hardcodees (YAGNI), deplacables sur Asset plus tard si besoin.
/ Project rule (djc stack):
- Use serializers.Serializer, never Django Forms.
- Hardcoded bounds (YAGNI), movable onto Asset later if needed.
"""

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers


class RefillAmountSerializer(serializers.Serializer):
    """
    Valide un montant de recharge FED saisi en centimes.
    / Validates a FED refill amount in cents.

    La conversion euros -> centimes est faite par la vue AVANT d'appeler ce serializer
    (l'user saisit en euros dans le formulaire HTMX, la vue convertit via Decimal).
    / Euros -> cents conversion is done by the view BEFORE calling this serializer.
    """

    # Montant minimum : 100 centimes = 1,00 EUR
    # Montant maximum : 50000 centimes = 500,00 EUR
    # / Min: 100 cents = 1.00 EUR. Max: 50000 cents = 500.00 EUR.
    MIN_CENTS = 100
    MAX_CENTS = 50000

    amount_cents = serializers.IntegerField(
        min_value=MIN_CENTS,
        max_value=MAX_CENTS,
        error_messages={
            "required": _("Le montant est obligatoire."),
            "min_value": _("Montant minimum : 1,00 €"),
            "max_value": _("Montant maximum : 500,00 €"),
            "invalid": _("Montant invalide."),
        },
    )
