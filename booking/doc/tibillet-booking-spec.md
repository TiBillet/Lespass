# TiBillet — Booking Module Specification

**Version:** v0.8 (draft)
**Status:**  Ready for review by TiBillet core team
**Date:**    2026-04-14
**Author:**  Joris REHM
**Note:**    This version was produced in a pair specification session with Claude AI (Anthropic)

Changes:

  - 0.8 Work on the UI specification
  - 0.7 §2 Member actor updated. §3.1.6 Booking status updated.
         §4.2 Member cancel flow clarified. §4.3 Volunteer flow updated.
         §5 Availability, Pricing, Cancellation rules updated.
         §7 Member views updated; new §7 Member (account administration)
         section added. §7 Volunteer admin table updated.
  - 0.6 Section 3 restructured: §3.1 Schema Models groups all persisted
         models (§3.1.1–§3.1.6); §3.5 Slot removed and replaced by a new
         §3.2 Booking Logic that formally defines the four sets O, W, E, B.
         Each set has a Purpose, a Definition, and cross-references to the
         schema models.
         Schema corrections (aligned with code): Booking.date+start_time
         replaced by start_datetime (tz-aware); Booking.member renamed user;
         OpeningEntry.template renamed weekly_opening. §3.1.1 capacity=0
         note added. §3.1.3 end_date >= start_date rule added. §3.1.4
         max-opening-duration consequence added. §5 Business Rules:
         member vs volunteer alignment rule distinguished explicitly
         (finding §11 resolved).
  - 0.5 Slot: replace date+start_time+end_time with start_datetime+end_datetime
         (timezone-aware, consistent with Booking.start_datetime — decisions §2)
  - 0.4 Rename SlotTemplate to WeeklyOpening
    and SlotEntry to OpeningEntry
  - 0.3 Simplify: the "unit" feature replaced by resource grouping
  - 0.2 First commited version
  - 0.1 Early draft (not published)

---

## 1. Context & Goals

TiBillet is a federated, open-source platform built with Django and htmx as a
Hypermedia-Driven Application (HDA), deployed in a multi-tenant architecture.
It is used by tiers-lieux, fablabs, associations, and cultural venues, and already
handles ticketing, membership, cashless wallets, credit card payments, and a
federated event agenda.

This document specifies a new **Booking module** — a first-class addition to the
TiBillet platform that allows members of an association to reserve shared resources
(rooms, coworking desks, machines, equipment, etc.) in fixed time slots, with
optional payment via the existing TiBillet payment system.

### Goals

- Enable associations to expose shared resources for booking by their members.
- Reuse existing TiBillet primitives: membership gating, wallet/cashless payments,
  tenant isolation.
- Provide a public-facing, embeddable booking page for each tenant.
- Keep the model simple: one-off bookings on fixed recurring slots, instant
  confirmation.

### Non-goals (v1)

- Recurring / subscription bookings.
- Cross-tenant resource sharing (federated booking).
- Mobile native app (web-responsive is sufficient for v1).


## 2. Actors

+--------------------+--------------------------------------------------------------+
| Actor              | Description                                                  |
+====================+==============================================================+
| **Member**         | A user with an active membership in the tenant's             |
|                    | association. Can browse resources, book slots, and cancel    |
|                    | confirmed bookings within the deadline. Has access to a      |
|                    | restricted admin area to view and cancel own confirmed        |
|                    | bookings.                                                    |
+--------------------+--------------------------------------------------------------+
| **Volunteer**      | A trusted member with elevated rights. Manages resources,    |
|                    | weekly openings, calendars, and cancellation policies via the |
|                    | Django admin panel. Can view and cancel any booking.         |
+--------------------+--------------------------------------------------------------+
| **Public visitor** | An anonymous user who can view the public booking page but   |
|                    | cannot book (booking requires membership).                   |
+--------------------+--------------------------------------------------------------+


## 3. Core Concepts

### 3.1 Schema Models

The Django models that persist data for the booking module.

#### 3.1.1 Resource

A bookable entity. Examples: "Salle de réunion A", "Imprimante 3D Prusa",
"Bureau coworking 1". Availability is controlled via a Calendar
(see 3.1.3), not by an active flag.

**Core logic attributes:**

+-------------------------------+-----------------+---------------------------------------------+
| Field                         | Type            | Description                                 |
+===============================+=================+=============================================+
| `calendar`                    | FK              | Calendar that governs this resource's       |
|                               |                 | closed periods                              |
+-------------------------------+-----------------+---------------------------------------------+
| `capacity`                    | integer         | Max simultaneous bookings per slot          |
|                               |                 | (1 = exclusive)                             |
+-------------------------------+-----------------+---------------------------------------------+
| `cancellation_deadline_hours` | integer         | Hours before slot start within which        |
|                               |                 | cancellation is still allowed               |
+-------------------------------+-----------------+---------------------------------------------+
| `booking_horizon_days`        | integer         | How far ahead a member can book             |
|                               |                 | (e.g. 28 = no booking beyond 28 days)       |
+-------------------------------+-----------------+---------------------------------------------+
| `weekly_opening`              | FK              | Weekly opening schedule applied to this     |
|                               |                 | resource                                    |
+-------------------------------+-----------------+---------------------------------------------+
| `pricing_rule`                | FK              | TiBillet Price object applied to bookings   |
|                               |                 | on this resource                            |
+-------------------------------+-----------------+---------------------------------------------+

Note:

- `capacity` can be equal to 0, thus desactivating the ressource.


**Presentation attributes:**

+---------------+-----------------+-----------------------------------------------+
| Field         | Type            | Description                                   |
+===============+=================+===============================================+
| `name`        | string          | Display name                                  |
+---------------+-----------------+-----------------------------------------------+
| `group`       | FK              | Optional grouping                             |
+---------------+-----------------+-----------------------------------------------+
| `description` | text            | Rich description shown on the public page     |
+---------------+-----------------+-----------------------------------------------+
| `image`       | url             | Optional photo                                |
+---------------+-----------------+-----------------------------------------------+
| `tags`        | list of strings | Free-form labels for filtering and display    |
|               |                 | (e.g. "salle", "machine")                     |
+---------------+-----------------+-----------------------------------------------+


#### 3.1.2 Resource Group

A Resource Group is an optional organisational layer that clusters related
resources for display on the public booking page. For example, "Salles de
répétitions" groups "Salle Verte", "Salle Rouge", and "Salle Rose".

A group has no booking logic of its own. Bookings are always made on a
concrete Resource, not on a group. The group only affects presentation:
the public page shows resources grouped together, and the member picks a
specific resource within the group before booking.

**Attributes:**

+---------------+-----------------+-----------------------------------------------+
| Field         | Type            | Description                                   |
+===============+=================+===============================================+
| `name`        | string          | Display name, e.g. "Salles de répétitions"    |
+---------------+-----------------+-----------------------------------------------+
| `description` | text            | Optional description shown on the public page |
+---------------+-----------------+-----------------------------------------------+
| `image`       | url             | Optional photo                                |
+---------------+-----------------+-----------------------------------------------+
| `tags`        | list of strings | Free-form labels (same role as on Resource)   |
+---------------+-----------------+-----------------------------------------------+

**Rules:**

- A resource belongs to at most one group. Group is optional.
- A resource not assigned to any group is displayed individually on the
  public page.
- Groups are purely presentational: no business rules derive from group
  membership.


#### 3.1.3 Calendar

A Calendar defines when resources are closed or open. An association can
have one or several calendars (e.g. one for all rooms, one for machines).
Outside of declared closed periods, a resource is implicitly open.

**Attributes:**

+--------+--------+----------------------------------------------------+
| Field  | Type   | Description                                        |
+========+========+====================================================+
| `name` | string | e.g. "Calendrier principal", "Calendrier machines" |
+--------+--------+----------------------------------------------------+

A Calendar contains a set of **ClosedPeriod** entries:

+--------------+--------------+------------------------------------------------+
| Field        | Type         | Description                                    |
+==============+==============+================================================+
| `calendar`   | FK           | Parent calendar                                |
+--------------+--------------+------------------------------------------------+
| `label`      | string       | Optional description                           |
|              |              | (e.g. "Congés d'été", "Jour férié")            |
+--------------+--------------+------------------------------------------------+
| `start_date` | date         | First day of the closed period (inclusive)     |
+--------------+--------------+------------------------------------------------+
| `end_date`   | date or null | Last day of the closed period (inclusive).     |
|              |              | Equal to `start_date` for a single day off.    |
|              |              | `null` = closed indefinitely.                  |
+--------------+--------------+------------------------------------------------+

**Rules:**

- Slots that fall within a ClosedPeriod are excluded when computing
  availability on the fly.
- ClosedPeriods can overlap without conflict.
- Adding a ClosedPeriod over dates that already have confirmed bookings
  does **not** automatically cancel those bookings. The volunteer handles
  them manually.
- A single day off is modelled as a ClosedPeriod where
  `start_date == end_date`.
- `end_date` >= `start_date` (if not null)

#### 3.1.4 Weekly Opening

A reusable weekly opening schedule. It defines which time slots are open
on which days of the week. A template can be shared across multiple
resources. Temporal exceptions (holidays, closures) are handled
exclusively by the Calendar.

**v1 constraint:** a resource has exactly one weekly opening at a time.
Multiple templates per resource (e.g. a summer vs. winter schedule) are
out of scope for v1 and would require a date-ranged assignment model.

**Non-overlap constraint:** within a given Weekly Opening, OpeningEntries
must not overlap each other. The system must reject any OpeningEntry whose
generated time window intersects with an existing one. This check is
non-trivial because:

- An OpeningEntry can bleed into the next day if
  `start_time + slot_count × slot_duration_minutes > 24h`.
- The last OpeningEntry of the week (e.g. Sunday) can bleed into the
  first OpeningEntry of the week (Monday), creating a wrap-around
  overlap.

The overlap check must therefore treat the weekly schedule as a circular
7-day timeline and compare all OpeningEntry windows modulo 7 days.

As a consequence: the longest possible opengings is a slot that cover
a full week or a partition of that.

**Attributes:**

+--------+--------+------------------------------------------+
| Field  | Type   | Description                              |
+========+========+==========================================+
| `name` | string | e.g. "Horaires standard", "Horaires été" |
+--------+--------+------------------------------------------+

A Weekly Opening contains a set of **OpeningEntry** rows, each defining
one recurring slot:

+-------------------------+---------+------------------------------------------+
| Field                   | Type    | Description                              |
+=========================+=========+==========================================+
| `weekly_opening`        | FK      | Parent weekly opening                    |
+-------------------------+---------+------------------------------------------+
| `weekday`               | enum    | `mon`, `tue`, `wed`, `thu`,              |
|                         |         | `fri`, `sat`, `sun`                      |
+-------------------------+---------+------------------------------------------+
| `start_time`            | time    | Start of the first slot, e.g. `10:00`   |
+-------------------------+---------+------------------------------------------+
| `slot_duration_minutes` | integer | Duration of each slot in minutes,        |
|                         |         | e.g. `60`                                |
+-------------------------+---------+------------------------------------------+
| `slot_count`            | integer | Number of consecutive slots generated    |
|                         |         | from `start_time`                        |
+-------------------------+---------+------------------------------------------+

**Example:** `weekday=mon, start_time=10:00, slot_duration_minutes=60,
slot_count=5` generates: 10:00–11:00, 11:00–12:00, 12:00–13:00,
13:00–14:00, 14:00–15:00.


#### 3.1.5 Pricing

TiBillet already has a Product + Price model that covers all pricing
needs for the booking module. Rather than introducing a custom
PricingRule model, each bookable resource is backed by a TiBillet
**Product**, and pricing is configured via the existing **Price** model,
which provides:

- `prix` — the amount (0 for free slots).
- `adhesion_obligatoire` — optional FK to a membership product; gates
  booking to members of that type.
- `max_per_user` — **not used for bookings.** Availability is naturally
  constrained by capacity and time; no per-member cap is applied.
- `vat` — inherited VAT handling.

The `pricing_rule` FK on Resource (see 3.1.1) therefore points to a
TiBillet **Price** object, not a custom model.

> **Open question (core team):** confirm the correct way to integrate
> the booking product into the existing Product model (correct
> `categorie_article` value, any required flags, etc.).


#### 3.1.6 Booking

A Booking is a fully self-contained record. It stores the actual agreed
time explicitly, independently of the resource's current Weekly Opening.
This means:

- If the Weekly Opening changes after a booking is made, existing
  bookings are unaffected.
- Volunteers can create bookings that do not correspond to any slot in
  the template (e.g. exceptional one-off reservations).

Cancellation is modelled as deletion of the Booking row — no cancelled
state is stored.

**Attributes:**

+-------------------------+--------------------+------------------------------------------+
| Field                   | Type               | Description                              |
+=========================+====================+==========================================+
| `resource`              | FK                 | The booked resource                      |
+-------------------------+--------------------+------------------------------------------+
| `start_datetime`        | datetime (tz-aware)| Start of the booking, in the tenant's    |
|                         |                    | venue timezone                           |
+-------------------------+--------------------+------------------------------------------+
| `slot_duration_minutes` | integer            | Duration of each slot unit in minutes    |
+-------------------------+--------------------+------------------------------------------+
| `slot_count`            | integer            | Number of consecutive slot units booked  |
+-------------------------+--------------------+------------------------------------------+
| `user`                  | FK → TiBillet User | The member who made the booking          |
+-------------------------+--------------------+------------------------------------------+
| `status`                | enum               | `new` — in basket, pending user          |
|                         |                    | validation;                              |
|                         |                    | `validated` — pending payment;           |
|                         |                    | `confirmed` — payment done.              |
|                         |                    | Free slots (`prix = 0`) skip             |
|                         |                    | `validated` and go directly from         |
|                         |                    | `new` to `confirmed`.                    |
+-------------------------+--------------------+------------------------------------------+
| `booked_at`             | datetime           | When the booking was created             |
+-------------------------+--------------------+------------------------------------------+
| `payment_ref`           | string or null     | Reference to the TiBillet                |
|                         |                    | wallet/cashless transaction, set on      |
|                         |                    | confirmation                             |
+-------------------------+--------------------+------------------------------------------+


### 3.2 Booking Logic

The booking logic is triggered by two kinds of user requests:

1. **Slot browsing** — a member (or public visitor) opens the booking
   page for a resource and asks: "which slots are available, and how
   many places remain in each?" The system returns the set E of bookable
   intervals for that resource over a date range.

2. **Booking request** — a member submits a request to book a specific
   start time, duration, and slot count on a resource. The system checks
   the request against E and, if valid, creates the booking B.

In both cases the same pipeline is evaluated on the fly from the stored
models. None of the intermediate sets are persisted.

**O** — normalized open-day intervals
:   `Calendar + ClosedPeriods`

**W** — theoretical slots
:   `WeeklyOpening + O`

**E** — bookable intervals, annotated with capacity
:   `W + capacity from DB`

**B** — a booking
:   `member selection from E`

All datetimes are timezone-aware, using the tenant's venue timezone.


#### 3.2.1 O — Normalized Open-Day Intervals

**Purpose.** The Calendar records which days the venue is closed (see
§3.1.3). O is the complement: the set of continuous time spans during
which the venue is open. It answers the question "on which stretches of
time is this resource potentially available?" before any opening
schedule is applied.

**Computation window.** O is always computed over a finite window
`[date_from, date_to]`, supplied by the user request:

- For slot browsing, `date_from` is today and `date_to` is
  `today + booking_horizon_days`. "Today" is resolved in the tenant's
  venue timezone, not in UTC.
- For a booking request, `date_from` is the date the booking starts
  and `date_to` is the date it ends — which may be later than
  `date_from` when the booking spans multiple days.

**Definition.** Given the Calendar's ClosedPeriods (see §3.1.3), O is
the complement of the closed set within the window
`[date_from 00:00 local, date_to+1 00:00 local)`.

Each ClosedPeriod (`start_date`, `end_date`) — stored as naive
`DateField` values — defines a closed span
`[start_date 00:00 local, end_date+1 00:00 local)`. When periods
overlap or are adjacent, they are merged. `end_date = None` extends
the closure to the end of the window.

O is then the set of gaps that remain:

```
O = complement of merged_closed_periods
    within [date_from 00:00, date_to+1 00:00)
```

Example (Europe/Paris, CEST = +02:00, window = full summer):
`date_from = 2026-07-01`, `date_to = 2026-08-31`

```
ClosedPeriods: 2026-07-14 → 2026-07-20,  2026-08-15 (single day)

O = [
  [2026-07-01 00:00+02, 2026-07-14 00:00+02),
  [2026-07-21 00:00+02, 2026-08-15 00:00+02),
  [2026-08-16 00:00+02, 2026-09-01 00:00+02),
]
```


#### 3.2.2 W — Theoretical Slots

**Purpose.** The WeeklyOpening (see §3.1.4) defines a repeating weekly
pattern of time windows. W is that pattern unrolled over the open-day
intervals O: the set of concrete time slots that the resource offers
during open days. It answers the question "given the opening schedule,
on which specific time windows could a booking exist?"

**Definition.** For each OpeningEntry in the WeeklyOpening, and for
each occurrence of its weekday within the computation window,
`slot_count` consecutive half-open intervals of `slot_duration_minutes`
are generated starting at `start_time`. A generated slot is included
in W if and only if it is fully contained within some open-day interval
`o ∈ O`:

```
w ∈ W  ⟺  ∃ o ∈ O,  w ⊆ o
```

A slot that straddles a boundary of O is rejected entirely — it is
never trimmed. Three consequences worth noting:

- A slot that starts on an open day but ends on a closed day is
  excluded.
- A slot that starts on a closed day but ends on the next open day is
  excluded.
- A multi-day slot that starts and ends on open days but crosses a
  closed day in the middle is excluded.


#### 3.2.3 E — Bookable Intervals

**Purpose.** W contains every slot the opening schedule produces over
open days, with no regard for how those slots are already booked. E is W
enriched with real-time capacity information in order to define what a
member can actually book right now, It is the set the member sees on the
booking page: each element is a slot that is open, reachable within the
booking horizon, and shows how many places are still available. It is
also the set which will be used to validate a booking request.

**Definition.** E is W annotated with two capacity fields:

- **max_capacity** — the resource's capacity (see §3.1.1), constant
  across all intervals.
- **remaining_capacity(w)** — units still available for interval `w`:

```
remaining_capacity(w) = max_capacity − |{ x ∈ DB | x overlaps w }|
```

DB is all existing bookings whatever their status. Two intervals
overlap when their intersection is not empty. Partial overlap counts
as full. `remaining_capacity` is clamped to 0 (never negative).

> **Business rule.** A member who books a slot gets full ownership of
> the resource for its entire duration. Any existing booking that
> touches the slot — even briefly — already occupies the resource, so
> the available capacity decreases by one for the whole slot.


#### 3.2.4 B — A Booking

**Purpose.** E tells the member which slots exist and how many places
remain. B is the member's choice: one or more consecutive slots from E
that they want to reserve. It answers the question "is this specific
booking request valid, and can it be created?"

**Definition.** A booking is a series of `k` consecutive half-open
intervals, each of duration `T`, starting at a chosen start time `p`:

```
B = { [p, p+T), [p+T, p+2T), …, [p+(k-1)T, p+kT) }
```

This maps directly to the Booking model (see §3.1.6): `p` is
`start_datetime`, `T` is `slot_duration_minutes`, and `k` is
`slot_count`.

**Member booking.** The UI presents elements of E, but the booking
request arrives as a plain HTTP POST — the server cannot trust that
`p`, `T`, and `k` are aligned to any slot in E. The server must
therefore verify the request against E explicitly. The validity rule is:

```
Let E' = { e ∈ E | remaining_capacity(e) > 0 }
B is valid  ⟺  B ⊆ E'
```

Each element of B must be exactly a slot present in E' — same start,
same duration. This single condition captures alignment, availability,
and the gap constraint: if a closed day falls within the consecutive
sequence of B, the corresponding slot is absent from E' and the
inclusion fails. If a member needs slots across two separate open
windows, they submit two booking requests.

**Volunteer booking.** The volunteer may create ad-hoc bookings at any
start time and duration via the admin panel (see §4.3), with no
alignment constraint. Such bookings bypass the E validity rule but
still decrease `remaining_capacity` for any overlapping slot.

> **Concurrency.** E is computed from a snapshot of the database at
> request time. Two concurrent booking requests for the last available
> slot can both see `remaining_capacity = 1`, both pass validation, and
> both succeed — leaving the resource overbooked. The server must
> therefore enforce the capacity constraint atomically: re-check
> `remaining_capacity` inside a database transaction with a row-level
> lock on the affected slots before inserting the Booking row.


## 4. User Flows

### 4.1 Member — Browse & Book

1. Member visits the public booking page (or the embedded widget on the
   association's site).
2. Member browses resources, optionally filtering by tag. Each resource shows its
   next available slots.
3. Member selects a slot. If not logged in, they are redirected to login.
4. Member chooses how many consecutive slots they want (`slot_count`).
5. System checks: membership valid (if `adhesion_obligatoire` is set on the Price),
   slot within `booking_horizon_days`, remaining capacity > 0.
6. Booking is created with status `new`. The unit is reserved but not yet paid.
   Member is asked if they want to add more bookings to their basket before
   proceeding to validation.
7. Member reviews their basket and confirms. Bookings move to status `validated`.
8. If the slot is free (`prix = 0`), bookings move directly to `confirmed` with no
   payment step. Otherwise payment is processed via TiBillet (wallet, cashless, or
   credit card). If payment fails or the balance is insufficient, bookings are
   refused with a clear error and deleted.
9. On payment success, bookings move to status `confirmed`. Member receives a
   confirmation notification.

### 4.2 Member — Cancel a Booking

Only `confirmed` bookings can be cancelled through this flow. `new` and
`validated` bookings are removed from the basket management page (see §4.1,
steps 6–7) with no refund, as no payment has been collected.

1. Member opens their account administration page and views their upcoming
   `confirmed` bookings.
2. Member requests cancellation of a booking from the account administration
   page.
3. System checks whether the cancellation deadline has passed: the current time
   must be before the booking start time minus the resource's cancellation
   deadline.
4. If past the deadline: cancellation is refused; member is shown the deadline.
5. If before the deadline: booking is deleted, wallet/cashless refunded
   automatically if applicable. Member receives a cancellation confirmation
   notification.

### 4.3 Volunteer — Manage Resources

1. Volunteer accesses the booking admin panel within TiBillet backoffice.
2. Volunteer creates/edits ResourceGroups to organise resources for display on
   the public page.
3. Volunteer creates/edits Resources, assigns a Weekly Opening, a Calendar, and a
   Price. Resources can optionally be assigned to a ResourceGroup.
4. Volunteer manages Calendars: creates ClosedPeriods for holidays or extended
   closures.
5. Volunteer views all bookings for any resource (list + calendar view), filterable
   by date and status.
6. Volunteer can delete any booking on behalf of a member. No automatic refund is
   triggered; any refund is handled manually by the volunteer.
7. Volunteer can create an ad-hoc booking for any resource, date, and time,
   regardless of the Weekly Opening.

### 4.4 Public Booking Page

- Accessible without login (URL structure is an implementation detail).
- Shows all resources with their next available slots. Resources with no upcoming
  availability are shown but greyed out.
- Slots already full (`remaining_capacity = 0`) are shown as unavailable.
- Clicking a slot prompts login if not authenticated.
- Embeddable as an `<iframe>` on external sites.
- URL parameters allow filtering by tag.


## 5. Business Rules

### Availability and Capacity

- Slots are computed on the fly from the resource's Weekly Opening and Calendar;
  nothing is pre-generated or stored.
- A slot is generated only if every day it intersects is open: for each date
  from `start_datetime.date()` to `end_datetime.date()` (inclusive), the date
  must not fall within a `ClosedPeriod`. A slot may span multiple days as long
  as none of those days is closed.
- **Member bookings** must be aligned with the computed slots in E: each slot in
  the request must match exactly an element of E' (same start, same duration).
  The server verifies this explicitly — it cannot trust the HTTP POST (see
  §3.2.4).
- A member may hold any number of bookings on the same resource, as long as
  capacity allows.
- **Volunteer bookings** (created via the admin panel) are not required to be
  aligned with computed slots. A volunteer may choose an arbitrary start time and
  duration (e.g. 10:12 for 12 minutes while the opening defines 60-minute slots
  starting at 10:00). The E validity rule does not apply, but the booking still
  decreases `remaining_capacity` for any overlapping slot.
- Any booking (member or volunteer) decreases `remaining_capacity` by 1 for
  every computed slot it overlaps, even partially. Two intervals overlap when
  their intersection is not empty (see §3.2.3).
- A computed slot is considered unavailable when its `remaining_capacity = 0`,
  i.e. all units are covered by at least one overlapping booking regardless of
  of their status.
- When a member books multiple consecutive slots (`slot_count > 1`), all slots in
  the range must be available before the booking is created.
- Slots outside the resource's `booking_horizon_days` window are never surfaced to
  members.
- A member can book any slot whose start time is strictly in the future. There
  is no minimum advance notice: a slot starting in a few minutes is bookable
  as long as it has not started yet and capacity allows.

### Pricing & Membership

- Pricing and membership eligibility are checked at booking validation time.
- Free slots (`prix = 0`) skip the payment step entirely: status transitions
  directly from `new` to `confirmed`, bypassing `validated`.

### Cancellation

- Cancellation is modelled as deletion of the Booking row. No cancelled state is
  stored.
- Only `confirmed` bookings are cancellable through the member account
  administration page. `new` and `validated` bookings are removed from the
  basket management page; no refund applies as no payment has been collected.
- Cancellation deadline is configured per resource. Default: 24 hours before
  slot start.
- **Member cancellation** (own `confirmed` booking via account administration):
  wallet/cashless refunded automatically if applicable.
- **Volunteer cancellation** (any booking via backoffice): no automatic refund.
  Any refund is handled manually by the volunteer.

> **Open question (core team):** what is the refund behaviour for credit card
> payments on cancellation?

### Basket & Timeouts

- A member's basket can hold multiple `new` bookings before validation.
- A `new` booking that is not validated within a set timeout is automatically
  deleted, freeing the unit. Default timeout: 15 minutes. To be implemented as a
  periodic cleanup task (e.g. Celery beat).

> **Open question (core team):** should `validated` bookings also expire, and if so
> with a different timeout than `new`?

> **Open question (core team):** does the timeout apply per individual booking, or
> per basket session?


## 6. Integration with TiBillet

+-------------------------------------+----------------------------------------------+
| TiBillet system                     | Integration point                            |
+=====================================+==============================================+
| **Membership**                      | Booking eligibility check via                |
|                                     | `adhesion_obligatoire` on the Price object   |
+-------------------------------------+----------------------------------------------+
| **Product / Price**                 | Each bookable resource is backed by a        |
|                                     | TiBillet Product; pricing uses the existing  |
|                                     | Price model                                  |
+-------------------------------------+----------------------------------------------+
| **Wallet / Cashless / Credit card** | Payment and refund on cancellation handled   |
|                                     | by existing TiBillet payment machinery       |
+-------------------------------------+----------------------------------------------+
| **Auth / Users**                    | Login required to book; volunteer role from  |
|                                     | existing permission system                   |
+-------------------------------------+----------------------------------------------+
| **Federated agenda**                | Out of scope v1 — bookable resources are not |
|                                     | published to the federated agenda            |
+-------------------------------------+----------------------------------------------+
| **HDA / htmx**                      | All views follow existing TiBillet HDA       |
|                                     | conventions; server returns HTML fragments,  |
|                                     | no JSON API layer                            |
+-------------------------------------+----------------------------------------------+


## 7. Server-side Views & Hypermedia Interactions

TiBillet is a Hypermedia-Driven Application (HDA). The server returns HTML
fragments; interactions are driven by HTTP requests with HTML responses via
htmx. There is no JSON API layer for the booking module. All views follow
the existing TiBillet HDA conventions.

### 7.0 Page Structure

```
booking/booking_base.html
    ├── #basket-container       (always at top — OOB-updated after every booking)
    ├── {% block booking_content %}
    │       ├── home.html
    │       │       └── partial/card.html  (one per resource)
    │       │               └── partial/slot_list.html
    │       │                       └── partial/slot_row.html  (one per slot)
    │       └── resource.html
    │               └── partial/slot_list.html
    │                       └── partial/slot_row.html  (one per slot)
    └── HTMX 422 swap handler
```

Each slot row has a stable DOM id `slot-<resource_pk>-<YmdHi>`. Clicking
an available row replaces it (outerHTML) with `booking_form.html`, which
carries the same id. On submit, the form is replaced back by the updated
`slot_row.html` (via outerHTML); `#basket-container` is updated in the
same response via HTMX OOB swap. No page reload is needed.

### 7.1 Web Pages

#### Home — Resource Catalogue

- URL: `GET /booking/`
- Auth: public
- Template: `booking/views/home.html`
- List of all resources with their next available slot. Tag filter via
  `?tag=`. Resources with no upcoming availability are shown greyed out.

#### Resource Page

- URL: `GET /booking/resource/{resource_pk}/`
- Auth: public
- Template: `booking/views/resource.html`

**What the member sees:**

The slot list is grouped by date. For each date, every slot is shown:

+---------------------+---------------------------------------------------+
| Slot state          | Presentation & action                             |
+=====================+===================================================+
| Available           | Clickable link showing the time range.            |
|                     | Click → `GET booking_form` → the slot row         |
|                     | (`<li id="slot-<pk>-<YmdHi>">`) is replaced       |
|                     | in-place by the booking form (outerHTML swap).    |
|                     | Rendered by `partial/slot_row.html` (shared).     |
|                     | If not logged in → redirect to login.             |
+---------------------+---------------------------------------------------+
| Full                | Inert badge "Complet". Not clickable.             |
+---------------------+---------------------------------------------------+
| Past / beyond       | Not shown.                                        |
| horizon             |                                                   |
+---------------------+---------------------------------------------------+

### 7.2 Web Components

HTMX partials — replace a specific DOM fragment, never the full page.

#### Booking Form

- URL: `GET /booking/resource/{resource_pk}/booking_form/?start=<ISO-tz>`
- Auth: member
- Target: `#slot-<resource_pk>-<YmdHi>` (the slot row, outerHTML swap)

**What the member sees:** the booking form rendered inline in place of the
slot row. Shows the chosen start time, a `slot_count` picker (1 to max
consecutive available slots), and the total price.

**Action:** submit → `POST add_to_basket`.

- Success → the form `<li>` is replaced by the updated `slot_row.html`
  (same outerHTML target); `#basket-container` is updated via OOB swap
  in the same response. No page reload.
- Error (422) → the form `<li>` is replaced by itself with an error
  message and a "Réessayer" link that re-opens the booking form.

#### Add to Basket

- URL: `POST /booking/resource/{resource_pk}/add_to_basket/`
- Auth: member
- Target (success): `#slot-<resource_pk>-<YmdHi>` (outerHTML) + OOB
  `#basket-container`
- Target (error): `#slot-<resource_pk>-<YmdHi>` (outerHTML, form with
  error)

Creates a `new` booking for the chosen slot(s) and returns the updated
basket. On validation failure returns the form with an error message.

#### Remove from Basket

- URL: `POST /booking/{booking_pk}/remove_from_basket/`
- Auth: member
- Target: `#basket-container`

Deletes the `new` booking and returns the refreshed basket.

#### Basket

- URL: `GET /booking/basket/`
- Auth: member
- Target: `#basket-container`

**What the member sees:** list of `new` bookings (resource, time range,
price per line), total, a remove button per line, and a "Confirmer"
button.

**Action:** "Confirmer" → `POST validate_basket`.

#### Basket Confirmed

- URL: `POST /booking/validate_basket/`
- Auth: member
- Target: `#basket-container`

Moves all `new` bookings to `confirmed` (via payment if `prix > 0`) and
returns a confirmation partial. On payment failure returns an error
partial and the bookings are deleted.

#### Cancel Booking

- URL: `POST /booking/cancel/`
- Auth: member
- Target: `#basket-container` (empty on success)

**Action:** member clicks "Annuler" on a `confirmed` booking in their
account. Returns empty HTML on success; error partial if past the
cancellation deadline.

### 7.3 Member Account Administration

Members have access to a restricted area of the Django admin panel.
Unlike volunteers, a member can only view and act on their own bookings.

+-----------------+--------------+----------------------------------------------+
| Model           | Admin type   | Member permissions                           |
+=================+==============+==============================================+
| Booking (own)   | `ModelAdmin` | List own upcoming bookings; cancel (delete)  |
|                 |              | own bookings before the cancellation         |
|                 |              | deadline                                     |
+-----------------+--------------+----------------------------------------------+

### 7.4 Volunteer Backoffice

The volunteer backoffice is managed entirely by the Django admin panel.
No custom views are required for resource management, weekly openings,
calendars, or booking administration.

Django admin registration:

+-----------------+--------------+-----------------------+
| Model           | Admin type   | Inline children       |
+=================+==============+=======================+
| ResourceGroup   | `ModelAdmin` | —                     |
+-----------------+--------------+-----------------------+
| Resource        | `ModelAdmin` | —                     |
+-----------------+--------------+-----------------------+
| WeeklyOpening   | `ModelAdmin` | OpeningEntry (inline) |
+-----------------+--------------+-----------------------+
| Calendar        | `ModelAdmin` | ClosedPeriod (inline) |
+-----------------+--------------+-----------------------+
| Booking         | `ModelAdmin` | —                     |
+-----------------+--------------+-----------------------+

## 8. Open Questions

These need resolution before implementation begins. Questions marked **(core team)**
should be discussed with the TiBillet core team.

1. **Product integration (core team)** — What is the correct `categorie_article`
   value and required flags to use for bookable resources in the existing TiBillet
   Product model?

2. **Credit card refunds (core team)** — What is the expected refund behaviour for
   credit card payments on booking cancellation?

3. **Basket timeouts (core team)** — Should `validated` bookings (payment initiated)
   also expire? Does the `new` timeout apply per individual booking or per basket
   session?

4. **Notification channel** — Email only, or integrate with TiBillet's existing
   notification system? Should volunteers be notified on each new booking?

5. **Public page i18n** — Should the public booking page respect the tenant's
   language setting or the browser's?

6. **Resource ordering** — How should resources be ordered on the public page?
   Volunteer-defined manual order, or alphabetical?


## 9. Out of Scope (v1)

- Recurring bookings (member books "every Monday 9–10am")
- Multiple weekly openings per resource (e.g. summer vs. winter schedule)
- Cross-tenant / federated resource sharing
- Publication of bookable resources to the federated agenda
- Waitlist when a slot is full
- Native mobile app (Web Rulez, web is king!)
- QR code check-in at resource location
- Usage analytics / reporting dashboard
- Free form booking (not constrainted by recurring slots) not planned
