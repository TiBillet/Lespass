"""
Serializers de l'app booking — réservation de ressources partagées
/ booking app serializers — shared resource reservation

LOCALISATION : booking/serializers.py

Les serializers DRF valident les données entrantes.
On n'utilise pas Django Forms — uniquement des serializers.Serializer.
/ DRF serializers validate incoming data.
We do not use Django Forms — only serializers.Serializer.
"""
from rest_framework import serializers


class BookingFormQuerySerializer(serializers.Serializer):
    """
    Valide les paramètres GET de la vue booking_form.
    / Validates the GET query params for the booking_form view.

    LOCALISATION : booking/serializers.py

    Paramètres attendus dans la query string :
      start_datetime        — datetime ISO 8601 tz-aware du créneau demandé
      slot_duration_minutes — durée du créneau en minutes (entier ≥ 1)
    / Expected query string params:
      start_datetime        — tz-aware ISO 8601 datetime of the requested slot
      slot_duration_minutes — slot duration in minutes (integer ≥ 1)
    """
    start_datetime = serializers.DateTimeField()
    slot_duration_minutes = serializers.IntegerField(min_value=1)


class BookingCreateSerializer(serializers.Serializer):
    """
    Valide le corps JSON de la vue add_to_basket.
    / Validates the JSON body for the add_to_basket view.

    LOCALISATION : booking/serializers.py

    Champs attendus dans le corps de la requête POST :
      start_datetime        — datetime ISO 8601 tz-aware du premier créneau
      slot_duration_minutes — durée de chaque créneau en minutes (entier ≥ 1)
      slot_count            — nombre de créneaux à réserver d'un coup (entier ≥ 1)
    / Expected POST body fields:
      start_datetime        — tz-aware ISO 8601 datetime of the first slot
      slot_duration_minutes — duration of each slot in minutes (integer ≥ 1)
      slot_count            — number of consecutive slots to book at once (integer ≥ 1)
    """
    start_datetime = serializers.DateTimeField()
    slot_duration_minutes = serializers.IntegerField(min_value=1)
    slot_count = serializers.IntegerField(min_value=1)


class RemoveFromBasketSerializer(serializers.Serializer):
    """
    Valide le corps de la vue remove_from_basket.
    / Validates the body for the remove_from_basket view.

    LOCALISATION : booking/serializers.py

    Champ attendu :
      booking_pk — clé primaire (entier) de la réservation à retirer
    / Expected field:
      booking_pk — primary key (integer) of the booking to remove
    """
    booking_pk = serializers.IntegerField()


class CancelFormQuerySerializer(serializers.Serializer):
    """
    Valide les paramètres GET de la vue cancel_form.
    / Validates the GET query params for the cancel_form view.

    LOCALISATION : booking/serializers.py

    Paramètres attendus dans la query string :
      start_datetime        — datetime ISO 8601 tz-aware du créneau
      slot_duration_minutes — durée du créneau en minutes (entier ≥ 1)
      remaining_capacity    — capacité restante au moment de l'ouverture du formulaire
      is_new_week           — 0 ou 1 : le créneau démarre une nouvelle semaine ISO
    / Expected query string params:
      start_datetime        — tz-aware ISO 8601 datetime of the slot
      slot_duration_minutes — slot duration in minutes (integer ≥ 1)
      remaining_capacity    — remaining capacity when the form was opened
      is_new_week           — 0 or 1: slot starts a new ISO week
    """
    start_datetime        = serializers.DateTimeField()
    slot_duration_minutes = serializers.IntegerField(min_value=1)
    remaining_capacity    = serializers.IntegerField(min_value=0)
    is_new_week           = serializers.BooleanField()


class CancelBookingSerializer(serializers.Serializer):
    """
    Valide le corps de la vue cancel.
    / Validates the body for the cancel view.

    LOCALISATION : booking/serializers.py

    Champ attendu :
      booking_pk — clé primaire (entier) de la réservation à annuler
    / Expected field:
      booking_pk — primary key (integer) of the booking to cancel
    """
    booking_pk = serializers.IntegerField()
