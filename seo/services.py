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


def get_counts_for_tenant(schema_name):
    """
    Compte, pour UN schema tenant, les events futurs publies et les produits
    "lieu vivant" (BILLET/FREERES/ADHESION) publies. Une seule requete sur 1 schema.
    / Per-tenant counts (1 schema): published future events + alive-venue products.

    SECURITE / SECURITY : schema_name vient de Client.schema_name (DB, admin-only),
    jamais d'input utilisateur (cf. note en tete de fichier).

    Retourne / Returns: dict {"event_count": int, "product_count": int}
    """
    now = timezone.now()
    placeholders_categories = ", ".join(["%s"] * len(CATEGORIES_PRODUIT_LIEU_VIVANT))
    sql = (
        f"SELECT "
        f'(SELECT COUNT(*) FROM "{schema_name}"."BaseBillet_event" '
        f" WHERE published = true AND datetime >= %s) AS event_count, "
        f'(SELECT COUNT(*) FROM "{schema_name}"."BaseBillet_product" '
        f"   WHERE publish = true AND categorie_article IN ({placeholders_categories})"
        f") AS product_count"
    )
    params = [now, *CATEGORIES_PRODUIT_LIEU_VIVANT]
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        row = cursor.fetchone()
    return {"event_count": row[0], "product_count": row[1]}


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
        # `postal_address_id` est la FK vers PostalAddress (sert a AGGREGATE_POINTS).
        # / `postal_address_id` is the FK to PostalAddress (used for AGGREGATE_POINTS).
        parts.append(
            f"SELECT %s AS tenant_id, uuid::text AS uuid, name, slug, short_description, "
            f"datetime, end_datetime, img, postal_address_id "
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
                    "uuid": row[1],
                    "name": row[2],
                    "slug": row[3],
                    "short_description": row[4],
                    "datetime": row[5].isoformat() if row[5] else None,
                    "end_datetime": row[6].isoformat() if row[6] else None,
                    "img": row[7] or "",
                    "postal_address_id": row[8],
                }
            )

    return results


def get_event_tags_for_tenants(tenant_schemas):
    """
    Récupère tous les tags des events publiés et futurs pour les schémas donnés.
    1 seule requête SQL UNION ALL avec JOIN sur la table M2M event_tag.
    / Fetch all tags for published future events across given schemas.
    Single UNION ALL SQL query with JOIN on the event_tag M2M table.

    Paramètres / Parameters:
        tenant_schemas: list[tuple(uuid, schema_name)]
    Retourne / Returns:
        dict[event_uuid_str, list[dict]] — {event_uuid: [{slug, name, color}, ...]}
        Les events sans tag ne figurent pas dans le dict (JOIN strict).
        / Events without tags are absent from the dict (strict JOIN).

    SÉCURITÉ / SECURITY : schema_name vient de Client.schema_name (DB, admin-only),
    jamais d'input utilisateur. Pattern identique aux autres helpers du fichier.
    """
    if not tenant_schemas:
        return {}

    parts = []
    params = []
    now = timezone.now()

    for tenant_uuid, schema_name in tenant_schemas:
        # JOIN entre Event, table M2M (BaseBillet_event_tag) et Tag.
        # On caste event_id en text pour pouvoir comparer aux UUIDs cote Python.
        # / JOIN between Event, M2M table (BaseBillet_event_tag) and Tag.
        # Cast event_id to text for cross-Python UUID comparison.
        parts.append(
            f"SELECT e.uuid::text AS event_uuid, "
            f"t.slug, t.name, t.color "
            f'FROM "{schema_name}"."BaseBillet_event" e '
            f'JOIN "{schema_name}"."BaseBillet_event_tag" et ON et.event_id = e.uuid '
            f'JOIN "{schema_name}"."BaseBillet_tag" t ON t.uuid = et.tag_id '
            f"WHERE e.published = true AND e.datetime >= %s"
        )
        params.append(now)

    sql = " UNION ALL ".join(parts)

    resultat = {}
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        for row in cursor.fetchall():
            event_uuid, slug, name, color = row
            if event_uuid not in resultat:
                resultat[event_uuid] = []
            resultat[event_uuid].append({
                "slug": slug,
                "name": name,
                "color": color,
            })

    return resultat


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
        "postal_address_id": None,
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
# AGGREGATE_POINTS helper / Helper pour les points d'agregat
# ---------------------------------------------------------------------------


def get_postal_addresses_for_tenants(tenant_schemas):
    """
    Pour chaque tenant donne, recupere toutes les PostalAddress avec coords.
    / For each given tenant, fetches all PostalAddress with coords.

    Parametres / Parameters:
        tenant_schemas: list[tuple[str, str]] — liste de (tenant_uuid, schema_name)

    Retourne / Returns:
        dict[str, list[dict]] — {tenant_uuid: [pa_dict, ...]}
        chaque pa_dict contient pa_id, latitude, longitude, name,
        street_address, postal_code, address_locality, address_country.
    """
    from BaseBillet.models import PostalAddress
    from django_tenants.utils import tenant_context
    from Customers.models import Client

    resultat = {}
    for tenant_uuid, schema_name in tenant_schemas:
        try:
            tenant = Client.objects.get(schema_name=schema_name)
        except Client.DoesNotExist:
            continue
        with tenant_context(tenant):
            pa_list = []
            queryset = PostalAddress.objects.exclude(
                latitude__isnull=True
            ).exclude(longitude__isnull=True)
            for pa in queryset:
                pa_list.append({
                    "pa_id": pa.pk,
                    "latitude": float(pa.latitude),
                    "longitude": float(pa.longitude),
                    "name": pa.name or "",
                    "street_address": pa.street_address or "",
                    "postal_code": pa.postal_code or "",
                    "address_locality": pa.address_locality or "",
                    "address_country": pa.address_country or "",
                })
            if pa_list:
                resultat[tenant_uuid] = pa_list
    return resultat


def build_aggregate_points(tenant_schemas, configs_by_tenant, events_by_tenant):
    """
    Construit la liste des points (1 par PA active) pour AGGREGATE_POINTS.
    / Builds the list of points (1 per active PA) for AGGREGATE_POINTS.

    Filtre "tenant vivant" : si le tenant n'est pas dans configs_by_tenant,
    on le skip (= l'appelant a deja filtre par vivacite).
    / "Alive tenant" filter: skip if not in configs_by_tenant.

    Limite events par PA : top 5, et events_futurs_count_total a le total.
    / Events per PA limit: top 5, total in events_futurs_count_total.
    """
    LIMIT_EVENTS_DANS_POPUP = 5

    tenants_vivants = [
        (uuid, schema) for uuid, schema in tenant_schemas if uuid in configs_by_tenant
    ]
    pa_par_tenant = get_postal_addresses_for_tenants(tenants_vivants)

    points = []
    for tenant_uuid, _schema in tenants_vivants:
        config = configs_by_tenant.get(tenant_uuid, {})
        pa_list = pa_par_tenant.get(tenant_uuid, [])
        events_du_tenant = events_by_tenant.get(tenant_uuid, [])

        # Index events par pa_id (1 event est sur 1 seule PA)
        # / Index events by pa_id (1 event lives on 1 PA)
        events_par_pa = {}
        for event in events_du_tenant:
            pa_id = event.get("postal_address_id")
            if pa_id is None:
                continue
            events_par_pa.setdefault(pa_id, []).append(event)

        main_address_id = config.get("postal_address_id")
        for pa in pa_list:
            events_lies = events_par_pa.get(pa["pa_id"], [])
            # Champ "datetime" dans get_events_for_tenants (ISO string).
            # On expose datetime_iso cote sortie pour clarte JS.
            # / Field is "datetime" in get_events_for_tenants; expose as datetime_iso.
            events_tries = sorted(events_lies, key=lambda e: e.get("datetime") or "")
            events_pour_popup = []
            for ev in events_tries[:LIMIT_EVENTS_DANS_POPUP]:
                events_pour_popup.append({
                    "uuid": ev.get("uuid", ""),
                    "name": ev.get("name", ""),
                    "datetime_iso": ev.get("datetime", ""),
                    "slug": ev.get("slug", ""),
                    "tags": ev.get("tags", []),
                    # Vignette de l'event (variation crop), ajoutee dans tasks.py.
                    # / Event thumbnail (crop variation), added in tasks.py.
                    "image_url": ev.get("image_url"),
                })

            address_morceaux = [pa["street_address"], pa["postal_code"], pa["address_locality"]]
            address_morceaux_nettoyes = [m for m in address_morceaux if m]
            address_display = ", ".join(address_morceaux_nettoyes)

            points.append({
                # pa_id unique GLOBALEMENT : PostalAddress.pk repart a 1 dans chaque
                # schema tenant, donc on prefixe par tenant_uuid pour eviter les
                # collisions cote JS (cle des markers). Le matching interne (events,
                # is_main_address) reste sur le pk brut.
                # / Globally unique pa_id: PostalAddress.pk restarts at 1 per tenant
                # schema, so prefix with tenant_uuid to avoid JS marker key collisions.
                "pa_id": f"{tenant_uuid}:{pa['pa_id']}",
                "latitude": pa["latitude"],
                "longitude": pa["longitude"],
                "pa_name": pa["name"] or pa["street_address"] or pa["address_locality"] or config.get("organisation", ""),
                "address_display": address_display,
                "is_main_address": (pa["pa_id"] == main_address_id),
                "tenant_id": tenant_uuid,
                "tenant_organisation": config.get("organisation", ""),
                "tenant_domain": config.get("domain", ""),
                "tenant_logo_url": config.get("logo_url"),
                # Image principale du lieu (social card) — fallback derriere le logo.
                # / Venue main image (social card) — fallback behind the logo.
                "tenant_image_url": config.get("social_card_url"),
                "events_futurs": events_pour_popup,
                "events_futurs_count_total": len(events_tries),
            })

    return {"points": points}


# ---------------------------------------------------------------------------
# Explorer data builder / Constructeur de donnees explorer
# ---------------------------------------------------------------------------


def build_explorer_data_for_tenants(tenant_uuids):
    """
    Renvoie les donnees pour la page explorer ROOT :
    - points : 1 par PA active (pour les markers carte)
    - tenants : 1 par tenant vivant (pour le JSON-LD federation, infos
      tenant-level type locality/country/short_description qui n'ont pas
      de sens au niveau PA).
    / Returns data for the ROOT explorer page:
    - points: 1 per active PA (map markers)
    - tenants: 1 per alive tenant (federation JSON-LD, tenant-level fields)

    Parametres / Parameters:
        tenant_uuids: list[str] — UUIDs des tenants a inclure.
                                  Si vide, retourne {"points": [], "tenants": []}.
    """
    from seo.models import SEOCache
    from seo.views_common import get_seo_cache

    if not tenant_uuids:
        return {"points": [], "tenants": []}

    uuids_set = set(tenant_uuids)
    points_data = get_seo_cache(SEOCache.AGGREGATE_POINTS) or {}
    points_filtres = [
        p for p in points_data.get("points", []) if p.get("tenant_id") in uuids_set
    ]

    # AGGREGATE_LIEUX reste lue ici uniquement pour les infos tenant-level
    # (locality, country, short_description, logo_url) consommees par le
    # JSON-LD federation. Le cache AGGREGATE_LIEUX est maintenu intact par
    # refresh_seo_cache, pas de redondance.
    # / AGGREGATE_LIEUX is still read here only for tenant-level fields
    # consumed by the federation JSON-LD.
    lieux_data = get_seo_cache(SEOCache.AGGREGATE_LIEUX) or {}
    tenants_filtres = [
        lieu for lieu in lieux_data.get("lieux", []) if lieu.get("tenant_id") in uuids_set
    ]

    return {"points": points_filtres, "tenants": tenants_filtres}


def build_explorer_data():
    """
    Wrapper sans filtre : tous les tenants presents dans AGGREGATE_POINTS
    et AGGREGATE_LIEUX.
    / Unfiltered wrapper: all tenants from AGGREGATE_POINTS and AGGREGATE_LIEUX.
    """
    from seo.models import SEOCache
    from seo.views_common import get_seo_cache

    points_data = get_seo_cache(SEOCache.AGGREGATE_POINTS) or {}
    lieux_data = get_seo_cache(SEOCache.AGGREGATE_LIEUX) or {}
    # Union des tenant_ids vus dans l'un ou l'autre cache
    # / Union of tenant_ids seen in either cache
    tenant_uuids = list(
        {p.get("tenant_id") for p in points_data.get("points", []) if p.get("tenant_id")}
        | {l.get("tenant_id") for l in lieux_data.get("lieux", []) if l.get("tenant_id")}
    )
    return build_explorer_data_for_tenants(tenant_uuids)


# ---------------------------------------------------------------------------
# Options d'affichage par tenant / Per-tenant display options
# ---------------------------------------------------------------------------


def appliquer_options_federation(
    explorer_data,
    afficher_seulement_avec_event,
    tri_des_lieux,
    afficher_lieux_sans_adresse=False,
):
    """
    Filtre et trie explorer_data selon les options du tenant (FederationConfiguration).
    N'agit QUE sur la carte/liste : filtre les points (PA) et les tenants.
    / Filter and sort explorer_data according to tenant FederationConfiguration options.

    LOCALISATION : seo/services.py

    Parametres / Parameters:
        explorer_data: dict {"points": [...], "tenants": [...]}
        afficher_seulement_avec_event: bool — si True, ne garde que les lieux
            avec au moins 1 event futur.
        tri_des_lieux: str — "alpha" (nom d'organisation) ou "events" (prochain event).
        afficher_lieux_sans_adresse: bool — si True, injecte un "point sans
            coordonnees" pour chaque tenant sans adresse geocodee (sans point reel),
            pour qu'il apparaisse dans la liste.

    Retourne / Returns: nouveau dict {"points", "tenants"}, filtre et trie.
    """
    points = list(explorer_data.get("points", []))
    tenants = list(explorer_data.get("tenants", []))

    # Lieux sans adresse : on injecte un "point sans coordonnees" par tenant qui
    # n'a aucun point reel. Cote JS, ce point apparait dans la liste mais son
    # marqueur carte est ignore (addMarkers fait `continue` si lat/lng manquent).
    # / Addressless venues: inject one coords-less point per tenant without any
    # real point. The JS lists it but skips its map marker (no lat/lng).
    if afficher_lieux_sans_adresse:
        tenant_ids_avec_point = {p.get("tenant_id") for p in points}
        for tenant in tenants:
            tenant_id = tenant.get("tenant_id")
            if tenant_id in tenant_ids_avec_point:
                continue
            points.append({
                "pa_id": f"addressless-{tenant_id}",
                "latitude": None,
                "longitude": None,
                "pa_name": tenant.get("name", ""),
                "address_display": "",
                "is_main_address": False,
                "tenant_id": tenant_id,
                "tenant_organisation": tenant.get("name", ""),
                "tenant_domain": tenant.get("domain", ""),
                "tenant_logo_url": tenant.get("logo_url"),
                "events_futurs": [],
                "events_futurs_count_total": tenant.get("event_count", 0),
                "is_addressless": True,
            })

    # Filtre "event a venir seulement" / "upcoming event only" filter
    if afficher_seulement_avec_event:
        points = [p for p in points if (p.get("events_futurs_count_total") or 0) > 0]
        tenants = [t for t in tenants if (t.get("event_count") or 0) > 0]

    # Tri des points : l'ordre des cartes lieu (cote JS) suit l'ordre des points.
    # / Sort points: the JS venue-card order follows the points order.
    if tri_des_lieux == "events":
        # Par date du prochain event ; les lieux sans event finissent a la fin.
        # / By next-event date; venues without events go last.
        def cle_prochain_event(point):
            events = point.get("events_futurs") or []
            if not events:
                return "9999"
            return events[0].get("datetime_iso") or "9999"
        points.sort(key=cle_prochain_event)
    else:
        # Alphabetique par nom d'organisation du tenant.
        # / Alphabetical by tenant organisation name.
        points.sort(key=lambda p: (p.get("tenant_organisation") or "").lower())

    return {"points": points, "tenants": tenants}
