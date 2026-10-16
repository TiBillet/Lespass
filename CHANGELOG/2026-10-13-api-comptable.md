# API comptable : les clôtures, leurs écritures et le plan comptable pour les logiciels comptables / Accounting API: closures, entries and chart of accounts for accounting software

**Date :** 2026-10-13
**Migration :** Oui (`BaseBillet/migrations/0230_externalapikey_comptabilite.py` : un booléen ; prod : un lieu après l'autre)

## Resume / Summary
**Quoi / What :**
- Nouveau droit de clé d'API **« Comptabilité (lecture) »** (`ExternalApiKey.comptabilite`), sur les basenames `closure` et `account`. La clé seule suffit : un logiciel comptable tourne la nuit, sans humain.
- `GET /api/v2/closures/?after_number=<n>` : les clôtures J à importer (avec des ventes, sans la J « reprise »), de numéro plus grand que `n`, dans l'ordre. Pas de pages. Le curseur est un numéro, jamais une date : une J du filet peut être créée en retard mais datée d'avant.
- `GET /api/v2/closures/<uuid>/entries/` : les écritures de la J en JSON, avec les noms des colonnes du FEC (`JournalCode`, `EcritureNum`, `CompteNum`, `Debit`…), en centimes entiers, dates ISO, **sans `ValidDate`** (l'écriture arrive non verrouillée dans le logiciel).
- `GET /api/v2/closures/<uuid>/fec/` : le fichier FEC, octet pour octet celui du bouton de l'admin.
- `GET /api/v2/accounts/` : tous les comptes du lieu (actifs ou non), triés par numéro ; charge le plan par défaut si le lieu n'en a aucun.
- Refus : `404 not_exportable` (clôture jamais à importer : H / M / A, J sans vente, J reprise, uuid inconnu) ; `409 missing_account` ou `409 unbalanced_entry` (à réessayer plus tard ; le déséquilibre est journalisé en exception).
- La règle « FEC refusé avant la mise en service » sort de la vue admin : `comptabilite.tasks.refus_du_fec_avant_la_mise_en_service(cloture)`, appelée par le bouton FEC de l'admin (comportement inchangé) et par l'API. `comptabilite.tasks.journees_a_importer(apres_le_numero)` donne la liste des J.
- `api_v2/GUIDELINES.md` : `viewsets.ViewSet` partout (et non plus « Prefer ModelViewSet »), et une section « Comptabilité » qui explique l'exception aux noms schema.org.
- Doc utilisateur `TECH_DOC/comptabilite.md` : import manuel du FEC dans Dolibarr (essayé sur 24.0.1) et création d'une clé pour un logiciel comptable.

/ New "accounting read" API key right; four read-only routes (closures list with a number cursor, entries in FEC column names without ValidDate, FEC file, chart of accounts); one shared go-live refusal rule for the admin and the API.

**Pourquoi / Why :** Chantier 06 (connecteurs vers les logiciels comptables) : la pièce commune à Dolibarr, Dokos, Paheko, Pennylane. Spec : `TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-06-connecteurs-comptables/CHANTIER-06-A-api-comptable.md` (relue par Fable).

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/models.py` | `ExternalApiKey.comptabilite` ; `api_permissions()` : `closure`, `account` |
| `BaseBillet/migrations/0230_externalapikey_comptabilite.py` | `AddField` |
| `comptabilite/tasks.py` | `refus_du_fec_avant_la_mise_en_service`, `journees_a_importer` ; docstring de `mise_en_service_du_lieu` |
| `comptabilite/admin.py` | `exporter_fec` appelle la règle partagée (même message, même comportement) |
| `api_v2/views.py` | `ClosureViewSet` (`list`, `entries`, `fec`), `AccountViewSet` (`list`) |
| `api_v2/serializers.py` | `LigneDEcritureComptableSerializer`, `EcritureComptableSerializer`, `ClotureAImporterSerializer`, `CompteComptableSerializer` |
| `api_v2/urls.py` | routes `closures`, `accounts` |
| `api_v2/openapi-schema.yaml` | les quatre routes, réponses `AccountingNotExportable`, `AccountingConflict` |
| `api_v2/GUIDELINES.md` | `viewsets.ViewSet` ; section « Comptabilité » |
| `Administration/admin_tenant.py` | `ExternalApiKeyAdmin` : le droit dans la liste et la fiche |
| `Administration/management/commands/test_api_key.py` | la clé de test a le droit `comptabilite` |
| `TECH_DOC/comptabilite.md` | import manuel dans Dolibarr ; clé pour un logiciel comptable |
| `tests/pytest/test_api_v2_comptabilite.py` | 15 tests, schéma dédié |

Chaînes i18n ajoutées (source en français) :
- « Comptabilité (lecture) »
- « Le paramètre « after_number » doit être un nombre entier positif : le numéro de la dernière clôture importée. »
- « Cette clôture n'a pas d'écritures à importer : seules les clôtures journalières qui ont des ventes en ont. »
- La phrase du refus de mise en service est **inchangée** (même msgid, déplacée de `comptabilite/admin.py` vers `comptabilite/tasks.py`).

### Preuves / Evidence
- Rouge : 15 failed (`TypeError: ExternalApiKey() got unexpected keyword arguments: 'comptabilite'`), puis, après la migration, 15 failed (routes 404, `refus_du_fec_avant_la_mise_en_service` absente).
- Vert : 15 passed ; voisins `test_fec_equilibre.py`, `test_comptabilite_exports.py`, `test_reprise_clotures.py`, `test_membership_by_wallet.py`, `test_api_v2_wallet_refill.py`, `test_api_v2_liste_des_evenements.py` : 112 passed avec les nouveaux.

| # | Mutation (à la main, sha256 identiques après) | Tuée par |
|---|---|---|
| 1 | `"closure": self.sale` | 12 tests |
| 2 | niveau J retiré du filtre de `journees_a_importer` | liste_ne_donne_que_les_j |
| 3 | J reprise gardée dans la liste | liste_sans_la_j_reprise |
| 4 | `numero_sequentiel__gte` | after_number, j_creee_en_retard |
| 5 | `ValidDate` ajoutée au JSON | entries_egales, sans_valid_date |
| 6 | `Debit` en nombre à virgule | sans_valid_date_et_equilibrees |
| 7 | compte manquant → 500 | compte_manquant_409 |
| 8 | filet du plan retiré de `/accounts/` | accounts_charge_le_plan |
| 9 | comptes inactifs filtrés | accounts_tous_les_comptes |
| 10 | refus de mise en service ignoré par l'API | refus_de_la_j_reprise_meme_regle |
| 11 | J reprise retirée de la règle partagée | refus_meme_regle + `test_reprise_clotures.py::test_fec_refuse_sur_la_j_reprise_avec_le_message` |
| 12 | code `unbalanced_entry` → `missing_account` | ecriture_desequilibree_409 |

Corrections de la relecture de sécurité (Opus) : `after_number` limité à 18 chiffres (M-9 ; au-delà de 4300, `int()` levait une erreur 500) ; `fec/` accepte `Accept: text/plain` (M-14 ; DRF répondait 406), par le rendu `RenduTexteDuFec` ; tests du 403 sur `entries/` et `fec/` sans le droit (M-13). Rouge : 2 failed (`assert 200 == 400`, `assert 406 == 200`) ; vert : 15 passed. Suite complète avant ces corrections : **3902 passed, 1 xfailed, 2 errors** (interblocages dans `test_supprimer_lieux_inactifs.py`, causés par des scripts lancés en parallèle sur la base ; le fichier seul : 55 passed).

Mutation non jouée : « curseur par date » (spec §8). Avec `after_number`, l'API ne reçoit plus d'heure de passage : la mutation n'a plus de sens dans le code. Le test 5 (`test_j_creee_en_retard_est_vue_avec_after_number`) garde le scénario.

---

## Comment tester (a la main) / Manual test
1. Admin du lieu → Clés d'API → Ajouter « Dolibarr », cocher seulement « Comptabilité (lecture) », enregistrer, copier la clé.
2. `curl -sk -H "Authorization: Api-Key <clé>" https://lespass.tibillet.localhost/api/v2/closures/` → `{"results": [...]}`.
3. Avec l'`uuid` d'une J : `.../api/v2/closures/<uuid>/entries/` (JSON, sans `ValidDate`) et `.../fec/` (fichier). Une J dont un produit n'a pas de compte : `409` `missing_account`.
4. `.../api/v2/accounts/` : la liste des comptes.
5. Sans la case « Comptabilité (lecture) » : `403`.

### Verifs automatiques
```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations --check --dry-run
make test ARGS="tests/pytest/test_api_v2_comptabilite.py"
```
