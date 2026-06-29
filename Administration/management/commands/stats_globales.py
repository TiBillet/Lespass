"""
Statistiques globales multi-tenant, en UNE seule requete SQL.
/ Global multi-tenant statistics, in a SINGLE SQL query.

LOCALISATION : Administration/management/commands/stats_globales.py

But : compter, sur toute l'instance TiBillet, le nombre de lieux actifs, les
events passes et futurs, les produits d'adhesion, et les utilisateurs — sans
boucler tenant par tenant.
/ Goal: count, across the whole TiBillet instance, active venues, past/future
events, membership products, and users — without looping tenant by tenant.

DEFINITION "lieu actif" : un tenant qui a AU MOINS un event (passe ou futur)
OU au moins un produit d'adhesion.
/ "active venue" = a tenant with AT LEAST one event (past or future) OR at
least one membership product.

POURQUOI UN SEUL SQL ?
Avec django-tenants, les tables Event et Product vivent dans CHAQUE schema
tenant (pas de table commune). Boucler avec tenant_context ferait N changements
de search_path + N requetes. A la place, on construit un seul SQL avec UNION ALL
sur tous les schemas : 1 seul aller-retour DB. Les users (AuthBillet) sont en
SHARED_APPS (schema public) : 1 requete directe.
/ With django-tenants, Event and Product tables live in EACH tenant schema (no
shared table). Looping with tenant_context means N search_path switches + N
queries. Instead we build a single UNION ALL SQL over all schemas: 1 DB round
trip. Users (AuthBillet) are in SHARED_APPS (public schema): 1 direct query.

USAGE :
    docker exec lespass_django poetry run python manage.py stats_globales
    docker exec lespass_django poetry run python manage.py stats_globales --json

Commande 100 % lecture seule. Aucune ecriture en base.
/ 100 % read-only command. Zero database writes.

DEPENDENCIES :
- Customers.Client : modele tenant (SHARED_APPS), fournit la liste des schemas
- AuthBillet.TibilletUser : modele user (SHARED_APPS, schema public)
- BaseBillet.Event / Product : tables par schema, lues en SQL brut
"""

import argparse
import json

from django.core.management.base import BaseCommand
from django.db import connection

from AuthBillet.models import TibilletUser
from Customers.models import Client


# Categories de Client a exclure : ce ne sont pas des lieux reels.
# / Client categories to skip: these are not real venues.
# - 'M' = META  (agregateur d'evenements)
# - 'R' = ROOT  (tenant landing public)
# - 'W' = WAITING_CONFIG (brouillons d'onboarding, pas encore actifs)
CATEGORIES_A_EXCLURE = ("M", "R", "W")

# Code categorie d'un produit d'adhesion (cf. BaseBillet.Product.ADHESION).
# / Category code of a membership product.
CATEGORIE_ADHESION = "A"


class Command(BaseCommand):
    help = "Statistiques globales multi-tenant (lieux actifs, events, adhesions, users) en une seule requete."

    def add_arguments(self, parser):
        parser.formatter_class = argparse.RawTextHelpFormatter
        parser.add_argument(
            "--json",
            action="store_true",
            dest="format_json",
            help="Sort les stats en JSON sur stdout au lieu du tableau lisible.",
        )

    def handle(self, *args, **options):
        format_json = options["format_json"]

        # 1) Users : SHARED_APPS -> schema public -> une seule requete.
        # / Users: SHARED_APPS -> public schema -> single query.
        nombre_utilisateurs = TibilletUser.objects.count()

        # 2) Liste des schemas tenants (hors public + hors categories non-lieux).
        # / List of tenant schemas (excluding public + non-venue categories).
        schemas = list(
            Client.objects
            .exclude(schema_name="public")
            .exclude(categorie__in=CATEGORIES_A_EXCLURE)
            .order_by("schema_name")
            .values_list("schema_name", flat=True)
        )

        # Cas limite : aucun tenant. On evite un SQL vide.
        # / Edge case: no tenant. Avoid an empty SQL string.
        lignes_par_lieu = []
        if schemas:
            # On construit un morceau de SELECT par schema, puis UNION ALL.
            # Les noms de schemas viennent de la DB (pas d'input utilisateur) et
            # sont valides par django-tenants ; on les quote en double guillemets.
            # / One SELECT chunk per schema, joined by UNION ALL. Schema names
            # come from the DB (not user input) and are validated by
            # django-tenants; we double-quote them.
            morceaux = []
            for schema in schemas:
                morceaux.append(f'''
                    SELECT
                      '{schema}' AS schema,
                      (SELECT count(*) FROM "{schema}"."BaseBillet_event"
                         WHERE datetime <  now()) AS events_passes,
                      (SELECT count(*) FROM "{schema}"."BaseBillet_event"
                         WHERE datetime >= now()) AS events_futurs,
                      (SELECT count(*) FROM "{schema}"."BaseBillet_product"
                         WHERE categorie_article = '{CATEGORIE_ADHESION}') AS produits_adhesion
                ''')
            sql = " UNION ALL ".join(morceaux)

            with connection.cursor() as curseur:
                curseur.execute(sql)
                lignes_par_lieu = curseur.fetchall()

        # 3) Agregation en Python (les volumes sont petits : un lieu par row).
        # / Aggregate in Python (small volume: one venue per row).
        lieux_actifs = 0
        total_events_passes = 0
        total_events_futurs = 0
        total_produits_adhesion = 0
        detail_lieux = []

        for schema, events_passes, events_futurs, produits_adhesion in lignes_par_lieu:
            # Un lieu est actif s'il a au moins un event OU un produit d'adhesion.
            # / A venue is active if it has at least one event OR membership product.
            est_actif = (events_passes + events_futurs) > 0 or produits_adhesion > 0
            if est_actif:
                lieux_actifs += 1
            total_events_passes += events_passes
            total_events_futurs += events_futurs
            total_produits_adhesion += produits_adhesion
            detail_lieux.append({
                "schema": schema,
                "events_passes": events_passes,
                "events_futurs": events_futurs,
                "produits_adhesion": produits_adhesion,
                "actif": est_actif,
            })

        # 4) Sortie : JSON brut ou tableau lisible.
        # / Output: raw JSON or human-readable table.
        if format_json:
            resultat = {
                "lieux_total": len(schemas),
                "lieux_actifs": lieux_actifs,
                "events_passes": total_events_passes,
                "events_futurs": total_events_futurs,
                "produits_adhesion": total_produits_adhesion,
                "utilisateurs": nombre_utilisateurs,
                "detail_lieux": detail_lieux,
            }
            self.stdout.write(json.dumps(resultat, indent=2, ensure_ascii=False))
            return

        # Tableau detail par lieu.
        # / Per-venue detail table.
        self.stdout.write("")
        self.stdout.write(f"{'Lieu':32} {'passes':>7} {'futurs':>7} {'adhes':>6}  actif")
        self.stdout.write("-" * 64)
        for lieu in detail_lieux:
            marque_actif = "OUI" if lieu["actif"] else "non"
            self.stdout.write(
                f"{lieu['schema']:32} "
                f"{lieu['events_passes']:>7} "
                f"{lieu['events_futurs']:>7} "
                f"{lieu['produits_adhesion']:>6}  "
                f"{marque_actif}"
            )

        # Synthese globale.
        # / Global summary.
        self.stdout.write("=" * 64)
        self.stdout.write(self.style.SUCCESS(
            f"Lieux actifs         : {lieux_actifs} / {len(schemas)}\n"
            f"Events passes        : {total_events_passes}\n"
            f"Events futurs        : {total_events_futurs}\n"
            f"Produits d'adhesion  : {total_produits_adhesion}\n"
            f"Utilisateurs (total) : {nombre_utilisateurs}"
        ))
