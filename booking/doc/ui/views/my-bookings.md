# My Bookings

**URL:** `GET /booking/my-bookings/`
**Access:** Login required

## What the user sees

The page has two sections: upcoming bookings and past bookings.
Nothing is ever deleted from this view — a confirmed booking stays
visible after it ends, moved to the past section.

**Upcoming bookings** — `end_datetime > now()`, ordered by
`start_datetime` ascending (soonest first). Includes bookings that
are currently in progress (started but not yet ended).

**Past bookings** — `end_datetime <= now()`, ordered by
`start_datetime` descending (most recent first).

When arriving here after a successful booking, the create-booking
view redirects to `/booking/my-bookings/?new=<booking_pk>`. The
template reads this param and highlights the matching booking in
the list so the user can find it immediately. When navigating to
this page directly, no param is present and no booking is
highlighted.

Each upcoming booking shows:

- Resource name.
- Date and time.
- Number of slots booked (only shown when slot_count > 1).
- A "Annuler" link → goes to the cancel confirmation page
  (see [cancel-booking.md](cancel-booking.md)).

Each past booking shows:

- Resource name.
- Date and time.
- Number of slots booked (only shown when slot_count > 1).
- No cancel link.

## What the user can do

**Cancel an upcoming booking:** click the "Annuler" link on an
upcoming booking row. The full cancellation flow is specified in
[cancel-booking.md](cancel-booking.md).

## Edge cases

**No upcoming bookings:** a message "Aucune réservation à venir."
in the upcoming section. The past section still shows if it has
entries.

**No bookings at all:** a message "Aucune réservation." with a
link back to the resource list.

**Not logged in:** redirect to login with `?next=` pointing back
here.
