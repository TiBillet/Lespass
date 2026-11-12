# Anonymiser les copies de production / Anonymise production dumps

**Date :** 2026-11-12
**Migration :** Non

## Resume / Summary

**Quoi / What :** un script autonome, `seo/scripts_observatoire/anonymiser_dump.py`, lit un
dump PostgreSQL texte (Lespass, LaBoutik V1) ou une base SQLite (Fedow) et écrit une copie
où les e-mails, clés API, mots de passe, clés RSA, noms, prénoms, pseudos et téléphones sont
remplacés. Ce n'est pas une commande Django.
/ A standalone script that writes a copy of a production dump with e-mails, API keys,
passwords, RSA keys, names and phone numbers replaced. Not a Django command.

**Pourquoi / Why :** travailler sur de vraies données (observatoire, dev) sans y laisser les
données personnelles ni les secrets de la production.
/ Work on real data without keeping production personal data and secrets.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `seo/scripts_observatoire/anonymiser_dump.py` | Nouveau : le script (bibliothèque standard seulement) |
| `seo/scripts_observatoire/README.md` | Nouveau : mode d'emploi |
| `tests/pytest/test_anonymiser_dump.py` | Nouveau : 35 tests sur données fabriquées |
| `TECH_DOC/SESSIONS/OBSERVATOIRE/CHANTIER-03-anonymisation-des-dumps.md` | Nouveau : spec |
| `TECH_DOC/SESSIONS/OBSERVATOIRE/INDEX.md` | Ligne du chantier 03 |

---

## Comment tester (a la main) / Manual test

### Test 1 — dump LaBoutik de dev
1. `cp ../LaBoutik/Backup/dumps/*.sql.gz /tmp/essai/laboutik.sql.gz`
2. `python3 seo/scripts_observatoire/anonymiser_dump.py /tmp/essai/laboutik.sql.gz`
3. Attendu : code 0, `controle final : OK`, aucune valeur réelle dans le rapport.

### Test 2 — la copie se charge
1. Lancer un Postgres jetable sans réseau :
   `docker run -d --rm --name essai_pg --network none -e POSTGRES_PASSWORD=essai postgres:13-bookworm`
2. `zcat /tmp/essai/laboutik.anonyme.sql.gz | docker exec -i essai_pg psql -q -v ON_ERROR_STOP=1 -U postgres -d postgres`
3. Attendu : code 0 (contraintes d'unicité comprises).
4. `docker exec essai_pg psql -U postgres -d laboutik -c 'select email, name from "APIcashless_membre" limit 5'`
   → e-mails vides ou en `@anonyme.invalid`, noms en `Anonyme-xxxxxx`.
5. `docker stop essai_pg`

### Test 3 — dump Lespass de dev (multi-tenant)
1. `docker exec lespass_postgres pg_dumpall -U lespass_postgres_user | gzip > /tmp/essai/lespass_dev.sql.gz`
2. Anonymiser, puis charger comme au test 2 (base `tibillet`).
3. Attendu : code 0 aux deux étapes ; `AuthBillet_tibilletuser.email` tout en `@anonyme.invalid`.

### Test 4 — les trois bases ensemble
Passer les trois fichiers dans la même commande, puis vérifier qu'un e-mail présent dans
Lespass et dans Fedow a le même faux e-mail des deux côtés.

### Tests automatiques
`docker exec lespass_django poetry run pytest tests/pytest/test_anonymiser_dump.py -q`
(35 tests). 26 mutations volontaires du script ont chacune fait échouer au moins un test.

### Test 5 — arrêt en cours de route
Lancer le script sur une grosse base SQLite, puis `kill -TERM` pendant le traitement.
Attendu : code 143, et plus aucun fichier `*.travail-PAS-ENCORE-ANONYME`.
