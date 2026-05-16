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

from django.contrib import admin, messages
from django.shortcuts import redirect
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin
from unfold.decorators import action

from Administration.admin.site import staff_admin_site
from ApiBillet.permissions import RootPermissionWithRequest, TenantAdminPermissionWithRequest
from MetaBillet.models import WaitingConfiguration
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


@admin.register(WaitingConfiguration, site=staff_admin_site)
class WaitingConfigAdmin(ModelAdmin):
    """
    Admin Unfold pour WaitingConfiguration (brouillons du wizard onboard).

    Migre depuis `Administration/admin_tenant.py` le 2026-05-16 dans le
    cadre du cleanup du flow legacy `/tenant/new/`. Avant cette migration,
    cet admin etait melange avec tous les autres admins de tenant.

    Cas d'usage : le ROOT admin peut visualiser les brouillons en cours,
    leur etat (`current_step`, `email_confirmed`, `created`, `tenant`),
    et finaliser manuellement la creation tenant pour un brouillon bloque
    (via l'action `create_tenant`). En pratique, la creation se fait
    deja automatiquement via `onboard.tasks.create_tenant_from_draft`
    avec retry — cette action manuelle est un filet de securite.

    Permissions : ROOT only (`RootPermissionWithRequest`). Les brouillons
    vivent dans le schema `meta` partage et contiennent des donnees
    sensibles (emails, OTP hashes) qui ne doivent pas etre exposees aux
    admins de tenant.

    / Unfold admin for WaitingConfiguration (onboard wizard drafts).
    Migrated from `Administration/admin_tenant.py` on 2026-05-16 as part
    of the legacy `/tenant/new/` cleanup. ROOT-only: drafts live in the
    shared `meta` schema and contain sensitive data (emails, OTP hashes).
    """

    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False

    list_display = (
        "organisation",
        "email",
        "datetime",
        "site_web",
        "short_description",
        "laboutik_wanted",
        "payment_wanted",
        "email_confirmed",
        "created",
    )

    fields = list_display
    readonly_fields = (
        "datetime",
    )

    ordering = ('-datetime',)

    list_filter = ["datetime", "created"]
    search_fields = ["email", "organisation", "datetime"]

    actions_detail = ["create_tenant"]

    @action(
        description=_("Create instance"),
        url_path="create_tenant",
        permissions=["custom_actions_detail"],
    )
    def create_tenant(self, request, object_id):
        """
        Action manuelle pour finaliser la creation d'un tenant a partir
        d'un brouillon `WaitingConfiguration`. Utilisee comme filet de
        securite quand `onboard.tasks.create_tenant_from_draft` a echoue
        et n'a pas pu retry (ex: pool de tenants vides epuise).

        / Manual action to finalize tenant creation from a draft. Safety
        net when `create_tenant_from_draft` failed and couldn't retry.
        """
        wc = WaitingConfiguration.objects.get(pk=object_id)
        if wc.email_confirmed:
            try:
                wc.create_tenant()
                messages.add_message(
                    request, messages.SUCCESS,
                    _("Tenant created."),
                )
            except Exception as e:
                messages.add_message(
                    request, messages.ERROR,
                    _("%(name)s tenant create error: %(err)s") % {
                        "name": wc.organisation, "err": e,
                    },
                )
        else:
            messages.add_message(
                request, messages.WARNING,
                _("Email not confirmed"),
            )
        return redirect(request.META["HTTP_REFERER"])

    def has_custom_actions_detail_permission(self, request, object_id):
        return RootPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return RootPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return RootPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return RootPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return RootPermissionWithRequest(request)
