"""
Management command : audit des clotures comptables.
/ Management command: audit accounting closures.

LOCALISATION : comptabilite/management/commands/verify_clotures.py

Usage :
    manage.py verify_clotures              # tous les tenants
    manage.py verify_clotures --tenant=lespass

Verifications :
1. Continuite des numero_sequentiel (pas de trou).
2. hash_lignes recalcule vs stocke (detection de modification post-cloture).

/ Checks:
1. numero_sequentiel continuity (no gaps).
2. hash_lignes recompute vs stored (detect post-closure tampering).
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
        from comptabilite.models import ClotureCaisse
        from comptabilite.services import RapportComptableService

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

            # 2. Hash chain (recalcul vs stocke)
            # / Hash chain (recompute vs stored)
            for cloture in clotures:
                # Si pas de hash stocke, on ignore (anciennes clotures)
                # / Skip if no stored hash (legacy clotures)
                if not cloture.hash_lignes:
                    continue
                service = RapportComptableService(
                    cloture.datetime_debut, cloture.datetime_fin,
                )
                hash_recalcule = service.calculer_hash_lignes()
                if hash_recalcule != cloture.hash_lignes:
                    anomalies += 1
                    self.stdout.write(self.style.ERROR(
                        f"  cloture #{cloture.numero_sequentiel} : "
                        f"hash invalide (mismatch — lignes modifiees post-cloture ?)"
                    ))

        return anomalies
