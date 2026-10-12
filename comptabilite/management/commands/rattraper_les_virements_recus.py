"""
Le rattrapage des virements reçus : chaque paiement Stripe `T` validé et sans vente
reçoit sa vente « virement reçu ». Passage à blanc par défaut, écriture avec
`--executer`.
/ Catch-up of received transfers: each validated T payment without a sale gets its
"transfer received" sale. Dry run by default, writing with --executer.

LOCALISATION : comptabilite/management/commands/rattraper_les_virements_recus.py

USAGE
    docker exec lespass_django poetry run python /DjangoFiles/manage.py \\
        rattraper_les_virements_recus [--schema <schéma du lieu>] [--executer]

Sans `--schema`, tous les lieux (hors schéma public), l'un après l'autre.
Sans `--executer`, rien n'est écrit (passage à blanc).
/ Without --schema, every venue. Without --executer, nothing is written.

LES PAIEMENTS RATTRAPÉS
Les paiements de source `T` (webhook Stripe `transfer.created`), validés, sans vente
et sans ligne : le même filtre que la reprise (`BaseBillet/reprise_des_ventes.py`).
Leur montant et leur date sont lus dans `metadata_stripe`. La vente est écrite par la
fabrique commune `ecrire_la_vente_d_un_virement_recu` (BaseBillet/services_vente.py),
avec la clé `virement-recu-<uuid du paiement>`, celle du webhook : un paiement n'a
jamais deux ventes. Une transaction par vente : une erreur sur un paiement est comptée,
et la commande passe au suivant.
/ Validated T payments without a sale; one transaction per sale; an error is counted
and the command goes on.

LA DATE DE LA VENTE
La date du transfert si elle est APRÈS la fin de la dernière clôture du lieu, tous
niveaux confondus (J, H, M, A : le plus grand `datetime_fin` de
`comptabilite.models.ClotureCaisse`, la seule clôture du lieu). Sinon « maintenant » :
une vente datée dans une période déjà clôturée n'entrerait dans aucune J (la suivante
commence à la fin de la précédente), et resterait hors des totaux perpétuels.
/ The transfer date if after the end of the last closure (any level), else "now".

LE RAPPORT
Des nombres, des montants, des schémas et des domaines seulement : jamais le texte de
`metadata`, ni nom, ni mail. Un bloc par lieu qui a au moins un paiement à rattraper,
puis le total :
- paiements trouvés (les illisibles compris) ;
- montant (euros) : la somme des montants LISIBLES seulement ;
- illisibles : `metadata` sans montant ni date lisibles, aucune vente écrite ;
- à blanc : ventes à écrire, et ventes à dater maintenant (période close) ;
- avec `--executer` : ventes écrites, ventes datées maintenant (période close), erreurs.
Une erreur est aussi écrite sur la sortie d'erreur : schéma, uuid court du paiement et
type d'erreur. Un paiement `T` n'a pas d'utilisateur : son uuid n'est pas une donnée
personnelle.
/ Numbers, amounts, schemas and domains only; an error line names the payment uuid.

CE QUE LA COMMANDE NE FAIT PAS
Aucune requête réseau (ni Stripe, ni Fedow, ni ancien LaBoutik), aucune tâche Celery,
aucun mail. Elle n'appelle jamais `reprendre_les_ventes_existantes` : la reprise refuse
un lieu qui a déjà des ventes hors reprise.
/ No network call, no Celery task, no mail; never calls the takeover command.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Max
from django_tenants.utils import get_public_schema_name, tenant_context

from BaseBillet.models import Paiement_stripe
from BaseBillet.services_vente import (
    PREFIXE_DE_LA_CLE_D_UN_VIREMENT_RECU,
    ecrire_la_vente_d_un_virement_recu,
    montant_et_date_du_transfert,
)
from comptabilite.models import ClotureCaisse
from Customers.models import Client


def _en_euros(montant_en_centimes):
    """
    Un montant en centimes, affiché en euros à deux décimales. Affichage seulement.
    / A cent amount shown in euros. Display only.
    """
    montant_en_euros = Decimal(montant_en_centimes) / Decimal(100)
    return montant_en_euros.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _nouveau_compte():
    """Les compteurs d'un lieu, ou du total, à zéro. / Counters at zero."""
    return {
        "paiements_trouves": 0,
        "montant": 0,
        "illisibles": 0,
        "ventes_a_ecrire": 0,
        "ventes_ecrites": 0,
        "ventes_datees_maintenant": 0,
        "erreurs": 0,
    }


def _ajouter_au_total(compte_total, compte_du_lieu):
    """Ajoute les compteurs d'un lieu au total. / Adds a venue's counters to the total."""
    for nom_du_compteur, valeur in compte_du_lieu.items():
        compte_total[nom_du_compteur] += valeur


def _fin_de_la_derniere_cloture_du_lieu():
    """
    La fin de la dernière clôture du lieu courant, tous niveaux confondus (le plus
    grand `datetime_fin`), ou None si le lieu n'a aucune clôture.
    / The end of the current venue's last closure, any level, or None.
    """
    agregat = ClotureCaisse.objects.aggregate(fin_la_plus_tardive=Max("datetime_fin"))
    return agregat["fin_la_plus_tardive"]


class Command(BaseCommand):
    help = (
        "Rattrapage des virements reçus : chaque paiement Stripe T validé et sans vente "
        "reçoit sa vente « virement reçu ». Passage à blanc par défaut ; --executer écrit."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--schema",
            default=None,
            help="Le schéma d'un seul lieu. Sans cette option : tous les lieux.",
        )
        parser.add_argument(
            "--executer",
            action="store_true",
            help="Écrit les ventes. Sans cette option : rien n'est écrit.",
        )

    def handle(self, *args, **options):
        schema_demande = options["schema"]
        ecriture_demandee = options["executer"]
        if schema_demande:
            lieux_a_lire = list(Client.objects.filter(schema_name=schema_demande))
            if not lieux_a_lire:
                raise CommandError(f"Aucun lieu pour le schéma « {schema_demande} ».")
        else:
            lieux_a_lire = list(
                Client.objects.exclude(schema_name=get_public_schema_name()).order_by(
                    "schema_name"
                )
            )

        if ecriture_demandee:
            self.stdout.write("Rattrapage des virements reçus AVEC écriture.")
        else:
            self.stdout.write(
                "Passage à blanc du rattrapage des virements reçus : rien n'est écrit."
            )

        compte_de_tous_les_lieux = _nouveau_compte()
        for lieu in lieux_a_lire:
            with tenant_context(lieu):
                compte_du_lieu = self._rattraper_le_lieu(lieu, ecriture_demandee)

            # Un lieu sans paiement à rattraper n'a pas de bloc : le rapport reste lisible
            # sur des centaines de lieux.
            # / A venue with nothing to catch up has no block.
            if compte_du_lieu["paiements_trouves"] == 0:
                continue

            # Le domaine principal aide à reconnaître le lieu (le schéma est un uuid).
            # / The primary domain helps recognise the venue (the schema is a uuid).
            domaine_principal_du_lieu = lieu.get_primary_domain()
            texte_du_domaine = "sans domaine principal"
            if domaine_principal_du_lieu is not None:
                texte_du_domaine = domaine_principal_du_lieu.domain
            self._afficher_le_compte(
                f"Lieu {texte_du_domaine} — schéma {lieu.schema_name}",
                compte_du_lieu,
                ecriture_demandee,
            )
            _ajouter_au_total(compte_de_tous_les_lieux, compte_du_lieu)

        self._afficher_le_compte(
            f"Total de {len(lieux_a_lire)} lieu(x)",
            compte_de_tous_les_lieux,
            ecriture_demandee,
        )

    def _rattraper_le_lieu(self, lieu, ecriture_demandee):
        """
        Lit (et écrit si demandé) les virements à rattraper du lieu courant. Appelée
        dans le `tenant_context` du lieu.
        / Reads (and writes if asked) the current venue's transfers to catch up.

        :return: les compteurs du lieu (`_nouveau_compte`)
        """
        compte_du_lieu = _nouveau_compte()
        fin_de_la_derniere_cloture = _fin_de_la_derniere_cloture_du_lieu()

        paiements_a_rattraper = Paiement_stripe.objects.filter(
            source=Paiement_stripe.TRANSFERT,
            status=Paiement_stripe.VALID,
            vente__isnull=True,
            lignearticles__isnull=True,
        ).order_by("order_date", "uuid")

        for paiement in paiements_a_rattraper:
            compte_du_lieu["paiements_trouves"] += 1
            montant_du_virement, date_du_virement = montant_et_date_du_transfert(
                paiement.metadata_stripe
            )
            if montant_du_virement is None:
                compte_du_lieu["illisibles"] += 1
                continue
            compte_du_lieu["montant"] += montant_du_virement

            # La période du transfert est close si une clôture finit à sa date ou après :
            # la vente est alors encaissée maintenant (None).
            # / The transfer period is closed if a closure ends at or after its date.
            periode_close = (
                fin_de_la_derniere_cloture is not None
                and date_du_virement <= fin_de_la_derniere_cloture
            )
            date_d_encaissement = date_du_virement
            if periode_close:
                date_d_encaissement = None

            if not ecriture_demandee:
                compte_du_lieu["ventes_a_ecrire"] += 1
                if periode_close:
                    compte_du_lieu["ventes_datees_maintenant"] += 1
                continue

            # La fabrique écrit tout ou rien, dans sa transaction : une erreur ne laisse
            # aucune vente à moitié écrite, et le paiement suivant est traité.
            # / The factory writes all or nothing; an error does not stop the command.
            try:
                ecrire_la_vente_d_un_virement_recu(
                    paiement,
                    montant_du_virement,
                    f"{PREFIXE_DE_LA_CLE_D_UN_VIREMENT_RECU}{paiement.uuid}",
                    datetime_encaissement=date_d_encaissement,
                )
            except Exception as erreur_de_la_vente:
                compte_du_lieu["erreurs"] += 1
                self.stderr.write(
                    self.style.ERROR(
                        f"Lieu {lieu.schema_name} : la vente du paiement "
                        f"{paiement.uuid_8()} n'a pas pu être écrite "
                        f"({type(erreur_de_la_vente).__name__})."
                    )
                )
                continue

            compte_du_lieu["ventes_ecrites"] += 1
            if periode_close:
                compte_du_lieu["ventes_datees_maintenant"] += 1

        return compte_du_lieu

    def _afficher_le_compte(self, titre, compte, ecriture_demandee):
        """
        Affiche un bloc du rapport : nombres et montants seulement.
        / Shows one report block: numbers and amounts only.
        """
        self.stdout.write("")
        self.stdout.write(f"=== {titre} ===")
        self.stdout.write(f"Paiements trouvés : {compte['paiements_trouves']}")
        self.stdout.write(f"Montant : {_en_euros(compte['montant'])} €")
        self.stdout.write(f"Illisibles : {compte['illisibles']}")
        if ecriture_demandee:
            self.stdout.write(f"Ventes écrites : {compte['ventes_ecrites']}")
            self.stdout.write(
                f"Ventes datées maintenant (période close) : "
                f"{compte['ventes_datees_maintenant']}"
            )
            self.stdout.write(f"Erreurs : {compte['erreurs']}")
        else:
            self.stdout.write(f"Ventes à écrire : {compte['ventes_a_ecrire']}")
            self.stdout.write(
                f"Ventes à dater maintenant (période close) : "
                f"{compte['ventes_datees_maintenant']}"
            )
