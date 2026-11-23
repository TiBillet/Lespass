# CHANTIER 02 — Tarifs affichés et payés par créneau

**Origine :** PR #492 (Joris), demande de G'Récup (créneaux de 180 minutes).
**Décision :** arrondi au centime par créneau (Jonas et Joris, 2026-11-23). L'arrondi aux
10 centimes, d'abord proposé, a été écarté : il changeait le prix payé même pour des
créneaux d'une heure (9,99 €/h facturés 10 €).

Le prix reste **horaire** en base (`Price.prix`). Le formulaire de réservation affiche
et fait payer des **créneaux**. Un seul calcul : `booking/montants.py`, appelé par le
moteur (`booking_engine.validate_new_booking`), le panier
(`PanierSession.add_resource`), la ligne du panier (`context_processors.py`) et les
libellés du formulaire (`booking/views.py`, `tarifs_du_formulaire`).

## Formulaire de réservation

Le formulaire est à `/booking/<resource>/book/`. Un visiteur non connecté n'a pas le
formulaire : il est redirigé vers `/`, avec l'avertissement « Please login to access
this page. ».

## Tarifs

Le formulaire liste, sous « Tarifs », les tarifs en vente du produit de la ressource
(publiés et non archivés), un choix chacun.

Sortes de tarif :

- **tarif fixe** : `free_price` faux, `prix` supérieur à 0 ;
- **tarif à prix libre** : `free_price` vrai, `prix` est le minimum horaire ;
- **tarif gratuit** : `free_price` faux, `prix` à 0.

Le montant d'un créneau vaut `prix × durée du créneau / 60`, arrondi au centime le plus
proche (au centime supérieur à mi-chemin). Une durée multiple de 60 minutes ne demande
jamais d'arrondi.

| `prix` | Durée du créneau | Valeur exacte | 1 créneau | 3 créneaux |
|--------|------------------|---------------|-----------|------------|
| 10.00  | 40 minutes       | 6,666…        | 6,67      | 20,01      |
| 10.00  | 50 minutes       | 8,333…        | 8,33      | 24,99      |
| 7.00   | 45 minutes       | 5,25          | 5,25      | 15,75      |
| 3.33   | 180 minutes      | 9,99          | 9,99      | 29,97      |

Exemple : des créneaux de 180 minutes, et un produit qui a « Plein tarif » à 12.00
(fixe), « Soutien » à 5.00 (prix libre), « Solidaire » à 0.00 (prix libre),
« Bénévoles » à 0.00 (fixe, donc gratuit) et « Ancien tarif » (archivé) :

    Tarifs :
      ( ) Plein tarif - 36 € / créneau
      ( ) Soutien - prix libre dès 15 € / créneau
      ( ) Solidaire - prix libre
      ( ) Bénévoles - gratuit

Une fois « Soutien » choisi, il montre un champ de montant avec le texte indicatif
« Montant par créneau, 15 € minimum ». Pour « Solidaire » : « Montant par créneau ».

- Un montant s'écrit sans centimes inutiles, selon la langue : « 36 », « 8,33 ».
- **R1** : pour un tarif fixe, le montant payé pour N créneaux vaut N fois le montant
  affiché par créneau (on arrondit chaque créneau, puis on multiplie).
- **R2** : le minimum d'un prix libre est `prix × durée du créneau / 60`, arrondi au
  centime supérieur. Un montant saisi égal à ce minimum est accepté ; un montant
  inférieur est refusé.
- **R3** : le montant saisi pour un prix libre est un montant par créneau : pour N
  créneaux, le montant payé vaut N fois le montant saisi, en réservation directe comme
  en passant par le panier. Il est converti en montant horaire, sans arrondi, dès la
  réception ; le panier le garde sous cette forme.
- Quand la ressource n'a qu'un tarif en vente, et qu'on peut le choisir, il est
  présélectionné.

La ligne d'une ressource dans le panier se lit « N × montant d'un créneau = total ».

## Tests

- Libellés du formulaire : `booking/tests/test_booking_form_prices.py`.
- Montants payés (R1 à R3), sans et avec panier : `tests/pytest/test_booking_montant_par_creneau.py`.
- Ligne du panier : `tests/pytest/test_panier_mvt.py`.

## Reste à faire (remarques de Joris et demandes de lieux)

- Pages de réservation : vérifier quelle image est affichée, celle de la ressource ou
  celle de son produit de ressource.
- Formulaire : retirer la gestion du stock épuisé des tarifs, que les tarifs de ressource
  ne déclenchent jamais.
- Formulaire : retirer la branche « Log in to access this rate. », qui ne s'affiche
  jamais puisque le formulaire exige d'être connecté.
- Formulaire : retirer la branche non HTMX de `book` (`booking/views/book.html`
  manquant) et son commentaire de repli périmé.
- Panier : rendre la ligne d'une ressource moins verbeuse (la durée apparaît encore
  deux fois, « slot » n'est ni traduit ni accordé).
- Liste des ressources : le prix de la carte d'une ressource (« 10 € », `libelle_prix`
  posé par `BookingViewSet.list`) est ambigu, sans unité ni sorte de tarif.
- Formulaire : rendre plus visibles les contours gris trop pâles, surtout les boutons
  radio des tarifs.
- Réservation : afficher la durée des créneaux en heures et minutes, pas seulement en
  minutes.
- Réservation : un délai minimum avant le début d'un créneau, réglable par ressource
  (demande d'un lieu). À trancher : unité, valeur par défaut, affichage dans le
  calendrier, créneau payé trop tard depuis le panier.
- Admin : permettre aux administrateurs de réserver une ressource, y compris hors des
  créneaux habituels (ressource en travaux). S'inspirer de la réservation par l'admin de
  la billetterie.
- Admin : créer par défaut un calendrier de fermeture vide (`Calendar`) et des créneaux
  hebdomadaires vides (`WeeklyOpening`), pour créer une ressource sans les créer d'abord.
- Un vrai prix par créneau en base (10 € pile pour 3 h) demanderait un chantier à part :
  la durée est portée par chaque `OpeningEntry`, et une même ressource peut mélanger
  plusieurs durées.
