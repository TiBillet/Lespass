"""
Vues de l'app booking — réservation de ressources partagées
/ booking app views — shared resource reservation

LOCALISATION : booking/views.py

Ce fichier contiendra les ViewSets pour la gestion des réservations
de ressources partagées (salles, équipements, etc.).
Les modèles et la logique métier sont à définir.
/ This file will contain ViewSets for managing shared resource reservations
(rooms, equipment, etc.). Models and business logic are to be defined.
"""
from rest_framework import viewsets, permissions
from django.shortcuts import render


class BookingViewSet(viewsets.ViewSet):
    """
    ViewSet principal de l'app booking.
    / Main ViewSet for the booking app.

    LOCALISATION : booking/views.py

    Gère les réservations de ressources partagées.
    / Manages shared resource reservations.
    """
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def list(self, request):
        # Liste des réservations — à implémenter
        # / List of bookings — to be implemented
        return render(request, 'booking/views/list.html', {})

    def retrieve(self, request, pk=None):
        # Détail d'une réservation — à implémenter
        # / Booking detail — to be implemented
        return render(request, 'booking/views/detail.html', {})
