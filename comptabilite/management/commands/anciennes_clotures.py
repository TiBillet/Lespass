"""
Exporter puis supprimer les anciennes clôtures, la nuit de la bascule.
/ Export then delete the old closures, on the switch-over night.

LOCALISATION : comptabilite/management/commands/anciennes_clotures.py

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-R-reprise-ventes.md (§1,
§12 étapes 4 et 7) et le brief CHANTIER-05-briefs/05-R-4a.md.

USAGE
    # Étape 4 : AVANT les migrations. Écrit un fichier par lieu et un résumé. Rien en base.
    manage.py anciennes_clotures --exporter /dossier/vide
    # Étape 7 : APRÈS les migrations. À blanc par défaut.
    manage.py anciennes_clotures --supprimer --export /dossier/de/l/export
    manage.py anciennes_clotures --supprimer --export /dossier/de/l/export --executer

--exporter <dossier>
    Pour chaque lieu (hors schéma public), lit `comptabilite_cloturecaisse` en SQL brut et
    écrit `<schéma>.json` (liste des lignes) puis `resume.csv` (schéma, domaine, nombre).
    Un lieu sans clôture n'a pas de fichier, mais une ligne à 0 dans le résumé. Un dossier
    qui contient déjà un fichier est refusé : rien n'est écrasé.

--supprimer --export <dossier> [--executer]
    Pour chaque lieu, compare le nombre de clôtures en base au nombre du `resume.csv`.
    Égal : les clôtures du lieu sont supprimées (une transaction par lieu). Différent, ou
    lieu absent du résumé : rien n'est supprimé, le lieu est listé en refus. Sans
    `--executer`, rien n'est supprimé : mêmes comptages, à blanc.

SQL BRUT SEULEMENT : à l'export, la table a encore la forme de `main` (avant les
migrations), le modèle Django ne la décrit plus. Les noms de schéma viennent de la table
des lieux, entre guillemets doubles, jamais d'une saisie.
Le rapport ne montre que des nombres, des schémas et des domaines.
/ Raw SQL only. Schema names come from the venues table, double-quoted. The report shows
only numbers, schemas and domains.
"""

import csv
import json
import os
import time

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from Administration import nettoyage_des_lieux
from Administration.nettoyage_des_lieux import nom_complet

NOM_DU_FICHIER_RESUME = "resume.csv"
COLONNE_SCHEMA = "schema"
COLONNE_DOMAINE = "domaine"
COLONNE_NOMBRE = "nombre_de_clotures"
TABLE_DES_CLOTURES = "comptabilite_cloturecaisse"
DOMAINE_ABSENT = "(sans domaine)"


class Command(BaseCommand):
    help = (
        "Exporte (--exporter) puis supprime (--supprimer) les anciennes clôtures de "
        "chaque lieu. Voir CHANTIER-05-R-reprise-ventes.md §12 étapes 4 et 7."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--exporter",
            dest="dossier_a_remplir",
            default=None,
            help="Écrit un fichier JSON par lieu et resume.csv dans ce dossier vide.",
        )
        parser.add_argument(
            "--supprimer",
            action="store_true",
            help="Supprime les clôtures des lieux dont le nombre colle au résumé.",
        )
        parser.add_argument(
            "--export",
            dest="dossier_de_l_export",
            default=None,
            help="Le dossier d'un export précédent (obligatoire avec --supprimer).",
        )
        parser.add_argument(
            "--executer",
            action="store_true",
            help="Avec --supprimer : supprime vraiment. Sans elle, passage à blanc.",
        )

    def handle(self, *args, **options):
        heure_de_depart = time.monotonic()
        dossier_a_remplir = options["dossier_a_remplir"]
        supprimer = options["supprimer"]
        dossier_de_l_export = options["dossier_de_l_export"]

        un_seul_mode_demande = bool(dossier_a_remplir) != bool(supprimer)
        if not un_seul_mode_demande:
            raise CommandError(
                "Choisir --exporter <dossier> OU --supprimer --export <dossier>."
            )
        if supprimer and not dossier_de_l_export:
            raise CommandError("--supprimer demande --export <dossier>.")
        if options["executer"] and not supprimer:
            raise CommandError("--executer ne va qu'avec --supprimer.")

        connection.set_schema_to_public()
        with connection.cursor() as curseur:
            tous_les_lieux = nettoyage_des_lieux.lire_les_lieux(curseur)

        if dossier_a_remplir:
            self.exporter_les_clotures(tous_les_lieux, dossier_a_remplir)
        else:
            self.supprimer_les_clotures(
                tous_les_lieux, dossier_de_l_export, options["executer"]
            )

        duree = time.monotonic() - heure_de_depart
        self.stdout.write(f"Durée : {duree:.1f} s")

    # ------------------------------------------------------------------
    # Mode --exporter
    # ------------------------------------------------------------------

    def exporter_les_clotures(self, tous_les_lieux, dossier):
        """
        Un fichier JSON par lieu qui a des clôtures, et le résumé de tous les lieux.
        Aucune écriture en base.
        / One JSON file per venue with closures, and the summary of all venues.
        """
        os.makedirs(dossier, exist_ok=True)
        if os.listdir(dossier):
            raise CommandError(
                f"Le dossier « {dossier} » n'est pas vide : rien n'est écrasé."
            )

        lignes_du_resume = []
        nombre_total_exporte = 0
        for lieu in tous_les_lieux:
            nom_du_schema = lieu["nom_du_schema"]
            domaine = lieu["domaine"] or DOMAINE_ABSENT

            with connection.cursor() as curseur:
                curseur.execute(
                    f"SELECT row_to_json(cloture) "
                    f"FROM {nom_complet(nom_du_schema, TABLE_DES_CLOTURES)} cloture "
                    f"ORDER BY numero_sequentiel"
                )
                lignes_exportees = []
                for (ligne_en_json,) in curseur.fetchall():
                    lignes_exportees.append(ligne_en_json)

            nombre_de_clotures = len(lignes_exportees)
            if nombre_de_clotures > 0:
                chemin_du_fichier = os.path.join(dossier, f"{nom_du_schema}.json")
                with open(chemin_du_fichier, "w", encoding="utf-8") as fichier:
                    json.dump(
                        lignes_exportees, fichier, ensure_ascii=False, default=str
                    )

            lignes_du_resume.append([nom_du_schema, domaine, nombre_de_clotures])
            nombre_total_exporte += nombre_de_clotures

        chemin_du_resume = os.path.join(dossier, NOM_DU_FICHIER_RESUME)
        with open(chemin_du_resume, "w", newline="", encoding="utf-8") as fichier:
            ecrivain = csv.writer(fichier)
            ecrivain.writerow([COLONNE_SCHEMA, COLONNE_DOMAINE, COLONNE_NOMBRE])
            ecrivain.writerows(lignes_du_resume)

        self.stdout.write(f"Lieux traités : {len(tous_les_lieux)}")
        self.stdout.write(f"Clôtures exportées : {nombre_total_exporte}")

    # ------------------------------------------------------------------
    # Mode --supprimer
    # ------------------------------------------------------------------

    def lire_le_resume(self, dossier):
        """
        Le résumé de l'export : schéma -> nombre de clôtures annoncé.
        / The export summary: schema -> announced number of closures.
        """
        chemin_du_resume = os.path.join(dossier, NOM_DU_FICHIER_RESUME)
        if not os.path.isfile(chemin_du_resume):
            raise CommandError(f"Pas de {NOM_DU_FICHIER_RESUME} dans « {dossier} ».")

        nombre_annonce_par_schema = {}
        with open(chemin_du_resume, newline="", encoding="utf-8") as fichier:
            for ligne in csv.DictReader(fichier):
                nombre_annonce_par_schema[ligne[COLONNE_SCHEMA]] = int(
                    ligne[COLONNE_NOMBRE]
                )
        return nombre_annonce_par_schema

    def supprimer_les_clotures(self, tous_les_lieux, dossier, executer):
        """
        Pour chaque lieu : supprime si le nombre en base égale celui du résumé, sinon
        refuse. Une transaction par lieu ; un échec n'arrête pas les autres lieux.
        / Per venue: delete if the database count equals the summary, else refuse.
        """
        nombre_annonce_par_schema = self.lire_le_resume(dossier)

        nombre_de_lieux_vides = 0
        nombre_de_clotures_supprimees = 0
        lieux_refuses = []

        for lieu in tous_les_lieux:
            nom_du_schema = lieu["nom_du_schema"]
            domaine = lieu["domaine"] or DOMAINE_ABSENT
            table = nom_complet(nom_du_schema, TABLE_DES_CLOTURES)

            if nom_du_schema not in nombre_annonce_par_schema:
                lieux_refuses.append((domaine, "absent du résumé"))
                continue

            try:
                with transaction.atomic():
                    with connection.cursor() as curseur:
                        curseur.execute(f"SELECT count(*) FROM {table}")
                        nombre_en_base = curseur.fetchone()[0]

                        nombre_annonce = nombre_annonce_par_schema[nom_du_schema]
                        if nombre_en_base != nombre_annonce:
                            lieux_refuses.append(
                                (
                                    domaine,
                                    f"{nombre_en_base} en base, {nombre_annonce} au résumé",
                                )
                            )
                            continue

                        if executer:
                            curseur.execute(f"DELETE FROM {table}")
            except Exception as erreur:
                lieux_refuses.append((domaine, f"échec : {type(erreur).__name__}"))
                continue

            nombre_de_lieux_vides += 1
            nombre_de_clotures_supprimees += nombre_en_base

        mode = "supprimées" if executer else "à supprimer (à blanc)"
        self.stdout.write(f"Lieux traités : {len(tous_les_lieux)}")
        self.stdout.write(f"Lieux concernés : {nombre_de_lieux_vides}")
        self.stdout.write(f"Clôtures {mode} : {nombre_de_clotures_supprimees}")
        self.stdout.write(f"Lieux refusés : {len(lieux_refuses)}")
        for domaine, raison in lieux_refuses:
            self.stdout.write(f"  refusé : {domaine} ({raison})")
