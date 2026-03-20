---
apply: always
---

# Plan de tests — Lespass (TiBillet)

Document de reference unique pour la strategie de tests du projet Lespass.

---

## 1. Philosophie des tests

### Principes FALC (Facile A Lire et Comprendre)

| Regle | Application Lespass |
|-------|-------------------|
| **TestCase avec ROLLBACK** | `FastTenantTestCase` de django-tenants (schema_context automatique, rollback en fin de test) |
| **self.client in-process** | `self.client` Django (pas de `requests` HTTP, pas de `docker exec`) |
| **Pas d'I/O externe** | Mocker Stripe (`unittest.mock`), pas d'appels reseau |
| **setUp minimal** | Creer 2-3 objets max par test, pas de `loaddata` |
| **1 browser par classe** | `setUpClass` lance Chromium, `setUp` ouvre un onglet |
| **pytest + pytest-django** | Runner unique. `FastTenantTestCase` comme base class, compatible pytest. |
| **Tests atomiques** | 1 test = 1 comportement precis |
| **Noms verbeux** | `test_paiement_especes_cree_ligne_article_avec_status_V` |
| **Bilingue** | Commentaires FR + EN |

### Pourquoi pytest + pytest-django ?

C'est le standard de facto des gros projets Django (Sentry, Zulip, Wagtail). On a deja 28 fichiers pytest — pas de raison de jeter cet existant.

| Feature pytest | Equivalent Django natif |
|----------------|----------------------|
| `@pytest.fixture(scope="session")` | `setUp` / `setUpClass` seulement |
| `pytest-xdist` (parallelisme intelligent) | `--parallel` (basique) |
| `--reuse-db` (pytest-django) | `--keepdb` |
| `--last-failed` (relance que les echecs) | N'existe pas |
| `--stepwise` (s'arrete au 1er echec) | `--failfast` (similaire) |
| Fixtures composables et cachables | Pas d'equivalent |

Le gain de `--last-failed` seul justifie pytest : en cycle edit-test-edit, relancer uniquement les tests casses est un multiplicateur de productivite.

### Pourquoi migrer le reste ?

- **requests HTTP** : chaque test API fait un appel reseau complet (TCP, TLS, serveur). Lent. → Remplacer par `self.client` Django (in-process).
- **Playwright TS x 3 navigateurs** : 119 tests x 3 = 357 executions. ~54 minutes. → 1 navigateur, Playwright Python.
- **Django TestCase** : transaction ROLLBACK, client in-process, pas de reseau. ~100x plus rapide.
- **Playwright Python** : 1 navigateur, acces ORM direct dans les assertions.

---

## 2. Infrastructure

### 2.1 Framework et commandes

**pytest est le runner unique.** Tous les tests (unitaires, integration, E2E Python) passent par pytest + pytest-django.

```bash
# Tous les tests (--reuse-db = reutilise la base de test, ~12s gagnes par run)
docker exec lespass_django poetry run pytest tests/ --reuse-db -v

# Tests laboutik uniquement
docker exec lespass_django poetry run pytest tests/pytest/test_paiement_especes_cb.py --reuse-db -v

# Relancer uniquement les tests qui ont echoue au run precedent
docker exec lespass_django poetry run pytest tests/ --reuse-db --last-failed

# S'arreter au premier echec (utile en dev)
docker exec lespass_django poetry run pytest tests/ --reuse-db --stepwise

# Avec cle API injectee (tests API v2 existants)
poetry run pytest -qs tests/pytest --api-key <KEY>
```

### 2.1.1 --reuse-db (le quick win)

`--reuse-db` (pytest-django) reutilise la base de test entre les runs. Economise ~12s de `CREATE DATABASE` + migrations a chaque lancement. Zero risque, zero changement de code. **A utiliser systematiquement.**

Equivalent Django natif : `--keepdb`.

### 2.1.2 --parallel / pytest-xdist (a tester)

`pytest-xdist` repartit les tests sur N workers (1 par CPU).

**Attention avec django-tenants** : chaque worker doit creer ses propres schemas tenant. Le cout d'init est multiplie par N. `FastTenantTestCase` cree un schema temporaire par classe de test — risque de collision si deux workers creent le meme nom de schema.

**Verdict** : a tester en Phase B, pas garanti out-of-the-box avec django-tenants. Pour l'instant les tests unitaires (~3 min) ne sont pas CPU-bound.

**Tests Playwright TS (existants, en migration) :**
```bash
cd tests/playwright

# 1 seul navigateur (chromium — defaut apres Phase A)
yarn test:chromium:console --workers=1

# Avec logs detailles
DEBUG=pw:api yarn playwright test --project=chromium --workers=1 tests/adhesions/11-anonymous-membership.spec.ts

# Tests laboutik uniquement
yarn test:laboutik
```

### 2.2 Multi-tenant (django-tenants)

Lespass utilise `django-tenants` : 1 schema PostgreSQL par tenant.

Les tests Django doivent utiliser :
- `FastTenantTestCase` (unitaires/integration) : cree un tenant temporaire, rollback automatique
- `TenantClient` : client HTTP qui injecte le bon tenant dans la requete

```python
from django_tenants.test.cases import FastTenantTestCase
from django_tenants.test.client import TenantClient

class MonTest(FastTenantTestCase):
    @classmethod
    def get_test_tenant_domain(cls):
        return 'lespass.test.localhost'

    @classmethod
    def get_test_schema_name(cls):
        return 'test_lespass'

    def setUp(self):
        self.client = TenantClient(self.tenant)
```

### 2.3 Auth dans les tests

**Playwright TS (actuel)** : `loginAs(page, email)` navigue vers `/`, ouvre le panneau login, remplit l'email, clique "TEST MODE". Repete a chaque test.

**Playwright TS (optimise — Phase A)** : `storageState` sauvegarde les cookies apres 1 login. Les tests suivants chargent le state sans re-login.

**Django TestCase (cible)** : `self.client.force_login(user)` — instantane, pas de navigation.

---

## 3. Inventaire — Tests pytest existants (28 fichiers)

### 3.1 Tests API v2 (15 fichiers, ~15 tests)

Ces tests utilisent `requests` HTTP vers l'API v2 (schema.org/JSON-LD).
Migration : remplacer `requests.get/post` par `self.client.get/post` (in-process, pas de reseau).

| Fichier | Tests | Sujet | Migration |
|---------|-------|-------|-----------|
| `test_event_create.py` | 1 | Creation event | `requests` → `self.client` |
| `test_events_list.py` | 1 | Liste events | `requests` → `self.client` |
| `test_event_retrieve.py` | 1 | Retrieve event | `requests` → `self.client` |
| `test_event_delete.py` | 1 | Delete event | `requests` → `self.client` |
| `test_event_create_extended.py` | 1 | Event etendu | `requests` → `self.client` |
| `test_event_images.py` | 1 | Images event | `requests` → `self.client` |
| `test_event_link_address.py` | 1 | Lier adresse | `requests` → `self.client` |
| `test_postal_address_crud.py` | 1 | CRUD adresse | `requests` → `self.client` |
| `test_postal_address_images.py` | 1 | Images adresse | `requests` → `self.client` |
| `test_reservation_create.py` | 1 | Reservation | `requests` → `self.client` |
| `test_membership_create.py` | 1 | Adhesion | `requests` → `self.client` |
| `test_crowd_initiative_create.py` | 1 | Crowds create | `requests` → `self.client` |
| `test_crowd_initiative_list.py` | 1 | Crowds list | `requests` → `self.client` |
| `test_crowd_budget_item_flow.py` | 1 | Budget item | `requests` → `self.client` |
| `test_crowd_votes_participations.py` | 1 | Votes | `requests` → `self.client` |

> Ces fichiers restent en pytest. Seul le transport change (`requests` HTTP → `self.client` in-process).

### 3.2 Tests metier (13 fichiers, ~115 tests)

Ces tests verifient la logique metier (modeles, vues, services).

| Fichier | Tests | Sujet | Convertir vers |
|---------|-------|-------|---------------|
| `test_fedow_core.py` | 8 | Assets, Tokens, Transactions | FastTenantTestCase |
| `test_pos_models.py` | 9 | Modeles POS | FastTenantTestCase |
| `test_pos_views_data.py` | 12 | Construction donnees vues | FastTenantTestCase |
| `test_caisse_navigation.py` | 12 | Navigation, serializers | FastTenantTestCase |
| `test_paiement_especes_cb.py` | 8 | Paiement especes/CB | FastTenantTestCase |
| `test_paiement_cashless.py` | 8 | Paiement NFC cashless | FastTenantTestCase |
| `test_retour_carte_recharges.py` | 15 | Retour carte, recharges | FastTenantTestCase |
| `test_commandes_tables.py` | 10 | Commandes restaurant | FastTenantTestCase |
| `test_cloture_caisse.py` | 8 | Cloture caisse | FastTenantTestCase |
| `test_cloture_export.py` | 9 | Export PDF/CSV | FastTenantTestCase |
| `test_validation_prix_libre.py` | 12 | Validation prix libre | FastTenantTestCase |
| `test_verify_transactions.py` | 4 | Integrite transactions | FastTenantTestCase |
| `test_charge_festival.py` | — | 1000 tx concurrentes | Stress test (a creer) |

> Note : `test_charge_festival.py` n'existe pas encore. Prevu comme stress test.
> Tous ces fichiers restent en pytest. Les tests metier migrent vers `FastTenantTestCase` comme base class (compatible pytest).

---

## 4. Inventaire — Tests Playwright TypeScript existants (51 fichiers, ~165 tests)

### 4.1 Adhesions (24 fichiers)

| Fichier | Tests | Stripe | Login | Convertir vers |
|---------|-------|--------|-------|---------------|
| `03-memberships.spec.ts` | 1 | non | admin | FastTenantTestCase |
| `04-membership-recurring.spec.ts` | 1 | non | admin | FastTenantTestCase |
| `05-membership-validation.spec.ts` | 1 | non | admin | FastTenantTestCase |
| `06-membership-amap.spec.ts` | 1 | non | admin | FastTenantTestCase |
| `07-fix-solidaire.spec.ts` | 1 | non | admin | FastTenantTestCase |
| `08-membership-ssa-with-forms.spec.ts` | 1 | non | admin | FastTenantTestCase |
| `11-anonymous-membership.spec.ts` | 1 | oui | non | **PlaywrightLive** (flow Stripe) |
| `12-anonymous-membership-dynamic-form.spec.ts` | 1 | oui | non | **PlaywrightLive** (formulaire dynamique) |
| `13-ssa-membership-tokens.spec.ts` | 1 | oui | user | **PlaywrightLive** (tirelire multi-page) |
| `14-membership-manual-validation.spec.ts` | 1 | oui | admin+user | **PlaywrightLive** (cross-roles) |
| `15-membership-free-price.spec.ts` | 1 | oui | non | **PlaywrightLive** (prix libre Stripe) |
| `17-membership-free-price-multi.spec.ts` | 4 | oui | non | **PlaywrightLive** (multi-prix) |
| `20-membership-validations.spec.ts` | 1 | non | non | **PlaywrightLive** (validation JS client) |
| `21-membership-account-states.spec.ts` | 1 | non | user | FastTenantTestCase |
| `22-membership-recurring-cancel.spec.ts` | 1 | non | user | FastTenantTestCase |
| `26-admin-membership-custom-form-edit.spec.ts` | 1 | non | admin | FastTenantTestCase |
| `27-membership-dynamic-form-full-cycle.spec.ts` | 7 | oui | non | **PlaywrightLive** (cycle complet) |
| `33-admin-ajouter-paiement.spec.ts` | 2 | non | admin | FastTenantTestCase |
| `34-admin-cancel-membership.spec.ts` | 2 | non | admin | FastTenantTestCase |
| `35-admin-membership-list-status.spec.ts` | 3 | non | admin | FastTenantTestCase |
| `36-sepa-duplicate-protection.spec.ts` | 3 | non | admin | FastTenantTestCase |
| `37-admin-adhesions-obligatoires-m2m.spec.ts` | 1 | non | non | FastTenantTestCase |
| `42-membership-zero-price.spec.ts` | 2 | oui | non | FastTenantTestCase (mock Stripe) |
| `43-membership-manual-validation-stripe.spec.ts` | 1 | oui | admin | **PlaywrightLive** |

### 4.2 Admin (10 fichiers)

| Fichier | Tests | Stripe | Login | Convertir vers |
|---------|-------|--------|-------|---------------|
| `01-login.spec.ts` | 2 | non | non | **PlaywrightLive** (flow login) |
| `02-admin-configuration.spec.ts` | 1 | non | admin | FastTenantTestCase |
| `16-user-account-summary.spec.ts` | 1 | non | user | FastTenantTestCase |
| `28-numeric-overflow-validation.spec.ts` | 2 | non | non | FastTenantTestCase |
| `29-admin-proxy-products.spec.ts` | 6 | non | admin | FastTenantTestCase |
| `31-admin-asset-federation.spec.ts` | 1 | non | admin x2 | **PlaywrightLive** (cross-tenant) |
| `32-admin-credit-note.spec.ts` | 1 | non | admin | FastTenantTestCase |
| `33-admin-audit-fixes.spec.ts` | 8 | non | non | FastTenantTestCase |
| `99-theme_language.spec.ts` | 3 | non | admin | FastTenantTestCase |

### 4.3 Crowds (3 fichiers)

| Fichier | Tests | Stripe | Login | Convertir vers |
|---------|-------|--------|-------|---------------|
| `23-crowds-participation.spec.ts` | 1 | non | admin | **PlaywrightLive** (popup UI) |
| `24-crowds-summary.spec.ts` | 1 | non | non | FastTenantTestCase |
| `44-crowds-contribution-stripe.spec.ts` | 2 | oui | non | **PlaywrightLive** (Stripe) |

### 4.4 Evenements (8 fichiers)

| Fichier | Tests | Stripe | Login | Convertir vers |
|---------|-------|--------|-------|---------------|
| `09-anonymous-events.spec.ts` | 3 | oui | non | **PlaywrightLive** (flow booking) |
| `10-anonymous-event-dynamic-form.spec.ts` | 1 | oui | non | **PlaywrightLive** (formulaire) |
| `18-reservation-validations.spec.ts` | 1 | non | non | **PlaywrightLive** (validation JS) |
| `19-reservation-limits.spec.ts` | 1 | non | user | FastTenantTestCase |
| `21-event-quick-create-duplicate.spec.ts` | 1 | non | admin | FastTenantTestCase |
| `25-product-duplication-complex.spec.ts` | 1 | non | admin | FastTenantTestCase |
| `35-admin-reservation-cancel.spec.ts` | 2 | non | admin | FastTenantTestCase |
| `38-event-adhesion-obligatoire-check.spec.ts` | 1 | non | user | FastTenantTestCase |

### 4.5 LaBoutik (7 fichiers)

| Fichier | Tests | Stripe | Login | Convertir vers |
|---------|-------|--------|-------|---------------|
| `30-discovery-pin-pairing.spec.ts` | 1 | non | admin | FastTenantTestCase |
| `39-laboutik-pos-paiement.spec.ts` | 8 | non | admin | **PlaywrightLive** (HTMX) |
| `40-laboutik-commandes-tables.spec.ts` | 7 | non | admin | **SKIP** (feature incomplete) |
| `41-laboutik-cloture-caisse.spec.ts` | 3 | non | admin | FastTenantTestCase (deja couvert pytest) |
| `44-laboutik-adhesion-identification.spec.ts` | 8 | non | admin | **PlaywrightLive** (NFC + HTMX) |
| `45-laboutik-pos-tiles-visual.spec.ts` | 9 | non | admin | **PlaywrightLive** (rendu CSS) |
| `46-laboutik-securite-a11y.spec.ts` | 3 | non | admin | FastTenantTestCase (attributs HTML) |

### 4.6 Recap conversion

| Cible | Fichiers | Critere |
|-------|----------|---------|
| **PlaywrightLive (Python)** | ~20 | Flows visuels, Stripe, HTMX, cross-tenant |
| **FastTenantTestCase** | ~30 | Admin CRUD, validation, logique metier |
| **Skip** | 1 | Feature incomplete (commandes tables) |

---

## 5. Architecture cible

### 5.1 Tests unitaires : pytest + FastTenantTestCase

`FastTenantTestCase` est la base class (ROLLBACK + tenant). pytest est le runner.
On utilise `self.assert*` (style unittest) car `FastTenantTestCase` herite de `TestCase`.

```python
import pytest
from django_tenants.test.cases import FastTenantTestCase
from django_tenants.test.client import TenantClient
from BaseBillet.models import Product, LigneArticle
from laboutik.models import PointDeVente


class PaiementEspecesTest(FastTenantTestCase):
    """Tests paiement especes dans le contexte du tenant lespass.
    / Tests for cash payment in the lespass tenant context."""

    @classmethod
    def get_test_tenant_domain(cls):
        return 'lespass.test.localhost'

    @classmethod
    def get_test_schema_name(cls):
        return 'test_lespass'

    def setUp(self):
        self.client = TenantClient(self.tenant)
        # Creer les donnees minimales pour le test
        # / Create minimal test data
        self.pv = PointDeVente.objects.create(name="Bar Test")
        self.product = Product.objects.create(name="Biere Test")

    def test_paiement_especes_cree_ligne_article_avec_status_V(self):
        """Un paiement especes doit creer une LigneArticle avec status V.
        / A cash payment must create a LigneArticle with status V."""
        response = self.client.post('/laboutik/paiement/payer/', {
            'moyen_paiement': 'CA',
            'articles': [{'product': str(self.product.pk), 'qty': 1}],
        }, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        ligne = LigneArticle.objects.last()
        self.assertEqual(ligne.moyen_paiement, 'CA')
```

> Note : on peut aussi ecrire des tests en style fonctions pytest (`def test_xxx()`) avec des fixtures.
> Les deux styles coexistent. `FastTenantTestCase` impose le style classe car il herite de `TestCase`.

### 5.2 Tests E2E : PlaywrightTenantLiveTestCase (Python)

```python
from django_tenants.test.cases import TenantTestCase
from django.test import LiveServerTestCase
from playwright.sync_api import sync_playwright

class PlaywrightTenantLiveTestCase(TenantTestCase, LiveServerTestCase):
    """Base pour tests E2E Playwright dans un contexte multi-tenant.
    / Base class for Playwright E2E tests in a multi-tenant context."""

    browser = None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        self.page = self.browser.new_page()
        self.page.set_default_timeout(10000)

    def tearDown(self):
        self.page.close()
        super().tearDown()

    def naviguer_vers(self, chemin):
        """Naviguer vers un chemin relatif au serveur de test.
        / Navigate to a path relative to the test server."""
        self.page.goto(f"{self.live_server_url}{chemin}")
        self.page.wait_for_load_state("networkidle")
```

### 5.3 Matrice de conversion (Playwright TS → cible)

**Convertir en FastTenantTestCase si :**
- Le test fait du CRUD admin (create/edit/delete via formulaire)
- Le test verifie une logique metier (statut, calcul, validation serveur)
- Le test ne touche pas a Stripe (ou peut mocker Stripe)
- Le test ne verifie pas de rendu visuel (CSS, layout, HTMX)

**Convertir en PlaywrightLive si :**
- Le test fait un paiement Stripe (iframe, redirection)
- Le test verifie un rendu HTMX (swap, animation, overlay)
- Le test verifie un flow multi-pages avec navigation reelle
- Le test verifie de la validation cote client (JavaScript)
- Le test implique du cross-tenant (2 sous-domaines)

---

## 6. Gains immediats (Phase A — sans refonte)

### 6.1 — 1 navigateur par defaut

Modification de `playwright.config.ts` : seul chromium est actif par defaut.
Firefox et webkit sont commentes (reactiver si besoin avec `--project=firefox`).

**Gain estime : ~36 minutes** (119 tests x 2 navigateurs evites).

### 6.2 — storageState pour auth

Fichier `global-auth.setup.ts` : login admin une seule fois, sauvegarde les cookies dans `.auth/admin.json`. Les tests admin chargent le state sans re-login.

**Gain estime : ~8 minutes** (evite ~40 re-logins admin a ~12s chacun).

### 6.3 — Scripts yarn cibles

```json
{
  "test:laboutik": "playwright test --project=chromium tests/laboutik/",
  "test:adhesions": "playwright test --project=chromium tests/adhesions/",
  "test:admin": "playwright test --project=chromium tests/admin/"
}
```

**Gain : feedback rapide en dev** (~3 min pour laboutik au lieu de 54 min total).

---

## 7. Phases de migration

### Phase A : PLAN_TEST.md + gains immediats ← CETTE SESSION

- [x] Ecrire `tests/PLAN_TEST.md`
- [x] Modifier `playwright.config.ts` (1 navigateur)
- [x] Creer `global-auth.setup.ts` (storageState)
- [x] Ajouter scripts yarn cibles
- [x] Mettre a jour `tests/README.md` (redirect)

### Phase B : Prototype FastTenantTestCase (pytest)

- Convertir `test_paiement_especes_cb.py` : remplacer `requests` HTTP par `FastTenantTestCase` + `self.client`
- Valider que ROLLBACK fonctionne avec django-tenants sous pytest
- Ajouter `pytest-django` + `--reuse-db` dans la config si pas deja fait
- Tester `pytest-xdist` avec django-tenants (collision de schemas ?)
- Mesurer le gain de temps

### Phase C : Prototype PlaywrightTenantLiveTestCase (pytest)

- Creer `tests/e2e/base.py` avec PlaywrightTenantLiveTestCase
- Convertir `01-login.spec.ts` de TypeScript → Python (pytest + classe)
- Valider que Playwright Sync fonctionne (pas de bug asyncio car WSGI)
- Tester l'acces ORM direct dans les assertions E2E

### Phase D : Migration progressive

- Migrer les 15 tests API v2 : `requests` HTTP → `self.client` (garder pytest, changer le transport)
- Convertir les ~30 fichiers PW TS → FastTenantTestCase (pytest)
- Convertir les ~20 fichiers PW TS → PlaywrightLive (pytest)
- Supprimer les fichiers TypeScript au fur et a mesure

### Phase E : Nettoyage

- Supprimer `tests/playwright/` quand tous les E2E sont en Python
- Consolider `conftest.py` (fixtures partagees : tenant, admin user, etc.)
- Mettre a jour ce fichier avec les metriques finales

---

## 8. Metriques de reference

| Metrique | Avant | Apres Phase A | Apres Phase E |
|----------|-------|---------------|---------------|
| Tests Playwright TS | 119 x 3 nav | 119 x 1 nav | 0 |
| Tests Playwright Python (pytest) | 0 | 0 | ~20 |
| Tests FastTenantTestCase (pytest) | ~130 | ~130 | ~250 |
| Runner | pytest + yarn PW | pytest + yarn PW | **pytest seul** |
| Temps E2E | ~54 min | ~14 min | ~5 min |
| Temps unitaire | ~3 min | ~3 min | ~30s |
| **Total** | **~57 min** | **~17 min** | **~5.5 min** |

Options supplementaires apres Phase E :
- `--reuse-db` : -12s par run (systematique)
- `--last-failed` : relance uniquement les echecs (cycle dev)
- `pytest-xdist` : parallelisme si valide avec django-tenants

---

*Ce document est un commun numerique. Prenez-en soin !*
*This document is a digital common. Take care of it!*
