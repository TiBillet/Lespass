"""
Services SEO cross-schema : requetes SQL et helpers Memcached.
/ Cross-schema SEO services: SQL queries and Memcached helpers.

LOCALISATION: seo/services.py
"""

import logging

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
    import os

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


def get_active_tenants_with_counts():
    """
    Retourne la liste des tenants actifs (hors ROOT et WAITING_CONFIG)
    avec le nombre d'evenements publies et d'adhesions publiees.
    1 seule requete SQL avec UNION ALL sur tous les schemas tenant.
    / Returns list of active tenants (excluding ROOT and WAITING_CONFIG)
    with published event count and published membership count.
    Single SQL query using UNION ALL across all tenant schemas.

    Retourne / Returns: list[dict] avec cles tenant_id, schema_name, event_count, membership_count
    """
    # Recuperer tous les tenants actifs (pas ROOT, pas WAITING_CONFIG)
    # / Get all active tenants (not ROOT, not WAITING_CONFIG)
    excluded_categories = [Client.ROOT, Client.WAITING_CONFIG]
    tenants = Client.objects.exclude(categorie__in=excluded_categories)

    if not tenants.exists():
        return []

    # Construire les sous-requetes UNION ALL pour les events et memberships
    # Les params doivent etre separes car le SQL final met tous les events
    # avant tous les memberships.
    # / Build UNION ALL sub-queries for events and memberships.
    # Params must be separate because final SQL puts all events before all memberships.
    event_parts = []
    event_params = []
    membership_parts = []
    membership_params = []

    now = timezone.now()
    for tenant in tenants:
        schema = tenant.schema_name
        tenant_uuid_str = str(tenant.uuid)

        # Comptage des evenements publies et futurs
        # / Count published and future events
        event_parts.append(
            f"SELECT %s AS tenant_id, %s AS schema_name, "
            f"COUNT(*) AS event_count "
            f'FROM "{schema}"."BaseBillet_event" '
            f"WHERE published = true AND datetime >= %s"
        )
        event_params.extend([tenant_uuid_str, schema, now])

        # Comptage des adhesions publiees
        # / Count published memberships
        membership_parts.append(
            f"SELECT %s AS tenant_id, %s AS schema_name, "
            f"COUNT(*) AS membership_count "
            f'FROM "{schema}"."BaseBillet_product" '
            f"WHERE publish = true AND categorie_article = 'A'"
        )
        membership_params.extend([tenant_uuid_str, schema])

    # Joindre les deux sous-requetes avec UNION ALL
    # / Join both sub-queries with UNION ALL
    event_sql = " UNION ALL ".join(event_parts)
    membership_sql = " UNION ALL ".join(membership_parts)

    # Params : d'abord tous les event_params, puis tous les membership_params
    # / Params: all event_params first, then all membership_params
    all_params = event_params + membership_params

    # Requete finale : jointure des counts events et memberships par tenant
    # / Final query: join event and membership counts by tenant
    sql = f"""
        SELECT e.tenant_id, e.schema_name, e.event_count, COALESCE(m.membership_count, 0) AS membership_count
        FROM ({event_sql}) AS e
        LEFT JOIN ({membership_sql}) AS m ON e.tenant_id = m.tenant_id
    """

    results = []
    with connection.cursor() as cursor:
        cursor.execute(sql, all_params)
        for row in cursor.fetchall():
            results.append(
                {
                    "tenant_id": row[0],
                    "schema_name": row[1],
                    "event_count": row[2],
                    "membership_count": row[3],
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


def get_memberships_for_tenants(tenant_schemas):
    """
    Recupere toutes les adhesions publiees pour les schemas donnes.
    1 seule requete SQL UNION ALL.
    / Fetch all published memberships for given schemas.
    Single UNION ALL SQL query.

    Parametres / Parameters:
        tenant_schemas: list[tuple(uuid, schema_name)]
    Retourne / Returns: list[dict] avec cles tenant_id, uuid, name, short_description
    """
    if not tenant_schemas:
        return []

    parts = []
    params = []

    for tenant_uuid, schema_name in tenant_schemas:
        parts.append(
            f"SELECT %s AS tenant_id, uuid::text, name, short_description "
            f'FROM "{schema_name}"."BaseBillet_product" '
            f"WHERE publish = true AND categorie_article = 'A'"
        )
        params.append(str(tenant_uuid))

    sql = " UNION ALL ".join(parts)

    results = []
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        for row in cursor.fetchall():
            results.append(
                {
                    "tenant_id": row[0],
                    "uuid": row[1],
                    "name": row[2],
                    "short_description": row[3],
                }
            )

    return results


def get_initiatives_for_tenants(tenant_schemas):
    """
    Recupere toutes les initiatives non archivees pour les schemas donnes.
    1 seule requete SQL UNION ALL.
    / Fetch all non-archived initiatives for given schemas.
    Single UNION ALL SQL query.

    Parametres / Parameters:
        tenant_schemas: list[tuple(uuid, schema_name)]
    Retourne / Returns: list[dict] avec cles tenant_id, uuid, name, short_description, budget_contributif
    """
    if not tenant_schemas:
        return []

    parts = []
    params = []

    for tenant_uuid, schema_name in tenant_schemas:
        parts.append(
            f"SELECT %s AS tenant_id, uuid::text, name, short_description, "
            f"budget_contributif "
            f'FROM "{schema_name}"."crowds_initiative" '
            f"WHERE archived = false"
        )
        params.append(str(tenant_uuid))

    sql = " UNION ALL ".join(parts)

    results = []
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        for row in cursor.fetchall():
            results.append(
                {
                    "tenant_id": row[0],
                    "uuid": row[1],
                    "name": row[2],
                    "short_description": row[3],
                    "budget_contributif": row[4],
                }
            )

    return results


def get_all_assets():
    """
    Recupere tous les assets fedow_core (SHARED_APPS, schema public).
    / Fetch all fedow_core assets (SHARED_APPS, public schema).

    Retourne / Returns: list[dict] avec cles uuid, name, category
    """
    sql = """
        SELECT uuid::text, name, category
        FROM "public"."fedow_core_asset"
    """
    results = []
    with connection.cursor() as cursor:
        cursor.execute(sql)
        for row in cursor.fetchall():
            results.append(
                {
                    "uuid": row[0],
                    "name": row[1],
                    "category": row[2],
                }
            )

    return results


def build_tenant_config_data(client):
    """
    Bascule sur le schema du tenant et lit la Configuration singleton.
    Retourne un dict avec les champs SEO utiles.
    / Switch to tenant schema and read the Configuration singleton.
    Returns a dict with useful SEO fields.
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
            "Pas de domaine pour le tenant %s / No domain for tenant %s", client.name
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
# Comptages bruts cross-tenant / Raw cross-tenant counts
# ---------------------------------------------------------------------------


def get_global_counts(tenant_schemas):
    """
    Compte le nombre TOTAL (non filtre) d'events, adhesions et initiatives
    sur tous les schemas tenants. 1 seule requete SQL UNION ALL.
    / Count the TOTAL (unfiltered) number of events, memberships and initiatives
    across all tenant schemas. Single UNION ALL SQL query.

    LOCALISATION: seo/services.py

    Contrairement a get_active_tenants_with_counts() qui filtre les events
    publies et futurs, cette fonction compte TOUT : passes, non publies, etc.
    C'est pour l'affichage "chiffres cles" de la landing page.
    / Unlike get_active_tenants_with_counts() which filters published future
    events, this function counts EVERYTHING: past, unpublished, etc.
    This is for the "key figures" display on the landing page.

    Parametres / Parameters:
        tenant_schemas: list[tuple(uuid, schema_name)]
    Retourne / Returns: dict avec cles events, memberships, initiatives
    """
    if not tenant_schemas:
        return {"events": 0, "memberships": 0, "initiatives": 0}

    # 3 comptages en 1 requete : on fait un UNION ALL de sous-requetes
    # qui comptent chacune dans leur table, puis on somme par type.
    # / 3 counts in 1 query: UNION ALL sub-queries that count in their
    # respective tables, then sum by type.
    parts = []
    params = []

    for tenant_uuid, schema_name in tenant_schemas:
        # Events (tous, pas filtres) / Events (all, unfiltered)
        parts.append(
            f"SELECT 'events' AS type_comptage, COUNT(*) AS nb "
            f'FROM "{schema_name}"."BaseBillet_event"'
        )
        # Adhesions (tous les products avec categorie_article='A')
        # / Memberships (all products with categorie_article='A')
        parts.append(
            f"SELECT 'memberships' AS type_comptage, COUNT(*) AS nb "
            f'FROM "{schema_name}"."BaseBillet_product" '
            f"WHERE categorie_article = 'A'"
        )
        # Initiatives (app crowds) / Initiatives (crowds app)
        parts.append(
            f"SELECT 'initiatives' AS type_comptage, COUNT(*) AS nb "
            f'FROM "{schema_name}"."crowds_initiative"'
        )

    sql = (
        f"SELECT type_comptage, SUM(nb) AS total "
        f"FROM ({' UNION ALL '.join(parts)}) AS counts "
        f"GROUP BY type_comptage"
    )

    result = {"events": 0, "memberships": 0, "initiatives": 0, "assets": 0}
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        for row in cursor.fetchall():
            type_comptage = row[0]
            total = int(row[1])
            if type_comptage in result:
                result[type_comptage] = total

    # Assets fedow_core : table dans le schema PUBLIC (SHARED_APPS),
    # pas besoin de UNION ALL — un simple COUNT suffit.
    # / fedow_core Assets: table in the PUBLIC schema (SHARED_APPS),
    # no UNION ALL needed — a simple COUNT is enough.
    from fedow_core.models import Asset
    result["assets"] = Asset.objects.filter(active=True).count()

    return result


# ---------------------------------------------------------------------------
# Explorer data builder / Constructeur de donnees explorer
# ---------------------------------------------------------------------------


def build_explorer_data():
    """
    Construit les donnees structurees pour la page explorer (carte + liste).
    Lit les 3 agregats depuis SEOCache et les reorganise :
    - lieux : uniquement ceux avec coordonnees GPS, chacun avec events/memberships imbriques
    - events : liste plate avec lieu_id/lieu_name/lieu_domain ajoutes
    - memberships : liste plate avec lieu_id/lieu_name/lieu_domain ajoutes
    / Build structured data for the explorer page (map + list).
    Reads 3 aggregates from SEOCache and restructures them:
    - lieux: only those with GPS coordinates, each with nested events/memberships
    - events: flat list with lieu_id/lieu_name/lieu_domain added
    - memberships: flat list with lieu_id/lieu_name/lieu_domain added

    Retourne / Returns: dict avec cles lieux, events, memberships
    """
    # Import local pour eviter les imports circulaires
    # / Local import to avoid circular imports
    from seo.models import SEOCache
    from seo.views_common import get_seo_cache

    # Lire les 5 agregats depuis le cache L1/L2
    # / Read the 5 aggregates from L1/L2 cache
    lieux_data = get_seo_cache(SEOCache.AGGREGATE_LIEUX) or {}
    events_data = get_seo_cache(SEOCache.AGGREGATE_EVENTS) or {}
    memberships_data = get_seo_cache(SEOCache.AGGREGATE_MEMBERSHIPS) or {}
    initiatives_data = get_seo_cache(SEOCache.AGGREGATE_INITIATIVES) or {}
    assets_data = get_seo_cache(SEOCache.AGGREGATE_ASSETS) or {}

    raw_lieux = lieux_data.get("lieux", [])
    raw_events = events_data.get("events", [])
    raw_memberships = memberships_data.get("memberships", [])
    raw_initiatives = initiatives_data.get("initiatives", [])
    raw_assets = assets_data.get("assets", [])

    # Index des lieux par tenant_id, en excluant ceux sans coordonnees GPS
    # / Index lieux by tenant_id, excluding those without GPS coordinates
    lieux_by_tenant = {}
    for lieu in raw_lieux:
        if lieu.get("latitude") is None or lieu.get("longitude") is None:
            continue
        # Copie du lieu avec listes events/memberships vides
        # / Copy of lieu with empty events/memberships lists
        lieu_copy = dict(lieu)
        lieu_copy["events"] = []
        lieu_copy["memberships"] = []
        lieu_copy["initiatives"] = []
        tenant_id = lieu["tenant_id"]
        lieux_by_tenant[tenant_id] = lieu_copy

    # Construire la liste plate d'events avec infos du lieu parent
    # / Build flat event list with parent lieu info
    flat_events = []
    for event in raw_events:
        tenant_id = event.get("tenant_id")
        lieu = lieux_by_tenant.get(tenant_id)
        if lieu is None:
            # Le lieu n'a pas de coordonnees GPS, on ignore cet event
            # / The lieu has no GPS coordinates, skip this event
            continue

        # Copie de l'event avec les infos du lieu
        # / Copy of event with lieu info
        event_copy = dict(event)
        event_copy["lieu_id"] = tenant_id
        event_copy["lieu_name"] = lieu.get("name", "")
        event_copy["lieu_domain"] = lieu.get("domain", "")
        flat_events.append(event_copy)

        # Imbriquer sous le lieu parent / Nest under parent lieu
        lieu["events"].append(event)

    # Meme chose pour les memberships / Same for memberships
    flat_memberships = []
    for membership in raw_memberships:
        tenant_id = membership.get("tenant_id")
        lieu = lieux_by_tenant.get(tenant_id)
        if lieu is None:
            continue

        membership_copy = dict(membership)
        membership_copy["lieu_id"] = tenant_id
        membership_copy["lieu_name"] = lieu.get("name", "")
        membership_copy["lieu_domain"] = lieu.get("domain", "")
        flat_memberships.append(membership_copy)

        lieu["memberships"].append(membership)

    # Meme chose pour les initiatives / Same for initiatives
    flat_initiatives = []
    for initiative in raw_initiatives:
        tenant_id = initiative.get("tenant_id")
        lieu = lieux_by_tenant.get(tenant_id)
        if lieu is None:
            continue

        initiative_copy = dict(initiative)
        initiative_copy["lieu_id"] = tenant_id
        initiative_copy["lieu_name"] = lieu.get("name", "")
        initiative_copy["lieu_domain"] = lieu.get("domain", "")
        flat_initiatives.append(initiative_copy)

        lieu["initiatives"].append(initiative)

    # Convertir l'index en liste / Convert index to list
    result_lieux = list(lieux_by_tenant.values())

    return {
        "lieux": result_lieux,
        "events": flat_events,
        "memberships": flat_memberships,
        "initiatives": flat_initiatives,
        "assets": raw_assets,
    }
