"""
QrcodeCashless/admin.py — Admin CarteCashless dans Unfold (staff_admin_site).
QrcodeCashless/admin.py — CarteCashless admin in Unfold (staff_admin_site).

Le dashboard (Administration/admin/dashboard.py) propose un bouton « Cartes NFC »
pointant vers `staff_admin:QrcodeCashless_cartecashless_changelist`. Sans ce ModelAdmin,
le reverse echoue et le bouton est mort (« # »). On enregistre donc une vue LECTURE SEULE.
/ The dashboard "NFC cards" button reverses this changelist; without the ModelAdmin the
button is dead ("#"). We register a READ-ONLY admin.

IMPORTANT — Filtrage par tenant :
CarteCashless est en SHARED_APPS (schema public PostgreSQL) : PAS d'isolation automatique.
get_queryset() DOIT filtrer par tenant (via detail.origine = la place qui a emis la carte),
exactement comme fedow_core/admin.py. Sans ca, un lieu verrait les cartes de TOUS les lieux.
/ CarteCashless is in SHARED_APPS: no automatic isolation. get_queryset() MUST filter by
tenant (via detail.origine), like fedow_core/admin.py.
"""

import logging

from django.contrib import admin
from django.db import connection
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin

from Administration.admin_tenant import staff_admin_site
from ApiBillet.permissions import TenantAdminPermissionWithRequest
from QrcodeCashless.models import CarteCashless

logger = logging.getLogger(__name__)


# Helper module-level — jamais a l'interieur d'une classe ModelAdmin Unfold (piege 23).
# Module-level helper — never inside a ModelAdmin class with Unfold (pitfall 23).
def _uuid_court(valeur):
    """8 premiers caracteres d'un uuid (lisibilite admin). / First 8 chars of a uuid."""
    if not valeur:
        return "—"
    return str(valeur)[:8]


@admin.register(CarteCashless, site=staff_admin_site)
class CarteCashlessAdmin(ModelAdmin):
    """
    Admin LECTURE SEULE des cartes NFC (CarteCashless).
    Read-only admin for NFC cards.

    On ne cree, ni ne modifie, ni ne supprime une carte depuis l'admin : les cartes sont
    provisionnees dans Fedow (seed / import) puis miroitees en local. L'admin sert a
    CONSULTER (depannage : retrouver une carte par tag_id, voir son user / wallet / origine).
    / Cards are never created/edited/deleted from the admin: they are provisioned in Fedow
    then mirrored locally. The admin is for CONSULTING only (troubleshooting).
    """

    list_display = ["tag_id", "number", "user", "wallet_court", "origine_court"]
    search_fields = ["tag_id", "number", "user__email"]

    # --- Colonnes calculees / Computed columns ---

    def wallet_court(self, obj):
        """UUID court du wallet effectif (ephemere si carte anonyme, sinon celui du user).
        / Short UUID of the effective wallet (ephemeral if anonymous, else the user's)."""
        wallet = obj.wallet_ephemere or (obj.user.wallet if obj.user_id else None)
        return _uuid_court(wallet.uuid if wallet else None)

    wallet_court.short_description = _("Wallet")

    def origine_court(self, obj):
        """Lieu (tenant) qui a emis la carte, via detail.origine.
        / Venue (tenant) that issued the card, via detail.origine."""
        if obj.detail_id and obj.detail.origine_id:
            return obj.detail.origine.name
        return "—"

    origine_court.short_description = _("Lieu d'origine")

    # --- Queryset filtre par tenant / Tenant-filtered queryset ---

    def get_queryset(self, request):
        """
        Filtre les cartes par tenant courant (la place d'emission, detail.origine).
        Filters cards by current tenant (the issuing place, detail.origine).

        SHARED_APPS oblige : sans ce filtre, un lieu verrait les cartes de tous les lieux.
        SHARED_APPS requires this: without it, a venue would see all venues' cards.
        """
        queryset = super().get_queryset(request)
        tenant_actuel = connection.tenant
        return queryset.filter(detail__origine=tenant_actuel).select_related(
            "user", "user__wallet", "detail", "detail__origine", "wallet_ephemere"
        )

    # --- Permissions : lecture seule / Read-only permissions ---

    def has_add_permission(self, request):
        return False

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
