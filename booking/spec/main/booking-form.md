# Formulaire de réservation

Le formulaire où un réservant réserve un ou plusieurs créneaux
consécutifs d'une ressource, à `/booking/<resource>/book/`. Les textes
cités sont les textes source, avant traduction.

Un visiteur non connecté n'a pas le formulaire : il est redirigé vers
`/`, avec l'avertissement « Please login to access this page. ». Le
reste de cette page concerne les réservants connectés.

## Tarifs

Le formulaire liste, sous « Tarifs », les tarifs en vente du produit de
la ressource, un choix chacun. Un tarif qui n'est pas en vente
n'apparaît pas. L'ordre des tarifs n'est pas spécifié.

Les montants sont par créneau : pour un tarif fixe, le montant d'un
créneau vaut `prix × durée du créneau / 60`, arrondi aux 10 centimes
les plus proches, et à la dizaine supérieure à mi-chemin.

| `prix` | Durée du créneau | Valeur exacte | 1 créneau | 3 créneaux |
|--------|------------------|---------------|-----------|------------|
| 10.00  | 40 minutes       | 6,666…        | 6,70      | 20,10      |
| 10.00  | 50 minutes       | 8,333…        | 8,30      | 24,90      |
| 7.00   | 45 minutes       | 5,25          | 5,30      | 15,90      |
| 3.33   | 180 minutes      | 9,99          | 10        | 30         |

Exemple : des créneaux de 180 minutes, et un produit qui a « Plein
tarif » à 12.00 (fixe), « Soutien » à 5.00 (prix libre), « Solidaire »
à 0.00 (prix libre), « Bénévoles » à 0.00 (fixe, donc gratuit) et
« Ancien tarif » (archivé) :

    Tarifs :
      ( ) Plein tarif - 36 € / créneau
      ( ) Soutien - prix libre dès 15 € / créneau
      ( ) Solidaire - prix libre
      ( ) Bénévoles - gratuit

Une fois « Soutien » choisi, il montre un champ de montant avec le
texte indicatif « Montant par créneau, 15 € minimum ». Pour
« Solidaire », le texte indicatif est « Montant par créneau ».

- Un tarif fixe se lit `<name> - <montant> € / créneau`.
- Un tarif à prix libre se lit `<name> - prix libre dès <minimum> € /
  créneau`, ou `<name> - prix libre` quand `prix` vaut 0.
- Un tarif gratuit se lit `<name> - gratuit`.
- Un montant s'écrit sans centimes inutiles, selon la langue : « 36 »,
  « 8,30 » en français.
- R1: Pour un tarif fixe, le montant payé pour N créneaux vaut N fois le
  montant affiché par créneau.
- R2: Le minimum d'un prix libre est `prix × durée du créneau / 60`,
  arrondi aux 10 centimes supérieurs. Un montant saisi égal à ce minimum est
  accepté ; un montant inférieur est refusé.
- R3: Le montant saisi pour un prix libre est un montant par créneau :
  pour N créneaux, le montant payé vaut N fois le montant saisi, en
  réservation directe comme en passant par le panier.
- Quand la ressource n'a qu'un tarif en vente, et qu'on peut le
  choisir, il est présélectionné.
- La monnaie n'est pas spécifiée.

Un tarif réservé aux adhérents montre, selon le réservant :

- l'adhésion est valide, ou l'un de ses produits d'adhésion est dans le
  panier du réservant : le tarif, comme un choix normal ;
- sinon : « You must have <adhésion> or <adhésion> to book this
  rate. », chaque adhésion en lien vers `/memberships/?open=<uuid>`, et
  pas de choix.
