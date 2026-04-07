"""
Celery task pour rafraichir le cache SEO cross-tenant.
/ Celery task to refresh the cross-tenant SEO cache.

LOCALISATION: seo/tasks.py
"""

import logging

from celery import shared_task

from Customers.models import Client
from seo.models import SEOCache

logger = logging.getLogger(__name__)


@shared_task(name="seo.tasks.refresh_seo_cache")
def refresh_seo_cache():
    """
    Rafraichit le cache SEO pour tous les tenants actifs.
    Appele par Celery Beat toutes les 4 heures.
    / Refresh SEO cache for all active tenants.
    Called by Celery Beat every 4 hours.

    Pipeline :
    1. get_active_tenants_with_counts() — 1 requete SQL cross-schema
    2. get_events_for_tenants() — 1 requete SQL cross-schema
    3. get_memberships_for_tenants() — 1 requete SQL cross-schema
    4. build_tenant_config_data() — N requetes ORM (1 par tenant)
    5. Ecriture SEOCache (update_or_create)
    6. Nettoyage des entrees obsoletes
    7. Ecriture Memcached L1
    """
    from seo.services import (
        build_tenant_config_data,
        get_active_tenants_with_counts,
        get_events_for_tenants,
        get_memberships_for_tenants,
        set_memcached_l1,
    )

    logger.info("Debut refresh_seo_cache / Starting refresh_seo_cache")

    # ------------------------------------------------------------------
    # Etape 1 : Comptes par tenant (1 requete SQL)
    # / Step 1: Per-tenant counts (1 SQL query)
    # ------------------------------------------------------------------
    tenant_counts = get_active_tenants_with_counts()
    logger.info(
        "Tenants actifs trouves : %d / Active tenants found: %d",
        len(tenant_counts),
        len(tenant_counts),
    )

    # Extraire la liste (uuid, schema_name) pour les requetes suivantes
    # / Extract (uuid, schema_name) list for next queries
    tenant_schemas = [(row["tenant_id"], row["schema_name"]) for row in tenant_counts]

    # Index des counts par tenant_id pour acces rapide
    # / Index counts by tenant_id for fast access
    counts_by_tenant = {}
    for row in tenant_counts:
        counts_by_tenant[row["tenant_id"]] = {
            "event_count": row["event_count"],
            "membership_count": row["membership_count"],
        }

    # ------------------------------------------------------------------
    # Etape 2-3 : Evenements et adhesions (2 requetes SQL)
    # / Step 2-3: Events and memberships (2 SQL queries)
    # ------------------------------------------------------------------
    all_events = get_events_for_tenants(tenant_schemas)
    all_memberships = get_memberships_for_tenants(tenant_schemas)

    # Grouper par tenant_id / Group by tenant_id
    events_by_tenant = {}
    for event in all_events:
        tid = event["tenant_id"]
        if tid not in events_by_tenant:
            events_by_tenant[tid] = []
        events_by_tenant[tid].append(event)

    memberships_by_tenant = {}
    for membership in all_memberships:
        tid = membership["tenant_id"]
        if tid not in memberships_by_tenant:
            memberships_by_tenant[tid] = []
        memberships_by_tenant[tid].append(membership)

    # ------------------------------------------------------------------
    # Etape 4 : Config par tenant (N requetes ORM)
    # / Step 4: Per-tenant config (N ORM queries)
    # ------------------------------------------------------------------
    active_tenant_ids = set()
    configs_by_tenant = {}

    # Charger les objets Client pour build_tenant_config_data
    # / Load Client objects for build_tenant_config_data
    tenant_id_list = [row["tenant_id"] for row in tenant_counts]
    clients = Client.objects.filter(uuid__in=tenant_id_list)
    clients_by_id = {str(c.uuid): c for c in clients}

    for tenant_id, client in clients_by_id.items():
        active_tenant_ids.add(tenant_id)
        config_data = build_tenant_config_data(client)
        configs_by_tenant[tenant_id] = config_data

    # ------------------------------------------------------------------
    # Etape 5 : Ecriture des entrees par tenant
    # / Step 5: Write per-tenant entries
    # ------------------------------------------------------------------
    for tenant_id in active_tenant_ids:
        client = clients_by_id[tenant_id]
        config_data = configs_by_tenant.get(tenant_id, {})
        counts = counts_by_tenant.get(
            tenant_id, {"event_count": 0, "membership_count": 0}
        )
        tenant_events = events_by_tenant.get(tenant_id, [])
        tenant_memberships = memberships_by_tenant.get(tenant_id, [])

        # tenant_summary : config + stats
        summary_data = {
            **config_data,
            **counts,
        }
        SEOCache.objects.update_or_create(
            cache_type=SEOCache.TENANT_SUMMARY,
            tenant=client,
            defaults={"data": summary_data},
        )
        set_memcached_l1(SEOCache.TENANT_SUMMARY, tenant_id, summary_data)

        # tenant_events : liste des evenements du tenant
        # / tenant_events: list of events for this tenant
        SEOCache.objects.update_or_create(
            cache_type=SEOCache.TENANT_EVENTS,
            tenant=client,
            defaults={"data": {"events": tenant_events}},
        )
        set_memcached_l1(SEOCache.TENANT_EVENTS, tenant_id, {"events": tenant_events})

        # tenant_memberships : liste des adhesions du tenant
        # / tenant_memberships: list of memberships for this tenant
        SEOCache.objects.update_or_create(
            cache_type=SEOCache.TENANT_MEMBERSHIPS,
            tenant=client,
            defaults={"data": {"memberships": tenant_memberships}},
        )
        set_memcached_l1(
            SEOCache.TENANT_MEMBERSHIPS, tenant_id, {"memberships": tenant_memberships}
        )

    # ------------------------------------------------------------------
    # Etape 6 : Agregats globaux (tenant=None)
    # / Step 6: Global aggregates (tenant=None)
    # ------------------------------------------------------------------

    # aggregate_events : tous les evenements de tous les tenants
    # / aggregate_events: all events from all tenants
    aggregate_events_data = {"events": all_events}
    SEOCache.objects.update_or_create(
        cache_type=SEOCache.AGGREGATE_EVENTS,
        tenant=None,
        defaults={"data": aggregate_events_data},
    )
    set_memcached_l1(SEOCache.AGGREGATE_EVENTS, None, aggregate_events_data)

    # aggregate_memberships : toutes les adhesions de tous les tenants
    # / aggregate_memberships: all memberships from all tenants
    aggregate_memberships_data = {"memberships": all_memberships}
    SEOCache.objects.update_or_create(
        cache_type=SEOCache.AGGREGATE_MEMBERSHIPS,
        tenant=None,
        defaults={"data": aggregate_memberships_data},
    )
    set_memcached_l1(SEOCache.AGGREGATE_MEMBERSHIPS, None, aggregate_memberships_data)

    # aggregate_lieux : liste des lieux actifs (tenants avec domaine)
    # / aggregate_lieux: list of active venues (tenants with domain)
    lieux = []
    for tenant_id in active_tenant_ids:
        config = configs_by_tenant.get(tenant_id, {})
        if config.get("domain"):
            lieux.append(
                {
                    "tenant_id": tenant_id,
                    "name": config.get("organisation") or config.get("name", ""),
                    "domain": config["domain"],
                    "slug": config.get("slug", ""),
                    "short_description": config.get("short_description", ""),
                    "locality": config.get("locality", ""),
                    "country": config.get("country", ""),
                    "logo_url": config.get("logo_url"),
                    "categorie": config.get("categorie", ""),
                    "latitude": config.get("latitude"),
                    "longitude": config.get("longitude"),
                }
            )
    aggregate_lieux_data = {"lieux": lieux}
    SEOCache.objects.update_or_create(
        cache_type=SEOCache.AGGREGATE_LIEUX,
        tenant=None,
        defaults={"data": aggregate_lieux_data},
    )
    set_memcached_l1(SEOCache.AGGREGATE_LIEUX, None, aggregate_lieux_data)

    # sitemap_index : liste des tenants avec domaine pour le sitemap
    # / sitemap_index: list of tenants with domain for sitemap
    sitemap_tenants = []
    for tenant_id in active_tenant_ids:
        config = configs_by_tenant.get(tenant_id, {})
        if config.get("domain"):
            sitemap_tenants.append(
                {
                    "tenant_id": tenant_id,
                    "domain": config["domain"],
                    "name": config.get("organisation") or config.get("name", ""),
                }
            )
    sitemap_data = {"tenants": sitemap_tenants}
    SEOCache.objects.update_or_create(
        cache_type=SEOCache.SITEMAP_INDEX,
        tenant=None,
        defaults={"data": sitemap_data},
    )
    set_memcached_l1(SEOCache.SITEMAP_INDEX, None, sitemap_data)

    # ------------------------------------------------------------------
    # Etape 7 : Nettoyage des entrees obsoletes (tenants supprimes/inactifs)
    # / Step 7: Clean up stale entries (deleted/inactive tenants)
    # ------------------------------------------------------------------
    stale_count = (
        SEOCache.objects.exclude(tenant__isnull=True)
        .exclude(tenant__uuid__in=tenant_id_list)
        .delete()[0]
    )

    if stale_count > 0:
        logger.info(
            "Entrees obsoletes supprimees : %d / Stale entries deleted: %d",
            stale_count,
            stale_count,
        )

    logger.info(
        "Fin refresh_seo_cache : %d tenants, %d events, %d memberships / "
        "Done refresh_seo_cache: %d tenants, %d events, %d memberships",
        len(active_tenant_ids),
        len(all_events),
        len(all_memberships),
        len(active_tenant_ids),
        len(all_events),
        len(all_memberships),
    )

    return {
        "tenants": len(active_tenant_ids),
        "events": len(all_events),
        "memberships": len(all_memberships),
    }
