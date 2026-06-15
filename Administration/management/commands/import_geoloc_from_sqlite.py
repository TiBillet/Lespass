"""
Importe en base Lespass les coordonnees GPS et adresses validees depuis la
SQLite produite par l'outil ~/TiBillet/nominatim-review/.
/ Imports validated GPS coords + addresses from the nominatim-review SQLite.

LOCALISATION : Administration/management/commands/import_geoloc_from_sqlite.py

DRY-RUN PAR DEFAUT : la commande n'ecrit RIEN sans le flag --apply.
/ DRY-RUN BY DEFAULT: command writes NOTHING without --apply flag.

REGLE D'IMPORT :
- human_review_status='approved'        : coords Nominatim valides en l'etat.
  -> UPDATE PostalAddress.latitude/longitude depuis nominatim_*
  -> UPDATE adresse depuis proposed_* SEULEMENT si l'adresse Lespass est vide
- human_review_status='manual_override' : coords manuelles (drag) + adresse
  corrigee (recherche ou reverse).
  -> UPDATE PostalAddress.latitude/longitude depuis human_reviewed_*
  -> UPDATE adresse depuis human_reviewed_* SEULEMENT si Lespass vide
- Les autres status (rejected, pending) sont skip.

STUBS LEGACY (postgres_id IS NULL) :
- On CREE une nouvelle PostalAddress avec toutes les donnees
- On la rattache a Configuration.postal_address du tenant

SAFETY :
- Aucune adresse existante n'est ECRASEE : on n'ecrit dans street_address/etc
  que si le champ est NULL ou vide cote Lespass.
- Transaction atomique PAR TENANT : si une erreur sur 1 PA, on rollback
  juste les PA de ce tenant, pas les autres.
- Tenant_context() obligatoire pour chaque ecriture (TENANT_APP).

USAGE :
    # 1. Recuperer la SQLite depuis le poste du mainteneur
    scp jonas@poste:~/TiBillet/nominatim-review/geocoded.sqlite /tmp/

    # 2. DRY-RUN (recommande, defaut)
    docker exec lespass_django poetry run python manage.py \\
        import_geoloc_from_sqlite /tmp/geocoded.sqlite

    # 3. Apres validation, APPLY pour vraiment ecrire
    docker exec lespass_django poetry run python manage.py \\
        import_geoloc_from_sqlite /tmp/geocoded.sqlite --apply

    # Tests : limiter aux N premieres entrees
    manage.py import_geoloc_from_sqlite /tmp/geocoded.sqlite --limit 5

    # Cibler un seul tenant
    manage.py import_geoloc_from_sqlite /tmp/geocoded.sqlite --schema=raffinerie
"""

import argparse
import sqlite3
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand
from django.db import transaction
from django_tenants.utils import tenant_context

from BaseBillet.models import Configuration, PostalAddress
from Customers.models import Client


# Tolerance pour parser une coord string en Decimal.
# / Tolerance for parsing a string coord into Decimal.
def parser_coord(valeur_str):
    """
    Convertit une chaine de coord en Decimal. Renvoie None si vide/invalide.
    / Converts a coord string to Decimal. Returns None if empty/invalid.
    """
    if valeur_str is None:
        return None
    valeur_str = str(valeur_str).strip()
    if not valeur_str:
        return None
    try:
        return Decimal(valeur_str)
    except (InvalidOperation, ValueError):
        return None


def chaine_non_vide(valeur):
    """
    True si la valeur est une string non vide (apres strip).
    / True if value is a non-empty string (after strip).
    """
    return valeur is not None and str(valeur).strip() != ""


class Command(BaseCommand):
    help = "Importe coords + adresses validees depuis une SQLite nominatim-review."

    def add_arguments(self, parser):
        parser.formatter_class = argparse.RawTextHelpFormatter
        parser.description = (
            "Importe en base Lespass les coordonnees GPS et adresses validees\n"
            "depuis la SQLite produite par l'outil nominatim-review.\n\n"
            "PAR DEFAUT : DRY-RUN (n'ecrit rien).\n"
            "Ajouter --apply pour vraiment ecrire.\n\n"
            "Exemples :\n"
            "  manage.py import_geoloc_from_sqlite /tmp/geocoded.sqlite\n"
            "  manage.py import_geoloc_from_sqlite /tmp/geocoded.sqlite --apply\n"
            "  manage.py import_geoloc_from_sqlite /tmp/geocoded.sqlite --limit 5\n"
            "  manage.py import_geoloc_from_sqlite /tmp/geocoded.sqlite --schema=raffinerie"
        )
        parser.add_argument(
            "sqlite_path", type=str,
            help="Chemin vers la SQLite produite par nominatim-review.",
        )
        parser.add_argument(
            "--apply", action="store_true",
            help="Applique vraiment les changements. Par defaut : DRY-RUN.",
        )
        parser.add_argument(
            "--limit", type=int, default=None,
            help="Limite aux N premieres entrees (utile pour tester).",
        )
        parser.add_argument(
            "--schema", type=str, default=None,
            help="Limiter a un seul tenant_schema (pour test cible).",
        )

    def handle(self, *args, **options):
        chemin_sqlite = options["sqlite_path"]
        dry_run = not options["apply"]
        limite = options["limit"]
        filtre_schema = options["schema"]

        # Banner explicite pour le mode
        # / Explicit banner for the mode
        if dry_run:
            self.stdout.write(self.style.WARNING(
                "\n=== MODE DRY-RUN : aucune ecriture en base ===\n"
                "Ajouter --apply pour vraiment importer.\n"
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                "\n=== MODE APPLY : ecritures reelles en base ===\n"
            ))

        # Lecture des PA a importer
        # / Read PAs to import
        connexion = sqlite3.connect(chemin_sqlite)
        connexion.row_factory = sqlite3.Row

        clauses_where = ["human_review_status IN ('approved', 'manual_override')"]
        parametres = []
        if filtre_schema:
            clauses_where.append("tenant_schema = ?")
            parametres.append(filtre_schema)

        requete = f"""
            SELECT * FROM postal_addresses
            WHERE {' AND '.join(clauses_where)}
            ORDER BY tenant_schema, id
        """
        if limite is not None:
            requete += f" LIMIT {int(limite)}"

        pa_a_importer = connexion.execute(requete, parametres).fetchall()
        connexion.close()

        # Groupage par tenant_schema pour transactions par tenant
        # / Group by tenant_schema for per-tenant transactions
        groupes_par_tenant = {}
        for row in pa_a_importer:
            schema = row["tenant_schema"]
            groupes_par_tenant.setdefault(schema, []).append(row)

        self.stdout.write(
            f"PA a traiter : {len(pa_a_importer)} "
            f"reparties sur {len(groupes_par_tenant)} tenants\n"
        )

        # Compteurs globaux
        # / Global counters
        compteurs = {
            "update_coords_only": 0,
            "update_coords_and_address": 0,
            "create_from_stub": 0,
            "promoted_to_main": 0,
            "skip_tenant_introuvable": 0,
            "skip_pa_introuvable": 0,
            "skip_pas_de_coords": 0,
            "skip_config_introuvable": 0,
            "erreur": 0,
        }

        # Boucle par tenant
        # / Per-tenant loop
        for schema, rows_du_tenant in groupes_par_tenant.items():
            try:
                tenant = Client.objects.get(schema_name=schema)
            except Client.DoesNotExist:
                self.stderr.write(self.style.ERROR(
                    f"[{schema}] tenant introuvable -> {len(rows_du_tenant)} PA skip"
                ))
                compteurs["skip_tenant_introuvable"] += len(rows_du_tenant)
                continue

            self.stdout.write(f"\n[{schema}] ({len(rows_du_tenant)} PA)")

            with tenant_context(tenant):
                # Transaction atomique par tenant : si une PA plante,
                # on rollback les autres PA de CE tenant uniquement.
                # / Atomic per-tenant transaction.
                try:
                    with transaction.atomic():
                        for row in rows_du_tenant:
                            self._traiter_une_pa(row, dry_run, compteurs)
                        # En DRY-RUN, on force le rollback meme si tout OK,
                        # pour ne RIEN ecrire en base.
                        # / In DRY-RUN, force rollback to write NOTHING.
                        if dry_run:
                            raise _RollbackDryRun()
                except _RollbackDryRun:
                    pass  # rollback normal du dry-run
                except Exception as erreur:
                    self.stderr.write(self.style.ERROR(
                        f"  [{schema}] ROLLBACK transaction : {type(erreur).__name__}: {erreur}"
                    ))
                    compteurs["erreur"] += len(rows_du_tenant)

        # Stats finales
        # / Final stats
        self.stdout.write(self.style.SUCCESS(
            f"\n=== STATS {'DRY-RUN' if dry_run else 'APPLY'} ===\n"
            f"UPDATE coords seules           : {compteurs['update_coords_only']}\n"
            f"UPDATE coords + adresse        : {compteurs['update_coords_and_address']}\n"
            f"CREATE PostalAddress (stubs)   : {compteurs['create_from_stub']}\n"
            f"PROMOTE en adresse principale  : {compteurs['promoted_to_main']}\n"
            f"Skip (tenant introuvable)      : {compteurs['skip_tenant_introuvable']}\n"
            f"Skip (PA postgres_id absente)  : {compteurs['skip_pa_introuvable']}\n"
            f"Skip (pas de coords valides)   : {compteurs['skip_pas_de_coords']}\n"
            f"Skip (Configuration absente)   : {compteurs['skip_config_introuvable']}\n"
            f"Erreurs (rollback tenant)      : {compteurs['erreur']}\n"
        ))

        if dry_run:
            self.stdout.write(self.style.WARNING(
                "\nRAPPEL : DRY-RUN, aucune ecriture effectuee.\n"
                "Relancer avec --apply pour appliquer.\n"
            ))

    def _traiter_une_pa(self, row, dry_run, compteurs):
        """
        Traite une PA de la SQLite. Decide UPDATE existant ou CREATE stub.
        Affiche le diff prevu (utile en dry-run).
        / Processes a SQLite PA. Decides UPDATE or CREATE stub.
        Prints the planned diff (useful in dry-run).
        """
        status = row["human_review_status"]
        postgres_id = row["postgres_id"]
        prefixe_log = f"  pa#{row['id']} ({status})"

        # Choix des coords + adresse selon le status
        # / Pick coords + address based on status
        if status == "manual_override":
            lat = parser_coord(row["human_reviewed_latitude"])
            lng = parser_coord(row["human_reviewed_longitude"])
            adresse_source = {
                "street_address": row["human_reviewed_street_address"],
                "address_locality": row["human_reviewed_address_locality"],
                "postal_code": row["human_reviewed_postal_code"],
                "address_country": row["human_reviewed_address_country"],
            }
        else:  # approved
            lat = parser_coord(row["nominatim_latitude"])
            lng = parser_coord(row["nominatim_longitude"])
            adresse_source = {
                "street_address": row["proposed_street_address"],
                "address_locality": row["proposed_address_locality"],
                "postal_code": row["proposed_postal_code"],
                "address_country": row["proposed_address_country"],
            }

        if lat is None or lng is None:
            self.stdout.write(f"{prefixe_log} SKIP (pas de coords valides)")
            compteurs["skip_pas_de_coords"] += 1
            return

        # Cas 1 : Stub legacy (postgres_id IS NULL) -> CREATE + rattache a Configuration
        # / Case 1: legacy stub -> CREATE + attach to Configuration
        if postgres_id is None:
            self._creer_stub(row, lat, lng, adresse_source, dry_run, compteurs, prefixe_log)
            return

        # Cas 2 : PostalAddress existante -> UPDATE
        # / Case 2: existing PostalAddress -> UPDATE
        try:
            postal_address = PostalAddress.objects.get(pk=postgres_id)
        except PostalAddress.DoesNotExist:
            self.stdout.write(self.style.WARNING(
                f"{prefixe_log} SKIP (PostalAddress pk={postgres_id} introuvable)"
            ))
            compteurs["skip_pa_introuvable"] += 1
            return

        # Champs adresse a remplir : on n'ECRASE jamais l'existant.
        # / Address fields to fill: never OVERWRITE existing values.
        adresse_a_ecrire = {}
        for champ, valeur_proposee in adresse_source.items():
            valeur_actuelle = getattr(postal_address, champ)
            if chaine_non_vide(valeur_proposee) and not chaine_non_vide(valeur_actuelle):
                adresse_a_ecrire[champ] = valeur_proposee

        # Log du diff
        # / Diff log
        modifications = [f"lat={lat}", f"lng={lng}"]
        for champ, valeur in adresse_a_ecrire.items():
            modifications.append(f"{champ}={valeur!r}")
        self.stdout.write(f"{prefixe_log} UPDATE pa pk={postgres_id} : {', '.join(modifications)}")

        if not dry_run:
            postal_address.latitude = lat
            postal_address.longitude = lng
            for champ, valeur in adresse_a_ecrire.items():
                setattr(postal_address, champ, valeur)
            postal_address.save(update_fields=["latitude", "longitude"] + list(adresse_a_ecrire.keys()))

        if adresse_a_ecrire:
            compteurs["update_coords_and_address"] += 1
        else:
            compteurs["update_coords_only"] += 1

        # Promotion eventuelle : si la PA mise a jour est la SEULE du tenant
        # ET que Configuration n'a pas encore de postal_address, on la promeut
        # en adresse principale. Cas typique : tenant qui avait declare son
        # lieu seulement via un Event, jamais lie a Configuration.
        # / Possible promotion: if updated PA is the ONLY one in this tenant
        # AND Configuration has no postal_address yet, promote to main address.
        self._promouvoir_en_principale_si_seule(
            postal_address, dry_run, compteurs, prefixe_log
        )

    def _promouvoir_en_principale_si_seule(self, postal_address, dry_run, compteurs, prefixe_log):
        """
        Promeut la PA en adresse principale (Configuration.postal_address) SI :
        - Configuration.postal_address est NULL (pas d'adresse principale set)
        - ET cette PA est la SEULE du tenant (count == 1)
        / Promotes PA to main address if no main yet AND only PA in tenant.

        Sinon, ne fait rien (silencieux).
        / Otherwise does nothing (silent).
        """
        configuration = Configuration.objects.first()
        if configuration is None:
            return
        if configuration.postal_address_id is not None:
            # Une adresse principale est deja set, on n'ecrase pas.
            # / Main address already set, don't overwrite.
            return
        nombre_pa_dans_tenant = PostalAddress.objects.count()
        if nombre_pa_dans_tenant != 1:
            # Plusieurs PA dans le tenant : on ne sait pas laquelle est
            # la principale, on laisse l'humain decider.
            # / Multiple PAs in tenant: don't guess which is main.
            return

        self.stdout.write(self.style.SUCCESS(
            f"{prefixe_log}   -> PROMOTE en adresse principale "
            f"(Configuration.postal_address = pa pk={postal_address.pk}, "
            f"seule PA du tenant)"
        ))
        if not dry_run:
            configuration.postal_address = postal_address
            configuration.save(update_fields=["postal_address"])
        compteurs["promoted_to_main"] += 1

    def _creer_stub(self, row, lat, lng, adresse_source, dry_run, compteurs, prefixe_log):
        """
        Cree une PostalAddress et la rattache a Configuration.postal_address.
        Cas des stubs legacy (postgres_id=NULL) cote SQLite.
        / Creates a PostalAddress and attaches it to Configuration.postal_address.
        """
        try:
            configuration = Configuration.objects.first()
        except Exception:
            configuration = None
        if configuration is None:
            self.stdout.write(self.style.WARNING(
                f"{prefixe_log} SKIP (Configuration introuvable pour ce tenant)"
            ))
            compteurs["skip_config_introuvable"] += 1
            return

        # Si Configuration a deja une postal_address, on ne cree pas un doublon :
        # on UPDATE celle qui existe deja.
        # / If Configuration already has a postal_address, update that instead.
        if configuration.postal_address_id is not None:
            self.stdout.write(self.style.WARNING(
                f"{prefixe_log} stub mais Configuration.postal_address_id="
                f"{configuration.postal_address_id} existe deja : UPDATE en place"
            ))
            self._updater_pa_existante_pour_stub(
                configuration.postal_address, lat, lng, adresse_source,
                dry_run, compteurs, prefixe_log,
            )
            return

        # CREATE une nouvelle PostalAddress
        # / CREATE a new PostalAddress
        donnees_create = {
            "name": row["name"] or configuration.organisation,
            "latitude": lat,
            "longitude": lng,
            "street_address": adresse_source["street_address"] or "",
            "address_locality": adresse_source["address_locality"] or "",
            "postal_code": adresse_source["postal_code"] or "",
            "address_country": adresse_source["address_country"] or "",
        }
        self.stdout.write(
            f"{prefixe_log} CREATE PostalAddress + lier a Configuration : "
            f"{donnees_create['name']!r} ({lat}, {lng}) - "
            f"{donnees_create['street_address']!r}, {donnees_create['address_locality']!r}"
        )

        if not dry_run:
            nouvelle_pa = PostalAddress.objects.create(**donnees_create)
            configuration.postal_address = nouvelle_pa
            configuration.save(update_fields=["postal_address"])

        compteurs["create_from_stub"] += 1

    def _updater_pa_existante_pour_stub(self, postal_address, lat, lng, adresse_source,
                                        dry_run, compteurs, prefixe_log):
        """
        Cas particulier : un stub SQLite mais Configuration.postal_address est
        deja set cote Lespass (a ete cree entre l'export et l'import).
        On update cette PA au lieu d'en creer une 2eme.
        / Edge case: stub in SQLite but PA already exists in Lespass.
        Update that PA instead of creating a duplicate.
        """
        adresse_a_ecrire = {}
        for champ, valeur_proposee in adresse_source.items():
            valeur_actuelle = getattr(postal_address, champ)
            if chaine_non_vide(valeur_proposee) and not chaine_non_vide(valeur_actuelle):
                adresse_a_ecrire[champ] = valeur_proposee
        modifications = [f"lat={lat}", f"lng={lng}"]
        for champ, valeur in adresse_a_ecrire.items():
            modifications.append(f"{champ}={valeur!r}")
        self.stdout.write(
            f"{prefixe_log}   -> UPDATE pa pk={postal_address.pk} : {', '.join(modifications)}"
        )
        if not dry_run:
            postal_address.latitude = lat
            postal_address.longitude = lng
            for champ, valeur in adresse_a_ecrire.items():
                setattr(postal_address, champ, valeur)
            postal_address.save(update_fields=["latitude", "longitude"] + list(adresse_a_ecrire.keys()))
        if adresse_a_ecrire:
            compteurs["update_coords_and_address"] += 1
        else:
            compteurs["update_coords_only"] += 1


# Exception sentinelle interne pour rollback intentionnel en dry-run.
# / Internal sentinel exception for intentional rollback in dry-run.
class _RollbackDryRun(Exception):
    pass
