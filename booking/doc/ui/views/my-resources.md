# My Resources — Member Booking History Page

**Template:** `BaseBillet/templates/reunion/views/account/my_resources.html`
**Rendered by:** `MyAccount.my_resources()` in `BaseBillet/views.py:1107`
**URL:** `GET /my_account/my_resources/`
**Base template:** `reunion/account_base.html`

This page lives inside the existing BaseBillet member account area, not in
the booking app. It shows the authenticated member's upcoming confirmed
bookings, each with an inline HTMX cancel button.

The page is only reachable when `config.module_booking` is `True` — the
tab button in the account index is guarded by `{% if config.module_booking %}`.

---

## Context variables

| Variable                  | Type               | Required | Description                                                 |
|---------------------------|--------------------|----------|-------------------------------------------------------------|
| `reservations_confirmees` | `QuerySet[Booking]` | yes     | Member's upcoming `confirmed` bookings, ordered by `start_datetime`. Filtered: `user=request.user`, `status='confirmed'`, `start_datetime__gt=now()`. `select_related('resource')` applied. |
| `account_tab`             | `str`              | yes      | Fixed value `'my_resources'` — activates the tab in the account index. |
| `config`                  | `Configuration`    | yes      | Tenant config from `get_context(request)`.                  |

---

## States

| State                      | Condition                                  | Visual                                                         |
|----------------------------|--------------------------------------------|----------------------------------------------------------------|
| Has confirmed bookings     | `reservations_confirmees` is non-empty     | `<ul class="list-group">` with one `<li>` per booking          |
| No confirmed bookings      | `reservations_confirmees` is empty         | Muted paragraph "Aucune réservation confirmée à venir."        |
| Multi-slot booking         | `reservation.slot_count > 1`               | Secondary badge `{{ slot_count }} créneaux` next to the date   |
| Single-slot booking        | `reservation.slot_count == 1`              | No badge — only resource name and formatted date               |
| Cancel button — default    | Before HTMX request fires                  | Danger outline button "Annuler" with × icon                    |
| Cancel error — deadline    | 422 with `erreur_deadline=True`            | Warning badge "Annulation impossible" + deadline text inline   |
| Cancel error — generic     | 422 with `erreur` string                   | Danger badge with the error message inline                     |
| Cancel success             | 200 with `HX-Redirect`                     | Full page reload of `/my_account/my_resources/`                |

---

## HTMX interactions

- **Cancel button** (`hx-post`):
  - Trigger: click on the cancel `<button>`
  - Request: `POST /booking/cancel/` with body `{"booking_pk": "<reservation.pk>"}`
  - Target: `#cancel-result-<reservation.pk>` (the `<span>` wrapping the button)
  - Swap: `innerHTML` — replaces only the button content with the error partial
  - On HTTP 200: `HX-Redirect: /my_account/my_resources/` triggers a full
    navigation (HTMX intercepts the header and calls `window.location`)
  - On HTTP 422: `cancel_error.html` is swapped in place of the button

- **Inline 422 handling** (inline `<script>` in the template):
  Configures `htmx:beforeOnLoad` to set `shouldSwap = true` and
  `isError = false` for HTTP 422 responses, enabling the error partial swap.
  See DJC skill — "HTMX Quirks §2" for the reason.

- **"Voir les ressources disponibles" link** (plain `<a>`, no HTMX):
  Navigates to `/booking/` — full page load, no HTMX swap.

---

## Entry point

The "Mes ressources" tab button appears in `account/index.html` only when
`config.module_booking` is `True`:

```
/my_account/          → account index (index.html)
    └── "Mes ressources" button (data-testid="btn-my-resources")
            → /my_account/my_resources/
```

After a successful cancellation, `HX-Redirect` reloads the same page.

---

## cancel() endpoint (called by this page)

**ViewSet:** `BookingViewSet.cancel()` in `booking/views.py:544`
**URL:** `POST /booking/cancel/`

| Response | Condition                                         | Body                                         |
|----------|---------------------------------------------------|----------------------------------------------|
| 200      | Booking deleted                                   | Empty + `HX-Redirect: /my_account/my_resources/` |
| 401      | User not authenticated                            | Empty                                        |
| 422      | Booking not found, wrong owner, or wrong status  | `cancel_error.html` with `erreur` string     |
| 422      | Cancellation deadline exceeded                    | `cancel_error.html` with `erreur_deadline=True` + `deadline_datetime` |

Only `confirmed` bookings are cancellable through this endpoint. `new`
bookings are removed via `remove_from_basket()` (basket management page).

---

## Accessibility

- `<h1>` with `bi-chair` icon: icon has `aria-hidden="true"`
- Cancel button icon (`bi-x-circle`): `aria-hidden="true"`
- Each list item: `data-testid="my-resource-<pk>"` for E2E targeting
- No `aria-live` on the list — the inline cancel error appears inside the
  existing `<span>` without moving focus. Consider adding `aria-live="polite"`
  on `#cancel-result-<pk>` in a future iteration.

---

## data-testid

| Value                          | Element           | Purpose                                |
|--------------------------------|-------------------|----------------------------------------|
| `my-resource-<pk>`             | `<li>`            | Per-booking list item                  |
| `btn-cancel-<pk>`              | `<button>`        | Cancel button; `<pk>` is `reservation.pk` |
| `btn-my-resources`             | account index `<a>` | Tab button (in `account/index.html`) |
| `booking-empty-list`           | —                 | Not yet added (missing `data-testid` on the empty state `<p>`) |

---

## Known gaps / future work

- The empty-state `<p>` has no `data-testid` — Playwright tests cannot
  reliably target it.
- The inline `<script>` for 422 HTMX handling duplicates logic that should
  live in the base template or a shared JS include (see DJC skill quirks §2).
- No `aria-live` on the cancel result span — screen readers may miss inline
  error messages after cancellation attempt.
- After cancellation the page does a full reload via `HX-Redirect`. A future
  improvement could update only the booking list via an OOB swap.
