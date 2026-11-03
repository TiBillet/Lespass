# Booking form

The form where a booker books a slot of a resource, at
`/booking/<resource>/book/`. Quoted texts are the source texts, before
translation.

A visitor who is not logged in does not get the form: they are
redirected to `/`, with the warning "Please login to access this
page.". The rest of this page is about logged-in bookers.

## Prices

The form lists, under "Tarifs", the prices of the resource's product
that are on sale, one choice each. A price that is not on sale does
not appear. The order of the prices is unspecified.

Example: a resource whose product has "Plein tarif" at 12.00 (fixed),
"Soutien" at 5.00 (open) and "Ancien tarif" (archived):

    Tarifs :
      ( ) Plein tarif - 12.00€ /h
      ( ) Soutien

- A fixed price reads `<name> - <prix>€ /h`.
- An open price reads `<name>`. Once selected, it shows an amount field
  with the placeholder "Enter the amount (minimum <prix>€)" and the help
  "Enter the desired amount per hour".
- When the resource has a single price on sale, and it can be chosen,
  it is pre-selected.
- The display of a free price, the currency, and the number format of
  amounts are unspecified.

A members-only price shows, depending on the booker:

- the membership is valid, or one of its membership products is in the
  booker's cart: the price, as a normal choice;
- otherwise: "You must have <membership> or <membership> to book this
  rate.", each membership linking to `/memberships/?open=<uuid>`, and
  no choice.
