"""
tests/pytest/test_rapport_unique.py
Le rapport des ventes (`comptabilite/rapport.py`, `RapportDesVentes`) : chiffre
d'affaires, règlements, caisse espèces, réconciliation, offerts, annexe, points, marge
brute, détail et intégrité, calculés par des sommes de champs entiers sur les ventes
réglées de la période ; et le rapport X (temps réel), qui y ajoute l'habitus des cartes
et les opérateurs.
/ The sales report: revenue, payments, cash drawer, reconciliation, gifts, appendix,
points, gross margin, detail and integrity, computed by sums of integer fields over the
settled sales of the period; and the X report, which adds card habits and operators.

LOCALISATION : tests/pytest/test_rapport_unique.py

RÈGLES MÉTIER TESTÉES (fiche F §1, §2, §6 ; tronc §2, §4)
- Le rapport ne lit que les ventes `REGLEE` dont l'heure d'encaissement est dans la
  période : `debut <= datetime_encaissement < fin`. La borne de fin est exclue : deux
  périodes qui se suivent ne comptent jamais deux fois la même vente.
- Toute somme en euros ne lit que les ventes en euros (`unite = EUR`). Une vente en
  points ou en temps n'est comptée qu'en section 8, par monnaie.
- Chiffre d'affaires : articles en euros, hors « hors chiffre d'affaires », des natures
  VENTE et AVOIR. Les jetons cadeau (LG) sont une vente ordinaire à TVA 0 (D8 bis).
  Une recharge, un écart d'encaissement, des jetons repris au vidage n'y sont pas.
- Règlements (section 3) : natures VENTE, AVOIR, CORRECTION ; le vidage de carte n'y
  est pas (il est en section 7). Trois blocs : argent (ni FREE ni NM ni cashless),
  cashless (LE, SF, LG, par moyen puis par monnaie), hors argent (offert = règlements
  FREE, recharge cadeau comprise ; points par monnaie).
- Réconciliation : l'argent reçu est tout l'argent entré moins tout l'argent sorti,
  vidages de carte compris ; il vaut la somme des cinq termes signés.
- Les sections sur les recharges et les écarts lisent l'article, jamais `Vente.nature`.
- Le journal d'une vente vient de `journal_pour` ; s'il est impossible, la vente est
  rangée sous « ? » et le rapport ne tombe pas.
- Chaque détail additionne exactement son total (aucune ligne perdue ni écrasée).
- Caisse espèces (le tiroir) : seules comptent les ventes faites sur un point de vente
  (`Vente.point_de_vente` renseigné, vidages compris). Les espèces de l'admin, de
  l'API v2 ou du webhook de LaBoutik V1 restent en section 3, hors du tiroir. Les
  sorties de caisse suivent la même borne que les ventes : `debut <= datetime < fin`.
- Marge brute (D21) : CA HT − Σ coûts d'achat des articles servis (articles du chiffre
  d'affaires et articles des ventes en points ; jamais une recharge, un écart ou des
  jetons repris). Un article au coût inconnu est un article VENDU (vente VENTE,
  quantité > 0 ; jamais un avoir ni un retour de consigne), sans coût d'achat
  (`cout_achat` vide, prix d'achat 0), au total catalogue non nul ; on compte des
  unités (Σ des quantités, arrondie à l'entier) : un article payé en deux parts
  compte 1. Ce nombre n'est jamais négatif.
- Tiroir : les corrections de moyen de paiement sont à part (leur net en espèces), ni
  dans les espèces reçues ni dans les espèces rendues.
- Intégrité : la chaîne des ventes est vérifiée sur la plage de la période seulement ;
  la première vente de la plage est reliée à l'empreinte stockée de la précédente.
- Le Z stocké ne garde jamais d'email : un opérateur y est son identifiant. Le rapport X
  (jamais stocké) ajoute l'habitus des cartes et les opérateurs (avec l'email).
- Une moyenne ou une médiane est un nombre entier de centimes, arrondi demi-haut.
- Le dictionnaire complet se sérialise en JSON sans aide (`json.dumps` sans
  `default=`) : il est stocké tel quel dans la clôture. Ses clés sont des codes ou des
  uuid, jamais un texte traduit.

FORME DU DICTIONNAIRE (le contrat lu par ces tests)
Chaque section est rendue par sa propre méthode ; `toutes_les_sections()` les réunit
sous ces clés. Montants : entiers signés, sommes brutes des champs (un avoir, des
espèces rendues, un remboursement sont négatifs). Taux de TVA : texte du taux stocké
sur la ligne (« 20.00 », « 5.50 », « 0.00 »). Monnaies : uuid en texte.
/ Each section has its own method; toutes_les_sections() gathers them. Amounts are
signed raw sums of integer fields.

    section_en_tete()          → "en_tete"
        lieu, mentions_legales, fuseau_horaire (nom du fuseau du lieu au calcul),
        debut, fin (textes ISO), numero_premiere_vente, numero_derniere_vente,
        nombre_de_ventes, nombre_de_ventes_gratuites (VENTE réglée à total_ttc 0)
    section_chiffre_affaires() → "chiffre_affaires"
        total_ttc_en_centimes, total_ht_en_centimes, total_tva_en_centimes,
        par_taux {taux: {total_ttc_en_centimes, total_ht_en_centimes, total_tva_en_centimes}},
        par_categorie {uuid de la catégorie de caisse, ou "type_<code du type de
                       produit>": {nom, …mêmes totaux…}},
        par_origine {code SaleOrigin: {libelle, …mêmes totaux…}},
        par_journal {code journal: {libelle, …mêmes totaux…}}
    section_reglements()       → "reglements"
        argent {total_en_centimes, par_moyen {code PaymentMethod: {libelle, total_en_centimes}}},
        cashless {total_en_centimes,
                  par_moyen {code: {libelle, total_en_centimes,
                                    par_monnaie {uuid ou "sans_monnaie": {nom, total_en_centimes}}}}},
        hors_argent {offert_en_centimes, points_par_monnaie {uuid: {nom, total_en_centiemes}}}
    section_reconciliation()   → "reconciliation"
        argent_recu_en_centimes, ventes_payees_en_argent_en_centimes,
        recharges_en_centimes, remboursements_en_centimes, cartes_videes_en_centimes,
        ecarts_d_encaissement_en_centimes (des nombres seulement : la phrase est écrite
        par l'affichage)
    section_offerts()          → "offerts"
        valeur_catalogue_en_centimes, cout_achat_en_centimes, quantite (texte),
        par_produit {uuid du produit: {nom, quantite, valeur_catalogue_en_centimes,
                                       cout_achat_en_centimes}}
    section_annexe()           → "annexe"
        avoirs {nombre, total_en_centimes, par_moyen (hors offert),
                retours_consigne {nombre (unités), total_en_centimes},
                remboursements_stripe_a_faire_a_la_main {nombre, total_en_centimes}},
        recharges_et_cartes {recharges_encaissees {total_en_centimes,
                                                   par_moyen {code ou "plusieurs_moyens"}},
                             cadeau_emis_en_centimes,
                             cartes_videes {nombre, especes_rendues_en_centimes,
                                            jetons_cadeau_repris_en_centimes}},
        ecarts_d_encaissement {nombre, total_en_centimes},
        corrections {nombre, liste [{numero, moyen_avant, moyen_apres,
                                     operateur (uuid de l'utilisateur en texte, ou None)}]}
    section_points()           → "points"
        {uuid: {nom, total_en_centiemes, offert_en_centiemes}}
    section_caisse_especes()   → "caisse_especes"
        fond_de_caisse_en_centimes, especes_recues_en_centimes (≥ 0),
        especes_rendues_en_centimes (≤ 0), corrections_en_centimes (net en espèces
        des corrections de moyen), sorties_en_centimes (≥ 0),
        solde_theorique_en_centimes (= fond + reçues + rendues + corrections − sorties)
    section_marge_brute()      → "marge_brute"
        chiffre_affaires_ht_en_centimes, cout_achat_en_centimes, marge_brute_en_centimes,
        nombre_d_articles_au_cout_inconnu
    section_detail()           → "detail"
        billets {uuid de l'événement: {nom, date (texte ISO),
                 par_tarif {uuid du tarif: {produit, nom, quantite (texte),
                                            total_ttc_en_centimes}}}},
        adhesions {uuid du produit: {nom, quantite (texte), total_ttc_en_centimes}},
        ventes_par_produit {uuid du produit: {nom, categorie (clé de par_categorie),
                            quantite (texte), total_ttc_en_centimes, total_ht_en_centimes,
                            offert_en_centimes, cout_achat_en_centimes}}
    section_integrite()        → "integrite"
        statut ("OK" ou "ANOMALIES"), anomalies [{numero, uuid, raison}]

    rapport_x() = toutes_les_sections() sans "integrite" (un contrôle du Z, trop
    lourd pour l'écran temps réel) + deux clés, jamais dans le Z stocké :
        habitus_cartes {nombre_de_cartes, total_des_depenses_en_centimes,
                        panier_moyen_en_centimes, depense_mediane_en_centimes,
                        recharge_mediane_en_centimes, reste_moyen_sur_carte_en_centimes,
                        reste_median_sur_carte_en_centimes, nouveaux_membres}
        operateurs {uuid de l'utilisateur, ou "sans_operateur":
                    {nom (email, ou « Sans opérateur »), nombre_de_ventes,
                     chiffre_affaires_ttc_en_centimes, argent_en_centimes}}

D'OÙ VIENNENT LES VALEURS ATTENDUES
Les valeurs de la fiche F §6 quand elle en donne ; sinon un calcul à la main, écrit en
commentaire au-dessus de l'assertion, avec la seule formule d'argent du projet
(tronc §2) : HT = arrondi_demi_haut(net × 100 / (100 + taux)), TVA = net − HT.
/ The sheet's values when it gives them; otherwise a hand computation written above
the assertion.

SCHÉMA DÉDIÉ
Le rapport lit TOUTES les ventes du lieu sur la période : il faut un lieu qui ne
contient que les ventes du test (`FastTenantTestCase`, tronc §8.5). Chaque test annule
sa transaction à la fin (`FastTenantTestCase` hérite de `TestCase`). Le singleton
`LaboutikConfiguration` est créé en base (tests/PIEGES.md 9.86) : sans lui, la clé de
l'empreinte de la vente échoue.
Les ventes sont écrites PAR LE SERVICE (`BaseBillet/services_vente.py`, directement ou
par `fabriques_vente.py`), jamais par `LigneArticle.objects.create`. Chaque vente
encaissée est vérifiée par `verifier_egalites`.
L'heure d'encaissement n'est jamais modifiée après coup : elle est scellée dans
l'empreinte de la vente (`laboutik/integrity.py`, `calculer_hmac_vente`). Le test de la
borne de fin prend donc la période autour de l'heure réelle d'encaissement.
/ Dedicated schema, rolled back after each test. Sales are written through the sale
service. The settlement time is never changed afterwards (it is fingerprinted).

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-F-rapport-unique.md (§1,
§2, §6), CHANTIER-05-montants-entiers.md (§2, §4).

Lancer / Run : make test ARGS="tests/pytest/test_rapport_unique.py"
"""

import sys

# Le code Django vit dans /DjangoFiles a l'interieur du conteneur.
# / Django code lives in /DjangoFiles inside the container.
sys.path.insert(0, "/DjangoFiles")

import django  # noqa: E402

django.setup()

import json  # noqa: E402
import uuid  # noqa: E402
from datetime import datetime, timedelta  # noqa: E402
from decimal import Decimal  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest.mock import patch  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

from django.db import connection  # noqa: E402
from django.utils import timezone, translation  # noqa: E402
from django_tenants.test.cases import FastTenantTestCase  # noqa: E402

import comptabilite.rapport  # noqa: E402
from AuthBillet.models import TibilletUser, Wallet  # noqa: E402
from BaseBillet.models import (  # noqa: E402
    CategorieProduct,
    Configuration,
    Event,
    LigneArticle,
    Membership,
    Paiement_stripe,
    PaymentMethod,
    PostalAddress,
    PriceSold,
    Product,
    ProductSold,
    Reservation,
    SaleOrigin,
)
from BaseBillet.models_vente import Reglement, Vente  # noqa: E402
from Customers.models import Client  # noqa: E402
from BaseBillet.services_vente import (  # noqa: E402
    NOM_JETONS_CADEAU_REPRIS_AU_VIDAGE,
    ajouter_article,
    ajouter_l_article_d_avoir,
    ajouter_l_article_d_ecart_d_encaissement,
    ajouter_reglement,
    annuler_vente,
    ecrire_la_vente_d_avoir_d_une_ligne,
    encaisser_vente,
    ouvrir_vente,
    tarif_vendu_d_un_produit_systeme,
)
from comptabilite.presentation import sections_pour_affichage  # noqa: E402
from comptabilite.rapport import RapportDesVentes  # noqa: E402
from fabriques_panier import (  # noqa: E402
    ajouter_un_tarif,
    creer_adhesion,
    creer_evenement_avec_tarif,
    creer_une_adhesion_active,
    creer_utilisateur,
    identifiant_unique,
    taches_celery_enregistrees,
)
from fabriques_vente import (  # noqa: E402
    creer_tarif_vendu,
    fabriquer_vente_encaissee,
    verifier_egalites,
)
from fedow_core.models import Asset, Token  # noqa: E402
from laboutik.integrity import verifier_chaine_ventes  # noqa: E402
from laboutik.models import (  # noqa: E402
    LaboutikConfiguration,
    PointDeVente,
    SortieCaisse,
)
from QrcodeCashless.models import CarteCashless  # noqa: E402

# Noms lus tels quels dans le rapport (monnaies).
# / Names read as they are in the report (currencies).
NOM_DE_LA_MONNAIE_LOCALE = "Monnaie locale rapport unique"
NOM_DES_JETONS_CADEAU = "Jetons cadeau rapport unique"
NOM_DES_POINTS = "Points rapport unique"

# Le libellé du journal d'une vente dont le journal est impossible : il renvoie à
# l'écran « Plan complet ? ».
# / The label of the journal of a sale whose journal cannot be found.
LIBELLE_DU_JOURNAL_IMPOSSIBLE = "À corriger : voir « Plan complet ? »"

# Le libellé d'un produit sans catégorie de caisse et sans type de produit.
# / The label of a product without POS category and without product type.
LIBELLE_SANS_CATEGORIE = "Sans catégorie"

# Le nom des ventes sans opérateur, au rapport X.
# / The name of the sales without operator, in the X report.
LIBELLE_SANS_OPERATEUR = "Sans opérateur"

# Ce que le source du rapport ne contient jamais : l'argent n'y est jamais recalculé
# (prix × quantité, arrondi de la base, nombre à virgule).
# / What the report source never contains: money is never recomputed there.
TEXTES_INTERDITS_DANS_LE_RAPPORT = [
    "amount",
    "* qty",
    "*qty",
    "qty *",
    "qty*",
    "Round(",
    "float(",
]


class TestRapportDesVentes(FastTenantTestCase):
    """
    Le rapport des ventes, sections 1 à 11, et le rapport X (fiche F §2).
    / The sales report, sections 1 to 11, and the X report.
    """

    @classmethod
    def get_test_schema_name(cls):
        return "test_rapport_unique"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-rapport-unique.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        """`Client.name` est unique et obligatoire. / Client.name is unique."""
        tenant.name = "Test rapport unique"

    def setUp(self):
        """
        Le lieu de test, son singleton de caisse, la période du rapport, et un jus à
        3,50 € (TVA 20 %) vendu à la caisse.
        / The test venue, its register singleton, the report period, a juice.
        """
        # Le rollback du test précédent a rendu le `search_path` au public.
        # / The previous test's rollback returned the search_path to public.
        connection.set_tenant(self.tenant)

        # Le singleton de la caisse doit exister en base (tests/PIEGES.md 9.86) : il
        # porte la clé de l'empreinte des ventes.
        # / The register singleton must exist in the database (fingerprint key).
        LaboutikConfiguration.get_solo().save()

        # La période du rapport, large des deux côtés : seules les ventes du test sont
        # dans le lieu, l'heure de la machine ne change rien au résultat.
        # / The report period, wide on both sides.
        self.debut_de_la_periode = timezone.now() - timedelta(hours=1)
        self.fin_de_la_periode = timezone.now() + timedelta(hours=1)

        self.tarif_du_jus = creer_tarif_vendu(
            nom="Jus",
            prix_en_euros="3.50",
            taux_tva="20.00",
            methode_caisse=Product.VENTE,
        )

    # ------------------------------------------------------------------
    # Outils du test
    # / Test helpers
    # ------------------------------------------------------------------

    def _rapport(self, debut=None, fin=None):
        """
        Le rapport des ventes de la période (par défaut, celle du test).
        / The sales report of the period (by default, the test's).
        """
        if debut is None:
            debut = self.debut_de_la_periode
        if fin is None:
            fin = self.fin_de_la_periode
        return RapportDesVentes(debut, fin)

    def _monnaie(self, nom, categorie):
        """
        Une monnaie du moteur fedow_core, créée par le lieu de test.
        / A fedow_core currency created by the test venue.
        """
        portefeuille_d_origine = Wallet.objects.create(
            name=f"Portefeuille rapport unique {identifiant_unique()}"
        )
        return Asset.objects.create(
            name=nom,
            currency_code="EUR",
            category=categorie,
            tenant_origin=self.tenant,
            wallet_origin=portefeuille_d_origine,
        )

    def _point_de_vente(self, nom):
        """
        Un point de vente caché (tests/PIEGES.md 9.41), sans code journal : son
        journal est dérivé de son nom (`code_journal_du_point_de_vente`).
        / A hidden point of sale without journal code: its journal comes from its name.
        """
        return PointDeVente.objects.create(name=nom, code_journal="", hidden=True)

    def _vendre_un_jus_en_especes(
        self, point_de_vente=None, quantite="1", operateur=None
    ):
        """
        Une vente de caisse : `quantite` jus à 3,50 € en espèces, compte juste.
        / A register sale: `quantite` juices at 3.50 € in cash.
        """
        montant_en_centimes = 350 * int(quantite)
        vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            point_de_vente=point_de_vente,
            operateur=operateur,
            articles=[
                {
                    "pricesold": self.tarif_du_jus,
                    "quantite": Decimal(quantite),
                    "prix_unitaire": 350,
                    "taux_tva": Decimal("20"),
                },
            ],
            reglements=[
                {"moyen": PaymentMethod.CASH, "montant": montant_en_centimes},
            ],
        )
        verifier_egalites(vente)
        return vente

    def _vente_du_fil_rouge(self, monnaie_locale):
        """
        L'exemple fil rouge (diagnostic du chantier 05) : trois jus à 3,50 €, payés
        5,00 € en monnaie locale sur la carte et 5,50 € en CB. Pendant la transition,
        la caisse coupe l'article en deux « parts », chacune avec son argent réel
        (`total_catalogue_impose`, tronc §5).
        / The running example: three juices, 5.00 € local currency + 5.50 € card,
        written in two "parts" like the register does during the transition.
        """
        vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                {
                    "pricesold": self.tarif_du_jus,
                    "quantite": Decimal("1.428571"),
                    "prix_unitaire": 350,
                    "taux_tva": Decimal("20"),
                    "total_catalogue_impose": 500,
                },
                {
                    "pricesold": self.tarif_du_jus,
                    "quantite": Decimal("1.571429"),
                    "prix_unitaire": 350,
                    "taux_tva": Decimal("20"),
                    "total_catalogue_impose": 550,
                },
            ],
            reglements=[
                {
                    "moyen": PaymentMethod.LOCAL_EURO,
                    "montant": 500,
                    "asset": monnaie_locale.uuid,
                },
                {"moyen": PaymentMethod.CC, "montant": 550},
            ],
        )
        verifier_egalites(vente)
        return vente

    # ------------------------------------------------------------------
    # 1, 2 — Chiffre d'affaires
    # / 1, 2 — Revenue
    # ------------------------------------------------------------------

    def test_ca_trois_jus_nfc_et_cb_1050_875_175(self):
        """
        Fiche F §6, test 1 : l'exemple fil rouge. Trois jus à 3,50 € payés 5,00 € en
        monnaie locale et 5,50 € en CB : chiffre d'affaires 1050 TTC, 875 HT, 175 TVA.
        Les règlements : 500 en cashless (la monnaie locale, par son nom), 550 en
        argent (CB).
        / Running example: revenue 1050 / 875 / 175; 500 cashless, 550 card.
        """
        monnaie_locale = self._monnaie(NOM_DE_LA_MONNAIE_LOCALE, Asset.TLF)
        self._vente_du_fil_rouge(monnaie_locale)

        rapport = self._rapport()
        chiffre_affaires = rapport.section_chiffre_affaires()
        reglements = rapport.section_reglements()

        # Part LE : 500 → HT arrondi(500 × 100 / 120) = arrondi(416,67) = 417, TVA 83.
        # Part CB : 550 → HT arrondi(458,33) = 458, TVA 92.
        # Total : 1050 TTC, 875 HT, 175 TVA.
        # / LE part 500 → 417 + 83; card part 550 → 458 + 92.
        assert chiffre_affaires["total_ttc_en_centimes"] == 1050
        assert chiffre_affaires["total_ht_en_centimes"] == 875
        assert chiffre_affaires["total_tva_en_centimes"] == 175

        assert reglements["argent"]["total_en_centimes"] == 550
        assert reglements["argent"]["par_moyen"]["CC"]["total_en_centimes"] == 550
        assert reglements["cashless"]["total_en_centimes"] == 500
        cashless_en_monnaie_locale = reglements["cashless"]["par_moyen"]["LE"]
        assert cashless_en_monnaie_locale["total_en_centimes"] == 500
        ligne_de_la_monnaie_locale = cashless_en_monnaie_locale["par_monnaie"][
            str(monnaie_locale.uuid)
        ]
        assert ligne_de_la_monnaie_locale["nom"] == NOM_DE_LA_MONNAIE_LOCALE
        assert ligne_de_la_monnaie_locale["total_en_centimes"] == 500

    def test_ca_par_taux_egal_somme_des_lignes(self):
        """
        Fiche F §6, test 2 : le chiffre d'affaires par taux est EXACTEMENT la somme des
        HT et des TVA écrits sur les lignes, jamais un HT recalculé sur le total du
        taux. Les montants sont choisis pour que les deux calculs diffèrent d'un
        centime (TVA calculée par ligne, D6).
        / Revenue per rate is EXACTLY the sum of the line amounts, never recomputed
        on the rate total (amounts chosen so both differ by one cent).
        """
        tarif_a_vingt_pour_cent = creer_tarif_vendu(
            nom="Planche", prix_en_euros="3.33", taux_tva="20.00"
        )
        tarif_a_cinq_cinquante = creer_tarif_vendu(
            nom="Livre", prix_en_euros="1.01", taux_tva="5.50"
        )
        tarif_a_dix_pour_cent = creer_tarif_vendu(
            nom="Repas", prix_en_euros="1.55", taux_tva="10.00"
        )

        def article(tarif_vendu, prix_unitaire, taux_tva):
            return {
                "pricesold": tarif_vendu,
                "quantite": Decimal("1"),
                "prix_unitaire": prix_unitaire,
                "taux_tva": Decimal(taux_tva),
            }

        # Vente A : 333 (20 %) + 101 (5,5 %) + 155 (10 %) = 589 en espèces.
        # / Sale A: 333 + 101 + 155 = 589 in cash.
        vente_a = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                article(tarif_a_vingt_pour_cent, 333, "20"),
                article(tarif_a_cinq_cinquante, 101, "5.5"),
                article(tarif_a_dix_pour_cent, 155, "10"),
            ],
            reglements=[{"moyen": PaymentMethod.CASH, "montant": 589}],
        )
        verifier_egalites(vente_a)

        # Vente B : 333 (20 %) + 101 (5,5 %) = 434 en CB.
        # / Sale B: 333 + 101 = 434 by card.
        vente_b = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                article(tarif_a_vingt_pour_cent, 333, "20"),
                article(tarif_a_cinq_cinquante, 101, "5.5"),
            ],
            reglements=[{"moyen": PaymentMethod.CC, "montant": 434}],
        )
        verifier_egalites(vente_b)

        chiffre_affaires = self._rapport().section_chiffre_affaires()
        par_taux = chiffre_affaires["par_taux"]

        assert set(par_taux.keys()) == {"20.00", "5.50", "10.00"}

        # 20 % : chaque ligne 333 → HT arrondi(277,5) = 278, TVA 55 ; deux lignes :
        # 666 / 556 / 110. (Recalculé sur 666, le HT vaudrait 555.)
        # / 20 %: each line 278 + 55; two lines 666 / 556 / 110 (not 555).
        assert par_taux["20.00"]["total_ttc_en_centimes"] == 666
        assert par_taux["20.00"]["total_ht_en_centimes"] == 556
        assert par_taux["20.00"]["total_tva_en_centimes"] == 110

        # 5,5 % : chaque ligne 101 → HT arrondi(95,73) = 96, TVA 5 ; deux lignes :
        # 202 / 192 / 10. (Recalculé sur 202, le HT vaudrait 191.)
        # / 5.5 %: each line 96 + 5; two lines 202 / 192 / 10 (not 191).
        assert par_taux["5.50"]["total_ttc_en_centimes"] == 202
        assert par_taux["5.50"]["total_ht_en_centimes"] == 192
        assert par_taux["5.50"]["total_tva_en_centimes"] == 10

        # 10 % : une ligne 155 → HT arrondi(140,91) = 141, TVA 14.
        # / 10 %: one line 141 + 14.
        assert par_taux["10.00"]["total_ttc_en_centimes"] == 155
        assert par_taux["10.00"]["total_ht_en_centimes"] == 141
        assert par_taux["10.00"]["total_tva_en_centimes"] == 14

        # Les totaux sont la somme des taux : 1023 / 889 / 134.
        # / Totals are the sum of the rates.
        assert chiffre_affaires["total_ttc_en_centimes"] == 1023
        assert chiffre_affaires["total_ht_en_centimes"] == 889
        assert chiffre_affaires["total_tva_en_centimes"] == 134

    # ------------------------------------------------------------------
    # 3, 4, 5, 6 — Jetons cadeau et recharges
    # / 3, 4, 5, 6 — Gift tokens and top-ups
    # ------------------------------------------------------------------

    def test_jetons_dans_le_ca_tva_0_et_dans_le_cashless(self):
        """
        Fiche F §6, test 3 : une bière à 5,00 €, payée 3,00 € en jetons cadeau et
        2,00 € en CB. Les jetons sont une vente ordinaire (D8 bis) : chiffre
        d'affaires 500, dont 300 à TVA 0 ; argent 200 ; cashless « jetons » 300 ;
        offerts 0 (section 6). Les jetons ne sont jamais de l'argent au sens strict.
        / A 5.00 € beer: 3.00 € in gift tokens + 2.00 € card. Revenue 500 (300 at 0 %
        VAT), money 200, cashless tokens 300, gifts 0.
        """
        jetons_cadeau = self._monnaie(NOM_DES_JETONS_CADEAU, Asset.TNF)
        tarif_de_la_biere = creer_tarif_vendu(
            nom="Biere", prix_en_euros="5.00", taux_tva="20.00"
        )

        # Deux parts, comme la caisse : la part en jetons à TVA 0, la part CB à 20 %.
        # / Two parts, like the register: token part at 0 % VAT, card part at 20 %.
        vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                {
                    "pricesold": tarif_de_la_biere,
                    "quantite": Decimal("0.6"),
                    "prix_unitaire": 500,
                    "taux_tva": Decimal("0"),
                    "total_catalogue_impose": 300,
                },
                {
                    "pricesold": tarif_de_la_biere,
                    "quantite": Decimal("0.4"),
                    "prix_unitaire": 500,
                    "taux_tva": Decimal("20"),
                    "total_catalogue_impose": 200,
                },
            ],
            reglements=[
                {
                    "moyen": PaymentMethod.LOCAL_GIFT,
                    "montant": 300,
                    "asset": jetons_cadeau.uuid,
                },
                {"moyen": PaymentMethod.CC, "montant": 200},
            ],
        )
        verifier_egalites(vente)

        rapport = self._rapport()
        chiffre_affaires = rapport.section_chiffre_affaires()
        reglements = rapport.section_reglements()
        offerts = rapport.section_offerts()

        # Part jetons : 300 à TVA 0 → HT 300, TVA 0. Part CB : 200 à 20 % → HT
        # arrondi(166,67) = 167, TVA 33. Total : 500 / 467 / 33.
        # / Token part 300 / 300 / 0; card part 200 / 167 / 33.
        assert chiffre_affaires["total_ttc_en_centimes"] == 500
        assert chiffre_affaires["total_ht_en_centimes"] == 467
        assert chiffre_affaires["total_tva_en_centimes"] == 33
        assert chiffre_affaires["par_taux"]["0.00"]["total_ttc_en_centimes"] == 300
        assert chiffre_affaires["par_taux"]["0.00"]["total_tva_en_centimes"] == 0
        assert chiffre_affaires["par_taux"]["20.00"]["total_ttc_en_centimes"] == 200

        assert reglements["argent"]["total_en_centimes"] == 200
        assert list(reglements["argent"]["par_moyen"].keys()) == ["CC"]
        assert reglements["cashless"]["total_en_centimes"] == 300
        assert list(reglements["cashless"]["par_moyen"].keys()) == ["LG"]
        ligne_des_jetons = reglements["cashless"]["par_moyen"]["LG"]["par_monnaie"][
            str(jetons_cadeau.uuid)
        ]
        assert ligne_des_jetons["nom"] == NOM_DES_JETONS_CADEAU
        assert ligne_des_jetons["total_en_centimes"] == 300

        assert offerts["valeur_catalogue_en_centimes"] == 0

    def test_recharge_cadeau_puis_jetons_comptes_une_fois(self):
        """
        Fiche F §6, test 4 : une recharge cadeau de 10,00 € (entièrement offerte,
        règlement FREE), puis une bière de 3,00 € payée en jetons cadeau.
        - section 7 : « cadeau émis » 1000 ;
        - section 2 : chiffre d'affaires 300, à TVA 0 ;
        - section 6 (offerts du bouton OFFRIR, articles du chiffre d'affaires) : 0 ;
        - section 3, hors argent, « offert » : 1000 (Σ des règlements FREE, recharge
          cadeau comprise) ;
        - section 7, recharges encaissées : aucune (la recharge cadeau n'encaisse rien).
        Le cadeau n'est pas compté deux fois dans le chiffre d'affaires ni dans les
        offerts.
        / Gift top-up 1000 then a 300 beer in tokens: "gift issued" 1000 (section 7),
        revenue 300 at 0 % VAT, section 6 gifts 0, section 3 "offered" 1000.
        """
        jetons_cadeau = self._monnaie(NOM_DES_JETONS_CADEAU, Asset.TNF)
        tarif_de_la_recharge_cadeau = creer_tarif_vendu(
            nom="Recharge cadeau",
            prix_en_euros="10.00",
            taux_tva="0.00",
            methode_caisse=Product.RECHARGE_CADEAU,
        )
        tarif_de_la_biere = creer_tarif_vendu(
            nom="Biere", prix_en_euros="3.00", taux_tva="20.00"
        )

        # La recharge cadeau : le service pose la part offerte et le règlement FREE.
        # / The gift top-up: the service sets the offered part and the FREE payment.
        vente_de_la_recharge_cadeau = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                {
                    "pricesold": tarif_de_la_recharge_cadeau,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 1000,
                    "taux_tva": Decimal("0"),
                    "offert_en_totalite": True,
                },
            ],
        )
        verifier_egalites(vente_de_la_recharge_cadeau)

        vente_de_la_biere_en_jetons = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                {
                    "pricesold": tarif_de_la_biere,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 300,
                    "taux_tva": Decimal("0"),
                },
            ],
            reglements=[
                {
                    "moyen": PaymentMethod.LOCAL_GIFT,
                    "montant": 300,
                    "asset": jetons_cadeau.uuid,
                },
            ],
        )
        verifier_egalites(vente_de_la_biere_en_jetons)

        rapport = self._rapport()
        annexe = rapport.section_annexe()
        chiffre_affaires = rapport.section_chiffre_affaires()
        offerts = rapport.section_offerts()
        reglements = rapport.section_reglements()

        assert annexe["recharges_et_cartes"]["cadeau_emis_en_centimes"] == 1000
        recharges_encaissees = annexe["recharges_et_cartes"]["recharges_encaissees"]
        assert recharges_encaissees["total_en_centimes"] == 0
        assert recharges_encaissees["par_moyen"] == {}

        assert chiffre_affaires["total_ttc_en_centimes"] == 300
        assert chiffre_affaires["total_tva_en_centimes"] == 0
        assert list(chiffre_affaires["par_taux"].keys()) == ["0.00"]

        assert offerts["valeur_catalogue_en_centimes"] == 0

        assert reglements["hors_argent"]["offert_en_centimes"] == 1000

    def test_recharge_encaissee_hors_ca_puis_consommation_dans_ca(self):
        """
        Fiche F §6, test 5 : une recharge de 20,00 € payée en CB, puis une bière de
        5,00 € payée en monnaie locale. La recharge est une dette (hors chiffre
        d'affaires, D10) : le chiffre d'affaires naît à la consommation. Chiffre
        d'affaires 500, argent 2000.
        / A 20.00 € top-up by card, then a 5.00 € beer in local currency: revenue 500,
        money 2000.
        """
        monnaie_locale = self._monnaie(NOM_DE_LA_MONNAIE_LOCALE, Asset.TLF)
        tarif_de_la_recharge = creer_tarif_vendu(
            nom="Recharge",
            prix_en_euros="20.00",
            taux_tva="0.00",
            methode_caisse=Product.RECHARGE_EUROS,
        )
        tarif_de_la_biere = creer_tarif_vendu(
            nom="Biere", prix_en_euros="5.00", taux_tva="20.00"
        )

        vente_de_la_recharge = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                {
                    "pricesold": tarif_de_la_recharge,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 2000,
                    "taux_tva": Decimal("0"),
                },
            ],
            reglements=[{"moyen": PaymentMethod.CC, "montant": 2000}],
        )
        verifier_egalites(vente_de_la_recharge)

        vente_de_la_biere = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                {
                    "pricesold": tarif_de_la_biere,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 500,
                    "taux_tva": Decimal("20"),
                },
            ],
            reglements=[
                {
                    "moyen": PaymentMethod.LOCAL_EURO,
                    "montant": 500,
                    "asset": monnaie_locale.uuid,
                },
            ],
        )
        verifier_egalites(vente_de_la_biere)

        rapport = self._rapport()
        assert rapport.section_chiffre_affaires()["total_ttc_en_centimes"] == 500
        assert rapport.section_reglements()["argent"]["total_en_centimes"] == 2000

    def test_panier_biere_et_recharge_section_recharges(self):
        """
        Fiche F §6, test 6 : un seul panier, une bière à 5,00 € et une recharge de
        20,00 €, payé 25,00 € en CB. La vente est de nature VENTE : la section des
        recharges lit l'article (hors chiffre d'affaires, recharge), jamais
        `Vente.nature`. La recharge est vue : 2000, en CB ; le chiffre d'affaires ne
        garde que la bière (500).
        / One cart, a beer and a top-up, paid by card. The sale is a VENTE: the top-up
        section reads the item, never Vente.nature. Top-up seen: 2000 by card.
        """
        tarif_de_la_recharge = creer_tarif_vendu(
            nom="Recharge",
            prix_en_euros="20.00",
            taux_tva="0.00",
            methode_caisse=Product.RECHARGE_EUROS,
        )
        tarif_de_la_biere = creer_tarif_vendu(
            nom="Biere", prix_en_euros="5.00", taux_tva="20.00"
        )

        vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                {
                    "pricesold": tarif_de_la_biere,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 500,
                    "taux_tva": Decimal("20"),
                },
                {
                    "pricesold": tarif_de_la_recharge,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 2000,
                    "taux_tva": Decimal("0"),
                },
            ],
            reglements=[{"moyen": PaymentMethod.CC, "montant": 2500}],
        )
        verifier_egalites(vente)
        assert vente.nature == Vente.Nature.VENTE

        rapport = self._rapport()
        recharges_encaissees = rapport.section_annexe()["recharges_et_cartes"][
            "recharges_encaissees"
        ]

        assert recharges_encaissees["total_en_centimes"] == 2000
        assert recharges_encaissees["par_moyen"]["CC"]["total_en_centimes"] == 2000
        assert rapport.section_chiffre_affaires()["total_ttc_en_centimes"] == 500

    # ------------------------------------------------------------------
    # 7, 7b — Avoirs
    # / 7, 7b — Credit notes
    # ------------------------------------------------------------------

    def test_consigne_dans_ca_retour_en_avoir(self):
        """
        Fiche F §6, test 7 (D11) : un gobelet consigné vendu 1,00 € en espèces, puis
        rapporté : vente AVOIR sans vente liée (le gobelet est anonyme), article de
        retour au prix et au taux du gobelet (prix −100, quantité 1, comme la caisse),
        1,00 € rendu en espèces. Chiffre d'affaires 0 ; « retours consigne » 1.
        / A 1.00 € deposit cup sold, then returned (AVOIR, −100, cash −100): revenue 0,
        "deposit returns" 1.
        """
        tarif_du_gobelet = creer_tarif_vendu(
            nom="Gobelet",
            prix_en_euros="1.00",
            taux_tva="20.00",
            methode_caisse=Product.VENTE,
        )
        tarif_du_retour = creer_tarif_vendu(
            nom="Retour gobelet",
            prix_en_euros="-1.00",
            taux_tva="20.00",
            methode_caisse=Product.RETOUR_CONSIGNE,
        )
        produit_de_retour = tarif_du_retour.productsold.product
        produit_de_retour.consigne_remboursee = tarif_du_gobelet.productsold.product
        produit_de_retour.save()

        vente_du_gobelet = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                {
                    "pricesold": tarif_du_gobelet,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 100,
                    "taux_tva": Decimal("20"),
                },
            ],
            reglements=[{"moyen": PaymentMethod.CASH, "montant": 100}],
        )
        verifier_egalites(vente_du_gobelet)

        # Le retour, écrit comme la caisse l'écrit (laboutik/views.py) : prix négatif,
        # quantité positive, taux du gobelet.
        # / The return, written like the register: negative price, positive quantity.
        vente_du_retour = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            nature=Vente.Nature.AVOIR,
            articles=[
                {
                    "pricesold": tarif_du_retour,
                    "quantite": Decimal("1"),
                    "prix_unitaire": -100,
                    "taux_tva": Decimal("20"),
                },
            ],
            reglements=[{"moyen": PaymentMethod.CASH, "montant": -100}],
        )
        verifier_egalites(vente_du_retour)

        rapport = self._rapport()
        chiffre_affaires = rapport.section_chiffre_affaires()
        avoirs = rapport.section_annexe()["avoirs"]

        # Gobelet 100 / HT 83 / TVA 17 ; retour −100 / −83 / −17. Somme : 0.
        # / Cup 100 / 83 / 17; return −100 / −83 / −17. Sum: 0.
        assert chiffre_affaires["total_ttc_en_centimes"] == 0
        assert chiffre_affaires["total_ht_en_centimes"] == 0
        assert chiffre_affaires["total_tva_en_centimes"] == 0

        assert avoirs["nombre"] == 1
        assert avoirs["total_en_centimes"] == -100
        assert avoirs["retours_consigne"]["nombre"] == 1
        assert avoirs["retours_consigne"]["total_en_centimes"] == -100

    def _billet_vendu_en_ligne_par_stripe(self, prix_en_centimes, ecart_en_centimes=0):
        """
        Un billet vendu en ligne et payé par Stripe : la vente, son paiement Stripe
        (moyen SN, relié à la vente) et sa ligne, relue en base. Si Stripe encaisse un
        montant différent du billet, l'écart est écrit par le service
        (`ajouter_l_article_d_ecart_d_encaissement`) et le règlement copie le montant
        Stripe.
        / A ticket sold online and paid by Stripe; a different collected amount writes a
        collection gap item. The line is read back.
        """
        acheteur = creer_utilisateur()
        tarif_du_billet = creer_tarif_vendu(
            nom="Billet",
            prix_en_euros=str(Decimal(prix_en_centimes) / 100),
            taux_tva="5.50",
            categorie_article=Product.BILLET,
        )
        vente_en_ligne = ouvrir_vente(
            origine=SaleOrigin.LESPASS,
            nature=Vente.Nature.VENTE,
            client=acheteur,
        )
        paiement = Paiement_stripe.objects.create(
            user=acheteur,
            status=Paiement_stripe.VALID,
            moyen=PaymentMethod.STRIPE_NOFED,
            payment_intent_id=f"pi_test_{identifiant_unique()}",
            vente=vente_en_ligne,
        )
        ligne = ajouter_article(
            vente_en_ligne,
            pricesold=tarif_du_billet,
            quantite=Decimal("1"),
            prix_unitaire=prix_en_centimes,
            taux_tva=Decimal("5.5"),
            payment_method=PaymentMethod.STRIPE_NOFED,
            paiement_stripe=paiement,
            status=LigneArticle.VALID,
        )
        ajouter_l_article_d_ecart_d_encaissement(vente_en_ligne, ecart_en_centimes)
        ajouter_reglement(
            vente_en_ligne,
            moyen=PaymentMethod.STRIPE_NOFED,
            montant=prix_en_centimes + ecart_en_centimes,
            paiement_stripe=paiement,
        )
        vente_en_ligne = encaisser_vente(vente_en_ligne)
        verifier_egalites(vente_en_ligne)

        # Relue en base : l'objet en mémoire garde sa vente « en attente », et la
        # fonction des avoirs lit `ligne.vente.statut`.
        # / Read back: the in-memory line still holds its pending sale.
        return LigneArticle.objects.get(pk=ligne.pk)

    def _avoir_admin_d_une_ligne_stripe(self, ligne):
        """
        L'avoir fait dans l'admin pour une ligne payée par Stripe, par la fonction du
        bouton « Avoir » : un règlement Stripe négatif, sans référence externe, car
        aucun appel à Stripe n'est fait (D27). Les tâches Celery sont interceptées.
        / The admin credit note of a Stripe line, through the "Credit note" function.
        """
        with taches_celery_enregistrees():
            article_d_avoir = ecrire_la_vente_d_avoir_d_une_ligne(
                ligne,
                quantite=Decimal("1"),
                moyen_rembourse=None,
                origine=SaleOrigin.ADMIN,
            )
        vente_d_avoir = Vente.objects.get(pk=article_d_avoir.vente_id)
        verifier_egalites(vente_d_avoir)
        return vente_d_avoir

    def _avoir_rembourse_par_stripe(
        self, ligne, montant_rembourse_par_stripe, reference_externe
    ):
        """
        L'avoir d'une ligne payée par Stripe, remboursé par Stripe : le règlement
        Stripe négatif porte la référence du remboursement. Si Stripe rend un montant
        différent de l'article, l'écart est écrit par le service
        (`ajouter_l_article_d_ecart_d_encaissement`), comme au remboursement réel.
        / The credit note of a Stripe line refunded by Stripe, with its reference; a
        different refunded amount writes a collection gap item.
        """
        vente_d_avoir = ouvrir_vente(
            origine=SaleOrigin.ADMIN,
            nature=Vente.Nature.AVOIR,
            vente_liee=ligne.vente,
        )
        article_d_avoir = ajouter_l_article_d_avoir(vente_d_avoir, ligne, Decimal("1"))
        ecart_en_centimes = -montant_rembourse_par_stripe - article_d_avoir.total_ttc
        ajouter_l_article_d_ecart_d_encaissement(vente_d_avoir, ecart_en_centimes)
        ajouter_reglement(
            vente_d_avoir,
            moyen=PaymentMethod.STRIPE_NOFED,
            montant=-montant_rembourse_par_stripe,
            reference_externe=reference_externe,
        )
        vente_d_avoir = encaisser_vente(vente_d_avoir)
        verifier_egalites(vente_d_avoir)
        return vente_d_avoir

    def test_remboursements_stripe_a_faire_a_la_main_dans_le_z(self):
        """
        Fiche F §6, test 7b (D27) : l'avoir fait dans l'admin pour un billet payé par
        Stripe (bouton « Avoir », `ecrire_la_vente_d_avoir_d_une_ligne`) écrit un
        règlement Stripe négatif SANS `reference_externe` : aucun appel à Stripe. La
        section 7 le compte « à faire à la main : 1 / 35,00 € ». Un second avoir,
        remboursé par Stripe avec sa référence, n'y est pas. Les deux sont dans les
        avoirs, par moyen : Stripe −5500.
        / An admin credit note on a Stripe line, without refund reference, is counted
        "to do by hand: 1 / 35.00 €"; one refunded by Stripe with a reference is not.
        """
        billet_a_35_euros = self._billet_vendu_en_ligne_par_stripe(3500)
        self._avoir_admin_d_une_ligne_stripe(billet_a_35_euros)
        billet_a_20_euros = self._billet_vendu_en_ligne_par_stripe(2000)
        self._avoir_rembourse_par_stripe(
            billet_a_20_euros,
            montant_rembourse_par_stripe=2000,
            reference_externe="re_test_rapport_unique",
        )

        avoirs = self._rapport().section_annexe()["avoirs"]
        a_faire_a_la_main = avoirs["remboursements_stripe_a_faire_a_la_main"]

        # Somme brute des règlements concernés : −3500 (affichée « 35,00 € »).
        # / Raw sum of the payments concerned: −3500 (shown "35.00 €").
        assert a_faire_a_la_main["nombre"] == 1
        assert a_faire_a_la_main["total_en_centimes"] == -3500

        # Les deux avoirs restent comptés dans les avoirs.
        # / Both credit notes are still counted as credit notes.
        assert avoirs["nombre"] == 2
        assert avoirs["total_en_centimes"] == -5500
        assert set(avoirs["par_moyen"].keys()) == {PaymentMethod.STRIPE_NOFED}
        assert avoirs["par_moyen"]["SN"]["total_en_centimes"] == -5500

    # ------------------------------------------------------------------
    # 8, 8c — Vidage de carte
    # / 8, 8c — Card emptying
    # ------------------------------------------------------------------

    def test_vider_carte_especes_rendues(self):
        """
        Fiche F §6, test 8 (D12) : une carte de 15,00 € en monnaie locale vidée, les
        espèces rendues. La vente VIDAGE_CARTE n'a pas d'article ; ses règlements
        s'annulent (LE +1500, espèces −1500), comme la caisse les écrit. Les espèces
        rendues sont en section 7 ; RIEN en section 3 (règlements).
        / A 15.00 € card emptied, cash given back: shown in section 7, NOTHING in
        section 3.
        """
        monnaie_locale = self._monnaie(NOM_DE_LA_MONNAIE_LOCALE, Asset.TLF)

        vente_du_vidage = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            nature=Vente.Nature.VIDAGE_CARTE,
            reglements=[
                {
                    "moyen": PaymentMethod.LOCAL_EURO,
                    "montant": 1500,
                    "asset": monnaie_locale.uuid,
                },
                {"moyen": PaymentMethod.CASH, "montant": -1500},
            ],
        )
        verifier_egalites(vente_du_vidage)

        rapport = self._rapport()
        cartes_videes = rapport.section_annexe()["recharges_et_cartes"]["cartes_videes"]
        reglements = rapport.section_reglements()

        assert cartes_videes["nombre"] == 1
        assert cartes_videes["especes_rendues_en_centimes"] == -1500

        assert reglements["argent"]["total_en_centimes"] == 0
        assert reglements["argent"]["par_moyen"] == {}
        assert reglements["cashless"]["total_en_centimes"] == 0
        assert reglements["cashless"]["par_moyen"] == {}

    def test_vider_carte_jetons_cadeau_repris(self):
        """
        Fiche F §6, test 8c (D8 bis, D12) : une carte qui n'a que 2,00 € de jetons
        cadeau est vidée. La caisse écrit une vente VIDAGE_CARTE : un règlement
        « jetons » +200 et l'article « Jetons cadeau repris au vidage » de 200 (hors
        chiffre d'affaires, TVA 0), aucun règlement espèces. Section 7 : « jetons
        repris » 200 ; hors chiffre d'affaires ; aucun euro ; rien en section 3.
        / A card with 2.00 € of gift tokens only, emptied: "tokens taken back" 200 in
        section 7, off revenue, no euro, nothing in section 3.
        """
        jetons_cadeau = self._monnaie(NOM_DES_JETONS_CADEAU, Asset.TNF)

        vente_du_vidage = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            nature=Vente.Nature.VIDAGE_CARTE,
            articles=[
                {
                    "pricesold": tarif_vendu_d_un_produit_systeme(
                        NOM_JETONS_CADEAU_REPRIS_AU_VIDAGE
                    ),
                    "quantite": Decimal("1"),
                    "prix_unitaire": 200,
                    "taux_tva": Decimal("0"),
                    "hors_chiffre_affaires": True,
                },
            ],
            reglements=[
                {
                    "moyen": PaymentMethod.LOCAL_GIFT,
                    "montant": 200,
                    "asset": jetons_cadeau.uuid,
                },
            ],
        )
        verifier_egalites(vente_du_vidage)

        rapport = self._rapport()
        cartes_videes = rapport.section_annexe()["recharges_et_cartes"]["cartes_videes"]
        chiffre_affaires = rapport.section_chiffre_affaires()
        reglements = rapport.section_reglements()

        assert cartes_videes["jetons_cadeau_repris_en_centimes"] == 200
        assert cartes_videes["especes_rendues_en_centimes"] == 0

        assert chiffre_affaires["total_ttc_en_centimes"] == 0
        assert chiffre_affaires["par_taux"] == {}

        assert reglements["argent"]["total_en_centimes"] == 0
        assert reglements["argent"]["par_moyen"] == {}
        assert reglements["cashless"]["total_en_centimes"] == 0
        assert reglements["cashless"]["par_moyen"] == {}

    # ------------------------------------------------------------------
    # 9 — Écart d'encaissement
    # / 9 — Collection gap
    # ------------------------------------------------------------------

    def test_ecart_d_encaissement_section_et_reconciliation(self):
        """
        Fiche F §6, test 9 (D26) : un billet de 10,00 €, Stripe encaisse 10,03 €.
        L'écart (+3, « reçu en plus », hors chiffre d'affaires, TVA 0) est écrit par
        le service (`ajouter_l_article_d_ecart_d_encaissement`).
        - section 7 : écarts d'encaissement, nombre 1, total 3 ;
        - section 2 : chiffre d'affaires 1000 (l'écart n'y est pas) ;
        - section 5 : argent reçu 1003 = ventes payées en argent 1000 + recharges 0
          + remboursements 0 + cartes vidées 0 + écarts 3 (termes signés).
        / A 10.00 € ticket, Stripe collects 10.03 €: gap +3 in section 7, revenue 1000,
        reconciliation 1003 = 1000 + 3.
        """
        tarif_du_billet = creer_tarif_vendu(
            nom="Billet",
            prix_en_euros="10.00",
            taux_tva="20.00",
            categorie_article=Product.BILLET,
        )
        vente = ouvrir_vente(origine=SaleOrigin.LESPASS, nature=Vente.Nature.VENTE)
        ajouter_article(
            vente,
            pricesold=tarif_du_billet,
            quantite=Decimal("1"),
            prix_unitaire=1000,
            taux_tva=Decimal("20"),
        )
        ajouter_l_article_d_ecart_d_encaissement(vente, 3)
        ajouter_reglement(vente, moyen=PaymentMethod.STRIPE_NOFED, montant=1003)
        vente = encaisser_vente(vente)
        verifier_egalites(vente)

        rapport = self._rapport()
        ecarts = rapport.section_annexe()["ecarts_d_encaissement"]
        reconciliation = rapport.section_reconciliation()

        assert ecarts["nombre"] == 1
        assert ecarts["total_en_centimes"] == 3

        assert rapport.section_chiffre_affaires()["total_ttc_en_centimes"] == 1000

        assert reconciliation["argent_recu_en_centimes"] == 1003
        assert reconciliation["ventes_payees_en_argent_en_centimes"] == 1000
        assert reconciliation["recharges_en_centimes"] == 0
        assert reconciliation["remboursements_en_centimes"] == 0
        assert reconciliation["cartes_videes_en_centimes"] == 0
        assert reconciliation["ecarts_d_encaissement_en_centimes"] == 3

    # ------------------------------------------------------------------
    # 10 — Origine et journal
    # / 10 — Origin and journal
    # ------------------------------------------------------------------

    def test_ventilation_par_origine_et_par_journal(self):
        """
        Fiche F §6, test 10 : une vente de caisse au point de vente « Bar » (journal
        « BAR », dérivé du nom) et une vente en ligne sans point de vente (journal
        « WEB », table des origines). Deux lignes par origine, deux lignes par journal.
        / A register sale at "Bar" and an online sale: two lines per origin, two per
        journal.
        """
        point_de_vente_du_bar = self._point_de_vente("Bar")
        self._vendre_un_jus_en_especes(point_de_vente=point_de_vente_du_bar)

        tarif_du_billet = creer_tarif_vendu(
            nom="Billet",
            prix_en_euros="20.00",
            taux_tva="5.50",
            categorie_article=Product.BILLET,
        )
        vente_en_ligne = fabriquer_vente_encaissee(
            origine=SaleOrigin.LESPASS,
            articles=[
                {
                    "pricesold": tarif_du_billet,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 2000,
                    "taux_tva": Decimal("5.5"),
                },
            ],
            reglements=[{"moyen": PaymentMethod.STRIPE_NOFED, "montant": 2000}],
        )
        verifier_egalites(vente_en_ligne)

        chiffre_affaires = self._rapport().section_chiffre_affaires()
        par_origine = chiffre_affaires["par_origine"]
        par_journal = chiffre_affaires["par_journal"]

        # Jus 350 à 20 % → HT arrondi(291,67) = 292, TVA 58.
        # Billet 2000 à 5,5 % → HT arrondi(1895,73) = 1896, TVA 104.
        # / Juice 350 → 292 + 58; ticket 2000 → 1896 + 104.
        assert set(par_origine.keys()) == {SaleOrigin.LABOUTIK, SaleOrigin.LESPASS}
        assert par_origine[SaleOrigin.LABOUTIK]["total_ttc_en_centimes"] == 350
        assert par_origine[SaleOrigin.LABOUTIK]["total_ht_en_centimes"] == 292
        assert par_origine[SaleOrigin.LABOUTIK]["total_tva_en_centimes"] == 58
        assert par_origine[SaleOrigin.LESPASS]["total_ttc_en_centimes"] == 2000
        assert par_origine[SaleOrigin.LESPASS]["total_ht_en_centimes"] == 1896
        assert par_origine[SaleOrigin.LESPASS]["total_tva_en_centimes"] == 104

        assert set(par_journal.keys()) == {"BAR", "WEB"}
        assert par_journal["BAR"]["total_ttc_en_centimes"] == 350
        assert par_journal["BAR"]["total_ht_en_centimes"] == 292
        assert par_journal["BAR"]["total_tva_en_centimes"] == 58
        assert par_journal["WEB"]["total_ttc_en_centimes"] == 2000
        assert par_journal["WEB"]["total_ht_en_centimes"] == 1896
        assert par_journal["WEB"]["total_tva_en_centimes"] == 104

    def test_journal_impossible_range_la_vente_sous_point_d_interrogation(self):
        """
        Le point de vente « 123 » n'a pas de code journal et son
        nom n'a aucune lettre : `journal_pour` lève `CompteComptableManquant`. Le
        rapport ne tombe pas : la vente est rangée sous le journal « ? », avec le
        libellé « À corriger : voir « Plan complet ? » ».
        / A point of sale without any letter in its name: the sale goes under "?",
        the report does not crash.
        """
        point_de_vente_sans_lettre = self._point_de_vente("123")
        self._vendre_un_jus_en_especes(point_de_vente=point_de_vente_sans_lettre)

        # Le libellé est traduit au moment du calcul : le rapport est calculé en
        # français, la langue des textes source.
        # / The label is translated at computation time: computed in French.
        with translation.override("fr"):
            par_journal = self._rapport().section_chiffre_affaires()["par_journal"]

        assert set(par_journal.keys()) == {"?"}
        assert par_journal["?"]["libelle"] == LIBELLE_DU_JOURNAL_IMPOSSIBLE
        assert par_journal["?"]["total_ttc_en_centimes"] == 350

    # ------------------------------------------------------------------
    # 12 — Correction de moyen de paiement
    # / 12 — Payment method correction
    # ------------------------------------------------------------------

    def _operateur(self):
        """
        Un utilisateur qui opère la caisse (schéma public, annulé avec le test).
        / A user operating the register (public schema, rolled back with the test).
        """
        email_de_l_operateur = f"operateur-{identifiant_unique()}@tibillet.localhost"
        return TibilletUser.objects.create(
            email=email_de_l_operateur,
            username=email_de_l_operateur,
        )

    def _corriger_les_especes_en_cb(
        self, vente_d_origine, operateur, point_de_vente=None
    ):
        """
        La correction d'un jus payé en espèces : une vente CORRECTION liée, sans
        article, espèces −350 et CB +350 (D14). La caisse l'écrit sur le point de vente
        de la vente d'origine.
        / The correction of a cash juice: a linked CORRECTION sale, cash −350, card +350.
        """
        vente_de_correction = ouvrir_vente(
            origine=SaleOrigin.LABOUTIK,
            nature=Vente.Nature.CORRECTION,
            vente_liee=vente_d_origine,
            operateur=operateur,
            point_de_vente=point_de_vente,
        )
        ajouter_reglement(vente_de_correction, moyen=PaymentMethod.CASH, montant=-350)
        ajouter_reglement(vente_de_correction, moyen=PaymentMethod.CC, montant=350)
        vente_de_correction = encaisser_vente(vente_de_correction)
        verifier_egalites(vente_de_correction)
        return vente_de_correction

    def test_correction_comptee_dans_la_j_de_la_correction(self):
        """
        Fiche F §6, test 12 (D14) : un jus vendu 3,50 € en espèces, puis corrigé en
        CB dans la même période. La correction est une nouvelle vente CORRECTION,
        liée, sans article : espèces −350, CB +350. Dans le rapport : espèces 0, CB 350
        (−espèces +CB), chiffre d'affaires inchangé (350). La vente d'origine n'est pas
        modifiée. La section 7 liste la correction (moyen avant → après, identifiant
        de l'opérateur).
        / A juice sold in cash, then corrected to card: cash 0, card 350, revenue
        unchanged, original sale unchanged; section 7 lists the correction.
        """
        vente_d_origine = self._vendre_un_jus_en_especes()
        operateur = self._operateur()
        vente_de_correction = self._corriger_les_especes_en_cb(
            vente_d_origine, operateur
        )

        rapport = self._rapport()
        reglements = rapport.section_reglements()
        corrections = rapport.section_annexe()["corrections"]

        assert reglements["argent"]["par_moyen"]["CA"]["total_en_centimes"] == 0
        assert reglements["argent"]["par_moyen"]["CC"]["total_en_centimes"] == 350
        assert reglements["argent"]["total_en_centimes"] == 350
        assert rapport.section_chiffre_affaires()["total_ttc_en_centimes"] == 350

        # La vente d'origine garde son règlement espèces.
        # / The original sale keeps its cash payment.
        vente_d_origine_relue = Vente.objects.get(pk=vente_d_origine.pk)
        reglements_relus_en_base = vente_d_origine_relue.reglements.all()
        reglements_de_la_vente_d_origine = []
        for reglement in reglements_relus_en_base:
            reglements_de_la_vente_d_origine.append(
                (reglement.moyen, reglement.montant)
            )
        assert reglements_de_la_vente_d_origine == [(PaymentMethod.CASH, 350)]

        assert corrections["nombre"] == 1
        correction_listee = corrections["liste"][0]
        assert correction_listee["numero"] == vente_de_correction.numero
        assert correction_listee["moyen_avant"] == PaymentMethod.CASH
        assert correction_listee["moyen_apres"] == PaymentMethod.CC
        assert correction_listee["operateur"] == str(operateur.pk)

    # ------------------------------------------------------------------
    # 13 et période — Ce que le rapport lit
    # / 13 and period — What the report reads
    # ------------------------------------------------------------------

    def test_vente_en_attente_hors_rapport(self):
        """
        Fiche F §6, test 13 : une vente réglée (un jus, 350 en espèces), une vente
        EN_ATTENTE (5,00 €, jamais encaissée) et une vente ANNULEE (7,00 €). Seule la
        vente réglée est dans le rapport : chiffre d'affaires 350, espèces 350, une
        vente, plage [son numéro, son numéro].
        / A settled sale, a pending one and a cancelled one: only the settled sale is
        in the report.
        """
        vente_reglee = self._vendre_un_jus_en_especes()

        vente_en_attente = ouvrir_vente(
            origine=SaleOrigin.LABOUTIK, nature=Vente.Nature.VENTE
        )
        ajouter_article(
            vente_en_attente,
            pricesold=self.tarif_du_jus,
            quantite=Decimal("1"),
            prix_unitaire=500,
            taux_tva=Decimal("20"),
        )
        ajouter_reglement(vente_en_attente, moyen=PaymentMethod.CASH, montant=500)

        vente_annulee = ouvrir_vente(
            origine=SaleOrigin.LABOUTIK, nature=Vente.Nature.VENTE
        )
        ajouter_article(
            vente_annulee,
            pricesold=self.tarif_du_jus,
            quantite=Decimal("2"),
            prix_unitaire=350,
            taux_tva=Decimal("20"),
        )
        ajouter_reglement(vente_annulee, moyen=PaymentMethod.CASH, montant=700)
        annuler_vente(vente_annulee)

        rapport = self._rapport()
        en_tete = rapport.section_en_tete()
        reglements = rapport.section_reglements()

        assert rapport.section_chiffre_affaires()["total_ttc_en_centimes"] == 350
        assert reglements["argent"]["par_moyen"]["CA"]["total_en_centimes"] == 350
        assert reglements["argent"]["total_en_centimes"] == 350
        assert en_tete["nombre_de_ventes"] == 1
        assert en_tete["numero_premiere_vente"] == vente_reglee.numero
        assert en_tete["numero_derniere_vente"] == vente_reglee.numero

    def test_vente_encaissee_a_la_borne_de_fin_hors_periode(self):
        """
        Une vente est dans le rapport si
        `debut <= datetime_encaissement < fin`. Une vente encaissée exactement à la
        borne de fin n'est pas dans la période qui finit là ; elle est dans la période
        qui commence là. Deux périodes qui se suivent la comptent une seule fois.
        La période est prise autour de l'heure réelle d'encaissement (jamais modifiée :
        elle est dans l'empreinte de la vente).
        / A sale settled exactly at the end bound is out of the period ending there,
        and in the one starting there.
        """
        vente = self._vendre_un_jus_en_especes()
        heure_d_encaissement = Vente.objects.get(pk=vente.pk).datetime_encaissement

        rapport_qui_finit_a_l_encaissement = self._rapport(
            debut=heure_d_encaissement - timedelta(hours=1),
            fin=heure_d_encaissement,
        )
        rapport_qui_commence_a_l_encaissement = self._rapport(
            debut=heure_d_encaissement,
            fin=heure_d_encaissement + timedelta(hours=1),
        )

        en_tete_avant = rapport_qui_finit_a_l_encaissement.section_en_tete()
        chiffre_affaires_avant = (
            rapport_qui_finit_a_l_encaissement.section_chiffre_affaires()
        )
        assert en_tete_avant["nombre_de_ventes"] == 0
        assert chiffre_affaires_avant["total_ttc_en_centimes"] == 0

        en_tete_apres = rapport_qui_commence_a_l_encaissement.section_en_tete()
        chiffre_affaires_apres = (
            rapport_qui_commence_a_l_encaissement.section_chiffre_affaires()
        )
        assert en_tete_apres["nombre_de_ventes"] == 1
        assert chiffre_affaires_apres["total_ttc_en_centimes"] == 350

    # ------------------------------------------------------------------
    # 8 — Points
    # / 8 — Points
    # ------------------------------------------------------------------

    def _vente_en_points(self, monnaie_de_points, prix_en_centiemes, prix_achat=0):
        """
        Une vente en points (D9) : unité = la monnaie de points, TVA 0, règlement NM.
        Le prix d'achat, lui, est en centimes d'euro (0 = inconnu).
        / A points sale: unit = the points currency, 0 VAT, NM payment. The purchase
        price is in euro cents (0 = unknown).
        """
        tarif_de_la_planche = creer_tarif_vendu(
            nom="Planche en points", prix_en_euros="5.00", taux_tva="0.00"
        )
        vente = ouvrir_vente(
            origine=SaleOrigin.LABOUTIK,
            nature=Vente.Nature.VENTE,
            unite=str(monnaie_de_points.uuid),
        )
        ajouter_article(
            vente,
            pricesold=tarif_de_la_planche,
            quantite=Decimal("1"),
            prix_unitaire=prix_en_centiemes,
            taux_tva=Decimal("0"),
            prix_achat=prix_achat,
        )
        ajouter_reglement(
            vente,
            moyen=PaymentMethod.NON_MONETAIRE,
            montant=prix_en_centiemes,
            asset=monnaie_de_points.uuid,
        )
        vente = encaisser_vente(vente)
        verifier_egalites(vente)
        return vente

    def test_points_par_monnaie_hors_ca_et_hors_argent(self):
        """
        Section 8 (D9) : une planche vendue 500 centièmes de points. Elle n'entre ni
        dans le chiffre d'affaires, ni dans l'argent, ni dans le cashless. Elle est
        comptée en points, par monnaie (section 8, et section 3 « hors argent »).
        / A points sale: neither revenue, nor money, nor cashless; counted in points.
        """
        points = self._monnaie(NOM_DES_POINTS, Asset.FID)
        self._vente_en_points(points, 500)

        rapport = self._rapport()
        chiffre_affaires = rapport.section_chiffre_affaires()
        reglements = rapport.section_reglements()
        section_points = rapport.section_points()

        assert chiffre_affaires["total_ttc_en_centimes"] == 0
        assert chiffre_affaires["par_taux"] == {}
        assert reglements["argent"]["total_en_centimes"] == 0
        assert reglements["cashless"]["total_en_centimes"] == 0

        points_du_bloc_hors_argent = reglements["hors_argent"]["points_par_monnaie"]
        assert points_du_bloc_hors_argent[str(points.uuid)]["total_en_centiemes"] == 500

        assert section_points[str(points.uuid)]["nom"] == NOM_DES_POINTS
        assert section_points[str(points.uuid)]["total_en_centiemes"] == 500

    # ------------------------------------------------------------------
    # Vidage dans l'argent reçu, recharges à plusieurs moyens, ventes gratuites,
    # catégories
    # / Card emptying in money received, multi-method top-ups, free sales, categories
    # ------------------------------------------------------------------

    def test_vidage_compte_dans_l_argent_recu_pas_dans_la_section_3(self):
        """
        L'« argent reçu » de la réconciliation est tout l'argent entré moins tout
        l'argent sorti sur la période, vidages compris (comme le solde de caisse de
        LaBoutik V1). La section 3 reste hors vidage. Une vente de 10,00 € en espèces,
        puis une carte de 1,50 € vidée en espèces :
        - section 3 : argent 1000 ;
        - section 5 : argent reçu 850 = ventes payées en argent 1000 + recharges 0
          + remboursements 0 + cartes vidées (−150) + écarts 0.
        / "Money received" includes card emptying; section 3 does not.
        """
        monnaie_locale = self._monnaie(NOM_DE_LA_MONNAIE_LOCALE, Asset.TLF)
        tarif_du_repas = creer_tarif_vendu(
            nom="Repas", prix_en_euros="10.00", taux_tva="10.00"
        )
        vente_du_repas = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                {
                    "pricesold": tarif_du_repas,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 1000,
                    "taux_tva": Decimal("10"),
                },
            ],
            reglements=[{"moyen": PaymentMethod.CASH, "montant": 1000}],
        )
        verifier_egalites(vente_du_repas)

        vente_du_vidage = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            nature=Vente.Nature.VIDAGE_CARTE,
            reglements=[
                {
                    "moyen": PaymentMethod.LOCAL_EURO,
                    "montant": 150,
                    "asset": monnaie_locale.uuid,
                },
                {"moyen": PaymentMethod.CASH, "montant": -150},
            ],
        )
        verifier_egalites(vente_du_vidage)

        rapport = self._rapport()
        reglements = rapport.section_reglements()
        reconciliation = rapport.section_reconciliation()

        assert reglements["argent"]["total_en_centimes"] == 1000

        assert reconciliation["argent_recu_en_centimes"] == 850
        assert reconciliation["ventes_payees_en_argent_en_centimes"] == 1000
        assert reconciliation["recharges_en_centimes"] == 0
        assert reconciliation["remboursements_en_centimes"] == 0
        assert reconciliation["cartes_videes_en_centimes"] == -150
        assert reconciliation["ecarts_d_encaissement_en_centimes"] == 0

        # La phrase tombe juste : l'argent reçu est la somme des cinq termes signés.
        # / The sentence adds up: money received is the sum of the five signed terms.
        somme_des_termes = (
            reconciliation["ventes_payees_en_argent_en_centimes"]
            + reconciliation["recharges_en_centimes"]
            + reconciliation["remboursements_en_centimes"]
            + reconciliation["cartes_videes_en_centimes"]
            + reconciliation["ecarts_d_encaissement_en_centimes"]
        )
        assert somme_des_termes == reconciliation["argent_recu_en_centimes"]

    def test_recharge_d_une_vente_a_plusieurs_moyens_d_argent_rien_n_est_perdu(self):
        """
        Les recharges encaissées sont rangées sous le moyen d'argent de la vente
        qui les contient. Une vente qui a plusieurs moyens d'argent (inatteignable par
        la caisse aujourd'hui) range ses recharges sous « plusieurs_moyens » : rien
        n'est perdu. Une bière à 5,00 € et une recharge de 20,00 €, payées 15,00 € en
        CB et 10,00 € en espèces : recharges 2000, toutes sous « plusieurs_moyens ».
        / A sale with several money methods: its top-ups go under "plusieurs_moyens".
        """
        tarif_de_la_recharge = creer_tarif_vendu(
            nom="Recharge",
            prix_en_euros="20.00",
            taux_tva="0.00",
            methode_caisse=Product.RECHARGE_EUROS,
        )
        tarif_de_la_biere = creer_tarif_vendu(
            nom="Biere", prix_en_euros="5.00", taux_tva="20.00"
        )
        vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                {
                    "pricesold": tarif_de_la_biere,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 500,
                    "taux_tva": Decimal("20"),
                },
                {
                    "pricesold": tarif_de_la_recharge,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 2000,
                    "taux_tva": Decimal("0"),
                },
            ],
            reglements=[
                {"moyen": PaymentMethod.CC, "montant": 1500},
                {"moyen": PaymentMethod.CASH, "montant": 1000},
            ],
        )
        verifier_egalites(vente)

        rapport = self._rapport()
        recharges_encaissees = rapport.section_annexe()["recharges_et_cartes"][
            "recharges_encaissees"
        ]
        reconciliation = rapport.section_reconciliation()

        assert recharges_encaissees["total_en_centimes"] == 2000
        assert set(recharges_encaissees["par_moyen"].keys()) == {"plusieurs_moyens"}
        assert (
            recharges_encaissees["par_moyen"]["plusieurs_moyens"]["total_en_centimes"]
            == 2000
        )

        # Réconciliation : 2500 reçus = 500 de ventes + 2000 de recharges.
        # / Reconciliation: 2500 received = 500 sales + 2000 top-ups.
        assert reconciliation["argent_recu_en_centimes"] == 2500
        assert reconciliation["ventes_payees_en_argent_en_centimes"] == 500
        assert reconciliation["recharges_en_centimes"] == 2000

    def test_ventes_gratuites_comptees_dans_l_en_tete(self):
        """
        Une vente gratuite est une vente de nature VENTE, réglée, à total_ttc 0 ;
        elle est numérotée comme les autres. Un jus payé, un billet à
        0 € (aucun règlement) et un vidage de carte (nature VIDAGE_CARTE, total 0) :
        trois ventes, dont une gratuite. Le lieu est le nom de l'organisation
        (`Configuration.organisation`).
        / A free sale is a settled VENTE with total_ttc 0: three sales, one free.
        """
        monnaie_locale = self._monnaie(NOM_DE_LA_MONNAIE_LOCALE, Asset.TLF)
        self._vendre_un_jus_en_especes()

        tarif_du_billet_gratuit = creer_tarif_vendu(
            nom="Billet gratuit",
            prix_en_euros="0.00",
            taux_tva="0.00",
            categorie_article=Product.BILLET,
        )
        vente_gratuite = fabriquer_vente_encaissee(
            origine=SaleOrigin.LESPASS,
            articles=[
                {
                    "pricesold": tarif_du_billet_gratuit,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 0,
                    "taux_tva": Decimal("0"),
                },
            ],
        )
        verifier_egalites(vente_gratuite)

        vente_du_vidage = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            nature=Vente.Nature.VIDAGE_CARTE,
            reglements=[
                {
                    "moyen": PaymentMethod.LOCAL_EURO,
                    "montant": 150,
                    "asset": monnaie_locale.uuid,
                },
                {"moyen": PaymentMethod.CASH, "montant": -150},
            ],
        )
        verifier_egalites(vente_du_vidage)

        en_tete = self._rapport().section_en_tete()

        assert en_tete["nombre_de_ventes"] == 3
        assert en_tete["nombre_de_ventes_gratuites"] == 1
        assert en_tete["lieu"] == Configuration.get_solo().organisation

    def test_en_tete_porte_les_mentions_legales_du_lieu(self):
        """
        L'en-tête du rapport porte les mentions légales du lieu, lues dans
        `Configuration` au moment du calcul : organisation, adresse (la rue de
        l'adresse postale), code postal, ville, SIREN / SIRET, numéro de TVA, email,
        téléphone. Elles sont figées dans le Z à la clôture : un ancien Z garde
        l'ancienne adresse. Un champ vide vaut "".
        / The report header carries the venue's legal mentions, read when computed.
        """
        configuration = Configuration.get_solo()
        valeurs_d_origine = {
            "postal_address": configuration.postal_address,
            "postal_code": configuration.postal_code,
            "city": configuration.city,
            "siren": configuration.siren,
            "tva_number": configuration.tva_number,
            "email": configuration.email,
            "phone": configuration.phone,
        }

        # Le cache de la configuration survit à l'annulation du test : les valeurs
        # d'origine y sont remises à la fin.
        # / The configuration cache survives the rollback: original values are put back.
        def remettre_la_configuration_d_origine():
            configuration_a_remettre = Configuration.get_solo()
            for nom_du_champ, valeur in valeurs_d_origine.items():
                setattr(configuration_a_remettre, nom_du_champ, valeur)
            configuration_a_remettre.save()

        self.addCleanup(remettre_la_configuration_d_origine)

        with taches_celery_enregistrees():
            adresse_du_lieu = PostalAddress.objects.create(
                name="Adresse rapport unique",
                street_address="12 rue des Lilas",
                address_locality="Saint-Denis",
                postal_code="97400",
                address_country="FR",
            )
        configuration.postal_address = adresse_du_lieu
        configuration.postal_code = 97400
        configuration.city = "Saint-Denis"
        configuration.siren = "123456789"
        configuration.tva_number = "FR12123456789"
        configuration.email = "contact@lieu-rapport-unique.localhost"
        configuration.phone = "0262000000"
        configuration.save()
        self._vendre_un_jus_en_especes()

        en_tete = self._rapport().toutes_les_sections()["en_tete"]

        assert en_tete["mentions_legales"] == {
            "organisation": Configuration.get_solo().organisation,
            "adresse": "12 rue des Lilas",
            "code_postal": "97400",
            "ville": "Saint-Denis",
            "siren": "123456789",
            "numero_tva": "FR12123456789",
            "email": "contact@lieu-rapport-unique.localhost",
            "telephone": "0262000000",
        }

    def test_en_tete_mentions_legales_vides_sans_adresse(self):
        """
        Un lieu sans adresse postale ni SIREN : les mentions vides valent "" (jamais
        None), le rapport reste sérialisable en JSON.
        / A venue without address nor SIREN: empty mentions are "".
        """
        configuration = Configuration.get_solo()
        valeurs_d_origine = {
            "postal_address": configuration.postal_address,
            "siren": configuration.siren,
        }

        def remettre_la_configuration_d_origine():
            configuration_a_remettre = Configuration.get_solo()
            for nom_du_champ, valeur in valeurs_d_origine.items():
                setattr(configuration_a_remettre, nom_du_champ, valeur)
            configuration_a_remettre.save()

        self.addCleanup(remettre_la_configuration_d_origine)
        configuration.postal_address = None
        configuration.siren = None
        configuration.save()

        mentions_legales = self._rapport().section_en_tete()["mentions_legales"]

        assert mentions_legales["adresse"] == ""
        assert mentions_legales["siren"] == ""
        json.dumps(mentions_legales)

    def test_en_tete_porte_le_fuseau_du_lieu_au_moment_du_calcul(self):
        """
        L'en-tête porte le nom du fuseau du lieu au moment du calcul : un Z garde ce
        fuseau pour afficher ses heures, même si le lieu en change ensuite. Le lieu est
        en Martinique pendant le calcul (configuration en mémoire, jamais enregistrée :
        tests/PIEGES.md 13.5).
        / The header carries the venue's time zone name at computation time.
        """
        configuration_en_martinique = Configuration.get_solo()
        configuration_en_martinique.fuseau_horaire = "America/Martinique"

        with patch.object(
            Configuration, "get_solo", return_value=configuration_en_martinique
        ):
            en_tete = self._rapport().section_en_tete()

        assert en_tete["fuseau_horaire"] == "America/Martinique"
        json.dumps(en_tete)

    def test_chiffre_affaires_par_categorie_avec_et_sans_categorie(self):
        """
        La catégorie d'un article est la catégorie de caisse de son produit
        (`categorie_pos`) : clé = uuid de la catégorie. Sans catégorie de caisse, le
        type du produit la remplace : clé = « type_ » + code du type
        (`categorie_article`), nom = libellé du type. Chaque entrée porte son `nom` ;
        aucune clé n'est un texte traduit. Un jus de la catégorie « Boissons rapport
        unique » (3,50 €, 20 %) et un billet sans catégorie de caisse (20,00 €, 5,5 %) :
        deux lignes.
        / Category key = POS category uuid, otherwise "type_<product type code>";
        each entry carries its name; no translated key.
        """
        categorie_des_boissons = CategorieProduct.objects.create(
            name="Boissons rapport unique"
        )
        produit_du_jus = self.tarif_du_jus.productsold.product
        produit_du_jus.categorie_pos = categorie_des_boissons
        produit_du_jus.save()
        self._vendre_un_jus_en_especes()

        tarif_du_billet = creer_tarif_vendu(
            nom="Billet",
            prix_en_euros="20.00",
            taux_tva="5.50",
            categorie_article=Product.BILLET,
        )
        vente_en_ligne = fabriquer_vente_encaissee(
            origine=SaleOrigin.LESPASS,
            articles=[
                {
                    "pricesold": tarif_du_billet,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 2000,
                    "taux_tva": Decimal("5.5"),
                },
            ],
            reglements=[{"moyen": PaymentMethod.STRIPE_NOFED, "montant": 2000}],
        )
        verifier_egalites(vente_en_ligne)

        # Le nom du type est traduit au moment du calcul : rapport et attente sont
        # calculés dans la même langue.
        # / The type name is translated at computation time, in the same language.
        with translation.override("fr"):
            par_categorie = self._rapport().section_chiffre_affaires()["par_categorie"]
            libelles_des_types = dict(Product.CATEGORIE_ARTICLE_CHOICES)
            nom_du_type_billet = str(libelles_des_types[Product.BILLET])

        cle_des_boissons = str(categorie_des_boissons.uuid)
        cle_du_type_billet = f"type_{Product.BILLET}"

        # Jus 350 → HT 292, TVA 58 ; billet 2000 → HT 1896, TVA 104.
        # / Juice 350 → 292 + 58; ticket 2000 → 1896 + 104.
        assert set(par_categorie.keys()) == {cle_des_boissons, cle_du_type_billet}
        assert par_categorie[cle_des_boissons] == {
            "nom": "Boissons rapport unique",
            "total_ttc_en_centimes": 350,
            "total_ht_en_centimes": 292,
            "total_tva_en_centimes": 58,
        }
        assert par_categorie[cle_du_type_billet] == {
            "nom": nom_du_type_billet,
            "total_ttc_en_centimes": 2000,
            "total_ht_en_centimes": 1896,
            "total_tva_en_centimes": 104,
        }

    # ------------------------------------------------------------------
    # Détails sans perte, euros séparés des points
    # / Lossless details, euros apart from points
    # ------------------------------------------------------------------

    def test_cashless_une_monnaie_reglee_par_deux_moyens_ne_perd_rien(self):
        """
        Le cashless est rangé par moyen, PUIS par monnaie : une même monnaie réglée par
        deux moyens, ou deux règlements sans monnaie de deux moyens, gardent chacun
        leur ligne. Une bière à 10,00 € réglée : monnaie A en LE 300 et en SF 200, LE
        sans monnaie 100, LG sans monnaie 50, espèces 350.
        - LE : 400 (A 300, sans monnaie 100) ;
        - SF : 200 (A 200) ;
        - LG : 50 (sans monnaie 50) ;
        - cashless : 650.
        / Cashless by method, THEN by currency: nothing is overwritten.
        """
        monnaie_a = self._monnaie(NOM_DE_LA_MONNAIE_LOCALE, Asset.TLF)
        tarif_de_la_biere = creer_tarif_vendu(
            nom="Biere", prix_en_euros="10.00", taux_tva="20.00"
        )
        vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                {
                    "pricesold": tarif_de_la_biere,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 1000,
                    "taux_tva": Decimal("20"),
                },
            ],
            reglements=[
                {
                    "moyen": PaymentMethod.LOCAL_EURO,
                    "montant": 300,
                    "asset": monnaie_a.uuid,
                },
                {
                    "moyen": PaymentMethod.STRIPE_FED,
                    "montant": 200,
                    "asset": monnaie_a.uuid,
                },
                {"moyen": PaymentMethod.LOCAL_EURO, "montant": 100},
                {"moyen": PaymentMethod.LOCAL_GIFT, "montant": 50},
                {"moyen": PaymentMethod.CASH, "montant": 350},
            ],
        )
        verifier_egalites(vente)

        cashless = self._rapport().section_reglements()["cashless"]
        cle_de_a = str(monnaie_a.uuid)

        assert cashless["total_en_centimes"] == 650
        assert set(cashless["par_moyen"].keys()) == {"LE", "SF", "LG"}

        monnaie_locale = cashless["par_moyen"]["LE"]
        assert monnaie_locale["total_en_centimes"] == 400
        assert set(monnaie_locale["par_monnaie"].keys()) == {cle_de_a, "sans_monnaie"}
        assert monnaie_locale["par_monnaie"][cle_de_a]["nom"] == NOM_DE_LA_MONNAIE_LOCALE
        assert monnaie_locale["par_monnaie"][cle_de_a]["total_en_centimes"] == 300
        assert monnaie_locale["par_monnaie"]["sans_monnaie"]["total_en_centimes"] == 100

        monnaie_federee = cashless["par_moyen"]["SF"]
        assert monnaie_federee["total_en_centimes"] == 200
        assert set(monnaie_federee["par_monnaie"].keys()) == {cle_de_a}
        assert monnaie_federee["par_monnaie"][cle_de_a]["total_en_centimes"] == 200

        jetons = cashless["par_moyen"]["LG"]
        assert jetons["total_en_centimes"] == 50
        assert set(jetons["par_monnaie"].keys()) == {"sans_monnaie"}
        assert jetons["par_monnaie"]["sans_monnaie"]["total_en_centimes"] == 50

    def _une_biere_encaissee(self, tarif_de_la_biere, prix_unitaire, taux_tva, reglements):
        """
        Une bière vendue à la caisse, réglée par les règlements donnés.
        / A beer sold at the register, settled by the given payments.
        """
        vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                {
                    "pricesold": tarif_de_la_biere,
                    "quantite": Decimal("1"),
                    "prix_unitaire": prix_unitaire,
                    "taux_tva": Decimal(taux_tva),
                },
            ],
            reglements=reglements,
        )
        verifier_egalites(vente)
        return vente

    def test_chaque_detail_additionne_exactement_son_total(self):
        """
        Invariant : dans chaque section, la somme des lignes d'un détail vaut son
        total, au centime. Scénario mêlé : espèces, CB, LE et SF sur la monnaie locale,
        LG sur les jetons cadeau, un article offert, une vente en points, une recharge,
        un avoir en espèces, une correction, un article offert puis annulé par un
        avoir (règlement FREE négatif).
        / Invariant: in every section, the lines of a detail add up to its total.
        """
        monnaie_locale = self._monnaie(NOM_DE_LA_MONNAIE_LOCALE, Asset.TLF)
        jetons_cadeau = self._monnaie(NOM_DES_JETONS_CADEAU, Asset.TNF)
        points = self._monnaie(NOM_DES_POINTS, Asset.FID)
        tarif_de_la_biere = creer_tarif_vendu(
            nom="Biere", prix_en_euros="4.00", taux_tva="20.00"
        )
        tarif_de_la_recharge = creer_tarif_vendu(
            nom="Recharge",
            prix_en_euros="10.00",
            taux_tva="0.00",
            methode_caisse=Product.RECHARGE_EUROS,
        )

        # Fil rouge (LE 500 + CB 550), une bière en SF, une bière en jetons.
        # / Running example, a beer in SF, a beer in gift tokens.
        self._vente_du_fil_rouge(monnaie_locale)
        self._une_biere_encaissee(
            tarif_de_la_biere,
            400,
            "20",
            [
                {
                    "moyen": PaymentMethod.STRIPE_FED,
                    "montant": 400,
                    "asset": monnaie_locale.uuid,
                },
            ],
        )
        self._une_biere_encaissee(
            tarif_de_la_biere,
            300,
            "0",
            [
                {
                    "moyen": PaymentMethod.LOCAL_GIFT,
                    "montant": 300,
                    "asset": jetons_cadeau.uuid,
                },
            ],
        )

        # Un jus offert (bouton OFFRIR), une vente en points, une recharge en CB.
        # / A gifted juice, a points sale, a card top-up.
        vente_offerte = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                {
                    "pricesold": self.tarif_du_jus,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 350,
                    "taux_tva": Decimal("20"),
                    "prix_achat": 120,
                    "offert_en_totalite": True,
                },
            ],
        )
        verifier_egalites(vente_offerte)
        self._vente_en_points(points, 500)
        vente_de_la_recharge = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                {
                    "pricesold": tarif_de_la_recharge,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 1000,
                    "taux_tva": Decimal("0"),
                },
            ],
            reglements=[{"moyen": PaymentMethod.CC, "montant": 1000}],
        )
        verifier_egalites(vente_de_la_recharge)

        # Un jus vendu puis remboursé en espèces par l'admin ; un jus corrigé en CB.
        # / A juice refunded in cash by the admin; a juice corrected to card.
        ligne_du_jus_rembourse = self._ligne_d_un_jus_vendu_en_especes(prix=350)
        with taches_celery_enregistrees():
            ecrire_la_vente_d_avoir_d_une_ligne(
                ligne_du_jus_rembourse,
                quantite=Decimal("1"),
                moyen_rembourse=PaymentMethod.CASH,
                origine=SaleOrigin.ADMIN,
            )
        jus_corrige = self._vendre_un_jus_en_especes()
        self._corriger_les_especes_en_cb(jus_corrige, self._operateur())

        # Un sirop offert (2,00 €), puis annulé par un avoir : l'avoir n'écrit qu'un
        # règlement FREE négatif, qui n'est pas de l'argent rendu.
        # / A gifted syrup, then cancelled: its credit note only writes a negative FREE
        # payment, which is not money given back.
        vente_du_sirop_offert = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                {
                    "pricesold": self.tarif_du_jus,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 200,
                    "taux_tva": Decimal("20"),
                    "offert_en_totalite": True,
                    "status": LigneArticle.VALID,
                },
            ],
        )
        verifier_egalites(vente_du_sirop_offert)
        with taches_celery_enregistrees():
            ecrire_la_vente_d_avoir_d_une_ligne(
                LigneArticle.objects.get(vente=vente_du_sirop_offert),
                quantite=Decimal("1"),
                moyen_rembourse=None,
                origine=SaleOrigin.ADMIN,
            )

        sections = self._rapport().toutes_les_sections()

        # Section 2 : chaque ventilation additionne les trois totaux.
        # / Section 2: every breakdown adds up to the three totals.
        chiffre_affaires = sections["chiffre_affaires"]
        noms_des_ventilations = ["par_taux", "par_categorie", "par_origine", "par_journal"]
        noms_des_totaux = [
            "total_ttc_en_centimes",
            "total_ht_en_centimes",
            "total_tva_en_centimes",
        ]
        for nom_de_la_ventilation in noms_des_ventilations:
            for nom_du_total in noms_des_totaux:
                somme_des_lignes = 0
                for ligne in chiffre_affaires[nom_de_la_ventilation].values():
                    somme_des_lignes += ligne[nom_du_total]
                assert somme_des_lignes == chiffre_affaires[nom_du_total], (
                    nom_de_la_ventilation,
                    nom_du_total,
                )

        # Section 3 : argent par moyen ; cashless par moyen, puis par monnaie.
        # / Section 3: money by method; cashless by method, then by currency.
        argent = sections["reglements"]["argent"]
        somme_de_l_argent = 0
        for ligne_du_moyen in argent["par_moyen"].values():
            somme_de_l_argent += ligne_du_moyen["total_en_centimes"]
        assert somme_de_l_argent == argent["total_en_centimes"]

        cashless = sections["reglements"]["cashless"]
        assert set(cashless["par_moyen"].keys()) == {"LE", "SF", "LG"}
        somme_du_cashless = 0
        for code_du_moyen, ligne_du_moyen in cashless["par_moyen"].items():
            somme_des_monnaies_du_moyen = 0
            for ligne_de_la_monnaie in ligne_du_moyen["par_monnaie"].values():
                somme_des_monnaies_du_moyen += ligne_de_la_monnaie["total_en_centimes"]
            assert somme_des_monnaies_du_moyen == ligne_du_moyen["total_en_centimes"], (
                code_du_moyen
            )
            somme_du_cashless += ligne_du_moyen["total_en_centimes"]
        assert somme_du_cashless == cashless["total_en_centimes"]

        # Section 3, hors argent : l'offert ; les points égaux à la section 8.
        # / Section 3, non-money: offered; points equal to section 8.
        hors_argent = sections["reglements"]["hors_argent"]
        assert hors_argent["offert_en_centimes"] == 350
        cle_des_points = str(points.uuid)
        assert set(hors_argent["points_par_monnaie"].keys()) == {cle_des_points}
        points_de_la_section_3 = hors_argent["points_par_monnaie"][cle_des_points]
        points_de_la_section_8 = sections["points"][cle_des_points]
        assert (
            points_de_la_section_3["total_en_centiemes"]
            == points_de_la_section_8["total_en_centiemes"]
            == 500
        )

        # Section 6 : les produits offerts additionnent la valeur et le coût.
        # / Section 6: gifted products add up to value and cost.
        offerts = sections["offerts"]
        somme_des_valeurs = 0
        somme_des_couts = 0
        for ligne_du_produit in offerts["par_produit"].values():
            somme_des_valeurs += ligne_du_produit["valeur_catalogue_en_centimes"]
            somme_des_couts += ligne_du_produit["cout_achat_en_centimes"]
        assert somme_des_valeurs == offerts["valeur_catalogue_en_centimes"] == 350
        assert somme_des_couts == offerts["cout_achat_en_centimes"] == 120

        # Section 7 : avoirs et recharges par moyen ; corrections listées.
        # / Section 7: credit notes and top-ups by method; corrections listed.
        annexe = sections["annexe"]
        somme_des_avoirs = 0
        for ligne_du_moyen in annexe["avoirs"]["par_moyen"].values():
            somme_des_avoirs += ligne_du_moyen["total_en_centimes"]
        assert somme_des_avoirs == annexe["avoirs"]["total_en_centimes"] == -350

        recharges_encaissees = annexe["recharges_et_cartes"]["recharges_encaissees"]
        somme_des_recharges = 0
        for ligne_du_moyen in recharges_encaissees["par_moyen"].values():
            somme_des_recharges += ligne_du_moyen["total_en_centimes"]
        assert somme_des_recharges == recharges_encaissees["total_en_centimes"] == 1000

        corrections = annexe["corrections"]
        assert corrections["nombre"] == len(corrections["liste"]) == 1

    def test_recharge_offerte_en_points_comptee_en_section_8_seulement(self):
        """
        Toute somme en euros ne lit que les ventes en euros. Une recharge offerte en
        points (écrite comme l'API v2 l'écrit : vente à l'unité de la monnaie de
        points, article de recharge entièrement offert, règlement FREE) n'entre ni dans
        le « cadeau émis », ni dans les recharges encaissées, ni dans l'offert de la
        section 3. Elle est en section 8, par monnaie : offert 500 centièmes de points,
        total net 0.
        / A top-up offered in points is counted in section 8 only.
        """
        points = self._monnaie(NOM_DES_POINTS, Asset.FID)
        tarif_de_la_recharge_en_points = creer_tarif_vendu(
            nom="Recharge points",
            prix_en_euros="0.00",
            taux_tva="0.00",
            categorie_article=Product.RECHARGE_CASHLESS,
        )
        vente = ouvrir_vente(
            origine=SaleOrigin.LESPASS,
            nature=Vente.Nature.VENTE,
            unite=str(points.uuid),
        )
        ajouter_article(
            vente,
            pricesold=tarif_de_la_recharge_en_points,
            quantite=Decimal("1"),
            prix_unitaire=500,
            taux_tva=Decimal("0"),
            offert_en_totalite=True,
        )
        vente = encaisser_vente(vente)
        verifier_egalites(vente)

        rapport = self._rapport()
        recharges_et_cartes = rapport.section_annexe()["recharges_et_cartes"]
        hors_argent = rapport.section_reglements()["hors_argent"]
        section_points = rapport.section_points()

        assert recharges_et_cartes["cadeau_emis_en_centimes"] == 0
        assert recharges_et_cartes["recharges_encaissees"]["total_en_centimes"] == 0
        assert hors_argent["offert_en_centimes"] == 0

        assert section_points == {
            str(points.uuid): {
                "nom": NOM_DES_POINTS,
                "total_en_centiemes": 0,
                "offert_en_centiemes": 500,
            },
        }

    def test_bouton_offrir_quantite_valeur_catalogue_et_cout(self):
        """
        Section 6, le bouton OFFRIR : deux jus offerts (3,50 € l'un, prix d'achat
        1,20 €). Quantité « 2.000000 » (texte), valeur catalogue 700, coût d'achat
        240 (2 × 120), et le détail par produit (clé = uuid du produit). Un jus vendu
        et une recharge cadeau n'y sont pas.
        / The GIFT button: two juices gifted, quantity, catalogue value, cost, by product.
        """
        tarif_de_la_recharge_cadeau = creer_tarif_vendu(
            nom="Recharge cadeau",
            prix_en_euros="10.00",
            taux_tva="0.00",
            methode_caisse=Product.RECHARGE_CADEAU,
        )
        vente_offerte = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                {
                    "pricesold": self.tarif_du_jus,
                    "quantite": Decimal("2"),
                    "prix_unitaire": 350,
                    "taux_tva": Decimal("20"),
                    "prix_achat": 120,
                    "offert_en_totalite": True,
                },
            ],
        )
        verifier_egalites(vente_offerte)
        self._vendre_un_jus_en_especes()
        vente_de_la_recharge_cadeau = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                {
                    "pricesold": tarif_de_la_recharge_cadeau,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 1000,
                    "taux_tva": Decimal("0"),
                    "offert_en_totalite": True,
                },
            ],
        )
        verifier_egalites(vente_de_la_recharge_cadeau)

        offerts = self._rapport().section_offerts()
        produit_du_jus = self.tarif_du_jus.productsold.product

        assert offerts == {
            "quantite": "2.000000",
            "valeur_catalogue_en_centimes": 700,
            "cout_achat_en_centimes": 240,
            "par_produit": {
                str(produit_du_jus.uuid): {
                    "nom": produit_du_jus.name,
                    "quantite": "2.000000",
                    "valeur_catalogue_en_centimes": 700,
                    "cout_achat_en_centimes": 240,
                },
            },
        }

    # ------------------------------------------------------------------
    # Réconciliation complète
    # / Full reconciliation
    # ------------------------------------------------------------------

    def _ligne_d_un_jus_vendu_en_especes(self, prix):
        """
        Une vente de caisse d'un jus en espèces, dont la ligne est VALID (comme la
        caisse l'écrit), relue en base pour la fonction des avoirs.
        / A register juice sale whose line is VALID, read back for the credit notes.
        """
        vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                {
                    "pricesold": self.tarif_du_jus,
                    "quantite": Decimal("1"),
                    "prix_unitaire": prix,
                    "taux_tva": Decimal("20"),
                    "status": LigneArticle.VALID,
                },
            ],
            reglements=[{"moyen": PaymentMethod.CASH, "montant": prix}],
        )
        verifier_egalites(vente)
        return LigneArticle.objects.get(vente=vente)

    def test_chiffre_affaires_par_moyen_decor_mele_somme_egale_au_ca(self):
        """
        Le chiffre d'affaires par moyen (section 2, `par_moyen`) sur un décor mêlé :
        - un jus à 10,00 € en espèces, puis remboursé en espèces (avoir) : espèces
          +1000 −1000, CA +1000 −1000 ;
        - un jus à 3,50 € en espèces, corrigé en CB : espèces +350 −350, CB +350 ;
        - une recharge de 20,00 € en espèces : espèces +2000, part hors CA −2000 ;
        - une bière à 5,00 € en monnaie locale : monnaie locale +500 ;
        - une bière à 5,00 € en CB : CB +500 ;
        - un billet à 20,00 € payé par Stripe, qui encaisse 20,03 € : Stripe +2003,
          écart hors CA −3.
        Calcul à la main : espèces 1000 − 1000 + 350 − 350 + 2000 − 2000 = 0 ; CB
        350 + 500 = 850 ; monnaie locale 500 ; Stripe 2003 − 3 = 2000. Chiffre
        d'affaires : 1000 − 1000 + 350 + 500 + 500 + 2000 = 3350 = 0 + 850 + 500 +
        2000. L'affichage ne met pas le tableau par moyen en alerte.
        / Revenue by method on a mixed setting: cash 0, card 850, local 500, Stripe
        2000; their sum equals the revenue 3350; no display alert.
        """
        monnaie_locale = self._monnaie(NOM_DE_LA_MONNAIE_LOCALE, Asset.TLF)
        tarif_de_la_recharge = creer_tarif_vendu(
            nom="Recharge", prix_en_euros="20.00", taux_tva="0.00",
            methode_caisse=Product.RECHARGE_EUROS,
        )
        tarif_de_la_biere = creer_tarif_vendu(
            nom="Biere", prix_en_euros="5.00", taux_tva="20.00",
        )

        # Le jus à 10,00 € puis son avoir en espèces.
        # / The 10.00 € juice, then its cash credit note.
        ligne_du_jus = self._ligne_d_un_jus_vendu_en_especes(prix=1000)
        with taches_celery_enregistrees():
            ecrire_la_vente_d_avoir_d_une_ligne(
                ligne_du_jus,
                quantite=Decimal("1"),
                moyen_rembourse=PaymentMethod.CASH,
                origine=SaleOrigin.ADMIN,
            )
        # Le jus à 3,50 € en espèces, corrigé en CB.
        # / The 3.50 € cash juice, corrected into card.
        vente_a_corriger = self._vendre_un_jus_en_especes()
        self._corriger_les_especes_en_cb(vente_a_corriger, self._operateur())
        # La recharge en espèces, la bière en monnaie locale, la bière en CB.
        # / The cash top-up, the local currency beer, the card beer.
        verifier_egalites(fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[{
                "pricesold": tarif_de_la_recharge, "quantite": Decimal("1"),
                "prix_unitaire": 2000, "taux_tva": Decimal("0"),
            }],
            reglements=[{"moyen": PaymentMethod.CASH, "montant": 2000}],
        ))
        verifier_egalites(fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[{
                "pricesold": tarif_de_la_biere, "quantite": Decimal("1"),
                "prix_unitaire": 500, "taux_tva": Decimal("20"),
            }],
            reglements=[{
                "moyen": PaymentMethod.LOCAL_EURO, "montant": 500,
                "asset": monnaie_locale.uuid,
            }],
        ))
        verifier_egalites(fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[{
                "pricesold": tarif_de_la_biere, "quantite": Decimal("1"),
                "prix_unitaire": 500, "taux_tva": Decimal("20"),
            }],
            reglements=[{"moyen": PaymentMethod.CC, "montant": 500}],
        ))
        # Le billet Stripe avec un écart de +3.
        # / The Stripe ticket with a +3 gap.
        self._billet_vendu_en_ligne_par_stripe(2000, ecart_en_centimes=3)

        chiffre_affaires = self._rapport().section_chiffre_affaires()

        totaux_par_moyen = {}
        somme_des_moyens = 0
        for code_du_moyen, ligne_du_moyen in chiffre_affaires["par_moyen"].items():
            totaux_par_moyen[code_du_moyen] = ligne_du_moyen["total_en_centimes"]
            somme_des_moyens += ligne_du_moyen["total_en_centimes"]
        assert totaux_par_moyen == {
            PaymentMethod.CASH: 0,
            PaymentMethod.CC: 850,
            PaymentMethod.LOCAL_EURO: 500,
            PaymentMethod.STRIPE_NOFED: 2000,
        }
        assert chiffre_affaires["total_ttc_en_centimes"] == 3350
        assert somme_des_moyens == chiffre_affaires["total_ttc_en_centimes"]

        with translation.override("fr"):
            sections = sections_pour_affichage({"chiffre_affaires": chiffre_affaires})
        tableau_par_moyen = None
        for tableau in sections[0]["tableaux"]:
            if tableau["testid"] == "chiffre-affaires-par-moyen":
                tableau_par_moyen = tableau
        assert tableau_par_moyen is not None
        assert tableau_par_moyen["alerte"] is False

    def test_chiffre_affaires_par_moyen_qui_ne_recompose_pas_le_ca_est_en_alerte(self):
        """
        Un rapport dont les lignes par moyen (900) ne recomposent pas le chiffre
        d'affaires (1000) : le tableau « Par moyen de paiement » est en alerte, avec
        l'écart écrit en mots (−1,00 €).
        / Lines by method that do not add up to the revenue: the table is in alert,
        with the gap in words.
        """
        chiffre_affaires_incoherent = {
            "total_ttc_en_centimes": 1000,
            "total_ht_en_centimes": 833,
            "total_tva_en_centimes": 167,
            "par_moyen": {
                PaymentMethod.CASH: {"libelle": "Espèces", "total_en_centimes": 900},
            },
            "par_taux": {},
            "par_categorie": {},
            "par_origine": {},
            "par_journal": {},
        }

        with translation.override("fr"):
            sections = sections_pour_affichage(
                {"chiffre_affaires": chiffre_affaires_incoherent}
            )

        tableau_par_moyen = None
        for tableau in sections[0]["tableaux"]:
            if tableau["testid"] == "chiffre-affaires-par-moyen":
                tableau_par_moyen = tableau
        assert tableau_par_moyen is not None
        assert tableau_par_moyen["alerte"] is True
        assert "ne recomposent pas" in tableau_par_moyen["message_d_alerte"]
        # L'écart est signé : 900 − 1000 = −100, écrit « −1,00 € » (signe moins
        # typographique, espace insécable).
        # / The gap is signed: −100, written with the typographic minus.
        ecart_attendu = f"écart de {chr(0x2212)}1,00{chr(0xA0)}€"
        assert ecart_attendu in tableau_par_moyen["message_d_alerte"], (
            tableau_par_moyen["message_d_alerte"]
        )

        # La fiche de la clôture dans l'admin écrit l'alerte en mots, pas seulement
        # en rouge (une couleur seule ne se lit pas avec un lecteur d'écran).
        # / The admin closure page writes the alert in words, not only in red.
        from django.template.loader import render_to_string

        with translation.override("fr"):
            contenu_de_la_section = render_to_string(
                "comptabilite/admin/_contenu_section_rapport.html",
                {"section": sections[0]},
            )
        assert 'data-testid="comptabilite-alerte-chiffre-affaires-par-moyen"' in (
            contenu_de_la_section
        )
        assert "ne recomposent pas" in contenu_de_la_section

    # ------------------------------------------------------------------
    # Σ du chiffre d'affaires par moyen = chiffre d'affaires TTC, cas par cas
    # / Revenue by method adds up to the revenue, case by case
    # ------------------------------------------------------------------

    def _totaux_par_moyen(self, par_moyen):
        """
        Un dictionnaire « par moyen » du rapport, réduit à {code: montant}.
        / A "by method" report dict, reduced to {code: amount}.
        """
        totaux = {}
        moyens_et_lignes = par_moyen.items()
        for code_du_moyen, ligne_du_moyen in moyens_et_lignes:
            totaux[code_du_moyen] = ligne_du_moyen["total_en_centimes"]
        return totaux

    def _totaux_non_nuls_par_moyen(self, par_moyen):
        """
        Les lignes non nulles d'un dictionnaire « par moyen », en {code: montant} (un
        moyen corrigé peut rester à 0).
        / The non-zero lines of a "by method" dict (a corrected method may stay at 0).
        """
        totaux = {}
        moyens_et_lignes = par_moyen.items()
        for code_du_moyen, ligne_du_moyen in moyens_et_lignes:
            if ligne_du_moyen["total_en_centimes"] != 0:
                totaux[code_du_moyen] = ligne_du_moyen["total_en_centimes"]
        return totaux

    def _verifier_somme_egale_au_chiffre_d_affaires(self, chiffre_affaires):
        """
        L'invariant : Σ des lignes par moyen = chiffre d'affaires TTC.
        / The invariant: the lines by method add up to the revenue.
        """
        somme_des_moyens = 0
        lignes_par_moyen = chiffre_affaires["par_moyen"].values()
        for ligne_du_moyen in lignes_par_moyen:
            somme_des_moyens += ligne_du_moyen["total_en_centimes"]
        assert somme_des_moyens == chiffre_affaires["total_ttc_en_centimes"]

    def _tarif_de_recharge(self, prix_en_euros):
        """Une recharge en euros de caisse (hors chiffre d'affaires, TVA 0).
        / A register euro top-up (off revenue, 0 % VAT)."""
        return creer_tarif_vendu(
            nom="Recharge",
            prix_en_euros=prix_en_euros,
            taux_tva="0.00",
            methode_caisse=Product.RECHARGE_EUROS,
        )

    def _corriger_le_moyen(self, vente_d_origine, moyen_ancien, moyen_nouveau, montant):
        """
        La correction du moyen de paiement d'une vente, comme la caisse l'écrit
        (`corriger_moyen_paiement`) : une vente CORRECTION liée, sans article, ancien
        moyen −montant, nouveau moyen +montant.
        / A payment method correction, as the register writes it.
        """
        correction = ouvrir_vente(
            origine=SaleOrigin.LABOUTIK,
            nature=Vente.Nature.CORRECTION,
            vente_liee=vente_d_origine,
        )
        ajouter_reglement(correction, moyen=moyen_ancien, montant=-montant)
        ajouter_reglement(correction, moyen=moyen_nouveau, montant=montant)
        correction = encaisser_vente(correction)
        verifier_egalites(correction)
        return correction

    def test_chiffre_affaires_par_moyen_offert_total_et_part_offerte(self):
        """
        Une bière à 5,00 € offerte en totalité (règlement FREE 500, ajouté par le
        service) et un jus à 3,50 € avec 1,50 € offerts (espèces 200, FREE 150).
        L'offert n'est pas de l'argent : par moyen = {espèces 200} ; chiffre
        d'affaires 0 + 200 = 200.
        / A fully gifted beer and a juice with a gifted part: by method = cash 200;
        revenue 200.
        """
        tarif_de_la_biere = creer_tarif_vendu(nom="Biere", prix_en_euros="5.00")
        verifier_egalites(fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[{
                "pricesold": tarif_de_la_biere, "quantite": Decimal("1"),
                "prix_unitaire": 500, "taux_tva": Decimal("20"),
                "offert_en_totalite": True,
            }],
        ))
        verifier_egalites(fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[{
                "pricesold": self.tarif_du_jus, "quantite": Decimal("1"),
                "prix_unitaire": 350, "taux_tva": Decimal("20"),
                "part_offerte": 150,
                "source_offert": LigneArticle.SourceOffert.OFFRIR,
            }],
            reglements=[
                {"moyen": PaymentMethod.CASH, "montant": 200},
                {"moyen": PaymentMethod.FREE, "montant": 150},
            ],
        ))

        chiffre_affaires = self._rapport().section_chiffre_affaires()

        assert self._totaux_par_moyen(chiffre_affaires["par_moyen"]) == {
            PaymentMethod.CASH: 200,
        }
        assert chiffre_affaires["total_ttc_en_centimes"] == 200
        self._verifier_somme_egale_au_chiffre_d_affaires(chiffre_affaires)

    def test_chiffre_affaires_par_moyen_jetons_cadeau(self):
        """
        Une bière à 5,00 € payée en jetons cadeau (LG, TVA 0, D8 bis) : c'est une
        vente. Par moyen = {jetons 500} ; chiffre d'affaires 500.
        / A beer paid in gift tokens is a sale: by method = tokens 500; revenue 500.
        """
        jetons_cadeau = self._monnaie(NOM_DES_JETONS_CADEAU, Asset.TNF)
        tarif_de_la_biere = creer_tarif_vendu(
            nom="Biere", prix_en_euros="5.00", taux_tva="0.00"
        )
        verifier_egalites(fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[{
                "pricesold": tarif_de_la_biere, "quantite": Decimal("1"),
                "prix_unitaire": 500, "taux_tva": Decimal("0"),
            }],
            reglements=[{
                "moyen": PaymentMethod.LOCAL_GIFT, "montant": 500,
                "asset": jetons_cadeau.uuid,
            }],
        ))

        chiffre_affaires = self._rapport().section_chiffre_affaires()

        assert self._totaux_par_moyen(chiffre_affaires["par_moyen"]) == {
            PaymentMethod.LOCAL_GIFT: 500,
        }
        assert chiffre_affaires["total_ttc_en_centimes"] == 500
        self._verifier_somme_egale_au_chiffre_d_affaires(chiffre_affaires)

    def test_chiffre_affaires_par_moyen_vente_en_points_exclue(self):
        """
        Une planche à 300,00 points (vente en points, règlement NM) et un jus à
        3,50 € en espèces. Les points ne sont ni du chiffre d'affaires ni un moyen :
        par moyen = {espèces 350} ; chiffre d'affaires 350.
        / A points sale and a cash juice: by method = cash 350; revenue 350.
        """
        points = self._monnaie(NOM_DES_POINTS, Asset.FID)
        self._vente_en_points(points, 30000)
        self._vendre_un_jus_en_especes()

        chiffre_affaires = self._rapport().section_chiffre_affaires()

        assert self._totaux_par_moyen(chiffre_affaires["par_moyen"]) == {
            PaymentMethod.CASH: 350,
        }
        assert chiffre_affaires["total_ttc_en_centimes"] == 350
        self._verifier_somme_egale_au_chiffre_d_affaires(chiffre_affaires)

    def test_chiffre_affaires_par_moyen_ecart_negatif(self):
        """
        Un billet à 20,00 € payé par Stripe, qui n'encaisse que 19,98 € : règlement
        Stripe 1998, écart d'encaissement hors chiffre d'affaires −2. Par moyen =
        Stripe 1998 − (−2) = 2000 ; chiffre d'affaires 2000.
        / A Stripe ticket collected 2 cents short: Stripe 1998 + 2 = 2000; revenue 2000.
        """
        self._billet_vendu_en_ligne_par_stripe(2000, ecart_en_centimes=-2)

        chiffre_affaires = self._rapport().section_chiffre_affaires()

        assert self._totaux_par_moyen(chiffre_affaires["par_moyen"]) == {
            PaymentMethod.STRIPE_NOFED: 2000,
        }
        assert chiffre_affaires["total_ttc_en_centimes"] == 2000
        self._verifier_somme_egale_au_chiffre_d_affaires(chiffre_affaires)

    def test_chiffre_affaires_par_moyen_plusieurs_moyens(self):
        """
        Une recharge de 20,00 € et une bière à 5,00 €, payées 15,00 € en espèces et
        10,00 € par CB. La part hors chiffre d'affaires (2000) ne sait pas sous quel
        moyen tomber : elle est retirée de « plusieurs moyens ». Par moyen = espèces
        1500, CB 1000, plusieurs moyens −2000 ; Σ = 500 = chiffre d'affaires (la
        bière).
        / A top-up and a beer paid by two methods: the off-revenue part goes under
        "plusieurs_moyens": 1500 + 1000 − 2000 = 500 = revenue.
        """
        tarif_de_la_biere = creer_tarif_vendu(nom="Biere", prix_en_euros="5.00")
        verifier_egalites(fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                {
                    "pricesold": self._tarif_de_recharge("20.00"),
                    "quantite": Decimal("1"),
                    "prix_unitaire": 2000, "taux_tva": Decimal("0"),
                },
                {
                    "pricesold": tarif_de_la_biere, "quantite": Decimal("1"),
                    "prix_unitaire": 500, "taux_tva": Decimal("20"),
                },
            ],
            reglements=[
                {"moyen": PaymentMethod.CASH, "montant": 1500},
                {"moyen": PaymentMethod.CC, "montant": 1000},
            ],
        ))

        chiffre_affaires = self._rapport().section_chiffre_affaires()

        assert self._totaux_par_moyen(chiffre_affaires["par_moyen"]) == {
            PaymentMethod.CASH: 1500,
            PaymentMethod.CC: 1000,
            "plusieurs_moyens": -2000,
        }
        assert chiffre_affaires["total_ttc_en_centimes"] == 500
        self._verifier_somme_egale_au_chiffre_d_affaires(chiffre_affaires)

    def test_recharge_en_especes_corrigee_en_cb(self):
        """
        Une recharge de 20,00 € encaissée en espèces par erreur, puis corrigée en CB
        (vente CORRECTION : espèces −2000, CB +2000). La recharge n'est pas du
        chiffre d'affaires : sa part suit l'argent.
        - Chiffre d'affaires par moyen : espèces 2000 − 2000 (part hors CA) − 2000 +
          2000 (part rendue) = 0 ; CB 2000 − 2000 (part retirée) = 0. Rien de non nul.
        - Recharges par moyen : espèces 2000 − 2000 = 0, CB +2000.
        - Ticket X : aucune ligne au-dessus du TOTAL, TOTAL 0, « Recharges: 20.00
          EUR » sous le total.
        / A cash top-up corrected to card: revenue by method all zero, top-ups under
        card 2000, X ticket with no line above a 0 TOTAL.
        """
        from laboutik.printing.formatters import formatter_ticket_x

        vente_de_la_recharge = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[{
                "pricesold": self._tarif_de_recharge("20.00"),
                "quantite": Decimal("1"),
                "prix_unitaire": 2000, "taux_tva": Decimal("0"),
            }],
            reglements=[{"moyen": PaymentMethod.CASH, "montant": 2000}],
        )
        verifier_egalites(vente_de_la_recharge)
        self._corriger_le_moyen(
            vente_de_la_recharge, PaymentMethod.CASH, PaymentMethod.CC, 2000
        )

        rapport = self._rapport()
        chiffre_affaires = rapport.section_chiffre_affaires()
        recharges_encaissees = rapport.section_annexe()["recharges_et_cartes"][
            "recharges_encaissees"
        ]

        assert self._totaux_non_nuls_par_moyen(chiffre_affaires["par_moyen"]) == {}
        assert chiffre_affaires["total_ttc_en_centimes"] == 0
        self._verifier_somme_egale_au_chiffre_d_affaires(chiffre_affaires)
        assert self._totaux_non_nuls_par_moyen(recharges_encaissees["par_moyen"]) == {
            PaymentMethod.CC: 2000,
        }

        ticket_x = formatter_ticket_x(rapport.rapport_x(), self.debut_de_la_periode)
        assert ticket_x["articles"] == []
        assert ticket_x["total"]["amount"] == 0
        assert "Recharges: 20.00 EUR" in ticket_x["footer"]

    def test_biere_et_recharge_en_especes_corrigees_en_cb(self):
        """
        Une bière à 5,00 € et une recharge de 10,00 €, payées 15,00 € en espèces,
        puis corrigées en CB (espèces −1500, CB +1500).
        - Chiffre d'affaires par moyen : espèces 1500 − 1000 − 1500 + 1000 = 0 ; CB
          1500 − 1000 = 500. Chiffre d'affaires 500 (la bière).
        - Recharges par moyen : espèces 1000 − 1000 = 0, CB +1000.
        / A beer and a top-up paid in cash, corrected to card: revenue card 500,
        top-ups card 1000.
        """
        tarif_de_la_biere = creer_tarif_vendu(nom="Biere", prix_en_euros="5.00")
        vente_du_panier = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                {
                    "pricesold": tarif_de_la_biere, "quantite": Decimal("1"),
                    "prix_unitaire": 500, "taux_tva": Decimal("20"),
                },
                {
                    "pricesold": self._tarif_de_recharge("10.00"),
                    "quantite": Decimal("1"),
                    "prix_unitaire": 1000, "taux_tva": Decimal("0"),
                },
            ],
            reglements=[{"moyen": PaymentMethod.CASH, "montant": 1500}],
        )
        verifier_egalites(vente_du_panier)
        self._corriger_le_moyen(
            vente_du_panier, PaymentMethod.CASH, PaymentMethod.CC, 1500
        )

        rapport = self._rapport()
        chiffre_affaires = rapport.section_chiffre_affaires()
        recharges_encaissees = rapport.section_annexe()["recharges_et_cartes"][
            "recharges_encaissees"
        ]

        assert self._totaux_non_nuls_par_moyen(chiffre_affaires["par_moyen"]) == {
            PaymentMethod.CC: 500,
        }
        assert chiffre_affaires["total_ttc_en_centimes"] == 500
        self._verifier_somme_egale_au_chiffre_d_affaires(chiffre_affaires)
        assert self._totaux_non_nuls_par_moyen(recharges_encaissees["par_moyen"]) == {
            PaymentMethod.CC: 1000,
        }

    def test_recharge_vendue_puis_remboursee(self):
        """
        Une recharge de 20,00 € en espèces, puis remboursée en espèces (avoir : article
        de recharge −2000, hors chiffre d'affaires ; espèces −2000).
        - Chiffre d'affaires par moyen : espèces 2000 − 2000 − 2000 + 2000 = 0 ;
          chiffre d'affaires 0.
        - Réconciliation : recharges 2000 (brut), recharges remboursées −2000.
        - Ticket X : sous le total, « Recharges: 20.00 EUR » et « Recharges
          remboursées: -20.00 » (sans « EUR » : la ligne dépasserait les 32 caractères
          du ticket).
        / A top-up sold then refunded: revenue 0; refunded top-ups −2000, printed
        under the X ticket total.
        """
        from laboutik.printing.formatters import formatter_ticket_x

        vente_de_la_recharge = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[{
                "pricesold": self._tarif_de_recharge("20.00"),
                "quantite": Decimal("1"),
                "prix_unitaire": 2000, "taux_tva": Decimal("0"),
                "status": LigneArticle.VALID,
            }],
            reglements=[{"moyen": PaymentMethod.CASH, "montant": 2000}],
        )
        verifier_egalites(vente_de_la_recharge)
        ligne_de_la_recharge = LigneArticle.objects.get(vente=vente_de_la_recharge)
        vente_d_avoir = ouvrir_vente(
            origine=SaleOrigin.ADMIN,
            nature=Vente.Nature.AVOIR,
            vente_liee=vente_de_la_recharge,
        )
        ajouter_l_article_d_avoir(vente_d_avoir, ligne_de_la_recharge, Decimal("1"))
        ajouter_reglement(vente_d_avoir, moyen=PaymentMethod.CASH, montant=-2000)
        verifier_egalites(encaisser_vente(vente_d_avoir))

        rapport = self._rapport()
        chiffre_affaires = rapport.section_chiffre_affaires()
        reconciliation = rapport.section_reconciliation()

        assert self._totaux_non_nuls_par_moyen(chiffre_affaires["par_moyen"]) == {}
        assert chiffre_affaires["total_ttc_en_centimes"] == 0
        self._verifier_somme_egale_au_chiffre_d_affaires(chiffre_affaires)
        assert reconciliation["recharges_en_centimes"] == 2000
        assert reconciliation["recharges_remboursees_en_centimes"] == -2000

        ticket_x = formatter_ticket_x(rapport.rapport_x(), self.debut_de_la_periode)
        assert "Recharges: 20.00 EUR" in ticket_x["footer"]
        assert "Recharges remboursées: -20.00" in ticket_x["footer"]

    def test_chiffre_affaires_par_moyen_requetes_constantes_avec_des_corrections(self):
        """
        Le nombre de requêtes de la section « chiffre d'affaires » ne grandit pas
        avec le nombre de corrections de recharge : une, puis trois corrections, même
        nombre de requêtes.
        / The revenue section's query count does not grow with the number of
        top-up corrections.
        """
        from django.test.utils import CaptureQueriesContext

        tarif_de_la_recharge = self._tarif_de_recharge("20.00")
        nombre_de_requetes_par_essai = []
        for nombre_de_corrections_a_ajouter in [1, 2]:
            compteur_de_corrections = 0
            while compteur_de_corrections < nombre_de_corrections_a_ajouter:
                vente_de_la_recharge = fabriquer_vente_encaissee(
                    origine=SaleOrigin.LABOUTIK,
                    articles=[{
                        "pricesold": tarif_de_la_recharge,
                        "quantite": Decimal("1"),
                        "prix_unitaire": 2000, "taux_tva": Decimal("0"),
                    }],
                    reglements=[{"moyen": PaymentMethod.CASH, "montant": 2000}],
                )
                self._corriger_le_moyen(
                    vente_de_la_recharge, PaymentMethod.CASH, PaymentMethod.CC, 2000
                )
                compteur_de_corrections += 1
            rapport = self._rapport()
            with CaptureQueriesContext(connection) as requetes:
                rapport.section_chiffre_affaires()
            nombre_de_requetes_par_essai.append(len(requetes))

        assert nombre_de_requetes_par_essai[0] == nombre_de_requetes_par_essai[1]

    def test_recharge_corrigee_deux_fois_suit_le_dernier_moyen(self):
        """
        Une recharge de 20,00 € en espèces, corrigée en CB, puis la CB corrigée en
        chèque. La part de la recharge suit l'argent à chaque correction.
        - Chiffre d'affaires par moyen : espèces 2000 − 2000 (hors CA) − 2000 + 2000
          (rendue par la 1ʳᵉ correction) = 0 ; CB 2000 − 2000 (retirée) − 2000 + 2000
          (rendue par la 2ᵉ) = 0 ; chèque 2000 − 2000 (retirée) = 0. Tout à 0.
        - Recharges par moyen : espèces 2000 − 2000 = 0 ; CB +2000 − 2000 = 0 ;
          chèque +2000. Seule ligne non nulle : chèque 2000.
        / A cash top-up corrected to card, then card to cheque: revenue all zero,
        top-ups under cheque 2000.
        """
        vente_de_la_recharge = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[{
                "pricesold": self._tarif_de_recharge("20.00"),
                "quantite": Decimal("1"),
                "prix_unitaire": 2000, "taux_tva": Decimal("0"),
            }],
            reglements=[{"moyen": PaymentMethod.CASH, "montant": 2000}],
        )
        verifier_egalites(vente_de_la_recharge)
        self._corriger_le_moyen(
            vente_de_la_recharge, PaymentMethod.CASH, PaymentMethod.CC, 2000
        )
        self._corriger_le_moyen(
            vente_de_la_recharge, PaymentMethod.CC, PaymentMethod.CHEQUE, 2000
        )

        rapport = self._rapport()
        chiffre_affaires = rapport.section_chiffre_affaires()
        recharges_encaissees = rapport.section_annexe()["recharges_et_cartes"][
            "recharges_encaissees"
        ]

        assert self._totaux_non_nuls_par_moyen(chiffre_affaires["par_moyen"]) == {}
        assert chiffre_affaires["total_ttc_en_centimes"] == 0
        self._verifier_somme_egale_au_chiffre_d_affaires(chiffre_affaires)
        assert self._totaux_non_nuls_par_moyen(recharges_encaissees["par_moyen"]) == {
            PaymentMethod.CHEQUE: 2000,
        }

    def _recharge_en_especes_a_l_heure(self, heure):
        """
        Une recharge de 20,00 € encaissée en espèces à l'heure donnée.
        / A 20.00 € cash top-up settled at the given time.
        """
        with patch("django.utils.timezone.now", return_value=heure):
            vente_de_la_recharge = fabriquer_vente_encaissee(
                origine=SaleOrigin.LABOUTIK,
                articles=[{
                    "pricesold": self._tarif_de_recharge("20.00"),
                    "quantite": Decimal("1"),
                    "prix_unitaire": 2000, "taux_tva": Decimal("0"),
                }],
                reglements=[{"moyen": PaymentMethod.CASH, "montant": 2000}],
            )
        verifier_egalites(vente_de_la_recharge)
        return vente_de_la_recharge

    def _corriger_le_moyen_a_l_heure(
        self, heure, vente_d_origine, moyen_ancien, moyen_nouveau, montant
    ):
        """
        La correction du moyen de paiement d'une vente, encaissée à l'heure donnée.
        / A payment method correction settled at the given time.
        """
        with patch("django.utils.timezone.now", return_value=heure):
            return self._corriger_le_moyen(
                vente_d_origine, moyen_ancien, moyen_nouveau, montant
            )

    def test_correction_d_avant_la_periode_suivie_sans_deplacement(self):
        """
        Une recharge de 20,00 € en espèces le 10/03/2026 à 12:00, corrigée en CB le
        même jour à 12:10 (C1), puis la CB corrigée en chèque le 12/03/2026 à 12:00
        (C2). Le rapport du 12/03 (Paris) ne contient que C2.
        - C1 est hors de la période : elle est suivie (la part est sous CB avant C2),
          mais elle ne déplace rien dans ce rapport. Les espèces n'y apparaissent pas.
        - C2 déplace la part de la CB au chèque.
        - Chiffre d'affaires par moyen : CB −2000 + 2000 = 0 ; chèque 2000 − 2000 = 0.
        - Recharges par moyen : CB −2000, chèque +2000 (la recharge est comptée le
          10/03, sous les espèces, dans le rapport de son jour).
        / A correction before the period is followed but emits nothing: only C2 moves
        the part, from card to cheque; cash never appears.
        """
        fuseau_de_paris = ZoneInfo("Europe/Paris")
        vente_de_la_recharge = self._recharge_en_especes_a_l_heure(
            datetime(2026, 3, 10, 12, 0, tzinfo=fuseau_de_paris)
        )
        self._corriger_le_moyen_a_l_heure(
            datetime(2026, 3, 10, 12, 10, tzinfo=fuseau_de_paris),
            vente_de_la_recharge, PaymentMethod.CASH, PaymentMethod.CC, 2000,
        )
        self._corriger_le_moyen_a_l_heure(
            datetime(2026, 3, 12, 12, 0, tzinfo=fuseau_de_paris),
            vente_de_la_recharge, PaymentMethod.CC, PaymentMethod.CHEQUE, 2000,
        )

        rapport_du_12_mars = self._rapport(
            debut=datetime(2026, 3, 12, 0, 0, tzinfo=fuseau_de_paris),
            fin=datetime(2026, 3, 13, 0, 0, tzinfo=fuseau_de_paris),
        )
        chiffre_affaires = rapport_du_12_mars.section_chiffre_affaires()
        recharges_encaissees = rapport_du_12_mars.section_annexe()[
            "recharges_et_cartes"
        ]["recharges_encaissees"]

        assert self._totaux_par_moyen(chiffre_affaires["par_moyen"]) == {
            PaymentMethod.CC: 0,
            PaymentMethod.CHEQUE: 0,
        }
        self._verifier_somme_egale_au_chiffre_d_affaires(chiffre_affaires)
        assert self._totaux_par_moyen(recharges_encaissees["par_moyen"]) == {
            PaymentMethod.CC: -2000,
            PaymentMethod.CHEQUE: 2000,
        }
        assert recharges_encaissees["total_en_centimes"] == 0

    def test_deux_corrections_a_cheval_sur_la_borne_d_une_m(self):
        """
        Le lieu est à Paris. Une recharge de 20,00 € en espèces le 31/01/2026 à 23:30 ;
        C1 espèces → CB le 31/01 à 23:50 ; C2 CB → chèque le 01/02 à 00:10. Le rapport
        de la M de février (01/02 00:00 → 01/03 00:00, heure de Paris) ne contient
        que C2.
        - Chiffre d'affaires par moyen : CB 0, chèque 0.
        - Recharges par moyen : CB −2000, chèque +2000.
        / Two corrections across a calendar M boundary: in February's M, revenue by
        method card 0 / cheque 0; top-ups card −2000 / cheque +2000.
        """
        fuseau_de_paris = ZoneInfo("Europe/Paris")
        vente_de_la_recharge = self._recharge_en_especes_a_l_heure(
            datetime(2026, 1, 31, 23, 30, tzinfo=fuseau_de_paris)
        )
        self._corriger_le_moyen_a_l_heure(
            datetime(2026, 1, 31, 23, 50, tzinfo=fuseau_de_paris),
            vente_de_la_recharge, PaymentMethod.CASH, PaymentMethod.CC, 2000,
        )
        self._corriger_le_moyen_a_l_heure(
            datetime(2026, 2, 1, 0, 10, tzinfo=fuseau_de_paris),
            vente_de_la_recharge, PaymentMethod.CC, PaymentMethod.CHEQUE, 2000,
        )

        rapport_de_fevrier = self._rapport(
            debut=datetime(2026, 2, 1, 0, 0, tzinfo=fuseau_de_paris),
            fin=datetime(2026, 3, 1, 0, 0, tzinfo=fuseau_de_paris),
        )
        chiffre_affaires = rapport_de_fevrier.section_chiffre_affaires()
        recharges_encaissees = rapport_de_fevrier.section_annexe()[
            "recharges_et_cartes"
        ]["recharges_encaissees"]

        assert self._totaux_par_moyen(chiffre_affaires["par_moyen"]) == {
            PaymentMethod.CC: 0,
            PaymentMethod.CHEQUE: 0,
        }
        self._verifier_somme_egale_au_chiffre_d_affaires(chiffre_affaires)
        assert self._totaux_par_moyen(recharges_encaissees["par_moyen"]) == {
            PaymentMethod.CC: -2000,
            PaymentMethod.CHEQUE: 2000,
        }

    def test_correction_d_un_avoir_de_recharge_sans_dependre_du_signe(self):
        """
        Une recharge de 20,00 € en espèces, remboursée en espèces (avoir : article de
        recharge −2000, espèces −2000), puis l'avoir corrigé en CB : la correction
        porte les signes inverses d'une correction de vente (espèces +2000, CB −2000).
        Le déplacement suit la paire {espèces, CB}, pas le signe.
        - Chiffre d'affaires par moyen : tout à 0 (rien de non nul).
        - Recharges encaissées par moyen : espèces 2000 (la recharge de la vente) ; un
          avoir n'est pas une recharge encaissée, sa correction ne la déplace pas.
        / A refunded top-up whose credit note is corrected to card (reversed signs):
        the move follows the pair, not the sign; revenue all zero, top-ups cash 2000.
        """
        vente_de_la_recharge = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[{
                "pricesold": self._tarif_de_recharge("20.00"),
                "quantite": Decimal("1"),
                "prix_unitaire": 2000, "taux_tva": Decimal("0"),
                "status": LigneArticle.VALID,
            }],
            reglements=[{"moyen": PaymentMethod.CASH, "montant": 2000}],
        )
        verifier_egalites(vente_de_la_recharge)
        ligne_de_la_recharge = LigneArticle.objects.get(vente=vente_de_la_recharge)
        vente_d_avoir = ouvrir_vente(
            origine=SaleOrigin.LABOUTIK,
            nature=Vente.Nature.AVOIR,
            vente_liee=vente_de_la_recharge,
        )
        ajouter_l_article_d_avoir(vente_d_avoir, ligne_de_la_recharge, Decimal("1"))
        ajouter_reglement(vente_d_avoir, moyen=PaymentMethod.CASH, montant=-2000)
        vente_d_avoir = encaisser_vente(vente_d_avoir)
        verifier_egalites(vente_d_avoir)
        self._corriger_le_moyen(
            vente_d_avoir, PaymentMethod.CASH, PaymentMethod.CC, -2000
        )

        rapport = self._rapport()
        chiffre_affaires = rapport.section_chiffre_affaires()
        recharges_encaissees = rapport.section_annexe()["recharges_et_cartes"][
            "recharges_encaissees"
        ]

        assert self._totaux_non_nuls_par_moyen(chiffre_affaires["par_moyen"]) == {}
        assert chiffre_affaires["total_ttc_en_centimes"] == 0
        self._verifier_somme_egale_au_chiffre_d_affaires(chiffre_affaires)
        assert self._totaux_non_nuls_par_moyen(recharges_encaissees["par_moyen"]) == {
            PaymentMethod.CASH: 2000,
        }

    def test_chiffre_affaires_par_moyen_ordre_a_l_ecran(self):
        """
        L'écran écrit les moyens du chiffre d'affaires dans l'ordre des tickets :
        espèces, CB, chèque, puis les autres moyens d'argent (par code : SN), puis
        le cashless (par code : LE), puis « plusieurs moyens ». Le dictionnaire est
        donné dans un autre ordre exprès.
        / The screen writes the methods in the tickets' order: cash, card, cheque,
        other money, cashless, several.
        """
        chiffre_affaires = {
            "total_ttc_en_centimes": 600,
            "total_ht_en_centimes": 500,
            "total_tva_en_centimes": 100,
            "par_moyen": {
                "plusieurs_moyens": {"libelle": "Plusieurs", "total_en_centimes": 100},
                PaymentMethod.LOCAL_EURO: {"libelle": "LE", "total_en_centimes": 100},
                PaymentMethod.STRIPE_NOFED: {"libelle": "SN", "total_en_centimes": 100},
                PaymentMethod.CHEQUE: {"libelle": "CH", "total_en_centimes": 100},
                PaymentMethod.CC: {"libelle": "CC", "total_en_centimes": 100},
                PaymentMethod.CASH: {"libelle": "CA", "total_en_centimes": 100},
            },
            "par_taux": {},
            "par_categorie": {},
            "par_origine": {},
            "par_journal": {},
        }

        with translation.override("fr"):
            sections = sections_pour_affichage({"chiffre_affaires": chiffre_affaires})

        tableau_par_moyen = None
        tableaux_de_la_section = sections[0]["tableaux"]
        for tableau in tableaux_de_la_section:
            if tableau["testid"] == "chiffre-affaires-par-moyen":
                tableau_par_moyen = tableau
        assert tableau_par_moyen is not None
        libelles_dans_l_ordre = []
        for ligne in tableau_par_moyen["lignes"]:
            libelles_dans_l_ordre.append(ligne[0]["texte"])
        assert libelles_dans_l_ordre == ["CA", "CC", "CH", "SN", "LE", "Plusieurs"]

    def test_reconciliation_avoirs_correction_vidage_termes_et_egalites(self):
        """
        Section 5 sur un scénario complet :
        - un jus à 30,00 € en espèces, puis remboursé en espèces par l'admin (−3000) ;
        - un billet à 20,00 € payé par Stripe, qui encaisse 20,03 € (écart +3), puis
          remboursé par Stripe 20,01 € (−2001, écart −1) ;
        - une recharge de 15,00 € en CB, corrigée en espèces (CB −1500, espèces +1500) ;
        - une carte de 7,00 € vidée en espèces (−700).
        Argent : ventes 3000 + 2003 + 1500 = 6503 ; correction 0 ; avoirs −5001 ;
        vidage −700 ; argent reçu 802.
        Termes : recharges 1500 ; écarts 2 (tous : +3 et −1) ; remboursements = argent
        des avoirs −5001 moins leurs écarts (−1) = −5000 ; ventes payées en argent =
        6503 − 1500 − 3 = 5000 ; cartes vidées −700.
        Identité : 5000 + 1500 − 5000 − 700 + 2 = 802.
        Égalités entre sections : argent reçu = argent de la section 3 (1502) +
        espèces rendues aux vidages (−700) ; recharges = total des recharges de
        l'annexe ; écarts = total des écarts de l'annexe. La section 5 ne rend que des
        nombres : la phrase est écrite par l'affichage.
        / Full reconciliation scenario: every term, the identity, and the equalities
        between sections.
        """
        monnaie_locale = self._monnaie(NOM_DE_LA_MONNAIE_LOCALE, Asset.TLF)

        # Le jus, puis son avoir en espèces par le bouton « Avoir ».
        # / The juice, then its cash credit note.
        ligne_du_jus = self._ligne_d_un_jus_vendu_en_especes(prix=3000)
        with taches_celery_enregistrees():
            ecrire_la_vente_d_avoir_d_une_ligne(
                ligne_du_jus,
                quantite=Decimal("1"),
                moyen_rembourse=PaymentMethod.CASH,
                origine=SaleOrigin.ADMIN,
            )

        # Le billet payé par Stripe avec un écart, puis remboursé par Stripe.
        # / The Stripe ticket with a gap, then refunded by Stripe.
        ligne_du_billet = self._billet_vendu_en_ligne_par_stripe(
            2000, ecart_en_centimes=3
        )
        self._avoir_rembourse_par_stripe(
            ligne_du_billet,
            montant_rembourse_par_stripe=2001,
            reference_externe="re_test_rapport_unique",
        )

        # La recharge en CB, corrigée en espèces.
        # / The card top-up, corrected to cash.
        tarif_de_la_recharge = creer_tarif_vendu(
            nom="Recharge",
            prix_en_euros="15.00",
            taux_tva="0.00",
            methode_caisse=Product.RECHARGE_EUROS,
        )
        vente_de_la_recharge = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                {
                    "pricesold": tarif_de_la_recharge,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 1500,
                    "taux_tva": Decimal("0"),
                },
            ],
            reglements=[{"moyen": PaymentMethod.CC, "montant": 1500}],
        )
        verifier_egalites(vente_de_la_recharge)
        correction = ouvrir_vente(
            origine=SaleOrigin.LABOUTIK,
            nature=Vente.Nature.CORRECTION,
            vente_liee=vente_de_la_recharge,
        )
        ajouter_reglement(correction, moyen=PaymentMethod.CC, montant=-1500)
        ajouter_reglement(correction, moyen=PaymentMethod.CASH, montant=1500)
        correction = encaisser_vente(correction)
        verifier_egalites(correction)

        # La carte vidée.
        # / The emptied card.
        vente_du_vidage = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            nature=Vente.Nature.VIDAGE_CARTE,
            reglements=[
                {
                    "moyen": PaymentMethod.LOCAL_EURO,
                    "montant": 700,
                    "asset": monnaie_locale.uuid,
                },
                {"moyen": PaymentMethod.CASH, "montant": -700},
            ],
        )
        verifier_egalites(vente_du_vidage)

        sections = self._rapport().toutes_les_sections()
        reconciliation = sections["reconciliation"]
        annexe = sections["annexe"]

        assert reconciliation == {
            "argent_recu_en_centimes": 802,
            "ventes_payees_en_argent_en_centimes": 5000,
            "recharges_en_centimes": 1500,
            "recharges_remboursees_en_centimes": 0,
            "remboursements_en_centimes": -5000,
            "cartes_videes_en_centimes": -700,
            "ecarts_d_encaissement_en_centimes": 2,
        }

        somme_des_termes = (
            reconciliation["ventes_payees_en_argent_en_centimes"]
            + reconciliation["recharges_en_centimes"]
            + reconciliation["remboursements_en_centimes"]
            + reconciliation["cartes_videes_en_centimes"]
            + reconciliation["ecarts_d_encaissement_en_centimes"]
        )
        assert somme_des_termes == reconciliation["argent_recu_en_centimes"]

        argent_de_la_section_3 = sections["reglements"]["argent"]["total_en_centimes"]
        especes_rendues = annexe["recharges_et_cartes"]["cartes_videes"][
            "especes_rendues_en_centimes"
        ]
        assert argent_de_la_section_3 == 1502
        assert especes_rendues == -700
        assert (
            argent_de_la_section_3 + especes_rendues
            == reconciliation["argent_recu_en_centimes"]
        )
        recharges_de_l_annexe = annexe["recharges_et_cartes"]["recharges_encaissees"]
        assert (
            reconciliation["recharges_en_centimes"]
            == recharges_de_l_annexe["total_en_centimes"]
        )
        assert (
            reconciliation["ecarts_d_encaissement_en_centimes"]
            == annexe["ecarts_d_encaissement"]["total_en_centimes"]
        )

        # Les avoirs, par moyen : espèces −3000, Stripe −2001 ; total net −5001.
        # / Credit notes by method: cash −3000, Stripe −2001; net total −5001.
        assert annexe["avoirs"]["nombre"] == 2
        assert annexe["avoirs"]["total_en_centimes"] == -5001
        assert annexe["avoirs"]["par_moyen"]["CA"]["total_en_centimes"] == -3000
        assert annexe["avoirs"]["par_moyen"]["SN"]["total_en_centimes"] == -2001

    # ------------------------------------------------------------------
    # Produit sans catégorie, ventes gratuites en points
    # / Product without category, free sales in points
    # ------------------------------------------------------------------

    def test_produit_sans_categorie_ni_type_libelle_sans_categorie(self):
        """
        Un produit sans catégorie de caisse et sans type de produit (type `N`) est
        rangé sous la clé « type_N », avec le libellé « Sans catégorie ». Le texte du
        menu de choix du type (« Sélectionner une catégorie ») n'est jamais un nom de
        catégorie. Un jus sans catégorie, 3,50 € en espèces.
        / A product without POS category and without product type: key "type_N",
        label "Sans catégorie", never the choice menu text.
        """
        self._vendre_un_jus_en_especes()

        # Le libellé est traduit au moment du calcul : le rapport est calculé en
        # français, la langue des textes source.
        # / The label is translated at computation time: computed in French.
        with translation.override("fr"):
            par_categorie = self._rapport().section_chiffre_affaires()["par_categorie"]

        cle_sans_type = f"type_{Product.NONE}"
        assert set(par_categorie.keys()) == {cle_sans_type}
        assert par_categorie[cle_sans_type]["nom"] == LIBELLE_SANS_CATEGORIE
        assert par_categorie[cle_sans_type]["total_ttc_en_centimes"] == 350

    def test_vente_gratuite_compte_aussi_la_recharge_offerte_en_points(self):
        """
        Une vente gratuite est une vente VENTE réglée à total_ttc 0, quelle que soit
        son unité. Une recharge offerte en points est gratuite, comme la recharge
        cadeau en euros ; une vente en points payée ne vaut jamais 0. Une recharge
        offerte en points (écrite comme l'API v2 l'écrit), une planche payée 500
        centièmes de points et un jus payé en espèces : trois ventes, dont une gratuite.
        / A free sale is a settled VENTE at total_ttc 0, whatever its unit: a top-up
        offered in points is free; a paid points sale never is.
        """
        points = self._monnaie(NOM_DES_POINTS, Asset.FID)
        tarif_de_la_recharge_en_points = creer_tarif_vendu(
            nom="Recharge points",
            prix_en_euros="0.00",
            taux_tva="0.00",
            categorie_article=Product.RECHARGE_CASHLESS,
        )
        recharge_offerte_en_points = ouvrir_vente(
            origine=SaleOrigin.LESPASS,
            nature=Vente.Nature.VENTE,
            unite=str(points.uuid),
        )
        ajouter_article(
            recharge_offerte_en_points,
            pricesold=tarif_de_la_recharge_en_points,
            quantite=Decimal("1"),
            prix_unitaire=500,
            taux_tva=Decimal("0"),
            offert_en_totalite=True,
        )
        recharge_offerte_en_points = encaisser_vente(recharge_offerte_en_points)
        verifier_egalites(recharge_offerte_en_points)

        self._vente_en_points(points, 500)
        self._vendre_un_jus_en_especes()

        en_tete = self._rapport().section_en_tete()

        assert en_tete["nombre_de_ventes"] == 3
        assert en_tete["nombre_de_ventes_gratuites"] == 1

    # ------------------------------------------------------------------
    # 4 — Caisse espèces (le tiroir)
    # / 4 — Cash drawer
    # ------------------------------------------------------------------

    def _poser_le_fond_de_caisse(self, fond_en_centimes):
        """
        Pose le fond de caisse du lieu de test.
        Le singleton est aussi gardé dans le cache (django-solo), et l'annulation de
        la transaction ne touche pas le cache : le fond est remis à 0 à la fin du test,
        avant l'annulation. Sans cela, les autres tests du lieu liraient ce fond.
        / Sets the test venue's cash float, reset to 0 at the end of the test: the
        singleton is also cached, and the rollback does not touch the cache.
        """
        configuration_de_la_caisse = LaboutikConfiguration.get_solo()
        configuration_de_la_caisse.fond_de_caisse = fond_en_centimes
        configuration_de_la_caisse.save()
        self.addCleanup(self._remettre_le_fond_de_caisse_a_zero)

    def _remettre_le_fond_de_caisse_a_zero(self):
        """Le fond de caisse revient au défaut du champ. / Cash float back to default."""
        configuration_de_la_caisse = LaboutikConfiguration.get_solo()
        configuration_de_la_caisse.fond_de_caisse = 0
        configuration_de_la_caisse.save()

    def _sortie_de_caisse(self, point_de_vente, montant_en_centimes, heure=None):
        """
        Un retrait d'espèces du tiroir. Son heure est posée à la création
        (`auto_now_add`) : une autre heure est posée ensuite par `update()`
        (tests/PIEGES.md 13.19).
        / A cash withdrawal; another time is set afterwards with update().
        """
        sortie = SortieCaisse.objects.create(
            point_de_vente=point_de_vente,
            montant_total=montant_en_centimes,
        )
        if heure is not None:
            SortieCaisse.objects.filter(pk=sortie.pk).update(datetime=heure)
        return sortie

    def _tarifs_du_gobelet_et_de_son_retour(self):
        """
        Un gobelet consigné à 1,00 € (TVA 20 %) et son produit de retour (prix
        −1,00 €, RETOUR_CONSIGNE), relié au gobelet comme la caisse le demande.
        / A 1.00 € deposit cup and its return product, linked to the cup.
        """
        tarif_du_gobelet = creer_tarif_vendu(
            nom="Gobelet",
            prix_en_euros="1.00",
            taux_tva="20.00",
            methode_caisse=Product.VENTE,
        )
        tarif_du_retour = creer_tarif_vendu(
            nom="Retour gobelet",
            prix_en_euros="-1.00",
            taux_tva="20.00",
            methode_caisse=Product.RETOUR_CONSIGNE,
        )
        produit_de_retour = tarif_du_retour.productsold.product
        produit_de_retour.consigne_remboursee = tarif_du_gobelet.productsold.product
        produit_de_retour.save()
        return tarif_du_gobelet, tarif_du_retour

    def _vendre_le_gobelet_puis_le_rendre(
        self, point_de_vente=None, prix_achat_du_gobelet=0
    ):
        """
        Un gobelet vendu 1,00 € en espèces, puis rapporté : vente AVOIR, article de
        retour au prix et au taux du gobelet (prix −100, quantité 1), 1,00 € rendu en
        espèces. Le prix d'achat du retour est l'opposé de celui du gobelet, comme la
        caisse l'écrit (laboutik/views.py) : un gobelet rendu retire son coût.
        / A cup sold, then returned (AVOIR, −100 in cash); the return's purchase price
        is the opposite of the cup's, like the register writes it.
        """
        tarif_du_gobelet, tarif_du_retour = self._tarifs_du_gobelet_et_de_son_retour()
        vente_du_gobelet = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            point_de_vente=point_de_vente,
            articles=[
                {
                    "pricesold": tarif_du_gobelet,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 100,
                    "taux_tva": Decimal("20"),
                    "prix_achat": prix_achat_du_gobelet,
                },
            ],
            reglements=[{"moyen": PaymentMethod.CASH, "montant": 100}],
        )
        verifier_egalites(vente_du_gobelet)

        vente_du_retour = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            nature=Vente.Nature.AVOIR,
            point_de_vente=point_de_vente,
            articles=[
                {
                    "pricesold": tarif_du_retour,
                    "quantite": Decimal("1"),
                    "prix_unitaire": -100,
                    "taux_tva": Decimal("20"),
                    "prix_achat": -prix_achat_du_gobelet,
                },
            ],
            reglements=[{"moyen": PaymentMethod.CASH, "montant": -100}],
        )
        verifier_egalites(vente_du_retour)

    def test_caisse_especes_fond_recues_rendues_sorties_solde(self):
        """
        Section 4, le tiroir de la caisse. Fond de caisse 50,00 €. Au point de vente
        « Bar » :
        - un jus 3,50 € et un gobelet consigné 1,00 €, en espèces : reçues 450 ;
        - un jus 3,50 € en CB : aucune espèce ;
        - le retour du gobelet, 1,00 € rendu en espèces (avoir) : rendues −100 ;
        - une carte de 15,00 € vidée, les espèces rendues : rendues −1500.
        Trois sorties de caisse : 20,00 € dans la période (comptée), 99,99 € juste
        avant le début, 7,77 € pile à la fin (borne exclue, comme pour les ventes) :
        sorties 2000.
        Solde théorique = fond + reçues + rendues − sorties
                        = 5000 + 450 − 1600 − 2000 = 1850.
        / Cash drawer: float 5000, received 450, given back −1600, withdrawals 2000 (one
        just before the period and one exactly at its end are not counted), balance 1850.
        """
        self._poser_le_fond_de_caisse(5000)
        point_de_vente_du_bar = self._point_de_vente("Bar")
        monnaie_locale = self._monnaie(NOM_DE_LA_MONNAIE_LOCALE, Asset.TLF)

        self._vendre_un_jus_en_especes(point_de_vente=point_de_vente_du_bar)
        vente_du_jus_en_cb = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            point_de_vente=point_de_vente_du_bar,
            articles=[
                {
                    "pricesold": self.tarif_du_jus,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 350,
                    "taux_tva": Decimal("20"),
                },
            ],
            reglements=[{"moyen": PaymentMethod.CC, "montant": 350}],
        )
        verifier_egalites(vente_du_jus_en_cb)
        self._vendre_le_gobelet_puis_le_rendre(point_de_vente=point_de_vente_du_bar)

        vente_du_vidage = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            nature=Vente.Nature.VIDAGE_CARTE,
            point_de_vente=point_de_vente_du_bar,
            reglements=[
                {
                    "moyen": PaymentMethod.LOCAL_EURO,
                    "montant": 1500,
                    "asset": monnaie_locale.uuid,
                },
                {"moyen": PaymentMethod.CASH, "montant": -1500},
            ],
        )
        verifier_egalites(vente_du_vidage)

        self._sortie_de_caisse(point_de_vente_du_bar, 2000)
        self._sortie_de_caisse(
            point_de_vente_du_bar,
            9999,
            heure=self.debut_de_la_periode - timedelta(minutes=1),
        )
        self._sortie_de_caisse(point_de_vente_du_bar, 777, heure=self.fin_de_la_periode)

        caisse_especes = self._rapport().section_caisse_especes()

        assert caisse_especes == {
            "fond_de_caisse_en_centimes": 5000,
            "especes_recues_en_centimes": 450,
            "especes_rendues_en_centimes": -1600,
            "corrections_en_centimes": 0,
            "sorties_en_centimes": 2000,
            "solde_theorique_en_centimes": 1850,
        }

    def test_caisse_especes_ignore_les_especes_hors_caisse_v2(self):
        """
        Le tiroir ne compte que les ventes faites sur un point de vente de la caisse
        LaBoutik V2. Les espèces déclarées ailleurs restent dans les règlements
        (section 3), hors du tiroir. Fond de caisse 0 (défaut du champ).
        - un jus 3,50 € en espèces au « Bar » : dans le tiroir ;
        - ce jus remboursé en espèces dans l'admin (avoir sans point de vente) ;
        - une planche 5,00 € en espèces, vente écrite par l'admin, sans point de vente ;
        - un billet 8,00 € « payé ailleurs » en espèces, déclaré par l'API v2, sans
          point de vente.
        Tiroir : reçues 350, rendues 0, solde 350. Section 3, espèces :
        350 − 350 + 500 + 800 = 1300.
        / Only sales made at a V2 register point of sale are in the drawer; cash
        declared elsewhere stays in section 3.
        """
        point_de_vente_du_bar = self._point_de_vente("Bar")

        # Le jus du bar, ligne VALID comme la caisse l'écrit, relue pour l'avoir.
        # / The bar juice, VALID line like the register writes it, read back.
        vente_du_jus_au_bar = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            point_de_vente=point_de_vente_du_bar,
            articles=[
                {
                    "pricesold": self.tarif_du_jus,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 350,
                    "taux_tva": Decimal("20"),
                    "status": LigneArticle.VALID,
                },
            ],
            reglements=[{"moyen": PaymentMethod.CASH, "montant": 350}],
        )
        verifier_egalites(vente_du_jus_au_bar)
        with taches_celery_enregistrees():
            ecrire_la_vente_d_avoir_d_une_ligne(
                LigneArticle.objects.get(vente=vente_du_jus_au_bar),
                quantite=Decimal("1"),
                moyen_rembourse=PaymentMethod.CASH,
                origine=SaleOrigin.ADMIN,
            )

        tarif_de_la_planche = creer_tarif_vendu(
            nom="Planche", prix_en_euros="5.00", taux_tva="20.00"
        )
        vente_de_l_admin = fabriquer_vente_encaissee(
            origine=SaleOrigin.ADMIN,
            articles=[
                {
                    "pricesold": tarif_de_la_planche,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 500,
                    "taux_tva": Decimal("20"),
                },
            ],
            reglements=[{"moyen": PaymentMethod.CASH, "montant": 500}],
        )
        verifier_egalites(vente_de_l_admin)

        tarif_du_billet = creer_tarif_vendu(
            nom="Billet",
            prix_en_euros="8.00",
            taux_tva="5.50",
            categorie_article=Product.BILLET,
        )
        vente_payee_ailleurs = fabriquer_vente_encaissee(
            origine=SaleOrigin.API,
            articles=[
                {
                    "pricesold": tarif_du_billet,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 800,
                    "taux_tva": Decimal("5.5"),
                },
            ],
            reglements=[{"moyen": PaymentMethod.CASH, "montant": 800}],
        )
        verifier_egalites(vente_payee_ailleurs)

        rapport = self._rapport()
        caisse_especes = rapport.section_caisse_especes()
        especes_de_la_section_3 = rapport.section_reglements()["argent"]["par_moyen"][
            "CA"
        ]

        assert caisse_especes == {
            "fond_de_caisse_en_centimes": 0,
            "especes_recues_en_centimes": 350,
            "especes_rendues_en_centimes": 0,
            "corrections_en_centimes": 0,
            "sorties_en_centimes": 0,
            "solde_theorique_en_centimes": 350,
        }
        assert especes_de_la_section_3["total_en_centimes"] == 1300

    def test_caisse_especes_corrections_a_part(self):
        """
        Une correction de moyen de paiement faite à la caisse n'est ni une espèce
        reçue ni une espèce rendue : son net en espèces est sur une ligne à part,
        « corrections », que le solde ajoute. Un jus 3,50 € en espèces au « Bar »,
        puis corrigé en CB au « Bar » (espèces −350, CB +350). Fond 0 :
        reçues 350, rendues 0, corrections −350, solde 350 + 0 − 350 − 0 = 0.
        / A payment method correction is neither cash received nor cash given back:
        its cash net is on its own line, added to the balance.
        """
        point_de_vente_du_bar = self._point_de_vente("Bar")
        jus_du_bar = self._vendre_un_jus_en_especes(
            point_de_vente=point_de_vente_du_bar
        )
        self._corriger_les_especes_en_cb(
            jus_du_bar, None, point_de_vente=point_de_vente_du_bar
        )

        caisse_especes = self._rapport().section_caisse_especes()

        assert caisse_especes == {
            "fond_de_caisse_en_centimes": 0,
            "especes_recues_en_centimes": 350,
            "especes_rendues_en_centimes": 0,
            "corrections_en_centimes": -350,
            "sorties_en_centimes": 0,
            "solde_theorique_en_centimes": 0,
        }

    # ------------------------------------------------------------------
    # 9 — Marge brute
    # / 9 — Gross margin
    # ------------------------------------------------------------------

    def test_marge_brute_somme_des_couts_et_compte_inconnus(self):
        """
        Fiche F §6, test 11 (D21) : marge brute = CA HT − Σ des coûts d'achat écrits sur
        les articles servis. Le coût n'est jamais recalculé (ni quantité × prix, ni
        prix d'achat du produit). En espèces, sauf mention :
        - un jus 3,50 € (20 %), prix d'achat 1,20 € : HT 292, coût 120 ;
        - trois planches à 4,00 € sur une ligne (10 %), prix d'achat inconnu :
          HT arrondi(1200 / 1,1) = 1091, coût inconnu, 3 unités ;
        - un billet gratuit (0 €), prix d'achat inconnu : HT 0 ; rien n'est vendu, il
          n'est pas « au coût inconnu » ;
        - un jus offert (bouton OFFRIR), prix d'achat 1,20 € : HT 0, coût 120 ;
        - un gobelet 1,00 € (20 %), prix d'achat 0,30 € : HT 83, coût 30 ; puis son
          retour (avoir) : HT −83, coût −30 ;
        - un fromage au poids, 0,350 kg pour 4,52 € (5,5 %), prix d'achat 8,00 € le kg,
          quantité de la ligne 1 : HT 428, coût arrondi(0,350 × 800) = 280 ;
        - une recharge 10,00 € en CB : pas servie (hors chiffre d'affaires).
        CA HT 1811 ; coût 120 + 120 + 30 − 30 + 280 = 520 ; marge 1291 ; 3 articles au
        coût inconnu (les trois planches, une seule ligne : on compte des unités).
        / Gross margin = revenue excl. tax − Σ purchase costs written on the served
        items; one item with an unknown cost.
        """
        tarif_de_la_planche = creer_tarif_vendu(
            nom="Planche", prix_en_euros="4.00", taux_tva="10.00"
        )
        tarif_du_billet_gratuit = creer_tarif_vendu(
            nom="Billet gratuit",
            prix_en_euros="0.00",
            taux_tva="0.00",
            categorie_article=Product.BILLET,
        )
        tarif_du_fromage = creer_tarif_vendu(
            nom="Fromage au poids", prix_en_euros="12.90", taux_tva="5.50"
        )
        tarif_de_la_recharge = creer_tarif_vendu(
            nom="Recharge",
            prix_en_euros="10.00",
            taux_tva="0.00",
            methode_caisse=Product.RECHARGE_EUROS,
        )

        vente_du_jus = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                {
                    "pricesold": self.tarif_du_jus,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 350,
                    "taux_tva": Decimal("20"),
                    "prix_achat": 120,
                },
            ],
            reglements=[{"moyen": PaymentMethod.CASH, "montant": 350}],
        )
        verifier_egalites(vente_du_jus)

        vente_de_la_planche = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                {
                    "pricesold": tarif_de_la_planche,
                    "quantite": Decimal("3"),
                    "prix_unitaire": 400,
                    "taux_tva": Decimal("10"),
                },
            ],
            reglements=[{"moyen": PaymentMethod.CASH, "montant": 1200}],
        )
        verifier_egalites(vente_de_la_planche)

        vente_du_billet_gratuit = fabriquer_vente_encaissee(
            origine=SaleOrigin.LESPASS,
            articles=[
                {
                    "pricesold": tarif_du_billet_gratuit,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 0,
                    "taux_tva": Decimal("0"),
                },
            ],
        )
        verifier_egalites(vente_du_billet_gratuit)

        vente_du_jus_offert = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                {
                    "pricesold": self.tarif_du_jus,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 350,
                    "taux_tva": Decimal("20"),
                    "prix_achat": 120,
                    "offert_en_totalite": True,
                },
            ],
        )
        verifier_egalites(vente_du_jus_offert)

        self._vendre_le_gobelet_puis_le_rendre(prix_achat_du_gobelet=30)

        # Vente au poids, comme la caisse l'écrit : quantité 1 sur la ligne, le coût
        # sur la quantité réellement servie, dans l'unité du prix d'achat (kg).
        # / Weight sale like the register: quantity 1, cost on the real served kg.
        vente_du_fromage = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                {
                    "pricesold": tarif_du_fromage,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 452,
                    "taux_tva": Decimal("5.5"),
                    "prix_achat": 800,
                    "quantite_pour_cout": Decimal("0.350"),
                },
            ],
            reglements=[{"moyen": PaymentMethod.CASH, "montant": 452}],
        )
        verifier_egalites(vente_du_fromage)

        vente_de_la_recharge = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                {
                    "pricesold": tarif_de_la_recharge,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 1000,
                    "taux_tva": Decimal("0"),
                },
            ],
            reglements=[{"moyen": PaymentMethod.CC, "montant": 1000}],
        )
        verifier_egalites(vente_de_la_recharge)

        rapport = self._rapport()
        marge_brute = rapport.section_marge_brute()

        # HT : jus 350 → arrondi(291,67) = 292 ; planches 3 × 400 = 1200 →
        # arrondi(1090,91) = 1091 ; gobelet 83 et retour −83 ; fromage 452 →
        # arrondi(428,44) = 428.
        # / HT: juice 292, boards 1091, cup 83 and return −83, cheese 428.
        assert marge_brute == {
            "chiffre_affaires_ht_en_centimes": 1811,
            "cout_achat_en_centimes": 520,
            "marge_brute_en_centimes": 1291,
            "nombre_d_articles_au_cout_inconnu": 3,
        }
        assert (
            marge_brute["chiffre_affaires_ht_en_centimes"]
            == rapport.section_chiffre_affaires()["total_ht_en_centimes"]
        )

    def test_marge_brute_un_article_paye_en_deux_parts_compte_un_cout_inconnu(self):
        """
        Les articles au coût inconnu se comptent en unités, pas en lignes. Une bière
        5,00 € sans prix d'achat, payée 3,00 € en jetons cadeau et 2,00 € en CB : la
        caisse l'écrit en deux parts (quantités 0,6 à TVA 0 et 0,4 à 20 %). Elle compte
        pour 1 article au coût inconnu (0,6 + 0,4 = 1), pas 2.
        / Unknown-cost items are counted in units: an item paid in two parts counts 1.
        """
        jetons_cadeau = self._monnaie(NOM_DES_JETONS_CADEAU, Asset.TNF)
        tarif_de_la_biere = creer_tarif_vendu(
            nom="Biere", prix_en_euros="5.00", taux_tva="20.00"
        )
        vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                {
                    "pricesold": tarif_de_la_biere,
                    "quantite": Decimal("0.6"),
                    "prix_unitaire": 500,
                    "taux_tva": Decimal("0"),
                    "total_catalogue_impose": 300,
                },
                {
                    "pricesold": tarif_de_la_biere,
                    "quantite": Decimal("0.4"),
                    "prix_unitaire": 500,
                    "taux_tva": Decimal("20"),
                    "total_catalogue_impose": 200,
                },
            ],
            reglements=[
                {
                    "moyen": PaymentMethod.LOCAL_GIFT,
                    "montant": 300,
                    "asset": jetons_cadeau.uuid,
                },
                {"moyen": PaymentMethod.CC, "montant": 200},
            ],
        )
        verifier_egalites(vente)

        marge_brute = self._rapport().section_marge_brute()

        assert marge_brute["nombre_d_articles_au_cout_inconnu"] == 1

    def test_marge_brute_compte_les_points(self):
        """
        Fiche F §6, test 25c (D21) : un article vendu en points est servi. Son coût
        d'achat (en centimes d'euro) entre dans la marge, alors que la vente en points
        n'est pas dans le chiffre d'affaires. Un jus 3,50 € en espèces (prix d'achat
        1,20 €) et une planche vendue 500 centièmes de points (prix d'achat 1,50 €) :
        CA HT 292, coût 120 + 150 = 270, marge 22.
        / An item sold in points is served: its purchase cost is in the margin, while
        the points sale is not revenue.
        """
        points = self._monnaie(NOM_DES_POINTS, Asset.FID)
        vente_du_jus = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                {
                    "pricesold": self.tarif_du_jus,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 350,
                    "taux_tva": Decimal("20"),
                    "prix_achat": 120,
                },
            ],
            reglements=[{"moyen": PaymentMethod.CASH, "montant": 350}],
        )
        verifier_egalites(vente_du_jus)
        self._vente_en_points(points, 500, prix_achat=150)

        marge_brute = self._rapport().section_marge_brute()

        assert marge_brute == {
            "chiffre_affaires_ht_en_centimes": 292,
            "cout_achat_en_centimes": 270,
            "marge_brute_en_centimes": 22,
            "nombre_d_articles_au_cout_inconnu": 0,
        }

    def test_marge_brute_d_une_vente_remboursee_en_entier_est_nulle(self):
        """
        Un jus 3,50 € en espèces (prix d'achat 1,20 €, coût 120), puis remboursé en
        entier par l'admin (avoir en espèces). L'avoir reprend le coût en négatif
        (−120) : CA HT 292 − 292 = 0, coût 120 − 120 = 0, marge 0, et aucun article
        « au coût inconnu ».
        / A juice sold then fully refunded: the credit note takes the cost back, so the
        margin is 0 and no item has an unknown cost.
        """
        vente_du_jus = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                {
                    "pricesold": self.tarif_du_jus,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 350,
                    "taux_tva": Decimal("20"),
                    "prix_achat": 120,
                    "status": LigneArticle.VALID,
                },
            ],
            reglements=[{"moyen": PaymentMethod.CASH, "montant": 350}],
        )
        verifier_egalites(vente_du_jus)
        with taches_celery_enregistrees():
            ecrire_la_vente_d_avoir_d_une_ligne(
                LigneArticle.objects.get(vente=vente_du_jus),
                quantite=Decimal("1"),
                moyen_rembourse=PaymentMethod.CASH,
                origine=SaleOrigin.ADMIN,
            )

        marge_brute = self._rapport().section_marge_brute()

        assert marge_brute == {
            "chiffre_affaires_ht_en_centimes": 0,
            "cout_achat_en_centimes": 0,
            "marge_brute_en_centimes": 0,
            "nombre_d_articles_au_cout_inconnu": 0,
        }

    def test_marge_brute_l_avoir_d_un_article_au_cout_inconnu_ne_compte_pas(self):
        """
        Les articles au coût inconnu sont des articles VENDUS : un avoir n'en est pas
        un. Un jus 3,50 € sans prix d'achat, vendu en espèces, puis remboursé en
        entier par l'admin (avoir en espèces). La période du rapport commence à l'heure
        de l'avoir : la vente du jus n'y est pas, seul l'avoir y est. Le nombre
        d'articles au coût inconnu vaut 0, jamais −1.
        / Unknown-cost items are SOLD items: a credit note is not one. The credit note
        of an unknown-cost juice, in a period without its sale, counts 0, never −1.
        """
        vente_du_jus = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                {
                    "pricesold": self.tarif_du_jus,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 350,
                    "taux_tva": Decimal("20"),
                    "status": LigneArticle.VALID,
                },
            ],
            reglements=[{"moyen": PaymentMethod.CASH, "montant": 350}],
        )
        verifier_egalites(vente_du_jus)
        with taches_celery_enregistrees():
            article_d_avoir = ecrire_la_vente_d_avoir_d_une_ligne(
                LigneArticle.objects.get(vente=vente_du_jus),
                quantite=Decimal("1"),
                moyen_rembourse=PaymentMethod.CASH,
                origine=SaleOrigin.ADMIN,
            )
        heure_de_la_vente_du_jus = Vente.objects.get(
            pk=vente_du_jus.pk
        ).datetime_encaissement
        heure_de_l_avoir = Vente.objects.get(
            pk=article_d_avoir.vente_id
        ).datetime_encaissement
        # L'état de départ : la vente du jus est AVANT le début de la période.
        # / Starting state: the juice sale is BEFORE the period starts.
        assert heure_de_la_vente_du_jus < heure_de_l_avoir

        marge_brute = self._rapport(debut=heure_de_l_avoir).section_marge_brute()

        assert marge_brute["nombre_d_articles_au_cout_inconnu"] == 0

    def test_marge_brute_un_gobelet_sans_prix_d_achat_vendu_puis_rendu_compte_un(self):
        """
        Un gobelet consigné 1,00 € sans prix d'achat, vendu puis rapporté dans la même
        période. Le gobelet vendu est un article au coût inconnu. Le retour est dans
        une vente AVOIR : il n'est pas un article vendu, il ne retire rien du compte.
        Le nombre d'articles au coût inconnu vaut 1.
        / A cup without purchase price, sold then returned in the same period: the sold
        cup counts, the return (an AVOIR sale) does not. The count is 1.
        """
        self._vendre_le_gobelet_puis_le_rendre(prix_achat_du_gobelet=0)

        marge_brute = self._rapport().section_marge_brute()

        assert marge_brute["nombre_d_articles_au_cout_inconnu"] == 1

    def test_marge_brute_une_ligne_negative_d_une_vente_ne_retire_rien_au_cout_inconnu(
        self,
    ):
        """
        Seules les lignes à quantité positive sont des articles vendus. Une vente
        VENTE porte deux jus sans prix d'achat (+2) et une ligne de jus à quantité −1
        (le service l'accepte). Le nombre d'articles au coût inconnu vaut 2 : la ligne
        négative ne retire rien.
        / Only positive-quantity lines are sold items: a −1 line in a VENTE sale does
        not lower the count (2, not 1).
        """
        vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                {
                    "pricesold": self.tarif_du_jus,
                    "quantite": Decimal("2"),
                    "prix_unitaire": 350,
                    "taux_tva": Decimal("20"),
                },
                {
                    "pricesold": self.tarif_du_jus,
                    "quantite": Decimal("-1"),
                    "prix_unitaire": 350,
                    "taux_tva": Decimal("20"),
                },
            ],
            reglements=[{"moyen": PaymentMethod.CASH, "montant": 350}],
        )
        verifier_egalites(vente)

        marge_brute = self._rapport().section_marge_brute()

        assert marge_brute["nombre_d_articles_au_cout_inconnu"] == 2

    # ------------------------------------------------------------------
    # 10 — Détail
    # / 10 — Detail
    # ------------------------------------------------------------------

    def test_detail_billets_adhesions_produits(self):
        """
        Section 10, le détail (ce que l'ancien Z imprime, sur les champs entiers) :
        - billets, par événement puis par tarif : un concert, deux billets « Plein
          tarif » à 20,00 € et un billet « Tarif réduit » à 10,00 € (5,5 %), payés par
          Stripe ;
        - adhésions, par produit : une adhésion à 20,00 € (TVA 0) en espèces ;
        - ventes par produit (quantité, TTC, HT, offert, coût) : tous les articles du
          chiffre d'affaires, billets et adhésions compris. Deux jus vendus en espèces
          (prix d'achat 1,20 €) et un jus offert. Une recharge (hors chiffre
          d'affaires) n'y est pas.
        Une quantité est rendue en texte. Les ventes par produit additionnent
        exactement le chiffre d'affaires.
        / Detail: tickets by event and price, memberships by product, sales by product
        (all revenue items). Quantities as text; the products add up to the revenue.
        """
        # Le concert, ses deux tarifs, et la réservation des trois billets.
        # / The concert, its two prices, and the booking of the three tickets.
        acheteur = creer_utilisateur()
        concert = creer_evenement_avec_tarif(prix="20.00")
        tarif_reduit = ajouter_un_tarif(
            concert.produit, prix="10.00", nom="Tarif réduit"
        )
        billet_vendu = ProductSold.objects.create(
            product=concert.produit, event=concert.evenement
        )
        tarif_vendu_plein = PriceSold.objects.create(
            productsold=billet_vendu, price=concert.tarif, prix=concert.tarif.prix
        )
        tarif_vendu_reduit = PriceSold.objects.create(
            productsold=billet_vendu, price=tarif_reduit, prix=tarif_reduit.prix
        )
        reservation = Reservation.objects.create(
            user_commande=acheteur, event=concert.evenement, status=Reservation.VALID
        )
        vente_des_billets = fabriquer_vente_encaissee(
            origine=SaleOrigin.LESPASS,
            articles=[
                {
                    "pricesold": tarif_vendu_plein,
                    "quantite": Decimal("2"),
                    "prix_unitaire": 2000,
                    "taux_tva": Decimal("5.5"),
                    "reservation": reservation,
                },
                {
                    "pricesold": tarif_vendu_reduit,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 1000,
                    "taux_tva": Decimal("5.5"),
                    "reservation": reservation,
                },
            ],
            reglements=[{"moyen": PaymentMethod.STRIPE_NOFED, "montant": 5000}],
        )
        verifier_egalites(vente_des_billets)

        # L'adhésion, vendue en espèces.
        # / The membership, sold in cash.
        adhesion = creer_adhesion(prix="20.00")
        adhesion_de_l_adherente = creer_une_adhesion_active(
            creer_utilisateur(), adhesion
        )
        adhesion_vendue = ProductSold.objects.create(product=adhesion.produit)
        tarif_vendu_de_l_adhesion = PriceSold.objects.create(
            productsold=adhesion_vendue, price=adhesion.tarif, prix=adhesion.tarif.prix
        )
        vente_de_l_adhesion = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                {
                    "pricesold": tarif_vendu_de_l_adhesion,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 2000,
                    "taux_tva": Decimal("0"),
                    "membership": adhesion_de_l_adherente,
                },
            ],
            reglements=[{"moyen": PaymentMethod.CASH, "montant": 2000}],
        )
        verifier_egalites(vente_de_l_adhesion)

        # Deux jus vendus, un jus offert, une recharge.
        # / Two juices sold, one gifted, one top-up.
        vente_des_jus = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                {
                    "pricesold": self.tarif_du_jus,
                    "quantite": Decimal("2"),
                    "prix_unitaire": 350,
                    "taux_tva": Decimal("20"),
                    "prix_achat": 120,
                },
            ],
            reglements=[{"moyen": PaymentMethod.CASH, "montant": 700}],
        )
        verifier_egalites(vente_des_jus)
        vente_du_jus_offert = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                {
                    "pricesold": self.tarif_du_jus,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 350,
                    "taux_tva": Decimal("20"),
                    "prix_achat": 120,
                    "offert_en_totalite": True,
                },
            ],
        )
        verifier_egalites(vente_du_jus_offert)
        tarif_de_la_recharge = creer_tarif_vendu(
            nom="Recharge",
            prix_en_euros="10.00",
            taux_tva="0.00",
            methode_caisse=Product.RECHARGE_EUROS,
        )
        vente_de_la_recharge = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                {
                    "pricesold": tarif_de_la_recharge,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 1000,
                    "taux_tva": Decimal("0"),
                },
            ],
            reglements=[{"moyen": PaymentMethod.CC, "montant": 1000}],
        )
        verifier_egalites(vente_de_la_recharge)

        rapport = self._rapport()
        detail = rapport.section_detail()
        chiffre_affaires = rapport.section_chiffre_affaires()

        evenement_relu = Event.objects.get(pk=concert.evenement.pk)
        assert detail["billets"] == {
            str(concert.evenement.uuid): {
                "nom": evenement_relu.name,
                "date": evenement_relu.datetime.isoformat(),
                "par_tarif": {
                    str(concert.tarif.uuid): {
                        "produit": concert.produit.name,
                        "nom": "Plein tarif",
                        "quantite": "2.000000",
                        "total_ttc_en_centimes": 4000,
                    },
                    str(tarif_reduit.uuid): {
                        "produit": concert.produit.name,
                        "nom": "Tarif réduit",
                        "quantite": "1.000000",
                        "total_ttc_en_centimes": 1000,
                    },
                },
            },
        }

        assert detail["adhesions"] == {
            str(adhesion.produit.uuid): {
                "nom": adhesion.produit.name,
                "quantite": "1.000000",
                "total_ttc_en_centimes": 2000,
            },
        }

        # Jus : 2 vendus (700, HT arrondi(583,33) = 583, coût 240) + 1 offert (net 0,
        # offert 350, coût 120). Billets : 4000 → HT arrondi(3791,47) = 3791 ;
        # 1000 → HT arrondi(947,87) = 948. Adhésion : 2000 à TVA 0.
        # / Juice: 2 sold + 1 gifted; tickets HT 3791 + 948; membership at 0 % VAT.
        produit_du_jus = self.tarif_du_jus.productsold.product
        assert detail["ventes_par_produit"] == {
            str(produit_du_jus.uuid): {
                "nom": produit_du_jus.name,
                "categorie": f"type_{Product.NONE}",
                "quantite": "3.000000",
                "total_ttc_en_centimes": 700,
                "total_ht_en_centimes": 583,
                "offert_en_centimes": 350,
                "cout_achat_en_centimes": 360,
            },
            str(concert.produit.uuid): {
                "nom": concert.produit.name,
                "categorie": f"type_{Product.BILLET}",
                "quantite": "3.000000",
                "total_ttc_en_centimes": 5000,
                "total_ht_en_centimes": 4739,
                "offert_en_centimes": 0,
                "cout_achat_en_centimes": 0,
            },
            str(adhesion.produit.uuid): {
                "nom": adhesion.produit.name,
                "categorie": f"type_{Product.ADHESION}",
                "quantite": "1.000000",
                "total_ttc_en_centimes": 2000,
                "total_ht_en_centimes": 2000,
                "offert_en_centimes": 0,
                "cout_achat_en_centimes": 0,
            },
        }

        # Les ventes par produit additionnent exactement le chiffre d'affaires.
        # / Sales by product add up exactly to the revenue.
        somme_des_ttc = 0
        somme_des_ht = 0
        for ligne_du_produit in detail["ventes_par_produit"].values():
            somme_des_ttc += ligne_du_produit["total_ttc_en_centimes"]
            somme_des_ht += ligne_du_produit["total_ht_en_centimes"]
        assert somme_des_ttc == chiffre_affaires["total_ttc_en_centimes"] == 7700
        assert somme_des_ht == chiffre_affaires["total_ht_en_centimes"] == 7322

    # ------------------------------------------------------------------
    # 11 — Intégrité
    # / 11 — Integrity
    # ------------------------------------------------------------------

    def _alterer_le_reglement(self, vente):
        """
        Altère une vente encaissée comme le ferait une écriture à la main dans la
        base : son règlement passe en CB par `update()` (aucun service, aucune nouvelle
        empreinte). Les deux égalités de la vente tiennent encore : seule son empreinte
        le voit.
        / Alters a settled sale like a hand-made database write: only its fingerprint
        sees it.
        """
        Reglement.objects.filter(vente=vente).update(moyen=PaymentMethod.CC)

    def _rapport_qui_commence_a_la_vente(self, vente):
        """
        Le rapport d'une période qui commence à l'heure d'encaissement de la vente
        (lue en base) : les ventes d'avant sont hors de la période.
        / The report of a period starting at the sale's settlement time.
        """
        heure_d_encaissement = Vente.objects.get(pk=vente.pk).datetime_encaissement
        return self._rapport(debut=heure_d_encaissement)

    def test_integrite_ok_puis_alteration_detectee_sur_la_plage(self):
        """
        Section 11 : la chaîne des ventes est vérifiée sur la plage de la période.
        Trois jus en espèces ; la période commence à l'encaissement du deuxième, sa
        plage est [n° 2, n° 3]. La première vente de la plage est reliée à l'empreinte
        stockée de la vente n° 1 : « OK ». Puis le règlement de la vente n° 2 est
        altéré par `update()` : une anomalie, sur la vente n° 2 (empreinte fausse).
        / The chain is checked over the period's range; the first sale of the range is
        linked to the stored fingerprint of the previous one: OK; then an alteration
        in the range is found.
        """
        self._vendre_un_jus_en_especes()
        deuxieme_vente = self._vendre_un_jus_en_especes()
        troisieme_vente = self._vendre_un_jus_en_especes()
        rapport = self._rapport_qui_commence_a_la_vente(deuxieme_vente)

        en_tete = rapport.section_en_tete()
        assert en_tete["numero_premiere_vente"] == deuxieme_vente.numero
        assert en_tete["numero_derniere_vente"] == troisieme_vente.numero
        assert rapport.section_integrite() == {"statut": "OK", "anomalies": []}

        self._alterer_le_reglement(deuxieme_vente)
        integrite = rapport.section_integrite()

        assert integrite["statut"] == "ANOMALIES"
        assert len(integrite["anomalies"]) == 1
        anomalie = integrite["anomalies"][0]
        assert anomalie["numero"] == deuxieme_vente.numero
        assert anomalie["uuid"] == str(deuxieme_vente.uuid)
        assert anomalie["raison"].startswith("Empreinte fausse")

    def test_integrite_ignore_une_alteration_hors_de_la_plage(self):
        """
        Une vente hors de la période n'est pas vérifiée : son altération n'est pas
        vue. Trois jus en espèces, la période commence à l'encaissement du deuxième ;
        la vente n° 1 est altérée par `update()`. Son empreinte stockée ne change pas :
        la vente n° 2 y reste reliée. Intégrité de la période : « OK ».
        / A sale out of the period is not checked: its alteration is not seen.
        """
        premiere_vente = self._vendre_un_jus_en_especes()
        deuxieme_vente = self._vendre_un_jus_en_especes()
        self._vendre_un_jus_en_especes()
        self._alterer_le_reglement(premiere_vente)

        rapport = self._rapport_qui_commence_a_la_vente(deuxieme_vente)

        assert rapport.section_integrite() == {"statut": "OK", "anomalies": []}

    def test_integrite_ignore_une_alteration_apres_la_fin_de_la_periode(self):
        """
        Une vente encaissée après la période n'est pas vérifiée : son altération
        n'est pas vue. Trois jus en espèces ; la période finit à l'encaissement du
        troisième (borne de fin exclue) : sa plage est [n° 1, n° 2]. La vente n° 3 est
        altérée par `update()`. Intégrité de la période : « OK ».
        / A sale settled after the period is not checked: its alteration is not seen.
        """
        premiere_vente = self._vendre_un_jus_en_especes()
        deuxieme_vente = self._vendre_un_jus_en_especes()
        troisieme_vente = self._vendre_un_jus_en_especes()
        self._alterer_le_reglement(troisieme_vente)
        heure_de_la_troisieme_vente = Vente.objects.get(
            pk=troisieme_vente.pk
        ).datetime_encaissement

        rapport = self._rapport(fin=heure_de_la_troisieme_vente)

        en_tete = rapport.section_en_tete()
        assert en_tete["numero_premiere_vente"] == premiere_vente.numero
        assert en_tete["numero_derniere_vente"] == deuxieme_vente.numero
        assert rapport.section_integrite() == {"statut": "OK", "anomalies": []}

    def test_verifier_chaine_ventes_ignore_une_alteration_apres_la_plage(self):
        """
        `verifier_chaine_ventes` avec une plage ne vérifie pas les ventes d'après sa
        fin. Trois jus ; la vente n° 3 est altérée par `update()`. Sans plage,
        l'anomalie est trouvée ; sur la plage [n° 1, n° 2], rien n'est signalé.
        / With a range, sales after its end are not checked.
        """
        premiere_vente = self._vendre_un_jus_en_especes()
        deuxieme_vente = self._vendre_un_jus_en_especes()
        troisieme_vente = self._vendre_un_jus_en_especes()
        self._alterer_le_reglement(troisieme_vente)
        cle_de_l_empreinte = LaboutikConfiguration.get_solo().get_or_create_hmac_key()

        anomalies_sans_plage = verifier_chaine_ventes(cle_de_l_empreinte)
        anomalies_sur_la_plage = verifier_chaine_ventes(
            cle_de_l_empreinte,
            numero_de_la_premiere_vente=premiere_vente.numero,
            numero_de_la_derniere_vente=deuxieme_vente.numero,
        )

        assert len(anomalies_sans_plage) == 1
        assert anomalies_sans_plage[0]["numero"] == troisieme_vente.numero
        assert anomalies_sur_la_plage == []

    def _supprimer_la_vente(self, vente):
        """
        Supprime une vente encaissée, ses articles et ses règlements, comme le ferait
        une écriture à la main dans la base (aucun service).
        / Deletes a settled sale with its items and payments, like a hand-made write.
        """
        LigneArticle.objects.filter(vente=vente).delete()
        Reglement.objects.filter(vente=vente).delete()
        Vente.objects.filter(pk=vente.pk).delete()

    def test_verifier_chaine_ventes_vente_supprimee_juste_avant_la_plage(self):
        """
        La plage est reliée à la DERNIÈRE vente réglée de numéro inférieur à son
        début, pas à « numéro − 1 ». Quatre jus ; la vente n° 3 est supprimée. Sur la
        plage [n° 4, n° 4], la vente n° 4 est signalée comme sur la chaîne entière :
        « Trou de numéro » (elle suit la n° 2) et « Maillon cassé ».
        / The range is linked to the last settled sale numbered below its start: a sale
        deleted just before the range shows as a number gap, as on the whole chain.
        """
        self._vendre_un_jus_en_especes()
        self._vendre_un_jus_en_especes()
        troisieme_vente = self._vendre_un_jus_en_especes()
        quatrieme_vente = self._vendre_un_jus_en_especes()
        self._supprimer_la_vente(troisieme_vente)
        cle_de_l_empreinte = LaboutikConfiguration.get_solo().get_or_create_hmac_key()

        anomalies_de_toute_la_chaine = verifier_chaine_ventes(cle_de_l_empreinte)
        anomalies_sur_la_plage = verifier_chaine_ventes(
            cle_de_l_empreinte,
            numero_de_la_premiere_vente=quatrieme_vente.numero,
            numero_de_la_derniere_vente=quatrieme_vente.numero,
        )

        raisons_sur_la_plage = []
        for anomalie in anomalies_sur_la_plage:
            assert anomalie["numero"] == quatrieme_vente.numero
            raisons_sur_la_plage.append(anomalie["raison"])
        assert len(raisons_sur_la_plage) == 2
        assert raisons_sur_la_plage[0].startswith("Trou de numéro")
        assert raisons_sur_la_plage[1].startswith("Maillon cassé")
        assert anomalies_sur_la_plage == anomalies_de_toute_la_chaine

    def test_verifier_chaine_ventes_plage_qui_commence_la_chaine_ok(self):
        """
        Une plage qui commence à la première vente du lieu n'a pas de vente avant
        elle : elle commence la chaîne (empreinte précédente "", aucun numéro
        précédent). Trois jus, plage [n° 1, n° 3] : aucune anomalie.
        / A range starting at the venue's first sale starts the chain: no anomaly.
        """
        premiere_vente = self._vendre_un_jus_en_especes()
        self._vendre_un_jus_en_especes()
        troisieme_vente = self._vendre_un_jus_en_especes()
        cle_de_l_empreinte = LaboutikConfiguration.get_solo().get_or_create_hmac_key()

        anomalies_sur_la_plage = verifier_chaine_ventes(
            cle_de_l_empreinte,
            numero_de_la_premiere_vente=premiere_vente.numero,
            numero_de_la_derniere_vente=troisieme_vente.numero,
        )

        assert premiere_vente.numero == 1
        assert anomalies_sur_la_plage == []

    def test_integrite_d_une_periode_sans_vente_ok_sans_verification(self):
        """
        Une période sans vente n'a pas de plage : intégrité « OK », aucune vente n'est
        vérifiée. Un jus est vendu puis altéré avant la période : il n'est pas vu.
        / A period without sales has no range: OK, nothing is checked.
        """
        vente = self._vendre_un_jus_en_especes()
        self._alterer_le_reglement(vente)
        heure_d_encaissement = Vente.objects.get(pk=vente.pk).datetime_encaissement
        rapport_d_une_periode_sans_vente = self._rapport(
            debut=heure_d_encaissement + timedelta(seconds=1),
            fin=heure_d_encaissement + timedelta(hours=1),
        )

        en_tete = rapport_d_une_periode_sans_vente.section_en_tete()
        assert en_tete["nombre_de_ventes"] == 0
        assert rapport_d_une_periode_sans_vente.section_integrite() == {
            "statut": "OK",
            "anomalies": [],
        }

    def test_verifier_chaine_ventes_sans_plage_verifie_toute_la_chaine(self):
        """
        `verifier_chaine_ventes` sans plage (ses deux paramètres absents, ou à None)
        vérifie toute la chaîne du lieu, comme ses appelants l'attendent. Trois jus ;
        la vente n° 1 est altérée : l'anomalie est trouvée sans plage, et le résultat
        est le même avec les deux paramètres à None.
        / Without a range, verifier_chaine_ventes checks the whole chain.
        """
        premiere_vente = self._vendre_un_jus_en_especes()
        self._vendre_un_jus_en_especes()
        self._vendre_un_jus_en_especes()
        self._alterer_le_reglement(premiere_vente)
        cle_de_l_empreinte = LaboutikConfiguration.get_solo().get_or_create_hmac_key()

        anomalies_sans_plage = verifier_chaine_ventes(cle_de_l_empreinte)
        anomalies_avec_la_plage_a_none = verifier_chaine_ventes(
            cle_de_l_empreinte,
            numero_de_la_premiere_vente=None,
            numero_de_la_derniere_vente=None,
        )

        assert len(anomalies_sans_plage) == 1
        assert anomalies_sans_plage[0]["numero"] == premiere_vente.numero
        assert anomalies_avec_la_plage_a_none == anomalies_sans_plage

    # ------------------------------------------------------------------
    # Le Z stocké ne garde jamais d'email
    # / The stored Z never keeps an email
    # ------------------------------------------------------------------

    def test_z_stocke_l_identifiant_de_l_operateur_jamais_son_email(self):
        """
        Le Z stocké (scellé, jamais effaçable) ne garde jamais d'email : l'opérateur
        d'une correction y est l'identifiant de l'utilisateur (uuid en texte), None
        s'il n'y en a pas. L'écran retrouve le nom à l'affichage. Deux jus en espèces
        vendus par un opérateur ; le premier corrigé en CB par l'opérateur, le second
        corrigé sans opérateur. Aucun « @ » dans le Z sérialisé.
        / The stored Z never keeps an email: a correction's operator is the user's
        uuid, None without one. No "@" in the serialized Z.
        """
        operateur = self._operateur()
        premier_jus = self._vendre_un_jus_en_especes(operateur=operateur)
        second_jus = self._vendre_un_jus_en_especes(operateur=operateur)
        self._corriger_les_especes_en_cb(premier_jus, operateur)
        self._corriger_les_especes_en_cb(second_jus, None)

        sections_du_z = self._rapport().toutes_les_sections()

        operateurs_des_corrections = []
        for correction in sections_du_z["annexe"]["corrections"]["liste"]:
            operateurs_des_corrections.append(correction["operateur"])
        assert operateurs_des_corrections == [str(operateur.pk), None]
        assert "@" not in json.dumps(sections_du_z)

    # ------------------------------------------------------------------
    # Rapport X : habitus des cartes et opérateurs
    # / X report: card habits and operators
    # ------------------------------------------------------------------

    def test_rapport_x_ajoute_habitus_et_operateurs_hors_z(self):
        """
        Le rapport X (temps réel, jamais stocké) = les sections du Z, plus
        « habitus_cartes » et « operateurs ». Ces deux clés ne sont jamais dans
        `toutes_les_sections()` (le Z stocké). L'intégrité (section 11) est un
        contrôle du Z : elle relit chaque vente de la plage, trop lourd pour l'écran
        temps réel ; le rapport X ne la calcule pas. Les sections communes sont les
        mêmes.
        / The X report = the Z sections without integrity, plus card habits and
        operators; those two keys are never in the stored Z.
        """
        self._vendre_un_jus_en_especes(operateur=self._operateur())
        rapport = self._rapport()

        sections_du_z = rapport.toutes_les_sections()
        rapport_x = rapport.rapport_x()

        assert "habitus_cartes" not in sections_du_z
        assert "operateurs" not in sections_du_z
        assert "integrite" in sections_du_z
        assert "integrite" not in rapport_x
        cles_attendues_du_rapport_x = set(sections_du_z.keys())
        cles_attendues_du_rapport_x.remove("integrite")
        cles_attendues_du_rapport_x.add("habitus_cartes")
        cles_attendues_du_rapport_x.add("operateurs")
        assert set(rapport_x.keys()) == cles_attendues_du_rapport_x
        for nom_de_la_section in cles_attendues_du_rapport_x:
            if nom_de_la_section not in sections_du_z:
                continue
            assert rapport_x[nom_de_la_section] == sections_du_z[nom_de_la_section], (
                nom_de_la_section
            )

    def test_operateurs_ventes_ca_argent(self):
        """
        Rapport X, opérateurs : par opérateur de la vente (clé : identifiant de
        l'utilisateur ; nom : son email, ou « Sans opérateur »), le nombre de ventes,
        le chiffre d'affaires TTC (articles du chiffre d'affaires) et l'argent
        (règlements d'argent au sens strict).
        - opératrice A : un jus 3,50 € en espèces, un jus 3,50 € en CB, une bière
          5,00 € en monnaie locale : 3 ventes, CA 1200, argent 700 (le cashless n'est
          pas de l'argent) ;
        - opérateur B : une recharge 10,00 € en CB : 1 vente, CA 0 (hors chiffre
          d'affaires), argent 1000 ;
        - sans opérateur : un jus 3,50 € en espèces : 1 vente, CA 350, argent 350.
        / X report, operators: number of sales, revenue, money, per sale operator.
        """
        monnaie_locale = self._monnaie(NOM_DE_LA_MONNAIE_LOCALE, Asset.TLF)
        operatrice_a = self._operateur()
        operateur_b = self._operateur()
        tarif_de_la_biere = creer_tarif_vendu(
            nom="Biere", prix_en_euros="5.00", taux_tva="20.00"
        )
        tarif_de_la_recharge = creer_tarif_vendu(
            nom="Recharge",
            prix_en_euros="10.00",
            taux_tva="0.00",
            methode_caisse=Product.RECHARGE_EUROS,
        )

        self._vendre_un_jus_en_especes(operateur=operatrice_a)
        vente_du_jus_en_cb = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            operateur=operatrice_a,
            articles=[
                {
                    "pricesold": self.tarif_du_jus,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 350,
                    "taux_tva": Decimal("20"),
                },
            ],
            reglements=[{"moyen": PaymentMethod.CC, "montant": 350}],
        )
        verifier_egalites(vente_du_jus_en_cb)
        vente_de_la_biere = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            operateur=operatrice_a,
            articles=[
                {
                    "pricesold": tarif_de_la_biere,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 500,
                    "taux_tva": Decimal("20"),
                },
            ],
            reglements=[
                {
                    "moyen": PaymentMethod.LOCAL_EURO,
                    "montant": 500,
                    "asset": monnaie_locale.uuid,
                },
            ],
        )
        verifier_egalites(vente_de_la_biere)

        vente_de_la_recharge = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            operateur=operateur_b,
            articles=[
                {
                    "pricesold": tarif_de_la_recharge,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 1000,
                    "taux_tva": Decimal("0"),
                },
            ],
            reglements=[{"moyen": PaymentMethod.CC, "montant": 1000}],
        )
        verifier_egalites(vente_de_la_recharge)

        self._vendre_un_jus_en_especes()

        # Le libellé « Sans opérateur » est traduit au moment du calcul.
        # / The "no operator" label is translated at computation time.
        with translation.override("fr"):
            operateurs = self._rapport().rapport_x()["operateurs"]

        assert operateurs == {
            str(operatrice_a.pk): {
                "nom": operatrice_a.email,
                "nombre_de_ventes": 3,
                "chiffre_affaires_ttc_en_centimes": 1200,
                "argent_en_centimes": 700,
            },
            str(operateur_b.pk): {
                "nom": operateur_b.email,
                "nombre_de_ventes": 1,
                "chiffre_affaires_ttc_en_centimes": 0,
                "argent_en_centimes": 1000,
            },
            "sans_operateur": {
                "nom": LIBELLE_SANS_OPERATEUR,
                "nombre_de_ventes": 1,
                "chiffre_affaires_ttc_en_centimes": 350,
                "argent_en_centimes": 350,
            },
        }

    def _carte_d_un_client(self, monnaie_locale, solde_en_centimes):
        """
        Une carte NFC dont l'utilisateur a un portefeuille, avec un solde en monnaie
        locale (lu en direct par l'habitus). Les cartes sont dans le schéma `public`
        (tests/PIEGES.md 9.30), créées dans la transaction du test et annulées avec
        elle. `tag_id` et `number` font 8 caractères au plus (tests/PIEGES.md 9.31).
        / An NFC card whose user has a wallet with a local currency balance.
        """
        client = creer_utilisateur()
        portefeuille_du_client = Wallet.objects.create(
            name=f"Portefeuille client rapport unique {identifiant_unique()}"
        )
        client.wallet = portefeuille_du_client
        client.save(update_fields=["wallet"])
        Token.objects.create(
            wallet=portefeuille_du_client,
            asset=monnaie_locale,
            value=solde_en_centimes,
        )
        identifiant_de_la_carte = identifiant_unique().upper()
        return CarteCashless.objects.create(
            tag_id=identifiant_de_la_carte,
            number=identifiant_de_la_carte,
            uuid=uuid.uuid4(),
            user=client,
        )

    def _vente_sur_la_carte(
        self, carte, tarif_vendu, prix_unitaire, taux_tva, reglement
    ):
        """
        Une vente de caisse d'un article, faite avec la carte du client, réglée par le
        règlement donné. Le règlement porte la carte, comme la caisse l'écrit.
        / A one-item register sale made with the customer's card; the payment carries
        the card, like the register writes it.
        """
        reglement_avec_la_carte = dict(reglement)
        reglement_avec_la_carte["carte"] = carte
        vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            carte=carte,
            articles=[
                {
                    "pricesold": tarif_vendu,
                    "quantite": Decimal("1"),
                    "prix_unitaire": prix_unitaire,
                    "taux_tva": Decimal(taux_tva),
                },
            ],
            reglements=[reglement_avec_la_carte],
        )
        verifier_egalites(vente)
        return vente

    def test_habitus_cartes_en_centimes_entiers(self):
        """
        Rapport X, habitus des cartes. Les cartes sont celles des ventes de la période
        (`Vente.carte`). Dépense d'une carte = Σ de ses règlements cashless des ventes
        VENTE ; recharge d'une carte = Σ net de ses recharges encaissées ; reste sur
        carte = solde en monnaie locale, lu en direct. Moyennes et médianes en centimes
        entiers, arrondies demi-haut.
        - carte A : recharge 20,00 € en CB ; une bière 5,00 € et un jus 3,50 € en
          monnaie locale : dépense 850, recharge 2000 ; solde 11,50 € ;
        - carte B : recharge 10,01 € en CB ; un sirop 1,51 € en monnaie locale :
          dépense 151, recharge 1001 ; solde 0,01 € ;
        - un jus en espèces sans carte (hors habitus) ; une adhésion créée pendant la
          période (un nouveau membre).
        Nombre de cartes 2 ; total 1001 ; panier moyen 1001 / 2 cartes qui dépensent
        = 500,5 → 501 ;
        dépense médiane (850 + 151) / 2 = 500,5 → 501 ; recharge médiane
        (2000 + 1001) / 2 = 1500,5 → 1501 ; reste moyen et médian
        (1150 + 1) / 2 = 575,5 → 576.
        / Card habits, as whole cents rounded half-up.
        """
        monnaie_locale = self._monnaie(NOM_DE_LA_MONNAIE_LOCALE, Asset.TLF)
        carte_a = self._carte_d_un_client(monnaie_locale, 1150)
        carte_b = self._carte_d_un_client(monnaie_locale, 1)
        tarif_de_la_recharge = creer_tarif_vendu(
            nom="Recharge",
            prix_en_euros="20.00",
            taux_tva="0.00",
            methode_caisse=Product.RECHARGE_EUROS,
        )
        tarif_de_la_biere = creer_tarif_vendu(
            nom="Biere", prix_en_euros="5.00", taux_tva="20.00"
        )
        tarif_du_sirop = creer_tarif_vendu(
            nom="Sirop", prix_en_euros="1.51", taux_tva="20.00"
        )

        self._vente_sur_la_carte(
            carte_a,
            tarif_de_la_recharge,
            2000,
            "0",
            {"moyen": PaymentMethod.CC, "montant": 2000},
        )
        self._vente_sur_la_carte(
            carte_a,
            tarif_de_la_biere,
            500,
            "20",
            {
                "moyen": PaymentMethod.LOCAL_EURO,
                "montant": 500,
                "asset": monnaie_locale.uuid,
            },
        )
        self._vente_sur_la_carte(
            carte_a,
            self.tarif_du_jus,
            350,
            "20",
            {
                "moyen": PaymentMethod.LOCAL_EURO,
                "montant": 350,
                "asset": monnaie_locale.uuid,
            },
        )
        self._vente_sur_la_carte(
            carte_b,
            tarif_de_la_recharge,
            1001,
            "0",
            {"moyen": PaymentMethod.CC, "montant": 1001},
        )
        self._vente_sur_la_carte(
            carte_b,
            tarif_du_sirop,
            151,
            "20",
            {
                "moyen": PaymentMethod.LOCAL_EURO,
                "montant": 151,
                "asset": monnaie_locale.uuid,
            },
        )
        self._vendre_un_jus_en_especes()
        creer_une_adhesion_active(creer_utilisateur(), creer_adhesion())

        habitus_cartes = self._rapport().rapport_x()["habitus_cartes"]

        assert habitus_cartes == {
            "nombre_de_cartes": 2,
            "total_des_depenses_en_centimes": 1001,
            "panier_moyen_en_centimes": 501,
            "depense_mediane_en_centimes": 501,
            "recharge_mediane_en_centimes": 1501,
            "reste_moyen_sur_carte_en_centimes": 576,
            "reste_median_sur_carte_en_centimes": 576,
            "nouveaux_membres": 1,
        }

        # Aucun nombre à virgule : un `float` n'est jamais un montant du rapport.
        # / No float: a float is never an amount of the report.
        for nom_de_l_indicateur, valeur in habitus_cartes.items():
            assert type(valeur) is int, nom_de_l_indicateur

    def test_habitus_depenses_sur_les_seules_cartes_qui_depensent(self):
        """
        Rapport X, habitus : une carte qui n'a que rechargé compte parmi les cartes,
        mais n'entre ni dans la médiane des dépenses ni dans la division du panier
        moyen.
        - carte A : recharge 20,00 € en CB, aucune dépense ;
        - carte B : une bière 3,00 € en monnaie locale (dépense 300) ;
        - carte C : une bière 5,01 € en monnaie locale (dépense 501).
        Nombre de cartes 3 ; total 801 ; panier moyen 801 / 2 = 400,5 → 401 ;
        dépense médiane (300 + 501) / 2 = 400,5 → 401. (Avec la carte A à 0 : panier
        801 / 3 = 267, médiane 300.)
        / A card that only topped up counts as a card, but neither in the spending
        median nor in the average basket division.
        """
        monnaie_locale = self._monnaie(NOM_DE_LA_MONNAIE_LOCALE, Asset.TLF)
        carte_qui_recharge = self._carte_d_un_client(monnaie_locale, 0)
        premiere_carte_qui_depense = self._carte_d_un_client(monnaie_locale, 0)
        seconde_carte_qui_depense = self._carte_d_un_client(monnaie_locale, 0)
        tarif_de_la_recharge = creer_tarif_vendu(
            nom="Recharge",
            prix_en_euros="20.00",
            taux_tva="0.00",
            methode_caisse=Product.RECHARGE_EUROS,
        )
        tarif_de_la_biere = creer_tarif_vendu(
            nom="Biere", prix_en_euros="3.00", taux_tva="20.00"
        )

        self._vente_sur_la_carte(
            carte_qui_recharge,
            tarif_de_la_recharge,
            2000,
            "0",
            {"moyen": PaymentMethod.CC, "montant": 2000},
        )
        self._vente_sur_la_carte(
            premiere_carte_qui_depense,
            tarif_de_la_biere,
            300,
            "20",
            {
                "moyen": PaymentMethod.LOCAL_EURO,
                "montant": 300,
                "asset": monnaie_locale.uuid,
            },
        )
        self._vente_sur_la_carte(
            seconde_carte_qui_depense,
            tarif_de_la_biere,
            501,
            "20",
            {
                "moyen": PaymentMethod.LOCAL_EURO,
                "montant": 501,
                "asset": monnaie_locale.uuid,
            },
        )

        habitus_cartes = self._rapport().rapport_x()["habitus_cartes"]

        assert habitus_cartes["nombre_de_cartes"] == 3
        assert habitus_cartes["total_des_depenses_en_centimes"] == 801
        assert habitus_cartes["panier_moyen_en_centimes"] == 401
        assert habitus_cartes["depense_mediane_en_centimes"] == 401

    def test_habitus_recharge_cadeau_seule_hors_de_la_mediane_des_recharges(self):
        """
        Rapport X, habitus : une recharge cadeau n'encaisse rien (net 0). Une carte
        qui n'a reçu qu'une recharge cadeau n'entre pas dans la médiane des recharges.
        - carte A : recharge cadeau 10,00 € (entièrement offerte) ;
        - carte B : recharge 10,00 € en CB ;
        - carte C : recharge 20,01 € en CB.
        Recharge médiane (1000 + 2001) / 2 = 1500,5 → 1501. (Avec la carte A à 0 :
        médiane de 0, 1000, 2001 = 1000.)
        / A card that only got a gift top-up is not in the top-up median.
        """
        monnaie_locale = self._monnaie(NOM_DE_LA_MONNAIE_LOCALE, Asset.TLF)
        carte_de_la_recharge_cadeau = self._carte_d_un_client(monnaie_locale, 0)
        premiere_carte_rechargee = self._carte_d_un_client(monnaie_locale, 0)
        seconde_carte_rechargee = self._carte_d_un_client(monnaie_locale, 0)
        tarif_de_la_recharge_cadeau = creer_tarif_vendu(
            nom="Recharge cadeau",
            prix_en_euros="10.00",
            taux_tva="0.00",
            methode_caisse=Product.RECHARGE_CADEAU,
        )
        tarif_de_la_recharge = creer_tarif_vendu(
            nom="Recharge",
            prix_en_euros="10.00",
            taux_tva="0.00",
            methode_caisse=Product.RECHARGE_EUROS,
        )

        # La recharge cadeau : le service pose la part offerte et le règlement FREE.
        # / The gift top-up: the service sets the offered part and the FREE payment.
        vente_de_la_recharge_cadeau = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            carte=carte_de_la_recharge_cadeau,
            articles=[
                {
                    "pricesold": tarif_de_la_recharge_cadeau,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 1000,
                    "taux_tva": Decimal("0"),
                    "offert_en_totalite": True,
                },
            ],
        )
        verifier_egalites(vente_de_la_recharge_cadeau)
        self._vente_sur_la_carte(
            premiere_carte_rechargee,
            tarif_de_la_recharge,
            1000,
            "0",
            {"moyen": PaymentMethod.CC, "montant": 1000},
        )
        self._vente_sur_la_carte(
            seconde_carte_rechargee,
            tarif_de_la_recharge,
            2001,
            "0",
            {"moyen": PaymentMethod.CC, "montant": 2001},
        )

        habitus_cartes = self._rapport().rapport_x()["habitus_cartes"]

        assert habitus_cartes["nombre_de_cartes"] == 3
        assert habitus_cartes["recharge_mediane_en_centimes"] == 1501

    def test_habitus_nouveau_membre_a_la_borne_de_fin_hors_periode(self):
        """
        Rapport X, habitus : les nouveaux membres suivent la même borne que les ventes,
        `debut <= date_added < fin`. Une adhésion datée pile du début est comptée ;
        une adhésion datée pile de la fin ne l'est pas (elle est dans la période
        suivante). `date_added` est posée à la création (`auto_now_add`) : l'heure est
        posée ensuite par `update()` (tests/PIEGES.md 13.19). Nouveaux membres : 1.
        / New members follow the sales bound: one at the start counts, one exactly at
        the end does not.
        """
        adhesion = creer_adhesion()
        adhesion_au_debut = creer_une_adhesion_active(creer_utilisateur(), adhesion)
        adhesion_a_la_fin = creer_une_adhesion_active(creer_utilisateur(), adhesion)
        Membership.objects.filter(pk=adhesion_au_debut.pk).update(
            date_added=self.debut_de_la_periode
        )
        Membership.objects.filter(pk=adhesion_a_la_fin.pk).update(
            date_added=self.fin_de_la_periode
        )

        habitus_cartes = self._rapport().rapport_x()["habitus_cartes"]

        assert habitus_cartes["nouveaux_membres"] == 1

    def test_habitus_paiement_a_deux_cartes_chaque_carte_compte_sa_depense(self):
        """
        Rapport X, habitus : les cartes viennent de la vente (`Vente.carte`) ET des
        règlements cashless (`Reglement.carte`), chacune comptée une fois ; la dépense
        est rangée par la carte du RÈGLEMENT. Une bière 8,01 € payée par deux cartes :
        la carte A (celle de la vente) 3,00 €, la carte B 5,01 €, en monnaie locale.
        Soldes restants : A 1,00 €, B 3,01 €.
        Nombre de cartes 2 ; dépenses A 300, B 501 ; total 801 ; panier moyen
        801 / 2 = 400,5 → 401 ; dépense médiane (300 + 501) / 2 = 400,5 → 401 ;
        reste moyen et médian (100 + 301) / 2 = 200,5 → 201. (Par la seule carte de la
        vente : 1 carte, une dépense de 801, reste 100.)
        / Cards come from the sale and from cashless payments, each counted once;
        spending is grouped by the payment's card.
        """
        monnaie_locale = self._monnaie(NOM_DE_LA_MONNAIE_LOCALE, Asset.TLF)
        carte_a = self._carte_d_un_client(monnaie_locale, 100)
        carte_b = self._carte_d_un_client(monnaie_locale, 301)
        tarif_de_la_biere = creer_tarif_vendu(
            nom="Biere", prix_en_euros="8.01", taux_tva="20.00"
        )
        vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            carte=carte_a,
            articles=[
                {
                    "pricesold": tarif_de_la_biere,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 801,
                    "taux_tva": Decimal("20"),
                },
            ],
            reglements=[
                {
                    "moyen": PaymentMethod.LOCAL_EURO,
                    "montant": 300,
                    "asset": monnaie_locale.uuid,
                    "carte": carte_a,
                },
                {
                    "moyen": PaymentMethod.LOCAL_EURO,
                    "montant": 501,
                    "asset": monnaie_locale.uuid,
                    "carte": carte_b,
                },
            ],
        )
        verifier_egalites(vente)

        habitus_cartes = self._rapport().rapport_x()["habitus_cartes"]

        assert habitus_cartes["nombre_de_cartes"] == 2
        assert habitus_cartes["total_des_depenses_en_centimes"] == 801
        assert habitus_cartes["panier_moyen_en_centimes"] == 401
        assert habitus_cartes["depense_mediane_en_centimes"] == 401
        assert habitus_cartes["reste_moyen_sur_carte_en_centimes"] == 201
        assert habitus_cartes["reste_median_sur_carte_en_centimes"] == 201

    def test_habitus_reste_sur_carte_monnaie_du_lieu_et_moyenne_par_carte(self):
        """
        Rapport X, habitus : le reste sur carte ne lit que les monnaies locales DU
        LIEU (créées par le lieu), et la moyenne se fait PAR CARTE (somme des soldes
        d'une carte, puis moyenne sur les cartes).
        - carte A : 10,00 € dans la monnaie locale du lieu et 5,00 € dans une seconde
          monnaie locale du lieu : 1500 ;
        - carte B : 0,01 € dans la monnaie locale du lieu, et 50,00 € dans la monnaie
          locale d'un autre lieu (pas lue) : 1.
        Chaque carte a une dépense de 1,00 € (elle est dans les ventes de la période).
        Reste moyen et médian (1500 + 1) / 2 = 750,5 → 751. (Par solde : 1501 / 3 =
        500 ; avec l'autre lieu : 3251.)
        / Remaining balance: the venue's local currencies only, averaged per card.
        """
        monnaie_locale = self._monnaie(NOM_DE_LA_MONNAIE_LOCALE, Asset.TLF)
        seconde_monnaie_locale = self._monnaie(
            "Seconde monnaie locale rapport unique", Asset.TLF
        )
        autre_lieu = Client.objects.exclude(pk=self.tenant.pk).first()
        monnaie_locale_d_un_autre_lieu = Asset.objects.create(
            name="Monnaie locale d'un autre lieu rapport unique",
            currency_code="EUR",
            category=Asset.TLF,
            tenant_origin=autre_lieu,
            wallet_origin=Wallet.objects.create(
                name=f"Portefeuille autre lieu {identifiant_unique()}"
            ),
        )
        carte_a = self._carte_d_un_client(monnaie_locale, 1000)
        Token.objects.create(
            wallet=carte_a.user.wallet, asset=seconde_monnaie_locale, value=500
        )
        carte_b = self._carte_d_un_client(monnaie_locale, 1)
        Token.objects.create(
            wallet=carte_b.user.wallet,
            asset=monnaie_locale_d_un_autre_lieu,
            value=5000,
        )
        tarif_du_sirop = creer_tarif_vendu(
            nom="Sirop", prix_en_euros="1.00", taux_tva="20.00"
        )
        for carte in [carte_a, carte_b]:
            self._vente_sur_la_carte(
                carte,
                tarif_du_sirop,
                100,
                "20",
                {
                    "moyen": PaymentMethod.LOCAL_EURO,
                    "montant": 100,
                    "asset": monnaie_locale.uuid,
                },
            )

        habitus_cartes = self._rapport().rapport_x()["habitus_cartes"]

        assert habitus_cartes["reste_moyen_sur_carte_en_centimes"] == 751
        assert habitus_cartes["reste_median_sur_carte_en_centimes"] == 751

    # ------------------------------------------------------------------
    # Le dictionnaire complet
    # / The full dictionary
    # ------------------------------------------------------------------

    def test_rapport_serialisable_en_json(self):
        """
        Le dictionnaire de toutes les sections se sérialise en JSON sans aide
        (`json.dumps` sans `default=`) : ni `Decimal`, ni uuid, ni date non convertis.
        Il est stocké tel quel dans `ClotureCaisse.rapport_json`. Le scénario remplit
        les sections : le fil rouge (monnaie locale), un billet Stripe avec un écart et
        son avoir admin, une vente en points, une correction.
        / The full dictionary serializes to JSON without help.
        """
        monnaie_locale = self._monnaie(NOM_DE_LA_MONNAIE_LOCALE, Asset.TLF)
        points = self._monnaie(NOM_DES_POINTS, Asset.FID)
        self._vente_du_fil_rouge(monnaie_locale)
        billet = self._billet_vendu_en_ligne_par_stripe(3500, ecart_en_centimes=3)
        self._avoir_admin_d_une_ligne_stripe(billet)
        self._vente_en_points(points, 500)
        vente_d_origine = self._vendre_un_jus_en_especes()
        self._corriger_les_especes_en_cb(vente_d_origine, self._operateur())

        toutes_les_sections = self._rapport().toutes_les_sections()

        assert set(toutes_les_sections.keys()) == {
            "en_tete",
            "chiffre_affaires",
            "reglements",
            "caisse_especes",
            "reconciliation",
            "offerts",
            "annexe",
            "points",
            "marge_brute",
            "detail",
            "integrite",
        }

        # `json.dumps` lève TypeError sur un Decimal, un UUID ou une date.
        # / json.dumps raises TypeError on a Decimal, a UUID or a date.
        rapport_en_json = json.dumps(toutes_les_sections)
        assert json.loads(rapport_en_json) == toutes_les_sections

    def test_aucun_amount_fois_qty_dans_le_rapport(self):
        """
        Fiche F §6, test 26 : le rapport, la ventilation comptable et le FEC ne font
        que des sommes de champs entiers. Leurs sources (`comptabilite/rapport.py`,
        `comptabilite/ventilation.py`, `comptabilite/fec.py`) ne contiennent jamais
        le prix unitaire
        historique (`amount`), une multiplication par la quantité, un arrondi de la
        base (`Round(`) ni un nombre à virgule (`float(`).
        / The report and breakdown sources never contain `amount`, a multiplication by
        the quantity, `Round(` or `float(`.
        """
        dossier_de_la_comptabilite = Path(comptabilite.rapport.__file__).parent
        fichiers_verifies = [
            dossier_de_la_comptabilite / "rapport.py",
            dossier_de_la_comptabilite / "ventilation.py",
            dossier_de_la_comptabilite / "fec.py",
        ]

        textes_interdits_trouves = []
        for fichier_verifie in fichiers_verifies:
            source_du_fichier = fichier_verifie.read_text(encoding="utf-8")
            for texte_interdit in TEXTES_INTERDITS_DANS_LE_RAPPORT:
                if texte_interdit in source_du_fichier:
                    textes_interdits_trouves.append(
                        f"{fichier_verifie.name} : {texte_interdit}"
                    )

        assert textes_interdits_trouves == []
