"""
La J « reprise » : une clôture journalière par lieu qui couvre tout l'historique des
ventes, créée la nuit de la bascule, après la reprise des ventes.
/ The "reprise" J: one daily closure per venue covering the whole sales history,
created on the switch night, after the sales takeover.

LOCALISATION : comptabilite/management/commands/creer_la_cloture_de_reprise.py

USAGE
    docker exec lespass_django poetry run python /DjangoFiles/manage.py \\
        creer_la_cloture_de_reprise [--schema <schéma du lieu>]

Sans `--schema`, tous les lieux (hors schéma public), l'un après l'autre.
/ Without --schema, every venue.

POUR CHAQUE LIEU
- Le lieu a déjà sa J reprise : rien n'est fait (la commande se rejoue sans risque).
- Le lieu a déjà une J ordinaire, sans J reprise : REFUSÉ, avec un message. La J
  partirait de la fin de cette J et ne couvrirait pas tout l'historique.
- Le lieu n'a aucune vente réglée : aucune J.
- Sinon : la J reprise est créée, de la première vente réglée du lieu jusqu'au moment
  de la commande. Elle porte le total perpétuel de tout l'historique, comme une J
  normale, et `"reprise": true` dans l'en-tête de son rapport (posé avant l'empreinte).
  Sa fin est la MISE EN SERVICE de la comptabilité du lieu
  (`comptabilite.tasks.mise_en_service_du_lieu`).
Un lieu refusé ou en erreur n'arrête pas les suivants. La commande finit en erreur
(code de sortie non nul) s'il y a eu au moins une erreur ; un refus n'en est pas une.
/ Per venue: already done → nothing; ordinary J present → refused with a message; no
settled sale → no J; otherwise the "reprise" J is created. An error or a refusal does
not stop the next venues; the command fails only on errors.

CE QUE LA COMMANDE NE FAIT PAS
- Aucun mail : elle ne passe pas par `generer_cloture_pour_tenant`, qui demande le mail.
- Aucune tâche Celery : elle tourne ici même, synchrone (la limite de 30 min d'une
  tâche Celery ne la coupe pas).
- Aucune semaine, aucun mois, aucune année : la tâche horaire les rattrape ensuite,
  12 au plus par passage.
/ No e-mail, no Celery task (synchronous), no H / M / A.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-R-reprise-ventes.md (§11.1,
§12 étape 10).
"""

import logging

from django.core.management.base import BaseCommand, CommandError
from django_tenants.utils import get_public_schema_name, tenant_context

from comptabilite.models import ClotureCaisse
from comptabilite.tasks import _creer_la_cloture_journaliere, la_j_de_reprise_du_lieu
from Customers.models import Client

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Crée la J « reprise » de chaque lieu : une clôture journalière qui couvre "
        "tout l'historique des ventes (nuit de la bascule)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--schema",
            default=None,
            help="Le schéma d'un seul lieu. Sans cette option : tous les lieux.",
        )

    def handle(self, *args, **options):
        schema_demande = options["schema"]
        if schema_demande:
            lieux_a_cloturer = list(Client.objects.filter(schema_name=schema_demande))
            if not lieux_a_cloturer:
                raise CommandError(f"Aucun lieu pour le schéma « {schema_demande} ».")
        else:
            lieux_a_cloturer = list(
                Client.objects.exclude(schema_name=get_public_schema_name()).order_by(
                    "schema_name"
                )
            )

        # Une erreur dans un lieu est écrite et n'arrête pas les suivants.
        # / An error in one venue is written and does not stop the next ones.
        lieux_en_erreur = []
        for lieu in lieux_a_cloturer:
            try:
                with tenant_context(lieu):
                    self._creer_la_j_de_reprise_du_lieu(lieu)
            except Exception as erreur_du_lieu:
                logger.exception(f"[{lieu.schema_name}] Échec de la J reprise.")
                self.stderr.write(
                    self.style.ERROR(
                        f"Lieu {lieu.schema_name} : erreur : {erreur_du_lieu}"
                    )
                )
                lieux_en_erreur.append(lieu.schema_name)

        if lieux_en_erreur:
            raise CommandError(
                f"{len(lieux_en_erreur)} lieu(x) en erreur : {', '.join(lieux_en_erreur)}"
            )

    def _creer_la_j_de_reprise_du_lieu(self, lieu):
        """
        Crée la J reprise du lieu courant, ou dit pourquoi elle n'est pas créée.
        À appeler dans le `tenant_context` du lieu, HORS de toute transaction (la J
        prend un verrou court dans une transaction durable).
        / Creates the current venue's "reprise" J, or says why not. Outside any
        transaction.
        """
        # Déjà faite : la commande se rejoue sans rien créer.
        # / Already done: replaying creates nothing.
        j_de_reprise_existante = la_j_de_reprise_du_lieu()
        if j_de_reprise_existante is not None:
            self.stdout.write(
                f"Lieu {lieu.schema_name} : J reprise déjà faite "
                f"(clôture n° {j_de_reprise_existante.numero_sequentiel}), rien à faire."
            )
            return

        # Une J ordinaire existe déjà : la J reprise partirait de sa fin, l'historique
        # d'avant ne serait pas couvert. Refus, et passage au lieu suivant.
        # / An ordinary J exists: the "reprise" J would start at its end. Refused.
        j_ordinaire_existante = ClotureCaisse.derniere_journaliere()
        if j_ordinaire_existante is not None:
            self.stderr.write(
                self.style.ERROR(
                    f"Lieu {lieu.schema_name} : J reprise refusée : le lieu a déjà une "
                    f"clôture journalière ordinaire (n° "
                    f"{j_ordinaire_existante.numero_sequentiel}). La J reprise partirait "
                    f"de sa fin et ne couvrirait pas tout l'historique."
                )
            )
            return

        j_de_reprise = _creer_la_cloture_journaliere(reprise=True)
        if j_de_reprise is None:
            self.stdout.write(
                f"Lieu {lieu.schema_name} : aucune vente réglée, aucune J reprise."
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"Lieu {lieu.schema_name} : J reprise n° "
                f"{j_de_reprise.numero_sequentiel} créée, du "
                f"{j_de_reprise.datetime_debut.isoformat()} au "
                f"{j_de_reprise.datetime_fin.isoformat()} "
                f"({j_de_reprise.nombre_transactions} ventes, "
                f"total {j_de_reprise.total_general} centimes)."
            )
        )
