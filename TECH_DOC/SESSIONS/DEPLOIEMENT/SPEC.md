# Chantier 01 — `make update` : mettre la prod à jour sans coupure

> **Statut** : spec, à valider par le mainteneur (2026-10-18). Relue par Fable (corrections intégrées).
> **Remplace** l'idée 1 et l'idée 2 de `TECH_DOC/SESSIONS/TODO/DEPLOIEMENT-mise-a-jour-sans-coupure.md`
> (constats du 2026-10-12, toujours valables, à lire avant ce document). Correction de ce TODO :
> HUP ne fait pas « aucune requête perdue sans attente », voir la première décision.

## Le but

Une mise à jour de code, avec ou sans migration, ne doit produire **ni 502, ni gel, ni
ralentissement** visible. Une mise à jour « lourde » (dépendances, image, système) reste une
opération planifiée, avec une coupure courte assumée.

## Les décisions

| Sujet | Décision | Raison |
|---|---|---|
| Rechargement de gunicorn | Workers remplacés **un par un** : TTIN, attente du préchauffage, TTOU | HUP arrête les anciens workers AVANT que les nouveaux aient chargé Django. Banc d'essai du 2026-10-18 (dev, 22 cœurs) : HUP = une requête bloquée 3,9 s ; TTIN/TTOU = 35 ms au pire, 0 erreur sur 240 requêtes |
| Où tourne la migration | Dans un **conteneur jetable** `lespass_maj`, lancé depuis l'image de la nouvelle version, pendant que l'ancien code sert | Le dossier servi ne change qu'après la migration : pendant les ~15 min de `migrate_schemas`, les workers servent l'ancien code ET les anciens gabarits |
| Où se construit l'image | Sur la machine du mainteneur (script de release), poussée sur Docker Hub | Pas de CPU pris au petit serveur de prod |
| Tags de l'image | `latest` (la version courante) et `$VERSION` (pour revenir en arrière) | Choix du mainteneur : `latest` est le plus parlant au quotidien |
| Lien image ↔ code | L'image porte le label `org.opencontainers.image.revision` = SHA du commit. `make update` tire `latest` et refuse de continuer si ce label n'est pas le commit cible | Sans ce contrôle, `latest` pourrait être plus récent ou plus ancien que le git de la prod (release oubliée, commit poussé sans release) |
| Image du conteneur de prod | `tibillet/lespass:latest` dans le compose | Un `up -d --no-deps lespass_django` fait à la main recrée la prod sur la dernière image tirée par `make update` |
| Daphne, Celery | Simple `restart` | Les fronts se reconnectent ; Celery finit ses tâches (TERM) |
| Migrations incompatibles avec l'ancien code | Règle expand/contract, gérée par le mainteneur | Fenêtre courte acceptée ; pas d'outil (syzygy, safemigrate) pour l'instant |
| Exécuteur de migration | `multiprocessing` par défaut ; `EXECUTEUR=standard` si une migration ajoute une clé étrangère vers une table publique | Interblocage vu deux fois dans ce cas (TODO, 2026-10-06) |
| gunicorn 26 + `gunicornc` | Chantier 02 | `show workers` (colonne BOOTED) remplacera la lecture du log |

## Préparer un serveur — `make env`

Une fois, sur un nouveau serveur (`scripts/fabriquer_env_prod.sh`, modèle `env_prod_example`) :
1. Pas de `.env` : copie de `env_prod_example`, secrets tirés au hasard à la place de `A_GENERER`
   (`DJANGO_SECRET`, `FERNET_KEY` au format Fernet, `POSTGRES_PASSWORD`), droits 600. Un `.env`
   existant n'est **jamais** remplacé : une nouvelle `FERNET_KEY` rendrait illisibles les données
   chiffrées en base.
2. Création des dossiers montés qui manquent (`database/`, `backup/`, `ssh/` en 700, `logs/`, `www/`).
3. Contrôles, sans rien modifier : valeurs `A_REMPLIR` restantes, `TEST`/`DEBUG`/`DEMO`/`STRIPE_TEST`
   à 0, réseau `frontend` (Traefik), `docker compose`, `at`, ligne `saveDb.sh` dans la
   crontab, clé borg dans `ssh/`.

Relançable à volonté : après le premier passage, il ne fait plus que les contrôles.
`env_prod_example` ne garde que ce que la prod lit : les variables de dev de `env_example`
(`TLS_CERT_NAME`, `E2E_TEST_TOKEN`, `DEMO_TAGID_*`, Formbricks, Fedow de test, Sunmi) n'y sont pas,
et `FERNET_KEY` n'y figure qu'une fois (`env_example` la déclare deux fois, Lespass puis Fedow : dans
un même `.env`, la dernière ligne gagne).

## Les trois gestes

### 1. Release (machine du mainteneur) — `docker_push_update.sh` revu

1. Refuse des modifications non commitées (`git status --porcelain --untracked-files=no`) :
   l'image doit être EXACTEMENT un commit. Les fichiers non suivis n'entrent pas dans l'image.
2. Refuse un commit absent du dépôt distant : `git fetch` puis
   `git merge-base --is-ancestor HEAD @{u}` (la prod doit pouvoir le récupérer).
3. Construit depuis le commit, dans un dossier temporaire, pour garder les DEUX barrières
   (seuls les fichiers suivis, PUIS le `.dockerignore`) :
   ```bash
   dossier=$(mktemp -d)
   git archive HEAD | tar -x -C "$dossier"
   docker build -f "$dossier/dockerfile" \
       --label org.opencontainers.image.revision=<sha complet> \
       -t tibillet/lespass:$VERSION -t tibillet/lespass:latest "$dossier"
   ```
   Pas de `git archive | docker build -` : le `.dockerignore` n'est garanti que pour un contexte
   qui est un dossier. Le label dit de quel commit vient l'image (`docker inspect`) :
   `make update` s'en sert pour vérifier qu'il tire la bonne.
4. Refuse un `$VERSION` déjà publié (`docker manifest inspect`) : un tag de version sert à revenir
   en arrière, il ne s'écrase jamais. Incrémenter `VERSION` à chaque release.
5. Pousse les deux tags.

`REFAIRE_LA_BASE=1 ./docker_push_update.sh` ajoute `--pull --no-cache` : `python:3.11` retéléchargé,
système et venv reconstruits. Réservé aux grosses mises à jour : sinon chaque release repousse et
fait retélécharger tout le venv (~690 Mo).

Le script ne fait plus `git checkout main && git pull` : il construit HEAD, tel quel.
`start.sh` ne migre jamais : une migration au démarrage empêcherait supervisord de partir,
donc le site de répondre, jusqu'à sa fin. Le fichier `VERSION` ne porte que le numéro de version.

### 2. `make update` (prod) — `scripts/mise_a_jour_prod.sh`

| # | Étape | Arrêt si… |
|---|---|---|
| 1 | Verrou `flock` + journal `logs/mise_a_jour_*.log` | un autre `make update` tourne |
| 2 | Fenêtre horaire : :05–:20 / :35–:50 | hors fenêtre |
| 3 | État de départ : gunicorn, daphne, celery en RUNNING (lecture de la sortie de `status`) ; arbre propre ; venv de prod conforme au `poetry.lock` de HEAD (`poetry install --dry-run` doit annoncer `0 installs, 0 updates, 0 removals`) ; aucun conteneur `lespass_maj` qui tourne (un `lespass_maj` arrêté, reste d'un échec : on journalise ses logs puis `docker rm`) | un seul point faux |
| 4 | `git fetch`, cible = `@{u}`. HEAD = cible et `logs/dernier_commit_deploye` = cible → « rien à faire » | pas d'upstream |
| 5 | Fichiers à geste manuel changés entre HEAD et la cible : `poetry.lock`, `pyproject.toml`, `dockerfile`, `start.sh`, `supervisor/`, `gunicorn_conf.py`, `nginx_prod/`, `docker-compose.prod.yml` | → « grosse mise à jour », rien n'est touché |
| 6 | `docker pull tibillet/lespass:latest` (aucun effet sur la prod ; peut prendre plusieurs minutes si la couche du venv a changé : c'est pourquoi il passe AVANT la fenêtre stricte). Son label `org.opencontainers.image.revision` doit être le commit cible | label différent → « la release de ce commit n'est pas faite » |
| 7 | Migration nécessaire ? `*/migrations/*.py` changés depuis `logs/dernier_commit_migre` (absent → oui ; `MIGRER=1` / `MIGRER=0` pour forcer). Si oui : l'heure est relue, fenêtre :05–:10 / :35–:40, et aucun `pg_dump%` dans `pg_stat_activity` | hors fenêtre stricte, sauvegarde en cours |
| 8 | Conteneur `lespass_maj`, lancé **détaché** (`docker compose run -d --no-deps --name lespass_maj`, sans `--rm`, avec `PYTHONUNBUFFERED=1`), suivi par `docker logs -f` dans le journal, code retour par `docker wait`, puis `docker rm`. Il fait : `manage.py check`, import de `TiBillet.wsgi` et `TiBillet.asgi`, peuplement des deux résolveurs d'URLs, puis `migrate_schemas` si nécessaire (`nice -n 19 ionice -c3`, `PGOPTIONS="-c lock_timeout=5s"`, `--executor=${EXECUTEUR:-multiprocessing}`). Succès de la migration, ou `MIGRER=0` → `logs/dernier_commit_migre` | contrôle ou migration en échec : le code servi n'a pas bougé |
| 9 | `git merge --ff-only <sha>`, puis `collectstatic` dans `lespass_django` | — |
| 10 | Gunicorn un par un : boucle tant qu'un PID d'ancien worker vit ; TTIN (`supervisorctl signal`) → attendre `warmup worker <pid> : ` dans `logs/gunicorn.logs` (90 s) → TTOU → attendre le départ d'un ancien (40 s). `trap` qui rend le worker en trop. PID du maître relu à chaque tour. Arrêt si aucun worker trouvé au départ | ligne d'échec du préchauffage (pas de TTOU de rattrapage : il retirerait un ancien worker sain), « Worker failed to boot », « Shutting down: Master », maître changé |
| 11 | `/robots.txt` → 200, cinq fois (Host = `$DOMAIN`, `X-Forwarded-Proto: https`) | autre code |
| 12 | `restart daphne`, `restart celery`, 15 s, tout en RUNNING. Puis `logs/dernier_commit_deploye`, et `docker image prune -f --filter label=org.opencontainers.image.revision` : l'ancienne `latest`, détaguée par le pull, part, sauf si un conteneur l'utilise encore (celui de prod) ; les images des autres piles ne sont pas touchées | un service pas en RUNNING |

**Pourquoi détaché (étape 8).** Un `docker compose run` attaché relaie TOUS les signaux au
conteneur (`ForwardAllSignals`) : un Ctrl-C, ou la coupure d'une session SSH hors byobu,
interromprait `migrate_schemas` au milieu d'un schéma. Détaché, le conteneur ne dépend plus du
terminal : si le script meurt, la migration finit seule, et la relance de `make update` la trouve
(étape 3). Sans `--rm`, sa sortie reste lisible jusqu'au `docker rm`. `--name` est obligatoire :
`docker compose run` ignore le `container_name` du compose et invente un nom aléatoire. Le nom
fixe interdit d'ailleurs d'en lancer deux à la fois (« name already in use »).

**Pourquoi le contrôle de l'étape 8 suffit.** Il tourne dans l'image de la nouvelle version : il
prouve que le code ET ses dépendances démarrent. C'est indispensable : un worker gunicorn qui ne
démarre pas (code 3 ou 4) fait s'arrêter le maître et tous les autres workers. Il vaut pour les
workers de prod parce que (a) l'étape 3 vérifie que le venv de prod est conforme au `poetry.lock`
de HEAD, et (b) l'étape 5 vérifie que ce `poetry.lock` est celui de la cible. Le chemin du venv
est le même dans l'image et dans la prod (Poetry le dérive du dossier, `/DjangoFiles`).

### 3. Grosse mise à jour (de temps en temps, coupure planifiée)

Pour les dépendances, le `dockerfile`, la conf supervisor ou nginx, le compose, et le système.
Release faite avant (avec `REFAIRE_LA_BASE=1` pour mettre aussi le système de l'image à jour).
1. `apt update && apt upgrade` sur l'hôte.
2. `git status --porcelain --untracked-files=no` vide (aucune modification locale), puis
   `git merge --ff-only`, `docker pull tibillet/lespass:latest` (vérifier son label de commit).
3. **S'il y a des migrations, les passer AVANT de recréer le conteneur**, depuis la nouvelle image
   (l'ancien code sert encore) :
   `docker compose -f docker-compose.prod.yml run --rm --no-deps --name lespass_maj lespass_maj bash -c 'cd /DjangoFiles && poetry run python manage.py migrate_schemas --executor=multiprocessing'`
   (dans byobu : ce `run` attaché transmet un Ctrl-C à la migration).
4. `docker compose -f docker-compose.prod.yml up -d --no-deps lespass_django` (et `lespass_nginx`
   si sa conf a changé) — coupure d'environ 1 min, le temps de `start.sh`. Page de maintenance
   si besoin (conf 2 de nginx).
5. `docker exec lespass_nginx nginx -s reload` : nginx résout `lespass_django` au chargement de
   sa conf (pas de `resolver`) ; un conteneur recréé peut changer d'IP → 502 jusqu'au reload.
6. `MIGRER=0 make update` : remplace les workers (inutile mais sans effet) et pose les deux marqueurs.
7. Reboot si le noyau a changé.

Au premier passage : supprimer l'ancienne image construite sur place (`docker image ls`, image
`lespass-lespass_django`, `docker rmi`).

### Revenir en arrière

Geste à la main, hors `make update` (qui suit toujours `@{u}`). Le code servi vient du git ;
l'image n'apporte que le venv et le système.
1. Ramener le git au commit de la version (`git reset --keep <commit>`).
2. Si les dépendances diffèrent : `docker pull tibillet/lespass:<VERSION>`,
   `docker tag tibillet/lespass:<VERSION> tibillet/lespass:latest`, puis
   `docker compose -f docker-compose.prod.yml up -d --no-deps lespass_django` (coupure courte),
   puis `docker exec lespass_nginx nginx -s reload`.
   Sinon : `supervisorctl restart gunicorn daphne celery` (coupure de quelques secondes).
3. Une migration déjà appliquée ne se défait pas toute seule : `migrate_schemas <app> <migration>`,
   à décider au cas par cas.

## Les changements de fichiers

| Fichier | Changement |
|---|---|
| `dockerfile` | `POETRY_VERSION=2.4.3` (le lock est en `lock-version 2.1`, Poetry ≥ 2 obligatoire). Dépendances AVANT le code : `COPY pyproject.toml poetry.lock`, `poetry install`, puis `COPY ./`. Création de `/DjangoFiles/logs` avec `chown tibillet` AVANT `USER tibillet` : `logs/` est exclu de l'image, or `LOGGING` ouvre ses fichiers dans `BASE_DIR/logs/` dès `django.setup()` |
| `docker-compose.prod.yml` | `lespass_django` : `image: tibillet/lespass:latest` au lieu de `build: .`. Nouveau service `lespass_maj` : même image, `container_name: lespass_maj` (ignoré par `run`, d'où `--name` dans le script), profil `maj`, `.env`, réseau `backend`, liens postgres/redis/memcached (`DATABASES` vise l'hôte `postgres`), **aucun volume** |
| `env_prod_example`, `scripts/fabriquer_env_prod.sh` | `make env` : préparer un serveur |
| `docker_push_update.sh` | Release (geste 1), `REFAIRE_LA_BASE=1` pour une grosse mise à jour |
| `scripts/mise_a_jour_prod.sh` | `make update` (geste 2). La copie `logs/code_cible` disparaît |
| `Makefile` | Cibles `env`, `update` et `update_nuit` (tire l'image tout de suite, puis programme `make update` à 02:05 avec `at`, en transmettant `MIGRER` et `EXECUTEUR`) |
| `CHANGELOG/2026-10-18-make-update-sans-coupure.md` | Mis à jour |

Le premier passage à ce fonctionnement est lui-même une grosse mise à jour (compose et dockerfile changent).

Un `docker compose run` sur un service profilé marche sans `--profile`, et `up -d` l'ignore
(doc Compose « profiles »). Il doit être lancé depuis le dossier du compose de prod (même nom de
projet), sinon les `links` ne trouvent pas les conteneurs en place.

## Règles d'écriture qui en découlent

- **Une migration n'écrit jamais de fichier.** `lespass_maj` n'a pas `www/media` (exclu de l'image).
  Si un jour c'est nécessaire : monter `./www/media` seul, jamais le code.
- **Une migration reste compatible avec l'ancien code** (expand/contract, à écrire dans `GUIDELINES.md`).

## Ce qui reste, en connaissance de cause

- **Une à deux minutes de mélange** entre le `merge` (étape 9) et la fin de l'étape 10 : les
  anciens workers lisent les nouveaux gabarits sur le disque (`settings.py` déclare ses `loaders`
  sans `cached.Loader`), et un module importé pour la première fois charge le nouveau code.
  Ajouter `cached.Loader` réduirait le risque et accélérerait chaque rendu ; chantier séparé.
- **L'ancien code tourne sur le nouveau schéma** pendant toute la migration : règle expand/contract.
- **Après un `make update`, la `latest` locale n'est plus l'image du conteneur de prod.** Tout
  `docker compose up -d` qui touche `lespass_django` sans `--no-deps` (ex. `up -d lespass_nginx`)
  le recrée : environ 1 min de coupure. Toujours `--no-deps`.
- **`update_nuit` et personne pour relancer** : un arrêt avant le `merge` laisse le site
  intact ; un arrêt pendant ou après le remplacement des workers se lit le lendemain dans
  `logs/mise_a_jour_*.log`. Avant le premier usage sur la prod : `git remote -v` (un remote SSH
  qui dépend de ssh-agent échoue la nuit ; le dépôt est public, HTTPS suffit),
  `echo 'docker ps' | at now + 1 minute`, `docker compose version` (≥ 2).
- **Daphne** : 2 à 4 s de connexion refusée sur `/ws/` au restart. Accepté.
- **Celery** : `supervisor/conf.d/celery.conf` n'a pas de `stopwaitsecs` (10 s, puis la tâche est
  tuée). À régler lors d'une grosse mise à jour.
- **Un `make update` en cours tourne avec l'ancienne version du script** (bash garde le fichier
  ouvert ; git le remplace par un nouveau). Sans danger ; une nouvelle version sert à la fois suivante.

## Plus tard

- Contrôle de la mémoire disponible avant la migration et avant le remplacement des workers
  (à mesurer lors des premiers passages).

Crons de l'hôte : :00 et :30 (confirmé par le mainteneur le 2026-10-18).
