"""
Fonctions utilitaires pour le POS — reset carte, helpers de test.
La fonction reset_carte sera aussi utilisee dans la caisse (feature future :
permettre au caissier de retirer un wallet et un user d'une carte NFC).
Pour l'instant, utilisable uniquement en mode DEBUG.
/ POS utility functions — card reset, test helpers.
The reset_carte function will also be used in the POS (future feature:
allow cashier to remove a wallet and user from an NFC card).
For now, only usable in DEBUG mode.

LOCALISATION : laboutik/utils/test_helpers.py
"""
import logging

from django.conf import settings
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)


def reset_carte(tag_id=None):
    """
    Remet a zero une carte NFC : detache le user et supprime le wallet_ephemere.
    La carte reste en base (tag_id, number, detail) mais redevient anonyme.
    Utilisee par les tests Playwright et par create_test_pos_data (carte 3 jetable).
    Sera aussi la base de la feature caisse "reset carte" (retirer user/wallet d'une carte).
    / Resets an NFC card: detaches user and deletes wallet_ephemere.
    The card stays in DB (tag_id, number, detail) but becomes anonymous.
    Used by Playwright tests and create_test_pos_data (disposable card 3).
    Will also be the basis for the POS "reset card" feature (remove user/wallet from card).

    LOCALISATION : laboutik/utils/test_helpers.py

    SECURITE : refuse de s'executer si DEBUG=False (sera retire quand la feature POS sera implementee).
    / SECURITY: refuses to run if DEBUG=False (will be removed when POS feature is implemented).

    :param tag_id: tag_id de la carte a reset (par defaut DEMO_TAGID_CLIENT3)
    :return: dict avec le resultat du reset
    """
    if not settings.DEBUG:
        logger.warning("reset_carte refuse : DEBUG=False")
        return {"status": "refused", "reason": "DEBUG=False"}

    from QrcodeCashless.models import CarteCashless
    from AuthBillet.models import Wallet

    if tag_id is None:
        tag_id = getattr(settings, "DEMO_TAGID_CLIENT3", "D74B1B5D")

    try:
        carte = CarteCashless.objects.get(tag_id=tag_id)
    except CarteCashless.DoesNotExist:
        logger.info(f"reset_carte : carte {tag_id} introuvable")
        return {"status": "not_found", "tag_id": tag_id}

    resultat = {
        "status": "ok",
        "tag_id": tag_id,
        "user_removed": False,
        "wallet_ephemere_removed": False,
    }

    # 1. Supprimer le lien user (sans supprimer le TibilletUser)
    # / 1. Remove user link (without deleting the TibilletUser)
    if carte.user is not None:
        ancien_email = carte.user.email
        carte.user = None
        resultat["user_removed"] = True
        resultat["ancien_email"] = ancien_email
        logger.info(f"reset_carte : user {ancien_email} detache de {tag_id}")

    # 2. Supprimer le wallet ephemere (supprimer l'objet Wallet + les tokens)
    #    Il faut d'abord supprimer les objets qui referencent ce wallet
    #    (Transaction.sender/receiver et LigneArticle.wallet sont PROTECT).
    # / 2. Remove ephemeral wallet (delete the Wallet object + tokens)
    #    Must first delete objects referencing this wallet
    #    (Transaction.sender/receiver and LigneArticle.wallet are PROTECT).
    if hasattr(carte, 'wallet_ephemere') and carte.wallet_ephemere is not None:
        wallet_eph = carte.wallet_ephemere
        carte.wallet_ephemere = None
        carte.save()

        # Supprimer les transactions liees au wallet ephemere (sender ou receiver)
        # / Delete transactions linked to the ephemeral wallet (sender or receiver)
        from fedow_core.models import Token, Transaction
        nb_tx = Transaction.objects.filter(sender=wallet_eph).delete()[0]
        nb_tx += Transaction.objects.filter(receiver=wallet_eph).delete()[0]

        # Supprimer les lignes d'article liees au wallet ephemere
        # / Delete article lines linked to the ephemeral wallet
        from BaseBillet.models import LigneArticle
        nb_lignes = LigneArticle.objects.filter(wallet=wallet_eph).delete()[0]

        # Supprimer les tokens du wallet ephemere
        # / Delete tokens from ephemeral wallet
        nb_tokens_supprimes = Token.objects.filter(wallet=wallet_eph).delete()[0]

        wallet_eph.delete()
        resultat["wallet_ephemere_removed"] = True
        resultat["tokens_supprimes"] = nb_tokens_supprimes
        logger.info(f"reset_carte : wallet ephemere supprime ({nb_tokens_supprimes} tokens)")
    else:
        carte.save()

    return resultat
