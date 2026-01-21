## SANITIZER
from typing import Optional
from urllib.parse import urlparse
import nh3

ALLOWED_TAGS = [
    "p", "br", "strong", "em", "u",
    "ul", "ol", "li",
    "blockquote", "code", "pre",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "a", "img", "span"
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
            parsed = urlparse(value)
            path = (parsed.path or "").lower()
            # Only consider regular http/https/relative URLs; schemes are filtered elsewhere
            for prefix in DISALLOWED_IMAGE_PATH_PREFIXES:
                if path.startswith(prefix):
                    return None  # drop src attribute
        return value
    except Exception:
        # On any parsing error, drop the attribute to be safe
        return None



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
