# Resource Detail

**URL:** `GET /booking/resource/<pk>/`
**Access:** Public to view; login required to book

## What the user sees

- Resource name, description, and image (if set).
- A chronological list of slots up to the resource's booking horizon.
  - A coloured "Semaine N" banner marks the start of each new ISO week.
  - A bold date header (e.g. "Lundi 04 mai") marks the start of each
    contiguous group of same-duration slots.
  - Each slot shows its time range and duration only (the date is not
    repeated per slot).
- Remaining capacity is shown per slot when the resource has capacity > 1.
- Slots that are full (remaining_capacity = 0) appear in the list
  but are marked unavailable and are not clickable.
- A link back to the resource list.

## What the user can do

**Click an available slot:**
- If logged in → goes to the booking page for that slot. The
  booking page will show how many consecutive slots of the same
  duration can be chained from that start time.
- If not logged in → redirected to the login page, then returned
  here after login.

## Edge cases

**No upcoming slots:** a message "Aucun créneau disponible
prochainement." This can happen in three situations:

- The WeeklyOpening assigned to the resource has no OpeningEntry
  rows yet. Every resource must have a WeeklyOpening (it is
  mandatory in the model), but a WeeklyOpening can be empty.
- The entire booking horizon is covered by ClosedPeriods in the
  resource's Calendar.
- The resource has capacity = 0, which deactivates it without
  deleting it.

**Resource not found:** 404.
