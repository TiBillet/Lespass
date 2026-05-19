"""
Management command pour ajouter un ou plusieurs slots vides au pool de tenants
WAITING_CONFIG. Ce pool est consomme par `onboard.tasks.create_tenant_from_draft`
au moment ou un brouillon WaitingConfiguration est finalise : un Client deja
provisionne (schema Postgres pre-cree) est recategorise en SALLE_SPECTACLE et
renomme avec le slug du tenant final.

Sans cette commande, le pool finit par s'epuiser et la creation de tenants
echoue silencieusement (cf. `tasks.create_tenant_from_draft`, etape 2 Pool
check qui ecrit `wc.error_message` et abandonne).

A executer manuellement OU en cron (ex: nightly) pour maintenir le pool.

/ Management command to add one or more empty slots to the WAITING_CONFIG
tenant pool. This pool is consumed by `onboard.tasks.create_tenant_from_draft`
when a WaitingConfiguration draft is finalised: a pre-provisioned Client (with
pre-created Postgres schema) is re-categorised to SALLE_SPECTACLE and renamed
with the final tenant slug.

Without this command, the pool eventually depletes and tenant creation silently
fails (cf. `tasks.create_tenant_from_draft`, step 2 "Pool check" writes
`wc.error_message` and gives up).

Run manually OR via cron (e.g. nightly) to keep the pool refilled.

LOCALISATION: onboard/management/commands/create_empty_tenant.py

Usage :
    docker exec lespass_django poetry run python manage.py create_empty_tenant
    docker exec lespass_django poetry run python manage.py create_empty_tenant --count 5
"""

import secrets

from django.core.management.base import BaseCommand
from django.utils.translation import gettext_lazy as _

from Customers.models import Client, Domain


class Command(BaseCommand):
    help = (
        "Cree N tenants vides en categorie WAITING_CONFIG pour repeupler le pool. "
        "/ Create N empty WAITING_CONFIG tenants to refill the pool."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--count",
            type=int,
            default=1,
            help=_("Number of empty tenants to create (default 1)."),
        )

    def handle(self, *args, **options):
        # ATTENTION : `auto_create_schema=True` sur Client → chaque create()
        # declenche ~200 migrations sur le nouveau schema (5-7 min).
        # / WARNING: `auto_create_schema=True` on Client → each create()
        # triggers ~200 migrations on the new schema (5-7 min).
        count = options["count"]
        created = []

        for _i in range(count):
            # Genere un schema/name unique pour ne pas entrer en conflit.
            # `schema_name` n'accepte pas de tirets en PostgreSQL : on les
            # remplace par des underscores.
            # / Generate a unique schema/name to avoid conflicts. Postgres
            # `schema_name` cannot contain dashes, so we replace them with
            # underscores.
            slug = f"empty-{secrets.token_hex(4)}"
            tenant = Client.objects.create(
                schema_name=slug.replace("-", "_"),
                name=slug,
                categorie=Client.WAITING_CONFIG,
                on_trial=True,
            )
            # Domain technique, sera renomme a la prise de slot par
            # `WaitingConfiguration.create_tenant()`.
            # / Technical domain, renamed when the slot is taken by
            # `WaitingConfiguration.create_tenant()`.
            Domain.objects.create(
                domain=f"{slug}.tibillet.coop",
                tenant=tenant,
                is_primary=True,
            )
            created.append(slug)
            self.stdout.write(
                self.style.SUCCESS(f"Created empty tenant: {slug}")
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Total: {len(created)} empty tenant(s) created."
            )
        )
