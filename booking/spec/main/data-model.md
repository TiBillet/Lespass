# Modèle de données

Seulement les entités et les champs qu'utilisent les zones spécifiées.

## Ressource

Une chose réservable d'un lieu : une salle, une machine, un bureau.

- `name`
- `product` : son produit de ressource (obligatoire).

## Produit de ressource

Un `Product` de catégorie `RESOURCE` (`BaseBillet`). Plusieurs
ressources peuvent en partager un.

- `prices` : ses tarifs.

## Tarif

Un tarif d'un produit de ressource (`BaseBillet.Price`).

- `name`
- `prix` : un montant pour une heure de réservation.
- `free_price` : vrai pour un tarif à prix libre.
- `publish`, `archived` : un tarif est en vente quand il est publié et
  non archivé.
- `adhesions_obligatoires` : des produits d'adhésion, éventuellement
  aucun. S'il y en a, le tarif est réservé aux adhérents : il faut une
  adhésion valide à l'un d'eux.

Sortes de tarif :

- tarif fixe : `free_price` faux, `prix` supérieur à 0. Le réservant
  paie le montant par créneau que le formulaire en déduit.
- tarif à prix libre : `free_price` vrai. Le réservant choisit un
  montant par créneau au moins égal au minimum que le formulaire déduit
  de `prix`.
- tarif gratuit : `free_price` faux, `prix` à 0.
