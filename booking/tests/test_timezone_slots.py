"""
Tests du moteur de créneaux avec fuseau horaire.
/ Tests of the slot engine with timezone.

LOCALISATION : booking/tests/test_timezone_slots.py

Deux fuseaux stables sans DST :
  - Africa/Lagos  (UTC+1) : stable toute l'année
  - Asia/Tokyo    (UTC+9) : stable toute l'année
/ Two stable timezones without DST:
  - Africa/Lagos  (UTC+1): stable all year
  - Asia/Tokyo    (UTC+9): stable all year

Le fuseau est activé via Configuration.fuseau_horaire → config.get_tzinfo()
→ timezone.override(tz) — reproduit le chemin de production (middleware).
/ The timezone is activated via Configuration.fuseau_horaire → config.get_tzinfo()
→ timezone.override(tz) — reproduces the production path (middleware).

Points critiques vérifiés :
  1. Un slot créé à 09:00 local est bien à 09:00 dans le fuseau du tenant,
     pas à 09:00 UTC.
  2. Un slot qui traverse minuit (ex : 23:00 + 2h) intersecte deux dates
     LOCALES, même si les deux instants UTC tombent le même jour UTC.
  3. Un slot se terminant exactement à minuit ne touche pas le lendemain
     (sémantique semi-ouverte [start, end)).
/ Critical points checked:
  1. A slot created at 09:00 local is at 09:00 in the tenant timezone, not UTC.
  2. A slot crossing midnight (e.g. 23:00 + 2h) intersects two LOCAL dates,
     even if both UTC instants fall on the same UTC day.
  3. A slot ending exactly at midnight does not touch the next day
     (half-open interval semantics [start, end)).

Lancement / Run:
    docker exec lespass_django poetry run pytest \\
        booking/tests/test_timezone_slots.py -v
"""
import datetime
import os
import sys

sys.path.insert(0, '/DjangoFiles')

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'TiBillet.settings')
django.setup()

import pytest
from django.utils import timezone
from django_tenants.utils import schema_context

TEST_PREFIX = '[test_tz_slots]'
TENANT_SCHEMA = 'lespass'

# Fuseaux stables sans DST — choisis pour leur stabilité d'offset.
# / Stable timezones without DST — chosen for their offset stability.
TZ_NAME_LAGOS = 'Africa/Lagos'   # UTC+1, pas de DST / no DST
TZ_NAME_TOKYO = 'Asia/Tokyo'     # UTC+9, pas de DST / no DST


# ===========================================================================
# conftest inline — DB access
# ===========================================================================

@pytest.fixture(scope="session")
def django_db_setup():
    """
    Pas de création de test database — utilise la base dev existante.
    / Skip test database creation — use the existing dev database.
    """
    pass


@pytest.fixture(autouse=True, scope="session")
def _enable_db_access_for_all(django_db_blocker):
    """
    Désactiver le bloqueur d'accès DB de pytest-django.
    / Disable pytest-django's database blocker.
    """
    django_db_blocker.unblock()
    yield
    django_db_blocker.restore()


# ===========================================================================
# Helpers — fuseau tenant
# / Helpers — tenant timezone
# ===========================================================================

def _set_tenant_timezone(tz_name):
    """
    Met à jour Configuration.fuseau_horaire et retourne le pytz.timezone.
    / Updates Configuration.fuseau_horaire and returns the pytz timezone.

    LOCALISATION : booking/tests/test_timezone_slots.py

    Reproduit le chemin de production : en production, le middleware lit
    Configuration.fuseau_horaire pour activer le fuseau du tenant.
    / Reproduces the production path: in production, the middleware reads
    Configuration.fuseau_horaire to activate the tenant timezone.

    Appeler à l'intérieur d'un schema_context(TENANT_SCHEMA).
    / Call inside a schema_context(TENANT_SCHEMA).
    """
    from BaseBillet.models import Configuration

    config = Configuration.get_solo()
    config.fuseau_horaire = tz_name
    config.save(update_fields=['fuseau_horaire'])
    return config.get_tzinfo()


def _restore_tenant_timezone(tz_name):
    """
    Restaure Configuration.fuseau_horaire à sa valeur d'avant le test.
    / Restores Configuration.fuseau_horaire to its pre-test value.
    """
    from BaseBillet.models import Configuration

    config = Configuration.get_solo()
    config.fuseau_horaire = tz_name
    config.save(update_fields=['fuseau_horaire'])


# ===========================================================================
# Helpers — création de données
# / Helpers — data creation
# ===========================================================================

def _make_calendar(label):
    """Crée un Calendar de test. / Creates a test Calendar."""
    from booking.models import Calendar

    calendar, _created = Calendar.objects.get_or_create(
        name=f'{TEST_PREFIX} {label}',
    )
    return calendar


def _make_weekly_opening(label):
    """Crée un WeeklyOpening de test. / Creates a test WeeklyOpening."""
    from booking.models import WeeklyOpening

    opening, _created = WeeklyOpening.objects.get_or_create(
        name=f'{TEST_PREFIX} {label}',
    )
    return opening


def _make_resource(name, calendar, weekly_opening, capacity=1, horizon=28):
    """Crée une Resource de test. / Creates a test Resource."""
    from booking.models import Resource

    resource, _created = Resource.objects.get_or_create(
        name=f'{TEST_PREFIX} {name}',
        defaults={
            'calendar': calendar,
            'weekly_opening': weekly_opening,
            'capacity': capacity,
            'booking_horizon_days': horizon,
        },
    )
    return resource


def _add_opening_entry(weekly_opening, weekday, start_time,
                       slot_duration_minutes=60, slot_count=1):
    """
    Ajoute une OpeningEntry au WeeklyOpening.
    / Adds an OpeningEntry to the WeeklyOpening.
    """
    from booking.models import OpeningEntry

    return OpeningEntry.objects.create(
        weekly_opening=weekly_opening,
        weekday=weekday,
        start_time=start_time,
        slot_duration_minutes=slot_duration_minutes,
        slot_count=slot_count,
    )


def _add_closed_period(calendar, start_date, end_date=None, label='Fermeture'):
    """
    Crée une ClosedPeriod sur le Calendar.
    / Creates a ClosedPeriod on the Calendar.
    """
    from booking.models import ClosedPeriod

    return ClosedPeriod.objects.create(
        calendar=calendar,
        start_date=start_date,
        end_date=end_date or start_date,
        label=label,
    )


def _add_booking(resource, user, start_datetime, slot_duration_minutes=60, slot_count=1):
    """
    Crée une réservation confirmée.
    / Creates a confirmed booking.
    """
    from booking.models import Booking

    return Booking.objects.create(
        resource=resource,
        user=user,
        start_datetime=start_datetime,
        slot_duration_minutes=slot_duration_minutes,
        slot_count=slot_count,
        status='confirmed',
    )


def _get_test_user():
    """
    Récupère le premier superutilisateur actif du tenant.
    / Gets the first active superuser from the tenant.
    """
    from AuthBillet.models import TibilletUser

    user = (
        TibilletUser.objects.filter(is_superuser=True).first()
        or TibilletUser.objects.filter(is_active=True).first()
    )
    if user is None:
        raise RuntimeError(
            'Aucun utilisateur trouvé dans le tenant lespass. '
            'Veuillez créer un utilisateur.'
        )
    return user


def _cleanup():
    """
    Supprime toutes les données de test dans l'ordre FK (on_delete=PROTECT).
    / Deletes all test data in FK order (on_delete=PROTECT).

    Ordre : Booking → Resource → OpeningEntry → WeeklyOpening
                    → ClosedPeriod → Calendar
    """
    from booking.models import (
        Booking, Resource, OpeningEntry, WeeklyOpening,
        ClosedPeriod, Calendar,
    )

    Booking.objects.filter(resource__name__startswith=TEST_PREFIX).delete()
    Resource.objects.filter(name__startswith=TEST_PREFIX).delete()
    OpeningEntry.objects.filter(weekly_opening__name__startswith=TEST_PREFIX).delete()
    WeeklyOpening.objects.filter(name__startswith=TEST_PREFIX).delete()
    ClosedPeriod.objects.filter(calendar__name__startswith=TEST_PREFIX).delete()
    Calendar.objects.filter(name__startswith=TEST_PREFIX).delete()


# ===========================================================================
# Helpers — dates
# ===========================================================================

def _next_weekday(weekday, min_days_ahead=3):
    """
    Retourne la prochaine date dont le jour de semaine vaut `weekday`,
    au moins `min_days_ahead` jours dans le futur.
    / Returns the next date with the given weekday, at least
    min_days_ahead days in the future.

    weekday : 0 = lundi (Monday) → 6 = dimanche (Sunday)
    """
    today = datetime.date.today()
    start = today + datetime.timedelta(days=min_days_ahead)
    days_until_weekday = (weekday - start.weekday()) % 7
    return start + datetime.timedelta(days=days_until_weekday)


def _make_aware_in(naive_dt, tz):
    """
    Construit un datetime timezone-aware dans le fuseau donné.
    / Builds a timezone-aware datetime in the given timezone.
    """
    return timezone.make_aware(naive_dt, tz)


# ===========================================================================
# Section 1 — Génération de créneaux
# / Section 1 — Slot generation
# ===========================================================================

@pytest.mark.django_db
def test_slot_local_time_is_preserved_utc_plus_1():
    """
    Un créneau à 09:00 en fuseau UTC+1 (Lagos) doit avoir son heure locale à 09:00.
    / A slot at 09:00 in UTC+1 (Lagos) must have local time 09:00.

    LOCALISATION : booking/tests/test_timezone_slots.py

    En UTC, ce créneau est à 08:00 (09:00 − 1h offset).
    C'est le fuseau configuré dans Configuration.fuseau_horaire qui
    détermine l'heure locale, pas le fuseau du serveur.
    / In UTC, this slot is at 08:00 (09:00 − 1h offset).
    The timezone configured in Configuration.fuseau_horaire determines
    the local time, not the server timezone.

    Lundi (weekday=0), 09:00, 60 min, 1 créneau.
    """
    from booking.slot_engine import generate_theoretical_slots, get_opening_entries_for_resource

    with schema_context(TENANT_SCHEMA):
        from BaseBillet.models import Configuration
        original_tz_name = Configuration.get_solo().fuseau_horaire

        try:
            # Active le fuseau UTC+1 via Configuration (chemin de production).
            # / Activate UTC+1 via Configuration (production path).
            tz = _set_tenant_timezone(TZ_NAME_LAGOS)

            monday = _next_weekday(weekday=0)
            calendar = _make_calendar('slot_time_utc_plus_1')
            weekly_opening = _make_weekly_opening('slot_time_utc_plus_1')
            resource_for_test = _make_resource('slot_time_utc_plus_1', calendar, weekly_opening)

            _add_opening_entry(
                weekly_opening,
                weekday=0,
                start_time=datetime.time(9, 0),
                slot_duration_minutes=60,
                slot_count=1,
            )

            opening_entries = get_opening_entries_for_resource(resource_for_test)

            with timezone.override(tz):
                slots = generate_theoretical_slots(
                    opening_entries=opening_entries,
                    date_from=monday,
                    date_to=monday,
                    closed_dates=set(),
                )

            assert len(slots) == 1
            slot = slots[0]

            # Le datetime du créneau doit être timezone-aware.
            # / The slot datetime must be timezone-aware.
            assert slot.start.tzinfo is not None

            # L'heure locale dans le fuseau Lagos (UTC+1) doit être 09:00.
            # / The local time in the Lagos timezone (UTC+1) must be 09:00.
            local_start = slot.start.astimezone(tz)
            assert local_start.hour == 9
            assert local_start.minute == 0

            # En UTC, le créneau est à 08:00 (09:00 − 1h).
            # / In UTC, the slot is at 08:00 (09:00 − 1h).
            utc_start = slot.start.astimezone(datetime.timezone.utc)
            assert utc_start.hour == 8

        finally:
            _cleanup()
            _restore_tenant_timezone(original_tz_name)


@pytest.mark.django_db
def test_slot_local_time_is_preserved_utc_plus_9():
    """
    Un créneau à 09:00 en fuseau UTC+9 (Tokyo) doit avoir son heure locale à 09:00.
    / A slot at 09:00 in UTC+9 (Tokyo) must have local time 09:00.

    LOCALISATION : booking/tests/test_timezone_slots.py

    En UTC, ce créneau est à 00:00 (09:00 − 9h).
    Les deux tests UTC+1 et UTC+9 ensemble confirment que le fuseau du
    tenant est respecté, pas celui du serveur.
    / In UTC, this slot is at 00:00 (09:00 − 9h).
    Both UTC+1 and UTC+9 tests together confirm that the tenant timezone
    is respected, not the server timezone.

    Lundi (weekday=0), 09:00, 60 min, 1 créneau.
    """
    from booking.slot_engine import generate_theoretical_slots, get_opening_entries_for_resource

    with schema_context(TENANT_SCHEMA):
        from BaseBillet.models import Configuration
        original_tz_name = Configuration.get_solo().fuseau_horaire

        try:
            tz = _set_tenant_timezone(TZ_NAME_TOKYO)

            monday = _next_weekday(weekday=0)
            calendar = _make_calendar('slot_time_utc_plus_9')
            weekly_opening = _make_weekly_opening('slot_time_utc_plus_9')
            resource_for_test = _make_resource('slot_time_utc_plus_9', calendar, weekly_opening)

            _add_opening_entry(
                weekly_opening,
                weekday=0,
                start_time=datetime.time(9, 0),
                slot_duration_minutes=60,
                slot_count=1,
            )

            opening_entries = get_opening_entries_for_resource(resource_for_test)

            with timezone.override(tz):
                slots = generate_theoretical_slots(
                    opening_entries=opening_entries,
                    date_from=monday,
                    date_to=monday,
                    closed_dates=set(),
                )

            assert len(slots) == 1
            slot = slots[0]

            assert slot.start.tzinfo is not None

            # L'heure locale dans le fuseau Tokyo (UTC+9) doit être 09:00.
            # / The local time in the Tokyo timezone (UTC+9) must be 09:00.
            local_start = slot.start.astimezone(tz)
            assert local_start.hour == 9
            assert local_start.minute == 0

            # En UTC, le créneau est à 00:00 (09:00 − 9h).
            # / In UTC, the slot is at 00:00 (09:00 − 9h).
            utc_start = slot.start.astimezone(datetime.timezone.utc)
            assert utc_start.hour == 0

        finally:
            _cleanup()
            _restore_tenant_timezone(original_tz_name)


@pytest.mark.django_db
def test_midnight_crossing_slot_closed_second_day_utc_plus_1():
    """
    Un slot 23:00−01:00 en UTC+1 est exclu si le lendemain local est fermé.
    / A slot 23:00−01:00 in UTC+1 is excluded if the next local day is closed.

    LOCALISATION : booking/tests/test_timezone_slots.py

    En UTC+1, ce slot (22:00−00:00 UTC) tient sur UNE SEULE date UTC.
    Mais localement il traverse minuit et touche deux dates (mercredi ET jeudi).
    La vérification de fermeture doit utiliser les dates LOCALES, pas UTC.
    / In UTC+1, this slot (22:00−00:00 UTC) spans ONE single UTC date.
    But locally it crosses midnight and touches two dates (Wednesday AND Thursday).
    Closure checking must use LOCAL dates, not UTC.

    Mercredi (weekday=2), 23:00, 120 min (finit jeudi 01:00 local).
    ClosedPeriod : le jeudi correspondant.
    """
    from booking.slot_engine import (
        generate_theoretical_slots,
        get_opening_entries_for_resource,
        get_closed_dates_for_resource,
    )

    with schema_context(TENANT_SCHEMA):
        from BaseBillet.models import Configuration
        original_tz_name = Configuration.get_solo().fuseau_horaire

        try:
            tz = _set_tenant_timezone(TZ_NAME_LAGOS)

            wednesday = _next_weekday(weekday=2)
            thursday = wednesday + datetime.timedelta(days=1)

            calendar = _make_calendar('midnight_cross_closed_utc1')
            weekly_opening = _make_weekly_opening('midnight_cross_closed_utc1')
            resource_for_test = _make_resource('midnight_cross_closed_utc1', calendar, weekly_opening)

            # Créneau mercredi 23:00 → jeudi 01:00 (traverse minuit local).
            # / Slot Wednesday 23:00 → Thursday 01:00 (crosses local midnight).
            _add_opening_entry(
                weekly_opening,
                weekday=2,  # Mercredi / Wednesday
                start_time=datetime.time(23, 0),
                slot_duration_minutes=120,
                slot_count=1,
            )

            # Ferme le jeudi local — le lendemain du slot.
            # / Close local Thursday — the day after the slot.
            _add_closed_period(calendar, start_date=thursday, label='Jeudi fermé')

            opening_entries = get_opening_entries_for_resource(resource_for_test)

            # Récupère les dates fermées sur la plage mercredi−jeudi.
            # / Retrieve closed dates over the Wednesday−Thursday range.
            closed_dates = get_closed_dates_for_resource(resource_for_test, wednesday, thursday)

            with timezone.override(tz):
                slots = generate_theoretical_slots(
                    opening_entries=opening_entries,
                    date_from=wednesday,
                    date_to=wednesday,
                    closed_dates=closed_dates,
                )

            # Le slot intersecte le jeudi local qui est fermé → exclu.
            # En UTC+1 le slot est 22:00−00:00 UTC (une seule date UTC),
            # mais localement il touche mercredi ET jeudi.
            # / The slot intersects local Thursday which is closed → excluded.
            # In UTC+1 the slot is 22:00−00:00 UTC (single UTC date),
            # but locally it touches Wednesday AND Thursday.
            assert len(slots) == 0, (
                f'Attendu 0 créneau (jeudi local Lagos fermé), obtenu {len(slots)}'
            )

        finally:
            _cleanup()
            _restore_tenant_timezone(original_tz_name)


@pytest.mark.django_db
def test_midnight_crossing_slot_closed_second_day_utc_plus_9():
    """
    Un slot 23:00−01:00 en UTC+9 est exclu si le lendemain local est fermé.
    / A slot 23:00−01:00 in UTC+9 is excluded if the next local day is closed.

    LOCALISATION : booking/tests/test_timezone_slots.py

    En UTC+9, ce slot (14:00−16:00 UTC) tient sur UNE SEULE date UTC.
    Les instants UTC sont radicalement différents du test UTC+1 (22:00−00:00),
    mais le comportement de fermeture locale doit être identique.
    / In UTC+9, this slot (14:00−16:00 UTC) spans ONE single UTC date.
    The UTC instants differ radically from the UTC+1 test (22:00−00:00),
    but the local closure behavior must be identical.
    """
    from booking.slot_engine import (
        generate_theoretical_slots,
        get_opening_entries_for_resource,
        get_closed_dates_for_resource,
    )

    with schema_context(TENANT_SCHEMA):
        from BaseBillet.models import Configuration
        original_tz_name = Configuration.get_solo().fuseau_horaire

        try:
            tz = _set_tenant_timezone(TZ_NAME_TOKYO)

            wednesday = _next_weekday(weekday=2)
            thursday = wednesday + datetime.timedelta(days=1)

            calendar = _make_calendar('midnight_cross_closed_utc9')
            weekly_opening = _make_weekly_opening('midnight_cross_closed_utc9')
            resource_for_test = _make_resource('midnight_cross_closed_utc9', calendar, weekly_opening)

            _add_opening_entry(
                weekly_opening,
                weekday=2,
                start_time=datetime.time(23, 0),
                slot_duration_minutes=120,
                slot_count=1,
            )
            _add_closed_period(calendar, start_date=thursday, label='Jeudi fermé Tokyo')

            opening_entries = get_opening_entries_for_resource(resource_for_test)
            closed_dates = get_closed_dates_for_resource(resource_for_test, wednesday, thursday)

            with timezone.override(tz):
                slots = generate_theoretical_slots(
                    opening_entries=opening_entries,
                    date_from=wednesday,
                    date_to=wednesday,
                    closed_dates=closed_dates,
                )

            assert len(slots) == 0, (
                f'Attendu 0 créneau (jeudi local Tokyo fermé), obtenu {len(slots)}'
            )

        finally:
            _cleanup()
            _restore_tenant_timezone(original_tz_name)


@pytest.mark.django_db
def test_midnight_crossing_slot_open_second_day_utc_plus_1():
    """
    Un slot 23:00−01:00 en UTC+1 est généré normalement si aucun jour n'est fermé.
    / A slot 23:00−01:00 in UTC+1 is generated normally when no day is closed.

    LOCALISATION : booking/tests/test_timezone_slots.py

    Cas nominal : pas de fermeture → 1 créneau attendu,
    débutant à 23:00 heure locale Lagos.
    / Nominal case: no closure → 1 slot expected,
    starting at 23:00 local Lagos time.
    """
    from booking.slot_engine import generate_theoretical_slots, get_opening_entries_for_resource

    with schema_context(TENANT_SCHEMA):
        from BaseBillet.models import Configuration
        original_tz_name = Configuration.get_solo().fuseau_horaire

        try:
            tz = _set_tenant_timezone(TZ_NAME_LAGOS)

            wednesday = _next_weekday(weekday=2)

            calendar = _make_calendar('midnight_cross_open_utc1')
            weekly_opening = _make_weekly_opening('midnight_cross_open_utc1')
            resource_for_test = _make_resource('midnight_cross_open_utc1', calendar, weekly_opening)

            _add_opening_entry(
                weekly_opening,
                weekday=2,
                start_time=datetime.time(23, 0),
                slot_duration_minutes=120,
                slot_count=1,
            )

            opening_entries = get_opening_entries_for_resource(resource_for_test)

            with timezone.override(tz):
                slots = generate_theoretical_slots(
                    opening_entries=opening_entries,
                    date_from=wednesday,
                    date_to=wednesday,
                    closed_dates=set(),
                )

            assert len(slots) == 1, (
                f'Attendu 1 créneau (aucune fermeture), obtenu {len(slots)}'
            )

            # L'heure de début doit être 23:00 en heure locale.
            # / The start time must be 23:00 in local time.
            local_start = slots[0].start.astimezone(tz)
            assert local_start.hour == 23
            assert local_start.minute == 0

        finally:
            _cleanup()
            _restore_tenant_timezone(original_tz_name)


@pytest.mark.django_db
def test_slot_23h45_crosses_midnight_closed_next_day_utc_plus_1():
    """
    Un slot 23:45−00:15 en UTC+1 est exclu si le mardi local est fermé.
    / A slot 23:45−00:15 in UTC+1 is excluded if local Tuesday is closed.

    LOCALISATION : booking/tests/test_timezone_slots.py

    En UTC : 22:45−23:15 (UNE seule date UTC, lundi UTC).
    Localement à Lagos : traverse minuit, touche lundi ET mardi local.
    La fermeture mardi doit exclure le slot même si en UTC c'est le lundi.
    / In UTC: 22:45−23:15 (ONE single UTC date, UTC Monday).
    Locally in Lagos: crosses midnight, touches local Monday AND Tuesday.
    Tuesday closure must exclude the slot even though in UTC it is Monday.
    """
    from booking.slot_engine import (
        generate_theoretical_slots,
        get_opening_entries_for_resource,
        get_closed_dates_for_resource,
    )

    with schema_context(TENANT_SCHEMA):
        from BaseBillet.models import Configuration
        original_tz_name = Configuration.get_solo().fuseau_horaire

        try:
            tz = _set_tenant_timezone(TZ_NAME_LAGOS)

            monday = _next_weekday(weekday=0)
            tuesday = monday + datetime.timedelta(days=1)

            calendar = _make_calendar('23h45_closed_utc1')
            weekly_opening = _make_weekly_opening('23h45_closed_utc1')
            resource_for_test = _make_resource('23h45_closed_utc1', calendar, weekly_opening)

            # 23:45 + 30 min → fin à 00:15 mardi local.
            # / 23:45 + 30 min → end at 00:15 local Tuesday.
            _add_opening_entry(
                weekly_opening,
                weekday=0,  # Lundi / Monday
                start_time=datetime.time(23, 45),
                slot_duration_minutes=30,
                slot_count=1,
            )
            _add_closed_period(calendar, start_date=tuesday, label='Mardi fermé Lagos')

            opening_entries = get_opening_entries_for_resource(resource_for_test)
            closed_dates = get_closed_dates_for_resource(resource_for_test, monday, tuesday)

            with timezone.override(tz):
                slots = generate_theoretical_slots(
                    opening_entries=opening_entries,
                    date_from=monday,
                    date_to=monday,
                    closed_dates=closed_dates,
                )

            assert len(slots) == 0, (
                f'Attendu 0 créneau (mardi local Lagos fermé), obtenu {len(slots)}'
            )

        finally:
            _cleanup()
            _restore_tenant_timezone(original_tz_name)


@pytest.mark.django_db
def test_slot_23h45_crosses_midnight_closed_next_day_utc_plus_9():
    """
    Un slot 23:45−00:15 en UTC+9 est exclu si le mardi local Tokyo est fermé.
    / A slot 23:45−00:15 in UTC+9 is excluded if local Tokyo Tuesday is closed.

    LOCALISATION : booking/tests/test_timezone_slots.py

    En UTC : 14:45−15:15 (UNE seule date UTC, lundi UTC).
    Localement à Tokyo : traverse minuit, touche lundi ET mardi local.
    Même comportement attendu qu'en UTC+1, malgré des heures UTC différentes.
    / In UTC: 14:45−15:15 (ONE single UTC date, UTC Monday).
    Locally in Tokyo: crosses midnight, touches local Monday AND Tuesday.
    Same expected behavior as UTC+1, despite different UTC hours.
    """
    from booking.slot_engine import (
        generate_theoretical_slots,
        get_opening_entries_for_resource,
        get_closed_dates_for_resource,
    )

    with schema_context(TENANT_SCHEMA):
        from BaseBillet.models import Configuration
        original_tz_name = Configuration.get_solo().fuseau_horaire

        try:
            tz = _set_tenant_timezone(TZ_NAME_TOKYO)

            monday = _next_weekday(weekday=0)
            tuesday = monday + datetime.timedelta(days=1)

            calendar = _make_calendar('23h45_closed_utc9')
            weekly_opening = _make_weekly_opening('23h45_closed_utc9')
            resource_for_test = _make_resource('23h45_closed_utc9', calendar, weekly_opening)

            _add_opening_entry(
                weekly_opening,
                weekday=0,
                start_time=datetime.time(23, 45),
                slot_duration_minutes=30,
                slot_count=1,
            )
            _add_closed_period(calendar, start_date=tuesday, label='Mardi fermé Tokyo')

            opening_entries = get_opening_entries_for_resource(resource_for_test)
            closed_dates = get_closed_dates_for_resource(resource_for_test, monday, tuesday)

            with timezone.override(tz):
                slots = generate_theoretical_slots(
                    opening_entries=opening_entries,
                    date_from=monday,
                    date_to=monday,
                    closed_dates=closed_dates,
                )

            assert len(slots) == 0, (
                f'Attendu 0 créneau (mardi local Tokyo fermé), obtenu {len(slots)}'
            )

        finally:
            _cleanup()
            _restore_tenant_timezone(original_tz_name)


@pytest.mark.django_db
def test_slot_ending_exactly_at_midnight_next_day_closed_utc_plus_1():
    """
    Un slot 23:00−00:00 (fin pile à minuit) n'est PAS exclu si le mardi est fermé.
    / A slot 23:00−00:00 (ending exactly at midnight) is NOT excluded if Tuesday is closed.

    LOCALISATION : booking/tests/test_timezone_slots.py

    Sémantique semi-ouverte [start, end) :
    Le slot finit à la frontière de minuit sans occuper le mardi.
    last_dt = end_dt − 1 µs = 23:59:59.999999 → date locale = lundi.
    La fermeture du mardi ne doit PAS exclure ce slot.
    / Half-open interval semantics [start, end):
    The slot ends at the midnight boundary without occupying Tuesday.
    last_dt = end_dt − 1 µs = 23:59:59.999999 → local date = Monday.
    Tuesday closure must NOT exclude this slot.

    Contraste avec test_slot_23h45_crosses_midnight_closed_next_day_utc_plus_1 :
    30 minutes de plus et le slot serait exclu.
    / Contrast with test_slot_23h45_crosses_midnight_closed_next_day_utc_plus_1:
    30 extra minutes and the slot would be excluded.
    """
    from booking.slot_engine import (
        generate_theoretical_slots,
        get_opening_entries_for_resource,
        get_closed_dates_for_resource,
    )

    with schema_context(TENANT_SCHEMA):
        from BaseBillet.models import Configuration
        original_tz_name = Configuration.get_solo().fuseau_horaire

        try:
            tz = _set_tenant_timezone(TZ_NAME_LAGOS)

            monday = _next_weekday(weekday=0)
            tuesday = monday + datetime.timedelta(days=1)

            calendar = _make_calendar('midnight_exact_utc1')
            weekly_opening = _make_weekly_opening('midnight_exact_utc1')
            resource_for_test = _make_resource('midnight_exact_utc1', calendar, weekly_opening)

            # 23:00 + 60 min → fin exactement à 00:00 mardi local (minuit pile).
            # / 23:00 + 60 min → end exactly at 00:00 local Tuesday (midnight).
            _add_opening_entry(
                weekly_opening,
                weekday=0,
                start_time=datetime.time(23, 0),
                slot_duration_minutes=60,
                slot_count=1,
            )
            _add_closed_period(calendar, start_date=tuesday, label='Mardi fermé')

            opening_entries = get_opening_entries_for_resource(resource_for_test)
            closed_dates = get_closed_dates_for_resource(resource_for_test, monday, tuesday)

            with timezone.override(tz):
                slots = generate_theoretical_slots(
                    opening_entries=opening_entries,
                    date_from=monday,
                    date_to=monday,
                    closed_dates=closed_dates,
                )

            # Le slot finit EXACTEMENT à minuit → n'occupe pas le mardi.
            # last_dt = 23:59:59.999999 → date locale = lundi uniquement.
            # / Slot ends EXACTLY at midnight → does not occupy Tuesday.
            # last_dt = 23:59:59.999999 → local date = Monday only.
            assert len(slots) == 1, (
                f'Attendu 1 créneau (fin à minuit pile, mardi non occupé), '
                f'obtenu {len(slots)}'
            )

        finally:
            _cleanup()
            _restore_tenant_timezone(original_tz_name)


# ===========================================================================
# Section 2 — Validation de réservation
# / Section 2 — Booking validation
# ===========================================================================

@pytest.mark.django_db
def test_booking_validation_accepts_valid_slot_utc_plus_1():
    """
    validate_new_booking accepte une réservation valide en fuseau UTC+1 (Lagos).
    / validate_new_booking accepts a valid booking in UTC+1 (Lagos).

    LOCALISATION : booking/tests/test_timezone_slots.py

    Lundi 10:00 heure Lagos, 60 min, capacité 1, aucune réservation existante.
    / Monday 10:00 Lagos time, 60 min, capacity 1, no existing bookings.
    """
    from booking.booking_validator import validate_new_booking

    with schema_context(TENANT_SCHEMA):
        from BaseBillet.models import Configuration
        original_tz_name = Configuration.get_solo().fuseau_horaire

        try:
            tz = _set_tenant_timezone(TZ_NAME_LAGOS)

            monday = _next_weekday(weekday=0)
            calendar = _make_calendar('validation_valid_utc1')
            weekly_opening = _make_weekly_opening('validation_valid_utc1')
            resource_for_test = _make_resource('validation_valid_utc1', calendar, weekly_opening)

            _add_opening_entry(
                weekly_opening,
                weekday=0,
                start_time=datetime.time(10, 0),
                slot_duration_minutes=60,
                slot_count=1,
            )

            # start_datetime timezone-aware dans le fuseau du tenant.
            # / start_datetime timezone-aware in the tenant timezone.
            start_datetime = _make_aware_in(
                datetime.datetime.combine(monday, datetime.time(10, 0)),
                tz,
            )

            with timezone.override(tz):
                is_valid, error = validate_new_booking(
                    resource=resource_for_test,
                    start_datetime=start_datetime,
                    slot_duration_minutes=60,
                    slot_count=1,
                    member=_get_test_user(),
                )

            assert is_valid is True, f'Attendu True, erreur obtenue : {error}'
            assert error is None

        finally:
            _cleanup()
            _restore_tenant_timezone(original_tz_name)


@pytest.mark.django_db
def test_booking_validation_accepts_valid_slot_utc_plus_9():
    """
    validate_new_booking accepte une réservation valide en fuseau UTC+9 (Tokyo).
    / validate_new_booking accepts a valid booking in UTC+9 (Tokyo).

    LOCALISATION : booking/tests/test_timezone_slots.py

    Lundi 10:00 heure Tokyo, 60 min.
    En UTC ce créneau est à 01:00 (10:00 − 9h).
    La validation doit fonctionner identiquement à UTC+1.
    / Monday 10:00 Tokyo time, 60 min.
    In UTC this slot is at 01:00 (10:00 − 9h).
    Validation must work identically to UTC+1.
    """
    from booking.booking_validator import validate_new_booking

    with schema_context(TENANT_SCHEMA):
        from BaseBillet.models import Configuration
        original_tz_name = Configuration.get_solo().fuseau_horaire

        try:
            tz = _set_tenant_timezone(TZ_NAME_TOKYO)

            monday = _next_weekday(weekday=0)
            calendar = _make_calendar('validation_valid_utc9')
            weekly_opening = _make_weekly_opening('validation_valid_utc9')
            resource_for_test = _make_resource('validation_valid_utc9', calendar, weekly_opening)

            _add_opening_entry(
                weekly_opening,
                weekday=0,
                start_time=datetime.time(10, 0),
                slot_duration_minutes=60,
                slot_count=1,
            )

            start_datetime = _make_aware_in(
                datetime.datetime.combine(monday, datetime.time(10, 0)),
                tz,
            )

            with timezone.override(tz):
                is_valid, error = validate_new_booking(
                    resource=resource_for_test,
                    start_datetime=start_datetime,
                    slot_duration_minutes=60,
                    slot_count=1,
                    member=_get_test_user(),
                )

            assert is_valid is True, f'Attendu True, erreur obtenue : {error}'
            assert error is None

        finally:
            _cleanup()
            _restore_tenant_timezone(original_tz_name)


@pytest.mark.django_db
def test_booking_validation_rejects_full_slot_utc_plus_9():
    """
    validate_new_booking rejette une réservation si le créneau est complet (UTC+9).
    / validate_new_booking rejects a booking if the slot is full (UTC+9).

    LOCALISATION : booking/tests/test_timezone_slots.py

    Ressource capacité=1. Une réservation existante occupe le créneau.
    La deuxième tentative doit être refusée.
    / Resource capacity=1. An existing booking occupies the slot.
    The second attempt must be rejected.
    """
    from booking.booking_validator import validate_new_booking

    with schema_context(TENANT_SCHEMA):
        from BaseBillet.models import Configuration
        original_tz_name = Configuration.get_solo().fuseau_horaire

        try:
            tz = _set_tenant_timezone(TZ_NAME_TOKYO)

            monday = _next_weekday(weekday=0)
            calendar = _make_calendar('validation_full_utc9')
            weekly_opening = _make_weekly_opening('validation_full_utc9')

            # Capacité 1 — un seul booking possible par créneau.
            # / Capacity 1 — only one booking possible per slot.
            resource_for_test = _make_resource(
                'validation_full_utc9', calendar, weekly_opening, capacity=1
            )

            _add_opening_entry(
                weekly_opening,
                weekday=0,
                start_time=datetime.time(10, 0),
                slot_duration_minutes=60,
                slot_count=1,
            )

            start_datetime = _make_aware_in(
                datetime.datetime.combine(monday, datetime.time(10, 0)),
                tz,
            )

            # Remplit le créneau avec une première réservation.
            # / Fill the slot with a first booking.
            _add_booking(
                resource=resource_for_test,
                user=_get_test_user(),
                start_datetime=start_datetime,
                slot_duration_minutes=60,
                slot_count=1,
            )

            # Tente une deuxième réservation sur le même créneau complet.
            # / Attempt a second booking on the same full slot.
            with timezone.override(tz):
                is_valid, error = validate_new_booking(
                    resource=resource_for_test,
                    start_datetime=start_datetime,
                    slot_duration_minutes=60,
                    slot_count=1,
                    member=_get_test_user(),
                )

            assert is_valid is False, 'Attendu False (créneau complet)'
            assert error is not None

        finally:
            _cleanup()
            _restore_tenant_timezone(original_tz_name)


@pytest.mark.django_db
def test_booking_validation_rejects_slot_on_closed_date_utc_plus_1():
    """
    validate_new_booking rejette une réservation si le jour est fermé (UTC+1).
    / validate_new_booking rejects a booking if the day is closed (UTC+1).

    LOCALISATION : booking/tests/test_timezone_slots.py

    Le lundi demandé est dans une ClosedPeriod.
    compute_slots exclut ce créneau → la validation retourne False.
    / The requested Monday is in a ClosedPeriod.
    compute_slots excludes this slot → validation returns False.
    """
    from booking.booking_validator import validate_new_booking

    with schema_context(TENANT_SCHEMA):
        from BaseBillet.models import Configuration
        original_tz_name = Configuration.get_solo().fuseau_horaire

        try:
            tz = _set_tenant_timezone(TZ_NAME_LAGOS)

            monday = _next_weekday(weekday=0)
            calendar = _make_calendar('validation_closed_utc1')
            weekly_opening = _make_weekly_opening('validation_closed_utc1')
            resource_for_test = _make_resource('validation_closed_utc1', calendar, weekly_opening)

            _add_opening_entry(
                weekly_opening,
                weekday=0,
                start_time=datetime.time(10, 0),
                slot_duration_minutes=60,
                slot_count=1,
            )

            # Ferme le lundi demandé — le créneau doit disparaître de compute_slots.
            # / Close the requested Monday — the slot must disappear from compute_slots.
            _add_closed_period(calendar, start_date=monday, label='Lundi fermé Lagos')

            start_datetime = _make_aware_in(
                datetime.datetime.combine(monday, datetime.time(10, 0)),
                tz,
            )

            with timezone.override(tz):
                is_valid, error = validate_new_booking(
                    resource=resource_for_test,
                    start_datetime=start_datetime,
                    slot_duration_minutes=60,
                    slot_count=1,
                    member=_get_test_user(),
                )

            assert is_valid is False, 'Attendu False (lundi fermé Lagos)'
            assert error is not None

        finally:
            _cleanup()
            _restore_tenant_timezone(original_tz_name)
