# SlotRow — Single Slot Row

**Template:** `booking/templates/booking/partial/slot_row.html`
**Included by:** `booking/partial/slot_list.html`
**Also rendered by:** `BookingViewSet.add_to_basket()` (after a booking is
created, the slot row is re-rendered with updated capacity)

One `<li>` per time slot. Clicking an available slot replaces the `<li>`
with the inline booking form (`booking_form.html`). After a successful
`add_to_basket`, it is replaced back with the updated slot row (capacity
decremented) via an OOB swap.

---

## Context variables

`ressource` (`Resource`, required)
  Parent resource (used for HTMX URL and DOM ID).

`creneau` (`BookableInterval`, required)
  The time slot with capacity and display annotations.

### BookableInterval shape

`start` (`datetime`)
  Slot start (tz-aware).

`end` (`datetime`)
  Slot end (tz-aware).

`remaining_capacity` (`int`)
  0 = full; > 0 = available.

`slot_duration_minutes` (`int`)
  Duration in minutes.

`group_id` (`str`)
  Groups consecutive same-opening slots.

`is_in_group` (`bool`)
  True if ≥ 2 consecutive slots share a `group_id`.

`is_group_end` (`bool`)
  True if last (or only) slot in a visual group.

`is_new_week` (`bool`)
  True if ISO week differs from the previous slot.

Annotations are added by `annoter_creneaux_pour_affichage()` in
`booking/views.py` before the template is rendered.

---

## DOM ID

Each `<li>` gets a stable ID used as HTMX swap target:

```
id="slot-{{ ressource.pk }}-{{ creneau.start|date:'Ymd-Hi' }}"
```

Example: `slot-42-20260510-0900`

---

## States

**Week separator** — `creneau.is_new_week=True`
  Muted `<li>` showing "Semaine W" — not clickable.

**Available** — `remaining_capacity > 0`
  Green ✓ icon + capacity badge; clickable link.

**Full** — `remaining_capacity == 0`
  Grey ✕ icon + "Complet" badge; no link.

**Grouped** — `is_in_group=True`
  Left border (`border-start border-2`) on the `<li>`.

**Group end** — `is_group_end=True`
  Larger bottom margin to visually close the group.

States can combine: e.g. an available + grouped + group-end slot.

---

## HTMX interactions

### Available slot — open booking form

Click on the slot link:
```
hx-get="/booking/<ressource.pk>/booking_form/
        ?start_datetime=<ISO>&slot_duration_minutes=<N>"
hx-target="#slot-<ressource.pk>-<Ymd-Hi>"
hx-swap="outerHTML"
```

The `<li>` is replaced in-place by `booking_form.html` (same DOM ID).

### After successful `add_to_basket`

The server re-renders this template with updated capacity and returns
it as part of the response (not OOB — it is the primary swap target).
The basket partial is returned as OOB alongside it.

---

## Accessibility

- Available slot link: `aria-label="Réserver {{ creneau.start|date:'D d/m/Y H:i' }}"`
- Full slot: `aria-disabled="true"` on the `<li>`; "Complet" badge with
  `aria-label="Complet"` and `role="status"`
- Green/grey icons: `aria-hidden="true"` (decorative)
- Week separator: `aria-hidden="true"` (navigational aid, not content)
- After HTMX swap (form open): focus should move to the form's first
  input (requires `htmx:afterSwap` JS hook — not yet implemented)

---

## data-testid

`booking-slot-available` — `<li>`
  Available slot (no grouping).

`booking-slot-available booking-slot-grouped` — `<li>`
  Available slot inside a visual group.

`booking-slot-unavailable` — `<li>`
  Full slot (no grouping).

`booking-slot-unavailable booking-slot-grouped` — `<li>`
  Full slot inside a visual group.

`booking-week-separator` — `<li>`
  Week separator row.
