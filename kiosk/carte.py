"""
kiosk/carte.py — Lecture d'une carte NFC pour l'affichage de la borne.
/ Reading an NFC card for the kiosk display.

LOCALISATION : kiosk/carte.py

Le solde d'une carte vit a DEUX endroits, comme a la caisse V2 :
- le Fedow DISTANT : la monnaie federee (FED) et les anciennes monnaies
  locales (V1). On les lit dans la reponse de FedowAPI().NFCcard.retrieve().
- la base LOCALE (fedow_core) : la monnaie locale du lieu. C'est la que la
  caisse V2 ET la borne creditent (kiosk/credit.py).
Les deux stocks sont separes : on additionne, sans rien compter deux fois.
Ce fichier renvoie un petit dictionnaire simple, que les templates affichent.
/ A card's balance lives in TWO places, like at the V2 POS: remote Fedow
(FED + legacy currencies) and the local fedow_core database (the venue's
local currency, credited by the POS and the kiosk). Disjoint stores: we add.

UTILISE PAR :
- kiosk/views.py : check_request_card, recapitulatif
- kiosk/validators.py : RefillWisePoseValidator (solde avant recharge)
"""

from AuthBillet.models import Wallet
from fedow_connect.fedow_api import FedowAPI
from fedow_core.models import Asset
from fedow_core.services import WalletService
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


# Les categories de jetons LOCAUX (fedow_core) qui valent des euros.
# / LOCAL (fedow_core) token categories worth euros.
CATEGORIES_DE_JETONS_LOCAUX_EN_EUROS = [Asset.TLF, Asset.FED]


def trouver_le_portefeuille_local(carte_locale, uuid_du_portefeuille_fedow):
    """
    Le portefeuille local (fedow_core) de la carte, SANS appel reseau.
    / The card's local wallet, WITHOUT any network call.

    LOCALISATION : kiosk/carte.py

    kiosk/credit.py utilise la version caisse
    (_obtenir_ou_creer_wallet) ; ici on suit le MEME ordre de priorite, pour
    lire le MEME portefeuille que celui qui sera credite.
    / Same priority order as the POS helper, so we read the wallet that gets
    credited.

    Ordre : 1. le portefeuille de l'utilisateur de la carte,
            2. le portefeuille « ephemere » de la carte anonyme,
            3. la copie locale du portefeuille Fedow (meme uuid).

    :return: Wallet, ou None
    """
    if carte_locale.user and carte_locale.user.wallet:
        return carte_locale.user.wallet
    if carte_locale.wallet_ephemere:
        return carte_locale.wallet_ephemere
    if uuid_du_portefeuille_fedow:
        return Wallet.objects.filter(uuid=uuid_du_portefeuille_fedow).first()
    return None


def calculer_le_solde_local_en_centimes(portefeuille_local):
    """
    Additionne les jetons en euros de la base locale (fedow_core).
    / Adds up the euro tokens from the local database.

    :param portefeuille_local: Wallet, ou None
    :return: int, le solde en centimes
    """
    if portefeuille_local is None:
        return 0

    solde_local_en_centimes = 0
    for jeton in WalletService.obtenir_tous_les_soldes(portefeuille_local):
        if jeton.asset.category in CATEGORIES_DE_JETONS_LOCAUX_EN_EUROS:
            solde_local_en_centimes += jeton.value
    return solde_local_en_centimes


def lire_la_carte_pour_la_borne(tag_id):
    """
    Lit une carte chez Fedow et renvoie ce que la borne affiche.
    / Reads a card from Fedow and returns what the kiosk displays.

    FLUX :
    1. Fedow connait-il la carte ? (leve CarteInconnueDeFedow sinon)
    2. La copie locale existe-t-elle ? (leve CarteCashless.DoesNotExist sinon)
    3. On calcule le solde en euros (Fedow distant + base locale) et on
       regarde si la carte est enregistree.

    :param tag_id: str, 8 caracteres hexadecimaux
    :return: dict {tag_id, numero_court, solde_centimes, est_enregistree,
                   carte_locale}
    """
    tag_id_propre = str(tag_id).strip().upper()

    carte_fedow = FedowAPI().NFCcard.retrieve(tag_id_propre)
    carte_locale = CarteCashless.objects.get(tag_id=tag_id_propre)

    # Solde = Fedow distant + base locale (deux stocks separes).
    # / Balance = remote Fedow + local database (two disjoint stores).
    solde_distant_en_centimes = calculer_le_solde_en_centimes(carte_fedow)
    uuid_du_portefeuille_fedow = (carte_fedow.get("wallet") or {}).get("uuid")
    portefeuille_local = trouver_le_portefeuille_local(carte_locale, uuid_du_portefeuille_fedow)
    solde_local_en_centimes = calculer_le_solde_local_en_centimes(portefeuille_local)
    solde_en_centimes = solde_distant_en_centimes + solde_local_en_centimes

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
