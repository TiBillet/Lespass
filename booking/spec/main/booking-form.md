# Formulaire de réservation

Le formulaire où un réservant réserve un créneau d'une ressource, à
`/booking/<resource>/book/`. Les textes cités sont les textes source,
avant traduction.

Un visiteur non connecté n'a pas le formulaire : il est redirigé vers
`/`, avec l'avertissement « Please login to access this page. ». Le
reste de cette page concerne les réservants connectés.

## Tarifs

Le formulaire liste, sous « Tarifs », les tarifs en vente du produit de
la ressource, un choix chacun. Un tarif qui n'est pas en vente
n'apparaît pas. L'ordre des tarifs n'est pas spécifié.

Exemple : une ressource dont le produit a « Plein tarif » à 12.00
(fixe), « Soutien » à 5.00 (prix libre) et « Ancien tarif » (archivé) :

    Tarifs :
      ( ) Plein tarif - 12.00€ /h
      ( ) Soutien

- Un tarif fixe se lit `<name> - <prix>€ /h`.
- Un tarif à prix libre se lit `<name>`. Une fois choisi, il montre un
  champ de montant avec le texte indicatif « Enter the amount (minimum
  <prix>€) » et l'aide « Enter the desired amount per hour ».
- Quand la ressource n'a qu'un tarif en vente, et qu'on peut le
  choisir, il est présélectionné.
- L'affichage d'un tarif gratuit, la monnaie et le format des montants
  ne sont pas spécifiés.

Un tarif réservé aux adhérents montre, selon le réservant :

- l'adhésion est valide, ou l'un de ses produits d'adhésion est dans le
  panier du réservant : le tarif, comme un choix normal ;
- sinon : « You must have <adhésion> or <adhésion> to book this
  rate. », chaque adhésion en lien vers `/memberships/?open=<uuid>`, et
  pas de choix.
