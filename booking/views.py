"""
Vues de l'app booking — réservation de ressources partagées.
/ booking app views — shared resource reservation.

LOCALISATION : booking/views.py

Flux v0.1 : GET/POST simples, réservation directement en statut 'confirmed'.
/ v0.1 flow: simple GET/POST, booking created directly with status 'confirmed'.
"""
import datetime
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from urllib.parse import urlencode
from django_htmx.http import HttpResponseClientRedirect
from django.http import Http404, HttpResponseBadRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import permissions, viewsets
from django.contrib import messages
from django.utils.translation import gettext_lazy as _, ngettext
from rest_framework.decorators import action

from BaseBillet.models import Price, Paiement_stripe
from BaseBillet.views import get_context
from booking.booking_engine import Interval, compute_slots, validate_new_booking
from booking.models import Booking, Resource
from booking.serializers import BookingCreateSerializer
from booking.tasks import send_booking_cancellation_user


logger = logging.getLogger(__name__)


# ── Display layer ────────────────────────────────────────────────────────────


@dataclass
class DisplaySlot:
    """
    Représentation d'un créneau pour l'affichage.
    Construite par annotate_slots_for_display() depuis des BookableInterval.
    / View-layer representation of a bookable slot.
    Built by annotate_slots_for_display() from BookableInterval objects.
    """
    start:                 datetime.datetime
    end:                   datetime.datetime
    remaining_capacity:    int
    slot_duration_minutes: int
    is_new_week:           bool = False
    in_cart:               bool = False



@dataclass
class DisplaySlotGroup:
    """
    Séquence contiguë de DisplaySlot de même durée
    (x.end == next.start et x.slot_duration_minutes == next.slot_duration_minutes).
    Un créneau isolé a un groupe à un seul élément.
    / A contiguous run of DisplaySlot objects sharing the same duration
    (x.end == next.start and x.slot_duration_minutes == next.slot_duration_minutes).
    / A solo slot has slots=[itself].
    """
    slots: list = field(default_factory=list)  # list[DisplaySlot]

    @property
    def start(self) -> datetime.datetime:
        return self.slots[0].start

    @property
    def end(self) -> datetime.datetime:
        return self.slots[-1].end


def annotate_slots_for_display(raw_slots):
    """
    Convertit une liste de BookableInterval en objets d'affichage.
    / Converts a list of BookableInterval objects into display-layer objects.

    LOCALISATION : booking/views.py

    Retourne list[DisplaySlotGroup]. Chaque groupe contient une séquence
    contiguë de DisplaySlot de même durée.
    / Returns list[DisplaySlotGroup]. Each group holds a contiguous run of
    DisplaySlot objects sharing the same duration.

    Passe 1 : crée un DisplaySlot par créneau avec is_new_week calculé.
    Passe 2 : groupe les DisplaySlot contigus en DisplaySlotGroup.
    / Pass 1: create DisplaySlot per slot with is_new_week computed globally.
    / Pass 2: group consecutive DisplaySlot objects into DisplaySlotGroup runs.

    :param raw_slots: list[BookableInterval]
    :return: list[DisplaySlotGroup]
    """
    # Passe 1 : crée les DisplaySlot avec le marqueur de semaine.
    # / Pass 1: create DisplaySlot objects with the week marker.
    display_slots = []
    for i, slot in enumerate(raw_slots):
        is_new_week = (
            i > 0
            and slot.start.isocalendar()[:2] != raw_slots[i - 1].start.isocalendar()[:2]
        )
        display_slots.append(DisplaySlot(
            start=slot.start,
            end=slot.end,
            remaining_capacity=slot.remaining_capacity,
            slot_duration_minutes=slot.duration_minutes(),
            is_new_week=is_new_week,
        ))

    # Passe 2 : regroupe les créneaux contigus en DisplaySlotGroup.
    # / Pass 2: group contiguous slots into DisplaySlotGroup runs.
    if not display_slots:
        return []

    groups = []
    current_run = [display_slots[0]]
    for ds in display_slots[1:]:
        same_duration = ds.slot_duration_minutes == current_run[-1].slot_duration_minutes
        contiguous    = ds.start == current_run[-1].end
        if contiguous and same_duration:
            current_run.append(ds)
        else:
            groups.append(DisplaySlotGroup(slots=current_run))
            current_run = [ds]
    groups.append(DisplaySlotGroup(slots=current_run))
    return groups


# ── ViewSet ──────────────────────────────────────────────────────────────────


class BookingViewSet(viewsets.ViewSet):
    """
    Vues du module booking — flux GET/POST simples.
    / booking module views — simple GET/POST flow.

    LOCALISATION : booking/views.py
    """
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def _group_resources(self):
        """
        Charge toutes les ressources et les répartit par groupe.
        Retourne (resources_groups, ungrouped_resources).
        / Loads all resources and splits them by group.
        Returns (resources_groups, ungrouped_resources).

        LOCALISATION : booking/views.py

        """
        all_resources = list(
            Resource.objects.select_related('group', 'product').order_by('product__name')
        )

        items_by_group  = defaultdict(list)
        ungrouped_resources = []

        for resource in all_resources:
            if resource.group:
                items_by_group[resource.group].append(resource)
            else:
                ungrouped_resources.append(resource)

        # Trie les groupes par nom, puis les ressources dans chaque groupe.
        # / Sort groups by name, then resources within each group.
        resources_groups = sorted(
            [{'group': group, 'resources': resources}
             for group, resources in items_by_group.items()],
            key=lambda entry: entry['group'].name,
        )

        return resources_groups, ungrouped_resources

    def _build_calendar_weeks(self, slot_groups):
        """
        Reorganise les groupes de creneaux par semaine et par jour.
        / Reorganizes slot groups by week and by day.

        LOCALISATION : booking/views.py

        Retourne (weeks, min_hour, max_hour) :
        - weeks : list[dict] avec year, week, days, groups
        - days : list[dict] avec date et groups
        - groups : list[dict] avec start, end, slots
        - slots : dict avec start, end, duration, capacity, row_start, row_end, column_index
        - min_hour / max_hour : bornes des heures affichees
        / Returns (weeks, min_hour, max_hour):
        - weeks: list[dict] with year, week, days, groups
        - days: list[dict] with date and groups
        - groups: list[dict] with start, end, slots
        - slots: dict with start, end, duration, capacity, row_start, row_end, column_index
        - min_hour / max_hour: hour boundaries for display
        """
        # Passe 1 : calcule les bornes horaires globales.
        # / Pass 1: compute global hour boundaries.
        global_min_hour = None
        global_max_hour = None
        for group in slot_groups:
            for slot in group.slots:
                if global_min_hour is None or slot.start.hour < global_min_hour:
                    global_min_hour = slot.start.hour
                end_hour = slot.end.hour
                if slot.end.minute > 0:
                    end_hour += 1
                if global_max_hour is None or end_hour > global_max_hour:
                    global_max_hour = end_hour

        global_min_hour = global_min_hour or 0
        global_max_hour = global_max_hour or 24

        # Passe 2 : construit la structure par semaine et par jour.
        # / Pass 2: build the structure by week and by day.
        weeks_map = {}
        for group in slot_groups:
            week_year, week_number = group.start.isocalendar()[:2]
            week_key = (week_year, week_number)
            if week_key not in weeks_map:
                weeks_map[week_key] = {
                    'year': week_year,
                    'week': week_number,
                    'days': {},
                }
            day = group.start.date()
            if day not in weeks_map[week_key]['days']:
                weeks_map[week_key]['days'][day] = {
                    'date': day,
                    'groups': [],
                }

            enriched_slots = []
            for slot in group.slots:
                row_start = ((slot.start.hour - global_min_hour) * 2
                             + (slot.start.minute // 30)) + 2
                row_span = max(1, slot.slot_duration_minutes // 30)
                row_end = row_start + row_span
                enriched_slots.append({
                    'start': slot.start,
                    'end': slot.end,
                    'slot_duration_minutes': slot.slot_duration_minutes,
                    'remaining_capacity': slot.remaining_capacity,
                    'in_cart': slot.in_cart,
                    'row_start': row_start,
                    'row_end': row_end,
                })

            weeks_map[week_key]['days'][day]['groups'].append({
                'start': group.start,
                'end': group.end,
                'slots': enriched_slots,
            })

        weeks = []
        for week_key in sorted(weeks_map.keys()):
            week_data = weeks_map[week_key]
            days = []
            for day_index, day in enumerate(sorted(week_data['days'].keys())):
                day_data = week_data['days'][day]
                # Ajoute column_index a chaque slot (2 = premiere colonne jour).
                # / Add column_index to each slot (2 = first day column).
                column_index = day_index + 2
                for group in day_data['groups']:
                    for slot in group['slots']:
                        slot['column_index'] = column_index
                days.append(day_data)
            weeks.append({
                'year': week_data['year'],
                'week': week_data['week'],
                'days': days,
            })

        return weeks, global_min_hour, global_max_hour

    def _build_mobile_days(self, slot_groups):
        """
        Regroupe les creneaux par jour pour l'affichage mobile.
        / Groups slots by day for mobile display.

        LOCALISATION : booking/views.py

        Retourne (mobile_days, time_rows, min_hour, max_hour) :
        - mobile_days : list[dict] avec index, day (un seul jour par page)
        - time_rows : lignes horaires pour la grille mobile
        - min_hour / max_hour : bornes des heures affichees
        / Returns (mobile_days, time_rows, min_hour, max_hour):
        - mobile_days: list[dict] with index, day (one day per page)
        - time_rows: time rows for the mobile grid
        - min_hour / max_hour: hour boundaries for display
        """
        # Passe 1 : collecte tous les jours avec leurs groupes de creneaux.
        # / Pass 1: collect all days with their slot groups.
        days_map = {}
        global_min_hour = None
        global_max_hour = None

        for group in slot_groups:
            day = group.start.date()
            if day not in days_map:
                days_map[day] = {
                    'date': day,
                    'weekday': group.start.weekday(),
                    'day_number': group.start.day,
                    'groups': [],
                }

            for slot in group.slots:
                # Met a jour les bornes horaires globales.
                # / Updates global hour boundaries.
                if global_min_hour is None or slot.start.hour < global_min_hour:
                    global_min_hour = slot.start.hour
                end_hour = slot.end.hour
                if slot.end.minute > 0:
                    end_hour += 1
                if global_max_hour is None or end_hour > global_max_hour:
                    global_max_hour = end_hour

            days_map[day]['groups'].append({
                'start': group.start,
                'end': group.end,
                'slots': list(group.slots),
            })

        global_min_hour = global_min_hour or 0
        global_max_hour = global_max_hour or 24

        # Passe 2 : ajoute les indices de ligne pour la grille mobile.
        # / Pass 2: add row indices for the mobile grid.
        all_days = []
        for day in sorted(days_map.keys()):
            day_data = days_map[day]
            for group in day_data['groups']:
                for slot in group['slots']:
                    slot.row_start = ((slot.start.hour - global_min_hour) * 2
                                      + (slot.start.minute // 30)) + 2
                    row_span = max(1, slot.slot_duration_minutes // 30)
                    slot.row_end = slot.row_start + row_span
            all_days.append(day_data)

        # Passe 3 : chaque jour devient une page mobile individuelle.
        # / Pass 3: each day becomes an individual mobile page.
        mobile_days = []
        for i, day_data in enumerate(all_days):
            mobile_days.append({
                'index': i,
                'day': day_data,
            })

        # Lignes horaires pour la grille mobile.
        # / Time rows for the mobile grid.
        time_rows = []
        for hour in range(global_min_hour, global_max_hour + 1):
            for minute in (0, 30):
                if hour == global_max_hour and minute > 0:
                    break
                time_rows.append({
                    'hour': hour,
                    'minute': minute,
                    'label': f"{hour:02d}:{minute:02d}",
                    'row_index': ((hour - global_min_hour) * 2 + (minute // 30)) + 2,
                })

        return mobile_days, time_rows, global_min_hour, global_max_hour

    def _get_resource_choices(self, current_resource):
        """
        Retourne les ressources pour le selecteur de la version mobile,
        groupées par ResourceGroup.
        / Returns resources for the mobile selector, grouped by ResourceGroup.

        LOCALISATION : booking/views.py

        :param current_resource: Resource selectionnee
        :return: list[dict] avec group_name (None pour les ressources sans groupe)
                 et resources (liste de ressources avec pk, name, selected)
        / list[dict] with group_name (None for ungrouped resources)
        / and resources (list of resources with pk, name, selected)
        """
        resources_groups, ungrouped_resources = self._group_resources()
        resource_choices = []

        if ungrouped_resources:
            resource_choices.append({
                'group_name': None,
                'resources': [
                    {
                        'pk': resource.pk,
                        'name': resource.product.name,
                        'selected': resource.pk == current_resource.pk,
                    }
                    for resource in ungrouped_resources
                ],
            })

        for group_entry in resources_groups:
            group = group_entry['group']
            resource_choices.append({
                'group_name': group.name,
                'resources': [
                    {
                        'pk': resource.pk,
                        'name': resource.product.name,
                        'selected': resource.pk == current_resource.pk,
                    }
                    for resource in group_entry['resources']
                ],
            })

        return resource_choices

    # ── Liste des ressources ─────────────────────────────────────────────────

    def list(self, request):
        """
        Affiche la liste de toutes les ressources avec un aperçu des créneaux.
        / Displays the list of all resources with a slot preview.

        LOCALISATION : booking/views.py

        Accès : public.
        / Access: public.
        """
        context = get_context(request)
        resources_groups, ungrouped_resources = self._group_resources()
        context.update({
            'resources_groups': resources_groups,
            'ungrouped_resources':  ungrouped_resources,
        })
        return render(request, 'booking/views/home.html', context)

    # ── Détail d'une ressource ───────────────────────────────────────────────

    @action(detail=True, methods=['get'], url_path="resource", url_name="resource")
    def resource_page(self, request, pk=None):
        """
        Affiche le detail d'une ressource et la liste complete de ses creneaux.
        / Displays a resource's detail and the full list of its slots.

        LOCALISATION : booking/views.py

        Acces : public.
        / Access: public.
        """
        resource = get_object_or_404(
            Resource.objects.select_related('calendar', 'weekly_opening', 'group'),
            pk=pk,
        )
        slot_groups = annotate_slots_for_display(compute_slots(resource))

        # Marque les créneaux déjà présents dans le panier.
        # / Mark slots already present in the cart.
        from BaseBillet.services_panier import PanierSession
        panier = PanierSession(request)
        cart_resource_items = [
            item for item in panier.resources()
            if item.get('resource_uuid') == str(resource.pk)
        ]
        for group in slot_groups:
            for slot in group.slots:
                for item in cart_resource_items:
                    item_start = parse_datetime(item['start_datetime'])
                    item_end = item_start + datetime.timedelta(
                        minutes=int(item['slot_duration_minutes']) * int(item['slot_count'])
                    )
                    if item_start <= slot.start < item_end:
                        slot.in_cart = True
                        break

        calendar_weeks, min_hour, max_hour = self._build_calendar_weeks(slot_groups)
        mobile_days, mobile_time_rows, mobile_min_hour, mobile_max_hour = self._build_mobile_days(slot_groups)
        resource_choices = self._get_resource_choices(resource)

        # Barre de jours pour la navigation mobile (chaque jour pointe vers sa page).
        # / Day bar for mobile navigation (each day points to its own page).
        weekday_letters = 'LMMJVSD'
        mobile_day_bar = []
        for mobile_day in mobile_days:
            day = mobile_day['day']
            mobile_day_bar.append({
                'date': day['date'],
                'weekday': day['weekday'],
                'weekday_letter': weekday_letters[day['weekday']],
                'day_number': day['day_number'],
                'day_index': mobile_day['index'],
            })

        # Construit les lignes horaires pour la grille du calendrier desktop.
        # / Builds the time rows for the desktop calendar grid.
        time_rows = []
        for hour in range(min_hour, max_hour + 1):
            for minute in (0, 30):
                if hour == max_hour and minute > 0:
                    break
                time_rows.append({
                    'hour': hour,
                    'minute': minute,
                    'label': f"{hour:02d}:{minute:02d}",
                    'row_index': ((hour - min_hour) * 2 + (minute // 30)) + 2,
                })

        context = get_context(request)
        context.update({
            'resource':          resource,
            'slot_groups':       slot_groups,
            'calendar_weeks':    calendar_weeks,
            'min_hour':          min_hour,
            'max_hour':          max_hour,
            'time_rows':         time_rows,
            'mobile_days':       mobile_days,
            'mobile_time_rows':  mobile_time_rows,
            'mobile_min_hour':   mobile_min_hour,
            'mobile_max_hour':   mobile_max_hour,
            'mobile_day_bar':    mobile_day_bar,
            'resource_choices':  resource_choices,
        })
        return render(request, 'booking/views/resource.html', context)

    # ── Formulaire et création de réservation ────────────────────────────────

    @action(detail=True, methods=['get','post'], url_path="book", url_name="book")
    def book(self, request, pk=None):
        """
        GET  : affiche le formulaire de confirmation de réservation.
        POST : crée la réservation et redirige vers mes réservations.
        / GET:  shows the booking confirmation form.
        / POST: creates the booking and redirects to my bookings.

        LOCALISATION : booking/views.py

        Accès : authentifié uniquement.
        / Access: authenticated users only.
        """
        # Redirige les visiteurs non connectés vers la page de connexion.
        # / Redirect unauthenticated visitors to the login page.
        if not request.user.is_authenticated:
            login_url   = reverse('connexion')
            redirect_url = f'{login_url}?next={request.get_full_path()}'
            return HttpResponseClientRedirect(redirect_url)

        resource = get_object_or_404(
            Resource.objects.select_related('calendar', 'weekly_opening'),
            pk=pk,
        )

        if request.method == 'GET':
            return self._book_get(request, resource)
        return self._book_post(request, resource)

    def _book_get(self, request, resource):
        """
        Affiche le formulaire de réservation pour le créneau demandé.
        / Displays the booking form for the requested slot.

        LOCALISATION : booking/views.py

        Paramètre GET : start_datetime — datetime naïf local (ex: 2026-05-10T10:00:00).
        Le serveur l'interprète dans le fuseau du tenant (spec create-booking.md §GET).
        / GET param: start_datetime — naive local datetime (e.g. 2026-05-10T10:00:00).
        The server interprets it in the tenant's timezone (spec create-booking.md §GET).
        """
        tz = timezone.get_current_timezone()

        # Parse le datetime naïf et le rend tz-aware dans le fuseau du tenant.
        # Un paramètre manquant ou invalide redirige vers la ressource.
        # / Parse the naive datetime and make it tz-aware in the tenant timezone.
        # A missing or invalid param redirects back to the resource page.
        start_datetime_raw   = request.GET.get('start_datetime', '')
        start_datetime_naive = parse_datetime(start_datetime_raw)
        if start_datetime_naive is None:
            return HttpResponseBadRequest()
        start_datetime = timezone.make_aware(start_datetime_naive, tz)

        # Utilise group_end comme fin de fenêtre quand il est fourni par la page
        # de détail — borne exacte du groupe contigu contenant start_datetime.
        # Repli sur l'horizon complet si le paramètre est absent ou invalide.
        # / Use group_end as the window end when provided by the resource detail
        # page — exact boundary of the contiguous group containing start_datetime.
        # Falls back to the full horizon if the param is absent or unparseable.
        group_end_raw   = request.GET.get('group_end', '')
        group_end_naive = parse_datetime(group_end_raw)
        if group_end_naive is not None:
            window_end = timezone.make_aware(group_end_naive, tz)
        else:
            window_end = timezone.make_aware(
                datetime.datetime.combine(
                    start_datetime.astimezone(tz).date()
                    + datetime.timedelta(days=resource.booking_horizon_days + 1),
                    datetime.time.min,
                ),
                tz,
            )
        window      = Interval(start=start_datetime, end=window_end)
        slot_groups = annotate_slots_for_display(compute_slots(resource, window))

        # Cherche le créneau demandé dans sa séquence contiguë, puis extrait
        # les créneaux disponibles consécutifs depuis sa position.
        # / Find the requested slot in its contiguous group, then extract
        # consecutive available slots from its position.
        requested_slot     = None
        max_slot_count     = 0
        consecutive_slots  = []
        for group in slot_groups:
            for i, slot in enumerate(group.slots):
                if slot.start == start_datetime:
                    requested_slot = slot
                    for s in group.slots[i:]:
                        if s.remaining_capacity <= 0:
                            break
                        max_slot_count += 1
                    consecutive_slots = group.slots[i:i + max_slot_count]
                    break
            if requested_slot:
                break

        # Créneau introuvable ou complet → redirige vers slot-unavailable.
        # / Slot not found or full → redirect to slot-unavailable.
        if requested_slot is None or requested_slot.remaining_capacity <= 0:
            context = get_context(request)
            context.update({
                'resource': resource,
                'start_datetime': start_datetime,
            })
            return render(request, 'booking/partials/slot_unavailable.html', context)

        # Calcule si l'annulation sera possible après réservation.
        # deadline = start - cancellation_deadline_hours.
        # Si now() > deadline, l'annulation n'est déjà plus possible.
        # / Compute whether cancellation will be possible after booking.
        # deadline = start - cancellation_deadline_hours.
        # If now() > deadline, cancellation is already no longer possible.
        cancellation_deadline  = start_datetime - datetime.timedelta(
            hours=resource.cancellation_deadline_hours,
        )
        cancellation_possible  = timezone.now() <= cancellation_deadline

        context = get_context(request)
        context.update({
            'resource':              resource,
            'slot':                  requested_slot,
            'consecutive_slots':     consecutive_slots,
            'max_slot_count':        max_slot_count,
            'slot_duration_minutes': requested_slot.slot_duration_minutes,
            'start_datetime':        start_datetime,
            'group_end':             consecutive_slots[-1].end if consecutive_slots else window_end,
            'cancellation_deadline': cancellation_deadline,
            'cancellation_possible': cancellation_possible,
        })
        # En requete HTMX (popup SweetAlert2), on retourne le partial.
        # / For HTMX requests (SweetAlert2 popup), return the partial.
        if request.htmx:
            return render(request, 'booking/partials/book_form.html', context)
        return render(request, 'booking/views/book.html', context)

    def _book_post(self, request, resource):
        """
        Crée une réservation confirmée depuis les données POST.
        / Creates a confirmed booking from POST data.

        LOCALISATION : booking/views.py

        Succès    → redirige vers /my_account/my_bookings/?new=<pk> si la réservation est gratuite.
                  → redirige vers stripe si la réservation est payante
        Échec     → re-render du formulaire avec message d'erreur

        / Success → redirect to /my_account/my_bookings/?new=<pk> if booking is free
                  → redirect to stripe if booking need payement
        / Failure → re-render the form with an error message
        """

        try:
            price_uuid = request.POST.get('price_uuid') or request.POST.get('price')
            price = Price.objects.get(uuid=price_uuid)
        except Price.DoesNotExist:
            messages.error(request, _("Le prix n'existe pas"))
            response = HttpResponse("")
            response["HX-Refresh"] = "true"
            return response

        # Parse le datetime naïf depuis le champ caché du formulaire.
        # / Parse the naive datetime from the form hidden field.
        tz = timezone.get_current_timezone()
        start_datetime_raw   = request.POST.get('start_datetime', '')
        start_datetime_naive = parse_datetime(start_datetime_raw)
        if start_datetime_naive is None:
            return HttpResponseBadRequest()
        start_datetime = timezone.make_aware(start_datetime_naive, tz)

        # Dérive slot_duration_minutes en recalculant les créneaux depuis
        # start_datetime. Utilise group_end comme borne de fenêtre si disponible.
        # / Derive slot_duration_minutes by recomputing slots from start_datetime.
        # Uses group_end as the window boundary if available.
        group_end_raw   = request.POST.get('group_end', '')
        group_end_naive = parse_datetime(group_end_raw)
        if group_end_naive is not None:
            window_end_derive = timezone.make_aware(group_end_naive, tz)
        else:
            window_end_derive = timezone.make_aware(
                datetime.datetime.combine(
                    start_datetime.astimezone(tz).date()
                    + datetime.timedelta(days=resource.booking_horizon_days + 1),
                    datetime.time.min,
                ),
                tz,
            )
        window_derive = Interval(start=start_datetime, end=window_end_derive)
        slot_groups_derive = annotate_slots_for_display(compute_slots(resource, window_derive))

        requested_slot = None
        max_slot_count = 0
        consecutive_slots = []
        slot_duration_minutes = None
        for group in slot_groups_derive:
            for i, slot in enumerate(group.slots):
                if slot.start == start_datetime:
                    requested_slot = slot
                    slot_duration_minutes = slot.slot_duration_minutes
                    for s in group.slots[i:]:
                        if s.remaining_capacity <= 0:
                            break
                        max_slot_count += 1
                    consecutive_slots = group.slots[i:i + max_slot_count]
                    break
            if slot_duration_minutes:
                break

        if slot_duration_minutes is None or requested_slot is None:
            return HttpResponseBadRequest()

        def _build_form_context(error=None, race_condition=False):
            cancellation_deadline = start_datetime - datetime.timedelta(
                hours=resource.cancellation_deadline_hours,
            )
            cancellation_possible = timezone.now() <= cancellation_deadline
            context = get_context(request)
            context.update({
                'resource': resource,
                'slot': requested_slot,
                'consecutive_slots': consecutive_slots,
                'max_slot_count': max_slot_count,
                'slot_duration_minutes': slot_duration_minutes,
                'start_datetime': start_datetime,
                'group_end': consecutive_slots[-1].end if consecutive_slots else window_end_derive,
                'cancellation_deadline': cancellation_deadline,
                'cancellation_possible': cancellation_possible,
                'error': error,
            })
            if race_condition:
                context['race_condition'] = True
            return context

        # Parse et valide l'heure de fin depuis le champ du formulaire.
        # / Parse and validate the end time from the form field.
        end_time_raw = request.POST.get('end_time', '')
        end_time_naive = parse_datetime(end_time_raw)
        if end_time_naive is None:
            context = _build_form_context(error=_("Invalid end time format."))
            if request.htmx:
                return render(request, 'booking/partials/book_form.html', context, status=422)
            return render(request, 'booking/views/book.html', context)

        end_datetime = timezone.make_aware(end_time_naive, tz)

        if end_datetime <= start_datetime:
            context = _build_form_context(error=_("End time must be after start time."))
            if request.htmx:
                return render(request, 'booking/partials/book_form.html', context, status=422)
            return render(request, 'booking/views/book.html', context)

        if end_datetime not in [slot.end for slot in consecutive_slots]:
            context = _build_form_context(error=_("End time must match an available slot end."))
            if request.htmx:
                return render(request, 'booking/partials/book_form.html', context, status=422)
            return render(request, 'booking/views/book.html', context)

        duration_minutes = int((end_datetime - start_datetime).total_seconds() // 60)
        if duration_minutes % slot_duration_minutes != 0:
            context = _build_form_context(error=_("Selected duration is not a multiple of the slot duration."))
            if request.htmx:
                return render(request, 'booking/partials/book_form.html', context, status=422)
            return render(request, 'booking/views/book.html', context)

        slot_count = duration_minutes // slot_duration_minutes

        # Valide le slot_count calculé via le serializer.
        # / Validate the computed slot_count through the serializer.
        data = request.POST.copy()
        data['slot_count'] = slot_count
        serializer_body = BookingCreateSerializer(data=data)
        if not serializer_body.is_valid():
            context = _build_form_context(error=serializer_body.errors)
            if request.htmx:
                return render(request, 'booking/partials/book_form.html', context, status=422)
            return render(request, 'booking/views/book.html', context)

        slot_count = serializer_body.validated_data['slot_count']

        is_valid, result, checkout_url = validate_new_booking(
            resource              = resource,
            start_datetime        = start_datetime,
            slot_duration_minutes = slot_duration_minutes,
            slot_count            = slot_count,
            member                = request.user,
            price=price
        )

        if is_valid:
            # Reservation creee — redirige vers mes reservations avec mise en evidence.
            # / Booking created — redirect to my bookings with highlight.
            my_bookings_url = (
                reverse('my_account-my-bookings')
                + '?' + urlencode({'new': result.pk})
            )
            target_url = checkout_url or my_bookings_url
            # En requete HTMX, on utilise une redirection client pour eviter le swap.
            # / For HTMX requests, use client redirect to avoid swap.

            if checkout_url is None:
                messages.success(request, _("Réservation créée avec succès."))

            if request.htmx:
                return HttpResponseClientRedirect(target_url)
            return redirect(target_url)

        # Échec (modification concurrente, créneau commencé, etc.) — re-render avec
        # les créneaux recalculés et le message d'erreur.
        # / Failure (race condition, slot started, etc.) — re-render with
        # freshly computed slots and the error message.
        tz         = timezone.get_current_timezone()
        horizon_end = timezone.make_aware(
            datetime.datetime.combine(
                start_datetime.astimezone(tz).date()
                + datetime.timedelta(days=resource.booking_horizon_days + 1),
                datetime.time.min,
            ),
            tz,
        )
        window      = Interval(start=start_datetime, end=horizon_end)
        slot_groups = annotate_slots_for_display(compute_slots(resource, window))

        requested_slot    = None
        max_slot_count    = 0
        consecutive_slots = []
        for group in slot_groups:
            for i, slot in enumerate(group.slots):
                if slot.start == start_datetime:
                    requested_slot = slot
                    for s in group.slots[i:]:
                        if s.remaining_capacity <= 0:
                            break
                        max_slot_count += 1
                    consecutive_slots = group.slots[i:i + max_slot_count]
                    break
            if requested_slot:
                break

        context = _build_form_context(error=result, race_condition=True)
        # En requete HTMX, on retourne le partial avec les erreurs en 422.
        # / For HTMX requests, return the partial with errors and 422 status.
        if request.htmx:
            return render(request, 'booking/partials/book_form.html', context, status=422)
        return render(request, 'booking/views/book.html', context)

    # ── Créneau indisponible ─────────────────────────────────────────────────

    @action(detail=True, methods=['get'], url_path="slot-unavailable", url_name="slot-unavailable")
    def slot_unavailable(self, request, pk=None):
        """
        Affiche la page "créneau pris" après une modification concurrente.
        / Displays the "slot taken" page after a race condition.

        LOCALISATION : booking/views.py

        Accès : public. Redirigé depuis book() quand le créneau est complet.
        / Access: public. Redirected from book() when the slot is full.
        """
        resource = get_object_or_404(Resource, pk=pk)

        # Parse start_datetime depuis la query string — dégrade proprement à None.
        # / Parse start_datetime from query string — degrades gracefully to None.
        start_datetime_raw = request.GET.get('start_datetime', '')
        start_datetime     = parse_datetime(start_datetime_raw)

        context = get_context(request)
        context.update({
            'resource':       resource,
            'start_datetime': start_datetime,
        })
        return render(request, 'booking/views/slot_unavailable.html', context)

    # ── Mes réservations ─────────────────────────────────────────────────────
    # Déplacé dans BaseBillet.views.MyAccount pour plus de cohérence

    # ── Confirmation d'annulation ────────────────────────────────────────────

    @action(detail=True, methods=['get', 'post'], url_path="cancel", url_name="cancel")
    def cancel_confirm(self, request, pk=None):
        """
        GET  : affiche la page de confirmation d'annulation.
        POST : supprime la réservation et redirige vers mes réservations.
        / GET:  shows the cancellation confirmation page.
        / POST: deletes the booking and redirects to my bookings.

        LOCALISATION : booking/views.py

        L'annulation est modélisée par la suppression de la ligne Booking.
        / Cancellation is modelled as deletion of the Booking row.

        Accès : authentifié uniquement.
        / Access: authenticated users only.
        """
        if not request.user.is_authenticated:
            login_url   = reverse('connexion')
            redirect_url = f'{login_url}?next={request.get_full_path()}'
            return redirect(redirect_url)

        booking = get_object_or_404(
            Booking.objects.select_related('resource'),
            pk     = pk,
            user   = request.user,
            status__in = [Booking.PAID_BY_USER, Booking.ADMIN_VALID, Booking.FREERES_USERACTIV],
        )

        deadline = booking.deadline()
        deadline_passed = booking.deadline_passed()

        if request.method == 'GET':
            context = get_context(request)
            context.update({
                'booking':         booking,
                'deadline':        deadline,
                'deadline_passed': deadline_passed,
            })
            return render(request, 'booking/views/cancel_booking.html', context)

        # POST — recompute deadline to guard against race condition.
        deadline_passed = booking.deadline_passed()
        if deadline_passed:
            context = get_context(request)
            context.update({
                'booking':         booking,
                'deadline':        deadline,
                'deadline_passed': True,
            })
            return render(request, 'booking/views/cancel_booking.html', context)

        try:
            cancel_text = booking.cancel_and_refund_booking()

            try:
                send_booking_cancellation_user.delay(str(booking.pk))
            except Exception as ce:
                logger.error(f"Failed to queue cancellation email for booking {booking.pk}: {ce}")

            messages.add_message(request, messages.SUCCESS, cancel_text)
            return HttpResponseClientRedirect(reverse('my_account-my-bookings'))

        except Exception as e:
            logger.error(f"Error canceling booking {booking.pk}: {e}")
            messages.add_message(request, messages.ERROR,
                                 _("An error occurred while cancelling your booking.") + f" : {e}")
            return HttpResponseClientRedirect(reverse('my_account-my-bookings'))


