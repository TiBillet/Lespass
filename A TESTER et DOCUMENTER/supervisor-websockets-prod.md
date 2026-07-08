# WebSockets en production : supervisord mono-conteneur

Chantier 2 controlvanne (suite du câblage) — décision actée avec le mainteneur :
pattern LaBoutik transposé, **un seul conteneur** en production (moins
d'empreinte mémoire), supervisord orchestre les 3 processus.

## Ce qui a été fait

| Fichier | Changement |
|---|---|
| `supervisor/supervisord.conf` | **Créé** — supervisord non-root (user tibillet), logs `/DjangoFiles/logs/supervisor/`, include conf.d |
| `supervisor/conf.d/gunicorn.conf` | **Créé** — HTTP `:8002`, même commande qu'avant **sans `--reload`** |
| `supervisor/conf.d/daphne.conf` | **Créé** — WebSockets `:7999` (`TiBillet.asgi:application`) |
| `supervisor/conf.d/celery.conf` | **Créé** — worker + beat (`-B`), remplace le conteneur `lespass_celery` |
| `start.sh` | Lance supervisord puis `exec tail -f` des logs (pattern LaBoutik) ; ne lance plus gunicorn directement |
| `dockerfile` | + paquet `supervisor` (apt, avant `USER tibillet`) |
| `nginx_prod/lespass_prod.conf` | + `location ~ ^/(wss\|ws)/` → `lespass_django:7999` (Upgrade + `proxy_read_timeout 86400`) |
| `docker-compose.pre-prod.yml` | `lespass_django` : `command: "bash start.sh"` ; service **`lespass_celery` supprimé** ; nginx monte **`nginx_prod/lespass_prod.conf`** |
| `TiBillet/asgi.py` | **Fix `AppRegistryNotReady`** : `get_asgi_application()` déplacé AVANT les imports applicatifs (bug dormant, invisible sous runserver, fatal sous daphne standalone — c'est le fix « étape 2 » documenté par Mike) |
| `launch_ws.sh` | **Supprimé** (orphelin, remplacé par `conf.d/daphne.conf`) |
| `flush.sh` | Conscient de supervisord : `stop all` avant le dropdb, `start all` à la fin (dev inchangé : runserver final) |

**Dev : rien ne change.** `docker-compose.yml` + `start_dev.sh` + runserver byobu
(qui sert HTTP **et** WS sur :8002) restent identiques ; le service celery du
compose **dev** est conservé.

## Migration nécessaire : Non (mais REBUILD de l'image obligatoire)

```bash
docker compose -f docker-compose.pre-prod.yml build lespass_django
```
(le paquet `supervisor` entre dans l'image)

## Déjà testé (dans le conteneur dev, supervisor installé à la main)

- supervisord parse la conf réelle et gère les 3 programmes (status OK)
- daphne `:7999` sous supervisord : handshake WebSocket → **101 Switching
  Protocols** (et **403** sans header `Origin` — le validateur d'hôtes est actif)
- le crash `AppRegistryNotReady` reproduit PUIS corrigé par le fix asgi.py
- non-régression dev : WS sur `:8002` (runserver) → 101 ; `manage.py check` 0 ;
  47 tests controlvanne + discovery verts

⚠️ Le paquet supervisor a été installé À LA MAIN dans le conteneur dev courant
pour ces tests (`apt-get install supervisor`) — jetable, un rebuild l'apporte
proprement via le dockerfile.

## Tests à réaliser (pre-prod, après rebuild)

1. `docker compose -f docker-compose.pre-prod.yml up -d --build`
2. `docker logs lespass_django` : « Supervisord start », puis les logs
   gunicorn/daphne/celery défilent
3. `docker exec lespass_django supervisorctl -c /DjangoFiles/supervisor/supervisord.conf status`
   → `gunicorn RUNNING`, `daphne RUNNING`, `celery RUNNING`
4. HTTP : la home du tenant répond via Traefik/nginx
5. WebSocket : ouvrir `/controlvanne/kiosk/` → console « WS connecté sur
   /ws/rfid/all/ » ; idem POS laboutik (`ws/laboutik/`)
6. Celery : vérifier qu'une tâche beat part (logs celery.logs) et qu'il n'y a
   **qu'un seul** worker (`docker ps` : plus de conteneur lespass_celery)
7. Redémarrage d'un service isolé :
   `supervisorctl -c /DjangoFiles/supervisor/supervisord.conf restart daphne`

## Notes d'exploitation

- Gestion des services : `supervisorctl -c /DjangoFiles/supervisor/supervisord.conf status|restart|stop <prog>`
- Logs par service : `/DjangoFiles/logs/{gunicorn,daphne,celery}.logs` +
  `logs/supervisor/supervisord.log`
- `celerybeat-schedule` s'écrit dans `/DjangoFiles` (volume bind en pre-prod)
- Le message supervisord « CRIT Server 'unix_http_server' running without any
  HTTP authentication » est attendu : socket unix chmod 0700, conteneur
  mono-utilisateur (identique LaBoutik)
