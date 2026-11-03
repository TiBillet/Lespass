# Data model

Only the entities and fields that specified zones use.

## Resource

A bookable thing of a place: a room, a machine, a desk.

- `name`
- `product`: its resource product (required).

## Resource product

A `Product` of category `RESOURCE` (`BaseBillet`). Several resources
may share one.

- `prices`: its prices.

## Price

A price of a resource product (`BaseBillet.Price`).

- `name`
- `prix`: an amount for one hour of booking.
- `free_price`: true for an open price.
- `publish`, `archived`: a price is on sale when it is published and
  not archived.
- `adhesions_obligatoires`: membership products, possibly none. When
  there are some, the price is members-only: it needs a valid
  membership to any one of them.

Kinds of price:

- fixed price: `free_price` false, `prix` above 0. The booker pays
  `prix` per hour.
- open price: `free_price` true. The booker types an amount per hour,
  at least `prix`.
- free price: `free_price` false, `prix` 0. "Free" always means this
  kind, never an open price.
