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
