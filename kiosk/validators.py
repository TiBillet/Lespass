"""
kiosk/validators.py — Validation des donnees de recharge kiosque (CHANTIER-02, Task 02A).
kiosk/validators.py — Kiosk refill data validation (CHANTIER-02, Task 02A).

Copie rebranchee de LaBoutik htmxview/validators.py (RefillWisePoseValidator).
Le parcours "link" (identification email/nom depuis le kiosque, linkValidator
cote LaBoutik) n'est pas repris ici : YAGNI, cf. plan CHANTIER-02 Task 02A.
/ Rebranched copy of LaBoutik htmxview/validators.py (RefillWisePoseValidator).
The "link" flow (kiosk email/name identification, linkValidator on LaBoutik's
side) is NOT ported here: YAGNI, see CHANTIER-02 Task 02A plan.
"""

import logging
from decimal import Decimal

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from fedow_connect.fedow_api import FedowAPI
from QrcodeCashless.models import CarteCashless

logger = logging.getLogger(__name__)


class RefillWisePoseValidator(serializers.Serializer):
    """
    Valide le montant et la carte NFC pour une recharge kiosque via TPE Stripe.
    `validate_tag_id` verifie d'abord que la carte est connue de Fedow, puis
    recupere sa copie locale (QrcodeCashless.CarteCashless) et l'attache a
    `self.card` (comme le fait la version LaBoutik).
    / Validates the amount and NFC card for a kiosk refill via a Stripe
    terminal. `validate_tag_id` first checks the card is known to Fedow, then
    fetches its local copy (QrcodeCashless.CarteCashless) and attaches it to
    `self.card` (same behaviour as the LaBoutik version).
    """
    # min_value en Decimal (pas float) : DRF emet un UserWarning sinon.
    # / min_value as Decimal (not float): DRF raises a UserWarning otherwise.
    totalAmount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0.01"))
    tag_id = serializers.CharField(max_length=8, min_length=8, required=True)

    def validate_tag_id(self, value):
        try:
            tag_id = value.upper()
            logger.info(f"--> tag_id = {tag_id}")

            # Verifie que la carte existe cote Fedow avant de chercher la copie locale.
            # / Check the card exists on Fedow before looking up the local copy.
            FedowAPI().NFCcard.retrieve(tag_id)
            self.card = CarteCashless.objects.get(tag_id=tag_id)
            return self.card
        except CarteCashless.DoesNotExist:
            raise ValidationError(_("Card not found with tag %(tag_id)s") % {"tag_id": value})
        except Exception as e:
            raise ValidationError(str(e))

    def validate_totalAmount(self, value):
        """
        Le montant doit etre positif ; conversion en centimes pour Fedow/Stripe.
        / Amount must be positive; converted to cents for Fedow/Stripe.
        """
        if value <= 0:
            raise serializers.ValidationError(_("Amount must be positive"))

        return int(value * 100)
