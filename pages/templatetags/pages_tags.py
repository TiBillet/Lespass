"""
Template tags de l'app pages.
/ Template tags of the pages app.

LOCALISATION : pages/templatetags/pages_tags.py
"""

from django import template

register = template.Library()


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
