"""
Vues de l'app booking — réservation de ressources partagées.
/ booking app views — shared resource reservation.

LOCALISATION : booking/views.py

Flux v0.1 : GET/POST simples, réservation directement en statut 'confirmed'.
/ v0.1 flow: simple GET/POST, booking created directly with status 'confirmed'.
"""
import calendar
import datetime
import logging
from collections import defaultdict
from urllib.parse import urlencode
from django_htmx.http import HttpResponseClientRedirect
from django.http import HttpResponseBadRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import permissions, viewsets
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from rest_framework.decorators import action

from BaseBillet.models import Price, PaymentMethod
from BaseBillet.views import get_context
from booking.booking_engine import Interval, compute_slots, validate_new_booking
from booking.booking_engine import annotate_slots_for_display
from booking.booking_engine import validate_resource_booking_form
from booking.models import Booking, Resource
from booking.tasks import send_booking_cancellation_user


logger = logging.getLogger(__name__)


# ── Affichage des créneaux / Slot display ───────────────────────────────────
# Les classes DisplaySlot, DisplaySlotGroup et la fonction
# annotate_slots_for_display ont été déplacées dans booking/booking_engine.py
# car elles sont partagées avec BaseBillet/views.py.
# / Moved to booking/booking_engine.py because they are shared with BaseBillet/views.py.

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
                        'name': resource.name,
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
                        'name': resource.name,
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

        # Branchement selon le type de reservation de la ressource.
        # / Branch according to the resource's booking type.
        if resource.slot_type == Resource.DAY:
            # TODO-FOR-DAY-BOOKING : Recheck
            return self._render_resource_day_page(request, resource)

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

    def _render_resource_day_page(self, request, resource):
        """
        Affiche le detail d'une ressource journaliere avec un calendrier mensuel.
        / Displays a day-resource detail with a monthly calendar.

        LOCALISATION : booking/views.py

        Acces : public.
        / Access: public.
        """
        # TODO-FOR-DAY-BOOKING : Recheck
        tz = timezone.get_current_timezone()
        today = timezone.now().date()

        # Determine le mois a afficher depuis le parametre ?month=YYYY-MM.
        # / Determine the displayed month from the ?month=YYYY-MM query parameter.
        month_param = request.GET.get('month', '')
        if month_param:
            try:
                year, month = map(int, month_param.split('-'))
                requested_month = datetime.date(year, month, 1)
            except (ValueError, TypeError):
                requested_month = datetime.date(today.year, today.month, 1)
        else:
            requested_month = datetime.date(today.year, today.month, 1)

        # Calcule la fenetre sur le mois affiche.
        # / Compute the window for the displayed month.
        first_day_of_month = requested_month
        last_day_of_month = datetime.date(
            requested_month.year,
            requested_month.month,
            calendar.monthrange(requested_month.year, requested_month.month)[1],
        )
        window_start = timezone.make_aware(
            datetime.datetime.combine(first_day_of_month, datetime.time.min),
            tz,
        )
        window_end = timezone.make_aware(
            datetime.datetime.combine(
                last_day_of_month + datetime.timedelta(days=1),
                datetime.time.min,
            ),
            tz,
        )
        window = Interval(start=window_start, end=window_end)

        slot_groups = annotate_slots_for_display(compute_slots(resource, window))

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

        month_weeks = self._build_month_calendar(
            slot_groups=slot_groups,
            year=requested_month.year,
            month=requested_month.month,
            today=today,
        )

        # Mois precedent et suivant pour la navigation.
        # / Previous and next month for navigation.
        prev_month = (requested_month.replace(day=1) - datetime.timedelta(days=1)).replace(day=1)
        next_month = (requested_month.replace(day=1) + datetime.timedelta(days=32)).replace(day=1)

        # Libelles courts des jours de la semaine pour l'en-tete du calendrier.
        # / Short weekday labels for the calendar header.
        weekday_labels = [
            _('Mon'), _('Tue'), _('Wed'), _('Thu'), _('Fri'), _('Sat'), _('Sun')
        ]

        resource_choices = self._get_resource_choices(resource)

        context = get_context(request)
        context.update({
            'resource':        resource,
            'requested_month': requested_month,
            'month_weeks':     month_weeks,
            'prev_month':      prev_month,
            'next_month':      next_month,
            'today':           today,
            'weekday_labels':  weekday_labels,
            'resource_choices': resource_choices,
        })
        # En requete HTMX (navigation entre mois), on retourne uniquement le partial calendrier.
        # / For HTMX requests (month navigation), return only the calendar partial.
        if request.htmx:
            return render(request, 'booking/partials/resource_day_calendar.html', context)
        return render(request, 'booking/views/resource_day.html', context)

    def _build_month_calendar(self, slot_groups, year, month, today):
        """
        Construit la grille mensuelle avec l'etat de chaque jour.
        / Builds the monthly grid with the state of each day.

        LOCALISATION : booking/views.py

        Retourne une liste de semaines, chaque semaine contenant 7 jours.
        Chaque jour contient : date, is_current_month, slot, group, state.
        / Returns a list of weeks, each week containing 7 days.
        Each day contains: date, is_current_month, slot, group, state.

        :param slot_groups: list[DisplaySlotGroup]
        :param year: annee du mois affiche (int)
        :param month: mois affiche (int)
        :param today: date du jour (date)
        :return: list[list[dict]]
        """
        # TODO-FOR-DAY-BOOKING : Recheck

        # Indexe les créneaux et leurs groupes par date de debut.
        # / Index slots and their groups by start date.
        slot_by_date = {}
        group_by_date = {}
        for group in slot_groups:
            for slot in group.slots:
                slot_date = slot.start.date()
                slot_by_date[slot_date] = slot
                group_by_date[slot_date] = group

        weeks = []
        for week_dates in calendar.Calendar(firstweekday=0).monthdatescalendar(year, month):
            week_days = []
            for day_date in week_dates:
                slot = slot_by_date.get(day_date)
                group = group_by_date.get(day_date)

                # Un jour passe est non reservable, meme si un creneau existe
                # en base (car la fenetre commence au debut du mois).
                # / A past day is not bookable, even if a slot exists in the
                # database (because the window starts at the beginning of the month).
                if day_date < today:
                    state = 'past'
                elif slot:
                    if slot.in_cart:
                        state = 'cart'
                    elif slot.remaining_capacity > 0:
                        state = 'free'
                    else:
                        state = 'busy'
                else:
                    state = 'unavailable'

                week_days.append({
                    'date': day_date,
                    'is_current_month': day_date.month == month,
                    'slot': slot,
                    'group': group,
                    'state': state,
                })
            weeks.append(week_days)

        return weeks

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
        if resource.slot_type == Resource.HOUR:
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
        elif resource.slot_type == Resource.DAY:
            # TODO-FOR-DAY-BOOKING
            pass

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
            if resource.slot_type == Resource.HOUR:
                return render(request, 'booking/partials/book_form.html', context)
            elif resource.slot_type == Resource.DAY:
                # TODO-FOR-DAY-BOOKING
                pass

        return render(request, 'booking/views/book.html', context)

    def _build_resource_form_context(
        self,
        request,
        resource,
        start_datetime,
        requested_slot,
        consecutive_slots,
        max_slot_count,
        slot_duration_minutes,
        window_end,
        error=None,
        race_condition=False,
    ):
        """
        Construit le contexte commun pour le formulaire de réservation.
        / Builds the common context for the booking form.

        LOCALISATION : booking/views.py

        Ce helper est utilisé par _book_post pour éviter la duplication
        de la construction du contexte de rendu.
        / Helper used by _book_post to avoid duplicating context building.
        """
        cancellation_deadline = None
        cancellation_possible = False
        if start_datetime:
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
            'group_end': consecutive_slots[-1].end if consecutive_slots else window_end,
            'cancellation_deadline': cancellation_deadline,
            'cancellation_possible': cancellation_possible,
            'error': error,
        })
        if race_condition:
            context['race_condition'] = True
        return context

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

        # Validation centralisée du formulaire ressource.
        # / Centralized resource form validation.
        error_message, validation_result = validate_resource_booking_form(
            resource=resource,
            post_data=request.POST,
            price=price,
        )

        if error_message:
            context = self._build_resource_form_context(
                request=request,
                resource=resource,
                start_datetime=validation_result.get('start_datetime'),
                requested_slot=validation_result.get('requested_slot'),
                consecutive_slots=validation_result.get('consecutive_slots', []),
                max_slot_count=validation_result.get('max_slot_count', 0),
                slot_duration_minutes=validation_result.get('slot_duration_minutes'),
                window_end=validation_result.get('window_end'),
                error=validation_result.get('error', error_message),
            )
            if request.htmx:
                if resource.slot_type == Resource.DAY:
                    # TODO-FOR-DAY-BOOKING
                    pass
                return render(request, 'booking/partials/book_form.html', context, status=422)
            return render(request, 'booking/views/book.html', context)

        start_datetime = validation_result['start_datetime']
        slot_duration_minutes = validation_result['slot_duration_minutes']
        slot_count = validation_result['slot_count']

        firstname = request.POST.get("firstname", None)
        lastname = request.POST.get("lastname", None)

        custom_amount = request.POST.get(f"custom_amount_{price_uuid}", None)


        is_valid, result, checkout_url = validate_new_booking(
            resource=resource,
            start_datetime=start_datetime,
            slot_duration_minutes=slot_duration_minutes,
            slot_count=slot_count,
            member=request.user,
            price=price,
            first_name=firstname,
            last_name=lastname,
            external_payment_method=PaymentMethod.STRIPE_NOFED,
            custom_amount=custom_amount
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
        tz = timezone.get_current_timezone()
        horizon_end = timezone.make_aware(
            datetime.datetime.combine(
                start_datetime.astimezone(tz).date()
                + datetime.timedelta(days=resource.booking_horizon_days + 1),
                datetime.time.min,
            ),
            tz,
        )
        if resource.slot_type == Resource.DAY:
            # TODO-FOR-DAY-BOOKING
            pass
        else:
            window = Interval(start=start_datetime, end=horizon_end)
            slot_groups = annotate_slots_for_display(compute_slots(resource, window))

        requested_slot = None
        max_slot_count = 0
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

        context = self._build_resource_form_context(
            request=request,
            resource=resource,
            start_datetime=start_datetime,
            requested_slot=requested_slot,
            consecutive_slots=consecutive_slots,
            max_slot_count=max_slot_count,
            slot_duration_minutes=requested_slot.slot_duration_minutes if requested_slot else None,
            window_end=horizon_end,
            error=result,
            race_condition=True,
        )
        # En requete HTMX, on retourne le partial avec les erreurs en 422.
        # / For HTMX requests, return the partial with errors and 422 status.
        if request.htmx:
            if resource.slot_type == Resource.DAY:
                # TODO-FOR-DAY-BOOKING
                pass
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
        POST : met l'état de la réservation à Booking.USER_CANCELED et redirige vers mes réservations.
        / GET:  shows the cancellation confirmation page.
        / POST: set the status of the booking to à Booking.USER_CANCELED and redirects to my bookings.

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


