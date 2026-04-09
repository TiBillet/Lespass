# TiBillet — Booking Module Specification

**Version:** v0.5
**Status:**  Ready for review by TiBillet core team
**Date:**    2026-04-09
**Author:**  Joris REHM
**Note:**    This version was produced in a pair specification session with Claude AI (Anthropic)

Changes:

  - 0.5 Slot: replace date+start_time+end_time with start_datetime+end_datetime
         (timezone-aware, consistent with Booking.start_datetime — decisions §2)
  - 0.4 Rename SlotTemplate to WeeklyOpening
    and SlotEntry to OpeningEntry

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
|                    | within the deadline.                                         |
+--------------------+--------------------------------------------------------------+
| **Volunteer**      | A trusted member with elevated rights. Manages resources,    |
|                    | weekly openings, calendars, and cancellation policies via the |
|                    | Django admin panel. Can view and cancel any booking.         |
+--------------------+--------------------------------------------------------------+
| **Public visitor** | An anonymous user who can view the public booking page but   |
|                    | cannot book (booking requires membership).                   |
+--------------------+--------------------------------------------------------------+


## 3. Core Concepts

### 3.1 Resource

A bookable entity. Examples: "Salle de réunion A", "Imprimante 3D Prusa",
"Bureau coworking 1". Availability is controlled via a Calendar (see 3.3),
not by an active flag.

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
| `weekly_opening`               | FK              | Weekly opening schedule applied to this     |
|                               |                 | resource                                    |
+-------------------------------+-----------------+---------------------------------------------+
| `pricing_rule`                | FK              | TiBillet Price object applied to bookings   |
|                               |                 | on this resource                            |
+-------------------------------+-----------------+---------------------------------------------+

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


### 3.2 Resource Group

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


### 3.3 Calendar

A Calendar defines when resources are closed or open. An association can have one or
several calendars (e.g. one for all rooms, one for machines). Outside of declared
closed periods, a resource is implicitly open.

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

- Slots that fall within a ClosedPeriod are excluded when computing availability
  on the fly.
- ClosedPeriods can overlap without conflict.
- Adding a ClosedPeriod over dates that already have confirmed bookings does
  **not** automatically cancel those bookings. The volunteer handles them manually.
- A single day off is modelled as a ClosedPeriod where `start_date == end_date`.


### 3.4 Weekly Opening

A reusable weekly opening schedule. It defines which time slots are open on which
days of the week. A template can be shared across multiple resources. Temporal
exceptions (holidays, closures) are handled exclusively by the Calendar.

**v1 constraint:** a resource has exactly one weekly opening at a time. Multiple
templates per resource (e.g. a summer vs. winter schedule) are out of scope for v1
and would require a date-ranged assignment model.

**Non-overlap constraint:** within a given Weekly Opening, SlotEntries must not
overlap each other. The system must reject any OpeningEntry whose generated time window
intersects with an existing one. This check is non-trivial because:

- A OpeningEntry can bleed into the next day if
  `start_time + slot_count × slot_duration_minutes > 24h`.
- The last OpeningEntry of the week (e.g. Sunday) can bleed into the first OpeningEntry
  of the week (Monday), creating a wrap-around overlap.

The overlap check must therefore treat the weekly schedule as a circular 7-day
timeline and compare all OpeningEntry windows modulo 7 days.

**Attributes:**

+--------+--------+------------------------------------------+
| Field  | Type   | Description                              |
+========+========+==========================================+
| `name` | string | e.g. "Horaires standard", "Horaires été" |
+--------+--------+------------------------------------------+

A Weekly Opening contains a set of **OpeningEntry** rows, each defining one recurring
slot:

+-------------------------+---------+------------------------------------------+
| Field                   | Type    | Description                              |
+=========================+=========+==========================================+
| `template`              | FK      | Parent weekly opening                     |
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

**Example:** `weekday=mon, start_time=10:00, slot_duration_minutes=60, slot_count=5`
generates: 10:00–11:00, 11:00–12:00, 12:00–13:00, 13:00–14:00, 14:00–15:00.


### 3.5 Slot

A Slot is a virtual, non-persisted concept. Slots are computed on the fly by the
application from three inputs:

- The resource's **WeeklyOpening** (weekdays, start time, duration, count).
- The resource's **Calendar** (ClosedPeriods are excluded).
- The resource's **`booking_horizon_days`** (slots beyond the horizon are not
  surfaced).

No Slot rows are stored in the database. The application computes and returns them
dynamically when a client requests availability.

**Computed fields exposed by the application:**

+-------------------------+----------+------------------------------------------+
| Field                   | Type     | Description                              |
+=========================+==========+==========================================+
| `resource_id`           | id       | Parent resource                          |
+-------------------------+----------+------------------------------------------+
| `start_datetime`        | datetime | Timezone-aware start of the slot.        |
|                         |          | Derived from OpeningEntry + date.        |
+-------------------------+----------+------------------------------------------+
| `end_datetime`          | datetime | Timezone-aware end of the slot.          |
|                         |          | `start_datetime + slot_duration_minutes` |
+-------------------------+----------+------------------------------------------+
| `slot_duration_minutes` | integer  | Duration of the slot in minutes          |
+-------------------------+----------+------------------------------------------+
| `remaining_capacity`    | integer  | `capacity − count of overlapping         |
|                         |          | bookings`. 0 = slot is full.             |
+-------------------------+----------+------------------------------------------+


### 3.6 Pricing

TiBillet already has a Product + Price model that covers all pricing needs for the
booking module. Rather than introducing a custom PricingRule model, each bookable
resource is backed by a TiBillet **Product**, and pricing is configured via the
existing **Price** model, which provides:

- `prix` — the amount (0 for free slots).
- `adhesion_obligatoire` — optional FK to a membership product; gates booking to
  members of that type.
- `max_per_user` — **not used for bookings.** Availability is naturally constrained
  by capacity and time; no per-member cap is applied.
- `vat` — inherited VAT handling.

The `pricing_rule` FK on Resource (see 3.1) therefore points to a TiBillet **Price**
object, not a custom model.

> **Open question (core team):** confirm the correct way to integrate the booking
> product into the existing Product model (correct `categorie_article` value, any
> required flags, etc.).


### 3.7 Booking

A Booking is a fully self-contained record. It stores the actual agreed time
explicitly, independently of the resource's current Weekly Opening. This means:

- If the Weekly Opening changes after a booking is made, existing bookings are
  unaffected.
- Volunteers can create bookings that do not correspond to any slot in the template
  (e.g. exceptional one-off reservations).

Cancellation is modelled as deletion of the Booking row — no cancelled state is
stored.

**Attributes:**

+-------------------------+--------------------+------------------------------------------+
| Field                   | Type               | Description                              |
+=========================+====================+==========================================+
| `resource`              | FK                 | The booked resource                      |
+-------------------------+--------------------+------------------------------------------+
| `date`                  | date               | Date of the booking                      |
+-------------------------+--------------------+------------------------------------------+
| `start_time`            | time               | Start time of the booking                |
+-------------------------+--------------------+------------------------------------------+
| `slot_duration_minutes` | integer            | Duration of each slot unit in minutes    |
+-------------------------+--------------------+------------------------------------------+
| `slot_count`            | integer            | Number of consecutive slot units booked  |
| `member`                | FK → TiBillet User | The member who made the booking          |
+-------------------------+--------------------+------------------------------------------+
| `status`                | enum               | `new` — in basket, pending user          |
|                         |                    | validation;                              |
|                         |                    | `validated` — pending payment;           |
|                         |                    | `confirmed` — payment done               |
+-------------------------+--------------------+------------------------------------------+
| `booked_at`             | datetime           | When the booking was created             |
+-------------------------+--------------------+------------------------------------------+
| `payment_ref`           | string or null     | Reference to the TiBillet                |
|                         |                    | wallet/cashless transaction, set on      |
|                         |                    | confirmation                             |
+-------------------------+--------------------+------------------------------------------+


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

1. Member views their upcoming confirmed bookings in their TiBillet account
   dashboard.
2. Member requests cancellation.
3. System checks whether the cancellation deadline has passed: the current time must
   be before the booking start time minus the resource's cancellation deadline.
4. If past the deadline: cancellation is refused; member is shown the deadline.
5. If before the deadline: booking is deleted, wallet/cashless refunded if
   applicable.

### 4.3 Volunteer — Manage Resources

1. Volunteer accesses the booking admin panel within TiBillet backoffice.
2. Volunteer creates/edits Resources, assigns a Weekly Opening, a Calendar, and a
   Price.
3. Volunteer manages Calendars: creates ClosedPeriods for holidays or extended
   closures.
4. Volunteer views all bookings for any resource (list + calendar view), filterable
   by date and status.
5. Volunteer can delete any booking on behalf of a member. Refund is handled
   manually.
6. Volunteer can create an ad-hoc booking for any resource, date, and time,
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

### Availability

- Slots are computed on the fly from the resource's Weekly Opening and Calendar;
  nothing is pre-generated or stored.
- A slot is generated only if every day it intersects is open: for each date
  from `start_datetime.date()` to `end_datetime.date()` (inclusive), the date
  must not fall within a `ClosedPeriod`. A slot may span multiple days as long
  as none of those days is closed.
- Bookings are not required to be aligned with computed slots. A booking may have
  an arbitrary start time and duration (e.g. a volunteer creates a booking starting
  at 10:12 for 12 minutes, while the template defines slots at 10:00 for 60
  minutes).
- A booking decreases `remaining_capacity` by 1 for every computed slot it
  overlaps, even partially. A computed slot is considered overlapped if the
  booking's time window intersects with the slot's time window.
- A computed slot is considered unavailable when its `remaining_capacity = 0`,
  i.e. all units are covered by at least one overlapping booking in status `new`,
  `validated`, or `confirmed`.
- When a member books multiple consecutive slots (`slot_count > 1`), all slots in
  the range must be available before the booking is created.
- Slots outside the resource's `booking_horizon_days` window are never surfaced to
  members.

### Capacity

- A slot is full when all its units are taken (`remaining_capacity = 0`).
- A unit cannot be shared between several bookings: at any point in time, a unit
  may only be held by one booking.
- A member may hold any number of bookings on the same resource, as long as
  capacity allows.

### Pricing & Membership

- Pricing and membership eligibility are checked at booking validation time.
- Free slots (`prix = 0`) skip the payment step entirely and go directly to
  `confirmed`.

### Cancellation

- Cancellation is modelled as deletion of the Booking row. No cancelled state is
  stored.
- Cancellation deadline is configured per resource. Default: 24 hours before slot
  start.
- Refunds on cancellation are handled by TiBillet for wallet and cashless payments.

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
fragments; interactions are driven by HTTP requests with HTML responses via htmx.
There is no JSON API layer for the booking module. All views follow the existing
TiBillet HDA conventions.

### Public (no auth)

+-----------------+----------------------------------+------------------------------+
| View            | Trigger                          | Returns                      |
+=================+==================================+==============================+
| Resource list   | GET — page load or tag filter    | Full page or partial: list   |
|                 |                                  | of resources with their next |
|                 |                                  | available slots              |
+-----------------+----------------------------------+------------------------------+
| Slot picker     | GET — member selects a resource  | Partial: calendar view of    |
|                 |                                  | computed available slots for |
|                 |                                  | the resource                 |
+-----------------+----------------------------------+------------------------------+

### Member (authenticated)

+-----------------+------------------------------------+------------------------------+
| View            | Trigger                            | Returns                      |
+=================+====================================+==============================+
| Booking form    | GET — member selects a slot        | Partial: form to choose      |
|                 |                                    | `slot_count`                 |
+-----------------+------------------------------------+------------------------------+
| Add to basket   | POST — member submits booking form | Partial: updated basket;     |
|                 |                                    | prompt to add more or        |
|                 |                                    | proceed to validation        |
+-----------------+------------------------------------+------------------------------+
| Basket view     | GET                                | Partial: list of `new`       |
|                 |                                    | bookings with total price    |
+-----------------+------------------------------------+------------------------------+
| Validate basket | POST — member confirms basket      | Redirect to TiBillet payment |
|                 |                                    | flow; bookings move to       |
|                 |                                    | `validated`                  |
+-----------------+------------------------------------+------------------------------+
| Booking list    | GET                                | Full page: member's upcoming |
|                 |                                    | `confirmed` bookings         |
+-----------------+------------------------------------+------------------------------+
| Cancel booking  | POST — member requests             | Partial: updated booking     |
|                 | cancellation                       | list or error if past        |
|                 |                                    | deadline                     |
+-----------------+------------------------------------+------------------------------+

### Volunteer (backoffice)

The volunteer backoffice is managed entirely by the Django admin panel. No custom
views are required for resource management, weekly openings, calendars, or booking
administration.

Django admin registration:

+--------------+--------------+-----------------------------------------------+
| Model        | Admin type   | Inline children                               |
+==============+==============+===============================================+
| Resource     | `ModelAdmin` | —                                             |
+--------------+--------------+-----------------------------------------------+
| WeeklyOpening | `ModelAdmin` | `OpeningEntry` as `TabularInline`                |
|              |              | (compact rows: weekday, start_time,           |
|              |              | duration, count)                              |
+--------------+--------------+-----------------------------------------------+
| Calendar     | `ModelAdmin` | `ClosedPeriod` as `StackedInline`             |
|              |              | (start_date, end_date, label need             |
|              |              | vertical space)                               |
+--------------+--------------+-----------------------------------------------+
| Booking      | `ModelAdmin` | —                                             |
+--------------+--------------+-----------------------------------------------+


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
- Native mobile app
- QR code check-in at resource location
- Usage analytics / reporting dashboard
