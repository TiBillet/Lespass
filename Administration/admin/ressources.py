"""
Enregistrements de l'administration Django pour le module booking.
/ Django admin registrations for the booking module.

LOCALISATION : booking/admin.py
"""
from django.contrib import admin
from django.forms import ModelForm
from django import forms
from unfold.admin import ModelAdmin, TabularInline
from unfold.widgets import UnfoldAdminSelect2Widget, UnfoldAdminDateWidget, UnfoldAdminSplitDateTimeWidget
from django.utils.translation import gettext_lazy as _
from unfold.widgets import (
    UnfoldAdminEmailInputWidget,
    UnfoldAdminSelectWidget,
    UnfoldAdminSelect2Widget,
    UnfoldAdminTextInputWidget,
)

from Administration.admin.site import staff_admin_site
from ApiBillet.permissions import TenantAdminPermissionWithRequest
from AuthBillet.models import TibilletUser
from AuthBillet.utils import get_or_create_user
from BaseBillet.models import Price, Product
from booking.models import (
    Booking,
    Calendar,
    ClosedPeriod,
    OpeningEntry,
    Resource,
    ResourceGroup,
    WeeklyOpening,
)


class ClosedPeriodInline(TabularInline):
    model = ClosedPeriod
    extra = 0


class OpeningEntryInline(TabularInline):
    model = OpeningEntry
    extra = 0


@admin.register(Calendar, site=staff_admin_site)
class CalendarAdmin(ModelAdmin):
    inlines = [ClosedPeriodInline]


    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)



@admin.register(WeeklyOpening, site=staff_admin_site)
class WeeklyOpeningAdmin(ModelAdmin):
    inlines = [OpeningEntryInline]

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


@admin.register(Booking, site=staff_admin_site)
class BookingAdmin(ModelAdmin):

    #TODO : Create a calendar view (reuse from lespass maybe) to create bookings

    ordering = ("-booked_at",)

    exclude = ["commande"]

    list_display = (
        'booked_at',
        'user',
        'resource',
        'status',
        'total_time',
        'total_paid',
    )


    # search_fields = ['event__name', 'user_commande__email', 'datetime', 'custom_form']
    list_filter = [
        'status',
        'start_datetime'
    ]

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)



class ResourceInline(TabularInline):
    model = Resource
    extra = 0
    fields = ['name', 'capacity', 'weekly_opening', 'calendar']


@admin.register(ResourceGroup, site=staff_admin_site)
class ResourceGroupAdmin(ModelAdmin):
    inlines = [ResourceInline]


class ResourceAddAdmin(ModelForm):

    # user = forms.ModelChoiceField(
    #     required=True,
    #     queryset=TibilletUser.objects.all(),
    #     empty_label=_("Sélectionnez un utilisateur"),  # Texte affiché par défaut
    #     label="Email",
    #     widget=UnfoldAdminSelect2Widget,
    # )
    #
    # prices = forms.ModelChoiceField(
    #     queryset=Price.objects.filter(product__categorie_article=Product.RESOURCE),
    #     empty_label=_("Sélectionnez un tarif"),  # Texte affiché par défaut
    #     required=True,
    #     widget=UnfoldAdminSelect2Widget,
    #     label=_("Ressource")
    # )

    class Meta:
        model = Resource
        fields = '__all__'
        # fields = ["group","calendar","weekly_opening","capacity","cancellation_deadline_hours","booking_horizon_days"]
        # widgets = {
        #     # "prices": UnfoldAdminSelect2Widget,
        #     "group": UnfoldAdminSelect2Widget,
        #     "calendar": UnfoldAdminSelect2Widget,
        #     "weekly_opening": UnfoldAdminSelect2Widget,
        # }


@admin.register(Resource, site=staff_admin_site)
class ResourceAdmin(ModelAdmin):
    # list_display = ['name', 'get_product_name', 'get_product_tags', 'capacity', 'weekly_opening', 'calendar']
    list_display = ['get_product_name', 'capacity', 'weekly_opening', 'calendar']

    form = ResourceAddAdmin

    autocomplete_fields = [
        # "tag",
        # "thematique",
        # # "options_radio",
        # # "options_checkbox",
        # "carrousel",

        # Le autocomplete fields + many2many ne permet pas de filtrage facile
        # Pour filter les produits de type billet, regarder le get_search_results dans ProductAdmin
        "product",
    ]

    @admin.display(description=_('Product Name'))
    def get_product_name(self, obj):
        return obj.product.name

    @admin.display(description=_('Product Tags'))
    def get_product_tags(self, obj):
        return obj.product.tag

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)
