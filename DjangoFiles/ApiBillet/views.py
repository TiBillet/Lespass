# Create your views here.
import json

import requests
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.utils import timezone
from django_weasyprint import WeasyTemplateView
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from ApiBillet.serializers import EventSerializer, PriceSerializer, ProductSerializer, ReservationSerializer, \
    ReservationValidator
from AuthBillet.models import TenantAdminPermission
from Customers.models import Client, Domain
from BaseBillet.models import Event, Price, Product, Reservation, Configuration, Ticket
from rest_framework import viewsets, permissions, status

import os
import logging
logger = logging.getLogger(__name__)


def new_tenants(schema_name):
    tenant = Client.objects.get_or_create(schema_name=schema_name,
                                          name=schema_name,
                                          paid_until='2200-12-05',
                                          on_trial=False)[0]

    tenant_domain = Domain.objects.get_or_create(domain=f'{schema_name}.{os.getenv("DOMAIN")}',
                                                 tenant=tenant,
                                                 is_primary=True,
                                                 )

    return tenant, tenant_domain


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
        serializer = ProductSerializer(Product.objects.all(), many=True, context={'request': request})
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


class EventsViewSet(viewsets.ViewSet):

    def list(self, request):
        queryset = Event.objects.all().order_by('-datetime')
        serializer = EventSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        queryset = Event.objects.all().order_by('-datetime')
        event = get_object_or_404(queryset, pk=pk)
        serializer = EventSerializer(event)
        return Response(serializer.data)

    def create(self, request):
        serializer = EventSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, pk=None):
        queryset = Event.objects.all().order_by('-datetime')
        print(f"update : {pk}")
        event = get_object_or_404(queryset, pk=pk)
        print(event)
        serializer = EventSerializer(event, data=request.data)
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
        permission_classes = [TenantAdminPermission]
        return [permission() for permission in permission_classes]


class Membership(viewsets.ViewSet):

    def send_mail_to_cashless_for_membership(request, data: dict, carte: any):
        sess = requests.Session()
        configuration = Configuration.get_solo()

        r = sess.post(
            f'{configuration.server_cashless}/api/billetterie_qrcode_adhesion',
            headers={
                'Authorization': f'Api-Key {configuration.key_cashless}'
            },
            data={
                'prenom': data.get('prenom'),
                'name': data.get('name'),
                'email': data.get('email'),
                'tel': data.get('tel'),
                'uuid_carte': carte.uuid,
            })

        sess.close()

        # nouveau membre crée avec uniquement l'email on demande la suite.
        # HTTP_202_ACCEPTED
        # HTTP_201_CREATED
        if r.status_code in (201, 204):
            messages.success(request, f"{data.get('email')}", extra_tags='email')
            return HttpResponseRedirect(f'#demande_nom_prenom_tel')

        # partial information :
        elif r.status_code == 206:
            partial = json.loads(r.text)
            messages.success(request, f"{data.get('email')}", extra_tags='email')
            if partial.get('name'):
                messages.success(request, f"Email déja connu. Name déja connu", extra_tags='name')
            if partial.get('prenom'):
                messages.success(request, f"Email déja connu. prenom déja connu", extra_tags='prenom')
            if partial.get('tel'):
                messages.success(request, f"Email déja connu. tel déja connu", extra_tags='tel')
            return HttpResponseRedirect(f'#demande_nom_prenom_tel')

        # nouveau membre crée, on demande la suite.
        elif r.status_code == 202:
            messages.success(request, f"Carte liée au membre {data.get('email')}")
            return HttpResponseRedirect(f'#adhesionsuccess')

        else:
            messages.error(request, f'Erreur {r.status_code} {r.text}')
            return HttpResponseRedirect(f'#erreur')


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
