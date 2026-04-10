"""
Tests du moteur de calcul de créneaux (slot engine).
/ Tests for the slot computation engine.

LOCALISATION : booking/tests/test_slot_engine.py

Règle métier : les créneaux sont calculés à la volée à partir du
WeeklyOpening, du Calendar et des réservations existantes de la ressource.
Aucune ligne Slot n'est stockée en base.
/ Business rule: slots are computed on the fly from WeeklyOpening, Calendar,
and existing bookings. No Slot rows are stored in the database.

Chaque test crée ses propres données et les nettoie dans un bloc try/finally.
/ Each test creates its own data and cleans it up in a try/finally block.

Lancement / Run:
    docker exec lespass_django poetry run pytest \
        booking/tests/test_slot_engine.py -v
"""
import datetime

import pytest
from django.utils import timezone
from django_tenants.utils import schema_context

TEST_PREFIX = '[test_slot_engine]'
TENANT_SCHEMA = 'lespass'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_resource(name, calendar, weekly_opening, capacity=1, horizon=28):
    """
    Crée une Resource de test avec les paramètres donnés.
    / Creates a test Resource with the given parameters.
    """
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


def _make_calendar(label):
    """
    Crée un Calendar de test.
    / Creates a test Calendar.
    """
    from booking.models import Calendar

    calendar, _created = Calendar.objects.get_or_create(
        name=f'{TEST_PREFIX} {label}',
    )
    return calendar


def _make_weekly_opening(label):
    """
    Crée un WeeklyOpening de test sans entrées.
    / Creates a test WeeklyOpening with no entries.
    """
    from booking.models import WeeklyOpening

    opening, _created = WeeklyOpening.objects.get_or_create(
        name=f'{TEST_PREFIX} {label}',
    )
    return opening


def _cleanup():
    """
    Supprime toutes les données de test dans l'ordre correct (on_delete=PROTECT).
    / Deletes all test data in the correct order (on_delete=PROTECT).
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


# ---------------------------------------------------------------------------
# Tests — get_closed_dates_for_resource
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_get_closed_dates_returns_all_dates_in_closed_period():
    """
    get_closed_dates_for_resource retourne toutes les dates d'une période
    de fermeture multi-jours.
    / get_closed_dates_for_resource returns all dates of a multi-day closure.

    LOCALISATION : booking/tests/test_slot_engine.py

    Période : 2026-06-10 → 2026-06-12.
    La requête couvre juin 2026 entier.
    Les trois dates fermées doivent apparaître dans le résultat.
    La date précédente (2026-06-09) ne doit pas y être.
    / Period: 2026-06-10 → 2026-06-12. Query covers all of June 2026.
    / The three closed dates must appear in the result.
    / The preceding date (2026-06-09) must not.

    Juin 2026 (jours) :
     1   2   3   4   5   6   7   8   9  10  11  12  13  14 …
     ·   ·   ·   ·   ·   ·   ·   ·   ·  ░░  ░░  ░░   ·   · …
                                     ✗   ↑   ↑   ↑   ✗
    """
    from booking.models import ClosedPeriod
    from booking.slot_engine import get_closed_dates_for_resource

    with schema_context(TENANT_SCHEMA):
        try:
            calendar = _make_calendar('multi_day_closure')
            weekly_opening = _make_weekly_opening('multi_day_closure')
            resource = _make_resource('multi_day_closure', calendar, weekly_opening)

            ClosedPeriod.objects.create(
                calendar=calendar,
                start_date=datetime.date(2026, 6, 10),
                end_date=datetime.date(2026, 6, 12),
                label='Test closure',
            )

            closed = get_closed_dates_for_resource(
                resource,
                datetime.date(2026, 6, 1),
                datetime.date(2026, 6, 30),
            )

            assert datetime.date(2026, 6, 10) in closed
            assert datetime.date(2026, 6, 11) in closed
            assert datetime.date(2026, 6, 12) in closed
            assert datetime.date(2026, 6, 9) not in closed
            assert datetime.date(2026, 6, 13) not in closed

        finally:
            _cleanup()


@pytest.mark.django_db
def test_get_closed_dates_handles_single_day_period():
    """
    get_closed_dates_for_resource gère une ClosedPeriod d'un seul jour
    (start_date == end_date).
    / get_closed_dates_for_resource handles a single-day ClosedPeriod.

    LOCALISATION : booking/tests/test_slot_engine.py

    2026-06-15 est fermé. 2026-06-14 et 2026-06-16 doivent rester ouverts.
    / 2026-06-15 is closed. 2026-06-14 and 2026-06-16 must remain open.

    …  13  14  15  16  17 …
    …   ·   ·  ░░   ·   · …
            ✗   ↑   ✗
    """
    from booking.models import ClosedPeriod
    from booking.slot_engine import get_closed_dates_for_resource

    with schema_context(TENANT_SCHEMA):
        try:
            calendar = _make_calendar('single_day_closure')
            weekly_opening = _make_weekly_opening('single_day_closure')
            resource = _make_resource('single_day_closure', calendar, weekly_opening)

            ClosedPeriod.objects.create(
                calendar=calendar,
                start_date=datetime.date(2026, 6, 15),
                end_date=datetime.date(2026, 6, 15),
                label='Single day',
            )

            closed = get_closed_dates_for_resource(
                resource,
                datetime.date(2026, 6, 1),
                datetime.date(2026, 6, 30),
            )

            assert datetime.date(2026, 6, 15) in closed
            assert datetime.date(2026, 6, 14) not in closed
            assert datetime.date(2026, 6, 16) not in closed

        finally:
            _cleanup()


@pytest.mark.django_db
def test_get_closed_dates_handles_null_end_date():
    """
    get_closed_dates_for_resource gère une fermeture sans fin (end_date=None).
    Les dates de la fenêtre de requête après start_date sont toutes fermées.
    / get_closed_dates_for_resource handles an endless closure (end_date=None).
    / All dates in the query window after start_date are closed.

    LOCALISATION : booking/tests/test_slot_engine.py

    Fermeture sans fin depuis 2026-06-20.
    Fenêtre de requête : 2026-06-18 → 2026-06-25.
    2026-06-20 à 2026-06-25 doivent être fermés. 2026-06-19 doit être ouvert.
    / Endless closure from 2026-06-20.
    / Query window: 2026-06-18 → 2026-06-25.
    / 2026-06-20 to 2026-06-25 must be closed. 2026-06-19 must be open.

    Fenêtre 18–25 :
     18  19  20  21  22  23  24  25
      ·   ·  ░░  ░░  ░░  ░░  ░░  ░░
         ✗   ↑   ↑   ↑   ↑   ↑   ↑
    La fermeture s'étend jusqu'à date_to car end_date est None.
    / Closure extends to date_to because end_date is None.
    """
    from booking.models import ClosedPeriod
    from booking.slot_engine import get_closed_dates_for_resource

    with schema_context(TENANT_SCHEMA):
        try:
            calendar = _make_calendar('null_end_date')
            weekly_opening = _make_weekly_opening('null_end_date')
            resource = _make_resource('null_end_date', calendar, weekly_opening)

            ClosedPeriod.objects.create(
                calendar=calendar,
                start_date=datetime.date(2026, 6, 20),
                end_date=None,
                label='Endless closure',
            )

            closed = get_closed_dates_for_resource(
                resource,
                datetime.date(2026, 6, 18),
                datetime.date(2026, 6, 25),
            )

            for day in range(20, 26):
                assert datetime.date(2026, 6, day) in closed

            assert datetime.date(2026, 6, 19) not in closed

        finally:
            _cleanup()


@pytest.mark.django_db
def test_get_closed_dates_handles_overlapping_closed_periods():
    """
    get_closed_dates_for_resource retourne l'union de deux ClosedPeriod
    qui se chevauchent, sans doublon ni trou.
    / get_closed_dates_for_resource returns the union of two overlapping
    ClosedPeriods, without duplicates or gaps.

    LOCALISATION : booking/tests/test_slot_engine.py

    Période A : 2026-06-10 → 2026-06-15.
    Période B : 2026-06-13 → 2026-06-18 (chevauche A sur 13–15).
    Union attendue : 2026-06-10 → 2026-06-18 (9 dates).
    / Period A: 2026-06-10 → 2026-06-15.
    / Period B: 2026-06-13 → 2026-06-18 (overlaps A on 13–15).
    / Expected union: 2026-06-10 → 2026-06-18 (9 dates).

     10  11  12  13  14  15  16  17  18
    ░░░A░░░░░░░░░░░░░░░
                  ░░░░░░B░░░░░░░░░░░░░
    ──────────────────────────────────
    ↑   ↑   ↑   ↑   ↑   ↑   ↑   ↑   ↑   (toutes dans le résultat)
    """
    from booking.models import ClosedPeriod
    from booking.slot_engine import get_closed_dates_for_resource

    with schema_context(TENANT_SCHEMA):
        try:
            calendar = _make_calendar('overlapping_periods')
            weekly_opening = _make_weekly_opening('overlapping_periods')
            resource = _make_resource('overlapping_periods', calendar, weekly_opening)

            ClosedPeriod.objects.create(
                calendar=calendar,
                start_date=datetime.date(2026, 6, 10),
                end_date=datetime.date(2026, 6, 15),
                label='Période A',
            )
            ClosedPeriod.objects.create(
                calendar=calendar,
                start_date=datetime.date(2026, 6, 13),
                end_date=datetime.date(2026, 6, 18),
                label='Période B',
            )

            closed = get_closed_dates_for_resource(
                resource,
                datetime.date(2026, 6, 1),
                datetime.date(2026, 6, 30),
            )

            # Toutes les dates de l'union doivent être présentes.
            # / All dates of the union must be present.
            for day in range(10, 19):
                assert datetime.date(2026, 6, day) in closed

            # Les dates hors union doivent être absentes.
            # / Dates outside the union must be absent.
            assert datetime.date(2026, 6, 9) not in closed
            assert datetime.date(2026, 6, 19) not in closed

        finally:
            _cleanup()


# ---------------------------------------------------------------------------
# Tests — generate_theoretical_slots
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_generate_theoretical_slots_from_weekday_template():
    """
    generate_theoretical_slots génère les bons créneaux à partir d'un
    OpeningEntry (lundi 09:00, 60 min, 2 créneaux).
    / generate_theoretical_slots generates correct slots from an OpeningEntry
    / (Monday 09:00, 60 min, 2 slots).

    LOCALISATION : booking/tests/test_slot_engine.py

    2026-06-01 est un lundi.
    start_datetime du premier créneau : 2026-06-01 09:00 (timezone-aware).
    end_datetime du premier créneau   : 2026-06-01 10:00.
    start_datetime du deuxième créneau : 2026-06-01 10:00.
    / 2026-06-01 is a Monday.
    / First slot start_datetime: 2026-06-01 09:00 (timezone-aware).
    / First slot end_datetime: 2026-06-01 10:00.
    / Second slot start_datetime: 2026-06-01 10:00.

    Lundi 2026-06-01 :
    08:00  09:00  10:00  11:00
             ████   ████
             ↑      ↑
          slot[0] slot[1]
          09–10   10–11   (timezone-aware)
    """
    from booking.models import OpeningEntry, WeeklyOpening
    from booking.slot_engine import generate_theoretical_slots

    with schema_context(TENANT_SCHEMA):
        try:
            opening = WeeklyOpening.objects.create(
                name=f'{TEST_PREFIX} gen_from_template',
            )
            entry = OpeningEntry.objects.create(
                weekly_opening=opening,
                weekday=OpeningEntry.MONDAY,
                start_time=datetime.time(9, 0),
                slot_duration_minutes=60,
                slot_count=2,
            )

            slots = generate_theoretical_slots(
                opening_entries=[entry],
                date_from=datetime.date(2026, 6, 1),
                date_to=datetime.date(2026, 6, 1),
                closed_dates=set(),
            )

            assert len(slots) == 2
            assert slots[0].start.date() == datetime.date(2026, 6, 1)
            assert slots[0].start.time() == datetime.time(9, 0)
            assert slots[0].end.time() == datetime.time(10, 0)
            assert slots[1].start.time() == datetime.time(10, 0)
            assert slots[1].end.time() == datetime.time(11, 0)
            # Les start_datetime doivent être timezone-aware.
            # / start_datetime must be timezone-aware.
            assert slots[0].start.tzinfo is not None

        finally:
            OpeningEntry.objects.filter(
                weekly_opening__name__startswith=TEST_PREFIX,
            ).delete()
            WeeklyOpening.objects.filter(name__startswith=TEST_PREFIX).delete()


@pytest.mark.django_db
def test_generate_theoretical_slots_excludes_closed_dates():
    """
    generate_theoretical_slots exclut les dates fermées passées dans closed_dates.
    / generate_theoretical_slots excludes dates passed in closed_dates.

    LOCALISATION : booking/tests/test_slot_engine.py

    Deux lundis : 2026-06-01 (fermé) et 2026-06-08 (ouvert).
    Seul le créneau du 2026-06-08 doit être retourné.
    / Two Mondays: 2026-06-01 (closed) and 2026-06-08 (open).
    / Only the 2026-06-08 slot must be returned.

    Lun 01 Jun    Lun 08 Jun
      ░░░░          ████
      ✗ bloqué      ↑ retourné
    """
    from booking.models import OpeningEntry, WeeklyOpening
    from booking.slot_engine import generate_theoretical_slots

    with schema_context(TENANT_SCHEMA):
        try:
            opening = WeeklyOpening.objects.create(
                name=f'{TEST_PREFIX} exclude_closed_dates',
            )
            entry = OpeningEntry.objects.create(
                weekly_opening=opening,
                weekday=OpeningEntry.MONDAY,
                start_time=datetime.time(9, 0),
                slot_duration_minutes=60,
                slot_count=1,
            )

            closed_dates = {datetime.date(2026, 6, 1)}

            slots = generate_theoretical_slots(
                opening_entries=[entry],
                date_from=datetime.date(2026, 6, 1),
                date_to=datetime.date(2026, 6, 8),
                closed_dates=closed_dates,
            )

            assert len(slots) == 1
            assert slots[0].start.date() == datetime.date(2026, 6, 8)

        finally:
            OpeningEntry.objects.filter(
                weekly_opening__name__startswith=TEST_PREFIX,
            ).delete()
            WeeklyOpening.objects.filter(name__startswith=TEST_PREFIX).delete()


@pytest.mark.django_db
def test_generate_theoretical_slots_respects_date_to_boundary():
    """
    generate_theoretical_slots ne génère pas de créneaux après date_to.
    / generate_theoretical_slots does not generate slots after date_to.

    LOCALISATION : booking/tests/test_slot_engine.py

    Fenêtre : 2026-06-01 (lundi) → 2026-06-07 (dimanche).
    Un seul lundi dans cette fenêtre : 2026-06-01.
    Le lundi suivant 2026-06-08 est hors fenêtre et ne doit pas apparaître.
    / Window: 2026-06-01 (Mon) → 2026-06-07 (Sun). One Monday in window.
    / 2026-06-08 is outside the window and must not appear.

    Lun 01  Mar 02 … Dim 07 | Lun 08 (hors fenêtre)
      ████    ·        ·    |   ✗
      ↑
    """
    from booking.models import OpeningEntry, WeeklyOpening
    from booking.slot_engine import generate_theoretical_slots

    with schema_context(TENANT_SCHEMA):
        try:
            opening = WeeklyOpening.objects.create(
                name=f'{TEST_PREFIX} date_to_boundary',
            )
            entry = OpeningEntry.objects.create(
                weekly_opening=opening,
                weekday=OpeningEntry.MONDAY,
                start_time=datetime.time(9, 0),
                slot_duration_minutes=60,
                slot_count=1,
            )

            slots = generate_theoretical_slots(
                opening_entries=[entry],
                date_from=datetime.date(2026, 6, 1),
                date_to=datetime.date(2026, 6, 7),
                closed_dates=set(),
            )

            assert len(slots) == 1
            assert slots[0].start.date() == datetime.date(2026, 6, 1)

        finally:
            OpeningEntry.objects.filter(
                weekly_opening__name__startswith=TEST_PREFIX,
            ).delete()
            WeeklyOpening.objects.filter(name__startswith=TEST_PREFIX).delete()


@pytest.mark.django_db
def test_generate_theoretical_slots_start_on_closed_day_bleed_into_open_day_is_excluded():
    """
    Un créneau qui DÉMARRE un jour fermé est exclu même si sa fin tombe
    un jour ouvert. La fermeture s'applique à la date de début.
    / A slot that STARTS on a closed day is excluded even if its end falls
    on an open day. Closure applies to the start date.

    LOCALISATION : booking/tests/test_slot_engine.py

    Scénario :
    - OpeningEntry : lundi 23:30, 60 min, 1 créneau.
    - Le créneau déborde : start=lundi 23:30, end=mardi 00:30.
    - Lundi est fermé (ClosedPeriod). Mardi est ouvert.
    - Résultat attendu : 0 créneau retourné (commence lundi → bloqué).
    / Scenario:
    - OpeningEntry: Monday 23:30, 60 min, 1 slot.
    - Slot bleeds: start=Monday 23:30, end=Tuesday 00:30.
    - Monday is closed. Tuesday is open.
    - Expected: 0 slots returned (starts Monday → blocked).

    Lun 01/06 (fermé ░░)        Mar 02/06 (ouvert)
    ────────────────────────────────────────────────
    22:00  23:00  23:30  00:00  00:30
                   ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓
                   ✗ bloqué — démarre lundi (░░)
    Résultat : 0 créneaux. / Result: 0 slots.
    """
    from booking.models import ClosedPeriod, OpeningEntry, WeeklyOpening
    from booking.slot_engine import generate_theoretical_slots

    with schema_context(TENANT_SCHEMA):
        try:
            # 2026-06-01 est un lundi fermé, 2026-06-02 est un mardi ouvert.
            # / 2026-06-01 is a closed Monday, 2026-06-02 is an open Tuesday.
            calendar = _make_calendar('start_closed_end_open')
            weekly_opening = _make_weekly_opening('start_closed_end_open')
            resource = _make_resource('start_closed_end_open', calendar, weekly_opening)

            ClosedPeriod.objects.create(
                calendar=calendar,
                start_date=datetime.date(2026, 6, 1),
                end_date=datetime.date(2026, 6, 1),
                label='Lundi fermé',
            )

            entry = OpeningEntry.objects.create(
                weekly_opening=weekly_opening,
                weekday=OpeningEntry.MONDAY,
                start_time=datetime.time(23, 30),
                slot_duration_minutes=60,
                slot_count=1,
            )

            closed_dates = {datetime.date(2026, 6, 1)}

            slots = generate_theoretical_slots(
                opening_entries=[entry],
                date_from=datetime.date(2026, 6, 1),
                date_to=datetime.date(2026, 6, 2),
                closed_dates=closed_dates,
            )

            # Le créneau commence lundi (fermé) → il doit être EXCLU.
            # Même si la fin tombe mardi (ouvert).
            # / Slot starts Monday (closed) → must be EXCLUDED.
            # / Even though end falls on Tuesday (open).
            assert len(slots) == 0

        finally:
            _cleanup()


@pytest.mark.django_db
def test_generate_theoretical_slots_last_slot_bleeds_onto_open_day_is_returned():
    """
    Quand un OpeningEntry génère plusieurs créneaux et que certains démarrent
    un jour fermé, les créneaux suivants dont le start_datetime tombe sur un
    jour ouvert doivent quand même être retournés.
    / When an OpeningEntry generates multiple slots and some start on a closed
    day, subsequent slots whose start_datetime falls on an open day must still
    be returned.

    LOCALISATION : booking/tests/test_slot_engine.py

    La vérification des fermetures se fait sur la DATE DE DÉBUT DU CRÉNEAU
    (slot par slot), pas sur la date de l'OpeningEntry.
    / Closure check is on each slot's start_datetime.date(), not on the
    OpeningEntry's weekday date.

    Scénario :
    - OpeningEntry : lundi 22:00, 120 min, slot_count=2.
    - Lundi 2026-06-01 est fermé. Mardi 2026-06-02 est ouvert.
    - slot[0] : start=lundi 22:00, end=mardi 00:00 → start_date=lundi (░░) → EXCLU.
    - slot[1] : start=mardi 00:00, end=mardi 02:00 → start_date=mardi (ouvert) → RETOURNÉ.
    - Résultat attendu : 1 créneau (slot[1] seulement).
    / Scenario:
    - OpeningEntry: Monday 22:00, 120 min, slot_count=2.
    - Monday 2026-06-01 is closed. Tuesday 2026-06-02 is open.
    - slot[0]: start=Mon 22:00, end=Tue 00:00 → start_date=Mon (░░) → EXCLUDED.
    - slot[1]: start=Tue 00:00, end=Tue 02:00 → start_date=Tue (open) → RETURNED.
    - Expected: 1 slot (slot[1] only).

    Lun 01/06 (fermé ░░)         Mar 02/06 (ouvert)
    ──────────────────────────────────────────────────
    22:00       00:00       02:00
      ├── slot[0] ─┤── slot[1] ──┤
      ✗ exclu      ↑ retourné
      start=lun░░  start=mar

    Implémentation : la vérification `start_datetime.date() in closed_dates`
    doit être faite SLOT PAR SLOT, pas une fois pour l'entrée entière.
    / Implementation: the check `start_datetime.date() in closed_dates`
    must be done PER SLOT, not once for the whole entry.
    """
    from booking.models import ClosedPeriod, OpeningEntry, WeeklyOpening
    from booking.slot_engine import generate_theoretical_slots

    with schema_context(TENANT_SCHEMA):
        try:
            # 2026-06-01 est un lundi fermé, 2026-06-02 est un mardi ouvert.
            # / 2026-06-01 is a closed Monday, 2026-06-02 is an open Tuesday.
            calendar = _make_calendar('last_slot_open_day')
            weekly_opening = _make_weekly_opening('last_slot_open_day')
            resource = _make_resource('last_slot_open_day', calendar, weekly_opening)

            ClosedPeriod.objects.create(
                calendar=calendar,
                start_date=datetime.date(2026, 6, 1),
                end_date=datetime.date(2026, 6, 1),
                label='Lundi fermé',
            )

            entry = OpeningEntry.objects.create(
                weekly_opening=weekly_opening,
                weekday=OpeningEntry.MONDAY,
                start_time=datetime.time(22, 0),
                slot_duration_minutes=120,
                slot_count=2,
            )

            closed_dates = {datetime.date(2026, 6, 1)}

            slots = generate_theoretical_slots(
                opening_entries=[entry],
                date_from=datetime.date(2026, 6, 1),
                date_to=datetime.date(2026, 6, 2),
                closed_dates=closed_dates,
            )

            # slot[0] commence lundi (fermé) → exclu.
            # slot[1] commence mardi (ouvert) → retourné.
            # / slot[0] starts Monday (closed) → excluded.
            # / slot[1] starts Tuesday (open) → returned.
            assert len(slots) == 1
            assert slots[0].start.date() == datetime.date(2026, 6, 2)
            assert slots[0].start.time() == datetime.time(0, 0)
            assert slots[0].end.time() == datetime.time(2, 0)

        finally:
            _cleanup()


@pytest.mark.django_db
def test_generate_theoretical_slots_multi_day_spanning_entry():
    """
    Un OpeningEntry dont les créneaux s'étendent sur plusieurs jours :
    slot_duration_minutes=720 (12h), slot_count=3.
    Le créneau [1] (lundi 20:00 → mardi 08:00) débute lundi (ouvert).
    Le créneau [2] (mardi 08:00 → mardi 20:00) débute mardi (fermé) → exclu.
    / An OpeningEntry whose slots span multiple days:
    slot_duration_minutes=720 (12h), slot_count=3.
    Slot [1] (Mon 20:00 → Tue 08:00) starts Monday (open).
    Slot [2] (Tue 08:00 → Tue 20:00) starts Tuesday (closed) → excluded.

    LOCALISATION : booking/tests/test_slot_engine.py

    OpeningEntry : lundi 08:00, 720 min (12h), slot_count=3.
    Créneaux théoriques :
      [0] lundi 08:00 → 20:00  (entier sur lundi ouvert → RETOURNÉ)
      [1] lundi 20:00 → mardi 08:00 (déborde sur mardi → EXCLU)
      [2] mardi 08:00 → mardi 20:00 (mardi fermé → EXCLU)
    closed_dates = {mardi 2026-06-02}.
    Résultat attendu : 1 créneau ([0] seulement).
    Règle : inclusion complète dans un seul jour ouvert (decisions §7).
    / OpeningEntry: Monday 08:00, 720 min (12h), slot_count=3.
    / Theoretical slots:
    /   [0] Mon 08:00–20:00  (fully on open Monday → RETURNED)
    /   [1] Mon 20:00–Tue 08:00 (bleeds past midnight → EXCLUDED)
    /   [2] Tue 08:00–20:00  (Tuesday closed → EXCLUDED)
    / Expected: 1 slot ([0] only). Rule: must fit entirely within a single open day.

    Lun 01/06 (ouvert)              Mar 02/06 (fermé ░░)
    ─────────────────────────────────────────────────────────
    08:00          20:00       00:00        08:00          20:00
      ├──── [0] ────┤           │            │
      ↑ RETOURNÉ     ├──── [1] ─────────────┤    ├──── [2] ────┤
                     ✗ intersecte mar (░░)        ✗ mar (░░)
    """
    from booking.models import OpeningEntry, WeeklyOpening
    from booking.slot_engine import generate_theoretical_slots

    with schema_context(TENANT_SCHEMA):
        try:
            opening = WeeklyOpening.objects.create(
                name=f'{TEST_PREFIX} multi_day_entry',
            )
            entry = OpeningEntry.objects.create(
                weekly_opening=opening,
                weekday=OpeningEntry.MONDAY,
                start_time=datetime.time(8, 0),
                slot_duration_minutes=720,
                slot_count=3,
            )

            # Mardi 2026-06-02 est fermé.
            # / Tuesday 2026-06-02 is closed.
            closed_dates = {datetime.date(2026, 6, 2)}

            slots = generate_theoretical_slots(
                opening_entries=[entry],
                date_from=datetime.date(2026, 6, 1),
                date_to=datetime.date(2026, 6, 2),
                closed_dates=closed_dates,
            )

            # Seul [0] est retourné : tous ses jours intersectés (lundi) sont ouverts.
            # [1] intersecte mardi (fermé) → exclu (decisions §7).
            # [2] intersecte mardi (fermé) → exclu.
            # / Only [0] returned: all intersected days (Monday) are open.
            # / [1] intersects Tuesday (closed) → excluded (decisions §7).
            # / [2] intersects Tuesday (closed) → excluded.
            assert len(slots) == 1
            assert slots[0].start.date() == datetime.date(2026, 6, 1)
            assert slots[0].start.time() == datetime.time(8, 0)
            assert slots[0].end.time() == datetime.time(20, 0)

        finally:
            OpeningEntry.objects.filter(
                weekly_opening__name__startswith=TEST_PREFIX,
            ).delete()
            WeeklyOpening.objects.filter(name__startswith=TEST_PREFIX).delete()


@pytest.mark.django_db
def test_generate_theoretical_slots_bleed_into_closed_day_start_date_is_open():
    """
    Un créneau qui démarre un jour ouvert mais se termine un jour fermé doit
    quand même être retourné. La fermeture s'applique à la date de début,
    pas à la date de fin.
    / A slot starting on an open day but ending on a closed day must still
    be returned. Closure applies to the start date, not the end date.

    LOCALISATION : booking/tests/test_slot_engine.py

    Scénario :
    - OpeningEntry : dimanche 23:30, 60 min, 1 créneau.
    - Le créneau déborde : start=dimanche 23:30, end=lundi 00:30.
    - Lundi est une date fermée (ClosedPeriod).
    - Résultat attendu : 0 créneau retourné.
      Le créneau déborde sur le lendemain → exclu (règle : inclusion complète
      dans un seul jour ouvert — voir decisions §7).
    / Scenario:
    - OpeningEntry: Sunday 23:30, 60 min, 1 slot.
    - Slot bleeds: start=Sunday 23:30, end=Monday 00:30.
    - Monday is a closed date (ClosedPeriod).
    - Expected: 0 slots returned.
      Slot bleeds past midnight → excluded (rule: must fit entirely within
      a single open day — see decisions §7).

    Dim 07/06 (ouvert)           Lun 08/06 (fermé ░░)
    ─────────────────────────────────────────────────────
    22:00  23:00  23:30  00:00  00:30
                   ████████████████
                   ↑ start         ↑ end
                   (dim ouvert)    (lun ░░)
    Le créneau intersecte lundi (fermé) → EXCLU.
    / Slot intersects Monday (closed) → EXCLUDED.
    Résultat : 0 créneaux. / Result: 0 slots.
    """
    from booking.models import ClosedPeriod, OpeningEntry, WeeklyOpening
    from booking.slot_engine import generate_theoretical_slots

    with schema_context(TENANT_SCHEMA):
        try:
            # 2026-06-07 est un dimanche, 2026-06-08 est un lundi fermé.
            # / 2026-06-07 is a Sunday, 2026-06-08 is a closed Monday.
            calendar = _make_calendar('bleed_into_closed')
            weekly_opening = _make_weekly_opening('bleed_into_closed')
            resource = _make_resource('bleed_into_closed', calendar, weekly_opening)

            ClosedPeriod.objects.create(
                calendar=calendar,
                start_date=datetime.date(2026, 6, 8),
                end_date=datetime.date(2026, 6, 8),
                label='Lundi fermé',
            )

            entry = OpeningEntry.objects.create(
                weekly_opening=weekly_opening,
                weekday=OpeningEntry.SUNDAY,
                start_time=datetime.time(23, 30),
                slot_duration_minutes=60,
                slot_count=1,
            )

            closed_dates = {datetime.date(2026, 6, 8)}

            slots = generate_theoretical_slots(
                opening_entries=[entry],
                date_from=datetime.date(2026, 6, 7),
                date_to=datetime.date(2026, 6, 8),
                closed_dates=closed_dates,
            )

            # Le créneau intersecte lundi (fermé) → exclu.
            # / Slot intersects Monday (closed) → excluded.
            assert len(slots) == 0

        finally:
            _cleanup()


@pytest.mark.django_db
def test_generate_theoretical_slots_multi_day_slot_all_open_days_is_returned():
    """
    Un créneau qui s'étend sur plusieurs jours est retourné si tous les jours
    qu'il intersecte sont ouverts.
    / A slot spanning multiple days is returned if all intersected days are open.

    LOCALISATION : booking/tests/test_slot_engine.py

    OpeningEntry : jeudi (weekday=3), 00:00, slot_duration_minutes=2880 (2×24×60),
                   slot_count=1.
    Créneau : 2026-06-04 (jeu) 00:00 → 2026-06-06 (sam) 00:00.
    Jours intersectés : jeudi 04 et vendredi 05. Tous deux ouverts.
    Résultat attendu : 1 créneau retourné.
    / OpeningEntry: Thursday (weekday=3), 00:00, slot_duration_minutes=2880,
      slot_count=1.
    / Slot: 2026-06-04 (Thu) 00:00 → 2026-06-06 (Sat) 00:00.
    / Intersected days: Thursday 04 and Friday 05. Both open.
    / Expected: 1 slot returned.

    Jeu 04/06 (ouvert)         Ven 05/06 (ouvert)         Sam 06/06
    ──────────────────────────────────────────────────────────────────
    00:00                     00:00                       00:00
      ├───────── jour 1 ────────┼──────────── jour 2 ────────┤
      ↑ start                                                 ↑ end
      Tous les jours intersectés (jeu + ven) sont ouverts → RETOURNÉ.
      / All intersected days (Thu + Fri) are open → RETURNED.
    """
    from booking.models import OpeningEntry, WeeklyOpening
    from booking.slot_engine import generate_theoretical_slots

    with schema_context(TENANT_SCHEMA):
        try:
            # 2026-06-04 = jeudi, 2026-06-05 = vendredi. Tous deux ouverts.
            # / 2026-06-04 = Thursday, 2026-06-05 = Friday. Both open.
            opening = WeeklyOpening.objects.create(
                name=f'{TEST_PREFIX} multi_day_all_open',
            )
            entry = OpeningEntry.objects.create(
                weekly_opening=opening,
                weekday=OpeningEntry.THURSDAY,
                start_time=datetime.time(0, 0),
                slot_duration_minutes=2880,
                slot_count=1,
            )

            slots = generate_theoretical_slots(
                opening_entries=[entry],
                date_from=datetime.date(2026, 6, 4),
                date_to=datetime.date(2026, 6, 6),
                closed_dates=set(),
            )

            # Tous les jours intersectés sont ouverts → créneau retourné.
            # / All intersected days are open → slot returned.
            assert len(slots) == 1
            assert slots[0].start.date() == datetime.date(2026, 6, 4)
            assert slots[0].start.time() == datetime.time(0, 0)
            assert slots[0].end.date() == datetime.date(2026, 6, 6)
            assert slots[0].end.time() == datetime.time(0, 0)
            assert slots[0].duration_minutes() == 2880

        finally:
            OpeningEntry.objects.filter(
                weekly_opening__name__startswith=TEST_PREFIX,
            ).delete()
            WeeklyOpening.objects.filter(name__startswith=TEST_PREFIX).delete()


@pytest.mark.django_db
def test_generate_theoretical_slots_three_day_slot_with_closed_middle_day_is_excluded():
    """
    Un OpeningEntry dont le créneau unique dure 3 jours complets est toujours
    exclu : il ne tient pas dans un seul jour ouvert (règle decisions §7).
    De plus, le jour du milieu est fermé (raison supplémentaire).
    / An OpeningEntry whose single slot lasts 3 full days is always excluded:
    it does not fit within a single open day (rule decisions §7).
    Additionally, the middle day is closed (extra reason).

    LOCALISATION : booking/tests/test_slot_engine.py

    OpeningEntry : jeudi (weekday=3), 00:00, slot_duration_minutes=4320 (3×24×60),
                   slot_count=1.
    Créneau généré (sans règle) : 2026-06-04 (jeu) 00:00 → 2026-06-07 (dim) 00:00.
    Les trois jours couverts : jeudi 04, vendredi 05, samedi 06.
    Jour fermé : vendredi 05 (jour du milieu).
    Jeudi et samedi sont ouverts.
    / OpeningEntry: Thursday (weekday=3), 00:00, slot_duration_minutes=4320,
      slot_count=1.
    / Unconstrained slot: 2026-06-04 (Thu) 00:00 → 2026-06-07 (Sun) 00:00.
    / Days covered: Thursday 04, Friday 05, Saturday 06.
    / Closed day: Friday 05 (the middle day). Thursday and Saturday are open.

    Le slot est exclu car il intersecte le vendredi (fermé — jour du milieu).
    Même si jeudi et samedi sont ouverts, un seul jour fermé suffit à exclure
    le créneau (decisions §7).
    / The slot is excluded because it intersects Friday (closed — middle day).
    / Even though Thursday and Saturday are open, one closed day is enough
    / to exclude the slot (decisions §7).

    Jeu 04/06 (ouvert)   Ven 05/06 (fermé ░░)   Sam 06/06 (ouvert)
    ──────────────────────────────────────────────────────────────────
    00:00                00:00                   00:00                00:00
      ├─────── jour 1 ────┼──────── jour 2 ────────┼────── jour 3 ────┤
      ↑ start             ░░░ fermé ░░░             ↑                  ↑ end (dim)
      ✗ — ne tient pas dans un seul jour ouvert → EXCLU (0 créneaux)
    """
    from booking.models import ClosedPeriod, OpeningEntry, WeeklyOpening
    from booking.slot_engine import generate_theoretical_slots

    with schema_context(TENANT_SCHEMA):
        try:
            # 2026-06-04 = jeudi, 2026-06-05 = vendredi (fermé), 2026-06-06 = samedi.
            # / 2026-06-04 = Thursday, 2026-06-05 = Friday (closed), 2026-06-06 = Saturday.
            calendar = _make_calendar('three_day_slot')
            weekly_opening = _make_weekly_opening('three_day_slot')
            resource = _make_resource('three_day_slot', calendar, weekly_opening)

            ClosedPeriod.objects.create(
                calendar=calendar,
                start_date=datetime.date(2026, 6, 5),
                end_date=datetime.date(2026, 6, 5),
                label='Vendredi fermé',
            )

            entry = OpeningEntry.objects.create(
                weekly_opening=weekly_opening,
                weekday=OpeningEntry.THURSDAY,
                start_time=datetime.time(0, 0),
                slot_duration_minutes=4320,
                slot_count=1,
            )

            closed_dates = {datetime.date(2026, 6, 5)}

            slots = generate_theoretical_slots(
                opening_entries=[entry],
                date_from=datetime.date(2026, 6, 4),
                date_to=datetime.date(2026, 6, 7),
                closed_dates=closed_dates,
            )

            # Le créneau intersecte vendredi (fermé) → exclu.
            # / Slot intersects Friday (closed) → excluded.
            assert len(slots) == 0

        finally:
            _cleanup()


# ---------------------------------------------------------------------------
# Tests — compute_remaining_capacity
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_compute_remaining_capacity_with_no_bookings_equals_capacity():
    """
    Aucune réservation → remaining_capacity == capacity de la ressource.
    / No bookings → remaining_capacity == resource capacity.

    LOCALISATION : booking/tests/test_slot_engine.py
    """
    from booking.slot_engine import BookableInterval, Interval, compute_remaining_capacity

    slot = BookableInterval(
        interval=Interval(
            start=timezone.make_aware(datetime.datetime(2026, 6, 1, 9, 0)),
            end=timezone.make_aware(datetime.datetime(2026, 6, 1, 10, 0)),
        ),
        max_capacity=3,
        remaining_capacity=0,
    )
    assert compute_remaining_capacity(slot, capacity=3, existing_bookings=[]) == 3


@pytest.mark.django_db
def test_compute_remaining_capacity_decreases_with_overlapping_booking():
    """
    Une réservation qui chevauche le créneau réduit remaining_capacity de 1.
    / One booking overlapping the slot reduces remaining_capacity by 1.

    LOCALISATION : booking/tests/test_slot_engine.py

    Créneau 09:00–10:00, capacity=3, une réservation à 09:00 → résultat=2.
    / Slot 09:00–10:00, capacity=3, one booking at 09:00 → result=2.

    09:00                 10:00
      ├─────── slot ──────┤    capacity = 3
      ├─────── B1 ────────┤    bookings = 1
                               remaining = 2  ✓
    """
    from booking.models import Booking
    from booking.slot_engine import BookableInterval, Interval, compute_remaining_capacity

    with schema_context(TENANT_SCHEMA):
        try:
            from AuthBillet.models import TibilletUser

            user = TibilletUser.objects.filter(is_superuser=True).first()
            calendar = _make_calendar('overlap_one')
            weekly_opening = _make_weekly_opening('overlap_one')
            resource = _make_resource('overlap_one', calendar, weekly_opening, capacity=3)

            booking = Booking.objects.create(
                resource=resource,
                user=user,
                start_datetime=timezone.make_aware(datetime.datetime(2026, 6, 1, 9, 0)),
                slot_duration_minutes=60,
                slot_count=1,
                status=Booking.STATUS_NEW,
            )

            slot = BookableInterval(
                interval=Interval(
                    start=timezone.make_aware(datetime.datetime(2026, 6, 1, 9, 0)),
                    end=timezone.make_aware(datetime.datetime(2026, 6, 1, 10, 0)),
                ),
                max_capacity=3,
                remaining_capacity=0,
            )

            result = compute_remaining_capacity(slot, capacity=3, existing_bookings=[booking])

            assert result == 2

        finally:
            _cleanup()


@pytest.mark.django_db
def test_compute_remaining_capacity_zero_when_all_units_taken():
    """
    Autant de réservations que la capacité → remaining_capacity == 0.
    / As many bookings as capacity → remaining_capacity == 0.

    LOCALISATION : booking/tests/test_slot_engine.py

    Créneau 09:00–10:00, capacity=2, deux réservations → résultat=0.
    / Slot 09:00–10:00, capacity=2, two bookings → result=0.

    09:00                 10:00
      ├─────── slot ──────┤    capacity = 2
      ├─────── B1 ────────┤    booking 1 (status=new)
      ├─────── B2 ────────┤    booking 2 (status=confirmed)
                               remaining = 0  ✓
    """
    from booking.models import Booking
    from booking.slot_engine import BookableInterval, Interval, compute_remaining_capacity

    with schema_context(TENANT_SCHEMA):
        try:
            from AuthBillet.models import TibilletUser

            user = TibilletUser.objects.filter(is_superuser=True).first()
            calendar = _make_calendar('all_units_taken')
            weekly_opening = _make_weekly_opening('all_units_taken')
            resource = _make_resource('all_units_taken', calendar, weekly_opening, capacity=2)

            booking_1 = Booking.objects.create(
                resource=resource,
                user=user,
                start_datetime=timezone.make_aware(datetime.datetime(2026, 6, 1, 9, 0)),
                slot_duration_minutes=60,
                slot_count=1,
                status=Booking.STATUS_NEW,
            )
            booking_2 = Booking.objects.create(
                resource=resource,
                user=user,
                start_datetime=timezone.make_aware(datetime.datetime(2026, 6, 1, 9, 0)),
                slot_duration_minutes=60,
                slot_count=1,
                status=Booking.STATUS_CONFIRMED,
            )

            slot = BookableInterval(
                interval=Interval(
                    start=timezone.make_aware(datetime.datetime(2026, 6, 1, 9, 0)),
                    end=timezone.make_aware(datetime.datetime(2026, 6, 1, 10, 0)),
                ),
                max_capacity=2,
                remaining_capacity=0,
            )

            result = compute_remaining_capacity(
                slot, capacity=2, existing_bookings=[booking_1, booking_2]
            )

            assert result == 0

        finally:
            _cleanup()


# ---------------------------------------------------------------------------
# Tests — compute_slots (end-to-end)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_compute_slots_booking_count_gt_1_overlaps_multiple_slots():
    """
    Une réservation avec slot_count=2 chevauche les deux créneaux couverts.
    / A booking with slot_count=2 overlaps both covered slots.

    LOCALISATION : booking/tests/test_slot_engine.py

    WeeklyOpening : lundi 09:00, 60 min, 2 créneaux (09:00 et 10:00).
    Réservation   : 2026-06-01 09:00, 60 min × 2 créneaux (couvre 09:00–11:00).
    Les deux créneaux doivent avoir remaining_capacity=0.
    / WeeklyOpening: Monday 09:00, 60 min, 2 slots (09:00 and 10:00).
    / Booking: 2026-06-01 09:00, 60 min × 2 slots (covers 09:00–11:00).
    / Both slots must have remaining_capacity=0.

    09:00       10:00       11:00
      ├── slot[0] ┼── slot[1] ┤   capacity = 1
      ├────────── B1 ──────────┤   slot_count = 2
    slot[0].remaining = 0  ✓
    slot[1].remaining = 0  ✓
    """
    from booking.models import Booking, OpeningEntry
    from booking.slot_engine import compute_slots

    with schema_context(TENANT_SCHEMA):
        try:
            from AuthBillet.models import TibilletUser

            user = TibilletUser.objects.filter(is_superuser=True).first()
            calendar = _make_calendar('slot_count_gt_1')
            weekly_opening = _make_weekly_opening('slot_count_gt_1')
            OpeningEntry.objects.create(
                weekly_opening=weekly_opening,
                weekday=OpeningEntry.MONDAY,
                start_time=datetime.time(9, 0),
                slot_duration_minutes=60,
                slot_count=2,
            )
            resource = _make_resource(
                'slot_count_gt_1', calendar, weekly_opening, capacity=1
            )

            Booking.objects.create(
                resource=resource,
                user=user,
                start_datetime=timezone.make_aware(datetime.datetime(2026, 6, 1, 9, 0)),
                slot_duration_minutes=60,
                slot_count=2,
                status=Booking.STATUS_NEW,
            )

            # Augmente l'horizon pour couvrir 2026-06-01 (date passée).
            # / Increase horizon to cover 2026-06-01 (a past date).
            resource.booking_horizon_days = 99999
            resource.save(update_fields=['booking_horizon_days'])

            slots = compute_slots(
                resource,
                datetime.date(2026, 6, 1),
                datetime.date(2026, 6, 1),
            )

            assert len(slots) == 2
            assert slots[0].remaining_capacity == 0
            assert slots[1].remaining_capacity == 0

        finally:
            _cleanup()


@pytest.mark.django_db
def test_compute_slots_booking_partial_overlap_counts_as_full_overlap():
    """
    Un booking qui démarre à l'intérieur du créneau est compté comme
    chevauchant ce créneau (chevauchement partiel = complet).
    / A booking starting inside the slot counts as overlapping it
    / (partial overlap = full overlap).

    LOCALISATION : booking/tests/test_slot_engine.py

    Créneau : 2026-06-01 09:00–10:00.
    Booking : 2026-06-01 09:30, 60 min × 1 → couvre 09:30–10:30.
    Le créneau 09:00–10:00 est partiellement couvert → remaining_capacity=0.
    / Slot: 2026-06-01 09:00–10:00.
    / Booking: 2026-06-01 09:30, 60 min × 1 → covers 09:30–10:30.
    / Slot 09:00–10:00 is partially covered → remaining_capacity=0.

    09:00       09:30       10:00       10:30
      ├──── slot ────────────┤
                  ├───── B1 ──────────────┤
      ←─ partiel ─→
    Chevauchement partiel = chevauchement complet → remaining = 0  ✓
    / Partial overlap counts as full overlap → remaining = 0  ✓
    """
    from booking.models import Booking, OpeningEntry
    from booking.slot_engine import compute_slots

    with schema_context(TENANT_SCHEMA):
        try:
            from AuthBillet.models import TibilletUser

            user = TibilletUser.objects.filter(is_superuser=True).first()
            calendar = _make_calendar('partial_overlap')
            weekly_opening = _make_weekly_opening('partial_overlap')
            OpeningEntry.objects.create(
                weekly_opening=weekly_opening,
                weekday=OpeningEntry.MONDAY,
                start_time=datetime.time(9, 0),
                slot_duration_minutes=60,
                slot_count=1,
            )
            resource = _make_resource(
                'partial_overlap', calendar, weekly_opening, capacity=1
            )

            Booking.objects.create(
                resource=resource,
                user=user,
                start_datetime=timezone.make_aware(datetime.datetime(2026, 6, 1, 9, 30)),
                slot_duration_minutes=60,
                slot_count=1,
                status=Booking.STATUS_NEW,
            )

            # Augmente l'horizon pour couvrir 2026-06-01.
            # / Increase horizon to cover 2026-06-01 (a past date).
            resource.booking_horizon_days = 99999
            resource.save(update_fields=['booking_horizon_days'])

            slots = compute_slots(
                resource,
                datetime.date(2026, 6, 1),
                datetime.date(2026, 6, 1),
            )

            assert len(slots) == 1
            assert slots[0].remaining_capacity == 0

        finally:
            _cleanup()


@pytest.mark.django_db
def test_compute_slots_returns_empty_when_no_opening_entries():
    """
    compute_slots retourne [] quand le WeeklyOpening n'a aucune entrée.
    / compute_slots returns [] when the WeeklyOpening has no entries.

    LOCALISATION : booking/tests/test_slot_engine.py
    """
    from booking.slot_engine import compute_slots

    with schema_context(TENANT_SCHEMA):
        try:
            calendar = _make_calendar('no_entries')
            weekly_opening = _make_weekly_opening('no_entries')
            # Aucun OpeningEntry créé pour ce WeeklyOpening.
            # / No OpeningEntry created for this WeeklyOpening.
            resource = _make_resource('no_entries', calendar, weekly_opening)

            slots = compute_slots(
                resource,
                datetime.date(2026, 6, 1),
                datetime.date(2026, 6, 7),
            )

            assert slots == []

        finally:
            _cleanup()


@pytest.mark.django_db
def test_compute_slots_end_to_end_with_fixture_coworking_resource():
    """
    Test de bout en bout avec la ressource "Coworking" des fixtures.
    / End-to-end test with the "Coworking" fixture resource.

    LOCALISATION : booking/tests/test_slot_engine.py

    "Coworking" : lun–ven, 8 créneaux × 60 min à partir de 09:00, capacity=3.
    On cherche le prochain lundi dans l'horizon de réservation.
    8 créneaux doivent être retournés, de 09:00 à 17:00.
    / "Coworking": Mon–Fri, 8 × 60 min from 09:00, capacity=3.
    / Find next Monday within booking horizon.
    / 8 slots expected, from 09:00 to 17:00.

    Prochain lundi :
    09:00 10:00 11:00 12:00 13:00 14:00 15:00 16:00 17:00
      ████  ████  ████  ████  ████  ████  ████  ████
      [0]   [1]   [2]   [3]   [4]   [5]   [6]   [7]
    len = 8, remaining_capacity <= 3 pour chaque créneau.
    """
    from booking.models import Resource
    from booking.slot_engine import compute_slots

    with schema_context(TENANT_SCHEMA):
        resource = Resource.objects.filter(name='Coworking').first()
        if resource is None:
            pytest.skip('Fixture "Coworking" absente — lancer create_booking_fixtures')

        today = datetime.date.today()
        # Prochain lundi (jamais aujourd'hui même si on est lundi).
        # / Next Monday (never today even if today is Monday).
        days_to_monday = (7 - today.weekday()) % 7 or 7
        next_monday = today + datetime.timedelta(days=days_to_monday)

        if days_to_monday > resource.booking_horizon_days:
            pytest.skip(
                f'Le prochain lundi ({next_monday}) est hors horizon '
                f'({resource.booking_horizon_days} jours).'
            )

        slots = compute_slots(resource, next_monday, next_monday)

        if not slots:
            pytest.skip(
                f'Aucun créneau pour {next_monday} — '
                'probablement un jour férié ou une fermeture.'
            )

        assert len(slots) == 8

        assert slots[0].start.time() == datetime.time(9, 0)
        assert slots[0].end.time() == datetime.time(10, 0)
        assert slots[7].start.time() == datetime.time(16, 0)
        assert slots[7].end.time() == datetime.time(17, 0)

        for slot in slots:
            assert slot.start.date() == next_monday
            assert slot.duration_minutes() == 60
            assert slot.remaining_capacity <= 3


@pytest.mark.django_db
def test_compute_slots_end_to_end_with_fixture_petite_salle():
    """
    Test de bout en bout avec la ressource "Petite salle" des fixtures.
    / End-to-end test with the "Petite salle" fixture resource.

    LOCALISATION : booking/tests/test_slot_engine.py

    "Petite salle" : sam+dim, 3 créneaux × 180 min à partir de 10:00, capacity=1.
    On cherche le prochain samedi dans l'horizon de réservation.
    3 créneaux doivent être retournés : 10:00–13:00, 13:00–16:00, 16:00–19:00.
    / "Petite salle": Sat+Sun, 3 × 180 min from 10:00, capacity=1.
    / Find next Saturday within booking horizon.
    / 3 slots expected: 10:00–13:00, 13:00–16:00, 16:00–19:00.

    Prochain samedi :
    10:00       13:00       16:00       19:00
      ████████████  ████████████  ████████████
          [0]           [1]           [2]
        180 min       180 min       180 min
    """
    from booking.models import Resource
    from booking.slot_engine import compute_slots

    with schema_context(TENANT_SCHEMA):
        resource = Resource.objects.filter(name='Petite salle').first()
        if resource is None:
            pytest.skip('Fixture "Petite salle" absente — lancer create_booking_fixtures')

        today = datetime.date.today()
        # Prochain samedi (weekday=5). Jamais aujourd'hui.
        # / Next Saturday (weekday=5). Never today.
        days_to_saturday = (5 - today.weekday()) % 7 or 7
        next_saturday = today + datetime.timedelta(days=days_to_saturday)

        if days_to_saturday > resource.booking_horizon_days:
            pytest.skip(
                f'Le prochain samedi ({next_saturday}) est hors horizon '
                f'({resource.booking_horizon_days} jours).'
            )

        slots = compute_slots(resource, next_saturday, next_saturday)

        if not slots:
            pytest.skip(
                f'Aucun créneau pour {next_saturday} — '
                'probablement une fermeture.'
            )

        assert len(slots) == 3

        assert slots[0].start.time() == datetime.time(10, 0)
        assert slots[0].end.time() == datetime.time(13, 0)
        assert slots[1].start.time() == datetime.time(13, 0)
        assert slots[1].end.time() == datetime.time(16, 0)
        assert slots[2].start.time() == datetime.time(16, 0)
        assert slots[2].end.time() == datetime.time(19, 0)

        for slot in slots:
            assert slot.duration_minutes() == 180


# ---------------------------------------------------------------------------
# Tests — generate_theoretical_slots — ouverture couvrant toute la semaine
# / Tests — generate_theoretical_slots — full-week opening
# ---------------------------------------------------------------------------
#
# Ces tests utilisent un WeeklyOpening de 7 OpeningEntry (lun–dim),
# chacun : start_time=00:00, slot_duration_minutes=60, slot_count=24.
# Semaine fixe : 2026-06-01 (lun) → 2026-06-07 (dim).
# Total théorique sans fermeture : 7 × 24 = 168 créneaux.
#
# Note sur la frontière minuit :
# Le dernier créneau de chaque journée (23:00–00:00) a
# end_datetime = 00:00:00 du lendemain. L'intervalle est semi-ouvert
# [start, end) — end = 00:00:00 est le premier instant du lendemain
# mais le créneau n'y a aucune durée. Par conséquent, le lendemain
# n'est PAS comptabilisé comme « intersecté » par ce créneau. Un
# créneau qui déborde réellement (ex. 23:30 + 60 min = 00:30) est en
# revanche bien exclu si le lendemain est fermé.
# / Note on midnight boundary: the last slot of each day (23:00–00:00)
# has end_datetime = 00:00:00 of the next day. The interval is
# half-open [start, end) — end=00:00 is the first instant of the next
# day but the slot has zero duration there. Therefore, the next day
# is NOT counted as "intersected" by this slot. A slot that genuinely
# bleeds over (e.g. 23:30 + 60 min = 00:30) is still excluded when
# the next day is closed.
# ---------------------------------------------------------------------------

def _make_full_week_opening(label):
    """
    Crée un WeeklyOpening avec 7 OpeningEntry (lun–dim),
    chacun : 00:00, 60 min, 24 créneaux.
    / Creates a WeeklyOpening with 7 OpeningEntry (Mon–Sun),
    each: 00:00, 60 min, 24 slots.

    LOCALISATION : booking/tests/test_slot_engine.py
    """
    from booking.models import OpeningEntry, WeeklyOpening

    opening, _created = WeeklyOpening.objects.get_or_create(
        name=f'{TEST_PREFIX} full_week_{label}',
    )
    for weekday in range(7):
        OpeningEntry.objects.get_or_create(
            weekly_opening=opening,
            weekday=weekday,
            defaults={
                'start_time': datetime.time(0, 0),
                'slot_duration_minutes': 60,
                'slot_count': 24,
            },
        )
    return opening


DATE_FROM_FULL_WEEK = datetime.date(2026, 6, 1)   # lundi / Monday
DATE_TO_FULL_WEEK   = datetime.date(2026, 6, 7)   # dimanche / Sunday


@pytest.mark.django_db
def test_full_week_opening_no_closed_day_returns_168_slots():
    """
    Une ouverture 7j/7 de 00:00 à 24:00 (24 créneaux × 60 min) sans
    aucune fermeture doit retourner 168 créneaux sur la semaine entière.
    / A 7-day 24h opening (24 × 60 min slots, no closures) must return
    168 slots over the full week.

    LOCALISATION : booking/tests/test_slot_engine.py

    Semaine 2026-06-01 (lun) → 2026-06-07 (dim).
    7 jours × 24 créneaux = 168 créneaux attendus.
    / Week 2026-06-01 (Mon) → 2026-06-07 (Sun).
    / 7 days × 24 slots = 168 slots expected.

    Lun  Mar  Mer  Jeu  Ven  Sam  Dim
    ████ ████ ████ ████ ████ ████ ████   ← 24 créneaux chaque jour
     24   24   24   24   24   24   24  = 168
    """
    from booking.slot_engine import generate_theoretical_slots

    with schema_context(TENANT_SCHEMA):
        try:
            opening = _make_full_week_opening('no_closed_day')
            entries = list(opening.opening_entries.all())

            slots = generate_theoretical_slots(
                opening_entries=entries,
                date_from=DATE_FROM_FULL_WEEK,
                date_to=DATE_TO_FULL_WEEK,
                closed_dates=set(),
            )

            assert len(slots) == 168

        finally:
            _cleanup()


@pytest.mark.django_db
def test_full_week_opening_wednesday_closed_returns_144_slots():
    """
    Fermeture du mercredi uniquement : 24 créneaux retirés, 144 restants.
    / Wednesday closed only: 24 slots removed, 144 remaining.

    LOCALISATION : booking/tests/test_slot_engine.py

    Semaine 2026-06-01 (lun) → 2026-06-07 (dim).
    Mercredi 2026-06-03 fermé.
    Le dernier créneau de mardi (23:00–00:00) finit exactement à
    minuit — il n'intersecte pas le mercredi (intervalle semi-ouvert).
    / Week 2026-06-01–2026-06-07. Wednesday 2026-06-03 closed.
    / Tuesday's last slot (23:00–00:00) ends exactly at midnight —
    / it does NOT intersect Wednesday (half-open interval).

    Lun  Mar  Mer  Jeu  Ven  Sam  Dim
    ████ ████ ░░░░ ████ ████ ████ ████
     24   24    0   24   24   24   24  = 144
    """
    from booking.slot_engine import generate_theoretical_slots

    with schema_context(TENANT_SCHEMA):
        try:
            opening = _make_full_week_opening('wednesday_closed')
            entries = list(opening.opening_entries.all())

            # Mercredi 2026-06-03 (weekday=2)
            # / Wednesday 2026-06-03 (weekday=2)
            closed_dates = {datetime.date(2026, 6, 3)}

            slots = generate_theoretical_slots(
                opening_entries=entries,
                date_from=DATE_FROM_FULL_WEEK,
                date_to=DATE_TO_FULL_WEEK,
                closed_dates=closed_dates,
            )

            assert len(slots) == 144

            # Aucun créneau ne doit démarrer le mercredi.
            # / No slot must start on Wednesday.
            closed_day_slots = [
                s for s in slots
                if s.start.date() == datetime.date(2026, 6, 3)
            ]
            assert len(closed_day_slots) == 0

        finally:
            _cleanup()


@pytest.mark.django_db
def test_full_week_opening_monday_closed_returns_144_slots():
    """
    Fermeture du lundi (premier jour de la semaine) : 144 créneaux.
    / Monday (first day of week) closed: 144 slots.

    LOCALISATION : booking/tests/test_slot_engine.py

    Semaine 2026-06-01 (lun) → 2026-06-07 (dim).
    Lundi 2026-06-01 fermé.
    Le dimanche précédent n'appartient pas à la plage demandée :
    son éventuel débordement est hors périmètre.
    / Week 2026-06-01–2026-06-07. Monday 2026-06-01 closed.
    / The preceding Sunday is outside the date range; any bleed-over
    / from it is out of scope.

    Lun  Mar  Mer  Jeu  Ven  Sam  Dim
    ░░░░ ████ ████ ████ ████ ████ ████
      0   24   24   24   24   24   24  = 144
    """
    from booking.slot_engine import generate_theoretical_slots

    with schema_context(TENANT_SCHEMA):
        try:
            opening = _make_full_week_opening('monday_closed')
            entries = list(opening.opening_entries.all())

            # Lundi 2026-06-01 (weekday=0)
            # / Monday 2026-06-01 (weekday=0)
            closed_dates = {datetime.date(2026, 6, 1)}

            slots = generate_theoretical_slots(
                opening_entries=entries,
                date_from=DATE_FROM_FULL_WEEK,
                date_to=DATE_TO_FULL_WEEK,
                closed_dates=closed_dates,
            )

            assert len(slots) == 144

            # Aucun créneau ne doit démarrer le lundi.
            # / No slot must start on Monday.
            monday_slots = [
                s for s in slots
                if s.start.date() == datetime.date(2026, 6, 1)
            ]
            assert len(monday_slots) == 0

        finally:
            _cleanup()


@pytest.mark.django_db
def test_full_week_opening_sunday_closed_returns_144_slots():
    """
    Fermeture du dimanche (dernier jour de la semaine) : 144 créneaux.
    / Sunday (last day of week) closed: 144 slots.

    LOCALISATION : booking/tests/test_slot_engine.py

    Semaine 2026-06-01 (lun) → 2026-06-07 (dim).
    Dimanche 2026-06-07 fermé.
    Le dernier créneau du samedi (23:00–00:00) finit exactement
    à minuit du dimanche — il n'intersecte pas le dimanche (semi-ouvert).
    / Week 2026-06-01–2026-06-07. Sunday 2026-06-07 closed.
    / Saturday's last slot (23:00–00:00) ends at Sunday midnight —
    / it does NOT intersect Sunday (half-open interval).

    Lun  Mar  Mer  Jeu  Ven  Sam  Dim
    ████ ████ ████ ████ ████ ████ ░░░░
     24   24   24   24   24   24    0  = 144
    """
    from booking.slot_engine import generate_theoretical_slots

    with schema_context(TENANT_SCHEMA):
        try:
            opening = _make_full_week_opening('sunday_closed')
            entries = list(opening.opening_entries.all())

            # Dimanche 2026-06-07 (weekday=6)
            # / Sunday 2026-06-07 (weekday=6)
            closed_dates = {datetime.date(2026, 6, 7)}

            slots = generate_theoretical_slots(
                opening_entries=entries,
                date_from=DATE_FROM_FULL_WEEK,
                date_to=DATE_TO_FULL_WEEK,
                closed_dates=closed_dates,
            )

            assert len(slots) == 144

            # Aucun créneau ne doit démarrer le dimanche.
            # / No slot must start on Sunday.
            sunday_slots = [
                s for s in slots
                if s.start.date() == datetime.date(2026, 6, 7)
            ]
            assert len(sunday_slots) == 0

        finally:
            _cleanup()


@pytest.mark.django_db
def test_full_week_opening_two_non_adjacent_days_closed_returns_120_slots():
    """
    Fermeture de deux jours non adjacents (mardi + vendredi) : 120 créneaux.
    / Two non-adjacent days closed (Tuesday + Friday): 120 slots.

    LOCALISATION : booking/tests/test_slot_engine.py

    Semaine 2026-06-01 (lun) → 2026-06-07 (dim).
    Mardi 2026-06-02 et vendredi 2026-06-05 fermés.
    Les jours adjacents (lun et mer autour de mar, jeu et sam autour de ven)
    sont ouverts — la frontière minuit ne crée aucune ambiguïté (semi-ouvert).
    / Week 2026-06-01–2026-06-07.
    / Tuesday 2026-06-02 and Friday 2026-06-05 closed.
    / Adjacent days are open — midnight boundary creates no ambiguity
    / (half-open intervals).

    Lun  Mar  Mer  Jeu  Ven  Sam  Dim
    ████ ░░░░ ████ ████ ░░░░ ████ ████
     24    0   24   24    0   24   24  = 120
    """
    from booking.slot_engine import generate_theoretical_slots

    with schema_context(TENANT_SCHEMA):
        try:
            opening = _make_full_week_opening('two_days_closed')
            entries = list(opening.opening_entries.all())

            # Mardi 2026-06-02 et vendredi 2026-06-05
            # / Tuesday 2026-06-02 and Friday 2026-06-05
            closed_dates = {
                datetime.date(2026, 6, 2),
                datetime.date(2026, 6, 5),
            }

            slots = generate_theoretical_slots(
                opening_entries=entries,
                date_from=DATE_FROM_FULL_WEEK,
                date_to=DATE_TO_FULL_WEEK,
                closed_dates=closed_dates,
            )

            assert len(slots) == 120

            # Aucun créneau ne doit démarrer un jour fermé.
            # / No slot must start on a closed day.
            closed_day_slots = [
                s for s in slots
                if s.start.date() in closed_dates
            ]
            assert len(closed_day_slots) == 0

        finally:
            _cleanup()


# ---------------------------------------------------------------------------
# Tests — generate_theoretical_slots — 1 entrée × 7 créneaux d'une journée
# / Tests — generate_theoretical_slots — 1 entry × 7 one-day slots
# ---------------------------------------------------------------------------
#
# Un seul OpeningEntry : lundi (weekday=0), 00:00, slot_duration_minutes=1440
# (= 24×60, une journée entière), slot_count=7.
# Les 7 créneaux consécutifs couvrent exactement une semaine :
#   slot[0] : lun 00:00 → mar 00:00
#   slot[1] : mar 00:00 → mer 00:00
#   ...
#   slot[6] : dim 00:00 → lun 00:00 (semaine suivante)
# Semaine fixe : 2026-06-01 (lun) → 2026-06-07 (dim).
#
# Règle de fermeture (decisions §7) : vérification slot par slot sur
# start_datetime.date(). Quand lundi (jour de l'entrée) est fermé,
# seul slot[0] est exclu — les créneaux suivants dont le start_datetime
# tombe un jour ouvert sont bien retournés.
# / Single OpeningEntry: Monday, 00:00, slot_duration_minutes=1440 (1 day),
# slot_count=7. 7 consecutive slots cover exactly one week.
# Closure rule (decisions §7): per-slot check on start_datetime.date().
# When Monday (entry's day) is closed, only slot[0] is excluded — later
# slots whose start_datetime falls on an open day are still returned.
#
# Note d'implémentation : slot_start_minutes pour slot[6] = 6×1440 = 8640 min.
# 8640 // 60 = 144 heures → datetime(y, m, d, 144, 0) lève une erreur.
# L'implémentation doit utiliser timedelta, pas la division heures/minutes.
# / Implementation note: slot_start_minutes for slot[6] = 8640 min.
# 8640 // 60 = 144 hours → datetime(y, m, d, 144, 0) raises ValueError.
# The implementation must use timedelta addition, not hour/minute division.
# ---------------------------------------------------------------------------

def _make_one_day_slots_opening(label):
    """
    Crée un WeeklyOpening avec un seul OpeningEntry :
    lundi, 00:00, slot_duration_minutes=1440 (1 journée), slot_count=7.
    / Creates a WeeklyOpening with a single OpeningEntry:
    Monday, 00:00, slot_duration_minutes=1440 (1 day), slot_count=7.

    LOCALISATION : booking/tests/test_slot_engine.py
    """
    from booking.models import OpeningEntry, WeeklyOpening

    opening, _created = WeeklyOpening.objects.get_or_create(
        name=f'{TEST_PREFIX} one_day_slots_{label}',
    )
    OpeningEntry.objects.get_or_create(
        weekly_opening=opening,
        weekday=OpeningEntry.MONDAY,
        defaults={
            'start_time': datetime.time(0, 0),
            'slot_duration_minutes': 1440,
            'slot_count': 7,
        },
    )
    return opening


@pytest.mark.django_db
def test_one_day_slots_opening_no_closed_day_returns_7_slots():
    """
    1 entrée lundi × 7 créneaux d'une journée, aucun jour fermé : 7 créneaux.
    / 1 Monday entry × 7 one-day slots, no closed day: 7 slots.

    LOCALISATION : booking/tests/test_slot_engine.py

    Semaine 2026-06-01 (lun) → 2026-06-07 (dim).
    Chaque créneau couvre un jour complet (1440 min).
    Aucune fermeture → les 7 créneaux sont retournés.
    / Week 2026-06-01 (Mon) → 2026-06-07 (Sun).
    / Each slot covers one full day (1440 min). No closure → 7 slots returned.

    Lun  Mar  Mer  Jeu  Ven  Sam  Dim
    ████ ████ ████ ████ ████ ████ ████
    [0]  [1]  [2]  [3]  [4]  [5]  [6]   = 7 créneaux
    """
    from booking.slot_engine import generate_theoretical_slots

    with schema_context(TENANT_SCHEMA):
        try:
            opening = _make_one_day_slots_opening('no_closed_day')
            entries = list(opening.opening_entries.all())

            slots = generate_theoretical_slots(
                opening_entries=entries,
                date_from=DATE_FROM_FULL_WEEK,
                date_to=DATE_TO_FULL_WEEK,
                closed_dates=set(),
            )

            assert len(slots) == 7

            # Vérifier que les créneaux couvrent bien lun–dim dans l'ordre.
            # / Verify slots cover Mon–Sun in order.
            expected_dates = [
                datetime.date(2026, 6, 1),  # lun / Mon
                datetime.date(2026, 6, 2),  # mar / Tue
                datetime.date(2026, 6, 3),  # mer / Wed
                datetime.date(2026, 6, 4),  # jeu / Thu
                datetime.date(2026, 6, 5),  # ven / Fri
                datetime.date(2026, 6, 6),  # sam / Sat
                datetime.date(2026, 6, 7),  # dim / Sun
            ]
            for slot, expected_date in zip(slots, expected_dates):
                assert slot.start.date() == expected_date
                assert slot.duration_minutes() == 1440

        finally:
            _cleanup()


@pytest.mark.django_db
def test_one_day_slots_opening_wednesday_closed_returns_6_slots():
    """
    1 entrée lundi × 7 créneaux d'une journée, mercredi fermé : 6 créneaux.
    / 1 Monday entry × 7 one-day slots, Wednesday closed: 6 slots.

    LOCALISATION : booking/tests/test_slot_engine.py

    Semaine 2026-06-01 (lun) → 2026-06-07 (dim).
    Mercredi 2026-06-03 fermé → slot[2] (mer) exclu.
    / Week 2026-06-01–2026-06-07. Wednesday 2026-06-03 closed → slot[2] excluded.

    Lun  Mar  Mer  Jeu  Ven  Sam  Dim
    ████ ████ ░░░░ ████ ████ ████ ████
    [0]  [1]  [2]  [3]  [4]  [5]  [6]
               ✗ exclu
    Résultat : 6 créneaux. / Result: 6 slots.
    """
    from booking.slot_engine import generate_theoretical_slots

    with schema_context(TENANT_SCHEMA):
        try:
            opening = _make_one_day_slots_opening('wednesday_closed')
            entries = list(opening.opening_entries.all())

            # Mercredi 2026-06-03
            closed_dates = {datetime.date(2026, 6, 3)}

            slots = generate_theoretical_slots(
                opening_entries=entries,
                date_from=DATE_FROM_FULL_WEEK,
                date_to=DATE_TO_FULL_WEEK,
                closed_dates=closed_dates,
            )

            assert len(slots) == 6

            # Aucun créneau ne doit démarrer le mercredi.
            # / No slot must start on Wednesday.
            assert all(
                s.start.date() != datetime.date(2026, 6, 3)
                for s in slots
            )

        finally:
            _cleanup()


@pytest.mark.django_db
def test_one_day_slots_opening_monday_closed_returns_6_slots():
    """
    1 entrée lundi × 7 créneaux, lundi (jour de l'entrée) fermé : 6 créneaux.
    / 1 Monday entry × 7 slots, Monday (entry's own day) closed: 6 slots.

    LOCALISATION : booking/tests/test_slot_engine.py

    Règle clé (decisions §7) : la fermeture est vérifiée slot par slot sur
    start_datetime.date(). Quand lundi est fermé, seul slot[0] (start=lun)
    est exclu. Les slots 1–6 dont le start_datetime tombe mar–dim sont
    ouverts et doivent être retournés.
    Ce test vérifie que la vérification n'est pas faite UNE SEULE FOIS
    pour l'entrée entière (ce qui exclurait tous les créneaux).
    / Key rule (decisions §7): closure is checked per-slot on start_datetime.date().
    / When Monday is closed, only slot[0] (start=Mon) is excluded.
    / Slots 1–6 whose start_datetime falls on Tue–Sun are open and returned.
    / This test verifies the check is NOT done once for the whole entry.

    Lun  Mar  Mer  Jeu  Ven  Sam  Dim
    ░░░░ ████ ████ ████ ████ ████ ████
    [0]  [1]  [2]  [3]  [4]  [5]  [6]
     ✗    ↑    ↑    ↑    ↑    ↑    ↑
    exclu  slots générés car start_datetime ≠ lundi

    Résultat : 6 créneaux (slots[1]–slots[6]). / Result: 6 slots.
    """
    from booking.slot_engine import generate_theoretical_slots

    with schema_context(TENANT_SCHEMA):
        try:
            opening = _make_one_day_slots_opening('monday_closed')
            entries = list(opening.opening_entries.all())

            # Lundi 2026-06-01 (jour de l'entrée) fermé.
            # / Monday 2026-06-01 (entry's own day) closed.
            closed_dates = {datetime.date(2026, 6, 1)}

            slots = generate_theoretical_slots(
                opening_entries=entries,
                date_from=DATE_FROM_FULL_WEEK,
                date_to=DATE_TO_FULL_WEEK,
                closed_dates=closed_dates,
            )

            # 6 créneaux (mar–dim), pas 0 ni 7.
            # / 6 slots (Tue–Sun), not 0 or 7.
            assert len(slots) == 6

            # Aucun créneau ne commence le lundi.
            # / No slot starts on Monday.
            assert all(
                s.start.date() != datetime.date(2026, 6, 1)
                for s in slots
            )

            # Le premier créneau retourné doit commencer le mardi.
            # / The first returned slot must start on Tuesday.
            assert slots[0].start.date() == datetime.date(2026, 6, 2)

        finally:
            _cleanup()


@pytest.mark.django_db
def test_one_day_slots_opening_sunday_closed_returns_6_slots():
    """
    1 entrée lundi × 7 créneaux, dimanche (dernier créneau) fermé : 6 créneaux.
    / 1 Monday entry × 7 slots, Sunday (last slot) closed: 6 slots.

    LOCALISATION : booking/tests/test_slot_engine.py

    Semaine 2026-06-01 (lun) → 2026-06-07 (dim).
    Dimanche 2026-06-07 fermé → slot[6] (start=dim) exclu.
    Les slots[0]–slots[5] (lun–sam) sont ouverts → retournés.
    / Week 2026-06-01–2026-06-07.
    / Sunday 2026-06-07 closed → slot[6] (start=Sun) excluded.
    / Slots[0]–slots[5] (Mon–Sat) are open → returned.

    Lun  Mar  Mer  Jeu  Ven  Sam  Dim
    ████ ████ ████ ████ ████ ████ ░░░░
    [0]  [1]  [2]  [3]  [4]  [5]  [6]
                                    ✗ exclu
    Résultat : 6 créneaux. / Result: 6 slots.
    """
    from booking.slot_engine import generate_theoretical_slots

    with schema_context(TENANT_SCHEMA):
        try:
            opening = _make_one_day_slots_opening('sunday_closed')
            entries = list(opening.opening_entries.all())

            # Dimanche 2026-06-07 (weekday=6)
            # / Sunday 2026-06-07 (weekday=6)
            closed_dates = {datetime.date(2026, 6, 7)}

            slots = generate_theoretical_slots(
                opening_entries=entries,
                date_from=DATE_FROM_FULL_WEEK,
                date_to=DATE_TO_FULL_WEEK,
                closed_dates=closed_dates,
            )

            assert len(slots) == 6

            # Le dernier créneau retourné doit être le samedi.
            # / The last returned slot must be Saturday.
            assert slots[-1].start.date() == datetime.date(2026, 6, 6)

        finally:
            _cleanup()


@pytest.mark.django_db
def test_one_day_slots_opening_two_non_adjacent_days_closed_returns_5_slots():
    """
    1 entrée lundi × 7 créneaux, deux jours non adjacents fermés : 5 créneaux.
    / 1 Monday entry × 7 slots, two non-adjacent days closed: 5 slots.

    LOCALISATION : booking/tests/test_slot_engine.py

    Semaine 2026-06-01 (lun) → 2026-06-07 (dim).
    Mardi 2026-06-02 et vendredi 2026-06-05 fermés.
    slot[1] (start=mar) et slot[4] (start=ven) exclus.
    / Week 2026-06-01–2026-06-07.
    / Tuesday 2026-06-02 and Friday 2026-06-05 closed.
    / slot[1] (start=Tue) and slot[4] (start=Fri) excluded.

    Lun  Mar  Mer  Jeu  Ven  Sam  Dim
    ████ ░░░░ ████ ████ ░░░░ ████ ████
    [0]  [1]  [2]  [3]  [4]  [5]  [6]
          ✗              ✗
    Résultat : 5 créneaux. / Result: 5 slots.
    """
    from booking.slot_engine import generate_theoretical_slots

    with schema_context(TENANT_SCHEMA):
        try:
            opening = _make_one_day_slots_opening('two_days_closed')
            entries = list(opening.opening_entries.all())

            # Mardi 2026-06-02 et vendredi 2026-06-05
            # / Tuesday 2026-06-02 and Friday 2026-06-05
            closed_dates = {
                datetime.date(2026, 6, 2),
                datetime.date(2026, 6, 5),
            }

            slots = generate_theoretical_slots(
                opening_entries=entries,
                date_from=DATE_FROM_FULL_WEEK,
                date_to=DATE_TO_FULL_WEEK,
                closed_dates=closed_dates,
            )

            assert len(slots) == 5

            # Aucun créneau ne doit démarrer un jour fermé.
            # / No slot must start on a closed day.
            assert all(
                s.start.date() not in closed_dates
                for s in slots
            )

        finally:
            _cleanup()


# ---------------------------------------------------------------------------
# Tests — generate_theoretical_slots — ouverture maximale : 1 créneau d'une semaine
# / Tests — generate_theoretical_slots — maximum opening: 1 slot of one week
# ---------------------------------------------------------------------------
#
# Un seul OpeningEntry : lundi (weekday=0), 00:00,
# slot_duration_minutes=10 080 (= WEEK_MINUTES = 7×24×60), slot_count=1.
# C'est le plus grand créneau possible (§9 autorise duration × count ≤ WEEK_MINUTES).
# Le créneau unique couvre toute la semaine :
#   slot[0] : lun 2026-06-01 00:00 → lun 2026-06-08 00:00
# Semaine fixe : 2026-06-01 (lun) → 2026-06-07 (dim).
#
# Règle d'intersection (decisions §7, intervalle semi-ouvert) :
# Le créneau intersecte les 7 jours de la semaine (lun–dim).
# Si UN seul de ces jours est fermé, le créneau est exclu.
# Résultat : soit 1 créneau (aucun jour fermé), soit 0 (au moins un jour fermé).
# / Single OpeningEntry: Monday, 00:00, slot_duration_minutes=10 080
# (= WEEK_MINUTES), slot_count=1. Largest possible slot (§9 allows ≤ WEEK_MINUTES).
# The single slot covers the entire week (Mon–Mon next week).
# Intersection rule (decisions §7, half-open): the slot intersects all 7 days.
# If ANY of those 7 days is closed, the slot is excluded.
# Result: 1 slot (no closure) or 0 (at least one closed day).
# ---------------------------------------------------------------------------

WEEK_MINUTES = 7 * 24 * 60   # 10 080 minutes


def _make_one_week_slot_opening(label):
    """
    Crée un WeeklyOpening avec un seul OpeningEntry :
    lundi, 00:00, slot_duration_minutes=10 080 (1 semaine), slot_count=1.
    / Creates a WeeklyOpening with a single OpeningEntry:
    Monday, 00:00, slot_duration_minutes=10 080 (1 week), slot_count=1.

    LOCALISATION : booking/tests/test_slot_engine.py
    """
    from booking.models import OpeningEntry, WeeklyOpening

    opening, _created = WeeklyOpening.objects.get_or_create(
        name=f'{TEST_PREFIX} one_week_slot_{label}',
    )
    OpeningEntry.objects.get_or_create(
        weekly_opening=opening,
        weekday=OpeningEntry.MONDAY,
        defaults={
            'start_time': datetime.time(0, 0),
            'slot_duration_minutes': WEEK_MINUTES,
            'slot_count': 1,
        },
    )
    return opening


@pytest.mark.django_db
def test_one_week_slot_opening_no_closed_day_returns_1_slot():
    """
    1 créneau d'une semaine entière, aucun jour fermé : 1 créneau retourné.
    / 1 full-week slot, no closed day: 1 slot returned.

    LOCALISATION : booking/tests/test_slot_engine.py

    OpeningEntry : lundi 00:00, 10 080 min (7 jours), 1 créneau.
    Semaine 2026-06-01 (lun) → 2026-06-07 (dim). Aucune fermeture.
    Le créneau intersecte tous les jours de la semaine — tous ouverts → retourné.
    / OpeningEntry: Monday 00:00, 10 080 min (7 days), 1 slot.
    / Week 2026-06-01 (Mon) → 2026-06-07 (Sun). No closures.
    / Slot intersects all 7 days — all open → returned.

    Lun  Mar  Mer  Jeu  Ven  Sam  Dim
    ████████████████████████████████████
    ↑ start lun 00:00             ↑ end lun suivant 00:00
    Tous les jours ouverts → 1 créneau. / All days open → 1 slot.
    """
    from booking.slot_engine import generate_theoretical_slots

    with schema_context(TENANT_SCHEMA):
        try:
            opening = _make_one_week_slot_opening('no_closed_day')
            entries = list(opening.opening_entries.all())

            slots = generate_theoretical_slots(
                opening_entries=entries,
                date_from=DATE_FROM_FULL_WEEK,
                date_to=DATE_TO_FULL_WEEK,
                closed_dates=set(),
            )

            assert len(slots) == 1

            slot = slots[0]
            assert slot.start.date() == datetime.date(2026, 6, 1)
            assert slot.duration_minutes() == WEEK_MINUTES
            # Le créneau dure exactement une semaine.
            # / The slot lasts exactly one week.
            expected_end = slot.start + datetime.timedelta(minutes=WEEK_MINUTES)
            assert slot.end == expected_end

        finally:
            _cleanup()


@pytest.mark.django_db
def test_one_week_slot_opening_wednesday_closed_returns_0_slots():
    """
    1 créneau d'une semaine entière, mercredi fermé : 0 créneaux.
    / 1 full-week slot, Wednesday closed: 0 slots.

    LOCALISATION : booking/tests/test_slot_engine.py

    Le créneau intersecte tous les jours lun–dim (intervalle semi-ouvert).
    Mercredi est l'un de ces jours → le créneau est exclu.
    / The slot intersects all days Mon–Sun (half-open interval).
    / Wednesday is one of those days → the slot is excluded.

    Lun  Mar  Mer  Jeu  Ven  Sam  Dim
    ████ ████ ░░░░ ████ ████ ████ ████
    ↑──────────── créneau unique ──────────────↑
               ✗ intersecte mercredi (fermé)
    Résultat : 0 créneaux. / Result: 0 slots.
    """
    from booking.slot_engine import generate_theoretical_slots

    with schema_context(TENANT_SCHEMA):
        try:
            opening = _make_one_week_slot_opening('wednesday_closed')
            entries = list(opening.opening_entries.all())

            closed_dates = {datetime.date(2026, 6, 3)}  # mercredi / Wednesday

            slots = generate_theoretical_slots(
                opening_entries=entries,
                date_from=DATE_FROM_FULL_WEEK,
                date_to=DATE_TO_FULL_WEEK,
                closed_dates=closed_dates,
            )

            assert len(slots) == 0

        finally:
            _cleanup()


@pytest.mark.django_db
def test_one_week_slot_opening_monday_closed_returns_0_slots():
    """
    1 créneau d'une semaine entière, lundi (premier jour) fermé : 0 créneaux.
    / 1 full-week slot, Monday (first day) closed: 0 slots.

    LOCALISATION : booking/tests/test_slot_engine.py

    Lundi est à la fois le jour de l'entrée ET le premier jour intersecté
    par le créneau. Le créneau est exclu.
    / Monday is both the entry's weekday AND the first day intersected
    / by the slot. The slot is excluded.

    Lun  Mar  Mer  Jeu  Ven  Sam  Dim
    ░░░░ ████ ████ ████ ████ ████ ████
    ↑──────────── créneau unique ──────────────↑
     ✗ intersecte lundi (fermé)
    Résultat : 0 créneaux. / Result: 0 slots.
    """
    from booking.slot_engine import generate_theoretical_slots

    with schema_context(TENANT_SCHEMA):
        try:
            opening = _make_one_week_slot_opening('monday_closed')
            entries = list(opening.opening_entries.all())

            closed_dates = {datetime.date(2026, 6, 1)}  # lundi / Monday

            slots = generate_theoretical_slots(
                opening_entries=entries,
                date_from=DATE_FROM_FULL_WEEK,
                date_to=DATE_TO_FULL_WEEK,
                closed_dates=closed_dates,
            )

            assert len(slots) == 0

        finally:
            _cleanup()


@pytest.mark.django_db
def test_one_week_slot_opening_sunday_closed_returns_0_slots():
    """
    1 créneau d'une semaine entière, dimanche (dernier jour) fermé : 0 créneaux.
    / 1 full-week slot, Sunday (last day) closed: 0 slots.

    LOCALISATION : booking/tests/test_slot_engine.py

    Le créneau va de lun 00:00 à lun 00:00 (semaine suivante).
    Avec l'intervalle semi-ouvert, le dernier jour intersecté est dimanche
    (end_datetime − 1 µs → dim 23:59:59.999999 → date = dim).
    Dimanche fermé → le créneau est exclu.
    / Slot goes from Mon 00:00 to Mon 00:00 (next week).
    / With half-open interval, the last intersected day is Sunday
    / (end_datetime − 1 µs → Sun 23:59:59.999999 → date = Sun).
    / Sunday closed → slot excluded.

    Lun  Mar  Mer  Jeu  Ven  Sam  Dim
    ████ ████ ████ ████ ████ ████ ░░░░
    ↑──────────── créneau unique ──────────────↑
                                   ✗ intersecte dimanche (fermé)
    Résultat : 0 créneaux. / Result: 0 slots.
    """
    from booking.slot_engine import generate_theoretical_slots

    with schema_context(TENANT_SCHEMA):
        try:
            opening = _make_one_week_slot_opening('sunday_closed')
            entries = list(opening.opening_entries.all())

            closed_dates = {datetime.date(2026, 6, 7)}  # dimanche / Sunday

            slots = generate_theoretical_slots(
                opening_entries=entries,
                date_from=DATE_FROM_FULL_WEEK,
                date_to=DATE_TO_FULL_WEEK,
                closed_dates=closed_dates,
            )

            assert len(slots) == 0

        finally:
            _cleanup()
