# make update : mise à jour de la prod sans coupure / Zero-downtime production update

**Date :** 2026-10-18
**Migration :** Non (le script lance `migrate_schemas` quand une mise à jour en contient)

## Resume / Summary
**Quoi / What :** une image Docker par release, construite depuis le commit et poussée sur Docker
Hub (`make release`, `scripts/release.sh`) ; nouvelle commande `make update` (`scripts/mise_a_jour_prod.sh`) :
`docker pull` de l'image, contrôle du nouveau code et migration dans un conteneur jetable
`lespass_maj` pendant que l'ancien code sert, `git merge --ff-only`, `collectstatic`, workers
gunicorn remplacés un par un (TTIN/TTOU), redémarrage de daphne et de celery. Sans migration,
voie courte : ni release ni pull, le contrôle tourne dans `lespass_django` après le merge
(retour à l'ancien commit s'il échoue).
/ One Docker image per release, built from the commit; new `make update`: pull, check and migrate
in a throwaway `lespass_maj` container while the old code serves, fast-forward merge,
one-by-one gunicorn worker replacement, daphne and celery restart. Without a migration, short
path: no release, no pull, the check runs in `lespass_django` after the merge.

**Pourquoi / Why :** `supervisorctl restart` ferme le port de gunicorn (502), et HUP arrête les
anciens workers avant que les nouveaux aient chargé Django (gel mesuré : 3,9 s en dev). Migrer
depuis la nouvelle image laisse le dossier servi intact pendant les ~15 min de `migrate_schemas` :
les anciens workers ne rendent pas les nouveaux gabarits (non mis en cache).
/ `restart` closes the port (502), HUP freezes requests; migrating from the new image keeps the
served folder untouched during the migration.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `env_prod_example`, `scripts/fabriquer_env_prod.sh` | `make env` : `.env` de prod depuis un modèle (secrets générés, `A_REMPLIR`), dossiers montés, contrôles du serveur ; ne remplace jamais un `.env` existant |
| `scripts/release.sh` (ex `docker_push_update.sh`), `make release` | Release : construit toujours `origin/main` (quelle que soit la branche courante), `VERSION` lu dans ce commit, build depuis `git archive` extrait, label `org.opencontainers.image.revision`, tags `latest` + `$VERSION` |
| `start.sh`, `VERSION` | Plus de migration au démarrage du conteneur : la variable `MIGRATE` disparaît, les migrations passent par `make update` |
| `dockerfile` | Dépendances avant le code (cache de la couche venv), Poetry épinglé 2.4.3, dossier `logs/` créé |
| `docker-compose.prod.yml` | `lespass_django` en `image: tibillet/lespass:latest` ; nouveau service `lespass_maj` (profil `maj`, aucun volume) |
| `scripts/mise_a_jour_prod.sh` | Nouveau : `make update`. Pas de fenêtre horaire : verrou partagé avec la sauvegarde, et `restart celery` hors de :58–:04. Voie courte sans migration (`COMPLET=1` pour la voie avec image). Commits listés dans le journal, confirmation devant un terminal, `CIBLE=<sha>` |
| `cron/saveDb.sh` | Prend le verrou de `make update` le temps du `pg_dumpall` (attente de 25 min au plus, puis sauvegarde sautée) |
| `Makefile` | Cibles `release`, `env`, `update` et `update_nuit` (fige la cible, `CIBLE=<sha>`, puis programme `make update` à 02:05 avec `at`) |
| `README.md`, `README.en.md` | Section « Mettre a jour la production » ; `make coverage`, `make help`, `LENTEUR` ajoutés aux tests |
| `TECH_DOC/SESSIONS/DEPLOIEMENT/` | Nouveau hub : `INDEX.md`, `SPEC.md` (chantier 01) |

Le premier passage est une « grosse mise à jour » (le compose et le dockerfile changent) :
voir `SPEC.md`, geste 3.

---

## Comment tester (a la main) / Manual test

### Test 0 — banc d'essai TTIN/TTOU contre HUP (dev, déjà joué le 2026-10-18)
Un gunicorn jetable sur 127.0.0.1:8099 dans `lespass_django`, 3 workers, une requête
`/robots.txt` toutes les 50 ms :
- TTIN/TTOU : 240 requêtes, 0 erreur, la plus lente 35 ms, les 3 anciens workers remplacés.
- HUP : 119 requêtes, 0 erreur, une requête bloquée 3,9 s.

### Test 1 — garde-fous en dev
1. `make update` en dev : arrêt sur « supervisord ne tourne pas ».
2. Rien n'a bougé : `git status` identique, pas de fetch.

### Test 2 — première release et grosse mise à jour
1. Machine du mainteneur, `main` poussé, `VERSION` incrémenté sur `main` : `make release`.
2. `docker image inspect -f '{{ index .Config.Labels "org.opencontainers.image.revision" }}' tibillet/lespass:latest`
   = `git rev-parse origin/main`.
3. Prod : geste 3 de `SPEC.md` (merge, pull, `up -d --no-deps lespass_django`), puis
   `MIGRER=0 make update` (ou `MIGRER=1` s'il y a des migrations) pour poser les marqueurs.

### Test 3 — mise à jour de code ordinaire
1. Un commit sans dépendance ni dockerfile, poussé sur `main`, puis `make release`.
2. Prod, dans byobu : `make update` ; les commits s'affichent, répondre « o ».
3. Dans un autre panneau : `tail -f logs/gunicorn.logs` (une ligne « warmup worker » puis le départ
   d'un ancien worker, par tour) et le log nginx (`urt=` normal, aucun 502).
4. Fin : « Mise a jour terminee », `logs/dernier_commit_deploye` = `git rev-parse HEAD`.
5. Relancer `make update` : « Deja a jour. Rien a faire. »

### Test 3 bis — voie courte (sans migration)
1. Un commit sans migration (ex. un gabarit), poussé sur `main`, **sans** `make release`.
2. Prod : `make update` → « Migration : non », « Voie : courte », pas de `docker pull`, puis
   « Controle dans lespass_django », workers remplacés, « Mise a jour terminee ».
3. Déjà joué en dev le 2026-10-19 : le contrôle dans `lespass_django` (`docker exec`, 13 s, OK),
   et `git reset --keep` après un `merge --ff-only` dans un dépôt jetable (fichiers modifiés et
   ajoutés revenus, fichiers non suivis gardés).

### Test 4 — refus
1. Commit avec migration poussé sans release : arrêt « lancer make release », rien de modifié.
2. Verrou : dans un autre panneau, `flock logs/mise_a_jour.lock sleep 120`, puis `make update` : « Verrou pris… Attente », il part à la fin du `sleep`. Et l'inverse : pendant un `make update`, `docker exec lespass_django /DjangoFiles/cron/saveDb.sh` attend sa fin.
3. Couper la session SSH pendant la migration, relancer : arrêt « lespass_maj tourne encore ».
4. Un commit qui modifie `poetry.lock` : arrêt « grosse mise a jour ».
