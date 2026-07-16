# API v1 — validation réservation loggée en `warning` (anti-bruit Sentry) / Reservation validation logged at warning

**Date :** 2026-05-25
**Migration :** Non

**Quoi / What :** `ApiReservationViewset.create` (v1) loggeait les **échecs de validation
(400 client)** en `logger.error` → events Sentry. Passé en **`logger.warning`** : la
`LoggingIntegration` Sentry (défaut `event_level=ERROR`, aucune surcharge dans
`settings.py`) ne crée **plus d'event** pour ces 400 (juste un breadcrumb). Le 400 + le
corps d'erreur informent déjà l'appelant.
/ v1 reservation `create` logged client 400 validation failures at `error` (Sentry events).
Now `warning` → no Sentry event (default `event_level=ERROR`).

**Pourquoi / Why :** une validation 400 côté client (payload incomplet) n'est pas une
erreur applicative ; elle ne doit pas solliciter Sentry.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `ApiBillet/views.py` | `ApiReservationViewset.create` : `logger.error` → `logger.warning` sur `validator.errors` |

### Migration
- **Migration nécessaire / Migration required :** Non
