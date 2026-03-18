import logging
from datetime import timedelta
from decimal import Decimal

from django.contrib import admin, messages
from django.db import models, IntegrityError, connection
from django.db.models import Count, Q, Prefetch
from django.forms import ModelForm
from django.http import HttpRequest
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from import_export.admin import ImportExportModelAdmin
from import_export import resources, fields
from import_export.widgets import ForeignKeyWidget
from unfold.admin import ModelAdmin, TabularInline
from unfold.contrib.filters.admin import RangeDateTimeFilter
from unfold.contrib.forms.widgets import WysiwygWidget
from unfold.contrib.import_export.forms import ExportForm, ImportForm
from unfold.decorators import display, action
from unfold.sections import TableSection

from Administration.admin.site import staff_admin_site, sanitize_textfields
from ApiBillet.permissions import TenantAdminPermissionWithRequest
from ApiBillet.serializers import get_or_create_price_sold
from BaseBillet.models import (
    Configuration, Event, Ticket, Reservation, PostalAddress
)

logger = logging.getLogger(__name__)


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
        EventArchiveFilter,
        ('datetime', RangeDateTimeFilter),
        'published',
    ]
    list_filter_submit = True

    autocomplete_fields = [
        "tag",
        "thematique",
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

        # Fabrication des pricesold event/prix pour pouvoir être selectionné sur le + billet
        for product in obj.products.all():
            for price in product.prices.all():
                get_or_create_price_sold(price=price, event=obj)

        try:
            super().save_model(request, obj, form, change)
        except IntegrityError as err:
            err_str = str(err)
            if (
                "BaseBillet_event_name_datetime" in err_str
                or ("duplicate key value violates unique constraint" in err_str and "(name, datetime)" in err_str)
            ):
                messages.error(request, _("event existe déja"))
                return redirect(request.META.get("HTTP_REFERER", reverse("admin:index")))
            logger.error(err)
            raise err
        except Exception as err:
            logger.error(err)
            raise err

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
            child_duplicate.carrousel.set(child.carrousel.all())

        return duplicate
