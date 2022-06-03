import datetime

from django.contrib.auth.tokens import default_token_generator, PasswordResetTokenGenerator
from django.db import connection
from django_tenants.utils import schema_context, tenant_context
from rest_framework import serializers
from rest_framework.generics import get_object_or_404
from rest_framework_simplejwt.tokens import RefreshToken

from AuthBillet.models import TibilletUser, TermUser, TerminalPairingToken
import logging
from django.utils.translation import ugettext_lazy as _

from AuthBillet.utils import MacAdressField
from BaseBillet.models import Reservation, Ticket, Membership
from BaseBillet.tasks import terminal_pairing_celery_mailer

logger = logging.getLogger(__name__)


class CreateUserValidator(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(min_length=8, required=False)


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


class CreateTerminalValidator(serializers.Serializer):
    email_admin = serializers.EmailField()
    unique_id = serializers.CharField()
    mac_adress = MacAdressField()
    ip_locale = serializers.IPAddressField()

    def validate_email_admin(self, value):
        try:
            with schema_context('public'):
                user = TibilletUser.objects.get(
                    email=value,
                    is_active=True,
                    is_staff=True)

        except TibilletUser.DoesNotExist:
            raise serializers.ValidationError(_(f'DoesNotExist'))
        except Exception as e:
            raise serializers.ValidationError(_(f'{e}'))

        self.user_parent = user
        return user.email

    def validate(self, attrs):
        validation_data = super().validate(attrs)

        part_email = list(self.user_parent.email.partition('@'))
        part_email[0] = f"{part_email[0]}+{attrs.get('unique_id')}"
        email = "".join(part_email).lower()

        logger.info(f'email : {email}, {self.user_parent.pk}')

        term_user, created = TibilletUser.objects.get_or_create(
            email=email,
            username=email,
            user_parent_pk=self.user_parent.pk,
            espece=TibilletUser.TYPE_TERM
        )

        if created:
            term_user.client_source = connection.tenant
            term_user.terminal_uuid = attrs.get('unique_id')
            term_user.local_ip_sended = attrs.get('ip_locale')
            term_user.mac_adress_sended = attrs.get('mac_adress')
        else:
            if term_user.mac_adress_sended != attrs.get('mac_adress'):
                raise serializers.ValidationError(_(f"mac_adress not valid"))

        # for tenant in self.user_parent.client_admin.all():
        #     term_user.client_admin.add(tenant)

        term_user.is_active = False
        term_user.save()

        self.term_user = term_user
        task = terminal_pairing_celery_mailer.delay(term_user.email)

        return validation_data

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['email_admin'] = self.user_parent.email
        representation['term_user'] = self.term_user.email
        representation['espece'] = self.term_user.espece
        representation['app_token'] = default_token_generator.make_token(self.term_user)

        return representation


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
    class Meta:
        model = Membership
        fields = [
            'price',
            'price_name',
            'product_uuid',
            'product_name',
            'date_added',
            'first_contribution',
            'last_contribution',
            'deadline',
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
    membership = MembershipSerializer(many=True)

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
            'reservations',
            'membership'

        ]
        read_only_fields = fields
        # depth = 1
