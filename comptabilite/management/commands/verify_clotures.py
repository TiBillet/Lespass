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

La cle HMAC du lieu est lue, jamais creee : des clotures sans cle sont une anomalie.
Seule ecriture possible : `LaboutikConfiguration.get_solo()` cree la ligne du
singleton (vide, sans cle) si le lieu ne l'a pas encore.
Une erreur sur un lieu est une anomalie ; l'audit des autres lieux continue.

Code de sortie : 0 sans anomalie ; au moins une anomalie, ou un `--tenant` inconnu
→ `CommandError`, code 1.

/ Checks:
1. numero_sequentiel continuity (no gaps).
2. The chain of closures (fingerprint, link to the previous closure).
3. Continuity of the J (no gap, no overlap, in time and in sale numbers).
4. For each J, the sales chain of its range.
"""
from django.core.management.base import BaseCommand, CommandError
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
            tenants = list(Client.objects.filter(schema_name=opts["tenant"]))
            if not tenants:
                raise CommandError(f"Tenant {opts['tenant']} introuvable.")
        else:
            tenants = list(Client.objects.exclude(schema_name="public"))

        total_anomalies = 0

        for tenant in tenants:
            # Une erreur sur un lieu ne bloque pas les autres : elle compte comme une
            # anomalie, et elle est écrite.
            # / An error on one venue does not stop the others: it is an anomaly.
            try:
                anomalies = self._verifier_tenant(tenant)
            except Exception as erreur_du_lieu:
                anomalies = 1
                self.stdout.write(self.style.ERROR(
                    f"  [tenant={tenant.schema_name}] Erreur pendant l'audit : "
                    f"{erreur_du_lieu}"
                ))
            total_anomalies += anomalies

        if total_anomalies == 0:
            self.stdout.write(self.style.SUCCESS(
                "\nAudit complet : aucune anomalie detectee."
            ))
            return

        # Au moins une anomalie : la commande sort avec le code 1 (`CommandError`),
        # pour qu'une tache planifiee ou un script voie l'alerte sans lire le texte.
        # / At least one anomaly: exit code 1, so a scheduler or a script sees it.
        self.stdout.write(self.style.WARNING(
            f"\nAudit complet : {total_anomalies} anomalie(s) detectee(s)."
        ))
        raise CommandError(
            f"Audit des clotures : {total_anomalies} anomalie(s) detectee(s)."
        )

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

            # 2. La chaine des clotures, tous niveaux. La cle est LUE, jamais creee
            #    (`get_solo()` peut seulement creer la ligne vide du singleton). Des
            #    clotures sans cle : la cle a disparu, les empreintes ne peuvent plus
            #    etre verifiees, c'est une anomalie.
            # / 2. The chain of closures. The key is read, never created (get_solo()
            #    may only create the empty singleton row); closures without a key is
            #    an anomaly.
            cle_du_lieu = LaboutikConfiguration.get_solo().get_hmac_key()
            if not cle_du_lieu:
                self.stdout.write(self.style.ERROR(
                    "  Pas de cle HMAC alors que des clotures existent : "
                    "empreintes invérifiables."
                ))
                return anomalies + 1
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
