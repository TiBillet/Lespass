"""
Vues de l'app booking — réservation de ressources partagées.
/ booking app views — shared resource reservation.

LOCALISATION : booking/views.py

Flux v0.1 : GET/POST simples, réservation directement en statut 'confirmed'.
/ v0.1 flow: simple GET/POST, booking created directly with status 'confirmed'.
"""
import datetime
from collections import defaultdict
from dataclasses import dataclass, field
from urllib.parse import urlencode

from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import permissions, viewsets

from BaseBillet.views import get_context
from booking.booking_engine import Interval, compute_slots, validate_new_booking
from booking.models import Booking, Resource
from booking.serializers import BookingCreateSerializer


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



@dataclass
class DisplaySlotGroup:
    """
    Séquence contiguë de DisplaySlot de même durée
    (x.end == next.start et x.slot_duration_minutes == next.slot_duration_minutes).
    Un créneau isolé a un groupe à un seul élément.
    / A contiguous run of DisplaySlot objects sharing the same duration
    (x.end == next.start and x.slot_duration_minutes == next.slot_duration_minutes).
    A solo slot has slots=[itself].
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
            Resource.objects.select_related('group').order_by('name')
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

    def resource_page(self, request, pk=None):
        """
        Affiche le détail d'une ressource et la liste complète de ses créneaux.
        / Displays a resource's detail and the full list of its slots.

        LOCALISATION : booking/views.py

        Accès : public.
        / Access: public.
        """
        resource = get_object_or_404(
            Resource.objects.select_related('calendar', 'weekly_opening', 'group'),
            pk=pk,
        )
        slot_groups = annotate_slots_for_display(compute_slots(resource))
        context = get_context(request)
        context.update({
            'resource':   resource,
            'slot_groups': slot_groups,
        })
        return render(request, 'booking/views/resource.html', context)

    # ── Formulaire et création de réservation ────────────────────────────────

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
            return redirect(redirect_url)

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
            unavailable_url = (
                reverse('booking-slot-unavailable', kwargs={'pk': resource.pk})
                + '?' + urlencode({'start_datetime': start_datetime_raw})
            )
            return redirect(unavailable_url)

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
        return render(request, 'booking/views/book.html', context)

    def _book_post(self, request, resource):
        """
        Crée une réservation confirmée depuis les données POST.
        / Creates a confirmed booking from POST data.

        LOCALISATION : booking/views.py

        Succès    → redirige vers /booking/my-bookings/?new=<pk>
        Échec     → re-render du formulaire avec message d'erreur
        / Success → redirect to /booking/my-bookings/?new=<pk>
        / Failure → re-render the form with an error message
        """
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
        slot_groups_derive   = annotate_slots_for_display(compute_slots(resource, window_derive))
        slot_duration_minutes = None
        for group in slot_groups_derive:
            for slot in group.slots:
                if slot.start == start_datetime:
                    slot_duration_minutes = slot.slot_duration_minutes
                    break
            if slot_duration_minutes:
                break

        if slot_duration_minutes is None:
            return HttpResponseBadRequest()

        serializer_body = BookingCreateSerializer(data=request.POST)
        if not serializer_body.is_valid():
            context = get_context(request)
            context.update({
                'resource':       resource,
                'start_datetime': start_datetime,
                'error':          serializer_body.errors,
            })
            return render(request, 'booking/views/book.html', context)

        slot_count = serializer_body.validated_data['slot_count']

        is_valid, result = validate_new_booking(
            resource              = resource,
            start_datetime        = start_datetime,
            slot_duration_minutes = slot_duration_minutes,
            slot_count            = slot_count,
            member                = request.user,
        )

        if is_valid:
            # Réservation créée — redirige vers mes réservations avec mise en évidence.
            # / Booking created — redirect to my bookings with highlight.
            my_bookings_url = (
                reverse('booking-my-bookings')
                + '?' + urlencode({'new': result.pk})
            )
            return redirect(my_bookings_url)

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
            'slot_duration_minutes': slot_duration_minutes,
            'start_datetime':        start_datetime,
            'group_end':             consecutive_slots[-1].end if consecutive_slots else window_end_derive,
            'cancellation_deadline': cancellation_deadline,
            'cancellation_possible': cancellation_possible,
            'error':                 result,
            'race_condition':        True,
        })
        return render(request, 'booking/views/book.html', context)

    # ── Créneau indisponible ─────────────────────────────────────────────────

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

    def my_bookings(self, request):
        """
        Liste les réservations confirmées du membre : à venir et passées.
        / Lists the member's confirmed bookings: upcoming and past.

        LOCALISATION : booking/views.py

        Accès :
          Non authentifié           → 302 vers /connexion/?next=...
          config.module_booking=False → 404
          Authentifié + module actif  → HTTP 200
        / Access:
          Unauthenticated             → 302 to /connexion/?next=...
          config.module_booking=False → 404
          Authenticated + module on   → HTTP 200
        """
        if not request.user.is_authenticated:
            login_url   = reverse('connexion')
            redirect_url = f'{login_url}?next={request.get_full_path()}'
            return redirect(redirect_url)

        context = get_context(request)
        config  = context['config']
        if not config.module_booking:
            raise Http404

        now = timezone.now()

        upcoming_bookings = (
            Booking.objects
            .filter(user=request.user, status=Booking.STATUS_CONFIRMED, end_datetime__gt=now)
            .select_related('resource')
            .order_by('start_datetime')
        )
        past_bookings = (
            Booking.objects
            .filter(user=request.user, status=Booking.STATUS_CONFIRMED, end_datetime__lte=now)
            .select_related('resource')
            .order_by('-start_datetime')
        )

        # Clé GET optionnelle pour mettre en évidence la nouvelle réservation.
        # / Optional GET key to highlight the newly created booking.
        highlighted_booking_pk = request.GET.get('new')
        if highlighted_booking_pk:
            try:
                highlighted_booking_pk = int(highlighted_booking_pk)
            except (TypeError, ValueError):
                highlighted_booking_pk = None

        context.update({
            'upcoming_bookings':      upcoming_bookings,
            'past_bookings':          past_bookings,
            'highlighted_booking_pk': highlighted_booking_pk,
        })
        return render(request, 'booking/views/my_bookings.html', context)

    # ── Confirmation d'annulation ────────────────────────────────────────────

    def cancel_confirm(self, request, booking_pk=None):
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
            pk     = booking_pk,
            user   = request.user,
            status = Booking.STATUS_CONFIRMED,
        )

        deadline = booking.start_datetime - datetime.timedelta(
            hours=booking.resource.cancellation_deadline_hours,
        )
        deadline_passed = timezone.now() > deadline

        if request.method == 'GET':
            context = get_context(request)
            context.update({
                'booking':         booking,
                'deadline':        deadline,
                'deadline_passed': deadline_passed,
            })
            return render(request, 'booking/views/cancel_booking.html', context)

        # POST — recompute deadline to guard against race condition.
        deadline_passed = timezone.now() > deadline
        if deadline_passed:
            context = get_context(request)
            context.update({
                'booking':         booking,
                'deadline':        deadline,
                'deadline_passed': True,
            })
            return render(request, 'booking/views/cancel_booking.html', context)

        booking.delete()
        return redirect(reverse('booking-my-bookings'))
