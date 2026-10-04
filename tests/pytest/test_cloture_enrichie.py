"""
Le contenu de la clôture journalière créée par le bouton « Clôturer » de la caisse :
numéro séquentiel, total perpétuel, plage de la journée, sections du rapport stocké.
/ The content of the daily closure created by the register "Close" button: sequential
number, perpetual total, day range, stored report sections.

LOCALISATION : tests/pytest/test_cloture_enrichie.py

RÈGLES MÉTIER TESTÉES
- Chaque clic sur « Clôturer » (avec au moins une vente depuis la clôture précédente)
  crée une clôture journalière unique (`comptabilite.ClotureCaisse`, la « J »),
  numérotée à la suite : n° 1, puis n° 2.
- La première J d'un lieu commence à sa première vente réglée ; la suivante commence
  à la fin de la précédente.
- Le total perpétuel d'une J = celui de la J précédente + le chiffre d'affaires TTC de
  cette J ; jamais remis à zéro.
- La J stocke toutes les sections du rapport des ventes (`RapportDesVentes`).
/ Each click creates a numbered J; the first J starts at the first settled sale, the
next one at the end of the previous one; perpetual total = previous + this J's revenue;
the J stores every section of the sales report.

Le détail du calcul d'une J (filet automatique, H / M / A, chaîne des clôtures) est
testé par tests/pytest/test_cloture_unique.py, sur la tâche elle-même. Ce fichier
vérifie que le BOUTON produit la même J.
/ The J computation itself is tested in test_cloture_unique.py; this file checks the
button produces the same J.

SCHÉMA DÉDIÉ
Une J lit TOUTES les ventes du lieu : ce fichier tourne dans un lieu qui ne contient
que ses propres ventes (`FastTenantTestCase`). Chaque test annule sa transaction à la
fin. Le singleton `LaboutikConfiguration` est créé en base (tests/PIEGES.md 9.86). Les
ventes sont écrites PAR LE SERVICE (`fabriques_vente.py`).
/ Dedicated schema, rolled back after each test. Sales through the sale service.

D'OÙ VIENNENT LES VALEURS ATTENDUES (calcul à la main)
Une bière vaut 5,00 € (500 centimes). Dix bières : 10 × 500 = 5000 ; six bières :
6 × 500 = 3000. Total perpétuel : 0 + 5000 = 5000, puis 5000 + 3000 = 8000
(fiche F §6 test 14 : précédent + CA de la J).
/ Hand computation: 10 beers = 5000, 6 beers = 3000; perpetual 5000 then 8000.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-F-rapport-unique.md (§3.1,
§6), CHANTIER-05-G-lecteurs.md (§2).

Lancement / Run:
    make test ARGS="tests/pytest/test_cloture_enrichie.py"
"""
import sys

# Le code Django est dans /DjangoFiles a l'interieur du conteneur.
# / Django code is in /DjangoFiles inside the container.
sys.path.insert(0, '/DjangoFiles')

import django

django.setup()

import uuid  # noqa: E402
from decimal import Decimal  # noqa: E402

from django.db import connection  # noqa: E402
from django_tenants.test.cases import FastTenantTestCase  # noqa: E402
from django_tenants.test.client import TenantClient  # noqa: E402

from AuthBillet.models import TibilletUser  # noqa: E402
from BaseBillet.models import (  # noqa: E402
    Configuration, LigneArticle, PaymentMethod, SaleOrigin,
)
from BaseBillet.models_vente import Vente  # noqa: E402
from comptabilite.models import ClotureCaisse  # noqa: E402
from fabriques_vente import (  # noqa: E402
    creer_tarif_vendu,
    fabriquer_vente_encaissee,
    verifier_egalites,
)
from laboutik.models import LaboutikConfiguration, PointDeVente  # noqa: E402


# Adresse de la clôture au comptoir (laboutik/urls.py).
# / Counter closure address.
URL_DE_LA_CLOTURE = '/laboutik/caisse/cloturer/'

# Les sections du rapport stocké dans une J (`RapportDesVentes.toutes_les_sections()`).
# / The report sections stored in a J.
SECTIONS_DU_RAPPORT_D_UNE_J = {
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


class TestClotureEnrichie(FastTenantTestCase):
    """
    Numéro, perpétuel, plage et sections de la J créée par le bouton.
    / Number, perpetual total, range and sections of the J created by the button.
    """

    @classmethod
    def get_test_schema_name(cls):
        return 'test_cloture_enrichie'

    @classmethod
    def get_test_tenant_domain(cls):
        return 'test-cloture-enrichie.tibillet.localhost'

    @classmethod
    def setup_tenant(cls, tenant):
        """Champ requis sur Client. / Required field on Client."""
        tenant.name = 'Test Cloture Enrichie'

    def setUp(self):
        """
        Un comptoir, une bière à 5,00 €, un admin connecté à la caisse.
        / A counter, a beer at 5.00 €, a logged-in admin.
        """
        # Le rollback du test précédent a rendu le `search_path` au public.
        # / The previous test's rollback returned the search_path to public.
        connection.set_tenant(self.tenant)

        # Le singleton de la caisse porte la clé des empreintes (tests/PIEGES.md 9.86).
        # / The register singleton carries the fingerprint key.
        LaboutikConfiguration.get_solo().save()

        # Toutes les valeurs sont écrites ici : le cache garde celles du test d'avant.
        # Aucun e-mail de rapport : une J n'envoie rien.
        # / Every value is written here. No report e-mail.
        configuration = Configuration.get_solo()
        configuration.module_monnaie_locale = True
        configuration.module_caisse = True
        configuration.fuseau_horaire = "Europe/Paris"
        configuration.rapport_emails = ""
        configuration.save()

        self.tarif_de_la_biere = creer_tarif_vendu(
            nom="Biere", prix_en_euros="5.00", taux_tva="20.00",
        )
        self.point_de_vente = PointDeVente.objects.create(
            name='Comptoir test cloture enrichie',
            comportement=PointDeVente.DIRECT,
            service_direct=True,
            accepte_especes=True,
            accepte_carte_bancaire=True,
            hidden=True,
        )

        # `TibilletUser` vit dans le schéma public ; il est annulé avec le test.
        # / TibilletUser lives in the public schema; rolled back with the test.
        self.admin, _admin_cree = TibilletUser.objects.get_or_create(
            email='admin-test-cloture-enrichie@tibillet.localhost',
            defaults={
                'username': 'admin-test-cloture-enrichie@tibillet.localhost',
                'is_staff': True,
                'is_active': True,
            },
        )
        self.admin.client_admin.add(self.tenant)

        self.client_http = TenantClient(self.tenant)
        self.client_http.force_login(self.admin)

    def _vendre_des_bieres(self, quantite, moyen):
        """
        Une vente de caisse réglée au comptoir : `quantite` bières à 5,00 €, payées
        avec un seul moyen. Rend la vente.
        / A settled register sale: `quantite` beers paid with one method.
        """
        vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            point_de_vente=self.point_de_vente,
            operateur=self.admin,
            articles=[
                {
                    'pricesold': self.tarif_de_la_biere,
                    'quantite': Decimal(quantite),
                    'prix_unitaire': 500,
                    'taux_tva': Decimal('20'),
                    'payment_method': moyen,
                    'status': LigneArticle.VALID,
                    'uuid_transaction': uuid.uuid4(),
                    'point_de_vente': self.point_de_vente,
                },
            ],
            reglements=[{'moyen': moyen, 'montant': 500 * quantite}],
        )
        verifier_egalites(vente)
        return vente

    def _cliquer_sur_cloturer(self):
        """
        Le caissier clique sur « Clôturer » ; le bouton doit répondre 200. Rend la
        dernière J du lieu.
        / The cashier clicks "Close" (200 expected). Returns the venue's last J.
        """
        reponse = self.client_http.post(
            URL_DE_LA_CLOTURE, {'uuid_pv': str(self.point_de_vente.uuid)}
        )
        assert reponse.status_code == 200, reponse.content.decode()[:400]
        return (
            ClotureCaisse.objects.filter(niveau=ClotureCaisse.NIVEAU_JOURNALIER)
            .order_by('-numero_sequentiel')
            .first()
        )

    def test_deux_clotures_du_bouton_numerotees_1_et_2_et_qui_se_suivent(self):
        """
        Une vente, « Clôturer » ; une vente, « Clôturer ». Deux J, n° 1 puis n° 2 ; la
        n° 2 commence à la fin de la n° 1.
        / Sale, close; sale, close: J no. 1 then no. 2, the second starting where the
        first ends.
        """
        self._vendre_des_bieres(1, PaymentMethod.CASH)
        premiere_j = self._cliquer_sur_cloturer()
        self._vendre_des_bieres(1, PaymentMethod.CC)
        deuxieme_j = self._cliquer_sur_cloturer()

        assert premiere_j is not None
        assert premiere_j.numero_sequentiel == 1
        assert deuxieme_j.numero_sequentiel == 2
        assert deuxieme_j.datetime_debut == premiere_j.datetime_fin

    def test_premiere_j_du_bouton_commence_a_la_premiere_vente(self):
        """
        La première J du lieu commence à l'heure d'encaissement de sa première vente.
        / The venue's first J starts at its first sale's settlement time.
        """
        premiere_vente = self._vendre_des_bieres(1, PaymentMethod.CASH)
        heure_de_la_premiere_vente = Vente.objects.get(
            pk=premiere_vente.pk
        ).datetime_encaissement

        premiere_j = self._cliquer_sur_cloturer()

        assert premiere_j is not None
        assert premiere_j.datetime_debut == heure_de_la_premiere_vente

    def test_deux_clotures_du_bouton_total_perpetuel_cumule(self):
        """
        Dix bières (5000), « Clôturer » ; six bières (3000), « Clôturer ». Total
        perpétuel : 5000, puis 5000 + 3000 = 8000 ; nombre de ventes perpétuel 1,
        puis 2.
        / 5000 then 3000: perpetual total 5000 then 8000; perpetual sales 1 then 2.
        """
        self._vendre_des_bieres(10, PaymentMethod.CASH)
        premiere_j = self._cliquer_sur_cloturer()
        self._vendre_des_bieres(6, PaymentMethod.CC)
        deuxieme_j = self._cliquer_sur_cloturer()

        assert premiere_j is not None
        assert premiere_j.total_general == 5000
        assert premiere_j.total_perpetuel == 5000
        assert premiere_j.nombre_ventes_perpetuel == 1
        assert deuxieme_j.total_general == 3000
        assert deuxieme_j.total_perpetuel == 8000
        assert deuxieme_j.nombre_ventes_perpetuel == 2

    def test_rapport_json_de_la_j_du_bouton_a_les_sections_du_rapport_unique(self):
        """
        La J du bouton stocke les sections du rapport des ventes d'une J : en-tête,
        chiffre d'affaires, règlements, caisse espèces, réconciliation, offerts,
        annexe, points, marge brute, détail, intégrité.
        / The button's J stores every section of a J sales report.
        """
        self._vendre_des_bieres(1, PaymentMethod.CASH)

        j_du_bouton = self._cliquer_sur_cloturer()

        assert j_du_bouton is not None
        assert set(j_du_bouton.rapport_json.keys()) == SECTIONS_DU_RAPPORT_D_UNE_J
