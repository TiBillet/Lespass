# API v1 de réservation supprimée / v1 reservation API removed

**Date :** 2026-09-30
**Migration :** Non

## Resume / Summary
**Quoi / What :** `POST /api/reservations/` (et `GET` liste / détail) de l'API v1 est supprimée :
route, `ApiReservationViewset`, `ApiReservationValidator`, `ApiReservationSerializer`.
L'appel répond désormais 404. / The v1 `/api/reservations/` route, viewset, validator and
serializer are removed; calls now answer 404.
**Pourquoi / Why :** cette route répondait 500 à chaque appel (`self.user_commande` jamais posé)
et refusait tout utilisateur connecté : elle ne créait jamais de réservation. L'API v2
(`/api/v2/reservations/`) la remplace. / The route always failed (500); the v2 API replaces it.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `ApiBillet/urls.py` | Retrait de la route `reservations` |
| `ApiBillet/views.py` | Retrait de `ApiReservationViewset` et de ses imports |
| `ApiBillet/serializers.py` | Retrait de `ApiReservationValidator`, `ApiReservationSerializer` et des imports devenus inutiles |
| `tests/pytest/test_api_v1_reservation_supprimee.py` | Nouveau : `/api/reservations/` répond 404 (POST et GET) |

---

## Comment tester (a la main) / Manual test
### Test 1 — la route n'existe plus
1. `curl -i -X POST https://lespass.tibillet.localhost/api/reservations/ -H 'Content-Type: application/json' -d '{}'`
2. Verification : `404 Not Found`.

### Test 2 — l'API v2 fonctionne toujours
1. Appeler `GET /api/v2/reservations/` avec `Authorization: Api-Key <clé>`.
2. Verification : `200`.
