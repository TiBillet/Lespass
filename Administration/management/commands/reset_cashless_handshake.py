"""
Management command pour effacer la configuration cashless (LaBoutik)
d'un tenant et permettre un nouveau handshake depuis zéro.

Management command to clear the cashless (LaBoutik) configuration
for a tenant and allow a fresh handshake from scratch.

Usage :
    docker exec lespass_django poetry run python manage.py reset_cashless_handshake --tenant <schema_name>
"""

import logging

from django.core.management.base import BaseCommand
from django_tenants.utils import tenant_context

from Customers.models import Client

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Efface la configuration cashless (LaBoutik) d'un tenant "
        "pour permettre un nouveau handshake. / "
        "Clear the cashless (LaBoutik) config for a tenant "
        "to allow a fresh handshake."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant",
            type=str,
            required=True,
            help="Nom du schéma du tenant (schema_name). / Tenant schema name.",
        )

    def handle(self, *args, **options):
        tenant_name = options["tenant"]

        try:
            tenant = Client.objects.get(schema_name=tenant_name)
        except Client.DoesNotExist:
            self.stderr.write(
                self.style.ERROR(f"Tenant '{tenant_name}' introuvable. / Tenant '{tenant_name}' not found.")
            )
            return

        with tenant_context(tenant):
            from BaseBillet.models import Configuration

            config = Configuration.get_solo()

            if not config.server_cashless and not config.key_cashless and not config.laboutik_public_pem:
                self.stdout.write(f"[{tenant_name}] Rien à effacer. / Nothing to clear.")
                return

            old_server = config.server_cashless or "(vide)"
            config.server_cashless = None
            config.key_cashless = None
            config.laboutik_public_pem = None
            config.save()

            self.stdout.write(
                self.style.SUCCESS(
                    f"[{tenant_name}] Config cashless effacée (ancien serveur : {old_server}). "
                    f"LaBoutik peut refaire le handshake."
                )
            )