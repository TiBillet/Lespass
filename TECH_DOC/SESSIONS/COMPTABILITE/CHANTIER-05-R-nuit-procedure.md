# Chantier 05-R-4 — La nuit de la bascule, pas à pas

> **Statut** : ✅ **RÉPÉTÉE** sur la copie (2026-10-08/09, dernière section), relue par Fable (constats
> intégrés). Prête pour la nuit.
> Source : fiche R §12 (l'ordre et les contrôles), décisions du SUIVI §5 ; contrôles SQL :
> `scripts/nuit_de_bascule/` ; compose : `docker-compose.prod.yml`.
> **Le mainteneur est aux commandes toute la nuit** (migration de serveur et DNS compris) et
> décide seul d'un retour arrière.

Sur le serveur de prod, dans le dossier Lespass. Notation :
- `DJ` = `docker exec -i lespass_django poetry run python /DjangoFiles/manage.py`
- `SQL <fichier>` = `docker exec -i lespass_postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1' < scripts/nuit_de_bascule/<fichier>`
  (scripts en **lecture seule**, nombres seulement)
- `<dossier>` = un dossier **hors du dépôt**, gardé avec la sauvegarde (ex. `~/bascule_AAAA-MM-JJ/`)
- chaque commande longue : `time …` et sortie copiée dans `<dossier>`.

Le mainteneur lance tout. Claude n'a pas accès à la prod : il lit les sorties collées et dit
si les nombres sont bons et quelle commande vient ensuite (comme pendant la répétition).

## Avant la nuit (même serveur, décision du mainteneur 2026-10-11)

La bascule se fait **sur le serveur actuel** (`51.77.151.34`) : pas de migration de serveur
cette nuit-là, la base reste dans `./database`, aucun transfert ni restauration.

- [ ] Branche commitée, suite complète verte, procédure répétée sur la copie (fait le 2026-10-09).
- [ ] **Avant de toucher au système : dump de sécurité copié HORS du serveur** (voir l'étape 2
      pour la commande ; vérifier le code de sortie, la taille, `pg_restore -l`, et le `sha256sum`
      des deux côtés de la copie), plus une copie de `./www/media`.
- [ ] **Ubuntu** monté de version (22.04 → 24.04) par le mainteneur ; après : tous les conteneurs
      relancés (`docker ps`), `verifier_traefik.sh 51.77.151.34` vert.
- [ ] **Traefik v3** (`~/Gits/TraefikV3/wildcard_conf`, README l.70-79) :
  `mkdir letsencrypt traefik_logs` ; `traefik_dynamic.yml` copié **dans `wildcard_conf/`**
  (il porte le middleware `crowdsec@file` appliqué à TOUT le HTTPS : absent, Docker crée un
  dossier à sa place et plus aucun site ne répond) ; clé LAPI de crowdsec renseignée ;
  `.env` de Traefik avec les clés OVH (`tibillet.re`) et le jeton Gandi (`tibillet.coop`).
- [ ] **Syntaxe des règles** : Traefik v3 n'accepte plus les règles v2 du compose actuel
  (`HostRegexp({sub:…})`). Soit Traefik v3 démarre la nuit même, avec le compose de la
  branche ; soit, avant, ajouter `traefik.http.routers.<nom>.ruleSyntax=v2` à chaque routeur
  du compose actuel. (Fedow tourne sur un autre serveur, `141.94.27.163` : son Traefik n'est pas concerné.)
- [ ] **`scripts/nuit_de_bascule/verifier_traefik.sh 51.77.151.34`** : « TOUT EST BON »
  (DNS, certificats valides et non expirants, wildcards `*.tibillet.re` / `*.tibillet.coop`,
  redirection 80 → 443, réponse HTTPS ; 9 domaines). Référence sous Traefik v2 le 2026-10-11 :
  tout bon. À relancer après le passage en v3, puis à l'étape 11.
- [ ] **crowdsec** filtre tout Lespass : vérifier que ses scénarios ne bannissent pas l'IP
  d'un festival (dizaines de caisses derrière une seule IP) ; liste blanche si besoin.
- [ ] **Le code arrive par un clone À PART** (décision du mainteneur 2026-10-11 : `~/Lespass` n'est
  aujourd'hui qu'un dossier — compose, `.env`, `nginx/`, `database/`, `www/`, `logs/`,
  `backup/`, `ssh/` — ; on clone désormais le dépôt). On ne clone PAS dans `~/Lespass` avant la
  nuit : le dépôt écraserait `docker-compose.yml` (il deviendrait celui du DEV, mêmes noms de
  conteneurs) et `nginx/`, que le nginx actuel monte (il ne redémarrerait plus). La veille :
  ```
  git clone https://github.com/TiBillet/Lespass.git ~/Lespass-nouveau     # branche main
  cp ~/Lespass/.env ~/Lespass-nouveau/.env
  ```
  puis dans `~/Lespass-nouveau/.env` : les corrections ci-dessous, plus
  `COMPOSE_FILE=docker-compose.prod.yml` et `COMPOSE_PROJECT_NAME=lespass` (même nom de projet
  que la prod : après l'échange des dossiers, l'image construite la veille est retrouvée).
  Contrôle : `git -C ~/Lespass-nouveau log -1` = le commit voulu ; `~/Lespass` n'a pas changé.
- [ ] **`.env` de `~/Lespass-nouveau`** (relu le 2026-10-11 contre le `.env` de prod) : **ajouter**
  `DOMAIN_REGEX='^.+\.tibillet\.re$$'`, `DOMAIN_GANDI='tibillet.coop'`,
  `DOMAIN_GANDI_REGEX='^.+\.tibillet\.coop$$'` (sans eux, règles Traefik vides : tous les lieux
  en 404 ; le `$$` est obligatoire) ; **garder une seule ligne** `STRIPE_TEST=0` (elle apparaît
  deux fois) ; conseillé : `DEFAULT_FROM_EMAIL` en clair (sinon repli sur `EMAIL_HOST_USER`,
  comme aujourd'hui) ; **ne jamais régénérer** `FERNET_KEY` (champs chiffrés en base) ni
  `DJANGO_SECRET` (sessions). Contrôle : `cd ~/Lespass-nouveau && docker compose config | grep -E 'routers\.lespass-(ovh|gandi)\.rule'` : aucun `Host(``)` vide.
- [ ] **Compose de `~/Lespass-nouveau`** : `lespass_nginx` sur la **conf 2 (maintenance)** pour la
  nuit (commenter la ligne 1, décommenter les deux lignes de la conf 2) ; `lespass_django` en
  `sleep infinity` (déjà le cas). Il reprend les chemins de la prod (`./database`,
  `./backup:/Backup`, `./ssh:/home/tibillet/.ssh`, `./www`, `./logs`).
- [ ] **Construire l'image la veille**, dans `~/Lespass-nouveau` : `docker compose build`
  (apt + `poetry install` ; 10 à 20 min, beaucoup de mémoire). **Seulement `build`, jamais `up`
  la veille** : même nom de projet que la prod, un `up` remplacerait ses conteneurs. Contrôle :
  `docker images | grep lespass-lespass_django` ; l'ancienne prod tourne toujours. La nuit : `up -d`
  **sans** `--build`.
- [ ] **Copie de secours de la prod actuelle** : `mkdir -p <dossier> && cp ~/Lespass/docker-compose.yml
  ~/Lespass/.env <dossier>/ && cp -r ~/Lespass/nginx <dossier>/nginx` ; `docker images | grep
  tibillet/lespass` (l'image `latest` reste présente pour le retour arrière).
- [ ] `start.sh` : avec `MIGRATE=1`, il migre en `--executor=multiprocessing`
  (interblocage) : laisser `MIGRATE=0` (fichier `VERSION`).
- [ ] **Traefik v3 en place des jours avant la nuit, pas la nuit même** (les deux relectures) :
      lire la vraie conf v2 (`docker inspect traefik`, son `acme.json`) ; copier l'`acme.json` v2
      dans `wildcard_conf/letsencrypt/` (sinon 2 wildcards + 5 certificats réémis, limite Let's
      Encrypt de 5 doublons par semaine) ; adapter les routeurs du compose actuel
      (`traefik.enable=true`, règles v3 ou `ruleSyntax=v2`, résolveurs `le-ovh` / `le-gandi` /
      `myresolver`) ;
      `verifier_traefik.sh 51.77.151.34` vert sous v3 (Fedow, sur son propre serveur, y est vérifié sans contrôle d'IP).
- [ ] **Sauvegarde automatique** : `crontab -l` sur l'hôte (qui lance `cron/saveDb.sh` ?) ;
      **suspendre ce cron pour la nuit** (un `pg_dumpall` pendant les migrations les bloque).
- [ ] **`tmux`** sur le serveur pour toute la nuit (une coupure SSH tuerait les migrations).
- [ ] `df -h` : de quoi copier `./database` (étape 2).
- [ ] `controle_avant.sql` joué la veille (il ne dépend pas du code) : un STOP se découvre avant la nuit.

## La nuit

| # | Étape | Commande | Contrôle | Durée (répétition) |
|---|---|---|---|---|
| 0 | **Avant de couper** : capture de la fiche de l'asset CLAF et de ses remises en banque (elle a besoin du site) | navigateur | — | — |
| 1 | **Maintenance** : l'ANCIEN nginx sert la page « peau neuve » ; puis couper l'application **et Celery** (conteneur `lespass_celery` séparé), en laissant finir les tâches en cours | dans `~/Lespass` (ancien dossier) : `mv nginx nginx_prod_actuel && mkdir nginx && cp ~/Lespass-nouveau/nginx_prod/lespass_maintenance.conf nginx/` ; ajouter `- ../Lespass-nouveau/nginx_prod/maintenance:/maintenance:ro` aux volumes de `lespass_nginx` dans `docker-compose.yml` ; `docker compose up -d lespass_nginx` ; puis `docker stop -t 120 lespass_celery lespass_django` | la page de maintenance (503) sur un domaine de lieu et un domaine personnalisé ; `docker ps` : ni `lespass_django` ni `lespass_celery` | 2 min |
| 2 | **Sauvegarde à froid** (le retour arrière devient un échange de dossiers, instantané) ; le cron de sauvegarde est suspendu | `docker stop lespass_postgres` ; `sudo cp -a ~/Lespass/database ~/Lespass/database_avant_bascule` ; `docker start lespass_postgres` | `sudo du -s database database_avant_bascule` : même taille ; Postgres redémarre (`docker logs lespass_postgres \| tail`) | **à mesurer** (taille de la base) |
| 3 | **Échanger les dossiers et démarrer la branche** (`lespass_django` en `sleep infinity`, nginx sur la conf 2 maintenance). Une minute sans page de maintenance entre `down` et `up` | `cd ~/Lespass && docker compose down` (retire aussi `lespass_celery`) ; `sudo mv ~/Lespass/database ~/Lespass/www ~/Lespass/logs ~/Lespass/backup ~/Lespass/ssh ~/Lespass-nouveau/` (`database_avant_bascule` reste dans l'ancien dossier) ; `mv ~/Lespass ~/Lespass-ancien && mv ~/Lespass-nouveau ~/Lespass` ; `cd ~/Lespass && docker compose up -d --remove-orphans` (image de la veille, `COMPOSE_FILE` déjà dans le `.env`) | `docker ps -a` : plus de `lespass_celery` ; `docker exec lespass_django ps aux \| grep -cE "celery\|gunicorn"` = 0 ; `docker exec lespass_postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SHOW max_locks_per_transaction;"'` = 4096 ; `ls ~/Lespass/database \| head` non vide ; page de maintenance servie | ~5 min |
| 4 | Contrôles d'avant | `SQL controle_avant.sql` | drapeaux V2 : 0 ; comptes hors plan : 0 ; **noter** le nombre d'anciennes clôtures. Sinon **STOP** | < 1 min |
| 5 | **Export des anciennes clôtures** (base NON migrée) | `time DJ anciennes_clotures --exporter /tmp/anciennes_clotures` puis `docker cp lespass_django:/tmp/anciennes_clotures <dossier>/` | « Clôtures exportées » = le nombre de l'étape 4 | 14 s |
| 6 | **Migrations, un lieu après l'autre** (jamais `--executor=multiprocessing`) | `time DJ migrate_schemas 2>&1 \| tee <dossier>/migrations.log` | `grep -c "moteur v2 (module V2 actif)" <dossier>/migrations.log` = 0 ; `SQL controle_apres_migration.sql` : `legacy` partout sauf `W` en `v2`, 0 vente, 0 règlement, 0 lieu sans clé | **3 h 14** (513 lieux, R-0) |
| 7 | Suppression des anciennes clôtures | `DJ anciennes_clotures --supprimer --export /tmp/anciennes_clotures` (à blanc), puis la même avec `--executer` | 0 lieu refusé ; « Clôtures supprimées » = étape 4 | 13 s |
| 8 | Reprise à blanc | `time DJ reprendre_les_ventes_existantes > <dossier>/reprise_blanc.txt 2>&1` | bloc « Total » : aucune anomalie autre que « monnaie de recharge introuvable » (1 004, à 0 €) ; ancien = nouveau hors parts QR ; 125 virements reçus | 40 s |
| 9 | **Écriture de la reprise** | `time DJ reprendre_les_ventes_existantes --executer > <dossier>/reprise_ecriture.txt 2>&1` | 0 lieu refusé ; « Chaîne des ventes valide : oui » ; `SQL controle_apres_reprise.sql` : 0 ligne sans vente, 0 avoir sans vente liée, 0 vente hors reprise, 0 paiement `T` sans vente, 0 clôture | 11 min 25 |
| 10 | **J « reprise »** ; juste avant : **revérifier qu'aucun Celery ne tourne** | `docker exec lespass_django ps aux \| grep -c celery` ; `time DJ creer_la_cloture_de_reprise > <dossier>/j_reprise.txt 2>&1` ; `DJ verify_clotures \| tail -1` ; `SQL controle_apres_reprise.sql` | 0 refus ; « Audit complet : aucune anomalie » ; une J reprise par lieu avec des ventes réglées (102 sur la copie) | 2 min 33 + 2 min 12 |
| 10 bis | **Avant de rouvrir** : file Redis et planning de Celery beat | `docker exec lespass_redis redis-cli LLEN celery` et `docker exec lespass_redis redis-cli HLEN unacked` ; `rm -f ~/Lespass/celerybeat-schedule*` | les deux à 0 ; sinon : regarder ce qui est en file (mails de billets légitimes ? tâches périmées ?) et **décider** de garder ou de vider (`FLUSHALL`) avant de relancer Celery | 1 min |
| 11 | **Réouverture** : compose `lespass_django` en `command: "bash start.sh"` (`MIGRATE=0`) et `lespass_nginx` sur la conf 1 | `docker compose -f docker-compose.prod.yml up -d lespass_django lespass_nginx` ; `docker logs lespass_django \| grep -E "Skip migrate\|Supervisord"` ; `bash scripts/nuit_de_bascule/verifier_traefik.sh 51.77.151.34` | « Skip migrate » ; `verifier_traefik.sh` : TOUT EST BON (HTTPS 200 partout) ; une vente de test ; ventes historiques visibles dans l'admin ; `docker exec lespass_django poetry run supervisorctl -c /DjangoFiles/supervisor/supervisord.conf status` : 3 RUNNING ; `free -m` : pas de swap qui grimpe ; `docker exec lespass_django bash /DjangoFiles/cron/saveDb.sh` à la main, puis cron de sauvegarde réactivé | 10 min |
| 12 | Après : capture CLAF refaite ; surveiller la première heure (rattrapage des clôtures H / M / A, 12 par lieu et par heure, sans mail) | navigateur ; `docker logs -f lespass_django` | mêmes chiffres qu'à l'étape 0 ; pas d'erreur en boucle | — |

**Durée** : ~3 h 35 + la sauvegarde.

## Si une étape plante

| Étape | Que faire |
|---|---|
| 1 à 5 (avant les migrations) | Rien n'a changé dans les données. Corriger et reprendre, ou abandonner : avant l'étape 3, remettre `nginx_prod_actuel` à la place de `nginx` dans `~/Lespass` et `docker compose up -d` (ancien compose) ; après l'étape 3, suivre le « retour arrière complet » ci-dessous (la base n'a pas changé : `database` et `database_avant_bascule` sont identiques). |
| 5, export | Le dossier n'est jamais écrasé : le vider (`docker exec lespass_django rm -rf /tmp/anciennes_clotures`), relancer. |
| 6, migrations | Relancer `DJ migrate_schemas` : il reprend où il s'est arrêté. Si un même lieu échoue deux fois : **STOP**, décider (correction ou retour arrière). |
| 7, suppression des clôtures | Relancer. Un lieu déjà vidé apparaît « refusé » (0 en base, N au résumé) : il est déjà traité. |
| 8, reprise à blanc | Une anomalie nouvelle : **STOP avant d'écrire**, on l'examine. |
| 9, écriture | **Relancer la même commande** : les ventes déjà écrites sont sautées (une transaction par vente). |
| 10, J reprise | Relancer : les lieux déjà faits sont sautés. Un lieu refusé « J ordinaire » = Celery tournait : l'arrêter, puis traiter ce lieu à la main. |
| 11, réouverture | Le site ne répond pas : lire `docker logs lespass_django`, remettre la page de maintenance le temps de corriger. Les données sont bonnes. |

**Retour arrière complet** (décision du mainteneur), possible **jusqu'à l'étape 11** :
```
cd ~/Lespass && docker compose down
sudo mv ~/Lespass/www ~/Lespass/logs ~/Lespass/backup ~/Lespass/ssh ~/Lespass-ancien/
sudo mv ~/Lespass/database ~/Lespass-ancien/database_apres_essai        # la base migrée, gardée pour comprendre
sudo mv ~/Lespass-ancien/database_avant_bascule ~/Lespass-ancien/database
mv ~/Lespass ~/Lespass-nouveau && mv ~/Lespass-ancien ~/Lespass
cd ~/Lespass && rm -rf nginx && mv nginx_prod_actuel nginx      # et retirer la ligne /maintenance du compose
docker compose up -d                                             # ancien compose : image tibillet/lespass:latest, lespass_celery
```
**Après la réouverture, un retour arrière perdrait les nouvelles ventes** : c'est le point de
non-retour. Le retour arrière prend quelques minutes (échange de dossiers, aucune restauration).

## Répétition chronométrée sur la copie (R-4)

**Dump** : `db-prod/tibillet-2026-10-06-base-seule.sql.gz` (décision du mainteneur, 2026-10-08).
**Qui lance quoi** : toute écriture sur la copie est lancée par le **mainteneur** (le
classificateur la refuse à Claude) ; Claude lance les lectures et les comptages, et note les
durées. Depuis la racine du dépôt. `MC` = `docker exec -i copie_prod_django poetry run python /DjangoFiles/manage.py`
(le code est monté en lecture seule : les fichiers produits vont dans `/tmp` du conteneur,
puis `docker cp` vers `db-prod/`, mode 600). Chaque commande est précédée de `time`.

| # | Qui | Commande | Contrôle | Durée |
|---|---|---|---|---|
| R1 | mainteneur | `bash db-prod/copie_prod.sh detruire` (confirmation tapée) puis `bash db-prod/copie_prod.sh demarrer` | « VÉRIFICATION OK » | fait (2026-10-08) |
| R2 | mainteneur | `time bash db-prod/copie_prod.sh charger db-prod/tibillet-2026-10-06-base-seule.sql.gz` | 513 lieux | **45 min 08** (513 lieux) |
| R3 | Claude | `bash db-prod/copie_prod.sh compter_avant` | 0 lieu avec un drapeau V2 | 35 s ; 0 drapeau V2 |
| R4 | mainteneur | `bash db-prod/copie_prod.sh neutraliser` | OK | 2 s |
| R5-R7 | — | ~~suppression des lieux inactifs~~ : **abandonnée** (mainteneur, 2026-10-09). Jouée une fois avant l'abandon : passage à blanc sur la base non migrée OK (147 lieux, 39 s), suppression 4 min 20, 0 échec. La copie de cette répétition a donc 366 lieux, pas 513 | — | — |
| R8 | Claude | comptages de l'étape 3 (plan comptable par défaut de `main` seul ; 0 drapeau V2) et `count(*)` SQL des anciennes clôtures par schéma | STOP si un autre plan | < 1 s ; 50 992 clôtures dans 366 lieux ; 0 compte hors plan par défaut |
| R9 | mainteneur | `time MC anciennes_clotures --exporter /tmp/anciennes_clotures` | **étape 4 sur la base NON migrée** ; total = comptage de R8 | **4,3 s** (14 s en tout) ; 50 992 exportées = comptage R8 ; **base non migrée : OK** |
| R10 | mainteneur | `time bash db-prod/copie_prod.sh migrer` | 0 « moteur v2 » ; `W` en `v2` | **2 h 20** (8 433 s, 366 lieux, ~23 s / lieu) ; 0 « moteur v2 » ; `legacy` 346, `v2` 20 (`W`) ; 0 vente, 0 règlement, 0 lieu sans clé |
| R11 | mainteneur | `time MC anciennes_clotures --supprimer --export /tmp/anciennes_clotures` puis la même avec `--executer` | 0 refus ; 0 clôture en base | **2,4 s** (13 s en tout) ; 50 992 supprimées, 0 refus |
| R12 | Claude | `time MC reprendre_les_ventes_existantes > db-prod/R4_blanc.txt` | 0 anomalie bloquante ; mêmes totaux que §14 bis | **40 s** ; mêmes totaux qu'au §14 bis (141 en attente au lieu de 157 : un jour de plus) |
| R13 | mainteneur | `time MC reprendre_les_ventes_existantes --executer > db-prod/R4_ecriture.txt 2>&1` | 0 refus ; chaîne valide ; Claude : 0 ligne sans vente, 0 avoir sans vente liée | **11 min 25** ; 22 489 ventes, chaîne valide ; 0 ligne sans vente, 0 avoir sans vente liée, 0 paiement `T` sans vente |
| R14 | mainteneur | `time MC creer_la_cloture_de_reprise > db-prod/R4_j_reprise.txt 2>&1` | 0 refus ; Claude : `verify_clotures` sans anomalie | **2 min 33** ; 102 J, 264 lieux sans vente, 0 refus ; `verify_clotures` (2 min 12) : aucune anomalie |
| R15 | Claude | `bash db-prod/copie_prod.sh compter` | 0 mail capté | 0 mail capté |

**Bilan de la répétition (2026-10-08/09)** : toutes les étapes passent, 0 anomalie, 0 mail.
Durée de la nuit, d'après les mesures : sauvegarde complète (non mesurée : à chronométrer en prod)
+ export des clôtures (15 s) + migrations de **513 lieux (3 h 14, R-0)** + suppression des
clôtures (15 s) + reprise à blanc (40 s) + écriture (11 min 30) + J reprise (2 min 30) +
`verify_clotures` (2 min 15) ≈ **3 h 35 + la sauvegarde**.

Déjà éprouvé sur la copie migrée (instantané `db-prod/copie_migree_nettoyee_2026-10-08.dump`) :
étapes 4 (export sur une base déjà migrée), 7, 8, 9, 10 (fiche R §14 bis à §14 quater).
