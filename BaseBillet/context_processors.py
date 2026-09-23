"""
Context processors BaseBillet.
/ BaseBillet context processors.

Expose le panier courant a tous les templates via {{ panier }}.
/ Exposes the current cart to all templates via {{ panier }}.
"""
from datetime import datetime
import logging
from decimal import Decimal

from django.utils.functional import SimpleLazyObject

from booking.models import Resource

logger = logging.getLogger(__name__)


def _valeur_a_la_demande(nom_de_la_valeur, calcul, valeur_si_le_panier_est_abime):
    """
    Rend une valeur calculée SEULEMENT si un gabarit la lit, et jamais deux fois.
    / Returns a value computed ONLY when a template reads it, and never twice.

    LOCALISATION : BaseBillet/context_processors.py

    Ce context processor tourne à chaque rendu de page, alors que le détail des articles, le
    total et les adhésions du panier ne sont lus que par la page du panier et les formulaires
    de vente. Les calculer d'avance coûterait plusieurs requêtes par article sur tout le site.
    / This context processor runs on every render, while these values are only read by the
    cart page and the sale forms: computing them eagerly would cost queries on every page.

    Le panier vit en session : une donnée abîmée ne doit pas casser le rendu de la page. On
    rend alors la valeur vide, comme le filet de `panier_context`.
    / The cart lives in the session: damaged data must not break the page render.
    """
    def _calculer_maintenant():
        try:
            return calcul()
        except Exception as exc:
            logger.warning(f"panier_context ({nom_de_la_valeur}) a échoué : {exc}")
            return valeur_si_le_panier_est_abime

    return SimpleLazyObject(_calculer_maintenant)


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
        # `count`, `is_empty`, `items` et le code promo se lisent dans la session : aucune
        # requête. Les trois autres valeurs coûtent des requêtes par article : elles ne sont
        # calculées que si un gabarit les lit (voir _valeur_a_la_demande).
        # Source de vérité unique du total : PanierSession.calcul_total_centimes(), converti
        # en euros pour l'affichage.
        # / The first values are read from the session (no query). The three others cost
        # queries per item: they are computed only when a template reads them.
        return {
            'panier': {
                'count': panier.count(),
                'is_empty': panier.is_empty(),
                'items': panier.items(),
                'items_with_details': _valeur_a_la_demande(
                    'items_with_details', lambda: _build_items_with_details(panier), []
                ),
                'total_ttc': _valeur_a_la_demande(
                    'total_ttc',
                    lambda: Decimal(panier.calcul_total_centimes()) / Decimal(100),
                    Decimal('0.00'),
                ),
                'adhesions_product_ids': _valeur_a_la_demande(
                    'adhesions_product_ids', panier.adhesions_product_ids, []
                ),
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
    from BaseBillet.services_panier import montant_apres_remise
    result = []
    # `index` = rang de l'item dans le panier en session. Le bouton « retirer » l'envoie à
    # `/panier/<index>/remove/`. On ne peut PAS utiliser le rang d'affichage : un item dont le
    # tarif, l'événement ou la ressource a disparu est sauté ci-dessous, et les rangs
    # d'affichage ne correspondraient plus à ceux de la session.
    # / `index` = the item's position in the session cart, sent by the remove button. The
    # display position cannot be used: skipped items would shift it.
    for index, item in enumerate(panier.items()):
        try:
            price = Price.objects.get(uuid=item['price_uuid'])
            product = price.product
        except Price.DoesNotExist:
            # Price supprime depuis l'ajout au panier : on skip silencieusement.
            # / Price deleted since cart add: skip silently.
            continue

        detail = {
            'index': index,
            'type': item['type'],
            'price': price,
            'product': product,
            'qty': item.get('qty', 1),
            'custom_amount': item.get('custom_amount'),
            'options': item.get('options', []),
            'firstname': item.get('firstname', ""),
            'custom_form': item.get('custom_form', {}),
        }
        if item['type'] == 'ticket':
            try:
                event = Event.objects.get(uuid=item['event_uuid'])
                detail['event'] = event
            except Event.DoesNotExist:
                continue

            # Code promo : le panier affiche le prix avant remise, le prix remisé et le code,
            # calculés comme au paiement (PanierSession.code_promo_du_billet,
            # montant_apres_remise).
            # / Promo code: price before discount, discounted price and code, as at checkout.
            code_promo = panier.code_promo_du_billet(item, price)
            detail['code_promo'] = code_promo
            if code_promo:
                if price.free_price and item.get('custom_amount'):
                    prix_avant_remise = Decimal(str(item['custom_amount']))
                else:
                    prix_avant_remise = price.prix or Decimal("0.00")
                detail['prix_avant_remise'] = prix_avant_remise
                detail['prix_remise'] = montant_apres_remise(prix_avant_remise, code_promo)
        if item['type'] == 'resource':
            try:
                resource = Resource.objects.get(pk=item['resource_uuid'])
                detail['resource'] = resource
                # ValueError : une date de créneau abîmée en session ne doit pas casser la
                # page — l'article est simplement sauté, comme un tarif supprimé.
                # / ValueError: a damaged slot date in the session must not break the page.
                detail['start_datetime'] = datetime.fromisoformat(item.get("start_datetime"))

                detail['slot_duration_minutes'] = item.get("slot_duration_minutes")
                detail['slot_count'] = item.get("slot_count")
                detail['total_estimation'] = item.get("total_estimation")
                detail['hours'] = item.get("hours")

            except (Resource.DoesNotExist, ValueError, TypeError):
                continue

        result.append(detail)
    return result


