"""
Filtres de template pour l'affichage des montants en euros.
/ Template filters for displaying amounts in euros.

LOCALISATION : laboutik/templatetags/laboutik_filters.py

Utilisation dans un template :
    {% load laboutik_filters %}
    {{ montant_centimes|euros }}
    → "127,50 €"
"""
from django import template

register = template.Library()


@register.filter
def euros(centimes):
    """
    Convertit des centimes (int) en affichage euros.
    12750 → "127,50 €"
    0 → "0,00 €"
    -500 → "-5,00 €"
    None → "0,00 €"
    / Converts cents (int) to euro display.
    """
    from BaseBillet.models import Configuration

    if centimes is None:
        centimes = 0

    # Recuperer le symbole de la monnaie du tenant
    # / Get the tenant's currency symbol
    try:
        config = Configuration.get_solo()
        code_monnaie = config.currency_code or "EUR"
    except Exception:
        code_monnaie = "EUR"

    symbole = "€" if code_monnaie == "EUR" else code_monnaie

    # Conversion centimes → euros avec 2 decimales
    # Separateur decimal : virgule (convention FR)
    # Separateur milliers : espace insecable (U+00A0)
    # / Cents → euros with 2 decimals
    # Decimal separator: comma (FR convention)
    # Thousands separator: non-breaking space
    valeur = int(centimes) / 100

    # Formater avec separateur de milliers
    # / Format with thousands separator
    partie_entiere = int(valeur)
    partie_decimale = abs(int(round((valeur - partie_entiere) * 100)))

    # Signe negatif a part pour le formatage
    # / Separate negative sign for formatting
    signe = "-" if valeur < 0 else ""
    partie_entiere_abs = abs(partie_entiere)

    # Separateur milliers avec espace insecable (U+00A0)
    # / Thousands separator with non-breaking space
    entier_formate = f"{partie_entiere_abs:,}".replace(",", "\u00a0")

    return f"{signe}{entier_formate},{partie_decimale:02d} {symbole}"


@register.filter
def montant_dans_la_monnaie(centimes, nom_de_la_monnaie):
    """
    Ecrit un montant dans sa monnaie : euros, ou points / temps.
    / Writes an amount in its currency: euros, or points / time.

    - Sans nom de monnaie (vide ou None) : comme le filtre `euros`.
    - Avec un nom : les centiemes divises par 100, deux decimales, puis le nom.
      Les points et les heures sont comptes en centiemes, comme les centimes
      (300 points = 30000).
    30000, "Points fidélité" → "300,00 Points fidélité"
    500, ""                  → "5,00 €"

    Usage : {{ montant_centimes|montant_dans_la_monnaie:nom_de_la_monnaie }}
    """
    if not nom_de_la_monnaie:
        return euros(centimes)

    montant_en_euros_formate = euros(centimes)
    # euros() finit par « <espace> <symbole> » : on garde le nombre seul.
    # / euros() ends with " <symbol>": keep the number only.
    nombre_formate = montant_en_euros_formate.rsplit(" ", 1)[0]
    return f"{nombre_formate} {nom_de_la_monnaie}"


@register.filter
def afficher_poids(article):
    """
    Convertit (poids_total + unite_poids) en chaine compacte collee.
    Conversion automatique en kg / L des que la quantite atteint le seuil :
        unite "GR" : >= 1000 → "1,5kg" ; sinon "350g"
        unite "CL" : >= 100  → "2L"    ; sinon "50cl"
    Retourne "" si l'article n'a pas de poids (article non vrac).
    / Converts (poids_total + unite_poids) into a compact joined string.
    Auto kg / L conversion above the threshold.

    Usage : {{ article|afficher_poids }} → "350g" / "1,5kg" / "50cl" / "2L" / ""
    """
    if not article:
        return ""
    poids = article.get("poids_total") if hasattr(article, "get") else None
    if not poids:
        return ""
    unite = article.get("unite_poids") if hasattr(article, "get") else None

    # Helper local : enleve les zeros traînants et le separateur final.
    # Ex: "1,50" → "1,5" ; "1,00" → "1" ; "12,30" → "12,3"
    # / Local helper: strip trailing zeros and final separator.
    def _compacter(valeur_str):
        if "," not in valeur_str:
            return valeur_str
        return valeur_str.rstrip("0").rstrip(",")

    if unite == "GR":
        if poids >= 1000:
            valeur_kg = f"{poids / 1000:.2f}".replace(".", ",")
            return f"{_compacter(valeur_kg)}kg"
        return f"{poids}g"

    if unite == "CL":
        if poids >= 100:
            valeur_l = f"{poids / 100:.2f}".replace(".", ",")
            return f"{_compacter(valeur_l)}L"
        return f"{poids}cl"

    # Unite inconnue (ne devrait pas arriver) : on affiche le nombre brut.
    # / Unknown unit (should not happen): show raw number.
    return f"{poids}"


@register.filter
def has_poids(articles):
    """
    Retourne True si au moins un article de la liste a un poids_total non-null.
    Utilise pour afficher conditionnellement la colonne "Poids/Vol" dans
    les tableaux de detail des ventes.
    / Returns True if at least one article in the list has a non-null
    poids_total. Used to conditionally show the "Weight/Vol." column.
    """
    if not articles:
        return False
    for article in articles:
        if article and article.get("poids_total"):
            return True
    return False
