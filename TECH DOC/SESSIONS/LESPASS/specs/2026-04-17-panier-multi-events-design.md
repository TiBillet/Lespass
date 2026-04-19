# Design Spec — Panier d'achat multi-events

> **Nouveau chantier** sur le site public Lespass.
> Permet à un utilisateur d'acheter en une seule commande des billets de plusieurs events + des adhésions.
>
> Date : 2026-04-17
> Auteurs : Jonas (mainteneur) + Claude Code (brainstorming)

---

## 1. Objectif

Aujourd'hui, chaque achat sur Lespass est scoped à **un seul event** (ou à une adhésion isolée). L'utilisateur qui veut acheter 3 billets pour 2 events différents + une adhésion doit passer par 3 parcours distincts et payer 3 fois. Pas d'ergonomie, pas de panier.

Ce chantier introduit un panier d'achat permettant :
- de cumuler des billets de plusieurs events
- de cumuler des adhésions standards
- de débloquer les tarifs réservés aux adhérents si l'adhésion requise est dans le panier
- de payer en **un seul checkout Stripe** (une session, N line_items)
- de matérialiser atomiquement N `Reservation` + M `Membership` + 1 `Paiement_stripe` au moment du paiement

**Ce que ce n'est pas :**
- Pas une refonte du modèle `Reservation` (reste FK vers 1 event)
- Pas un panier persisté en DB (reste en session Django)
- Pas un support des adhésions récurrentes (incompatible Stripe)
- Pas un remplacement du flow direct actuel ("Payer maintenant" reste possible)

---

## 2. Décisions prises

| # | Décision | Justification |
|---|----------|---------------|
| 1 | Nouveau modèle `Commande` pivot | Découple "regroupement d'items" de "moyen de paiement" — compatible futurs moyens non-Stripe |
| 2 | Panier en **session Django** (pas en DB) | Zéro persistance pour les paniers abandonnés, pas de nettoyage, cohérent avec le hold actuel (matérialisation au checkout) |
| 3 | `Commande` créée seulement au checkout | Comportement identique au modèle actuel (Reservation créée au moment du paiement) — pas de régression sur le stock |
| 4 | Périmètre v1 : items "simples" uniquement | YAGNI — Formbricks va être retiré, pas besoin de gérer les cas tordus |
| 5 | Adhésions récurrentes hors panier | Stripe n'autorise pas de mélanger `payment` et `subscription` dans une session — refonte majeure inutile |
| 6 | Validation manuelle hors panier | Pas de paiement, parcours admin séparé — pas sa place dans un panier |
| 7 | 1 seul code promo actif par panier | Modèle `PromotionalCode` (FK → Product) déjà compatible — 1 code peut s'appliquer à N lignes du même product dans le panier |
| 8 | Adhésion traitée en **Phase 1** au checkout | Permet aux tarifs gatés (`adhesions_obligatoires`) d'être validés dans la même commande que l'adhésion qui les débloque |
| 9 | Atomicité complète via `@transaction.atomic` | Soit tout est créé, soit rien — pas d'état incohérent |
| 10 | Un seul email acheteur, tous les billets au même nom | Simplifie le parcours v1 — per-billet nominatif reportable en v2 |
| 11 | Indicateur panier HTMX dans le header | Pas de JS custom — refresh partiel HTMX à chaque ajout/retrait |
| 12 | TTL session Django par défaut | Pas de TTL forcé sur le panier |
| 13 | Flow direct conservé pour tous les tarifs | "Payer maintenant" sur la page event reste intact, aucune régression |
| 14 | **Pas de nouveau validator webhook** — réutilisation de la cascade de signaux existante | `PRE_SAVE_TRANSITIONS` (`signals.py`) gère déjà N lignes via `TRIGGER_LigneArticlePaid_ActionByCategorie`. Seul `set_ligne_article_paid()` ligne 52-57 nécessite une adaptation mineure (itération sur les lignes au lieu de la FK `paiement_stripe.reservation` unique). |
| 15 | Paramètre `accept_sepa` sur `CreationPaiementStripe` | Le code actuel `if not self.reservation` active SEPA dès que la FK reservation est nulle. Pour un panier contenant des billets, on veut exclure SEPA (billets à utiliser rapidement). Ajout d'un flag explicite. |
| 16 | Page de confirmation = page "mes réservations" existante | `stripe_return` redirige déjà vers `/my_account/my_reservations/` pour l'utilisateur authentifié. Les N reservations + K memberships matérialisés par la commande y sont listés naturellement. Pas besoin d'une page dédiée. |
| 17 | Correction incidente du bug `ReservationValidator` overlap | Check actuel ligne 613 n'exclut pas `CANCELED`, ni les `UNPAID` abandonnées → user bloqué par sa propre resa abandonnée 3h plus tôt. Fix inclus : filtre `BLOCKING_STATUSES` + fenêtre 15 min pour `CREATED/UNPAID`, avec message explicite "paiement en cours". Cohérence flow direct / flow panier. |

---

## 3. Architecture

### 3.1 — Nouveau modèle `Commande`

Fichier : `BaseBillet/models.py`

```python
class Commande(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                              related_name='commandes')
    email_acheteur = models.EmailField()
    first_name = models.CharField(max_length=200)
    last_name = models.CharField(max_length=200)

    DRAFT = 'DRAFT'
    PENDING = 'PENDING'
    PAID = 'PAID'
    CANCELED = 'CANCELED'
    EXPIRED = 'EXPIRED'
    STATUS_CHOICES = [
        (DRAFT, _('Draft')),
        (PENDING, _('Pending payment')),
        (PAID, _('Paid')),
        (CANCELED, _('Canceled')),
        (EXPIRED, _('Expired')),
    ]
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=DRAFT)

    paiement_stripe = models.OneToOneField(
        'Paiement_stripe', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='commande_obj'
    )
    # Commentaire (FR) : OneToOne nullable — une commande gratuite (0€) n'a pas de Paiement_stripe.
    # Comment (EN): nullable OneToOne — a free order (0€) has no Paiement_stripe.

    promo_code = models.ForeignKey(
        'PromotionalCode', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='commandes'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ('-created_at',)
```

**Modifications sur les modèles existants** :

- `Reservation` : ajouter `commande = FK → Commande, nullable, related_name='reservations'`
- `Membership` : ajouter `commande = FK → Commande, nullable, related_name='memberships_commande'`

Les champs restent nullable pour garantir la rétrocompatibilité avec les anciennes Reservation/Membership créées sans panier.

### 3.2 — Format du panier en session

Structure stockée dans `request.session['panier']` :

```python
{
    "items": [
        {
            "type": "ticket",
            "event_uuid": "uuid-event-A",
            "price_uuid": "uuid-price",
            "qty": 2,
            "custom_amount": None,            # ou decimal string si free_price
            "options": ["uuid-option-1"],     # UUIDs d'OptionGenerale
            "custom_form": {"field": "val"},  # dict ProductFormField
        },
        {
            "type": "membership",
            "price_uuid": "uuid-price-adhesion",
            "custom_amount": None,
            "options": [],
            "custom_form": {},
        }
    ],
    "promo_code_name": "ETUDIANT10",  # ou None
    "created_at": "2026-04-17T12:00:00+00:00"
}
```

Clé stable : tout manipulé par un service dédié (`BaseBillet/services_panier.py`), jamais en direct depuis les vues.

### 3.3 — Service `PanierSession`

Fichier : `BaseBillet/services_panier.py` (nouveau)

```python
class PanierSession:
    """
    Gestionnaire du panier en session Django. Pure fonction : lit/écrit request.session.
    / Django session-backed cart manager. Pure function: reads/writes request.session.
    """
    SESSION_KEY = 'panier'

    def __init__(self, request):
        self.request = request
        self.session = request.session
        self.data = self._load()

    def _load(self) -> dict: ...
    def _save(self) -> None: ...

    # Opérations publiques
    def add_ticket(self, event_uuid, price_uuid, qty, *,
                    custom_amount=None, options=None, custom_form=None) -> None: ...
    def add_membership(self, price_uuid, *,
                         custom_amount=None, options=None, custom_form=None) -> None: ...
    def remove_item(self, index: int) -> None: ...
    def update_quantity(self, index: int, qty: int) -> None: ...
    def clear(self) -> None: ...

    # Code promo
    def set_promo_code(self, code_name: str) -> None: ...   # valide + stocke
    def clear_promo_code(self) -> None: ...

    # Lecture
    def items(self) -> list[dict]: ...
    def count(self) -> int: ...                             # nb total d'items (pour badge)
    def is_empty(self) -> bool: ...
    def total_ttc(self) -> Decimal: ...                     # total calculé avec promo appliqué
    def adhesions_product_ids(self) -> list[UUID]: ...      # products d'adhésion présents (pour cart-aware visibility)
    def has_recurring_membership(self) -> bool: ...         # toujours False — exclus à l'ajout
```

**Validations à l'ajout** (`add_ticket`, `add_membership`) :

- `Price` existe, `price.product.publish=True`
- **Pour `add_ticket`** :
  - `price.product.categorie_article in [BILLET, FREERES]`
  - `Event` existe, pas complet, en future
  - `price` est bien un price de l'event (via `event.products`)
  - `qty > 0`, respect de `price.max_per_user` et `price.out_of_stock()`
  - Si `adhesions_obligatoires` existe : vérifier `user.memberships` OU adhésion dans le panier (cart-aware)
  - Si `price.free_price` : valider `custom_amount >= price.prix`
- **Pour `add_membership`** :
  - `price.product.categorie_article == ADHESION`
  - **`price.recurring_payment is False`** → sinon raise `InvalidItemError("recurring_membership_not_allowed_in_cart")`
  - **`price.manual_validation is False`** → sinon raise `InvalidItemError("manual_validation_not_allowed_in_cart")`
  - Si `price.free_price` : valider `custom_amount`

### 3.4 — Service `CommandeService`

Fichier : `BaseBillet/services_commande.py` (nouveau)

Orchestrateur qui transforme un `PanierSession` en objets DB. **Transaction atomique** du début à la fin.

```python
class CommandeService:
    """
    Matérialisation d'un panier session en objets DB + création du paiement.
    / Materializes a session cart into DB objects + creates the payment.
    """

    @staticmethod
    @transaction.atomic
    def materialiser(panier: PanierSession, user: TibilletUser,
                      first_name: str, last_name: str, email: str) -> 'Commande':
        # 1. Re-validation complète du panier contre la DB
        # 2. Création Commande(status=PENDING)
        # 3. Phase 1 — Memberships (en premier pour que les tarifs gatés les voient)
        # 4. Phase 2 — Reservations + Tickets (groupés par event)
        # 5. Phase 3 — LigneArticle consolidées
        # 6. Phase 4a — Si total > 0 : CreationPaiementStripe → attache au Commande
        # 6. Phase 4b — Si total = 0 : marquage VALID/ONCE direct (méthode F / Membership.ONCE)
        # 7. Retour de la commande — la vue redirige vers Stripe ou vers la confirmation
        ...
```

**Séquence détaillée** :

**Phase 1 — Memberships** :
```python
for item in panier.items if item['type'] == 'membership':
    price = Price.objects.get(uuid=item['price_uuid'])
    membership = Membership.objects.create(
        user=user, price=price, commande=commande,
        contribution_value=montant(item, price),
        status=Membership.WAITING_PAYMENT,
        first_name=first_name, last_name=last_name,
        newsletter=False,  # opt-out côté panier par défaut v1
        custom_form=item.get('custom_form') or None,
    )
    if item.get('options'):
        membership.option_generale.set(item['options'])
    line = LigneArticle.objects.create(
        pricesold=get_or_create_price_sold(price, custom_amount=...),
        membership=membership,
        payment_method=PaymentMethod.STRIPE_NOFED,
        amount=dec_to_int(...),
        qty=1,
        sale_origin=SaleOrigin.LESPASS,
    )
    lignes.append(line)
```

**Phase 2 — Reservations** : groupement par event_uuid.
```python
tickets_par_event = {}
for item in panier.items if item['type'] == 'ticket':
    tickets_par_event.setdefault(item['event_uuid'], []).append(item)

for event_uuid, items in tickets_par_event.items():
    event = Event.objects.get(uuid=event_uuid)
    reservation = Reservation.objects.create(
        user_commande=user, event=event, commande=commande,
        custom_form=fusion_custom_forms(items) or None,
        status=Reservation.CREATED,
    )
    # Re-vérif cart-aware des tarifs gatés (user_memberships + memberships commande)
    # Création PriceSold, LigneArticle, Ticket pour chaque item
    # Réutilise TicketCreator ADAPTÉ (voir 3.5)
```

**Phase 3 — Consolidation** : toutes les `LigneArticle` créées (Phase 1 + 2) sont réunies dans une liste pour Stripe.

**Phase 4a — Paiement Stripe (total > 0)** :
```python
metadata = {
    'tenant': f'{tenant.uuid}',
    'tenant_name': f'{tenant.name}',
    'commande_uuid': f'{commande.uuid}',
    # pas de reservation_uuid ni membership_uuid : le commande_uuid suffit pour le webhook
}
new_paiement = CreationPaiementStripe(
    user=user,
    liste_ligne_article=toutes_lignes,
    metadata=metadata,
    reservation=None,                # pas de FK — le pivot est Commande
    source=Paiement_stripe.FRONT_BILLETTERIE,
    success_url='stripe_return/',
    cancel_url='stripe_return/',
    absolute_domain=f'https://{tenant.get_primary_domain()}/panier/',
)
commande.paiement_stripe = new_paiement.paiement_stripe_db
commande.save()
```

**Phase 4b — Panier gratuit (total = 0)** :
- Chaque `Membership` passe `Membership.ONCE` direct + `set_deadline()`.
- Chaque `Reservation` passe `Reservation.FREERES` ou `FREERES_USERACTIV` (selon `user.is_active`).
- Les `LigneArticle` passent à `VALID` avec `payment_method=FREE`.
- `Commande.status = PAID`, `paid_at = now`.
- Les signaux/tasks existants (envoi email, ticket PDF) se déclenchent comme aujourd'hui via les statuts.

### 3.5 — Adaptation `TicketCreator`

Fichier : `BaseBillet/validators.py`, classe existante `TicketCreator`.

Aujourd'hui `TicketCreator.__init__()` crée les tickets + appelle `get_checkout_stripe()` automatiquement (ligne 313 et 654). Pour le panier, on ne veut **pas** créer le checkout à ce moment — il sera créé par le `CommandeService` une fois toutes les lignes consolidées.

**Modification proposée** :
- Ajouter un paramètre `create_checkout: bool = True` au constructeur de `TicketCreator`.
- Quand `create_checkout=False` : ne pas appeler `self.get_checkout_stripe()` à la fin de `method_B()`.
- Zéro changement pour tous les appels existants (flow direct) — ils gardent `create_checkout=True` par défaut.

Le `CommandeService` appelle `TicketCreator(..., create_checkout=False)` pour chaque Reservation et récupère `ticket_creator.list_line_article_sold` pour consolidation.

### 3.6 — Webhook Stripe — adaptation minimale via cascade de signaux

**Insight d'audit** : la cascade de signaux Django existante (`BaseBillet/signals.py` — `PRE_SAVE_TRANSITIONS`) gère **déjà** un `Paiement_stripe` avec N `LigneArticle` pointant vers N reservations + K memberships. **Aucun nouveau validator webhook n'est nécessaire.**

**Flow actuel du webhook** (`ApiBillet.views.Webhook_stripe.post` ligne 1042+) :

```
checkout.session.completed arrive
  │
  └── paiement_stripe.update_checkout_status()
       │
       ├── paiement_stripe.status = PAID
       └── paiement_stripe.save()
            │
            └── pre_save_signal_status (signals.py:365)
                 │
                 └── set_ligne_article_paid()  ← UNIQUE POINT À ADAPTER
                      │
                      ├── pour chaque LigneArticle :
                      │    ligne.status = PAID ; ligne.save()
                      │    └── TRIGGER_LigneArticlePaid_ActionByCategorie
                      │         ├── trigger_B (BILLET) → send_sale_to_laboutik + ligne.status=VALID
                      │         └── trigger_A (ADHESION) → update_membership + email + ligne.status=VALID
                      └── "if paiement_stripe.reservation:" (ligne 52)
                           reservation.status = PAID ; reservation.save()
                           └── reservation_paid → active tickets + envoi mail
```

**Le SEUL point à modifier** : `set_ligne_article_paid()` dans `BaseBillet/signals.py` ligne 36-59.

**Code actuel** (ligne 52-57) :
```python
# s'il y a une réservation, on la met aussi en payée :
if new_instance.reservation:
    new_instance.reservation.status = Reservation.PAID
    new_instance.reservation.save()
```

**Code proposé** (rétrocompatible) :
```python
# Mise en PAID de TOUTES les reservations référencées par les lignes du paiement.
# Rétrocompat : si paiement_stripe.reservation (FK legacy) est set, on la traite.
# Nouveau : on itère aussi sur ligne.reservation pour supporter les paniers multi-events.
# / Move ALL reservations referenced by the payment's lines to PAID status.
# Backward compat: if paiement_stripe.reservation (legacy FK) is set, process it.
# New: also iterate on ligne.reservation to support multi-event carts.
reservations_a_valider = set()
if new_instance.reservation:
    reservations_a_valider.add(new_instance.reservation)
for ligne in new_instance.lignearticles.all():
    if ligne.reservation:
        reservations_a_valider.add(ligne.reservation)

for reservation in reservations_a_valider:
    reservation.status = Reservation.PAID
    reservation.save()
```

**Pourquoi c'est rétrocompatible** :
- Flow mono-event existant : `paiement_stripe.reservation` est set, `ligne.reservation` pointe vers la même reservation. Le `set()` dédoublonne → 1 seule reservation traitée, identique à l'existant.
- Flow adhésion-only existant : `paiement_stripe.reservation=None`, `ligne.reservation=None` (convention dans `MembershipValidator.get_checkout_stripe()` ligne 722). Le set est vide, pas de reservation traitée, identique à l'existant.
- Flow panier multi-events : `paiement_stripe.reservation=None`, N lignes ont `ligne.reservation` pointant vers N reservations. Le set contient N reservations, toutes passées en PAID.
- Flow crowds : `ligne.reservation=None` sur les lignes crowdfunding (pas de reservation). Identique.

**Cascade naturelle sur les Memberships multi** :
- `trigger_A (ADHESION)` agit ligne par ligne sur `ligne.membership` (FK directe sur LigneArticle).
- Pour un panier avec 2 adhésions, les 2 lignes correspondantes déclenchent chacune `trigger_A`, qui chacun :
  - met à jour SON membership (`update_membership_state_after_stripe_paiement`)
  - envoie SON email
- **Aucun changement nécessaire** dans `trigger_A`. C'est déjà "per-ligne".

**Cascade naturelle sur la Commande** (nouveau) :
- On ajoute un handler `post_save` léger sur `Paiement_stripe` qui détecte `status → VALID` et met à jour `Commande.status = PAID` + `paid_at = now`. Une fonction de 5 lignes dans `signals.py`.
- Alternative : une méthode sur `Paiement_stripe` appelée depuis `set_paiement_stripe_valid()` — mais l'approche post_save est moins intrusive.

### 3.7 — Adaptation `CreationPaiementStripe` — flag SEPA

**Problème détecté** : `PaiementStripe/views.py:159` active SEPA dès que `self.reservation` est `None`. Logique implicite actuelle : "pas de reservation = adhésion = SEPA OK". Pour un panier contenant des billets, `self.reservation=None` mais **on ne veut pas SEPA** (les billets doivent être utilisables rapidement).

**Modification** :
```python
# Avant (ligne 34-44)
def __init__(self, user, liste_ligne_article, metadata, reservation,
             source=None, absolute_domain=None, success_url=None, cancel_url=None,
             invoice=None):

# Après
def __init__(self, user, liste_ligne_article, metadata, reservation,
             source=None, absolute_domain=None, success_url=None, cancel_url=None,
             invoice=None, accept_sepa: bool = None):
    # accept_sepa : None = auto (True si reservation=None, sinon False) — comportement legacy
    #              True = forcer SEPA autorisé (adhésion-only)
    #              False = forcer SEPA refusé (panier avec billets)
    self.accept_sepa = accept_sepa
```

Puis dans `dict_checkout_creator()` :
```python
# Avant
if not self.reservation and self.config.stripe_accept_sepa:
    payment_method_types.append("sepa_debit")

# Après
sepa_authorized = self.accept_sepa if self.accept_sepa is not None else (not self.reservation)
if sepa_authorized and self.config.stripe_accept_sepa:
    payment_method_types.append("sepa_debit")
```

**Appel depuis `CommandeService`** :
```python
contains_tickets = any(item['type'] == 'ticket' for item in panier.items)
CreationPaiementStripe(
    ...,
    reservation=None,
    accept_sepa=False if contains_tickets else True,
)
```

**Rétrocompatibilité** : tous les appels existants passent `accept_sepa=None` (valeur par défaut) → comportement legacy strictement identique.

### 3.7 — Validator cart-aware pour `adhesions_obligatoires`

**Modification dans `ReservationValidator.validate()`** (`BaseBillet/validators.py:580`) :

```python
# Check adhésion — EXISTANT + cart-aware
if price.adhesions_obligatoires.exists():
    # Condition 1 : adhésion active déjà payée
    has_active_membership = user.memberships.filter(
        price__product__in=price.adhesions_obligatoires.all(),
        deadline__gte=timezone.now(),
    ).exists()

    # Condition 2 (NOUVEAU) : adhésion dans la commande en cours
    # Uniquement quand le validator est appelé depuis CommandeService
    has_in_current_order = False
    if hasattr(self, 'current_commande'):
        required_products = list(price.adhesions_obligatoires.all())
        has_in_current_order = self.current_commande.memberships_commande.filter(
            price__product__in=required_products
        ).exists()

    if not (has_active_membership or has_in_current_order):
        raise serializers.ValidationError(_("User is not subscribed."))
```

Le `CommandeService`, avant d'appeler `ReservationValidator`, injecte `validator.current_commande = commande` (qui contient déjà les Memberships créés en Phase 1).

**Visibilité côté page event** — le template lit le panier via context processor (voir 3.8) et peut marquer les tarifs gatés comme "sélectionnables" si `panier.adhesions_product_ids` matche `price.adhesions_obligatoires`. Implémentation visuelle : un bandeau sur le tarif *"Nécessite l'adhésion X — ajoutez-la au panier pour débloquer ce tarif"*.

### 3.7bis — Détection de chevauchement temporel (quand `allow_concurrent_bookings=False`)

**Contexte** : si la config tenant interdit les bookings concurrents, un user ne peut pas avoir 2 reservations chevauchantes temporellement.

**Bug existant corrigé au passage** : `ReservationValidator.validate()` ligne 613 vérifie aujourd'hui les overlaps **sans filtrer sur le statut**, ce qui inclut `CANCELED` et les reservations `UNPAID` abandonnées. Conséquence : un user qui a abandonné un paiement 3h plus tôt ne peut plus rien réserver sur le créneau.

**Nouvelle logique de blocage** — constante partagée `BaseBillet/models.py` (ou fichier dédié) :

```python
# Statuts qui bloquent inconditionnellement un chevauchement.
# / Statuses that unconditionally block an overlap.
BLOCKING_STATUSES = [
    Reservation.PAID,
    Reservation.VALID,
    Reservation.PAID_ERROR,          # billet existe même si email KO
    Reservation.PAID_NOMAIL,         # idem
    Reservation.FREERES,             # gratuit, en attente validation email
    Reservation.FREERES_USERACTIV,   # gratuit confirmé
]

# Statuts qui bloquent uniquement si la reservation est récente (< 15 min).
# / Statuses that block only if the reservation is recent (< 15 min).
# Cohérent avec event.under_purchase() qui utilise le même TTL.
RECENT_BLOCKING_STATUSES = [
    Reservation.CREATED,
    Reservation.UNPAID,
]
RECENT_BLOCKING_WINDOW = timedelta(minutes=15)
```

**Filtre à appliquer** (utilisé à la fois dans `PanierSession.add_ticket()` et dans `ReservationValidator.validate()`) :

```python
from django.db.models import Q

def _reservations_bloquantes_pour_user(user, start, end):
    """
    Retourne le queryset des reservations du user qui chevauchent [start, end]
    et qui bloquent une nouvelle réservation.
    / Returns the queryset of user's reservations that overlap [start, end]
    and block a new booking.
    """
    overlap_q = (
        Q(event__datetime__range=(start, end)) |
        Q(event__end_datetime__range=(start, end)) |
        Q(event__datetime__lte=start, event__end_datetime__gte=end)
    )

    # Blocage inconditionnel / unconditional block
    blocage_dur = Reservation.objects.filter(
        user_commande=user,
        status__in=BLOCKING_STATUSES,
    ).filter(overlap_q)

    # Blocage si récent (< 15 min) / block if recent (< 15 min)
    seuil_recent = timezone.now() - RECENT_BLOCKING_WINDOW
    blocage_recent = Reservation.objects.filter(
        user_commande=user,
        status__in=RECENT_BLOCKING_STATUSES,
        datetime__gte=seuil_recent,
    ).filter(overlap_q)

    return blocage_dur.union(blocage_recent)
```

**Messages d'erreur différenciés** (à l'ajout panier) :

```python
# Si la resa bloquante est dans BLOCKING_STATUSES (dur)
raise InvalidItemError(
    _("You already have a booking that overlaps with this event: %(name)s")
    % {"name": resa_bloquante.event.name}
)

# Si la resa bloquante est dans RECENT_BLOCKING_STATUSES (récente)
raise InvalidItemError(
    _("You have a payment in progress for an event that overlaps with this one: %(name)s. "
      "Please complete it or wait 15 minutes before trying another booking.")
    % {"name": resa_bloquante.event.name}
)
```

**Application dans `PanierSession.add_ticket()`** (après les validations standards) :

```python
if not Configuration.get_solo().allow_concurrent_bookings:
    start = event.datetime
    end = event.end_datetime or (start + timedelta(hours=1))

    # Cas A : chevauchement avec un autre item déjà dans le panier
    for item in self.items():
        if item['type'] != 'ticket' or item['event_uuid'] == str(event_uuid):
            continue
        other_event = Event.objects.get(uuid=item['event_uuid'])
        other_start = other_event.datetime
        other_end = other_event.end_datetime or (other_start + timedelta(hours=1))
        if (start < other_end) and (other_start < end):
            raise InvalidItemError(
                _("This event overlaps with another event in your cart: %(name)s")
                % {"name": other_event.name}
            )

    # Cas B : chevauchement avec une reservation existante du user (BD)
    if self.request.user.is_authenticated:
        conflit = _reservations_bloquantes_pour_user(
            self.request.user, start, end,
        ).first()
        if conflit:
            if conflit.status in BLOCKING_STATUSES:
                msg = _("You already have a booking that overlaps with this event: %(name)s")
            else:
                msg = _("You have a payment in progress for an event that overlaps with this one: "
                        "%(name)s. Please complete it or wait 15 minutes before trying another booking.")
            raise InvalidItemError(msg % {"name": conflit.event.name})
```

**Correction du validator existant** — `BaseBillet/validators.py:606-620` devient :

```python
if not Configuration.get_solo().allow_concurrent_bookings:
    start_this_event = event.datetime
    end_this_event = event.end_datetime or (start_this_event + timedelta(hours=1))

    conflit = _reservations_bloquantes_pour_user(
        user, start_this_event, end_this_event,
    ).first()
    if conflit:
        if conflit.status in BLOCKING_STATUSES:
            raise serializers.ValidationError(
                _("You have already booked this slot: %(name)s") % {"name": conflit.event.name}
            )
        else:
            raise serializers.ValidationError(
                _("You have a payment in progress for this slot: %(name)s. "
                  "Please complete it or wait 15 minutes.") % {"name": conflit.event.name}
            )
```

**Bénéfice** :
- Flow direct existant (mono-event) : corrigé, plus de blocage par resa `CANCELED` ou `UNPAID` ancienne.
- Flow panier : même règle, UX cohérente entre les deux.

### 3.8 — Context processor panier

Fichier : `BaseBillet/context_processors.py` (existant — on ajoute une fonction).

```python
def panier_context(request):
    """
    Expose le panier courant aux templates.
    Disponible partout via {{ panier.count }}, {{ panier.items }}, etc.
    """
    from BaseBillet.services_panier import PanierSession
    panier = PanierSession(request)
    return {
        'panier': {
            'count': panier.count(),
            'is_empty': panier.is_empty(),
            'items_with_details': panier.items_with_details(),  # items enrichis (Event, Price, Product)
            'total_ttc': panier.total_ttc(),
            'adhesions_product_ids': panier.adhesions_product_ids(),
            'promo_code_name': panier.data.get('promo_code_name'),
        }
    }
```

À enregistrer dans `TEMPLATES[0]['OPTIONS']['context_processors']` de `settings.py`.

### 3.9 — URLs et vues HTMX

Fichier : `BaseBillet/urls.py` + `BaseBillet/views.py`.

| Méthode | URL | Vue | Rôle |
|---|---|---|---|
| `POST` | `/panier/add/ticket/` | `PanierMVT.add_ticket` | Ajoute N billets d'un event (depuis modal event) |
| `POST` | `/panier/add/membership/` | `PanierMVT.add_membership` | Ajoute une adhésion (depuis modal adhésion) |
| `POST` | `/panier/remove/<int:index>/` | `PanierMVT.remove_item` | Retire un item (depuis page panier) |
| `POST` | `/panier/update-quantity/<int:index>/` | `PanierMVT.update_quantity` | Change la quantité d'un item |
| `POST` | `/panier/promo-code/` | `PanierMVT.set_promo_code` | Applique un code promo |
| `POST` | `/panier/promo-code/clear/` | `PanierMVT.clear_promo_code` | Retire le code promo |
| `POST` | `/panier/clear/` | `PanierMVT.clear` | Vide le panier |
| `GET` | `/panier/` | `PanierMVT.view` | Page panier (récap, modif, total, bouton checkout) |
| `POST` | `/panier/checkout/` | `PanierMVT.checkout` | Appelle `CommandeService.materialiser()` → Stripe ou confirmation |
| `GET` | `/panier/badge/` | `PanierMVT.badge` | Partial HTMX : badge compteur pour header |

Toutes les vues de manipulation retournent un partial HTMX refresh du badge + message toast.

### 3.10 — Modal "Ajouter au panier / Payer maintenant"

Déclenchement : au clic sur "Valider" dans un formulaire de sélection de tarifs (page event ou page adhésion).

Comportement :
- Si le tarif contient `recurring_payment=True` → modal n'affiche que "Payer maintenant" (flow direct)
- Sinon → modal avec deux boutons :
  - **"Ajouter au panier"** → POST `/panier/add/ticket/` ou `/panier/add/membership/`, refresh du badge, toast "Ajouté au panier"
  - **"Payer maintenant"** → flow actuel (crée Reservation ou Membership direct, checkout Stripe immédiat)

Pas de sur-ingénierie : un template partial `htmx/components/modal_ajouter_panier.html`, deux boutons, un `hx-post` chacun.

---

## 4. Restrictions v1

| Cas | Décision |
|---|---|
| Adhésion `recurring_payment=True` | **Exclue du panier** — flow direct uniquement. Validation dans `PanierSession.add_membership()` raise `InvalidItemError`. |
| Adhésion `manual_validation=True` | **Exclue du panier** — flow direct uniquement. Idem validation à l'ajout. |
| Event `Event.ACTION` (sans tarif) | **Exclue du panier** — pas de sens d'ajouter une action au panier. |
| Code promo | **1 seul actif par panier**, stocké en session. Appliqué aux lignes dont `product == code.product`. Autres lignes plein tarif. |
| Quantités gratuit + payant dans le même panier | **Autorisé** — géré via les statuts existants (ligne gratuite VALID direct, ligne payante attend webhook). |
| Panier 100% gratuit | **Autorisé** — pas de Stripe, tout VALID/ONCE + envoi email confirmation. |
| Panier multi-users | **Non supporté** — un panier = une session = un utilisateur. |
| Récupération après logout/login | **Non supporté v1** — session Django expire, panier perdu. |
| Per-billet nominatif | **Non supporté v1** — un seul nom/email pour tous les billets. |
| Multi-devices | **Non supporté v1** — session cookie per-device. |

---

## 5. Data flow complet

```
USER                    BROWSER                    DJANGO                      DB                    STRIPE
 │                         │                          │                          │                      │
 │  Sélectionne 2 billets  │                          │                          │                      │
 │  event A, clique Valider│                          │                          │                      │
 │────────────────────────>│                          │                          │                      │
 │                         │  POST validate_event     │                          │                      │
 │                         │─────────────────────────>│                          │                      │
 │                         │  Modal HTMX              │                          │                      │
 │                         │<─────────────────────────│                          │                      │
 │  Clique "Ajouter panier"│                          │                          │                      │
 │────────────────────────>│                          │                          │                      │
 │                         │  POST /panier/add/ticket/│                          │                      │
 │                         │─────────────────────────>│                          │                      │
 │                         │                          │ PanierSession.add_ticket │                      │
 │                         │                          │ (validation + session)   │                      │
 │                         │  Badge 2 + toast         │                          │                      │
 │                         │<─────────────────────────│                          │                      │
 │                         │                          │                          │                      │
 │  Va sur event B,        │                          │                          │                      │
 │  ajoute 1 billet        │                          │                          │                      │
 │  Puis adhésion X        │                          │                          │                      │
 │  (même parcours)        │                          │                          │                      │
 │                         │                          │                          │                      │
 │  Va sur /panier/        │                          │                          │                      │
 │  Clique "Passer paiement"                          │                          │                      │
 │────────────────────────>│                          │                          │                      │
 │                         │  POST /panier/checkout/  │                          │                      │
 │                         │─────────────────────────>│                          │                      │
 │                         │                          │ CommandeService.materialiser()                  │
 │                         │                          │ ─ BEGIN ATOMIC ─         │                      │
 │                         │                          │   re-validate            │                      │
 │                         │                          │   create Commande────────>│                      │
 │                         │                          │   Phase 1 : Membership ──>│                      │
 │                         │                          │   Phase 2 : Reservation+ ─>│                      │
 │                         │                          │             Ticket+LineArt │                      │
 │                         │                          │   Phase 3 : CreationPaiementStripe ──────────────>│
 │                         │                          │                          │  checkout.Session.create
 │                         │                          │<──────────────────────────────────── session.url │
 │                         │                          │   commande.paiement = ───>│                      │
 │                         │                          │ ─ END ATOMIC ─           │                      │
 │                         │ 302 redirect Stripe      │                          │                      │
 │                         │<─────────────────────────│                          │                      │
 │   Paye sur Stripe       │                          │                          │                      │
 │─────────────────────────────────────────────────────────────────────────────────────────────────────>│
 │                         │                          │  POST /webhook/ stripe   │                      │
 │                         │                          │<────────────────────────────────────────────────│
 │                         │                          │ Webhook_stripe.post (inchangé)                  │
 │                         │                          │  → paiement_stripe.update_checkout_status()     │
 │                         │                          │     status = PAID → .save()                     │
 │                         │                          │                                                 │
 │                         │                          │ Cascade signaux (inchangée sauf 1 patch) :      │
 │                         │                          │  set_ligne_article_paid() [PATCHÉ]              │
 │                         │                          │   → itère sur ligne.reservation (set)           │
 │                         │                          │   → N reservations → PAID chacune               │
 │                         │                          │  Chaque ligne passée en PAID → trigger_B/trigger_A │
 │                         │                          │   → tâche Celery email + set ligne VALID        │
 │                         │                          │  Toutes lignes VALID → paiement_stripe VALID    │
 │                         │                          │  post_save Paiement_stripe → Commande.PAID      │
 │                         │                          │                          │                      │
 │   Redirect success      │                          │                          │                      │
 │<────────────────────────────────────────────────────────────────────────────────────────────────────│
 │   Page confirmation avec tous les tickets + adhésion                          │                      │
```

---

## 6. Fichiers à créer / modifier

| Fichier | Action | Complexité |
|---|---|---|
| `BaseBillet/models.py` | Modifier — `Commande`, FK sur `Reservation`/`Membership` | Simple |
| `BaseBillet/migrations/XXXX_commande.py` | Créer | Simple |
| `BaseBillet/services_panier.py` | Créer — `PanierSession` | Moyen |
| `BaseBillet/services_commande.py` | Créer — `CommandeService.materialiser()` | Moyen |
| `BaseBillet/validators.py` | Modifier — `TicketCreator(create_checkout=bool)`, `ReservationValidator` cart-aware | Moyen |
| `BaseBillet/views.py` | Modifier — `PanierMVT` (10 actions) uniquement | Moyen |
| `BaseBillet/urls.py` | Modifier — URLs panier | Simple |
| `BaseBillet/context_processors.py` | Modifier — `panier_context()` | Simple |
| `TiBillet/settings.py` | Modifier — ajout `panier_context` aux TEMPLATES | Simple |
| `BaseBillet/signals.py` | Modifier — `set_ligne_article_paid()` : itération sur `ligne.reservation` au lieu de FK unique + post_save handler pour `Commande.status = PAID` | Simple |
| `PaiementStripe/views.py` | Modifier — ajout param `accept_sepa` à `CreationPaiementStripe.__init__` + adaptation `dict_checkout_creator()` | Simple |
| `ApiBillet/views.py` | **Aucune modification** — `Webhook_stripe.post` reste inchangé, la cascade de signaux gère le panier naturellement | — |
| `BaseBillet/templates/htmx/components/modal_ajouter_panier.html` | Créer | Simple |
| `BaseBillet/templates/htmx/components/panier_badge.html` | Créer | Simple |
| `BaseBillet/templates/htmx/views/panier.html` | Créer — page panier | Moyen |
| `BaseBillet/templates/htmx/views/panier_confirmation.html` | Créer — page confirmation post-paiement | Simple |
| `BaseBillet/templates/includes/header.html` (ou similaire) | Modifier — ajout icône panier | Simple |
| `BaseBillet/templates/htmx/views/event.html` | Modifier — cart-aware visibility des tarifs gatés | Simple |
| `tests/pytest/test_panier_service.py` | Créer — tests PanierSession | Moyen |
| `tests/pytest/test_commande_service.py` | Créer — tests CommandeService (atomicité, phases) | Moyen |
| `tests/pytest/test_panier_cart_aware_adhesion.py` | Créer — tarifs gatés débloqués via panier | Moyen |
| `tests/pytest/test_panier_signals_cascade.py` | Créer — non-régression `set_ligne_article_paid` + cascade multi-reservations | Moyen |
| `tests/pytest/test_panier_sepa_flag.py` | Créer — `accept_sepa` respecté selon contenu panier | Simple |
| `tests/pytest/test_overlap_blocking_statuses.py` | Créer — chevauchement temporel : BLOCKING_STATUSES, fenêtre 15 min pour UNPAID/CREATED, non-régression flow direct | Moyen |
| `tests/playwright/tests/XX-panier-multi-events.spec.ts` | Créer — E2E ajout multi-events + checkout Stripe | Moyen |

---

## 7. Découpage en sessions

| Session | Titre | Livrable | Dépend de |
|---|---|---|---|
| **01** | Modèle Commande + migration | `Commande`, FK sur Reservation/Membership, migration, tests modèles | — |
| **02** | Services panier + commande | `PanierSession`, `CommandeService.materialiser()`, adaptation `TicketCreator`, tests pytest | 01 |
| **03** | Patch signals + cart-aware validator | Patch `set_ligne_article_paid()` (itération sur lignes) + post_save `Commande.PAID` + `accept_sepa` sur `CreationPaiementStripe` + `ReservationValidator` cart-aware, tests de non-régression sur flows existants | 02 |
| **04** | Vues HTMX + context processor | `PanierMVT`, URLs, context processor, tests pytest vues | 02 |
| **05** | Templates frontend | Modal, page panier, badge header, cart-aware event.html, page confirmation | 04 |
| **06** | Tests E2E + polish | Tests Playwright (ajout multi-events, checkout, cas promo, cas gratuit, tarifs gatés), a11y, i18n | 05 |

Un livrable par session, pytest + manage.py check OK avant de passer à la suivante.

---

## 8. Risques et points de vigilance

| Risque | Mitigation |
|---|---|
| Divergence session vs DB (prix changé entre ajout et checkout) | Re-validation complète à chaque opération et au checkout |
| Panier avec item dont `price.publish=False` | Validation bloque l'ajout, re-validation filtre au checkout |
| Stock épuisé entre ajout et paiement | Pas de hold en session — message clair à l'utilisateur au moment du checkout si rupture. Identique au comportement actuel (matérialisation uniquement au checkout, comme le flow direct existant). |
| Webhook Stripe arrive avant que la Commande soit commit (race) | Transaction atomique garantit qu'au moment où Stripe peut appeler le webhook, la commande est déjà commit en DB |
| Utilisateur a déjà l'adhésion requise activée + ajoute une 2e adhésion du même product au panier | Bloqué par `max_per_user` sur `Price` si défini, ou autorisé (family membership) — comportement identique à aujourd'hui |
| Code promo atteint `usage_limit` entre ajout et checkout | Re-validation au checkout rejette le code et applique plein tarif, avec message |
| Adhésion récurrente tentée via API bypassant le front | Check backend dur dans `add_membership()` → `InvalidItemError` |
| Champs `nullable` sur `Reservation.commande` et `Membership.commande` | Acceptés — les flows directs existants continuent de créer des objets sans `commande` |
| Double paiement d'une même commande si user recharge | `status=PENDING` bloque `materialiser()` s'il détecte une commande PENDING récente pour le même user → possible amélioration v2 |
| Panier contenant des events chevauchants temporellement | Si `Configuration.allow_concurrent_bookings=False` : rejet dès l'ajout au panier (cf. section 3.7bis). Check contre les autres items du panier + contre les reservations en DB du user. Correction incidente d'un bug pré-existant (toutes reservations comptaient, y compris `CANCELED` et `UNPAID` abandonnées). v1 : blocage inconditionnel pour `[PAID, VALID, PAID_ERROR, PAID_NOMAIL, FREERES, FREERES_USERACTIV]`, blocage récent (< 15 min) pour `[CREATED, UNPAID]` avec message explicite "paiement en cours, finalisez ou attendez 15 min". |
| Événement passe complet entre ajout panier et checkout | `event.complet()` (models.py:2299) utilise `valid_tickets_count + under_purchase` avec un TTL 15min. Au checkout, re-validation lève "Number of places available : X" → user voit le message, peut réduire la quantité. Comportement identique au flow direct d'aujourd'hui. |
| Cascade signaux : `set_ligne_article_paid()` avant patch validait `paiement_stripe.reservation` (FK unique) — après patch itère sur `ligne.reservation` (set) | **Rétrocompatibilité validée** : flow mono-event = même reservation sur FK unique ET sur `ligne.reservation`, le `set()` dédoublonne → 1 seule reservation traitée, comportement strictement identique. Flow adhésion-only = set vide, identique. |
| SEPA activé par erreur sur un panier contenant des billets | Le flag `accept_sepa=False` est passé explicitement depuis `CommandeService` quand `contains_tickets=True`. Par défaut (None), comportement legacy préservé. |
| Multiples emails (1 par reservation + 1 par adhésion) au lieu d'un récapitulatif | **Accepté en v1** — cohérent avec le code existant (`trigger_A` envoie un mail par adhésion via `send_membership_invoice_to_email`, `reservation_paid` envoie un mail par resa via `ticket_celery_mailer`). Un mail unique récapitulatif = v2. |
| Fedow intégration : `trigger_A` appelle `fedowAPI.membership.create` pour chaque adhésion | Traité par ligne, transparent pour le panier. Un échec Fedow est non-bloquant (try/except dans trigger_A). |
| Laboutik sync : `send_sale_to_laboutik.delay(ligne.pk)` appelé par ligne | Traité ligne par ligne, identique à aujourd'hui. Pas de régression. |
| WebSocket broadcast jauge : `broadcast_jauge_apres_ticket_save` déclenché à chaque Ticket save | Pour un panier N events, N broadcasts distincts — un par event concerné. Comportement attendu. |

---

## 9. Tests prévus

**Tests pytest** :
- `PanierSession` : ajout/retrait/modif, validations, rejet `recurring_payment`, rejet `manual_validation`, code promo
- `CommandeService.materialiser()` :
  - cas nominal multi-events + adhésion
  - cas panier gratuit (total 0€)
  - cas mix gratuit + payant
  - cas échec stock → rollback complet
  - cas code promo appliqué sur 1 ligne
  - Phase 1 adhésion crée Membership avant Phase 2 (tarif gaté débloqué)
- `ReservationValidator` cart-aware : tarif gaté accepté si adhésion dans la commande
- Chevauchement temporel — `_reservations_bloquantes_pour_user()` :
  - **Non-régression** : 2 resa sur créneaux chevauchants avec statuts PAID → bloque (comportement identique)
  - **Correction** : resa CANCELED chevauchante → ne bloque plus
  - **Correction** : resa UNPAID de > 15 min → ne bloque plus (fix bug existant)
  - **Nouveau** : resa UNPAID de < 15 min → bloque avec message "paiement en cours, finalisez ou attendez 15 minutes"
  - **Nouveau panier** : 2 items panier sur créneaux chevauchants → 2e ajout refusé avec message explicite
  - **Anonyme** : pas de check DB (pas d'identification user) → check au checkout uniquement
- Cascade signaux `set_ligne_article_paid()` patché :
  - **Non-régression** flow mono-event : 1 seule reservation traitée (FK unique)
  - **Non-régression** flow adhésion-only : aucune reservation traitée (set vide)
  - **Nouveau** flow panier multi-events : N reservations passées en PAID
  - **Nouveau** flow panier gratuit : pas de Stripe, tout passe direct en FREERES/ONCE
- `CreationPaiementStripe(accept_sepa=...)` :
  - `None` (legacy) : SEPA activé seulement si `reservation=None` ET config SEPA ON
  - `False` : SEPA toujours désactivé (panier avec billets)
  - `True` : SEPA activé si config SEPA ON (adhésion-only)
- `post_save Paiement_stripe` : déclenche `Commande.status=PAID` + `paid_at=now` quand paiement VALID
- Webhook `Webhook_stripe.post` **inchangé** — test de non-régression que les flows existants passent toujours

**Tests Playwright E2E** :
- Flow complet : ajout 2 events + 1 adhésion → checkout Stripe → confirmation
- Flow mixte : billet payant + billet gratuit → paiement partiel + email validation
- Flow adhésion requise : ajouter adhésion → tarif gaté devient sélectionnable → checkout
- Rejet adhésion récurrente : modal n'affiche que "Payer maintenant"
- Code promo : appliqué à la bonne ligne, autres lignes plein tarif

---

## 10. Non-objectifs (explicitement hors scope)

- Panier persisté en DB entre sessions
- Relance email panier abandonné
- Panier multi-devices / multi-sessions
- Panier partagé entre utilisateurs (achat groupé)
- Nominatif par billet
- Adhésions récurrentes dans le panier
- Adhésions à validation manuelle dans le panier
- Factures PDF consolidées (une commande = une facture)
- Upsell / cross-sell dans le panier
- Codes promo multiples
- Exports comptables liés à la Commande (reste au niveau LigneArticle, comme aujourd'hui)
