# SlotList — Slot List Wrapper

**Template:** `booking/templates/booking/partial/slot_list.html`
**Included by:**
- `booking/partial/card.html` (first 5 slots only)
- `booking/views/resource.html` (full list)
**Not a standalone HTMX endpoint** — thin wrapper, no logic.

Renders an unstyled `<ul>` containing one `slot_row.html` per slot.
Has no state of its own — delegates entirely to `slot_row.html`.

---

## Context variables

`ressource` (`Resource`, required)
  Passed through to each slot row.

`creneaux` (`list[BookableInterval]`, required)
  List of slots to render.

Slots must be pre-annotated with `is_new_week` by
`annotate_slots_for_display()` before inclusion.

---

## States

This component has no states of its own. An empty `creneaux` list
produces an empty `<ul>` — the parent template handles the empty-state
message.

---

## Included partials

- `{% include "booking/partial/slot_row.html" with ressource=ressource creneau=creneau %}` — one per slot

---

## HTMX interactions

None at this level. All HTMX is on `slot_row.html`.

---

## Accessibility

- `<ul class="list-unstyled">` is a semantic list; no extra ARIA needed
- If the list is dynamically updated after an HTMX swap, the parent
  container should carry `aria-live="polite"`
