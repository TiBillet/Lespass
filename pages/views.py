"""
Vues publiques de l'app pages.
/ Public views of the pages app.

LOCALISATION : pages/views.py

Une Page est servie sur /<slug>/. Son rendu reutilise le contexte et le systeme
de skin de BaseBillet (get_context + base_template), pour que la page heritee de
l'entete, du pied de page et du theme du tenant.
/ A Page is served on /<slug>/. Its rendering reuses BaseBillet's context and skin
system (get_context + base_template), so the page inherits the tenant's header,
footer and theme.
"""

from django.http import Http404
from django.shortcuts import get_object_or_404, render

from ApiBillet.permissions import TenantAdminPermissionWithRequest
from pages.models import Page


def rendre_page(request, page):
    """
    Construit le contexte et rend une Page avec ses blocs ordonnes.
    / Builds the context and renders a Page with its ordered blocks.

    On importe get_context ici (pas en haut du module) pour eviter un import
    circulaire : BaseBillet.views importe pages (hook page d'accueil), et pages
    importerait BaseBillet en retour.
    / get_context is imported here (not at module top) to avoid a circular import:
    BaseBillet.views imports pages (home page hook), and pages would import
    BaseBillet back.
    """
    from BaseBillet.views import get_context, get_skin_courant

    # Skin courant du tenant (classic par defaut) : choisit le dossier de gabarits.
    # / Current tenant skin (classic by default): selects the templates folder.
    skin = get_skin_courant()

    context = get_context(request)
    # ATTENTION : get_context met deja context["page"] = numero de pagination.
    # On range donc l'objet Page sous une autre cle.
    # / WARNING: get_context already sets context["page"] = pagination number.
    # So we store the Page object under another key.
    from pages.services import grouper_blocs

    blocs = page.blocs.all()
    context["page_courante"] = page
    context["blocs"] = blocs
    # Groupes pour le rendu : les CARTE consecutives sont regroupees en grille.
    # / Render groups: consecutive CARTE blocks are bundled into a grid.
    context["groupes_blocs"] = grouper_blocs(blocs)
    context["skin_courant"] = skin

    # Gabarit de page du skin courant, fallback "classic" (premier trouve).
    # / Page template of the current skin, fallback to "classic" (first found).
    return render(
        request,
        [f"pages/{skin}/page.html", "pages/classic/page.html"],
        context,
    )


def page_publique(request, slug):
    """
    Sert une Page publique a partir de son slug.
    / Serves a public Page from its slug.

    - Page introuvable -> 404.
    - Page non publiee -> 404 pour le public, mais visible en preview pour un
      administrateur du tenant.
    / - Page not found -> 404.
    - Unpublished page -> 404 for the public, but visible as preview for a tenant
      administrator.
    """
    # Si le module pages est desactive pour ce tenant, aucune page n'est servie.
    # / If the pages module is disabled for this tenant, no page is served.
    from BaseBillet.models import Configuration
    if not Configuration.get_solo().module_pages:
        raise Http404("Module pages desactive / Pages module disabled")

    page = get_object_or_404(Page, slug=slug)

    # Brouillon : visible uniquement par un administrateur du tenant (preview).
    # / Draft: only visible to a tenant administrator (preview).
    if not page.publie and not TenantAdminPermissionWithRequest(request):
        raise Http404("Page non publiee / Unpublished page")

    return rendre_page(request, page)
