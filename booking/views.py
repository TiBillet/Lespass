"""
Vues de l'app booking.
/ booking app views.

LOCALISATION : booking/views.py
"""
import datetime
from collections import defaultdict

from django.shortcuts import render
from django.utils import timezone
from rest_framework import viewsets, permissions
from rest_framework.decorators import action

from BaseBillet.views import get_context
from booking.booking_engine import compute_slots
from booking.models import Resource


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

        date_debut = timezone.localdate()
        date_fin   = date_debut + datetime.timedelta(days=14)

        items_par_groupe  = defaultdict(list)
        items_sans_groupe = []

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

        # defaultdict préserve l'ordre d'insertion (Python 3.7+).
        # / defaultdict preserves insertion order (Python 3.7+).
        groupes_annotes = [
            {'groupe': groupe, 'items': items}
            for groupe, items in items_par_groupe.items()
        ]

        return groupes_annotes, items_sans_groupe, tag_filtre

    def list(self, request):
        contexte = get_context(request)
        groupes_annotes, items_sans_groupe, tag_filtre = self._annote_ressources(request)

        contexte.update({
            'groupes_annotes':   groupes_annotes,
            'items_sans_groupe': items_sans_groupe,
            'tag_filtre':        tag_filtre,
        })

        return render(request, 'booking/views/list.html', contexte)

    @action(detail=False, methods=['GET'])
    def embed(self, request):
        """
        Page intégrable en iframe — sans chrome (spec §4.4).
        Réutilise list.html en remplaçant base_template par embed_base.html.
        / iframe-embeddable page — chrome-free (spec §4.4).
        Reuses list.html by swapping base_template for embed_base.html.
        """
        contexte = get_context(request)
        groupes_annotes, items_sans_groupe, tag_filtre = self._annote_ressources(request)

        contexte['base_template'] = 'booking/embed_base.html'
        contexte.update({
            'groupes_annotes':   groupes_annotes,
            'items_sans_groupe': items_sans_groupe,
            'tag_filtre':        tag_filtre,
        })

        reponse = render(request, 'booking/views/list.html', contexte)
        reponse['X-Frame-Options'] = 'ALLOWALL'
        return reponse

    def retrieve(self, request, pk=None):
        # à implémenter / to be implemented
        return render(request, 'booking/views/detail.html', {})
