"""
Tests de la validation d'une nouvelle réservation.
/ Tests for new booking validation.

LOCALISATION : booking/tests/test_booking_validation.py

La fonction testée :
    validate_new_booking(resource, start_datetime, slot_duration_minutes,
                         slot_count, member)
    → (is_valid: bool, error: str | None)

Règles vérifiées :
  1. Tous les créneaux demandés sont dans la fenêtre booking_horizon_days.
  2. Aucun créneau ne tombe dans une ClosedPeriod.
  3. Tous les créneaux ont une remaining_capacity > 0.
/ Rules checked:
  1. All requested slots fall within booking_horizon_days.
  2. No slot falls inside a ClosedPeriod.
  3. All slots have remaining_capacity > 0.

Lancement / Run:
    docker exec lespass_django poetry run pytest \
        booking/tests/test_booking_validation.py -v
"""
import datetime

import pytest
from django.utils import timezone
from django_tenants.utils import schema_context

TEST_PREFIX = '[test_booking_validation]'
TENANT_SCHEMA = 'lespass'

# Date du jour utilisée comme ancrage pour tous les calculs de dates.
# / Today's date used as anchor for all date calculations.
TODAY = datetime.date.today()


# ---------------------------------------------------------------------------
# Helpers — création de données
# / Helpers — data creation
# ---------------------------------------------------------------------------

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


def _make_calendar(label):
    from booking.models import Calendar

    calendar, _ = Calendar.objects.get_or_create(
        name=f'{TEST_PREFIX} {label}',
    )
    return calendar


def _make_weekly_opening(label):
    from booking.models import WeeklyOpening

    opening, _ = WeeklyOpening.objects.get_or_create(
        name=f'{TEST_PREFIX} {label}',
    )
    return opening


def _make_resource(name, calendar, weekly_opening, capacity=1, horizon=28):
    from booking.models import Resource

    resource, _ = Resource.objects.get_or_create(
        name=f'{TEST_PREFIX} {name}',
        defaults={
            'calendar': calendar,
            'weekly_opening': weekly_opening,
            'capacity': capacity,
            'booking_horizon_days': horizon,
        },
    )
    return resource


def _add_opening_entry(
    weekly_opening,
    weekday,
    start_time,
    slot_duration_minutes=60,
    slot_count=1,
):
    from booking.models import OpeningEntry

    return OpeningEntry.objects.create(
        weekly_opening=weekly_opening,
        weekday=weekday,
        start_time=start_time,
        slot_duration_minutes=slot_duration_minutes,
        slot_count=slot_count,
    )


def _add_closed_period(calendar, start_date, end_date=None, label='Fermeture'):
    from booking.models import ClosedPeriod

    return ClosedPeriod.objects.create(
        calendar=calendar,
        start_date=start_date,
        end_date=end_date,
        label=label,
    )


def _add_booking(
    resource,
    user,
    start_datetime,
    slot_duration_minutes=60,
    slot_count=1,
):
    from booking.models import Booking

    return Booking.objects.create(
        resource=resource,
        user=user,
        start_datetime=start_datetime,
        slot_duration_minutes=slot_duration_minutes,
        slot_count=slot_count,
        status='confirmed',
    )


def _cleanup():
    """
    Supprime toutes les données de test dans l'ordre FK (PROTECT).
    / Deletes all test data in FK order (PROTECT).

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


def _make_aware_dt(date, time):
    """
    Construit un datetime timezone-aware à partir d'une date et d'une heure.
    / Builds a timezone-aware datetime from a date and a time.
    """
    tz = timezone.get_current_timezone()
    return timezone.make_aware(datetime.datetime.combine(date, time), tz)


def _next_weekday(weekday, min_days_ahead=2):
    """
    Retourne la prochaine date dont le jour de semaine vaut `weekday`,
    au moins `min_days_ahead` jours dans le futur.
    / Returns the next date with the given weekday, at least
    min_days_ahead days in the future.

    weekday : 0 = lundi (Monday) → 6 = dimanche (Sunday)
    """
    start = TODAY + datetime.timedelta(days=min_days_ahead)
    days_until_weekday = (weekday - start.weekday()) % 7
    return start + datetime.timedelta(days=days_until_weekday)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_validate_booking_accepts_valid_slot():
    """
    Un créneau ouvert, dans l'horizon et non complet est accepté.
    / An open, within-horizon, non-full slot is accepted.

    LOCALISATION : booking/tests/test_booking_validation.py

    Scénario :
    - Ressource : horizon 28 jours, capacité 1.
    - Lundi prochain à 10:00, 1 créneau de 60 min.
    - Aucune réservation existante, aucune fermeture.
    → (True, None)
    / Scenario:
    - Resource: 28-day horizon, capacity 1.
    - Next Monday at 10:00, 1 slot of 60 min.
    - No existing bookings, no closures.
    → (True, None)
    """
    from booking.booking_validator import validate_new_booking

    with schema_context(TENANT_SCHEMA):
        try:
            calendar = _make_calendar('accepts_valid')
            opening = _make_weekly_opening('accepts_valid')
            resource = _make_resource('accepts_valid', calendar, opening, capacity=1, horizon=28)

            # Lundi prochain, au moins 2 jours dans le futur.
            # / Next Monday, at least 2 days in the future.
            next_monday = _next_weekday(weekday=0, min_days_ahead=2)
            slot_time = datetime.time(10, 0)

            _add_opening_entry(
                opening,
                weekday=0,
                start_time=slot_time,
                slot_duration_minutes=60,
                slot_count=1,
            )

            start_dt = _make_aware_dt(next_monday, slot_time)
            user = _get_test_user()

            is_valid, error = validate_new_booking(
                resource=resource,
                start_datetime=start_dt,
                slot_duration_minutes=60,
                slot_count=1,
                member=user,
            )

            assert is_valid is True
            assert error is None
        finally:
            _cleanup()


@pytest.mark.django_db
def test_validate_booking_rejects_slot_beyond_horizon():
    """
    Un créneau au-delà de booking_horizon_days est refusé.
    / A slot beyond booking_horizon_days is rejected.

    LOCALISATION : booking/tests/test_booking_validation.py

    Scénario :
    - Ressource : horizon 7 jours.
    - Créneau demandé : dans 14 jours (lundi à 10:00).
    → (False, message non vide)
    / Scenario:
    - Resource: 7-day horizon.
    - Requested slot: 14 days from today (Monday at 10:00).
    → (False, non-empty message)
    """
    from booking.booking_validator import validate_new_booking

    with schema_context(TENANT_SCHEMA):
        try:
            calendar = _make_calendar('beyond_horizon')
            opening = _make_weekly_opening('beyond_horizon')
            # Horizon 7 jours — la date cible (14j) dépasse la limite.
            # / 7-day horizon — the target date (14d ahead) exceeds the limit.
            resource = _make_resource('beyond_horizon', calendar, opening, capacity=1, horizon=7)

            # Un lundi au moins 14 jours dans le futur.
            # / A Monday at least 14 days in the future.
            far_monday = _next_weekday(weekday=0, min_days_ahead=14)
            slot_time = datetime.time(10, 0)

            _add_opening_entry(
                opening,
                weekday=far_monday.weekday(),
                start_time=slot_time,
                slot_duration_minutes=60,
                slot_count=1,
            )

            start_dt = _make_aware_dt(far_monday, slot_time)
            user = _get_test_user()

            is_valid, error = validate_new_booking(
                resource=resource,
                start_datetime=start_dt,
                slot_duration_minutes=60,
                slot_count=1,
                member=user,
            )

            assert is_valid is False
            assert error is not None
        finally:
            _cleanup()


@pytest.mark.django_db
def test_validate_booking_rejects_slot_in_closed_period():
    """
    Un créneau dans une ClosedPeriod est refusé.
    / A slot falling inside a ClosedPeriod is rejected.

    LOCALISATION : booking/tests/test_booking_validation.py

    Scénario :
    - Ressource : horizon 28 jours.
    - Lundi prochain est déclaré fermé dans le Calendar.
    - Créneau demandé : lundi prochain à 10:00.
    → (False, message non vide)
    / Scenario:
    - Resource: 28-day horizon.
    - Next Monday is declared closed in the Calendar.
    - Requested slot: next Monday at 10:00.
    → (False, non-empty message)
    """
    from booking.booking_validator import validate_new_booking

    with schema_context(TENANT_SCHEMA):
        try:
            calendar = _make_calendar('closed_period')
            opening = _make_weekly_opening('closed_period')
            resource = _make_resource('closed_period', calendar, opening, capacity=1, horizon=28)

            next_monday = _next_weekday(weekday=0, min_days_ahead=2)
            slot_time = datetime.time(10, 0)

            _add_opening_entry(
                opening,
                weekday=0,
                start_time=slot_time,
                slot_duration_minutes=60,
                slot_count=1,
            )
            # Fermeture sur la journée entière du lundi.
            # / Full-day closure on Monday.
            _add_closed_period(
                calendar,
                start_date=next_monday,
                end_date=next_monday,
                label='Fermeture test',
            )

            start_dt = _make_aware_dt(next_monday, slot_time)
            user = _get_test_user()

            is_valid, error = validate_new_booking(
                resource=resource,
                start_datetime=start_dt,
                slot_duration_minutes=60,
                slot_count=1,
                member=user,
            )

            assert is_valid is False
            assert error is not None
        finally:
            _cleanup()


@pytest.mark.django_db
def test_validate_booking_rejects_full_slot():
    """
    Un créneau complet (remaining_capacity == 0) est refusé.
    / A full slot (remaining_capacity == 0) is rejected.

    LOCALISATION : booking/tests/test_booking_validation.py

    Scénario :
    - Ressource : capacité 1, horizon 28 jours.
    - Lundi prochain à 10:00 — une réservation occupe déjà ce créneau.
    → (False, message non vide)
    / Scenario:
    - Resource: capacity 1, 28-day horizon.
    - Next Monday at 10:00 — one existing booking already fills this slot.
    → (False, non-empty message)
    """
    from booking.booking_validator import validate_new_booking

    with schema_context(TENANT_SCHEMA):
        try:
            calendar = _make_calendar('full_slot')
            opening = _make_weekly_opening('full_slot')
            resource = _make_resource('full_slot', calendar, opening, capacity=1, horizon=28)

            next_monday = _next_weekday(weekday=0, min_days_ahead=2)
            slot_time = datetime.time(10, 0)

            _add_opening_entry(
                opening,
                weekday=0,
                start_time=slot_time,
                slot_duration_minutes=60,
                slot_count=1,
            )

            start_dt = _make_aware_dt(next_monday, slot_time)
            user = _get_test_user()

            # Réservation existante qui occupe ce créneau.
            # / Existing booking that fills this slot.
            _add_booking(
                resource,
                user,
                start_datetime=start_dt,
                slot_duration_minutes=60,
                slot_count=1,
            )

            is_valid, error = validate_new_booking(
                resource=resource,
                start_datetime=start_dt,
                slot_duration_minutes=60,
                slot_count=1,
                member=user,
            )

            assert is_valid is False
            assert error is not None
        finally:
            _cleanup()


@pytest.mark.django_db
def test_validate_booking_slot_count_gt_1_all_slots_must_be_available():
    """
    Quand slot_count > 1, tous les créneaux consécutifs doivent être disponibles.
    / When slot_count > 1, all consecutive slots must be available.

    LOCALISATION : booking/tests/test_booking_validation.py

    Scénario :
    - Ressource : capacité 1, horizon 28 jours.
    - Lundi prochain : 3 créneaux de 60 min à partir de 10:00.
    - Aucune réservation existante, aucune fermeture.
    → (True, None)
    / Scenario:
    - Resource: capacity 1, 28-day horizon.
    - Next Monday: 3 slots of 60 min from 10:00.
    - No existing bookings, no closures.
    → (True, None)
    """
    from booking.booking_validator import validate_new_booking

    with schema_context(TENANT_SCHEMA):
        try:
            calendar = _make_calendar('multi_all_available')
            opening = _make_weekly_opening('multi_all_available')
            resource = _make_resource('multi_all_available', calendar, opening, capacity=1, horizon=28)

            next_monday = _next_weekday(weekday=0, min_days_ahead=2)
            slot_time = datetime.time(10, 0)

            # 3 créneaux consécutifs de 60 min disponibles.
            # / 3 consecutive 60-min slots available.
            _add_opening_entry(
                opening,
                weekday=0,
                start_time=slot_time,
                slot_duration_minutes=60,
                slot_count=3,
            )

            start_dt = _make_aware_dt(next_monday, slot_time)
            user = _get_test_user()

            is_valid, error = validate_new_booking(
                resource=resource,
                start_datetime=start_dt,
                slot_duration_minutes=60,
                slot_count=3,
                member=user,
            )

            assert is_valid is True
            assert error is None
        finally:
            _cleanup()


@pytest.mark.django_db
def test_validate_booking_slot_count_gt_1_fails_if_one_slot_full():
    """
    Quand slot_count > 1, un seul créneau complet suffit à invalider
    la demande entière.
    / When slot_count > 1, a single full slot is enough to reject the
    whole request.

    LOCALISATION : booking/tests/test_booking_validation.py

    Scénario :
    - Ressource : capacité 1, horizon 28 jours.
    - Lundi prochain : 3 créneaux de 60 min à partir de 10:00.
    - Le 2ème créneau (11:00–12:00) est déjà réservé.
    - Demande : slot_count=3 à partir de 10:00.
    → (False, message non vide)
    / Scenario:
    - Resource: capacity 1, 28-day horizon.
    - Next Monday: 3 slots of 60 min from 10:00.
    - 2nd slot (11:00–12:00) is already booked.
    - Request: slot_count=3 from 10:00.
    → (False, non-empty message)
    """
    from booking.booking_validator import validate_new_booking

    with schema_context(TENANT_SCHEMA):
        try:
            calendar = _make_calendar('multi_one_full')
            opening = _make_weekly_opening('multi_one_full')
            resource = _make_resource('multi_one_full', calendar, opening, capacity=1, horizon=28)

            next_monday = _next_weekday(weekday=0, min_days_ahead=2)
            slot_time = datetime.time(10, 0)

            _add_opening_entry(
                opening,
                weekday=0,
                start_time=slot_time,
                slot_duration_minutes=60,
                slot_count=3,
            )

            start_dt = _make_aware_dt(next_monday, slot_time)
            # Créneau du milieu (11:00) déjà pris.
            # / Middle slot (11:00) already taken.
            second_slot_start = start_dt + datetime.timedelta(minutes=60)
            user = _get_test_user()

            _add_booking(
                resource,
                user,
                start_datetime=second_slot_start,
                slot_duration_minutes=60,
                slot_count=1,
            )

            is_valid, error = validate_new_booking(
                resource=resource,
                start_datetime=start_dt,
                slot_duration_minutes=60,
                slot_count=3,
                member=user,
            )

            assert is_valid is False
            assert error is not None
        finally:
            _cleanup()


@pytest.mark.django_db
def test_validate_booking_slot_count_gt_1_fails_if_one_slot_in_closed_period():
    """
    Quand slot_count > 1, un seul créneau dans une ClosedPeriod suffit
    à invalider la demande entière.
    / When slot_count > 1, a single slot in a ClosedPeriod is enough to
    reject the whole request.

    LOCALISATION : booking/tests/test_booking_validation.py

    Scénario :
    - Ressource : horizon 28 jours, créneaux de 1 jour (1440 min).
    - Lundi prochain : 3 créneaux journaliers (lundi, mardi, mercredi).
    - Mardi est déclaré fermé.
    - Demande : slot_count=3 à partir de lundi 00:00.
    → (False, message non vide) — le créneau du mardi est dans une fermeture.
    / Scenario:
    - Resource: 28-day horizon, 1-day slots (1440 min).
    - Next Monday: 3 daily slots (Monday, Tuesday, Wednesday).
    - Tuesday is declared closed.
    - Request: slot_count=3 from Monday 00:00.
    → (False, non-empty message) — Tuesday slot falls in a closure.
    """
    from booking.booking_validator import validate_new_booking

    with schema_context(TENANT_SCHEMA):
        try:
            calendar = _make_calendar('multi_one_closed')
            opening = _make_weekly_opening('multi_one_closed')
            resource = _make_resource('multi_one_closed', calendar, opening, capacity=1, horizon=28)

            # Lundi prochain, au moins 3 jours dans le futur pour garantir
            # que lundi + mardi + mercredi sont tous dans l'horizon.
            # / Next Monday, at least 3 days ahead to ensure Mon/Tue/Wed
            # all fall within horizon.
            next_monday = _next_weekday(weekday=0, min_days_ahead=3)
            next_tuesday = next_monday + datetime.timedelta(days=1)
            slot_time = datetime.time(0, 0)

            # Une entrée lundi, 3 créneaux de 24h — couvre lun, mar, mer.
            # / One Monday entry, 3 daily slots — covers Mon, Tue, Wed.
            _add_opening_entry(
                opening,
                weekday=0,
                start_time=slot_time,
                slot_duration_minutes=1440,
                slot_count=3,
            )

            # Fermeture du mardi — le 2ème créneau tombe ce jour-là.
            # / Tuesday closure — the 2nd slot falls on that day.
            _add_closed_period(
                calendar,
                start_date=next_tuesday,
                end_date=next_tuesday,
                label='Fermeture mardi',
            )

            start_dt = _make_aware_dt(next_monday, slot_time)
            user = _get_test_user()

            is_valid, error = validate_new_booking(
                resource=resource,
                start_datetime=start_dt,
                slot_duration_minutes=1440,
                slot_count=3,
                member=user,
            )

            assert is_valid is False
            assert error is not None
        finally:
            _cleanup()


@pytest.mark.django_db
def test_validate_booking_rejects_mismatched_slot_duration():
    """
    Un créneau dont slot_duration_minutes ne correspond à aucun créneau
    théorique est refusé.
    / A slot whose slot_duration_minutes matches no theoretical slot is rejected.

    LOCALISATION : booking/tests/test_booking_validation.py

    Règle métier : chaque créneau demandé doit s'aligner exactement sur
    un créneau théorique (même start_datetime, même slot_duration_minutes).
    / Business rule: each requested slot must align exactly to a theoretical
    slot (same start_datetime, same slot_duration_minutes).

    Scénario :
    - Ouverture : lundi 10:00, 60 min par créneau, slot_count=1.
    - Demande : lundi 10:00, slot_duration_minutes=30.
    → (False, message non vide)
    / Scenario:
    - Opening: Monday 10:00, 60 min per slot, slot_count=1.
    - Request: Monday 10:00, slot_duration_minutes=30.
    → (False, non-empty message)
    """
    from booking.booking_validator import validate_new_booking

    with schema_context(TENANT_SCHEMA):
        try:
            calendar = _make_calendar('mismatched_duration')
            opening = _make_weekly_opening('mismatched_duration')
            resource = _make_resource('mismatched_duration', calendar, opening, capacity=1, horizon=28)

            next_monday = _next_weekday(weekday=0, min_days_ahead=2)
            slot_time = datetime.time(10, 0)

            # Ouverture : créneaux de 60 min.
            # / Opening: 60-min slots.
            _add_opening_entry(
                opening,
                weekday=0,
                start_time=slot_time,
                slot_duration_minutes=60,
                slot_count=1,
            )

            start_dt = _make_aware_dt(next_monday, slot_time)
            user = _get_test_user()

            # Demande avec slot_duration_minutes=30 — ne correspond à aucun
            # créneau théorique de l'ouverture.
            # / Request with slot_duration_minutes=30 — matches no theoretical
            # slot from the opening.
            is_valid, error = validate_new_booking(
                resource=resource,
                start_datetime=start_dt,
                slot_duration_minutes=30,
                slot_count=1,
                member=user,
            )

            assert is_valid is False
            assert error is not None
        finally:
            _cleanup()


@pytest.mark.django_db
def test_validate_booking_rejects_start_time_not_aligned_to_opening():
    """
    Un créneau dont start_datetime ne correspond à aucun créneau théorique
    est refusé.
    / A slot whose start_datetime matches no theoretical slot is rejected.

    LOCALISATION : booking/tests/test_booking_validation.py

    Règle métier : start_datetime doit correspondre exactement au début
    d'un créneau théorique de l'ouverture.
    / Business rule: start_datetime must match exactly the start of a
    theoretical slot from the opening.

    Scénario :
    - Ouverture : lundi 10:00, 60 min, slot_count=1.
    - Demande : lundi 10:15 (décalage de 15 min — non aligné).
    → (False, message non vide)
    / Scenario:
    - Opening: Monday 10:00, 60 min, slot_count=1.
    - Request: Monday 10:15 (15-min offset — not aligned).
    → (False, non-empty message)
    """
    from booking.booking_validator import validate_new_booking

    with schema_context(TENANT_SCHEMA):
        try:
            calendar = _make_calendar('misaligned_start')
            opening = _make_weekly_opening('misaligned_start')
            resource = _make_resource('misaligned_start', calendar, opening, capacity=1, horizon=28)

            next_monday = _next_weekday(weekday=0, min_days_ahead=2)

            _add_opening_entry(
                opening,
                weekday=0,
                start_time=datetime.time(10, 0),
                slot_duration_minutes=60,
                slot_count=1,
            )

            # 10:15 — ni le début ni un multiple de 60 min depuis 10:00.
            # / 10:15 — neither the start nor a multiple of 60 min from 10:00.
            misaligned_dt = _make_aware_dt(next_monday, datetime.time(10, 15))
            user = _get_test_user()

            is_valid, error = validate_new_booking(
                resource=resource,
                start_datetime=misaligned_dt,
                slot_duration_minutes=60,
                slot_count=1,
                member=user,
            )

            assert is_valid is False
            assert error is not None
        finally:
            _cleanup()


@pytest.mark.django_db
def test_validate_booking_slot_count_gt_1_rejects_if_series_exceeds_opening():
    """
    Quand slot_count dépasse le nombre de créneaux définis dans l'ouverture,
    la demande est refusée.
    / When slot_count exceeds the number of slots defined in the opening,
    the request is rejected.

    LOCALISATION : booking/tests/test_booking_validation.py

    Règle métier : chaque créneau de la série doit s'aligner sur un créneau
    théorique. Si l'ouverture définit 2 créneaux et la demande en couvre 3,
    le 3ème créneau n'existe pas dans l'ouverture.
    / Business rule: each slot in the series must align to a theoretical slot.
    If the opening defines 2 slots and the request covers 3, the 3rd slot
    does not exist in the opening.

    Scénario :
    - Ouverture : lundi 10:00, 60 min, slot_count=2 (10:00–11:00 et 11:00–12:00).
    - Demande : slot_count=3 à partir de 10:00 (le 3ème créneau 12:00 n'existe pas).
    → (False, message non vide)
    / Scenario:
    - Opening: Monday 10:00, 60 min, slot_count=2 (10:00–11:00 and 11:00–12:00).
    - Request: slot_count=3 from 10:00 (3rd slot 12:00 does not exist).
    → (False, non-empty message)
    """
    from booking.booking_validator import validate_new_booking

    with schema_context(TENANT_SCHEMA):
        try:
            calendar = _make_calendar('exceeds_opening')
            opening = _make_weekly_opening('exceeds_opening')
            resource = _make_resource('exceeds_opening', calendar, opening, capacity=1, horizon=28)

            next_monday = _next_weekday(weekday=0, min_days_ahead=2)
            slot_time = datetime.time(10, 0)

            # Ouverture : seulement 2 créneaux de 60 min.
            # / Opening: only 2 slots of 60 min.
            _add_opening_entry(
                opening,
                weekday=0,
                start_time=slot_time,
                slot_duration_minutes=60,
                slot_count=2,
            )

            start_dt = _make_aware_dt(next_monday, slot_time)
            user = _get_test_user()

            # Demande de 3 créneaux — le 3ème (12:00) n'est pas dans l'ouverture.
            # / Request for 3 slots — the 3rd (12:00) is not in the opening.
            is_valid, error = validate_new_booking(
                resource=resource,
                start_datetime=start_dt,
                slot_duration_minutes=60,
                slot_count=3,
                member=user,
            )

            assert is_valid is False
            assert error is not None
        finally:
            _cleanup()


@pytest.mark.django_db
def test_validate_booking_accepts_slot_bleeding_into_next_open_day():
    """
    Un créneau qui déborde sur le lendemain est accepté si le lendemain
    est ouvert.
    / A slot bleeding into the next day is accepted when the next day is open.

    LOCALISATION : booking/tests/test_booking_validation.py

    Scénario :
    - Ouverture : lundi 23:00, 120 min (créneau 23:00–01:00 du mardi).
    - Aucune fermeture.
    → (True, None)
    / Scenario:
    - Opening: Monday 23:00, 120 min (slot 23:00–01:00 Tuesday).
    - No closure.
    → (True, None)
    """
    from booking.booking_validator import validate_new_booking

    with schema_context(TENANT_SCHEMA):
        try:
            calendar = _make_calendar('bleed_open_next_day')
            opening = _make_weekly_opening('bleed_open_next_day')
            resource = _make_resource('bleed_open_next_day', calendar, opening, capacity=1, horizon=28)

            next_monday = _next_weekday(weekday=0, min_days_ahead=2)

            _add_opening_entry(
                opening,
                weekday=0,
                start_time=datetime.time(23, 0),
                slot_duration_minutes=120,
                slot_count=1,
            )

            start_dt = _make_aware_dt(next_monday, datetime.time(23, 0))
            user = _get_test_user()

            is_valid, error = validate_new_booking(
                resource=resource,
                start_datetime=start_dt,
                slot_duration_minutes=120,
                slot_count=1,
                member=user,
            )

            assert is_valid is True
            assert error is None
        finally:
            _cleanup()


@pytest.mark.django_db
def test_validate_booking_rejects_slot_bleeding_into_closed_next_day():
    """
    Un créneau qui déborde sur le lendemain est refusé si le lendemain
    est fermé.
    / A slot bleeding into the next day is rejected when the next day is closed.

    LOCALISATION : booking/tests/test_booking_validation.py

    Scénario :
    - Ouverture : lundi 23:00, 120 min (créneau 23:00–01:00 du mardi).
    - Mardi déclaré fermé.
    → (False, message non vide) — le créneau intersecte mardi (fermé).
    / Scenario:
    - Opening: Monday 23:00, 120 min (slot 23:00–01:00 Tuesday).
    - Tuesday declared closed.
    → (False, non-empty message) — the slot intersects Tuesday (closed).
    """
    from booking.booking_validator import validate_new_booking

    with schema_context(TENANT_SCHEMA):
        try:
            calendar = _make_calendar('bleed_closed_next_day')
            opening = _make_weekly_opening('bleed_closed_next_day')
            resource = _make_resource('bleed_closed_next_day', calendar, opening, capacity=1, horizon=28)

            next_monday = _next_weekday(weekday=0, min_days_ahead=2)
            next_tuesday = next_monday + datetime.timedelta(days=1)

            _add_opening_entry(
                opening,
                weekday=0,
                start_time=datetime.time(23, 0),
                slot_duration_minutes=120,
                slot_count=1,
            )

            # Fermeture du mardi — le créneau lundi 23:00–mardi 01:00
            # intersecte ce jour fermé.
            # / Tuesday closure — the Monday 23:00–Tuesday 01:00 slot
            # intersects this closed day.
            _add_closed_period(
                calendar,
                start_date=next_tuesday,
                end_date=next_tuesday,
                label='Fermeture mardi',
            )

            start_dt = _make_aware_dt(next_monday, datetime.time(23, 0))
            user = _get_test_user()

            is_valid, error = validate_new_booking(
                resource=resource,
                start_datetime=start_dt,
                slot_duration_minutes=120,
                slot_count=1,
                member=user,
            )

            assert is_valid is False
            assert error is not None
        finally:
            _cleanup()
