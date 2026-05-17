"""
Exporte en JSON les tenants + leurs PostalAddress (une par row), pour permettre
un backfill geoloc en local via Nominatim.
/ Exports tenants + their PostalAddress entries (one per row), to enable
local geocoding backfill via Nominatim.

LOCALISATION : Administration/management/commands/export_tenants_addresses.py

But : recenser les structures qui ont des PostalAddress sans geoloc (lat/long)
pour pouvoir leur envoyer un email de relance ou completer automatiquement
via OpenStreetMap.
/ Goal: list the organisations whose PostalAddress lacks geoloc (lat/long)
to send them a follow-up email or auto-complete via OpenStreetMap.

USAGE :
    docker exec lespass_django poetry run python manage.py export_tenants_addresses
    docker exec lespass_django poetry run python manage.py export_tenants_addresses --output=/tmp/tenants.json
    docker exec lespass_django poetry run python manage.py export_tenants_addresses --only-incomplete

Marche aussi sur un dump SQL restaure localement : il suffit de pointer
DATABASE_URL sur la base locale et de lancer la commande dans le container
Lespass. Aucune ecriture en base : commande 100 % lecture seule.
/ Also works on a locally restored SQL dump. Zero writes: 100 % read-only.

STRUCTURE DE SORTIE :
{
  "tenants": [
    {schema, tenant_name, categorie, organisation, email, phone, site_web,
     legacy_adress, legacy_postal_code, legacy_city, configuration_manquante}
  ],
  "postal_addresses": [
    {tenant_schema, postgres_id, is_main_address, name, street_address,
     address_locality, postal_code, address_country, latitude, longitude}
  ]
}

is_main_address (bool) :
- True  : cette PA est celle referencee par Configuration.postal_address
          (l'adresse du lieu principal du tenant). Aussi True pour les stubs
          legacy puisqu'ils representent l'adresse principale.
- False : cette PA est uniquement referencee par des Events (ou orpheline).
Utile pour prioriser la revue humaine : l'adresse principale compte plus
qu'une adresse d'event ponctuel.
/ is_main_address (bool):
- True : PA referenced by Configuration.postal_address (tenant main address).
         Also True for legacy stubs since they represent the main address.
- False: PA only referenced by Events (or orphaned).
Useful for prioritizing human review.

DEDUPLICATION NATIVE : on tape directement la table PostalAddress du tenant
(PostalAddress.objects.all()), donc chaque PA n'apparait qu'une fois meme si
plusieurs modeles (Configuration, Event(s)) la referencent.
/ NATIVE DEDUPLICATION: we query the tenant's PostalAddress table directly,
so each PA appears once even if multiple models reference it.

postgres_id :
- entier > 0 : id de la PostalAddress reelle dans Lespass (pour reimport via UPDATE)
- NULL       : stub legacy genere quand Configuration n'a pas de FK PostalAddress
               mais a les anciens champs adress/city remplis. L'import devra
               CREER une nouvelle PostalAddress et la lier a Configuration.

FLUX :
1. Liste les Client (modele tenant) hors public + categories non-actives
2. Pour chacun : tenant_context(tenant) -> lit Configuration + PostalAddress.objects.all()
3. Si Configuration n'a pas de FK postal_address mais a un adress legacy : stub
4. Sortie JSON sur stdout (ou --output), stats sur stderr

DEPENDENCIES :
- Customers.Client : modele tenant (SHARED_APPS)
- BaseBillet.Configuration : singleton TENANT_APP
- BaseBillet.PostalAddress : adresse schema.org (TENANT_APP)
"""

import argparse
import json

from django.core.management.base import BaseCommand
from django.db.models import Q
from django_tenants.utils import tenant_context

from BaseBillet.models import Configuration, PostalAddress
from Customers.models import Client


# Categories de Client a exclure (cf. Customers/models.py:17).
# / Client categories to skip.
# - 'M' = META  (tenant racine meta)
# - 'R' = ROOT  (tenant landing root)
# - 'W' = WAITING_CONFIG (brouillons d'onboarding, pas encore actifs)
CATEGORIES_A_EXCLURE = ("M", "R", "W")


def serialiser_postal_address(postal_address, tenant_schema, is_main_address):
    """
    Serialise une PostalAddress Lespass en dict JSON-compatible.
    / Serializes a Lespass PostalAddress into a JSON-compatible dict.

    is_main_address : True si cette PA est referencee par Configuration.postal_address.
    / is_main_address: True if this PA is referenced by Configuration.postal_address.

    Decimal -> str pour les coords (evite les soucis JSON / precision).
    / Decimal -> str for coords (avoids JSON / precision issues).
    """
    latitude_str = None
    if postal_address.latitude is not None:
        latitude_str = str(postal_address.latitude)
    longitude_str = None
    if postal_address.longitude is not None:
        longitude_str = str(postal_address.longitude)

    return {
        "tenant_schema": tenant_schema,
        "postgres_id": postal_address.pk,
        "is_main_address": is_main_address,
        "name": postal_address.name,
        "street_address": postal_address.street_address,
        "address_locality": postal_address.address_locality,
        "postal_code": postal_address.postal_code,
        "address_country": postal_address.address_country,
        "latitude": latitude_str,
        "longitude": longitude_str,
    }


def stub_name_only_pour_configuration(configuration, tenant_schema):
    """
    Stub minimaliste pour un tenant qui n'a NI FK postal_address NI champ
    legacy adress. On exporte juste son nom d'organisation pour que le
    backfill puisse tenter une recherche Nominatim par nom (bucket name_only,
    confidence low, needs_review obligatoire).
    / Minimal stub for a tenant with NO FK postal_address AND no legacy adress.
    We export just the organisation name so the backfill can try a Nominatim
    name search (name_only bucket, low confidence, mandatory needs_review).

    Renvoie None si meme le nom d'organisation est vide (tenant fantome).
    / Returns None if even the organisation name is empty (ghost tenant).
    """
    if not configuration.organisation:
        return None
    return {
        "tenant_schema": tenant_schema,
        "postgres_id": None,  # NULL = stub a creer en import
        # is_main_address=True : ce stub deviendra l'adresse principale du tenant.
        # / is_main_address=True: this stub will become the tenant's main address.
        "is_main_address": True,
        "name": configuration.organisation,
        "street_address": None,
        "address_locality": None,
        "postal_code": None,
        "address_country": None,
        "latitude": None,
        "longitude": None,
    }


def stub_legacy_pour_configuration(configuration, tenant_schema):
    """
    Si Configuration n'a pas de FK PostalAddress mais a un champ legacy adress,
    on genere un "stub" qui sera traite comme une PostalAddress sans postgres_id.
    Le backfill pourra le geocoder ; un futur script d'import devra alors CREER
    une vraie PostalAddress cote Lespass et la rattacher a Configuration.
    / If Configuration has no FK PostalAddress but has a legacy adress field,
    generate a "stub" treated as a PostalAddress without postgres_id.

    Renvoie None si le tenant n'a vraiment rien cote legacy.
    / Returns None if the tenant has nothing at all on the legacy side.
    """
    if not (configuration.adress or configuration.city or configuration.postal_code):
        return None

    cp_str = None
    if configuration.postal_code is not None:
        cp_str = str(configuration.postal_code)

    return {
        "tenant_schema": tenant_schema,
        "postgres_id": None,  # NULL = stub a creer en import
        # Un stub legacy represente toujours l'adresse principale du tenant
        # (il vient de Configuration), donc is_main_address=True.
        # / A legacy stub always represents the tenant's main address.
        "is_main_address": True,
        "name": configuration.organisation,
        "street_address": configuration.adress,
        "address_locality": configuration.city,
        "postal_code": cp_str,
        "address_country": None,  # pas de champ pays cote legacy
        "latitude": None,
        "longitude": None,
    }


class Command(BaseCommand):
    help = "Exporte tenants + leurs PostalAddress en JSON pour backfill geoloc local."

    def add_arguments(self, parser):
        parser.formatter_class = argparse.RawTextHelpFormatter
        parser.description = (
            "Exporte les tenants et leurs PostalAddress (avec deduplication)\n"
            "pour un backfill geoloc Nominatim en local.\n"
            "Aucune ecriture en base.\n\n"
            "Exemples :\n"
            "  manage.py export_tenants_addresses > tenants.json\n"
            "  manage.py export_tenants_addresses --output=/tmp/tenants.json\n"
            "  manage.py export_tenants_addresses --only-incomplete"
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
            help=(
                "Ne sort que les PostalAddress sans geoloc (lat/long manquants). "
                "Les tenants sans aucune PostalAddress incomplete sont aussi sortis "
                "s'ils ont un stub legacy a geocoder."
            ),
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

        tenants_out = []
        postal_addresses_out = []

        nombre_tenants = 0
        nombre_sans_configuration = 0
        nombre_pa_total = 0
        nombre_pa_sans_geoloc = 0
        nombre_stubs_legacy = 0

        for tenant in tenants_a_exporter:
            nombre_tenants += 1
            schema = tenant.schema_name

            # Bascule dans le schema du tenant.
            # / Switch to the tenant's schema.
            with tenant_context(tenant):
                # Pas de get_solo : on ne cree rien en lecture.
                # / No get_solo: never create on read.
                configuration = Configuration.objects.first()

                tenant_dict = {
                    "schema": schema,
                    "tenant_name": tenant.name,
                    "categorie": tenant.categorie,
                    "organisation": None,
                    "email": None,
                    "phone": None,
                    "site_web": None,
                    "legacy_adress": None,
                    "legacy_postal_code": None,
                    "legacy_city": None,
                    "configuration_manquante": configuration is None,
                }

                if configuration is None:
                    nombre_sans_configuration += 1
                    tenants_out.append(tenant_dict)
                    continue

                tenant_dict.update({
                    "organisation": configuration.organisation,
                    "email": configuration.email,
                    "phone": configuration.phone,
                    "site_web": configuration.site_web,
                    "legacy_adress": configuration.adress,
                    "legacy_postal_code": (
                        str(configuration.postal_code)
                        if configuration.postal_code is not None else None
                    ),
                    "legacy_city": configuration.city,
                })
                tenants_out.append(tenant_dict)

                # --- Collecte des PostalAddress : tap direct sur la table ---
                # / --- Collect PostalAddress: direct table tap ---
                # Toutes les PA du tenant sont dans cette table, peu importe
                # qui les reference (Configuration, Event, ou meme orphelines).
                # Deduplication native : 1 row = 1 PostalAddress reelle.
                # / All tenant PAs are in this table regardless of who references
                # them. Native deduplication: 1 row = 1 real PostalAddress.
                # ID de l'adresse principale du tenant (sans suivre la FK).
                # Sert a marquer is_main_address pour chaque PA exportee.
                # / ID of the tenant's main address (without following the FK).
                # Used to mark is_main_address for each exported PA.
                main_address_pk = configuration.postal_address_id

                requete_pa = PostalAddress.objects.all()
                if seulement_incomplets:
                    # Filtrage au niveau SQL : evite de materialiser les PA deja geolocalisees
                    # / SQL-level filter: avoid materializing already-geolocated PAs
                    requete_pa = requete_pa.filter(
                        Q(latitude__isnull=True) | Q(longitude__isnull=True)
                    )

                for postal_address in requete_pa:
                    nombre_pa_total += 1
                    a_geoloc = (
                        postal_address.latitude is not None
                        and postal_address.longitude is not None
                    )
                    if not a_geoloc:
                        nombre_pa_sans_geoloc += 1
                    est_adresse_principale = (postal_address.pk == main_address_pk)
                    postal_addresses_out.append(
                        serialiser_postal_address(postal_address, schema, est_adresse_principale)
                    )

                # Stub legacy : si Configuration n'a pas de FK postal_address
                # mais a un champ adress legacy rempli, on cree un stub virtuel.
                # / Legacy stub: if Configuration has no FK postal_address but
                # has a legacy adress field filled, create a virtual stub.
                if configuration.postal_address is None:
                    stub = stub_legacy_pour_configuration(configuration, schema)
                    if stub is not None:
                        nombre_stubs_legacy += 1
                        nombre_pa_total += 1
                        nombre_pa_sans_geoloc += 1  # un stub n'a jamais de geoloc
                        postal_addresses_out.append(stub)

        # --- Stats sur stderr ---
        self.stderr.write(self.style.SUCCESS(
            "\n--- Stats export ---\n"
            f"Tenants parcourus              : {nombre_tenants}\n"
            f"Sans Configuration             : {nombre_sans_configuration}\n"
            f"PostalAddress distinctes total : {nombre_pa_total}\n"
            f"PostalAddress sans geoloc      : {nombre_pa_sans_geoloc}\n"
            f"Stubs legacy crees             : {nombre_stubs_legacy}\n"
            f"Lignes exportees (PA)          : {len(postal_addresses_out)}\n"
            f"Lignes exportees (tenants)     : {len(tenants_out)}\n"
        ))

        # --- Sortie JSON ---
        contenu_json = json.dumps(
            {"tenants": tenants_out, "postal_addresses": postal_addresses_out},
            indent=2,
            ensure_ascii=False,
        )
        if chemin_sortie:
            with open(chemin_sortie, "w", encoding="utf-8") as fichier:
                fichier.write(contenu_json)
            self.stderr.write(self.style.SUCCESS(f"JSON ecrit dans : {chemin_sortie}"))
        else:
            self.stdout.write(contenu_json)
