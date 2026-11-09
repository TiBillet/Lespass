"""
tests/pytest/test_demo_ventes_de_la_veille.py
La démo d'un flush : des ventes d'hier écrites par le vrai moteur, et leur clôture J,
exportable sans erreur (FEC, API comptable, Dolibarr).
/ The flush demo: yesterday's sales through the real engine, and their J closure,
exportable without error.

LOCALISATION : tests/pytest/test_demo_ventes_de_la_veille.py

RÈGLES MÉTIER TESTÉES
- `create_test_pos_data` relie les catégories de caisse au 707000 et pose la TVA des
  produits (alcool 20 %, le reste 10 %) : une vente du Bar ne manque d'aucun compte.
- `seed_ventes_de_la_veille_par_le_moteur` écrit 5 ventes réglées, datées d'hier :
  3 au Bar (espèces, CB), 2 billets de concert à 5,5 % et 1 adhésion en ligne
  (Stripe).
- La J de ces ventes se ventile en deux écritures (BAR, WEB), aux montants attendus,
  avec les trois comptes de TVA (20 %, 10 %, 5,5 %).
- Un second passage n'écrit rien (le lieu a déjà des ventes).
/ Business rules: POS categories get 707000 and products their VAT; 5 settled sales
dated yesterday; the J splits into BAR and WEB entries with the expected amounts; a
second run writes nothing.

Schéma dédié (`FastTenantTestCase`) : le test écrit des ventes et une clôture.
"""

import sys

# Le code Django vit dans /DjangoFiles a l'interieur du conteneur.
# / Django code lives in /DjangoFiles inside the container.
sys.path.insert(0, "/DjangoFiles")

import django  # noqa: E402

django.setup()

from datetime import time, timedelta  # noqa: E402
from decimal import Decimal  # noqa: E402

from django.core.management import call_command  # noqa: E402
from django.db import connection  # noqa: E402
from django.utils import timezone  # noqa: E402
from django_tenants.test.cases import FastTenantTestCase  # noqa: E402

import comptabilite.tasks  # noqa: E402
from Administration.management.commands._demo_data_v2_ventes import (  # noqa: E402
    seed_ventes_de_la_veille_par_le_moteur,
)
from BaseBillet.models import Configuration, Event, Price, Product, Tva  # noqa: E402
from BaseBillet.models_vente import Vente  # noqa: E402
from comptabilite.models import ClotureCaisse  # noqa: E402
from comptabilite.ventilation import ecritures_de_l_export  # noqa: E402
from laboutik.models import LaboutikConfiguration  # noqa: E402


class TestDemoVentesDeLaVeille(FastTenantTestCase):
    """
    Les ventes d'hier de la démo et leur J. / The demo's yesterday sales and their J.
    """

    @classmethod
    def get_test_schema_name(cls):
        return "test_demo_ventes_veille"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-demo-ventes-veille.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        """`Client.name` est unique et obligatoire. / Client.name is unique."""
        tenant.name = "Test demo ventes de la veille"

    def setUp(self):
        """
        Le lieu (Paris, sans TVA par défaut, aucun mail de rapport), la caisse de
        démo (`create_test_pos_data`), et les deux fixtures du mode complet que les
        ventes en ligne utilisent : le concert et l'adhésion.
        / The venue, the demo POS, and the concert and membership fixtures.
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

        # Les fixtures du mode complet de `demo_data_v2` (billet à 5,5 %).
        # / The full-mode fixtures of demo_data_v2 (ticket at 5.5 %).
        concert = Event.objects.create(
            name="What the Funk ? — Spectacle payant",
            datetime=timezone.now() + timedelta(days=30),
        )
        billet = Product.objects.create(
            name="Billet",
            categorie_article=Product.BILLET,
            tva=Tva.objects.get_or_create(tva_rate=Decimal("5.50"))[0],
        )
        Price.objects.create(product=billet, name="Plein tarif", prix=Decimal("20.00"))
        concert.products.add(billet)
        adhesion = Product.objects.create(
            name="Adhésion associative Tiers Lustre",
            categorie_article=Product.ADHESION,
        )
        Price.objects.create(product=adhesion, name="Plein tarif", prix=Decimal("30.00"))

    def _ecrire_les_ventes_et_cloturer(self):
        """Les ventes d'hier, puis la J du vrai moteur. / Sales, then the real J."""
        resultat = seed_ventes_de_la_veille_par_le_moteur()
        uuid_de_la_j = comptabilite.tasks.generer_cloture_pour_tenant(
            schema_name=self.tenant.schema_name,
            niveau=ClotureCaisse.NIVEAU_JOURNALIER,
        )
        return resultat, ClotureCaisse.objects.get(uuid=uuid_de_la_j)

    def test_cinq_ventes_reglees_datees_d_hier(self):
        resultat, _cloture = self._ecrire_les_ventes_et_cloturer()

        assert resultat["sautees"] == []
        assert len(resultat["ecrites"]) == 5
        ventes = Vente.objects.filter(statut=Vente.Statut.REGLEE)
        assert ventes.count() == 5
        fuseau_du_lieu = Configuration.get_solo().get_tzinfo()
        hier = (timezone.localtime(timezone.now(), fuseau_du_lieu) - timedelta(days=1)).date()
        for vente in ventes:
            assert timezone.localtime(vente.datetime_encaissement, fuseau_du_lieu).date() == hier

    def test_la_j_se_ventile_en_bar_et_web_avec_les_trois_tva(self):
        """
        BAR : espèces 13 €, CB 22 € ; 707000 29,55 €, TVA 20 % 5 €, TVA 10 % 0,45 €.
        WEB : Stripe 70 € ; 706000 37,91 €, TVA 5,5 % 2,09 €, 756000 30 €.
        / BAR and WEB entries with the expected amounts.
        """
        _resultat, cloture = self._ecrire_les_ventes_et_cloturer()

        montants_par_journal = {}
        for ecriture in ecritures_de_l_export(cloture)["ecritures"]:
            montants_par_compte = {}
            for ligne in ecriture["lignes"]:
                debit, credit = montants_par_compte.get(ligne["compte"], (0, 0))
                montants_par_compte[ligne["compte"]] = (
                    debit + ligne["debit"],
                    credit + ligne["credit"],
                )
            montants_par_journal[ecriture["journal"]] = montants_par_compte

        assert montants_par_journal == {
            "BAR": {
                "530000": (1300, 0),
                "512100": (2200, 0),
                "707000": (0, 2955),
                "445711": (0, 500),
                "445712": (0, 45),
            },
            "WEB": {
                "517100": (7000, 0),
                "706000": (0, 3791),
                "445713": (0, 209),
                "756000": (0, 3000),
            },
        }

    def test_un_second_passage_n_ecrit_rien(self):
        self._ecrire_les_ventes_et_cloturer()

        second_resultat = seed_ventes_de_la_veille_par_le_moteur()

        assert second_resultat["ecrites"] == []
        assert Vente.objects.filter(statut=Vente.Statut.REGLEE).count() == 5
