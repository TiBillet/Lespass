import datetime

from rest_framework import serializers

from ApiBillet.serializers import ReservationSerializer
from AuthBillet.models import TibilletUser
import logging

from BaseBillet.models import Reservation, Ticket

logger = logging.getLogger(__name__)

class CreateUserValidator(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(min_length=8, required=False)


class MeTicketsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ticket
        fields = [
            'uuid',
            'first_name',
            'last_name',
            # 'reservation',
            'pricesold',
            'status',
            'seat',
            # 'event_name',
            'pdf_url',
        ]
        read_only_fields = fields

class MeReservationSerializer(serializers.ModelSerializer):
    tickets = MeTicketsSerializer(many=True)
    class Meta:
        model = Reservation
        fields = [
            'uuid',
            'datetime',
            'event',
            'status',
            'options',
            'tickets',
            'paiements',
        ]
        read_only_fields = fields

class MeSerializer(serializers.ModelSerializer):
    reservations = serializers.SerializerMethodField()

    # On filtre les reservation : pas plus vieille qu'une semaine.
    def get_reservations(self, user):
        last_week = datetime.datetime.now().date() - datetime.timedelta(days=7)
        qs = Reservation.objects.filter(user_commande=user, datetime__gt=last_week)
        serializer = MeReservationSerializer(instance=qs, many=True)
        return serializer.data

    class Meta:
        model = TibilletUser
        fields = [
            'email',
            'first_name',
            'last_name',
            'phone',
            'accept_newsletter',
            'postal_code',
            'birth_date',
            'can_create_tenant',
            'espece',
            'is_staff',
            'reservations'
        ]
        read_only_fields = fields
        # depth = 1
