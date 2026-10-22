# Prix affiché en double sur la réservation de ressource / Duplicated price on resource booking form

**Date :** 2026-10-22
**Migration :** Non

## Resume / Summary
**Quoi / What :** Le formulaire de réservation d'une ressource affichait chaque tarif deux fois (nom + prix au-dessus du bouton radio, puis à nouveau dans le label du radio). Le label orphelin du haut est supprimé : le tarif n'apparaît plus qu'une fois. L'unité est harmonisée en « € /h » sur les trois variantes du tarif.
/ The resource booking form showed each price twice. The orphan label above the radio is removed; the price now appears once. The unit is unified as "€ /h".

**Pourquoi / Why :** Ce bloc, copié du formulaire d'événement, servait d'étiquette au compteur de quantité. Ici, il n'y a pas de compteur : le label pointait vers un élément inexistant (`for="amount-…"`), et les lecteurs d'écran annonçaient le prix deux fois.
/ The block, copied from the event form, labelled a quantity counter that doesn't exist here: orphan label, price read twice by screen readers.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `booking/templates/booking/partials/book_form.html` | Suppression du label orphelin et de la classe morte `js-order` ; « par heure » → « /h » |

---

## Comment tester (a la main) / Manual test

### Test 1 — tarif simple
1. Ouvrir une ressource publiée avec un tarif fixe (ex. 10 €/h).
2. Cliquer sur un créneau pour ouvrir le formulaire de réservation.
3. Vérifier : le tarif apparaît **une seule fois**, sous la forme « Nom - 10,00€ /h », à côté du bouton radio.

### Test 2 — plusieurs tarifs, prix libre, adhésion obligatoire
1. Ressource avec un tarif fixe, un tarif à prix libre et un tarif réservé aux adhérents.
2. Vérifier : chaque tarif apparaît une seule fois, et les trois affichent l'unité « /h ».
3. Cocher le prix libre : le champ de montant s'affiche toujours.
4. Tarif adhérent sans adhésion : le message d'adhésion requise s'affiche toujours.

### Verifs automatiques
- `tests/pytest/test_booking_*` : 71 passés.
- E2E `test_booking_formulaire_dynamique`, `test_booking_calendrier_semaine`, `test_booking_validation_manuelle_stripe` : passés, sauf le parcours Stripe qui demande `stripe listen`.
