"""
Management command : generer une cloture manuellement.
/ Manually generate a closure.

LOCALISATION : comptabilite/management/commands/generer_cloture.py

Usage :
    manage.py generer_cloture --niveau=J
    manage.py generer_cloture --niveau=J --tenant=lespass
    manage.py generer_cloture --niveau=M
    manage.py generer_cloture --niveau=M \\
        --datetime-debut=2026-04-01T00:00:00+02:00 \\
        --datetime-fin=2026-05-01T00:00:00+02:00

J : la journee glissante, de la fin de la J precedente a maintenant (aucune borne :
elles viennent de la J precedente). Rien n'est cree sans vente depuis la J precedente.
H / M / A : la periode precedente en heure locale du lieu, ou les bornes donnees.
Des bornes donnees portent un fuseau et sont une vraie semaine / un vrai mois / une
vraie annee du lieu, en heure locale (sinon : refus pour ce lieu). Rien n'est cree pour
une periode sans vente ou deja cloturee.
Une erreur dans un lieu n'arrete pas les autres ; la commande finit alors en erreur.
/ J: the sliding day, no bounds. H / M / A: the previous period in local time, or the
given bounds (with a time zone, the venue's real local period). Nothing is created
without sales. An error in one venue does not stop the others; the command then fails.
"""
import logging

from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Genere une cloture comptable pour un ou tous les tenants."

    def add_arguments(self, parser):
        parser.add_argument(
            "--niveau",
            choices=["J", "H", "M", "A"],
            required=True,
            help="Niveau de cloture : J (jour), H (semaine), M (mois), A (annee).",
        )
        parser.add_argument(
            "--tenant",
            default=None,
            help="schema_name d'un tenant precis. Si absent, tous les tenants.",
        )
        parser.add_argument(
            "--datetime-debut",
            default=None,
            help="H / M / A seulement : ISO datetime debut (sinon la periode precedente).",
        )
        parser.add_argument(
            "--datetime-fin",
            default=None,
            help="H / M / A seulement : ISO datetime fin (sinon la periode precedente).",
        )

    def handle(self, *args, **opts):
        from Customers.models import Client
        from comptabilite.tasks import generer_cloture_pour_tenant

        # La J est glissante : ses bornes viennent de la J precedente et du moment
        # present, jamais de la ligne de commande.
        # / The J is sliding: its bounds never come from the command line.
        bornes_donnees = opts.get("datetime_debut") or opts.get("datetime_fin")
        if opts["niveau"] == "J" and bornes_donnees:
            raise CommandError(
                "La cloture J n'accepte pas de bornes : elle va de la fin de la J "
                "precedente au moment present."
            )

        if opts.get("tenant"):
            tenants = list(Client.objects.filter(schema_name=opts["tenant"]))
            if not tenants:
                self.stderr.write(f"Tenant {opts['tenant']} introuvable.")
                return
        else:
            tenants = list(Client.objects.exclude(schema_name="public"))

        # Une erreur dans un lieu est ecrite et n'arrete pas les suivants. La commande
        # finit en erreur (code de sortie non nul) s'il y en a eu au moins une.
        # / An error in one venue is written and does not stop the next ones; the
        # command ends in error if there was at least one.
        lieux_en_erreur = []
        for tenant in tenants:
            self.stdout.write(
                f"-> {tenant.schema_name} (niveau={opts['niveau']})"
            )
            try:
                uuid_str = generer_cloture_pour_tenant(
                    schema_name=tenant.schema_name,
                    niveau=opts["niveau"],
                    datetime_debut_iso=opts.get("datetime_debut"),
                    datetime_fin_iso=opts.get("datetime_fin"),
                )
            except Exception as erreur_du_lieu:
                logger.exception(f"[{tenant.schema_name}] Echec de generer_cloture.")
                self.stderr.write(f"   [{tenant.schema_name}] erreur : {erreur_du_lieu}")
                lieux_en_erreur.append(tenant.schema_name)
                continue

            if uuid_str:
                self.stdout.write(self.style.SUCCESS(f"   cloture {uuid_str}"))
            else:
                self.stdout.write(
                    self.style.WARNING(
                        "   rien a cloturer (aucune vente, ou periode deja cloturee)"
                    )
                )

        if lieux_en_erreur:
            raise CommandError(
                f"{len(lieux_en_erreur)} lieu(x) en erreur : {', '.join(lieux_en_erreur)}"
            )
