# Session 6b — Interval Abstraction: Design Discussion

**Date:**       2026-04-10
**Authors:**    Joris REHM + Claude (Anthropic) — pair design session
**Status:**     Migration Done


## 1. Motivation

Open time windows and bookings are all **half-open time intervals**
`[a, b)`. The current code handles them as tuples of
`(start_datetime, duration_minutes)`.
This representation works, but it makes interval operations implicit:
"does this booking overlap that slot?" requires reconstructing `b` from
`a + duration` every time.

The question is: what is the right abstraction?


## 2. What we are modelling

### 2.1 Calendar — from raw admin closures to normalized open-day intervals

A `Calendar` is an independent object that groups `ClosedPeriod` entries.
Each entry is recorded from the **administrator's point of view**:

- dates are naive `DateField` values (no timezone, no time component)
- periods can overlap each other (e.g. a summer closure and a public
  holiday within that summer)
- `end_date` can be `None` — an open-ended closure with no known end

This raw representation is intentional: it reflects what the admin enters
in the panel and what is stored in the database. It is not required to be
disjoint or sorted.

**Normalized open-day intervals**

What the slot engine actually needs is not the closed periods themselves
but their complement: the **intervals of time where the venue is open**.
The computation proceeds in two steps:

Step 1 — build the normalized closed set.
Convert the raw `ClosedPeriod` entries into a disjoint, sorted series of
timezone-aware half-open intervals:

1. Convert each naive `DateField` day into a timezone-aware interval
   `[day 00:00 local, day+1 00:00 local)` using the tenant venue timezone.
2. Merge overlapping or adjacent intervals into a single wider interval.
3. Treat `end_date = None` as extending to the computation horizon `date_to`.

```
[2026-07-14 00:00+10, 2026-07-21 00:00+10)   ← merged summer closure
[2026-08-15 00:00+10, 2026-08-16 00:00+10)   ← public holiday
```

Step 2 — take the complement within the computation window
`[date_from 00:00 local, date_to+1 00:00 local)`.
The gaps between closed intervals — and between the window boundaries and
the first/last closed interval — are the **normalized open-day intervals**:

```
[date_from 00:00+10, 2026-07-14 00:00+10)   ← open before summer
[2026-07-21 00:00+10, 2026-08-15 00:00+10)  ← open between closures
[2026-08-16 00:00+10, date_to+1 00:00+10)   ← open after holiday
```

This normalized open-day series is what the slot engine intersects with
the `WeeklyOpening` to produce actual bookable intervals.


### 2.2 Bookable intervals — E

Let **W** be the set of half-open intervals produced by expanding the
`WeeklyOpening` over the computation window:

```
W = { [Mon 09:00, Mon 12:00), [Mon 14:00, Mon 17:00),
      [Tue 09:00, Tue 12:00), … }
```

Let **O** be the normalized open-day interval set produced from the
`Calendar` (see §2.1):

```
O = { [date_from 00:00, 2026-07-14 00:00),
      [2026-07-21 00:00, 2026-08-15 00:00),
      [2026-08-16 00:00, date_to+1 00:00), … }
```

An interval from **W** that straddles the boundary of an open-day interval
is rejected entirely — it is not trimmed. The set of **bookable intervals**
is:

```
E = { w ∈ W | ∃ o ∈ O, w ⊆ o }
```

Each element of **E** carries a `max_capacity` — the maximum number of
simultaneous bookings allowed for that interval. This is a property of
the `Resource`, constant across all intervals.

**E** is not stored. It is computed on the fly from **W** and **O**.


### 2.3 A booking

A booking is a **series of `k` consecutive half-open intervals** chosen
by the user, each of duration `T`:

```
B = { [p, p+T), [p+T, p+2T), …, [p+(k-1)T, p+kT) }
```

For a **member booking** (via the public interface), each element of **B**
must be exactly one of the intervals in **E** — the member selects from
the computed bookable intervals, so alignment to `WeeklyOpening`
boundaries is enforced by construction. The member cannot submit an
arbitrary `[p, q)`.

For a **volunteer booking** (via the admin panel, see spec §4.3), no
alignment constraint applies — the volunteer may create ad-hoc bookings
at any start time and duration.

The member booking validity rule is:

```
booking B is valid  ⟺
  ∃ e ∈ E  such that  ∀ b ∈ B :  b ⊆ e
                     ∧  remaining_capacity(b) > 0
```

A single enclosing `e` must contain all elements of **B**.
`remaining_capacity(b)` is `max_capacity` minus the count of existing
bookings whose interval overlaps `b`.

All elements of **B** must come from the same element of **E**: a booking
cannot cross a gap. If a member wants intervals across two open windows,
they make two separate booking requests in the UI.


### 2.4 Remaining capacity

`remaining_capacity(b)` for a bookable interval `b ∈ E` is:

```
remaining_capacity(b) = max_capacity − |{ x ∈ DB | x overlaps b }|
```

where **DB** is the set of all existing bookings in the database,
regardless of their alignment.

The key rule is: **any existing booking that intersects `b` decreases the
remaining capacity by 1**, even if that booking was created by a volunteer
and does not align with the `WeeklyOpening`. The goal of the booking
software is to enforce resource availability — the physical resource
cannot be in two places at once, whatever the origin of the booking.

Two intervals overlap when:

```
x overlaps b  ⟺  x.start < b.end  ∧  b.start < x.end
```

This is the standard half-open interval overlap test. Partial overlap
(a booking that straddles the boundary of `b`) counts as a full overlap —
the resource is considered occupied for the whole of `b`.

`remaining_capacity` is never negative: if more bookings overlap `b` than
`max_capacity` allows (possible via admin override), the result is clamped
to 0.


## 3. Open design questions

### Q1 — Alignment ✓ resolved

**Member bookings:** alignment to `WeeklyOpening` boundaries is enforced
by the UI — the member selects from the displayed elements of **E**, so
`p` and `q` are always boundaries of some `w ∈ W` by construction.

**Volunteer bookings:** no alignment constraint. The admin can create
any `[p, q)`.

### Q2 — Gap crossing ✓ resolved

All elements of **B** must come from the same `e ∈ E`. A booking cannot
cross a gap between two open windows. If the member needs time across two
windows, they submit two separate booking requests.

### Q3 — Granularity of remaining_capacity check ✓ resolved

From §2.4, `remaining_capacity` is defined per interval `b ∈ E` — each
element of **B** is checked independently against all overlapping DB
bookings. Since different existing bookings may cover different parts of
`[p, p+kT)`, each `b ∈ B` must individually satisfy
`remaining_capacity(b) > 0`. A member cannot book a sub-interval that is
already full even if adjacent sub-intervals are free.

## 4. Software design

### 4.1 Two classes — Interval and BookableInterval (option A)

The model in section 2 uses intervals at three different levels:

+-----+-------+------------------+-------------------+
| Set | From  | Capacity?        | Python type       |
+=====+=======+==================+===================+
| O   | §2.1  | No — pure time   | `Interval`        |
+-----+-------+------------------+-------------------+
| W   | §2.2  | No — pure time   | `Interval`        |
+-----+-------+------------------+-------------------+
| E   | §2.2  | Yes              | `BookableInterval`|
+-----+-------+------------------+-------------------+

A single class would force capacity fields onto **O** and **W** intervals
that have no business carrying them. Two classes is the right separation.

**`Interval`** — a pure half-open time interval:

```python
@dataclasses.dataclass(frozen=True)
class Interval:
    start: datetime.datetime   # inclusive, timezone-aware
    end:   datetime.datetime   # exclusive, timezone-aware

    def overlaps(self, other: 'Interval') -> bool:
        return self.start < other.end and other.start < self.end

    def contains(self, other: 'Interval') -> bool:
        return self.start <= other.start and other.end <= self.end

    def duration_minutes(self) -> int:
        return int((self.end - self.start).total_seconds() / 60)
```

**`BookableInterval`** — an element of **E**, composing an `Interval`
with capacity information:

```python
@dataclasses.dataclass
class BookableInterval:
    interval:           Interval
    max_capacity:       int
    remaining_capacity: int

    @property
    def start(self) -> datetime.datetime:
        return self.interval.start

    @property
    def end(self) -> datetime.datetime:
        return self.interval.end
```

`frozen=True` on `Interval` makes it hashable — usable as a dict key if
needed. `BookableInterval` is not frozen because `remaining_capacity` is
filled in after construction.


### 4.2 Migration plan (Done)

The current `Slot` dataclass was an intermediate design that did not fully
model the domain. It is dropped entirely — there is no backward
compatibility shim.

**Files to rewrite:**

+--------------------------------------+------------------------------------------+
| File                                 | Change                                   |
+======================================+==========================================+
| `booking/slot_engine.py`             | Replace `Slot` with `Interval` and       |
|                                      | `BookableInterval`. Rewrite all          |
|                                      | functions to produce and consume the     |
|                                      | new types.                               |
+--------------------------------------+------------------------------------------+
| `booking/booking_validator.py`       | Rewrite validation logic against         |
|                                      | `BookableInterval` list. Replace the     |
|                                      | `(start, duration)` dict key with        |
|                                      | `Interval` containment check.            |
+--------------------------------------+------------------------------------------+
| `booking/tests/test_slot_engine.py`  | Rewrite all tests using the new classes. |
|                                      | No attempt to preserve old test          |
|                                      | structure.                               |
+--------------------------------------+------------------------------------------+
| `booking/tests/test_booking_        | Rewrite all tests using the new classes. |
| validator.py`                        |                                          |
+--------------------------------------+------------------------------------------+

All existing tests that reference `Slot`, `slot.start_datetime`,
`slot.end_datetime`, or `slot.remaining_capacity` will be rewritten from
scratch. The new tests validate the same business rules but expressed in
terms of `Interval` and `BookableInterval`.
