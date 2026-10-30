"""
Enregistrements de l'administration Django pour le module booking.
/ Django admin registrations for the booking module.

LOCALISATION : booking/admin.py
"""
from django.contrib import admin
from django.db import connection, models
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from django.forms import ModelForm
from django.utils import timezone
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
from unfold.contrib.forms.widgets import WysiwygWidget
from Administration.admin.mixins import ExportCsvLisibleParExcelMixin
from Administration.importers.resources_bookings_exporters import BookingExportResource
from Administration.admin.site import staff_admin_site, sanitize_textfields
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

    # custom_form est retiré du formulaire : pas d'édition du JSON brut.
    # Les réponses s'affichent en tableau sous la fiche (change_form_after_template).
    # / custom_form is not editable as raw JSON; shown as a table below the form.
    exclude = ["commande", "custom_form"]
    change_form_after_template = "admin/booking/custom_form.html"

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
    # motif_du_refus : écrit par le bouton « Refuser » du panneau, jamais à la main.
    # / motif_du_refus: written by the panel's "Refuse" button, never by hand.
    readonly_fields = ["user", "motif_du_refus"]

    # Panneau « Valider / Refuser » d'une demande à validation manuelle, affiché AVANT
    # le formulaire. Les boutons appellent booking/views.py (admin_accept, admin_refuse).
    # / "Accept / Refuse" panel for a manual validation request, shown BEFORE the form.
    change_form_before_template = "admin/booking/actions_panel.html"

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        """
        Donne au panneau d'actions le booking et ce qu'il doit afficher.
        / Gives the action panel the booking and what it must show.

        LOCALISATION : Administration/admin/resources.py

        Contexte du panneau (admin/booking/actions_panel.html) :
        - booking_du_panneau : le booking, seulement si c'est une demande non payée
          (en attente, ou validée sans paiement). Sinon le panneau ne s'affiche pas.
        - tarif_de_la_demande : le tarif du créneau, pour l'information « adhésion ».
        - lien_de_paiement : l'adresse envoyée par mail (BookingViewSet.pay).
        """
        extra_context = extra_context or {}
        if object_id:
            booking = Booking.objects.select_related("user", "resource").filter(pk=object_id).first()
            if booking is not None and booking.est_une_demande_non_payee():
                extra_context["booking_du_panneau"] = booking

                ligne_du_creneau = booking.lignearticles.select_related("pricesold__price").first()
                if ligne_du_creneau is not None:
                    extra_context["tarif_de_la_demande"] = ligne_du_creneau.pricesold.price

                domaine_du_lieu = connection.tenant.get_primary_domain().domain
                extra_context["lien_de_paiement"] = f"https://{domaine_du_lieu}/booking/{booking.pk}/pay/"

        return super().changeform_view(request, object_id, form_url, extra_context)

    def save_model(self, request, obj, form, change):
        """
        Pose la date d'annulation quand l'admin passe le statut à annulé.
        La date d'annulation sert au récap du matin.
        / Sets the cancellation date when the admin switches the status to cancelled.

        LOCALISATION : Administration/admin/resources.py
        """
        statut_change = "status" in form.changed_data
        statut_annule = obj.status in (Booking.ADMIN_CANCELED, Booking.USER_CANCELED)
        if change and statut_change and statut_annule and obj.annulee_le is None:
            obj.annulee_le = timezone.now()
        super().save_model(request, obj, form, change)

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

    # INDISPENSABLE : on ne crée jamais une ressource depuis la fiche d'un groupe.
    # Une ressource exige un produit, absent de cet inline : la ligne partirait en
    # base sans produit et la page planterait. On crée la ressource dans l'admin
    # Ressources, et on y choisit son groupe.
    # / A resource is never created from a group page: it needs a product, which
    # this inline does not show. Create it from the Resource admin.
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


# Pas d'entrée dans le menu latéral : on gère les groupes depuis le formulaire
# d'une ressource. Le menu « ⋮ » à côté du champ « Groupe » ouvre cet admin en
# fenêtre pour ajouter ou modifier un groupe. INDISPENSABLE : sans cet
# enregistrement, ce menu disparaît.
# / Not in the sidebar: groups are managed from the resource form, whose "Group"
# field menu opens this admin in a popup. Keep it registered.
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

    # La description est du texte riche : éditeur WYSIWYG d'Unfold.
    # / The description is rich text: Unfold WYSIWYG editor.
    formfield_overrides = {
        models.TextField: {
            "widget": WysiwygWidget,
        }
    }

    @admin.display(description=_('Product Name'))
    def get_product_name(self, obj):
        return obj.product.name

    def save_model(self, request, obj, form, change):
        # INDISPENSABLE : la description est rendue avec |safe sur la page publique.
        # On nettoie tous les TextField (clean_html) avant d'enregistrer, contre le XSS.
        # / REQUIRED: the description is rendered with |safe. Sanitize against XSS.
        sanitize_textfields(obj)
        super().save_model(request, obj, form, change)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)
