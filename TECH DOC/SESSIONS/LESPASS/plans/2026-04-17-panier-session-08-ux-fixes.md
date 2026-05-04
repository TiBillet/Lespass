# Panier multi-events — Plan Session 08 : UX fixes + cohérence

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Corriger les 4 problèmes UX découverts lors de l'inspection Chrome (Session 07 a introduit IsAuthenticated trop agressif, 403 silencieux, i18n non compilé, hiérarchie boutons floue) et améliorer la cohérence UX anonyme/authentifié.

**Architecture:** Pur ajustement UX — permissions granulaires par action, feedback frontend sur 403, template conditionnel, polish empty state. Zéro changement de modèle, zéro migration.

**Tech Stack:** Django 5.x, DRF, HTMX, Bootstrap 5.

**Inspection source :** test Chrome MCP sur tenant lespass (2026-04-17) — 8 observations notées.

**Dépend de :** Sessions 01-07 DONE (89 tests pytest, chantier panier v2 clos).

**Scope :**
- ✅ A1 — Permissions granulaires `PanierMVT` : `list`/`badge` → `AllowAny` (template gère l'état auth), écritures → `IsAuthenticated`
- ✅ A2 — Intercept HTMX 403 global → toast + offcanvas login (catch universel au niveau navbar/base)
- ✅ A3 — Compiler `.po` → `Add to cart` en "Ajouter au panier"
- ✅ A4 — `booking_form.html` : bouton "Add to cart" conditionnel `{% if user.is_authenticated %}`, sinon bouton "Log in to add to cart" qui ouvre l'offcanvas
- ✅ B1 — Hiérarchie `Pay now` vs `Add to cart` dans `booking_form.html` selon état du panier
- ✅ B2 — Badge panier anonyme : style grisé + cadenas si anonyme + count > 0
- ✅ B3 — Empty state `/panier/` : SVG inline + copy chaleureux + 2 CTA (events + adhésions)

**Hors scope :**
- ❌ Polish C (bounce badge, toast enrichi) — Session 09 optionnelle
- ❌ Bugs D (None config.organisation, None max_per_user, 2 prix dupliqués) — tickets séparés, non-panier

**Règle projet :** L'agent ne touche jamais à git.

---

## Architecture des fichiers

| Fichier | Action | Tâche |
|---|---|---|
| `BaseBillet/views.py` | Modifier | A1 permissions granulaires `PanierMVT.get_permissions` |
| `BaseBillet/templates/reunion/base.html` | Modifier | A2 handler HTMX 403 global (script inline) |
| `locale/fr/LC_MESSAGES/django.mo` | Régénérer | A3 `compilemessages` |
| `BaseBillet/templates/reunion/views/event/partial/booking_form.html` | Modifier | A4 bouton conditionnel + B1 hiérarchie |
| `BaseBillet/templates/htmx/components/panier_badge.html` | Modifier | B2 badge anonyme différencié |
| `BaseBillet/templates/htmx/views/panier.html` | Modifier | B3 empty state amélioré |
| `tests/pytest/test_panier_mvt.py` | Modifier | Tests permissions granulaires (list AllowAny, checkout IsAuthenticated) |

**Pas de nouveau fichier.** Tout s'inscrit dans l'existant.

---

## Tâche 8.1 : A1 permissions granulaires + A3 compilemessages

**Fichiers :**
- Modifier : `BaseBillet/views.py` (méthode `PanierMVT.get_permissions`)
- Modifier : `tests/pytest/test_panier_mvt.py` (adapter tests `list`/`badge` anonymes)
- Régénérer : fichiers `.mo` de traduction

**Contexte :** Session 07 a mis `IsAuthenticated` sur TOUT `PanierMVT`. Conséquence : GET `/panier/` en anonyme retourne la page DRF browsable API JSON 403 au lieu de notre template panier (qui sait gérer l'état auth). Il faut granulariser.

- [ ] **Étape 1 : Adapter `get_permissions()` dans `PanierMVT`**

Dans `BaseBillet/views.py`, classe `PanierMVT`. Remplacer :

```python
    def get_permissions(self):
        # Panier = feature auth-only (simplifie l'UX, derive buyer de request.user).
        # Le flow direct (event/membership sans panier) reste anonyme, ailleurs.
        # / Cart = auth-only feature (simpler UX, buyer derived from request.user).
        # Direct flow (event/membership without cart) stays anonymous elsewhere.
        return [permissions.IsAuthenticated()]
```

Par :

```python
    def get_permissions(self):
        # Lectures du panier (list + badge) : AllowAny — session-scoped, aucun data leak.
        # Le template panier gère l'état auth (anonyme → message "log in to checkout").
        # Écritures (add, remove, checkout, promo, clear) : IsAuthenticated — force le login.
        # / Reads: AllowAny (session-scoped, no data leak). Template handles auth state.
        # Writes: IsAuthenticated (force login via HTMX 403 catch + offcanvas).
        if self.action in ['list', 'badge']:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]
```

- [ ] **Étape 2 : Adapter le test anonyme dans `test_panier_mvt.py`**

Dans `tests/pytest/test_panier_mvt.py`, adapter le test `test_GET_panier_list_renvoie_page` pour qu'il passe en anonyme :

```python
@pytest.mark.django_db
def test_GET_panier_list_renvoie_page(tenant_context_lespass):
    """
    GET /panier/ est accessible en anonyme (template gère l'état auth).
    / GET /panier/ is accessible when anonymous (template handles auth state).
    """
    from django.test import Client
    anon_client = Client(HTTP_HOST='lespass.tibillet.localhost')
    response = anon_client.get('/panier/')
    assert response.status_code == 200
    # Pas le template DRF browsable API (qui aurait du JSON dans le title)
    # / Not the DRF browsable API template (which has JSON in title)
    assert b"Django REST framework" not in response.content or b"panier" in response.content.lower()
```

Et `test_GET_panier_badge_renvoie_partial` pareil (accessible anonyme) :

```python
@pytest.mark.django_db
def test_GET_panier_badge_renvoie_partial(tenant_context_lespass):
    """GET /panier/badge/ accessible anonyme."""
    from django.test import Client
    anon_client = Client(HTTP_HOST='lespass.tibillet.localhost')
    response = anon_client.get('/panier/badge/')
    assert response.status_code == 200
    assert b"panier-badge" in response.content
```

Ajouter un test qui vérifie que les écritures sont toujours `IsAuthenticated` :

```python
@pytest.mark.django_db
def test_POST_add_ticket_anonyme_retourne_403(tenant_context_lespass, event_avec_tarif):
    """Anonyme + POST add_tickets_batch → 403.
    / Anonymous + POST add_tickets_batch → 403."""
    from django.test import Client
    event, price = event_avec_tarif
    anon_client = Client(HTTP_HOST='lespass.tibillet.localhost')
    response = anon_client.post('/panier/add/tickets_batch/', {
        'event': str(event.uuid),
        str(price.uuid): '1',
    })
    assert response.status_code == 403


@pytest.mark.django_db
def test_POST_checkout_anonyme_retourne_403(tenant_context_lespass):
    """Anonyme + POST checkout → 403 (test existant, confirm reste valide)."""
    from django.test import Client
    anon_client = Client(HTTP_HOST='lespass.tibillet.localhost')
    response = anon_client.post('/panier/checkout/')
    assert response.status_code == 403
```

- [ ] **Étape 3 : `manage.py check` doit passer**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

- [ ] **Étape 4 : Compiler les messages (A3)**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py compilemessages
```

Attendu : pas d'erreur. Les `.mo` de `locale/fr/` et `locale/en/` sont régénérés.

Si la commande demande `makemessages` d'abord :

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py makemessages -l fr --no-location
docker exec lespass_django poetry run python /DjangoFiles/manage.py makemessages -l en --no-location
docker exec lespass_django poetry run python /DjangoFiles/manage.py compilemessages
```

Note : les traductions effectives ("Add to cart" → "Ajouter au panier") sont dans les `.po`. Si elles manquent, les ajouter manuellement :

```bash
grep -A1 "Add to cart" /DjangoFiles/locale/fr/LC_MESSAGES/django.po | head -10
```

Si `msgstr ""` vide → éditer le fichier `.po` pour ajouter `msgstr "Ajouter au panier"`, puis recompiler.

- [ ] **Étape 5 : Smoke test — le template français s'affiche**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py tenant_command shell --schema=lespass <<'PY'
from django.test import Client
from django.utils import translation
translation.activate('fr')
c = Client(HTTP_HOST='lespass.tibillet.localhost')
r = c.get('/panier/')
print('status:', r.status_code)
PY
```

Attendu : `status: 200`.

- [ ] **Étape 6 : Lancer les tests panier**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_panier_mvt.py -v
```

Attendu : tous les tests passent (12+ selon adaptations).

**Point de contrôle commit (mainteneur)** — fin Tâche 8.1.

---

## Tâche 8.2 : A4 bouton conditionnel + A2 catch HTMX 403 global

**Fichiers :**
- Modifier : `BaseBillet/templates/reunion/views/event/partial/booking_form.html` (bouton conditionnel)
- Modifier : `BaseBillet/templates/reunion/base.html` (script HTMX 403 catch)

**Contexte :** Double ceinture. Côté booking_form, on n'affiche pas le bouton "Add to cart" pour un anonyme (on le remplace par un bouton qui ouvre l'offcanvas login). Côté global, on intercepte les 403 HTMX qui passeraient malgré tout (ex: session expirée en cours de navigation) pour afficher un toast + ouvrir l'offcanvas login.

- [ ] **Étape 1 : Bouton conditionnel dans `booking_form.html`**

Dans `BaseBillet/templates/reunion/views/event/partial/booking_form.html`, trouver le bouton "Add to cart" ajouté Session 05 :

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

Le remplacer par :

```html
        {% if user.is_authenticated %}
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
        {% else %}
            <button type="button"
                    class="btn btn-outline-secondary w-100 mb-3"
                    data-bs-toggle="offcanvas"
                    data-bs-target="#loginPanel"
                    data-testid="booking-add-to-cart-login"
                    aria-label="{% trans 'Log in to add these tickets to your cart' %}">
                <i class="bi bi-lock me-2" aria-hidden="true"></i>
                {% trans "Log in to add to cart" %}
            </button>
        {% endif %}
```

- [ ] **Étape 2 : Ajouter le catch HTMX 403 global dans `base.html`**

Dans `BaseBillet/templates/reunion/base.html`, repérer la fin du fichier (juste avant `</body>`). Ajouter ce script :

```html
<script>
// HTMX 403 global catch : redirect vers login pour les actions panier qui nécessitent auth.
// / HTMX global 403 catch: redirect to login for panier actions requiring auth.
document.body.addEventListener('htmx:responseError', function(evt) {
    const status = evt.detail.xhr.status;
    const path = evt.detail.pathInfo.requestPath || '';
    if (status === 403 && path.startsWith('/panier/')) {
        // Ouvrir l'offcanvas login s'il existe
        // / Open login offcanvas if present
        const loginPanel = document.getElementById('loginPanel');
        if (loginPanel && typeof bootstrap !== 'undefined') {
            bootstrap.Offcanvas.getOrCreateInstance(loginPanel).show();
        }
        // Toast informatif
        // / Informational toast
        const container = document.createElement('div');
        container.className = 'toast-container position-fixed top-0 end-0 p-3';
        container.style.zIndex = '1100';
        container.innerHTML = `
            <div class="toast show" role="alert" aria-live="assertive">
                <div class="toast-header bg-primary text-white border-0">
                    <i class="bi bi-info-circle me-2" aria-hidden="true"></i>
                    <strong class="me-auto">{% trans "Login required" %}</strong>
                    <button type="button" class="btn-close btn-close-white" data-bs-dismiss="toast"></button>
                </div>
                <div class="toast-body small">
                    {% trans "Please log in to use your cart." %}
                </div>
            </div>`;
        document.body.appendChild(container);
        setTimeout(() => container.remove(), 5000);
    }
});
</script>
```

**Note** : si `base.html` est utilisé aussi par le skin faire-festival (via `extends` ou `block scripts`), vérifier que le script est chargé aussi là-bas. Alternativement, le mettre dans `reunion/partials/navbar.html` qui contient déjà l'offcanvas login.

- [ ] **Étape 3 : `manage.py check` doit passer**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

- [ ] **Étape 4 : Smoke test — le template conditionnel fonctionne**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py tenant_command shell --schema=lespass <<'PY'
from django.template.loader import render_to_string
from django.contrib.auth.models import AnonymousUser
from BaseBillet.models import Event

event = Event.objects.filter(slug__isnull=False).first()
if not event:
    print("No event - skip")
else:
    # Anonyme : bouton "Log in to add to cart"
    html_anon = render_to_string('reunion/views/event/partial/booking_form.html', {
        'event': event, 'user': AnonymousUser(),
    })
    print('anon has login cta:', 'booking-add-to-cart-login' in html_anon)
    print('anon has batch button:', 'booking-add-to-cart"' in html_anon)

    # Auth (fake) : bouton "Add to cart"
    from AuthBillet.models import TibilletUser
    user = TibilletUser.objects.first()
    html_auth = render_to_string('reunion/views/event/partial/booking_form.html', {
        'event': event, 'user': user,
    })
    print('auth has batch button:', 'booking-add-to-cart"' in html_auth)
    print('auth has login cta:', 'booking-add-to-cart-login' in html_auth)
PY
```

Attendu :
```
anon has login cta: True
anon has batch button: False
auth has batch button: True
auth has login cta: False
```

- [ ] **Étape 5 : Non-régression pytest**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_panier_batch.py tests/pytest/test_panier_mvt.py -q
```

Attendu : tous les tests passent.

**Point de contrôle commit (mainteneur)** — fin Tâche 8.2.

---

## Tâche 8.3 : B1 hiérarchie boutons + B2 badge anonyme

**Fichiers :**
- Modifier : `BaseBillet/templates/reunion/views/event/partial/booking_form.html` (hiérarchie)
- Modifier : `BaseBillet/templates/htmx/components/panier_badge.html` (badge anonyme)

**Contexte :**
- **B1** : actuellement "Pay now" (primary) et "Add to cart" (outline) sont visuellement proches. Si le panier contient déjà un item, inverser : "Add to cart" devient primary pour inciter à compléter le parcours panier.
- **B2** : un anonyme voit `badge=1` mais ne peut rien en faire (session antérieure). Afficher un style grisé + cadenas pour signaler qu'il faut se connecter.

- [ ] **Étape 1 : Hiérarchie boutons dans `booking_form.html`**

Dans `BaseBillet/templates/reunion/views/event/partial/booking_form.html`, le bloc des 2 boutons (existing submit + Add to cart) contient actuellement :

```html
<button type="submit" class="btn btn-primary w-100 mb-3" data-testid="booking-submit">{% trans 'Send booking request' %}</button>

{% if user.is_authenticated %}
    <button type="button" class="btn btn-outline-primary w-100 mb-3" ...>
        ...
        {% trans "Add to cart" %}
    </button>
{% else %}
    <button type="button" class="btn btn-outline-secondary w-100 mb-3" ...>
        ...
        {% trans "Log in to add to cart" %}
    </button>
{% endif %}
```

Réorganiser selon l'état du panier (`panier.count`) :

```html
{% if panier.count > 0 and user.is_authenticated %}
    {# Panier non vide → "Add to cart" en primary (complète le parcours), "Pay now" secondaire #}
    <button type="button"
            class="btn btn-primary w-100 mb-2"
            hx-post="/panier/add/tickets_batch/"
            hx-include="closest form"
            hx-swap="none"
            data-testid="booking-add-to-cart"
            aria-label="{% trans 'Add these tickets to your cart' %}">
        <i class="bi bi-bag-plus me-2" aria-hidden="true"></i>
        {% blocktrans count n=panier.count %}Add to cart ({{ n }} already in){% plural %}Add to cart ({{ n }} already in){% endblocktrans %}
    </button>
    <button type="submit" class="btn btn-outline-secondary w-100" data-testid="booking-submit">
        <i class="bi bi-credit-card me-1" aria-hidden="true"></i>
        <small>{% trans "or pay this event separately now" %}</small>
    </button>
{% elif user.is_authenticated %}
    {# Panier vide + authentifié : "Pay now" primary, "Add to cart" secondaire #}
    <button type="submit" class="btn btn-primary w-100 mb-2" data-testid="booking-submit">
        <i class="bi bi-credit-card me-2" aria-hidden="true"></i>
        {% trans "Pay now" %}
    </button>
    <button type="button"
            class="btn btn-link text-muted w-100"
            hx-post="/panier/add/tickets_batch/"
            hx-include="closest form"
            hx-swap="none"
            data-testid="booking-add-to-cart"
            aria-label="{% trans 'Add these tickets to your cart' %}">
        <i class="bi bi-bag-plus me-1" aria-hidden="true"></i>
        <small>{% trans "or add to cart to combine with other events" %}</small>
    </button>
{% else %}
    {# Anonyme : "Send booking request" (direct flow) primary, "Log in to add to cart" secondaire #}
    <button type="submit" class="btn btn-primary w-100 mb-2" data-testid="booking-submit">
        {% trans 'Send booking request' %}
    </button>
    <button type="button"
            class="btn btn-outline-secondary w-100"
            data-bs-toggle="offcanvas"
            data-bs-target="#loginPanel"
            data-testid="booking-add-to-cart-login"
            aria-label="{% trans 'Log in to add these tickets to your cart' %}">
        <i class="bi bi-lock me-2" aria-hidden="true"></i>
        <small>{% trans "Log in to add to cart" %}</small>
    </button>
{% endif %}

<a href="." class="btn btn-link text-muted d-block mt-2" data-testid="booking-cancel">
    {% trans 'Cancel' %}
</a>
```

**Note** : `panier.count` est disponible via le context processor. Verify that booking_form template actually has access to it — normally yes via RequestContext.

- [ ] **Étape 2 : Badge anonyme différencié dans `panier_badge.html`**

Remplacer le contenu de `BaseBillet/templates/htmx/components/panier_badge.html` :

```html
{% load i18n %}
{# Badges compteur du panier — rendu partout (page panier + navbar). #}
{# Cart counter badges — rendered everywhere (cart page + navbar). #}

{# Badge pour la page panier (in-page) #}
<span id="panier-badge" hx-swap-oob="true">
    {% if panier.count > 0 %}
        {% if user.is_authenticated %}
            <span class="badge bg-primary">{{ panier.count }}</span>
        {% else %}
            {# Anonyme avec items en session : badge grisé + cadenas #}
            {# Anonymous with session items: greyed badge + lock #}
            <span class="badge bg-secondary opacity-75"
                  title="{% trans 'Log in to use your cart' %}">
                <i class="bi bi-lock-fill" style="font-size: 0.7em;" aria-hidden="true"></i>
                {{ panier.count }}
            </span>
        {% endif %}
    {% endif %}
</span>

{# Badge pour la navbar (header) #}
<span id="panier-badge-nav" hx-swap-oob="true">
    {% if panier.count > 0 %}
        {% if user.is_authenticated %}
            <span class="position-absolute top-0 start-100 translate-middle badge rounded-pill bg-primary">
                {{ panier.count }}
                <span class="visually-hidden">{% trans "items" %}</span>
            </span>
        {% else %}
            <span class="position-absolute top-0 start-100 translate-middle badge rounded-pill bg-secondary opacity-75"
                  title="{% trans 'Log in to use your cart' %}">
                <i class="bi bi-lock-fill" style="font-size: 0.6em;" aria-hidden="true"></i>
                {{ panier.count }}
                <span class="visually-hidden">{% trans "items (login required)" %}</span>
            </span>
        {% endif %}
    {% endif %}
</span>
```

- [ ] **Étape 3 : `manage.py check` doit passer**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

- [ ] **Étape 4 : Smoke test — badge anonyme affiche le cadenas**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py tenant_command shell --schema=lespass <<'PY'
from django.template.loader import render_to_string
from django.contrib.auth.models import AnonymousUser
from AuthBillet.models import TibilletUser

# Anonyme avec panier count > 0
html_anon = render_to_string('htmx/components/panier_badge.html', {
    'panier': {'count': 2},
    'user': AnonymousUser(),
})
print('anon has lock icon:', 'bi-lock-fill' in html_anon)
print('anon has secondary bg:', 'bg-secondary' in html_anon)

# Auth avec panier count > 0
user = TibilletUser.objects.first()
html_auth = render_to_string('htmx/components/panier_badge.html', {
    'panier': {'count': 2},
    'user': user,
})
print('auth has primary bg:', 'bg-primary' in html_auth)
print('auth has lock icon:', 'bi-lock-fill' in html_auth)
PY
```

Attendu :
```
anon has lock icon: True
anon has secondary bg: True
auth has primary bg: True
auth has lock icon: False
```

- [ ] **Étape 5 : Non-régression pytest**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_panier_context_processor.py tests/pytest/test_panier_mvt.py -q
```

**Point de contrôle commit (mainteneur)** — fin Tâche 8.3.

---

## Tâche 8.4 : B3 empty state panier + vérifs finales Session 08

**Fichiers :**
- Modifier : `BaseBillet/templates/htmx/views/panier.html` (empty state amélioré)

**Contexte :** L'empty state actuel est correct mais fade. Un SVG inline simple + copy chaleureux + 2 CTA (events + adhésions) rend la page plus accueillante.

- [ ] **Étape 1 : Améliorer l'empty state de `/panier/`**

Dans `BaseBillet/templates/htmx/views/panier.html`, repérer le bloc `{% if panier.is_empty %}` :

```html
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
    ...
```

Le remplacer par :

```html
{% if panier.is_empty %}
    <div class="card shadow-sm border-0">
        <div class="card-body text-center py-5 px-4">
            {# SVG panier vide — sobre, cohérent avec l'icône navbar bi-bag #}
            {# Empty cart SVG — sober, matches navbar bi-bag icon #}
            <svg width="120" height="120" viewBox="0 0 120 120"
                 class="mb-4 text-muted opacity-50" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M25 45 L35 95 L85 95 L95 45 Z" stroke-linejoin="round"/>
                <path d="M40 45 L40 35 Q40 20 60 20 Q80 20 80 35 L80 45" stroke-linecap="round"/>
                {# Quelques points qui évoquent des items qui flottent #}
                <circle cx="48" cy="65" r="2" fill="currentColor" opacity="0.4" stroke="none"/>
                <circle cx="72" cy="75" r="2" fill="currentColor" opacity="0.4" stroke="none"/>
                <circle cx="60" cy="60" r="1.5" fill="currentColor" opacity="0.3" stroke="none"/>
            </svg>

            <h2 class="h4 mb-2">{% trans "Your cart is waiting" %}</h2>
            <p class="text-muted mb-4">
                {% trans "Browse events or memberships to fill it up." %}
            </p>

            <div class="d-flex gap-2 justify-content-center flex-wrap">
                <a href="/event/" class="btn btn-primary"
                   hx-get="/event/" hx-target="body" hx-push-url="true">
                    <i class="bi bi-calendar-event me-2" aria-hidden="true"></i>
                    {% trans "Browse events" %}
                </a>
                <a href="/memberships/" class="btn btn-outline-primary"
                   hx-get="/memberships/" hx-target="body" hx-push-url="true">
                    <i class="bi bi-person-badge me-2" aria-hidden="true"></i>
                    {% trans "Memberships" %}
                </a>
            </div>
        </div>
    </div>
{% else %}
    ...  {# le reste inchangé #}
```

- [ ] **Étape 2 : `manage.py check` doit passer**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

- [ ] **Étape 3 : Smoke test — empty state rend**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py tenant_command shell --schema=lespass <<'PY'
from django.test import Client
c = Client(HTTP_HOST='lespass.tibillet.localhost')
r = c.get('/panier/')
print('status:', r.status_code)
print('has empty svg:', b'Your cart is waiting' in r.content)
print('has 2 CTA:', b'Browse events' in r.content and b'Memberships' in r.content)
PY
```

Attendu : tous True.

- [ ] **Étape 4 : Vérifications finales globales**

```bash
# Django check
docker exec lespass_django poetry run python /DjangoFiles/manage.py check

# Makemigrations dry-run
docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations --dry-run

# Pytest Sessions 01-07 + tests adaptés Session 08
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
    tests/pytest/test_stripe_checkout_url.py \
    -q
```

Attendu :
- `manage.py check` : 0 issue
- `makemigrations --dry-run` : No changes detected
- pytest : ~89+ tests PASS (avec les nouveaux tests auth/permissions ajoutés Tâche 8.1)

- [ ] **Étape 5 : Ruff**

```bash
docker exec lespass_django poetry run ruff check /DjangoFiles/BaseBillet/views.py
```

Attendu : pas d'erreurs nouvelles introduites.

**Session 08 — terminée.**

---

## Récap fichiers touchés

| Action | Fichier | Tâche |
|---|---|---|
| Modifier | `BaseBillet/views.py` | 8.1 permissions granulaires |
| Régénérer | `locale/{fr,en}/LC_MESSAGES/django.mo` | 8.1 compilemessages |
| Modifier | `tests/pytest/test_panier_mvt.py` | 8.1 adapter tests anonymes + ajouter tests écritures 403 |
| Modifier | `BaseBillet/templates/reunion/base.html` | 8.2 catch HTMX 403 global |
| Modifier | `BaseBillet/templates/reunion/views/event/partial/booking_form.html` | 8.2 bouton conditionnel + 8.3 hiérarchie |
| Modifier | `BaseBillet/templates/htmx/components/panier_badge.html` | 8.3 badge anonyme différencié |
| Modifier | `BaseBillet/templates/htmx/views/panier.html` | 8.4 empty state amélioré |

## Critères de Done Session 08

- [x] A1 : `/panier/` et `/panier/badge/` accessibles anonyme (200), écritures restent 403
- [x] A2 : clic anonyme sur action panier → toast + offcanvas login
- [x] A3 : `.mo` compilés, "Add to cart" → "Ajouter au panier" en FR
- [x] A4 : bouton `Add to cart` absent si anonyme, remplacé par "Log in to add to cart"
- [x] B1 : hiérarchie "Pay now" vs "Add to cart" selon `panier.count` et `user.is_authenticated`
- [x] B2 : badge navbar grisé + cadenas si anonyme + count > 0
- [x] B3 : empty state `/panier/` avec SVG + 2 CTA (events + memberships)
- [x] `manage.py check` : 0 issue
- [x] Tests pytest : +3 tests nouveaux, tous existants adaptés PASS
- [x] Non-régression : zéro test cassé

## Hors scope — ailleurs

- Bugs config existants : `None` organisation, `None` max_per_user, 2 prix FREERES dupliqués
- Polish optionnel : bounce badge, toast enrichi, animation unlock
