"""
Credit de la carte apres un paiement reussi a la borne.
/ Card credit after a successful kiosk payment.

LOCALISATION : kiosk/credit.py

POURQUOI CE FICHIER :
La borne est un module V2. La caisse V2 (LaBoutik) credite les cartes dans la
base locale (fedow_core), pas sur le Fedow distant. La borne fait pareil :
quand Stripe confirme le paiement, on credite la monnaie locale du lieu sur la
carte, avec LES MEMES fonctions que la caisse (laboutik/views.py) :
- _obtenir_ou_creer_wallet : le portefeuille de la carte ;
- _executer_recharges : la transaction de recharge + les lignes de vente.
Avant, on attendait que Stripe previenne le Fedow distant (webhook). Ca ne
marchait ni en local, ni avec la caisse V2 (deux soldes differents).
/ The kiosk is a V2 module: like the V2 POS, it credits the card in the local
database (fedow_core), with the SAME functions as the POS.

APPELE PAR : PaymentsIntent.get_from_stripe (kiosk/models.py), des que le
statut passe a « reussi ». get_from_stripe est le seul passage oblige : tache
Celery (kiosk/tasks.py), sondage de secours (kiosk/views.py:payment_status)
et annulation (annuler_sur_le_terminal) passent tous par lui.
/ Called by PaymentsIntent.get_from_stripe, the single chokepoint.

UNE SEULE FOIS : la tache Celery et le sondage de secours peuvent voir le
succes en meme temps. Le champ PaymentsIntent.carte_creditee_le est pose dans
la MEME transaction que le credit, sous verrou (select_for_update).
/ ONCE ONLY: carte_creditee_le is set in the SAME transaction as the credit,
under a row lock.
"""

import logging

from django.db import connection, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


def trouver_le_produit_de_recharge_de_la_borne():
    """
    Le produit « Recharge euros » de la monnaie locale du lieu.
    / The venue's local currency "Euro top-up" product.

    LOCALISATION : kiosk/credit.py

    Ce produit est cree tout seul par le signal de fedow_core
    (fedow_core/signals.py) quand le lieu cree sa monnaie locale (Asset TLF).
    On prend son tarif « Libre » : la borne accepte n'importe quel montant.
    / Auto-created by the fedow_core signal with the TLF asset. We use its
    "free price" rate: the kiosk accepts any amount.

    :return: (produit, tarif_libre), ou (None, None) si le lieu n'a pas de
             monnaie locale prete / or (None, None) if not set up
    """
    from BaseBillet.models import Product
    from fedow_core.models import Asset

    produit_de_recharge = (
        Product.objects.filter(
            methode_caisse=Product.RECHARGE_EUROS,
            archive=False,
            asset__category=Asset.TLF,
            asset__tenant_origin=connection.tenant,
            asset__active=True,
            asset__archive=False,
        )
        .select_related("asset")
        .order_by("poids", "name")
        .first()
    )
    if produit_de_recharge is None:
        return None, None

    tarif_libre = produit_de_recharge.prices.filter(free_price=True).first()
    if tarif_libre is None:
        return produit_de_recharge, None

    return produit_de_recharge, tarif_libre


def crediter_la_carte_du_paiement(payment_intent_pk):
    """
    Credite la carte du montant paye, UNE seule fois par paiement.
    / Credits the card with the paid amount, ONCE per payment.

    LOCALISATION : kiosk/credit.py

    FLUX :
    1. Relit le paiement. Deja credite, pas reussi ou sans carte : rien a faire.
    2. Trouve le produit de recharge et le portefeuille de la carte (HORS
       transaction : le portefeuille peut demander un appel reseau a Fedow).
    3. Dans une transaction, sous verrou : reverifie, credite via
       _executer_recharges (comme la caisse, paiement « carte bancaire »),
       puis pose carte_creditee_le.

    Ne leve jamais : une erreur est journalisee, le paiement reste « non
    credite » (carte_creditee_le vide), visible dans l'admin.
    / Never raises: errors are logged, the payment stays "not credited".

    :param payment_intent_pk: uuid du PaymentsIntent
    :return: True si la carte vient d'etre creditee, sinon False
    """
    from kiosk.models import PaymentsIntent
    from laboutik.views import _executer_recharges, _obtenir_ou_creer_wallet

    try:
        # 1. Faut-il crediter ? / Is a credit needed?
        paiement = PaymentsIntent.objects.select_related("card").get(pk=payment_intent_pk)
        if paiement.carte_creditee_le is not None:
            return False
        if paiement.status != PaymentsIntent.SUCCEEDED:
            return False
        if paiement.card is None:
            logger.error(f"crediter_la_carte_du_paiement : paiement {paiement.pk} sans carte")
            return False

        # 2. Produit de recharge + portefeuille, hors transaction.
        # / Top-up product + wallet, outside the transaction.
        produit_de_recharge, tarif_libre = trouver_le_produit_de_recharge_de_la_borne()
        if tarif_libre is None:
            logger.error(
                f"crediter_la_carte_du_paiement : pas de produit « Recharge euros » "
                f"avec un tarif libre sur ce lieu. Paiement {paiement.pk} NON credite."
            )
            return False

        carte = paiement.card
        portefeuille_de_la_carte = _obtenir_ou_creer_wallet(carte)

        # 3. Credit, sous verrou. / Credit, under lock.
        with transaction.atomic():
            paiement_verrouille = PaymentsIntent.objects.select_for_update().get(pk=paiement.pk)

            # Un autre processus (Celery / sondage) a pu crediter entre-temps.
            # / Another process may have credited in the meantime.
            if paiement_verrouille.carte_creditee_le is not None:
                return False

            # Meme format de panier que la caisse (laboutik/views.py).
            # / Same cart format as the POS.
            article_de_recharge = {
                "product": produit_de_recharge,
                "price": tarif_libre,
                "quantite": 1,
                "prix_centimes": paiement_verrouille.amount,
            }
            _executer_recharges(
                articles_panier=[article_de_recharge],
                wallet_client=portefeuille_de_la_carte,
                carte_client=carte,
                code_methode_paiement="carte_bancaire",
                ip_client=None,
            )

            paiement_verrouille.carte_creditee_le = timezone.now()
            paiement_verrouille.save(update_fields=["carte_creditee_le"])

        logger.info(
            f"crediter_la_carte_du_paiement : carte {carte.tag_id} creditee de "
            f"{paiement.amount} centimes (paiement {paiement.pk})"
        )
        return True

    except Exception as erreur_de_credit:
        logger.error(
            f"crediter_la_carte_du_paiement : echec du credit pour le paiement "
            f"{payment_intent_pk} : {erreur_de_credit}"
        )
        return False
