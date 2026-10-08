# Chantier 05-R-4 — La nuit de la bascule, pas à pas

> **Statut** : 🔧 BROUILLON (2026-10-08), relu par Fable (constats intégrés) — à éprouver par la
> **répétition chronométrée** sur la copie (dernière section).
> Source : fiche R §12 (l'ordre et les contrôles), §18 (lieux inactifs), décisions du SUIVI §5.
> **Le mainteneur est aux commandes toute la nuit** (migration de serveur et DNS compris) et
> décide seul d'un retour arrière.

Notation : `DJ` = `docker exec -i <conteneur Django de la prod> poetry run python /DjangoFiles/manage.py`.
`<sauvegardes>` = un dossier **hors du dépôt**, sur le serveur, gardé avec la sauvegarde complète.

## Avant la nuit

- [ ] Branche prête : fiche R commitée, suite complète verte, E2E verts.
- [ ] Copie de la production la plus récente : répétition complète de cette procédure,
      chronométrée (dernière section). **Prérequis bloquant** : les étapes 2 bis
      (`supprimer_lieux_inactifs`) et 4 (`anciennes_clotures --exporter`) y tournent avec le
      code de la branche sur la base de `main` **non migrée**, comme la nuit (elles n'ont été
      éprouvées que sur une base déjà migrée).
- [ ] **J-1, en production, lecture seule** : `DJ supprimer_lieux_inactifs --rapport <sauvegardes>/lieux_inactifs_J-1.csv`
      → le mainteneur valide la liste (elle devient le fichier `--liste` de l'étape 2 bis).
- [ ] Message aux lieux : fermeture de la billetterie, de l'admin et des caisses pendant la nuit.

## La nuit

| # | Étape | Commande | Contrôle | Durée mesurée (copie) |
|---|---|---|---|---|
| 1 | Tout couper : site, admin, API ; **worker ET beat Celery arrêtés** jusqu'à l'étape 11 | (pile de prod) | plus aucune requête dans les journaux | — |
| 2 | Postgres avec `max_locks_per_transaction` ≥ 512 (copie : 4 096 pour le chargement) | compose de prod | `SHOW max_locks_per_transaction;` | — |
| 1 bis | Image de la branche déployée, `MIGRATE=0`, site toujours coupé | (mainteneur) | aucune ligne `migrate_schemas` dans le journal ; **aucun processus Celery** (le déploiement relance souvent `lespass_celery`, beat compris : `docker ps` + `ps aux | grep celery` dans les conteneurs) | — |
| 2 bis | **Sauvegarde complète** puis suppression des lieux inactifs, puis des 2 schémas sans lieu | `pg_dump -Fc …` ; `DJ supprimer_lieux_inactifs --liste <liste J-1> --executer --rapport … --traces-externes …` | 0 schéma sans lieu, 0 lieu sans schéma | sauvegarde : à mesurer ; suppression : 7 min 12 (148 lieux) |
| 3 | Plan comptable par défaut de `main` seul présent ; **0 lieu de production avec un drapeau V2** | comptages SQL (copie-prod §3.5, `compter_avant`) | sinon **STOP** | — |
| 4 | **Export des anciennes clôtures**, AVANT les migrations | `DJ anciennes_clotures --exporter <sauvegardes>/anciennes_clotures/` | total du rapport = un comptage SQL **séparé** fait juste avant (somme des `count(*)` de `comptabilite_cloturecaisse` par schéma) ; nombre de fichiers = lieux qui ont des clôtures | 4,8 s (50 827 clôtures, copie migrée) |
| 5 | Capture de la fiche de l'asset CLAF et de ses remises en banque | (navigateur, copie-prod §3.5) | — | — |
| 6 | Migrations, **un lieu après l'autre** (jamais `--executor=multiprocessing`) | `DJ migrate_schemas` | aucune ligne « moteur v2 (module V2 actif) » ; lieux `legacy` sauf `W` | 3 h 14 pour 513 lieux (~23 s / lieu) ; ~2 h 20 attendues pour 365 |
| 7 | **Suppression des anciennes clôtures** | `DJ anciennes_clotures --supprimer --export <sauvegardes>/anciennes_clotures/` (à blanc), puis la même avec `--executer` | 0 lieu refusé ; 0 ligne dans `comptabilite_cloturecaisse` | 2,5 s |
| 8 | Passage à blanc de la reprise | `DJ reprendre_les_ventes_existantes > <sauvegardes>/reprise_blanc.txt` | **0 anomalie bloquante** ; total « ancien = nouveau » hors parts QR ; 125 virements reçus | 42 s (365 lieux) |
| 9 | **Écriture de la reprise** | `DJ reprendre_les_ventes_existantes --executer > <sauvegardes>/reprise_ecriture.txt` | 0 lieu refusé (sinon la ligne « Chaîne des ventes valide » du total disparaît : lire chaque lieu) ; « Chaîne des ventes valide : oui » ; contrôles : 0 ligne sans vente, 0 avoir sans vente liée. **Une erreur arrête la commande : la relancer telle quelle, les ventes déjà écrites sont sautées** | 12 min (22 489 ventes) |
| 10 | **J « reprise »** par lieu (synchrone, sans mail). **Juste avant : revérifier qu'aucun processus Celery ne tourne** (un beat vivant créerait une J ordinaire, et la J reprise serait refusée dans ce lieu) | `DJ creer_la_cloture_de_reprise > <sauvegardes>/j_reprise.txt` | une J par lieu qui a des ventes ; 0 refus ; `verify_clotures` OK | 102 J (copie) ; durée à noter à la répétition |
| 11 | Réouverture ; Celery relancé (filet J ; rattrapage H / M / A, 12 par passage, sans mail). Les mails de `supprimer_lieux_inactifs` attendent dans Redis depuis 2 bis : **Redis doit suivre la migration de serveur**, sinon ils sont perdus | (pile de prod) | Mailpit de la répétition : 0 mail de clôture historique ; charge du rattrapage (102 lieux × 12 rapports par heure) : à surveiller la première heure, jamais mesurée (pas de worker sur la copie) | — |
| 12 | Capture CLAF (étape 5) refaite | (navigateur) | mêmes chiffres | — |

**Retour arrière** (décision du mainteneur) : restaurer la sauvegarde de l'étape 2 bis et
redéployer l'image de `main`.

## Répétition chronométrée sur la copie

Ordre de la copie (copie-prod §2 bis) : `detruire`, `demarrer`, `charger <dump le plus récent>`,
`compter_avant`, `neutraliser`, puis les étapes 2 bis (sans sauvegarde ni mails), 3, 4, 6
(`migrer`), 7, 8, 9, 10 de la nuit ; `compter` (Mailpit) à la fin. Chaque durée est notée dans
la dernière colonne ci-dessus.

Déjà éprouvé sur la copie migrée (instantané `db-prod/copie_migree_nettoyee_2026-10-08.dump`) :
étapes 4 (export sur une base déjà migrée), 7, 8, 9, 10 (fiche R §14 bis à §14 quater).
