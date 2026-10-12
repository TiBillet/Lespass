# Déploiement — une commande de mise à jour, sans coupure même avec une migration

> **Statut** : idée, spec à écrire. Demande du mainteneur (2026-10-12), au premier déploiement
> après la nuit de bascule du chantier 05 (`git pull` du skin V2 par défaut et de l'accueil V2).
> Pré-requis : chantier 05 en production (fait le 2026-10-12).

## Le problème
La prod n'a pas de procédure de mise à jour écrite. Le `Makefile` ne contient que des cibles de
test (`test`, `e2e`, `e2e-visible`, `coverage`). Le 2026-10-12, le premier déploiement s'est fait à
la main : `git restore` du compose modifié sur le serveur, `git pull`, `migrate_schemas`,
`collectstatic`, `supervisorctl restart` (le site coupé quelques secondes).

`docker_push_update.sh` ne sert plus à la prod : il construit et pousse l'image
`tibillet/lespass` sur Docker Hub, utile quand le code était DANS l'image. Depuis la bascule, le
dépôt est **monté** (`docker-compose.prod.yml` : `./:/DjangoFiles`) et l'image est construite sur
place (`build: .`) : un `git pull` change le code.

## Ce qui change, et le geste qui va avec (constaté le 2026-10-12)
| Ce qui change | Geste |
|---|---|
| Code seul | `git pull`, `collectstatic`, recharger |
| + migrations | `migrate_schemas` entre le pull et le rechargement |
| + dépendances (`pyproject.toml`, `poetry.lock`) | `docker restart lespass_django` (`start.sh` refait `poetry install` et `collectstatic`, ~1 min de coupure) |
| + `dockerfile` | `docker compose build lespass_django && docker compose up -d lespass_django` |

**Piège vécu le 2026-10-12 : modifier le `.env` recrée toute la chaîne.** `lespass_postgres` et
`lespass_django` lisent le `.env` (`env_file`) : une variable ajoutée change leur configuration aux
yeux de compose. `docker compose up -d lespass_nginx` a alors recréé postgres, puis django (dont
nginx dépend par `links`), puis nginx : **~1 min 30 de 502 sur tout le site** (le temps de
`start.sh`). Pour un seul service : **toujours `docker compose up -d --no-deps <service>`**.
Une variable du `.env` lue par Django ne s'applique qu'au prochain redémarrage voulu de
`lespass_django`.

## Idée 1 — `make deploy` (simple)
Enchaîne : dépôt du serveur sans modification locale (sinon STOP) → `git pull` → liste des
migrations en attente → `collectstatic` → `migrate_schemas` s'il y en a → rechargement.
Plus `make maintenance-on` / `make maintenance-off` (conf 2 de nginx dans le compose, recréer
`lespass_nginx`).

**Rechargement sans coupure du code** :
- Gunicorn ne précharge pas l'application (`gunicorn_conf.py`, pas de `--preload`) : un signal
  `HUP` (`supervisorctl signal HUP gunicorn`) démarre de nouveaux workers sur le nouveau code,
  les anciens finissent leurs requêtes. Aucune requête perdue.
- Daphne : un redémarrage coupe les WebSockets quelques secondes ; les caisses se reconnectent
  (extension WebSocket de HTMX). **À vérifier** sur une caisse.
- Celery : laisser finir les tâches en cours. `stopwaitsecs` n'est pas réglé dans
  `supervisor/conf.d/celery.conf` (10 s par défaut, puis la tâche est tuée).

## Idée 2 — zéro coupure avec une migration : une règle d'écriture, pas un outil
Avec ~520 lieux, `migrate_schemas` dure de quelques minutes à plusieurs heures (3 h 55 la nuit
de bascule). Pendant ce temps, certains lieux sont migrés, d'autres non, et c'est **l'ancien code**
qui les sert tous. Donc :
- **une migration doit rester compatible avec le code d'avant** (« expand / contract ») : ajouter
  une colonne qui accepte NULL ou qui a une valeur par défaut, oui ; supprimer ou renommer une
  colonne, en DEUX mises à jour (le code cesse de la lire, puis on la retire) ;
- ordre : migrer pendant que l'ancien code tourne, PUIS recharger Gunicorn ;
- `make deploy` signale les migrations qui suppriment ou renomment (lecture de `sqlmigrate`) ;
- migration incompatible (rare) : page de maintenance.
À écrire dans `GUIDELINES.md`.

**Multiprocessing ou un lieu après l'autre** : `--executor=multiprocessing` s'est bloqué deux fois
sur un interblocage PostgreSQL (copie du 2026-10-06 : deux lieux ajoutant des clés étrangères vers
`AuthBillet_tibilletuser` et `QrcodeCashless_cartecashless` dans l'ordre inverse). Les 4096 verrous
(`max_locks_per_transaction`) n'y changent rien : ils évitent « out of shared memory », pas un
interblocage. Règle : multiprocessing si aucune migration n'ajoute de clé étrangère vers une table
publique (`sqlmigrate` le dit) ; sinon un lieu après l'autre. `make deploy` peut le décider.

**Ne pas lancer `migrate_schemas` pour rien** : le 2026-10-12, `pages/0002` (aucune instruction
SQL, `sqlmigrate` = no-op) a pris **14 min 41** sur 518 lieux, même en multiprocessing (graphe des
migrations et connexion ouverts pour chaque lieu). `make deploy` ne le lance que si une migration
est en attente.

## Écarté pour l'instant : la rotation à deux piles (bleu / vert)
- Le code est monté depuis UN dossier : deux versions côte à côte demanderaient le code dans
  l'image (retour à `docker_push_update.sh`) ou deux clones.
- `lespass_django` occupe ~1,8 Go sur 3,8 Go de mémoire (mesure du 2026-10-12) : deux piles ne
  tiennent pas sur ce serveur.
- La règle « expand / contract » resterait obligatoire de toute façon.

## Points à trancher dans la spec
1. `make deploy` ou un script `scripts/deployer.sh` appelé par le Makefile ?
2. Le compose modifié à la main sur le serveur : interdit (tout passe par le dépôt) ?
3. Valeur de `stopwaitsecs` pour Celery (durée de la plus longue tâche : clôtures, mails).
4. Que fait `make deploy` d'une migration incompatible : refus, ou maintenance automatique ?
