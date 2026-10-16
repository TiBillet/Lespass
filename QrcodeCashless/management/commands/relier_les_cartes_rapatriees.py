"""
Relie à leur propriétaire les cartes locales d'un lieu que l'ancien Fedow dit liées.
/ Links to their owner the venue's local cards that the old Fedow says are linked.

LOCALISATION : QrcodeCashless/management/commands/relier_les_cartes_rapatriees.py

Une carte locale (`CarteCashless`) peut être sans propriétaire alors que l'ancien Fedow
la dit liée à une personne. C'est le cas des cartes rapatriées au premier scan, ou
liées par QR code avant d'exister ici, avant que le rapatriement et la liaison ne
posent la propriétaire (QrcodeCashless/services.py, `fabriquer_le_miroir_de_la_carte`).
Cette commande les rattrape, carte par carte.
/ Catches up local cards left without owner while the old Fedow says they are linked.

POUR CHAQUE CARTE SANS PROPRIÉTAIRE ÉMISE PAR LE LIEU :
1. On lit sa fiche chez l'ancien Fedow (`GET card/{tag_id}/`).
2. Carte anonyme là-bas (portefeuille éphémère) : rien à faire.
3. Carte liée là-bas à une personne connue ici (même uuid de portefeuille) : on la lie
   en local (`CarteService.lier_a_user` : transactionnel et idempotent).
4. Personne inconnue ici, carte inconnue de l'ancien Fedow, ou refus local : signalé.

Deux modes :
- par défaut, passage à blanc : liste ce qui serait fait, n'écrit RIEN ;
- `--executer` : lie chaque carte. Un refus n'arrête pas les autres cartes : il est écrit
  dans la sortie d'erreur, avec le tag et le détail.
/ Dry run by default; --executer writes. A refusal never stops the other cards.

Usage :
    docker exec lespass_django poetry run python /DjangoFiles/manage.py \\
        relier_les_cartes_rapatriees --schema lespass
    docker exec lespass_django poetry run python /DjangoFiles/manage.py \\
        relier_les_cartes_rapatriees --schema lespass --executer

Spec : TECH_DOC/SESSIONS/QRCODECASHLESS/CHANTIER-03-fed-invisible-en-caisse.md (C-2)
"""

from django.core.management.base import BaseCommand, CommandError
from django_tenants.utils import tenant_context

from Customers.models import Client
from QrcodeCashless.models import CarteCashless
from QrcodeCashless.services import proprietaire_d_apres_la_fiche_fedow
from fedow_connect.fedow_api import CarteInconnueDeFedow, FedowAPI
from fedow_connect.models import FedowConfig
from fedow_core.services import CarteService


class Command(BaseCommand):
    help = (
        "Relie à leur propriétaire les cartes locales d'un lieu que l'ancien Fedow "
        "dit liées. Passage à blanc par défaut ; --executer pour écrire."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--schema",
            required=True,
            help="Schéma du lieu (ex : lespass).",
        )
        parser.add_argument(
            "--executer",
            action="store_true",
            help="Lie chaque carte en local. Sans ce drapeau, rien n'est écrit.",
        )

    def handle(self, *args, **options):
        nom_du_schema = options["schema"]
        lieu = Client.objects.filter(schema_name=nom_du_schema).first()
        if lieu is None:
            raise CommandError(f"Lieu introuvable : {nom_du_schema}")

        executer = options["executer"]

        # FedowConfig est une donnée du lieu : tout se lit dans son schéma.
        # / FedowConfig is venue data: everything is read in its schema.
        with tenant_context(lieu):
            # can_fedow() AVANT FedowAPI() : sinon, sur un lieu sans place, la création
            # du client lancerait une création de place chez l'ancien Fedow.
            # / can_fedow() BEFORE FedowAPI(): otherwise a place would be created.
            if not FedowConfig.get_solo().can_fedow():
                self.stdout.write(
                    f"Lieu {lieu.schema_name} non relié à l'ancien Fedow : rien à faire."
                )
                return

            cartes_sans_proprietaire = list(
                CarteCashless.objects.filter(
                    user__isnull=True, detail__origine=lieu
                ).order_by("tag_id")
            )
            self.stdout.write(
                f"Lieu {lieu.schema_name} : {len(cartes_sans_proprietaire)} carte(s) "
                f"sans propriétaire."
            )

            client_de_l_ancien_fedow = FedowAPI()
            nombre_de_cartes_a_relier = 0
            nombre_de_cartes_reliees = 0
            nombre_de_cartes_anonymes = 0
            nombre_de_cartes_en_erreur = 0

            for carte in cartes_sans_proprietaire:
                # 1. La fiche de la carte chez l'ancien Fedow.
                # / 1. The card's record on the old Fedow.
                try:
                    fiche_de_la_carte = client_de_l_ancien_fedow.NFCcard.retrieve(
                        carte.tag_id
                    )
                except CarteInconnueDeFedow:
                    nombre_de_cartes_en_erreur += 1
                    self.stderr.write(f"  {carte.tag_id} : inconnue de l'ancien Fedow.")
                    continue
                except Exception as erreur_de_lecture:
                    nombre_de_cartes_en_erreur += 1
                    self.stderr.write(
                        f"  {carte.tag_id} : lecture impossible chez l'ancien Fedow. "
                        f"Détail : {erreur_de_lecture}"
                    )
                    continue

                # 2. Carte anonyme là-bas : rien à faire.
                # / 2. Anonymous there: nothing to do.
                if fiche_de_la_carte["is_wallet_ephemere"]:
                    nombre_de_cartes_anonymes += 1
                    continue

                # 3. La personne, retrouvée ici par l'uuid de son portefeuille.
                # / 3. The person, found here by their wallet uuid.
                proprietaire = proprietaire_d_apres_la_fiche_fedow(fiche_de_la_carte)
                if proprietaire is None:
                    nombre_de_cartes_en_erreur += 1
                    self.stderr.write(
                        f"  {carte.tag_id} : liée chez l'ancien Fedow au portefeuille "
                        f"{fiche_de_la_carte['wallet']['uuid']}, personne inconnue ici."
                    )
                    continue

                nombre_de_cartes_a_relier += 1
                if not executer:
                    self.stdout.write(
                        f"  {carte.tag_id} : à relier à {proprietaire.email}."
                    )
                    continue

                try:
                    CarteService.lier_a_user(qrcode_uuid=carte.uuid, user=proprietaire)
                    nombre_de_cartes_reliees += 1
                    self.stdout.write(
                        f"  {carte.tag_id} : reliée à {proprietaire.email}."
                    )
                except Exception as erreur_de_liaison:
                    nombre_de_cartes_en_erreur += 1
                    self.stderr.write(
                        f"  {carte.tag_id} : liaison locale refusée pour "
                        f"{proprietaire.email}. Détail : "
                        f"{type(erreur_de_liaison).__name__} {erreur_de_liaison}"
                    )

            self.stdout.write(
                f"Terminé : {nombre_de_cartes_a_relier} à relier, "
                f"{nombre_de_cartes_reliees} reliée(s), "
                f"{nombre_de_cartes_anonymes} anonyme(s) chez l'ancien Fedow, "
                f"{nombre_de_cartes_en_erreur} en erreur."
            )
            if not executer:
                self.stdout.write(
                    "Passage à blanc : rien n'est écrit. Relancer avec --executer."
                )
