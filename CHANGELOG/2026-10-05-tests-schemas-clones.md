# Schémas de test clonés / Cloned test schemas

**Date :** 2026-10-05
**Migration :** Non

## Resume / Summary
**Quoi / What :** sous pytest, le schéma dédié d'un `FastTenantTestCase` qui manque n'est plus créé en rejouant toutes les migrations : il est copié depuis un schéma modèle `test_modele`, lui-même créé par les migrations une seule fois et refait tout seul quand la liste des migrations du code change. Après la copie, les noms des contraintes UNIQUE et des séquences sont remis comme dans un lieu migré, et le clone reçoit sa propre clé d'empreinte.
/ Under pytest, a FastTenantTestCase's missing schema is no longer built by replaying every migration: it is copied from a `test_modele` template schema, itself built once by migrations and rebuilt automatically when the code's migration list changes. After the copy, UNIQUE constraint and sequence names are restored as in a migrated venue, and the clone gets its own fingerprint key.

**Pourquoi / Why :** chaque schéma coûtait ~55 s de migrations. Après une purge ou une base neuve, ~40 schémas ajoutaient ~40 min à `make test`. Un clone prend ~2,5 s.
/ Each schema cost ~55 s of migrations; ~40 schemas added ~40 min to `make test` after a purge or a fresh database. A clone takes ~2.5 s.

**Périmètre / Scope :** seulement sous pytest et avec `TEST=1`. La création d'un lieu (dev, onboard, préproduction, production) ne change pas : elle rejoue toujours les migrations. Aucun code applicatif touché.
/ pytest and `TEST=1` only. Venue creation (dev, onboard, preproduction, production) is unchanged. No application code touched.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `tests/pytest/schemas_clones.py` | Nouveau : schéma modèle (création, péremption), copie `clone_schema` de django-tenants, noms remis, clé d'empreinte propre / New: template schema, copy, names restored, own key |
| `tests/pytest/conftest.py` | Nouvelle fixture `_schema_de_test_cree_par_clonage` (classe, autouse) : clone le schéma manquant avant le `setUpClass` / New class fixture cloning the missing schema before setUpClass |
| `tests/README.md` | Durées réelles à chaud et à froid / Real warm and cold durations |
| `TECH_DOC/SKILLS/tibillet-test/SKILL.md` | §3 bis : le piège du froid et le clonage / Cold-run trap and cloning |
| `tests/PIEGES.md` | 14.1 à 14.4 : coût à froid, noms perdus par `clone_schema`, données copiées (clé, UUID), modèle figé sur `public` / Cold cost, names lost, copied data, template frozen on public |

### Mesures / Measurements
| Cas / Case | Avant / Before | Après / After |
|---|---|---|
| 1 schéma (`test_paiement_idempotence.py`) | 54,3 s | 2,6 s |
| 5 fichiers, 7 schémas | ~385 s estimés (7 × 55 s) | 31 s en tout, ~2,5 s par schéma |
| Suite complète à chaud (schémas déjà là) | ~10 min | 10 min 22 s, 3423 passed (inchangé) |
| Un schéma pendant la suite complète | ~55 s | 5 à 10 s (la copie ralentit quand la base compte beaucoup de schémas) |
| Suite complète à froid (`make test`, 43 schémas + le modèle) | ~50 min (enquête préalable) | 15 min 31 s, 3423 passed |

---

## Comment tester (a la main) / Manual test

### Test 1 — un schéma à froid
1. Purger UN schéma de test (procédure du skill `tibillet-test`, §3), par exemple `test_paiement_idempotence`.
2. `make test ARGS="tests/pytest/test_paiement_idempotence.py -q --durations=3"`
3. Attendu : la ligne `setup` du premier test dure ~2,5 s (et non ~55 s). 6 passed.

### Test 2 — le modèle se refait seul
1. `DROP SCHEMA test_modele CASCADE` (shell Django, connexion sur `public`), puis purger un schéma de test.
2. Relancer le fichier : le message `[schemas_clones] Schéma modèle « test_modele » absent ou périmé` apparaît (avec `-s`), le setup dure ~1 min une fois, puis ~2,5 s aux suivants.

### Test 3 — clé d'empreinte propre
Lire `hmac_key` dans `laboutik_laboutikconfiguration` de deux schémas clonés : valeurs différentes ; celle de `test_modele` est vide.

### Non couvert
- Les UUID des lignes écrites par les migrations (comptes, TVA, catégorie, correspondances) sont identiques d'un clone à l'autre (PIEGES 14.3).
- Le modèle fige les uuid du FED de `public` (PIEGES 14.4).
- `clone_schema` installe ses fonctions SQL dans le schéma `public` (`public.clone_schema` et ses aides) : c'est le fonctionnement de django-tenants.
