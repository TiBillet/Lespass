import json
import logging
from typing import Any, Optional, Dict
from uuid import UUID

from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.db import connection
from django.db.models import Q
from django.forms import Form
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, get_object_or_404
from django.urls import reverse, re_path
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST
from django_htmx.http import HttpResponseClientRedirect
from django_tenants.utils import tenant_context
from unfold.admin import ModelAdmin
from unfold.decorators import display, action

from Administration.admin.site import staff_admin_site
from ApiBillet.permissions import TenantAdminPermissionWithRequest
from AuthBillet.models import Wallet
from fedow_connect.fedow_api import FedowAPI
from fedow_connect.models import FedowConfig
from fedow_public.models import AssetFedowPublic as Asset, AssetFedowPublic

logger = logging.getLogger(__name__)


@admin.register(AssetFedowPublic, site=staff_admin_site)
class AssetAdmin(ModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False

    change_form_before_template = "admin/asset/asset_change_form_before.html"
    list_before_template = "admin/asset/asset_list_before.html"

    list_display = [
        "name",
        "currency_code",
        "category",
        "origin",
        "_federated_with",
    ]

    readonly_fields = [
        'created_at',
        'wallet_origin',
        'federated_with',
    ]

    fields = [
        "name",
        "currency_code",
        "category",
        "pending_invitations",
        "federated_with",
    ]

    autocomplete_fields = [
        'pending_invitations',
    ]

    actions_row = ["archive", ]

    @action(
        description=_("Archive"),
        url_path="archive",
        permissions=["changelist_row_action"],
    )
    def archive(self, request, object_id):
        asset = get_object_or_404(Asset, pk=object_id)
        fedowAPI = FedowAPI()
        fedowAPI.asset.archive_asset(asset.uuid)
        asset.archive = True
        asset.save()
        messages.success(request, _(f"{asset.name} Archived"))
        return redirect(request.META["HTTP_REFERER"])

    def has_changelist_row_action_permission(self, request: HttpRequest, *args, **kwargs):
        return TenantAdminPermissionWithRequest(request)

    def _federated_with(self, obj):
        feds = [place.name for place in obj.federated_with.all()]
        feds.append(obj.origin.name)
        return ", ".join(feds)

    # On affiche que les assets non adhésions + origin + fédéré
    def get_queryset(self, request):
        logger.info(f"get_queryset AssetAdmin : {request.user}")
        fedowAPI = FedowAPI()
        fedowAPI.asset.get_accepted_assets()
        # On va mettre a jour les assets chez Fedow :

        tenant = connection.tenant
        queryset = (
            super()
            .get_queryset(request)
            .exclude(category__in=[AssetFedowPublic.BADGE, AssetFedowPublic.SUBSCRIPTION])
            .filter(Q(origin=tenant) | Q(federated_with=tenant))
            .filter(archive=False)
            .distinct()
        )
        return queryset

    def save_model(self, request: HttpRequest, obj: Asset, form: Form, change: Any) -> None:
        # Vérifie si l'objet est nouveau
        new = not change or not getattr(obj, 'pk', None)
        if new:
            # Vérifie les champs choisis (ici, la catégorie) selon le contexte
            allowed_on_create = {AssetFedowPublic.TOKEN_LOCAL_FIAT, AssetFedowPublic.TOKEN_LOCAL_NOT_FIAT,
                                 AssetFedowPublic.TIME, Asset.FIDELITY}
            if obj.category not in allowed_on_create:
                messages.error(request, _("Catégorie non autorisée pour une création."))
                raise ValidationError("Invalid category on create")

            obj.origin = connection.tenant
            fedow_config = FedowConfig.get_solo()
            obj.wallet_origin = fedow_config.wallet
            # On sauvegarde dans la base de donnée
            super().save_model(request, obj, form, change)

            try:
                fedowAPI = FedowAPI(fedow_config=fedow_config)
                asset, created = fedowAPI.asset.get_or_create_token_asset(obj)
                logger.info(f"Asset créé chez fédow {asset} : {created}")
            except Exception as e:
                messages.error(request, f"{e}")
                raise ValidationError(str(e))

            if not created:
                messages.error(request, _("Asset already exists"))
                raise ValidationError("Asset already exists")

    def get_readonly_fields(self, request, obj=None):
        ro = list(super().get_readonly_fields(request, obj))
        if obj is not None:
            for f in ("name", "currency_code", "category"):
                if f not in ro:
                    ro.append(f)
        return ro

    def save_related(self, request, form, formsets, change):
        """Ensure only origin tenant admins can modify pending_invitations.
        If the current tenant is not the asset origin, any attempted change to
        pending_invitations is reverted and an error message is shown.
        """
        obj = form.instance
        # Snapshot existing pending invitations before m2m save
        prev_pending_ids = set()
        if getattr(obj, 'pk', None):
            try:
                prev_pending_ids = set(obj.pending_invitations.values_list('pk', flat=True))
            except Exception:
                prev_pending_ids = set()
        super().save_related(request, form, formsets, change)
        try:
            current_tenant_id = getattr(connection.tenant, 'pk', None)
            origin_id = getattr(obj, 'origin_id', None)
            if obj.pk and origin_id != current_tenant_id:
                # Non-origin tenant is not allowed to change invitations: revert to previous
                obj.pending_invitations.set(list(prev_pending_ids))
                messages.error(request, _("Seul le lieu d'origine peut envoyer des invitations."))
        except Exception:
            # Fail-closed: if something goes wrong, keep previous state already restored above when applicable
            pass

    def get_form(self, request, obj=None, **kwargs):
        # Limit category choices on add form to TOKEN_LOCAL_FIAT and TOKEN_LOCAL_NOT_FIAT
        form = super().get_form(request, obj, **kwargs)
        try:
            if obj is None and 'category' in form.base_fields:
                allowed = [
                    (Asset.TOKEN_LOCAL_FIAT, dict(Asset.CATEGORIES)[Asset.TOKEN_LOCAL_FIAT]),
                    (Asset.TOKEN_LOCAL_NOT_FIAT, dict(Asset.CATEGORIES)[Asset.TOKEN_LOCAL_NOT_FIAT]),
                    (Asset.TIME, dict(Asset.CATEGORIES)[Asset.TIME]),
                    (Asset.FIDELITY, dict(Asset.CATEGORIES)[Asset.FIDELITY]),
                ]
                form.base_fields['category'].choices = allowed
        except Exception:
            pass
        return form

    def get_fields(self, request, obj=None):
        # Hide "Partager cet actif" (pending_invitations) unless the current tenant is the asset origin
        fields = list(super().get_fields(request, obj))
        try:
            if obj is not None:
                current_tenant = connection.tenant
                if getattr(obj, 'origin_id', None) != getattr(current_tenant, 'pk', None):
                    if 'pending_invitations' in fields:
                        fields.remove('pending_invitations')
        except Exception:
            # In case of any unexpected issue, fall back to original fields
            pass
        return fields

    def changeform_view(self, request: HttpRequest, object_id: Optional[str] = None, form_url: str = "",
                        extra_context: Optional[Dict[str, Any]] = None):
        """Inject Fedow data for the before template on change view and handle invite form POST."""
        extra_context = extra_context or {}
        serialized_asset = {}
        error_message = None
        total_by_place_with_uuid = {}

        if object_id:
            try:
                fedow = FedowAPI()
                fedow_data = fedow.asset.total_by_place_with_uuid(uuid=object_id)
                # fedow_data is a JSON string; parse it to dict
                total_by_place_with_uuid = json.loads(fedow_data) if isinstance(fedow_data, (str, bytes)) else (
                        fedow_data or {})
                logger.info(f"fedow_data : {fedow_data}")

                # Expected new structure: {"total_by_place": [{"place_name": ..., "place_uuid": ..., "total_value": ...}, ...], "serialized_asset": {...}}
                totals_list = (total_by_place_with_uuid or {}).get("total_by_place") or []
                serialized_asset = (total_by_place_with_uuid or {}).get("serialized_asset") or {}

            except Exception as e:
                error_message = str(e)

        extra_context.update({
            "total_by_place_with_uuid": total_by_place_with_uuid,
            "serialized_asset": serialized_asset,
            "fedow_error": error_message,
            "asset_pk": object_id,
        })
        return super().changeform_view(request, object_id, form_url, extra_context)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            re_path(
                r'^accept_invitation/(?P<asset_pk>.+)/$',
                self.admin_site.admin_view(csrf_protect(require_POST(self.accept_invitation))),
                name='asset-accept-invitation',
            ),
            re_path(
                r'^bank_deposit/(?P<asset_pk>.+)/(?P<wallet_to_deposit>.+)/$',
                self.admin_site.admin_view(csrf_protect(require_POST(self.bank_deposit))),
                name='asset-bank-deposit',
            ),
        ]
        return custom_urls + urls

    def accept_invitation(self, request: HttpRequest, asset_pk: str):
        # Accept an invitation for the current tenant on the given asset
        tenant = connection.tenant
        place_added_uuid = FedowConfig.get_solo().fedow_place_uuid

        # Basic permission check for tenant admins
        if not TenantAdminPermissionWithRequest(request):
            messages.error(request, _("Permission refusée."))
            return redirect(
                reverse(f"{self.admin_site.name}:{self.model._meta.app_label}_{self.model._meta.model_name}_changelist")
            )

        asset = get_object_or_404(AssetFedowPublic, pk=asset_pk)

        if request.method != 'POST':
            return redirect(
                reverse(f"{self.admin_site.name}:{self.model._meta.app_label}_{self.model._meta.model_name}_changelist")
            )

        if asset.pending_invitations.filter(pk=tenant.pk).exists():
            with tenant_context(asset.origin):
                fedowAPI = FedowAPI()
                place_origin_uuid = FedowConfig.get_solo().fedow_place_uuid
                federation = fedowAPI.federation.create_fed(
                    user=request.user,
                    asset=asset,
                    place_added_uuid=place_added_uuid,
                    place_origin_uuid=place_origin_uuid,
                )
                # Move tenant from pending to federated
                asset.pending_invitations.remove(tenant)
                asset.federated_with.add(tenant)

            messages.success(request, _("Invitation acceptée."))
        else:
            messages.error(request, _("Aucune invitation en attente pour ce lieu."))

        return redirect(
            reverse(f"{self.admin_site.name}:{self.model._meta.app_label}_{self.model._meta.model_name}_changelist")
        )

    def bank_deposit(self, request: HttpRequest, asset_pk: str, wallet_to_deposit: str):
        """Handle HTMX POST to declare a bank deposit for a local asset.
        Expects POST params: place (str), amount (decimal), origin_wallet (uuid optional), destination_wallet (uuid optional).
        wallet_to_deposit : Le wallet qu'il faut vider
        """
        if not TenantAdminPermissionWithRequest(request):
            return HttpResponse(status=403)

        asset = get_object_or_404(AssetFedowPublic, uuid=UUID(asset_pk))
        wallet = get_object_or_404(Wallet, uuid=UUID(wallet_to_deposit))
        wallet_to_deposit = wallet.uuid

        try:
            fedow = FedowAPI()
            transaction = fedow.wallet.local_asset_bank_deposit(
                user=request.user,
                wallet_to_deposit=f"{wallet_to_deposit}",
                asset=asset,
            )
            messages.add_message(request, messages.SUCCESS, _("Remise en banque OK."))

        except Exception as e:
            logger.error(e)
            messages.add_message(request, messages.ERROR, f"{e}")

        return HttpResponseClientRedirect(request.META["HTTP_REFERER"])

    def changelist_view(self, request: HttpRequest, extra_context: Optional[Dict[str, Any]] = None):
        # Provide invitations list for the list_before_template
        extra_context = extra_context or {}
        tenant = connection.tenant
        invitations_qs = AssetFedowPublic.objects.filter(pending_invitations=tenant).select_related('origin')
        extra_context.update({
            'asset_invitations': invitations_qs,
        })
        return super().changelist_view(request, extra_context=extra_context)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return False
