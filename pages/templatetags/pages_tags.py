"""
Template tags de l'app pages.
/ Template tags of the pages app.

LOCALISATION : pages/templatetags/pages_tags.py
"""

import json
import re

from django import template
from django.utils.html import strip_tags
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _

register = template.Library()


# Profondeur maximale remontee par le fil d'Ariane. C'est un garde-fou : une
# hierarchie circulaire (une page dont un ancetre serait elle-meme) ferait
# boucler la remontee a l'infini, et le rendu de la page ne rendrait jamais la
# main. `Page.clean()` refuse deja les cycles, mais rien ne garantit qu'une
# donnee ecrite hors validation (migration, script) respecte cette regle.
# / Maximum depth walked by the breadcrumb. A safety net: a circular hierarchy
# would loop forever and the page would never finish rendering. `Page.clean()`
# already rejects cycles, but nothing guarantees data written outside
# validation (a migration, a script) respects that rule.
PROFONDEUR_MAX_FIL_ARIANE = 10


@register.simple_tag
def fil_ariane(page):
    """
    Retourne la chaine d'ancetres d'une page, de la racine du site jusqu'a elle.
    / Returns a page's ancestor chain, from the site root down to itself.

    LOCALISATION : pages/templatetags/pages_tags.py

    SOURCE UNIQUE du fil d'Ariane. Les trois endroits qui l'affichaient le
    reconstruisaient chacun de leur cote — le JSON-LD, le gabarit du socle et
    celui du skin — et une hierarchie a plus d'un niveau aurait demande trois
    reecritures a garder synchronisees.
    / SINGLE SOURCE of the breadcrumb. The three places that displayed it each
    rebuilt it on their own, so a deeper hierarchy would have meant three
    rewrites to keep in sync.

    Un maillon est un dict {titre, url, est_la_page_courante}. Les ancetres
    NON PUBLIES sont omis : un lien vers un brouillon menerait a un 404, aussi
    bien pour un visiteur que pour un moteur de recherche.
    / A crumb is a {titre, url, est_la_page_courante} dict. UNPUBLISHED
    ancestors are left out: a link to a draft leads to a 404, for a visitor as
    much as for a search engine.

    Retourne une liste vide pour une page de premier niveau : il n'y a alors
    rien a afficher, et le gabarit ne pose pas de fil d'Ariane a un seul maillon.
    / Returns an empty list for a top-level page: there is nothing to show.

    Utilisation : {% fil_ariane page_courante as maillons %}
    """
    if page is None or not page.parent_id:
        return []

    # On remonte de la page vers la racine, puis on retourne la liste : c'est
    # l'ordre de lecture (Accueil > Rubrique > Page).
    # / Walk up from the page to the root, then reverse: that is reading order.
    ancetres = []
    courante = page.parent
    profondeur = 0
    while courante is not None and profondeur < PROFONDEUR_MAX_FIL_ARIANE:
        if courante.publie:
            ancetres.append({
                "titre": courante.titre,
                "url": courante.get_absolute_url(),
                "est_la_page_courante": False,
            })
        courante = courante.parent
        profondeur += 1
    ancetres.reverse()

    # gettext (immediat) et non gettext_lazy : ce libelle part aussi dans le
    # JSON-LD, et json.dumps ne sait pas serialiser un objet de traduction
    # differee. Le tag s'execute au rendu, donc la langue active est la bonne.
    # / gettext (immediate), not gettext_lazy: this label also goes into the
    # JSON-LD, and json.dumps cannot serialise a lazy translation object. The
    # tag runs at render time, so the active language is the right one.
    maillons = [{"titre": _("Accueil"), "url": "/", "est_la_page_courante": False}]
    maillons.extend(ancetres)
    maillons.append({
        "titre": page.titre,
        "url": page.get_absolute_url(),
        "est_la_page_courante": True,
    })
    return maillons


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

    # Toute page publique est une WebPage. Le moteur ne distingue plus de
    # type « article » : une page reste une page, quel que soit son parent.
    # / Every public page is a WebPage. The engine no longer tells "articles"
    # apart: a page is a page, whatever its parent.
    page_web = {"@type": "WebPage", "name": nom, "url": url}
    if description:
        page_web["description"] = description
    # Dates de publication et de derniere mise a jour : elles disent au moteur
    # si le contenu est frais, et s'affichent parfois dans les resultats.
    # / Publication and last-update dates: they tell the engine how fresh the
    # content is, and sometimes show up in search results.
    if page.created_at:
        page_web["datePublished"] = page.created_at.isoformat()
    if page.updated_at:
        page_web["dateModified"] = page.updated_at.isoformat()
    graphe = [page_web]

    # FAQPage : seulement si la page a des blocs FAQ avec une question.
    # / FAQPage: only if the page has FAQ blocks with a question.
    faqs = [b for b in page.blocs.all() if b.type_bloc == "FAQ" and b.titre]
    if faqs:
        questions = []
        for bloc in faqs:
            # La reponse est du HTML riche (editeur WYSIWYG). Retirer les
            # balises sans precaution colle la fin d'un paragraphe au debut du
            # suivant : « ...possibilite de :Faire decouvrir... ». On pose donc
            # une espace a la place de chaque fin de bloc AVANT de depouiller,
            # puis on ramene les espaces multiples a une seule.
            # / The answer is rich HTML. Stripping tags naively glues the end of
            # a paragraph to the start of the next one, so we insert a space
            # where each block-level tag closes, then collapse whitespace.
            # `<br>` est auto-fermant : il s'ecrit `<br>` ou `<br/>`, jamais
            # `</br>`. Il lui faut donc sa propre alternative dans le motif.
            # / `<br>` is self-closing: it never appears as `</br>`, so it needs
            # its own alternative in the pattern.
            texte_espace = re.sub(
                r"<br\s*/?>|</(p|li|div|h[1-6])\s*>",
                " ",
                bloc.texte or "",
                flags=re.IGNORECASE,
            )
            texte_propre = " ".join(strip_tags(texte_espace).split())
            questions.append({
                "@type": "Question",
                "name": bloc.titre,
                "acceptedAnswer": {"@type": "Answer", "text": texte_propre},
            })
        graphe.append({"@type": "FAQPage", "mainEntity": questions})

    # BreadcrumbList : le fil d'Ariane structure, eligible au resultat enrichi
    # Google. La chaine vient du tag `fil_ariane` — la MEME que celle affichee
    # par les gabarits, donc les deux ne peuvent pas diverger.
    # / BreadcrumbList: the structured breadcrumb, eligible for Google's rich
    # result. The chain comes from the `fil_ariane` tag — the SAME one the
    # templates display, so the two cannot drift apart.
    maillons = fil_ariane(page)
    if maillons:
        graphe.append({
            "@type": "BreadcrumbList",
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": rang,
                    "name": maillon["titre"],
                    # URL absolue : un fil d'Ariane structure se lit hors du site.
                    # / Absolute URL: a structured breadcrumb is read off-site.
                    "item": (
                        request.build_absolute_uri(maillon["url"])
                        if request else maillon["url"]
                    ),
                }
                for rang, maillon in enumerate(maillons, start=1)
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
def embed_iframe(url, titre=""):
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

    # Le titre de l'iframe est ce qu'annonce un lecteur d'ecran a la place du
    # contenu integre. Le titre du bloc le decrit ; sans lui, tous les embeds
    # d'une page s'annoncent « Contenu integre » et deviennent indiscernables.
    # / The iframe title is what a screen reader announces instead of the
    # embedded content. Without the block title, every embed on a page
    # announces itself identically.
    titre_iframe = escape(titre) if titre else "Contenu intégré"
    iframe = (
        f'<div class="tb-embed">'
        f'<iframe src="{escape(src)}" title="{titre_iframe}" loading="lazy" '
        f'allow="accelerometer; autoplay; clipboard-write; encrypted-media; '
        f'gyroscope; picture-in-picture" allowfullscreen referrerpolicy="strict-origin-when-cross-origin">'
        f"</iframe></div>"
    )
    return mark_safe(iframe)


def _domaines_embed_autorises():
    """
    Ensemble des hotes autorises pour un contenu integre en widget (whitelist ROOT).
    Lit RootConfiguration.domaines_embed_autorises (SHARED_APPS, schema public ;
    lisible depuis un tenant via le search_path). Normalise chaque ligne : on
    retire espaces, casse, et un eventuel schema/slash (un ROOT collera souvent
    "https://newsletter.ghost.io/").
    / Set of allowed hosts for an IFRAME block (GLOBAL ROOT whitelist). Reads
    RootConfiguration.domaines_embed_autorises (SHARED, public schema; readable
    from a tenant). Normalizes each line: strip spaces/case and an optional
    scheme/slash.
    """
    from urllib.parse import urlparse

    from root_billet.models import RootConfiguration

    brut = RootConfiguration.get_solo().domaines_embed_autorises or ""
    hotes = set()
    for ligne in brut.splitlines():
        valeur = ligne.strip().lower()
        if not valeur:
            continue
        # Si le ROOT a colle un schema/slash, on extrait juste l'hote.
        # / If the ROOT pasted a scheme/slash, extract just the host.
        if "://" in valeur:
            valeur = urlparse(valeur).hostname or ""
        else:
            valeur = valeur.split("/")[0]
        if valeur:
            hotes.add(valeur)
    return hotes


@register.simple_tag
def iframe_libre(url, hauteur=600, titre=""):
    """
    Rend un <iframe> pour une URL HTTPS dont l'hote est dans la whitelist GLOBALE
    ROOT (RootConfiguration.domaines_embed_autorises). Tout autre cas -> chaine
    vide : on n'injecte JAMAIS un iframe vers un hote arbitraire (securite). Le
    src est ECHAPPE, la hauteur CASTEE en int. Contrairement a embed_iframe, on
    garde l'URL telle quelle (principe d'un iframe libre : formulaire/newsletter).
    / Renders an <iframe> for an HTTPS URL whose host is in the GLOBAL ROOT
    whitelist. Any other case -> empty string. src ESCAPED, height cast to int.
    Unlike embed_iframe, we keep the URL as-is (free iframe: form/newsletter).

    Utilisation : {% iframe_libre bloc.embed_url bloc.hauteur_px %}
    """
    from urllib.parse import urlparse

    from django.utils.html import escape

    if not url or not isinstance(url, str):
        return ""
    try:
        decoupage = urlparse(url)
    except (ValueError, TypeError):
        return ""
    # HTTPS obligatoire (un iframe http: serait bloque en mixed content de toute
    # facon) + hote non vide. / HTTPS required + non-empty host.
    if decoupage.scheme != "https":
        return ""
    hote = (decoupage.hostname or "").lower()
    if not hote or hote not in _domaines_embed_autorises():
        return ""

    # Hauteur bornee/castee (defense en profondeur, meme si le modele valide deja).
    # / Height bounded/cast (defense in depth, even though the model validates).
    try:
        hauteur_int = max(100, min(4000, int(hauteur)))
    except (ValueError, TypeError):
        hauteur_int = 600

    # Meme raison que dans embed_iframe : le titre du bloc decrit le contenu.
    # / Same reason as in embed_iframe: the block title describes the content.
    titre_iframe = escape(titre) if titre else "Contenu intégré"
    iframe = (
        f'<div class="tb-iframe">'
        f'<iframe src="{escape(url)}" title="{titre_iframe}" height="{hauteur_int}" '
        f'loading="lazy" referrerpolicy="no-referrer" '
        f'sandbox="allow-scripts allow-same-origin allow-forms allow-popups">'
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

    # Index RANG -> image de l'inline, le rang commencant a 1.
    # On numerote par le RANG D'AFFICHAGE, pas par la valeur brute du champ
    # `position` : le glisser-deposer d'Unfold renumerote les positions a
    # partir de ZERO, alors que les images creees par ailleurs partent de UN.
    # Resoudre sur la valeur brute ferait donc glisser d'un cran toutes les
    # references ![legende](galerie:N) d'un article des qu'on reordonne ses
    # images — en silence. Le rang, lui, dit ce que l'auteur voit : galerie:1
    # est la premiere image de l'encart.
    # / RANK -> inline image index, ranks starting at 1. We number by DISPLAY
    # RANK, not by the raw `position` value: Unfold's drag-and-drop renumbers
    # positions from ZERO while images created elsewhere start at ONE. Resolving
    # on the raw value would silently shift every ![caption](galerie:N)
    # reference by one as soon as the images are reordered. The rank matches
    # what the author sees: galerie:1 is the first image of the inline.
    # `.all()` et non `.order_by("position")` : ImageGalerie.Meta trie deja par
    # position, et un order_by explicite REFAIT une requete en ignorant le
    # prefetch_related pose par la vue — une requete par bloc de texte.
    # / `.all()`, not `.order_by("position")`: ImageGalerie.Meta already orders
    # by position, and an explicit order_by REISSUES a query, bypassing the
    # view's prefetch_related — one query per text block.
    images_par_position = {
        rang: image
        for rang, image in enumerate(bloc.images_galerie.all(), start=1)
    }

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
    # Le prefixe d'ancre rend les identifiants de titres uniques a l'echelle de
    # la page : deux blocs qui portent le meme titre auraient sinon la meme
    # ancre, et le sommaire n'en atteindrait qu'un.
    # / The anchor prefix keeps heading ids unique page-wide: two blocks sharing
    # a heading would otherwise produce the same anchor.
    return rendre_markdown(texte, _prefixe_ancre_du_bloc(bloc))


# Attributs conserves par le sanitize, en plus de ceux que nh3 autorise deja.
# `id` sur les titres : c'est la cible des ancres, donc de la table des matieres.
# `class` sur les conteneurs de code : c'est ce qui porte la coloration
# syntaxique. Sans cette liste, nh3 les retire tous les deux et la TOC pointe
# dans le vide pendant que le code s'affiche en gris.
# / Attributes kept by the sanitizer, on top of nh3's defaults. `id` on
# headings is the anchor target (hence the table of contents); `class` on code
# containers carries syntax highlighting. Without this, nh3 strips both.
ATTRIBUTS_TITRES = ("h1", "h2", "h3", "h4", "h5", "h6")
ATTRIBUTS_CODE = ("div", "pre", "code", "span", "table", "td", "th")

# Les titres du contenu commencent au niveau 2 : le <h1> appartient a la Page
# (banniere ou titre de secours), jamais au corps d'un bloc. Un auteur qui tape
# « # » obtiendrait sinon un second <h1>.
# / Content headings start at level 2: the <h1> belongs to the Page, never to a
# block's body. Otherwise an author typing "# " would produce a second <h1>.
NIVEAU_DE_BASE_DES_TITRES = 2


def _fabriquer_convertisseur(prefixe_ancre=""):
    """
    Fabrique un convertisseur Markdown configure pour le moteur.
    / Builds a Markdown converter configured for the engine.

    LOCALISATION : pages/templatetags/pages_tags.py

    `baselevel` fait la demotion des titres NATIVEMENT, a la construction de
    l'arbre : ne jamais la refaire ensuite par des remplacements de chaines sur
    le HTML produit, qui cesseraient de correspondre des qu'un titre porte un
    attribut (`<h2 id="...">`), et echoueraient en silence.
    / `baselevel` demotes headings NATIVELY while building the tree: never redo
    it afterwards with string replacements on the produced HTML — they stop
    matching as soon as a heading carries an attribute, and fail silently.

    :param prefixe_ancre: prefixe applique aux identifiants de titres. Deux
        blocs d'une meme page qui portent le meme titre produiraient sinon deux
        fois le meme `id` : le navigateur n'en atteindrait qu'un.
        / prefix applied to heading ids: two blocks sharing a heading would
        otherwise produce the same `id` twice.
    """
    import markdown as bibliotheque_markdown
    from markdown.extensions.toc import slugify_unicode

    def slug_prefixe(valeur, separateur):
        # slugify_unicode et non slugify : le second jette les accents, donc
        # « Présentation » et « Presentation » donneraient la meme ancre.
        # / slugify_unicode, not slugify: the latter drops accents.
        base = slugify_unicode(valeur, separateur)
        return f"{prefixe_ancre}{base}" if prefixe_ancre else base

    return bibliotheque_markdown.Markdown(
        extensions=["extra", "sane_lists", "toc", "codehilite"],
        extension_configs={
            "toc": {"baselevel": NIVEAU_DE_BASE_DES_TITRES, "slugify": slug_prefixe},
            # `guess_lang: False` : sans langue declaree, on ne colorise pas
            # plutot que de deviner faux. / Do not guess: no declared language
            # means no colouring, rather than wrong colouring.
            "codehilite": {"guess_lang": False},
        },
    )


def _attributs_autorises():
    """
    Liste blanche d'attributs passee au sanitize.
    / Attribute whitelist handed to the sanitizer.
    """
    import nh3

    autorises = {balise: set(attrs) for balise, attrs in nh3.ALLOWED_ATTRIBUTES.items()}
    for balise in ATTRIBUTS_TITRES:
        autorises.setdefault(balise, set()).add("id")
    for balise in ATTRIBUTS_CODE:
        autorises.setdefault(balise, set()).add("class")
    return autorises


@register.filter
def rendre_markdown(texte_markdown, prefixe_ancre=""):
    """
    Rend du Markdown en HTML sur : titres ancres, code colorise, HTML sanitize.
    / Renders Markdown to HTML: anchored headings, highlighted code, sanitized.

    LOCALISATION : pages/templatetags/pages_tags.py

    Deux etapes, dans cet ordre :
    1. markdown.Markdown().convert() produit le HTML (avec les `id` de titres
       et les `class` de coloration) ;
    2. nh3.clean() le nettoie. NON NEGOCIABLE — meme si seuls les admins du
       tenant ecrivent, un XSS stocke dans une page publique reste un XSS (vol
       de session d'un autre admin, defacement). nh3 garde les balises de
       contenu et retire scripts, handlers on*, javascript: etc.
    / Two steps: convert, then sanitize. The sanitize is non-negotiable — a
    stored XSS in a public page is still an XSS.

    Utilisation : {{ bloc.texte|rendre_markdown }}
    """
    import nh3

    if not texte_markdown:
        return ""

    convertisseur = _fabriquer_convertisseur(prefixe_ancre)
    html_genere = convertisseur.convert(texte_markdown)
    return mark_safe(nh3.clean(html_genere, attributes=_attributs_autorises()))


@register.simple_tag
def table_des_matieres(page):
    """
    Retourne les titres des blocs de texte d'une page, pour son sommaire.
    / Returns the headings of a page's text blocks, for its table of contents.

    LOCALISATION : pages/templatetags/pages_tags.py

    Le sommaire appartient a la PAGE, pas au bloc : une page peut porter
    plusieurs blocs de texte, et un sommaire par bloc en afficherait autant.
    Les ancres sont prefixees par bloc (voir `rendre_markdown`), ce qui les
    garde uniques quand deux blocs partagent un titre.
    / The table of contents belongs to the PAGE, not the block: a page may
    carry several text blocks, and one summary per block would show several.

    Retourne une liste de dicts {niveau, titre, ancre}, vide si la page n'a
    aucun titre — le gabarit n'affiche alors rien.
    / Returns a list of {niveau, titre, ancre} dicts, empty when the page has
    no heading — the template then shows nothing.

    Utilisation : {% table_des_matieres page_courante as sommaire %}
    """
    if page is None:
        return []

    entrees = []
    for bloc in page.blocs.all():
        if bloc.type_bloc != "TEXTE" or not bloc.texte:
            continue
        # Le texte est reconverti pour lire ses titres. C'est un second rendu
        # du meme contenu : acceptable sur des pages de cette taille, et cela
        # evite de faire remonter un etat depuis le filtre de rendu.
        # / The text is converted again to read its headings: a second render
        # of the same content, acceptable at this page size.
        convertisseur = _fabriquer_convertisseur(_prefixe_ancre_du_bloc(bloc))
        convertisseur.convert(bloc.texte)
        for jeton in convertisseur.toc_tokens:
            entrees.extend(_aplatir_titres(jeton))
    return entrees


def _prefixe_ancre_du_bloc(bloc):
    """
    Prefixe d'ancre propre a un bloc, stable entre deux rendus.
    / A block's own anchor prefix, stable across renders.
    """
    return f"b{str(bloc.uuid)[:8]}-"


def _aplatir_titres(jeton, niveau=1):
    """
    Met a plat l'arbre de titres rendu par l'extension toc.
    / Flattens the heading tree produced by the toc extension.
    """
    entrees = [{"niveau": niveau, "titre": jeton["name"], "ancre": jeton["id"]}]
    for enfant in jeton.get("children", []):
        entrees.extend(_aplatir_titres(enfant, niveau + 1))
    return entrees


@register.simple_tag
def sous_pages_publiees(page_courante, nombre_max=6):
    """
    Retourne les sous-pages PUBLIÉES d'une page (bloc LISTE, source SOUS_PAGES),
    triées comme la navbar (position puis titre), limitées à nombre_max.
    Requête DIRECTE sur le modèle — même pattern que evenements_a_venir.
    / Returns a page's PUBLISHED sub-pages (LISTE block, SOUS_PAGES source),
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
    LISTE est ainsi dynamique sans dependre de l'API.
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

    # Le gabarit le plus precis d'abord : le couple (type, affichage). Un type a
    # rendu unique (TEXTE, LIEU, FAQ, LISTE) n'a pas d'affichage et retombe donc
    # directement sur bloc_<type>.html.
    # / Most specific template first: the (type, affichage) pair. A
    # single-rendering type has no affichage and falls straight through.
    candidats = []

    if bloc.affichage:
        affichage = bloc.affichage.lower()
        candidats.append(f"pages/{skin}/partials/bloc_{type_bloc}_{affichage}.html")
        candidats.append(f"pages/classic/partials/bloc_{type_bloc}_{affichage}.html")

    # Repli sur le gabarit du type : un skin peut ne surcharger qu'un affichage,
    # et un type a rendu unique n'a que celui-ci.
    # / Fallback on the type template: a skin may override a single affichage,
    # and a single-rendering type only has this one.
    candidats.append(f"pages/{skin}/partials/bloc_{type_bloc}.html")
    candidats.append(f"pages/classic/partials/bloc_{type_bloc}.html")

    return candidats
