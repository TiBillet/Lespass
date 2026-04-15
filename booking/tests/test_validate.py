"""
Tests pour retirer du panier et valider le panier (session 11).
/ Tests for remove-from-basket and validate-basket actions (session 11).

LOCALISATION : booking/tests/test_validate.py

Couvre les cas définis dans le plan de test session 11.1 :
- remove_from_basket : supprime une réservation 'new' de l'utilisateur
- remove_from_basket : rejette une réservation 'confirmed'
- remove_from_basket : rejette une réservation d'un autre membre
- remove_from_basket : exige une authentification
- validate_basket : passe toutes les réservations 'new' à 'confirmed'
- validate_basket : retourne 422 si le panier est vide
- validate_basket : exige une authentification

/ Covers session 11.1 test plan cases:
- remove_from_basket: deletes a 'new' booking owned by the user
- remove_from_basket: rejects a 'confirmed' booking
- remove_from_basket: rejects a booking owned by another member
- remove_from_basket: requires authentication
- validate_basket: moves all 'new' bookings to 'confirmed'
- validate_basket: returns 422 when basket is empty
- validate_basket: requires authentication

Lancement / Run:
    docker exec lespass_django poetry run pytest \
        booking/tests/test_validate.py -v
"""
import datetime
import json
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


TEST_PREFIX   = '[test_booking_validate]'
TENANT_SCHEMA = 'lespass'
HOST          = 'lespass.tibillet.localhost'


# ─── Helpers ────────────────────────────────────────────────────────────────

def _prochain_lundi():
    """
    Retourne la prochaine occurrence du lundi en excluant aujourd'hui.
    / Returns the next Monday, excluding today.
    """
    aujourd_hui = datetime.date.today()
    # lundi = 0 ; si aujourd'hui est lundi, on prend le lundi suivant.
    # / Monday = 0; if today is Monday, skip to next Monday.
    jours_avant_lundi = 0 - aujourd_hui.weekday()
    if jours_avant_lundi <= 0:
        jours_avant_lundi += 7
    return aujourd_hui + datetime.timedelta(days=jours_avant_lundi)


# ─── Fixtures locales ────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client_anonyme():
    """
    Client Django anonyme configuré pour le tenant lespass.
    / Anonymous Django test client configured for the lespass tenant.

    LOCALISATION : booking/tests/test_validate.py
    """
    return DjangoClient(HTTP_HOST=HOST)


@pytest.fixture(scope="module")
def ressource_pour_validation(tenant):
    """
    Ressource avec 3 créneaux consécutifs d'1h chaque lundi à 09:00.
    Capacité = 10, horizon = 28 jours.
    / Resource with 3 consecutive 1-hour slots every Monday at 09:00.
    Capacity = 10, horizon = 28 days.

    LOCALISATION : booking/tests/test_validate.py

    Utilisée pour tous les tests de cette suite.
    / Used by all tests in this suite.
    """
    from booking.models import Calendar, WeeklyOpening, Resource, OpeningEntry

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
                'calendar':             calendrier,
                'weekly_opening':       planning,
                'capacity':             10,
                'booking_horizon_days': 28,
            },
        )
        OpeningEntry.objects.get_or_create(
            weekly_opening=planning,
            weekday=0,
            start_time=datetime.time(9, 0),
            defaults={
                'slot_duration_minutes': 60,
                'slot_count':            3,
            },
        )
        return ressource


@pytest.fixture(scope="module")
def second_user_client(tenant):
    """
    Client Django authentifié comme un deuxième utilisateur (non superutilisateur).
    / Django client authenticated as a second user (non-superuser).

    LOCALISATION : booking/tests/test_validate.py

    Utilisé pour tester le rejet des réservations appartenant à un autre membre.
    / Used to test rejection of bookings owned by another member.
    """
    from AuthBillet.models import TibilletUser

    with schema_context(TENANT_SCHEMA):
        # Crée un second utilisateur de test si il n'existe pas encore.
        # / Create a second test user if it does not exist yet.
        second_utilisateur, _ = TibilletUser.objects.get_or_create(
            username=f'{TEST_PREFIX}_second_user',
            defaults={
                'email':     f'second_user_validate_test@tibillet.test',
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

    LOCALISATION : booking/tests/test_validate.py

    Ordre (on_delete=PROTECT — pas de cascade) :
    Booking → Resource → OpeningEntry → WeeklyOpening → Calendar
    Le second utilisateur de test est aussi supprimé.
    / Deletion order (on_delete=PROTECT — no cascade):
    Booking → Resource → OpeningEntry → WeeklyOpening → Calendar
    The second test user is also deleted.
    """
    yield

    with schema_context(TENANT_SCHEMA):
        from booking.models import (
            Booking, Resource, OpeningEntry, WeeklyOpening, Calendar,
        )
        from AuthBillet.models import TibilletUser

        Booking.objects.filter(
            resource__name__startswith=TEST_PREFIX,
        ).delete()
        Resource.objects.filter(name__startswith=TEST_PREFIX).delete()
        OpeningEntry.objects.filter(
            weekly_opening__name__startswith=TEST_PREFIX,
        ).delete()
        WeeklyOpening.objects.filter(name__startswith=TEST_PREFIX).delete()
        Calendar.objects.filter(name__startswith=TEST_PREFIX).delete()
        TibilletUser.objects.filter(
            username__startswith=TEST_PREFIX,
        ).delete()


# ─── Tests : remove_from_basket ─────────────────────────────────────────────

def test_remove_from_basket_deletes_new_booking(
    admin_client,
    test_user,
    ressource_pour_validation,
):
    """
    Un POST valide supprime la réservation 'new' et retourne HTTP 200.
    / A valid POST deletes the 'new' booking and returns HTTP 200.

    LOCALISATION : booking/tests/test_validate.py
    """
    from booking.models import Booking

    prochain_lundi = _prochain_lundi()
    fuseau_horaire = timezone.get_current_timezone()
    start_dt = timezone.make_aware(
        datetime.datetime.combine(prochain_lundi, datetime.time(9, 0)),
        fuseau_horaire,
    )

    with schema_context(TENANT_SCHEMA):
        pk_ressource = ressource_pour_validation.pk
        # Crée une réservation 'new' à supprimer via l'action.
        # / Create a 'new' booking to delete via the action.
        reservation = Booking.objects.create(
            resource              = ressource_pour_validation,
            user                  = test_user,
            start_datetime        = start_dt,
            slot_duration_minutes = 60,
            slot_count            = 1,
            status                = Booking.STATUS_NEW,
        )
        pk_reservation = reservation.pk

    reponse = admin_client.post(
        f'/booking/{pk_ressource}/remove_from_basket/',
        data=json.dumps({'booking_pk': pk_reservation}),
        content_type='application/json',
    )

    assert reponse.status_code == 200

    with schema_context(TENANT_SCHEMA):
        # La réservation doit être supprimée de la base.
        # / The booking must be deleted from the database.
        assert not Booking.objects.filter(pk=pk_reservation).exists()


def test_remove_from_basket_rejects_confirmed_booking(
    admin_client,
    test_user,
    ressource_pour_validation,
):
    """
    Une réservation 'confirmed' ne peut pas être retirée du panier (HTTP 422).
    / A 'confirmed' booking cannot be removed from the basket (HTTP 422).

    LOCALISATION : booking/tests/test_validate.py

    Seules les réservations 'new' peuvent être retirées du panier sans remboursement.
    Les réservations 'confirmed' passent par le flux d'annulation (session 13).
    / Only 'new' bookings can be removed from the basket without refund.
    'Confirmed' bookings go through the cancellation flow (session 13).
    """
    from booking.models import Booking

    prochain_lundi = _prochain_lundi()
    fuseau_horaire = timezone.get_current_timezone()
    start_dt = timezone.make_aware(
        datetime.datetime.combine(prochain_lundi, datetime.time(10, 0)),
        fuseau_horaire,
    )

    with schema_context(TENANT_SCHEMA):
        pk_ressource = ressource_pour_validation.pk
        reservation = Booking.objects.create(
            resource              = ressource_pour_validation,
            user                  = test_user,
            start_datetime        = start_dt,
            slot_duration_minutes = 60,
            slot_count            = 1,
            status                = Booking.STATUS_CONFIRMED,
        )
        pk_reservation = reservation.pk

    reponse = admin_client.post(
        f'/booking/{pk_ressource}/remove_from_basket/',
        data=json.dumps({'booking_pk': pk_reservation}),
        content_type='application/json',
    )

    assert reponse.status_code == 422

    with schema_context(TENANT_SCHEMA):
        # La réservation doit toujours exister.
        # / The booking must still exist.
        assert Booking.objects.filter(pk=pk_reservation).exists()
        Booking.objects.filter(pk=pk_reservation).delete()


def test_remove_from_basket_rejects_booking_owned_by_another_member(
    second_user_client,
    test_user,
    ressource_pour_validation,
):
    """
    Un membre ne peut pas retirer la réservation d'un autre membre (HTTP 422).
    / A member cannot remove another member's booking (HTTP 422).

    LOCALISATION : booking/tests/test_validate.py
    """
    from booking.models import Booking

    prochain_lundi = _prochain_lundi()
    fuseau_horaire = timezone.get_current_timezone()
    start_dt = timezone.make_aware(
        datetime.datetime.combine(prochain_lundi, datetime.time(11, 0)),
        fuseau_horaire,
    )

    with schema_context(TENANT_SCHEMA):
        pk_ressource = ressource_pour_validation.pk
        # La réservation appartient à test_user.
        # / The booking belongs to test_user.
        reservation = Booking.objects.create(
            resource              = ressource_pour_validation,
            user                  = test_user,
            start_datetime        = start_dt,
            slot_duration_minutes = 60,
            slot_count            = 1,
            status                = Booking.STATUS_NEW,
        )
        pk_reservation = reservation.pk

    # second_user_client tente de retirer la réservation de test_user.
    # / second_user_client tries to remove test_user's booking.
    reponse = second_user_client.post(
        f'/booking/{pk_ressource}/remove_from_basket/',
        data=json.dumps({'booking_pk': pk_reservation}),
        content_type='application/json',
    )

    assert reponse.status_code == 422

    with schema_context(TENANT_SCHEMA):
        assert Booking.objects.filter(pk=pk_reservation).exists()
        Booking.objects.filter(pk=pk_reservation).delete()


def test_remove_from_basket_requires_authentication(
    client_anonyme,
    test_user,
    ressource_pour_validation,
):
    """
    Un utilisateur non authentifié reçoit HTTP 401.
    / An unauthenticated user receives HTTP 401.

    LOCALISATION : booking/tests/test_validate.py
    """
    from booking.models import Booking

    prochain_lundi = _prochain_lundi()
    fuseau_horaire = timezone.get_current_timezone()
    start_dt = timezone.make_aware(
        datetime.datetime.combine(prochain_lundi, datetime.time(9, 0)),
        fuseau_horaire,
    )

    with schema_context(TENANT_SCHEMA):
        pk_ressource = ressource_pour_validation.pk
        reservation = Booking.objects.create(
            resource              = ressource_pour_validation,
            user                  = test_user,
            start_datetime        = start_dt,
            slot_duration_minutes = 60,
            slot_count            = 1,
            status                = Booking.STATUS_NEW,
        )
        pk_reservation = reservation.pk

    reponse = client_anonyme.post(
        f'/booking/{pk_ressource}/remove_from_basket/',
        data=json.dumps({'booking_pk': pk_reservation}),
        content_type='application/json',
    )

    assert reponse.status_code == 401

    with schema_context(TENANT_SCHEMA):
        Booking.objects.filter(pk=pk_reservation).delete()


# ─── Tests : validate_basket ────────────────────────────────────────────────

def test_validate_basket_moves_new_bookings_to_confirmed(
    admin_client,
    test_user,
    ressource_pour_validation,
):
    """
    Valider le panier passe toutes les réservations 'new' à 'confirmed'.
    / Validating the basket moves all 'new' bookings to 'confirmed'.

    LOCALISATION : booking/tests/test_validate.py

    Le paiement est reporté — la transition directe new → confirmed est
    le comportement attendu pour cette session.
    / Payment is deferred — the direct new → confirmed transition is the
    expected behaviour for this session.
    """
    from booking.models import Booking

    prochain_lundi = _prochain_lundi()
    fuseau_horaire = timezone.get_current_timezone()

    with schema_context(TENANT_SCHEMA):
        # Supprime les éventuelles réservations 'new' résiduelles pour ce test.
        # / Delete any residual 'new' bookings for this test.
        Booking.objects.filter(
            user=test_user, status=Booking.STATUS_NEW,
        ).delete()

        # Crée deux réservations 'new' consécutives sur des créneaux différents.
        # / Create two consecutive 'new' bookings on different slots.
        start_dt_creneau_1 = timezone.make_aware(
            datetime.datetime.combine(prochain_lundi, datetime.time(9, 0)),
            fuseau_horaire,
        )
        start_dt_creneau_2 = timezone.make_aware(
            datetime.datetime.combine(prochain_lundi, datetime.time(10, 0)),
            fuseau_horaire,
        )
        reservation_1 = Booking.objects.create(
            resource              = ressource_pour_validation,
            user                  = test_user,
            start_datetime        = start_dt_creneau_1,
            slot_duration_minutes = 60,
            slot_count            = 1,
            status                = Booking.STATUS_NEW,
        )
        reservation_2 = Booking.objects.create(
            resource              = ressource_pour_validation,
            user                  = test_user,
            start_datetime        = start_dt_creneau_2,
            slot_duration_minutes = 60,
            slot_count            = 1,
            status                = Booking.STATUS_NEW,
        )

    reponse = admin_client.post('/booking/validate_basket/')

    assert reponse.status_code == 200

    with schema_context(TENANT_SCHEMA):
        # Les deux réservations doivent être passées à 'confirmed'.
        # / Both bookings must now be 'confirmed'.
        reservation_1.refresh_from_db()
        reservation_2.refresh_from_db()
        assert reservation_1.status == Booking.STATUS_CONFIRMED
        assert reservation_2.status == Booking.STATUS_CONFIRMED
        Booking.objects.filter(
            pk__in=[reservation_1.pk, reservation_2.pk],
        ).delete()


def test_validate_empty_basket_returns_error(
    admin_client,
    test_user,
):
    """
    Valider un panier vide retourne HTTP 422.
    / Validating an empty basket returns HTTP 422.

    LOCALISATION : booking/tests/test_validate.py
    """
    from booking.models import Booking

    with schema_context(TENANT_SCHEMA):
        # S'assure qu'il n'y a aucune réservation 'new' pour cet utilisateur.
        # / Ensure there are no 'new' bookings for this user.
        Booking.objects.filter(
            user=test_user, status=Booking.STATUS_NEW,
        ).delete()

    reponse = admin_client.post('/booking/validate_basket/')

    assert reponse.status_code == 422


def test_validate_basket_requires_authentication(client_anonyme):
    """
    Un utilisateur non authentifié reçoit HTTP 401.
    / An unauthenticated user receives HTTP 401.

    LOCALISATION : booking/tests/test_validate.py
    """
    reponse = client_anonyme.post('/booking/validate_basket/')

    assert reponse.status_code == 401
