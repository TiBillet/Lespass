# Slot Unavailable

**URL:** `GET /booking/<pk>/slot-unavailable/`
**Access:** Public

## What the user sees

A calm explanation that the starting slot they tried to book is no
longer available:

- Resource name.
- The slot date and time they were trying to book.
- A short explanation: the slot was taken between the moment they
  saw it and the moment they arrived on the booking page. This is
  a normal situation when several people book at the same time.
- One clear action: a link back to the resource detail page to
  choose another starting slot.

## When this page appears

Only when the **starting slot itself** is already taken on arrival
at the booking page (GET). There is nothing to book from this start
time at all.

When only some consecutive slots are taken (but the starting slot
is still available), the booking page handles it directly by
showing a fresh slot list — no redirect here.

## Edge cases

**Resource not found:** 404.
