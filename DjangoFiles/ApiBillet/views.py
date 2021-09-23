from django.shortcuts import render

# Create your views here.
from ApiBillet.serializers import EventSerializer
from Customers.models import Client, Domain
from BaseBillet.models import Event
from rest_framework import viewsets, permissions

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




class EventViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows users to be viewed or edited.
    """
    queryset = Event.objects.all().order_by('-datetime')
    serializer_class = EventSerializer
    permission_classes = [permissions.AllowAny]
