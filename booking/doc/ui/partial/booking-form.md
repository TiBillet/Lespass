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

`ressource` (`Resource`, required)
  Parent resource.

`slot_li_id` (`str`, required)
  DOM ID of this `<li>`: `"slot-<pk>-<Ymd-Hi>"`.

`creneau` (`DisplaySlot`, optional)
  Slot data; absent when `slot_indisponible=True`.

`max_slot_count` (`int`, optional)
  Max value for the consecutive-slots input.

`slot_duration_minutes` (`int`, optional)
  Slot duration in minutes.

`start_datetime` (`datetime`, optional)
  Slot start (used in hidden field + display).

`slot_indisponible` (`bool`, optional)
  True → show "slot unavailable" state.

`erreur` (`dict | str | None`, optional)
  Validation errors from server.

`display_remaining_capacity` (`int`, optional)
  Capacity at form-open time; error state only.

`display_is_new_week` (`"0"|"1"`, optional)
  Week-separator flag at form-open time; error state only.

The `display_*` variables are only needed in the error state. They are
provided by `add_to_basket`, which reads them from the hidden form fields
submitted with the POST. The normal state reads them directly from `creneau`.

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

- Red alert with the error message text (`role="alert"`)
- "Réessayer" button: `hx-get="/booking/<pk>/booking_form/?..."` →
  reloads a fresh form
- "Annuler" link: `hx-get="/booking/<pk>/cancel_form/?..."` →
  restores the slot row (same endpoint as the normal-state cancel)
- `data-testid="booking-form-error"`

### 3. Normal form  (default)

Available slot, no errors.

- Blue info box showing slot time and duration (the duration is shown
  here in the info box; the slot-count label does not repeat it)
- Number input `slot_count` (min=1, max=`max_slot_count`, default=1)
  Label: "Nombre de créneaux"
  Hidden when `max_slot_count=1` (no choice to make); a hidden
  `slot_count=1` field is submitted instead
- Submit button "Ajouter au panier"
- Cancel link — calls the dedicated `cancel_form` endpoint:
  `GET /booking/<pk>/cancel_form/?start_datetime=...&slot_duration_minutes=...`
  Returns `slot_row.html` via `hx-swap="outerHTML"` on `#<slot_li_id>`
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

### Cancel link (both normal and error states)

```
hx-get="/booking/<pk>/cancel_form/
        ?start_datetime=...
        &slot_duration_minutes=...
        &remaining_capacity=...
        &is_new_week=0|1"
hx-target="#{{ slot_li_id }}"
hx-swap="outerHTML"
```

`cancel_form` validates these params with `CancelFormQuerySerializer`,
then reconstructs a `DisplaySlot` directly from them — **no
`compute_slots` call**. The slot is restored exactly as it was displayed
when the form opened.

The display values are encoded in the cancel URL:

- **Normal state** — read from `creneau` at render time.
- **Error state** — read from the `display_*` context variables
  (threaded back from `add_to_basket`, which reads them from the hidden
  form fields submitted with the POST).

`cancel_form` requires authentication (same as `booking_form`). An
unauthenticated request is redirected to login via `HX-Redirect`.

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

`booking-form-slot-unavailable` — alert box
  Slot no longer available message.

`booking-form-error` — alert box
  Validation error message.

`booking-form-slot-start` — form container
  Normal booking form.
