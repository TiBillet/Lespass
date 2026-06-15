"""
Celery tasks pour le cache SEO cross-tenant.
/ Celery tasks for the cross-tenant SEO cache.

LOCALISATION: seo/tasks.py

Architecture (cf. SESSIONS/SEO/CHANTIER-07) : producteur / agregateur.
- refresh_tenant_seo_cache(tenant_id) : recalcule les fragments d'UN tenant
  (TENANT_SUMMARY, TENANT_EVENTS, TENANT_POINTS). Declenche par post_save (cible).
- rebuild_seo_aggregates() : recompose les agregats globaux par recombinaison des
  fragments (lecture SEOCache, zero cross-schema).
- refresh_seo_cache() : orchestrateur du beat 4h (tous les fragments + rebuild +
  FEDERATION_INCOMING + nettoyage stale). Filet anti-derive.

Version allegee : on porte uniquement lieux + events (pas adhesions/crowds/fedow_core).
/ Lightweight version: venues + events only.
"""

import logging

from celery import shared_task

from Customers.models import Client
from seo.models import SEOCache

logger = logging.getLogger(__name__)


@shared_task(name="seo.tasks.refresh_tenant_seo_cache")
def refresh_tenant_seo_cache(tenant_id):
    """
    Recalcule les fragments SEO d'UN tenant : TENANT_SUMMARY, TENANT_EVENTS, TENANT_POINTS.
    N'ecrit AUCUN agregat (cf. rebuild_seo_aggregates). Cout : 1 schema.
    / Recompute one tenant's SEO fragments. No aggregate writes here.

    Parametres / Parameters: tenant_id (str uuid du Client)
    """
    from seo.services import (
        build_aggregate_points,
        build_stdimage_variation_url,
        build_tenant_config_data,
        get_counts_for_tenant,
        get_event_tags_for_tenants,
        get_events_for_tenants,
        set_memcached_l1,
    )

    try:
        client = Client.objects.get(uuid=tenant_id)
    except Client.DoesNotExist:
        logger.warning("refresh_tenant_seo_cache : tenant %s introuvable", tenant_id)
        return None
    if client.categorie in (Client.ROOT, Client.WAITING_CONFIG):
        return None

    tenant_uuid = str(client.uuid)
    schema = client.schema_name
    tenant_schemas = [(tenant_uuid, schema)]

    # 1. Comptes (1 schema) / Counts (1 schema)
    counts = get_counts_for_tenant(schema)

    # 2. Events + tags / Events + tags
    events = get_events_for_tenants(tenant_schemas)
    tags_par_event = get_event_tags_for_tenants(tenant_schemas)
    for event in events:
        event["tags"] = tags_par_event.get(event.get("uuid", ""), [])

    # 3. Config du tenant / Tenant config
    config_data = build_tenant_config_data(client)

    # 4. Enrichir les events (image crop, url canonique, nom du lieu)
    # / Enrich events (crop image, canonical url, venue name)
    tenant_domain = config_data.get("domain", "")
    tenant_name = config_data.get("organisation") or config_data.get("name", "")
    for event in events:
        event["image_url"] = build_stdimage_variation_url(
            event.get("img", ""), variation="crop"
        )
        slug = event.get("slug", "")
        if tenant_domain and slug:
            event["canonical_url"] = f"https://{tenant_domain}/event/{slug}"
        else:
            event["canonical_url"] = None
        event["tenant_name"] = tenant_name

    # 5. Ecriture des fragments / Write fragments
    summary_data = {**config_data, **counts}
    SEOCache.objects.update_or_create(
        cache_type=SEOCache.TENANT_SUMMARY,
        tenant=client,
        defaults={"data": summary_data},
    )
    set_memcached_l1(SEOCache.TENANT_SUMMARY, tenant_uuid, summary_data)

    events_data = {"events": events}
    SEOCache.objects.update_or_create(
        cache_type=SEOCache.TENANT_EVENTS,
        tenant=client,
        defaults={"data": events_data},
    )
    set_memcached_l1(SEOCache.TENANT_EVENTS, tenant_uuid, events_data)

    # TENANT_POINTS : points (PA geocodees) SI le lieu est "vivant" (domaine + au
    # moins 1 event futur OU 1 produit), sinon liste vide. Meme regle que l'agregat
    # historique pour preserver l'equivalence.
    # / TENANT_POINTS: points only if the venue is "alive", else empty list.
    a_des_events = counts.get("event_count", 0) > 0
    a_des_produits = counts.get("product_count", 0) > 0
    lieu_est_vivant = bool(tenant_domain) and (a_des_events or a_des_produits)
    if lieu_est_vivant:
        points_data = build_aggregate_points(
            tenant_schemas, {tenant_uuid: config_data}, {tenant_uuid: events}
        )
    else:
        points_data = {"points": []}
    SEOCache.objects.update_or_create(
        cache_type=SEOCache.TENANT_POINTS,
        tenant=client,
        defaults={"data": points_data},
    )
    set_memcached_l1(SEOCache.TENANT_POINTS, tenant_uuid, points_data)

    return {
        "tenant": tenant_uuid,
        "events": len(events),
        "points": len(points_data.get("points", [])),
        "vivant": lieu_est_vivant,
    }


@shared_task(name="seo.tasks.rebuild_seo_aggregates")
def rebuild_seo_aggregates():
    """
    Recompose AGGREGATE_EVENTS / AGGREGATE_POINTS / AGGREGATE_LIEUX / SITEMAP_INDEX
    a partir des fragments TENANT_* (lecture SEOCache, ZERO cross-schema).
    Ne touche PAS FEDERATION_INCOMING (depend des FederatedPlace -> beat seulement).
    / Recompose aggregates from TENANT_* fragments (no cross-schema). Excludes incoming edges.
    """
    from seo.services import set_memcached_l1

    # AGGREGATE_EVENTS : concat de tous les TENANT_EVENTS, tri date asc.
    # / Concatenation of all TENANT_EVENTS, sorted by ascending date.
    aggregate_events = []
    for entry in SEOCache.objects.filter(cache_type=SEOCache.TENANT_EVENTS):
        aggregate_events.extend(entry.data.get("events", []))
    aggregate_events.sort(key=lambda e: e.get("datetime") or "")
    aggregate_events_data = {"events": aggregate_events}
    SEOCache.objects.update_or_create(
        cache_type=SEOCache.AGGREGATE_EVENTS, tenant=None,
        defaults={"data": aggregate_events_data},
    )
    set_memcached_l1(SEOCache.AGGREGATE_EVENTS, None, aggregate_events_data)

    # AGGREGATE_POINTS : concat des TENANT_POINTS (deja filtres "vivant" a la source).
    # / Concatenation of all TENANT_POINTS (already alive-filtered at the source).
    aggregate_points = []
    for entry in SEOCache.objects.filter(cache_type=SEOCache.TENANT_POINTS):
        aggregate_points.extend(entry.data.get("points", []))
    aggregate_points_data = {"points": aggregate_points}
    SEOCache.objects.update_or_create(
        cache_type=SEOCache.AGGREGATE_POINTS, tenant=None,
        defaults={"data": aggregate_points_data},
    )
    set_memcached_l1(SEOCache.AGGREGATE_POINTS, None, aggregate_points_data)

    # AGGREGATE_LIEUX + SITEMAP_INDEX : filtre "lieu vivant" sur les TENANT_SUMMARY.
    # / Alive-venue filter on TENANT_SUMMARY fragments.
    lieux = []
    sitemap_tenants = []
    for entry in SEOCache.objects.filter(cache_type=SEOCache.TENANT_SUMMARY):
        config = entry.data
        domaine_du_tenant = config.get("domain")
        a_des_events = config.get("event_count", 0) > 0
        a_des_produits = config.get("product_count", 0) > 0
        lieu_est_vivant = bool(domaine_du_tenant) and (a_des_events or a_des_produits)
        if not lieu_est_vivant:
            continue
        tenant_uuid = config.get("tenant_id")
        nom = config.get("organisation") or config.get("name", "")
        lieux.append({
            "tenant_id": tenant_uuid,
            "name": nom,
            "domain": domaine_du_tenant,
            "slug": config.get("slug", ""),
            "short_description": config.get("short_description", ""),
            "locality": config.get("locality", ""),
            "country": config.get("country", ""),
            "logo_url": config.get("logo_url"),
            # Image principale du lieu (social card) — fallback derriere le logo cote carto.
            # / Venue main image — fallback behind the logo in the map.
            "image_url": config.get("social_card_url"),
            "categorie": config.get("categorie", ""),
            "latitude": config.get("latitude"),
            "longitude": config.get("longitude"),
            "event_count": config.get("event_count", 0),
            "product_count": config.get("product_count", 0),
        })
        sitemap_tenants.append({
            "tenant_id": tenant_uuid,
            "domain": domaine_du_tenant,
            "name": nom,
        })

    aggregate_lieux_data = {"lieux": lieux}
    SEOCache.objects.update_or_create(
        cache_type=SEOCache.AGGREGATE_LIEUX, tenant=None,
        defaults={"data": aggregate_lieux_data},
    )
    set_memcached_l1(SEOCache.AGGREGATE_LIEUX, None, aggregate_lieux_data)

    sitemap_data = {"tenants": sitemap_tenants}
    SEOCache.objects.update_or_create(
        cache_type=SEOCache.SITEMAP_INDEX, tenant=None,
        defaults={"data": sitemap_data},
    )
    set_memcached_l1(SEOCache.SITEMAP_INDEX, None, sitemap_data)

    logger.info(
        "rebuild_seo_aggregates : %d events, %d points, %d lieux vivants",
        len(aggregate_events), len(aggregate_points), len(lieux),
    )
    return {
        "events": len(aggregate_events),
        "points": len(aggregate_points),
        "lieux": len(lieux),
    }


@shared_task(name="seo.tasks.refresh_seo_cache")
def refresh_seo_cache():
    """
    Beat 4h : recalcul INTEGRAL. Boucle refresh_tenant_seo_cache sur tous les tenants
    actifs + rebuild_seo_aggregates() + FEDERATION_INCOMING (cross-schema, ici seulement)
    + nettoyage des entrees obsoletes. Filet anti-derive.
    / Full 4h rebuild: per-tenant fragments + aggregates + incoming edges + stale cleanup.
    """
    from django.db import connection as _conn
    from seo.services import set_memcached_l1

    logger.info("Debut refresh_seo_cache / Starting refresh_seo_cache")

    excluded_categories = [Client.ROOT, Client.WAITING_CONFIG]
    tenants = list(Client.objects.exclude(categorie__in=excluded_categories))
    tenant_id_list = [str(t.uuid) for t in tenants]
    tenant_schemas = [(str(t.uuid), t.schema_name) for t in tenants]
    logger.info("Tenants actifs trouves : %d", len(tenants))

    # 1. Fragments par tenant / Per-tenant fragments
    for tenant in tenants:
        refresh_tenant_seo_cache(str(tenant.uuid))

    # 2. Agregats par recombinaison / Aggregates by recombination
    aggregats = rebuild_seo_aggregates()

    # 3. FEDERATION_INCOMING : arretes entrantes (depend des FederatedPlace, cross-schema).
    # Recalcule UNIQUEMENT ici (beat), pas dans rebuild_seo_aggregates.
    # / Incoming federation edges (depend on FederatedPlace, cross-schema). Beat only.
    schema_to_uuid = {schema: uuid for uuid, schema in tenant_schemas}
    incoming_by_tenant = {}
    if tenant_schemas:
        edge_parts = []
        edge_params = []
        for _uuid, schema_name in tenant_schemas:
            edge_parts.append(
                f"SELECT %s AS source_schema, tenant_id::text AS target_uuid "
                f'FROM "{schema_name}"."BaseBillet_federatedplace"'
            )
            edge_params.append(schema_name)

        edge_sql = " UNION ALL ".join(edge_parts)

        with _conn.cursor() as cursor:
            cursor.execute(edge_sql, edge_params)
            for source_schema, target_uuid in cursor.fetchall():
                source_uuid = schema_to_uuid.get(source_schema)
                if not source_uuid or not target_uuid:
                    continue
                # On ne note pas les self-loops (un tenant qui se federe lui-meme)
                # / Skip self-loops (a tenant federating with itself)
                if source_uuid == target_uuid:
                    continue
                incoming_by_tenant.setdefault(target_uuid, []).append(source_uuid)

        # Tri stable des UUIDs sources pour chaque target.
        # / Stable sort of source UUIDs for each target.
        for target_uuid in incoming_by_tenant:
            incoming_by_tenant[target_uuid] = sorted(set(incoming_by_tenant[target_uuid]))

    federation_incoming_data = {"by_tenant": incoming_by_tenant}
    SEOCache.objects.update_or_create(
        cache_type=SEOCache.FEDERATION_INCOMING, tenant=None,
        defaults={"data": federation_incoming_data},
    )
    set_memcached_l1(SEOCache.FEDERATION_INCOMING, None, federation_incoming_data)

    # 4. Nettoyage des entrees obsoletes (tenants supprimes/inactifs)
    # / Clean up stale entries (deleted/inactive tenants)
    stale_count = (
        SEOCache.objects.exclude(tenant__isnull=True)
        .exclude(tenant__uuid__in=tenant_id_list)
        .delete()[0]
    )
    if stale_count > 0:
        logger.info("Entrees obsoletes supprimees : %d", stale_count)

    logger.info("Fin refresh_seo_cache : %d tenants actifs", len(tenants))
    return {
        "tenants": len(tenants),
        "events": aggregats.get("events", 0),
        "lieux": aggregats.get("lieux", 0),
    }
