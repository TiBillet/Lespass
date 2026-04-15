"""
Tests pour la page "Mes ressources" dans /my_account/ (session 12).
/ Tests for the "My resources" page in /my_account/ (session 12).

LOCALISATION : booking/tests/test_my_resources.py

Couvre les cas définis dans le plan de test session 12.1 :
- my_resources : exige une authentification (302 vers /)
- my_resources : affiche les réservations 'confirmed' du membre
- my_resources : n'affiche pas les réservations 'new' (panier)
- my_resources : n'affiche pas les réservations des autres membres
- bouton dans index.html : absent quand config.module_booking=False
- bouton dans index.html : présent quand config.module_booking=True

/ Covers session 12.1 test plan cases:
- my_resources: requires authentication (302 to /)
- my_resources: shows the member's 'confirmed' bookings
- my_resources: excludes 'new' (basket) bookings
- my_resources: excludes other members' bookings
- button in index.html: absent when config.module_booking=False
- button in index.html: present when config.module_booking=True

Lancement / Run:
    docker exec lespass_django poetry run pytest \
        booking/tests/test_my_resources.py -v
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


TEST_PREFIX   = '[test_booking_my_resources]'
TENANT_SCHEMA = 'lespass'
HOST          = 'lespass.tibillet.localhost'


# ─── Fixtures locales ─────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client_anonyme():
    """
    Client Django anonyme configuré pour le tenant lespass.
    / Anonymous Django test client for the lespass tenant.

    LOCALISATION : booking/tests/test_my_resources.py
    """
    return DjangoClient(HTTP_HOST=HOST)


@pytest.fixture(scope="module")
def ressource_pour_my_resources(tenant):
    """
    Ressource minimale pour les tests de la page "Mes ressources".
    Capacité = 10, un créneau d'1h le lundi à 10:00.
    / Minimal resource for the "My resources" page tests.
    Capacity = 10, one 1-hour slot on Monday at 10:00.

    LOCALISATION : booking/tests/test_my_resources.py
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
            start_time=datetime.time(10, 0),
            defaults={
                'slot_duration_minutes': 60,
                'slot_count':            1,
            },
        )
        return ressource


@pytest.fixture(scope="module")
def second_user_client(tenant):
    """
    Client Django authentifié comme un deuxième utilisateur de test.
    / Django client authenticated as a second test user.

    LOCALISATION : booking/tests/test_my_resources.py

    Utilisé pour vérifier qu'un membre ne voit pas les réservations d'un autre.
    / Used to verify a member cannot see another member's bookings.
    """
    from AuthBillet.models import TibilletUser

    with schema_context(TENANT_SCHEMA):
        second_utilisateur, _ = TibilletUser.objects.get_or_create(
            username=f'{TEST_PREFIX}_second_user',
            defaults={
                'email':     'second_user_my_resources@tibillet.test',
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

    LOCALISATION : booking/tests/test_my_resources.py

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


# ─── Tests : /my_account/my_resources/ ───────────────────────────────────────

def test_my_resources_requires_authentication(client_anonyme):
    """
    Un visiteur non authentifié est redirigé vers / (HTTP 302).
    Le dispatch() de MyAccount redirige avant toute logique de la vue.
    / An unauthenticated visitor is redirected to / (HTTP 302).
    MyAccount.dispatch() redirects before any view logic.

    LOCALISATION : booking/tests/test_my_resources.py
    """
    reponse = client_anonyme.get('/my_account/my_resources/')

    assert reponse.status_code == 302
    assert reponse['Location'] == '/'


def test_my_resources_shows_confirmed_bookings(
    admin_client,
    test_user,
    ressource_pour_my_resources,
):
    """
    Les réservations 'confirmed' du membre s'affichent sur la page.
    Chaque ligne doit porter data-testid="my-resource-{pk}".
    / The member's 'confirmed' bookings appear on the page.
    Each row must carry data-testid="my-resource-{pk}".

    LOCALISATION : booking/tests/test_my_resources.py
    """
    from booking.models import Booking

    with schema_context(TENANT_SCHEMA):
        # Nettoie les réservations existantes pour ce test.
        # / Clean up any pre-existing bookings for this test.
        Booking.objects.filter(
            resource=ressource_pour_my_resources,
            user=test_user,
        ).delete()
        reservation_confirmee = Booking.objects.create(
            resource              = ressource_pour_my_resources,
            user                  = test_user,
            start_datetime        = timezone.now() + datetime.timedelta(days=7),
            slot_duration_minutes = 60,
            slot_count            = 1,
            status                = Booking.STATUS_CONFIRMED,
        )

    reponse = admin_client.get('/my_account/my_resources/')

    assert reponse.status_code == 200

    # Le nom de la ressource et le data-testid de la ligne doivent être présents.
    # / The resource name and the row data-testid must be present.
    contenu = reponse.content.decode()
    assert ressource_pour_my_resources.name in contenu
    assert f'data-testid="my-resource-{reservation_confirmee.pk}"' in contenu

    with schema_context(TENANT_SCHEMA):
        reservation_confirmee.delete()


def test_my_resources_excludes_new_bookings(
    admin_client,
    test_user,
    ressource_pour_my_resources,
):
    """
    Les réservations 'new' (panier) n'apparaissent PAS sur la page.
    / 'new' (basket) bookings do NOT appear on the page.

    LOCALISATION : booking/tests/test_my_resources.py
    """
    from booking.models import Booking

    with schema_context(TENANT_SCHEMA):
        Booking.objects.filter(
            resource=ressource_pour_my_resources,
            user=test_user,
        ).delete()
        reservation_new = Booking.objects.create(
            resource              = ressource_pour_my_resources,
            user                  = test_user,
            start_datetime        = timezone.now() + datetime.timedelta(days=7),
            slot_duration_minutes = 60,
            slot_count            = 1,
            status                = Booking.STATUS_NEW,
        )

    reponse = admin_client.get('/my_account/my_resources/')

    assert reponse.status_code == 200

    # La réservation 'new' ne doit pas apparaître dans la liste.
    # / The 'new' booking must not appear in the list.
    contenu = reponse.content.decode()
    assert f'data-testid="my-resource-{reservation_new.pk}"' not in contenu

    with schema_context(TENANT_SCHEMA):
        reservation_new.delete()


def test_my_resources_excludes_other_members_bookings(
    admin_client,
    test_user,
    second_user_client,
    ressource_pour_my_resources,
):
    """
    Les réservations 'confirmed' d'un autre membre ne s'affichent pas.
    / Another member's 'confirmed' bookings do not appear.

    LOCALISATION : booking/tests/test_my_resources.py
    """
    from booking.models import Booking
    from AuthBillet.models import TibilletUser

    with schema_context(TENANT_SCHEMA):
        second_utilisateur = TibilletUser.objects.get(
            username=f'{TEST_PREFIX}_second_user',
        )
        reservation_autre_membre = Booking.objects.create(
            resource              = ressource_pour_my_resources,
            user                  = second_utilisateur,
            start_datetime        = timezone.now() + datetime.timedelta(days=8),
            slot_duration_minutes = 60,
            slot_count            = 1,
            status                = Booking.STATUS_CONFIRMED,
        )

    reponse = admin_client.get('/my_account/my_resources/')

    assert reponse.status_code == 200

    # La réservation de l'autre membre ne doit pas apparaître.
    # / The other member's booking must not appear.
    contenu = reponse.content.decode()
    assert f'data-testid="my-resource-{reservation_autre_membre.pk}"' not in contenu

    with schema_context(TENANT_SCHEMA):
        reservation_autre_membre.delete()


# ─── Tests : bouton dans /my_account/ ────────────────────────────────────────

def test_my_resources_button_visible_when_module_enabled(admin_client, tenant):
    """
    Le bouton 'Mes ressources' s'affiche dans /my_account/ quand
    config.module_booking est True.
    / The 'My resources' button appears in /my_account/ when
    config.module_booking is True.

    LOCALISATION : booking/tests/test_my_resources.py
    """
    from BaseBillet.models import Configuration

    with schema_context(TENANT_SCHEMA):
        config = Configuration.get_solo()
        valeur_originale = config.module_booking
        config.module_booking = True
        config.save(update_fields=['module_booking'])

    try:
        reponse = admin_client.get('/my_account/')
        assert reponse.status_code == 200
        contenu = reponse.content.decode()
        # Le bouton doit porter data-testid="btn-my-resources".
        # / The button must carry data-testid="btn-my-resources".
        assert 'data-testid="btn-my-resources"' in contenu
    finally:
        # Restaure la valeur d'origine quelle que soit l'issue du test.
        # / Restore the original value regardless of the test outcome.
        with schema_context(TENANT_SCHEMA):
            config.module_booking = valeur_originale
            config.save(update_fields=['module_booking'])


def test_my_resources_button_hidden_when_module_disabled(admin_client, tenant):
    """
    Le bouton 'Mes ressources' est absent de /my_account/ quand
    config.module_booking est False.
    / The 'My resources' button is absent from /my_account/ when
    config.module_booking is False.

    LOCALISATION : booking/tests/test_my_resources.py
    """
    from BaseBillet.models import Configuration

    with schema_context(TENANT_SCHEMA):
        config = Configuration.get_solo()
        valeur_originale = config.module_booking
        config.module_booking = False
        config.save(update_fields=['module_booking'])

    try:
        reponse = admin_client.get('/my_account/')
        assert reponse.status_code == 200
        contenu = reponse.content.decode()
        assert 'data-testid="btn-my-resources"' not in contenu
    finally:
        with schema_context(TENANT_SCHEMA):
            config.module_booking = valeur_originale
            config.save(update_fields=['module_booking'])
