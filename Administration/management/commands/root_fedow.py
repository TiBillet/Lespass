import logging
import os

from django.core.management.base import BaseCommand
from django_tenants.utils import schema_context

from root_billet.models import RootConfiguration

logger = logging.getLogger(__name__)


class Command(BaseCommand):

    def handle(self, *args, **options):
        pass

