# Un seul plan comptable, lisible, qui sépare tout (chantier 05, fiche E) / One single readable chart of accounts that separates everything (worksite 05, sheet E)

**Date :** 2026-10-02
**Migration :** Oui — `laboutik/0008_dedoublonner_les_numeros_de_compte`, `laboutik/0009_comptecomptable_numero_de_compte_unique`, `laboutik/0010_charger_le_plan_comptable_par_defaut` (E-1a) ; `laboutik/0011_monnaie_et_code_journal`, `laboutik/0012_relier_le_fed_au_compte_du_reseau`, `laboutik/0013_ranger_les_crowds_dans_le_financement_participatif`, `comptabilite/0004_retirer_l_ancien_plan_comptable` (E-1b) ; `BaseBillet/0232_alter_product_prix_achat` (E-2, aide seulement).
`docker exec lespass_django poetry run python manage.py migrate_schemas --executor=multiprocessing`

## Resume / Summary
**Quoi / What :** un seul plan comptable par défaut, aux numéros à 6 chiffres, présent dans chaque lieu ; le chargement ajoute ce qui manque sans rien effacer. /
One single default chart of accounts, 6-digit numbers, present in every venue; loading adds what is missing and erases nothing.

**Pourquoi / Why :** chantier 05 « montants entiers », fiche E : dissocier les ventes en ligne, les points de vente, les monnaies et la TVA ; « un seul [plan], simple, qui s'ouvre à la création du lieu » (mainteneur, 2026-10-02). /
Worksite 05, sheet E: separate online sales, points of sale, currencies and VAT; "one single simple plan, opened when the venue is created".

Sections ci-dessous : E-1a (plan par défaut, chargement, unicité, bouton corrigé), E-1b (règles de compte, journal, CSV en ligne sur le plan unique, retrait de l'ancien plan), E-2 (écrans pour un bénévole, « Plan complet ? »), E-3 (jetons offerts : vraie vente hors TVA, dette soldée ; crowds sans TVA), E-4 (corrections de la grande relecture, tests qui manquaient), puis les tableaux des mutations. / Sections below: E-1a, E-1b, E-2, E-3, E-4, then the mutation tables.

## E-1a — Un seul plan, toujours présent / One single plan, always present

**Migration :** Oui (3, ci-dessus) — **Chaînes i18n :** oui (liste plus bas).

### Resume / Summary
**Quoi / What :**
- **Plan par défaut** (`laboutik/plan_comptable_par_defaut.py`, données seules) : 20 comptes. Ventes 706000, 707000, 707900 (ventes réglées en jetons offerts, TVA 0), 756000, 754000 ; TVA 445711 (20 %), 445712 (10 %), 445713 (5,5 %), 445714 (2,1 %) ; trésorerie 530000, 511200, 512100, 517100, 512000 ; tiers 467000 (monnaie FED), 419100, 471000 ; charges 623400, 658000 ; 758000 (produit exceptionnel). Correspondances : `CA` 530000, `CH` 511200, `CC` 512100, `SN` / `SP` / `SR` 517100, `TR` 512000, `LE` / `LG` 419100, `UK` 471000 ; aucune pour `NA`, `NM`, `SF`, `QR`. Catégories reliées si elles existent : « Financement participatif » 754000, écarts d'encaissement 758000 / 658000. /
  Default plan: 20 accounts, 10 payment method mappings, 3 known categories linked when they exist.
- **Chargement** (`laboutik/plan_comptable.py`) : `charger_le_plan_comptable_par_defaut()` ajoute ce qui manque. Compte ordinaire retrouvé par son numéro ; compte de TVA retrouvé **par son taux** ; si le numéro voulu est pris par un compte d'un autre taux : ni création ni écrasement, un avertissement (journal et retour de la fonction). Correspondance créée seulement si le moyen n'en a aucune. Catégorie connue reliée seulement si elle existe et n'a pas de compte ; jamais créée, sauf « Financement participatif » (créée si elle manque, depuis E-1b). Filet `s_assurer_que_le_plan_existe()` : charge le plan si le lieu n'a **aucun** compte (atomic, `IntegrityError` attrapée) ; appelé par personne en E-1a (E-2 et F le brancheront). /
  Loading adds what is missing; VAT looked up by rate; a VAT number taken by another rate gives a warning; safety net loads when the venue has no account.
- **Profils `bar_resto` et `association` retirés** : la commande `charger_plan_comptable --schema=<lieu>` perd `--jeu` et `--reset` ; le bouton de l'admin charge le plan par défaut **sans rien effacer** (avant : il effaçait tout le plan et vidait les liens des catégories dès qu'un compte existait) ; son bandeau a un seul bouton et dit ce qu'il fait. /
  Profiles removed: the command loses `--jeu` and `--reset`; the admin button no longer erases the plan.
- **Unicité de `numero_de_compte`** dans un lieu, en trois migrations : 0008 dédoublonnage (`RunPython`, garde le **premier par `pk`**, repointe catégories et correspondances, supprime les autres ; rien dans `public`) ; 0009 contrainte ; 0010 chargement du plan dans tout lieu sans compte (couvre les lieux créés plus tard : `auto_create_schema` rejoue les migrations). Inverses : `noop`. /
  Account number unique per venue: dedup (keeps the first by pk), constraint, plan loaded where no account exists.

**Correction du brief :** le brief disait « garde le plus ancien » ; `CompteComptable` n'a pas de date de création (clé uuid4) : « le plus ancien » ne se calcule pas. Décision de l'orchestrateur : le premier par `pk` (tous les liens finissent sur lui, le choix n'a pas d'autre effet). /
Brief correction: "keep the oldest" cannot be computed; the first by pk is kept.

**Pourquoi / Why :** fiche E §2 et §3.4 ; SUIVI §5 (2026-10-02). Le bouton contredisait son bandeau (bug existant). /
Sheet E §2 and §3.4. The button contradicted its banner (existing bug).

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/plan_comptable_par_defaut.py` | Nouveau : données du plan (comptes, correspondances, catégories connues, `NOM_CATEGORIE_FINANCEMENT_PARTICIPATIF`) |
| `laboutik/plan_comptable.py` | Nouveau : `charger_le_plan_comptable_par_defaut()`, `s_assurer_que_le_plan_existe()` |
| `laboutik/management/commands/charger_plan_comptable.py` | Réécrit : `--schema` seul, appelle le chargeur, n'efface rien |
| `laboutik/views.py` | `CaisseViewSet.charger_plan_comptable` : plus de `jeu`, appelle le chargeur, message « n compte(s) ajouté(s) », avertissements montrés |
| `Administration/templates/admin/comptable/changelist_before.html` | Un seul bouton « Charger le plan par défaut » ; texte vrai ; `aria-live` sur la zone de réponse |
| `laboutik/models.py` | `CompteComptable.numero_de_compte` : `unique=True` |
| `laboutik/migrations/0008_…`, `0009_…`, `0010_…` | Dédoublonnage, contrainte, chargement du plan |
| `tests/pytest/test_plan_comptable_unique.py` | Nouveau : 11 tests (schéma dédié) |
| `tests/pytest/test_export_comptable.py` | `jeu=` retiré, `7072000` → `707000` ; tests des deux profils supprimés (couverts par `test_plan_par_defaut_complet_six_chiffres`) ; attente `000000` gardée (fiche F) |
| `tests/pytest/test_profils_csv_comptable.py`, `test_hors_argent_offerts.py`, `test_vente_en_points.py` | `jeu=` retiré, `7072000` → `707000` |

### Chaînes i18n / i18n strings
Workflow i18n à lancer par le mainteneur (pas de `makemessages`). / i18n workflow to be run by the maintainer.
- Nouvelles (source FR) : « %(nombre)s compte(s) ajouté(s) au plan comptable. Rien n'a été effacé. » ; « Ajoute les comptes du plan par défaut qui manquent. Les comptes existants et les liens des catégories ne sont jamais modifiés. Ajoutez vos comptes, ne renumérotez pas ceux du plan par défaut. » ; « Charger le plan par défaut ».
- Retirées du code : « Jeu de comptes invalide. » ; « Plan comptable charge avec succes. » ; « Plan comptable remplace avec succes (%(nb)s comptes precedents supprimes). » ; « Pre-fill accounting codes for your activity type. Existing accounts will not be overwritten. » ; « Bar / Restaurant » ; « Association » (dans ce gabarit seulement).
- Gardée : « Load a default chart of accounts » (titre du bandeau).

### Tests vus rouges / Tests seen red
Avant tout code de production (10 tests ; le 11ᵉ, `test_chargement_tva_numero_pris_par_un_autre_taux_avertit`, ajouté après la décision « avertissement ») :
```
test_bouton_de_l_admin_n_efface_plus_le_plan          assert 400 == 200 (« Jeu de comptes invalide »)
test_categories_d_ecart_reliees_si_elles_existent     CommandError: the following arguments are required: --jeu
test_chargement_ajoute_ce_qui_manque_sans_rien_effacer CommandError: ... --jeu
test_chargement_cherche_la_tva_par_taux               CommandError: ... --jeu
test_dedoublonnage_garde_un_compte_et_repointe_les_liens ModuleNotFoundError: laboutik.migrations.0008_dedoublonner_les_numeros_de_compte
test_filet_charge_le_plan_si_aucun_compte             ImportError: s_assurer_que_le_plan_existe
test_filet_ne_fait_rien_si_un_compte_existe           ImportError: s_assurer_que_le_plan_existe
test_migration_charge_le_plan_si_aucun_compte         ModuleNotFoundError: laboutik.migrations.0010_charger_le_plan_comptable_par_defaut
test_numero_de_compte_unique                          AssertionError: IntegrityError not raised
test_plan_par_defaut_complet_six_chiffres             assert set() == {'419100', ...}
10 failed
```

## E-1b — Les règles de compte, le journal, le CSV en ligne sur le plan unique / Account rules, journal, online CSV on the single plan

**Migration :** Oui (4) — `laboutik/0011_monnaie_et_code_journal` (schéma : `PointDeVente.code_journal`, modèle `MappingMonnaie`), `laboutik/0012_relier_le_fed_au_compte_du_reseau` (données), `laboutik/0013_ranger_les_crowds_dans_le_financement_participatif` (données), `comptabilite/0004_retirer_l_ancien_plan_comptable` (schéma : `DeleteModel` × 2). Une migration par nature d'opération (PIEGES 9.113). Inverses des migrations de données : `noop`. — **Chaînes i18n :** oui (liste plus bas).

### Resume / Summary
**Quoi / What :**
- **`laboutik.MappingMonnaie`** : un compte par monnaie (`asset_uuid` unique, sans clé étrangère : fedow_core ou ancien Fedow ; `compte_de_tresorerie` en `PROTECT`). Les deux uuid du FED vont au 467000 : par le chargeur (étape 4) et, pour les lieux déjà chargés, par la migration 0012 (crée le 467000 s'il manque, ne touche pas une correspondance existante, idempotente, rien dans `public`). /
  One account per currency; both FED uuids go to 467000 (loader and data migration).
- **`PointDeVente.code_journal`** : 10 lettres majuscules au plus (`RegexValidator`), vide permis. /
  Journal code: uppercase letters only, 10 max.
- **Règles** (`laboutik/plan_comptable.py`, sans état, une seule exception `CompteComptableManquant` dont le message nomme ce qui manque) :
  - `compte_pour_reglement(moyen, asset_uuid)` : `NA` / `NM` → `None` ; le compte de la monnaie d'abord ; `SF` toujours par sa monnaie (sans compte de monnaie : erreur, même si le moyen `SF` a une correspondance) ; une monnaie d'un autre lieu sans compte : erreur ; sinon le compte du moyen (correspondance absente ou au compte vide : erreur, D23). /
    Currency first; SF only through its currency; another venue's currency without account, missing or empty method mapping: error.
  - `journal_pour(point_de_vente, origine)` : le point de vente gagne ; son code, sinon dérivé du nom (majuscules, sans accent, lettres seules, 10) ; nom sans lettre : erreur ; sans point de vente : `CAISSE` (LB, QR, NF), `TIREUSE` (TI), `WEB` (LP, AP, EX, WK), `ADMIN` (AD) ; origine inconnue : erreur. `collisions_de_codes_journal()` : `{code: [points de vente]}` des seuls codes en double (pour « Plan complet ? », E-2). /
    The point of sale wins; code set or derived from the name; 9-origin table; collisions listed.
  - `compte_pour_article(ligne)`, dans l'ordre : (0) liste explicite, catégorie ignorée : écarts par le nom de leur produit (758000 / 658000), recharges `RE`, `RC`, `R`, `E` → 419100, virement du pot central `VR` → compte de la monnaie de la ligne ; `TM` / `FD` : erreur, avec ou sans catégorie ; (1) `CR` → compte de la catégorie de la consigne remboursée (sinon erreur) ; (2) catégorie de caisse reliée à un compte ; (3) `AD` → 756000, `BI` → 706000, `VT` / `FR` sans catégorie : erreur ; (4) `B`, `F`, `G`, `Q`, `C` → 706000, `A` → 756000 ; (5) erreur. Numéros tirés de `COMPTE_PAR_DEFAUT` (module de données), cherchés par `numero_de_compte`. /
    Item account rules in the sheet's order; numbers from COMPTE_PAR_DEFAUT.
- **Crowds = don au 754000** : `crowds/views.py` crée le produit « crowdfunding » dans la catégorie « Financement participatif » (créée reliée au 754000, ou reliée au 754000 si elle existe sans compte) ; le chargeur crée cette catégorie si elle manque et y range les produits crowds sans catégorie ; la migration 0013 fait de même dans les lieux existants. La TVA 0 des crowds reste à E-3. /
  Crowds contributions go to 754000 through their category.
- **CSV comptable en ligne** (`comptabilite/csv_comptable.py`) : lit le plan de la caisse (`laboutik.MappingMoyenDePaiement`, `laboutik.CompteComptable`) ; TVA cherchée **par taux** ; billets / adhésions par `COMPTE_PAR_DEFAUT`. Le prorata du HT, le repli 512000 avec avertissement (aussi pour une correspondance au compte vide) et la lecture de `rapport_json` ne changent pas (fiche F). /
  The online CSV reads the register's plan; VAT by rate.
- **Ancien plan retiré** : `comptabilite.CompteComptable` et `comptabilite.MappingMoyenDePaiement` (modèles, admins, import) supprimés par `DeleteModel` ; la migration de données `comptabilite/0002` reste dans l'historique, ses lignes partent avec les tables (« en prod, aucun compte comptable n'existe »). `ClotureCaisse` intouché. Commentaires périmés corrigés dans `comptabilite/apps.py` et `comptabilite/fec.py`. /
  Old plan removed (models, admins); migration 0002 stays in history.

**Pourquoi / Why :** fiche E §2.1 (fin), §3.1, §3.2, §3.3 ; SUIVI §5 (2026-10-02 : un compte par monnaie, `VR` au compte de la monnaie, crowds = don) ; décisions de l'orchestrateur à l'étape 2 (FED et crowds aussi par migration, règle 0 en liste explicite, `TM` / `FD` toujours en erreur, compte de moyen vide en erreur). /
Sheet E §2.1, §3.1-§3.3; maintainer and orchestrator decisions.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/models.py` | `PointDeVente.code_journal` ; modèle `MappingMonnaie` |
| `laboutik/plan_comptable.py` | `CompteComptableManquant`, `compte_pour_reglement`, `journal_pour`, `code_journal_du_point_de_vente`, `collisions_de_codes_journal`, `compte_pour_article` ; chargeur : catégorie crowds (créée, produits rangés) et FED au 467000 |
| `laboutik/plan_comptable_par_defaut.py` | `COMPTE_PAR_DEFAUT`, `NOM_DU_PRODUIT_DE_FINANCEMENT_PARTICIPATIF` |
| `laboutik/migrations/0011_…`, `0012_…`, `0013_…` | Schéma ; FED au 467000 ; crowds au 754000 |
| `comptabilite/csv_comptable.py` | Lit le plan de la caisse ; TVA par taux ; billets / adhésions par `COMPTE_PAR_DEFAUT` |
| `comptabilite/models.py`, `comptabilite/admin.py`, `comptabilite/migrations/0004_…` | Retrait des deux modèles de l'ancien plan et de leurs admins |
| `comptabilite/apps.py`, `comptabilite/fec.py` | Commentaires seulement |
| `crowds/views.py` | `_get_or_create_crowdfunding_price` : création du produit dans la catégorie « Financement participatif » reliée au 754000 |
| `tests/pytest/test_plan_comptable_unique.py` | 24 tests ajoutés (35 au total) ; `test_categories_d_ecart_reliees_si_elles_existent` ne vérifie plus la catégorie crowds (le chargeur la crée désormais) ; `_vider_le_plan_du_lieu` supprime d'abord les `MappingMonnaie` |
| `tests/pytest/test_comptabilite_models.py` | **Supprimé** : il testait les deux modèles retirés et le seed `comptabilite/0002` ; ses cas utiles (comptes et correspondances CA / CC / CH présents dans chaque lieu) sont couverts par `test_plan_par_defaut_complet_six_chiffres` |
| `tests/pytest/test_export_comptable.py`, `test_profils_csv_comptable.py` | `setUp` : `MappingMonnaie.objects.all().delete()` avant les comptes. Mécanisme seulement, aucune attente ne change : `PROTECT` voulu, la correspondance du FED (migration 0012) protège le 467000 |

### Chaînes i18n / i18n strings
Workflow i18n à lancer par le mainteneur (pas de `makemessages`). / i18n workflow to be run by the maintainer.
- Nouvelles (source FR) : « Code journal » ; « Code du journal comptable de ce point de vente, 10 lettres majuscules au plus (ex. : BAR). Vide : dérivé du nom du point de vente. » ; « Lettres majuscules seules, sans accent (ex. : BAR). » ; « Monnaie (uuid) » ; « Identifiant de la monnaie (fedow_core ou ancien Fedow). » ; « Compte de la monnaie » ; « Compte d'une monnaie » ; « Comptes des monnaies ».
- Retirées du code (admin et modèles de l'ancien plan) : « Numéro de compte », « Libellé », « Type de compte », « Actif », « Compte comptable », « Comptes comptables », « Ventes », « TVA collectée », « Trésorerie (banque / caisse) », « Clients », « Autre », « Moyen de paiement », « Code PaymentMethod de BaseBillet (CC, CA, CH, TR, SF, ...) », « Mapping moyen de paiement », « Mappings moyens de paiement » (à garder si un autre code les emploie).

### Tests vus rouges / Tests seen red
Avant tout code de production (15 tests) : collecte en erreur `ImportError: cannot import name 'MappingMonnaie' from 'laboutik.models'` ; avec des bouchons en mémoire, 15 failed, 11 passed (E-1a vert) : `TypeError ... 'code_journal'` (journaux, collisions, validation), `NotImplementedError` (règles), `AttributeError` sur `MappingMonnaie`, et deux rouges de fond sur le CSV (`('530000', 'Caisse (especes)')`, `('512000', 'Banque')`, `'4457300'` : comptes de l'ancien plan ; `['4457100', '…', '4457300'] != ['445700', '445713', '445714']`). Les 9 tests ajoutés après les décisions de l'orchestrateur (crowds, FED par migration, compte de moyen vide, nom sans lettre, consigne sans compte) ont été écrits avec le code : leurs mutations sont au tableau E-1b.

### Tests verts / Tests green
- `make test ARGS="tests/pytest/test_plan_comptable_unique.py -q"` : 35 passed.
- `rg -l "comptabilite|csv_comptable|plan_comptable|crowd" tests/pytest` + `test_caracterisation_*.py` (35 fichiers) : 414 passed.
- `manage.py check` : aucun problème ; `makemigrations --check` : aucun changement ; `migrate_schemas` rejoué : rien à appliquer.

## E-2 — Lisible pour un bénévole : menus, comptes des monnaies, « Plan complet ? » / Readable for a volunteer: menus, currency accounts, "Complete plan?"

**Migration :** Oui (1) — `BaseBillet/0232_alter_product_prix_achat` (`AlterField`, aide du prix d'achat seulement, aucune donnée). — **Chaînes i18n :** oui (liste plus bas).

### Resume / Summary
**Quoi / What :**
- **Menu « Ventes & comptabilité »** : sous les rapports et « Entries », trois entrées toujours présentes (le plan sert aussi à l'export en ligne) : « Plan comptable », « Comptes des moyens de paiement », « Comptes des monnaies ». Les entrées commentées vers l'ancien plan (`comptabilite_*`) sont retirées. /
  Three always-visible entries under the reports.
- **Plan comptable** : liste regroupée par nature (tri nature puis numéro, filtre par nature existant) ; une phrase d'aide par nature (ventes, TVA, trésorerie, tiers, charges, écarts, spécial) ; l'aide des ventes dit que 754000 / 756000 sont des comptes d'association (un bar en société utilise 706000 / 707000). /
  Accounts grouped by nature, one help sentence per nature.
- **Comptes des monnaies** (admin nouveau de `MappingMonnaie`) : une ligne par monnaie acceptée par le lieu (fedow_core : `AssetService.obtenir_assets_accessibles` ; ancien Fedow : créées par le lieu, fédérées avec lui, et le FED), sans les monnaies archivées ni celles sans argent (points, temps, adhésion, badge). Chaque ligne : nom, origine (« ce lieu » / « un autre lieu » / « fédérée »), compte. Une monnaie du lieu sans compte propre affiche en neutre le compte de son moyen (`LE` ou `LG`, 419100) : l'export passe. Une monnaie d'un autre lieu ou fédérée sans compte est en **orange** : « l'export comptable sera refusé tant que ce compte manque », avec un lien « Choisir un compte » (formulaire, monnaie déjà choisie). Le formulaire propose les monnaies acceptées (pas un uuid à taper) et seulement des comptes de trésorerie ou de tiers. /
  One row per accepted money currency; venue currency falls back to its method's account (neutral); other venue's or federated currency without account in orange.
- **« Plan complet ? »** (`laboutik/plan_comptable.py`, `ce_qui_manque_pour_exporter()`) : appelle d'abord le filet, puis rend les manques, chacun avec une phrase et un lien vers l'écran qui le règle : produit vendu sans compte ; moyen de paiement utilisé sans compte ; monnaie utilisée sans compte ; taux de TVA utilisé sans compte (0 % n'en exige pas) ; codes journal en double ; point de vente sans code au nom sans lettre ; règlements au compte d'attente 471000, à reclasser. « Utilisé » = dans une vente réglée du lieu. Composant en tête des trois écrans du plan ; rien ne manque : message vert « Le plan est complet : l'export est possible ». /
  "Complete plan?" lists what blocks the export, on top of the three plan screens.
- **`collisions_de_codes_journal()`** saute un point de vente sans code au nom sans lettre (il ne cache plus la collision des autres) ; `points_de_vente_sans_code_journal()` les rend à part. /
  The collision function skips letterless names; a new function returns them.
- **Points de vente** : le champ « Code journal » est dans le formulaire (aide du modèle). /
  Journal code field in the point of sale form.
- **Prix d'achat** : aide « en centimes, par unité de vente (kg, litre, pièce) ; 0 = inconnu » (D21). /
  Purchase price help text.

**Pourquoi / Why :** fiche E §4 et §3.4 (rappel du 471000) ; décisions de l'orchestrateur à l'étape 2 (monnaie du lieu en neutre, orange pour une monnaie d'ailleurs ; archivées et monnaies sans argent sans ligne ; collision et nom sans lettre listés ensemble ; menu toujours présent ; TVA 0 sans compte). /
Sheet E §4; orchestrator decisions.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin/dashboard.py` | Trois entrées du plan sous « Entries » ; entrées commentées `comptabilite_*` retirées |
| `Administration/admin/laboutik.py` | `PointDeVenteAdmin` : `code_journal` ; `CompteComptableAdmin` : tri par nature, manques ; `MappingMoyenDePaiementAdmin` : bandeau « Plan complet ? » ; nouveaux `MappingMonnaieForm` et `MappingMonnaieAdmin` |
| `Administration/templates/admin/comptable/plan_complet.html` | Nouveau : composant « Plan complet ? » |
| `Administration/templates/admin/comptable/changelist_before.html` | Composant en tête ; aides par nature |
| `Administration/templates/admin/comptable/moyens_changelist_before.html` | Nouveau : composant en tête |
| `Administration/templates/admin/comptable/monnaies_changelist_before.html` | Nouveau : composant en tête ; une ligne par monnaie acceptée |
| `laboutik/plan_comptable.py` | `collisions_de_codes_journal` saute les noms sans lettre ; `points_de_vente_sans_code_journal`, `nom_de_la_monnaie`, `monnaies_acceptees_par_le_lieu`, `ce_qui_manque_pour_exporter` |
| `BaseBillet/models.py`, `BaseBillet/migrations/0232_alter_product_prix_achat.py` | Aide du prix d'achat |
| `tests/pytest/test_plan_comptable_unique.py` | 16 tests ajoutés (51 au total) |
| `tests/e2e/test_admin_plan_comptable.py` | Nouveau : un parcours (menu → trois écrans ; moyen SN sans compte signalé, puis plus après la pose du compte) |

### Chaînes i18n / i18n strings
Workflow i18n à lancer par le mainteneur (pas de `makemessages`). / i18n workflow to be run by the maintainer.
- Nouvelles (source FR) :
  - menu : « Plan comptable », « Comptes des moyens de paiement », « Comptes des monnaies » ;
  - « Plan complet ? » : « Plan complet ? », « Il manque des choses pour faire l'export comptable : », « Régler », « Le plan est complet : l'export est possible », « Le produit « %(nom)s » est vendu, mais il n'a pas de compte. Rangez-le dans une catégorie de caisse reliée à un compte. », « Le moyen de paiement « %(moyen)s » est utilisé, mais il n'a pas de compte. Choisissez son compte. », « La monnaie « %(nom)s » est utilisée, mais elle n'a pas de compte. Choisissez son compte. », « Des ventes ont une TVA à %(taux)s %%, mais le plan n'a pas de compte de TVA à ce taux. Ajoutez-le au plan comptable. », « Les points de vente %(noms)s ont le même code journal « %(code)s ». Donnez à chacun un code différent. », « Donnez un code journal au point de vente « %(nom)s » : son nom ne contient aucune lettre. », pluriel « %(nombre)s règlement est au compte d'attente (471000), moyen de paiement inconnu : à reclasser. » / « %(nombre)s règlements sont au compte d'attente (471000), moyen de paiement inconnu : à reclasser. » ;
  - comptes des monnaies : « ce lieu », « un autre lieu », « fédérée », « Monnaies acceptées par le lieu », « Monnaie », « Origine », « Compte », « Modifier », « Compte du moyen utilisé : %(compte)s », « Choisir un compte propre », « Compte manquant : l'export comptable sera refusé tant que ce compte manque. », « Choisir un compte », « Le lieu n'accepte aucune monnaie. », « Choisissez une monnaie acceptée par le lieu. » ;
  - natures : « Les natures de compte », « Ventes », « TVA », « Trésorerie », « Tiers », « Charges », « Écarts », « Spécial », et les sept phrases d'aide ;
  - prix d'achat : « Prix d'achat en centimes, par unité de vente (kg, litre, pièce) ; 0 = inconnu. »
- Retirée : « Prix d'achat unitaire en centimes. Utilise pour le calcul du benefice estime. / Unit purchase price in cents. Used for estimated profit calculation. »

### Tests vus rouges / Tests seen red
Étape 1 (avant tout code de production, 10 tests) : 10 failed, 35 passed — `KeyError: 'code_journal'` (formulaire du point de vente), `KeyError: <class 'laboutik.models.MappingMonnaie'>` (aucun admin), `NoReverseMatch: 'laboutik_mappingmonnaie_changelist'` ×3, `ImportError: cannot import name 'ce_qui_manque_pour_exporter'` ×3, liste non regroupée (`['TIERS', 'TVA', …, 'TIERS', …]`), aide du prix d'achat ancienne. Tests des décisions (5, ajoutés avant le code) : 15 failed, 35 passed (dont `ImportError: cannot import name 'points_de_vente_sans_code_journal'`).

### Tests verts / Tests green
- `make test ARGS="tests/pytest/test_plan_comptable_unique.py tests/pytest/test_menu_rapports.py"` : 51 passed (×2) ; après les corrections des mutations 13 et 19 : `test_plan_comptable_unique.py` seul, 51 passed.
- `rg -l "dashboard|navigation|CompteComptableAdmin|PointDeVenteAdmin|prix_achat" tests/pytest/` + `test_caracterisation_*.py` + `test_export_comptable.py`, `test_profils_csv_comptable.py`, `test_vente_en_points.py` : 687 passed, sans modification.
- E2E seul, serveur à 200 ×3 : `make e2e ARGS="tests/e2e/test_admin_plan_comptable.py"` : 1 passed ; la correspondance SN du lieu `lespass` est remise (517100).
- `manage.py check` : aucun problème ; `makemigrations --check` : aucun changement.

## E-3 — Les jetons offerts sont une vraie vente hors TVA, leur dette se solde (D8 bis) / Gift tokens are a real sale without VAT, their debt is settled (D8 bis)

**Migration :** Non — **Chaînes i18n :** non.

**Changement de comportement / Behaviour change.** Décision du mainteneur (tronc D8 bis, 2026-10-02, remplace D8) : « solder la dette, voir le compte, avec une écriture sur les ventes, mais hors TVA ; jeton dépensé et crédité visible par le lieu ». / Maintainer decision D8 bis, replacing D8.

### Resume / Summary
**Quoi / What :**
- **Une part payée en jetons cadeau (LG) est une vente ordinaire, TVA 0** : rien d'offert, sans source d'offert, net = total. Caisse (`_creer_lignes_articles_cascade`, ses trois appelants), tireuse (`facturer_tirage`), et toute ligne dont la TVA vient de `_taux_tva_de_la_ligne_de_caisse` (LG → 0, comme FREE et NM). Le règlement LG est un vrai règlement : il compte dans les deux égalités. /
  A token part is an ordinary sale at 0 % VAT; the LG payment counts in both equalities.
- **`MOYENS_OFFERTS` = `[FREE]`** (LG en sort). `MOYENS_HORS_ENCAISSEMENT` le suit (`MOYENS_OFFERTS + [NM]`) : **aucun lecteur, code mort, à retirer en H**. `LigneArticle.SourceOffert.JETONS` est gardé (données anciennes, reprise R), plus écrit ; noté pour H. /
  LG leaves MOYENS_OFFERTS. MOYENS_HORS_ENCAISSEMENT (no reader) and SourceOffert.JETONS kept for H.
- **Vidage de carte** : des jetons perdus annulent la dette. Par transaction de jetons repris (Fedow local `TNF` ou ancien Fedow « TNF ») : un règlement LG positif (monnaie, carte, `fedow_transaction_uuid` en local ou `reference_externe` pour l'ancien Fedow, comme les autres règlements du vidage) et un article « Jetons cadeau repris au vidage » (produit système créé à la demande, nom en constante `NOM_JETONS_CADEAU_REPRIS_AU_VIDAGE`), quantité 1, prix = montant, TVA 0, hors chiffre d'affaires, moyen historique LG, sans carte ni monnaie. Une carte qui n'a que des jetons écrit sa vente `VIDAGE_CARTE` (aucun règlement espèces). /
  Card emptying writes an LG payment and a "gift tokens taken back" item per token transaction; a tokens-only card writes its sale.
- **Plan comptable** : la catégorie « Jetons cadeau repris au vidage » est une catégorie connue du chargeur → 623400 ; `compte_pour_article` : règle 0 par le nom → 623400 ; **nouvelle règle 0 ter** : une ligne payée en jetons (`payment_method == LG`, jusqu'à H) → **707900**, après la règle 0, avant la catégorie. `COMPTE_PAR_DEFAUT` gagne `ventes_reglees_en_jetons` (707900) et `cadeaux_a_la_clientele` (623400). « Plan complet ? » examine une ligne par (produit, monnaie, moyen). /
  Plan: taken-back tokens → 623400 by name; a token-paid line → 707900.
- **Avoirs** : nouvelle règle `ligne_sans_argent_a_rendre(ligne)` (entièrement offerte ou payée en jetons, `ligne_payee_en_jetons`) ; elle décide du champ « Remboursé par » partout (bouton « Avoir », annulations admin réservations / billets, annulation d'adhésion, messages d'annulation de l'utilisateur pour réservation, billet, booking). `ecrire_la_vente_d_avoir_d_une_ligne` : une ligne payée en jetons → aucun moyen exigé, un règlement LG négatif du net (monnaie et carte de la ligne), aucun recrédit de la carte. Le message « Cet article a été offert » de l'écran d'avoir reste réservé à une ligne offerte. /
  Credit notes: a token line needs no "Refunded by" method, gets a negative LG payment, no card credit back.
- **Crowds = don** : la ligne de contribution est à TVA 0 (`crowds/views.py`), quel que soit le taux du lieu. /
  Crowds contribution at 0 % VAT.
- **Démo** : cas 12c (sandwich payé en jetons) à TVA 0.
- **Archive LNE** : rien ne change dans le calcul (le taux 0 suffit) ; le commentaire dit la règle.
- **Ticket client** : la part en jetons (TVA 0) et la part en argent (TVA 20 %) ne se regroupent plus (clé de regroupement par taux) : deux lignes, et la TVA 0 % de la part en jetons apparaît. Accepté (vérité fiscale), code du ticket inchangé.
- **Anciens rapports** (`laboutik/reports.py`, non touché) : regroupés par taux, la part en jetons y fait sa propre ligne à 0 % ; le coût d'achat (`prix_achat × int(qty)`) et le bénéfice changent en conséquence. Accepté (remplacés en F).
- `tarif_vendu_d_ecart_d_encaissement` délègue à la nouvelle `tarif_vendu_d_un_produit_systeme(nom)` (écarts et jetons repris).

**Pourquoi / Why :** fiche E §3.5, tronc D8 bis, brief 05-E-3 et décisions de l'orchestrateur (2026-10-03). / Sheet E §3.5, trunk D8 bis.

**Base de dev à régénérer** : sortir LG de `MOYENS_OFFERTS` fait échouer `verifier_chaine_ventes` sur les ventes déjà scellées avec des jetons (décision du mainteneur : régénérer). / The dev database must be regenerated.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/services_vente.py` | `MOYENS_OFFERTS` = `[FREE]` ; `NOM_JETONS_CADEAU_REPRIS_AU_VIDAGE` ; `ligne_payee_en_jetons`, `ligne_sans_argent_a_rendre` ; avoir d'une ligne en jetons (LG négatif) ; `tarif_vendu_d_un_produit_systeme` |
| `laboutik/views.py` | `_taux_tva_de_la_ligne_de_caisse` (LG → 0) ; cascade sans part offerte ; `_ecrire_la_vente_du_vidage` (jetons écrits, vente « que jetons ») ; commentaires |
| `controlvanne/billing.py` | Part en jetons : vente ordinaire ; import `PaymentMethod` devenu inutile retiré |
| `crowds/views.py` | Contribution à TVA 0 ; import `_taux_tva_de_la_ligne_de_caisse` devenu inutile retiré |
| `laboutik/plan_comptable.py` | Règle 0 (jetons repris → 623400), règle 0 ter (LG → 707900) ; « Plan complet ? » distinct par moyen |
| `laboutik/plan_comptable_par_defaut.py` | `COMPTE_PAR_DEFAUT` (707900, 623400) ; catégorie connue « Jetons cadeau repris au vidage » → 623400 |
| `Administration/admin_tenant.py`, `BaseBillet/views.py`, `BaseBillet/models.py`, `booking/models.py` | `ligne_sans_argent_a_rendre` au lieu de `ligne_entierement_offerte` |
| `Administration/management/commands/_demo_data_v2_ventes.py` | Cas 12c à TVA 0 |
| `laboutik/archivage.py` | Commentaire seulement |
| `tests/pytest/fabriques_vente.py` | Oracle : `MOYENS_OFFERTS_DE_L_ORACLE = [FREE]` écrit dans le test (plus importé du service) |
| tests (voir plus bas) | 11 tests nouveaux (12 cas), 16 tests et 2 fabriques adaptés, 1 test retiré |

### Tests nouveaux / New tests
`test_caisse_ecrit_la_vente.py::test_jetons_vente_ordinaire_tva_zero` ; `test_tireuse_ecrit_la_vente.py::test_tireuse_jetons_vente_ordinaire_tva_zero` ; `test_caisse_vider_carte_deux_fedow.py::test_vider_carte_jetons_ecrits_article_et_reglement_lg`, `::test_vider_carte_seulement_jetons_ecrit_une_vente` ; `test_avoirs_ecrivent_la_vente.py::test_avoir_d_une_part_en_jetons_reglement_lg_negatif_sans_rembourse_par[bouton_avoir|annulation_de_la_reservation]`, `::test_annulation_adhesion_payee_en_jetons_reglement_lg_sans_champ` ; `test_en_ligne_ecrit_la_vente.py::test_crowds_tva_zero` ; `test_vente_service.py::TestServiceDeVente::test_moyens_offerts_ne_contient_que_free` ; `test_plan_comptable_unique.py::…::test_categorie_jetons_repris_reliee_au_623400`, `::test_compte_pour_article_jetons_repris_623400`, `::test_compte_pour_article_jeton_depense_au_707900`.

### Tests existants modifiés (conséquence de D8 bis) / Existing tests changed
| Test | Avant → après | Raison |
|---|---|---|
| `test_caisse_ecrit_la_vente.py::test_jetons_et_monnaie_locale_sur_un_article_parts_entieres` | part jetons offert 300→0, source JETONS→"", net 0→300 ; vente offert 300→0, net 200→500, HT 167→467 | D8 bis : part en jetons vendue (gardé : il fixe les parts entières) |
| `test_caisse_ecrit_la_vente.py::test_jetons_benevoles_part_offerte_hors_tva` → **renommé** `test_jetons_benevoles_puis_cb_part_en_jetons_vendue_hors_tva` | mêmes valeurs (offert 300→0, net 0→300 ; vente net 200→500, HT 167→467) | D8 bis ; nom devenu faux (« part offerte ») |
| `test_caisse_ecrit_la_vente.py::test_archive_lne_part_en_jetons_garde_les_valeurs_d_avant` → **renommé** `test_archive_lne_part_en_jetons_tva_zero` | archive de la part jetons HT "500"→"600", TVA "100"→"0" | Part en jetons à TVA 0 ; nom devenu faux |
| `test_tireuse_ecrit_la_vente.py::test_tirage_jetons_et_monnaie_locale_parts_entieres` (+ docstring du fichier) | part offert 100→0, source JETONS→"", net 0→100 ; vente offert 100→0, net 300→400, HT 250→350 | D8 bis |
| `test_tireuse_ancien_fedow.py::test_tirage_locales_puis_ancien_fedow_une_vente` | offert 100→0, net 300→400 | D8 bis |
| `test_tireuse_ancien_fedow.py::test_ancien_fedow_debite_avant_les_monnaies_locales` (**hors liste fermée**, même conséquence que le précédent) | offert 100→0, net 300→400 | D8 bis |
| `test_avoirs_ecrivent_la_vente.py::vendre_a_la_caisse_une_biere_en_deux_parts` (fabrique) | part jetons sans part offerte ni source, TVA 20→0 | État de départ D8 bis |
| `test_avoirs_ecrivent_la_vente.py::test_avoir_part_en_jetons_de_la_cascade_un_seul_reglement_free` → **renommé** `…_un_seul_reglement_lg` | avoir offert −300→0, net 0→−300, source JETONS→"" ; règlement FREE −300 → LG −300 | Avoir d'une part en jetons ; nom devenu faux |
| `test_caisse_anciens_rapports.py::test_anciens_rapports_inchanges_jetons_cadeau_puis_cb` → **renommé** `test_anciens_rapports_jetons_cadeau_puis_cb_part_en_jetons_a_tva_zero` | détail des ventes : 1 ligne (TTC 500, HT 417, coût 100, bénéfice 317) → 2 lignes triées par taux (0 % : TTC 300, HT 300, coût 0, bénéfice 300 ; 20 % : TTC 200, HT 167, TVA 33, coût 0, bénéfice 167) ; `calculer_tva` 20 % 500/417/83 → 0 % 300/300/0 + 20 % 200/167/33 | Regroupement par taux de l'ancien rapport ; test rendu déterministe (tri par taux) ; nom devenu faux (« inchangés ») |
| `test_total_ht_ligne.py::test_le_ht_des_parts_d_un_paiement_en_cascade` | `[0, 333]` → `[333, 600]` | Part en jetons : HT = net à TVA 0 |
| `test_demo_data_ventes.py::test_seed_ventilation_tva_par_taux` | `par_taux["5.50"]` 10000→4000 | Cas 12c à TVA 0 |
| `test_ticket_client_imprime.py::test_les_parts_d_un_article_sont_regroupees` → **renommé** `…_regroupees_par_taux` | 1 ligne « x3 1500 » → 2 lignes (0.00 : « 1.20 » 600 ; 20.00 : « 1.80 » 900) | Clé de regroupement par taux ; accepté |
| `test_ticket_client_imprime.py::test_une_part_inferieure_a_un_article_n_est_pas_perdue` | `articles[0].total` 1000 → lignes 200 et 800 (total 1000 inchangé) | Idem |
| `test_ticket_client_imprime.py::test_la_tva_du_ticket_porte_sur_le_montant_entier` → **renommé** `…_porte_sur_la_part_en_argent` | `[20.00 : 1250/250/1500]` → `0.00 : 600/0/600` + `20.00 : 750/150/900` | TVA 0 de la part en jetons |
| `test_caisse_vider_carte_deux_fedow.py::test_vider_carte_jetons_cadeau_locaux_repris_sans_argent` → **renommé** `…_sans_argent_reglement_lg` | règlements + (LG, +200, uuid local) ; un article de 200 | Jetons écrits au vidage |
| `test_caisse_vider_carte_deux_fedow.py::test_vider_carte_ancien_fedow_et_local` | `articles.count()` 0 → un article de 50 ; règlements + (LG, +50, référence distante) | Idem |
| `test_caisse_vider_carte_deux_fedow.py::test_vider_carte_seulement_jetons_cadeau_aucune_vente` | **retiré** | Remplacé par `test_vider_carte_seulement_jetons_ecrit_une_vente`, qui dit l'inverse (ses autres vérifications y sont reprises) |
| `test_en_ligne_ecrit_la_vente.py::test_crowds_contribution_vente_en_attente` (liste élargie par l'orchestrateur) | `vat` 10.00→0, `total_ht` 1364→1500 | Crowds = don, sans TVA |
| `tests/pytest/fabriques_vente.py` (oracle) | `MOYENS_OFFERTS` importé → `[FREE]` écrit dans le test | Une mutation de `MOYENS_OFFERTS` doit se voir |

Non touché : `tests/e2e/test_parcours_fedow_reel.py` importe encore `MOYENS_OFFERTS` dans un script (l.810-827) : il suit la valeur de production ; à relancer au `make e2e` de fin de G.

### Tests vus rouges / Tests seen red
Étape 1 (avant tout code de production) : 10 failed — part offerte 300 / 100 au lieu de 0 (caisse, tireuse), aucun règlement LG au vidage, aucune vente « que jetons », TVA crowds 10, `MOYENS_OFFERTS` avec LG, `ImportError` de la constante (plan ×2), état de départ des avoirs refusé (`EgaliteDeVenteRompue`). Rejoué par l'orchestrateur : 10 failed, 304 passed. Les trois tests ajoutés à l'étape 2 sur décision de l'orchestrateur (`test_compte_pour_article_jeton_depense_au_707900`, `test_annulation_adhesion_payee_en_jetons_reglement_lg_sans_champ`, vérifications des uuid du vidage) ont été écrits avec le code : ils sont couverts par les mutations 12, 15, 19, 20 et 5-6.

### Tests verts / Tests green
- Fichiers touchés : `test_caisse_ecrit_la_vente.py`, `test_tireuse_ecrit_la_vente.py`, `test_tireuse_ancien_fedow.py`, `test_caisse_vider_carte_deux_fedow.py`, `test_vente_service.py`, `test_plan_comptable_unique.py`, `test_total_ht_ligne.py`, `test_ticket_client_imprime.py`, `test_caisse_anciens_rapports.py` : 231 passed, 1 failed (`test_ancien_fedow_debite_avant_les_monnaies_locales`, hors liste, adapté) ; `test_tireuse_ancien_fedow.py`, `test_avoirs_ecrivent_la_vente.py`, `test_en_ligne_ecrit_la_vente.py`, `test_demo_data_ventes.py` : 131 passed.
- `test_vente_*.py` + `test_caracterisation_*.py` : 158 passed, sans modification.
- Suite complète `make test ARGS="tests/pytest/ booking/tests/"` : **2688 passed** (16 min 41 s).
- `manage.py check` : aucun problème ; `makemigrations --check` : aucun changement.

## E-4 — Corrections de la grande relecture, tests qui manquaient / Review fixes, missing tests

**Migration :** Non (la migration non commitée `laboutik/0009` est corrigée dans le fichier : aide du numéro de compte ; aucune migration nouvelle). — **Chaînes i18n :** oui (liste plus bas).

### Resume / Summary
**Quoi / What :**
- **« Plan complet ? » ne fait plus une requête par produit vendu** : la liste des lignes lit d'un coup la catégorie du produit et son compte, et la catégorie de la consigne remboursée et son compte (`select_related`) ; les comptes du plan par défaut sont lus en une requête au début de l'appel et passés à `compte_pour_article` par un paramètre nommé facultatif `comptes_du_plan_par_defaut` (les autres appelants ne le passent pas). Mesure : 13 requêtes avec 2 produits vendus, 28 avec 12 avant ; le même nombre après. /
  "Complete plan?" no longer makes one query per sold product.
- **Ventes en points hors de « Plan complet ? »** : la section des produits ne lit que les ventes en euros (`vente__unite="EUR"`). Les autres sections n'en ont pas besoin (règlements `NM` sans compte, TVA 0) : un commentaire le dit. /
  Points sales skipped in the products section.
- **Recharge FED en ligne hors chiffre d'affaires** : `ajouter_article` marque aussi `Product.RECHARGE_CASHLESS_FED` (`E`). /
  Online FED top-up off revenue.
- **L'ancien Z ignore les jetons cadeau repris au vidage** (décision du mainteneur, 2026-10-03) : `laboutik/reports.py` écarte les lignes du produit système `NOM_JETONS_CADEAU_REPRIS_AU_VIDAGE`, une seule exclusion, au queryset de base. /
  The old Z report leaves out the gift tokens taken back at card emptying.
- **Compte du plan par défaut supprimé** : `CompteDuPlanParDefautManquant` (sous-classe de `CompteComptableManquant`, attribut `numero_de_compte`), levée par `_compte_du_plan_par_defaut`. « Plan complet ? » la reconnaît sans lire le message : un seul manque par numéro, « Le compte 707900 du plan par défaut manque. Le bouton « Charger le plan par défaut » le remet. », lien vers le plan, sans la phrase « Rangez-le… » pour le produit. /
  A deleted default account is named, once per number, with the button that restores it.
- **Ordre des natures** : la liste du plan suit l'ordre des phrases d'aide (ventes, TVA, trésorerie, tiers, charges, écarts, spécial), par une expression `Case/When` dans `CompteComptableAdmin.ordering`. /
  Natures ordered like the help sentences.
- **Aide du numéro de compte** : exemples à 6 chiffres (707000 ; docstring : 707000, 530000, 445711). /
  6-digit examples.
- **Accessibilité** : le lien « Régler » porte un `aria-label` « Régler : <phrase du manque> » et un `data-testid`. /
  The "Fix" link carries the missing item's sentence.
- **Code journal en majuscules** : `code_journal_du_point_de_vente` rend le code posé en majuscules ; les collisions comparent des majuscules (`bar` / `BAR`). /
  Journal code uppercased.
- **Doublon de monnaie** : « Cette monnaie a déjà son compte : modifiez la ligne existante. » au lieu du message de Django (`MappingMonnaieForm.Meta.error_messages`). /
  Plain sentence for a duplicate currency.
- **Lisibilité du vidage** : la boucle des jetons repris est sous le `if` qui définit leur tarif (comportement identique). /
  Readability only.

**Pourquoi / Why :** grande relecture Fable de la fiche E (brief 05-E-4) ; décisions du mainteneur et de l'orchestrateur (2026-10-03). / Fable review of sheet E.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/plan_comptable.py` | `CompteDuPlanParDefautManquant` ; `_compte_du_plan_par_defaut` et `compte_pour_article` : paramètre `comptes_du_plan_par_defaut` ; `code_journal_du_point_de_vente` : `.upper()` ; `ce_qui_manque_pour_exporter` : comptes du plan lus une fois, `select_related`, `vente__unite="EUR"` (produits), manque d'un compte du plan par défaut |
| `BaseBillet/services_vente.py` | `ajouter_article` : `RECHARGE_CASHLESS_FED` hors chiffre d'affaires (et le commentaire de `METHODES_CAISSE_HORS_CHIFFRE_AFFAIRES` qui le cite) |
| `laboutik/reports.py` | Exclusion du produit « Jetons cadeau repris au vidage » |
| `laboutik/views.py` | `_ecrire_la_vente_du_vidage` : boucle sous le `if` |
| `Administration/admin/laboutik.py` | `ORDRE_DES_NATURES_COMME_L_AIDE`, `RANG_DE_LA_NATURE_COMME_L_AIDE`, `ordering` ; `MappingMonnaieForm.Meta.error_messages` |
| `Administration/templates/admin/comptable/plan_complet.html` | `aria-label` et `data-testid` du lien « Régler » |
| `laboutik/models.py`, `laboutik/migrations/0009_comptecomptable_numero_de_compte_unique.py` | Aide et docstring à 6 chiffres |
| `tests/pytest/test_plan_comptable_unique.py` | 30 tests ajoutés (84 au total) ; commentaire de la recharge FED ; deux comparaisons en français forcées en français |
| `tests/pytest/test_caisse_anciens_rapports.py` | `test_ancien_z_ignore_les_jetons_cadeau_repris_au_vidage` |

### Chaînes i18n / i18n strings
Workflow i18n à lancer par le mainteneur (pas de `makemessages`). / i18n workflow to be run by the maintainer.
- Nouvelles (source FR) : « Le compte %(numero)s du plan par défaut manque. Le bouton « Charger le plan par défaut » le remet. » ; « Cette monnaie a déjà son compte : modifiez la ligne existante. ».
- Changée : « Numero du compte PCG (ex: 7072000). / PCG account number (e.g. 7072000). » → « Numero du compte PCG (ex: 707000). / PCG account number (e.g. 707000). ».
- `aria-label` du lien : réutilise « Régler » et la phrase du manque (déjà traduites).

### Tests vus rouges / Tests seen red
Étape 1 (avant tout code de production) : **10 failed, 78 passed** — cashless 500 au lieu de 300 (ancien Z) ; `len('7072000') == 6` ; `'bar' == 'BAR'` ; message de Django du doublon ; « Rangez-le… » au lieu de 707900 ; produit vendu en points signalé ; `aria-label` absent (« Régler ») ; 13 → 28 requêtes ; `'CHARGE' == 'VENTE'` ; `hors_chiffre_affaires` False (recharge FED). Rejoué par l'orchestrateur : les mêmes.

### Tests verts / Tests green
- `test_plan_comptable_unique.py`, `test_caisse_anciens_rapports.py`, `test_caisse_vider_carte_deux_fedow.py`, `test_pos_vider_carte.py`, `test_vente_service.py`, `test_caracterisation_*.py` (5), `test_cloture_caisse.py`, `test_cloture_enrichie.py`, `test_cloture_export.py`, `test_hors_argent_offerts.py`, `test_rapports_cheque.py`, `test_ventes_remontent_au_ticket_z.py`, `test_menu_rapports.py`, `test_export_comptable.py` : 275 passed.
- Suite complète `make test ARGS="-q -p no:warnings tests/pytest/ booking/tests/"` : **2719 passed** (17 min 07 s ; 2688 + 31 tests nouveaux).
- Après la suite, trois tests renforcés pour que leurs mutations se voient (deux produits pour « un seul manque par numéro » ; message « Remboursé par » vérifié, ligne relue en base ; session Stripe simulée dans deux tests de garde) : `test_plan_comptable_unique.py` + `test_caisse_anciens_rapports.py`, 88 passed.
- `manage.py check` : aucun problème ; `makemigrations --check --dry-run` : « No changes detected ».

---

## Comment tester (a la main) / Manual test

### Test 1 — le plan est là
1. Admin du lieu `lespass` → Ventes & comptabilité → plan comptable (`/admin/laboutik/comptecomptable/`).
2. Attendu : 20 comptes à 6 chiffres (706000 … 758000), un compte de TVA par taux (445711 = 20 %, 445712 = 10 %, 445713 = 5,5 %, 445714 = 2,1 %).
3. `/admin/laboutik/mappingmoyendepaiement/` : 10 correspondances (CA, CH, CC, SN, SP, SR, TR, LE, LG, UK).

### Test 2 — le bouton n'efface rien
1. Modifier le libellé de 707000 ; relier une catégorie de caisse à 707000 ; supprimer 530000.
2. Liste des comptes → « Charger le plan par défaut ».
3. Attendu : message « 1 compte(s) ajouté(s)… Rien n'a été effacé. » ; 530000 revient ; le libellé de 707000 et le lien de la catégorie sont intacts.

### Test 3 — la commande
```
docker exec lespass_django poetry run python manage.py charger_plan_comptable --schema=lespass
```
Attendu : « 0 compte(s) et 0 correspondance(s) ajoute(s). Rien n'a ete efface. » sur un lieu complet.

### Test 4 (E-1b) — le code journal d'un point de vente
1. Admin → Points de vente → un point de vente → champ « Code journal ».
2. Saisir `BAR1`, puis `bar` : refusé (« Lettres majuscules seules, sans accent »). Saisir `BAR` : accepté. Laisser vide : accepté.

### Test 5 (E-1b) — le FED et les crowds sont reliés
Dans `docker exec -it lespass_django poetry run python manage.py tenant_command shell --schema=lespass` :
```python
from laboutik.models import MappingMonnaie
[(m.asset_uuid, m.compte_de_tresorerie.numero_de_compte) for m in MappingMonnaie.objects.all()]
# Attendu : le ou les uuid du FED → 467000
from BaseBillet.models import CategorieProduct, Product
CategorieProduct.objects.get(name="Financement participatif").compte_comptable.numero_de_compte  # "754000"
[p.categorie_pos.name for p in Product.objects.filter(name__iexact="crowdfunding")]  # ["Financement participatif"]
```

### Test 6 (E-1b) — l'ancien plan a disparu
1. Admin : le menu ne propose plus les écrans « Comptes comptables » / « Mappings moyens de paiement » de l'app comptabilité (les écrans de la caisse restent : `/admin/laboutik/comptecomptable/`).
2. Une clôture → export CSV comptable (Sage 50) : les comptes sont ceux du plan de la caisse (530000, 517100, 706000, 756000, 445711…), plus de numéros à 7 chiffres pour la TVA.

### Test 7 (E-1b) — les règles, à la main
Dans le shell du lieu :
```python
from laboutik.plan_comptable import compte_pour_reglement, journal_pour, collisions_de_codes_journal
compte_pour_reglement("CA", None).numero_de_compte  # "530000"
compte_pour_reglement("NA", None)                   # None
journal_pour(None, "LP")                            # "WEB"
collisions_de_codes_journal()                       # {} sur un lieu sans doublon
```

### Test 8 (E-2) — le menu et les trois écrans
1. Admin du lieu → section « Ventes et comptabilité » (barre latérale) : sous « Lignes comptables », « Plan comptable », « Comptes des moyens de paiement », « Comptes des monnaies ». Vrai aussi avec le module caisse désactivé.
2. Chaque écran montre en tête la carte « Plan complet ? ».
3. Plan comptable : les comptes sont regroupés par nature ; sous le bandeau, la carte « Les natures de compte » donne une phrase par nature (754000 / 756000 : comptes d'association).

### Test 9 (E-2) — « Plan complet ? »
1. Comptes des moyens de paiement → « Stripe (SN) » → vider son compte → enregistrer.
2. En tête : en orange, « Le moyen de paiement « … (SN) » est utilisé, mais il n'a pas de compte » (le lieu a des ventes Stripe réglées), avec « Régler ».
3. Remettre 517100 → la ligne disparaît. Plus rien ne manque : message vert « Le plan est complet : l'export est possible ».
4. Créer un point de vente « 123 » sans code journal : « Donnez un code journal au point de vente « 123 » » ; lui donner `TEST` : la ligne disparaît.

### Test 10 (E-2) — comptes des monnaies
1. Comptes des monnaies : une ligne par monnaie acceptée (nom, origine, compte). La monnaie locale du lieu : « Compte du moyen utilisé : 419100 — … » (neutre). Le FED : « fédérée », 467000.
2. Une monnaie d'un autre lieu, fédérée avec le lieu, sans compte : en orange, « Compte manquant : l'export comptable sera refusé tant que ce compte manque. », lien « Choisir un compte » → formulaire, monnaie déjà choisie ; la liste des comptes ne propose que trésorerie et tiers. Enregistrer → la ligne affiche le compte, plus d'orange.
3. Une monnaie archivée, ou de points / temps / adhésion / badge : pas de ligne.

### Test 11 (E-2) — code journal et prix d'achat
1. Points de vente → un point de vente : champ « Code journal » dans « General », avec son aide.
2. Un produit de caisse : l'aide du prix d'achat dit « en centimes, par unité de vente (kg, litre, pièce) ; 0 = inconnu ».

### Test 12 (E-3) — une bière payée en jetons et en monnaie locale
Préalable : base de dev régénérée (les ventes scellées avant E-3 avec des jetons cassent `verifier_chaine_ventes`).
1. Caisse : une carte avec 3 € de jetons cadeau et 2 € de monnaie locale ; vendre une bière à 5 € (TVA 20 %).
2. Admin → liste des ventes : deux lignes ; la part « Cadeau » (LG) vaut 3 €, TVA 0 %, rien d'offert ; la part monnaie locale 2 €, TVA 20 %.
3. Ticket client : deux lignes (x0.60 3,00 € à 0 % ; x0.40 2,00 € à 20 %), total 5,00 €.

### Test 13 (E-3) — vider une carte avec des jetons
1. Une carte avec seulement 2 € de jetons cadeau : « Vider la carte » → écran de succès, aucun argent rendu.
2. Liste des ventes : une vente « Vidage de carte » avec l'article « Jetons cadeau repris au vidage » (2 €, TVA 0) et un règlement jetons +2 €.
3. Plan comptable → catégories : la catégorie « Jetons cadeau repris au vidage » est reliée au 623400 après « Recharger le plan ».

### Test 14 (E-3) — avoir d'une part payée en jetons
1. Sur la part « Cadeau » du test 12 : bouton « Avoir » → l'écran n'a pas de champ « Remboursé par ».
2. Valider : vente AVOIR avec un règlement jetons −3 € ; le solde de jetons de la carte ne remonte pas.

### Test 15 (E-3) — contribution crowds
1. Contribuer 15 € à une initiative en paiement direct : la ligne de la contribution est à TVA 0 % (HT 15 €), même si le lieu a un taux par défaut.

### Test 16 (E-4) — un compte du plan par défaut supprimé
1. Plan comptable → supprimer 707900. Vendre en caisse un article payé en jetons cadeau.
2. En tête des écrans du plan : « Le compte 707900 du plan par défaut manque. Le bouton « Charger le plan par défaut » le remet. », lien vers le plan.
3. « Charger le plan par défaut » → 707900 revient, le manque disparaît.

### Test 17 (E-4) — ordre du plan, doublon de monnaie, code journal
1. Plan comptable : les ventes d'abord, puis TVA, trésorerie, tiers, charges, écarts, spécial (l'ordre des phrases d'aide).
2. Comptes des monnaies → ajouter un compte à une monnaie qui en a déjà un : « Cette monnaie a déjà son compte : modifiez la ligne existante. ».
3. Lecteur d'écran (ou inspecteur) sur un manque : le lien « Régler » s'annonce « Régler : <la phrase> ».

### Test 18 (E-4) — l'ancien Z et le vidage
1. Vider à la caisse une carte qui n'a que 2 € de jetons cadeau ; puis ticket X (ou Z) du comptoir.
2. Attendu : ni l'article « Jetons cadeau repris au vidage » dans le détail, ni ses 2 € dans le cashless.

### Verifs DB
Dans `docker exec -it lespass_django poetry run python manage.py tenant_command shell --schema=lespass` :
`from laboutik.models import CompteComptable; CompteComptable.objects.count()` → 20 sur un lieu qui n'avait aucun compte.
Tests : `make test ARGS="tests/pytest/test_plan_comptable_unique.py"`.

---

## Mutations (fiche E-1a) / Mutations

Jouées à la main par l'orchestrateur : 7 tuées (2026-10-02) (Edit, `make test ARGS=…`, Edit inverse, `sha256sum` identique). / To be played by the orchestrator.

| # | Mutation (fichier:ligne) | Test attendu en échec | Résultat |
|---|---|---|---|
| 1 | Chargement qui efface : `laboutik/plan_comptable.py:62`, ajouter en tête du `with transaction.atomic():` `MappingMoyenDePaiement.objects.all().delete(); CompteComptable.objects.all().delete()` | `test_chargement_ajoute_ce_qui_manque_sans_rien_effacer`, `test_bouton_de_l_admin_n_efface_plus_le_plan`, `test_chargement_cherche_la_tva_par_taux` | tuée (orchestrateur) |
| 2 | Bouton qui efface encore : `laboutik/views.py:4197`, avant l'appel, `CompteComptable.objects.all().delete()` | `test_bouton_de_l_admin_n_efface_plus_le_plan` | tuée (orchestrateur) |
| 3 | Dédoublonnage qui ne repointe pas : `laboutik/migrations/0008_dedoublonner_les_numeros_de_compte.py:54-59`, supprimer les deux `.update(...)` | `test_dedoublonnage_garde_un_compte_et_repointe_les_liens` | tuée (orchestrateur) |
| 4 | Filet qui charge même si un compte existe : `laboutik/plan_comptable.py:162`, `if le_lieu_a_deja_un_compte:` → `if False:` | `test_filet_ne_fait_rien_si_un_compte_existe` | tuée (orchestrateur) |
| 5 | Compte de TVA cherché par numéro : `laboutik/plan_comptable.py:67`, `if not est_un_compte_de_tva:` → `if True:` (tous les comptes par `get_or_create` sur le numéro) | `test_chargement_cherche_la_tva_par_taux`, `test_chargement_tva_numero_pris_par_un_autre_taux_avertit` | tuée (orchestrateur) |
| 6 | Unicité retirée : sans objet par Edit (la contrainte vit en base, posée par la migration 0009 ; `laboutik/models.py:2050` seul ne change pas la base) | `test_numero_de_compte_unique` | vu rouge avant 0009 (« IntegrityError not raised ») |
| 7 | Catégories connues non reliées : `laboutik/plan_comptable.py:135-136`, filtre `compte_comptable__isnull=True` → `compte_comptable__isnull=False` | `test_categories_d_ecart_reliees_si_elles_existent` | tuée (orchestrateur) |
| 8 | Migration de chargement qui ne fait rien : `laboutik/migrations/0010_charger_le_plan_comptable_par_defaut.py:47`, `if le_lieu_a_deja_un_compte:` → `if True:` | `test_migration_charge_le_plan_si_aucun_compte` | tuée (orchestrateur) |

## Mutations (fiche E-1b) / Mutations

Numéros de ligne de l'état livré par E-1b (`laboutik/plan_comptable.py` a bougé depuis le tableau E-1a). Jouées à la main par l'orchestrateur : toutes tuées (24 mutations jouées le 2026-10-02, SUIVI §6). / Line numbers of the E-1b state.

| # | Mutation (fichier:ligne) | Test attendu en échec | Résultat |
|---|---|---|---|
| 1 | Ordre monnaie / moyen inversé : `laboutik/plan_comptable.py:341-344`, déplacer le bloc « compte de la monnaie » après la lecture du moyen (l.360-370) | `test_compte_de_la_monnaie_prioritaire_sur_le_moyen` | tuée (orchestrateur) |
| 2 | Repli sur le moyen pour toute monnaie : `laboutik/plan_comptable.py:353`, `if not _la_monnaie_est_celle_du_lieu(asset_uuid):` → `if False:` | `test_monnaie_d_un_autre_lieu_sans_compte_refus` | tuée (orchestrateur) |
| 3 | `SF` par le moyen : `laboutik/plan_comptable.py:346`, `if moyen == PaymentMethod.STRIPE_FED:` → `if False:` | `test_fed_ses_deux_uuid_vont_au_467` (SF sans monnaie) | tuée (orchestrateur) |
| 4 | Compte de moyen vide accepté : `laboutik/plan_comptable.py:368`, `is None` → `is False` | `test_correspondance_de_moyen_au_compte_vide_erreur` | tuée (orchestrateur) |
| 5 | Journal toujours `WEB` : `laboutik/plan_comptable.py:445`, `JOURNAL_PAR_ORIGINE.get(origine)` → `"WEB"` | `test_journal_par_defaut_selon_origine` | tuée (orchestrateur) |
| 6 | Origine du point de vente ignorée : `laboutik/plan_comptable.py:442`, `if point_de_vente is not None:` → `if False:` | `test_journal_du_point_de_vente_lettres_seules` | tuée (orchestrateur) |
| 7 | Nom sans lettre accepté : `laboutik/plan_comptable.py:417`, `if code_derive == "":` → `if False:` | `test_journal_d_un_point_de_vente_au_nom_sans_lettre_erreur` | tuée (orchestrateur) |
| 8 | Collision non signalée : `laboutik/plan_comptable.py:474`, `> 1` → `> 2` | `test_code_journal_collision_signalee` | tuée (orchestrateur) |
| 9 | Catégorie avant la règle 0 : `laboutik/plan_comptable.py:589-592` (bloc « 2. La catégorie »), déplacer avant l.542 | `test_compte_article_ordre_des_regles` (recharge en 7xx, `VR`), `test_ecarts_758_et_658` | tuée (orchestrateur) |
| 10 | Un seul compte pour les deux écarts : `laboutik/plan_comptable.py:549`, `"ecart_recu_en_moins"` → `"ecart_recu_en_plus"` | `test_ecarts_758_et_658` | tuée (orchestrateur) |
| 11 | Recharge `E` oubliée : `laboutik/plan_comptable.py:484`, retirer `Product.RECHARGE_CASHLESS_FED` | `test_compte_article_ordre_des_regles` (recharge FED) | tuée (orchestrateur) |
| 12 | `TM` / `FD` acceptés avec une catégorie : `laboutik/plan_comptable.py:570-574`, déplacer après le bloc « 2. La catégorie » | `test_compte_article_sans_regle_refus` | tuée (orchestrateur) |
| 13 | `CR` par la catégorie du retour : `laboutik/plan_comptable.py:577`, `== Product.RETOUR_CONSIGNE` → `== "ZZ"` | `test_compte_article_ordre_des_regles` (attendu 419600), `test_retour_de_consigne_sans_compte_de_consigne_erreur` | tuée (orchestrateur) |
| 14 | TVA cherchée par numéro dans le CSV : `comptabilite/csv_comptable.py:171-174`, filtre → `numero_de_compte=COMPTES_DEFAUT[compte_key]` | `test_tva_cherchee_par_taux` | tuée (orchestrateur) |
| 15 | Le CSV ne lit plus les correspondances de la caisse : `comptabilite/csv_comptable.py:84`, `moyen_de_paiement=code` → `moyen_de_paiement="ZZ"` | `test_csv_comptable_lit_le_plan_de_la_caisse` | tuée (orchestrateur) |
| 16 | FED non relié par le chargeur : `laboutik/plan_comptable.py:208` et `:212`, supprimer les deux `append` | `test_fed_ses_deux_uuid_vont_au_467` | tuée (orchestrateur) |
| 17 | FED non relié par la migration : `laboutik/migrations/0012_relier_le_fed_au_compte_du_reseau.py:77`, `asset_uuid=uuid_du_fed` → `asset_uuid=uuid.uuid4()` (avec `import uuid`) | `test_migration_relie_le_fed_au_467` | tuée (orchestrateur) |
| 18 | Produits crowds non rangés par le chargeur : `laboutik/plan_comptable.py:181`, `categorie_pos__isnull=True` → `categorie_pos__isnull=False` | `test_chargement_cree_la_categorie_des_crowds_et_y_range_leurs_produits` | tuée (orchestrateur) |
| 19 | Produit crowds créé sans catégorie : `crowds/views.py:174`, `categorie_pos=categorie_financement_participatif` → `categorie_pos=None` | `test_produit_crowds_cree_dans_la_categorie_du_financement_participatif` | tuée (orchestrateur) |
| 20 | Catégorie crowds existante laissée sans compte (vue) : `crowds/views.py:168`, `elif ... is None:` → `elif False:` | `test_produit_crowds_cree_avec_une_categorie_existante_sans_compte` | tuée (orchestrateur) |
| 21 | Migration crowds qui ne relie pas une catégorie existante : `laboutik/migrations/0013_ranger_les_crowds_dans_le_financement_participatif.py:78`, `elif ... is None:` → `elif False:` | `test_migration_relie_la_categorie_des_crowds_et_range_leurs_produits` | tuée (orchestrateur) |
| 22 | Migration crowds qui ne range pas les produits : `0013_…py:86`, `categorie_pos__isnull=True` → `categorie_pos__isnull=False` | `test_migration_cree_la_categorie_des_crowds_si_elle_manque`, `test_migration_relie_la_categorie_des_crowds_et_range_leurs_produits` | tuée (orchestrateur) |
| 23 | Code journal sans validation : `laboutik/models.py:881`, `regex=r"^[A-Z]+$"` → `regex=r".*"` | `test_code_journal_refuse_autre_chose_que_des_lettres` | tuée (orchestrateur) |

## Mutations (fiche E-2) / Mutations

Numéros de ligne de l'état joué par l'orchestrateur. Depuis, `laboutik/plan_comptable.py` a perdu une ligne après la l.722 (code mort `compte_manquant` retiré, voir 19). Jouées à la main (Edit, `make test`, Edit inverse, sha256 identique) : 22 tuées par l'orchestrateur ; 13 d'abord survivante, tuée après l'ajout d'un test ; 19 sans objet (code mort retiré), remplacée par 19 bis, tuée. / Line numbers of the state played by the orchestrator.

| # | Mutation (fichier:ligne) | Test attendu en échec | Résultat |
|---|---|---|---|
| 1 | Filet non appelé : `laboutik/plan_comptable.py:857`, supprimer `s_assurer_que_le_plan_existe()` | `test_plan_complet_appelle_le_filet` | tuée (orchestrateur) |
| 2 | Produit vendu sans compte oublié : `laboutik/plan_comptable.py:884`, `except CompteComptableManquant:` → `except ZeroDivisionError:` | `test_plan_complet_signale_ce_qui_manque` (cas produit, erreur levée) | tuée (orchestrateur) |
| 3 | Vente en attente comptée : `laboutik/plan_comptable.py:872`, `filter(vente__statut=Vente.Statut.REGLEE)` → `filter(vente__isnull=False)` | `test_plan_complet_signale_ce_qui_manque` (cas produit : 2 manques) | tuée (orchestrateur) |
| 4 | Moyen sans compte oublié : `laboutik/plan_comptable.py:948`, bloc `manques.append(...)` du moyen → `pass` | `test_plan_complet_signale_ce_qui_manque` (cas moyen), `test_plan_complet_affiche_les_manques_en_tete_des_trois_ecrans` | tuée (orchestrateur) |
| 5 | Monnaie sans compte oubliée : `laboutik/plan_comptable.py:932`, bloc `manques.append(...)` de la monnaie → `pass` | `test_plan_complet_signale_ce_qui_manque` (cas monnaie) | tuée (orchestrateur) |
| 6 | Monnaie signalée comme un moyen : `laboutik/plan_comptable.py:920-927`, `la_faute_vient_de_la_monnaie = (…)` → `la_faute_vient_de_la_monnaie = False` | `test_plan_complet_signale_ce_qui_manque` (cas monnaie : nom absent, lien des moyens) | tuée (orchestrateur) |
| 7 | TVA sans compte oubliée : `laboutik/plan_comptable.py:974`, `if le_plan_a_ce_taux:` → `if True:` | `test_plan_complet_signale_ce_qui_manque` (cas TVA) | tuée (orchestrateur) |
| 8 | TVA 0 exigée : `laboutik/plan_comptable.py:964`, supprimer `.exclude(vat=0)` | `test_plan_complet_tva_zero_sans_compte_de_tva` | tuée (orchestrateur) |
| 9 | Collision oubliée : `laboutik/plan_comptable.py:988`, `collisions_de_codes_journal().items()` → `{}.items()` | `test_plan_complet_signale_ce_qui_manque` (cas collision), `test_plan_complet_collision_et_nom_sans_lettre_listes_ensemble` | tuée (orchestrateur) |
| 10 | Nom sans lettre oublié : `laboutik/plan_comptable.py:1004`, `points_de_vente_sans_code_journal()` → `[]` | `test_plan_complet_signale_ce_qui_manque` (cas nom sans lettre), `test_plan_complet_collision_et_nom_sans_lettre_listes_ensemble` | tuée (orchestrateur) |
| 11 | Nom sans lettre qui cache la collision : `laboutik/plan_comptable.py:488`, `continue` → `raise` | `test_collisions_de_codes_journal_ignore_un_nom_sans_lettre`, `test_plan_complet_collision_et_nom_sans_lettre_listes_ensemble` | tuée (orchestrateur) |
| 12 | Rappel du 471000 oublié : `laboutik/plan_comptable.py:1024`, `> 0` → `> 99` | `test_plan_complet_signale_ce_qui_manque` (cas 471000) | tuée (orchestrateur) |
| 13 | Produit signalé deux fois : `laboutik/plan_comptable.py:880-881` (état actuel), supprimer `if produit.pk in produits_deja_signales: continue` | `test_plan_complet_meme_produit_vendu_dans_deux_monnaies_un_seul_manque` (ajouté : même produit vendu en euros et en monnaie du lieu ; le `DISTINCT ON (produit, monnaie)` ne suffit plus) | survivante (orchestrateur), puis **tuée** après l'ajout du test : `AssertionError: ["Le produit « … Planche deux monnaies … » …", "Le produit « … Planche deux monnaies … » …"]` (1 failed, 50 passed) ; sha256 identique |
| 14 | Monnaie de l'ancien Fedow absente de l'écran : `laboutik/plan_comptable.py:804`, `for monnaie in monnaies_ancien_fedow:` → `for monnaie in []:` | `test_comptes_des_monnaies_liste_les_monnaies_acceptees`, `test_comptes_des_monnaies_orange_seulement_pour_une_monnaie_d_ailleurs` | tuée (orchestrateur) |
| 15 | Monnaies fédérées de l'ancien Fedow absentes : `laboutik/plan_comptable.py:799`, supprimer `\| Q(federated_with__schema_name=…)` | `test_comptes_des_monnaies_liste_les_monnaies_acceptees` | tuée (orchestrateur) |
| 16 | Monnaies archivées montrées : `laboutik/plan_comptable.py:794`, supprimer `archive=False,` | `test_comptes_des_monnaies_sans_archivees_ni_monnaies_sans_argent` | tuée (orchestrateur) |
| 17 | Monnaies sans argent montrées : `laboutik/plan_comptable.py:665`, `["TLF", "TNF", "FED"]` → `["TLF", "TNF", "FED", "FID", "TIM", "SUB", "BDG"]` | `test_comptes_des_monnaies_sans_archivees_ni_monnaies_sans_argent` | tuée (orchestrateur) |
| 18 | Monnaie du lieu en orange : `laboutik/plan_comptable.py:726`, `est_du_lieu and moyen_de_repli is not None` → `False` | `test_comptes_des_monnaies_orange_seulement_pour_une_monnaie_d_ailleurs` | tuée (orchestrateur) |
| 19 | Monnaie sans compte jamais en orange : `laboutik/plan_comptable.py:737`, `compte_manquant = True` → `compte_manquant = False` | — | survivante (orchestrateur) : `compte_manquant` n'était lu par personne (le gabarit décide l'orange par `correspondance` et `compte_du_moyen`). **Code mort retiré** ; remplacée par 19 bis |
| 19 bis | Monnaie sans compte jamais en orange (gabarit) : `Administration/templates/admin/comptable/monnaies_changelist_before.html:43`, `{% elif ligne.compte_du_moyen %}` → `{% elif True %}` | `test_comptes_des_monnaies_liste_les_monnaies_acceptees`, `test_comptes_des_monnaies_orange_seulement_pour_une_monnaie_d_ailleurs` (ils exigent `data-testid="monnaie-sans-compte-<uuid>"` et la phrase) | **tuée** : `assert 0 == 1` (alerte absente), `AssertionError: []` (alerte du FED absente) (2 failed, 49 passed) ; sha256 identique |
| 20 | Formulaire des monnaies qui propose tout : `Administration/admin/laboutik.py:2013`, `nature_du_compte__in=…` → `nature_du_compte__isnull=False` | `test_comptes_des_monnaies_formulaire_ne_propose_que_tresorerie_et_tiers` | tuée (orchestrateur) |
| 21 | Entrée de menu manquante : `Administration/admin/dashboard.py:890-897`, supprimer l'entrée « Comptes des monnaies » | `test_menu_ventes_et_comptabilite_a_les_trois_ecrans`, E2E `test_menu_mene_aux_ecrans_du_plan_et_plan_complet_suit_le_compte_pose` | tuée (orchestrateur) |
| 22 | Plan non regroupé par nature : `Administration/admin/laboutik.py:1819`, `('nature_du_compte', 'numero_de_compte')` → `('numero_de_compte',)` | `test_plan_comptable_regroupe_par_nature_avec_une_aide_par_nature` | tuée (orchestrateur) |
| 23 | Composant absent d'un écran : `Administration/templates/admin/comptable/moyens_changelist_before.html:11`, supprimer l'`include` | `test_plan_complet_rien_a_signaler_message_vert`, `test_plan_complet_affiche_les_manques_en_tete_des_trois_ecrans` | tuée (orchestrateur) |
| 24 | Code journal absent du formulaire : `Administration/admin/laboutik.py:175`, supprimer `'code_journal',` | `test_code_journal_dans_le_formulaire_du_point_de_vente` | tuée (orchestrateur) |

## Mutations (fiche E-3) / Mutations

Numéros de ligne de l'état livré par E-3. Jouées à la main par l'orchestrateur : 22 tuées, n° 23 inatteignable et n° 24 équivalente acceptées (2026-10-03) (Edit, `make test ARGS=…`, Edit inverse, `sha256sum` identique). / To be played by the orchestrator.

| # | Mutation (fichier:ligne) | Test attendu en échec | Résultat |
|---|---|---|---|
| 1 | `LG` laissé dans `MOYENS_OFFERTS` : `BaseBillet/services_vente.py:68`, `[PaymentMethod.FREE]` → `[PaymentMethod.LOCAL_GIFT, PaymentMethod.FREE]` | `test_moyens_offerts_ne_contient_que_free` ; et l'encaissement de toute vente avec une part en jetons (`EgaliteDeVenteRompue`) : `test_jetons_vente_ordinaire_tva_zero`, `test_tireuse_jetons_vente_ordinaire_tva_zero`, tests du vidage | tuée (orchestrateur) |
| 2 | TVA des jetons non nulle : `laboutik/views.py:6270`, retirer `PaymentMethod.LOCAL_GIFT,` | `test_jetons_vente_ordinaire_tva_zero`, `test_tireuse_jetons_vente_ordinaire_tva_zero`, `test_archive_lne_part_en_jetons_tva_zero`, `test_le_ht_des_parts_d_un_paiement_en_cascade`, tests du ticket | tuée (orchestrateur) |
| 3 | Part offerte des jetons gardée (caisse) : `laboutik/views.py:6859`, ajouter à l'appel `part_offerte=argent_reel_de_la_part_en_centimes if payment_method_code == PaymentMethod.LOCAL_GIFT else 0,` | `test_jetons_vente_ordinaire_tva_zero`, `test_jetons_et_monnaie_locale_sur_un_article_parts_entieres` | tuée (orchestrateur) |
| 4 | Part offerte des jetons gardée (tireuse) : `controlvanne/billing.py:650`, même ajout avec `montant_a` | `test_tireuse_jetons_vente_ordinaire_tva_zero`, `test_tirage_jetons_et_monnaie_locale_parts_entieres` | tuée (orchestrateur) |
| 5 | Jetons sautés au vidage (local) : `laboutik/views.py:2004-2015`, supprimer l'`append` (garder `continue`) | `test_vider_carte_jetons_ecrits_article_et_reglement_lg`, `test_vider_carte_jetons_cadeau_locaux_repris_sans_argent_reglement_lg` | tuée (orchestrateur) |
| 6 | Jetons sautés au vidage (ancien Fedow) : `laboutik/views.py:2050`, `jetons_cadeau_repris.append(…)` → `pass` | `test_vider_carte_jetons_ecrits_article_et_reglement_lg`, `test_vider_carte_ancien_fedow_et_local` | tuée (orchestrateur) |
| 7 | Vente « que jetons » non écrite : `laboutik/views.py:2059`, `rien_n_est_repris = argent_rendu_en_centimes == 0 and …` → `rien_n_est_repris = argent_rendu_en_centimes == 0` | `test_vider_carte_seulement_jetons_ecrit_une_vente` | tuée (orchestrateur) |
| 8 | Article des jetons repris non écrit : `laboutik/views.py:2097`, `for jeton_cadeau_repris in jetons_cadeau_repris:` → `for jeton_cadeau_repris in []:` | tests du vidage avec jetons (égalité rompue) | tuée (orchestrateur) |
| 9 | Règlement espèces nul écrit : `laboutik/views.py:2114`, `if argent_rendu_en_centimes != 0:` → `if True:` | `test_vider_carte_seulement_jetons_ecrit_une_vente` (montant 0 refusé) | tuée (orchestrateur) |
| 10 | Avoir de jetons qui exige « Remboursé par » : `BaseBillet/services_vente.py:735`, `ligne_entierement_offerte(ligne) or ligne_payee_en_jetons(ligne)` → `ligne_entierement_offerte(ligne)` | `test_avoir_d_une_part_en_jetons_reglement_lg_negatif_sans_rembourse_par` (×2), `test_annulation_adhesion_payee_en_jetons_reglement_lg_sans_champ`, `test_avoir_part_en_jetons_de_la_cascade_un_seul_reglement_lg` | tuée (orchestrateur) |
| 11 | Avoir de jetons réglé comme de l'argent : `BaseBillet/services_vente.py:902`, `if net_rendu != 0 and ligne_payee_en_jetons(ligne):` → `if False:` | mêmes tests (moyen obligatoire, refus) | tuée (orchestrateur) |
| 12 | Avoir LG sans monnaie ni carte : `BaseBillet/services_vente.py:907-908`, `asset=ligne.asset, carte=ligne.carte` → `asset=None, carte=None` | `test_avoir_d_une_part_en_jetons_reglement_lg_negatif_sans_rembourse_par`, `test_annulation_adhesion_payee_en_jetons_reglement_lg_sans_champ` | tuée (orchestrateur) |
| 13 | Écran « Avoir » sur la seule règle « offert » : `Administration/admin_tenant.py:2189`, `ligne_sans_argent_a_rendre(` → `ligne_entierement_offerte(` | `…[bouton_avoir]`, `test_avoir_part_en_jetons_de_la_cascade_un_seul_reglement_lg` | tuée (orchestrateur) |
| 14 | Écran d'annulation admin : `Administration/admin_tenant.py:3397`, `ligne_sans_argent_a_rendre(ligne)` → `ligne_entierement_offerte(ligne)` | `…[annulation_de_la_reservation]` | tuée (orchestrateur) |
| 15 | Annulation d'adhésion : `BaseBillet/views.py:4939-4941`, `ligne_sans_argent_a_rendre(ligne_du_dernier_paiement)` → `False` | `test_annulation_adhesion_payee_en_jetons_reglement_lg_sans_champ` | tuée (orchestrateur) |
| 16 | TVA crowds non nulle : `crowds/views.py:1000`, `Decimal("0")` → `Decimal("10")` | `test_crowds_tva_zero`, `test_crowds_contribution_vente_en_attente` | tuée (orchestrateur) |
| 17 | Catégorie des jetons repris non reliée : `laboutik/plan_comptable_par_defaut.py:257`, `"623400"` → `"707000"` | `test_categorie_jetons_repris_reliee_au_623400` | tuée (orchestrateur) |
| 18 | Règle 0 des jetons repris absente : `laboutik/plan_comptable.py:603`, `if produit.name == NOM_JETONS_CADEAU_REPRIS_AU_VIDAGE:` → `if False:` | `test_compte_pour_article_jetons_repris_623400` (707900 par la règle 0 ter) | tuée (orchestrateur) |
| 19 | Règle 0 ter absente : `laboutik/plan_comptable.py:637`, `if ligne.payment_method == PaymentMethod.LOCAL_GIFT:` → `if False:` | `test_compte_pour_article_jeton_depense_au_707900` | tuée (orchestrateur) |
| 20 | Règle 0 ter après la catégorie : `laboutik/plan_comptable.py:630-638`, déplacer le bloc après celui de l.653 (« 2. La catégorie ») | `test_compte_pour_article_jeton_depense_au_707900` (catégorie 707000) | tuée (orchestrateur) |
| 21 | Oracle qui suit la production : `tests/pytest/fabriques_vente.py:59`, `[PaymentMethod.FREE]` → `[PaymentMethod.LOCAL_GIFT, PaymentMethod.FREE]` | tous les tests à part en jetons (2ᵉ égalité de l'oracle) | tuée (orchestrateur) |
| 22 | Démo 12c taxée : `Administration/management/commands/_demo_data_v2_ventes.py:608`, `vat=Decimal("0")` → `vat=Decimal("5.50")` | `test_seed_ventilation_tva_par_taux` | tuée (orchestrateur) |
| 23 | Messages d'annulation de l'utilisateur (`BaseBillet/models.py:3350`, `:3521`, `booking/models.py:666`) : sans test (aucun parcours n'écrit une réservation, un billet ou un booking payé en jetons) | — | non jouable (chemin inatteignable) |
| 24 | « Plan complet ? » sans le moyen : `laboutik/plan_comptable.py:897-898`, retirer `"payment_method"` | — | probablement équivalente : une part en jetons porte la monnaie TNF, déjà distincte des autres monnaies |

## Mutations (fiche E-4) / Mutations

Numéros de ligne de l'état livré par E-4 ; chaque ancre est unique dans son fichier (`grep -cF` = 1). Jouées à la main par l'orchestrateur (Edit, `make test ARGS=…`, Edit inverse, `sha256sum` identique). Tests dans `tests/pytest/test_plan_comptable_unique.py` sauf mention. / To be played by the orchestrator.

**Corrections / Fixes**

| # | Fichier:ligne — ancre exacte → remplacement | Test attendu en échec | Résultat |
|---|---|---|---|
| 1 | `laboutik/plan_comptable.py:970` — `"pricesold__productsold__product__categorie_pos__compte_comptable",` → `"pricesold__productsold__product",` | `test_plan_complet_nombre_de_requetes_ne_grandit_pas` | tuée (orchestrateur) |
| 2 | `laboutik/plan_comptable.py:983` — `compte_pour_article(ligne, comptes_du_plan_par_defaut)` → `compte_pour_article(ligne)` | `test_plan_complet_nombre_de_requetes_ne_grandit_pas` | tuée (orchestrateur) |
| 3 | `laboutik/plan_comptable.py:967` — `vente__unite="EUR",` → (ligne vide) | `test_plan_complet_ignore_les_ventes_en_points` | tuée (orchestrateur) |
| 4 | `BaseBillet/services_vente.py:497` — `in [Product.RECHARGE_CASHLESS, Product.RECHARGE_CASHLESS_FED]` → `in [Product.RECHARGE_CASHLESS]` | `test_recharge_fed_en_ligne_hors_chiffre_affaires` | tuée (orchestrateur) |
| 5 | `laboutik/reports.py:207` — `pricesold__productsold__product__name=NOM_JETONS_CADEAU_REPRIS_AU_VIDAGE,` → `pricesold__productsold__product__name="ZZ",` | `test_caisse_anciens_rapports.py::…::test_ancien_z_ignore_les_jetons_cadeau_repris_au_vidage` | tuée (orchestrateur) |
| 6 | `laboutik/plan_comptable.py:984` — `except CompteDuPlanParDefautManquant as erreur:` → `except ZeroDivisionError as erreur:` | `test_plan_complet_compte_du_plan_par_defaut_supprime` (phrase « Rangez-le… », lien des catégories) | tuée (orchestrateur) |
| 7 | `laboutik/plan_comptable.py:991` — `if numero_manquant in numeros_du_plan_par_defaut_deja_signales:` → `if False:` | `test_plan_complet_compte_du_plan_par_defaut_supprime` (deux manques) | tuée (orchestrateur) |
| 8 | `Administration/admin/laboutik.py:1850` — `ordering = (RANG_DE_LA_NATURE_COMME_L_AIDE.asc(), 'numero_de_compte')` → `ordering = ('nature_du_compte', 'numero_de_compte')` | `test_plan_comptable_ordonne_par_nature_comme_l_aide` | tuée (orchestrateur) |
| 9 | `laboutik/models.py:2077` — `"Numero du compte PCG (ex: 707000). "` → `"Numero du compte PCG (ex: 7072000). "` | `test_aide_du_numero_de_compte_six_chiffres` (et `makemigrations --check` non vide) | tuée (orchestrateur) |
| 10 | `Administration/templates/admin/comptable/plan_complet.html:36` — `aria-label="{% translate 'Régler' %} : {{ manque.phrase }}"` → (ligne vide) | `test_plan_complet_lien_regler_porte_la_phrase_du_manque` | tuée (orchestrateur) |
| 11 | `laboutik/plan_comptable.py:453` — `return point_de_vente.code_journal.upper()` → `return point_de_vente.code_journal` | `test_code_journal_en_majuscules` | tuée (orchestrateur) |
| 12 | `Administration/admin/laboutik.py:1984` — `'unique': _("Cette monnaie a déjà son compte : modifiez la ligne existante."),` → `'unique_zz': _("Cette monnaie a déjà son compte : modifiez la ligne existante."),` | `test_formulaire_monnaie_doublon_phrase_falc` | tuée (orchestrateur) |
| 13 | `laboutik/views.py:2097` — `        for jeton_cadeau_repris in jetons_cadeau_repris:` → `        for jeton_cadeau_repris in jetons_cadeau_repris[:0]:` (la correction 11 est une remise en forme sans effet : la mutation prouve que la boucle déplacée tourne toujours) | `test_caisse_vider_carte_deux_fedow.py::test_vider_carte_jetons_ecrits_article_et_reglement_lg`, `test_ancien_z_ignore_les_jetons_cadeau_repris_au_vidage` (égalité rompue) | tuée (orchestrateur) |

**Gardes couvertes / Covered guards**

| # | Fichier:ligne — ancre exacte → remplacement | Test attendu en échec | Résultat |
|---|---|---|---|
| 14 | `BaseBillet/services_vente.py:592` — `if vente_avoir.nature != Vente.Nature.AVOIR:` → `if False:` | `test_article_d_avoir_hors_d_une_vente_avoir_refuse` | tuée (orchestrateur) |
| 15 | `BaseBillet/services_vente.py:599` — `quantite_hors_bornes = quantite <= 0 or quantite > quantite_vendue` → `quantite_hors_bornes = False` | `test_article_d_avoir_quantite_hors_bornes_refusee` | tuée (orchestrateur) |
| 16 | `BaseBillet/services_vente.py:652` — `metadonnees_de_l_avoir.update(ligne_d_origine.metadata)` → `pass` | `test_article_d_avoir_recopie_les_metadonnees_de_la_ligne_d_origine` | tuée (orchestrateur) |
| 17 | `BaseBillet/services_vente.py:856` — `vente_d_origine is not None and vente_d_origine.statut != Vente.Statut.REGLEE` → `False` | `test_avoir_vente_d_origine_pas_reglee_refuse_par_le_service` (et `test_avoirs_ecrivent_la_vente.py::test_avoir_vente_d_origine_pas_reglee_refuse`) | tuée (orchestrateur) par le test du service ; le test de l'écran admin passe sous la mutation (le formulaire refuse avant le service) |
| 18 | `BaseBillet/services_vente.py:915` — `if not moyen_de_l_argent_rendu:` → `if False:` | `test_avoir_argent_a_rendre_sans_moyen_refuse_par_le_service` (le message « Remboursé par » manque : le refus vient d'`ajouter_reglement`) | tuée (orchestrateur) |
| 19 | `PaiementStripe/utils.py:104` — `if specified_quantity == 0:` → `if False:` | `test_remboursement_stripe_quantite_zero_refusee` | tuée (orchestrateur) |
| 20 | `PaiementStripe/utils.py:110` — `if not paiement.lignearticles.filter(pk=ligne_article.pk).exists():` → `if False:` | `test_remboursement_stripe_ligne_d_un_autre_paiement_refusee` | tuée (orchestrateur) |
| 21 | `PaiementStripe/utils.py:128` — `if not ligne_remboursable:` → `if False:` | `test_remboursement_stripe_ligne_non_remboursable_sautee` | tuée (orchestrateur) |
| 22 | `PaiementStripe/utils.py:286` — `somme_des_parts_offertes_rendues - part_offerte_deja_tracee` → `somme_des_parts_offertes_rendues` | `test_remboursement_stripe_part_offerte_jamais_tracee_deux_fois` (`EgaliteDeVenteRompue`) | tuée (orchestrateur) |
| 23 | `PaiementStripe/utils.py:347` — `except InvalidRequestError as e:` → `except ZeroDivisionError as e:` | `test_remboursement_stripe_refus_de_stripe_rien_n_est_ecrit` (`InvalidRequestError` au lieu de `ValueError`) | tuée (orchestrateur) |
| 24 | `laboutik/plan_comptable.py:663` — `if compte_de_la_monnaie is None:` → `if False:` | `test_virement_recu_dont_la_monnaie_n_a_pas_de_compte_erreur` | tuée (orchestrateur) |
| 25 | `laboutik/plan_comptable.py:761` — `monnaie_ancien_fedow = AssetFedowPublic.objects.filter(uuid=asset_uuid).first()` → `monnaie_ancien_fedow = None` | `test_nom_de_la_monnaie_ancien_fedow_puis_uuid_inconnu` | tuée (orchestrateur) |
| 26 | `laboutik/plan_comptable.py:1053` — `if asset_uuid in monnaies_deja_signalees:` → `if False:` | `test_plan_complet_une_monnaie_et_un_moyen_signales_une_seule_fois` | tuée (orchestrateur) |
| 27 | `laboutik/plan_comptable.py:1068` — `if moyen in moyens_deja_signales:` → `if False:` | `test_plan_complet_une_monnaie_et_un_moyen_signales_une_seule_fois` | tuée (orchestrateur) |

**27 mutations jouées à la main par l'orchestrateur (2026-10-03), 27 tuées, sha256 des 8 fichiers identiques après coup.** Raisons vérifiées sur les n° 1 (13 → 23 requêtes), 6 (phrase « Rangez-le… »), 22 (`EgaliteDeVenteRompue` −1000 / −500), 23 (`InvalidRequestError` non attrapée).

Non couvert par une mutation propre : les tests « qui manquaient » sur du code déjà muté ailleurs (`compte_pour_reglement` LG : E-1b n° 2 ; chargeur sur l'ancien bar_resto : E-1a n° 5 ; vidage de jetons d'un autre lieu : E-1b n° 2 et E-3 n° 6 ; formulaire des monnaies : liste, monnaie gardée, refus ; écran pré-rempli : comportement de l'admin Django).
