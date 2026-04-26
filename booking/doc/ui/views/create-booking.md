# Create a Booking

**Access:** Login required

## GET — display the booking form

**URL:** `GET /booking/<pk>/book/?start_datetime=<local datetime>`

`<pk>` is the primary key of the Resource. `start_datetime` is in
the tenant's local timezone, with no UTC offset — for example
`2026-05-10T10:00:00`. This matches what the user sees on the
resource detail page. The server interprets it as local time for
this tenant.

The user arrives here in two situations:
- From clicking a slot on the resource detail page.
- After a POST that failed due to a race condition — the page
  re-renders so the user can see the updated availability and
  resubmit.

In both cases the server derives the slot duration by computing
the slots for this resource and finding the one matching
`start_datetime`. It then computes the fresh list of all
consecutive slots of the same duration from that start time and
renders the page.

The page shows:
- Resource name.
- A fresh list of all consecutive slots from the start time, each
  with its current load. Two cases:
  - capacity = 1 (exclusive resource): each slot is either
    available or taken.
  - capacity > 1 (shared resource): each slot shows remaining
    places and total capacity, e.g. "2 / 3 places disponibles".

Example for an exclusive resource with 60min slots at 10:00:

  10:00 → 11:00   available
  11:00 → 12:00   available
  12:00 → 13:00   taken

Example for a shared resource (capacity 3):

  10:00 → 11:00   2 / 3 places disponibles
  11:00 → 12:00   3 / 3 places disponibles
  12:00 → 13:00   0 / 3 places disponibles

- A slot count input (min 1, max = available run before the first
  fully taken slot). Always shown — the form is a deliberate
  confirmation step even when only one slot is available. After a
  race condition re-render, the input resets to the new maximum.
- The cancellation deadline for this resource, shown as a
  commitment: "Vous pouvez annuler jusqu'au <deadline datetime>."
  If the deadline is already past at booking time (e.g. the slot
  starts in less than the deadline window), the message changes to
  "L'annulation ne sera pas possible pour ce créneau."
- A "Confirmer" button.
- A "Retour" link — an explicit link to the resource detail page
  URL (`/booking/resource/<pk>/`), not a browser back button.
  Following it triggers a fresh GET of the resource detail page,
  which recomputes all slot availability.

If the starting slot is already taken, the user is redirected
immediately to the slot unavailable page — no form is shown.

## POST — submit the booking

**URL:** `POST /booking/<pk>/book/`

The user submits the form. Parameters in the request body:

- `start_datetime` — local datetime of the first slot, no UTC
  offset, e.g. `2026-05-10T10:00:00`
- `slot_count` — number of consecutive slots to book (min 1)

The server derives `slot_duration_minutes` from `start_datetime`
and the resource, same as on GET.

The server validates them and creates the booking if all requested
slots are still available.

- All requested slots still available → booking created with
  status `confirmed`, redirected to
  `/booking/my-bookings/?new=<booking_pk>`.
- A slot in the requested range was taken between the page load
  and the submission (race condition) → the page re-renders with
  a message "Un créneau a été réservé entre temps. Voici les
  disponibilités actualisées." and a fresh slot list. No redirect
  — the message is passed directly in the POST response.
- The slot has already started by submission time → the page
  re-renders with a distinct message "Ce créneau est déjà
  commencé." and a link back to the resource detail page.

## Edge cases

**Starting slot already taken on arrival:** the user is redirected
to the slot unavailable page.

**Not logged in:** redirect to login with `?next=` pointing back
here.

**Resource or slot not found (bad URL params):** 404.
