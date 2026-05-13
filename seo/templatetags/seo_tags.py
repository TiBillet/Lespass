"""
Template filters pour l'app SEO.
/ Template filters for the SEO app.

LOCALISATION: seo/templatetags/seo_tags.py
"""

from datetime import datetime

from django import template
from django.utils.formats import date_format

register = template.Library()


@register.filter
def format_iso_date(value):
    """
    Convertit une date ISO string en format humain lisible.
    Ex: '2026-10-13T10:39:38.320637+00:00' → 'Lundi 13 octobre 2026'
    / Converts an ISO date string to a human-readable format.

    LOCALISATION: seo/templatetags/seo_tags.py
    """
    if not value:
        return ""

    # Si c'est deja un objet datetime, formater directement
    # / If already a datetime object, format directly
    if isinstance(value, datetime):
        return date_format(value, format="l j F Y")

    # Sinon, parser la chaine ISO / Otherwise, parse the ISO string
    try:
        # Tronquer les microsecondes et le timezone pour simplifier le parsing
        # / Truncate microseconds and timezone for simpler parsing
        date_str = str(value)
        if "T" in date_str:
            date_part = date_str.split("T")[0]
            time_part = date_str.split("T")[1]
            # Extraire heures:minutes / Extract hours:minutes
            time_clean = time_part[:5]
            parsed = datetime.strptime(f"{date_part} {time_clean}", "%Y-%m-%d %H:%M")
            return date_format(parsed, format="l j F Y, H\\hi")
        else:
            parsed = datetime.strptime(date_str[:10], "%Y-%m-%d")
            return date_format(parsed, format="l j F Y")
    except (ValueError, IndexError):
        return str(value)
