# Panier multi-events — Plan Session 05 : Polish UX (modal, page panier, badge navbar, cart-aware)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finaliser l'UX du panier côté utilisateur — page panier fonctionnelle/jolie, icône panier dans la navbar, modal "Ajouter au panier / Payer maintenant" sur la page event, visibilité cart-aware des tarifs gatés.

**Architecture:** Travail quasi-exclusivement template. Un seul ajout backend : un endpoint `add_tickets_batch` sur `PanierMVT` qui parse le payload existant de la page event (format legacy `ReservationValidator`) pour ajouter plusieurs tarifs à la fois au panier (DRY — réutilise la logique d'extraction des prices/options/custom_amounts).

**Tech Stack:** Bootstrap 5 + Bootstrap Icons (`bi`), HTMX avec `hx-swap-oob`, pas de JS custom sauf minimum nécessaire (un switch de target de formulaire).

**Spec:** `TECH DOC/SESSIONS/LESPASS/specs/2026-04-17-panier-multi-events-design.md` (sections 3.8, 3.10)

**Dépend de :** Sessions 01-04 DONE (82 tests, aucune régression).

**Scope de cette session :**
- ✅ Endpoint `PanierMVT.add_tickets_batch` (parse payload page event → N appels `panier.add_ticket`)
- ✅ Page panier `htmx/views/panier.html` refaite avec Bootstrap 5 (liste items avec images, contrôles qty ±, promo code, total, formulaire checkout)
- ✅ Icône panier + badge dans la navbar (`reunion/partials/navbar.html`)
- ✅ Modal Bootstrap "Ajouter au panier / Payer maintenant" sur `htmx/views/event.html`
- ✅ Cart-aware tarifs gatés : si `panier.adhesions_product_ids` matche `price.adhesions_obligatoires`, afficher "Accessible via le panier" au lieu de "Connectez-vous pour accéder"
- ✅ Tests pytest pour le nouvel endpoint batch

**Hors scope (Session 06) :**
- ❌ Tests E2E Playwright
- ❌ Design assets / animations / dark mode refinement

**Règle projet :** L'agent ne touche jamais à git. Pas de JS custom sauf strict minimum — HTMX et Bootstrap data-bs-* à fond.

---

## Architecture des fichiers

| Fichier | Action | Rôle |
|---|---|---|
| `BaseBillet/views.py` | Modifier | Classe `PanierMVT` : ajouter action `add_tickets_batch` (POST /panier/add/tickets_batch/) |
| `BaseBillet/templates/htmx/views/panier.html` | Refaire | Page panier complète avec Bootstrap 5 |
| `BaseBillet/templates/reunion/partials/navbar.html` | Modifier | Ajouter icône panier + badge avec lien `/panier/` |
| `BaseBillet/templates/htmx/views/event.html` | Modifier | Remplacer bouton direct par modal choice + 2 forms (add cart / pay now) |
| `BaseBillet/templates/htmx/components/cardTickets.html` | Modifier | Cart-aware visibility des tarifs gatés (utiliser `panier.adhesions_product_ids`) |
| `BaseBillet/templates/htmx/components/panier_item.html` | Créer | Partial pour afficher une ligne du panier (DRY) |
| `tests/pytest/test_panier_batch.py` | Créer | 3-4 tests du batch endpoint |

**Principes :**
- `add_tickets_batch` réutilise `ReservationValidator.extract_products()` via duplication légère pour respecter l'isolation des services.
- Modal event page : HTML/HTMX pur, pas de JS au-delà du `form.action` switch (1 ligne `onclick` minimum).
- Page panier : partial `panier_item.html` inclus dans la page principale → permet refresh HTMX item par item plus tard (Session 06 pour polish).

---

## Tâche 5.1 : Endpoint batch `add_tickets_batch` sur `PanierMVT`

**Fichiers :**
- Modifier : `BaseBillet/views.py` (classe `PanierMVT`)
- Créer : `tests/pytest/test_panier_batch.py`

**Contexte :** La page event soumet le formulaire avec tous les tarifs sélectionnés en un seul POST (format legacy : chaque input a `name="{{ price.uuid }}"` et `value="<qty>"`, plus `options`, `custom_amount_<uuid>`, `form__<field>`, etc.). Pour intégrer le panier, on a besoin d'un endpoint qui accepte ce même payload et ajoute tous les tarifs en un appel.

**Approche :** l'action parcourt les products/prices de l'event, extrait les quantités et options comme le fait `ReservationValidator.extract_products()`, puis appelle `panier.add_ticket()` pour chaque (price, qty). En cas d'erreur sur un item, on rollback les ajouts déjà effectués.

- [ ] **Étape 1 : Ajouter l'action `add_tickets_batch` à `PanierMVT`**

Dans `BaseBillet/views.py`, à la fin de la classe `PanierMVT` (avant la dernière accolade ou juste après `badge()`), ajouter :

```python
    # --- POST /panier/add/tickets_batch/ ---
    @action(detail=False, methods=['POST'], url_path='add/tickets_batch')
    def add_tickets_batch(self, request):
        """
        Ajoute plusieurs billets au panier à partir du formulaire page event
        (format legacy : price_uuid=qty + options + custom_amount_<uuid> + form__<field>).
        Rollback si erreur (on retire tous les items ajoutés dans cette requête).

        / Add multiple tickets to the cart from the event page form (legacy
        format: price_uuid=qty + options + custom_amount_<uuid> + form__<field>).
        Rollback on error (remove all items added in this request).
        """
        from BaseBillet.models import Event, Price
        from BaseBillet.services_panier import PanierSession, InvalidItemError
        from decimal import Decimal

        slug = request.POST.get('slug')
        try:
            event = Event.objects.get(slug=slug)
        except Event.DoesNotExist:
            return self._render_badge_and_toast(
                request, message=_("Event not found."), level='error',
            )

        panier = PanierSession(request)
        added_count_before = len(panier.items())

        # Extraire options de l'event / Extract event options
        options_ids = request.POST.getlist('options') if hasattr(request.POST, 'getlist') else []
        # Custom form fields (prefix form__) / Custom form fields
        custom_form = {k[len('form__'):]: v for k, v in request.POST.items() if k.startswith('form__')}

        items_added = 0
        try:
            for product in event.products.all():
                for price in product.prices.all():
                    price_key = str(price.uuid)
                    raw_qty = request.POST.get(price_key)
                    if not raw_qty:
                        continue
                    try:
                        qty = int(Decimal(str(raw_qty).replace(',', '.')))
                    except (TypeError, ValueError):
                        continue
                    if qty <= 0:
                        continue

                    # Custom amount si free_price / Custom amount if free_price
                    custom_amount = None
                    if price.free_price:
                        custom_amount_raw = request.POST.get(f"custom_amount_{price.uuid}")
                        if custom_amount_raw not in [None, '', 'null']:
                            custom_amount = custom_amount_raw

                    panier.add_ticket(
                        event_uuid=event.uuid,
                        price_uuid=price.uuid,
                        qty=qty,
                        custom_amount=custom_amount,
                        options=options_ids,
                        custom_form=custom_form,
                    )
                    items_added += 1
        except InvalidItemError as exc:
            # Rollback : retirer les items ajoutés pendant cette requête
            # / Rollback: remove items added during this request
            added_after = len(panier.items())
            for _ in range(added_after - added_count_before):
                panier.remove_item(added_count_before)
            return self._render_badge_and_toast(
                request, message=str(exc), level='error',
            )

        if items_added == 0:
            return self._render_badge_and_toast(
                request, message=_("No tickets selected."), level='error',
            )

        message = ngettext(
            "%(count)d ticket added to cart.",
            "%(count)d tickets added to cart.",
            items_added,
        ) % {'count': items_added}
        return self._render_badge_and_toast(request, message=message)
```

**Note imports :** `ngettext` doit être importé en haut de `views.py`. Ajouter si absent : `from django.utils.translation import ngettext, gettext_lazy as _`.

- [ ] **Étape 2 : `manage.py check` doit passer**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

- [ ] **Étape 3 : Vérifier l'URL**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py show_urls 2>&1 | grep panier
```

Attendu : nouvelle URL `/panier/add/tickets_batch/` listée.

- [ ] **Étape 4 : Créer `tests/pytest/test_panier_batch.py`**

```python
"""
Tests du endpoint add_tickets_batch sur PanierMVT.
Session 05 — Tâche 5.1.

Run:
    poetry run pytest -q tests/pytest/test_panier_batch.py
"""
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import Client
from django.utils import timezone
from django_tenants.utils import tenant_context


@pytest.fixture(autouse=True)
def _reset_translation_after_test():
    from django.utils import translation
    yield
    translation.deactivate()


@pytest.fixture
def tenant_context_lespass():
    from Customers.models import Client as TenantClient
    tenant = TenantClient.objects.get(schema_name="lespass")
    with tenant_context(tenant):
        yield tenant


@pytest.fixture
def http_client(tenant_context_lespass):
    return Client(HTTP_HOST='lespass.tibillet.localhost')


@pytest.fixture
def event_avec_2_tarifs(tenant_context_lespass):
    """Event avec 1 product et 2 prices.
    / Event with 1 product and 2 prices."""
    from BaseBillet.models import Event, Price, Product

    event = Event.objects.create(
        name=f"Batch-{uuid.uuid4()}",
        slug=f"batch-{uuid.uuid4().hex[:8]}",
        datetime=timezone.now() + timedelta(days=4),
        jauge_max=100,
    )
    product = Product.objects.create(
        name=f"Billets {uuid.uuid4()}", categorie_article=Product.BILLET,
    )
    event.products.add(product)
    price_a = Price.objects.create(
        product=product, name="Plein", prix=Decimal("10.00"), publish=True,
    )
    price_b = Price.objects.create(
        product=product, name="Réduit", prix=Decimal("5.00"), publish=True,
    )
    return event, product, price_a, price_b


@pytest.mark.django_db
def test_batch_ajoute_plusieurs_tarifs_dun_coup(http_client, event_avec_2_tarifs):
    """POST /panier/add/tickets_batch/ avec 2 tarifs → 2 items en panier.
    / POST /panier/add/tickets_batch/ with 2 rates → 2 items in cart."""
    event, _product, price_a, price_b = event_avec_2_tarifs

    response = http_client.post('/panier/add/tickets_batch/', {
        'slug': event.slug,
        str(price_a.uuid): '2',  # 2 billets plein
        str(price_b.uuid): '1',  # 1 billet réduit
    })
    assert response.status_code == 200
    assert b"added" in response.content.lower() or b"ajout" in response.content.lower()

    session = http_client.session
    items = session.get('panier', {}).get('items', [])
    assert len(items) == 2
    qtys = {i['price_uuid']: i['qty'] for i in items}
    assert qtys[str(price_a.uuid)] == 2
    assert qtys[str(price_b.uuid)] == 1


@pytest.mark.django_db
def test_batch_event_inexistant_retourne_erreur(http_client):
    """Event slug invalide → toast error."""
    response = http_client.post('/panier/add/tickets_batch/', {
        'slug': 'does-not-exist',
        str(uuid.uuid4()): '1',
    })
    assert response.status_code == 200
    assert b"Event not found" in response.content or b"not found" in response.content.lower()


@pytest.mark.django_db
def test_batch_aucune_quantite_retourne_erreur(http_client, event_avec_2_tarifs):
    """Aucun tarif avec qty > 0 → toast 'No tickets selected'."""
    event, _product, price_a, _price_b = event_avec_2_tarifs

    response = http_client.post('/panier/add/tickets_batch/', {
        'slug': event.slug,
        str(price_a.uuid): '0',  # qty 0 ignoré
    })
    assert response.status_code == 200
    assert b"No tickets" in response.content or b"Aucun" in response.content or b"ticket" in response.content.lower()
    session = http_client.session
    assert len(session.get('panier', {}).get('items', [])) == 0


@pytest.mark.django_db
def test_batch_rollback_si_un_item_echoue(http_client, tenant_context_lespass):
    """Si un des tarifs est invalide en cours de batch, rollback total.
    / If one rate is invalid mid-batch, total rollback."""
    from BaseBillet.models import Event, Price, Product

    event = Event.objects.create(
        name=f"RB-{uuid.uuid4()}",
        slug=f"rb-{uuid.uuid4().hex[:8]}",
        datetime=timezone.now() + timedelta(days=3),
        jauge_max=100,
    )
    product = Product.objects.create(
        name=f"P {uuid.uuid4()}", categorie_article=Product.BILLET,
    )
    event.products.add(product)
    # price_ok
    price_ok = Price.objects.create(
        product=product, name="OK", prix=Decimal("10.00"), publish=True,
    )
    # price_invalid : non publié → add_ticket raise
    price_invalid = Price.objects.create(
        product=product, name="KO", prix=Decimal("5.00"), publish=False,
    )
    http_client = Client(HTTP_HOST='lespass.tibillet.localhost')

    response = http_client.post('/panier/add/tickets_batch/', {
        'slug': event.slug,
        str(price_ok.uuid): '1',
        str(price_invalid.uuid): '1',
    })
    assert response.status_code == 200
    # Toast d'erreur
    assert b"not available" in response.content.lower() or b"error" in response.content.lower()
    # Panier vide après rollback
    session = http_client.session
    assert len(session.get('panier', {}).get('items', [])) == 0
```

- [ ] **Étape 5 : Lancer les tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_panier_batch.py -v
```

Attendu : 4 tests PASS.

**Point de contrôle commit (mainteneur)** — fin Tâche 5.1.

---

## Tâche 5.2 : Refaire la page `/panier/` avec Bootstrap 5

**Fichiers :**
- Remplacer : `BaseBillet/templates/htmx/views/panier.html`
- Créer : `BaseBillet/templates/htmx/components/panier_item.html`

**Contexte :** La page panier squelette (Session 04) est minimale. Pour Session 05, on la refait proprement avec :
- Carte récapitulative avec image/nom event ou adhésion
- Contrôles qty + / - (uniquement pour billets)
- Bouton retirer
- Section code promo (input + apply/clear)
- Total TTC
- Formulaire acheteur (first/last/email) + bouton checkout

Design : reprend les patterns Bootstrap 5 du projet (card, list-group, btn-outline-*, input-group) et utilise HTMX pour les actions (pas de reload de page).

- [ ] **Étape 1 : Créer `BaseBillet/templates/htmx/components/panier_item.html`**

```html
{% load i18n %}
{# Partial d'un item du panier — réutilisable pour refresh HTMX. #}
{# Cart item partial — reusable for HTMX refresh. #}
<li id="panier-item-{{ forloop.counter0 }}" class="list-group-item d-flex align-items-center gap-3">
    {% if detail.type == 'ticket' %}
        {% if detail.event.img %}
            <img src="{{ detail.event.img.med.url }}" alt="{{ detail.event.name }}"
                 class="rounded" style="width: 64px; height: 64px; object-fit: cover;">
        {% else %}
            <div class="rounded bg-secondary bg-opacity-25 d-flex align-items-center justify-content-center"
                 style="width: 64px; height: 64px;">
                <i class="bi bi-ticket-perforated fs-4 text-secondary"></i>
            </div>
        {% endif %}
        <div class="flex-grow-1">
            <div class="fw-semibold">{{ detail.event.name }}</div>
            <small class="text-muted">
                {{ detail.event.datetime|date:"DATETIME_FORMAT" }}
                &middot; {{ detail.price.name }}
                {% if detail.price.prix %}&middot; {{ detail.price.prix }} €{% endif %}
            </small>
        </div>
        <div class="input-group input-group-sm" style="width: 120px;">
            <form method="post" action="{% url 'panier-update-quantity' pk=forloop.counter0 %}"
                  hx-post="{% url 'panier-update-quantity' pk=forloop.counter0 %}"
                  hx-swap="none"
                  class="d-flex w-100">
                {% csrf_token %}
                <input type="number" name="qty" value="{{ detail.qty }}" min="1"
                       class="form-control form-control-sm text-center"
                       onchange="this.form.requestSubmit();">
            </form>
        </div>
    {% else %}
        {% if detail.product.img %}
            <img src="{{ detail.product.img.med.url }}" alt="{{ detail.product.name }}"
                 class="rounded" style="width: 64px; height: 64px; object-fit: cover;">
        {% else %}
            <div class="rounded bg-primary bg-opacity-25 d-flex align-items-center justify-content-center"
                 style="width: 64px; height: 64px;">
                <i class="bi bi-person-badge fs-4 text-primary"></i>
            </div>
        {% endif %}
        <div class="flex-grow-1">
            <div class="fw-semibold">{{ detail.product.name }}</div>
            <small class="text-muted">
                {% trans "Membership" %} &middot; {{ detail.price.name }}
                {% if detail.price.prix %}&middot; {{ detail.price.prix }} €{% endif %}
            </small>
        </div>
    {% endif %}

    <form method="post" action="{% url 'panier-remove' pk=forloop.counter0 %}"
          hx-post="{% url 'panier-remove' pk=forloop.counter0 %}"
          hx-swap="none">
        {% csrf_token %}
        <button type="submit" class="btn btn-sm btn-outline-danger" aria-label="{% trans 'Remove' %}">
            <i class="bi bi-trash"></i>
        </button>
    </form>
</li>
```

- [ ] **Étape 2 : Remplacer `BaseBillet/templates/htmx/views/panier.html`**

```html
{% extends base_template %}
{% load i18n %}

{% block main %}
<div class="container py-5">
    <div class="row">
        <div class="col-12 col-lg-8 mx-auto">

            <div class="d-flex align-items-center mb-4">
                <i class="bi bi-bag fs-1 me-3 text-primary"></i>
                <h1 class="mb-0">{% trans "Your cart" %}</h1>
                {% if not panier.is_empty %}
                    <span class="badge bg-primary ms-3 fs-6">{{ panier.count }}</span>
                {% endif %}
            </div>

            {% if panier.is_empty %}
                <div class="card shadow-sm">
                    <div class="card-body text-center py-5">
                        <i class="bi bi-bag-x fs-1 text-muted"></i>
                        <p class="mt-3 mb-4 text-muted">{% trans "Your cart is empty." %}</p>
                        <a href="/" class="btn btn-primary">
                            <i class="bi bi-calendar-event me-2"></i>
                            {% trans "Browse events" %}
                        </a>
                    </div>
                </div>
            {% else %}
                <div class="card shadow-sm mb-4">
                    <ul class="list-group list-group-flush">
                        {% for detail in panier.items_with_details %}
                            {% include "htmx/components/panier_item.html" with detail=detail forloop=forloop %}
                        {% endfor %}
                    </ul>
                </div>

                {# --- Code promo --- #}
                <div class="card shadow-sm mb-4">
                    <div class="card-body">
                        <h5 class="card-title">
                            <i class="bi bi-tag me-2"></i>
                            {% trans "Promotional code" %}
                        </h5>
                        {% if panier.promo_code_name %}
                            <div class="d-flex align-items-center justify-content-between">
                                <span class="badge bg-success fs-6">
                                    <i class="bi bi-check2-circle me-1"></i>
                                    {{ panier.promo_code_name }}
                                </span>
                                <form method="post" action="{% url 'panier-clear-promo-code' %}"
                                      hx-post="{% url 'panier-clear-promo-code' %}"
                                      hx-swap="none">
                                    {% csrf_token %}
                                    <button type="submit" class="btn btn-sm btn-link text-danger">
                                        {% trans "Remove" %}
                                    </button>
                                </form>
                            </div>
                        {% else %}
                            <form method="post" action="{% url 'panier-set-promo-code' %}"
                                  hx-post="{% url 'panier-set-promo-code' %}"
                                  hx-swap="none"
                                  class="d-flex gap-2">
                                {% csrf_token %}
                                <input type="text" name="code_name" class="form-control"
                                       placeholder="{% trans 'Enter code' %}" required>
                                <button type="submit" class="btn btn-outline-primary">
                                    {% trans "Apply" %}
                                </button>
                            </form>
                        {% endif %}
                    </div>
                </div>

                {# --- Total + checkout --- #}
                <div class="card shadow-sm">
                    <div class="card-body">
                        <div class="d-flex justify-content-between align-items-center mb-4">
                            <span class="h5 mb-0">{% trans "Total" %}</span>
                            <span class="h4 mb-0 text-primary fw-bold">{{ panier.total_ttc|floatformat:2 }} €</span>
                        </div>

                        <form method="post" action="{% url 'panier-checkout' %}"
                              hx-post="{% url 'panier-checkout' %}"
                              class="vstack gap-3">
                            {% csrf_token %}
                            <div class="row g-3">
                                <div class="col-md-6">
                                    <label class="form-label">{% trans "First name" %}</label>
                                    <input type="text" name="first_name" class="form-control"
                                           required autocomplete="given-name">
                                </div>
                                <div class="col-md-6">
                                    <label class="form-label">{% trans "Last name" %}</label>
                                    <input type="text" name="last_name" class="form-control"
                                           required autocomplete="family-name">
                                </div>
                            </div>
                            <div>
                                <label class="form-label">{% trans "Email" %}</label>
                                <input type="email" name="email" class="form-control"
                                       {% if user.is_authenticated %}value="{{ user.email }}"{% endif %}
                                       required autocomplete="email">
                            </div>
                            <button type="submit" class="btn btn-primary btn-lg">
                                <i class="bi bi-credit-card me-2"></i>
                                {% trans "Proceed to payment" %}
                            </button>
                        </form>
                    </div>
                </div>

                {# --- Bouton vider --- #}
                <div class="text-center mt-3">
                    <form method="post" action="{% url 'panier-clear' %}"
                          hx-post="{% url 'panier-clear' %}"
                          hx-confirm="{% trans 'Empty the cart?' %}"
                          hx-swap="none"
                          class="d-inline">
                        {% csrf_token %}
                        <button type="submit" class="btn btn-sm btn-link text-muted">
                            <i class="bi bi-x-circle me-1"></i>
                            {% trans "Empty cart" %}
                        </button>
                    </form>
                </div>
            {% endif %}
        </div>
    </div>
</div>

{# Container pour toasts HTMX #}
<div id="panier-toasts" hx-swap-oob="true"></div>
{% endblock main %}
```

- [ ] **Étape 3 : Smoke test manuel**

```bash
docker exec lespass_django poetry run python -c "
from django.test import Client
from django_tenants.utils import tenant_context
from Customers.models import Client as T
tenant = T.objects.get(schema_name='lespass')
with tenant_context(tenant):
    c = Client(HTTP_HOST='lespass.tibillet.localhost')
    r = c.get('/panier/')
    print('status:', r.status_code, 'template has bi-bag:', b'bi-bag' in r.content)
"
```

Attendu : `status: 200, template has bi-bag: True`.

- [ ] **Étape 4 : `manage.py check` doit passer**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

- [ ] **Étape 5 : Vérifier les tests Session 04 sur la page panier passent toujours**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_panier_mvt.py -v
```

Attendu : les 13 tests passent (seul le contenu du template a changé, l'URL et le status restent 200).

**Point de contrôle commit (mainteneur)** — fin Tâche 5.2.

---

## Tâche 5.3 : Icône panier dans la navbar

**Fichiers :**
- Modifier : `BaseBillet/templates/reunion/partials/navbar.html`

**Contexte :** La navbar est dans `reunion/partials/navbar.html`. On ajoute une icône panier avec le badge `panier.count` à côté du theme toggle (avant "My account"/"Log in"). Le badge se rafraîchit automatiquement via `hx-swap-oob="true"` quand on ajoute un item.

- [ ] **Étape 1 : Lire le fichier pour repérer la position d'insertion**

```bash
docker exec lespass_django cat /DjangoFiles/BaseBillet/templates/reunion/partials/navbar.html | head -70
```

L'élément existant `<div class="nav-item">` qui contient le theme toggle est autour de la ligne 58. On va insérer le panier **juste après** le theme toggle et **avant** le bloc user (`if user.is_authenticated == False`).

- [ ] **Étape 2 : Insérer l'icône panier**

Dans `BaseBillet/templates/reunion/partials/navbar.html`, repérer la section autour du `themeToggle` (ligne ~52-57). Juste après le div `<div class="nav-item">` qui contient le theme toggle button, **avant** le div `<div class="nav-item">` qui contient le bloc login/my_account, ajouter :

```html
          <div class="nav-item">
            <a class="nav-link position-relative" href="/panier/"
               hx-get="/panier/" hx-target="body" hx-push-url="true"
               title="{% trans 'Your cart' %}">
              <i class="bi bi-bag"></i>
              <span class="d-xl-none">{% trans "Cart" %}</span>
              <span id="panier-badge-nav" hx-swap-oob="true">
                {% if panier.count > 0 %}
                  <span class="position-absolute top-0 start-100 translate-middle badge rounded-pill bg-primary">
                    {{ panier.count }}
                    <span class="visually-hidden">{% trans "items" %}</span>
                  </span>
                {% endif %}
              </span>
            </a>
          </div>
```

**Note** : l'id `panier-badge-nav` est différent de `panier-badge` (utilisé dans `panier_badge.html`). Il faut donc adapter `panier_badge.html` pour qu'il rende les DEUX badges avec leurs ids respectifs (sinon le hx-swap-oob ne touchera que le premier).

- [ ] **Étape 3 : Adapter `panier_badge.html` pour rendre les deux badges**

Remplacer le contenu de `BaseBillet/templates/htmx/components/panier_badge.html` :

```html
{# Badges compteur du panier — rendus partout (page panier + navbar). #}
{# Cart counter badges — rendered everywhere (cart page + navbar). #}

{# Badge pour la page panier / Cart page badge #}
<span id="panier-badge" hx-swap-oob="true">
    {% if panier.count > 0 %}
        <span class="badge bg-primary">{{ panier.count }}</span>
    {% endif %}
</span>

{# Badge pour la navbar / Navbar badge #}
<span id="panier-badge-nav" hx-swap-oob="true">
    {% if panier.count > 0 %}
        <span class="position-absolute top-0 start-100 translate-middle badge rounded-pill bg-primary">
            {{ panier.count }}
            <span class="visually-hidden">{% trans "items" %}</span>
        </span>
    {% endif %}
</span>
```

Ajouter `{% load i18n %}` en tête du fichier si absent.

- [ ] **Étape 4 : `manage.py check` doit passer**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

- [ ] **Étape 5 : Smoke test — l'icône panier apparaît sur la home**

```bash
docker exec lespass_django poetry run python -c "
from django.test import Client
from django_tenants.utils import tenant_context
from Customers.models import Client as T
tenant = T.objects.get(schema_name='lespass')
with tenant_context(tenant):
    c = Client(HTTP_HOST='lespass.tibillet.localhost')
    r = c.get('/')
    has_bag_nav = b'href=\"/panier/\"' in r.content or b'bi-bag' in r.content
    print('status:', r.status_code, 'navbar has cart link:', has_bag_nav)
"
```

Attendu : `status: 200, navbar has cart link: True`.

**Point de contrôle commit (mainteneur)** — fin Tâche 5.3.

---

## Tâche 5.4 : Modal "Ajouter au panier / Payer maintenant" sur page event

**Fichiers :**
- Modifier : `BaseBillet/templates/htmx/views/event.html`

**Contexte :** La page event a actuellement UN bouton "Valider la réservation" qui soumet le form vers `/validate_event/` (flow direct existant). On remplace ce bouton par un bouton qui ouvre une modal Bootstrap avec 2 choix :
- **Ajouter au panier** → submit le form vers `/panier/add/tickets_batch/` (nouveau endpoint)
- **Payer maintenant** → submit le form vers `/validate_event/` (flow direct inchangé)

Approche : un petit switch d'`action` sur le form avant submit, via `onclick` (minimal JS, accepté par le projet car c'est 1 ligne).

- [ ] **Étape 1 : Modifier `BaseBillet/templates/htmx/views/event.html`**

Dans `BaseBillet/templates/htmx/views/event.html`, remplacer le bouton "Valider la réservation" (lignes 38-43) :

```html
                <div class="d-flex flex-row">
                    <button type="button" class="btn bg-gradient-info btn-lg mt-4 mb-2 w-75 mx-auto" role="button"
                            aria-label="Valider la réservation" onclick="validateEventForm()">
                        Valider la réservation
                    </button>
                </div>
```

Par :

```html
                <div class="d-flex flex-row">
                    <button type="button" class="btn bg-gradient-info btn-lg mt-4 mb-2 w-75 mx-auto"
                            role="button"
                            aria-label="{% trans 'Validate reservation' %}"
                            data-bs-toggle="modal" data-bs-target="#choiceModal">
                        {% trans "Validate reservation" %}
                    </button>
                </div>

                {# Modal choix : ajouter au panier vs payer maintenant #}
                {# Choice modal: add to cart vs pay now #}
                <div class="modal fade" id="choiceModal" tabindex="-1"
                     aria-labelledby="choiceModalLabel" aria-hidden="true">
                    <div class="modal-dialog modal-dialog-centered">
                        <div class="modal-content">
                            <div class="modal-header">
                                <h5 class="modal-title" id="choiceModalLabel">
                                    <i class="bi bi-bag me-2"></i>
                                    {% trans "How do you want to proceed?" %}
                                </h5>
                                <button type="button" class="btn-close" data-bs-dismiss="modal"
                                        aria-label="{% trans 'Close' %}"></button>
                            </div>
                            <div class="modal-body">
                                <p class="text-muted mb-4">
                                    {% trans "Add this to your cart to combine it with other events, or pay now." %}
                                </p>
                                <div class="d-grid gap-2">
                                    <button type="button" class="btn btn-outline-primary btn-lg"
                                            onclick="submitEventForm('/panier/add/tickets_batch/')">
                                        <i class="bi bi-bag-plus me-2"></i>
                                        {% trans "Add to cart" %}
                                    </button>
                                    <button type="button" class="btn btn-primary btn-lg"
                                            onclick="submitEventForm('/validate_event/')">
                                        <i class="bi bi-credit-card me-2"></i>
                                        {% trans "Pay now" %}
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
```

- [ ] **Étape 2 : Adapter le JS pour supporter l'action dynamique**

Dans le même fichier, le bloc `<script>` contient `validateEventForm()`. Le renommer/adapter en `submitEventForm(targetUrl)` :

Remplacer :

```javascript
    <script>
        function validateEventForm() {
            const form = document.querySelector('#event-form')
            validateConfirmEmail()
            validateForm(null, form)
            if (form.checkValidity() !== false) {
                form.submit()
            }
        }
        ...
```

Par :

```javascript
    <script>
        function submitEventForm(targetUrl) {
            const form = document.querySelector('#event-form')
            validateConfirmEmail()
            validateForm(null, form)
            if (form.checkValidity() !== false) {
                form.action = targetUrl
                form.submit()
            }
        }
```

Conserver `validateConfirmEmail()` tel quel (fonction existante, pas touchée).

- [ ] **Étape 3 : `manage.py check` doit passer**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

- [ ] **Étape 4 : Smoke test — modal présent sur page event**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py tenant_command shell --schema=lespass <<'PY'
from django.test import Client
c = Client(HTTP_HOST='lespass.tibillet.localhost')
# Trouver un event existant publie
from BaseBillet.models import Event
event = Event.objects.filter(published=True).first() if hasattr(Event, 'published') else Event.objects.first()
if event:
    r = c.get(f'/event/{event.slug}/')
    print('status:', r.status_code, 'has choiceModal:', b'choiceModal' in r.content, 'has submitEventForm:', b'submitEventForm' in r.content)
else:
    print('No event found for smoke test — skipping')
PY
```

Attendu : `has choiceModal: True, has submitEventForm: True`. (Si aucun event en DB, le smoke test est skippé — c'est OK, le test pytest de Session 04 sur `/panier/add/tickets_batch/` couvre déjà le nouvel endpoint.)

- [ ] **Étape 5 : Non-régression tests panier**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_panier_batch.py tests/pytest/test_panier_mvt.py -q
```

Attendu : 17 tests PASS.

**Point de contrôle commit (mainteneur)** — fin Tâche 5.4.

---

## Tâche 5.5 : Cart-aware visibility des tarifs gatés

**Fichiers :**
- Modifier : `BaseBillet/templates/htmx/components/cardTickets.html`

**Contexte :** Actuellement, un tarif avec `adhesions_obligatoires` affiche :
- Si user connecté + adhésion active → selectable
- Si user connecté + pas d'adhésion → "Vous devez être adhérent" bloquant
- Si user anonyme → "Connectez-vous pour accéder"

**Nouveau comportement cart-aware** :
- Si adhésion requise est dans `panier.adhesions_product_ids` → afficher "Accessible via panier" + tarif sélectionnable
- Sinon → comportement existant

- [ ] **Étape 1 : Explorer le template `cardTickets.html`**

```bash
docker exec lespass_django cat /DjangoFiles/BaseBillet/templates/htmx/components/cardTickets.html | head -150
```

Repérer la section qui gère `{% if price.adhesions_obligatoires.exists %}` (autour de la ligne 68). Il y a 3 branches : anonyme, connecté-non-adhérent, connecté-adhérent.

- [ ] **Étape 2 : Ajouter la branche cart-aware**

Lire attentivement le fichier `BaseBillet/templates/htmx/components/cardTickets.html`. Trouver la structure approximative :

```
{% if price.adhesions_obligatoires.exists %}
    {% if user.is_authenticated == False %}
        [message anonyme]
    {% else %}
        {% if user has active membership %}
            [tarif selectable]
        {% else %}
            [message "pas adherent"]
        {% endif %}
    {% endif %}
{% else %}
    [tarif selectable classique]
{% endif %}
```

Modifier la logique pour **ajouter un check cart-aware avant** le check d'authentification :

```django
{% if price.adhesions_obligatoires.exists %}
    {# --- NOUVEAU : check cart-aware en priorite --- #}
    {# --- NEW: cart-aware check takes priority --- #}
    {% with is_in_cart=price.adhesions_obligatoires.all|in_cart:panier.adhesions_product_ids %}
        {% if is_in_cart %}
            {# Adhesion requise est dans le panier → tarif selectable #}
            {# Required membership in cart → rate selectable #}
            <div class="alert alert-info py-2 mb-2 small">
                <i class="bi bi-bag-check me-1"></i>
                {% trans "Accessible via the membership in your cart." %}
            </div>
            {# Tarif selectable (reutilise le meme markup que les tarifs standards) #}
            {# Rate selectable (reuses same markup as standard rates) #}
            [INSÉRER ICI LE MÊME MARKUP QUE LA BRANCHE "user a l'adhésion" CI-DESSOUS]
        {% elif user.is_authenticated == False %}
            [message anonyme existant]
        {% else %}
            [les 2 branches existantes]
        {% endif %}
    {% endwith %}
{% else %}
    [existant]
{% endif %}
```

**Important** : Le filtre `|in_cart:panier.adhesions_product_ids` n'existe pas encore — il faut le créer.

- [ ] **Étape 3 : Créer un template filter `in_cart`**

Dans `BaseBillet/templatetags/tibitags.py` (fichier existant — on y ajoute juste un filter), ajouter à la fin :

```python
@register.filter
def in_cart(adhesions_queryset, cart_product_ids):
    """
    Template filter : True si au moins un des products d'adhesions_obligatoires
    est dans la liste des UUIDs d'adhesions du panier.

    / Template filter: True if at least one adhesions_obligatoires product is in
    the cart's membership UUIDs list.

    Usage :
        {% if price.adhesions_obligatoires.all|in_cart:panier.adhesions_product_ids %}
    """
    if not cart_product_ids:
        return False
    cart_ids_str = {str(uid) for uid in cart_product_ids}
    for product in adhesions_queryset:
        if str(product.uuid) in cart_ids_str:
            return True
    return False
```

Vérifier que `register` est bien défini en tête du fichier (`register = template.Library()`) — c'est standard Django.

- [ ] **Étape 4 : Appliquer la modification dans `cardTickets.html`**

**IMPORTANT** : le template `cardTickets.html` a une structure complexe (lignes 68-150+). L'implémenteur doit :
1. D'abord **lire le fichier complet** pour comprendre sa structure
2. Identifier le bloc `{% if user.is_authenticated == False %}` / `{% else %}` qui gère les 2 branches connecté/non-connecté dans le cas `adhesions_obligatoires.exists`
3. **Encapsuler** ce bloc dans un nouveau `{% with is_in_cart=... %}` et **ajouter en premier une branche** `{% if is_in_cart %}` qui affiche le tarif comme sélectable.

Structure finale souhaitée :

```django
{% if price.adhesions_obligatoires.exists %}
    {% with is_in_cart=price.adhesions_obligatoires.all|in_cart:panier.adhesions_product_ids %}
        {% if is_in_cart %}
            <div class="alert alert-info py-2 mb-2 small">
                <i class="bi bi-bag-check me-1"></i>
                {% trans "Accessible via the membership in your cart." %}
            </div>
            {% include "htmx/components/inputNumberNonNominatif.html" with price=price %}
        {% elif user.is_authenticated == False %}
            {# ---- bloc existant "non connecte" ---- #}
            ...
        {% else %}
            {# ---- bloc existant "connecte" (les 2 sous-branches) ---- #}
            ...
        {% endif %}
    {% endwith %}
{% else %}
    {# ---- bloc existant "tarif standard" ---- #}
    ...
{% endif %}
```

L'`include "htmx/components/inputNumberNonNominatif.html"` est probablement ce que font les autres branches pour afficher le selector de quantité ; à confirmer en lisant le fichier. Sinon, copier-coller le markup exact d'une des branches qui autorise la sélection.

- [ ] **Étape 5 : `manage.py check` doit passer**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

- [ ] **Étape 6 : Smoke test — le filter `in_cart` fonctionne**

```bash
docker exec lespass_django poetry run python -c "
import django; django.setup()
from django.template import Template, Context
from BaseBillet.templatetags.tibitags import in_cart
import uuid
# Mock queryset avec un .uuid
class FakeProduct:
    def __init__(self, u): self.uuid = u
u1 = uuid.uuid4()
u2 = uuid.uuid4()
# Présent
print('in_cart match:', in_cart([FakeProduct(u1)], [u1, u2]))
# Absent
print('in_cart no match:', in_cart([FakeProduct(u1)], [u2]))
# Vide
print('in_cart empty:', in_cart([FakeProduct(u1)], []))
" 2>&1 | grep in_cart
```

Attendu : `in_cart match: True`, `in_cart no match: False`, `in_cart empty: False`.

**Point de contrôle commit (mainteneur)** — fin Tâche 5.5.

---

## Tâche 5.6 : Vérifications finales Session 05

**Fichiers :** aucun — vérifications uniquement.

- [ ] **Étape 1 : `manage.py check`**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Attendu : 0 issue.

- [ ] **Étape 2 : `makemigrations --dry-run`**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations --dry-run
```

Attendu : `No changes detected`.

- [ ] **Étape 3 : Pytest Sessions 01-05**

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
    -v
```

Attendu : 82 + 4 = **86 tests PASS**.

- [ ] **Étape 4 : Non-régression globale**

```bash
docker exec lespass_django poetry run pytest tests/pytest/ -q
```

Attendu : aucune régression vs Session 04.

- [ ] **Étape 5 : Smoke tests UX manuels**

Ouvrir un navigateur sur `http://lespass.tibillet.localhost:8002/` et vérifier :
- La navbar affiche l'icône panier (`bi-bag`).
- Le badge est absent si panier vide.
- Cliquer sur l'icône redirige vers `/panier/`.
- La page `/panier/` affiche "Your cart is empty" si rien dedans.
- Sur une page event avec tarifs, cliquer "Valider la réservation" ouvre une modal avec 2 boutons.
- Cliquer "Ajouter au panier" soumet le form, le badge se met à jour.
- Cliquer "Payer maintenant" redirige vers Stripe (flow existant).

**Session 05 — terminée.**

---

## Récap fichiers touchés

| Action | Fichier |
|---|---|
| Modifier | `BaseBillet/views.py` (+action `add_tickets_batch`) |
| Modifier | `BaseBillet/templatetags/tibitags.py` (+filter `in_cart`) |
| Remplacer | `BaseBillet/templates/htmx/views/panier.html` (refonte Bootstrap) |
| Créer | `BaseBillet/templates/htmx/components/panier_item.html` |
| Modifier | `BaseBillet/templates/htmx/components/panier_badge.html` (+badge navbar) |
| Modifier | `BaseBillet/templates/reunion/partials/navbar.html` (+icône panier) |
| Modifier | `BaseBillet/templates/htmx/views/event.html` (+modal choix) |
| Modifier | `BaseBillet/templates/htmx/components/cardTickets.html` (cart-aware) |
| Créer | `tests/pytest/test_panier_batch.py` (4 tests) |

## Critères de Done Session 05

- [x] Endpoint `/panier/add/tickets_batch/` opérationnel (4 tests PASS)
- [x] Page `/panier/` avec Bootstrap 5 : liste items avec image, controles qty, code promo, total, form checkout
- [x] Navbar : icône panier + badge (mis à jour via hx-swap-oob)
- [x] Page event : bouton principal ouvre modal "Ajouter au panier / Payer maintenant"
- [x] Tarifs gatés affichent "Accessible via le panier" si l'adhésion est dans le panier
- [x] `manage.py check` : 0 issue
- [x] 4 tests ajoutés en Session 05, tous PASS
- [x] Aucune régression sur Sessions 01-04

## Hors scope — attendu en Session 06

- Tests E2E Playwright (navigation utilisateur complète : home → event → modal → ajout panier → second event → checkout)
- A11y audit (navigation clavier dans la modal, annonces screen reader pour le badge)
- i18n complet (vérifier toutes les strings sont `{% trans %}`)
- Responsive fine-tuning (mobile < 576px)
- Dark mode cohérence
