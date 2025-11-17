import json
import logging
import re
from datetime import timedelta
from decimal import Decimal
from typing import Any, Optional, Dict
from urllib.parse import urlencode
from uuid import UUID

import requests
import segno
from django import forms
from django.conf import settings
from django.contrib import admin
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.signing import TimestampSigner
from django.db import models, connection, IntegrityError
from django.db.models import Model, Count, Q, Prefetch
from django.forms import ModelForm, Form, HiddenInput
from django.http import HttpResponse, HttpRequest, HttpResponseRedirect
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
)

from Administration.importers.ticket_exporter import TicketExportResource
from Administration.utils import clean_html
from ApiBillet.permissions import TenantAdminPermissionWithRequest, RootPermissionWithRequest
from ApiBillet.serializers import get_or_create_price_sold
from AuthBillet.models import HumanUser, TibilletUser, Wallet
from AuthBillet.utils import get_or_create_user
from BaseBillet.models import Configuration, OptionGenerale, Product, Price, Paiement_stripe, Membership, Webhook, Tag, \
    LigneArticle, PaymentMethod, Reservation, ExternalApiKey, GhostConfig, Event, Ticket, PriceSold, SaleOrigin, \
    FormbricksConfig, FormbricksForms, FederatedPlace, PostalAddress, Carrousel, BrevoConfig, ScanApp, ProductFormField, \
    PromotionalCode
from BaseBillet.tasks import create_membership_invoice_pdf, send_membership_invoice_to_email, webhook_reservation, \
    webhook_membership, create_ticket_pdf, ticket_celery_mailer, send_ticket_cancellation_user, \
    send_reservation_cancellation_user, send_sale_to_laboutik
from Customers.models import Client
from MetaBillet.models import WaitingConfiguration
from crowds.models import Contribution, Vote, Participation, CrowdConfig, Initiative
from fedow_connect.fedow_api import FedowAPI
from fedow_connect.models import FedowConfig
from fedow_connect.utils import dround
from fedow_public.models import AssetFedowPublic as Asset, AssetFedowPublic

# from simple_history.admin import SimpleHistoryAdmin

logger = logging.getLogger(__name__)





def sanitize_textfields(instance: models.Model) -> None:
    """Sanitize all TextField values on a model instance in-place using clean_html.
    Only string values are sanitized; None and non-string values are ignored.
    """
    # pass
    for field in instance._meta.get_fields():
        if isinstance(field, models.TextField):
            field_name = field.name
            if hasattr(instance, field_name):
                value = getattr(instance, field_name)
                if isinstance(value, str) and value:
                    setattr(instance, field_name, clean_html(value))


class StaffAdminSite(UnfoldAdminSite):
    def login(self, request, extra_context=None):
        """
        Redirect admin login to the root URL for better security.
        """
        messages.add_message(request, messages.WARNING, _("Please login to access this page."))
        return HttpResponseRedirect('/')


staff_admin_site = StaffAdminSite(name='staff_admin')


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
    ]

    fields = [
        'name',
        'ip',
        'created',
        # Les boutons de permissions :
        ('event', 'product',),
        ('reservation', 'ticket'),
        ('wallet',),
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
                webhook_membership(membership.pk, solo_webhook_pk=object_id)
                webhook.refresh_from_db()
            elif webhook.event == Webhook.RESERVATION_V:
                # On va chercher le membership le plus récent
                reservation = Reservation.objects.filter(status=Reservation.VALID).first()
                webhook_reservation(reservation.pk, solo_webhook_pk=object_id)
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


########################################################################
# class ConfigurationAdminForm(ModelForm):
#     """Admin form to add a 'Nom de domaine' input with live slug preview that maps to Configuration.slug."""
#
#     domain_name = forms.CharField(
#         label=_("Sous domaine"),
#         max_length=100,
#         required=False,
#         help_text=mark_safe('''<span>Attention ! Changer ceci changera l'adresse de touuuuut votre espace</span></br><small>Slug: <code id="slug-preview"></code></small>'''),
#         widget=UnfoldAdminTextInputWidget(
#             attrs={
#                 # Live preview of slug using HTMX
#                 "hx-post": "slugify_preview/",
#                 "hx-trigger": "keyup changed delay:300ms",
#                 "hx-target": "#slug-preview",
#                 "hx-swap": "innerHTML",
#             }
#         ),
#     )
#
#     class Meta:
#         model = Configuration
#         fields = '__all__'
#
#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#         # Initialize domain_name from current slug (best effort)
#         if self.instance and getattr(self.instance, 'slug', ''):
#             self.fields['domain_name'].initial = self.instance.slug
#
#     def save(self, commit=True):
#         instance: Configuration = super().save(commit=False)
#         domain = self.cleaned_data.get('domain_name')
#         if domain:
#             instance.slug = slugify(domain)
#         if commit:
#             instance.save()
#             self.save_m2m()
#         return instance
#

@admin.register(Configuration, site=staff_admin_site)
class ConfigurationAdmin(SingletonModelAdmin, ModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False
    # form = ConfigurationAdminForm

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.select_related('postal_address').prefetch_related(
            'federated_with',
            'option_generale_radio',
            'option_generale_checkbox'
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
                # 'map_img',
            )
        }),
        ('Options générales', {
            'fields': (
                #         'need_name',
                'fuseau_horaire',
                'language',
                'jauge_max',
                'allow_concurrent_bookings',
                'currency_code',
                # 'option_generale_radio',
                # 'option_generale_checkbox',
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
                # 'stripe_mode_test',
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
    #
    # def get_urls(self):
    #     urls = super().get_urls()
    #     custom_urls = [
    #         re_path(
    #             r'^slugify_preview/$',
    #             self.admin_site.admin_view(csrf_protect(require_POST(self.slugify_preview))),
    #             name='configuration-slugify-preview',
    #         ),
    #     ]
    #     return custom_urls + urls
    #
    # def slugify_preview(self, request: HttpRequest):
    #     """HTMX endpoint: returns the slugified version of posted domain_name."""
    #     if not TenantAdminPermissionWithRequest(request):
    #         return HttpResponse("", status=403)
    #     value = request.POST.get('domain_name', '')
    #     return HttpResponse(slugify(value))

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


class PriceInlineChangeForm(ModelForm):
    # Le formulaire pour changer une adhésion
    class Meta:
        model = Price
        fields = (
            'name',
            'product',
            'prix',
            'free_price',
            'subscription_type',
            'publish',
        )

    def clean_prix(self):
        cleaned_data = self.cleaned_data
        prix = cleaned_data.get('prix')
        if 0 < prix < 1:
            raise forms.ValidationError(_("A rate cannot be between 0€ and 1€"), code="invalid")
        return prix

    def clean_subscription_type(self):
        cleaned_data = self.cleaned_data
        product: Product = cleaned_data.get('product')
        subscription_type = cleaned_data.get('subscription_type')
        if product.categorie_article == Product.ADHESION:
            if subscription_type == Price.NA:
                raise forms.ValidationError(_("A subscription must have a duration"), code="invalid")
        return subscription_type


class PriceInline(TabularInline):
    model = Price
    fk_name = 'product'
    form = PriceInlineChangeForm
    # hide_title = True
    # collapsible = True # usefull for StackedInline

    # ordering_field = "weight"
    # max_num = 1
    extra = 0
    show_change_link = True

    # tab = True # don't set to false : comment or the tab title will be visible

    # Surcharger la méthode pour désactiver la suppression
    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


class ProductFormFieldInlineForm(ModelForm):
    """
    Inline form that exposes a user-friendly CSV input for options on
    RADIO_SELECT and MULTI_SELECT field types, while storing a JSON list
    in the underlying `options` JSONField.
    """
    options_csv = forms.CharField(
        required=False,
        label=_("Choices"),
        help_text=_('For Single select (menu), Radio or Multiple select, enter choices separated by commas. Example: Rock, Electro, Jazz'),
        widget=UnfoldAdminTextInputWidget(attrs={"placeholder": "Rock, Electro, Jazz"}),
    )

    class Meta:
        model = ProductFormField
        # Exclude the real `options` field from the rendered form; it will be
        # set from `options_csv` in `clean()`/`save()`.
        fields = ("label", "field_type", "required", "help_text", "order")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Initialize CSV proxy from existing JSON list
        try:
            opts = self.instance.options if getattr(self, 'instance', None) else None
            if isinstance(opts, list) and all(isinstance(x, str) for x in opts):
                self.fields["options_csv"].initial = ", ".join(opts)
        except Exception:
            pass
        # Disable the Choices input unless type is Single/Radio/Multi select
        try:
            ftype = getattr(self.instance, 'field_type', None)
            selectable = ftype in (
                ProductFormField.FieldType.SINGLE_SELECT,
                ProductFormField.FieldType.RADIO_SELECT,
                ProductFormField.FieldType.MULTI_SELECT,
            )
            if not selectable:
                self.fields["options_csv"].widget.attrs["disabled"] = "disabled"
                # self.fields["options_csv"].widget.attrs["placeholder"] = "Inutile"
                # self.fields["options_csv"].widget.attrs["style"] = "display: none"
        except Exception:
            pass

    @staticmethod
    def _parse_csv_or_json(value: str):
        """Parse a CSV string or JSON array into a list of non-empty strings."""
        if value is None:
            return []
        s = str(value).strip()
        if not s:
            return []
        # If JSON-looking, try to parse first
        if s.startswith("[") or s.startswith("{"):
            try:
                data = json.loads(s)
                if isinstance(data, list):
                    res = []
                    for v in data:
                        if v is None:
                            continue
                        sv = str(v).strip()
                        if sv:
                            # Collapse internal multiple spaces
                            sv = re.sub(r"\s+", " ", sv)
                            if sv not in res:
                                res.append(sv)
                    return res
            except Exception:
                # fall back to CSV parsing
                pass
        # CSV path
        parts = [re.sub(r"\s+", " ", p.strip()) for p in s.split(",")]
        res = []
        for p in parts:
            if p and p not in res:
                res.append(p)
        return res

    def clean(self):
        cleaned = super().clean()
        ftype = cleaned.get("field_type")
        csv_val = cleaned.get("options_csv")
        # Manage options list for Single select, Radio and Multi select
        if ftype in (
            ProductFormField.FieldType.SINGLE_SELECT,
            ProductFormField.FieldType.RADIO_SELECT,
            ProductFormField.FieldType.MULTI_SELECT,
        ):
            options_list = self._parse_csv_or_json(csv_val)
            cleaned["options"] = options_list if options_list else None
        else:
            # For non-choice types, clear options to avoid stale data
            cleaned["options"] = None
        return cleaned

    def save(self, commit=True):
        """Ensure the cleaned options are written to the instance even if the
        underlying model field `options` is not rendered in the form/inline.
        """
        instance = super().save(commit=False)
        # Use cleaned_data computed in clean()
        if "options" in self.cleaned_data:
            instance.options = self.cleaned_data.get("options")
        if commit:
            instance.save()
        return instance


class ProductFormFieldInline(TabularInline):
    """Sortable inline for dynamic membership form fields (ProductFormField)."""
    model = ProductFormField
    fk_name = 'product'
    extra = 0
    show_change_link = True

    # Unfold sortable inline settings
    ordering_field = "order"
    hide_ordering_field = True

    # Put inline in its own tab in the Product admin change view
    tab = True

    # Columns in the inline rows (Unfold supports list_display for inlines)
    list_display = ["label", "field_type", "required", "order"]

    # Use custom form with CSV proxy field
    form = ProductFormFieldInlineForm

    # Fields displayed in the inline form (key is auto-generated from label)
    fields = (
        "label",
        "field_type",
        "required",
        "options_csv",
        "help_text",
        "order",
    )

    # Keep JSON widget small for advanced/legacy editing
    formfield_overrides = {
        models.JSONField: {"widget": forms.Textarea(attrs={"rows": 3})}
    }

    # Optional: show an information block before the inline (Unfold supports before templates on components)
    # list_before_template = "admin/product/product_form_fields_inline_before.html"

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


class ProductAdminCustomForm(ModelForm):
    class Meta:
        model = Product
        fields = (
            'name',
            'categorie_article',
            # 'nominative',
            'short_description',
            'long_description',
            'img',
            'poids',
            "option_generale_radio",
            "option_generale_checkbox",
            "validate_button_text",
            "legal_link",
            'publish',
            'archive',
        )
        help_texts = {
            'img': _('Product image is displayed at a 16/9 ratio.'),
        }

    categorie_article = forms.ChoiceField(
        required=False,
        choices=[
            (Product.NONE, _('Select a category')),
            (Product.BILLET, _('Ticket booking')),
            (Product.FREERES, _('Free booking')),
            (Product.ADHESION, _('Subscription or membership')),
            ],
        widget=UnfoldAdminSelectWidget(),  # attrs={"placeholder": "Entrez l'adresse email"}
        label=_("Payment method"),
    )

    def clean_categorie_article(self):
        cleaned_data = self.cleaned_data
        categorie = cleaned_data.get('categorie_article')
        if categorie == Product.NONE:
            raise forms.ValidationError(_("Please add at least one category to this product."))

        # Vérification que la clé Stripe est opérationnelle :
        if categorie != Product.FREERES:
            config = Configuration.get_solo()
            if not config.stripe_payouts_enabled:
                raise forms.ValidationError(
                    _("Your Stripe account is not activated. To create paid items, please go to Settings/Stripe/Onboard."))
        return categorie

    def clean(self):
        # Vérification qu'il existe au moins un tarif si produit payant
        if self.data.get('categorie_article') not in [Product.FREERES, Product.BADGE]:
            try:
                # récupération du dictionnaire data pour vérifier qu'on a bien au moin un tarif dans le inline :
                if int(self.data.getlist('prices-TOTAL_FORMS')[0]) > 0:
                    return super().clean()
                raise forms.ValidationError(_("Please add at least one rate to this product."))
            except Exception as e:
                raise forms.ValidationError(_("Please add at least one rate to this product."))


@register_component
class CheckStripeComponent(BaseComponent):
    def get_context_data(self, **kwargs):
        config = Configuration.get_solo()
        context = super().get_context_data(**kwargs)
        context["children"] = render_to_string(
            "admin/product/checkstripe_component.html",
            {
                "stripe_payouts_enabled": config.stripe_payouts_enabled,
            },
        )
        return context


@admin.register(Product, site=staff_admin_site)
class ProductAdmin(ModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False
    inlines = [PriceInline, ProductFormFieldInline]

    list_before_template = "admin/product/product_list_before.html"  # appelle le component CheckStripe plus haut pour le contexte

    form = ProductAdminCustomForm

    fieldsets = (
        (_('General'), {
            'fields': (
                'name',
                'categorie_article',
                'img',
                'poids',
                'short_description',
                'long_description',
                'max_per_user',
                'validate_button_text',
                'legal_link',
                'publish',
                'archive',
            ),
        }),
        (_('Options'), {
            'fields': (
                'option_generale_radio',
                'option_generale_checkbox',
            ),
        }),
    )

    list_display = (
        'name',
        'img',
        'categorie_article',
        'publish',
        'poids',
    )

    ordering = ("categorie_article", "poids",)
    autocomplete_fields = [
        "option_generale_radio", "option_generale_checkbox",
    ]
    list_filter = ['publish', 'categorie_article']
    search_fields = ['name']

    # Pour les bouton en haut de la vue change
    # chaque decorateur @action génère une nouvelle route
    actions_row = ["archive", ]

    formfield_overrides = {
        models.TextField: {
            "widget": WysiwygWidget,
        }
    }

    @action(
        description=_("Archive"),
        url_path="archive",
        permissions=["changelist_row_action"],
    )
    def archive(self, request, object_id):
        obj = get_object_or_404(Product, pk=object_id)
        obj.archive = True
        obj.save()
        messages.success(request, _(f"{obj.name} Archived"))
        return redirect(request.META["HTTP_REFERER"])

    def get_queryset(self, request):
        # On retire les recharges cashless et l'article Don
        # Pas besoin de les afficher, ils se créent automatiquement.
        qs = super().get_queryset(request)
        return qs.exclude(categorie_article__in=[Product.RECHARGE_CASHLESS, Product.DON]).exclude(archive=True)

    def get_search_results(self, request, queryset, search_term):
        """
        Pour la recherche de produit dans la page Event.
        On est sur un Many2Many, il faut bidouiller la réponde de ce coté
        Le but est que cela n'affiche dans le auto complete fields que les catégories Billets
        """
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        if request.headers.get('Referer'):
            logger.info(request.headers.get('Referer'))
            if ("event" in request.headers['Referer']
                    and "admin/autocomplete" in request.path):  # Cela vient bien de l'admin event
                queryset = queryset.filter(categorie_article__in=[
                    Product.BILLET,
                    Product.FREERES,
                ]).exclude(archive=True)
        return queryset, use_distinct

    def save_model(self, request, obj: Product, form, change):
        # Sanitize all TextField inputs to avoid XSS via WysiwYG/TextField
        sanitize_textfields(obj)
        try:
            super().save_model(request, obj, form, change)
        except IntegrityError as err:
            err_str = str(err)
            # Handle unique_together = ("categorie_article", "name") on Product
            if (
                "BaseBillet_product_categorie_article_name" in err_str
                or "BaseBillet_product_categorie_article_name_" in err_str
                or "duplicate key value violates unique constraint" in err_str and "(categorie_article, name)" in err_str
            ):
                messages.error(
                    request,
                    _(
                        "Un produit avec ce nom existe déjà dans cette catégorie.\n"
                        "Merci de choisir un autre nom pour éviter les doublons."
                    ),
                )
                # Stay on the same page
                return redirect(request.META.get("HTTP_REFERER", reverse("admin:index")))
            # Unknown integrity error: log and re-raise
            logger.error(err)
            raise err
        except Exception as err:
            logger.error(err)
            raise err

    # def save_model(self, request, obj, form, change):
    #     try:
    #         super().save_model(request, obj, form, change)
    #     except IntegrityError as err:
    #         if "BaseBillet_product_categorie_article_name" in str(err): # erreur pour         unique_together = ('categorie_article', 'name')
    #             messages.error(
    #                 request,
    #                 _(f"Un autre produit avec ce nom existe déja."),
    #             )
    #             return redirect(request.META["HTTP_REFERER"])
    #             # raise forms.ValidationError({"identifier": "This identifier is already in use."}) from err
    #         logger.error(err)
    #         raise err
    #     except Exception as err:
    #         logger.error(err)
    #         raise err

    def has_changelist_row_action_permission(self, request: HttpRequest, *args, **kwargs):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


@admin.register(PromotionalCode, site=staff_admin_site)
class PromotionalCodeAdmin(ModelAdmin):
    compressed_fields = True
    warn_unsaved_form = True

    list_display = (
        'name',
        'product',
        'discount_rate',
        'is_active',
        'usage_count',
        'usage_limit',
        'remaining_uses',
        'date_created',
    )

    fields = (
        'name',
        'product',
        'discount_rate',
        'is_active',
        'usage_limit',
        'usage_count',
    )

    readonly_fields = ('usage_count',)

    list_filter = ['is_active', 'product']
    search_fields = ['name', 'product__name']
    ordering = ('-date_created',)

    # pas d'auto complete sinon le formfield_for_foreignkey ne fonctionne pas, il faudra passer par le get_search_results coté ProductAdmin
    # autocomplete_fields = ['product']

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'product':  # Replace 'user_field' with your actual field name
            kwargs['queryset'] = Product.objects.filter(
                archive=False, categorie_article=Product.BILLET
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    @display(description=_("Remaining uses"))
    def remaining_uses(self, obj):
        remaining = obj.remaining_uses()
        if remaining is None:
            return _("Unlimited")
        return remaining

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


class PriceChangeForm(ModelForm):
    # Le formulaire pour changer un prix lorsque l'on clic sur modification
    class Meta:
        model = Price
        fields = (
            'name',
            'product',
            'prix',
            'free_price',
            'subscription_type',
            'recurring_payment',
            'iteration',
            'order',
            'publish',
            'max_per_user',
            'stock',
            'adhesion_obligatoire',
            # topup when paid :
            'fedow_reward_enabled',
            'fedow_reward_asset',
            'fedow_reward_amount',
        )

    def clean_recurring_payment(self):
        cleaned_data = self.cleaned_data  # récupère les donnée au fur et a mesure des validation, attention a l'ordre des fields
        recurring_payment = cleaned_data.get('recurring_payment')
        if recurring_payment:
            data = self.data  # récupère les data sans les avoir validé

            if hasattr(self.instance, 'product'):
                categorie_product = self.instance.product.categorie_article
            elif self.cleaned_data.get('product'):
                categorie_product = self.cleaned_data['product'].categorie_article
            else :
                raise forms.ValidationError(_("No product ?"), code="invalid")

            if categorie_product :
                if categorie_product != Product.ADHESION:
                    raise forms.ValidationError(
                    _("A recurring payment plan must have a membership-type product."), code="invalid")

            if data.get('subscription_type') not in [Price.DAY, Price.WEEK, Price.MONTH, Price.CAL_MONTH, Price.YEAR]:
                raise forms.ValidationError(_("A recurring payment must have a membership term. Re-enter the term just above."),
                                            code="invalid")

        return recurring_payment

    def clean_prix(self):
        cleaned_data = self.cleaned_data  # récupère les donnée au fur et a mesure des validation, attention a l'ordre des fields
        prix = cleaned_data.get('prix')
        if 0 < prix < 1:
            raise forms.ValidationError(_("A rate cannot be between 0€ and 1€"), code="invalid")

        return prix

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # On cache les options réservés aux adhésions
        try :
            instance: Price = kwargs.get('instance')
            if instance.product.categorie_article != Product.ADHESION:
                self.fields['subscription_type'].widget = HiddenInput()
                self.fields['recurring_payment'].widget = HiddenInput()
                self.fields['iteration'].widget = HiddenInput()
                self.fields['manual_validation'].widget = HiddenInput()
                self.fields['product'].widget = HiddenInput() # caché sauf si bouton + en haut a droite
                # Filtrage des produits : uniquement des produits adhésions.
                # Possible facilement car Foreign Key (voir get_search_results dans ProductAdmin)
                self.fields['adhesion_obligatoire'].queryset = Product.objects.filter(
                    categorie_article=Product.ADHESION,
                    archive=False,
                )
            elif instance.product.categorie_article == Product.ADHESION : # si c'est un produit qui n'est pas l'adhésion
                self.fields['product'].widget = HiddenInput() # caché sauf si bouton + en haut a droite
                self.fields['adhesion_obligatoire'].widget = HiddenInput()

        except AttributeError as e :
            # NoneType' object has no attribute 'product
            logger.info(f"Formulaire add : {e} ")
        except Exception as e :
            logger.error(f"Error in PriceChangeForm __init__ : {e}")
            raise e


        client: Client = connection.tenant
        # Limit the Asset choices to local tokens, time, and fidelity
        self.fields['fedow_reward_asset'].queryset = AssetFedowPublic.objects.filter(
            category__in=[
                Asset.TOKEN_LOCAL_FIAT,
                Asset.TOKEN_LOCAL_NOT_FIAT,
                Asset.TIME,
                Asset.FIDELITY,
            ],
            archive=False,
            origin=client,
        )

        # Improve display label: show name, currency and category
        def _label(obj):
            try:
                return f"{obj.name} ({obj.currency_code}) - {obj.get_category_display()}"
            except Exception:
                return str(obj)

        self.fields['fedow_reward_asset'].label_from_instance = _label


@admin.register(Price, site=staff_admin_site)
class PriceAdmin(ModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False
    form = PriceChangeForm

    conditional_fields = {
        "max_per_user": "free_price == false",
        "iteration": "recurring_payment == true",
        "commitment": "iteration > 0",
    }

    fieldsets = (
        (_('General'), {
            'fields': (
                'name',
                'product',
                ('prix', 'free_price'),
                'subscription_type',
                ('recurring_payment', 'iteration', 'commitment'),
                'manual_validation',
                'order',
                'max_per_user',
                'stock',
                'adhesion_obligatoire',
                'publish',
            ),
            'classes': ['tab'],
        }),
        (_('Triggers'), {
            'fields': (
                'fedow_reward_enabled',
                'reward_on_ticket_scanned',
                'fedow_reward_asset',
                'fedow_reward_amount',
            ),
            'classes': ['tab'],
        }),
    )

    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


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


class MembershipInline(TabularInline):
    model = Membership
    # form = MembershipInlineForm
    extra = 0
    # show_change_link = True
    can_delete = False
    tab = True

    fields = (
        'first_name',
        'last_name',
        'last_contribution',
        'price',
        'contribution_value',
        'deadline',
        'is_valid',
    )
    readonly_fields = fields

    def get_queryset(self, request):
        # On ne rend pas visible les adhésion qui n'ont pas eu de last_contribution
        return super().get_queryset(request).exclude(last_contribution=None)

    def has_change_permission(self, request, obj=None):
        return False  # On interdit la modification

    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request, obj=None):
        return False  # Autoriser l'ajout

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    # def formfield_for_foreignkey(self, db_field, request=None, **kwargs):
    #     if db_field.name == "price":  # Filtre sur le champ ForeignKey "prix"
    #         # Appliquez un filtre sur les objets accessibles via la ForeignKey
    #         kwargs["queryset"] = Price.objects.filter(product__categorie_article=Product.ADHESION,
    #                                                   publish=True)  # Exemple de filtre
    #     return super().formfield_for_foreignkey(db_field, request, **kwargs)
    #
    # # pour retirer les petits boutons add/edit a coté de la foreign key
    # def get_formset(self, request, obj=None, **kwargs):
    #     formset = super().get_formset(request, obj, **kwargs)
    #     price = formset.form.base_fields['price']
    #
    #     price.widget.can_add_related = False
    #     price.widget.can_delete_related = False
    #     price.widget.can_change_related = False
    #     price.widget.can_view_related = False
    #
    #     return formset


class is_tenant_admin(admin.SimpleListFilter):
    # Human-readable title which will be displayed in the
    # right admin sidebar just above the filter options.
    title = _("Administrator")

    # Parameter for the filter that will be used in the URL query.
    parameter_name = "is_admin"

    def lookups(self, request, model_admin):
        return [("Y", _("Yes")), ("N", _("No"))]

    def queryset(self, request, queryset):
        if self.value() == "Y":
            return queryset.filter(
                client_admin__in=[connection.tenant],
                is_staff=True,
                is_active=True,
                espece=TibilletUser.TYPE_HUM
            ).distinct()
        if self.value() == "N":
            return queryset.exclude(
                client_admin__in=[connection.tenant],
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
    warn_unsaved_form = True  # Default: False
    inlines = [MembershipInline, ]

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.prefetch_related('memberships', 'client_admin', 'client_achat')

    """
    On affiche en haut du changelist un bouton pour pouvoir changer sa carte 
    Change form view sert à donner le pk de l'user pour le bouton htmx
    """
    change_form_after_template = "admin/membership/get_wallet_info.html"

    def changeform_view(self, request: HttpRequest, object_id: Optional[str] = None, form_url: str = "",
                        extra_context: Optional[Dict[str, bool]] = None) -> Any:
        extra_context = extra_context or {}
        extra_context['object_id'] = object_id
        return super().changeform_view(request, object_id, form_url, extra_context)

    list_display = [
        'email',
        'first_name',
        'last_name',
        'display_memberships_valid',
        'is_active',
    ]

    search_fields = [
        'email',
        'first_name',
        'last_name',
    ]

    fieldsets = [
        ('Général', {
            'fields': [
                'email',
                ('first_name', 'last_name'),
                "is_active",
                ("email_valid", "email_error"),
                "administre",
            ],
        }),
    ]
    readonly_fields = ["email", "email_valid", "email_error", "administre", "achat", "client_source"]

    list_filter = [
        "is_active",
        "email_error",
        UserWithMembershipValid,
        "is_staff",
        "email_valid",
        "email_error",
        # "is_hidden",
        # ("salary", RangeNumericFilter),
        # ("status", ChoicesDropdownFilter),
        # ("created_at", RangeDateTimeFilter),
    ]

    # Pour les bouton en haut de la vue change
    # chaque decorateur @action génère une nouvelle route
    actions_detail = ["set_admin", "remove_admin"]

    @action(
        description=_("Give admin rights"),
        url_path="set_admin",
        permissions=["custom_actions_detail"],
    )
    def set_admin(self, request, object_id):
        user = HumanUser.objects.get(pk=object_id)
        if all([user.email_valid, user.is_active]) and not user.email_error:
            user.set_staff(connection.tenant)
            messages.success(request,
                             _(f"With great power comes great responsibilities. {user.email} has been promoted to admin."))
        else:
            messages.error(request, _(f"Does not fulfill condition: {user.email} needs to confirm their email."))

        return redirect(request.META["HTTP_REFERER"])

    @action(
        description=_("Strip admin rights"),
        url_path="remove_admin",
        permissions=["custom_actions_detail"],
    )
    def remove_admin(self, request, object_id):
        user = HumanUser.objects.get(pk=object_id)
        user.client_admin.remove(connection.tenant)
        messages.success(request, _(f"{user.email} has been demoted."))
        return redirect(request.META["HTTP_REFERER"])

    # noinspection PyTypeChecker
    @display(description=_("Subscriptions"), label={None: "danger", True: "success"})
    def display_memberships_valid(self, instance: HumanUser):
        count = instance.memberships_valid()
        if count > 0:
            return True, _(f"Valid: {count}")
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
        return TenantAdminPermissionWithRequest(request)


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
    price = forms.ModelChoiceField(
        queryset=Price.objects.filter(product__categorie_article=Product.ADHESION, product__archive=False),
        # Remplis le champ select avec les objets Price
        empty_label=_("Select an subscription"),  # Texte affiché par défaut
        required=True,
        widget=UnfoldAdminSelectWidget(),
        label=_("Subscriptions")
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
            'option_generale',
        ]

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
            linked_serialized_card = self.fedowAPI.NFCcard.linkwallet_card_number(user=user, card_number=self.card_number)

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
            'option_generale',
            'deadline',
            'commentaire',
            'custom_form',
        )

# Le petit badge route a droite du titre "adhésion"
def adhesion_badge_callback(request):
    # Recherche de la quantité de nouvelles adhésions ces 14 dernièrs jours
    return f"+ {Membership.objects.filter(last_contribution__gte=timezone.localtime() - timedelta(days=7)).count()}"


@register_component
class MembershipComponent(BaseComponent):
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Les adhésions en cours :
        active_count = Membership.objects.filter(deadline__gte=timezone.localtime()).count()
        # Les user qui n'ont pas d'adhésion en cours :
        inactive_count = HumanUser.objects.exclude(
            memberships__deadline__gte=timezone.localtime()
        ).distinct().count()

        context["children"] = render_to_string(
            "admin/membership/membership_component.html",
            {
                "type": kwargs.get('type'),
                "active": active_count,
                "inactive": inactive_count,
                "pending": Membership.objects.filter(state=Membership.ADMIN_WAITING).count(),
            },
        )
        return context


class MembershipCustomFormSection(TemplateSection):
    template_name = "admin/membership/custom_form_section.html"
    verbose_name = _("Custom form answers")


@admin.register(Membership, site=staff_admin_site)
class MembershipAdmin(ModelAdmin, ImportExportModelAdmin):
    # Expandable section to display custom form answers in changelist
    list_sections = [MembershipCustomFormSection]
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False

    resource_classes = [MembershipExportResource, MembershipImportResource]
    export_form_class = ExportForm
    import_form_class = ImportForm

    list_before_template = "admin/membership/membership_list_before.html"  # appelle le MembershipComponent plus haut pour le contexte

    # Formulaire de modification
    form = MembershipChangeForm
    # Formulaire de création. A besoin de get_form pour fonctionner
    add_form = MembershipAddForm

    list_display = (
        'email',
        'first_name',
        'last_name',
        'price',
        'contribution_value',
        'options',
        'last_contribution',
        'deadline',
        'display_is_valid',
        'status',
        'payment_method',
        # 'state_display',
        # 'commentaire',
    )

    ordering = ('-date_added',)
    search_fields = ('user__email', 'user__first_name', 'user__last_name', 'card_number', 'last_contribution',
                     'custom_form')
    list_filter = ['price__product', 'last_contribution', 'deadline', ]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return (
            qs.select_related('user', 'price', 'price__product')
            .prefetch_related('option_generale', 'price__product__form_fields')
        )

    ### FORMULAIRES
    autocomplete_fields = ['option_generale', ]

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
        option_ids = params.getlist('option_generale')
        if option_ids:
            # Keep as list of IDs (ModelMultipleChoiceField accepts IDs as initial)
            initial['option_generale'] = option_ids

        return initial

    # Pour les bouton en haut de la vue change
    # chaque decorateur @action génère une nouvelle route
    actions_detail = ["send_invoice", "get_invoice", "renouveller"]

    def changeform_view(self, request: HttpRequest, object_id: Optional[str] = None, form_url: str = "",
                        extra_context: Optional[Dict[str, bool]] = None):
        extra_context = extra_context or {}
        show_validation_buttons = False
        if object_id:
            try:
                membership = Membership.objects.get(pk=object_id)
                if membership.status == Membership.ADMIN_WAITING:
                    show_validation_buttons = True
            except Membership.DoesNotExist:
                show_validation_buttons = False
        extra_context["show_validation_buttons"] = show_validation_buttons
        return super().changeform_view(request, object_id, form_url, extra_context)

    @action(
        description=_("Send an receipt through email"),
        url_path="send_invoice",
        permissions=["custom_actions_detail"],
    )
    def send_invoice(self, request, object_id):
        membership = Membership.objects.get(pk=object_id)
        send_membership_invoice_to_email.delay(str(membership.uuid))
        messages.success(
            request,
            _(f"Invoice sent to {membership.user.email}"),
        )
        return redirect(request.META["HTTP_REFERER"])

    @action(
        description=_("Build an receipt"),
        url_path="get_invoice",
        permissions=["custom_actions_detail"],
    )
    def get_invoice(self, request, object_id):
        membership = Membership.objects.get(pk=object_id)
        pdf_binary = create_membership_invoice_pdf(membership)
        response = HttpResponse(pdf_binary, content_type='application/pdf')
        try :
            paiement_id = f"-{membership.stripe_paiement.order_by('-datetime').first().invoice_number()}"
        except:
            paiement_id = ""
        response['Content-Disposition'] = f'attachment; filename="receipt{paiement_id}.pdf"'
        return response
        # messages.success(
        #     request,
        #     _(f"Facture générée"),
        # )
        # return redirect(request.META["HTTP_REFERER"]) 

    @action(
        description=_("Renouveller"),
        url_path="renouveller",
        permissions=["custom_actions_detail"],
    )
    def renouveller(self, request, object_id):
        """Open the add form with the same information prefilled to renew a membership."""
        membership = Membership.objects.get(pk=object_id)

        # Build the admin add URL for this model on the current admin site
        opts = self.model._meta
        add_url = reverse(f"{self.admin_site.name}:{opts.app_label}_{opts.model_name}_add")

        # Base params from current membership
        params = {}
        if getattr(membership, 'user', None) and getattr(membership.user, 'email', None):
            params['email'] = membership.user.email
        if membership.price_id:
            params['price'] = membership.price_id
        if membership.contribution_value is not None:
            # Convert Decimal to string to avoid locale issues
            params['contribution'] = str(membership.contribution_value)
        if membership.payment_method:
            params['payment_method'] = membership.payment_method
        if membership.first_name:
            params['first_name'] = membership.first_name
        if membership.last_name:
            params['last_name'] = membership.last_name

        # ManyToMany: option_generale -> pass multiple query params
        option_ids = list(membership.option_generale.values_list('pk', flat=True))

        # Encode query string with doseq for multi-values
        query = urlencode(params, doseq=True)
        if option_ids:
            option_query = urlencode([("option_generale", oid) for oid in option_ids])
            query = f"{query}&{option_query}" if query else option_query

        return redirect(f"{add_url}?{query}")

    @display(description=_("Valid"), boolean=True)
    def display_is_valid(self, instance: Membership):
        return instance.is_valid()

    # @display(description=_("State"))
    # def state_display(self, instance: Membership):
        #### Show human-readable label for state, possibly with icon/color later
        # return instance.get_state_display()

    def has_custom_actions_detail_permission(self, request, object_id):
        return TenantAdminPermissionWithRequest(request)

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

@admin.register(LigneArticle, site=staff_admin_site)
class LigneArticleAdmin(ModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False

    list_filter = ('status', 'pricesold__productsold')

    list_display = [
        'productsold',
        'datetime',
        'amount_decimal',
        '_qty',
        'vat',
        'total_decimal',
        'display_status',
        'payment_method',
        'sended_to_laboutik',
    ]
    # fields = "__all__"
    # readonly_fields = fields

    ordering = ('-datetime',)

    def get_queryset(self, request):
        # Utiliser select_related pour précharger pricesold et productsold
        queryset = super().get_queryset(request)
        return queryset.select_related('pricesold__productsold')

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
    @display(description=_("Status"), label={None: "danger", True: "success"})
    def display_status(self, instance: LigneArticle):
        status = instance.status
        if status in [LigneArticle.VALID, LigneArticle.FREERES]:
            return True, f"{instance.get_status_display()}"
        return None, f"{instance.get_status_display()}"

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


@admin.register(Event, site=staff_admin_site)
class EventAdmin(ModelAdmin, ImportExportModelAdmin):
    form = EventForm
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False
    date_hierarchy = "datetime"
    ordering = ("-datetime",)
    # Unfold sections (expandable rows)
    list_sections = [
        EventPricesSummaryTable,
        ChildActionsSummaryTable,
    ]
    list_per_page = 20

    export_form_class = ExportForm
    import_form_class = ImportForm

    inlines = [EventChildrenInline, ]

    actions_row = ["duplicate_day_plus_one", "duplicate_week_plus_one", "duplicate_week_plus_two",
                   "duplicate_month_plus_one"]

    fieldsets = (
        (None, {
            'fields': (
                'name',
                # 'categorie',
                'datetime',
                'end_datetime',
                'img',
                'sticker_img',
                'carrousel',
                'short_description',
                'long_description',
                'jauge_max',
                'show_gauge',
                'postal_address',
            )
        }),
        (_('Tags and forms'), {
            'fields': (
                'tag',
                'options_radio',
                'options_checkbox',
            ),
        }),
        (_('Bookings'), {
            'fields': (
                # 'easy_reservation',
                'max_per_user',
                'products',
                'custom_confirmation_message',
                'refund_deadline',
            ),
        }),
        (_('Publish'), {
            'fields': (
                'published',
                'private',
            ),
        }),
        # ("Carrousel d'image", {
        #     'fields': (
        #         'carrousel',
        #     ),
        #     "classes": ["tab"],
        # }),
    )

    list_display = [
        'name',
        # 'categorie',
        'display_valid_tickets_count',
        'datetime',
        'published',
    ]

    list_editable = ['published', ]
    readonly_fields = (
        'display_valid_tickets_count',
    )

    search_fields = ['name']
    list_filter = [
        ('datetime', RangeDateTimeFilter),
        'published',
    ]
    list_filter_submit = True

    autocomplete_fields = [
        "tag",
        "options_radio",
        "options_checkbox",
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
                'tag', 'options_radio', 'options_checkbox', 'carrousel', 'products',
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

        # Fabrication des pricesold event/prix pour pouvoir être selectionné sur le + billet
        for product in obj.products.all():
            for price in product.prices.all():
                get_or_create_price_sold(price=price, event=obj)

        super().save_model(request, obj, form, change)

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
        duplicate.options_radio.set(obj.options_radio.all())
        duplicate.options_checkbox.set(obj.options_checkbox.all())
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
            child_duplicate.options_radio.set(child.options_radio.all())
            child_duplicate.options_checkbox.set(child.options_checkbox.all())
            child_duplicate.carrousel.set(child.carrousel.all())

        return duplicate


class ReservationValidFilter(admin.SimpleListFilter):
    # Pour filtrer sur les réservation valide : payée, payée et confirmée, et mail en erreur même si payés
    title = _("Valid")

    # Parameter for the filter that will be used in the URL query.
    parameter_name = "status_valid"

    def lookups(self, request, model_admin):
        return [
            ("Y", _("Yes")),
            ("N", _("No")),
        ]

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """
        if self.value() == "Y":
            return queryset.exclude(
                status__in=[
                    Reservation.CANCELED,
                    Reservation.CREATED,
                    Reservation.UNPAID,
                ]
            ).distinct()
        if self.value() == "N":
            return queryset.filter(
                status__in=[
                    Reservation.CANCELED,
                    Reservation.CREATED,
                    Reservation.UNPAID,
                ]
            ).distinct()



class ReservationAddAdmin(ModelForm):
    # Uniquement les tarif Adhésion
    email = forms.EmailField(
        required=True,
        widget=UnfoldAdminEmailInputWidget(),  # attrs={"placeholder": "Entrez l'adresse email"}
        label="Email",
    )

    pricesold = forms.ModelChoiceField(
        queryset=PriceSold.objects.filter(
            productsold__event__datetime__gte=timezone.localtime() - timedelta(days=1)).order_by(
            "productsold__event__datetime"),
        # Remplis le champ select avec les objets Price
        empty_label=_("Select a product"),  # Texte affiché par défaut
        required=True,
        widget=UnfoldAdminSelectWidget(),
        label=_("Rate")
    )

    options_checkbox = forms.ModelMultipleChoiceField(
        # Uniquement les options qui sont utilisé dans les évènements futurs
        required=False,
        queryset=OptionGenerale.objects.filter(
            options_checkbox__datetime__gte=timezone.localtime() - timedelta(days=1)),
        widget=UnfoldAdminCheckboxSelectMultiple(),
        label=_("Multiple choice menu"),
    )

    options_radio = forms.ModelChoiceField(
        # Uniquement les options qui sont utilisé dans les évènements futurs
        required=False,
        queryset=OptionGenerale.objects.filter(options_radio__datetime__gte=timezone.localtime() - timedelta(days=1)),
        widget=UnfoldAdminRadioSelectWidget(),
        label=_("Single choice menu"),
    )

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
        reservation.status = Reservation.VALID # automatiquement en VALID,on est sur l'admin
        # On va chercher les options
        options_checkbox = cleaned_data.pop('options_checkbox')
        if options_checkbox:
            reservation.options.set(options_checkbox)
        options_radio = cleaned_data.pop('options_radio')
        if options_radio:
            reservation.options.add(options_radio)

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
        vente = LigneArticle.objects.create(
            pricesold=pricesold,
            qty=quantity,
            amount=int(pricesold.prix * quantity * 100),
            payment_method=payment_method,
            status=LigneArticle.VALID,
        )
        # envoie à Laboutik
        send_sale_to_laboutik.delay(vente.pk)

        # Envoie des ticket par mail
        ticket_celery_mailer.delay(reservation.pk)


        return reservation

class ReservationCustomFormSection(TemplateSection):
    template_name = "admin/reservation/custom_form_section.html"
    verbose_name = _("Custom form answers")


@admin.register(Reservation, site=staff_admin_site)
class ReservationAdmin(ModelAdmin):
    # Expandable section to display custom form answers in changelist
    list_sections = [ReservationCustomFormSection]

    # Formulaire de création. A besoin de get_form pour fonctionner
    add_form = ReservationAddAdmin
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
        'options_str',
        'total_paid',
    )
    # readonly_fields = list_display
    search_fields = ['event__name', 'user_commande__email', 'options__name', 'datetime', 'custom_form']
    list_filter = ['event', ReservationValidFilter, 'datetime', 'options']

    # Bulk actions available in changelist
    actions = ["action_cancel_refund_reservations"]

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return (
            queryset
            .select_related('user_commande', 'event')
            .prefetch_related(
                'options',
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

    @display(description=_("Options"))
    def options_str(self, instance: Reservation):
        return " - ".join([option.name for option in instance.options.all()])

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
            ("Y", _("Yes")),
            ("N", _("No")),
        ]

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """
        if self.value() == "Y":
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
    list_filter = ["reservation__event", TicketValidFilter, "reservation__options"]
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
        'options',
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
                'reservation__options',
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
        return queryset.prefetch_related('domains').exclude(categorie__in=[Client.WAITING_CONFIG, Client.ROOT, Client.META])

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
                pk=connection.tenant.pk) # on retire le client actuel
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
    autocomplete_fields = ["tag_filter", "tag_exclude", "tenant" ]

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
            logger.error("ApiException when calling AccountApi->get_account: %s\n" % e)
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
            "name_funding_goal",
            "name_contributions",
            "name_participations",
        )}),
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
    model = Contribution
    fk_name = 'initiative'
    extra = 0
    can_delete = True
    show_change_link = True

    fields = ("contributor_name", "amount", "amount_eur_display", "payment_status", "paid_at")
    readonly_fields = ("amount_eur_display", )

    def amount_eur_display(self, obj):
        if not obj:
            return ""
        return f"{obj.amount_eur:.2f} {obj.initiative.currency}"

    amount_eur_display.short_description = _("Montant")

    # Surcharger la méthode pour désactiver la suppression
    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


class VoteInline(TabularInline):
    model = Vote
    fk_name = 'initiative'
    extra = 0
    can_delete = False
    readonly_fields = ("user", "created_at")
    fields = ("user", "created_at")

    # Surcharger la méthode pour désactiver la suppression
    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

class ParticipationInline(TabularInline):
    model = Participation
    fk_name = 'initiative'
    extra = 0
    fields = (
        "participant",
        "description",
        "requested_amount_cents",
        "state",
        "time_spent_minutes",
        "created_at",
        "updated_at",
    )
    readonly_fields = ("created_at", "updated_at")

    # Surcharger la méthode pour désactiver la suppression
    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

class InitiativeAdminForm(ModelForm):
    funding_goal_eur = forms.DecimalField(
        label=_("Objectif"),
        help_text=_("Montant de l'objectif dans la devise de l'initiative (affiché en unités, enregistré en centimes)."),
        decimal_places=2,
        max_digits=12,
        min_value=0,
        required=True,
        widget=UnfoldAdminTextInputWidget,
    )

    class Meta:
        model = Initiative
        fields = (
            "name",
            "short_description",
            "description",
            "funding_goal_eur",
            "currency",
            # "direct_debit",
            "img",
            "budget_contributif",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        inst: Initiative | None = getattr(self, "instance", None)
        if inst and getattr(inst, "pk", None):
            try:
                self.fields["funding_goal_eur"].initial = (Decimal(inst.funding_goal or 0) / Decimal("100")).quantize(Decimal("0.01"))
            except Exception:
                self.fields["funding_goal_eur"].initial = Decimal("0.00")

    def save(self, commit=True):
        instance: Initiative = super().save(commit=False)
        # Convert euros to integer cents safely
        value_eur: Decimal = self.cleaned_data.get("funding_goal_eur") or Decimal("0")
        cents = int((value_eur.quantize(Decimal("0.01")) * 100).to_integral_value())
        instance.funding_goal = max(0, cents)
        if commit:
            instance.save()
            self.save_m2m()
        return instance


@admin.register(Initiative, site=staff_admin_site)
class InitiativeAdmin(ModelAdmin):
    form = InitiativeAdminForm
    list_display = (
        "name",
        "created_at",
        "funded_amount_display",
        "funding_goal_display",
        "progress_percent_int",
        "currency",
        "votes_count",
        "requested_total_display",
    )

    fields = (
        "name",
        "short_description",
        "description",
        "funding_goal_eur",
        "currency",
        # "direct_debit",
        "img",
        "tags",
        "archived",
        "budget_contributif",
        "adaptative_funding_goal_on_participation",
    )

    list_filter = ("created_at", "tags")
    search_fields = ("name", "description", "tags__name")
    date_hierarchy = "created_at"
    inlines = [ContributionInline, ParticipationInline, ]
    ordering = ("-created_at",)
    filter_horizontal = ("tags",)
    autocomplete_fields = ("tags", )

    formfield_overrides = {
        models.TextField: {
            "widget": WysiwygWidget,
        }
    }

    def save_model(self, request, obj, form, change):
        obj: Initiative
        # Sanitize all TextField inputs to avoid XSS via WYSIWYG/TextField
        sanitize_textfields(obj)
        super().save_model(request, obj, form, change)

    def currency(self, obj: Initiative):
        if obj.asset :
            return obj.asset.currency_code
        return obj.currency

    currency.short_description = _("Devise")

    def funded_amount_display(self, obj):
        return f"{obj.funded_amount_eur:.2f}"

    funded_amount_display.short_description = _("Financé")

    def funding_goal_display(self, obj):
        return f"{obj.funding_goal_eur:.2f} {self.currency(obj)}"

    funding_goal_display.short_description = _("Objectif")

    def requested_total_display(self, obj):
        # Seules les participations approuvées par un·e admin sont comptées dans le total (voir modèle)
        color = obj.requested_ratio_color
        value = f"{obj.requested_total_eur:.2f} {self.currency(obj)}"
        return format_html('<span class="badge text-bg-{}">{}</span>', color, value)

    requested_total_display.short_description = _("Demandes validées")




### UNFOLD ADMIN DASHBOARD
def environment_callback(request):
    if settings.DEBUG:
        return [_("Development"), "primary"]

    return [_("Production"), "primary"]


def dashboard_callback(request, context):
    context.update({
        "custom_variable": "value",
    })

    return context
