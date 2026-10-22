"""
Vues de l'app booking — réservation de ressources partagées.
/ booking app views — shared resource reservation.

LOCALISATION : booking/views.py

Flux v0.1 : GET/POST simples, réservation directement en statut 'confirmed'.
/ v0.1 flow: simple GET/POST, booking created directly with status 'confirmed'.
"""
import calendar
import datetime
import html
import logging
from collections import defaultdict
from urllib.parse import urlencode

import stripe
from django_htmx.http import HttpResponseClientRedirect
from django.db import connection, transaction
from django.db.models import Count, Q
from django.http import HttpResponseBadRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.html import strip_tags
from django.utils.text import Truncator
from rest_framework import permissions, viewsets
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext
from rest_framework.decorators import action

from BaseBillet.models import Configuration, Event, Paiement_stripe, Price, PaymentMethod, ProductFormField, Ticket
from BaseBillet.services_libelle_prix import TYPE_RESSOURCE, libelle_prix
from BaseBillet.views import get_context, reponses_du_formulaire_personnalise_pour_le_panier
from booking.benevolat import lire_la_semaine_demandee, lundi_de_la_semaine, titre_de_la_semaine
from booking.booking_engine import Interval, compute_slots, confirmer_booking_gratuit, get_checkout_stripe, validate_new_booking
from booking.booking_engine import annotate_slots_for_display, get_existing_bookings_for_resource
from booking.booking_engine import validate_resource_booking_form
from booking.models import Booking, Resource
from booking.tasks import send_booking_cancellation_user
from booking.tasks import send_booking_request_admin, send_booking_request_user
from booking.tasks import send_booking_accepted_user, send_booking_refused_user
from booking.serializers import MotifDuRefusSerializer
from root_billet.models import RootConfiguration
from ApiBillet.permissions import TenantAdminPermissionWithRequest


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
            Resource.objects.select_related('group', 'product').order_by('name')
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

    def _ajouter_les_infos_admin_aux_creneaux(self, resource, fenetre, slot_groups):
        """
        Pour un admin du lieu : dit QUI occupe chaque créneau de la semaine.
        / For a venue admin: tells WHO occupies each slot of the week.

        LOCALISATION : booking/views.py

        Pose sur chaque créneau occupé (DisplaySlot) un dict `infos_admin` :
        - evenements : les événements qui bloquent la ressource (titre, horaires, jauge)
        - reservations : les réservations qui occupent le créneau (personne, statut, horaires)
        - libelles_de_la_case : les lignes écrites dans la case (un titre par événement,
          sinon le nom, sinon « N réservations »)
        Un créneau que personne n'occupe garde infos_admin à None.
        Lu par booking/partials/resource_semaine.html et infos_creneau_admin.html.

        Deux requêtes pour toute la semaine, quel que soit le nombre de créneaux.
        Les filtres sont ceux du moteur (booking_engine.py) : réservations par
        get_existing_bookings_for_resource(), événements comme
        get_event_intervals_blocking_resource(). Si ces filtres changent là-bas,
        ils doivent changer ici, sinon l'admin verrait d'autres occupants que
        ceux qui bloquent vraiment le créneau.
        / Two queries per week. Same filters as the booking engine: keep them in sync.
        """
        reservations_de_la_semaine = list(
            get_existing_bookings_for_resource(resource, window=fenetre)
            .select_related('user')
            .order_by('start_datetime')
        )
        evenements_de_la_semaine = list(
            Event.objects.filter(
                ressource_bloquee=resource,
                archived=False,
                end_datetime__isnull=False,
                datetime__lt=fenetre.end,
                end_datetime__gt=fenetre.start,
            )
            .annotate(
                nombre_de_billets_valides=Count(
                    'reservation__tickets',
                    filter=Q(reservation__tickets__status__in=[Ticket.SCANNED, Ticket.NOT_SCANNED]),
                    distinct=True,
                ),
            )
            .order_by('datetime')
        )

        for group in slot_groups:
            for slot in group.slots:
                # Un occupant chevauche le créneau s'il commence avant sa fin
                # et finit après son début.
                # / An occupant overlaps the slot if it starts before its end and ends after its start.
                evenements_du_creneau = []
                for evenement in evenements_de_la_semaine:
                    if evenement.datetime < slot.end and evenement.end_datetime > slot.start:
                        evenements_du_creneau.append({
                            'titre': evenement.name,
                            'debut': evenement.datetime,
                            'fin': evenement.end_datetime,
                            'billets_valides': evenement.nombre_de_billets_valides,
                            'jauge_max': evenement.jauge_max,
                        })

                reservations_du_creneau = []
                for reservation in reservations_de_la_semaine:
                    if reservation.start_datetime < slot.end and reservation.end_datetime > slot.start:
                        # Le nom saisi à la réservation d'abord, sinon celui du compte.
                        # / The name typed when booking first, else the account's.
                        prenom = reservation.first_name or reservation.user.first_name or ""
                        nom = reservation.last_name or reservation.user.last_name or ""
                        prenom_et_nom = f"{prenom} {nom}".strip()
                        reservations_du_creneau.append({
                            'prenom_et_nom': prenom_et_nom,
                            'email': reservation.user.email,
                            'statut': reservation.get_status_display(),
                            'debut': reservation.start_datetime,
                            'fin': reservation.end_datetime,
                        })

                creneau_occupe = evenements_du_creneau or reservations_du_creneau
                if not creneau_occupe:
                    continue

                # Les lignes écrites dans la case : le titre de CHAQUE événement
                # (plusieurs événements peuvent se chevaucher sur un créneau),
                # sinon la personne, sinon le nombre de réservations.
                # / Cell lines: every event title, else the person, else the booking count.
                libelles_de_la_case = []
                if evenements_du_creneau:
                    for evenement_du_creneau in evenements_du_creneau:
                        libelles_de_la_case.append(evenement_du_creneau['titre'])
                elif len(reservations_du_creneau) == 1:
                    premiere_reservation = reservations_du_creneau[0]
                    libelles_de_la_case.append(premiere_reservation['prenom_et_nom'] or premiere_reservation['email'])
                else:
                    nombre_de_reservations = len(reservations_du_creneau)
                    libelles_de_la_case.append(ngettext(
                        "%(nombre)s réservation",
                        "%(nombre)s réservations",
                        nombre_de_reservations,
                    ) % {'nombre': nombre_de_reservations})

                slot.infos_admin = {
                    'libelles_de_la_case': libelles_de_la_case,
                    'evenements': evenements_du_creneau,
                    'reservations': reservations_du_creneau,
                }

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
                # Un créneau qui finit à minuit finit le lendemain à 0 h : il compte
                # pour 24 h. Aucun créneau ne finit APRÈS minuit (OpeningEntry.clean).
                # / A slot ending at midnight ends at 0:00 the next day: it counts as 24.
                if slot.end.date() > slot.start.date():
                    end_hour = 24
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
                    'infos_admin': slot.infos_admin,
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
                # Un créneau qui finit à minuit compte pour 24 h (voir _build_calendar_weeks).
                # / A slot ending at midnight counts as 24.
                if slot.end.date() > slot.start.date():
                    end_hour = 24
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

        Une seule ressource : il n'y a rien à choisir, on ouvre directement sa page.
        / Only one resource: nothing to choose, open its page directly.
        """
        resources_groups, ungrouped_resources = self._group_resources()
        toutes_les_ressources = list(ungrouped_resources)
        for group_entry in resources_groups:
            toutes_les_ressources.extend(group_entry['resources'])

        il_y_a_une_seule_ressource = len(toutes_les_ressources) == 1
        if il_y_a_une_seule_ressource:
            la_seule_ressource = toutes_les_ressources[0]
            return redirect('booking-resource', pk=la_seule_ressource.pk)

        context = get_context(request)

        # Texte du prix de chaque carte (cotton/V2/ressource_card.html).
        # Les regles sont dans BaseBillet/services_libelle_prix.py.
        # / Price label of each card. Rules live in services_libelle_prix.py.
        for resource in toutes_les_ressources:
            resource.libelle_prix = libelle_prix(
                resource.published_prices(), TYPE_RESSOURCE,
            )

        context.update({
            'resources_groups': resources_groups,
            'ungrouped_resources':  ungrouped_resources,
        })
        return render(request, 'booking/views/resources_list.html', context)

    def _semaine_affichee(self, request, resource):
        """
        Choisit la semaine du calendrier à afficher, et la fenêtre de calcul de ses créneaux.
        / Picks the calendar week to display, and the slot computation window.

        LOCALISATION : booking/views.py

        - Paramètre ?semaine=AAAA-MM-JJ (n'importe quel jour, ramené à son lundi).
        - Absent, illisible ou passé : la semaine en cours, même vide.
        - Après la dernière semaine réservable : la dernière semaine réservable.

        La fenêtre est construite au FUSEAU DU LIEU. INDISPENSABLE : le moteur
        (generate_theoretical_slots) lit le fuseau dans window.start. Avec
        timezone.now() brut (UTC), les créneaux de la semaine en cours seraient décalés.
        Aucune marge n'est utile en fin de fenêtre : OpeningEntry.clean() interdit
        qu'un créneau finisse après minuit.
        / The window is built in the VENUE TIMEZONE: the engine reads the timezone
        from window.start. No end margin: no slot ends after midnight.

        :return: dict avec lundi, titre, precedente, suivante (lundi ou None), fenetre (Interval)
        """
        fuseau_du_lieu = timezone.get_current_timezone()
        maintenant = timezone.localtime(timezone.now(), fuseau_du_lieu)
        aujourd_hui = maintenant.date()
        lundi_de_cette_semaine = lundi_de_la_semaine(aujourd_hui)
        dernier_jour_reservable = aujourd_hui + datetime.timedelta(days=resource.booking_horizon_days)
        lundi_de_la_derniere_semaine = lundi_de_la_semaine(dernier_jour_reservable)

        lundi_affiche = lundi_de_cette_semaine
        semaine_demandee = lire_la_semaine_demandee(request.GET.get("semaine"))
        if semaine_demandee is not None:
            lundi_demande = lundi_de_la_semaine(semaine_demandee)
            if lundi_demande > lundi_de_cette_semaine:
                lundi_affiche = min(lundi_demande, lundi_de_la_derniere_semaine)

        lundi_precedent = lundi_affiche - datetime.timedelta(days=7)
        lundi_suivant = lundi_affiche + datetime.timedelta(days=7)

        # Le passé n'est jamais affiché : pas de semaine avant la semaine en cours.
        # / The past is never shown.
        semaine_precedente = None
        if lundi_precedent >= lundi_de_cette_semaine:
            semaine_precedente = lundi_precedent

        semaine_suivante = None
        if lundi_suivant <= lundi_de_la_derniere_semaine:
            semaine_suivante = lundi_suivant

        # Début : lundi 0 h, ou maintenant pour la semaine en cours (créneaux commencés
        # exclus). Les deux valeurs sont au fuseau du lieu.
        # / Start: Monday 0:00, or now for the current week. Both in venue timezone.
        debut_du_lundi = timezone.make_aware(
            datetime.datetime.combine(lundi_affiche, datetime.time.min), fuseau_du_lieu,
        )
        debut_du_lundi_suivant = timezone.make_aware(
            datetime.datetime.combine(lundi_suivant, datetime.time.min), fuseau_du_lieu,
        )
        fenetre_de_la_semaine = Interval(
            start=max(debut_du_lundi, maintenant),
            end=debut_du_lundi_suivant,
        )

        return {
            'lundi': lundi_affiche,
            'titre': titre_de_la_semaine(lundi_affiche),
            'precedente': semaine_precedente,
            'suivante': semaine_suivante,
            'fenetre': fenetre_de_la_semaine,
        }

    # ── Détail d'une ressource ───────────────────────────────────────────────

    @action(detail=True, methods=['get'], url_path="resource", url_name="resource")
    def resource_page(self, request, pk=None):
        """
        Affiche le detail d'une ressource et son calendrier, UNE SEMAINE à la fois.
        / Displays a resource's detail and its calendar, ONE WEEK at a time.

        LOCALISATION : booking/views.py

        GET /booking/<pk>/resource/?semaine=AAAA-MM-JJ
        - Requête normale : la page entière (booking/views/resource.html).
        - Lien « semaine précédente / suivante » (htmx, en-tête HX-Target :
          booking-calendrier-semaine) : la zone de la semaine seule
          (booking/partials/resource_semaine.html).
        Le retour arrière du navigateur recharge la page entière (les skins règlent
        htmx avec historyCacheSize: 0) : il passe par la requête normale.
        / Normal request: full page. Week link (HX-Target): the week zone only.

        Acces : public.
        / Access: public.
        """
        resource = get_object_or_404(
            Resource.objects.select_related('calendar', 'weekly_opening', 'group'),
            pk=pk,
        )

        semaine = self._semaine_affichee(request, resource)
        slot_groups = annotate_slots_for_display(compute_slots(resource, semaine['fenetre']))

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

        # Un admin du lieu voit qui occupe chaque créneau (événement, réservations).
        # / A venue admin sees who occupies each slot (event, bookings).
        utilisateur_est_admin_du_lieu = (
            request.user.is_authenticated
            and request.user.is_tenant_admin(connection.tenant)
        )
        if utilisateur_est_admin_du_lieu:
            self._ajouter_les_infos_admin_aux_creneaux(resource, semaine['fenetre'], slot_groups)

        calendar_weeks, min_hour, max_hour = self._build_calendar_weeks(slot_groups)
        mobile_days, mobile_time_rows, mobile_min_hour, mobile_max_hour = self._build_mobile_days(slot_groups)

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

        contexte_de_la_semaine = {
            'resource':          resource,
            'semaine':           semaine,
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
        }

        # Lien de semaine (htmx) : la zone de la semaine seule.
        # htmx envoie l'id de la cible sans le « # ».
        # / Week link (htmx): the week zone only. htmx sends the target id without "#".
        demande_la_zone_de_la_semaine = request.headers.get("HX-Target") == "booking-calendrier-semaine"
        if demande_la_zone_de_la_semaine:
            return render(request, 'booking/partials/resource_semaine.html', contexte_de_la_semaine)

        context = get_context(request)
        context.update(contexte_de_la_semaine)
        resource_choices = self._get_resource_choices(resource)

        # Compte les ressources proposées dans le sélecteur.
        # Une seule : le sélecteur est masqué, il n'y a rien à choisir.
        # / Counts the resources in the selector. A single one: the selector is hidden.
        nombre_de_ressources = 0
        for group in resource_choices:
            nombre_de_ressources += len(group['resources'])

        context['resource_choices'] = resource_choices
        context['plusieurs_ressources'] = nombre_de_ressources > 1

        # Meta description : la description sans balises ni entités HTML (« &amp; »
        # redevient « & »). Le gabarit l'échappe ensuite UNE seule fois.
        # Avec |striptags dans le gabarit, « & » sortirait « &amp;amp; ».
        # / Meta description: tags stripped and entities decoded; escaped once by the template.
        description_en_texte_brut = html.unescape(strip_tags(resource.description or ""))
        context['meta_description_de_la_ressource'] = Truncator(description_en_texte_brut).words(20)
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
            messages.add_message(request, messages.WARNING,
                                 _("Please login to access this page."))
            return HttpResponseClientRedirect('/')

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
            'reponses_saisies': self._reponses_saisies_du_formulaire(request, resource),
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
        return context

    def _produits_avec_questions(self, resource):
        """
        Les produits dont on lit les questions du formulaire dynamique.
        / Products whose dynamic form questions are read.

        Une ressource a au plus un produit (Resource.product). Sans produit,
        la liste est vide : aucune question n'est posée.
        / A resource has at most one product; none means no question.
        """
        if resource.product is None:
            return []
        return [resource.product]

    def _reponses_saisies_du_formulaire(self, request, resource):
        """
        Les réponses tapées par la personne, pour les réafficher après une erreur.
        / Answers typed by the person, to show them again after an error.

        LOCALISATION : booking/views.py

        Lu par le partial commun/formulaires/champs_produit.html (paramètre prefill).
        Clé : le nom technique de la question (field.name), comme le champ « form__<name> ».
        Un choix multiple garde toutes ses cases cochées (getlist).
        Hors POST (premier affichage), le dictionnaire est vide.
        / Keyed by field.name; multi-select keeps every checked value; empty outside POST.
        """
        reponses_saisies = {}
        if request.method != 'POST':
            return reponses_saisies

        for produit in self._produits_avec_questions(resource):
            for question in produit.form_fields.all():
                nom_du_champ = f"form__{question.name}"
                question_a_choix_multiple = question.field_type == ProductFormField.FieldType.MULTI_SELECT
                if question_a_choix_multiple:
                    reponses_saisies[question.name] = request.POST.getlist(nom_du_champ)
                else:
                    reponses_saisies[question.name] = request.POST.get(nom_du_champ, "")
        return reponses_saisies

    def _book_post(self, request, resource):
        """
        Crée une réservation confirmée depuis les données POST.
        / Creates a confirmed booking from POST data.

        LOCALISATION : booking/views.py

        Succès    → redirige vers /my_account/my_bookings/?new=<pk> si la réservation est gratuite.
                  → redirige vers stripe si la réservation est payante
                  → redirige vers /my_account/my_bookings/?new=<pk> si c'est une demande
                    à validation manuelle (tarif manual_validation), avec les deux mails
                    « demande reçue » (admin et personne)
        Échec     → re-render du formulaire avec message d'erreur

        / Success → redirect to /my_account/my_bookings/?new=<pk> if booking is free
                  → redirect to stripe if booking need payement
        / Failure → re-render the form with an error message
        """

        try:
            price_uuid = request.POST.get('price_uuid') or request.POST.get('price')
            price = Price.objects.get(uuid=price_uuid, archived=False)
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
                return render(request, 'booking/partials/book_form.html', context, status=422)
            return render(request, 'booking/views/book.html', context)

        start_datetime = validation_result['start_datetime']
        slot_duration_minutes = validation_result['slot_duration_minutes']
        slot_count = validation_result['slot_count']

        firstname = request.POST.get("firstname", None)
        lastname = request.POST.get("lastname", None)

        custom_amount = request.POST.get(f"custom_amount_{price_uuid}", None)

        # Réponses au formulaire dynamique du produit de la ressource.
        # Même fonction que le panier (PanierMVT.add_resource) : les réponses sont
        # rangées pareil, quel que soit le parcours. Une question obligatoire sans
        # réponse renvoie le formulaire en 422, avec les réponses déjà tapées.
        # / Dynamic form answers, same builder as the cart; 422 on a missing required answer.
        reponses_au_formulaire, erreur_du_formulaire = reponses_du_formulaire_personnalise_pour_le_panier(
            request,
            self._produits_avec_questions(resource),
        )
        if erreur_du_formulaire:
            context = self._build_resource_form_context(
                request=request,
                resource=resource,
                start_datetime=start_datetime,
                requested_slot=validation_result.get('requested_slot'),
                consecutive_slots=validation_result.get('consecutive_slots', []),
                max_slot_count=validation_result.get('max_slot_count', 0),
                slot_duration_minutes=slot_duration_minutes,
                window_end=validation_result.get('window_end'),
                error=erreur_du_formulaire,
            )
            if request.htmx:
                return render(request, 'booking/partials/book_form.html', context, status=422)
            return render(request, 'booking/views/book.html', context)

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
            custom_amount=custom_amount,
            custom_form=reponses_au_formulaire,
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

            # Une demande à validation manuelle : pas de paiement maintenant.
            # Les deux mails « demande reçue » partent après le commit : la tâche
            # Celery doit trouver le booking en base.
            # / A manual validation request: no payment now. Both "request received"
            # emails are sent after commit, so the task finds the booking.
            est_une_demande_a_valider = result.status == Booking.ADMIN_WAITING
            if est_une_demande_a_valider:
                pk_de_la_demande = str(result.pk)
                transaction.on_commit(lambda: send_booking_request_admin.delay(pk_de_la_demande))
                transaction.on_commit(lambda: send_booking_request_user.delay(pk_de_la_demande))
                messages.success(request, _(
                    "Votre demande de réservation a été envoyée. "
                    "Vous recevrez une confirmation ou une invitation à payer par mail."
                ))
            elif checkout_url is None:
                messages.success(request, _("Réservation créée avec succès."))

            if request.htmx:
                return HttpResponseClientRedirect(target_url)
            return redirect(target_url)

        # Échec (modification concurrente, créneau commencé, tarif refusé, montant sous le
        # minimum Stripe, etc.) — re-render avec les créneaux recalculés et le message
        # d'erreur renvoyé par validate_new_booking, qui donne la raison exacte.
        # / Failure (race condition, slot started, refused price, amount below the Stripe
        # minimum, etc.) — re-render with freshly computed slots and the exact error message.
        tz = timezone.get_current_timezone()
        horizon_end = timezone.make_aware(
            datetime.datetime.combine(
                start_datetime.astimezone(tz).date()
                + datetime.timedelta(days=resource.booking_horizon_days + 1),
                datetime.time.min,
            ),
            tz,
        )
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
        )
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

    # ── Paiement d'une demande validée ───────────────────────────────────────

    @action(detail=True, methods=['get'], url_path="pay", url_name="pay")
    def pay(self, request, pk=None):
        """
        Envoie la personne vers Stripe pour payer une demande validée par l'admin.
        / Sends the person to Stripe to pay an admin-validated request.

        LOCALISATION : booking/views.py

        Lien du mail « demande acceptée » et du bouton « Payer » de « Mes réservations ».
        Même logique que BaseBillet/views.py, get_checkout_for_membership.
        / Link of the "request accepted" email and of the "Pay" button in my bookings.

        FLUX :
        1. Personne non connectée -> page de connexion, puis retour ici.
        2. Booking d'une autre personne -> 404.
        3. Déjà payé, ou validé sans reste à payer -> page « déjà payée ».
        4. Pas encore validé -> page « en attente de validation » (409).
        5. Plus validé (refusé, annulé...) -> page « lien plus valable » (409).
        6. Une session Stripe existe encore : ouverte -> on la réutilise ;
           terminée -> page « paiement en cours » ; sinon -> marquée EXPIRE.
        7. Sinon : nouvelle session Stripe (get_checkout_stripe garde ADMIN_VALID).

        Accès : la personne qui a fait la demande, connectée.
        / Access: the logged-in person who made the request.
        """
        if not request.user.is_authenticated:
            login_url = reverse('connexion')
            return redirect(f'{login_url}?next={request.get_full_path()}')

        booking = get_object_or_404(
            Booking.objects.select_related('resource'),
            pk=pk,
            user=request.user,
        )

        context = get_context(request)
        context['booking'] = booking

        # Validée mais déjà réglée (statut changé à la main) : rien à payer.
        # / Validated but already settled (status changed by hand): nothing to pay.
        deja_reglee = (
            booking.status == Booking.ADMIN_VALID and not booking.est_une_demande_non_payee()
        )
        if booking.status == Booking.PAID_BY_USER or deja_reglee:
            context['situation'] = 'deja_payee'
            return render(request, 'booking/views/pay_info.html', context)

        if booking.status == Booking.ADMIN_WAITING:
            context['situation'] = 'en_attente_de_validation'
            return render(request, 'booking/views/pay_info.html', context, status=409)

        if booking.status != Booking.ADMIN_VALID:
            context['situation'] = 'lien_plus_valable'
            return render(request, 'booking/views/pay_info.html', context, status=409)

        # Une session Stripe déjà créée pour ce booking, pas encore encaissée.
        # / A Stripe session already created for this booking, not yet collected.
        paiement_stripe_existant = booking.paiements.filter(
            status__in=[Paiement_stripe.PENDING, Paiement_stripe.OPEN],
            checkout_session_id_stripe__isnull=False,
        ).order_by('-order_date').first()

        if paiement_stripe_existant:
            try:
                stripe.api_key = RootConfiguration.get_solo().get_stripe_api()
                config = Configuration.get_solo()
                session_stripe = stripe.checkout.Session.retrieve(
                    paiement_stripe_existant.checkout_session_id_stripe,
                    stripe_account=config.get_stripe_connect_account(),
                )
            except Exception as erreur_stripe:
                # En cas de doute, on NE recrée PAS de session : ce pourrait être un
                # deuxième paiement. La personne réessaiera plus tard.
                # / When in doubt, do NOT create a new session: it could be a 2nd payment.
                logger.warning(f"pay : session Stripe du booking {booking.pk} illisible : {erreur_stripe}")
                context['situation'] = 'paiement_en_cours'
                return render(request, 'booking/views/pay_info.html', context)

            # Session encore ouverte : la personne n'a pas fini de payer.
            # / Session still open: the person has not finished paying.
            if session_stripe.status == 'open' and session_stripe.url:
                return redirect(session_stripe.url)

            # Session terminée : le paiement est fait, le retour de Stripe arrive.
            # / Session complete: payment done, Stripe's confirmation is on its way.
            if session_stripe.status == 'complete':
                context['situation'] = 'paiement_en_cours'
                return render(request, 'booking/views/pay_info.html', context)

            # Session expirée chez Stripe : on la marque et on en crée une nouvelle.
            # / Session expired at Stripe: mark it and create a new one.
            paiement_stripe_existant.status = Paiement_stripe.EXPIRE
            paiement_stripe_existant.save(update_fields=['status'])

        # La vente de la demande, ouverte à sa création (validate_new_booking).
        # / The request's sale, opened when it was created.
        vente_de_la_demande = booking.lignearticles.first().vente
        checkout_url = get_checkout_stripe(booking, vente=vente_de_la_demande)
        return redirect(checkout_url)

    # ── Décision de l'admin sur une demande ──────────────────────────────────

    def _recharger_la_fiche_admin(self):
        """
        Recharge la fiche admin du booking après une décision.
        / Reloads the booking admin page after a decision.

        Rechargement complet, pas un simple partiel : le formulaire sous le panneau
        montre le statut. Resté à l'ancien statut, un clic sur « Enregistrer »
        remettrait la demande en attente.
        / Full reload: the form below shows the status; a stale form saved again
        would put the request back to waiting.
        """
        reponse = HttpResponse("")
        reponse["HX-Refresh"] = "true"
        return reponse

    @action(detail=True, methods=['post'], url_path="admin_accept", url_name="admin-accept")
    def admin_accept(self, request, pk=None):
        """
        L'admin accepte une demande de réservation, ou renvoie le lien de paiement.
        / The admin accepts a booking request, or resends the payment link.

        LOCALISATION : booking/views.py

        Appelée par le panneau Administration/templates/admin/booking/actions_panel.html.

        FLUX :
        - ADMIN_WAITING, reste à payer -> ADMIN_VALID + mail « Payer ma réservation ».
        - ADMIN_WAITING, gratuit -> confirmer_booking_gratuit (FREERES / FREERES_USERACTIV,
          vente encaissée à 0) + mail « réservation confirmée ».
        - ADMIN_VALID non payée, avec renvoyer_le_lien=true -> renvoie seulement le mail.
        - Sinon -> rien, un avertissement.

        Le booking est verrouillé (select_for_update) et son statut relu : un double clic,
        ou deux admins en même temps, n'envoient qu'un mail. Le mail part après le commit :
        la tâche lit le statut posé ici.
        / Locked and re-read: a double click sends one email. Email sent after commit.

        Accès : admin du lieu (403 sinon).
        """
        if not TenantAdminPermissionWithRequest(request):
            return HttpResponse(status=403)

        demande_de_renvoi_du_lien = request.POST.get("renvoyer_le_lien") == "true"

        with transaction.atomic():
            booking = get_object_or_404(Booking.objects.select_for_update(), pk=pk)

            if booking.status == Booking.ADMIN_WAITING:
                if booking.to_pay() > 0:
                    booking.status = Booking.ADMIN_VALID
                    booking.save(update_fields=["status"])
                    message_pour_l_admin = _("Demande acceptée. La personne a reçu le lien de paiement par mail.")
                else:
                    ligne_du_creneau = booking.lignearticles.get()
                    confirmer_booking_gratuit(booking, ligne_du_creneau, ligne_du_creneau.vente, booking.user)
                    message_pour_l_admin = _("Demande acceptée. La réservation gratuite est confirmée, la personne a reçu un mail.")

            elif booking.status == Booking.ADMIN_VALID and demande_de_renvoi_du_lien and booking.est_une_demande_non_payee():
                message_pour_l_admin = _("Le lien de paiement a été renvoyé par mail.")

            else:
                messages.warning(request, _("Cette réservation n'est pas en attente de validation."))
                return self._recharger_la_fiche_admin()

            pk_du_booking = str(booking.pk)
            transaction.on_commit(lambda: send_booking_accepted_user.delay(pk_du_booking))

        messages.success(request, message_pour_l_admin)
        return self._recharger_la_fiche_admin()

    @action(detail=True, methods=['post'], url_path="admin_refuse", url_name="admin-refuse")
    def admin_refuse(self, request, pk=None):
        """
        L'admin refuse une demande de réservation non payée, avec un motif facultatif.
        / The admin refuses an unpaid booking request, with an optional reason.

        LOCALISATION : booking/views.py

        Appelée par le panneau Administration/templates/admin/booking/actions_panel.html.

        FLUX : demande en attente (ADMIN_WAITING) ou validée non payée (ADMIN_VALID)
        -> Booking.annuler_la_demande_non_payee(ADMIN_CANCELED) : session Stripe fermée,
        vente et lignes annulées, créneau libéré, motif enregistré.
        Puis mail de refus, après le commit.
        Une réservation déjà payée ne se refuse pas ici : rien ne change, un avertissement.
        / Waiting or validated-unpaid request -> cancelled, then refusal email after commit.

        Accès : admin du lieu (403 sinon).
        """
        if not TenantAdminPermissionWithRequest(request):
            return HttpResponse(status=403)

        validateur_du_motif = MotifDuRefusSerializer(data=request.POST)
        if not validateur_du_motif.is_valid():
            messages.error(request, _("Le motif est trop long (2000 caractères au plus)."))
            return self._recharger_la_fiche_admin()
        motif_du_refus = validateur_du_motif.validated_data.get("motif_du_refus", "")

        with transaction.atomic():
            booking = get_object_or_404(Booking.objects.select_for_update(), pk=pk)

            if not booking.est_une_demande_non_payee():
                messages.warning(request, _("Seule une demande non payée peut être refusée."))
                return self._recharger_la_fiche_admin()

            booking.annuler_la_demande_non_payee(Booking.ADMIN_CANCELED, motif_du_refus=motif_du_refus)

            pk_du_booking = str(booking.pk)
            transaction.on_commit(lambda: send_booking_refused_user.delay(pk_du_booking))

        messages.success(request, _("Demande refusée. La personne a reçu un mail."))
        return self._recharger_la_fiche_admin()

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
            status__in = [Booking.PAID_BY_USER, Booking.ADMIN_VALID, Booking.ADMIN_WAITING,
                           Booking.FREERES, Booking.FREERES_USERACTIV],
        )

        # Une demande non payée se retire jusqu'au début du créneau, sans tenir compte
        # du délai d'annulation (Booking.annulation_possible) : sa date limite affichée
        # est donc le début du créneau. Le gabarit garde le nom deadline_passed.
        # / An unpaid request can be withdrawn until the slot starts: that is its deadline.
        deadline = booking.deadline()
        if booking.est_une_demande_non_payee():
            deadline = booking.start_datetime
        deadline_passed = not booking.annulation_possible()

        if request.method == 'GET':
            context = get_context(request)
            context.update({
                'booking':         booking,
                'deadline':        deadline,
                'deadline_passed': deadline_passed,
            })
            return render(request, 'booking/views/cancel_booking.html', context)

        # POST — recompute deadline to guard against race condition.
        deadline_passed = not booking.annulation_possible()
        if deadline_passed:
            context = get_context(request)
            context.update({
                'booking':         booking,
                'deadline':        deadline,
                'deadline_passed': True,
            })
            return render(request, 'booking/views/cancel_booking.html', context)

        try:
            # Lu AVANT l'annulation : après, le statut est USER_CANCELED.
            # / Read BEFORE cancelling: afterwards the status is USER_CANCELED.
            etait_une_demande_non_payee = booking.est_une_demande_non_payee()
            cancel_text = booking.cancel_and_refund_booking()

            try:
                send_booking_cancellation_user.delay(
                    str(booking.pk),
                    demande_non_payee=etait_une_demande_non_payee,
                )
            except Exception as ce:
                logger.error(f"Failed to queue cancellation email for booking {booking.pk}: {ce}")

            messages.add_message(request, messages.SUCCESS, cancel_text)
            return HttpResponseClientRedirect(reverse('my_account-my-bookings'))

        except Exception as e:
            logger.error(f"Error canceling booking {booking.pk}: {e}")
            messages.add_message(request, messages.ERROR,
                                 _("An error occurred while cancelling your booking.") + f" : {e}")
            return HttpResponseClientRedirect(reverse('my_account-my-bookings'))


