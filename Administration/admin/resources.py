"""
Enregistrements de l'administration Django pour le module booking.
/ Django admin registrations for the booking module.

LOCALISATION : booking/admin.py
"""
from django.contrib import admin
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from django.forms import ModelForm
from django import forms
# ModelAdmin vient de Administration/admin/base.py : c'est le ModelAdmin
# d'Unfold plus le placeholder de recherche tire de search_fields.
# / Project ModelAdmin: Unfold's, plus the search placeholder.
from Administration.admin.base import ModelAdmin
from unfold.admin import TabularInline
from unfold.contrib.filters.admin import ChoicesDropdownFilter
from unfold.widgets import UnfoldAdminSelect2Widget, UnfoldAdminDateWidget, UnfoldAdminSplitDateTimeWidget
from django.utils.translation import gettext_lazy as _
from unfold.widgets import (
    UnfoldAdminEmailInputWidget,
    UnfoldAdminSelectWidget,
    UnfoldAdminSelect2Widget,
    UnfoldAdminTextInputWidget,
)
from import_export.admin import ExportActionModelAdmin
from unfold.contrib.import_export.forms import ExportForm
from Administration.admin.mixins import ExportCsvLisibleParExcelMixin
from Administration.importers.resources_bookings_exporters import BookingExportResource
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
    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)



class OpeningEntryInline(TabularInline):
    model = OpeningEntry
    extra = 0
    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)



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
class BookingAdmin(ExportCsvLisibleParExcelMixin, ModelAdmin, ExportActionModelAdmin):

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
    # Filtre en liste déroulante (Unfold), envoyé par le bouton « Filtrer ».
    # / Dropdown filter (Unfold), sent by the "Filter" button.
    list_filter = [
        ('status', ChoicesDropdownFilter),
        'start_datetime'
    ]

    # Export lisible : date, heure de début et de fin à l'heure du lieu, statut en libellé.
    # / Readable export: date, start and end time in venue time, status as a label.
    resource_classes = [BookingExportResource]
    export_form_class = ExportForm

    def get_export_queryset(self, request):
        # La ressource et l'utilisateur sont lus à chaque ligne exportée :
        # on les charge en une seule requête.
        # / Resource and user are read on every exported row: load them in one query.
        queryset_de_l_export = super().get_export_queryset(request)
        queryset_de_l_export = queryset_de_l_export.select_related('resource', 'user')

        # Le total payé est calculé par la base, en une seule requête pour tout l'export.
        # Même règle que Booking.total_paid() : mêmes statuts (STATUTS_DES_LIGNES_PAYEES).
        # Coalesce : une réservation sans ligne payée vaut 0, pas None.
        # Lu par BookingExportResource.dehydrate_total_paye.
        # / Total paid summed by the database in one query, same rule as total_paid().
        lignes_payees = Q(lignearticles__status__in=Booking.STATUTS_DES_LIGNES_PAYEES)
        queryset_de_l_export = queryset_de_l_export.annotate(
            total_paye_en_centimes=Coalesce(
                Sum('lignearticles__total_ttc', filter=lignes_payees),
                0,
            )
        )
        return queryset_de_l_export

    # INDISPENSABLE : user reste en lecture seule. Les utilisateurs sont partagés entre
    # tous les lieux (AuthBillet est en SHARED_APPS). Modifiable, ce champ devient une
    # liste déroulante de TOUS les comptes de l'instance : page très lente, et emails
    # des autres lieux visibles par l'admin.
    # / user MUST stay read-only: users are shared across all tenants. Editable, it
    # renders a select of every account of the instance (slow, leaks other venues' emails).
    readonly_fields = ["user"]

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

    # Un inline a ses propres permissions : sans ces méthodes, Django demande
    # booking.view_resource…, que l'admin d'un lieu n'a pas, et la fiche du groupe
    # s'affiche sans ses ressources.
    # / An inline has its own permissions: without these, a venue admin sees the
    # group page without its resources.
    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


@admin.register(ResourceGroup, site=staff_admin_site)
class ResourceGroupAdmin(ModelAdmin):
    inlines = [ResourceInline]
    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


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
    list_display = ['name', 'capacity', 'weekly_opening', 'calendar']

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

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)
