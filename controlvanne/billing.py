"""
Facturation des tirages de bière via fedow_core.
/ Billing for beer pours via fedow_core.

LOCALISATION : controlvanne/billing.py

Ce module encapsule la logique de facturation spécifique à la tireuse.
Le ViewSet appelle ces fonctions — séparation ViewSet / logique métier.
/ This module encapsulates tap-specific billing logic.
The ViewSet calls these functions — separation of ViewSet / business logic.

Cascade fiduciaire : même ordre que LaBoutik — TNF → TLF → FED (Fedow local), puis le
reste sur l'ancien Fedow (TLF fédérés puis FED), pour une carte d'utilisateur dans un
lieu relié. Temps et fidélité ne paient jamais un tirage.
/ Fiduciary cascade: same order as LaBoutik — TNF → TLF → FED (local Fedow), then the
remainder on the old Fedow (user card, linked venue). Time and loyalty never pay.

Dépendances :
- fedow_core.services : AssetService, WalletService, TransactionService
- fedow_core.models : Asset, Token, Transaction
- BaseBillet.models : LigneArticle, ProductSold, PriceSold, SaleOrigin
- inventaire.services : StockService
- QrcodeCashless.models : CarteCashless
- laboutik.views : ORDRE_CASCADE_FIDUCIAIRE, MAPPING_ASSET_CATEGORY_PAYMENT_METHOD,
  _obtenir_ou_creer_wallet, _taux_tva_de_la_ligne_de_caisse, lire_depensable_fed_frais,
  _debiter_legacy (ancien Fedow ; importés au moment de l'appel)
"""

import logging
import uuid as uuid_module
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

from django.db import connection, transaction

logger = logging.getLogger(__name__)

def obtenir_contexte_cashless(carte):
    """
    Résout le wallet client et la cascade d'assets fiduciaires pour un paiement tireuse.
    / Resolves the client wallet and fiduciary asset cascade for a tap payment.

    Même logique que LaBoutik : cascade TNF → TLF → FED via AssetService.
    / Same logic as LaBoutik: TNF → TLF → FED cascade via AssetService.

    :param carte: CarteCashless
    :return: dict avec wallet_client, cascade_assets (liste ordonnée).
             None si aucun asset OU si le wallet de la carte n'est pas
             résoluble (carte vierge inconnue du Fedow legacy) — le POS
             tireuse refuse alors proprement au lieu de renvoyer un 500.
             / None if no asset OR if the card wallet cannot be resolved
             (blank card unknown to legacy Fedow) — the tap POS then
             refuses cleanly instead of returning a 500.
    """
    from laboutik.views import ORDRE_CASCADE_FIDUCIAIRE, _obtenir_ou_creer_wallet
    from fedow_core.models import Asset
    from fedow_core.services import AssetService

    # --- Résoudre le wallet du client ---
    # déléguer à laboutik (logique identique, source unique)
    # PIÈGE (fix review 2026-07-06, finding C3) : _obtenir_ou_creer_wallet
    # LÈVE une Exception si la carte n'a ni user.wallet, ni wallet_ephemere,
    # et n'est pas résoluble via le Fedow legacy (can_fedow False ou carte
    # inconnue). Une carte sans wallet n'a de toute façon aucun token :
    # on transforme l'exception en refus propre (None → authorized: false).
    # / TRAP: _obtenir_ou_creer_wallet RAISES if the card has no user.wallet,
    # no wallet_ephemere, and cannot be resolved via legacy Fedow. A card
    # without a wallet has no tokens anyway: turn the exception into a clean
    # refusal (None → authorized: false).
    try:
        wallet_client = _obtenir_ou_creer_wallet(carte)
    except Exception as erreur:
        logger.warning(
            f"Tireuse : wallet non résoluble pour la carte {carte.tag_id} "
            f"— refus propre. Détail : {erreur}"
        )
        return None

    # --- Construire la cascade d'assets accessibles ---
    # / Build the cascade of accessible assets
    # Même logique que LaBoutik Phase 1 : tous les assets du tenant + fédérés.
    # / Same logic as LaBoutik Phase 1: all tenant assets + federated.
    assets_accessibles = AssetService.obtenir_assets_accessibles(connection.tenant)

    cascade_assets = []
    for categorie in ORDRE_CASCADE_FIDUCIAIRE:
        asset = assets_accessibles.filter(category=categorie).first()
        if asset is not None:
            cascade_assets.append(asset)

    if not cascade_assets:
        logger.warning(
            f"Aucun asset fiduciaire (TNF/TLF/FED) pour le tenant {connection.tenant.name}"
        )
        return None

    return {
        "wallet_client": wallet_client,
        "cascade_assets": cascade_assets,
    }


# ──────────────────────────────────────────────────────────────────────
# Calculs d'argent communs à la facture et à l'écran du kiosk
# / Money computations shared by the bill and the kiosk screen
# ──────────────────────────────────────────────────────────────────────
#
# Une seule formule pour le montant facturé ET le montant affiché : l'écran ne
# peut plus annoncer un centime de différence avec ce qui est débité. Le JS du
# kiosk (ecran_tireuse.js) ne calcule plus rien : il écrit ces valeurs.
# (audit 2026-09-26, point 2.3)
# / One formula for the billed AND displayed amount; the kiosk JS only writes.

# Volume d'un « verre » pour « soit N verres » (25 cl)
# / Glass volume for "N glasses" (25 cl)
VOLUME_D_UN_VERRE_ML = Decimal("250")


def calculer_litres_du_volume(volume_ml):
    """
    Un volume en litres, arrondi à 3 décimales (au millilitre, demi-haut). Pour le
    volume facturé d'un tirage, c'est la quantité (`qty`) de sa ligne, et la quantité
    sur laquelle le montant est calculé.
    / A volume in litres, rounded to 3 decimals: for a pour's billed volume, the line's
    quantity and the quantity the amount is computed on.

    Exemple : 333,7 ml → 0,334 L.

    :param volume_ml: Decimal, float ou str — volume en ml
    :return: Decimal à 3 décimales
    """
    volume_en_ml = Decimal(str(volume_ml))
    litres_exacts = volume_en_ml / Decimal("1000")
    return litres_exacts.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def calculer_prix_au_litre_en_centimes(prix_litre):
    """
    Le prix au litre en centimes entiers (arrondi demi-haut) : le prix unitaire
    (`amount`) de la ligne du tirage.
    / The price per litre in whole cents: the line's unit price.

    :param prix_litre: Decimal — prix au litre en euros
    :return: int
    """
    from BaseBillet.services_vente import arrondir_au_centime_demi_haut

    return arrondir_au_centime_demi_haut(prix_litre * Decimal("100"))


def calculer_montant_centimes(volume_ml, prix_litre):
    """
    Prix d'un volume servi, en centimes. C'est ce montant qui est facturé, c'est celui
    que l'écran de la tireuse affiche, et c'est le total de la ligne du tirage : les
    trois restent égaux.
    / Price of a served volume, in cents. Billed, displayed, and the line's total: all
    three stay equal.

    LE CALCUL (le même que la formule du service de vente pour la ligne) :
    1. la quantité d'abord : les litres du volume arrondis à 3 décimales
       (`calculer_litres_du_volume`) ;
    2. puis UN seul calcul : prix au litre en centimes × litres, arrondi au centime
       DEMI-HAUT (`arrondir_au_centime_demi_haut`, la règle de tout l'argent du projet).
    Calculer sur le volume exact donnerait parfois un centime de plus ou de moins que
    la ligne, et l'égalité de la vente casserait après le débit des monnaies.
    / Quantity first (litres rounded to 3 decimals), then one half-up computation: the
    same as the sale service's formula for the line, so the sale's equality holds.

    Exemples : 250 ml à 3,50 €/L = 0,250 × 350 = 87,5 → 88 centimes ;
    333,7 ml à 7,50 €/L = 0,334 × 750 = 250,5 → 251.

    :param volume_ml: Decimal, float ou str — volume servi en ml
    :param prix_litre: Decimal — prix au litre en euros
    :return: int — montant en centimes (0 si volume ou prix nul)
    """
    from BaseBillet.services_vente import arrondir_au_centime_demi_haut

    volume_en_ml = Decimal(str(volume_ml))
    if volume_en_ml <= 0 or prix_litre <= 0:
        return 0
    litres_du_volume = calculer_litres_du_volume(volume_en_ml)
    prix_au_litre_en_centimes = calculer_prix_au_litre_en_centimes(prix_litre)
    montant_exact_en_centimes = Decimal(prix_au_litre_en_centimes) * litres_du_volume
    return arrondir_au_centime_demi_haut(montant_exact_en_centimes)


def calculer_nombre_de_verres(solde_centimes, prix_litre):
    """
    Nombre de verres de 25 cl que le solde permet (arrondi vers le bas).
    / Number of 25 cl glasses the balance allows (rounded down).

    Le prix d'un verre est calculé avec la même formule que la facture.
    / The glass price uses the same formula as the bill.

    :param solde_centimes: int — solde en centimes
    :param prix_litre: Decimal — prix au litre en euros
    :return: int, ou None si le prix est nul (pas de nombre de verres à afficher)
    """
    prix_d_un_verre_centimes = calculer_montant_centimes(VOLUME_D_UN_VERRE_ML, prix_litre)
    if prix_d_un_verre_centimes <= 0:
        return None
    return max(0, int(solde_centimes) // prix_d_un_verre_centimes)


def formater_euros(montant_centimes):
    """
    Montant en centimes → texte affichable, au format de la langue active.
    / Amount in cents → displayable text, in the active language format.

    Exemple (fr) : 1410 → « 14,10 € ».

    :param montant_centimes: int
    :return: str
    """
    from django.utils.formats import number_format

    montant_en_euros = Decimal(int(montant_centimes)) / Decimal("100")
    return f"{number_format(montant_en_euros, decimal_pos=2, use_l10n=True)}\u00a0€"


def calculer_solde_total_cascade(wallet_client, cascade_assets):
    """
    Somme les soldes de tous les assets de la cascade pour ce wallet.
    / Sum balances of all cascade assets for this wallet.

    :param wallet_client: Wallet
    :param cascade_assets: liste ordonnée d'Asset (TNF, TLF, FED…)
    :return: int — solde total en centimes
    """
    from fedow_core.services import WalletService

    total = 0
    for asset in cascade_assets:
        total += WalletService.obtenir_solde(wallet_client, asset)
    return total


def lire_le_solde_de_l_ancien_fedow(carte):
    """
    Solde dépensable de la carte sur l'ancien Fedow (TLF fédérés + FED), lu frais.
    / Card's spendable balance on the old Fedow (federated TLF + FED), read fresh.

    LOCALISATION : controlvanne/billing.py

    L'ancien Fedow ne débite que le portefeuille d'un UTILISATEUR : une carte anonyme
    vaut 0, sans aucun appel. Pour une carte d'utilisateur, la lecture passe par
    `lire_depensable_fed_frais` (brique de la caisse) : elle rend « indisponible » si le
    lieu n'est pas relié à l'ancien Fedow ou si le serveur ne répond pas. Indisponible
    vaut 0 : la tireuse continue avec les monnaies locales, jamais de refus pour ça.
    / Anonymous card: 0, no call. User card: fresh read through the register's helper;
    unavailable (venue not linked, server down) counts as 0, never a refusal.

    L'import se fait au moment de l'appel, comme les autres briques de la caisse.
    / Imported at call time, like the other register building blocks.

    :param carte: CarteCashless
    :return: int — solde en centimes (0 si carte anonyme ou ancien Fedow indisponible)
    """
    from laboutik.views import lire_depensable_fed_frais

    carte_sans_utilisateur = carte.user_id is None
    if carte_sans_utilisateur:
        return 0

    solde_distant_en_centimes, ancien_fedow_disponible = lire_depensable_fed_frais(
        carte.user
    )
    if not ancien_fedow_disponible:
        return 0
    return solde_distant_en_centimes


def calculer_solde_de_la_carte(carte, contexte_cashless):
    """
    Solde total de la carte pour la tireuse : monnaies locales (cascade TNF → TLF →
    FED local) + solde de l'ancien Fedow. C'est LA fonction de solde de la tireuse :
    le badge (`authorize`) et l'écran (`_lire_le_solde_de_la_carte`) l'utilisent tous
    les deux, pour dire le même solde.
    / Card total balance for the tap: local currencies + old Fedow. THE tap balance
    function, used by both authorize and the screen, so they show the same balance.

    :param carte: CarteCashless
    :param contexte_cashless: dict retourné par obtenir_contexte_cashless()
    :return: int — solde en centimes
    """
    solde_des_monnaies_locales = calculer_solde_total_cascade(
        contexte_cashless["wallet_client"], contexte_cashless["cascade_assets"]
    )
    solde_de_l_ancien_fedow = lire_le_solde_de_l_ancien_fedow(carte)
    return solde_des_monnaies_locales + solde_de_l_ancien_fedow


def calculer_volume_autorise_ml(
    solde_centimes, prix_litre_decimal, reservoir_disponible_ml
):
    """
    Calcule le volume maximum autorisé en ml depuis le solde wallet.
    / Computes the maximum allowed volume in ml from wallet balance.

    Formule : (solde_centimes / prix_centimes_par_litre) * 1000 ml
    / Formula: (balance_cents / price_cents_per_liter) * 1000 ml

    Arrondi VERS LE BAS au millilitre : la facture porte au plus ce volume
    (`facturer_tirage`), et son montant ne dépasse donc jamais le solde lu au badge.
    Exemple : 87 c à 3,50 €/L = 248,57 ml → 248 ml → 0,248 × 350 = 86,8 → 87 c.
    / Rounded DOWN to the millilitre: the bill carries at most this volume, so its
    amount never exceeds the balance read at the badge.

    :param solde_centimes: int — solde total (tous assets cascade) en centimes
    :param prix_litre_decimal: Decimal — prix au litre en EUR (ex: Decimal("3.50"))
    :param reservoir_disponible_ml: float — volume restant dans la tireuse en ml
    :return: Decimal — volume autorisé en ml (entier de millilitres)
    """
    if prix_litre_decimal <= 0:
        return Decimal("0.00")

    # Prix au litre en centimes, arrondi DEMI-HAUT comme le prix de la ligne du tirage
    # (`calculer_prix_au_litre_en_centimes`) : 3,505 €/L → 351 c/L. Un autre arrondi
    # autoriserait un volume dont la facture dépasse le solde.
    # / Price per litre in cents, rounded half up like the line's price.
    prix_centimes_par_litre = calculer_prix_au_litre_en_centimes(prix_litre_decimal)
    if prix_centimes_par_litre <= 0:
        return Decimal("0.00")

    # Volume max selon le solde / Max volume based on balance
    volume_max_solde_ml = (
        Decimal(str(solde_centimes)) / Decimal(str(prix_centimes_par_litre)) * 1000
    )

    # Limiter au réservoir disponible / Cap at available reservoir
    volume_max_ml = min(volume_max_solde_ml, Decimal(str(reservoir_disponible_ml)))

    volume_max_au_ml_inferieur = volume_max_ml.quantize(Decimal("1"), rounding=ROUND_DOWN)
    return max(Decimal("0"), volume_max_au_ml_inferieur)


def facturer_tirage(
    session, tireuse, carte, volume_ml, contexte_cashless, ip="0.0.0.0"
):
    """
    Facture un tirage de bière : monnaies locales d'abord, puis l'ancien Fedow.
    / Bills a beer pour: local currencies first, then the old Fedow.

    Appelé au pour_end quand le volume final est connu, sous le verrou de la session
    (`_cloturer_session_et_facturer`, qui empêche de facturer deux fois).
    / Called at pour_end, under the session lock (no double billing).

    RÉPARTITION (la même que le cashless de la caisse) : monnaies locales d'abord (Fedow
    local, en cascade : jetons cadeau TNF, puis TLF, puis FED local), puis le reste sur
    l'ancien Fedow (TLF fédérés puis FED). L'ancien Fedow ne sert qu'à une carte
    d'utilisateur dans un lieu relié. Temps et fidélité ne paient jamais un tirage.
    / Split (same as the register's cashless): local currencies first, then the
    remainder on the old Fedow (user card, linked venue only). Never time or loyalty.

    ORDRE DES OPÉRATIONS (le même que la caisse) :
    1. LIRE, sans rien débiter : les soldes des monnaies locales de la cascade, puis le
       solde de l'ancien Fedow (lu frais : il a pu baisser depuis le badge).
    2. RÉPARTIR le montant : monnaies locales dans l'ordre de la cascade, le reste sur
       l'ancien Fedow, plafonné à son solde lu.
    3. DÉBITER L'ANCIEN FEDOW D'ABORD (`_debiter_legacy`, appel réseau ; il débite
       lui-même les TLF fédérés puis le FED, et rend le moyen de chaque transaction).
       Ce débit se fait AVANT le bloc atomique local, donc avant tout verrou de jeton :
       pendant l'appel réseau, les autres ventes cashless du lieu n'attendent pas. Il
       reste sous le verrou de la session (l'appelant), pour ne facturer qu'une fois.
    4. PUIS, dans le bloc atomique : les débits locaux (une Transaction fedow_core par
       monnaie), la vente, et `encaisser_vente` en dernier.
    / Order (same as the register): 1. read local and remote balances, no debit;
    2. split; 3. debit the old Fedow FIRST, before the local atomic block and any token
    lock (still under the session lock); 4. then local debits, the sale, and
    encaisser_vente last.

    LE VOLUME FACTURÉ (Q-H13) : le plus petit du volume servi et du volume autorisé au
    badge (`session.allowed_ml_session`, calculé depuis le solde et arrondi vers le bas
    au millilitre par `calculer_volume_autorise_ml`). Le Raspberry Pi ne contrôle le
    plafond qu'une fois par seconde : le débordement au-delà du volume autorisé n'est
    pas facturé. Le poids pour le stock (`weight_quantity`) et le décrément du stock
    gardent le volume RÉELLEMENT servi : l'inventaire reste juste.
    / Billed volume: the smaller of the served volume and the volume authorised at the
    badge (rounded down to the ml); the overflow is not billed. The stock keeps the
    really served volume.

    LE FILET : l'argent débité ne couvre pas la ligne quand l'ancien Fedow échoue ou que
    son solde a baissé depuis le badge. La bière est servie : la ligne garde son prix,
    et ce qui manque devient un article « Écart d'encaissement — reçu en moins » (D26).
    L'échec du débit distant est journalisé en ERROR (il peut suivre un débit déjà fait
    côté serveur), et UN SEUL avertissement dit le montant non encaissé.
    / Safety net: when the old Fedow fails or its balance dropped, the line keeps its
    price and a "received less" gap item carries the missing money. One warning.

    LE TIRAGE EST UNE VENTE (service de vente, BaseBillet/services_vente.py) :
    1. une `Vente` d'origine TIREUSE, au point de vente de la tireuse, avec la carte et
       son utilisateur comme client (None pour une carte anonyme) ;
    2. UN article (une `LigneArticle`), quel que soit le nombre de monnaies débitées
       (D15) : `qty` = les litres facturés (`calculer_litres_du_volume`), `amount` = le
       prix au litre en centimes, total par la formule du service (le même centime que
       `calculer_montant_centimes`), coût d'achat sur ces litres. La part payée en
       jetons cadeau (LG) va dans `part_en_jetons` : vendue hors TVA (D8 bis). La ligne
       ne porte ni moyen, ni monnaie, ni carte, ni portefeuille (Q-H2) : ils sont dans
       les règlements ;
    3. un règlement par transaction : montant et uuid copiés de la transaction. Locale :
       `fedow_transaction_uuid`. Ancien Fedow : `reference_externe` (la transaction vit
       sur le serveur distant) ;
    3 bis. si les règlements ne couvrent pas la ligne : l'article d'écart « reçu en
       moins » (`ajouter_l_article_d_ecart_d_encaissement`) ;
    4. `encaisser_vente` EN DERNIER : il vérifie les deux égalités, pose le numéro et
       l'empreinte chaînée. Il prend le verrou du lieu jusqu'à la fin de la transaction :
       le débit de l'ancien Fedow (appel réseau) se fait avant, et aucun appel réseau ne
       suit.

    ÉCHEC APRÈS LE DÉBIT DE L'ANCIEN FEDOW
    Le débit de l'ancien Fedow ne s'annule pas avec la base : l'argent pris là-bas reste
    pris. Si le bloc atomique local échoue ensuite, seul le local est annulé (débits
    locaux, articles, vente) :
    - l'encaissement refuse les égalités (`EgaliteDeVenteRompue`) : l'exception n'est
      pas attrapée, la requête répond 500 et Sentry la capte ;
    - un solde local a baissé entre la lecture et le débit (`SoldeInsuffisant`) :
      l'exception remonte à l'appelant (`_cloturer_session_et_facturer`), qui la
      journalise en erreur.
    Dans les deux cas, aucune vente n'est écrite pour l'argent déjà pris sur l'ancien
    Fedow : c'est l'erreur journalisée qui le signale.
    / The pour is a sale: one TIREUSE sale, ONE item (litres × price per litre), one
    payment per debited transaction (local: fedow_transaction_uuid; old Fedow:
    reference_externe), a gap item if money is missing, settled LAST. The old Fedow
    debit is NOT rolled back with the database: if the local block fails afterwards
    (broken equality → 500 + Sentry; SoldeInsuffisant → logged by the caller), only
    the local part is undone and the money taken remotely stays taken.

    :param session: RfidSession — la session de service (porte le volume autorisé)
    :param tireuse: TireuseBec — la tireuse
    :param carte: CarteCashless — la carte NFC du client
    :param volume_ml: Decimal — volume servi en ml
    :param contexte_cashless: dict retourné par obtenir_contexte_cashless()
    :param ip: str — IP du Raspberry Pi
    :return: dict avec transactions, ligne_article, montant_centimes (l'argent
        réellement débité : il s'affiche à l'écran de fin de service). None si rien
        n'est facturé (volume nul, prix nul, aucune monnaie débitée).
    """
    from fedow_core.services import TransactionService, WalletService
    from fedow_core.exceptions import SoldeInsuffisant
    from BaseBillet.models import (
        LigneArticle,
        PaymentMethod,
        ProductSold,
        PriceSold,
        SaleOrigin,
    )
    from BaseBillet.models_vente import Vente
    from BaseBillet.services_vente import (
        ajouter_article,
        ajouter_reglement,
        encaisser_vente,
        ouvrir_vente,
    )

    if volume_ml <= 0:
        return None

    prix_litre = tireuse.prix_litre  # Decimal, EUR
    if prix_litre <= 0:
        logger.warning(
            f"Tireuse {tireuse.nom_tireuse} : prix_litre=0, pas de facturation"
        )
        return None

    # Le volume facturé : le plus petit du volume servi et du volume autorisé au badge
    # (Q-H13). Le débordement au-delà du volume autorisé n'est pas facturé ; le stock,
    # lui, baisse du volume réellement servi (plus bas).
    # / Billed volume: the smaller of the served and the authorised volume (Q-H13).
    volume_servi_ml = Decimal(str(volume_ml))
    volume_autorise_ml = Decimal(str(session.allowed_ml_session))
    volume_facture_ml = min(volume_servi_ml, volume_autorise_ml)
    if volume_facture_ml < volume_servi_ml:
        logger.info(
            f"Débordement non facturé (tireuse={tireuse.nom_tireuse}, "
            f"carte={carte.tag_id}) : servi {volume_servi_ml} ml, autorisé "
            f"{volume_autorise_ml} ml, facturé {volume_facture_ml} ml."
        )

    # Prix des litres facturés, en centimes : même formule que l'écran du kiosk, et
    # même centime que le total de la ligne (la quantité est arrondie d'abord).
    # / Price of the billed litres: same formula as the kiosk screen and the line.
    montant_centimes = calculer_montant_centimes(volume_facture_ml, prix_litre)

    if montant_centimes <= 0:
        return None

    wallet_client = contexte_cashless["wallet_client"]
    cascade_assets = contexte_cashless["cascade_assets"]
    tenant_courant = connection.tenant

    # --- Wallet receveur : wallet du lieu (pas asset.wallet_origin qui peut être erroné) ---
    # Même convention que LaBoutik (WalletService.get_or_create_wallet_tenant).
    # asset.wallet_origin représente le wallet de genèse de l'asset, qui peut
    # accidentellement pointer sur un wallet utilisateur — ce qui ferait s'annuler
    # débit et crédit (solde non décrémenté).
    # / Receiver wallet: venue wallet (not asset.wallet_origin which may be wrong).
    # Same convention as LaBoutik (WalletService.get_or_create_wallet_tenant).
    # asset.wallet_origin is the asset genesis wallet, which may accidentally
    # point to a user wallet — causing debit and credit to cancel out (balance unchanged).
    wallet_lieu = WalletService.get_or_create_wallet_tenant(tenant_courant)

    # 1. LIRE les soldes des monnaies locales et RÉPARTIR, sans rien débiter.
    # Monnaies locales dans l'ordre de la cascade (TNF → TLF → FED local) : chacune
    # prend ce qu'elle peut couvrir. Les débits se font plus bas, dans le bloc
    # atomique, APRÈS le débit de l'ancien Fedow.
    # / 1. READ local balances and SPLIT, no debit yet. Local currencies in cascade
    #   order; the debits happen below, in the atomic block, AFTER the old Fedow debit.
    restant_centimes = montant_centimes
    repartition_sur_les_monnaies_locales = []
    for asset in cascade_assets:
        if restant_centimes <= 0:
            break

        solde_asset = WalletService.obtenir_solde(wallet_client, asset)
        if solde_asset <= 0:
            continue

        montant_asset = min(solde_asset, restant_centimes)
        repartition_sur_les_monnaies_locales.append((asset, montant_asset))
        restant_centimes -= montant_asset

    # Identifiant de paiement du tirage : sur toutes ses lignes, et envoyé à
    # l'ancien Fedow avec le débit (traçabilité tireuse ↔ ancien Fedow).
    # / The pour's payment id: on all its lines, and sent with the old Fedow debit.
    uuid_transaction = uuid_module.uuid4()

    # 1 bis. Le reste sur l'ancien Fedow : LIRE son solde (frais, il a pu baisser depuis le
    # badge), RÉPARTIR (plafonné au solde lu), puis DÉBITER, D'ABORD. C'est un appel
    # réseau : il se fait ICI, avant le bloc atomique local, donc avant tout verrou de
    # jeton (`creer_vente` verrouille les jetons du client ET du lieu) et avant le
    # verrou du lieu pris par `encaisser_vente`. Pendant l'appel, les autres ventes
    # cashless du lieu n'attendent pas. Il reste sous le verrou de la session
    # (l'appelant) : une session n'est facturée qu'une fois.
    # Ce débit ne s'annule pas avec la base : l'argent pris là-bas reste pris.
    # / 1 bis. The remainder on the old Fedow: read (fresh), split (capped), then debit
    #   FIRST. Network call HERE, before the local atomic block: no token lock nor
    #   venue lock is held meanwhile. Still under the session lock (bill once).
    #   It is not rolled back with the database.
    transactions_de_l_ancien_fedow = []
    if restant_centimes > 0:
        solde_de_l_ancien_fedow = lire_le_solde_de_l_ancien_fedow(carte)
        if solde_de_l_ancien_fedow > 0:
            from laboutik.views import _debiter_legacy

            montant_demande_a_l_ancien_fedow = min(
                solde_de_l_ancien_fedow, restant_centimes
            )
            try:
                transactions_de_l_ancien_fedow = _debiter_legacy(
                    carte.user, montant_demande_a_l_ancien_fedow, uuid_transaction
                )
            except Exception as erreur_de_l_ancien_fedow:
                # L'échec peut arriver APRÈS un débit fait côté serveur (réponse
                # perdue) : c'est une ERREUR, avec sa cause, la carte et le montant
                # demandé. La bière est servie : on encaisse les monnaies locales
                # seules ; le montant non encaissé est dit par l'avertissement plus bas.
                # / The failure may follow a server-side debit (lost response): an
                #   ERROR with cause, card and requested amount. Collect locals only;
                #   the warning below gives the uncollected amount.
                logger.error(
                    f"Débit de l'ancien Fedow en échec au pour_end "
                    f"(tireuse={tireuse.nom_tireuse}, carte={carte.tag_id}, "
                    f"demandé {montant_demande_a_l_ancien_fedow} cts ; le serveur a "
                    f"pu débiter quand même) : {erreur_de_l_ancien_fedow}"
                )
                transactions_de_l_ancien_fedow = []

        for transaction_distante in transactions_de_l_ancien_fedow:
            montant_de_la_transaction_distante = transaction_distante[1]
            restant_centimes -= montant_de_la_transaction_distante

    # L'argent réellement débité, toutes monnaies : c'est lui que la réponse et l'écran
    # de fin de service annoncent.
    # / The money really debited, all currencies: announced by the response and screen.
    montant_debite_centimes = montant_centimes - restant_centimes

    if restant_centimes > 0:
        # Montant non couvert : le filet. Le volume facturé ne dépasse jamais le volume
        # autorisé au badge : il manque de l'argent seulement si l'ancien Fedow échoue,
        # ou si un solde a baissé depuis le badge.
        # La bière est déjà servie : on encaisse ce qui a été réellement débité
        # plutôt que d'abandonner toute la facturation (sinon le tirage est offert).
        # La ligne garde le prix des litres facturés ; ce qui manque devient l'article
        # d'écart « reçu en moins », plus bas. C'est le SEUL avertissement du montant
        # non encaissé.
        # / Uncovered amount, the safety net (old Fedow failed or a balance dropped
        # since the badge). Collect what was really debited; the line keeps its price
        # and a "received less" gap item carries the rest. The ONLY warning about it.
        logger.warning(
            f"Solde insuffisant au pour_end (tireuse={tireuse.nom_tireuse}, "
            f"carte={carte.tag_id}) : demande {montant_centimes} cts, "
            f"debite {montant_debite_centimes} cts, "
            f"manque {restant_centimes} cts (non encaissé, écart reçu en moins)."
        )

    rien_a_debiter = (
        not repartition_sur_les_monnaies_locales and not transactions_de_l_ancien_fedow
    )
    if rien_a_debiter:
        # Aucune monnaie à débiter, ni locale ni sur l'ancien Fedow : rien à
        # facturer, rien à enregistrer.
        # / Nothing to debit, local or old Fedow: nothing to bill.
        return None

    # --- Bloc atomique : débits locaux + vente + stock + encaissement ---
    # / Atomic block: local debits + sale + stock + settlement
    with transaction.atomic():

        # 1 ter. Débiter les monnaies locales, selon la répartition lue plus haut. Chaque
        # débit verrouille les jetons (client et lieu) jusqu'à la fin de la
        # transaction. Un solde local qui a baissé depuis la lecture lève
        # `SoldeInsuffisant` : le bloc est annulé, l'appelant journalise l'erreur.
        # / 1 ter. Debit local currencies as split above. Each debit locks the tokens
        #   until commit. A balance lowered since the read raises SoldeInsuffisant.
        transactions_creees = []
        debits_par_asset = []
        for asset, montant_asset in repartition_sur_les_monnaies_locales:
            tx = TransactionService.creer_vente(
                sender_wallet=wallet_client,
                receiver_wallet=wallet_lieu,
                asset=asset,
                montant_en_centimes=montant_asset,
                tenant=tenant_courant,
                card=carte,
                ip=ip,
                comment=(
                    f"Tirage {tireuse.nom_tireuse}: {float(volume_ml):.0f}ml"
                    f" [{asset.category}]"
                ),
            )
            transactions_creees.append(tx)
            debits_par_asset.append((asset, montant_asset))

        # Volume RÉELLEMENT servi, en centilitres, pour weight_quantity et le stock
        # (unité stock = cl) : débordement compris, l'inventaire reste juste.
        # / Really served volume in cl, for weight_quantity and the stock.
        volume_cl = int(round(float(volume_ml) / 10))
        # 2. Snapshots ProductSold / PriceSold
        # / ProductSold / PriceSold snapshots
        produit = tireuse.fut_actif
        # La tireuse facture en euros : un tarif « au litre » en points ou en
        # temps (asset non vide) n'est jamais pris.
        # / The tap bills in euros: a per-litre points/time price is never used.
        prix_obj = produit.prices.filter(poids_mesure=True, asset__isnull=True, archived=False).first()

        # _created et pas _ : « _ » masquerait gettext si on l'importe un jour
        # / _created, not _: "_" would shadow gettext if imported later
        product_sold, _created = ProductSold.objects.get_or_create(
            product=produit,
            event=None,
            defaults={"categorie_article": produit.categorie_article},
        )

        price_sold, _created = PriceSold.objects.get_or_create(
            productsold=product_sold,
            price=prix_obj,
            defaults={"prix": prix_obj.prix},
        )

        # 3. La vente du tirage. Elle naît « en attente » ; elle est encaissée à la fin
        # du bloc, après les articles et les règlements.
        # / 3. The pour's sale, born pending; settled at the end of the block.
        vente = ouvrir_vente(
            origine=SaleOrigin.TIREUSE,
            nature=Vente.Nature.VENTE,
            point_de_vente=tireuse.point_de_vente,
            client=carte.user,
            carte=carte,
        )

        # 4. UN article pour le tirage, quel que soit le nombre de monnaies débitées
        # (D15), écrit par le service de vente :
        # - qty = les litres facturés, arrondis à 3 décimales ; amount = le prix au litre
        #   en centimes. Le service calcule le total (prix × litres, demi-haut) : le
        #   même centime que `montant_centimes` (même quantité, même prix, même arrondi) ;
        # - le coût d'achat porte sur ces litres (le prix d'achat d'un fût est au litre) ;
        # - la part payée en jetons cadeau (débits LG) va dans `part_en_jetons` : vendue
        #   hors TVA (D8 bis), la TVA du fût ne porte que sur le reste ;
        # - ni moyen, ni monnaie, ni carte, ni portefeuille (Q-H2) : les règlements les
        #   portent. Le poids en centilitres reste dans `weight_quantity` (le stock).
        # Pinte de 0,500 L à 8 €/L payée 1 € TNF + 3 € TLF → 1 ligne : qty 0,500,
        # amount 800, total 400, part en jetons 100.
        # / 4. ONE item for the pour (D15): qty = litres billed, amount = price per
        #   litre; cost on the litres; gift-token debits in part_en_jetons; no method,
        #   currency, card or wallet on the line (Q-H2).
        from laboutik.views import (
            MAPPING_ASSET_CATEGORY_PAYMENT_METHOD,
            _taux_tva_de_la_ligne_de_caisse,
        )

        part_payee_en_jetons = 0
        for asset, montant_debite_dans_la_monnaie in debits_par_asset:
            moyen_de_la_monnaie = MAPPING_ASSET_CATEGORY_PAYMENT_METHOD[asset.category]
            if moyen_de_la_monnaie == PaymentMethod.LOCAL_GIFT:
                part_payee_en_jetons += montant_debite_dans_la_monnaie

        litres_factures = calculer_litres_du_volume(volume_facture_ml)
        prix_au_litre_en_centimes = calculer_prix_au_litre_en_centimes(prix_litre)

        # Le taux de TVA : celui du fût (ou le taux par défaut du lieu). Aucun moyen
        # n'est passé : la ligne n'en a pas, et les jetons sont sortis de la TVA par
        # leur part.
        # / VAT rate: the keg's (or the venue default); no method on the line.
        ligne_du_tirage = ajouter_article(
            vente,
            pricesold=price_sold,
            quantite=litres_factures,
            prix_unitaire=prix_au_litre_en_centimes,
            taux_tva=_taux_tva_de_la_ligne_de_caisse(produit, None),
            prix_achat=int(produit.prix_achat),
            part_en_jetons=part_payee_en_jetons,
            sale_origin=SaleOrigin.TIREUSE,
            status=LigneArticle.VALID,
            point_de_vente=tireuse.point_de_vente,
            weight_quantity=volume_cl,
            uuid_transaction=uuid_transaction,
        )

        # 5. Un règlement par transaction fedow_core créée : son montant et son uuid
        # sont COPIÉS de la transaction, jamais recalculés depuis les articles.
        # / 5. One payment per fedow_core transaction, copied from it.
        for transaction_de_la_monnaie in transactions_creees:
            monnaie_debitee = transaction_de_la_monnaie.asset
            ajouter_reglement(
                vente,
                moyen=MAPPING_ASSET_CATEGORY_PAYMENT_METHOD[monnaie_debitee.category],
                montant=transaction_de_la_monnaie.amount,
                asset=monnaie_debitee.uuid,
                carte=carte,
                wallet=wallet_client,
                fedow_transaction_uuid=transaction_de_la_monnaie.uuid,
            )

        # 5 bis. Un règlement par transaction de l'ancien Fedow, copié d'elle. Elle vit
        # sur le serveur distant : son uuid va dans `reference_externe`
        # (`fedow_transaction_uuid` est réservé aux transactions fedow_core locales).
        # / 5 bis. One payment per old Fedow transaction; its uuid in reference_externe.
        for transaction_distante in transactions_de_l_ancien_fedow:
            uuid_de_la_monnaie_distante = transaction_distante[0]
            montant_de_la_transaction_distante = transaction_distante[1]
            moyen_de_la_transaction_distante = transaction_distante[2]
            uuid_de_la_transaction_distante = transaction_distante[3]
            ajouter_reglement(
                vente,
                moyen=moyen_de_la_transaction_distante,
                montant=montant_de_la_transaction_distante,
                asset=uuid_de_la_monnaie_distante,
                carte=carte,
                reference_externe=str(uuid_de_la_transaction_distante),
            )

        # 5 ter. Le filet : les règlements ne couvrent pas la ligne (ancien Fedow en
        # échec, ou solde baissé depuis le badge). La ligne garde le prix des litres
        # facturés ; ce qui manque devient l'article « Écart d'encaissement — reçu en
        # moins » (D26). Un débit ne s'annule pas : c'est l'écart qui fait tenir les
        # deux égalités. Écart = argent débité − total de la ligne ; rien s'il vaut 0.
        # / 5 ter. Safety net: the payments do not cover the line; the missing money
        #   becomes a "received less" gap item (D26), so both equalities hold.
        from BaseBillet.services_vente import ajouter_l_article_d_ecart_d_encaissement

        ecart_en_centimes = montant_debite_centimes - ligne_du_tirage.total_ttc
        ajouter_l_article_d_ecart_d_encaissement(vente, ecart_en_centimes)

        # 6. Session liée à la ligne du tirage (même convention que laboutik).
        # / Session linked to the pour's line (same convention as laboutik).
        session.ligne_article = ligne_du_tirage
        session.save(update_fields=["ligne_article"])

        # 7. Décrémenter le stock inventaire si le produit en a un
        # / Decrement inventory stock if the product has one
        #
        # Pas de stock pour ce fût : rien à faire (cas normal). On le teste
        # avec hasattr, sans try/except qui cacherait les vraies erreurs.
        # Stock présent : on le décrémente dans un SAVEPOINT (atomic imbriqué).
        # Si StockService échoue en base, seul le savepoint est annulé : la
        # facture (transactions, LigneArticle, session) reste valide, et
        # l'erreur est journalisée. Avant, un except/pass SANS savepoint
        # laissait la transaction Postgres cassée : la requête suivante levait
        # une erreur et TOUTE la facture était annulée (audit 2026-09-26, point 2.1).
        # / No stock: nothing to do. Stock: decrement inside a SAVEPOINT, so a
        # stock DB error only rolls back the savepoint; the bill stays valid.
        le_produit_a_un_stock = hasattr(produit, "stock_inventaire")
        if le_produit_a_un_stock:
            from inventaire.services import StockService

            try:
                with transaction.atomic():
                    StockService.decrementer_pour_vente(
                        stock=produit.stock_inventaire,
                        contenance=volume_cl,
                        qty=1,
                        ligne_article=ligne_du_tirage,
                    )

                # Prévenir les caisses LaBoutik du nouveau stock (badge de la tuile),
                # après le commit de la facture. / Notify POS terminals after commit.
                from wsocket.broadcast import broadcast_etat_stock

                stock_du_fut = produit.stock_inventaire
                transaction.on_commit(lambda: broadcast_etat_stock(stock_du_fut))
            except Exception:
                logger.exception(
                    f"Stock non décrémenté pour le tirage (tireuse={tireuse.nom_tireuse}, "
                    f"volume={volume_cl} cl) : la facture est conservée."
                )

        # 8. Encaisser la vente, EN DERNIER : vérifie les deux égalités, pose le numéro
        # et l'empreinte chaînée. Le verrou du lieu est tenu jusqu'à la fin de la
        # transaction : aucun appel réseau après. `EgaliteDeVenteRompue` n'est pas
        # attrapée : le bloc local est annulé (débits locaux, articles, vente), la
        # requête répond 500 et Sentry la capte. Le débit de l'ancien Fedow, fait
        # avant ce bloc, ne s'annule pas : l'argent pris là-bas reste pris, sans vente.
        # / 8. Settle the sale LAST (venue lock held until commit: no network call
        #   after). A broken equality is not caught: the local block rolls back (500,
        #   Sentry); the old Fedow debit made before it stays taken.
        encaisser_vente(vente)

    assets_debites_str = ", ".join(
        f"{tx.asset.category}" for tx in transactions_creees
    ) if transactions_creees else "aucun"

    logger.info(
        f"Facturation cascade: tireuse={tireuse.nom_tireuse} volume={float(volume_ml):.0f}ml "
        f"prix={montant_centimes}cts debite={montant_debite_centimes}cts "
        f"assets=[{assets_debites_str}] "
        f"ancien_fedow={len(transactions_de_l_ancien_fedow)} transaction(s) "
        f"ligne={ligne_du_tirage.uuid}"
    )

    return {
        "transactions": transactions_creees,
        # Compatibilité avec le code existant qui lit ["transaction"]. None quand le
        # tirage est payé entièrement par l'ancien Fedow (aucune transaction locale).
        # / Backward compatibility. None when the old Fedow paid the whole pour.
        "transaction": transactions_creees[0] if transactions_creees else None,
        # La ligne du tirage (une seule) / The pour's line (only one)
        "ligne_article": ligne_du_tirage,
        # L'argent réellement débité : la réponse au Raspberry Pi et l'écran de fin
        # de service l'annoncent (inférieur au prix si le solde manquait).
        # / The money really debited: announced to the Pi and on the end screen.
        "montant_centimes": montant_debite_centimes,
    }
