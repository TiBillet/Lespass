"""
Gestionnaire du panier en session Django.
/ Django session-backed cart manager.

Le panier vit uniquement dans request.session['panier']. Aucune écriture
en DB à ce niveau — la matérialisation se fait dans CommandeService.

/ The cart lives only in request.session['panier']. No DB writes at this
level — materialization happens in CommandeService.
"""
import logging
from datetime import timedelta
from decimal import Decimal

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

    # --- Total + revalidation (Session 07 — S5 + S6) ---
    # --- Total + revalidation (Session 07 — S5 + S6) ---

    def calcul_total_centimes(self):
        """
        Total TTC du panier en centimes (int). Source de vérité unique pour
        les totaux pré-matérialisation. Utilisé par le context processor et
        par materialiser() pour la détection "panier gratuit".
        / Cart TTC total in cents (int). Single source of truth for
        pre-materialization totals.
        """
        from BaseBillet.models import Price
        total = 0
        for item in self._data.get('items', []):
            try:
                price = Price.objects.get(uuid=item['price_uuid'])
            except Price.DoesNotExist:
                continue
            if price.free_price and item.get('custom_amount'):
                amount_eur = Decimal(str(item['custom_amount']))
            else:
                amount_eur = price.prix or Decimal("0.00")
            qty = int(item.get('qty', 1))
            total += int(amount_eur * qty * 100)
        return total

    def revalidate_all(self):
        """
        Re-applique toutes les validations d'add sur les items présents.
        Appelé par CommandeService.materialiser() en Phase 0.
        Lève InvalidItemError sur le premier item invalide (stock épuisé,
        price dépublié, adhésion obligatoire plus disponible, etc.).
        / Re-apply all add validations on present items. Called by
        materialiser() in Phase 0. Raises InvalidItemError on first invalid.
        """
        # Copie des items (on va les re-injecter un par un)
        # / Copy items (we'll re-inject one by one)
        items_snapshot = list(self._data.get('items', []))
        self._data['items'] = []
        self._save()
        for item in items_snapshot:
            if item['type'] == 'ticket':
                self.add_ticket(
                    event_uuid=item['event_uuid'],
                    price_uuid=item['price_uuid'],
                    qty=item['qty'],
                    custom_amount=item.get('custom_amount'),
                    options=item.get('options', []),
                    custom_form=item.get('custom_form', {}),
                )
            elif item['type'] == 'membership':
                self.add_membership(
                    price_uuid=item['price_uuid'],
                    custom_amount=item.get('custom_amount'),
                    options=item.get('options', []),
                    custom_form=item.get('custom_form', {}),
                )
