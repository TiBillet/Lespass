# CancelError — Booking Cancellation Error Feedback

**Template:** `booking/templates/booking/partial/cancel_error.html`
**Rendered by:** `BookingViewSet.cancel()` on error (HTTP 422)
**Swap target:** `#cancel-result-<pk>` `hx-swap="innerHTML"`
**Location:** Rendered inside `my_account/my_resources.html`
(a different app — this partial is cross-app).

Shown inline next to a booking row in the "My reservations" page when a
cancellation fails. Two distinct failure modes have distinct visuals.

---

## Context variables

| Variable            | Type       | Required | Description                                          |
|---------------------|------------|----------|------------------------------------------------------|
| `erreur_deadline`   | `bool`     | yes      | True if cancellation is refused due to deadline      |
| `deadline_datetime` | `datetime` | no       | Cancellation deadline; required when `erreur_deadline=True` |
| `erreur`            | `str`      | no       | Generic error message; used when `erreur_deadline=False` |

---

## States

### 1. Deadline exceeded  (`erreur_deadline=True`)

The cancellation window has passed. The booking cannot be cancelled.

- Yellow/warning alert badge: "Annulation impossible"
- Formatted deadline: `{{ deadline_datetime|date:"d/m/Y H:i" }}`
  Example: "La date limite d'annulation était le 10/05/2026 à 09:00"
- No action button

### 2. Generic error  (`erreur_deadline=False`, `erreur` set)

Any other server error (booking not found, wrong owner, wrong status).

- Red/danger alert badge
- Error message text from `erreur`
- No action button

---

## HTMX interactions

This partial is a **response only** — it has no outgoing HTMX
attributes of its own. It is injected into `#cancel-result-<pk>` by
the cancel button in `my_resources.html`:

```
hx-post="/booking/cancel/"
hx-vals='{"booking_pk": {{ booking.pk }}}'
hx-target="#cancel-result-{{ booking.pk }}"
hx-swap="innerHTML"
```

On success (200) the server sends `HX-Redirect` to
`/my_account/my_resources/` instead of rendering this template.

---

## Accessibility

- Both error states: `role="alert"` on the badge container so screen
  readers announce the error immediately without focus movement
- Deadline datetime: wrapped in `<time datetime="{{ deadline_datetime|date:'c' }}">` for semantic HTML
- Decorative warning/danger icons: `aria-hidden="true"`

---

## data-testid

This partial does not currently define `data-testid` attributes.
Recommended additions:

| Value                          | Element      | Purpose                         |
|--------------------------------|--------------|---------------------------------|
| `cancel-error-deadline`        | alert badge  | Deadline-exceeded error state   |
| `cancel-error-generic`         | alert badge  | Generic error state             |
