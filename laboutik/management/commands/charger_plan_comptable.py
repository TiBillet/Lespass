"""
Management command pour charger le plan comptable par defaut dans un tenant.
/ Management command to load the default chart of accounts into a tenant.

Un seul plan par defaut (numeros a 6 chiffres) : voir
`laboutik/plan_comptable_par_defaut.py`. La commande AJOUTE ce qui manque : elle
n'efface rien et ne renumerote rien. On peut la relancer sans risque.
/ One single default plan (6-digit numbers). The command ADDS what is missing: it
erases nothing and renumbers nothing. Safe to run again.

LOCALISATION : laboutik/management/commands/charger_plan_comptable.py

Usage :
    docker exec lespass_django poetry run python manage.py charger_plan_comptable \
        --schema=lespass
"""

from django.core.management.base import BaseCommand
from django_tenants.utils import tenant_context


class Command(BaseCommand):
    help = (
        "Ajoute au tenant ce qui manque du plan comptable par defaut, sans rien effacer. "
        "/ Adds to the tenant what is missing from the default chart of accounts, "
        "erasing nothing."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--schema",
            type=str,
            required=True,
            help=(
                "Nom du schema tenant (ex: lespass). "
                "/ Tenant schema name (e.g. lespass)."
            ),
        )

    def handle(self, *args, **options):
        schema = options["schema"]

        # --- 1. Verifier que le tenant existe ---
        # / 1. Verify that the tenant exists
        from Customers.models import Client

        try:
            tenant = Client.objects.get(schema_name=schema)
        except Client.DoesNotExist:
            self.stderr.write(
                self.style.ERROR(
                    f"Tenant '{schema}' introuvable. / Tenant '{schema}' not found."
                )
            )
            return

        # --- 2. Charger ce qui manque, dans le tenant ---
        # / 2. Load what is missing, inside the tenant
        with tenant_context(tenant):
            from laboutik.models import CompteComptable, MappingMoyenDePaiement
            from laboutik.plan_comptable import charger_le_plan_comptable_par_defaut

            nombre_de_comptes_avant = CompteComptable.objects.count()
            nombre_de_correspondances_avant = MappingMoyenDePaiement.objects.count()

            avertissements = charger_le_plan_comptable_par_defaut()

            nombre_de_comptes_ajoutes = (
                CompteComptable.objects.count() - nombre_de_comptes_avant
            )
            nombre_de_correspondances_ajoutees = (
                MappingMoyenDePaiement.objects.count() - nombre_de_correspondances_avant
            )

        for avertissement in avertissements:
            self.stdout.write(self.style.WARNING(f"[{schema}] {avertissement}"))

        self.stdout.write(
            self.style.SUCCESS(
                f"[{schema}] {nombre_de_comptes_ajoutes} compte(s) et "
                f"{nombre_de_correspondances_ajoutees} correspondance(s) ajoute(s). "
                f"Rien n'a ete efface. "
                f"/ {nombre_de_comptes_ajoutes} account(s) and "
                f"{nombre_de_correspondances_ajoutees} mapping(s) added. "
                f"Nothing was erased."
            )
        )
