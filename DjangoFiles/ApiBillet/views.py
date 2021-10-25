from django.shortcuts import render

# Create your views here.
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from ApiBillet.serializers import EventSerializer, PriceSerializer, ProductSerializer, ReservationSerializer, \
    ReservationValidator
from AuthBillet.models import TenantAdminPermission
from Customers.models import Client, Domain
from BaseBillet.models import Event, Price, Product, Reservation
from rest_framework import viewsets, permissions, status

import os


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