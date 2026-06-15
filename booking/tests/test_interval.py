"""
Tests unitaires purs pour les classes Interval et BookableInterval.
/ Pure unit tests for the Interval and BookableInterval classes.

LOCALISATION : booking/tests/test_interval.py

Ces tests ne nécessitent pas d'accès à la base de données.
Ils vérifient la logique pure des méthodes overlaps(), contains()
et duration_minutes() de la classe Interval, ainsi que les propriétés
de délégation de BookableInterval.
/ These tests do not require database access.
They check the pure logic of Interval.overlaps(), contains() and
duration_minutes(), and the delegation properties of BookableInterval.

Lancement / Run:
    docker exec lespass_django poetry run pytest \
        booking/tests/test_interval.py -v
"""
import datetime

import pytest

UTC = datetime.timezone.utc


def _dt(hour, minute=0, day=1):
    """
    Construit un datetime timezone-aware (UTC) pour les tests.
    L'année et le mois sont fixes — seuls day, hour et minute varient.
    / Builds a UTC timezone-aware datetime for tests.
    Year and month are fixed — only day, hour, minute vary.
    """
    return datetime.datetime(2026, 6, day, hour, minute, tzinfo=UTC)


def _interval(start_hour, end_hour, start_day=1, end_day=1):
    """
    Raccourci : crée un Interval [start_hour:00, end_hour:00) sur le jour donné.
    / Shortcut: creates an Interval [start_hour:00, end_hour:00) on the given day.
    """
    from booking.booking_engine import Interval

    return Interval(
        start=_dt(start_hour, day=start_day),
        end=_dt(end_hour, day=end_day),
    )


# ---------------------------------------------------------------------------
# Tests — Interval.overlaps()
# ---------------------------------------------------------------------------

def test_overlaps_same_interval():
    """
    Deux intervalles identiques se chevauchent.
    / Two identical intervals overlap.

    LOCALISATION : booking/tests/test_interval.py

    [10, 11) ∩ [10, 11) → True
    """
    a = _interval(10, 11)
    assert a.overlaps(a) is True


def test_overlaps_adjacent_do_not_overlap():
    """
    Deux intervalles adjacents ne se chevauchent pas.
    La borne supérieure est exclue — [10, 11) finit avant [11, 12).
    / Two adjacent intervals do not overlap.
    Upper bound is exclusive — [10, 11) ends before [11, 12).

    LOCALISATION : booking/tests/test_interval.py

    [10, 11) ∩ [11, 12) → False (symétrique)
    """
    a = _interval(10, 11)
    b = _interval(11, 12)
    assert a.overlaps(b) is False
    assert b.overlaps(a) is False


def test_overlaps_partial_overlap():
    """
    Deux intervalles qui se chevauchent partiellement.
    / Two intervals that partially overlap.

    LOCALISATION : booking/tests/test_interval.py

    [10, 12) ∩ [11, 13) → True (symétrique)
    """
    a = _interval(10, 12)
    b = _interval(11, 13)
    assert a.overlaps(b) is True
    assert b.overlaps(a) is True


def test_overlaps_one_contains_the_other():
    """
    Un intervalle qui contient entièrement l'autre se chevauche.
    / An interval that fully contains the other overlaps.

    LOCALISATION : booking/tests/test_interval.py

    [10, 14) ∩ [11, 13) → True (symétrique)
    """
    outer = _interval(10, 14)
    inner = _interval(11, 13)
    assert outer.overlaps(inner) is True
    assert inner.overlaps(outer) is True


def test_overlaps_no_overlap():
    """
    Deux intervalles disjoints ne se chevauchent pas.
    / Two disjoint intervals do not overlap.

    LOCALISATION : booking/tests/test_interval.py

    [10, 11) ∩ [12, 13) → False (symétrique)
    """
    a = _interval(10, 11)
    b = _interval(12, 13)
    assert a.overlaps(b) is False
    assert b.overlaps(a) is False


def test_overlaps_touching_at_upper_bound():
    """
    Un intervalle qui se termine exactement là où l'autre commence
    ne chevauche pas (borne supérieure exclue).
    / An interval ending exactly where another begins does not overlap
    (exclusive upper bound).

    LOCALISATION : booking/tests/test_interval.py

    [8, 10) ∩ [10, 12) → False — 10 est exclu de [8, 10)
    / [8, 10) ∩ [10, 12) → False — 10 is excluded from [8, 10)
    """
    a = _interval(8, 10)
    b = _interval(10, 12)
    assert a.overlaps(b) is False
    assert b.overlaps(a) is False


# ---------------------------------------------------------------------------
# Tests — Interval.contains()
# ---------------------------------------------------------------------------

def test_contains_same_interval():
    """
    Un intervalle se contient lui-même.
    / An interval contains itself.

    LOCALISATION : booking/tests/test_interval.py

    [10, 11) ⊇ [10, 11) → True
    """
    a = _interval(10, 11)
    assert a.contains(a) is True


def test_contains_strictly_inner():
    """
    Un intervalle contient un plus petit qu'il englobe entièrement.
    / An interval contains a smaller one it fully englobes.

    LOCALISATION : booking/tests/test_interval.py

    [10, 14) ⊇ [11, 13) → True
    """
    outer = _interval(10, 14)
    inner = _interval(11, 13)
    assert outer.contains(inner) is True


def test_contains_reverse_is_false():
    """
    L'intervalle intérieur ne contient pas l'extérieur.
    / The inner interval does not contain the outer one.

    LOCALISATION : booking/tests/test_interval.py

    [11, 13) ⊇ [10, 14) → False
    """
    outer = _interval(10, 14)
    inner = _interval(11, 13)
    assert inner.contains(outer) is False


def test_contains_starts_before():
    """
    Un intervalle qui commence avant self n'est pas contenu.
    / An interval starting before self is not contained.

    LOCALISATION : booking/tests/test_interval.py

    [10, 11) ⊇ [9, 11) → False — [9, 11) déborde à gauche
    / [10, 11) ⊇ [9, 11) → False — [9, 11) starts before self
    """
    a = _interval(10, 11)
    b = _interval(9, 11)
    assert a.contains(b) is False


def test_contains_ends_after():
    """
    Un intervalle qui se termine après self n'est pas contenu.
    / An interval ending after self is not contained.

    LOCALISATION : booking/tests/test_interval.py

    [10, 11) ⊇ [10, 12) → False — [10, 12) déborde à droite
    / [10, 11) ⊇ [10, 12) → False — [10, 12) ends after self
    """
    a = _interval(10, 11)
    b = _interval(10, 12)
    assert a.contains(b) is False


def test_contains_no_overlap():
    """
    Deux intervalles disjoints ne se contiennent pas.
    / Two disjoint intervals do not contain each other.

    LOCALISATION : booking/tests/test_interval.py

    [10, 11) ⊇ [12, 13) → False
    """
    a = _interval(10, 11)
    b = _interval(12, 13)
    assert a.contains(b) is False
    assert b.contains(a) is False


def test_contains_shared_start_only():
    """
    Même début mais fin différente — only contained quand other se termine avant.
    / Same start but different end — only contained when other ends earlier.

    LOCALISATION : booking/tests/test_interval.py

    [10, 12) ⊇ [10, 11) → True  (même début, other finit avant)
    [10, 11) ⊇ [10, 12) → False (même début, other finit après)
    """
    wide = _interval(10, 12)
    narrow = _interval(10, 11)
    assert wide.contains(narrow) is True
    assert narrow.contains(wide) is False


def test_contains_shared_end_only():
    """
    Même fin mais début différent.
    / Same end but different start.

    LOCALISATION : booking/tests/test_interval.py

    [10, 12) ⊇ [11, 12) → True  (other commence après)
    [11, 12) ⊇ [10, 12) → False (other commence avant)
    """
    wide = _interval(10, 12)
    narrow = _interval(11, 12)
    assert wide.contains(narrow) is True
    assert narrow.contains(wide) is False


# ---------------------------------------------------------------------------
# Tests — Interval.duration_minutes()
# ---------------------------------------------------------------------------

def test_duration_minutes_one_hour():
    """
    Un intervalle d'une heure vaut 60 minutes.
    / A one-hour interval is 60 minutes.

    LOCALISATION : booking/tests/test_interval.py
    """
    a = _interval(10, 11)
    assert a.duration_minutes() == 60


def test_duration_minutes_half_hour():
    """
    Un intervalle de 30 minutes.
    / A 30-minute interval.

    LOCALISATION : booking/tests/test_interval.py
    """
    from booking.booking_engine import Interval

    a = Interval(
        start=_dt(10, 0),
        end=_dt(10, 30),
    )
    assert a.duration_minutes() == 30


def test_duration_minutes_crossing_midnight():
    """
    Un intervalle qui traverse minuit — lundi 23:00 → mardi 01:00.
    / An interval crossing midnight — Monday 23:00 → Tuesday 01:00.

    LOCALISATION : booking/tests/test_interval.py

    23:00 → 01:00 = 120 minutes.
    """
    from booking.booking_engine import Interval

    a = Interval(
        start=_dt(23, 0, day=1),
        end=_dt(1, 0, day=2),
    )
    assert a.duration_minutes() == 120


def test_duration_minutes_full_day():
    """
    Un intervalle d'un jour entier vaut 1440 minutes.
    / A full-day interval is 1440 minutes.

    LOCALISATION : booking/tests/test_interval.py
    """
    from booking.booking_engine import Interval

    a = Interval(
        start=_dt(0, 0, day=1),
        end=_dt(0, 0, day=2),
    )
    assert a.duration_minutes() == 1440


# ---------------------------------------------------------------------------
# Tests — BookableInterval
# ---------------------------------------------------------------------------

def test_bookable_interval_start_end_delegate_to_interval():
    """
    Les propriétés start et end délèguent à l'Interval interne.
    / start and end properties delegate to the inner Interval.

    LOCALISATION : booking/tests/test_interval.py
    """
    from booking.booking_engine import BookableInterval

    interval = _interval(10, 11)
    bookable = BookableInterval(
        interval=interval,
        max_capacity=3,
        remaining_capacity=2,
    )

    assert bookable.start == interval.start
    assert bookable.end == interval.end


def test_bookable_interval_stores_capacities():
    """
    BookableInterval conserve max_capacity et remaining_capacity.
    / BookableInterval stores max_capacity and remaining_capacity.

    LOCALISATION : booking/tests/test_interval.py
    """
    from booking.booking_engine import BookableInterval

    interval = _interval(10, 11)
    bookable = BookableInterval(
        interval=interval,
        max_capacity=5,
        remaining_capacity=3,
    )

    assert bookable.max_capacity == 5
    assert bookable.remaining_capacity == 3


def test_bookable_interval_remaining_capacity_can_be_zero():
    """
    remaining_capacity == 0 représente un créneau complet.
    / remaining_capacity == 0 represents a fully booked slot.

    LOCALISATION : booking/tests/test_interval.py
    """
    from booking.booking_engine import BookableInterval

    interval = _interval(10, 11)
    bookable = BookableInterval(
        interval=interval,
        max_capacity=1,
        remaining_capacity=0,
    )

    assert bookable.remaining_capacity == 0


def test_bookable_interval_remaining_capacity_is_mutable():
    """
    remaining_capacity peut être modifié après construction
    (BookableInterval n'est pas frozen).
    / remaining_capacity can be updated after construction
    (BookableInterval is not frozen).

    LOCALISATION : booking/tests/test_interval.py
    """
    from booking.booking_engine import BookableInterval

    interval = _interval(10, 11)
    bookable = BookableInterval(
        interval=interval,
        max_capacity=3,
        remaining_capacity=3,
    )

    bookable.remaining_capacity = 2
    assert bookable.remaining_capacity == 2


def test_bookable_interval_wraps_interval_methods():
    """
    L'Interval interne conserve ses méthodes accessibles via bookable.interval.
    / The inner Interval keeps its methods accessible via bookable.interval.

    LOCALISATION : booking/tests/test_interval.py
    """
    from booking.booking_engine import BookableInterval, Interval

    interval_a = _interval(10, 11)
    interval_b = _interval(10, 12)
    bookable_a = BookableInterval(interval=interval_a, max_capacity=1, remaining_capacity=1)
    bookable_b = BookableInterval(interval=interval_b, max_capacity=1, remaining_capacity=1)

    # interval.contains() est accessible via .interval
    # / interval.contains() is accessible via .interval
    assert bookable_b.interval.contains(bookable_a.interval) is True
    assert bookable_a.interval.contains(bookable_b.interval) is False
