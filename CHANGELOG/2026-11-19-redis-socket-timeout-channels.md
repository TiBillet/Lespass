# Les websockets ne se coupent plus toutes les 5 secondes / Websockets no longer drop every 5 seconds

**Date :** 2026-11-19
**Migration :** Non

## Resume / Summary
**Quoi / What :** `CHANNEL_LAYERS` fixe `socket_timeout` à 15 s pour la connexion Redis de Django Channels.
/ `CHANNEL_LAYERS` sets `socket_timeout` to 15 s on the Django Channels Redis connection.

**Pourquoi / Why :** redis-py 8 (installé avec le commit `19130e7b`) coupe toute lecture Redis après 5 s par défaut.
channels_redis attend les messages avec `BZPOPMIN` bloquant pendant 5 s. Le client abandonnait donc avant la réponse
de Redis : `TimeoutError: Timeout reading from redis:6379` (Sentry BILLETTERIE-COOP-W4), le consumer plantait, et
chaque websocket inactif (imprimante Sunmi, caisse, kiosque, tireuse) se reconnectait toutes les ~9 s. Un ticket
envoyé pendant la reconnexion était perdu. Celery et le cache ne sont pas concernés (ils fixent leurs propres délais).
/ redis-py 8 defaults `socket_timeout` to 5 s, equal to channels_redis' blocking `BZPOPMIN` (5 s): idle websockets
crashed every ~9 s. Known upstream: django/channels_redis#422.

Fixes https://tibillet.sentry.io/issues/BILLETTERIE-COOP-W4

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `TiBillet/settings.py` | `CHANNEL_LAYERS` : hôte en dict avec `"socket_timeout": 15` |

---

## Comment tester (a la main) / Manual test

**Le venv de dev doit avoir redis-py 8.x** (celui du `poetry.lock`). Avec redis-py 5.3.1, le bug n'apparaît pas et
le test ne prouve rien. Vérifier : `docker exec lespass_django poetry run python -c "import redis; print(redis.__version__)"`.

### Test 1 — un websocket inactif reste ouvert
1. Redémarrer Daphne (seul service à relancer en prod).
2. Ouvrir la caisse LaBoutik ou connecter une imprimante Sunmi Inner.
3. Ne rien faire pendant 1 minute.
4. Attendu : aucune déconnexion dans la console du navigateur, aucune ligne
   `Timeout reading from redis` dans `logs/daphne.logs`, rien de nouveau dans Sentry BILLETTERIE-COOP-W4.

### Test 2 — un message passe après une longue attente
1. Après 1 minute d'inactivité, lancer une impression ou une vente.
2. Attendu : le ticket sort, la caisse reçoit la mise à jour.

### Vérif en prod
- Sentry BILLETTERIE-COOP-W4 : plus aucun événement après le redémarrage de Daphne.
