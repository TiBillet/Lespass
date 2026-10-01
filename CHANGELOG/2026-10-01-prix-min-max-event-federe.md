# Prix des évènements : fiche fédérée et agenda / Event prices: federated page and agenda

**Date :** 2026-10-01
**Migration :** Non

## Resume / Summary
**Quoi / What :**
- `EventMVT.federated_events_get()` et `federated_events_get_hex8()` posent `price_min`, `price_max` et `free_price` sur l'event, via le helper `_calculer_prix_min_max_event()`.
- L'agenda (`federated_events_filter()`, donc `list` et `partial_list`) pose `event.price_min` en texte (« A partir de X € », « Prix libre », « Entré libre »), via le helper `_libelle_prix_agenda()`. Les cartes `cotton/V2/event_card.html` l'affichent.
- La clé du cache de l'agenda contient la langue active.
- Les tarifs archivés sont ignorés partout.

/ Federated event getters set `price_min`, `price_max`, `free_price`. The agenda sets a text `price_min` shown on event cards. The agenda cache key now includes the active language. Archived prices are ignored.

**Pourquoi / Why :**
- Le calcul existait dans `tenant_retrieve()` et n'a pas été recopié quand cette méthode a été remplacée par `federated_events_get()` (commit `869ce52f`, 2025-04-09) : la fiche d'un event fédéré n'affichait plus de prix.
- Les cartes de l'agenda n'affichaient pas de prix (point R1 noté dans `event_card.html`).
- Le libellé du prix est traduit avant la mise en cache : sans la langue dans la clé, tous les visiteurs verraient la langue du premier.

/ Federated event pages had lost their price; agenda cards never showed one; the price label is translated before caching, hence the language in the cache key.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/views.py` | Helpers `EventMVT._calculer_prix_min_max_event()` et `_libelle_prix_agenda()` ; appels dans `federated_events_get()`, `federated_events_get_hex8()` et `federated_events_filter()` ; langue dans la clé de cache de l'agenda ; import `get_language` |

---

## Comment tester (a la main) / Manual test
### Test 1 — fiche d'un event d'un lieu fédéré
1. Sur le lieu A, fédérer le lieu B (admin → lieux fédérés).
2. Sur le lieu B, créer un event publié avec deux tarifs (ex : 5 € et 12 €).
3. Depuis le domaine du lieu A, ouvrir `/event/<slug-de-l-event-de-B>/`.
4. Vérifier : le bloc de réservation affiche la fourchette de prix (5 € → 12 €).

### Test 2 — agenda
1. Ouvrir `/event/` sur le lieu A (skin V2).
2. Event avec tarifs 5 € et 12 € → la carte affiche « A partir de 5 € ».
3. Event avec seulement un tarif en prix libre → « Prix libre ».
4. Event sans tarif → « Entré libre ».
5. Les events du lieu fédéré B affichent aussi leur prix.
6. Filtrer par jour (`?date=AAAA-MM-JJ`) et charger la page suivante : les prix restent affichés.

### Test 3 — cache et langue
1. Ouvrir `/event/` en français, puis passer en anglais.
2. Vérifier : le libellé du prix change de langue (pas de texte français figé en anglais).
3. Modifier un event, recharger : la liste est bien rafraîchie.

### Cas limites
- Un tarif archivé n'entre jamais dans le min/max.
- Les nouvelles chaînes ne sont pas nouvelles : « A partir de %(price)s € », « Prix libre », « Entré libre » existent déjà (utilisées par `index()`).
