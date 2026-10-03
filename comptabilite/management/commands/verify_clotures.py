"""
Management command : audit des clotures comptables.
/ Management command: audit accounting closures.

LOCALISATION : comptabilite/management/commands/verify_clotures.py

Usage :
    manage.py verify_clotures              # tous les tenants
    manage.py verify_clotures --tenant=lespass

Verifications :
1. Continuite des numero_sequentiel (pas de trou).
2. Chaine des clotures (`comptabilite/integrite.py` verifier_chaine_clotures) :
   empreinte recalculee vs stockee, previous_hmac = empreinte de la cloture d'avant.
3. Continuite des J (`comptabilite/integrite.py` verifier_continuite_des_journees) :
   la J n+1 commence ou la J n finit, et sa premiere vente suit la derniere de la J n.
4. Pour chaque J, la chaine des ventes de sa plage
   (`laboutik/integrity.py` verifier_chaine_ventes).

/ Checks:
1. numero_sequentiel continuity (no gaps).
2. The chain of closures (fingerprint, link to the previous closure).
3. Continuity of the J (no gap, no overlap, in time and in sale numbers).
4. For each J, the sales chain of its range.
"""
from django.core.management.base import BaseCommand
from django_tenants.utils import tenant_context


class Command(BaseCommand):
    help = "Audit des clotures comptables (continuite + hash chain)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant",
            default=None,
            help="schema_name d'un tenant precis (sinon : tous).",
        )

    def handle(self, *args, **opts):
        from Customers.models import Client

        if opts.get("tenant"):
            tenants = Client.objects.filter(schema_name=opts["tenant"])
            if not tenants.exists():
                self.stderr.write(f"Tenant {opts['tenant']} introuvable.")
                return
        else:
            tenants = Client.objects.exclude(schema_name="public")

        total_anomalies = 0

        for tenant in tenants:
            anomalies = self._verifier_tenant(tenant)
            total_anomalies += anomalies

        if total_anomalies == 0:
            self.stdout.write(self.style.SUCCESS(
                "\nAudit complet : aucune anomalie detectee."
            ))
        else:
            self.stdout.write(self.style.WARNING(
                f"\nAudit complet : {total_anomalies} anomalie(s) detectee(s)."
            ))

    def _verifier_tenant(self, tenant) -> int:
        """
        Verifie un tenant. Retourne le nombre d'anomalies trouvees.
        / Verify one tenant. Returns the number of anomalies found.
        """
        from comptabilite.integrite import (
            verifier_chaine_clotures,
            verifier_continuite_des_journees,
        )
        from comptabilite.models import ClotureCaisse
        from laboutik.integrity import verifier_chaine_ventes
        from laboutik.models import LaboutikConfiguration

        self.stdout.write(f"\n[tenant={tenant.schema_name}]")

        anomalies = 0

        with tenant_context(tenant):
            clotures = list(
                ClotureCaisse.objects
                .order_by("numero_sequentiel")
                .all()
            )

            if not clotures:
                self.stdout.write("  (aucune cloture)")
                return 0

            # 1. Continuite numero_sequentiel
            # / Sequential number continuity
            numeros_attendus = list(range(
                clotures[0].numero_sequentiel,
                clotures[-1].numero_sequentiel + 1,
            ))
            numeros_reels = [c.numero_sequentiel for c in clotures]
            trous = sorted(set(numeros_attendus) - set(numeros_reels))

            if trous:
                anomalies += len(trous)
                self.stdout.write(self.style.ERROR(
                    f"  trou(s) dans la sequence numero_sequentiel : "
                    f"numeros manquant(s) {trous}"
                ))
            else:
                self.stdout.write(self.style.SUCCESS(
                    f"  {len(clotures)} cloture(s), numeros "
                    f"{clotures[0].numero_sequentiel}-{clotures[-1].numero_sequentiel} continus"
                ))

            # 2. La chaine des clotures, tous niveaux.
            # / The chain of closures, every level.
            cle_du_lieu = LaboutikConfiguration.get_solo().get_or_create_hmac_key()
            anomalies_des_clotures = verifier_chaine_clotures(cle_du_lieu)
            for anomalie in anomalies_des_clotures:
                anomalies += 1
                self.stdout.write(self.style.ERROR(f"  {anomalie['raison']}"))

            # 3. La continuite des J : ni trou ni chevauchement.
            # / 3. Continuity of the J: no gap, no overlap.
            anomalies_de_continuite = verifier_continuite_des_journees()
            for anomalie in anomalies_de_continuite:
                anomalies += 1
                self.stdout.write(self.style.ERROR(f"  {anomalie['raison']}"))

            # 4. Pour chaque J, la chaine des ventes de sa plage.
            # / 4. For each J, the sales chain of its range.
            for cloture in clotures:
                cloture_journaliere_avec_ventes = (
                    cloture.niveau == ClotureCaisse.NIVEAU_JOURNALIER
                    and cloture.numero_premiere_vente is not None
                )
                if not cloture_journaliere_avec_ventes:
                    continue
                anomalies_des_ventes = verifier_chaine_ventes(
                    cle_du_lieu,
                    numero_de_la_premiere_vente=cloture.numero_premiere_vente,
                    numero_de_la_derniere_vente=cloture.numero_derniere_vente,
                )
                for anomalie in anomalies_des_ventes:
                    anomalies += 1
                    self.stdout.write(self.style.ERROR(
                        f"  clôture n° {cloture.numero_sequentiel} : {anomalie['raison']}"
                    ))

        return anomalies
