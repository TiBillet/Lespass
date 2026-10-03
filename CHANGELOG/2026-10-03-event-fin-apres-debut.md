# Fin d'évènement après le début / Event end after start

**Date :** 2026-10-03
**Migration :** Non

## Resume / Summary
**Quoi / What :** un évènement ne peut plus être créé ni modifié avec une date de fin antérieure à sa date de début. Vérification dans le modèle (`Event.clean()`, donc l'admin) et dans les deux API (v1 et v2). Une fin égale au début reste acceptée.
/ An event can no longer be created or edited with an end date before its start date. Checked in the model (`Event.clean()`, hence the admin) and in both APIs (v1, v2). End equal to start is still allowed.

**Pourquoi / Why :** aucune vérification n'existait dans l'admin ni dans les API. Seul `EventQuickCreateSerializer` la faisait, et il n'est plus utilisé.
/ No check existed in the admin or the APIs; only the unused `EventQuickCreateSerializer` had it.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/models.py` | Nouvelle méthode `Event.clean()` : erreur sur `end_datetime` si fin < début |
| `api_v2/serializers.py` | `EventCreateSerializer.validate` : erreur sur `endDate` si fin < début |
| `ApiBillet/serializers.py` | `EventWriteSerializer.validate` : idem, en modification partielle la date absente est lue sur l'évènement existant |
| `tests/pytest/test_event_fin_avant_debut.py` | 10 tests : modèle, formulaire admin, API v2, API v1 (création + modification partielle) |

**i18n :** 1 nouvelle chaîne (`"La fin de l'évènement doit être après son début."`), workflow i18n à lancer.

---

## Comment tester (a la main) / Manual test

### Test 1 — admin, fin avant début
1. Admin > Évènements > Ajouter.
2. Début : demain 20h. Fin : demain 18h. Enregistrer.
3. Attendu : le formulaire est réaffiché avec l'erreur « La fin de l'évènement doit être après son début. » sous le champ de fin. Aucun évènement créé.

### Test 2 — admin, cas valides
1. Même formulaire avec fin = demain 23h → enregistré.
2. Fin vide → enregistré.
3. Fin = début exact → enregistré.

### Test 3 — API v2
`POST /api/v2/events/` avec `startDate` > `endDate` → 400, erreur sur `endDate`.

### Test 4 — API v1, modification partielle
`PATCH` d'un évènement existant en n'envoyant que `endDate` antérieur à sa date de début → 400, erreur sur `endDate`.

### Automatique
`poetry run pytest -q tests/pytest/test_event_fin_avant_debut.py`

### Non couvert
- Import CSV (django-import-export) et `Event.save()` direct (shell, scripts) : `clean()` n'y est pas appelé.
- Les évènements déjà en base avec une fin avant le début ne sont pas corrigés ; ils déclencheront l'erreur à leur prochaine modification dans l'admin.
