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


class NoEligibleTokens(Exception):
    """
    Levee quand une carte n'a aucun token eligible au remboursement.
    Raised when a card has no eligible tokens for refund.

    Tokens eligibles = TLF dont asset.tenant_origin == tenant courant + FED.
    Cas typiques : carte vierge, solde 0, ou tokens uniquement en categories
    non remboursables (TNF, TIM, FID).
    """

    def __init__(self, carte_tag_id: str = ""):
        self.carte_tag_id = carte_tag_id
        message = _(
            "Aucun solde remboursable sur la carte {tag_id}."
        ).format(tag_id=carte_tag_id)
        super().__init__(message)


class MontantSuperieurDette(Exception):
    """
    Levee quand un superuser tente d'enregistrer un virement bancaire d'un montant
    superieur a la dette actuelle du pot central envers le tenant pour cet asset.

    Raised when a superuser attempts to record a bank transfer larger than
    the central pot's current debt to the tenant for this asset.

    Securite hard : on n'accepte jamais qu'un BANK_TRANSFER cree une dette negative
    (qui voudrait dire "le tenant doit au pot central", hors scope V2).
    / Hard security: we never accept a BANK_TRANSFER that creates negative debt
    (which would mean "tenant owes the central pot", out of V2 scope).
    """

    def __init__(self, montant_demande_en_centimes: int, dette_actuelle_en_centimes: int):
        self.montant_demande_en_centimes = montant_demande_en_centimes
        self.dette_actuelle_en_centimes = dette_actuelle_en_centimes
        message = _(
            "Montant demande %(montant)s centimes superieur a la dette actuelle "
            "%(dette)s centimes."
        ) % {
            "montant": montant_demande_en_centimes,
            "dette": dette_actuelle_en_centimes,
        }
        super().__init__(message)
