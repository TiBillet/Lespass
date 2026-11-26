# Admin des événements : plus d'erreur 500 avec une jauge à 0 / Event admin: no more 500 error with a zero capacity

**Date :** 2026-11-26
**Migration :** Non

## Resume / Summary
**Quoi / What :** la colonne « Pourcentage de ticket valide » de la liste des événements affiche « — » quand la jauge vaut 0, au lieu de faire planter la page.
/ The "valid tickets percentage" column shows "—" when the capacity is 0, instead of crashing the page.

**Pourquoi / Why :** le pourcentage divisait par `jauge_max` dans la requête SQL. Un seul événement à jauge 0 suffisait à lever `DataError: division by zero` : la liste `/admin/BaseBillet/event/` du lieu (Sentry BILLETTERIE-COOP-W8) et la fiche de modification de l'événement (BILLETTERIE-COOP-W9) tombaient en erreur 500. La fiche passe elle aussi par `get_queryset()`.
/ The percentage divided by `jauge_max` in SQL. One zero-capacity event made the event list and that event's change page return a 500 error.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin_tenant.py` | `EventAdmin.get_queryset()` : `NullIf(F("jauge_max"), 0)` au dénominateur. `display_valid_tickets_percentage()` : affiche « — » quand le pourcentage vaut `None`. |
| `tests/pytest/test_event_admin_jauge_zero.py` | Nouveau : 4 tests (liste qui se charge, fiche qui s'ouvre, colonne « — », témoin jauge normale à « 0.0% »). |

---

## Comment tester (a la main) / Manual test
### Test 1 — jauge à zéro
1. Dans l'admin d'un lieu, créer ou modifier un événement et mettre sa jauge à 0.
2. Ouvrir la liste des événements `/admin/BaseBillet/event/`.
3. La page s'affiche. La colonne « Pourcentage de ticket valide » de cet événement montre « — ».

### Test 2 — jauge normale
1. Un événement avec une jauge de 50 et aucun billet affiche « 0.0% ».
2. Trier la liste sur la colonne pourcentage : pas d'erreur.

### Test 3 — fiche de l'événement à jauge zéro
1. Depuis la liste, cliquer sur l'événement à jauge 0.
2. La page de modification s'ouvre sans erreur.

### Verifs automatiques
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_event_admin_jauge_zero.py -q
```
