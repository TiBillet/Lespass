# Cancel a Booking

**Access:** Login required

## GET — display the cancellation confirmation

**URL:** `GET /booking/cancel/<booking_pk>/`

`<booking_pk>` is the primary key of the Booking to cancel.

The user arrives here from the "Annuler" button on the My Bookings
page. The page shows the full details of what is about to be
cancelled so the user can make a deliberate decision:

- Resource name.
- Slot date, time, and duration.
- Number of slots (only shown when slot_count > 1).
- The cancellation deadline.

Two states depending on the deadline:

**Deadline not yet passed:** a confirmation form is shown with a
"Confirmer l'annulation" button and a "Retour" link back to
My Bookings. The user must actively confirm before anything
is deleted.

**Deadline already passed:** no form is shown. A message explains
that cancellation is no longer possible and shows the exact
deadline that was missed. A link back to My Bookings is shown.

## POST — perform the cancellation

**URL:** `POST /booking/cancel/<booking_pk>/`

The user submits the confirmation form.

- Deadline not passed → booking deleted, redirected to
  `/booking/my-bookings/`.
- Deadline passed between GET and POST (race condition) → page
  re-renders with the "deadline passed" state and a message
  explaining what happened.

## Edge cases

**Booking not found or belongs to another user:** 404.

**Booking status is not `confirmed`:** 404 — only confirmed
bookings are cancellable through this flow.

**Not logged in:** redirect to login with `?next=` pointing back
here.
