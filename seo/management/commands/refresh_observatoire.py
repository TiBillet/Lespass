"""
Commande qui calcule l'observatoire des instances et range le resultat.
/ Command that computes the instance observatory and stores the result.

LOCALISATION : seo/management/commands/refresh_observatoire.py

Usage :
    python manage.py refresh_observatoire
    python manage.py refresh_observatoire --mois 36

QUI LA LANCE
- Le beat Celery, chaque nuit (`TiBillet/celery.py`, `cron_refresh_observatoire`,
  avec --par cron).
- Le mainteneur, a la main.
C'est le SEUL chemin qui lance le calcul : aucune vue, aucun bouton.
/ The nightly Celery beat, or the maintainer by hand. The ONLY way to compute.

FLUX :
1. `seo/observatoire.py` `calculer_observatoire_du_reseau()` lit tous les lieux.
2. Si au moins un lieu a ete lu, le resultat remplace l'ancien dans `SEOCache`
   (une ligne en base, sans expiration).
3. Si aucun lieu n'a ete lu, rien n'est ecrit et la commande echoue : le dernier
   bon calcul reste affiche, et l'erreur remonte (Sentry, logs Celery).
/ Compute, then replace the SEOCache row. No venue read: write nothing, fail.

La commande tourne depuis le schema public. Elle n'a pas besoin de choisir un
lieu : le calcul entre lui-meme dans chaque lieu avec tenant_context().
/ Runs from the public schema; the computation enters each venue itself.
"""

from django.core.management.base import BaseCommand, CommandError

from seo.models import SEOCache
from seo.observatoire import calculer_observatoire_du_reseau

# La page compare les 12 derniers mois aux 12 d'avant : il faut au moins 13 mois.
# / The page compares the last 12 months to the previous ones: 13 months minimum.
NOMBRE_DE_MOIS_MINIMUM = 13


class Command(BaseCommand):
    help = (
        "Calcule l'observatoire des instances et le range dans SEOCache "
        "/ Computes the instance observatory and stores it in SEOCache"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--mois",
            type=int,
            default=24,
            help="Nombre de mois d'historique (au moins 13) / Months of history (13 minimum)",
        )
        parser.add_argument(
            "--par",
            type=str,
            default="manage.py",
            choices=["manage.py", "cron"],
            help="Qui lance le calcul, affiche par la page / Who runs it, shown by the page",
        )

    def handle(self, *args, **options):
        nombre_de_mois = options["mois"]
        if nombre_de_mois < NOMBRE_DE_MOIS_MINIMUM:
            raise CommandError(
                f"--mois doit valoir au moins {NOMBRE_DE_MOIS_MINIMUM} "
                f"/ --mois must be at least {NOMBRE_DE_MOIS_MINIMUM}"
            )

        donnees_de_l_observatoire = calculer_observatoire_du_reseau(
            nombre_de_mois=nombre_de_mois,
            calcule_par=options["par"],
            journal=self.stderr.write,
        )

        # Garde-fou : un calcul qui n'a lu aucun lieu n'ecrase pas le dernier bon
        # calcul. C'est le cas d'une base injoignable ou d'une migration oubliee.
        # / Safety net: a run that read no venue never overwrites the last good one.
        aucun_lieu_lu = donnees_de_l_observatoire["bilan"]["lieux_lus"] == 0
        if aucun_lieu_lu:
            raise CommandError(
                "Aucun lieu lu : le cache de l'observatoire n'est pas modifié. "
                f"Bilan : {donnees_de_l_observatoire['bilan']} "
                "/ No venue read: the observatory cache is left unchanged."
            )

        SEOCache.objects.update_or_create(
            cache_type=SEOCache.OBSERVATOIRE,
            tenant=None,
            defaults={"data": donnees_de_l_observatoire},
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Observatoire enregistré : {donnees_de_l_observatoire['bilan']['lieux_lus']} lieux "
                "/ Observatory saved"
            )
        )
