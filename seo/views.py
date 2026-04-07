"""
Vues ROOT : landing, lieux, evenements, adhesions, recherche.
/ ROOT views: landing, venues, events, memberships, search.

Ces vues lisent le cache SEOCache (schema public) via get_seo_cache().
Elles ne font aucune requete cross-schema directe.
/ These views read from SEOCache (public schema) via get_seo_cache().
They make no direct cross-schema queries.

LOCALISATION: seo/views.py
"""

import json
import logging

from django.core.paginator import Paginator
from django.http import HttpResponse
from django.template.response import TemplateResponse
from django.utils import timezone

from seo.models import SEOCache
from seo.views_common import (
    build_json_ld_item_list,
    build_json_ld_organization,
    get_seo_cache,
)

logger = logging.getLogger(__name__)


def landing(request):
    """
    Page d'accueil ROOT : chiffres cles, top 12 lieux, top 6 evenements.
    / ROOT landing page: key figures, top 12 venues, top 6 events.

    URL: GET /
    """
    # Lire les agregats depuis le cache / Read aggregates from cache
    lieux_data = get_seo_cache(SEOCache.AGGREGATE_LIEUX) or {}
    events_data = get_seo_cache(SEOCache.AGGREGATE_EVENTS) or {}
    memberships_data = get_seo_cache(SEOCache.AGGREGATE_MEMBERSHIPS) or {}

    all_lieux = lieux_data.get("lieux", [])
    all_events = events_data.get("events", [])
    all_memberships = memberships_data.get("memberships", [])

    # Chiffres cles / Key figures
    lieux_count = len(all_lieux)
    events_count = len(all_events)
    memberships_count = len(all_memberships)

    # Top 12 lieux, top 6 evenements / Top 12 venues, top 6 events
    top_lieux = all_lieux[:12]
    top_events = all_events[:6]

    # JSON-LD Organization pour le reseau TiBillet
    # / JSON-LD Organization for the TiBillet network
    json_ld_org = build_json_ld_organization(
        name="TiBillet",
        url=request.build_absolute_uri("/"),
        description="Cooperative de lieux culturels et associatifs",
    )

    context = {
        "lieux_count": lieux_count,
        "events_count": events_count,
        "memberships_count": memberships_count,
        "top_lieux": top_lieux,
        "top_events": top_events,
        "json_ld": json.dumps(json_ld_org),
        "page_title": "TiBillet - Reseau cooperatif",
        "page_description": "Decouvrez les lieux, evenements et adhesions du reseau TiBillet.",
        "canonical_url": request.build_absolute_uri("/"),
    }

    return TemplateResponse(request, "seo/landing.html", context)


def lieux(request):
    """
    Liste de tous les lieux actifs du reseau.
    / List of all active venues in the network.

    URL: GET /lieux/
    """
    lieux_data = get_seo_cache(SEOCache.AGGREGATE_LIEUX) or {}
    all_lieux = lieux_data.get("lieux", [])

    # JSON-LD ItemList / JSON-LD ItemList
    items_for_ld = []
    for lieu in all_lieux:
        domain = lieu.get("domain", "")
        url = f"https://{domain}/" if domain else ""
        items_for_ld.append(
            {
                "url": url,
                "name": lieu.get("name", ""),
            }
        )
    json_ld_list = build_json_ld_item_list(items_for_ld)

    context = {
        "lieux": all_lieux,
        "json_ld": json.dumps(json_ld_list),
        "page_title": "Lieux - TiBillet",
        "page_description": "Tous les lieux du reseau cooperatif TiBillet.",
        "canonical_url": request.build_absolute_uri("/lieux/"),
    }

    return TemplateResponse(request, "seo/lieux.html", context)


def evenements(request):
    """
    Liste de tous les evenements, pagines par 20.
    / List of all events, paginated by 20.

    URL: GET /evenements/?page=N
    """
    events_data = get_seo_cache(SEOCache.AGGREGATE_EVENTS) or {}
    all_events = events_data.get("events", [])

    # Pagination : 20 evenements par page / 20 events per page
    paginator = Paginator(all_events, 20)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    # JSON-LD ItemList pour la page courante / JSON-LD ItemList for current page
    items_for_ld = []
    for event in page_obj:
        items_for_ld.append(
            {
                "url": event.get("canonical_url", ""),
                "name": event.get("name", ""),
            }
        )
    json_ld_list = build_json_ld_item_list(items_for_ld)

    context = {
        "page_obj": page_obj,
        "json_ld": json.dumps(json_ld_list),
        "page_title": "Evenements - TiBillet",
        "page_description": "Tous les evenements a venir du reseau TiBillet.",
        "canonical_url": request.build_absolute_uri("/evenements/"),
    }

    return TemplateResponse(request, "seo/evenements.html", context)


def adhesions(request):
    """
    Liste de toutes les adhesions disponibles.
    / List of all available memberships.

    URL: GET /adhesions/
    """
    memberships_data = get_seo_cache(SEOCache.AGGREGATE_MEMBERSHIPS) or {}
    all_memberships = memberships_data.get("memberships", [])

    # JSON-LD ItemList / JSON-LD ItemList
    items_for_ld = []
    for membership in all_memberships:
        items_for_ld.append(
            {
                "url": membership.get("canonical_url", ""),
                "name": membership.get("name", ""),
            }
        )
    json_ld_list = build_json_ld_item_list(items_for_ld)

    context = {
        "memberships": all_memberships,
        "json_ld": json.dumps(json_ld_list),
        "page_title": "Adhesions - TiBillet",
        "page_description": "Toutes les adhesions disponibles dans le reseau TiBillet.",
        "canonical_url": request.build_absolute_uri("/adhesions/"),
    }

    return TemplateResponse(request, "seo/adhesions.html", context)


def recherche(request):
    """
    Recherche textuelle dans les lieux, evenements et adhesions.
    Correspondance partielle insensible a la casse sur le champ 'name'.
    / Text search across venues, events and memberships.
    Case-insensitive partial match on the 'name' field.

    URL: GET /recherche/?q=...
    """
    query = request.GET.get("q", "").strip()

    results_lieux = []
    results_events = []
    results_memberships = []

    if query:
        query_lower = query.lower()

        # Chercher dans les lieux / Search in venues
        lieux_data = get_seo_cache(SEOCache.AGGREGATE_LIEUX) or {}
        for lieu in lieux_data.get("lieux", []):
            name = (lieu.get("name") or "").lower()
            locality = (lieu.get("locality") or "").lower()
            description = (lieu.get("short_description") or "").lower()
            # Chercher dans nom, ville et description
            # / Search in name, city and description
            if (
                query_lower in name
                or query_lower in locality
                or query_lower in description
            ):
                results_lieux.append(lieu)

        # Chercher dans les evenements / Search in events
        events_data = get_seo_cache(SEOCache.AGGREGATE_EVENTS) or {}
        for event in events_data.get("events", []):
            name = (event.get("name") or "").lower()
            description = (event.get("short_description") or "").lower()
            if query_lower in name or query_lower in description:
                results_events.append(event)

        # Chercher dans les adhesions / Search in memberships
        memberships_data = get_seo_cache(SEOCache.AGGREGATE_MEMBERSHIPS) or {}
        for membership in memberships_data.get("memberships", []):
            name = (membership.get("name") or "").lower()
            description = (membership.get("short_description") or "").lower()
            if query_lower in name or query_lower in description:
                results_memberships.append(membership)

    total_results = len(results_lieux) + len(results_events) + len(results_memberships)

    context = {
        "query": query,
        "results_lieux": results_lieux,
        "results_events": results_events,
        "results_memberships": results_memberships,
        "total_results": total_results,
        "page_title": f"Recherche : {query} - TiBillet"
        if query
        else "Recherche - TiBillet",
        "page_description": "Rechercher dans le reseau TiBillet.",
        "canonical_url": request.build_absolute_uri("/recherche/"),
    }

    return TemplateResponse(request, "seo/recherche.html", context)


def explorer(request):
    """
    Page Explorer : carte Leaflet + liste filtree de lieux/events/adhesions.
    Outil de decouverte interactif (pas SEO crawlable).
    / Explorer page: Leaflet map + filtered list of venues/events/memberships.
    Interactive discovery tool (not SEO crawlable).

    URL: GET /explorer/
    """
    from seo.services import build_explorer_data

    explorer_data = build_explorer_data()

    context = {
        "explorer_data": explorer_data,
        "page_title": "Explorer - TiBillet",
        "page_description": "Explorez les lieux, evenements et adhesions du reseau TiBillet sur une carte interactive.",
    }

    return TemplateResponse(request, "seo/explorer.html", context)


def sitemap_index_view(request):
    """
    Sitemap index cross-tenant pour le ROOT.
    Liste les sitemaps de chaque tenant actif.
    / Cross-tenant sitemap index for ROOT.
    Lists sitemaps for each active tenant.

    LOCALISATION: seo/views.py
    """
    data = get_seo_cache(SEOCache.SITEMAP_INDEX) or {"tenants": []}
    tenants = data.get("tenants", [])

    # Construire le XML du sitemap index / Build sitemap index XML
    xml_parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for tenant in tenants:
        domain = tenant.get("domain", "")
        sitemap_url = tenant.get(
            "sitemap_url", f"https://{domain}/sitemap.xml" if domain else ""
        )
        updated = tenant.get("updated_at", timezone.now().isoformat())
        xml_parts.append("  <sitemap>")
        xml_parts.append(f"    <loc>{sitemap_url}</loc>")
        xml_parts.append(f"    <lastmod>{updated[:10]}</lastmod>")
        xml_parts.append("  </sitemap>")
    xml_parts.append("</sitemapindex>")

    xml_content = "\n".join(xml_parts)
    return HttpResponse(xml_content, content_type="application/xml")
