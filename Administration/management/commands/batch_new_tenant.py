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
from BaseBillet.models import Configuration, FederatedPlace
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
        parser.add_argument('--federation', '-r', required=False, help='On fédère les tenants sur cette instance')
        parser.add_argument('--mail', '-m', action='store_true', help='On envoie les mails aux adresses fournies')

    def _federate_clients(self, federation_slug: str, clients: List[Client]):
        """S'assure que les clients fournis sont enregistrés comme lieux fédérés dans le tenant cible."""
        try:
            # schema_name est utilisé pour identifier le tenant de la fédération
            fed_client = Client.objects.get(schema_name=federation_slug)
            with tenant_context(fed_client):
                from BaseBillet.models import FederatedPlace
                for client in clients:
                    FederatedPlace.objects.update_or_create(
                        tenant=client,
                        defaults={'membership_visible': True}
                    )
                    self.stdout.write(self.style.SUCCESS(f"Fédération OK : {client.name} ajouté à {federation_slug}"))
        except Client.DoesNotExist:
            self.stderr.write(self.style.ERROR(f"Fédération impossible : le tenant '{federation_slug}' n'existe pas."))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Erreur lors de la fédération : {e}"))

    def handle(self, *args, **options):
        input_path = options['file']
        send_mail = options['mail']  # True si -m est présent, False sinon

        base_domain = 'tibillet.coop'
        if not base_domain:
            raise CommandError("Variable d'environnement DOMAIN manquante")

        created_clients: List[Tuple[Client, dict]] = []
        # Exemple : [(<Client: tenant1>, {'Name': 'Mon Org', 'slug': 'mon-org', 'emails': ['admin@ex.com']}), ...]

        # Phase 1: création des tenants en attente dans PUBLIC + schéma (pas de domaine ici)
        with schema_context('public'):
            for row in _iter_input_rows(input_path):
                name = (row.get('Name') or '').strip()
                if not name:
                    self.stderr.write(self.style.WARNING("erreur : 'Name' manquant"))
                    raise CommandError("erreur : 'Name' manquant")

                description = row.get('description') or ''
                emails = _norm_emails(row.get('email'))
                if not emails:
                    self.stderr.write(self.style.WARNING(f"{name}: aucun email fourni"))
                    raise CommandError(f"{name}: aucun email fourni")

                slug = slugify(name)
                if not slug:
                    self.stderr.write(self.style.WARNING(f"{name}: slug vide"))
                    raise CommandError(f"{name}: slug vide")

                # Étape 1: création/maj du tenant sans auto_create_schema
                client = Client.objects.filter(schema_name=slug).exists()
                if client:
                    raise CommandError(f"{name}: client avec ce nom existe déjà")

                if not client:
                    client = Client(
                        schema_name=slug,
                        name=name,
                        categorie=Client.SALLE_SPECTACLE,
                    )
                    client.auto_create_schema = False
                    client.save()
                    self.stdout.write(self.style.SUCCESS(f"Client WAITING_CONFIG créé: {slug}"))

                # Crée le schéma si nécessaire
                with connection.cursor() as cursor:
                    cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{slug}";')

                # Domaine principal idempotent et rattaché au tenant
                try:
                    domain_str = f"{slug}.{base_domain}"
                    domain_obj, _ = Domain.objects.get_or_create(
                        domain=domain_str,
                        tenant=client,
                        is_primary=True,
                    )
                except Exception as e:
                    logger.warning(f"Impossible d'assurer le domaine principal pour {name}: {e}")
                    raise CommandError(f"Impossible d'assurer le domaine principal pour {name}: {e}")

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
                    with tenant_context(client):
                        # Group staff
                        emails = meta['emails']
                        primary = emails[0]
                        secondary = emails[1] if len(emails) > 1 else None

                        # Admin principal
                        admin_user = get_or_create_user(primary, send_mail=send_mail)
                        if admin_user is None:
                            self.stderr.write(self.style.ERROR(f"{meta['slug']}: impossible de créer l'admin principal {primary}"))
                            raise CommandError(f"Impossible de créer l'admin principal {primary} pour {meta['slug']}")
                        else:
                            admin_user.client_admin.add(client)
                            admin_user.save()

                        # Second admin (ajout au client_admin)
                        if secondary:
                            second_user = get_or_create_user(primary, send_mail=send_mail)
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

        # Phase 4: Fédération (optionnel)
        federation_slug = options.get('federation')
        if federation_slug and created_clients:
            # On extrait juste la liste des objets Client de created_clients
            clients_only = [c for c, _ in created_clients]
            self._federate_clients(federation_slug, clients_only)

        if not created_clients:
            self.stdout.write(self.style.WARNING("Aucun tenant traité"))
        else:
            self.stdout.write(self.style.SUCCESS(f"Tenants traités: {', '.join(m['slug'] for _, m in created_clients)}"))
