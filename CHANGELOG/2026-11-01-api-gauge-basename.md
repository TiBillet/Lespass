# Route /api/gauge/ : une clé valide n'est plus refusée / Route /api/gauge/: a valid key is no longer refused

**Date :** 2026-11-01
**Migration :** Non

## Resume / Summary
**Quoi / What :** `GET /api/gauge/` répond de nouveau aux clés API admin qui ont le droit « Tickets ». Une clé sans ce droit reçoit toujours un 403.
/ `GET /api/gauge/` works again for admin API keys with the "Tickets" right. A key without that right still gets a 403.

**Pourquoi / Why :** `get_apikey_valid()` lit `view.basename`, or `Gauge` est une `APIView` montée avec `path()` et n'en a pas. L'`AttributeError` était attrapée et transformée en 403, y compris pour une clé valide. La route était fermée depuis le passage à `TenantAdminApiPermission` (`154eb92f`, 2025-01-08). Sentry : BILLETTERIE-COOP-VS.
/ `get_apikey_valid()` reads `view.basename`, which `Gauge` lacks. The caught `AttributeError` became a 403, even for a valid key. The route had been closed since `154eb92f` (2025-01-08).

**Droits / Permissions :** la jauge suit le droit `ticket`. Aucun accès nouveau : avec ce droit, une clé admin lit déjà le détail des billets du jour sur `/api/ticket/`.
/ The gauge follows the `ticket` right. No new access: such a key can already read today's tickets on `/api/ticket/`.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `ApiBillet/views.py` | `Gauge.basename = "ticket"` |
| `tests/pytest/test_api_gauge.py` | Nouveau : clé avec et sans le droit `ticket` |

---

## Comment tester (a la main) / Manual test
### Test 1 — clé admin avec le droit « Tickets »
1. Dans l'admin, créer une clé API avec le droit « Tickets », liée à un admin du lieu.
2. `curl -H "Authorization: Api-Key <clé>" https://lespass.tibillet.localhost/api/gauge/`
3. Réponse 200 avec `gauge_max`, `all_tickets` et `scanned_tickets`.

### Test 2 — clé sans le droit
1. Retirer le droit « Tickets » de la clé.
2. Refaire l'appel : réponse 403, et aucune erreur `get_apikey_valid` dans les logs.

### Tests automatiques
`docker exec lespass_django poetry run pytest tests/pytest/test_api_gauge.py -q`
