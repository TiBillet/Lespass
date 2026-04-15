"""
Tests pour l'annulation d'une réservation depuis /my_account/ (session 13).
/ Tests for booking cancellation from /my_account/ (session 13).

LOCALISATION : booking/tests/test_cancel.py

Couvre les cas définis dans le plan de test session 13.1 :
- cancel : exige une authentification (HTTP 401)
- cancel : supprime la réservation si avant la deadline
- cancel : refuse l'annulation si après la deadline (HTTP 422 + info deadline)
- cancel : refuse si la réservation appartient à un autre membre (HTTP 422)

/ Covers session 13.1 test plan cases:
- cancel: requires authentication (HTTP 401)
- cancel: deletes the booking if before the deadline
- cancel: refuses if past the deadline (HTTP 422 + deadline info)
- cancel: refuses if the booking belongs to another member (HTTP 422)

Lancement / Run:
    docker exec lespass_django poetry run pytest \
        booking/tests/test_cancel.py -v
"""
import datetime
import os
import sys

sys.path.insert(0, '/DjangoFiles')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'TiBillet.settings')

import django
django.setup()

import pytest
from django.test import Client as DjangoClient
from django.utils import timezone
from django_tenants.utils import schema_context


TEST_PREFIX   = '[test_booking_cancel]'
TENANT_SCHEMA = 'lespass'
HOST          = 'lespass.tibillet.localhost'
CANCEL_URL    = '/booking/cancel/'


# ─── Fixtures locales ─────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client_anonyme():
    """
    Client Django anonyme configuré pour le tenant lespass.
    / Anonymous Django test client for the lespass tenant.

    LOCALISATION : booking/tests/test_cancel.py
    """
    return DjangoClient(HTTP_HOST=HOST)


@pytest.fixture(scope="module")
def ressource_pour_cancel(tenant):
    """
    Ressource avec deadline d'annulation de 24h pour les tests.
    / Resource with 24-hour cancellation deadline for tests.

    LOCALISATION : booking/tests/test_cancel.py

    cancellation_deadline_hours=24 : toute réservation commençant dans
    moins de 24h ne peut plus être annulée.
    / cancellation_deadline_hours=24: any booking starting in less than
    24h cannot be cancelled anymore.
    """
    from booking.models import Calendar, WeeklyOpening, Resource

    with schema_context(TENANT_SCHEMA):
        calendrier, _ = Calendar.objects.get_or_create(
            name=f'{TEST_PREFIX} Calendrier',
        )
        planning, _ = WeeklyOpening.objects.get_or_create(
            name=f'{TEST_PREFIX} Planning',
        )
        ressource, _ = Resource.objects.get_or_create(
            name=f'{TEST_PREFIX} Ressource',
            defaults={
                'calendar':                    calendrier,
                'weekly_opening':              planning,
                'capacity':                    10,
                'booking_horizon_days':        28,
                'cancellation_deadline_hours': 24,
            },
        )
        return ressource


@pytest.fixture(scope="module")
def second_user_client(tenant):
    """
    Client Django authentifié comme un deuxième utilisateur de test.
    / Django client authenticated as a second test user.

    LOCALISATION : booking/tests/test_cancel.py

    Utilisé pour vérifier qu'un membre ne peut pas annuler la réservation
    d'un autre membre.
    / Used to verify a member cannot cancel another member's booking.
    """
    from AuthBillet.models import TibilletUser

    with schema_context(TENANT_SCHEMA):
        second_utilisateur, _ = TibilletUser.objects.get_or_create(
            username=f'{TEST_PREFIX}_second_user',
            defaults={
                'email':     'second_user_cancel@tibillet.test',
                'is_active': True,
            },
        )

    client = DjangoClient(HTTP_HOST=HOST)
    client.force_login(second_utilisateur)
    return client


@pytest.fixture(scope="module", autouse=True)
def nettoyage_donnees_de_test(tenant):
    """
    Supprime toutes les données de test après le module.
    / Deletes all test data after the module.

    LOCALISATION : booking/tests/test_cancel.py

    Ordre (on_delete=PROTECT — pas de cascade) :
    Booking → Resource → WeeklyOpening → Calendar
    Le second utilisateur de test est aussi supprimé.
    / Deletion order (on_delete=PROTECT — no cascade):
    Booking → Resource → WeeklyOpening → Calendar
    The second test user is also deleted.
    """
    yield

    with schema_context(TENANT_SCHEMA):
        from booking.models import Booking, Resource, WeeklyOpening, Calendar
        from AuthBillet.models import TibilletUser

        Booking.objects.filter(
            resource__name__startswith=TEST_PREFIX,
        ).delete()
        Resource.objects.filter(name__startswith=TEST_PREFIX).delete()
        WeeklyOpening.objects.filter(name__startswith=TEST_PREFIX).delete()
        Calendar.objects.filter(name__startswith=TEST_PREFIX).delete()
        TibilletUser.objects.filter(
            username__startswith=TEST_PREFIX,
        ).delete()


# ─── Tests ────────────────────────────────────────────────────────────────────

def test_cancel_requires_authentication(client_anonyme):
    """
    Un visiteur non authentifié reçoit HTTP 401.
    / An unauthenticated visitor receives HTTP 401.

    LOCALISATION : booking/tests/test_cancel.py
    """
    reponse = client_anonyme.post(CANCEL_URL, data={'booking_pk': 999})

    assert reponse.status_code == 401


def test_cancel_before_deadline_deletes_booking(
    admin_client,
    test_user,
    ressource_pour_cancel,
):
    """
    Annulation avant la deadline : la réservation est supprimée (HTTP 200).
    / Cancellation before the deadline: booking is deleted (HTTP 200).

    LOCALISATION : booking/tests/test_cancel.py

    La réservation commence dans 7 jours, deadline=24h.
    → L'annulation est autorisée car now() < start_datetime − 24h.
    / The booking starts in 7 days, deadline=24h.
    → Cancellation is allowed because now() < start_datetime − 24h.
    """
    from booking.models import Booking

    with schema_context(TENANT_SCHEMA):
        reservation = Booking.objects.create(
            resource              = ressource_pour_cancel,
            user                  = test_user,
            start_datetime        = timezone.now() + datetime.timedelta(days=7),
            slot_duration_minutes = 60,
            slot_count            = 1,
            status                = Booking.STATUS_CONFIRMED,
        )
        reservation_pk = reservation.pk

    reponse = admin_client.post(CANCEL_URL, data={'booking_pk': reservation_pk})

    assert reponse.status_code == 200

    # La réservation doit avoir été supprimée de la base.
    # / The booking must have been deleted from the database.
    with schema_context(TENANT_SCHEMA):
        assert not Booking.objects.filter(pk=reservation_pk).exists()


def test_cancel_after_deadline_returns_error_with_deadline_info(
    admin_client,
    test_user,
    ressource_pour_cancel,
):
    """
    Annulation après la deadline : HTTP 422, la deadline est dans la réponse.
    / Cancellation after the deadline: HTTP 422, deadline info in the response.

    LOCALISATION : booking/tests/test_cancel.py

    La réservation commence dans 1 heure, deadline=24h.
    → La deadline est dépassée depuis 23h — annulation refusée.
    / The booking starts in 1 hour, deadline=24h.
    → The deadline was exceeded 23 hours ago — cancellation refused.
    """
    from booking.models import Booking

    with schema_context(TENANT_SCHEMA):
        reservation = Booking.objects.create(
            resource              = ressource_pour_cancel,
            user                  = test_user,
            start_datetime        = timezone.now() + datetime.timedelta(hours=1),
            slot_duration_minutes = 60,
            slot_count            = 1,
            status                = Booking.STATUS_CONFIRMED,
        )
        reservation_pk = reservation.pk

    reponse = admin_client.post(CANCEL_URL, data={'booking_pk': reservation_pk})

    assert reponse.status_code == 422

    # La réponse doit mentionner la notion de délai (FR) ou deadline (EN).
    # / The response must mention deadline (FR: délai) or deadline (EN).
    contenu = reponse.content.decode()
    assert 'deadline' in contenu.lower() or 'délai' in contenu.lower()

    with schema_context(TENANT_SCHEMA):
        reservation.delete()


def test_cancel_rejects_booking_owned_by_another_member(
    admin_client,
    second_user_client,
    ressource_pour_cancel,
):
    """
    Un membre ne peut pas annuler la réservation d'un autre membre (HTTP 422).
    / A member cannot cancel another member's booking (HTTP 422).

    LOCALISATION : booking/tests/test_cancel.py
    """
    from booking.models import Booking
    from AuthBillet.models import TibilletUser

    with schema_context(TENANT_SCHEMA):
        second_utilisateur = TibilletUser.objects.get(
            username=f'{TEST_PREFIX}_second_user',
        )
        reservation_autre_membre = Booking.objects.create(
            resource              = ressource_pour_cancel,
            user                  = second_utilisateur,
            start_datetime        = timezone.now() + datetime.timedelta(days=7),
            slot_duration_minutes = 60,
            slot_count            = 1,
            status                = Booking.STATUS_CONFIRMED,
        )
        reservation_pk = reservation_autre_membre.pk

    # admin_client tente d'annuler la réservation du second_utilisateur.
    # / admin_client tries to cancel second_utilisateur's booking.
    reponse = admin_client.post(CANCEL_URL, data={'booking_pk': reservation_pk})

    assert reponse.status_code == 422

    # La réservation de l'autre membre doit toujours exister.
    # / The other member's booking must still exist.
    with schema_context(TENANT_SCHEMA):
        assert Booking.objects.filter(pk=reservation_pk).exists()
        reservation_autre_membre.delete()
