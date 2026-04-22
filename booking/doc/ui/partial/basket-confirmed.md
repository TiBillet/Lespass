# BasketConfirmed — Booking Confirmation Message

**Template:** `booking/templates/booking/partial/basket_confirmed.html`
**Rendered by:** `BookingViewSet.validate_basket()` on success
**Replaces:** `[data-testid='booking-basket']` (same swap target as
`basket.html` — `hx-swap="outerHTML"`)

One-shot success feedback. Replaces the basket container after all
'new' bookings are confirmed. Shows a count and an optional return link.

---

## Context variables

+--------------------------+-------+----------+----------------------------------------------+
| Variable                 | Type  | Required | Description                                  |
+==========================+=======+==========+==============================================+
| `nombre_de_reservations` | `int` | yes      | Number of bookings just confirmed            |
+--------------------------+-------+----------+----------------------------------------------+
| `request.path`           | `str` | yes      | Current URL path (auto from request context) |
+--------------------------+-------+----------+----------------------------------------------+

---

## States

+-------------------------+-------------------------------+--------------------------------------------+
| State                   | Condition                     | Visual                                     |
+=========================+===============================+============================================+
| On booking page         | `request.path == "/booking/"` | Green badge only; no return link shown     |
+-------------------------+-------------------------------+--------------------------------------------+
| On resource detail page | `request.path != "/booking/"` | Green badge + "Toutes les ressources" link |
+-------------------------+-------------------------------+--------------------------------------------+

The return link navigates back to `/booking/` with HTMX full-body swap.

---

## HTMX interactions

### Return to resource list (conditional)

Only rendered when `request.path != "/booking/"`:
```
hx-get="/booking/"
hx-target="body"
hx-swap="innerHTML"
hx-push-url="true"
href="/booking/"
```

---

## Accessibility

- Success badge: `role="status"` so screen readers announce the
  confirmation without requiring focus
- Count: `aria-label="{{ nombre_de_reservations }} réservation(s)
  confirmée(s)"` on the badge

---

## data-testid

+------------------+-----------------+----------------------------------------------+
| Value            | Element         | Purpose                                      |
+==================+=================+==============================================+
| `booking-basket` | wrapper element | Same target as basket.html (swap continuity) |
+------------------+-----------------+----------------------------------------------+
