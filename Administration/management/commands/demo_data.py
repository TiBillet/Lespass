from os.path import exists

import requests
import stripe
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils.text import slugify
from django_tenants.utils import tenant_context

from Customers.models import Client, Domain
import os

from root_billet.models import RootConfiguration

import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    def add_arguments(self, parser):

        # Named (optional) arguments
        parser.add_argument(
            '--tdd',
            action='store_true',
            help='Demo data for Test drived dev',
        )

    def handle(self, *args, **options):
        import ipdb; ipdb.set_trace()
