"""
Déclare à l'ancien Fedow toutes les cartes primaires existantes d'un lieu.
/ Declares every existing primary card of a venue to the old Fedow.

LOCALISATION : laboutik/management/commands/declarer_cartes_primaires_ancien_fedow.py

Une carte primaire est déclarée à l'ancien Fedow quand elle est créée par l'admin ou
par `create_test_pos_data` (laboutik/carte_primaire_ancien_fedow.py). Les cartes
primaires créées autrement, ou avant ce mécanisme, ne le sont pas : l'ancien Fedow
refuse alors les vidages qu'elles signent. Cette commande les rattrape.
/ Primary cards created otherwise, or before the mechanism, are not declared: this
command catches them up.

IDEMPOTENTE : une carte déjà déclarée répond 208, sans erreur.
/ Idempotent: an already declared card answers 208.

Deux modes :
- `--a-blanc` (par défaut) : liste les cartes primaires du lieu, n'envoie RIEN ;
- `--appliquer` : déclare chaque carte primaire, une fois. Un refus n'arrête pas les
  autres cartes : il est écrit dans la sortie d'erreur, avec le tag et le détail.
/ `--a-blanc` (default) lists without sending anything; `--appliquer` declares.

Usage :
    docker exec lespass_django poetry run python /DjangoFiles/manage.py \\
        declarer_cartes_primaires_ancien_fedow --schema lespass
    docker exec lespass_django poetry run python /DjangoFiles/manage.py \\
        declarer_cartes_primaires_ancien_fedow --schema lespass --appliquer
"""

from django.core.management.base import BaseCommand, CommandError
from django_tenants.utils import tenant_context

from Customers.models import Client
from fedow_connect.fedow_api import CarteInconnueDeFedow
from fedow_connect.models import FedowConfig
from laboutik.carte_primaire_ancien_fedow import declarer_la_carte_primaire_a_l_ancien_fedow
from laboutik.models import CartePrimaire


class Command(BaseCommand):
    help = (
        "Déclare à l'ancien Fedow les cartes primaires existantes d'un lieu. "
        "Passage à blanc par défaut ; --appliquer pour envoyer."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--schema",
            required=True,
            help="Schéma du lieu (ex : lespass).",
        )
        modes = parser.add_mutually_exclusive_group()
        modes.add_argument(
            "--a-blanc",
            action="store_true",
            help="Liste les cartes primaires sans rien envoyer (mode par défaut).",
        )
        modes.add_argument(
            "--appliquer",
            action="store_true",
            help="Déclare chaque carte primaire à l'ancien Fedow.",
        )

    def handle(self, *args, **options):
        nom_du_schema = options["schema"]
        lieu = Client.objects.filter(schema_name=nom_du_schema).first()
        if lieu is None:
            raise CommandError(f"Lieu introuvable : {nom_du_schema}")

        # Les cartes primaires sont des données du lieu : tout se lit dans son schéma.
        # / Primary cards are venue data: everything is read in its schema.
        with tenant_context(lieu):
            cartes_primaires_du_lieu = list(
                CartePrimaire.objects.select_related("carte").order_by("carte__tag_id")
            )
            lieu_relie_a_l_ancien_fedow = FedowConfig.get_solo().can_fedow()

            self.stdout.write(
                f"Lieu {lieu.schema_name} : {len(cartes_primaires_du_lieu)} carte(s) "
                f"primaire(s). Relié à l'ancien Fedow : "
                f"{'oui' if lieu_relie_a_l_ancien_fedow else 'non'}."
            )
            for carte_primaire in cartes_primaires_du_lieu:
                self.stdout.write(
                    f"  - {carte_primaire.carte.tag_id} (n° {carte_primaire.carte.number})"
                )

            if not lieu_relie_a_l_ancien_fedow:
                self.stdout.write("Lieu non relié à l'ancien Fedow : rien à déclarer.")
                return

            if not options["appliquer"]:
                self.stdout.write(
                    "Passage à blanc : rien n'est envoyé. Relancer avec --appliquer."
                )
                return

            nombre_de_cartes_declarees = 0
            nombre_de_cartes_refusees = 0
            for carte_primaire in cartes_primaires_du_lieu:
                tag_de_la_carte = carte_primaire.carte.tag_id
                try:
                    declarer_la_carte_primaire_a_l_ancien_fedow(carte_primaire.carte)
                    nombre_de_cartes_declarees += 1
                    self.stdout.write(f"  {tag_de_la_carte} : déclarée.")

                except CarteInconnueDeFedow:
                    nombre_de_cartes_refusees += 1
                    self.stderr.write(
                        f"  {tag_de_la_carte} : INCONNUE de l'ancien Fedow, non déclarée "
                        "(la créer d'abord dans l'admin des cartes)."
                    )

                except Exception as erreur_de_l_ancien_fedow:
                    nombre_de_cartes_refusees += 1
                    self.stderr.write(
                        f"  {tag_de_la_carte} : REFUSÉE par l'ancien Fedow. "
                        f"Détail : {erreur_de_l_ancien_fedow}"
                    )

            self.stdout.write(
                f"Terminé : {nombre_de_cartes_declarees} déclarée(s), "
                f"{nombre_de_cartes_refusees} refusée(s)."
            )
