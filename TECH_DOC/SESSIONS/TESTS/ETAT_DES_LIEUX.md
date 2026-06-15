# État des lieux des tests — Lespass main

Date : 2026-06-11
Repo audité : `/home/jonas/TiBillet/dev/Lespass` (branche main)
Repo de référence V2 : `/home/jonas/TiBillet/dev/lespass-main`

Ce document dit : ce qui existe, ce qui passe, ce que ça couvre.
Document écrit en FALC : phrases courtes, une idée par phrase.

---

## 1. Résultats des runs (2026-06-11)

| Suite | Commande | Résultat | Durée |
|---|---|---|---|
| pytest DB-only | `docker exec lespass_django poetry run pytest tests/pytest/ -q` | ✅ **229 passed** | 49 s |
| E2E Python (Playwright) | `docker exec lespass_django poetry run pytest tests/e2e/ -q` | ✅ **8 passed** | 17 s |
| Legacy django_test | `docker exec lespass_django poetry run pytest tests/django_test/ -q` | ❌ **2 failed, 2 passed** | 2 min 48 |
| E2E TypeScript (Playwright) | `cd tests/playwright && yarn test:chromium:console` | ✅ **67 passed, 1 skipped** | **10 min 54** |

**Important** : `tests/django_test/` n'est PAS lancé par la commande par défaut.
Il est rouge et très lent. Voir PLAN_SIMPLIFICATION.md.

### 1.b Détail suite TypeScript

- 68 tests dans 42 specs (certains specs ont plusieurs tests).
- Tout est vert. 1 test skipped.
- Séquentiel (`workers=1`), donc la durée est la somme de tous les tests.
- Les 12 specs qui passent par un **vrai checkout Stripe** sont les plus lents :
  mesures relevées pendant le run — spec 43 (validation manuelle + Stripe) : 36 s,
  spec 44 (contribution crowds Stripe) : 22 s. Les specs sans Stripe font 1 à 5 s.
  Les specs Stripe représentent donc à eux seuls plus de la moitié des ~11 minutes.

---

## 2. Coverage (pytest DB-only, hors migrations)

Mesurée avec `pytest-cov` (installé dans le venv du container via pip,
pas dans `pyproject.toml`). Fichier brut : `tests/coverage_pytest.json`.

| App | Lignes | Coverage |
|---|---|---|
| MetaBillet | 112 | 78,6 % |
| AuthBillet | 550 | 59,1 % |
| fedow_connect | 946 | 36,4 % |
| api_v2 | 1 114 | 35,1 % |
| BaseBillet | 6 466 | 30,8 % |
| Administration | 5 430 | 30,7 % |
| crowds | 1 059 | 30,7 % |
| ApiBillet | 1 437 | 28,9 % |
| PaiementStripe | 191 | 23,0 % |
| **TOTAL** | **17 305** | **32,3 %** |

Lecture FALC :
- Les **modèles** sont bien couverts (ex : `crowds/models.py` 70 %, `MetaBillet/models.py` 87 %).
- Les **vues** sont mal couvertes (ex : `crowds/views.py` 13 %, `PaiementStripe/views.py` 20 %).
- C'est normal : les vues sont surtout testées par les 42 specs Playwright TS,
  qui ne comptent pas dans cette coverage Python.
- Les **tâches Celery** sont presque pas couvertes (`crowds/tasks.py` 19 %).

---

## 3. Inventaire — pytest DB-only (43 fichiers, 202 fonctions, 229 tests exécutés)

| Domaine | Fichiers | Tests | Ce que ça teste |
|---|---|---|---|
| Comptabilité / LNE | 8 (`test_comptabilite_*`, `test_demo_data_ventes`) | ~48 | ClotureCaisse, HMAC, exports CSV, Celery, service de calcul |
| OTP / Auth | 2 (`test_otp_*`) | 33 | Génération, validation, session, TTL |
| Événements | 10 (`test_event_*`, `test_events_list`) | ~30 | CRUD API v2, images, wizard, propositions, adresses |
| SEO / Explorer | 4 (`test_seo_*`) | 19 | Cache fragments, tags, indexation, agrégation points carte |
| Fédération | 3 (`test_federation_*`) | 15 | Config root, tags auto, vues d'intégration |
| Tiers-lieux / Géo | 2 (`test_tiers_lieux`, `test_widget_form_field_geo`) | 18 | Modèle, API, widget géoloc |
| Wallet / Recharge | 1 (`test_api_v2_wallet_refill`) | 11 | Recharge cadeau via API v2 + Fedow |
| Crowds | 4 (`test_crowd_*`) | ~12 | Initiatives, votes, budget items |
| Adhésions | 2 (`test_membership_*`) | 4 | Création schema.org, filtre par wallet |
| Réservations | 1 (`test_reservation_create`) | ~2 | Création réservation API |
| Divers | 6 (postal address, produit, proxys, middleware) | ~12 | CRUD adresses, retrieve produit, signaux proxy, redirect doc |

Constat : la couverture pytest est **déséquilibrée**.
Comptabilité et OTP sont très testés. Adhésions et réservations très peu —
ils reposent presque entièrement sur les specs TypeScript.

---

## 4. Inventaire — E2E Python (`tests/e2e/`, 1 fichier, 8 tests)

| Fichier | Tests | Ce que ça teste |
|---|---|---|
| `test_explorer_ux_pills_tags.py` | 8 | Page racine /explorer/, pills, tags, UX SEO |

C'est le seul test E2E déjà migré au format Python (le format cible, comme la V2).

---

## 5. Inventaire — Playwright TypeScript (42 specs, ~42 tests)

Config : `workers=1`, séquentiel, timeout 60 s/test, chromium.
12 specs paient avec la vraie carte de test Stripe (`4242…`).

| Domaine | Specs | Détail |
|---|---|---|
| Adhésions | 20 | simple, récurrente (+annulation), validation manuelle, prix libre (+multi), prix zéro, AMAP, SSA, formulaires dynamiques (x3 !), états de compte, SEPA |
| Admin | 8 | configuration, avoir, ajouter paiement, annuler adhésion/résa, listes, M2M adhésions obligatoires, form custom |
| Réservations / Billetterie | 5 | événement anonyme gratuit/payant, form dynamique, validations, limites de stock |
| Crowds | 3 | participation, résumé, contribution Stripe |
| Divers | 6 | login, compte utilisateur, duplication produit, overflow numérique, explorer markers, thème/langue |

Problèmes relevés :
- **3 specs quasi identiques** sur adhésion + formulaire dynamique (08, 12, 27).
- **Numéro 35 utilisé 3 fois** (membership-list-status, reservation-cancel, explorer-markers).
- `tests/README.md` annonce « 10 API + 16 E2E » : **document obsolète** (réalité : 229 + 42).

---

## 6. Le modèle V2 (`../lespass-main`) — ce qu'on copie

La V2 a 992 tests pytest (~30 s) + 120 tests E2E Playwright **en Python** (~3 min).
Zéro TypeScript. Tout se lance avec pytest.

Ce que la V2 fait et qu'on doit reprendre :

1. **Playwright Python dans `tests/e2e/`** avec un conftest dédié :
   fixture `page` (chromium headless, résolution `*.tibillet.localhost` → 172.17.0.1),
   `ignore_https_errors=True`, dual-mode container/host.
2. **Login instantané** : endpoint `__test_only__/force_login/` protégé par
   `E2E_TEST_TOKEN` + `DEBUG=True` → cookie de session en 100 ms au lieu
   d'un login UI de 5 s par test.
3. **Markers pytest** : `@pytest.mark.e2e`, `@pytest.mark.integration`
   → on filtre avec `-m`.
4. **Fixtures factory** : `login_as(page, email)`, `django_shell(code, schema=...)`,
   `create_event(api_key)`, `fill_stripe_card(page, email)`.
5. **Vérification DB après action navigateur** via `django_shell` —
   pas de scripts shell séparés.
6. **`data-testid` partout** pour des sélecteurs stables.

Attention : les deux repos utilisent les **mêmes noms de containers**
(`lespass_django`, etc.). On ne peut pas faire tourner les deux stacks en même temps.
Actuellement, c'est le repo main qui est monté dans `lespass_django`.

---

## 7. Dossiers annexes

| Dossier | Contenu | Verdict |
|---|---|---|
| `tests/scripts/` | `setup_test_data.py`, `verify_*.py` — appelés par les specs TS pour vérifier la DB | Vivront tant que les specs TS vivent ; la V2 les remplace par la fixture `django_shell` |
| `tests/stress/` | Tests de charge ponctuels | Hors suite, à garder tel quel |
| `tests/django_test/` | 2 fichiers legacy (management commands, sales API) | ❌ Rouge, lent, à traiter (voir plan) |
| `tests/PIEGES.md` | ~80 pièges documentés | ✅ Source de vérité, à jour |
| `tests/README.md` | Guide de lancement | ⚠️ Obsolète, à réécrire |
