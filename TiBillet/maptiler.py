"""
Expose la cle MapTiler a tous les gabarits.
/ Exposes the MapTiler key to every template.

LOCALISATION : TiBillet/maptiler.py

Les cartes du projet vivent dans des apps differentes (pages, seo, widgets
d'adresse inclus par onboard et par le wizard d'evenement). Sans context
processor, chaque vue qui rend une carte devrait penser a passer la cle : la
premiere oubliee affiche une carte au repli sans que personne ne s'en apercoive.
/ The project's maps live in different apps. Without a context processor every
view rendering a map would have to remember to pass the key; the first one
forgotten would silently render the fallback basemap.

La cle est PUBLIQUE par nature : elle part dans le HTML et MapTiler la restreint
par domaine. Il n'y a donc rien a proteger ici.
/ The key is PUBLIC by design: it ships in the HTML and MapTiler restricts it by
domain. There is nothing to protect here.

Le gabarit la pose dans un data-* et le JS la lit — cf. static/cartes/tb_fond_de_carte.js.
/ The template puts it in a data-* and the JS reads it.
"""

from django.conf import settings


def maptiler_context(request):
    """
    Ajoute `maptiler_key` au contexte de tous les gabarits.
    / Adds `maptiler_key` to every template context.

    Chaine vide si la variable d'environnement MAPTILER_KEY est absente : le JS
    bascule alors sur le fond de carte de repli.
    / Empty string when MAPTILER_KEY is unset: the JS then uses the fallback basemap.
    """
    return {"maptiler_key": settings.MAPTILER_KEY}
