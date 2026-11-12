"""
tests/pytest/test_demo_data_ventes.py
L'historique des ventes de démo, écrit par le vrai moteur de vente, et ses clôtures.
/ The demo sales history, written by the real sales engine, and its closures.

LOCALISATION : tests/pytest/test_demo_data_ventes.py

RÈGLES MÉTIER TESTÉES (Administration/management/commands/_demo_data_v2_ventes.py)
- Chaque article écrit par le seed a sa vente, et elle est réglée.
- Une clôture M par mois de ventes, au chiffre d'affaires de 1 000,00 €.
- Les numéros des ventes suivent l'ordre de leurs heures ; la chaîne des ventes est
  saine ; l'intégrité de chaque J est « OK ».
- Tous les moyens et cas du programme sont présents.
- Un second passage n'écrit rien : ni vente, ni clôture.
- Le reset refuse sans DEBUG et TEST ; le passage à blanc ne supprime rien ; le vrai
  reset vide les ventes et les clôtures, sans toucher aux lignes de create_test_pos_data.
/ Business rules: every seeded item has its settled sale; one M per month at 1,000 €;
numbers follow times, chain is sound; every case is present; a second run writes
nothing; the reset is guarded and has a dry run.

Schéma dédié (`FastTenantTestCase`) : le seed écrit des ventes et des clôtures, que
toute clôture lit pour le lieu entier. Deux mois d'historique (`nombre_de_mois=2`) au
lieu de 24, pour la durée du test : le programme est le même chaque mois.
/ Dedicated schema; two months instead of 24 for speed (same programme every month).

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-07-seed-ventes-reelles.md
"""

import sys

# Le code Django vit dans /DjangoFiles a l'interieur du conteneur.
# / Django code lives in /DjangoFiles inside the container.
sys.path.insert(0, "/DjangoFiles")

import django  # noqa: E402

django.setup()

from datetime import time  # noqa: E402
from decimal import Decimal  # noqa: E402

from django.core.management import call_command  # noqa: E402
from django.db import connection  # noqa: E402
from django.test import override_settings  # noqa: E402
from django_tenants.test.cases import FastTenantTestCase  # noqa: E402

from Administration.management.commands._demo_data_v2_ventes import (  # noqa: E402
    CHIFFRE_D_AFFAIRES_D_UN_MOIS_EN_CENTIMES,
    DEMO_PRODUCT_PREFIX,
    reinitialiser_les_ventes_du_lieu,
    seed_clotures_demo,
    seed_ventes_demo,
)
from BaseBillet.models import Configuration, LigneArticle, PaymentMethod  # noqa: E402
from BaseBillet.models_vente import Reglement, Vente  # noqa: E402
from comptabilite.models import ClotureCaisse  # noqa: E402
from comptabilite.ventilation import ecritures_de_l_export  # noqa: E402
from laboutik.integrity import verifier_chaine_ventes  # noqa: E402
from laboutik.management.commands.create_test_pos_data import (  # noqa: E402
    UUID_TRANSACTION_DES_LIGNES_DE_DEMO,
)
from laboutik.models import LaboutikConfiguration  # noqa: E402

NOMBRE_DE_MOIS_DU_TEST = 2

# Le programme d'un mois : 30 ventes (dont 2 avoirs) et 31 articles.
# / A month's programme: 30 sales (2 credit notes) and 31 items.
NOMBRE_DE_VENTES_PAR_MOIS = 30
NOMBRE_D_ARTICLES_PAR_MOIS = 31


class TestSeedDesVentesReelles(FastTenantTestCase):
    """
    L'historique de démo et ses clôtures. / The demo history and its closures.
    """

    @classmethod
    def get_test_schema_name(cls):
        return "test_demo_ventes_historique"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-demo-ventes-historique.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        """`Client.name` est unique et obligatoire. / Client.name is unique."""
        tenant.name = "Test demo ventes historique"

    def setUp(self):
        """
        Le lieu (Paris, fermeture 2 h, sans TVA par défaut) et la caisse de démo
        (`create_test_pos_data` : Bar, produits, monnaies, catégories au 707000).
        / The venue and the demo POS.
        """
        connection.set_tenant(self.tenant)

        # Le singleton de la caisse porte la clé des empreintes (tests/PIEGES.md 9.86).
        # / The register singleton holds the fingerprint key.
        LaboutikConfiguration.get_solo().save()

        configuration = Configuration.get_solo()
        configuration.fuseau_horaire = "Europe/Paris"
        configuration.heure_de_fermeture = time(2, 0)
        configuration.vat_taxe = Decimal("0")
        configuration.save()

        call_command("create_test_pos_data", schema=self.tenant.schema_name)

    def _ecrire_l_historique_et_cloturer(self):
        """
        L'historique de 2 mois, puis ses clôtures. Rend aussi les uuid des articles qui
        existaient avant (ceux de create_test_pos_data).
        / The 2-month history, then its closures; plus the items existing before.
        """
        uuids_des_articles_d_avant = set(LigneArticle.objects.values_list("uuid", flat=True))
        stats = seed_ventes_demo(nombre_de_mois=NOMBRE_DE_MOIS_DU_TEST)
        clotures_creees = seed_clotures_demo(self.tenant.schema_name)
        return stats, clotures_creees, uuids_des_articles_d_avant

    def test_chaque_article_ecrit_par_le_seed_a_sa_vente_reglee(self):
        stats, _clotures, uuids_des_articles_d_avant = self._ecrire_l_historique_et_cloturer()

        articles_du_seed = LigneArticle.objects.exclude(uuid__in=uuids_des_articles_d_avant)
        assert stats["cas_sautes"] == []
        assert stats["nombre_de_ventes"] == NOMBRE_DE_VENTES_PAR_MOIS * NOMBRE_DE_MOIS_DU_TEST
        assert articles_du_seed.count() == NOMBRE_D_ARTICLES_PAR_MOIS * NOMBRE_DE_MOIS_DU_TEST
        assert stats["nombre_d_articles"] == articles_du_seed.count()
        assert articles_du_seed.filter(vente__isnull=True).count() == 0
        assert articles_du_seed.exclude(vente__statut=Vente.Statut.REGLEE).count() == 0

    def test_une_cloture_m_par_mois_de_ventes_au_chiffre_d_affaires_de_1000_euros(self):
        stats, clotures_creees, _avant = self._ecrire_l_historique_et_cloturer()

        clotures_m = ClotureCaisse.objects.filter(
            niveau=ClotureCaisse.NIVEAU_MENSUEL
        ).order_by("datetime_debut")
        assert clotures_creees[ClotureCaisse.NIVEAU_MENSUEL] == NOMBRE_DE_MOIS_DU_TEST
        assert clotures_m.count() == NOMBRE_DE_MOIS_DU_TEST

        fuseau_du_lieu = Configuration.get_solo().get_tzinfo()
        mois_des_clotures = []
        for cloture_m in clotures_m:
            assert cloture_m.total_general == CHIFFRE_D_AFFAIRES_D_UN_MOIS_EN_CENTIMES == 100000
            assert cloture_m.nombre_transactions == NOMBRE_DE_VENTES_PAR_MOIS
            mois_des_clotures.append(
                cloture_m.datetime_debut.astimezone(fuseau_du_lieu).strftime("%Y-%m")
            )
        assert mois_des_clotures == stats["mois_ecrits"]

    def test_les_numeros_suivent_les_heures_et_la_chaine_des_ventes_est_saine(self):
        self._ecrire_l_historique_et_cloturer()

        heures_par_numero = list(
            Vente.objects.filter(statut=Vente.Statut.REGLEE)
            .order_by("numero")
            .values_list("datetime_encaissement", flat=True)
        )
        assert heures_par_numero == sorted(heures_par_numero)

        cle_du_lieu = LaboutikConfiguration.get_solo().get_or_create_hmac_key()
        assert verifier_chaine_ventes(cle_du_lieu) == []

        # Une J par journée de ventes (le 6 et le 20 de chaque mois), toutes « OK ».
        # / One J per sales day, all "OK".
        clotures_j = ClotureCaisse.objects.filter(niveau=ClotureCaisse.NIVEAU_JOURNALIER)
        assert clotures_j.count() == 2 * NOMBRE_DE_MOIS_DU_TEST
        for cloture_j in clotures_j:
            assert cloture_j.rapport_json["integrite"]["statut"] == "OK"

    def test_l_export_comptable_de_chaque_j_ne_manque_d_aucun_compte(self):
        """
        Chaque J s'exporte (FEC, API comptable) : chaque article et chaque règlement a
        son compte. Un règlement SF sans sa monnaie FED, par exemple, n'en a pas.
        / Every J exports: every item and payment has its account.
        """
        self._ecrire_l_historique_et_cloturer()

        clotures_j = ClotureCaisse.objects.filter(niveau=ClotureCaisse.NIVEAU_JOURNALIER)
        for cloture_j in clotures_j:
            export_de_la_j = ecritures_de_l_export(cloture_j)
            assert len(export_de_la_j["ecritures"]) > 0

    def test_tous_les_moyens_et_cas_du_programme_sont_presents(self):
        self._ecrire_l_historique_et_cloturer()

        moyens_des_reglements = set(Reglement.objects.values_list("moyen", flat=True))
        moyens_attendus = {
            PaymentMethod.STRIPE_FED,
            PaymentMethod.STRIPE_NOFED,
            PaymentMethod.STRIPE_SEPA_NOFED,
            PaymentMethod.STRIPE_RECURENT,
            PaymentMethod.CC,
            PaymentMethod.CASH,
            PaymentMethod.CHEQUE,
            PaymentMethod.TRANSFER,
            PaymentMethod.LOCAL_EURO,
            PaymentMethod.LOCAL_GIFT,
            PaymentMethod.FREE,
        }
        assert moyens_attendus - moyens_des_reglements == set()

        # Trois recharges par mois, hors chiffre d'affaires : en ligne R et E, caisse RE.
        # / Three top-ups a month, off revenue.
        recharges = LigneArticle.objects.filter(
            vente__nature=Vente.Nature.VENTE, hors_chiffre_affaires=True
        )
        assert recharges.count() == 3 * NOMBRE_DE_MOIS_DU_TEST

        # Deux avoirs par mois : un billet, une vente entière.
        # / Two credit notes a month.
        avoirs = Vente.objects.filter(nature=Vente.Nature.AVOIR, statut=Vente.Statut.REGLEE)
        assert avoirs.count() == 2 * NOMBRE_DE_MOIS_DU_TEST
        assert LigneArticle.objects.filter(status=LigneArticle.CREDIT_NOTE).count() == (
            2 * NOMBRE_DE_MOIS_DU_TEST
        )

        # Des ventes gratuites, sans règlement : billets offerts et prix libres à 0 €.
        # / Free sales, without payment.
        ventes_sans_reglement = Vente.objects.filter(
            statut=Vente.Statut.REGLEE, reglements__isnull=True
        )
        assert ventes_sans_reglement.count() == 3 * NOMBRE_DE_MOIS_DU_TEST

    def test_un_second_passage_n_ecrit_ni_vente_ni_cloture(self):
        self._ecrire_l_historique_et_cloturer()
        nombre_de_ventes_apres_le_premier = Vente.objects.count()
        nombre_de_clotures_apres_le_premier = ClotureCaisse.objects.count()

        second_passage = seed_ventes_demo(nombre_de_mois=NOMBRE_DE_MOIS_DU_TEST)
        clotures_du_second_passage = seed_clotures_demo(self.tenant.schema_name)

        assert second_passage["deja_des_ventes"] is True
        assert second_passage["nombre_de_ventes"] == 0
        assert clotures_du_second_passage == {"J": 0, "H": 0, "M": 0, "A": 0}
        assert Vente.objects.count() == nombre_de_ventes_apres_le_premier
        assert ClotureCaisse.objects.count() == nombre_de_clotures_apres_le_premier

    def test_le_reset_refuse_sans_debug_et_test(self):
        self._ecrire_l_historique_et_cloturer()
        nombre_de_ventes = Vente.objects.count()

        with override_settings(DEBUG=False, TEST=True):
            with self.assertRaises(RuntimeError):
                reinitialiser_les_ventes_du_lieu(passage_a_blanc=False)
        with override_settings(DEBUG=True, TEST=False):
            with self.assertRaises(RuntimeError):
                reinitialiser_les_ventes_du_lieu(passage_a_blanc=False)

        assert Vente.objects.count() == nombre_de_ventes

    def test_le_passage_a_blanc_ne_supprime_rien_et_le_reset_vide_ventes_et_clotures(self):
        self._ecrire_l_historique_et_cloturer()
        nombre_de_ventes = Vente.objects.count()
        nombre_de_clotures = ClotureCaisse.objects.count()
        lignes_de_create_test_pos_data = LigneArticle.objects.filter(
            uuid_transaction=UUID_TRANSACTION_DES_LIGNES_DE_DEMO
        ).count()

        with override_settings(DEBUG=True, TEST=True):
            nombres_a_blanc = reinitialiser_les_ventes_du_lieu(passage_a_blanc=True)
            assert nombres_a_blanc["ventes"] == nombre_de_ventes
            assert nombres_a_blanc["clotures"] == nombre_de_clotures
            assert Vente.objects.count() == nombre_de_ventes
            assert ClotureCaisse.objects.count() == nombre_de_clotures

            reinitialiser_les_ventes_du_lieu(passage_a_blanc=False)

        assert Vente.objects.count() == 0
        assert Reglement.objects.count() == 0
        assert ClotureCaisse.objects.count() == 0
        assert LigneArticle.objects.filter(
            pricesold__productsold__product__name__startswith=DEMO_PRODUCT_PREFIX
        ).count() == 0
        assert LigneArticle.objects.filter(
            uuid_transaction=UUID_TRANSACTION_DES_LIGNES_DE_DEMO
        ).count() == lignes_de_create_test_pos_data
