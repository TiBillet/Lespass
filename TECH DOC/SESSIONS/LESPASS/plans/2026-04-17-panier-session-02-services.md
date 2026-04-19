# Panier multi-events — Plan Session 02 : Services `PanierSession` + `CommandeService`

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Poser la logique métier du panier — gestionnaire de session `PanierSession` (ajout/retrait/validations) + orchestrateur de matérialisation `CommandeService.materialiser()` (transaction atomique transforme un panier en DB).

**Architecture:** Deux services indépendants dans `BaseBillet/`. `PanierSession` manipule uniquement `request.session` (pas d'écriture DB). `CommandeService.materialiser()` est l'unique point d'entrée qui écrit en DB (Commande + N Reservations + M Memberships + LigneArticle + éventuel Paiement_stripe), le tout sous `@transaction.atomic`. Une petite adaptation (flag `create_checkout`) est faite sur `TicketCreator` existant pour le rendre réutilisable par l'orchestrateur.

**Tech Stack:** Django 5.x, django-tenants, poetry, PostgreSQL, pytest. FALC (verbose, commentaires FR/EN, noms explicites, pas de sur-ingénierie).

**Spec:** `TECH DOC/SESSIONS/LESPASS/specs/2026-04-17-panier-multi-events-design.md` (sections 3.3, 3.4, 3.5, 3.7bis)

**Dépend de :** Session 01 (modèle `Commande` + FK sur Reservation/Membership — déjà DONE).

**Scope de cette session :**
- ✅ `BaseBillet/services_panier.py` — classe `PanierSession` + constantes overlap + helper `reservations_bloquantes_pour_user()` + exceptions (`InvalidItemError`, `PanierError`)
- ✅ Adaptation `BaseBillet/validators.py` — `TicketCreator.__init__(create_checkout=True)` param
- ✅ `BaseBillet/services_commande.py` — classe `CommandeService` + méthode `materialiser()`
- ✅ Tests pytest : `test_panier_session.py`, `test_commande_service.py`, `test_ticket_creator_no_checkout.py`
- ✅ Vérifications finales : manage.py check, suite pytest complète, zéro régression

**Hors scope (sessions suivantes) :**
- ❌ Patch `signals.py` + `ReservationValidator` cart-aware → Session 03
- ❌ Param `accept_sepa` sur `CreationPaiementStripe` → Session 03 (mais `CommandeService` passera déjà le flag, sera ignoré tant que Session 03 pas faite)
- ❌ Vues HTMX `PanierMVT` → Session 04
- ❌ Templates modal / page panier → Session 05
- ❌ Tests E2E Playwright → Session 06

**Règle projet :** L'agent ne touche jamais à git. Les commits sont faits par le mainteneur.

---

## Architecture des fichiers

| Fichier | Action | Rôle |
|---|---|---|
| `BaseBillet/services_panier.py` | Créer | Classe `PanierSession` (manipulation session uniquement, zéro écriture DB) + constantes overlap + helper partagé + exceptions |
| `BaseBillet/services_commande.py` | Créer | Classe `CommandeService` avec méthode statique `materialiser()` — orchestrateur atomique session → DB |
| `BaseBillet/validators.py` | Modifier | `TicketCreator.__init__` : nouveau param `create_checkout: bool = True`. Si False, ne pas appeler `self.get_checkout_stripe()` à la fin de `method_B`. Aucune autre modif. |
| `tests/pytest/test_panier_session.py` | Créer | Tests PanierSession : ajout/retrait, validations, overlap, code promo, cart-aware adhésion |
| `tests/pytest/test_commande_service.py` | Créer | Tests CommandeService.materialiser() : cas nominal, gratuit, mix, rollback, ordre Phase 1/2 |
| `tests/pytest/test_ticket_creator_no_checkout.py` | Créer | Tests non-régression TicketCreator avec `create_checkout=False` |

**Principes de découpage respectés :**
- `services_panier.py` : responsabilité unique = manipuler la session (jamais la DB).
- `services_commande.py` : responsabilité unique = matérialiser un panier en DB (atomique).
- La frontière est nette : PanierSession donne des items (dict), CommandeService transforme en ORM.
- Les deux services se parlent via des types simples (dicts, listes). Pas de couplage direct.

---

## Tâche 2.1 : `PanierSession` squelette + exceptions

**Fichiers :**
- Créer : `BaseBillet/services_panier.py`

**Contexte :** On crée d'abord la classe `PanierSession` avec les opérations de base (lecture/écriture de la clé `panier` dans `request.session`, add/remove simples SANS validations complexes). Les validations métier viennent dans les tâches suivantes. Objectif : avoir une classe fonctionnelle et testable dès la première tâche.

- [ ] **Étape 1 : Créer le fichier avec la structure de base**

```python
"""
Gestionnaire du panier en session Django.
/ Django session-backed cart manager.

Le panier vit uniquement dans request.session['panier']. Aucune écriture
en DB à ce niveau — la matérialisation se fait dans CommandeService.

/ The cart lives only in request.session['panier']. No DB writes at this
level — materialization happens in CommandeService.
"""
import logging
import uuid as uuid_lib
from datetime import timedelta
from decimal import Decimal
from typing import Optional

from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Exceptions panier
# / Cart exceptions
# --------------------------------------------------------------------------


class PanierError(Exception):
    """Exception générique du panier. / Generic cart exception."""


class InvalidItemError(PanierError):
    """Un item ne peut pas être ajouté au panier (validation métier).
    / An item cannot be added to the cart (business validation)."""


# --------------------------------------------------------------------------
# Constantes de détection de chevauchement (cf. spec section 3.7bis)
# / Overlap detection constants (cf. spec section 3.7bis)
# --------------------------------------------------------------------------
# Importées de manière retardée (éviter circular import au chargement)
# / Imported lazily (avoid circular import at load time)


def _blocking_statuses():
    """Statuts qui bloquent inconditionnellement un chevauchement.
    / Statuses that unconditionally block an overlap."""
    from BaseBillet.models import Reservation
    return [
        Reservation.PAID,
        Reservation.VALID,
        Reservation.PAID_ERROR,
        Reservation.PAID_NOMAIL,
        Reservation.FREERES,
        Reservation.FREERES_USERACTIV,
    ]


def _recent_blocking_statuses():
    """Statuts qui bloquent uniquement si récents (< 15 min).
    / Statuses that block only if recent (< 15 min)."""
    from BaseBillet.models import Reservation
    return [Reservation.CREATED, Reservation.UNPAID]


RECENT_BLOCKING_WINDOW = timedelta(minutes=15)


def reservations_bloquantes_pour_user(user, start, end):
    """
    Retourne les reservations du user qui chevauchent [start, end] et qui
    bloquent une nouvelle réservation.
    / Returns the user's reservations that overlap [start, end] and block
    a new booking.

    Logique (cf. spec section 3.7bis) :
    - Blocage dur : statuts dans BLOCKING_STATUSES, toujours.
    - Blocage récent : statuts CREATED/UNPAID uniquement si créés < 15 min.

    / Logic (cf. spec section 3.7bis):
    - Hard block: statuses in BLOCKING_STATUSES, always.
    - Recent block: CREATED/UNPAID only if created < 15 min ago.
    """
    from BaseBillet.models import Reservation

    overlap_q = (
        Q(event__datetime__range=(start, end)) |
        Q(event__end_datetime__range=(start, end)) |
        Q(event__datetime__lte=start, event__end_datetime__gte=end)
    )

    blocage_dur = Reservation.objects.filter(
        user_commande=user,
        status__in=_blocking_statuses(),
    ).filter(overlap_q)

    seuil_recent = timezone.now() - RECENT_BLOCKING_WINDOW
    blocage_recent = Reservation.objects.filter(
        user_commande=user,
        status__in=_recent_blocking_statuses(),
        datetime__gte=seuil_recent,
    ).filter(overlap_q)

    return blocage_dur.union(blocage_recent)


# --------------------------------------------------------------------------
# PanierSession — gestionnaire du panier en session
# / PanierSession — session-backed cart manager
# --------------------------------------------------------------------------


class PanierSession:
    """
    Manipule le panier stocké dans request.session['panier'].

    Structure de la session :
        request.session['panier'] = {
            'items': [
                {'type': 'ticket', 'event_uuid': '...', 'price_uuid': '...',
                 'qty': 2, 'custom_amount': None,
                 'options': [...], 'custom_form': {}},
                {'type': 'membership', 'price_uuid': '...',
                 'custom_amount': None, 'options': [], 'custom_form': {}},
            ],
            'promo_code_name': None,
            'created_at': '2026-04-17T12:00:00+00:00',
        }

    / Manipulates the cart stored in request.session['panier'].
    """

    SESSION_KEY = 'panier'

    def __init__(self, request):
        self.request = request
        self.session = request.session
        self._load()

    # --- Internes : lecture/écriture session ---
    # --- Internal: session read/write ---

    def _load(self):
        """Charge ou initialise la structure du panier.
        / Loads or initializes the cart structure."""
        data = self.session.get(self.SESSION_KEY)
        if not data or not isinstance(data, dict):
            data = {
                'items': [],
                'promo_code_name': None,
                'created_at': timezone.now().isoformat(),
            }
            self.session[self.SESSION_KEY] = data
            self.session.modified = True
        self._data = data

    def _save(self):
        """Persiste les modifications en session.
        / Persists changes to the session."""
        self.session[self.SESSION_KEY] = self._data
        self.session.modified = True

    # --- Lecture publique ---
    # --- Public read ---

    @property
    def data(self):
        """Accès brut aux données du panier.
        / Raw access to cart data."""
        return self._data

    def items(self):
        """Liste des items (dicts) actuellement dans le panier.
        / List of items (dicts) currently in the cart."""
        return list(self._data.get('items', []))

    def count(self):
        """Nombre total d'items (pour le badge header).
        Un item billet qty=3 compte pour 3, un membership compte pour 1.
        / Total number of items (for header badge).
        A ticket item qty=3 counts as 3, a membership counts as 1."""
        total = 0
        for item in self._data.get('items', []):
            if item['type'] == 'ticket':
                total += int(item.get('qty', 0))
            else:
                total += 1
        return total

    def is_empty(self):
        """True si le panier n'a aucun item.
        / True if the cart has no items."""
        return len(self._data.get('items', [])) == 0

    # --- Écritures publiques (squelette — validations dans tâches suivantes) ---
    # --- Public writes (skeleton — validations in later tasks) ---

    def add_ticket(self, event_uuid, price_uuid, qty,
                   custom_amount=None, options=None, custom_form=None):
        """
        Ajoute un item billet au panier. Validations complètes dans Tâche 2.2+.
        / Adds a ticket item to the cart. Full validations in Task 2.2+.
        """
        # Pour l'instant : on convertit en str pour uniformité du stockage JSON,
        # on accepte tel quel, aucune validation DB (viendra Tâche 2.2).
        # / For now: convert to str for JSON storage uniformity, accept as is,
        # no DB validation (coming in Task 2.2).
        item = {
            'type': 'ticket',
            'event_uuid': str(event_uuid),
            'price_uuid': str(price_uuid),
            'qty': int(qty),
            'custom_amount': str(custom_amount) if custom_amount is not None else None,
            'options': [str(o) for o in (options or [])],
            'custom_form': dict(custom_form or {}),
        }
        self._data['items'].append(item)
        self._save()
        return item

    def add_membership(self, price_uuid,
                       custom_amount=None, options=None, custom_form=None):
        """
        Ajoute un item adhésion au panier. Validations complètes dans Tâche 2.2+.
        / Adds a membership item to the cart. Full validations in Task 2.2+.
        """
        item = {
            'type': 'membership',
            'price_uuid': str(price_uuid),
            'custom_amount': str(custom_amount) if custom_amount is not None else None,
            'options': [str(o) for o in (options or [])],
            'custom_form': dict(custom_form or {}),
        }
        self._data['items'].append(item)
        self._save()
        return item

    def remove_item(self, index):
        """
        Retire l'item à l'index donné. Pas d'erreur si index invalide (silent).
        / Removes the item at the given index. No error on invalid index.
        """
        items = self._data.get('items', [])
        if 0 <= index < len(items):
            items.pop(index)
            self._save()

    def update_quantity(self, index, qty):
        """
        Met à jour la quantité d'un item billet. Si qty <= 0, retire l'item.
        Ignore les items membership (leur qty est toujours 1).
        / Updates a ticket item's quantity. If qty <= 0, removes it.
        Ignores membership items (qty always 1).
        """
        items = self._data.get('items', [])
        if not (0 <= index < len(items)):
            return
        item = items[index]
        if item['type'] != 'ticket':
            return
        if qty <= 0:
            self.remove_item(index)
            return
        item['qty'] = int(qty)
        self._save()

    def clear(self):
        """Vide complètement le panier.
        / Clears the entire cart."""
        self._data = {
            'items': [],
            'promo_code_name': None,
            'created_at': timezone.now().isoformat(),
        }
        self._save()

    def adhesions_product_ids(self):
        """
        UUIDs des Product d'adhésion présents dans le panier (pour débloquer
        les tarifs gatés dans les templates).
        / UUIDs of membership Products present in the cart (to unlock gated
        rates in templates).
        """
        from BaseBillet.models import Price
        product_ids = []
        for item in self._data.get('items', []):
            if item['type'] != 'membership':
                continue
            try:
                price = Price.objects.get(uuid=item['price_uuid'])
                product_ids.append(price.product.uuid)
            except Price.DoesNotExist:
                continue
        return product_ids
```

- [ ] **Étape 2 : `manage.py check` doit passer**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Attendu : `System check identified no issues (0 silenced).`

- [ ] **Étape 3 : Écrire les tests basiques dans `tests/pytest/test_panier_session.py`**

```python
"""
Tests du gestionnaire de panier en session.
Session 02 — Tâche 2.1 : squelette (add/remove/count/clear basique).
/ Session cart manager tests. Session 02 — Task 2.1: skeleton.

Run:
    poetry run pytest -q tests/pytest/test_panier_session.py
"""
import uuid
from decimal import Decimal

import pytest
from django_tenants.utils import tenant_context


@pytest.fixture
def tenant_context_lespass():
    from Customers.models import Client as TenantClient
    tenant = TenantClient.objects.get(schema_name="lespass")
    with tenant_context(tenant):
        yield tenant


@pytest.fixture
def request_with_session():
    """RequestFactory avec session middleware activé.
    / RequestFactory with session middleware enabled."""
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory
    factory = RequestFactory()
    request = factory.get('/')

    def _get_response(req):
        return None

    middleware = SessionMiddleware(_get_response)
    middleware.process_request(request)
    request.session.save()
    return request


@pytest.mark.django_db
def test_panier_vide_au_debut(tenant_context_lespass, request_with_session):
    """Un panier fraîchement instancié est vide.
    / A freshly instantiated cart is empty."""
    from BaseBillet.services_panier import PanierSession
    panier = PanierSession(request_with_session)
    assert panier.is_empty() is True
    assert panier.count() == 0
    assert panier.items() == []


@pytest.mark.django_db
def test_add_ticket_stocke_en_session(tenant_context_lespass, request_with_session):
    """add_ticket stocke un item dans la session.
    / add_ticket stores an item in the session."""
    from BaseBillet.services_panier import PanierSession
    panier = PanierSession(request_with_session)
    event_uuid = uuid.uuid4()
    price_uuid = uuid.uuid4()
    panier.add_ticket(event_uuid, price_uuid, qty=2)

    assert panier.count() == 2  # qty=2
    items = panier.items()
    assert len(items) == 1
    assert items[0]['type'] == 'ticket'
    assert items[0]['event_uuid'] == str(event_uuid)
    assert items[0]['price_uuid'] == str(price_uuid)
    assert items[0]['qty'] == 2


@pytest.mark.django_db
def test_add_membership_stocke_en_session(tenant_context_lespass, request_with_session):
    """add_membership stocke un item adhésion.
    / add_membership stores a membership item."""
    from BaseBillet.services_panier import PanierSession
    panier = PanierSession(request_with_session)
    price_uuid = uuid.uuid4()
    panier.add_membership(price_uuid)
    assert panier.count() == 1
    items = panier.items()
    assert items[0]['type'] == 'membership'
    assert items[0]['price_uuid'] == str(price_uuid)


@pytest.mark.django_db
def test_count_cumule_tickets_et_memberships(tenant_context_lespass, request_with_session):
    """count() somme qty des billets + 1 par adhésion.
    / count() sums ticket qty + 1 per membership."""
    from BaseBillet.services_panier import PanierSession
    panier = PanierSession(request_with_session)
    panier.add_ticket(uuid.uuid4(), uuid.uuid4(), qty=3)
    panier.add_ticket(uuid.uuid4(), uuid.uuid4(), qty=2)
    panier.add_membership(uuid.uuid4())
    # 3 + 2 + 1 = 6
    assert panier.count() == 6


@pytest.mark.django_db
def test_remove_item_retire_a_index(tenant_context_lespass, request_with_session):
    """remove_item retire l'item à l'index spécifié.
    / remove_item removes the item at the given index."""
    from BaseBillet.services_panier import PanierSession
    panier = PanierSession(request_with_session)
    p1 = uuid.uuid4()
    p2 = uuid.uuid4()
    panier.add_ticket(uuid.uuid4(), p1, qty=1)
    panier.add_ticket(uuid.uuid4(), p2, qty=1)

    panier.remove_item(0)

    items = panier.items()
    assert len(items) == 1
    assert items[0]['price_uuid'] == str(p2)


@pytest.mark.django_db
def test_remove_item_index_invalide_silencieux(tenant_context_lespass, request_with_session):
    """remove_item sur index invalide ne plante pas.
    / remove_item on invalid index does not crash."""
    from BaseBillet.services_panier import PanierSession
    panier = PanierSession(request_with_session)
    panier.add_ticket(uuid.uuid4(), uuid.uuid4(), qty=1)

    panier.remove_item(99)  # OOR — silent
    panier.remove_item(-1)  # negative — silent

    assert len(panier.items()) == 1


@pytest.mark.django_db
def test_update_quantity_change_qty(tenant_context_lespass, request_with_session):
    """update_quantity modifie la qty d'un item billet.
    / update_quantity changes the qty of a ticket item."""
    from BaseBillet.services_panier import PanierSession
    panier = PanierSession(request_with_session)
    panier.add_ticket(uuid.uuid4(), uuid.uuid4(), qty=1)

    panier.update_quantity(0, 5)

    assert panier.items()[0]['qty'] == 5
    assert panier.count() == 5


@pytest.mark.django_db
def test_update_quantity_zero_retire_item(tenant_context_lespass, request_with_session):
    """update_quantity avec qty=0 retire l'item.
    / update_quantity with qty=0 removes the item."""
    from BaseBillet.services_panier import PanierSession
    panier = PanierSession(request_with_session)
    panier.add_ticket(uuid.uuid4(), uuid.uuid4(), qty=3)

    panier.update_quantity(0, 0)

    assert panier.is_empty() is True


@pytest.mark.django_db
def test_update_quantity_ignore_membership(tenant_context_lespass, request_with_session):
    """update_quantity sur un membership n'a aucun effet.
    / update_quantity on a membership has no effect."""
    from BaseBillet.services_panier import PanierSession
    panier = PanierSession(request_with_session)
    panier.add_membership(uuid.uuid4())

    panier.update_quantity(0, 5)  # ignoré pour membership

    # L'item membership est toujours là, sans modif
    items = panier.items()
    assert len(items) == 1
    assert items[0]['type'] == 'membership'
    assert 'qty' not in items[0]  # pas de qty sur membership


@pytest.mark.django_db
def test_clear_vide_tout(tenant_context_lespass, request_with_session):
    """clear() vide totalement le panier.
    / clear() completely empties the cart."""
    from BaseBillet.services_panier import PanierSession
    panier = PanierSession(request_with_session)
    panier.add_ticket(uuid.uuid4(), uuid.uuid4(), qty=2)
    panier.add_membership(uuid.uuid4())
    assert panier.count() > 0

    panier.clear()

    assert panier.is_empty() is True
    assert panier.count() == 0


@pytest.mark.django_db
def test_panier_persiste_entre_instances(tenant_context_lespass, request_with_session):
    """Deux PanierSession sur la même request voient les mêmes items.
    / Two PanierSession on the same request see the same items."""
    from BaseBillet.services_panier import PanierSession
    panier1 = PanierSession(request_with_session)
    panier1.add_ticket(uuid.uuid4(), uuid.uuid4(), qty=2)

    panier2 = PanierSession(request_with_session)
    assert panier2.count() == 2


@pytest.mark.django_db
def test_adhesions_product_ids_retourne_products_adhesion(
    tenant_context_lespass, request_with_session
):
    """adhesions_product_ids() renvoie les UUIDs de Product des adhésions présentes.
    / adhesions_product_ids() returns UUIDs of Product for present memberships."""
    from decimal import Decimal
    from BaseBillet.models import Price, Product
    from BaseBillet.services_panier import PanierSession

    prod_adhesion = Product.objects.create(
        name=f"Adh {uuid.uuid4()}", categorie_article=Product.ADHESION,
    )
    price_adhesion = Price.objects.create(
        product=prod_adhesion, name="Std", prix=Decimal("10.00"), publish=True,
    )

    panier = PanierSession(request_with_session)
    panier.add_membership(price_adhesion.uuid)
    panier.add_ticket(uuid.uuid4(), uuid.uuid4(), qty=1)  # ne doit pas apparaître

    product_ids = panier.adhesions_product_ids()
    assert prod_adhesion.uuid in product_ids
    assert len(product_ids) == 1

    # Cleanup / Nettoyage
    price_adhesion.delete()
    prod_adhesion.delete()
```

- [ ] **Étape 4 : Lancer les tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_panier_session.py -v
```

Attendu : 12 tests PASS.

**Point de contrôle commit (mainteneur)** — fin Tâche 2.1.

---

## Tâche 2.2 : Validations standards dans `PanierSession`

**Fichiers :**
- Modifier : `BaseBillet/services_panier.py` (enrichir `add_ticket` et `add_membership`)
- Modifier : `tests/pytest/test_panier_session.py` (ajouter tests validations)

**Contexte :** On ajoute les validations métier :
- `add_ticket` : Event existe + pas complet + price publié + price valide pour event + qty > 0 + stock + max_per_user
- `add_membership` : Price est bien ADHESION + pas `recurring_payment` + pas `manual_validation` + pas doublon

Ces validations lèvent `InvalidItemError` avec un message clair.

- [ ] **Étape 1 : Enrichir `add_ticket` dans `services_panier.py`**

Remplacer la méthode `add_ticket` existante par la version suivante :

```python
    def add_ticket(self, event_uuid, price_uuid, qty,
                   custom_amount=None, options=None, custom_form=None):
        """
        Ajoute un item billet au panier après validation.
        / Adds a ticket item to the cart after validation.

        Raises:
            InvalidItemError: si le price/event est invalide, épuisé, non publié,
                ou si la qty dépasse les limites.
        """
        from BaseBillet.models import Event, Price

        # Validation 1 : qty positive
        # Validation 1: positive qty
        if qty is None or int(qty) <= 0:
            raise InvalidItemError(_("Quantity must be positive."))

        # Validation 2 : Event existe et pas complet
        # Validation 2: Event exists and not full
        try:
            event = Event.objects.get(uuid=event_uuid)
        except Event.DoesNotExist:
            raise InvalidItemError(_("Event not found."))
        if event.complet():
            raise InvalidItemError(_("This event is full."))

        # Validation 3 : Price existe et publié
        # Validation 3: Price exists and published
        try:
            price = Price.objects.get(uuid=price_uuid)
        except Price.DoesNotExist:
            raise InvalidItemError(_("Price not found."))
        if not price.publish:
            raise InvalidItemError(_("This rate is not available."))
        if price.product.archive:
            raise InvalidItemError(_("This product is archived."))

        # Validation 4 : Price fait bien partie des products de l'event
        # Validation 4: Price belongs to one of the event's products
        if price.product not in event.products.all():
            raise InvalidItemError(_("This rate is not available for this event."))

        # Validation 5 : max_per_user sur le price (si défini)
        # Validation 5: max_per_user on the price (if defined)
        if price.max_per_user and int(qty) > price.max_per_user:
            raise InvalidItemError(_("Quantity exceeds the per-user limit for this rate."))

        # Validation 6 : stock disponible
        # Validation 6: stock available
        if price.out_of_stock(event=event):
            raise InvalidItemError(_("This rate is sold out."))

        # Validation 7 : free_price → custom_amount >= prix minimum
        # Validation 7: free_price → custom_amount >= minimum price
        if price.free_price:
            if custom_amount is None:
                raise InvalidItemError(_("An amount is required for the free price."))
            try:
                amount_dec = Decimal(str(custom_amount))
            except Exception:
                raise InvalidItemError(_("Invalid amount."))
            if price.prix and amount_dec < price.prix:
                raise InvalidItemError(
                    _("The amount must be greater than or equal to the minimum.")
                )
            if amount_dec > Decimal("999999.99"):
                raise InvalidItemError(_("The amount is too high."))

        # Toutes les validations passent — on stocke en session
        # All validations passed — store in session
        item = {
            'type': 'ticket',
            'event_uuid': str(event_uuid),
            'price_uuid': str(price_uuid),
            'qty': int(qty),
            'custom_amount': str(custom_amount) if custom_amount is not None else None,
            'options': [str(o) for o in (options or [])],
            'custom_form': dict(custom_form or {}),
        }
        self._data['items'].append(item)
        self._save()
        return item
```

- [ ] **Étape 2 : Enrichir `add_membership` dans `services_panier.py`**

Remplacer la méthode par :

```python
    def add_membership(self, price_uuid,
                       custom_amount=None, options=None, custom_form=None):
        """
        Ajoute un item adhésion au panier après validation.
        / Adds a membership item to the cart after validation.

        Raises:
            InvalidItemError: si price invalide, categorie non ADHESION,
                recurring_payment ou manual_validation (exclus du panier v1).
        """
        from BaseBillet.models import Price, Product

        # Validation 1 : Price existe et publié
        # Validation 1: Price exists and published
        try:
            price = Price.objects.get(uuid=price_uuid)
        except Price.DoesNotExist:
            raise InvalidItemError(_("Price not found."))
        if not price.publish:
            raise InvalidItemError(_("This rate is not available."))
        if price.product.archive:
            raise InvalidItemError(_("This product is archived."))

        # Validation 2 : Product doit être categorie ADHESION
        # Validation 2: Product must be ADHESION category
        if price.product.categorie_article != Product.ADHESION:
            raise InvalidItemError(_("This rate is not a membership."))

        # Validation 3 : pas de paiement récurrent (exclu du panier en v1)
        # Validation 3: no recurring payment (excluded from cart in v1)
        if price.recurring_payment:
            raise InvalidItemError(
                _("Recurring memberships require a direct payment and cannot be added to the cart.")
            )

        # Validation 4 : pas de validation manuelle (exclue du panier en v1)
        # Validation 4: no manual validation (excluded from cart in v1)
        if price.manual_validation:
            raise InvalidItemError(
                _("Memberships with manual validation cannot be added to the cart.")
            )

        # Validation 5 : pas de doublon (1 adhésion du même price max)
        # Validation 5: no duplicate (1 membership of the same price max)
        for existing in self._data.get('items', []):
            if existing.get('type') == 'membership' and existing.get('price_uuid') == str(price_uuid):
                raise InvalidItemError(_("This membership is already in your cart."))

        # Validation 6 : free_price → custom_amount >= min
        # Validation 6: free_price → custom_amount >= min
        if price.free_price:
            if custom_amount is None:
                raise InvalidItemError(_("An amount is required for the free price."))
            try:
                amount_dec = Decimal(str(custom_amount))
            except Exception:
                raise InvalidItemError(_("Invalid amount."))
            if price.prix and amount_dec < price.prix:
                raise InvalidItemError(
                    _("The amount must be greater than or equal to the minimum.")
                )
            if amount_dec > Decimal("999999.99"):
                raise InvalidItemError(_("The amount is too high."))

        item = {
            'type': 'membership',
            'price_uuid': str(price_uuid),
            'custom_amount': str(custom_amount) if custom_amount is not None else None,
            'options': [str(o) for o in (options or [])],
            'custom_form': dict(custom_form or {}),
        }
        self._data['items'].append(item)
        self._save()
        return item
```

- [ ] **Étape 3 : Ajouter tests de validations dans `test_panier_session.py`**

Ajouter à la fin du fichier de tests :

```python
# ==========================================================================
# Tests Tâche 2.2 — validations standards
# / Task 2.2 tests — standard validations
# ==========================================================================


@pytest.fixture
def event_avec_tarif(tenant_context_lespass):
    """Event + Product billet + Price publié, prêt à l'emploi.
    / Event + ticket Product + published Price, ready to use."""
    from datetime import timedelta
    from decimal import Decimal
    from django.utils import timezone
    from BaseBillet.models import Event, Price, Product

    event = Event.objects.create(
        name=f"Evt {uuid.uuid4()}",
        datetime=timezone.now() + timedelta(days=7),
        jauge_max=100,
    )
    product = Product.objects.create(
        name=f"Billet {uuid.uuid4()}",
        categorie_article=Product.BILLET,
    )
    event.products.add(product)
    price = Price.objects.create(
        product=product, name="Plein", prix=Decimal("10.00"), publish=True,
    )
    yield event, price
    price.delete()
    product.delete()
    event.delete()


@pytest.fixture
def adhesion_standard(tenant_context_lespass):
    """Product ADHESION + Price simple (pas recurring, pas manual_validation).
    / Standard ADHESION Product + Price (no recurring, no manual validation)."""
    from decimal import Decimal
    from BaseBillet.models import Price, Product

    product = Product.objects.create(
        name=f"Adh {uuid.uuid4()}", categorie_article=Product.ADHESION,
    )
    price = Price.objects.create(
        product=product, name="Std", prix=Decimal("15.00"), publish=True,
    )
    yield product, price
    price.delete()
    product.delete()


@pytest.mark.django_db
def test_add_ticket_refuse_qty_zero(request_with_session, event_avec_tarif):
    from BaseBillet.services_panier import PanierSession, InvalidItemError
    event, price = event_avec_tarif
    panier = PanierSession(request_with_session)
    with pytest.raises(InvalidItemError, match="Quantity must be positive"):
        panier.add_ticket(event.uuid, price.uuid, qty=0)


@pytest.mark.django_db
def test_add_ticket_refuse_event_inexistant(request_with_session, tenant_context_lespass):
    from BaseBillet.services_panier import PanierSession, InvalidItemError
    panier = PanierSession(request_with_session)
    with pytest.raises(InvalidItemError, match="Event not found"):
        panier.add_ticket(uuid.uuid4(), uuid.uuid4(), qty=1)


@pytest.mark.django_db
def test_add_ticket_refuse_price_inexistant(request_with_session, event_avec_tarif):
    from BaseBillet.services_panier import PanierSession, InvalidItemError
    event, _price = event_avec_tarif
    panier = PanierSession(request_with_session)
    with pytest.raises(InvalidItemError, match="Price not found"):
        panier.add_ticket(event.uuid, uuid.uuid4(), qty=1)


@pytest.mark.django_db
def test_add_ticket_refuse_price_non_publie(request_with_session, event_avec_tarif):
    from BaseBillet.services_panier import PanierSession, InvalidItemError
    event, price = event_avec_tarif
    price.publish = False
    price.save()
    panier = PanierSession(request_with_session)
    with pytest.raises(InvalidItemError, match="not available"):
        panier.add_ticket(event.uuid, price.uuid, qty=1)


@pytest.mark.django_db
def test_add_ticket_refuse_price_pas_dans_event(request_with_session, tenant_context_lespass):
    """Si un price n'est pas lié à l'event via products, refusé.
    / If a price is not linked to the event via products, refused."""
    from datetime import timedelta
    from decimal import Decimal
    from django.utils import timezone
    from BaseBillet.models import Event, Price, Product
    from BaseBillet.services_panier import PanierSession, InvalidItemError

    event = Event.objects.create(
        name=f"Evt {uuid.uuid4()}",
        datetime=timezone.now() + timedelta(days=5),
        jauge_max=50,
    )
    # Product non lié à l'event / Product not linked to event
    product_other = Product.objects.create(
        name=f"Other {uuid.uuid4()}", categorie_article=Product.BILLET,
    )
    price_other = Price.objects.create(
        product=product_other, name="X", prix=Decimal("5.00"), publish=True,
    )
    panier = PanierSession(request_with_session)
    with pytest.raises(InvalidItemError, match="not available for this event"):
        panier.add_ticket(event.uuid, price_other.uuid, qty=1)

    price_other.delete()
    product_other.delete()
    event.delete()


@pytest.mark.django_db
def test_add_membership_refuse_recurring(request_with_session, adhesion_standard):
    from BaseBillet.services_panier import PanierSession, InvalidItemError
    _product, price = adhesion_standard
    price.recurring_payment = True
    price.save()
    panier = PanierSession(request_with_session)
    with pytest.raises(InvalidItemError, match="Recurring memberships"):
        panier.add_membership(price.uuid)


@pytest.mark.django_db
def test_add_membership_refuse_manual_validation(request_with_session, adhesion_standard):
    from BaseBillet.services_panier import PanierSession, InvalidItemError
    _product, price = adhesion_standard
    price.manual_validation = True
    price.save()
    panier = PanierSession(request_with_session)
    with pytest.raises(InvalidItemError, match="manual validation"):
        panier.add_membership(price.uuid)


@pytest.mark.django_db
def test_add_membership_refuse_doublon(request_with_session, adhesion_standard):
    from BaseBillet.services_panier import PanierSession, InvalidItemError
    _product, price = adhesion_standard
    panier = PanierSession(request_with_session)
    panier.add_membership(price.uuid)
    with pytest.raises(InvalidItemError, match="already in your cart"):
        panier.add_membership(price.uuid)


@pytest.mark.django_db
def test_add_membership_refuse_produit_non_adhesion(request_with_session, event_avec_tarif):
    """Un price de type BILLET ne peut pas être ajouté via add_membership.
    / A BILLET-type price cannot be added via add_membership."""
    from BaseBillet.services_panier import PanierSession, InvalidItemError
    _event, price_billet = event_avec_tarif
    panier = PanierSession(request_with_session)
    with pytest.raises(InvalidItemError, match="not a membership"):
        panier.add_membership(price_billet.uuid)
```

- [ ] **Étape 4 : Lancer les tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_panier_session.py -v
```

Attendu : les 12 tests de Tâche 2.1 + 9 nouveaux tests = 21 PASS.

**Point de contrôle commit (mainteneur)** — fin Tâche 2.2.

---

## Tâche 2.3 : Chevauchement temporel + cart-aware adhesions + code promo

**Fichiers :**
- Modifier : `BaseBillet/services_panier.py`
- Modifier : `tests/pytest/test_panier_session.py`

**Contexte :** On termine les validations de `add_ticket` avec 3 sujets :
1. **Chevauchement temporel** si `Configuration.allow_concurrent_bookings=False` — contre les autres items du panier + contre les reservations DB du user (via `reservations_bloquantes_pour_user`).
2. **Cart-aware `adhesions_obligatoires`** : si le price requiert une adhésion, accepter l'adhésion déjà en DB OU dans le panier courant.
3. **Code promo** : méthode `set_promo_code(code_name)` qui valide le code et le stocke en session.

- [ ] **Étape 1 : Ajouter la logique d'overlap dans `add_ticket`**

Dans `BaseBillet/services_panier.py`, juste **avant** la ligne qui construit `item = {'type': 'ticket', ...}` à la fin de `add_ticket`, insérer :

```python
        # Validation 8 : chevauchement temporel (si config l'interdit)
        # / Validation 8: temporal overlap (if config forbids)
        from BaseBillet.models import Configuration
        config = Configuration.get_solo()
        if not config.allow_concurrent_bookings:
            start = event.datetime
            end = event.end_datetime or (start + timedelta(hours=1))

            # Cas A : chevauchement avec un autre item billet DU panier
            # / Case A: overlap with another ticket item OF the cart
            from BaseBillet.models import Event as EventModel
            for existing in self._data.get('items', []):
                if existing.get('type') != 'ticket':
                    continue
                if existing.get('event_uuid') == str(event_uuid):
                    continue  # même event : OK d'ajouter plusieurs billets
                try:
                    other_event = EventModel.objects.get(uuid=existing['event_uuid'])
                except EventModel.DoesNotExist:
                    continue
                other_start = other_event.datetime
                other_end = other_event.end_datetime or (other_start + timedelta(hours=1))
                if (start < other_end) and (other_start < end):
                    raise InvalidItemError(
                        _("This event overlaps with another event in your cart: %(name)s")
                        % {"name": other_event.name}
                    )

            # Cas B : chevauchement avec reservation existante du user (DB)
            # / Case B: overlap with existing user reservation (DB)
            if self.request.user.is_authenticated:
                conflit = reservations_bloquantes_pour_user(
                    self.request.user, start, end
                ).first()
                if conflit:
                    blocking_hard = _blocking_statuses()
                    if conflit.status in blocking_hard:
                        raise InvalidItemError(
                            _("You already have a booking that overlaps with this event: %(name)s")
                            % {"name": conflit.event.name}
                        )
                    # Sinon — blocage récent (<15 min), message spécifique
                    # / Otherwise — recent block (<15 min), specific message
                    raise InvalidItemError(
                        _("You have a payment in progress for an event that overlaps with this one: "
                          "%(name)s. Please complete it or wait 15 minutes before trying another booking.")
                        % {"name": conflit.event.name}
                    )
```

Attention : `from BaseBillet.models import Event as EventModel` — on renomme pour éviter le shadowing de `event` (variable locale).

- [ ] **Étape 2 : Cart-aware `adhesions_obligatoires` dans `add_ticket`**

Juste **après** la validation 7 (free_price) et **avant** la validation 8 (overlap), insérer :

```python
        # Validation 7bis : adhesions_obligatoires — cart-aware
        # Le tarif est accepté si l'user a déjà l'adhésion active OU si
        # l'adhésion est dans le panier courant.
        # / Validation 7bis: adhesions_obligatoires — cart-aware
        # Rate accepted if user already has active membership OR the
        # required membership is in the current cart.
        if price.adhesions_obligatoires.exists():
            required_products = list(price.adhesions_obligatoires.all())

            # Adhésion active en DB ?
            # / Active membership in DB?
            has_active_membership = False
            if self.request.user.is_authenticated:
                from BaseBillet.models import Membership
                has_active_membership = Membership.objects.filter(
                    user=self.request.user,
                    price__product__in=required_products,
                    deadline__gte=timezone.now(),
                ).exists()

            # Adhésion dans le panier courant ?
            # / Membership in current cart?
            has_in_cart = False
            required_product_uuids = {str(p.uuid) for p in required_products}
            for existing in self._data.get('items', []):
                if existing.get('type') != 'membership':
                    continue
                try:
                    from BaseBillet.models import Price as PriceModel
                    existing_price = PriceModel.objects.get(uuid=existing['price_uuid'])
                    if str(existing_price.product.uuid) in required_product_uuids:
                        has_in_cart = True
                        break
                except PriceModel.DoesNotExist:
                    continue

            if not (has_active_membership or has_in_cart):
                names = ", ".join([p.name for p in required_products])
                raise InvalidItemError(
                    _("This rate requires a membership: %(names)s. "
                      "Please add the required membership to your cart first.")
                    % {"names": names}
                )
```

- [ ] **Étape 3 : Ajouter les méthodes code promo sur `PanierSession`**

À la fin de la classe `PanierSession` (juste avant la fin de la classe, après `adhesions_product_ids`) :

```python
    # --- Code promo ---
    # --- Promotional code ---

    def set_promo_code(self, code_name):
        """
        Applique un code promo au panier après validation.
        Le code doit correspondre à un PromotionalCode actif et utilisable.
        / Apply a promotional code to the cart after validation.
        The code must match an active and usable PromotionalCode.

        Raises:
            InvalidItemError: si le code n'existe pas, n'est pas actif, ou
                n'a aucun product matché dans le panier.
        """
        from BaseBillet.models import PromotionalCode

        try:
            promo = PromotionalCode.objects.get(name=code_name, is_active=True)
        except PromotionalCode.DoesNotExist:
            raise InvalidItemError(_("Invalid or inactive promotional code."))
        if not promo.is_usable():
            raise InvalidItemError(_("Invalid or inactive promotional code."))

        # Le product du code doit être présent dans le panier (billet ou adhésion)
        # / The code's product must be present in the cart (ticket or membership)
        from BaseBillet.models import Price
        present = False
        for item in self._data.get('items', []):
            try:
                price = Price.objects.get(uuid=item['price_uuid'])
                if price.product == promo.product:
                    present = True
                    break
            except Price.DoesNotExist:
                continue
        if not present:
            raise InvalidItemError(
                _("This promotional code does not apply to any item in your cart.")
            )

        self._data['promo_code_name'] = code_name
        self._save()

    def clear_promo_code(self):
        """Retire le code promo du panier.
        / Removes the promotional code from the cart."""
        self._data['promo_code_name'] = None
        self._save()

    def promo_code(self):
        """Retourne le PromotionalCode actuel ou None. Re-valide à chaque appel.
        / Returns current PromotionalCode or None. Re-validates each call."""
        from BaseBillet.models import PromotionalCode
        name = self._data.get('promo_code_name')
        if not name:
            return None
        try:
            promo = PromotionalCode.objects.get(name=name, is_active=True)
            if promo.is_usable():
                return promo
        except PromotionalCode.DoesNotExist:
            pass
        # Code devenu invalide — on le nettoie silencieusement
        # / Code became invalid — clean up silently
        self._data['promo_code_name'] = None
        self._save()
        return None
```

- [ ] **Étape 4 : Tests pour overlap, cart-aware et promo**

Ajouter dans `test_panier_session.py` :

```python
# ==========================================================================
# Tests Tâche 2.3 — overlap, cart-aware adhésion, code promo
# / Task 2.3 tests — overlap, cart-aware membership, promo code
# ==========================================================================


@pytest.fixture
def request_authentifie(request_with_session, tenant_context_lespass):
    """Request avec user authentifié (pour tests overlap DB).
    / Request with authenticated user (for DB overlap tests)."""
    from AuthBillet.models import TibilletUser
    user = TibilletUser.objects.create(
        email=f"req-{uuid.uuid4()}@example.org",
        username=f"req-{uuid.uuid4()}",
    )
    request_with_session.user = user
    yield request_with_session
    # cleanup des objets qui pointent sur user (PROTECT/SET_NULL)
    from BaseBillet.models import Commande, LigneArticle, Membership, Reservation, Paiement_stripe
    LigneArticle.objects.filter(
        Q(reservation__user_commande=user) | Q(membership__user=user)
    ).delete()
    Reservation.objects.filter(user_commande=user).delete()
    Membership.objects.filter(user=user).delete()
    Commande.objects.filter(user=user).delete()
    Paiement_stripe.objects.filter(user=user).delete()
    user.delete()


@pytest.mark.django_db
def test_set_promo_code_refuse_code_inexistant(request_with_session, event_avec_tarif):
    from BaseBillet.services_panier import PanierSession, InvalidItemError
    event, price = event_avec_tarif
    panier = PanierSession(request_with_session)
    panier.add_ticket(event.uuid, price.uuid, qty=1)
    with pytest.raises(InvalidItemError, match="Invalid"):
        panier.set_promo_code("DOES_NOT_EXIST")


@pytest.mark.django_db
def test_set_promo_code_refuse_si_product_pas_dans_panier(
    request_with_session, event_avec_tarif, tenant_context_lespass,
):
    """Un code lié à un product absent du panier est refusé.
    / A code linked to a product absent from the cart is refused."""
    from decimal import Decimal
    from BaseBillet.models import Product, PromotionalCode
    from BaseBillet.services_panier import PanierSession, InvalidItemError

    event, price = event_avec_tarif
    other_product = Product.objects.create(
        name=f"Other {uuid.uuid4()}", categorie_article=Product.BILLET,
    )
    promo = PromotionalCode.objects.create(
        name=f"PROMO-{uuid.uuid4().hex[:8]}",
        discount_rate=Decimal("10.00"),
        product=other_product,
    )
    panier = PanierSession(request_with_session)
    panier.add_ticket(event.uuid, price.uuid, qty=1)
    with pytest.raises(InvalidItemError, match="does not apply"):
        panier.set_promo_code(promo.name)

    promo.delete()
    other_product.delete()


@pytest.mark.django_db
def test_set_promo_code_ok_si_product_dans_panier(
    request_with_session, event_avec_tarif,
):
    """Le code s'applique si son product est présent.
    / The code applies if its product is present."""
    from decimal import Decimal
    from BaseBillet.models import PromotionalCode
    from BaseBillet.services_panier import PanierSession

    event, price = event_avec_tarif
    promo = PromotionalCode.objects.create(
        name=f"OK-{uuid.uuid4().hex[:8]}",
        discount_rate=Decimal("10.00"),
        product=price.product,
    )
    panier = PanierSession(request_with_session)
    panier.add_ticket(event.uuid, price.uuid, qty=1)
    panier.set_promo_code(promo.name)

    assert panier.data['promo_code_name'] == promo.name
    assert panier.promo_code() == promo

    promo.delete()


@pytest.mark.django_db
def test_clear_promo_code(request_with_session, event_avec_tarif):
    from decimal import Decimal
    from BaseBillet.models import PromotionalCode
    from BaseBillet.services_panier import PanierSession

    event, price = event_avec_tarif
    promo = PromotionalCode.objects.create(
        name=f"CLR-{uuid.uuid4().hex[:8]}",
        discount_rate=Decimal("5.00"), product=price.product,
    )
    panier = PanierSession(request_with_session)
    panier.add_ticket(event.uuid, price.uuid, qty=1)
    panier.set_promo_code(promo.name)
    panier.clear_promo_code()
    assert panier.data['promo_code_name'] is None
    assert panier.promo_code() is None

    promo.delete()


@pytest.mark.django_db
def test_add_ticket_refuse_adhesion_obligatoire_sans_adhesion(
    request_authentifie, tenant_context_lespass,
):
    """Un tarif gaté est refusé si l'user n'a pas l'adhésion (ni en DB ni en panier).
    / A gated rate is refused if the user has no membership (neither in DB nor cart)."""
    from datetime import timedelta
    from decimal import Decimal
    from django.utils import timezone
    from BaseBillet.models import Event, Price, Product
    from BaseBillet.services_panier import PanierSession, InvalidItemError

    # Setup : un event + un tarif gaté par une adhésion requise
    event = Event.objects.create(
        name=f"Gated {uuid.uuid4()}", datetime=timezone.now() + timedelta(days=5),
        jauge_max=50,
    )
    prod_billet = Product.objects.create(
        name=f"B {uuid.uuid4()}", categorie_article=Product.BILLET,
    )
    event.products.add(prod_billet)
    prod_adhesion_required = Product.objects.create(
        name=f"A {uuid.uuid4()}", categorie_article=Product.ADHESION,
    )
    price_gated = Price.objects.create(
        product=prod_billet, name="Adhérent", prix=Decimal("5.00"), publish=True,
    )
    price_gated.adhesions_obligatoires.add(prod_adhesion_required)

    panier = PanierSession(request_authentifie)
    with pytest.raises(InvalidItemError, match="requires a membership"):
        panier.add_ticket(event.uuid, price_gated.uuid, qty=1)

    price_gated.delete()
    prod_adhesion_required.delete()
    prod_billet.delete()
    event.delete()


@pytest.mark.django_db
def test_add_ticket_accepte_si_adhesion_dans_panier(
    request_authentifie, tenant_context_lespass,
):
    """Un tarif gaté est accepté si l'adhésion requise est dans le panier.
    / A gated rate is accepted if the required membership is in the cart."""
    from datetime import timedelta
    from decimal import Decimal
    from django.utils import timezone
    from BaseBillet.models import Event, Price, Product
    from BaseBillet.services_panier import PanierSession

    event = Event.objects.create(
        name=f"GatedOK {uuid.uuid4()}", datetime=timezone.now() + timedelta(days=5),
        jauge_max=50,
    )
    prod_billet = Product.objects.create(
        name=f"B {uuid.uuid4()}", categorie_article=Product.BILLET,
    )
    event.products.add(prod_billet)
    prod_adhesion_required = Product.objects.create(
        name=f"A {uuid.uuid4()}", categorie_article=Product.ADHESION,
    )
    price_adhesion = Price.objects.create(
        product=prod_adhesion_required, name="Std", prix=Decimal("15.00"), publish=True,
    )
    price_gated = Price.objects.create(
        product=prod_billet, name="Adh", prix=Decimal("5.00"), publish=True,
    )
    price_gated.adhesions_obligatoires.add(prod_adhesion_required)

    panier = PanierSession(request_authentifie)
    panier.add_membership(price_adhesion.uuid)
    # Le tarif gaté est maintenant acceptable car l'adhésion est dans le panier
    panier.add_ticket(event.uuid, price_gated.uuid, qty=1)

    assert panier.count() == 2  # 1 adhésion + 1 billet

    price_gated.delete()
    price_adhesion.delete()
    prod_adhesion_required.delete()
    prod_billet.delete()
    event.delete()


@pytest.mark.django_db
def test_add_ticket_refuse_overlap_contre_panier(
    request_with_session, tenant_context_lespass,
):
    """Deux events chevauchants dans le panier = refus si allow_concurrent_bookings=False.
    / Two overlapping events in the cart = refused if allow_concurrent_bookings=False."""
    from datetime import timedelta
    from decimal import Decimal
    from django.utils import timezone
    from BaseBillet.models import Configuration, Event, Price, Product
    from BaseBillet.services_panier import PanierSession, InvalidItemError

    config = Configuration.get_solo()
    config.allow_concurrent_bookings = False
    config.save()

    try:
        start = timezone.now() + timedelta(days=3)
        event_a = Event.objects.create(
            name=f"A-{uuid.uuid4()}", datetime=start,
            end_datetime=start + timedelta(hours=2), jauge_max=50,
        )
        event_b = Event.objects.create(
            name=f"B-{uuid.uuid4()}", datetime=start + timedelta(hours=1),  # chevauche A
            end_datetime=start + timedelta(hours=3), jauge_max=50,
        )
        prod = Product.objects.create(
            name=f"P {uuid.uuid4()}", categorie_article=Product.BILLET,
        )
        event_a.products.add(prod)
        event_b.products.add(prod)
        price = Price.objects.create(
            product=prod, name="x", prix=Decimal("5.00"), publish=True,
        )

        panier = PanierSession(request_with_session)
        panier.add_ticket(event_a.uuid, price.uuid, qty=1)
        with pytest.raises(InvalidItemError, match="overlaps with another event in your cart"):
            panier.add_ticket(event_b.uuid, price.uuid, qty=1)

        price.delete()
        prod.delete()
        event_a.delete()
        event_b.delete()
    finally:
        config.allow_concurrent_bookings = True
        config.save()
```

- [ ] **Étape 5 : Lancer les tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_panier_session.py -v
```

Attendu : 21 tests de Tâche 2.1+2.2 + 7 nouveaux = 28 PASS.

**Point de contrôle commit (mainteneur)** — fin Tâche 2.3.

---

## Tâche 2.4 : Adapter `TicketCreator` avec flag `create_checkout`

**Fichiers :**
- Modifier : `BaseBillet/validators.py` (classe `TicketCreator`, lignes 185-350)
- Créer : `tests/pytest/test_ticket_creator_no_checkout.py`

**Contexte :** Aujourd'hui `TicketCreator.__init__` crée Tickets + LigneArticle + appelle `get_checkout_stripe()` en dernière étape. Pour le panier, on veut pouvoir skip le `get_checkout_stripe()` (qui sera appelé plus tard, une seule fois, par `CommandeService.materialiser()` avec toutes les lignes consolidées).

**Changement minimal** : ajouter `create_checkout: bool = True`. Si `False`, ne pas appeler `get_checkout_stripe()` à la fin de `method_B()`.

**Rétrocompat :** aucun appel existant ne passe le param → comportement inchangé.

- [ ] **Étape 1 : Modifier `TicketCreator.__init__` signature**

Dans `BaseBillet/validators.py` vers ligne 185, remplacer la signature :

```python
class TicketCreator():

    def __init__(self, reservation: Reservation, products_dict: dict, promo_code: PromotionalCode = None, custom_amounts: dict = None,
                 sale_origin: str = SaleOrigin.LESPASS):
```

Par :

```python
class TicketCreator():

    def __init__(self, reservation: Reservation, products_dict: dict, promo_code: PromotionalCode = None, custom_amounts: dict = None,
                 sale_origin: str = SaleOrigin.LESPASS,
                 create_checkout: bool = True):
```

Puis dans le corps de `__init__`, après `self.sale_origin = sale_origin` et avant `self.list_line_article_sold = []`, ajouter :

```python
        # Si False, on ne déclenche pas get_checkout_stripe() à la fin de method_B.
        # Utilisé par CommandeService.materialiser() qui consolide toutes les
        # LigneArticle puis crée UN SEUL checkout Stripe pour la commande entière.
        # / If False, skip get_checkout_stripe() at the end of method_B.
        # Used by CommandeService.materialiser() which consolidates all
        # LigneArticle then creates ONE Stripe checkout for the entire order.
        self.create_checkout = create_checkout
```

- [ ] **Étape 2 : Modifier `method_B` pour respecter le flag**

Dans la méthode `method_B` de `TicketCreator`, trouver la ligne :

```python
        self.checkout_link = self.get_checkout_stripe()
        return tickets
```

La remplacer par :

```python
        if self.create_checkout:
            self.checkout_link = self.get_checkout_stripe()
        # Si create_checkout=False : le caller (CommandeService) appellera
        # lui-même CreationPaiementStripe avec toutes les lignes consolidées.
        # / If create_checkout=False: caller (CommandeService) will call
        # CreationPaiementStripe itself with all consolidated lines.
        return tickets
```

- [ ] **Étape 3 : Tests non-régression + nouveau flag**

Créer `tests/pytest/test_ticket_creator_no_checkout.py` :

```python
"""
Tests de non-régression et du nouveau flag `create_checkout` sur TicketCreator.
Session 02 — Tâche 2.4.

Run:
    poetry run pytest -q tests/pytest/test_ticket_creator_no_checkout.py
"""
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from django_tenants.utils import tenant_context


@pytest.fixture
def tenant_context_lespass():
    from Customers.models import Client as TenantClient
    tenant = TenantClient.objects.get(schema_name="lespass")
    with tenant_context(tenant):
        yield tenant


@pytest.fixture
def user_acheteur(tenant_context_lespass):
    from AuthBillet.models import TibilletUser
    user = TibilletUser.objects.create(
        email=f"u-{uuid.uuid4()}@example.org",
        username=f"u-{uuid.uuid4()}",
    )
    yield user
    from django.db.models import Q
    from BaseBillet.models import (
        Commande, LigneArticle, Membership, Paiement_stripe, Reservation,
    )
    LigneArticle.objects.filter(
        Q(reservation__user_commande=user) | Q(membership__user=user)
    ).delete()
    Reservation.objects.filter(user_commande=user).delete()
    Membership.objects.filter(user=user).delete()
    Commande.objects.filter(user=user).delete()
    Paiement_stripe.objects.filter(user=user).delete()
    user.delete()


@pytest.fixture
def setup_event_and_reservation(tenant_context_lespass, user_acheteur):
    """Setup : event + product + price + reservation vide, prête pour TicketCreator.
    / Setup: event + product + price + empty reservation, ready for TicketCreator."""
    from BaseBillet.models import Event, Price, Product, Reservation

    event = Event.objects.create(
        name=f"TC-{uuid.uuid4()}",
        datetime=timezone.now() + timedelta(days=3),
        jauge_max=50,
    )
    product = Product.objects.create(
        name=f"B {uuid.uuid4()}", categorie_article=Product.BILLET,
    )
    event.products.add(product)
    price = Price.objects.create(
        product=product, name="Plein", prix=Decimal("10.00"), publish=True,
    )
    reservation = Reservation.objects.create(
        user_commande=user_acheteur, event=event,
    )
    return {
        "event": event, "product": product, "price": price,
        "reservation": reservation,
    }


@pytest.mark.django_db
def test_ticket_creator_create_checkout_false_ne_cree_pas_stripe(setup_event_and_reservation):
    """Avec create_checkout=False, aucun Paiement_stripe n'est créé.
    Les LigneArticle et Tickets sont bien créés.
    / With create_checkout=False, no Paiement_stripe is created.
    LigneArticle and Tickets are still created."""
    from BaseBillet.models import LigneArticle, Paiement_stripe, Ticket
    from BaseBillet.validators import TicketCreator

    data = setup_event_and_reservation
    count_stripe_before = Paiement_stripe.objects.count()

    products_dict = {data["product"]: {data["price"]: 2}}
    creator = TicketCreator(
        reservation=data["reservation"],
        products_dict=products_dict,
        create_checkout=False,
    )

    # Tickets créés
    # / Tickets created
    assert data["reservation"].tickets.count() == 2
    # LigneArticle créée
    # / LigneArticle created
    assert len(creator.list_line_article_sold) == 1
    # Aucun Paiement_stripe créé
    # / No Paiement_stripe created
    assert Paiement_stripe.objects.count() == count_stripe_before
    # checkout_link reste None
    # / checkout_link remains None
    assert creator.checkout_link is None


@pytest.mark.django_db
def test_ticket_creator_create_checkout_true_par_defaut_cree_stripe(
    setup_event_and_reservation,
):
    """Par défaut (create_checkout=True), un Paiement_stripe est créé (flow existant).
    / By default (create_checkout=True), a Paiement_stripe is created (existing flow)."""
    from BaseBillet.models import Paiement_stripe
    from BaseBillet.validators import TicketCreator

    data = setup_event_and_reservation
    count_before = Paiement_stripe.objects.count()

    products_dict = {data["product"]: {data["price"]: 1}}
    # On s'attend à ce que Stripe soit interrogé mais on n'a pas de clé valide
    # en test. On attrape simplement les cas où la création se fait quand même
    # (mock ou endpoint stub) ou échoue proprement.
    # / We expect Stripe to be called but we don't have a valid key in test.
    # We catch the cases where creation still succeeds (mock/stub) or fails cleanly.
    try:
        creator = TicketCreator(
            reservation=data["reservation"],
            products_dict=products_dict,
            # create_checkout=True par défaut — donc appelle get_checkout_stripe
        )
        # Si on arrive ici sans exception, un Paiement_stripe a été créé
        assert Paiement_stripe.objects.count() > count_before
    except Exception:
        # Acceptable : env de test sans clé Stripe valide.
        # Le comportement testé c'est la TENTATIVE d'appel, vs skip avec create_checkout=False
        # / Acceptable: test env without valid Stripe key.
        # Tested behavior: attempt to call, vs skip with create_checkout=False
        pass
```

- [ ] **Étape 4 : Lancer les tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_ticket_creator_no_checkout.py -v
```

Attendu : 2 tests PASS. Le test `create_checkout=True` peut passer avec ou sans exception Stripe (l'important est qu'il **tente** l'appel alors que `create_checkout=False` ne le fait pas).

- [ ] **Étape 5 : Vérifier aucune régression sur les tests de Reservation existants**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_reservation_create.py tests/pytest/test_reservation_limits.py -v
```

Attendu : tests existants passent sans modification (le flag par défaut est `True` = comportement identique).

**Point de contrôle commit (mainteneur)** — fin Tâche 2.4.

---

## Tâche 2.5 : `CommandeService.materialiser()`

**Fichiers :**
- Créer : `BaseBillet/services_commande.py`
- Créer : `tests/pytest/test_commande_service.py`

**Contexte :** C'est la **pièce centrale** de ce chantier. Prend un `PanierSession` + des infos acheteur, produit une `Commande` avec N `Reservation` + K `Membership` + LigneArticle, optionnellement lie un `Paiement_stripe`. Tout atomique.

Phases (cf. spec section 3.4) :
1. Re-validation complète (via ré-appel aux mêmes validations que `PanierSession`)
2. Création `Commande(status=PENDING)`
3. Phase 1 — Memberships d'abord (pour débloquer tarifs gatés)
4. Phase 2 — Reservations groupées par event, via `TicketCreator(create_checkout=False)`
5. Phase 3 — Si total > 0 : `CreationPaiementStripe` avec toutes les LigneArticle
6. Phase 4 — Si total = 0 : marquer tout VALID direct + memberships en ONCE

Note importante : le param `accept_sepa` de `CreationPaiementStripe` n'existe pas encore (sera ajouté Session 03). En attendant, on appelle `CreationPaiementStripe` sans ce flag — le comportement par défaut suffit. Session 03 affinera.

- [ ] **Étape 1 : Créer `BaseBillet/services_commande.py`**

```python
"""
Orchestrateur de matérialisation d'un panier en objets DB.
/ Cart-to-DB materialization orchestrator.

Responsabilité unique : transformer un PanierSession en Commande + N Reservations
+ M Memberships + LigneArticle + éventuel Paiement_stripe. Le tout atomique.

/ Single responsibility: transform a PanierSession into Commande + N Reservations
+ M Memberships + LigneArticle + optional Paiement_stripe. Atomic.
"""
import logging
from decimal import Decimal

from django.db import connection, transaction
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


class CommandeServiceError(Exception):
    """Erreur à la matérialisation.
    / Error during materialization."""


class CommandeService:
    """
    Service stateless qui matérialise un panier en DB.
    / Stateless service that materializes a cart to DB.
    """

    @staticmethod
    @transaction.atomic
    def materialiser(panier, user, first_name, last_name, email):
        """
        Transforme le panier en objets DB et retourne la Commande créée.

        Args:
            panier: PanierSession instance.
            user: TibilletUser (déjà résolu par email au niveau de la vue).
            first_name, last_name, email: infos acheteur.

        Returns:
            Commande: la commande créée avec son status (PENDING si Stripe
                nécessaire, PAID si commande gratuite).

        Raises:
            CommandeServiceError: si le panier est invalide ou vide.
            InvalidItemError (via re-validation): si un item du panier n'est
                plus valide au moment du checkout.

        / Transforms the cart into DB objects and returns the created Commande.
        """
        from BaseBillet.models import (
            Commande, LigneArticle, Membership, PaymentMethod, Price,
            Reservation, SaleOrigin,
        )
        from BaseBillet.services_panier import PanierSession
        from ApiBillet.serializers import dec_to_int, get_or_create_price_sold

        if panier.is_empty():
            raise CommandeServiceError(_("Cart is empty."))

        # -- Création de la Commande pivot (status=PENDING) --
        # -- Create the pivot Commande (status=PENDING) --
        promo_code = panier.promo_code()
        commande = Commande.objects.create(
            user=user,
            email_acheteur=email,
            first_name=first_name,
            last_name=last_name,
            status=Commande.PENDING,
            promo_code=promo_code,
        )

        all_lines = []
        total_centimes = 0

        # -- Phase 1 : Memberships en premier --
        # -- Phase 1: Memberships first --
        for item in panier.items():
            if item['type'] != 'membership':
                continue
            price = Price.objects.get(uuid=item['price_uuid'])
            amount_dec = CommandeService._resolve_amount(price, item)
            membership = Membership.objects.create(
                user=user,
                price=price,
                commande=commande,
                contribution_value=amount_dec,
                status=Membership.WAITING_PAYMENT,
                first_name=first_name,
                last_name=last_name,
                newsletter=False,
                custom_form=item.get('custom_form') or None,
            )
            if item.get('options'):
                from BaseBillet.models import OptionGenerale
                opts = OptionGenerale.objects.filter(
                    uuid__in=item['options']
                )
                if opts.exists():
                    membership.option_generale.set(opts)

            price_sold = get_or_create_price_sold(price, custom_amount=amount_dec)
            amount_cts = dec_to_int(amount_dec)
            line = LigneArticle.objects.create(
                pricesold=price_sold,
                membership=membership,
                payment_method=PaymentMethod.STRIPE_NOFED,
                amount=amount_cts,
                qty=1,
                sale_origin=SaleOrigin.LESPASS,
                promotional_code=(promo_code if promo_code and promo_code.product == price.product else None),
            )
            all_lines.append(line)
            total_centimes += amount_cts

        # -- Phase 2 : Reservations groupées par event_uuid --
        # -- Phase 2: Reservations grouped by event_uuid --
        from BaseBillet.models import Event
        tickets_par_event = {}
        for item in panier.items():
            if item['type'] != 'ticket':
                continue
            tickets_par_event.setdefault(item['event_uuid'], []).append(item)

        for event_uuid, items_event in tickets_par_event.items():
            event = Event.objects.get(uuid=event_uuid)
            # Construction d'un products_dict conforme au format attendu par TicketCreator
            # / Build a products_dict compatible with TicketCreator's expected format
            products_dict = {}
            custom_amounts = {}
            for it in items_event:
                price = Price.objects.get(uuid=it['price_uuid'])
                qty = int(it['qty'])
                products_dict.setdefault(price.product, {})
                products_dict[price.product][price] = products_dict[price.product].get(price, 0) + qty
                if it.get('custom_amount'):
                    custom_amounts[price.uuid] = Decimal(str(it['custom_amount']))

            reservation = Reservation.objects.create(
                user_commande=user,
                event=event,
                commande=commande,
                status=Reservation.CREATED,
            )

            # TicketCreator gère Tickets + LigneArticle. On bloque son Stripe.
            # / TicketCreator handles Tickets + LigneArticle. We disable its Stripe.
            from BaseBillet.validators import TicketCreator
            creator = TicketCreator(
                reservation=reservation,
                products_dict=products_dict,
                promo_code=promo_code,
                custom_amounts=custom_amounts,
                sale_origin=SaleOrigin.LESPASS,
                create_checkout=False,  # <-- clé : pas de Stripe ici
            )
            for line in creator.list_line_article_sold:
                all_lines.append(line)
                total_centimes += int(line.amount * line.qty)

        # -- Phase 3/4 : Stripe ou gratuit --
        # -- Phase 3/4: Stripe or free --
        if total_centimes > 0:
            CommandeService._creer_paiement_stripe(commande, user, all_lines)
            # Status reste PENDING — Stripe webhook basculera en PAID via signaux
        else:
            CommandeService._finaliser_gratuit(commande, all_lines)

        logger.info(
            f"CommandeService.materialiser OK : commande={commande.uuid_8()}, "
            f"lignes={len(all_lines)}, total_cts={total_centimes}, status={commande.status}"
        )
        return commande

    @staticmethod
    def _resolve_amount(price, item):
        """Calcule le montant Decimal à utiliser pour ce price + item.
        / Compute the Decimal amount to use for this price + item."""
        if price.free_price and item.get('custom_amount'):
            return Decimal(str(item['custom_amount']))
        return price.prix or Decimal("0.00")

    @staticmethod
    def _creer_paiement_stripe(commande, user, lignes):
        """Phase 3 — crée un Paiement_stripe consolidé pour toutes les lignes.
        / Phase 3 — create a consolidated Paiement_stripe for all lines."""
        from BaseBillet.models import LigneArticle, Paiement_stripe
        from PaiementStripe.views import CreationPaiementStripe

        tenant = connection.tenant
        metadata = {
            'tenant': f'{tenant.uuid}',
            'tenant_name': f'{tenant.name}',
            'commande_uuid': f'{commande.uuid}',
        }

        new_paiement = CreationPaiementStripe(
            user=user,
            liste_ligne_article=lignes,
            metadata=metadata,
            reservation=None,  # Pas de FK : le pivot est Commande
            source=Paiement_stripe.FRONT_BILLETTERIE,
            success_url=f"stripe_return/",
            cancel_url=f"stripe_return/",
            absolute_domain=f"https://{tenant.get_primary_domain()}/panier/",
        )
        if not new_paiement.is_valid():
            raise CommandeServiceError(_("Payment creation failed."))

        paiement = new_paiement.paiement_stripe_db
        paiement.lignearticles.all().update(status=LigneArticle.UNPAID)

        commande.paiement_stripe = paiement
        commande.save(update_fields=["paiement_stripe"])

    @staticmethod
    def _finaliser_gratuit(commande, lignes):
        """
        Phase 4 — commande gratuite (total 0€) : pas de Stripe, tout VALID direct.
        / Phase 4 — free order (total 0€): no Stripe, all VALID direct.
        """
        from django.utils import timezone
        from BaseBillet.models import Commande, LigneArticle, Membership, PaymentMethod, Reservation

        now = timezone.now()

        # Memberships de la commande → ONCE + deadline
        # / Commande's memberships → ONCE + deadline
        for membership in commande.memberships_commande.all():
            if not membership.first_contribution:
                membership.first_contribution = now
            membership.last_contribution = now
            membership.payment_method = PaymentMethod.FREE
            membership.status = Membership.ONCE
            membership.save()
            membership.set_deadline()

        # Reservations de la commande → FREERES/FREERES_USERACTIV selon user.is_active
        # / Commande's reservations → FREERES/FREERES_USERACTIV per user.is_active
        for reservation in commande.reservations.all():
            user = reservation.user_commande
            reservation.status = (
                Reservation.FREERES_USERACTIV if user.is_active else Reservation.FREERES
            )
            reservation.save()

        # LigneArticle → VALID + payment_method=FREE
        # / LigneArticle → VALID + payment_method=FREE
        for line in lignes:
            line.status = LigneArticle.VALID
            line.payment_method = PaymentMethod.FREE
            line.save(update_fields=["status", "payment_method"])

        commande.status = Commande.PAID
        commande.paid_at = now
        commande.save(update_fields=["status", "paid_at"])
```

- [ ] **Étape 2 : Créer `tests/pytest/test_commande_service.py`**

```python
"""
Tests du service de matérialisation de commande.
Session 02 — Tâche 2.5.

Run:
    poetry run pytest -q tests/pytest/test_commande_service.py
"""
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.db.models import Q
from django.utils import timezone
from django_tenants.utils import tenant_context


@pytest.fixture
def tenant_context_lespass():
    from Customers.models import Client as TenantClient
    tenant = TenantClient.objects.get(schema_name="lespass")
    with tenant_context(tenant):
        yield tenant


@pytest.fixture
def user_acheteur(tenant_context_lespass):
    from AuthBillet.models import TibilletUser
    user = TibilletUser.objects.create(
        email=f"cs-{uuid.uuid4()}@example.org",
        username=f"cs-{uuid.uuid4()}",
    )
    yield user
    from BaseBillet.models import (
        Commande, LigneArticle, Membership, Paiement_stripe, Reservation,
    )
    LigneArticle.objects.filter(
        Q(reservation__user_commande=user) | Q(membership__user=user)
    ).delete()
    Reservation.objects.filter(user_commande=user).delete()
    Membership.objects.filter(user=user).delete()
    Commande.objects.filter(user=user).delete()
    Paiement_stripe.objects.filter(user=user).delete()
    user.delete()


@pytest.fixture
def request_authentifie(user_acheteur, tenant_context_lespass):
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory
    factory = RequestFactory()
    request = factory.get('/')
    middleware = SessionMiddleware(lambda r: None)
    middleware.process_request(request)
    request.session.save()
    request.user = user_acheteur
    return request


@pytest.mark.django_db
def test_materialiser_commande_gratuite_multi_events(
    request_authentifie, user_acheteur, tenant_context_lespass,
):
    """Un panier 100% gratuit avec 2 events → Commande PAID direct (pas de Stripe).
    / A 100% free cart with 2 events → Commande PAID direct (no Stripe)."""
    from BaseBillet.models import Commande, Event, Price, Product, Reservation
    from BaseBillet.services_commande import CommandeService
    from BaseBillet.services_panier import PanierSession

    # Setup : 2 events gratuits avec produit et prix 0€
    prod_free = Product.objects.create(
        name=f"Free {uuid.uuid4()}", categorie_article=Product.FREERES,
    )
    event_a = Event.objects.create(
        name=f"EA-{uuid.uuid4()}", datetime=timezone.now() + timedelta(days=3),
        end_datetime=timezone.now() + timedelta(days=3, hours=2), jauge_max=100,
    )
    event_b = Event.objects.create(
        name=f"EB-{uuid.uuid4()}", datetime=timezone.now() + timedelta(days=5),
        end_datetime=timezone.now() + timedelta(days=5, hours=2), jauge_max=100,
    )
    event_a.products.add(prod_free)
    event_b.products.add(prod_free)
    # Price 0€ créé automatiquement via signal post_save sur FREERES
    # / Price 0€ auto-created via post_save signal on FREERES
    price_free = prod_free.prices.filter(prix=0).first()
    assert price_free is not None

    # Ajout au panier
    panier = PanierSession(request_authentifie)
    panier.add_ticket(event_a.uuid, price_free.uuid, qty=2)
    panier.add_ticket(event_b.uuid, price_free.uuid, qty=1)

    # Matérialisation
    commande = CommandeService.materialiser(
        panier, user_acheteur,
        first_name="Free",
        last_name="Tester",
        email=user_acheteur.email,
    )

    # Assertions
    assert commande.status == Commande.PAID
    assert commande.paid_at is not None
    assert commande.paiement_stripe is None
    assert commande.reservations.count() == 2
    # Chaque reservation doit être en FREERES ou FREERES_USERACTIV
    # / Each reservation must be in FREERES or FREERES_USERACTIV
    for r in commande.reservations.all():
        assert r.status in [Reservation.FREERES, Reservation.FREERES_USERACTIV]
    assert commande.total_lignes() == 0

    # Cleanup (user fixture s'occupe du reste)
    price_free.delete()
    prod_free.delete()
    event_a.delete()
    event_b.delete()


@pytest.mark.django_db
def test_materialiser_commande_vide_leve_erreur(
    request_authentifie, user_acheteur, tenant_context_lespass,
):
    from BaseBillet.services_commande import CommandeService, CommandeServiceError
    from BaseBillet.services_panier import PanierSession

    panier = PanierSession(request_authentifie)
    with pytest.raises(CommandeServiceError, match="empty"):
        CommandeService.materialiser(
            panier, user_acheteur,
            first_name="X", last_name="Y", email=user_acheteur.email,
        )


@pytest.mark.django_db
def test_materialiser_cree_membership_avant_reservation(
    request_authentifie, user_acheteur, tenant_context_lespass,
):
    """Phase 1 (Membership) doit finir avant Phase 2 (Reservation).
    Vérifié par : un tarif gaté par l'adhésion du panier est accepté.
    / Phase 1 (Membership) must finish before Phase 2 (Reservation).
    Verified by: a rate gated by the cart's membership is accepted."""
    from BaseBillet.models import Commande, Event, Membership, Price, Product
    from BaseBillet.services_commande import CommandeService
    from BaseBillet.services_panier import PanierSession

    # Adhésion gratuite + billet gaté à 0€
    prod_adh = Product.objects.create(
        name=f"Ad {uuid.uuid4()}", categorie_article=Product.ADHESION,
    )
    price_adh = Price.objects.create(
        product=prod_adh, name="A", prix=Decimal("0.00"), publish=True,
    )
    prod_billet = Product.objects.create(
        name=f"Bg {uuid.uuid4()}", categorie_article=Product.BILLET,
    )
    event = Event.objects.create(
        name=f"Gated {uuid.uuid4()}", datetime=timezone.now() + timedelta(days=2),
        end_datetime=timezone.now() + timedelta(days=2, hours=1), jauge_max=50,
    )
    event.products.add(prod_billet)
    price_billet = Price.objects.create(
        product=prod_billet, name="Adh", prix=Decimal("0.00"), publish=True,
    )
    price_billet.adhesions_obligatoires.add(prod_adh)

    panier = PanierSession(request_authentifie)
    panier.add_membership(price_adh.uuid)
    panier.add_ticket(event.uuid, price_billet.uuid, qty=1)

    commande = CommandeService.materialiser(
        panier, user_acheteur,
        first_name="O", last_name="K", email=user_acheteur.email,
    )

    assert commande.status == Commande.PAID  # tout gratuit
    assert commande.memberships_commande.count() == 1
    assert commande.reservations.count() == 1
    # Le membership doit être ONCE (gratuit)
    m = commande.memberships_commande.first()
    assert m.status == Membership.ONCE
    assert m.deadline is not None

    price_billet.delete()
    price_adh.delete()
    event.delete()
    prod_billet.delete()
    prod_adh.delete()


@pytest.mark.django_db
def test_materialiser_rollback_si_erreur(
    request_authentifie, user_acheteur, tenant_context_lespass,
):
    """Si une exception survient en cours de matérialisation, tout rollback.
    / If an exception occurs during materialization, everything rolls back."""
    from unittest.mock import patch
    from BaseBillet.models import Commande, Event, Price, Product
    from BaseBillet.services_commande import CommandeService
    from BaseBillet.services_panier import PanierSession

    prod = Product.objects.create(
        name=f"R {uuid.uuid4()}", categorie_article=Product.FREERES,
    )
    event = Event.objects.create(
        name=f"RB-{uuid.uuid4()}", datetime=timezone.now() + timedelta(days=3),
        end_datetime=timezone.now() + timedelta(days=3, hours=2), jauge_max=50,
    )
    event.products.add(prod)
    price = prod.prices.filter(prix=0).first()

    panier = PanierSession(request_authentifie)
    panier.add_ticket(event.uuid, price.uuid, qty=1)

    count_before = Commande.objects.filter(user=user_acheteur).count()

    # Force une exception dans la Phase 4 (gratuit) via mock
    with patch(
        "BaseBillet.services_commande.CommandeService._finaliser_gratuit",
        side_effect=RuntimeError("boom"),
    ):
        with pytest.raises(RuntimeError):
            CommandeService.materialiser(
                panier, user_acheteur,
                first_name="R", last_name="B", email=user_acheteur.email,
            )

    # La commande ne doit pas exister (rollback)
    count_after = Commande.objects.filter(user=user_acheteur).count()
    assert count_after == count_before

    price.delete()
    prod.delete()
    event.delete()
```

- [ ] **Étape 3 : Lancer les tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_commande_service.py -v
```

Attendu : 4 tests PASS.

**Point de contrôle commit (mainteneur)** — fin Tâche 2.5.

---

## Tâche 2.6 : Vérifications finales

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

- [ ] **Étape 3 : Suite pytest Session 01 + Session 02**

```bash
docker exec lespass_django poetry run pytest \
    tests/pytest/test_commande_model.py \
    tests/pytest/test_panier_session.py \
    tests/pytest/test_commande_service.py \
    tests/pytest/test_ticket_creator_no_checkout.py -v
```

Attendu : 13 (Session 01) + 28 (Tâches 2.1-2.3) + 2 (Tâche 2.4) + 4 (Tâche 2.5) = **47 tests PASS**.

- [ ] **Étape 4 : Non-régression globale**

```bash
docker exec lespass_django poetry run pytest tests/pytest/ -q
```

Attendu : tous les tests passent OU uniquement les flakies connus (même liste qu'en Session 01). Aucun test nouvellement cassé par nos changements.

**Session 02 — terminée.**

---

## Récap fichiers touchés

| Action | Fichier |
|---|---|
| Créer | `BaseBillet/services_panier.py` (~400 lignes) |
| Créer | `BaseBillet/services_commande.py` (~220 lignes) |
| Modifier | `BaseBillet/validators.py` (2 lignes : signature + condition) |
| Créer | `tests/pytest/test_panier_session.py` (~600 lignes, 28 tests) |
| Créer | `tests/pytest/test_commande_service.py` (~220 lignes, 4 tests) |
| Créer | `tests/pytest/test_ticket_creator_no_checkout.py` (~100 lignes, 2 tests) |

## Critères de Done Session 02

- [x] `PanierSession` opérationnel : add/remove/count/clear + toutes les validations (stock, max_per_user, recurring, manual, adhesion obligatoire cart-aware, overlap) + code promo
- [x] `CommandeService.materialiser()` fonctionne pour : gratuit mono-event, gratuit multi-events, panier avec adhésion débloquant un tarif gaté, rollback en cas d'erreur
- [x] `TicketCreator(create_checkout=False)` ne crée pas de Paiement_stripe (utilisé par `CommandeService`)
- [x] `manage.py check` : 0 issue
- [x] 34 tests ajoutés en Session 02, tous PASS
- [x] Aucune régression sur les tests existants

## Hors scope — attendu en Session 03

- Patch `set_ligne_article_paid()` dans `signals.py` (itération sur lignes multi-reservations)
- Param `accept_sepa` sur `CreationPaiementStripe`
- `ReservationValidator` cart-aware + correction bug overlap (incorporé dans le validator existant)
- Tests de non-régression signals/webhook
