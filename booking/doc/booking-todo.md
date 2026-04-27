# Booking — Todo

Tasks agreed in the v0.1 planning session (2026-04-26).
Check items off as they are done.

## Spec

- [x] Annotate tibillet-booking-spec.md with v0.1 / v0.2 markers
      throughout
- [x] Add tags to spec §9 Out of Scope
- [x] Update §3.1.6 Booking status table (remove new/validated,
      note that confirmed is the only status in v0.1)
- [x] Update §4.1 Member flow (remove basket steps 6–7)
- [x] Update §4.4 Public Booking Page (remove tag filtering)
- [x] Update §5 Basket & Timeouts (mark entire section out of scope
      for v0.1)
- [x] Update §6 Integration (mark Product/Price/Wallet as deferred)
- [x] Update §7.2 Member User Journey (remove basket and HTMX
      inline form description, align with v0.1 flow)

## Models (migrations required)

Run in this order — §15 filter depends on end_datetime existing:

- [x] Remove `tags` from Resource and ResourceGroup
- [ ] Add `end_datetime` to Booking — §15 performance fix.
      Once done: update `get_existing_bookings_for_resource` to
      filter with `start_datetime < window.end AND end_datetime >
      window.start` instead of loading all bookings.
- [ ] Simplify `Booking.status` — keep `confirmed` only, remove
      `new` and `validated`

## Engine

- [ ] Fix `select_for_update` — lock Booking rows, not the Resource
      row. The race condition is between concurrent new bookings, not
      between bookings and resource deletions.
- [ ] Apply §15 date filter in `get_existing_bookings_for_resource`
      (depends on end_datetime migration above)

## Views and URLs

- [ ] Update urls.py — add new URL patterns:
      - `/booking/<pk>/book/`
      - `/booking/<pk>/slot-unavailable/`
      - `/booking/cancel/<booking_pk>/`
- [ ] Rewrite views.py — replace the current 800-line ViewSet with
      simple methods, no HTMX partial management:
      - list()             — resource list
      - resource_page()    — resource detail with full slot list
      - book()             — GET: confirmation form (redirect to
                             slot-unavailable if already full);
                             POST: create confirmed booking,
                             redirect to my-bookings on success,
                             redirect to slot-unavailable on failure
      - slot_unavailable() — slot was taken (race condition)
      - my_bookings()      — list upcoming and past bookings
      - cancel_confirm()   — GET: show cancellation confirmation;
                             POST: delete booking, redirect to
                             my-bookings

## Templates

- [ ] Delete all existing templates
- [ ] Simplify booking_base.html — remove basket include and
      HTMX 422 script
- [ ] Write 6 new simple templates:
      - home.html              (resource list)
      - resource.html          (resource detail + slot list)
      - book.html              (booking confirmation form)
      - slot_unavailable.html  (slot taken — race condition)
      - my_bookings.html       (upcoming and past bookings)
      - cancel_booking.html    (cancel confirmation + deadline)

## Tests

- [x] Delete UI tests that were never validated and do not catch
      real issues: test_views_public, test_views_resource,
      test_basket, test_cancel, test_admin, test_my_resources,
      test_validate
- [x] Keep: test_booking_engine, test_interval,
      test_timezone_slots, test_weekly_opening_overlap,
      test_models

## Fixture

- [ ] Add description and image to each Resource in the demo fixture
