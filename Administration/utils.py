## SANITIZER
import posixpath
import re
from typing import Optional
from urllib.parse import unquote, urlparse
import nh3

ALLOWED_TAGS = [
    "p", "br", "strong", "em", "u",
    "ul", "ol", "li",
    "blockquote", "code", "pre",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "a", "img", "span", "del"
]
ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "rel"],
    "img": ["src", "alt", "title"],
}

# Disallow image URLs pointing to potentially dangerous internal routes
DISALLOWED_IMAGE_PATH_PREFIXES = (
    "/admin",
    "/logout",
    "/deconnexion",
    "/signout",
)


def _attribute_filter(tag: str, attr: str, value: str) -> Optional[str]:
    """Filter attributes during sanitization.
    - For <img src>, remove the attribute if it targets problematic internal routes
      like /admin or logout endpoints (even if relative URLs).
    Returning None removes the attribute.
    """
    try:
        if tag == "img" and attr == "src" and isinstance(value, str):
            # On lit le chemin comme le NAVIGATEUR le lira, sinon le filtre se contourne :
            # - le navigateur retire tabulations et retours à la ligne, et lit « \ » comme « / » ;
            # - Django décode les « %xx » : « /%61dmin » arrive sur « /admin » ;
            # - « /./admin » et « /.//admin » sont normalisés en « /admin » ;
            # - un « .. » peut remonter jusqu'à la racine (« ../admin ») : refusé d'office.
            # / Read the path as the BROWSER will: strip tabs/newlines, "\" as "/",
            # percent-decode, normalize; any ".." segment is rejected.
            valeur_lue_par_le_navigateur = value
            for caractere_ignore in ("\t", "\n", "\r"):
                valeur_lue_par_le_navigateur = valeur_lue_par_le_navigateur.replace(caractere_ignore, "")
            valeur_lue_par_le_navigateur = valeur_lue_par_le_navigateur.strip().replace("\\", "/")

            parsed = urlparse(valeur_lue_par_le_navigateur)
            chemin_decode = unquote(parsed.path or "")

            segments_du_chemin = chemin_decode.split("/")
            if ".." in segments_du_chemin:
                return None  # drop src attribute

            chemin_sans_doubles_barres = re.sub(r"/{2,}", "/", chemin_decode)
            if chemin_sans_doubles_barres:
                chemin_normalise = posixpath.normpath(chemin_sans_doubles_barres)
            else:
                chemin_normalise = ""
            path = chemin_normalise.lower()

            # Only consider regular http/https/relative URLs; schemes are filtered elsewhere
            for prefix in DISALLOWED_IMAGE_PATH_PREFIXES:
                if path.startswith(prefix):
                    return None  # drop src attribute
        return value
    except Exception:
        # On any parsing error, drop the attribute to be safe
        return None



def url_a_schema_dangereux(valeur):
    """
    Vrai si l'URL utilise un schema dangereux (javascript:, data:, vbscript:).
    On retire d'abord espaces et caracteres de controle pour dejouer les
    obfuscations type "java\\tscript:". On ne teste que le debut.
    / True if the URL uses a dangerous scheme. Strips whitespace/control chars first
    to defeat obfuscations, then tests the start only.
    """
    if not valeur or not isinstance(valeur, str):
        return False
    compact = "".join(c for c in valeur if not c.isspace() and ord(c) >= 0x20).lower()
    return compact.startswith(("javascript:", "data:", "vbscript:"))


def clean_text(text: str) -> str:
    """Nettoie une chaîne de texte brut en supprimant tout HTML.
    Clean a plain text string by stripping all HTML tags.

    Utilisé pour les entrées utilisateur qui ne doivent contenir aucun HTML
    (noms de champs, valeurs de formulaire, etc.).
    Used for user inputs that should contain no HTML at all
    (field names, form values, etc.).
    """
    # nh3.clean avec tags vide supprime tout le HTML et ne garde que le texte
    # nh3.clean with empty tags strips all HTML and keeps only text
    return nh3.clean(
        text,
        tags=set(),
        attributes={},
        strip_comments=True,
    )


def clean_html(html: str) -> str:
    # Use nh3 (ammonia) to sanitize HTML; explicitly restrict URL schemes and strip comments.
    url_schemes = {"http", "https", "mailto", "tel"}
    # nh3 expects sets for tags and attributes values
    tags = set(ALLOWED_TAGS)
    attributes = {k: set(v) for k, v in ALLOWED_ATTRIBUTES.items()}
    return nh3.clean(
        html,
        tags=tags,
        attributes=attributes,
        url_schemes=url_schemes,
        attribute_filter=_attribute_filter,
        strip_comments=True,
        link_rel=None,  # allow existing rel and don't auto-insert
    )
