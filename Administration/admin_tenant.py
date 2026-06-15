from Administration.admin.dashboard import (  # noqa: F401
    dashboard_callback, environment_callback, get_sidebar_navigation,
    MODULE_FIELDS, _build_modules_context, adhesion_badge_callback,
)

from Administration.admin import (
    products,
    prices
)
from Administration.admin.help_messages_dictionnary import HELP_MESSAGES_DICT
from Administration.admin.mixins import HelpDisplayMixin

from Administration.admin.site import staff_admin_site, sanitize_textfields


import json
import logging
import re
from datetime import timedelta
from decimal import Decimal
from typing import Any, Optional, Dict
from urllib.parse import urlencode
from uuid import UUID, uuid4
from unfold.utils import parse_datetime_str
from django.core.validators import EMPTY_VALUES
from collections.abc import Iterator
from django.urls import path, reverse, NoReverseMatch

from django.contrib import admin
from django.contrib.admin.options import ModelAdmin
from django.contrib.admin.views.main import ChangeList
from django.core.validators import EMPTY_VALUES
from django.db.models import Model, QuerySet
from django.db.models.fields import DateField, DateTimeField, Field
from django.forms import ValidationError
from django.http import HttpRequest

from unfold.contrib.filters.forms import RangeDateForm, RangeDateTimeForm
from unfold.utils import parse_date_str, parse_datetime_str

import requests
import segno
from django import forms
from django.conf import settings
from django.contrib import admin
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.signing import TimestampSigner
from django.db import models, connection, IntegrityError, transaction as db_transaction
from django.db.models import Model, Count, Q, Prefetch, F
from django.forms import ModelForm, Form, HiddenInput
from django.http import HttpResponse, HttpRequest, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.shortcuts import redirect, get_object_or_404
from django.template.defaultfilters import slugify
from django.template.loader import render_to_string
from django.urls import reverse, re_path
from django.utils import timezone
from django.utils.html import format_html
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST
from django_htmx.http import HttpResponseClientRedirect
from django_tenants.utils import tenant_context
from import_export.admin import ImportExportModelAdmin, ExportActionModelAdmin
from import_export import resources, fields
from import_export.widgets import ForeignKeyWidget
from rest_framework import status
from rest_framework.response import Response
from rest_framework_api_key.models import APIKey
from solo.admin import SingletonModelAdmin
from unfold.admin import ModelAdmin, TabularInline
from unfold.components import register_component, BaseComponent
from unfold.contrib.filters.admin import (
    # AutocompleteSelectMultipleFilter,
    # ChoicesDropdownFilter,
    # MultipleRelatedDropdownFilter,
    # RangeDateFilter,
    RangeDateTimeFilter,
    # RangeNumericFilter,
    # SingleNumericFilter,
    # TextFilter,
)
from unfold.contrib.forms.widgets import WysiwygWidget
from unfold.contrib.import_export.forms import ExportForm, ImportForm
from unfold.decorators import display, action
from unfold.sections import TableSection, TemplateSection
from unfold.sites import UnfoldAdminSite
from unfold.widgets import (
    UnfoldAdminCheckboxSelectMultiple,
    UnfoldAdminEmailInputWidget,
    UnfoldAdminRadioSelectWidget,
    UnfoldAdminColorInputWidget,
    UnfoldAdminSelectWidget,
    UnfoldAdminTextInputWidget,
    UnfoldBooleanSwitchWidget,
    UnfoldAdminSelect2Widget
)

from Administration.importers.ticket_exporter import TicketExportResource
from Administration.importers.lignearticle_exporter import LigneArticleExportResource
from Administration.utils import clean_html
from ApiBillet.permissions import TenantAdminPermissionWithRequest, RootPermissionWithRequest
from ApiBillet.serializers import get_or_create_price_sold, dec_to_int
from AuthBillet.models import HumanUser, TibilletUser, Wallet
from AuthBillet.utils import get_or_create_user
from BaseBillet.models import Configuration, OptionGenerale, Product, Price, Paiement_stripe, Membership, Webhook, Tag, \
    LigneArticle, PaymentMethod, Reservation, ExternalApiKey, GhostConfig, Event, Ticket, PriceSold, SaleOrigin, \
    FormbricksConfig, FormbricksForms, FederatedPlace, PostalAddress, Carrousel, BrevoConfig, ScanApp, ProductFormField, \
    PromotionalCode, Tva, MembershipProduct, FederationConfiguration
from BaseBillet.tasks import webhook_reservation, \
    webhook_membership, create_ticket_pdf, ticket_celery_mailer, send_ticket_cancellation_user, \
    send_reservation_cancellation_user, send_sale_to_laboutik, forge_connexion_url
from Customers.models import Client
from MetaBillet.models import WaitingConfiguration
from crowds.models import Contribution, Vote, Participation, CrowdConfig, Initiative, BudgetItem
from fedow_connect.fedow_api import FedowAPI
from fedow_connect.models import FedowConfig
from fedow_connect.utils import dround
from fedow_public.models import AssetFedowPublic as Asset, AssetFedowPublic

# from simple_history.admin import SimpleHistoryAdmin
from stripe._error import InvalidRequestError

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
        # membership : requis pour que LaBoutik lise les adhesions (route by-wallet).
        # / membership: required so LaBoutik can read memberships (by-wallet route).
        ('membership', 'crowd'),
        # Recharge cadeau : asset TNF que cette cle peut crediter via l'API v2
        # / Gift refill: TNF asset this key may top-up via API v2
        'gift_asset',
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
        new_value = getattr(configuration, field_name)

        if field_name == "module_monnaie_locale" and not new_value and configuration.module_caisse:
            messages.add_message(request, messages.ERROR, _("The \"POS & restaurant\" module required this module. You must disable it before disabling "))
            setattr(configuration, field_name, current_value)

        if field_name == "module_caisse" and new_value and not configuration.module_monnaie_locale:
            messages.add_message(request, messages.ERROR, _("The \"Local currency & cashless\" module is required by this module. You must enabled it before"))
            setattr(configuration, field_name, current_value)


        configuration.clean()

        # Configuration.save() peut lever ValidationError (ex: SEPA pas actif cote Stripe).
        # Sans ce try/except, l'exception remonte en 500 silencieux cote HTMX.
        # On capture comme ConfigurationAdmin.save_model() le fait deja plus haut.
        # / Configuration.save() may raise ValidationError (e.g. SEPA not active on Stripe).
        # / Without this guard, the exception bubbles up as a silent 500 over HTMX.
        try:
            configuration.save()
        except ValidationError as e:
            error_message = e.message if hasattr(e, "message") else str(e)
            messages.error(request, error_message)

        # HX-Refresh force un reload complet : la sidebar se met a jour
        # et les messages d'erreur eventuels apparaissent en toast.
        # / HX-Refresh forces a full reload: sidebar updates and any error
        # / messages show up as toast notifications.
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

        try:
            super().save_model(request, obj, form, change)
        except ValidationError as e:
            # Le ValidationError vient de Configuration.save() (ex: SEPA pas activé dans Stripe)
            # On le transforme en message d'erreur admin au lieu d'un 500
            # / ValidationError from Configuration.save() (e.g. SEPA not active in Stripe)
            # / Convert to admin error message instead of 500
            messages.error(request, e.message)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return False


class TagForm(ModelForm):
    class Meta:
        model = Tag
        fields = '__all__'
        widgets = {
            'color': UnfoldAdminColorInputWidget(),
        }


@admin.register(Carrousel, site=staff_admin_site)
class CarrouselAdmin(ModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False
    ordering = ('order', 'name')
    list_display = ('name', 'on_event_list_page', 'order', 'link', 'events_names')
    list_editable = ('on_event_list_page', 'order')

    search_fields = ('name',)

    @display(description=_("Included in events"))
    def events_names(self, instance: Carrousel):
        return ", ".join([event.name for event in instance.events.all()])

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


@admin.register(Tag, site=staff_admin_site)
class TagAdmin(ModelAdmin):
    compressed_fields = True  # Default: False 
    warn_unsaved_form = True  # Default: False

    actions_list = ["sync_tags_action"]

    form = TagForm
    fields = ("name", "color")
    list_display = [
        "name",
        "_color",
    ]
    readonly_fields = ['uuid', ]
    search_fields = ['name']

    def _color(self, obj):
        # Add link to change page around color div
        return format_html(
            '<a href="{url}">'
            '<div style="width: 20px; height: 20px; background-color: {color}; border: 1px solid #000;"></div>'
            '</a>',
            url=reverse('staff_admin:BaseBillet_tag_change', args=[obj.pk]),
            color=obj.color,
        )

    _color.short_description = _("Color")

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_sync_tags_action_permission(self, request):
        return TenantAdminPermissionWithRequest(request)

    @action(
        description=_("Synchronize tags"),
        url_path="sync_tags",
        permissions=["sync_tags_action"],
    )
    def sync_tags_action(self, request):
        current_tenant = connection.tenant

        # 1. Identifier les parents (ceux qui nous fédèrent)
        # On utilise une requête SQL optimisée pour éviter 600 changements de contexte
        from django.db import connection as db_connection
        cursor = db_connection.cursor()

        # On récupère les schémas possédant la table FederatedPlace
        cursor.execute("SELECT table_schema FROM information_schema.tables WHERE table_name = 'BaseBillet_federatedplace'")
        schemas_with_fed = {row[0] for row in cursor.fetchall()}

        # On exclut le public, le nôtre et les schémas système
        schemas_to_check = [s for s in schemas_with_fed if s not in ['public', 'information_schema', 'pg_catalog', current_tenant.schema_name]]

        parents_pks = []
        if schemas_to_check:
            batch_size = 50
            for i in range(0, len(schemas_to_check), batch_size):
                batch = schemas_to_check[i:i + batch_size]
                query_parts = []
                params = []
                for schema in batch:
                    query_parts.append(f'SELECT %s WHERE EXISTS (SELECT 1 FROM "{schema}"."BaseBillet_federatedplace" WHERE tenant_id = %s)')
                    params.extend([schema, current_tenant.pk])

                if query_parts:
                    full_query = " UNION ALL ".join(query_parts)
                    cursor.execute(full_query, params)
                    for row in cursor.fetchall():
                        parents_pks.append(row[0])

        parents = list(Client.objects.filter(schema_name__in=parents_pks))

        # 2. Identifier les enfants (ceux que nous fédérons)
        children = [fp.tenant for fp in FederatedPlace.objects.all().select_related('tenant')]

        # Combiner et dédupliquer en gardant l'ordre (parents d'abord)
        seen = {current_tenant.pk}
        tenants_to_sync = []
        for t in parents + children:
            if t.pk not in seen:
                tenants_to_sync.append(t)
                seen.add(t.pk)

        # 3. Collecter tous les tags distants en une seule fois
        all_remote_tags = {}
        if tenants_to_sync:
            # On vérifie quels schémas ont la table Tag
            cursor.execute("SELECT table_schema FROM information_schema.tables WHERE table_name = 'BaseBillet_tag'")
            schemas_with_tags = {row[0] for row in cursor.fetchall()}

            schemas_to_fetch = [t.schema_name for t in tenants_to_sync if t.schema_name in schemas_with_tags]

            if schemas_to_fetch:
                batch_size = 50
                for i in range(0, len(schemas_to_fetch), batch_size):
                    batch = schemas_to_fetch[i:i + batch_size]
                    query_parts = []
                    for schema in batch:
                        query_parts.append(f'SELECT name, color FROM "{schema}"."BaseBillet_tag"')

                    full_query = " UNION ALL ".join(query_parts)
                    cursor.execute(full_query)
                    for name, color in cursor.fetchall():
                        # Le dernier rencontré gagne (priorité aux enfants sur les parents si conflit)
                        all_remote_tags[name] = color

        # 4. Appliquer les changements localement en masse
        local_tags = {t.name: t for t in Tag.objects.all()}
        tags_created = 0
        tags_updated = 0

        to_create = []
        to_update = []

        for name, color in all_remote_tags.items():
            cleaned_color = Tag._clean_hex(color, "#0dcaf0")
            if name in local_tags:
                tag = local_tags[name]
                if tag.color != cleaned_color:
                    tag.color = cleaned_color
                    to_update.append(tag)
            else:
                to_create.append(Tag(
                    uuid=uuid4(),
                    name=name,
                    slug=slugify(name),
                    color=cleaned_color
                ))

        if to_create:
            Tag.objects.bulk_create(to_create)
            tags_created = len(to_create)

        if to_update:
            Tag.objects.bulk_update(to_update, ['color'])
            tags_updated = len(to_update)

        messages.success(request, _("Synchronization complete: {} tags created, {} tags updated.").format(tags_created, tags_updated))
        return redirect(request.META.get("HTTP_REFERER", reverse("staff_admin:BaseBillet_tag_changelist")))

"""

@admin.register(OptionGenerale, site=staff_admin_site)
class OptionGeneraleAdmin(ModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False
    search_fields = ('name',)
    list_display = (
        'name',
        'poids',
    )

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)
"""


@admin.register(Paiement_stripe, site=staff_admin_site)
class PaiementStripeAdmin(ModelAdmin):
    compressed_fields = True  # Default: False

    list_display = (
        'user',
        'order_date',
        'status',
        # 'traitement_en_cours',
        'source_traitement',
        'source',
        'articles',
        'total',
        'uuid_8',
    )
    readonly_fields = list_display
    ordering = ('-order_date',)
    search_fields = ('user__email', 'order_date')
    list_filter = ('status', 'order_date',)

    def has_delete_permission(self, request, obj=None):
        # return request.user.is_superuser
        return False

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return True


"""
USER
"""


class is_tenant_admin_filter(admin.SimpleListFilter):
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


class can_init_paiement_filter(admin.SimpleListFilter):
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


# ---------------------------------------------------------------------------
# Badges de statut pour la fiche utilisateur (évènements + adhésions).
# Styles inline (hex) : le bundle Unfold n'inclut pas toutes les classes Tailwind ;
# un fond saturé + texte blanc reste lisible en thème clair comme sombre.
# Helpers AU NIVEAU MODULE (hors classe) — Unfold wrappe les méthodes des ModelAdmin.
# / Status badges for the user profile. Inline hex styles, readable in light/dark.
# Module-level helpers (NOT inside the admin class) — Unfold wraps ModelAdmin methods.
# ---------------------------------------------------------------------------
BADGE_VERT = ("#16a34a", "#ffffff")    # validé / payé
BADGE_BLEU = ("#2563eb", "#ffffff")    # gratuit / en ligne
BADGE_AMBRE = ("#d97706", "#ffffff")   # en attente / non payé
BADGE_ROUGE = ("#dc2626", "#ffffff")   # annulé
BADGE_GRIS = ("#6b7280", "#ffffff")    # autre


def _badge_couleur_reservation(status_code):
    """Couleur (fond, texte) du badge selon le statut de réservation.
    / Badge color (bg, fg) for a booking status."""
    if status_code in (Reservation.VALID, Reservation.PAID,
                       Reservation.PAID_NOMAIL, Reservation.PAID_ERROR):
        return BADGE_VERT
    if status_code in (Reservation.FREERES, Reservation.FREERES_USERACTIV):
        return BADGE_BLEU
    if status_code in (Reservation.CREATED, Reservation.UNPAID):
        return BADGE_AMBRE
    if status_code == Reservation.CANCELED:
        return BADGE_ROUGE
    return BADGE_GRIS


def _badge_couleur_adhesion(est_valide, status_code):
    """Couleur (fond, texte) du badge selon l'état d'adhésion.
    / Badge color (bg, fg) for a membership state."""
    if est_valide:
        return BADGE_VERT
    if status_code in (Membership.CANCELED, Membership.ADMIN_CANCELED):
        return BADGE_ROUGE
    return BADGE_GRIS


def _admin_url_basebillet(model_name, pk):
    """URL admin de modification d'un objet BaseBillet, ou None si introuvable.
    / Admin change URL for a BaseBillet object, or None if not found."""
    try:
        return reverse(f"staff_admin:BaseBillet_{model_name}_change", args=[pk])
    except NoReverseMatch:
        return None


# Statuts de ligne considérés comme "payés" (cf Reservation.articles_paid).
# / Line statuses considered "paid".
LIGNE_PAYEE_STATUTS = (LigneArticle.PAID, LigneArticle.VALID, LigneArticle.REFUNDED)


def _lignes_payees_prefetch(reservation):
    """Lignes payées/confirmées/remboursées d'une réservation, en exploitant les
    relations préchargées (prefetch_related) : zéro requête par réservation.
    Réplique la logique de Reservation.articles_paid() mais en mémoire — la méthode
    du modèle, elle, fait un .filter() (donc une requête) à chaque appel.
    / Prefetch-aware version of Reservation.articles_paid() — no per-row query.
    """
    # Lignes liées directement à la réservation (données récentes)
    # / Lines linked directly to the reservation (recent data)
    lignes_directes = [
        ligne for ligne in reservation.lignearticles.all()
        if ligne.status in LIGNE_PAYEE_STATUTS
    ]
    if lignes_directes:
        return lignes_directes

    # Fallback : anciennes lignes liées via le paiement Stripe
    # / Fallback: legacy lines linked via the Stripe payment
    lignes_legacy = []
    for paiement in reservation.paiements.all():
        lignes_legacy += [
            ligne for ligne in paiement.lignearticles.all()
            if ligne.status in LIGNE_PAYEE_STATUTS
        ]
    return lignes_legacy


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
        # Nom / prénom / email portés par l'user lui-même
        # / Name / first name / email carried by the user itself
        'email',
        'first_name',
        'last_name',
        # Nom / prénom saisis sur les adhésions de l'user (souvent l'adhérent·e
        # réel·le, parfois différent de l'user). Django ajoute distinct() au besoin.
        # / Name / first name entered on the user's memberships (the actual member,
        # sometimes different from the account user). Django adds distinct() if needed.
        'memberships__first_name',
        'memberships__last_name',
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
        is_tenant_admin_filter,
        can_init_paiement_filter,
        "email_valid",
    ]

    def changeform_view(self, request: HttpRequest, object_id: Optional[str] = None, form_url: str = "",
                        extra_context: Optional[Dict[str, bool]] = None) -> Any:
        extra_context = extra_context or {}
        extra_context['object_id'] = object_id
        if object_id:
            # Bloc 1 — états initiaux des toggles de droits.
            # Conserve le comportement existant : re-lève une erreur inattendue.
            # / Rights toggles initial states. Keeps existing behaviour (re-raises).
            try:
                user = TibilletUser.objects.get(pk=object_id)
                tenant = connection.tenant
                extra_context['is_client_admin'] = user.client_admin.filter(pk=tenant.pk).exists()
                extra_context['can_initiate_payment'] = user.initiate_payment.filter(pk=tenant.pk).exists()
                extra_context['can_create_event'] = user.create_event.filter(pk=tenant.pk).exists()
                extra_context['can_manage_crowd'] = user.manage_crowd.filter(pk=tenant.pk).exists()
            except HumanUser.DoesNotExist:
                extra_context['is_client_admin'] = False
                extra_context['can_initiate_payment'] = False
                extra_context['can_create_event'] = False
                extra_context['can_manage_crowd'] = False
            except ValidationError:
                # Requete POST pour les actions (object_id pas un uuid) : on ignore.
                # / POST for actions (object_id not a uuid): ignore.
                pass
            except Exception as e:
                raise e

            # Bloc 2 — évènements + adhésions (tenant courant), préparés en listes de
            # dictionnaires. ISOLÉ dans son propre try/except : un cas de données
            # limite ne doit JAMAIS faire planter (500) la fiche utilisateur — on
            # logge et on affiche la page sans (ou avec moins d') encarts.
            # / Bookings + memberships. Isolated try/except: an edge case must never
            # 500 the user change page; we log and render the page anyway.
            try:
                user = TibilletUser.objects.get(pk=object_id)
                extra_context['devise'] = Configuration.get_solo().currency_code
                maintenant = timezone.now()

                # Prefetch des relations : nombre de requêtes constant (pas de N+1).
                # Tri NULLS LAST : les réservations sans évènement ne remontent pas en tête.
                # / Prefetch relations (no N+1); NULLS LAST so event-less bookings stay last.
                reservations = (
                    Reservation.objects
                    .filter(user_commande=user)
                    .select_related('event')
                    .prefetch_related('tickets', 'lignearticles', 'paiements__lignearticles')
                    .order_by(F('event__datetime').desc(nulls_last=True))
                )
                evenements_a_venir = []
                evenements_passes = []
                for reservation in reservations:
                    badge_fond, badge_texte = _badge_couleur_reservation(reservation.status)
                    # Lignes payées calculées UNE seule fois sur les relations préchargées.
                    # / Paid lines computed once from prefetched relations.
                    lignes_payees = _lignes_payees_prefetch(reservation)
                    montant_paye = dround(sum(int(ligne.amount * ligne.qty) for ligne in lignes_payees))
                    moyens_de_paiement = sorted({
                        ligne.get_payment_method_display()
                        for ligne in lignes_payees
                        if ligne.payment_method
                    })
                    date_evenement = reservation.event.datetime if reservation.event else None
                    if date_evenement and date_evenement >= maintenant:
                        liste_cible = evenements_a_venir
                    else:
                        liste_cible = evenements_passes
                    liste_cible.append({
                        'nom': reservation.event.name if reservation.event else _("(évènement supprimé)"),
                        'date': date_evenement,
                        'nb_billets': len(reservation.tickets.all()),
                        'montant': montant_paye,
                        'moyens': ", ".join(moyens_de_paiement),
                        'statut': reservation.get_status_display(),
                        'badge_fond': badge_fond,
                        'badge_texte': badge_texte,
                        'url': _admin_url_basebillet('reservation', reservation.pk),
                    })
                extra_context['evenements_a_venir'] = evenements_a_venir
                extra_context['evenements_passes'] = evenements_passes

                adhesions = (
                    Membership.objects
                    .filter(user=user)
                    .select_related('price', 'price__product')
                    .order_by('-deadline')
                )
                adhesions_en_cours = []
                adhesions_passees = []
                for adhesion in adhesions:
                    est_valide = adhesion.is_valid()
                    badge_fond, badge_texte = _badge_couleur_adhesion(est_valide, adhesion.status)
                    if est_valide:
                        liste_cible = adhesions_en_cours
                    else:
                        liste_cible = adhesions_passees
                    liste_cible.append({
                        'produit': adhesion.product_name() or "—",
                        'tarif': adhesion.price_name() or "",
                        'montant': adhesion.contribution_value,
                        'moyen': adhesion.get_payment_method_display() if adhesion.payment_method else "",
                        'deadline': adhesion.deadline,
                        'statut': _("En cours") if est_valide else adhesion.get_status_display(),
                        'badge_fond': badge_fond,
                        'badge_texte': badge_texte,
                        'url': _admin_url_basebillet('membership', adhesion.pk),
                    })
                extra_context['adhesions_en_cours'] = adhesions_en_cours
                extra_context['adhesions_passees'] = adhesions_passees
            except Exception as erreur_encarts:
                logger.error(
                    f"HumanUserAdmin : encarts évènements/adhésions indisponibles "
                    f"pour {object_id} : {erreur_encarts}"
                )

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
            base_url = "https://tibillet.coop"

        connexion_url = forge_connexion_url(user, base_url)
        return redirect(connexion_url)


### ADHESION

from Administration.importers.membership_importers import (
    MembershipExportResource,
    MembershipImportResource
)


# from Administration.importers.event_importers import PostalAddressForeignKeyWidget
class MembershipAddForm(ModelForm):
    '''
    Formulaire d'ajout d'adhésion sur l'interface d'administration.
    '''

    # Un formulaire d'email qui va générer les action get_or_create_user
    email = forms.EmailField(
        required=True,
        widget=UnfoldAdminEmailInputWidget(),  # attrs={"placeholder": "Entrez l'adresse email"}
        label="Email",
    )

    # Uniquement les tarif Adhésion
    # / Only membership prices
    price = forms.ModelChoiceField(
        queryset=Price.objects.filter(
            product__categorie_article=Product.ADHESION, product__archive=False
        ).select_related('product', 'fedow_reward_asset').order_by("-free_price","name"),
        # Remplis le champ select avec les objets Price
        # / Fills the select with Price objects
        empty_label=_("Select an subscription"),  # Texte affiché par défaut
        required=True,
        widget=UnfoldAdminSelectWidget(),
        label=_("Subscriptions"),
        help_text=_("Si un déclencheur de tokens est configuré sur le tarif, il sera activé à l'enregistrement du paiement. Une ligne comptable sera aussi créée dans les Ventes."),
    )

    # Fabrication au cas ou = 0
    contribution = forms.FloatField(
        required=False,
        widget=UnfoldAdminTextInputWidget(),  # attrs={"placeholder": "Entrez l'adresse email"}
        label=_("Contribution (€)"),
    )

    payment_method = forms.ChoiceField(
        required=False,
        choices=PaymentMethod.classic(),  # on retire les choix stripe
        widget=UnfoldAdminSelectWidget(),  # attrs={"placeholder": "Entrez l'adresse email"}
        label=_("Payment method"),
    )

    card_number = forms.CharField(
        required=False,
        min_length=8,
        max_length=8,
        label=_("Card number"),
        # validators=[validate_hex8],
        widget=UnfoldAdminTextInputWidget(),
    )

    class Meta:
        model = Membership
        fields = [
            'last_name',
            'first_name',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Affiche l'info du déclencheur tokens dans le label du select
        # / Shows token trigger info in the select label
        def _label_price_avec_declencheur(price_obj):
            label = str(price_obj)
            if price_obj.fedow_reward_enabled and price_obj.fedow_reward_asset and price_obj.fedow_reward_amount:
                label += f" ⚡ +{price_obj.fedow_reward_amount} {price_obj.fedow_reward_asset.name}"
            return label

        self.fields['price'].label_from_instance = _label_price_avec_declencheur

    def clean_email(self):
        cleaned_data = self.cleaned_data
        email = cleaned_data.get('email')
        user = get_or_create_user(email, send_mail=False)
        self.fedowAPI = FedowAPI()
        self.fedowAPI.wallet.get_or_create_wallet(user)
        self.user_wallet_serialized = self.fedowAPI.wallet.cached_retrieve_by_signature(user).validated_data
        return email

    def clean_card_number(self):
        cleaned_data = self.cleaned_data
        card_number = cleaned_data.get('card_number')
        if card_number:

            # Si clean_email a echoue, le wallet n'existe pas encore — on ne peut pas valider la carte
            # If clean_email failed, the wallet doesn't exist yet — we can't validate the card
            if not hasattr(self, 'user_wallet_serialized'):
                raise forms.ValidationError(_("Please provide a valid email address first."))

            if self.user_wallet_serialized.get('has_user_card'):
                raise forms.ValidationError(_("A card is already linked to this email address."))

            if not re.match(r'^[0-9A-Fa-f]{8}$', card_number):
                raise forms.ValidationError(_("Card number must be exactly 8 hexadecimal characters."))

            fedowApi = FedowAPI()
            card_serialized = fedowApi.NFCcard.card_number_retrieve(card_number)

            if not card_serialized:
                raise forms.ValidationError(_("Unknown card number"))
            if not card_serialized.get('is_wallet_ephemere'):
                raise forms.ValidationError(_("This card is already linked to a user."))

            self.card_serialized = card_serialized
        self.card_number = card_number
        return card_number

    def clean(self):
        # On vérifie que le moyen de paiement est bien entré si > 0
        cleaned_data = self.cleaned_data
        if cleaned_data.get("contribution"):
            if cleaned_data.get("contribution") > 0 and cleaned_data.get("payment_method") == PaymentMethod.FREE:
                raise forms.ValidationError(_("Please add a payment method for the contribution."),
                                            code="invalid")

        if cleaned_data.get("payment_method") != PaymentMethod.FREE:
            if not cleaned_data.get("contribution"):
                raise forms.ValidationError(_("Please fill in the value of the contribution."), code="invalid")
            if not cleaned_data.get("contribution") > 0:
                raise forms.ValidationError(_("Please fill in a positive value of the contribution."), code="invalid")

        return super().clean()

    def save(self, commit=True):
        self.instance: Membership
        # On indique que l'adhésion a été créé sur l'admin
        self.instance.status = Membership.ADMIN

        # Associez l'utilisateur au champ 'user' du formulaire
        email = self.cleaned_data.pop('email')
        user = get_or_create_user(email)

        self.instance.user = user

        # Numéro de carte saisi (8 hexa) -> enregistré sur l'adhésion
        # card_number = self.cleaned_data.get('card_number')
        # if card_number:
        #     self.instance.card_number = card_number

        # Flotant (FALC) vers Decimal
        contribution = self.cleaned_data.pop('contribution')
        self.instance.contribution_value = dround(Decimal(contribution)) if contribution else 0

        # Mise à jour des dates de contribution :
        self.instance.first_contribution = timezone.localtime()
        self.instance.last_contribution = timezone.localtime()
        # self.instance.set_deadline()

        if self.card_number:
            # Ne lier la carte chez Fedow QU'APRES le commit de la transaction.
            # L'admin Django appelle form.save() AVANT de valider les inlines :
            # si un formset est invalide, la transaction DB est annulee mais un
            # appel HTTP deja parti vers Fedow ne peut pas l'etre — la carte
            # serait liee chez Fedow sans adhesion cote Lespass.
            # (Bug trouve par tests/pytest/test_membership_card_wallet_fedow.py)
            # / Only link the card on Fedow AFTER the DB transaction commits.
            # Django admin calls form.save() BEFORE validating inlines: on an
            # invalid formset the DB transaction rolls back, but an HTTP call
            # already sent to Fedow cannot — the card would be linked on Fedow
            # with no membership on the Lespass side.
            utilisateur_a_lier = user
            numero_carte_a_lier = self.card_number
            fedow_api = self.fedowAPI
            db_transaction.on_commit(
                lambda: fedow_api.NFCcard.linkwallet_card_number(
                    user=utilisateur_a_lier,
                    card_number=numero_carte_a_lier,
                )
            )

        # Le post save BaseBillet.signals.create_lignearticle_if_membership_created_on_admin s'executera
        # # Création de la ligne Article vendu qui envera à la caisse si besoin
        return super().save(commit=commit)


class MembershipChangeForm(ModelForm):
    # Le formulaire pour changer une adhésion
    class Meta:
        model = Membership
        fields = (
            'last_name',
            'first_name',
            'deadline',
            'commentaire',
            'newsletter',
        )



class MembershipStatusFilter(admin.SimpleListFilter):
    title = _("Statut d'adhésion (par défaut filtré)")
    parameter_name = "membership_status"

    def lookups(self, request, model_admin):
        return [
            ("valid", _("Valids")),
            ("wa", _("Attente de validation")),
            ("wp", _("Attente de paiement")),
            ("canceled", _("Canceled")),
            ("all", _("Sans distinction")),
        ]

    def queryset(self, request, queryset):
        value = self.value()

        # Filtrage par défaut
        if value is None:
            return queryset.exclude(status__in=[Membership.CANCELED, Membership.ADMIN_CANCELED])

        if value == "valid":
            # On masque les annulées
            return queryset.exclude(
                Q(status__in=[Membership.CANCELED, Membership.ADMIN_CANCELED]) |
                Q(deadline__lt=timezone.localtime()))

        if value == "wa":
            return queryset.filter(status=Membership.ADMIN_WAITING)

        if value == "wp":
            return queryset.filter(status__in=[Membership.WAITING_PAYMENT, Membership.ADMIN_VALID])

        if value == "canceled":
            return queryset.filter(status__in=[Membership.CANCELED, Membership.ADMIN_CANCELED])

        if value == "all":
            return queryset
        return queryset


@register_component
class MembershipComponent(BaseComponent):
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Les adhésions en cours :
        active_count = Membership.objects.filter(deadline__gte=timezone.localtime()).exclude(
            status__in=[Membership.CANCELED, Membership.ADMIN_CANCELED]).count()
        # Les user qui n'ont pas d'adhésion en cours :
        inactive_count = HumanUser.objects.exclude(
            memberships__deadline__gte=timezone.localtime(),
            memberships__status__in=[Membership.CANCELED, Membership.ADMIN_CANCELED],
        ).distinct().count()

        pending_count = Membership.objects.filter(status=Membership.ADMIN_WAITING).count()

        context["children"] = render_to_string(
            "admin/membership/membership_component.html",
            {
                "type": kwargs.get('type'),
                "active": active_count,
                "inactive": inactive_count,
                "pending": pending_count,
            },
        )
        return context


class MembershipCustomFormSection(TemplateSection):
    template_name = "admin/membership/custom_form_section.html"
    verbose_name = _("Custom form answers")


class LigneArticleInline(TabularInline):
    model = LigneArticle
    fk_name = "membership"
    extra = 0
    show_change_link = True
    can_delete = False
    verbose_name = _("Ventes / Ligne comptables")
    verbose_name_plural = _("Ventes / Ligne comptables")

    fields = (
        "datetime",
        "amount_decimal",
        "qty_decimal",
        "vat",
        "total_decimal",
        "display_status",
        "payment_method",
        "sale_origin",
    )
    readonly_fields = fields

    @display(description=_("Value"))
    def amount_decimal(self, obj):
        return obj.amount_decimal()

    @display(description=_("Quantité"))
    def qty_decimal(self, obj):
        return dround(obj.qty)

    @display(description=_("TVA"))
    def vat(self, obj):
        return obj.vat

    @display(description=_("Total"))
    def total_decimal(self, obj):
        return obj.total_decimal()

    @display(description=_("Statut"), label={None: "danger", True: "success"})
    def display_status(self, instance: LigneArticle):
        return instance.get_status_display()

    def has_view_permission(self, request, obj=None):
        return True

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class MembershipPublishedFilter(admin.SimpleListFilter):
    """
    Filter for filtering Membership by MembershipProduct that are not archived
    """
    title = _('Product')
    parameter_name = 'price' # Get the product from the price

    def lookups(self, request, model_admin):
        # Return only product that are not archived to display in the filter
        return [
            (product.pk, product.name)
            for product in MembershipProduct.objects.filter(archive=False)
        ]

    def queryset(self, request, queryset):
        if self.value():
            # Return only membership where the product correspond to the selected product
            return queryset.filter(price__product=self.value())
        return queryset



@admin.register(Membership, site=staff_admin_site)
class MembershipAdmin(HelpDisplayMixin, ModelAdmin, ImportExportModelAdmin):

    inlines = [LigneArticleInline]
    # Expandable section to display custom form answers in changelist
    list_sections = [MembershipCustomFormSection]
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False
    # Ajoute un bloc personnalisé après le formulaire dans la vue change
    change_form_after_template = "admin/membership/custom_form.html"

    resource_classes = [MembershipExportResource, MembershipImportResource]
    export_form_class = ExportForm
    import_form_class = ImportForm

    list_before_template = "admin/membership/membership_list_before.html"  # appelle le MembershipComponent plus haut pour le contexte

    # Help info for HelpModelAdmin
    list_help_text = HELP_MESSAGES_DICT["ADHESION"]["list_help_text"]
    list_help_url = HELP_MESSAGES_DICT["ADHESION"]["list_help_url"]

    changeform_help_text = HELP_MESSAGES_DICT["ADHESION"]["changeform_help_text"]
    changeform_help_url = HELP_MESSAGES_DICT["ADHESION"]["changeform_help_url"]

    # Formulaire de modification
    form = MembershipChangeForm
    # Formulaire de création. A besoin de get_form pour fonctionner
    add_form = MembershipAddForm

    list_display = (
        'email',
        'date_added',
        'first_name',
        'last_name',
        'price',
        'contribution_value',
        # 'options',
        'display_last_contribution',
        'display_deadline',
        'display_is_valid',
        'status',
        'recurrence',
        # 'state',
        # 'payment_method',
        # 'state_display',
        # 'commentaire',
    )

    ordering = ('-date_added',)
    search_fields = ('user__email', 'user__first_name', 'user__last_name', 'card_number', 'last_contribution',
                     'custom_form')
    list_filter = [MembershipStatusFilter, MembershipPublishedFilter, 'last_contribution', 'deadline', ]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return (
            qs.select_related('user', 'price', 'price__product')
            .prefetch_related('price__product__form_fields')
        )

    @display(description=_("User"))
    def user_email_link(self, obj):
        if obj.user:
            url = reverse("staff_admin:AuthBillet_humanuser_change", args=[obj.user.pk])
            return format_html(
                '<a href="{}" class="font-medium text-primary-600 underline decoration-primary-500 decoration-2 underline-offset-4 hover:text-primary-800 dark:text-primary-500 dark:decoration-primary-600 dark:hover:text-primary-400">{}</a>',
                url,
                obj.user.email
            )
        return "-"

    @display(description=_("Produit / Tarif"))
    def price_product_display(self, obj: Membership):
        return f"{obj.price.product.name} / {obj.price.name}"

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = super().get_readonly_fields(request, obj)
        if obj:  # On est en train de modifier
            return list(readonly_fields) + ['user_email_link', 'price_product_display']
        return readonly_fields

    # def get_fields(self, request, obj=None):
    #     fields = super().get_fields(request, obj)
    #     if obj:
    #         # Si on est en modif, on s'assure que user_email_link est présent et au début
    #         if 'user_email_link' or 'price_product_display' not in fields:
    #             fields = ['user_email_link', 'price_product_display'] + list(fields)
    #     return fields

    ### FORMULAIRES
    # autocomplete_fields = ['option_generale', ]

    def get_form(self, request, obj=None, **kwargs):
        """ Si c'est un add, on modifie un peu le formulaire pour avoir un champs email """
        defaults = {}
        if obj is None:
            defaults['form'] = self.add_form
        defaults.update(kwargs)
        return super().get_form(request, obj, **defaults)

    def get_changeform_initial_data(self, request):
        """Prefill the add form with values provided in the query string.

        Supports simple fields and ManyToMany 'option_generale' via repeated
        query params (e.g. ?option_generale=1&option_generale=2).
        """
        initial = super().get_changeform_initial_data(request)
        params = request.GET

        # Simple scalar params that map to form fields
        for key in [
            'email',
            'price',
            'contribution',
            'payment_method',
            'first_name',
            'last_name',
            # 'card_number',
        ]:
            value = params.get(key)
            if value not in [None, ""]:
                initial[key] = value

        # ManyToMany: option_generale (allow multiple ids)
        # option_ids = params.getlist('option_generale')
        # if option_ids:
            # Keep as list of IDs (ModelMultipleChoiceField accepts IDs as initial)
            # initial['option_generale'] = option_ids

        return initial

    # Panneau d'actions HTMX affiché AVANT le formulaire dans la vue change
    # / HTMX action panel displayed BEFORE the form in the change view
    change_form_before_template = "admin/membership/actions_panel.html"

    def changeform_view(self, request: HttpRequest, object_id: Optional[str] = None, form_url: str = "",
                        extra_context: Optional[Dict[str, bool]] = None):
        extra_context = extra_context or {}
        extra_context["show_validation_buttons"] = False

        if object_id:
            try:
                membership = Membership.objects.select_related('user', 'price', 'price__product').get(pk=object_id)
                extra_context['membership'] = membership
                if membership.status == Membership.ADMIN_WAITING:
                    extra_context["show_validation_buttons"] = True

                # URL de renouvellement avec les données pré-remplies
                # / Renewal URL with pre-filled data
                opts = self.model._meta
                url_formulaire_ajout = reverse(f"{self.admin_site.name}:{opts.app_label}_{opts.model_name}_add")
                params_renouvellement = {}
                if getattr(membership, 'user', None) and getattr(membership.user, 'email', None):
                    params_renouvellement['email'] = membership.user.email
                if membership.price_id:
                    params_renouvellement['price'] = membership.price_id
                if membership.contribution_value is not None:
                    params_renouvellement['contribution'] = str(membership.contribution_value)
                if membership.payment_method:
                    params_renouvellement['payment_method'] = membership.payment_method
                if membership.first_name:
                    params_renouvellement['first_name'] = membership.first_name
                if membership.last_name:
                    params_renouvellement['last_name'] = membership.last_name
                extra_context['renouveller_url'] = f"{url_formulaire_ajout}?{urlencode(params_renouvellement, doseq=True)}"

                # Lien de paiement copiable pour les adhésions validées manuellement (état AV)
                # Même URL que celle envoyée par email — la vue gère l'idempotence (pas de double paiement)
                # / Copyable payment link for manually validated memberships (state AV)
                # Same URL as sent by email — the view handles idempotency (no double payment)
                if membership.status in [Membership.ADMIN_VALID, Membership.ADMIN_WAITING]:
                    try:
                        domaine_tenant = connection.tenant.get_primary_domain().domain
                        extra_context['lien_paiement'] = f"https://{domaine_tenant}/memberships/{membership.uuid}/get_checkout_for_membership"
                    except Exception:
                        pass

                # Statuts qui permettent l'ajout d'un paiement hors-ligne (pour conditionnel template)
                # / Statuses that allow offline payment (for template conditional)
                extra_context['statuts_attente_paiement'] = [
                    Membership.WAITING_PAYMENT,
                    Membership.ADMIN_WAITING,
                    Membership.ADMIN_VALID,
                ]

            except Membership.DoesNotExist:
                extra_context["show_validation_buttons"] = False

        return super().changeform_view(request, object_id, form_url, extra_context)

    @display(description=_("Payment"), ordering="last_contribution")
    def display_last_contribution(self, instance: Membership):
        if instance.last_contribution:
            return instance.last_contribution.strftime("%d/%m/%Y")
        return "-"

    @display(description=_("End"), ordering="deadline")
    def display_deadline(self, instance: Membership):
        if instance.deadline:
            return instance.deadline.strftime("%d/%m/%Y")
        return "-"

    @display(description=_("Valid"), boolean=True)
    def display_is_valid(self, instance: Membership):
        return instance.is_valid()

    @display(description=_("Recurence"), ordering="current_iteration")
    def recurrence(self, instance: Membership):
        if instance.max_iteration and instance.current_iteration:
            return f"{instance.current_iteration}/{instance.max_iteration}"
        elif instance.current_iteration:
            return f"{instance.current_iteration}"
        elif instance.stripe_id_subscription:
            return "∞"
        return ""

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        # return request.user.is_superuser
        return False


### VENTES ###

class LigneArticlePublishedFilter(admin.SimpleListFilter):
    """
    Filter for filtering LigneArticle by Product that are not archived
    """
    title = _('Product')
    parameter_name = 'product'

    def lookups(self, request, model_admin):
        # Return only product that are not archived to display in the filter
        return [
            (product.pk, product.name)
            for product in Product.objects.filter(archive=False)
        ]

    def queryset(self, request, queryset):
        if self.value():
            # Return only sales where the product correspond to the selected product
            return queryset.filter(pricesold__productsold__product=self.value())
        return queryset

class RangeDateTimeFilterWithTimeZone(RangeDateTimeFilter):
    """
    This just override the 'RangeDateTimeFilter' 'queryset' method to take the timezone into account
    """
    def queryset(self, request, queryset):
        filters = {}

        # Get the timezone from the tenant config
        config = Configuration.get_solo()
        new_timezone = config.get_tzinfo()

        date_value_from = self.used_parameters.get(f"{self.parameter_name}_from_0")
        time_value_from = self.used_parameters.get(f"{self.parameter_name}_from_1")

        date_value_to = self.used_parameters.get(f"{self.parameter_name}_to_0")
        time_value_to = self.used_parameters.get(f"{self.parameter_name}_to_1")

        if date_value_from not in EMPTY_VALUES and time_value_from not in EMPTY_VALUES:
            # Add the timezone to the datetime for the filter to work correctly
            value_from = new_timezone.localize(parse_datetime_str(f"{date_value_from} {time_value_from}"))

            filters.update(
                {
                    f"{self.parameter_name}__gte": value_from,
                }
            )

        if date_value_to not in EMPTY_VALUES and time_value_to not in EMPTY_VALUES:
            # Add the timezone to the datetime for the filter to work correctly
            value_to = new_timezone.localize(parse_datetime_str(f"{date_value_to} {time_value_to}"))

            filters.update(
                {
                    f"{self.parameter_name}__lte": value_to
                }
            )
        try:
            return queryset.filter(**filters)
        except (ValueError, ValidationError):
            return None

@admin.register(LigneArticle, site=staff_admin_site)
class LigneArticleAdmin(ModelAdmin,ExportActionModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False
    list_filter_submit = True

    list_filter = ('status',
                   LigneArticlePublishedFilter,
                   ('datetime', RangeDateTimeFilterWithTimeZone),
                   )

    list_display = [
        'productsold',
        'user_email',
        'datetime',
        'amount_decimal',
        '_qty',
        'vat',
        'total_decimal',
        'display_status',
        'payment_method',
        'sale_origin',
        # 'sended_to_laboutik',
    ]
    # fields = "__all__"
    # readonly_fields = fields
    search_fields = ('datetime', 'pricesold__productsold__product__name', 'pricesold__price__name',
                     'paiement_stripe__user__email', 'membership__user__email')
    ordering = ('-datetime',)

    resource_classes = [LigneArticleExportResource]
    export_form_class = ExportForm

    def get_queryset(self, request):
        # Utiliser select_related pour précharger pricesold et productsold
        queryset = super().get_queryset(request)
        return queryset.select_related('pricesold__productsold',
                                       'pricesold__price',
                                       'paiement_stripe',
                                       'paiement_stripe__user',
                                       'membership',
                                       'membership__user',
                                       )

    @display(description=_("Value"))
    def amount_decimal(self, obj):
        return dround(obj.amount)

    @display(description=_("Quantité"))
    def _qty(self, obj):
        return dround(obj.qty)

    @display(description=_("Total"))
    def total_decimal(self, obj: LigneArticle):
        return dround(obj.total())

    @display(description=_("Product"))
    def productsold(self, obj):
        return f"{obj.pricesold.productsold} - {obj.pricesold}"

    # noinspection PyTypeChecker
    @display(description=_("Status"), label={None: "danger", True: "success", "warning": "warning"})
    def display_status(self, instance: LigneArticle):
        status = instance.status
        if status in [LigneArticle.VALID, LigneArticle.FREERES]:
            return True, f"{instance.get_status_display()}"
        if status == LigneArticle.CREDIT_NOTE:
            return "warning", f"{instance.get_status_display()}"
        if instance.credit_notes.exists():
            return "warning", f"{instance.get_status_display()} ⚠"
        return None, f"{instance.get_status_display()}"

    actions_row = ["emettre_avoir"]

    @action(
        description=_("Credit note"),  # Avoir
        url_path="emettre_avoir",
        permissions=["custom_actions_row"],
    )
    def emettre_avoir(self, request, object_id):
        """
        Cree un avoir (ligne negative) pour annuler comptablement cette vente.
        / Creates a credit note (negative line) to cancel this sale.
        """
        ligne_originale = get_object_or_404(
            LigneArticle.objects.select_related('pricesold', 'pricesold__productsold'),
            pk=object_id,
        )

        redirect_url = request.META.get("HTTP_REFERER", "/admin/")

        # Garde : uniquement sur les lignes VALID ou PAID
        if ligne_originale.status not in [LigneArticle.VALID, LigneArticle.PAID]:
            messages.error(request, _("A credit note can only be issued for a confirmed or paid entry."))
            return redirect(redirect_url)

        # Garde : pas d'avoir si un avoir existe deja
        if ligne_originale.credit_notes.exists():
            messages.error(request, _("A credit note already exists for this entry."))
            return redirect(redirect_url)

        # Creer la ligne avoir / Create the credit note line
        avoir = LigneArticle.objects.create(
            pricesold=ligne_originale.pricesold,
            qty=-ligne_originale.qty,
            amount=ligne_originale.amount,
            vat=ligne_originale.vat,
            paiement_stripe=ligne_originale.paiement_stripe,
            membership=ligne_originale.membership,
            payment_method=ligne_originale.payment_method,
            asset=ligne_originale.asset,
            wallet=ligne_originale.wallet,
            sale_origin=SaleOrigin.ADMIN,
            credit_note_for=ligne_originale,
            status=LigneArticle.CREATED,
        )
        # Declenche la machine a etat / Trigger state machine
        avoir.status = LigneArticle.CREDIT_NOTE
        avoir.save()

        messages.success(request, _("Credit note created."))
        return redirect(redirect_url)

    def has_custom_actions_row_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PostalAddress, site=staff_admin_site)
class PostalAddressAdmin(ModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False

    list_display = [
        "name",
        "street_address",
        "address_locality",
        "address_region",
        "postal_code",
        "address_country",
        "latitude",
        "longitude",
        "comment",
        "is_main",
    ]

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


##### EVENT ADMIN


class EventChildrenInline(TabularInline):
    model = Event
    fk_name = 'parent'
    verbose_name = _("Volunteering")  # Pour l'instant, les enfants sont forcément des Actions.
    hide_title = True
    fields = (
        'name',
        'datetime',
        'jauge_max',
        'valid_tickets_count',
    )

    # ordering_field = "weight"
    # max_num = 1
    extra = 0
    show_change_link = True
    tab = True

    readonly_fields = (
        'valid_tickets_count',
    )

    # Surcharger la méthode pour désactiver la suppression
    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


class EventForm(ModelForm):
    class Meta:
        model = Event
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['products'].widget.can_change_related = False
        self.fields['products'].widget.can_add_related = False
        self.fields['products'].help_text = _("Leave empty to avoid reservations.")
        self.fields['short_description'].help_text = _("Used for social network descriptions.")

        try:
            # On mets la valeur de la jauge réglée dans la config par default
            config = Configuration.get_solo()
            self.fields['jauge_max'].initial = config.jauge_max
        except Exception as e:
            logger.error(f"set gauge max error : {e}")
            pass


class EventPricesSummaryTable(TableSection):
    verbose_name = _("Résumé par tarif")
    height = 240
    related_name = "pricesold_for_sections"  # Event property returning Ticket queryset with annotations
    fields = ["price_name", "qty_reserved", "total_euros"]

    def price_name(self, instance: Ticket):
        # Prefer annotated name to avoid extra queries
        name = getattr(instance, "section_price_name", None)
        if name:
            return name
        try:
            return instance.pricesold.price.name if instance.pricesold and instance.pricesold.price else "—"
        except Exception:
            return "—"

    def qty_reserved(self, instance: Ticket):
        qty = getattr(instance, "section_qty_reserved", None)
        if qty is None:
            qty = 0
        try:
            from decimal import Decimal
            if isinstance(qty, Decimal):
                return int(qty) if qty == qty.to_integral() else qty
            return int(qty) if float(qty).is_integer() else qty
        except Exception:
            return qty

    def total_euros(self, instance: Ticket):
        euros = getattr(instance, "section_euros_total", None)
        if euros is None:
            euros = 0
        try:
            from decimal import Decimal
            return (Decimal(euros)).quantize(Decimal("1.00"))
        except Exception:
            return 0


class ChildActionsSummaryTable(TableSection):
    verbose_name = _("Action bénévoles")
    height = 240
    related_name = "children_pricesold_for_sections"
    fields = ["price_name", "qty_reserved"]

    def price_name(self, instance: Ticket):
        name = getattr(instance, "section_price_name", None)
        if name:
            return name
        try:
            return instance.reservation.event.name if instance.reservation and instance.reservation.event else "Oups"
        except Exception:
            return "—"

    def qty_reserved(self, instance: Ticket):
        qty = getattr(instance, "section_qty_reserved", None)
        if qty is None:
            qty = 0
        try:
            from decimal import Decimal
            if isinstance(qty, Decimal):
                return int(qty) if qty == qty.to_integral() else qty
            return int(qty) if float(qty).is_integer() else qty
        except Exception:
            return qty

    # Hide the section entirely if the event has no children
    def render(self):
        try:
            if not self.instance.children.exists():
                return ""
        except Exception:
            return ""
        return super().render()


class EventArchiveFilter(admin.SimpleListFilter):
    title = _("Archived")
    parameter_name = "archived"

    def lookups(self, request, model_admin):
        return [
            ("archived", _("Archived")),
        ]

    def queryset(self, request, queryset):
        value = self.value()
        # Filtrage par défaut
        if value is None:
            return queryset.exclude(archived=True)
        if value == "archived":
            return queryset.filter(archived=True)
        return queryset


# Import/Export Resource pour Event
# Resource for CSV import/export of events in admin
class EventResource(resources.ModelResource):
    """Ressource d'import/export pour les événements.
    Resource for import/export of events.

    Clés uniques: (name, datetime) — identifie si on crée ou met à jour.
    Unique keys: (name, datetime) — determines create vs update.

    Les ForeignKey (postal_address) sont exportées en clair (nom lisible).
    ForeignKey fields (postal_address) are exported as human-readable names.

    Les ManyToMany (products, tag) ne sont pas gérés ici.
    ManyToMany fields (products, tag) are not handled here.
    Il faudrait un widget M2MWidget personnalisé pour les gérer.
    A custom M2MWidget would be needed to handle them.
    """

    # postal_address : on exporte/importe le nom de l'adresse au lieu de l'ID
    # postal_address: export/import the address name instead of the raw PK
    postal_address = fields.Field(
        column_name='postal_address',
        attribute='postal_address',
        widget=ForeignKeyWidget(PostalAddress, field='name'),
    )

    class Meta:
        model = Event
        import_id_fields = ('name', 'datetime')
        fields = (
            'name', 'datetime', 'end_datetime', 'jauge_max', 'max_per_user',
            'short_description', 'long_description', 'published', 'archived',
            'private', 'show_time', 'show_gauge', 'slug', 'is_external',
            'full_url', 'postal_address', 'reservation_button_name',
            'minimum_cashless_required',
        )
        # Ordre des colonnes dans le CSV exporté
        # Column order in the exported CSV
        export_order = fields
        widgets = {
            'datetime': {'format': '%Y-%m-%d %H:%M:%S'},
            'end_datetime': {'format': '%Y-%m-%d %H:%M:%S'},
        }
        # Ne pas lever d'erreur sur les lignes invalides, les ignorer
        # Skip invalid rows instead of raising errors
        skip_unchanged = True
        # Afficher un diff des changements avant import
        # Show a diff of changes before import
        report_skipped = True


class IsProposalFilter(admin.SimpleListFilter):
    """
    Filtre sidebar Unfold pour distinguer propositions publiques en
    attente, propositions approuvees et events normaux.
    / Unfold sidebar filter for pending proposals, approved proposals
    and regular events.
    """
    title = _("Proposal status")
    parameter_name = "proposal_status"

    def lookups(self, request, model_admin):
        return [
            ("pending", _("Proposals pending")),
            ("approved", _("Proposals approved")),
            ("regular", _("Regular events")),
        ]

    def queryset(self, request, queryset):
        if self.value() == "pending":
            return queryset.filter(is_proposal=True, published=False)
        if self.value() == "approved":
            return queryset.filter(is_proposal=True, published=True)
        if self.value() == "regular":
            return queryset.filter(is_proposal=False)
        return queryset


@admin.register(Event, site=staff_admin_site)
class EventAdmin(ModelAdmin, ImportExportModelAdmin):
    form = EventForm
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False
    date_hierarchy = "datetime"
    ordering = ("-datetime",)
    
    # Import/Export configuration
    resource_classes = [EventResource]
    export_form_class = ExportForm
    import_form_class = ImportForm
    
    # Unfold sections (expandable rows)
    list_sections = [
        EventPricesSummaryTable,
        ChildActionsSummaryTable,
    ]
    list_per_page = 20

    change_form_template = 'admin/event/change_form.html'

    export_form_class = ExportForm
    import_form_class = ImportForm

    inlines = [EventChildrenInline, ]

    actions_row = ["duplicate_day_plus_one", "duplicate_week_plus_one", "duplicate_week_plus_two",
                   "duplicate_month_plus_one", "archive"]

    fieldsets = (
        (None, {
            'fields': (
                'name',
                # 'categorie',
                'datetime',
                'end_datetime',
                'show_time',
                'img',
                'sticker_img',
                'carrousel',
                'short_description',
                'long_description',
                'jauge_max',
                'show_gauge',
                'postal_address',
                'tag',
                'thematique',
            )
        }),
        (_('Bookings'), {
            'fields': (
                # 'easy_reservation',
                'products',
                'max_per_user',
                'reservation_button_name',
                'custom_confirmation_message',
                'refund_deadline',
            ),
        }),
        (_('Publish'), {
            'fields': (
                'published',
                'private',
                'archived',
            ),
        }),
    )

    list_display = [
        'name',
        # 'categorie',
        'display_valid_tickets_count',
        'datetime',
        'show_time',
        'published',
    ]

    list_editable = ['published', ]
    readonly_fields = (
        'display_valid_tickets_count',
    )

    search_fields = ['name']
    list_filter = [
        IsProposalFilter,
        EventArchiveFilter,
        ('datetime', RangeDateTimeFilterWithTimeZone),
        'published',
    ]
    list_filter_submit = True

    actions = ["approuver_propositions"]

    autocomplete_fields = [
        "tag",
        "thematique",
        # "options_radio",
        # "options_checkbox",
        "carrousel",

        # Le autocomplete fields + many2many ne permet pas de filtrage facile
        # Pour filter les produits de type billet, regarder le get_search_results dans ProductAdmin
        "products",
    ]

    formfield_overrides = {
        models.TextField: {
            "widget": WysiwygWidget,
        }
    }

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        # Les events action et les events children doivent s'afficher dans un inline
        return (
            queryset
            .exclude(categorie=Event.ACTION)
            .exclude(parent__isnull=False)
            .select_related('postal_address')
            .prefetch_related(
                'tag', 'carrousel', 'products',
                Prefetch(
                    'reservation',
                    queryset=Reservation.objects.select_related('user_commande')
                    .only('pk', 'datetime', 'status', 'user_commande__email', 'event')
                ),
            )
            .annotate(
                valid_tickets_count_annotated=Count(
                    'reservation__tickets',
                    filter=Q(reservation__tickets__status__in=[Ticket.SCANNED, Ticket.NOT_SCANNED]),
                    distinct=True,
                )
            )
        )

    def save_model(self, request, obj: Event, form, change):
        # Sanitize all TextField inputs to avoid XSS via WysiwYG/TextField
        sanitize_textfields(obj)

        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        obj = form.instance
        # Fabrication des pricesold event/prix pour pouvoir être selectionné sur le + billet
        # Doit être dans save_related (pas save_model) car les M2M products
        # ne sont disponibles qu'après que Django les a sauvées.
        for product in obj.products.all():
            for price in product.prices.all():
                get_or_create_price_sold(price=price, event=obj)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return False

    def has_custom_actions_row_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    @display(description=_("Valid tickets"))
    def display_valid_tickets_count(self, instance: Event):
        # Use annotated value to avoid N+1; fallback to method if not present (e.g., detail page)
        count = getattr(instance, 'valid_tickets_count_annotated', None)
        if count is None:
            count = instance.valid_tickets_count()
        return f"{count} / {instance.jauge_max}"

    @action(
        description=_("Archive"),
        permissions=["custom_actions_row"],
    )
    def archive(self, request, object_id):
        event = Event.objects.get(pk=object_id)
        event.archived = True
        event.published = False
        event.save(update_fields=['archived', 'published'])
        return redirect(request.META["HTTP_REFERER"])

    @action(
        description=_("Duplicate (day+1)"),
        permissions=["custom_actions_row"],
    )
    def duplicate_day_plus_one(self, request, object_id):
        """Duplicate an event with the date set to the next day"""
        obj = Event.objects.get(pk=object_id)
        try:
            duplicate = self._duplicate_event(obj, date_adjustment="day")
            messages.success(request, _("Event duplicated successfully"))
        except IntegrityError as e:
            messages.error(request, _("Un evenement avec le même nom et date semble déja dupliqué"))

        return redirect(request.META["HTTP_REFERER"])

        # return redirect(reverse('staff:BaseBillet_event_change', args=[duplicate.uuid]))

    @action(
        description=_("Duplicate (week+1)"),
        permissions=["custom_actions_row"],
    )
    def duplicate_week_plus_one(self, request, object_id):
        """Duplicate an event with the date set to the next week"""
        obj = Event.objects.get(pk=object_id)
        try:
            duplicate = self._duplicate_event(obj, date_adjustment="week")
            messages.success(request, _("Event duplicated successfully"))
        except IntegrityError as e:
            messages.error(request, _("Un evenement avec le même nom et date semble déja dupliqué"))

        return redirect(request.META["HTTP_REFERER"])

        # return redirect(reverse('staff:BaseBillet_event_change', args=[duplicate.uuid]))

    @action(
        description=_("Duplicate (week+2)"),
        permissions=["custom_actions_row"],
    )
    def duplicate_week_plus_two(self, request, object_id):
        """Duplicate an event with the date set to two weeks ahead"""
        obj = Event.objects.get(pk=object_id)
        try:
            duplicate = self._duplicate_event(obj, date_adjustment="week2")
            messages.success(request, _("Event duplicated successfully"))
        except IntegrityError as e:
            messages.error(request, _("Un evenement avec le même nom et date semble déja dupliqué"))

        return redirect(request.META["HTTP_REFERER"])

        # return redirect(reverse('staff:BaseBillet_event_change', args=[duplicate.uuid]))

    @action(
        description=_("Duplicate (month+1)"),
        permissions=["custom_actions_row"],
    )
    def duplicate_month_plus_one(self, request, object_id):
        """Duplicate an event with the date set to the next month"""
        obj = Event.objects.get(pk=object_id)
        try:
            duplicate = self._duplicate_event(obj, date_adjustment="month")
            messages.success(request, _("Event duplicated successfully"))
        except IntegrityError as e:
            messages.error(request, _("Un evenement avec le même nom et date semble déja dupliqué"))
        return redirect(request.META["HTTP_REFERER"])

        # return redirect(reverse('staff:BaseBillet_event_change', args=[duplicate.uuid]))

    def _duplicate_event(self, obj, date_adjustment=None):
        """
        Helper method to duplicate an event

        Args:
            obj: The event to duplicate
            date_adjustment: Type of date adjustment to apply ("day", "week", "month", or None for same date)

        Returns:
            The duplicated event
        """
        # Create a copy of the event
        duplicate = Event.objects.get(uuid=obj.uuid)
        duplicate.pk = None  # This will create a new object on save
        duplicate.rsa_key = None  # Ensure a new RSA key is generated
        duplicate.slug = None  # Ensure a new slug is generated

        # Set the name (no prefix)
        duplicate.name = obj.name

        # Set published to False
        duplicate.published = False

        # Adjust the date based on the date_adjustment parameter
        if date_adjustment == "day":
            # Add 1 day to the date
            duplicate.datetime = obj.datetime + timedelta(days=1)
            if obj.end_datetime:
                duplicate.end_datetime = obj.end_datetime + timedelta(days=1)
        elif date_adjustment == "week":
            # Add 7 days to the date
            duplicate.datetime = obj.datetime + timedelta(days=7)
            if obj.end_datetime:
                duplicate.end_datetime = obj.end_datetime + timedelta(days=7)
        elif date_adjustment == "week2":
            # Add 14 days to the date
            duplicate.datetime = obj.datetime + timedelta(days=14)
            if obj.end_datetime:
                duplicate.end_datetime = obj.end_datetime + timedelta(days=14)
        elif date_adjustment == "month":
            # Add 1 month to the date
            from dateutil.relativedelta import relativedelta
            duplicate.datetime = obj.datetime + relativedelta(months=1)
            if obj.end_datetime:
                duplicate.end_datetime = obj.end_datetime + relativedelta(months=1)

        # Save the duplicate
        duplicate.save()

        # Copy many-to-many relationships
        duplicate.products.set(obj.products.all())
        duplicate.tag.set(obj.tag.all())
        # duplicate.options_radio.set(obj.options_radio.all())
        # duplicate.options_checkbox.set(obj.options_checkbox.all())
        duplicate.carrousel.set(obj.carrousel.all())

        # Duplicate child events of type ACTION
        for child in obj.children.filter(categorie=Event.ACTION):
            child_duplicate = Event.objects.get(uuid=child.uuid)
            child_duplicate.pk = None  # This will create a new object on save
            child_duplicate.rsa_key = None  # Ensure a new RSA key is generated
            child_duplicate.slug = None  # Ensure a new slug is generated
            child_duplicate.parent = duplicate

            # Child events should be published
            child_duplicate.published = True

            # Adjust the date based on the date_adjustment parameter
            if date_adjustment == "day":
                # Add 1 day to the date
                child_duplicate.datetime = child.datetime + timedelta(days=1)
                if child.end_datetime:
                    child_duplicate.end_datetime = child.end_datetime + timedelta(days=1)
            elif date_adjustment == "week":
                # Add 7 days to the date
                child_duplicate.datetime = child.datetime + timedelta(days=7)
                if child.end_datetime:
                    child_duplicate.end_datetime = child.end_datetime + timedelta(days=7)
            elif date_adjustment == "week2":
                # Add 14 days to the date
                child_duplicate.datetime = child.datetime + timedelta(days=14)
                if child.end_datetime:
                    child_duplicate.end_datetime = child.end_datetime + timedelta(days=14)
            elif date_adjustment == "month":
                # Add 1 month to the date
                from dateutil.relativedelta import relativedelta
                child_duplicate.datetime = child.datetime + relativedelta(months=1)
                if child.end_datetime:
                    child_duplicate.end_datetime = child.end_datetime + relativedelta(months=1)

            child_duplicate.save()

            # Copy many-to-many relationships for child
            child_duplicate.products.set(child.products.all())
            child_duplicate.tag.set(child.tag.all())
            # child_duplicate.options_radio.set(child.options_radio.all())
            # child_duplicate.options_checkbox.set(child.options_checkbox.all())
            child_duplicate.carrousel.set(child.carrousel.all())

        return duplicate

    @admin.action(description=_("Approve and publish selected proposals"))
    def approuver_propositions(self, request, queryset):
        """
        Action bulk : pour chaque event selectionne qui est une proposition
        en attente, set is_proposal=False + published=True.
        / Bulk action: approve and publish selected pending proposals.
        """
        nb_approuvees = queryset.filter(is_proposal=True, published=False).update(
            is_proposal=False,
            published=True,
        )
        self.message_user(
            request,
            _("%(n)s proposal(s) approved.") % {"n": nb_approuvees},
            messages.SUCCESS,
        )


class ReservationValidFilter(admin.SimpleListFilter):
    # Pour filtrer sur les réservation valide : payée, payée et confirmée, et mail en erreur même si payés
    title = _("Valid")

    # Parameter for the filter that will be used in the URL query.
    parameter_name = "status_valid"

    def lookups(self, request, model_admin):
        return [
            # ("Y", _("Yes")),
            ("N", _("Invalids")),
        ]

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """
        value = self.value()
        if value == None:  # valeur par défault
            return queryset.exclude(
                status__in=[
                    Reservation.CANCELED,
                    Reservation.CREATED,
                    Reservation.UNPAID,
                ]
            ).distinct()

        if value == "N":
            return queryset.filter(
                status__in=[
                    Reservation.CANCELED,
                    Reservation.CREATED,
                    Reservation.UNPAID,
                ]
            ).distinct()


class ReservationAddAdmin(ModelForm):
    # Uniquement les tarif Adhésion
    email = forms.ModelChoiceField(
        required=True,
        queryset=TibilletUser.objects.all(),
        empty_label=_("Select a user"),  # Texte affiché par défaut
        label="Email",
        widget=UnfoldAdminSelect2Widget,
    )

    pricesold = forms.ModelChoiceField(
        queryset=PriceSold.objects.filter(
            productsold__event__datetime__gte=timezone.localtime() - timedelta(days=1)).order_by(
            "productsold__event__datetime"),
        # Remplis le champ select avec les objets Price
        empty_label=_("Select a product"),  # Texte affiché par défaut
        required=True,
        widget=UnfoldAdminSelect2Widget,
        label=_("Rate")
    )

    # options_checkbox = forms.ModelMultipleChoiceField(
    #     # Uniquement les options qui sont utilisé dans les évènements futurs
    #     required=False,
    #     queryset=OptionGenerale.objects.filter(
    #         options_checkbox__datetime__gte=timezone.localtime() - timedelta(days=1)),
    #     widget=UnfoldAdminCheckboxSelectMultiple(),
    #     label=_("Multiple choice menu"),
    # )
    #
    # options_radio = forms.ModelChoiceField(
    #     # Uniquement les options qui sont utilisé dans les évènements futurs
    #     required=False,
    #     queryset=OptionGenerale.objects.filter(options_radio__datetime__gte=timezone.localtime() - timedelta(days=1)),
    #     widget=UnfoldAdminRadioSelectWidget(),
    #     label=_("Single choice menu"),
    # )

    payment_method = forms.ChoiceField(
        required=False,
        choices=PaymentMethod.classic(),  # on retire les choix token
        widget=UnfoldAdminSelectWidget(),  # attrs={"placeholder": "Entrez l'adresse email"}
        label=_("Payment method"),
    )

    quantity = forms.IntegerField(
        required=False,
        initial=1,
        min_value=1,
        max_value=32767,
        widget=UnfoldAdminTextInputWidget(attrs={"type": "number", "min": "1"}),
        label=_("Quantity"),
    )

    class Meta:
        model = Reservation
        fields = []
        # 'first_name',
        # 'last_name',
        # ]

    def clean_payment_method(self):
        cleaned_data = self.cleaned_data
        pricesold = cleaned_data.get('pricesold')
        payment_method = cleaned_data.get('payment_method')
        # pricesold peut être None si le champ a des erreurs de validation ou n'est pas renseigné
        # On ne valide la méthode de paiement que si on a un produit
        if pricesold and getattr(pricesold, 'productsold', None):
            if pricesold.productsold.categorie_article == Product.FREERES and payment_method != PaymentMethod.FREE:
                raise forms.ValidationError(_("Une reservation gratuite doit être en paiement OFFERT"), code="invalid")
        return payment_method

    def clean(self):
        return super().clean()

    def save(self, commit=True):
        cleaned_data = self.cleaned_data

        email = self.cleaned_data.pop('email')
        user = get_or_create_user(email)

        pricesold: PriceSold = cleaned_data.pop('pricesold')
        event: Event = pricesold.productsold.event

        reservation: Reservation = self.instance
        reservation.user_commande = user
        reservation.event = event
        reservation.status = Reservation.VALID  # automatiquement en VALID,on est sur l'admin
        # On va chercher les options
        # options_checkbox = cleaned_data.pop('options_checkbox')
        # if options_checkbox:
        #     reservation.options.set(options_checkbox)
        # options_radio = cleaned_data.pop('options_radio')
        # if options_radio:
        #     reservation.options.add(options_radio)

        reservation = super().save(commit=commit)

        ### Création des billets associés
        payment_method = self.cleaned_data.pop('payment_method')
        quantity = self.cleaned_data.pop('quantity', 1) or 1
        for _ in range(quantity):
            Ticket.objects.create(
                payment_method=payment_method,
                reservation=reservation,
                status=Ticket.NOT_SCANNED,
                sale_origin=SaleOrigin.ADMIN,
                pricesold=pricesold,
            )

        # Création de la ligne comptables
        # Si offert, le montant est 0
        if payment_method == PaymentMethod.FREE:
            amount = 0
        else:
            amount = int(pricesold.prix * quantity * 100)

        vente = LigneArticle.objects.create(
            pricesold=pricesold,
            qty=quantity,
            amount=amount,
            payment_method=payment_method,
            status=LigneArticle.VALID,
            sale_origin=SaleOrigin.ADMIN,
            reservation=reservation,
        )
        # envoie à Laboutik
        send_sale_to_laboutik.delay(vente.pk)

        # Envoie des ticket par mail
        ticket_celery_mailer.delay(reservation.pk)

        return reservation


class ReservationCustomFormSection(TemplateSection):
    template_name = "admin/reservation/custom_form_section.html"
    verbose_name = _("Custom form answers")


class EventArchivedFilter(admin.SimpleListFilter):
    title = _("Archived Event")
    parameter_name = 'event_archived'

    def lookups(self, request, model_admin):
        events = Event.objects.filter(archived=True).order_by('-datetime')
        return [(str(e.pk), str(e)) for e in events]

    def queryset(self, request, queryset):
        if self.value():
            if queryset.model == Reservation:
                return queryset.filter(event_id=self.value())
            elif queryset.model == Ticket:
                return queryset.filter(reservation__event_id=self.value())
        return queryset


class EventFutureFilter(admin.SimpleListFilter):
    title = _("-> Future event")
    parameter_name = 'event_future'

    def lookups(self, request, model_admin):
        now = timezone.now() - timedelta(days=1)
        events = Event.objects.filter(archived=False, datetime__gte=now).order_by('datetime')
        return [(str(e.pk), str(e)) for e in events]

    def queryset(self, request, queryset):
        if self.value():
            if queryset.model == Reservation:
                return queryset.filter(event_id=self.value())
            elif queryset.model == Ticket:
                return queryset.filter(reservation__event_id=self.value())
        return queryset


class EventPastFilter(admin.SimpleListFilter):
    title = _("<- Past event")
    parameter_name = 'event_past'

    def lookups(self, request, model_admin):
        now = timezone.now()
        events = Event.objects.filter(archived=False, datetime__lt=now).order_by('-datetime')
        return [(str(e.pk), str(e)) for e in events]

    def queryset(self, request, queryset):
        if self.value():
            if queryset.model == Reservation:
                return queryset.filter(event_id=self.value())
            elif queryset.model == Ticket:
                return queryset.filter(reservation__event_id=self.value())
        return queryset


@admin.register(Reservation, site=staff_admin_site)
class ReservationAdmin(ModelAdmin):
    # Expandable section to display custom form answers in changelist
    list_sections = [ReservationCustomFormSection]

    # Formulaire de création. A besoin de get_form pour fonctionner
    add_form = ReservationAddAdmin
    autocomplete_fields = ["event",]

    def get_form(self, request, obj=None, **kwargs):
        """ Si c'est un add, on modifie le formulaire"""
        defaults = {}
        if obj is None:
            defaults['form'] = self.add_form
        defaults.update(kwargs)
        return super().get_form(request, obj, **defaults)

    list_display = (
        'datetime',
        'user_commande',
        'event',
        'status',
        'tickets_count',
        # 'options_str',
        'total_paid',
    )
    # readonly_fields = list_display

    search_fields = ['event__name', 'user_commande__email', 'datetime', 'custom_form']
    list_filter = [
        EventFutureFilter,
        ReservationValidFilter,
        'datetime',
        # 'options',
        EventPastFilter,
        EventArchivedFilter,
    ]

    # Bulk actions available in changelist
    actions = ["action_cancel_refund_reservations"]

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return (
            queryset
            .select_related('user_commande', 'event')
            .prefetch_related(
                # 'options',
                'tickets',
                'tickets__pricesold__price__product__form_fields',
            )
        )

    @admin.action(description=_("Cancel and refund selected reservations"))
    def action_cancel_refund_reservations(self, request, queryset):
        # Only operate on queryset of reservations; prefetch to reduce queries
        qs = queryset.select_related('user_commande', 'event').prefetch_related('tickets')
        success_count = 0
        errors = []
        for resa in qs:
            try:
                msg = resa.cancel_and_refund_resa()
                try:
                    send_reservation_cancellation_user.delay(str(resa.uuid))
                except Exception as ce:
                    logger.error(f"Failed to queue reservation cancellation email for {resa.uuid}: {ce}")
                success_count += 1
            except Exception as e:
                errors.append(str(e))
        if success_count:
            messages.success(request, _("%(count)d reservation(s) cancelled and refunded.") % {"count": success_count})
        if errors:
            unique_errors = list(dict.fromkeys(errors))
            preview = " | ".join(unique_errors[:5])
            if len(unique_errors) > 5:
                preview += _(" ... (%(more)d more)") % {"more": len(unique_errors) - 5}
            messages.error(request, _("Some reservations failed to cancel/refund: %(errors)s") % {"errors": preview})

    @display(description=_("Ticket count"))
    def tickets_count(self, instance: Reservation):
        return instance.tickets.filter(status__in=[Ticket.SCANNED, Ticket.NOT_SCANNED]).count()

    # @display(description=_("Options"))
    # def options_str(self, instance: Reservation):
    #     return " - ".join([option.name for option in instance.options.all()])

    actions_detail = ["send_ticket_to_mail", ]

    @action(
        description=_("Send tickets through email again"),
        url_path="send_ticket_to_mail",
        permissions=["custom_actions_detail"],
    )
    def send_ticket_to_mail(self, request, object_id):
        reservation = Reservation.objects.get(pk=object_id)
        ticket_celery_mailer.delay(reservation.pk)
        messages.success(
            request,
            _(f"Tickets sent to {reservation.user_commande.email}"),
        )
        return redirect(request.META["HTTP_REFERER"])

    def has_custom_actions_detail_permission(self, request, object_id):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        # Allow bulk actions in changelist for authorized tenant admins
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return False


class TicketChangeAdmin(ModelForm):
    class Meta:
        model = Ticket
        fields = [
            'first_name',
            'last_name',
        ]


class TicketValidFilter(admin.SimpleListFilter):
    # Pour filtrer sur les réservation valide : payée, payée et confirmée, et mail en erreur même si payés
    title = _("Valid")

    # Parameter for the filter that will be used in the URL query.
    parameter_name = "status_valid"

    def lookups(self, request, model_admin):
        return [
            # ("Y", _("Yes")),
            ("N", _("No")),
        ]

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """
        if self.value() == None:
            return queryset.filter(
                status__in=[
                    Ticket.NOT_SCANNED,
                    Ticket.SCANNED,
                ]
            ).distinct()
        if self.value() == "N":
            return queryset.exclude(
                status__in=[
                    Ticket.NOT_SCANNED,
                    Ticket.SCANNED,
                ]
            ).distinct()


class TicketCustomFormSection(TemplateSection):
    template_name = "admin/ticket/custom_form_section.html"
    verbose_name = _("Custom form answers")


@admin.register(Ticket, site=staff_admin_site)
class TicketAdmin(ModelAdmin, ExportActionModelAdmin):
    ordering = ('-reservation__datetime',)
    list_filter = [
        EventFutureFilter,
        EventPastFilter,
        TicketValidFilter,
        "reservation__datetime",
        # "reservation__options",
        EventArchivedFilter,
    ]
    search_fields = (
        'uuid',
        'first_name',
        'last_name',
        'reservation__user_commande__email',
        'reservation__custom_form',
    )

    list_display = [
        'ticket',
        # 'first_name',
        # 'last_name',
        'event',
        # 'options',
        'product_name',
        'price_name',
        'state',
        'scan',
        'reservation__datetime',
    ]

    resource_classes = [TicketExportResource]
    export_form_class = ExportForm

    actions = ["action_unscan_selected", "action_cancel_refund_selected"]

    # Expandable section to display parent reservation custom form answers
    list_sections = [TicketCustomFormSection]

    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False

    # Formulaire de modification
    form = TicketChangeAdmin

    @admin.action(description=_("Unscan selected tickets"))
    def action_unscan_selected(self, request, queryset):
        updated = 0
        skipped = 0
        for ticket in queryset.select_related('reservation'):
            if ticket.status == Ticket.SCANNED:
                ticket.status = Ticket.NOT_SCANNED
                ticket.save()
                updated += 1
            else:
                skipped += 1
        if updated:
            messages.success(request, _("%(count)d ticket(s) unscanned successfully.") % {"count": updated})
        if skipped:
            messages.info(request, _("%(count)d ticket(s) were not scanned and were skipped.") % {"count": skipped})

    @admin.action(description=_("Cancel and refund"))
    def action_cancel_refund_selected(self, request, queryset):
        # Group selected tickets by reservation
        tickets = queryset.select_related('reservation')
        res_to_tickets: Dict[str, Dict[str, Any]] = {}
        for t in tickets:
            resa_id = str(t.reservation_id)
            bucket = res_to_tickets.setdefault(resa_id, {"reservation": t.reservation, "tickets": []})
            bucket["tickets"].append(t)

        resa_success = 0
        ticket_success = 0
        errors = []

        for resa_id, bucket in res_to_tickets.items():
            resa = bucket["reservation"]
            selected_tickets = bucket["tickets"]
            try:
                total_in_resa = resa.tickets.count()
                if len(selected_tickets) == total_in_resa:
                    # All tickets of reservation selected -> cancel whole reservation
                    msg = resa.cancel_and_refund_resa()
                    try:
                        send_reservation_cancellation_user.delay(str(resa.uuid))
                    except Exception as ce:
                        logger.error(f"Failed to queue reservation cancellation email for {resa.uuid}: {ce}")
                    resa_success += 1
                else:
                    # Partial selection -> cancel each selected ticket
                    for t in selected_tickets:
                        try:
                            msg = resa.cancel_and_refund_ticket(t)
                            try:
                                send_ticket_cancellation_user.delay(str(t.uuid))
                            except Exception as ce:
                                logger.error(f"Failed to queue ticket cancellation email for {t.uuid}: {ce}")
                            ticket_success += 1
                        except Exception as te:
                            errors.append(str(te))
            except Exception as e:
                errors.append(str(e))

        if resa_success:
            messages.success(request, _("%(count)d reservation(s) cancelled and refunded.") % {"count": resa_success})
        if ticket_success:
            messages.success(request, _("%(count)d ticket(s) cancelled and refunded.") % {"count": ticket_success})
        if errors:
            # Deduplicate and limit message length
            unique_errors = list(dict.fromkeys(errors))
            preview = " | ".join(unique_errors[:5])
            if len(unique_errors) > 5:
                preview += _(" ... (%(more)d more)") % {"more": len(unique_errors) - 5}
            messages.error(request, _("Some items failed to cancel/refund: %(errors)s") % {"errors": preview})

    @admin.display(ordering='pricesold__price', description=_('Price'))
    def price_name(self, obj: Ticket):
        if obj.pricesold:
            return obj.pricesold.price.name
        return ""

    @admin.display(ordering='pricesold__price', description=_('Product'))
    def product_name(self, obj: Ticket):
        if obj.pricesold:
            return obj.pricesold.price.product.name
        return ""

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return (
            queryset
            .select_related('reservation', 'reservation__event', 'reservation__event__parent',
                            'reservation__user_commande')
            .prefetch_related(
                # 'reservation__options',
                'reservation__tickets__pricesold__price__product__form_fields',
            )
        )

    @admin.display(ordering='reservation__datetime', description=_('Booked at'))
    def reservation__datetime(self, obj):
        return obj.reservation.datetime

    @admin.display(ordering='reservation__event', description='Event')
    def event(self, obj):
        if obj.reservation.event.parent:
            return f"{obj.reservation.event.parent} -> {obj.reservation.event}"
        return obj.reservation.event

    # noinspection PyTypeChecker
    @display(description=_("State"), label={None: "danger", True: "success", 'scanned': "warning"})
    def state(self, obj: Ticket):
        if obj.status == Ticket.NOT_SCANNED:
            return True, obj.get_status_display()
        elif obj.status == Ticket.SCANNED:
            return 'scanned', obj.get_status_display()
        # logger.info(f"state: {obj.status} - {obj.get_status_display()}")
        return None, obj.get_status_display()

    # noinspection PyTypeChecker
    @display(description=_("Scan"), label={True: "success"})
    def scan(self, obj: Ticket):
        if obj.status == Ticket.NOT_SCANNED:
            scan_one = _("SCAN 1")
            scan_all = _("SCAN")
            ticket_count = Ticket.objects.filter(reservation=obj.reservation).count()
            if ticket_count > 1:  # Si on a plusieurs ticket dans la même reservation, on permet le scan tous les tickets
                return True, format_html(
                    f'<button><a href="{reverse("staff_admin:ticket-scann", args=[obj.pk])}" class="button">{scan_one}</a></button>&nbsp;'
                    f'  --  '
                    f'<button><a href="{reverse("staff_admin:ticket-scann", args=[obj.pk])}?all=True" class="button">{scan_all} {ticket_count}</a></button>&nbsp;',
                )
            return True, format_html(
                f'<button><a href="{reverse("staff_admin:ticket-scann", args=[obj.pk])}" class="button">{scan_one}</a></button>&nbsp;')
        return None, ""

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            re_path(
                r'^(?P<ticket_pk>.+)/scanner/$',
                self.admin_site.admin_view(self.scanner),
                name='ticket-scann',
            ),
        ]
        return custom_urls + urls

    def scanner(self, request, ticket_pk, *arg, **kwarg):
        list_to_scan = []
        ticket = Ticket.objects.get(pk=ticket_pk)
        list_to_scan.append(ticket)

        if request.GET.get('all') == 'True':
            list_to_scan = Ticket.objects.filter(reservation=ticket.reservation)

        for ticket in list_to_scan:
            if ticket.status == Ticket.NOT_SCANNED:
                ticket.status = Ticket.SCANNED
                ticket.save()

        return redirect(request.META["HTTP_REFERER"])

    @display(description=_("Ticket n°"))
    def ticket(self, instance: Ticket):
        return f"{instance.reservation.user_commande.email} {str(instance.uuid)[:8]}"

    actions_row = ["get_pdf"]

    @action(description=_("PDF"),
            url_path="ticket_pdf",
            permissions=["custom_actions_row"])
    def get_pdf(self, request, object_id):
        ticket = get_object_or_404(Ticket, uuid=object_id)

        VALID_TICKET_FOR_PDF = [Ticket.NOT_SCANNED, Ticket.SCANNED]
        if ticket.status not in VALID_TICKET_FOR_PDF:
            return Response('Invalid ticket', status=status.HTTP_403_FORBIDDEN)

        pdf_binary = create_ticket_pdf(ticket)
        response = HttpResponse(pdf_binary, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{ticket.pdf_filename()}"'
        return response

    def has_custom_actions_row_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        # Allow bulk actions in changelist for authorized tenant admins
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        # return request.user.is_superuser
        return False

    # def get_queryset(self, request):
    #     qs = super(TicketAdmin, self).get_queryset(request)
    #     future_events = qs.filter(
    #         reservation__event__datetime__gt=(timezone.localtime() - timedelta(days=2)).date(),
    #     )
    #     return future_events


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
        Pour la recherche de tenant dans la page Federation.
        On est sur un autocomplete, il faut bidouiller la réponde de ce coté
        Le but est que cela n'affiche dans le auto complete fields que les catégories Billets
        """
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        if request.headers.get('Referer'):
            logger.info(request.headers.get('Referer'))
            if ("federatedplace" in request.headers['Referer']
                    and "admin/autocomplete" in request.path):  # Cela vient bien de l'admin event
                queryset = queryset.exclude(categorie__in=[Client.WAITING_CONFIG, Client.ROOT, Client.META]).exclude(
                    pk=connection.tenant.pk)  # on retire le client actuel
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

@admin.register(FederationConfiguration, site=staff_admin_site)
class FederationConfigurationAdmin(SingletonModelAdmin, ModelAdmin):
    compressed_fields = True
    warn_unsaved_form = True

    autocomplete_fields = ["tags_federation"]

    fieldsets = (
        (_("Affichage des lieux"), {"fields": (
            "afficher_lieux_sans_adresse",
            "afficher_seulement_lieux_avec_event",
            "afficher_lieux_entrants",
            "tri_des_lieux",
        )}),
        # Federation automatique par tags : le tenant s'abonne a des tags et
        # recoit les events de TOUT le reseau qui les portent (agenda + carto).
        # / Tag-based auto federation: subscribe to tags, receive matching events
        # from the WHOLE network (agenda + map).
        (_("Fédération automatique par tags"), {"fields": ("tags_federation",)}),
        (_("Présentation"), {"fields": ("texte_introduction",)}),
        # Agenda participatif : active le formulaire public de proposition
        # d'evenement (deplace depuis le dashboard des modules vers ici).
        # / Participatory agenda: enables the public event-proposal form
        # (moved from the modules dashboard to here).
        (_("Agenda participatif"), {"fields": (
            "module_agenda_participatif",
            "proposition_anonyme_autorisee",
            "tag_auto_proposition",
        )}),
    )

    formfield_overrides = {
        models.TextField: {
            "widget": WysiwygWidget,
        }
    }

    def save_model(self, request, obj, form, change):
        # Sanitize les TextField pour eviter le XSS via WYSIWYG
        # / Sanitize TextFields to avoid XSS via WYSIWYG
        sanitize_textfields(obj)
        super().save_model(request, obj, form, change)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(FederatedPlace, site=staff_admin_site)
class FederatedPlaceAdmin(ModelAdmin):
    list_display = ["tenant", "str_tag_filter", "str_tag_exclude", "membership_visible", ]
    fields = ["tenant", "tag_filter", "tag_exclude", "membership_visible", ]
    autocomplete_fields = ["tag_filter", "tag_exclude", "tenant"]

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.select_related('tenant').prefetch_related('tag_filter', 'tag_exclude')

    # def formfield_for_foreignkey(self, db_field, request, **kwargs):
    #     if db_field.name == 'tenant':  # Replace 'user_field' with your actual field name
    #         kwargs['queryset'] = Client.objects.all().exclude(
    #             categorie__in=[Client.ROOT, Client.META, Client.WAITING_CONFIG]).exclude(
    #             pk=connection.tenant.pk)
    #     return super().formfield_for_foreignkey(db_field, request, **kwargs)

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
            # headers = {'x-api-key': obj.api_key}
            # check_api = requests.get(f'{obj.api_host}/api/v1/me', headers=headers)
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

        from sib_api_v3_sdk.rest import ApiException
        try:
            ghost_config = GhostConfig.get_solo()
            ghost_url = ghost_config.ghost_url
            ghost_key = ghost_config.get_api_key()
        except ApiException as e:
            ghost_config.last_log = f"{e}"
            logger.warning("ApiException when calling AccountApi->get_account: %s\n" % e)
            messages.error(request, _(f"Api not OK : {e}"))
            return redirect(request.META["HTTP_REFERER"])
        except Exception:
            messages.error(request, _("La connexion à l'API Ghost a échoué. L'API a potentiellement mal été configuré "))
            return redirect(request.META["HTTP_REFERER"])


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
        return False
        #return TenantAdminPermissionWithRequest(request)

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

    # def has_add_permission(self, request, obj=None):
    #     return TenantAdminPermissionWithRequest(request)

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
        # import ipdb; ipdb.set_trace()
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


# NOTE : `WaitingConfigAdmin` a ete migre vers `onboard/admin.py` lors
# de la session de cleanup legacy 2026-05-16. Cf.
# `TECH_DOC/SESSIONS/ONBOARD/03-session-recap.md`.
# / WaitingConfigAdmin moved to `onboard/admin.py` on 2026-05-16.


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


# ----------------------
# ModelAdmins CROWDS
# ----------------------


@admin.register(CrowdConfig, site=staff_admin_site)
class CrowdConfigAdmin(SingletonModelAdmin, ModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False

    fieldsets = (
        (_("Général"), {"fields": ("active",)}),
        (_("Affichage"), {"fields": (
            "title",
            "description",
            "vote_button_name",
            "name_goal",
            "name_funding",
            "name_participations",
            "contributor_covenant",
            "pro_bono_name",
        )}),
        # (_("Financement"), {"fields": (
        #     "global_funding_button",
        #     "global_funding_button_text",
        # )}),
    )

    formfield_overrides = {
        models.TextField: {
            "widget": WysiwygWidget,
        }
    }

    def save_model(self, request, obj, form, change):
        obj: CrowdConfig
        # Sanitize all TextField inputs to avoid XSS via WYSIWYG/TextField
        sanitize_textfields(obj)
        super().save_model(request, obj, form, change)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return False


# @admin.register(CrowdTag, site=staff_admin_site)
# class CrowdTagAdmin(ModelAdmin):
#     list_display = ("name", "slug", "color_bg", "color_preview")
#     search_fields = ("name", "slug")
#     prepopulated_fields = {"slug": ("name",)}
#     ordering = ("name",)
#     fields = ("name", "slug", "color_bg")
#
#     def color_preview(self, obj):
#         return format_html(
#             '<span style="display:inline-block;width:2rem;height:1rem;border-radius:.25rem;vertical-align:middle;{}"></span> '
#             '<span class="text-muted small">{}</span>',
#             obj.style_attr + ';border:1px solid rgba(0,0,0,.2)',
#             obj.color_bg,
#         )
#
#     color_preview.short_description = _("Aperçu")

# ----------------------
# INITIATIVE CROWDS
# ----------------------


class ContributionInline(TabularInline):
    """
    FR: Inline pour les contributions financières d'une initiative.
        L'ajout direct depuis l'admin est désactivé pour éviter les erreurs d'intégrité (ex: participant_id NULL).
    EN: Inline for financial contributions of an initiative.
        Direct addition from admin is disabled to prevent integrity errors (e.g. participant_id NULL).
    """
    model = Contribution
    fk_name = 'initiative'
    # FR: Ne pas proposer de nouvelle ligne par défaut / EN: No empty row by default
    extra = 0
    can_delete = True
    show_change_link = True
    # FR: Evite de charger 200k users dans un select: champ en saisie par ID
    # EN: Avoid loading 200k users in a select: field input by ID
    raw_id_fields = ("contributor",)

    fields = (
        "contributor_name",
        "contributor",
        "description",
        "amount",
        "amount_eur_display",
        "payment_status",
        "paid_at",
        "created_at",
    )
    readonly_fields = ("amount_eur_display", "created_at", "contributor")

    def amount_eur_display(self, obj):
        if not obj:
            return ""
        return f"{obj.amount_eur:.2f} {obj.initiative.currency}"

    amount_eur_display.short_description = _("Montant")

    # FR: Permissions : on INTERDIT l'ajout; seule la modification/suppression est permise
    # EN: Permissions: addition is FORBIDDEN; only modification/deletion is allowed
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("contributor", "initiative")


class VoteInline(TabularInline):
    model = Vote
    fk_name = 'initiative'
    extra = 0
    can_delete = True
    readonly_fields = ("created_at", "user")
    fields = ("user", "created_at")
    # Saisie par ID pour éviter l'autocomplete sur une très grande table user
    raw_id_fields = ("user",)

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        # Pas de modification du vote: on peut supprimer/ajouter
        return False

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("user")


class BudgetItemInline(TabularInline):
    """
    FR: Inline pour les lignes budgétaires (objectifs à financer).
        L'ajout direct est interdit ici pour forcer l'usage du front ou un flux contrôlé.
    EN: Inline for budget items (funding goals).
        Direct addition is forbidden here to force use of the front-end or a controlled flow.
    """
    model = BudgetItem
    fk_name = 'initiative'
    # FR: Ne pas proposer de nouvelle ligne par défaut / EN: No empty row by default
    extra = 0
    can_delete = True
    show_change_link = True
    # FR: Evite les gros menus déroulants de users / EN: Avoid large user dropdowns
    raw_id_fields = ("contributor", "validator")

    fields = (
        "contributor",
        "description",
        "amount",
        "state",
        "validator",
        "created_at",
    )
    readonly_fields = ("created_at", "contributor", "validator")

    # FR: Permissions: on INTERDIT l'ajout; seule la modification/suppression est permise
    # EN: Permissions: addition is FORBIDDEN; only modification/deletion is allowed
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("contributor", "validator")


class ParticipationInline(TabularInline):
    """
    FR: Inline pour les participations (actions des utilisateurs).
        L'ajout est bloqué car il manquait souvent le participant_id (IntegrityError).
    EN: Inline for participations (user actions).
        Addition is blocked because participant_id was often missing (IntegrityError).
    """
    model = Participation
    fk_name = 'initiative'
    # FR: On NE PROPOSE PAS de nouvelle ligne par défaut / EN: No empty row by default
    extra = 0
    # FR: Evite le chargement massif des users / EN: Avoid massive user loading
    raw_id_fields = ("participant",)
    fields = (
        "participant",
        "description",
        "amount",
        "state",
        "time_spent_minutes",
        "created_at",
        "updated_at",
    )
    readonly_fields = ("created_at", "updated_at", "participant")

    # FR: Permissions: on INTERDIT l'ajout; seule la modification/suppression est permise
    # EN: Permissions: addition is FORBIDDEN; only modification/deletion is allowed
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("participant")


# class InitiativeAdminForm(ModelForm):
#     funding_goal_eur = forms.DecimalField(
#         label=_("Objectif"),
#         help_text=_("Montant de l'objectif dans la devise de l'initiative (affiché en unités, enregistré en centimes)."),
#         decimal_places=2,
#         max_digits=12,
#         min_value=0,
#         required=True,
#         widget=UnfoldAdminTextInputWidget,
#     )
#
#     class Meta:
#         model = Initiative
#         fields = (
#             "name",
#             "short_description",
#             "description",
#             "funding_goal_eur",
#             "currency",
#             # "direct_debit",
#             "img",
#             "budget_contributif",
#         )
#
#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#         inst: Initiative | None = getattr(self, "instance", None)
#         if inst and getattr(inst, "pk", None):
#             try:
#                 self.fields["funding_goal_eur"].initial = (Decimal(inst.funding_goal or 0) / Decimal("100")).quantize(Decimal("0.01"))
#             except Exception:
#                 self.fields["funding_goal_eur"].initial = Decimal("0.00")
#
#     def save(self, commit=True):
#         instance: Initiative = super().save(commit=False)
#         # Convert euros to integer cents safely
#         value_eur: Decimal = self.cleaned_data.get("funding_goal_eur") or Decimal("0")
#         cents = int((value_eur.quantize(Decimal("0.01")) * 100).to_integral_value())
#         instance.funding_goal = max(0, cents)
#         if commit:
#             instance.save()
#             self.save_m2m()
#         return instance


@admin.register(Initiative, site=staff_admin_site)
class InitiativeAdmin(ModelAdmin):
    # form = InitiativeAdminForm
    list_display = (
        "name",
        "created_at",
        "funded_amount_display",
        "funding_goal_display",
        "progress_percent_int",
        "currency",
        "votes_count",
        # "requested_total_display",
    )

    fields = (
        "name",
        "short_description",
        "description",
        "currency",
        "img",
        "tags",
        "archived",
        "vote",
        "budget_contributif",
        "direct_debit",
        # "adaptative_funding_goal_on_participation",

    )

    list_filter = ("created_at", "tags")
    search_fields = ("name", "description", "tags__name")
    date_hierarchy = "created_at"
    inlines = [VoteInline, BudgetItemInline, ContributionInline, ParticipationInline]
    ordering = ("-created_at",)
    filter_horizontal = ("tags",)
    autocomplete_fields = ("tags",)
    # Optimise les requêtes en changelist (FK direct)
    list_select_related = ("asset",)

    formfield_overrides = {
        models.TextField: {
            "widget": WysiwygWidget,
        }
    }

    def get_queryset(self, request):
        # Optimise les agrégations et évite les N+1 en liste admin
        qs = super().get_queryset(request)
        qs = (
            qs
            .select_related("asset")
            .prefetch_related("tags")
            .annotate(
                funded_total=models.Sum("contributions__amount", distinct=True),
                funding_goal_total=models.Sum(
                    models.Case(
                        models.When(budget_items__state="approved", then=models.F("budget_items__amount")),
                        default=models.Value(0),
                        output_field=models.IntegerField(),
                    ),
                    distinct=True,
                ),
                votes_total=models.Count("votes", distinct=True),
            )
        )
        return qs

    def save_model(self, request, obj, form, change):
        obj: Initiative
        # Sanitize all TextField inputs to avoid XSS via WYSIWYG/TextField
        sanitize_textfields(obj)

        # FR: Si direct_debit est activé, vérifier qu'un compte Stripe est connecté.
        #     Sans Stripe, le paiement en ligne ne peut pas fonctionner.
        # EN: If direct_debit is enabled, check that a Stripe account is connected.
        if obj.direct_debit:
            config = Configuration.get_solo()
            stripe_est_configure = bool(
                config.stripe_connect_account or config.stripe_connect_account_test
            )
            if not stripe_est_configure:
                from django.contrib import messages
                obj.direct_debit = False
                messages.error(
                    request,
                    _("Paiement direct désactivé : aucun compte Stripe n'est connecté. "
                      "Configurez Stripe dans Paramètres avant d'activer le paiement direct.")
                )

        super().save_model(request, obj, form, change)

    def currency(self, obj: Initiative):
        if obj.asset:
            return obj.asset.currency_code
        return obj.currency

    currency.short_description = _("Devise")

    def funded_amount_display(self, obj):
        total = getattr(obj, "funded_total", None)
        if total is None:
            total = obj.total_funded_amount
        decimal_amount = Decimal(total or 0) / Decimal("100")
        return f"{decimal_amount:.2f}"

    funded_amount_display.short_description = _("Financé")

    def funding_goal_display(self, obj):
        # Objectif = somme des lignes budgétaires approuvées
        goal = getattr(obj, "funding_goal_total", None)
        if goal is None:
            goal = obj.total_funding_amount
        decimal_amount = Decimal(goal or 0) / Decimal("100")
        return f"{decimal_amount:.2f} {self.currency(obj)}"

    funding_goal_display.short_description = _("Objectif")

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)
