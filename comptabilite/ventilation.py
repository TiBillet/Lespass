"""
La ventilation comptable d'une clôture J : une écriture par journal, équilibrée.
/ The accounting breakdown of a J closure: one balanced entry per journal.

LOCALISATION : comptabilite/ventilation.py

CE QUE FAIT CE MODULE
`ventiler_cloture(cloture_j)` lit les ventes réglées EN EUROS de la plage de la J
(`numero_premiere_vente` à `numero_derniere_vente`), leurs règlements et leurs
articles, et le plan comptable DU MOMENT (le calcul est refait à chaque export : rien
n'est figé dans la clôture). Chaque vente va entièrement dans un seul journal
(`journal_pour`). Pour chaque journal, une écriture :

| Côté   | Ligne                                                      | Montant           |
|--------|------------------------------------------------------------|-------------------|
| Débit  | règlement d'argent ou cashless (`compte_pour_reglement`)   | Σ règlements      |
| Crédit | article du chiffre d'affaires (`compte_pour_article`)      | Σ HT              |
| Crédit | TVA, par taux (`compte_de_tva_pour_taux`)                  | Σ TVA             |
| Crédit | article hors chiffre d'affaires (`compte_pour_article`)    | Σ TTC             |
| Débit  | recharge offerte : cadeaux à la clientèle (623400)         | Σ part offerte    |
| Crédit | recharge offerte : compte de la recharge (419100)          | Σ part offerte    |

- L'offert (FREE) et les points (NM) n'ont pas de compte : aucune ligne. Une vente en
  points n'est pas lue du tout.
- Un taux de TVA de 0 n'écrit aucune ligne de TVA.
- Les montants sont regroupés par compte dans chaque écriture : un compte n'a qu'une
  ligne, son solde net. Un solde négatif (avoir, espèces rendues, écart reçu en moins)
  passe du côté opposé, en positif. Un solde nul n'écrit pas de ligne.
- Chaque écriture est vérifiée : Σ débits = Σ crédits, sinon `EcritureDesequilibree`.
  Un compte manquant : `CompteComptableManquant` (laboutik/plan_comptable.py). Une
  vente rangée sous un code journal refusé (porté par plusieurs points de vente, ou
  réservé aux journaux d'origine) : `CompteComptableManquant` (des ventes se
  mêleraient dans un journal).

POURQUOI L'ÉCRITURE EST ÉQUILIBRÉE
Pour toute vente réglée en euros : Σ règlements hors offert = Σ nets des articles
(deuxième égalité, `encaisser_vente`) = Σ HT + Σ TVA (chiffre d'affaires) + Σ nets hors
chiffre d'affaires. La recharge offerte écrit ses deux côtés. La vérification attrape
une donnée altérée après l'encaissement.
/ For every settled euro sale, payments (offered excluded) = nets = HT + VAT + off
revenue nets. The check catches data altered after settlement.

LE NOMBRE DE REQUÊTES NE GRANDIT PAS AVEC LE NOMBRE DE VENTES
Les ventes d'une J, leurs règlements et leurs articles sont lus en trois requêtes.
Les comptes sont gardés dans des dictionnaires, remplis au fil de la lecture et
partagés par toutes les J d'un export : un compte par (moyen, monnaie), un compte de
TVA par taux, les comptes du plan par défaut lus une fois. Il ne reste, par J, que sa
première vente (la date) et ses trois requêtes de ventes. Un export d'un an (des
centaines de J, des milliers de ventes) se fait dans une requête HTTP de l'admin.
/ A J's sales, payments and items are read in three queries; accounts are kept in
dicts shared by every J of an export.

L'EXPORT D'UNE CLÔTURE (le FEC)
`ecritures_de_l_export(cloture)` rend les écritures à exporter, prêtes à écrire :
- une J : ses écritures ; une H / M / A : celles des J DATÉES dans la période ;
- chaque écriture porte sa date (date de début de service de sa J, dans le fuseau
  figé dans l'en-tête du rapport de la J), son numéro (« n° de la J-code journal »),
  sa pièce (n° de la J) et son libellé ;
- la date du nom du fichier : pour une J, sa date de début de service ; pour une
  H / M / A, son dernier jour local, dans son fuseau ;
- un compte manquant est relevé avec le numéro de la J en cause.

APPELÉE PAR : `comptabilite/fec.py` (`generer_fec_cloture`), le seul export comptable
du lieu ; `comptabilite/balance.py` (la balance du plan comptable), par
`ecritures_des_journees` et `journees_datees_entre` : la balance et le FEC lisent les
mêmes écritures.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-F-rapport-unique.md (§4).
Tests : tests/pytest/test_fec_equilibre.py (ventilation et FEC),
tests/pytest/test_comptabilite_exports.py (forme du FEC, bouton de la fiche),
tests/pytest/test_plan_comptable_unique.py (le FEC lit le plan du lieu),
tests/pytest/test_rapport_unique.py (test 26 : aucun prix × quantité).
"""

from datetime import datetime, time, timedelta, timezone as fuseau_utc
from zoneinfo import ZoneInfo

from django.db.models import Prefetch

from BaseBillet.models import LigneArticle
from BaseBillet.models_vente import Vente
from comptabilite.models import ClotureCaisse
from laboutik.plan_comptable import (
    LIBELLE_DU_JOURNAL_SANS_POINT_DE_VENTE,
    METHODES_CAISSE_DES_RECHARGES,
    TYPES_DE_PRODUIT_DES_RECHARGES,
    CompteComptableManquant,
    collisions_de_codes_journal,
    compte_des_cadeaux_a_la_clientele,
    compte_des_ventes_reglees_en_jetons,
    compte_de_tva_pour_taux,
    compte_pour_article,
    compte_pour_reglement,
    comptes_du_plan_par_defaut_du_lieu,
    journal_pour,
    points_de_vente_au_code_journal_reserve,
)


class EcritureDesequilibree(Exception):
    """
    Une écriture de la ventilation n'est pas équilibrée (Σ débits ≠ Σ crédits) :
    l'export est refusé. Le message nomme la clôture, le journal, les débits, les
    crédits et l'écart, en centimes.
    / An entry is not balanced: the export is refused. The message names the closure,
    the journal, debits, credits and the gap, in cents.

    LOCALISATION : comptabilite/ventilation.py
    """


def codes_journal_refuses_a_l_export():
    """
    Les codes journal sous lesquels aucune vente ne s'exporte, avec la phrase du refus :
    - un code porté par plusieurs points de vente (`collisions_de_codes_journal`) ;
    - un code d'un journal d'origine porté par un point de vente
      (`points_de_vente_au_code_journal_reserve`), par exemple un point de vente
      nommé « Caisse ».
    Dans les deux cas, des ventes différentes se mêleraient dans un journal (fiche E
    §3.2, D23). « Plan complet ? » signale les mêmes codes.
    / The journal codes under which no sale is exported, with the refusal sentence.

    APPELÉE une fois par export, par `ecritures_de_l_export`, même pour une année ;
    `ventiler_cloture` l'appelle elle-même quand on ne lui passe pas les codes.
    / Called once per export by ecritures_de_l_export; ventiler_cloture calls it
    itself when no codes are given.

    :return: dict {code journal: phrase du refus}
    """
    phrase_par_code_refuse = {}

    collisions = collisions_de_codes_journal()
    for code, points_de_vente in collisions.items():
        noms_des_points_de_vente = []
        for point_de_vente in points_de_vente:
            noms_des_points_de_vente.append(f"« {point_de_vente.name} »")
        phrase_par_code_refuse[code] = (
            f"Les points de vente {', '.join(noms_des_points_de_vente)} ont le même "
            f"code journal « {code} » : donnez à chacun un code différent."
        )

    points_de_vente_par_code_reserve = points_de_vente_au_code_journal_reserve()
    for code, points_de_vente in points_de_vente_par_code_reserve.items():
        noms_des_points_de_vente = []
        for point_de_vente in points_de_vente:
            noms_des_points_de_vente.append(f"« {point_de_vente.name} »")
        phrase_par_code_refuse[code] = (
            f"Le code journal « {code} » de {', '.join(noms_des_points_de_vente)} est "
            f"réservé aux ventes sans point de vente : donnez-lui un autre code."
        )
    return phrase_par_code_refuse


def _ajouter_au_compte(soldes_par_numero, compte, montant_au_debit):
    """
    Ajoute un montant au solde d'un compte de l'écriture. Le solde est compté au
    débit : un montant au crédit s'ajoute en négatif.
    / Adds a sum to an account's balance in the entry, counted on the debit side.

    :param soldes_par_numero: dict {numéro: {"compte": CompteComptable, "solde": int}}
    :param compte: le `CompteComptable`
    :param montant_au_debit: centimes (int), positif au débit, négatif au crédit
    """
    numero_du_compte = compte.numero_de_compte
    if numero_du_compte not in soldes_par_numero:
        soldes_par_numero[numero_du_compte] = {"compte": compte, "solde": 0}
    soldes_par_numero[numero_du_compte]["solde"] += montant_au_debit


def _ecrire_le_reglement(soldes_par_numero, reglement, compte_par_moyen_et_monnaie):
    """
    Un règlement d'argent ou cashless : son montant au débit du compte de son moyen et
    de sa monnaie. L'offert (FREE) et les points (NM) n'ont pas de compte : rien.
    La règle n'est appliquée qu'une fois par (moyen, monnaie) : son résultat est gardé
    dans `compte_par_moyen_et_monnaie`.
    / A money or cashless payment: debit of its method and currency account. The rule
    runs once per (method, currency).
    """
    cle_du_moyen_et_de_la_monnaie = (reglement.moyen, reglement.asset)
    if cle_du_moyen_et_de_la_monnaie not in compte_par_moyen_et_monnaie:
        compte_par_moyen_et_monnaie[cle_du_moyen_et_de_la_monnaie] = (
            compte_pour_reglement(reglement.moyen, reglement.asset)
        )
    compte_du_reglement = compte_par_moyen_et_monnaie[cle_du_moyen_et_de_la_monnaie]
    if compte_du_reglement is None:
        return
    _ajouter_au_compte(soldes_par_numero, compte_du_reglement, reglement.montant)


def _ecrire_l_article_du_chiffre_d_affaires(
    soldes_par_numero, ligne, comptes_du_plan_par_defaut
):
    """
    Un article du chiffre d'affaires : sa part payée en jetons au crédit du compte des
    ventes réglées en jetons (707900, hors TVA, D8 bis), puis le HT du reste au crédit
    du compte de l'article (`compte_pour_article`). Un article sans HT (entièrement
    offert) n'écrit rien. Un article entièrement payé en jetons n'écrit rien au compte
    de l'article, et n'en a pas besoin.
    / A revenue item: its token part credited to 707900 (no VAT), then the
    remainder's HT credited to the item's account. Nothing for a zero HT; nothing on
    the item's account for a fully token-paid item.
    """
    part_en_jetons = ligne.part_en_jetons
    if part_en_jetons != 0:
        compte_des_jetons = compte_des_ventes_reglees_en_jetons(
            comptes_du_plan_par_defaut
        )
        _ajouter_au_compte(soldes_par_numero, compte_des_jetons, -part_en_jetons)

    ht_du_reste = ligne.total_ht - part_en_jetons
    if ht_du_reste == 0:
        return
    compte_de_l_article = compte_pour_article(ligne, comptes_du_plan_par_defaut)
    _ajouter_au_compte(soldes_par_numero, compte_de_l_article, -ht_du_reste)


def _ecrire_la_tva_de_l_article(soldes_par_numero, ligne, compte_de_tva_par_taux):
    """
    La TVA d'un article du chiffre d'affaires : au crédit du compte de TVA de son
    taux. Un taux de 0, ou une TVA nulle, n'écrit rien. Le compte n'est cherché qu'une
    fois par taux : il est gardé dans `compte_de_tva_par_taux`.
    / A revenue item's VAT: credited to the VAT account of its rate, looked up once
    per rate.
    """
    if ligne.vat == 0 or ligne.total_tva == 0:
        return
    if ligne.vat not in compte_de_tva_par_taux:
        compte_de_tva_par_taux[ligne.vat] = compte_de_tva_pour_taux(ligne.vat)
    compte_de_la_tva = compte_de_tva_par_taux[ligne.vat]
    _ajouter_au_compte(soldes_par_numero, compte_de_la_tva, -ligne.total_tva)


def _ecrire_l_article_hors_chiffre_d_affaires(
    soldes_par_numero, ligne, comptes_du_plan_par_defaut
):
    """
    Un article hors chiffre d'affaires (recharge, écart d'encaissement, jetons repris
    au vidage, virement) : son TTC au crédit du compte de l'article (TVA 0).
    / An off-revenue item: its TTC credited to the item's account.
    """
    if ligne.total_ttc == 0:
        return
    compte_de_l_article = compte_pour_article(ligne, comptes_du_plan_par_defaut)
    _ajouter_au_compte(soldes_par_numero, compte_de_l_article, -ligne.total_ttc)


def _ecrire_la_recharge_offerte(soldes_par_numero, ligne, comptes_du_plan_par_defaut):
    """
    La part offerte d'un article de recharge (D8 bis) : une charge et une dette.
    Débit du compte des cadeaux à la clientèle (623400), crédit du compte de la
    recharge (419100). Vaut pour toute recharge offerte : recharge cadeau, recharge
    en euros offerte par le bouton OFFRIR, recharge offerte de l'API v2.
    Un article hors chiffre d'affaires offert qui N'EST PAS une recharge (mode de
    caisse « fidélité » FD, « virement reçu » VR, offerts par le bouton OFFRIR)
    n'écrit rien : aucune dette n'est née.
    / The offered part of a top-up item: gifts expense debit, top-up account credit.
    An offered off-revenue item that is not a top-up (FD, VR) writes nothing.
    """
    if ligne.part_offerte == 0:
        return
    produit = ligne.pricesold.productsold.product
    est_une_recharge = (
        produit.methode_caisse in METHODES_CAISSE_DES_RECHARGES
        or produit.categorie_article in TYPES_DE_PRODUIT_DES_RECHARGES
    )
    if not est_une_recharge:
        return

    compte_des_cadeaux = compte_des_cadeaux_a_la_clientele(comptes_du_plan_par_defaut)
    compte_de_la_recharge = compte_pour_article(ligne, comptes_du_plan_par_defaut)

    _ajouter_au_compte(soldes_par_numero, compte_des_cadeaux, ligne.part_offerte)
    _ajouter_au_compte(soldes_par_numero, compte_de_la_recharge, -ligne.part_offerte)


def _lignes_de_l_ecriture(soldes_par_numero):
    """
    Les lignes d'une écriture, une par compte : un solde positif au débit, un solde
    négatif au crédit (en positif), un solde nul sans ligne. Les débits d'abord, puis
    les crédits, chacun par numéro de compte.
    / One line per account: positive balance on debit, negative on credit (positive),
    zero without line. Debits first, then credits, by account number.
    """
    lignes_au_debit = []
    lignes_au_credit = []
    numeros_dans_l_ordre = sorted(soldes_par_numero.keys())
    for numero_du_compte in numeros_dans_l_ordre:
        compte = soldes_par_numero[numero_du_compte]["compte"]
        solde = soldes_par_numero[numero_du_compte]["solde"]
        if solde > 0:
            lignes_au_debit.append(
                {
                    "compte": numero_du_compte,
                    "libelle": compte.libelle_du_compte,
                    "debit": solde,
                    "credit": 0,
                }
            )
        if solde < 0:
            lignes_au_credit.append(
                {
                    "compte": numero_du_compte,
                    "libelle": compte.libelle_du_compte,
                    "debit": 0,
                    "credit": -solde,
                }
            )
    return lignes_au_debit + lignes_au_credit


def _verifier_l_equilibre(cloture_j, code_du_journal, lignes):
    """
    Σ débits = Σ crédits, sinon `EcritureDesequilibree`.
    / Debits = credits, otherwise EcritureDesequilibree.
    """
    total_des_debits = 0
    total_des_credits = 0
    for ligne in lignes:
        total_des_debits += ligne["debit"]
        total_des_credits += ligne["credit"]
    if total_des_debits != total_des_credits:
        ecart = total_des_debits - total_des_credits
        raise EcritureDesequilibree(
            f"L'écriture du journal « {code_du_journal} » de la clôture "
            f"n° {cloture_j.numero_sequentiel} est déséquilibrée : débits "
            f"{total_des_debits} centimes, crédits {total_des_credits} centimes, "
            f"écart de {ecart} centimes."
        )


def _libelle_du_journal(vente, code_du_journal):
    """
    Le libellé d'un journal : le nom du point de vente, sinon celui de la table des
    journaux d'origine.
    / A journal's label: the point of sale's name, else the origin table's.
    """
    if vente.point_de_vente is not None:
        return vente.point_de_vente.name
    return LIBELLE_DU_JOURNAL_SANS_POINT_DE_VENTE.get(code_du_journal, code_du_journal)


def ventiler_cloture(
    cloture_j,
    codes_journal_refuses=None,
    comptes_du_plan_par_defaut=None,
    compte_par_moyen_et_monnaie=None,
    compte_de_tva_par_taux=None,
):
    """
    Les écritures d'une clôture J, une par journal, triées par code journal.
    / The entries of a J closure, one per journal, sorted by journal code.

    LOCALISATION : comptabilite/ventilation.py

    FLUX :
    1. Les ventes réglées en euros de la plage de la J, avec leurs règlements et leurs
       articles (lus en trois requêtes).
    2. Pour chaque vente : son journal (`journal_pour`), refusé s'il est dans les codes
       refusés ; puis ses règlements et ses articles, ajoutés aux soldes par compte de
       l'écriture de ce journal. Les comptes trouvés sont gardés dans des dict.
    3. Pour chaque journal : les lignes (une par compte, côté du solde), puis la
       vérification de l'équilibre.

    LES DICT DES COMPTES DÉJÀ LUS : un appelant qui ventile plusieurs J (le FEC d'un
    mois) les crée une fois et les passe à chaque J ; ils se remplissent au fil de la
    lecture. Sans eux (None), ils sont créés ici, pour cette J seulement.
    / Already-read account dicts: a caller ventilating several J creates them once and
    passes them; None creates them here, for this J only.

    :param cloture_j: une `ClotureCaisse` de niveau J, avec sa plage de ventes (une J
        sans plage ne donne rien : `ecritures_de_l_export` ne l'envoie pas ici)
    :param codes_journal_refuses: dict {code: phrase du refus} de
        `codes_journal_refuses_a_l_export()`, ou None pour le lire ici
    :param comptes_du_plan_par_defaut: dict de `comptes_du_plan_par_defaut_du_lieu()`,
        ou None pour le lire ici
    :param compte_par_moyen_et_monnaie: dict {(moyen, monnaie): compte}, ou None
    :param compte_de_tva_par_taux: dict {taux: compte}, ou None
    :return: liste de dict {"journal": code, "libelle_du_journal": texte,
        "lignes": [{"compte", "libelle", "debit", "credit"}]} ; montants en centimes
        entiers positifs
    :raises CompteComptableManquant: si un compte ou un journal manque, ou si une
        vente est rangée sous un code journal refusé
    :raises EcritureDesequilibree: si une écriture n'est pas équilibrée
    :raises ValueError: si la clôture n'est pas une J
    """
    if cloture_j.niveau != ClotureCaisse.NIVEAU_JOURNALIER:
        raise ValueError(
            f"Seule une clôture journalière se ventile : la clôture "
            f"n° {cloture_j.numero_sequentiel} est de niveau {cloture_j.niveau}."
        )
    if codes_journal_refuses is None:
        codes_journal_refuses = codes_journal_refuses_a_l_export()

    # Les comptes déjà trouvés : la règle d'un compte n'est appliquée qu'une fois par
    # clé, quel que soit le nombre de ventes (et de J, si l'appelant les partage).
    # / Accounts already found: each rule runs once per key.
    if comptes_du_plan_par_defaut is None:
        comptes_du_plan_par_defaut = comptes_du_plan_par_defaut_du_lieu()
    if compte_par_moyen_et_monnaie is None:
        compte_par_moyen_et_monnaie = {}
    if compte_de_tva_par_taux is None:
        compte_de_tva_par_taux = {}

    # Le `select_related` lit d'un coup ce que les règles de compte lisent : le
    # produit, sa catégorie et son compte, la consigne remboursée et son compte.
    # / The select_related reads at once what the account rules read.
    articles_avec_leur_produit = LigneArticle.objects.select_related(
        "pricesold__productsold__product__categorie_pos__compte_comptable",
        "pricesold__productsold__product__consigne_remboursee__categorie_pos__compte_comptable",
    )
    ventes_de_la_j = (
        Vente.objects.filter(
            statut=Vente.Statut.REGLEE,
            unite="EUR",
            numero__gte=cloture_j.numero_premiere_vente,
            numero__lte=cloture_j.numero_derniere_vente,
        )
        .select_related("point_de_vente")
        .prefetch_related(
            "reglements",
            Prefetch("articles", queryset=articles_avec_leur_produit),
        )
        .order_by("numero")
    )

    soldes_par_journal = {}
    libelle_par_journal = {}
    for vente in ventes_de_la_j:
        code_du_journal = journal_pour(vente.point_de_vente, vente.origine)
        if code_du_journal in codes_journal_refuses:
            raise CompteComptableManquant(codes_journal_refuses[code_du_journal])
        if code_du_journal not in soldes_par_journal:
            soldes_par_journal[code_du_journal] = {}
            libelle_par_journal[code_du_journal] = _libelle_du_journal(
                vente, code_du_journal
            )
        soldes_par_numero = soldes_par_journal[code_du_journal]

        reglements_de_la_vente = vente.reglements.all()
        for reglement in reglements_de_la_vente:
            _ecrire_le_reglement(
                soldes_par_numero, reglement, compte_par_moyen_et_monnaie
            )

        articles_de_la_vente = vente.articles.all()
        for ligne in articles_de_la_vente:
            if ligne.hors_chiffre_affaires:
                _ecrire_l_article_hors_chiffre_d_affaires(
                    soldes_par_numero, ligne, comptes_du_plan_par_defaut
                )
                _ecrire_la_recharge_offerte(
                    soldes_par_numero, ligne, comptes_du_plan_par_defaut
                )
            else:
                _ecrire_l_article_du_chiffre_d_affaires(
                    soldes_par_numero, ligne, comptes_du_plan_par_defaut
                )
                _ecrire_la_tva_de_l_article(
                    soldes_par_numero, ligne, compte_de_tva_par_taux
                )

    ecritures = []
    codes_des_journaux = sorted(soldes_par_journal.keys())
    for code_du_journal in codes_des_journaux:
        lignes = _lignes_de_l_ecriture(soldes_par_journal[code_du_journal])
        if lignes == []:
            continue
        _verifier_l_equilibre(cloture_j, code_du_journal, lignes)
        ecritures.append(
            {
                "journal": code_du_journal,
                "libelle_du_journal": libelle_par_journal[code_du_journal],
                "lignes": lignes,
            }
        )
    return ecritures


# --------------------------------------------------------------------------- #
#  L'export d'une clôture (le FEC) / A closure's export (the FEC)             #
# --------------------------------------------------------------------------- #


def _fuseau_de_la_cloture(cloture):
    """
    Le fuseau figé dans l'en-tête du rapport de la clôture. Toute clôture le porte :
    la clé est lue directement, une donnée corrompue lève une exception au lieu de
    changer une date en silence.
    / The time zone frozen in the closure's report header, read directly.
    """
    return ZoneInfo(cloture.rapport_json["en_tete"]["fuseau_horaire"])


def date_de_debut_de_service(cloture_j):
    """
    La date de début de service d'une J : la date locale de sa première vente, dans
    le fuseau de la clôture.
    / A J's start-of-service date: the local date of its first sale.

    :param cloture_j: une `ClotureCaisse` de niveau J, avec sa plage de ventes
    :return: une date
    """
    premiere_vente = Vente.objects.get(numero=cloture_j.numero_premiere_vente)
    fuseau_de_la_j = _fuseau_de_la_cloture(cloture_j)
    return premiere_vente.datetime_encaissement.astimezone(fuseau_de_la_j).date()


def _bornes_locales_de_la_periode(cloture_de_la_periode):
    """
    Le premier jour d'une H / M / A et le jour qui la suit (exclu), en dates locales,
    dans le fuseau de la période.
    / The first day of an H / M / A and the day after it, local dates.

    :return: (premier jour, jour qui suit la période)
    """
    fuseau_de_la_periode = _fuseau_de_la_cloture(cloture_de_la_periode)
    premier_jour_de_la_periode = cloture_de_la_periode.datetime_debut.astimezone(
        fuseau_de_la_periode
    ).date()
    jour_qui_suit_la_periode = cloture_de_la_periode.datetime_fin.astimezone(
        fuseau_de_la_periode
    ).date()
    return premier_jour_de_la_periode, jour_qui_suit_la_periode


def _journees_datees_dans_la_periode(cloture_de_la_periode):
    """
    Les J dont la date de début de service est dans la période d'une H, M ou A, dans
    l'ordre des numéros, chacune avec sa date (calculée une seule fois).
    / The J whose start-of-service date is inside an H / M / A period, by number,
    each with its date.

    Les candidates ont une plage de ventes (une J sans vente n'a pas de date de début
    de service) et chevauchent la période en temps ; la date de chacune est ensuite
    comparée aux jours de la période. La date d'une J est prise dans le fuseau de la
    J, les jours de la période dans le fuseau de la période : si le lieu change de
    fuseau entre les deux (rare), une J de minuit peut tomber dans un mois voisin.
    / Candidates overlap the period in time; each date is compared to the period's
    days. A venue changing time zone between the J and the period (rare) may move a
    midnight J to a neighbouring month.

    :return: liste de (ClotureCaisse J, date de début de service)
    """
    premier_jour_de_la_periode, jour_qui_suit_la_periode = (
        _bornes_locales_de_la_periode(cloture_de_la_periode)
    )
    journees_candidates = ClotureCaisse.objects.filter(
        niveau=ClotureCaisse.NIVEAU_JOURNALIER,
        numero_premiere_vente__isnull=False,
        numero_derniere_vente__isnull=False,
        datetime_debut__lt=cloture_de_la_periode.datetime_fin,
        datetime_fin__gt=cloture_de_la_periode.datetime_debut,
    ).order_by("numero_sequentiel")

    journees_datees_dans_la_periode = []
    for journee in journees_candidates:
        date_de_la_journee = date_de_debut_de_service(journee)
        datee_dans_la_periode = (
            premier_jour_de_la_periode <= date_de_la_journee < jour_qui_suit_la_periode
        )
        if datee_dans_la_periode:
            journees_datees_dans_la_periode.append((journee, date_de_la_journee))
    return journees_datees_dans_la_periode


def _ecritures_datees_d_une_journee(cloture_j, date_de_la_journee, comptes_de_l_export):
    """
    Les écritures d'une J, chacune avec sa date, son numéro, sa pièce et son libellé.
    / A J's entries, each with its date, number, piece reference and label.

    :param comptes_de_l_export: dict {"codes_journal_refuses",
        "comptes_du_plan_par_defaut", "compte_par_moyen_et_monnaie",
        "compte_de_tva_par_taux"}, créé une fois pour tout l'export
    :raises CompteComptableManquant: relevé avec le numéro de la J en cause
    """
    numero_de_la_journee = str(cloture_j.numero_sequentiel)
    try:
        ecritures = ventiler_cloture(
            cloture_j,
            codes_journal_refuses=comptes_de_l_export["codes_journal_refuses"],
            comptes_du_plan_par_defaut=comptes_de_l_export[
                "comptes_du_plan_par_defaut"
            ],
            compte_par_moyen_et_monnaie=comptes_de_l_export[
                "compte_par_moyen_et_monnaie"
            ],
            compte_de_tva_par_taux=comptes_de_l_export["compte_de_tva_par_taux"],
        )
    except CompteComptableManquant as compte_manquant:
        raise CompteComptableManquant(
            f"Clôture J n° {numero_de_la_journee} : {compte_manquant}"
        ) from compte_manquant

    for ecriture in ecritures:
        ecriture["date"] = date_de_la_journee
        ecriture["numero_d_ecriture"] = f"{numero_de_la_journee}-{ecriture['journal']}"
        ecriture["piece"] = numero_de_la_journee
        ecriture["libelle"] = (
            f"Clôture J n° {numero_de_la_journee} — {ecriture['libelle_du_journal']}"
        )
    return ecritures


def ecritures_de_l_export(cloture):
    """
    Ce que le FEC écrit pour une clôture : ses écritures si
    c'est une J ; celles des J datées dans sa période si c'est une H, M ou A. Les
    codes journal refusés et les comptes sont lus une seule fois pour tout l'export,
    même pour une année.
    / What an accounting export writes for a closure: its entries for a J; its dated
    J's entries for an H / M / A. Refused codes and accounts are read once.

    LOCALISATION : comptabilite/ventilation.py

    Une J sans plage de ventes (sans vente) ne donne aucune écriture ; le nom de son
    fichier prend la date locale de sa fin.
    / A J without sales range gives no entry; its file name takes its local end date.

    :param cloture: une `ClotureCaisse`
    :return: dict {"ecritures": liste d'écritures de `ventiler_cloture`, chacune avec
        en plus "date" (date), "numero_d_ecriture", "piece", "libelle" (textes) ;
        "date_du_nom_du_fichier": date locale}
    :raises CompteComptableManquant: si un compte ou un journal manque (le message
        nomme la J en cause)
    :raises EcritureDesequilibree: si une écriture n'est pas équilibrée
    """
    if cloture.niveau == ClotureCaisse.NIVEAU_JOURNALIER:
        la_j_a_une_plage_de_ventes = (
            cloture.numero_premiere_vente is not None
            and cloture.numero_derniere_vente is not None
        )
        if la_j_a_une_plage_de_ventes:
            date_de_la_j = date_de_debut_de_service(cloture)
            journees_de_l_export = [(cloture, date_de_la_j)]
            date_du_nom_du_fichier = date_de_la_j
        else:
            journees_de_l_export = []
            fuseau_de_la_j = _fuseau_de_la_cloture(cloture)
            date_du_nom_du_fichier = cloture.datetime_fin.astimezone(
                fuseau_de_la_j
            ).date()
    else:
        journees_de_l_export = _journees_datees_dans_la_periode(cloture)
        _premier_jour, jour_qui_suit_la_periode = _bornes_locales_de_la_periode(cloture)
        date_du_nom_du_fichier = jour_qui_suit_la_periode - timedelta(days=1)

    return {
        "ecritures": ecritures_des_journees(journees_de_l_export),
        "date_du_nom_du_fichier": date_du_nom_du_fichier,
    }


def ecritures_des_journees(journees_de_l_export):
    """
    Les écritures d'une liste de J datées, dans l'ordre de la liste. C'est le cœur
    commun du FEC (`ecritures_de_l_export`) et de la balance du plan comptable
    (`comptabilite/balance.py`) : les deux lisent donc les MÊMES écritures.
    Les codes journal refusés et les comptes sont lus une seule fois pour toute la
    liste, même pour une année.
    / The entries of a list of dated J. The shared core of the FEC and of the trial
    balance: both read the SAME entries. Refused codes and accounts are read once.

    LOCALISATION : comptabilite/ventilation.py

    :param journees_de_l_export: liste de (ClotureCaisse J, date de début de service)
    :return: liste d'écritures de `ventiler_cloture`, chacune avec en plus "date",
        "numero_d_ecriture", "piece", "libelle"
    :raises CompteComptableManquant: si un compte ou un journal manque (le message
        nomme la J en cause)
    :raises EcritureDesequilibree: si une écriture n'est pas équilibrée
    """
    # Ce qui est lu une seule fois pour tout l'export, puis partagé entre les J.
    # / What is read once for the whole export, then shared between the J.
    comptes_de_l_export = {
        "codes_journal_refuses": codes_journal_refuses_a_l_export(),
        "comptes_du_plan_par_defaut": comptes_du_plan_par_defaut_du_lieu(),
        "compte_par_moyen_et_monnaie": {},
        "compte_de_tva_par_taux": {},
    }

    ecritures_de_toutes_les_journees = []
    for journee, date_de_la_journee in journees_de_l_export:
        ecritures_de_la_journee = _ecritures_datees_d_une_journee(
            journee, date_de_la_journee, comptes_de_l_export
        )
        ecritures_de_toutes_les_journees.extend(ecritures_de_la_journee)
    return ecritures_de_toutes_les_journees


def journees_datees_entre(premier_jour, dernier_jour):
    """
    Les J dont la date de début de service est entre deux dates (incluses), dans
    l'ordre des numéros, chacune avec sa date. Même règle de date que le FEC d'une
    semaine, d'un mois ou d'une année : une J est datée du jour local de sa première
    vente, dans le fuseau figé dans son rapport (`date_de_debut_de_service`).
    / The J whose start-of-service date is between two dates (included), by number,
    each with its date. Same date rule as the FEC of a period.

    LOCALISATION : comptabilite/ventilation.py
    APPELÉE PAR : comptabilite/balance.py (`balance_de_la_periode`).

    Les candidates sont prises large, en temps universel : un jour de marge avant,
    deux après (un fuseau est à moins de 14 h du temps universel). La date de
    chacune est ensuite comparée aux deux dates : seules les J datées dans la
    période restent.
    / Candidates are taken wide (UTC, one day before, two after), then each date is
    compared to the two dates.

    :param premier_jour: date (incluse)
    :param dernier_jour: date (incluse)
    :return: liste de (ClotureCaisse J, date de début de service)
    """
    debut_large = datetime.combine(premier_jour, time.min, tzinfo=fuseau_utc.utc) - (
        timedelta(days=1)
    )
    fin_large = datetime.combine(dernier_jour, time.min, tzinfo=fuseau_utc.utc) + (
        timedelta(days=2)
    )
    journees_candidates = ClotureCaisse.objects.filter(
        niveau=ClotureCaisse.NIVEAU_JOURNALIER,
        numero_premiere_vente__isnull=False,
        numero_derniere_vente__isnull=False,
        datetime_debut__lt=fin_large,
        datetime_fin__gt=debut_large,
    ).order_by("numero_sequentiel")

    journees_datees_dans_la_periode = []
    for journee in journees_candidates:
        date_de_la_journee = date_de_debut_de_service(journee)
        if premier_jour <= date_de_la_journee <= dernier_jour:
            journees_datees_dans_la_periode.append((journee, date_de_la_journee))
    return journees_datees_dans_la_periode
