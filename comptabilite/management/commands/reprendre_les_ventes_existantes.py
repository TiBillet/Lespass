"""
La reprise des ventes existantes : passage à blanc par défaut, écriture avec
`--executer`. Calcule le plan de chaque lieu, affiche son rapport, et l'écrit si on le
demande.
/ Takeover of existing sales: dry run by default, writing with --executer.

LOCALISATION : comptabilite/management/commands/reprendre_les_ventes_existantes.py

USAGE
    docker exec lespass_django poetry run python /DjangoFiles/manage.py \\
        reprendre_les_ventes_existantes [--schema <schéma du lieu>] [--executer]

Sans `--schema`, tous les lieux (hors schéma public), l'un après l'autre.
Sans `--executer`, rien n'est écrit (passage à blanc).
/ Without --schema, every venue. Without --executer, nothing is written.

LE RAPPORT
Par lieu, des NOMBRES seulement, jamais de donnée personnelle (ni mail, ni nom, ni
carte, ni texte de `metadata`) : lignes lues, ventes par nature et par statut,
règlements par moyen, totaux, anomalies par type, informations, paiements Stripe sans
ligne, durée du calcul. Avec `--executer`, en plus : ventes écrites, ventes sautées
(déjà reprises), chaîne des ventes valide (oui / non), durée de l'écriture. Puis le
total de tous les lieux.
/ Per venue, NUMBERS only. With --executer: written, skipped, chain valid, duration.

UN LIEU REFUSÉ
Un lieu qui a déjà une vente réglée hors reprise n'est pas écrit (fiche R §10) : un
message le dit, et la commande passe au lieu suivant. Une chaîne invalide est affichée
en erreur ; le lieu reste écrit (une transaction par vente).
/ A refused venue is not written; the command goes on with the next one.

CE QUE LA COMMANDE NE FAIT PAS
Aucune requête réseau (ni Stripe, ni Fedow, ni ancien LaBoutik), aucune tâche Celery,
aucun mail. Le calcul est dans BaseBillet/reprise_des_ventes.py, l'écriture dans
BaseBillet/reprise_des_ventes_ecriture.py.
/ No network call, no Celery task, no mail.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-R-reprise-ventes.md (§10).
"""

import time
from decimal import ROUND_HALF_UP, Decimal

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django_tenants.utils import get_public_schema_name, tenant_context

from BaseBillet.reprise_des_ventes import calculer_le_plan_de_reprise
from BaseBillet.reprise_des_ventes_ecriture import (
    RepriseRefusee,
    ecrire_le_plan_de_reprise,
)
from Customers.models import Client


def _en_euros(montant_en_centimes):
    """
    Un montant en centimes, affiché en euros à deux décimales. Affichage seulement :
    rien n'est enregistré.
    / A cent amount shown in euros. Display only: nothing is stored.
    """
    montant_en_euros = Decimal(montant_en_centimes) / Decimal(100)
    return montant_en_euros.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _ajouter(dictionnaire_des_nombres, cle, nombre):
    """Ajoute `nombre` au compteur `cle`. / Adds `nombre` to the `cle` counter."""
    nombre_deja_compte = dictionnaire_des_nombres.get(cle, 0)
    dictionnaire_des_nombres[cle] = nombre_deja_compte + nombre


def _nouveau_resume():
    """Un résumé vide : les nombres d'un rapport.
    / An empty summary: the numbers of a report."""
    return {
        "lignes_lues": 0,
        "ventes_par_nature_et_statut": {},
        "nombre_de_reglements_par_moyen": {},
        "montant_des_reglements_par_moyen": {},
        "total_ancien_calcul_hors_parts_qr": Decimal("0"),
        "total_catalogue_hors_parts_qr": 0,
        "total_ttc": 0,
        "total_part_offerte": 0,
        "anomalies": {},
        "informations": {},
        "paiements_stripe_sans_ligne": 0,
        "duree_en_secondes": 0.0,
    }


def _resume_du_plan(plan, duree_en_secondes):
    """
    Les nombres du rapport d'un lieu, lus dans son plan.
    / The numbers of one venue's report, read from its plan.
    """
    resume = _nouveau_resume()
    resume["lignes_lues"] = plan.nombre_de_lignes_lues
    for vente_a_reprendre in plan.ventes:
        nature_et_statut = f"{vente_a_reprendre.nature} {vente_a_reprendre.statut}"
        _ajouter(resume["ventes_par_nature_et_statut"], nature_et_statut, 1)
        for reglement in vente_a_reprendre.reglements:
            _ajouter(resume["nombre_de_reglements_par_moyen"], reglement.moyen, 1)
            _ajouter(
                resume["montant_des_reglements_par_moyen"],
                reglement.moyen,
                reglement.montant,
            )
    resume["total_ancien_calcul_hors_parts_qr"] = plan.total_ancien_calcul_hors_parts_qr
    resume["total_catalogue_hors_parts_qr"] = plan.total_catalogue_hors_parts_qr
    resume["total_ttc"] = plan.total_ttc
    resume["total_part_offerte"] = plan.total_part_offerte
    resume["anomalies"] = dict(plan.anomalies)
    resume["informations"] = dict(plan.informations)
    resume["paiements_stripe_sans_ligne"] = plan.nombre_de_paiements_stripe_sans_ligne
    resume["duree_en_secondes"] = duree_en_secondes
    return resume


def _ajouter_au_total(resume_total, resume_du_lieu):
    """Ajoute les nombres d'un lieu au total de tous les lieux.
    / Adds one venue's numbers to the total of all venues."""
    resume_total["lignes_lues"] += resume_du_lieu["lignes_lues"]
    resume_total["total_ancien_calcul_hors_parts_qr"] += resume_du_lieu[
        "total_ancien_calcul_hors_parts_qr"
    ]
    resume_total["total_catalogue_hors_parts_qr"] += resume_du_lieu[
        "total_catalogue_hors_parts_qr"
    ]
    resume_total["total_ttc"] += resume_du_lieu["total_ttc"]
    resume_total["total_part_offerte"] += resume_du_lieu["total_part_offerte"]
    resume_total["paiements_stripe_sans_ligne"] += resume_du_lieu[
        "paiements_stripe_sans_ligne"
    ]
    resume_total["duree_en_secondes"] += resume_du_lieu["duree_en_secondes"]

    noms_des_compteurs = [
        "ventes_par_nature_et_statut",
        "nombre_de_reglements_par_moyen",
        "montant_des_reglements_par_moyen",
        "anomalies",
        "informations",
    ]
    for nom_du_compteur in noms_des_compteurs:
        for cle, nombre in resume_du_lieu[nom_du_compteur].items():
            _ajouter(resume_total[nom_du_compteur], cle, nombre)


def _nouvelle_ecriture():
    """Les nombres vides d'une écriture.
    / The empty numbers of a writing."""
    return {
        "ventes_ecrites": 0,
        "ventes_sautees": 0,
        "ventes_a_origines_melangees": 0,
        "lieux_refuses": 0,
        "lieux_a_chaine_invalide": 0,
        "duree_en_secondes": 0.0,
    }


def _ajouter_l_ecriture_au_total(ecriture_totale, ecriture_du_lieu):
    """Ajoute les nombres de l'écriture d'un lieu au total de tous les lieux.
    / Adds one venue's writing numbers to the total."""
    for nom_du_nombre, nombre in ecriture_du_lieu.items():
        ecriture_totale[nom_du_nombre] += nombre


class Command(BaseCommand):
    help = (
        "Reprise des ventes existantes : calcule le plan de chaque lieu et affiche son "
        "rapport (nombres seulement). Passage à blanc par défaut ; --executer écrit."
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
            help="Écrit le plan de chaque lieu. Sans cette option : rien n'est écrit.",
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

        # Un seul moment pour tous les lieux : l'âge des paiements en cours s'y compte.
        # / One moment for every venue: pending payments' age is counted from it.
        moment_de_la_reprise = timezone.now()
        if ecriture_demandee:
            self.stdout.write(
                f"Reprise des ventes AVEC écriture. "
                f"Moment de la reprise : {moment_de_la_reprise.isoformat()}."
            )
        else:
            self.stdout.write(
                f"Passage à blanc de la reprise des ventes : rien n'est écrit. "
                f"Moment de la reprise : {moment_de_la_reprise.isoformat()}."
            )

        resume_de_tous_les_lieux = _nouveau_resume()
        ecriture_de_tous_les_lieux = _nouvelle_ecriture()
        for lieu in lieux_a_lire:
            debut_du_calcul = time.monotonic()
            with tenant_context(lieu):
                plan_du_lieu = calculer_le_plan_de_reprise(moment_de_la_reprise)
            duree_du_calcul = time.monotonic() - debut_du_calcul

            # Le nom et le domaine principal aident le mainteneur à reconnaître le lieu
            # dans le rapport (le schéma n'est qu'un uuid).
            # / Name and primary domain help recognise the venue (the schema is a uuid).
            domaine_principal_du_lieu = lieu.get_primary_domain()
            texte_du_domaine = "sans domaine principal"
            if domaine_principal_du_lieu is not None:
                texte_du_domaine = domaine_principal_du_lieu.domain
            resume_du_lieu = _resume_du_plan(plan_du_lieu, duree_du_calcul)
            self._afficher_le_resume(
                f"Lieu {lieu.name} — {texte_du_domaine} — schéma {lieu.schema_name}",
                resume_du_lieu,
            )
            _ajouter_au_total(resume_de_tous_les_lieux, resume_du_lieu)

            if ecriture_demandee:
                ecriture_du_lieu = self._ecrire_le_plan_du_lieu(lieu, plan_du_lieu)
                self._afficher_l_ecriture(ecriture_du_lieu)
                _ajouter_l_ecriture_au_total(
                    ecriture_de_tous_les_lieux, ecriture_du_lieu
                )

        titre_du_total = f"Total de {len(lieux_a_lire)} lieu(x)"
        self._afficher_le_resume(titre_du_total, resume_de_tous_les_lieux)
        if ecriture_demandee:
            self._afficher_l_ecriture(ecriture_de_tous_les_lieux)

    def _ecrire_le_plan_du_lieu(self, lieu, plan_du_lieu):
        """
        Écrit le plan d'un lieu et rend les nombres de son écriture. Un lieu refusé
        (déjà une vente réglée hors reprise) n'est pas écrit : le message est affiché,
        et la commande continue avec le lieu suivant.
        / Writes one venue's plan; a refused venue is reported and skipped.
        """
        ecriture_du_lieu = _nouvelle_ecriture()
        debut_de_l_ecriture = time.monotonic()
        try:
            with tenant_context(lieu):
                resultat = ecrire_le_plan_de_reprise(plan_du_lieu)
        except RepriseRefusee as refus:
            self.stderr.write(self.style.ERROR(f"Lieu {lieu.schema_name} : {refus}"))
            ecriture_du_lieu["lieux_refuses"] = 1
            return ecriture_du_lieu

        ecriture_du_lieu["ventes_ecrites"] = resultat.nombre_de_ventes_ecrites
        ecriture_du_lieu["ventes_sautees"] = resultat.nombre_de_ventes_sautees
        ecriture_du_lieu["ventes_a_origines_melangees"] = (
            resultat.nombre_de_ventes_a_origines_melangees
        )
        if not resultat.chaine_valide:
            ecriture_du_lieu["lieux_a_chaine_invalide"] = 1
            self.stderr.write(
                self.style.ERROR(
                    f"Lieu {lieu.schema_name} : chaîne des ventes INVALIDE "
                    f"({len(resultat.anomalies_de_la_chaine)} anomalie(s)). "
                    f"Lancer verify_integrity."
                )
            )
        ecriture_du_lieu["duree_en_secondes"] = time.monotonic() - debut_de_l_ecriture
        return ecriture_du_lieu

    def _afficher_l_ecriture(self, ecriture):
        """
        Affiche les nombres d'une écriture (un lieu, ou le total de tous les lieux).
        / Prints the numbers of a writing (one venue, or the total).
        """
        self.stdout.write("Écriture :")
        self.stdout.write(f"  Ventes écrites : {ecriture['ventes_ecrites']}")
        self.stdout.write(
            f"  Ventes sautées (déjà reprises) : {ecriture['ventes_sautees']}"
        )
        self.stdout.write(
            f"  Ventes à origines mélangées (origine de la première ligne) : "
            f"{ecriture['ventes_a_origines_melangees']}"
        )
        if ecriture["lieux_refuses"] > 0:
            self.stdout.write(
                f"  Lieux refusés (vente réglée hors reprise) : "
                f"{ecriture['lieux_refuses']}"
            )
        if ecriture["lieux_a_chaine_invalide"] > 0:
            self.stdout.write(
                f"  Chaîne des ventes valide : non "
                f"({ecriture['lieux_a_chaine_invalide']} lieu(x))"
            )
        elif ecriture["lieux_refuses"] == 0:
            self.stdout.write("  Chaîne des ventes valide : oui")
        self.stdout.write(
            f"  Durée de l'écriture : {ecriture['duree_en_secondes']:.2f} s"
        )

    def _afficher_le_resume(self, titre, resume):
        """
        Affiche les nombres d'un résumé, sous un titre.
        / Prints a summary's numbers under a title.
        """
        self.stdout.write("")
        self.stdout.write(f"=== {titre} ===")
        self.stdout.write(f"Lignes lues : {resume['lignes_lues']}")

        self.stdout.write("Ventes par nature et statut :")
        for nature_et_statut, nombre in sorted(
            resume["ventes_par_nature_et_statut"].items()
        ):
            self.stdout.write(f"  {nature_et_statut} : {nombre}")

        self.stdout.write("Règlements par moyen (nombre, montant) :")
        for moyen, nombre in sorted(resume["nombre_de_reglements_par_moyen"].items()):
            montant_du_moyen = resume["montant_des_reglements_par_moyen"][moyen]
            self.stdout.write(f"  {moyen} : {nombre}, {_en_euros(montant_du_moyen)} €")

        self.stdout.write(
            "Hors parts QR — ancien calcul (Σ amount × qty) : "
            f"{_en_euros(resume['total_ancien_calcul_hors_parts_qr'])} € ; "
            "nouveau total catalogue : "
            f"{_en_euros(resume['total_catalogue_hors_parts_qr'])} €"
        )
        self.stdout.write(
            f"Tous les articles — Σ net vendu (total_ttc) : "
            f"{_en_euros(resume['total_ttc'])} € ; Σ part offerte : "
            f"{_en_euros(resume['total_part_offerte'])} €"
        )

        self.stdout.write("Anomalies (nombre de lignes) :")
        if not resume["anomalies"]:
            self.stdout.write("  aucune")
        for type_d_anomalie, nombre in sorted(resume["anomalies"].items()):
            self.stdout.write(f"  {type_d_anomalie} : {nombre}")

        self.stdout.write("Informations (nombre de paiements) :")
        if not resume["informations"]:
            self.stdout.write("  aucune")
        for type_d_information, nombre in sorted(resume["informations"].items()):
            self.stdout.write(f"  {type_d_information} : {nombre}")

        self.stdout.write(
            f"Paiements Stripe sans ligne (aucune vente) : "
            f"{resume['paiements_stripe_sans_ligne']}"
        )
        self.stdout.write(f"Durée du calcul : {resume['duree_en_secondes']:.2f} s")
