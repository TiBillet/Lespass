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
├── booking_form()      → partial/booking-form.md
├── add_to_basket()     → partial/slot-row.md + partial/basket.md (OOB)
├── remove_from_basket() → partial/basket.md
├── validate_basket()   → partial/basket-confirmed.md
└── cancel()            → partial/cancel-error.md

MyAccount (BaseBillet)
└── my_resources()      → views/my-resources.md
```

---

## Files

### Pages (full views)

| File                         | Template                        | URL               |
|------------------------------|---------------------------------|-------------------|
| [views/home.md](views/home.md) | `booking/views/home.html`       | `GET /booking/`   |
| [views/resource-detail.md](views/resource-detail.md) | `booking/views/resource.html` | `GET /booking/resource/<pk>/` |
| [views/my-resources.md](views/my-resources.md) | `BaseBillet/templates/reunion/views/account/my_resources.html` | `GET /my_account/my_resources/` |

### Partials (HTMX fragments)

| File                                            | Template                                 |
|-------------------------------------------------|------------------------------------------|
| [partial/card.md](partial/card.md)              | `booking/partial/card.html`              |
| [partial/slot-list.md](partial/slot-list.md)    | `booking/partial/slot_list.html`         |
| [partial/slot-row.md](partial/slot-row.md)      | `booking/partial/slot_row.html`          |
| [partial/booking-form.md](partial/booking-form.md) | `booking/partial/booking_form.html`   |
| [partial/basket.md](partial/basket.md)          | `booking/partial/basket.html`            |
| [partial/basket-confirmed.md](partial/basket-confirmed.md) | `booking/partial/basket_confirmed.html` |
| [partial/cancel-error.md](partial/cancel-error.md) | `booking/partial/cancel_error.html`  |

---

## Format convention

Each spec uses this structure:

```
## ComponentName
Short description.

### Context variables
Table: name | type | description | required?

### States
Table: state | condition | visual description

### HTMX interactions
One bullet per trigger: event → endpoint → target + swap strategy

### Accessibility
ARIA attributes, aria-live regions, screen-reader labels

### data-testid
Table: attribute value | element | purpose
```
