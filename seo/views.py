"""
Vues ROOT : landing, lieux, evenements, recherche, explorer.
/ ROOT views: landing, venues, events, search, explorer.

Ces vues lisent le cache SEOCache (schema public) via get_seo_cache().
Elles ne font aucune requete cross-schema directe.
/ These views read from SEOCache (public schema) via get_seo_cache().
They make no direct cross-schema queries.

LOCALISATION: seo/views.py

Version V1 allegee : pas de /adhesions/, pas d'assets monnaie, pas
d'initiatives crowds. On agrege uniquement lieux + evenements.
/ V1 lightweight version: no /adhesions/, no currency assets, no crowds
initiatives. We aggregate only venues + events.
"""

import json
import logging

from django.core.paginator import Paginator
from django.http import HttpResponse
from django.template.response import TemplateResponse
from django.utils import timezone

from seo.models import SEOCache
from seo.views_common import (
    build_json_ld_federation,
    build_json_ld_item_list,
    build_json_ld_organization,
    get_seo_cache,
    json_for_html,
)

logger = logging.getLogger(__name__)


def landing(request):
    """
    Page d'accueil ROOT : chiffres cles, bandeau lieux, bandeau evenements.
    / ROOT landing page: key figures, venues marquee, events marquee.

    URL: GET /
    """
    # Lire les agregats depuis le cache / Read aggregates from cache
    lieux_data = get_seo_cache(SEOCache.AGGREGATE_LIEUX) or {}
    events_data = get_seo_cache(SEOCache.AGGREGATE_EVENTS) or {}

    all_lieux = lieux_data.get("lieux", [])
    all_events = events_data.get("events", [])

    # Chiffres cles bruts depuis le cache GLOBAL_COUNTS.
    # / Raw key figures from the GLOBAL_COUNTS cache.
    global_counts = get_seo_cache(SEOCache.GLOBAL_COUNTS) or {}
    lieux_count = global_counts.get("lieux", len(all_lieux))
    events_count = global_counts.get("events", 0)

    # Lieux tries par activite (nombre d'events) pour le bandeau deferoulant.
    # event_count est deja dans AGGREGATE_LIEUX (rempli par refresh_seo_cache),
    # pas besoin de N requetes TENANT_SUMMARY supplementaires.
    # / Venues sorted by activity (event count) for the scrolling marquee.
    # event_count is already in AGGREGATE_LIEUX (filled by refresh_seo_cache),
    # no need for N additional TENANT_SUMMARY queries.
    lieux_pour_bandeau = []
    for lieu in all_lieux:
        lieu_enrichi = dict(lieu)
        lieu_enrichi["activite"] = lieu.get("event_count", 0)
        # Initiale pour le fallback quand pas de logo
        # / Initial letter fallback when no logo
        nom = lieu.get("name", "?")
        lieu_enrichi["initiale"] = nom[0].upper() if nom else "?"
        lieux_pour_bandeau.append(lieu_enrichi)

    # Trier par activite decroissante (les plus actifs en premier)
    # / Sort by descending activity (most active first)
    lieux_pour_bandeau.sort(key=lambda l: l["activite"], reverse=True)

    # Top 6 evenements / Top 6 events
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
        "lieux_pour_bandeau": lieux_pour_bandeau,
        "top_events": top_events,
        "json_ld": json_for_html(json_ld_org),
        "page_title": "TiBillet — Billetterie coopérative et lieux culturels",
        "page_description": (
            "TiBillet : billetterie en ligne libre et coopérative pour les lieux "
            "culturels et associatifs. Découvrez les lieux et les événements à venir."
        ),
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
        "json_ld": json_for_html(json_ld_list),
        "page_title": "Lieux - TiBillet",
        "page_description": (
            "Découvrez les lieux culturels et associatifs du réseau coopératif "
            "TiBillet : salles, cafés, festivals, tiers-lieux."
        ),
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
        "json_ld": json_for_html(json_ld_list),
        "page_title": "Evenements - TiBillet",
        "page_description": (
            "Tous les événements à venir dans le réseau TiBillet : concerts, "
            "ateliers, spectacles, rencontres."
        ),
        "canonical_url": request.build_absolute_uri("/evenements/"),
    }

    return TemplateResponse(request, "seo/evenements.html", context)


def recherche(request):
    """
    Recherche textuelle dans les lieux et evenements.
    Correspondance partielle insensible a la casse.
    / Text search across venues and events.
    Case-insensitive partial match.

    URL: GET /recherche/?q=...
    """
    query = request.GET.get("q", "").strip()

    results_lieux = []
    results_events = []

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

    total_results = len(results_lieux) + len(results_events)

    context = {
        "query": query,
        "results_lieux": results_lieux,
        "results_events": results_events,
        "total_results": total_results,
        "page_title": f"Recherche : {query} - TiBillet"
        if query
        else "Recherche - TiBillet",
        "page_description": (
            f"Résultats de recherche pour « {query} » dans le réseau coopératif "
            f"TiBillet : lieux et événements."
            if query
            else (
                "Recherchez un lieu ou un événement dans le "
                "réseau coopératif TiBillet."
            )
        ),
        "canonical_url": request.build_absolute_uri("/recherche/"),
    }

    return TemplateResponse(request, "seo/recherche.html", context)


def explorer(request):
    """
    Page Explorer : carte Leaflet + liste filtree de lieux/events.
    Outil de decouverte interactif. La page elle-meme reste noindex (cf.
    seo/templates/seo/explorer.html), mais le JSON-LD declare la structure
    du reseau pour les LLMs et les rich snippets.
    / Explorer page: Leaflet map + filtered list of venues/events.
    Interactive discovery tool. The page itself stays noindex (cf.
    seo/templates/seo/explorer.html), but the JSON-LD declares the
    network structure for LLMs and rich snippets.

    URL: GET /explorer/
    """
    from seo.services import build_explorer_data

    explorer_data = build_explorer_data()

    # JSON-LD reseau : racine = TiBillet, subOrganization = tous les tenants.
    # Permet aux LLMs et a Google de comprendre l'ensemble du reseau cooperatif.
    # / Network JSON-LD: root = TiBillet, subOrganization = all tenants.
    # Lets LLMs and Google understand the whole cooperative network.
    federation_members = []
    for lieu in explorer_data.get("lieux", []):
        domain = lieu.get("domain", "")
        member_url = f"https://{domain}/" if domain else ""
        federation_members.append({
            "name": lieu.get("name", ""),
            "url": member_url,
            "short_description": lieu.get("short_description", ""),
            "locality": lieu.get("locality", ""),
            "country": lieu.get("country", ""),
            "logo_url": lieu.get("logo_url") or "",
        })

    federation_json_ld_dict = build_json_ld_federation(
        root_name="TiBillet",
        root_url=request.build_absolute_uri("/"),
        federation_members=federation_members,
        root_description=(
            "Cooperative de lieux culturels et associatifs. Billetterie, "
            "adhesions, agenda federe, monnaie locale."
        ),
    )

    context = {
        "explorer_data": explorer_data,
        # ROOT public : aucun tenant courant a highlighter sur la carte.
        # / Public ROOT: no current tenant to highlight on the map.
        "current_tenant_uuid": "",
        "federation_json_ld": json_for_html(federation_json_ld_dict),
        "page_title": "Explorer - TiBillet",
        "page_description": (
            "Explorez sur une carte interactive les lieux culturels et "
            "événements du réseau coopératif TiBillet."
        ),
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
    from xml.sax.saxutils import escape as xml_escape

    data = get_seo_cache(SEOCache.SITEMAP_INDEX) or {"tenants": []}
    tenants = data.get("tenants", [])

    # Construire le XML du sitemap index. On echappe les valeurs avec
    # xml.sax.saxutils.escape pour eviter qu'un domain ou une URL contenant
    # & ou < ne casse le document XML (cas peu probable mais defensif).
    # / Build sitemap index XML. Escape values via xml.sax.saxutils.escape
    # to avoid a domain or URL containing & or < breaking the XML
    # document (unlikely but defensive).
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
        xml_parts.append(f"    <loc>{xml_escape(sitemap_url)}</loc>")
        xml_parts.append(f"    <lastmod>{xml_escape(updated[:10])}</lastmod>")
        xml_parts.append("  </sitemap>")
    xml_parts.append("</sitemapindex>")

    xml_content = "\n".join(xml_parts)
    return HttpResponse(xml_content, content_type="application/xml")
