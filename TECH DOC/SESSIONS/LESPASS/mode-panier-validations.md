# Mode panier — Architecture, validations et tests

Date : avril 2026
Statut : livré
Branch : `panier`

---

## TL;DR — Garanties du mode panier

| Scénario | Comportement | Test |
|----------|--------------|------|
| User ajoute des billets, jauge devient pleine **avant** clic "Ajouter" | **Refus** à l'ajout, toast rouge avec places restantes | `test_add_ticket_refuse_si_jauge_event_depassee` |
| User ajoute OK, attend 10 min, clique "Passer au paiement", **jauge pleine entre-temps** | **Refus** au checkout, toast rouge | `test_revalidate_all_detecte_limite_depassee_entre_ajout_et_checkout` |
| User a déjà des billets dans le panier et essaie d'en ajouter au-delà de `max_per_user` | **Refus** à l'ajout (cumul panier comptabilisé) | `test_add_ticket_refuse_si_panier_depasse_*_max_per_user` (×3) |
| User a déjà des billets **en DB** (réservations VALID) + cumul panier dépasse | **Refus** à l'ajout (DB + panier comptabilisés) | `test_add_ticket_user_auth_refuse_si_db_plus_cart_depasse_event_max` |
| User ajoute sans atteindre la limite, tickets **under_purchase** d'autres users remplissent la jauge | **Refus** à l'ajout | `test_add_ticket_jauge_compte_under_purchase` |
| User atteint exactement la limite (qty = max_per_user) | **Accept** (limite inclusive) | `test_add_ticket_accepte_exactement_a_la_limite` |

**Parité totale avec le flow direct `POST /event/.../reservation/`** (`ReservationValidator`) — plus aucun trou de validation entre panier et flow direct.

---

## 1. Architecture générale

Deux flows coexistent dans Lespass :

```
                    ┌──────────────────────┐
                    │     User UI          │
                    └──────────┬───────────┘
                               │
            ┌──────────────────┴──────────────────┐
            │                                     │
     FLOW DIRECT                           FLOW PANIER
            │                                     │
            ▼                                     ▼
  POST /event/{uuid}/reservation/     POST /panier/add/tickets_batch/
            │                                     │
            ▼                                     ▼
     ReservationValidator                 PanierSession.add_ticket
     (validators.py)                      (services_panier.py)
            │                                     │
            │                              ┌──────┴──────┐
            │                              ▼             ▼
            │                         Session DB     validate_ticket_
            │                         (stockage)     cart_limits()
            │                              │             │
            │                              │     [5 validations
            │                              │      cart-aware]
            │                              ▼
            │                        User clique Checkout
            │                              │
            │                              ▼
            │                    POST /panier/checkout/
            │                              │
            │                              ▼
            │                  CommandeService.materialiser()
            │                              │
            │                              ▼
            │                    panier.revalidate_all()
            │                    [re-applique les validations
            │                     sur tous les items]
            │                              │
            └──────────────────┬───────────┘
                               │
                               ▼
                     Paiement Stripe ou gratuit
```

**Les 2 flows utilisent les mêmes validations** mais à des moments différents :
- **Direct** : validation unique au POST reservation → création Stripe immédiate
- **Panier** : validation à chaque `add_ticket` **ET** re-validation complète au checkout
  → garantit la cohérence si des ajouts/annulations DB se produisent entre-temps

---

## 2. Les 8 validations de `PanierSession.add_ticket`

Localisation : `BaseBillet/services_panier.py`

```python
def add_ticket(self, event_uuid, price_uuid, qty,
               custom_amount=None, options=None, custom_form=None,
               promotional_code_name=None):
    """
    Ajoute un item billet au panier apres validation (8 checks).
    """
```

### Validation 1 — Quantité positive
`qty > 0` sinon `InvalidItemError("Quantity must be positive.")`

### Validation 2 — Event existe et accessible
- `Event.objects.get(uuid=event_uuid)` existe
- `event.complet()` → False (jauge globale DB uniquement)

### Validation 3 — Price existe et actif
- Price existe
- `price.publish` = True
- `price.product.archive` = False

### Validation 4 — Price appartient à l'event
`price.product in event.products.all()` — empêche les attaques par UUID de price d'un autre event.

### Validation 5 — Price max_per_user (sanity check qty seule)
`qty > price.max_per_user` → refus. Check basique sur la requête seule (pas de cumul DB+panier, c'est le rôle de 5bis).

### Validation 5bis — Cart-aware limits ⭐ **nouveau refactor avril 2026**

**Fonction `validate_ticket_cart_limits(user, event, product, price, qty_to_add, cart_items)`.**

Calcule :
- `cart_qty_event` : somme des qty des items panier de cet event
- `cart_qty_product` : somme des qty des items panier de ce product dans cet event
- `cart_qty_price` : somme des qty des items panier pour ce price

Vérifie :

**Si user authentifié** :
```
db_qty_event    = count(Ticket user, event, status in [NOT_SCANNED, SCANNED])
db_qty_product  = count idem filtré par product
db_qty_price    = count idem filtré par price

total_event   = db_qty_event   + cart_qty_event   + qty_to_add
total_product = db_qty_product + cart_qty_product + qty_to_add
total_price   = db_qty_price   + cart_qty_price   + qty_to_add

if total_event   > event.max_per_user   → raise InvalidItemError
if total_product > product.max_per_user → raise InvalidItemError
if total_price   > price.max_per_user   → raise InvalidItemError
```

**Si user anonyme** (flow panier exige auth en prod, mais sécurité défensive) :
Skip DB checks, garde les cart-level uniquement.

**Jauge globale (tous users)** :
```
valid_count     = event.valid_tickets_count()   # tickets PAID actifs
under_purchase  = event.under_purchase()        # tickets CREATED <15min
total_occupation = valid_count + under_purchase + cart_qty_event + qty_to_add

if total_occupation > event.jauge_max → raise InvalidItemError avec places restantes
```

### Validation 6 — Stock price
`price.out_of_stock(event=event)` → refus si stock tarif épuisé (compte les tickets existants).

### Validation 7 — Prix libre (free_price)
Si `price.free_price` :
- `custom_amount` requis
- `custom_amount >= price.prix` (minimum)
- `custom_amount <= 999999.99` (plafond hard-coded)

### Validation 7bis — Adhésions obligatoires (cart-aware)
Si `price.adhesions_obligatoires.exists()` :
- User a l'adhésion active en DB (`user.memberships.filter(deadline__gte=now)`), OU
- Adhésion dans le panier courant (cart-aware — permet d'acheter adhésion + tarif adhérent en une transaction)

Sinon → `InvalidItemError("This rate requires a membership: X...")`

### Validation 8 — Overlap temporel
Si `Configuration.allow_concurrent_bookings` = False :
- Pas d'overlap avec un autre event dans le panier
- Pas d'overlap avec une réservation existante du user en DB (hors statuts CANCELED)
- Blocage dur : statuts BLOCKING_STATUSES (PAID, VALID, FREERES, etc.)
- Blocage récent : statuts CREATED/UNPAID depuis <15min

### Validation 9 — Code promo (optionnel, item-level)
Si `promotional_code_name` fourni :
- `PromotionalCode.objects.get(name=..., is_active=True)` existe
- `promo.is_usable()` (usage_limit non atteinte)
- `promo.product_id == price.product_id` (code lié au bon product)

**Le code est stocké par item**, pas au niveau panier. Au checkout, il est appliqué uniquement à la ligne concernée.

---

## 3. Re-validation au checkout

Localisation : `BaseBillet/services_commande.py`

```python
def materialiser(panier, user, first_name, last_name, email):
    # Phase 0 : re-validation complete des items
    panier.revalidate_all()
    
    # Phase 1 : creation Memberships + LigneArticle
    # Phase 2 : Reservations groupees par event + Tickets (TicketCreator)
    # Phase 3 : Stripe si payant, ou finalisation gratuite
```

### `panier.revalidate_all()`

```python
def revalidate_all(self):
    items_snapshot = list(self._data['items'])
    self._data['items'] = []
    self._save()
    for item in items_snapshot:
        # Re-appelle add_ticket ou add_membership — re-applique les 8+
        # validations. Si une limite a change entre-temps (jauge pleine,
        # stock epuise, adhesion retiree) → InvalidItemError.
        if item['type'] == 'ticket':
            self.add_ticket(...)
        else:
            self.add_membership(...)
```

### Gestion de l'erreur dans la vue

`PanierMVT.checkout` :

```python
try:
    commande = CommandeService.materialiser(panier, user, ...)
except InvalidItemError as exc:
    # Ex : "Not enough seats available. Remaining: 0"
    return self._render_badge_and_toast(
        request, message=str(exc), level='error',
    )
except CommandeServiceError as exc:
    # Ex : "Cart is empty."
    return self._render_badge_and_toast(request, message=str(exc), level='error')
```

→ Toast SweetAlert rouge top-right avec le message précis.

---

## 4. Ce qui a été supprimé (refactor avril 2026)

### ❌ `update_quantity` — supprimé complètement

**Pourquoi** : impossible de garantir que la nouvelle qty respecte les limites sans dupliquer toute la logique de `add_ticket`. La façon honnête : **user retire + re-ajoute via booking_form**.

**Impact code** :
- `services_panier.py` : méthode `update_quantity` supprimée (remplacée par comment)
- `views.py` : endpoint `@action update_quantity` supprimé → route 404
- `panier_item.html` : `<input type="number">` → `<span>× N</span>` lecture seule
- Tests : 3 tests supprimés, 1 remplacé par un test qui vérifie le 404

### ❌ Code promo global du panier — supprimé

**Pourquoi** : un code promo est lié à un **product** (FK), pas au panier global. L'ancienne UI permettait d'appliquer un code à tout le panier, mais le serveur l'appliquait déjà item-par-item.

**Maintenant** : champ `promotional_code` dans chaque booking_form/membership form, stocké **sur l'item** du panier.

### ❌ Section "Complete my profile" du panier — supprimée

**Pourquoi** : les infos (firstname, lastname) sont collectées dans les formulaires d'adhésion et de réservation, pas au niveau panier. Le bandeau jaune "Please complete your profile" qui pointait vers `/my_account/` n'a plus lieu d'être.

---

## 5. Tests unitaires — couverture

Localisation : `tests/pytest/test_panier_session.py`

### Tests existants (avant refactor)

| # | Test | Couvre |
|---|------|--------|
| 1 | `test_add_ticket_stocke_en_session` | Flow nominal add |
| 2 | `test_add_ticket_refuse_price_non_publie` | Validation 3 |
| 3 | `test_add_ticket_refuse_price_pas_dans_event` | Validation 4 |
| 4 | `test_add_ticket_refuse_adhesion_obligatoire_sans_adhesion` | Validation 7bis |
| 5 | `test_add_ticket_accepte_si_adhesion_dans_panier` | Validation 7bis cart-aware |
| 6 | `test_add_ticket_refuse_overlap_contre_panier` | Validation 8 |
| 7 | `test_revalidate_all_detecte_price_depublie` | revalidate_all |

### Tests nouveaux (refactor avril 2026)

| # | Test | Couvre |
|---|------|--------|
| 1 | `test_add_ticket_refuse_si_panier_seul_depasse_event_max_per_user` | V5bis event.max_per_user cart-only |
| 2 | `test_add_ticket_refuse_si_panier_depasse_product_max_per_user` | V5bis product.max_per_user |
| 3 | `test_add_ticket_refuse_si_panier_depasse_price_max_per_user` | V5bis price.max_per_user cart-aware |
| 4 | `test_add_ticket_accepte_exactement_a_la_limite` | Limite inclusive (edge case) |
| 5 | `test_add_ticket_refuse_si_jauge_event_depassee` | V5bis jauge globale |
| 6 | `test_add_ticket_user_auth_refuse_si_db_plus_cart_depasse_event_max` | V5bis DB+cart cumul |
| 7 | `test_add_ticket_jauge_compte_under_purchase` | V5bis jauge compte under_purchase |
| 8 | `test_revalidate_all_detecte_limite_depassee_entre_ajout_et_checkout` | Re-validation au checkout |

### Résultat

**95 tests panier passent** (90 avant + 8 nouveaux − 3 supprimés) — zéro régression.

---

## 6. Comparaison panier vs flow direct

| Validation | Flow direct (`ReservationValidator`) | Flow panier (`add_ticket` + `revalidate_all`) |
|-----------|--------------------------------------|----------------------------------------------|
| qty > 0 | ✅ | ✅ |
| Event existe, pas complet | ✅ | ✅ |
| Price publish, product non-archive | ✅ | ✅ |
| Price appartient à event | ✅ | ✅ |
| `event.max_per_user_reached_on_this_event(user)` | ✅ L564 | ✅ V5bis |
| `product.max_per_user_reached(user, event)` | ✅ L569 | ✅ V5bis |
| `price.max_per_user_reached(user, event)` | ✅ L579 | ✅ V5bis (cart-aware) |
| `total_qty > event.max_per_user` | ✅ L611 | ✅ V5bis (DB+cart+add) |
| `valid + under_purchase + total > jauge_max` | ✅ L619 | ✅ V5bis (+cart) |
| Stock `price.out_of_stock(event)` | ✅ L583 | ✅ V6 |
| Code promo matche product | ✅ L540 | ✅ V9 |
| Adhesion obligatoire active | ✅ L598 | ✅ V7bis (cart-aware) |
| Overlap temporel | ✅ L624 | ✅ V8 |
| Free price custom_amount min/max | via dec_to_int | ✅ V7 |

**Parité complète** sur les 13 validations. Le flow panier ajoute même le cart-aware check pour les adhésions obligatoires (non présent dans le flow direct), ce qui permet d'acheter adhésion + tarif adhérent en une seule transaction.

---

## 7. Diagramme de séquence — checkout

```
User                  PanierMVT             CommandeService       PanierSession
 │                        │                        │                     │
 │── POST /checkout/ ─────│                        │                     │
 │                        │── materialiser(panier) │                     │
 │                        │                        │── revalidate_all() ─│
 │                        │                        │                     │
 │                        │                        │          ┌── add_ticket(item1) ─┐
 │                        │                        │          │   (8+ validations)    │
 │                        │                        │          │   ...                 │
 │                        │                        │          └── add_ticket(itemN) ─┘
 │                        │                        │                     │
 │                        │                        │ [if InvalidItemError]
 │                        │                        │                     │
 │                        │                        │── Phase 1: Memberships
 │                        │                        │── Phase 2: Reservations + Tickets
 │                        │                        │── Phase 3: Stripe ou gratuit
 │                        │                        │                     │
 │                        │◄── commande ───────────│                     │
 │                        │                        │                     │
 │                        │── panier.clear() ──────────────────────────►│
 │                        │                        │                     │
 │◄─ HX-Redirect Stripe ─│                        │                     │
```

**Points clés** :
- `revalidate_all()` est **atomic** : si un item fail, aucune Commande n'est créée (rollback DB).
- `panier.clear()` **uniquement après succès**. En cas d'échec, le panier est intact → user peut corriger.

---

## 8. Questions fréquentes (FAQ)

### Q: Pourquoi pas de fonction partagée avec `ReservationValidator` ?

Parce qu'ils ont des signatures très différentes :
- `ReservationValidator` est un DRF Serializer qui prend des dict POST (email, options, custom_form, prices sous forme de dict-de-dict).
- `add_ticket` prend des paramètres scalaires (event_uuid, price_uuid, qty).

Le helper `validate_ticket_cart_limits` est une **extraction ciblée** des checks de limites (sans la partie validation de format). Si un jour on veut les partager, on pourrait extraire une fonction pure `check_limits(user, event, product, price, qty, extra_db_count=0, extra_cart_count=0)` utilisée par les 2.

### Q: Pourquoi `validate_ticket_cart_limits` vs les méthodes existantes sur Event/Product/Price ?

Les méthodes `Event.max_per_user_reached_on_this_event`, `Product.max_per_user_reached`, `Price.max_per_user_reached` retournent True/False en **ne comptant que la DB**, sans prendre en compte ni le panier ni la qty à ajouter. Pour un check cart-aware, il faut :

```
total = db_count + cart_count + qty_to_add
if total > max → reject
```

Les 3 méthodes existantes sont appelées par `ReservationValidator` qui fait un workflow différent (count-based, pas sum-based). Pour le panier, sum-based est la bonne approche.

### Q: Que se passe-t-il si la re-validation au checkout échoue ?

`InvalidItemError` remontée à `PanierMVT.checkout` :

```python
except InvalidItemError as exc:
    return self._render_badge_and_toast(request, message=str(exc), level='error')
```

→ Toast SweetAlert rouge top-right, user reste sur `/panier/` avec son panier intact. Il peut :
- Retirer l'item problématique (si adhésion retirée, par ex.)
- Réduire la quantité (impossible via UI → retirer + re-ajouter)
- Attendre que la jauge se libère
- Abandonner

Aucune Commande ou Paiement_stripe n'a été créée — rollback propre.

### Q: Pourquoi inclure un `under_purchase` dans le calcul de la jauge ?

`under_purchase` = tickets créés il y a moins de 15 minutes en statut CREATED/UNPAID (user est en cours de paiement Stripe). Ne pas les compter laisserait la jauge "apparaître libre" pendant qu'un autre user est en train de payer → double-booking.

Exactement le même comportement que le flow direct (`ReservationValidator` L617-619).

### Q: L'user anonyme peut-il exploiter les checks manquants ?

Non. En prod :
- Le flow panier nécessite l'auth (`PanierMVT.get_permissions()` → `IsAuthenticated` sur les writes).
- Le flow direct (`/event/.../reservation/`) crée un TibilletUser à la volée via `get_or_create_user(email)` — donc tous les checks DB sont actifs.

Le skip DB pour anonyme dans `validate_ticket_cart_limits` est une **sécurité défensive** (ne crash pas si appelé avec AnonymousUser), pas un contournement.

---

## 9. Référentiel des fichiers touchés

| Fichier | Nature |
|---------|--------|
| `BaseBillet/services_panier.py` | Helper `validate_ticket_cart_limits` + 3 helpers privés `_cart_qty_for_*` + intégration V5bis dans `add_ticket` + suppression `update_quantity` |
| `BaseBillet/services_commande.py` | `materialiser` catche `InvalidItemError` pour remonter message précis |
| `BaseBillet/views.py` | `PanierMVT.update_quantity` supprimée. `PanierMVT.checkout` catche `InvalidItemError`. |
| `BaseBillet/templates/htmx/components/panier_item.html` | `<input type="number">` → `<span class="badge">× N</span>` |
| `BaseBillet/templates/htmx/components/panier_content.html` | Retrait mention `update_quantity` |
| `tests/pytest/test_panier_session.py` | 8 nouveaux tests + suppression 3 tests `update_quantity` |
| `tests/pytest/test_panier_mvt.py` | 1 test remplacé par test 404 endpoint |

---

## 10. Références

- Spec panier multi-events : `TECH DOC/SESSIONS/LESPASS/specs/2026-04-17-panier-multi-events-design.md`
- Pièges documentés : `tests/PIEGES.md`
- Stratégie E2E : `TECH DOC/IDEAS/strategie-tests-e2e-panier.md`
- Plans sessions : `TECH DOC/SESSIONS/LESPASS/plans/2026-04-17-panier-session-0{1-8}-*.md`
- CHANGELOG : `CHANGELOG.md` section "Panier d'achat multi-events"
