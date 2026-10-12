"""
Dépublie toutes les pages de l'app pages, sur tous les lieux.
/ Unpublishes every page of the pages app, on every venue.

LOCALISATION : pages/management/commands/depublier_toutes_les_pages.py

Une page dépubliée n'est ni servie, ni listée dans le menu. Sans page d'accueil
publiée, la racine "/" d'un lieu affiche l'accueil du skin
(pages/<skin>/vues/accueil.html).
Rien n'est supprimé : une page se republie d'un clic dans l'admin « Pages ».
/ An unpublished page is neither served nor listed in the menu. Without a
published home page, "/" shows the skin's home. Nothing is deleted.

Par défaut, la commande AFFICHE seulement ce qu'elle ferait (passage à blanc).
Elle n'écrit en base qu'avec --appliquer.
/ By default it only SHOWS what it would do (dry run). --appliquer writes.

Usage :
    python manage.py depublier_toutes_les_pages               # passage à blanc
    python manage.py depublier_toutes_les_pages --appliquer
    python manage.py depublier_toutes_les_pages --schema=raffinerie --appliquer
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django_tenants.utils import tenant_context

from Customers.models import Client


class Command(BaseCommand):
    help = "Dépublie toutes les pages de l'app pages, lieu par lieu (passage à blanc par défaut)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--appliquer",
            action="store_true",
            help="Écrit en base. Sans cette option, rien n'est modifié.",
        )
        parser.add_argument(
            "--schema",
            default=None,
            help="Ne traiter qu'un seul lieu (nom du schéma).",
        )

    def handle(self, *args, **options):
        from pages.models import Page

        appliquer = options["appliquer"]

        # Le schéma public n'est pas un lieu : on l'exclut toujours.
        # / The public schema is not a venue: always excluded.
        lieux = Client.objects.exclude(schema_name="public").order_by("schema_name")
        if options["schema"]:
            lieux = lieux.filter(schema_name=options["schema"])
            if not lieux.exists():
                self.stderr.write(f"Lieu introuvable : {options['schema']}")
                return

        if not appliquer:
            self.stdout.write(
                self.style.WARNING(
                    "PASSAGE À BLANC : rien n'est modifié. Relancer avec --appliquer."
                )
            )

        total_pages_depubliees = 0
        nombre_de_lieux_touches = 0

        # Un lieu après l'autre, une transaction par lieu : un échec sur un lieu
        # n'annule pas les lieux déjà traités, et ne laisse pas un lieu à moitié fait.
        # / One venue at a time, one transaction per venue.
        for lieu in lieux:
            with tenant_context(lieu):
                pages_publiees = Page.objects.filter(publie=True).order_by("slug")
                nombre_de_pages = pages_publiees.count()
                if nombre_de_pages == 0:
                    continue

                liste_des_pages = []
                for page in pages_publiees:
                    marque_accueil = " [accueil]" if page.est_accueil else ""
                    liste_des_pages.append(f"/{page.slug}/{marque_accueil}")
                self.stdout.write(
                    f"{lieu.schema_name} ({lieu.name}) : {nombre_de_pages} page(s) — "
                    + ", ".join(liste_des_pages)
                )

                if appliquer:
                    with transaction.atomic():
                        pages_publiees.update(publie=False)

                total_pages_depubliees += nombre_de_pages
                nombre_de_lieux_touches += 1

        verbe = "dépubliée(s)" if appliquer else "à dépublier"
        self.stdout.write(
            self.style.SUCCESS(
                f"{total_pages_depubliees} page(s) {verbe} sur {nombre_de_lieux_touches} lieu(x)."
            )
        )
