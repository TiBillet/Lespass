"""
Management command pour verifier l'integrite des ventes et des clotures des lieux.
/ Management command to verify the integrity of the venues' sales and closures.

LOCALISATION : laboutik/management/commands/verify_integrity.py

Usage :
    docker exec lespass_django poetry run python manage.py verify_integrity
    docker exec lespass_django poetry run python manage.py verify_integrity --schema=lespass

Sans --schema, TOUS les lieux sont verifies (comme verify_clotures).

CE QUE LA COMMANDE VERIFIE, POUR CHAQUE LIEU :
1. La chaine des ventes reglees (`laboutik/integrity.py` verifier_chaine_ventes) :
   numeros sans trou, maillons, empreintes recalculees, les deux egalites.
2. La chaine des clotures (`comptabilite/integrite.py` verifier_chaine_clotures) :
   empreinte recalculee, lien avec la cloture d'avant.
La cle HMAC du lieu est LUE (`get_hmac_key`), jamais creee. Seule ecriture
possible : `LaboutikConfiguration.get_solo()` cree la ligne du singleton (vide,
sans cle) si le lieu ne l'a pas encore. Un lieu sans cle et
sans vente scellee n'a rien a verifier ; un lieu sans cle avec des ventes scellees
est une anomalie (la cle a disparu). Une erreur sur un lieu est une anomalie : la
verification des autres lieux continue.

CODE DE SORTIE : 0 si tout est sain. Au moins une anomalie, ou aucun lieu a
verifier : la commande leve `CommandError` et sort avec le code 1. Une tache
planifiee ou un script voit l'alerte sans lire le texte.
/ Checks the sales chain and the closures chain of every venue (or one). The key is
read, never created; `get_solo()` may create the empty singleton row. Exit code 0
when sound, 1 on any anomaly or without any venue.
"""
from django.core.management.base import BaseCommand, CommandError
from django_tenants.utils import tenant_context


class Command(BaseCommand):
    help = (
        "Verifie la chaine des ventes et la chaine des clotures des lieux "
        "/ Verifies the sales chain and the closures chain of the venues"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--schema', type=str, default=None,
            help='Schema du lieu a verifier (defaut : tous les lieux)',
        )

    def handle(self, *args, **options):
        from Customers.models import Client

        schema_demande = options['schema']
        if schema_demande:
            lieux_a_verifier = list(Client.objects.filter(schema_name=schema_demande))
        else:
            lieux_a_verifier = list(Client.objects.exclude(schema_name='public'))

        if not lieux_a_verifier:
            raise CommandError(
                f"Aucun lieu a verifier (schema demande : {schema_demande or 'tous'})."
            )

        nombre_total_d_anomalies = 0
        for lieu in lieux_a_verifier:
            # Une erreur sur un lieu ne bloque pas les autres : elle compte comme une
            # anomalie, et elle est ecrite.
            # / An error on one venue does not stop the others: it is an anomaly.
            try:
                nombre_total_d_anomalies += self._verifier_le_lieu(lieu)
            except Exception as erreur_du_lieu:
                nombre_total_d_anomalies += 1
                self.stdout.write(self.style.ERROR(
                    f"[{lieu.schema_name}] Erreur pendant la verification : "
                    f"{erreur_du_lieu}"
                ))

        if nombre_total_d_anomalies == 0:
            self.stdout.write(self.style.SUCCESS(
                "CHAINES INTEGRES — ventes et clotures verifiees, 0 anomalie"
            ))
            return

        raise CommandError(
            f"{nombre_total_d_anomalies} anomalie(s) d'integrite detectee(s)."
        )

    def _verifier_le_lieu(self, lieu):
        """
        Verifie les chaines d'un lieu et ecrit ses anomalies. Rend leur nombre.
        / Verifies one venue's chains, writes its anomalies, returns their count.
        """
        from BaseBillet.models_vente import Vente
        from comptabilite.integrite import verifier_chaine_clotures
        from comptabilite.models import ClotureCaisse
        from laboutik.integrity import verifier_chaine_ventes
        from laboutik.models import LaboutikConfiguration

        schema = lieu.schema_name
        with tenant_context(lieu):
            cle = LaboutikConfiguration.get_solo().get_hmac_key()
            ventes_scellees = Vente.objects.filter(
                statut=Vente.Statut.REGLEE,
            ).exclude(hmac_hash='')

            # Sans cle : rien a verifier si rien n'est scelle ; sinon la cle a
            # disparu, c'est une anomalie.
            # / Without a key: nothing to verify if nothing is sealed; otherwise an
            # anomaly (the key is gone).
            if not cle:
                if ventes_scellees.exists():
                    self.stdout.write(self.style.ERROR(
                        f"[{schema}] Pas de cle HMAC alors que des ventes sont "
                        f"scellees : verification impossible."
                    ))
                    return 1
                self.stdout.write(self.style.WARNING(
                    f"[{schema}] Pas de cle HMAC, aucune vente scellee : rien a verifier."
                ))
                return 0

            nombre_de_ventes_reglees = Vente.objects.filter(
                statut=Vente.Statut.REGLEE,
            ).count()
            nombre_de_clotures = ClotureCaisse.objects.count()
            self.stdout.write(
                f"[{schema}] {nombre_de_ventes_reglees} vente(s) reglee(s), "
                f"{nombre_de_clotures} cloture(s)"
            )

            anomalies_des_ventes = verifier_chaine_ventes(cle)
            anomalies_des_clotures = verifier_chaine_clotures(cle)

        anomalies = anomalies_des_ventes + anomalies_des_clotures
        if not anomalies:
            return 0

        self.stdout.write(self.style.ERROR(
            f"  [{schema}] ALERTE — {len(anomalies)} anomalie(s) d'integrite :"
        ))
        for anomalie in anomalies:
            self.stdout.write(f"    - {anomalie['raison']}")
        return len(anomalies)
