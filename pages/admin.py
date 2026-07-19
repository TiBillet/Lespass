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
- La fiche d'une page porte un onglet « Blocs » : sommaire de ses blocs
  (type, titre), reordonnables par glisser-deposer, avec un lien « modifier »
  vers la fiche complete du bloc.
- La fiche d'un bloc porte le contenu. Premiere action : choisir le TYPE -> les
  champs correspondants se deroulent (conditional_fields NATIF d'Unfold /
  Alpine.js, aucun JavaScript maison).
/ EDITING UX: the PAGE is the entry point.
- The page list only shows MAIN pages (no parent). Each row's chevron expands
  its sub-pages (list_sections). The "Level" filter brings back the full list.
- A page form carries a "Blocks" tab: a summary of its blocks (type, title),
  reorderable by drag-and-drop, with an "edit" link to the full block form.
- The block form carries the content. First action: choose the TYPE -> matching
  fields unfold (Unfold's NATIVE conditional_fields / Alpine.js, no custom JS).

POURQUOI LE SOMMAIRE ET NON LE CONTENU DANS L'INLINE : conditional_fields
d'Unfold ne s'applique qu'au formulaire principal (le scope Alpine est pose sur
le <form> du changeform, a partir des champs de `adminform`). Une inline qui
porterait les ~30 champs du catalogue les afficherait donc TOUS, pour tous les
types, sur chaque ligne.
/ WHY A SUMMARY AND NOT THE CONTENT IN THE INLINE: Unfold's conditional_fields
only applies to the main form (the Alpine scope sits on the changeform <form>,
built from `adminform` fields). An inline carrying the catalogue's ~30 fields
would show them ALL, for every type, on every row.
"""

from django import forms
from django.contrib import admin
from django.db.models import Count, Max
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from solo.admin import SingletonModelAdmin
from unfold.admin import ModelAdmin, TabularInline
from unfold.contrib.filters.admin import (
    AutocompleteSelectFilter,
    ChoicesDropdownFilter,
)
from unfold.contrib.forms.widgets import WysiwygWidget
from unfold.decorators import display
from unfold.sections import TableSection

from Administration.admin.site import sanitize_textfields, staff_admin_site
from Administration.utils import url_a_schema_dangereux
from ApiBillet.permissions import TenantAdminPermissionWithRequest
from pages.models import Bloc, ConfigurationSite, ImageGalerie, Page
from pages.blocs_catalogue import (
    AFFICHAGES_AVEC_GALERIE,
    AFFICHAGES_PAR_TYPE,
    CHAMPS_PAR_AFFICHAGE,
    CHAMPS_PAR_TYPE,
)


# Champ de formulaire dedie a la saisie Markdown (editeur EasyMDE) : il double
# le champ modele `texte` pour le seul type TEXTE, dont la source ne doit pas
# passer par le WYSIWYG. / Dedicated Markdown form field (EasyMDE editor): it
# doubles the `texte` model field for the TEXTE type only.
_CHAMP_MARKDOWN = "texte_markdown"


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
    return tuple(champs)


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


def _expression_alpine(types):
    """
    Rend l'expression Alpine.js qui n'affiche un champ que pour ces types.
    / Renders the Alpine.js expression showing a field only for these types.
    """
    if len(types) == 1:
        return _test_du_type(types[0])
    liste = ",".join(f"'{t}'" for t in types)
    return f"[{liste}].includes(type_bloc)"


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
                fragments_par_champ.setdefault(champ, []).append(
                    _test_du_type(type_bloc)
                )
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

    # L'affichage n'a de sens que pour les types qui en proposent plusieurs.
    # / The affichage only matters for types offering more than one.
    types_avec_affichage = [
        type_bloc for type_bloc, valeurs in AFFICHAGES_PAR_TYPE.items() if valeurs
    ]
    visibilite["affichage"] = _expression_alpine(types_avec_affichage)

    # La page a lister ne concerne que le bloc LISTE.
    # / The page to list only concerns the LISTE block.
    visibilite["page_source"] = _test_du_type("LISTE")

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

    related_name = "enfants"
    verbose_name = _("Sous-pages")
    fields = ["titre", "publie", "nb_blocs"]

    def titre(self, instance):
        return _lien_vers_la_fiche(instance)

    titre.short_description = _("Titre")

    def nb_blocs(self, instance):
        return instance.blocs.count()

    nb_blocs.short_description = _("Blocs")


class BlocInline(TabularInline):
    """
    Sommaire des blocs d'une page, dans un onglet de sa fiche.
    / Summary of a page's blocks, in a tab of its form.

    Les colonnes se limitent au type et au titre : le contenu se saisit dans la
    fiche du bloc, ou les champs s'adaptent au type choisi (cf. docstring du
    module). Le lien « modifier » de chaque ligne y mene.
    / Columns are limited to type and title: content is typed in the block form,
    where fields adapt to the chosen type (see the module docstring). Each row's
    "edit" link goes there.
    """

    model = Bloc
    # Bloc porte deux cles etrangeres vers Page : `page` (la page qui affiche le
    # bloc) et `page_source` (la page dont un bloc LISTE affiche les enfants).
    # / Bloc carries two foreign keys to Page: `page` (the page displaying the
    # block) and `page_source` (the page whose children a LISTE block shows).
    fk_name = "page"
    extra = 0
    tab = True
    show_change_link = True
    fields = ("type_bloc", "titre", "modifier", "position")
    readonly_fields = ("modifier",)
    ordering = ("position",)
    # Unfold repete le libelle complet du type au-dessus de chaque ligne, alors
    # que la ligne le porte deja dans son select. On masque ce titre ; le lien
    # d'edition, qu'Unfold y loge et ne montre qu'au survol, est remplace par la
    # colonne « modifier » ci-dessous, visible en permanence.
    # / Unfold repeats the full type label above each row, which the row's own
    # select already carries. We hide that title; the edit link Unfold puts
    # there and only reveals on hover is replaced by the always-visible
    # "modifier" column below.
    hide_title = True
    # Tri par glisser-deposer (sortable Unfold) : la poignee remplace la saisie
    # manuelle du nombre, le champ position est masque.
    # / Drag-and-drop sorting (Unfold sortable): the handle replaces manual
    # number input, the position field is hidden.
    ordering_field = "position"
    hide_ordering_field = True

    @display(description=_("Contenu"))
    def modifier(self, obj):
        """
        Lien vers la fiche du bloc, ou se saisit son contenu.
        / Link to the block form, where its content is typed.

        Une ligne pas encore enregistree n'a pas de fiche : on invite alors a
        enregistrer d'abord. / A row not saved yet has no form: we then invite
        the user to save first.
        """
        if obj is None or obj._state.adding:
            return _("Enregistrer d'abord")
        url = reverse("staff_admin:pages_bloc_change", args=[obj.pk])
        return format_html(
            '<a href="{}" class="text-primary-600">✎ {}</a>', url, _("modifier")
        )

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


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
    Admin d'une Page : ses metadonnees, et le sommaire de ses blocs en onglet.
    / Page admin: its metadata, plus the summary of its blocks in a tab.
    """

    compressed_fields = True
    warn_unsaved_form = True

    # Sommaire des blocs de la page, dans un onglet.
    # / Summary of the page's blocks, in a tab.
    inlines = [BlocInline]

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

    def save_formset(self, request, form, formset, change):
        """
        Place les blocs AJOUTES depuis l'onglet en fin de page.
        / Appends blocks ADDED from the tab at the end of the page.

        Le glisser-deposer d'Unfold n'ecrit les positions qu'apres un
        deplacement : une ligne fraichement ajoutee arriverait sinon en
        position 0, donc en tete de page.
        / Unfold's drag-and-drop only writes positions after a move: a freshly
        added row would otherwise land at position 0, i.e. at the top.

        On ne touche QUE les lignes neuves (`_state.adding`). Le tri d'Unfold
        renumerote les blocs existants A PARTIR DE ZERO : traiter la position 0
        comme « non renseignee » renverrait en fin de page le bloc que l'on
        vient justement de glisser en tete.
        `_state.adding` et non `pk` : la cle primaire est un UUID avec
        default=uuid4, donc toujours renseignee, meme sur un objet neuf.
        / We only touch NEW rows (`_state.adding`). Unfold's sorter renumbers
        existing blocks FROM ZERO: treating position 0 as "unset" would send the
        block just dragged to the top back to the bottom. `_state.adding`, not
        `pk`: the primary key is a UUID with default=uuid4, hence always set.
        """
        if formset.model is not Bloc:
            return super().save_formset(request, form, formset, change)

        blocs = formset.save(commit=False)
        derniere_position = (
            Bloc.objects.filter(page=form.instance).aggregate(maxi=Max("position"))["maxi"] or 0
        )
        for bloc in blocs:
            if bloc._state.adding and not bloc.position:
                derniere_position += 1
                bloc.position = derniere_position
            bloc.save()
        for bloc_supprime in formset.deleted_objects:
            bloc_supprime.delete()
        formset.save_m2m()

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
        )}
        js = (
            "pages/vendor/easymde/easymde.min.js",
            "pages/admin/editeur_markdown.js",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Bloc TEXTE existant : la source Markdown est dans instance.texte.
        # `_state.adding` et non `pk` : la cle primaire est un UUID avec
        # default=uuid4, donc `pk` est TOUJOURS renseigne, meme sur un objet
        # jamais enregistre. / Existing TEXTE block: the Markdown source lives
        # in instance.texte. `_state.adding`, not `pk`: the primary key is a
        # UUID with default=uuid4, so `pk` is ALWAYS set, even on a new object.
        if not self.instance._state.adding and self.instance.type_bloc == Bloc.TEXTE:
            self.fields["texte_markdown"].initial = self.instance.texte
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


@admin.register(Bloc, site=staff_admin_site)
class BlocAdmin(ModelAdmin):
    """
    Fiche complete d'un Bloc. Les champs visibles dependent de type_bloc, pilotes
    par conditional_fields NATIF d'Unfold (expressions Alpine.js evaluees cote
    navigateur). type_bloc est un select : Unfold l'expose dans le scope Alpine,
    donc les expressions du type "type_bloc == 'SECTION' && affichage == 'CARTE'"
    fonctionnent sans aucun JavaScript maison.
    / Full Bloc form. Visible fields depend on type_bloc, driven by Unfold's NATIVE
    conditional_fields (Alpine.js expressions). type_bloc is a select exposed in the
    Alpine scope, so "type_bloc == 'SECTION' && affichage == 'CARTE'" works with
    no custom JS.

    On arrive ici depuis l'onglet « Blocs » de la page (lien « modifier » d'une
    ligne), ou depuis la liste des blocs. Premiere action a la creation :
    choisir le TYPE DE BLOC -> les champs correspondants se deroulent. La Page
    d'appartenance est un simple SELECT. L'ordre d'affichage des blocs sur la
    page se regle par glisser-deposer, ici ou dans l'onglet de la page.
    / Reached from the page's "Blocks" tab (a row's "edit" link), or from the
    block list. First action on creation: choose the BLOCK TYPE -> matching
    fields unfold. The owning Page is a plain SELECT. The display order is set
    by drag-and-drop, here or in the page's tab.
    """

    compressed_fields = True
    warn_unsaved_form = True
    form = BlocAdminForm
    # Notes d'aide affichees au-dessus du formulaire, chacune visible pour un
    # type ou un couple (type, affichage) donne — via Alpine, meme mecanisme
    # que conditional_fields.
    # / Help notes shown above the form, each revealed for a given type or
    # (type, affichage) pair — via Alpine, same mechanism as conditional_fields.
    change_form_before_template = "admin/pages/bloc/hero_aide_before.html"
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
    fields = ("type_bloc", "page") + _CHAMPS_DU_CATALOGUE

    # Expressions Alpine.js evaluees cote navigateur par conditional_fields
    # (natif Unfold) : un champ n'apparait que pour les types qui l'utilisent.
    # / Alpine.js expressions evaluated browser-side by Unfold's native
    # conditional_fields: a field only shows for the types that use it.
    conditional_fields = _visibilite_des_champs()

    def save_model(self, request, obj, form, change):
        # Nettoie le HTML du champ texte (WYSIWYG) avant enregistrement.
        # EXCEPTION bloc TEXTE : `texte` est de la SOURCE Markdown, pas du
        # HTML — clean_html la mutilerait (autoliens <https://…>, exemples de
        # code contenant des balises). La sécurité est assurée AU RENDU par le
        # filtre rendre_markdown (markdown puis nh3.clean sur le HTML produit).
        # / Sanitize the WYSIWYG text field HTML before saving. EXCEPTION for
        # the TEXTE block: `texte` is Markdown SOURCE, not HTML — clean_html
        # would mangle it (<https://…> autolinks, code samples with tags).
        # Safety is enforced AT RENDER TIME by the rendre_markdown filter.
        if obj.type_bloc == Bloc.TEXTE:
            sanitize_textfields(obj)
            # La source Markdown vient du champ de formulaire dedie (editeur
            # EasyMDE), posee APRES sanitize pour ne pas etre mutilee.
            # / The Markdown source comes from the dedicated form field
            # (EasyMDE editor), set AFTER sanitize so it is not mangled.
            obj.texte = form.cleaned_data.get("texte_markdown", "")
        else:
            sanitize_textfields(obj)

        # Sécurité : neutralise les URLs à schéma dangereux (javascript:, data:,
        # vbscript:) dans les champs lien, qui pourraient produire un XSS au clic.
        # / Security: neutralize dangerous-scheme URLs (javascript:, data:, vbscript:)
        # in link fields, which could trigger an XSS on click.
        for champ_url in ("bouton_url", "bouton2_url", "embed_url"):
            valeur = getattr(obj, champ_url, "")
            if url_a_schema_dangereux(valeur):
                setattr(obj, champ_url, "")

        # A la creation, si aucune position n'est saisie, on place le bloc en fin
        # de page (max + 1) pour qu'il s'ajoute naturellement a la suite.
        # / On creation, if no position is set, append the block at the end of the
        # page (max + 1) so it naturally adds after the others.
        if not change and not obj.position and obj.page_id:
            derniere_position = Bloc.objects.filter(page=obj.page).aggregate(
                maxi=Max("position")
            )["maxi"] or 0
            obj.position = derniere_position + 1

        super().save_model(request, obj, form, change)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)
