---
apply: always
---

# 🧪 Guide des Tests — Lespass (TiBillet) / Tests Guide

Ce document explique comment lancer les tests et où écrire les nouveaux.
Il est écrit pour être facile à comprendre, même si vous débutez.
*This document explains how to run the tests and where to write new ones.*

**À lire avant d'écrire un test : [`tests/PIEGES.md`](PIEGES.md)** (~80 pièges documentés).

Dernière mise à jour : 2026-07-12.

---

## 🤖 Skill agent IA — `TECH_DOC/SKILLS/tibillet-test/`

Le skill qui apprend à un agent (Claude Code) à **lancer et diagnostiquer** les tests de
ce projet vit dans **`TECH_DOC/SKILLS/tibillet-test/`**, avec tous les autres skills du
projet (voir `TECH_DOC/SKILLS/README.md`). Il porte l'arbre de décision des échecs typiques
(schémas `test_*` périmés, fuite de schéma multi-tenant, classes fragmentées par le tri de
collecte, `502` quand le serveur live est down) et la procédure de purge à froid.

**Si tu découvres un nouveau piège d'infra de test, mets `PIEGES.md` ET le skill à jour
dans le même commit.**

`.claude/` n'est jamais committé (outillage local). Chaque dev crée donc le lien une
fois, depuis la racine du dépôt :

```bash
mkdir -p .claude/skills
ln -sfn "$(pwd)/TECH_DOC/SKILLS/tibillet-test" .claude/skills/tibillet-test
```

Le lien doit être **absolu** (`$(pwd)/...`) : un lien relatif n'est pas résolu de façon
fiable par le chargeur de skills. Relancer Claude Code après création du lien.

---

## 🗺️ Les deux suites / The two suites

| Suite | Dossier | Outil | Durée | Rôle |
|---|---|---|---|---|
| **Backend DB-only** | `tests/pytest/` | pytest | ~1 min 30 | Modèles, vues, API, validations serveur, **Stripe mocké** |
| **E2E navigateur** | `tests/e2e/` | Playwright **Python** | ~9 à 12 min | Validations JS, HTMX, admin Unfold, parcours complets, **Stripe réel** et **Fedow réel** |

> Pas de compteur de tests dans ce document : il change à chaque session et
> devient faux plus vite qu'on ne le corrige. Pour le nombre du jour :
> `pytest tests/pytest/ --collect-only -q | tail -1`.

L'ancienne suite TypeScript (`tests/playwright/`) a été **entièrement migrée
en Python puis supprimée le 2026-06-11** (42 specs → 0, dossier et outillage
Node/yarn retirés du projet).

Règle de décision / Decision rule:

- Ça teste du **Python / de la logique serveur** ? → `tests/pytest/` (50× plus rapide).
- Ça teste du **JS / HTMX / rendu navigateur** ? → `tests/e2e/` (Playwright Python).

---

## 🚀 Lancer les tests / Running the tests

Trois modes, du plus rapide au plus complet. Le choix se fait sur **ce qu'on
accepte de ne pas vérifier**, pas seulement sur la durée.

```bash
# --- 1. BACKEND SEUL (~1 min 30) ---
# Aucun prérequis : ni serveur, ni navigateur, ni Stripe. Stripe est mocké.
docker exec lespass_django poetry run pytest tests/pytest/ -q

# --- 2. E2E SANS STRIPE (~9 min) ---
# Les parcours qui attendent un webhook Stripe sont IGNORÉS — et nommés
# en rouge en fin de run, impossible de les rater.
docker exec lespass_django poetry run pytest tests/e2e/ -q

# --- 3. E2E COMPLET (~12 min) ---
# Lancer `stripe listen` sur l'hôte AVANT, dans un autre terminal.
docker exec -e E2E_STRIPE_LISTEN=1 lespass_django poetry run pytest tests/e2e/ -q

# --- Raccourcis utiles ---
docker exec lespass_django poetry run pytest tests/ --last-failed   # seuls les échecs précédents
docker exec lespass_django poetry run pytest tests/pytest/ -m integration  # API v2 seulement
```

**L'écart entre les modes 2 et 3 n'est que de ~3 min.** Le mode 2 n'existe pas
pour gagner du temps, mais pour pouvoir lancer les E2E **sans avoir à démarrer
`stripe listen`**. Dès qu'on touche au paiement, au Fedow ou aux adhésions, c'est
le mode 3 qui fait foi.

**Ordre conseillé : les E2E AVANT pytest.** Les E2E créent de vraies ventes dans
le tenant de développement ; un test pytest qui compte largement peut en être
pollué. C'est déjà arrivé.

### Prérequis E2E / E2E prerequisites

1. Le serveur Django tourne (Traefik, `https://lespass.tibillet.localhost/`).
   Diagnostic en 5 secondes s'il y a un doute — un `502` veut dire qu'il est mort
   et que les échecs ne viennent pas de vous (cf. `PIEGES.md` 9.111) :
   ```bash
   curl -sk -o /dev/null -w "%{http_code}\n" https://lespass.tibillet.localhost/
   ```
2. `.env` contient `ADMIN_EMAIL` et `E2E_TEST_TOKEN` (déjà le cas en dev).
3. Chromium Playwright installé dans le container. `install-deps` exige **root**
   (cf. `PIEGES.md` 9.40) :
   ```bash
   docker exec -u root lespass_django /DjangoFiles/.venv/bin/playwright install-deps chromium
   docker exec lespass_django poetry run playwright install chromium
   ```
4. Celery tourne (`lespass_celery`) : les récompenses en monnaie partent par
   `.delay()`. Sans worker, elles ne sont **jamais** versées — et rien ne le dit.

### Le mode 3 en détail : `stripe listen`

Le marqueur `stripe_listen` (déclaré dans `pytest.ini`, **pas** dans
`pyproject.toml` — un marqueur déclaré là y est inerte) porte les parcours qui
ne s'achèvent que sur un webhook Stripe : recharge en monnaie fédérée, validation
manuelle d'adhésion, renouvellement d'abonnement.

```bash
# 1. sur l'hôte, dans un terminal qu'on laisse ouvert :
stripe listen

# 2. dans un autre :
docker exec -e E2E_STRIPE_LISTEN=1 lespass_django poetry run pytest tests/e2e/ -q
```

Deux choses à savoir :

- **`E2E_STRIPE_LISTEN=1` est déclaratif.** Il affirme que le CLI tourne, il ne
  le vérifie pas : le conteneur ne voit pas les processus de l'hôte. Si le CLI
  meurt en cours de session, les tests s'exécutent quand même et échouent pour
  une raison sans rapport avec le code. Vérification :
  ```bash
  tmux list-panes -a -F "#{pane_current_command}" | grep stripe   # rien = CLI mort
  ```
- **Sans la variable, le skip est bruyant.** Un encadré rouge en fin de run nomme
  chaque test non joué (hook `pytest_terminal_summary`, `tests/e2e/conftest.py`).
  C'est délibéré : un run vert qui cache des parcours de paiement non vérifiés
  donne une confiance qu'on n'a pas.

### Faire passer un mois : les horloges de test Stripe

`test_renouvellement_adhesion_recurrente.py` vérifie qu'une adhésion mensuelle
reverse bien sa récompense **à chaque échéance**. Pour ne pas attendre un mois,
le client Stripe est rattaché à une `TestClock` que le test avance de 32 jours :

```python
horloge = stripe.test_helpers.TestClock.create(frozen_time=int(time.time()), ...)
client  = stripe.Customer.create(email=..., test_clock=horloge.id, ...)
# ... puis, plus tard :
stripe.test_helpers.TestClock.advance(horloge.id,
                                      frozen_time=h.frozen_time + 32 * 24 * 3600, ...)
```

Stripe émet alors une **vraie** facture, prélève **vraiment** la carte de test et
envoie un **vrai** `invoice.paid` — rien n'est simulé côté Lespass.

Trois pièges, tous payés :

1. **Un client sans moyen de paiement par défaut** fait échouer chaque échéance
   (`invoice.payment_failed` en boucle, puis suppression de l'abonnement).
   Attacher `pm_card_visa` **et** le désigner dans `invoice_settings`.
2. **La première facture ne déclenche rien** : elle porte
   `billing_reason='subscription_create'`, que le webhook ignore volontairement.
   Seul le deuxième cycle est un renouvellement.
3. **`advance` est asynchrone.** Attendre que l'horloge repasse `ready` avant de
   conclure, sinon on conclut sur un cycle qui n'a pas encore eu lieu.

Le teardown supprime l'horloge, ce qui emporte le client et l'abonnement.

### Carte Stripe de test / Stripe test card

`4242 4242 4242 4242`, nom `Douglas Adams`, date `12/42`, code `424`.

---

## 🔑 Le login instantané E2E / Instant E2E login

Les tests E2E Python ne passent **pas** par le formulaire de connexion.
La fixture `login_as(page, email)` appelle l'endpoint de test
`POST /api/user/__test_only__/force_login/` qui pose un cookie de session
en ~100 ms (au lieu de ~5 s par le flow UI).

Sécurité — triple garde-fou (voir `AuthBillet/views_test_only.py`) :

1. `settings.DEBUG` doit valoir `True` ;
2. la variable d'env `E2E_TEST_TOKEN` doit être définie côté serveur ;
3. le header `X-Test-Token` doit correspondre (comparaison constant-time).

Sinon : réponse 404 silencieuse. L'endpoint n'est **jamais** monté en production.

---

## 🎭 Politique Stripe / Stripe policy

Même politique que la V2 (`lespass-main`) :

- **La logique de paiement se teste en pytest avec `mock_stripe`**
  (fixture du `tests/pytest/conftest.py`) : adhésions, réservations, crowds,
  prix libre, validation manuelle, tokens SSA — zéro réseau.
- **Quelques parcours E2E réels** vérifient qu'un vrai `checkout.stripe.com`
  aboutit : les smoke (`test_stripe_smoke.py`), et les parcours marqués
  `stripe_listen` qui vont jusqu'au webhook de confirmation.
- On n'ajoute **pas** de nouveau parcours Stripe réel sans bonne raison :
  chaque checkout réel coûte ~30 s à chaque run.

**Ce qu'un mock ne peut pas prouver.** Un service simulé accepte ce qu'on lui
envoie ; il ne dit rien du contrat réel. C'est le Fedow **réel** qui a révélé
qu'une recharge exige `ligne_article_uuid` dans ses métadonnées — un contrat que
personne n'avait écrit ailleurs que dans le code d'un appelant. Même logique côté
Stripe : les mocks couvrent la logique métier, les parcours réels couvrent le
contrat.

Flow mock en 3 étapes (voir PIEGES.md 9.19) :
POST formulaire → vérifier `mock_stripe.mock_create.called` → simuler le
retour avec `paiement.update_checkout_status()`.

### Ce qui parle aux services RÉELS

| Fichier | Service réel | Marqueur |
|---|---|---|
| `test_parcours_fedow_reel.py` | Fedow (+ Stripe pour la recharge fédérée) | partiel |
| `test_recharge_pos_puis_qrcode.py` | Fedow | — |
| `test_recompense_au_scan_puis_qrcode.py` | Fedow | — |
| `test_adhesion_recompense_puis_qrcode.py` | Fedow | — |
| `test_renouvellement_adhesion_recurrente.py` | Fedow + Stripe (horloge de test) | `stripe_listen` |
| `test_stripe_smoke.py` | Stripe | — |
| `test_membership_manual_validation_stripe.py` | Stripe (webhook) | `stripe_listen` |

**Ces tests ne s'annulent pas.** Une vente débite un vrai portefeuille, une remise
en banque vide celui du lieu, une récompense émet de la monnaie. Le Fedow n'a pas
de marche arrière : à lancer sur un environnement de développement dont on accepte
qu'il soit remué.

---

## ✍️ Écrire un nouveau test / Writing a new test

Règles d'or / Golden rules:

1. **Atomique** — un test vérifie une seule chose.
2. **Noms verbeux** — pas d'abréviations.
3. **Commentaires bilingues FR/EN** (FALC).
4. **DB dev partagée, pas de rollback** : noms suffixés (`uuid4().hex[:8]`),
   assertions en **delta** (jamais de total absolu — piège 9.60),
   nettoyage en fin de test quand c'est possible.
5. **`data-testid`** sur tout élément ciblé par un test E2E.
6. Deux `conftest.py` séparés (`tests/pytest/` et `tests/e2e/`) —
   ne pas créer de conftest racine.

Fixtures déjà disponibles / Available fixtures:

- `tests/pytest/conftest.py` : `api_client`, `auth_headers`, `admin_user`,
  `admin_client`, `tenant`, `mock_stripe`.
- `tests/e2e/conftest.py` : `page`, `login_as`, `login_as_admin`,
  `login_as_admin_on_subdomain`, `create_event`, `create_product`,
  `django_shell`, `setup_test_data`, `fill_stripe_card`.

---

## 🔄 Migration TypeScript → Python (TERMINÉE le 2026-06-11)

L'ancienne suite `tests/playwright/` (TypeScript, 42 specs) a été entièrement
remplacée par `tests/e2e/` (Python), sur le modèle de la V2, puis supprimée.
Table de correspondance (pour retrouver un ancien spec dans l'historique git) :

| Ancien spec TS | Remplacé par |
|---|---|
| 18-reservation-validations | `tests/e2e/test_reservation_validations.py` |
| 20-membership-validations | `tests/e2e/test_membership_validations.py` |
| 28-numeric-overflow-validation | `tests/e2e/test_numeric_overflow_validation.py` |
| 08, 12 (adhésion + form dynamique) | fusionnés dans le spec TS 27 + pytest mock |
| 09, 10 (réservations Stripe) | `test_stripe_reservation.py` (mock) + smoke E2E |
| 11, 13, 15, 42 (adhésions Stripe) | `test_stripe_membership_*.py` (mock) + smoke E2E |
| 44 (crowds Stripe) | `test_stripe_crowds.py` (mock) |
| 01-login | `tests/e2e/test_login.py` |
| 02-admin-configuration | `tests/e2e/test_admin_configuration.py` |
| 16-user-account-summary | `tests/e2e/test_user_account_summary.py` |
| 19-reservation-limits | `tests/e2e/test_reservation_limits.py` |
| 21-membership-account-states | `tests/e2e/test_membership_account_states.py` |
| 23-crowds-participation | `tests/e2e/test_crowds_participation.py` |
| 24-crowds-summary | `tests/e2e/test_crowds_summary.py` |
| 99-theme_language | `tests/e2e/test_theme_language.py` |
| 26, 32, 33, 34, 35 (admin adhésions) | `test_admin_membership_custom_form_edit.py`, `test_admin_credit_note.py`, `test_admin_ajouter_paiement.py`, `test_admin_cancel_membership.py`, `test_admin_membership_list_status.py` |
| 37, 38 (adhésions obligatoires) | `test_admin_adhesions_obligatoires_m2m.py`, `test_event_adhesion_obligatoire_check.py` |
| 39-admin-reservation-cancel | `test_admin_reservation_cancel.py` |
| 03-07, 14 (produits adhésion admin) | `test_memberships_admin_create.py`, `test_membership_recurring_create.py`, `test_membership_validation_product.py`, `test_membership_amap.py`, `test_membership_fix_solidaire.py`, `test_membership_manual_validation.py` |
| 17, 22, 27, 36, 43 (parcours adhésion) | `test_membership_free_price_multi.py`, `test_membership_recurring_cancel.py`, `test_membership_dynamic_form_full_cycle.py`, `test_sepa_duplicate_protection.py`, `test_membership_manual_validation_stripe.py` |

| 25-product-duplication-complex | `test_product_duplication_complex.py` |
| 29-event-quick-create-duplicate | `test_event_quick_create_duplicate.py` |
| 40-explorer-markers-per-pa | `test_explorer_markers_per_pa.py` |

Historique complet de la migration : `TECH_DOC/SESSIONS/TESTS/` (CHANTIER-01 à 05).

---

## 📁 Dossiers annexes / Other folders

| Dossier | Contenu |
|---|---|
| `tests/scripts/` | `setup_test_data.py` — utilisé par la fixture `setup_test_data` du conftest e2e |
| `tests/stress/` | Tests de charge ponctuels, hors suite |
| `tests/django_test/` | ⚠️ Legacy, partiellement rouge, à vider (voir PLAN_SIMPLIFICATION.md) |
| `tests/PIEGES.md` | ~80 pièges documentés — **à lire avant d'écrire un test** |
