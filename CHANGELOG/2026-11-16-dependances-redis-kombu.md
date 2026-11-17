# Dépendances : redis monté pour kombu 5.7, Playwright 1.65.1 côté hôte / Dependencies: redis raised for kombu 5.7, host Playwright 1.65.1

**Date :** 2026-11-16
**Migration :** Non
**Déploiement :** grosse mise à jour (`poetry.lock` et `pyproject.toml` changent : `make update` s'arrête). Release avec la nouvelle image, puis `TECH_DOC/SESSIONS/DEPLOIEMENT/SPEC.md`, section « Grosse mise à jour ».

## Resume / Summary
**Quoi / What :**
- `poetry update` général (celery 5.7.0, kombu 5.7.0, cryptography 50.0.2, django-tenants 3.13.0, playwright 1.65.2, etc.).
- `pyproject.toml` : `redis = "^5"` devient `redis = ">=6.4,<9"`. `redis` passe de 5.3.1 à 8.1.0. Aucun autre paquet ne bouge avec ce changement.
- `scripts/lancer_tests.sh` et `tests/README.md` : le serveur Playwright de l'hôte (`make e2e-visible`) passe en 1.65.1. C'est la version du driver embarqué par le paquet Python 1.65.2 ; npm n'a pas de 1.65.2.

/ General `poetry update`; redis constraint raised to `>=6.4,<9` (5.3.1 -> 8.1.0); host Playwright server set to the bundled driver 1.65.1.

**Pourquoi / Why :** kombu 5.7.0 exige redis-py 6.4 ou plus. Il ne le vérifie pas à l'installation, mais au démarrage du worker. Avec redis 5.3.1, Celery s'arrête aussitôt :
`VersionMismatch('Redis transport requires redis-py versions 6.1.0 or later. You have 5.3.1')`.
En prod, Celery tourne dans `lespass_django` (supervisor) : sans ce correctif, plus aucune tâche (e-mails, clôtures, cron) ne partirait. Le code n'importe pas redis directement : seuls kombu et channels-redis (`>=4.6`) l'utilisent.
/ kombu 5.7.0 requires redis-py >= 6.4 and only checks it when the worker starts.

**Playwright :** le serveur de navigateur de l'hôte doit avoir la même version que le Playwright du conteneur, sinon la connexion est refusée.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `pyproject.toml` | `redis = ">=6.4,<9"` + commentaire |
| `poetry.lock` | `poetry update` + redis 8.1.0 |
| `scripts/lancer_tests.sh` | `VERSION_DE_PLAYWRIGHT="1.65.1"` + commentaire (version du driver) |
| `tests/README.md` | commandes `npx playwright@1.65.1` |

---

## Vérifications faites / Checks done
Dans une image construite depuis le `dockerfile`, sans volume (comme `lespass_maj`) :
- `poetry sync --dry-run` : 0 install, 0 mise à jour, 0 suppression. `pip check` : aucun conflit.
- `manage.py check` : aucune erreur. Imports `TiBillet.wsgi`, `TiBillet.asgi` et résolveur d'URLs : OK.
- Worker Celery : connecté à Redis, « ready ».
- gunicorn (avec `gunicorn_conf.py`) et daphne : 200.
- Chromium de Playwright 1.65.2 : démarre avec les seules bibliothèques installées par le `dockerfile`.

En dev :
- `lespass_celery` : `poetry sync`, redémarré, « ready », beat démarré.
- Depuis Django : ping du worker, aller-retour d'une tâche avec résultat, envoi et réception sur le channel layer.

## À faire après un `docker compose down` / `build` / `up` en dev
- Le Chromium de Playwright n'est pas dans l'image : `docker exec lespass_django poetry run playwright install chromium`.
- Première fois sur l'hôte pour `make e2e-visible` : `PLAYWRIGHT_HOST_PLATFORM_OVERRIDE=ubuntu24.04-x64 npx -y playwright@1.65.1 install chromium`.
