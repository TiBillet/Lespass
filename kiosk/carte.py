"""
kiosk/carte.py — Lecture d'une carte NFC pour l'affichage de la borne.
/ Reading an NFC card for the kiosk display.

LOCALISATION : kiosk/carte.py

La borne parle au Fedow DISTANT (coexistence V1), jamais a fedow_core.
Ce fichier transforme la reponse de Fedow en un petit dictionnaire simple,
que les templates affichent tel quel.
/ The kiosk talks to the REMOTE Fedow (V1 coexistence), never to fedow_core.
This file turns Fedow's answer into a small plain dict for the templates.

UTILISE PAR :
- kiosk/views.py : check_request_card, recapitulatif
- kiosk/validators.py : RefillWisePoseValidator (solde avant recharge)
"""

from fedow_connect.fedow_api import FedowAPI
from fedow_public.models import AssetFedowPublic
from QrcodeCashless.models import CarteCashless


# Les jetons qui valent des euros : la monnaie locale et la monnaie federee.
# Les autres (temps, fidelite, badges, adhesions) ne sont pas un solde.
# / Tokens worth euros: local currency and federated currency.
CATEGORIES_DE_JETONS_EN_EUROS = [
    AssetFedowPublic.TOKEN_LOCAL_FIAT,
    AssetFedowPublic.STRIPE_FED_FIAT,
]


def calculer_le_solde_en_centimes(carte_fedow):
    """
    Additionne les jetons en euros du portefeuille de la carte.
    / Adds up the euro tokens of the card's wallet.

    :param carte_fedow: dict renvoye par FedowAPI().NFCcard.retrieve()
    :return: int, le solde en centimes
    """
    portefeuille = carte_fedow.get("wallet") or {}
    jetons = portefeuille.get("tokens") or []

    solde_en_centimes = 0
    for jeton in jetons:
        categorie_du_jeton = jeton.get("asset_category")
        if categorie_du_jeton in CATEGORIES_DE_JETONS_EN_EUROS:
            solde_en_centimes += int(jeton.get("value") or 0)
    return solde_en_centimes


def lire_la_carte_pour_la_borne(tag_id):
    """
    Lit une carte chez Fedow et renvoie ce que la borne affiche.
    / Reads a card from Fedow and returns what the kiosk displays.

    FLUX :
    1. Fedow connait-il la carte ? (leve CarteInconnueDeFedow sinon)
    2. La copie locale existe-t-elle ? (leve CarteCashless.DoesNotExist sinon)
    3. On calcule le solde en euros et on regarde si la carte est enregistree.

    :param tag_id: str, 8 caracteres hexadecimaux
    :return: dict {tag_id, numero_court, solde_centimes, est_enregistree,
                   carte_locale}
    """
    tag_id_propre = str(tag_id).strip().upper()

    carte_fedow = FedowAPI().NFCcard.retrieve(tag_id_propre)
    carte_locale = CarteCashless.objects.get(tag_id=tag_id_propre)

    solde_en_centimes = calculer_le_solde_en_centimes(carte_fedow)

    # Une carte « ephemere » n'est liee a personne : si elle est perdue,
    # l'argent est perdu. On le signale avec une modale.
    # / An "ephemeral" card belongs to nobody: lost card, lost money.
    carte_est_anonyme = bool(carte_fedow.get("is_wallet_ephemere", False))

    # Le numero imprime sur la carte. On n'en montre que la fin : « ·· 4F2A ».
    # / The number printed on the card. We only show its end.
    numero_imprime = carte_fedow.get("number_printed") or carte_locale.number or ""
    numero_court = str(numero_imprime)[-4:].upper()

    return {
        "tag_id": tag_id_propre,
        "numero_court": numero_court,
        "solde_centimes": solde_en_centimes,
        "est_enregistree": not carte_est_anonyme,
        "carte_locale": carte_locale,
    }
