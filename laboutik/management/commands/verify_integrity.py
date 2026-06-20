"""
Management command pour verifier l'integrite de la chaine HMAC.
/ Management command to verify HMAC chain integrity.

LOCALISATION : laboutik/management/commands/verify_integrity.py

Usage :
    docker exec lespass_django poetry run python manage.py verify_integrity --schema=lespass
"""
from django.core.management.base import BaseCommand
from django.db import connection
from django_tenants.utils import schema_context

from BaseBillet.models import LigneArticle, SaleOrigin


class Command(BaseCommand):
    help = 'Verifie la chaine HMAC des LigneArticle / Verifies HMAC chain integrity'

    def add_arguments(self, parser):
        parser.add_argument(
            '--schema', type=str, default=None,
            help='Schema du tenant a verifier (defaut: tenant courant)',
        )

    def handle(self, *args, **options):
        schema = options['schema'] or connection.schema_name

        # Si on est dans le schema public, prendre le premier tenant
        # / If in public schema, take the first tenant
        if schema == 'public':
            from Customers.models import Client
            tenant = Client.objects.exclude(schema_name='public').first()
            if not tenant:
                self.stderr.write("Aucun tenant trouve.")
                return
            schema = tenant.schema_name

        with schema_context(schema):
            from laboutik.models import LaboutikConfiguration
            from laboutik.integrity import verifier_chaine

            config = LaboutikConfiguration.get_solo()
            cle = config.get_hmac_key()

            if not cle:
                self.stdout.write(self.style.WARNING(
                    f"[{schema}] Pas de cle HMAC configuree. Aucune verification possible."
                ))
                return

            lignes = LigneArticle.objects.filter(
                sale_origin=SaleOrigin.LABOUTIK,
            )
            total_lignes = lignes.count()
            lignes_avec_hmac = lignes.filter(hmac_hash__gt='').count()

            self.stdout.write(
                f"[{schema}] {total_lignes} lignes totales, {lignes_avec_hmac} avec HMAC"
            )

            est_valide, erreurs, corrections = verifier_chaine(lignes, cle)

            if corrections:
                self.stdout.write(self.style.WARNING(
                    f"  {len(corrections)} correction(s) tracee(s) "
                    f"(HMAC casse volontairement)"
                ))
                for c in corrections:
                    self.stdout.write(
                        f"    - {c['uuid']} : {c['ancien_moyen']} -> {c['nouveau_moyen']}"
                    )

            if est_valide:
                self.stdout.write(self.style.SUCCESS(
                    f"  CHAINE INTEGRE — {lignes_avec_hmac} lignes verifiees, 0 erreur"
                ))
            else:
                self.stdout.write(self.style.ERROR(
                    f"  ALERTE — {len(erreurs)} erreur(s) d'integrite detectee(s) :"
                ))
                for e in erreurs:
                    self.stdout.write(f"    - {e['uuid']} ({e['datetime']})")
