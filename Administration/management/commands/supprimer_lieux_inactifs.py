"""
Supprimer les lieux qui n'ont jamais eu aucune activité, avant la migration de la bascule.
/ Delete the venues that never had any activity, before the switch-over migration.

LOCALISATION : Administration/management/commands/supprimer_lieux_inactifs.py

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-R-reprise-ventes.md §18
(et §12 étape 2 bis : la nuit de la bascule, juste avant `migrate_schemas`).
La détection (les 8 critères) est dans Administration/nettoyage_des_lieux.py.
/ Spec §18. Detection (the 8 criteria) lives in Administration/nettoyage_des_lieux.py.

USAGE :
    # À blanc (par défaut) : rien n'est écrit. Tous les lieux sont examinés.
    manage.py supprimer_lieux_inactifs --rapport rapport.csv
    # Exécution : seulement les lieux de la liste validée, encore inactifs.
    manage.py supprimer_lieux_inactifs --liste domaines.txt --executer \\
        --rapport rapport.csv --traces-externes traces.csv

OPTIONS :
- `--executer` : supprime. Sans elle, la commande est à blanc.
- `--liste <fichier>` : un domaine principal par ligne. Obligatoire avec `--executer`.
  Limite l'examen aux lieux de la liste, à blanc comme en exécution.
- `--jours-minimum N` (60) : un lieu plus jeune est gardé.
- `--rapport <chemin.csv>` : colonnes liste, domaine, date_de_creation, raisons.
- `--traces-externes <chemin.csv>` : colonnes domaine, stripe_connect,
  stripe_connect_test, place_fedow (lieux supprimés, ou à supprimer à blanc).
- `--sans-mail` : aucun mail aux administrateurs.

FLUX :
1. Lire les lieux et leur domaine principal. Un lieu sans domaine principal (emplacement
   du pool) est ignoré et compté.
2. Lire, dans le catalogue, toutes les lignes qui pointent vers les lieux examinés.
3. Pour chaque lieu : ses raisons d'être gardé (nettoyage_des_lieux.py).
4. Avec `--executer`, pour chaque lieu de la liste encore inactif, UNE transaction :
   traces externes et adresses des administrateurs lues ; `DROP SCHEMA … CASCADE` ;
   liens partagés vidés ou supprimés ; domaines ; ligne `Client` ; contrôle par le
   catalogue (plus rien ne pointe vers le lieu, sinon exception : la transaction est
   annulée et le schéma revient). Un échec n'arrête pas les autres lieux.
5. Après tous les lieux : un mail par administrateur, qui liste ses lieux supprimés, mis
   en file Celery (`send_email_generique.delay`). Rien pour un lieu en échec.
6. Rapport à l'écran et en CSV ; résumé chiffré.
/ Flow: read venues, read references, judge each venue, delete each listed inactive
venue in its own transaction, queue one mail per admin, write the reports.

SQL BRUT SEULEMENT (`connection.cursor()`) : la nuit, la base n'est pas encore migrée.
Le lieu est toujours désigné par son domaine principal, jamais par son schéma.
/ Raw SQL only. A venue is always named by its primary domain, never its schema.
"""

import csv
import time
from functools import partial

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext

from Administration import nettoyage_des_lieux
from Administration.nettoyage_des_lieux import nom_complet, nom_sql

# Les valeurs de la colonne `liste` du rapport. Textes fixes (pas traduits) : le rapport
# est un outil d'exploitation, relu par le mainteneur et par les tests.
# / Values of the report's `liste` column. Fixed texts (not translated).
LISTE_A_SUPPRIMER = "à supprimer"
LISTE_SUPPRIME = "supprimé"
LISTE_GARDE = "gardé"
LISTE_ECHEC = "échec"
RAISON_D_UN_LIEU_INACTIF = "aucune activité"

CATEGORIE_DU_POOL = "W"


class ReferenceRestanteVersLeLieu(Exception):
    """Une ligne pointe encore vers le lieu juste avant le COMMIT.
    / A row still points to the venue right before COMMIT."""


class Command(BaseCommand):
    help = (
        "Supprime les lieux qui n'ont jamais eu aucune activité (à blanc par défaut). "
        "Voir CHANTIER-05-R-reprise-ventes.md §18."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--executer",
            action="store_true",
            help="Supprime vraiment. Sans cette option, rien n'est écrit.",
        )
        parser.add_argument(
            "--liste",
            dest="chemin_de_la_liste",
            default=None,
            help="Fichier des domaines validés, un par ligne (obligatoire avec --executer).",
        )
        parser.add_argument(
            "--jours-minimum",
            dest="jours_minimum",
            type=int,
            default=60,
            help="Un lieu créé il y a moins de N jours est gardé (défaut : 60).",
        )
        parser.add_argument(
            "--rapport",
            dest="chemin_du_rapport",
            default=None,
            help="Chemin du rapport CSV.",
        )
        parser.add_argument(
            "--traces-externes",
            dest="chemin_des_traces_externes",
            default=None,
            help="Chemin du CSV des traces externes (Stripe Connect, place Fedow).",
        )
        parser.add_argument(
            "--sans-mail",
            action="store_true",
            help="N'envoie aucun mail aux administrateurs.",
        )

    def handle(self, *args, **options):
        heure_de_depart = time.monotonic()
        executer = options["executer"]
        chemin_de_la_liste = options["chemin_de_la_liste"]

        if executer and not chemin_de_la_liste:
            raise CommandError(
                "L'option --liste est obligatoire avec --executer : "
                "seuls les lieux de la liste validée peuvent être supprimés."
            )

        domaines_de_la_liste = None
        if chemin_de_la_liste:
            domaines_de_la_liste = self.lire_la_liste_des_domaines(chemin_de_la_liste)

        connection.set_schema_to_public()

        # 1. Les lieux. / 1. The venues.
        with connection.cursor() as curseur:
            tous_les_lieux = nettoyage_des_lieux.lire_les_lieux(curseur)

        domaine_par_schema = {}
        for lieu in tous_les_lieux:
            domaine_par_schema[lieu["nom_du_schema"]] = lieu["domaine"]

        lieux_examines = []
        nombre_d_emplacements_du_pool_ignores = 0
        nombre_de_lieux_sans_domaine_ignores = 0
        domaines_connus = set()
        for lieu in tous_les_lieux:
            if lieu["domaine"] is None:
                if lieu["categorie"] == CATEGORIE_DU_POOL:
                    nombre_d_emplacements_du_pool_ignores += 1
                else:
                    nombre_de_lieux_sans_domaine_ignores += 1
                continue
            domaines_connus.add(lieu["domaine"])
            if (
                domaines_de_la_liste is not None
                and lieu["domaine"] not in domaines_de_la_liste
            ):
                continue
            lieux_examines.append(lieu)

        domaines_inconnus = []
        if domaines_de_la_liste is not None:
            for domaine in domaines_de_la_liste:
                if domaine not in domaines_connus:
                    domaines_inconnus.append(domaine)

        # 2 et 3. Les raisons de chaque lieu. / 2 and 3. Each venue's reasons.
        self.juger_les_lieux(
            lieux_examines, domaine_par_schema, options["jours_minimum"]
        )

        # 4. La suppression, lieu par lieu. / 4. Deletion, venue by venue.
        signalements = []
        lieux_supprimes_par_adresse = {}
        for lieu in lieux_examines:
            if lieu["liste"] == LISTE_ECHEC:
                continue
            lieu_inactif = len(lieu["raisons"]) == 0
            if not executer:
                if lieu_inactif:
                    lieu["liste"] = LISTE_A_SUPPRIMER
                    lieu["raisons"] = [RAISON_D_UN_LIEU_INACTIF]
                continue
            if not lieu_inactif:
                signalements.append(
                    f"{lieu['domaine']} : dans la liste, mais actif maintenant : "
                    + " ; ".join(lieu["raisons"])
                )
                continue
            self.supprimer_le_lieu(
                lieu, domaine_par_schema, lieux_supprimes_par_adresse
            )

        # 5. Les mails, après tous les lieux. / 5. The mails, after all venues.
        nombre_de_mails_mis_en_file = 0
        if executer and not options["sans_mail"]:
            nombre_de_mails_mis_en_file = self.mettre_les_mails_en_file(
                lieux_supprimes_par_adresse
            )

        # 6. Les rapports. / 6. The reports.
        self.afficher_le_rapport(
            lieux_examines, executer, signalements, domaines_inconnus
        )
        if options["chemin_du_rapport"]:
            self.ecrire_le_rapport_csv(options["chemin_du_rapport"], lieux_examines)
        if options["chemin_des_traces_externes"]:
            self.ecrire_les_traces_externes(
                options["chemin_des_traces_externes"], lieux_examines
            )
        self.afficher_le_resume(
            lieux_examines,
            executer,
            nombre_d_emplacements_du_pool_ignores,
            nombre_de_lieux_sans_domaine_ignores,
            nombre_de_mails_mis_en_file,
            domaines_inconnus,
            time.monotonic() - heure_de_depart,
        )

    # ------------------------------------------------------------------ #
    #  Lecture de la liste                                               #
    # ------------------------------------------------------------------ #

    def lire_la_liste_des_domaines(self, chemin_de_la_liste):
        """
        Les domaines du fichier, un par ligne, en minuscules. Les lignes vides et celles
        qui commencent par « # » sont sautées.
        / The file's domains, one per line, lowercase; blank and « # » lines skipped.
        """
        try:
            with open(chemin_de_la_liste, encoding="utf-8") as fichier:
                lignes = fichier.read().splitlines()
        except OSError as erreur:
            raise CommandError(f"Liste illisible : {erreur}")

        domaines = []
        for ligne in lignes:
            domaine = ligne.strip().lower()
            if not domaine or domaine.startswith("#"):
                continue
            if domaine not in domaines:
                domaines.append(domaine)
        return domaines

    # ------------------------------------------------------------------ #
    #  Détection                                                         #
    # ------------------------------------------------------------------ #

    def juger_les_lieux(self, lieux_examines, domaine_par_schema, jours_minimum):
        """
        Pose sur chaque lieu examiné : `raisons` (vide = inactif), `liste` (« gardé »,
        ou « échec » si sa lecture a planté), `traces_externes`.
        / Sets reasons, list and external traces on each examined venue.
        """
        aujourd_hui = timezone.localdate()
        uuids_des_lieux_examines = []
        for lieu in lieux_examines:
            uuids_des_lieux_examines.append(lieu["uuid"])

        with connection.cursor() as curseur:
            cles_etrangeres = (
                nettoyage_des_lieux.lire_les_cles_etrangeres_vers_les_lieux(curseur)
            )
            references_par_lieu = (
                nettoyage_des_lieux.compter_les_references_vers_les_lieux(
                    curseur, cles_etrangeres, uuids_des_lieux_examines
                )
            )

            for lieu in lieux_examines:
                lieu["liste"] = LISTE_GARDE
                lieu["raisons"] = []
                lieu["traces_externes"] = None
                lieu["administrateurs"] = []
                try:
                    lieu["raisons"] = nettoyage_des_lieux.raisons_qui_gardent_le_lieu(
                        curseur,
                        lieu,
                        references_par_lieu.get(lieu["uuid"], []),
                        domaine_par_schema,
                        jours_minimum,
                        aujourd_hui,
                    )
                    if not lieu["raisons"]:
                        lieu["traces_externes"] = (
                            nettoyage_des_lieux.lire_les_traces_externes(
                                curseur, lieu["nom_du_schema"]
                            )
                        )
                        lieu["administrateurs"] = (
                            nettoyage_des_lieux.lire_les_adresses_des_administrateurs(
                                curseur, lieu["uuid"]
                            )
                        )
                except Exception as erreur:
                    lieu["liste"] = LISTE_ECHEC
                    lieu["raisons"] = [
                        message_sans_nom_de_schema(erreur, domaine_par_schema)
                    ]

    # ------------------------------------------------------------------ #
    #  Suppression d'un lieu                                             #
    # ------------------------------------------------------------------ #

    def supprimer_le_lieu(self, lieu, domaine_par_schema, lieux_supprimes_par_adresse):
        """
        Supprime UN lieu dans UNE transaction. Un échec est noté sur le lieu (« échec »)
        et n'arrête pas les autres.
        / Deletes ONE venue in ONE transaction. A failure is recorded, others go on.

        ORDRE : traces externes et administrateurs lus ; schéma supprimé ; liens partagés
        vidés ou supprimés ; domaines ; `Client` ; contrôle par le catalogue. Les clés
        étrangères de Django sont vérifiées au COMMIT : une référence oubliée fait aussi
        échouer le COMMIT, et le schéma revient.
        / Order: read traces and admins; drop schema; clean shared links; domains;
        Client; catalogue check. Django FKs are also checked at COMMIT.
        """
        uuid_du_lieu = lieu["uuid"]
        nom_du_schema = lieu["nom_du_schema"]
        lieu_supprime = {
            "domaine": lieu["domaine"],
            "date_de_creation": lieu["date_de_creation"],
        }

        try:
            with transaction.atomic():
                with connection.cursor() as curseur:
                    lieu["traces_externes"] = (
                        nettoyage_des_lieux.lire_les_traces_externes(
                            curseur, nom_du_schema
                        )
                    )
                    adresses_des_administrateurs = (
                        nettoyage_des_lieux.lire_les_adresses_des_administrateurs(
                            curseur, uuid_du_lieu
                        )
                    )
                    lieu["administrateurs"] = adresses_des_administrateurs

                    curseur.execute(f"DROP SCHEMA {nom_sql(nom_du_schema)} CASCADE")
                    nettoyer_les_liens_partages(curseur, uuid_du_lieu)

                    # Les domaines, puis la ligne `Client`.
                    # / The domains, then the Client row.
                    curseur.execute(
                        'DELETE FROM public."Customers_domain" WHERE tenant_id = %s::uuid',
                        [uuid_du_lieu],
                    )
                    curseur.execute(
                        'DELETE FROM public."Customers_client" WHERE uuid = %s::uuid',
                        [uuid_du_lieu],
                    )

                    tables_restantes = (
                        nettoyage_des_lieux.references_restantes_vers_le_lieu(
                            curseur, uuid_du_lieu, domaine_par_schema
                        )
                    )
                    if tables_restantes:
                        raise ReferenceRestanteVersLeLieu(
                            "références restantes vers le lieu : "
                            + ", ".join(tables_restantes)
                        )

                transaction.on_commit(
                    partial(
                        noter_la_suppression_apres_le_commit,
                        lieux_supprimes_par_adresse,
                        adresses_des_administrateurs,
                        lieu_supprime,
                    )
                )
            lieu["liste"] = LISTE_SUPPRIME
            lieu["raisons"] = [RAISON_D_UN_LIEU_INACTIF]
        except Exception as erreur:
            lieu["liste"] = LISTE_ECHEC
            lieu["raisons"] = [message_sans_nom_de_schema(erreur, domaine_par_schema)]

    # ------------------------------------------------------------------ #
    #  Mails                                                             #
    # ------------------------------------------------------------------ #

    def mettre_les_mails_en_file(self, lieux_supprimes_par_adresse):
        """
        Un mail par administrateur, qui liste tous ses lieux supprimés, mis en file
        Celery. La nuit, le worker est arrêté : les mails partent à la réouverture.
        / One mail per administrator, listing all his deleted venues, queued in Celery.
        """
        from BaseBillet.tasks import send_email_generique

        nombre_de_mails = 0
        for adresse in sorted(lieux_supprimes_par_adresse.keys()):
            contexte_du_mail = construire_le_mail_d_un_administrateur(
                adresse, lieux_supprimes_par_adresse[adresse]
            )
            send_email_generique.delay(context=contexte_du_mail, email=adresse)
            nombre_de_mails += 1
        return nombre_de_mails

    # ------------------------------------------------------------------ #
    #  Rapports                                                          #
    # ------------------------------------------------------------------ #

    def afficher_le_rapport(
        self, lieux_examines, executer, signalements, domaines_inconnus
    ):
        """Les listes à l'écran, un lieu par ligne. / The lists on screen."""
        titre_de_la_premiere_liste = "Lieux à supprimer"
        valeur_de_la_premiere_liste = LISTE_A_SUPPRIMER
        if executer:
            titre_de_la_premiere_liste = "Lieux supprimés"
            valeur_de_la_premiere_liste = LISTE_SUPPRIME

        listes_a_afficher = [
            (titre_de_la_premiere_liste, valeur_de_la_premiere_liste),
            ("Lieux gardés", LISTE_GARDE),
            ("Lieux en échec", LISTE_ECHEC),
        ]
        for titre, valeur_de_la_liste in listes_a_afficher:
            lieux_de_la_liste = []
            for lieu in lieux_examines:
                if lieu["liste"] == valeur_de_la_liste:
                    lieux_de_la_liste.append(lieu)
            self.stdout.write(f"\n{titre} ({len(lieux_de_la_liste)}) :")
            for lieu in lieux_de_la_liste:
                self.stdout.write(
                    f"  {lieu['domaine']} — créé le {lieu['date_de_creation'].isoformat()}"
                    f" — " + " ; ".join(lieu["raisons"])
                )

        if signalements or domaines_inconnus:
            self.stdout.write("\nSignalements :")
            for signalement in signalements:
                self.stdout.write(f"  {signalement}")
            for domaine in domaines_inconnus:
                self.stdout.write(f"  {domaine} : domaine de la liste inconnu")

    def ecrire_le_rapport_csv(self, chemin_du_rapport, lieux_examines):
        """Une ligne par lieu examiné. / One row per examined venue."""
        with open(chemin_du_rapport, "w", encoding="utf-8", newline="") as fichier:
            ecrivain = csv.writer(fichier)
            ecrivain.writerow(["liste", "domaine", "date_de_creation", "raisons"])
            for lieu in lieux_examines:
                ecrivain.writerow(
                    [
                        lieu["liste"],
                        lieu["domaine"],
                        lieu["date_de_creation"].isoformat(),
                        " ; ".join(lieu["raisons"]),
                    ]
                )

    def ecrire_les_traces_externes(self, chemin_des_traces, lieux_examines):
        """
        Les traces externes des lieux supprimés (à blanc : à supprimer), pour un nettoyage
        plus tard chez Stripe et Fedow. La colonne `administrateurs` garde « qui prévenir »
        si la file des mails est perdue : ce fichier contient des adresses, il reste hors du
        dépôt.
        / External traces of deleted (or to-delete) venues, with the admins' addresses
        (personal data: keep the file out of the repository).
        """
        with open(chemin_des_traces, "w", encoding="utf-8", newline="") as fichier:
            ecrivain = csv.writer(fichier)
            ecrivain.writerow(
                [
                    "domaine",
                    "stripe_connect",
                    "stripe_connect_test",
                    "place_fedow",
                    "administrateurs",
                ]
            )
            for lieu in lieux_examines:
                if lieu["liste"] not in [LISTE_SUPPRIME, LISTE_A_SUPPRIMER]:
                    continue
                traces = lieu["traces_externes"]
                ecrivain.writerow(
                    [
                        lieu["domaine"],
                        traces["stripe_connect"],
                        traces["stripe_connect_test"],
                        traces["place_fedow"],
                        " ; ".join(lieu["administrateurs"]),
                    ]
                )

    def afficher_le_resume(
        self,
        lieux_examines,
        executer,
        nombre_d_emplacements_du_pool_ignores,
        nombre_de_lieux_sans_domaine_ignores,
        nombre_de_mails_mis_en_file,
        domaines_inconnus,
        duree_en_secondes,
    ):
        """Le résumé chiffré. / The figures summary."""
        nombre_par_liste = {
            LISTE_A_SUPPRIMER: 0,
            LISTE_SUPPRIME: 0,
            LISTE_GARDE: 0,
            LISTE_ECHEC: 0,
        }
        for lieu in lieux_examines:
            nombre_par_liste[lieu["liste"]] += 1

        liste_des_lieux_retires = LISTE_A_SUPPRIMER
        if executer:
            liste_des_lieux_retires = LISTE_SUPPRIME
        nombre_de_lieux_retires_sans_administrateur = 0
        for lieu in lieux_examines:
            if lieu["liste"] == liste_des_lieux_retires and not lieu["administrateurs"]:
                nombre_de_lieux_retires_sans_administrateur += 1

        if executer:
            ligne_des_suppressions = (
                f"{nombre_par_liste[LISTE_SUPPRIME]} lieux supprimés"
            )
            ligne_des_lieux_sans_administrateur = (
                f"{nombre_de_lieux_retires_sans_administrateur} lieux supprimés "
                f"sans administrateur (aucun mail)"
            )
        else:
            ligne_des_suppressions = (
                f"{nombre_par_liste[LISTE_A_SUPPRIMER]} lieux à supprimer (à blanc)"
            )
            ligne_des_lieux_sans_administrateur = (
                f"{nombre_de_lieux_retires_sans_administrateur} lieux à supprimer "
                f"sans administrateur (aucun mail)"
            )

        self.stdout.write("\nRésumé :")
        self.stdout.write(f"  {len(lieux_examines)} lieux examinés")
        self.stdout.write(f"  {ligne_des_suppressions}")
        self.stdout.write(f"  {ligne_des_lieux_sans_administrateur}")
        self.stdout.write(f"  {nombre_par_liste[LISTE_GARDE]} lieux gardés")
        self.stdout.write(f"  {nombre_par_liste[LISTE_ECHEC]} lieux en échec")
        self.stdout.write(
            f"  {nombre_d_emplacements_du_pool_ignores} emplacements du pool ignorés"
        )
        self.stdout.write(
            f"  {nombre_de_lieux_sans_domaine_ignores} autres lieux sans domaine principal ignorés"
        )
        self.stdout.write(f"  {len(domaines_inconnus)} domaines de la liste inconnus")
        self.stdout.write(f"  {nombre_de_mails_mis_en_file} mails mis en file")
        self.stdout.write(f"  durée : {duree_en_secondes:.1f} s")


# --------------------------------------------------------------------------
# Outils de la suppression
# / Deletion helpers
# --------------------------------------------------------------------------


def noter_la_suppression_apres_le_commit(
    lieux_supprimes_par_adresse, adresses_des_administrateurs, lieu_supprime
):
    """
    Appelée par `transaction.on_commit`, donc seulement si la suppression du lieu est
    validée : ajoute le lieu à la liste de chacun de ses administrateurs. Les mails
    partent une fois tous les lieux traités.
    / Called on commit only: adds the venue to each of its administrators' list.
    """
    for adresse in adresses_des_administrateurs:
        if adresse not in lieux_supprimes_par_adresse:
            lieux_supprimes_par_adresse[adresse] = []
        lieux_supprimes_par_adresse[adresse].append(lieu_supprime)


def nettoyer_les_liens_partages(curseur, uuid_du_lieu):
    """
    Vide ou supprime les liens du schéma public vers le lieu que l'outil sait nettoyer.
    Les utilisateurs et les portefeuilles sont GARDÉS. Une table absente est sautée.
    / Empties or deletes the public links to the venue. Users and wallets are KEPT.

    - `client_source` des utilisateurs -> vide ;
    - liens « acheteur » et « administrateur » du lieu -> supprimés ;
    - origine des portefeuilles -> vide ;
    - fiche d'onboarding du lieu -> supprimée (elle porte les coordonnées du demandeur) ;
    - invitations d'onboarding envoyées par le lieu -> supprimées (la fiche d'un autre
      lieu qui en a utilisé une garde sa fiche, sans l'invitation) ;
    - cache SEO du lieu -> supprimé.
    """
    if nettoyage_des_lieux.la_table_existe(
        curseur, "public", "AuthBillet_tibilletuser"
    ):
        curseur.execute(
            'UPDATE public."AuthBillet_tibilletuser" SET client_source_id = NULL '
            "WHERE client_source_id = %s::uuid",
            [uuid_du_lieu],
        )
    for nom_de_la_table_des_liens in [
        "AuthBillet_tibilletuser_client_achat",
        "AuthBillet_tibilletuser_client_admin",
    ]:
        if nettoyage_des_lieux.la_table_existe(
            curseur, "public", nom_de_la_table_des_liens
        ):
            curseur.execute(
                f"DELETE FROM {nom_complet('public', nom_de_la_table_des_liens)} "
                f"WHERE client_id = %s::uuid",
                [uuid_du_lieu],
            )
    if nettoyage_des_lieux.la_table_existe(curseur, "public", "AuthBillet_wallet"):
        curseur.execute(
            'UPDATE public."AuthBillet_wallet" SET origin_id = NULL WHERE origin_id = %s::uuid',
            [uuid_du_lieu],
        )
    if nettoyage_des_lieux.la_table_existe(
        curseur, "public", "MetaBillet_waitingconfiguration"
    ):
        curseur.execute(
            'DELETE FROM public."MetaBillet_waitingconfiguration" WHERE tenant_id = %s::uuid',
            [uuid_du_lieu],
        )
    if nettoyage_des_lieux.la_table_existe(
        curseur, "public", "onboard_onboardinvitation"
    ):
        colonnes_des_fiches = nettoyage_des_lieux.colonnes_de_la_table(
            curseur, "public", "MetaBillet_waitingconfiguration"
        )
        if "invitation_id" in colonnes_des_fiches:
            curseur.execute(
                'UPDATE public."MetaBillet_waitingconfiguration" SET invitation_id = NULL '
                'WHERE invitation_id IN (SELECT id FROM public."onboard_onboardinvitation" '
                "WHERE invited_by_tenant_id = %s::uuid)",
                [uuid_du_lieu],
            )
        curseur.execute(
            'DELETE FROM public."onboard_onboardinvitation" '
            "WHERE invited_by_tenant_id = %s::uuid",
            [uuid_du_lieu],
        )
    if nettoyage_des_lieux.la_table_existe(curseur, "public", "seo_seocache"):
        curseur.execute(
            'DELETE FROM public."seo_seocache" WHERE tenant_id = %s::uuid',
            [uuid_du_lieu],
        )


def message_sans_nom_de_schema(erreur, domaine_par_schema):
    """
    Le message d'une erreur, où chaque nom de schéma entre guillemets est remplacé par le
    domaine de son lieu : aucun nom de schéma ne sort de la commande.
    / The error message, with each quoted schema name replaced by its venue's domain.
    """
    message = str(erreur).strip().replace("\n", " ")
    for nom_du_schema, domaine in domaine_par_schema.items():
        remplacement = domaine or "lieu sans domaine principal"
        # PostgreSQL cite un schéma seul (`"schema"`) ou devant une table
        # (`"schema.table"`, `"schema"."table"`).
        # / PostgreSQL quotes a schema alone or in front of a table.
        message = message.replace(f'"{nom_du_schema}"', f"«{remplacement}»")
        message = message.replace(f'"{nom_du_schema}.', f"«{remplacement}».")
    return message


def construire_le_mail_d_un_administrateur(adresse, lieux_supprimes):
    """
    Le contexte du mail générique (BaseBillet/templates/emails/email_generique.html) pour
    un administrateur. Texte de la fiche §18. Des chaînes simples : le contexte passe
    par Celery (JSON).
    / Generic mail context for one administrator; plain strings (sent through Celery).
    """
    if len(lieux_supprimes) == 1:
        lieu_supprime = lieux_supprimes[0]
        texte_principal = gettext(
            "Votre espace TiBillet %(domaine)s, ouvert le %(date)s, n'a jamais été utilisé : "
            "aucun événement, aucune adhésion, aucune vente. Dans un souci de mutualisation, "
            "nous supprimons les espaces non utilisés : nous l'avons fermé et nous avons "
            "supprimé ses données."
        ) % {
            "domaine": lieu_supprime["domaine"],
            "date": date_format(lieu_supprime["date_de_creation"], "DATE_FORMAT"),
        }
    else:
        espaces_supprimes = []
        for lieu_supprime in lieux_supprimes:
            espaces_supprimes.append(
                gettext("%(domaine)s (ouvert le %(date)s)")
                % {
                    "domaine": lieu_supprime["domaine"],
                    "date": date_format(
                        lieu_supprime["date_de_creation"], "DATE_FORMAT"
                    ),
                }
            )
        texte_principal = gettext(
            "Vos espaces TiBillet %(espaces)s n'ont jamais été utilisés : aucun événement, "
            "aucune adhésion, aucune vente. Dans un souci de mutualisation, nous supprimons "
            "les espaces non utilisés : nous les avons fermés et nous avons supprimé leurs "
            "données."
        ) % {"espaces": ", ".join(espaces_supprimes)}

    return {
        "title": gettext("Votre espace TiBillet a été fermé"),
        "sub_title": "TiBillet",
        "username": adresse,
        "main_text": texte_principal,
        "main_text_2": gettext(
            "Si vous souhaitez en ouvrir un nouveau, n'hésitez pas à retourner sur "
            "https://tibillet.coop. Une nouvelle version de TiBillet arrive très bientôt."
        ),
        "main_text_3": gettext(
            "Vos données personnelles : votre compte TiBillet (votre adresse email) reste "
            "ouvert, car il peut servir sur d'autres lieux. Pour le supprimer aussi, "
            "répondez simplement à ce message. Conformément au RGPD, vous pouvez à tout "
            "moment demander l'accès à vos données, leur correction ou leur suppression."
        ),
        "end_text": gettext("Bien à vous"),
        "signature": gettext("L'équipe de la coopérative TiBillet"),
    }
