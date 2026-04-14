"""
Vues de l'app booking — réservation de ressources partagées.
/ booking app views — shared resource reservations.

LOCALISATION : booking/views.py
"""
import datetime
from collections import defaultdict

from django.shortcuts import render
from django.utils import timezone
from rest_framework import viewsets, permissions

from BaseBillet.views import get_context
from booking.booking_engine import compute_slots
from booking.models import Resource


class BookingViewSet(viewsets.ViewSet):
    """
    ViewSet principal de l'app booking.
    / Main ViewSet for the booking app.

    LOCALISATION : booking/views.py
    """
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def list(self, request):
        """
        Page publique : liste des ressources avec leurs créneaux à venir.
        / Public page: resource list with upcoming slots.

        LOCALISATION : booking/views.py — BookingViewSet.list()

        Flux d'exécution :
        1. Construit le contexte de base (skin, config, navbar) via get_context()
        2. Récupère toutes les ressources avec leurs FK
        3. Filtre par tag si le paramètre ?tag= est fourni dans l'URL
        4. Pour chaque ressource, calcule les créneaux des 14 prochains jours
        5. Répartit les ressources en groupes (groupes_annotes) et sans-groupe
           (items_sans_groupe) — les groupes sont purement présentationnels (spec §3.1.2)
        6. Rend le template avec les deux listes

        / Execution flow:
        1. Builds base context (skin, config, navbar) via get_context()
        2. Fetches all resources with their FKs
        3. Filters by tag if ?tag= URL parameter is provided
        4. For each resource, computes slots for the next 14 days
        5. Splits resources into groups (groupes_annotes) and ungrouped
           (items_sans_groupe) — groups are purely presentational (spec §3.1.2)
        6. Renders the template with both lists

        Spec §4.4 — vue publique de réservation.
        / Spec §4.4 — public booking view.
        """
        contexte = get_context(request)

        # Paramètre de filtre par tag (ex : ?tag=salle).
        # / Tag filter URL parameter (e.g. ?tag=salle).
        tag_filtre = request.GET.get('tag', '')

        # Récupère toutes les ressources avec les FK nécessaires au moteur.
        # / Fetch all resources with FKs required by the engine.
        toutes_les_ressources = list(
            Resource.objects.select_related(
                'calendar', 'weekly_opening', 'group',
            ).all()
        )

        # Filtre par tag si demandé — tag doit être dans la liste JSON tags.
        # / Filter by tag if requested — tag must be in the JSON tags list.
        if tag_filtre:
            toutes_les_ressources = [
                ressource for ressource in toutes_les_ressources
                if tag_filtre in ressource.tags
            ]

        # Fenêtre de calcul : aujourd'hui jusqu'à dans 14 jours.
        # / Computation window: today to 14 days ahead.
        date_debut = timezone.localdate()
        date_fin   = date_debut + datetime.timedelta(days=14)

        # Pour chaque ressource : calcule les créneaux, puis répartit en groupes
        # ou sans-groupe. compute_slots() exclut déjà les créneaux passés.
        # / For each resource: compute slots, then split into groups or ungrouped.
        # compute_slots() already excludes past slots.
        items_par_groupe  = defaultdict(list)  # groupe → [item, ...]
        items_sans_groupe = []                 # ressources sans groupe

        for ressource in toutes_les_ressources:
            creneaux = compute_slots(ressource, date_debut, date_fin)
            item = {
                'ressource':      ressource,
                'creneaux':       creneaux,
                'a_des_creneaux': len(creneaux) > 0,
            }
            if ressource.group:
                items_par_groupe[ressource.group].append(item)
            else:
                items_sans_groupe.append(item)

        # Construit la liste ordonnée des sections de groupes.
        # L'ordre suit l'ordre d'insertion du defaultdict (Python 3.7+).
        # / Build ordered list of group sections.
        # Order follows defaultdict insertion order (Python 3.7+).
        groupes_annotes = [
            {'groupe': groupe, 'items': items}
            for groupe, items in items_par_groupe.items()
        ]

        contexte.update({
            'groupes_annotes':   groupes_annotes,
            'items_sans_groupe': items_sans_groupe,
            'tag_filtre':        tag_filtre,
        })

        return render(request, 'booking/views/list.html', contexte)

    def retrieve(self, request, pk=None):
        # Détail d'une ressource — à implémenter
        # / Resource detail — to be implemented
        return render(request, 'booking/views/detail.html', {})
