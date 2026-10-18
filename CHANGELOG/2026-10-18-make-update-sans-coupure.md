# make update : mise à jour de la prod sans coupure / Zero-downtime production update

**Date :** 2026-10-18
**Migration :** Non (le script lance `migrate_schemas` quand une mise à jour en contient)

## Resume / Summary
**Quoi / What :** nouvelle commande `make update` (`scripts/mise_a_jour_prod.sh`) qui met la prod à
jour : `git fetch`, contrôle du nouveau code et migration depuis une copie (`logs/code_cible`),
`git merge --ff-only`, `collectstatic`, remplacement des workers gunicorn un par un (TTIN/TTOU),
redémarrage de daphne et de celery, contrôles à chaque étape.
/ New `make update` command: fetch, check and migrate from a copy of the target code, fast-forward
merge, collectstatic, one-by-one gunicorn worker replacement (TTIN/TTOU), daphne and celery restart.

**Pourquoi / Why :** `supervisorctl restart` ferme le port de gunicorn (502), et HUP arrête les
anciens workers avant que les nouveaux aient chargé Django (gel mesuré : 3,9 s en dev). Migrer
depuis une copie évite que les anciens workers rendent les nouveaux gabarits pendant les ~15 min
de `migrate_schemas` (les gabarits ne sont pas mis en cache, `settings.py` déclare ses loaders).
/ `restart` closes the port (502) and HUP freezes requests; migrating from a copy keeps old workers
from rendering new templates during the migration.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `scripts/mise_a_jour_prod.sh` | Nouveau : la procédure complète |
| `Makefile` | Cible `update` (ajoutée à `CIBLES`) |

Garde-fous : verrou `flock`, journal `logs/mise_a_jour_*.log`, départ de :05 à :20 / :35 à :50
(:05 à :10 / :35 à :40 s'il y a une migration), refus si une sauvegarde `pg_dump` tourne, arrêt
avant le merge si un fichier demande un geste à la main (dépendances, dockerfile, supervisor,
`gunicorn_conf.py`, `nginx_prod/`, compose), `lock_timeout=5s` + `nice`/`ionice` pour la migration,
marqueurs `logs/dernier_commit_migre` et `logs/dernier_commit_deploye` pour reprendre après un échec.

Suite : montée en gunicorn 26 (chantier à part), puis `gunicornc` (`show workers` / `worker kill`)
à la place de la lecture du log.

---

## Comment tester (a la main) / Manual test

### Test 0 — banc d'essai TTIN/TTOU contre HUP (dev, déjà joué le 2026-10-18)
Un gunicorn jetable sur 127.0.0.1:8099 dans `lespass_django`, 3 workers, une requête
`/robots.txt` toutes les 50 ms :
- TTIN/TTOU : 240 requêtes, 0 erreur, la plus lente 35 ms, les 3 anciens workers remplacés.
- HUP : 119 requêtes, 0 erreur, une requête bloquée 3,9 s.

### Test 1 — garde-fous en dev
1. `make update` en dev : arrêt sur « supervisord ne tourne pas » (ou sur la fenêtre horaire).
2. Rien n'a bougé : `git status` identique, pas de fetch.

### Test 2 — première mise à jour en prod
1. Sur l'hôte, dans byobu, vérifier `crontab -l` (crons à :00 et :30).
2. Premier lancement : pas de marqueur, donc migration (~15 min). Si on sait qu'il n'y a rien à
   migrer : `MIGRER=0 make update`.
3. Pendant le remplacement des workers, dans un autre panneau :
   `tail -f logs/gunicorn.logs` (une ligne « warmup worker » puis un « Worker exiting » par tour)
   et le log nginx (`urt=` doit rester normal, aucun 502).
4. Fin : « Mise a jour terminee », `logs/dernier_commit_deploye` = `git rev-parse HEAD`.
5. Relancer `make update` : « Deja a jour. Rien a faire. »

### Test 3 — reprise après échec
1. Lancer une migration à :12 : refus (« elle se lance de :05 a :10 »).
2. Couper la session SSH pendant la migration, relancer : refus (« une migration tourne deja »).
