"""
tests/pytest/test_demo_recap_de_la_veille.py
La démo d'un flush, côté récap du matin : l'activité d'hier de quatre personnes
différentes, reprise par la J, puis le récap envoyé à l'admin du lieu.
/ The flush demo, morning-recap side: yesterday's activity of four different people,
taken up by the J, then the recap sent to the venue admin.

LOCALISATION : tests/pytest/test_demo_recap_de_la_veille.py

RÈGLES MÉTIER TESTÉES
- `_seed_ventes_de_la_veille` (demo_data_v2) écrit les ventes d'hier, puis l'activité
  des quatre personnes `recap-*@example.com`, puis la J : chaque personne a au moins
  un objet daté d'hier, et la J reprend la vente de David.
- Le récap de la démo a les rubriques adhésions, adhésions en attente, réservations,
  réservations de ressources, inscriptions bénévoles et annulations, et une J.
- Un second passage n'écrit rien (la J existe).
- Un planning introuvable donne une phrase « sautée », pas d'erreur.
- `_envoyer_le_recap_de_demo` envoie UN mail à l'admin du lieu, avec le PDF de la J.
/ Business rules: four people with activity dated yesterday, the J takes up David's
sale, the recap has the expected sections, a second run writes nothing, a missing
planning is skipped, the demo recap goes to the venue admin with the J's PDF.

Schéma dédié (`FastTenantTestCase`) : le test écrit des ventes et une clôture.
La commande cherche le lieu « lespass » : le test lui donne le lieu de test, par une
vraie fonction de filtre (pas de mock rendu).
/ Dedicated schema. The command looks up "lespass": the test hands it the test venue
through a real filter function.
"""

import sys

# Le code Django vit dans /DjangoFiles a l'interieur du conteneur.
# / Django code lives in /DjangoFiles inside the container.
sys.path.insert(0, "/DjangoFiles")

import django  # noqa: E402

django.setup()

from datetime import time, timedelta  # noqa: E402
from decimal import Decimal  # noqa: E402
from io import StringIO  # noqa: E402
from unittest.mock import patch  # noqa: E402

import requests  # noqa: E402
from django.core.management import call_command  # noqa: E402
from django.db import connection  # noqa: E402
from django.utils import timezone  # noqa: E402
from django_tenants.test.cases import FastTenantTestCase  # noqa: E402

from Administration.management.commands._demo_data_v2_recap import (  # noqa: E402
    seed_activite_de_la_veille_pour_le_recap,
)
from Administration.management.commands.demo_data_v2 import Command  # noqa: E402
from Administration.recap_quotidien import (  # noqa: E402
    fenetre_de_la_veille,
    preparer_le_recap_du_lieu,
)
from AuthBillet.models import TibilletUser  # noqa: E402
from BaseBillet.models import (  # noqa: E402
    Configuration,
    Event,
    Membership,
    Price,
    Product,
    Reservation,
    Tva,
)
from BaseBillet.models_vente import Vente  # noqa: E402
from booking.models import Booking, InscriptionBenevole, PlanningBenevole  # noqa: E402
from comptabilite.models import ClotureCaisse  # noqa: E402
from comptabilite.ventilation import ecritures_de_l_export  # noqa: E402
from Customers.models import Client  # noqa: E402
from laboutik.models import LaboutikConfiguration  # noqa: E402


EMAILS_DES_PERSONNES_DE_DEMO = [
    "recap-alice@example.com",
    "recap-bruno@example.com",
    "recap-chloe@example.com",
    "recap-david@example.com",
]

EMAIL_DE_L_ADMIN_DU_LIEU = "admin-du-lieu-recap@example.org"


class FauxMailer:
    """
    Remplace `CeleryMailerClass` : garde les arguments de chaque appel, ne rend rien.
    / Replaces CeleryMailerClass: keeps each call's arguments, renders nothing.
    """

    appels = []

    def __init__(self, **arguments):
        FauxMailer.appels.append(arguments)

    def send(self):
        return True


class TestDemoRecapDeLaVeille(FastTenantTestCase):
    """
    L'activité d'hier de la démo et son récap. / The demo's yesterday activity and recap.
    """

    @classmethod
    def get_test_schema_name(cls):
        return "test_demo_recap_veille"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-demo-recap-veille.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        """`Client.name` est unique et obligatoire. / Client.name is unique."""
        tenant.name = "Test demo recap de la veille"

    def setUp(self):
        """
        Le lieu (Paris, sans TVA par défaut, aucun mail de rapport), la caisse de démo,
        le concert et l'adhésion du mode complet, les ressources et plannings
        bénévoles (`create_booking_fixtures`, sans téléchargement d'image), et un admin.
        / The venue, the demo POS, the concert and membership fixtures, the booking
        fixtures (no image download), and an admin.
        """
        connection.set_tenant(self.tenant)

        # Le singleton de la caisse porte la clé des empreintes (tests/PIEGES.md 9.86).
        # / The register singleton holds the fingerprint key.
        LaboutikConfiguration.get_solo().save()

        configuration = Configuration.get_solo()
        configuration.fuseau_horaire = "Europe/Paris"
        configuration.heure_de_fermeture = time(2, 0)
        configuration.vat_taxe = Decimal("0")
        configuration.language = "fr"
        configuration.email = "lieu@example.org"
        configuration.rapport_emails = ""
        configuration.rapport_periodicite = Configuration.PERIODICITE_NONE
        configuration.save()

        call_command("create_test_pos_data", schema=self.tenant.schema_name)

        # Les fixtures du mode complet de `demo_data_v2`.
        # / The full-mode fixtures of demo_data_v2.
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
        Price.objects.create(
            product=adhesion, name="Plein tarif", prix=Decimal("30.00")
        )

        # Ressources et plannings bénévoles, sans appel réseau.
        # / Resources and volunteer plannings, without network call.
        with patch(
            "booking.management.commands.create_booking_fixtures.requests.get",
            side_effect=requests.RequestException("hors ligne"),
        ):
            call_command("create_booking_fixtures", stdout=StringIO())

        administrateur, _cree = TibilletUser.objects.get_or_create(
            email=EMAIL_DE_L_ADMIN_DU_LIEU,
            defaults={"username": EMAIL_DE_L_ADMIN_DU_LIEU, "is_active": True},
        )
        administrateur.client_admin.add(self.tenant)

        FauxMailer.appels = []

    def _filtre_qui_rend_le_lieu_de_test(self):
        """
        Une vraie fonction de filtre : `schema_name="lespass"` devient le schéma de test.
        / A real filter function: schema_name="lespass" becomes the test schema.
        """
        filtre_d_origine = Client.objects.filter
        schema_de_test = self.tenant.schema_name

        def filtrer(*arguments, **filtres):
            if filtres.get("schema_name") == "lespass":
                filtres["schema_name"] = schema_de_test
            return filtre_d_origine(*arguments, **filtres)

        return filtrer

    def _lancer_le_seed_du_flush(self):
        """
        `_seed_ventes_de_la_veille` de la commande, sur le lieu de test.
        / The command's `_seed_ventes_de_la_veille`, on the test venue.
        """
        sortie = StringIO()
        commande = Command(stdout=sortie)
        with patch.object(
            Client.objects, "filter", new=self._filtre_qui_rend_le_lieu_de_test()
        ):
            commande._seed_ventes_de_la_veille({})
        connection.set_tenant(self.tenant)
        return sortie.getvalue()

    def _hier_en_heure_du_lieu(self):
        fuseau_du_lieu = Configuration.get_solo().get_tzinfo()
        return (
            timezone.localtime(timezone.now(), fuseau_du_lieu) - timedelta(days=1)
        ).date()

    def _est_d_hier(self, moment):
        fuseau_du_lieu = Configuration.get_solo().get_tzinfo()
        return (
            timezone.localtime(moment, fuseau_du_lieu).date()
            == self._hier_en_heure_du_lieu()
        )

    def _le_recap_de_demo(self):
        maintenant = timezone.now()
        fuseau_du_lieu = Configuration.get_solo().get_tzinfo()
        debut_de_la_veille, _fin = fenetre_de_la_veille(maintenant, fuseau_du_lieu)
        return preparer_le_recap_du_lieu(maintenant, debut_de_la_veille, maintenant)

    def test_quatre_personnes_differentes_ont_une_activite_d_hier(self):
        self._lancer_le_seed_du_flush()

        for email in EMAILS_DES_PERSONNES_DE_DEMO:
            personne = TibilletUser.objects.get(email=email)
            moments = []
            for adhesion in Membership.objects.filter(user=personne):
                moments.append(adhesion.date_added)
            for reservation in Reservation.objects.filter(user_commande=personne):
                moments.append(reservation.created_at)
            for booking in Booking.objects.filter(user=personne):
                moments.append(booking.booked_at)
            for inscription in InscriptionBenevole.objects.filter(user=personne):
                moments.append(inscription.created_at)
            for vente in Vente.objects.filter(
                client=personne, statut=Vente.Statut.REGLEE
            ):
                moments.append(vente.datetime_encaissement)

            assert len(moments) > 0, f"{email} n'a aucune activité"
            for moment in moments:
                assert self._est_d_hier(moment), f"{email} : {moment} n'est pas d'hier"

    def test_le_recap_de_demo_a_toutes_les_rubriques_attendues(self):
        self._lancer_le_seed_du_flush()

        recap = self._le_recap_de_demo()

        cles_des_rubriques = []
        for rubrique in recap["rubriques"]:
            cles_des_rubriques.append(rubrique["cle"])
        for cle_attendue in [
            "nouvelles_adhesions",
            "adhesions_en_attente",
            "nouvelles_reservations",
            "nouvelles_reservations_de_ressources",
            "nouvelles_inscriptions_benevoles",
            "annulations",
        ]:
            assert cle_attendue in cles_des_rubriques, cle_attendue
        assert len(recap["clotures"]) == 1

    def test_la_j_reprend_les_ventes_des_personnes_de_demo(self):
        self._lancer_le_seed_du_flush()

        cloture_j = ClotureCaisse.objects.get(niveau=ClotureCaisse.NIVEAU_JOURNALIER)
        for email in [
            "recap-alice@example.com",
            "recap-bruno@example.com",
            "recap-david@example.com",
        ]:
            ventes_de_la_personne = Vente.objects.filter(
                client__email=email, statut=Vente.Statut.REGLEE
            )
            assert ventes_de_la_personne.exists(), email
            for vente in ventes_de_la_personne:
                assert (
                    cloture_j.numero_premiere_vente
                    <= vente.numero
                    <= cloture_j.numero_derniere_vente
                ), email

        # La J reste exportable (journal ADMIN de la salle payée sur place compris).
        # / The J stays exportable (including the ADMIN journal of the room paid on site).
        journaux = []
        for ecriture in ecritures_de_l_export(cloture_j)["ecritures"]:
            journaux.append(ecriture["journal"])
        assert journaux == ["ADMIN", "BAR", "WEB"]

    def test_les_annulations_et_le_booking_de_la_demo(self):
        """
        David : sa réservation de concert est annulée hier. Bruno : la « Petite salle »,
        payée sur place (une ligne en espèces liée au booking).
        / David's concert booking cancelled yesterday; Bruno's small room paid on site.
        """
        self._lancer_le_seed_du_flush()

        reservation_annulee = Reservation.objects.get(
            user_commande__email="recap-david@example.com", status=Reservation.CANCELED
        )
        assert self._est_d_hier(reservation_annulee.annulee_le)

        booking_de_bruno = Booking.objects.get(user__email="recap-bruno@example.com")
        assert booking_de_bruno.resource.product.name == "Petite salle"
        assert booking_de_bruno.status == Booking.PAID_BY_USER
        assert (
            booking_de_bruno.lignearticles.filter(
                vente__statut=Vente.Statut.REGLEE
            ).count()
            == 1
        )

    def test_un_second_passage_n_ecrit_rien(self):
        self._lancer_le_seed_du_flush()
        nombre_d_adhesions = Membership.objects.count()

        second_resultat = seed_activite_de_la_veille_pour_le_recap()

        assert second_resultat["ecrites"] == []
        assert Membership.objects.count() == nombre_d_adhesions

    def test_un_planning_introuvable_est_saute_sans_erreur(self):
        PlanningBenevole.objects.filter(slug="festival").delete()

        resultat = seed_activite_de_la_veille_pour_le_recap()

        assert len(resultat["sautees"]) == 1
        assert "Festival" in resultat["sautees"][0]
        assert not InscriptionBenevole.objects.filter(
            user__email="recap-chloe@example.com"
        ).exists()

    def test_le_recap_de_demo_part_a_l_admin(self):
        self._lancer_le_seed_du_flush()

        sortie = StringIO()
        commande = Command(stdout=sortie)
        with patch.object(
            Client.objects, "filter", new=self._filtre_qui_rend_le_lieu_de_test()
        ):
            with patch(
                "Administration.recap_quotidien.CeleryMailerClass", new=FauxMailer
            ):
                commande._envoyer_le_recap_de_demo({})

        assert len(FauxMailer.appels) == 1
        arguments_du_mail = FauxMailer.appels[0]
        assert EMAIL_DE_L_ADMIN_DU_LIEU in arguments_du_mail["email"]
        noms_des_fichiers = list(arguments_du_mail["attached_files"].keys())
        assert len(noms_des_fichiers) == 1
        assert noms_des_fichiers[0].endswith(".pdf")
        assert "Récap envoyé à" in sortie.getvalue()
        # Le marqueur du récap horaire n'est pas posé par la démo.
        # / The hourly recap marker is not set by the demo.
        assert Configuration.objects.get().recap_quotidien_traite_le is None
