"""
Balises de gabarit propres a l'admin TiBillet.
/ Template tags specific to the TiBillet admin.

LOCALISATION : Administration/templatetags/tb_admin.py

Ce module existe pour garder la surcharge de
Administration/templates/unfold/helpers/header_title.html TRIVIALE : deux
lignes ajoutees au fichier d'Unfold, et zero logique dedans. Toute
l'intelligence est ici, en Python, testable sans rendre un gabarit.
/ Exists to keep our header_title.html override trivial: all the logic lives
  here, in Python, testable without rendering a template.
"""

from django import template

from Administration.admin.dashboard import (
    _construire_sections_modules,
    _module_du_chemin,
    _safe_rev,
)

register = template.Library()


@register.simple_tag(takes_context=True)
def fil_ariane_par_module(context, parts):
    """
    Remplace le nom de l'application Django par celui du MODULE.
    / Replaces the Django app name with the module name.

    LOCALISATION : Administration/templatetags/tb_admin.py
    Appelee par notre surcharge de unfold/helpers/header_title.html.

    LE PROBLEME. header_title (unfold/templatetags/unfold.py) ouvre toujours
    le fil d'Ariane par l'application Django du modele :

        Billetterie  >  Evenements
        ^^^^^^^^^^^ le verbose_name de l'app BaseBillet, qui pointe vers
                    /admin/BaseBillet/ — 29 modeles a plat.

    « Billetterie » ressemble a un nom de module sans en etre un, et sa page
    ne veut rien dire dans une navigation Domaines -> Modules. On remplace
    donc l'entree par le vrai parent de la page :

        Agenda et Billetterie  >  Evenements
        -> /admin/module/agenda/

    / The breadcrumb opened on the Django app; we name the module instead.

    CE QUE CETTE BALISE NE FAIT JAMAIS. Elle ne retire aucune entree et n'en
    ajoute aucune : elle en remplace AU PLUS une. Un fil d'Ariane casse
    serait plus genant que le defaut qu'on corrige — donc au moindre doute,
    on rend « parts » tel quel.
    / Never removes nor adds an entry: replaces at most one, and returns
      parts untouched at the slightest doubt.

    :param context: contexte de gabarit (doit contenir « request »)
    :param parts: la liste d'entrees construite par header_title
    :return: la liste, modifiee ou non
    """
    request = context.get("request")

    # Il faut AU MOINS deux entrees. C'est le garde-fou principal, et il
    # merite son explication : header_title.html est rendu par
    # render_to_string(..., context={"parts": parts}), donc « opts » n'est PAS
    # dans le contexte — on ne peut pas savoir autrement qu'on est sur une
    # page de modele. Or une page de modele produit toujours 2 entrees
    # (application + modele) ou 3 (+ l'objet), tandis qu'une page sans modele
    # — tableau de bord, page de domaine, page de module — en produit UNE
    # seule : « Bienvenue <untel> ». Sans ce test, on ecraserait ce message
    # d'accueil par un nom de module.
    # / At least two entries: "opts" is not in this template's context, and a
    #   model page always yields 2-3 entries while a non-model page yields the
    #   single "Welcome <user>" line, which we must not overwrite.
    if request is None or not parts or len(parts) < 2:
        return parts

    module = _module_du_chemin(
        request.path,
        _construire_sections_modules(request),
        # La page du module ne doit PAS compter : elle deviendrait son propre
        # parent, et le fil d'Ariane pointerait sur lui-meme.
        # / The module page must not count: it would become its own parent.
        inclure_page_du_module=False,
    )

    # Aucun module : les 31 changelists qui n'appartiennent a aucun module
    # gardent exactement le fil d'Ariane d'Unfold. C'est aussi ce qui protege
    # tout modele ajoute demain sans etre range.
    # / No module: the breadcrumb is left exactly as Unfold built it.
    if module is None or not module.get("_slug"):
        return parts

    remplacees = list(parts)
    remplacees[0] = {
        "link": _safe_rev("staff_admin:page_de_module", args=[module["_slug"]]),
        "title": module["title"],
    }
    return remplacees
