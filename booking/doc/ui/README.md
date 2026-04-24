# Booking UI — Specification Index

Each file in this folder documents one template (view or partial) as a
UI component: context variables, visual states, HTMX wiring, and
accessibility requirements.

Use these specs to prompt Claude Code for iterative UI changes.
Example prompt: "Update `slot-row.md` state X, then implement it."

---

## Component map

```
BookingViewSet
├── list()              → views/home.md
│   └── card.html       → partial/card.md
│       └── slot_list   → partial/slot-list.md
│           └── slot_row → partial/slot-row.md
│
├── resource_page()     → views/resource-detail.md
│   └── slot_list       → partial/slot-list.md
│       └── slot_row    → partial/slot-row.md
│
├── my_bookings()       → views/my-bookings.md
├── booking_form()      → partial/booking-form.md
├── add_to_basket()     → partial/slot-row.md + partial/basket.md (OOB)
├── remove_from_basket() → partial/basket.md
├── validate_basket()   → partial/basket-confirmed.md
└── cancel()            → partial/cancel-error.md

```

---

## Files

### Pages (full views)

[views/home.md](views/home.md)
  template : `booking/views/home.html`
  url      : `GET /booking/`

[views/resource-detail.md](views/resource-detail.md)
  template : `booking/views/resource.html`
  url      : `GET /booking/resource/<pk>/`

[views/my-bookings.md](views/my-bookings.md)
  template : `booking/templates/booking/views/my_bookings.html`
  url      : `GET /booking/my-bookings/`

### Partials (HTMX fragments)

[partial/card.md](partial/card.md)
  template : `booking/partial/card.html`

[partial/slot-list.md](partial/slot-list.md)
  template : `booking/partial/slot_list.html`

[partial/slot-row.md](partial/slot-row.md)
  template : `booking/partial/slot_row.html`

[partial/booking-form.md](partial/booking-form.md)
  template : `booking/partial/booking_form.html`

[partial/basket.md](partial/basket.md)
  template : `booking/partial/basket.html`

[partial/basket-confirmed.md](partial/basket-confirmed.md)
  template : `booking/partial/basket_confirmed.html`

[partial/cancel-error.md](partial/cancel-error.md)
  template : `booking/partial/cancel_error.html`

---

## Format convention

Each spec uses this structure:

```
## ComponentName
Short description.

### Context variables
One entry per variable: `name` (type, required/optional) + description.

### States
One entry per state: **bold state name** — condition + visual description.

### HTMX interactions
One bullet per trigger: event → endpoint → target + swap strategy

### Accessibility
ARIA attributes, aria-live regions, screen-reader labels

### data-testid
One entry per value: `attribute-value` — element + purpose.
```
