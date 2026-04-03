"""
Admin Unfold pour la gestion de stock (inventaire).
/ Unfold admin for stock management (inventory).

LOCALISATION : Administration/admin/inventaire.py
"""

import logging

from django.contrib import admin
from django.http import HttpRequest
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


# Couleurs de badge Unfold par type de mouvement
# / Unfold badge colors per movement type
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

    def has_view_permission(self, request: HttpRequest, obj=None) -> bool:
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request: HttpRequest, obj=None) -> bool:
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        return TenantAdminPermissionWithRequest(request)


# ---------------------------------------------------------------------------
# Admin lecture seule pour les mouvements de stock
# / Read-only admin for stock movements
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
    return obj.type_mouvement


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


@admin.register(MouvementStock, site=staff_admin_site)
class MouvementStockAdmin(ModelAdmin):
    """Admin lecture seule pour consulter l'historique des mouvements de stock.
    / Read-only admin to browse stock movement history."""

    compressed_fields = True
    warn_unsaved_form = True

    list_display = [
        display_cree_le,
        display_produit,
        display_type_mouvement,
        display_quantite,
        display_stock_apres,
        display_motif,
        display_auteur,
    ]

    list_filter = ["type_mouvement", "cree_le"]
    search_fields = ["stock__product__name", "motif"]
    ordering = ["-cree_le"]

    # Lecture seule — aucune modification possible / Read-only — no changes allowed
    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        return False

    def has_view_permission(self, request: HttpRequest, obj=None) -> bool:
        return TenantAdminPermissionWithRequest(request)
