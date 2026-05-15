"""
Admin Unfold pour OnboardInvitation.
/ Unfold admin for OnboardInvitation.

LOCALISATION: onboard/admin.py

NOTE :
Sur la branche `main-wizard`, `fedow_core` n'est pas encore merge donc
l'action "Generate invitation" depuis `FederationAdmin` (cf. Task 21 du
plan onboard) n'est PAS implementee ici. Elle sera ajoutee au merge V2,
en meme temps que la FK `OnboardInvitation.federation`.
Cet admin permet uniquement de lister et d'inspecter les invitations
existantes (creees par les tests ou par un futur outil d'invitation).
/ On the `main-wizard` branch, `fedow_core` is not yet merged so the
"Generate invitation" action on `FederationAdmin` (Task 21 of the
onboard plan) is NOT implemented here. It will be added at V2 merge,
along with the `OnboardInvitation.federation` FK.
This admin only lists/inspects existing invitations (created via tests
or a future invitation tool).
"""

from django.contrib import admin
from unfold.admin import ModelAdmin

from Administration.admin.site import staff_admin_site
from ApiBillet.permissions import TenantAdminPermissionWithRequest
from onboard.models import OnboardInvitation


@admin.register(OnboardInvitation, site=staff_admin_site)
class OnboardInvitationAdmin(ModelAdmin):
    """
    Admin Unfold pour OnboardInvitation. Lecture seule sur le code et
    les timestamps auto-generes (code, created_at, used_at).
    / Unfold admin for OnboardInvitation. Read-only on code and
    auto-generated timestamps (code, created_at, used_at).

    Permissions : reservees aux admins de tenant (convention du projet,
    cf. TenantAdminPermissionWithRequest dans ApiBillet/permissions.py).
    / Permissions: restricted to tenant admins (project convention,
    see TenantAdminPermissionWithRequest in ApiBillet/permissions.py).
    """

    # Affichage liste — colonnes lisibles d'un coup d'oeil.
    # / List view — at-a-glance columns.
    list_display = (
        "code",
        "invited_by_tenant",
        "invited_by_user",
        "email_invited",
        "used_at",
        "expires_at",
        "created_at",
    )

    list_filter = ("expires_at", "used_at", "invited_by_tenant")
    search_fields = ("code", "email_invited", "invited_by_user__email")

    # Le code, les timestamps `created_at` et `used_at` sont generes
    # automatiquement (defaut secrets.token_urlsafe, auto_now_add,
    # marquage applicatif lors de l'usage). On les protege en lecture
    # seule pour eviter toute modification manuelle.
    # / Code and timestamps are auto-generated (default
    # secrets.token_urlsafe, auto_now_add, app-level mark on use).
    # Read-only to prevent manual changes.
    readonly_fields = ("code", "created_at", "used_at")

    ordering = ("-created_at",)

    # Permissions explicites — convention du projet : chaque ModelAdmin
    # declare ses 4 permissions via TenantAdminPermissionWithRequest
    # (cf. CarrouselAdmin, TagAdmin, etc. dans Administration/admin_tenant.py).
    # / Explicit permissions — project convention: each ModelAdmin
    # declares its 4 permissions via TenantAdminPermissionWithRequest
    # (see CarrouselAdmin, TagAdmin, etc. in Administration/admin_tenant.py).
    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)
