"""
Tests de la vue de détail d'une ressource de réservation.
/ Tests for the resource booking detail view.

LOCALISATION : booking/tests/test_views_resource.py

Couvre les cas définis dans le plan de test session 8b :
- Accès public sans authentification
- 404 pour une ressource inconnue
- Nom de la ressource visible dans la page
- Tous les créneaux de l'horizon sont affichés (pas de slice à 5)
- Créneau complet → marqué indisponible

/ Covers the test plan session 8b cases:
- Public access without authentication
- 404 for unknown resource
- Resource name visible in the page
- All slots within horizon are displayed (no slice at 5)
- Full slot → marked unavailable

Lancement / Run:
    docker exec lespass_django poetry run pytest \
        booking/tests/test_views_resource.py -v
"""
import datetime
import sys
import os

sys.path.insert(0, '/DjangoFiles')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'TiBillet.settings')

import django
django.setup()

import pytest
from django.test import Client as DjangoClient
from django.utils import timezone
from django_tenants.utils import schema_context


TEST_PREFIX   = '[test_booking_views_detail]'
TENANT_SCHEMA = 'lespass'
HOST          = 'lespass.tibillet.localhost'


# ─── Helpers ────────────────────────────────────────────────────────────────

def _prochain_jour_semaine(numero_jour):
    """
    Retourne la prochaine occurrence du jour de la semaine donné.
    / Returns the next occurrence of the given weekday.

    numero_jour : 0 = lundi, 6 = dimanche.
    Si aujourd'hui est ce jour, retourne la semaine prochaine.
    """
    aujourd_hui = datetime.date.today()
    jours_avant = numero_jour - aujourd_hui.weekday()
    if jours_avant <= 0:
        jours_avant += 7
    return aujourd_hui + datetime.timedelta(days=jours_avant)


# ─── Fixtures de session ────────────────────────────────────────────────────

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


# ─── Fixtures : tenant et client HTTP ───────────────────────────────────────

@pytest.fixture(scope="module")
def tenant():
    """Le tenant 'lespass'. / The 'lespass' tenant."""
    from Customers.models import Client
    return Client.objects.get(schema_name=TENANT_SCHEMA)


@pytest.fixture(scope="module")
def client_anonyme():
    """
    Client Django anonyme configuré pour le tenant lespass.
    / Anonymous Django test client configured for the lespass tenant.
    """
    return DjangoClient(HTTP_HOST=HOST)


# ─── Fixtures : données de test ─────────────────────────────────────────────

@pytest.fixture(scope="module")
def ressource_avec_creneaux(tenant):
    """
    Ressource avec plus de 5 créneaux disponibles dans l'horizon.
    / Resource with more than 5 available slots within the horizon.

    LOCALISATION : booking/tests/test_views_resource.py

    Un OpeningEntry lundi avec slot_count=6 génère 6 créneaux par lundi.
    Sur un horizon de 28 jours (4 lundis), cela donne 24 créneaux > 5.
    La card list n'en affiche que 5 (|slice:":5") — le detail doit tout montrer.
    / One Monday OpeningEntry with slot_count=6 generates 6 slots per Monday.
    Over a 28-day horizon (4 Mondays), that gives 24 slots > 5.
    The list card shows only 5 (|slice:":5") — the detail page must show all.
    """
    from booking.models import Calendar, WeeklyOpening, Resource, OpeningEntry

    with schema_context(TENANT_SCHEMA):
        calendrier, _cree = Calendar.objects.get_or_create(
            name=f'{TEST_PREFIX} Calendrier Creneaux',
        )
        planning_semaine, _cree = WeeklyOpening.objects.get_or_create(
            name=f'{TEST_PREFIX} Planning Creneaux',
        )
        ressource, _cree = Resource.objects.get_or_create(
            name=f'{TEST_PREFIX} Ressource Avec Creneaux',
            defaults={
                'calendar':             calendrier,
                'weekly_opening':       planning_semaine,
                'capacity':             10,
                'booking_horizon_days': 28,
            },
        )
        # 6 créneaux consécutifs d'1 heure chaque lundi à partir de 09:00.
        # / 6 consecutive 1-hour slots every Monday starting at 09:00.
        OpeningEntry.objects.get_or_create(
            weekly_opening=planning_semaine,
            weekday=0,
            start_time=datetime.time(9, 0),
            defaults={
                'slot_duration_minutes': 60,
                'slot_count':            6,
            },
        )
        return ressource


@pytest.fixture(scope="module")
def ressource_complete(tenant):
    """
    Ressource avec un créneau entièrement réservé (capacity=1, 1 réservation).
    / Resource with one fully booked slot (capacity=1, 1 confirmed booking).

    LOCALISATION : booking/tests/test_views_resource.py

    Permet de vérifier que data-testid="booking-slot-unavailable" est présent
    sur la page de détail quand remaining_capacity == 0.
    / Verifies that data-testid="booking-slot-unavailable" is present
    on the detail page when remaining_capacity == 0.
    """
    from booking.models import (
        Calendar, WeeklyOpening, Resource, OpeningEntry, Booking,
    )
    from AuthBillet.models import TibilletUser

    with schema_context(TENANT_SCHEMA):
        utilisateur = (
            TibilletUser.objects.filter(is_superuser=True).first()
            or TibilletUser.objects.filter(is_active=True).first()
        )
        if utilisateur is None:
            raise RuntimeError(
                'Aucun utilisateur trouvé dans le tenant lespass. '
                'Veuillez créer un compte utilisateur.'
            )

        calendrier, _cree = Calendar.objects.get_or_create(
            name=f'{TEST_PREFIX} Calendrier Complet',
        )
        planning_semaine, _cree = WeeklyOpening.objects.get_or_create(
            name=f'{TEST_PREFIX} Planning Complet',
        )
        ressource, _cree = Resource.objects.get_or_create(
            name=f'{TEST_PREFIX} Ressource Complete',
            defaults={
                'calendar':             calendrier,
                'weekly_opening':       planning_semaine,
                'capacity':             1,
                'booking_horizon_days': 28,
            },
        )
        OpeningEntry.objects.get_or_create(
            weekly_opening=planning_semaine,
            weekday=0,
            start_time=datetime.time(10, 0),
            defaults={
                'slot_duration_minutes': 60,
                'slot_count':            1,
            },
        )

        Booking.objects.filter(resource=ressource).delete()

        prochain_lundi = _prochain_jour_semaine(numero_jour=0)
        fuseau_horaire = timezone.get_current_timezone()
        debut_datetime = timezone.make_aware(
            datetime.datetime.combine(prochain_lundi, datetime.time(10, 0)),
            fuseau_horaire,
        )
        Booking.objects.create(
            resource              = ressource,
            user                  = utilisateur,
            start_datetime        = debut_datetime,
            slot_duration_minutes = 60,
            slot_count            = 1,
            status                = Booking.STATUS_CONFIRMED,
        )
        return ressource


# ─── Fixture de nettoyage ────────────────────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def nettoyage_donnees_de_test(tenant):
    """
    Supprime toutes les données de test après le module.
    / Deletes all test data after the module.

    LOCALISATION : booking/tests/test_views_resource.py

    Ordre : Booking → Resource → OpeningEntry → WeeklyOpening → Calendar
    """
    yield

    with schema_context(TENANT_SCHEMA):
        from booking.models import (
            Booking, Resource, OpeningEntry, WeeklyOpening,
            ClosedPeriod, Calendar,
        )
        Booking.objects.filter(
            resource__name__startswith=TEST_PREFIX,
        ).delete()
        Resource.objects.filter(name__startswith=TEST_PREFIX).delete()
        OpeningEntry.objects.filter(
            weekly_opening__name__startswith=TEST_PREFIX,
        ).delete()
        WeeklyOpening.objects.filter(name__startswith=TEST_PREFIX).delete()
        ClosedPeriod.objects.filter(
            calendar__name__startswith=TEST_PREFIX,
        ).delete()
        Calendar.objects.filter(name__startswith=TEST_PREFIX).delete()


# ─── Tests ──────────────────────────────────────────────────────────────────

def test_resource_detail_accessible_without_authentication(
    client_anonyme,
    ressource_avec_creneaux,
):
    """
    La page de détail d'une ressource est accessible sans authentification.
    / The resource detail page is accessible without authentication.

    Spec §4.4 : la page publique de réservation est accessible sans login.
    """
    with schema_context(TENANT_SCHEMA):
        pk = ressource_avec_creneaux.pk

    reponse = client_anonyme.get(f'/booking/resource/{pk}/')

    assert reponse.status_code == 200


def test_resource_detail_returns_404_for_unknown_resource(client_anonyme):
    """
    Une ressource inexistante retourne HTTP 404.
    / An unknown resource returns HTTP 404.
    """
    reponse = client_anonyme.get('/booking/resource/99999/')

    assert reponse.status_code == 404


def test_resource_detail_shows_resource_name(
    client_anonyme,
    ressource_avec_creneaux,
):
    """
    Le nom de la ressource est présent dans le HTML de la page de détail.
    / The resource name is present in the detail page HTML.
    """
    with schema_context(TENANT_SCHEMA):
        pk  = ressource_avec_creneaux.pk
        nom = ressource_avec_creneaux.name

    reponse = client_anonyme.get(f'/booking/resource/{pk}/')

    assert reponse.status_code == 200
    contenu = reponse.content.decode('utf-8')
    assert nom in contenu


def test_resource_detail_shows_all_slots_within_horizon(
    client_anonyme,
    ressource_avec_creneaux,
):
    """
    La page de détail affiche tous les créneaux de l'horizon, pas seulement 5.
    / The detail page displays all slots within the horizon, not just 5.

    La card list applique |slice:":5" — la page detail ne doit pas.
    Avec slot_count=6 par lundi sur 28 jours, il y a au moins 6 créneaux.
    / The list card applies |slice:":5" — the detail page must not.
    With slot_count=6 per Monday over 28 days, there are at least 6 slots.
    """
    with schema_context(TENANT_SCHEMA):
        pk = ressource_avec_creneaux.pk

    reponse = client_anonyme.get(f'/booking/resource/{pk}/')

    assert reponse.status_code == 200
    contenu = reponse.content.decode('utf-8')

    # Compte les lignes de créneau (disponibles + indisponibles).
    # / Count slot rows (available + unavailable).
    nombre_creneaux = contenu.count('data-testid="booking-slot')
    assert nombre_creneaux > 5, (
        f"Attendu > 5 créneaux sur la page de détail, trouvé {nombre_creneaux}. "
        f"La page applique peut-être un |slice trop restrictif."
    )


def test_resource_detail_marks_full_slots_as_unavailable(
    client_anonyme,
    ressource_complete,
):
    """
    Un créneau dont la capacité restante est 0 est affiché comme indisponible.
    / A slot with remaining capacity = 0 is displayed as unavailable.

    Spec §4.4 : créneaux complets → marqués indisponibles.
    """
    with schema_context(TENANT_SCHEMA):
        pk = ressource_complete.pk

    reponse = client_anonyme.get(f'/booking/resource/{pk}/')

    assert reponse.status_code == 200
    contenu = reponse.content.decode('utf-8')

    assert 'data-testid="booking-slot-unavailable"' in contenu
