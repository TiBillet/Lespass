import datetime
import logging

from django.db import connection
from rest_framework import serializers

from ApiBillet.serializers import OptionsSerializer
from AuthBillet.models import TibilletUser
from BaseBillet.models import Reservation, Ticket, Membership

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


class MembershipSerializer(serializers.ModelSerializer):
    # products = ProductSerializer(many=True)
    option_generale = OptionsSerializer(many=True)

    class Meta:
        model = Membership
        fields = [
            'price',
            'price_name',
            'product_uuid',
            'product_name',
            # 'product',
            'date_added',
            'first_contribution',
            'last_contribution',
            'deadline',
            'status',
            'contribution_value',
            'last_action',
            'first_name',
            'last_name',
            'pseudo',
            'newsletter',
            'postal_code',
            'birth_date',
            'phone',
            'email',
            'option_generale',
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


# noinspection PyUnresolvedReferences
class MeSerializer(serializers.ModelSerializer):
    reservations = serializers.SerializerMethodField()
    membership = serializers.SerializerMethodField()
    admin_this_tenant = serializers.SerializerMethodField()

    # membership = MembershipSerializer(many=True )

    # On filtre les reservation : pas plus vieille qu'une semaine.
    def get_reservations(self, user):
        reservation_valide = [
            Reservation.FREERES_USERACTIV,
            Reservation.PAID,
            Reservation.VALID
        ]
        last_week = datetime.datetime.now().date() - datetime.timedelta(days=7)
        qs = Reservation.objects.filter(user_commande=user, datetime__gt=last_week, status__in=reservation_valide)
        serializer = MeReservationSerializer(instance=qs, many=True)
        return serializer.data

    def get_membership(self, user: TibilletUser):
        # Last contibution est False si aucun paiement n'a jamais été fait.
        qs = user.memberships.filter(last_contribution__isnull=False)
        serializer = MembershipSerializer(instance=qs, many=True)
        return serializer.data

    def get_admin_this_tenant(self, user: TibilletUser):
        this_tenant: Client = connection.tenant
        if user.is_tenant_admin(this_tenant):
            return True

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
            # 'can_create_tenant',
            'espece',
            'is_staff',
            'as_password',
            'reservations',
            'membership',
            'admin_this_tenant',
        ]
        read_only_fields = fields
        # depth = 1
