# TDD Incremental Meta-Plan — `booking` app

**Spec reference:** `booking/doc/tibillet-booking-spec.md`
**Design reference:** `booking/doc/tibillet-booking-logic-design.md`
**Approach:** each session = write tests FIRST, then the minimal code
to make them pass.

> **Convention:** at the end of each session, update this document to
> reflect what was actually implemented (final fields, decisions made,
> deviations from the initial plan). Mark the session `(DONE ✓)` in
> its heading.

--------------------------------------------------------------------------------

## Test location & conventions

### Why `booking/tests/` and not `tests/pytest/`

The existing `tests/pytest/` folder contains all other apps' tests
(crowds, laboutik, etc.) and was built before the project had many
apps. For the `booking` app, we decided to put the tests inside the
app — `booking/tests/` — for the following reasons:

- The app is self-contained: models, views, and tests live together
- Easier to run in isolation: `pytest booking/tests/ -v`
- Follows Django's own convention (`startapp` creates `tests.py`
  inside the app)
- Makes the app easier to extract or redistribute later
- With TDD, a large number of test files will be produced — keeping
  them inside the app avoids polluting the shared `tests/pytest/`
  folder

### Structure

```
booking/
└── tests/
    ├── __init__.py
    ├── conftest.py                    # Re-exports shared fixtures + booking-specific ones
    ├── test_models.py                 # Session 1 — model declarations
    ├── test_weekly_opening_overlap.py  # Session 2 — non-overlap constraint
    ├── test_interval.py               # Session 6b — Interval / BookableInterval unit tests
    ├── test_booking_engine.py         # Sessions 5+6 — moteur O/W/E + validate_new_booking
    ├── test_views_public.py           # Session 7
    ├── test_embed.py                  # Session 8 — embeddable iframe page
    ├── test_slot_picker.py            # Session 9
    ├── test_basket.py                 # Session 10
    ├── test_validate.py               # Session 12
    ├── test_cancel.py                 # Session 13
    └── test_tasks.py                  # Session 14
```

### `booking/tests/conftest.py`

```python
"""
Fixtures for the booking app tests.
/ Fixtures pour les tests de l'app booking.

LOCALISATION : booking/tests/conftest.py

Re-exports shared session fixtures from tests/pytest/conftest.py so
that booking tests have access to the tenant, API client, and admin
user without duplication.
"""
# Re-export shared session fixtures — no duplication
from tests.pytest.conftest import (  # noqa: F401
    tenant, api_client, admin_user, mock_stripe
)
```

### Running tests

```bash
# Booking tests only (fast feedback during TDD)
docker exec lespass_django poetry run pytest booking/tests/ -v

# All tests including booking
docker exec lespass_django poetry run pytest tests/ booking/tests/ -v

# Existing suite only (unchanged)
docker exec lespass_django poetry run pytest tests/pytest/ -q

# Check migrations
docker exec lespass_django poetry run python manage.py \
    makemigrations booking --check

# Django system check
docker exec lespass_django poetry run python manage.py check
```

--------------------------------------------------------------------------------

## Session 0 — App skeleton (DONE ✓)

`booking/` created with `startapp`. Registered in `TENANT_APPS` and
`urls_tenants.py`.

--------------------------------------------------------------------------------

## Session 1 — All booking models (no logic, only simple constraints) (DONE ✓)

Declare all models in the database. No complex business logic yet —
only field-level constraints (required, null/blank, defaults, FK
relationships). The `pricing_rule` FK to TiBillet's `Price` model is
**excluded** here; it will be added in Session 12 when payment
integration is tackled.

**Models declared** (file: `booking/models.py`):

+---------------+------------------------------------------------------+
| Model         | Key fields (as implemented)                          |
+===============+======================================================+
| Resource      | name, group FK nullable, calendar FK, weekly_opening |
|               | FK, capacity (default 1, 0 allowed), tags            |
|               | cancellation_deadline_hours (default 24),            |
|               | booking_horizon_days (default 28)                    |
+---------------+------------------------------------------------------+
| ResourceGroup | name, description, image, tags                       |
+---------------+------------------------------------------------------+
| Calendar      | name                                                 |
+---------------+------------------------------------------------------+
| ClosedPeriod  | calendar FK, start_datetime, end_datetime (nullable) |
|               | label                                                |
+---------------+------------------------------------------------------+
| WeeklyOpening | name                                                 |
+---------------+------------------------------------------------------+
| OpeningEntry  | weekly_opening FK, weekday, start_time,              |
|               | slot_duration_minutes, slot_count                    |
+---------------+------------------------------------------------------+
| Booking       | resource FK, user FK (AUTH_USER_MODEL), start_       |
|               | datetime (timezone-aware), slot_duration_minutes,    |
|               | slot_count, status (new/validated/confirmed),        |
|               | booked_at (auto), payment_ref (nullable)             |
+---------------+------------------------------------------------------+

**Key decisions made during this session:**

- All FKs use `on_delete=PROTECT` (no cascade).
- `start_datetime` is a timezone-aware `DateTimeField` — not a split
  `date` + `time`. TiBillet defines a timezone per tenant; see
  `booking/doc/tibillet-booking-decisions.md`.
- Capacity 0 is allowed — it disables booking without an extra flag.
- The FK to `AUTH_USER_MODEL` is named `user` (not `member`), matching
  TiBillet's own convention throughout the codebase.
- `SlotTemplate` / `SlotEntry` renamed to `WeeklyOpening` /
  `OpeningEntry` in models, tests, spec, and plan.

**Tests kept** (`booking/tests/test_models.py`):

- `test_booking_default_status_is_new` — the `new` status has
  important business semantics (basket, not yet confirmed).

**Tests discarded** (tested only Django internals, not business rules):
`test_resource_group_is_optional`, `test_closed_period_end_date_is_
nullable`, `test_resource_capacity_defaults_to_1`, `test_booking_
payment_ref_is_nullable`, and similar default/null checks.

**Migration:** `booking/migrations/0001_initial.py` applied to all
tenant schemas.

--------------------------------------------------------------------------------

## Session 2 — Complex database constraint: WeeklyOpening non-overlap (DONE ✓)

Design and implement the non-overlap validation for OpeningEntry within
a WeeklyOpening. This is the most complex rule in the spec (circular
7-day timeline, bleed-over into next day, wrap-around Sunday→Monday).

### Session 2.1 — Red phase (DONE ✓)

**Files created:**
- `booking/tests/test_weekly_opening_overlap.py`

**Tests written (final list — deviations from initial plan noted):**
```
test_slot_entry_accepts_non_overlapping_entries_same_day
test_slot_entry_rejects_overlap_same_day
test_slot_entry_rejects_overlap_bleeding_into_next_day
test_slot_entry_rejects_circular_overlap_sunday_to_monday
test_slot_entry_accepts_entries_on_different_days_no_overlap
test_slot_entry_rejects_overlap_spanning_whole_week_bleeding_into_wednesday
test_slot_entry_accepts_entries_touching_at_boundary
```

**Deviations from initial plan:**

- `test_slot_entry_overlap_check_treats_week_as_circular` dropped — it
  was a duplicate of `test_slot_entry_rejects_circular_overlap_sunday_to_monday`
  (same concept, different numbers).
- Two tests added during review:
  - `test_slot_entry_rejects_overlap_spanning_whole_week_bleeding_into_wednesday`
    — entry spanning 9 days from Monday; covers entire week + bleed.
    Note: such an entry (duration > WEEK_MINUTES) covers the whole week,
    so every sibling conflicts. No gap exists — the "after bleed, accepted"
    sub-case that was initially drafted was removed once the math confirmed
    it was wrong.
  - `test_slot_entry_accepts_entries_touching_at_boundary` — guards against
    off-by-one in the overlap check (intervals are half-open `[start, end)`).

### Session 2.2 — Green phase (DONE ✓)

**Files modified:**
- `booking/models.py`

**Key decisions made during this session:**

- Overlap logic extracted into a module-level pure function
  `_intervals_overlap(a_start, a_end, b_start, b_end)` — easier to
  unit-test independently if needed.
- `WEEK_MINUTES = 7 * 24 * 60` constant defined at module level.
- Validation in `OpeningEntry.clean()` (not `save()`) — Django's
  standard validation hook; called explicitly via `full_clean()`.
- Guard `if not self.weekly_opening_id: return` — prevents crash when
  `clean()` is called on an incomplete form before FK validation runs.
- Three overlap cases handled: (1) direct linear, (2) self bleeds past
  end of week, (3) sibling bleeds past end of week.
- All 7 tests pass; Session 1 test unaffected (8/8 green).

--------------------------------------------------------------------------------

## Session 3 — Add fixtures in the lespass tenant (DONE ✓)

Create realistic demo data in the lespass tenant. This data serves as a
manual verification baseline for the admin panel (Session 4) and is
available in all subsequent sessions.

**Deviation from initial plan:** no TDD cycle — fixture data creation
doesn't warrant tests. Implemented as a management command called
automatically by `demo_data_v2` (and therefore by `flush.sh`).

**Files created:**
- `booking/management/__init__.py` (empty)
- `booking/management/commands/__init__.py` (empty)
- `booking/management/commands/create_booking_fixtures.py`

**File modified:**
- `Administration/management/commands/demo_data_v2.py` — section 5
  added at the end: calls `create_booking_fixtures` per tenant inside
  `tenant_context`.

**Fixtures created (idempotent — get_or_create / update_or_create):**

+------------------------------+------------------------------------------+
| Object                       | Details                                  |
+==============================+==========================================+
| Calendar "Calendrier 2026"   | 11 French public holidays (single-day),  |
|                              | summer closure Jul 1 – Aug 31,           |
|                              | end-of-year closure Dec 21 – Jan 2       |
+------------------------------+------------------------------------------+
| WeeklyOpening                | Mon–Fri, 8 × 60 min from 09:00           |
| "Coworking weekdays"         |                                          |
+------------------------------+------------------------------------------+
| WeeklyOpening                | Sat + Sun, 3 × 180 min from 10:00        |
| "Salles de répét' weekend"   |                                          |
+------------------------------+------------------------------------------+
| Resource "Coworking"         | capacity 3, no group, weekday opening    |
+------------------------------+------------------------------------------+
| Resource "Imprimante 3D"     | capacity 1, no group, weekday opening    |
+------------------------------+------------------------------------------+
| ResourceGroup                | —                                        |
| "Salle de répét'"            |                                          |
+------------------------------+------------------------------------------+
| Resource "Petite salle"      | capacity 1, group Salle de répét',       |
|                              | weekend opening                          |
+------------------------------+------------------------------------------+
| Resource "Grande salle"      | capacity 1, group Salle de répét',       |
|                              | weekend opening                          |
+------------------------------+------------------------------------------+

**Key decisions:**
- "Imprimante 3D" resource added (capacity 1, same opening as Coworking).
- End-of-year closure starts Dec 21 (not Dec 24 as initially planned).
- Command relies on caller's tenant context — no internal schema switch.
- `update_or_create` used for Resources (repairs broken FKs on re-run);
  `get_or_create` used for all other objects.

--------------------------------------------------------------------------------

## Session 4 — Django admin panel (DONE ✓)

Add the admin panel early so that the fixtures from Session 3 are
visible and manually verifiable in the backoffice throughout
development.

**Admin registrations as implemented:**

+---------------+------------+--------------------------------------+
| Model         | Admin type | Inline children / extras             |
+===============+============+======================================+
| ResourceGroup | ModelAdmin | Resource as TabularInline            |
+---------------+------------+--------------------------------------+
| Calendar      | ModelAdmin | ClosedPeriod as TabularInline        |
+---------------+------------+--------------------------------------+
| WeeklyOpening | ModelAdmin | OpeningEntry as TabularInline        |
+---------------+------------+--------------------------------------+
| Resource      | ModelAdmin | list_display with 5 columns          |
+---------------+------------+--------------------------------------+
| Booking       | ModelAdmin | filterable by date and status        |
+---------------+------------+--------------------------------------+

**Files created / modified:**

- `booking/tests/test_admin.py` — 5 tests
- `booking/tests/conftest.py` — added `admin_client` fixture
- `booking/admin.py` — registrations on `staff_admin_site` (Unfold)
- `Administration/admin_tenant.py` — imports `booking.admin`
- `Administration/admin/dashboard.py` — booking section in sidebar,
  conditional on `configuration.module_booking`
- `BaseBillet/models.py` — added `module_booking` BooleanField
- `BaseBillet/migrations/0208_module_booking.py` — migration

**Deviations from plan:**

- The project uses a custom `staff_admin_site` (Unfold), not
  `admin.site` — all registrations use `@admin.register(site=...)`.
- `ClosedPeriod` uses `TabularInline` instead of `StackedInline` —
  13 entries were too tall with StackedInline.
- `ResourceGroup` shows its `Resource` children as a TabularInline.
- `Resource` has `list_display` for a tabular changelist view.
- `tags` field excluded from admin on both Resource and ResourceGroup
  (JSONField textarea unusable — see decisions doc §4).
- Booking section in sidebar gated on `module_booking` flag, added to
  `Configuration` model and dashboard toggle cards.
- `ClosedPeriod.end_date` help_text updated to document the
  single-day / multi-day / endless convention.
- French translations pending — PO file has upstream merge conflicts
  (see decisions doc §5).

--------------------------------------------------------------------------------

## Session 5 — Slot computation engine (pure Python, independent file) (DONE ✓)

The algorithm lives in `booking/slot_engine.py`. It is broken down
into simple, independently testable functions.

**Files created / modified:**

- `booking/slot_engine.py` — engine implementation
- `booking/tests/test_slot_engine.py` — 35 tests
- `booking/doc/tibillet-booking-spec.md` — v0.4 → v0.5
- `booking/doc/tibillet-booking-decisions.md` — §7, §8, §9 added
- `booking/tests/test_weekly_opening_overlap.py` — §9 test added (skipped)

**Functions as implemented:**

```python
def get_closed_dates_for_resource(resource, date_from, date_to) -> set[date]
def get_opening_entries_for_resource(resource) -> QuerySet
def get_existing_bookings_for_resource(resource, date_from, date_to) -> QuerySet
def generate_theoretical_slots(resource_id, opening_entries, date_from, date_to, closed_dates) -> list[Slot]
def compute_remaining_capacity(slot, capacity, existing_bookings) -> int
def compute_slots(resource, date_from, date_to) -> list[Slot]
```

Internal helper (not exported):

```python
def _slot_intersects_closed_date(start_dt, end_dt, closed_dates) -> bool
```

**Key decisions made during this session:**

- Closure check is **per slot**, not per entry (decisions §7). The original
  plan had `if current_date not in closed_dates` as an outer guard — this
  was wrong: an entry whose start day is closed can still produce slots
  whose `start_datetime` falls on a later open day (bleed-over). Guard
  removed; `_slot_intersects_closed_date` is called for each slot instead.

- **Half-open interval** for date intersection: `(end_dt − 1 µs).date()`
  is used as the last checked day. A slot ending exactly at midnight
  (00:00:00 of the next day) does NOT intersect that next day — it ends
  at the boundary with zero duration there. A slot ending at 00:30 of the
  next day does intersect it and is excluded if that day is closed.

- **timedelta arithmetic** for slot start computation — not `hours // 60`.
  `slot_start_minutes = i × slot_duration_minutes` can exceed 1439 for
  large slot counts (e.g. 7 × 1440 min → slot[6] starts at 8640 min).
  `datetime(y, m, d, 144, 0)` raises `ValueError`; `timedelta` addition
  handles it correctly.

- `compute_remaining_capacity` parameter named `capacity` (not
  `resource_capacity`) — matches the call sites in the tests.

**Tests written (final list — 35 total):**

```
# get_closed_dates_for_resource (4)
test_get_closed_dates_returns_all_dates_in_closed_period
test_get_closed_dates_handles_single_day_period
test_get_closed_dates_handles_null_end_date
test_get_closed_dates_ignores_period_outside_range

# generate_theoretical_slots (13)
test_generate_theoretical_slots_from_weekday_template
test_generate_theoretical_slots_excludes_closed_dates
test_generate_theoretical_slots_respects_booking_horizon
test_generate_theoretical_slots_start_on_closed_day_bleed_into_open_day_is_excluded
test_generate_theoretical_slots_last_slot_bleeds_onto_open_day_is_returned
test_generate_theoretical_slots_bleed_into_closed_day_start_date_is_open
test_generate_theoretical_slots_multi_day_slot_all_open_days_is_returned
test_generate_theoretical_slots_multi_day_spanning_entry
test_generate_theoretical_slots_three_day_slot_with_closed_middle_day_is_excluded
# full-week opening (7 entries × 24 × 60 min):
test_full_week_opening_no_closed_day_returns_168_slots
test_full_week_opening_wednesday_closed_returns_144_slots
test_full_week_opening_monday_closed_returns_144_slots
test_full_week_opening_sunday_closed_returns_144_slots
test_full_week_opening_two_non_adjacent_days_closed_returns_120_slots
# 1 entry × 7 slots of 1 day (1440 min):
test_one_day_slots_opening_no_closed_day_returns_7_slots
test_one_day_slots_opening_wednesday_closed_returns_6_slots
test_one_day_slots_opening_monday_closed_returns_6_slots  ← verifies per-slot check
test_one_day_slots_opening_sunday_closed_returns_6_slots
test_one_day_slots_opening_two_non_adjacent_days_closed_returns_5_slots
# 1 entry × 1 slot of 1 week (10 080 min = WEEK_MINUTES):
test_one_week_slot_opening_no_closed_day_returns_1_slot
test_one_week_slot_opening_wednesday_closed_returns_0_slots
test_one_week_slot_opening_monday_closed_returns_0_slots
test_one_week_slot_opening_sunday_closed_returns_0_slots

# compute_remaining_capacity (3)
test_compute_remaining_capacity_with_no_bookings_equals_capacity
test_compute_remaining_capacity_decreases_with_overlapping_booking
test_compute_remaining_capacity_zero_when_all_units_taken

# compute_slots end-to-end (5)
test_compute_slots_booking_count_gt_1_overlaps_multiple_slots
test_compute_slots_booking_partial_overlap_counts_as_full_overlap
test_compute_slots_returns_empty_when_no_template
test_compute_slots_end_to_end_with_fixture_coworking_resource
test_compute_slots_end_to_end_with_fixture_petite_salle
```

**Deviations from initial plan:**

- 14 tests planned → 35 tests written. The extra tests cover bleed-over
  edge cases, multi-day slots, full-week openings, and the maximum slot
  size (WEEK_MINUTES), all of which were added during the red phase review.
- `generate_theoretical_slots` receives `resource_id` as first argument
  (needed to populate `Slot.resource_id`); not in the original signature.
- A private helper `_slot_intersects_closed_date` was extracted to keep
  the per-slot date-range check readable.
- The spec was updated (v0.5) and decisions §7/§8/§9 were added during
  the red phase.
- Test for §9 (`OpeningEntry` total duration > WEEK_MINUTES raises on
  `full_clean()`) written in `test_weekly_opening_overlap.py` but marked
  `@pytest.mark.skip` — the `clean()` check is not yet implemented.

--------------------------------------------------------------------------------

## Session 5b — Model constraints (DONE ✓)

**decision §8 — ClosedPeriod: end_date ≥ start_date (DONE ✓)**

- `ClosedPeriod.clean()` raises `ValidationError` if `end_date < start_date`.
- `Meta.constraints` adds a `CheckConstraint` for DB-level enforcement.
- Migration `0002_closed_period_end_date_constraint.py` applied.
- 3 tests added to `test_models.py` (reject / equal / null).

**decision §9 — OpeningEntry: slot_duration_minutes × slot_count ≤ WEEK_MINUTES (DONE ✓)**

Check added to `OpeningEntry.clean()` before the overlap check. No migration
needed. Test `test_slot_entry_rejects_single_entry_total_duration_exceeds_one_week`
unskipped and passing.

--------------------------------------------------------------------------------

## Session 6 — Booking validation logic (DONE ✓)

Reuse the slot computation engine to validate a new booking request
before creating the Booking row. Called by the "add to basket" view
(Session 10).

**Function signature as implemented:**

```python
def validate_new_booking(resource, start_datetime, slot_duration_minutes,
                         slot_count, member):
    """Returns (is_valid: bool, error: str | None)."""
```

`date + start_time` replaced by `start_datetime` (timezone-aware,
decisions §2). `slot_duration_minutes` added — required to look up
slots by `(start_datetime, slot_duration_minutes)`.

**Files created:**
- `booking/tests/test_booking_validation.py` — 12 tests
- `booking/booking_validator.py`

**Tests (12):**
```
test_validate_booking_accepts_valid_slot
test_validate_booking_rejects_slot_beyond_horizon
test_validate_booking_rejects_slot_in_closed_period
test_validate_booking_rejects_full_slot
test_validate_booking_slot_count_gt_1_all_slots_must_be_available
test_validate_booking_slot_count_gt_1_fails_if_one_slot_full
test_validate_booking_slot_count_gt_1_fails_if_one_slot_in_closed_period
test_validate_booking_rejects_mismatched_slot_duration
test_validate_booking_rejects_start_time_not_aligned_to_opening
test_validate_booking_slot_count_gt_1_rejects_if_series_exceeds_opening
test_validate_booking_accepts_slot_bleeding_into_next_open_day
test_validate_booking_rejects_slot_bleeding_into_closed_next_day
```

Tests 8–10 enforce the alignment rule: every slot in the requested
series must match exactly a theoretical slot
`(start_datetime, slot_duration_minutes)` from `compute_slots`.

Tests 11–12 cover bleed-over: a slot starting late at night and ending
the next day must be rejected if the next day is closed.

**Implementation strategy:**

`validate_new_booking` calls `compute_slots(resource, date_from,
date_to)` and builds a lookup dict
`{(start_datetime, slot_duration_minutes): Slot}`. Every slot in the
series is checked the same way — no special case for the first slot:

1. Slot present in the lookup → aligned to opening, not closed, within
   horizon (absent = any of these failures). `compute_slots` already
   enforces the horizon; a slot beyond it is simply absent.
2. `remaining_capacity > 0` → not fully booked.

**`date_to` computation — covers bleed-over:**

```python
last_slot_end_dt = start_datetime + timedelta(
    minutes=slot_duration_minutes * slot_count
)
date_to = (last_slot_end_dt - timedelta(microseconds=1)).date()
```

`date_to` is the last day actually occupied by the whole requested
period, using `(end − 1 µs).date()` — consistent with
`_slot_intersects_closed_date`. A period ending exactly at midnight
does not occupy the next day. Using `last_slot_start_dt.date()` as
`date_to` would omit next-day closed periods from the lookup,
silently allowing bleed-over slots into closed days.

--------------------------------------------------------------------------------

## Session 6b — Refactoring booking logic (DONE ✓)

The human had intuition about several issues:

1. As stated in §2, datetimes in database are timezone-aware but dates in
   Calendar are not. In a tenant at UTC+10 this matters significantly.
2. A better data model was needed for slot creation and booking validation.
   The core abstraction is the half-open time interval [a, b). Open days of
   a venue can be normalized into a disjoint series of open-ended intervals.
   A bookable slot is such an interval with capacity metadata.

### Phase 1 — Pair design session (DONE ✓)

A pair design session (human + AI) produced the design document
`booking/doc/tibillet-booking-logic-design.md`.

Key decisions made:

- `Slot` dataclass dropped in favour of two new classes: `Interval`
  (pure, frozen, hashable half-open time interval) and `BookableInterval`
  (`Interval` + `max_capacity` + `remaining_capacity`, composed not
  inherited).
- Open time modelled as three sets: **O** (normalized open-day intervals
  from `Calendar`), **W** (weekly opening intervals from `WeeklyOpening`),
  **E** = `{ w ∈ W | ∃ o ∈ O, w ⊆ o }` (bookable intervals — containment,
  not clipping).
- A member booking is a series **B** of consecutive intervals, all from
  the same `e ∈ E`, each with `remaining_capacity > 0`.
- `remaining_capacity` counts all DB bookings that overlap the interval,
  regardless of alignment (volunteer bookings included).
- Spec ambiguity §5 ("bookings not required to be aligned") applies only
  to volunteer/admin bookings, not member bookings. Recorded as finding §11.

### Phase 2 — Inner red/green TDD cycle on new classes (DONE ✓)

**Inner TDD cycle** for `Interval` and `BookableInterval` only:

- Skeleton classes added to `booking/slot_engine.py` with
  `NotImplementedError` stubs.
- `booking/tests/test_interval.py` created — 23 pure unit tests (no DB)
  covering `overlaps()`, `contains()`, `duration_minutes()` boundary
  cases and `BookableInterval` property delegation.
- Methods implemented (one-liners). All 23 tests pass.

**Integration tests rewritten** (`test_slot_engine.py`) to use the new
API:

- `slot.start_datetime` → `slot.start`
- `slot.end_datetime` → `slot.end`
- `slot.slot_duration_minutes` (assertions) → `slot.duration_minutes()`
- `Slot(...)` constructors → `BookableInterval(interval=Interval(...), ...)`
- `resource_id` parameter removed from `generate_theoretical_slots` calls

At this stage: 20 tests were RED (implementation still returned `Slot`),
23 unit tests GREEN, 10 booking-validation tests GREEN.

### Phase 3 — Green phase (DONE ✓)

**`booking/slot_engine.py`** rewritten:

- `Slot` class removed.
- `generate_theoretical_slots` — `resource_id` parameter dropped, returns
  `list[BookableInterval]` (`max_capacity=0, remaining_capacity=0`
  at generation time, filled by `compute_slots`).
- `compute_remaining_capacity` — accepts `BookableInterval`, uses
  `slot.interval.overlaps(booking_interval)` (constructs an `Interval`
  for each DB booking and delegates to `Interval.overlaps`).
- `compute_slots` — timezone bug fixed: `datetime.date.today()` →
  `timezone.localdate()`; sets `max_capacity` and `remaining_capacity`
  on each `BookableInterval`.

**`booking/booking_validator.py`** — dict key updated from
`(slot.start_datetime, slot.slot_duration_minutes)` to
`(slot.start, slot.duration_minutes())`.

Final result: **70/70 tests pass** (23 unit + 30 slot-engine integration +
10 booking-validation + 7 pre-existing model/overlap tests).

### Session 6c — Test catalogue (DONE ✓)

A pair design session (human + AI) produced a formal test catalogue
`booking/doc/tibillet-booking-test-cases.md`.

**Motivation:** the existing test files are correct but the business
rules they verify are implicit — buried in docstrings and scattered
`assert` calls. The catalogue makes every test case a self-contained,
readable specification.

**Notation:** pseudo-Haskell functional syntax. Each test is a
derivation chain expressed with five core functions:

```
open-day           :: Date → Date → Timezone → Calendar → [Interval]
theoretical-slots  :: WeeklyOpening → [Interval] → [Interval]
expand             :: Booking → [Interval]
bookable-intervals :: [Interval] → Int → [Interval] → [BookableInterval]
validate_new_booking :: Resource → DateTime → Int → Int → User
                      → (Bool, Str | None)
```

The derivation chain `cal → O → W → B → E → validate` is explicit in
every test. Intermediate `assert` steps show why the final result holds,
making the containment rule (`w ⊆ o`) and capacity arithmetic visible
without reading the implementation.

**Coverage:** all 48 tests from `test_slot_engine.py` and
`test_booking_validation.py` are documented.

**Findings recorded during this session:**

- §12 — two tests in `test_slot_engine.py` depend on database fixtures
  (`"Coworking"`, `"Petite salle"`) instead of inline data. TODO warnings
  added in both the test file and the catalogue.
- §13 — clock injection pattern identified for `compute_slots` and
  `validate_new_booking`: adding an optional `reference_date` parameter
  would allow all validation tests to use fixed dates instead of
  `next_weekday`.

### Session 6d — Fix §12 et §13 (DONE ✓)

Corrections des deux findings identifiés en session 6c.

**§12 — Suppression de la dépendance aux fixtures de base de données.**

Les deux tests de bout en bout dans `test_slot_engine.py` interrogeaient
des objets `Calendar` et `WeeklyOpening` nommés `"Coworking"` et
`"Petite salle"` supposés présents en base. Ils étaient silencieusement
ignorés si ces fixtures étaient absentes.

Correction : réécriture des deux tests avec des données inline créées
par les helpers `_make_*` existants. Le helper `_add_opening_entry` (absent
de `test_slot_engine.py`) a été ajouté au fichier. Les `pytest.skip` ont
été supprimés.

**§13 — Clock injection dans `compute_slots` et `validate_new_booking`.**

`compute_slots` appelait `timezone.localdate()` en interne, forçant tous
les tests de `test_booking_validation.py` à calculer des dates relatives
via `_next_weekday()`. Cela rendait les tests non-déterministes et
difficiles à lire.

Correction :
- `compute_slots(resource, date_from, date_to, reference_date=None)` —
  `reference_date or timezone.localdate()` remplace l'appel direct.
- `validate_new_booking(..., reference_date=None)` — le paramètre est
  propagé jusqu'à `compute_slots`.
- Les 12 tests de `test_booking_validation.py` remplacent
  `_next_weekday()` par les constantes fixes `MONDAY_NEAR = 2026-06-08`
  et `MONDAY_FAR = 2026-06-15` (anchor `REFERENCE_DATE = 2026-06-01`).
- Le catalogue `tibillet-booking-test-cases.md` est mis à jour : dates
  fixes dans toute la section `validate_new_booking`, données inline pour
  les deux tests de bout en bout.

**Résultat :** 47/47 tests passent, aucun `pytest.skip`, aucun appel à
`_next_weekday` dans `test_booking_validation.py`.

### Session 6e — Réécriture du moteur et consolidation des fichiers (DONE ✓)

Travail réalisé en pair-programming (humain + IA) à partir de la
spécification §3.2 (v0.6) et du finding §14.

**Réécriture de `slot_engine.py` → `booking_engine.py`.**

La version précédente implémentait O et W de façon implicite : elle
calculait les intervalles fermés et vérifiait que les créneaux ne les
chevauchaient pas. La nouvelle version suit littéralement §3.2 :

- **O** — nouvelle fonction pure `compute_open_intervals(closed_periods,
  date_from, date_to, tz)` : calcule le complémentaire des `ClosedPeriod`
  fusionnées (nouvelle fonction `merge_intervals`). Prend `tz` en
  paramètre au lieu de lire `timezone.get_current_timezone()` en interne
  — testable sans base de données.
- **W** — `generate_theoretical_slots` utilise désormais
  `Interval.contains()` sur les intervalles ouverts O (règle
  `w ∈ W ⟺ ∃ o ∈ O, w ⊆ o`) au lieu de `overlaps()` sur les intervalles
  fermés. Prend `open_intervals` et `tz` en paramètres.
- **E** — `get_existing_bookings_for_resource` filtre explicitement sur
  `status__in=[new, validated, confirmed]` (spec §3.2.3). La nouvelle
  fonction `get_closed_periods_for_resource` remplace l'ancienne
  `get_closed_intervals_for_resource`.
- **B + §14** — `validate_new_booking` intègre désormais la création
  atomique en deux étapes : pré-validation rapide (non atomique) puis
  `transaction.atomic()` avec `Resource.objects.select_for_update()`.
  Le verrou sur la ligne `Resource` sérialise les créations concurrentes
  et élimine la race condition décrite en §14.

**Consolidation des fichiers.**

- `booking_validator.py` supprimé : `validate_new_booking` est désormais
  une fonction directe dans `booking_engine.py` (plus de wrapper).
- `slot_engine.py` renommé `booking_engine.py` (le mot « slot » n'est
  plus le terme structurant de la spec v0.6).
- `test_slot_engine.py` renommé `test_booking_engine.py`.
- `test_booking_validation.py` fusionné dans `test_booking_engine.py` :
  constantes `REFERENCE_DATE`/`MONDAY_NEAR`/`MONDAY_FAR`, helpers
  `_get_test_user`, `_make_aware_dt`, `_add_closed_period`, `_add_booking`
  et les 12 tests de validation ajoutés au fichier unifié. Le helper
  inutilisé `_next_weekday` (référençait une variable `TODAY` non définie)
  a été supprimé.

**Refactoring des tests — finding §10 (tests unitaires purs).**

Suite à la mise à jour de `tibillet-booking-test-cases.md` et à la
réécriture de `booking_engine.py`, `test_booking_engine.py` a été
entièrement réécrit pour appliquer §10 (stratégie mixte).

- **Tests unitaires purs** (sans `@pytest.mark.django_db`, sans
  `schema_context`) pour les fonctions algorithmiquement pures :
  `compute_open_intervals`, `generate_theoretical_slots`,
  `compute_remaining_capacity`. Ces tests utilisent `types.SimpleNamespace`
  (`_cp`, `_oe`, `_bk`) et `zoneinfo.ZoneInfo('Europe/Paris')` — aucun
  accès base de données.
- **Tests d'intégration** conservés pour les orchestrateurs DB :
  `compute_slots` et `validate_new_booking`.
- Corrections d'API : les anciens tests passaient `closed_intervals=...`
  (keyword inexistant) à `generate_theoretical_slots` → `TypeError`.
  Remplacés par le flux correct : `compute_open_intervals → O →
  generate_theoretical_slots(open_intervals=O)`.
- `test_get_closed_intervals_*` (signature erronée sur 3 args) remplacés
  par `test_compute_open_intervals_*` qui appellent la bonne fonction.
- Hack `booking_horizon_days = 99999` remplacé par
  `reference_date=datetime.date(2026, 6, 1)` (clock injection §13).

**Résultat : 47 tests, 0 échec.**

**Structure du test après consolidation :**

```
booking/tests/
    test_booking_engine.py   # moteur O/W/E + validate_new_booking (B)
    test_interval.py         # tests unitaires purs Interval/BookableInterval
    test_timezone_slots.py   # cas fuseau horaire
    test_models.py
    test_weekly_opening_overlap.py
```

--------------------------------------------------------------------------------

## Session 7 — Public view: resource list + available slots (DONE ✓)

### Session 7.1 — Red phase

**Files created:**
- `booking/tests/test_views_public.py`

**Tests written (7 — 5 initial + 2 added for ResourceGroup in same session):**
```
test_resource_list_accessible_without_authentication
test_resource_list_returns_html_200
test_resource_list_filters_by_tag
test_resource_with_no_availability_appears_greyed_out
test_full_slot_appears_as_unavailable
test_group_name_appears_as_heading
test_ungrouped_resource_appears_individually
```

### Session 7.2 — Green phase

**Files created / modified:**
- `booking/views.py` — `BookingViewSet.list()`; no serializer needed
  (server-rendered HTML, no JSON API)
- `booking/templates/booking/views/list.html`
- `booking/templates/booking/partial/card.html`

ResourceGroup display (spec §3.1.2) implemented in the same session:
resources split into `groupes_annotes` + `items_sans_groupe`; ungrouped
section gets a `<hr>` separator and "Autres ressources" heading when
both zones are present.

--------------------------------------------------------------------------------

## Session 8 — Embeddable iframe page (DONE ✓)

The public booking page must be embeddable as an `<iframe>` on
external sites (spec section 4.4). This requires a dedicated route
that renders the booking page without the TiBillet site chrome
(navigation, header, footer) and with HTTP headers that allow
embedding. Tag filtering via URL parameter must also work inside
the embed.

### Session 8.1 — Red phase

**Files created:**
- `booking/tests/test_embed.py`

**Tests written (3 — business logic already covered by Session 7):**
```
test_embed_page_accessible_without_authentication
test_embed_page_response_allows_iframe_embedding
test_embed_page_has_no_site_navigation_chrome
```

### Session 8.2 — Green phase

**Files created / modified:**
- `booking/views.py` — `_annote_ressources()` helper extracted;
  `list()` simplified; `BookingViewSet.embed()` (@action GET) added
- `booking/templates/booking/embed_base.html` — minimal full HTML
  document (Bootstrap CSS, no chrome); used as `base_template`
  override so `list.html` is reused unchanged

`booking/urls.py` — no change; DefaultRouter auto-registers the
`@action` route at `/booking/embed/`.

`X-Frame-Options: ALLOWALL` set directly on the response.

--------------------------------------------------------------------------------

## Session 9 — Resource detail page (full slot list) (DONE ✓)

Spec §4.1 step 3 : after browsing the list, the member selects a slot on the
resource detail page. The list card shows only the first 5 slots; the detail
page shows all slots within `booking_horizon_days` and will carry the "add to
basket" button (Session 10).

Same pattern as Session 7: `retrieve()` returns a full server-rendered page,
navigated to via HTMX anti-blink link from each card. No separate `@action`
needed — the DefaultRouter already maps `GET /booking/<pk>/` to `retrieve()`.

### Session 9.1 — Red phase

**Files created:**
- `booking/tests/test_views_detail.py`

**Tests written (5):**
```
test_resource_detail_accessible_without_authentication
test_resource_detail_returns_404_for_unknown_resource
test_resource_detail_shows_resource_name
test_resource_detail_shows_all_slots_within_horizon
test_resource_detail_marks_full_slots_as_unavailable
```

### Session 9.2 — Green phase

**Files created / modified:**
- `booking/views.py` — `retrieve()` stub replaced; `get_object_or_404`
  added to imports; calls `compute_slots(ressource)` with no date args
- `booking/templates/booking/views/detail.html` — full page: image, name,
  description, tags, all slots (no `|slice`); `mx-md-4 mx-lg-5` on slot
  list for horizontal inset on large screens; HTMX back-link to `/booking/`
- `booking/templates/booking/partial/card.html` — resource name wrapped in
  HTMX anti-blink link to `/booking/<pk>/`

`booking/urls.py` — no change; DefaultRouter already routes
`GET /booking/<pk>/` to `retrieve()`.

--------------------------------------------------------------------------------

## Session 10 — Add to basket (authenticated member)

### Session 10.1 — Red phase

**Files to create:**
- `booking/tests/test_basket.py`

**Tests to write:**
```
test_add_to_basket_creates_booking_with_status_new
test_add_to_basket_rejects_unauthenticated_user
test_add_to_basket_rejects_full_slot
test_add_to_basket_rejects_slot_beyond_horizon
test_add_to_basket_rejects_slot_in_closed_period
test_add_to_basket_slot_count_gt_1_checks_all_slots
```

### Session 10.2 — Green phase

> ⚠️ **AI stops here.** The human reviews the tests, completes or
> adjusts them if needed, and confirms before proceeding to the green
> phase.

**Files to create / modify:**
- `booking/views.py` — `BookingViewSet.add_to_basket()` (@action POST)
- `booking/serializers.py` — `BookingCreateSerializer`
- `booking/templates/booking/partial/basket.html`

Write the minimal view, serializer, and template to make all
red-phase tests pass.

--------------------------------------------------------------------------------

## Session 11 — Member booking list (authenticated member dashboard)

The page where a member sees their upcoming confirmed bookings and
accesses cancellation. Referenced in spec section 4.2 ("Member views
their upcoming confirmed bookings in their TiBillet account
dashboard").

### Session 11.1 — Red phase

**Files to create:**
- `booking/tests/test_views_member.py`

**Tests to write:**
```
test_my_bookings_requires_authentication
test_my_bookings_shows_only_confirmed_bookings
test_my_bookings_does_not_show_other_members_bookings
test_my_bookings_shows_cancellation_button_before_deadline
test_my_bookings_hides_cancellation_button_after_deadline
test_my_bookings_excludes_past_bookings
```

### Session 11.2 — Green phase

> ⚠️ **AI stops here.** The human reviews the tests, completes or
> adjusts them if needed, and confirms before proceeding to the green
> phase.

**Files to create / modify:**
- `booking/views.py` — `BookingViewSet.my_bookings()` (@action GET)
- `booking/templates/booking/views/my_bookings.html`
- `booking/templates/booking/partial/booking_row.html`

Write the minimal view and templates to make all red-phase tests pass.

--------------------------------------------------------------------------------

## Session 12 — Basket validation + payment (TiBillet Price integration)

This is where the `pricing_rule` FK on Resource is added, pointing to
TiBillet's existing `Price` model. Resolve the open question in the
spec (correct `categorie_article` value) with the core team before
implementing this session.

### Session 12.1 — Red phase

**Files to create:**
- `booking/tests/test_validate.py`

**Tests to write:**
```
test_validate_basket_free_slot_goes_directly_to_confirmed
test_validate_basket_paid_slot_moves_to_validated
test_validate_basket_insufficient_payment_deletes_bookings
test_validate_empty_basket_returns_error
```

### Session 12.2 — Green phase

> ⚠️ **AI stops here.** The human reviews the tests, completes or
> adjusts them if needed, and confirms before proceeding to the green
> phase.

**Files to create / modify:**
- `booking/models.py` — add `pricing_rule = FK(Price)` on Resource
- `booking/migrations/` — migration for the new FK
- `booking/views.py` — `BookingViewSet.validate_basket()` (@action POST)

Write the minimal payment integration logic to make all red-phase
tests pass.

--------------------------------------------------------------------------------

## Session 13 — Cancellation

### Session 13.1 — Red phase

**Files to create:**
- `booking/tests/test_cancel.py`

**Tests to write:**
```
test_cancel_before_deadline_deletes_booking
test_cancel_after_deadline_returns_error_with_deadline_info
test_cancel_refunds_wallet_payment
test_cancel_rejects_booking_owned_by_another_member
```

### Session 13.2 — Green phase

> ⚠️ **AI stops here.** The human reviews the tests, completes or
> adjusts them if needed, and confirms before proceeding to the green
> phase.

**Files to create / modify:**
- `booking/views.py` — `BookingViewSet.cancel()` (@action POST)

Write the minimal cancellation logic to make all red-phase tests pass.

--------------------------------------------------------------------------------

## Session 14 — Celery task: basket expiry

### Session 14.1 — Red phase

**Files to create:**
- `booking/tests/test_tasks.py`

**Tests to write:**
```
test_expire_new_bookings_deletes_new_booking_after_timeout
test_expire_new_bookings_keeps_validated_booking
test_expire_new_bookings_keeps_confirmed_booking
test_expire_new_bookings_does_not_delete_before_timeout
```

### Session 14.2 — Green phase

> ⚠️ **AI stops here.** The human reviews the tests, completes or
> adjusts them if needed, and confirms before proceeding to the green
> phase.

**Files to create / modify:**
- `booking/tasks.py` — `expire_new_bookings_task()`

Write the minimal Celery task to make all red-phase tests pass.
