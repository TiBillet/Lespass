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
import random

from django.core.paginator import Paginator
from django.http import HttpResponse
from django.template.response import TemplateResponse
from django.utils import timezone
from django.utils.translation import gettext as _

from seo.models import SEOCache
from seo.views_common import (
    build_json_ld_federation,
    build_json_ld_item_list,
    build_json_ld_organization,
    get_seo_cache,
    json_for_html,
)

logger = logging.getLogger(__name__)


# Liste des contributeurs affiches dans la section "Ils contribuent" de la home.
# Chaque entree est un dict avec trois cles :
#   - "nom" : nom du contributeur (sert d'attribut alt de l'image et de title du lien)
#   - "logo": chemin du fichier dans le dossier static, ex. "contributeurs/mon-logo.svg"
#   - "url" : adresse du site du contributeur (le logo devient un lien cliquable)
# Pour ajouter un contributeur : deposer son logo dans seo/static/contributeurs/
# puis ajouter une ligne ici. La section reste masquee tant que la liste est vide.
# / Contributors shown in the "They contribute" section of the home page.
# Each entry is a dict with three keys:
#   - "nom" : contributor name (used as image alt and link title)
#   - "logo": file path in the static folder, e.g. "contributeurs/my-logo.svg"
#   - "url" : contributor website (the logo becomes a clickable link)
# To add a contributor: drop the logo in seo/static/contributeurs/ then add a
# line here. The section stays hidden while the list is empty.
CONTRIBUTEURS = [
    # Lieux culturels de La Réunion / Réunion cultural venues
    {"nom": "3 Peaks", "logo": "contributeurs/3peaks-ori.png", "url": ""},  # à vérifier : URL / to verify: URL
    {"nom": "La Raffinerie", "logo": "contributeurs/raffinerie1.jpg", "url": "https://www.laraffinerie.re/"},
    {"nom": "Demeter", "logo": "contributeurs/Demeter.png", "url": ""},  # à vérifier : nom + URL / to verify: name + URL
    # Réseaux de tiers-lieux et coopération / Maker spaces & cooperation networks
    {"nom": "La Réunion des Tiers-Lieux", "logo": "contributeurs/Logo-RTL.png", "url": "https://www.communecter.org/costum/co/index/slug/LaReunionDesTiersLieux/"},
    {"nom": "ANTL", "logo": "contributeurs/antl.png", "url": ""},  # à vérifier : nom complet + URL / to verify: full name + URL
    {"nom": "La Rosée", "logo": "contributeurs/larosee.jpg", "url": ""},  # à vérifier : URL (réseau tiers-lieux d'Occitanie) / to verify: URL
    {"nom": "France Tiers-Lieux", "logo": "contributeurs/ftl.png", "url": ""},  # à vérifier : nom + URL / to verify: name + URL
    {"nom": "La Compagnie des Tiers-Lieux", "logo": "contributeurs/Compagnie des tiers lieux.svg", "url": ""},  # à vérifier : URL / to verify: URL
    {"nom": "Circa", "logo": "contributeurs/circa.png", "url": ""},  # à vérifier : URL / to verify: URL
    {"nom": "CoopCircuits", "logo": "contributeurs/coopcircuit-noir.png", "url": "https://coopcircuits.fr/"},
    {"nom": "JetBrains", "logo": "contributeurs/jet_brain_beam.png", "url": "https://jb.gg/OpenSourceSupport"},
    {"nom": "France 2030", "logo": "contributeurs/france_2030.png", "url": "https://www.economie.gouv.fr/france-2030"},
]


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

    # Lieux pour le bandeau deferoulant : ordre aleatoire a chaque chargement.
    # On limite le nombre affiche pour ne pas alourdir le DOM, et la duree
    # d'animation est calculee dynamiquement pour garder une vitesse de
    # defilement constante peu importe le nombre de lieux. Avant ce fix,
    # avec 375 tenants en prod, le bandeau defilait a 2500 px/sec (illisible)
    # parce que la duree etait fixee a 30s en CSS.
    # / Venues for the scrolling marquee: random order on each load.
    # We limit the number displayed to avoid bloating the DOM, and the
    # animation duration is computed dynamically to keep scroll speed
    # constant regardless of how many lieux there are. Before this fix,
    # with 375 tenants in prod the marquee scrolled at 2500 px/sec
    # (unreadable) because duration was hardcoded to 30s in CSS.
    lieux_pour_bandeau = []
    for lieu in all_lieux:
        lieu_enrichi = dict(lieu)
        # Initiale pour le fallback quand pas de logo
        # / Initial letter fallback when no logo
        nom = lieu.get("name", "?")
        lieu_enrichi["initiale"] = nom[0].upper() if nom else "?"
        lieux_pour_bandeau.append(lieu_enrichi)

    # Melange aleatoire : chaque chargement de la page propose un ordre
    # different, ce qui valorise tous les lieux du reseau de maniere equitable.
    # / Random shuffle: each page load shows a different order, giving every
    # venue equal exposure across the network.
    random.shuffle(lieux_pour_bandeau)

    # Plafond : on n'affiche jamais plus de 100 lieux dans le bandeau.
    # Avec le doublage du template (`{% for copy in "ab" %}`), cela fait
    # 200 elements DOM au pire, ce qui reste leger.
    # / Cap: never more than 100 lieux in the marquee. With the template
    # duplication (`{% for copy in "ab" %}`) it's at worst 200 DOM nodes,
    # still lightweight.
    LIMITE_BANDEAU_LIEUX = 100
    if len(lieux_pour_bandeau) > LIMITE_BANDEAU_LIEUX:
        lieux_pour_bandeau = lieux_pour_bandeau[:LIMITE_BANDEAU_LIEUX]

    # Duree d'animation calculee pour viser une vitesse de defilement
    # constante (~40 px/sec). On estime la largeur moyenne d'un item a
    # ~150px (logo 36px + padding + nom). Plancher a 30s pour ne pas
    # defiler trop vite quand il y a peu de lieux.
    # / Animation duration sized for constant scroll speed (~40 px/sec).
    # We estimate the average item width at ~150px (logo 36px + padding +
    # name). Floor at 30s to avoid scrolling too fast with few venues.
    LARGEUR_ITEM_PX = 150
    VITESSE_CIBLE_PX_PAR_SEC = 40
    marquee_lieux_duration_sec = max(
        30,
        int(len(lieux_pour_bandeau) * LARGEUR_ITEM_PX / VITESSE_CIBLE_PX_PAR_SEC),
    )

    # Top 6 evenements / Top 6 events
    top_events = all_events[:6]

    # JSON-LD Organization pour le reseau TiBillet
    # / JSON-LD Organization for the TiBillet network
    json_ld_org = build_json_ld_organization(
        name="TiBillet",
        url=request.build_absolute_uri("/"),
        description="Cooperative de lieux culturels et associatifs",
    )

    # JSON-LD WebSite + SearchAction : permet a Google de proposer un
    # sitelinks searchbox dans les resultats de recherche (l'utilisateur
    # peut chercher directement dans TiBillet depuis la SERP). Cible le
    # formulaire de recherche `/explorer/?q=...` deja en place dans la
    # navbar. Cf. https://developers.google.com/search/docs/appearance/structured-data/sitelinks-searchbox
    # / JSON-LD WebSite + SearchAction: lets Google offer a sitelinks
    # searchbox in SERP results. Targets the existing `/explorer/?q=...`
    # search form already wired in the navbar.
    json_ld_website = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": "TiBillet",
        "url": request.build_absolute_uri("/"),
        "potentialAction": {
            "@type": "SearchAction",
            "target": {
                "@type": "EntryPoint",
                "urlTemplate": request.build_absolute_uri("/explorer/") + "?q={search_term_string}",
            },
            "query-input": "required name=search_term_string",
        },
    }

    context = {
        "lieux_pour_bandeau": lieux_pour_bandeau,
        "marquee_lieux_duration_sec": marquee_lieux_duration_sec,
        "top_events": top_events,
        # Contributeurs de TiBillet — section "Ils contribuent" (logos cliquables).
        # / TiBillet contributors — "They contribute" section (clickable logos).
        "contributeurs": CONTRIBUTEURS,
        # Deux JSON-LD distincts : `json_ld` = WebSite (searchbox SERP),
        # `json_ld_org` = Organization. Le template `base.html` injecte les
        # deux dans <head> via des balises <script type="application/ld+json">
        # separees (pattern valide schema.org).
        # / Two JSON-LD blocks: `json_ld` = WebSite (SERP searchbox),
        # `json_ld_org` = Organization. `base.html` injects both as separate
        # <script type="application/ld+json"> tags (valid schema.org pattern).
        "json_ld": json_for_html(json_ld_website),
        "json_ld_org": json_for_html(json_ld_org),
        "page_title": _("TiBillet — Billetterie coopérative et lieux culturels"),
        "page_description": _(
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
        "page_title": _("Lieux - TiBillet"),
        "page_description": _(
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
        "page_title": _("Evenements - TiBillet"),
        "page_description": _(
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
        "page_title": (
            _("Recherche : %(query)s - TiBillet") % {"query": query}
            if query
            else _("Recherche - TiBillet")
        ),
        "page_description": (
            _(
                "Résultats de recherche pour « %(query)s » dans le réseau "
                "coopératif TiBillet : lieux et événements."
            ) % {"query": query}
            if query
            else _(
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
    # Iteration sur explorer_data["tenants"] : 1 entree par tenant vivant
    # (independamment du nombre de PostalAddress qu'il a). Le JSON-LD
    # decrit l'organisation, pas chaque adresse.
    # / Network JSON-LD: iterate over tenants (1 per alive tenant).
    federation_members = []
    for tenant_lieu in explorer_data.get("tenants", []):
        domain = tenant_lieu.get("domain", "")
        member_url = f"https://{domain}/" if domain else ""
        federation_members.append({
            "name": tenant_lieu.get("name", ""),
            "url": member_url,
            "short_description": tenant_lieu.get("short_description", ""),
            "locality": tenant_lieu.get("locality", ""),
            "country": tenant_lieu.get("country", ""),
            "logo_url": tenant_lieu.get("logo_url") or "",
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
        "page_title": _("Explorer - TiBillet"),
        "page_description": _(
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
