# CHANTIER-02 — WebSockets en production : supervisord mono-conteneur

**Date** : 2026-07-06 — **FAIT** (recette pre-prod restante, cf. A TESTER)
**Décision mainteneur** : pattern LaBoutik (`../LaBoutik/supervisor/`),
**un seul conteneur** en production (moins d'empreinte mémoire) — celery
inclus dans supervisord, plus de conteneur `lespass_celery` séparé.

## Le problème

En production, `start.sh` lançait gunicorn (WSGI) seul : **rien ne servait
`/ws/`**. Le POS laboutik (`ws/laboutik/`, `ws/printer/`) et les tireuses
controlvanne (`ws/rfid/`) n'avaient aucun temps réel hors dev (en dev, le
runserver-daphne de channels sert HTTP + WS sur :8002).

## Ce qui a été livré

| Pièce | Détail |
|---|---|
| `supervisor/supervisord.conf` | Non-root (user tibillet du conteneur), nodaemon, logs `/DjangoFiles/logs/supervisor/`, include `conf.d/*.conf` |
| `conf.d/gunicorn.conf` | HTTP `:8002` — commande historique sans `--reload` |
| `conf.d/daphne.conf` | WebSockets `:7999` — `poetry run daphne TiBillet.asgi:application` |
| `conf.d/celery.conf` | worker + beat (`-B --concurrency=6`) |
| `start.sh` | poetry/collectstatic/MIGRATE=1 inchangés, puis supervisord + `exec tail -f` des logs |
| `dockerfile` | + paquet `supervisor` (avec `apt-get update &&` sur la ligne — piège du cache Docker) |
| `nginx_prod/lespass_prod.conf` | `location ~ ^/(wss\|ws)/` → `:7999`, `proxy_read_timeout 86400` |
| `docker-compose.pre-prod.yml` | django → `bash start.sh`, nginx monte la conf **prod** (montait la conf dev !), service celery supprimé |
| `flush.sh` | Détecte le socket supervisord : `stop all` → flush → `start all` (dev : comportement inchangé, runserver final) |
| `launch_ws.sh` | Supprimé (orphelin) |

## Le bug déterré : `AppRegistryNotReady`

Premier lancement de daphne standalone sous supervisord → crash immédiat.
Cause : `TiBillet/asgi.py` importait `wsocket`/`controlvanne` **avant**
`get_asgi_application()`. Invisible sous runserver (Django déjà initialisé),
fatal pour tout serveur ASGI standalone. C'est exactement le bug dormant
documenté par Mike (étape 2 de `controlvanne/Synthese_merge_vs_chantiers.md`).
Fix appliqué : ordre canonique Django/Channels + commentaire de garde.

## Validé en conteneur dev (supervisor installé à la main, jetable)

- supervisord parse la conf réelle, 3 programmes gérés (`status` OK)
- daphne `:7999` : handshake WS → **101 Switching Protocols** ; sans header
  `Origin` → **403** (AllowedHostsOriginValidator actif)
- dev intact : WS 101 sur `:8002` (runserver), `check` 0, 47 tests verts

## Recette pre-prod (après rebuild) → `A TESTER et DOCUMENTER/supervisor-websockets-prod.md`

## Exploitation

```bash
docker exec lespass_django supervisorctl -c /DjangoFiles/supervisor/supervisord.conf status
docker exec lespass_django supervisorctl -c /DjangoFiles/supervisor/supervisord.conf restart daphne
# Flush pre-prod (stop all → flush → start all, automatique) :
docker exec -e DEBUG=1 lespass_django bash flush.sh
```
