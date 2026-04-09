"""
Tests de la contrainte de non-chevauchement des OpeningEntry.
/ Tests for the non-overlap constraint on OpeningEntry.

LOCALISATION : booking/tests/test_weekly_opening_overlap.py

Règle métier : dans un WeeklyOpening, deux OpeningEntry ne peuvent pas
se chevaucher. La semaine est traitée comme une timeline circulaire de
7 × 24 h. Une entry dont la durée totale dépasse minuit « déborde » sur
le jour suivant. Le dimanche peut déborder sur le lundi (retour en
début de semaine).
/ Business rule: within a WeeklyOpening, two OpeningEntry must not
overlap. The week is a circular 7 × 24 h timeline. An entry whose
total duration extends past midnight "bleeds" into the next day.
Sunday can bleed into Monday (circular wrap-around).

Représentation interne utilisée par la validation :
  position_en_minutes = weekday × 1440 + heure × 60 + minute
  fin_en_minutes      = position_en_minutes + slot_duration_minutes × slot_count
  Si fin_en_minutes > 10 080 (= 7 × 1440), le bloc déborde et on le
  compare circulairement au début de la semaine.
/ Internal representation used by the validator:
  position_minutes = weekday × 1440 + hour × 60 + minute
  end_minutes      = position_minutes + slot_duration_minutes × slot_count
  If end_minutes > 10 080 (= 7 × 1440), the block wraps around and is
  compared circularly to the start of the week.

Lancement / Run:
    docker exec lespass_django poetry run pytest \
        booking/tests/test_weekly_opening_overlap.py -v
"""
import datetime

import pytest
from django.core.exceptions import ValidationError
from django_tenants.utils import schema_context

TEST_PREFIX = '[test_weekly_opening_overlap]'
TENANT_SCHEMA = 'lespass'


@pytest.mark.django_db
def test_slot_entry_accepts_non_overlapping_entries_same_day():
    """
    Deux OpeningEntry sur le même jour sans chevauchement sont acceptées.
    / Two OpeningEntry on the same day without overlap are accepted.

    LOCALISATION : booking/tests/test_weekly_opening_overlap.py

    Lundi matin  : 09:00 → 12:00 (3 créneaux × 60 min).
    Lundi après-midi : 13:00 → 15:00 (2 créneaux × 60 min).
    Plage libre de 12:00 à 13:00 — aucun chevauchement.
    full_clean() ne doit PAS lever ValidationError.
    / Monday morning: 09:00 → 12:00 (3 slots × 60 min).
    / Monday afternoon: 13:00 → 15:00 (2 slots × 60 min).
    / Free gap 12:00–13:00 — no overlap. full_clean() must NOT raise.
    """
    from booking.models import WeeklyOpening, OpeningEntry

    with schema_context(TENANT_SCHEMA):
        opening = WeeklyOpening.objects.create(
            name=f'{TEST_PREFIX} accepts_non_overlapping_same_day',
        )
        try:
            OpeningEntry.objects.create(
                weekly_opening=opening,
                weekday=OpeningEntry.MONDAY,
                start_time=datetime.time(9, 0),
                slot_duration_minutes=60,
                slot_count=3,
            )

            entry_afternoon = OpeningEntry(
                weekly_opening=opening,
                weekday=OpeningEntry.MONDAY,
                start_time=datetime.time(13, 0),
                slot_duration_minutes=60,
                slot_count=2,
            )
            entry_afternoon.full_clean()

        finally:
            # on_delete=PROTECT — children before parent
            OpeningEntry.objects.filter(
                weekly_opening__name__startswith=TEST_PREFIX,
            ).delete()
            WeeklyOpening.objects.filter(name__startswith=TEST_PREFIX).delete()


@pytest.mark.django_db
def test_slot_entry_rejects_overlap_same_day():
    """
    Deux OpeningEntry sur le même jour qui se chevauchent sont refusées.
    / Two OpeningEntry on the same day that overlap are rejected.

    LOCALISATION : booking/tests/test_weekly_opening_overlap.py

    Lundi matin : 09:00 → 12:00 (3 × 60 min).
    Lundi       : 11:00 → 13:00 (2 × 60 min) — chevauchement 11:00–12:00.
    full_clean() doit lever ValidationError.
    / Monday morning: 09:00 → 12:00 (3 × 60 min).
    / Monday: 11:00 → 13:00 (2 × 60 min) — overlap 11:00–12:00.
    / full_clean() must raise ValidationError.
    """
    from booking.models import WeeklyOpening, OpeningEntry

    with schema_context(TENANT_SCHEMA):
        opening = WeeklyOpening.objects.create(
            name=f'{TEST_PREFIX} rejects_overlap_same_day',
        )
        try:
            OpeningEntry.objects.create(
                weekly_opening=opening,
                weekday=OpeningEntry.MONDAY,
                start_time=datetime.time(9, 0),
                slot_duration_minutes=60,
                slot_count=3,
            )

            entry_overlapping = OpeningEntry(
                weekly_opening=opening,
                weekday=OpeningEntry.MONDAY,
                start_time=datetime.time(11, 0),
                slot_duration_minutes=60,
                slot_count=2,
            )
            with pytest.raises(ValidationError):
                entry_overlapping.full_clean()

        finally:
            OpeningEntry.objects.filter(
                weekly_opening__name__startswith=TEST_PREFIX,
            ).delete()
            WeeklyOpening.objects.filter(name__startswith=TEST_PREFIX).delete()


@pytest.mark.django_db
def test_slot_entry_rejects_overlap_bleeding_into_next_day():
    """
    Un entry qui dépasse minuit est détecté comme chevauchant le jour suivant.
    / An entry that extends past midnight is detected as overlapping the next day.

    LOCALISATION : booking/tests/test_weekly_opening_overlap.py

    Lundi  : 23:00 → mardi 02:00 (2 créneaux × 90 min).
    Mardi  : 01:00 → mardi 02:00 (1 créneau × 60 min).
    Chevauchement mardi 01:00–02:00 → ValidationError.
    / Monday: 23:00 → Tuesday 02:00 (2 slots × 90 min).
    / Tuesday: 01:00 → Tuesday 02:00 (1 slot × 60 min).
    / Overlap Tuesday 01:00–02:00 → ValidationError.
    """
    from booking.models import WeeklyOpening, OpeningEntry

    with schema_context(TENANT_SCHEMA):
        opening = WeeklyOpening.objects.create(
            name=f'{TEST_PREFIX} rejects_bleed_into_next_day',
        )
        try:
            OpeningEntry.objects.create(
                weekly_opening=opening,
                weekday=OpeningEntry.MONDAY,
                start_time=datetime.time(23, 0),
                slot_duration_minutes=90,
                slot_count=2,
            )

            entry_tuesday = OpeningEntry(
                weekly_opening=opening,
                weekday=OpeningEntry.TUESDAY,
                start_time=datetime.time(1, 0),
                slot_duration_minutes=60,
                slot_count=1,
            )
            with pytest.raises(ValidationError):
                entry_tuesday.full_clean()

        finally:
            OpeningEntry.objects.filter(
                weekly_opening__name__startswith=TEST_PREFIX,
            ).delete()
            WeeklyOpening.objects.filter(name__startswith=TEST_PREFIX).delete()


@pytest.mark.django_db
def test_slot_entry_rejects_circular_overlap_sunday_to_monday():
    """
    Un entry du dimanche qui dépasse minuit chevauche le lundi de la même semaine.
    / A Sunday entry extending past midnight overlaps the Monday of the same week.

    LOCALISATION : booking/tests/test_weekly_opening_overlap.py

    Dimanche : 23:00 → lundi 02:00 (2 créneaux × 90 min) — débordement circulaire.
    Lundi    : 01:00 → 02:00 (1 créneau × 60 min).
    Chevauchement lundi 01:00–02:00 → ValidationError.
    / Sunday: 23:00 → Monday 02:00 (2 slots × 90 min) — circular bleed-over.
    / Monday: 01:00 → 02:00 (1 slot × 60 min).
    / Overlap Monday 01:00–02:00 → ValidationError.
    """
    from booking.models import WeeklyOpening, OpeningEntry

    with schema_context(TENANT_SCHEMA):
        opening = WeeklyOpening.objects.create(
            name=f'{TEST_PREFIX} rejects_circular_sunday_monday',
        )
        try:
            OpeningEntry.objects.create(
                weekly_opening=opening,
                weekday=OpeningEntry.SUNDAY,
                start_time=datetime.time(23, 0),
                slot_duration_minutes=90,
                slot_count=2,
            )

            entry_monday = OpeningEntry(
                weekly_opening=opening,
                weekday=OpeningEntry.MONDAY,
                start_time=datetime.time(1, 0),
                slot_duration_minutes=60,
                slot_count=1,
            )
            with pytest.raises(ValidationError):
                entry_monday.full_clean()

        finally:
            OpeningEntry.objects.filter(
                weekly_opening__name__startswith=TEST_PREFIX,
            ).delete()
            WeeklyOpening.objects.filter(name__startswith=TEST_PREFIX).delete()


@pytest.mark.django_db
def test_slot_entry_accepts_entries_on_different_days_no_overlap():
    """
    Deux entries sur des jours différents et sans débordement sont acceptés.
    / Two entries on different days with no bleed-over are accepted.

    LOCALISATION : booking/tests/test_weekly_opening_overlap.py

    Lundi  : 09:00 → 12:00 (3 × 60 min).
    Mardi  : 09:00 → 12:00 (3 × 60 min).
    Jours différents, pas de débordement → full_clean() ne lève pas d'exception.
    / Monday: 09:00 → 12:00. Tuesday: 09:00 → 12:00. No overlap.
    """
    from booking.models import WeeklyOpening, OpeningEntry

    with schema_context(TENANT_SCHEMA):
        opening = WeeklyOpening.objects.create(
            name=f'{TEST_PREFIX} accepts_different_days_no_overlap',
        )
        try:
            OpeningEntry.objects.create(
                weekly_opening=opening,
                weekday=OpeningEntry.MONDAY,
                start_time=datetime.time(9, 0),
                slot_duration_minutes=60,
                slot_count=3,
            )

            entry_tuesday = OpeningEntry(
                weekly_opening=opening,
                weekday=OpeningEntry.TUESDAY,
                start_time=datetime.time(9, 0),
                slot_duration_minutes=60,
                slot_count=3,
            )
            entry_tuesday.full_clean()

        finally:
            OpeningEntry.objects.filter(
                weekly_opening__name__startswith=TEST_PREFIX,
            ).delete()
            WeeklyOpening.objects.filter(name__startswith=TEST_PREFIX).delete()


@pytest.mark.django_db
def test_slot_entry_rejects_overlap_spanning_whole_week_bleeding_into_wednesday():
    """
    Un entry qui couvre plus d'une semaine complète déborde circulairement
    jusqu'au mercredi — toute autre entry entre en conflit car l'entry A
    couvre la semaine entière.
    / An entry spanning more than a full week wraps circularly into Wednesday —
    every other entry conflicts because entry A covers the entire week.

    LOCALISATION : booking/tests/test_weekly_opening_overlap.py

    Entry A : lundi 02:00, 9 créneaux × 1440 min (= 9 jours).
    Corps principal : [120, 10 080) = lundi 02:00 → fin de semaine.
    Débordement     : [0, 3 000)   = lundi 00:00 → mercredi 02:00.
    Les deux zones couvrent la semaine entière — pas de plage libre.
    Entry B : mercredi 01:00 (2 940 min) — dans le débordement → rejetée.
    / Entry A: Monday 02:00, 9 slots × 1440 min (9 days).
    / Main body [120, 10 080) + bleed [0, 3 000) cover the entire week.
    / Entry B: Wednesday 01:00 (2 940) → inside bleed → rejected.
    """
    from booking.models import WeeklyOpening, OpeningEntry

    with schema_context(TENANT_SCHEMA):
        opening = WeeklyOpening.objects.create(
            name=f'{TEST_PREFIX} whole_week_bleed_into_wednesday',
        )
        try:
            OpeningEntry.objects.create(
                weekly_opening=opening,
                weekday=OpeningEntry.MONDAY,
                start_time=datetime.time(2, 0),
                slot_duration_minutes=1440,
                slot_count=9,
            )

            entry_wednesday_inside_bleed = OpeningEntry(
                weekly_opening=opening,
                weekday=OpeningEntry.WEDNESDAY,
                start_time=datetime.time(1, 0),
                slot_duration_minutes=60,
                slot_count=1,
            )
            with pytest.raises(ValidationError):
                entry_wednesday_inside_bleed.full_clean()

        finally:
            OpeningEntry.objects.filter(
                weekly_opening__name__startswith=TEST_PREFIX,
            ).delete()
            WeeklyOpening.objects.filter(name__startswith=TEST_PREFIX).delete()


@pytest.mark.django_db
def test_slot_entry_rejects_single_entry_total_duration_exceeds_one_week():
    """
    Un seul OpeningEntry dont la durée totale dépasse une semaine est refusé.
    / A single OpeningEntry whose total duration exceeds one week is rejected.

    LOCALISATION : booking/tests/test_weekly_opening_overlap.py

    Règle métier (décisions §9) : la durée totale d'un OpeningEntry
    (slot_duration_minutes × slot_count) ne peut pas dépasser WEEK_MINUTES
    (10 080 min = 7 × 24 × 60). Si elle le dépasse, l'entry « déborde sur
    elle-même » — son dernier slot empiète sur le prochain cycle hebdomadaire
    du même entry, créant un chevauchement logique.
    / Business rule (decisions §9): total duration (slot_duration_minutes ×
    / slot_count) must not exceed WEEK_MINUTES (10 080). If it does, the entry
    / "bleeds into itself" across the weekly cycle.

    Cas de test — timeline (semaine circulaire 0–10 080 min) :
    / Test case — circular week timeline (0–10 080 min):

        lun 00:00       lun 00:00 (fin de semaine)
        |<——————————————————————————————10 081 min——————————————————————————————>|
        |[0                          Entry A (10 081 min)                  10 081)|
                                             ^ dépasse 10 080 → rejeté

    Entry A : lundi 00:00, 1 créneau × 10 081 min.
    10 081 > WEEK_MINUTES (10 080) → full_clean() doit lever ValidationError.
    / Entry A: Monday 00:00, 1 slot × 10 081 min.
    / 10 081 > WEEK_MINUTES → full_clean() must raise ValidationError.

    Note : ceci vérifie la validation au niveau de l'entry isolé — sans
    qu'une autre entry soit présente dans le WeeklyOpening. Le test couvre
    le gap identifié en décisions §9 (la contrainte de chevauchement inter-
    entries ne rejette pas un entry trop long créé seul).
    / Note: this validates the isolated entry — no sibling entry needed.
    / Covers the gap in decisions §9.
    """
    from booking.models import WeeklyOpening, OpeningEntry

    with schema_context(TENANT_SCHEMA):
        opening = WeeklyOpening.objects.create(
            name=f'{TEST_PREFIX} rejects_single_entry_exceeds_one_week',
        )
        try:
            # Durée totale : 1 × 10 081 min > 10 080 min (une semaine exacte)
            # / Total duration: 1 × 10 081 min > 10 080 min (one full week)
            entry_too_long = OpeningEntry(
                weekly_opening=opening,
                weekday=OpeningEntry.MONDAY,
                start_time=datetime.time(0, 0),
                slot_duration_minutes=10081,
                slot_count=1,
            )
            with pytest.raises(ValidationError):
                entry_too_long.full_clean()

        finally:
            OpeningEntry.objects.filter(
                weekly_opening__name__startswith=TEST_PREFIX,
            ).delete()
            WeeklyOpening.objects.filter(name__startswith=TEST_PREFIX).delete()


@pytest.mark.django_db
def test_slot_entry_accepts_entries_touching_at_boundary():
    """
    Deux entries qui se touchent (fin du premier = début du second) sont acceptées.
    / Two entries that touch (end of first = start of second) are accepted.

    LOCALISATION : booking/tests/test_weekly_opening_overlap.py

    Lundi 09:00 → 12:00 (3 × 60 min), puis lundi 12:00 → 14:00 (2 × 60 min).
    Les intervalles sont semi-ouverts [start, end) : 12:00 appartient au second
    entry, pas au premier. Pas de chevauchement → full_clean() ne doit pas lever.
    / Monday 09:00 → 12:00, then Monday 12:00 → 14:00.
    / Intervals are half-open [start, end): 12:00 belongs to the second entry,
    / not the first. No overlap → full_clean() must not raise.
    """
    from booking.models import WeeklyOpening, OpeningEntry

    with schema_context(TENANT_SCHEMA):
        opening = WeeklyOpening.objects.create(
            name=f'{TEST_PREFIX} accepts_touching_boundary',
        )
        try:
            OpeningEntry.objects.create(
                weekly_opening=opening,
                weekday=OpeningEntry.MONDAY,
                start_time=datetime.time(9, 0),
                slot_duration_minutes=60,
                slot_count=3,
            )

            entry_touching = OpeningEntry(
                weekly_opening=opening,
                weekday=OpeningEntry.MONDAY,
                start_time=datetime.time(12, 0),
                slot_duration_minutes=60,
                slot_count=2,
            )
            entry_touching.full_clean()

        finally:
            OpeningEntry.objects.filter(
                weekly_opening__name__startswith=TEST_PREFIX,
            ).delete()
            WeeklyOpening.objects.filter(name__startswith=TEST_PREFIX).delete()
