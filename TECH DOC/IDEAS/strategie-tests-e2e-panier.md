# Stratégie de tests E2E Playwright — Lespass

Réflexion issue de la session panier (avril 2026) sur la philosophie des tests
E2E, leurs limites, et un plan concret de stabilisation pour `tests/e2e/`.

---

## TL;DR

- **Les E2E sont chers et fragiles.** 70-80% de fiabilité en moyenne vs 95-99%
  pour les tests pytest DB-only. Chaque dépendance ajoute du bruit (timing,
  réseau, DOM, i18n, login, session).
- **Mon approche : "E2E as smoke test, pas as coverage".** Max 1 E2E par flow
  métier critique. La couverture exhaustive se fait en pytest DB-only.
- **Problèmes actuels des E2E Lespass** : login via flow UI (TEST MODE) fragile,
  fixtures qui créent des données DB sans `@pytest.mark.django_db`, pas de
  CI qui les exécute, pas de rollback entre tests.
- **Plan en 4 étapes** : (1) réécrire `login_as_admin` en `force_login`,
  (2) supprimer fixtures de création DB, (3) réécrire les 2 tests cassés,
  (4) ajouter ~2 E2E pour couvrir les flows critiques de la session panier.

---

## 1. Philosophie — les 3 couches de tests

| Couche | Cible | Rapidité | Fiabilité | Ce qui casse |
|--------|-------|----------|-----------|--------------|
| **Unit** (`test_*.py` direct) | Une fonction pure | ms | 99% | Jamais (isolé) |
| **Integration (pytest DB)** | Models + views + signals | ~200ms | 95% | Fixtures, migration, cache state |
| **E2E (Playwright)** | Browser + Django + Traefik + DOM + JS + CSS + session | 2-10s | 70-80% | Timing, réseau, DOM dynamique, sélecteurs, login, locale, env CI |

**L'E2E multiplie les points de rupture.** Sur 50 E2E qui testent chacun 10
éléments (login + navigation + form + HTMX swap + assertion), la probabilité
qu'au moins un tombe à cause d'un truc non lié au code métier est élevée.

**Conséquence** : les E2E sont utiles pour valider **l'intégration globale**
(ça marche en prod), pas pour couvrir **la logique métier** (ça se teste en
pytest, plus rapide et plus fiable).

---

## 2. Ce qui casse nos E2E Lespass — pièges réels

PIEGES.md en documente 50+. Les plus douloureux :

### 2.1 Login via flow TEST MODE (conftest `login_as_admin`)

Le flow actuel de `tests/e2e/conftest.py:104-142` :

1. `page.goto('/')`
2. Click sur le bouton "Log in" de la navbar
3. Fill email dans `#loginEmail`
4. Submit le form `#loginForm`
5. Attendre l'apparition du lien "TEST MODE" (injection HTMX)
6. Click dessus
7. Assert `/my_account/` accessible

**6 étapes UI qui peuvent chacune flaker.** Si le design navbar change, si
HTMX met 100ms de plus, si la trad "Log in" change en "Connexion", le test
fail — sans rapport avec le code métier testé.

**Alternative** : `force_login` côté Django → injection cookie directement →
skip toutes les étapes UI. ~10x plus rapide, beaucoup plus stable.

### 2.2 Sélecteurs HTML fragiles

- **`.first` sur un radio** sans savoir quel prix arrive en premier → si
  l'adhésion a un "Prix libre" en premier dans le rendu, `.first` va le
  sélectionner et le test échoue car `custom_amount` est requis (validation
  HTML5 bloque).
- **PIEGES 9.47** : IDs avec `__` invalides en CSS `#` → obligé d'utiliser
  `[id="..."]`.
- **PIEGES 9.39** : duplicate ID dans le DOM → Playwright strict mode refuse
  → scoper avec un ancêtre (ex: `.navbar #panier-badge-nav`).
- **PIEGES 9.34** : `{% translate %}` change le texte selon la langue active
  → assertions avec `assert 'Adhesion' in text or 'Membership' in text`.

### 2.3 Timing HTMX + Stripe

- **PIEGES 9.28** : `networkidle` ne résout jamais sur les pages Stripe
  (analytics + SSE permanents) → utiliser `domcontentloaded`.
- **Attendre le swap HTMX avant d'asserter** : `wait_for_selector(...)` plutôt
  que `time.sleep()` arbitraire.
- **Toasts SweetAlert** : timer `3500ms` → l'assertion peut arriver après le
  dismiss → soit `wait_for` tôt, soit tester le side-effect (badge navbar).

### 2.4 Fixtures DB

- **`@pytest.mark.django_db` obligatoire** pour tout test qui appelle
  `*.objects.create()`. **Oublié** dans `event_gratuit_publie` → les 2 tests
  panier pré-existants crashent avec `RuntimeError: Database access not allowed`.
- **Pas de rollback DB entre E2E** : contrairement aux tests pytest avec
  `LiveServer`, les E2E Playwright s'appuient sur le vrai serveur Django qui
  utilise la DB tenant. Pas de rollback auto. Si un test ajoute 3 items au
  panier et oublie de clear, le test suivant hérite de l'état. → tous les
  tests doivent être **défensivement idempotents** (clear au début).

### 2.5 State partagé

- Session user persistante entre tests (cookies).
- Panier en session persistant.
- Events/adhésions créés par un test visibles dans le test suivant.

→ Les E2E doivent être **indépendants par construction** (préparer leur propre
état) et **nettoyer en fin** (clear cart, logout).

---

## 3. Pourquoi le test passe *maintenant* mais pourrait flaker demain

Mon test `TestPanierMembershipFlow::test_admin_ajoute_adhesion_au_panier_puis_vide`
passe aujourd'hui. Dans une semaine, si :

- Quelqu'un renomme "Adhésion associative Tiers Lustre" →
  `has-text("Solidaire")` peut échouer si le tarif Solidaire est retiré du
  seed.
- Le flow login change (ex: captcha, magic link email) →
  `login_as_admin` timeout sur l'étape Test Mode.
- Une nouvelle langue par défaut → assertions sur texte FR échouent.
- Le `data-testid="membership-firstname"` est renommé → `fill()` timeout.

Le test casse pour une raison **non liée** au code panier. On corrige le test,
c'est de la **maintenance pure** qui pollue les PRs.

---

## 4. Règles que je suivrais pour écrire un E2E

### 4.1 Max 1 E2E par flow métier critique

**Pas 5 variantes.** Un seul "happy path achat billet". Un seul "happy path
adhésion". Les variantes (anonyme vs auth, gratuit vs payant, cart-aware) sont
couvertes en pytest DB-only où on peut tester en 200ms chaque variante.

### 4.2 Un E2E prouve l'intégration, pas la logique

- **Bon** : "Je clique Acheter, je suis redirigé sur Stripe".
- **Mauvais** : "Je vérifie que le prix final après code promo 50% est 5€".
  → celui-là c'est un pytest qui appelle `CommandeService.materialiser()`
  directement, pas du Playwright.

### 4.3 Les fixtures E2E ne créent pas de données métier

Les E2E s'appuient sur le tenant seedé (`demo_data_v2`). Si le test a besoin
d'une donnée particulière (event gratuit, adhésion récurrente), elle doit
être dans le seed standard, pas créée dans la fixture.

→ **aucun `Event.objects.create()` ni `Product.objects.create()` dans les
fixtures E2E.**

### 4.4 Login via force_login, pas via UI

C'est un pré-requis du test, pas son objet. Gain 5-10s par test + élimination
d'un point de rupture majeur.

### 4.5 Pas d'E2E pour du CSS / polish visuel

Les règles UI (tabular-nums, text-wrap balance, offcanvas scroll, badge centré)
ne se testent pas en E2E — validation manuelle ou screenshot testing (séparé).

---

## 5. Plan de stabilisation — session dédiée "E2E panier"

### Étape 1 — Réécrire `login_as_admin` en `force_login` (fondation)

Nouvelle fixture dans `tests/e2e/conftest.py` :

```python
@pytest.fixture(scope="session")
def login_as_admin(browser, admin_email):
    """Force-login via Django session cookie injecté dans le browser.
    ~100ms au lieu de 5s pour le flow UI TEST MODE.
    """
    def _login_as_admin(page):
        # Récupère un sessionid valide via un endpoint de test protégé
        # (à créer : /test_only/force_login/?email=... avec token d'env)
        # OU directement via un shell Django qui exporte le cookie.
        session_id = _get_session_id_for_email(admin_email)
        page.context.add_cookies([{
            'name': 'sessionid',
            'value': session_id,
            'domain': f'{SUB}.{DOMAIN}',
            'path': '/',
        }])
    return _login_as_admin
```

**Deux options d'implémentation** :

**Option A — Endpoint de test dédié** (recommandé)
- Créer `views_test_only.force_login()` accessible uniquement si
  `settings.DEBUG=True` ET un header `X-Test-Token` valide.
- Le conftest fait un HTTP POST vers cet endpoint, récupère le cookie.
- **Avantage** : simple, isolé, sécurisé.
- **Inconvénient** : ajoute du code test-only en prod (mais gated par `DEBUG`).

**Option B — Shell Django + export cookie**
- Le conftest invoque un shell Django qui fait `Client.force_login(user)` + export.
- **Avantage** : pas de code en prod.
- **Inconvénient** : complexe, subprocess + parsing.

### Étape 2 — Supprimer les fixtures de création DB

Les 2 tests pré-existants utilisent `event_gratuit_publie` qui fait
`Event.objects.create()`. Remplacer par :

1. Seed d'un event test dans `demo_data_v2.py` avec un **slug déterministe** :
   ```python
   {"name": "E2E Test — Event gratuit", "slug": "e2e-test-event-gratuit", ...}
   ```
2. Le test E2E navigue vers `/event/e2e-test-event-gratuit/` sans créer.

### Étape 3 — Réécrire les 2 tests pré-existants

Même pattern que `TestPanierMembershipFlow::test_admin_ajoute_adhesion_au_panier_puis_vide`
(livré cette session) :

- Login admin (via force_login fixture)
- Navigate vers l'event/adhésion seedé
- Click add-to-cart
- Assert badge navbar (scopé `.navbar`)
- Navigate `/panier/`
- Assert item présent
- Click checkout (redirect Stripe)

### Étape 4 — Ajouter ~2 E2E pour les fixes critiques de cette session

```python
def test_checkout_redirects_to_stripe(self, page, login_as_admin):
    """Add ticket payant → /panier/ → 'Passer au paiement' → URL Stripe"""
    login_as_admin(page)
    # clear + add ticket payant (seeded)
    # navigate /panier/
    # click 'Passer au paiement'
    page.wait_for_url(
        lambda u: 'checkout.stripe.com' in u,
        timeout=10_000,
        wait_until='domcontentloaded',  # PIEGES 9.28
    )

def test_add_to_cart_and_pay_chains_checkout(self, page, login_as_admin):
    """'Ajouter au panier et payer' → redirect Stripe immédiat"""
    # click sur add-and-pay → expect redirect Stripe
```

### Critère d'arrêt

**Après les 4 étapes, ~5 E2E panier** :

1. Add ticket → panier → vider
2. Add adhésion payante → panier → Stripe redirect
3. Add ticket + checkout direct → Stripe redirect
4. Add + pay → Stripe redirect
5. Cart-aware adhésion obligatoire (le tarif gated apparaît)

**5 tests E2E, pas 20.** L'épreuve de force sur la CI doit être rapide (1-2 min).
Le reste = pytest DB-only où on peut tester toutes les variantes en confort.

---

## 6. CI — point ouvert

Actuellement les E2E ne tournent **que localement**. Risques :

- Chaque dev a un env légèrement différent (locale, certs, docker-compose,
  ports, cache).
- Un test qui passe chez un contributeur peut fail chez un autre.
- Zéro garantie qu'un PR ne casse pas les E2E (elles ne sont pas dans la CI).

### Recommandation

GitHub Actions / GitLab CI avec un job E2E qui :
- Lance `docker compose up` (containers TiBillet + Traefik)
- Installe Playwright (`playwright install-deps chromium` — PIEGES 9.40)
- Lance `poetry run pytest tests/e2e/ --tb=short`
- Artifacts : screenshots/videos en cas d'échec (Playwright trace viewer)

**Coût** : ~5-10 min par run CI. Acceptable pour une suite de ~10 E2E max.

---

## 7. Quand écrire un E2E ? Quand ne pas ?

| Cas | E2E ? |
|-----|-------|
| Fix d'un bug dans une fonction Python pure | Non — unit test |
| Changement de logique d'un `ViewSet` (response JSON/HTML) | Non — pytest DB-only |
| Changement CSS d'un composant | Non — validation manuelle / screenshot testing |
| Fix d'un bug dans un serializer DRF | Non — pytest DB-only |
| Changement de flow HTMX (hx-swap, OOB, triggers) qui impacte l'UX | **Oui** — E2E |
| Nouveau flow bout-en-bout critique (checkout, inscription, cancellation) | **Oui** — E2E |
| Changement du texte d'un bouton | Non |
| Intégration Stripe modifiée (URL success, webhook) | **Oui** — E2E avec mock Stripe server |
| Refactor de code qui ne change pas l'UX | Non — pytest suffit |

**Règle mentale** : "Est-ce que ce changement peut casser l'expérience utilisateur
de manière observable dans un browser sans qu'un pytest ne le détecte ?" Si
oui → E2E. Sinon → pytest.

---

## 8. Alternative : screenshot testing

Pour le polish visuel (CSS, badges, layouts), les E2E "click-and-assert" sont
mauvais. Alternative : **screenshot testing** (Percy, Chromatic, Playwright
`page.screenshot()` + comparaison).

Pattern :
1. Ouvrir la page /panier/ avec un état connu
2. Prendre un screenshot
3. Comparer au baseline (stockage Git LFS ou cloud)
4. Si diff visuel > N% → fail

**Pas pour tout** — uniquement les composants critiques (navbar avec badge,
offcanvas booking, page panier, page event). Besoin d'un setup CI dédié.

**Hors scope Lespass pour l'instant**, à considérer si la prod exige une
stabilité visuelle forte.

---

## 9. Résumé — ce qu'il faut retenir

1. **E2E = smoke test, pas coverage.** Max 1 par flow métier critique.
2. **Test logique en pytest DB-only** — 10x plus rapide, 10x plus fiable.
3. **`force_login` > flow UI** pour les pré-requis de test.
4. **Fixtures E2E ≠ fabrique de données** — utiliser le seed standard.
5. **CI obligatoire** pour que les E2E servent à quelque chose.
6. **Pas de test visuel en E2E** — screenshot testing à la place si besoin.

---

## Références

- `tests/PIEGES.md` — 50+ pièges documentés (9.1-9.50, mises à jour en continu)
- `tests/e2e/conftest.py` — fixtures actuelles (login, page, browser)
- `tests/e2e/test_panier_flow.py` — 3 tests dont 1 ✅ livré Session panier 2026-04
- `Administration/management/commands/demo_data_v2.py` — seed tenant standard
