# BookingForm — Inline Slot Booking Form

**Template:** `booking/templates/booking/partial/booking_form.html`
**Rendered by:** `BookingViewSet.booking_form()` and (on error)
`BookingViewSet.add_to_basket()`
**URL:** `GET /booking/<pk>/booking_form/
          ?start_datetime=<ISO>&slot_duration_minutes=<N>`

This partial **replaces** a `slot_row.html` `<li>` in-place (same DOM ID,
`hx-swap="outerHTML"`). It is an inline form, not a modal or page.

When the user submits, `add_to_basket` either:
- **Success** → replaces this `<li>` with updated `slot_row.html`
  + OOB-updates the basket
- **Error** → re-renders this template (same `<li>`) with `erreur` set

---

## Context variables

| Variable               | Type                | Required | Description                                        |
|------------------------|---------------------|----------|----------------------------------------------------|
| `ressource`            | `Resource`          | yes      | Parent resource                                    |
| `slot_li_id`           | `str`               | yes      | DOM ID of this `<li>`: `"slot-<pk>-<Ymd-Hi>"`     |
| `creneau`              | `BookableInterval`  | no       | Slot data; absent when `slot_indisponible=True`    |
| `max_slot_count`       | `int`               | no       | Max value for the consecutive-slots input          |
| `slot_duration_minutes`| `int`               | no       | Slot duration in minutes (displayed in form label) |
| `start_datetime`       | `datetime`          | no       | Slot start (used in hidden field + display)        |
| `slot_indisponible`    | `bool`              | no       | True → show "slot unavailable" state               |
| `erreur`               | `dict \| str \| None` | no     | Validation errors from server                      |

---

## States

### 1. Slot unavailable  (`slot_indisponible=True`)

The slot was valid when the user clicked but is now full (race
condition) or the query params are invalid.

- Red/orange alert box: "Ce créneau n'est plus disponible"
- No form rendered
- `data-testid="booking-form-slot-unavailable"`

### 2. Validation error  (`erreur` is truthy)

The form was submitted but the server rejected it (serializer error
or engine error). The form is re-rendered as a 422 response.

- Red alert with the error message text
- "Réessayer" button:
  `hx-get="/booking/<pk>/booking_form/?..."` → `hx-target="#<slot_li_id>"`
  `hx-swap="outerHTML"` — reloads a fresh form
- `data-testid="booking-form-error"`

### 3. Normal form  (default)

Available slot, no errors.

- Blue info box showing slot time and duration
- Number input `slot_count` (min=1, max=`max_slot_count`, default=1)
  Label: "Nombre de créneaux ({{ slot_duration_minutes }} min chacun)"
  Hidden only when `max_slot_count=1` (no choice to make)
- Submit button "Ajouter au panier"
- Cancel link (re-renders the original `slot_row.html`):
  `hx-get="/booking/<pk>/booking_form/?..."` → back to slot row
  *(currently reloads the form — open question whether to add a
  dedicated cancel endpoint that returns slot_row directly)*
- `data-testid="booking-form-slot-start"`

---

## HTMX interactions

### Form submission (normal state)

```
<form hx-post="/booking/<ressource.pk>/add_to_basket/"
      hx-target="#{{ slot_li_id }}"
      hx-swap="outerHTML">
  <input type="hidden" name="start_datetime" value="...">
  <input type="hidden" name="slot_duration_minutes" value="...">
  <input type="number" name="slot_count" min="1" max="{{ max_slot_count }}">
  <button type="submit">Ajouter au panier</button>
</form>
```

CSRF token is included (inherited from `<body hx-headers='...'>`).

### Retry button (error state)

```
hx-get="/booking/<pk>/booking_form/?start_datetime=...&slot_duration_minutes=..."
hx-target="#{{ slot_li_id }}"
hx-swap="outerHTML"
```

### 422 handling

`booking_base.html` configures HTMX globally to allow swapping on 422:
```javascript
if (status === 422) {
    event.detail.shouldSwap = true;
    event.detail.isError = false;
}
```

### Unauthenticated request

If the user is not logged in when `booking_form` is called:
- HTMX request: server sends `HX-Redirect` to login page
- Direct request: server sends Django redirect to login page

The form is never rendered for unauthenticated users.

---

## Accessibility

- Form: `role="form"` + `aria-label="Réserver {{ creneau.start|date:'D d/m/Y H:i' }}"`
- Number input: `aria-label="Nombre de créneaux"` with visible `<label>`
- Error message: `role="alert"` so screen readers announce it immediately
- Unavailable message: `role="alert"`
- After swap: focus should move to the form's first interactive element
  (enhancement: JS `htmx:afterSwap` hook — not yet implemented)

---

## data-testid

| Value                          | Element        | Purpose                              |
|--------------------------------|----------------|--------------------------------------|
| `booking-form-slot-unavailable` | alert box     | Slot no longer available message     |
| `booking-form-error`           | alert box      | Validation error message             |
| `booking-form-slot-start`      | form container | Normal booking form                  |
