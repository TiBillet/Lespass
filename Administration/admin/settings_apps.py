import logging
from typing import Any, Optional, Dict

import requests
from django.contrib import admin, messages
from django.db import connection
from django.forms import ModelForm, Form
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, get_object_or_404
from django.template.defaultfilters import slugify
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.db.models import Model
from solo.admin import SingletonModelAdmin
from unfold.admin import ModelAdmin
from unfold.decorators import display, action

from Administration.admin.site import staff_admin_site
from ApiBillet.permissions import TenantAdminPermissionWithRequest, RootPermissionWithRequest
from AuthBillet.models import TibilletUser
from BaseBillet.models import (
    GhostConfig, FormbricksConfig, FormbricksForms, FederatedPlace, BrevoConfig, Product
)
from Customers.models import Client
from MetaBillet.models import WaitingConfiguration

logger = logging.getLogger(__name__)


@admin.register(Client, site=staff_admin_site)
class TenantAdmin(ModelAdmin):
    # Doit être référencé pour le champs autocomplete_fields federated_with de configuration
    # est en CRUD total false
    # Seul le search fields est utile :
    search_fields = ['name', ]

    list_display = ['name', 'created_on', 'primary_domain', ]

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        # Uniquement les client qui ont un domaine
        return queryset.prefetch_related('domains').exclude(
            categorie__in=[Client.WAITING_CONFIG, Client.ROOT, Client.META])

    def get_search_results(self, request, queryset, search_term):
        """
        Filtre l'autocomplete des tenants selon la page d'origine.
        Filters tenant autocomplete based on the referring page.

        Utilise sur les pages FederatedPlace (V1) et Federation (V2).
        Exclut les tenants systeme (WAITING_CONFIG, ROOT, META)
        et le tenant courant (on ne s'invite pas soi-meme).
        Used on FederatedPlace (V1) and Federation (V2) pages.
        Excludes system tenants (WAITING_CONFIG, ROOT, META)
        and the current tenant (you don't invite yourself).
        """
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        referer = request.headers.get('Referer', '')
        requete_est_autocomplete = "admin/autocomplete" in request.path

        # Pages qui utilisent l'autocomplete de tenants :
        # - FederatedPlace (V1) : "federatedplace" dans le referer
        # - Federation (V2) : "federation" dans le referer
        # - Asset fedow_core (V2) : "fedow_core/asset" dans le referer
        #   (pour pending_invitations — invitation per-asset)
        page_utilise_autocomplete_tenant = (
            "federatedplace" in referer
            or "federation" in referer
            or "fedow_core/asset" in referer
        )

        if requete_est_autocomplete and page_utilise_autocomplete_tenant:
            queryset = queryset.exclude(
                categorie__in=[Client.WAITING_CONFIG, Client.ROOT, Client.META],
            ).exclude(
                pk=connection.tenant.pk,
            )
        return queryset, use_distinct

    actions_row = ["go_admin", ]

    @action(
        description=_("Go admin"),
        url_path="go_admin",
        permissions=["redirect_admin_action"],
    )
    def go_admin(self, request, object_id):
        tenant: Client = get_object_or_404(Client, pk=object_id)
        primary_domain = f"https://{tenant.get_primary_domain().domain}"
        user = request.user
        if user.is_superuser:
            token = user.get_connect_token()
            connexion_url = f"{primary_domain}/emailconfirmation/{token}"
            return redirect(connexion_url)
        return redirect(request.META["HTTP_REFERER"])

    @display(description=_("Domaine principal"))
    def primary_domain(self, instance: Client):
        primary_domain = f"https://{instance.get_primary_domain().domain}"
        return format_html(f"<a href='{primary_domain}' target='_blank'>{primary_domain}</a>")

    def has_redirect_admin_action_permission(self, request: HttpRequest, *args, **kwargs):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


### Connect

@admin.register(FederatedPlace, site=staff_admin_site)
class FederatedPlaceAdmin(ModelAdmin):
    list_display = ["tenant", "str_tag_filter", "str_tag_exclude", "membership_visible", ]
    fields = ["tenant", "tag_filter", "tag_exclude", "membership_visible", ]
    autocomplete_fields = ["tag_filter", "tag_exclude", "tenant"]

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.select_related('tenant').prefetch_related('tag_filter', 'tag_exclude')

    actions_row = ["connect_to", ]

    @action(
        description=_("See this place"),
        url_path="connect_to",
        permissions=["redirect_admin_action"],
    )
    def connect_to(self, request, object_id):
        fp = get_object_or_404(FederatedPlace, pk=object_id)
        tenant = fp.tenant
        primary_domain = f"https://{tenant.get_primary_domain().domain}"
        user: TibilletUser = request.user
        token = user.get_connect_token()
        connexion_url = f"{primary_domain}/emailconfirmation/{token}"
        return redirect(connexion_url)

    def has_redirect_admin_action_permission(self, request: HttpRequest, *args, **kwargs):
        return TenantAdminPermissionWithRequest(request)

    @display(description=_("Included tags"))
    def str_tag_filter(self, instance: FederatedPlace):
        return ", ".join([tag.name for tag in instance.tag_filter.all()])

    @display(description=_("Excluded tags"))
    def str_tag_exclude(self, instance: FederatedPlace):
        return ", ".join([tag.name for tag in instance.tag_exclude.all()])

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


# Deux formulaires, un qui s'affiche si l'api est vide (ou supprimé)
# L'autre qui n'affiche pas l'input.
class GhostConfigChangeform(ModelForm):
    class Meta:
        model = GhostConfig
        fields = ['ghost_last_log']


class GhostConfigAddform(ModelForm):
    class Meta:
        model = GhostConfig
        fields = ['ghost_url', 'ghost_key', 'ghost_last_log']


@admin.register(GhostConfig, site=staff_admin_site)
class GhostConfigAdmin(SingletonModelAdmin, ModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False

    form = GhostConfigChangeform
    add_form = GhostConfigAddform

    readonly_fields = ["has_key", "ghost_last_log"]
    actions_detail = ["test_api_ghost_admin_button"]

    @display(description=_("Has key"), boolean=True)
    def has_key(self, instance: GhostConfig):
        return True if instance.ghost_key else False

    def get_form(self, request, obj=None, **kwargs):
        """ Si c'est un add, on modifie un peu le formulaire pour avoir un champs email """
        defaults = {}
        if not obj.ghost_key:
            defaults['form'] = self.add_form
        defaults.update(kwargs)
        return super().get_form(request, obj, **defaults)

    def test_api_ghost(self, ghost_url, ghost_key):
        import datetime
        import jwt

        # Split the key into ID and SECRET
        id, secret = ghost_key.split(':')

        # Prepare header and payload
        iat = int(datetime.datetime.now().timestamp())

        header = {'alg': 'HS256', 'typ': 'JWT', 'kid': id}
        payload = {
            'iat': iat,
            'exp': iat + 5 * 60,
            'aud': '/admin/'
        }

        # Create the token
        token = jwt.encode(payload, bytes.fromhex(secret), algorithm='HS256', headers=header)

        # Make a request to the Ghost API
        headers = {'Authorization': f'Ghost {token}'}
        response = requests.get(f"{ghost_url}/ghost/api/admin/members/", headers=headers, params={"limit": 1})
        return response

    def save_model(self, request, obj: GhostConfig, form, change):
        if change:
            try:
                response = self.test_api_ghost(obj.ghost_url, obj.ghost_key)
                if response.ok:
                    obj.set_api_key(obj.ghost_key)
                    messages.success(request, _("Api Key inserted"))
                else:
                    messages.error(request,
                                   _(f"Ghost API connection failed: {response.status_code} - {response.reason}"))
            except Exception as e:
                messages.error(request, _(f"Ghost API connection failed: {e}"))

            # Always save the model, even in error cases
            super().save_model(request, obj, form, change)

    @action(description=_("Test Api"),
            url_path="test_api_ghost_admin_button",
            permissions=["custom_actions_detail"])
    def test_api_ghost_admin_button(self, request, object_id):

        ghost_config = GhostConfig.get_solo()
        ghost_url = ghost_config.ghost_url
        ghost_key = ghost_config.get_api_key()

        if not ghost_url or not ghost_key:
            messages.error(request, _("Ghost URL or API key is missing"))
            return redirect(request.META["HTTP_REFERER"])

        try:
            response = self.test_api_ghost(ghost_url, ghost_key)
            # Update the last_log field with the response
            ghost_config.ghost_last_log = f"{timezone.now()} - Status: {response.status_code} - Response: {response.text}"
            ghost_config.save()

            if response.ok:
                messages.success(request, _("Ghost API connection successful"))
            else:
                messages.error(request, _(f"Ghost API connection failed: {response.status_code} - {response.reason}"))

        except Exception as e:
            ghost_config.ghost_last_log = f"{timezone.now()} - Error: {type(e).__name__} - {str(e)}"
            ghost_config.save()
            messages.error(request, _(f"Error testing Ghost API: {type(e).__name__} - {str(e)}"))

        return redirect(request.META["HTTP_REFERER"])

    def has_custom_actions_detail_permission(self, request, object_id):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request: HttpRequest, obj: Model | None = None) -> bool:
        return TenantAdminPermissionWithRequest(request)


# Deux formulaires, un qui s'affiche si l'api est vide (ou supprimé)
# L'autre qui n'affiche pas l'input.
class FormbricksConfigChangeform(ModelForm):
    class Meta:
        model = FormbricksConfig
        fields = ['api_host']


class FormbricksConfigAddform(ModelForm):
    class Meta:
        model = FormbricksConfig
        fields = ['api_key', 'api_host']


@admin.register(FormbricksConfig, site=staff_admin_site)
class FormbricksConfigAdmin(SingletonModelAdmin, ModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False

    form = FormbricksConfigChangeform
    add_form = FormbricksConfigAddform

    readonly_fields = ["has_key", ]

    @display(description=_("Api key"), boolean=True)
    def has_key(self, instance: FormbricksConfig):
        return True if instance.api_key else False

    def get_form(self, request, obj=None, **kwargs):
        """ Si c'est un add, on modifie un peu le formulaire pour avoir un champs email """
        defaults = {}
        if not obj.api_key:
            defaults['form'] = self.add_form
        defaults.update(kwargs)
        return super().get_form(request, obj, **defaults)

    def save_model(self, request, obj: FormbricksConfig, form, change):
        if change:
            headers = {'x-api-key': obj.api_key}
            check_api = requests.get(f'{obj.api_host}/api/v1/me', headers=headers)
            if check_api.ok:
                obj.set_api_key(obj.api_key)
                messages.success(request, _("Api OK"))
            else:
                obj.api_key = None
                messages.error(request, _("Api not OK"))

        super().save_model(request, obj, form, change)

    # Pour les boutons en haut de la vue changelist
    # chaque decorateur @action génère une nouvelle route
    actions_detail = ["test_api_formbricks", ]

    @action(description=_("Test Api"),
            url_path="test_api_formbricks",
            permissions=["custom_actions_detail"])
    def test_api_formbricks(self, request, object_id):
        fbc = FormbricksConfig.get_solo()
        api_host = fbc.api_host
        headers = {'x-api-key': fbc.get_api_key()}
        check_api = requests.get(f'{api_host}/api/v1/me', headers=headers)
        if check_api.ok:
            messages.success(request, _("Api OK"))
        else:
            messages.error(request, _("Api not OK"))
        return redirect(request.META["HTTP_REFERER"])

    def has_custom_actions_detail_permission(self, request, object_id):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


@admin.register(FormbricksForms, site=staff_admin_site)
class FormbricksFormsAdmin(ModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False

    list_display = ['product', 'environmentId']

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'product':  # Replace 'user_field' with your actual field name
            kwargs['queryset'] = Product.objects.filter(
                archive=False,
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj: FormbricksForms, form, change):
        if obj.product:
            messages.info(request, f"product_name : {slugify(obj.product.name)}")
            for price in obj.product.prices.all():
                messages.info(request, f"price_name : {slugify(price.name)}")
        super().save_model(request, obj, form, change)

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

    actions_detail = ["create_tenant", ]

    @action(description=_("Create instance"),
            url_path="create_tenant",
            permissions=["custom_actions_detail"])
    def create_tenant(self, request, object_id):
        wc = WaitingConfiguration.objects.get(pk=object_id)
        if wc.email_confirmed:
            try:
                tenant = wc.create_tenant()
                messages.add_message(
                    request, messages.SUCCESS,
                    _(f"creation OK")
                )
            except Exception as e:
                messages.add_message(
                    request, messages.ERROR,
                    _(f"{wc.organisation} tenant create error : {e} not confirmed")
                )

        else:
            messages.add_message(
                request, messages.WARNING,
                _(f"Email not confirmed")
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


# Deux formulaires, un qui s'affiche si l'api est vide (ou supprimé)
# L'autre qui n'affiche pas l'input.
class BrevoConfigChangeform(ModelForm):
    class Meta:
        model = BrevoConfig
        fields = ['last_log']


class BrevoConfigAddform(ModelForm):
    class Meta:
        model = BrevoConfig
        fields = ['api_key', 'last_log', ]


@admin.register(BrevoConfig, site=staff_admin_site)
class BrevoConfigAdmin(SingletonModelAdmin, ModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False

    readonly_fields = ['last_log', "has_key", ]
    actions_detail = ["test_api_brevo", ]

    form = BrevoConfigChangeform
    add_form = BrevoConfigAddform

    @display(description=_("Has key"), boolean=True)
    def has_key(self, instance: BrevoConfig):
        return True if instance.api_key else False

    def get_form(self, request, obj=None, **kwargs):
        """ Si c'est un add, on modifie un peu le formulaire pour avoir un champs email """
        defaults = {}
        if not obj.api_key:
            defaults['form'] = self.add_form
        defaults.update(kwargs)
        return super().get_form(request, obj, **defaults)

    def save_model(self, request, obj: FormbricksConfig, form, change):
        if change:
            obj.set_api_key(obj.api_key)
            messages.success(request, _("Clé Api chiffrée"))

        super().save_model(request, obj, form, change)

    @action(description=_("Test Api"),
            url_path="test_api_brevo",
            permissions=["custom_actions_detail"])
    def test_api_brevo(self, request, object_id):
        import sib_api_v3_sdk
        from sib_api_v3_sdk.rest import ApiException
        brevo_config = BrevoConfig.get_solo()

        try:
            configuration = sib_api_v3_sdk.Configuration()
            configuration.api_key['api-key'] = brevo_config.get_api_key()
            api_instance = sib_api_v3_sdk.AccountApi(sib_api_v3_sdk.ApiClient(configuration))
            api_response = api_instance.get_account()
            brevo_config.last_log = api_response
            messages.success(request, _(f"Api OK"))
        except ApiException as e:
            brevo_config.last_log = f"{e}"
            logger.warning("ApiException when calling AccountApi->get_account: %s\n" % e)
            messages.error(request, _(f"Api not OK : {e}"))
        except Exception as e:
            brevo_config.last_log = f"{type(e)} - {e}"
            logger.error("Exception when calling AccountApi->get_account: %s\n" % e)
            messages.error(request, f"Error : {type(e)} - {e}")

        brevo_config.save()
        return redirect(request.META["HTTP_REFERER"])

    def has_custom_actions_detail_permission(self, request, object_id):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return False
        # return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)
