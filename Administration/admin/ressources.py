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


class BookingAddAdmin(ModelForm):

    user = forms.ModelChoiceField(
        required=True,
        queryset=TibilletUser.objects.all(),
        empty_label=_("Sélectionnez un utilisateur"),  # Texte affiché par défaut
        label="Email",
        widget=UnfoldAdminSelect2Widget,
    )

    ressource = forms.ModelChoiceField(
        queryset=Resource.objects.all(),
        empty_label=_("Sélectionnez une ressource"),  # Texte affiché par défaut
        required=True,
        widget=UnfoldAdminSelect2Widget,
        label=_("Ressource")
    )

    debut_slot = forms.DateTimeField(
        label="Heure",
        widget=UnfoldAdminSplitDateTimeWidget
    )

    nombre_slot = forms.NumberInput()


# payment_method = forms.ChoiceField(
    #     required=False,
    #     choices=PaymentMethod.classic(),  # on retire les choix token
    #     widget=UnfoldAdminSelectWidget(),  # attrs={"placeholder": "Entrez l'adresse email"}
    #     label=_("Payment method"),
    # )
    #
    # quantity = forms.IntegerField(
    #     required=False,
    #     initial=1,
    #     min_value=1,
    #     max_value=32767,
    #     widget=UnfoldAdminTextInputWidget(attrs={"type": "number", "min": "1"}),
    #     label=_("Quantity"),
    # )

    class Meta:
        model = Booking
        fields = []
        # 'first_name',
        # 'last_name',
        # ]

    # TODO-ANTO : implement correctly save ++
    def save(self, commit=True):
        cleaned_data = self.cleaned_data

        email = self.cleaned_data.pop('email')
        user = get_or_create_user(email)

        booking: Booking = self.instance

        ressource: Resource = cleaned_data.pop('ressource')
        booking.resource = ressource

        booking = super().save(commit=commit)

        return booking

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

@admin.register(Booking, site=staff_admin_site)
class BookingAdmin(ModelAdmin):

    ordering = ("-booked_at",)

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
        return TenantAdminPermissionWithRequest(request)

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
