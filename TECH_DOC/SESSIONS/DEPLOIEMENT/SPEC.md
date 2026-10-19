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
| Lien image ↔ code | L'image porte le label `org.opencontainers.image.revision` = SHA du commit. Dans la voie avec image, `make update` tire `latest` et refuse de continuer si ce label n'est pas le commit cible | Sans ce contrôle, `latest` pourrait être plus récent ou plus ancien que le git de la prod (release oubliée, commit poussé sans release) |
| Mise à jour sans migration | **Voie courte** : ni release ni `docker pull`. Après le `merge`, le même contrôle tourne dans un processus neuf de `lespass_django` ; s'il échoue, `git reset --keep` vers l'ancien commit et arrêt, aucun worker touché. `COMPLET=1` force la voie avec image | Une à deux minutes au lieu d'une release à construire et pousser. Le contrôle reste indispensable (un worker qui ne démarre pas fait tomber gunicorn) ; dans `lespass_django`, il est même plus fidèle : c'est le venv et le code que chargeront les nouveaux workers |
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

### 1. Release (machine du mainteneur) — `make release` (`scripts/release.sh`)

1. `git fetch origin main`. L'image est **toujours celle d'`origin/main`**, quelle que soit la
   branche courante et l'état du dossier local (modifications non commitées comprises) : c'est
   exactement le commit que la prod tirera. Si HEAD n'est pas `origin/main`, le script le dit,
   pour information.
2. `VERSION` est lu dans ce commit (`git show origin/main:VERSION`), pas dans le dossier local.
3. Construit depuis le commit, dans un dossier temporaire, pour garder les DEUX barrières
   (seuls les fichiers suivis, PUIS le `.dockerignore`) :
   ```bash
   dossier=$(mktemp -d)
   git archive origin/main | tar -x -C "$dossier"
   docker build -f "$dossier/dockerfile" \
       --label org.opencontainers.image.revision=<sha complet> \
       -t tibillet/lespass:$VERSION -t tibillet/lespass:latest "$dossier"
   ```
   Pas de `git archive | docker build -` : le `.dockerignore` n'est garanti que pour un contexte
   qui est un dossier. Le label dit de quel commit vient l'image (`docker inspect`) :
   `make update` s'en sert pour vérifier qu'il tire la bonne.
4. Refuse un `$VERSION` déjà publié (`docker manifest inspect`) : un tag de version sert à revenir
   en arrière, il ne s'écrase jamais. Incrémenter `VERSION` sur `main` à chaque release.
5. Pousse les deux tags (connecté à Docker Hub : `docker login`).

`REFAIRE_LA_BASE=1 make release` ajoute `--pull --no-cache` : `python:3.11` retéléchargé,
système et venv reconstruits. Réservé aux grosses mises à jour : sinon chaque release repousse et
fait retélécharger tout le venv (~690 Mo).

`start.sh` ne migre jamais : une migration au démarrage empêcherait supervisord de partir,
donc le site de répondre, jusqu'à sa fin. Le fichier `VERSION` ne porte que le numéro de version.

### 2. `make update` (prod) — `scripts/mise_a_jour_prod.sh`

| # | Étape | Arrêt si… |
|---|---|---|
| 1 | `umask 022`, puis verrou `flock` sur `logs/mise_a_jour.lock`, partagé avec `cron/saveDb.sh` (voir ci-dessous) ; s'il est pris, attente de 30 min au plus. Plus de fenêtre horaire : le verrou la remplace. Puis journal `logs/mise_a_jour_*.journal` (pas `.log` : logrotate viderait chaque nuit tous les `*.log` de `logs/`) | verrou toujours pris après 30 min |
| 2 | État de départ : gunicorn, daphne, celery en RUNNING (lecture de la sortie de `status`, toujours journalisée : son code retour vaut 3 dès qu'un programme est arrêté) ; arbre propre ; venv de prod conforme au `poetry.lock` de HEAD (`poetry install --dry-run` doit annoncer `0 installs, 0 updates, 0 removals`) ; aucun conteneur `lespass_maj` qui tourne (un `lespass_maj` arrêté, reste d'un échec : on journalise ses logs puis `docker rm`) | un seul point faux |
| 3 | `git fetch`, cible = `@{u}`, ou `CIBLE=<sha>` (posée par `update_nuit`, doit être sur `@{u}`). Les commits à déployer (`git log --oneline`, `git diff --stat`) sont écrits dans le journal ; devant un terminal, confirmation `[o/N]` (5 min au plus, le verrou est tenu pendant l'attente). HEAD = cible et `logs/dernier_commit_deploye` = cible → « rien à faire ». HEAD doit être un ancêtre de la cible (`git merge-base --is-ancestor`). Fichiers à geste manuel changés entre HEAD et la cible : `poetry.lock`, `pyproject.toml`, `dockerfile`, `start.sh`, `supervisor/`, `gunicorn_conf.py`, `nginx_prod/`, `docker-compose.prod.yml` | pas d'upstream ; `CIBLE` inconnue ou hors de `@{u}` ; réponse autre que « o » ; HEAD pas ancêtre (commit local sur le serveur, ou historique réécrit : sinon le merge répondrait « déjà à jour » sans rien faire, ou échouerait après la migration) ; fichier à geste manuel → « grosse mise à jour ». Rien n'est touché |
| 4 | Migration nécessaire ? `*/migrations/*.py` changés depuis `logs/dernier_commit_migre` (absent → oui ; `MIGRER=1` / `MIGRER=0` pour forcer). La réponse choisit la voie : **oui → voie avec image** (étape 5), **non → voie courte** (étape 5 sautée, `COMPLET=1` pour la garder). Si oui : aucun `pg_dump%` dans `pg_stat_activity` (un dump lancé à la main, hors du cron) | marqueur qui n'est pas un commit connu (sans ce contrôle, le `git diff` échouerait en silence et la migration serait sautée) ; dump en cours |
| 5 | Voie avec image : `docker pull tibillet/lespass:latest` (aucun effet sur la prod ; peut prendre plusieurs minutes si la couche du venv a changé : rien n'est encore touché). Son label `org.opencontainers.image.revision` doit être le commit cible. Puis conteneur `lespass_maj`, lancé **détaché** (`docker compose run -d --no-deps --name lespass_maj`, sans `--rm`, avec `PYTHONUNBUFFERED=1`), suivi par `docker logs -f` dans le journal, code retour par `docker wait`, puis `docker rm`. Il fait : `manage.py check`, import de `TiBillet.wsgi` et `TiBillet.asgi`, peuplement des deux résolveurs d'URLs, puis `migrate_schemas` si nécessaire (`nice -n 19 ionice -c3`, `PGOPTIONS="-c lock_timeout=5s"`, `--executor=${EXECUTEUR:-multiprocessing}`). Succès de la migration, ou `MIGRER=0` → `logs/dernier_commit_migre` | label différent → « la release de ce commit n'est pas faite » ; contrôle ou migration en échec : le code servi n'a pas bougé |
| 6 | `git merge --ff-only <sha>`. Voie courte : le contrôle de l'étape 5 (sans migration) dans un processus neuf de `lespass_django` (`docker exec`, environ 15 s) ; `MIGRER=0` → `logs/dernier_commit_migre`. Puis `collectstatic` dans `lespass_django` | voie courte, contrôle en échec : `git reset --keep <ancien commit>`, le dossier servi revient tel qu'il était, aucun worker touché. `collectstatic` en échec : **pas** de retour arrière (le code est en place, les anciens workers servent) ; corriger et relancer reprend à cette étape |
| 7 | Gunicorn un par un : boucle tant qu'un PID d'ancien worker vit ; TTIN (`supervisorctl signal`) → attendre `warmup worker <pid> : ` dans `logs/gunicorn.logs` (90 s) → TTOU → attendre le départ d'un ancien (40 s). `trap` qui rend le worker en trop. PID du maître relu à chaque tour. Arrêt si aucun worker trouvé au départ | ligne d'échec du préchauffage, ou pas de ligne en 90 s (pas de TTOU de rattrapage : il retirerait un ancien worker sain ; gunicorn garde un worker en trop, le message le dit, `supervisorctl signal TTOU gunicorn` le rend après un `make update` réussi), « Worker failed to boot », « Shutting down: Master », maître changé |
| 8 | `/robots.txt` → 200, ou 301/302, cinq fois (Host = `$DOMAIN`, `X-Forwarded-Proto: https`). La redirection vient de `CanonicalDomainRedirectMiddleware` quand le domaine principal du tenant public n'est pas `$DOMAIN` (cas de la prod au 2026-10-19) : elle prouve aussi que le worker répond | 5xx, 000 (pas de réponse : l'échec de curl ne coupe pas le script, `\|\| true`, le code 000 est traité) |
| 9 | `restart daphne`, puis `restart celery` hors de :58–:04 (attente de :05 sinon : les tâches Celery beat partent toutes à :00, un restart couperait une tâche en cours au bout de `stopwaitsecs`), 15 s, tout en RUNNING. Puis `logs/dernier_commit_deploye`, et `docker image prune -f --filter label=org.opencontainers.image.revision` : l'ancienne `latest`, détaguée par le pull, part, sauf si un conteneur l'utilise encore (celui de prod) ; les images des autres piles ne sont pas touchées | un service pas en RUNNING |

**Le verrou partagé avec la sauvegarde (étape 1).** `make update` et `cron/saveDb.sh` prennent
le même `flock`, `logs/mise_a_jour.lock` (`/DjangoFiles/logs/mise_a_jour.lock` dans le conteneur,
le dossier est monté ; vérifié : le verrou passe entre l'hôte et le conteneur). La sauvegarde ne
le tient que pendant `pg_dumpall` : c'est lui qui verrouille toutes les tables, une migration
lancée en même temps échouerait sur son `lock_timeout`. Pendant un `make update`, la sauvegarde
attend ; après 25 min elle est sautée (avant le cron suivant, pour ne pas les empiler), et la
suivante passera. Le fichier est créé par `make update` ; la sauvegarde l'ouvre en lecture seule
(`flock` n'a pas besoin du droit d'écriture), et sans fichier elle part sans verrou. Fichier
présent mais illisible (créé sous un autre umask) : elle part aussi sans verrou, avec un message,
plutôt que de mourir avant `pg_dumpall` ; `make update` pose `umask 022` pour l'éviter. Il remplace
les fenêtres horaires de :05–:20 et :05–:10.

**Pourquoi détaché (étape 5).** Un `docker compose run` attaché relaie TOUS les signaux au
conteneur (`ForwardAllSignals`) : un Ctrl-C, ou la coupure d'une session SSH hors byobu,
interromprait `migrate_schemas` au milieu d'un schéma. Détaché, le conteneur ne dépend plus du
terminal : si le script meurt, la migration finit seule, et la relance de `make update` la trouve
(étape 2). Sans `--rm`, sa sortie reste lisible jusqu'au `docker rm`. `--name` est obligatoire :
`docker compose run` ignore le `container_name` du compose et invente un nom aléatoire. Le nom
fixe interdit d'ailleurs d'en lancer deux à la fois (« name already in use »).

**Pourquoi le contrôle suffit (étape 5, ou étape 6 dans la voie courte).** Dans la voie avec
image, il tourne dans l'image de la nouvelle version : il prouve que le code ET ses dépendances
démarrent. C'est indispensable : un worker gunicorn qui ne
démarre pas (code 3 ou 4) fait s'arrêter le maître et tous les autres workers. Il vaut pour les
workers de prod parce que (a) l'étape 2 vérifie que le venv de prod est conforme au `poetry.lock`
de HEAD, et (b) l'étape 3 vérifie que ce `poetry.lock` est celui de la cible. Le chemin du venv
est le même dans l'image et dans la prod (Poetry le dérive du dossier, `/DjangoFiles`). Dans la
voie courte, il tourne dans `lespass_django` après le `merge` : même venv, même code que les
futurs workers. Les workers en place ne le voient pas : ils ont l'ancien code en mémoire, et
seuls les gabarits sont relus sur le disque pendant ces quelques secondes.

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
| `scripts/release.sh` (ex `docker_push_update.sh`) | `make release` (geste 1) : image d'`origin/main`, `REFAIRE_LA_BASE=1` pour une grosse mise à jour |
| `scripts/mise_a_jour_prod.sh` | `make update` (geste 2). La copie `logs/code_cible` disparaît |
| `Makefile` | Cibles `release`, `env`, `update` et `update_nuit` (fige la cible tout de suite et affiche ses commits, tire l'image, puis programme `CIBLE=<sha> make update` à 02:05 avec `at`, en transmettant `MIGRER`, `EXECUTEUR` et `COMPLET`) |
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

- **Une à deux minutes de mélange** entre le `merge` (étape 6) et la fin de l'étape 7 : les
  anciens workers lisent les nouveaux gabarits sur le disque (`settings.py` déclare ses `loaders`
  sans `cached.Loader`), et un module importé pour la première fois charge le nouveau code.
  Ajouter `cached.Loader` réduirait le risque et accélérerait chaque rendu ; chantier séparé.
- **L'ancien code tourne sur le nouveau schéma** pendant toute la migration : règle expand/contract.
- **Voie courte : `latest` peut avoir un commit de retard** sur la prod, et le commit déployé n'a
  pas de tag de version pour y revenir (le retour en arrière se fait par le git). Sans effet sur
  le fonctionnement : les dépendances n'ont pas bougé (étape 3). La prochaine mise à jour avec
  migration demandera la release de son commit.
- **Après un `make update`, la `latest` locale n'est plus l'image du conteneur de prod.** Tout
  `docker compose up -d` qui touche `lespass_django` sans `--no-deps` (ex. `up -d lespass_nginx`)
  le recrée : environ 1 min de coupure. Toujours `--no-deps`.
- **La voie courte n'a plus la barrière de la release** : tout commit sans migration poussé sur
  `main` part au prochain `make update`. Garde-fous : les commits listés et la confirmation devant
  un terminal ; `update_nuit` fige la cible au moment où il est programmé (un commit poussé
  ensuite ne part pas à 02:05).
- **`update_nuit` et personne pour relancer** : un arrêt avant le `merge` laisse le site
  intact ; un arrêt pendant ou après le remplacement des workers se lit le lendemain dans
  `logs/mise_a_jour_*.journal`. Avant le premier usage sur la prod : `git remote -v` (un remote SSH
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

## TODO — relecture du 2026-10-19 (agent Fable), non corrigé, à trancher par le mainteneur

Corrigés le même jour : ancêtre de la cible (étape 3), marqueur de migration invalide (étape 4),
verrou illisible par la sauvegarde, curl en échec (étape 8), `collectstatic` en échec et worker
en trop (messages), tableau `status` journalisé, `--dry-run` en échec, journal en `.journal`,
numérotation unique.

- [ ] **Architecture : migrer sans image.** La voie avec image n'apporte rien que le venv de prod
  n'ait déjà (tout changement de dépendance arrête le script à l'étape 3). Option : `git worktree
  add logs/code_cible <cible>` (dans le dossier monté), puis `check` et `migrate_schemas` dans
  `lespass_django` avec `$(poetry env info -p)/bin/python` (pas `poetry run` : le venv est dérivé du
  chemin), `-w /DjangoFiles/logs/code_cible`, et `mkdir logs/code_cible/logs` pour le LOGGING
  (`BASE_DIR` est dérivé du fichier, settings.py:23 ; aucun `.env` lu par les settings). Gains :
  plus de `make release` pour une migration, un seul contrôle AVANT le merge (plus de
  `git reset --keep`), `latest` jamais en retard ; la release ne sert qu'aux grosses mises à jour.
  Perte : la migration prend la mémoire et le CPU de `lespass_django`.
- [ ] **Modèle modifié sans migration** : invisible aux contrôles (aucun fichier de migration → voie
  courte → erreurs 500). Ajouter `manage.py makemigrations --check --dry-run` au contrôle.
- [ ] **Mémoire** : voie avec image = un Django + 2 processus de migration, puis un worker gunicorn
  de plus à chaque tour, sur 3,8 Go. Un seuil `MemAvailable` avant `lespass_maj` et avant chaque
  TTIN (voir « Plus tard »).
- [ ] **Relance après un `git pull` manuel** : HEAD = cible, donc le diff des fichiers à geste
  manuel (étape 3) est vide, et le message « revenu à … » de la voie courte est faux (le
  `git reset --keep` ne fait rien). Baser ce diff sur `logs/dernier_commit_deploye` quand il existe.
- [ ] **Ménage des images** : `org.opencontainers.image.revision` est le label OCI standard (buildx,
  GitHub Actions) : les images sans tag d'autres piles qui le portent partent aussi. Sans danger,
  mais le commentaire est faux. Poser un label propre dans `release.sh` (ex.
  `coop.tibillet.release=1`) et filtrer dessus.
- [ ] **Celery et le nouveau code** : pendant l'attente de :05 (jusqu'à 7 min), l'ancien celery
  peut charger un module neuf (imports faits dans les tâches, `TiBillet/celery.py`). À ajouter à
  « Ce qui reste ».
- [ ] **Sauvegardes sautées** : le `docker pull` se fait sous le verrou ; pull + migration + attente
  de :05 peuvent dépasser 25 min et faire sauter une ou deux sauvegardes. Tirer l'image avant de
  prendre le verrou, ou l'écrire dans « Ce qui reste ».

Crons de l'hôte : :00 et :30 (confirmé par le mainteneur le 2026-10-18).
