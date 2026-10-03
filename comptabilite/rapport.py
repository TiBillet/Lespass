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
  `hors_chiffre_affaires = False`, natures VENTE et AVOIR. Les articles payés en jetons
  cadeau en font partie (vente ordinaire à TVA 0, D8 bis).
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
from django.db.models import Count, Max, Min, Q, Sum
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


def _libelle_du_moyen(code_du_moyen):
    """Le nom lisible d'un moyen de paiement. / Readable name of a payment method."""
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
        dans les avoirs.
        / Collected top-ups (gross): off-revenue top-up items of VENTE euro sales.
        """
        produit_est_une_recharge = Q(
            pricesold__productsold__product__methode_caisse__in=METHODES_CAISSE_DES_RECHARGES
        ) | Q(
            pricesold__productsold__product__categorie_article__in=TYPES_DE_PRODUIT_DES_RECHARGES
        )
        return self._articles_des_ventes_en_euros().filter(
            produit_est_une_recharge,
            hors_chiffre_affaires=True,
            vente__nature=Vente.Nature.VENTE,
        )

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

    def _chiffre_affaires_par_taux(self, articles_du_chiffre_d_affaires):
        """
        Clé : le taux stocké sur la ligne, en texte (« 20.00 », « 5.50 »).
        / Key: the rate stored on the line, as text.
        """
        sommes_par_taux = (
            articles_du_chiffre_d_affaires.values("vat")
            .annotate(**_sommes_ttc_ht_tva())
            .order_by("vat")
        )
        par_taux = {}
        for sommes_du_taux in sommes_par_taux:
            ligne_du_taux = {
                "total_ttc_en_centimes": 0,
                "total_ht_en_centimes": 0,
                "total_tva_en_centimes": 0,
            }
            _ajouter_les_trois_totaux(ligne_du_taux, sommes_du_taux)
            par_taux[str(sommes_du_taux["vat"])] = ligne_du_taux
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
                "libelle": _libelle_du_moyen(code_du_moyen),
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
                    "libelle": _libelle_du_moyen(code_du_moyen),
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
        - écarts d'encaissement : Σ net de TOUS les articles d'écart (le total de
          l'annexe) ;
        - remboursements : l'argent des avoirs, moins les écarts des avoirs (déjà
          comptés dans « écarts ») ;
        - cartes vidées : l'argent des vidages (négatif) ;
        - ventes payées en argent : l'argent des ventes VENTE et CORRECTION, moins les
          recharges et les écarts hors avoirs.
        Argent reçu = somme des cinq termes, par construction.
        / The terms; money received equals the sum of the five terms by construction.
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

        articles_d_ecart = self._articles_d_ecart_d_encaissement()
        tous_les_ecarts = articles_d_ecart.aggregate(
            total=Coalesce(Sum("total_ttc"), 0)
        )["total"]
        ecarts_des_avoirs = articles_d_ecart.filter(
            vente__nature=Vente.Nature.AVOIR
        ).aggregate(total=Coalesce(Sum("total_ttc"), 0))["total"]
        ecarts_hors_avoirs = tous_les_ecarts - ecarts_des_avoirs

        remboursements = argent_des_avoirs - ecarts_des_avoirs

        # TODO : cette formule suppose que le net d'une recharge payante et d'un écart
        # est entièrement de l'argent : une recharge payante ne se paie jamais en
        # cashless, et un écart n'existe aujourd'hui que sur un paiement Stripe. La
        # fiche H prévoit des écarts sur un paiement QR / NFC (Fedow débite en partie) :
        # leur net ne serait plus de l'argent, la formule sera à revoir.
        # / TODO: assumes top-ups and gaps are paid in money; gaps on QR / NFC payments
        # (sheet H) would break this assumption.
        ventes_payees_en_argent = argent_des_ventes - recharges - ecarts_hors_avoirs

        return {
            "argent_recu_en_centimes": argent_recu,
            "ventes_payees_en_argent_en_centimes": ventes_payees_en_argent,
            "recharges_en_centimes": recharges,
            "remboursements_en_centimes": remboursements,
            "cartes_videes_en_centimes": cartes_videes,
            "ecarts_d_encaissement_en_centimes": tous_les_ecarts,
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
        dépensés n'y sont pas : ce sont des ventes (D8 bis). Détail par produit : clé =
        uuid du produit.
        / The GIFT button, on revenue items only; detail keyed by product uuid.
        """
        articles_offerts = self._articles_du_chiffre_d_affaires().filter(
            source_offert=LigneArticle.SourceOffert.OFFRIR
        )
        totaux = articles_offerts.aggregate(
            quantite=Sum("qty"),
            valeur_catalogue_en_centimes=Coalesce(Sum("part_offerte"), 0),
            cout_achat_en_centimes=Coalesce(Sum("cout_achat"), 0),
        )
        sommes_par_produit = (
            articles_offerts.values(
                "pricesold__productsold__product",
                "pricesold__productsold__product__name",
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
            uuid_du_produit = sommes_du_produit["pricesold__productsold__product"]
            par_produit[str(uuid_du_produit)] = {
                "nom": sommes_du_produit["pricesold__productsold__product__name"],
                "quantite": str(sommes_du_produit["quantite"]),
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
                "libelle": _libelle_du_moyen(code_du_moyen),
                "total_en_centimes": somme_du_moyen["total_en_centimes"],
            }

        # Retours consigne : le nombre est un nombre de gobelets (Σ quantités). Le
        # `int()` porte sur une quantité, jamais sur de l'argent.
        # TODO fiche H : la caisse écrit aujourd'hui le retour avec un prix négatif et
        # une quantité positive ; quand la quantité deviendra négative (D13), prendre
        # l'opposé de la somme.
        # / Deposit returns: a number of cups. TODO sheet H: the quantity sign changes.
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
                "nombre": int(quantite_des_retours),
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
        rien n'est perdu.
        / Top-ups under their sale's money method; otherwise under "plusieurs_moyens".
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
                libelle_du_moyen = _libelle_du_moyen(cle_du_moyen)
            else:
                cle_du_moyen = CLE_PLUSIEURS_MOYENS
                libelle_du_moyen = gettext("Plusieurs moyens")

            if cle_du_moyen not in par_moyen:
                par_moyen[cle_du_moyen] = {
                    "libelle": libelle_du_moyen,
                    "total_en_centimes": 0,
                }
            par_moyen[cle_du_moyen]["total_en_centimes"] += net_des_recharges
        return par_moyen

    def _annexe_ecarts_d_encaissement(self):
        """
        Les écarts d'encaissement (D26) : nombre d'articles et total net, toutes
        natures (un remboursement Stripe peut aussi en écrire un).
        / Collection gaps: number of items and net total, every nature.
        """
        totaux_des_ecarts = self._articles_d_ecart_d_encaissement().aggregate(
            nombre=Count("pk"),
            total_en_centimes=Coalesce(Sum("total_ttc"), 0),
        )
        return {
            "nombre": totaux_des_ecarts["nombre"],
            "total_en_centimes": totaux_des_ecarts["total_en_centimes"],
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
        UNITÉS (Σ des quantités, arrondie demi-haut à l'entier), pas des lignes : un
        article payé en deux parts compte 1, trois planches sur une ligne comptent 3.
        / Gross margin = revenue excl. tax − Σ purchase costs of served items; SOLD items
        (VENTE sales, quantity > 0) with an unknown cost and a non-zero catalogue total
        are counted: never negative.
        """
        articles_servis = self._articles_servis()
        cout_achat = articles_servis.aggregate(
            total=Coalesce(Sum("cout_achat"), 0)
        )["total"]
        # La somme des quantités est un `Decimal` (des parts à 6 décimales) : elle est
        # arrondie à l'unité entière. Ce n'est pas de l'argent.
        # / The sum of quantities is a Decimal: rounded to a whole unit. Not money.
        quantite_au_cout_inconnu = (
            articles_servis.filter(
                vente__nature=Vente.Nature.VENTE,
                qty__gt=0,
                cout_achat__isnull=True,
            )
            .exclude(total_catalogue=0)
            .aggregate(total=Sum("qty"))["total"]
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
        d'affaires.
        / All revenue items by product; the lines add up exactly to the revenue.
        """
        sommes_par_produit = (
            articles_du_chiffre_d_affaires.values(
                "pricesold__productsold__product",
                "pricesold__productsold__product__name",
                "pricesold__productsold__product__categorie_pos",
                "pricesold__productsold__product__categorie_pos__name",
                "pricesold__productsold__product__categorie_article",
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
            uuid_du_produit = sommes_du_produit["pricesold__productsold__product"]
            ventes_par_produit[str(uuid_du_produit)] = {
                "nom": sommes_du_produit["pricesold__productsold__product__name"],
                "categorie": cle_de_la_categorie,
                "quantite": str(sommes_du_produit["quantite"]),
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
