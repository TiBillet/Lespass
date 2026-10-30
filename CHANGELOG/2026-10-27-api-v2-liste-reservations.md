# API v2 : liste des réservations et champs inscrits / API v2: reservation list and attendee fields

**Date :** 2026-10-27
**Migration :** Non

## Resume / Summary
**Quoi / What :** nouvelle route `GET /api/v2/reservations/?event=<uuid>` (liste des inscrits d'un événement). Chaque réservation (liste, détail, création) expose en plus `underName.givenName` / `underName.familyName` (compte qui réserve), `totalPrice` (montant payé en euros, avoirs et remboursements déduits) + `priceCurrency`, et les réponses au formulaire dynamique dans `additionalProperty` (`customForm`). Le `reservationStatus` traduit maintenant tous les statuts : payée ou e-mail vérifié → `ReservationConfirmed`, annulée → `ReservationCancelled`. / New `GET /api/v2/reservations/?event=<uuid>` route (attendee list). Each reservation also exposes first/last name, amount paid, currency and dynamic form answers. `reservationStatus` now maps every status (paid → confirmed, cancelled → cancelled).
**Pourquoi / Why :** issue #487 (La Raffinerie) : récupérer la liste des inscrits à un atelier avec les montants payés. Sans route de liste, il fallait connaître chaque uuid à l'avance. Une réservation payée ressortait « en attente », une annulée aussi. / Issue #487: fetch a workshop's attendee list with amounts paid. Paid and cancelled reservations used to come out as "pending".

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `api_v2/views.py` | `ReservationViewSet.list()` avec filtre `event` (400 si uuid invalide) |
| `api_v2/serializers.py` | `ReservationSchemaSerializer` : noms, `totalPrice`, `priceCurrency`, `customForm`, statuts complets |
| `api_v2/openapi-schema.yaml` | Route `listReservations` + nouveaux champs du schéma `Reservation` |
| `tests/pytest/test_api_v2_reservation_liste.py` | 6 tests (filtre, 400, montant, noms, formulaire, annulée) |
| `TECH_DOC/SKILLS/tibillet-api/references/recettes.md` | Repère de la route de liste |

---

## Comment tester (a la main) / Manual test
### Test 1 — liste des inscrits d'un événement
1. Admin → Clés API : créer une clé avec la permission « Réservation ».
2. Réserver 2 places payantes sur un événement (en ligne, ou en caisse).
3. `curl -s -H "Authorization: Api-Key <clé>" "https://lespass.tibillet.localhost/api/v2/reservations/?event=<uuid de l'événement>" | jq`
4. Attendu : la réservation est dans `results`, avec `underName.email`, `givenName`, `familyName`, `totalPrice` (ex. `"20.00"`), `priceCurrency: "EUR"`, `reservationStatus: .../ReservationConfirmed`.

### Test 2 — formulaire dynamique
1. Ajouter une question au formulaire du produit billet, réserver en y répondant.
2. Relire la liste : `additionalProperty` contient `{"name": "customForm", "value": {"<libellé de la question>": "<réponse>"}}`.

### Test 3 — cas limites
- `?event=pas-un-uuid` → 400.
- Annuler la réservation dans l'admin → elle reste dans la liste avec `ReservationCancelled` ; si elle a été remboursée, `totalPrice` diminue d'autant.
- Sans `?event=` → toutes les réservations du lieu, les plus récentes d'abord.

### Verifs automatiques
`docker exec lespass_django poetry run pytest tests/pytest/test_api_v2_reservation_liste.py -q`
