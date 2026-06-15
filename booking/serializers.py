"""
Serializers de l'app booking — réservation de ressources partagées.
/ booking app serializers — shared resource reservation.

LOCALISATION : booking/serializers.py

Les serializers DRF valident les données entrantes.
On n'utilise pas Django Forms — uniquement des serializers.Serializer.
/ DRF serializers validate incoming data.
We do not use Django Forms — only serializers.Serializer.
"""
from rest_framework import serializers


class BookingCreateSerializer(serializers.Serializer):
    """
    Valide les champs numériques du corps POST de la vue book.
    / Validates the numeric fields of the POST body for the book view.

    LOCALISATION : booking/serializers.py

    start_datetime est parsé manuellement dans la vue (datetime naïf local).
    / start_datetime is parsed manually in the view (naive local datetime).

    Champ attendu :
      slot_count — nombre de créneaux consécutifs (entier ≥ 1)
    / Expected field:
      slot_count — number of consecutive slots (integer ≥ 1)

    """
    slot_count = serializers.IntegerField(min_value=1)
