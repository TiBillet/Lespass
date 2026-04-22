# Card — Resource Card

**Template:** `booking/templates/booking/partial/card.html`
**Included by:** `booking/views/home.html`
**Not a standalone HTMX endpoint** — rendered server-side inside `home.html`.

Bootstrap card for a single resource. Shows image, name, truncated
description, tag badges, and the first 5 slots. Greys out when the
resource has no available slots.

---

## Context variables

| Variable           | Type                     | Required | Description                              |
|--------------------|--------------------------|----------|------------------------------------------|
| `item.ressource`   | `Resource`               | yes      | The bookable resource object             |
| `item.creneaux`    | `list[BookableInterval]` | yes      | Computed slots (first 5 shown)           |
| `item.a_des_creneaux` | `bool`               | yes      | True if at least one slot exists         |

---

## States

| State          | Condition                  | Visual                                          |
|----------------|----------------------------|-------------------------------------------------|
| Active card    | `item.a_des_creneaux=True` | Normal card; name is a clickable HTMX link      |
| Greyed card    | `item.a_des_creneaux=False`| `opacity-50`, `filter: grayscale(1)`; no link   |
| Has image      | `item.ressource.image` set | `<img>` card-img-top                            |
| No image       | image is falsy             | No image element                                |
| Has tags       | `item.ressource.tags` set  | Tag badges below description                    |
| Slot overflow  | `item.creneaux` has > 5    | Only first 5 slots shown (no "show more")       |

---

## Included partials

- `{% include "booking/partial/slot_list.html" with ressource=item.ressource creneaux=item.creneaux|slice:":5" %}`

---

## HTMX interactions

All links exist only when `item.a_des_creneaux=True`.

- **Resource name link** → resource detail page:
  `hx-get="/booking/resource/<pk>/"` → `hx-target="body"` `hx-swap="innerHTML"` `hx-push-url="true"`
  `href` kept for no-JS fallback.

- **Tag badge click** → filtered home:
  `hx-get="/booking/?tag=<tag>"` → `hx-target="body"` `hx-swap="innerHTML"` `hx-push-url="true"`

---

## Accessibility

- Card image: `alt="{{ item.ressource.name }}"`
- Greyed card: `aria-disabled="true"` on the card wrapper; name rendered as plain `<span>` not `<a>`
- Tags wrapper: `aria-label="Tags"`
- Decorative icons on tag badges: `aria-hidden="true"`
- Description truncation is visual only (no `aria-label` override needed)

---

## data-testid

| Value                       | Element         | Purpose                             |
|-----------------------------|-----------------|-------------------------------------|
| `booking-resource-card`     | card container  | Active card (has slots)             |
| `booking-resource-card-greyed` | card container | Greyed card (no slots)           |
