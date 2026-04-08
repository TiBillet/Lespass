# TDD Incremental Meta-Plan — `booking` app

**Spec reference:** `booking/doc/tibillet-booking-spec.md`
**Approach:** each session = write tests FIRST, then the minimal code
to make them pass.

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
    ├── test_slot_template_overlap.py  # Session 2 — non-overlap constraint
    ├── test_slot_engine.py            # Session 5 — slot computation
    ├── test_booking_validation.py     # Session 6 — new booking validation
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

## Session 1 — All booking models (no logic, only simple constraints)

Declare all models in the database. No complex business logic yet —
only field-level constraints (required, null/blank, defaults, FK
relationships). The `pricing_rule` FK to TiBillet's `Price` model is
**excluded** here; it will be added in Session 12 when payment
integration is tackled.

**Models declared:**

+---------------+------------------------------------------------------+
| Model         | Key fields                                           |
+===============+======================================================+
| ResourceGroup | name, description, image, tags                       |
+---------------+------------------------------------------------------+
| Calendar      | name                                                 |
+---------------+------------------------------------------------------+
| ClosedPeriod  | calendar FK, start_date, end_date (nullable), label  |
+---------------+------------------------------------------------------+
| SlotTemplate  | name                                                 |
+---------------+------------------------------------------------------+
| SlotEntry     | template FK, weekday, start_time,                    |
|               | slot_duration_minutes, slot_count                    |
+---------------+------------------------------------------------------+
| Resource      | name, group FK (nullable), calendar FK,              |
|               | slot_template FK, capacity,                          |
|               | cancellation_deadline_hours,                         |
|               | booking_horizon_days, description, image, tags       |
+---------------+------------------------------------------------------+
| Booking       | resource FK, member FK, date, start_time,            |
|               | slot_duration_minutes, slot_count,                   |
|               | status (new/validated/confirmed), booked_at,         |
|               | payment_ref (nullable)                               |
+---------------+------------------------------------------------------+

### Session 1.1 — Red phase

**Files to create:**
- `booking/tests/test_models.py`

**Tests to write:**
```
test_resource_group_requires_name
test_calendar_requires_name
test_closed_period_end_date_is_nullable
test_closed_period_single_day_start_equals_end
test_slot_template_requires_name
test_slot_entry_requires_weekday_start_time_duration_count
test_resource_capacity_defaults_to_1
test_resource_cancellation_deadline_defaults_to_24h
test_resource_booking_horizon_defaults_to_28_days
test_resource_group_is_optional
test_booking_default_status_is_new
test_booking_payment_ref_is_nullable
```

> ⚠️ **AI stops here.** The human reviews the tests, completes or
> adjusts them if needed, and confirms before proceeding to the green
> phase.

### Session 1.2 — Green phase

**Files to create / modify:**
- `booking/models.py` — ResourceGroup, Calendar, ClosedPeriod,
  SlotTemplate, SlotEntry, Resource, Booking
- `booking/migrations/0001_initial.py`

Write the minimal model declarations to make all red-phase tests pass.

--------------------------------------------------------------------------------

## Session 2 — Complex database constraint: SlotTemplate non-overlap

Design and implement the non-overlap validation for SlotEntry within
a SlotTemplate. This is the most complex rule in the spec (circular
7-day timeline, bleed-over into next day, wrap-around Sunday→Monday).

### Session 2.1 — Red phase

**Files to create:**
- `booking/tests/test_slot_template_overlap.py`

**Tests to write:**
```
test_slot_entry_accepts_non_overlapping_entries_same_day
test_slot_entry_rejects_overlap_same_day
test_slot_entry_rejects_overlap_bleeding_into_next_day
test_slot_entry_rejects_circular_overlap_sunday_to_monday
test_slot_entry_accepts_entries_on_different_days_no_overlap
test_slot_entry_overlap_check_treats_week_as_circular
```

> ⚠️ **AI stops here.** The human reviews the tests, completes or
> adjusts them if needed, and confirms before proceeding to the green
> phase.

### Session 2.2 — Green phase

**Files to modify:**
- `booking/models.py` — add `clean()` or `save()` validation on
  SlotEntry

Write the minimal overlap-check logic to make all red-phase tests
pass.

--------------------------------------------------------------------------------

## Session 3 — Add fixtures in the lespass tenant

Create realistic test data in the lespass tenant. This data will be
used in all subsequent sessions and serves as a manual verification
baseline for the admin panel (Session 4).

### Session 3.1 — Red phase

**Files to create:**
- `booking/tests/test_fixtures_command.py`

**Tests to write:**
```
test_create_booking_fixtures_command_runs_without_error
test_create_booking_fixtures_creates_coworking_resource
test_create_booking_fixtures_creates_salle_repet_group_with_two_resources
test_create_booking_fixtures_creates_calendar_with_closed_periods
test_create_booking_fixtures_assigns_slot_templates_to_resources
```

> ⚠️ **AI stops here.** The human reviews the tests, completes or
> adjusts them if needed, and confirms before proceeding to the green
> phase.

### Session 3.2 — Green phase

**Files to create:**
- `booking/management/commands/create_booking_fixtures.py`

**Fixtures to create:**

*Resources:*
- Resource "Coworking" — capacity 3, no group

*Resource group "Salle de répét'" with two resources:*
- Resource "Petite salle" — capacity 1
- Resource "Grande salle" — capacity 1

*Calendar "Calendrier 2026":*
- Closed on all French public holidays 2026
- Closed July + August 2026 (summer closure)
- Closed December 24 – January 2 (end-of-year closure)

*Slot template "Coworking weekdays":*
- Every weekday (Mon–Fri), 8 slots of 1 hour starting at 09:00
  (generates: 09:00–10:00, 10:00–11:00, …, 16:00–17:00)

*Slot template "Salles de répét' weekend":*
- Saturday + Sunday only, 3 slots of 3 hours starting at 10:00
  (generates: 10:00–13:00, 13:00–16:00, 16:00–19:00)

Assign "Coworking weekdays" to "Coworking" resource.
Assign "Salles de répét' weekend" to both "Petite salle" and
"Grande salle".
Assign "Calendrier 2026" to all three resources.

--------------------------------------------------------------------------------

## Session 4 — Django admin panel

Add the admin panel early so that the fixtures from Session 3 are
visible and manually verifiable in the backoffice throughout
development.

**Admin registrations (per spec section 7):**

+---------------+------------+-----------------------------------+
| Model         | Admin type | Inline children                   |
+===============+============+===================================+
| ResourceGroup | ModelAdmin | —                                 |
+---------------+------------+-----------------------------------+
| Calendar      | ModelAdmin | ClosedPeriod as StackedInline     |
+---------------+------------+-----------------------------------+
| SlotTemplate  | ModelAdmin | SlotEntry as TabularInline        |
+---------------+------------+-----------------------------------+
| Resource      | ModelAdmin | —                                 |
+---------------+------------+-----------------------------------+
| Booking       | ModelAdmin | — (filterable by date and status) |
+---------------+------------+-----------------------------------+

### Session 4.1 — Red phase

**Files to create:**
- `booking/tests/test_admin.py`

**Tests to write:**
```
test_admin_resource_list_accessible_to_staff
test_admin_slot_template_shows_slot_entries_inline
test_admin_calendar_shows_closed_periods_inline
test_admin_booking_list_filterable_by_date
test_admin_booking_list_filterable_by_status
```

> ⚠️ **AI stops here.** The human reviews the tests, completes or
> adjusts them if needed, and confirms before proceeding to the green
> phase.

### Session 4.2 — Green phase

**Files to modify:**
- `booking/admin.py`

Write the minimal admin registrations to make all red-phase tests
pass.

--------------------------------------------------------------------------------

## Session 5 — Slot computation engine (pure Python, independent file)

The algorithm lives in `booking/slot_engine.py`. It is broken down
into simple, independently testable functions.

**Function breakdown:**

```python
# Assumes a given resource and a given period
# / Pour une ressource et une période donnée

def get_closed_dates_for_resource(resource, date_from, date_to):
    """Query DB: fetch ClosedPeriods from the resource's Calendar."""

def get_slot_entries_for_resource(resource):
    """Query DB: fetch SlotEntries from the resource's SlotTemplate."""

def get_existing_bookings_for_resource(resource, date_from, date_to):
    """Query DB: fetch Bookings (new/validated/confirmed) in the period."""

def generate_theoretical_slots(slot_entries, date_from, date_to, closed_dates):
    """Compute all theoretical slots — no DB queries, pure date math."""

def compute_remaining_capacity(slot, resource_capacity, existing_bookings):
    """For one slot: capacity − count of overlapping bookings."""

def compute_slots(resource, date_from, date_to):
    """Entry point: returns list of slots with remaining_capacity."""
```

### Session 5.1 — Red phase

**Files to create:**
- `booking/tests/test_slot_engine.py`

**Tests to write (this part must be thoroughly tested):**
```
test_get_closed_dates_returns_all_dates_in_closed_period
test_get_closed_dates_handles_single_day_period
test_get_closed_dates_handles_null_end_date
test_generate_theoretical_slots_from_weekday_template
test_generate_theoretical_slots_excludes_closed_dates
test_generate_theoretical_slots_respects_booking_horizon
test_compute_remaining_capacity_with_no_bookings_equals_capacity
test_compute_remaining_capacity_decreases_with_overlapping_booking
test_compute_remaining_capacity_zero_when_all_units_taken
test_compute_slots_booking_count_gt_1_overlaps_multiple_slots
test_compute_slots_booking_partial_overlap_counts_as_full_overlap
test_compute_slots_returns_empty_when_no_template
test_compute_slots_end_to_end_with_fixture_coworking_resource
test_compute_slots_end_to_end_with_fixture_petite_salle
```

> ⚠️ **AI stops here.** The human reviews the tests, completes or
> adjusts them if needed, and confirms before proceeding to the green
> phase.

### Session 5.2 — Green phase

**Files to create:**
- `booking/slot_engine.py`

Write the minimal slot computation logic to make all red-phase tests
pass.

--------------------------------------------------------------------------------

## Session 6 — Booking validation logic

Reuse the slot computation engine to validate a new booking request
before creating the Booking row. This logic is called by the
"add to basket" view (Session 10).

**Function breakdown:**

```python
def validate_new_booking(resource, date, start_time, slot_count, member):
    """
    Returns (is_valid: bool, error: str | None).
    Checks:
    - All requested slots are within booking_horizon_days
    - None of the requested slots falls in a ClosedPeriod
    - All requested slots have remaining_capacity > 0
    """
```

### Session 6.1 — Red phase

**Files to create:**
- `booking/tests/test_booking_validation.py`

**Tests to write (must be thoroughly tested):**
```
test_validate_booking_accepts_valid_slot
test_validate_booking_rejects_slot_beyond_horizon
test_validate_booking_rejects_slot_in_closed_period
test_validate_booking_rejects_full_slot
test_validate_booking_slot_count_gt_1_all_slots_must_be_available
test_validate_booking_slot_count_gt_1_fails_if_one_slot_full
test_validate_booking_slot_count_gt_1_fails_if_one_slot_in_closed_period
```

> ⚠️ **AI stops here.** The human reviews the tests, completes or
> adjusts them if needed, and confirms before proceeding to the green
> phase.

### Session 6.2 — Green phase

**Files to create:**
- `booking/booking_validator.py`

Write the minimal validation logic to make all red-phase tests pass.

--------------------------------------------------------------------------------

## Session 7 — Public view: resource list + available slots

### Session 7.1 — Red phase

**Files to create:**
- `booking/tests/test_views_public.py`

**Tests to write:**
```
test_resource_list_accessible_without_authentication
test_resource_list_returns_html_200
test_resource_list_filters_by_tag
test_resource_with_no_availability_appears_greyed_out
test_full_slot_appears_as_unavailable
```

> ⚠️ **AI stops here.** The human reviews the tests, completes or
> adjusts them if needed, and confirms before proceeding to the green
> phase.

### Session 7.2 — Green phase

**Files to create / modify:**
- `booking/views.py` — `BookingViewSet.list()`
- `booking/serializers.py` — `ResourcePublicSerializer`
- `booking/templates/booking/views/list.html`
- `booking/templates/booking/partial/card.html`

Write the minimal view, serializer, and templates to make all
red-phase tests pass.

--------------------------------------------------------------------------------

## Session 8 — Embeddable iframe page

The public booking page must be embeddable as an `<iframe>` on
external sites (spec section 4.4). This requires a dedicated route
that renders the booking page without the TiBillet site chrome
(navigation, header, footer) and with HTTP headers that allow
embedding. Tag filtering via URL parameter must also work inside
the embed.

### Session 8.1 — Red phase

**Files to create:**
- `booking/tests/test_embed.py`

**Tests to write:**
```
test_embed_page_accessible_without_authentication
test_embed_page_returns_html_200
test_embed_page_response_allows_iframe_embedding
test_embed_page_has_no_site_navigation_chrome
test_embed_page_filters_by_tag_url_parameter
test_embed_page_shows_greyed_out_resources_with_no_availability
```

> ⚠️ **AI stops here.** The human reviews the tests, completes or
> adjusts them if needed, and confirms before proceeding to the green
> phase.

### Session 8.2 — Green phase

**Files to create / modify:**
- `booking/views.py` — `BookingViewSet.embed()` (@action GET)
- `booking/templates/booking/views/embed.html` — chrome-free variant
  of the list template
- `booking/urls.py` — register the embed route

Set `X-Frame-Options` to `ALLOWALL` (or remove it) on the embed
response so browsers permit framing. Reuse the slot computation from
Session 7; no new business logic needed.

--------------------------------------------------------------------------------

## Session 9 — Slot picker (HTMX partial view)

### Session 9.1 — Red phase

**Files to create:**
- `booking/tests/test_slot_picker.py`

**Tests to write:**
```
test_slot_picker_returns_partial_html
test_slot_picker_excludes_slots_beyond_horizon
test_slot_picker_excludes_slots_in_closed_period
test_slot_picker_marks_full_slots_as_unavailable
```

> ⚠️ **AI stops here.** The human reviews the tests, completes or
> adjusts them if needed, and confirms before proceeding to the green
> phase.

### Session 9.2 — Green phase

**Files to create / modify:**
- `booking/views.py` — `BookingViewSet.slots()` (@action GET)
- `booking/templates/booking/partial/slot_picker.html`

Write the minimal HTMX partial view to make all red-phase tests pass.

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

> ⚠️ **AI stops here.** The human reviews the tests, completes or
> adjusts them if needed, and confirms before proceeding to the green
> phase.

### Session 10.2 — Green phase

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

> ⚠️ **AI stops here.** The human reviews the tests, completes or
> adjusts them if needed, and confirms before proceeding to the green
> phase.

### Session 11.2 — Green phase

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

> ⚠️ **AI stops here.** The human reviews the tests, completes or
> adjusts them if needed, and confirms before proceeding to the green
> phase.

### Session 12.2 — Green phase

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

> ⚠️ **AI stops here.** The human reviews the tests, completes or
> adjusts them if needed, and confirms before proceeding to the green
> phase.

### Session 13.2 — Green phase

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

> ⚠️ **AI stops here.** The human reviews the tests, completes or
> adjusts them if needed, and confirms before proceeding to the green
> phase.

### Session 14.2 — Green phase

**Files to create / modify:**
- `booking/tasks.py` — `expire_new_bookings_task()`

Write the minimal Celery task to make all red-phase tests pass.
