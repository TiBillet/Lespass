import logging
from datetime import timedelta
from typing import Any, Optional, Dict
from urllib.parse import urlencode

from django.contrib import admin, messages
from django.db import connection
from django.http import HttpRequest
from django.shortcuts import redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin
from unfold.decorators import display, action

from Administration.admin.site import staff_admin_site
from ApiBillet.permissions import TenantAdminPermissionWithRequest, RootPermissionWithRequest
from AuthBillet.models import HumanUser, TibilletUser
from BaseBillet.tasks import forge_connexion_url

logger = logging.getLogger(__name__)


class IsTenantAdminFilter(admin.SimpleListFilter):
    # Human-readable title which will be displayed in the
    # right admin sidebar just above the filter options.
    title = _("Administrator")

    # Parameter for the filter that will be used in the URL query.
    parameter_name = "client_admin"

    def lookups(self, request, model_admin):
        return [("Y", _("Yes")), ("N", _("No"))]

    def queryset(self, request, queryset):
        if self.value() == "Y":
            return queryset.filter(
                client_admin__in=[connection.tenant],
                espece=TibilletUser.TYPE_HUM
            ).distinct()
        if self.value() == "N":
            return queryset.exclude(
                client_admin__in=[connection.tenant],
            ).distinct()


class CanInitPaiementFilter(admin.SimpleListFilter):
    # Human-readable title which will be displayed in the
    # right admin sidebar just above the filter options.
    title = _("Can initiate payments")

    # Parameter for the filter that will be used in the URL query.
    parameter_name = "initiate_payment"

    def lookups(self, request, model_admin):
        return [("Y", _("Yes")), ("N", _("No"))]

    def queryset(self, request, queryset):
        if self.value() == "Y":
            return queryset.filter(
                initiate_payment__in=[connection.tenant],
                espece=TibilletUser.TYPE_HUM
            ).distinct()
        if self.value() == "N":
            return queryset.exclude(
                initiate_payment__in=[connection.tenant],
            ).distinct()


class UserWithMembershipValid(admin.SimpleListFilter):
    # Human-readable title which will be displayed in the
    # right admin sidebar just above the filter options.
    title = _("Valid subscription")

    # Parameter for the filter that will be used in the URL query.
    parameter_name = "membership_valid"

    def lookups(self, request, model_admin):
        """
        Returns a list of tuples. The first element in each
        tuple is the coded value for the option that will
        appear in the URL query. The second element is the
        human-readable name for the option that will appear
        in the right sidebar.
        """
        return [
            ("Y", _("Yes")),
            ("N", _("No")),
            ("B", _("Expires soon (2 weeks)")),
        ]

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """
        # Compare the requested value (either '80s' or '90s')
        # to decide how to filter the queryset.
        if self.value() == "Y":
            return queryset.filter(
                memberships__deadline__gte=timezone.localtime(),
            ).distinct()
        if self.value() == "N":
            return queryset.exclude(
                memberships__deadline__gte=timezone.localtime()
            ).distinct()
        if self.value() == "B":
            return queryset.filter(
                memberships__deadline__lte=timezone.localtime() + timedelta(weeks=2),
                memberships__deadline__gte=timezone.localtime(),
            ).distinct()


# Tout les utilisateurs de type HUMAIN
@admin.register(HumanUser, site=staff_admin_site)
class HumanUserAdmin(ModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = False  # Default: False

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.prefetch_related('memberships', 'client_admin')

    change_form_after_template = "admin/human_user/right_and_wallet_info.html"

    list_display = [
        'email',
        'first_name',
        'last_name',
        'display_memberships_valid',
    ]

    search_fields = [
        'email',
        'first_name',
        'last_name',
    ]

    fieldsets = (
        ('Général', {
            'fields': (
                'email',
                ('first_name', 'last_name'),
                "email_valid",
            )
        }),
    )

    readonly_fields = [
        "email",
        "email_valid",
        "administre",
    ]

    list_filter = [
        "is_active",
        UserWithMembershipValid,
        IsTenantAdminFilter,
        CanInitPaiementFilter,
        "email_valid",
    ]

    def changeform_view(self, request: HttpRequest, object_id: Optional[str] = None, form_url: str = "",
                        extra_context: Optional[Dict[str, bool]] = None) -> Any:
        extra_context = extra_context or {}
        extra_context['object_id'] = object_id
        # Provide initial states for rights toggles
        if object_id:
            try:
                user = TibilletUser.objects.get(pk=object_id)
                tenant = connection.tenant
                # Admin (client_admin) initial state
                extra_context['is_client_admin'] = user.client_admin.filter(pk=tenant.pk).exists()
                extra_context['can_initiate_payment'] = user.initiate_payment.filter(pk=tenant.pk).exists()
                extra_context['can_create_event'] = user.create_event.filter(pk=tenant.pk).exists()
                extra_context['can_manage_crowd'] = user.manage_crowd.filter(pk=tenant.pk).exists()
            except HumanUser.DoesNotExist:
                extra_context['is_client_admin'] = False
                extra_context['can_initiate_payment'] = False
                extra_context['can_create_event'] = False
                extra_context['can_manage_crowd'] = False
            except Exception as e:
                raise e

        return super().changeform_view(request, object_id, form_url, extra_context)

    # noinspection PyTypeChecker
    @display(description=_("Subscriptions"), label={None: "danger", True: "success"})
    def display_memberships_valid(self, instance: HumanUser):
        count = instance.memberships_valid()
        if count > 0:
            # Lien cliquable vers la liste des adhésions filtrée par l'email
            url = "/admin/BaseBillet/membership/"
            query = urlencode({"q": instance.email})
            return True, format_html('<a href="{}?{}">{}</a>', url, query, _(f"Valid: {count}"))
        return None, _("None")

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request, obj=None):
        return False  # Autoriser l'ajout

    def has_custom_actions_detail_permission(self, request, object_id):
        perm = TenantAdminPermissionWithRequest(request)
        logger.info(request.user, perm)
        return perm

    actions_row = ["login_as_user", ]

    def has_custom_actions_row_permission(self, request, obj=None):
        return RootPermissionWithRequest(request)

    @action(
        description=_("Login as this user"),
        url_path="login_as_user",
        permissions=["custom_actions_row"],
    )
    def login_as_user(self, request, object_id):
        if not RootPermissionWithRequest(request):
            messages.error(request, _("You do not have permission to perform this action."))
            return redirect(request.META.get("HTTP_REFERER", "/admin/"))

        user = get_object_or_404(HumanUser, pk=object_id)
        tenant = connection.tenant
        try:
            domain = tenant.get_primary_domain().domain
            base_url = f"https://{domain}"
        except Exception:
            base_url = "https://tibillet.org"

        connexion_url = forge_connexion_url(user, base_url)
        return redirect(connexion_url)
