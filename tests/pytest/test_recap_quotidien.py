"""
tests/pytest/test_recap_quotidien.py
Le récap du matin des admins : un mail par lieu qui résume la veille.
/ The admins' morning recap: one mail per venue summarising yesterday.

LOCALISATION : tests/pytest/test_recap_quotidien.py

Spécification : TECH_DOC/SESSIONS/RECAP_QUOTIDIEN/SPEC.md

Dates de référence : le mardi 13 octobre 2026, heure de Paris (CEST, UTC+2).
« La veille » = lundi 12 octobre.
/ Reference date: Tuesday 13 October 2026, Paris time.

Lancer / Run : make test ARGS="tests/pytest/test_recap_quotidien.py"
"""

import sys

# Le code Django vit dans /DjangoFiles a l'interieur du conteneur.
# / Django code lives in /DjangoFiles inside the container.
sys.path.insert(0, "/DjangoFiles")

import django  # noqa: E402

django.setup()

from datetime import datetime, time  # noqa: E402
from unittest.mock import patch  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

from django.db import connection  # noqa: E402
from django_tenants.test.cases import FastTenantTestCase  # noqa: E402

from BaseBillet.models import Configuration, Event, Membership, Reservation  # noqa: E402
from booking.models import Booking  # noqa: E402
from fabriques_panier import (  # noqa: E402
    creer_adhesion,
    creer_evenement_avec_tarif,
    creer_ressource_avec_tarif,
    creer_utilisateur,
)
from laboutik.models import LaboutikConfiguration  # noqa: E402

FUSEAU_DE_PARIS = ZoneInfo("Europe/Paris")
FUSEAU_UTC = ZoneInfo("UTC")


def heure_de_paris(annee, mois, jour, heure, minute=0):
    """Un moment en heure de Paris. / A moment in Paris time."""
    return datetime(annee, mois, jour, heure, minute, tzinfo=FUSEAU_DE_PARIS)


def heure_utc(annee, mois, jour, heure, minute=0):
    """Un moment en UTC. / A moment in UTC."""
    return datetime(annee, mois, jour, heure, minute, tzinfo=FUSEAU_UTC)


class RecapQuotidienTestCase(FastTenantTestCase):
    """
    Base commune : le lieu de test et sa configuration réécrite à chaque test.
    / Common base: the test venue and its configuration rewritten in every test.
    """

    @classmethod
    def get_test_schema_name(cls):
        return "test_recap_quotidien"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-recap-quotidien.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        """`Client.name` est unique et obligatoire. / Client.name is unique."""
        tenant.name = "Test recap quotidien"

    def setUp(self):
        """
        Le rollback du test précédent a rendu le `search_path` au public. Le cache
        de la configuration (django-solo) survit au rollback : on écrit ici toutes
        les valeurs lues par le récap, puis on sauvegarde.
        / Previous rollback reset search_path; the solo cache survives it, so every
        value read by the recap is written here, then saved.
        """
        connection.set_tenant(self.tenant)
        LaboutikConfiguration.get_solo().save()

        configuration = Configuration.get_solo()
        configuration.fuseau_horaire = "Europe/Paris"
        configuration.heure_de_fermeture = time(2, 0)
        configuration.language = "fr"
        configuration.rapport_emails = ""
        configuration.rapport_periodicite = Configuration.PERIODICITE_NONE
        configuration.email = "lieu@example.org"
        configuration.save()


class TestLesDatesDeCreation(RecapQuotidienTestCase):
    """
    Les champs de date qui rendent « créé hier » et « annulé hier » fiables.
    / The date fields that make "created yesterday" and "cancelled yesterday" reliable.
    """

    def _creer_une_reservation(self):
        utilisateur = creer_utilisateur()
        billetterie = creer_evenement_avec_tarif()
        return Reservation.objects.create(
            user_commande=utilisateur, event=billetterie.evenement
        )

    def test_une_reservation_garde_sa_date_de_creation_quand_on_la_modifie(self):
        # created_at est posé à la création, puis ne bouge plus.
        reservation = self._creer_une_reservation()
        date_de_creation = reservation.created_at
        with patch(
            "django.utils.timezone.now", return_value=heure_de_paris(2026, 10, 14, 9)
        ):
            reservation.save()
        reservation.refresh_from_db()
        assert reservation.created_at is not None
        assert reservation.created_at == date_de_creation

    def test_un_evenement_garde_sa_date_de_creation_quand_on_le_modifie(self):
        evenement = creer_evenement_avec_tarif().evenement
        date_de_creation = evenement.created_at
        with patch(
            "django.utils.timezone.now", return_value=heure_de_paris(2026, 10, 14, 9)
        ):
            evenement.save()
        evenement.refresh_from_db()
        assert evenement.created_at is not None
        assert evenement.created_at == date_de_creation

    def test_annulee_le_est_vide_a_la_creation(self):
        # Réservation, booking, adhésion : annulee_le vaut None tant que rien n'est annulé.
        reservation = self._creer_une_reservation()

        ressource = creer_ressource_avec_tarif()
        booking = Booking.objects.create(
            resource=ressource.ressource,
            user=creer_utilisateur(),
            start_datetime=ressource.debut_du_creneau,
            slot_duration_minutes=60,
            slot_count=1,
        )

        adhesion = creer_adhesion()
        membership = Membership.objects.create(price=adhesion.tarif, user=None)

        assert reservation.annulee_le is None
        assert booking.annulee_le is None
        assert membership.annulee_le is None

    def test_la_configuration_a_un_marqueur_de_recap_vide(self):
        assert Configuration.get_solo().recap_quotidien_traite_le is None
