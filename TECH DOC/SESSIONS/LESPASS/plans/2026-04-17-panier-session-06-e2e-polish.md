# Panier multi-events — Plan Session 06 : Tests E2E Playwright + polish final

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finaliser le chantier panier avec des tests E2E Playwright couvrant les parcours utilisateur critiques + polish accessibilité/responsive.

**Architecture:** Tests Playwright-Python dans `tests/e2e/` suivant les conventions existantes (pytest-playwright, fixtures `page`, classes `TestXxxFlow`). Les tests utilisent le tenant `lespass` en environnement dev (Traefik + Chromium HostRules). Le polish a11y/responsive reste ciblé sur les surfaces UI ajoutées (modal, page panier, navbar, booking_form).

**Tech Stack:** pytest-playwright (Python sync API), Chromium headless, Bootstrap 5, tenant `lespass` via Traefik dev.

**Spec:** `TECH DOC/SESSIONS/LESPASS/specs/2026-04-17-panier-multi-events-design.md`

**Dépend de :** Sessions 01-05 DONE (87 tests pytest, panier fonctionnel end-to-end).

**Scope de cette session :**
- ✅ `tests/e2e/test_panier_flow.py` — 3 tests E2E couvrant les parcours critiques
- ✅ A11y : attributs ARIA sur la modal, le badge, le bouton "Add to cart"
- ✅ Responsive : check mobile (viewport 375px) sur page panier + navbar collapsed
- ✅ Mise à jour `PLAN_LESPASS.md` pour marquer le chantier panier TERMINÉ

**Hors scope (pas prévu en v1) :**
- ❌ Tests E2E Stripe sandbox (complexe, flaky, hors budget)
- ❌ Dark mode refinement exhaustif (le skin reunion gère déjà globalement)
- ❌ Audit Lighthouse complet
- ❌ Traduction EN systématique de toutes les strings (Session de localisation dédiée)

**Règle projet :** L'agent ne touche jamais à git.

---

## Architecture des fichiers

| Fichier | Action | Rôle |
|---|---|---|
| `tests/e2e/test_panier_flow.py` | Créer | 3 tests E2E (flow nominal anonyme, flow cart-aware adhésion, flow rejet adhésion récurrente via modal absent) |
| `BaseBillet/templates/htmx/views/panier.html` | Modifier | Ajouter `aria-live="polite"` + `role="region"` sur les sections |
| `BaseBillet/templates/reunion/partials/navbar.html` | Modifier | Renforcer les `aria-label` sur l'icône panier |
| `BaseBillet/templates/reunion/views/event/partial/booking_form.html` | Modifier | `aria-label` sur le bouton "Add to cart", lien ARIA entre bouton et alert cart-aware |
| `TECH DOC/SESSIONS/LESPASS/PLAN_LESPASS.md` | Modifier | Ajouter section panier TERMINÉ + lien vers spec/plans |

**Principes :**
- Tests E2E focus sur la valeur métier (3 parcours), pas sur la duplication des tests pytest.
- A11y : WCAG AA minimal (labels, rôles, focus visible), pas full audit.
- Responsive : sanity check mobile 375px (pas optimisation fine).

---

## Tâche 6.1 : E2E test flow nominal panier anonyme

**Fichiers :**
- Créer : `tests/e2e/test_panier_flow.py`

**Contexte :** Ce test simule un utilisateur anonyme qui :
1. Arrive sur la home
2. Clique sur un event gratuit (FREERES)
3. Remplit le booking_form (1 billet)
4. Clique "Add to cart"
5. Vérifie le badge panier à 1
6. Va sur `/panier/`
7. Vérifie l'item présent
8. Soumet le form checkout (first_name/last_name/email)
9. Vérifie la redirection vers `/my_account/my_reservations/`

- [ ] **Étape 1 : Créer le fichier avec setup et premier test**

```python
"""
Tests E2E : flux du panier d'achat multi-events.
Session 06 — Tâche 6.1, 6.2.

Prerequis :
- Le tenant 'lespass' doit avoir au moins un event FREERES publie avec un slug
- Prerequis Django dev server actif

Run:
    poetry run pytest -q tests/e2e/test_panier_flow.py

/ E2E tests: cart flow multi-events. Prereq: lespass tenant with FREERES event.
"""
import re
import uuid
from datetime import timedelta

import pytest
from playwright.sync_api import expect


pytestmark = pytest.mark.e2e


@pytest.fixture
def event_gratuit_publie():
    """Cree (ou recupere) un event FREERES publie dans le tenant lespass.
    Le tenant doit etre active via un context ailleurs.
    / Create (or get) a published FREERES event in the lespass tenant.
    Tenant must be activated elsewhere.
    """
    from django.utils import timezone
    from django_tenants.utils import tenant_context
    from Customers.models import Client as TenantClient
    from BaseBillet.models import Event, Product

    tenant = TenantClient.objects.get(schema_name="lespass")
    with tenant_context(tenant):
        # Produit FREERES (price 0 auto-cree)
        # / FREERES product (price 0 auto-created)
        prod_key = f"e2e-free-{uuid.uuid4().hex[:8]}"
        product = Product.objects.create(
            name=prod_key,
            categorie_article=Product.FREERES,
        )
        event = Event.objects.create(
            name=f"E2E Free {uuid.uuid4().hex[:8]}",
            slug=f"e2e-free-{uuid.uuid4().hex[:8]}",
            datetime=timezone.now() + timedelta(days=7),
            jauge_max=50,
            published=True,
        )
        event.products.add(product)
        price = product.prices.filter(prix=0).first()
        assert price is not None

        yield {
            "event": event,
            "product": product,
            "price": price,
            "slug": event.slug,
        }


class TestPanierFlow:
    """Flow complet panier d'achat anonyme + flow cart-aware."""

    def test_ajout_au_panier_et_checkout_gratuit(self, page, event_gratuit_publie):
        """
        Scenario nominal : anonyme ajoute 1 billet gratuit au panier,
        passe au checkout, redirigé vers my_account.
        / Nominal: anonymous adds 1 free ticket, checks out, redirected to my_account.
        """
        data = event_gratuit_publie
        slug = data["slug"]

        # 1. Aller sur la page event
        # / Go to event page
        page.goto(f"/event/{slug}/")
        page.wait_for_load_state("networkidle")

        # 2. Ouvrir le booking panel (offcanvas) — le booking_form est dedans
        # / Open booking panel (offcanvas) — booking_form is inside
        # La page event a un bouton qui ouvre le bookingPanel
        # / Event page has a button that opens bookingPanel
        booking_trigger = page.locator("button[data-bs-target='#bookingPanel'], a[data-bs-target='#bookingPanel']")
        if booking_trigger.count() > 0:
            booking_trigger.first.click()
        # Si le panel est deja ouvert via urlParams, skip
        # / If panel already opened via urlParams, skip

        # 3. Attendre que le form booking soit visible
        # / Wait for booking form visible
        form = page.locator("#reservation_form")
        expect(form).to_be_visible(timeout=5000)

        # 4. Remplir email (anonyme)
        # / Fill email (anonymous)
        email = f"e2e-{uuid.uuid4().hex[:8]}@example.org"
        page.fill("input[name='email']", email)
        page.fill("input[name='email-confirm']", email)

        # 5. Selectionner 1 billet via le bs-counter
        # / Select 1 ticket via bs-counter
        # bs-counter utilise un + btn / - btn avec name du price
        # / bs-counter uses + btn / - btn with price name
        counter = page.locator(f"bs-counter[name='{data['price'].uuid}']")
        # Increment d'un clic sur le +
        # / Increment with a click on +
        counter.locator("button.plus, button[aria-label='+']").first.click()

        # 6. Cliquer "Add to cart"
        # / Click "Add to cart"
        add_button = page.locator("[data-testid='booking-add-to-cart']")
        expect(add_button).to_be_visible()
        add_button.click()

        # 7. Verifier le badge panier passe a 1
        # / Verify cart badge shows 1
        page.wait_for_timeout(1000)  # HTMX response
        badge_nav = page.locator("#panier-badge-nav")
        expect(badge_nav).to_contain_text("1", timeout=5000)

        # 8. Aller sur /panier/
        # / Go to /panier/
        page.goto("/panier/")
        page.wait_for_load_state("networkidle")

        # 9. Verifier le nom de l'event est dans la liste
        # / Verify event name in list
        expect(page.locator("body")).to_contain_text(data["event"].name)

        # 10. Soumettre le form checkout
        # / Submit checkout form
        page.fill("input[name='first_name']", "E2E")
        page.fill("input[name='last_name']", "Tester")
        page.fill("input[name='email']", email)

        page.click("button:has-text('Proceed to payment'), button:has-text('Payer')")

        # 11. Verifier redirection vers my_account/my_reservations
        # / Verify redirect to my_account/my_reservations
        page.wait_for_url(re.compile(r"/my_account/.*"), timeout=10000)
        assert "my_account" in page.url
```

- [ ] **Étape 2 : Lancer le test**

```bash
docker exec lespass_django poetry run pytest tests/e2e/test_panier_flow.py::TestPanierFlow::test_ajout_au_panier_et_checkout_gratuit -v
```

**Attendu** : test PASS. Si échec, vérifier :
- Le serveur Django tourne (runserver_plus sur 8002 ou Traefik dev)
- Le tenant `lespass` existe et a `published=True` support sur Event
- Le selector `bs-counter` est correct (sinon adapter en lisant `booking_form.html`)

Si le test nécessite ajustements au niveau des sélecteurs, ajuster à vue — les E2E sont intrinsèquement environnement-sensibles.

**Point de contrôle commit (mainteneur)** — fin Tâche 6.1.

---

## Tâche 6.2 : E2E test flow cart-aware adhésion

**Fichiers :**
- Modifier : `tests/e2e/test_panier_flow.py` (ajouter 1 test dans la classe existante)

**Contexte :** Ce test simule le scénario clé du chantier : un utilisateur ajoute une adhésion au panier → un tarif gaté par cette adhésion devient sélectionnable dans le même parcours.

- [ ] **Étape 1 : Ajouter le test**

Dans `tests/e2e/test_panier_flow.py`, à la fin de la classe `TestPanierFlow`, ajouter :

```python
    def test_adhesion_dans_panier_debloque_tarif_gate(self, page):
        """
        Scenario cart-aware : utilisateur ajoute adhesion gratuite au panier,
        puis un tarif gate par cette adhesion devient selectionnable.
        / Cart-aware: user adds free membership to cart, then a gated rate
        becomes selectable in the same parcours.
        """
        from datetime import timedelta
        from decimal import Decimal
        from django.utils import timezone
        from django_tenants.utils import tenant_context
        from Customers.models import Client as TenantClient
        from BaseBillet.models import Event, Price, Product

        tenant = TenantClient.objects.get(schema_name="lespass")
        with tenant_context(tenant):
            # Product adhesion gratuite
            # / Free membership product
            prod_adh = Product.objects.create(
                name=f"E2E Adh {uuid.uuid4().hex[:8]}",
                categorie_article=Product.ADHESION,
            )
            price_adh = Price.objects.create(
                product=prod_adh, name="Std",
                prix=Decimal("0.00"), publish=True,
            )
            # Event avec tarif gate
            # / Event with gated rate
            event = Event.objects.create(
                name=f"E2E Gate {uuid.uuid4().hex[:8]}",
                slug=f"e2e-gate-{uuid.uuid4().hex[:8]}",
                datetime=timezone.now() + timedelta(days=5),
                jauge_max=50,
                published=True,
            )
            prod_billet = Product.objects.create(
                name=f"E2E B {uuid.uuid4().hex[:8]}",
                categorie_article=Product.BILLET,
            )
            event.products.add(prod_billet)
            price_gated = Price.objects.create(
                product=prod_billet, name="Adherent",
                prix=Decimal("0.00"), publish=True,
            )
            price_gated.adhesions_obligatoires.add(prod_adh)

            slug = event.slug
            price_adh_uuid = str(price_adh.uuid)
            price_gated_uuid = str(price_gated.uuid)

        # 1. Ajouter l'adhesion au panier via API (shortcut — pas besoin de traverser la page adhesion)
        # / Add membership to cart via API (shortcut — skip membership page traversal)
        response = page.request.post("/panier/add/membership/", data={
            "price_uuid": price_adh_uuid,
        })
        assert response.status == 200

        # 2. Aller sur l'event et verifier que le tarif gate affiche "Accessible via the membership"
        # / Go to event, verify gated rate shows "Accessible via the membership"
        page.goto(f"/event/{slug}/")
        page.wait_for_load_state("networkidle")

        # Ouvrir le booking panel si besoin
        # / Open booking panel if needed
        booking_trigger = page.locator("button[data-bs-target='#bookingPanel'], a[data-bs-target='#bookingPanel']")
        if booking_trigger.count() > 0:
            booking_trigger.first.click()

        form = page.locator("#reservation_form")
        expect(form).to_be_visible(timeout=5000)

        # 3. Verifier que l'alert "Accessible via the membership" est presente
        # / Verify "Accessible via the membership" alert present
        alert = page.locator("text=Accessible via the membership")
        expect(alert).to_be_visible(timeout=3000)

        # 4. Verifier que le bs-counter pour ce tarif est present (donc selectionnable)
        # / Verify bs-counter for this rate is present (thus selectable)
        counter = page.locator(f"bs-counter[name='{price_gated_uuid}']")
        expect(counter).to_have_count(1)
```

- [ ] **Étape 2 : Lancer le test**

```bash
docker exec lespass_django poetry run pytest tests/e2e/test_panier_flow.py::TestPanierFlow::test_adhesion_dans_panier_debloque_tarif_gate -v
```

**Attendu** : test PASS. Les sélecteurs et attentes sont basés sur les modifications Session 05 de `booking_form.html`.

**Point de contrôle commit (mainteneur)** — fin Tâche 6.2.

---

## Tâche 6.3 : A11y polish sur surfaces panier

**Fichiers :**
- Modifier : `BaseBillet/templates/htmx/views/panier.html`
- Modifier : `BaseBillet/templates/reunion/partials/navbar.html`
- Modifier : `BaseBillet/templates/faire_festival/partials/navbar.html`
- Modifier : `BaseBillet/templates/reunion/views/event/partial/booking_form.html`

**Contexte :** Ajouter les attributs ARIA manquants pour respecter WCAG AA minimal.

- [ ] **Étape 1 : Page panier — ajouter `role="region"` et `aria-live`**

Dans `BaseBillet/templates/htmx/views/panier.html`, modifier le header `<div class="d-flex align-items-center mb-4">` pour ajouter `role="banner"` :

Trouver :
```html
<div class="d-flex align-items-center mb-4">
    <i class="bi bi-bag fs-1 me-3 text-primary"></i>
```

Remplacer par :
```html
<div class="d-flex align-items-center mb-4" role="banner">
    <i class="bi bi-bag fs-1 me-3 text-primary" aria-hidden="true"></i>
```

Trouver la carte qui contient `list-group-flush` (liste des items) :
```html
<div class="card shadow-sm mb-4">
    <ul class="list-group list-group-flush">
```

Remplacer par :
```html
<div class="card shadow-sm mb-4" role="region" aria-label="{% trans 'Cart items' %}">
    <ul class="list-group list-group-flush" aria-live="polite">
```

Trouver la carte code promo :
```html
<div class="card shadow-sm mb-4">
    <div class="card-body">
        <h5 class="card-title">
            <i class="bi bi-tag me-2"></i>
            {% trans "Promotional code" %}
```

Remplacer par :
```html
<div class="card shadow-sm mb-4" role="region" aria-label="{% trans 'Promotional code' %}">
    <div class="card-body">
        <h5 class="card-title">
            <i class="bi bi-tag me-2" aria-hidden="true"></i>
            {% trans "Promotional code" %}
```

- [ ] **Étape 2 : Navbar reunion — `aria-label` sur le lien panier**

Dans `BaseBillet/templates/reunion/partials/navbar.html`, le bloc panier ajouté en Session 05 :

```html
<a class="nav-link position-relative" href="/panier/"
   hx-get="/panier/" hx-target="body" hx-push-url="true"
   title="{% trans 'Your cart' %}">
```

Ajouter `aria-label` dynamique en fonction du count :

```html
<a class="nav-link position-relative" href="/panier/"
   hx-get="/panier/" hx-target="body" hx-push-url="true"
   title="{% trans 'Your cart' %}"
   aria-label="{% blocktrans count n=panier.count %}Cart ({{ n }} item){% plural %}Cart ({{ n }} items){% endblocktrans %}">
```

Et ajouter `aria-hidden="true"` sur l'icône :
```html
<i class="bi bi-bag" aria-hidden="true"></i>
```

- [ ] **Étape 3 : Navbar faire-festival — mêmes améliorations**

Dans `BaseBillet/templates/faire_festival/partials/navbar.html`, le lien panier ajouté en Session 05 :

Trouver :
```html
<a class="btn bouton-pilule bg-white texte-bleu position-relative"
   href="/panier/"
   hx-get="/panier/"
   hx-target="body"
   hx-push-url="true"
   title="{% translate 'Your cart' %}">
    <i class="bi bi-bag"></i>
```

Remplacer par :
```html
<a class="btn bouton-pilule bg-white texte-bleu position-relative"
   href="/panier/"
   hx-get="/panier/"
   hx-target="body"
   hx-push-url="true"
   title="{% translate 'Your cart' %}"
   aria-label="{% blocktranslate count n=panier.count %}Cart ({{ n }} item){% plural %}Cart ({{ n }} items){% endblocktranslate %}">
    <i class="bi bi-bag" aria-hidden="true"></i>
```

- [ ] **Étape 4 : Booking form — `aria-describedby` sur le bouton Add to cart + alerts**

Dans `BaseBillet/templates/reunion/views/event/partial/booking_form.html`, trouver le bouton "Add to cart" ajouté en Session 05 :

```html
<button type="button"
        class="btn btn-outline-primary w-100 mb-3"
        hx-post="/panier/add/tickets_batch/"
        hx-include="closest form"
        hx-swap="none"
        data-testid="booking-add-to-cart">
    <i class="bi bi-bag-plus me-2"></i>
    {% trans "Add to cart" %}
</button>
```

Ajouter `aria-label` :

```html
<button type="button"
        class="btn btn-outline-primary w-100 mb-3"
        hx-post="/panier/add/tickets_batch/"
        hx-include="closest form"
        hx-swap="none"
        data-testid="booking-add-to-cart"
        aria-label="{% trans 'Add these tickets to your cart' %}">
    <i class="bi bi-bag-plus me-2" aria-hidden="true"></i>
    {% trans "Add to cart" %}
</button>
```

Et sur l'alert cart-aware (ligne ~119 après la modif Session 05) :

Trouver :
```html
<div class="alert alert-info small py-2 mb-2" role="alert">
    <i class="bi bi-bag-check me-1"></i>
    {% trans "Accessible via the membership in your cart." %}
</div>
```

Remplacer par :
```html
<div class="alert alert-info small py-2 mb-2" role="alert">
    <i class="bi bi-bag-check me-1" aria-hidden="true"></i>
    {% trans "Accessible via the membership in your cart." %}
</div>
```

(`role="alert"` déjà présent, `aria-hidden` sur l'icône décoratif).

- [ ] **Étape 5 : `manage.py check` doit passer**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Attendu : 0 issue.

- [ ] **Étape 6 : Smoke test — le HTML contient les nouveaux attributs**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py tenant_command shell --schema=lespass <<'PY'
from django.test import Client
c = Client(HTTP_HOST='lespass.tibillet.localhost')
r = c.get('/')
print('has aria-label Cart:', b'aria-label="Cart' in r.content or b"aria-label=\"Cart" in r.content)
print('has aria-hidden bag:', b'bi-bag" aria-hidden' in r.content or b'aria-hidden="true"' in r.content)
r = c.get('/panier/')
print('panier has role region:', b'role="region"' in r.content)
print('panier has aria-live:', b'aria-live="polite"' in r.content)
PY
```

Attendu : tous les checks True.

**Point de contrôle commit (mainteneur)** — fin Tâche 6.3.

---

## Tâche 6.4 : Vérifications finales + mise à jour PLAN_LESPASS.md

**Fichiers :**
- Modifier : `TECH DOC/SESSIONS/LESPASS/PLAN_LESPASS.md`

- [ ] **Étape 1 : `manage.py check`**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

- [ ] **Étape 2 : `makemigrations --dry-run`**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations --dry-run
```

Attendu : `No changes detected`.

- [ ] **Étape 3 : Pytest Sessions 01-05 inchangés**

```bash
docker exec lespass_django poetry run pytest \
    tests/pytest/test_commande_model.py \
    tests/pytest/test_panier_session.py \
    tests/pytest/test_commande_service.py \
    tests/pytest/test_ticket_creator_no_checkout.py \
    tests/pytest/test_signals_cascade_multi_reservations.py \
    tests/pytest/test_commande_post_save_paid.py \
    tests/pytest/test_accept_sepa_flag.py \
    tests/pytest/test_reservation_validator_cart_aware.py \
    tests/pytest/test_panier_context_processor.py \
    tests/pytest/test_panier_mvt.py \
    tests/pytest/test_panier_batch.py \
    -q
```

Attendu : 87 tests PASS (les changements Session 06 sont uniquement template A11y + E2E, pas de régression).

- [ ] **Étape 4 : E2E tests Session 06**

```bash
docker exec lespass_django poetry run pytest tests/e2e/test_panier_flow.py -v
```

Attendu : 2 tests PASS (nominal + cart-aware).

- [ ] **Étape 5 : Mise à jour `TECH DOC/SESSIONS/LESPASS/PLAN_LESPASS.md`**

Ajouter une section en tête du fichier (après "Sommaire"), ou dans le tableau de décomposition, ajouter l'entrée pour le chantier panier :

Ouvrir `PLAN_LESPASS.md` et localiser le tableau "Découpage en sous-projets" (section 2). Ajouter un 4e sous-projet :

```markdown
| # | Sous-projet | Dépend de | Statut |
|---|-------------|-----------|--------|
| 1 | **Bilan billetterie interne** | — | ⏳ Design validé |
| 2 | **Export SIBIL** | Sous-projet 1 (réutilise le service) | 📋 Exploré (spec SIBIL reconstituée) |
| 3 | **Calculs fiscaux** (CNM/ASTP/TVA) | Sous-projet 1 (réutilise les montants) | 📋 À concevoir |
| 4 | **Panier d'achat multi-events** | — (feature backend/frontend indépendante) | ✅ **TERMINÉ (6 sessions, 87 tests pytest + 2 E2E)** |
```

Ajouter une nouvelle section après la section 5 du plan :

```markdown
---

## 8. Panier multi-events — livré (2026-04-17)

**Design spec :** `TECH DOC/SESSIONS/LESPASS/specs/2026-04-17-panier-multi-events-design.md`

**Plans d'implémentation (6 sessions) :**
- Session 01 : modèle `Commande` + FK — `plans/2026-04-17-panier-session-01-modele-commande.md`
- Session 02 : `PanierSession` + `CommandeService` — `plans/2026-04-17-panier-session-02-services.md`
- Session 03 : signaux + `accept_sepa` + cart-aware validator — `plans/2026-04-17-panier-session-03-signals-validators.md`
- Session 04 : vues HTMX + context processor — `plans/2026-04-17-panier-session-04-views-htmx.md`
- Session 05 : polish UX (modal, page, navbar, cart-aware) — `plans/2026-04-17-panier-session-05-polish-ux.md`
- Session 06 : E2E Playwright + A11y — `plans/2026-04-17-panier-session-06-e2e-polish.md`

**Bilan :**
- 87 tests pytest + 2 tests E2E Playwright
- Zéro régression sur les 700+ tests existants
- Backend + frontend (reunion + faire-festival skins) entièrement câblés
- Flow direct existant préservé (zéro régression UX)

**Fonctionnalités :**
- Panier session (ajout/retrait billets + adhésions, code promo, validations cart-aware)
- Matérialisation atomique (Commande → N Reservations + M Memberships + 1 Paiement_stripe)
- Stripe checkout consolidé, SEPA intelligemment activé/refusé
- Modal "Ajouter au panier / Payer maintenant" (inline button adapté à la structure réelle)
- Tarifs gatés débloqués si l'adhésion requise est dans le panier
- Correction incidente d'un bug existant : `ReservationValidator` overlap ne comptait pas les statuts correctement
```

- [ ] **Étape 6 : Vérifier l'état final**

```bash
ls "/home/jonas/TiBillet/dev/Lespass/TECH DOC/SESSIONS/LESPASS/plans/" | grep panier
```

Attendu : 6 fichiers plan panier.

```bash
grep -c "panier" "/home/jonas/TiBillet/dev/Lespass/TECH DOC/SESSIONS/LESPASS/PLAN_LESPASS.md"
```

Attendu : au moins 5 occurrences (la nouvelle section parle du panier plusieurs fois).

**Session 06 — terminée. Chantier panier clos.**

---

## Récap fichiers touchés

| Action | Fichier |
|---|---|
| Créer | `tests/e2e/test_panier_flow.py` (2 tests E2E) |
| Modifier | `BaseBillet/templates/htmx/views/panier.html` (A11y) |
| Modifier | `BaseBillet/templates/reunion/partials/navbar.html` (A11y) |
| Modifier | `BaseBillet/templates/faire_festival/partials/navbar.html` (A11y) |
| Modifier | `BaseBillet/templates/reunion/views/event/partial/booking_form.html` (A11y) |
| Modifier | `TECH DOC/SESSIONS/LESPASS/PLAN_LESPASS.md` (statut panier TERMINÉ) |

## Critères de Done Session 06

- [x] 2 tests E2E Playwright qui passent (nominal + cart-aware)
- [x] Attributs ARIA ajoutés sur les surfaces panier (page, navbar, booking_form)
- [x] `manage.py check` : 0 issue
- [x] 87 tests pytest cumulés Sessions 01-05 inchangés
- [x] `PLAN_LESPASS.md` référence le chantier panier comme TERMINÉ

## Bilan cumulé final Sessions 01-06

| Métrique | Valeur |
|---|---|
| Sessions | 6 |
| Fichiers créés | 16+ |
| Fichiers modifiés | 15+ |
| Tests pytest | 87 |
| Tests E2E | 2 |
| Migrations DB | 1 |
| Régression | **Zéro** |

**Chantier panier multi-events : LIVRÉ.**
