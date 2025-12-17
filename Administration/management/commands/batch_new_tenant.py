import csv
import json
import logging
import os
import sys
from typing import Iterable, List, Tuple

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils.text import slugify
from django_tenants.utils import schema_context, tenant_context

from AuthBillet.utils import get_or_create_user
from BaseBillet.models import Configuration
from Customers.models import Client, Domain

logger = logging.getLogger(__name__)


def _norm_emails(value) -> List[str]:
    """Normalize email field to a list of non-empty, lower-cased emails."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        emails = value
    else:
        # CSV case or single string; split on comma/semicolon
        emails = [e for chunk in str(value).split(';') for e in chunk.split(',')]
    return [e.strip().lower() for e in emails if e and e.strip()]


def _iter_input_rows(path: str) -> Iterable[dict]:
    """Yield dict rows with keys: Name, description, email.

    Supports JSON (array or object) and CSV.
    """
    if not os.path.isfile(path):
        raise CommandError(f"Fichier introuvable: {path}")

    ext = os.path.splitext(path)[1].lower()
    with open(path, 'r', encoding='utf-8') as fh:
        if ext in ('.json',):
            data = json.load(fh)
            items = data if isinstance(data, list) else [data]
            for item in items:
                # La variable attendue est "Name" (compat: tolère aussi "name"/"nom")
                yield {
                    'Name': item.get('Name') or item.get('name') or item.get('nom') or '',
                    'description': item.get('description') or '',
                    'email': item.get('email'),
                }
        elif ext in ('.csv',):
            reader = csv.DictReader(fh)
            for row in reader:
                yield {
                    'Name': row.get('Name') or row.get('name') or row.get('nom') or '',
                    'description': row.get('description') or '',
                    'email': row.get('email'),
                }
        else:
            raise CommandError("Format non supporté (utilisez .json ou .csv)")


class Command(BaseCommand):
    help = "Création par lot de nouveaux tenants en 2 temps depuis JSON/CSV (email, Name, description)."

    def add_arguments(self, parser):
        parser.add_argument('--file', '-f', required=True, help='Chemin du fichier JSON ou CSV')

    def handle(self, *args, **options):
        input_path = options['file']

        base_domain = os.getenv('DOMAIN')
        if not base_domain:
            raise CommandError("Variable d'environnement DOMAIN manquante")

        created_clients: List[Tuple[Client, dict]] = []

        # Phase 1: création des tenants en attente dans PUBLIC + schéma (pas de domaine ici)
        with schema_context('public'):
            for row in _iter_input_rows(input_path):
                name = (row.get('Name') or '').strip()
                if not name:
                    self.stderr.write(self.style.WARNING("Ligne ignorée: 'Name' manquant"))
                    continue

                description = row.get('description') or ''
                emails = _norm_emails(row.get('email'))
                if not emails:
                    self.stderr.write(self.style.WARNING(f"{name}: aucun email fourni — ligne ignorée"))
                    continue

                slug = slugify(name)
                if not slug:
                    self.stderr.write(self.style.WARNING(f"{name}: slug vide — ligne ignorée"))
                    continue

                # Crée ou récupère le Client en mode WAITING_CONFIG
                client, created = Client.objects.get_or_create(
                    schema_name=slug,
                    defaults={
                        'name': slug,
                        'on_trial': False,
                        'categorie': Client.WAITING_CONFIG,
                    }
                )

                if not created:
                    # Met à jour la catégorie si besoin pour le pipeline d'init
                    if client.categorie != Client.WAITING_CONFIG:
                        client.categorie = Client.WAITING_CONFIG
                        client.save()
                    msg = f"Client déjà existant pour {slug}, on continue"
                    logger.info(msg)
                    self.stdout.write(self.style.WARNING(msg))
                else:
                    # Empêche l'auto-creation car on gère le schéma à la main
                    client.auto_create_schema = False
                    client.save()
                    self.stdout.write(self.style.SUCCESS(f"Client WAITING_CONFIG créé: {slug}"))

                # Crée le schéma si nécessaire
                with connection.cursor() as cursor:
                    cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{slug}";')

                # Mémorise les infos pour la finalisation
                created_clients.append((client, {
                    'Name': name,
                    'slug': slug,
                    'description': description,
                    'emails': emails,
                }))

        # Phase 2: migrations des schémas créés
        if created_clients:
            try:
                import subprocess
                self.stdout.write(self.style.NOTICE("Lancement des migrations des tenants (multiprocessing)..."))
                subprocess.run(
                    [sys.executable, 'manage.py', 'migrate_schemas', '--executor=multiprocessing'],
                    check=True,
                )
                self.stdout.write(self.style.SUCCESS("Migrations terminées."))
            except Exception as e:
                logger.exception("Erreur lors des migrations des tenants")
                raise CommandError(f"Erreur migrations tenants: {e}")

        # Phase 3: finalisation (admins + Configuration)
        if created_clients:
            for client, meta in created_clients:
                try:
                    # Domaine primaire (créé après migrations)
                    with schema_context('public'):
                        domain_str = f"{meta['slug']}.{base_domain}"
                        Domain.objects.get_or_create(
                            domain=domain_str,
                            tenant=client,
                            defaults={'is_primary': True}
                        )

                    with tenant_context(client):
                        # Group staff
                        from django.contrib.auth.models import Group
                        staff_group, _ = Group.objects.get_or_create(name="staff")

                        emails = meta['emails']
                        primary = emails[0]
                        secondary = emails[1] if len(emails) > 1 else None

                        # Admin principal
                        admin_user = get_or_create_user(primary)
                        if admin_user is None:
                            self.stderr.write(self.style.ERROR(f"{meta['slug']}: impossible de créer l'admin principal {primary}"))
                        else:
                            admin_user.client_admin.add(client)
                            admin_user.is_staff = True
                            admin_user.is_superuser = True
                            admin_user.groups.add(staff_group)
                            admin_user.save()

                        # Second admin (ajout au client_admin)
                        if secondary:
                            second_user = get_or_create_user(secondary)
                            if second_user:
                                second_user.client_admin.add(client)
                                second_user.save()

                        # Configuration de base
                        cfg = Configuration.get_solo()
                        cfg.organisation = meta['Name']
                        # Remplit les descriptions s'il y en a
                        desc = (meta.get('description') or '').strip()
                        if desc:
                            cfg.long_description = desc
                            cfg.short_description = desc[:250]
                        # Préremplit le slug si vide
                        if not cfg.slug:
                            cfg.slug = meta['slug']
                        # Préremplit l'email si vide
                        if not cfg.email:
                            cfg.email = primary
                        cfg.save()

                        self.stdout.write(self.style.SUCCESS(f"{meta['slug']}: finalisation OK"))

                except Exception as e:
                    logger.exception("Finalisation échouée pour %s", meta.get('slug'))
                    self.stderr.write(self.style.ERROR(f"{meta.get('slug')}: erreur de finalisation — {e}"))

        if not created_clients:
            self.stdout.write(self.style.WARNING("Aucun tenant traité"))
        else:
            self.stdout.write(self.style.SUCCESS(f"Tenants traités: {', '.join(m['slug'] for _, m in created_clients)}"))
