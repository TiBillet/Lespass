# Chantier 05-R-4 — La nuit de la bascule, pas à pas

> **Statut** : ✅ **RÉPÉTÉE** sur la copie (2026-10-08/09, dernière section), relue par Fable (constats
> intégrés). Prête pour la nuit.
> Source : fiche R §12 (l'ordre et les contrôles), §18 (lieux inactifs), décisions du SUIVI §5.
> **Le mainteneur est aux commandes toute la nuit** (migration de serveur et DNS compris) et
> décide seul d'un retour arrière.

Notation : `DJ` = `docker exec -i <conteneur Django de la prod> poetry run python /DjangoFiles/manage.py`.
`<sauvegardes>` = un dossier **hors du dépôt**, sur le serveur, gardé avec la sauvegarde complète.

## Avant la nuit

- [ ] Branche prête : fiche R commitée, suite complète verte, E2E verts.
- [ ] Copie de la production la plus récente : répétition complète de cette procédure,
      chronométrée (dernière section). **Prérequis bloquant** : l'étape 4
      (`anciennes_clotures --exporter`) y tourne avec le code de la branche sur la base de
      `main` **non migrée**, comme la nuit.
- [ ] Message aux lieux : fermeture de la billetterie, de l'admin et des caisses pendant la nuit.

## La nuit

| # | Étape | Commande | Contrôle | Durée mesurée (copie) |
|---|---|---|---|---|
| 1 | Tout couper : site, admin, API ; **worker ET beat Celery arrêtés** jusqu'à l'étape 11 | (pile de prod) | plus aucune requête dans les journaux | — |
| 2 | Postgres avec `max_locks_per_transaction` ≥ 512 (copie : 4 096 pour le chargement) | compose de prod | `SHOW max_locks_per_transaction;` | — |
| 1 bis | Image de la branche déployée, `MIGRATE=0`, site toujours coupé | (mainteneur) | aucune ligne `migrate_schemas` dans le journal ; **aucun processus Celery** (le déploiement relance souvent `lespass_celery`, beat compris : `docker ps` + `ps aux | grep celery` dans les conteneurs) | — |
| 2 bis | **Sauvegarde complète**. (Plus de suppression des lieux inactifs : abandonnée par le mainteneur le 2026-10-09, tri au cas par cas plus tard, TODO `ADMIN-suppression-tenant-superadmin.md`. Les 2 schémas sans lieu restent : `migrate_schemas` ne migre que les lieux.) | `pg_dump -Fc …` | fichier lisible par `pg_restore -l` | à mesurer |
| 3 | Plan comptable par défaut de `main` seul présent ; **0 lieu de production avec un drapeau V2** | comptages SQL (copie-prod §3.5, `compter_avant`) | sinon **STOP** | — |
| 4 | **Export des anciennes clôtures**, AVANT les migrations | `DJ anciennes_clotures --exporter <sauvegardes>/anciennes_clotures/` | total du rapport = un comptage SQL **séparé** fait juste avant (somme des `count(*)` de `comptabilite_cloturecaisse` par schéma) ; nombre de fichiers = lieux qui ont des clôtures | 4,8 s (50 827 clôtures, copie migrée) |
| 5 | Capture de la fiche de l'asset CLAF et de ses remises en banque | (navigateur, copie-prod §3.5) | — | — |
| 6 | Migrations, **un lieu après l'autre** (jamais `--executor=multiprocessing`) | `DJ migrate_schemas` | aucune ligne « moteur v2 (module V2 actif) » ; lieux `legacy` sauf `W` | **3 h 14 pour 513 lieux** (R-0, ~23 s / lieu) |
| 7 | **Suppression des anciennes clôtures** | `DJ anciennes_clotures --supprimer --export <sauvegardes>/anciennes_clotures/` (à blanc), puis la même avec `--executer` | 0 lieu refusé ; 0 ligne dans `comptabilite_cloturecaisse` | 2,5 s |
| 8 | Passage à blanc de la reprise | `DJ reprendre_les_ventes_existantes > <sauvegardes>/reprise_blanc.txt` | **0 anomalie bloquante** ; total « ancien = nouveau » hors parts QR ; 125 virements reçus | 42 s (365 lieux) |
| 9 | **Écriture de la reprise** | `DJ reprendre_les_ventes_existantes --executer > <sauvegardes>/reprise_ecriture.txt` | 0 lieu refusé (sinon la ligne « Chaîne des ventes valide » du total disparaît : lire chaque lieu) ; « Chaîne des ventes valide : oui » ; contrôles : 0 ligne sans vente, 0 avoir sans vente liée. **Une erreur arrête la commande : la relancer telle quelle, les ventes déjà écrites sont sautées** | 12 min (22 489 ventes) |
| 10 | **J « reprise »** par lieu (synchrone, sans mail). **Juste avant : revérifier qu'aucun processus Celery ne tourne** (un beat vivant créerait une J ordinaire, et la J reprise serait refusée dans ce lieu) | `DJ creer_la_cloture_de_reprise > <sauvegardes>/j_reprise.txt` | une J par lieu qui a des ventes ; 0 refus ; `verify_clotures` OK | 102 J (copie) ; durée à noter à la répétition |
| 11 | Réouverture ; Celery relancé (filet J ; rattrapage H / M / A, 12 par passage, sans mail). Les mails de `supprimer_lieux_inactifs` attendent dans Redis depuis 2 bis : **Redis doit suivre la migration de serveur**, sinon ils sont perdus | (pile de prod) | Mailpit de la répétition : 0 mail de clôture historique ; charge du rattrapage (102 lieux × 12 rapports par heure) : à surveiller la première heure, jamais mesurée (pas de worker sur la copie) | — |
| 12 | Capture CLAF (étape 5) refaite | (navigateur) | mêmes chiffres | — |

**Retour arrière** (décision du mainteneur) : restaurer la sauvegarde de l'étape 2 bis et
redéployer l'image de `main`.

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
