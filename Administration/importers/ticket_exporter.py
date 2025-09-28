from django.utils.translation import gettext_lazy as _
from import_export import resources, fields
from import_export.fields import Field
from django import forms
import pytz

from BaseBillet.models import Ticket, Event, Configuration
from unfold.contrib.import_export.forms import ExportForm


class JSONKeyField(Field):
    """A Field that exports a value from Reservation.custom_form for a given key."""
    def __init__(self, key: str, column_name: str = None):
        # attribute isn't used for value extraction; keep None
        super().__init__(column_name=column_name or key)
        self.key = key

    def get_value(self, obj):
        # obj is a Ticket; fetch parent reservation.custom_form
        reservation = getattr(obj, 'reservation', None)
        data = getattr(reservation, 'custom_form', None) if reservation else None
        if isinstance(data, dict):
            import json as _json
            value = data.get(self.key)
            if isinstance(value, (dict, list)):
                return _json.dumps(value, ensure_ascii=False)
            return value
        return None


class TicketExportResource(resources.ModelResource):
    # Define fields from related models
    event_name = Field(attribute='reservation__event__name', column_name='event_name')
    event_datetime = Field(column_name='event_datetime')
    # first_name = Field(attribute='first_name', column_name='first_name')
    # last_name = Field(attribute='last_name', column_name='last_name')
    status_display = Field(attribute='get_status_display', column_name='status')
    price_name = Field(attribute='pricesold__price__name', column_name='price_name')
    product_name = Field(attribute='pricesold__productsold__product__name', column_name='product_name')
    options = Field(attribute='options', column_name='options')
    reservation_datetime = Field(column_name='reservation_datetime')
    payment_method_display = Field(attribute='get_payment_method_display', column_name='payment_method')

    # Formbricks fields
    email = Field(attribute='reservation__user_commande__email', column_name='email')
    user_id = Field(column_name='userId')
    reservation_uuid = Field(attribute='reservation__uuid', column_name='reservation_uuid')

    # --- Dynamic columns for Reservation.custom_form ---
    def before_export(self, queryset, *args, **kwargs):
        # Collect all keys from parent reservation.custom_form JSON across queryset
        keys = set()
        try:
            for obj in queryset:
                reservation = getattr(obj, 'reservation', None)
                data = getattr(reservation, 'custom_form', None) if reservation else None
                if isinstance(data, dict):
                    for k in data.keys():
                        if k is not None:
                            keys.add(str(k))
        except Exception:
            pass
        # Store sorted keys for deterministic column order
        self._custom_form_keys = sorted(keys)

    def get_export_fields(self, *args, **kwargs):
        base_fields = super().get_export_fields(*args, **kwargs)
        # Avoid duplicates by column name
        existing = set()
        for f in base_fields:
            name = getattr(f, 'column_name', None) or getattr(f, 'attribute', None)
            if name:
                existing.add(str(name))
        dynamic_fields = []
        for key in getattr(self, '_custom_form_keys', []):
            if key not in existing:
                dynamic_fields.append(JSONKeyField(key=key, column_name=key))
        return base_fields + dynamic_fields

    def get_export_headers(self, selected_fields=None, *args, **kwargs):
        # Build headers directly from field column names to support dynamic fields
        fields = selected_fields or self.get_export_fields(*args, **kwargs)
        return [f.column_name for f in fields]

    def get_field_name(self, field):
        # Gracefully handle dynamically generated JSONKeyField instances
        if isinstance(field, JSONKeyField):
            return field.column_name
        return super().get_field_name(field)


    def dehydrate_user_id(self, ticket):
        """
        Format user_id as "email uuid[:4]"
        """
        if ticket.reservation and ticket.reservation.user_commande:
            email = ticket.reservation.user_commande.email
            uuid_prefix = str(ticket.reservation.uuid)[:4]
            return f"{email} {uuid_prefix}"
        return ""

    class Meta:
        model = Ticket
        fields = (
            'event_name',
            'event_datetime',
            'email',
            'user_id',
            'reservation_uuid',
            # 'first_name',
            # 'last_name',
            'status_display',
            'price_name',
            'product_name',
            'options',
            'reservation_datetime',
            'payment_method_display',
        )
        export_order = ('event_name', 'event_datetime', 'first_name', 'last_name', 'email', 'user_id', 'reservation_uuid')

    def dehydrate_event_datetime(self, ticket):
        """
        Format event_datetime in a human-readable format with the venue's timezone.
        """
        if ticket.reservation and ticket.reservation.event and ticket.reservation.event.datetime:
            tzlocal = pytz.timezone(Configuration.get_solo().fuseau_horaire)
            localized_datetime = ticket.reservation.event.datetime.astimezone(tzlocal)
            return localized_datetime.strftime('%d/%m/%Y %H:%M')
        return ""

    def dehydrate_reservation_datetime(self, ticket):
        """
        Format reservation_datetime in a human-readable format with the venue's timezone.
        """
        if ticket.reservation and ticket.reservation.datetime:
            tzlocal = pytz.timezone(Configuration.get_solo().fuseau_horaire)
            localized_datetime = ticket.reservation.datetime.astimezone(tzlocal)
            return localized_datetime.strftime('%d/%m/%Y %H:%M')
        return ""

    def filter_queryset(self, queryset, request=None):
        # Filter queryset based on the selected event
        event_id = None

        # Try to get event_id from different possible sources
        if request:
            # Check if event_id is in POST data
            if hasattr(request, 'POST') and request.POST.get('event'):
                event_id = request.POST.get('event')
            # Check if event_id is in GET data
            elif hasattr(request, 'GET') and request.GET.get('event'):
                event_id = request.GET.get('event')
            # Check if event_id is directly attached to the request
            elif hasattr(request, 'event'):
                event_id = request.event
            # Check if there's a form_data attribute
            elif hasattr(request, 'form_data') and request.form_data.get('event'):
                event_id = request.form_data.get('event')

            # Check if status_valid=Y is in the URL
            status_valid = None
            if hasattr(request, 'GET') and request.GET.get('status_valid'):
                status_valid = request.GET.get('status_valid')

        if event_id:
            queryset = queryset.filter(reservation__event_id=event_id)

        # Filter by valid status if status_valid=Y is in the URL
        if request and hasattr(request, 'GET') and request.GET.get('status_valid') == 'Y':
            queryset = queryset.filter(status__in=[Ticket.NOT_SCANNED, Ticket.SCANNED])

        return queryset


# class TicketExportForm(ExportForm):
#     event = forms.ModelChoiceField(
#         queryset=Event.objects.all(),
#         required=False,
#         label=_("Event"),
#         help_text=_("Select an event to filter tickets")
#     )
