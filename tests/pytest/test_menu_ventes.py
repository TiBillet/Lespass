"""
Les écrans Ventes de la caisse : liste des ventes, détail d'une vente, écran de
correction du moyen, historiques du récapitulatif en cours.
/ The register's Sales screens: sales list, sale detail, payment method correction
screen, histories of the current recap.

LOCALISATION : tests/pytest/test_menu_ventes.py

RÈGLES MÉTIER TESTÉES
- La liste des ventes montre UNE ligne par vente réglée du service en cours, faite
  sur un point de vente du lieu (caisse ou tireuse), jamais une vente en ligne. Elle
  montre toutes les opérations numérotées de ces points de vente, avec un badge de
  nature : « Vente », « Avoir », « Correction », « Carte vidée ». La plus récente
  d'abord, 20 par page.
- Chaque ligne : numéro de la vente, heure locale du lieu, badge de nature, point de
  vente, total de la vente, moyens de paiement en clair lus dans ses règlements
  (« 5,50 € Carte bancaire + 5,00 € Monnaie locale menu ventes » : un moyen d'argent
  par son nom, un règlement cashless par le nom de sa monnaie, dans l'ordre de
  `comptabilite/presentation.py`, le comptoir d'abord, le cashless ensuite),
  nombre d'articles (quantités réelles). Les montants s'écrivent à la française
  (`euros_a_la_francaise`).
- Le filtre par moyen garde les ventes qui ont AU MOINS UN RÈGLEMENT de ce moyen. Le
  moyen écrit sur une ligne d'article ne compte pas.
- Le nombre de requêtes de la liste ne dépend pas du nombre de ventes.
- Le détail d'une vente s'ouvre par l'uuid de la VENTE : ses articles avec leur
  quantité réelle (un article payé avec deux moyens reste UN article), prix unitaire,
  part offerte et total ; ses règlements (moyen, monnaie, montant) ; un lien vers la
  vente liée (avoir, correction) ; son statut. Un bouton « Corriger » par moyen
  corrigeable (espèces, CB, chèque) qui a encore de l'argent dans les règlements
  nets de la vente : le refus vient de `raison_du_refus_de_correction(vente,
  moyen)`. Le bouton transmet une ligne de la vente et le moyen corrigé. Une vente
  en attente s'affiche aussi, avec son statut, sans bouton « Corriger ».
- L'écran « corriger le moyen » affiche le net du moyen à corriger (règlements de
  la vente et de ses corrections), pas le prix d'une part d'article.
- L'écran Ventes (récapitulatif en cours) et ses historiques (par article, synthèse
  par moyen) lisent le rapport des ventes du service (`RapportDesVentes`) : toutes
  origines, ventes en ligne comprises. Le rapport complet reste dans l'admin.
/ One row per settled sale made on a point of sale of the venue, with a nature badge;
payment methods read from the payments; filter on payments; constant query count;
detail by sale uuid with real quantities and payments; correction screen shows the
payment amount; recap histories read the single sales report.

SCHÉMA DÉDIÉ
Le service en cours commence à la fin de la dernière clôture journalière (ou à la
première vente réglée du lieu) : en base partagée, il dépendrait de l'état de la base
de dev. Ici, le lieu ne contient que les ventes du test (`FastTenantTestCase`), et
chaque test annule sa transaction. Les ventes sont écrites PAR LE SERVICE DE VENTE
(`fabriques_vente.py`, `BaseBillet/services_vente.py`), la correction par la vraie
route de la caisse, la J par la vraie tâche.
/ Dedicated schema; sales written by the sale service; correction through the real
route; J through the real task.

D'OÙ VIENNENT LES VALEURS ATTENDUES (calculées à la main)
- Fil rouge du chantier : 3 jus à 3,50 € = 10,50 €, payés 5,00 € en monnaie locale
  et 5,50 € par carte bancaire. La caisse écrit deux « parts » de l'article : monnaie
  locale 350 × 1,428571 → 500 imposés, carte bancaire 350 × 1,571429 → 550 imposés.
  Quantité réelle 1,428571 + 1,571429 = 3 ; total 500 + 550 = 1050 → « 10,50 € ».
  Règlements : monnaie locale 500 (« 5,00 € »), carte bancaire 550 (« 5,50 € »).
- Pinte 5,00 € ; demi 3,00 € ; 3 pintes + 2 demis = 1500 + 600 = 2100 → 5 articles.
- Billet en ligne 10,00 €, réglé par Stripe (1000).
- Total du fil rouge et du billet en ligne : 1050 + 1000 = 2050 → « 20,50 € » ; le
  billet en ligne n'a pas de point de vente (« Sans point de vente », 10,00 €).
- Vrac : 350 g de cacahuètes à 12,00 €/kg = 350 × 0,012 = 4,20 € (prix de la ligne
  420, poids 350).
- Les libellés sont ceux de la caisse en français (« Carte bancaire ») ; un règlement
  cashless porte le nom de la monnaie créée par le test (« Monnaie locale menu
  ventes ») ; les badges de nature sont écrits ici.
/ Hand-computed expected values: the project's running example (3 juices, 10.50 €,
5.00 € local currency + 5.50 € card), pints and halves, an online ticket, bulk.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-G-lecteurs.md (§3, §5
tests 7, 8 et 9).

Lancer / Run : make test ARGS="tests/pytest/test_menu_ventes.py"
"""

import sys

# Le code Django vit dans /DjangoFiles a l'interieur du conteneur.
# / Django code lives in /DjangoFiles inside the container.
sys.path.insert(0, "/DjangoFiles")

import django  # noqa: E402

django.setup()

import re  # noqa: E402
import uuid as uuid_module  # noqa: E402
from datetime import time, timedelta  # noqa: E402
from decimal import Decimal  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

from django.db import connection  # noqa: E402
from django.utils import timezone  # noqa: E402
from django_tenants.test.cases import FastTenantTestCase  # noqa: E402
from django_tenants.test.client import TenantClient  # noqa: E402

import comptabilite.tasks  # noqa: E402
from AuthBillet.models import TibilletUser, Wallet  # noqa: E402
from BaseBillet.models import (  # noqa: E402
    Configuration,
    Event,
    LigneArticle,
    PaymentMethod,
    Price,
    PriceSold,
    Product,
    ProductSold,
    SaleOrigin,
)
from BaseBillet.models_vente import Vente  # noqa: E402
from BaseBillet.services_vente import (  # noqa: E402
    ajouter_article,
    ajouter_reglement,
    encaisser_vente,
    ouvrir_vente,
)
from comptabilite.models import ClotureCaisse  # noqa: E402
from fabriques_ecran import (  # noqa: E402
    attributs_des_elements,
    euros,
    lire_l_element,
    texte_sans_espaces_en_trop,
    textes_des_elements,
)
from fabriques_vente import (  # noqa: E402
    creer_tarif_vendu,
    fabriquer_vente_encaissee,
    verifier_egalites,
)
from fabriques_panier import taches_celery_enregistrees  # noqa: E402
from fedow_core.models import Asset  # noqa: E402
from fedow_core.services import AssetService  # noqa: E402
from fedow_public.models import AssetFedowPublic  # noqa: E402
from inventaire.models import Stock, UniteStock  # noqa: E402
from laboutik.models import LaboutikConfiguration, PointDeVente  # noqa: E402

# Adresses de la caisse (laboutik/urls.py). Le détail d'une vente s'ouvre par
# l'uuid de la vente : DEBUT_DE_L_URL_DU_DETAIL_D_UNE_VENTE + uuid + "/".
# / Register addresses. The sale detail opens with the sale's uuid.
URL_DE_LA_LISTE_DES_VENTES = "/laboutik/caisse/liste-ventes/"
DEBUT_DE_L_URL_DU_DETAIL_D_UNE_VENTE = "/laboutik/caisse/detail-vente/"
URL_DU_RECAP_EN_COURS = "/laboutik/caisse/recap-en-cours/"
URL_DU_FORMULAIRE_DE_CORRECTION = "/laboutik/paiement/formulaire_correction/"
URL_DE_LA_CORRECTION_DU_MOYEN = "/laboutik/paiement/corriger_moyen_paiement/"

# Le fuseau du lieu de test : les heures de la liste s'écrivent dans ce fuseau, et non
# en temps universel (le fuseau du serveur).
# / The test venue's time zone: list hours are written in it, not in UTC.
FUSEAU_DU_LIEU = "Europe/Paris"

# Les badges de nature, écrits à la main.
# / The nature badges, hand-written.
BADGE_VENTE = "Vente"
BADGE_AVOIR = "Avoir"
BADGE_CORRECTION = "Correction"
BADGE_CARTE_VIDEE = "Carte vidée"

# Le libellé d'un moyen d'argent, en français, écrit à la main. Un règlement cashless
# s'écrit par le nom de sa monnaie, celle créée par le test.
# / A money method label in French, hand-written. A cashless payment is written by
# its currency's name, the one created by the test.
LIBELLE_CARTE_BANCAIRE = "Carte bancaire"
NOM_DE_LA_MONNAIE_LOCALE = "Monnaie locale menu ventes"

# L'ancien titre de l'historique « par moyen », qui lisait les lignes de la caisse.
# / The old title of the "by method" history, which read register lines.
ANCIEN_TITRE_DES_LIGNES_DE_CAISSE = (
    "Lignes de caisse (hors ventes en ligne, recharges comprises)"
)

# Paramètres de test : faux tag de carte primaire et type d'app.
# / Test params: fake primary card tag and app type.
TAG_ID_CM_DE_TEST = "A49E8E2A"
TYPE_APP_DE_TEST = "sunmi"

# Une page de la liste des ventes.
# / One page of the sales list.
NOMBRE_DE_VENTES_PAR_PAGE = 20


def chiffres_du_texte(texte):
    """
    Les seuls chiffres d'un texte : « n° 12 » → « 12 ».
    / Only the digits of a text.
    """
    return re.sub(r"\D", "", texte)


def montant_attendu(nombre_en_texte):
    """
    Un montant attendu, écrit à la main, espaces ramenées à une seule :
    « 10,50 » → « 10,50 € ». Les textes lus dans la page le sont aussi.
    / An expected hand-written amount, spaces collapsed like the page texts.
    """
    return texte_sans_espaces_en_trop(euros(nombre_en_texte))


class CompteurDeRequetesSql:
    """
    Compte les requêtes SQL envoyées par la connexion, pendant une requête du client
    de test. Branché par `connection.execute_wrapper` : `CaptureQueriesContext` ne
    voit pas les requêtes faites pendant une requête du client (le signal
    `request_started` vide son journal).
    / Counts SQL queries through connection.execute_wrapper (CaptureQueriesContext
    misses the queries made during a test client request).
    """

    def __init__(self):
        self.nombre_de_requetes = 0

    def __call__(self, execute, sql, params, many, context):
        self.nombre_de_requetes += 1
        return execute(sql, params, many, context)


class TestEcransVentesSurLesVentes(FastTenantTestCase):
    """
    Les écrans Ventes de la caisse lus sur les ventes (`Vente`, `Reglement`).
    / The register's Sales screens read on the sales.
    """

    @classmethod
    def get_test_schema_name(cls):
        return "test_menu_ventes"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-menu-ventes.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        """`Client.name` est unique et obligatoire. / Client.name is unique."""
        tenant.name = "Test menu ventes"

    def setUp(self):
        """
        Le lieu de test : singleton de caisse, configuration (caisse active, Paris,
        aucun e-mail de rapport), un comptoir et une tireuse, les articles, une
        monnaie locale, un administrateur connecté à la caisse.
        / The test venue: register singleton, configuration, a counter and a tap,
        items, a local currency, a logged-in admin.
        """
        # Le rollback du test précédent a rendu le `search_path` au public.
        # / The previous test's rollback returned the search_path to public.
        connection.set_tenant(self.tenant)

        # Le singleton de la caisse porte la clé des empreintes (tests/PIEGES.md 9.86).
        # / The register singleton carries the fingerprint key.
        LaboutikConfiguration.get_solo().save()

        # Les routes de la caisse sont gardées par `module_caisse`, qui exige
        # `module_monnaie_locale`. Toutes les valeurs sont écrites ici : le cache de
        # la configuration garde celles du test précédent.
        # / Register routes need module_caisse. Every value is written here.
        configuration = Configuration.get_solo()
        configuration.module_monnaie_locale = True
        configuration.module_caisse = True
        configuration.fuseau_horaire = FUSEAU_DU_LIEU
        configuration.heure_de_fermeture = time(2, 0)
        configuration.rapport_emails = ""
        configuration.save()

        self.comptoir = PointDeVente.objects.create(
            name="Comptoir menu ventes",
            comportement=PointDeVente.DIRECT,
            service_direct=True,
            accepte_especes=True,
            accepte_carte_bancaire=True,
            accepte_cheque=True,
        )
        self.point_de_vente_de_la_tireuse = PointDeVente.objects.create(
            name="Tireuse menu ventes",
            comportement=PointDeVente.DIRECT,
            service_direct=True,
        )

        self.tarif_du_jus = creer_tarif_vendu(
            nom="Jus", prix_en_euros="3.50", taux_tva="20.00",
        )
        self.tarif_de_la_pinte = creer_tarif_vendu(
            nom="Pinte", prix_en_euros="5.00", taux_tva="20.00",
        )
        self.tarif_du_demi = creer_tarif_vendu(
            nom="Demi", prix_en_euros="3.00", taux_tva="20.00",
        )
        self.tarif_de_la_consigne = creer_tarif_vendu(
            nom="Consigne", prix_en_euros="1.00", taux_tva="20.00",
        )
        self.tarif_de_la_biere_tiree = creer_tarif_vendu(
            nom="Biere tiree", prix_en_euros="4.50", taux_tva="20.00",
        )
        self.tarif_du_billet_en_ligne = creer_tarif_vendu(
            nom="Billet en ligne", prix_en_euros="10.00", taux_tva="20.00",
        )

        # La monnaie locale du lieu (`fedow_core`, schéma public) : annulée avec le
        # test.
        # / The venue's local currency (public schema): rolled back with the test.
        portefeuille_du_lieu = Wallet.objects.create(
            origin=self.tenant, name="Portefeuille du lieu menu ventes",
        )
        self.monnaie_locale = AssetService.creer_asset(
            tenant=self.tenant,
            name=NOM_DE_LA_MONNAIE_LOCALE,
            category=Asset.TLF,
            currency_code="EUR",
            wallet_origin=portefeuille_du_lieu,
        )

        # `TibilletUser` vit dans le schéma public ; il est annulé avec le test.
        # / TibilletUser lives in the public schema; rolled back with the test.
        self.administrateur_du_lieu, _utilisateur_cree = (
            TibilletUser.objects.get_or_create(
                email="admin-test-menu-ventes@tibillet.localhost",
                defaults={
                    "username": "admin-test-menu-ventes@tibillet.localhost",
                    "is_staff": True,
                    "is_active": True,
                },
            )
        )
        self.administrateur_du_lieu.client_admin.add(self.tenant)

        # La caisse répond en français : les libellés attendus le sont.
        # / The register answers in French, like the expected labels.
        self.client_du_caissier = TenantClient(self.tenant, HTTP_ACCEPT_LANGUAGE="fr")
        self.client_du_caissier.force_login(self.administrateur_du_lieu)

    # ------------------------------------------------------------------
    # Outils du test : les ventes
    # / Test helpers: the sales
    # ------------------------------------------------------------------

    def _vendre_au_comptoir_en_especes(self, articles_vendus, avec_identifiant=True):
        """
        Une vente de caisse réglée en espèces, au comptoir : un article par couple
        (tarif vendu, prix unitaire en centimes, quantité). Avec `avec_identifiant`,
        toutes les lignes portent le même identifiant de paiement, comme la caisse
        l'écrit ; sans, elles n'en ont pas (lignes d'une vente sans identifiant).
        Rend la vente.
        / A settled cash register sale at the counter. Returns the sale.
        """
        identifiant_du_paiement = None
        if avec_identifiant:
            identifiant_du_paiement = uuid_module.uuid4()

        articles = []
        montant_total = 0
        for tarif_vendu, prix_unitaire, quantite in articles_vendus:
            articles.append({
                "pricesold": tarif_vendu,
                "quantite": Decimal(quantite),
                "prix_unitaire": prix_unitaire,
                "taux_tva": Decimal("20"),
                "payment_method": PaymentMethod.CASH,
                "status": LigneArticle.VALID,
                "uuid_transaction": identifiant_du_paiement,
                "point_de_vente": self.comptoir,
            })
            montant_total += prix_unitaire * quantite

        vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            point_de_vente=self.comptoir,
            operateur=self.administrateur_du_lieu,
            articles=articles,
            reglements=[{"moyen": PaymentMethod.CASH, "montant": montant_total}],
        )
        verifier_egalites(vente)
        return vente

    def _vendre_une_pinte_en_especes(self):
        """Une pinte à 5,00 € payée en espèces. / One cash pint."""
        return self._vendre_au_comptoir_en_especes([(self.tarif_de_la_pinte, 500, 1)])

    def _vendre_trois_jus_en_monnaie_locale_et_carte_bancaire(self):
        """
        Le fil rouge : trois jus à 3,50 € (10,50 €), payés 5,00 € en monnaie locale
        et 5,50 € par carte bancaire. La caisse écrit deux « parts » de l'article,
        chacune avec son argent réel, sur le même identifiant de paiement.
        Rend la vente.
        / The running example: two parts of the item, one payment id. Returns the sale.
        """
        identifiant_du_paiement = uuid_module.uuid4()
        vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            point_de_vente=self.comptoir,
            operateur=self.administrateur_du_lieu,
            articles=[
                {
                    "pricesold": self.tarif_du_jus,
                    "quantite": Decimal("1.428571"),
                    "prix_unitaire": 350,
                    "taux_tva": Decimal("20"),
                    "total_catalogue_impose": 500,
                    "payment_method": PaymentMethod.LOCAL_EURO,
                    "asset": self.monnaie_locale.uuid,
                    "status": LigneArticle.VALID,
                    "uuid_transaction": identifiant_du_paiement,
                    "point_de_vente": self.comptoir,
                },
                {
                    "pricesold": self.tarif_du_jus,
                    "quantite": Decimal("1.571429"),
                    "prix_unitaire": 350,
                    "taux_tva": Decimal("20"),
                    "total_catalogue_impose": 550,
                    "payment_method": PaymentMethod.CC,
                    "status": LigneArticle.VALID,
                    "uuid_transaction": identifiant_du_paiement,
                    "point_de_vente": self.comptoir,
                },
            ],
            reglements=[
                {
                    "moyen": PaymentMethod.LOCAL_EURO,
                    "montant": 500,
                    "asset": self.monnaie_locale.uuid,
                },
                {"moyen": PaymentMethod.CC, "montant": 550},
            ],
        )
        verifier_egalites(vente)
        return vente

    def _vendre_a_la_tireuse(self):
        """
        Une bière tirée à 4,50 €, payée en monnaie locale à la tireuse (origine
        tireuse, point de vente de la tireuse). Rend la vente.
        / A tapped beer paid in local currency at the tap. Returns the sale.
        """
        vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.TIREUSE,
            point_de_vente=self.point_de_vente_de_la_tireuse,
            articles=[
                {
                    "pricesold": self.tarif_de_la_biere_tiree,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 450,
                    "taux_tva": Decimal("20"),
                    "payment_method": PaymentMethod.LOCAL_EURO,
                    "asset": self.monnaie_locale.uuid,
                    "status": LigneArticle.VALID,
                    "point_de_vente": self.point_de_vente_de_la_tireuse,
                },
            ],
            reglements=[
                {
                    "moyen": PaymentMethod.LOCAL_EURO,
                    "montant": 450,
                    "asset": self.monnaie_locale.uuid,
                },
            ],
        )
        verifier_egalites(vente)
        return vente

    def _vendre_un_billet_en_ligne(self):
        """
        Un billet à 10,00 € vendu en ligne, réglé par Stripe : aucun point de vente.
        Rend la vente.
        / A 10.00 € ticket sold online, paid by Stripe: no point of sale.
        """
        vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.LESPASS,
            articles=[
                {
                    "pricesold": self.tarif_du_billet_en_ligne,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 1000,
                    "taux_tva": Decimal("20"),
                    "payment_method": PaymentMethod.STRIPE_NOFED,
                    "status": LigneArticle.VALID,
                },
            ],
            reglements=[{"moyen": PaymentMethod.STRIPE_NOFED, "montant": 1000}],
        )
        verifier_egalites(vente)
        return vente

    def _rendre_une_consigne_en_especes(self):
        """
        Un retour de consigne au comptoir : une vente AVOIR, un article à −1,00 €,
        rendu en espèces (règlement espèces de −100). Rend la vente.
        / A deposit return at the counter: an AVOIR sale, refunded in cash.
        """
        vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            nature=Vente.Nature.AVOIR,
            point_de_vente=self.comptoir,
            operateur=self.administrateur_du_lieu,
            articles=[
                {
                    "pricesold": self.tarif_de_la_consigne,
                    "quantite": Decimal("-1"),
                    "prix_unitaire": 100,
                    "taux_tva": Decimal("20"),
                    "payment_method": PaymentMethod.CASH,
                    "status": LigneArticle.VALID,
                    "point_de_vente": self.comptoir,
                },
            ],
            reglements=[{"moyen": PaymentMethod.CASH, "montant": -100}],
        )
        verifier_egalites(vente)
        return vente

    def _vider_une_carte_en_especes(self):
        """
        Le vidage d'une carte au comptoir : 5,00 € de monnaie locale repris, rendus
        en espèces. Une vente VIDAGE_CARTE sans article, deux règlements qui
        s'annulent (monnaie locale +500, espèces −500). Rend la vente.
        / Card emptying at the counter: no item, two payments that cancel out.
        """
        vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            nature=Vente.Nature.VIDAGE_CARTE,
            point_de_vente=self.comptoir,
            operateur=self.administrateur_du_lieu,
            reglements=[
                {
                    "moyen": PaymentMethod.LOCAL_EURO,
                    "montant": 500,
                    "asset": self.monnaie_locale.uuid,
                },
                {"moyen": PaymentMethod.CASH, "montant": -500},
            ],
        )
        verifier_egalites(vente)
        return vente

    def _corriger_en_carte_bancaire(self, vente_en_especes):
        """
        Le caissier corrige en carte bancaire le moyen d'une vente payée en espèces,
        par la vraie route (elle écrit une vente CORRECTION liée). Rend la vente
        CORRECTION.
        / The cashier corrects a cash sale into card, through the real route.
        Returns the CORRECTION sale.
        """
        ligne_de_la_vente = vente_en_especes.articles.first()
        donnees_du_formulaire = {
            "ligne_uuid": str(ligne_de_la_vente.uuid),
            "ancien_moyen": ligne_de_la_vente.payment_method,
            "nouveau_moyen": PaymentMethod.CC,
            "raison": "Erreur de moyen au moment du paiement",
        }
        reponse = self.client_du_caissier.post(
            URL_DE_LA_CORRECTION_DU_MOYEN, donnees_du_formulaire
        )
        self.assertEqual(reponse.status_code, 200, reponse.content.decode()[:400])
        return Vente.objects.get(
            nature=Vente.Nature.CORRECTION, vente_liee=vente_en_especes
        )

    def _cloturer_la_journee(self):
        """
        Le « Z de fin de service » : crée la J du lieu, maintenant, par la vraie
        tâche.
        / The end-of-service Z: creates the venue's J now, through the real task.
        """
        uuid_de_la_j = comptabilite.tasks.generer_cloture_pour_tenant(
            schema_name=self.tenant.schema_name,
            niveau=ClotureCaisse.NIVEAU_JOURNALIER,
        )
        self.assertIsNotNone(uuid_de_la_j, "La J aurait dû être créée.")

    # ------------------------------------------------------------------
    # Outils du test : les écrans
    # / Test helpers: the screens
    # ------------------------------------------------------------------

    def _lire_la_liste_des_ventes(self, parametres=""):
        """
        Ouvre la liste des ventes (page complète), avec les paramètres donnés
        (« ?moyen=CC »…). Rend le HTML.
        / Opens the sales list with the given parameters. Returns its HTML.
        """
        reponse = self.client_du_caissier.get(
            f"{URL_DE_LA_LISTE_DES_VENTES}{parametres}"
        )
        contenu = reponse.content.decode()
        self.assertEqual(reponse.status_code, 200, contenu[:400])
        return contenu

    def _numeros_affiches(self, contenu):
        """
        Les numéros de vente de la liste, dans l'ordre affiché.
        / The sale numbers of the list, in display order.
        """
        textes_des_numeros = textes_des_elements(contenu, "vente-numero")
        numeros = []
        for texte_du_numero in textes_des_numeros:
            numeros.append(chiffres_du_texte(texte_du_numero))
        return numeros

    def _ouvrir_le_detail_de_la_vente(self, vente):
        """
        Ouvre l'écran du détail d'une vente, par l'uuid de la vente. Rend le HTML.
        / Opens a sale's detail screen by the sale's uuid. Returns its HTML.
        """
        reponse = self.client_du_caissier.get(
            f"{DEBUT_DE_L_URL_DU_DETAIL_D_UNE_VENTE}{vente.uuid}/"
        )
        contenu = reponse.content.decode()
        self.assertEqual(reponse.status_code, 200, contenu[:400])
        return contenu

    def _lire_le_recap_en_cours(self):
        """
        Ouvre le récapitulatif en cours (page complète). Rend le HTML.
        / Opens the current recap (full page). Returns its HTML.
        """
        reponse = self.client_du_caissier.get(URL_DU_RECAP_EN_COURS)
        contenu = reponse.content.decode()
        self.assertEqual(reponse.status_code, 200, contenu[:400])
        return contenu

    def _ouvrir_le_formulaire_de_correction(self, ligne, ancien_moyen):
        """
        Ouvre l'écran « corriger le moyen » d'un moyen de la vente de cette ligne,
        comme le bouton du détail (une ligne de la vente + le moyen corrigé). Rend le
        montant affiché, espaces ramenées à une seule.
        / Opens the correction screen of one method of the line's sale, like the
        detail button. Returns the amount shown.
        """
        reponse = self.client_du_caissier.get(
            URL_DU_FORMULAIRE_DE_CORRECTION,
            {"ligne_uuid": str(ligne.uuid), "ancien_moyen": ancien_moyen},
        )
        contenu = reponse.content.decode()
        self.assertEqual(reponse.status_code, 200, contenu[:400])
        texte_du_montant, _attributs = lire_l_element(contenu, "correction-montant")
        return texte_sans_espaces_en_trop(texte_du_montant)

    def _corriger_la_ligne(self, ligne, ancien_moyen, nouveau_moyen):
        """
        Corrige un moyen de la vente de cette ligne par la vraie route : la ligne
        retrouve la vente, `ancien_moyen` est le moyen corrigé. Rend la réponse.
        / Corrects one method of the line's sale through the real route.
        """
        return self.client_du_caissier.post(
            URL_DE_LA_CORRECTION_DU_MOYEN,
            {
                "ligne_uuid": str(ligne.uuid),
                "ancien_moyen": ancien_moyen,
                "nouveau_moyen": nouveau_moyen,
                "raison": "Erreur de moyen au moment du paiement",
            },
        )

    def _montants_des_reglements_par_moyen(self, vente):
        """
        Les règlements d'une vente, par moyen : {moyen: montant}.
        / A sale's payments by method.
        """
        montants_par_moyen = {}
        reglements_de_la_vente = vente.reglements.all()
        for reglement in reglements_de_la_vente:
            montants_par_moyen[reglement.moyen] = reglement.montant
        return montants_par_moyen

    # ------------------------------------------------------------------
    # Le récapitulatif en cours
    # / The current recap
    # ------------------------------------------------------------------

    def test_recap_en_cours_aucune_vente(self):
        """
        Un lieu sans aucune vente : le récapitulatif en cours répond 200 et dit
        « aucune vente » (`data-testid="recap-aucune-vente"`).
        / A venue without any sale: the recap says "no sale".
        """
        reponse = self.client_du_caissier.get(URL_DU_RECAP_EN_COURS)

        self.assertEqual(reponse.status_code, 200)
        self.assertIn('data-testid="recap-aucune-vente"', reponse.content.decode())

    def test_recap_par_moyen_et_par_point_de_vente_du_rapport_du_service(self):
        """
        Le fil rouge à la caisse et un billet de 10,00 € vendu en ligne (Stripe).
        L'écran Ventes lit le rapport du service, ventes en ligne comprises :
        - Total : 10,50 + 10,00 = « 20,50 € » ;
        - « Par moyen de paiement » : carte bancaire 5,50 € ;
        - « Par point de vente » : le billet en ligne sous « Sans point de vente »,
          10,00 €.
        / The Sales screen reads the service report, online sales included.
        """
        self._vendre_trois_jus_en_monnaie_locale_et_carte_bancaire()
        self._vendre_un_billet_en_ligne()

        contenu = self._lire_le_recap_en_cours()

        texte_du_total, _attributs = lire_l_element(contenu, "recap-total")
        self.assertEqual(texte_sans_espaces_en_trop(texte_du_total), montant_attendu("20,50"))

        texte_par_moyen, _attributs = lire_l_element(contenu, "recap-totaux-moyen")
        texte_par_moyen = texte_sans_espaces_en_trop(texte_par_moyen)
        self.assertIn(
            f"{LIBELLE_CARTE_BANCAIRE} {montant_attendu('5,50')}", texte_par_moyen
        )

        texte_par_point_de_vente, _attributs = lire_l_element(contenu, "recap-par-pv")
        texte_par_point_de_vente = texte_sans_espaces_en_trop(texte_par_point_de_vente)
        self.assertIn(
            f"Sans point de vente {montant_attendu('10,00')}", texte_par_point_de_vente
        )

    def test_historique_de_vente_par_article_du_rapport_du_service(self):
        """
        Le fil rouge à la caisse et un billet vendu en ligne. Le bouton « Historique
        de vente » ouvre, en bas de l'écran (cible HTMX « detail-contenu »), le
        tableau par article : les jus (quantité 3, 10,50 €) ET le billet vendu en
        ligne. Seul ce tableau est rendu : ni les chiffres du haut, ni les
        mini-tableaux.
        / The "Sales history" button renders only the by-item table.
        """
        self._vendre_trois_jus_en_monnaie_locale_et_carte_bancaire()
        self._vendre_un_billet_en_ligne()
        nom_du_jus = self.tarif_du_jus.productsold.product.name
        nom_du_billet = self.tarif_du_billet_en_ligne.productsold.product.name

        reponse = self.client_du_caissier.get(
            f"{URL_DU_RECAP_EN_COURS}?vue=detail_articles",
            HTTP_HX_REQUEST="true",
            HTTP_HX_TARGET="detail-contenu",
        )

        contenu = reponse.content.decode()
        self.assertEqual(reponse.status_code, 200, contenu[:400])
        texte_du_detail, _attributs = lire_l_element(contenu, "recap-detail-articles")
        texte_du_detail = texte_sans_espaces_en_trop(texte_du_detail)
        self.assertIn(f"{nom_du_jus} 3 {montant_attendu('10,50')}", texte_du_detail)
        self.assertIn(nom_du_billet, texte_du_detail)
        self.assertNotIn('data-testid="recap-kpi-total"', contenu)
        self.assertNotIn('data-testid="recap-totaux-moyen"', contenu)

    def test_recap_a_les_trois_boutons_d_historique_et_rien_du_rapport_complet(self):
        """
        L'écran Ventes garde la forme de la maquette : trois boutons d'historique
        (vente, commande, synthèse par moyen). Le rapport complet reste dans
        l'admin : ni règlements, ni réconciliation, ni marge brute, ni opérateurs,
        ni sections repliées. L'ancien titre « Lignes de caisse (hors ventes en
        ligne, recharges comprises) » n'apparaît plus.
        / Three history buttons; the full report stays in the admin.
        """
        self._vendre_une_pinte_en_especes()

        contenu = self._lire_le_recap_en_cours()

        self.assertIn('data-testid="btn-historique-ventes"', contenu)
        self.assertIn('data-testid="btn-historique-commandes"', contenu)
        self.assertIn('data-testid="btn-historique-synthese"', contenu)
        for testid_du_rapport_complet in [
            "recap-reglements",
            "recap-reconciliation",
            "recap-marge-brute-repliee",
            "recap-operateurs-repliee",
            "recap-annexe-repliee",
        ]:
            self.assertNotIn(f'data-testid="{testid_du_rapport_complet}', contenu)
        self.assertNotIn("<details", contenu)
        self.assertNotIn(ANCIEN_TITRE_DES_LIGNES_DE_CAISSE, contenu)

    def test_recap_boutons_fond_et_sortie_de_caisse_gardent_les_params(self):
        """
        Le Ticket X passe les 3 paramètres aux boutons Fond de caisse et Sortie de
        caisse, et au bouton « Historique de commande ».
        / Ticket X passes the 3 params to the float, withdrawal and order history
        buttons.
        """
        self._vendre_une_pinte_en_especes()

        reponse = self.client_du_caissier.get(
            f"{URL_DU_RECAP_EN_COURS}?uuid_pv={self.comptoir.uuid}"
            f"&tag_id_cm={TAG_ID_CM_DE_TEST}&type_app={TYPE_APP_DE_TEST}"
        )

        self.assertEqual(reponse.status_code, 200)
        contenu = reponse.content.decode()
        # Les params sont échappés dans les attributs (& devient &amp;).
        # / Params are escaped in attributes (& becomes &amp;).
        params_attendus = (
            f"uuid_pv={self.comptoir.uuid}&amp;tag_id_cm={TAG_ID_CM_DE_TEST}"
            f"&amp;type_app={TYPE_APP_DE_TEST}"
        )
        self.assertIn(f"/laboutik/caisse/fond-de-caisse/?{params_attendus}", contenu)
        self.assertIn(f"/laboutik/caisse/sortie-de-caisse/?{params_attendus}", contenu)
        self.assertIn(f"/laboutik/caisse/liste-ventes/?{params_attendus}", contenu)

    def test_fond_de_caisse_bouton_retour_garde_les_params(self):
        """
        Le bouton Retour du Fond de caisse renvoie vers le Ticket X avec les 3
        paramètres.
        / The float Back button goes back to Ticket X with the 3 params.
        """
        reponse = self.client_du_caissier.get(
            f"/laboutik/caisse/fond-de-caisse/?uuid_pv={self.comptoir.uuid}"
            f"&tag_id_cm={TAG_ID_CM_DE_TEST}&type_app={TYPE_APP_DE_TEST}"
        )

        self.assertEqual(reponse.status_code, 200)
        self.assertIn(
            f"/laboutik/caisse/recap-en-cours/?uuid_pv={self.comptoir.uuid}"
            f"&amp;tag_id_cm={TAG_ID_CM_DE_TEST}&amp;type_app={TYPE_APP_DE_TEST}",
            reponse.content.decode(),
        )

    def test_sortie_de_caisse_formulaire_renvoie_tag_et_type_app(self):
        """
        Le formulaire de Sortie de caisse renvoie tag_id_cm et type_app en champs
        cachés.
        / The withdrawal form sends back tag_id_cm and type_app as hidden fields.
        """
        reponse = self.client_du_caissier.get(
            f"/laboutik/caisse/sortie-de-caisse/?uuid_pv={self.comptoir.uuid}"
            f"&tag_id_cm={TAG_ID_CM_DE_TEST}&type_app={TYPE_APP_DE_TEST}"
        )

        self.assertEqual(reponse.status_code, 200)
        contenu = reponse.content.decode()
        self.assertIn(f'name="tag_id_cm" value="{TAG_ID_CM_DE_TEST}"', contenu)
        self.assertIn(f'name="type_app" value="{TYPE_APP_DE_TEST}"', contenu)

    # ------------------------------------------------------------------
    # La liste des ventes
    # / The sales list
    # ------------------------------------------------------------------

    def test_liste_des_ventes_une_ligne_moyens_en_clair(self):
        """
        Le fil rouge : UNE ligne. Numéro de la vente, heure d'encaissement à l'heure
        de Paris, badge « Vente », comptoir, total 10,50 €, moyens en clair
        « 5,50 € Carte bancaire + 5,00 € Monnaie locale menu ventes » (le comptoir
        d'abord, le cashless ensuite, par le nom de sa monnaie), 3 articles
        (1,428571 + 1,571429).
        / The running example: one row with number, local time, badge, point of sale,
        total, payment methods in words, 3 items.
        """
        vente = self._vendre_trois_jus_en_monnaie_locale_et_carte_bancaire()
        heure_locale_attendue = vente.datetime_encaissement.astimezone(
            ZoneInfo(FUSEAU_DU_LIEU)
        ).strftime("%H:%M")

        contenu = self._lire_la_liste_des_ventes()

        self.assertEqual(self._numeros_affiches(contenu), [str(vente.numero)])
        self.assertEqual(
            textes_des_elements(contenu, "vente-heure"), [heure_locale_attendue]
        )
        self.assertEqual(textes_des_elements(contenu, "vente-nature"), [BADGE_VENTE])
        self.assertEqual(
            textes_des_elements(contenu, "vente-point-de-vente"),
            ["Comptoir menu ventes"],
        )
        self.assertEqual(
            textes_des_elements(contenu, "vente-total"), [montant_attendu("10,50")]
        )
        self.assertEqual(
            textes_des_elements(contenu, "vente-moyens"),
            [
                f"{montant_attendu('5,50')} {LIBELLE_CARTE_BANCAIRE} + "
                f"{montant_attendu('5,00')} {NOM_DE_LA_MONNAIE_LOCALE}"
            ],
        )
        nombres_d_articles = textes_des_elements(contenu, "vente-nombre-articles")
        self.assertEqual(len(nombres_d_articles), 1)
        self.assertEqual(nombres_d_articles[0].split()[0], "3")

    def test_liste_des_ventes_une_ligne_par_vente_meme_sans_identifiant_de_paiement(
        self,
    ):
        """
        3 pintes et 2 demis payés en espèces, lignes SANS identifiant de paiement :
        une seule ligne dans la liste, total 21,00 € (1500 + 600), 5 articles.
        / Lines without payment id: still one row per sale, 21.00 €, 5 items.
        """
        vente = self._vendre_au_comptoir_en_especes(
            [(self.tarif_de_la_pinte, 500, 3), (self.tarif_du_demi, 300, 2)],
            avec_identifiant=False,
        )

        contenu = self._lire_la_liste_des_ventes()

        self.assertEqual(self._numeros_affiches(contenu), [str(vente.numero)])
        self.assertEqual(
            textes_des_elements(contenu, "vente-total"), [montant_attendu("21,00")]
        )
        nombres_d_articles = textes_des_elements(contenu, "vente-nombre-articles")
        self.assertEqual(nombres_d_articles[0].split()[0], "5")

    def test_liste_des_ventes_montre_la_tireuse_et_pas_la_vente_en_ligne(self):
        """
        Une vente au comptoir, puis une à la tireuse, puis un billet vendu en ligne.
        La liste montre la tireuse puis le comptoir (la plus récente d'abord), et
        jamais la vente en ligne : elle n'est pas faite sur un point de vente.
        / Counter, tap, online: the list shows the tap and the counter, never online.
        """
        vente_au_comptoir = self._vendre_une_pinte_en_especes()
        vente_a_la_tireuse = self._vendre_a_la_tireuse()
        vente_en_ligne = self._vendre_un_billet_en_ligne()

        contenu = self._lire_la_liste_des_ventes()

        numeros_affiches = self._numeros_affiches(contenu)
        self.assertEqual(
            numeros_affiches,
            [str(vente_a_la_tireuse.numero), str(vente_au_comptoir.numero)],
        )
        self.assertNotIn(str(vente_en_ligne.numero), numeros_affiches)

    def test_liste_des_ventes_montre_toutes_les_operations_numerotees_avec_leur_nature(
        self,
    ):
        """
        Une pinte en espèces, un retour de consigne (avoir), la correction de la
        pinte en carte bancaire, le vidage d'une carte. La liste montre les quatre
        opérations, la plus récente d'abord, avec des numéros qui se suivent et leur
        badge : « Carte vidée », « Correction », « Avoir », « Vente ».
        / Four numbered operations, consecutive numbers, with their nature badge.
        """
        vente_de_la_pinte = self._vendre_une_pinte_en_especes()
        avoir_de_la_consigne = self._rendre_une_consigne_en_especes()
        correction_de_la_pinte = self._corriger_en_carte_bancaire(vente_de_la_pinte)
        vidage_de_la_carte = self._vider_une_carte_en_especes()

        contenu = self._lire_la_liste_des_ventes()

        self.assertEqual(
            self._numeros_affiches(contenu),
            [
                str(vidage_de_la_carte.numero),
                str(correction_de_la_pinte.numero),
                str(avoir_de_la_consigne.numero),
                str(vente_de_la_pinte.numero),
            ],
        )
        self.assertEqual(vidage_de_la_carte.numero, vente_de_la_pinte.numero + 3)
        self.assertEqual(
            textes_des_elements(contenu, "vente-nature"),
            [BADGE_CARTE_VIDEE, BADGE_CORRECTION, BADGE_AVOIR, BADGE_VENTE],
        )

    def test_liste_des_ventes_moyens_lus_dans_les_reglements_apres_une_correction(
        self,
    ):
        """
        Une pinte en espèces, puis sa correction en carte bancaire : la ligne de la
        pinte porte désormais « carte bancaire ». Dans la liste, la vente d'origine
        montre toujours « 5,00 € Espèces » : ses moyens sont lus dans ses
        règlements, jamais sur ses lignes.
        / After a correction, the original sale still shows "5,00 € Espèces": methods
        are read from its payments, never from its lines.
        """
        vente_de_la_pinte = self._vendre_une_pinte_en_especes()
        self._corriger_en_carte_bancaire(vente_de_la_pinte)

        contenu = self._lire_la_liste_des_ventes()

        numeros_affiches = self._numeros_affiches(contenu)
        moyens_affiches = textes_des_elements(contenu, "vente-moyens")
        self.assertIn(str(vente_de_la_pinte.numero), numeros_affiches)
        self.assertEqual(len(moyens_affiches), len(numeros_affiches))
        position_de_la_vente_d_origine = numeros_affiches.index(
            str(vente_de_la_pinte.numero)
        )
        self.assertEqual(
            moyens_affiches[position_de_la_vente_d_origine],
            f"{montant_attendu('5,00')} Espèces",
        )

    def test_liste_filtree_sur_la_carte_bancaire_garde_la_vente_a_deux_moyens(self):
        """
        Le fil rouge et une pinte en espèces. Filtre « carte bancaire » : seule la
        vente du fil rouge, avec le total de TOUTE la vente (10,50 €), pas sa part
        en carte bancaire.
        / Card filter: only the two-method sale, with the whole sale total.
        """
        vente_a_deux_moyens = self._vendre_trois_jus_en_monnaie_locale_et_carte_bancaire()
        self._vendre_une_pinte_en_especes()

        contenu = self._lire_la_liste_des_ventes(f"?moyen={PaymentMethod.CC}")

        self.assertEqual(
            self._numeros_affiches(contenu), [str(vente_a_deux_moyens.numero)]
        )
        self.assertEqual(
            textes_des_elements(contenu, "vente-total"), [montant_attendu("10,50")]
        )

    def test_liste_filtree_sur_un_moyen_lit_les_reglements_pas_les_lignes(self):
        """
        Une pinte en espèces, puis sa correction en carte bancaire : la ligne de la
        pinte porte désormais « carte bancaire », mais la vente d'origine a été
        réglée en espèces. Filtre « carte bancaire » : seule la vente de correction
        (elle a un règlement carte bancaire), pas la vente d'origine.
        / Card filter reads the payments: the correction sale only, not the original
        sale whose line now says "card".
        """
        vente_de_la_pinte = self._vendre_une_pinte_en_especes()
        correction_de_la_pinte = self._corriger_en_carte_bancaire(vente_de_la_pinte)

        contenu = self._lire_la_liste_des_ventes(f"?moyen={PaymentMethod.CC}")

        self.assertEqual(
            self._numeros_affiches(contenu), [str(correction_de_la_pinte.numero)]
        )

    def test_liste_filtree_sur_un_point_de_vente(self):
        """
        Une vente au comptoir et une à la tireuse. Filtre sur le comptoir : seule la
        vente du comptoir.
        / Point of sale filter: only the counter's sale.
        """
        vente_au_comptoir = self._vendre_une_pinte_en_especes()
        self._vendre_a_la_tireuse()

        contenu = self._lire_la_liste_des_ventes(f"?pv={self.comptoir.uuid}")

        self.assertEqual(
            self._numeros_affiches(contenu), [str(vente_au_comptoir.numero)]
        )

    def test_liste_des_ventes_montre_une_vente_ouverte_avant_la_j_et_reglee_apres(
        self,
    ):
        """
        Une pinte réglée ; une deuxième vente ouverte (son article est écrit), puis la
        J, puis la deuxième vente est réglée. La liste du service en cours montre la
        deuxième vente : elle est réglée après la J, même si son article a été écrit
        avant.
        / A sale whose item was written before the J and settled after it is in the
        current service list.
        """
        self._vendre_une_pinte_en_especes()
        vente_ouverte_avant_la_j = ouvrir_vente(
            origine=SaleOrigin.LABOUTIK,
            nature=Vente.Nature.VENTE,
            point_de_vente=self.comptoir,
            operateur=self.administrateur_du_lieu,
        )
        ajouter_article(
            vente_ouverte_avant_la_j,
            pricesold=self.tarif_de_la_pinte,
            quantite=Decimal("1"),
            prix_unitaire=500,
            taux_tva=Decimal("20"),
            payment_method=PaymentMethod.CASH,
            status=LigneArticle.VALID,
            point_de_vente=self.comptoir,
        )
        self._cloturer_la_journee()
        ajouter_reglement(vente_ouverte_avant_la_j, moyen=PaymentMethod.CASH, montant=500)
        vente_reglee_apres_la_j = encaisser_vente(vente_ouverte_avant_la_j)
        verifier_egalites(vente_reglee_apres_la_j)

        contenu = self._lire_la_liste_des_ventes()

        self.assertEqual(
            self._numeros_affiches(contenu), [str(vente_reglee_apres_la_j.numero)]
        )

    def test_liste_des_ventes_premiere_page_de_vingt(self):
        """
        21 pintes vendues une à une. La première page montre 20 ventes, la plus
        récente d'abord (la 21ᵉ), et la ligne qui charge la suite au défilement.
        / 21 sales: the first page shows 20, the most recent first, and the loader.
        """
        ventes = []
        for _numero_de_la_pinte in range(NOMBRE_DE_VENTES_PAR_PAGE + 1):
            ventes.append(self._vendre_une_pinte_en_especes())

        contenu = self._lire_la_liste_des_ventes()

        numeros_affiches = self._numeros_affiches(contenu)
        self.assertEqual(len(numeros_affiches), NOMBRE_DE_VENTES_PAR_PAGE)
        self.assertEqual(numeros_affiches[0], str(ventes[-1].numero))
        self.assertEqual(numeros_affiches[-1], str(ventes[1].numero))
        self.assertIn('data-testid="scroll-loader"', contenu)

    def test_liste_des_ventes_deuxieme_page(self):
        """
        21 pintes vendues une à une. La suite de la première page (`?avant=` le
        numéro de la dernière vente affichée, la 2ᵉ) montre la plus ancienne vente
        seule, sans ligne de chargement de la suite.
        / 21 sales: the rest after the first page (`avant=` the last shown number)
        shows the oldest one, no loader.
        """
        ventes = []
        for _numero_de_la_pinte in range(NOMBRE_DE_VENTES_PAR_PAGE + 1):
            ventes.append(self._vendre_une_pinte_en_especes())

        contenu = self._lire_la_liste_des_ventes(f"?avant={ventes[1].numero}")

        self.assertEqual(self._numeros_affiches(contenu), [str(ventes[0].numero)])
        self.assertNotIn('data-testid="scroll-loader"', contenu)

    def test_la_ligne_de_chargement_demande_la_suite_par_numero(self):
        """
        21 pintes vendues une à une : la ligne de chargement de la première page
        demande les ventes de numéro plus petit que la dernière affichée (la 2ᵉ).
        / The first page's loader asks for sales numbered below the last shown one.
        """
        ventes = []
        for _numero_de_la_pinte in range(NOMBRE_DE_VENTES_PAR_PAGE + 1):
            ventes.append(self._vendre_une_pinte_en_especes())

        contenu = self._lire_la_liste_des_ventes()

        lignes_de_chargement = attributs_des_elements(contenu, "scroll-loader")
        self.assertEqual(len(lignes_de_chargement), 1)
        self.assertIn(f"avant={ventes[1].numero}", lignes_de_chargement[0]["hx-get"])

    def test_liste_filtree_sur_un_point_de_vente_illisible_ne_montre_rien(self):
        """
        Un filtre de point de vente qui n'est pas un uuid : 200, et aucune vente (pas
        une erreur 500).
        / A point of sale filter that is not a uuid: 200, no sale.
        """
        self._vendre_une_pinte_en_especes()

        contenu = self._lire_la_liste_des_ventes("?pv=pas-un-uuid")

        self.assertEqual(self._numeros_affiches(contenu), [])

    def test_liste_des_ventes_nombre_de_requetes_constant(self):
        """
        Le nombre de requêtes SQL de la liste est le même avec une vente et avec
        quatre (deux moyens, espèces, tireuse) : aucune requête par vente.
        / The list's SQL query count is the same with one sale and with four.
        """
        self._vendre_trois_jus_en_monnaie_locale_et_carte_bancaire()
        compteur_avec_une_vente = CompteurDeRequetesSql()
        with connection.execute_wrapper(compteur_avec_une_vente):
            self._lire_la_liste_des_ventes()

        self._vendre_trois_jus_en_monnaie_locale_et_carte_bancaire()
        self._vendre_une_pinte_en_especes()
        self._vendre_a_la_tireuse()
        compteur_avec_quatre_ventes = CompteurDeRequetesSql()
        with connection.execute_wrapper(compteur_avec_quatre_ventes):
            contenu = self._lire_la_liste_des_ventes()

        self.assertEqual(len(self._numeros_affiches(contenu)), 4)
        self.assertEqual(
            compteur_avec_quatre_ventes.nombre_de_requetes,
            compteur_avec_une_vente.nombre_de_requetes,
        )

    # ------------------------------------------------------------------
    # Le détail d'une vente
    # / The sale detail
    # ------------------------------------------------------------------

    def test_detail_vente_quantites_reelles(self):
        """
        Le fil rouge : le détail montre UN article jus, quantité « 3 » (pas « 2 » et
        « 1 »), prix unitaire 3,50 €, total 10,50 € ; total de la vente 10,50 €.
        / The running example: one juice item, quantity 3, 3.50 €, 10.50 €.
        """
        vente = self._vendre_trois_jus_en_monnaie_locale_et_carte_bancaire()

        contenu = self._ouvrir_le_detail_de_la_vente(vente)

        self.assertEqual(textes_des_elements(contenu, "detail-qty"), ["3"])
        self.assertEqual(
            textes_des_elements(contenu, "detail-prix-unit"), [montant_attendu("3,50")]
        )
        self.assertEqual(
            textes_des_elements(contenu, "detail-total-ligne"),
            [montant_attendu("10,50")],
        )
        self.assertEqual(
            textes_des_elements(contenu, "detail-total-transaction"),
            [montant_attendu("10,50")],
        )

    def test_detail_vente_montre_les_reglements(self):
        """
        Le fil rouge : le détail montre ses deux règlements, dans l'ordre du
        comptoir puis du cashless : carte bancaire 5,50 €, puis 5,00 € de monnaie
        locale, écrit par le nom de la monnaie (moyen et monnaie).
        / The running example: both payments, card 5.50 € then local currency 5.00 €
        with the currency name.
        """
        vente = self._vendre_trois_jus_en_monnaie_locale_et_carte_bancaire()

        contenu = self._ouvrir_le_detail_de_la_vente(vente)

        self.assertEqual(
            textes_des_elements(contenu, "detail-reglement-moyen"),
            [LIBELLE_CARTE_BANCAIRE, NOM_DE_LA_MONNAIE_LOCALE],
        )
        self.assertEqual(
            textes_des_elements(contenu, "detail-reglement-montant"),
            [montant_attendu("5,50"), montant_attendu("5,00")],
        )
        monnaies_des_reglements = textes_des_elements(
            contenu, "detail-reglement-monnaie"
        )
        self.assertEqual(len(monnaies_des_reglements), 2)
        self.assertEqual(monnaies_des_reglements[1], NOM_DE_LA_MONNAIE_LOCALE)

    def test_detail_vente_un_bouton_corriger_par_reglement_corrigeable(self):
        """
        Le fil rouge : le détail propose UN bouton « Corriger », pour le règlement
        carte bancaire. Il transmet une ligne de la vente (pour retrouver la vente)
        et le moyen corrigé (`ancien_moyen=CC`) ; son formulaire se charge dans la
        zone de ce moyen (`correction-zone-<vente>-CC`). Le règlement en monnaie
        locale (cashless) n'a pas de bouton.
        / The running example: ONE "Correct" button, for the card payment, carrying a
        line of the sale and the corrected method. The local currency has none.
        """
        vente = self._vendre_trois_jus_en_monnaie_locale_et_carte_bancaire()
        uuids_des_lignes_de_la_vente = []
        for ligne_de_la_vente in vente.articles.all():
            uuids_des_lignes_de_la_vente.append(str(ligne_de_la_vente.uuid))

        contenu = self._ouvrir_le_detail_de_la_vente(vente)

        boutons_corriger = attributs_des_elements(contenu, "btn-corriger")
        self.assertEqual(len(boutons_corriger), 1, boutons_corriger)
        adresse_du_bouton = boutons_corriger[0].get("hx-get", "")
        self.assertIn(f"ancien_moyen={PaymentMethod.CC}", adresse_du_bouton)
        ligne_transmise = re.search(r"ligne_uuid=([0-9a-f-]+)", adresse_du_bouton)
        self.assertIsNotNone(ligne_transmise, adresse_du_bouton)
        self.assertIn(ligne_transmise.group(1), uuids_des_lignes_de_la_vente)
        self.assertEqual(
            boutons_corriger[0].get("hx-target"),
            f"#correction-zone-{vente.uuid}-{PaymentMethod.CC}",
        )
        self.assertNotIn(f"ancien_moyen={PaymentMethod.LOCAL_EURO}", contenu)

    def test_detail_vente_montre_la_part_offerte(self):
        """
        Une pinte à 5,00 € entièrement offerte (bouton OFFRIR) : le détail montre la
        part offerte 5,00 € et un total d'article de 0,00 €.
        / A fully offered pint: offered part 5.00 €, item total 0.00 €.
        """
        vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            point_de_vente=self.comptoir,
            operateur=self.administrateur_du_lieu,
            articles=[
                {
                    "pricesold": self.tarif_de_la_pinte,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 500,
                    "taux_tva": Decimal("20"),
                    "offert_en_totalite": True,
                    "status": LigneArticle.VALID,
                    "point_de_vente": self.comptoir,
                },
            ],
        )
        verifier_egalites(vente)

        contenu = self._ouvrir_le_detail_de_la_vente(vente)

        self.assertEqual(
            textes_des_elements(contenu, "detail-part-offerte"),
            [montant_attendu("5,00")],
        )
        self.assertEqual(
            textes_des_elements(contenu, "detail-total-ligne"),
            [montant_attendu("0,00")],
        )

    def test_detail_d_une_correction_mene_a_la_vente_d_origine(self):
        """
        Une pinte en espèces, puis sa correction en carte bancaire. Le détail de la
        vente CORRECTION porte un lien vers le détail de la vente d'origine.
        / The CORRECTION sale detail links to the original sale's detail.
        """
        vente_de_la_pinte = self._vendre_une_pinte_en_especes()
        correction_de_la_pinte = self._corriger_en_carte_bancaire(vente_de_la_pinte)
        adresse_du_detail_d_origine = (
            f"{DEBUT_DE_L_URL_DU_DETAIL_D_UNE_VENTE}{vente_de_la_pinte.uuid}/"
        )

        contenu = self._ouvrir_le_detail_de_la_vente(correction_de_la_pinte)

        liens_vers_la_vente_liee = attributs_des_elements(contenu, "detail-vente-liee")
        self.assertEqual(len(liens_vers_la_vente_liee), 1, contenu[:2000])
        valeurs_des_attributs = list(liens_vers_la_vente_liee[0].values())
        un_attribut_mene_a_l_origine = False
        for valeur_de_l_attribut in valeurs_des_attributs:
            if valeur_de_l_attribut and adresse_du_detail_d_origine in valeur_de_l_attribut:
                un_attribut_mene_a_l_origine = True
        self.assertTrue(un_attribut_mene_a_l_origine, liens_vers_la_vente_liee)

    def test_detail_vente_vrac_poids_et_prix_au_kilo(self):
        """
        350 g de cacahuètes en vrac à 12,00 €/kg (4,20 €), sous la forme D15 : la ligne
        porte 0,350 kg au prix du kilo (1200). Le détail montre « 0,350 kg » en
        quantité, « 12,00 €/kg » en prix unitaire et 4,20 € de total.
        / Bulk peanuts (D15 form: 0.350 kg at 1200 per kg): quantity with its unit,
        price per kg and total.
        """
        produit_en_vrac = Product.objects.create(
            name=f"Cacahuetes en vrac menu ventes {uuid_module.uuid4().hex[:8]}",
            categorie_article=Product.NONE,
        )
        tarif_au_kilo = Price.objects.create(
            product=produit_en_vrac,
            name="Au poids",
            prix=Decimal("12.00"),
            poids_mesure=True,
            publish=True,
        )
        Stock.objects.create(
            product=produit_en_vrac, quantite=5000, unite=UniteStock.GR,
        )
        produit_vendu = ProductSold.objects.create(product=produit_en_vrac)
        tarif_vendu_au_kilo = PriceSold.objects.create(
            productsold=produit_vendu, price=tarif_au_kilo, prix=tarif_au_kilo.prix,
        )
        vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            point_de_vente=self.comptoir,
            articles=[
                {
                    "pricesold": tarif_vendu_au_kilo,
                    "quantite": Decimal("0.350"),
                    "prix_unitaire": 1200,
                    "taux_tva": Decimal("20"),
                    "weight_quantity": 350,
                    "payment_method": PaymentMethod.CASH,
                    "status": LigneArticle.VALID,
                    "point_de_vente": self.comptoir,
                },
            ],
            reglements=[{"moyen": PaymentMethod.CASH, "montant": 420}],
        )
        verifier_egalites(vente)

        contenu = self._ouvrir_le_detail_de_la_vente(vente)

        self.assertEqual(
            textes_des_elements(contenu, "detail-qty"),
            [texte_sans_espaces_en_trop("0,350 kg")],
        )
        self.assertEqual(
            textes_des_elements(contenu, "detail-prix-unit"),
            [texte_sans_espaces_en_trop("12,00 €/kg")],
        )
        self.assertEqual(
            textes_des_elements(contenu, "detail-total-ligne"),
            [montant_attendu("4,20")],
        )

    def test_detail_vente_introuvable(self):
        """
        Un uuid de vente qui n'existe pas : 404.
        / An unknown sale uuid: 404.
        """
        reponse = self.client_du_caissier.get(
            f"{DEBUT_DE_L_URL_DU_DETAIL_D_UNE_VENTE}{uuid_module.uuid4()}/"
        )

        self.assertEqual(reponse.status_code, 404)

    def test_detail_vente_uuid_invalide(self):
        """
        Une adresse qui ne porte pas un uuid : 404 (pas 500).
        / An address without a uuid: 404, not 500.
        """
        reponse = self.client_du_caissier.get(
            f"{DEBUT_DE_L_URL_DU_DETAIL_D_UNE_VENTE}pas-un-uuid/"
        )

        self.assertEqual(reponse.status_code, 404)

    # ------------------------------------------------------------------
    # L'écran « corriger le moyen »
    # / The "correct the payment method" screen
    # ------------------------------------------------------------------

    def test_ecran_corriger_moyen_affiche_le_montant_du_reglement(self):
        """
        Le fil rouge : l'écran de correction de la part payée par carte bancaire
        affiche 5,50 € (le règlement carte bancaire), pas 3,50 € (le prix d'un jus).
        / The correction screen of the card part shows 5.50 € (the card payment),
        not 3.50 € (one juice).
        """
        vente = self._vendre_trois_jus_en_monnaie_locale_et_carte_bancaire()
        part_en_carte_bancaire = vente.articles.get(payment_method=PaymentMethod.CC)

        montant_affiche = self._ouvrir_le_formulaire_de_correction(
            part_en_carte_bancaire, PaymentMethod.CC
        )

        self.assertEqual(montant_affiche, montant_attendu("5,50"))

    def test_ecran_corriger_moyen_affiche_la_somme_des_lignes_du_moyen(self):
        """
        Une pinte (5,00 €) et un demi (3,00 €) payés en espèces : l'écran de
        correction de la pinte affiche 8,00 €, l'argent que la correction déplace
        (toutes les lignes de la vente payées en espèces).
        / A pint and a half in cash: the pint's correction screen shows 8.00 €.
        """
        vente = self._vendre_au_comptoir_en_especes(
            [(self.tarif_de_la_pinte, 500, 1), (self.tarif_du_demi, 300, 1)]
        )
        ligne_de_la_pinte = vente.articles.get(pricesold=self.tarif_de_la_pinte)

        montant_affiche = self._ouvrir_le_formulaire_de_correction(
            ligne_de_la_pinte, PaymentMethod.CASH
        )

        self.assertEqual(montant_affiche, montant_attendu("8,00"))

    def test_la_correction_deplace_le_montant_affiche(self):
        """
        Une pinte et un demi en espèces (8,00 €). L'écran de correction affiche un
        montant ; la correction en carte bancaire écrit une vente CORRECTION dont les
        règlements valent ce montant : espèces −800, carte bancaire +800.
        / The CORRECTION sale's payments equal the amount the screen showed.
        """
        vente = self._vendre_au_comptoir_en_especes(
            [(self.tarif_de_la_pinte, 500, 1), (self.tarif_du_demi, 300, 1)]
        )
        ligne_de_la_pinte = vente.articles.get(pricesold=self.tarif_de_la_pinte)
        montant_affiche = self._ouvrir_le_formulaire_de_correction(
            ligne_de_la_pinte, PaymentMethod.CASH
        )

        reponse = self._corriger_la_ligne(
            ligne_de_la_pinte, PaymentMethod.CASH, PaymentMethod.CC
        )

        self.assertEqual(reponse.status_code, 200, reponse.content.decode()[:400])
        vente_de_correction = Vente.objects.get(
            nature=Vente.Nature.CORRECTION, vente_liee=vente
        )
        montants = self._montants_des_reglements_par_moyen(vente_de_correction)
        self.assertEqual(montants, {PaymentMethod.CASH: -800, PaymentMethod.CC: 800})
        self.assertEqual(montant_affiche, montant_attendu("8,00"))

    def test_la_correction_d_une_vente_sans_identifiant_de_paiement_deplace_toute_la_vente(
        self,
    ):
        """
        Une pinte et un demi en espèces, lignes SANS identifiant de paiement : la
        correction en carte bancaire déplace 8,00 € (les deux lignes de la vente),
        pas 5,00 € (la seule ligne cliquée).
        / Lines without payment id: the correction moves the whole sale (8.00 €).
        """
        vente = self._vendre_au_comptoir_en_especes(
            [(self.tarif_de_la_pinte, 500, 1), (self.tarif_du_demi, 300, 1)],
            avec_identifiant=False,
        )
        ligne_de_la_pinte = vente.articles.get(pricesold=self.tarif_de_la_pinte)

        reponse = self._corriger_la_ligne(
            ligne_de_la_pinte, PaymentMethod.CASH, PaymentMethod.CC
        )

        self.assertEqual(reponse.status_code, 200, reponse.content.decode()[:400])
        vente_de_correction = Vente.objects.get(
            nature=Vente.Nature.CORRECTION, vente_liee=vente
        )
        montants = self._montants_des_reglements_par_moyen(vente_de_correction)
        self.assertEqual(montants, {PaymentMethod.CASH: -800, PaymentMethod.CC: 800})

    def test_une_correction_erronee_se_corrige_encore(self):
        """
        Une pinte en espèces, corrigée en carte bancaire, puis (c'était une erreur)
        en chèque. Après la 1ʳᵉ correction, le détail propose un seul bouton
        « Corriger », pour la carte bancaire (le moyen des règlements nets) ; la 2ᵉ
        correction (carte bancaire → chèque) écrit une 2ᵉ vente CORRECTION :
        carte bancaire −500, chèque +500.
        / A cash pint corrected into card, then into cheque: the detail offers a
        Correct button for card, and a second CORRECTION is written.
        """
        vente_de_la_pinte = self._vendre_une_pinte_en_especes()
        ligne_de_la_pinte = vente_de_la_pinte.articles.get()
        self._corriger_la_ligne(ligne_de_la_pinte, PaymentMethod.CASH, PaymentMethod.CC)
        contenu_du_detail = self._ouvrir_le_detail_de_la_vente(vente_de_la_pinte)
        boutons_corriger = attributs_des_elements(contenu_du_detail, "btn-corriger")
        self.assertEqual(len(boutons_corriger), 1, boutons_corriger)
        self.assertIn(
            f"ancien_moyen={PaymentMethod.CC}", boutons_corriger[0].get("hx-get", "")
        )

        reponse = self._corriger_la_ligne(
            ligne_de_la_pinte, PaymentMethod.CC, PaymentMethod.CHEQUE
        )

        self.assertEqual(reponse.status_code, 200, reponse.content.decode()[:400])
        corrections_de_la_pinte = list(
            Vente.objects.filter(
                nature=Vente.Nature.CORRECTION, vente_liee=vente_de_la_pinte
            ).order_by("numero")
        )
        self.assertEqual(len(corrections_de_la_pinte), 2)
        montants = self._montants_des_reglements_par_moyen(corrections_de_la_pinte[1])
        self.assertEqual(
            montants, {PaymentMethod.CC: -500, PaymentMethod.CHEQUE: 500}
        )

    def test_apres_une_correction_le_detail_est_re_rendu(self):
        """
        Une pinte en espèces corrigée en carte bancaire : la route répond par le
        détail de la vente d'origine (message de correction, et la vente
        CORRECTION dans les ventes dérivées).
        / After a correction the route answers with the original sale's detail.
        """
        vente_de_la_pinte = self._vendre_une_pinte_en_especes()
        ligne_de_la_pinte = vente_de_la_pinte.articles.get()

        reponse = self._corriger_la_ligne(
            ligne_de_la_pinte, PaymentMethod.CASH, PaymentMethod.CC
        )

        contenu = reponse.content.decode()
        self.assertEqual(reponse.status_code, 200, contenu[:400])
        self.assertIn('data-testid="correction-succes"', contenu)
        self.assertIn('data-testid="ventes-detail"', contenu)
        vente_de_correction = Vente.objects.get(
            nature=Vente.Nature.CORRECTION, vente_liee=vente_de_la_pinte
        )
        self.assertEqual(
            textes_des_elements(contenu, "detail-vente-derivee"),
            [f"Corrigée par la vente n° {vente_de_correction.numero}"],
        )
        # Le message de correction reçoit le focus après l'échange (htmx).
        # / The correction message gets the focus after the swap.
        message_de_correction = attributs_des_elements(contenu, "correction-succes")
        self.assertIn("autofocus", message_de_correction[0])

    def test_deux_envois_du_meme_formulaire_ne_font_qu_une_correction(self):
        """
        Une pinte en espèces ; le même formulaire (espèces vues → carte bancaire)
        est envoyé deux fois (double clic). Une seule vente CORRECTION ; le second
        envoi est refusé (400) : sous le verrou, le net des espèces vaut déjà 0. Le
        message clair est rendu dans la zone du formulaire de ce moyen
        (`HX-Retarget` vers `correction-zone-<vente>-CA`).
        / The same form posted twice: one CORRECTION only; the second post is
        refused (the cash net is already 0), in the method's form zone.
        """
        vente_de_la_pinte = self._vendre_une_pinte_en_especes()
        ligne_de_la_pinte = vente_de_la_pinte.articles.get()
        donnees_du_formulaire = {
            "ligne_uuid": str(ligne_de_la_pinte.uuid),
            "ancien_moyen": PaymentMethod.CASH,
            "nouveau_moyen": PaymentMethod.CC,
            "raison": "Erreur de moyen au moment du paiement",
        }
        premiere_reponse = self.client_du_caissier.post(
            URL_DE_LA_CORRECTION_DU_MOYEN, donnees_du_formulaire
        )

        seconde_reponse = self.client_du_caissier.post(
            URL_DE_LA_CORRECTION_DU_MOYEN, donnees_du_formulaire
        )

        self.assertEqual(premiere_reponse.status_code, 200)
        self.assertEqual(seconde_reponse.status_code, 400)
        texte_du_refus, _attributs = lire_l_element(
            seconde_reponse.content.decode(), "alerte-messages-texte"
        )
        self.assertEqual(
            texte_du_refus,
            "Il ne reste rien à corriger pour le moyen « Espèces » sur cette vente : "
            "elle vient peut-être d'être corrigée. Rouvrez la vente pour voir ses "
            "règlements.",
        )
        self.assertEqual(
            seconde_reponse["HX-Retarget"],
            f"#correction-zone-{vente_de_la_pinte.uuid}-{PaymentMethod.CASH}",
        )
        self.assertEqual(
            Vente.objects.filter(
                nature=Vente.Nature.CORRECTION, vente_liee=vente_de_la_pinte
            ).count(),
            1,
        )

    def test_ecran_corriger_moyen_uuid_illisible_404(self):
        """
        L'écran de correction d'une ligne dont l'identifiant n'est pas un uuid :
        404, pas 500.
        / The correction screen with an unreadable uuid: 404, not 500.
        """
        reponse = self.client_du_caissier.get(
            f"{URL_DU_FORMULAIRE_DE_CORRECTION}?ligne_uuid=pas-un-uuid"
        )

        self.assertEqual(reponse.status_code, 404)

    def test_la_ligne_de_la_liste_porte_un_bouton_pour_le_clavier(self):
        """
        La ligne d'une vente reste une ligne de tableau ; la cellule du numéro porte
        un vrai bouton, fermé (`aria-expanded="false"`), qui commande la ligne du
        détail (`aria-controls="detail-vente-<uuid>"`).
        / The number cell holds a real button controlling the detail row.
        """
        vente = self._vendre_une_pinte_en_especes()

        contenu = self._lire_la_liste_des_ventes()

        boutons = attributs_des_elements(contenu, "vente-bouton-detail")
        self.assertEqual(len(boutons), 1)
        self.assertEqual(boutons[0]["aria-expanded"], "false")
        self.assertEqual(boutons[0]["aria-controls"], f"detail-vente-{vente.uuid}")

    def test_reimprimer_seulement_une_vente_ou_un_avoir(self):
        """
        Une pinte en espèces, corrigée en carte bancaire : le détail de la vente
        propose « Ré-imprimer », celui de la vente CORRECTION non (pas de ticket
        client pour une correction).
        / Reprint is offered for a sale, not for a CORRECTION.
        """
        vente_de_la_pinte = self._vendre_une_pinte_en_especes()
        correction_de_la_pinte = self._corriger_en_carte_bancaire(vente_de_la_pinte)

        contenu_de_la_vente = self._ouvrir_le_detail_de_la_vente(vente_de_la_pinte)
        contenu_de_la_correction = self._ouvrir_le_detail_de_la_vente(
            correction_de_la_pinte
        )

        self.assertIn('data-testid="btn-reimprimer"', contenu_de_la_vente)
        self.assertNotIn('data-testid="btn-reimprimer"', contenu_de_la_correction)

    def test_liste_une_vente_sans_moyen_montre_un_tiret(self):
        """
        Une pinte entièrement offerte (aucun moyen de paiement, l'offert n'en est
        pas un) : les moyens en clair disent « — ».
        / A fully offered sale shows a dash as payment methods.
        """
        vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            point_de_vente=self.comptoir,
            articles=[
                {
                    "pricesold": self.tarif_de_la_pinte,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 500,
                    "taux_tva": Decimal("20"),
                    "offert_en_totalite": True,
                    "status": LigneArticle.VALID,
                    "point_de_vente": self.comptoir,
                },
            ],
        )
        verifier_egalites(vente)

        contenu = self._lire_la_liste_des_ventes()

        self.assertEqual(textes_des_elements(contenu, "vente-moyens"), ["—"])

    # ------------------------------------------------------------------
    # Le détail : ventes dérivées, tirages, événements, monnaies
    # / The detail: derived sales, pours, events, currencies
    # ------------------------------------------------------------------

    def test_detail_d_une_vente_corrigee_mene_a_la_vente_de_correction(self):
        """
        Une pinte en espèces corrigée en carte bancaire : le détail de la pinte dit
        « Corrigée par la vente n° X », avec un lien vers le détail de la vente
        CORRECTION.
        / The corrected sale's detail links to the CORRECTION sale.
        """
        vente_de_la_pinte = self._vendre_une_pinte_en_especes()
        correction_de_la_pinte = self._corriger_en_carte_bancaire(vente_de_la_pinte)
        adresse_de_la_correction = (
            f"{DEBUT_DE_L_URL_DU_DETAIL_D_UNE_VENTE}{correction_de_la_pinte.uuid}/"
        )

        contenu = self._ouvrir_le_detail_de_la_vente(vente_de_la_pinte)

        self.assertEqual(
            textes_des_elements(contenu, "detail-vente-derivee"),
            [f"Corrigée par la vente n° {correction_de_la_pinte.numero}"],
        )
        liens = attributs_des_elements(contenu, "detail-vente-derivee")
        self.assertEqual(liens[0]["href"], adresse_de_la_correction)

    def test_detail_d_un_tirage_paye_avec_deux_moyens_montre_un_article(self):
        """
        Une pinte de 50 cl tirée à la tireuse (4,00 €), payée 1,00 € en jetons cadeau
        et 3,00 € en monnaie locale, écrite comme la tireuse l'écrit (D15) : UNE ligne
        de 0,500 L au prix du litre (8,00 €), dont 1,00 € payé en jetons. Le détail
        montre UN article, « 0,50 L », total 4,00 €.
        / A pour paid with two methods, one D15 line: one item, "0,50 L", 4.00 €.
        """
        tarif_de_la_pinte_tiree = creer_tarif_vendu(
            nom="Pinte tiree", prix_en_euros="8.00", taux_tva="20.00"
        )
        Stock.objects.create(
            product=tarif_de_la_pinte_tiree.productsold.product,
            quantite=10000,
            unite=UniteStock.CL,
        )
        ligne_du_tirage = {
            "pricesold": tarif_de_la_pinte_tiree,
            "quantite": Decimal("0.500"),
            "prix_unitaire": 800,
            "taux_tva": Decimal("20"),
            "part_en_jetons": 100,
            "weight_quantity": 50,
            "status": LigneArticle.VALID,
            "point_de_vente": self.point_de_vente_de_la_tireuse,
        }
        vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.TIREUSE,
            point_de_vente=self.point_de_vente_de_la_tireuse,
            articles=[ligne_du_tirage],
            reglements=[
                {"moyen": PaymentMethod.LOCAL_GIFT, "montant": 100},
                {
                    "moyen": PaymentMethod.LOCAL_EURO,
                    "montant": 300,
                    "asset": self.monnaie_locale.uuid,
                },
            ],
        )
        verifier_egalites(vente)

        contenu = self._ouvrir_le_detail_de_la_vente(vente)

        self.assertEqual(textes_des_elements(contenu, "detail-qty"), ["0,50 L"])
        self.assertEqual(
            textes_des_elements(contenu, "detail-total-ligne"),
            [montant_attendu("4,00")],
        )

    def test_detail_les_billets_de_deux_evenements_font_deux_articles(self):
        """
        Le même tarif de billet (10,00 €) vendu pour deux événements, dans une vente
        en espèces : deux articles, un par événement, chacun avec son nom.
        / The same ticket price for two events: two items, one per event.
        """
        tarif_du_billet = creer_tarif_vendu(
            nom="Billet", prix_en_euros="10.00", categorie_article=Product.BILLET
        )
        tarifs_vendus_par_evenement = []
        noms_des_evenements = ["Concert du vendredi", "Concert du samedi"]
        for nom_de_l_evenement in noms_des_evenements:
            debut_de_l_evenement = timezone.now() + timedelta(days=10)
            with taches_celery_enregistrees():
                evenement = Event.objects.create(
                    name=f"{nom_de_l_evenement} {uuid_module.uuid4().hex[:6]}",
                    datetime=debut_de_l_evenement,
                    end_datetime=debut_de_l_evenement + timedelta(hours=2),
                    jauge_max=100,
                )
            produit_vendu = ProductSold.objects.create(
                product=tarif_du_billet.productsold.product, event=evenement
            )
            tarif_vendu_pour_cet_evenement = PriceSold.objects.create(
                productsold=produit_vendu,
                price=tarif_du_billet.price,
                prix=tarif_du_billet.prix,
            )
            tarifs_vendus_par_evenement.append(tarif_vendu_pour_cet_evenement)
        vente = self._vendre_au_comptoir_en_especes(
            [
                (tarifs_vendus_par_evenement[0], 1000, 1),
                (tarifs_vendus_par_evenement[1], 1000, 1),
            ]
        )

        contenu = self._ouvrir_le_detail_de_la_vente(vente)

        self.assertEqual(textes_des_elements(contenu, "detail-qty"), ["1", "1"])
        texte_du_detail, _attributs = lire_l_element(contenu, "detail-articles")
        for nom_de_l_evenement in noms_des_evenements:
            self.assertIn(nom_de_l_evenement, texte_du_detail)

    def test_liste_une_monnaie_de_l_ancien_fedow_s_ecrit_par_son_nom(self):
        """
        Une bière tirée payée avec une monnaie de l'ancien Fedow (absente de
        fedow_core) : les moyens en clair l'écrivent par son nom, comme le rapport.
        / A currency of the old Fedow is written by its name, like the report.
        """
        portefeuille_de_l_ancien_fedow = Wallet.objects.create(
            origin=self.tenant, name="Portefeuille ancien Fedow menu ventes",
        )
        monnaie_de_l_ancien_fedow = AssetFedowPublic.objects.create(
            name="Monnaie ancien Fedow menu ventes",
            currency_code="AFM",
            wallet_origin=portefeuille_de_l_ancien_fedow,
            origin=self.tenant,
            category=AssetFedowPublic.TOKEN_LOCAL_FIAT,
        )
        vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.TIREUSE,
            point_de_vente=self.point_de_vente_de_la_tireuse,
            articles=[
                {
                    "pricesold": self.tarif_de_la_biere_tiree,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 450,
                    "taux_tva": Decimal("20"),
                    "payment_method": PaymentMethod.LOCAL_EURO,
                    "asset": monnaie_de_l_ancien_fedow.uuid,
                    "status": LigneArticle.VALID,
                    "point_de_vente": self.point_de_vente_de_la_tireuse,
                },
            ],
            reglements=[
                {
                    "moyen": PaymentMethod.LOCAL_EURO,
                    "montant": 450,
                    "asset": monnaie_de_l_ancien_fedow.uuid,
                },
            ],
        )
        verifier_egalites(vente)

        contenu = self._lire_la_liste_des_ventes()

        self.assertEqual(
            textes_des_elements(contenu, "vente-moyens"),
            [f"{montant_attendu('4,50')} Monnaie ancien Fedow menu ventes"],
        )

    def test_liste_l_offert_n_est_pas_un_moyen_en_clair(self):
        """
        Un jus à 3,50 € payé en espèces et une pinte offerte : les moyens en clair
        disent « 3,50 € Espèces », sans l'offert (montré sur l'article).
        / The offered part is not a payment method in words.
        """
        vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            point_de_vente=self.comptoir,
            articles=[
                {
                    "pricesold": self.tarif_du_jus,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 350,
                    "taux_tva": Decimal("20"),
                    "payment_method": PaymentMethod.CASH,
                    "status": LigneArticle.VALID,
                    "point_de_vente": self.comptoir,
                },
                {
                    "pricesold": self.tarif_de_la_pinte,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 500,
                    "taux_tva": Decimal("20"),
                    "offert_en_totalite": True,
                    "status": LigneArticle.VALID,
                    "point_de_vente": self.comptoir,
                },
            ],
            reglements=[{"moyen": PaymentMethod.CASH, "montant": 350}],
        )
        verifier_egalites(vente)

        contenu = self._lire_la_liste_des_ventes()

        self.assertEqual(
            textes_des_elements(contenu, "vente-moyens"),
            [f"{montant_attendu('3,50')} Espèces"],
        )
