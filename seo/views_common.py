"""
Helpers SEO : lecteur cache L1/L2, builders JSON-LD, robots.txt.
/ SEO helpers: L1/L2 cache reader, JSON-LD builders, robots.txt.

LOCALISATION: seo/views_common.py
"""

import logging

from django.http import HttpResponse

from seo.models import SEOCache
from seo.services import get_memcached_l1, set_memcached_l1

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lecteur cache L1 (Memcached) -> L2 (DB) / L1 (Memcached) -> L2 (DB) reader
# ---------------------------------------------------------------------------


def get_seo_cache(cache_type, tenant_uuid=None):
    """
    Tente Memcached L1 en premier. En cas de miss, lit depuis SEOCache (DB L2)
    et recharge L1 pour les prochains appels.
    / Try Memcached L1 first. On miss, read from SEOCache (DB L2)
    and reload L1 for subsequent calls.

    Parametres / Parameters:
        cache_type: une des constantes SEOCache (ex. SEOCache.AGGREGATE_EVENTS)
        tenant_uuid: UUID du tenant, ou None pour les agregats globaux

    Retourne / Returns:
        dict ou None si aucune donnee trouvee
    """
    # Essai L1 (Memcached) / Try L1 (Memcached)
    data_from_l1 = get_memcached_l1(cache_type, tenant_uuid)
    if data_from_l1 is not None:
        return data_from_l1

    # Miss L1 → fallback L2 (DB) / L1 miss → fallback to L2 (DB)
    try:
        entry = SEOCache.objects.get(
            cache_type=cache_type,
            tenant_id=tenant_uuid,
        )
    except SEOCache.DoesNotExist:
        return None

    # Recharger L1 pour les prochains appels / Reload L1 for next calls
    set_memcached_l1(cache_type, tenant_uuid, entry.data)

    return entry.data


# ---------------------------------------------------------------------------
# Builders JSON-LD / JSON-LD builders
# ---------------------------------------------------------------------------


def build_json_ld_organization(
    name, url, logo_url="", description="", same_as=None, address=None
):
    """
    Construit un dict JSON-LD schema.org/Organization.
    / Build a JSON-LD schema.org/Organization dict.

    Parametres / Parameters:
        name: nom de l'organisation
        url: URL du site
        logo_url: URL du logo (optionnel)
        description: description courte (optionnel)
        same_as: liste d'URLs reseaux sociaux (optionnel)
        address: dict avec streetAddress, addressLocality, addressCountry (optionnel)

    Retourne / Returns: dict pret a etre serialise en JSON
    """
    json_ld = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": name,
        "url": url,
    }

    if logo_url:
        json_ld["logo"] = logo_url

    if description:
        json_ld["description"] = description

    if same_as:
        json_ld["sameAs"] = same_as

    if address:
        json_ld["address"] = {
            "@type": "PostalAddress",
            **address,
        }

    return json_ld


def build_json_ld_product(
    name,
    description,
    price,
    currency="EUR",
    url="",
    availability="https://schema.org/InStock",
):
    """
    Construit un dict JSON-LD schema.org/Product avec une Offer imbriquee.
    / Build a JSON-LD schema.org/Product dict with a nested Offer.

    Parametres / Parameters:
        name: nom du produit (ex. "Adhesion annuelle")
        description: description du produit
        price: prix sous forme de string (ex. "15.00")
        currency: devise ISO 4217 (defaut "EUR")
        url: URL du produit (optionnel)
        availability: URL schema.org d'availability (defaut InStock)

    Retourne / Returns: dict pret a etre serialise en JSON
    """
    json_ld = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": name,
        "description": description,
        "offers": {
            "@type": "Offer",
            "price": price,
            "priceCurrency": currency,
            "availability": availability,
        },
    }

    if url:
        json_ld["offers"]["url"] = url

    return json_ld


def build_json_ld_item_list(items):
    """
    Construit un dict JSON-LD schema.org/ItemList a partir d'une liste d'items.
    / Build a JSON-LD schema.org/ItemList dict from a list of items.

    Parametres / Parameters:
        items: liste de dicts avec au minimum 'url' et 'name'

    Retourne / Returns: dict pret a etre serialise en JSON
    """
    list_items = []
    for position, item in enumerate(items, start=1):
        list_item = {
            "@type": "ListItem",
            "position": position,
            "url": item.get("url", ""),
            "name": item.get("name", ""),
        }
        list_items.append(list_item)

    json_ld = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "itemListElement": list_items,
    }

    return json_ld


# ---------------------------------------------------------------------------
# Vue robots.txt / robots.txt view
# ---------------------------------------------------------------------------


def robots_txt(request):
    """
    Genere un robots.txt dynamique avec l'URL du sitemap.
    Remplace BaseBillet/views_robots.py.
    / Generate a dynamic robots.txt with the sitemap URL.
    Replaces BaseBillet/views_robots.py.

    URL d'acces / Access URL: https://yourdomain.com/robots.txt
    """
    domain = request.get_host()

    # Ajouter le protocole si absent / Add protocol if missing
    if not domain.startswith("http"):
        domain = f"https://{domain}"

    robots_content = f"User-agent: *\nAllow: /\n\nSitemap: {domain}/sitemap.xml\n"

    return HttpResponse(robots_content, content_type="text/plain")
