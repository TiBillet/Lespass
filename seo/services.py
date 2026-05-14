"""
Services SEO cross-schema : requetes SQL et helpers Memcached.
/ Cross-schema SEO services: SQL queries and Memcached helpers.

LOCALISATION: seo/services.py

Version V1 allegee : on agrege uniquement les lieux et les evenements.
Les adhesions (Product ADHESION), initiatives (crowds) et monnaies
fedow_core sont volontairement exclues pour cette etape de migration.
/ V1 lightweight version: we only aggregate venues and events.
Memberships (Product ADHESION), initiatives (crowds) and fedow_core
currencies are deliberately excluded for this migration step.
"""

import logging
import os

from django.core.cache import cache
from django.db import connection
from django.utils import timezone
from django_tenants.utils import tenant_context

from Customers.models import Client

logger = logging.getLogger(__name__)

# TTL du cache Memcached L1 : 4 heures (= frequence du Celery beat)
# / Memcached L1 cache TTL: 4 hours (= Celery beat frequency)
MEMCACHED_L1_TTL = 4 * 60 * 60


# ---------------------------------------------------------------------------
# Helpers Memcached L1 / Memcached L1 helpers
# ---------------------------------------------------------------------------


def _memcached_key(cache_type, tenant_uuid):
    """
    Cle Memcached pour un type de cache et un tenant (ou None pour global).
    / Memcached key for a cache type and tenant (or None for global).
    """
    tenant_part = str(tenant_uuid) if tenant_uuid else "global"
    return f"seo:{cache_type}:{tenant_part}"


def set_memcached_l1(cache_type, tenant_uuid, data):
    """
    Ecrit dans Memcached L1 avec TTL de 4h.
    / Write to Memcached L1 with 4h TTL.
    """
    key = _memcached_key(cache_type, tenant_uuid)
    cache.set(key, data, MEMCACHED_L1_TTL)


def get_memcached_l1(cache_type, tenant_uuid):
    """
    Lit depuis Memcached L1. Retourne None si absent ou expire.
    / Read from Memcached L1. Returns None if missing or expired.
    """
    key = _memcached_key(cache_type, tenant_uuid)
    return cache.get(key)


# ---------------------------------------------------------------------------
# Helpers URL images / Image URL helpers
# ---------------------------------------------------------------------------


def build_stdimage_variation_url(img_path, variation="crop"):
    """
    Construit l'URL d'une variation StdImageField a partir du chemin brut en DB.
    Exemple : "images/event_foo.jpg" → "/media/images/event_foo.crop.jpg"
    Retourne None si pas d'image.
    / Builds a StdImageField variation URL from the raw DB path.
    Example: "images/event_foo.jpg" → "/media/images/event_foo.crop.jpg"
    Returns None if no image.
    """
    if not img_path:
        return None

    base_sans_extension, extension = os.path.splitext(img_path)
    return f"/media/{base_sans_extension}.{variation}{extension}"


# ---------------------------------------------------------------------------
# Requetes SQL cross-schema / Cross-schema SQL queries
# ---------------------------------------------------------------------------
#
# SECURITE / SECURITY:
# Les noms de schemas sont injectes via f-string (pas de %s parametrise)
# car PostgreSQL ne permet pas de parametriser les identifiants (noms de table/schema).
# C'est SUR car schema_name provient uniquement de Client.schema_name en DB,
# controle par l'admin, jamais par un input utilisateur.
# / Schema names are injected via f-string (not parameterized %s)
# because PostgreSQL does not allow parameterizing identifiers (table/schema names).
# This is SAFE because schema_name comes only from Client.schema_name in DB,
# controlled by admin, never from user input.


# Categories de Product qui temoignent qu'un lieu est "vivant" cote SEO :
# billetterie payante, reservation gratuite, adhesion/abonnement.
# Si on en trouve au moins 1 publie, le lieu a une raison d'apparaitre
# dans la landing root, la page /lieux/ et le sitemap.
# / Product categories that prove a venue is "alive" SEO-wise: paid
# ticketing, free booking, membership. At least 1 published is enough
# to justify listing the venue on root landing, /lieux/ and sitemap.
CATEGORIES_PRODUIT_LIEU_VIVANT = ("B", "F", "A")


def get_active_tenants_with_counts():
    """
    Retourne la liste des tenants actifs (hors ROOT et WAITING_CONFIG)
    avec deux comptages par tenant :
    - event_count : nombre d'evenements publies et futurs
    - product_count : nombre de Product publies appartenant aux categories
      "lieu vivant" (BILLET, FREERES, ADHESION)
    1 seule requete SQL UNION ALL sur tous les schemas tenant.
    Chaque sous-requete utilise des sous-selects scalaires pour
    ramener event_count + product_count sur la meme ligne.

    / Returns list of active tenants (excluding ROOT and WAITING_CONFIG)
    with two per-tenant counts:
    - event_count: published future event count
    - product_count: published Product count for "alive venue" categories
      (BILLET, FREERES, ADHESION)
    Single SQL query (UNION ALL across all tenant schemas, scalar
    sub-selects to bring both counts on the same row).

    Retourne / Returns: list[dict] avec cles tenant_id, schema_name,
    event_count, product_count
    """
    # Recuperer tous les tenants actifs (pas ROOT, pas WAITING_CONFIG)
    # / Get all active tenants (not ROOT, not WAITING_CONFIG)
    excluded_categories = [Client.ROOT, Client.WAITING_CONFIG]
    tenants = Client.objects.exclude(categorie__in=excluded_categories)

    if not tenants.exists():
        return []

    # Construire les sous-requetes UNION ALL. Chaque ligne ramene
    # (tenant_id, schema_name, event_count, product_count) via deux
    # sous-selects scalaires.
    # / Build UNION ALL sub-queries. Each row returns
    # (tenant_id, schema_name, event_count, product_count) via two
    # scalar sub-selects.
    parts = []
    params = []

    now = timezone.now()
    # On prepare une fois la liste des codes categorie pour la clause IN.
    # / Build the IN clause placeholders for product categories once.
    placeholders_categories = ", ".join(
        ["%s"] * len(CATEGORIES_PRODUIT_LIEU_VIVANT)
    )

    for tenant in tenants:
        schema = tenant.schema_name
        tenant_uuid_str = str(tenant.uuid)

        # 1 ligne par tenant avec event_count + product_count.
        # / One row per tenant with event_count + product_count.
        parts.append(
            f"SELECT %s AS tenant_id, %s AS schema_name, "
            f"(SELECT COUNT(*) "
            f' FROM "{schema}"."BaseBillet_event" '
            f" WHERE published = true AND datetime >= %s"
            f") AS event_count, "
            f"(SELECT COUNT(*) "
            f' FROM "{schema}"."BaseBillet_product" '
            f" WHERE publish = true "
            f"   AND categorie_article IN ({placeholders_categories})"
            f") AS product_count"
        )
        params.append(tenant_uuid_str)
        params.append(schema)
        params.append(now)
        params.extend(CATEGORIES_PRODUIT_LIEU_VIVANT)

    sql = " UNION ALL ".join(parts)

    results = []
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        for row in cursor.fetchall():
            results.append(
                {
                    "tenant_id": row[0],
                    "schema_name": row[1],
                    "event_count": row[2],
                    "product_count": row[3],
                }
            )

    return results


def get_events_for_tenants(tenant_schemas):
    """
    Recupere tous les evenements publies et futurs pour les schemas donnes.
    1 seule requete SQL UNION ALL.
    / Fetch all published future events for given schemas.
    Single UNION ALL SQL query.

    Parametres / Parameters:
        tenant_schemas: list[tuple(uuid, schema_name)]
    Retourne / Returns: list[dict] avec cles tenant_id, name, slug, short_description, datetime, end_datetime, img
    """
    if not tenant_schemas:
        return []

    parts = []
    params = []
    now = timezone.now()

    for tenant_uuid, schema_name in tenant_schemas:
        # On recupere aussi le champ `img` (chemin relatif StdImageField)
        # pour construire les URLs des vignettes dans tasks.py.
        # / Also fetch the `img` field (relative StdImageField path)
        # to build thumbnail URLs in tasks.py.
        parts.append(
            f"SELECT %s AS tenant_id, name, slug, short_description, "
            f"datetime, end_datetime, img "
            f'FROM "{schema_name}"."BaseBillet_event" '
            f"WHERE published = true AND datetime >= %s"
        )
        params.extend([str(tenant_uuid), now])

    sql = " UNION ALL ".join(parts) + " ORDER BY datetime ASC"

    results = []
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        for row in cursor.fetchall():
            results.append(
                {
                    "tenant_id": row[0],
                    "name": row[1],
                    "slug": row[2],
                    "short_description": row[3],
                    "datetime": row[4].isoformat() if row[4] else None,
                    "end_datetime": row[5].isoformat() if row[5] else None,
                    "img": row[6] or "",
                }
            )

    return results


def build_tenant_config_data(client):
    """
    Bascule sur le schema du tenant et lit la Configuration singleton.
    Retourne un dict avec les champs SEO utiles.
    / Switch to tenant schema and read the Configuration singleton.
    Returns a dict with useful SEO fields.

    Version V1 allegee : pas de accepted_asset_ids (pas de fedow_core).
    / V1 lightweight version: no accepted_asset_ids (no fedow_core).
    """
    data = {
        "tenant_id": str(client.uuid),
        "schema_name": client.schema_name,
        "name": client.name,
        "categorie": client.categorie,
        "domain": None,
        "organisation": None,
        "slug": None,
        "short_description": None,
        "long_description": None,
        "email": None,
        "phone": None,
        "site_web": None,
        "twitter": None,
        "facebook": None,
        "instagram": None,
        "language": "fr",
        "social_card_url": None,
        "logo_url": None,
        "locality": None,
        "country": None,
        "latitude": None,
        "longitude": None,
    }

    # Domaine principal du tenant / Tenant primary domain
    try:
        primary_domain = client.get_primary_domain()
        if primary_domain:
            data["domain"] = primary_domain.domain
    except Exception:
        logger.warning(
            "Pas de domaine pour le tenant %s / No domain for tenant %s",
            client.name,
            client.name,
        )

    # Lire la Configuration dans le schema du tenant
    # / Read Configuration in the tenant schema
    try:
        with tenant_context(client):
            from BaseBillet.models import Configuration

            config = Configuration.get_solo()

            data["organisation"] = config.organisation or client.name
            data["slug"] = config.slug or ""
            data["short_description"] = config.short_description or ""
            data["long_description"] = config.long_description or ""
            data["email"] = config.email or ""
            data["phone"] = config.phone or ""
            data["site_web"] = config.site_web or ""
            data["twitter"] = config.twitter or ""
            data["facebook"] = config.facebook or ""
            data["instagram"] = config.instagram or ""
            data["language"] = config.language or "fr"

            # Image social card / Social card image
            # config.get_social_card est une @property : pas de parentheses.
            # / config.get_social_card is a @property: no parentheses.
            social_card = config.get_social_card
            if social_card:
                data["social_card_url"] = social_card

            # Logo
            if config.logo:
                try:
                    data["logo_url"] = config.logo.med.url
                except Exception:
                    pass

            # Adresse postale / Postal address
            if config.postal_address:
                data["locality"] = config.postal_address.address_locality or ""
                data["country"] = config.postal_address.address_country or ""
                # Coordonnees GPS / GPS coordinates
                data["latitude"] = (
                    float(config.postal_address.latitude)
                    if config.postal_address.latitude
                    else None
                )
                data["longitude"] = (
                    float(config.postal_address.longitude)
                    if config.postal_address.longitude
                    else None
                )

    except Exception as exc:
        logger.warning(
            "Erreur lecture config tenant %s : %s / Error reading tenant config %s: %s",
            client.name,
            exc,
            client.name,
            exc,
        )

    return data


# ---------------------------------------------------------------------------
# Explorer data builder / Constructeur de donnees explorer
# ---------------------------------------------------------------------------


def build_explorer_data_for_tenants(tenant_uuids):
    """
    Construit les donnees structurees pour la page explorer (carte + liste),
    en filtrant sur la liste d'UUIDs fournie.
    / Build structured data for the explorer page (map + list),
    filtering on the provided UUID list.

    Parametres / Parameters:
        tenant_uuids: list[str] — UUIDs des tenants a inclure.
                                  Si vide, retourne {"lieux": [], "events": []}.

    Retourne / Returns: dict avec cles lieux, events
    """
    from seo.models import SEOCache
    from seo.views_common import get_seo_cache

    if not tenant_uuids:
        return {"lieux": [], "events": []}

    # Convertir en set pour lookup O(1) / Convert to set for O(1) lookup
    uuids_set = set(tenant_uuids)

    # Lire les 2 agregats depuis le cache L1/L2
    # / Read the 2 aggregates from L1/L2 cache
    lieux_data = get_seo_cache(SEOCache.AGGREGATE_LIEUX) or {}
    events_data = get_seo_cache(SEOCache.AGGREGATE_EVENTS) or {}

    raw_lieux = lieux_data.get("lieux", [])
    raw_events = events_data.get("events", [])

    # Filtrer + indexer les lieux par tenant_id, en excluant ceux sans coords GPS
    # / Filter + index lieux by tenant_id, excluding those without GPS coords
    lieux_by_tenant = {}
    for lieu in raw_lieux:
        if lieu["tenant_id"] not in uuids_set:
            continue
        if lieu.get("latitude") is None or lieu.get("longitude") is None:
            continue
        lieu_copy = dict(lieu)
        lieu_copy["events"] = []
        lieux_by_tenant[lieu["tenant_id"]] = lieu_copy

    # Construire la liste plate d'events avec infos du lieu parent
    # / Build flat event list with parent lieu info
    flat_events = []
    for event in raw_events:
        tenant_id = event.get("tenant_id")
        if tenant_id not in uuids_set:
            continue
        lieu = lieux_by_tenant.get(tenant_id)
        if lieu is None:
            continue
        event_copy = dict(event)
        event_copy["lieu_id"] = tenant_id
        event_copy["lieu_name"] = lieu.get("name", "")
        event_copy["lieu_domain"] = lieu.get("domain", "")
        flat_events.append(event_copy)
        # Imbriquer sous le lieu parent / Nest under parent lieu
        lieu["events"].append(event)

    return {
        "lieux": list(lieux_by_tenant.values()),
        "events": flat_events,
    }


def build_explorer_data():
    """
    Compatibilite retro : appelle build_explorer_data_for_tenants() avec
    l'ensemble des tenant_ids presents dans AGGREGATE_LIEUX.
    Comportement identique a la version d'avant le refactor.
    / Backward compat: calls build_explorer_data_for_tenants() with all
    tenant_ids from AGGREGATE_LIEUX. Identical behavior to pre-refactor.
    """
    from seo.models import SEOCache
    from seo.views_common import get_seo_cache

    lieux_data = get_seo_cache(SEOCache.AGGREGATE_LIEUX) or {}
    all_uuids = [lieu["tenant_id"] for lieu in lieux_data.get("lieux", [])]
    return build_explorer_data_for_tenants(all_uuids)
