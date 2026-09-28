"""
kiosk/validators.py — Validation des donnees de recharge kiosque (CHANTIER-02, Task 02A).
kiosk/validators.py — Kiosk refill data validation (CHANTIER-02, Task 02A).

Copie rebranchee de LaBoutik htmxview/validators.py (RefillWisePoseValidator).
Le parcours "link" (identification email/nom depuis le kiosque, linkValidator
cote LaBoutik) n'est pas repris ici : YAGNI, cf. plan CHANTIER-02 Task 02A.
/ Rebranched copy of LaBoutik htmxview/validators.py (RefillWisePoseValidator).
The "link" flow (kiosk email/name identification, linkValidator on LaBoutik's
side) is NOT ported here: YAGNI, see CHANTIER-02 Task 02A plan.

LOCALISATION : kiosk/validators.py
"""

import logging
from decimal import Decimal

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from fedow_connect.fedow_api import CarteInconnueDeFedow
from kiosk.carte import lire_la_carte_pour_la_borne
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

    LOCALISATION : kiosk/validators.py
    """
    # min_value en Decimal (pas float) : DRF emet un UserWarning sinon.
    # / min_value as Decimal (not float): DRF raises a UserWarning otherwise.
    # La borne recharge en euros entiers : max_value aligne sur le pave numerique
    # (5 chiffres, sans virgule). Les centimes sont refuses dans validate_totalAmount.
    # decimal_places=2 reste accepte en ENTREE : le formulaire envoie « 20.00 ».
    # / Whole euros only: max_value matches the keypad (5 digits, no comma).
    # Cents are refused in validate_totalAmount; "20.00" is still accepted as input.
    totalAmount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("1"),
        max_value=Decimal("99999"),
        error_messages={
            "max_value": _("Le montant est trop élevé."),
        },
    )
    tag_id = serializers.CharField(max_length=8, min_length=8, required=True)

    def validate_tag_id(self, value):
        # On lit la carte en entier (solde compris) plutot que de jeter la reponse
        # de Fedow : le solde avant recharge sert a l'ecran de succes.
        # / Read the whole card (balance included) instead of discarding Fedow's
        # answer: the balance before refill feeds the success screen.
        try:
            self.carte_lue = lire_la_carte_pour_la_borne(value)
            self.card = self.carte_lue["carte_locale"]
            return self.card
        except (CarteCashless.DoesNotExist, CarteInconnueDeFedow):
            raise ValidationError(_("Card not found with tag %(tag_id)s") % {"tag_id": value})
        except Exception as e:
            # Le texte brut (reseau, Fedow) reste dans le journal ; le public lit
            # un message simple et traduit. / Raw error logged, plain message shown.
            logger.error(f"validate_tag_id : lecture de la carte {value} impossible : {e}")
            raise ValidationError(_("La carte n'a pas pu être lue. Merci de réessayer."))

    def validate_totalAmount(self, value):
        """
        Le montant doit etre positif et en euros entiers ; conversion en
        centimes pour Fedow/Stripe.
        / Amount must be positive and in whole euros; converted to cents.
        """
        if value <= 0:
            raise serializers.ValidationError(_("Amount must be positive"))

        # « 20.00 » passe, « 20.50 » est refuse : le pave de la borne n'a pas de
        # virgule, un montant avec des centimes vient forcement d'ailleurs.
        # / "20.00" passes, "20.50" is refused: the keypad has no comma.
        le_montant_a_des_centimes = (value % 1) != 0
        if le_montant_a_des_centimes:
            raise serializers.ValidationError(
                _("Le montant doit être un nombre entier d'euros.")
            )

        return int(value * 100)


class RecapitulatifSerializer(RefillWisePoseValidator):
    """
    Valide le montant et la carte avant d'afficher le recapitulatif.
    / Validates amount and card before showing the summary.

    LOCALISATION : kiosk/validators.py

    Memes regles que la recharge : on ne montre jamais un recapitulatif
    qu'on refuserait ensuite au paiement.
    / Same rules as the refill: never show a summary the payment would refuse.
    """
