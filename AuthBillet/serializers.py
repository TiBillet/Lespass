import datetime
import logging

from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.db import connection
from django.utils.translation import gettext_lazy as _
from django_tenants.utils import tenant_context
from rest_framework import serializers
from rest_framework.generics import get_object_or_404
from rest_framework_simplejwt.tokens import RefreshToken

from ApiBillet.serializers import OptionsSerializer
from AuthBillet.models import TibilletUser, TerminalPairingToken
from AuthBillet.utils import MacAdressField
from BaseBillet.models import Reservation, Ticket, Membership

logger = logging.getLogger(__name__)


class CreateUserValidator(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(min_length=8, required=False)

"""
class TokenTerminalValidator(serializers.Serializer):
    email_term = serializers.EmailField()
    unique_id = serializers.CharField()
    mac_adress = MacAdressField()
    ip_locale = serializers.IPAddressField()
    app_token = serializers.CharField()

    def validate(self, attrs):
        validation_data = super().validate(attrs)

        self.term_user = get_object_or_404(TibilletUser,
                                           email=attrs.get('email_term'),
                                           terminal_uuid=attrs.get('unique_id'),
                                           local_ip_sended=attrs.get('ip_locale'),
                                           mac_adress_sended=attrs.get('mac_adress'),
                                           espece=TibilletUser.TYPE_TERM
                                           )

        pairing = get_object_or_404(TerminalPairingToken,
                                    user=self.term_user,
                                    token=self.context.get('token'),
                                    used=False,

                                    )


        PR = PasswordResetTokenGenerator()
        is_token_valid = PR.check_token(self.term_user, attrs.get('app_token'))
        if not is_token_valid:
            raise serializers.ValidationError(_(f'app_token non valide'))

        # token expiration : 10 minutes
        if (datetime.datetime.now() - datetime.timedelta(
                seconds=(100 * 60))).timestamp() > pairing.datetime.timestamp():
            raise serializers.ValidationError(_(f'Token expiré'))

        user_parent = self.term_user.user_parent()
        if not user_parent.is_staff:
            raise serializers.ValidationError(_(f'User invalide'))

        self.tenant_admin = {}
        tenants_admin = user_parent.client_admin.all()
        for tenant in tenants_admin:
            self.term_user.client_admin.add(tenant)
            self.tenant_admin[tenant.name] = tenant.get_primary_domain().domain

        # On enregistre avec le context de l'admin du parent
        # ça crash si on reste sur le tenant public.
        # Pas génant dans la mesure ou le model user est public.
        with tenant_context(tenants_admin.first()):
            self.term_user.is_active = True
            self.term_user.save()

        pairing.used = True
        pairing.save()

        return validation_data

    def to_representation(self, instance):
        representation = super().to_representation(instance)

        refresh = RefreshToken.for_user(self.term_user)
        representation['jwt_token'] = {"refresh": str(refresh), "access": str(refresh.access_token)}

        representation['espece'] = self.term_user.espece
        representation['tenants_admin'] = self.tenant_admin

        return representation
"""


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
        # First contibution est False si aucun paiement n'a jamais été fait.
        qs = user.membership.filter(first_contribution__isnull=False)
        serializer = MembershipSerializer(instance=qs, many=True)
        return serializer.data

    def get_admin_this_tenant(self, user: TibilletUser):
        this_tenant: Client = connection.tenant
        if this_tenant in user.client_admin.all():
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
