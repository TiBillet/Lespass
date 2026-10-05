# Compteur de billets borné aux places restantes / Ticket counter capped to the remaining seats

**Date :** 2026-09-17
**Migration :** Non
**Sentry :** BILLETTERIE-COOP-4G (781 occurrences depuis avril 2025)

## Resume / Summary

**Quoi / What :** le compteur de billets du formulaire de réservation ne propose plus
davantage que les places réellement disponibles. Le nombre de places restantes s'affiche
sous le total. Il n'y a plus jamais d'attribut `max="None"`.
/ The booking counter never offers more than the seats actually available, the remaining
seats are shown under the total, and `max="None"` is never rendered.

**Pourquoi / Why :** sur un évènement où il restait 1 place, le compteur laissait saisir
jusqu'à 10 billets, et le serveur refusait. L'attribut `max` du composant `bs-counter`
n'était borné que par `max_per_user`, jamais par
`jauge_max − valid_tickets_count − under_purchase`.
/ The counter's `max` only used `max_per_user`, never the remaining seats.

**Plafond `None` / `NaN` :** `Event.max_per_user` et `Price.max_per_user` sont
facultatifs. Quand les deux étaient vides, le gabarit rendait `max="None"`. Or
`bs-counter.mjs` teste `if (this.max)` (« None » est vrai) puis `Number(this.max)` (NaN) :
le bouton `+` n'était jamais désactivé, et le champ affichait « 0 / NaN ».
/ An empty per-user cap rendered `max="None"`, read as NaN by bs-counter.

**Calcul :** le plafond est calculé en Python dans `EventMVT.retrieve`, comme le plus
petit des plafonds réellement définis, et déposé sur chaque tarif sous le nom
`max_billets`. Sans plafond, il vaut `None` et le gabarit n'écrit **aucun** attribut `max`.
/ The cap is computed in `EventMVT.retrieve` and attached to each price as `max_billets`.

**Piège à connaître / Gotcha :** le plafond est posé dans la boucle
`for p in event.published_prices:`, **pas** sur la liste issue du `prefetch_related`. Ce
sont deux collections d'instances Python différentes pour les mêmes lignes SQL, et le
gabarit itère sur la première.
/ The cap must be set on `event.published_prices` instances, which the template iterates.

**Affichage :** les places restantes s'affichent sous le total, en permanence si le lieu a
activé « Afficher la jauge », sinon à partir de 10 places ou moins. Le message est unique
pour tout le formulaire : le répéter sous chaque compteur laisserait croire à un stock
par tarif. Il est masqué pour un évènement fédéré (jauge non calculable depuis ce schéma).
/ Remaining seats are shown once, always if the gauge is visible, otherwise at 10 or less.

**Refus de validation en `warning` :** un refus métier (jauge atteinte, quota dépassé,
adhésion manquante) passe en `logger.warning` et ne crée plus d'event Sentry. Une part de
ces refus reste légitime : `under_purchase` compte les paniers ouverts depuis moins de
15 minutes, donc le stock bouge entre l'affichage et l'envoi.
/ Business refusals are logged as warnings and no longer reach Sentry.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/views.py` | `EventMVT.retrieve` : `places_restantes`, plafond `max_billets` par tarif, `event.remaining_seats`. `action_reservation` et `reservation` : `logger.error` → `logger.warning` |
| `BaseBillet/templates/commun/formulaires/reservation.html` | Les **trois** `bs-counter` (tarif normal, adhésion obligatoire, adhésion dans le panier) écrivent `{% if price.max_billets is not None %}max="…"{% endif %}`. Message des places restantes sous le total |
| `tests/pytest/test_booking_counter_max.py` | Nouveau — 11 tests de rendu : plafond par tarif, plusieurs tarifs, branches « adhésion obligatoire » et « adhésion dans le panier », zéro non avalé, aucun `None` ni `NaN`, seuil d'affichage, jauge visible, évènement fédéré, accord singulier / pluriel |

**i18n :** 1 nouveau `blocktrans` (singulier / pluriel des places restantes) : workflow
i18n à lancer.

---

## Comment tester (a la main) / Manual test

### Test 1 — dernière place
1. Admin : créer un évènement avec une jauge de 3 et un tarif sans quota par personne.
2. Réserver 2 billets.
3. Rouvrir le formulaire : le compteur s'arrête à **1**, le bouton `+` se désactive, et
   le message « Il reste 1 place disponible. » s'affiche sous le total.

### Test 2 — aucun plafond
1. Évènement sans jauge, `max_per_user` vide sur l'évènement et le tarif.
2. Le compteur n'a **pas** d'attribut `max` (DevTools), et le champ n'affiche jamais
   « NaN ».

### Test 3 — jauge visible
1. Activer « Afficher la jauge » sur l'évènement, avec 50 places libres.
2. Le message des places restantes s'affiche même au-dessus de 10.

### Tests automatisés
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_booking_counter_max.py -q
```
