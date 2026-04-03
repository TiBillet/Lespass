"""
Filtres de template pour l'affichage des montants en euros (BaseBillet).
/ Template filters for displaying amounts in euros (BaseBillet).

LOCALISATION : BaseBillet/templatetags/billet_filters.py

Utilisation dans un template :
    {% load billet_filters %}
    {{ montant_centimes|cents_to_euros }}
    → "127,50 €"
"""

from django import template

register = template.Library()


@register.filter
def cents_to_euros(centimes):
    """
    Convertit des centimes (int) en affichage euros.
    12750 → "127,50 €"
    0 → "0,00 €"
    -500 → "-5,00 €"
    None → "0,00 €"
    / Converts cents (int) to euro display.
    """
    if centimes is None:
        centimes = 0

    # Conversion centimes → euros avec 2 decimales
    # Separateur decimal : virgule (convention FR)
    # Separateur milliers : espace insecable (U+00A0)
    # / Cents → euros with 2 decimals
    valeur = int(centimes) / 100

    # Formater avec separateur de milliers / Format with thousands separator
    partie_entiere = int(valeur)
    partie_decimale = abs(int(round((valeur - partie_entiere) * 100)))

    # Signe negatif a part / Separate negative sign
    signe = "-" if valeur < 0 else ""
    partie_entiere_abs = abs(partie_entiere)

    # Separateur milliers avec espace insecable (U+00A0)
    # / Thousands separator with non-breaking space
    entier_formate = f"{partie_entiere_abs:,}".replace(",", "\u00a0")

    return f"{signe}{entier_formate},{partie_decimale:02d} €"
