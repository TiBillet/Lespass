import logging
from datetime import timedelta
from typing import Any, Dict

from django import forms
from django.contrib import admin, messages
from django.forms import ModelForm
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, get_object_or_404
from django.urls import reverse, re_path
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from import_export.admin import ExportActionModelAdmin
from rest_framework import status
from rest_framework.response import Response
from unfold.admin import ModelAdmin
from unfold.contrib.import_export.forms import ExportForm
from unfold.decorators import display, action
from unfold.sections import TemplateSection
from unfold.widgets import (
    UnfoldAdminEmailInputWidget,
    UnfoldAdminSelectWidget,
    UnfoldAdminTextInputWidget,
)

from Administration.admin.site import staff_admin_site
from Administration.importers.ticket_exporter import TicketExportResource
from ApiBillet.permissions import TenantAdminPermissionWithRequest
from AuthBillet.utils import get_or_create_user
from BaseBillet.models import (
    Product, Reservation, Ticket, PriceSold, LigneArticle, PaymentMethod, SaleOrigin, Event
)
from BaseBillet.tasks import (
    ticket_celery_mailer, send_ticket_cancellation_user,
    send_reservation_cancellation_user, send_sale_to_laboutik,
    create_ticket_pdf
)

logger = logging.getLogger(__name__)


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

    search_fields = ['event__name', 'user_commande__email', 'datetime', 'custom_form']
    list_filter = [
        EventFutureFilter,
        ReservationValidFilter,
        'datetime',
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
        'event',
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
        return False
