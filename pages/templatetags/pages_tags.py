"""
Template tags de l'app pages.
/ Template tags of the pages app.

LOCALISATION : pages/templatetags/pages_tags.py
"""

import json

from django import template
from django.utils.html import strip_tags
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag(takes_context=True)
def jsonld_page(context, page):
    """
    Rend les donnees structurees JSON-LD (schema.org) d'une Page : un WebPage, et
    un FAQPage si la page contient des blocs FAQ (eligible aux resultats enrichis
    Google). Construit cote serveur (pas d'API) et echappe pour eviter toute
    injection via le contenu (`<` -> `\\u003c`).
    / Renders the JSON-LD (schema.org) structured data of a Page: a WebPage, plus a
    FAQPage if the page has FAQ blocks (eligible for Google rich results). Built
    server-side (no API) and escaped to prevent content injection.

    Utilisation : {% jsonld_page page_courante %}
    """
    request = context.get("request")
    config = context.get("config")
    url = request.build_absolute_uri() if request else ""

    nom = page.meta_title or page.titre
    description = page.meta_description or (getattr(config, "organisation", "") or "")
    nom_organisation = getattr(config, "organisation", "") or ""

    # ARTICLE ou WebPage ? Une page dont le parent est une page BLOG (champ
    # explicite est_blog) est un article : on émet le type schema.org/Article
    # avec datePublished/dateModified (champs created_at/updated_at du modèle)
    # et author = l'Organization du lieu (pas de champ auteur sur Page : pour
    # un blog d'organisation, c'est le bon auteur).
    # / ARTICLE or WebPage? A page whose parent is a BLOG page (explicit
    # est_blog field) is an article: emit schema.org/Article with
    # datePublished/dateModified and author = the venue's Organization.
    page_est_un_article = bool(page.parent_id and page.parent.est_blog)
    if page_est_un_article:
        page_web = {
            "@type": "Article",
            "headline": nom,
            "url": url,
            "datePublished": page.created_at.isoformat(),
            "dateModified": page.updated_at.isoformat(),
            "author": {"@type": "Organization", "name": nom_organisation},
            "publisher": {"@type": "Organization", "name": nom_organisation},
        }
        if page.image:
            # URL absolue obligatoire pour les parseurs d'images structurées.
            # / Absolute URL required by structured-image parsers.
            page_web["image"] = (
                request.build_absolute_uri(page.image.social_card.url)
                if request else page.image.social_card.url
            )
    else:
        page_web = {"@type": "WebPage", "name": nom, "url": url}
    if description:
        page_web["description"] = description
    graphe = [page_web]

    # FAQPage : seulement si la page a des blocs FAQ avec une question.
    # / FAQPage: only if the page has FAQ blocks with a question.
    faqs = [b for b in page.blocs.all() if b.type_bloc == "FAQ" and b.titre]
    if faqs:
        graphe.append({
            "@type": "FAQPage",
            "mainEntity": [
                {
                    "@type": "Question",
                    "name": bloc.titre,
                    "acceptedAnswer": {"@type": "Answer", "text": strip_tags(bloc.texte)},
                }
                for bloc in faqs
            ],
        })

    # BreadcrumbList : fil d'Ariane si la page est une sous-page (Accueil > Parent >
    # Page) -> éligible au résultat enrichi « fil d'Ariane » Google.
    # / BreadcrumbList: breadcrumb if the page is a sub-page (Home > Parent > Page)
    # -> eligible for Google's breadcrumb rich result.
    if page.parent_id:
        racine = request.build_absolute_uri("/") if request else "/"
        maillons = [{"@type": "ListItem", "position": 1, "name": "Accueil", "item": racine}]
        # Maillon parent seulement s'il est PUBLIÉ (même règle que le fil
        # d'ariane visible : pas de lien structuré vers un brouillon → 404).
        # / Parent crumb only if PUBLISHED (same rule as the visible
        # breadcrumb: no structured link to a draft → 404).
        parent = page.parent
        if parent.publie:
            url_parent = (
                request.build_absolute_uri(f"/{parent.slug}/") if request else f"/{parent.slug}/"
            )
            maillons.append(
                {"@type": "ListItem", "position": 2, "name": parent.titre, "item": url_parent}
            )
        maillons.append(
            {"@type": "ListItem", "position": len(maillons) + 1, "name": page.titre, "item": url}
        )
        graphe.append({"@type": "BreadcrumbList", "itemListElement": maillons})

    data = {"@context": "https://schema.org", "@graph": graphe}
    # ensure_ascii=False garde les accents ; on echappe <, > et & (comme Django
    # json_script) pour neutraliser toute fermeture </script> ou commentaire.
    # / ensure_ascii=False keeps accents; escape <, > and & (like Django json_script)
    # to neutralize any </script> close or comment.
    json_str = (
        json.dumps(data, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    return mark_safe(f'<script type="application/ld+json">{json_str}</script>')


# Instances PeerTube autorisées par défaut. PeerTube est FÉDÉRÉ (n'importe quel
# hôte peut servir des vidéos) : on ne peut donc pas tout accepter sans rouvrir la
# faille d'iframe arbitraire. On part d'une petite liste d'instances connues, que
# le mainteneur peut étendre via le setting optionnel PAGES_PEERTUBE_HOSTS (tuple
# de domaines), SANS modifier ce fichier.
# / Default allowed PeerTube instances. PeerTube is FEDERATED (any host can serve
# videos), so we cannot accept everything without reopening the arbitrary-iframe
# hole. We start from a small known-instances list, extendable by the maintainer
# via the optional PAGES_PEERTUBE_HOSTS setting (tuple of domains).
DEFAULT_PEERTUBE_HOSTS = (
    "framatube.org",
    "makertube.net",
    "videos-libr.es",
)


def _peertube_hosts():
    """Ensemble des hôtes PeerTube autorisés (défaut + setting optionnel).
    / Set of allowed PeerTube hosts (default + optional setting)."""
    from django.conf import settings

    extra = getattr(settings, "PAGES_PEERTUBE_HOSTS", ()) or ()
    return set(DEFAULT_PEERTUBE_HOSTS) | {str(h).lower() for h in extra}


def _id_valide(identifiant):
    """Vrai si l'identifiant ne contient que des caractères sûrs (anti-injection).
    / True if the id only contains safe characters (anti-injection)."""
    return bool(identifiant) and all(
        c.isalnum() or c in "-_" for c in identifiant
    )


@register.simple_tag
def embed_iframe(url):
    """
    Rend un iframe responsive 16:9 pour une URL d'une LISTE BLANCHE d'hôtes
    (YouTube, Vimeo, et instances PeerTube autorisées). Tout autre hôte -> chaîne
    vide : on n'injecte JAMAIS un iframe vers un hôte arbitraire (sécurité). On
    parse l'URL, on valide l'hôte ET l'identifiant, et on RECONSTRUIT nous-mêmes
    l'URL d'embed (jamais l'URL brute de l'utilisateur). Le src final est échappé.
    / Renders a responsive 16:9 iframe for a URL from a WHITELIST of hosts (YouTube,
    Vimeo, allowed PeerTube instances). Any other host -> empty string. We parse the
    URL, validate host AND id, and REBUILD the embed URL ourselves (never the raw
    URL). The final src is escaped.

    Utilisation : {% embed_iframe bloc.embed_url %}
    """
    from urllib.parse import parse_qs, urlparse

    from django.utils.html import escape

    if not url or not isinstance(url, str):
        return ""
    # On n'accepte que http(s) : pas de javascript:, data:, etc.
    # / Only http(s): no javascript:, data:, etc.
    try:
        decoupage = urlparse(url)
    except (ValueError, TypeError):
        return ""
    if decoupage.scheme not in ("http", "https"):
        return ""

    hote = (decoupage.hostname or "").lower()
    identifiant = None
    src = None

    # YouTube : identifiant alphanumérique, rendu via youtube-nocookie.
    # / YouTube: alphanumeric id, rendered via youtube-nocookie.
    if hote in ("www.youtube.com", "youtube.com", "m.youtube.com"):
        identifiant = (parse_qs(decoupage.query).get("v") or [""])[0]
    elif hote == "youtu.be":
        identifiant = decoupage.path.lstrip("/").split("/")[0]
    if identifiant and hote.endswith(("youtube.com", "youtu.be")):
        if _id_valide(identifiant):
            src = f"https://www.youtube-nocookie.com/embed/{identifiant}"

    # Vimeo : identifiant numérique uniquement. / Vimeo: numeric id only.
    if not src and hote in ("vimeo.com", "www.vimeo.com", "player.vimeo.com"):
        segments = [p for p in decoupage.path.split("/") if p]
        identifiant = segments[-1] if segments else ""
        if identifiant.isdigit():
            src = f"https://player.vimeo.com/video/{identifiant}"

    # PeerTube : hôte d'une instance AUTORISÉE, identifiant (UUID ou short) sûr.
    # URLs reconnues : /videos/watch/<id>, /w/<id>, /videos/embed/<id>.
    # On reconstruit toujours vers /videos/embed/<id> sur le MÊME hôte autorisé.
    # / PeerTube: ALLOWED instance host + safe id (UUID or short). We always rebuild
    # to /videos/embed/<id> on the SAME allowed host.
    if not src and hote in _peertube_hosts():
        segments = [p for p in decoupage.path.split("/") if p]
        identifiant = segments[-1] if segments else ""
        if _id_valide(identifiant):
            src = f"https://{hote}/videos/embed/{identifiant}"

    if not src:
        # Hôte/identifiant non reconnu : on n'affiche rien (pas d'iframe arbitraire).
        # / Unknown host/id: render nothing (no arbitrary iframe).
        return ""

    iframe = (
        f'<div class="tb-embed">'
        f'<iframe src="{escape(src)}" title="Contenu intégré" loading="lazy" '
        f'allow="accelerometer; autoplay; clipboard-write; encrypted-media; '
        f'gyroscope; picture-in-picture" allowfullscreen referrerpolicy="strict-origin-when-cross-origin">'
        f"</iframe></div>"
    )
    return mark_safe(iframe)


@register.simple_tag(takes_context=True)
def jsonld_event(context, event):
    """
    Rend les données structurées JSON-LD schema.org/Event d'un évènement,
    construites côté Python (json.dumps) — JAMAIS à la main dans le gabarit.
    / Renders the schema.org/Event JSON-LD of an event, built in Python
    (json.dumps) — NEVER hand-crafted in the template.

    LOCALISATION : pages/templatetags/pages_tags.py

    POURQUOI (audit SEO 2026-07-05) : l'ancien JSON écrit à la main dans
    vues/evenement.html était INVALIDE (retour à la ligne littéral dans la
    description, virgule traînante quand offers manquait, latitude avec
    virgule décimale française) → Google rejetait tout le bloc, zéro rich
    snippet. json.dumps garantit l'échappement ; les nombres géo passent par
    float() (point décimal) ; offers est calculé depuis published_prices
    (l'ancien event.price_min n'existait pas : offers n'était jamais rendu).
    / WHY: the hand-written JSON was INVALID (literal newline in description,
    trailing comma, French decimal comma in geo) → Google rejected the whole
    block. json.dumps guarantees escaping; geo goes through float(); offers is
    computed from published_prices (the old event.price_min never existed).

    Utilisation : {% jsonld_event event %}
    """
    request = context.get("request")
    config = context.get("config")
    url = request.build_absolute_uri() if request else ""
    racine = request.build_absolute_uri("/") if request else "/"

    description = (
        strip_tags(event.short_description or "")
        or strip_tags(event.long_description or "")[:150]
        or event.name
    )

    donnees = {
        "@context": "https://schema.org",
        "@type": "Event",
        "name": event.name,
        "description": description,
        "url": url,
        "startDate": event.datetime.isoformat(),
        "eventStatus": "https://schema.org/EventScheduled",
    }
    if event.end_datetime:
        donnees["endDate"] = event.end_datetime.isoformat()

    # Image : URL ABSOLUE obligatoire pour les parseurs (même règle qu'og:image).
    # / Image: ABSOLUTE URL required by parsers (same rule as og:image).
    if event.img:
        donnees["image"] = request.build_absolute_uri(event.img.hdr.url) if request else event.img.hdr.url

    lieu = {"@type": "Place", "name": getattr(config, "organisation", "") or event.name}
    adresse = event.postal_address
    if adresse:
        lieu["address"] = {
            "@type": "PostalAddress",
            "streetAddress": adresse.street_address or "",
            "addressLocality": adresse.address_locality or "",
            "postalCode": adresse.postal_code or "",
            "addressCountry": adresse.address_country or "",
        }
        if adresse.name:
            lieu["address"]["name"] = adresse.name
        if adresse.latitude and adresse.longitude:
            # float() impose le POINT décimal (l'ancien gabarit sortait la
            # virgule française, illisible par les parseurs schema.org).
            # / float() enforces the decimal POINT (the old template output
            # the French comma, unreadable by schema.org parsers).
            lieu["geo"] = {
                "@type": "GeoCoordinates",
                "latitude": float(adresse.latitude),
                "longitude": float(adresse.longitude),
            }
    donnees["location"] = lieu

    donnees["organizer"] = {
        "@type": "Organization",
        "name": getattr(config, "organisation", "") or "",
        "url": racine,
    }

    # Offers : prix minimum des tarifs PUBLIÉS (rich snippet billetterie).
    # published_prices est une @property (pas un appel).
    # / Offers: minimum price of the PUBLISHED prices (ticketing rich snippet).
    # published_prices is a @property (not a call).
    prix_publies = [float(p.prix) for p in event.published_prices]
    if prix_publies:
        donnees["offers"] = {
            "@type": "Offer",
            "price": min(prix_publies),
            "priceCurrency": "EUR",
            "url": url,
            "availability": (
                "https://schema.org/SoldOut" if event.complet
                else "https://schema.org/InStock"
            ),
        }

    # Même échappement que jsonld_page (neutralise </script> et commentaires).
    # / Same escaping as jsonld_page (neutralizes </script> and comments).
    json_str = (
        json.dumps(donnees, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    return mark_safe(f'<script type="application/ld+json">{json_str}</script>')


@register.filter
def rendre_bloc_markdown(bloc):
    """
    Rend le texte Markdown d'un bloc, en résolvant d'abord ses références
    d'images : ![légende](galerie:N) pointe la N-ième image de l'inline
    « Images » du bloc (modèle ImageGalerie, champ position).
    / Renders a block's Markdown text, first resolving its image references:
    ![caption](galerie:N) points to the N-th image of the block's images
    inline (ImageGalerie model, position field).

    LOCALISATION : pages/templatetags/pages_tags.py

    Règles FALC :
    - (galerie:N) est remplacé par l'URL réelle de la variation med (480px,
      la plus grande variation NON croppée d'ImageGalerie — .tb-markdown img
      est déjà en max-width 100 %).
    - ![](galerie:N) sans légende : la légende de l'inline devient le texte
      alternatif.
    - Référence inconnue (position sans image) : remplacée par un marqueur
      texte visible « [image galerie:N introuvable] » — l'auteur voit son
      erreur (la référence brute deviendrait un <img> sans src, invisible).
    / (galerie:N) is replaced by the med variation URL; an empty ![] alt falls
    back to the inline caption; an unknown reference becomes a visible text
    marker so the author sees the mistake instead of a silent hole.

    Utilisation : {{ bloc|rendre_bloc_markdown }}
    """
    import re as bibliotheque_re

    texte = bloc.texte or ""

    # Index position -> image de l'inline. / position -> inline image index.
    images_par_position = {img.position: img for img in bloc.images_galerie.all()}

    def remplacer(correspondance):
        alt = correspondance.group("alt")
        position = int(correspondance.group("position"))
        image = images_par_position.get(position)
        if image is None or not image.image:
            # Référence inconnue : marqueur texte VISIBLE (la réf brute
            # deviendrait un <img> sans src, invisible après sanitize).
            # / Unknown ref: VISIBLE text marker (the raw ref would become
            # a src-less <img>, invisible after sanitizing).
            return f"*[image galerie:{position} introuvable]*"
        texte_alternatif = alt or image.legende or ""
        return f"![{texte_alternatif}]({image.image.med.url})"

    texte = bibliotheque_re.sub(
        r"!\[(?P<alt>[^\]]*)\]\(galerie:(?P<position>\d+)\)",
        remplacer,
        texte,
    )
    return rendre_markdown(texte)


@register.filter
def rendre_markdown(texte_markdown):
    """
    Convertit un texte Markdown en HTML SÛR (bloc MARKDOWN).
    / Converts Markdown text into SAFE HTML (MARKDOWN block).

    LOCALISATION : pages/templatetags/pages_tags.py

    Deux étapes, dans cet ordre :
    1. markdown.markdown() avec l'extension "extra" (tableaux, code clôturé,
       notes) et "sane_lists" (listes prévisibles).
    2. nh3.clean() : sanitize du HTML produit. NON NÉGOCIABLE — même si seuls
       les admins du tenant écrivent, un XSS stocké dans une page publique
       reste un XSS (vol de session d'un autre admin, defacement).
       nh3 garde les balises de contenu (titres, listes, liens, tableaux,
       images, code) et retire scripts, handlers on*, javascript: etc.
    / Two steps: markdown.markdown() with "extra" + "sane_lists", then
    nh3.clean() — non-negotiable sanitize (a stored XSS in a public page is
    still an XSS). nh3 keeps content tags and strips scripts/on*/javascript:.

    Utilisation : {{ bloc.texte|rendre_markdown }}
    """
    import markdown as bibliotheque_markdown
    import nh3

    if not texte_markdown:
        return ""

    html_genere = bibliotheque_markdown.markdown(
        texte_markdown,
        extensions=["extra", "sane_lists"],
    )
    html_nettoye = nh3.clean(html_genere)

    # DÉMOTION des titres d'un niveau (h1→h2 … h5→h6) : le h1 de la page
    # appartient à la Page (bloc HERO ou titre de page.html), jamais au
    # contenu markdown — sinon un auteur qui tape « # » crée un double h1
    # (audit SEO 2026-07-05). Ordre décroissant pour ne pas re-décaler.
    # / Heading DEMOTION by one level (h1→h2 … h5→h6): the page's h1 belongs
    # to the Page (HERO block or page.html title), never to markdown content —
    # otherwise a "# " author creates a duplicate h1. Descending order so
    # nothing gets shifted twice.
    for niveau in (5, 4, 3, 2, 1):
        html_nettoye = html_nettoye.replace(f"<h{niveau}>", f"<h{niveau + 1}>")
        html_nettoye = html_nettoye.replace(f"</h{niveau}>", f"</h{niveau + 1}>")

    return mark_safe(html_nettoye)


@register.simple_tag
def sous_pages_publiees(page_courante, nombre_max=6):
    """
    Retourne les sous-pages PUBLIÉES de la page courante (bloc LISTE_SOUS_PAGES),
    triées comme la navbar (position puis titre), limitées à nombre_max.
    Requête DIRECTE sur le modèle — même pattern que evenements_a_venir.
    / Returns the current page's PUBLISHED sub-pages (LISTE_SOUS_PAGES block),
    sorted like the navbar (position then title), limited to nombre_max.
    DIRECT model query — same pattern as evenements_a_venir.

    Utilisation : {% sous_pages_publiees page_courante bloc.nombre_max as sous_pages %}
    """
    if page_courante is None:
        return []
    return (
        page_courante.enfants.filter(publie=True)
        .order_by("position", "titre")[: nombre_max or 6]
    )


@register.simple_tag
def evenements_a_venir(nombre_max=6):
    """
    Retourne les prochains evenements publies du tenant, tries par date croissante,
    limites a `nombre_max`. Requete DIRECTE sur le modele (pas d'API) — le bloc
    EVENEMENTS est ainsi dynamique sans dependre de l'API.
    / Returns the tenant's upcoming published events, sorted by ascending date,
    limited to `nombre_max`. DIRECT model query (no API) — makes the EVENEMENTS
    block dynamic without depending on the API.

    Utilisation : {% evenements_a_venir bloc.nombre_max as evenements %}
    """
    from django.utils import timezone

    from BaseBillet.models import Event

    # Evenements a venir OU en cours (date de fin encore dans le futur).
    # / Upcoming OR ongoing events (end date still in the future).
    from django.db.models import Q

    maintenant = timezone.now()
    return (
        Event.objects.filter(published=True)
        .filter(Q(datetime__gte=maintenant) | Q(end_datetime__gte=maintenant))
        .order_by("datetime")[: nombre_max or 6]
    )


@register.simple_tag(takes_context=True)
def templates_bloc(context, bloc):
    """
    Retourne la liste des gabarits candidats pour un bloc, dans l'ordre de
    priorite : d'abord le gabarit du skin courant, puis le fallback "classic".
    / Returns the candidate templates for a block, in priority order: the current
    skin template first, then the "classic" fallback.

    Utilisation dans page.html :
        {% templates_bloc bloc as gabarits %}
        {% include gabarits %}
    Django `{% include <liste> %}` utilise select_template : il prend le premier
    gabarit qui existe. Un bloc sans variante dans le skin courant retombe donc
    automatiquement sur "classic".
    / Django `{% include <list> %}` uses select_template: it picks the first
    existing template, so a block with no variant in the current skin falls back
    to "classic" automatically.
    """
    skin = context.get("skin_courant", "classic")
    type_bloc = bloc.type_bloc.lower()
    return [
        f"pages/{skin}/partials/bloc_{type_bloc}.html",
        f"pages/classic/partials/bloc_{type_bloc}.html",
    ]
