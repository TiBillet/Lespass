"""
Management command : generer une (ou plusieurs) cloture(s) manuellement.
/ Manually generate one or more closures.

LOCALISATION : comptabilite/management/commands/generer_cloture.py

Usage :
    manage.py generer_cloture --niveau=J
    manage.py generer_cloture --niveau=J --tenant=lespass
    manage.py generer_cloture --niveau=M \\
        --datetime-debut=2026-04-01T00:00:00+00:00 \\
        --datetime-fin=2026-05-01T00:00:00+00:00
"""
import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Genere une cloture comptable pour un ou tous les tenants."

    def add_arguments(self, parser):
        parser.add_argument(
            "--niveau",
            choices=["J", "H", "M", "A"],
            required=True,
            help="Niveau de cloture : J (jour), H (semaine), M (mois), A (annee).",
        )
        parser.add_argument(
            "--tenant",
            default=None,
            help="schema_name d'un tenant precis. Si absent, tous les tenants.",
        )
        parser.add_argument(
            "--datetime-debut",
            default=None,
            help="ISO datetime debut (override des bornes automatiques).",
        )
        parser.add_argument(
            "--datetime-fin",
            default=None,
            help="ISO datetime fin (override des bornes automatiques).",
        )

    def handle(self, *args, **opts):
        from Customers.models import Client
        from comptabilite.tasks import generer_cloture_pour_tenant

        if opts.get("tenant"):
            tenants = Client.objects.filter(schema_name=opts["tenant"])
            if not tenants.exists():
                self.stderr.write(f"Tenant {opts['tenant']} introuvable.")
                return
        else:
            tenants = Client.objects.exclude(schema_name="public")

        for tenant in tenants:
            self.stdout.write(
                f"-> {tenant.schema_name} (niveau={opts['niveau']})"
            )
            uuid_str = generer_cloture_pour_tenant(
                schema_name=tenant.schema_name,
                niveau=opts["niveau"],
                datetime_debut_iso=opts.get("datetime_debut"),
                datetime_fin_iso=opts.get("datetime_fin"),
            )
            if uuid_str:
                self.stdout.write(self.style.SUCCESS(f"   cloture {uuid_str}"))
            else:
                self.stdout.write(
                    self.style.WARNING("   skipped (modules inactifs)")
                )
