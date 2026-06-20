"""
Management command pour verifier l'integrite d'une archive fiscale ZIP.
/ Management command to verify the integrity of a fiscal ZIP archive.

LOCALISATION : laboutik/management/commands/verifier_archive.py

Usage :
    docker exec lespass_django poetry run python manage.py verifier_archive \
        --archive /chemin/vers/archive.zip \
        --schema lespass
"""
import sys

from django.core.management.base import BaseCommand, CommandError
from django_tenants.utils import schema_context


class Command(BaseCommand):
    help = 'Verifie l\'integrite d\'une archive fiscale ZIP / Verifies fiscal ZIP archive integrity'

    def add_arguments(self, parser):
        parser.add_argument(
            '--archive', type=str, required=True,
            help='Chemin vers le fichier ZIP a verifier / Path to the ZIP file to verify',
        )
        parser.add_argument(
            '--schema', type=str, required=True,
            help='Nom du schema tenant (pour recuperer la cle HMAC) / Tenant schema name (to retrieve HMAC key)',
        )

    def handle(self, *args, **options):
        chemin_zip = options['archive']
        schema = options['schema']

        # Verifier que le fichier ZIP existe / Check that the ZIP file exists
        import os
        if not os.path.isfile(chemin_zip):
            raise CommandError(
                f"Fichier introuvable : {chemin_zip}"
                f" / File not found: {chemin_zip}"
            )

        # Verifier que le tenant existe / Check that the tenant exists
        from Customers.models import Client
        if not Client.objects.filter(schema_name=schema).exists():
            raise CommandError(
                f"Schema tenant introuvable : {schema}"
                f" / Tenant schema not found: {schema}"
            )

        # Lire le fichier ZIP en bytes / Read the ZIP file as bytes
        with open(chemin_zip, 'rb') as f:
            zip_bytes = f.read()

        with schema_context(schema):
            from laboutik.models import LaboutikConfiguration
            from laboutik.archivage import verifier_hash_archive, creer_entree_journal

            config = LaboutikConfiguration.get_solo()
            cle = config.get_hmac_key()

            # Verifier que la cle HMAC est configuree / Check HMAC key is configured
            if not cle:
                raise CommandError(
                    f"[{schema}] Pas de cle HMAC configuree. Impossible de verifier l'archive."
                    f" / [{schema}] No HMAC key configured. Cannot verify archive."
                )

            self.stdout.write(f"[{schema}] Verification de l'archive : {chemin_zip}")

            # Verifier les HMAC de l'archive / Verify archive HMACs
            est_valide, resultats = verifier_hash_archive(zip_bytes, cle)

            # Afficher les resultats fichier par fichier / Print per-file results
            for detail in resultats:
                nom = detail['nom']
                valide = detail['valide']
                if valide:
                    self.stdout.write(self.style.SUCCESS(f"  OK  {nom}"))
                else:
                    self.stdout.write(self.style.ERROR(
                        f"  KO  {nom}"
                        f" (attendu: {detail['hash_attendu'][:16]}..."
                        f" calcule: {detail['hash_calcule'][:16]}...)"
                    ))

            # Enregistrer l'operation dans le journal / Log the operation to the journal
            details_journal = {
                'archive': chemin_zip,
                'schema': schema,
                'est_valide': est_valide,
                'nb_fichiers': len(resultats),
                'nb_erreurs': sum(1 for d in resultats if not d['valide']),
            }
            creer_entree_journal(
                type_operation='VERIFICATION',
                details=details_journal,
                cle_secrete=cle,
            )

            # Resultat global / Global result
            if est_valide:
                self.stdout.write(self.style.SUCCESS(
                    f"\n[{schema}] ARCHIVE INTEGRE — {len(resultats)} fichier(s) verifies, 0 erreur"
                ))
            else:
                nb_erreurs = sum(1 for d in resultats if not d['valide'])
                self.stdout.write(self.style.ERROR(
                    f"\n[{schema}] ALERTE — {nb_erreurs} erreur(s) detectee(s) sur {len(resultats)} fichier(s)"
                ))
                sys.exit(1)
