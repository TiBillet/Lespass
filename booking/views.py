"""
Vues de l'app booking.
/ booking app views.

LOCALISATION : booking/views.py
"""
from collections import Counter, defaultdict


def annoter_creneaux_pour_affichage(creneaux):
    """
    Annote chaque créneau avec les indicateurs visuels d'affichage.
    / Annotates each slot with visual display indicators.

    LOCALISATION : booking/views.py

    Ces propriétés ne font pas partie de la logique métier (booking_engine.py).
    Elles sont calculées ici, dans la couche vue, car elles servent uniquement
    au rendu HTML (slot_row.html).
    / These properties are not part of the booking logic (booking_engine.py).
    They are computed here, in the view layer, because they only serve
    HTML rendering (slot_row.html).

    Propriétés ajoutées / Added properties:
      is_in_group  — True si le créneau appartient à un groupe de ≥ 2 créneaux
                     consécutifs issus du même OpeningEntry × date
      is_group_end — True si dernier (ou seul) créneau du groupe
      is_new_week  — True si ce créneau démarre une nouvelle semaine ISO
                     (jamais True pour le tout premier créneau de la liste)

    :param creneaux: list[BookableInterval]
    :return: list[BookableInterval] — mêmes objets, annotés en place
    """
    group_id_counts = Counter(creneau.group_id for creneau in creneaux)

    for i, creneau in enumerate(creneaux):
        creneau.is_in_group = group_id_counts[creneau.group_id] > 1

        suivant_meme_groupe = (
            i < len(creneaux) - 1
            and creneaux[i + 1].group_id == creneau.group_id
        )
        creneau.is_group_end = not suivant_meme_groupe

        # is_new_week : vrai si la semaine ISO change par rapport au créneau précédent.
        # Le tout premier créneau ne déclenche jamais de séparateur de semaine.
        # / is_new_week: True when the ISO week changes from the previous slot.
        # The very first slot never triggers a week separator.
        if i > 0:
            semaine_courante   = creneau.start.isocalendar()[:2]
            semaine_precedente = creneaux[i - 1].start.isocalendar()[:2]
            creneau.is_new_week = semaine_courante != semaine_precedente
        else:
            creneau.is_new_week = False

    return creneaux

from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils.dateparse import parse_datetime
from rest_framework import viewsets, permissions
from rest_framework.decorators import action

from BaseBillet.views import get_context
from booking.booking_engine import (
    compute_max_consecutive_slots,
    compute_slots,
    validate_new_booking,
)
from booking.models import Resource
from booking.serializers import (
    BookingCreateSerializer,
    BookingFormQuerySerializer,
    CancelBookingSerializer,
    RemoveFromBasketSerializer,
)


class BookingViewSet(viewsets.ViewSet):
    """
    LOCALISATION : booking/views.py
    """
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def _annote_ressources(self, request):
        """
        Retourne (groupes_annotes, items_sans_groupe, tag_filtre).
        compute_slots() exclut déjà les créneaux passés.
        / Returns (groupes_annotes, items_sans_groupe, tag_filtre).
        compute_slots() already excludes past slots.
        """
        tag_filtre = request.GET.get('tag', '')

        toutes_les_ressources = list(
            Resource.objects.select_related(
                'calendar', 'weekly_opening', 'group',
            ).all()
        )

        if tag_filtre:
            toutes_les_ressources = [
                r for r in toutes_les_ressources
                if tag_filtre in r.tags
            ]

        items_par_groupe  = defaultdict(list)
        items_sans_groupe = []

        for ressource in toutes_les_ressources:
            creneaux = compute_slots(ressource)
            item = {
                'ressource':      ressource,
                'creneaux':       creneaux,
                'a_des_creneaux': len(creneaux) > 0,
            }
            if ressource.group:
                items_par_groupe[ressource.group].append(item)
            else:
                items_sans_groupe.append(item)

        # defaultdict préserve l'ordre d'insertion (Python 3.7+).
        # / defaultdict preserves insertion order (Python 3.7+).
        groupes_annotes = [
            {'groupe': groupe, 'items': items}
            for groupe, items in items_par_groupe.items()
        ]

        return groupes_annotes, items_sans_groupe, tag_filtre

    def _reservations_en_cours(self, request):
        """
        Retourne les réservations 'new' de l'utilisateur connecté, ou [] sinon.
        / Returns the authenticated user's 'new' bookings, or [] otherwise.

        LOCALISATION : booking/views.py
        """
        if not request.user.is_authenticated:
            return []
        from booking.models import Booking
        return Booking.objects.filter(
            user   = request.user,
            status = Booking.STATUS_NEW,
        ).select_related('resource')

    def _slot_li_id(self, ressource_pk, start_datetime):
        """
        Construit l'id DOM d'une ligne de créneau.
        Doit correspondre au format "slot-<pk>-<Ymd-Hi>" des templates.
        / Builds the DOM id of a slot row.
        Must match the "slot-<pk>-<Ymd-Hi>" format used in templates.
        """
        if start_datetime:
            return f"slot-{ressource_pk}-{start_datetime.strftime('%Y%m%d-%H%M')}"
        return f"slot-{ressource_pk}-unknown"

    def list(self, request):
        contexte = get_context(request)
        groupes_annotes, items_sans_groupe, tag_filtre = self._annote_ressources(request)

        contexte.update({
            'groupes_annotes':    groupes_annotes,
            'items_sans_groupe':  items_sans_groupe,
            'tag_filtre':         tag_filtre,
            'reservations_en_cours': self._reservations_en_cours(request),
        })

        return render(request, 'booking/views/home.html', contexte)

    @action(detail=False, methods=['GET'], url_path=r'resource/(?P<pk>[^/.]+)', url_name='resource')
    def resource_page(self, request, pk=None):
        ressource = get_object_or_404(
            Resource.objects.select_related('calendar', 'weekly_opening', 'group'),
            pk=pk,
        )
        creneaux = annoter_creneaux_pour_affichage(compute_slots(ressource))
        contexte = get_context(request)
        contexte.update({
            'ressource':             ressource,
            'creneaux':              creneaux,
            'reservations_en_cours': self._reservations_en_cours(request),
        })
        return render(request, 'booking/views/resource.html', contexte)

    @action(detail=True, methods=['GET'])
    def booking_form(self, request, pk=None):
        """
        Affiche le formulaire de réservation pour un créneau donné.
        / Shows the booking form for a given slot.

        LOCALISATION : booking/views.py

        Paramètres GET (query string) :
          start_datetime        — datetime ISO 8601 tz-aware du créneau
          slot_duration_minutes — durée en minutes

        Accès :
          Authentifié   → HTTP 200 avec le formulaire
          Non authentifié → HTTP 302 vers LOGIN_URL?next=<url courante>
        / Access:
          Authenticated   → HTTP 200 with the form
          Unauthenticated → HTTP 302 to LOGIN_URL?next=<current url>
        """
        # Redirige les visiteurs non connectés vers la page de connexion.
        # Ce projet utilise /connexion/ (name='connexion') — pas django.contrib.auth.urls.
        # Django définit toujours LOGIN_URL='/accounts/login/' dans global_settings.py,
        # donc on ne peut pas utiliser settings.LOGIN_URL comme détection d'absence.
        # / Redirect unauthenticated visitors to the login page.
        # This project uses /connexion/ (name='connexion') — not django.contrib.auth.urls.
        # Django always sets LOGIN_URL='/accounts/login/' via global_settings.py,
        # so we cannot use settings.LOGIN_URL to detect its absence.
        if not request.user.is_authenticated:
            from django.urls import reverse
            login_url = reverse('connexion')
            url_de_retour = f'{login_url}?next={request.get_full_path()}'

            # Requête HTMX : renvoie HX-Redirect pour forcer une navigation
            # complète vers la connexion. Sans cela, Django renverrait un 302
            # que le navigateur suivrait en chargeant la page de connexion
            # DANS la div cible — mauvaise UX.
            # / HTMX request: send HX-Redirect to force full navigation to
            # login. Without this, Django would return a 302 that the browser
            # follows by loading the login page INSIDE the target div — bad UX.
            if request.htmx:
                reponse = HttpResponse()
                reponse['HX-Redirect'] = url_de_retour
                return reponse

            return redirect(url_de_retour)

        ressource = get_object_or_404(
            Resource.objects.select_related('calendar', 'weekly_opening'),
            pk=pk,
        )

        # Valide les paramètres de créneau fournis dans la query string.
        # / Validates slot parameters from the query string.
        serializer_params = BookingFormQuerySerializer(data=request.GET)
        if not serializer_params.is_valid():
            contexte = get_context(request)
            contexte.update({
                'ressource':        ressource,
                'slot_li_id':       self._slot_li_id(ressource.pk, None),
                'start_datetime':   None,
                'slot_indisponible': True,
            })
            return render(request, 'booking/partial/booking_form.html', contexte)

        start_datetime        = serializer_params.validated_data['start_datetime']
        slot_duration_minutes = serializer_params.validated_data['slot_duration_minutes']
        slot_li_id            = self._slot_li_id(ressource.pk, start_datetime)

        creneaux = compute_slots(ressource)

        # Cherche le créneau demandé dans E (même début et même durée).
        # / Looks up the requested slot in E (matching start and duration).
        creneau_demande = None
        for creneau in creneaux:
            if (creneau.start == start_datetime
                    and creneau.duration_minutes() == slot_duration_minutes):
                creneau_demande = creneau
                break

        # Créneau absent de E ou capacité épuisée → affiche le message d'indisponibilité.
        # / Slot not in E or capacity exhausted → show unavailability message.
        if creneau_demande is None or creneau_demande.remaining_capacity <= 0:
            contexte = get_context(request)
            contexte.update({
                'ressource':        ressource,
                'slot_li_id':       slot_li_id,
                'start_datetime':   start_datetime,
                'slot_indisponible': True,
            })
            return render(request, 'booking/partial/booking_form.html', contexte)

        max_slot_count = compute_max_consecutive_slots(
            creneaux, start_datetime, slot_duration_minutes
        )

        contexte = get_context(request)
        contexte.update({
            'ressource':            ressource,
            'slot_li_id':           slot_li_id,
            'creneau':              creneau_demande,
            'max_slot_count':       max_slot_count,
            'slot_duration_minutes': slot_duration_minutes,
            'start_datetime':       start_datetime,
        })
        return render(request, 'booking/partial/booking_form.html', contexte)

    @action(detail=True, methods=['POST'], permission_classes=[permissions.AllowAny])
    def add_to_basket(self, request, pk=None):
        """
        Crée une réservation avec le statut 'new' (ajout au panier).
        / Creates a booking with status 'new' (add to basket).

        LOCALISATION : booking/views.py

        Corps de la requête (JSON) :
          start_datetime        — datetime ISO 8601 tz-aware du premier créneau
          slot_duration_minutes — durée de chaque créneau en minutes
          slot_count            — nombre de créneaux consécutifs à réserver

        Réponses :
          HTTP 200 — réservation créée, renvoie le partial panier
          HTTP 401 — utilisateur non authentifié
          HTTP 422 — validation échouée (créneau complet, hors horizon, passé, etc.)
        / Responses:
          HTTP 200 — booking created, returns the basket partial
          HTTP 401 — unauthenticated user
          HTTP 422 — validation failed (full slot, beyond horizon, past, etc.)
        """
        # Refuse les requêtes non authentifiées avec HTTP 401.
        # / Reject unauthenticated requests with HTTP 401.
        if not request.user.is_authenticated:
            return HttpResponse(status=401)

        ressource = get_object_or_404(Resource, pk=pk)

        # Essaie de lire start_datetime depuis les données brutes pour le slot_li_id,
        # même si le serializer échoue plus tard.
        # / Try to read start_datetime from raw data for slot_li_id,
        # even if the serializer fails later.
        start_datetime_brut = parse_datetime(
            request.data.get('start_datetime', '')
        )
        slot_duration_brut = request.data.get('slot_duration_minutes')
        slot_li_id = self._slot_li_id(ressource.pk, start_datetime_brut)

        # request.data est parsé automatiquement par DRF selon le Content-Type.
        # / request.data is parsed automatically by DRF based on Content-Type.
        serializer_corps = BookingCreateSerializer(data=request.data)
        if not serializer_corps.is_valid():
            contexte = get_context(request)
            contexte.update({
                'ressource':            ressource,
                'slot_li_id':           slot_li_id,
                'start_datetime':       start_datetime_brut,
                'slot_duration_minutes': slot_duration_brut,
                'erreur':               serializer_corps.errors,
            })
            return render(
                request,
                'booking/partial/booking_form.html',
                contexte,
                status=422,
            )

        start_datetime        = serializer_corps.validated_data['start_datetime']
        slot_duration_minutes = serializer_corps.validated_data['slot_duration_minutes']
        slot_li_id            = self._slot_li_id(ressource.pk, start_datetime)

        is_valid, resultat = validate_new_booking(
            resource              = ressource,
            start_datetime        = start_datetime,
            slot_duration_minutes = slot_duration_minutes,
            slot_count            = serializer_corps.validated_data['slot_count'],
            member                = request.user,
        )

        if not is_valid:
            contexte = get_context(request)
            contexte.update({
                'ressource':            ressource,
                'slot_li_id':           slot_li_id,
                'start_datetime':       start_datetime,
                'slot_duration_minutes': slot_duration_minutes,
                'erreur':               resultat,
            })
            return render(
                request,
                'booking/partial/booking_form.html',
                contexte,
                status=422,
            )

        # Réservation créée — renvoie la ligne du créneau mise à jour (capacité
        # décrémentée) + le panier mis à jour en OOB swap.
        # Le slot_row.html remplace le <li> du formulaire via outerHTML.
        # / Booking created — return the updated slot row (decremented capacity)
        # + the updated basket as an OOB swap.
        # slot_row.html replaces the form <li> via outerHTML.

        # Recompute le créneau pour obtenir la capacité après réservation.
        # Les annotations d'affichage sont ajoutées pour que slot_row.html
        # rende correctement les indicateurs visuels du créneau mis à jour.
        # / Recompute the slot to get capacity after booking.
        # Display annotations are added so slot_row.html renders the updated
        # slot's visual indicators correctly.
        creneaux_mis_a_jour = annoter_creneaux_pour_affichage(compute_slots(ressource))
        creneau_mis_a_jour = None
        for creneau in creneaux_mis_a_jour:
            if (creneau.start == start_datetime
                    and creneau.duration_minutes() == slot_duration_minutes):
                creneau_mis_a_jour = creneau
                break

        contexte_slot = {
            'ressource': ressource,
            'creneau':   creneau_mis_a_jour,
        }
        contexte_panier = get_context(request)
        contexte_panier.update({
            'reservations_en_cours': self._reservations_en_cours(request),
            'oob': True,
        })

        slot_html   = render_to_string(
            'booking/partial/slot_row.html', contexte_slot, request=request,
        )
        panier_html = render_to_string(
            'booking/partial/basket.html', contexte_panier, request=request,
        )
        return HttpResponse(slot_html + panier_html)

    @action(detail=True, methods=['POST'], permission_classes=[permissions.AllowAny])
    def remove_from_basket(self, request, pk=None):
        """
        Supprime une réservation 'new' du panier de l'utilisateur.
        / Removes a 'new' booking from the user's basket.

        LOCALISATION : booking/views.py

        Corps de la requête :
          booking_pk — clé primaire de la réservation à retirer

        Réponses :
          HTTP 200 — réservation supprimée, renvoie le partial panier mis à jour
          HTTP 401 — utilisateur non authentifié
          HTTP 422 — réservation introuvable, non 'new', ou appartenant à un autre membre
        / Responses:
          HTTP 200 — booking deleted, returns updated basket partial
          HTTP 401 — unauthenticated user
          HTTP 422 — booking not found, not 'new', or owned by another member
        """
        if not request.user.is_authenticated:
            return HttpResponse(status=401)

        ressource = get_object_or_404(Resource, pk=pk)

        serializer_corps = RemoveFromBasketSerializer(data=request.data)
        if not serializer_corps.is_valid():
            contexte = get_context(request)
            contexte.update({'erreur': serializer_corps.errors})
            return render(
                request, 'booking/partial/basket.html', contexte, status=422,
            )

        from booking.models import Booking

        # Cherche la réservation appartenant à cet utilisateur.
        # / Look up the booking owned by this user.
        try:
            reservation_a_supprimer = Booking.objects.get(
                pk   = serializer_corps.validated_data['booking_pk'],
                user = request.user,
            )
        except Booking.DoesNotExist:
            contexte = get_context(request)
            contexte.update({'erreur': 'Réservation introuvable.'})
            return render(
                request, 'booking/partial/basket.html', contexte, status=422,
            )

        # Seules les réservations 'new' peuvent être retirées du panier.
        # Les réservations 'confirmed' passent par le flux d'annulation.
        # / Only 'new' bookings can be removed from the basket.
        # 'Confirmed' bookings go through the cancellation flow.
        if reservation_a_supprimer.status != Booking.STATUS_NEW:
            contexte = get_context(request)
            contexte.update({'erreur': 'Seules les réservations en attente peuvent être retirées.'})
            return render(
                request, 'booking/partial/basket.html', contexte, status=422,
            )

        reservation_a_supprimer.delete()

        # Recharge la page courante pour mettre à jour à la fois le panier
        # et les disponibilités des créneaux (capacité restante).
        # HX-Redirect est intercepté par HTMX : il déclenche window.location
        # sans passer par la cascade de swap normale.
        # / Reload the current page to update both the basket and slot
        # availability (remaining capacity).
        # HX-Redirect is intercepted by HTMX: it triggers window.location
        # without going through the normal swap cascade.
        url_de_retour = request.META.get('HTTP_REFERER', '/booking/')
        reponse = HttpResponse(status=200)
        reponse['HX-Redirect'] = url_de_retour
        return reponse

    @action(detail=False, methods=['POST'], permission_classes=[permissions.AllowAny])
    def validate_basket(self, request):
        """
        Valide toutes les réservations 'new' de l'utilisateur → statut 'confirmed'.
        / Validates all 'new' bookings for the user → status 'confirmed'.

        LOCALISATION : booking/views.py

        Le paiement est reporté à une session ultérieure.
        La transition directe new → confirmed s'applique pour l'instant.
        / Payment is deferred to a later session.
        The direct new → confirmed transition applies for now.

        Réponses :
          HTTP 200 — réservations confirmées, renvoie le partial de confirmation
          HTTP 401 — utilisateur non authentifié
          HTTP 422 — panier vide
        / Responses:
          HTTP 200 — bookings confirmed, returns the confirmation partial
          HTTP 401 — unauthenticated user
          HTTP 422 — empty basket
        """
        if not request.user.is_authenticated:
            return HttpResponse(status=401)

        from booking.models import Booking

        reservations_new = list(
            Booking.objects.filter(
                user   = request.user,
                status = Booking.STATUS_NEW,
            )
        )

        if not reservations_new:
            contexte = get_context(request)
            contexte.update({'erreur': 'Votre panier est vide.'})
            return render(
                request, 'booking/partial/basket.html', contexte, status=422,
            )

        # Passe toutes les réservations 'new' à 'confirmed'.
        # / Move all 'new' bookings to 'confirmed'.
        nombre_de_reservations = len(reservations_new)
        for reservation in reservations_new:
            reservation.status = Booking.STATUS_CONFIRMED
            reservation.save(update_fields=['status'])

        contexte = get_context(request)
        contexte.update({'nombre_de_reservations': nombre_de_reservations})
        return render(request, 'booking/partial/basket_confirmed.html', contexte)

    @action(detail=False, methods=['POST'], permission_classes=[permissions.AllowAny])
    def cancel(self, request):
        """
        Annule une réservation 'confirmed' si la deadline n'est pas dépassée.
        / Cancels a 'confirmed' booking if the cancellation deadline has not passed.

        LOCALISATION : booking/views.py

        L'annulation est modélisée par la suppression de la ligne Booking —
        aucun statut 'cancelled' n'est stocké (spec §5).
        / Cancellation is modelled as deletion of the Booking row —
        no 'cancelled' status is stored (spec §5).

        Corps de la requête :
          booking_pk — clé primaire (entier) de la réservation à annuler

        Réponses :
          HTTP 200 — réservation supprimée ; HX-Redirect vers /my_account/my_resources/
          HTTP 401 — utilisateur non authentifié
          HTTP 422 — réservation introuvable, deadline dépassée, ou statut invalide
        / Responses:
          HTTP 200 — booking deleted; HX-Redirect to /my_account/my_resources/
          HTTP 401 — unauthenticated user
          HTTP 422 — booking not found, deadline exceeded, or invalid status
        """
        import datetime
        from django.utils.translation import gettext as _
        from booking.models import Booking
        from django.utils import timezone

        # Refuse les requêtes non authentifiées avec HTTP 401.
        # / Reject unauthenticated requests with HTTP 401.
        if not request.user.is_authenticated:
            return HttpResponse(status=401)

        serializer_corps = CancelBookingSerializer(data=request.data)
        if not serializer_corps.is_valid():
            contexte = get_context(request)
            contexte.update({'erreur': serializer_corps.errors})
            return render(
                request, 'booking/partial/cancel_error.html', contexte, status=422,
            )

        # Cherche la réservation appartenant à cet utilisateur.
        # Un booking d'un autre membre lève DoesNotExist — pas de fuite d'information.
        # / Look up the booking owned by this user.
        # Another member's booking raises DoesNotExist — no information leak.
        try:
            reservation = Booking.objects.select_related('resource').get(
                pk   = serializer_corps.validated_data['booking_pk'],
                user = request.user,
            )
        except Booking.DoesNotExist:
            contexte = get_context(request)
            contexte.update({'erreur': _('Réservation introuvable.')})
            return render(
                request, 'booking/partial/cancel_error.html', contexte, status=422,
            )

        # Seules les réservations 'confirmed' sont annulables par ce flux.
        # Les réservations 'new' se suppriment via remove_from_basket.
        # / Only 'confirmed' bookings are cancellable through this flow.
        # 'new' bookings are removed via remove_from_basket.
        if reservation.status != Booking.STATUS_CONFIRMED:
            contexte = get_context(request)
            contexte.update({
                'erreur': _('Seules les réservations confirmées peuvent être annulées.'),
            })
            return render(
                request, 'booking/partial/cancel_error.html', contexte, status=422,
            )

        # Calcule la deadline : start_datetime − cancellation_deadline_hours.
        # Si now() > deadline, l'annulation est refusée.
        # / Compute the deadline: start_datetime − cancellation_deadline_hours.
        # If now() > deadline, cancellation is refused.
        deadline = reservation.start_datetime - datetime.timedelta(
            hours=reservation.resource.cancellation_deadline_hours,
        )
        if timezone.now() > deadline:
            contexte = get_context(request)
            contexte.update({
                'erreur_deadline':  True,
                'reservation':      reservation,
                'deadline_datetime': deadline,
            })
            return render(
                request, 'booking/partial/cancel_error.html', contexte, status=422,
            )

        # Annulation autorisée — supprime la ligne Booking.
        # / Cancellation allowed — delete the Booking row.
        reservation.delete()

        reponse = HttpResponse(status=200)
        reponse['HX-Redirect'] = '/my_account/my_resources/'
        return reponse
