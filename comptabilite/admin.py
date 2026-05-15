"""
Admin Unfold pour l'app comptabilite.
/ Unfold admin for the comptabilite app.

LOCALISATION : comptabilite/admin.py

S1 : admin liste minimaliste, read-only. ClotureCaisseAdmin sera enrichi en S3
avec change_form_before_template (rapport visuel) et en S4 avec les exports.

/ S1: minimal read-only list admin. ClotureCaisseAdmin will be enriched in S3
with change_form_before_template (visual report) and in S4 with exports.
"""
from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from unfold.admin import ModelAdmin

from Administration.admin.site import staff_admin_site
from ApiBillet.permissions import TenantAdminPermissionWithRequest

from comptabilite.models import ClotureCaisse


# Helpers d'affichage definis AU NIVEAU MODULE (pas methodes de classe).
# Unfold wrappe les methodes d'un ModelAdmin avec son systeme @action, ce qui
# peut causer des bugs sur des helpers internes. (cf. tests/PIEGES.md)
# / Display helpers defined AT MODULE LEVEL (not class methods). Unfold wraps
# ModelAdmin methods via @action which can break internal helpers.

def _format_euros(centimes: int) -> str:
    """
    Formate un montant en centimes en chaine euros lisible.
    / Format a cents amount as a readable euros string.
    """
    if centimes is None:
        return "—"
    return f"{centimes / 100:.2f} €"


@admin.register(ClotureCaisse, site=staff_admin_site)
class ClotureCaisseAdmin(ModelAdmin):
    """
    Admin read-only pour les clotures comptables.
    / Read-only admin for accounting closures.
    """

    list_display = (
        "datetime_fin",
        "niveau",
        "numero_sequentiel",
        "responsable",
        "ca_ttc",
        "nombre_transactions",
    )
    list_filter = ("niveau",)
    search_fields = ("responsable__email",)
    ordering = ("-datetime_fin",)

    # Aucun fieldset : l'edition est interdite, la vue detail sera surchargee en S3.
    # / No fieldset: editing forbidden, detail view will be overridden in S3.
    fieldsets = ()

    # --- Permissions : modele immuable ---
    # / Permissions: immutable model

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        # Creation uniquement via Celery ou management command.
        # / Creation only via Celery or management command.
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    # --- Colonnes d'affichage ---
    # / Display columns

    @admin.display(description=_("Total TTC"), ordering="total_general")
    def ca_ttc(self, obj):
        return _format_euros(obj.total_general)
