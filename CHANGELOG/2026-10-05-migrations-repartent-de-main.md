# Les migrations repartent de `main` / Migrations restart from `main`

**Date :** 2026-10-05
**Migration :** Oui — base de dev à recréer / Yes — dev database must be recreated

## Resume / Summary
**Quoi / What :** toutes les migrations ajoutées par la branche `main-fedow-import` depuis `main` (70 fichiers) sont supprimées et regénérées. Les migrations de `main` ne changent pas.
/ Every migration added by the `main-fedow-import` branch since `main` (70 files) is deleted and regenerated. The `main` migrations do not change.

**Pourquoi / Why :** après la fusion, deux séries de migrations portaient les mêmes numéros (BaseBillet 0230-0235 et 0230-0234, laboutik 0007-0009 en double). `main` est ce qui tourne en production : on repart de lui, avec une seule série lisible.
/ After the merge, two migration series had the same numbers (BaseBillet 0230-0235 and 0230-0234, laboutik 0007-0009 twice). `main` is what runs in production: we restart from it, with one readable series.

**Données / Data :** les migrations de données sont dans des fichiers séparés du schéma.
/ Data migrations live in files separate from the schema.
- `seo 0005` supprime les doublons de SEOCache, AVANT que `seo 0006` pose les contraintes d'unicité.
  / `seo 0005` removes SEOCache duplicates BEFORE `seo 0006` adds the unique constraints.
- `BaseBillet 0225` copie le skin de `Configuration` vers `pages.ConfigurationSite` et crée la page d'accueil par défaut, PUIS `BaseBillet 0226` retire le champ `skin`.
  / `BaseBillet 0225` copies the skin into `pages.ConfigurationSite` and creates the default home page, THEN `BaseBillet 0226` removes the `skin` field.
- `laboutik 0002` prépare chaque lieu : plan comptable par défaut, FED relié au 467000, crowds rangés dans « Financement participatif » (754000), configuration LaBoutik et sa clé d'empreinte.
  / `laboutik 0002` prepares each venue: default chart of accounts, FED linked to 467000, crowds filed under crowdfunding (754000), LaBoutik configuration and its fingerprint key.

Ne sont PAS reprises (corrections de bases de dev, sans objet sur une base neuve ou en production) : les anciennes laboutik 0004 (noms de terminaux), 0006 (icônes FontAwesome), 0008 (numéros de compte en double), 0014 (lien de clôture des impressions).
/ NOT carried over (dev database fixes, pointless on a new database or in production): former laboutik 0004, 0006, 0008, 0014.

### Nouveaux fichiers / New files
| App | Fichiers / Files |
|---|---|
| AuthBillet | `0024_role_de_terminal_et_portefeuille` |
| BaseBillet | `0222_ventes_reglements_commandes_et_categories`, `0223_ligne_article_reservation_couts_et_jetons`, `0224_liens_caisse_fedow_et_montants_des_ventes`, `0225_copier_le_skin_et_creer_la_page_d_accueil` (données / data), `0226_retirer_le_skin_de_la_configuration` |
| Customers | `0005_libelles_fr_du_lieu` |
| MetaBillet | `0018_libelles_fr_de_la_demande_de_lieu` |
| QrcodeCashless | `0021_portefeuille_ephemere_de_la_carte` |
| comptabilite | `0004_cloture_chainee`, `0005_cloture_unique_et_retrait_de_l_ancien_plan` |
| crowds | `0009_libelle_fr_de_la_description` |
| discovery | `0003_appairage_cible_et_role_du_terminal` |
| fedow_public | `0004_libelles_fr_des_monnaies` |
| onboard | `0002_libelle_fr_de_la_date_d_invitation` |
| root_billet | `0007_domaines_embed_autorises` |
| seo | `0005_dedoublonner_seocache` (données / data), `0006_contraintes_uniques_seocache` |
| booking, controlvanne, fedow_core, inventaire, kiosk, pages | `0001_initial` |
| laboutik | `0001_initial`, `0002_preparer_chaque_lieu` (données / data) |

Tests adaptés / Adapted tests : `tests/pytest/test_cle_d_empreinte_du_lieu.py` et `tests/pytest/test_plan_comptable_unique.py` pointent vers `laboutik 0002_preparer_chaque_lieu` ; les tests des migrations non reprises (icônes 0006, dédoublonnage 0008) sont retirés de `tests/pytest/test_laboutik_icones.py` et `tests/pytest/test_plan_comptable_unique.py`.
/ Tests point to `laboutik 0002_preparer_chaque_lieu`; tests of the dropped migrations (0006, 0008) are removed.

---

## Ce que fait chaque développeur / What each developer does
Une base de dev qui a appliqué les anciennes migrations de la branche ne peut pas passer aux nouvelles : les noms ont changé. Il faut la recréer.
/ A dev database that applied the old branch migrations cannot move to the new ones: names changed. Recreate it.

1. `docker compose down -v` (supprime les volumes, donc la base) / (removes the volumes, hence the database).
2. Relancer les conteneurs, puis `./flush.sh` dans le conteneur `lespass_django`.
   / Start the containers again, then `./flush.sh` in the `lespass_django` container.

## Production
Rien à défaire. Les migrations de `main` déjà appliquées en production sont intactes ; au déploiement, seules les nouvelles migrations listées ci-dessus s'appliquent, à la suite de celles de `main`.
/ Nothing to undo. The `main` migrations already applied in production are untouched; on deployment, only the new migrations above are applied, after the `main` ones.
