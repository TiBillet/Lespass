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

UX D'EDITION (approche INVERSEE) :
- On edite les BLOCS directement (BlocAdmin = objet principal, dans la sidebar).
- Premiere action dans la fiche d'un bloc : choisir le TYPE -> les champs
  correspondants se deroulent (conditional_fields NATIF d'Unfold / Alpine.js,
  aucun JavaScript maison).
- La Page d'appartenance est un SELECT dans la fiche du bloc, avec les boutons
  "+" / modifier a cote (creer/ouvrir une page sans quitter le bloc).
- L'ordre d'affichage des blocs sur la page = champ "position".
- PageAdmin ne gere plus que les metadonnees de la page (titre, slug, accueil...).
/ EDITING UX (INVERTED approach):
- Blocks are edited directly (BlocAdmin = main object, in the sidebar).
- First action in a block form: choose the TYPE -> matching fields unfold
  (Unfold's NATIVE conditional_fields / Alpine.js, no custom JavaScript).
- The owning Page is a SELECT in the block form, with the "+" / edit buttons next
  to it (create/open a page without leaving the block).
- The block display order = "position" field.
- PageAdmin now only manages page metadata (title, slug, home...).
"""

from django import forms
from django.contrib import admin
from django.db.models import Count, Max
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

from Administration.admin.site import sanitize_textfields, staff_admin_site
from Administration.utils import url_a_schema_dangereux
from ApiBillet.permissions import TenantAdminPermissionWithRequest
from pages.models import Bloc, ConfigurationSite, ImageGalerie, Page


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
    Admin d'une Page : metadonnees uniquement (titre, slug, publication, accueil).
    Les blocs ne s'editent PLUS ici : on les edite cote Bloc (approche inversee),
    en selectionnant la page depuis le formulaire du bloc.
    / Page admin: metadata only (title, slug, publication, home). Blocks are no
    longer edited here: they are edited from the Bloc side (inverted approach),
    by selecting the page from the block form.
    """

    compressed_fields = True
    warn_unsaved_form = True

    # Remplit le slug depuis le titre (modifiable ensuite).
    # / Fills the slug from the title (editable afterwards).
    prepopulated_fields = {"slug": ("titre",)}

    list_display = [
        "titre",
        "slug",
        "parent",
        "display_publie",
        "display_accueil",
        "nb_blocs",
        "display_voir",
        "updated_at",
    ]
    # Tri par GLISSER-DÉPOSER (sortable Unfold, comme les blocs) : la poignée
    # remplace la colonne position ; l'ordre enregistré pilote la navbar.
    # / DRAG-AND-DROP sorting (Unfold sortable, like the blocks): the handle
    # replaces the position column; the saved order drives the navbar.
    ordering_field = "position"
    hide_ordering_field = True
    list_filter = ["publie", "est_accueil", "parent"]
    search_fields = ["titre", "slug"]
    list_select_related = ["parent"]
    ordering = ["position", "titre"]

    def get_queryset(self, request):
        # Annote le nombre de blocs pour l'afficher sans requete par ligne (N+1).
        # / Annotate the block count to display it without a per-row query (N+1).
        return super().get_queryset(request).annotate(_nb_blocs=Count("blocs"))

    fieldsets = (
        (
            _("Page"),
            {
                "fields": (
                    "titre",
                    "slug",
                    "position",
                    ("publie", "est_accueil", "est_blog"),
                    "parent",
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

    @display(description=_("Publiee"), boolean=True)
    def display_publie(self, obj):
        return obj.publie

    @display(description=_("Accueil"), boolean=True)
    def display_accueil(self, obj):
        return obj.est_accueil

    @display(description=_("Blocs"))
    def nb_blocs(self, obj):
        # Nombre de blocs de la page (annote dans get_queryset).
        # / Number of blocks on the page (annotated in get_queryset).
        return getattr(obj, "_nb_blocs", obj.blocs.count())

    @display(description=_("Voir"))
    def display_voir(self, obj):
        # Lien direct vers la page publique (accueil -> /, sinon /<slug>/).
        # / Direct link to the public page (home -> /, otherwise /<slug>/).
        if not obj.publie:
            return "—"
        url = "/" if obj.est_accueil else f"/{obj.slug}/"
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
    """Images d'un bloc GALERIE, éditées en ligne dans la fiche du bloc.
    / Images of a GALERIE block, edited inline in the block form."""

    model = ImageGalerie
    extra = 1
    fields = ("image", "legende", "position")
    ordering = ("position",)
    # Tri par glisser-déposer (sortable Unfold) : la poignée remplace la
    # saisie manuelle du nombre, le champ position est masqué.
    # / Drag-and-drop sorting (Unfold sortable): the handle replaces manual
    # number input, the position field is hidden.
    ordering_field = "position"
    hide_ordering_field = True


class BlocAdminForm(forms.ModelForm):
    """Formulaire du Bloc : editeur WYSIWYG sur le champ texte, et editeur
    MARKDOWN (EasyMDE, vendorise) sur le champ de formulaire texte_markdown.

    POURQUOI DEUX CHAMPS pour un seul champ modele (texte) : le WYSIWYG Trix
    produit du HTML — taper de la source Markdown dedans est penible et la
    mutile. Le bloc MARKDOWN a donc SON champ de formulaire (texte_markdown,
    affiche uniquement pour ce type via conditional_fields), edite avec
    EasyMDE (barre d'outils + apercu), et recopie dans obj.texte a la
    sauvegarde (save_model).
    / Bloc form: WYSIWYG editor on the text field, and a MARKDOWN editor
    (vendored EasyMDE) on the texte_markdown form field. WHY TWO form fields
    for one model field: Trix produces HTML — typing Markdown source in it is
    painful. The MARKDOWN block gets its own form field (shown only for that
    type), edited with EasyMDE, copied into obj.texte on save."""

    # Source Markdown de l'article (bloc MARKDOWN uniquement). Champ de
    # FORMULAIRE : la valeur vit dans Bloc.texte.
    # / Article Markdown source (MARKDOWN block only). FORM field: the value
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
        # Bloc MARKDOWN existant : la source est dans instance.texte.
        # / Existing MARKDOWN block: the source lives in instance.texte.
        if self.instance.pk and self.instance.type_bloc == Bloc.MARKDOWN:
            self.fields["texte_markdown"].initial = self.instance.texte
        # Table position -> URL des images de l'inline, embarquée en
        # data-attribute : l'APERÇU EasyMDE (rendu côté navigateur) peut
        # ainsi résoudre les références ![légende](galerie:N) au lieu
        # d'afficher une image cassée.
        # / position -> URL table of the inline images, embedded as a data
        # attribute so the EasyMDE PREVIEW (browser-side rendering) can
        # resolve ![caption](galerie:N) references instead of showing a
        # broken image.
        if self.instance.pk:
            import json

            urls_galerie = {
                img.position: img.image.med.url
                for img in self.instance.images_galerie.all()
                if img.image
            }
            self.fields["texte_markdown"].widget.attrs["data-galerie"] = json.dumps(urls_galerie)


@admin.register(Bloc, site=staff_admin_site)
class BlocAdmin(ModelAdmin):
    """
    Fiche complete d'un Bloc. Les champs visibles dependent de type_bloc, pilotes
    par conditional_fields NATIF d'Unfold (expressions Alpine.js evaluees cote
    navigateur). type_bloc est un select : Unfold l'expose dans le scope Alpine,
    donc les expressions du type "['HERO','CTA'].includes(type_bloc)" fonctionnent
    sans aucun JavaScript maison.
    / Full Bloc form. Visible fields depend on type_bloc, driven by Unfold's NATIVE
    conditional_fields (Alpine.js expressions). type_bloc is a select exposed in the
    Alpine scope, so "['HERO','CTA'].includes(type_bloc)" works with no custom JS.

    APPROCHE INVERSEE : c'est le Bloc qu'on edite (objet principal du changeform).
    Premiere action : choisir le TYPE DE BLOC -> les champs correspondants se
    deroulent. La Page d'appartenance est un simple SELECT (avec les boutons
    "+" / modifier a cote, pour creer ou ouvrir une page sans quitter le bloc).
    L'ordre d'affichage des blocs sur la page est donne par le champ "position".
    / INVERTED APPROACH: the Bloc is the main edited object. First action: choose
    the BLOCK TYPE -> matching fields unfold. The owning Page is a plain SELECT
    (with the "+" / edit buttons next to it, to create or open a page without
    leaving the block). The display order is given by the "position" field.
    """

    compressed_fields = True
    warn_unsaved_form = True
    form = BlocAdminForm
    # Note d'aide affichee au-dessus du formulaire, visible uniquement quand le
    # type choisi est HERO (via Alpine, meme mecanisme que conditional_fields) :
    # elle explique que l'image de fond vient de la Configuration, pas du bloc.
    # / Help note above the form, shown only when the chosen type is HERO (via
    # Alpine, same mechanism as conditional_fields): explains that the background
    # image comes from the Configuration, not from the block.
    change_form_before_template = "admin/pages/bloc/hero_aide_before.html"
    # Images du bloc GALERIE (inline).
    # / GALERIE block images (inline).
    inlines = [ImageGalerieInline]

    def get_inlines(self, request, obj=None):
        """
        N'affiche l'inline « Images » QUE sur les blocs GALERIE et MARKDOWN.
        / Show the images inline ONLY on GALERIE and MARKDOWN blocks.

        LOCALISATION : pages/admin.py — BlocAdmin.get_inlines

        Avant, l'inline apparaissait sur TOUS les types de blocs (bruit dans
        le formulaire). À la CRÉATION (obj=None), le type n'est pas encore
        connu côté serveur : on masque l'inline, il apparaît après le premier
        enregistrement du bloc GALERIE (flux Django standard).
        / Before, the inline appeared on ALL block types (form noise). On
        CREATION (obj=None) the type is not yet known server-side: the inline
        is hidden and appears after the GALERIE block's first save.
        """
        if obj is not None and obj.type_bloc in (Bloc.GALERIE, Bloc.MARKDOWN):
            # GALERIE : les images SONT le contenu du bloc. MARKDOWN : les
            # images illustrent l'article et se referencent dans le texte via
            # ![legende](galerie:N) (N = position dans l'inline).
            # / GALERIE: the images ARE the block content. MARKDOWN: the
            # images illustrate the article, referenced in the text via
            # ![caption](galerie:N) (N = position in the inline).
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
    # - type_bloc : menu déroulant compact (16 types).
    # list_filter_submit : bouton « Filtrer » (une requête, pas une par clic).
    # / Unfold advanced filters (demo's "driverwithfilters" pattern):
    # autocomplete on page (the raw link list exploded with the blog), parent
    # page filter (all blocks of a page's sub-pages), compact dropdown for
    # the 16 types, and a submit button (one query, not one per click).
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
    fields = (
        "type_bloc",
        "page",
        "surtitre",
        "titre",
        "sous_titre",
        "texte",
        "texte_markdown",
        "image",
        "image_secondaire",
        "video",
        "points_gps",
        "contenu",
        "nombre_max",
        "repliable",
        "embed_url",
        "image_position",
        "affichage_image",
        "badge",
        "bouton_label",
        "bouton_url",
        "bouton2_label",
        "bouton2_url",
        "auteur_nom",
        "auteur_role",
        "auteur_photo",
    )

    # Visibilite des champs selon type_bloc (cf. matrice dans SPEC.md).
    # Expressions Alpine.js : == pour un type unique, .includes() pour plusieurs.
    # / Field visibility based on type_bloc (see matrix in SPEC.md).
    # Alpine.js expressions: == for a single type, .includes() for several.
    conditional_fields = {
        "surtitre": "type_bloc == 'CARTE'",
        "titre": "['HERO','PARAGRAPHE','IMAGE_TEXTE','CTA','VIDEO_TEXTE','CARTE','IMAGE','CARTE_LEAFLET','FAQ','EVENEMENTS','GALERIE','EMBED','MARKDOWN','LISTE_SOUS_PAGES'].includes(type_bloc)",
        "nombre_max": "['EVENEMENTS','LISTE_SOUS_PAGES'].includes(type_bloc)",
        "repliable": "type_bloc == 'FAQ'",
        "embed_url": "type_bloc == 'EMBED'",
        "sous_titre": "['HERO','CTA'].includes(type_bloc)",
        "texte": "['PARAGRAPHE','IMAGE_TEXTE','CTA','TEMOIGNAGE','VIDEO_TEXTE','CARTE','FAQ'].includes(type_bloc)",
        "texte_markdown": "type_bloc == 'MARKDOWN'",
        # HERO n'a plus de champ image : son fond est l'image generique du lieu
        # (Configuration.img), lue au rendu. / HERO has no image field anymore:
        # its background is the venue's generic image (Configuration.img).
        "image": "['IMAGE_TEXTE','CARTE','IMAGE','CARTE_LEAFLET'].includes(type_bloc)",
        "image_secondaire": "type_bloc == 'CARTE_LEAFLET'",
        "video": "type_bloc == 'VIDEO_TEXTE'",
        "points_gps": "type_bloc == 'CARTE_LEAFLET'",
        "contenu": "type_bloc == 'INFOS'",
        "image_position": "type_bloc == 'IMAGE_TEXTE'",
        "affichage_image": "type_bloc == 'IMAGE'",
        "badge": "['CARTE','CARTE_LEAFLET'].includes(type_bloc)",
        # HERO n'a plus de boutons : les actions vont dans un bloc CTA separe.
        # / HERO has no buttons anymore: actions go into a separate CTA block.
        "bouton_label": "['IMAGE_TEXTE','CTA','CARTE'].includes(type_bloc)",
        "bouton_url": "['IMAGE_TEXTE','CTA','CARTE'].includes(type_bloc)",
        "bouton2_label": "type_bloc == 'CTA'",
        "bouton2_url": "type_bloc == 'CTA'",
        "auteur_nom": "type_bloc == 'TEMOIGNAGE'",
        "auteur_role": "type_bloc == 'TEMOIGNAGE'",
        "auteur_photo": "type_bloc == 'TEMOIGNAGE'",
    }

    def save_model(self, request, obj, form, change):
        # Nettoie le HTML du champ texte (WYSIWYG) avant enregistrement.
        # EXCEPTION bloc MARKDOWN : `texte` est de la SOURCE Markdown, pas du
        # HTML — clean_html la mutilerait (autoliens <https://…>, exemples de
        # code contenant des balises). La sécurité est assurée AU RENDU par le
        # filtre rendre_markdown (markdown puis nh3.clean sur le HTML produit).
        # / Sanitize the WYSIWYG text field HTML before saving. EXCEPTION for
        # the MARKDOWN block: `texte` is Markdown SOURCE, not HTML — clean_html
        # would mangle it (<https://…> autolinks, code samples with tags).
        # Safety is enforced AT RENDER TIME by the rendre_markdown filter.
        if obj.type_bloc == Bloc.MARKDOWN:
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
