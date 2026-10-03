"""
Tests pour la management command verify_clotures.
/ Tests for the verify_clotures management command.

LOCALISATION : tests/pytest/test_comptabilite_verify.py

CE QUE LA COMMANDE VÉRIFIE (fiche F §3.2)
1. La continuité des numéros de clôture (pas de trou).
2. La chaîne des clôtures : l'empreinte de chaque clôture, recalculée avec la clé du
   lieu, est celle enregistrée ; son `previous_hmac` est l'empreinte de la clôture
   d'avant ("" pour la première).
3. La continuité des J : la J n+1 commence où la J n finit, et sa première vente suit
   la dernière vente de la J n.
4. Pour chaque J, la chaîne des ventes de sa plage (`verifier_chaine_ventes`).
/ What the command checks: numbering continuity, the chain of closures, the continuity
of the J, and the sales chain of each J's range.

SCHÉMA DÉDIÉ : une clôture lit toutes les ventes du lieu ; le lieu de test ne contient
que les ventes du test, et chaque test annule sa transaction à la fin. Le singleton
`LaboutikConfiguration` est créé en base (tests/PIEGES.md 9.86) : il porte la clé des
empreintes. Ventes et clôtures sont faites à une heure choisie (`timezone.now`
remplacé) : l'heure d'encaissement est scellée dans l'empreinte de la vente.
/ Dedicated schema, rolled back after each test.

Lancer / Run : make test ARGS="tests/pytest/test_comptabilite_verify.py"
"""

import sys

# Le code Django vit dans /DjangoFiles a l'interieur du conteneur.
# / Django code lives in /DjangoFiles inside the container.
sys.path.insert(0, "/DjangoFiles")

import django  # noqa: E402

django.setup()

from datetime import datetime  # noqa: E402
from decimal import Decimal  # noqa: E402
from io import StringIO  # noqa: E402
from unittest.mock import patch  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

from django.core.management import call_command  # noqa: E402
from django.db import connection  # noqa: E402
from django_tenants.test.cases import FastTenantTestCase  # noqa: E402

from BaseBillet.models import Configuration, PaymentMethod, Product, SaleOrigin  # noqa: E402
from comptabilite.models import ClotureCaisse  # noqa: E402
from comptabilite.tasks import generer_cloture_pour_tenant  # noqa: E402
from fabriques_vente import creer_tarif_vendu, fabriquer_vente_encaissee  # noqa: E402
from laboutik.models import LaboutikConfiguration  # noqa: E402

FUSEAU_DE_PARIS = ZoneInfo("Europe/Paris")


def heure_de_paris(annee, mois, jour, heure, minute=0):
    """Un moment en heure de Paris. / A moment in Paris time."""
    return datetime(annee, mois, jour, heure, minute, tzinfo=FUSEAU_DE_PARIS)


class TestVerifyClotures(FastTenantTestCase):
    """
    La commande d'audit des clôtures. / The closure audit command.
    """

    @classmethod
    def get_test_schema_name(cls):
        return "test_comptabilite_verify"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-comptabilite-verify.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        """`Client.name` est unique et obligatoire. / Client.name is unique."""
        tenant.name = "Test comptabilite verify"

    def setUp(self):
        """
        Le lieu de test, son singleton de caisse, sa configuration (aucun email de
        rapport) et un jus à 3,50 €.
        / The test venue, its register singleton, its configuration, a juice.
        """
        connection.set_tenant(self.tenant)
        LaboutikConfiguration.get_solo().save()

        configuration = Configuration.get_solo()
        configuration.fuseau_horaire = "Europe/Paris"
        configuration.rapport_emails = ""
        configuration.save()

        self.tarif_du_jus = creer_tarif_vendu(
            nom="Jus",
            prix_en_euros="3.50",
            taux_tva="20.00",
            methode_caisse=Product.VENTE,
        )

    def _vendre_un_jus_puis_cloturer(self, heure_de_la_vente, heure_de_la_cloture):
        """
        Un jus vendu en espèces à `heure_de_la_vente`, puis la J à `heure_de_la_cloture`.
        Rend la J.
        / One juice sold, then the J. Returns the J.
        """
        with patch("django.utils.timezone.now", return_value=heure_de_la_vente):
            fabriquer_vente_encaissee(
                origine=SaleOrigin.LABOUTIK,
                articles=[
                    {
                        "pricesold": self.tarif_du_jus,
                        "quantite": Decimal("1"),
                        "prix_unitaire": 350,
                        "taux_tva": Decimal("20"),
                    },
                ],
                reglements=[{"moyen": PaymentMethod.CASH, "montant": 350}],
            )
        with patch("django.utils.timezone.now", return_value=heure_de_la_cloture):
            uuid_de_la_j = generer_cloture_pour_tenant(
                schema_name=self.tenant.schema_name,
                niveau=ClotureCaisse.NIVEAU_JOURNALIER,
            )
        return ClotureCaisse.objects.get(uuid=uuid_de_la_j)

    def _sortie_de_verify_clotures(self):
        """Le texte écrit par la commande, pour le lieu de test. / The command output."""
        sortie_de_la_commande = StringIO()
        call_command(
            "verify_clotures",
            f"--tenant={self.tenant.schema_name}",
            stdout=sortie_de_la_commande,
        )
        return sortie_de_la_commande.getvalue()

    def test_verify_clotures_chaine_saine_aucune_anomalie(self):
        """
        Deux J saines : la commande ne signale rien.
        / Two sound J: the command reports nothing.
        """
        self._vendre_un_jus_puis_cloturer(
            heure_de_paris(2026, 3, 10, 10, 0), heure_de_paris(2026, 3, 10, 12, 0)
        )
        self._vendre_un_jus_puis_cloturer(
            heure_de_paris(2026, 3, 10, 13, 0), heure_de_paris(2026, 3, 10, 15, 0)
        )

        texte_de_la_sortie = self._sortie_de_verify_clotures()

        self.assertIn("aucune anomalie", texte_de_la_sortie)

    def test_verify_clotures_signale_une_cloture_alteree(self):
        """
        Le `rapport_json` d'une J est modifié par `update()` (une écriture à la main
        dans la base) : la commande signale l'empreinte fausse de la clôture n° 1.
        / A J's stored report is tampered with: the command flags closure no. 1.
        """
        cloture_j = self._vendre_un_jus_puis_cloturer(
            heure_de_paris(2026, 3, 10, 10, 0), heure_de_paris(2026, 3, 10, 12, 0)
        )
        rapport_altere = dict(cloture_j.rapport_json)
        rapport_altere["chiffre_affaires"] = dict(rapport_altere["chiffre_affaires"])
        rapport_altere["chiffre_affaires"]["total_ttc_en_centimes"] = 1
        ClotureCaisse.objects.filter(pk=cloture_j.pk).update(rapport_json=rapport_altere)

        texte_de_la_sortie = self._sortie_de_verify_clotures()

        self.assertIn("Empreinte fausse", texte_de_la_sortie)
        self.assertIn("clôture n° 1", texte_de_la_sortie)
        self.assertNotIn("aucune anomalie", texte_de_la_sortie)

    def test_verify_clotures_signale_une_j_qui_ne_commence_pas_a_la_fin_de_la_precedente(
        self,
    ):
        """
        Deux J ; le début de la J n° 2 est reculé d'une heure par `update()` (une
        écriture à la main) : les deux J se chevauchent. La commande le signale.
        / J no. 2 does not start where J no. 1 ends: reported.
        """
        self._vendre_un_jus_puis_cloturer(
            heure_de_paris(2026, 3, 10, 10, 0), heure_de_paris(2026, 3, 10, 12, 0)
        )
        deuxieme_j = self._vendre_un_jus_puis_cloturer(
            heure_de_paris(2026, 3, 10, 13, 0), heure_de_paris(2026, 3, 10, 15, 0)
        )
        ClotureCaisse.objects.filter(pk=deuxieme_j.pk).update(
            datetime_debut=heure_de_paris(2026, 3, 10, 11, 0)
        )

        texte_de_la_sortie = self._sortie_de_verify_clotures()

        self.assertIn(
            "Journée discontinue : la clôture n° 2 ne commence pas à la fin de la "
            "clôture n° 1",
            texte_de_la_sortie,
        )

    def test_verify_clotures_signale_une_j_dont_la_premiere_vente_ne_suit_pas(self):
        """
        Deux J ; la première vente de la J n° 2 est écrite n° 3 par `update()` (la
        vente n° 2 n'est plus couverte par aucune J). La commande le signale.
        / J no. 2's first sale does not follow J no. 1's last one: reported.
        """
        self._vendre_un_jus_puis_cloturer(
            heure_de_paris(2026, 3, 10, 10, 0), heure_de_paris(2026, 3, 10, 12, 0)
        )
        deuxieme_j = self._vendre_un_jus_puis_cloturer(
            heure_de_paris(2026, 3, 10, 13, 0), heure_de_paris(2026, 3, 10, 15, 0)
        )
        ClotureCaisse.objects.filter(pk=deuxieme_j.pk).update(numero_premiere_vente=3)

        texte_de_la_sortie = self._sortie_de_verify_clotures()

        self.assertIn(
            "Journée discontinue : la première vente de la clôture n° 2 ne suit pas la "
            "dernière vente de la clôture n° 1",
            texte_de_la_sortie,
        )

    def test_verify_clotures_signale_trou_sequentiel(self):
        """
        Trois J ; la J du milieu est supprimée : la commande signale le trou de
        numérotation.
        / The middle J is deleted: the command flags the numbering gap.
        """
        self._vendre_un_jus_puis_cloturer(
            heure_de_paris(2026, 3, 10, 10, 0), heure_de_paris(2026, 3, 10, 11, 0)
        )
        j_du_milieu = self._vendre_un_jus_puis_cloturer(
            heure_de_paris(2026, 3, 10, 12, 0), heure_de_paris(2026, 3, 10, 13, 0)
        )
        self._vendre_un_jus_puis_cloturer(
            heure_de_paris(2026, 3, 10, 14, 0), heure_de_paris(2026, 3, 10, 15, 0)
        )
        ClotureCaisse.objects.filter(pk=j_du_milieu.pk).delete()

        texte_de_la_sortie = self._sortie_de_verify_clotures()

        self.assertIn("trou", texte_de_la_sortie.lower())
        self.assertNotIn("aucune anomalie", texte_de_la_sortie)
