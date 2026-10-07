# Verrou de moteur : les lieux existants restent sur l'ancien Fedow / Engine lock: existing venues stay on the old Fedow

**Date :** 2026-10-06
**Migration :** Oui — `Customers 0006_moteur_de_monnaie` (schéma public) et
`BaseBillet 0227_moteur_v2_si_un_module_v2_est_actif` (chaque lieu).
`docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing`

> **À FAIRE APRÈS LA MIGRATION, SUR LA BASE DE DEV : purger les schémas `test_*`** (skill
> `tibillet-test` §3, avec l'accord du mainteneur). Les 46 lignes `Client` `test_*` qui
> existaient avant `Customers 0006` sont passées en `legacy`. Purgées, elles sont recréées
> en `v2` au lancement suivant des tests.
>
> **Lieux de dev après `migrate_schemas` (constaté le 2026-10-06) :** `lespass`,
> `le-coeur-en-or`, `la-maison-des-communs` et `le-reseau-des-lieux-en-reseau` passent en
> `v2` (module V2 actif). `festival`, `meta` et `public` restent `legacy`. Les 20 emplacements
> du pool (`WAITING_CONFIG`) sont en `v2`.

## Résumé de la spec 15 / Spec 15 summary

**Quoi / What :** chaque lieu a un moteur de monnaie, `Client.moteur_monnaie` : `legacy`
(l'ancien Fedow distant, `fedow_connect` / `fedow_public`) ou `v2` (le moteur local
`fedow_core`). Un lieu `legacy` ne peut ni allumer un module V2, ni ouvrir l'admin
`fedow_core`, ni être invité dans une monnaie ou une fédération V2. Le gestionnaire du lieu
ne peut jamais changer son moteur (aucun formulaire du lieu ne le montre).
/ Each venue has a currency engine (`legacy` = old remote Fedow, `v2` = local `fedow_core`).
A legacy venue cannot switch V2 modules on, open the fedow_core admin, or be invited into V2.

**Pourquoi / Why :** la décision S6 « hybride additif » garde les lieux existants sur
l'ancien Fedow. Avant cette spec, rien dans le code ne l'imposait : un interrupteur, une URL
d'admin ou une invitation V2 suffisait à faire basculer un lieu de production.
/ Decision S6 keeps existing venues on the old Fedow; nothing in the code enforced it.

**Migrations / Migrations :**
- `Customers 0006_moteur_de_monnaie` (schéma public) : tous les lieux existants passent
  `legacy`, sauf les emplacements vides du pool (`WAITING_CONFIG`), en `v2` ; puis le défaut
  devient `v2` (tout lieu créé ensuite est `v2`).
- `BaseBillet 0227_moteur_v2_si_un_module_v2_est_actif` (chaque lieu) : un lieu dont la
  configuration a déjà un module V2 allumé (caisse, monnaie locale, kiosk, tireuse) passe en
  `v2`, et c'est écrit dans le journal de migration.
/ 0006: existing venues legacy, pool slots v2, default v2. 0227: venues with a V2 module on → v2.

**Ce que voit un lieu `legacy` / What a legacy venue sees :** au tableau de bord, les cartes
Caisse, Monnaies locales, Kiosk et Tireuses sans interrupteur, avec la phrase « Votre lieu
utilise l'ancien moteur de monnaie (Fedow). Ce module n'est pas disponible. » (un module
resté allumé en base garde son interrupteur, seulement pour l'éteindre). Dans le menu : pas
de section caisse, terminaux, inventaire, tireuse, kiosk ; la section « Monnaies » ne montre
que « Assets legacy » (si la fédération est allumée ou si le lieu a des assets legacy).
`/admin/fedow_core/…` répond 403. La caisse V2, la borne kiosk et la tireuse refusent l'accès.
/ Closed V2 cards with an explanation, no V2 sidebar sections, "Assets legacy" only, 403 on
fedow_core, V2 POS / kiosk / tap refused.

**Ce qui reste ouvert / What stays open :**
- pour un lieu `legacy`, à l'identique de `main` : tout l'ancien Fedow (assets legacy,
  invitations et acceptations legacy, ventilation, remise en banque, recharge FED,
  remboursement, paiement QR / NFC de « Mon compte », récompenses d'adhésion), LaBoutik V1,
  la billetterie, les adhésions, « Ventes et comptabilité » ;
- pour le chantier : relecture Opus du diff (session 15-bis) ; workflow i18n (5 chaînes : « Ancien Fedow »,
  « Moteur V2 », « Moteur de monnaie » en 15-1, le message du verrou en 15-2, « Assets
  legacy » en 15-3) ;
  aucun outil de bascule `legacy` → `v2` (hors périmètre, décision du mainteneur plus tard) ;
  la spec 14 (E2E de fédération inter-lieux) s'appuie sur la fixture
  `moteurs_de_depart_verifies` livrée en 15-4.
/ Legacy venues keep the whole old Fedow, LaBoutik V1, ticketing, memberships, sales.
Still to do: Opus review (15-bis), i18n workflow, no switch tool (out of scope).

**Conséquence pour la production et la reprise R / Consequence for production and the
sales takeover :** après la bascule, **tous les lieux de production sont `legacy`** (sauf le
pool), à une condition : aucun n'a un drapeau de module V2 à vrai avant `0227`. C'est vérifié
sur la copie de production par `bash db-prod/copie_prod.sh compter_avant` (après `charger`,
avant `neutraliser`) ; attendu 0, sinon STOP et décision du mainteneur avant la bascule
(`TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-R-copie-prod.md` §3.5). Les deux migrations
entrent dans l'ordre de la nuit de bascule (fiche R §7.2, liste réelle des 28 migrations de
la branche). **La reprise des ventes ne dépend pas du moteur** : c'est une commande, ses
services et les clôtures ne lisent ni le moteur ni les drapeaux de module, et la section
« Ventes et comptabilité » de l'admin reste affichée pour un lieu `legacy` (fiche R §11).
/ After go-live every production venue is legacy, provided none has a V2 flag before 0227
(checked on the production copy by `compter_avant`). The sales takeover does not depend on
the engine.

## Session 15-1 — le champ, les migrations, la démo / the field, the migrations, the demo

**Quoi / What :** chaque lieu porte maintenant son moteur de monnaie : `Client.moteur_monnaie`
vaut `legacy` (ancien Fedow) ou `v2` (moteur `fedow_core`). Les lieux qui existent avant le
déploiement sont `legacy`. Un lieu qui a déjà un module V2 allumé (caisse, monnaie locale,
kiosk, tireuse) passe en `v2`. Un lieu créé ensuite est `v2`. Une seule fonction lit ce
moteur : `lieu_en_moteur_legacy()`.
/ Each venue now carries its currency engine (`legacy` or `v2`). Existing venues are legacy,
venues with a V2 module already on are v2, new venues are v2. One reader function.

**Pourquoi / Why :** rien n'empêchait un lieu existant de basculer vers le moteur V2
(décision S6 « hybride additif » : les lieux existants restent sur le Fedow distant). Ce
champ est la base du verrou (sessions 15-2 et 15-3).
/ Nothing stopped an existing venue from switching to V2; this field is the lock's base.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Customers/models.py` | champ `Client.moteur_monnaie` (défaut `v2`), fonction `lieu_en_moteur_legacy()` (`FakeTenant`, public, `None` = fermé) |
| `Customers/migrations/0006_moteur_de_monnaie.py` | neuf : champ ajouté en `legacy`, pool `WAITING_CONFIG` en `v2`, défaut passé à `v2` |
| `BaseBillet/migrations/0227_moteur_v2_si_un_module_v2_est_actif.py` | neuf : passe en `v2` le lieu dont la `Configuration` a un module V2 allumé |
| `Administration/management/commands/demo_data_v2.py` | `moteur_de_monnaie_du_lieu_de_demo()` : un lieu `caisse_v1_legacy` (`festival`) est `legacy`, les autres `v2` |
| `tests/pytest/conftest.py` | `verifier_les_moteurs_de_depart()` et fixture `moteurs_de_depart_verifies` (à demander, pas appliquées à toute la suite) |
| `tests/pytest/test_verrou_moteur_legacy.py` | neuf : 9 tests (champ, 0006, 0227, lecture du moteur, démo) |
| `tests/pytest/test_fedow_core.py` | le second lieu V2 est `le-coeur-en-or` (`festival` est legacy) |

## Session 15-2 — le verrou côté serveur / the server-side lock

**Quoi / What :** pour un lieu `legacy`, le serveur ferme tout ce qui passe par le moteur V2 :
- allumer un module V2 (caisse, monnaie locale, kiosk, tireuse) est refusé, même par un POST
  direct. Éteindre un module V2 resté allumé reste permis (la caisse d'abord, puis la monnaie
  locale : la règle « la caisse exige la monnaie locale » ne change pas) ;
- l'admin `fedow_core` (assets, tokens, transactions, fédérations) répond 403. Ses routes
  personnalisées (accepter une invitation, exclure un membre) refusent elles-mêmes ;
- un lieu legacy n'est jamais proposé ni accepté dans une invitation V2 (asset ou fédération) ;
- la caisse V2, la borne kiosk et la tireuse refusent l'accès ;
- « Mon compte » n'ajoute plus de tokens locaux `fedow_core`.
Restent ouverts : tout l'ancien Fedow, LaBoutik V1 et `api/inventaire/` (aucun argent).
/ For a legacy venue the server closes everything that goes through the V2 engine:
switching V2 modules on, the fedow_core admin and its routes, V2 invitations, the V2 POS,
kiosk and tap, local tokens in "My account". Switching off stays allowed.

**Pourquoi / Why :** sans ce verrou, un lieu existant pouvait basculer vers le moteur V2 par
un interrupteur, une URL d'admin ou une invitation (spec 15 §1).
/ Without it, an existing venue could switch to V2 through a toggle, an admin URL or an
invitation.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin_tenant.py` | `MODULES_V2_FERMES_AUX_LIEUX_LEGACY`, `MESSAGE_MODULE_FERME_AUX_LIEUX_LEGACY` ; `module_toggle` refuse d'allumer un module V2 en legacy ; `TenantAdmin.get_search_results` ne propose que des lieux v2 à l'autocomplétion des invitations V2 |
| `fedow_core/admin.py` | `admin_fedow_core_ouvert()` (permissions des 4 admins), garde legacy dans `has_change_permission` / `has_delete_permission`, dans `accept_asset_invitation`, `accept_invitation`, `remove_member` ; `lieux_invitables_en_v2()` pour les querysets de `pending_invitations` et `pending_tenants` ; `save_related` retire un lieu legacy invité |
| `BaseBillet/permissions.py` | `HasLaBoutikTerminalAccess` refuse un lieu legacy ; commentaire : `HasLaBoutikAccess` (V1, inventaire) ne lit pas le moteur |
| `kiosk/views.py` | `IsKioskTerminal` refuse un lieu legacy |
| `controlvanne/permissions.py` | `HasTireuseAccess` refuse un lieu legacy |
| `BaseBillet/views.py` | `get_distant_fedow_tokens` et `admin_my_cards` n'ajoutent pas les tokens locaux en legacy |
| `tests/pytest/test_verrou_moteur_legacy.py` | 2e partie : 9 tests (module_toggle, admin et routes fedow_core, invitations, points d'entrée V2, tokens de « Mon compte », inventaire) |
| `tests/pytest/test_pos_vider_carte.py` | fragilité hors verrou : la fixture `asset_tlf_vc` crée son asset sous `schema_context(public)`. Après `test_parcours_vente_fed_et_remise_en_banque.py` (requêtes HTTP sur `lespass`), la connexion gardait `schema_name = "lespass"` avec un `search_path` réel revenu à `public` : le signal d'Asset cherchait `BaseBillet_categorieproduct` dans `public` (11 erreurs) |

**Traductions :** une nouvelle chaîne (`MESSAGE_MODULE_FERME_AUX_LIEUX_LEGACY`) : le workflow
i18n est à lancer.

## Session 15-3 — l'affichage du verrou / the lock on screen

**Quoi / What :**
- **Tableau de bord** : pour un lieu `legacy`, les cartes des 4 modules V2 (caisse, monnaie
  locale, kiosk, tireuse) sont fermées : pas d'interrupteur, la phrase du verrou sous la carte,
  pas de lien « Ouvrir le kiosque » ni « Open POS ». La caisse LaBoutik V1 garde son état.
  Un module V2 resté allumé en base garde son interrupteur, pour l'éteindre (décision Q2).
  Les cartes fermées ne comptent pas dans « Découvrir plus de modules » ni dans le
  compteur du domaine.
- **Menu latéral** : les sections caisse, terminaux, inventaire, tireuse et kiosk n'existent
  que pour un lieu `v2`. La section « Monnaies » est la seule porte vers les monnaies
  (décision Q1) : lieu `v2` = pages `fedow_core` si la monnaie locale est allumée, plus
  « Assets legacy » si le lieu a des assets de l'ancien Fedow (origine, fédéré ou invité ;
  FED, badges, adhésions et archivés exclus) ; lieu `legacy` = seulement « Assets legacy », si
  la fédération est allumée ou si le lieu a des assets legacy. « Assets » sort du module
  « Fédération et agenda participatif ».
/ Legacy venues: V2 dashboard cards closed (a module still on keeps its switch to turn it
off), V2 sidebar sections hidden; the "Currencies" section follows the engine and lists
"Assets legacy" when the venue has legacy assets. "Assets" leaves the Federation module.

**Pourquoi / Why :** le serveur refusait déjà (15-2) ; l'écran proposait encore des
interrupteurs et des pages fermées. Une seule entrée vers les assets legacy garde la règle
« une page, une section » du rail.
/ The server already refused; the screen still offered closed switches and pages.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin/dashboard.py` | `_construire_sections_modules` : sections V2 seulement en `v2`, section « Monnaies » selon le moteur et les assets legacy, « Assets » retiré de Fédération ; `_build_modules_context` : `carte["moteur_legacy"]`, interrupteur seulement pour éteindre, pas de lien d'ouverture ; `_poser_le_lien_d_ouverture` : pas d'« Open POS » en legacy ; `_compter_les_cartes_reelles` : sans les cartes fermées éteintes ; `_poser_les_liens_des_modules` : une carte éteinte ou fermée ne mène pas à son module ; tables des pages : `fedow_public.assetfedowpublic` rangé sous « Monnaies » |
| `Administration/templates/admin/partials/dashboard_module_card.html` | branche `moteur_legacy` (ni interrupteur ni pastille V1) et phrase du verrou sous la carte (`data-testid="<carte>-moteur-legacy"`) |
| `tests/pytest/test_verrou_moteur_legacy.py` | 3e partie : 9 tests (cartes, Q2, liens d'ouverture, compteur, sections V2, section « Monnaies », page de module, Fédération, une page = une section) |

**Traductions :** une nouvelle chaîne, `"Assets legacy"` : le workflow i18n est à lancer.

## Session 15-4 — documents, copie de production, prérequis de la spec 14 / documents, production copy, spec 14 prerequisite

**Quoi / What :**
- **Copie de production** : nouvelle sous-commande `bash db-prod/copie_prod.sh compter_avant`,
  en **lecture seule** (transaction `READ ONLY`, psql seul), à lancer après `charger` et
  **avant** `neutraliser`. Comptages agrégés seulement : lieux, lieux par catégorie, lieux
  avec `module_caisse` / `module_monnaie_locale` / `module_kiosk` / `module_tireuse` à vrai
  (et avec au moins un), lieux avec `server_cashless` renseigné (jamais affiché), lieux
  `module_federation`. Une colonne absente de la production (`module_kiosk`) compte « faux ».
  Conclusion `OK` (0 lieu de production avec un drapeau V2) ou `STOP`. Refus si la pile n'est
  pas la bonne, si aucun dump n'est chargé, ou si la neutralisation est faite (« trop tard,
  `server_cashless` est vidé »). Procédure mise à jour : `charger` → `compter_avant` →
  `neutraliser` → `migrer` → `compter`, et cases à cocher du moteur et du réseau CLAF.
- **Fiche R** : l'ordre de la nuit de bascule (§7.2) liste les vraies migrations de la
  branche (28 fichiers, app par app, depuis `556e2877` qui les fait repartir de `main`), dont
  `Customers 0006` et `BaseBillet 0227` ; vérification préalable `compter_avant` = 0 ; tous
  les lieux de production `legacy` après `0006` ; la reprise ne dépend pas du moteur (§11).
- **Tests** : `verifier_les_moteurs_de_depart()` quitte `tests/pytest/conftest.py` pour
  `tests/outils_moteur_de_monnaie.py`, importable par les deux suites. Fixture
  `moteurs_de_depart_verifies` dans les deux conftests (pytest, et E2E avec
  `django_db_blocker.unblock()`), à demander : pas appliquée à toute la suite.
- **Documents** : spec 15 §8 (cases faites, ordre des commandes) et §9 (fichiers réels des
  sessions 15-1 à 15-4) ; `FEDOW_IMPORT/INDEX.md` (spec 10, spec 15 à jour, suivi du
  chantier).
/ Read-only `compter_avant` subcommand on the production copy; takeover sheet lists the real
migrations and the engine check; the engine check moves to a module shared by pytest and
E2E; spec 15 §8/§9 and the hub index updated.

**Pourquoi / Why :** `compter` exige la neutralisation, qui vide `server_cashless` : le
comptage des drapeaux devait la précéder (relecture I2, décision Q4). Les anciens noms de
migrations de la fiche R étaient périmés depuis `556e2877` (relecture I3). La spec 14 (E2E)
doit vérifier les moteurs au départ, depuis un autre conftest.
/ Counting had to come before neutralisation; the takeover sheet had stale migration names;
spec 14 E2E tests need the engine check.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `db-prod/copie_prod.sh` | **hors git** : sous-commande `compter_avant` (lecture seule) ; `charger` annonce `compter_avant` puis `neutraliser` |
| `TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-R-copie-prod.md` | ordre des commandes, description de `compter_avant`, §3.5 « Vérifications du moteur de monnaie et du réseau CLAF » |
| `TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-R-reprise-ventes.md` | §7.2 étape 3 (migrations réelles, vérification c, lieux `legacy`) ; §11 (migrations, moteur et reprise) |
| `TECH_DOC/SESSIONS/FEDOW_IMPORT/15-spec-verrou-moteur-legacy.md` | §8 et §9 |
| `TECH_DOC/SESSIONS/FEDOW_IMPORT/INDEX.md` | spec 10, spec 15, suivi du chantier |
| `tests/outils_moteur_de_monnaie.py` | neuf : `MOTEURS_ATTENDUS_DES_LIEUX_DE_DEV`, `verifier_les_moteurs_de_depart()` |
| `tests/pytest/conftest.py` | la fonction en sort ; la fixture `moteurs_de_depart_verifies` l'importe |
| `tests/e2e/conftest.py` | fixture `moteurs_de_depart_verifies` (session, `django_db_blocker.unblock()`) |

## Session 15-bis — corrections de la relecture du diff / review fixes

**Quoi / What :**
- **I1 — appairage LaBoutik V1 refusé sur un lieu v2** : `Onboard_laboutik` répond 409
  `{"detail": ..., "code": "lieu_en_moteur_v2"}` pour un lieu v2, sans appeler le Fedow et
  sans rien écrire. Ce refus passe AVANT le verrou des modules (un lieu v2 n'a jamais de
  caisse V1). Un lieu legacy appaire comme avant (verrou des modules inchangé).
- **I2 — vérification de départ automatique** : fixture autouse de portée session
  `_moteurs_verifies_au_depart_de_la_suite` (`tests/pytest/conftest.py`), qui appelle
  `verifier_le_depart_de_la_suite()` (`tests/outils_moteur_de_monnaie.py`) : une requête,
  aucun `Client` `test_*` en `legacy`, `lespass` en `v2`, sinon `pytest.fail` avec la
  consigne (base neuve par `down -v` + flush, ou `UPDATE` SQL des `test_*`). La vérification
  complète (`moteurs_de_depart_verifies`) reste à la demande, en pytest comme en E2E.
- **M1** : `lieu_en_moteur_legacy()` rend toujours `True` pour le schéma public, quelle que
  soit la valeur de sa ligne `Client` (en `v2` sur une base neuve).
- **M2** : pas d'encart BETA sur une carte fermée par le verrou (caisse, tireuse).
- **M3** : le total d'un domaine compte toutes les cartes réelles (Laboutik 0 / 1,
  Lémachines 0 / 2 sur un lieu legacy, au lieu de 0 / 0) ; seule la pastille « Découvrir »
  écarte les cartes fermées et éteintes.
- **M4** : la requête « le lieu a des assets legacy » est mémorisée sur la requête HTTP
  (`_lieu_a_des_assets_legacy`) : 1 fois par page d'admin au lieu de 4.
- **M5** : tests de `FederationAdmin.has_delete_permission` et de `AssetAdmin.save_related`.
- **M6** : piège 15.1 dans `tests/PIEGES.md` (schéma de connexion périmé après l'annulation
  d'une transaction) ; trois fixtures de portée module créent leur asset TLF sous
  `schema_context(public)`.
- **M8** : `MODULES_V2_FERMES_AUX_LIEUX_LEGACY` et `MESSAGE_MODULE_FERME_AUX_LIEUX_LEGACY`
  déménagent dans `Customers/models.py`, à côté de `lieu_en_moteur_legacy()` (plus d'import
  local dans `dashboard.py`) ; imports remontés en tête (`BaseBillet/permissions.py`, les
  deux conftests) ; « APPELEE PAR » liste les vrais appelants.
- **M9** : spec 15 §5, §5.4, §5.5, §7, §9 ; M7 noté comme voulu (§5.5).
- **`tests/pytest/test_onboard_laboutik_verrou_v1_v2.py` réécrit** (décision de
  l'orchestrateur) :
  - **avant** : les tests postaient sur `lespass`, et écrivaient sa `Configuration` par
    `save()` (puis la restauraient) ;
  - **après** : lieu dédié `test_verrou_moteur_legacy` (`FastTenantTestCase`), passé en
    `legacy` par `update()` dans la transaction du test ; `Configuration` en mémoire
    (`get_solo()` et `save()` patchés). Assertions gardées : `code == "modules_v2_actifs"`
    pour chaque module V2 et pour les trois ensemble, « passe le verrou si aucun module V2 »,
    verrou actif en DEBUG. Un test ajouté : un lieu v2 avec des modules V2 est refusé par le
    verrou de moteur (`lieu_en_moteur_v2`), en premier ;
  - **raison** : avec I1, `lespass` (v2) est refusé avant le verrou des modules ; et un test
    ne doit jamais écrire dans `lespass`.
/ V1 pairing refused for a v2 venue; automatic start-up check; public schema always closed;
no BETA on closed cards; domain totals 0/N; legacy assets read once per request; tests for
federation delete and save_related; stale connection schema trap; constants moved next to
the engine reader; spec updated; the onboard test file moved to the dedicated test venue.

**Pourquoi / Why :** relecture Opus du diff de la spec 15 (0 bloquant, I1-I2, M1-M9) ; I1 et
M7 tranchées par le mainteneur.
/ Opus review of the spec 15 diff.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `ApiBillet/views.py` | `Onboard_laboutik` : refus d'un lieu v2 (409, `lieu_en_moteur_v2`) avant le verrou des modules |
| `Customers/models.py` | `lieu_en_moteur_legacy()` : public toujours fermé, docstring et appelants ; les deux constantes du verrou |
| `Administration/admin/dashboard.py` | BETA masqué sur une carte fermée ; total du domaine ; pastille « Découvrir » ; `_lieu_a_des_assets_legacy` mémorisé sur la requête ; constantes importées de `Customers.models` |
| `Administration/admin_tenant.py` | les constantes partent dans `Customers/models.py` (importées de là) |
| `fedow_core/admin.py` | `MESSAGE_MODULE_FERME_AUX_LIEUX_LEGACY` importé de `Customers.models` |
| `BaseBillet/permissions.py` | import de `lieu_en_moteur_legacy` en tête |
| `tests/outils_moteur_de_monnaie.py` | `verifier_le_depart_de_la_suite()`, consigne commune |
| `tests/pytest/conftest.py` | fixture autouse `_moteurs_verifies_au_depart_de_la_suite` ; imports en tête |
| `tests/e2e/conftest.py` | import en tête |
| `tests/pytest/test_verrou_moteur_legacy.py` | tests 23 à 29 ; message périmé corrigé ; constante importée de `Customers.models` |
| `tests/pytest/test_onboard_laboutik_verrou_v1_v2.py` | réécrit sur le lieu dédié (voir plus haut) |
| `tests/pytest/test_card_refund_service.py`, `test_remboursement_especes_trace_comptable.py`, `test_verify_transactions.py` | asset TLF de la fixture de portée module créé sous `schema_context(public)` |
| `tests/PIEGES.md` | piège 15.1 |
| `TECH_DOC/SESSIONS/FEDOW_IMPORT/15-spec-verrou-moteur-legacy.md` | §5, §5.4, §5.5, §7, §9 |

**Traductions / Translations :** une chaîne nouvelle (`ApiBillet/views.py`) : « Ce lieu
utilise le moteur de monnaie V2. Une caisse LaBoutik V1 ne peut pas s'y connecter. » — le
workflow i18n est à lancer par le mainteneur. La chaîne déménagée
(`MESSAGE_MODULE_FERME_AUX_LIEUX_LEGACY`) garde son texte : seule sa référence de fichier
change.

## Session « ter » — corrections de la relecture Fable, cascade sans monnaie archivée / Fable review fixes, cascade without archived currency

**Quoi / What :**
- **Cascade de paiement sans monnaie archivée** (décision du mainteneur) :
  `AssetService.obtenir_assets_accessibles` ne rend plus que les monnaies actives ET non
  archivées. Ses appelants choisissent la monnaie à DÉBITER : cascade NFC de la caisse,
  complément sur une 2e carte, cascade de la tireuse (le plan comptable filtrait déjà
  `archive=False`). Le vidage de la carte (`rembourser_en_especes`), son aperçu et la liste
  des soldes ont leurs propres requêtes : ils voient encore une monnaie archivée, ses jetons
  restants restent visibles et sont rendus en espèces.
- **M-1** : une monnaie `fedow_core` archivée n'apparaît plus dans le panneau des
  invitations, et la route `accept_asset_invitation` la refuse (message, l'invitation reste
  en attente).
- **M-5** : libellé du verrou : « Votre lieu utilise l'ancien moteur de monnaie (Fedow) : ce
  module V2 ne le concerne pas. »
- **M-4** : spec 15 §3 : le moteur n'est dans aucun écran, il ne change que par la base.
- **M-3** : le SQL de `compter_avant` (agrégats) est copié dans
  `TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-R-copie-prod.md` §3.3 (le script `db-prod/`
  est hors git).
- **M-8** : la vérification de départ compte seulement les requêtes sur `Customers_client`
  (au plus une), plus « exactement une requête » au total.
- **Fixtures de la tireuse** (`rf_asset_tlf`, `asset_tlf`, `test_asset_tlf_api`,
  `cv_asset_tlf`) : même règle que ci-dessous.
- **Fixture `rf_asset_tlf`** (`test_controlvanne_review_fixes.py`) : l'asset TLF est choisi
  par la requête de la cascade (`obtenir_assets_accessibles`, puis le premier TLF) ; le test
  C1 ne dépend plus des monnaies présentes sur `lespass`.
/ The payment cascade skips archived currencies (refunds and balances still see them);
archived assets are neither offered nor accepted as invitations; lock label reworded; spec
and copy-prod doc fixed; start-up check counts venue-table queries only; robust tap fixture.

**Pourquoi / Why :** relecture Fable du chantier 15 · 10 · 14 (M-1 à M-5, M-8) ; échec du
test C1 de la tireuse : 15 assets TLF « E2E Fed V2 … » de `lespass`, archivés mais actifs,
étaient choisis par la cascade (premier nom trié), alors que la carte du test était créditée
sur « Monnaie locale ». Les assets de la base de dev ne sont pas modifiés : archivés, ils sont
maintenant exclus.
/ Fable review; the tap C1 test failure (archived-but-active assets picked by the cascade).

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `fedow_core/services.py` | `obtenir_assets_accessibles` : `archive=False`, docstring (débit seulement ; vidage et soldes ont leurs requêtes) |
| `fedow_core/admin.py` | panneau des invitations sans monnaie archivée ; `accept_asset_invitation` refuse une monnaie archivée |
| `Customers/models.py` | libellé de `MESSAGE_MODULE_FERME_AUX_LIEUX_LEGACY` |
| `tests/pytest/test_cascade_sans_monnaie_archivee.py` | Nouveau : cascade (service et tireuse) sans monnaie archivée ; vidage et soldes la voient encore |
| `tests/pytest/test_verrou_moteur_legacy.py` | test 30 (M-1) ; M-8 (requêtes sur `Customers_client` ≤ 1) |
| `tests/pytest/test_controlvanne_review_fixes.py` | fixture `rf_asset_tlf` alignée sur la cascade |
| `tests/pytest/test_controlvanne_billing.py`, `test_controlvanne_api.py`, `test_controlvanne_models.py` | fixtures `asset_tlf`, `test_asset_tlf_api`, `cv_asset_tlf` et le re-crédit du test `card_removed` : l'asset crédité sur la carte est choisi par la requête de la cascade (elles prenaient le premier TLF `active=True`, une monnaie archivée sur la base de dev) |
| `tests/e2e/test_federation_asset_fedow_core.py` | M-2 (voir `2026-10-06-tests-federation-inter-lieux.md`) |
| `TECH_DOC/SESSIONS/FEDOW_IMPORT/15-spec-verrou-moteur-legacy.md` | §3 (M-4) |
| `TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-R-copie-prod.md` | §3.3 : SQL de `compter_avant` (M-3) |

**Traductions / Translations :** deux msgid nouveaux à traduire (workflow i18n par le
mainteneur) : le nouveau libellé de `MESSAGE_MODULE_FERME_AUX_LIEUX_LEGACY`
(`Customers/models.py`, l'ancien msgid disparaît) et « Cette monnaie est archivée : son
invitation ne peut plus être acceptée. » (`fedow_core/admin.py`).

---

## Menu « Monnaies » : une porte par moteur ; plus de création d'asset legacy / Currencies menu: one door per engine; no more legacy asset creation

**Quoi / What :** la section du menu s'appelle « Monnaies locales, temps, SSA et cashless ».
- Lieu v2, monnaie locale allumée : « Monnaies et tokens », « Transactions », « Réseaux de
  monnaie » (`fedow_core`) puis « Cartes NFC ». Plus d'entrée vers l'ancien Fedow, même si le
  lieu a des assets legacy.
- Lieu legacy, fédération allumée ou assets legacy : « Actifs » (l'admin des assets de l'ancien
  Fedow, libellé de `main`) puis « Cartes NFC ».
- L'admin des assets de l'ancien Fedow ne crée plus d'asset (le bouton « Ajouter » disparaît) :
  on gère, invite et accepte les assets existants.
/ v2 venues see the fedow_core pages, legacy venues see the old Fedow "Assets"; both get "NFC
cards"; no more legacy asset creation from the admin.

**Pourquoi / Why :** décision du mainteneur : la démo montrait deux portes vers les monnaies
(V2 et legacy). La caisse, la tireuse et le kiosk V2 paient avec les monnaies `fedow_core` :
un lieu v2 garde leurs pages. Un lieu legacy garde l'ancien Fedow. Plus de nouvel asset legacy
en attendant H-2 / H-3.
/ Maintainer decision: one door per engine; fedow_core is needed by the V2 POS.

| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin/dashboard.py` | section « Monnaies » : pages et condition d'affichage ; nom de `module_monnaie_locale` dans `MODULE_FIELDS` |
| `tests/pytest/test_verrou_moteur_legacy.py` | `test_section_monnaies_suit_le_moteur` réécrit sur la nouvelle règle ; `test_une_page_une_section_sur_un_lieu_legacy_avec_assets_legacy` (ex-« v2 ») et `test_assets_legacy_lus_une_fois_par_requete` passés sur un lieu legacy ; docstring du module |
| `Administration/admin_tenant.py` | `AssetAdmin` (`fedow_public`) : `has_add_permission` = False, plus de création d'asset legacy depuis l'admin (on gère, invite et accepte les existants) |
| `tests/pytest/test_admin_asset_sans_fedow.py` | nouveau test : page d'ajout 403 (même au superadmin), pas de lien d'ajout dans la liste |
| `tests/e2e/test_federation_asset_legacy_inter_lieux.py` | B1 : vérifie que la page d'ajout répond 403, puis crée l'asset comme le faisait `save_model` (ligne en base + `get_or_create_token_asset`) |

**Traductions / Translations :** un msgid nouveau : « Monnaies locales, temps, SSA et
cashless » (`dashboard.py`, l'ancien « Monnaies locales, temps et cashless » disparaît).
« Assets » est déjà traduit « Actifs ».

---

## Session 15-5 — Bascule en un clic / One-click switch to V2

**Quoi / What :** un lieu legacy passe **une fois**, de lui-même, au moteur V2 en allumant un
module V2 (caisse, monnaie locale, kiosk, tireuse), si rien ne le retient sur l'ancien Fedow.
Sept raisons le retiennent (`Customers/bascule_vers_v2.py`) : agenda partagé (`META`),
LaBoutik V1, monnaie d'un autre lieu acceptée ou invitation (hors `FED`, `SUB`, `BDG`),
monnaie propre (hors `SUB`, `BDG`), cartes NFC du lieu, recharge Stripe passée par l'ancien
Fedow. Avec une raison : refus, le message et la fenêtre de confirmation listent les raisons,
la carte du tableau de bord reste fermée et les affiche. Sans raison : la fenêtre annonce le
passage au nouveau moteur, la carte est celle d'un lieu v2, et l'allumage bascule le lieu
(`Client.moteur_monnaie = v2`) dans la même transaction que l'enregistrement du module.
Jamais de retour en legacy.
/ A legacy venue moves once to V2 by switching on a V2 module, unless something keeps it on
the old Fedow (seven reasons). Reasons are listed in the refusal, the window and the card.

**Pourquoi / Why :** décision 6 du mainteneur (spec 15 §2, §5.8) : livrée avant la bascule
de production, pour que les lieux qui le peuvent passent au moteur V2 sans intervention. Sur
la copie de production, la fonction des raisons donne **248 lieux qui peuvent basculer, 92
qui ne le peuvent pas**.
/ Maintainer decision 6: shipped before the production switch.

| Fichier / File | Changement / Change |
|---|---|
| `Customers/bascule_vers_v2.py` | **nouveau** : `raisons_qui_empechent_le_passage_en_v2(lieu)` (7 raisons, base seulement) et `raisons_qui_retiennent_le_lieu_courant()` (un `FakeTenant` ou le schéma public restent fermés) |
| `Administration/admin_tenant.py` | `module_toggle` : refus seulement avec des raisons (message « pas encore disponible » + raisons + phrase de fin) ; sinon bascule + enregistrement dans une transaction, `logger.info` ; `module_toggle_modal` : raisons ou texte de bascule |
| `Administration/templates/admin/dashboard_module_modal.html` | raisons sans bouton de confirmation ; texte de bascule (`data-testid` `module-modal-raisons-moteur-legacy`, `module-modal-passage-moteur-v2`) |
| `Administration/admin/dashboard.py` | `_build_modules_context` : raisons calculées une fois par affichage ; cartes V2 fermées seulement avec des raisons (`raisons_moteur_legacy` remplace `message_moteur_legacy`) |
| `Administration/templates/admin/partials/dashboard_module_card.html` | la carte fermée affiche les raisons à la place de la phrase fixe |
| `tests/pytest/test_bascule_vers_v2.py` | **nouveau** : 16 tests (les 7 raisons, l'ordre, `module_toggle`, la transaction, la fenêtre, la carte) |
| `tests/pytest/test_verrou_moteur_legacy.py` | tests des cartes fermées et du refus posés sur un lieu retenu (monnaie legacy ou cartes NFC) ; requêtes des assets legacy : 1 + un calcul des raisons |

**Traductions / Translations :** 12 msgid nouveaux (français) à passer au workflow i18n
(textes définitifs après 15-5-bis) : les 7 raisons (`Customers/bascule_vers_v2.py`, dont
« Votre lieu a eu des échanges avec l'ancien moteur. »), « Ce module n'est pas encore
disponible pour votre lieu : » et « Contactez l'équipe TiBillet pour lui indiquer que vous
souhaitez faire une migration. » (`admin_tenant.py`, la fenêtre, la carte), « Module non
disponible », « Pour activer ce module, votre lieu passe au nouveau moteur de monnaie de
TiBillet. », « Vos événements, réservations et adhésions ne changent pas. » (fenêtre).

**À savoir / Note :** sur une base de dev neuve, `festival` (legacy) n'a aucune raison : ses
cartes V2 s'ouvrent, et allumer un de ses modules V2 le passe en v2 pour de bon (la
vérification des moteurs de départ des E2E exige `festival` legacy).

### Session 15-5-bis — corrections de la relecture / review fixes

**Quoi / What :**
- la transaction n'entoure l'enregistrement que pendant une bascule : sans bascule, l'échec
  du SEPA garde l'enregistrement partiel de la méthode ; après l'échec d'une bascule, le
  cache du singleton est vidé (`get_solo()` ne rend plus un module que la base n'a pas) ;
- toute autre erreur pendant une bascule remet `connection.tenant` à legacy, puis remonte ;
- double clic : la bascule est faite une seule fois (`update` filtré sur `legacy`, journal
  seulement si une ligne change) et le bouton de confirmation se désactive au clic
  (`hx-disabled-elt`) ;
- aucun lien « Open POS / Open kiosk » pour un lieu encore legacy, retenu ou non ;
- textes du mainteneur : raison 7 « Votre lieu a eu des échanges avec l'ancien moteur. »,
  phrase de fin « Contactez l'équipe TiBillet pour lui indiquer que vous souhaitez faire une
  migration. » (message, fenêtre, carte) ; la carte retenue reprend l'introduction ;
- fenêtre avec raisons : titre « Module non disponible », un seul bouton « Fermer » ; boîte
  de dialogue accessible (`role="dialog"`, `aria-modal`, `aria-labelledby`), raisons en
  `role="alert"`.
/ Review fixes: transaction only while switching, singleton cache cleared on failure,
single switch on double click, no "Open" link for legacy venues, maintainer's wording,
accessible dialog.

| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin_tenant.py` | `module_toggle` : `atomic` seulement pendant la bascule, `clear_cache()` et remise à legacy sur échec, `update` filtré sur `legacy`, journal si une ligne change ; nouvelle phrase de fin |
| `Administration/templates/admin/dashboard_module_modal.html` | `role="dialog"`, titre « Module non disponible », bouton « Fermer », `role="alert"`, `hx-disabled-elt` |
| `Administration/admin/dashboard.py` | aucun lien d'ouverture V2 pour un lieu encore legacy (cartes génériques et caisse) |
| `Administration/templates/admin/partials/dashboard_module_card.html` | introduction + raisons + phrase de fin |
| `Customers/bascule_vers_v2.py` | texte de la raison 7 |
| `tests/pytest/test_bascule_vers_v2.py` | 5 tests neufs (cache après échec, enregistrement partiel, autre erreur, double clic, liens d'ouverture, fenêtre accessible) ; tests 13 et 15 complétés |

---

## Comment tester (à la main) / Manual test

### Test 1 — les moteurs des lieux de dev
```bash
docker exec lespass_postgres psql -U <user> -d <db> -c \
  "select schema_name, categorie, moteur_monnaie from public.\"Customers_client\" \
   where schema_name not like 'test\_%' order by 1"
```
Attendu : `lespass`, `le-coeur-en-or`, `la-maison-des-communs`,
`le-reseau-des-lieux-en-reseau` en `v2` ; `festival`, `meta`, `public` en `legacy` ;
les lignes `W` (pool) en `v2`.

### Test 2 — la vérification de départ
Après la purge des `test_*` et un `make test`, la vérification ne signale plus rien :
```bash
docker exec -w /DjangoFiles lespass_django poetry run python manage.py shell -c "
from tests.outils_moteur_de_monnaie import verifier_les_moteurs_de_depart
verifier_les_moteurs_de_depart(); print('OK')"
```

### Test 3 — la démo
Sur une base reconstruite (`demo_data_v2`), `festival` est `legacy`, les autres lieux `v2`.

### Test 4 (15-2) — un lieu legacy ne peut pas allumer un module V2
Sur `festival` (legacy), en admin : tableau de bord, interrupteur d'un module V2 (ou POST
direct sur `/admin/BaseBillet/configuration/module-toggle/module_caisse/`). Attendu : toast
« Votre lieu utilise l'ancien moteur de monnaie (Fedow). Ce module n'est pas disponible. »,
le module reste éteint. Sur `lespass` (v2) : le module s'allume comme avant.

### Test 5 (15-2) — l'admin fedow_core est fermé à un lieu legacy
Sur `festival` : `/admin/fedow_core/asset/`, `/admin/fedow_core/asset/add/`,
`/admin/fedow_core/federation/` → 403. Sur `lespass` → 200.

### Test 6 (15-2) — un lieu legacy n'est pas invitable
Sur `lespass`, fiche d'un asset `fedow_core` créé par le lieu, champ « invitations » : taper
« fest » → `festival` n'est pas proposé. Même chose dans une fédération V2.

### Test 7 (15-2) — l'ancien Fedow reste ouvert
Sur `festival` : l'admin des assets legacy (`/admin/fedow_public/assetfedowpublic/`) et
« Mon compte » (soldes du Fedow distant) fonctionnent comme avant.

### Test 8 (15-3) — le tableau de bord d'un lieu legacy
Sur `festival` (legacy), `/admin/`, ouvrir « Découvrir plus de modules ». Attendu : Caisse,
Monnaies locales, Kiosk et Tireuses sans interrupteur, avec la phrase « Votre lieu utilise
l'ancien moteur de monnaie (Fedow). Ce module n'est pas disponible. », sans « Ouvrir le
kiosque », sans encart BETA (15-bis). Les domaines Laboutik et Lémachines affichent 0/1 et
0/2 (15-bis ; 0/0 avant). La pastille « Découvrir » ne compte pas ces 4 cartes. Sur `lespass`
(v2) : rien ne change, la caisse et les tireuses gardent leur encart BETA.

### Test 9 (15-3) — le menu « Monnaies »
- `festival` : domaine Lerézo → « Monnaies locales, temps, SSA et cashless » → « Actifs »
  puis « Cartes NFC », un seul onglet « Gérer ». Pas de section Caisse, Terminaux, Inventaire,
  Tireuses, Kiosk. Le module « Fédération et agenda participatif » n'a plus « Assets ».
- `lespass` (v2, monnaie locale allumée) : la même section a « Monnaies et tokens »,
  « Transactions », « Réseaux de monnaie », « Cartes NFC » ; pas d'« Actifs » (ancien Fedow),
  bien que `lespass` ait des assets legacy.
- Sur `/admin/fedow_public/assetfedowpublic/` (lieu legacy), pas de bouton « Ajouter » ;
  `/admin/fedow_public/assetfedowpublic/add/` répond 403.

### Test 10 (15-4) — `compter_avant` sur la copie de production
Seulement sur la pile à part, après `charger` et avant `neutraliser` :
`bash db-prod/copie_prod.sh compter_avant`. Attendu : le tableau par catégorie (nombres
seulement) et `OK     0 lieu de production avec un drapeau V2`. Après `neutraliser`, la
même commande refuse : « trop tard, server_cashless est vidé ».

### Test 11 (15-bis) — appairage LaBoutik V1
Sur un lieu v2 (`lespass`), le POST d'appairage d'une caisse V1 sur `/api/onboard_laboutik/`
répond 409, `code = "lieu_en_moteur_v2"`. Sur `festival` (legacy), l'appairage se passe comme
avant (verrou des modules compris).

### Test 12 (15-bis) — la vérification de départ automatique
Tout `make test` commence par elle. Pour la voir échouer, sur la base de dev et avec
l'accord du mainteneur : passer une ligne `test_*` en `legacy`, lancer un test, lire la
consigne, puis remettre la ligne en `v2`.

### Tests automatiques
`make test ARGS="tests/pytest/test_verrou_moteur_legacy.py tests/pytest/test_onboard_laboutik_verrou_v1_v2.py"`
(41 tests : 27 de 15-1 à 15-3, 9 de 15-bis, 5 du verrou d'appairage).

### Test 13 (ter) — une monnaie archivée ne paie plus, mais se rend
Sur `lespass` (v2), dans l'admin `fedow_core`, archiver une monnaie TLF de test qui porte
des jetons sur une carte. À la caisse, payer avec cette carte : la monnaie archivée n'est
pas débitée (la monnaie locale en service l'est, ou « fonds insuffisants »). Le solde de la
carte (« Mon compte », aperçu du vidage) montre encore les jetons archivés ; « Vider la
carte » les rend en espèces.

### Test 14 (ter) — invitation sur une monnaie archivée
Inviter `le-coeur-en-or` sur une monnaie de `lespass`, puis l'archiver. Chez
`le-coeur-en-or`, la liste des monnaies n'affiche plus l'invitation ; un POST direct sur
`/admin/fedow_core/asset/accept_asset_invitation/<uuid>/` affiche « Cette monnaie est
archivée… » et l'invitation reste en attente.

`make test ARGS="tests/pytest/test_cascade_sans_monnaie_archivee.py tests/pytest/test_verrou_moteur_legacy.py tests/pytest/test_controlvanne_review_fixes.py"`

### Test 15 (15-5) — la bascule en un clic
Les tests 4 et 8 valent désormais pour un lieu legacy **retenu** (une raison au moins).
1. Lieu legacy retenu (ex. `festival` après le test B des E2E, fédéré à une monnaie de
   `lespass`) : tableau de bord, les 4 cartes V2 sans interrupteur affichent la raison
   (« Votre lieu accepte une monnaie partagée avec d'autres lieux. »), entre l'introduction et
   la phrase de fin. Un POST direct sur
   `/admin/BaseBillet/configuration/module-toggle/module_kiosk/` : toast « Ce module n'est
   pas encore disponible pour votre lieu : … Contactez l'équipe TiBillet pour lui indiquer
   que vous souhaitez faire une migration. », module éteint. Un GET direct sur
   `/admin/BaseBillet/configuration/module-toggle-modal/module_kiosk/` : fenêtre « Module non
   disponible », un seul bouton « Fermer ».
2. Lieu legacy sans raison (à faire sur une base jetable : la bascule est définitive) :
   interrupteur du kiosk → la fenêtre annonce « Pour activer ce module, votre lieu passe au
   nouveau moteur de monnaie de TiBillet. … » ; confirmer → module allumé, et
   `Client.objects.get(schema_name=…).moteur_monnaie == "v2"`. Le journal du serveur porte
   « Bascule en un clic : le lieu … passe au moteur V2 en allumant module_kiosk ».

`make test ARGS="tests/pytest/test_bascule_vers_v2.py tests/pytest/test_verrou_moteur_legacy.py"`
