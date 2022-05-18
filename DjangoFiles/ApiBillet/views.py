# Create your views here.
import json
from datetime import datetime, timedelta

import pytz
import requests
import stripe
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.http import HttpResponseRedirect, Http404, HttpResponse
from django.utils import timezone
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django_tenants.utils import schema_context, tenant_context
from django_weasyprint import WeasyTemplateView
from rest_framework import serializers
from rest_framework.decorators import permission_classes
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from django.utils.translation import ugettext_lazy as _
from django.utils.text import slugify
from rest_framework.views import APIView

from ApiBillet.serializers import EventSerializer, PriceSerializer, ProductSerializer, ReservationSerializer, \
    ReservationValidator, MembreValidator, ConfigurationSerializer, NewConfigSerializer, \
    EventCreateSerializer, TicketSerializer, OptionTicketSerializer, ChargeCashlessValidator, NewAdhesionValidator
from AuthBillet.models import TenantAdminPermission, TibilletUser
from BaseBillet.tasks import create_ticket_pdf, redirect_post_webhook_stripe_from_public
from Customers.models import Client, Domain
from BaseBillet.models import Event, Price, Product, Reservation, Configuration, Ticket, Paiement_stripe, OptionGenerale
from rest_framework import viewsets, permissions, status
from django.db import connection, IntegrityError

import os
import logging

logger = logging.getLogger(__name__)


class TarifBilletViewSet(viewsets.ViewSet):
    def list(self, request):
        queryset = Price.objects.all().order_by('prix')
        serializer = PriceSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)

    def create(self, request):
        serializer = PriceSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            permission_classes = [permissions.AllowAny]
        else:
            permission_classes = [TenantAdminPermission]
        return [permission() for permission in permission_classes]


class ProductViewSet(viewsets.ViewSet):

    def list(self, request):
        serializer = ProductSerializer(
            Product.objects.all(),
            many=True, context={'request': request})
        print(serializer.data)
        return Response(serializer.data)

    def create(self, request):
        serializer = ProductSerializer(data=request.data)
        if serializer.is_valid():
            product = serializer.save()
            if getattr(serializer, 'img_img', None):
                product.img.save(serializer.img_name, serializer.img_img.fp)

            return Response(serializer.data, status=status.HTTP_201_CREATED)
        for error in [serializer.errors[error][0] for error in serializer.errors]:
            if error.code == "unique":
                return Response(serializer.errors, status=status.HTTP_409_CONFLICT)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            permission_classes = [permissions.AllowAny]
        else:
            permission_classes = [TenantAdminPermission]
        return [permission() for permission in permission_classes]

'''

class ArtistViewSet(viewsets.ViewSet):

    def create(self, request):
        user: TibilletUser = request.user
        if not user.can_create_tenant:
            raise serializers.ValidationError(_("Vous n'avez pas la permission de créer de nouveaux lieux"))
        if not request.data.get('categorie'):
            raise serializers.ValidationError(_("categorie est obligatoire"))
        if request.data.get('categorie') not in [Client.ARTISTE, ]:
            raise serializers.ValidationError(_("categorie doit être une salle de spectacle"))

        serializer = NewConfigSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            futur_conf = serializer.validated_data
            with schema_context('public'):
                try:
                    tenant, created = Client.objects.get_or_create(
                        schema_name=slugify(futur_conf.get('organisation')),
                        name=futur_conf.get('organisation'),
                        categorie=request.data.get('categorie'),
                    )

                    if not created:
                        return Response(_(json.dumps(
                            {"uuid": f"{tenant.uuid}", "msg": f"{futur_conf.get('organisation')} existe déja"})),
                            status=status.HTTP_409_CONFLICT)

                    domain, created = Domain.objects.get_or_create(
                        domain=f"{slugify(futur_conf.get('organisation'))}.{os.getenv('DOMAIN')}",
                        tenant=tenant,
                        is_primary=True
                    )
                except IntegrityError as e:
                    return Response(_(f"{e}"), status=status.HTTP_400_BAD_REQUEST)
                except Exception as e:
                    return Response(_(f"{e}"), status=status.HTTP_405_METHOD_NOT_ALLOWED)

            with tenant_context(tenant):
                conf = Configuration.get_solo()
                serializer.update(instance=conf, validated_data=futur_conf)

                user.client_admin.add(tenant)

                place_serialized = ConfigurationSerializer(Configuration.get_solo(), context={'request': request})
                place_serialized_with_uuid = {'uuid': f"{tenant.uuid}"}
                place_serialized_with_uuid.update(place_serialized.data)
            return Response(place_serialized_with_uuid, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, pk=None):
        tenant = get_object_or_404(Client, pk=pk)
        user: TibilletUser = request.user
        if tenant not in user.client_admin.all():
            return Response(_(f"Not Allowed"), status=status.HTTP_405_METHOD_NOT_ALLOWED)
        with tenant_context(tenant):
            conf = Configuration.get_solo()
            serializer = NewConfigSerializer(conf, data=request.data, partial=True)
            if serializer.is_valid():
                print(serializer.validated_data)
                serializer.update(conf, serializer.validated_data)
                return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def list(self, request):
        places_serialized_with_uuid = []
        configurations = []
        for tenant in Client.objects.filter(categorie__in=['A', ]):
            with tenant_context(tenant):
                places_serialized_with_uuid.append({"uuid": f"{tenant.uuid}"})
                configurations.append(Configuration.get_solo())

        places_serialized = ConfigurationSerializer(configurations, context={'request': request}, many=True)

        for key, value in enumerate(places_serialized.data):
            places_serialized_with_uuid[key].update(value)

        return Response(places_serialized_with_uuid)

    def retrieve(self, request, pk=None):
        tenant = get_object_or_404(Client.objects.filter(categorie__in=['A']), pk=pk)
        with tenant_context(tenant):
            place_serialized = ConfigurationSerializer(Configuration.get_solo(), context={'request': request})
            place_serialized_with_uuid = {'uuid': f"{tenant.uuid}"}
            place_serialized_with_uuid.update(place_serialized.data)
        return Response(place_serialized_with_uuid)

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            permission_classes = [permissions.AllowAny]
        else:
            permission_classes = [TenantAdminPermission]
        return [permission() for permission in permission_classes]

'''

class TenantViewSet(viewsets.ViewSet):

    def create(self, request):
        user: TibilletUser = request.user

        if not user.can_create_tenant:
            raise serializers.ValidationError(_("Vous n'avez pas la permission de créer de nouveaux lieux"))
        if not request.data.get('categorie'):
            raise serializers.ValidationError(_("categorie est obligatoire"))

        categories = []
        if 'place' in request.get_full_path():
            categories = [Client.SALLE_SPECTACLE, Client.FESTIVAL]
        if 'artist' in request.get_full_path():
            categories = [Client.ARTISTE]

        if request.data.get('categorie') not in categories:
            raise serializers.ValidationError(_("categorie doit être une salle de spectacle"))

        serializer = NewConfigSerializer(data=request.data, context={'request': request})

        if serializer.is_valid():



            futur_conf = serializer.validated_data
            with schema_context('public'):
                try:
                    tenant, created = Client.objects.get_or_create(
                        schema_name=futur_conf.get('slug'),
                        name=futur_conf.get('organisation'),
                        categorie=request.data.get('categorie'),
                    )

                    if not created:
                        # raise serializers.ValidationError(_("Vous n'avez pas la permission de créer de nouveaux lieux"))
                        return Response(_(json.dumps(
                            {"uuid": f"{tenant.uuid}", "msg": f"{futur_conf.get('organisation')} existe déja"})),
                            status=status.HTTP_409_CONFLICT)

                    domain, created = Domain.objects.get_or_create(
                        domain=f"{futur_conf.get('slug')}.{os.getenv('DOMAIN')}",
                        tenant=tenant,
                        is_primary=True
                    )
                except IntegrityError as e:
                    return Response(_(f"{e}"), status=status.HTTP_400_BAD_REQUEST)
                except Exception as e:
                    return Response(_(f"{e}"), status=status.HTTP_405_METHOD_NOT_ALLOWED)

            print(tenant)
            with tenant_context(tenant):
                conf = Configuration.get_solo()
                serializer.update(instance=conf, validated_data=futur_conf)
                conf.stripe_api_key = os.environ.get('SRIPE_KEY')
                conf.stripe_test_api_key = os.environ.get('SRIPE_KEY_TEST')

                if os.environ.get('STRIPE_TEST') == "False":
                    conf.stripe_mode_test = False
                if os.environ.get('STRIPE_TEST') == "True":
                    conf.stripe_mode_test = True

                if getattr(serializer, 'img_img', None):
                    conf.img.save(serializer.img_name, serializer.img_img.fp)
                if getattr(serializer, 'logo_img', None):
                    conf.logo.save(serializer.logo_name, serializer.logo_img.fp)

                conf.save()
                user.client_admin.add(tenant)

                place_serialized = ConfigurationSerializer(Configuration.get_solo(), context={'request': request})
                place_serialized_with_uuid = {'uuid': f"{tenant.uuid}"}
                place_serialized_with_uuid.update(place_serialized.data)
            return Response(place_serialized_with_uuid, status=status.HTTP_201_CREATED)

        logger.info(f"serializer.errors : {serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, pk=None):
        tenant = get_object_or_404(Client, pk=pk)
        user: TibilletUser = request.user
        if tenant not in user.client_admin.all():
            return Response(_(f"Not Allowed"), status=status.HTTP_405_METHOD_NOT_ALLOWED)
        with tenant_context(tenant):
            conf = Configuration.get_solo()
            print(type(request.data.get('img')))
            print(request.data)
            print(request.headers)
            serializer = NewConfigSerializer(conf, data=request.data, partial=True)
            if serializer.is_valid():
                print(serializer.validated_data)
                # serializer.save()
                serializer.update(conf, serializer.validated_data)
                return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def list(self, request):
        places_serialized_with_uuid = []
        configurations = []
        categories = []
        if 'place' in request.get_full_path():
            categories = [Client.SALLE_SPECTACLE, Client.FESTIVAL]
        if 'artist' in request.get_full_path():
            categories = [Client.ARTISTE]


        for tenant in Client.objects.filter(categorie__in=categories):
            with tenant_context(tenant):
                places_serialized_with_uuid.append({"uuid": f"{tenant.uuid}"})
                configurations.append(Configuration.get_solo())

        places_serialized = ConfigurationSerializer(configurations, context={'request': request}, many=True)

        for key, value in enumerate(places_serialized.data):
            places_serialized_with_uuid[key].update(value)

        return Response(places_serialized_with_uuid)

    def retrieve(self, request, pk=None):
        tenant = get_object_or_404(Client.objects.filter(categorie__in=['S', 'F']), pk=pk)
        with tenant_context(tenant):
            place_serialized = ConfigurationSerializer(Configuration.get_solo(), context={'request': request})
            place_serialized_with_uuid = {'uuid': f"{tenant.uuid}"}
            place_serialized_with_uuid.update(place_serialized.data)
        return Response(place_serialized_with_uuid)

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            permission_classes = [permissions.AllowAny]
        else:
            permission_classes = [TenantAdminPermission]
        return [permission() for permission in permission_classes]


class HereViewSet(viewsets.ViewSet):

    def list(self, request):
        config = Configuration.get_solo()
        place_serialized = ConfigurationSerializer(config, context={'request': request})

        dict_return = {'uuid': f"{connection.tenant.uuid}"}
        dict_return.update(place_serialized.data)

        if config.button_adhesion or config.adhesion_obligatoire:
            products_adhesion = Product.objects.filter(categorie_article=Product.ADHESION)
            if len(products_adhesion) > 0:
                products_serializer = ProductSerializer(products_adhesion, many=True)
                dict_return['membership_products'] = products_serializer.data
        return Response(dict_return)

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            permission_classes = [permissions.AllowAny]
        else:
            permission_classes = [TenantAdminPermission]
        return [permission() for permission in permission_classes]


class EventsSlugViewSet(viewsets.ViewSet):
    def retrieve(self, request, pk=None):
        queryset = Event.objects.all().order_by('-datetime')
        event = get_object_or_404(queryset, slug=pk)
        serializer = EventSerializer(event)
        return Response(serializer.data)


    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            permission_classes = [permissions.AllowAny]
        else:
            permission_classes = [TenantAdminPermission]
        return [permission() for permission in permission_classes]


class EventsViewSet(viewsets.ViewSet):

    def list(self, request):
        tenant: Client = connection.tenant

        if tenant.categorie == Client.SALLE_SPECTACLE :
            queryset = Event.objects.filter(datetime__gte=datetime.now().date()).order_by('datetime')
            events_serialized = EventSerializer(queryset, many=True, context={'request': request})
            return Response(events_serialized.data)

        elif tenant.categorie == Client.META:
            events_serialized_data = []
            tenants = Client.objects.filter(categorie=Client.SALLE_SPECTACLE)
            for other_tenant in tenants:
                with tenant_context(other_tenant):
                    queryset = Event.objects.filter(datetime__gte=datetime.now().date()).order_by('datetime')
                    events_serialized = EventSerializer(queryset, many=True, context={'request': request})
                    for data in events_serialized.data:
                        events_serialized_data.append(data)
            return Response(events_serialized_data)


    def retrieve(self, request, pk=None):
        queryset = Event.objects.all().order_by('-datetime')
        event = get_object_or_404(queryset, pk=pk)
        serializer = EventSerializer(event)
        return Response(serializer.data)

    def create(self, request):
        print(request.data)
        serializer_create = EventCreateSerializer(data=request.data)
        if serializer_create.is_valid():
            # import ipdb; ipdb.set_trace()
            event: Event = serializer_create.validated_data
            serializer = EventSerializer(event)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        print(serializer_create.errors)
        return Response(serializer_create.errors, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, pk=None):
        queryset = Event.objects.all().order_by('-datetime')
        print(f"update : {pk}")
        event = get_object_or_404(queryset, pk=pk)
        print(event)
        serializer = EventSerializer(event, data=request.data, partial=True)
        if serializer.is_valid(raise_exception=True):
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, pk=None):
        queryset = Event.objects.all().order_by('-datetime')
        event = get_object_or_404(queryset, pk=pk)
        event.delete()
        return Response(('deleted'), status=status.HTTP_200_OK)

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            permission_classes = [permissions.AllowAny]
        else:
            permission_classes = [TenantAdminPermission]
        return [permission() for permission in permission_classes]


class ChargeCashless(viewsets.ViewSet):
    def create(self, request):
        print(request.data)
        configuration = Configuration.get_solo()
        if not configuration.key_cashless or not configuration.server_cashless:
            return Response(_("Serveur cashless non présent dans configuration"),
                            status=status.HTTP_405_METHOD_NOT_ALLOWED)

        try:
            response = requests.request("GET",
                                        f"{configuration.server_cashless}/api/checkcarteqruuid/{request.data.get('uuid')}/",
                                        headers={"Authorization": f"Api-Key {configuration.key_cashless}"},
                                        )

            if response.status_code != 200:
                return Response(_(f"Requete non comprise : {response.status_code}"),
                                status=status.HTTP_405_METHOD_NOT_ALLOWED)
        except Exception as e:
            return Response(_(f"Serveur cashless ne répond pas : {e}"), status=status.HTTP_408_REQUEST_TIMEOUT)

        validator = ChargeCashlessValidator(data=request.data, context={'request': request})
        if validator.is_valid():
            # serializer.save()
            return Response(validator.data, status=status.HTTP_201_CREATED)
        return Response(validator.errors, status=status.HTTP_400_BAD_REQUEST)

    def get_permissions(self):
        permission_classes = [permissions.IsAuthenticated]
        return [permission() for permission in permission_classes]


class ReservationViewset(viewsets.ViewSet):
    def list(self, request):
        queryset = Reservation.objects.all().order_by('-datetime')
        serializer = ReservationSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)

    def create(self, request):

        # import ipdb; ipdb.set_trace()
        logger.info(f"ReservationViewset CREATE : {request.data}")

        validator = ReservationValidator(data=request.data, context={'request': request})
        if validator.is_valid():
            return Response(validator.data, status=status.HTTP_201_CREATED)
        return Response(validator.errors, status=status.HTTP_400_BAD_REQUEST)

    def get_permissions(self):
        if self.action in ['list']:
            permission_classes = [TenantAdminPermission]
        else:
            permission_classes = [permissions.AllowAny]
        return [permission() for permission in permission_classes]


class OptionTicket(viewsets.ViewSet):
    def list(self, request):
        queryset = OptionGenerale.objects.all()
        serializer = OptionTicketSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)

    def create(self, request):
        print(request.data)
        validator = OptionTicketSerializer(data=request.data, context={'request': request})
        if validator.is_valid():
            validator.save()
            return Response(validator.data, status=status.HTTP_201_CREATED)
        else:
            for error in [validator.errors[error][0] for error in validator.errors]:
                if error.code == "unique":
                    return Response(validator.errors, status=status.HTTP_409_CONFLICT)
        return Response(validator.errors, status=status.HTTP_400_BAD_REQUEST)

    def get_permissions(self):
        if self.action in ['list']:
            permission_classes = [permissions.AllowAny]
        else:
            permission_classes = [TenantAdminPermission]
        return [permission() for permission in permission_classes]

def borne_temps_4h():
    now = timezone.now()
    jour = now.date()
    tzlocal = pytz.timezone(Configuration.get_solo().fuseau_horaire)
    debut_jour = tzlocal.localize(datetime.combine(jour, datetime.min.time()), is_dst=None) + timedelta(
        hours=4)
    lendemain_quatre_heure = tzlocal.localize(datetime.combine(jour, datetime.max.time()), is_dst=None) + timedelta(
        hours=4)

    if now < debut_jour:
        # Alors on demande au petit matin.
        # Les bornes sont ceux de la veille.
        return debut_jour - timedelta(days=1), debut_jour
    else:
        return debut_jour, lendemain_quatre_heure


@permission_classes([TenantAdminPermission])
class Gauge(APIView):

    # API pour avoir l'état de la jauge ( GAUGE in inglishe ) et des billets scannés.
    def get(self, request):
        config = Configuration.get_solo()
        debut_jour, lendemain_quatre_heure = borne_temps_4h()
        queryset = Ticket.objects.filter(
            reservation__event__datetime__gte=debut_jour,
            reservation__event__datetime__lte=lendemain_quatre_heure,
            status__in=[Ticket.NOT_SCANNED, Ticket.SCANNED]
        )

        data = {
            "gauge_max" : config.jauge_max,
            "all_tickets" : queryset.count(),
            "scanned_tickets" : queryset.filter(status=Ticket.SCANNED).count()
        }

        return Response(data, status=status.HTTP_200_OK)

class TicketViewset(viewsets.ViewSet):
    def list(self, request):
        debut_jour, lendemain_quatre_heure = borne_temps_4h()

        queryset = Ticket.objects.filter(
            reservation__event__datetime__gte=debut_jour,
            reservation__event__datetime__lte=lendemain_quatre_heure,
            status__in=["K","S"]
        )

        serializer = TicketSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)

    def get_permissions(self):
        permission_classes = [TenantAdminPermission]
        return [permission() for permission in permission_classes]


def request_for_data_cashless(user: TibilletUser):
    if user.email_error or not user.email:
        return {'erreur': f"user.email_error {user.email_error}"}

    sess = requests.Session
    configuration = Configuration.get_solo()
    if configuration.server_cashless and configuration.key_cashless:
        try:
            response = requests.request("POST",
                                        f"{configuration.server_cashless}/api/membre_check",
                                        headers={"Authorization": f"Api-Key {configuration.key_cashless}"},
                                        data={"email": user.email})

            if response.status_code != 200:
                return {'erreur': f"{response.status_code} : {response.text}"}
            return json.loads(response.content)
        except Exception as e:
            return {'erreur': f"{e}"}

    return {'erreur': f"pas de configuration server_cashless"}


class MembershipViewset(viewsets.ViewSet):

    def create(self, request):
        print(request.data)
        membre_validator = MembreValidator(data=request.data, context={'request': request})
        if membre_validator.is_valid():
            adhesion_validator = NewAdhesionValidator(data=request.data, context={'request': request})
            if adhesion_validator.is_valid():
                return Response(adhesion_validator.data, status=status.HTTP_201_CREATED)
            return Response(adhesion_validator.errors, status=status.HTTP_400_BAD_REQUEST)
        return Response(membre_validator.errors, status=status.HTTP_400_BAD_REQUEST)

    def retrieve(self, request, pk=None):
        try:
            email = force_str(urlsafe_base64_decode(pk))
        except:
            return Response("base64 email only", status=status.HTTP_406_NOT_ACCEPTABLE)
        User = get_user_model()
        user = User.objects.filter(email=email, username=email).first()

        if user:
            configuration = Configuration.get_solo()
            if configuration.server_cashless and configuration.key_cashless:
                data = request_for_data_cashless(user)
                data_retrieve = {
                    'a_jour_cotisation': data.get('a_jour_cotisation'),
                    'date_derniere_cotisation': data.get('date_derniere_cotisation'),
                    'prochaine_echeance': data.get('prochaine_echeance')
                }
                return Response(data_retrieve, status=status.HTTP_200_OK)

            return Response('no cashless server', status=status.HTTP_404_NOT_FOUND)
        return Response('no User', status=status.HTTP_402_PAYMENT_REQUIRED)

    def get_permissions(self):
        if self.action in ['create', 'retrieve']:
            permission_classes = [permissions.AllowAny]
        else:
            permission_classes = [TenantAdminPermission]

        return [permission() for permission in permission_classes]


class TicketPdf(APIView):
    permission_classes = [AllowAny]

    def get(self, request, pk_uuid):
        ticket = get_object_or_404(Ticket, uuid=pk_uuid)

        VALID_TICKET_FOR_PDF = [Ticket.NOT_SCANNED, Ticket.SCANNED]
        if ticket.status not in VALID_TICKET_FOR_PDF :
            return Response('Ticket non valide', status=status.HTTP_403_FORBIDDEN)

        pdf_binary = create_ticket_pdf(ticket)
        response = HttpResponse(pdf_binary, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{ticket.pdf_filename()}"'
        return response


# class TicketPdf(WeasyTemplateView):
#     permission_classes = [AllowAny]
#     template_name = 'ticket/ticket.html'
#
#     def get_context_data(self, pk_uuid, **kwargs):
#         logger.info(f"{timezone.now()} création de pdf demandé. uuid : {pk_uuid}")
#
#         self.config = Configuration.get_solo()
#         ticket: Ticket = get_object_or_404(Ticket, uuid=pk_uuid)
#         kwargs['ticket'] = ticket
#         kwargs['config'] = self.config
#
#         '''
#         context = {
#             'ticket': ticket,
#             'config': config,
#         }
#         '''
#
#         self.pdf_filename = ticket.pdf_filename()
#         return kwargs
#
#     def get_pdf_filename(self, **kwargs):
#         return self.pdf_filename


# On vérifie que les métatada soient les meme dans la DB et chez Stripe.
def metatadata_valid(paiement_stripe_db: Paiement_stripe, checkout_session):
    metadata_stripe_json = checkout_session.metadata
    metadata_stripe = json.loads(str(metadata_stripe_json))

    metadata_db_json = paiement_stripe_db.metadata_stripe
    metadata_db = json.loads(metadata_db_json)

    try:
        assert metadata_stripe == metadata_db
        assert set(metadata_db.keys()) == set(metadata_stripe.keys())
        for key in set(metadata_stripe.keys()):
            assert metadata_db[key] == metadata_stripe[key]
        return True
    except:
        logger.error(f"{timezone.now()} "
                     f"retour_stripe {paiement_stripe_db.uuid} : "
                     f"metadata ne correspondent pas : {metadata_stripe} {metadata_db}")
        return False


def paiment_stripe_validator(request, paiement_stripe):
    if paiement_stripe.traitement_en_cours:

        data = {
            "msg": 'Paiement validé. Création des billets et envoi par mail en cours.',
        }
        if paiement_stripe.reservation:
            serializer = TicketSerializer(paiement_stripe.reservation.tickets.all().exclude(status=Ticket.SCANNED),
                                          many=True)
            data["tickets"] = serializer.data
        return Response(
            data,
            status=status.HTTP_226_IM_USED
        )

    if paiement_stripe.reservation:
        if paiement_stripe.reservation.status == Reservation.PAID_ERROR:
            return Response(
                _("Erreur dans l'envoi du mail. Merci de vérifier l'adresse"),
                status=status.HTTP_412_PRECONDITION_FAILED
            )

        if paiement_stripe.status == Paiement_stripe.VALID or paiement_stripe.reservation.status == Reservation.VALID:
            serializer = TicketSerializer(paiement_stripe.reservation.tickets.filter(status=Ticket.NOT_SCANNED),
                                          many=True, context=request)
            # import ipdb; ipdb.set_trace()
            data = {
                "msg": 'Paiement validé. Billets envoyés par mail.',
                "tickets": serializer.data,
            }
            return Response(
                data,
                status=status.HTTP_208_ALREADY_REPORTED
            )

    configuration = Configuration.get_solo()
    stripe.api_key = configuration.get_stripe_api()

    print(f"paiment_stripe_validator : {paiement_stripe.status}")
    if paiement_stripe.status != Paiement_stripe.VALID:

        checkout_session = stripe.checkout.Session.retrieve(paiement_stripe.checkout_session_id_stripe)

        # Vérifie que les metatada soient cohérentes. #NTUI !
        if metatadata_valid(paiement_stripe, checkout_session):
            if checkout_session.payment_status == "unpaid":
                paiement_stripe.status = Paiement_stripe.PENDING
                if datetime.now().timestamp() > checkout_session.expires_at:
                    paiement_stripe.status = Paiement_stripe.EXPIRE
                paiement_stripe.save()
                return Response(
                    _(f'stripe : {checkout_session.payment_status} - paiement : {paiement_stripe.status}'),
                    status=status.HTTP_402_PAYMENT_REQUIRED
                )

            elif checkout_session.payment_status == "paid":

                # le .save() lance le process pre_save BaseBillet.models.send_to_cashless
                # qui modifie le status de chaque ligne
                # et envoie les informations au serveur cashless.
                # si validé par le serveur cashless, alors la ligne sera VALID.
                # Si toute les lignes sont VALID, le paiement_stripe sera aussi VALID
                # grace au post_save BaseBillet.models.check_status_stripe

                paiement_stripe.status = Paiement_stripe.PAID
                paiement_stripe.last_action = timezone.now()
                paiement_stripe.traitement_en_cours = True

                if request.method == 'GET':
                    paiement_stripe.source_traitement = Paiement_stripe.GET
                else:
                    paiement_stripe.source_traitement = Paiement_stripe.WEBHOOK

                paiement_stripe.save()
                logger.info("*" * 30)
                logger.info(
                    f"{datetime.now()} - paiment_stripe_validator - checkout_session.payment_status : {checkout_session.payment_status}")
                logger.info(
                    f"{datetime.now()} - paiment_stripe_validator - paiement_stripe.save() {paiement_stripe.status}")
                logger.info("*" * 30)

            else:
                paiement_stripe.status = Paiement_stripe.CANCELED
                paiement_stripe.save()
        else:
            return Response(_(f'Erreur Meta'), status=status.HTTP_406_NOT_ACCEPTABLE)

    # on vérifie que le status n'ai pas changé
    paiement_stripe.refresh_from_db()
    if paiement_stripe.source == Paiement_stripe.QRCODE:

        # SI le paiement est valide, c'est que les presave et postsave
        # ont validé la réponse du serveur cashless pour les recharges
        if paiement_stripe.status == Paiement_stripe.VALID:
            # on boucle ici pour récuperer l'uuid de la carte.
            for ligne_article in paiement_stripe.lignearticle_set.all():
                if ligne_article.carte:
                    if request.method == 'GET':
                        metadata_stripe_json = paiement_stripe.metadata_stripe
                        metadata_stripe = json.loads(str(metadata_stripe_json))
                        # import ipdb; ipdb.set_trace()
                        for ligne_article in paiement_stripe.lignearticle_set.all():
                            messages.success(request,
                                             f"{ligne_article.pricesold.price.product.name} : {ligne_article.pricesold.price.name}")

                        messages.success(request, f"Paiement validé. Merci !")

                        return HttpResponseRedirect(f"/qr/{ligne_article.carte.uuid}#success")
                    else:
                        return Response(f'VALID', status=status.HTTP_200_OK)


        else:
            # on boucle ici pour récuperer l'uuid de la carte.
            for ligne_article in paiement_stripe.lignearticle_set.all():
                if ligne_article.carte:
                    messages.error(request,
                                   f"Un problème de validation de paiement a été detecté. "
                                   f"Merci de vérifier votre moyen de paiement et/ou contactez un responsable.")
                    return HttpResponseRedirect(f"/qr/{ligne_article.carte.uuid}#erreurpaiement")



    elif paiement_stripe.source == Paiement_stripe.API_BILLETTERIE:
        if paiement_stripe.reservation:
            if paiement_stripe.reservation.status == Reservation.VALID:
                serializer = TicketSerializer(paiement_stripe.reservation.tickets.filter(status=Ticket.NOT_SCANNED),
                                              many=True, context=request)
                # import ipdb; ipdb.set_trace()
                data = {
                    "msg": 'Paiement validé. Billets envoyés par mail.',
                    "tickets": serializer.data,
                }
                return Response(
                    data,
                    status=status.HTTP_208_ALREADY_REPORTED
                )
        if paiement_stripe.status == Paiement_stripe.VALID:
            return Response(
                _('Paiement validé.'),
                status=status.HTTP_208_ALREADY_REPORTED
            )

        elif paiement_stripe.status == Paiement_stripe.PAID:
            logger.info(f"Paiement_stripe.API_BILLETTERIE  : {paiement_stripe.status}")
            data = {
                "msg": 'Paiement validé. Création des billets et envoi par mail en cours.',
            }
            if paiement_stripe.reservation:
                serializer = TicketSerializer(paiement_stripe.reservation.tickets.all().exclude(status=Ticket.SCANNED),
                                              many=True)
                data['tickets'] = serializer.data
            return Response(
                data,
                status=status.HTTP_202_ACCEPTED
            )

    raise Http404(f'{paiement_stripe.status}')


@permission_classes([permissions.AllowAny])
class Webhook_stripe(APIView):
    def post(self, request):
        payload = request.data

        # c'est une requete depuis les webhook
        # configuré dans l'admin stripe
        if payload.get('type') == "checkout.session.completed":
            logger.info(f"Webhook_stripe from stripe : {payload}")
            tenant_uuid_in_metadata = payload["data"]["object"]["metadata"]["tenant"]
            # if connection.tenant.schema_name == "public":
            if f"{connection.tenant.uuid}" != tenant_uuid_in_metadata:
                with tenant_context(Client.objects.get(uuid=tenant_uuid_in_metadata)):
                    paiement_stripe = get_object_or_404(Paiement_stripe,
                                                        checkout_session_id_stripe=payload['data']['object']['id'])

                tenant = Client.objects.get(uuid=tenant_uuid_in_metadata)
                url_redirect = f"https://{tenant.domains.all().first().domain}{request.path}"

                # On lance la requete nous même aussi,
                # de telle sorte que ça soit déja validé
                # lorsque le client arrive sur la page de redirection
                task = redirect_post_webhook_stripe_from_public.delay(url_redirect, request.data)
                return Response(f"redirect to {url_redirect} with celery", status=status.HTTP_200_OK)

            logger.info("*" * 30)
            logger.info(f"{datetime.now()} - {request.get_host()} - Webhook_stripe POST : {payload['type']}")
            logger.info("*" * 30)

            logger.info(f"checkout.session.completed : {payload}")

            paiement_stripe = get_object_or_404(Paiement_stripe,
                                                checkout_session_id_stripe=payload['data']['object']['id'])
            return paiment_stripe_validator(request, paiement_stripe)

        # c'est une requete depuis vue.js.
        post_from_front_vue_js = payload.get('uuid')
        if post_from_front_vue_js:
            logger.info(f"Webhook_stripe from vue.js : {payload}")
            paiement_stripe = get_object_or_404(Paiement_stripe,
                                                uuid=post_from_front_vue_js)
            return paiment_stripe_validator(request, paiement_stripe)


        # Réponse pour l'api stripe qui envoie des webhook pour tout autre que la validation de paiement.
        # Si on renvoie une erreur, ils suppriment le webhook de leur côté.
        return Response('Pouple', status=status.HTTP_202_ACCEPTED)

    def get(self, request, uuid_paiement):
        logger.info("*" * 30)
        logger.info(f"{datetime.now()} - Webhook_stripe GET : {uuid_paiement}")
        logger.info("*" * 30)

        paiement_stripe = get_object_or_404(Paiement_stripe,
                                            uuid=uuid_paiement)
        return paiment_stripe_validator(request, paiement_stripe)
