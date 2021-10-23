from django.shortcuts import render

# Create your views here.
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from ApiBillet.serializers import EventSerializer, TarifsSerializer
from AuthBillet.models import TenantAdminPermission
from Customers.models import Client, Domain
from BaseBillet.models import Event, TarifBillet
from rest_framework import viewsets, permissions, status

import os

def new_tenants(schema_name):
    tenant = Client.objects.get_or_create(schema_name=schema_name,
                                            name=schema_name,
                                            paid_until='2200-12-05',
                                            on_trial=False)[0]

    # Add one or more domains for the tenant

    tenant_domain = Domain.objects.get_or_create(domain=f'{schema_name}.{os.getenv("DOMAIN")}',
                                                   tenant=tenant,
                                                   is_primary=True,
                                                   )

    return tenant, tenant_domain

class TarifBilletViewSet(viewsets.ViewSet):
    def list(self, request):
        queryset = TarifBillet.objects.all().order_by('prix')
        serializer = TarifsSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)

    def create(self, request):
        serializer = TarifsSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get_permissions(self):
        """
        Instantiates and returns the list of permissions that this view requires.
        """
        if self.action in ['list','retrieve']:
            permission_classes = [permissions.AllowAny]
        else:
            permission_classes = [TenantAdminPermission]
        return [permission() for permission in permission_classes]

class EventsViewSet(viewsets.ViewSet):
    queryset = Event.objects.all().order_by('-datetime')

    def list(self, request):
        serializer = EventSerializer(self.queryset, many=True, context={'request': request})
        return Response(serializer.data)


    def retrieve(self, request, pk=None):
        print(f"retrieve : {pk}")
        event = get_object_or_404(self.queryset, pk=pk)
        serializer = EventSerializer(event)
        return Response(serializer.data)

    def create(self, request):
        serializer = EventSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, pk=None):
        print(f"update : {pk}")
        event = get_object_or_404(self.queryset, pk=pk)
        print(event)
        serializer = EventSerializer(event, data=request.data)
        if serializer.is_valid(raise_exception=True):
            # import ipdb; ipdb.set_trace()
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, pk=None):
        event = get_object_or_404(self.queryset, pk=pk)
        event.delete()
        return Response(('deleted'), status=status.HTTP_200_OK)

    def get_permissions(self):
        """
        Instantiates and returns the list of permissions that this view requires.
        """
        if self.action in ['list','retrieve']:
            permission_classes = [permissions.AllowAny]
        else:
            permission_classes = [TenantAdminPermission]
        return [permission() for permission in permission_classes]

class EventViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows users to be viewed or edited.
    """
    queryset = Event.objects.all().order_by('-datetime')
    serializer_class = EventSerializer
    permission_classes = [permissions.AllowAny]
