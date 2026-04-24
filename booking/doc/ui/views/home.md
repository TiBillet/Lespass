# Home — Resource List Page

**Template:** `booking/templates/booking/views/home.html`
**Rendered by:** `BookingViewSet.list()`
**URL:** `GET /booking/`
**Base template:** `booking/booking_base.html`

Public page. Lists all bookable resources grouped by `ResourceGroup`.
An optional `?tag=` query parameter filters cards to a single tag.

---

## Context variables

`groupes_annotes` (`list[dict]`, required)
  Groups with their resources and computed slots.
  Each item: `{'groupe': ResourceGroup, 'items': list[item_dict]}`

`items_sans_groupe` (`list[item_dict]`, required)
  Resources that have no group assigned.

`tag_filtre` (`str | None`, required)
  Active tag filter value from `?tag=` param.

`reservations_en_cours` (`QuerySet[Booking] | []`, required)
  Authenticated user's 'new' bookings for basket.

`item_dict` shape (built in `_annote_ressources()`):

`ressource` (`Resource`)
  The bookable resource.

`creneaux` (`list[BookableInterval]`)
  Computed available slots.

`a_des_creneaux` (`bool`)
  True if at least one slot exists.

---

## States

**Tag filter active** — `tag_filtre` is not None
  Blue badge with tag label + × clear link.

**Tag filter inactive** — `tag_filtre` is None
  No filter badge shown.

**Groups present** — `groupes_annotes` is non-empty
  Section heading per group + card grid.

**Ungrouped resources** — `items_sans_groupe` is non-empty
  Card grid with no heading.

**Empty list** — both lists empty after filter
  Muted message "Aucune ressource".

---

## Included partials

- `{% include "booking/partial/card.html" with item=item %}` — one per resource

---

## HTMX interactions

- **Tag filter clear** (`× tag_filtre`):
  `hx-get="/booking/"` → `hx-target="body"` `hx-swap="innerHTML"` `hx-push-url="true"`
- **Tag badge click** (on a card):
  `hx-get="/booking/?tag=<tag>"` → `hx-target="body"` `hx-swap="innerHTML"` `hx-push-url="true"`

Navigation always replaces the full `<body>` content (anti-blink pattern).
Basket (rendered by `booking_base.html`) persists across navigation.

---

## Accessibility

- `aria-hidden="true"` on decorative icons (× icon on tag badge)
- Tag filter badge: `aria-label="Filtre actif : {{ tag_filtre }}"` on the container
- Card grid region: no `aria-live` (static on load; full-page swap on navigation)

---

## data-testid

`booking-resource-list` — `<h1>`
  Page heading for E2E targeting.

`booking-tag-filter-active` — filter badge
  Active filter badge.

`booking-empty-list` — message `<p>`
  Empty state message.
