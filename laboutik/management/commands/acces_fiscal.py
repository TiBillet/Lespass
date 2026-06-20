"""
Management command pour exporter l'integralite de l'historique fiscal d'un tenant.
Genere un dossier (pas un ZIP) avec tous les fichiers CSV + JSON + README.txt.
/ Management command to export the full fiscal history of a tenant.
Generates a folder (not a ZIP) with all CSV + JSON + README.txt files.

LOCALISATION : laboutik/management/commands/acces_fiscal.py

Usage :
    docker exec lespass_django poetry run python manage.py acces_fiscal \
        --schema=lespass \
        --output=/tmp/export_fiscal
"""
import json
import os
from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django_tenants.utils import schema_context


class Command(BaseCommand):
    help = (
        'Exporte l\'integralite de l\'historique fiscal d\'un tenant dans un dossier '
        '/ Exports the full fiscal history of a tenant into a folder'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--schema', type=str, required=True,
            help='Nom du schema tenant (ex: lespass)',
        )
        parser.add_argument(
            '--output', type=str, required=True,
            help='Repertoire parent dans lequel le dossier d\'export sera cree',
        )

    def handle(self, *args, **options):
        schema = options['schema']
        output_parent = options['output']

        # --- Garde : le tenant doit exister / Guard: tenant must exist ---
        from Customers.models import Client
        try:
            Client.objects.get(schema_name=schema)
        except Client.DoesNotExist:
            raise CommandError(
                f"Aucun tenant trouve avec le schema '{schema}'."
            )

        # --- Construction du nom du dossier de sortie / Build output folder name ---
        # Format : export_fiscal_{schema}_{YYYY-MM-DD}/
        date_today = date.today().isoformat()
        nom_dossier = f"export_fiscal_{schema}_{date_today}"
        chemin_dossier = os.path.join(output_parent, nom_dossier)
        os.makedirs(chemin_dossier, exist_ok=True)

        # --- Traitement dans le contexte du tenant / Processing inside tenant context ---
        with schema_context(schema):
            from laboutik.models import LaboutikConfiguration
            from laboutik.archivage import (
                generer_fichiers_archive,
                calculer_hash_fichiers,
                generer_readme_fiscal,
                creer_entree_journal,
            )

            # Recuperer la cle HMAC / Get HMAC key
            config = LaboutikConfiguration.get_solo()
            cle = config.get_hmac_key()

            # --- Garde : la cle HMAC doit etre configuree / Guard: HMAC key must be set ---
            if not cle:
                raise CommandError(
                    f"[{schema}] Pas de cle HMAC configuree dans LaboutikConfiguration. "
                    f"Impossible de generer un export signe."
                )

            self.stdout.write(
                f"[{schema}] Generation de l'export fiscal complet (tout l'historique)..."
            )

            # 1. Generer les fichiers CSV + JSON sans limite de periode / Generate files with no date limit
            fichiers = generer_fichiers_archive(schema, debut=None, fin=None)

            # 2. Calculer les HMAC de chaque fichier / Compute HMAC for each file
            hash_json = calculer_hash_fichiers(fichiers, cle)

            # 3. Ecrire chaque fichier dans le dossier / Write each file to the folder
            for nom_fichier, contenu_bytes in fichiers.items():
                chemin_fichier = os.path.join(chemin_dossier, nom_fichier)
                with open(chemin_fichier, 'wb') as f:
                    f.write(contenu_bytes)

            # 4. Ecrire hash.json / Write hash.json
            hash_json_bytes = json.dumps(hash_json, ensure_ascii=False, indent=2).encode('utf-8')
            chemin_hash = os.path.join(chemin_dossier, 'hash.json')
            with open(chemin_hash, 'wb') as f:
                f.write(hash_json_bytes)

            # 5. Ecrire README.txt / Write README.txt
            readme_bytes = generer_readme_fiscal(schema)
            chemin_readme = os.path.join(chemin_dossier, 'README.txt')
            with open(chemin_readme, 'wb') as f:
                f.write(readme_bytes)

            # 6. Journaliser l'operation / Log the operation
            hash_global = hash_json.get('hash_global', '')
            nb_fichiers = len(fichiers) + 2  # +hash.json +README.txt
            creer_entree_journal(
                type_operation='EXPORT_FISCAL',
                details={
                    'schema': schema,
                    'dossier': chemin_dossier,
                    'date_export': date_today,
                    'nb_fichiers': nb_fichiers,
                    'hash_global': hash_global,
                },
                cle_secrete=cle,
            )

            # 7. Afficher le message de succes / Display success message
            self.stdout.write(self.style.SUCCESS(
                f"  Export fiscal genere : {chemin_dossier}\n"
                f"  Nombre de fichiers : {nb_fichiers}\n"
                f"  Hash global : {hash_global}"
            ))
