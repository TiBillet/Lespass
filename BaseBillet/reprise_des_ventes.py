"""
La reprise des ventes existantes : le CALCUL du plan, sans aucune écriture.
/ Takeover of existing sales: the plan COMPUTATION, without any write.

LOCALISATION : BaseBillet/reprise_des_ventes.py

LE BESOIN
Les anciennes lignes d'article (`LigneArticle`), écrites par l'ancien code, n'ont ni
vente, ni règlement, ni montants entiers. La reprise leur donne tout cela, une fois, la
nuit de la mise en production. Ce module ne fait que le calcul : pour le lieu courant,
il lit les anciennes lignes et les paiements Stripe, et il construit EN MÉMOIRE la liste
des ventes à créer. Il n'écrit rien en base, il n'appelle ni Stripe, ni Fedow, ni
Celery. L'écriture du plan, sans le recalculer, est une autre étape.
/ Builds in memory the list of sales to create for the current venue. Writes nothing,
calls no network service, no Celery task.

QUI L'APPELLE
`comptabilite/management/commands/reprendre_les_ventes_existantes.py` (le passage à
blanc), une fois par lieu, dans le `tenant_context` du lieu.
/ Called by the dry-run command, once per venue, inside the venue's tenant_context.

LES FORMES REPRISES
Seulement celles qui existent en production (comptées sur la copie : fiche R §14). Toute
autre forme devient l'anomalie « forme non prévue » : son groupe n'est pas dans le plan,
et le mainteneur décide quoi en faire s'il la voit au passage à blanc.
/ Only the shapes found in production; any other shape is a "forme non prévue" anomaly.

FLUX DE `calculer_le_plan_de_reprise`
1. Lire les catégories des monnaies (`fedow_public`) et les anciennes lignes sans vente.
2. Regrouper les lignes : une vente = un encaissement d'origine (fiche R §4).
3. Pour chaque groupe : vérifier sa forme, puis calculer sa nature, son statut, sa date,
   son client, les montants de chaque article (la formule unique
   `calculer_montants_article`) et ses règlements.
4. Chaque paiement Stripe `T` sans ligne devient une vente « virement reçu » (QO-9).
5. Compter les paiements Stripe sans ligne, et trier les ventes dans l'ordre du temps.
/ Read, group, compute each group, add the T payments, count, sort.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-R-reprise-ventes.md (§3 à
§10, §14, §17) ; décisions du SUIVI §4-§5 ; brief CHANTIER-05-briefs/05-R-1.md.
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from datetime import timezone as fuseau_horaire
from decimal import Decimal

from BaseBillet.models import LigneArticle, Paiement_stripe, PaymentMethod, Product
from BaseBillet.models_vente import Vente
from BaseBillet.services_vente import (
    METHODES_CAISSE_HORS_CHIFFRE_AFFAIRES,
    calculer_montants_article,
)
from fedow_public.models import AssetFedowPublic

# --------------------------------------------------------------------------
# Les types d'anomalie et d'information du rapport (textes, sans donnée personnelle)
# / The report's anomaly and information types (texts, no personal data)
# --------------------------------------------------------------------------

# Groupe non écrit : une forme que la production n'a pas.
# / Group not written: a shape production does not have.
ANOMALIE_FORME_NON_PREVUE = "forme non prévue"
# Groupe non écrit : des lignes payées et non payées dans une même vente hors Stripe.
# / Group not written: paid and unpaid lines in the same non-Stripe sale.
ANOMALIE_STATUTS_MELANGES = "statuts mélangés dans un groupe"
# Signalée, la reprise continue : l'avoir est repris sans vente liée (Q-R14).
# / Reported, the takeover goes on: the credit note is taken without its origin.
ANOMALIE_ORIGINE_D_AVOIR_INTROUVABLE = "origine d'avoir introuvable"
# Signalée, la reprise continue : la recharge est reprise en euros (Q-R19).
# / Reported, the takeover goes on: the top-up is taken in euros.
ANOMALIE_MONNAIE_DE_RECHARGE_INTROUVABLE = "monnaie de recharge introuvable"
# Paiement `T` non écrit : son message Stripe ne donne ni montant ni date lisibles.
# / T payment not written: its Stripe message gives no readable amount or date.
ANOMALIE_VIREMENT_RECU_ILLISIBLE = "virement reçu illisible"
# Paiement `T` non écrit : la monnaie FED n'existe pas dans `fedow_public`.
# / T payment not written: no FED currency in fedow_public.
ANOMALIE_MONNAIE_FED_INTROUVABLE = "monnaie FED introuvable"
# Information seulement : les quantités des parts d'un paiement QR ne font pas 1.
# / Information only: the quantities of a QR payment's parts do not add up to 1.
INFORMATION_QUANTITES_QR_HORS_BORNES = (
    "paiement QR dont la somme des quantités sort de [0,99 ; 1,01]"
)

# --------------------------------------------------------------------------
# Les formes de la production (fiche R §3 et §14)
# / Production shapes
# --------------------------------------------------------------------------

# Les quatre règles de regroupement, appliquées dans cet ordre (fiche R §4).
# / The four grouping rules, applied in this order.
REGLE_AVOIR = "avoir"
REGLE_PAIEMENT_QR = "paiement QR / NFC"
REGLE_PAIEMENT_STRIPE = "paiement Stripe"
REGLE_LIGNE_SEULE = "ligne seule"

# Les origines d'un paiement QR / NFC : ses parts partagent le même texte `metadata`.
# / QR / NFC payment origins: their parts share the same metadata text.
ORIGINES_QR = ["QR", "NF"]

# Les moyens vus sur les lignes de la production (R-0, tableau A), plus « vide ». Un
# autre moyen (jetons cadeau `LG`, points ou temps `NM`…) est une forme non prévue.
# / Payment methods seen in production (plus empty). Any other is an unexpected shape.
MOYENS_VUS_EN_PRODUCTION = [
    None,
    "",
    PaymentMethod.UNKNOWN,
    PaymentMethod.FREE,
    PaymentMethod.CC,
    PaymentMethod.CASH,
    PaymentMethod.CHEQUE,
    PaymentMethod.QRCODE_MA,
    PaymentMethod.TRANSFER,
    PaymentMethod.STRIPE_FED,
    PaymentMethod.STRIPE_NOFED,
    PaymentMethod.STRIPE_SEPA_NOFED,
    PaymentMethod.STRIPE_RECURENT,
    PaymentMethod.LOCAL_EURO,
]

# Les moyens acceptés sur une ligne reliée à un paiement Stripe (vide = Stripe carte).
# / Methods accepted on a line linked to a Stripe payment (empty = Stripe card).
MOYENS_D_UNE_LIGNE_STRIPE = [
    None,
    "",
    PaymentMethod.STRIPE_NOFED,
    PaymentMethod.STRIPE_SEPA_NOFED,
    PaymentMethod.STRIPE_RECURENT,
]

# Les moyens d'une ligne dont la quantité non entière, hors QR, en fait une part (QO-12).
# / Methods that make a non-integer line a part, outside QR (QO-12).
MOYENS_D_UNE_PART = [PaymentMethod.LOCAL_EURO, PaymentMethod.STRIPE_FED]

# Statuts de ligne : payée (vente réglée) ou jamais payée (vente annulée).
# / Line statuses: paid (settled sale) or never paid (cancelled sale).
STATUTS_DE_LIGNE_PAYEE = [LigneArticle.VALID, LigneArticle.PAID, LigneArticle.FREERES]
STATUTS_DE_LIGNE_NON_PAYEE = [
    LigneArticle.CREATED,
    LigneArticle.CANCELED,
    LigneArticle.FAILED,
    LigneArticle.UNPAID,
]
# Les seuls statuts acceptés sur une ligne d'un paiement Stripe non payé (W, E).
# / The only statuses accepted on a line of an unpaid Stripe payment.
STATUTS_DE_LIGNE_D_UN_PAIEMENT_NON_PAYE = [LigneArticle.UNPAID, LigneArticle.CREATED]
# Les statuts d'une ligne d'avoir : avoir admin (N) ou remboursement Stripe (R).
# / Credit-note line statuses: admin credit note or Stripe refund.
STATUTS_DE_LIGNE_D_AVOIR = [LigneArticle.CREDIT_NOTE, LigneArticle.REFUNDED]

# Statuts de paiement Stripe vus en production (R-0 §14 ligne 5). Les autres
# (N, O, S, F, C, H) sont des formes non prévues.
# / Stripe payment statuses seen in production. Others are unexpected shapes.
STATUTS_DE_PAIEMENT_PAYE = [
    Paiement_stripe.VALID,
    Paiement_stripe.PAID,
    Paiement_stripe.REFUNDED,
]
STATUTS_DE_PAIEMENT_NON_PAYE = [Paiement_stripe.PENDING, Paiement_stripe.EXPIRE]

# Un paiement en cours (W) commandé depuis moins longtemps reste en attente : le
# webhook l'encaissera après la bascule (Q-R8). Plus vieux : annulé.
# / A pending payment ordered more recently stays pending; older: cancelled.
AGE_MAXIMUM_D_UN_PAIEMENT_EN_ATTENTE = timedelta(days=30)

# Les produits de recharge : leur monnaie est relue dans `fedow_public`.
# / Top-up products: their currency is read in fedow_public.
CATEGORIES_DE_RECHARGE = [Product.RECHARGE_CASHLESS, Product.RECHARGE_CASHLESS_FED]
METHODES_CAISSE_DE_RECHARGE = [
    Product.RECHARGE_EUROS,
    Product.RECHARGE_CADEAU,
    Product.RECHARGE_TEMPS,
]
# Une recharge en temps ou en points n'existe pas en production : forme non prévue.
# / A time or points top-up does not exist in production: unexpected shape.
CATEGORIES_DE_MONNAIE_HORS_EUROS = [AssetFedowPublic.TIME, AssetFedowPublic.FIDELITY]

# Bornes de la somme des quantités des parts d'un paiement QR (`dround` à 2 décimales).
# / Bounds of the sum of a QR payment's part quantities.
SOMME_MINIMUM_DES_QUANTITES_QR = Decimal("0.99")
SOMME_MAXIMUM_DES_QUANTITES_QR = Decimal("1.01")

# La seule unité des ventes reprises (Q-R11 ; temps et points : forme non prévue).
# / The only unit of the sales taken over.
UNITE_DES_VENTES_REPRISES = "EUR"

# La référence des règlements d'un ancien avoir relié à un paiement Stripe (Q-R6) : le
# rapport ne les compte pas « remboursements Stripe à faire à la main ».
# / Reference of an old credit note's Stripe payment, so reports skip it.
REFERENCE_D_UN_AVOIR_REPRIS = "reprise"


# --------------------------------------------------------------------------
# Le plan : ce que l'écriture recevra, sans rien recalculer
# / The plan: what the writing step receives, without recomputing anything
# --------------------------------------------------------------------------


@dataclass
class ArticleAReprendre:
    """
    Un article d'une vente reprise : une ancienne ligne et ses montants entiers, ou un
    article à créer (virement reçu, `ligne` vide).
    / An item of a sale taken over: an old line and its amounts, or an item to create.
    """

    # L'ancienne ligne, rattachée à la vente par `.update()`. Vide : article à créer.
    # / The old line. Empty: an item to create.
    ligne: LigneArticle | None
    # "VR" pour l'article d'un virement reçu : son produit est celui de
    # `get_or_create_product_virement_recu` (BaseBillet/services_refund.py).
    # / "VR" for a received transfer item.
    methode_caisse_du_produit_a_creer: str | None
    quantite: Decimal
    prix_unitaire: int
    taux_tva: Decimal
    asset: uuid.UUID | None
    total_catalogue: int
    part_offerte: int
    source_offert: str
    part_en_jetons: int
    total_ttc: int
    total_ht: int
    total_tva: int
    hors_chiffre_affaires: bool
    # Vrai pour une part QR / NFC (et les lignes de QO-12) : son argent est `amount`.
    # / True for a QR / NFC part: its money is its amount.
    part_qr: bool


@dataclass
class ReglementAReprendre:
    """
    Un règlement d'une vente reprise. Carte et portefeuille sont ceux de toutes les
    lignes du couple (moyen, monnaie) quand elles ont les mêmes, sinon vides.
    / A payment of a sale taken over.
    """

    moyen: str
    montant: int
    asset: uuid.UUID | None
    carte_id: int | None
    wallet_id: uuid.UUID | None
    paiement_stripe: Paiement_stripe | None
    reference_externe: str


@dataclass
class VenteAReprendre:
    """
    Une vente à écrire. `cle_du_groupe` devient `Vente.idempotency_key =
    "reprise-<clé>"` : elle rend la reprise rejouable.
    / A sale to write; its group key becomes its idempotency key.
    """

    cle_du_groupe: str
    nature: str
    statut: str
    unite: str
    datetime_de_la_vente: datetime
    client: object
    # Le paiement Stripe dont cette vente est la vente d'origine
    # (`Paiement_stripe.vente`). Un avoir n'en a pas : ses règlements portent le
    # paiement qu'ils remboursent.
    # / The Stripe payment whose original sale this is. A credit note has none.
    paiement_stripe: Paiement_stripe | None
    # À poser sur le paiement Stripe d'une vente réglée (B-3, Q-R4). Vide : rien.
    # / To set on the Stripe payment of a settled sale. Empty: nothing.
    moyen_du_paiement_stripe: str | None
    montant_encaisse_du_paiement_stripe: int | None
    # La ligne vendue que cet avoir annule (Q-R14), et s'il faut poser
    # `credit_note_for` sur la ligne d'avoir (vrai quand l'origine vient de `metadata`).
    # / The sold line this credit note cancels, and whether to set credit_note_for.
    uuid_de_la_ligne_d_origine: uuid.UUID | None
    credit_note_for_a_poser: bool
    articles: list = field(default_factory=list)
    reglements: list = field(default_factory=list)


@dataclass
class PlanDeReprise:
    """
    Le plan de reprise d'un lieu, et les nombres de son rapport.
    / The takeover plan of one venue, and its report's numbers.
    """

    ventes: list = field(default_factory=list)
    # {type d'anomalie : nombre de lignes} (ou de paiements `T`).
    # / {anomaly type: number of lines}.
    anomalies: dict = field(default_factory=dict)
    # {type d'information : nombre de groupes}. Aucun effet sur le plan.
    # / {information type: number of groups}. No effect on the plan.
    informations: dict = field(default_factory=dict)
    nombre_de_lignes_lues: int = 0
    nombre_de_paiements_stripe_sans_ligne: int = 0
    # Hors parts QR, sur les anciennes lignes reprises : l'ancien calcul
    # (Σ amount × qty, exact) et le nouveau total catalogue. Ils doivent être égaux.
    # / Off QR parts: old computation and new catalogue total. They must be equal.
    total_ancien_calcul_hors_parts_qr: Decimal = Decimal("0")
    total_catalogue_hors_parts_qr: int = 0
    # Sur tous les articles du plan. / On every plan item.
    total_ttc: int = 0
    total_part_offerte: int = 0


@dataclass
class GroupeDeLignes:
    """Les anciennes lignes d'une même vente, et la règle qui les a réunies.
    / The old lines of one sale, and the rule that grouped them."""

    regle: str
    lignes: list


# --------------------------------------------------------------------------
# Le point d'entrée
# / Entry point
# --------------------------------------------------------------------------


def calculer_le_plan_de_reprise(moment_de_la_reprise):
    """
    Calcule le plan de reprise du lieu courant. N'écrit rien.
    / Computes the takeover plan of the current venue. Writes nothing.

    LOCALISATION : BaseBillet/reprise_des_ventes.py

    :param moment_de_la_reprise: datetime avec fuseau ; l'âge d'un paiement en cours
        (`order_date`) se compte depuis ce moment
    :return: un `PlanDeReprise`
    """
    plan = PlanDeReprise()

    # 1. Les catégories des monnaies, lues une fois : {uuid : catégorie}.
    # / 1. Currency categories, read once.
    categories_des_monnaies = {}
    for uuid_de_la_monnaie, categorie in AssetFedowPublic.objects.values_list(
        "uuid", "category"
    ):
        categories_des_monnaies[uuid_de_la_monnaie] = categorie

    # Les anciennes lignes : celles qui n'ont pas encore de vente. `select_related`
    # évite une requête par ligne (un lieu a jusqu'à 4 164 lignes).
    # / Old lines: those without a sale yet. select_related avoids one query per line.
    anciennes_lignes = list(
        LigneArticle.objects.filter(vente__isnull=True)
        .select_related(
            "pricesold__productsold__product",
            "paiement_stripe__user",
            "reservation__user_commande",
            "membership__user",
            "credit_note_for",
        )
        .order_by("datetime", "uuid")
    )
    plan.nombre_de_lignes_lues = len(anciennes_lignes)

    # 2. Le regroupement. / 2. Grouping.
    groupes_par_cle = _regrouper_les_lignes(anciennes_lignes)

    # Les lignes d'origine des remboursements, lues en une requête.
    # / The refunds' origin lines, read in one query.
    origines_lues_dans_metadata = _lire_les_origines_ecrites_dans_metadata(
        groupes_par_cle
    )

    # 3. Chaque groupe. / 3. Each group.
    for cle_du_groupe, groupe in groupes_par_cle.items():
        _reprendre_un_groupe(
            plan,
            cle_du_groupe,
            groupe,
            moment_de_la_reprise,
            categories_des_monnaies,
            origines_lues_dans_metadata,
        )

    # 4. Les paiements `T` sans ligne. / 4. T payments without lines.
    _reprendre_les_virements_recus(plan, categories_des_monnaies)

    # 5. Les paiements sans ligne, hors `T` validés : aucune vente, comptés seulement.
    # / 5. Payments without lines, except validated T: no sale, counted only.
    plan.nombre_de_paiements_stripe_sans_ligne = (
        Paiement_stripe.objects.filter(lignearticles__isnull=True)
        .exclude(source=Paiement_stripe.TRANSFERT, status=Paiement_stripe.VALID)
        .count()
    )

    # Ordre du temps ; à date égale, un avoir passe après la vente.
    # / Chronological order; at the same date, a credit note comes after the sale.
    plan.ventes.sort(key=_cle_de_tri_chronologique)
    return plan


def _cle_de_tri_chronologique(vente_a_reprendre):
    """Date, puis l'avoir après la vente, puis la clé (ordre stable).
    / Date, then credit note after sale, then key (stable order)."""
    rang_de_la_nature = 0
    if vente_a_reprendre.nature == Vente.Nature.AVOIR:
        rang_de_la_nature = 1
    return (
        vente_a_reprendre.datetime_de_la_vente,
        rang_de_la_nature,
        vente_a_reprendre.cle_du_groupe,
    )


def _compter(dictionnaire_des_nombres, type_a_compter, nombre):
    """Ajoute `nombre` au compteur `type_a_compter`.
    / Adds `nombre` to the `type_a_compter` counter."""
    nombre_deja_compte = dictionnaire_des_nombres.get(type_a_compter, 0)
    dictionnaire_des_nombres[type_a_compter] = nombre_deja_compte + nombre


# --------------------------------------------------------------------------
# 2. Le regroupement (fiche R §4)
# / Grouping
# --------------------------------------------------------------------------


def _regrouper_les_lignes(anciennes_lignes):
    """
    Range chaque ancienne ligne dans UN groupe, par la première règle qui la prend :
    1. avoir : une vente AVOIR par ligne (clé : uuid de la ligne) ;
    2. origine QR / NFC : une vente par texte `metadata` identique (clé : le plus
       petit uuid des parts) ;
    3. paiement Stripe posé : une vente par paiement (clé : uuid du paiement) ;
    4. toute autre ligne : une vente par ligne (clé : uuid de la ligne).
    / Puts each old line in ONE group, by the first rule that takes it.

    La règle 1 passe AVANT la règle 3 : l'ancien code recopiait `paiement_stripe` sur
    les lignes négatives. Sans cet ordre, un remboursement tomberait dans la vente
    d'origine.
    / Rule 1 runs BEFORE rule 3: the old code copied paiement_stripe onto refunds.

    :return: {clé du groupe (texte) : GroupeDeLignes}
    """
    groupes_par_cle = {}
    parts_qr_par_texte_de_metadata = {}

    for ligne in anciennes_lignes:
        if _ligne_est_un_avoir(ligne):
            groupes_par_cle[str(ligne.uuid)] = GroupeDeLignes(
                regle=REGLE_AVOIR, lignes=[ligne]
            )
        elif ligne.sale_origin in ORIGINES_QR:
            # Une part sans `metadata` ne peut être réunie à aucune autre : elle forme
            # son propre paiement.
            # / A part without metadata cannot be matched: it is its own payment.
            texte_de_la_metadata = _texte_de_la_metadata(ligne.metadata)
            if not texte_de_la_metadata:
                texte_de_la_metadata = str(ligne.uuid)
            if texte_de_la_metadata not in parts_qr_par_texte_de_metadata:
                parts_qr_par_texte_de_metadata[texte_de_la_metadata] = []
            parts_qr_par_texte_de_metadata[texte_de_la_metadata].append(ligne)
        elif ligne.paiement_stripe_id is not None:
            cle_du_paiement = str(ligne.paiement_stripe_id)
            if cle_du_paiement not in groupes_par_cle:
                groupes_par_cle[cle_du_paiement] = GroupeDeLignes(
                    regle=REGLE_PAIEMENT_STRIPE, lignes=[]
                )
            groupes_par_cle[cle_du_paiement].lignes.append(ligne)
        else:
            groupes_par_cle[str(ligne.uuid)] = GroupeDeLignes(
                regle=REGLE_LIGNE_SEULE, lignes=[ligne]
            )

    for parts_d_un_paiement_qr in parts_qr_par_texte_de_metadata.values():
        plus_petit_uuid_des_parts = parts_d_un_paiement_qr[0].uuid
        for part in parts_d_un_paiement_qr:
            if part.uuid < plus_petit_uuid_des_parts:
                plus_petit_uuid_des_parts = part.uuid
        groupes_par_cle[str(plus_petit_uuid_des_parts)] = GroupeDeLignes(
            regle=REGLE_PAIEMENT_QR, lignes=parts_d_un_paiement_qr
        )

    return groupes_par_cle


def _ligne_est_un_avoir(ligne):
    """
    Avoir : `credit_note_for` posé, statut avoir (`N`) ou remboursé (`R`), ou quantité
    négative. / Credit note: credit_note_for set, N or R status, or negative quantity.
    """
    if ligne.credit_note_for_id is not None:
        return True
    if ligne.status in STATUTS_DE_LIGNE_D_AVOIR:
        return True
    if ligne.qty < 0:
        return True
    return False


def _texte_de_la_metadata(metadata):
    """
    Le texte qui identifie un paiement QR. En production, `metadata` d'une part QR est
    toujours un texte JSON ; un dict est remis en texte, clés triées.
    / The text identifying a QR payment; a dict is turned back into sorted JSON text.
    """
    if metadata is None:
        return None
    if isinstance(metadata, str):
        return metadata
    return json.dumps(metadata, sort_keys=True)


def _metadata_en_dict(metadata):
    """
    `metadata` est un dict OU un texte JSON selon l'ancien producteur (I-9). Rend
    toujours un dict (vide s'il est illisible).
    / metadata is a dict OR a JSON text: always returns a dict (empty if unreadable).
    """
    if isinstance(metadata, dict):
        return metadata
    if isinstance(metadata, str):
        try:
            metadata_decodee = json.loads(metadata)
        except ValueError:
            return {}
        if isinstance(metadata_decodee, dict):
            return metadata_decodee
    return {}


def _uuid_d_origine_ecrit_dans_metadata(ligne):
    """
    L'uuid de la ligne d'origine écrit par l'ancien remboursement Stripe
    (`metadata["original_lignearticle_uuid"]`), ou None.
    / The origin line uuid written by the old Stripe refund, or None.
    """
    texte_de_l_uuid = _metadata_en_dict(ligne.metadata).get(
        "original_lignearticle_uuid"
    )
    if not texte_de_l_uuid:
        return None
    try:
        return uuid.UUID(str(texte_de_l_uuid))
    except ValueError:
        return None


def _lire_les_origines_ecrites_dans_metadata(groupes_par_cle):
    """
    Les lignes d'origine des avoirs sans `credit_note_for`, lues en UNE requête,
    qu'elles aient déjà une vente ou non.
    / The origin lines of credit notes without credit_note_for, read in ONE query.

    :return: {uuid : {"datetime", "sale_origin"}}
    """
    uuids_d_origine_a_lire = []
    for groupe in groupes_par_cle.values():
        if groupe.regle != REGLE_AVOIR:
            continue
        ligne_d_avoir = groupe.lignes[0]
        if ligne_d_avoir.credit_note_for_id is not None:
            continue
        uuid_d_origine = _uuid_d_origine_ecrit_dans_metadata(ligne_d_avoir)
        if uuid_d_origine is not None:
            uuids_d_origine_a_lire.append(uuid_d_origine)

    origines_par_uuid = {}
    for origine in LigneArticle.objects.filter(uuid__in=uuids_d_origine_a_lire).values(
        "uuid", "datetime", "sale_origin"
    ):
        origines_par_uuid[origine["uuid"]] = origine
    return origines_par_uuid


# --------------------------------------------------------------------------
# 3. Un groupe : forme, statut, articles, règlements
# / One group: shape, status, items, payments
# --------------------------------------------------------------------------


def _reprendre_un_groupe(
    plan,
    cle_du_groupe,
    groupe,
    moment_de_la_reprise,
    categories_des_monnaies,
    origines_lues_dans_metadata,
):
    """
    Calcule la vente d'un groupe et l'ajoute au plan, ou compte son anomalie.
    / Computes one group's sale and adds it to the plan, or counts its anomaly.

    Les anomalies « groupe non écrit » sont cherchées d'abord. Les anomalies
    « signalée, la reprise continue » ne sont comptées que pour un groupe écrit.
    / Blocking anomalies first; non-blocking ones only for a written group.
    """
    lignes_du_groupe = groupe.lignes
    nombre_de_lignes = len(lignes_du_groupe)

    # a. Les moyens de paiement. / a. Payment methods.
    if not _moyens_du_groupe_prevus(lignes_du_groupe):
        _compter(plan.anomalies, ANOMALIE_FORME_NON_PREVUE, nombre_de_lignes)
        return

    # b. La nature et le statut. / b. Nature and status.
    nature_de_la_vente = Vente.Nature.VENTE
    uuid_de_la_ligne_d_origine = None
    credit_note_for_a_poser = False
    if groupe.regle == REGLE_AVOIR:
        nature_de_la_vente = Vente.Nature.AVOIR
        statut_de_la_vente, type_d_anomalie, uuid_de_la_ligne_d_origine = (
            _statut_et_origine_d_un_avoir(
                lignes_du_groupe[0], origines_lues_dans_metadata
            )
        )
        ligne_d_avoir = lignes_du_groupe[0]
        credit_note_for_a_poser = (
            uuid_de_la_ligne_d_origine is not None
            and ligne_d_avoir.credit_note_for_id is None
        )
    elif groupe.regle == REGLE_PAIEMENT_STRIPE:
        statut_de_la_vente, type_d_anomalie = _statut_d_une_vente_stripe(
            lignes_du_groupe, moment_de_la_reprise
        )
    else:
        statut_de_la_vente, type_d_anomalie = _statut_d_une_vente_hors_stripe(
            lignes_du_groupe
        )
    if type_d_anomalie is not None:
        _compter(plan.anomalies, type_d_anomalie, nombre_de_lignes)
        return

    # c. Les recharges : une monnaie en temps ou en points n'est pas reprise.
    # / c. Top-ups: a time or points currency is not taken over.
    if _une_recharge_hors_euros(lignes_du_groupe, categories_des_monnaies):
        _compter(plan.anomalies, ANOMALIE_FORME_NON_PREVUE, nombre_de_lignes)
        return

    # Le groupe sera écrit : on compte maintenant ses anomalies non bloquantes.
    # / The group will be written: now count its non-blocking anomalies.
    if nature_de_la_vente == Vente.Nature.AVOIR and uuid_de_la_ligne_d_origine is None:
        _compter(plan.anomalies, ANOMALIE_ORIGINE_D_AVOIR_INTROUVABLE, 1)
    for ligne in lignes_du_groupe:
        recharge_payee_sans_monnaie_connue = (
            _ligne_est_une_recharge(ligne)
            and ligne.status in STATUTS_DE_LIGNE_PAYEE
            and categories_des_monnaies.get(ligne.asset) is None
        )
        if recharge_payee_sans_monnaie_connue:
            _compter(plan.anomalies, ANOMALIE_MONNAIE_DE_RECHARGE_INTROUVABLE, 1)

    # d. Les articles et les totaux du rapport. / d. Items and report totals.
    articles = []
    for ligne in lignes_du_groupe:
        article = _article_d_une_ancienne_ligne(ligne)
        articles.append(article)
        plan.total_ttc += article.total_ttc
        plan.total_part_offerte += article.part_offerte
        if not article.part_qr:
            plan.total_ancien_calcul_hors_parts_qr += Decimal(ligne.amount) * ligne.qty
            plan.total_catalogue_hors_parts_qr += article.total_catalogue

    # e. Le paiement Stripe d'origine, et ce qu'il recevra (vente réglée seulement).
    # / e. The original Stripe payment, and what it receives (settled sale only).
    paiement_stripe_d_origine = None
    moyen_du_paiement_stripe = None
    montant_encaisse_du_paiement_stripe = None
    if groupe.regle == REGLE_PAIEMENT_STRIPE:
        paiement_stripe_d_origine = lignes_du_groupe[0].paiement_stripe
        if statut_de_la_vente == Vente.Statut.REGLEE:
            moyen_du_paiement_stripe = _moyen_du_paiement_stripe(
                paiement_stripe_d_origine, lignes_du_groupe
            )
            # Q-R4 : le total d'origine des articles du paiement. Les avoirs sont des
            # ventes à part : ils ne sont pas déduits.
            # / Q-R4: the original total of the payment's items, refunds not deducted.
            montant_encaisse_du_paiement_stripe = 0
            for article in articles:
                montant_encaisse_du_paiement_stripe += article.total_ttc

    # f. Les règlements : seulement pour une vente réglée (une vente en attente ou
    # annulée n'a reçu aucun argent).
    # / f. Payments: settled sale only (pending or cancelled: no money received).
    reglements = []
    if statut_de_la_vente == Vente.Statut.REGLEE:
        reglements = _reglements_d_une_vente(
            articles, nature_de_la_vente, moyen_du_paiement_stripe
        )

    # g. L'information sur les quantités des parts QR. / g. QR quantities information.
    if groupe.regle == REGLE_PAIEMENT_QR:
        somme_des_quantites = Decimal("0")
        for part in lignes_du_groupe:
            somme_des_quantites += part.qty
        quantites_hors_bornes = (
            somme_des_quantites < SOMME_MINIMUM_DES_QUANTITES_QR
            or somme_des_quantites > SOMME_MAXIMUM_DES_QUANTITES_QR
        )
        if quantites_hors_bornes:
            _compter(plan.informations, INFORMATION_QUANTITES_QR_HORS_BORNES, 1)

    plan.ventes.append(
        VenteAReprendre(
            cle_du_groupe=cle_du_groupe,
            nature=nature_de_la_vente,
            statut=statut_de_la_vente,
            unite=UNITE_DES_VENTES_REPRISES,
            datetime_de_la_vente=_date_du_groupe(lignes_du_groupe),
            client=_client_du_groupe(lignes_du_groupe),
            paiement_stripe=paiement_stripe_d_origine,
            moyen_du_paiement_stripe=moyen_du_paiement_stripe,
            montant_encaisse_du_paiement_stripe=montant_encaisse_du_paiement_stripe,
            uuid_de_la_ligne_d_origine=uuid_de_la_ligne_d_origine,
            credit_note_for_a_poser=credit_note_for_a_poser,
            articles=articles,
            reglements=reglements,
        )
    )


def _moyens_du_groupe_prevus(lignes_du_groupe):
    """
    Vrai si chaque ligne a un moyen vu en production, à sa place : sur un paiement
    Stripe, un moyen Stripe ou vide (QO-7) ; hors Stripe, jamais vide (Q-R9).
    / True if every line has a production method, in its place.
    """
    for ligne in lignes_du_groupe:
        moyen_de_la_ligne = ligne.payment_method
        if moyen_de_la_ligne not in MOYENS_VUS_EN_PRODUCTION:
            return False
        ligne_reliee_a_stripe = ligne.paiement_stripe_id is not None
        if ligne_reliee_a_stripe and moyen_de_la_ligne not in MOYENS_D_UNE_LIGNE_STRIPE:
            return False
        if not ligne_reliee_a_stripe and not moyen_de_la_ligne:
            return False
    return True


def _statut_et_origine_d_un_avoir(ligne_d_avoir, origines_lues_dans_metadata):
    """
    Un avoir de la production : statut `N` ou `R`, quantité négative → REGLEE (§5.3).
    Sa ligne d'origine : `credit_note_for`, sinon `metadata` (Q-R14). Formes non
    prévues : autre statut, quantité positive (QO-6), avoir sur une part QR (QO-5),
    avoir daté avant son origine (QO-8).
    / A production credit note; its origin line; unexpected shapes.

    :return: (statut, type d'anomalie ou None, uuid de la ligne d'origine ou None)
    """
    avoir_de_la_production = (
        ligne_d_avoir.status in STATUTS_DE_LIGNE_D_AVOIR and ligne_d_avoir.qty < 0
    )
    if not avoir_de_la_production:
        return None, ANOMALIE_FORME_NON_PREVUE, None

    if ligne_d_avoir.credit_note_for_id is not None:
        ligne_d_origine = ligne_d_avoir.credit_note_for
        uuid_d_origine = ligne_d_origine.uuid
        date_de_l_origine = ligne_d_origine.datetime
        origine_de_la_vente_d_origine = ligne_d_origine.sale_origin
    else:
        uuid_d_origine = _uuid_d_origine_ecrit_dans_metadata(ligne_d_avoir)
        origine_lue = origines_lues_dans_metadata.get(uuid_d_origine)
        if origine_lue is None:
            # Origine introuvable : signalée, l'avoir est repris sans vente liée.
            # / Origin not found: reported, taken without a linked sale.
            return Vente.Statut.REGLEE, None, None
        date_de_l_origine = origine_lue["datetime"]
        origine_de_la_vente_d_origine = origine_lue["sale_origin"]

    if origine_de_la_vente_d_origine in ORIGINES_QR:
        return None, ANOMALIE_FORME_NON_PREVUE, None
    if ligne_d_avoir.datetime < date_de_l_origine:
        return None, ANOMALIE_FORME_NON_PREVUE, None
    return Vente.Statut.REGLEE, None, uuid_d_origine


def _statut_d_une_vente_stripe(lignes_du_groupe, moment_de_la_reprise):
    """
    Le statut d'une vente de paiement Stripe suit le paiement (§5.1) :
    - `V`, `P`, `R` → REGLEE, lignes `V`, `P` ou `F` seulement ;
    - `W` commandé il y a moins de 30 jours → EN_ATTENTE ; plus vieux, et `E` →
      ANNULEE ; lignes `U` ou `O` seulement ;
    - tout autre statut de paiement → forme non prévue.
    L'âge se lit sur `order_date` (`auto_now_add`), jamais sur `datetime` ni
    `last_action` (`auto_now` : déplacés par tout enregistrement).
    / The status follows the Stripe payment; age read on order_date only.

    :return: (statut, type d'anomalie ou None)
    """
    paiement = lignes_du_groupe[0].paiement_stripe

    if paiement.status in STATUTS_DE_PAIEMENT_PAYE:
        for ligne in lignes_du_groupe:
            if ligne.status not in STATUTS_DE_LIGNE_PAYEE:
                return None, ANOMALIE_FORME_NON_PREVUE
        return Vente.Statut.REGLEE, None

    if paiement.status in STATUTS_DE_PAIEMENT_NON_PAYE:
        for ligne in lignes_du_groupe:
            if ligne.status not in STATUTS_DE_LIGNE_D_UN_PAIEMENT_NON_PAYE:
                return None, ANOMALIE_FORME_NON_PREVUE
        date_limite_d_un_paiement_en_attente = (
            moment_de_la_reprise - AGE_MAXIMUM_D_UN_PAIEMENT_EN_ATTENTE
        )
        paiement_en_cours_recent = (
            paiement.status == Paiement_stripe.PENDING
            and paiement.order_date > date_limite_d_un_paiement_en_attente
        )
        if paiement_en_cours_recent:
            return Vente.Statut.EN_ATTENTE, None
        return Vente.Statut.ANNULEE, None

    return None, ANOMALIE_FORME_NON_PREVUE


def _statut_d_une_vente_hors_stripe(lignes_du_groupe):
    """
    Hors Stripe, le statut suit les lignes (§5.2) : toutes `V`, `P`, `F` → REGLEE ;
    toutes `O`, `C`, `D`, `U` → ANNULEE ; un mélange → anomalie.
    / Off Stripe, the status follows the lines.

    :return: (statut, type d'anomalie ou None)
    """
    toutes_les_lignes_payees = True
    toutes_les_lignes_non_payees = True
    for ligne in lignes_du_groupe:
        if ligne.status not in STATUTS_DE_LIGNE_PAYEE:
            toutes_les_lignes_payees = False
        if ligne.status not in STATUTS_DE_LIGNE_NON_PAYEE:
            toutes_les_lignes_non_payees = False

    if toutes_les_lignes_payees:
        return Vente.Statut.REGLEE, None
    if toutes_les_lignes_non_payees:
        return Vente.Statut.ANNULEE, None
    return None, ANOMALIE_STATUTS_MELANGES


def _ligne_est_une_recharge(ligne):
    """Le produit de la ligne est une recharge (euros, cadeau, temps).
    / The line's product is a top-up."""
    produit = ligne.pricesold.productsold.product
    if produit.categorie_article in CATEGORIES_DE_RECHARGE:
        return True
    if produit.methode_caisse in METHODES_CAISSE_DE_RECHARGE:
        return True
    return False


def _une_recharge_hors_euros(lignes_du_groupe, categories_des_monnaies):
    """Vrai si une ligne est une recharge en temps ou en points (absente de la
    production). / True if a line is a time or points top-up."""
    for ligne in lignes_du_groupe:
        if not _ligne_est_une_recharge(ligne):
            continue
        categorie_de_la_monnaie = categories_des_monnaies.get(ligne.asset)
        if categorie_de_la_monnaie in CATEGORIES_DE_MONNAIE_HORS_EUROS:
            return True
    return False


def _ligne_est_une_part_qr(ligne):
    """
    Une part QR / NFC (origine QR ou NF), ou une ligne `LE` / `SF` à quantité non
    entière hors QR, traitée comme une part (QO-12).
    / A QR / NFC part, or a non-integer LE / SF line treated as a part.
    """
    if ligne.sale_origin in ORIGINES_QR:
        return True
    quantite_non_entiere = ligne.qty != ligne.qty.to_integral_value()
    if ligne.payment_method in MOYENS_D_UNE_PART and quantite_non_entiere:
        return True
    return False


def _article_d_une_ancienne_ligne(ligne):
    """
    Les montants entiers d'une ancienne ligne, par la formule unique
    `calculer_montants_article` (BaseBillet/services_vente.py), avec les règles
    d'`ajouter_article` refaites ici (la reprise ne crée aucune ligne) :
    - taux de TVA : celui ÉCRIT SUR LA LIGNE (`vat`), jamais celui du tarif (Q-R11) ;
    - part QR : l'argent est `amount`, jamais `amount × qty` (Q-R10, QO-12) ;
    - moyen offert (`NA`) à montant non nul : part offerte = total catalogue, source
      OFFRIR (QO-10) ;
    - hors chiffre d'affaires : recharge, ou méthode de caisse hors chiffre d'affaires.
    / The old line's amounts by the single formula, with ajouter_article's rules.
    """
    part_qr = _ligne_est_une_part_qr(ligne)
    total_catalogue_impose = None
    if part_qr:
        total_catalogue_impose = ligne.amount

    montants = calculer_montants_article(
        prix_unitaire=ligne.amount,
        quantite=ligne.qty,
        taux_tva=ligne.vat,
        total_catalogue_impose=total_catalogue_impose,
    )
    source_offert = ""
    ligne_offerte_a_montant_non_nul = (
        ligne.payment_method == PaymentMethod.FREE and montants["total_catalogue"] != 0
    )
    if ligne_offerte_a_montant_non_nul:
        montants = calculer_montants_article(
            prix_unitaire=ligne.amount,
            quantite=ligne.qty,
            taux_tva=ligne.vat,
            part_offerte=montants["total_catalogue"],
            total_catalogue_impose=total_catalogue_impose,
        )
        source_offert = LigneArticle.SourceOffert.OFFRIR

    produit = ligne.pricesold.productsold.product
    hors_chiffre_affaires = (
        produit.methode_caisse in METHODES_CAISSE_HORS_CHIFFRE_AFFAIRES
        or produit.categorie_article in CATEGORIES_DE_RECHARGE
    )

    return ArticleAReprendre(
        ligne=ligne,
        methode_caisse_du_produit_a_creer=None,
        quantite=ligne.qty,
        prix_unitaire=ligne.amount,
        taux_tva=ligne.vat,
        asset=ligne.asset,
        total_catalogue=montants["total_catalogue"],
        part_offerte=montants["part_offerte"],
        source_offert=source_offert,
        part_en_jetons=0,
        total_ttc=montants["total_ttc"],
        total_ht=montants["total_ht"],
        total_tva=montants["total_tva"],
        hors_chiffre_affaires=hors_chiffre_affaires,
        part_qr=part_qr,
    )


def _moyen_du_paiement_stripe(paiement, lignes_du_paiement):
    """
    Le moyen du paiement Stripe (B-3) : SEPA (`SP`) si une ligne porte `SP` ;
    abonnement (`SR`) si le paiement vient d'une facture ou si une ligne porte `SR` ;
    sinon Stripe carte (`SN`, aussi pour un moyen vide : Q-R9).
    / The Stripe payment method: SP, else SR, else SN.
    """
    moyens_des_lignes = []
    for ligne in lignes_du_paiement:
        moyens_des_lignes.append(ligne.payment_method)
    if PaymentMethod.STRIPE_SEPA_NOFED in moyens_des_lignes:
        return PaymentMethod.STRIPE_SEPA_NOFED
    paiement_d_une_facture = paiement.source == Paiement_stripe.INVOICE
    if paiement_d_une_facture or PaymentMethod.STRIPE_RECURENT in moyens_des_lignes:
        return PaymentMethod.STRIPE_RECURENT
    return PaymentMethod.STRIPE_NOFED


def _reglements_d_une_vente(articles, nature_de_la_vente, moyen_du_paiement_stripe):
    """
    Les règlements d'une vente réglée (§7) :
    - un par couple (moyen, monnaie), montant = Σ des nets (`total_ttc`) du couple ;
    - un FREE égal à Σ des parts offertes ;
    - vente d'un paiement Stripe : le moyen du paiement, relié au paiement ;
    - ligne reliée à Stripe sans moyen : Stripe carte (Q-R9) ;
    - avoir relié à un paiement Stripe : relié au paiement, référence « reprise » (Q-R6) ;
    - aucun règlement de 0 (une vente gratuite n'en a pas).
    / The payments of a settled sale.

    :param moyen_du_paiement_stripe: le moyen d'une vente de paiement Stripe, sinon None
    """
    couples_dans_l_ordre = []
    sommes_par_couple = {}
    total_offert = 0

    for article in articles:
        ligne = article.ligne
        total_offert += article.part_offerte

        if moyen_du_paiement_stripe is not None:
            moyen_du_reglement = moyen_du_paiement_stripe
        elif not ligne.payment_method:
            moyen_du_reglement = PaymentMethod.STRIPE_NOFED
        else:
            moyen_du_reglement = ligne.payment_method

        # Toutes les lignes d'un groupe ont le même paiement Stripe (ou aucun) : il
        # suit le couple. / Every line of a group shares the same Stripe payment.
        couple = (moyen_du_reglement, ligne.asset)
        if couple not in sommes_par_couple:
            couples_dans_l_ordre.append(couple)
            sommes_par_couple[couple] = {
                "montant": 0,
                "cartes": [],
                "portefeuilles": [],
                "paiement_stripe": ligne.paiement_stripe,
            }
        somme_du_couple = sommes_par_couple[couple]
        somme_du_couple["montant"] += article.total_ttc
        if ligne.carte_id not in somme_du_couple["cartes"]:
            somme_du_couple["cartes"].append(ligne.carte_id)
        if ligne.wallet_id not in somme_du_couple["portefeuilles"]:
            somme_du_couple["portefeuilles"].append(ligne.wallet_id)

    reglements = []
    for couple in couples_dans_l_ordre:
        moyen_du_reglement, asset_du_reglement = couple
        somme_du_couple = sommes_par_couple[couple]
        if somme_du_couple["montant"] == 0:
            continue

        # Carte et portefeuille recopiés seulement s'ils sont les mêmes pour toutes
        # les lignes du couple. / Card and wallet copied only when identical.
        carte_id_du_reglement = None
        if len(somme_du_couple["cartes"]) == 1:
            carte_id_du_reglement = somme_du_couple["cartes"][0]
        wallet_id_du_reglement = None
        if len(somme_du_couple["portefeuilles"]) == 1:
            wallet_id_du_reglement = somme_du_couple["portefeuilles"][0]

        paiement_stripe_du_reglement = somme_du_couple["paiement_stripe"]
        reference_externe = ""
        avoir_relie_a_stripe = (
            nature_de_la_vente == Vente.Nature.AVOIR
            and paiement_stripe_du_reglement is not None
        )
        if avoir_relie_a_stripe:
            reference_externe = REFERENCE_D_UN_AVOIR_REPRIS

        reglements.append(
            ReglementAReprendre(
                moyen=moyen_du_reglement,
                montant=somme_du_couple["montant"],
                asset=asset_du_reglement,
                carte_id=carte_id_du_reglement,
                wallet_id=wallet_id_du_reglement,
                paiement_stripe=paiement_stripe_du_reglement,
                reference_externe=reference_externe,
            )
        )

    if total_offert != 0:
        reglements.append(
            ReglementAReprendre(
                moyen=PaymentMethod.FREE,
                montant=total_offert,
                asset=None,
                carte_id=None,
                wallet_id=None,
                paiement_stripe=None,
                reference_externe="",
            )
        )
    return reglements


def _date_du_groupe(lignes_du_groupe):
    """La date d'une vente reprise : la plus récente de ses lignes (Q-R14).
    / A sale's date: its most recent line."""
    date_la_plus_recente = lignes_du_groupe[0].datetime
    for ligne in lignes_du_groupe:
        if ligne.datetime > date_la_plus_recente:
            date_la_plus_recente = ligne.datetime
    return date_la_plus_recente


def _client_du_groupe(lignes_du_groupe):
    """
    Le client d'une vente reprise (QO-3) : l'utilisateur de la réservation, sinon de
    l'adhésion, sinon du paiement Stripe, sinon personne.
    / The client: reservation user, else membership user, else payment user, else none.
    """
    for ligne in lignes_du_groupe:
        if ligne.reservation is not None:
            return ligne.reservation.user_commande
    for ligne in lignes_du_groupe:
        if ligne.membership is not None and ligne.membership.user is not None:
            return ligne.membership.user
    for ligne in lignes_du_groupe:
        if ligne.paiement_stripe is not None and ligne.paiement_stripe.user is not None:
            return ligne.paiement_stripe.user
    return None


# --------------------------------------------------------------------------
# 4. Les paiements `T` : des ventes « virement reçu » (QO-9, option B)
# / T payments: "transfer received" sales
# --------------------------------------------------------------------------


def _reprendre_les_virements_recus(plan, categories_des_monnaies):
    """
    Chaque paiement Stripe `T` (retour en banque de monnaie FED), validé, sans ligne
    et sans vente, donne une vente « virement reçu » : un article `VR` à créer
    (quantité 1, TVA 0, hors chiffre d'affaires, monnaie FED) et un règlement Stripe
    en ligne (`SN`) relié au paiement. C'est la seule vente reprise qui crée un
    article. Aucun appel à Stripe ni à Fedow : montant et date sont lus dans
    `metadata_stripe`.
    / Each validated T payment without lines becomes a "transfer received" sale.
    """
    uuid_de_la_monnaie_fed = None
    for uuid_de_la_monnaie, categorie in categories_des_monnaies.items():
        if categorie == AssetFedowPublic.STRIPE_FED_FIAT:
            uuid_de_la_monnaie_fed = uuid_de_la_monnaie

    paiements_de_transfert = Paiement_stripe.objects.filter(
        source=Paiement_stripe.TRANSFERT,
        status=Paiement_stripe.VALID,
        vente__isnull=True,
        lignearticles__isnull=True,
    ).order_by("order_date", "uuid")

    for paiement in paiements_de_transfert:
        montant_du_virement, date_du_virement = _montant_et_date_du_transfert(
            paiement.metadata_stripe
        )
        if montant_du_virement is None:
            _compter(plan.anomalies, ANOMALIE_VIREMENT_RECU_ILLISIBLE, 1)
            continue
        if uuid_de_la_monnaie_fed is None:
            _compter(plan.anomalies, ANOMALIE_MONNAIE_FED_INTROUVABLE, 1)
            continue

        taux_tva_du_virement = Decimal("0")
        montants = calculer_montants_article(
            prix_unitaire=montant_du_virement,
            quantite=1,
            taux_tva=taux_tva_du_virement,
        )
        article_du_virement = ArticleAReprendre(
            ligne=None,
            methode_caisse_du_produit_a_creer=Product.VIREMENT_RECU,
            quantite=Decimal("1"),
            prix_unitaire=montant_du_virement,
            taux_tva=taux_tva_du_virement,
            asset=uuid_de_la_monnaie_fed,
            total_catalogue=montants["total_catalogue"],
            part_offerte=montants["part_offerte"],
            source_offert="",
            part_en_jetons=0,
            total_ttc=montants["total_ttc"],
            total_ht=montants["total_ht"],
            total_tva=montants["total_tva"],
            hors_chiffre_affaires=True,
            part_qr=False,
        )
        reglement_du_virement = ReglementAReprendre(
            moyen=PaymentMethod.STRIPE_NOFED,
            montant=montant_du_virement,
            asset=None,
            carte_id=None,
            wallet_id=None,
            paiement_stripe=paiement,
            reference_externe="",
        )
        plan.total_ttc += article_du_virement.total_ttc

        plan.ventes.append(
            VenteAReprendre(
                cle_du_groupe=str(paiement.uuid),
                nature=Vente.Nature.VENTE,
                statut=Vente.Statut.REGLEE,
                unite=UNITE_DES_VENTES_REPRISES,
                datetime_de_la_vente=date_du_virement,
                client=None,
                paiement_stripe=paiement,
                moyen_du_paiement_stripe=PaymentMethod.STRIPE_NOFED,
                montant_encaisse_du_paiement_stripe=montant_du_virement,
                uuid_de_la_ligne_d_origine=None,
                credit_note_for_a_poser=False,
                articles=[article_du_virement],
                reglements=[reglement_du_virement],
            )
        )


def _montant_et_date_du_transfert(metadata_stripe):
    """
    Le montant (centimes) et la date d'un transfert Stripe, lus dans le message du
    webhook `transfer.created` (ApiBillet/views.py). Le champ contient un TEXTE JSON
    (`json.dumps(payload)`). La date est `data.object.created` (horodatage Unix) :
    `order_date` porte l'heure de réception du webhook, pas celle du transfert.
    / Amount and date of a Stripe transfer, read in the webhook message (JSON text).

    :return: (montant en centimes, datetime UTC), ou (None, None) si illisible
    """
    message_de_stripe = metadata_stripe
    if isinstance(message_de_stripe, str):
        try:
            message_de_stripe = json.loads(message_de_stripe)
        except ValueError:
            return None, None
    try:
        objet_du_transfert = message_de_stripe["data"]["object"]
        montant_du_transfert = objet_du_transfert["amount"]
        horodatage_du_transfert = objet_du_transfert["created"]
    except (KeyError, TypeError):
        return None, None

    montant_lisible = type(montant_du_transfert) is int and montant_du_transfert > 0
    horodatage_lisible = type(horodatage_du_transfert) is int
    if not montant_lisible or not horodatage_lisible:
        return None, None
    date_du_transfert = datetime.fromtimestamp(
        horodatage_du_transfert, tz=fuseau_horaire.utc
    )
    return montant_du_transfert, date_du_transfert
