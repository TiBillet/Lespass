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
from django.urls import Resolver404, resolve

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

    SANS MODULE. Si la page n'appartient a aucun module, il n'y a rien pour
    remplacer l'entree de l'application Django. On la retire alors : sa page
    (/admin/BaseBillet/...) n'est jamais affichee, StaffAdminSite.app_index
    renvoie vers le tableau de bord. Les autres entrees ne bougent pas.
    / No module: the Django app entry is removed (its page is never shown).

    CE QUE CETTE BALISE NE FAIT JAMAIS. Elle n'ajoute aucune entree, et ne
    retire que celle de l'application Django, reconnue par la route de son
    lien. Au moindre doute, on rend « parts » tel quel.
    / Never adds an entry; only ever removes the Django app one.

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

    # Aucun module : la premiere entree est celle de l'application Django,
    # dont la page n'est jamais affichee (StaffAdminSite.app_index renvoie
    # vers le tableau de bord). On la retire, sans toucher aux autres.
    # Voir _sans_l_entree_de_l_application ci-dessous.
    # / No module: drop the Django app entry, whose page is never shown.
    if module is None or not module.get("_slug"):
        return _sans_l_entree_de_l_application(parts)

    remplacees = list(parts)
    remplacees[0] = {
        "link": _safe_rev("staff_admin:page_de_module", args=[module["_slug"]]),
        "title": module["title"],
    }
    return remplacees


def _sans_l_entree_de_l_application(parts):
    """
    Retire du fil d'Ariane l'entree qui pointe vers la page d'une application
    Django (/admin/BaseBillet/, /admin/laboutik/...).
    / Removes the breadcrumb entry pointing to a Django app page.

    LOCALISATION : Administration/templatetags/tb_admin.py

    On reconnait l'entree par la route de son lien (« app_list »), pas par sa
    position ni par son titre : on ne retire donc jamais autre chose.
    Si le lien ne correspond a aucune route, on garde l'entree.
    / The entry is recognised by its link's route name, never by position.

    :param parts: la liste d'entrees construite par header_title
    :return: une nouvelle liste, sans l'entree de l'application
    """
    entrees_gardees = []
    for entree in parts:
        lien = entree.get("link")
        lien_vers_une_application = False
        if lien:
            try:
                lien_vers_une_application = resolve(str(lien)).url_name == "app_list"
            except Resolver404:
                lien_vers_une_application = False
        if not lien_vers_une_application:
            entrees_gardees.append(entree)
    return entrees_gardees
