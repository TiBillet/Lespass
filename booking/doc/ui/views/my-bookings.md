# My Bookings — Member Confirmed Booking History

**Template:** `booking/templates/booking/views/my_bookings.html`
**Rendered by:** `BookingViewSet.my_bookings()` in `booking/views.py`
**URL:** `GET /booking/my-bookings/`
**Action decorator:** `@action(detail=False, methods=['GET'], url_path='my-bookings')`
**Base template:** `booking/booking_base.html`

Shows the authenticated member's upcoming confirmed bookings. Each booking
has an inline HTMX cancel button.

---

## Access control

- User not authenticated → 302 redirect to `/login/`
- `config.module_booking` is `False` → 404
- Authenticated + module enabled → Render the page

The redirect (not 401) is intentional: this is a GET page, not an HTMX
endpoint. A 401 would produce a blank error in the browser; a redirect
sends the user to login and returns them to this page afterward.

---

## Context variables

`confirmed_bookings` (`QuerySet[Booking]`, required)
  Member's upcoming `confirmed` bookings, ordered by `start_datetime`.
  Filtered: `user=request.user`, `status='confirmed'`,
  `start_datetime__gt=now()`. `select_related('resource')` applied.

---

## States

**Has confirmed bookings** — `confirmed_bookings` is non-empty
  `<ul class="list-group">` with one `<li>` per booking.

**No confirmed bookings** — `confirmed_bookings` is empty
  Muted paragraph "Aucune réservation confirmée à venir."

**Multi-slot booking** — `booking.slot_count > 1`
  Secondary badge `{{ slot_count }} créneaux` next to the date.

**Single-slot booking** — `booking.slot_count == 1`
  No badge — resource name and formatted date only.

**Cancel button — default** — before HTMX request fires
  Danger outline button "Annuler" with × icon.

**Cancel error — deadline** — 422 with `erreur_deadline=True`
  Warning badge "Annulation impossible" + deadline text inline.

**Cancel error — generic** — 422 with `erreur` string
  Danger badge with the error message inline.

**Cancel success** — 200 with `HX-Redirect`
  Full page reload of `/booking/my-bookings/`.

---

## HTMX interactions

- **Cancel button** (`hx-post`):
  - Trigger: click on the cancel `<button>`
  - Request: `POST /booking/cancel/` with body `{"booking_pk": "<booking.pk>"}`
  - Target: `#cancel-result-<booking.pk>` (the `<span>` wrapping the button)
  - Swap: `innerHTML` — replaces only the button content with the error partial
  - On HTTP 200: `HX-Redirect: /booking/my-bookings/` triggers full navigation
  - On HTTP 422: `cancel_error.html` is swapped in place of the button

- **422 handling** (inline `<script>` in the template):
  Configures `htmx:beforeOnLoad` to set `shouldSwap = true` and
  `isError = false` for HTTP 422 responses, enabling the error partial swap.
  See DJC skill — "HTMX Quirks §2".

---

## Navigation

- **Back link**: "← Mon compte" → `/my_account/` (plain `<a>`, no HTMX)
- **Forward link**: "Voir les ressources disponibles" → `/booking/`
  (plain `<a>`, no HTMX)
- **Entry point**: "Mes ressources" tile in `account/index.html`
  (`data-testid="btn-my-resources"`) links to `/booking/my-bookings/`.
  The tile is only shown when `config.module_booking` is `True`.

---

## cancel() endpoint (called by this page)

**ViewSet:** `BookingViewSet.cancel()` in `booking/views.py`
**URL:** `POST /booking/cancel/`

**200** — Booking deleted
  Empty + `HX-Redirect: /booking/my-bookings/`

**401** — User not authenticated
  Empty.

**422** — Booking not found, wrong owner, or wrong status
  `cancel_error.html` with `erreur` string.

**422** — Cancellation deadline exceeded
  `cancel_error.html` with `erreur_deadline=True` + `deadline_datetime`.

Only `confirmed` bookings are cancellable through this endpoint. `new`
bookings are removed via `remove_from_basket()`.

---

## Accessibility

- Page heading `<h1>` icon (`bi-chair`): `aria-hidden="true"`
- Cancel button icon (`bi-x-circle`): `aria-hidden="true"`
- Each list item: `data-testid="my-resource-<pk>"` for E2E targeting
- The inline cancel result span has no `aria-live` — consider adding
  `aria-live="polite"` on `#cancel-result-<pk>` so screen readers
  announce the error after a failed cancellation attempt.

---

## data-testid

`my-resource-<pk>` — `<li>`
  Per-booking list item.

`btn-cancel-<pk>` — `<button>`
  Cancel button; `<pk>` is `booking.pk`.

`booking-empty-list` — empty state `<p>`
  Empty state — add this; currently missing.
