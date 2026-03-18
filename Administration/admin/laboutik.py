import logging

from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, TabularInline

from Administration.admin.site import staff_admin_site
from ApiBillet.permissions import TenantAdminPermissionWithRequest
from laboutik.models import (
    PointDeVente, CartePrimaire, CategorieTable, Table,
    CommandeSauvegarde, ArticleCommandeSauvegarde,
    ClotureCaisse,
)

logger = logging.getLogger(__name__)


@admin.register(PointDeVente, site=staff_admin_site)
class PointDeVenteAdmin(ModelAdmin):
    """Admin pour les points de vente.
    Admin for points of sale.
    LOCALISATION : Administration/admin/laboutik.py"""
    compressed_fields = True
    warn_unsaved_form = True

    list_display = ('name', 'comportement', 'service_direct', 'hidden')
    list_filter = ['comportement', 'hidden']
    search_fields = ['name']
    ordering = ('poid_liste', 'name')
    filter_horizontal = ('products', 'categories')

    fieldsets = (
        (_('General'), {
            'fields': (
                'name',
                'icon',
                'comportement',
                'poid_liste',
                'hidden',
            ),
        }),
        (_('Options'), {
            'fields': (
                'service_direct',
                'afficher_les_prix',
                'accepte_especes',
                'accepte_carte_bancaire',
                'accepte_cheque',
                'accepte_commandes',
            ),
        }),
        (_('Products & categories'), {
            'fields': (
                'products',
                'categories',
            ),
        }),
    )

    def has_add_permission(self, request):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


@admin.register(CartePrimaire, site=staff_admin_site)
class CartePrimaireAdmin(ModelAdmin):
    """Admin pour les cartes primaires (operateurs de caisse).
    Admin for primary cards (POS operators).
    LOCALISATION : Administration/admin/laboutik.py"""
    compressed_fields = True
    warn_unsaved_form = True

    list_display = ('carte', 'edit_mode', 'datetime')
    list_filter = ['edit_mode']
    search_fields = ['carte__tag_id', 'carte__number']
    filter_horizontal = ('points_de_vente',)

    fieldsets = (
        (None, {
            'fields': (
                'carte',
                'edit_mode',
                'points_de_vente',
            ),
        }),
    )

    def has_add_permission(self, request):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


@admin.register(CategorieTable, site=staff_admin_site)
class CategorieTableAdmin(ModelAdmin):
    """Admin minimal pour les categories de table (Phase 4 = restaurant).
    Minimal admin for table categories (Phase 4 = restaurant).
    LOCALISATION : Administration/admin/laboutik.py"""
    list_display = ('name', 'icon')
    search_fields = ['name']

    def has_add_permission(self, request):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


@admin.register(Table, site=staff_admin_site)
class TableAdmin(ModelAdmin):
    """Admin minimal pour les tables de restaurant (Phase 4 = restaurant).
    Minimal admin for restaurant tables (Phase 4 = restaurant).
    LOCALISATION : Administration/admin/laboutik.py"""
    list_display = ('name', 'categorie', 'statut', 'ephemere', 'archive')
    list_filter = ['statut', 'categorie', 'archive']
    search_fields = ['name']
    ordering = ('poids', 'name')

    def has_add_permission(self, request):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


# --- Commandes de restaurant (Phase 4) ---
# --- Restaurant orders (Phase 4) ---

class ArticleCommandeSauvegardeInline(TabularInline):
    """Inline lecture seule pour les articles d'une commande.
    Read-only inline for order articles.
    LOCALISATION : Administration/admin/laboutik.py"""
    model = ArticleCommandeSauvegarde
    extra = 0
    fields = ('product', 'price', 'qty', 'reste_a_payer', 'reste_a_servir', 'statut')
    readonly_fields = ('product', 'price', 'qty', 'reste_a_payer', 'reste_a_servir', 'statut')

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CommandeSauvegarde, site=staff_admin_site)
class CommandeSauvegardeAdmin(ModelAdmin):
    """Admin lecture seule pour l'historique des commandes de restaurant.
    Read-only admin for restaurant order history.
    LOCALISATION : Administration/admin/laboutik.py"""
    list_display = ('uuid', 'table', 'statut', 'responsable', 'datetime', 'archive')
    list_filter = ['statut', 'archive']
    search_fields = ['uuid', 'commentaire']
    ordering = ('-datetime',)
    readonly_fields = (
        'uuid', 'service', 'responsable', 'table', 'datetime',
        'statut', 'commentaire', 'archive',
    )
    inlines = [ArticleCommandeSauvegardeInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


# --- Cloture de caisse (Phase 5) ---
# --- Cash register closure (Phase 5) ---

@admin.register(ClotureCaisse, site=staff_admin_site)
class ClotureCaisseAdmin(ModelAdmin):
    """Admin lecture seule pour les clotures de caisse.
    Read-only admin for cash register closures.
    LOCALISATION : Administration/admin/laboutik.py"""
    list_display = ('point_de_vente', 'responsable', 'datetime_cloture', 'total_general', 'nombre_transactions')
    list_filter = ['point_de_vente']
    search_fields = ['point_de_vente__name', 'responsable__email']
    ordering = ('-datetime_cloture',)
    readonly_fields = (
        'uuid', 'point_de_vente', 'responsable',
        'datetime_ouverture', 'datetime_cloture',
        'total_especes', 'total_carte_bancaire', 'total_cashless',
        'total_general', 'nombre_transactions', 'rapport_json',
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)
