import logging
from datetime import timedelta
from decimal import Decimal
from typing import Any
from unicodedata import category

import requests
import unfold.widgets
from django import forms
from django.conf import settings
from django.core.exceptions import MultipleObjectsReturned
from django.db import models, connection, IntegrityError
from django.contrib import admin
from django.contrib import messages
from django.db.models import Model
from django.forms import ModelForm, TextInput, Form, modelformset_factory
from django.forms.utils import ErrorList
from django.http import HttpResponse, HttpRequest, HttpResponseRedirect
from django.shortcuts import redirect, get_object_or_404
from django.template.defaultfilters import slugify
from django.urls import reverse, re_path
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from import_export.fields import Field
from import_export.widgets import ForeignKeyWidget, ManyToManyWidget
from rest_framework import status
from rest_framework.response import Response
from rest_framework_api_key.models import APIKey
from solo.admin import SingletonModelAdmin

from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display, action
from unfold.sites import UnfoldAdminSite
from unfold.widgets import UnfoldAdminTextInputWidget, UnfoldAdminEmailInputWidget, UnfoldAdminSelectWidget, \
    UnfoldAdminSelectMultipleWidget, UnfoldAdminRadioSelectWidget, UnfoldAdminCheckboxSelectMultiple
from unfold.contrib.forms.widgets import WysiwygWidget
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
# from simple_history.admin import SimpleHistoryAdmin

from import_export import resources, fields
from import_export.admin import ImportExportModelAdmin, ExportActionModelAdmin

from unfold.contrib.import_export.forms import ExportForm, ImportForm, SelectableFieldsExportForm

from ApiBillet.permissions import TenantAdminPermissionWithRequest, RootPermissionWithRequest
from AuthBillet.models import HumanUser, TibilletUser
from AuthBillet.utils import get_or_create_user
from BaseBillet.models import Configuration, OptionGenerale, Product, Price, Paiement_stripe, Membership, Webhook, Tag, \
    LigneArticle, PaymentMethod, Reservation, ExternalApiKey, GhostConfig, Event, Ticket, PriceSold, SaleOrigin, \
    FormbricksConfig, FormbricksForms, FederatedPlace, PostalAddress, Carrousel, BrevoConfig
from BaseBillet.tasks import create_membership_invoice_pdf, send_membership_invoice_to_email, webhook_reservation, \
    webhook_membership, create_ticket_pdf, ticket_celery_mailer
from Customers.models import Client
from MetaBillet.models import WaitingConfiguration
from fedow_connect.utils import dround

logger = logging.getLogger(__name__)


class StaffAdminSite(UnfoldAdminSite):
    pass


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
@admin.register(Configuration, site=staff_admin_site)
class ConfigurationAdmin(SingletonModelAdmin, ModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False

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
                'jauge_max',
                'allow_concurrent_bookings',
                # 'option_generale_radio',
                # 'option_generale_checkbox',
            ),
        }),
        ('Personnalisation', {
            'fields': (
                'membership_menu_name',
                'event_menu_name',
                'first_input_label_membership',
                'second_input_label_membership',
            ),
        }),
        ('Stripe', {
            'fields': (
                # 'vat_taxe',
                'onboard_stripe',
                # 'stripe_mode_test',
            ),
        }),
    )

    readonly_fields = ['onboard_stripe', ]
    autocomplete_fields = ['federated_with', ]

    formfield_overrides = {
        models.TextField: {
            "widget": WysiwygWidget,
        }
    }

    def save_model(self, request, obj, form, change):
        obj: Configuration
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
            'color': TextInput(attrs={'type': 'color'}),
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
        return format_html(
            '<div style="width: 20px; height: 20px; background-color: {}; border: 1px solid #000;"></div>',
            obj.color, )

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

    # ordering_field = "weight"
    # max_num = 1
    extra = 0
    show_change_link = True
    tab = True

    # Surcharger la méthode pour désactiver la suppression
    def has_delete_permission(self, request, obj=None):
        return False

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
            "legal_link",
            'publish',
            'archive',
        )

    def clean_categorie_article(self):
        cleaned_data = self.cleaned_data
        categorie = cleaned_data.get('categorie_article')
        if categorie == Product.NONE:
            raise forms.ValidationError(_("Please add at least one category to this product."))
        return categorie

    def clean(self):
        try:
            # récupération du dictionnaire data pour vérifier qu'on a bien au moin un tarif dans le inline :
            if int(self.data.getlist('prices-TOTAL_FORMS')[0]) > 0:
                return super().clean()
            raise forms.ValidationError(_("Please add at least one rate to this product."))
        except Exception as e:
            raise forms.ValidationError(_("Please add at least one rate to this product."))


@admin.register(Product, site=staff_admin_site)
class ProductAdmin(ModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False
    inlines = [PriceInline, ]

    form = ProductAdminCustomForm
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


class PriceChangeForm(ModelForm):
    # Le formulaire pour changer une adhésion
    class Meta:
        model = Price
        fields = (
            'name',
            'product',
            'prix',
            'free_price',
            'max_per_user',
            'subscription_type',
            'order',
            'publish',
            'adhesion_obligatoire',
        )

    def clean_prix(self):
        cleaned_data = self.cleaned_data
        prix = cleaned_data.get('prix')
        if 0 < prix < 1:
            raise forms.ValidationError(_("A rate cannot be between 0€ and 1€"), code="invalid")
        return prix

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Filtrage des produits : uniquement des produits adhésions.
        # Possible facilement car Foreign Key (voir get_search_results dans ProductAdmin)
        self.fields['adhesion_obligatoire'].queryset = Product.objects.filter(
            categorie_article=Product.ADHESION,
            archive=False,
        )


@admin.register(Price, site=staff_admin_site)
class PriceAdmin(ModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False
    form = PriceChangeForm

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
        # 'source_traitement',
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


class MembershipValid(admin.SimpleListFilter):
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
            ("O", _("No subscription")),

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
            return queryset.filter(
                memberships__deadline__lte=timezone.localtime(),
            ).distinct()
        if self.value() == "B":
            return queryset.filter(
                memberships__deadline__lte=timezone.localtime() + timedelta(weeks=2),
                memberships__deadline__gte=timezone.localtime(),
            ).distinct()
        if self.value() == 'O':
            return queryset.filter(memberships__isnull=True).distinct()


# Tout les utilisateurs de type HUMAIN
@admin.register(HumanUser, site=staff_admin_site)
class HumanUserAdmin(ModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False
    inlines = [MembershipInline, ]

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
        MembershipValid,
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

# L'objet pour la fonction EXPORT
class MembershipExportResource(resources.ModelResource):
    member_name = Field(attribute='member_name', column_name='member_name')
    email = Field(attribute='email', column_name='email')
    payment_method_name = Field(attribute='payment_method_name', column_name='payment_method_name')
    options = Field(attribute='options', column_name='options')
    status_name = Field(attribute='status_name', column_name='status_name')

    class Meta:
        model = Membership
        fields = (
            'last_contribution',
            'email',
            'member_name',
            'price__product__name',
            'price__name',
            'contribution_value',
            'payment_method_name',
            'options',
            'is_valid',
            'deadline',
            'status_name',
        )
        export_order = ('last_contribution',)


class EmailUserForeignKeyWidget(ForeignKeyWidget):
    def clean(self, value, row=None, **kwargs):
        try:
            val = super().clean(value)
        except TibilletUser.DoesNotExist:
            val = get_or_create_user(value, send_mail=False)
        return val

class PriceForeignKeyWidget(ForeignKeyWidget):
    def clean(self, value, row=None, **kwargs):
        try:
            val = super().clean(value)
        except MultipleObjectsReturned :
            val = Price.objects.get(name=value, product__name=row.get('product_name'))
        except Exception as err:
            raise err
        return val

class OptionsManyToManyWidgetWidget(ManyToManyWidget):
    def clean(self, value, row=None, **kwargs):
        if not value:
            return self.model.objects.none()
        else:
            objs = []
            names = value.split(self.separator)
            for name in names:
                if name.rstrip().lstrip() : # on supprime les espace avants et après
                    try :
                        option = OptionGenerale.objects.get(name=name)
                        objs.append(option)
                    except OptionGenerale.DoesNotExist:
                        option = OptionGenerale.objects.create(name=name)
                        objs.append(option)
            return objs

# Le moteur d'importation
class MembershipImportResource(resources.ModelResource):
    product_name = fields.Field(
        column_name='product_name',
        attribute='product_name',
        widget=ForeignKeyWidget(Product, field='name')) # renvoie une erreur si le produit n'existe pas

    price_name = fields.Field(
        column_name='price_name',
        attribute='price',
        widget=PriceForeignKeyWidget(Price, field='name')) # Vérfie que le price correspond bien au product

    # email = Field(attribute='email', column_name='email')

    email = fields.Field(
        column_name='email',
        attribute='user',
        widget=EmailUserForeignKeyWidget(TibilletUser, field='email')) # si l'user n'existe pas, va le créer

    option_generale = fields.Field(
        column_name='option_generale',
        attribute='option_generale',
        widget=OptionsManyToManyWidgetWidget(OptionGenerale, field='name', separator=';')
    )

    # def before_import_row(self, row, **kwargs):
    #     import ipdb; ipdb.set_trace()
    #
    # def after_import_row(self, row, row_result, **kwargs):
    #     import ipdb; ipdb.set_trace()

    def before_save_instance(self, instance, row, **kwargs):
        instance.status = Membership.IMPORT
        # import ipdb; ipdb.set_trace()

    class Meta:
        model = Membership
        fields = (
            'email',
            'first_name',
            'last_name',
            'last_contribution',
            'contribution_value',
            'product_name',
            'price_name',
            'option_generale',
            'commentaire',
        )
        import_id_fields = ('email',)

        widgets = {
            'last_contribution': {'format': '%d/%m/%Y'},
        }



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
        queryset=Price.objects.filter(product__categorie_article=Product.ADHESION),
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
        label=_("Contribution"),
    )

    payment_method = forms.ChoiceField(
        required=False,
        choices=PaymentMethod.not_online(),  # on retire les choix stripe
        widget=UnfoldAdminSelectWidget(),  # attrs={"placeholder": "Entrez l'adresse email"}
        label=_("Payment method"),
    )

    class Meta:
        model = Membership
        fields = [
            'last_name',
            'first_name',
            'option_generale',
        ]

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

        # Flotant (FALC) vers Decimal
        contribution = self.cleaned_data.pop('contribution')
        self.instance.contribution_value = dround(Decimal(contribution)) if contribution else 0

        # Mise à jour des dates de contribution :
        self.instance.first_contribution = timezone.localtime()
        self.instance.last_contribution = timezone.localtime()
        # self.instance.set_deadline()

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
        )


# Le petit badge route a droite du titre "adhésion"
def adhesion_badge_callback(request):
    # Recherche de la quantité de nouvelles adhésions ces 14 dernièrs jours
    return f"+ {Membership.objects.filter(last_contribution__gte=timezone.localtime() - timedelta(days=7)).count()}"


@admin.register(Membership, site=staff_admin_site)
class MembershipAdmin(ModelAdmin, ImportExportModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False

    resource_classes = [MembershipExportResource, MembershipImportResource]
    export_form_class = ExportForm
    import_form_class = ImportForm

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
        'is_valid',
        'status',
        'payment_method',
        # 'commentaire',
    )

    ordering = ('-date_added',)
    search_fields = ('user__email', 'user__first_name', 'user__last_name', 'card_number', 'last_contribution')
    list_filter = ['price__product', 'last_contribution', 'deadline', ]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.filter(last_contribution__isnull=False)

    ### FORMULAIRES
    autocomplete_fields = ['option_generale', ]

    def get_form(self, request, obj=None, **kwargs):
        """ Si c'est un add, on modifie un peu le formulaire pour avoir un champs email """
        defaults = {}
        if obj is None:
            defaults['form'] = self.add_form
        defaults.update(kwargs)
        return super().get_form(request, obj, **defaults)

    # Pour les bouton en haut de la vue change
    # chaque decorateur @action génère une nouvelle route
    actions_detail = ["send_invoice", "get_invoice"]

    @action(
        description=_("Send an invoice through email"),
        url_path="send_invoice",
        permissions=["custom_actions_detail"],
    )
    def send_invoice(self, request, object_id):
        membership = Membership.objects.get(pk=object_id)
        send_membership_invoice_to_email(membership)
        messages.success(
            request,
            _(f"Invoice sent to {membership.user.email}"),
        )
        return redirect(request.META["HTTP_REFERER"])

    @action(
        description=_("Build an invoice"),
        url_path="get_invoice",
        permissions=["custom_actions_detail"],
    )
    def get_invoice(self, request, object_id):
        membership = Membership.objects.get(pk=object_id)
        pdf_binary = create_membership_invoice_pdf(membership)
        response = HttpResponse(pdf_binary, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="facture.pdf"'
        return response
        # messages.success(
        #     request,
        #     _(f"Facture générée"),
        # )
        # return redirect(request.META["HTTP_REFERER"])

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

    list_display = [
        'productsold',
        'datetime',
        'amount_decimal',
        'qty',
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

        try:
            # On mets la valeur de la jauge réglée dans la config par default
            config = Configuration.get_solo()
            self.fields['jauge_max'].initial = config.jauge_max
        except Exception as e:
            logger.error(f"set gauge max error : {e}")
            pass

        # Filtrage des produits : uniquement des produits adhésions.
        # Possible facilement car Foreign Key (voir get_search_results dans ProductAdmin)
        # self.fields['adhesion_obligatoire'].queryset = Product.objects.filter(
        #     categorie_article=Product.ADHESION,
        #     archive=False,
        # )


@admin.register(Event, site=staff_admin_site)
class EventAdmin(ModelAdmin):
    form = EventForm
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False

    inlines = [EventChildrenInline, ]

    fieldsets = (
        (None, {
            'fields': (
                'name',
                # 'categorie',
                'datetime',
                'end_datetime',
                'img',
                'carrousel',
                'short_description',
                'long_description',
                'jauge_max',
                'postal_address',
                'published',
            )
        }),
        ('Bookings', {
            'fields': (
                # 'easy_reservation',
                'max_per_user',
                'products',
            ),
            "classes": ["tab"],
        }),
        ('Tags and forms', {
            'fields': (
                'tag',
                'options_radio',
                'options_checkbox',
            ),
            "classes": ["tab"],
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
        'valid_tickets_count',
        'datetime',
        'published',
    ]

    readonly_fields = (
        'valid_tickets_count',
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
        return queryset.exclude(categorie=Event.ACTION).exclude(parent__isnull=False)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Reservation, site=staff_admin_site)
class ReservationAdmin(ModelAdmin):
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
    search_fields = ['event__name', 'user_commande__email', 'options__name', 'datetime']
    list_filter = ['event', 'event__categorie', 'datetime', 'status', 'options']

    @display(description=_("Ticket count"))
    def tickets_count(self, instance: Reservation):
        return instance.tickets.count()

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
        return False

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class TicketAddAdmin(ModelForm):
    # Uniquement les tarif Adhésion
    email = forms.EmailField(
        required=True,
        widget=UnfoldAdminEmailInputWidget(),  # attrs={"placeholder": "Entrez l'adresse email"}
        label="Email",
    )

    pricesold = forms.ModelChoiceField(
        queryset=PriceSold.objects.filter(productsold__event__datetime__gte=timezone.localtime() - timedelta(days=1)),
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
        choices=PaymentMethod.not_online(),  # on retire les choix stripe
        widget=UnfoldAdminSelectWidget(),  # attrs={"placeholder": "Entrez l'adresse email"}
        label=_("Payment method"),
    )

    class Meta:
        model = Ticket
        fields = [
            'first_name',
            'last_name',
        ]

    def clean(self):
        return super().clean()

    def save(self, commit=True):
        cleaned_data = self.cleaned_data
        ticket: Ticket = self.instance
        # On indique que l'adhésion a été créé sur l'admin
        ticket.status = Ticket.CREATED
        ticket.sale_origin = SaleOrigin.ADMIN
        ticket.payment_method = self.cleaned_data.pop('payment_method')

        # Création de l'objet reservation avec l'user
        email = self.cleaned_data.pop('email')
        user = get_or_create_user(email)

        # Création de l'objet reservation
        pricesold: PriceSold = cleaned_data.pop('pricesold')
        event: Event = pricesold.productsold.event
        reservation = Reservation.objects.create(user_commande=user, event=event)
        ticket.reservation = reservation

        # On va chercher les options
        options_checkbox = cleaned_data.pop('options_checkbox')
        if options_checkbox:
            reservation.options.set(options_checkbox)
        options_radio = cleaned_data.pop('options_radio')
        if options_radio:
            reservation.options.add(options_radio)

        # Le post save BaseBillet.signals.create_lignearticle_if_membership_created_on_admin s'executera
        # # Création de la ligne Article vendu qui envera à la caisse si besoin
        return super().save(commit=commit)


class TicketChangeAdmin(ModelForm):
    class Meta:
        model = Ticket
        fields = [
            'first_name',
            'last_name',
        ]


@admin.register(Ticket, site=staff_admin_site)
class TicketAdmin(ModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False

    # Formulaire de modification
    form = TicketChangeAdmin
    # Formulaire de création. A besoin de get_form pour fonctionner
    add_form = TicketAddAdmin

    list_display = [
        'ticket',
        'first_name',
        'last_name',
        'event',
        'options',
        'state',
        'reservation__datetime',
    ]

    @admin.display(ordering='reservation__datetime', description='Booked at')
    def reservation__datetime(self, obj):
        return obj.reservation.datetime

    @admin.display(ordering='reservation__event', description='Event')
    def event(self, obj):
        if obj.reservation.event.parent:
            return f"{obj.reservation.event.parent} -> {obj.reservation.event}"
        return obj.reservation.event

    # list_editable = ['status',]
    # actions = [valider_ticket, ]
    ordering = ('-reservation__datetime',)
    # list_filter = [EventFilter, ]
    # list_filter = (F
    #     EventFilter,
    # 'reservation__uuid'
    # )
    list_filter = ["reservation__event", "status", "reservation__options"]

    search_fields = (
        'uuid',
        'first_name',
        'last_name',
        'reservation__user_commande__email'
    )

    # TODO: Checker un vrai bouton avec Unfold admin
    def state(self, obj):
        if obj.status == Ticket.NOT_SCANNED:
            return format_html(
                f'<button><a href="{reverse("staff_admin:ticket-scann", args=[obj.pk])}" class="button">Not scanned: scan ticket</a></button>&nbsp;',
            )
        elif obj.status == Ticket.SCANNED:
            return 'Validated / scanned'
        else:
            for choice in Reservation.TYPE_CHOICES:
                if choice[0] == obj.reservation.status:
                    return choice[1]

    state.short_description = 'State'
    state.allow_tags = True

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
        print(ticket_pk)
        ticket = Ticket.objects.get(pk=ticket_pk)
        ticket.status = Ticket.SCANNED
        ticket.save()
        messages.add_message(
            request,
            messages.SUCCESS,
            f"Ticket scanned successfully."
        )
        # context = self.admin_site.each_context(request)
        return HttpResponseRedirect(
            reverse("staff_admin:BaseBillet_ticket_changelist")
        )

    @display(description=_("Ticket n°"))
    def ticket(self, instance: Ticket):
        return f"{instance.reservation.user_commande.email} {str(instance.uuid)[:8]}"

    actions_detail = ["get_pdf", ]

    @action(description=_("PDF"),
            url_path="ticket_pdf",
            permissions=["custom_actions_detail"])
    def get_pdf(self, request, object_id):
        ticket = get_object_or_404(Ticket, uuid=object_id)

        VALID_TICKET_FOR_PDF = [Ticket.NOT_SCANNED, Ticket.SCANNED]
        if ticket.status not in VALID_TICKET_FOR_PDF:
            return Response('Invalid ticket', status=status.HTTP_403_FORBIDDEN)

        pdf_binary = create_ticket_pdf(ticket)
        response = HttpResponse(pdf_binary, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{ticket.pdf_filename()}"'
        return response

    def get_form(self, request, obj=None, **kwargs):
        """ Si c'est un add, on modifie le formulaire"""
        defaults = {}
        if obj is None:
            defaults['form'] = self.add_form
        defaults.update(kwargs)
        return super().get_form(request, obj, **defaults)

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
    list_display = ["tenant", "str_tag_filter", "str_tag_exclude", ]
    fields = ["tenant", "tag_filter", "tag_exclude", ]
    autocomplete_fields = ["tag_filter", "tag_exclude", ]

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'tenant':  # Replace 'user_field' with your actual field name
            kwargs['queryset'] = Client.objects.all().exclude(categorie__in=[Client.ROOT, Client.META]).exclude(pk=connection.tenant.pk)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

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
        fields = ['ghost_url', 'ghost_last_log']


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

    def save_model(self, request, obj: GhostConfig, form, change):
        if change:
            # headers = {'x-api-key': obj.api_key}
            # check_api = requests.get(f'{obj.api_host}/api/v1/me', headers=headers)
            obj.set_api_key(obj.ghost_key)
            messages.success(request, _("Api Key inserted"))
            # else:
            #     obj.api_key = None
            #     messages.error(request, "Api not OK")

        super().save_model(request, obj, form, change)

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
                categorie_article=Product.ADHESION,
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
        "laboutik_wanted",
        "id_acc_connect",
        "onboard_stripe_finished",
        "created",
    )

    fields = list_display
    readonly_fields = (
        "datetime",
    )

    ordering = ('-datetime',)

    list_filter = ["datetime", "created", "onboard_stripe_finished"]
    search_fields = ["email", "organisation", "datetime"]

    actions_detail = ["create_tenant", ]

    @action(description=_("Create instance"),
            url_path="create_tenant",
            permissions=["custom_actions_detail"])
    def create_tenant(self, request, object_id):
        wc = WaitingConfiguration.objects.get(pk=object_id)
        if wc.onboard_stripe_finished and wc.id_acc_connect:
            wc.create_tenant()
            messages.add_message(
                request, messages.SUCCESS,
                _(f"The Lèspass instance has been created. An invite email has been sent to {wc.email}")
            )
        else:
            messages.add_message(
                request, messages.WARNING,
                _(f"The collective is not yet finished with Stripe account creation.")
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
        fields = ['api_key', 'last_log',]

@admin.register(BrevoConfig, site=staff_admin_site)
class BrevoConfigAdmin(SingletonModelAdmin, ModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False

    readonly_fields = ['last_log', "has_key",]
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
            messages.error(request, _(f"Error : {type(e)} - {e}"))

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


### UNFOLD ADMIN
def environment_callback(request):
    if settings.DEBUG:
        return [_("Development"), "primary"]

    return [_("Production"), "primary"]


def dashboard_callback(request, context):
    context.update({
        "custom_variable": "value",
    })

    return context
