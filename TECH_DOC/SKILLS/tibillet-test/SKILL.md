---
name: tibillet-test
description: Lancer, diagnostiquer et écrire les tests du projet TiBillet/Lespass (Django multi-tenant django-tenants + pytest + Playwright). Utilise ce skill DÈS QU'on parle de lancer les tests, d'un test qui échoue, de pytest, de la suite qui casse, de "les tests sont rouges", "relance les tests", "vérifie que ça passe", d'écrire un nouveau test, ou de FastTenantTestCase / schémas de test / erreurs multi-tenant en test. Contient l'arbre de décision des échecs typiques (schémas test_* périmés, fuite de schéma, classes fragmentées, serveur down) qui ont déjà coûté des heures de debug.
---

# Tests TiBillet / Lespass — lancer, diagnostiquer, écrire

Source de vérité complémentaire : `tests/PIEGES.md` (~80 pièges, section 12.x pour
l'infra) et `tests/README.md`. **Lire `tests/PIEGES.md` AVANT d'écrire un nouveau test.**

---

## 0. Les 4 règles qui évitent 90 % des pertes de temps

1. **Un fichier qui passe seul ne prouve RIEN.** Les schémas `test_*` persistent en base
   de dev et masquent les bugs. Voir §3.
2. **La suite tourne sur la base de DEV**, pas sur une base de test. `conftest.py`
   neutralise `django_db_setup`. Il n'y a **pas de rollback global**.
3. **16 fichiers de tests tapent le serveur live** (HTTP via `requests`). Si le serveur
   est down → `502 Bad Gateway` en cascade. Ce ne sont **pas** des régressions.
4. **Jamais de `git` destructif** pour "réparer" un test. Alerter le mainteneur.

---

## 1. Lancer les tests

```bash
# Suite DB-only (~4-8 min selon l'état des schémas)
docker exec lespass_django poetry run pytest tests/pytest/ -q

# Un fichier / un test
docker exec lespass_django poetry run pytest tests/pytest/test_xxx.py -q
docker exec lespass_django poetry run pytest "tests/pytest/test_x.py::TestC::test_m" -q

# Raccourcis
docker exec lespass_django poetry run pytest tests/pytest/ --last-failed
docker exec lespass_django poetry run pytest tests/pytest/ --stepwise   # stop au 1er échec

# E2E navigateur (~4 min) — EXIGE le serveur live
docker exec lespass_django poetry run pytest tests/e2e/ -v -s
```

**Le serveur** : le mainteneur le tient dans **byobu**. Ne PAS lancer `runserver_plus`
soi-même (port 8002 déjà pris). Si les tests HTTP renvoient 502 → demander au mainteneur
de relancer son serveur.

**Ne jamais** utiliser `-n` / `pytest-xdist` (parallélisme) : la base de dev est
partagée, les tests se marcheraient dessus.

---

### Lancer par domaine (plus rapide qu'une suite complète)

**D'abord : vérifier que le glob matche vraiment.** Un glob qui ne correspond à aucun
fichier fait échouer pytest (`file or directory not found`) — et les noms de fichiers
bougent. Toujours lister avant de lancer :

```bash
ls tests/pytest/ | grep -E "membership|controlvanne"   # adapte le motif
```

Globs vérifiés au 2026-07-12 (re-vérifie s'ils ne matchent plus) :

```bash
# Adhésions
docker exec lespass_django poetry run pytest tests/pytest/test_membership_*.py tests/pytest/test_stripe_membership_*.py -v
# Événements / réservations
docker exec lespass_django poetry run pytest tests/pytest/test_event_*.py tests/pytest/test_reservation_*.py -v
# LaBoutik / POS / caisse
docker exec lespass_django poetry run pytest tests/pytest/test_pos_*.py tests/pytest/test_caisse_*.py tests/pytest/test_cloture_*.py tests/pytest/test_paiement_*.py -v
# Controlvanne (tireuse)
docker exec lespass_django poetry run pytest tests/pytest/test_controlvanne_*.py -v
# Crowds / Fedow
docker exec lespass_django poetry run pytest tests/pytest/test_crowd_*.py tests/pytest/test_fedow_core.py -v
```

**N'invente jamais un glob par analogie** (`test_adhesions_*`, `test_sepa_*`,
`test_laboutik_*` ont l'air plausibles : **aucun n'existe**). Liste, puis lance.

**Carte Stripe de test** (E2E) : `4242 4242 4242 4242`, nom `Douglas Adams`, date `12/42`,
code `424`.

**Playwright** (E2E, si absent du conteneur) :
```bash
docker exec -u root lespass_django /DjangoFiles/.venv/bin/playwright install-deps chromium
docker exec lespass_django poetry run playwright install chromium
```

---

## 2. Deux suites, deux objectifs

| Suite | Dossier | Teste | Navigateur |
|---|---|---|---|
| DB-only | `tests/pytest/` | modèles, serializers, vues, API, validations serveur, Stripe mock | non |
| E2E | `tests/e2e/` | JS, web components, HTMX swaps, SweetAlert2, NFC, cross-tenant | oui (Playwright) |

Règle : ça teste du Python → pytest. Ça teste du JS/CSS/navigateur → E2E.

---

## 3. ⚠️ LE PIÈGE CENTRAL : les schémas `test_*` persistent

`FastTenantTestCase` (django-tenants) :
- `setUpClass` **réutilise** un schéma existant et ne **rejoue JAMAIS les migrations**.
- `tearDownClass` fait **uniquement** `set_schema_to_public()` — il **ne droppe rien**
  (contrairement à `TenantTestCase`, non utilisé ici).

Trois conséquences qu'il faut avoir en tête **en permanence** :

1. **Lancer un fichier seul crée son schéma, qui reste en base.** Au run suivant il
   passe — *même si le bug est toujours là*. **Ne jamais conclure « c'est réparé »**
   après un run qui a bénéficié de schémas pré-existants.
2. **Toute nouvelle migration périme silencieusement tous les schémas `test_*`.** Ils ne
   sont jamais re-migrés → `column ... does not exist`. **Purger après toute migration
   touchant une TENANT_APP.**
3. `docker compose down -v` efface ces schémas → des erreurs « déjà corrigées »
   réapparaissent. C'est normal.

**Purger (état à froid)** — indispensable pour juger un fix d'infra de test :

```python
# docker exec lespass_django poetry run python /DjangoFiles/manage.py shell
from django.db import connection
connection.set_schema_to_public()
FILTRE = r'test\_%'          # filet de sécurité : UNIQUEMENT les schémas test_*
with connection.cursor() as c:
    c.execute('select uuid, schema_name from "Customers_client" where schema_name like %s', [FILTRE])
    tenants = c.fetchall()
    # Les FK modernes (seo_seocache, fedow_*, discovery_pairingdevice…) bloquent le DELETE :
    # on vide d'abord toutes les tables qui référencent Customers_client.
    c.execute('''select distinct tc.table_name, kcu.column_name
        from information_schema.table_constraints tc
        join information_schema.key_column_usage kcu on tc.constraint_name = kcu.constraint_name
        join information_schema.constraint_column_usage ccu on tc.constraint_name = ccu.constraint_name
        where tc.constraint_type='FOREIGN KEY' and ccu.table_name='Customers_client'
          and tc.table_schema='public' ''')
    for table, colonne in c.fetchall():
        c.execute(f'DELETE FROM "{table}" WHERE "{colonne}" IN '
                  f'(SELECT uuid FROM "Customers_client" WHERE schema_name LIKE %s)', [FILTRE])
    c.execute('DELETE FROM "Customers_client" WHERE schema_name LIKE %s', [FILTRE])
    for _uuid, nom in tenants:
        c.execute(f'DROP SCHEMA IF EXISTS "{nom}" CASCADE')
```

Le `DELETE` via l'ORM **échoue** (cascade tenant → `relation
"BaseBillet_configuration_federated_with" does not exist`, piège 12.5). SQL direct
obligatoire. **C'est destructif : demander l'accord du mainteneur avant de purger.**

---

## 4. Arbre de décision des échecs

| Message | Cause | Quoi faire |
|---|---|---|
| `502 Bad Gateway` (nginx) sur ~15 tests | Le **serveur live est down** | Demander au mainteneur de relancer byobu. Ce n'est **pas** une régression. |
| `column BaseBillet_configuration.module_xxx does not exist` | Schéma `test_*` **périmé** (créé avant la migration) | Purger les schémas `test_*` (§3) |
| `Can't create tenant outside the public schema. Current schema is lespass` | **Fuite de schéma** : un test a collé la connexion sur `lespass` | La fixture autouse class-scoped du conftest doit remettre `public` avant `setUpClass` des `FastTenantTestCase` |
| `duplicate key ... Customers_client_schema_name_key` | **Client orphelin** (schéma droppé, row restée) | Piège 12.5 → purge SQL (§3) |
| `relation "BaseBillet_xxx" does not exist` (hors test) | Le code tourne sur le schéma **public** | `print(connection.schema_name)`. Utiliser `tenant_context(tenant)` |
| `relation "..." does not exist` **at teardown** | Un finalizer de fixture nettoie des objets tenant alors que la connexion est sur `public` | Ne **jamais** remettre `public` en teardown de test |
| Chaque fichier **passe seul**, la suite **casse** | Pollution entre tests (fuite de schéma, ou classe fragmentée) | §5 |
| `assert True is False` sur `module_kiosk` | État de la **base de dev** (module activé) | Pas une régression du code |

---

## 5. « Ça passe seul mais pas en suite » — méthode

1. **Vérifier qu'aucune classe n'est fragmentée** (doit afficher `AUCUN`) :
   ```bash
   docker exec lespass_django poetry run pytest tests/pytest/ --collect-only -q \
     | grep "::" | sed 's/::[^:]*$//' | awk '
     { if ($0 != prev) { blocs[$0]++; prev=$0 } }
     END { n=0; for (c in blocs) if (blocs[c] > 1) { print blocs[c] " blocs -> " c; n++ }
           if (n==0) print "AUCUN" }'
   ```
   Une classe en 2+ blocs → pytest rejoue `setUpClass`/`tearDownClass` au milieu → état cassé.

2. **Ne jamais trier les tests par sous-chaîne de leur NOM** dans
   `pytest_collection_modifyitems`. Le projet est FALC, les tests sont en **français** :
   le mot **« liste » contient « list »**, « lien » contient... etc. Un tri
   `if "list" in name` éclate les classes. **Trier par FICHIER entier**, jamais par test.

3. **Isoler le coupable** : lancer le fichier qui casse précédé du fichier suspect.
   Un test qui utilise le client de test Django sur `lespass.tibillet.localhost` colle la
   connexion sur `lespass` (le middleware django-tenants ne la restaure jamais).

4. **Toujours re-valider À FROID** (schémas purgés). Sinon on valide un faux vert.

---

## 6. Écrire un test

**Règles d'or** : atomique (1 test = 1 action), noms verbeux en français, commentaires
bilingues FR/EN, FALC.

**Deux conftest séparés** : `tests/pytest/conftest.py` (DB) et `tests/e2e/conftest.py`
(navigateur). Ne pas créer de conftest racine.

**Pièges multi-tenant les plus fréquents** :
- `schema_context('lespass')` pose un **`FakeTenant`** : tout modèle qui lit
  `connection.tenant.uuid` **crashe**. Pour tout `create()` ou code qui touche le tenant →
  `tenant_context(tenant)`.
- `CarteCashless` est en **SHARED_APPS** (schéma `public`) → pas de `FastTenantTestCase`.
- Nettoyer les objets SHARED **dans un `tenant_context`** (le cascade-collect du delete a
  besoin des tables tenant).
- `Reservation.objects.create(status=VALID)` ne déclenche **pas** les signaux.
- `_, _created = get_or_create()` : `_` comme variable locale **casse `gettext`**.

**Ne JAMAIS** utiliser `transaction=True` / `TransactionTestCase` : sans base de test, le
teardown **flushe la vraie base de dev**.

---

## 7. Après le run — rapporter honnêtement

- Donner les **chiffres** (`X passed, Y failed, Z errors`), pas « ça marche ».
- **Distinguer** : régression de la session / échec préexistant / serveur down / état de
  la base de dev. Si tu ne peux pas établir de baseline « avant » (pas de `git stash` —
  interdit), **le dire** plutôt que d'affirmer.
- Preuve qu'un échec est préexistant : le reproduire **sans** le code de la session
  (ex. `--ignore=<mon_fichier>`), ou montrer que la cause n'a aucun rapport.
- Un échec « corrigé » par un run qui a bénéficié de schémas pré-existants **n'est pas
  corrigé** (§3).
