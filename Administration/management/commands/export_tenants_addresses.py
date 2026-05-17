"""
Exporte en JSON les adresses et coordonnees GPS de tous les tenants actifs.
/ Exports addresses and GPS coordinates of all active tenants as JSON.

LOCALISATION : Administration/management/commands/export_tenants_addresses.py

But : recenser les ~400 structures qui n'ont pas encore renseigne leur
adresse postale ou leur point de geolocalisation, pour pouvoir leur
envoyer un email de relance.
/ Goal: list the ~400 organisations that have not yet filled in their
postal address or GPS point, in order to send them a follow-up email.

USAGE :
    docker exec lespass_django poetry run python manage.py export_tenants_addresses
    docker exec lespass_django poetry run python manage.py export_tenants_addresses --output=/tmp/tenants.json
    docker exec lespass_django poetry run python manage.py export_tenants_addresses --only-incomplete --output=/tmp/a_relancer.json

Marche aussi sur un dump SQL restaure localement : il suffit de pointer
DATABASE_URL sur la base locale et de lancer la commande dans le container
Lespass. Aucune ecriture en base : commande 100 % lecture seule.
/ Also works on a locally restored SQL dump: just point DATABASE_URL to the
local database and run the command in the Lespass container. Zero writes:
this command is 100 % read-only.

FLUX :
1. Liste tous les Client (modele tenant django-tenants) hors public + categories non-actives
2. Pour chacun : tenant_context(tenant) -> lit Configuration.objects.first() (PAS get_solo, pour ne RIEN creer)
3. Recupere l'adresse "legacy" (champs adress/postal_code/city sur Configuration)
   ET l'adresse schema.org (FK postal_address avec lat/long)
4. Annote chaque ligne avec has_address / has_geoloc
5. Sortie JSON sur stdout, stats sur stderr

DEPENDENCIES :
- Customers.Client : modele tenant (TenantMixin, SHARED_APPS)
- BaseBillet.Configuration : singleton TENANT_APP (django-solo)
- BaseBillet.PostalAddress : adresse schema.org (TENANT_APP)
"""

import argparse
import json

from django.core.management.base import BaseCommand
from django_tenants.utils import tenant_context

from BaseBillet.models import Configuration
from Customers.models import Client


# Categories de Client a exclure (cf. Customers/models.py:17).
# / Client categories to skip.
# - 'M' = META  (tenant racine meta)
# - 'R' = ROOT  (tenant landing root)
# - 'W' = WAITING_CONFIG (brouillons d'onboarding, pas encore actifs)
CATEGORIES_A_EXCLURE = ("M", "R", "W")


class Command(BaseCommand):
    help = "Exporte en JSON les adresses et coordonnees GPS de tous les tenants actifs."

    def add_arguments(self, parser):
        parser.formatter_class = argparse.RawTextHelpFormatter
        parser.description = (
            "Exporte en JSON l'adresse et la geoloc de chaque tenant actif.\n"
            "Marche sur prod ET sur dump local. Aucune ecriture en base.\n\n"
            "Exemples :\n"
            "  manage.py export_tenants_addresses\n"
            "  manage.py export_tenants_addresses --output=/tmp/tenants.json\n"
            "  manage.py export_tenants_addresses --only-incomplete --output=/tmp/a_relancer.json"
        )
        parser.add_argument(
            "--output",
            type=str,
            default=None,
            help="Chemin du fichier de sortie. Par defaut : stdout.",
        )
        parser.add_argument(
            "--only-incomplete",
            action="store_true",
            help="Ne sort que les tenants sans adresse OU sans geoloc.",
        )

    def handle(self, *args, **options):
        chemin_sortie = options["output"]
        seulement_incomplets = options["only_incomplete"]

        # On exclut le schema public et les categories non-utilisateur.
        # / Skip the public schema and non-user categories.
        tenants_a_exporter = (
            Client.objects
            .exclude(schema_name="public")
            .exclude(categorie__in=CATEGORIES_A_EXCLURE)
            .order_by("schema_name")
        )

        lignes_export = []
        nombre_total = 0
        nombre_sans_configuration = 0
        nombre_sans_adresse = 0
        nombre_sans_geoloc = 0

        for tenant in tenants_a_exporter:
            nombre_total += 1

            # Bascule dans le schema du tenant pour lire sa Configuration.
            # / Switch to the tenant's schema to read its Configuration.
            with tenant_context(tenant):
                # On utilise .first() et PAS get_solo() pour ne creer aucune row.
                # / Use .first() (not get_solo) so we never auto-create rows.
                configuration_du_tenant = Configuration.objects.first()

                if configuration_du_tenant is None:
                    nombre_sans_configuration += 1
                    lignes_export.append({
                        "schema": tenant.schema_name,
                        "tenant_name": tenant.name,
                        "categorie": tenant.categorie,
                        "configuration_manquante": True,
                    })
                    continue

                # Adresse "legacy" : champs directement sur Configuration.
                # / Legacy address: fields directly on Configuration.
                adresse_legacy = {
                    "adress": configuration_du_tenant.adress,
                    "postal_code": configuration_du_tenant.postal_code,
                    "city": configuration_du_tenant.city,
                }

                # Adresse schema.org : FK PostalAddress, peut etre None.
                # / Schema.org address: FK PostalAddress, may be None.
                adresse_schema_org = None
                postal_address = configuration_du_tenant.postal_address
                if postal_address is not None:
                    # On convertit Decimal -> str pour eviter les soucis JSON.
                    # / Convert Decimal -> str to avoid JSON serialization issues.
                    latitude_str = None
                    if postal_address.latitude is not None:
                        latitude_str = str(postal_address.latitude)
                    longitude_str = None
                    if postal_address.longitude is not None:
                        longitude_str = str(postal_address.longitude)

                    adresse_schema_org = {
                        "name": postal_address.name,
                        "street_address": postal_address.street_address,
                        "address_locality": postal_address.address_locality,
                        "postal_code": postal_address.postal_code,
                        "address_country": postal_address.address_country,
                        "latitude": latitude_str,
                        "longitude": longitude_str,
                    }

                # Flags de completion. "Adresse" = au moins un champ rempli
                # cote schema.org OU cote legacy. "Geoloc" = lat ET long.
                # / Completion flags. "Address" = at least one filled field on
                # schema.org OR legacy side. "Geoloc" = both lat AND long.
                a_une_adresse = bool(
                    (postal_address is not None and postal_address.street_address)
                    or configuration_du_tenant.adress
                )
                a_une_geoloc = bool(
                    postal_address is not None
                    and postal_address.latitude is not None
                    and postal_address.longitude is not None
                )

                if not a_une_adresse:
                    nombre_sans_adresse += 1
                if not a_une_geoloc:
                    nombre_sans_geoloc += 1

                # Filtre --only-incomplete : on skip si tout est rempli.
                # / --only-incomplete filter: skip if everything is filled.
                if seulement_incomplets and a_une_adresse and a_une_geoloc:
                    continue

                lignes_export.append({
                    "schema": tenant.schema_name,
                    "tenant_name": tenant.name,
                    "categorie": tenant.categorie,
                    "organisation": configuration_du_tenant.organisation,
                    "email": configuration_du_tenant.email,
                    "phone": configuration_du_tenant.phone,
                    "site_web": configuration_du_tenant.site_web,
                    "adresse_legacy": adresse_legacy,
                    "adresse_schema_org": adresse_schema_org,
                    "has_address": a_une_adresse,
                    "has_geoloc": a_une_geoloc,
                })

        # Stats sur stderr : le JSON reste propre sur stdout pour `> fichier.json`.
        # / Stats on stderr so stdout JSON stays clean for `> file.json`.
        self.stderr.write(self.style.SUCCESS(
            "\n--- Stats export tenants ---\n"
            f"Total tenants parcourus  : {nombre_total}\n"
            f"Sans Configuration       : {nombre_sans_configuration}\n"
            f"Sans adresse             : {nombre_sans_adresse}\n"
            f"Sans geoloc (lat/long)   : {nombre_sans_geoloc}\n"
            f"Lignes exportees         : {len(lignes_export)}\n"
        ))

        # Sortie JSON : fichier si --output, sinon stdout.
        # / JSON output: file if --output, stdout otherwise.
        contenu_json = json.dumps(lignes_export, indent=2, ensure_ascii=False)
        if chemin_sortie:
            with open(chemin_sortie, "w", encoding="utf-8") as fichier:
                fichier.write(contenu_json)
            self.stderr.write(self.style.SUCCESS(f"JSON ecrit dans : {chemin_sortie}"))
        else:
            self.stdout.write(contenu_json)
