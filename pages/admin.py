"""
Admin Unfold de l'app pages.
/ Unfold admin of the pages app.

LOCALISATION : pages/admin.py

ENREGISTREMENT : ce module est importe explicitement par
Administration/admin_tenant.py (le projet n'utilise pas l'autodiscover admin :
tout est enregistre sur staff_admin_site, un site Unfold custom).
/ REGISTRATION: this module is imported explicitly by admin_tenant.py (the
project does not use admin autodiscover; everything is registered on the custom
Unfold site staff_admin_site).

UX D'EDITION : on part de la PAGE.
- La liste des pages n'affiche que les pages PRINCIPALES (sans parent). Le
  chevron de chaque ligne deplie ses sous-pages (list_sections). Le filtre
  « Niveau » permet de revenir a la liste complete.
- La fiche d'une page montre, sous son formulaire, la page RENDUE comme sur
  le site, dans UNE iframe. Chaque bloc y porte une barre d'actions
  (↑ ↓ Modifier ✕, et + pour ajouter un bloc juste apres) ; un menu
  « + Ajouter en tete » est au-dessus (pages/admin_apercu.py).
- La fiche d'un bloc porte le contenu, avec un APERCU EN DIRECT a cote du
  formulaire. Premiere action : choisir le MODELE DE BLOC (type + affichage
  en un seul select) -> les champs correspondants se deroulent
  (conditional_fields NATIF d'Unfold / Alpine.js). Les listes
  (infos pratiques, sous-cartes, points GPS) se saisissent ligne par ligne,
  plus jamais en JSON brut (pages/admin_widgets.py, pages/editeur_items.py).
/ EDITING UX: the PAGE is the entry point.
- The page list only shows MAIN pages (no parent). Each row's chevron expands
  its sub-pages (list_sections). The "Level" filter brings back the full list.
- A page form shows the page RENDERED as on the site, in ONE iframe, each
  block with an action bar (↑ ↓ edit ✕, + to add a block after it).
- The block form carries the content, with a LIVE PREVIEW beside the form.
  First action: choose the BLOCK MODEL (type + affichage in one select) ->
  matching fields unfold. Lists (practical
  info, sub-cards, GPS points) are typed line by line, never as raw JSON.

POURQUOI LE CONTENU SE SAISIT DANS LA FICHE DU BLOC ET PAS DANS LA PAGE :
conditional_fields d'Unfold ne s'applique qu'au formulaire principal (le scope
Alpine est pose sur le <form> du changeform). Un formulaire de bloc imbrique
dans la page afficherait les ~30 champs du catalogue pour tous les types.
/ WHY CONTENT IS TYPED IN THE BLOCK FORM, NOT THE PAGE: Unfold's
conditional_fields only applies to the main form.
"""

from django import forms
from django.contrib import admin, messages
from django.db.models import Count, Max
from django.http import HttpResponseRedirect
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from solo.admin import SingletonModelAdmin
# ModelAdmin vient de Administration/admin/base.py : c'est le ModelAdmin
# d'Unfold plus le placeholder de recherche tire de search_fields.
# / Project ModelAdmin: Unfold's, plus the search placeholder.
from Administration.admin.base import ModelAdmin
from unfold.admin import TabularInline
from unfold.contrib.filters.admin import (
    AutocompleteSelectFilter,
    ChoicesDropdownFilter,
)
from unfold.contrib.forms.widgets import WysiwygWidget
from unfold.widgets import UnfoldAdminSelectWidget
from unfold.decorators import display
from unfold.sections import TableSection

from Administration.admin.site import staff_admin_site
from ApiBillet.permissions import TenantAdminPermissionWithRequest
from pages.models import Bloc, ConfigurationSite, ImageGalerie, Page
from pages.admin_apercu import (
    CHAMP_CONTENU_CARTES,
    CHAMP_CONTENU_LIEU,
    CHAMP_POINTS_GPS,
    appliquer_editeurs_de_lignes,
    nettoyer_bloc,
    CHAMP_MODELE,
    decouper_modele,
    uuid_ou_none,
    menu_d_ajout,
    modeles_de_bloc,
    valeur_du_modele,
    vue_apercu_bloc_en_direct,
    vue_apercu_page,
    vue_deplacer_bloc,
    vue_ligne_vide,
    vue_retirer_bloc,
)
from pages.admin_widgets import LignesField
from pages.blocs_catalogue import (
    AFFICHAGES_AVEC_GALERIE,
    AFFICHAGES_PAR_TYPE,
    CHAMPS_PAR_AFFICHAGE,
    AFFICHAGE_PAR_DEFAUT,
    CHAMPS_PAR_TYPE,
    SKINS_PAR_CHAMP_DU_TYPE,
)
from pages.services import inserer_bloc_apres


# Champ de formulaire dedie a la saisie Markdown (editeur EasyMDE) : il double
# le champ modele `texte` pour le seul type TEXTE, dont la source ne doit pas
# passer par le WYSIWYG. / Dedicated Markdown form field (EasyMDE editor): it
# doubles the `texte` model field for the TEXTE type only.
_CHAMP_MARKDOWN = "texte_markdown"

# Champ de formulaire CACHE qui porte le skin du site. Il n'est jamais
# enregistre : il sert seulement aux conditions d'affichage (un champ que
# seul un skin rend, cf. SKINS_PAR_CHAMP_DU_TYPE).
# / HIDDEN form field carrying the site skin. Never saved: only used by the
# display conditions.
_CHAMP_SKIN = "skin_du_site"


def _champs_du_catalogue():
    """
    Tous les champs modele utilises par au moins un type de bloc, dans l'ordre
    du catalogue, plus le champ de saisie Markdown.
    / Every model field used by at least one block type, in catalogue order,
    plus the Markdown input field.
    """
    champs = []
    for champs_du_type in CHAMPS_PAR_TYPE.values():
        for champ in champs_du_type:
            if champ not in champs:
                champs.append(champ)
    # `source` et `page_source` pilotent le bloc LISTE ; `page_source` n'est pas
    # dans le catalogue (c'est une cle etrangere, cf. CHAMPS_RELATION) mais il
    # doit rester saisissable dans l'admin.
    # / `source` and `page_source` drive the LISTE block; `page_source` is kept
    # out of the catalogue (foreign key) but must stay editable in the admin.
    if "page_source" not in champs:
        champs.append("page_source")
    champs.append(_CHAMP_MARKDOWN)

    # Les deux champs JSON ne sont plus saisis en JSON brut : chacun est
    # remplace, a la meme place, par son editeur de lignes (champ de
    # formulaire, cf. BlocAdminForm). `contenu` a deux editeurs, car ses
    # elements n'ont pas la meme forme pour un LIEU et pour une SECTION.
    # / Both JSON fields are no longer typed as raw JSON: each is replaced, in
    # place, by its line editor. `contenu` has two editors, since its items
    # differ between a LIEU and a SECTION.
    champs_avec_editeurs = []
    for champ in champs:
        if champ == "contenu":
            champs_avec_editeurs.append(CHAMP_CONTENU_CARTES)
            champs_avec_editeurs.append(CHAMP_CONTENU_LIEU)
        elif champ == "points_gps":
            champs_avec_editeurs.append(CHAMP_POINTS_GPS)
        else:
            champs_avec_editeurs.append(champ)
    return tuple(champs_avec_editeurs)


def _test_du_type(type_bloc):
    """
    Fragment Alpine.js vrai quand le type choisi est celui-la.
    / Alpine.js fragment true when the chosen type is that one.
    """
    return f"type_bloc == '{type_bloc}'"


def _test_du_couple(type_bloc, affichages):
    """
    Fragment Alpine.js vrai pour ce type ET l'un de ces affichages.
    / Alpine.js fragment true for this type AND one of these affichages.

    Les deux selects (type_bloc et affichage) sont dans le meme scope Alpine du
    formulaire : l'expression peut donc croiser leurs valeurs.
    / Both selects live in the form's single Alpine scope, so the expression can
    cross their values.
    """
    if len(affichages) == 1:
        test_affichage = f"affichage == '{affichages[0]}'"
    else:
        liste = ",".join(f"'{a}'" for a in affichages)
        test_affichage = f"[{liste}].includes(affichage)"
    return f"({_test_du_type(type_bloc)} && {test_affichage})"


def _ou_logique(fragments):
    """
    Assemble des fragments Alpine.js en un « ou » unique.
    / Joins Alpine.js fragments into a single "or".
    """
    return " || ".join(fragments)


def _visibilite_des_champs():
    """
    Associe a chaque champ l'expression qui decide de son affichage.
    / Maps each field to the expression driving its display.

    Deux niveaux, tous deux lus dans le catalogue :
    - le TYPE, pour les champs d'un type a rendu unique (CHAMPS_PAR_TYPE) ;
    - le COUPLE (type, affichage), quand le type propose plusieurs rendus qui
      ne consomment pas les memes champs (CHAMPS_PAR_AFFICHAGE). Sans ce
      second niveau, une CITATION proposerait une image et deux boutons que son
      gabarit ne rend pas.
    / Two levels, both read from the catalogue: the TYPE for single-rendering
    types, and the (type, affichage) PAIR when a type's renderings do not
    consume the same fields. Without the second level, a CITATION would offer
    an image and two buttons its template never renders.
    """
    # Pour chaque champ, la liste des fragments d'expression qui le montrent.
    # / For each field, the list of expression fragments that reveal it.
    fragments_par_champ = {}

    for type_bloc, champs in CHAMPS_PAR_TYPE.items():
        champs_par_affichage = CHAMPS_PAR_AFFICHAGE.get(type_bloc)
        for champ in champs:
            if champ == "affichage":
                continue
            if champs_par_affichage is None:
                # Type a rendu unique : le champ suit son type.
                # / Single-rendering type: the field follows its type.
                fragment = _test_du_type(type_bloc)
                # Certains champs ne sont rendus que par certains skins (cf.
                # SKINS_PAR_CHAMP_DU_TYPE) : on ajoute la condition sur le skin
                # du site, porte par le champ cache `skin_du_site`.
                # / Some fields are only rendered by some skins: add the
                # condition on the site skin, carried by the hidden field.
                skins_qui_rendent = SKINS_PAR_CHAMP_DU_TYPE.get((type_bloc, champ))
                if skins_qui_rendent:
                    liste_skins = ",".join(f"'{skin}'" for skin in skins_qui_rendent)
                    fragment = f"({fragment} && [{liste_skins}].includes({_CHAMP_SKIN}))"
                fragments_par_champ.setdefault(champ, []).append(fragment)
                continue
            # Type a rendus multiples : le champ ne suit que les affichages
            # dont le gabarit le consomme.
            # / Multi-rendering type: the field only follows the affichages
            # whose template consumes it.
            affichages = [
                affichage
                for affichage, champs_rendus in champs_par_affichage.items()
                if champ in champs_rendus
            ]
            if affichages:
                fragments_par_champ.setdefault(champ, []).append(
                    _test_du_couple(type_bloc, affichages)
                )

    visibilite = {
        champ: _ou_logique(fragments)
        for champ, fragments in fragments_par_champ.items()
    }

    # `texte` du bloc TEXTE se saisit dans l'editeur Markdown, pas dans le
    # WYSIWYG : les deux champs ne s'affichent donc jamais ensemble.
    # / A TEXTE block's `texte` is typed in the Markdown editor, not the
    # WYSIWYG: the two fields never show together.
    visibilite["texte"] = _ou_logique(
        [
            fragment
            for fragment in fragments_par_champ.get("texte", [])
            if fragment != _test_du_type("TEXTE")
        ]
    )
    visibilite[_CHAMP_MARKDOWN] = _test_du_type("TEXTE")

    # Type et affichage ne se choisissent plus separement : le select
    # « Modele de bloc » les porte tous les deux (cf. BlocAdminForm). Ils
    # restent dans le formulaire, CACHES, parce que toutes les conditions
    # ci-dessus lisent `type_bloc` et `affichage` dans le scope Alpine.
    # / Type and affichage are no longer picked separately: the "block model"
    # select carries both. They stay in the form, HIDDEN, because every
    # condition above reads them in the Alpine scope.
    visibilite["type_bloc"] = "false"
    visibilite["affichage"] = "false"

    # La page a lister ne concerne que le bloc LISTE, et seulement quand il
    # liste des sous-pages (l'agenda n'a pas de page source).
    # / The page to list only concerns a LISTE block listing sub-pages.
    visibilite["page_source"] = f"({_test_du_type('LISTE')} && source == 'SOUS_PAGES')"

    # Champs caches : presents dans le formulaire (donc dans le scope Alpine,
    # et postes vers l'apercu), mais jamais affiches. Unfold ne cache pas la
    # ligne d'un champ cache : l'expression `false` s'en charge.
    # / Hidden fields: in the form (so in the Alpine scope, and posted to the
    # preview), never displayed. `false` hides their row.
    visibilite["page"] = "false"
    visibilite[_CHAMP_SKIN] = "false"

    # Editeurs de lignes (cf. _champs_du_catalogue) : ils reprennent la
    # visibilite des champs JSON qu'ils remplacent. `contenu` se partage entre
    # l'editeur LIEU (infos pratiques) et l'editeur des sous-cartes (les
    # couples SECTION dont le gabarit lit `contenu`).
    # / Line editors take over the visibility of the JSON fields they replace.
    # `contenu` splits between the LIEU editor and the SECTION sub-cards editor.
    fragments_contenu = fragments_par_champ.pop("contenu", [])
    visibilite.pop("contenu", None)
    fragments_cartes = []
    for fragment in fragments_contenu:
        if fragment != _test_du_type("LIEU"):
            fragments_cartes.append(fragment)
    visibilite[CHAMP_CONTENU_LIEU] = _test_du_type("LIEU")
    visibilite[CHAMP_CONTENU_CARTES] = _ou_logique(fragments_cartes)
    visibilite[CHAMP_POINTS_GPS] = visibilite.pop("points_gps")

    return visibilite


_CHAMPS_DU_CATALOGUE = _champs_du_catalogue()


def _lien_vers_la_fiche(page):
    """
    Lien cliquable vers la fiche d'edition d'une page, pour les tableaux qui ne
    passent pas par list_display (les sections).
    / Clickable link to a page's edit form, for tables that do not go through
    list_display (the sections).
    """
    url = reverse("staff_admin:pages_page_change", args=[page.pk])
    return format_html('<a href="{}" class="text-primary-600">{}</a>', url, page.titre)


class NiveauDePageFilter(admin.SimpleListFilter):
    """
    Filtre le niveau des pages affichees dans la liste.
    / Filters the level of the pages shown in the list.

    Sans selection, la liste ne montre que les pages PRINCIPALES : les
    sous-pages se consultent en depliant le chevron de leur parent.
    / With no selection, the list only shows MAIN pages: sub-pages are consulted
    by expanding their parent's chevron.
    """

    title = _("Niveau")
    parameter_name = "niveau"

    def lookups(self, request, model_admin):
        return [
            ("sous_pages", _("Sous-pages uniquement")),
            ("toutes", _("Toutes les pages")),
        ]

    def queryset(self, request, queryset):
        if self.value() == "toutes":
            return queryset
        if self.value() == "sous_pages":
            return queryset.filter(parent__isnull=False)
        # Une RECHERCHE porte sur tout le site : la restreindre aux pages
        # principales ferait repondre « aucun resultat » pour un article
        # pourtant present, et la recherche passerait pour cassee.
        # / A SEARCH covers the whole site: restricting it to main pages would
        # answer "no result" for an article that does exist, and the search
        # would look broken.
        if request.GET.get("q"):
            return queryset
        # Comportement par defaut : uniquement les pages principales.
        # / Default behaviour: main pages only.
        return queryset.filter(parent__isnull=True)


class BlocsSection(TableSection):
    """
    Blocs d'une page, deplies sous sa ligne dans la liste (chevron).
    / Blocks of a page, expanded under its row in the list (chevron).

    Chaque ligne mene a la fiche du bloc : on repere le bloc a corriger sans
    ouvrir la page. / Each row leads to the block form: you spot the block to
    fix without opening the page.
    """

    related_name = "blocs"
    verbose_name = _("Blocs de la page")
    fields = ["type_bloc", "titre", "modifier"]

    def type_bloc(self, instance):
        return instance.get_type_bloc_display()

    type_bloc.short_description = _("Type")

    def titre(self, instance):
        return instance.titre or "—"

    titre.short_description = _("Titre")

    def modifier(self, instance):
        url = reverse("staff_admin:pages_bloc_change", args=[instance.pk])
        return format_html(
            '<a href="{}" class="text-primary-600">{}</a>', url, _("modifier")
        )

    modifier.short_description = _("Action")


class SousPagesSection(TableSection):
    """
    Sous-pages d'une page, depliees sous sa ligne dans la liste (chevron).
    / Sub-pages of a page, expanded under its row in the list (chevron).
    """

    # On vise la property annotee du modele, pas la relation brute : sinon
    # nb_blocs declenche un count() PAR SOUS-PAGE, a chaque affichage de la
    # liste, pour un panneau que personne n'ouvre.
    # / Point at the annotated property, not the raw relation.
    related_name = "enfants_pour_section"
    verbose_name = _("Sous-pages")
    fields = ["titre", "publie", "nb_blocs"]

    def titre(self, instance):
        return _lien_vers_la_fiche(instance)

    titre.short_description = _("Titre")

    def nb_blocs(self, instance):
        # L'annotation vient de Page.enfants_pour_section. Le repli garde la
        # section juste si elle est un jour utilisee hors de cette property.
        # / Annotation from Page.enfants_pour_section; fallback keeps it
        #   correct if the section is ever used elsewhere.
        nombre = getattr(instance, "nb_blocs_annote", None)
        if nombre is not None:
            return nombre
        return instance.blocs.count()

    nb_blocs.short_description = _("Blocs")


@admin.register(ConfigurationSite, site=staff_admin_site)
class ConfigurationSiteAdmin(SingletonModelAdmin, ModelAdmin):
    """
    Admin du singleton de configuration du site (app pages).
    / Admin of the site configuration singleton (pages app).

    Premier reglage : le skin (theme graphique), deplace depuis
    BaseBillet.Configuration.
    / First setting: the skin (graphic theme), moved from BaseBillet.Configuration.
    """

    compressed_fields = True
    warn_unsaved_form = True

    # Mis à None, parce que "SingletonModelAdmin" est une classe de django,
    # et que le template d'unfold n'est pas atteint si on ne fais rien. Permet de respecter les settings.py
    change_form_template = None

    fieldsets = (
        (
            _("Apparence"),
            {
                "fields": ("skin",),
            },
        ),
    )

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request):
        # Singleton : on n'ajoute jamais d'instance supplementaire.
        # / Singleton: never add an extra instance.
        return False

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        # Singleton : pas de suppression.
        # / Singleton: no deletion.
        return False


@admin.register(Page, site=staff_admin_site)
class PageAdmin(ModelAdmin):
    """
    Admin d'une Page : ses metadonnees, et sous le formulaire la page rendue
    avec ses blocs (section « Contenu de la page »).
    / Page admin: its metadata, and below the form the rendered page with its
    blocks ("Page content" section).
    """

    compressed_fields = True
    warn_unsaved_form = True

    # La page RENDUE comme sur le site, sous le formulaire, dans une seule
    # iframe : chaque bloc a sa barre (↑ ↓ Modifier ✕ +). Gabarit pose HORS
    # du <form> (outer) : rien de ce qu'il contient ne soumet la page.
    # Pas d'inline de blocs : un formset renverrait des positions perimees
    # apres un deplacement fait depuis l'iframe.
    # / The page RENDERED as on the site, below the form, in one iframe.
    # Placed OUTSIDE the <form>. No block inline: a formset would send stale
    # positions back after a move made from the iframe.
    change_form_outer_after_template = "admin/pages/page/blocs_de_la_page.html"

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        """
        Ajoute au contexte ce qu'affiche la section « Contenu de la page ».
        / Adds what the "Page content" section displays.

        LOCALISATION : pages/admin.py — PageAdmin.changeform_view

        - `nombre_de_blocs` : sans bloc, la section invite a en ajouter un au
          lieu d'afficher une iframe vide ;
        - `menu_ajout_en_tete` : les modeles de bloc, avec leur lien d'ajout
          en tete de page (inserer_apres=0).
        / nombre_de_blocs: an empty page shows an invitation instead of an
        empty iframe. menu_ajout_en_tete: models with their add-at-top link.
        """
        extra_context = extra_context or {}
        # uuid_ou_none : un identifiant invalide (« abc ») ferait lever une
        # erreur 500 a la requete. On laisse alors Django admin repondre
        # (redirection « objet introuvable »).
        # / An invalid id would raise a 500: let Django admin answer instead.
        uuid_de_la_page = uuid_ou_none(object_id) if object_id else None
        if uuid_de_la_page is not None:
            page = Page.objects.filter(pk=uuid_de_la_page).first()
            if page is not None:
                extra_context["nombre_de_blocs"] = page.blocs.count()
                extra_context["menu_ajout_en_tete"] = menu_d_ajout(page, 0)
        return super().changeform_view(request, object_id, form_url, extra_context)

    def get_urls(self):
        """
        Ajoute la route de l'apercu de la page entiere (une seule iframe).
        / Adds the route of the whole-page preview (a single iframe).

        La vue est une fonction de module (pages/admin_apercu.py), pas une
        methode : Unfold enveloppe les methodes d'un ModelAdmin. Les routes
        custom passent AVANT celles de Django, dont `<path:object_id>/`
        avalerait tout.
        / The view is a module-level function. Custom routes go BEFORE
        Django's, whose `<path:object_id>/` would swallow everything.
        """
        routes_des_blocs = [
            path(
                "<path:object_id>/apercu/",
                self.admin_site.admin_view(vue_apercu_page),
                name="pages_page_apercu",
            ),
        ]
        return routes_des_blocs + super().get_urls()

    # Contenu deplie sous chaque ligne de la liste (chevron) : les blocs de la
    # page et ses sous-pages, cote a cote.
    # / Content expanded under each row of the list (chevron): the page's blocks
    # and its sub-pages, side by side.
    list_sections = [BlocsSection, SousPagesSection]
    list_sections_classes = "lg:grid-cols-2"

    # La place dans la navigation ne se lit que sur la RACINE d'un arbre : les
    # sous-pages heritent du choix de leur racine. Le champ disparait donc des
    # qu'une page parente est choisie — le laisser saisissable alors qu'il est
    # ignore serait de la magie au sens FALC.
    # / The place in the navigation is only read on a tree's ROOT: sub-pages
    # inherit their root's choice. The field therefore disappears as soon as a
    # parent page is picked — leaving it settable while ignored would be magic.
    conditional_fields = {"affichage_nav": "!parent"}

    # Remplit le slug depuis le titre (modifiable ensuite).
    # / Fills the slug from the title (editable afterwards).
    prepopulated_fields = {"slug": ("titre",)}

    list_display = [
        "titre",
        "publie",
        "display_accueil",
        "nb_blocs",
        "nb_sous_pages",
        "display_voir",
        "updated_at",
    ]
    # `publie` se bascule directement depuis la liste (interrupteur), sans
    # ouvrir la fiche : le bouton « Enregistrer » du bas valide la colonne.
    # / `publie` is toggled straight from the list (switch), without opening the
    # form: the bottom "Save" button commits the column.
    list_editable = ["publie"]
    # Tri par GLISSER-DÉPOSER (sortable Unfold, comme les blocs) : la poignée
    # remplace la colonne position ; l'ordre enregistré pilote la navbar.
    # / DRAG-AND-DROP sorting (Unfold sortable, like the blocks): the handle
    # replaces the position column; the saved order drives the navbar.
    ordering_field = "position"
    hide_ordering_field = True
    # NiveauDePageFilter en tete : sans selection, il restreint la liste aux
    # pages principales. / NiveauDePageFilter first: with no selection, it
    # restricts the list to main pages.
    list_filter = [NiveauDePageFilter, "publie", "est_accueil"]
    search_fields = ["titre", "slug"]
    list_select_related = ["parent"]
    ordering = ["position", "titre"]

    def get_queryset(self, request):
        # Annote les deux compteurs pour les afficher sans requete par ligne
        # (N+1). `distinct=True` est indispensable : deux Count sur deux
        # relations inverses dans la meme requete produisent un produit
        # cartesien, et chaque compteur se retrouve multiplie par l'autre.
        # / Annotate both counters to display them without a per-row query
        # (N+1). `distinct=True` is required: two Counts over two reverse
        # relations in one query produce a cartesian product, and each counter
        # ends up multiplied by the other.
        return (
            super()
            .get_queryset(request)
            .annotate(
                _nb_blocs=Count("blocs", distinct=True),
                _nb_sous_pages=Count("enfants", distinct=True),
            )
        )

    fieldsets = (
        (
            _("Page"),
            {
                "fields": (
                    "titre",
                    "slug",
                    "position",
                    ("publie", "est_accueil"),
                    "parent",
                    # `affichage_nav` decide de la place de la page dans la
                    # navigation, et c'est lui qui declenche le menu lateral
                    # (cf. pages/services.py). Sans lui dans le formulaire, le
                    # reglage n'etait modifiable que par l'API ou en base.
                    # / `affichage_nav` decides where the page sits in the
                    # navigation and triggers the side menu. Without it in the
                    # form, the setting was only reachable via the API or the DB.
                    "affichage_nav",
                    "afficher_sommaire",
                ),
            },
        ),
        (
            _("Référencement & partage (SEO)"),
            {
                "fields": (
                    "meta_title",
                    "meta_description",
                    "image",
                    "noindex",
                ),
                "description": _(
                    "Métadonnées pour les moteurs de recherche et le partage sur "
                    "les réseaux sociaux. Tous ces champs sont optionnels."
                ),
            },
        ),
    )

    @display(description=_("Accueil"), boolean=True)
    def display_accueil(self, obj):
        return obj.est_accueil

    @display(description=_("Blocs"))
    def nb_blocs(self, obj):
        # Nombre de blocs de la page (annote dans get_queryset).
        # / Number of blocks on the page (annotated in get_queryset).
        return getattr(obj, "_nb_blocs", obj.blocs.count())

    @display(description=_("Sous-pages"))
    def nb_sous_pages(self, obj):
        # Nombre de sous-pages, depliables par le chevron de la ligne.
        # / Number of sub-pages, expandable through the row's chevron.
        return getattr(obj, "_nb_sous_pages", obj.enfants.count())

    @display(description=_("Voir"))
    def display_voir(self, obj):
        # Lien direct vers la page publique. L'adresse vient de la page
        # elle-meme : voir Page.get_absolute_url().
        # / Direct link to the public page. The address comes from the page
        # itself: see Page.get_absolute_url().
        if not obj.publie:
            return "—"
        url = obj.get_absolute_url()
        return format_html(
            '<a href="{}" target="_blank" rel="noopener">↗ {}</a>', url, _("ouvrir")
        )

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


class ImageGalerieInline(TabularInline):
    """Images d'un bloc, éditées en ligne dans la fiche du bloc.
    / Images of a block, edited inline in the block form."""

    model = ImageGalerie
    extra = 1
    fields = ("image", "legende", "lien_url", "position")
    ordering = ("position",)
    # Tri par glisser-déposer (sortable Unfold) : la poignée remplace la
    # saisie manuelle du nombre, le champ position est masqué.
    # / Drag-and-drop sorting (Unfold sortable): the handle replaces manual
    # number input, the position field is hidden.
    ordering_field = "position"
    hide_ordering_field = True

    # Les 4 permissions sont OBLIGATOIRES. Sans elles, Django retombe sur les
    # permissions modele (`user.has_perm`), qu'un administrateur de tenant n'a
    # pas : Django ecarte alors l'inline du formulaire, et l'encart « Images »
    # devient invisible pour tout le monde sauf un superuser — rendant les
    # galeries et les images d'article inutilisables.
    # / The 4 permissions are MANDATORY. Without them Django falls back to model
    # permissions, which a tenant admin does not hold: Django then drops the
    # inline from the form, making the images box invisible to everyone but a
    # superuser — leaving galleries and article images unusable.
    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


def _choix_du_modele():
    """
    Les choix du select « Modele de bloc », groupes par type.
    / Choices of the "block model" select, grouped by type.

    LOCALISATION : pages/admin.py

    Un type a plusieurs affichages devient un groupe (<optgroup>) ; un type a
    rendu unique est une option simple. Construit depuis modeles_de_bloc()
    (pages/admin_apercu.py), donc depuis le catalogue.
    / A multi-affichage type becomes an <optgroup>; a single-rendering type is
    a plain option.
    """
    choix = [("", _("— Choisir un modèle de bloc —"))]
    for groupe in modeles_de_bloc():
        modeles = groupe["modeles"]
        type_a_rendu_unique = len(modeles) == 1 and not modeles[0]["affichage"]
        if type_a_rendu_unique:
            choix.append((modeles[0]["valeur"], groupe["libelle"]))
            continue
        options = []
        for modele in modeles:
            options.append((modele["valeur"], modele["libelle"]))
        choix.append((groupe["libelle"], options))
    return choix


def _modele_initial(formulaire):
    """
    Valeur de depart du select « Modele de bloc ».
    / Initial value of the "block model" select.

    - bloc existant : son type et son affichage ;
    - nouveau bloc : le type et l'affichage passes dans l'URL par les menus
      « + Ajouter » de la fiche Page (Django les met dans `initial`).
    Un type a plusieurs rendus sans affichage prend son affichage par defaut.
    / Existing block: its type and affichage. New block: those passed in the
    URL by the "+ Add" menus.
    """
    if not formulaire.instance._state.adding:
        type_bloc = formulaire.instance.type_bloc
        affichage = formulaire.instance.affichage
    else:
        type_bloc = formulaire.initial.get("type_bloc", "")
        affichage = formulaire.initial.get("affichage", "")
    if not type_bloc:
        return ""
    if not affichage and AFFICHAGES_PAR_TYPE.get(type_bloc):
        affichage = AFFICHAGE_PAR_DEFAUT.get(type_bloc, "")
    if not AFFICHAGES_PAR_TYPE.get(type_bloc):
        affichage = ""
    return valeur_du_modele(type_bloc, affichage)


class BlocAdminForm(forms.ModelForm):
    """Formulaire du Bloc : editeur WYSIWYG sur le champ texte, et editeur
    MARKDOWN (EasyMDE, vendorise) sur le champ de formulaire texte_markdown.

    POURQUOI DEUX CHAMPS pour un seul champ modele (texte) : le WYSIWYG Trix
    produit du HTML — taper de la source Markdown dedans est penible et la
    mutile. Le bloc TEXTE a donc SON champ de formulaire (texte_markdown,
    affiche uniquement pour ce type via conditional_fields), edite avec
    EasyMDE (barre d'outils + apercu), et recopie dans obj.texte a la
    sauvegarde (save_model).
    / Bloc form: WYSIWYG editor on the text field, and a MARKDOWN editor
    (vendored EasyMDE) on the texte_markdown form field. WHY TWO form fields
    for one model field: Trix produces HTML — typing Markdown source in it is
    painful. The TEXTE block gets its own form field (shown only for that
    type), edited with EasyMDE, copied into obj.texte on save."""

    # Source Markdown du contenu (bloc TEXTE uniquement). Champ de
    # FORMULAIRE : la valeur vit dans Bloc.texte.
    # / Article Markdown source (TEXTE block only). FORM field: the value
    # lives in Bloc.texte.
    texte_markdown = forms.CharField(
        required=False,
        label=_("Texte de l'article (Markdown)"),
        help_text=_(
            "Syntaxe Markdown : ## titre, **gras**, [lien](url), "
            "![légende](galerie:1) pour vos images. Aperçu via l'œil de la "
            "barre d'outils."
        ),
        widget=forms.Textarea(attrs={"class": "editeur-markdown", "rows": 16}),
    )

    # Editeurs de lignes : ils remplacent la saisie de JSON brut pour
    # `contenu` et `points_gps` (meme principe que texte_markdown : un champ
    # de FORMULAIRE qui alimente un champ modele, dans save_model).
    # Le rendu et la lecture des lignes : pages/admin_widgets.py.
    # / Line editors replacing raw JSON input for `contenu` and `points_gps`
    # (same idea as texte_markdown: a FORM field feeding a model field).
    contenu_lieu = LignesField(
        editeur="lieu",
        label=_("Infos pratiques (à côté de la carte)"),
    )
    contenu_cartes = LignesField(
        editeur="cartes",
        label=_("Éléments de la section"),
    )
    points_gps_editeur = LignesField(
        editeur="gps",
        label=_("Points sur la carte"),
    )

    # « Modele de bloc » : UN select pour le type ET l'affichage, groupe par
    # type (ex. « Section mise en avant › Carte »). Valeur "SECTION:CARTE",
    # redecoupee dans clean(). Les choix sont une FONCTION : Django la rappelle
    # a chaque formulaire, les libelles suivent donc la langue de la requete.
    # / ONE select for type AND affichage, grouped by type. Value
    # "SECTION:CARTE", split in clean(). Choices are a callable, re-evaluated
    # per form so labels follow the request language.
    modele = forms.ChoiceField(
        label=_("Modèle de bloc"),
        help_text=_(
            "Ce que montre le bloc, et sous quelle forme. Les champs à remplir "
            "s'adaptent au modèle choisi."
        ),
        choices=_choix_du_modele,
        widget=UnfoldAdminSelectWidget,
    )

    # Skin du site, pour les conditions d'affichage (cf. _CHAMP_SKIN). Champ
    # cache, jamais enregistre. / Site skin for display conditions. Hidden,
    # never saved.
    skin_du_site = forms.CharField(required=False, widget=forms.HiddenInput())

    class Meta:
        model = Bloc
        fields = "__all__"
        widgets = {
            "texte": WysiwygWidget,
        }

    class Media:
        css = {"all": (
            "pages/vendor/easymde/easymde.min.css",
            "pages/admin/editeur_markdown.css",
            # Disposition formulaire | apercu en direct.
            # / Form | live preview layout.
            "pages/admin/apercu_bloc.css",
        )}
        js = (
            "pages/vendor/easymde/easymde.min.js",
            "pages/admin/editeur_markdown.js",
        )

    def clean(self):
        """
        Redecoupe le « Modele de bloc » en type + affichage.
        / Splits the "block model" back into type + affichage.

        C'est ICI, et pas dans le navigateur, que type et affichage sont
        fixes : les valeurs des champs caches ne sont qu'une copie pour
        l'affichage. Bloc.clean() (appele ensuite par Django) verifie que
        l'affichage appartient bien au type.
        / Type and affichage are set HERE, not in the browser. Bloc.clean()
        then checks the affichage belongs to the type.
        """
        donnees = super().clean()
        modele = donnees.get(CHAMP_MODELE)
        if modele:
            type_bloc, affichage = decouper_modele(modele)
            donnees["type_bloc"] = type_bloc
            donnees["affichage"] = affichage
        return donnees

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Import local : BaseBillet.views importe pages (import circulaire).
        # / Local import: BaseBillet.views imports pages (circular import).
        from BaseBillet.views import get_skin_courant

        self.fields["skin_du_site"].initial = get_skin_courant()

        # La page d'un bloc ne se choisit pas dans sa fiche : un bloc s'ajoute
        # depuis la fiche de SA page (menus « + » de la section « Contenu de la
        # page », qui passent ?page=<uuid> dans l'URL). Le champ reste dans le formulaire, cache :
        # - a la creation, il porte la page recue dans l'URL ;
        # - a la modification, il est `disabled` : Django ignore toute valeur
        #   postee et garde la page d'origine.
        # / A block's page is not picked in its form: blocks are added from
        # their page. The field stays, hidden; on edit it is disabled, so Django
        # ignores any posted value and keeps the original page.
        if "page" in self.fields:
            self.fields["page"].widget = forms.HiddenInput()
            if not self.instance._state.adding:
                self.fields["page"].disabled = True

        # Type et affichage : caches, pilotes par le select « Modele de bloc ».
        # A chaque changement du select, Alpine recopie le type et l'affichage
        # dans ces deux champs : les conditions d'affichage des autres champs
        # (conditional_fields) les lisent. La valeur ENREGISTREE, elle, vient
        # de clean(), qui redecoupe le modele : on ne compte pas sur Alpine.
        # / Hidden, driven by the model select: Alpine copies type and affichage
        # on change for the display conditions. The SAVED value comes from
        # clean(), which splits the model: no reliance on Alpine.
        for nom_du_champ_cache in ("type_bloc", "affichage"):
            if nom_du_champ_cache in self.fields:
                self.fields[nom_du_champ_cache].widget = forms.HiddenInput()
                self.fields[nom_du_champ_cache].required = False
        self.fields[CHAMP_MODELE].widget.attrs["x-on:change"] = (
            "type_bloc = $event.target.value.split(':')[0]; "
            "affichage = $event.target.value.split(':')[1] || ''"
        )
        self.fields[CHAMP_MODELE].initial = _modele_initial(self)

        # Bloc TEXTE existant : la source Markdown est dans instance.texte.
        # `_state.adding` et non `pk` : la cle primaire est un UUID avec
        # default=uuid4, donc `pk` est TOUJOURS renseigne, meme sur un objet
        # jamais enregistre. / Existing TEXTE block: the Markdown source lives
        # in instance.texte. `_state.adding`, not `pk`: the primary key is a
        # UUID with default=uuid4, so `pk` is ALWAYS set, even on a new object.
        if not self.instance._state.adding and self.instance.type_bloc == Bloc.TEXTE:
            self.fields["texte_markdown"].initial = self.instance.texte
        # Les editeurs de lignes partent de la valeur en base. `contenu` sert a
        # deux editeurs : seul celui du type du bloc est pre-rempli, sinon un
        # bloc LIEU montrerait ses infos pratiques dans l'editeur des
        # sous-cartes (cache, mais renvoye a l'enregistrement).
        # / Line editors start from the stored value. Only the editor matching
        # the block type is pre-filled with `contenu`.
        if not self.instance._state.adding:
            if self.instance.type_bloc == Bloc.LIEU:
                self.fields["contenu_lieu"].initial = self.instance.contenu
                self.fields["points_gps_editeur"].initial = self.instance.points_gps
            elif self.instance.type_bloc == Bloc.SECTION:
                self.fields["contenu_cartes"].initial = self.instance.contenu
        # Table RANG -> URL des images de l'inline, embarquée en data-attribute :
        # l'APERÇU EasyMDE (rendu côté navigateur) peut ainsi résoudre les
        # références ![légende](galerie:N) au lieu d'afficher une image cassée.
        # Le rang commence à 1 et suit l'ordre d'affichage, comme la résolution
        # au rendu (cf. rendre_bloc_markdown) : les deux doivent numéroter
        # pareil, sinon l'aperçu montre autre chose que la page publiée.
        # / RANK -> URL table of the inline images, embedded as a data attribute
        # so the EasyMDE PREVIEW (browser-side) resolves ![caption](galerie:N).
        # Ranks start at 1 and follow display order, exactly like the render-time
        # resolution: both must number alike, or the preview shows something
        # else than the published page.
        if not self.instance._state.adding:
            import json

            urls_galerie = {
                rang: image.image.med.url
                for rang, image in enumerate(
                    self.instance.images_galerie.order_by("position"), start=1
                )
                if image.image
            }
            self.fields["texte_markdown"].widget.attrs["data-galerie"] = json.dumps(urls_galerie)


# Ancre de la section « Contenu de la page » (blocs rendus) sur la fiche d'une
# page. Elle est posee par admin/pages/page/blocs_de_la_page.html.
# / Anchor of the "Page content" section (rendered blocks) on a page form.
_ANCRE_CONTENU_DE_LA_PAGE = "#blocs-de-la-page"


def _position_d_insertion_demandee(request):
    """
    Lit `inserer_apres` dans l'URL du formulaire d'ajout d'un bloc.
    / Reads `inserer_apres` from the block add form URL.

    LOCALISATION : pages/admin.py

    Le parametre vient des menus « + » de la fiche Page : « + Ajouter en
    tete » (inserer_apres=0) et le + de la barre de chaque bloc
    (inserer_apres=<rang du bloc>). Les liens sont construits par
    pages/admin_apercu.py:url_d_ajout_d_un_bloc, et affiches par
    admin/pages/apercu/_menu_modeles.html. Le formulaire d'ajout poste vers sa
    propre URL : le parametre est donc toujours la au POST.
    Helper de module (pas une methode : Unfold enveloppe celles du ModelAdmin).
    / Comes from the "+" menus of the Page form (built by url_d_ajout_d_un_bloc).
    The add form posts to its own URL, so the parameter is still there on POST.

    :return: un entier >= 0, ou None si absent ou invalide
    """
    valeur = request.GET.get("inserer_apres", "")
    if not valeur.isdigit():
        return None
    return int(valeur)


def _page_de_l_url_existe(request):
    """
    Vrai si `?page=<uuid>` designe une page existante.
    / True if `?page=<uuid>` points to an existing page.

    LOCALISATION : pages/admin.py
    Une valeur qui n'est pas un UUID ferait lever une erreur a la requete :
    on la verifie d'abord. / A non-UUID value would make the query fail.
    """
    uuid_de_la_page = uuid_ou_none(request.GET.get("page", ""))
    if uuid_de_la_page is None:
        return False
    return Page.objects.filter(pk=uuid_de_la_page).exists()


def _url_contenu_de_la_page(page):
    """
    URL de la fiche d'une page, positionnee sur ses blocs rendus.
    / URL of a page form, scrolled to its rendered blocks.

    LOCALISATION : pages/admin.py

    Helper defini AU NIVEAU DU MODULE, jamais dans BlocAdmin : Unfold wrappe les
    methodes d'un ModelAdmin avec son systeme d'actions et casserait l'appel.
    / Module-level helper, never a ModelAdmin method: Unfold wraps ModelAdmin
    methods with its action system and would break the call.
    """
    url_de_la_page = reverse("staff_admin:pages_page_change", args=[page.pk])
    return f"{url_de_la_page}{_ANCRE_CONTENU_DE_LA_PAGE}"


@admin.register(Bloc, site=staff_admin_site)
class BlocAdmin(ModelAdmin):
    """
    Fiche complete d'un Bloc, avec son apercu en direct.
    / Full Bloc form, with its live preview.

    CHOIX DU MODELE : un seul select, « Modele de bloc » (champ de formulaire
    `modele`, valeur "TYPE:AFFICHAGE"). type_bloc et affichage restent dans le
    formulaire, CACHES : Alpine y recopie le modele choisi, et les
    conditional_fields NATIFS d'Unfold les lisent, ex.
    "type_bloc == 'SECTION' && affichage == 'CARTE'". Les valeurs enregistrees
    viennent de BlocAdminForm.clean(), qui redecoupe le modele cote serveur.
    / A single "block model" select; type_bloc and affichage stay as HIDDEN
    fields read by Unfold's conditional_fields. Saved values come from clean().

    ACCES : depuis la section « Contenu de la page » de la fiche Page (bouton
    Modifier d'un bloc, ou un menu « + » pour en ajouter un). La page du bloc
    est un champ cache, jamais modifiable ici ; sans ?page= dans l'URL, l'ajout
    renvoie vers la liste des pages (add_view). L'ordre des blocs se regle avec
    ↑ ↓ sur la fiche Page (ou par glisser-deposer dans la liste des blocs).
    / Reached from the Page form's "Page content" section. The page is a hidden
    field, never editable here. Order is set with ↑ ↓ on the Page form (or by
    drag-and-drop in the block list).
    """

    compressed_fields = True
    warn_unsaved_form = True
    form = BlocAdminForm
    # Notes d'aide affichees au-dessus du formulaire, chacune visible pour un
    # type ou un couple (type, affichage) donne — via Alpine, meme mecanisme
    # que conditional_fields.
    # / Help notes shown above the form, each revealed for a given type or
    # (type, affichage) pair — via Alpine, same mechanism as conditional_fields.
    # before.html assemble le panneau d'APERCU EN DIRECT et les notes d'aide.
    # / before.html gathers the LIVE PREVIEW panel and the help notes.
    change_form_before_template = "admin/pages/bloc/before.html"
    # Bouton « Retour a la page », AU-DESSUS du formulaire (hors <form>, sur
    # toute la largeur, hors de la grille formulaire | apercu).
    # / "Back to the page" button, ABOVE the form, full width.
    change_form_outer_before_template = "admin/pages/bloc/retour_page.html"
    # Images du bloc (inline).
    # / Block images (inline).
    inlines = [ImageGalerieInline]

    def get_inlines(self, request, obj=None):
        """
        N'affiche l'inline « Images » que la ou ces images seront RENDUES.
        / Show the images inline only where those images will be RENDERED.

        LOCALISATION : pages/admin.py — BlocAdmin.get_inlines

        Deux cas seulement :
        - TEXTE : les images illustrent l'article et se referencent dans la
          source Markdown via ![legende](galerie:N) (N = position dans l'inline) ;
        - IMAGES en GRILLE ou BANDE_LOGOS : les images SONT le contenu du bloc.
        Les affichages PLEINE_LARGEUR et VIGNETTE_TITRE, eux, lisent le champ
        `image` du bloc : leur proposer l'inline ferait saisir des images que le
        gabarit ne regarde jamais.
        A la CREATION (obj=None), le type n'est pas encore connu cote serveur :
        l'inline apparait apres le premier enregistrement (flux Django standard).
        / Only two cases: TEXTE (images referenced from the Markdown source) and
        IMAGES in GRILLE or BANDE_LOGOS (the images ARE the content).
        PLEINE_LARGEUR and VIGNETTE_TITRE read the block's `image` field instead:
        offering them the inline would collect images the template never reads.
        On CREATION (obj=None) the type is unknown server-side, so the inline
        appears after the first save.
        """
        if obj is None:
            return []
        if obj.type_bloc == Bloc.TEXTE:
            return [ImageGalerieInline]
        if (obj.type_bloc, obj.affichage) in AFFICHAGES_AVEC_GALERIE:
            return [ImageGalerieInline]
        return []

    # Liste : réordonnancement par GLISSER-DÉPOSER (sortable Unfold, comme la
    # démo formula/circuit). ordering_field ajoute la poignée de tri et
    # enregistre les positions dans l'ordre affiché ; hide_ordering_field
    # masque la colonne du nombre. Conseil d'usage : filtrer par page d'abord
    # (le tri mélange sinon les blocs de toutes les pages).
    # / List: DRAG-AND-DROP reordering (Unfold sortable, like the
    # formula/circuit demo). ordering_field adds the drag handle and saves the
    # positions in the displayed order; hide_ordering_field hides the number
    # column. Usage tip: filter by page first.
    list_display = ["__str__", "page", "type_bloc"]
    ordering_field = "position"
    hide_ordering_field = True
    # Filtres avancés Unfold (pattern « driverwithfilters » de la démo) :
    # - page : AUTOCOMPLETE (la liste brute de liens explosait avec le blog,
    #   chaque article étant une page) ;
    # - page__parent : tous les blocs des sous-pages d'une page (ex. tous les
    #   blocs des articles du Journal) ;
    # - type_bloc : menu déroulant compact (7 types).
    # list_filter_submit : bouton « Filtrer » (une requête, pas une par clic).
    # / Unfold advanced filters (demo's "driverwithfilters" pattern):
    # autocomplete on page (the raw link list exploded with the blog), parent
    # page filter (all blocks of a page's sub-pages), compact dropdown for
    # the 7 types, and a submit button (one query, not one per click).
    list_filter = [
        "page",  # liens cliquables (préférence mainteneur) / clickable links
        ("page__parent", AutocompleteSelectFilter),
        ("type_bloc", ChoicesDropdownFilter),
    ]
    # Filtres SUR la page, au-dessus de la liste (pattern « driverwithfilters »
    # de la démo Unfold) : le filtre page devient une barre de LIENS cliquables,
    # les selects s'appliquent à la sélection (auto-submit) — plus de tiroir
    # latéral ni de bouton « Filtrer ».
    # / Filters ON the page, above the list (Unfold demo's "driverwithfilters"
    # pattern): the page filter renders as a clickable LINKS bar, selects
    # auto-submit — no more side sheet nor "Filter" button.
    list_filter_sheet = False
    list_select_related = ["page"]
    search_fields = ["titre", "texte"]
    ordering = ["page", "position"]

    # "position" RETIRÉ du formulaire : l'ordre se règle par glisser-déposer
    # dans la liste (sortable Unfold) ; à la création, save_model place le bloc
    # en fin de page automatiquement.
    # / "position" REMOVED from the form: ordering is done by drag-and-drop in
    # the changelist (Unfold sortable); on creation, save_model appends the
    # block at the end of the page automatically.
    # Les champs du formulaire et leur visibilite sont DERIVES du catalogue
    # (pages/blocs_catalogue.py), jamais recopies : une liste tenue a la main
    # a cote du catalogue finit par decrire un modele qui n'existe plus, et
    # Django ne s'en apercoit qu'a la fabrication du formulaire — donc en 500
    # sur la fiche, pas au demarrage.
    # / Form fields and their visibility are DERIVED from the catalogue, never
    # copied: a hand-kept list drifts from the model, and Django only notices
    # when it builds the form — a 500 on the page, not at boot.
    # `affichage` n'est pas repris ici : il vient du catalogue, comme les
    # autres champs. / `affichage` is not repeated here: it comes from the
    # catalogue like every other field.
    # `page` et `skin_du_site` sont des champs CACHES (cf. BlocAdminForm) :
    # on ne change pas la page d'un bloc depuis sa fiche.
    # / `page` and `skin_du_site` are HIDDEN fields: a block's page is not
    # changed from its form.
    # « modele » en tete : c'est le premier choix de la fiche.
    # / "modele" first: it is the form's first choice.
    fields = (CHAMP_MODELE, "type_bloc", "page", _CHAMP_SKIN) + _CHAMPS_DU_CATALOGUE

    # Expressions Alpine.js evaluees cote navigateur par conditional_fields
    # (natif Unfold) : un champ n'apparait que pour les types qui l'utilisent.
    # / Alpine.js expressions evaluated browser-side by Unfold's native
    # conditional_fields: a field only shows for the types that use it.
    conditional_fields = _visibilite_des_champs()

    def save_model(self, request, obj, form, change):
        """
        Nettoie le bloc, recopie les editeurs de lignes, puis le place dans sa
        page avant de l'enregistrer.
        / Cleans the block, copies the line editors, then places it in its page
        before saving.

        LOCALISATION : pages/admin.py — BlocAdmin.save_model

        1. nettoyer_bloc (pages/admin_apercu.py) : clean_html sur les champs
           texte, SAUF la source Markdown du bloc TEXTE (posee apres, depuis
           texte_markdown) ; URL a schema dangereux videes. L'apercu en direct
           appelle la meme fonction.
        2. appliquer_editeurs_de_lignes : les lignes saisies deviennent
           `contenu` / `points_gps`, selon le type choisi.
        3. A la creation : si on vient d'un menu « + » de la fiche Page,
           `inserer_apres` (dans l'URL du formulaire d'ajout) dit ou placer le
           bloc. Sinon, il va en fin de page.
        / 1. Same cleaning as the live preview. 2. Lines become JSON fields.
        3. On creation, `inserer_apres` (in the add form URL) places the block;
        otherwise it goes at the end of the page.
        """
        nettoyer_bloc(obj, form.cleaned_data.get("texte_markdown", ""))
        appliquer_editeurs_de_lignes(
            obj,
            contenu_lieu=form.cleaned_data.get(CHAMP_CONTENU_LIEU, []),
            contenu_cartes=form.cleaned_data.get(CHAMP_CONTENU_CARTES, []),
            points_gps=form.cleaned_data.get(CHAMP_POINTS_GPS, []),
        )

        bloc_est_nouveau = not change
        if bloc_est_nouveau and obj.page_id:
            inserer_apres = _position_d_insertion_demandee(request)
            if inserer_apres is not None:
                inserer_bloc_apres(obj, inserer_apres)
            elif not obj.position:
                # En fin de page (max + 1). / At the end of the page.
                derniere_position = Bloc.objects.filter(page=obj.page).aggregate(
                    maxi=Max("position")
                )["maxi"] or 0
                obj.position = derniere_position + 1

        super().save_model(request, obj, form, change)

    def add_view(self, request, form_url="", extra_context=None):
        """
        Un bloc s'ajoute toujours depuis la fiche de sa page.
        / A block is always added from its page form.

        LOCALISATION : pages/admin.py — BlocAdmin.add_view

        La page n'est plus un select dans la fiche du bloc. Sans `?page=` dans
        l'URL (bouton « Ajouter » de la liste des blocs), on renvoie vers la
        liste des pages avec une explication, plutot que d'ouvrir un
        formulaire impossible a enregistrer.
        / The page is no longer a select. Without `?page=`, redirect to the page
        list with an explanation instead of an unsavable form.
        """
        page_existe = _page_de_l_url_existe(request)
        if not page_existe:
            messages.info(
                request,
                _(
                    "Un bloc s'ajoute depuis la fiche de sa page : ouvrez la "
                    "page, puis « + Ajouter en tête » ou le + d'un bloc."
                ),
            )
            return HttpResponseRedirect(reverse("staff_admin:pages_page_changelist"))
        return super().add_view(request, form_url, extra_context)

    def get_urls(self):
        """
        Routes de l'apercu en direct, des editeurs de lignes et des actions
        ↑ ↓ 🗑 de la fiche Page.
        / Routes of the live preview, line editors and Page form ↑ ↓ 🗑 actions.

        Les vues sont des fonctions de module (pages/admin_apercu.py). Les
        routes custom passent AVANT celles de Django, dont `<path:object_id>/`
        avalerait tout.
        / Views are module-level functions. Custom routes go BEFORE Django's.
        """
        vue_admin = self.admin_site.admin_view
        routes_de_l_apercu = [
            path(
                "apercu/",
                vue_admin(vue_apercu_bloc_en_direct),
                name="pages_bloc_apercu",
            ),
            path(
                "editeur-ligne/",
                vue_admin(vue_ligne_vide),
                name="pages_bloc_editeur_ligne",
            ),
            path(
                "<path:object_id>/deplacer/<str:sens>/",
                vue_admin(vue_deplacer_bloc),
                name="pages_bloc_deplacer",
            ),
            path(
                "<path:object_id>/retirer/",
                vue_admin(vue_retirer_bloc),
                name="pages_bloc_retirer",
            ),
        ]
        return routes_de_l_apercu + super().get_urls()

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        """
        Fil d'Ariane : on remplace « Blocs » par la PAGE d'appartenance.
        / Breadcrumb: replace "Blocs" with the owning PAGE.

        LOCALISATION : pages/admin.py — BlocAdmin.changeform_view

        Le titre de page d'Unfold se construit a partir de `opts` et `original`
        (cf. son template tag header_title). En y posant la Page, le fil devient
        « Pages / <nom de la page> » et ramene la ou l'on editait, au lieu de la
        liste de TOUS les blocs, ou l'on ne sait plus a quelle page ils
        appartiennent.
        / Unfold builds its page title from `opts` and `original`. Putting the
        Page there makes the trail read "Pages / <page name>" and lead back to
        where the user was editing, instead of the list of ALL blocks.
        """
        extra_context = extra_context or {}
        page_du_bloc = None
        if object_id:
            uuid_du_bloc = uuid_ou_none(object_id)
            bloc = None
            if uuid_du_bloc is not None:
                bloc = Bloc.objects.select_related("page").filter(pk=uuid_du_bloc).first()
            if bloc and bloc.page:
                extra_context["opts"] = Page._meta
                extra_context["original"] = bloc.page
                page_du_bloc = bloc.page
        elif _page_de_l_url_existe(request):
            # Ajout depuis la fiche Page : la page vient de ?page=<uuid>.
            # / Adding from the Page form: the page comes from ?page=<uuid>.
            page_du_bloc = Page.objects.filter(pk=request.GET["page"]).first()

        # Bouton « Retour a la page » (admin/pages/bloc/retour_page.html).
        # / "Back to the page" button.
        if page_du_bloc is not None:
            extra_context["page_du_bloc"] = page_du_bloc
            extra_context["url_retour_page"] = _url_contenu_de_la_page(page_du_bloc)
        return super().changeform_view(request, object_id, form_url, extra_context)

    def response_post_save_change(self, request, obj):
        """
        Apres « Enregistrer », on retourne a la section « Contenu de la page »
        de la fiche de la page.
        / After "Save", go back to the page form's "Page content" section.

        LOCALISATION : pages/admin.py — BlocAdmin.response_post_save_change

        On surcharge `response_post_save_change` et NON `response_change` :
        Django n'appelle ce hook que pour le bouton « Enregistrer » simple.
        « Enregistrer et continuer les modifications » garde donc son
        comportement normal (on reste sur la fiche du bloc).
        / We override `response_post_save_change`, NOT `response_change`: Django
        only calls this hook for the plain "Save" button, so "Save and continue
        editing" keeps its normal behaviour.
        """
        if obj.page_id:
            return HttpResponseRedirect(_url_contenu_de_la_page(obj.page))
        return super().response_post_save_change(request, obj)

    def response_add(self, request, obj, post_url_continue=None):
        """
        « Enregistrer et ajouter un nouveau » : le bloc suivant va dans la
        MEME page, juste apres celui qu'on vient de creer.
        / "Save and add another": the next block goes in the SAME page, right
        after the one just created.

        Sans ce retour, Django ouvrirait le formulaire d'ajout sans `?page=`,
        et add_view renverrait vers la liste des pages.
        / Otherwise Django would open the add form without `?page=`.
        """
        if "_addanother" in request.POST and obj.page_id:
            url_d_ajout = reverse("staff_admin:pages_bloc_add")
            return HttpResponseRedirect(
                f"{url_d_ajout}?page={obj.page_id}&inserer_apres={obj.position}"
            )
        return super().response_add(request, obj, post_url_continue)

    def response_post_save_add(self, request, obj):
        # Meme retour apres la creation d'un bloc.
        # / Same return trip after creating a block.
        if obj.page_id:
            return HttpResponseRedirect(_url_contenu_de_la_page(obj.page))
        return super().response_post_save_add(request, obj)

    def delete_model(self, request, obj):
        # On retient la page AVANT la suppression, pour y revenir ensuite
        # (response_delete ne recoit plus l'objet).
        # / Remember the page BEFORE deletion, to go back to it afterwards.
        request._page_du_bloc_supprime = obj.page
        super().delete_model(request, obj)

    def response_delete(self, request, obj_display, obj_id):
        """
        Apres la suppression d'un bloc, on retourne aux blocs de sa page.
        / After deleting a block, go back to its page's blocks.
        """
        page_du_bloc = getattr(request, "_page_du_bloc_supprime", None)
        if page_du_bloc is not None:
            return HttpResponseRedirect(_url_contenu_de_la_page(page_du_bloc))
        return super().response_delete(request, obj_display, obj_id)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)
