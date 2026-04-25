"""
Tests du moteur de réservation.
/ Tests for the booking engine.

LOCALISATION : booking/tests/test_booking_engine.py

Deux catégories de tests (§10) :

- Tests unitaires : fonctions pures sans accès DB.
  Pas de @pytest.mark.django_db ni de schema_context.
  Données construites avec des objets légers (SimpleNamespace) et
  des helpers purs (_cp, _oe, _bk, _aware).
  Fonctions couvertes : compute_open_intervals, generate_theoretical_slots,
  compute_remaining_capacity.

- Tests d'intégration : accès DB via schema_context('lespass').
  Fonctions couvertes : compute_slots, validate_new_booking.

/ Two test categories (§10):
/ - Unit tests: pure functions, no DB. Lightweight objects.
/ - Integration tests: DB via schema_context. Full stack.

Lancement / Run:
    docker exec lespass_django poetry run pytest \
        booking/tests/test_booking_engine.py -v
"""
import datetime
import types
import zoneinfo

import pytest
from django.utils import timezone
from django_tenants.utils import schema_context

from booking.booking_engine import Interval

TEST_PREFIX   = '[test_booking_engine]'
TENANT_SCHEMA = 'lespass'

# Fuseau horaire Europe/Paris passé explicitement aux fonctions pures.
# / Europe/Paris timezone passed explicitly to pure functions.
PARIS_TZ = zoneinfo.ZoneInfo('Europe/Paris')

# Dates fixes pour les tests validate_new_booking (finding §13).
# REFERENCE_NOW = 2026-06-01 00:00 CEST → horizon 28j → jusqu'au 2026-06-29.
# / Fixed datetimes for validate_new_booking tests (finding §13).
MONDAY_NEAR = datetime.date(2026, 6, 8)    # +7j  — dans l'horizon 28j
MONDAY_FAR  = datetime.date(2026, 6, 15)   # +14j — hors horizon 7j

# Semaine fixe pour les tests full-week / one-day-slots / one-week-slot.
# / Fixed week for full-week / one-day-slots / one-week-slot tests.
DATE_FROM_FULL_WEEK = timezone.make_aware(datetime.datetime(2026, 6, 1), PARIS_TZ)  # lundi / Monday midnight
DATE_TO_FULL_WEEK   = timezone.make_aware(datetime.datetime(2026, 6, 8), PARIS_TZ)  # lundi suivant, exclu / next Monday, exclusive
WINDOW_FULL_WEEK    = Interval(start=DATE_FROM_FULL_WEEK, end=DATE_TO_FULL_WEEK)

WEEK_MINUTES = 7 * 24 * 60   # 10 080 minutes


# ---------------------------------------------------------------------------
# Helpers — DB  (tests d'intégration)
# ---------------------------------------------------------------------------

def _make_resource(name, calendar, weekly_opening, capacity=1, horizon=28):
    from booking.models import Resource

    resource, _created = Resource.objects.get_or_create(
        name=f'{TEST_PREFIX} {name}',
        defaults={
            'calendar':             calendar,
            'weekly_opening':       weekly_opening,
            'capacity':             capacity,
            'booking_horizon_days': horizon,
        },
    )
    return resource


def _make_calendar(label):
    from booking.models import Calendar

    calendar, _created = Calendar.objects.get_or_create(
        name=f'{TEST_PREFIX} {label}',
    )
    return calendar


def _make_weekly_opening(label):
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
    OpeningEntry.objects.filter(
        weekly_opening__name__startswith=TEST_PREFIX
    ).delete()
    WeeklyOpening.objects.filter(name__startswith=TEST_PREFIX).delete()
    ClosedPeriod.objects.filter(
        calendar__name__startswith=TEST_PREFIX
    ).delete()
    Calendar.objects.filter(name__startswith=TEST_PREFIX).delete()


def _add_opening_entry(weekly_opening, weekday, start_time,
                       slot_duration_minutes=60, slot_count=1):
    from booking.models import OpeningEntry

    return OpeningEntry.objects.create(
        weekly_opening=weekly_opening,
        weekday=weekday,
        start_time=start_time,
        slot_duration_minutes=slot_duration_minutes,
        slot_count=slot_count,
    )


def _get_test_user():
    from AuthBillet.models import TibilletUser

    user = (
        TibilletUser.objects.filter(is_superuser=True).first()
        or TibilletUser.objects.filter(is_active=True).first()
    )
    if user is None:
        raise RuntimeError('Aucun utilisateur trouvé dans le tenant lespass.')
    return user


def _make_aware_dt(date, time):
    """Crée un datetime timezone-aware avec le fuseau courant du tenant."""
    tz = timezone.get_current_timezone()
    return timezone.make_aware(datetime.datetime.combine(date, time), tz)


def _add_closed_period(calendar, start_date, end_date=None, label='Fermeture'):
    from booking.models import ClosedPeriod

    return ClosedPeriod.objects.create(
        calendar=calendar,
        start_date=start_date,
        end_date=end_date,
        label=label,
    )


def _add_booking(resource, user, start_datetime,
                 slot_duration_minutes=60, slot_count=1):
    from booking.models import Booking

    return Booking.objects.create(
        resource=resource,
        user=user,
        start_datetime=start_datetime,
        slot_duration_minutes=slot_duration_minutes,
        slot_count=slot_count,
        status='confirmed',
    )


# ---------------------------------------------------------------------------
# Helpers — objets légers pour tests unitaires (§10)
# Lightweight object helpers for pure unit tests
# ---------------------------------------------------------------------------

def _cp(start_date, end_date=None):
    """
    Crée un objet ClosedPeriod léger (SimpleNamespace) pour les tests unitaires.
    Expose uniquement .start_date et .end_date comme le modèle ClosedPeriod.
    / Creates a lightweight ClosedPeriod-like object (SimpleNamespace) for unit tests.
    """
    return types.SimpleNamespace(start_date=start_date, end_date=end_date)


def _oe(weekday, start_time, slot_duration_minutes, slot_count):
    """
    Crée un objet OpeningEntry léger (SimpleNamespace) pour les tests unitaires.
    / Creates a lightweight OpeningEntry-like object (SimpleNamespace) for unit tests.
    """
    return types.SimpleNamespace(
        weekday=weekday,
        start_time=start_time,
        slot_duration_minutes=slot_duration_minutes,
        slot_count=slot_count,
    )


def _bk(start_datetime, slot_duration_minutes=60, slot_count=1):
    """
    Crée un objet Booking léger (SimpleNamespace) pour les tests unitaires de
    compute_remaining_capacity.
    / Creates a lightweight Booking-like object for compute_remaining_capacity tests.
    """
    return types.SimpleNamespace(
        start_datetime=start_datetime,
        slot_duration_minutes=slot_duration_minutes,
        slot_count=slot_count,
    )


def _aware(year, month, day, hour=0, minute=0):
    """
    Crée un datetime timezone-aware Europe/Paris.
    Utilisé dans les assertions des tests unitaires purs.
    / Creates a Europe/Paris timezone-aware datetime.
    / Used in assertions of pure unit tests.
    """
    return timezone.make_aware(
        datetime.datetime(year, month, day, hour, minute),
        PARIS_TZ,
    )


# Datetime de référence pour les tests validate_new_booking (finding §13).
# Défini après _aware pour pouvoir l'utiliser.
# / Reference datetime for validate_new_booking tests (finding §13).
# Defined after _aware so it can use it.
REFERENCE_NOW = _aware(2026, 6, 1)


# ---------------------------------------------------------------------------
# Tests — compute_open_intervals  (unitaires / §10)
# open-day :: Date → Date → Timezone → [ClosedPeriod] → [Interval]
#
# compute_open_intervals retourne O = complément des ClosedPeriods fusionnées
# dans la fenêtre [date_from, date_to) — les deux sont des datetime tz-aware.
# / compute_open_intervals returns O = complement of merged ClosedPeriods
# / within window [date_from, date_to) — both are tz-aware datetimes.
# ---------------------------------------------------------------------------

def test_compute_open_intervals_returns_complement_of_closed_period():
    """
    ClosedPeriod Jun 10–12 (3 jours) → O = deux intervalles ouverts.
    / ClosedPeriod Jun 10–12 (3 days) → O = two open intervals.

    LOCALISATION : booking/tests/test_booking_engine.py

    Fermé [Jun 10, Jun 13) → O = [Jun 01, Jun 10) ∪ [Jun 13, Jul 01).

    Juin 2026 :
     01 … 09  10  11  12  13 … 30
               ░░  ░░  ░░
    O : ←──────┘            └─────→
    """
    from booking.booking_engine import compute_open_intervals

    O = compute_open_intervals(
        closed_periods=[_cp(datetime.date(2026, 6, 10), datetime.date(2026, 6, 12))],
        window=Interval(_aware(2026, 6, 1), _aware(2026, 7, 1)),
    )

    assert O == [
        Interval(_aware(2026, 6, 1),  _aware(2026, 6, 10)),
        Interval(_aware(2026, 6, 13), _aware(2026, 7, 1)),
    ]


def test_compute_open_intervals_handles_single_day_period():
    """
    ClosedPeriod d'un seul jour → O = deux intervalles de part et d'autre.
    / Single-day ClosedPeriod → O = two intervals on each side.

    LOCALISATION : booking/tests/test_booking_engine.py

    Fermé [Jun 15, Jun 16) → O = [Jun 01, Jun 15) ∪ [Jun 16, Jul 01).
    """
    from booking.booking_engine import compute_open_intervals

    O = compute_open_intervals(
        closed_periods=[_cp(datetime.date(2026, 6, 15), datetime.date(2026, 6, 15))],
        window=Interval(_aware(2026, 6, 1), _aware(2026, 7, 1)),
    )

    assert O == [
        Interval(_aware(2026, 6, 1),  _aware(2026, 6, 15)),
        Interval(_aware(2026, 6, 16), _aware(2026, 7, 1)),
    ]


def test_compute_open_intervals_handles_null_end_date():
    """
    end_date=None → la fermeture s'étend jusqu'à date_to → O = un seul intervalle.
    / end_date=None → closure extends to date_to → O = single interval.

    LOCALISATION : booking/tests/test_booking_engine.py

    Fermeture depuis Jun 20 sans fin, fenêtre Jun 18–25.
    O = [Jun 18 00:00, Jun 20 00:00) seulement.

    Fenêtre 18–25 :
     18  19  20  21  22  23  24  25
      ·   ·  ░░  ░░  ░░  ░░  ░░  ░░
         O   └── fermeture jusqu'à date_to ──
    """
    from booking.booking_engine import compute_open_intervals

    O = compute_open_intervals(
        closed_periods=[_cp(datetime.date(2026, 6, 20), None)],
        window=Interval(_aware(2026, 6, 18), _aware(2026, 6, 26)),
    )

    assert O == [
        Interval(_aware(2026, 6, 18), _aware(2026, 6, 20)),
    ]


def test_compute_open_intervals_merges_overlapping_periods():
    """
    Deux ClosedPeriods qui se chevauchent sont fusionnées : O a deux intervalles.
    / Two overlapping ClosedPeriods are merged: O has two open intervals.

    LOCALISATION : booking/tests/test_booking_engine.py

    Période A Jun 10–15 + Période B Jun 13–18 → fermé fusionné [Jun 10, Jun 19).
    O = [Jun 01, Jun 10) ∪ [Jun 19, Jul 01).

     10  11  12  13  14  15  16  17  18
    ░░░A░░░░░░░░░░░░░░░
                  ░░░░░░░B░░░░░░░░░░░░░
    → fusion → [Jun 10, Jun 19)
    """
    from booking.booking_engine import compute_open_intervals

    O = compute_open_intervals(
        closed_periods=[
            _cp(datetime.date(2026, 6, 10), datetime.date(2026, 6, 15)),
            _cp(datetime.date(2026, 6, 13), datetime.date(2026, 6, 18)),
        ],
        window=Interval(_aware(2026, 6, 1), _aware(2026, 7, 1)),
    )

    assert O == [
        Interval(_aware(2026, 6, 1),  _aware(2026, 6, 10)),
        Interval(_aware(2026, 6, 19), _aware(2026, 7, 1)),
    ]


# ---------------------------------------------------------------------------
# Tests — generate_theoretical_slots  (unitaires / §10)
# theoretical-slots :: [OpeningEntry] → [Interval] → [Interval]
#
# Règle W (spec §3.2.2) : w ∈ W ⟺ ∃ o ∈ O, w ⊆ o
# Un créneau est retourné si et seulement s'il est entièrement contenu
# dans l'un des intervalles ouverts de O.
# / Rule W (spec §3.2.2): w ∈ W ⟺ ∃ o ∈ O, w ⊆ o
# / A slot is returned iff it is entirely contained in one open interval of O.
#
# Chaîne de chaque test : _cp → compute_open_intervals → O →
#                         _oe → generate_theoretical_slots → W → assertions.
# / Each test chain: _cp → compute_open_intervals → O →
# /                  _oe → generate_theoretical_slots → W → assertions.
# ---------------------------------------------------------------------------

def test_generate_theoretical_slots_from_weekday_template():
    """
    OpeningEntry lundi 09:00, 60 min, 2 créneaux → 2 créneaux retournés.
    / OpeningEntry Monday 09:00, 60 min, 2 slots → 2 slots returned.

    LOCALISATION : booking/tests/test_booking_engine.py

    2026-06-01 est un lundi. Europe/Paris en juin = CEST = +02:00.
    O = [Jun 01 00:00 +02:00, Jun 02 00:00 +02:00).
    slot[0] = [09:00, 10:00) ⊆ O → retourné.
    slot[1] = [10:00, 11:00) ⊆ O → retourné.
    / 2026-06-01 is Monday. Europe/Paris in June = CEST = +02:00.

    08:00  09:00  10:00  11:00
             ████   ████
          slot[0] slot[1]
    """
    from booking.booking_engine import compute_open_intervals, generate_theoretical_slots

    window  = Interval(_aware(2026, 6, 1), _aware(2026, 6, 2))
    O       = compute_open_intervals([], window)
    entries = [_oe(0, datetime.time(9, 0), 60, 2)]   # MONDAY 09:00, 60 min, 2 slots

    W = generate_theoretical_slots(entries, O, window)

    assert len(W) == 2
    assert W[0].start == _aware(2026, 6, 1, 9, 0)
    assert W[0].end   == _aware(2026, 6, 1, 10, 0)
    assert W[1].start == _aware(2026, 6, 1, 10, 0)
    assert W[1].end   == _aware(2026, 6, 1, 11, 0)
    assert W[0].start.tzinfo is not None


def test_generate_theoretical_slots_excludes_closed_dates():
    """
    Deux lundis dans la fenêtre ; Jun 01 fermé → seul Jun 08 retourné.
    / Two Mondays in window; Jun 01 closed → only Jun 08 returned.

    LOCALISATION : booking/tests/test_booking_engine.py

    O = [Jun 02 00:00, Jun 09 00:00) (Jun 01 fermé).
    slot Jun 01 09:00–10:00 : start=Jun 01 < O.start=Jun 02 → slot ⊄ O → exclu.
    slot Jun 08 09:00–10:00 : ⊆ O → retourné.

    Lun 01 Jun    Lun 08 Jun
      ░░░░          ████
      ✗ ⊄ O         ↑ ⊆ O
    """
    from booking.booking_engine import compute_open_intervals, generate_theoretical_slots

    window = Interval(_aware(2026, 6, 1), _aware(2026, 6, 9))
    O = compute_open_intervals(
        [_cp(datetime.date(2026, 6, 1), datetime.date(2026, 6, 1))],
        window,
    )
    entries = [_oe(0, datetime.time(9, 0), 60, 1)]   # MONDAY

    W = generate_theoretical_slots(entries, O, window)

    assert len(W) == 1
    assert W[0].start.date() == datetime.date(2026, 6, 8)


def test_generate_theoretical_slots_respects_date_to_boundary():
    """
    Fenêtre Jun 01–07 : un seul lundi (Jun 01). Jun 08 hors fenêtre → exclu.
    / Window Jun 01–07: one Monday (Jun 01). Jun 08 outside window → excluded.

    LOCALISATION : booking/tests/test_booking_engine.py

    Lun 01  Mar 02 … Dim 07 | Lun 08 (hors fenêtre)
      ████    ·        ·    |   ✗
      ↑ retourné
    """
    from booking.booking_engine import compute_open_intervals, generate_theoretical_slots

    window = Interval(_aware(2026, 6, 1), _aware(2026, 6, 8))
    O = compute_open_intervals([], window)
    entries = [_oe(0, datetime.time(9, 0), 60, 1)]   # MONDAY

    W = generate_theoretical_slots(entries, O, window)

    assert len(W) == 1
    assert W[0].start.date() == datetime.date(2026, 6, 1)


def test_generate_theoretical_slots_start_on_closed_day_bleed_into_open_day_is_excluded():
    """
    Créneau lun 23:30–mar 00:30 ; lundi fermé → O = [Mar 00:00, …).
    slot.start = lun 23:30 < O.start = mar 00:00 → slot ⊄ O → exclu.
    / Slot Mon 23:30–Tue 00:30; Monday closed → O = [Tue 00:00, …).
    / slot.start = Mon 23:30 < O.start → slot ⊄ O → excluded.

    LOCALISATION : booking/tests/test_booking_engine.py

    Lun 01/06 (fermé ░░)        Mar 02/06 (ouvert)
    22:00  23:00  23:30  00:00  00:30
                   ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓
                   ✗ slot.start < O.start → ⊄ O
    Résultat : 0 créneaux.
    """
    from booking.booking_engine import compute_open_intervals, generate_theoretical_slots

    window = Interval(_aware(2026, 6, 1), _aware(2026, 6, 3))
    O = compute_open_intervals(
        [_cp(datetime.date(2026, 6, 1), datetime.date(2026, 6, 1))],
        window,
    )
    entries = [_oe(0, datetime.time(23, 30), 60, 1)]   # MONDAY 23:30

    W = generate_theoretical_slots(entries, O, window)

    assert len(W) == 0


def test_generate_theoretical_slots_last_slot_bleeds_onto_open_day_is_returned():
    """
    OpeningEntry lun 22:00, 120 min, slot_count=2 ; lundi fermé.
    O = [Mar 00:00, Mer 00:00).
    slot[0] lun 22:00–mar 00:00 : slot.start < O.start → ⊄ O → exclu.
    slot[1] mar 00:00–mar 02:00 : ⊆ O → retourné.
    / OpeningEntry Mon 22:00, 120 min, slot_count=2; Monday closed.
    / O = [Tue 00:00, Wed 00:00).
    / slot[0] Mon 22:00–Tue 00:00: slot.start < O.start → ⊄ O → excluded.
    / slot[1] Tue 00:00–Tue 02:00: ⊆ O → returned.

    LOCALISATION : booking/tests/test_booking_engine.py

    Lun 01/06 (fermé ░░)         Mar 02/06 (ouvert)
    22:00       00:00       02:00
      ├── [0] ──┤── [1] ──┤
      ✗ ⊄ O     ↑ ⊆ O, retourné
    """
    from booking.booking_engine import compute_open_intervals, generate_theoretical_slots

    window = Interval(_aware(2026, 6, 1), _aware(2026, 6, 3))
    O = compute_open_intervals(
        [_cp(datetime.date(2026, 6, 1), datetime.date(2026, 6, 1))],
        window,
    )
    entries = [_oe(0, datetime.time(22, 0), 120, 2)]   # MONDAY 22:00, 120 min, 2 slots

    W = generate_theoretical_slots(entries, O, window)

    assert len(W) == 1
    assert W[0].start == _aware(2026, 6, 2, 0, 0)
    assert W[0].end   == _aware(2026, 6, 2, 2, 0)


def test_generate_theoretical_slots_multi_day_spanning_entry():
    """
    OpeningEntry lun 08:00, 720 min, slot_count=3 ; mardi fermé.
    O = [Jun 01 00:00, Jun 02 00:00).
    slot[0] Jun 01 08:00–20:00 : ⊆ O → retourné.
    slot[1] Jun 01 20:00–Jun 02 08:00 : end > O.end → ⊄ O → exclu.
    slot[2] Jun 02 08:00–20:00 : start > O.end → ⊄ O → exclu.
    / OpeningEntry Mon 08:00, 720 min, slot_count=3; Tuesday closed.
    / O = [Jun 01 00:00, Jun 02 00:00).
    / slot[0]: ⊆ O → returned. slot[1]: bleeds into closed Tue → excluded.
    / slot[2]: starts on closed Tue → excluded.

    LOCALISATION : booking/tests/test_booking_engine.py

    Lun 01/06 (ouvert)              Mar 02/06 (fermé ░░)
    08:00  20:00  00:00  08:00  20:00
      [0]    [1]          [2]
      ↑      ✗ end>O.end   ✗ start>O.end
    """
    from booking.booking_engine import compute_open_intervals, generate_theoretical_slots

    window = Interval(_aware(2026, 6, 1), _aware(2026, 6, 3))
    O = compute_open_intervals(
        [_cp(datetime.date(2026, 6, 2), datetime.date(2026, 6, 2))],
        window,
    )
    entries = [_oe(0, datetime.time(8, 0), 720, 3)]   # MONDAY 08:00, 720 min, 3 slots

    W = generate_theoretical_slots(entries, O, window)

    assert len(W) == 1
    assert W[0].start == _aware(2026, 6, 1, 8, 0)
    assert W[0].end   == _aware(2026, 6, 1, 20, 0)


def test_generate_theoretical_slots_bleed_into_closed_day_start_date_is_open():
    """
    Créneau dim 23:30–lun 00:30 ; lundi fermé → O = [Jun 07, Jun 08).
    slot.end = lun 00:30 > O.end = lun 00:00 → slot ⊄ O → exclu.
    / Slot Sun 23:30–Mon 00:30; Monday closed → O = [Jun 07, Jun 08).
    / slot.end = Mon 00:30 > O.end = Mon 00:00 → slot ⊄ O → excluded.

    LOCALISATION : booking/tests/test_booking_engine.py

    Dim 07/06 (ouvert)           Lun 08/06 (fermé ░░)
    22:00  23:30  00:00  00:30
                   ████████████
                   ↑ start       ↑ end > O.end → ⊄ O
    Résultat : 0 créneaux.
    """
    from booking.booking_engine import compute_open_intervals, generate_theoretical_slots

    window = Interval(_aware(2026, 6, 7), _aware(2026, 6, 9))
    O = compute_open_intervals(
        [_cp(datetime.date(2026, 6, 8), datetime.date(2026, 6, 8))],
        window,
    )
    entries = [_oe(6, datetime.time(23, 30), 60, 1)]   # SUNDAY 23:30

    W = generate_theoretical_slots(entries, O, window)

    assert len(W) == 0


def test_generate_theoretical_slots_multi_day_slot_all_open_days_is_returned():
    """
    Créneau jeu 00:00–sam 00:00 (2880 min) ; jeu et ven ouverts → retourné.
    O = [Jun 04 00:00, Jun 07 00:00). slot ⊆ O → retourné.
    / Slot Thu 00:00–Sat 00:00 (2880 min); Thu and Fri open → returned.
    / O = [Jun 04 00:00, Jun 07 00:00). slot ⊆ O → returned.

    LOCALISATION : booking/tests/test_booking_engine.py

    Jeu 04/06 (ouvert)    Ven 05/06 (ouvert)    Sam 06/06
    00:00                 00:00                  00:00
      ├──────────── 2880 min (48h) ──────────────────┤
      ↑ start                                         ↑ end = O.end
    ⊆ O → retourné
    """
    from booking.booking_engine import compute_open_intervals, generate_theoretical_slots

    window = Interval(_aware(2026, 6, 4), _aware(2026, 6, 7))
    O = compute_open_intervals([], window)
    entries = [_oe(3, datetime.time(0, 0), 2880, 1)]   # THURSDAY 00:00, 2880 min, 1 slot

    W = generate_theoretical_slots(entries, O, window)

    assert len(W) == 1
    assert W[0].start == _aware(2026, 6, 4, 0, 0)
    assert W[0].end   == _aware(2026, 6, 6, 0, 0)
    assert W[0].duration_minutes() == 2880


def test_generate_theoretical_slots_three_day_slot_with_closed_middle_day_is_excluded():
    """
    Créneau jeu 00:00–dim 00:00 (4320 min) ; vendredi fermé.
    O = [Jun 04, Jun 05) ∪ [Jun 06, Jun 08).
    slot ⊄ O[0] (end=Jun 07>Jun 05) et ⊄ O[1] (start=Jun 04<Jun 06) → exclu.
    / Slot Thu 00:00–Sun 00:00 (4320 min); Friday closed.
    / O = [Jun 04, Jun 05) ∪ [Jun 06, Jun 08).
    / slot ⊄ any o ∈ O → excluded.

    LOCALISATION : booking/tests/test_booking_engine.py

    Jeu 04  Ven 05 (░░)  Sam 06  Dim 07
      ├────────── 3 jours ──────────────┤
                ✗ ven fermé → O scindé → ⊄ tout o
    Résultat : 0 créneaux.
    """
    from booking.booking_engine import compute_open_intervals, generate_theoretical_slots

    window = Interval(_aware(2026, 6, 4), _aware(2026, 6, 8))
    O = compute_open_intervals(
        [_cp(datetime.date(2026, 6, 5), datetime.date(2026, 6, 5))],
        window,
    )
    entries = [_oe(3, datetime.time(0, 0), 4320, 1)]   # THURSDAY 00:00, 4320 min, 1 slot

    W = generate_theoretical_slots(entries, O, window)

    assert len(W) == 0



# ---------------------------------------------------------------------------
# Tests — compute_remaining_capacity  (unitaires / §10)
# bookable-intervals :: BookableInterval → Int → [Booking] → Int
#
# Chaque test suit la chaîne O → W → compute_remaining_capacity(slot, cap, B)
# pour reproduire le contexte exact de la spec §3.2.3.
# Les réservations sont des objets légers (_bk) sans accès DB.
# / Each test follows the O → W → compute_remaining_capacity chain.
# / Bookings are lightweight objects (_bk), no DB access.
# ---------------------------------------------------------------------------

def test_compute_remaining_capacity_with_no_bookings_equals_capacity():
    """
    Aucune réservation → remaining_capacity == capacity.
    / No bookings → remaining_capacity == capacity.

    LOCALISATION : booking/tests/test_booking_engine.py

    O = [Jun 01 00:00, Jun 02 00:00). W = [09:00–10:00]. capacity=3. B=[].
    E = [BookableInterval 09:00–10:00, max=3, remaining=3].

    09:00           10:00
      ├──── slot ───┤   capacity = 3, bookings = 0
                        remaining = 3  ✓
    """
    from booking.booking_engine import (
        compute_open_intervals, compute_remaining_capacity,
        generate_theoretical_slots,
    )

    window = Interval(_aware(2026, 6, 1), _aware(2026, 6, 2))
    O = compute_open_intervals([], window)
    W = generate_theoretical_slots([_oe(0, datetime.time(9, 0), 60, 1)], O, window)
    assert len(W) == 1

    assert compute_remaining_capacity(W[0], capacity=3, existing_bookings=[]) == 3


def test_compute_remaining_capacity_decreases_with_overlapping_booking():
    """
    Une réservation chevauchant le créneau réduit remaining de 1.
    / One booking overlapping the slot reduces remaining by 1.

    LOCALISATION : booking/tests/test_booking_engine.py

    O = [Jun 01 00:00, Jun 02 00:00). W = [09:00–10:00]. capacity=3.
    b1 = Booking 09:00–10:00, status=confirmed → remaining = 2.

    09:00           10:00
      ├──── slot ───┤   capacity = 3
      ├──── b1 ─────┤   bookings = 1
                        remaining = 2  ✓
    """
    from booking.booking_engine import (
        compute_open_intervals, compute_remaining_capacity,
        generate_theoretical_slots,
    )

    window = Interval(_aware(2026, 6, 1), _aware(2026, 6, 2))
    O = compute_open_intervals([], window)
    W = generate_theoretical_slots([_oe(0, datetime.time(9, 0), 60, 1)], O, window)

    b1 = _bk(_aware(2026, 6, 1, 9, 0), slot_duration_minutes=60, slot_count=1)

    assert compute_remaining_capacity(W[0], capacity=3, existing_bookings=[b1]) == 2


def test_compute_remaining_capacity_zero_when_all_units_taken():
    """
    Autant de réservations que la capacité → remaining_capacity == 0.
    / As many bookings as capacity → remaining_capacity == 0.

    LOCALISATION : booking/tests/test_booking_engine.py

    capacity=2, deux réservations sur le même créneau → remaining = 0.

    09:00           10:00
      ├──── slot ───┤   capacity = 2
      ├──── b1 ─────┤   status=new
      ├──── b2 ─────┤   status=confirmed
                        remaining = 0  ✓
    """
    from booking.booking_engine import (
        compute_open_intervals, compute_remaining_capacity,
        generate_theoretical_slots,
    )

    window = Interval(_aware(2026, 6, 1), _aware(2026, 6, 2))
    O = compute_open_intervals([], window)
    W = generate_theoretical_slots([_oe(0, datetime.time(9, 0), 60, 1)], O, window)

    b1 = _bk(_aware(2026, 6, 1, 9, 0), 60, 1)
    b2 = _bk(_aware(2026, 6, 1, 9, 0), 60, 1)

    assert compute_remaining_capacity(W[0], capacity=2, existing_bookings=[b1, b2]) == 0


# ---------------------------------------------------------------------------
# Tests — compute_slots end-to-end  (intégration)
# Utilise la pile complète : Resource DB → WeeklyOpening → Calendar → Booking.
# / Full-stack integration tests: Resource DB → WeeklyOpening → Calendar → Booking.
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_compute_slots_booking_count_gt_1_overlaps_multiple_slots():
    """
    Une réservation slot_count=2 chevauche les deux créneaux couverts.
    / A booking with slot_count=2 overlaps both covered slots.

    LOCALISATION : booking/tests/test_booking_engine.py

    WeeklyOpening : lundi 09:00, 60 min, 2 créneaux.
    Réservation : 2026-06-01 09:00, 60 min × 2 créneaux → couvre 09:00–11:00.
    Les deux créneaux ont remaining=0.
    / WeeklyOpening: Monday 09:00, 60 min, 2 slots.
    / Booking: 2026-06-01 09:00, 60 min × 2 slots → covers 09:00–11:00.
    / Both slots have remaining=0.

    09:00       10:00       11:00
      ├── [0] ───┼── [1] ───┤   capacity = 1
      ├─────── réservation ──┤   slot_count = 2
    [0].remaining = 0  ✓
    [1].remaining = 0  ✓
    """
    from booking.models import Booking, OpeningEntry
    from booking.booking_engine import compute_slots

    with schema_context(TENANT_SCHEMA):
        try:
            calendar      = _make_calendar('slot_count_gt_1')
            weekly_opening = _make_weekly_opening('slot_count_gt_1')
            OpeningEntry.objects.create(
                weekly_opening=weekly_opening,
                weekday=OpeningEntry.MONDAY,
                start_time=datetime.time(9, 0),
                slot_duration_minutes=60,
                slot_count=2,
            )
            resource = _make_resource(
                'slot_count_gt_1', calendar, weekly_opening, capacity=1,
            )

            user = _get_test_user()
            Booking.objects.create(
                resource=resource,
                user=user,
                start_datetime=_make_aware_dt(
                    datetime.date(2026, 6, 1), datetime.time(9, 0),
                ),
                slot_duration_minutes=60,
                slot_count=2,
                status=Booking.STATUS_NEW,
            )

            # reference_now = Jun 01 00:00 → date_from = Jun 01 00:00 → dans l'horizon par défaut.
            # / reference_now = Jun 01 00:00 → date_from = Jun 01 00:00 → within default horizon.
            # Fenêtre UTC pour cohérence avec _make_aware_dt (TIME_ZONE=UTC en tests).
            # / UTC window for consistency with _make_aware_dt (TIME_ZONE=UTC in tests).
            window     = Interval(
                _make_aware_dt(datetime.date(2026, 6, 1), datetime.time(0, 0)),
                _make_aware_dt(datetime.date(2026, 6, 2), datetime.time(0, 0)),
            )
            ref_now    = _make_aware_dt(datetime.date(2026, 6, 1), datetime.time(0, 0))
            slots = compute_slots(resource, window, reference_now=ref_now)

            assert len(slots) == 2
            assert slots[0].remaining_capacity == 0
            assert slots[1].remaining_capacity == 0

        finally:
            _cleanup()


@pytest.mark.django_db
def test_compute_slots_booking_partial_overlap_counts_as_full_overlap():
    """
    Un booking démarrant à l'intérieur du créneau compte comme chevauchement complet.
    / A booking starting inside the slot counts as full overlap.

    LOCALISATION : booking/tests/test_booking_engine.py

    Créneau 09:00–10:00, capacity=1. Booking 09:30–10:30 → remaining=0.

    09:00       09:30       10:00       10:30
      ├──── slot ─────────────┤
                  ├───── b1 ──────────────┤
    Partiel = complet → remaining = 0  ✓
    """
    from booking.models import Booking, OpeningEntry
    from booking.booking_engine import compute_slots

    with schema_context(TENANT_SCHEMA):
        try:
            calendar      = _make_calendar('partial_overlap')
            weekly_opening = _make_weekly_opening('partial_overlap')
            OpeningEntry.objects.create(
                weekly_opening=weekly_opening,
                weekday=OpeningEntry.MONDAY,
                start_time=datetime.time(9, 0),
                slot_duration_minutes=60,
                slot_count=1,
            )
            resource = _make_resource(
                'partial_overlap', calendar, weekly_opening, capacity=1,
            )

            user = _get_test_user()
            Booking.objects.create(
                resource=resource,
                user=user,
                start_datetime=_make_aware_dt(
                    datetime.date(2026, 6, 1), datetime.time(9, 30),
                ),
                slot_duration_minutes=60,
                slot_count=1,
                status=Booking.STATUS_NEW,
            )

            # Fenêtre UTC pour cohérence avec _make_aware_dt (TIME_ZONE=UTC en tests).
            # / UTC window for consistency with _make_aware_dt (TIME_ZONE=UTC in tests).
            window  = Interval(
                _make_aware_dt(datetime.date(2026, 6, 1), datetime.time(0, 0)),
                _make_aware_dt(datetime.date(2026, 6, 2), datetime.time(0, 0)),
            )
            ref_now = _make_aware_dt(datetime.date(2026, 6, 1), datetime.time(0, 0))
            slots = compute_slots(resource, window, reference_now=ref_now)

            assert len(slots) == 1
            assert slots[0].remaining_capacity == 0

        finally:
            _cleanup()


@pytest.mark.django_db
def test_compute_slots_returns_empty_when_no_opening_entries():
    """
    compute_slots retourne [] quand le WeeklyOpening n'a aucune entrée.
    / compute_slots returns [] when the WeeklyOpening has no entries.

    LOCALISATION : booking/tests/test_booking_engine.py
    """
    from booking.booking_engine import compute_slots

    with schema_context(TENANT_SCHEMA):
        try:
            calendar      = _make_calendar('no_entries')
            weekly_opening = _make_weekly_opening('no_entries')
            resource      = _make_resource('no_entries', calendar, weekly_opening)

            slots = compute_slots(
                resource,
                Interval(_aware(2026, 6, 1), _aware(2026, 6, 8)),
            )

            assert slots == []

        finally:
            _cleanup()


@pytest.mark.django_db
def test_compute_slots_end_to_end_with_fixture_coworking_resource():
    """
    Test de bout en bout — ressource de type "Coworking".
    / End-to-end test — "Coworking"-style resource.

    LOCALISATION : booking/tests/test_booking_engine.py

    Configuration : lun–ven, 8 créneaux × 60 min à partir de 09:00, capacity=3.
    Date fixe : 2026-06-02 (lundi), reference_date = 2026-06-01.
    8 créneaux attendus : 09:00–10:00, …, 16:00–17:00.
    / Config: Mon–Fri, 8 × 60 min from 09:00, capacity=3.
    / Fixed date: 2026-06-02 (Monday), reference_date = 2026-06-01.

    09:00 10:00 11:00 12:00 13:00 14:00 15:00 16:00 17:00
      [0]   [1]   [2]   [3]   [4]   [5]   [6]   [7]
    """
    from booking.booking_engine import compute_slots

    reference_now = _aware(2026, 6, 1)
    monday_dt     = _aware(2026, 6, 2)

    with schema_context(TENANT_SCHEMA):
        try:
            calendar = _make_calendar('coworking_e2e')
            opening  = _make_weekly_opening('coworking_e2e')
            resource = _make_resource(
                'coworking_e2e', calendar, opening, capacity=3, horizon=28,
            )

            for weekday in range(5):   # lun–ven / Mon–Fri
                _add_opening_entry(
                    opening, weekday=weekday,
                    start_time=datetime.time(9, 0),
                    slot_duration_minutes=60, slot_count=8,
                )

            slots = compute_slots(resource, Interval(monday_dt, _aware(2026, 6, 3)),
                                  reference_now=reference_now)

            assert len(slots) == 8
            assert slots[0].start.time() == datetime.time(9, 0)
            assert slots[0].end.time()   == datetime.time(10, 0)
            assert slots[7].start.time() == datetime.time(16, 0)
            assert slots[7].end.time()   == datetime.time(17, 0)

            for slot in slots:
                assert slot.start.date() == monday_dt.date()
                assert slot.duration_minutes() == 60
                assert slot.max_capacity == 3
                assert slot.remaining_capacity == 3

        finally:
            _cleanup()


@pytest.mark.django_db
def test_compute_slots_end_to_end_with_fixture_petite_salle():
    """
    Test de bout en bout — ressource de type "Petite salle".
    / End-to-end test — "Petite salle"-style resource.

    LOCALISATION : booking/tests/test_booking_engine.py

    Configuration : sam+dim, 3 créneaux × 180 min à partir de 10:00, capacity=1.
    Date fixe : 2026-06-07 (samedi), reference_date = 2026-06-01.
    3 créneaux attendus : 10:00–13:00, 13:00–16:00, 16:00–19:00.
    / Config: Sat+Sun, 3 × 180 min from 10:00, capacity=1.

    10:00       13:00       16:00       19:00
      [0]         [1]         [2]
     180 min     180 min     180 min
    """
    from booking.booking_engine import compute_slots

    reference_now = _aware(2026, 6, 1)
    saturday_dt   = _aware(2026, 6, 7)

    with schema_context(TENANT_SCHEMA):
        try:
            calendar = _make_calendar('petite_salle_e2e')
            opening  = _make_weekly_opening('petite_salle_e2e')
            resource = _make_resource(
                'petite_salle_e2e', calendar, opening, capacity=1, horizon=28,
            )

            for weekday in (5, 6):   # sam + dim / Sat + Sun
                _add_opening_entry(
                    opening, weekday=weekday,
                    start_time=datetime.time(10, 0),
                    slot_duration_minutes=180, slot_count=3,
                )

            slots = compute_slots(resource, Interval(saturday_dt, _aware(2026, 6, 8)),
                                  reference_now=reference_now)

            assert len(slots) == 3
            assert slots[0].start.time() == datetime.time(10, 0)
            assert slots[0].end.time()   == datetime.time(13, 0)
            assert slots[1].start.time() == datetime.time(13, 0)
            assert slots[1].end.time()   == datetime.time(16, 0)
            assert slots[2].start.time() == datetime.time(16, 0)
            assert slots[2].end.time()   == datetime.time(19, 0)

            for slot in slots:
                assert slot.duration_minutes() == 180
                assert slot.max_capacity == 1
                assert slot.remaining_capacity == 1

        finally:
            _cleanup()



# ---------------------------------------------------------------------------
# Tests — generate_theoretical_slots — ouverture toute la semaine  (unitaires / §10)
#
# Configuration partagée :
#   7 OpeningEntry légers (lun–dim), chacun : 00:00, 60 min, 24 créneaux.
#   Semaine 2026-06-01 (lun) → 2026-06-07 (dim).
#   Total sans fermeture : 7 × 24 = 168 créneaux.
#
# Note sur la frontière minuit (intervalle semi-ouvert [start, end)) :
# Le dernier créneau de chaque jour (23:00–00:00) a end = 00:00 du lendemain.
# Si le lendemain est dans O, end ≤ O.end → créneau ⊆ O → retourné.
# Si le lendemain est fermé, l'open interval se termine à minuit pile :
# end = O[k].end → créneau ⊆ O → retourné.
# Un créneau 23:30+60min=00:30 qui dépasse minuit d'un jour fermé a
# end=00:30 > O.end=00:00 → ⊄ O → exclu.
# / Note on midnight boundary (half-open [start, end)):
# / Last slot of each day (23:00–00:00) has end = 00:00 of next day.
# / end = O.end exactly → slot ⊆ O → returned.
# / slot 23:30+60min → end=00:30 > O.end=00:00 → ⊄ O → excluded.
# ---------------------------------------------------------------------------

def _full_week_entries():
    """
    Crée 7 OpeningEntry légers (lun–dim) : 00:00, 60 min, 24 créneaux.
    / Creates 7 lightweight OpeningEntry objects (Mon–Sun): 00:00, 60 min, 24 slots.
    """
    return [
        _oe(weekday=day, start_time=datetime.time(0, 0),
            slot_duration_minutes=60, slot_count=24)
        for day in range(7)
    ]


def test_full_week_opening_no_closed_day_returns_168_slots():
    """
    Ouverture 7j/7 24h/24, aucune fermeture : 168 créneaux.
    / 7-day 24h opening, no closures: 168 slots.

    LOCALISATION : booking/tests/test_booking_engine.py

    O = [Jun 01 00:00, Jun 08 00:00). 7 jours × 24 créneaux = 168.

    Lun  Mar  Mer  Jeu  Ven  Sam  Dim
    ████ ████ ████ ████ ████ ████ ████   24 créneaux par jour
     24   24   24   24   24   24   24  = 168
    """
    from booking.booking_engine import compute_open_intervals, generate_theoretical_slots

    O = compute_open_intervals([], WINDOW_FULL_WEEK)
    W = generate_theoretical_slots(_full_week_entries(), O, WINDOW_FULL_WEEK)

    assert len(W) == 168


def test_full_week_opening_wednesday_closed_returns_144_slots():
    """
    Mercredi fermé → 24 créneaux retirés, 144 restants.
    Le dernier créneau du mardi (mar 23:00–mer 00:00) finit exactement à
    l'end de O[0] → il est retourné (non exclu).
    / Wednesday closed → 24 slots removed, 144 remaining.
    / Tuesday's last slot ends exactly at O[0].end → returned.

    LOCALISATION : booking/tests/test_booking_engine.py

    O = [Jun 01 00:00, Jun 03 00:00) ∪ [Jun 04 00:00, Jun 08 00:00).

    Lun  Mar  Mer  Jeu  Ven  Sam  Dim
    ████ ████ ░░░░ ████ ████ ████ ████
     24   24    0   24   24   24   24  = 144
    """
    from booking.booking_engine import compute_open_intervals, generate_theoretical_slots

    O = compute_open_intervals(
        [_cp(datetime.date(2026, 6, 3), datetime.date(2026, 6, 3))],
        WINDOW_FULL_WEEK,
    )
    W = generate_theoretical_slots(_full_week_entries(), O, WINDOW_FULL_WEEK)

    assert len(W) == 144
    assert all(s.start.date() != datetime.date(2026, 6, 3) for s in W)


def test_full_week_opening_monday_closed_returns_144_slots():
    """
    Lundi fermé → 144 créneaux.
    / Monday (first day) closed → 144 slots.

    LOCALISATION : booking/tests/test_booking_engine.py

    O = [Jun 02 00:00, Jun 08 00:00).

    Lun  Mar  Mer  Jeu  Ven  Sam  Dim
    ░░░░ ████ ████ ████ ████ ████ ████
      0   24   24   24   24   24   24  = 144
    """
    from booking.booking_engine import compute_open_intervals, generate_theoretical_slots

    O = compute_open_intervals(
        [_cp(datetime.date(2026, 6, 1), datetime.date(2026, 6, 1))],
        WINDOW_FULL_WEEK,
    )
    W = generate_theoretical_slots(_full_week_entries(), O, WINDOW_FULL_WEEK)

    assert len(W) == 144
    assert all(s.start.date() != datetime.date(2026, 6, 1) for s in W)


def test_full_week_opening_sunday_closed_returns_144_slots():
    """
    Dimanche fermé → 144 créneaux.
    Le dernier créneau du samedi (sam 23:00–dim 00:00) finit à dim 00:00 = O.end
    → il est retourné.
    / Sunday (last day) closed → 144 slots.
    / Saturday's last slot ends at Sun 00:00 = O.end → returned.

    LOCALISATION : booking/tests/test_booking_engine.py

    O = [Jun 01 00:00, Jun 07 00:00).

    Lun  Mar  Mer  Jeu  Ven  Sam  Dim
    ████ ████ ████ ████ ████ ████ ░░░░
     24   24   24   24   24   24    0  = 144
    """
    from booking.booking_engine import compute_open_intervals, generate_theoretical_slots

    O = compute_open_intervals(
        [_cp(datetime.date(2026, 6, 7), datetime.date(2026, 6, 7))],
        WINDOW_FULL_WEEK,
    )
    W = generate_theoretical_slots(_full_week_entries(), O, WINDOW_FULL_WEEK)

    assert len(W) == 144
    assert all(s.start.date() != datetime.date(2026, 6, 7) for s in W)


def test_full_week_opening_two_non_adjacent_days_closed_returns_120_slots():
    """
    Mardi et vendredi fermés (non adjacents) → 120 créneaux.
    / Tuesday and Friday closed (non-adjacent) → 120 slots.

    LOCALISATION : booking/tests/test_booking_engine.py

    O = [Jun 01, Jun 02) ∪ [Jun 03, Jun 05) ∪ [Jun 06, Jun 08).

    Lun  Mar  Mer  Jeu  Ven  Sam  Dim
    ████ ░░░░ ████ ████ ░░░░ ████ ████
     24    0   24   24    0   24   24  = 120
    """
    from booking.booking_engine import compute_open_intervals, generate_theoretical_slots

    O = compute_open_intervals(
        [
            _cp(datetime.date(2026, 6, 2), datetime.date(2026, 6, 2)),
            _cp(datetime.date(2026, 6, 5), datetime.date(2026, 6, 5)),
        ],
        WINDOW_FULL_WEEK,
    )
    W = generate_theoretical_slots(_full_week_entries(), O, WINDOW_FULL_WEEK)

    assert len(W) == 120
    assert all(s.start.date() != datetime.date(2026, 6, 2) for s in W)
    assert all(s.start.date() != datetime.date(2026, 6, 5) for s in W)


# ---------------------------------------------------------------------------
# Tests — generate_theoretical_slots — 1 entry × 7 créneaux d'une journée
#         (unitaires / §10)
#
# Configuration : 1 OpeningEntry lundi (weekday=0), 00:00, 1440 min (1 jour),
#                 slot_count=7.
# Les 7 créneaux consécutifs couvrent exactement une semaine :
#   slot[0] lun 00:00 → mar 00:00
#   slot[1] mar 00:00 → mer 00:00
#   …
#   slot[6] dim 00:00 → lun 00:00 (semaine suivante)
# Semaine fixe : 2026-06-01 (lun) → 2026-06-07 (dim).
#
# Règle W (⊆ O) : chaque slot est vérifié individuellement.
# Quand lundi (jour de l'entrée) est fermé, seul slot[0] est exclu
# car son start tombe avant O.start. Les slots 1–6 dont le start_datetime
# est un jour ouvert restent ⊆ O → retournés.
# / Config: 1 Monday OpeningEntry, 00:00, 1440 min (1 day), slot_count=7.
# / Rule W (⊆ O): per-slot check. Closing Monday only excludes slot[0];
# / later slots starting on open days stay in O → returned.
#
# Note d'implémentation : l'offset temporel est calculé par timedelta
# (pas division heures/minutes) pour éviter ValueError quand
# slot_start_minutes = 8640 = 144 × 60 → datetime(…, 144, 0) lèverait erreur.
# ---------------------------------------------------------------------------

def _one_day_entries():
    """
    Crée 1 OpeningEntry léger : lundi, 00:00, 1440 min, 7 créneaux.
    / Creates 1 lightweight OpeningEntry: Monday, 00:00, 1440 min, 7 slots.
    """
    return [_oe(0, datetime.time(0, 0), 1440, 7)]


def test_one_day_slots_opening_no_closed_day_returns_7_slots():
    """
    1 entrée lundi × 7 créneaux d'une journée, aucune fermeture : 7 créneaux.
    / 1 Monday entry × 7 one-day slots, no closures: 7 slots.

    LOCALISATION : booking/tests/test_booking_engine.py

    O = [Jun 01 00:00, Jun 08 00:00). Tous les 7 slots ⊆ O.

    Lun  Mar  Mer  Jeu  Ven  Sam  Dim
    [0]  [1]  [2]  [3]  [4]  [5]  [6]   = 7 créneaux
    """
    from booking.booking_engine import compute_open_intervals, generate_theoretical_slots

    O = compute_open_intervals([], WINDOW_FULL_WEEK)
    W = generate_theoretical_slots(_one_day_entries(), O, WINDOW_FULL_WEEK)

    assert len(W) == 7

    expected_dates = [
        datetime.date(2026, 6, 1),   # lun / Mon
        datetime.date(2026, 6, 2),   # mar / Tue
        datetime.date(2026, 6, 3),   # mer / Wed
        datetime.date(2026, 6, 4),   # jeu / Thu
        datetime.date(2026, 6, 5),   # ven / Fri
        datetime.date(2026, 6, 6),   # sam / Sat
        datetime.date(2026, 6, 7),   # dim / Sun
    ]
    for slot, expected_date in zip(W, expected_dates):
        assert slot.start.date() == expected_date
        assert slot.duration_minutes() == 1440


def test_one_day_slots_opening_wednesday_closed_returns_6_slots():
    """
    1 entrée lundi × 7 créneaux, mercredi fermé → slot[2] exclu : 6 créneaux.
    / 1 Monday entry × 7 slots, Wednesday closed → slot[2] excluded: 6 slots.

    LOCALISATION : booking/tests/test_booking_engine.py

    O = [Jun 01, Jun 03) ∪ [Jun 04, Jun 08).
    slot[2] Jun 03–Jun 04 : end=Jun 04 > O[0].end=Jun 03 et start<O[1].start=Jun 04 → ⊄ O.
    """
    from booking.booking_engine import compute_open_intervals, generate_theoretical_slots

    O = compute_open_intervals(
        [_cp(datetime.date(2026, 6, 3), datetime.date(2026, 6, 3))],
        WINDOW_FULL_WEEK,
    )
    W = generate_theoretical_slots(_one_day_entries(), O, WINDOW_FULL_WEEK)

    assert len(W) == 6
    assert all(s.start.date() != datetime.date(2026, 6, 3) for s in W)


def test_one_day_slots_opening_monday_closed_returns_6_slots():
    """
    1 entrée lundi × 7 créneaux, lundi fermé → slot[0] exclu : 6 créneaux.
    / 1 Monday entry × 7 slots, Monday closed → slot[0] excluded: 6 slots.

    LOCALISATION : booking/tests/test_booking_engine.py

    O = [Jun 02 00:00, Jun 08 00:00).
    slot[0] Jun 01–Jun 02 : slot.start=Jun 01 < O.start=Jun 02 → ⊄ O → exclu.
    Les slots[1..6] dont le start ∈ [Jun 02, Jun 07] ⊆ O → retournés.
    La vérification est slot par slot — lundi fermé n'exclut pas l'entrée entière.
    / Closure is checked per-slot; Monday closed only excludes slot[0].

    Lun  Mar  Mer  Jeu  Ven  Sam  Dim
    ░░░░ ████ ████ ████ ████ ████ ████
    [0]  [1]  [2]  [3]  [4]  [5]  [6]
     ✗    ↑ premier retourné = Mar
    """
    from booking.booking_engine import compute_open_intervals, generate_theoretical_slots

    O = compute_open_intervals(
        [_cp(datetime.date(2026, 6, 1), datetime.date(2026, 6, 1))],
        WINDOW_FULL_WEEK,
    )
    W = generate_theoretical_slots(_one_day_entries(), O, WINDOW_FULL_WEEK)

    assert len(W) == 6
    assert W[0].start.date() == datetime.date(2026, 6, 2)


def test_one_day_slots_opening_sunday_closed_returns_6_slots():
    """
    1 entrée lundi × 7 créneaux, dimanche fermé → slot[6] exclu : 6 créneaux.
    / 1 Monday entry × 7 slots, Sunday closed → slot[6] excluded: 6 slots.

    LOCALISATION : booking/tests/test_booking_engine.py

    O = [Jun 01 00:00, Jun 07 00:00).
    slot[6] Jun 07–Jun 08 : slot.start=Jun 07=O.end → end=Jun 08>O.end → ⊄ O.
    slot[5] Jun 06–Jun 07 : end=Jun 07=O.end → ⊆ O → retourné.

    Lun  Mar  Mer  Jeu  Ven  Sam  Dim
    [0]  [1]  [2]  [3]  [4]  [5]  [6]
                                    ✗ ⊄ O
    """
    from booking.booking_engine import compute_open_intervals, generate_theoretical_slots

    O = compute_open_intervals(
        [_cp(datetime.date(2026, 6, 7), datetime.date(2026, 6, 7))],
        WINDOW_FULL_WEEK,
    )
    W = generate_theoretical_slots(_one_day_entries(), O, WINDOW_FULL_WEEK)

    assert len(W) == 6
    assert W[-1].start.date() == datetime.date(2026, 6, 6)


def test_one_day_slots_opening_two_non_adjacent_days_closed_returns_5_slots():
    """
    1 entrée lundi × 7 créneaux, mardi et vendredi fermés → 5 créneaux.
    / 1 Monday entry × 7 slots, Tuesday and Friday closed → 5 slots.

    LOCALISATION : booking/tests/test_booking_engine.py

    O = [Jun 01, Jun 02) ∪ [Jun 03, Jun 05) ∪ [Jun 06, Jun 08).
    slot[1] Jun 02–Jun 03 : ⊄ O → exclu.
    slot[4] Jun 05–Jun 06 : ⊄ O → exclu.

    Lun  Mar  Mer  Jeu  Ven  Sam  Dim
    [0]  [1]  [2]  [3]  [4]  [5]  [6]
          ✗              ✗
    Résultat : 5 créneaux.
    """
    from booking.booking_engine import compute_open_intervals, generate_theoretical_slots

    O = compute_open_intervals(
        [
            _cp(datetime.date(2026, 6, 2), datetime.date(2026, 6, 2)),
            _cp(datetime.date(2026, 6, 5), datetime.date(2026, 6, 5)),
        ],
        WINDOW_FULL_WEEK,
    )
    W = generate_theoretical_slots(_one_day_entries(), O, WINDOW_FULL_WEEK)

    assert len(W) == 5
    assert all(s.start.date() != datetime.date(2026, 6, 2) for s in W)
    assert all(s.start.date() != datetime.date(2026, 6, 5) for s in W)


# ---------------------------------------------------------------------------
# Tests — generate_theoretical_slots — 1 entry × 1 créneau d'une semaine
#         (unitaires / §10)
#
# Configuration : 1 OpeningEntry lundi (weekday=0), 00:00,
#                 slot_duration_minutes = WEEK_MINUTES = 10 080, slot_count=1.
# Le créneau unique couvre [Jun 01 00:00, Jun 08 00:00) = toute la semaine.
#
# Propriété clé : tout jour fermé scinde O → le créneau ⊄ tout o ∈ O → exclu.
# Résultat : 1 créneau (aucune fermeture) ou 0 (au moins un jour fermé).
# / Key property: any closed day splits O → slot ⊄ any o ∈ O → excluded.
# / Result: 1 slot (no closure) or 0 (any closed day).
# ---------------------------------------------------------------------------

def _one_week_entries():
    """
    Crée 1 OpeningEntry léger : lundi, 00:00, WEEK_MINUTES, 1 créneau.
    / Creates 1 lightweight OpeningEntry: Monday, 00:00, WEEK_MINUTES, 1 slot.
    """
    return [_oe(0, datetime.time(0, 0), WEEK_MINUTES, 1)]


def test_one_week_slot_opening_no_closed_day_returns_1_slot():
    """
    1 créneau d'une semaine entière, aucune fermeture : 1 créneau retourné.
    / 1 full-week slot, no closures: 1 slot returned.

    LOCALISATION : booking/tests/test_booking_engine.py

    O = [Jun 01, Jun 08). slot = [Jun 01, Jun 08) ⊆ O → retourné.

    Lun  Mar  Mer  Jeu  Ven  Sam  Dim
    ████████████████████████████████████
    ↑ start                       ↑ end = O.end
    """
    from booking.booking_engine import compute_open_intervals, generate_theoretical_slots

    O = compute_open_intervals([], WINDOW_FULL_WEEK)
    W = generate_theoretical_slots(_one_week_entries(), O, WINDOW_FULL_WEEK)

    assert len(W) == 1
    assert W[0].start.date()    == datetime.date(2026, 6, 1)
    assert W[0].duration_minutes() == WEEK_MINUTES


def test_one_week_slot_opening_wednesday_closed_returns_0_slots():
    """
    1 créneau d'une semaine, mercredi fermé → 0 créneaux.
    / 1 full-week slot, Wednesday closed → 0 slots.

    LOCALISATION : booking/tests/test_booking_engine.py

    O = [Jun 01, Jun 03) ∪ [Jun 04, Jun 08).
    slot [Jun 01, Jun 08) ⊄ O[0] (end=Jun 08>Jun 03) ⊄ O[1] (start=Jun 01<Jun 04) → exclu.

    Lun  Mar  Mer  Jeu  Ven  Sam  Dim
    ████ ████ ░░░░ ████ ████ ████ ████
    ↑──────────── créneau unique ─────↑
               ✗ O scindé → ⊄ tout o
    """
    from booking.booking_engine import compute_open_intervals, generate_theoretical_slots

    O = compute_open_intervals(
        [_cp(datetime.date(2026, 6, 3), datetime.date(2026, 6, 3))],
        WINDOW_FULL_WEEK,
    )
    W = generate_theoretical_slots(_one_week_entries(), O, WINDOW_FULL_WEEK)

    assert len(W) == 0


def test_one_week_slot_opening_monday_closed_returns_0_slots():
    """
    1 créneau d'une semaine, lundi fermé → 0 créneaux.
    / 1 full-week slot, Monday closed → 0 slots.

    LOCALISATION : booking/tests/test_booking_engine.py

    O = [Jun 02, Jun 08). slot.start=Jun 01 < O.start=Jun 02 → ⊄ O → exclu.
    """
    from booking.booking_engine import compute_open_intervals, generate_theoretical_slots

    O = compute_open_intervals(
        [_cp(datetime.date(2026, 6, 1), datetime.date(2026, 6, 1))],
        WINDOW_FULL_WEEK,
    )
    W = generate_theoretical_slots(_one_week_entries(), O, WINDOW_FULL_WEEK)

    assert len(W) == 0


def test_one_week_slot_opening_sunday_closed_returns_0_slots():
    """
    1 créneau d'une semaine, dimanche fermé → 0 créneaux.
    / 1 full-week slot, Sunday closed → 0 slots.

    LOCALISATION : booking/tests/test_booking_engine.py

    O = [Jun 01, Jun 07). slot.end=Jun 08 > O.end=Jun 07 → ⊄ O → exclu.
    """
    from booking.booking_engine import compute_open_intervals, generate_theoretical_slots

    O = compute_open_intervals(
        [_cp(datetime.date(2026, 6, 7), datetime.date(2026, 6, 7))],
        WINDOW_FULL_WEEK,
    )
    W = generate_theoretical_slots(_one_week_entries(), O, WINDOW_FULL_WEEK)

    assert len(W) == 0


# ---------------------------------------------------------------------------
# Tests — validate_new_booking  (intégration)
# Signature : validate_new_booking(resource, start_datetime, slot_duration_minutes,
#                                  slot_count, member, reference_date)
#           → (is_valid: bool, booking_or_error: Booking | str)
# reference_date = REFERENCE_DATE = 2026-06-01 dans tous les tests (§13).
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_validate_booking_accepts_valid_slot():
    """
    Un créneau ouvert, dans l'horizon et non complet est accepté.
    / An open, within-horizon, non-full slot is accepted.

    LOCALISATION : booking/tests/test_booking_engine.py

    Scénario : horizon 28j, capacité 1, MONDAY_NEAR à 10:00,
    aucune réservation, aucune fermeture. → (True, Booking)
    """
    from booking.booking_engine import validate_new_booking

    with schema_context(TENANT_SCHEMA):
        try:
            cal      = _make_calendar('val_accepts_valid')
            wop      = _make_weekly_opening('val_accepts_valid')
            resource = _make_resource('val_accepts_valid', cal, wop,
                                      capacity=1, horizon=28)
            _add_opening_entry(wop, weekday=0,
                               start_time=datetime.time(10, 0),
                               slot_duration_minutes=60, slot_count=1)

            is_valid, result = validate_new_booking(
                resource=resource,
                start_datetime=_make_aware_dt(MONDAY_NEAR, datetime.time(10, 0)),
                slot_duration_minutes=60,
                slot_count=1,
                member=_get_test_user(),
                reference_now=REFERENCE_NOW,
            )

            assert is_valid is True
            assert result is not None

        finally:
            _cleanup()


@pytest.mark.django_db
def test_validate_booking_rejects_slot_beyond_horizon():
    """
    Un créneau au-delà de booking_horizon_days est refusé.
    / A slot beyond booking_horizon_days is rejected.

    LOCALISATION : booking/tests/test_booking_engine.py

    Scénario : horizon 7j, créneau à MONDAY_FAR (+14j). → (False, str)
    """
    from booking.booking_engine import validate_new_booking

    with schema_context(TENANT_SCHEMA):
        try:
            cal      = _make_calendar('val_beyond_horizon')
            wop      = _make_weekly_opening('val_beyond_horizon')
            resource = _make_resource('val_beyond_horizon', cal, wop,
                                      capacity=1, horizon=7)
            _add_opening_entry(wop, weekday=MONDAY_FAR.weekday(),
                               start_time=datetime.time(10, 0),
                               slot_duration_minutes=60, slot_count=1)

            is_valid, error = validate_new_booking(
                resource=resource,
                start_datetime=_make_aware_dt(MONDAY_FAR, datetime.time(10, 0)),
                slot_duration_minutes=60,
                slot_count=1,
                member=_get_test_user(),
                reference_now=REFERENCE_NOW,
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

    LOCALISATION : booking/tests/test_booking_engine.py

    Scénario : MONDAY_NEAR déclaré fermé, créneau à 10:00. → (False, str)
    """
    from booking.booking_engine import validate_new_booking

    with schema_context(TENANT_SCHEMA):
        try:
            cal      = _make_calendar('val_closed_period')
            wop      = _make_weekly_opening('val_closed_period')
            resource = _make_resource('val_closed_period', cal, wop,
                                      capacity=1, horizon=28)
            _add_opening_entry(wop, weekday=0,
                               start_time=datetime.time(10, 0),
                               slot_duration_minutes=60, slot_count=1)
            _add_closed_period(cal,
                               start_date=MONDAY_NEAR, end_date=MONDAY_NEAR)

            is_valid, error = validate_new_booking(
                resource=resource,
                start_datetime=_make_aware_dt(MONDAY_NEAR, datetime.time(10, 0)),
                slot_duration_minutes=60,
                slot_count=1,
                member=_get_test_user(),
                reference_now=REFERENCE_NOW,
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

    LOCALISATION : booking/tests/test_booking_engine.py

    Scénario : capacité 1, une réservation existante sur le créneau. → (False, str)
    """
    from booking.booking_engine import validate_new_booking

    with schema_context(TENANT_SCHEMA):
        try:
            cal      = _make_calendar('val_full_slot')
            wop      = _make_weekly_opening('val_full_slot')
            resource = _make_resource('val_full_slot', cal, wop,
                                      capacity=1, horizon=28)
            _add_opening_entry(wop, weekday=0,
                               start_time=datetime.time(10, 0),
                               slot_duration_minutes=60, slot_count=1)

            start_dt = _make_aware_dt(MONDAY_NEAR, datetime.time(10, 0))
            user     = _get_test_user()
            _add_booking(resource, user, start_datetime=start_dt,
                         slot_duration_minutes=60, slot_count=1)

            is_valid, error = validate_new_booking(
                resource=resource,
                start_datetime=start_dt,
                slot_duration_minutes=60,
                slot_count=1,
                member=user,
                reference_now=REFERENCE_NOW,
            )

            assert is_valid is False
            assert error is not None

        finally:
            _cleanup()


@pytest.mark.django_db
def test_validate_booking_slot_count_gt_1_all_slots_must_be_available():
    """
    slot_count > 1 : tous les créneaux disponibles → accepté.
    / slot_count > 1: all slots available → accepted.

    LOCALISATION : booking/tests/test_booking_engine.py

    Scénario : 3 créneaux de 60 min, aucune réservation. → (True, Booking)
    """
    from booking.booking_engine import validate_new_booking

    with schema_context(TENANT_SCHEMA):
        try:
            cal      = _make_calendar('val_multi_all_available')
            wop      = _make_weekly_opening('val_multi_all_available')
            resource = _make_resource('val_multi_all_available', cal, wop,
                                      capacity=1, horizon=28)
            _add_opening_entry(wop, weekday=0,
                               start_time=datetime.time(10, 0),
                               slot_duration_minutes=60, slot_count=3)

            is_valid, result = validate_new_booking(
                resource=resource,
                start_datetime=_make_aware_dt(MONDAY_NEAR, datetime.time(10, 0)),
                slot_duration_minutes=60,
                slot_count=3,
                member=_get_test_user(),
                reference_now=REFERENCE_NOW,
            )

            assert is_valid is True
            assert result is not None

        finally:
            _cleanup()


@pytest.mark.django_db
def test_validate_booking_slot_count_gt_1_fails_if_one_slot_full():
    """
    slot_count > 1 : un créneau complet suffit à invalider la demande.
    / slot_count > 1: one full slot is enough to reject the whole request.

    LOCALISATION : booking/tests/test_booking_engine.py

    Scénario : 3 créneaux, le 2ème (11:00) déjà pris. → (False, str)
    """
    from booking.booking_engine import validate_new_booking

    with schema_context(TENANT_SCHEMA):
        try:
            cal      = _make_calendar('val_multi_one_full')
            wop      = _make_weekly_opening('val_multi_one_full')
            resource = _make_resource('val_multi_one_full', cal, wop,
                                      capacity=1, horizon=28)
            _add_opening_entry(wop, weekday=0,
                               start_time=datetime.time(10, 0),
                               slot_duration_minutes=60, slot_count=3)

            start_dt = _make_aware_dt(MONDAY_NEAR, datetime.time(10, 0))
            user     = _get_test_user()
            _add_booking(resource, user,
                         start_datetime=start_dt + datetime.timedelta(minutes=60),
                         slot_duration_minutes=60, slot_count=1)

            is_valid, error = validate_new_booking(
                resource=resource,
                start_datetime=start_dt,
                slot_duration_minutes=60,
                slot_count=3,
                member=user,
                reference_now=REFERENCE_NOW,
            )

            assert is_valid is False
            assert error is not None

        finally:
            _cleanup()


@pytest.mark.django_db
def test_validate_booking_slot_count_gt_1_fails_if_one_slot_in_closed_period():
    """
    slot_count > 1 : un créneau dans une ClosedPeriod invalide la demande.
    / slot_count > 1: one slot in a ClosedPeriod rejects the whole request.

    LOCALISATION : booking/tests/test_booking_engine.py

    Scénario : 3 créneaux journaliers (lun/mar/mer), mardi fermé. → (False, str)
    """
    from booking.booking_engine import validate_new_booking

    with schema_context(TENANT_SCHEMA):
        try:
            cal      = _make_calendar('val_multi_one_closed')
            wop      = _make_weekly_opening('val_multi_one_closed')
            resource = _make_resource('val_multi_one_closed', cal, wop,
                                      capacity=1, horizon=28)
            _add_opening_entry(wop, weekday=0,
                               start_time=datetime.time(0, 0),
                               slot_duration_minutes=1440, slot_count=3)
            _add_closed_period(cal,
                               start_date=MONDAY_NEAR + datetime.timedelta(days=1),
                               end_date=MONDAY_NEAR + datetime.timedelta(days=1))

            is_valid, error = validate_new_booking(
                resource=resource,
                start_datetime=_make_aware_dt(MONDAY_NEAR, datetime.time(0, 0)),
                slot_duration_minutes=1440,
                slot_count=3,
                member=_get_test_user(),
                reference_now=REFERENCE_NOW,
            )

            assert is_valid is False
            assert error is not None

        finally:
            _cleanup()


@pytest.mark.django_db
def test_validate_booking_rejects_mismatched_slot_duration():
    """
    slot_duration_minutes ne correspond à aucun créneau théorique → refusé.
    / slot_duration_minutes matches no theoretical slot → rejected.

    LOCALISATION : booking/tests/test_booking_engine.py

    Scénario : ouverture 60 min, demande 30 min. → (False, str)
    """
    from booking.booking_engine import validate_new_booking

    with schema_context(TENANT_SCHEMA):
        try:
            cal      = _make_calendar('val_mismatched_duration')
            wop      = _make_weekly_opening('val_mismatched_duration')
            resource = _make_resource('val_mismatched_duration', cal, wop,
                                      capacity=1, horizon=28)
            _add_opening_entry(wop, weekday=0,
                               start_time=datetime.time(10, 0),
                               slot_duration_minutes=60, slot_count=1)

            is_valid, error = validate_new_booking(
                resource=resource,
                start_datetime=_make_aware_dt(MONDAY_NEAR, datetime.time(10, 0)),
                slot_duration_minutes=30,
                slot_count=1,
                member=_get_test_user(),
                reference_now=REFERENCE_NOW,
            )

            assert is_valid is False
            assert error is not None

        finally:
            _cleanup()


@pytest.mark.django_db
def test_validate_booking_rejects_start_time_not_aligned_to_opening():
    """
    start_datetime ne correspond à aucun créneau théorique → refusé.
    / start_datetime matches no theoretical slot → rejected.

    LOCALISATION : booking/tests/test_booking_engine.py

    Scénario : ouverture 10:00, demande 10:15. → (False, str)
    """
    from booking.booking_engine import validate_new_booking

    with schema_context(TENANT_SCHEMA):
        try:
            cal      = _make_calendar('val_misaligned_start')
            wop      = _make_weekly_opening('val_misaligned_start')
            resource = _make_resource('val_misaligned_start', cal, wop,
                                      capacity=1, horizon=28)
            _add_opening_entry(wop, weekday=0,
                               start_time=datetime.time(10, 0),
                               slot_duration_minutes=60, slot_count=1)

            is_valid, error = validate_new_booking(
                resource=resource,
                start_datetime=_make_aware_dt(MONDAY_NEAR, datetime.time(10, 15)),
                slot_duration_minutes=60,
                slot_count=1,
                member=_get_test_user(),
                reference_now=REFERENCE_NOW,
            )

            assert is_valid is False
            assert error is not None

        finally:
            _cleanup()


@pytest.mark.django_db
def test_validate_booking_slot_count_gt_1_rejects_if_series_exceeds_opening():
    """
    slot_count dépasse le nombre de créneaux de l'ouverture → refusé.
    / slot_count exceeds the opening's slot count → rejected.

    LOCALISATION : booking/tests/test_booking_engine.py

    Scénario : ouverture slot_count=2, demande slot_count=3. → (False, str)
    Le 3ème créneau [12:00, 13:00) n'existe pas dans W → lookup échoue.
    """
    from booking.booking_engine import validate_new_booking

    with schema_context(TENANT_SCHEMA):
        try:
            cal      = _make_calendar('val_exceeds_opening')
            wop      = _make_weekly_opening('val_exceeds_opening')
            resource = _make_resource('val_exceeds_opening', cal, wop,
                                      capacity=1, horizon=28)
            _add_opening_entry(wop, weekday=0,
                               start_time=datetime.time(10, 0),
                               slot_duration_minutes=60, slot_count=2)

            is_valid, error = validate_new_booking(
                resource=resource,
                start_datetime=_make_aware_dt(MONDAY_NEAR, datetime.time(10, 0)),
                slot_duration_minutes=60,
                slot_count=3,
                member=_get_test_user(),
                reference_now=REFERENCE_NOW,
            )

            assert is_valid is False
            assert error is not None

        finally:
            _cleanup()


@pytest.mark.django_db
def test_validate_booking_accepts_slot_bleeding_into_next_open_day():
    """
    Créneau dépassant minuit accepté si le lendemain est ouvert.
    / Slot crossing midnight accepted when the next day is open.

    LOCALISATION : booking/tests/test_booking_engine.py

    Scénario : lundi 23:00, 120 min (→ mardi 01:00), aucune fermeture.
    O = [Jun 08 00:00, Jun 10 00:00). slot ⊆ O → (True, Booking)
    """
    from booking.booking_engine import validate_new_booking

    with schema_context(TENANT_SCHEMA):
        try:
            cal      = _make_calendar('val_bleed_open')
            wop      = _make_weekly_opening('val_bleed_open')
            resource = _make_resource('val_bleed_open', cal, wop,
                                      capacity=1, horizon=28)
            _add_opening_entry(wop, weekday=0,
                               start_time=datetime.time(23, 0),
                               slot_duration_minutes=120, slot_count=1)

            is_valid, result = validate_new_booking(
                resource=resource,
                start_datetime=_make_aware_dt(MONDAY_NEAR, datetime.time(23, 0)),
                slot_duration_minutes=120,
                slot_count=1,
                member=_get_test_user(),
                reference_now=REFERENCE_NOW,
            )

            assert is_valid is True
            assert result is not None

        finally:
            _cleanup()


@pytest.mark.django_db
def test_validate_booking_rejects_slot_bleeding_into_closed_next_day():
    """
    Créneau dépassant minuit refusé si le lendemain est fermé.
    / Slot crossing midnight rejected when the next day is closed.

    LOCALISATION : booking/tests/test_booking_engine.py

    Scénario : lundi 23:00, 120 min (→ mardi 01:00), mardi fermé.
    O = [Jun 08 00:00, Jun 09 00:00). slot.end=01:00 > O.end=00:00 → ⊄ O.
    → (False, str)
    """
    from booking.booking_engine import validate_new_booking

    with schema_context(TENANT_SCHEMA):
        try:
            cal      = _make_calendar('val_bleed_closed')
            wop      = _make_weekly_opening('val_bleed_closed')
            resource = _make_resource('val_bleed_closed', cal, wop,
                                      capacity=1, horizon=28)
            _add_opening_entry(wop, weekday=0,
                               start_time=datetime.time(23, 0),
                               slot_duration_minutes=120, slot_count=1)
            tuesday = MONDAY_NEAR + datetime.timedelta(days=1)
            _add_closed_period(cal, start_date=tuesday, end_date=tuesday)

            is_valid, error = validate_new_booking(
                resource=resource,
                start_datetime=_make_aware_dt(MONDAY_NEAR, datetime.time(23, 0)),
                slot_duration_minutes=120,
                slot_count=1,
                member=_get_test_user(),
                reference_now=REFERENCE_NOW,
            )

            assert is_valid is False
            assert error is not None

        finally:
            _cleanup()


@pytest.mark.django_db
def test_validate_booking_accepts_slot_starting_in_a_few_minutes():
    """
    Un créneau qui commence dans quelques minutes est réservable (§5 Availability).
    Pas de délai minimum : start_datetime > now suffit.
    / A slot starting in a few minutes is bookable (§5 Availability).
    No minimum notice: start_datetime > now is sufficient.

    LOCALISATION : booking/tests/test_booking_engine.py

    Scénario : ouverture 10:00, reference_now = 09:55 (5 min avant).
    Le créneau 10:00 est strictement dans le futur → (True, Booking).
    """
    from booking.booking_engine import validate_new_booking

    with schema_context(TENANT_SCHEMA):
        try:
            cal      = _make_calendar('val_near_future')
            wop      = _make_weekly_opening('val_near_future')
            resource = _make_resource('val_near_future', cal, wop,
                                      capacity=1, horizon=28)
            _add_opening_entry(wop, weekday=0,
                               start_time=datetime.time(10, 0),
                               slot_duration_minutes=60, slot_count=1)

            # « maintenant » est 09:55 → le créneau 10:00 est dans 5 minutes
            # / « now » is 09:55 → the 10:00 slot starts in 5 minutes
            reference_now = _make_aware_dt(MONDAY_NEAR, datetime.time(9, 55))

            is_valid, result = validate_new_booking(
                resource=resource,
                start_datetime=_make_aware_dt(MONDAY_NEAR, datetime.time(10, 0)),
                slot_duration_minutes=60,
                slot_count=1,
                member=_get_test_user(),
                reference_now=reference_now,
            )

            assert is_valid is True
            assert result is not None

        finally:
            _cleanup()


@pytest.mark.django_db
def test_validate_booking_rejects_slot_that_has_already_started():
    """
    Un créneau dont le début est passé ne peut plus être réservé (§5 Availability).
    / A slot whose start time is in the past cannot be booked (§5 Availability).

    LOCALISATION : booking/tests/test_booking_engine.py

    Scénario : ouverture 10:00, reference_now = 10:05 (5 min après).
    Le créneau 10:00 a déjà commencé → (False, str).
    """
    from booking.booking_engine import validate_new_booking

    with schema_context(TENANT_SCHEMA):
        try:
            cal      = _make_calendar('val_past_slot')
            wop      = _make_weekly_opening('val_past_slot')
            resource = _make_resource('val_past_slot', cal, wop,
                                      capacity=1, horizon=28)
            _add_opening_entry(wop, weekday=0,
                               start_time=datetime.time(10, 0),
                               slot_duration_minutes=60, slot_count=1)

            # « maintenant » est 10:05 → le créneau 10:00 a déjà commencé
            # / « now » is 10:05 → the 10:00 slot has already started
            reference_now = _make_aware_dt(MONDAY_NEAR, datetime.time(10, 5))

            is_valid, error = validate_new_booking(
                resource=resource,
                start_datetime=_make_aware_dt(MONDAY_NEAR, datetime.time(10, 0)),
                slot_duration_minutes=60,
                slot_count=1,
                member=_get_test_user(),
                reference_now=reference_now,
            )

            assert is_valid is False
            assert error is not None

        finally:
            _cleanup()




def test_generate_theoretical_slots_excludes_past_slots_when_date_from_is_mid_day():
    """
    Créneaux commençant avant date_from (milieu de journée) sont exclus.
    Créneaux commençant à partir de date_from sont inclus.
    / Slots starting before date_from (mid-day datetime) are excluded.
    / Slots starting at or after date_from are included.

    LOCALISATION : booking/tests/test_booking_engine.py

    Vérifie le correctif du bug : les créneaux passés du jour courant ne doivent
    pas être affichés quand date_from = timezone.now() (milieu de journée).
    / Verifies the bug fix: past-today slots must not be shown when
    / date_from = timezone.now() (mid-day).

    Ouverture lundi 08:00, 60 min × 4 créneaux → 08:00, 09:00, 10:00, 11:00.
    date_from = 10:00 → 08:00 et 09:00 exclus, 10:00 et 11:00 inclus.
    / Monday 08:00, 60 min × 4 slots → 08:00, 09:00, 10:00, 11:00.
    / date_from = 10:00 → 08:00 and 09:00 excluded, 10:00 and 11:00 included.
    """
    from booking.booking_engine import generate_theoretical_slots

    entries        = [_oe(weekday=0, start_time=datetime.time(8, 0),
                          slot_duration_minutes=60, slot_count=4)]
    window         = Interval(_aware(2026, 6, 1, 10, 0), _aware(2026, 6, 2))
    open_intervals = [Interval(start=_aware(2026, 6, 1), end=_aware(2026, 6, 2))]

    slots = generate_theoretical_slots(entries, open_intervals, window)

    starts = [s.start for s in slots]
    assert _aware(2026, 6, 1, 8, 0)  not in starts   # passé — exclu / past — excluded
    assert _aware(2026, 6, 1, 9, 0)  not in starts   # passé — exclu / past — excluded
    assert _aware(2026, 6, 1, 10, 0) in starts        # = date_from — inclus / included
    assert _aware(2026, 6, 1, 11, 0) in starts        # futur — inclus / future — included
    assert len(slots) == 2
