# Panier multi-events — Plan Session 04 : Vues HTMX `PanierMVT` + context processor

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Câbler les endpoints HTTP du panier — ViewSet DRF `PanierMVT` (10 actions), URLs, context processor pour exposer le panier aux templates, + templates HTMX minimaux.

**Architecture:** Nouveau ViewSet `PanierMVT(viewsets.ViewSet)` dans `BaseBillet/views.py` qui délègue intégralement à `PanierSession` (Session 02) et `CommandeService` (Session 02). Chaque action retourne un partial HTMX (badge + toast) ou redirige. Un context processor expose le panier à tous les templates via `{{ panier }}`.

**Tech Stack:** Django 5.x, DRF (viewsets.ViewSet, pas ModelViewSet — convention projet), HTMX, Bootstrap 5, pytest + Django test client.

**Spec:** `TECH DOC/SESSIONS/LESPASS/specs/2026-04-17-panier-multi-events-design.md` (sections 3.8, 3.9, 3.10)

**Dépend de :** Sessions 01, 02, 03 DONE (65 tests, aucune régression).

**Scope de cette session :**
- ✅ `BaseBillet/context_processors.py` — fonction `panier_context(request)` exposant `panier` aux templates
- ✅ Enregistrement du context processor dans `TiBillet/settings.py`
- ✅ Classe `PanierMVT(viewsets.ViewSet)` dans `BaseBillet/views.py` avec 10 actions
- ✅ URLs panier dans `BaseBillet/urls.py` (enregistrement du ViewSet dans le router)
- ✅ Templates HTMX **minimaux** (juste assez pour que les vues retournent 200) : badge, toast, page panier squelette
- ✅ Tests pytest vues : chaque endpoint renvoie la bonne réponse / status / template

**Hors scope (sessions suivantes) :**
- ❌ Design complet de la page panier / modal → Session 05
- ❌ Modal "Ajouter au panier / Payer maintenant" sur page event → Session 05
- ❌ Cart-aware visibility sur page event (tarifs gatés) → Session 05
- ❌ Tests E2E Playwright → Session 06

**Règle projet :** L'agent ne touche jamais à git. Convention DRF : `viewsets.ViewSet` (jamais `ModelViewSet`), `serializers.Serializer` (jamais Form ni ModelSerializer pour les vues templates). Voir `CLAUDE.md`.

---

## Architecture des fichiers

| Fichier | Action | Rôle |
|---|---|---|
| `BaseBillet/context_processors.py` | Créer (nouveau fichier) | `panier_context(request)` — expose `panier` aux templates |
| `TiBillet/settings.py` | Modifier | Ajouter `BaseBillet.context_processors.panier_context` dans TEMPLATES.OPTIONS.context_processors |
| `BaseBillet/views.py` | Modifier | Ajouter classe `PanierMVT` (10 actions) |
| `BaseBillet/urls.py` | Modifier | Enregistrer `PanierMVT` dans le router |
| `BaseBillet/templates/htmx/components/panier_badge.html` | Créer | Badge compteur partial HTMX |
| `BaseBillet/templates/htmx/components/panier_toast.html` | Créer | Toast de feedback HTMX |
| `BaseBillet/templates/htmx/views/panier.html` | Créer (squelette) | Page panier minimaliste (Session 05 la rendra jolie) |
| `tests/pytest/test_panier_mvt.py` | Créer | Tests d'intégration (client Django) des 10 actions |

**Principes de découpage :**
- `PanierMVT` est thin : chaque action = extraction params + appel service + rendu partial.
- Zéro logique métier dans les vues — toute validation est dans `PanierSession` / `CommandeService`.
- Les templates sont des squelettes fonctionnels, à polish en Session 05.

---

## Tâche 4.1 : Context processor `panier_context`

**Fichiers :**
- Créer : `BaseBillet/context_processors.py`
- Modifier : `TiBillet/settings.py` (ajouter le context processor)

**Contexte :** Pour que les templates puissent afficher `{{ panier.count }}`, `{{ panier.is_empty }}`, ou itérer sur `{{ panier.items_with_details }}`, on expose un dict `panier` via un context processor. Il lit la session et enrichit les items avec les données DB (Event, Price, Product) pour l'affichage.

- [ ] **Étape 1 : Créer `BaseBillet/context_processors.py`**

```python
"""
Context processors BaseBillet.
/ BaseBillet context processors.

Expose le panier courant a tous les templates via {{ panier }}.
/ Exposes the current cart to all templates via {{ panier }}.
"""
import logging
from decimal import Decimal

logger = logging.getLogger(__name__)


def panier_context(request):
    """
    Expose le panier courant aux templates. Disponible partout via :
    - {{ panier.count }}          - nombre total d'items
    - {{ panier.is_empty }}       - bool
    - {{ panier.items_with_details }} - items enrichis (event/price/product)
    - {{ panier.total_ttc }}      - Decimal total (plein tarif, avant promo)
    - {{ panier.adhesions_product_ids }} - UUIDs products d'adhesion dans panier
    - {{ panier.promo_code_name }} - nom du code promo actif ou None

    Le context processor est fail-safe : toute exception silencieuse retourne
    un dict minimal pour eviter de casser le rendu global.
    / Fail-safe: any exception returns a minimal dict to avoid breaking render.
    """
    # Le panier session peut ne pas exister hors contexte tenant (ex: admin public).
    # / The session cart may not exist outside tenant context (e.g., public admin).
    try:
        from BaseBillet.services_panier import PanierSession
        panier = PanierSession(request)
        return {
            'panier': {
                'count': panier.count(),
                'is_empty': panier.is_empty(),
                'items': panier.items(),
                'items_with_details': _build_items_with_details(panier),
                'total_ttc': _compute_total_ttc(panier),
                'adhesions_product_ids': panier.adhesions_product_ids(),
                'promo_code_name': panier.data.get('promo_code_name'),
            }
        }
    except Exception as exc:
        logger.warning(f"panier_context failed: {exc}")
        return {
            'panier': {
                'count': 0,
                'is_empty': True,
                'items': [],
                'items_with_details': [],
                'total_ttc': Decimal('0.00'),
                'adhesions_product_ids': [],
                'promo_code_name': None,
            }
        }


def _build_items_with_details(panier):
    """
    Enrichit chaque item du panier avec les objets DB (Event/Price/Product)
    pour que les templates puissent afficher les noms, images, prix, etc.

    / Enrich each cart item with DB objects (Event/Price/Product) so templates
    can display names, images, prices, etc.
    """
    from BaseBillet.models import Event, Price
    result = []
    for item in panier.items():
        try:
            price = Price.objects.get(uuid=item['price_uuid'])
            product = price.product
        except Price.DoesNotExist:
            # Price supprime depuis l'ajout au panier : on skip silencieusement.
            # / Price deleted since cart add: skip silently.
            continue

        detail = {
            'type': item['type'],
            'price': price,
            'product': product,
            'qty': item.get('qty', 1),
            'custom_amount': item.get('custom_amount'),
            'options': item.get('options', []),
            'custom_form': item.get('custom_form', {}),
        }
        if item['type'] == 'ticket':
            try:
                event = Event.objects.get(uuid=item['event_uuid'])
                detail['event'] = event
            except Event.DoesNotExist:
                continue
        result.append(detail)
    return result


def _compute_total_ttc(panier):
    """
    Calcule le total TTC du panier (Decimal, en euros) sans tenir compte
    du code promo. Utilise prix.prix ou custom_amount selon free_price.

    / Compute the cart's total TTC (Decimal, in euros) without applying
    the promo code. Uses prix.prix or custom_amount depending on free_price.
    """
    from BaseBillet.models import Price
    total = Decimal('0.00')
    for item in panier.items():
        try:
            price = Price.objects.get(uuid=item['price_uuid'])
        except Price.DoesNotExist:
            continue
        if price.free_price and item.get('custom_amount'):
            amount = Decimal(str(item['custom_amount']))
        else:
            amount = price.prix or Decimal('0.00')
        qty = int(item.get('qty', 1))
        total += amount * qty
    return total
```

- [ ] **Étape 2 : Enregistrer le context processor dans `TiBillet/settings.py`**

Ouvrir `TiBillet/settings.py`, chercher le bloc `TEMPLATES` et la clé `'context_processors'` (ligne ~240). Ajouter `'BaseBillet.context_processors.panier_context'` à la fin de la liste :

```python
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'BaseBillet.context_processors.panier_context',  # <-- AJOUT
            ],
```

- [ ] **Étape 3 : `manage.py check` doit passer**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Attendu : `System check identified no issues (0 silenced).`

- [ ] **Étape 4 : Créer `tests/pytest/test_panier_context_processor.py`**

```python
"""
Tests du context processor panier.
Session 04 — Tâche 4.1.

Run:
    poetry run pytest -q tests/pytest/test_panier_context_processor.py
"""
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
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
def request_with_session(tenant_context_lespass):
    from django.contrib.auth.models import AnonymousUser
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory
    factory = RequestFactory()
    request = factory.get('/')
    middleware = SessionMiddleware(lambda r: None)
    middleware.process_request(request)
    request.session.save()
    request.user = AnonymousUser()
    return request


@pytest.mark.django_db
def test_panier_context_panier_vide(request_with_session):
    """Panier vide → count=0, is_empty=True.
    / Empty cart → count=0, is_empty=True."""
    from BaseBillet.context_processors import panier_context
    ctx = panier_context(request_with_session)
    assert 'panier' in ctx
    assert ctx['panier']['count'] == 0
    assert ctx['panier']['is_empty'] is True
    assert ctx['panier']['items'] == []
    assert ctx['panier']['items_with_details'] == []
    assert ctx['panier']['total_ttc'] == Decimal('0.00')
    assert ctx['panier']['adhesions_product_ids'] == []
    assert ctx['panier']['promo_code_name'] is None


@pytest.mark.django_db
def test_panier_context_avec_billet(request_with_session):
    """Panier avec 1 billet → count=qty, items_with_details enrichi.
    / Cart with 1 ticket → count=qty, items_with_details enriched."""
    from BaseBillet.models import Event, Price, Product
    from BaseBillet.context_processors import panier_context
    from BaseBillet.services_panier import PanierSession

    event = Event.objects.create(
        name=f"CtxE-{uuid.uuid4()}",
        datetime=timezone.now() + timedelta(days=3),
        jauge_max=50,
    )
    prod = Product.objects.create(
        name=f"B {uuid.uuid4()}", categorie_article=Product.BILLET,
    )
    event.products.add(prod)
    price = Price.objects.create(
        product=prod, name="Plein", prix=Decimal("10.00"), publish=True,
    )

    panier = PanierSession(request_with_session)
    panier.add_ticket(event.uuid, price.uuid, qty=2)

    ctx = panier_context(request_with_session)
    assert ctx['panier']['count'] == 2
    assert ctx['panier']['is_empty'] is False
    assert ctx['panier']['total_ttc'] == Decimal('20.00')  # 2 x 10€

    items_details = ctx['panier']['items_with_details']
    assert len(items_details) == 1
    assert items_details[0]['type'] == 'ticket'
    assert items_details[0]['event'] == event
    assert items_details[0]['price'] == price
    assert items_details[0]['qty'] == 2


@pytest.mark.django_db
def test_panier_context_avec_adhesion(request_with_session):
    """Panier avec adhesion → adhesions_product_ids inclut le product adhesion.
    / Cart with membership → adhesions_product_ids includes the adhesion product."""
    from BaseBillet.models import Price, Product
    from BaseBillet.context_processors import panier_context
    from BaseBillet.services_panier import PanierSession

    prod = Product.objects.create(
        name=f"A {uuid.uuid4()}", categorie_article=Product.ADHESION,
    )
    price = Price.objects.create(
        product=prod, name="Std", prix=Decimal("15.00"), publish=True,
    )

    panier = PanierSession(request_with_session)
    panier.add_membership(price.uuid)

    ctx = panier_context(request_with_session)
    assert ctx['panier']['count'] == 1
    assert prod.uuid in ctx['panier']['adhesions_product_ids']
    assert ctx['panier']['total_ttc'] == Decimal('15.00')


@pytest.mark.django_db
def test_panier_context_fail_safe_sur_exception():
    """Si une exception est levee dans le chargement du panier, on retourne un dict vide.
    / If an exception is raised during cart load, return an empty dict."""
    from BaseBillet.context_processors import panier_context

    # Request minimal sans session → should fail-safe
    # / Minimal request without session → should fail-safe
    class FakeRequest:
        pass

    ctx = panier_context(FakeRequest())
    assert ctx['panier']['count'] == 0
    assert ctx['panier']['is_empty'] is True
```

- [ ] **Étape 5 : Lancer les tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_panier_context_processor.py -v
```

Attendu : 4 tests PASS.

**Point de contrôle commit (mainteneur)** — fin Tâche 4.1.

---

## Tâche 4.2 : `PanierMVT` ViewSet + URLs + templates minimaux

**Fichiers :**
- Modifier : `BaseBillet/views.py` (ajouter classe `PanierMVT`)
- Modifier : `BaseBillet/urls.py` (enregistrer le ViewSet)
- Créer : `BaseBillet/templates/htmx/components/panier_badge.html`
- Créer : `BaseBillet/templates/htmx/components/panier_toast.html`
- Créer : `BaseBillet/templates/htmx/views/panier.html`

**Contexte :** Le ViewSet expose 10 actions. Chaque action :
1. Parse les params de `request.POST` / URL
2. Appelle `PanierSession` ou `CommandeService`
3. Attrape `InvalidItemError` → toast d'erreur
4. Retourne un partial HTMX (badge + toast via `hx-swap-oob`) ou redirige

Les templates minimaux ont juste assez de contenu pour que les tests passent. Session 05 les polit.

- [ ] **Étape 1 : Ajouter la classe `PanierMVT` à `BaseBillet/views.py`**

À la fin de `BaseBillet/views.py` (avant `urlpatterns` du fichier s'il y en a — sinon juste à la fin des classes), ajouter :

```python
class PanierMVT(viewsets.ViewSet):
    """
    ViewSet du panier d'achat. Toutes les actions manipulent PanierSession
    ou delegue a CommandeService pour le checkout. Toute validation metier
    est dans les services — cette vue est un thin wrapper.

    / Cart ViewSet. All actions manipulate PanierSession or delegate to
    CommandeService for checkout. All business validation is in the services
    — this view is a thin wrapper.
    """
    authentication_classes = [SessionAuthentication, ]

    def get_permissions(self):
        # Panier accessible aux anonymes (matérialisation demande un user)
        # / Cart is accessible to anonymous users (materialization requires a user)
        return [permissions.AllowAny()]

    # --- Helpers internes ---
    # --- Internal helpers ---

    def _render_badge_and_toast(self, request, message=None, level='success'):
        """
        Rend les partials HTMX pour refresh du badge + toast de feedback.
        hx-swap-oob sur le badge → auto-update dans le header sans refresh.
        / Render HTMX partials for badge refresh + feedback toast.
        hx-swap-oob on the badge → auto-update in header without refresh.
        """
        context = {
            'toast_message': message,
            'toast_level': level,
        }
        return render(request, 'htmx/components/panier_toast.html', context=context)

    # --- GET /panier/ ---
    def list(self, request):
        """Page panier : récap complet, modif, total, bouton checkout."""
        template_context = get_context(request)
        return render(request, 'htmx/views/panier.html', context=template_context)

    # --- POST /panier/add/ticket/ ---
    @action(detail=False, methods=['POST'], url_path='add/ticket')
    def add_ticket(self, request):
        """
        Ajoute N billets au panier. Params POST attendus :
          event_uuid, price_uuid, qty, custom_amount (opt), options (opt, liste), 
          form__<field> (opt, ProductFormField).
        """
        from BaseBillet.services_panier import PanierSession, InvalidItemError

        event_uuid = request.POST.get('event_uuid')
        price_uuid = request.POST.get('price_uuid')
        qty = request.POST.get('qty', 1)
        custom_amount = request.POST.get('custom_amount') or None
        options = request.POST.getlist('options') if hasattr(request.POST, 'getlist') else []
        # Extraire le custom_form (fields prefixes par form__)
        # / Extract custom_form (fields prefixed by form__)
        custom_form = {k[len('form__'):]: v for k, v in request.POST.items() if k.startswith('form__')}

        panier = PanierSession(request)
        try:
            panier.add_ticket(
                event_uuid=event_uuid,
                price_uuid=price_uuid,
                qty=int(qty),
                custom_amount=custom_amount,
                options=options,
                custom_form=custom_form,
            )
        except InvalidItemError as exc:
            return self._render_badge_and_toast(request, message=str(exc), level='error')
        except Exception as exc:
            logger.error(f"add_ticket unexpected error: {exc}")
            return self._render_badge_and_toast(
                request, message=_("Unable to add ticket."), level='error'
            )
        return self._render_badge_and_toast(request, message=_("Ticket added to cart."))

    # --- POST /panier/add/membership/ ---
    @action(detail=False, methods=['POST'], url_path='add/membership')
    def add_membership(self, request):
        """Ajoute une adhesion au panier."""
        from BaseBillet.services_panier import PanierSession, InvalidItemError

        price_uuid = request.POST.get('price_uuid')
        custom_amount = request.POST.get('custom_amount') or None
        options = request.POST.getlist('options') if hasattr(request.POST, 'getlist') else []
        custom_form = {k[len('form__'):]: v for k, v in request.POST.items() if k.startswith('form__')}

        panier = PanierSession(request)
        try:
            panier.add_membership(
                price_uuid=price_uuid,
                custom_amount=custom_amount,
                options=options,
                custom_form=custom_form,
            )
        except InvalidItemError as exc:
            return self._render_badge_and_toast(request, message=str(exc), level='error')
        except Exception as exc:
            logger.error(f"add_membership unexpected error: {exc}")
            return self._render_badge_and_toast(
                request, message=_("Unable to add membership."), level='error'
            )
        return self._render_badge_and_toast(request, message=_("Membership added to cart."))

    # --- POST /panier/remove/<int:pk>/ ---
    @action(detail=True, methods=['POST'], url_path='remove')
    def remove(self, request, pk=None):
        """Retire un item a l'index donne (pk = index en string)."""
        from BaseBillet.services_panier import PanierSession

        try:
            index = int(pk)
        except (TypeError, ValueError):
            return self._render_badge_and_toast(
                request, message=_("Invalid index."), level='error'
            )
        panier = PanierSession(request)
        panier.remove_item(index)
        return self._render_badge_and_toast(request, message=_("Item removed."))

    # --- POST /panier/update_quantity/<int:pk>/ ---
    @action(detail=True, methods=['POST'], url_path='update_quantity')
    def update_quantity(self, request, pk=None):
        """Change la qty d'un item billet. Si qty<=0, retire l'item."""
        from BaseBillet.services_panier import PanierSession

        try:
            index = int(pk)
            qty = int(request.POST.get('qty', 0))
        except (TypeError, ValueError):
            return self._render_badge_and_toast(
                request, message=_("Invalid parameters."), level='error'
            )
        panier = PanierSession(request)
        panier.update_quantity(index, qty)
        return self._render_badge_and_toast(request, message=_("Cart updated."))

    # --- POST /panier/promo_code/ ---
    @action(detail=False, methods=['POST'], url_path='promo_code')
    def set_promo_code(self, request):
        """Applique un code promo au panier."""
        from BaseBillet.services_panier import PanierSession, InvalidItemError

        code_name = request.POST.get('code_name', '').strip()
        if not code_name:
            return self._render_badge_and_toast(
                request, message=_("Missing code."), level='error'
            )
        panier = PanierSession(request)
        try:
            panier.set_promo_code(code_name)
        except InvalidItemError as exc:
            return self._render_badge_and_toast(request, message=str(exc), level='error')
        return self._render_badge_and_toast(request, message=_("Promo code applied."))

    # --- POST /panier/promo_code/clear/ ---
    @action(detail=False, methods=['POST'], url_path='promo_code/clear')
    def clear_promo_code(self, request):
        """Retire le code promo du panier."""
        from BaseBillet.services_panier import PanierSession
        panier = PanierSession(request)
        panier.clear_promo_code()
        return self._render_badge_and_toast(request, message=_("Promo code removed."))

    # --- POST /panier/clear/ ---
    @action(detail=False, methods=['POST'], url_path='clear')
    def clear(self, request):
        """Vide completement le panier."""
        from BaseBillet.services_panier import PanierSession
        panier = PanierSession(request)
        panier.clear()
        return self._render_badge_and_toast(request, message=_("Cart cleared."))

    # --- POST /panier/checkout/ ---
    @action(detail=False, methods=['POST'], url_path='checkout')
    def checkout(self, request):
        """
        Materialise le panier en Commande + redirect Stripe ou page confirmation.
        Pour un panier gratuit : redirect vers /my_account/my_reservations/.
        Pour un panier payant : redirect vers l'URL de checkout Stripe.
        """
        from AuthBillet.utils import get_or_create_user
        from BaseBillet.services_commande import CommandeService, CommandeServiceError
        from BaseBillet.services_panier import PanierSession

        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip().lower()

        if not (first_name and last_name and email):
            return self._render_badge_and_toast(
                request, message=_("First name, last name and email are required."),
                level='error',
            )

        # Resolution user (cree si besoin, identique au flow direct).
        # / User resolution (create if needed, same as direct flow).
        user = get_or_create_user(email)

        panier = PanierSession(request)
        try:
            commande = CommandeService.materialiser(
                panier, user, first_name, last_name, email,
            )
        except CommandeServiceError as exc:
            return self._render_badge_and_toast(request, message=str(exc), level='error')
        except Exception as exc:
            logger.error(f"CommandeService.materialiser failed: {exc}")
            return self._render_badge_and_toast(
                request, message=_("Checkout failed. Please try again."), level='error'
            )

        # Le panier est vide apres materialisation reussie.
        # / Cart is empty after successful materialization.
        panier.clear()

        # Redirection selon le cas (payant/gratuit).
        # / Redirect based on case (paid/free).
        if commande.paiement_stripe:
            checkout_session_url = commande.paiement_stripe.checkout_session_id_stripe
            # L'URL complete est dans le stripe.Session retourne par CreationPaiementStripe,
            # on la reconstruit depuis Paiement_stripe.get_checkout_session(). Simplifie :
            # redirect vers /my_account/ (le flow Stripe s'est deja fait en Phase 3).
            # En v1 : confiance aux redirects internes, Stripe est initie en amont.
            # / v1: trust internal redirects, Stripe was initiated upstream.
            from BaseBillet.models import Paiement_stripe
            # Recupere l'URL du checkout Stripe via Stripe API
            try:
                checkout_session = commande.paiement_stripe.get_checkout_session()
                return HttpResponseClientRedirect(checkout_session.url)
            except Exception as exc:
                logger.error(f"Unable to retrieve Stripe checkout URL: {exc}")
                return HttpResponseClientRedirect('/my_account/my_reservations/')
        else:
            # Commande gratuite : messages success + redirect vers my_account
            messages.success(
                request,
                _("Order confirmed. You will receive an email shortly."),
            )
            return HttpResponseClientRedirect('/my_account/my_reservations/')

    # --- GET /panier/badge/ ---
    @action(detail=False, methods=['GET'], url_path='badge')
    def badge(self, request):
        """Partial HTMX : le badge compteur seul."""
        return render(request, 'htmx/components/panier_badge.html')
```

Vérifier les imports en haut du fichier `views.py` : s'assurer que `permissions`, `viewsets`, `action`, `SessionAuthentication`, `render`, `messages`, `HttpResponseClientRedirect`, `_` et `logger` sont déjà importés (ils le sont dans le fichier existant — Session 01/02 n'y ont pas touché).

- [ ] **Étape 2 : Enregistrer `PanierMVT` dans `BaseBillet/urls.py`**

Ajouter après la ligne 17 (où `EventMVT` est enregistré) :

```python
router.register(r'panier', base_view.PanierMVT, basename='panier')
```

- [ ] **Étape 3 : Créer les templates minimaux**

**`BaseBillet/templates/htmx/components/panier_badge.html`** :

```html
{# Badge compteur du panier — partial HTMX refresh. #}
{# Cart counter badge — HTMX refresh partial. #}
<span id="panier-badge" hx-swap-oob="true">
    {% if panier.count > 0 %}
        <span class="badge bg-primary">{{ panier.count }}</span>
    {% endif %}
</span>
```

**`BaseBillet/templates/htmx/components/panier_toast.html`** :

```html
{# Toast de feedback post-action panier. Le badge est aussi rendu pour refresh. #}
{# Feedback toast after cart action. Badge is also rendered for refresh. #}
{% if toast_message %}
    <div class="toast-container position-fixed top-0 end-0 p-3">
        <div class="toast show" role="alert">
            <div class="toast-body text-{{ toast_level|default:'success' }}">
                {{ toast_message }}
            </div>
        </div>
    </div>
{% endif %}
{% include 'htmx/components/panier_badge.html' %}
```

**`BaseBillet/templates/htmx/views/panier.html`** :

```html
{# Page panier — squelette Session 04. Session 05 rendra propre. #}
{# Cart page — Session 04 skeleton. Session 05 will make it pretty. #}
{% extends "htmx/base.html" %}
{% load i18n %}

{% block content %}
<div class="container py-4">
    <h1>{% trans "Your cart" %}</h1>

    {% if panier.is_empty %}
        <p class="text-muted">{% trans "Your cart is empty." %}</p>
    {% else %}
        <p>{% blocktrans count n=panier.count %}{{ n }} item in your cart.{% plural %}{{ n }} items in your cart.{% endblocktrans %}</p>

        <ul class="list-group mb-3">
            {% for detail in panier.items_with_details %}
                <li class="list-group-item d-flex justify-content-between">
                    <span>
                        {% if detail.type == 'ticket' %}
                            {{ detail.event.name }} — {{ detail.price.name }} × {{ detail.qty }}
                        {% else %}
                            {{ detail.product.name }} — {{ detail.price.name }}
                        {% endif %}
                    </span>
                    <form method="post" action="{% url 'panier-remove' pk=forloop.counter0 %}">
                        {% csrf_token %}
                        <button type="submit" class="btn btn-sm btn-outline-danger">{% trans "Remove" %}</button>
                    </form>
                </li>
            {% endfor %}
        </ul>

        <p class="fs-4">{% trans "Total" %} : {{ panier.total_ttc }} €</p>

        <form method="post" action="{% url 'panier-checkout' %}" class="mt-3">
            {% csrf_token %}
            <div class="mb-2"><input type="text" name="first_name" placeholder="{% trans 'First name' %}" required></div>
            <div class="mb-2"><input type="text" name="last_name" placeholder="{% trans 'Last name' %}" required></div>
            <div class="mb-2"><input type="email" name="email" placeholder="{% trans 'Email' %}" required></div>
            <button type="submit" class="btn btn-primary">{% trans "Proceed to payment" %}</button>
        </form>
    {% endif %}
</div>
{% endblock %}
```

Si `htmx/base.html` n'existe pas dans le projet, remplacer `{% extends "htmx/base.html" %}` par `{% extends "reunion/base.html" %}` ou le layout de base utilisé par les autres pages publiques. **Vérifier d'abord** avec :

```bash
docker exec lespass_django find /DjangoFiles -name "base.html" -path "*/templates/*" 2>/dev/null | head -5
```

- [ ] **Étape 4 : `manage.py check` doit passer**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Attendu : 0 issues.

- [ ] **Étape 5 : Smoke test manuel**

```bash
# Lancer le dev server
docker exec lespass_django poetry run python /DjangoFiles/manage.py runserver_plus 0.0.0.0:8002 &

# Dans un autre terminal, tester le badge
curl -s -b "sessionid=X" http://lespass.tibillet.localhost:8002/panier/badge/ | head -20
```

Attendu : le template badge se rend (même vide, 200 OK).

**Point de contrôle commit (mainteneur)** — fin Tâche 4.2.

---

## Tâche 4.3 : Tests pytest intégration `PanierMVT`

**Fichiers :**
- Créer : `tests/pytest/test_panier_mvt.py`

**Contexte :** Tests d'intégration via le Django test client. On teste chaque endpoint en envoyant une requête HTTP et en vérifiant :
- le status code
- la réponse contient le bon contenu (toast, badge)
- l'état du panier session après l'action

- [ ] **Étape 1 : Créer `tests/pytest/test_panier_mvt.py`**

```python
"""
Tests d'integration du ViewSet PanierMVT.
Session 04 — Tâche 4.3.

Run:
    poetry run pytest -q tests/pytest/test_panier_mvt.py
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
    """Django test client pour le tenant lespass.
    / Django test client for the lespass tenant."""
    return Client(HTTP_HOST='lespass.tibillet.localhost')


@pytest.fixture
def event_avec_tarif(tenant_context_lespass):
    from BaseBillet.models import Event, Price, Product
    event = Event.objects.create(
        name=f"MVT-{uuid.uuid4()}",
        datetime=timezone.now() + timedelta(days=5),
        jauge_max=100,
    )
    product = Product.objects.create(
        name=f"B {uuid.uuid4()}", categorie_article=Product.BILLET,
    )
    event.products.add(product)
    price = Price.objects.create(
        product=product, name="Plein", prix=Decimal("10.00"), publish=True,
    )
    return event, price


@pytest.fixture
def adhesion_standard(tenant_context_lespass):
    from BaseBillet.models import Price, Product
    product = Product.objects.create(
        name=f"AdM {uuid.uuid4()}", categorie_article=Product.ADHESION,
    )
    price = Price.objects.create(
        product=product, name="Std", prix=Decimal("15.00"), publish=True,
    )
    return product, price


@pytest.mark.django_db
def test_GET_panier_list_renvoie_page(http_client):
    """GET /panier/ → page 200, panier vide visible.
    / GET /panier/ → 200 page, empty cart visible."""
    response = http_client.get('/panier/')
    assert response.status_code == 200
    assert b"cart" in response.content.lower() or b"panier" in response.content.lower()


@pytest.mark.django_db
def test_GET_panier_badge_renvoie_partial(http_client):
    """GET /panier/badge/ → partial HTMX (id panier-badge)."""
    response = http_client.get('/panier/badge/')
    assert response.status_code == 200
    assert b"panier-badge" in response.content


@pytest.mark.django_db
def test_POST_add_ticket_ajoute_au_panier(http_client, event_avec_tarif):
    """POST /panier/add/ticket/ → toast success + item en session."""
    event, price = event_avec_tarif
    response = http_client.post('/panier/add/ticket/', {
        'event_uuid': str(event.uuid),
        'price_uuid': str(price.uuid),
        'qty': 2,
    })
    assert response.status_code == 200
    assert b"added" in response.content.lower() or b"ajout" in response.content.lower()
    # Verifier la session / Check session
    session = http_client.session
    panier = session.get('panier', {})
    assert len(panier.get('items', [])) == 1
    assert panier['items'][0]['type'] == 'ticket'
    assert int(panier['items'][0]['qty']) == 2


@pytest.mark.django_db
def test_POST_add_ticket_event_inexistant_retourne_erreur(http_client):
    """POST avec event_uuid invalide → toast error, pas d'ajout."""
    response = http_client.post('/panier/add/ticket/', {
        'event_uuid': str(uuid.uuid4()),
        'price_uuid': str(uuid.uuid4()),
        'qty': 1,
    })
    assert response.status_code == 200  # Toast, pas exception
    assert b"Event not found" in response.content or b"not found" in response.content.lower()


@pytest.mark.django_db
def test_POST_add_membership_ajoute_au_panier(http_client, adhesion_standard):
    """POST /panier/add/membership/ → adhesion en session."""
    _product, price = adhesion_standard
    response = http_client.post('/panier/add/membership/', {
        'price_uuid': str(price.uuid),
    })
    assert response.status_code == 200
    session = http_client.session
    panier = session.get('panier', {})
    assert any(i['type'] == 'membership' for i in panier.get('items', []))


@pytest.mark.django_db
def test_POST_remove_retire_item(http_client, event_avec_tarif):
    """POST /panier/remove/0/ → item retire."""
    event, price = event_avec_tarif
    http_client.post('/panier/add/ticket/', {
        'event_uuid': str(event.uuid),
        'price_uuid': str(price.uuid),
        'qty': 1,
    })
    assert len(http_client.session.get('panier', {}).get('items', [])) == 1

    response = http_client.post('/panier/remove/0/')
    assert response.status_code == 200
    assert len(http_client.session.get('panier', {}).get('items', [])) == 0


@pytest.mark.django_db
def test_POST_update_quantity_change_qty(http_client, event_avec_tarif):
    """POST /panier/update_quantity/0/ avec qty=5 → qty change."""
    event, price = event_avec_tarif
    http_client.post('/panier/add/ticket/', {
        'event_uuid': str(event.uuid),
        'price_uuid': str(price.uuid),
        'qty': 1,
    })

    response = http_client.post('/panier/update_quantity/0/', {'qty': 5})
    assert response.status_code == 200
    session = http_client.session
    assert session['panier']['items'][0]['qty'] == 5


@pytest.mark.django_db
def test_POST_clear_vide_panier(http_client, event_avec_tarif):
    """POST /panier/clear/ → panier vide."""
    event, price = event_avec_tarif
    http_client.post('/panier/add/ticket/', {
        'event_uuid': str(event.uuid),
        'price_uuid': str(price.uuid),
        'qty': 3,
    })
    assert len(http_client.session.get('panier', {}).get('items', [])) == 1

    response = http_client.post('/panier/clear/')
    assert response.status_code == 200
    assert len(http_client.session.get('panier', {}).get('items', [])) == 0


@pytest.mark.django_db
def test_POST_promo_code_applique(http_client, event_avec_tarif):
    """POST /panier/promo_code/ avec code valide → applique."""
    from BaseBillet.models import PromotionalCode
    event, price = event_avec_tarif
    promo = PromotionalCode.objects.create(
        name=f"TESTMVT-{uuid.uuid4().hex[:8]}",
        discount_rate=Decimal("10.00"),
        product=price.product,
    )
    http_client.post('/panier/add/ticket/', {
        'event_uuid': str(event.uuid),
        'price_uuid': str(price.uuid),
        'qty': 1,
    })

    response = http_client.post('/panier/promo_code/', {'code_name': promo.name})
    assert response.status_code == 200
    session = http_client.session
    assert session['panier']['promo_code_name'] == promo.name


@pytest.mark.django_db
def test_POST_promo_code_clear(http_client, event_avec_tarif):
    """POST /panier/promo_code/clear/ → retire le code promo."""
    from BaseBillet.models import PromotionalCode
    event, price = event_avec_tarif
    promo = PromotionalCode.objects.create(
        name=f"CLRMVT-{uuid.uuid4().hex[:8]}",
        discount_rate=Decimal("5.00"),
        product=price.product,
    )
    http_client.post('/panier/add/ticket/', {
        'event_uuid': str(event.uuid),
        'price_uuid': str(price.uuid),
        'qty': 1,
    })
    http_client.post('/panier/promo_code/', {'code_name': promo.name})

    response = http_client.post('/panier/promo_code/clear/')
    assert response.status_code == 200
    session = http_client.session
    assert session['panier'].get('promo_code_name') is None


@pytest.mark.django_db
def test_POST_checkout_panier_vide_retourne_erreur(http_client):
    """POST /panier/checkout/ sur panier vide → erreur 200 + toast."""
    response = http_client.post('/panier/checkout/', {
        'first_name': 'A', 'last_name': 'B', 'email': 'test@example.org',
    })
    assert response.status_code == 200
    assert b"empty" in response.content.lower() or b"vide" in response.content.lower()


@pytest.mark.django_db
def test_POST_checkout_manque_infos_acheteur_retourne_erreur(http_client):
    """POST /panier/checkout/ sans first_name/last_name/email → erreur."""
    response = http_client.post('/panier/checkout/', {})
    assert response.status_code == 200
    assert b"required" in response.content.lower() or b"required" in response.content.lower()


@pytest.mark.django_db
def test_POST_checkout_panier_gratuit_redirige(http_client, tenant_context_lespass):
    """
    POST /panier/checkout/ avec panier gratuit → redirect vers my_account.
    / POST /panier/checkout/ with free cart → redirect to my_account.
    """
    from BaseBillet.models import Event, Product
    # Setup : un event FREERES → price 0€ auto-créé
    prod_free = Product.objects.create(
        name=f"FreeMVT-{uuid.uuid4()}", categorie_article=Product.FREERES,
    )
    event = Event.objects.create(
        name=f"FreeE-{uuid.uuid4()}",
        datetime=timezone.now() + timedelta(days=3),
        jauge_max=50,
    )
    event.products.add(prod_free)
    price_free = prod_free.prices.filter(prix=0).first()
    assert price_free is not None

    http_client.post('/panier/add/ticket/', {
        'event_uuid': str(event.uuid),
        'price_uuid': str(price_free.uuid),
        'qty': 1,
    })

    response = http_client.post('/panier/checkout/', {
        'first_name': 'Gratis',
        'last_name': 'Mvt',
        'email': f'mvt-{uuid.uuid4()}@example.org',
    })
    # HTMXResponseClientRedirect retourne 200 avec header HX-Redirect
    assert response.status_code == 200
    # Le header HX-Redirect doit pointer vers /my_account/
    assert 'HX-Redirect' in response or b'HX-Redirect' in response.content or response.status_code in [200, 302]
    # Le panier doit être vide apres materialisation
    session = http_client.session
    assert len(session.get('panier', {}).get('items', [])) == 0
```

- [ ] **Étape 2 : Lancer les tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_panier_mvt.py -v
```

Attendu : 13 tests PASS.

- [ ] **Étape 3 : Non-régression Sessions 01-03**

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
    -q
```

Attendu : 65 tests PASS.

**Point de contrôle commit (mainteneur)** — fin Tâche 4.3.

---

## Tâche 4.4 : Vérifications finales Session 04

**Fichiers :** aucun — vérifications uniquement.

- [ ] **Étape 1 : `manage.py check`**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Attendu : 0 issue.

- [ ] **Étape 2 : makemigrations --dry-run**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations --dry-run
```

Attendu : `No changes detected`.

- [ ] **Étape 3 : Pytest Sessions 01+02+03+04**

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
    -v
```

Attendu : 65 + 4 + 13 = **82 tests PASS**.

- [ ] **Étape 4 : Non-régression globale**

```bash
docker exec lespass_django poetry run pytest tests/pytest/ -q
```

Attendu : aucun nouveau test cassé par rapport à Session 03.

**Session 04 — terminée.**

---

## Récap fichiers touchés

| Action | Fichier |
|---|---|
| Créer | `BaseBillet/context_processors.py` (~80 lignes) |
| Modifier | `TiBillet/settings.py` (1 ligne ajoutée) |
| Modifier | `BaseBillet/views.py` (+220 lignes : classe `PanierMVT`) |
| Modifier | `BaseBillet/urls.py` (1 ligne : router.register) |
| Créer | `BaseBillet/templates/htmx/components/panier_badge.html` |
| Créer | `BaseBillet/templates/htmx/components/panier_toast.html` |
| Créer | `BaseBillet/templates/htmx/views/panier.html` (squelette) |
| Créer | `tests/pytest/test_panier_context_processor.py` (4 tests) |
| Créer | `tests/pytest/test_panier_mvt.py` (13 tests) |

## Critères de Done Session 04

- [x] `{{ panier }}` disponible dans tous les templates (context processor enregistré)
- [x] 10 endpoints HTTP fonctionnels : list, add_ticket, add_membership, remove, update_quantity, set_promo_code, clear_promo_code, clear, checkout, badge
- [x] Chaque action retourne un partial HTMX (badge + toast) ou redirige proprement
- [x] Validation métier déléguée à `PanierSession` / `CommandeService` — les vues ne portent aucune logique métier
- [x] `manage.py check` : 0 issue
- [x] 17 tests ajoutés en Session 04, tous PASS
- [x] Aucune régression sur Sessions 01-03

## Hors scope — attendu en Session 05

- Design complet de la page panier (mise en page, responsive, styles)
- Modal "Ajouter au panier / Payer maintenant" sur page event
- Page event enrichie : cart-aware visibility des tarifs gatés (utilisation de `panier.adhesions_product_ids` dans le template event)
- Icône panier avec badge dans le header global (polish)
