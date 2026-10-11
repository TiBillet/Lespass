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
- [ ] **Ubuntu** monté de version (22.04 → 24.04) par le mainteneur.
- [ ] **Traefik v3** (`~/Gits/TraefikV3/wildcard_conf`, README l.70-79) :
  `mkdir letsencrypt traefik_logs` ; `traefik_dynamic.yml` copié **dans `wildcard_conf/`**
  (il porte le middleware `crowdsec@file` appliqué à TOUT le HTTPS : absent, Docker crée un
  dossier à sa place et plus aucun site ne répond) ; clé LAPI de crowdsec renseignée ;
  `.env` de Traefik avec les clés OVH (`tibillet.re`) et le jeton Gandi (`tibillet.coop`).
- [ ] **Syntaxe des règles** : Traefik v3 n'accepte plus les règles v2 du compose actuel
  (`HostRegexp({sub:…})`). Soit Traefik v3 démarre la nuit même, avec le compose de la
  branche ; soit, avant, ajouter `traefik.http.routers.<nom>.ruleSyntax=v2` à chaque routeur
  du compose actuel **et de Fedow** (même serveur, compose à part).
- [ ] **`scripts/nuit_de_bascule/verifier_traefik.sh 51.77.151.34`** : « TOUT EST BON »
  (DNS, certificats valides et non expirants, wildcards `*.tibillet.re` / `*.tibillet.coop`,
  redirection 80 → 443, réponse HTTPS ; 9 domaines). Référence sous Traefik v2 le 2026-10-11 :
  tout bon. À relancer après le passage en v3, puis à l'étape 11.
- [ ] **crowdsec** filtre tout Lespass : vérifier que ses scénarios ne bannissent pas l'IP
  d'un festival (dizaines de caisses derrière une seule IP) ; liste blanche si besoin.
- [ ] **Compose** : le dossier du serveur (`~/Lespass`) a son `docker-compose.yml` de prod
  (image `tibillet/lespass:latest`, conteneur `lespass_celery` séparé) ; la branche a un
  `docker-compose.yml` de **dev** et le compose de prod sous `docker-compose.prod.yml`. Décider
  comment le code arrive dans `~/Lespass` (git) sans écraser le compose actuel avant la nuit.
  Le compose de la branche reprend les chemins de la prod : `./database` (base),
  `./backup:/Backup` et `./ssh:/home/tibillet/.ssh` (sauvegarde `cron/saveDb.sh`), `./www`,
  `./logs`. `.env` de Lespass : `DOMAIN`, `DOMAIN_REGEX` (`^.+\.tibillet\.re$$`),
  `DOMAIN_GANDI`, `DOMAIN_GANDI_REGEX` (absents d'`env_example`).
- [ ] `start.sh` : avec `MIGRATE=1`, il migre en `--executor=multiprocessing`
  (interblocage) : laisser `MIGRATE=0` (fichier `VERSION`).
- [ ] Page de maintenance prête (`nginx_prod/lespass_maintenance.conf`, conf 2 commentée dans
  le compose, service `lespass_nginx`).
- [ ] Message aux lieux : billetterie, admin et caisses fermées pendant la nuit.

## La nuit

| # | Étape | Commande | Contrôle | Durée (répétition) |
|---|---|---|---|---|
| 0 | **Avant de couper** : capture de la fiche de l'asset CLAF et de ses remises en banque (elle a besoin du site) | navigateur | — | — |
| 1 | **Maintenance** : nginx sert la page « peau neuve » ; puis couper l'application **et Celery** (conteneur `lespass_celery` séparé sur la prod actuelle) | compose actuel : monter `nginx_prod/lespass_maintenance.conf` et `nginx_prod/maintenance` dans `lespass_nginx`, `docker compose up -d lespass_nginx` ; puis `docker compose stop lespass_django lespass_celery` | la page de maintenance (503) sur un domaine de lieu et un domaine personnalisé ; `docker ps` : ni `lespass_django` ni `lespass_celery` | 2 min |
| 2 | **Sauvegarde complète** | `docker exec lespass_postgres sh -c 'pg_dump -Fc -U "$POSTGRES_USER" "$POSTGRES_DB"' > <dossier>/avant_bascule.dump` | `docker exec -i lespass_postgres pg_restore -l < <dossier>/avant_bascule.dump \| grep -c "TABLE DATA"` > 0 | **à mesurer** |
| 3 | **Déployer la branche** avec le compose de prod de la branche (`lespass_django` en `sleep infinity`, nginx sur la conf 2 maintenance) ; l'ancien `lespass_celery` est retiré | code de la branche dans `~/Lespass` ; `docker compose -f docker-compose.prod.yml up -d --build --remove-orphans` | `docker ps -a` : plus de `lespass_celery` ; `docker exec lespass_django ps aux \| grep -cE "celery\|gunicorn"` = 0 ; `SHOW max_locks_per_transaction;` = 4096 ; page de maintenance toujours servie | ~10 min |
| 4 | Contrôles d'avant | `SQL controle_avant.sql` | drapeaux V2 : 0 ; comptes hors plan : 0 ; **noter** le nombre d'anciennes clôtures. Sinon **STOP** | < 1 min |
| 5 | **Export des anciennes clôtures** (base NON migrée) | `time DJ anciennes_clotures --exporter /tmp/anciennes_clotures` puis `docker cp lespass_django:/tmp/anciennes_clotures <dossier>/` | « Clôtures exportées » = le nombre de l'étape 4 | 14 s |
| 6 | **Migrations, un lieu après l'autre** (jamais `--executor=multiprocessing`) | `time DJ migrate_schemas 2>&1 \| tee <dossier>/migrations.log` | `grep -c "moteur v2 (module V2 actif)" <dossier>/migrations.log` = 0 ; `SQL controle_apres_migration.sql` : `legacy` partout sauf `W` en `v2`, 0 vente, 0 règlement, 0 lieu sans clé | **3 h 14** (513 lieux, R-0) |
| 7 | Suppression des anciennes clôtures | `DJ anciennes_clotures --supprimer --export /tmp/anciennes_clotures` (à blanc), puis la même avec `--executer` | 0 lieu refusé ; « Clôtures supprimées » = étape 4 | 13 s |
| 8 | Reprise à blanc | `time DJ reprendre_les_ventes_existantes > <dossier>/reprise_blanc.txt 2>&1` | bloc « Total » : aucune anomalie autre que « monnaie de recharge introuvable » (1 004, à 0 €) ; ancien = nouveau hors parts QR ; 125 virements reçus | 40 s |
| 9 | **Écriture de la reprise** | `time DJ reprendre_les_ventes_existantes --executer > <dossier>/reprise_ecriture.txt 2>&1` | 0 lieu refusé ; « Chaîne des ventes valide : oui » ; `SQL controle_apres_reprise.sql` : 0 ligne sans vente, 0 avoir sans vente liée, 0 vente hors reprise, 0 paiement `T` sans vente, 0 clôture | 11 min 25 |
| 10 | **J « reprise »** ; juste avant : **revérifier qu'aucun Celery ne tourne** | `docker exec lespass_django ps aux \| grep -c celery` ; `time DJ creer_la_cloture_de_reprise > <dossier>/j_reprise.txt 2>&1` ; `DJ verify_clotures \| tail -1` ; `SQL controle_apres_reprise.sql` | 0 refus ; « Audit complet : aucune anomalie » ; une J reprise par lieu avec des ventes réglées (102 sur la copie) | 2 min 33 + 2 min 12 |
| 11 | **Réouverture** : compose `lespass_django` en `command: "bash start.sh"` (`MIGRATE=0`) et `lespass_nginx` sur la conf 1 | `docker compose -f docker-compose.prod.yml up -d lespass_django lespass_nginx` ; `docker logs lespass_django \| grep -E "Skip migrate\|Supervisord"` ; `bash scripts/nuit_de_bascule/verifier_traefik.sh 51.77.151.34` | « Skip migrate » ; `verifier_traefik.sh` : TOUT EST BON (HTTPS 200 partout) ; une vente de test ; ventes historiques visibles dans l'admin ; Celery tourne (dans `lespass_django`) | 5 min |
| 12 | Après : capture CLAF refaite ; surveiller la première heure (rattrapage des clôtures H / M / A, 12 par lieu et par heure, sans mail) | navigateur ; `docker logs -f lespass_django` | mêmes chiffres qu'à l'étape 0 ; pas d'erreur en boucle | — |

**Durée** : ~3 h 35 + la sauvegarde.

## Si une étape plante

| Étape | Que faire |
|---|---|
| 1 à 5 (avant les migrations) | Rien n'a changé dans les données. Corriger et reprendre, ou abandonner : revenir au compose actuel (`docker compose up -d`, image `tibillet/lespass:latest`, `lespass_celery`) et la conf nginx 1, sans restaurer la base. |
| 5, export | Le dossier n'est jamais écrasé : le vider (`docker exec lespass_django rm -rf /tmp/anciennes_clotures`), relancer. |
| 6, migrations | Relancer `DJ migrate_schemas` : il reprend où il s'est arrêté. Si un même lieu échoue deux fois : **STOP**, décider (correction ou retour arrière). |
| 7, suppression des clôtures | Relancer. Un lieu déjà vidé apparaît « refusé » (0 en base, N au résumé) : il est déjà traité. |
| 8, reprise à blanc | Une anomalie nouvelle : **STOP avant d'écrire**, on l'examine. |
| 9, écriture | **Relancer la même commande** : les ventes déjà écrites sont sautées (une transaction par vente). |
| 10, J reprise | Relancer : les lieux déjà faits sont sautés. Un lieu refusé « J ordinaire » = Celery tournait : l'arrêter, puis traiter ce lieu à la main. |
| 11, réouverture | Le site ne répond pas : lire `docker logs lespass_django`, remettre la page de maintenance le temps de corriger. Les données sont bonnes. |

**Retour arrière complet** (décision du mainteneur), possible **jusqu'à l'étape 11** :
restaurer `<dossier>/avant_bascule.dump` dans une base vide (`pg_restore -j 4 --no-owner`),
puis revenir au compose actuel (image `tibillet/lespass:latest`, `lespass_celery`) et à la
conf nginx 1. **Après la réouverture, un retour arrière
perdrait les nouvelles ventes** : c'est le point de non-retour. La durée d'une restauration
n'est pas encore mesurée.

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
