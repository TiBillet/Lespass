"""
Répare la description longue des évènements de tous les lieux.
/ Repairs the long description of events in every venue.

LOCALISATION : Administration/management/commands/normaliser_textes_riches.py

Applique aux events déjà en base le même traitement qu'un nouvel
enregistrement (chantier TECH_DOC/SESSIONS/TEXTE_RICHE/SPEC.md, partie E) :
1. texte_brut_vers_html : un texte sans balise devient du HTML (sauts de
   ligne, liens). Avant, ses entités sont décodées : un texte sans balise en
   base est la sortie de nh3, donc déjà échappé (« Tom &amp; Jerry »). Sans ce
   décodage, il serait échappé deux fois (« Tom &amp;amp; Jerry ») ;
2. clean_html : nettoyage contre le XSS ;
3. normaliser_html_editeur : lignes vides de début et de fin, blocs vides,
   listes coupées.

L'écriture passe par QuerySet.update() : ni save(), ni signaux, ni
traitement d'image. Seule la colonne long_description change.
La commande est stable : la relancer ne change plus rien.

Lancer / Run :
    docker exec lespass_django poetry run python manage.py normaliser_textes_riches --dry-run
    docker exec lespass_django poetry run python manage.py normaliser_textes_riches
"""

import html as module_html

from django.core.management.base import BaseCommand
from django_tenants.utils import tenant_context

from Administration.utils import (
    UNE_BALISE_HTML,
    clean_html,
    normaliser_html_editeur,
    texte_brut_vers_html,
)
from BaseBillet.models import Event
from Customers.models import Client

# Avec --dry-run, nombre d'exemples « avant / après » affichés par lieu.
# / With --dry-run, number of before/after examples shown per venue.
NOMBRE_D_EXEMPLES_PAR_LIEU = 3


class Command(BaseCommand):
    help = (
        "Répare la description longue des évènements de tous les lieux "
        "(texte brut, lignes vides, listes coupées). / Repairs event long descriptions."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="N'écrit rien : affiche les chiffres et des exemples. / Writes nothing.",
        )

    def handle(self, *args, **options):
        passe_a_blanc = options["dry_run"]
        total_des_events_changes = 0

        tous_les_lieux = Client.objects.exclude(schema_name="public").order_by("schema_name")
        for lieu in tous_les_lieux:
            with tenant_context(lieu):
                events_lus = 0
                events_changes = 0

                events_avec_description = Event.objects.exclude(
                    long_description__isnull=True
                ).exclude(long_description="")

                for evenement in events_avec_description:
                    events_lus += 1
                    description_actuelle = evenement.long_description

                    # Texte sans balise : déjà échappé par nh3, on le décode
                    # d'abord. / Tagless text: already escaped by nh3, decode first.
                    description_a_convertir = description_actuelle
                    if not UNE_BALISE_HTML.search(description_actuelle):
                        description_a_convertir = module_html.unescape(description_actuelle)

                    description_reparee = normaliser_html_editeur(
                        clean_html(texte_brut_vers_html(description_a_convertir))
                    )
                    if description_reparee == description_actuelle:
                        continue

                    events_changes += 1
                    if passe_a_blanc:
                        if events_changes <= NOMBRE_D_EXEMPLES_PAR_LIEU:
                            self.stdout.write(f"  [{evenement.name}]")
                            self.stdout.write(f"    avant : {description_actuelle[:200]!r}")
                            self.stdout.write(f"    après : {description_reparee[:200]!r}")
                    else:
                        Event.objects.filter(pk=evenement.pk).update(
                            long_description=description_reparee
                        )

                if events_changes:
                    self.stdout.write(
                        f"{lieu.schema_name} : {events_lus} lus, {events_changes} changés"
                    )
                total_des_events_changes += events_changes

        if passe_a_blanc:
            self.stdout.write(
                self.style.WARNING(
                    f"Passe à blanc : {total_des_events_changes} events seraient changés. "
                    "Rien n'a été écrit."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"{total_des_events_changes} events réparés.")
            )
