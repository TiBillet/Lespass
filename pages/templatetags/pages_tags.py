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
