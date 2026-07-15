# Sentry — tracing désactivé (budget spans saturé) / Sentry tracing disabled

**Date :** 2026-05-25
**Migration :** Non · **Déploiement requis :** Oui (redémarrage prod)

**Quoi / What :** `sentry_sdk.init` (settings) : `traces_sample_rate` et
`profiles_sample_rate` passés de **0.3 → 0.0**. Le tracing/performance monitoring
(spans) est coupé ; les **events d'erreur (issues) restent captés normalement**.
/ Tracing/profiling sampling 0.3 → 0.0. Spans off, error events unaffected.

**Pourquoi / Why :** le volume festival (4000 users + tâches Celery) avec 30 % de
transactions tracées a **saturé le budget de spans** Sentry (100 % consommé → spans
droppés). On coupe le tracing pour ne plus exploser le budget. Remonter prudemment
(0.01–0.05) plus tard si besoin de perf.

**Note :** ne restaure pas l'ingestion de la **période en cours** (déjà consommée) —
ça nécessite un ajustement budget côté Sentry ou le reset de période. Prend effet
**au déploiement** (l'init ne tourne qu'en prod : `not DEBUG and SENTRY_DNS`).

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `TiBillet/settings.py` | `sentry_sdk.init` : `traces_sample_rate=0.0`, `profiles_sample_rate=0.0` |

### Migration
- **Migration nécessaire / Migration required :** Non
