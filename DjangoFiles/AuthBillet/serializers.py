import datetime

from django.contrib.auth import get_user_model
from django.db import connection
from django.utils.text import slugify
from rest_framework import serializers
import json
from django.utils.translation import gettext, gettext_lazy as _
from rest_framework.generics import get_object_or_404
from django_tenants.utils import schema_context, tenant_context

from AuthBillet.models import TibilletUser, HumanUser
from BaseBillet.models import Event, Price, Product, Reservation, Configuration, LigneArticle, Ticket, Paiement_stripe, \
    PriceSold, ProductSold, Artist_on_event
from Customers.models import Client
from PaiementStripe.views import creation_paiement_stripe

import logging

logger = logging.getLogger(__name__)


class MeSerializer(serializers.ModelSerializer):
    class Meta:
        model = TibilletUser
        fields = [
            "uuid",
            "name",
            "publish",
            "img",
            "categorie_article",
            "prices",
        ]
        depth = 1