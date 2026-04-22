# Resource Detail Page

**Template:** `booking/templates/booking/views/resource.html`
**Rendered by:** `BookingViewSet.resource_page()`
**URL:** `GET /booking/resource/<pk>/`
**Base template:** `booking/booking_base.html`

Full detail page for a single bookable resource. Shows the resource
description, image, tags, and the complete slot list.

---

## Context variables

| Variable               | Type                        | Required | Description                                     |
|------------------------|-----------------------------|----------|-------------------------------------------------|
| `ressource`            | `Resource`                  | yes      | The bookable resource object                    |
| `creneaux`             | `list[BookableInterval]`    | yes      | Computed slots, annotated for display grouping  |
| `reservations_en_cours` | `QuerySet[Booking] \| []`  | yes      | Authenticated user's 'new' bookings for basket  |

Slots are annotated by `annoter_creneaux_pour_affichage()` with:
`is_in_group`, `is_group_end`, `is_new_week` (see `partial/slot-row.md`).

---

## States

| State         | Condition                   | Visual                                           |
|---------------|-----------------------------|--------------------------------------------------|
| Has image     | `ressource.image` is set    | Full-width `<img>` hero at top of page           |
| No image      | `ressource.image` is falsy  | No image element rendered                        |
| Has tags      | `ressource.tags` is non-empty | Row of clickable tag badges below description  |
| No tags       | `ressource.tags` is empty   | No tag row rendered                              |
| Has slots     | `creneaux` is non-empty     | Slot list via `slot_list.html` partial           |
| No slots      | `creneaux` is empty         | Muted message "Aucun créneau disponible"         |

---

## Included partials

- `{% include "booking/partial/slot_list.html" with ressource=ressource creneaux=creneaux %}`

---

## HTMX interactions

- **Back to list button:**
  `hx-get="/booking/"` → `hx-target="body"` `hx-swap="innerHTML"` `hx-push-url="true"`

- **Tag badge click:**
  `hx-get="/booking/?tag=<tag>"` → `hx-target="body"` `hx-swap="innerHTML"` `hx-push-url="true"`

All navigation uses full-body swap (anti-blink pattern).

---

## Accessibility

- Back button: `aria-label="Retour à la liste"` or visible text
- Hero image: `alt="{{ ressource.name }}"` (meaningful, not decorative)
- Tags container: `aria-label="Tags"` on the wrapper `<p>` or `<div>`
- Decorative icons on tag badges: `aria-hidden="true"`

---

## data-testid

| Value                    | Element       | Purpose                       |
|--------------------------|---------------|-------------------------------|
| `booking-resource-detail` | back button  | E2E navigation target         |
