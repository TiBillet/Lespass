import logging
from typing import Any

from django import forms
from django.contrib import admin, messages
from django.db import connection
from django.forms import Form
from django.http import HttpResponse, HttpRequest, HttpResponseRedirect
from django.shortcuts import redirect
from django.template.loader import render_to_string
from django.urls import path, reverse
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from django.core.signing import TimestampSigner
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST
from rest_framework_api_key.models import APIKey
from unfold.admin import ModelAdmin
from unfold.contrib.forms.widgets import WysiwygWidget
from django.db import models
from solo.admin import SingletonModelAdmin
import segno

from Administration.admin.dashboard import MODULE_FIELDS, _build_modules_context
from Administration.admin.site import staff_admin_site, sanitize_textfields
from ApiBillet.permissions import TenantAdminPermissionWithRequest
from BaseBillet.models import (
    Configuration, ExternalApiKey, Webhook, ScanApp, Membership, Reservation
)
from BaseBillet.tasks import webhook_reservation, webhook_membership

logger = logging.getLogger(__name__)


@admin.register(ExternalApiKey, site=staff_admin_site)
class ExternalApiKeyAdmin(ModelAdmin):
    compressed_fields = True
    warn_unsaved_form = True

    list_display = [
        'name',
        'user',
        'created',
        'event',
        'product',
        'reservation',
        'ticket',
        'wallet',
        'sale',
    ]

    fields = [
        'name',
        'ip',
        'created',
        # Les boutons de permissions :
        ('event', 'product',),
        ('reservation', 'ticket'),
        ('wallet', 'sale'),
        'user',
        'key',
    ]

    readonly_fields = [
        'created',
        'user',
        'key',
    ]

    def save_model(self, request: HttpRequest, obj: ExternalApiKey, form: Form, change: Any) -> None:
        if not obj.pk and not obj.key and obj.name:

            # On affiche la string Key sur l'admin de django en message
            # et django.message capitalize chaque message...
            # du coup on fait bien gaffe à ce que je la clée générée ai bien une majusculle au début ...
            api_key, key = APIKey.objects.create_key(name=obj.name)
            while key[0].isupper() == False:
                api_key, key = APIKey.objects.create_key(name=obj.name)
                if key[0].isupper() == False:
                    api_key.delete()

            messages.add_message(
                request,
                messages.SUCCESS,
                _(f"Copy this key and save it somewhere safe! It will not be saved on our servers and can only be displayed this one time.")
            )
            messages.add_message(
                request,
                messages.WARNING,
                f"{key}"
            )
            obj.key = api_key
            obj.user = request.user
        super().save_model(request, obj, form, change)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


@admin.register(ScanApp, site=staff_admin_site)
class ScanAppAdmin(ModelAdmin):
    compressed_fields = True
    warn_unsaved_form = True
    list_before_template = "admin/scanapp/list_before.html"

    list_display = [
        'name',
        'claimed',
        'archive',
    ]

    fields = [
        'name',
        'archive',
        'pairing_code',
    ]

    readonly_fields = [
        'pairing_code',
    ]

    def pairing_code(self, obj):
        if obj.pk and obj.name and not obj.claimed:
            base_url = f"https://{connection.tenant.get_primary_domain().domain}"

            signer = TimestampSigner()
            token = urlsafe_base64_encode(signer.sign(f"{obj.uuid}").encode('utf8'))
            qrcode_data = f"{base_url}/scan/{token}/pair"

            logger.info(qrcode_data)

            ### VERIFICATION SIGNATURE AVANT D'ENVOYER
            scanapp_uuid = signer.unsign(urlsafe_base64_decode(token).decode('utf8'), max_age=(300))  # 5 min
            sc = ScanApp.objects.get(uuid=scanapp_uuid)
            if not obj == sc:
                raise Exception("signature check error")

            # Generate QR code using segno
            qr = segno.make(qrcode_data)

            # Get SVG as string with white background
            svg_string = qr.svg_inline(scale=4, light="white")

            # Use mark_safe for the SVG content to prevent escaping
            return format_html(f'{mark_safe(svg_string)}')
        elif obj.pk and obj.name and obj.claimed:
            return "Claimed"
        return "Sauvegarder pour afficher le qr code de pairing. ( bouton Enregistrer et continuer les modifications )"

    pairing_code.short_description = _("Pairing Code")

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


@admin.register(Webhook, site=staff_admin_site)
class WebhookAdmin(ModelAdmin):
    compressed_fields = True
    warn_unsaved_form = True

    readonly_fields = ['last_response', ]
    fields = [
        "url",
        "event",
        "active",
        "last_response",
    ]

    list_display = [
        "url",
        "event",
        "active",
        "last_response",
    ]

    actions_detail = ["test_webhook"]

    from unfold.decorators import action

    @action(
        description=_("Test"),
        url_path="test_webhook",
        permissions=["custom_actions_detail"],
    )
    def test_webhook(self, request, object_id):
        # import ipdb; ipdb.set_trace()
        # Lancement d'un test de webhook :
        webhook = Webhook.objects.get(pk=object_id)
        try:
            if webhook.event == Webhook.MEMBERSHIP_V:
                # On va chercher le membership le plus récent
                membership = Membership.objects.filter(contribution_value__isnull=False).first()
                webhook_membership(membership.pk)
                webhook.refresh_from_db()
            elif webhook.event == Webhook.RESERVATION_V:
                # On va chercher le membership le plus récent
                reservation = Reservation.objects.filter(status=Reservation.VALID).first()
                webhook_reservation(reservation.pk)
                webhook.refresh_from_db()

            messages.info(
                request,
                f"{webhook.last_response}",
            )
            return redirect(request.META["HTTP_REFERER"])

        except Exception as e:
            messages.error(
                request,
                f"{e}",
            )

    def has_custom_actions_detail_permission(self, request, object_id):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


@admin.register(Configuration, site=staff_admin_site)
class ConfigurationAdmin(SingletonModelAdmin, ModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False

    # form = ConfigurationAdminForm

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.select_related('postal_address').prefetch_related(
            'federated_with',
            # 'option_generale_radio',
            # 'option_generale_checkbox'
        )

    fieldsets = (
        (None, {
            'fields': (
                'organisation',
                'short_description',
                'long_description',
                'img',
                'logo',
                'postal_address',
                # 'adress',
                'phone',
                'email',
                'site_web',
                'skin',
            )
        }),
        ('Options générales', {
            'fields': (
                'fuseau_horaire',
                'language',
                'jauge_max',
                'allow_concurrent_bookings',
                'currency_code',
            ),
        }),
        ('Personnalisation', {
            'fields': (
                'event_menu_name',
                'membership_menu_name',
                'description_membership_page',
                'description_event_page',
                'first_input_label_membership',
                'second_input_label_membership',
                'additional_text_in_membership_mail',
            ),
        }),
        ('Stripe', {
            'fields': (
                # 'vat_taxe',
                'onboard_stripe',
                'stripe_invoice',
                'stripe_accept_sepa',
            ),
        }),
        # ('Danger !', {
        #     'fields': (
        #         'domain_name',  # Virtual field to set slug
        #     ),
        # }),
    )

    readonly_fields = ['onboard_stripe', ]
    autocomplete_fields = ['federated_with', ]

    formfield_overrides = {
        models.TextField: {
            "widget": WysiwygWidget,
        }
    }

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'module-toggle-modal/<str:field_name>/',
                self.admin_site.admin_view(self.module_toggle_modal),
                name='configuration-module-modal',
            ),
            path(
                'module-toggle/<str:field_name>/',
                self.admin_site.admin_view(csrf_protect(require_POST(self.module_toggle))),
                name='configuration-module-toggle',
            ),
        ]
        return custom_urls + urls

    def module_toggle_modal(self, request, field_name):
        """HTMX GET : renvoie le modal de confirmation pour activer/desactiver un module."""
        if field_name not in MODULE_FIELDS:
            return HttpResponse("", status=400)

        configuration = Configuration.get_solo()
        is_active = getattr(configuration, field_name)
        module_name = str(MODULE_FIELDS[field_name]["name"])

        toggle_url = reverse(
            'staff_admin:configuration-module-toggle',
            args=[field_name],
        )

        html = render_to_string(
            'admin/dashboard_module_modal.html',
            {
                "module_name": module_name,
                "is_active": is_active,
                "toggle_url": toggle_url,
                "csrf_token": request.META.get("CSRF_COOKIE", ""),
            },
            request=request,
        )
        return HttpResponse(html)

    def module_toggle(self, request, field_name):
        """HTMX POST : bascule un module et renvoie les cartes mises a jour."""
        if field_name not in MODULE_FIELDS:
            return HttpResponse("", status=400)

        configuration = Configuration.get_solo()
        current_value = getattr(configuration, field_name)
        setattr(configuration, field_name, not current_value)
        configuration.full_clean()
        configuration.save()

        # HX-Refresh force un reload complet : la sidebar se met a jour
        response = HttpResponse("")
        response["HX-Refresh"] = "true"
        return response

    def save_model(self, request, obj, form, change):
        obj: Configuration
        # Sanitize all TextField inputs to avoid XSS via WYSIWYG/TextField
        sanitize_textfields(obj)

        if obj.server_cashless and obj.key_cashless:
            if obj.check_serveur_cashless():
                messages.add_message(request, messages.INFO, _(f"Cashless server ONLINE"))
            else:
                messages.add_message(request, messages.ERROR, _("Cashless server OFFLINE or BAD KEY"))

        super().save_model(request, obj, form, change)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return False
