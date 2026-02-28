"""
fedow_core/exceptions.py — Exceptions metier du moteur de portefeuille.
fedow_core/exceptions.py — Business exceptions for the wallet engine.
"""

from django.utils.translation import gettext_lazy as _


class SoldeInsuffisant(Exception):
    """
    Levee quand un debit depasse le solde disponible sur un Token.
    Raised when a debit exceeds the available balance on a Token.

    Exemple / Example:
        Token.value = 500  (5,00 EUR)
        debiter(montant_en_centimes=800)  → SoldeInsuffisant
    """

    def __init__(self, solde_actuel_en_centimes, montant_demande_en_centimes, asset_name=""):
        self.solde_actuel_en_centimes = solde_actuel_en_centimes
        self.montant_demande_en_centimes = montant_demande_en_centimes
        self.asset_name = asset_name

        # Le message utilise _() car il peut remonter jusqu'a l'utilisateur
        # (reponse d'erreur dans une vue, toast, etc.).
        # The message uses _() because it can reach the end user
        # (error response in a view, toast, etc.).
        message = _(
            "Solde insuffisant pour '%(asset_name)s' : "
            "solde=%(solde)s centimes, "
            "demande=%(demande)s centimes."
        ) % {
            'asset_name': asset_name,
            'solde': solde_actuel_en_centimes,
            'demande': montant_demande_en_centimes,
        }
        super().__init__(message)
