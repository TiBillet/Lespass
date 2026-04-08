"""
Fixtures autonomes pour les tests de l'app booking.
/ Standalone fixtures for the booking app tests.

LOCALISATION : booking/tests/conftest.py

Ce fichier n'importe pas depuis tests/pytest/conftest.py — les hooks
addoption de ce fichier cassent quand on les importe hors contexte.
/ Does not import from tests/pytest/conftest.py — its addoption hooks
break when imported outside their native context.

Toutes les données de test sont préfixées par TEST_PREFIX.
Les FK utilisent on_delete=PROTECT : les enfants doivent être supprimés
avant leurs parents (pas de cascade).
/ All test data is prefixed with TEST_PREFIX.
FKs use on_delete=PROTECT: children must be deleted before their parents
(no cascade).

Lancement / Run:
    docker exec lespass_django poetry run pytest booking/tests/ -v
"""
import os
import sys

sys.path.insert(0, '/DjangoFiles')

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'TiBillet.settings')
django.setup()

import pytest
from django_tenants.utils import schema_context

from Customers.models import Client


TEST_PREFIX = '[test_booking_models]'
TENANT_SCHEMA = 'lespass'


@pytest.fixture(scope="session")
def django_db_setup():
    """Pas de création de test database — utilise la base dev existante.
    / Skip test database creation — use the existing dev database.
    """
    pass


@pytest.fixture(autouse=True, scope="session")
def _enable_db_access_for_all(django_db_blocker):
    """Désactiver le bloqueur d'accès DB de pytest-django.
    / Disable pytest-django's database blocker.
    """
    django_db_blocker.unblock()
    yield
    django_db_blocker.restore()


@pytest.fixture(scope="module")
def tenant():
    """Le tenant 'lespass'. / The 'lespass' tenant."""
    return Client.objects.get(schema_name=TENANT_SCHEMA)


@pytest.fixture(scope="module")
def test_calendar(tenant):
    """
    Calendrier minimal pour les tests.
    / Minimal calendar for tests.

    LOCALISATION : booking/tests/conftest.py
    """
    from booking.models import Calendar

    with schema_context(TENANT_SCHEMA):
        # get_or_create évite les doublons si le test est relancé sans
        # nettoyage préalable (ex: crash avant cleanup).
        # / get_or_create avoids duplicates if tests are re-run without
        # prior cleanup (e.g. crash before cleanup).
        calendar_for_tests, _created = Calendar.objects.get_or_create(
            name=f'{TEST_PREFIX} Calendar',
        )
        return calendar_for_tests


@pytest.fixture(scope="module")
def test_weekly_opening(tenant):
    """
    WeeklyOpening minimal pour les tests.
    / Minimal WeeklyOpening for tests.

    LOCALISATION : booking/tests/conftest.py
    """
    from booking.models import WeeklyOpening

    with schema_context(TENANT_SCHEMA):
        weekly_opening_for_tests, _created = WeeklyOpening.objects.get_or_create(
            name=f'{TEST_PREFIX} WeeklyOpening',
        )
        return weekly_opening_for_tests


@pytest.fixture(scope="module")
def test_resource(tenant, test_calendar, test_weekly_opening):
    """
    Resource minimale pour les tests.
    / Minimal Resource for tests.

    LOCALISATION : booking/tests/conftest.py
    """
    from booking.models import Resource

    with schema_context(TENANT_SCHEMA):
        resource_for_tests, _created = Resource.objects.get_or_create(
            name=f'{TEST_PREFIX} Resource',
            defaults={
                'calendar': test_calendar,
                'weekly_opening': test_weekly_opening,
            },
        )
        return resource_for_tests


@pytest.fixture(scope="module")
def test_user(tenant):
    """
    Premier utilisateur existant dans le tenant — lecture seule.
    / First existing user in the tenant — read-only.

    LOCALISATION : booking/tests/conftest.py
    """
    from AuthBillet.models import TibilletUser

    with schema_context(TENANT_SCHEMA):
        user = (
            TibilletUser.objects.filter(is_superuser=True).first()
            or TibilletUser.objects.filter(is_active=True).first()
        )
        if user is None:
            raise RuntimeError(
                "Aucun utilisateur trouvé dans le tenant lespass. "
                "Veuillez créer un utilisateur."
            )
        return user


@pytest.fixture(scope="module", autouse=True)
def cleanup_test_data(tenant):
    """
    Supprime toutes les données de test après le module.
    / Deletes all test data after the module.

    LOCALISATION : booking/tests/conftest.py

    Ordre de suppression (on_delete=PROTECT — pas de cascade) :
    Booking → Resource → OpeningEntry → WeeklyOpening
             → ClosedPeriod → Calendar → ResourceGroup
    / Deletion order (on_delete=PROTECT — no cascade):
    Booking → Resource → OpeningEntry → WeeklyOpening
             → ClosedPeriod → Calendar → ResourceGroup
    """
    yield

    with schema_context(TENANT_SCHEMA):
        from booking.models import (
            Booking, Resource, OpeningEntry, WeeklyOpening,
            ClosedPeriod, Calendar, ResourceGroup,
        )

        # Les bookings n'ont pas de champ 'name' — on filtre via la resource.
        # / Bookings have no 'name' field — filter via the resource.
        Booking.objects.filter(resource__name__startswith=TEST_PREFIX).delete()
        Resource.objects.filter(name__startswith=TEST_PREFIX).delete()
        OpeningEntry.objects.filter(weekly_opening__name__startswith=TEST_PREFIX).delete()
        WeeklyOpening.objects.filter(name__startswith=TEST_PREFIX).delete()
        ClosedPeriod.objects.filter(calendar__name__startswith=TEST_PREFIX).delete()
        Calendar.objects.filter(name__startswith=TEST_PREFIX).delete()
        ResourceGroup.objects.filter(name__startswith=TEST_PREFIX).delete()
