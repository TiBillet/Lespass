# Create your views here.
import decimal

import csv
import json
import uuid
from decimal import Decimal

from datetime import datetime, timedelta
import dateutil.parser
import pytz
import requests
import stripe
from django.contrib import messages
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core import management

from django.core.validators import URLValidator
from django.http import HttpResponseRedirect, Http404, HttpResponse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView
from django_tenants.utils import schema_context, tenant_context
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
    EventCreateSerializer, TicketSerializer, OptionsSerializer, ChargeCashlessValidator, NewAdhesionValidator, \
    DetailCashlessCardsValidator, DetailCashlessCardsSerializer, CashlessCardsValidator, \
    UpdateFederatedAssetFromCashlessValidator
from AuthBillet.models import TenantAdminPermission, TibilletUser, RootPermission, TenantAdminPermissionWithRequest
from AuthBillet.utils import user_apikey_valid, get_or_create_user
from BaseBillet.tasks import create_ticket_pdf, report_to_pdf, report_celery_mailer
from Customers.models import Client, Domain
from BaseBillet.models import Event, Price, Product, Reservation, Configuration, Ticket, Paiement_stripe, \
    OptionGenerale, Membership
from rest_framework import viewsets, permissions, status
from django.db import connection, IntegrityError
from TiBillet import settings

import os

from MetaBillet.models import EventDirectory, ProductDirectory
from PaiementStripe.views import new_entry_from_stripe_invoice
from QrcodeCashless.models import Detail, CarteCashless, Wallet, Asset, SyncFederatedLog
from QrcodeCashless.views import WalletValidator
from root_billet.models import RootConfiguration

import logging
logger = logging.getLogger(__name__)

class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, decimal.Decimal):
            return str(o)
        return super(DecimalEncoder, self).default(o)


# Refactor for get_permission
# Si c'est list/retrieve -> pour tout le monde
# Sinon, on vérifie la clé api
def get_permission_Api_LR_Any(self):
    # Si c'est une auth avec APIKEY,
    # on vérifie avec notre propre moteur
    # Si l'user est rendu, la clé est valide
    user_api = user_apikey_valid(self)
    if user_api:
        permission_classes = []
        self.request.user = user_api

    elif self.action in ['list', 'retrieve']:
        permission_classes = [permissions.AllowAny]
    else:
        permission_classes = [TenantAdminPermission]

    return [permission() for permission in permission_classes]


def get_permission_Api_LR_Admin(self):
    user_api = user_apikey_valid(self)
    if user_api:
        permission_classes = []
        self.request.user = user_api

    elif self.action in ['list', 'retrieve']:
        permission_classes = [TenantAdminPermission]
    else:
        permission_classes = [permissions.AllowAny]
    return [permission() for permission in permission_classes]


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
        return get_permission_Api_LR_Any(self)


class ProductViewSet(viewsets.ViewSet):

    def list(self, request):
        serializer = ProductSerializer(
            Product.objects.all(),
            many=True, context={'request': request})
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
        return get_permission_Api_LR_Any(self)


class TenantViewSet(viewsets.ViewSet):

    def create(self, request):
        # Le slug est-il disponible ?
        try:
            slug = slugify(request.data.get('organisation'))
            Client.objects.get(schema_name=slug)
            logger.warning(f"{slug} exist : Conflict")
            return Response(
                {f"{slug} existe déja : Conflit de nom"},
                status=status.HTTP_409_CONFLICT)
        except Client.DoesNotExist:
            pass

        # L'url correspond bien à la catégorie choisie ?
        if not request.data.get('categorie'):
            raise serializers.ValidationError(_("categorie est obligatoire"))
        categories = []
        if 'place' in request.get_full_path():
            categories = [Client.SALLE_SPECTACLE, Client.FESTIVAL]
        if 'artist' in request.get_full_path():
            categories = [Client.ARTISTE]

        if request.data.get('categorie') not in categories:
            raise serializers.ValidationError(_("categorie ne correspond pas à l'url"))


        serializer = NewConfigSerializer(data=request.data, context={'request': request})

        # import ipdb; ipdb.set_trace()

        if serializer.is_valid():

            futur_conf = serializer.validated_data
            slug = slugify(futur_conf.get('organisation'))
            with schema_context('public'):
                try:
                    tenant, created = Client.objects.get_or_create(
                        schema_name=slug,
                        name=futur_conf.get('organisation'),
                        categorie=request.data.get('categorie'),
                    )

                    if not created:
                        logger.error(f"{futur_conf.get('organisation')} existe déja")
                        return Response(_(json.dumps(
                            {"uuid": f"{tenant.uuid}", "msg": f"{futur_conf.get('organisation')} existe déja"})),
                            status=status.HTTP_409_CONFLICT)

                    domain, created = Domain.objects.get_or_create(
                        domain=f"{slug}.{os.getenv('DOMAIN')}",
                        tenant=tenant,
                        is_primary=True
                    )

                    # Ajoute des cartes de test DEMO
                    if settings.DEBUG and slug == "demo":
                        management.call_command("load_cards", "--demo")

                except IntegrityError as e:
                    logger.error(e)
                    return Response(_(f"{e}"), status=status.HTTP_400_BAD_REQUEST)
                except Exception as e:
                    logger.error(e)
                    return Response(_(f"{e}"), status=status.HTTP_405_METHOD_NOT_ALLOWED)

            with tenant_context(tenant):
                rootConf = RootConfiguration.get_solo()
                conf = Configuration.get_solo()
                info_stripe = serializer.info_stripe

                serializer.update(instance=conf, validated_data=futur_conf)

                conf.slug = slug

                conf.email = info_stripe.email
                conf.site_web = info_stripe.business_profile.url
                conf.phone = info_stripe.business_profile.support_phone

                conf.stripe_mode_test = rootConf.stripe_mode_test

                if rootConf.stripe_mode_test:
                    conf.stripe_connect_account_test = info_stripe.id
                else:
                    conf.stripe_connect_account = info_stripe.id

                if getattr(serializer, 'img_img', None):
                    conf.img.save(serializer.img_name, serializer.img_img.fp)
                if getattr(serializer, 'logo_img', None):
                    conf.logo.save(serializer.logo_name, serializer.logo_img.fp)

                conf.save()
                conf.check_serveur_cashless()
                # user.client_admin.add(tenant)


                staff_group = Group.objects.get(name="staff")

                user_from_email_nouveau_tenant = get_or_create_user(conf.email, force_mail=True)
                user_from_email_nouveau_tenant.client_admin.add(tenant)
                user_from_email_nouveau_tenant.is_staff = True
                user_from_email_nouveau_tenant.groups.add(staff_group)
                user_from_email_nouveau_tenant.save()

                place_serialized = ConfigurationSerializer(Configuration.get_solo(), context={'request': request})
                place_serialized_with_uuid = {'uuid': f"{tenant.uuid}"}
                place_serialized_with_uuid.update(place_serialized.data)

            return Response(place_serialized_with_uuid, status=status.HTTP_201_CREATED)

        logger.error(f"serializer.errors : {serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # def update(self, request, pk=None):
    #     tenant = get_object_or_404(Client, pk=pk)
    #     user: TibilletUser = request.user
    #     if tenant not in user.client_admin.all():
    #         return Response(_(f"Not Allowed"), status=status.HTTP_405_METHOD_NOT_ALLOWED)
    #     with tenant_context(tenant):
    #         conf = Configuration.get_solo()
    #         serializer = NewConfigSerializer(conf, data=request.data, partial=True)
    #         if serializer.is_valid():
    #             # serializer.save()
    #             serializer.update(conf, serializer.validated_data)
    #             return Response(serializer.data, status=status.HTTP_201_CREATED)
    #
    #     return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

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
        if self.action =='create':
            permission_classes = [permissions.AllowAny]
            return [permission() for permission in permission_classes]
        else :
            return get_permission_Api_LR_Any(self)
        # permission_classes = [permissions.AllowAny]


class HereViewSet(viewsets.ViewSet):

    def list(self, request):
        config = Configuration.get_solo()
        place_serialized = ConfigurationSerializer(config, context={'request': request})

        dict_return = {'uuid': f"{connection.tenant.uuid}"}
        dict_return.update(place_serialized.data)

        products_adhesion = Product.objects.filter(
            categorie_article=Product.ADHESION,
            prices__isnull=False
        ).distinct()

        if len(products_adhesion) > 0:
            products_serializer = ProductSerializer(products_adhesion, many=True)
            dict_return['membership_products'] = products_serializer.data

        return Response(dict_return)

    def get_permissions(self):
        return get_permission_Api_LR_Any(self)


class EventsSlugViewSet(viewsets.ViewSet):
    def retrieve(self, request, pk=None):
        queryset = Event.objects.all().order_by('-datetime')
        event = get_object_or_404(queryset, slug=pk)
        serializer = EventSerializer(event)
        return Response(serializer.data)

    def get_permissions(self):
        return get_permission_Api_LR_Any(self)


class EventsViewSet(viewsets.ViewSet):

    def list(self, request):
        tenant: Client = connection.tenant
        four_hour_before_now = datetime.now().date() - timedelta(hours=4)

        production_places = [Client.SALLE_SPECTACLE, Client.FESTIVAL]
        if tenant.categorie in production_places:
            queryset = Event.objects.filter(datetime__gte=four_hour_before_now).order_by('datetime')
            events_serialized = EventSerializer(queryset, many=True, context={'request': request})
            return Response(events_serialized.data)

        elif tenant.categorie == Client.ARTISTE:
            artist = tenant
            directory = {}
            events_serialized_data = []
            with schema_context('public'):
                events_from_public_directory = EventDirectory.objects.filter(
                    datetime__gte=four_hour_before_now,
                    artist=artist
                )
                for event in events_from_public_directory:
                    if directory.get(event.place):
                        directory[event.place].append(event.event_uuid)
                    else:
                        directory[event.place] = []
                        directory[event.place].append(event.event_uuid)

            for place in directory:
                with tenant_context(place):
                    queryset = Event.objects.filter(uuid__in=directory[place])
                    events_serialized = EventSerializer(queryset, many=True, context={'request': request})
                    for data in events_serialized.data:
                        events_serialized_data.append(data)

            return Response(events_serialized_data)

        elif tenant.categorie == Client.META:
            events_serialized_data = []
            tenants = Client.objects.filter(categorie=Client.SALLE_SPECTACLE)
            for other_tenant in tenants:
                with tenant_context(other_tenant):
                    queryset = Event.objects.filter(datetime__gte=four_hour_before_now).order_by('datetime')
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
        serializer_create = EventCreateSerializer(data=request.data)
        if serializer_create.is_valid():
            # import ipdb; ipdb.set_trace()
            event: Event = serializer_create.validated_data
            serializer = EventSerializer(event)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        logger.error(f"EventsViewSet : {serializer_create.errors}")
        return Response(serializer_create.errors, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, pk=None):
        queryset = Event.objects.all().order_by('-datetime')
        event = get_object_or_404(queryset, pk=pk)
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
        return get_permission_Api_LR_Any(self)


class DetailCashlessCards(viewsets.ViewSet):
    def create(self, request):
        validator = DetailCashlessCardsValidator(data=request.data, context={'request': request})
        if validator.is_valid():
            with schema_context('public'):
                logger.info('Detail valide')
                detailC = validator.save()
                serializer = DetailCashlessCardsSerializer(detailC)
                return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(validator.errors, status=status.HTTP_400_BAD_REQUEST)

    def get_permissions(self):
        permission_classes = [RootPermission]
        return [permission() for permission in permission_classes]


class Loadcardsfromdict(viewsets.ViewSet):
    def create(self, request):
        # logger.info(request.data)

        validator = CashlessCardsValidator(data=request.data, many=True)
        if validator.is_valid():
            prems = validator.data[0]
            detail = Detail.objects.get(uuid=prems.get('detail'))
            for carte in validator.data:
                part = carte.get('url').partition('/qr/')
                base_url = f"{part[0]}{part[1]}"
                uuid_qrcode = uuid.UUID(part[2], version=4)
                if detail.uuid == uuid.UUID(carte.get('detail'), version=4) and base_url == detail.base_url:
                    try:
                        carte, created = CarteCashless.objects.get_or_create(
                            tag_id=carte['tag_id'],
                            uuid=uuid_qrcode,
                            number=carte['number'],
                            detail=detail,
                        )
                        logger.info(f"{created}: {carte}")

                    except Exception as e:
                        logger.error(e)
                        Response(_(f"Erreur d'importation {e}"),
                                 status=status.HTTP_406_NOT_ACCEPTABLE)
                else:
                    Response(_(f"Erreur d'importation : Detail ne correspond pas"),
                             status=status.HTTP_406_NOT_ACCEPTABLE)

            return Response("poulpe", status=status.HTTP_200_OK)

        return Response(validator.errors, status=status.HTTP_400_BAD_REQUEST)

    def get_permissions(self):
        permission_classes = [RootPermission]
        return [permission() for permission in permission_classes]


class ChargeCashless(viewsets.ViewSet):
    def create(self, request):
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

    def retrieve(self, request, pk=None):
        queryset = Reservation.objects.all().order_by('-datetime')
        resa = get_object_or_404(queryset, pk=pk)
        serializer = ReservationSerializer(resa)
        return Response(serializer.data)

    def create(self, request):
        # import ipdb; ipdb.set_trace()
        logger.info(f"ReservationViewset CREATE : {request.data}")

        validator = ReservationValidator(data=request.data, context={'request': request})
        if validator.is_valid():
            return Response(validator.data, status=status.HTTP_201_CREATED)

        logger.error(f"ReservationViewset CREATE ERROR : {validator.errors}")
        return Response(validator.errors, status=status.HTTP_400_BAD_REQUEST)

    def get_permissions(self):
        return get_permission_Api_LR_Admin(self)


class OptionTicket(viewsets.ViewSet):
    def list(self, request):
        queryset = OptionGenerale.objects.all()
        serializer = OptionsSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)

    def create(self, request):
        validator = OptionsSerializer(data=request.data, context={'request': request})
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


'''
@permission_classes([permissions.IsAuthenticated])
class LoadCardsFromCsv(APIView):

    def is_string_an_url(self, url_string):
        validate_url = URLValidator()

        try:
            validate_url(url_string)
        except ValidationError as e:
            return False
        return True

    def post(self, request):
        try :
            gen = request.data['generation']
            content_csv_file = request.data['csv'].read().decode()
            file = StringIO(content_csv_file)
            csv_data = csv.reader(file, delimiter=",")
        except:
            return Response('Mauvais fichiers', status=status.HTTP_406_NOT_ACCEPTABLE)

        list_csv = []
        for line in csv_data:
            list_csv.append(line)

        # on saucissonne l'url d'une ligne au pif :
        part = list_csv[1][0].partition('/qr/')
        base_url = f"{part[0]}{part[1]}"

        if self.is_string_an_url(base_url) and uuid.UUID(part[2]) :
            detail_carte, created = Detail.objects.get_or_create(
                base_url=base_url,
                origine=connection.tenant,
                generation=int(gen),
            )

            numline = 1
            for line in list_csv:
                print(numline)
                part = line[0].partition('/qr/')
                try:
                    uuid_url = uuid.UUID(part[2])
                    print(f"base_url : {base_url}")
                    print(f"uuid_url : {uuid_url}")
                    print(f"number : {line[1]}")
                    print(f"tag_id : {line[2]}")

                    # if str(uuid_url).partition('-')[0].upper() != line[1]:
                    #     print('ERROR PRINT != uuid')
                    #     break

                    carte, created = CarteCashless.objects.get_or_create(
                        tag_id=line[2],
                        uuid=uuid_url,
                        number=line[1],
                        detail=detail_carte,
                    )

                    numline += 1
                except:
                    pass

            return Response('Cartes chargées', status=status.HTTP_200_OK)

        return Response('Mauvais formatage de fichier.', status=status.HTTP_406_NOT_ACCEPTABLE)
        # import ipdb; ipdb.set_trace()
'''


@permission_classes([permissions.IsAuthenticated])
class Cancel_sub(APIView):
    def post(self, request):
        user = request.user
        price = request.data.get('uuid_price')

        membership = Membership.objects.get(
            user=user,
            price=price
        )

        if membership.status == Membership.AUTO:
            stripe.api_key = Configuration.get_solo().get_stripe_api()
            stripe.Subscription.delete(
                membership.stripe_id_subscription,
                # stripe_account=config.get_stripe_connect_account(),
            )
            membership.status = Membership.CANCELED
            membership.save()

            # TODO: envoyer un mail de confirmation d'annulation
            return Response('Renouvellement automatique supprimé.', status=status.HTTP_200_OK)

        return Response('Pas de renouvellement automatique sur cette adhésion.', status=status.HTTP_406_NOT_ACCEPTABLE)


@permission_classes([TenantAdminPermission])
class Gauge(APIView):

    # API pour avoir l'état de la jauge (GAUGE in inglishe) et des billets scannés.
    def get(self, request):
        config = Configuration.get_solo()
        debut_jour, lendemain_quatre_heure = borne_temps_4h()
        queryset = Ticket.objects.filter(
            reservation__event__datetime__gte=debut_jour,
            reservation__event__datetime__lte=lendemain_quatre_heure,
            status__in=[Ticket.NOT_SCANNED, Ticket.SCANNED]
        )

        data = {
            "gauge_max": config.jauge_max,
            "all_tickets": queryset.count(),
            "scanned_tickets": queryset.filter(status=Ticket.SCANNED).count()
        }

        return Response(data, status=status.HTTP_200_OK)


class TicketViewset(viewsets.ViewSet):
    def list(self, request):
        debut_jour, lendemain_quatre_heure = borne_temps_4h()

        queryset = Ticket.objects.filter(
            reservation__event__datetime__gte=debut_jour,
            reservation__event__datetime__lte=lendemain_quatre_heure,
            status__in=["K", "S"]
        )

        serializer = TicketSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        queryset = Ticket.objects.all()
        ticket = get_object_or_404(queryset, pk=pk)
        serializer = TicketSerializer(ticket)
        return Response(serializer.data)

    def get_permissions(self):
        return get_permission_Api_LR_Admin(self)


def maj_membership_from_cashless(user: TibilletUser, data: dict):
    '''
    On met à jour la carte de membre si le cashless à des données plus récentes.

    '''
    logger.info('maj_membership_from_cashless')
    try:
        # Il n'y est sensé y avoir qu'un seul objet produit qui puisse être envoyé au cashless
        produit_adhesion = Product.objects.get(send_to_cashless=True)

        # On va chercher la carte membership
        deadline_billetterie = None
        membership = Membership.objects.filter(
            user=user,
            price__product=produit_adhesion
        ).first()

        if membership:
            deadline_billetterie = membership.deadline()
        else:
            prices_adhesion = produit_adhesion.prices.all()
            price: Price = prices_adhesion.get(prix=float(data.get('cotisation')))
            logger.info(f'Pas de membreship, on la crée avec la data du cashless :')
            logger.info(f'{data}')
            membership = Membership.objects.create(
                user=user,
                first_name=data.get('prenom'),
                last_name=data.get('name'),
                newsletter=bool(data.get('demarchage')),
                price=price
            )

        date_inscription = data.get('date_inscription')
        if date_inscription:
            deadline_cashless = datetime.strptime(data.get('prochaine_echeance'), '%Y-%m-%d').date()
            if deadline_billetterie:
                if deadline_billetterie >= deadline_cashless:
                    logger.info('Adhésion associative syncho avec le cashless.')
                    return membership

            logger.info(f'Adhésion associative {produit_adhesion} non syncho avec le cashless. On mets à jour.')

            membership.date_added = dateutil.parser.parse(data.get('date_ajout'))
            membership.first_contribution = datetime.strptime(data.get('date_inscription'), '%Y-%m-%d').date()
            membership.last_contribution = datetime.strptime(data.get('date_derniere_cotisation'), '%Y-%m-%d').date()
            membership.contribution_value = float(data.get('cotisation'))
            membership.save()

            return membership

    except Exception as e:
        logger.error(f'maj_membership_from_cashless ERROR : {e}')
        return None


def request_for_data_cashless(user: TibilletUser):
    if user.email_error or not user.email:
        return {'erreur': f"user.email_error {user.email_error}"}

    configuration = Configuration.get_solo()
    if configuration.server_cashless and configuration.key_cashless:
        try:
            verify = True
            if settings.DEBUG:
                verify = False

            response = requests.request("POST",
                                        f"{configuration.server_cashless}/api/membre_check",
                                        headers={"Authorization": f"Api-Key {configuration.key_cashless}"},
                                        data={"email": user.email},
                                        verify=verify)

            if response.status_code != 200:
                return {'erreur': f"{response.status_code} : {response.text}"}

            data = json.loads(response.content)
            if data.get('a_jour_cotisation'):
                membership = maj_membership_from_cashless(user, data)
            return data

        except Exception as e:
            return {'erreur': f"{e}"}

    return {'erreur': f"pas de configuration server_cashless"}


class MembershipViewset(viewsets.ViewSet):

    def create(self, request):
        logger.info(f"MembershipViewset reçue -> go MembreValidator")

        # Test pour option :
        # request.data['options'] = ['1ff89201-edfa-4839-80d8-a5f98737f970',]

        #TODO: Pourquoi deux serializers ?
        membre_validator = MembreValidator(data=request.data, context={'request': request})
        if membre_validator.is_valid():
            adhesion_validator = NewAdhesionValidator(data=request.data, context={'request': request})
            if adhesion_validator.is_valid():
                return Response(adhesion_validator.data, status=status.HTTP_201_CREATED)

            logger.error(f'adhesion_validator.errors : {adhesion_validator.errors}')
            return Response(adhesion_validator.errors, status=status.HTTP_400_BAD_REQUEST)

        logger.error(f'membre_validator.errors : {membre_validator.errors}')
        return Response(membre_validator.errors, status=status.HTTP_400_BAD_REQUEST)

    # TODO: gerer en interne, pas avec le cashless
    # def retrieve(self, request, pk=None):
    #     try:
    #         email = force_str(urlsafe_base64_decode(pk))
    #     except:
    #         return Response("base64 email only", status=status.HTTP_406_NOT_ACCEPTABLE)
    #     User = get_user_model()
    #     user = User.objects.filter(email=email, username=email).first()
    #
    #     if user:
    #         configuration = Configuration.get_solo()
    #         if configuration.server_cashless and configuration.key_cashless:
    #             data = request_for_data_cashless(user)
    #             data_retrieve = {
    #                 'a_jour_cotisation': data.get('a_jour_cotisation'),
    #                 'date_derniere_cotisation': data.get('date_derniere_cotisation'),
    #                 'prochaine_echeance': data.get('prochaine_echeance')
    #             }
    #             return Response(data_retrieve, status=status.HTTP_200_OK)
    #
    #         return Response('no cashless server', status=status.HTTP_404_NOT_FOUND)
    #     return Response('no User', status=status.HTTP_402_PAYMENT_REQUIRED)

    def get_permissions(self):
        if self.action in ['create', 'retrieve']:
            permission_classes = [permissions.AllowAny]
        else:
            permission_classes = [TenantAdminPermission]

        return [permission() for permission in permission_classes]


# class BookListView(ListView):
#     model = Book
#
#     def head(self, *args, **kwargs):
#         last_book = self.get_queryset().latest('publication_date')
#         response = HttpResponse(
#             # RFC 1123 date format.
#             headers={'Last-Modified': last_book.publication_date.strftime('%a, %d %b %Y %H:%M:%S GMT')},
#         )
#         return response

class ZReportPDF(View):
    def get(self, request, pk_uuid):
        logger.info(f"ZReportPDF user : {request.user}")
        if not TenantAdminPermissionWithRequest(request):
            return HttpResponse(f"403", content_type='application/json')

        configuration = Configuration.get_solo()
        if configuration.server_cashless and configuration.key_cashless:
            try:
                response = requests.request("GET",
                                            f"{configuration.server_cashless}/rapport/TicketZapi/{pk_uuid}",
                                            headers={"Authorization": f"Api-Key {configuration.key_cashless}"},
                                            verify=bool(not settings.DEBUG), )

                if response.status_code == 200:
                    data = json.loads(response.content)
                    date = data['date']
                    structure = data['structure']
                    # import ipdb; ipdb.set_trace()

                    logger.info(f"ZReportPDF data : {data}")
                    logger.info(f"  On envoie le mail")
                    report_celery_mailer.delay([data, ])

                    pdf_binary = report_to_pdf(data)
                    response = HttpResponse(pdf_binary, content_type='application/pdf')
                    response['Content-Disposition'] = f'attachment; filename="{structure}-{date}.pdf"'
                    return response

                    # return HttpResponse(json.dumps(data), content_type='application/json')
                    # return Response(data, status=status.HTTP_200_OK)

            except Exception as e:
                logger.info(f"ZReportPDF erreur {e}")
                raise e

            logger.info(f"ZReportPDF erreur {response.status_code} : {response.text}")
            return HttpResponse(f"{response.status_code}", content_type='application/json')

        # return {'erreur': f"pas de configuration server_cashless"}


class TicketPdf(APIView):
    permission_classes = [AllowAny]

    def get(self, request, pk_uuid):
        ticket = get_object_or_404(Ticket, uuid=pk_uuid)

        VALID_TICKET_FOR_PDF = [Ticket.NOT_SCANNED, Ticket.SCANNED]
        if ticket.status not in VALID_TICKET_FOR_PDF:
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

        # Si ce n'est pas une adhésion par QRCode,
        # on renvoie vers le front en annonçant que le travail est en cours
        if paiement_stripe.source != Paiement_stripe.QRCODE:
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

            data = {
                "msg": 'Paiement validé. Billets envoyés par mail.',
                "tickets": serializer.data,
            }

            return Response(
                data,
                status=status.HTTP_208_ALREADY_REPORTED
            )

    # configuration = Configuration.get_solo()
    # stripe.api_key = RootConfiguration.get_solo().get_stripe_api()
    stripe.api_key = Configuration.get_solo().get_stripe_api()

    # SI c'est une source depuis INVOICE,
    # L'object vient d'être créé, on vérifie que la facture stripe
    # est payée et on met en VALID.
    if paiement_stripe.source == Paiement_stripe.INVOICE:
        paiement_stripe.traitement_en_cours = True
        invoice = stripe.Invoice.retrieve(paiement_stripe.invoice_stripe)

        if invoice.status == 'paid':
            paiement_stripe.status = Paiement_stripe.PAID
            paiement_stripe.last_action = timezone.now()
            paiement_stripe.traitement_en_cours = True
            paiement_stripe.save()

            return Response(
                'invoice ok',
                status=status.HTTP_202_ACCEPTED
            )

        else:
            return Response(
                _(f'stripe invoice : {invoice.status} - paiement : {paiement_stripe.status}'),
                status=status.HTTP_402_PAYMENT_REQUIRED
            )

    # Sinon c'est un paiement stripe checkout
    elif paiement_stripe.status != Paiement_stripe.VALID:
        config = Configuration.get_solo()
        checkout_session = stripe.checkout.Session.retrieve(
            paiement_stripe.checkout_session_id_stripe,
            # stripe_account=config.get_stripe_connect_account()
        )

        paiement_stripe.customer_stripe = checkout_session.customer

        # Vérifie que les metatada soient cohérentes. #NTUI !
        if metatadata_valid(paiement_stripe, checkout_session):
            if checkout_session.payment_status == "unpaid":
                paiement_stripe.status = Paiement_stripe.PENDING
                if datetime.now().timestamp() > checkout_session.expires_at:
                    paiement_stripe.status = Paiement_stripe.EXPIRE

                paiement_stripe.save()

                if paiement_stripe.source != Paiement_stripe.QRCODE:
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

                # Dans le cas d'un nouvel abonnement
                # On va chercher le numéro de l'abonnement stripe
                # Et sa facture
                if checkout_session.mode == 'subscription':
                    if bool(checkout_session.subscription):
                        paiement_stripe.subscription = checkout_session.subscription
                        subscription = stripe.Subscription.retrieve(
                            checkout_session.subscription,
                            # stripe_account=config.get_stripe_connect_account()
                        )
                        paiement_stripe.invoice_stripe = subscription.latest_invoice

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

    # on vérifie le changement de status
    paiement_stripe.refresh_from_db()

    # Paiement depuis QRCode carte
    # on envoie au serveur cashless
    if paiement_stripe.source == Paiement_stripe.QRCODE:
        # Si le paiement est valide, c'est que les presave et postsave
        # ont validé la réponse du serveur cashless pour les recharges
        if paiement_stripe.status == Paiement_stripe.VALID:
            lignes_articles = paiement_stripe.lignearticle_set.all()
            # on boucle ici pour récuperer l'uuid de la carte.
            for ligne_article in lignes_articles:
                carte = ligne_article.carte
                if carte:
                    if request.method == 'GET':
                        # On re-boucle pour récuperer les noms des articles vendus afin de les afficher sur le front
                        for ligneArticle in lignes_articles:
                            messages.success(request,
                                             f"{ligneArticle.pricesold.price.product.name} : {ligneArticle.pricesold.price.name}")

                        messages.success(request, f"Paiement validé. Merci !")

                        return HttpResponseRedirect(f"/qr/{carte.uuid}#success")
                    else:
                        return Response(f'VALID', status=status.HTTP_200_OK)

        elif paiement_stripe.status == Paiement_stripe.PAID:
            for ligne_article in paiement_stripe.lignearticle_set.all():
                if ligne_article.carte:
                    messages.error(request,
                                   f"Le paiement à bien été validé "
                                   f"mais un problème est apparu avec votre carte cashless. "
                                   f"Merci de contacter un responsable.")
                    return HttpResponseRedirect(f"/qr/{ligne_article.carte.uuid}#erreurpaiement")

        else:
            # on boucle ici pour récuperer l'uuid de la carte.
            for ligne_article in paiement_stripe.lignearticle_set.all():
                if ligne_article.carte:
                    messages.error(request,
                                   f"Un problème de validation de paiement a été detecté. "
                                   f"Merci de vérifier votre moyen de paiement et/ou contactez un responsable.")
                    return HttpResponseRedirect(f"/qr/{ligne_article.carte.uuid}#erreurpaiement")



    # Derniere action : on crée et envoie les billets si besoin
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


# Si on a l'uuid, on considère qu'on a la carte.
# A réfléchir sur la suite en terme de vie privée ; AllowAny ?
@permission_classes([permissions.AllowAny])
class GetFederatedAssetFromCashless(APIView):
    def get(self, request, pk_uuid):

        # on informe de la quantité de l'asset fédéré sur la carte.
        card = get_object_or_404(CarteCashless, uuid=pk_uuid)
        data = {"stripe_wallet" : 0}
        try:
            wallet_stripe = card.wallet_set.get(asset__categorie=Asset.STRIPE_FED)
            data['stripe_wallet'] = wallet_stripe.qty
            return Response(data, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"GetFederatedAssetFromCashless : {e}")
            return Response(data, status=status.HTTP_404_NOT_FOUND)



@permission_classes([permissions.AllowAny])
class UpdateFederatedAssetFromCashless(APIView):
    def post(self, request):
        """
        Reception d'une demande d'update d'un portefeuille fédéré d'une carte cashless depuis un serveur cashless.
        On vérifie vers le serveur cashless ou vient la requete que la valeur est bonne (NTUI!)
        Ce qui nous permet de mettre ce point d'API en allowAny, de toute façon, on va vérifier !

        On met à jour la valeur en base de donnée sur la billetterie.
        Ensuite, on met à jour dans tous les serveurs cashless fédéré
        """

        validator = UpdateFederatedAssetFromCashlessValidator(data=request.data)
        if not validator.is_valid():
            logger.error(
                f"UpdateFederatedAssetFromCashless ERREUR validator.errors : {validator.errors} : request.data {request.data}")
            return Response(validator.errors, status=status.HTTP_400_BAD_REQUEST)

        validated_data = validator.data
        wallet_stripe: Wallet = validated_data['wallet_stripe']
        carte: CarteCashless = validated_data['card']

        old_qty = validated_data['old_qty']
        new_qty = validated_data['new_qty']
        domain = validated_data['domain']
        uuid_log = validated_data['uuid_commande']

        # On log l'action
        logger.info(f"UpdateFederatedAssetFromCashless validated_data : {validated_data}")
        syncLog: SyncFederatedLog = validated_data['syncLog']

        # Une nouvelle vente a été faites sur un cashless avec la monnaie fédérée.
        # On va vérifier coté cashless si la valeur reçue est bonne (NTUI!)
        if wallet_stripe.qty == old_qty and wallet_stripe.qty != new_qty:
            logger.info(f"UpdateFederatedAssetFromCashless NEED MAJ : {carte} - {wallet_stripe.qty} == {old_qty}")

            # On utilise la class qui va vérifier si tout existe et qui récupère les assets dans le serveur cashless
            validated_wallet = WalletValidator(uuid=carte.uuid)
            dict_carte_from_cashless = validated_wallet.carte_serveur_cashless

            new_qty_verified = None
            for asset in dict_carte_from_cashless.get('assets'):
                if asset['categorie_mp'] == 'SF':
                    new_qty_verified = Decimal(asset['qty'])

            # La valeur reçue par l'api allowAny correspond
            # à la valeur du serveur cashless
            # vérifié grâce à une API avec clé d'authentification
            if new_qty_verified == new_qty:

                wallet_stripe.qty = new_qty
                wallet_stripe.save()
                # TODO: logger
                logger.info(
                    f"UpdateFederatedAssetFromCashless MAJ : {carte} - {wallet_stripe.qty} == {new_qty} - {domain}")
                return Response(f"log {syncLog.uuid}", status=status.HTTP_202_ACCEPTED)

            # La valeur reçue est différente de celle du serveur cashless
            # NTUI ???
            else:
                logger.error(f"UpdateFederatedAssetFromCashless ERREUR : {carte} - {new_qty_verified} != {new_qty}")
                return Response(
                    f"UpdateFederatedAssetFromCashless ERROR new_qty_verified : {carte} - wallet {wallet_stripe.qty}, old {old_qty}, new {new_qty}, new_verified {new_qty_verified}",
                    status=status.HTTP_406_NOT_ACCEPTABLE)


        # Pas besoin de mise à jour.
        elif wallet_stripe.qty == new_qty:
            logger.info(f"UpdateFederatedAssetFromCashless NO MAJ : {carte} - {wallet_stripe.qty} == {new_qty}")
            tenant_uuid = str(connection.tenant.uuid)
            syncLog.etat_client_sync[tenant_uuid]['return'] = True
            syncLog.etat_client_sync[tenant_uuid]['return_value'] = f"{new_qty}"
            syncLog.save()
            return Response(f"NO NEED TO UPDATE - log {syncLog.uuid} already reported",
                            status=status.HTTP_208_ALREADY_REPORTED)


        # La valeur old est différente de celle du serveur cashless
        erreur = f"UpdateFederatedAssetFromCashless ERROR : " \
                 f"log {syncLog.uuid} - carte {carte} - " \
                 f"billetterie wallet {wallet_stripe.qty} != cashless old {old_qty} ou new {new_qty}"
        syncLog.etat_client_sync = erreur
        syncLog.save()

        logger.error(erreur)

        return Response(erreur, status=status.HTTP_409_CONFLICT)


def info_connected_account_stripe(id_acc_connect):
    stripe.api_key = RootConfiguration.get_solo().get_stripe_api()
    info_stripe = stripe.Account.retrieve(id_acc_connect)
    return info_stripe


def create_account_link_for_onboard(id_acc_connect=False):
    rootConf = RootConfiguration.get_solo()
    stripe.api_key = rootConf.get_stripe_api()

    meta = Client.objects.filter(categorie=Client.META)[0]
    meta_url = meta.get_primary_domain().domain

    if not id_acc_connect:
        acc_connect = stripe.Account.create(
            type="standard",
            country="FR",
        )
        id_acc_connect = acc_connect.get('id')

    account_link = stripe.AccountLink.create(
        account=id_acc_connect,
        refresh_url=f"https://{meta_url}/api/onboard_stripe_return/{id_acc_connect}",
        return_url=f"https://{meta_url}/api/onboard_stripe_return/{id_acc_connect}",
        type="account_onboarding",
    )

    url_onboard = account_link.get('url')
    return url_onboard


@permission_classes([permissions.AllowAny])
class Onboard_stripe_return(APIView):
    def get(self, request, id_acc_connect):
        details_submitted = info_connected_account_stripe(id_acc_connect).details_submitted
        if details_submitted:
            logger.info(f"details_submitted : {details_submitted}")
            return HttpResponseRedirect(f"/onboardreturn/{id_acc_connect}/")
        else:
            return Response(f"{create_account_link_for_onboard()}", status=status.HTTP_206_PARTIAL_CONTENT)


@permission_classes([permissions.AllowAny])
class Onboard(APIView):
    def get(self, request):
        return Response(f"{create_account_link_for_onboard()}", status=status.HTTP_202_ACCEPTED)


@permission_classes([permissions.AllowAny])
class Webhook_stripe(APIView):

    def post(self, request):
        payload = request.data
        logger.info(f" ")
        # logger.info(f"Webhook_stripe --> {payload}")
        logger.info(f"Webhook_stripe --> {payload.get('type')}")
        logger.info(f" ")

        # c'est une requete depuis les webhook
        # configuré dans l'admin stripe
        if payload.get('type') == "checkout.session.completed":
            logger.info(f"Webhook_stripe checkout.session.completed : {payload}")

            tenant_uuid_in_metadata = payload["data"]["object"]["metadata"].get("tenant")
            if not tenant_uuid_in_metadata:
                logger.warning(f"Webhook_stripe checkout.session.completed : {payload} - no tenant in metadata")
                return Response('no tenant in metadata',
                                status=status.HTTP_204_NO_CONTENT)

            # On utilise les metadata du paiement stripe pour savoir de quel tenant cela vient.
            if f"{connection.tenant.uuid}" != tenant_uuid_in_metadata:
                tenant = get_object_or_404(Client, uuid=tenant_uuid_in_metadata)
                with tenant_context(tenant):
                    paiement_stripe = get_object_or_404(Paiement_stripe,
                                                        checkout_session_id_stripe=payload['data']['object']['id'])
                    return paiment_stripe_validator(request, paiement_stripe)

            paiement_stripe = get_object_or_404(
                Paiement_stripe,
                checkout_session_id_stripe=payload['data']['object']['id']
            )
            return paiment_stripe_validator(request, paiement_stripe)


        # Prélèvement automatique d'un abonnement :
        # elif payload.get('type') == "customer.subscription.updated":
        #     # on récupère le don dans le paiement récurent si besoin
        #     logger.info(f"Webhook_stripe customer.subscription.updated : {payload['data']['object']['id']}")
        #     logger.info(f"")
        #     logger.info(f"")
        #     logger.info(f"{payload}")
        #     logger.info(f"")
        #     logger.info(f"")

        elif payload.get('type') == "invoice.paid":
            # logger.info(f" ")
            # logger.info(payload)
            # logger.info(f" ")

            logger.info(f"Webhook_stripe invoice.paid : {payload}")
            payload_object = payload['data']['object']
            billing_reason = payload_object.get('billing_reason')

            # C'est un renouvellement d'abonnement
            if billing_reason == 'subscription_cycle' \
                    and payload_object.get('paid'):

                product_sold_stripe_id = None
                for line in payload_object['lines']['data']:
                    product_sold_stripe_id = line['price']['product']
                    break

                # On va chercher le tenant de l'abonnement grâce à l'id du product stripe
                # dans la requete POST
                with schema_context('public'):
                    try:
                        product_from_public_tenant = ProductDirectory.objects.get(
                            product_sold_stripe_id=product_sold_stripe_id,
                        )
                        place = product_from_public_tenant.place
                    except ProductDirectory.DoesNotExist:
                        logger.error(
                            f"Webhook_stripe invoice.paid DoesNotExist : product_sold_stripe_id {product_sold_stripe_id}, serveur de test ?")
                        return Response('ProductDirectory DoesNotExist, serveur de test ?',
                                        status=status.HTTP_204_NO_CONTENT)

                # On a le tenant ( place ), on va chercher l'abonnement
                with tenant_context(place):
                    invoice = payload_object['id']
                    try:
                        membership = Membership.objects.get(
                            stripe_id_subscription=payload_object['subscription']
                        )
                        last_stripe_invoice = membership.last_stripe_invoice

                        # Même adhésion, mais facture différente :
                        # C'est alors un renouvellement automatique.
                        if invoice != last_stripe_invoice:
                            logger.info((f'    nouvelle facture arrivée : {invoice}'))
                            paiement_stripe = new_entry_from_stripe_invoice(membership.user, invoice)

                            return paiment_stripe_validator(request, paiement_stripe)

                        else:
                            logger.info((f'    facture déja créée et comptabilisée : {invoice}'))

                    except Membership.DoesNotExist:
                        logger.info((f'    Nouvelle adhésion, facture pas encore comptabilisée : {invoice}'))
                    except Exception:
                        logger.error((f'    erreur dans Webhook_stripe customer.subscription.updated : {Exception}'))
                        raise Exception

        # c'est une requete depuis vue.js.
        post_from_front_vue_js = payload.get('uuid')
        if post_from_front_vue_js:
            logger.info(f"Webhook_stripe post_from_front_vue_js : {payload}")
            paiement_stripe = get_object_or_404(Paiement_stripe,
                                                uuid=post_from_front_vue_js)
            return paiment_stripe_validator(request, paiement_stripe)

        # Réponse pour l'api stripe qui envoie des webhook pour tout autre que la validation de paiement.
        # Si on renvoie une erreur, ils suppriment le webhook de leur côté.
        return Response('Pouple', status=status.HTTP_207_MULTI_STATUS)

    def get(self, request, uuid_paiement):
        logger.info("*" * 30)
        logger.info(f"{datetime.now()} - Webhook_stripe GET : {uuid_paiement}")
        logger.info("*" * 30)

        paiement_stripe = get_object_or_404(Paiement_stripe,
                                            uuid=uuid_paiement)
        return paiment_stripe_validator(request, paiement_stripe)
