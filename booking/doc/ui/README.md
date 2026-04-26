# Booking UI — v0.1 Specification

No HTMX inline interactions.

## Pages

Pages the user browses to directly.

[views/home.md](views/home.md)
  url    : `GET /booking/`
  access : Public

[views/resource-detail.md](views/resource-detail.md)
  url    : `GET /booking/resource/<pk>/`
  access : Public

[views/my-bookings.md](views/my-bookings.md)
  url    : `GET /booking/my-bookings/`
  access : Login required

## Actions

Transactional pages: GET shows a confirmation form, POST performs
the action. Redirect-only pages are only reachable via redirect
from an action, never by direct navigation.

[views/create-booking.md](views/create-booking.md)
  url    : `GET  /booking/<pk>/book/`
           `POST /booking/<pk>/book/`
  access : Login required

[views/slot-unavailable.md](views/slot-unavailable.md)
  url    : `GET /booking/<pk>/slot-unavailable/`
  access : Public
  note   : redirect-only — reached from create-booking when the
            starting slot is already taken

[views/cancel-booking.md](views/cancel-booking.md)
  url    : `GET  /booking/cancel/<booking_pk>/`
           `POST /booking/cancel/<booking_pk>/`
  access : Login required

## Format

Each spec describes what the user sees and what they can do.
Implementation details (context variables, URL patterns, template
names) belong in the code, not the spec.

## What is not in v0.1

- Basket (bookings go directly to `confirmed`)
- Payment
- Membership gating (login is enough)
- HTMX inline interactions
- Embeddable iframe

These will be designed when real users ask for them, or when the
TiBillet core team makes progress on the payment and basket system.
