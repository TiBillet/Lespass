# Plan de simplification des tests — Lespass main

Date : 2026-06-11

Objectif demandé par le mainteneur :
1. Une **suite essentielle** rapide : « être sûr que tout roule » sur les 4 flux
   vitaux — recharge de wallet, paiement QR code, adhésion, billetterie.
2. Une **suite complète** pour les sessions de dev et la CI.
3. Retirer ou fusionner les tests trop longs et peu utiles.
4. Migrer vers du **Python** (pytest + Playwright Python) quand c'est utile,
   sur le modèle de la V2 (`../lespass-main`).

---

## 1. Suite ESSENTIELLE (smoke) — utilisable dès aujourd'hui

Ces tests existent déjà et couvrent 3 des 4 flux vitaux.
Durée totale : **~15 secondes**.

```bash
docker exec lespass_django poetry run pytest \
  tests/pytest/test_api_v2_wallet_refill.py \
  tests/pytest/test_membership_create.py \
  tests/pytest/test_membership_by_wallet.py \
  tests/pytest/test_reservation_create.py \
  tests/pytest/test_event_create.py \
  tests/pytest/test_events_list.py \
  -q
```

| Flux vital | Couvert par | État |
|---|---|---|
| Recharge wallet | `test_api_v2_wallet_refill.py` (11 tests) | ✅ |
| Adhésion | `test_membership_create.py` + `test_membership_by_wallet.py` | ✅ (léger) |
| Billetterie / réservation | `test_event_create.py` + `test_reservation_create.py` + `test_events_list.py` | ✅ (léger) |
| Paiement QR code | — | ❌ **À écrire** (voir TESTS_RESTANTS.md, priorité 1) |

### Étape suivante recommandée : un marker `smoke`

Comme la V2 utilise des markers (`e2e`, `integration`), ajouter dans `pytest.ini` :

```ini
markers =
    smoke: tests essentiels des 4 flux vitaux (wallet, qrcode, adhesion, billetterie)
```

Puis poser `pytestmark = pytest.mark.smoke` en tête des fichiers ci-dessus.
La commande devient simplement :

```bash
docker exec lespass_django poetry run pytest tests/pytest/ -m smoke -q
```

---

## 2. Suite COMPLÈTE

```bash
# Backend (49 s, 229 tests)
docker exec lespass_django poetry run pytest tests/pytest/ -q

# E2E Python (17 s, 8 tests)
docker exec lespass_django poetry run pytest tests/e2e/ -q

# E2E TypeScript (42 specs, séquentiel)
cd tests/playwright && yarn test:chromium:console
```

---

## 3. Tests à retirer ou fusionner

### 3.1 `tests/django_test/` — legacy, rouge, lent → à vider

- 4 tests, **2 en échec**, 2 min 48 de run. Pas inclus dans la suite par défaut.
- Personne ne les lance, donc personne ne voit qu'ils sont rouges.
- Causes mesurées (run du 2026-06-11) :
  - `test_management_commands.py` est un `TestCase` classique qui **recrée une
    base de test complète** (toutes les migrations) à chaque run → c'est lui
    qui coûte les minutes. L'échec : `mock_email_admin.delay.called` est False,
    le comportement d'envoi d'email a changé depuis l'écriture du test.
  - `test_sales_api.py` : `RuntimeError: Database access not allowed` — il est
    hors de `tests/pytest/` et ne profite pas de la fixture
    `_enable_db_access_for_all` du conftest. Incompatible avec l'architecture
    de test actuelle (DB dev partagée, pas de DB de test).
- Proposition :
  - `test_management_commands.py` : migrer le test vert (`get_login_link`) vers
    `tests/pytest/`, supprimer le test rouge (`launch_payment_success`) ou le
    réécrire avec le mock Stripe du conftest.
  - `test_sales_api.py` : réécrire en pytest moderne ou supprimer si l'API
    sales est couverte ailleurs.
  - Puis supprimer le dossier.

### 3.2 Specs TypeScript redondants → fusionner

| Specs | Problème | Action |
|---|---|---|
| 08 (ssa-with-forms), 12 (anonymous-membership-dynamic-form), 27 (dynamic-form-full-cycle) | 3 fois le même flux « adhésion + formulaire dynamique » à variantes près | Garder **27** (le plus complet), supprimer 08 et 12 |
| 21 (account-states) + 21 (event-quick-create) | Même numéro | Renuméroter |
| 35 x3 (membership-list-status, reservation-cancel, explorer-markers) | Même numéro 3 fois | Renuméroter |
| 04 / 22 (recurring + recurring-cancel) | 2 specs pour un cycle | Fusionner en 1 spec « cycle récurrent complet » |

### 3.3 Durées mesurées de la suite TS (run du 2026-06-11)

- Suite complète : **10 min 54** (67 passed, 1 skipped, séquentiel).
- Les specs **avec vrai checkout Stripe** (12 specs) coûtent 20 à 40 s chacun
  (mesuré : spec 43 = 36 s, spec 44 = 22 s). C'est plus de la moitié de la durée totale.
- Les specs sans Stripe font 1 à 5 s.

Conséquence pour la suite essentielle E2E : ne garder que **2 parcours Stripe**
en smoke (1 billetterie, 1 adhésion), et lancer les 10 autres uniquement dans
la suite complète. Les specs Stripe redondants (08, 12 → fusion dans 27 ;
15 + 17 prix libre → 1 seul) sont les premiers à retirer : chaque suppression
fait gagner ~30 s à chaque run complet.

---

## 4. Migration TypeScript → Playwright Python (modèle V2)

### Pourquoi

- Une seule techno de test (pytest) : plus de yarn/node pour tester.
- La V2 a déjà tout le socle : on **copie**, on n'invente pas.
- Vérification DB dans le même test via la fixture `django_shell`
  (fini les `tests/scripts/verify_*.py` appelés depuis TypeScript).

### Prérequis à porter depuis la V2 (1 session)

1. `AuthBillet/views_test_only.py` : endpoint `force_login` protégé par
   `E2E_TEST_TOKEN` + `DEBUG=True` → login en 100 ms.
2. Le `tests/e2e/conftest.py` V2 : fixtures `browser`, `page`, `login_as`,
   `login_as_admin`, `django_shell`, `fill_stripe_card`, dual-mode container/host.
3. Le marker `e2e` dans `pytest.ini`.

### Vagues de migration

| Vague | Specs TS concernés | Pourquoi commencer là |
|---|---|---|
| **1. Validations client (sans Stripe)** | 18, 20, 28 | La V2 a déjà `test_membership_validations.py` et `test_reservation_validations.py` en Python : copie quasi directe |
| **2. Smoke parcours payants** | 09 (billetterie anonyme), 11 (adhésion anonyme) | Ce sont les 2 parcours d'argent essentiels ; la V2 a `test_stripe_smoke.py` comme modèle |
| **3. Crowds** | 23, 24, 44 | La V2 a `test_crowds_participation.py` |
| **4. Admin** | 02, 26, 32–38 | Patterns admin Unfold déjà en V2 (`test_admin_*.py`) |
| **5. Le reste** | adhésions spécifiques (AMAP, SSA, SEPA, états) | Au fil de l'eau, à chaque fois qu'un spec TS casse |

Règle simple : **on ne réécrit pas un spec TS qui marche pour le plaisir**.
On migre une vague quand on touche au domaine, ou quand un spec devient rouge.
À la fin de chaque vague, on supprime les specs TS migrés.

### Critère « pytest plutôt que E2E »

Avant de migrer un spec TS en E2E Python, se poser la question de la V2 :
- Le spec teste de la **logique serveur** (statuts, montants, droits) ?
  → le réécrire en **pytest DB-only** (50× plus rapide), pas en E2E.
- Le spec teste du **JS / HTMX / rendu navigateur** ?
  → E2E Playwright Python.

Beaucoup des 20 specs « adhésions » testent en réalité de la logique serveur
à travers le navigateur. La cible raisonnable est : **~10-15 E2E Python**
(parcours critiques avec Stripe et HTMX) + le reste en pytest.

---

## 5. Documentation à mettre à jour

| Fichier | Action |
|---|---|
| `tests/README.md` | Réécrire : il annonce « 10 API + 16 E2E », la réalité est 229 + 8 + 42. Documenter les 2 suites (smoke / complète) et les durées. |
| `tests/PIEGES.md` | OK, à jour. Ajouter un sommaire (80 pièges, navigation difficile). |
| `CLAUDE.md` / `GUIDELINES.md` | Ajouter la commande smoke une fois le marker posé. |
