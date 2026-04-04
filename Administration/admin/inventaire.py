"""
Admin Unfold pour la gestion de stock (inventaire).
/ Unfold admin for stock management (inventory).

LOCALISATION : Administration/admin/inventaire.py

Les mouvements de stock peuvent être créés depuis l'admin (réception,
ajustement, perte, offert). Les types VENTE et DÉBIT MÈTRE sont exclus
car ils sont créés automatiquement (POS et capteur Pi).
La sauvegarde passe par StockService pour garantir l'update atomique
du stock et la cohérence du champ quantite_avant.
"""

import logging

from django.contrib import admin
from django.http import HttpRequest
from django.urls import path
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display

from Administration.admin.site import staff_admin_site
from ApiBillet.permissions import TenantAdminPermissionWithRequest
from inventaire.models import Stock, MouvementStock, TypeMouvement

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers au niveau du module (Unfold wrappe les méthodes de classe)
# Module-level helpers (Unfold wraps class methods)
# ---------------------------------------------------------------------------


def _formater_quantite_lisible(quantite, unite):
    """
    Convertit une quantité en unité de base vers un affichage lisible.
    / Converts a base-unit quantity to human-readable display.

    CL : >= 100 → litres (ex: "1.5 L"), sinon centilitres (ex: "50 cl")
    GR : >= 1000 → kilogrammes (ex: "1.5 kg"), sinon grammes (ex: "800 g")
    UN : entier brut (ex: "3")
    """
    if unite == "CL":
        if abs(quantite) >= 100:
            return f"{quantite / 100:.1f} L"
        return f"{quantite} cl"
    if unite == "GR":
        if abs(quantite) >= 1000:
            return f"{quantite / 1000:.1f} kg"
        return f"{quantite} g"
    # UN ou autre
    return str(quantite)


# Couleurs de badge Unfold par type de mouvement.
# Les clés sont les codes courts (VE, RE...) retournés comme premier élément du tuple.
# Unfold @display(label=) attend un tuple (clé, texte_affiché).
# / Unfold badge colors per movement type.
# Keys are short codes returned as first element of the tuple.
LABELS_TYPE_MOUVEMENT = {
    TypeMouvement.VE: "danger",
    TypeMouvement.RE: "success",
    TypeMouvement.AJ: "warning",
    TypeMouvement.OF: "info",
    TypeMouvement.PE: "danger",
    TypeMouvement.DM: "primary",
}


# ---------------------------------------------------------------------------
# Inline Stock pour POSProductAdmin
# / Stock inline for POSProductAdmin
# ---------------------------------------------------------------------------


class StockInline(TabularInline):
    model = Stock
    extra = 0
    max_num = 1
    fields = ("quantite", "unite", "seuil_alerte", "autoriser_vente_hors_stock")
    readonly_fields = ("quantite",)

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        field = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == "quantite" and field is not None:
            field.help_text = _(
                "Read-only. To add stock, go to Inventory > Stock movements > Add."
            )
        return field

    def has_view_permission(self, request: HttpRequest, obj=None) -> bool:
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request: HttpRequest, obj=None) -> bool:
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        return TenantAdminPermissionWithRequest(request)


# ---------------------------------------------------------------------------
# Admin Stock — liste et modification du seuil d'alerte / vente hors stock.
# Article, quantité et unité sont en lecture seule (modifiés par les mouvements).
# Aussi utilisé pour l'autocomplete dans MouvementStockAdmin.
# / Stock admin — list and edit alert threshold / out-of-stock sales flag.
# Article, quantity and unit are read-only (modified by movements).
# Also used for autocomplete in MouvementStockAdmin.
# ---------------------------------------------------------------------------


@display(description=_("Article"), ordering="product__name")
def display_stock_article(obj):
    return obj.product.name


@display(description=_("Quantité"))
def display_stock_quantite(obj):
    return _formater_quantite_lisible(obj.quantite, obj.unite)


@display(description=_("Unité"))
def display_stock_unite(obj):
    return obj.get_unite_display()


@admin.register(Stock, site=staff_admin_site)
class StockAdmin(ModelAdmin):
    """
    Admin des stocks produits.
    L'article, la quantité et l'unité sont en lecture seule.
    Le seuil d'alerte et le flag de vente hors stock sont modifiables.
    / Product stock admin.
    Article, quantity and unit are read-only.
    Alert threshold and out-of-stock flag are editable.

    LOCALISATION : Administration/admin/inventaire.py
    """

    compressed_fields = True
    warn_unsaved_form = True
    list_before_template = "admin/inventaire/stock_list_before.html"

    search_fields = ["product__name"]
    autocomplete_fields = ["product"]

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "product":
            from BaseBillet.models import Product

            # Uniquement les articles de vente (VT) — pas les recharges,
            # adhésions, consignes, etc. qui n'ont pas de stock physique.
            # / Only sale articles (VT) — not top-ups, memberships,
            # deposits, etc. which have no physical stock.
            kwargs["queryset"] = Product.objects.filter(methode_caisse=Product.VENTE)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_form(self, request, obj=None, **kwargs):
        # Retirer le lien "+" (ajout produit) du widget autocomplete.
        # autocomplete_fields recrée le widget après formfield_for_foreignkey,
        # donc can_add_related doit être mis ici, sur la form finale.
        # / Remove "+" (add product) link from autocomplete widget.
        form = super().get_form(request, obj, **kwargs)
        if "product" in form.base_fields:
            form.base_fields["product"].widget.can_add_related = False
            form.base_fields["product"].widget.can_change_related = False
        return form

    list_display = [
        display_stock_article,
        display_stock_quantite,
        display_stock_unite,
        "seuil_alerte",
        "autoriser_vente_hors_stock",
    ]
    list_editable = ["seuil_alerte", "autoriser_vente_hors_stock"]
    list_display_links = [display_stock_article]

    fields = [
        "product",
        "quantite",
        "unite",
        "seuil_alerte",
        "autoriser_vente_hors_stock",
    ]

    def get_readonly_fields(self, request, obj=None):
        # En mode change : article, quantité et unité sont en lecture seule
        # (la quantité se modifie via les actions stock, pas en éditant le champ)
        # En mode add : tout est éditable
        # / In change mode: article, quantity and unit are read-only
        # In add mode: everything is editable
        if obj is not None:
            return ["product", "quantite", "unite"]
        return []

    change_form_after_template = "admin/inventaire/stock_actions.html"
    add_form_template = "admin/inventaire/stock_add_help.html"

    def save_model(self, request, obj, form, change):
        """
        À la création d'un stock, crée automatiquement un mouvement de type
        réception pour tracer l'entrée initiale dans le journal.
        / On stock creation, automatically creates a reception movement
        to trace the initial entry in the movement log.
        """
        super().save_model(request, obj, form, change)

        # Uniquement à la création (pas à la modification)
        # / Only on creation (not on change)
        if not change and obj.quantite > 0:
            from inventaire.services import StockService

            StockService.creer_mouvement(
                stock=obj,
                type_mouvement=TypeMouvement.RE,
                quantite=obj.quantite,
                motif=_("Stock initial"),
                utilisateur=request.user,
            )

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        """
        Injecte le contexte pour le template after (actions stock).
        / Injects context for the after template (stock actions).
        """
        extra_context = extra_context or {}
        if object_id:
            from django.shortcuts import get_object_or_404

            stock = get_object_or_404(Stock, pk=object_id)
            derniers_mouvements = (
                MouvementStock.objects.filter(stock=stock)
                .exclude(type_mouvement__in=TYPES_AUTOMATIQUES)
                .select_related("cree_par")
                .order_by("-cree_le")[:5]
            )
            extra_context["stock"] = stock
            extra_context["product_name"] = stock.product.name
            extra_context["derniers_mouvements"] = derniers_mouvements
            extra_context["stock_action_url"] = (
                f"/admin/inventaire/stock/{object_id}/action/"
            )
        return super().changeform_view(request, object_id, form_url, extra_context)

    def get_urls(self):
        """
        Ajoute l'URL pour les actions manuelles de stock (HTMX partial).
        / Adds the URL for manual stock actions (HTMX partial).
        """
        from inventaire.views import stock_action_view

        custom_urls = [
            path(
                "<uuid:stock_uuid>/action/",
                self.admin_site.admin_view(stock_action_view),
                name="inventaire_stock_action",
            ),
        ]
        return custom_urls + super().get_urls()

    def has_module_permission(self, request):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return False


# ---------------------------------------------------------------------------
# Admin des mouvements de stock
# / Stock movements admin
# ---------------------------------------------------------------------------

# Fonctions d'affichage au niveau du module / Module-level display functions


@display(description=_("Date"), ordering="cree_le")
def display_cree_le(obj):
    return obj.cree_le


@display(description=_("Produit / Product"), ordering="stock__product__name")
def display_produit(obj):
    return obj.stock.product.name


@display(
    description=_("Type"),
    ordering="type_mouvement",
    label=LABELS_TYPE_MOUVEMENT,
)
def display_type_mouvement(obj):
    # Tuple (clé, texte) : la clé matche le dict LABELS_TYPE_MOUVEMENT,
    # le texte est le label complet affiché dans le badge.
    # / Tuple (key, text): key matches LABELS_TYPE_MOUVEMENT dict,
    # text is the full label displayed in the badge.
    return obj.type_mouvement, obj.get_type_mouvement_display()


@display(description=_("Quantité / Quantity"))
def display_quantite(obj):
    signe = "+" if obj.quantite >= 0 else ""
    return f"{signe}{_formater_quantite_lisible(obj.quantite, obj.stock.unite)}"


@display(description=_("Stock après / Stock after"))
def display_stock_apres(obj):
    stock_apres = obj.quantite_avant + obj.quantite
    return _formater_quantite_lisible(stock_apres, obj.stock.unite)


@display(description=_("Motif / Reason"))
def display_motif(obj):
    return obj.motif or "—"


@display(description=_("Auteur / Author"))
def display_auteur(obj):
    if obj.cree_par:
        return str(obj.cree_par)
    return _("Système / System")


# ---------------------------------------------------------------------------
# Filtre par type de mouvement avec défaut sur les types manuels
# Par défaut, on masque les types automatiques (VE, DM) pour ne montrer
# que les mouvements saisis manuellement.
# / Movement type filter with manual types as default.
# By default, auto types (VE, DM) are hidden.
# ---------------------------------------------------------------------------

# Types automatiques à masquer par défaut dans la liste
# / Auto types to hide by default in the list
TYPES_AUTOMATIQUES = [TypeMouvement.VE, TypeMouvement.DM]


class TypeMouvementFilter(admin.SimpleListFilter):
    title = _("Type de mouvement")
    parameter_name = "type_mvt"

    def lookups(self, request, model_admin):
        return [
            ("manuels", _("Manuels uniquement")),
            ("all", _("Tout afficher")),
            (TypeMouvement.RE, TypeMouvement.RE.label),
            (TypeMouvement.AJ, TypeMouvement.AJ.label),
            (TypeMouvement.OF, TypeMouvement.OF.label),
            (TypeMouvement.PE, TypeMouvement.PE.label),
            (TypeMouvement.DM, TypeMouvement.DM.label),
            (TypeMouvement.VE, TypeMouvement.VE.label),
        ]

    def queryset(self, request, queryset):
        value = self.value()

        # Par défaut : masquer les types automatiques (vente, débit mètre)
        # / Default: hide auto types (sale, meter debit)
        if value is None or value == "manuels":
            return queryset.exclude(type_mouvement__in=TYPES_AUTOMATIQUES)

        # Tout afficher
        # / Show everything
        if value == "all":
            return queryset

        # Filtre sur un type spécifique
        # / Filter on a specific type
        return queryset.filter(type_mouvement=value)


@admin.register(MouvementStock, site=staff_admin_site)
class MouvementStockAdmin(ModelAdmin):
    """
    Admin des mouvements de stock — lecture seule.
    L'ajout se fait via le formulaire HTMX sur la fiche Stock.
    / Stock movements admin — read-only.
    Adding is done via the HTMX form on the Stock detail page.

    LOCALISATION : Administration/admin/inventaire.py
    """

    compressed_fields = True
    warn_unsaved_form = True
    list_before_template = "admin/inventaire/mouvements_list_before.html"

    list_display = [
        display_cree_le,
        display_produit,
        display_type_mouvement,
        display_quantite,
        display_stock_apres,
        display_motif,
        display_auteur,
    ]

    list_filter = [TypeMouvementFilter, "cree_le"]
    search_fields = ["stock__product__name", "motif"]
    ordering = ["-cree_le"]

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "stock",
                    "type_mouvement",
                    "quantite",
                    "quantite_avant",
                    "motif",
                    "ligne_article",
                    "cloture",
                    "cree_par",
                    "cree_le",
                ),
            },
        ),
    )

    readonly_fields = [
        "stock",
        "type_mouvement",
        "quantite",
        "quantite_avant",
        "motif",
        "ligne_article",
        "cloture",
        "cree_par",
        "cree_le",
    ]

    def has_add_permission(self, request: HttpRequest) -> bool:
        # L'ajout se fait via le formulaire HTMX sur la fiche Stock
        # / Adding is done via the HTMX form on the Stock detail page
        return False

    def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        return False

    def has_view_permission(self, request: HttpRequest, obj=None) -> bool:
        return TenantAdminPermissionWithRequest(request)
