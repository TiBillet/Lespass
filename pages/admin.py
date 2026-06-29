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
from unfold.admin import ModelAdmin
from unfold.contrib.forms.widgets import WysiwygWidget
from unfold.decorators import display

from Administration.admin.site import sanitize_textfields, staff_admin_site
from ApiBillet.permissions import TenantAdminPermissionWithRequest
from pages.models import Bloc, ConfigurationSite, Page


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
        "display_publie",
        "display_accueil",
        "position",
        "nb_blocs",
        "display_voir",
        "updated_at",
    ]
    list_filter = ["publie", "est_accueil"]
    search_fields = ["titre", "slug"]
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
                    ("publie", "est_accueil"),
                    "meta_description",
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


class BlocAdminForm(forms.ModelForm):
    """Formulaire du Bloc : editeur WYSIWYG sur le champ texte.
    / Bloc form: WYSIWYG editor on the text field."""

    class Meta:
        model = Bloc
        fields = "__all__"
        widgets = {
            "texte": WysiwygWidget,
        }


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

    # Liste : on peut reordonner via "position" (editable en ligne), filtrer par page.
    # / List: reorder via "position" (inline editable), filter by page.
    list_display = ["__str__", "page", "type_bloc", "position"]
    list_editable = ["position"]
    list_filter = ["page", "type_bloc"]
    list_select_related = ["page"]
    search_fields = ["titre", "texte"]
    ordering = ["page", "position"]

    fields = (
        "type_bloc",
        "page",
        "position",
        "surtitre",
        "titre",
        "sous_titre",
        "texte",
        "image",
        "image_secondaire",
        "video",
        "points_gps",
        "contenu",
        "image_position",
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
        "titre": "['HERO','PARAGRAPHE','IMAGE_TEXTE','CTA','VIDEO_TEXTE','CARTE','IMAGE','CARTE_LEAFLET','FAQ'].includes(type_bloc)",
        "sous_titre": "['HERO','CTA'].includes(type_bloc)",
        "texte": "['PARAGRAPHE','IMAGE_TEXTE','CTA','TEMOIGNAGE','VIDEO_TEXTE','CARTE','FAQ'].includes(type_bloc)",
        "image": "['HERO','IMAGE_TEXTE','CARTE','IMAGE','CARTE_LEAFLET'].includes(type_bloc)",
        "image_secondaire": "['HERO','CARTE_LEAFLET'].includes(type_bloc)",
        "video": "type_bloc == 'VIDEO_TEXTE'",
        "points_gps": "type_bloc == 'CARTE_LEAFLET'",
        "contenu": "type_bloc == 'INFOS'",
        "image_position": "type_bloc == 'IMAGE_TEXTE'",
        "badge": "['CARTE','CARTE_LEAFLET'].includes(type_bloc)",
        "bouton_label": "['HERO','IMAGE_TEXTE','CTA','CARTE'].includes(type_bloc)",
        "bouton_url": "['HERO','IMAGE_TEXTE','CTA','CARTE'].includes(type_bloc)",
        "bouton2_label": "['HERO','CTA'].includes(type_bloc)",
        "bouton2_url": "['HERO','CTA'].includes(type_bloc)",
        "auteur_nom": "type_bloc == 'TEMOIGNAGE'",
        "auteur_role": "type_bloc == 'TEMOIGNAGE'",
        "auteur_photo": "type_bloc == 'TEMOIGNAGE'",
    }

    def save_model(self, request, obj, form, change):
        # Nettoie le HTML du champ texte (WYSIWYG) avant enregistrement.
        # / Sanitize the WYSIWYG text field HTML before saving.
        sanitize_textfields(obj)

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
