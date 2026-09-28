"""
kiosk/templatetags/kiosk_tags.py — Filtres de template de la borne.
/ Kiosk template filters.

LOCALISATION : kiosk/templatetags/kiosk_tags.py

Usage : {% load kiosk_tags %} puis {{ solde_centimes|euros }} -> « 34,50 »
(le separateur suit la langue active).
"""

from decimal import Decimal

from django import template
from django.utils.formats import number_format

register = template.Library()


@register.filter
def euros(montant_en_centimes):
    """
    Transforme des centimes en euros lisibles, toujours avec deux decimales.
    / Turns cents into readable euros, always with two decimals.

    :param montant_en_centimes: int (ou None)
    :return: str, par exemple « 34,50 ». Chaine vide si None.
    """
    if montant_en_centimes is None or montant_en_centimes == "":
        return ""
    montant_en_euros = Decimal(int(montant_en_centimes)) / 100
    return number_format(montant_en_euros, decimal_pos=2, use_l10n=True)
