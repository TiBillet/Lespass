"""
Filtres de template pour l'affichage des montants (BaseBillet).
/ Template filters for displaying amounts.

LOCALISATION : BaseBillet/templatetags/billet_filters.py

Utilisation dans un template / Template usage:
    {% load billet_filters %}
    {{ montant_centimes|cents_to_euros }}
    -> "127,50 €"
    {{ token.value|cents_to_asset:token.asset }}
    -> "127,50 TMP" (selon asset.currency_code)
"""

from django import template

register = template.Library()


# Symboles utilises pour les codes ISO connus
# Symbols used for known ISO codes
_SYMBOLES_DEVISE = {
    "EUR": "€",
    # Pas d'autres mappings pour l'instant : on affiche le code directement.
    # No other mappings for now: display the code as-is.
}


def _formater_montant(centimes, symbole: str) -> str:
    """
    Formatage commun centimes -> string avec separateur FR.
    Common formatting from cents to string with FR separators.

    - Separateur decimal : virgule
    - Separateur milliers : espace insecable U+00A0
    - 2 decimales toujours
    - Arithmetique entiere uniquement (pas de flottant)
    - Integer-only arithmetic (no floats)
    """
    if centimes is None:
        centimes = 0

    # Arithmetique entiere : separation signe / euros / cents via // et %
    # Integer arithmetic: sign / euros / cents split via // and %
    valeur_cents = int(centimes)
    signe = "-" if valeur_cents < 0 else ""
    valeur_abs = abs(valeur_cents)

    euros = valeur_abs // 100
    cents = valeur_abs % 100

    # Separateur milliers avec espace insecable (U+00A0)
    # Thousands separator with non-breaking space
    entier_formate = f"{euros:,}".replace(",", "\u00a0")

    return f"{signe}{entier_formate},{cents:02d} {symbole}"


@register.filter
def cents_to_euros(centimes):
    """
    Convertit des centimes (int) en affichage euros.
    12750 -> "127,50 €"
    0 -> "0,00 €"
    -500 -> "-5,00 €"
    None -> "0,00 €"
    / Converts cents (int) to euro display.
    """
    return _formater_montant(centimes, "€")


@register.filter
def cents_to_asset(centimes, asset):
    """
    Convertit des centimes en affichage selon le currency_code de l'asset.
    Si asset est None, fallback sur euros.

    Exemples / Examples:
      asset.currency_code = "EUR" -> "127,50 €"
      asset.currency_code = "TMP" -> "127,50 TMP"
      asset.currency_code = "PTS" -> "5,00 PTS"
      asset = None -> "127,50 €"

    / Converts cents to display according to asset.currency_code.
    """
    if asset is None:
        return _formater_montant(centimes, "€")

    code = asset.currency_code
    symbole = _SYMBOLES_DEVISE.get(code, code)
    return _formater_montant(centimes, symbole)
