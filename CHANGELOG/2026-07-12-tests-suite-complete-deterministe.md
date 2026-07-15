# Tests : suite complète déterministe / Tests: deterministic full suite

**Date :** 2026-07-12
**Migration :** Non / No

**Quoi / What :** correction de deux défauts de l'infrastructure de test qui rendaient
la suite complète ininterprétable : `pytest tests/pytest/` produisait ~90 `ERROR` alors
que **chaque fichier passait quand on le lançait seul**.

1. **Tri de collecte qui coupait les classes en deux.** `pytest_collection_modifyitems`
   rangeait *chaque test du projet* selon une sous-chaîne de son **nom** (`"list" in name`…)
   pour ordonner le flow API v2 Event. Or le mot **français « liste » contient la
   sous-chaîne anglaise « list »** : le test `test_retourne_liste_vide_...` partait dans un
   autre groupe que ses tests frères, **fragmentant sa classe `FastTenantTestCase`** en deux
   blocs non contigus → `setUpClass`/`tearDownClass` rejoués en plein milieu.
   Désormais on ne réordonne que des **fichiers entiers** (whitelist explicite), jamais des
   tests isolés : aucune classe ne peut plus être fragmentée.

2. **Fuite du schéma courant entre tests.** django-tenants pose `connection.set_tenant(...)`
   et ne revient jamais sur `public`. Le premier test qui « collait » la connexion sur
   `lespass` faisait échouer tous les `FastTenantTestCase` devant créer leur schéma
   (`Can't create tenant outside the public schema`). Une fixture autouse **class-scoped**
   remet `public` **en setup**, et **uniquement pour les `FastTenantTestCase`**.

**Pourquoi / Why :** une suite qui rend 90 erreurs indépendantes du code testé est pire
qu'inutile — elle masque les vraies régressions et fait perdre des heures à chaque session.

**À savoir (piège qui a coûté cher) :** `FastTenantTestCase` **ne supprime pas** son schéma
et ne **rejoue jamais les migrations** sur un schéma existant. Un fichier lancé seul crée son
schéma, qui **persiste** en base de dev et **masque le bug au run suivant**. Et **toute
nouvelle migration périme silencieusement tous les schémas `test_*`**. Procédure de purge
documentée dans `tests/PIEGES.md` 12.5.bis.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `tests/pytest/conftest.py` | Tri de collecte par fichier entier (`ORDRE_DU_FLOW_API_V2_EVENT`) ; fixture autouse class-scoped remettant `public` avant les `FastTenantTestCase` |
| `tests/PIEGES.md` | **12.5.bis** — les deux causes, le mécanisme réel de `FastTenantTestCase`, la procédure de purge des schémas `test_*` |

### Migration
- **Migration nécessaire / Migration required :** Non.
