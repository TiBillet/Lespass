"""
Tests du formulaire de réservation et ajout au panier.
/ Tests for the booking form and add-to-basket action.

LOCALISATION : booking/tests/test_basket.py

Couvre les cas définis dans le plan de test session 10.1 :
- Liens <a href> vers booking_form sur les pages publiques (liste et détail)
- booking_form GET : accessible authentifié, redirige vers login sinon
- booking_form GET : affiche les détails du créneau et le max_slot_count
- booking_form GET : affiche une erreur si le créneau est complet
- add_to_basket POST : crée une réservation avec le statut 'new'
- add_to_basket POST : rejette les cas invalides (non authentifié,
  créneau complet, hors horizon, période fermée, passé, slot_count > 1)

/ Covers test plan session 10.1 cases:
- <a href> links to booking_form on public pages (list and detail)
- booking_form GET: accessible when authenticated, redirects to login otherwise
- booking_form GET: shows slot details and max_slot_count
- booking_form GET: shows error when slot is fully booked
- add_to_basket POST: creates booking with status 'new'
- add_to_basket POST: rejects invalid cases (unauthenticated, full slot,
  beyond horizon, closed period, past slot, slot_count > capacity)

Lancement / Run:
    docker exec lespass_django poetry run pytest \
        booking/tests/test_basket.py -v
"""
import datetime
import json
import os
import sys
from urllib.parse import urlencode

sys.path.insert(0, '/DjangoFiles')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'TiBillet.settings')

import django
django.setup()

import pytest
from django.test import Client as DjangoClient
from django.utils import timezone
from django_tenants.utils import schema_context


TEST_PREFIX   = '[test_booking_basket]'
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
    jours_avant = 0 - aujourd_hui.weekday()
    if jours_avant <= 0:
        jours_avant += 7
    return aujourd_hui + datetime.timedelta(days=jours_avant)


def _url_booking_form(pk, start_dt, duration=60):
    """
    Construit l'URL du formulaire de réservation avec les paramètres de créneau.
    / Builds the booking form URL with slot query parameters.
    """
    params = urlencode({
        'start_datetime':        start_dt.isoformat(),
        'slot_duration_minutes': duration,
    })
    return f'/booking/{pk}/booking_form/?{params}'


# ─── Fixtures locales ────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client_anonyme():
    """
    Client Django anonyme configuré pour le tenant lespass.
    / Anonymous Django test client configured for the lespass tenant.

    LOCALISATION : booking/tests/test_basket.py
    """
    return DjangoClient(HTTP_HOST=HOST)


@pytest.fixture(scope="module")
def ressource_avec_creneaux(tenant):
    """
    Ressource avec 6 créneaux consécutifs d'1h chaque lundi à 09:00.
    Capacité = 10, horizon = 28 jours → au moins 6 créneaux disponibles.
    / Resource with 6 consecutive 1-hour slots every Monday at 09:00.
    Capacity = 10, horizon = 28 days → at least 6 available slots.

    LOCALISATION : booking/tests/test_basket.py

    Utilisée pour : liens publics, booking_form GET, add_to_basket succès,
    rejets hors-horizon et passé.
    / Used for: public links, booking_form GET, add_to_basket success,
    beyond-horizon and past-slot rejections.
    """
    from booking.models import Calendar, WeeklyOpening, Resource, OpeningEntry

    with schema_context(TENANT_SCHEMA):
        calendrier, _ = Calendar.objects.get_or_create(
            name=f'{TEST_PREFIX} Calendrier Basket',
        )
        planning, _ = WeeklyOpening.objects.get_or_create(
            name=f'{TEST_PREFIX} Planning Basket',
        )
        ressource, _ = Resource.objects.get_or_create(
            name=f'{TEST_PREFIX} Ressource Basket',
            defaults={
                'calendar':             calendrier,
                'weekly_opening':       planning,
                'capacity':             10,
                'booking_horizon_days': 28,
            },
        )
        # 6 créneaux consécutifs d'1h chaque lundi à partir de 09:00.
        # / 6 consecutive 1-hour slots every Monday starting at 09:00.
        OpeningEntry.objects.get_or_create(
            weekly_opening=planning,
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
    Ressource avec un créneau entièrement réservé (capacity=1, 1 réservation confirmée).
    / Resource with one fully booked slot (capacity=1, 1 confirmed booking).

    LOCALISATION : booking/tests/test_basket.py

    Créneau : prochain lundi à 10:00 — remaining_capacity == 0.
    / Slot: next Monday at 10:00 — remaining_capacity == 0.
    """
    from booking.models import Calendar, WeeklyOpening, Resource, OpeningEntry, Booking
    from AuthBillet.models import TibilletUser

    with schema_context(TENANT_SCHEMA):
        utilisateur = (
            TibilletUser.objects.filter(is_superuser=True).first()
            or TibilletUser.objects.filter(is_active=True).first()
        )
        if utilisateur is None:
            raise RuntimeError(
                'Aucun utilisateur trouvé dans le tenant lespass.'
            )

        calendrier, _ = Calendar.objects.get_or_create(
            name=f'{TEST_PREFIX} Calendrier Complet',
        )
        planning, _ = WeeklyOpening.objects.get_or_create(
            name=f'{TEST_PREFIX} Planning Complet',
        )
        ressource, _ = Resource.objects.get_or_create(
            name=f'{TEST_PREFIX} Ressource Complete',
            defaults={
                'calendar':             calendrier,
                'weekly_opening':       planning,
                'capacity':             1,
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

        # Supprime les réservations existantes pour éviter les doublons.
        # / Delete existing bookings to avoid duplicates.
        Booking.objects.filter(resource=ressource).delete()

        prochain_lundi = _prochain_lundi()
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


@pytest.fixture(scope="module")
def ressource_periode_fermee(tenant):
    """
    Ressource dont le calendrier est entièrement fermé sur les 28 prochains jours.
    / Resource whose calendar is fully closed for the next 28 days.

    LOCALISATION : booking/tests/test_basket.py

    compute_slots() retourne [] — aucun créneau n'est dans une plage ouverte.
    / compute_slots() returns [] — no slot falls within an open interval.
    """
    from booking.models import Calendar, WeeklyOpening, Resource, OpeningEntry, ClosedPeriod

    with schema_context(TENANT_SCHEMA):
        calendrier, _ = Calendar.objects.get_or_create(
            name=f'{TEST_PREFIX} Calendrier Ferme',
        )
        planning, _ = WeeklyOpening.objects.get_or_create(
            name=f'{TEST_PREFIX} Planning Ferme',
        )
        ressource, _ = Resource.objects.get_or_create(
            name=f'{TEST_PREFIX} Ressource Fermee',
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
            start_time=datetime.time(11, 0),
            defaults={
                'slot_duration_minutes': 60,
                'slot_count':            1,
            },
        )
        # Couvre l'intégralité de l'horizon avec une période de fermeture.
        # / Covers the entire horizon with a closed period.
        ClosedPeriod.objects.get_or_create(
            calendar   = calendrier,
            start_date = datetime.date.today(),
            defaults={
                'end_date': datetime.date.today() + datetime.timedelta(days=28),
            },
        )
        return ressource


@pytest.fixture(scope="module")
def ressource_deuxieme_creneau_plein(tenant):
    """
    Ressource avec capacity=1 et une réservation confirmée sur le 2e créneau.
    / Resource with capacity=1 and a confirmed booking on the 2nd slot.

    LOCALISATION : booking/tests/test_basket.py

    Créneau 1 (09:00) : disponible (remaining_capacity=1).
    Créneau 2 (10:00) : complet (remaining_capacity=0).
    Demander slot_count=2 depuis 09:00 doit échouer — le 2e créneau est plein.
    / Slot 1 (09:00): available. Slot 2 (10:00): full.
    Requesting slot_count=2 from 09:00 must fail — the 2nd slot is full.
    """
    from booking.models import Calendar, WeeklyOpening, Resource, OpeningEntry, Booking
    from AuthBillet.models import TibilletUser

    with schema_context(TENANT_SCHEMA):
        utilisateur = (
            TibilletUser.objects.filter(is_superuser=True).first()
            or TibilletUser.objects.filter(is_active=True).first()
        )

        calendrier, _ = Calendar.objects.get_or_create(
            name=f'{TEST_PREFIX} Calendrier Deuxieme',
        )
        planning, _ = WeeklyOpening.objects.get_or_create(
            name=f'{TEST_PREFIX} Planning Deuxieme',
        )
        ressource, _ = Resource.objects.get_or_create(
            name=f'{TEST_PREFIX} Ressource Deuxieme',
            defaults={
                'calendar':             calendrier,
                'weekly_opening':       planning,
                'capacity':             1,
                'booking_horizon_days': 28,
            },
        )
        # 3 créneaux consécutifs pour avoir le 1er libre et le 2e plein.
        # / 3 consecutive slots so slot 1 is free and slot 2 is full.
        OpeningEntry.objects.get_or_create(
            weekly_opening=planning,
            weekday=0,
            start_time=datetime.time(9, 0),
            defaults={
                'slot_duration_minutes': 60,
                'slot_count':            3,
            },
        )

        Booking.objects.filter(resource=ressource).delete()

        prochain_lundi = _prochain_lundi()
        fuseau_horaire = timezone.get_current_timezone()
        # Réservation sur le 2e créneau (10:00 = 09:00 + 60 min).
        # / Booking on the 2nd slot (10:00 = 09:00 + 60 min).
        debut_deuxieme_creneau = timezone.make_aware(
            datetime.datetime.combine(prochain_lundi, datetime.time(10, 0)),
            fuseau_horaire,
        )
        Booking.objects.create(
            resource              = ressource,
            user                  = utilisateur,
            start_datetime        = debut_deuxieme_creneau,
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

    LOCALISATION : booking/tests/test_basket.py

    Ordre (on_delete=PROTECT — pas de cascade) :
    Booking → Resource → OpeningEntry → WeeklyOpening → ClosedPeriod → Calendar
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


# ─── Tests : liens sur les pages publiques ──────────────────────────────────

def test_slot_link_present_on_list_page(
    client_anonyme,
    ressource_avec_creneaux,
):
    """
    Un créneau disponible sur la page liste porte un <a href> vers booking_form.
    / An available slot on the list page has an <a href> to booking_form.

    LOCALISATION : booking/tests/test_basket.py

    Les créneaux sont rendus par le partial partagé slot_list.html inclus
    dans card.html. Ce test vérifie que le partial est bien inclus et que
    le lien de réservation est présent.
    / Slots are rendered by the shared slot_list.html partial included in
    card.html. This test verifies the partial is included and the booking
    link is present.
    """
    with schema_context(TENANT_SCHEMA):
        pk = ressource_avec_creneaux.pk

    reponse = client_anonyme.get('/booking/')

    assert reponse.status_code == 200
    contenu = reponse.content.decode('utf-8')
    assert f'/booking/{pk}/booking_form/' in contenu
    assert 'data-testid="booking-slot-available"' in contenu


def test_slot_link_present_on_detail_page(
    client_anonyme,
    ressource_avec_creneaux,
):
    """
    Un créneau disponible sur la page de détail porte un <a href> vers booking_form.
    / An available slot on the detail page has an <a href> to booking_form.

    LOCALISATION : booking/tests/test_basket.py

    Les créneaux sont rendus par le partial partagé slot_list.html inclus
    dans resource.html. Ce test vérifie que le partial est bien inclus et
    que le lien de réservation est présent.
    / Slots are rendered by the shared slot_list.html partial included in
    resource.html. This test verifies the partial is included and the
    booking link is present.
    """
    with schema_context(TENANT_SCHEMA):
        pk = ressource_avec_creneaux.pk

    reponse = client_anonyme.get(f'/booking/resource/{pk}/')

    assert reponse.status_code == 200
    contenu = reponse.content.decode('utf-8')
    assert f'/booking/{pk}/booking_form/' in contenu
    assert 'data-testid="booking-slot-available"' in contenu


# ─── Tests : booking_form GET ───────────────────────────────────────────────

def test_booking_form_accessible_when_authenticated(
    admin_client,
    ressource_avec_creneaux,
):
    """
    La page booking_form est accessible à un utilisateur authentifié (HTTP 200).
    / The booking_form page is accessible to an authenticated user (HTTP 200).

    LOCALISATION : booking/tests/test_basket.py
    """
    with schema_context(TENANT_SCHEMA):
        pk = ressource_avec_creneaux.pk

    prochain_lundi = _prochain_lundi()
    fuseau_horaire = timezone.get_current_timezone()
    start_dt = timezone.make_aware(
        datetime.datetime.combine(prochain_lundi, datetime.time(9, 0)),
        fuseau_horaire,
    )

    reponse = admin_client.get(_url_booking_form(pk, start_dt))

    assert reponse.status_code == 200


def test_booking_form_redirects_to_login_when_unauthenticated(
    client_anonyme,
    ressource_avec_creneaux,
):
    """
    Un utilisateur non authentifié est redirigé vers la page de connexion (HTTP 302).
    / An unauthenticated user is redirected to the login page (HTTP 302).

    LOCALISATION : booking/tests/test_basket.py

    Le lien <a href> sur resource.html/card.html déclenche une requête GET
    navigateur classique. Django renvoie 302 vers LOGIN_URL?next=<url>.
    Sans hx-get, htmx ne capture pas la requête — le navigateur suit la
    redirection normalement.
    / The <a href> link on resource.html/card.html triggers a regular browser
    GET. Django returns 302 to LOGIN_URL?next=<url>.
    Without hx-get, htmx doesn't intercept — the browser follows the
    redirect normally.
    """
    with schema_context(TENANT_SCHEMA):
        pk = ressource_avec_creneaux.pk

    prochain_lundi = _prochain_lundi()
    fuseau_horaire = timezone.get_current_timezone()
    start_dt = timezone.make_aware(
        datetime.datetime.combine(prochain_lundi, datetime.time(9, 0)),
        fuseau_horaire,
    )

    reponse = client_anonyme.get(
        _url_booking_form(pk, start_dt),
        follow=False,
    )

    assert reponse.status_code == 302
    # La redirection doit inclure ?next= pour revenir au formulaire après la connexion.
    # / The redirect must include ?next= to return to the form after login.
    localisation = reponse.get('Location', '')
    assert 'next=' in localisation or '/accounts/login/' in localisation


def test_booking_form_shows_slot_details(
    admin_client,
    ressource_avec_creneaux,
):
    """
    Le formulaire de réservation affiche les détails du créneau sélectionné.
    / The booking form displays details of the selected slot.

    LOCALISATION : booking/tests/test_basket.py
    """
    with schema_context(TENANT_SCHEMA):
        pk = ressource_avec_creneaux.pk

    prochain_lundi = _prochain_lundi()
    fuseau_horaire = timezone.get_current_timezone()
    start_dt = timezone.make_aware(
        datetime.datetime.combine(prochain_lundi, datetime.time(9, 0)),
        fuseau_horaire,
    )

    reponse = admin_client.get(_url_booking_form(pk, start_dt))

    assert reponse.status_code == 200
    contenu = reponse.content.decode('utf-8')
    assert 'data-testid="booking-form-slot-start"' in contenu


def test_booking_form_shows_correct_max_slot_count(
    admin_client,
    ressource_avec_creneaux,
):
    """
    Le formulaire affiche max_slot_count=6 pour 6 créneaux consécutifs sans réservation.
    / The form shows max_slot_count=6 for 6 consecutive slots with no bookings.

    LOCALISATION : booking/tests/test_basket.py

    ressource_avec_creneaux a 6 créneaux d'1h à partir de 09:00 chaque lundi.
    Aucune réservation → compute_max_consecutive_slots retourne 6.
    Le sélecteur <input type="number"> doit avoir max="6".
    / ressource_avec_creneaux has 6 1-hour slots from 09:00 every Monday.
    No bookings → compute_max_consecutive_slots returns 6.
    The <input type="number"> selector must have max="6".
    """
    with schema_context(TENANT_SCHEMA):
        pk = ressource_avec_creneaux.pk
        from booking.models import Booking
        Booking.objects.filter(resource=ressource_avec_creneaux).delete()

    prochain_lundi = _prochain_lundi()
    fuseau_horaire = timezone.get_current_timezone()
    start_dt = timezone.make_aware(
        datetime.datetime.combine(prochain_lundi, datetime.time(9, 0)),
        fuseau_horaire,
    )

    reponse = admin_client.get(_url_booking_form(pk, start_dt))

    assert reponse.status_code == 200
    contenu = reponse.content.decode('utf-8')
    assert 'max="6"' in contenu


def test_booking_form_shows_error_when_slot_no_longer_available(
    admin_client,
    ressource_complete,
):
    """
    Le formulaire affiche un message d'erreur si le créneau est complet.
    / The form shows an error message when the slot is fully booked.

    LOCALISATION : booking/tests/test_basket.py

    ressource_complete a remaining_capacity=0 sur le créneau 10:00.
    Le partial d'erreur doit contenir data-testid="booking-form-slot-unavailable".
    / ressource_complete has remaining_capacity=0 on the 10:00 slot.
    The error partial must contain data-testid="booking-form-slot-unavailable".
    """
    with schema_context(TENANT_SCHEMA):
        pk = ressource_complete.pk

    prochain_lundi = _prochain_lundi()
    fuseau_horaire = timezone.get_current_timezone()
    # Le créneau complet est à 10:00 (défini dans la fixture ressource_complete).
    # / The full slot is at 10:00 (defined in the ressource_complete fixture).
    start_dt = timezone.make_aware(
        datetime.datetime.combine(prochain_lundi, datetime.time(10, 0)),
        fuseau_horaire,
    )

    reponse = admin_client.get(_url_booking_form(pk, start_dt))

    assert reponse.status_code == 200
    contenu = reponse.content.decode('utf-8')
    assert 'data-testid="booking-form-slot-unavailable"' in contenu


# ─── Tests : add_to_basket POST ─────────────────────────────────────────────

def test_add_to_basket_creates_booking_with_status_new(
    admin_client,
    ressource_avec_creneaux,
    test_user,
):
    """
    Un POST valide crée une réservation avec le statut 'new'.
    / A valid POST creates a booking with status 'new'.

    LOCALISATION : booking/tests/test_basket.py
    """
    from booking.models import Booking

    with schema_context(TENANT_SCHEMA):
        pk = ressource_avec_creneaux.pk
        Booking.objects.filter(resource=ressource_avec_creneaux).delete()

    prochain_lundi = _prochain_lundi()
    fuseau_horaire = timezone.get_current_timezone()
    start_dt = timezone.make_aware(
        datetime.datetime.combine(prochain_lundi, datetime.time(9, 0)),
        fuseau_horaire,
    )

    reponse = admin_client.post(
        f'/booking/{pk}/add_to_basket/',
        data=json.dumps({
            'start_datetime':        start_dt.isoformat(),
            'slot_duration_minutes': 60,
            'slot_count':            1,
        }),
        content_type='application/json',
    )

    assert reponse.status_code == 200

    with schema_context(TENANT_SCHEMA):
        assert Booking.objects.filter(
            resource=ressource_avec_creneaux,
            user=test_user,
            status=Booking.STATUS_NEW,
        ).exists()
        # Nettoyage immédiat pour ne pas perturber les autres tests sur cette ressource.
        # / Immediate cleanup to avoid disturbing other tests using this resource.
        Booking.objects.filter(resource=ressource_avec_creneaux).delete()


def test_add_to_basket_rejects_unauthenticated_user(
    client_anonyme,
    ressource_avec_creneaux,
):
    """
    Un utilisateur non authentifié reçoit HTTP 401.
    / An unauthenticated user receives HTTP 401.

    LOCALISATION : booking/tests/test_basket.py
    """
    with schema_context(TENANT_SCHEMA):
        pk = ressource_avec_creneaux.pk

    prochain_lundi = _prochain_lundi()
    fuseau_horaire = timezone.get_current_timezone()
    start_dt = timezone.make_aware(
        datetime.datetime.combine(prochain_lundi, datetime.time(9, 0)),
        fuseau_horaire,
    )

    reponse = client_anonyme.post(
        f'/booking/{pk}/add_to_basket/',
        data=json.dumps({
            'start_datetime':        start_dt.isoformat(),
            'slot_duration_minutes': 60,
            'slot_count':            1,
        }),
        content_type='application/json',
    )

    assert reponse.status_code == 401


def test_add_to_basket_rejects_full_slot(
    admin_client,
    ressource_complete,
):
    """
    Un créneau complet (remaining_capacity=0) retourne HTTP 422.
    / A full slot (remaining_capacity=0) returns HTTP 422.

    LOCALISATION : booking/tests/test_basket.py
    """
    with schema_context(TENANT_SCHEMA):
        pk = ressource_complete.pk

    prochain_lundi = _prochain_lundi()
    fuseau_horaire = timezone.get_current_timezone()
    start_dt = timezone.make_aware(
        datetime.datetime.combine(prochain_lundi, datetime.time(10, 0)),
        fuseau_horaire,
    )

    reponse = admin_client.post(
        f'/booking/{pk}/add_to_basket/',
        data=json.dumps({
            'start_datetime':        start_dt.isoformat(),
            'slot_duration_minutes': 60,
            'slot_count':            1,
        }),
        content_type='application/json',
    )

    assert reponse.status_code == 422


def test_add_to_basket_rejects_slot_beyond_horizon(
    admin_client,
    ressource_avec_creneaux,
):
    """
    Un créneau hors de l'horizon (> 28 jours) retourne HTTP 422.
    / A slot beyond the booking horizon (> 28 days) returns HTTP 422.

    LOCALISATION : booking/tests/test_basket.py
    """
    with schema_context(TENANT_SCHEMA):
        pk = ressource_avec_creneaux.pk

    fuseau_horaire = timezone.get_current_timezone()
    # 60 jours dans le futur — bien au-delà de l'horizon de 28 jours.
    # / 60 days in the future — well beyond the 28-day horizon.
    date_hors_horizon = datetime.date.today() + datetime.timedelta(days=60)
    start_dt = timezone.make_aware(
        datetime.datetime.combine(date_hors_horizon, datetime.time(9, 0)),
        fuseau_horaire,
    )

    reponse = admin_client.post(
        f'/booking/{pk}/add_to_basket/',
        data=json.dumps({
            'start_datetime':        start_dt.isoformat(),
            'slot_duration_minutes': 60,
            'slot_count':            1,
        }),
        content_type='application/json',
    )

    assert reponse.status_code == 422


def test_add_to_basket_rejects_slot_in_closed_period(
    admin_client,
    ressource_periode_fermee,
):
    """
    Un créneau dans une période de fermeture retourne HTTP 422.
    / A slot inside a closed period returns HTTP 422.

    LOCALISATION : booking/tests/test_basket.py
    """
    with schema_context(TENANT_SCHEMA):
        pk = ressource_periode_fermee.pk

    prochain_lundi = _prochain_lundi()
    fuseau_horaire = timezone.get_current_timezone()
    # L'entrée d'ouverture est à 11:00 mais le calendrier est fermé.
    # / The opening entry is at 11:00 but the calendar is closed.
    start_dt = timezone.make_aware(
        datetime.datetime.combine(prochain_lundi, datetime.time(11, 0)),
        fuseau_horaire,
    )

    reponse = admin_client.post(
        f'/booking/{pk}/add_to_basket/',
        data=json.dumps({
            'start_datetime':        start_dt.isoformat(),
            'slot_duration_minutes': 60,
            'slot_count':            1,
        }),
        content_type='application/json',
    )

    assert reponse.status_code == 422


def test_add_to_basket_rejects_past_slot(
    admin_client,
    ressource_avec_creneaux,
):
    """
    Un créneau dans le passé retourne HTTP 422.
    / A past slot returns HTTP 422.

    LOCALISATION : booking/tests/test_basket.py
    """
    with schema_context(TENANT_SCHEMA):
        pk = ressource_avec_creneaux.pk

    fuseau_horaire = timezone.get_current_timezone()
    hier = datetime.date.today() - datetime.timedelta(days=1)
    start_dt = timezone.make_aware(
        datetime.datetime.combine(hier, datetime.time(9, 0)),
        fuseau_horaire,
    )

    reponse = admin_client.post(
        f'/booking/{pk}/add_to_basket/',
        data=json.dumps({
            'start_datetime':        start_dt.isoformat(),
            'slot_duration_minutes': 60,
            'slot_count':            1,
        }),
        content_type='application/json',
    )

    assert reponse.status_code == 422


def test_add_to_basket_slot_count_gt_1_checks_all_slots(
    admin_client,
    ressource_deuxieme_creneau_plein,
):
    """
    Demander slot_count=2 quand le 2e créneau est complet retourne HTTP 422.
    / Requesting slot_count=2 when the 2nd slot is full returns HTTP 422.

    LOCALISATION : booking/tests/test_basket.py

    Créneau 1 (09:00) : disponible. Créneau 2 (10:00) : complet.
    validate_new_booking() vérifie chaque créneau de la plage — échoue sur le 2e.
    / Slot 1 (09:00): available. Slot 2 (10:00): full.
    validate_new_booking() checks each slot in the range — fails on the 2nd.
    """
    with schema_context(TENANT_SCHEMA):
        pk = ressource_deuxieme_creneau_plein.pk

    prochain_lundi = _prochain_lundi()
    fuseau_horaire = timezone.get_current_timezone()
    start_dt = timezone.make_aware(
        datetime.datetime.combine(prochain_lundi, datetime.time(9, 0)),
        fuseau_horaire,
    )

    reponse = admin_client.post(
        f'/booking/{pk}/add_to_basket/',
        data=json.dumps({
            'start_datetime':        start_dt.isoformat(),
            'slot_duration_minutes': 60,
            'slot_count':            2,
        }),
        content_type='application/json',
    )

    assert reponse.status_code == 422
