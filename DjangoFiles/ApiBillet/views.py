# Create your views here.
import json
import requests
from django.http import HttpResponseRedirect
from django.utils import timezone
from django_tenants.utils import schema_context, tenant_context
from django_weasyprint import WeasyTemplateView
from rest_framework import serializers
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from django.utils.translation import ugettext_lazy as _
from django.utils.text import slugify

from ApiBillet.serializers import EventSerializer, PriceSerializer, ProductSerializer, ReservationSerializer, \
    ReservationValidator, MembreshipValidator, ConfigurationSerializer, NewConfigSerializer, \
    EventCreateSerializer
from AuthBillet.models import TenantAdminPermission, TibilletUser
from Customers.models import Client, Domain
from BaseBillet.models import Event, Price, Product, Reservation, Configuration, Ticket
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
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            permission_classes = [permissions.AllowAny]
        else:
            permission_classes = [TenantAdminPermission]
        return [permission() for permission in permission_classes]


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
                        categorie=Client.ARTISTE,
                    )

                    if not created:
                        return Response(_(json.dumps({"uuid": f"{tenant.uuid}", "msg":f"{futur_conf.get('organisation')} existe déja"})),
                                        status=status.HTTP_409_CONFLICT)

                    domain, created = Domain.objects.get_or_create(
                        domain=f"{slugify(futur_conf.get('organisation'))}.{os.getenv('DOMAIN')}",
                        tenant=tenant,
                        is_primary=True
                    )
                except IntegrityError as e:
                    return Response(_(f"{e}"), status=status.HTTP_409_CONFLICT)
                except Exception as e:
                    return Response(_(f"{e}"), status=status.HTTP_405_METHOD_NOT_ALLOWED)

            print(tenant)
            with tenant_context(tenant):
                conf = Configuration.get_solo()
                serializer.update(instance=conf, validated_data=futur_conf)

                user.client_admin.add(tenant)

            return Response(serializer.data, status=status.HTTP_201_CREATED)
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
                serializer.update(conf, serializer.validated_data)
                return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def list(self, request):
        places_serialized_with_uuid = []
        configurations = []
        for tenant in Client.objects.filter(categorie__in=['A',]):
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



class PlacesViewSet(viewsets.ViewSet):

    def create(self, request):
        user: TibilletUser = request.user
        if not user.can_create_tenant:
            raise serializers.ValidationError(_("Vous n'avez pas la permission de créer de nouveaux lieux"))
        if not request.data.get('categorie'):
            raise serializers.ValidationError(_("categorie est obligatoire"))
        if request.data.get('categorie') not in [Client.SALLE_SPECTACLE, ]:
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
                        # raise serializers.ValidationError(_("Vous n'avez pas la permission de créer de nouveaux lieux"))
                        return Response(_(json.dumps({"uuid": f"{tenant.uuid}", "msg":f"{futur_conf.get('organisation')} existe déja"})),
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

            print(tenant)
            with tenant_context(tenant):
                conf = Configuration.get_solo()
                serializer.update(instance=conf, validated_data=futur_conf)

                user.client_admin.add(tenant)

            return Response(serializer.data, status=status.HTTP_201_CREATED)
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
        for tenant in Client.objects.filter(categorie__in=['S', 'F']):
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
        place_serialized = ConfigurationSerializer(Configuration.get_solo(), context={'request': request})
        dict_with_uuid = {'uuid': f"{connection.tenant.uuid}"}
        dict_with_uuid.update(place_serialized.data)
        return Response(dict_with_uuid)

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            permission_classes = [permissions.AllowAny]
        else:
            permission_classes = [TenantAdminPermission]
        return [permission() for permission in permission_classes]


class EventsViewSet(viewsets.ViewSet):

    def list(self, request):
        queryset = Event.objects.all().order_by('-datetime')
        events_serialized = EventSerializer(queryset, many=True, context={'request': request})
        return Response(events_serialized.data)

    def retrieve(self, request, pk=None):
        queryset = Event.objects.all().order_by('-datetime')
        event = get_object_or_404(queryset, pk=pk)
        serializer = EventSerializer(event)
        return Response(serializer.data)

    def create(self, request):
        serializer = EventCreateSerializer(data=request.data, partial=True)
        if serializer.is_valid():
            print(request.data)
            return Response(serializer.validated_data, status=status.HTTP_205_RESET_CONTENT)
        #     serializer.save()
        #     return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

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


class ReservationViewset(viewsets.ViewSet):
    def list(self, request):
        queryset = Reservation.objects.all().order_by('-datetime')
        serializer = ReservationSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)

    def create(self, request):
        print(request.data)
        validator = ReservationValidator(data=request.data, context={'request': request})
        if validator.is_valid():
            # serializer.save()
            return Response(validator.data, status=status.HTTP_201_CREATED)
        return Response(validator.errors, status=status.HTTP_400_BAD_REQUEST)

    def get_permissions(self):
        if self.action in ['list']:
            permission_classes = [TenantAdminPermission]
        else:
            permission_classes = [permissions.AllowAny]
        return [permission() for permission in permission_classes]


class MembershipViewset(viewsets.ViewSet):
    permission_classes = [AllowAny]

    def create(self, request):
        print(request.data)
        validator = MembreshipValidator(data=request.data, context={'request': request})
        if validator.is_valid():
            # serializer.save()
            return Response(validator.data, status=status.HTTP_201_CREATED)
        return Response(validator.errors, status=status.HTTP_400_BAD_REQUEST)

    def get_permissions(self):
        if self.action in ['create']:
            permission_classes = [permissions.AllowAny]
        else:
            permission_classes = [TenantAdminPermission]

        return [permission() for permission in permission_classes]


class TicketPdf(WeasyTemplateView):
    permission_classes = [AllowAny]
    template_name = 'ticket/ticket.html'

    def get_context_data(self, pk_uuid, **kwargs):
        logger.info(f"{timezone.now()} création de pdf demandé. uuid : {pk_uuid}")

        self.config = Configuration.get_solo()
        ticket: Ticket = get_object_or_404(Ticket, uuid=pk_uuid)
        kwargs['ticket'] = ticket
        kwargs['config'] = self.config

        '''
        context = {
            'ticket': ticket,
            'config': config,
        }
        '''

        self.pdf_filename = ticket.pdf_filename()
        return kwargs

    def get_pdf_filename(self, **kwargs):
        return self.pdf_filename

#
