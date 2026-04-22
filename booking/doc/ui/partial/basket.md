# Basket — Shopping Basket

**Template:** `booking/templates/booking/partial/basket.html`
**Rendered by (primary):**
- `BookingViewSet.list()` — included in `booking_base.html`
- `BookingViewSet.resource_page()` — same base
- `BookingViewSet.remove_from_basket()` — on error (422)
- `BookingViewSet.validate_basket()` — on error (422)

**Rendered by (OOB):**
- `BookingViewSet.add_to_basket()` — `hx-swap-oob="outerHTML"` after
  a booking is created; updates basket without a full-page reload

**Position:** Always visible at the top of every booking page
(rendered in `booking_base.html` above `{% block booking_content %}`).

---

## Context variables

+-------------------------+---------------------------+----------+-------------------------------------------------------+
| Variable                | Type                      | Required | Description                                           |
+=========================+===========================+==========+=======================================================+
| `reservations_en_cours` | `QuerySet[Booking] \| []` | yes      | User's 'new' bookings; empty list for anonymous users |
+-------------------------+---------------------------+----------+-------------------------------------------------------+
| `oob`                   | `bool`                    | no       | When True, adds `hx-swap-oob="outerHTML"` attribute   |
+-------------------------+---------------------------+----------+-------------------------------------------------------+

### Booking fields displayed per row

+------------------+------------------------------------------------+
| Field            | Display format                                 |
+==================+================================================+
| `resource.name`  | Plain text label                               |
+------------------+------------------------------------------------+
| `start_datetime` | `{{ reservation.start_datetime                 |
+------------------+------------------------------------------------+
| `slot_count`     | Badge `× N` (shown only when `slot_count > 1`) |
+------------------+------------------------------------------------+

---

## States

+-------------------+-----------------------------------+-----------------------------------------------+
| State             | Condition                         | Visual                                        |
+===================+===================================+===============================================+
| Empty basket      | `reservations_en_cours` is empty  | Muted text "Votre panier est vide"            |
+-------------------+-----------------------------------+-----------------------------------------------+
| Basket with items | `reservations_en_cours` non-empty | List of booking rows + "Confirmer" button     |
+-------------------+-----------------------------------+-----------------------------------------------+
| OOB mode          | `oob=True`                        | Adds `hx-swap-oob="outerHTML"` on the wrapper |
+-------------------+-----------------------------------+-----------------------------------------------+

---

## HTMX interactions

### Remove a booking

Each booking row has a remove button:
```
hx-post="/booking/<ressource.pk>/remove_from_basket/"
hx-vals='{"booking_pk": {{ reservation.pk }}}'
hx-target="[data-testid='booking-basket']"
hx-swap="outerHTML"
```

On success the server sends `HX-Redirect` to the current page
(HTMX follows the redirect, reloading the full body including the
basket with the item removed).

On error (422) the server re-renders this template with `erreur`,
replacing the basket container.

### Confirm basket

```
hx-post="/booking/validate_basket/"
hx-target="[data-testid='booking-basket']"
hx-swap="outerHTML"
```

On success the basket is replaced by `basket_confirmed.html`.
On error (422 — empty basket race condition) this template is
re-rendered with an error message.

### OOB update after add_to_basket

When a booking is added, `add_to_basket` returns two HTML fragments:
1. Updated `slot_row.html` (primary swap target)
2. This template with `oob=True` (out-of-band swap)

HTMX processes both swaps in the same response.

---

## Accessibility

- Basket container: `aria-live="polite"` so screen readers announce
  changes after OOB swaps
- Remove button: `aria-label="Retirer {{ reservation.resource.name }}
  du {{ reservation.start_datetime|date:'D d/m/Y H:i' }}"`
- Slot count badge: `aria-label="{{ reservation.slot_count }} créneaux"`
- Confirm button: `aria-describedby` pointing to item count (optional)
- Empty state: `role="status"` on the muted text

---

## data-testid

+----------------------+-------------------+----------------------------------+
| Value                | Element           | Purpose                          |
+======================+===================+==================================+
| `booking-basket`     | wrapper container | HTMX swap target (primary + OOB) |
+----------------------+-------------------+----------------------------------+
| `basket-remove-<pk>` | remove button     | Per-booking remove button        |
+----------------------+-------------------+----------------------------------+
| `basket-validate`    | confirm button    | Confirm all bookings button      |
+----------------------+-------------------+----------------------------------+
