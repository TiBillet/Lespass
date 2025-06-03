from django.utils.translation import gettext_lazy as _
from import_export import resources, fields
from import_export.fields import Field
from django import forms
import pytz

from BaseBillet.models import Ticket, Event, Configuration
from unfold.contrib.import_export.forms import ExportForm


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

    class Meta:
        model = Ticket
        fields = (
            'event_name',
            'event_datetime',
            # 'first_name',
            # 'last_name',
            'status_display',
            'price_name',
            'product_name',
            'options',
            'reservation_datetime',
            'payment_method_display',
        )
        export_order = ('event_name', 'event_datetime', 'first_name', 'last_name')

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
