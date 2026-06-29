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

from django.http import Http404, HttpResponse
from django.template.response import TemplateResponse
from django.utils import timezone
from django.utils.translation import gettext as _

from seo.features import FEATURE_DETAILS
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

    # JSON-LD ItemList des fonctionnalites qui ont une page de detail.
    # Ce bloc liste les vraies URLs `/features/<slug>/` : il aide Google
    # a comprendre l'ensemble "Fonctionnalites" et favorise l'affichage de
    # sitelinks (sous-menus) dans les resultats de recherche.
    # / JSON-LD ItemList of features that have a detail page. Listing the real
    # `/features/<slug>/` URLs helps Google understand the "Features" set
    # and encourages sitelinks (sub-links) in search results.
    feature_list_items = []
    for feature_slug, feature_data in FEATURE_DETAILS.items():
        feature_list_items.append(
            {
                "url": request.build_absolute_uri(f"/features/{feature_slug}/"),
                "name": str(feature_data["title"]),
            }
        )
    json_ld_features = json_for_html(build_json_ld_item_list(feature_list_items))

    context = {
        "lieux_pour_bandeau": lieux_pour_bandeau,
        "marquee_lieux_duration_sec": marquee_lieux_duration_sec,
        "top_events": top_events,
        # Registre des fonctionnalites (la grille est rendue par un include).
        # / Features registry (the grid is rendered by an include).
        "features": FEATURE_DETAILS,
        # ItemList des pages de fonctionnalites (SEO sitelinks).
        # / Feature pages ItemList (SEO sitelinks).
        "json_ld_features": json_ld_features,
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


def feature_detail(request, slug):
    """
    Page de detail d'une fonctionnalite : captures, descriptions, liens doc.
    / Feature detail page: screenshots, descriptions, doc links.

    URL: GET /features/<slug>/

    LOCALISATION : seo/views.py

    Le contenu vient du registre `seo.features.FEATURE_DETAILS`. La page est
    rendue ENTIEREMENT cote serveur (vraie page indexable) ; l'effet "anti-blink"
    cote landing est obtenu cote client par htmx (`hx-select="#seo-content"`),
    sans template ni branchement htmx ici. Un slug inconnu leve un 404.

    / Content comes from the `seo.features.FEATURE_DETAILS` registry. The page is
    fully server-rendered (real indexable page); the landing "anti-blink" effect
    is client-side via htmx (`hx-select="#seo-content"`), with no dual template
    or htmx branching here. An unknown slug raises a 404.

    SEO : deux blocs JSON-LD sont injectes dans le <head> via `base.html` :
    - `json_ld`     = BreadcrumbList (Accueil > Fonctionnalites > <titre>)
    - `json_ld_org` = TechArticle (le contenu de la page, lisible par les bots)
    / SEO: two JSON-LD blocks injected in <head> via base.html.
    """
    feature = FEATURE_DETAILS.get(slug)
    if feature is None:
        # Slug absent du registre : pas de page de detail.
        # / Slug not in registry: no detail page.
        raise Http404("Fonctionnalité inconnue / Unknown feature")

    titre = str(feature["title"])
    page_url = request.build_absolute_uri()
    accueil_url = request.build_absolute_uri("/")
    # Le fil d'Ariane pointe vers le hub /features/ (vraie page).
    # / Breadcrumb points to the /features/ hub (real page).
    fonctionnalites_url = request.build_absolute_uri("/features/")

    # BreadcrumbList : aide Google a afficher le fil d'Ariane dans les resultats.
    # / BreadcrumbList: helps Google show the breadcrumb trail in results.
    breadcrumb_json_ld = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": _("Accueil"), "item": accueil_url},
            {
                "@type": "ListItem",
                "position": 2,
                "name": _("Fonctionnalités"),
                "item": fonctionnalites_url,
            },
            {"@type": "ListItem", "position": 3, "name": titre, "item": page_url},
        ],
    }

    # TechArticle : decrit le contenu de la page pour les moteurs de recherche.
    # / TechArticle: describes the page content for search engines.
    article_json_ld = {
        "@context": "https://schema.org",
        "@type": "TechArticle",
        "headline": titre,
        "description": str(feature["meta_description"]),
        "inLanguage": "fr",
        "url": page_url,
        "isPartOf": {"@type": "WebSite", "name": "TiBillet", "url": accueil_url},
        "about": {"@type": "SoftwareApplication", "name": "TiBillet", "applicationCategory": "BusinessApplication"},
    }

    # Autres fonctionnalites (maillage interne = bon pour le SEO).
    # / Other features (internal linking = good for SEO).
    autres_fonctionnalites = []
    for autre_slug, autre_data in FEATURE_DETAILS.items():
        if autre_slug == slug:
            continue
        autres_fonctionnalites.append(
            {
                "slug": autre_slug,
                "title": autre_data["title"],
                "icon": autre_data["icon"],
            }
        )

    context = {
        "feature": feature,
        "slug": slug,
        "autres_fonctionnalites": autres_fonctionnalites,
        "json_ld": json_for_html(breadcrumb_json_ld),
        "json_ld_org": json_for_html(article_json_ld),
        # <title> SEO du registre (avec mots-cles) ; repli sur le titre simple.
        # / SEO <title> from the registry (keyword-rich); fallback to plain title.
        "page_title": str(feature.get("page_title") or f"{titre} — TiBillet"),
        "page_description": str(feature["meta_description"]),
        "canonical_url": page_url,
    }

    return TemplateResponse(request, "seo/feature_detail.html", context)


def features_hub(request):
    """
    Hub des fonctionnalites : page `/features/`.
    / Features hub: `/features/` page.

    URL: GET /features/

    LOCALISATION : seo/views.py

    Vraie page indexable qui reprend la grille de la landing (meme include) avec
    un H1 propre. Cible du fil d'Ariane des pages de detail et point d'entree
    pour les sitelinks (ItemList JSON-LD + BreadcrumbList).
    / Real indexable page reusing the landing features grid with its own H1.
    Breadcrumb target for detail pages and sitelinks entry point.
    """
    page_url = request.build_absolute_uri()
    accueil_url = request.build_absolute_uri("/")

    # ItemList des pages de fonctionnalites (memes URLs que le sitemap ROOT).
    # / Features pages ItemList (same URLs as the ROOT sitemap).
    feature_list_items = []
    for feature_slug, feature_data in FEATURE_DETAILS.items():
        feature_list_items.append(
            {
                "url": request.build_absolute_uri(f"/features/{feature_slug}/"),
                "name": str(feature_data["title"]),
            }
        )
    json_ld_features = json_for_html(build_json_ld_item_list(feature_list_items))

    # BreadcrumbList : Accueil > Fonctionnalites.
    # / BreadcrumbList: Home > Features.
    breadcrumb_json_ld = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": _("Accueil"), "item": accueil_url},
            {"@type": "ListItem", "position": 2, "name": _("Fonctionnalités"), "item": page_url},
        ],
    }

    context = {
        "features": FEATURE_DETAILS,
        "json_ld_features": json_ld_features,
        "json_ld": json_for_html(breadcrumb_json_ld),
        "page_title": _("Fonctionnalités — TiBillet"),
        "page_description": _(
            "Toutes les fonctionnalités de TiBillet : billetterie, adhésions, caisse, "
            "cashless NFC, monnaies locales, agenda fédéré, données ouvertes."
        ),
        "canonical_url": page_url,
    }

    return TemplateResponse(request, "seo/feature_hub.html", context)


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
    from django.conf import settings
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
        "maptiler_key": settings.MAPTILER_KEY,
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

    # Sitemap ROOT : pages du schema public (landing + hub + fonctionnalites).
    # Liste en premier car c'est le coeur editorial du site vitrine.
    # / ROOT sitemap: public-schema pages (landing + hub + features). Listed first.
    root_sitemap_url = request.build_absolute_uri("/sitemap-root.xml")
    root_lastmod = timezone.now().isoformat()[:10]
    xml_parts.append("  <sitemap>")
    xml_parts.append(f"    <loc>{xml_escape(root_sitemap_url)}</loc>")
    xml_parts.append(f"    <lastmod>{xml_escape(root_lastmod)}</lastmod>")
    xml_parts.append("  </sitemap>")

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


def sitemap_root_view(request):
    """
    Sitemap des pages ROOT (schema public).
    Liste la landing, le hub `/features/` et chaque page de fonctionnalite,
    plus l'explorateur. C'est ce qui rend les pages de fonctionnalites
    decouvrables par les moteurs (et favorise les sitelinks).
    / ROOT pages sitemap (public schema): landing, `/features/` hub, each
    feature page, plus the explorer. Makes feature pages discoverable (sitelinks).

    URL: GET /sitemap-root.xml

    LOCALISATION: seo/views.py
    """
    from xml.sax.saxutils import escape as xml_escape

    # Pages fixes du ROOT / Fixed ROOT pages.
    urls = [
        request.build_absolute_uri("/"),
        request.build_absolute_uri("/features/"),
        request.build_absolute_uri("/explorer/"),
    ]
    # Une URL par page de fonctionnalite / One URL per feature page.
    for feature_slug in FEATURE_DETAILS:
        urls.append(request.build_absolute_uri(f"/features/{feature_slug}/"))

    lastmod = timezone.now().isoformat()[:10]
    xml_parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for url in urls:
        xml_parts.append("  <url>")
        xml_parts.append(f"    <loc>{xml_escape(url)}</loc>")
        xml_parts.append(f"    <lastmod>{xml_escape(lastmod)}</lastmod>")
        xml_parts.append("  </url>")
    xml_parts.append("</urlset>")

    xml_content = "\n".join(xml_parts)
    return HttpResponse(xml_content, content_type="application/xml")
