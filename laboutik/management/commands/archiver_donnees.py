"""
Management command pour archiver les donnees fiscales d'un tenant sur une periode.
/ Management command to archive fiscal data for a tenant over a period.

LOCALISATION : laboutik/management/commands/archiver_donnees.py

Usage :
    docker exec lespass_django poetry run python manage.py archiver_donnees \
        --schema=lespass \
        --debut=2025-01-01 \
        --fin=2025-12-31 \
        --output=/tmp/archives
"""
import os
from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django_tenants.utils import schema_context


class Command(BaseCommand):
    help = 'Archive les donnees fiscales d\'un tenant sur une periode / Archives fiscal data for a tenant over a period'

    def add_arguments(self, parser):
        parser.add_argument(
            '--schema', type=str, required=True,
            help='Nom du schema tenant (ex: lespass)',
        )
        parser.add_argument(
            '--debut', type=str, required=True,
            help='Date de debut de la periode au format YYYY-MM-DD',
        )
        parser.add_argument(
            '--fin', type=str, required=True,
            help='Date de fin de la periode au format YYYY-MM-DD',
        )
        parser.add_argument(
            '--output', type=str, required=True,
            help='Repertoire de destination du fichier ZIP',
        )

    def handle(self, *args, **options):
        schema = options['schema']
        debut_str = options['debut']
        fin_str = options['fin']
        output_dir = options['output']

        # --- Parsing des dates / Parse dates ---
        try:
            debut = date.fromisoformat(debut_str)
        except ValueError:
            raise CommandError(
                f"Format de date invalide pour --debut : '{debut_str}'. Attendu : YYYY-MM-DD"
            )

        try:
            fin = date.fromisoformat(fin_str)
        except ValueError:
            raise CommandError(
                f"Format de date invalide pour --fin : '{fin_str}'. Attendu : YYYY-MM-DD"
            )

        # --- Garde : fin ne peut pas etre avant debut / Guard: fin cannot be before debut ---
        if fin < debut:
            raise CommandError(
                f"La date de fin ({fin}) est anterieure a la date de debut ({debut})."
            )

        # --- Garde : periode maximale 365 jours / Guard: max period 365 days ---
        nb_jours = (fin - debut).days
        if nb_jours > 365:
            raise CommandError(
                f"La periode demandee est de {nb_jours} jours. "
                f"Le maximum autorise est 365 jours."
            )

        # --- Garde : le tenant doit exister / Guard: tenant must exist ---
        from Customers.models import Client
        try:
            Client.objects.get(schema_name=schema)
        except Client.DoesNotExist:
            raise CommandError(
                f"Aucun tenant trouve avec le schema '{schema}'."
            )

        # --- Creation du repertoire de sortie si necessaire / Create output dir if needed ---
        os.makedirs(output_dir, exist_ok=True)

        # --- Traitement dans le contexte du tenant / Processing inside tenant context ---
        with schema_context(schema):
            from laboutik.models import LaboutikConfiguration
            from laboutik.archivage import (
                generer_fichiers_archive,
                calculer_hash_fichiers,
                empaqueter_zip,
                creer_entree_journal,
            )

            # Recuperer la cle HMAC / Get HMAC key
            config = LaboutikConfiguration.get_solo()
            cle = config.get_hmac_key()

            # --- Garde : la cle HMAC doit etre configuree / Guard: HMAC key must be set ---
            if not cle:
                raise CommandError(
                    f"[{schema}] Pas de cle HMAC configuree dans LaboutikConfiguration. "
                    f"Impossible de generer une archive signee."
                )

            self.stdout.write(
                f"[{schema}] Generation de l'archive du {debut} au {fin} ({nb_jours} jours)..."
            )

            # 1. Generer les fichiers CSV + JSON / Generate CSV + JSON files
            fichiers = generer_fichiers_archive(schema, debut, fin)

            # 2. Calculer les HMAC de chaque fichier / Compute HMAC for each file
            hash_json = calculer_hash_fichiers(fichiers, cle)

            # 3. Emballer dans un ZIP / Pack into ZIP
            zip_bytes = empaqueter_zip(fichiers, hash_json)

            # 4. Determiner le chemin de sortie / Determine output path
            # Format : {schema}_{YYYYMMDD}_{YYYYMMDD}.zip
            debut_no_dash = debut_str.replace('-', '')
            fin_no_dash = fin_str.replace('-', '')
            nom_fichier = f"{schema}_{debut_no_dash}_{fin_no_dash}.zip"
            chemin_complet = os.path.join(output_dir, nom_fichier)

            # 5. Ecrire le ZIP sur le disque / Write ZIP to disk
            with open(chemin_complet, 'wb') as f:
                f.write(zip_bytes)

            # 6. Journaliser l'operation / Log the operation
            hash_global = hash_json.get('hash_global', '')
            creer_entree_journal(
                type_operation='ARCHIVAGE',
                details={
                    'schema': schema,
                    'debut': debut_str,
                    'fin': fin_str,
                    'nb_jours': nb_jours,
                    'chemin': chemin_complet,
                    'taille_bytes': len(zip_bytes),
                    'hash_global': hash_global,
                    'compteurs': {
                        nom: len(contenu.split(b'\n')) - 2
                        for nom, contenu in fichiers.items()
                        if nom.endswith('.csv')
                    },
                },
                cle_secrete=cle,
            )

            # 7. Afficher le message de succes / Display success message
            self.stdout.write(self.style.SUCCESS(
                f"  Archive generee : {chemin_complet}\n"
                f"  Taille : {len(zip_bytes):,} octets\n"
                f"  Hash global : {hash_global}"
            ))
