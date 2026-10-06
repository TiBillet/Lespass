"""
Le rapport des ventes d'une période : un seul moteur pour toutes les origines.
/ The sales report of a period: one engine for every origin.

LOCALISATION : comptabilite/rapport.py

Le rapport ne lit QUE des ventes réglées (`Vente.statut = REGLEE`) dont l'heure
d'encaissement est dans la période, leurs articles (`LigneArticle`) et leurs
règlements (`Reglement`). Il ne fait QUE des sommes de champs entiers, en centimes :
`Sum("total_ttc")`, `Sum("montant")`, `Sum("part_offerte")`… L'argent n'est jamais
recalculé (tronc §2) : pas de prix × quantité, pas d'arrondi.
/ The report only reads settled sales of the period, their items and payments, and only
sums integer fields. Money is never recomputed.

LA PÉRIODE : une vente est dans le rapport si `debut <= datetime_encaissement < fin`.
La borne de fin est exclue : deux périodes qui se suivent ne comptent jamais deux fois
la même vente.
/ The period: debut <= settlement time < fin. Two consecutive periods never count a
sale twice.

LES DÉFINITIONS (fiche F §2) :
- Toute somme en euros ne lit que les ventes en euros (`unite = EUR`). Une vente en
  points ou en temps (`unite` = uuid de sa monnaie) n'est comptée qu'en section 8 et
  dans les points de la section 3, par monnaie.
- Articles du chiffre d'affaires : ventes en euros, articles
  `hors_chiffre_affaires = False`, natures VENTE et AVOIR. La part payée en jetons
  cadeau de chaque article (`part_en_jetons`) en fait partie : vente ordinaire, hors
  TVA (D8 bis), comptée au taux « 0.00 » du CA par taux.
- Argent : règlements dont le moyen n'est ni offert (FREE), ni points (NM), ni
  cashless. Cashless : monnaie locale (LE), fédérée (SF), jetons cadeau (LG).
- Recharges, écarts d'encaissement, jetons cadeau repris : reconnus par l'ARTICLE (hors
  chiffre d'affaires, et produit), jamais par `Vente.nature` (un panier bière + recharge
  est une vente VENTE). Mêmes règles que le plan comptable (`compte_pour_article`).
/ Definitions: euro sums read euro sales only; revenue items, money, cashless; top-ups
and gaps are recognised by the item, never by the sale nature.

LE RÉSULTAT : une méthode par section ; `toutes_les_sections()` les réunit dans un
dictionnaire sérialisable en JSON (entiers et textes seulement), stocké tel quel dans
`ClotureCaisse.rapport_json`. Les montants sont des sommes brutes, signées : un avoir,
des espèces rendues, un remboursement sont négatifs ; l'affichage les écrit en positif.
Les clés sont des codes ou des uuid, jamais un texte traduit : chaque entrée porte son
nom lisible dans un champ (`nom`, `libelle`).
/ One method per section; a JSON-serializable dict; signed raw sums; keys are codes or
uuids, never translated text.

Sections du Z (fiche F §2) : 1 en-tête, 2 chiffre d'affaires, 3 règlements, 4 caisse
espèces, 5 réconciliation, 6 offerts, 7 annexe, 8 points, 9 marge brute, 10 détail,
11 intégrité. Le rapport X (`rapport_x()`, temps réel, jamais stocké) reprend les
sections du Z SANS la 11 (l'intégrité, un contrôle trop lourd pour l'écran temps réel),
et y ajoute l'habitus des cartes et les opérateurs.
/ Z sections 1 to 11; the X report (never stored) takes the Z sections WITHOUT the 11th
(integrity), and adds card habits and operators.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-F-rapport-unique.md (§1, §2)
Tests : tests/pytest/test_rapport_unique.py
"""

from decimal import Decimal

from django.db import connection
from django.db.models import (
    BooleanField,
    Case,
    Count,
    DecimalField,
    Exists,
    F,
    Max,
    Min,
    OuterRef,
    Q,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Coalesce
from django.utils.translation import gettext

from AuthBillet.models import TibilletUser
from BaseBillet.models import (
    Configuration,
    LigneArticle,
    Membership,
    PaymentMethod,
    Product,
    SaleOrigin,
)
from BaseBillet.models_vente import Reglement, Vente
from BaseBillet.services_vente import (
    NOM_ECART_RECU_EN_MOINS,
    NOM_ECART_RECU_EN_PLUS,
    NOM_JETONS_CADEAU_REPRIS_AU_VIDAGE,
    arrondir_au_centime_demi_haut,
)
from fedow_core.models import Asset, Token
from laboutik.integrity import verifier_chaine_ventes
from laboutik.models import LaboutikConfiguration, PointDeVente, SortieCaisse
from laboutik.plan_comptable import (
    METHODES_CAISSE_DES_RECHARGES,
    TYPES_DE_PRODUIT_DES_RECHARGES,
    CompteComptableManquant,
    journal_pour,
    nom_de_la_monnaie,
)
from QrcodeCashless.models import CarteCashless

# Les natures dont les articles font le chiffre d'affaires.
# / The natures whose items make the revenue.
NATURES_DU_CHIFFRE_D_AFFAIRES = [Vente.Nature.VENTE, Vente.Nature.AVOIR]

# Les natures dont les règlements sont dans la section 3. Le vidage de carte n'y est
# pas : il est en section 7 (cartes vidées) et dans l'argent reçu de la section 5.
# / The natures whose payments are in section 3. Card emptying is not.
NATURES_DES_REGLEMENTS = [
    Vente.Nature.VENTE,
    Vente.Nature.AVOIR,
    Vente.Nature.CORRECTION,
]

# Les moyens cashless : monnaie locale, monnaie fédérée, jetons cadeau.
# / Cashless methods: local currency, federated currency, gift tokens.
MOYENS_CASHLESS = [
    PaymentMethod.LOCAL_EURO,
    PaymentMethod.STRIPE_FED,
    PaymentMethod.LOCAL_GIFT,
]

# Les moyens qui ne sont pas de l'argent : l'offert et les points (ou le temps).
# / Methods that are not money: offered and points (or time).
MOYENS_HORS_ARGENT = [PaymentMethod.FREE, PaymentMethod.NON_MONETAIRE]

# Tout ce qui n'est pas de l'argent au sens strict.
# / Everything that is not money in the strict sense.
MOYENS_QUI_NE_SONT_PAS_DE_L_ARGENT = MOYENS_CASHLESS + MOYENS_HORS_ARGENT

# Les moyens Stripe d'un remboursement en ligne (carte, SEPA, abonnement).
# / Stripe methods of an online refund.
MOYENS_STRIPE = [
    PaymentMethod.STRIPE_NOFED,
    PaymentMethod.STRIPE_SEPA_NOFED,
    PaymentMethod.STRIPE_RECURENT,
]

# Les noms des deux produits système d'écart d'encaissement (D26).
# / The names of the two collection gap system products.
NOMS_DES_ECARTS_D_ENCAISSEMENT = [NOM_ECART_RECU_EN_PLUS, NOM_ECART_RECU_EN_MOINS]

# Les clés de repli des dictionnaires : des codes, comme « CC » ou « CA ».
# / Fallback keys of the dictionaries: codes, like "CC" or "CA".
CLE_PLUSIEURS_MOYENS = "plusieurs_moyens"
CLE_SANS_MONNAIE = "sans_monnaie"
CLE_DU_JOURNAL_IMPOSSIBLE = "?"
PREFIXE_DE_LA_CLE_D_UN_TYPE_DE_PRODUIT = "type_"
CLE_SANS_OPERATEUR = "sans_operateur"
CLE_SANS_POINT_DE_VENTE = "sans_point_de_vente"

# Le résultat de la section « intégrité » : un code, jamais un texte traduit.
# / The integrity section result: a code, never a translated text.
STATUT_INTEGRITE_OK = "OK"
STATUT_INTEGRITE_ANOMALIES = "ANOMALIES"

# Les trois totaux d'une ligne du chiffre d'affaires.
# / The three totals of a revenue row.
NOMS_DES_TROIS_TOTAUX = [
    "total_ttc_en_centimes",
    "total_ht_en_centimes",
    "total_tva_en_centimes",
]


def _sommes_ttc_ht_tva():
    """
    Les trois sommes d'un groupe d'articles : TTC (net vendu), HT, TVA. 0 si le groupe
    est vide.
    / The three sums of a group of items. 0 when the group is empty.
    """
    return {
        "total_ttc_en_centimes": Coalesce(Sum("total_ttc"), 0),
        "total_ht_en_centimes": Coalesce(Sum("total_ht"), 0),
        "total_tva_en_centimes": Coalesce(Sum("total_tva"), 0),
    }


def _ajouter_les_trois_totaux(ligne_du_rapport, ligne_de_sommes):
    """
    Ajoute les trois totaux d'une ligne rendue par `values().annotate(...)` à une ligne
    du rapport. Deux groupes de la base peuvent aller dans la même ligne du rapport
    (même journal, même catégorie) : on additionne, rien n'est écrasé.
    / Adds the three totals of a grouped row to a report row: added, never overwritten.
    """
    for nom_du_total in NOMS_DES_TROIS_TOTAUX:
        ligne_du_rapport[nom_du_total] += ligne_de_sommes[nom_du_total]


def _cle_et_nom_de_la_categorie(
    uuid_de_la_categorie_de_caisse, nom_de_la_categorie_de_caisse, code_du_type
):
    """
    La clé et le nom lisible de la catégorie d'un produit.
    - Avec une catégorie de caisse (`categorie_pos`) : clé = son uuid, nom = son nom.
    - Sans : le type du produit (`categorie_article`), clé = « type_ » + code du type,
      nom = libellé du type. Le type « aucun » (`N`) a pour nom « Sans catégorie » :
      le libellé de ce choix est un texte de menu (« Sélectionner une catégorie »),
      jamais un nom de catégorie.
    / The key and readable name of a product's category: POS category, otherwise the
    product type ("Sans catégorie" for the "none" type).
    """
    if uuid_de_la_categorie_de_caisse is not None:
        return str(uuid_de_la_categorie_de_caisse), nom_de_la_categorie_de_caisse

    cle_de_la_categorie = f"{PREFIXE_DE_LA_CLE_D_UN_TYPE_DE_PRODUIT}{code_du_type}"
    if code_du_type == Product.NONE:
        return cle_de_la_categorie, gettext("Sans catégorie")

    libelles_des_types_de_produit = dict(Product.CATEGORIE_ARTICLE_CHOICES)
    nom_du_type = str(libelles_des_types_de_produit.get(code_du_type, code_du_type))
    return cle_de_la_categorie, nom_du_type


def _moyenne_en_centimes(total_en_centimes, nombre):
    """
    La moyenne d'un total sur un nombre, en centimes entiers arrondis demi-haut.
    0 si le nombre vaut 0. Calcul exact en `Decimal` : jamais de nombre à virgule.
    / The average in whole cents, rounded half-up; 0 when the count is 0.
    """
    if nombre == 0:
        return 0
    return arrondir_au_centime_demi_haut(Decimal(total_en_centimes) / Decimal(nombre))


def _mediane_en_centimes(valeurs_en_centimes):
    """
    La médiane d'une liste de montants, en centimes entiers. Nombre pair de valeurs :
    la moyenne des deux du milieu, arrondie demi-haut. 0 si la liste est vide.
    / The median in whole cents (even count: mean of the two middle values, rounded
    half-up); 0 for an empty list.
    """
    nombre_de_valeurs = len(valeurs_en_centimes)
    if nombre_de_valeurs == 0:
        return 0

    valeurs_triees = sorted(valeurs_en_centimes)
    position_du_milieu = nombre_de_valeurs // 2
    if nombre_de_valeurs % 2 == 1:
        return valeurs_triees[position_du_milieu]

    somme_des_deux_du_milieu = (
        valeurs_triees[position_du_milieu - 1] + valeurs_triees[position_du_milieu]
    )
    return _moyenne_en_centimes(somme_des_deux_du_milieu, 2)


def nom_du_moyen_de_paiement(code_du_moyen):
    """
    Le nom lisible d'un moyen de paiement. C'est la seule source des noms des
    moyens du rapport, de l'écran et des tickets : les trois moyens du comptoir ont
    un nom court, avec accents (« Espèces », « Carte bancaire », « Chèque ») ; les
    autres gardent le libellé de `PaymentMethod`.
    / Readable name of a payment method: the single source for the report, the
    screens and the tickets. Short names for the three counter methods.
    """
    noms_des_moyens_du_comptoir = {
        PaymentMethod.CASH: gettext("Espèces"),
        PaymentMethod.CC: gettext("Carte bancaire"),
        PaymentMethod.CHEQUE: gettext("Chèque"),
    }
    if code_du_moyen in noms_des_moyens_du_comptoir:
        return noms_des_moyens_du_comptoir[code_du_moyen]
    libelles_des_moyens = dict(PaymentMethod.choices)
    return str(libelles_des_moyens.get(code_du_moyen, code_du_moyen))


def _cle_et_nom_de_la_monnaie(uuid_de_la_monnaie):
    """
    La clé (uuid en texte, ou « sans_monnaie ») et le nom lisible d'une monnaie.
    / The key (uuid as text, or "sans_monnaie") and the readable name of a currency.
    """
    if uuid_de_la_monnaie is None:
        return CLE_SANS_MONNAIE, gettext("Sans monnaie")
    return str(uuid_de_la_monnaie), nom_de_la_monnaie(uuid_de_la_monnaie)


def _filtre_des_articles_de_recharge():
    """
    Le `Q` des articles dont le produit est une recharge : mêmes règles que le plan
    comptable (`RE`, `RC` à la caisse, `R`, `E` en ligne).
    / The Q of items whose product is a top-up (same rules as the chart of accounts).
    """
    return Q(
        pricesold__productsold__product__methode_caisse__in=METHODES_CAISSE_DES_RECHARGES
    ) | Q(
        pricesold__productsold__product__categorie_article__in=TYPES_DE_PRODUIT_DES_RECHARGES
    )


def unite_d_une_vente_au_poids(unite_du_stock, categorie_du_produit=None):
    """
    Le symbole de l'unité d'une vente au poids ou au volume (D15, Q-H4) :
    - « L » pour un fût (`Product.FUT`) : la tireuse écrit toujours des litres, que
      le fût ait un stock ou non ;
    - « L » si le stock du produit est en centilitres ;
    - « kg » sinon (stock en grammes, ou sans stock). Même règle que la caisse
      (`_diviseur_de_la_quantite_saisie`, laboutik/views.py).
    La quantité d'une telle ligne est dans cette unité.
    / The unit symbol of a weight / volume sale: "L" for a keg (the tap always writes
    litres) or a centilitre stock, "kg" otherwise (same rule as the register).

    LOCALISATION : comptabilite/rapport.py

    LU PAR : ce module (détail des ventes, offerts), laboutik/affichage_des_ventes.py
    (détail d'une vente, ticket), Administration/admin_tenant.py (fiche « Vente »,
    onglet des lignes).

    :param unite_du_stock: `Stock.unite` du produit ("GR", "CL", "UN"), ou None
    :param categorie_du_produit: `Product.categorie_article` du produit, ou None
    :return: "kg" ou "L"
    """
    if categorie_du_produit == Product.FUT:
        return "L"
    if unite_du_stock == "CL":
        return "L"
    return "kg"


def quantite_en_nombre_d_articles(prefixe_du_chemin=""):
    """
    L'expression SQL du nombre d'articles d'une ligne :
    - un article « Écart d'encaissement » ne compte pas : ce n'est pas un article vendu ;
    - une vente au poids ou au volume compte pour UN article : un poids dans
      `weight_quantity`, ou une ligne de fût (`Product.FUT`, un tirage de moins de
      5 ml a un poids de 0 cl). 0,350 kg de comté est une pesée, pas 0,35 article ;
    - sinon : sa quantité.
    C'est la seule règle « une pesée = un article » du projet.
    / SQL expression of a line's number of items: a collection gap counts 0, a weighing
    or a keg line counts ONE, otherwise its quantity. The project's only rule.

    LOCALISATION : comptabilite/rapport.py

    LU PAR : ce module (marge, total des offerts), laboutik/views.py (nombre
    d'articles de la liste des ventes, depuis les ventes : préfixe « articles__ »).

    :param prefixe_du_chemin: le chemin de la vente vers ses lignes (« articles__ »),
        vide pour une requête sur `LigneArticle`
    :return: une expression `Case`
    """
    chemin_du_produit = f"{prefixe_du_chemin}pricesold__productsold__product__"
    return Case(
        When(
            **{f"{chemin_du_produit}name__in": NOMS_DES_ECARTS_D_ENCAISSEMENT},
            then=Value(Decimal("0")),
        ),
        When(
            **{f"{prefixe_du_chemin}weight_quantity__gt": 0},
            then=Value(Decimal("1")),
        ),
        When(
            **{f"{chemin_du_produit}categorie_article": Product.FUT},
            then=Value(Decimal("1")),
        ),
        default=F(f"{prefixe_du_chemin}qty"),
        output_field=DecimalField(max_digits=12, decimal_places=6),
    )


def _ligne_au_poids_ou_au_volume():
    """
    L'expression SQL « cette ligne est une vente au poids ou au volume » : un poids
    dans `weight_quantity`, ou une ligne de fût (`Product.FUT` : un tirage de moins
    de 5 ml a un poids de 0 cl, et reste en litres). Elle sépare, au détail du
    rapport, les lignes au poids des lignes à la pièce d'un même produit : deux unités
    ne s'additionnent jamais.
    / SQL expression "this line is a weight / volume sale" (a weight, or a keg line).
    """
    return Case(
        When(weight_quantity__gt=0, then=Value(True)),
        When(
            pricesold__productsold__product__categorie_article=Product.FUT,
            then=Value(True),
        ),
        default=Value(False),
        output_field=BooleanField(),
    )


def _cle_et_unite_d_une_ligne_par_produit(sommes_du_produit):
    """
    La clé et l'unité d'une ligne « par produit » du rapport : un produit à la pièce
    garde son uuid comme clé et une unité vide ; ses lignes au poids ou au volume
    forment une autre ligne, de clé « uuid--kg » (ou « --L »), dans l'unité du stock
    (`unite_d_une_vente_au_poids`).
    / The key and unit of a "by product" report row: the product uuid for pieces,
    "uuid--kg" (or "--L") for its weight / volume lines.

    :param sommes_du_produit: une ligne de `values()` qui porte le produit, son type
        (`categorie_article`), `au_poids_ou_au_volume` et l'unité du stock
    :return: tuple (clé, unité)
    """
    uuid_du_produit = str(sommes_du_produit["pricesold__productsold__product"])
    if not sommes_du_produit["au_poids_ou_au_volume"]:
        return (uuid_du_produit, "")
    unite_de_la_quantite = unite_d_une_vente_au_poids(
        sommes_du_produit["pricesold__productsold__product__stock_inventaire__unite"],
        sommes_du_produit["pricesold__productsold__product__categorie_article"],
    )
    return (f"{uuid_du_produit}--{unite_de_la_quantite}", unite_de_la_quantite)


def _ajouter_au_moyen(par_moyen, code_du_moyen, libelle_du_moyen, montant_en_centimes):
    """
    Ajoute un montant (signé) à la ligne d'un moyen dans un dictionnaire « par
    moyen » du rapport, en créant la ligne si elle manque.
    / Adds signed cents to a method line of a "by method" dict, creating it.
    """
    if code_du_moyen not in par_moyen:
        par_moyen[code_du_moyen] = {
            "libelle": libelle_du_moyen,
            "total_en_centimes": 0,
        }
    par_moyen[code_du_moyen]["total_en_centimes"] += montant_en_centimes


class RapportDesVentes:
    """
    Le rapport des ventes réglées d'une période, section par section.
    / The report of the settled sales of a period, section by section.

    LOCALISATION : comptabilite/rapport.py

    Utilisation / Usage :
        rapport = RapportDesVentes(debut, fin)
        rapport.section_chiffre_affaires()   # une section
        rapport.toutes_les_sections()        # le dictionnaire complet (JSON)

    Le rapport lit le lieu courant (schéma de la connexion) : l'appelant se place dans
    le lieu (`tenant_context`) avant de l'appeler.
    / Reads the current venue: the caller sets the tenant first.
    """

    def __init__(self, debut, fin):
        """
        :param debut: début de la période (datetime avec fuseau), inclus
        :param fin: fin de la période (datetime avec fuseau), EXCLUE
        """
        self.debut = debut
        self.fin = fin

    # ------------------------------------------------------------------
    # Ce que le rapport lit
    # / What the report reads
    # ------------------------------------------------------------------

    def _ventes_reglees(self):
        """
        Les ventes réglées de la période, toutes natures, toutes origines, toutes
        unités (euros et points).
        / The settled sales of the period, every nature, origin and unit.
        """
        return Vente.objects.filter(
            statut=Vente.Statut.REGLEE,
            datetime_encaissement__gte=self.debut,
            datetime_encaissement__lt=self.fin,
        )

    def _ventes_en_euros(self):
        """
        Les ventes réglées en euros : la base de toute somme en euros.
        / Settled sales in euros: the base of every euro sum.
        """
        return self._ventes_reglees().filter(unite="EUR")

    def _articles_des_ventes_en_euros(self):
        """
        Les articles des ventes réglées en euros. Un article est lu PAR SA VENTE,
        jamais par sa propre date : un article d'une vente en attente n'existe pas pour
        le rapport.
        / Items of the settled euro sales, read through their sale.
        """
        return LigneArticle.objects.filter(vente__in=self._ventes_en_euros())

    def _reglements_des_ventes_en_euros(self):
        """Les règlements des ventes réglées en euros. / Payments of settled euro sales."""
        return Reglement.objects.filter(vente__in=self._ventes_en_euros())

    def _articles_du_chiffre_d_affaires(self):
        """
        Les articles du chiffre d'affaires : ventes en euros, articles pas hors chiffre
        d'affaires, natures VENTE et AVOIR.
        / Revenue items: euro sales, not off revenue, natures VENTE and AVOIR.
        """
        return self._articles_des_ventes_en_euros().filter(
            vente__nature__in=NATURES_DU_CHIFFRE_D_AFFAIRES,
            hors_chiffre_affaires=False,
        )

    def _articles_de_recharge_encaissees(self):
        """
        Les recharges encaissées : articles hors chiffre d'affaires dont le produit est
        une recharge (mêmes règles que le plan comptable : `RE`, `RC` à la caisse,
        `R`, `E` en ligne), dans les ventes en euros de nature VENTE. C'est un montant
        brut : une recharge remboursée reste comptée ici, et son remboursement apparaît
        dans les avoirs (`_articles_de_recharge_remboursees`).
        / Collected top-ups (gross): off-revenue top-up items of VENTE euro sales.
        """
        return self._articles_des_ventes_en_euros().filter(
            _filtre_des_articles_de_recharge(),
            hors_chiffre_affaires=True,
            vente__nature=Vente.Nature.VENTE,
        )

    def _articles_de_recharge_remboursees(self):
        """
        Les recharges remboursées : les articles de recharge des avoirs en euros. Un
        article d'avoir reprend le produit et le « hors chiffre d'affaires » de
        l'article qu'il annule ; son net est négatif.
        / Refunded top-ups: the top-up items of euro credit notes (negative net).
        """
        return self._articles_des_ventes_en_euros().filter(
            _filtre_des_articles_de_recharge(),
            hors_chiffre_affaires=True,
            vente__nature=Vente.Nature.AVOIR,
        )

    def _parts_deplacees_par_les_corrections(
        self, filtre_des_articles_deplaces, moyens_ignores
    ):
        """
        Les parts d'articles qu'une correction de moyen de paiement déplace avec
        l'argent, pour chaque vente CORRECTION de la période.
        / The item parts a payment method correction moves along with the money.

        POURQUOI : une vente CORRECTION n'a aucun article. Ses deux règlements
        (deux moyens, deux montants opposés) déplacent TOUT le net du moyen corrigé
        de la vente liée, recharge comprise. La part des articles qui n'est pas du
        chiffre d'affaires (une recharge) doit donc suivre l'argent :
        retirée du chiffre d'affaires du moyen d'arrivée, rendue au moyen de départ ;
        et, dans les recharges par moyen, passée du moyen de départ au moyen
        d'arrivée.
        / A CORRECTION sale has no item; its two payments move all the money of the
        corrected lines, top-up included: that part must follow the money.

        LE SENS DU DÉPLACEMENT ne dépend pas du signe des règlements : une correction
        porte une paire de moyens {m1, m2}. Si le moyen où se trouve la part est dans
        la paire, la part passe à l'autre moyen de la paire. Une correction d'avoir
        (montants de signes inverses) se lit donc comme une correction de vente.
        / The direction does not depend on the payments' sign: a correction carries
        a pair {m1, m2}; a part under one of them moves to the other.

        L'ARGENT CORRIGÉ : la correction déplace le net du moyen corrigé (règlements
        de la vente liée et de ses corrections) ; elle ne modifie aucune ligne. Une
        vente qui contient un article hors chiffre d'affaires a un seul moyen
        d'argent (la caisse refuse le cashless pour une recharge payante) : sa part
        est sous ce moyen. Une vente liée à plusieurs
        moyens (ou sans moyen) range sa part sous « plusieurs moyens » : rien n'est
        déplacé.
        / A sale with an off-revenue item has one money method; otherwise nothing
        moves.

        TOUTES LES CORRECTIONS DE LA VENTE LIÉE sont suivies, dans l'ordre de leurs
        numéros, même hors de la période : une correction d'avant la période a déjà
        changé le moyen de la part. Seules les corrections de la période émettent un
        déplacement. La vente liée est elle aussi lue hors de la période.
        / Every correction of the linked sale is followed by number, even outside
        the period; only the period's corrections emit a move.

        REQUÊTES : cinq, quel que soit le nombre de ventes.
        / Five queries, whatever the number of sales.

        :param filtre_des_articles_deplaces: `Q` des articles dont la part suit
            l'argent (hors chiffre d'affaires, ou recharges seulement)
        :param moyens_ignores: les moyens qui ne comptent pas pour trouver le moyen
            de la vente liée
        :return: liste de (moyen_de_depart, moyen_d_arrivee, part_en_centimes)
        """
        # 1. Les corrections de la période, et leurs ventes liées.
        # / 1. The period's corrections, and their linked sales.
        corrections_de_la_periode = (
            self._ventes_en_euros()
            .filter(nature=Vente.Nature.CORRECTION, vente_liee__isnull=False)
            .values("pk", "vente_liee_id")
        )
        identifiants_des_corrections_de_la_periode = set()
        identifiants_des_ventes_liees = set()
        for correction_de_la_periode in corrections_de_la_periode:
            identifiants_des_corrections_de_la_periode.add(
                correction_de_la_periode["pk"]
            )
            identifiants_des_ventes_liees.add(
                correction_de_la_periode["vente_liee_id"]
            )

        # 2. Toutes les corrections réglées de ces ventes liées, sans borne de
        #    période, dans l'ordre des numéros.
        # / 2. Every settled correction of these linked sales, with no period
        #    bound, by number.
        toutes_les_corrections_des_ventes_liees = list(
            Vente.objects.filter(
                statut=Vente.Statut.REGLEE,
                unite="EUR",
                nature=Vente.Nature.CORRECTION,
                vente_liee_id__in=identifiants_des_ventes_liees,
            )
            .order_by("numero")
            .values("pk", "vente_liee_id")
        )
        identifiants_de_toutes_les_corrections = []
        for correction_de_la_vente_liee in toutes_les_corrections_des_ventes_liees:
            identifiants_de_toutes_les_corrections.append(
                correction_de_la_vente_liee["pk"]
            )

        reglements_des_corrections = Reglement.objects.filter(
            vente_id__in=identifiants_de_toutes_les_corrections
        ).values("vente_id", "moyen")
        parts_des_ventes_liees = (
            LigneArticle.objects.filter(vente_id__in=identifiants_des_ventes_liees)
            .filter(filtre_des_articles_deplaces)
            .values("vente_id")
            .annotate(total_en_centimes=Sum("total_ttc"))
            .order_by("vente_id")
        )
        moyens_des_ventes_liees = (
            Reglement.objects.filter(vente_id__in=identifiants_des_ventes_liees)
            .exclude(moyen__in=moyens_ignores)
            .values("vente_id", "moyen")
            .distinct()
        )

        # La paire de moyens de chaque correction, sans regarder le signe.
        # / Each correction's pair of methods, regardless of the sign.
        paire_de_moyens_par_correction = {}
        for reglement in reglements_des_corrections:
            identifiant_de_la_correction = reglement["vente_id"]
            if identifiant_de_la_correction not in paire_de_moyens_par_correction:
                paire_de_moyens_par_correction[identifiant_de_la_correction] = set()
            paire_de_moyens_par_correction[identifiant_de_la_correction].add(
                reglement["moyen"]
            )

        # La part de chaque vente liée.
        # / Each linked sale's part.
        part_par_vente_liee = {}
        for part_de_la_vente in parts_des_ventes_liees:
            part_par_vente_liee[part_de_la_vente["vente_id"]] = part_de_la_vente[
                "total_en_centimes"
            ]

        # Le moyen où se trouve la part de chaque vente liée : son seul moyen.
        # / The method holding each linked sale's part: its only method.
        moyens_par_vente_liee = {}
        for vente_et_moyen in moyens_des_ventes_liees:
            identifiant_de_la_vente = vente_et_moyen["vente_id"]
            if identifiant_de_la_vente not in moyens_par_vente_liee:
                moyens_par_vente_liee[identifiant_de_la_vente] = set()
            moyens_par_vente_liee[identifiant_de_la_vente].add(vente_et_moyen["moyen"])
        moyen_de_la_part_par_vente_liee = {}
        ventes_liees_et_leurs_moyens = moyens_par_vente_liee.items()
        for identifiant_de_la_vente, moyens_de_la_vente in ventes_liees_et_leurs_moyens:
            if len(moyens_de_la_vente) == 1:
                moyen_de_la_part_par_vente_liee[identifiant_de_la_vente] = list(
                    moyens_de_la_vente
                )[0]

        # Chaque correction, dans l'ordre des numéros, déplace la part si son moyen
        # est dans la paire. Seules les corrections de la période émettent.
        # / Each correction, by number, moves the part if its method is in the
        # pair. Only the period's corrections emit.
        parts_deplacees = []
        for correction_de_la_vente_liee in toutes_les_corrections_des_ventes_liees:
            identifiant_de_la_correction = correction_de_la_vente_liee["pk"]
            identifiant_de_la_vente_liee = correction_de_la_vente_liee["vente_liee_id"]
            paire_de_moyens = paire_de_moyens_par_correction.get(
                identifiant_de_la_correction, set()
            )
            if len(paire_de_moyens) != 2:
                continue
            moyen_de_la_part = moyen_de_la_part_par_vente_liee.get(
                identifiant_de_la_vente_liee
            )
            if moyen_de_la_part not in paire_de_moyens:
                continue
            autres_moyens_de_la_paire = paire_de_moyens - {moyen_de_la_part}
            moyen_d_arrivee = list(autres_moyens_de_la_paire)[0]
            moyen_de_la_part_par_vente_liee[identifiant_de_la_vente_liee] = (
                moyen_d_arrivee
            )

            part = part_par_vente_liee.get(identifiant_de_la_vente_liee, 0)
            correction_de_la_periode = (
                identifiant_de_la_correction
                in identifiants_des_corrections_de_la_periode
            )
            if part and correction_de_la_periode:
                parts_deplacees.append((moyen_de_la_part, moyen_d_arrivee, part))
        return parts_deplacees

    def _articles_d_ecart_d_encaissement(self):
        """
        Les articles « Écart d'encaissement » des ventes en euros, toutes natures,
        reconnus par le nom de leur produit système (comme `compte_pour_article`).
        / Collection gap items of euro sales, every nature, recognised by name.
        """
        return self._articles_des_ventes_en_euros().filter(
            hors_chiffre_affaires=True,
            pricesold__productsold__product__name__in=NOMS_DES_ECARTS_D_ENCAISSEMENT,
        )

    def _articles_d_ecart_payes_en_cashless(self):
        """
        Les articles « Écart d'encaissement » des ventes qui ont au moins un règlement
        cashless (monnaie locale, monnaie fédérée, jetons) : l'écart d'un tirage ou d'un
        paiement QR / NFC. Aucun argent n'a bougé pour eux. Une vente qui mêle argent,
        cashless et écart n'existe pas : un écart vient d'un seul paiement (Stripe,
        tirage, QR / NFC).
        / Gap items of sales with at least one cashless payment (tap, QR / NFC): no
        money moved. A sale mixing money, cashless and a gap does not exist.
        """
        un_reglement_cashless_de_la_vente = Reglement.objects.filter(
            vente_id=OuterRef("vente_id"),
            moyen__in=MOYENS_CASHLESS,
        )
        return self._articles_d_ecart_d_encaissement().filter(
            Exists(un_reglement_cashless_de_la_vente)
        )

    def _reglements_d_argent(self):
        """
        Les règlements d'argent au sens strict des ventes en euros, TOUTES natures
        (vidages compris).
        / Money payments of euro sales, every nature (card emptying included).
        """
        return self._reglements_des_ventes_en_euros().exclude(
            moyen__in=MOYENS_QUI_NE_SONT_PAS_DE_L_ARGENT
        )

    # ------------------------------------------------------------------
    # Section 1 — En-tête
    # / Section 1 — Header
    # ------------------------------------------------------------------

    def section_en_tete(self):
        """
        Le lieu, ses mentions légales, la période, la plage des numéros de ventes et le
        nombre de ventes, toutes unités. Dont gratuites : ventes de nature VENTE réglées
        à total_ttc 0, toutes unités (recharge cadeau, panier offert et recharge offerte
        en points compris ; une vente en points payée ne vaut jamais 0). Le niveau, le
        numéro de clôture et le total perpétuel sont ajoutés par la clôture.
        Les mentions légales sont lues dans `Configuration` au moment du calcul. Elles
        sont figées dans le Z à la clôture : un ancien Z garde l'ancienne adresse, même
        si le lieu en change ensuite. Un champ vide vaut "".
        Le fuseau horaire du lieu (son nom, ex. « Europe/Paris ») est figé de la même
        façon : les heures d'un Z s'affichent toujours dans le fuseau de son calcul
        (comptabilite/presentation.py), même si le lieu change de fuseau ensuite.
        / Venue, legal mentions and time zone (read now, frozen in the Z), period, range
        of sale numbers, number of sales (free ones included).
        """
        configuration = Configuration.get_solo()

        # L'adresse est la rue de l'adresse postale du lieu, s'il en a une.
        # / The address is the street of the venue's postal address, if any.
        adresse_postale = configuration.postal_address
        if adresse_postale is not None and adresse_postale.street_address:
            adresse = str(adresse_postale.street_address)
        else:
            adresse = ""

        valeurs_des_mentions = {
            "organisation": configuration.organisation,
            "adresse": adresse,
            "code_postal": configuration.postal_code,
            "ville": configuration.city,
            "siren": configuration.siren,
            "numero_tva": configuration.tva_number,
            "email": configuration.email,
            "telephone": configuration.phone,
        }
        mentions_legales = {}
        for nom_de_la_mention, valeur in valeurs_des_mentions.items():
            if valeur is None:
                mentions_legales[nom_de_la_mention] = ""
            else:
                mentions_legales[nom_de_la_mention] = str(valeur)

        ventes_reglees = self._ventes_reglees()
        bornes_de_la_plage = ventes_reglees.aggregate(
            numero_premiere_vente=Min("numero"),
            numero_derniere_vente=Max("numero"),
            nombre_de_ventes=Count("pk"),
        )
        nombre_de_ventes_gratuites = ventes_reglees.filter(
            nature=Vente.Nature.VENTE, total_ttc=0
        ).count()

        return {
            "lieu": str(configuration.organisation),
            "mentions_legales": mentions_legales,
            "fuseau_horaire": str(configuration.fuseau_horaire),
            "debut": self.debut.isoformat(),
            "fin": self.fin.isoformat(),
            "numero_premiere_vente": bornes_de_la_plage["numero_premiere_vente"],
            "numero_derniere_vente": bornes_de_la_plage["numero_derniere_vente"],
            "nombre_de_ventes": bornes_de_la_plage["nombre_de_ventes"],
            "nombre_de_ventes_gratuites": nombre_de_ventes_gratuites,
        }

    # ------------------------------------------------------------------
    # Section 2 — Chiffre d'affaires
    # / Section 2 — Revenue
    # ------------------------------------------------------------------

    def section_chiffre_affaires(self):
        """
        Le chiffre d'affaires TTC / HT / TVA, puis par taux, par catégorie, par origine
        et par journal. Chaque total est la somme des montants écrits sur les lignes
        (TVA calculée par ligne, D6), jamais un HT recalculé sur un total.
        / Revenue incl. tax / excl. tax / VAT, by rate, category, origin and journal.
        """
        articles_du_chiffre_d_affaires = self._articles_du_chiffre_d_affaires()
        totaux = articles_du_chiffre_d_affaires.aggregate(**_sommes_ttc_ht_tva())

        return {
            "total_ttc_en_centimes": totaux["total_ttc_en_centimes"],
            "total_ht_en_centimes": totaux["total_ht_en_centimes"],
            "total_tva_en_centimes": totaux["total_tva_en_centimes"],
            "par_moyen": self._chiffre_affaires_par_moyen(),
            "par_taux": self._chiffre_affaires_par_taux(articles_du_chiffre_d_affaires),
            "par_categorie": self._chiffre_affaires_par_categorie(
                articles_du_chiffre_d_affaires
            ),
            "par_origine": self._chiffre_affaires_par_origine(
                articles_du_chiffre_d_affaires
            ),
            "par_journal": self._chiffre_affaires_par_journal(
                articles_du_chiffre_d_affaires
            ),
        }

    def _chiffre_affaires_par_moyen(self):
        """
        Le chiffre d'affaires TTC par moyen de paiement (argent et cashless) : les
        règlements des ventes VENTE, AVOIR et CORRECTION par moyen, moins la part
        HORS chiffre d'affaires de chaque vente (recharges, écarts d'encaissement,
        autres articles hors chiffre d'affaires), imputée au moyen de cette vente.
        Un avoir y est en négatif (un remboursement d'article est du chiffre
        d'affaires négatif) ; une correction déplace l'argent d'un moyen à l'autre.
        / Revenue by payment method: payments by method minus each sale's off-revenue
        part, charged to that sale's method. Credit notes are negative; corrections
        move money between methods.

        L'IMPUTATION (même règle que les recharges par moyen, section 7) : une vente
        qui contient un article hors chiffre d'affaires a le plus souvent un seul moyen
        (une recharge payante ne se paie jamais en cashless ; un écart vient d'un
        paiement Stripe, d'un tirage de la tireuse ou d'un paiement QR / NFC, et porte
        alors le moyen de ce paiement). Une vente avec plusieurs moyens (tirage payé en
        jetons et en monnaie locale, QR payé en deux monnaies), ou sans aucun, impute sa
        part hors chiffre d'affaires sous « plusieurs_moyens » : rien n'est perdu.
        / Imputation: a sale holding an off-revenue item has one method; otherwise
        "plusieurs_moyens".

        LA CORRECTION D'UNE RECHARGE : une vente CORRECTION déplace tout l'argent des
        lignes corrigées, recharge comprise. La part hors chiffre d'affaires de ces
        lignes suit l'argent : retirée du moyen d'arrivée, rendue au moyen de départ
        (`_parts_deplacees_par_les_corrections`, sans dépendre du signe).
        / A correction moves the top-up money too: its off-revenue part is removed
        from the arrival method and given back to the departure one.

        INVARIANT : Σ des `total_en_centimes` = le chiffre d'affaires TTC. Il découle
        de la 2ᵉ égalité de chaque vente (Σ règlements hors offert = Σ nets vendus).
        Il suppose qu'une vente en euros n'a aucun règlement NM (points) : le service
        de vente ne l'interdit pas, et un tel règlement compte dans la 2ᵉ égalité mais
        pas ici. L'affichage vérifie l'invariant et le signale s'il casse.
        / Invariant: the sum equals the revenue incl. tax. It assumes no euro sale has
        an NM payment; the display checks it.

        :return: {code du moyen: {"libelle", "total_en_centimes"}} ; les montants
            nuls sont gardés (un moyen corrigé à 0 reste visible)
        """
        ventes_de_la_section = self._ventes_en_euros().filter(
            nature__in=NATURES_DES_REGLEMENTS
        )
        sommes_par_vente_et_moyen = (
            Reglement.objects.filter(vente__in=ventes_de_la_section)
            .exclude(moyen__in=MOYENS_HORS_ARGENT)
            .values("vente", "moyen")
            .annotate(total_en_centimes=Sum("montant"))
            .order_by("vente", "moyen")
        )
        hors_chiffre_affaires_par_vente = (
            LigneArticle.objects.filter(
                vente__in=ventes_de_la_section,
                hors_chiffre_affaires=True,
            )
            .values("vente")
            .annotate(total_en_centimes=Sum("total_ttc"))
            .order_by("vente")
        )

        # 1. Les règlements, additionnés par moyen ; et les moyens de chaque vente.
        # / 1. Payments summed by method; and each sale's methods.
        par_moyen = {}
        moyens_par_vente = {}
        for somme_du_groupe in sommes_par_vente_et_moyen:
            code_du_moyen = somme_du_groupe["moyen"]
            identifiant_de_la_vente = somme_du_groupe["vente"]
            _ajouter_au_moyen(
                par_moyen,
                code_du_moyen,
                nom_du_moyen_de_paiement(code_du_moyen),
                somme_du_groupe["total_en_centimes"],
            )
            if identifiant_de_la_vente not in moyens_par_vente:
                moyens_par_vente[identifiant_de_la_vente] = set()
            moyens_par_vente[identifiant_de_la_vente].add(code_du_moyen)

        # 2. La part hors chiffre d'affaires de chaque vente, retirée de son moyen.
        # / 2. Each sale's off-revenue part, removed from its method.
        for hors_chiffre_affaires_de_la_vente in hors_chiffre_affaires_par_vente:
            montant_hors_chiffre_affaires = hors_chiffre_affaires_de_la_vente[
                "total_en_centimes"
            ]
            if montant_hors_chiffre_affaires == 0:
                continue
            moyens_de_la_vente = moyens_par_vente.get(
                hors_chiffre_affaires_de_la_vente["vente"], set()
            )
            if len(moyens_de_la_vente) == 1:
                cle_du_moyen = list(moyens_de_la_vente)[0]
                libelle_du_moyen = nom_du_moyen_de_paiement(cle_du_moyen)
            else:
                cle_du_moyen = CLE_PLUSIEURS_MOYENS
                libelle_du_moyen = gettext("Plusieurs moyens")
            _ajouter_au_moyen(
                par_moyen,
                cle_du_moyen,
                libelle_du_moyen,
                -montant_hors_chiffre_affaires,
            )

        # 3. La part hors chiffre d'affaires déplacée par une correction : retirée du
        #    moyen d'arrivée, rendue au moyen de départ.
        # / 3. The off-revenue part moved by a correction: removed from the arrival
        #    method, given back to the departure method.
        parts_deplacees = self._parts_deplacees_par_les_corrections(
            Q(hors_chiffre_affaires=True), MOYENS_HORS_ARGENT
        )
        for moyen_de_depart, moyen_d_arrivee, part in parts_deplacees:
            _ajouter_au_moyen(
                par_moyen, moyen_d_arrivee, nom_du_moyen_de_paiement(moyen_d_arrivee), -part
            )
            _ajouter_au_moyen(
                par_moyen, moyen_de_depart, nom_du_moyen_de_paiement(moyen_de_depart), part
            )
        return par_moyen

    def _chiffre_affaires_par_taux(self, articles_du_chiffre_d_affaires):
        """
        Clé : le taux stocké sur la ligne, en texte (« 20.00 », « 5.50 »).
        La part payée en jetons cadeau de chaque article (`part_en_jetons`) est vendue
        hors TVA (D8 bis) : elle va au taux « 0.00 » (HT = TTC, TVA 0), et le reste de
        l'article à son taux. Le total du chiffre d'affaires ne change pas.
        Un taux dont TOUTES les lignes sont entièrement en jetons n'a plus rien à
        montrer : il n'apparaît pas. Un taux qui vaut 0 pour une autre raison (une
        vente et son avoir qui s'annulent) reste affiché, comme sans jetons.
        / Key: the rate stored on the line, as text. Each item's token part goes to the
        "0.00" rate (HT = TTC, VAT 0), the rest to its rate. A rate whose lines are ALL
        fully token-paid is not shown; a rate at 0 for another reason stays.
        """
        lignes_entierement_en_jetons = Q(part_en_jetons=F("total_ttc")) & ~Q(
            part_en_jetons=0
        )
        sommes_par_taux = (
            articles_du_chiffre_d_affaires.values("vat")
            .annotate(
                **_sommes_ttc_ht_tva(),
                part_en_jetons_en_centimes=Coalesce(Sum("part_en_jetons"), 0),
                nombre_de_lignes_avec_un_reste=Count(
                    "pk", filter=~lignes_entierement_en_jetons
                ),
            )
            .order_by("vat")
        )
        par_taux = {}
        cle_du_taux_zero = "0.00"
        total_des_jetons = 0
        for sommes_du_taux in sommes_par_taux:
            part_en_jetons_du_taux = sommes_du_taux["part_en_jetons_en_centimes"]
            total_des_jetons += part_en_jetons_du_taux

            # Le reste du taux : ses sommes, moins la part en jetons (hors TVA : elle
            # est dans son HT et son TTC, jamais dans sa TVA).
            # / The rate's rest: its sums minus the token part (in HT and TTC only).
            reste_du_taux = {
                "total_ttc_en_centimes": (
                    sommes_du_taux["total_ttc_en_centimes"] - part_en_jetons_du_taux
                ),
                "total_ht_en_centimes": (
                    sommes_du_taux["total_ht_en_centimes"] - part_en_jetons_du_taux
                ),
                "total_tva_en_centimes": sommes_du_taux["total_tva_en_centimes"],
            }

            # Un taux dont toutes les lignes sont entièrement en jetons n'a plus rien
            # à montrer.
            # / A rate whose lines are all fully token-paid has nothing left to show.
            taux_entierement_en_jetons = (
                sommes_du_taux["nombre_de_lignes_avec_un_reste"] == 0
            )
            if taux_entierement_en_jetons:
                continue

            cle_du_taux = str(sommes_du_taux["vat"])
            if cle_du_taux not in par_taux:
                par_taux[cle_du_taux] = {
                    "total_ttc_en_centimes": 0,
                    "total_ht_en_centimes": 0,
                    "total_tva_en_centimes": 0,
                }
            _ajouter_les_trois_totaux(par_taux[cle_du_taux], reste_du_taux)

        # Les jetons de tous les taux, au taux « 0.00 » : HT = TTC, TVA 0.
        # / The tokens of every rate, at the "0.00" rate: HT = TTC, VAT 0.
        if total_des_jetons != 0:
            if cle_du_taux_zero not in par_taux:
                par_taux[cle_du_taux_zero] = {
                    "total_ttc_en_centimes": 0,
                    "total_ht_en_centimes": 0,
                    "total_tva_en_centimes": 0,
                }
            par_taux[cle_du_taux_zero]["total_ttc_en_centimes"] += total_des_jetons
            par_taux[cle_du_taux_zero]["total_ht_en_centimes"] += total_des_jetons
        return par_taux

    def _chiffre_affaires_par_categorie(self, articles_du_chiffre_d_affaires):
        """
        Clé et nom : `_cle_et_nom_de_la_categorie` (catégorie de caisse, sinon type
        du produit). Le tri par nom est départagé par l'uuid de la catégorie : deux
        catégories de même nom gardent toujours le même ordre.
        / Key and name from the POS category, otherwise the product type; stable order.
        """
        sommes_par_categorie = (
            articles_du_chiffre_d_affaires.values(
                "pricesold__productsold__product__categorie_pos",
                "pricesold__productsold__product__categorie_pos__name",
                "pricesold__productsold__product__categorie_article",
            )
            .annotate(**_sommes_ttc_ht_tva())
            .order_by(
                "pricesold__productsold__product__categorie_pos__name",
                "pricesold__productsold__product__categorie_pos",
                "pricesold__productsold__product__categorie_article",
            )
        )
        par_categorie = {}
        for sommes_de_la_categorie in sommes_par_categorie:
            cle_de_la_categorie, nom_de_la_categorie = _cle_et_nom_de_la_categorie(
                sommes_de_la_categorie["pricesold__productsold__product__categorie_pos"],
                sommes_de_la_categorie[
                    "pricesold__productsold__product__categorie_pos__name"
                ],
                sommes_de_la_categorie[
                    "pricesold__productsold__product__categorie_article"
                ],
            )

            # Un même produit sans catégorie de caisse peut venir de plusieurs groupes
            # de la base : les totaux s'additionnent.
            # / Several database groups may share a key: totals are added.
            if cle_de_la_categorie not in par_categorie:
                par_categorie[cle_de_la_categorie] = {
                    "nom": nom_de_la_categorie,
                    "total_ttc_en_centimes": 0,
                    "total_ht_en_centimes": 0,
                    "total_tva_en_centimes": 0,
                }
            _ajouter_les_trois_totaux(
                par_categorie[cle_de_la_categorie], sommes_de_la_categorie
            )
        return par_categorie

    def _chiffre_affaires_par_origine(self, articles_du_chiffre_d_affaires):
        """
        Clé : le code de l'origine de la vente (`SaleOrigin`, ex. « LB », « LP »).
        / Key: the sale origin code.
        """
        libelles_des_origines = dict(SaleOrigin.choices)
        sommes_par_origine = (
            articles_du_chiffre_d_affaires.values("vente__origine")
            .annotate(**_sommes_ttc_ht_tva())
            .order_by("vente__origine")
        )
        par_origine = {}
        for sommes_de_l_origine in sommes_par_origine:
            code_de_l_origine = sommes_de_l_origine["vente__origine"]
            libelle_de_l_origine = str(
                libelles_des_origines.get(code_de_l_origine, code_de_l_origine)
            )
            ligne_de_l_origine = {
                "libelle": libelle_de_l_origine,
                "total_ttc_en_centimes": 0,
                "total_ht_en_centimes": 0,
                "total_tva_en_centimes": 0,
            }
            _ajouter_les_trois_totaux(ligne_de_l_origine, sommes_de_l_origine)
            par_origine[code_de_l_origine] = ligne_de_l_origine
        return par_origine

    def _chiffre_affaires_par_journal(self, articles_du_chiffre_d_affaires):
        """
        Clé : le code journal de la vente (`journal_pour(point de vente, origine)`,
        fiche E §3.2). Si le journal est impossible (point de vente au nom sans
        lettre, origine sans journal), la vente va sous « ? », avec un libellé qui
        renvoie à « Plan complet ? » : le rapport ne tombe jamais à cause du plan.
        / Key: the sale's journal code; impossible journal → "?", the report never fails.
        """
        sommes_par_point_de_vente_et_origine = (
            articles_du_chiffre_d_affaires.values(
                "vente__point_de_vente", "vente__origine"
            )
            .annotate(**_sommes_ttc_ht_tva())
            .order_by("vente__point_de_vente", "vente__origine")
        )

        # Les points de vente lus en une seule requête.
        # / Points of sale read in one query.
        identifiants_des_points_de_vente = []
        for sommes_du_groupe in sommes_par_point_de_vente_et_origine:
            identifiant = sommes_du_groupe["vente__point_de_vente"]
            if identifiant is not None:
                identifiants_des_points_de_vente.append(identifiant)
        points_de_vente_par_identifiant = PointDeVente.objects.in_bulk(
            identifiants_des_points_de_vente
        )

        par_journal = {}
        for sommes_du_groupe in sommes_par_point_de_vente_et_origine:
            point_de_vente = points_de_vente_par_identifiant.get(
                sommes_du_groupe["vente__point_de_vente"]
            )
            origine = sommes_du_groupe["vente__origine"]
            try:
                code_du_journal = journal_pour(point_de_vente, origine)
                if point_de_vente is not None:
                    libelle_du_journal = point_de_vente.name
                else:
                    libelle_du_journal = code_du_journal
            except CompteComptableManquant:
                code_du_journal = CLE_DU_JOURNAL_IMPOSSIBLE
                libelle_du_journal = gettext("À corriger : voir « Plan complet ? »")

            # Deux groupes peuvent avoir le même journal (deux origines sans point de
            # vente qui vont toutes deux au « WEB ») : on additionne.
            # / Two groups may share a journal: they are added up.
            if code_du_journal not in par_journal:
                par_journal[code_du_journal] = {
                    "libelle": libelle_du_journal,
                    "total_ttc_en_centimes": 0,
                    "total_ht_en_centimes": 0,
                    "total_tva_en_centimes": 0,
                }
            _ajouter_les_trois_totaux(par_journal[code_du_journal], sommes_du_groupe)
        return par_journal

    def chiffre_affaires_par_point_de_vente(self):
        """
        Le chiffre d'affaires TTC par point de vente de la vente (caisse, tireuse).
        Les ventes sans point de vente (en ligne, admin, API) sont réunies sous
        « sans_point_de_vente ». Mêmes articles que le chiffre d'affaires : la somme
        des lignes vaut toujours le chiffre d'affaires TTC.
        / Revenue incl. tax by the sale's point of sale; sales without one are under
        "sans_point_de_vente". The rows always add up to the revenue.

        LU PAR : l'écran « Ventes » de la caisse (laboutik/views.py `recap_en_cours`,
        tableau « Par point de vente »). Pas dans le Z : le Z garde le journal
        (`par_journal`), qui suit le plan comptable.
        / Read by the register's Sales screen; not in the Z.

        :return: {uuid du point de vente en texte, ou "sans_point_de_vente":
            {"nom", "total_ttc_en_centimes"}}
        """
        sommes_par_point_de_vente = (
            self._articles_du_chiffre_d_affaires()
            .values("vente__point_de_vente", "vente__point_de_vente__name")
            .annotate(total_ttc_en_centimes=Coalesce(Sum("total_ttc"), 0))
            .order_by("vente__point_de_vente__name", "vente__point_de_vente")
        )
        par_point_de_vente = {}
        for sommes_du_point_de_vente in sommes_par_point_de_vente:
            uuid_du_point_de_vente = sommes_du_point_de_vente["vente__point_de_vente"]
            if uuid_du_point_de_vente is None:
                cle_du_point_de_vente = CLE_SANS_POINT_DE_VENTE
                nom_du_point_de_vente = gettext("Sans point de vente")
            else:
                cle_du_point_de_vente = str(uuid_du_point_de_vente)
                nom_du_point_de_vente = sommes_du_point_de_vente[
                    "vente__point_de_vente__name"
                ]
            par_point_de_vente[cle_du_point_de_vente] = {
                "nom": nom_du_point_de_vente,
                "total_ttc_en_centimes": sommes_du_point_de_vente[
                    "total_ttc_en_centimes"
                ],
            }
        return par_point_de_vente

    # ------------------------------------------------------------------
    # Les deux périmètres : la caisse et le reste (en ligne)
    # / The two scopes: the register and the rest (online)
    # ------------------------------------------------------------------

    def totaux_caisse_et_en_ligne(self):
        """
        Trois totaux de la période, séparés en deux périmètres :
        - « caisse » : les ventes faites SUR UN POINT DE VENTE (`Vente.point_de_vente`
          renseigné), le périmètre du tiroir (`section_caisse_especes`) ;
        - « en_ligne » : toutes les autres ventes réglées (en ligne, admin, QR code,
          API). Une vente n'est jamais dans les deux.
        / Three totals of the period, split into two scopes: sales made at a point of
        sale ("caisse") and every other settled sale ("en_ligne").

        LES TROIS TOTAUX (en centimes, signés comme tout le rapport) :
        - `reglements_en_centimes` : l'argent et le cashless des règlements des natures
          VENTE, AVOIR et CORRECTION, ni offert ni points (les blocs argent et cashless
          de `section_reglements`) ;
        - `recharges_encaissees_en_centimes` : le net des recharges encaissées (le
          total de `section_annexe`, recharges et cartes) ;
        - `adhesions_en_centimes` : le net des articles d'adhésion du chiffre
          d'affaires (les adhésions de `section_detail`).
        / Payments (money + cashless), collected top-ups, membership items.

        LU PAR : les fixtures E2E `rapports_comptables` (tests/e2e/conftest.py), qui
        vérifient au centime ce qu'un parcours a fait entrer dans chaque périmètre.
        / Read by the E2E fixtures, which check each scope to the cent.

        :return: {"caisse": {...}, "en_ligne": {...}}, chaque périmètre avec les trois
            totaux ci-dessus
        """
        totaux_par_perimetre = {}
        perimetres_et_filtre_de_la_vente = [
            ("caisse", {"vente__point_de_vente__isnull": False}),
            ("en_ligne", {"vente__point_de_vente__isnull": True}),
        ]
        for nom_du_perimetre, filtre_de_la_vente in perimetres_et_filtre_de_la_vente:
            reglements = (
                self._reglements_des_ventes_en_euros()
                .filter(vente__nature__in=NATURES_DES_REGLEMENTS, **filtre_de_la_vente)
                .exclude(moyen__in=MOYENS_HORS_ARGENT)
                .aggregate(total=Coalesce(Sum("montant"), 0))["total"]
            )
            recharges_encaissees = (
                self._articles_de_recharge_encaissees()
                .filter(**filtre_de_la_vente)
                .aggregate(total=Coalesce(Sum("total_ttc"), 0))["total"]
            )
            adhesions = (
                self._articles_du_chiffre_d_affaires()
                .filter(membership__isnull=False, **filtre_de_la_vente)
                .aggregate(total=Coalesce(Sum("total_ttc"), 0))["total"]
            )
            totaux_par_perimetre[nom_du_perimetre] = {
                "reglements_en_centimes": reglements,
                "recharges_encaissees_en_centimes": recharges_encaissees,
                "adhesions_en_centimes": adhesions,
            }
        return totaux_par_perimetre

    def perimetre_de_l_article(self, uuid_de_l_article):
        """
        Le périmètre où le rapport voit un article : « caisse » si sa vente réglée de
        la période a un point de vente, « en_ligne » sinon, None si le rapport ne le
        voit pas (vente en attente, annulée, hors période, ou article sans vente).
        Un article est vu PAR SA VENTE, jamais par sa propre date.
        / The scope where the report sees an item: "caisse", "en_ligne", or None.

        LU PAR : la fixture E2E `rapports_qui_voient_la_ligne` (tests/e2e/conftest.py).
        / Read by the E2E fixture rapports_qui_voient_la_ligne.

        :param uuid_de_l_article: uuid de la `LigneArticle` (texte ou UUID)
        :return: "caisse", "en_ligne" ou None
        """
        article_vu = (
            LigneArticle.objects.filter(
                uuid=uuid_de_l_article, vente__in=self._ventes_reglees()
            )
            .values("vente__point_de_vente")
            .first()
        )
        if article_vu is None:
            return None
        if article_vu["vente__point_de_vente"] is None:
            return "en_ligne"
        return "caisse"

    # ------------------------------------------------------------------
    # Section 3 — Règlements
    # / Section 3 — Payments
    # ------------------------------------------------------------------

    def section_reglements(self):
        """
        Les règlements des natures VENTE, AVOIR et CORRECTION (le vidage de carte est
        en section 7), en trois blocs : argent (par moyen), cashless (par moyen, puis
        par monnaie), hors argent (offert, points par monnaie). Les règlements d'une
        correction comptent dans la période où la correction est faite.
        / Payments of VENTE, AVOIR, CORRECTION in three blocks: money, cashless,
        non-money.
        """
        reglements_en_euros_de_la_section = (
            self._reglements_des_ventes_en_euros().filter(
                vente__nature__in=NATURES_DES_REGLEMENTS
            )
        )
        return {
            "argent": self._bloc_argent(reglements_en_euros_de_la_section),
            "cashless": self._bloc_cashless(reglements_en_euros_de_la_section),
            "hors_argent": self._bloc_hors_argent(reglements_en_euros_de_la_section),
        }

    def _bloc_argent(self, reglements_en_euros_de_la_section):
        """
        L'argent au sens strict, par moyen (espèces, CB, chèque, Stripe, virement,
        inconnu). Un moyen apparaît dès qu'il a un règlement, même si sa somme vaut 0
        (une correction qui l'annule).
        / Money in the strict sense, by method; a method shows even when it sums to 0.
        """
        sommes_par_moyen = (
            reglements_en_euros_de_la_section.exclude(
                moyen__in=MOYENS_QUI_NE_SONT_PAS_DE_L_ARGENT
            )
            .values("moyen")
            .annotate(total_en_centimes=Sum("montant"))
            .order_by("moyen")
        )
        total_de_l_argent = 0
        par_moyen = {}
        for somme_du_moyen in sommes_par_moyen:
            code_du_moyen = somme_du_moyen["moyen"]
            par_moyen[code_du_moyen] = {
                "libelle": nom_du_moyen_de_paiement(code_du_moyen),
                "total_en_centimes": somme_du_moyen["total_en_centimes"],
            }
            total_de_l_argent += somme_du_moyen["total_en_centimes"]
        return {"total_en_centimes": total_de_l_argent, "par_moyen": par_moyen}

    def _bloc_cashless(self, reglements_en_euros_de_la_section):
        """
        Le cashless, rangé par moyen (LE, SF, LG), PUIS par monnaie (clé = uuid de la
        monnaie en texte, « sans_monnaie » si le règlement n'en a pas). Une même
        monnaie réglée par deux moyens garde une ligne sous chaque moyen : rien n'est
        écrasé.
        / Cashless by method, THEN by currency: nothing is overwritten.
        """
        sommes_par_moyen_et_monnaie = (
            reglements_en_euros_de_la_section.filter(moyen__in=MOYENS_CASHLESS)
            .values("moyen", "asset")
            .annotate(total_en_centimes=Sum("montant"))
            .order_by("moyen", "asset")
        )
        total_du_cashless = 0
        par_moyen = {}
        for somme_du_groupe in sommes_par_moyen_et_monnaie:
            code_du_moyen = somme_du_groupe["moyen"]
            montant_du_groupe = somme_du_groupe["total_en_centimes"]

            if code_du_moyen not in par_moyen:
                par_moyen[code_du_moyen] = {
                    "libelle": nom_du_moyen_de_paiement(code_du_moyen),
                    "total_en_centimes": 0,
                    "par_monnaie": {},
                }
            ligne_du_moyen = par_moyen[code_du_moyen]

            cle_de_la_monnaie, nom_lisible_de_la_monnaie = _cle_et_nom_de_la_monnaie(
                somme_du_groupe["asset"]
            )
            ligne_du_moyen["par_monnaie"][cle_de_la_monnaie] = {
                "nom": nom_lisible_de_la_monnaie,
                "total_en_centimes": montant_du_groupe,
            }
            ligne_du_moyen["total_en_centimes"] += montant_du_groupe
            total_du_cashless += montant_du_groupe
        return {"total_en_centimes": total_du_cashless, "par_moyen": par_moyen}

    def _bloc_hors_argent(self, reglements_en_euros_de_la_section):
        """
        Hors argent : l'offert des ventes en euros (Σ des règlements FREE, recharge
        cadeau comprise) et les points, par monnaie, en centièmes de points. Les points
        viennent des ventes en points (leur unité est la monnaie de points).
        / Non-money: offered (FREE payments of euro sales) and points by currency.
        """
        offert = reglements_en_euros_de_la_section.filter(
            moyen=PaymentMethod.FREE
        ).aggregate(total=Coalesce(Sum("montant"), 0))["total"]

        sommes_des_points = (
            Reglement.objects.filter(
                vente__in=self._ventes_reglees(),
                vente__nature__in=NATURES_DES_REGLEMENTS,
                moyen=PaymentMethod.NON_MONETAIRE,
            )
            .values("asset")
            .annotate(total_en_centiemes=Sum("montant"))
            .order_by("asset")
        )
        points_par_monnaie = {}
        for somme_des_points in sommes_des_points:
            cle_de_la_monnaie, nom_lisible_de_la_monnaie = _cle_et_nom_de_la_monnaie(
                somme_des_points["asset"]
            )
            points_par_monnaie[cle_de_la_monnaie] = {
                "nom": nom_lisible_de_la_monnaie,
                "total_en_centiemes": somme_des_points["total_en_centiemes"],
            }
        return {"offert_en_centimes": offert, "points_par_monnaie": points_par_monnaie}

    # ------------------------------------------------------------------
    # Section 4 — Caisse espèces (le tiroir)
    # / Section 4 — Cash drawer
    # ------------------------------------------------------------------

    def section_caisse_especes(self):
        """
        Le tiroir de la caisse LaBoutik V2 : fond de caisse, espèces reçues, espèces
        rendues, sorties de caisse, solde théorique.
        / The V2 register cash drawer: float, cash received, cash given back,
        withdrawals, theoretical balance.

        LE PÉRIMÈTRE : seules les ventes faites SUR UN POINT DE VENTE
        (`Vente.point_de_vente` renseigné) passent par le tiroir, toutes natures
        (avoirs et vidages compris). Les espèces déclarées ailleurs (admin, « payé
        ailleurs » de l'API v2, webhook de LaBoutik V1) sont dans un autre tiroir :
        elles restent dans les règlements (section 3), jamais ici.
        / Only sales made at a point of sale go through the drawer; cash declared
        elsewhere stays in section 3.

        LES MONTANTS (signés, comme tout le rapport) :
        - fond de caisse : `LaboutikConfiguration.fond_de_caisse` (0 par défaut) ;
        - espèces reçues : Σ des règlements espèces positifs (≥ 0), hors corrections ;
        - espèces rendues : Σ des règlements espèces négatifs (≤ 0 : avoirs, vidages),
          hors corrections ;
        - corrections : le net en espèces des corrections de moyen de paiement (D14).
          Une correction ne fait pas entrer ni sortir d'argent du tiroir au moment où
          elle est faite : elle dit que l'argent compté à la vente n'était pas le bon.
          Elle est donc sur sa propre ligne ;
        - sorties : Σ des retraits (`SortieCaisse`) faits dans la période, même borne
          que les ventes (`debut <= datetime < fin`), en positif ;
        - solde théorique = fond + reçues + rendues + corrections − sorties.
        / Signed sums; corrections on their own line; balance = cash float + received
        + given back + corrections − withdrawals.
        """
        ventes_passees_par_le_tiroir = self._ventes_en_euros().filter(
            point_de_vente__isnull=False
        )
        reglements_en_especes_du_tiroir = Reglement.objects.filter(
            vente__in=ventes_passees_par_le_tiroir,
            moyen=PaymentMethod.CASH,
        )
        reglements_en_especes_hors_corrections = (
            reglements_en_especes_du_tiroir.exclude(
                vente__nature=Vente.Nature.CORRECTION
            )
        )
        especes_recues = reglements_en_especes_hors_corrections.filter(
            montant__gt=0
        ).aggregate(total=Coalesce(Sum("montant"), 0))["total"]
        especes_rendues = reglements_en_especes_hors_corrections.filter(
            montant__lt=0
        ).aggregate(total=Coalesce(Sum("montant"), 0))["total"]
        corrections = reglements_en_especes_du_tiroir.filter(
            vente__nature=Vente.Nature.CORRECTION
        ).aggregate(total=Coalesce(Sum("montant"), 0))["total"]

        sorties = SortieCaisse.objects.filter(
            datetime__gte=self.debut,
            datetime__lt=self.fin,
        ).aggregate(total=Coalesce(Sum("montant_total"), 0))["total"]

        fond_de_caisse = LaboutikConfiguration.get_solo().fond_de_caisse

        solde_theorique = (
            fond_de_caisse + especes_recues + especes_rendues + corrections - sorties
        )

        return {
            "fond_de_caisse_en_centimes": fond_de_caisse,
            "especes_recues_en_centimes": especes_recues,
            "especes_rendues_en_centimes": especes_rendues,
            "corrections_en_centimes": corrections,
            "sorties_en_centimes": sorties,
            "solde_theorique_en_centimes": solde_theorique,
        }

    # ------------------------------------------------------------------
    # Section 5 — Réconciliation
    # / Section 5 — Reconciliation
    # ------------------------------------------------------------------

    def section_reconciliation(self):
        """
        Les nombres de « Argent reçu = ventes payées en argent + recharges +
        remboursements + cartes vidées + écarts d'encaissement », tous signés. La
        phrase n'est pas stockée : l'affichage l'écrit, dans la langue du lecteur.
        / The signed figures of the reconciliation; the sentence is written by display.

        LES TERMES (tous sur l'argent au sens strict, ventes en euros) :
        - argent reçu : tout l'argent entré moins tout l'argent sorti, TOUTES natures,
          vidages compris (comme le solde de caisse de LaBoutik V1). Il vaut l'argent
          de la section 3 plus les espèces rendues aux vidages ;
        - recharges : Σ net des recharges encaissées (le total de l'annexe) ;
        - écarts d'encaissement : Σ net des articles d'écart EN ARGENT, ceux des ventes
          sans règlement cashless (un écart Stripe). L'écart d'un tirage ou d'un paiement
          QR / NFC est payé en cashless : aucun argent n'a bougé, il reste seulement
          dans l'annexe (« dont payés en cashless ») ;
        - remboursements : l'argent des avoirs, moins les écarts en argent des avoirs
          (déjà comptés dans « écarts ») ;
        - cartes vidées : l'argent des vidages (négatif) ;
        - ventes payées en argent : l'argent des ventes VENTE et CORRECTION, moins les
          recharges et les écarts en argent hors avoirs.
        Argent reçu = somme des cinq termes, par construction.
        En plus, hors de la phrase : les recharges remboursées, le net (négatif) des
        articles de recharge des avoirs. Elles sont déjà dans « remboursements » ;
        les tickets X et Z les impriment sous le total, à côté des recharges (un
        montant brut).
        / The terms; money received equals the sum of the five terms by construction.
        Also, outside the sentence: refunded top-ups (already in refunds), printed
        under the ticket total next to the gross top-ups.
        """
        reglements_d_argent = self._reglements_d_argent()

        argent_recu = reglements_d_argent.aggregate(
            total=Coalesce(Sum("montant"), 0)
        )["total"]
        argent_des_ventes = reglements_d_argent.filter(
            vente__nature__in=[Vente.Nature.VENTE, Vente.Nature.CORRECTION]
        ).aggregate(total=Coalesce(Sum("montant"), 0))["total"]
        argent_des_avoirs = reglements_d_argent.filter(
            vente__nature=Vente.Nature.AVOIR
        ).aggregate(total=Coalesce(Sum("montant"), 0))["total"]
        cartes_videes = reglements_d_argent.filter(
            vente__nature=Vente.Nature.VIDAGE_CARTE
        ).aggregate(total=Coalesce(Sum("montant"), 0))["total"]

        recharges = self._articles_de_recharge_encaissees().aggregate(
            total=Coalesce(Sum("total_ttc"), 0)
        )["total"]
        recharges_remboursees = self._articles_de_recharge_remboursees().aggregate(
            total=Coalesce(Sum("total_ttc"), 0)
        )["total"]

        # Les écarts EN ARGENT : ceux des ventes sans règlement cashless. Une recharge
        # payante ne se paie jamais en cashless : son net est de l'argent.
        # / Gaps IN MONEY: those of sales without a cashless payment.
        ecarts_payes_en_cashless = self._articles_d_ecart_payes_en_cashless()
        identifiants_des_ecarts_cashless = ecarts_payes_en_cashless.values("pk")
        articles_d_ecart_en_argent = self._articles_d_ecart_d_encaissement().exclude(
            pk__in=identifiants_des_ecarts_cashless
        )
        ecarts_en_argent = articles_d_ecart_en_argent.aggregate(
            total=Coalesce(Sum("total_ttc"), 0)
        )["total"]
        ecarts_en_argent_des_avoirs = articles_d_ecart_en_argent.filter(
            vente__nature=Vente.Nature.AVOIR
        ).aggregate(total=Coalesce(Sum("total_ttc"), 0))["total"]
        ecarts_en_argent_hors_avoirs = ecarts_en_argent - ecarts_en_argent_des_avoirs

        remboursements = argent_des_avoirs - ecarts_en_argent_des_avoirs

        ventes_payees_en_argent = (
            argent_des_ventes - recharges - ecarts_en_argent_hors_avoirs
        )

        return {
            "argent_recu_en_centimes": argent_recu,
            "ventes_payees_en_argent_en_centimes": ventes_payees_en_argent,
            "recharges_en_centimes": recharges,
            "recharges_remboursees_en_centimes": recharges_remboursees,
            "remboursements_en_centimes": remboursements,
            "cartes_videes_en_centimes": cartes_videes,
            "ecarts_d_encaissement_en_centimes": ecarts_en_argent,
        }

    # ------------------------------------------------------------------
    # Section 6 — Offerts
    # / Section 6 — Gifts
    # ------------------------------------------------------------------

    def section_offerts(self):
        """
        Le bouton OFFRIR : quantités, valeur catalogue offerte, coût d'achat, sur les
        articles du chiffre d'affaires SEULEMENT. La recharge cadeau (hors chiffre
        d'affaires) n'y est pas : elle est en section 7, « cadeau émis ». Les jetons
        dépensés n'y sont pas : ce sont des ventes (D8 bis). Détail par produit et par
        unité (`_cle_et_unite_d_une_ligne_par_produit`) : quantité dans l'unité de la
        ligne (`unite` : « kg » ou « L » pour les lignes au poids ou au volume, vide à
        la pièce). La quantité totale est un nombre d'articles : une pesée compte pour
        un.
        / The GIFT button, on revenue items only; detail by product and unit; the total
        quantity counts a weighing as one item.
        """
        articles_offerts = self._articles_du_chiffre_d_affaires().filter(
            source_offert=LigneArticle.SourceOffert.OFFRIR
        )
        totaux = articles_offerts.aggregate(
            quantite=Sum(quantite_en_nombre_d_articles()),
            valeur_catalogue_en_centimes=Coalesce(Sum("part_offerte"), 0),
            cout_achat_en_centimes=Coalesce(Sum("cout_achat"), 0),
        )
        sommes_par_produit = (
            articles_offerts.annotate(
                au_poids_ou_au_volume=_ligne_au_poids_ou_au_volume()
            )
            .values(
                "pricesold__productsold__product",
                "pricesold__productsold__product__name",
                "pricesold__productsold__product__categorie_article",
                "pricesold__productsold__product__stock_inventaire__unite",
                "au_poids_ou_au_volume",
            )
            .annotate(
                quantite=Sum("qty"),
                valeur_catalogue_en_centimes=Coalesce(Sum("part_offerte"), 0),
                cout_achat_en_centimes=Coalesce(Sum("cout_achat"), 0),
            )
            .order_by("pricesold__productsold__product__name")
        )

        # Une quantité est un `Decimal` : elle est rendue en texte (JSON).
        # / A quantity is a Decimal: returned as text (JSON).
        par_produit = {}
        for sommes_du_produit in sommes_par_produit:
            cle_de_la_ligne, unite_de_la_quantite = (
                _cle_et_unite_d_une_ligne_par_produit(sommes_du_produit)
            )
            par_produit[cle_de_la_ligne] = {
                "nom": sommes_du_produit["pricesold__productsold__product__name"],
                "quantite": str(sommes_du_produit["quantite"]),
                "unite": unite_de_la_quantite,
                "valeur_catalogue_en_centimes": sommes_du_produit[
                    "valeur_catalogue_en_centimes"
                ],
                "cout_achat_en_centimes": sommes_du_produit["cout_achat_en_centimes"],
            }

        quantite_totale = totaux["quantite"]
        if quantite_totale is None:
            quantite_totale = Decimal("0")

        return {
            "quantite": str(quantite_totale),
            "valeur_catalogue_en_centimes": totaux["valeur_catalogue_en_centimes"],
            "cout_achat_en_centimes": totaux["cout_achat_en_centimes"],
            "par_produit": par_produit,
        }

    # ------------------------------------------------------------------
    # Section 7 — Annexe
    # / Section 7 — Appendix
    # ------------------------------------------------------------------

    def section_annexe(self):
        """
        Quatre sous-listes : avoirs, recharges et cartes, écarts d'encaissement,
        corrections.
        / Four sub-lists: credit notes, top-ups and cards, gaps, corrections.
        """
        return {
            "avoirs": self._annexe_avoirs(),
            "recharges_et_cartes": self._annexe_recharges_et_cartes(),
            "ecarts_d_encaissement": self._annexe_ecarts_d_encaissement(),
            "corrections": self._annexe_corrections(),
        }

    def _annexe_avoirs(self):
        """
        Les avoirs en euros : nombre, total net, règlements par moyen hors offert (leur
        somme vaut le total net) ; dont retours consigne (D11, en unités) ; dont
        remboursements Stripe à faire à la main (règlements Stripe négatifs sans
        `reference_externe` : aucun appel à Stripe, D27).
        / Credit notes; payments by method except offered; deposit returns (units);
        Stripe refunds to do by hand.
        """
        ventes_d_avoir = self._ventes_en_euros().filter(nature=Vente.Nature.AVOIR)
        totaux_des_avoirs = ventes_d_avoir.aggregate(
            nombre=Count("pk"),
            total_en_centimes=Coalesce(Sum("total_ttc"), 0),
        )

        sommes_par_moyen = (
            Reglement.objects.filter(vente__in=ventes_d_avoir)
            .exclude(moyen=PaymentMethod.FREE)
            .values("moyen")
            .annotate(total_en_centimes=Sum("montant"))
            .order_by("moyen")
        )
        par_moyen = {}
        for somme_du_moyen in sommes_par_moyen:
            code_du_moyen = somme_du_moyen["moyen"]
            par_moyen[code_du_moyen] = {
                "libelle": nom_du_moyen_de_paiement(code_du_moyen),
                "total_en_centimes": somme_du_moyen["total_en_centimes"],
            }

        # Retours consigne : le nombre est un nombre de gobelets rendus. La ligne d'un
        # retour a une quantité NÉGATIVE et un prix positif (D13) : le nombre de
        # gobelets est l'opposé de la somme des quantités. Le `int()` porte sur une
        # quantité, jamais sur de l'argent.
        # / Deposit returns: a number of cups, minus the sum of the (negative)
        # quantities.
        totaux_des_retours = LigneArticle.objects.filter(
            vente__in=ventes_d_avoir,
            pricesold__productsold__product__methode_caisse=Product.RETOUR_CONSIGNE,
        ).aggregate(
            quantite=Sum("qty"),
            total_en_centimes=Coalesce(Sum("total_ttc"), 0),
        )
        quantite_des_retours = totaux_des_retours["quantite"]
        if quantite_des_retours is None:
            quantite_des_retours = Decimal("0")

        totaux_stripe_a_la_main = Reglement.objects.filter(
            vente__in=ventes_d_avoir,
            moyen__in=MOYENS_STRIPE,
            montant__lt=0,
            reference_externe="",
        ).aggregate(
            nombre=Count("pk"),
            total_en_centimes=Coalesce(Sum("montant"), 0),
        )

        return {
            "nombre": totaux_des_avoirs["nombre"],
            "total_en_centimes": totaux_des_avoirs["total_en_centimes"],
            "par_moyen": par_moyen,
            "retours_consigne": {
                "nombre": int(-quantite_des_retours),
                "total_en_centimes": totaux_des_retours["total_en_centimes"],
            },
            "remboursements_stripe_a_faire_a_la_main": {
                "nombre": totaux_stripe_a_la_main["nombre"],
                "total_en_centimes": totaux_stripe_a_la_main["total_en_centimes"],
            },
        }

    def _annexe_recharges_et_cartes(self):
        """
        Recharges encaissées (par moyen d'argent), cadeau émis, cartes vidées
        (espèces rendues, jetons cadeau repris). Ventes en euros seulement : une
        recharge offerte en points est en section 8.
        / Collected top-ups (by money method), gift issued, emptied cards; euro sales.
        """
        articles_de_recharge = self._articles_de_recharge_encaissees()
        totaux_des_recharges = articles_de_recharge.aggregate(
            total_en_centimes=Coalesce(Sum("total_ttc"), 0),
            cadeau_emis_en_centimes=Coalesce(Sum("part_offerte"), 0),
        )

        ventes_de_vidage = self._ventes_en_euros().filter(
            nature=Vente.Nature.VIDAGE_CARTE
        )
        especes_rendues = Reglement.objects.filter(
            vente__in=ventes_de_vidage,
            moyen=PaymentMethod.CASH,
        ).aggregate(total=Coalesce(Sum("montant"), 0))["total"]
        jetons_cadeau_repris = (
            self._articles_des_ventes_en_euros()
            .filter(
                pricesold__productsold__product__name=NOM_JETONS_CADEAU_REPRIS_AU_VIDAGE
            )
            .aggregate(total=Coalesce(Sum("total_ttc"), 0))["total"]
        )

        return {
            "recharges_encaissees": {
                "total_en_centimes": totaux_des_recharges["total_en_centimes"],
                "par_moyen": self._recharges_par_moyen(articles_de_recharge),
            },
            "cadeau_emis_en_centimes": totaux_des_recharges["cadeau_emis_en_centimes"],
            "cartes_videes": {
                "nombre": ventes_de_vidage.count(),
                "especes_rendues_en_centimes": especes_rendues,
                "jetons_cadeau_repris_en_centimes": jetons_cadeau_repris,
            },
        }

    def _recharges_par_moyen(self, articles_de_recharge):
        """
        Les recharges encaissées, rangées sous le moyen d'argent de la vente qui les
        contient. Une vente avec une recharge payante a un seul moyen d'argent (la
        caisse refuse le cashless pour une recharge payante). Une vente avec plusieurs
        moyens d'argent, ou sans aucun, range ses recharges sous « plusieurs_moyens » :
        rien n'est perdu. Une recharge dont le moyen a été corrigé est rangée sous le
        moyen corrigé (`_parts_deplacees_par_les_corrections`) ; le moyen de départ
        peut rester à 0. Seules les recharges des ventes de nature VENTE se
        déplacent, comme seules elles sont comptées ici : un avoir de recharge
        corrigé ne change pas les recharges encaissées.
        / Top-ups under their sale's money method; otherwise under "plusieurs_moyens".
        A corrected top-up of a VENTE sale moves to the corrected method.

        UNE CORRECTION D'UNE AUTRE PÉRIODE QUE LA RECHARGE : chaque déplacement est
        compté dans la période de SA correction, la recharge dans la période de sa
        vente. Un déplacement retire autant qu'il ajoute : la somme des recharges par
        moyen vaut toujours le total des recharges de la période. Mais quand la
        recharge est d'une période d'avant, la période de la correction montre une
        ligne négative sous le moyen de départ (et autant en positif sous le moyen
        d'arrivée), alors que sa recharge reste sous le moyen de départ dans le
        rapport de sa propre période. C'est rare : la caisse refuse de corriger une
        vente déjà couverte par une J.
        / A correction in another period than its top-up: each move counts in its
        correction's period; the by-method sum still equals the period's total, but
        that period shows a negative line under the departure method.
        """
        net_des_recharges_par_vente = (
            articles_de_recharge.values("vente")
            .annotate(total_en_centimes=Sum("total_ttc"))
            .order_by("vente")
        )
        moyens_d_argent_des_ventes_de_recharge = (
            Reglement.objects.filter(vente__in=articles_de_recharge.values("vente"))
            .exclude(moyen__in=MOYENS_QUI_NE_SONT_PAS_DE_L_ARGENT)
            .values("vente", "moyen")
            .distinct()
        )

        # Les moyens d'argent de chaque vente, lus en une seule requête.
        # / The money methods of each sale, read in one query.
        moyens_d_argent_par_vente = {}
        for vente_et_moyen in moyens_d_argent_des_ventes_de_recharge:
            identifiant_de_la_vente = vente_et_moyen["vente"]
            if identifiant_de_la_vente not in moyens_d_argent_par_vente:
                moyens_d_argent_par_vente[identifiant_de_la_vente] = set()
            moyens_d_argent_par_vente[identifiant_de_la_vente].add(
                vente_et_moyen["moyen"]
            )

        par_moyen = {}
        for net_de_la_vente in net_des_recharges_par_vente:
            net_des_recharges = net_de_la_vente["total_en_centimes"]

            # Une recharge cadeau a un net de 0 : rien n'est encaissé.
            # / A gift top-up nets to 0: nothing is collected.
            if net_des_recharges == 0:
                continue

            moyens_de_la_vente = moyens_d_argent_par_vente.get(
                net_de_la_vente["vente"], set()
            )
            if len(moyens_de_la_vente) == 1:
                cle_du_moyen = list(moyens_de_la_vente)[0]
                libelle_du_moyen = nom_du_moyen_de_paiement(cle_du_moyen)
            else:
                cle_du_moyen = CLE_PLUSIEURS_MOYENS
                libelle_du_moyen = gettext("Plusieurs moyens")

            _ajouter_au_moyen(
                par_moyen, cle_du_moyen, libelle_du_moyen, net_des_recharges
            )

        # Une recharge dont le moyen a été corrigé passe, avec son argent, du moyen
        # de départ au moyen d'arrivée.
        # / A corrected top-up moves, with its money, from the departure method to
        # the arrival one.
        filtre_des_recharges_deplacees = (
            _filtre_des_articles_de_recharge()
            & Q(hors_chiffre_affaires=True)
            & Q(vente__nature=Vente.Nature.VENTE)
        )
        parts_deplacees = self._parts_deplacees_par_les_corrections(
            filtre_des_recharges_deplacees,
            MOYENS_QUI_NE_SONT_PAS_DE_L_ARGENT,
        )
        for moyen_de_depart, moyen_d_arrivee, part in parts_deplacees:
            _ajouter_au_moyen(
                par_moyen, moyen_de_depart, nom_du_moyen_de_paiement(moyen_de_depart), -part
            )
            _ajouter_au_moyen(
                par_moyen, moyen_d_arrivee, nom_du_moyen_de_paiement(moyen_d_arrivee), part
            )
        return par_moyen

    def _annexe_ecarts_d_encaissement(self):
        """
        Les écarts d'encaissement (D26) : nombre d'articles et total net, toutes
        natures (un remboursement Stripe peut aussi en écrire un), dont la part payée
        en cashless (tirage, paiement QR / NFC : aucun argent n'a bougé).
        / Collection gaps: number of items and net total, every nature, of which the
        part paid in cashless.
        """
        totaux_des_ecarts = self._articles_d_ecart_d_encaissement().aggregate(
            nombre=Count("pk"),
            total_en_centimes=Coalesce(Sum("total_ttc"), 0),
        )
        articles_d_ecart_payes_en_cashless = self._articles_d_ecart_payes_en_cashless()
        ecarts_payes_en_cashless = articles_d_ecart_payes_en_cashless.aggregate(
            total=Coalesce(Sum("total_ttc"), 0)
        )["total"]
        return {
            "nombre": totaux_des_ecarts["nombre"],
            "total_en_centimes": totaux_des_ecarts["total_en_centimes"],
            "dont_payes_en_cashless_en_centimes": ecarts_payes_en_cashless,
        }

    def _annexe_corrections(self):
        """
        Les corrections de moyen de paiement (D14) : pour chacune, son numéro, le
        moyen avant (règlement négatif), le moyen après (règlement positif) et
        l'opérateur.
        L'opérateur est l'IDENTIFIANT de l'utilisateur (uuid en texte), None s'il n'y
        en a pas, jamais son email : ce dictionnaire est scellé dans le Z, jamais
        effaçable. L'écran retrouve le nom à l'affichage.
        / Payment method corrections. The operator is the user's id, never the email:
        this dictionary is sealed in the Z.
        """
        ventes_de_correction = (
            self._ventes_en_euros()
            .filter(nature=Vente.Nature.CORRECTION)
            .prefetch_related("reglements")
            .order_by("numero")
        )
        liste_des_corrections = []
        for vente_de_correction in ventes_de_correction:
            moyens_avant = []
            moyens_apres = []
            for reglement in vente_de_correction.reglements.all():
                if reglement.montant < 0 and reglement.moyen not in moyens_avant:
                    moyens_avant.append(reglement.moyen)
                if reglement.montant > 0 and reglement.moyen not in moyens_apres:
                    moyens_apres.append(reglement.moyen)

            if vente_de_correction.operateur_id is not None:
                operateur = str(vente_de_correction.operateur_id)
            else:
                operateur = None

            liste_des_corrections.append(
                {
                    "numero": vente_de_correction.numero,
                    "moyen_avant": ", ".join(moyens_avant),
                    "moyen_apres": ", ".join(moyens_apres),
                    "operateur": operateur,
                }
            )
        return {"nombre": len(liste_des_corrections), "liste": liste_des_corrections}

    # ------------------------------------------------------------------
    # Section 8 — Points
    # / Section 8 — Points
    # ------------------------------------------------------------------

    def section_points(self):
        """
        Les ventes en points ou en temps (D9), par monnaie (clé = uuid de la monnaie) :
        Σ net des articles et Σ part offerte (une recharge offerte en points), en
        centièmes de points. Elles ne sont ni dans le chiffre d'affaires ni dans
        l'argent.
        / Points sales by currency: net and offered part, in hundredths of points.
        """
        sommes_par_monnaie = (
            LigneArticle.objects.filter(
                vente__in=self._ventes_reglees().exclude(unite="EUR"),
                vente__nature__in=NATURES_DU_CHIFFRE_D_AFFAIRES,
            )
            .values("vente__unite")
            .annotate(
                total_en_centiemes=Coalesce(Sum("total_ttc"), 0),
                offert_en_centiemes=Coalesce(Sum("part_offerte"), 0),
            )
            .order_by("vente__unite")
        )
        points = {}
        for somme_de_la_monnaie in sommes_par_monnaie:
            uuid_de_la_monnaie = somme_de_la_monnaie["vente__unite"]
            points[uuid_de_la_monnaie] = {
                "nom": nom_de_la_monnaie(uuid_de_la_monnaie),
                "total_en_centiemes": somme_de_la_monnaie["total_en_centiemes"],
                "offert_en_centiemes": somme_de_la_monnaie["offert_en_centiemes"],
            }
        return points

    # ------------------------------------------------------------------
    # Section 9 — Marge brute
    # / Section 9 — Gross margin
    # ------------------------------------------------------------------

    def _articles_servis(self):
        """
        Les articles servis (D21) : les articles du chiffre d'affaires (ventes en
        euros) ET les articles des ventes en points, natures VENTE et AVOIR, jamais
        hors chiffre d'affaires (ni recharge, ni écart, ni jetons repris). Vendus,
        offerts, retours de consigne compris.
        / Served items: revenue items AND points sales items, never off-revenue ones.
        """
        return LigneArticle.objects.filter(
            vente__in=self._ventes_reglees(),
            vente__nature__in=NATURES_DU_CHIFFRE_D_AFFAIRES,
            hors_chiffre_affaires=False,
        )

    def section_marge_brute(self):
        """
        Marge brute (D21) = CA HT − Σ des coûts d'achat écrits sur les articles servis.
        Le coût n'est jamais recalculé : il est figé sur l'article à la vente
        (`cout_achat`, en centimes d'euro, même pour une vente en points). Un retour de
        consigne a un coût négatif : il retire le coût du gobelet rendu. Un article
        d'avoir (`ajouter_l_article_d_avoir`) porte en négatif le coût de ce qu'il
        rembourse : une vente remboursée en entier ne coûte plus rien.
        Articles au coût inconnu : articles VENDUS (articles servis des ventes de
        nature VENTE, quantité > 0) sans coût d'achat (`cout_achat` vide, prix d'achat
        0) dont le total catalogue n'est pas nul. Un avoir n'est pas un article vendu,
        ni un retour de consigne (il est dans une vente AVOIR) : le nombre n'est donc
        jamais négatif, même quand la vente d'origine est dans une autre période. Un
        article à 0 € (billet gratuit) ne rend pas la marge incomplète. On compte des
        ARTICLES, pas des lignes : trois planches sur une ligne comptent 3, une pesée
        (0,350 kg de comté) compte 1 (`quantite_en_nombre_d_articles`).
        / Gross margin = revenue excl. tax − Σ purchase costs of served items; SOLD items
        (VENTE sales, quantity > 0) with an unknown cost and a non-zero catalogue total
        are counted: never negative.
        """
        articles_servis = self._articles_servis()
        cout_achat = articles_servis.aggregate(
            total=Coalesce(Sum("cout_achat"), 0)
        )["total"]
        # La somme est un `Decimal` (des lignes de l'historique en parts, à 6
        # décimales) : elle est arrondie à l'unité entière. Ce n'est pas de l'argent.
        # / The sum is a Decimal: rounded to a whole unit. Not money.
        quantite_au_cout_inconnu = (
            articles_servis.filter(
                vente__nature=Vente.Nature.VENTE,
                qty__gt=0,
                cout_achat__isnull=True,
            )
            .exclude(total_catalogue=0)
            .aggregate(total=Sum(quantite_en_nombre_d_articles()))["total"]
        )
        if quantite_au_cout_inconnu is None:
            quantite_au_cout_inconnu = Decimal("0")
        nombre_d_articles_au_cout_inconnu = arrondir_au_centime_demi_haut(
            quantite_au_cout_inconnu
        )
        chiffre_affaires_ht = self._articles_du_chiffre_d_affaires().aggregate(
            total=Coalesce(Sum("total_ht"), 0)
        )["total"]

        return {
            "chiffre_affaires_ht_en_centimes": chiffre_affaires_ht,
            "cout_achat_en_centimes": cout_achat,
            "marge_brute_en_centimes": chiffre_affaires_ht - cout_achat,
            "nombre_d_articles_au_cout_inconnu": nombre_d_articles_au_cout_inconnu,
        }

    # ------------------------------------------------------------------
    # Section 10 — Détail
    # / Section 10 — Detail
    # ------------------------------------------------------------------

    def section_detail(self):
        """
        Le détail imprimé sur le Z : billets (par événement puis par tarif),
        adhésions (par produit), ventes par produit (quantité, TTC, HT, offert, coût).
        Tout est lu sur les articles du chiffre d'affaires (euros) : les ventes en
        points sont en section 8. Une quantité est un `Decimal` : elle est rendue en
        texte (JSON).
        / Detail: tickets by event and price, memberships by product, sales by
        product; revenue items only; quantities as text.
        """
        articles_du_chiffre_d_affaires = self._articles_du_chiffre_d_affaires()
        return {
            "billets": self._detail_des_billets(articles_du_chiffre_d_affaires),
            "adhesions": self._detail_des_adhesions(articles_du_chiffre_d_affaires),
            "ventes_par_produit": self._detail_des_ventes_par_produit(
                articles_du_chiffre_d_affaires
            ),
        }

    def _detail_des_billets(self, articles_du_chiffre_d_affaires):
        """
        Les billets : articles reliés à une réservation. Clé : uuid de l'événement,
        puis uuid du tarif (un tarif vendu a toujours un tarif, un événement toujours
        une date : champs obligatoires).
        / Tickets: items linked to a booking; keyed by event uuid, then price uuid.
        """
        sommes_par_tarif = (
            articles_du_chiffre_d_affaires.filter(reservation__isnull=False)
            .values(
                "reservation__event",
                "reservation__event__name",
                "reservation__event__datetime",
                "pricesold__price",
                "pricesold__price__name",
                "pricesold__productsold__product__name",
            )
            .annotate(
                quantite=Sum("qty"),
                total_ttc_en_centimes=Coalesce(Sum("total_ttc"), 0),
            )
            .order_by(
                "reservation__event__datetime",
                "reservation__event",
                "pricesold__productsold__product__name",
                "pricesold__price__name",
            )
        )

        billets = {}
        for sommes_du_tarif in sommes_par_tarif:
            cle_de_l_evenement = str(sommes_du_tarif["reservation__event"])
            if cle_de_l_evenement not in billets:
                billets[cle_de_l_evenement] = {
                    "nom": sommes_du_tarif["reservation__event__name"],
                    "date": sommes_du_tarif["reservation__event__datetime"].isoformat(),
                    "par_tarif": {},
                }

            cle_du_tarif = str(sommes_du_tarif["pricesold__price"])
            billets[cle_de_l_evenement]["par_tarif"][cle_du_tarif] = {
                "produit": sommes_du_tarif["pricesold__productsold__product__name"],
                "nom": sommes_du_tarif["pricesold__price__name"],
                "quantite": str(sommes_du_tarif["quantite"]),
                "total_ttc_en_centimes": sommes_du_tarif["total_ttc_en_centimes"],
            }
        return billets

    def _detail_des_adhesions(self, articles_du_chiffre_d_affaires):
        """
        Les adhésions : articles reliés à une adhésion. Clé : uuid du produit.
        / Memberships: items linked to a membership; keyed by product uuid.
        """
        sommes_par_produit = (
            articles_du_chiffre_d_affaires.filter(membership__isnull=False)
            .values(
                "pricesold__productsold__product",
                "pricesold__productsold__product__name",
            )
            .annotate(
                quantite=Sum("qty"),
                total_ttc_en_centimes=Coalesce(Sum("total_ttc"), 0),
            )
            .order_by(
                "pricesold__productsold__product__name",
                "pricesold__productsold__product",
            )
        )

        adhesions = {}
        for sommes_du_produit in sommes_par_produit:
            uuid_du_produit = sommes_du_produit["pricesold__productsold__product"]
            adhesions[str(uuid_du_produit)] = {
                "nom": sommes_du_produit["pricesold__productsold__product__name"],
                "quantite": str(sommes_du_produit["quantite"]),
                "total_ttc_en_centimes": sommes_du_produit["total_ttc_en_centimes"],
            }
        return adhesions

    def _detail_des_ventes_par_produit(self, articles_du_chiffre_d_affaires):
        """
        Tous les articles du chiffre d'affaires, par produit (billets et adhésions
        compris) : quantité, TTC, HT, part offerte, coût d'achat. Clé : uuid du
        produit ; `categorie` = la clé de la catégorie dans `par_categorie` (section
        2), pour grouper à l'affichage. Les lignes additionnent exactement le chiffre
        d'affaires. La quantité d'une vente au poids ou au volume est en kg ou en
        litres (D15) : `unite` le dit (« kg », « L »), vide pour des pièces (Q-H4).
        Deux unités ne s'additionnent jamais : un produit vendu au poids ET à la pièce
        donne deux lignes (`_cle_et_unite_d_une_ligne_par_produit`).
        / All revenue items by product and unit; the lines add up exactly to the
        revenue; a product sold by weight and by piece gives two rows.
        """
        sommes_par_produit = (
            articles_du_chiffre_d_affaires.annotate(
                au_poids_ou_au_volume=_ligne_au_poids_ou_au_volume()
            )
            .values(
                "pricesold__productsold__product",
                "pricesold__productsold__product__name",
                "pricesold__productsold__product__categorie_pos",
                "pricesold__productsold__product__categorie_pos__name",
                "pricesold__productsold__product__categorie_article",
                "pricesold__productsold__product__stock_inventaire__unite",
                "au_poids_ou_au_volume",
            )
            .annotate(
                quantite=Sum("qty"),
                total_ttc_en_centimes=Coalesce(Sum("total_ttc"), 0),
                total_ht_en_centimes=Coalesce(Sum("total_ht"), 0),
                offert_en_centimes=Coalesce(Sum("part_offerte"), 0),
                cout_achat_en_centimes=Coalesce(Sum("cout_achat"), 0),
            )
            .order_by(
                "pricesold__productsold__product__name",
                "pricesold__productsold__product",
            )
        )

        ventes_par_produit = {}
        for sommes_du_produit in sommes_par_produit:
            cle_de_la_categorie, _nom_de_la_categorie = _cle_et_nom_de_la_categorie(
                sommes_du_produit["pricesold__productsold__product__categorie_pos"],
                sommes_du_produit[
                    "pricesold__productsold__product__categorie_pos__name"
                ],
                sommes_du_produit["pricesold__productsold__product__categorie_article"],
            )
            cle_de_la_ligne, unite_de_la_quantite = (
                _cle_et_unite_d_une_ligne_par_produit(sommes_du_produit)
            )
            ventes_par_produit[cle_de_la_ligne] = {
                "nom": sommes_du_produit["pricesold__productsold__product__name"],
                "categorie": cle_de_la_categorie,
                "quantite": str(sommes_du_produit["quantite"]),
                "unite": unite_de_la_quantite,
                "total_ttc_en_centimes": sommes_du_produit["total_ttc_en_centimes"],
                "total_ht_en_centimes": sommes_du_produit["total_ht_en_centimes"],
                "offert_en_centimes": sommes_du_produit["offert_en_centimes"],
                "cout_achat_en_centimes": sommes_du_produit["cout_achat_en_centimes"],
            }
        return ventes_par_produit

    # ------------------------------------------------------------------
    # Section 11 — Intégrité
    # / Section 11 — Integrity
    # ------------------------------------------------------------------

    def section_integrite(self):
        """
        La chaîne des ventes vérifiée sur la plage de la période
        (`verifier_chaine_ventes`, laboutik/integrity.py) : statut « OK », ou
        « ANOMALIES » avec leur liste (numéro, uuid, raison). La première vente de la
        plage est reliée à l'empreinte stockée de la précédente. Une période sans vente
        n'a pas de plage : « OK », rien n'est vérifié (sans plage, la fonction
        relirait toute la chaîne du lieu).
        / The sales chain checked over the period's range; no sale: OK, nothing
        checked.
        """
        bornes_de_la_plage = self._ventes_reglees().aggregate(
            numero_premiere_vente=Min("numero"),
            numero_derniere_vente=Max("numero"),
        )
        numero_premiere_vente = bornes_de_la_plage["numero_premiere_vente"]
        numero_derniere_vente = bornes_de_la_plage["numero_derniere_vente"]

        periode_sans_vente = numero_premiere_vente is None
        if periode_sans_vente:
            return {"statut": STATUT_INTEGRITE_OK, "anomalies": []}

        # La clé du lieu, comme à l'encaissement (`encaisser_vente`).
        # / The venue key, as at settlement.
        cle_de_l_empreinte = LaboutikConfiguration.get_solo().get_or_create_hmac_key()
        anomalies = verifier_chaine_ventes(
            cle_de_l_empreinte,
            numero_de_la_premiere_vente=numero_premiere_vente,
            numero_de_la_derniere_vente=numero_derniere_vente,
        )

        if len(anomalies) == 0:
            statut = STATUT_INTEGRITE_OK
        else:
            statut = STATUT_INTEGRITE_ANOMALIES
        return {"statut": statut, "anomalies": anomalies}

    # ------------------------------------------------------------------
    # Rapport X — Habitus des cartes et opérateurs (jamais dans le Z stocké)
    # / X report — Card habits and operators (never in the stored Z)
    # ------------------------------------------------------------------

    def section_habitus_cartes(self):
        """
        L'habitus des cartes NFC, pour le rapport X seulement (temps réel, jamais
        stocké).
        / NFC card habits, for the X report only.

        LES DÉFINITIONS :
        - cartes : les cartes des ventes VENTE en euros de la période, lues sur la
          vente (`Vente.carte`) ET sur leurs règlements cashless (`Reglement.carte` :
          la seconde carte d'un paiement à deux cartes) ; une carte comptée une fois ;
          un vidage n'y entre pas ;
        - dépense d'une carte : Σ des règlements cashless (LE, SF, LG) des ventes
          VENTE, rangés par la carte du règlement (`Reglement.carte`) ; recharge d'une
          carte : Σ net de ses recharges encaissées (une recharge cadeau n'encaisse
          rien : une carte à 0 n'entre pas) ;
        - chaque médiane ne compte que les cartes concernées : une carte qui n'a que
          rechargé n'entre pas dans la médiane des dépenses, et inversement ;
        - panier moyen : total des dépenses / nombre de cartes QUI DÉPENSENT (une carte
          qui n'a que rechargé n'entre pas dans la division) ;
        - reste sur carte : le solde des monnaies locales (TLF) DU LIEU, lu EN DIRECT
          dans le portefeuille de l'utilisateur de la carte, sommé par portefeuille
          (deux cartes d'un même utilisateur partagent un solde) ; la moyenne et la
          médiane se font sur ces soldes. Une carte anonyme (sans
          utilisateur, portefeuille éphémère) n'est pas lue ;
        - nouveaux membres : adhésions créées dans la période
          (`debut <= date_added < fin`).
        Moyennes et médianes en centimes entiers, arrondies demi-haut.
        / Definitions: cards of the VENTE euro sales (sale and payment cards);
        per-card spending and top-ups;
        medians only over the cards concerned; live local currency balance of the
        card user's wallet (anonymous cards are not read); new members in the period.
        """
        ventes_de_nature_vente = self._ventes_en_euros().filter(
            nature=Vente.Nature.VENTE
        )
        ventes_avec_une_carte = ventes_de_nature_vente.filter(carte__isnull=False)
        reglements_cashless_avec_une_carte = Reglement.objects.filter(
            vente__in=ventes_de_nature_vente,
            moyen__in=MOYENS_CASHLESS,
            carte__isnull=False,
        )

        # Les cartes : celle de la vente, et celle de chaque règlement cashless (un
        # paiement à deux cartes met la seconde sur son règlement, pas sur la vente).
        # Une carte qui est aux deux endroits est comptée une fois.
        # / Cards: the sale's card and each cashless payment's card, counted once.
        cartes_de_la_periode = CarteCashless.objects.filter(
            Q(pk__in=ventes_avec_une_carte.values("carte"))
            | Q(pk__in=reglements_cashless_avec_une_carte.values("carte"))
        )
        nombre_de_cartes = cartes_de_la_periode.count()

        # La dépense est rangée par la carte du RÈGLEMENT.
        # / Spending is grouped by the payment's card.
        depenses_par_carte = (
            reglements_cashless_avec_une_carte.values("carte")
            .annotate(total=Sum("montant"))
            .order_by("carte")
        )
        depenses_des_cartes = []
        total_des_depenses = 0
        for depense_de_la_carte in depenses_par_carte:
            depenses_des_cartes.append(depense_de_la_carte["total"])
            total_des_depenses += depense_de_la_carte["total"]

        recharges_par_carte = (
            self._articles_de_recharge_encaissees()
            .filter(vente__in=ventes_avec_une_carte)
            .values("vente__carte")
            .annotate(total=Sum("total_ttc"))
            .order_by("vente__carte")
        )
        recharges_des_cartes = []
        for recharge_de_la_carte in recharges_par_carte:
            if recharge_de_la_carte["total"] == 0:
                continue
            recharges_des_cartes.append(recharge_de_la_carte["total"])

        # Le reste sur carte : les jetons des monnaies locales créées par CE lieu,
        # sommés par portefeuille (l'utilisateur de la carte : deux cartes d'un même
        # utilisateur partagent un solde), puis la moyenne sur ces soldes. Le lieu est
        # lu par le nom de son schéma : il marche aussi sous `schema_context`.
        # / Remaining balance: the venue's own local currencies, summed per wallet (the
        # card's user: two cards of one user share a balance), then averaged.
        portefeuilles_des_cartes = cartes_de_la_periode.filter(
            user__isnull=False,
            user__wallet__isnull=False,
        ).values("user__wallet")
        soldes_par_carte = (
            Token.objects.filter(
                wallet__in=portefeuilles_des_cartes,
                asset__category=Asset.TLF,
                asset__tenant_origin__schema_name=connection.schema_name,
            )
            .values("wallet")
            .annotate(total=Sum("value"))
            .order_by("wallet")
        )
        soldes_sur_les_cartes = []
        total_des_soldes = 0
        for solde_de_la_carte in soldes_par_carte:
            soldes_sur_les_cartes.append(solde_de_la_carte["total"])
            total_des_soldes += solde_de_la_carte["total"]

        nouveaux_membres = Membership.objects.filter(
            date_added__gte=self.debut,
            date_added__lt=self.fin,
        ).count()

        return {
            "nombre_de_cartes": nombre_de_cartes,
            "total_des_depenses_en_centimes": total_des_depenses,
            "panier_moyen_en_centimes": _moyenne_en_centimes(
                total_des_depenses, len(depenses_des_cartes)
            ),
            "depense_mediane_en_centimes": _mediane_en_centimes(depenses_des_cartes),
            "recharge_mediane_en_centimes": _mediane_en_centimes(recharges_des_cartes),
            "reste_moyen_sur_carte_en_centimes": _moyenne_en_centimes(
                total_des_soldes, len(soldes_sur_les_cartes)
            ),
            "reste_median_sur_carte_en_centimes": _mediane_en_centimes(
                soldes_sur_les_cartes
            ),
            "nouveaux_membres": nouveaux_membres,
        }

    def section_operateurs(self):
        """
        Les opérateurs, pour le rapport X seulement (jamais stocké : l'email y est
        permis). Par opérateur de la vente (clé : uuid de l'utilisateur ;
        « sans_operateur » s'il n'y en a pas) :
        - nombre de ventes : ventes réglées en euros, toutes natures ;
        - chiffre d'affaires TTC : articles du chiffre d'affaires ;
        - argent : règlements d'argent au sens strict, toutes natures (vidages
          compris, comme « argent reçu » en section 5).
        / Operators, X report only: number of sales, revenue, money per sale operator.
        """
        nombres_de_ventes = (
            self._ventes_en_euros()
            .values("operateur")
            .annotate(nombre=Count("pk"))
            .order_by("operateur")
        )
        chiffres_d_affaires = (
            self._articles_du_chiffre_d_affaires()
            .values("vente__operateur")
            .annotate(total=Sum("total_ttc"))
            .order_by("vente__operateur")
        )
        argent_par_operateur = (
            self._reglements_d_argent()
            .values("vente__operateur")
            .annotate(total=Sum("montant"))
            .order_by("vente__operateur")
        )

        # Les emails des opérateurs, lus en une seule requête.
        # / Operators' emails, read in one query.
        emails_des_operateurs = TibilletUser.objects.filter(
            pk__in=self._ventes_en_euros().values("operateur")
        ).values_list("pk", "email")
        emails_par_identifiant = {}
        for identifiant, email in emails_des_operateurs:
            emails_par_identifiant[identifiant] = email

        operateurs = {}
        for nombre_de_l_operateur in nombres_de_ventes:
            identifiant_de_l_operateur = nombre_de_l_operateur["operateur"]
            if identifiant_de_l_operateur is None:
                cle_de_l_operateur = CLE_SANS_OPERATEUR
                nom_de_l_operateur = gettext("Sans opérateur")
            else:
                cle_de_l_operateur = str(identifiant_de_l_operateur)
                nom_de_l_operateur = emails_par_identifiant.get(
                    identifiant_de_l_operateur, ""
                )
            operateurs[cle_de_l_operateur] = {
                "nom": nom_de_l_operateur,
                "nombre_de_ventes": nombre_de_l_operateur["nombre"],
                "chiffre_affaires_ttc_en_centimes": 0,
                "argent_en_centimes": 0,
            }

        for chiffre_de_l_operateur in chiffres_d_affaires:
            identifiant_de_l_operateur = chiffre_de_l_operateur["vente__operateur"]
            if identifiant_de_l_operateur is None:
                cle_de_l_operateur = CLE_SANS_OPERATEUR
            else:
                cle_de_l_operateur = str(identifiant_de_l_operateur)
            operateurs[cle_de_l_operateur]["chiffre_affaires_ttc_en_centimes"] = (
                chiffre_de_l_operateur["total"]
            )

        for argent_de_l_operateur in argent_par_operateur:
            identifiant_de_l_operateur = argent_de_l_operateur["vente__operateur"]
            if identifiant_de_l_operateur is None:
                cle_de_l_operateur = CLE_SANS_OPERATEUR
            else:
                cle_de_l_operateur = str(identifiant_de_l_operateur)
            operateurs[cle_de_l_operateur]["argent_en_centimes"] = (
                argent_de_l_operateur["total"]
            )

        return operateurs

    # ------------------------------------------------------------------
    # Le dictionnaire complet (Z) et le rapport X
    # / The full dictionary (Z) and the X report
    # ------------------------------------------------------------------

    def toutes_les_sections(self):
        """
        Les sections 1 à 11 du Z, dans un dictionnaire sérialisable en JSON (entiers
        et textes), stocké tel quel dans la clôture. Ni l'habitus des cartes ni les
        opérateurs : ils sont au rapport X seulement.
        / Z sections 1 to 11, JSON-serializable; no card habits nor operators.
        """
        return {
            "en_tete": self.section_en_tete(),
            "chiffre_affaires": self.section_chiffre_affaires(),
            "reglements": self.section_reglements(),
            "caisse_especes": self.section_caisse_especes(),
            "reconciliation": self.section_reconciliation(),
            "offerts": self.section_offerts(),
            "annexe": self.section_annexe(),
            "points": self.section_points(),
            "marge_brute": self.section_marge_brute(),
            "detail": self.section_detail(),
            "integrite": self.section_integrite(),
        }

    def rapport_x(self):
        """
        Le rapport X (temps réel, jamais stocké) : les sections du Z, plus l'habitus
        des cartes et les opérateurs. SANS la section 11 (intégrité) : c'est un
        contrôle du Z (la clôture), qui relit chaque vente de la plage (plusieurs
        requêtes par vente) ; trop lourd pour un écran temps réel.
        / The X report (never stored): the Z sections without integrity (a closure
        check, too heavy for a real-time screen), plus card habits and operators.
        """
        return {
            "en_tete": self.section_en_tete(),
            "chiffre_affaires": self.section_chiffre_affaires(),
            "reglements": self.section_reglements(),
            "caisse_especes": self.section_caisse_especes(),
            "reconciliation": self.section_reconciliation(),
            "offerts": self.section_offerts(),
            "annexe": self.section_annexe(),
            "points": self.section_points(),
            "marge_brute": self.section_marge_brute(),
            "detail": self.section_detail(),
            "habitus_cartes": self.section_habitus_cartes(),
            "operateurs": self.section_operateurs(),
        }
