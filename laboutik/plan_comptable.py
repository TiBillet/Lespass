"""
Le plan comptable du lieu : le charger, s'assurer qu'il existe, et les règles qui
donnent le compte d'un règlement, d'un article, et le journal d'une vente.
/ The venue's chart of accounts: load it, make sure it exists, and the rules giving
the account of a payment, of an item, and the journal of a sale.

LOCALISATION : laboutik/plan_comptable.py

Un seul plan par défaut, aux numéros à 6 chiffres. Ses données vivent dans
`laboutik/plan_comptable_par_defaut.py`.
/ One single default plan, 6-digit numbers. Its data lives in plan_comptable_par_defaut.py.

QUI APPELLE / CALLERS
---------------------
- `charger_le_plan_comptable_par_defaut()` : la commande `charger_plan_comptable` et
  le bouton « Charger le plan par défaut » de l'admin (`laboutik/views.py`).
- `s_assurer_que_le_plan_existe()` : le filet. Appelé à l'ouverture des trois écrans
  du plan (`Administration/admin/laboutik.py`), au début du FEC d'une clôture
  (`comptabilite/fec.py` `generer_fec_cloture`) et par « Plan complet ? ». Rien sur
  le chemin d'une vente.
- `compte_pour_reglement()`, `compte_pour_article()`, `compte_de_tva_pour_taux()`,
  `comptes_du_plan_par_defaut_du_lieu()`, `compte_des_cadeaux_a_la_clientele()`,
  `journal_pour()`, `collisions_de_codes_journal()`, `points_de_vente_au_code_journal_reserve()`,
  `points_de_vente_sans_code_journal()` : les exports (`comptabilite/ventilation.py`)
  et « Plan complet ? ». Ces règles ne modifient rien en base.
- `ce_qui_manque_pour_exporter()` (« Plan complet ? ») : le bouton « Vérifier le
  plan » des écrans du plan (`CompteComptableAdmin.verifier_le_plan`), jamais leur
  ouverture. `monnaies_acceptees_par_le_lieu()` : l'écran des comptes des monnaies.

La migration `laboutik/0002_preparer_chaque_lieu` a sa propre version
de ce chargement (modèles historiques, `apps.get_model`) : elle lit les mêmes données.
/ The 0002 migration has its own version (historical models): it reads the same data.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-E-plan-comptable.md §3, §4.
"""

import logging
import unicodedata
from decimal import Decimal
from urllib.parse import urlencode

from django.db import IntegrityError, connection, transaction
from django.db.models import F, Q
from django.urls import reverse
from django.utils.translation import gettext, ngettext

from BaseBillet.models import (
    CategorieProduct,
    LigneArticle,
    PaymentMethod,
    Product,
    SaleOrigin,
)
from BaseBillet.models_vente import Reglement, Vente
from BaseBillet.services_vente import (
    NOM_ECART_RECU_EN_MOINS,
    NOM_ECART_RECU_EN_PLUS,
    NOM_JETONS_CADEAU_REPRIS_AU_VIDAGE,
)
from Customers.models import Client
from fedow_core.models import Asset
from fedow_core.services import AssetService
from fedow_public.models import AssetFedowPublic
from laboutik.models import (
    CompteComptable,
    MappingMonnaie,
    MappingMoyenDePaiement,
    PointDeVente,
)
from laboutik.plan_comptable_par_defaut import (
    COMPTE_DES_CATEGORIES_CONNUES,
    COMPTE_PAR_DEFAUT,
    COMPTES_DU_PLAN_PAR_DEFAUT,
    CORRESPONDANCES_DES_MOYENS_PAR_DEFAUT,
    NOM_CATEGORIE_FINANCEMENT_PARTICIPATIF,
    NOM_DU_PRODUIT_DE_FINANCEMENT_PARTICIPATIF,
)

logger = logging.getLogger(__name__)


class CompteComptableManquant(Exception):
    """
    Le plan ne donne pas de compte (ou de journal) pour ce qu'on veut écrire : l'export
    est refusé (D23, jamais de ligne sautée en silence). Le message dit ce qui manque :
    le moyen, la monnaie, le produit ou l'origine.
    / The plan gives no account (or journal) for what must be written: the export is
    refused. The message says what is missing.

    LOCALISATION : laboutik/plan_comptable.py
    """


class CompteDuPlanParDefautManquant(CompteComptableManquant):
    """
    Un compte du plan par défaut (`COMPTE_PAR_DEFAUT`) manque dans le lieu : il a été
    supprimé. Le bouton « Charger le plan par défaut » le remet. `numero_de_compte`
    porte le numéro qui manque : « Plan complet ? » le nomme sans lire le message.
    / A default plan account is missing in the venue. `numero_de_compte` carries the
    missing number, so "Complete plan?" names it without parsing the message.

    LOCALISATION : laboutik/plan_comptable.py
    """

    def __init__(self, numero_de_compte):
        self.numero_de_compte = numero_de_compte
        super().__init__(
            f"Le compte {numero_de_compte} du plan par défaut manque dans le lieu."
        )


def charger_le_plan_comptable_par_defaut():
    """
    Ajoute au lieu courant ce qui manque du plan par défaut. N'efface rien, ne
    renumérote rien, ne modifie aucun compte ni aucun lien existant.
    / Adds to the current venue what is missing from the default plan. Erases
    nothing, renumbers nothing, changes no existing account or link.

    FLUX :
    1. Les comptes. Un compte ordinaire est retrouvé par son numéro et créé s'il
       manque. Un compte de TVA est retrouvé par son TAUX : si le lieu a déjà un
       compte de TVA à ce taux, quel que soit son numéro, rien n'est créé.
    2. Les correspondances des moyens de paiement, créées seulement si le moyen n'en
       a aucune (une correspondance existante, même vide, n'est pas touchée).
    3. Les catégories connues (financement participatif, écarts), reliées à leur
       compte si elles existent et n'ont pas encore de compte. Seule la catégorie
       « Financement participatif » est créée si elle manque ; les produits des
       contributions crowds sans catégorie y sont rangés.
    4. Les deux uuid du FED (fedow_core et ancien Fedow), reliés au 467000 s'ils
       existent et n'ont pas encore de compte.

    Le tout dans une transaction : un échec n'écrit rien.
    / All in one transaction: a failure writes nothing.

    :return: la liste des avertissements (str), vide si tout est chargé
    """
    avertissements = []

    with transaction.atomic():
        # --- 1. Les comptes / The accounts ---
        for entree in COMPTES_DU_PLAN_PAR_DEFAUT:
            est_un_compte_de_tva = entree["nature"] == CompteComptable.TVA

            if not est_un_compte_de_tva:
                CompteComptable.objects.get_or_create(
                    numero_de_compte=entree["numero"],
                    defaults={
                        "libelle_du_compte": entree["libelle"],
                        "nature_du_compte": entree["nature"],
                        "taux_de_tva": entree["taux_de_tva"],
                    },
                )
                continue

            # La TVA est cherchée par son taux, jamais par son numéro.
            # / VAT is looked up by its rate, never by its number.
            taux_de_ce_compte = Decimal(entree["taux_de_tva"])
            le_lieu_a_deja_ce_taux = CompteComptable.objects.filter(
                nature_du_compte=CompteComptable.TVA,
                taux_de_tva=taux_de_ce_compte,
            ).exists()
            if le_lieu_a_deja_ce_taux:
                continue

            # Le numéro voulu est pris par un autre compte (un autre taux, une autre
            # nature) : on ne crée pas, on n'écrase pas. On prévient.
            # / The wanted number is taken by another account: no creation, no
            # overwrite. A warning is returned.
            compte_qui_porte_deja_ce_numero = CompteComptable.objects.filter(
                numero_de_compte=entree["numero"]
            ).first()
            if compte_qui_porte_deja_ce_numero is not None:
                avertissement = (
                    f"Compte de TVA à {taux_de_ce_compte} % non créé : le numéro "
                    f"{entree['numero']} est déjà pris par "
                    f"« {compte_qui_porte_deja_ce_numero} »."
                )
                logger.warning(avertissement)
                avertissements.append(avertissement)
                continue

            CompteComptable.objects.create(
                numero_de_compte=entree["numero"],
                libelle_du_compte=entree["libelle"],
                nature_du_compte=entree["nature"],
                taux_de_tva=taux_de_ce_compte,
            )

        # --- 2. Les correspondances des moyens / The payment method mappings ---
        for correspondance in CORRESPONDANCES_DES_MOYENS_PAR_DEFAUT:
            le_moyen_a_deja_une_correspondance = MappingMoyenDePaiement.objects.filter(
                moyen_de_paiement=correspondance["moyen"]
            ).exists()
            if le_moyen_a_deja_une_correspondance:
                continue

            compte_de_tresorerie = CompteComptable.objects.get(
                numero_de_compte=correspondance["numero"]
            )
            MappingMoyenDePaiement.objects.create(
                moyen_de_paiement=correspondance["moyen"],
                libelle_moyen=correspondance["libelle"],
                compte_de_tresorerie=compte_de_tresorerie,
            )

        # --- 3. Les catégories connues / The known categories ---
        # La catégorie du financement participatif est créée si elle manque, et les
        # produits des contributions crowds sans catégorie y sont rangés : sans elle,
        # une contribution n'a pas de compte (754000).
        # / The crowdfunding category is created if missing, and crowds products
        # without category are put in it.
        # Le nom d'une catégorie n'est pas unique en base : on prend la première.
        # / A category name is not unique in the database: take the first one.
        categorie_financement_participatif = CategorieProduct.objects.filter(
            name=NOM_CATEGORIE_FINANCEMENT_PARTICIPATIF
        ).first()
        if categorie_financement_participatif is None:
            categorie_financement_participatif = CategorieProduct.objects.create(
                name=NOM_CATEGORIE_FINANCEMENT_PARTICIPATIF
            )
        produits_crowds_sans_categorie = Product.objects.filter(
            name__iexact=NOM_DU_PRODUIT_DE_FINANCEMENT_PARTICIPATIF,
            categorie_pos__isnull=True,
        )
        for produit_crowds in produits_crowds_sans_categorie:
            produit_crowds.categorie_pos = categorie_financement_participatif
            produit_crowds.save(update_fields=["categorie_pos"])

        for categorie_connue in COMPTE_DES_CATEGORIES_CONNUES:
            compte_de_la_categorie = CompteComptable.objects.get(
                numero_de_compte=categorie_connue["numero"]
            )
            categories_sans_compte = CategorieProduct.objects.filter(
                name=categorie_connue["nom_de_la_categorie"],
                compte_comptable__isnull=True,
            )
            for categorie in categories_sans_compte:
                categorie.compte_comptable = compte_de_la_categorie
                categorie.save(update_fields=["compte_comptable"])

        # --- 4. Le FED au compte du réseau / The FED to the network account ---
        # Le FED a deux uuid : celui de fedow_core et celui de l'ancien Fedow. Une
        # correspondance existante n'est pas touchée.
        # / The FED has two uuids. An existing mapping is not touched.
        compte_du_reseau_federe = CompteComptable.objects.get(
            numero_de_compte=COMPTE_PAR_DEFAUT["reseau_federe"]
        )
        uuids_du_fed = []
        for fed_de_fedow_core in Asset.objects.filter(category=Asset.FED):
            uuids_du_fed.append(fed_de_fedow_core.uuid)
        for fed_de_l_ancien_fedow in AssetFedowPublic.objects.filter(
            category=AssetFedowPublic.STRIPE_FED_FIAT
        ):
            uuids_du_fed.append(fed_de_l_ancien_fedow.uuid)
        for uuid_du_fed in uuids_du_fed:
            MappingMonnaie.objects.get_or_create(
                asset_uuid=uuid_du_fed,
                defaults={"compte_de_tresorerie": compte_du_reseau_federe},
            )

    return avertissements


def s_assurer_que_le_plan_existe():
    """
    Filet : charge le plan par défaut si le lieu n'a AUCUN compte. Sinon ne fait rien.
    / Safety net: loads the default plan if the venue has NO account. Else does nothing.

    Appelé à l'ouverture des trois écrans du plan, au début du FEC d'une clôture
    (`generer_fec_cloture`) et par « Plan complet ? ». Jamais pendant une vente.
    / Called when the three plan screens open, before a closure's FEC and by
    "Complete plan?". Never during a sale.

    Deux appels en même temps (deux exports) ne cassent rien : le second tombe sur
    l'unicité du numéro de compte, sa transaction est annulée, le plan du premier
    reste.
    / Two simultaneous calls break nothing: the second hits the account number
    uniqueness, its transaction is rolled back, the first one's plan remains.

    :return: la liste des avertissements du chargement (vide si rien n'est chargé)
    """
    le_lieu_a_deja_un_compte = CompteComptable.objects.exists()
    if le_lieu_a_deja_un_compte:
        return []

    try:
        with transaction.atomic():
            return charger_le_plan_comptable_par_defaut()
    except IntegrityError:
        logger.info(
            "Plan comptable chargé en même temps par un autre appel : rien à faire."
        )
        return []


# --------------------------------------------------------------------------- #
#  Les règles de compte (fiche E §3) / The account rules (sheet E §3)          #
# --------------------------------------------------------------------------- #


def _compte_du_plan_par_defaut(cle, comptes_du_plan_par_defaut=None):
    """
    Le compte du lieu qui porte le numéro de `COMPTE_PAR_DEFAUT[cle]`.
    / The venue account carrying the number COMPTE_PAR_DEFAUT[cle].

    :param comptes_du_plan_par_defaut: dict {numéro: compte} déjà lu par l'appelant
        (un numéro absent du dict manque au lieu), ou None pour lire le compte en base
    :raises CompteDuPlanParDefautManquant: si le lieu n'a pas ce compte
    """
    numero_de_compte = COMPTE_PAR_DEFAUT[cle]
    if comptes_du_plan_par_defaut is not None:
        compte = comptes_du_plan_par_defaut.get(numero_de_compte)
    else:
        compte = CompteComptable.objects.filter(
            numero_de_compte=numero_de_compte
        ).first()
    if compte is None:
        raise CompteDuPlanParDefautManquant(numero_de_compte)
    return compte


def comptes_du_plan_par_defaut_du_lieu():
    """
    Les comptes du lieu qui portent un numéro du plan par défaut (`COMPTE_PAR_DEFAUT`),
    lus en UNE requête. Un appelant qui applique la règle d'un article à beaucoup de
    lignes passe ce dict à `compte_pour_article` : la règle y cherche ses comptes au
    lieu de relire la base pour chaque ligne.
    / The venue's default-plan accounts, read in ONE query, to pass to
    compte_pour_article.

    :return: dict {numéro: CompteComptable} ; un numéro absent manque au lieu
    """
    comptes_du_plan_par_defaut = {}
    comptes_lus = CompteComptable.objects.filter(
        numero_de_compte__in=list(COMPTE_PAR_DEFAUT.values())
    )
    for compte_du_plan in comptes_lus:
        comptes_du_plan_par_defaut[compte_du_plan.numero_de_compte] = compte_du_plan
    return comptes_du_plan_par_defaut


def compte_des_cadeaux_a_la_clientele(comptes_du_plan_par_defaut=None):
    """
    Le compte des cadeaux à la clientèle (623400) : la charge d'une recharge offerte
    (D8 bis). C'est un compte du plan par défaut, cherché par son numéro.
    / The "gifts to customers" account (623400), the expense of an offered top-up.

    APPELÉE PAR : `comptabilite/ventilation.py` (recharge offerte).

    :param comptes_du_plan_par_defaut: dict de `comptes_du_plan_par_defaut_du_lieu()`,
        déjà lu par l'appelant, ou None pour lire le compte en base
    :return: le `CompteComptable`
    :raises CompteDuPlanParDefautManquant: si le lieu n'a pas ce compte
    """
    return _compte_du_plan_par_defaut(
        "cadeaux_a_la_clientele", comptes_du_plan_par_defaut
    )


def compte_des_ventes_reglees_en_jetons(comptes_du_plan_par_defaut=None):
    """
    Le compte des ventes réglées en jetons cadeau (707900), hors TVA : il reçoit la
    part payée en jetons de chaque article (D8 bis). C'est un compte du plan par
    défaut, cherché par son numéro.
    / The "sales settled in gift tokens" account (707900), without VAT.

    APPELÉE PAR : `comptabilite/ventilation.py` (part en jetons d'un article) et
    `ce_qui_manque_pour_exporter` (ce module, « Plan complet ? »).

    :param comptes_du_plan_par_defaut: dict de `comptes_du_plan_par_defaut_du_lieu()`,
        déjà lu par l'appelant, ou None pour lire le compte en base
    :return: le `CompteComptable`
    :raises CompteDuPlanParDefautManquant: si le lieu n'a pas ce compte
    """
    return _compte_du_plan_par_defaut(
        "ventes_reglees_en_jetons", comptes_du_plan_par_defaut
    )


def _la_monnaie_est_celle_du_lieu(asset_uuid):
    """
    Vrai si la monnaie a été créée par le lieu courant : `fedow_core.Asset.tenant_origin`
    ou `fedow_public.AssetFedowPublic.origin` (ancien Fedow).
    / True if the currency was created by the current venue (either engine).

    Le lieu est lu par le nom du schéma courant : `connection.tenant` peut être un
    FakeTenant (schema_context) qui n'a pas d'uuid.
    / The venue is read through the current schema name: connection.tenant may be a
    FakeTenant without uuid.
    """
    nom_du_schema_du_lieu = connection.schema_name
    monnaie_fedow_core_du_lieu = Asset.objects.filter(
        uuid=asset_uuid,
        tenant_origin__schema_name=nom_du_schema_du_lieu,
    ).exists()
    if monnaie_fedow_core_du_lieu:
        return True
    monnaie_ancien_fedow_du_lieu = AssetFedowPublic.objects.filter(
        uuid=asset_uuid,
        origin__schema_name=nom_du_schema_du_lieu,
    ).exists()
    return monnaie_ancien_fedow_du_lieu


def _compte_de_la_monnaie(asset_uuid):
    """
    Le compte de la monnaie (`MappingMonnaie`), ou None si elle n'en a pas.
    / The currency's account, or None if it has none.
    """
    correspondance_de_la_monnaie = (
        MappingMonnaie.objects.select_related("compte_de_tresorerie")
        .filter(asset_uuid=asset_uuid)
        .first()
    )
    if correspondance_de_la_monnaie is None:
        return None
    return correspondance_de_la_monnaie.compte_de_tresorerie


def compte_pour_reglement(moyen, asset_uuid):
    """
    Le compte de trésorerie d'un règlement.
    / The treasury account of a payment.

    LOCALISATION : laboutik/plan_comptable.py (fiche E §3.1)

    RÈGLE, dans l'ordre :
    0. `NA` (offert) et `NM` (points, temps) n'écrivent pas d'argent : rend None.
    1. La monnaie a un compte (`MappingMonnaie`) : ce compte.
    2. `SF` (FED) passe toujours par sa monnaie : sans compte de monnaie, erreur, même
       si le moyen `SF` a une correspondance.
    3. Une monnaie qui n'est pas celle du lieu (monnaie d'un autre lieu) : erreur. Un
       compte par monnaie.
    4. Sans monnaie, ou monnaie du lieu : le compte du moyen (`MappingMoyenDePaiement`).
       Une correspondance absente ou au compte vide : erreur.
    / 0. NA, NM: None. 1. Currency account. 2. SF only through its currency.
    3. Another venue's currency without account: error. 4. The method's account.

    :param moyen: code `PaymentMethod` du règlement (ex. "CA", "LE", "SF")
    :param asset_uuid: uuid de la monnaie du règlement, ou None
    :return: le `CompteComptable`, ou None pour NA et NM
    :raises CompteComptableManquant: si aucun compte ne convient
    """
    moyens_sans_ecriture_d_argent = [PaymentMethod.FREE, PaymentMethod.NON_MONETAIRE]
    if moyen in moyens_sans_ecriture_d_argent:
        return None

    if asset_uuid is not None:
        compte_de_la_monnaie = _compte_de_la_monnaie(asset_uuid)
        if compte_de_la_monnaie is not None:
            return compte_de_la_monnaie

    if moyen == PaymentMethod.STRIPE_FED:
        raise CompteComptableManquant(
            f"Le règlement « {moyen} » (FED) passe par sa monnaie, et la monnaie "
            f"« {asset_uuid} » n'a pas de compte."
        )

    if asset_uuid is not None:
        if not _la_monnaie_est_celle_du_lieu(asset_uuid):
            raise CompteComptableManquant(
                f"La monnaie « {asset_uuid} » (moyen « {moyen} ») n'a pas de compte : "
                f"une monnaie d'un autre lieu a besoin de son propre compte."
            )

    correspondance_du_moyen = (
        MappingMoyenDePaiement.objects.select_related("compte_de_tresorerie")
        .filter(moyen_de_paiement=moyen)
        .first()
    )
    if correspondance_du_moyen is None:
        raise CompteComptableManquant(
            f"Le moyen de paiement « {moyen} » n'a pas de compte."
        )
    if correspondance_du_moyen.compte_de_tresorerie is None:
        raise CompteComptableManquant(
            f"La correspondance du moyen de paiement « {moyen} » a un compte vide."
        )
    return correspondance_du_moyen.compte_de_tresorerie


# Le journal d'une vente sans point de vente, selon son origine (fiche E §3.2).
# Une origine absente de cette table lève une erreur : une origine ajoutée plus tard
# doit y recevoir son journal.
# / The journal of a sale without point of sale, by origin. A missing origin raises.
JOURNAL_PAR_ORIGINE = {
    SaleOrigin.LABOUTIK: "CAISSE",
    SaleOrigin.QRCODE_MA: "CAISSE",
    SaleOrigin.NFC_MA: "CAISSE",
    SaleOrigin.TIREUSE: "TIREUSE",
    SaleOrigin.LESPASS: "WEB",
    SaleOrigin.API: "WEB",
    SaleOrigin.EXTERNAL: "WEB",
    SaleOrigin.WEBHOOK: "WEB",
    SaleOrigin.ADMIN: "ADMIN",
}

# Le libellé de chaque journal d'origine, écrit dans le FEC (`JournalLib`). Le journal
# d'un point de vente a pour libellé le nom du point de vente. Ce sont des DONNÉES,
# comme un libellé de compte : jamais `_()`.
# / The label of each origin journal, written in the FEC. Data, never `_()`.
LIBELLE_DU_JOURNAL_SANS_POINT_DE_VENTE = {
    "CAISSE": "Caisse",
    "TIREUSE": "Tireuse",
    "WEB": "Ventes en ligne",
    "ADMIN": "Administration",
}

LONGUEUR_MAXIMALE_D_UN_CODE_JOURNAL = 10


def _lettres_d_un_code_journal(texte):
    """
    Les lettres d'un texte, comme un code journal les veut : majuscules, sans accent,
    lettres A à Z seulement, 10 au plus. « Buvette d'Été 2 » → « BUVETTEDET ».
    Rend "" si le texte ne contient aucune lettre.
    / A text's letters, as a journal code wants them. Returns "" without any letter.
    """
    # NFKD sépare la lettre de son accent (« É » → « E » + accent) ; on ne garde que
    # les lettres A à Z.
    # / NFKD splits a letter from its accent; only A to Z letters are kept.
    texte_decompose = unicodedata.normalize("NFKD", texte.upper())
    lettres_du_texte = []
    for caractere in texte_decompose:
        if "A" <= caractere <= "Z":
            lettres_du_texte.append(caractere)
    return "".join(lettres_du_texte)[:LONGUEUR_MAXIMALE_D_UN_CODE_JOURNAL]


def code_journal_du_point_de_vente(point_de_vente):
    """
    Le code journal d'un point de vente : son code renseigné, sinon son nom, nettoyé
    par la même règle (majuscules, sans accent, lettres A à Z seulement, 10 au plus).
    / A point of sale's journal code: its set code, else its name, cleaned by the same
    rule.

    « Buvette d'Été 2 » → « BUVETTEDET » ; code renseigné « bar2 » → « BAR ».

    Le code renseigné est nettoyé ici : le validateur du champ ne tourne que dans
    l'admin, et un code posé autrement (shell, API, migration) arriverait tel quel au
    FEC et aux logiciels comptables. Les collisions comparent donc des codes nettoyés.
    / The set code is cleaned here: the field validator only runs in the admin.

    :raises CompteComptableManquant: si le code renseigné, ou à défaut le nom, ne
        contient aucune lettre
    """
    if point_de_vente.code_journal:
        code_nettoye = _lettres_d_un_code_journal(point_de_vente.code_journal)
        if code_nettoye == "":
            raise CompteComptableManquant(
                f"Le code journal « {point_de_vente.code_journal} » du point de vente "
                f"« {point_de_vente.name} » ne contient aucune lettre."
            )
        return code_nettoye

    code_derive = _lettres_d_un_code_journal(point_de_vente.name)
    if code_derive == "":
        raise CompteComptableManquant(
            f"Le point de vente « {point_de_vente.name} » n'a pas de code journal, "
            f"et son nom ne contient aucune lettre pour en dériver un."
        )
    return code_derive


def journal_pour(point_de_vente, origine):
    """
    Le code du journal comptable d'une vente.
    / The accounting journal code of a sale.

    LOCALISATION : laboutik/plan_comptable.py (fiche E §3.2)

    Le point de vente gagne toujours quand il existe, quelle que soit l'origine (une
    tireuse a son point de vente : son code, pas « TIREUSE »). Sans point de vente :
    la table des origines.
    / The point of sale always wins. Without it: the origin table.

    :param point_de_vente: le `PointDeVente` de la vente, ou None
    :param origine: code `SaleOrigin` de la vente (ex. "LB", "LP")
    :return: le code journal (str)
    :raises CompteComptableManquant: si l'origine n'est pas dans la table
    """
    if point_de_vente is not None:
        return code_journal_du_point_de_vente(point_de_vente)

    journal_de_l_origine = JOURNAL_PAR_ORIGINE.get(origine)
    if journal_de_l_origine is None:
        raise CompteComptableManquant(
            f"L'origine de vente « {origine} » n'a pas de journal."
        )
    return journal_de_l_origine


def _points_de_vente_par_code_journal():
    """
    Les points de vente du lieu, regroupés par code journal, triés par nom.
    Un point de vente sans code possible (code renseigné ou nom sans lettre) est sauté
    ici, et rendu à part par `points_de_vente_sans_code_journal()`.
    / The venue's points of sale grouped by journal code; one without a possible code
    is skipped.

    :return: dict {code journal: [PointDeVente, ...]}
    """
    points_de_vente_du_lieu = PointDeVente.objects.order_by("name")
    points_de_vente_par_code = {}
    for point_de_vente in points_de_vente_du_lieu:
        try:
            code = code_journal_du_point_de_vente(point_de_vente)
        except CompteComptableManquant:
            continue
        if code not in points_de_vente_par_code:
            points_de_vente_par_code[code] = []
        points_de_vente_par_code[code].append(point_de_vente)
    return points_de_vente_par_code


def collisions_de_codes_journal():
    """
    Les codes journal portés par plusieurs points de vente. « Plan complet ? » les
    signale et l'export est refusé (D23).
    / Journal codes carried by several points of sale.

    LOCALISATION : laboutik/plan_comptable.py (fiche E §3.2)

    Un point de vente sans code possible est sauté (il ne cache pas la collision des
    autres).
    / A point of sale without possible code is skipped.

    :return: dict {code journal: [PointDeVente, ...]}, seulement les codes en double
    """
    collisions = {}
    points_de_vente_par_code = _points_de_vente_par_code_journal()
    for code, points_de_vente in points_de_vente_par_code.items():
        if len(points_de_vente) > 1:
            collisions[code] = points_de_vente
    return collisions


def points_de_vente_au_code_journal_reserve():
    """
    Les points de vente dont le code journal est celui d'un journal d'origine
    (`JOURNAL_PAR_ORIGINE` : CAISSE, TIREUSE, WEB, ADMIN), par exemple un point de vente
    nommé « Caisse ». Ces codes sont réservés aux ventes sans point de vente : sinon les
    deux se mêleraient dans un journal. « Plan complet ? » les signale et l'export est
    refusé.
    / Points of sale whose journal code is an origin journal's code (reserved).

    LOCALISATION : laboutik/plan_comptable.py (fiche E §3.2)

    :return: dict {code journal réservé: [PointDeVente, ...]}
    """
    codes_reserves_aux_origines = set()
    for code_du_journal_d_origine in JOURNAL_PAR_ORIGINE.values():
        codes_reserves_aux_origines.add(code_du_journal_d_origine)

    points_de_vente_au_code_reserve = {}
    points_de_vente_par_code = _points_de_vente_par_code_journal()
    for code, points_de_vente in points_de_vente_par_code.items():
        if code in codes_reserves_aux_origines:
            points_de_vente_au_code_reserve[code] = points_de_vente
    return points_de_vente_au_code_reserve


def points_de_vente_sans_code_journal():
    """
    Les points de vente sans code journal possible : leur code renseigné ne contient
    aucune lettre, ou, sans code renseigné, leur nom n'en contient aucune.
    « Plan complet ? » les signale.
    / Points of sale without a possible journal code (set code or name without letter).

    LOCALISATION : laboutik/plan_comptable.py (fiche E §3.2)

    :return: liste de PointDeVente, triée par nom
    """
    points_de_vente_sans_code = []
    for point_de_vente in PointDeVente.objects.order_by("name"):
        try:
            code_journal_du_point_de_vente(point_de_vente)
        except CompteComptableManquant:
            points_de_vente_sans_code.append(point_de_vente)
    return points_de_vente_sans_code


# Règle 0 : les recharges dont l'argent est une avance du client (419100).
# / Rule 0: top-ups whose money is a customer advance.
METHODES_CAISSE_DES_RECHARGES = [Product.RECHARGE_EUROS, Product.RECHARGE_CADEAU]
TYPES_DE_PRODUIT_DES_RECHARGES = [
    Product.RECHARGE_CASHLESS,
    Product.RECHARGE_CASHLESS_FED,
]

# Les modes de caisse sans compte : TM (désactivé à la caisse) et FD (inutilisé).
# / POS methods without account: TM (disabled) and FD (unused).
METHODES_CAISSE_SANS_COMPTE = [Product.RECHARGE_TEMPS, Product.FIDELITE]

# Règle 3 : le mode de caisse donne le compte. VT et FR exigent une catégorie.
# / Rule 3: the POS method gives the account. VT and FR require a category.
COMPTE_PAR_METHODE_CAISSE = {
    Product.ADHESION_POS: "cotisations",
    Product.BILLET_POS: "prestations",
}
METHODES_CAISSE_QUI_EXIGENT_UNE_CATEGORIE = [Product.VENTE, Product.FRACTIONNE_POS]

# Règle 4 : le type de produit donne le compte (vente en ligne).
# / Rule 4: the product type gives the account (online sale).
COMPTE_PAR_TYPE_DE_PRODUIT = {
    Product.BILLET: "prestations",
    Product.FREERES: "prestations",
    Product.BADGE: "prestations",
    Product.QRCODE_MA: "prestations",
    Product.RESOURCE: "prestations",
    Product.ADHESION: "cotisations",
}


def compte_pour_article(ligne, comptes_du_plan_par_defaut=None):
    """
    Le compte (de vente, de tiers…) d'un article vendu.
    / The account of a sold item.

    LOCALISATION : laboutik/plan_comptable.py (fiche E §3.3)

    RÈGLE, dans l'ordre (le premier qui répond gagne) :
    0. Une liste explicite d'articles hors chiffre d'affaires. Leur catégorie de caisse
       est IGNORÉE (une recharge rangée dans une catégorie 7xx irait sinon au chiffre
       d'affaires) :
       - les écarts d'encaissement, par leur nom : 758000 (reçu en plus), 658000 (reçu
         en moins) ;
       - les recharges `RE`, `RC` (caisse), `R`, `E` (en ligne) : 419100 ;
       - le virement du pot central `VR` : le compte de la monnaie de la ligne ;
       - les jetons cadeau repris au vidage, par leur nom : 623400.
    0 bis. `TM` et `FD` : erreur, avec ou sans catégorie.
    1. Retour de consigne `CR` : le compte de la catégorie de la consigne remboursée.
    2. La catégorie de caisse du produit a un compte : ce compte.
    3. Le mode de caisse : `AD` → 756000, `BI` → 706000 ; `VT`, `FR` : erreur (la
       catégorie est exigée).
    4. Le type de produit : `B`, `F`, `G`, `Q`, `C` → 706000, `A` → 756000.
    5. Sinon : erreur.
    / Rules in order: 0 explicit off-revenue list (category ignored), TM/FD error,
    1 deposit return, 2 POS category, 3 POS method, 4 product type, 5 error.

    LA PART EN JETONS (D8 bis) : ce compte est celui du RESTE de l'article (net − part
    payée en jetons). La part en jetons va au compte des ventes réglées en jetons
    (707900), écrit par la ventilation (comptabilite/ventilation.py). Une ligne
    entièrement en jetons n'a pas de reste : la ventilation n'appelle pas cette règle
    pour elle, et « Plan complet ? » ne lui demande pas de compte.
    / This account is the one of the item's REMAINDER; the token part goes to 707900,
    written by the ventilation.

    :param ligne: la `LigneArticle` (lue seulement : son produit, sa monnaie)
    :param comptes_du_plan_par_defaut: dict {numéro: CompteComptable} des comptes du
        plan par défaut, déjà lus par l'appelant en UNE requête. Il sert à
        `ce_qui_manque_pour_exporter`, qui appelle cette règle pour chaque produit
        vendu : sans lui, chaque produit relirait son compte en base. Les autres
        appelants n'en ont pas besoin : sans lui (None), le compte est lu en base.
        / Default plan accounts already read by the caller in ONE query; only
        "Complete plan?" needs it, other callers leave it None.
    :return: le `CompteComptable`
    :raises CompteComptableManquant: si aucune règle ne donne de compte
        (`CompteDuPlanParDefautManquant` si c'est un compte du plan par défaut qui
        manque)
    """
    produit = ligne.pricesold.productsold.product

    # --- 0. Hors chiffre d'affaires, liste explicite / Off revenue, explicit list ---
    # Les écarts sont reconnus par le nom de leur produit système
    # (`tarif_vendu_d_ecart_d_encaissement`, BaseBillet/services_vente.py).
    # / Gaps are recognised by their system product's name.
    if produit.name == NOM_ECART_RECU_EN_PLUS:
        return _compte_du_plan_par_defaut(
            "ecart_recu_en_plus", comptes_du_plan_par_defaut
        )
    if produit.name == NOM_ECART_RECU_EN_MOINS:
        return _compte_du_plan_par_defaut(
            "ecart_recu_en_moins", comptes_du_plan_par_defaut
        )

    # Les jetons cadeau repris au vidage (produit système, par son nom) : la dette des
    # jetons perdus est annulée, au compte des cadeaux (D8 bis).
    # / Gift tokens taken back at card emptying: the lost tokens' debt is cancelled.
    if produit.name == NOM_JETONS_CADEAU_REPRIS_AU_VIDAGE:
        return _compte_du_plan_par_defaut(
            "cadeaux_a_la_clientele", comptes_du_plan_par_defaut
        )

    est_une_recharge = (
        produit.methode_caisse in METHODES_CAISSE_DES_RECHARGES
        or produit.categorie_article in TYPES_DE_PRODUIT_DES_RECHARGES
    )
    if est_une_recharge:
        return _compte_du_plan_par_defaut(
            "avances_clients", comptes_du_plan_par_defaut
        )

    if produit.methode_caisse == Product.VIREMENT_RECU:
        compte_de_la_monnaie = None
        if ligne.asset is not None:
            compte_de_la_monnaie = _compte_de_la_monnaie(ligne.asset)
        if compte_de_la_monnaie is None:
            raise CompteComptableManquant(
                f"Le virement « {produit.name} » va au compte de sa monnaie, et la "
                f"monnaie « {ligne.asset} » n'a pas de compte."
            )
        return compte_de_la_monnaie

    # --- 0 bis. Modes sans compte / Methods without account ---
    if produit.methode_caisse in METHODES_CAISSE_SANS_COMPTE:
        raise CompteComptableManquant(
            f"Le produit « {produit.name} » a un mode de caisse sans compte "
            f"(« {produit.methode_caisse} »)."
        )

    # --- 1. Retour de consigne / Deposit return ---
    if produit.methode_caisse == Product.RETOUR_CONSIGNE:
        consigne_remboursee = produit.consigne_remboursee
        compte_de_la_consigne = None
        if consigne_remboursee is not None and consigne_remboursee.categorie_pos:
            compte_de_la_consigne = consigne_remboursee.categorie_pos.compte_comptable
        if compte_de_la_consigne is None:
            raise CompteComptableManquant(
                f"Le retour de consigne « {produit.name} » prend le compte de la "
                f"catégorie de sa consigne, et elle n'en a pas."
            )
        return compte_de_la_consigne

    # --- 2. La catégorie de caisse / The POS category ---
    categorie_de_caisse = produit.categorie_pos
    if categorie_de_caisse is not None and categorie_de_caisse.compte_comptable:
        return categorie_de_caisse.compte_comptable

    # --- 3. Le mode de caisse / The POS method ---
    cle_du_mode_de_caisse = COMPTE_PAR_METHODE_CAISSE.get(produit.methode_caisse)
    if cle_du_mode_de_caisse is not None:
        return _compte_du_plan_par_defaut(
            cle_du_mode_de_caisse, comptes_du_plan_par_defaut
        )
    if produit.methode_caisse in METHODES_CAISSE_QUI_EXIGENT_UNE_CATEGORIE:
        raise CompteComptableManquant(
            f"Le produit « {produit.name} » n'a pas de catégorie de caisse reliée à "
            f"un compte."
        )

    # --- 4. Le type de produit / The product type ---
    cle_du_type_de_produit = COMPTE_PAR_TYPE_DE_PRODUIT.get(produit.categorie_article)
    if cle_du_type_de_produit is not None:
        return _compte_du_plan_par_defaut(
            cle_du_type_de_produit, comptes_du_plan_par_defaut
        )

    # --- 5. Aucune règle / No rule ---
    raise CompteComptableManquant(
        f"Le produit « {produit.name} » n'a pas de compte : posez-lui une catégorie "
        f"de caisse reliée à un compte."
    )


def compte_de_tva_pour_taux(taux_de_tva):
    """
    Le compte de TVA collectée d'un taux.
    / The collected VAT account of a rate.

    LOCALISATION : laboutik/plan_comptable.py (fiche E §3.4)

    La TVA est cherchée par son TAUX, jamais par son numéro : un lieu peut renuméroter
    ses comptes de TVA. Un compte actif de ce taux d'abord (le plus petit numéro s'il
    y en a plusieurs) ; sinon un compte inactif de ce taux. « Inactif »
    (`est_actif=False`) cache seulement le compte des menus de choix : l'export s'en
    sert quand même.
    Un taux de 0 n'écrit pas de TVA : l'appelant ne demande pas son compte.
    / VAT is looked up by rate, never by number. An active account of that rate first
    (lowest number), otherwise an inactive one: "inactive" only hides the account from
    choice menus, the export still uses it.

    APPELÉE PAR : `comptabilite/ventilation.py` (ventilation d'une clôture J).

    :param taux_de_tva: le taux en pour cent (Decimal), celui de la ligne vendue
    :return: le `CompteComptable` de TVA
    :raises CompteComptableManquant: si aucun compte de TVA n'a ce taux
    """
    # Tri : les comptes actifs avant les inactifs (True avant False en ordre
    # décroissant), puis le plus petit numéro.
    # / Sort: active accounts first, then the lowest number.
    compte_de_tva = (
        CompteComptable.objects.filter(
            nature_du_compte=CompteComptable.TVA,
            taux_de_tva=taux_de_tva,
        )
        .order_by("-est_actif", "numero_de_compte")
        .first()
    )
    if compte_de_tva is None:
        raise CompteComptableManquant(
            f"Le plan n'a pas de compte de TVA au taux de "
            f"{_format_du_taux(Decimal(taux_de_tva))} %."
        )
    return compte_de_tva


# --------------------------------------------------------------------------- #
#  Les écrans du plan (fiche E §4) / The plan screens (sheet E §4)            #
# --------------------------------------------------------------------------- #

# Les catégories de monnaie qui portent de l'argent : fiduciaire du lieu (TLF),
# cadeau (TNF), fédérée (FED). Les mêmes codes dans les deux moteurs. Les points, le
# temps, l'adhésion et le badge n'écrivent pas d'argent : pas de compte.
# / Currency categories carrying money, same codes in both engines.
CATEGORIES_DE_MONNAIE_AVEC_ARGENT = ["TLF", "TNF", "FED"]
CATEGORIE_DE_LA_MONNAIE_FEDEREE = "FED"

# Le moyen dont une monnaie DU LIEU prend le compte quand elle n'a pas le sien
# (fiche E §3.1, `compte_pour_reglement`, règle 4).
# / The method whose account a venue currency takes when it has none.
MOYEN_DE_REPLI_PAR_CATEGORIE_DE_MONNAIE = {
    "TLF": PaymentMethod.LOCAL_EURO,
    "TNF": PaymentMethod.LOCAL_GIFT,
}


def noms_des_monnaies(uuids_des_monnaies):
    """
    Le nom lisible de plusieurs monnaies, cherché dans les deux moteurs (fedow_core
    d'abord, puis l'ancien Fedow pour celles qui n'y sont pas), en deux requêtes au
    plus, quel que soit le nombre de monnaies.
    / The readable names of several currencies, looked up in both engines, in two
    queries at most.

    LOCALISATION : laboutik/plan_comptable.py

    Une monnaie introuvable dans les deux moteurs n'est pas dans le dictionnaire :
    l'appelant choisit son repli.
    / A currency found in neither engine is left out: the caller picks its fallback.

    :param uuids_des_monnaies: uuids (objets UUID ou textes)
    :return: dict {uuid en texte: nom}
    """
    uuids_en_texte = set()
    for uuid_de_la_monnaie in uuids_des_monnaies:
        uuids_en_texte.add(str(uuid_de_la_monnaie))

    nom_par_uuid = {}
    if not uuids_en_texte:
        return nom_par_uuid

    monnaies_fedow_core = list(Asset.objects.filter(uuid__in=uuids_en_texte))
    for monnaie in monnaies_fedow_core:
        nom_par_uuid[str(monnaie.uuid)] = monnaie.name

    uuids_pas_encore_trouves = set()
    for uuid_en_texte in uuids_en_texte:
        if uuid_en_texte not in nom_par_uuid:
            uuids_pas_encore_trouves.add(uuid_en_texte)
    if not uuids_pas_encore_trouves:
        return nom_par_uuid

    monnaies_de_l_ancien_fedow = list(
        AssetFedowPublic.objects.filter(uuid__in=uuids_pas_encore_trouves)
    )
    for monnaie in monnaies_de_l_ancien_fedow:
        nom_par_uuid[str(monnaie.uuid)] = monnaie.name
    return nom_par_uuid


def nom_de_la_monnaie(asset_uuid):
    """
    Le nom lisible d'une monnaie, cherché dans les deux moteurs (fedow_core, puis
    ancien Fedow) par `noms_des_monnaies`. L'uuid en texte si elle est introuvable.
    / The readable name of a currency, looked up in both engines.
    """
    nom_par_uuid = noms_des_monnaies([asset_uuid])
    return nom_par_uuid.get(str(asset_uuid), str(asset_uuid))


def _ligne_d_une_monnaie(asset_uuid, nom, categorie, est_du_lieu):
    """
    Une ligne de l'écran « Comptes des monnaies ».
    / One row of the "Currency accounts" screen.

    RÈGLE (la même que `compte_pour_reglement`) :
    - la monnaie a son compte : ce compte ;
    - sinon, une monnaie DU LIEU (fiduciaire ou cadeau) prend le compte de son moyen
      (LE ou LG) : affiché en neutre, l'export passe ;
    - sinon (monnaie d'un autre lieu, ou fédérée) : compte manquant, l'export la
      refuse.
    / Own account; else a venue currency takes its method's account; else missing.

    Ni correspondance ni compte du moyen : le compte manque (l'écran le montre en
    orange, `monnaies_changelist_before.html`).
    / Neither mapping nor method account: the account is missing (orange on screen).

    :return: dict avec "uuid", "nom", "origine", "correspondance" (MappingMonnaie ou
        None), "compte_du_moyen" (CompteComptable ou None)
    """
    if categorie == CATEGORIE_DE_LA_MONNAIE_FEDEREE:
        origine = gettext("fédérée")
    elif est_du_lieu:
        origine = gettext("ce lieu")
    else:
        origine = gettext("un autre lieu")

    correspondance_de_la_monnaie = (
        MappingMonnaie.objects.select_related("compte_de_tresorerie")
        .filter(asset_uuid=asset_uuid)
        .first()
    )

    compte_du_moyen = None
    if correspondance_de_la_monnaie is None:
        moyen_de_repli = MOYEN_DE_REPLI_PAR_CATEGORIE_DE_MONNAIE.get(categorie)
        la_monnaie_prend_le_compte_de_son_moyen = (
            est_du_lieu and moyen_de_repli is not None
        )
        if la_monnaie_prend_le_compte_de_son_moyen:
            correspondance_du_moyen = (
                MappingMoyenDePaiement.objects.select_related("compte_de_tresorerie")
                .filter(moyen_de_paiement=moyen_de_repli)
                .first()
            )
            if correspondance_du_moyen is not None:
                compte_du_moyen = correspondance_du_moyen.compte_de_tresorerie

    return {
        "uuid": asset_uuid,
        "nom": nom,
        "origine": origine,
        "correspondance": correspondance_de_la_monnaie,
        "compte_du_moyen": compte_du_moyen,
    }


def monnaies_acceptees_par_le_lieu():
    """
    Les monnaies acceptées par le lieu courant, avec leur compte : une ligne par
    monnaie, triée par nom.
    / The currencies accepted by the current venue, with their account.

    LOCALISATION : laboutik/plan_comptable.py (fiche E §4)

    Acceptées :
    - fedow_core : `AssetService.obtenir_assets_accessibles` (les monnaies du lieu et
      celles partagées par une fédération) ;
    - ancien Fedow (`fedow_public.AssetFedowPublic`) : les monnaies créées par le lieu,
      celles fédérées avec lui (`federated_with`), et le FED.
    Sans les monnaies archivées, ni celles qui n'écrivent pas d'argent (points, temps,
    adhésion, badge).
    / fedow_core accessible assets, and old-Fedow ones created by or federated with
    the venue, plus the FED. Without archived or non-money currencies.

    :return: liste de dict (voir `_ligne_d_une_monnaie`)
    """
    # Le lieu est lu par le nom du schéma : `connection.tenant` peut être un
    # FakeTenant (schema_context) qui n'a pas d'uuid.
    # / The venue is read through the schema name (FakeTenant has no uuid).
    nom_du_schema_du_lieu = connection.schema_name
    lieu = Client.objects.filter(schema_name=nom_du_schema_du_lieu).first()

    lignes_des_monnaies = []

    if lieu is not None:
        monnaies_fedow_core = AssetService.obtenir_assets_accessibles(lieu).filter(
            archive=False,
            category__in=CATEGORIES_DE_MONNAIE_AVEC_ARGENT,
        )
        for monnaie in monnaies_fedow_core:
            lignes_des_monnaies.append(
                _ligne_d_une_monnaie(
                    monnaie.uuid,
                    monnaie.name,
                    monnaie.category,
                    est_du_lieu=(monnaie.tenant_origin_id == lieu.pk),
                )
            )

    monnaies_ancien_fedow = (
        AssetFedowPublic.objects.filter(
            archive=False,
            category__in=CATEGORIES_DE_MONNAIE_AVEC_ARGENT,
        )
        .filter(
            Q(origin__schema_name=nom_du_schema_du_lieu)
            | Q(federated_with__schema_name=nom_du_schema_du_lieu)
            | Q(category=CATEGORIE_DE_LA_MONNAIE_FEDEREE)
        )
        .distinct()
    )
    for monnaie in monnaies_ancien_fedow:
        est_du_lieu = lieu is not None and monnaie.origin_id == lieu.pk
        lignes_des_monnaies.append(
            _ligne_d_une_monnaie(
                monnaie.uuid,
                monnaie.name,
                monnaie.category,
                est_du_lieu=est_du_lieu,
            )
        )

    def nom_pour_le_tri(ligne_de_la_monnaie):
        return ligne_de_la_monnaie["nom"].lower()

    lignes_des_monnaies.sort(key=nom_pour_le_tri)
    return lignes_des_monnaies


def _format_du_taux(taux_de_tva):
    """
    Un taux de TVA écrit à la française : 5.50 → « 5,5 », 20.00 → « 20 ».
    / A VAT rate written the French way.
    """
    taux_sans_zeros_inutiles = format(taux_de_tva.normalize(), "f")
    return taux_sans_zeros_inutiles.replace(".", ",")


def ce_qui_manque_pour_exporter():
    """
    « Plan complet ? » : ce qui manque au plan pour que l'export comptable passe.
    / "Complete plan?": what the plan lacks for the accounting export to pass.

    LOCALISATION : laboutik/plan_comptable.py (fiche E §4)

    Appelle d'abord le filet `s_assurer_que_le_plan_existe()`. « Utilisé » veut dire :
    présent dans une vente RÉGLÉE du lieu. Lecture seule, sauf le filet.
    / Calls the safety net first. "Used" means: in a SETTLED sale of the venue.

    LES MANQUES, dans cet ordre :
    1. un produit vendu en euros sans compte (`compte_pour_article` lève) ; si la
       cause est un compte du plan par défaut supprimé, un seul manque par numéro,
       qui renvoie au bouton « Charger le plan par défaut ». Une ligne entièrement
       payée en jetons n'exige pas de compte de produit ;
    1 bis. le compte des ventes réglées en jetons (707900) absent, alors qu'un article
       a une part payée en jetons (même phrase que ci-dessus) ;
    2. un moyen de paiement utilisé sans compte ;
    3. une monnaie utilisée sans compte (monnaie d'un autre lieu, ou FED) ;
    4. un taux de TVA utilisé sans compte de TVA à ce taux (0 %, ou des lignes sans
       TVA, n'en exigent pas) ;
    5. deux points de vente au même code journal ; 5 bis. un point de vente au code
       d'un journal d'origine (CAISSE, TIREUSE, WEB, ADMIN) ;
    6. un point de vente sans code journal possible (code renseigné ou nom sans
       lettre) ;
    7. des règlements au compte d'attente 471000 (moyen inconnu), à reclasser.

    APPELÉ PAR : le bouton « Vérifier le plan » des trois écrans du plan dans
    l'admin (`Administration/admin/laboutik.py` CompteComptableAdmin.verifier_le_plan,
    composant `Administration/templates/admin/comptable/plan_complet.html`). Il relit
    tout l'historique du lieu : il n'est jamais appelé à l'ouverture d'un écran.

    :return: liste de dict {"phrase": texte pour un bénévole, "lien": URL de l'écran
        qui règle le manque} ; vide si le plan est complet
    """
    s_assurer_que_le_plan_existe()

    manques = []
    lien_du_plan = reverse("staff_admin:laboutik_comptecomptable_changelist")
    lien_des_moyens = reverse("staff_admin:laboutik_mappingmoyendepaiement_changelist")
    lien_des_monnaies = reverse("staff_admin:laboutik_mappingmonnaie_changelist")
    lien_des_points_de_vente = reverse("staff_admin:laboutik_pointdevente_changelist")
    lien_des_categories = reverse("staff_admin:BaseBillet_categorieproduct_changelist")
    # Les ventes qui ont un règlement au compte d'attente (moyen inconnu) : la liste des
    # ventes, filtrée sur ce moyen (filtre « Moyen de paiement », paramètre `moyen`).
    # / The sales with a payment to the suspense account: the sales list, filtered.
    lien_des_ventes_au_moyen_inconnu = (
        reverse("staff_admin:BaseBillet_vente_changelist")
        + "?"
        + urlencode({"moyen": PaymentMethod.UNKNOWN})
    )

    # Les comptes du plan par défaut, lus en UNE requête pour tout l'appel : la règle
    # du compte d'un article les cherche dans ce dict au lieu de relire la base pour
    # chaque produit. Variable locale : rien ne survit à l'appel.
    # / Default plan accounts, read in ONE query for the whole call. Local variable.
    comptes_du_plan_par_defaut = comptes_du_plan_par_defaut_du_lieu()

    # --- 1. Produits vendus sans compte / Products sold without account ---
    # Une ligne par couple (produit, monnaie) suffit : la règle ne lit que le produit
    # et la monnaie de la ligne (DISTINCT ON de Postgres), jamais son moyen.
    # Les ventes en points (`unite` ≠ "EUR") n'ont pas d'écriture comptable (fiche F
    # §4) : leurs produits n'ont pas besoin de compte.
    # Une ligne ENTIÈREMENT payée en jetons (part en jetons = net, non nul) n'a pas de
    # reste : tout va au compte des ventes réglées en jetons, rien au compte du
    # produit. Elle n'exige donc pas de compte de produit (vérifiée plus bas, par le
    # 707900).
    # Le `select_related` lit d'un coup ce que la règle lit : la catégorie du produit
    # et son compte (règle 2), la catégorie de la consigne remboursée et son compte
    # (règle 1). Sans lui, chaque produit vendu coûterait une à deux requêtes.
    # / One line per (product, currency) pair is enough; the line's method is never
    # read. Points sales write no entry: skipped. A fully token-paid line needs no
    # product account. The select_related reads what the rule reads, in one query.
    lignes_entierement_en_jetons = Q(part_en_jetons=F("total_ttc")) & ~Q(
        part_en_jetons=0
    )
    lignes_representatives = (
        LigneArticle.objects.filter(
            vente__statut=Vente.Statut.REGLEE,
            vente__unite="EUR",
        )
        .exclude(lignes_entierement_en_jetons)
        .select_related(
            "pricesold__productsold__product__categorie_pos__compte_comptable",
            "pricesold__productsold__product__consigne_remboursee__categorie_pos__compte_comptable",
        )
        .order_by("pricesold__productsold__product_id", "asset")
        .distinct("pricesold__productsold__product_id", "asset")
    )
    produits_deja_signales = set()
    numeros_du_plan_par_defaut_deja_signales = set()
    for ligne in lignes_representatives:
        produit = ligne.pricesold.productsold.product
        if produit.pk in produits_deja_signales:
            continue
        try:
            compte_pour_article(ligne, comptes_du_plan_par_defaut)
        except CompteDuPlanParDefautManquant as erreur:
            # Un compte du plan par défaut a été supprimé : la phrase nomme le numéro
            # et le bouton qui le remet. Un seul manque par numéro, même si plusieurs
            # produits en dépendent.
            # / A default plan account was deleted: one item per missing number.
            produits_deja_signales.add(produit.pk)
            numero_manquant = erreur.numero_de_compte
            if numero_manquant in numeros_du_plan_par_defaut_deja_signales:
                continue
            numeros_du_plan_par_defaut_deja_signales.add(numero_manquant)
            manques.append(
                {
                    "phrase": gettext(
                        "Le compte %(numero)s du plan par défaut manque. Le bouton "
                        "« Charger le plan par défaut » le remet."
                    )
                    % {"numero": numero_manquant},
                    "lien": lien_du_plan,
                }
            )
        except CompteComptableManquant:
            produits_deja_signales.add(produit.pk)
            manques.append(
                {
                    "phrase": gettext(
                        "Le produit « %(nom)s » est vendu, mais il n'a pas de "
                        "compte. Rangez-le dans une catégorie de caisse reliée à un "
                        "compte."
                    )
                    % {"nom": produit.name},
                    "lien": lien_des_categories,
                }
            )

    # --- 1 bis. Le compte des ventes réglées en jetons / The token sales account ---
    # Dès qu'un article vendu en euros a une part payée en jetons, le FEC écrit cette
    # part au compte des ventes réglées en jetons (707900) : il doit exister.
    # / As soon as a euro item has a token part, the FEC writes it to 707900.
    des_articles_ont_une_part_en_jetons = (
        LigneArticle.objects.filter(
            vente__statut=Vente.Statut.REGLEE,
            vente__unite="EUR",
        )
        .exclude(part_en_jetons=0)
        .exists()
    )
    if des_articles_ont_une_part_en_jetons:
        try:
            compte_des_ventes_reglees_en_jetons(comptes_du_plan_par_defaut)
        except CompteDuPlanParDefautManquant as erreur:
            numero_manquant = erreur.numero_de_compte
            if numero_manquant not in numeros_du_plan_par_defaut_deja_signales:
                numeros_du_plan_par_defaut_deja_signales.add(numero_manquant)
                manques.append(
                    {
                        "phrase": gettext(
                            "Le compte %(numero)s du plan par défaut manque. Le "
                            "bouton « Charger le plan par défaut » le remet."
                        )
                        % {"numero": numero_manquant},
                        "lien": lien_du_plan,
                    }
                )

    # --- 2 et 3. Moyens et monnaies utilisés sans compte ---
    # Les sections 2, 3, 4 et 7 n'ont pas besoin d'écarter les ventes en points : une
    # vente en points n'a que des règlements « points ou temps » (NM), qui n'ont pas
    # de compte à chercher, et des lignes à TVA 0, qui n'exigent pas de compte de TVA.
    # / Sections 2, 3, 4 and 7 need not skip points sales: they only have NM payments
    # (no account to look up) and 0 % VAT lines.
    couples_moyen_monnaie_utilises = (
        Reglement.objects.filter(vente__statut=Vente.Statut.REGLEE)
        .order_by("moyen", "asset")
        .values_list("moyen", "asset")
        .distinct()
    )
    libelle_par_moyen = dict(PaymentMethod.choices)
    moyens_deja_signales = set()
    monnaies_deja_signalees = set()
    for moyen, asset_uuid in couples_moyen_monnaie_utilises:
        try:
            compte_pour_reglement(moyen, asset_uuid)
            continue
        except CompteComptableManquant:
            pass

        # La faute vient de la monnaie quand elle n'a pas de compte et ne peut pas
        # prendre celui de son moyen (FED, ou monnaie d'un autre lieu).
        # / The currency is at fault when it has no account and cannot take its
        # method's one.
        la_faute_vient_de_la_monnaie = (
            asset_uuid is not None
            and _compte_de_la_monnaie(asset_uuid) is None
            and (
                moyen == PaymentMethod.STRIPE_FED
                or not _la_monnaie_est_celle_du_lieu(asset_uuid)
            )
        )
        if la_faute_vient_de_la_monnaie:
            if asset_uuid in monnaies_deja_signalees:
                continue
            monnaies_deja_signalees.add(asset_uuid)
            manques.append(
                {
                    "phrase": gettext(
                        "La monnaie « %(nom)s » est utilisée, mais elle n'a pas de "
                        "compte. Choisissez son compte."
                    )
                    % {"nom": nom_de_la_monnaie(asset_uuid)},
                    "lien": lien_des_monnaies,
                }
            )
            continue

        if moyen in moyens_deja_signales:
            continue
        moyens_deja_signales.add(moyen)
        libelle_du_moyen = libelle_par_moyen.get(moyen, moyen)
        manques.append(
            {
                "phrase": gettext(
                    "Le moyen de paiement « %(moyen)s » est utilisé, mais il n'a pas "
                    "de compte. Choisissez son compte."
                )
                % {"moyen": f"{libelle_du_moyen} ({moyen})"},
                "lien": lien_des_moyens,
            }
        )

    # --- 4. Taux de TVA utilisés sans compte / VAT rates used without account ---
    # Un taux de 0 % n'écrit pas de TVA : il n'exige pas de compte. Une ligne dont la
    # TVA vaut 0 (entièrement payée en jetons, entièrement offerte) n'en écrit pas non
    # plus (comptabilite/ventilation.py `_ecrire_la_tva_de_l_article`) : elle n'exige
    # pas de compte à son taux. Un compte de TVA de ce taux suffit, actif ou non :
    # « inactif » ne cache le compte que des menus de choix, l'export s'en sert quand
    # même (`compte_de_tva_pour_taux`).
    # / A 0 % rate, or a line whose VAT is 0, writes no VAT: no account required. Any
    # VAT account of that rate, active or not, is enough (the export uses it).
    taux_de_tva_utilises = (
        LigneArticle.objects.filter(vente__statut=Vente.Statut.REGLEE)
        .exclude(vat=0)
        .exclude(total_tva=0)
        .order_by("vat")
        .values_list("vat", flat=True)
        .distinct()
    )
    for taux_de_tva in taux_de_tva_utilises:
        le_plan_a_ce_taux = CompteComptable.objects.filter(
            nature_du_compte=CompteComptable.TVA,
            taux_de_tva=taux_de_tva,
        ).exists()
        if le_plan_a_ce_taux:
            continue
        manques.append(
            {
                "phrase": gettext(
                    "Des ventes ont une TVA à %(taux)s %%, mais le plan n'a pas de "
                    "compte de TVA à ce taux. Ajoutez-le au plan comptable."
                )
                % {"taux": _format_du_taux(taux_de_tva)},
                "lien": lien_du_plan,
            }
        )

    # --- 5. Codes journal en double / Duplicate journal codes ---
    for code, points_de_vente in collisions_de_codes_journal().items():
        noms_des_points_de_vente = []
        for point_de_vente in points_de_vente:
            noms_des_points_de_vente.append(f"« {point_de_vente.name} »")
        manques.append(
            {
                "phrase": gettext(
                    "Les points de vente %(noms)s ont le même code journal "
                    "« %(code)s ». Donnez à chacun un code différent."
                )
                % {"noms": ", ".join(noms_des_points_de_vente), "code": code},
                "lien": lien_des_points_de_vente,
            }
        )

    # --- 5 bis. Codes journal réservés aux origines / Codes reserved to origins ---
    points_de_vente_par_code_reserve = points_de_vente_au_code_journal_reserve()
    for code, points_de_vente in points_de_vente_par_code_reserve.items():
        noms_des_points_de_vente = []
        for point_de_vente in points_de_vente:
            noms_des_points_de_vente.append(f"« {point_de_vente.name} »")
        manques.append(
            {
                "phrase": gettext(
                    "Le code journal « %(code)s » de %(noms)s est réservé aux ventes "
                    "sans point de vente. Donnez-lui un autre code."
                )
                % {"noms": ", ".join(noms_des_points_de_vente), "code": code},
                "lien": lien_des_points_de_vente,
            }
        )

    # --- 6. Points de vente sans code possible / Points of sale without code ---
    # La phrase dit ce qui ne contient aucune lettre : le code renseigné, ou le nom.
    # / The sentence says what has no letter: the set code, or the name.
    for point_de_vente in points_de_vente_sans_code_journal():
        if point_de_vente.code_journal:
            phrase_du_manque = gettext(
                "Le code journal « %(code)s » du point de vente « %(nom)s » ne "
                "contient aucune lettre. Donnez-lui un code en lettres."
            ) % {"code": point_de_vente.code_journal, "nom": point_de_vente.name}
        else:
            phrase_du_manque = gettext(
                "Donnez un code journal au point de vente « %(nom)s » : son nom "
                "ne contient aucune lettre."
            ) % {"nom": point_de_vente.name}
        manques.append(
            {
                "phrase": phrase_du_manque,
                "lien": reverse(
                    "staff_admin:laboutik_pointdevente_change",
                    args=[point_de_vente.pk],
                ),
            }
        )

    # --- 7. Règlements au compte d'attente / Payments to the suspense account ---
    nombre_de_reglements_au_compte_d_attente = Reglement.objects.filter(
        vente__statut=Vente.Statut.REGLEE,
        moyen=PaymentMethod.UNKNOWN,
    ).count()
    if nombre_de_reglements_au_compte_d_attente > 0:
        manques.append(
            {
                "phrase": ngettext(
                    "%(nombre)s règlement est au compte d'attente (471000), moyen de "
                    "paiement inconnu : à reclasser.",
                    "%(nombre)s règlements sont au compte d'attente (471000), moyen "
                    "de paiement inconnu : à reclasser.",
                    nombre_de_reglements_au_compte_d_attente,
                )
                % {"nombre": nombre_de_reglements_au_compte_d_attente},
                "lien": lien_des_ventes_au_moyen_inconnu,
            }
        )

    return manques
