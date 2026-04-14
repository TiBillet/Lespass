"""
Administration/admin/cards.py — Admin Unfold pour CarteCashless et Detail.
Administration/admin/cards.py — Unfold admin for CarteCashless and Detail.

Filtre par detail.origine == tenant courant pour les non-superusers.
Creation et suppression reservees aux superusers.
Refund : integre dans change_form_before_template (panel + modal HTMX).
"""
from django.contrib import admin
from django.db import connection

from django.urls import path
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin

from Administration.admin.site import staff_admin_site
from Administration import views_cards
from ApiBillet.permissions import TenantAdminPermissionWithRequest

from QrcodeCashless.models import CarteCashless, Detail


# ---------------------------------------------------------------------------
# Helpers module-level (jamais dans une classe ModelAdmin Unfold !)
# Module-level helpers (NEVER inside a ModelAdmin class with Unfold!)
# Cf. tests/PIEGES.md "Ne JAMAIS definir de methodes helper dans un ModelAdmin Unfold"
# ---------------------------------------------------------------------------

def _user_link(carte: CarteCashless) -> str:
    if carte.user is None:
        return format_html('<span style="opacity:0.5">{}</span>', _("(anonyme)"))
    return format_html('{}', carte.user.email)


def _detail_origine(carte: CarteCashless) -> str:
    if carte.detail is None or carte.detail.origine is None:
        return "—"
    return carte.detail.origine.name


def _wallet_status(carte: CarteCashless) -> str:
    if carte.user is not None:
        return _("Identifiée")
    if carte.wallet_ephemere is not None:
        return _("Anonyme (éphémère)")
    return _("Vierge")


def _detail_nb_cartes(detail: Detail) -> int:
    return CarteCashless.objects.filter(detail=detail).count()


# ---------------------------------------------------------------------------
# CarteCashlessAdmin
# ---------------------------------------------------------------------------

@admin.register(CarteCashless, site=staff_admin_site)
class CarteCashlessAdmin(ModelAdmin):
    compressed_fields = True
    warn_unsaved_form = True

    list_display = (
        "tag_id",
        "number",
        "user_link",
        "detail_origine",
        "wallet_status",
    )
    search_fields = ("tag_id", "number", "user__email")
    list_filter = ("detail__origine",)
    readonly_fields = ("tag_id", "number", "uuid")

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            # Formulaire de creation : seuls les champs de base en readonly.
            # Add form: only base fields are read-only.
            return self.readonly_fields
        # En mode change : tous les champs en lecture seule.
        # In change mode: all fields read-only (form is purely informational).
        return [field.name for field in self.model._meta.fields]

    change_form_before_template = "admin/cards/refund_before.html"

    def user_link(self, obj):
        return _user_link(obj)
    user_link.short_description = _("Utilisateur·ice")

    def detail_origine(self, obj):
        return _detail_origine(obj)
    detail_origine.short_description = _("Lieu d'origine")

    def wallet_status(self, obj):
        return _wallet_status(obj)
    wallet_status.short_description = _("Statut")

    # --- Permissions : 4 methodes obligatoires ---
    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    # --- Filtre tenant ---
    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("user", "detail__origine")
        if request.user.is_superuser:
            return qs
        return qs.filter(detail__origine_id=connection.tenant.pk)

    # --- URLs custom : endpoints HTMX pour refund ---
    def get_urls(self):
        custom_urls = [
            path(
                "<uuid:pk>/refund-panel/",
                self.admin_site.admin_view(
                    views_cards.CardRefundViewSet.as_view({"get": "panel"})
                ),
                name="QrcodeCashless_cartecashless_refund_panel",
            ),
            path(
                "<uuid:pk>/refund-modal/",
                self.admin_site.admin_view(
                    views_cards.CardRefundViewSet.as_view({"get": "modal"})
                ),
                name="QrcodeCashless_cartecashless_refund_modal",
            ),
            path(
                "<uuid:pk>/refund-confirm/",
                self.admin_site.admin_view(
                    views_cards.CardRefundViewSet.as_view({"post": "confirm"})
                ),
                name="QrcodeCashless_cartecashless_refund_confirm",
            ),
        ]
        return custom_urls + super().get_urls()


# ---------------------------------------------------------------------------
# DetailAdmin (inchange)
# ---------------------------------------------------------------------------

@admin.register(Detail, site=staff_admin_site)
class DetailAdmin(ModelAdmin):
    compressed_fields = True
    warn_unsaved_form = True

    list_display = ("slug", "base_url", "origine", "generation", "nb_cartes")
    search_fields = ("slug", "base_url")
    list_filter = ("origine", "generation")
    readonly_fields = ("uuid",)

    def nb_cartes(self, obj):
        return _detail_nb_cartes(obj)
    nb_cartes.short_description = _("Nombre de cartes")

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("origine")
        if request.user.is_superuser:
            return qs
        return qs.filter(origine_id=connection.tenant.pk)
