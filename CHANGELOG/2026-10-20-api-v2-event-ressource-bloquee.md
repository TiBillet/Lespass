# API v2 : un événement peut bloquer une ressource / API v2: an event can block a booking resource

**Date :** 2026-10-20
**Migration :** Non

## Resume / Summary
**Quoi / What :** `POST /api/v2/events/` accepte `additionalProperty` `blockedResource` = l'id d'une ressource du module réservation (`/booking/<id>/resource/`). L'événement remplit `Event.ressource_bloquee`. `endDate` est alors obligatoire (400 sinon), un id inconnu renvoie 400. Le champ reste interne : il n'est jamais renvoyé.
/ `POST /api/v2/events/` accepts `additionalProperty` `blockedResource` (booking Resource id). Requires `endDate`. Write-only.

**Pourquoi / Why :** créer par script des événements récurrents (ex : tous les mercredis matin) qui occupent une salle, sans repasser chaque événement dans l'admin.
/ Script recurring events that occupy a room without editing each one in the admin.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `api_v2/serializers.py` | `EventCreateSerializer.validate()` lit `blockedResource` ; `create()` remplit `ressource_bloquee` |
| `api_v2/openapi-schema.yaml` | Doc de `blockedResource` + exemple de requête |
| `tests/pytest/test_api_v2_event_ressource_bloquee.py` | 3 tests : création OK, sans fin refusée, ressource inconnue refusée |

---

## Comment tester (a la main) / Manual test

### Test 1 — scenario nominal
1. Avoir une ressource booking (id visible dans l'URL `/booking/<id>/resource/`) et une clé API avec le droit `event`.
2. ```bash
   curl -k -X POST https://lespass.tibillet.localhost/api/v2/events/ \
     -H "Authorization: Api-Key $CLE" -H "Content-Type: application/json" \
     -d '{"@type":"Event","name":"Test blocage","startDate":"2026-11-04T09:00:00+01:00","endDate":"2026-11-04T12:00:00+01:00","additionalProperty":[{"name":"blockedResource","value":1}]}'
   ```
3. Attendu : 201, la réponse ne contient pas `blockedResource`.
4. Ouvrir `/booking/1/resource/` : les créneaux du 04/11 entre 9h et 12h sont complets.
5. Dans l'admin, la fiche de l'événement montre la ressource bloquée.

### Test 2 — cas limites
- Sans `endDate` : 400 sur `endDate` (« Une date de fin est obligatoire pour bloquer une ressource. »).
- `"value": 999999` : 400 sur `additionalProperty` (« Ressource à bloquer introuvable »).

### Verifs DB
```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py tenant_command shell -s lespass \
  -c "from BaseBillet.models import Event; print(Event.objects.filter(ressource_bloquee__isnull=False).values_list('name','datetime','ressource_bloquee'))"
```
