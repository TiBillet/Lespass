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


def build_json_ld_federation(
    root_name,
    root_url,
    federation_members,
    root_description=None,
    root_address=None,
    member_of=None,
):
    """
    Construit un JSON-LD Organization avec subOrganization = federation members.
    Permet aux LLMs (ChatGPT, Claude, Perplexity, Gemini) et aux moteurs de recherche
    de comprendre nativement la structure du reseau federe.
    / Build a JSON-LD Organization with subOrganization = federation members.
    Lets LLMs (ChatGPT, Claude, Perplexity, Gemini) and search engines natively
    understand the federated network structure.

    LOCALISATION : seo/views_common.py

    Parametres / Parameters:
        root_name: nom de l'organisation racine (le tenant courant, ou "TiBillet" pour ROOT)
        root_url: URL canonique de la racine
        federation_members: list[dict] des lieux federes. Chaque dict doit avoir
            au minimum 'name' et 'url' (https://...), optionnellement 'locality',
            'country', 'short_description', 'logo_url'.
        root_description: description courte de la racine (optionnel)
        root_address: dict {address_locality, address_country} pour la racine (optionnel)
        member_of: dict {name, url} si la racine est membre d'une organisation plus grande
            (typiquement, un tenant declare etre membre du reseau "TiBillet")

    Retourne / Returns: dict serialisable en JSON, pret pour <script type="application/ld+json">
    """
    sub_orgs = []
    for member in federation_members:
        sub = {
            "@type": "Organization",
            "name": member.get("name", ""),
            "url": member.get("url", ""),
        }
        if member.get("short_description"):
            sub["description"] = member["short_description"]
        if member.get("logo_url"):
            sub["logo"] = member["logo_url"]
        if member.get("locality") or member.get("country"):
            sub["address"] = {"@type": "PostalAddress"}
            if member.get("locality"):
                sub["address"]["addressLocality"] = member["locality"]
            if member.get("country"):
                sub["address"]["addressCountry"] = member["country"]
        sub_orgs.append(sub)

    json_ld = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": root_name,
        "url": root_url,
    }

    if root_description:
        json_ld["description"] = root_description

    if root_address:
        json_ld["address"] = {"@type": "PostalAddress", **root_address}

    if member_of:
        json_ld["memberOf"] = {
            "@type": "Organization",
            "name": member_of.get("name", ""),
            "url": member_of.get("url", ""),
        }

    if sub_orgs:
        json_ld["subOrganization"] = sub_orgs

    return json_ld


def build_json_ld_breadcrumb(items):
    """
    Construit un JSON-LD schema.org/BreadcrumbList pour rich snippets en SERP.
    / Build a JSON-LD schema.org/BreadcrumbList for rich snippets in SERP.

    LOCALISATION : seo/views_common.py

    Parametres / Parameters:
        items: list[dict] avec cles 'name' (libelle visible) et 'url' (URL canonique).
            L'ordre est important (du plus general au plus specifique).
            Exemple : [{"name": "Accueil", "url": "https://x/"},
                      {"name": "Reseau local", "url": "https://x/federation/"}]

    Retourne / Returns: dict serialisable en JSON.
    """
    list_items = []
    for position, item in enumerate(items, start=1):
        list_items.append({
            "@type": "ListItem",
            "position": position,
            "name": item.get("name", ""),
            "item": item.get("url", ""),
        })
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": list_items,
    }


def build_json_ld_item_list(items):
    """
    Construit un dict JSON-LD schema.org/ItemList a partir d'une liste d'items.
    / Build a JSON-LD schema.org/ItemList dict from a list of items.

    Parametres / Parameters:
        items: liste de dicts avec au minimum 'url' et 'name'
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
    Sert sur le schema public (ROOT). Les tenants gardent leur propre
    robots_txt dans BaseBillet/views_robots.py.
    / Generate a dynamic robots.txt with the sitemap URL.
    Serves on the public schema (ROOT). Tenants keep their own
    robots_txt in BaseBillet/views_robots.py.

    URL d'acces / Access URL: https://yourdomain.com/robots.txt
    """
    domain = request.get_host()

    # Ajouter le protocole si absent / Add protocol if missing
    if not domain.startswith("http"):
        domain = f"https://{domain}"

    robots_content = f"User-agent: *\nAllow: /\n\nSitemap: {domain}/sitemap.xml\n"

    return HttpResponse(robots_content, content_type="text/plain")


def humans_txt(request):
    """
    Genere humans.txt sur le schema public (ROOT).
    Memes infos que la version tenant (cf. BaseBillet/views_humans.py) :
    on credite l'equipe Code Commun, pas un tenant en particulier.
    / Generate humans.txt on the public schema (ROOT).
    Same info as the tenant version: credits the Code Commun team,
    not a specific tenant.

    URL : https://tibillet.localhost/humans.txt
    """
    # On reutilise la logique tenant (lecture du fichier VERSION)
    # / Reuse tenant logic (read VERSION file)
    from BaseBillet.views_humans import PROJECT_VERSION, PROJECT_LAST_UPDATE

    content = (
        f"/* TEAM */\n"
        f"    Développement: Coopérative Code Commun\n"
        f"    Site: https://codecommun.coop\n"
        f"    Contact: contact [at] tibillet.re\n"
        f"    Location: France\n"
        f"\n"
        f"/* SITE */\n"
        f"    Last update: {PROJECT_LAST_UPDATE}\n"
        f"    Version: {PROJECT_VERSION}\n"
        f"    Software: Django, Python, HTMX, Leaflet\n"
        f"    Standards: HTML5, CSS3, JSON-LD\n"
        f"    Components: Bootstrap 5, HTMX, SweetAlert2\n"
        f"    Source: https://github.com/TiBillet/Lespass\n"
    )
    return HttpResponse(content, content_type="text/plain; charset=utf-8")
