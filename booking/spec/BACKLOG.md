# Backlog

- Docs: delete `booking/doc/` once its content is specified or dropped.
- Docs: translate the documents of `booking/` (spec, README, `DEV43.md`) into French.
- Booking form: show the three kinds of price distinctly: fixed (per hour), open with its minimum (per hour), and free (0 €).
- Booking pages: check which image is shown, the resource's or its resource product's.
- Booking form: remove the out-of-stock handling of prices, which resource prices never trigger.
- Booking form: remove the 'Log in to access this rate.' branch, which never renders since the form requires login.
- Booking form: remove the non-HTMX branch of `book` (missing `booking/views/book.html`) and its out-of-date fallback comment.
