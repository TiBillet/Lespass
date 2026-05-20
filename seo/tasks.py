"""
Celery task pour rafraichir le cache SEO cross-tenant.
/ Celery task to refresh the cross-tenant SEO cache.

LOCALISATION: seo/tasks.py

Version V1 allegee : on rafraichit uniquement lieux + events.
Les adhesions, initiatives crowds et monnaies fedow_core sont
volontairement exclues pour cette etape de migration.
/ V1 lightweight version: only refreshes venues + events.
Memberships, crowds initiatives and fedow_core currencies are
deliberately excluded for this migration step.
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

    Pipeline allege (V1) :
    1. get_active_tenants_with_counts() — 1 requete SQL UNION ALL
       (event_count futur publie + product_count BILLET/FREERES/ADHESION)
    2. get_events_for_tenants() — 1 requete SQL UNION ALL
    3. build_tenant_config_data() — N requetes ORM (1 par tenant)
    4. Ecriture SEOCache per-tenant (TENANT_SUMMARY, TENANT_EVENTS)
       — tous les tenants actifs, sans filtre "lieu vivant"
    5. Ecriture SEOCache global (AGGREGATE_EVENTS, AGGREGATE_LIEUX,
       SITEMAP_INDEX) — filtre "lieu vivant" applique : un lieu n'apparait
       que s'il a au moins 1 event futur publie OU au moins 1 produit
       (BILLET, FREERES, ADHESION) publie.
    6. Nettoyage des entrees obsoletes (tenants supprimes)
    7. Ecriture Memcached L1 a chaque update
    """
    from seo.services import (
        build_stdimage_variation_url,
        build_tenant_config_data,
        get_active_tenants_with_counts,
        get_events_for_tenants,
        set_memcached_l1,
    )

    logger.info("Debut refresh_seo_cache / Starting refresh_seo_cache")

    # ------------------------------------------------------------------
    # Etape 1 : Comptes par tenant (1 requete SQL).
    # On recupere a la fois event_count et product_count par tenant ;
    # le product_count sert plus loin a filtrer les "lieux vivants".
    # / Step 1: Per-tenant counts (1 SQL query). We fetch event_count AND
    # product_count per tenant; product_count is used later to filter
    # "alive venues".
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
            "product_count": row["product_count"],
        }

    # ------------------------------------------------------------------
    # Etape 2 : Evenements de tous les tenants (1 requete SQL)
    # / Step 2: Events from all tenants (1 SQL query)
    # ------------------------------------------------------------------
    all_events = get_events_for_tenants(tenant_schemas)

    # Enrichir chaque event avec ses tags (1 requete SQL cross-schema).
    # Un event sans tag recoit tags=[] (defaut). On modifie all_events in-place
    # pour que events_by_tenant herite des tags automatiquement.
    # / Enrich each event with its tags (1 cross-schema SQL query).
    # Events without tags get tags=[]. Mutate all_events in-place so that
    # events_by_tenant inherits tags automatically.
    from seo.services import get_event_tags_for_tenants
    tags_par_event = get_event_tags_for_tenants(tenant_schemas)
    for event in all_events:
        event["tags"] = tags_par_event.get(event.get("uuid", ""), [])

    # Grouper par tenant_id / Group by tenant_id
    events_by_tenant = {}
    for event in all_events:
        tid = event["tenant_id"]
        if tid not in events_by_tenant:
            events_by_tenant[tid] = []
        events_by_tenant[tid].append(event)

    # ------------------------------------------------------------------
    # Etape 3 : Config par tenant (N requetes ORM)
    # / Step 3: Per-tenant config (N ORM queries)
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
    # Etape 4 : Ecriture des entrees par tenant
    # / Step 4: Write per-tenant entries
    # ------------------------------------------------------------------
    for tenant_id in active_tenant_ids:
        client = clients_by_id[tenant_id]
        config_data = configs_by_tenant.get(tenant_id, {})
        counts = counts_by_tenant.get(
            tenant_id, {"event_count": 0, "product_count": 0}
        )
        tenant_events = events_by_tenant.get(tenant_id, [])

        # Enrichir chaque event avec image_url et canonical_url.
        # On utilise le domaine du tenant pour construire les URLs completes.
        # / Enrich each event with image_url and canonical_url.
        # We use the tenant domain to build full URLs.
        tenant_domain = config_data.get("domain", "")
        tenant_name = config_data.get("organisation") or config_data.get("name", "")
        for event in tenant_events:
            # URL de la vignette crop (480x270) / Crop thumbnail URL (480x270)
            event["image_url"] = build_stdimage_variation_url(
                event.get("img", ""), variation="crop"
            )
            # URL canonique vers la page de l'event sur le site du tenant
            # / Canonical URL to the event page on the tenant site
            slug = event.get("slug", "")
            if tenant_domain and slug:
                event["canonical_url"] = f"https://{tenant_domain}/event/{slug}"
            else:
                event["canonical_url"] = None
            # Nom du lieu (tenant) pour affichage / Venue name for display
            event["tenant_name"] = tenant_name

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

    # ------------------------------------------------------------------
    # Etape 5 : Agregats globaux (tenant=None)
    # / Step 5: Global aggregates (tenant=None)
    # ------------------------------------------------------------------

    # Re-enrichir all_events avec image_url, canonical_url, tenant_name pour l'agregat
    # / Re-enrich all_events with image_url, canonical_url, tenant_name for the aggregate
    aggregate_events = []
    for tenant_id in active_tenant_ids:
        aggregate_events.extend(events_by_tenant.get(tenant_id, []))

    # Tri par date croissante pour l'affichage agenda
    # / Sort by ascending date for agenda display
    aggregate_events.sort(key=lambda e: e.get("datetime") or "")

    # aggregate_events : tous les evenements de tous les tenants
    # / aggregate_events: all events from all tenants
    aggregate_events_data = {"events": aggregate_events}
    SEOCache.objects.update_or_create(
        cache_type=SEOCache.AGGREGATE_EVENTS,
        tenant=None,
        defaults={"data": aggregate_events_data},
    )
    set_memcached_l1(SEOCache.AGGREGATE_EVENTS, None, aggregate_events_data)

    # aggregate_lieux : liste des lieux VIVANTS (tenants avec domaine ET
    # au moins 1 event futur publie OU au moins 1 produit BILLET/FREERES/
    # ADHESION publie). Un tenant sans contenu visible ne pollue donc plus
    # le marquee, la page /lieux/ ni la carte explorer.
    # / aggregate_lieux: list of ALIVE venues (with domain AND at least
    # one published future event OR one published BILLET/FREERES/ADHESION
    # product). Empty tenants no longer pollute the marquee, /lieux/ or
    # the explorer map.
    lieux = []
    for tenant_id in active_tenant_ids:
        config = configs_by_tenant.get(tenant_id, {})
        counts = counts_by_tenant.get(
            tenant_id, {"event_count": 0, "product_count": 0}
        )
        domaine_du_tenant = config.get("domain")
        a_des_events = counts.get("event_count", 0) > 0
        a_des_produits = counts.get("product_count", 0) > 0
        lieu_est_vivant = bool(domaine_du_tenant) and (a_des_events or a_des_produits)
        if not lieu_est_vivant:
            continue
        lieux.append(
            {
                "tenant_id": tenant_id,
                "name": config.get("organisation") or config.get("name", ""),
                "domain": domaine_du_tenant,
                "slug": config.get("slug", ""),
                "short_description": config.get("short_description", ""),
                "locality": config.get("locality", ""),
                "country": config.get("country", ""),
                "logo_url": config.get("logo_url"),
                "categorie": config.get("categorie", ""),
                "latitude": config.get("latitude"),
                "longitude": config.get("longitude"),
                "event_count": counts.get("event_count", 0),
                "product_count": counts.get("product_count", 0),
            }
        )
    aggregate_lieux_data = {"lieux": lieux}
    SEOCache.objects.update_or_create(
        cache_type=SEOCache.AGGREGATE_LIEUX,
        tenant=None,
        defaults={"data": aggregate_lieux_data},
    )
    set_memcached_l1(SEOCache.AGGREGATE_LIEUX, None, aggregate_lieux_data)

    # ------------------------------------------------------------------
    # Etape 6 : AGGREGATE_POINTS (1 entree par PA active)
    # Construit la liste des points geo (1 par PostalAddress avec coords,
    # pour chaque tenant vivant) avec les events futurs lies en popup.
    # / Step 6: AGGREGATE_POINTS (1 entry per active PA).
    # Builds the geo points list (1 per PA with coords, for alive tenants)
    # with future events linked for the popup.
    # ------------------------------------------------------------------
    from seo.services import build_aggregate_points

    # Filtre "tenant vivant" : meme regle que pour AGGREGATE_LIEUX
    # (au moins 1 event futur OU 1 produit publie).
    # / Alive filter: same rule as AGGREGATE_LIEUX.
    tenants_vivants_schemas = [
        (tenant_id, schema)
        for tenant_id, schema in tenant_schemas
        if (
            counts_by_tenant.get(tenant_id, {}).get("event_count", 0) > 0
            or counts_by_tenant.get(tenant_id, {}).get("product_count", 0) > 0
        )
    ]
    configs_vivants = {
        tid: configs_by_tenant[tid]
        for tid, _s in tenants_vivants_schemas
        if tid in configs_by_tenant
    }
    events_vivants = {
        tid: events_by_tenant.get(tid, [])
        for tid, _s in tenants_vivants_schemas
    }
    points_data = build_aggregate_points(
        tenants_vivants_schemas, configs_vivants, events_vivants
    )
    SEOCache.objects.update_or_create(
        cache_type=SEOCache.AGGREGATE_POINTS,
        tenant=None,
        defaults={"data": points_data},
    )
    set_memcached_l1(SEOCache.AGGREGATE_POINTS, None, points_data)
    logger.info(
        "AGGREGATE_POINTS ecrit : %d points / written: %d points",
        len(points_data["points"]),
        len(points_data["points"]),
    )

    # sitemap_index : MEME filtre que aggregate_lieux. Inutile de pointer
    # un crawler Google ou un LLM (GPTBot, ClaudeBot) vers un sitemap
    # tenant qui ne contient rien d'autre que la page d'accueil — ca
    # gaspille le crawl budget et dilue le signal qualite du domaine ROOT.
    # / sitemap_index: SAME filter as aggregate_lieux. No point pointing
    # Google or LLM crawlers (GPTBot, ClaudeBot) to a tenant sitemap that
    # holds nothing but the home page — wastes crawl budget and dilutes
    # the ROOT domain's quality signal.
    sitemap_tenants = []
    for tenant_id in active_tenant_ids:
        config = configs_by_tenant.get(tenant_id, {})
        counts = counts_by_tenant.get(
            tenant_id, {"event_count": 0, "product_count": 0}
        )
        domaine_du_tenant = config.get("domain")
        a_des_events = counts.get("event_count", 0) > 0
        a_des_produits = counts.get("product_count", 0) > 0
        lieu_est_vivant = bool(domaine_du_tenant) and (a_des_events or a_des_produits)
        if not lieu_est_vivant:
            continue
        sitemap_tenants.append(
            {
                "tenant_id": tenant_id,
                "domain": domaine_du_tenant,
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
    # Etape 5.bis : Calcul des arretes entrantes de fédération.
    # Pour chaque tenant X, on liste les tenants qui ont une FederatedPlace
    # pointant vers X (= les tenants qui federent AVEC X).
    # Permet a /federation/ d'un tenant d'afficher les voisins qui le federent
    # meme s'il n'a pas declare de relation reciproque.
    # / Step 5.bis: Compute incoming federation edges.
    # For each tenant X, list the tenants that have a FederatedPlace pointing
    # to X (= tenants that federate WITH X).
    # Allows /federation/ of a tenant to display neighbors that federate with
    # them even without a reciprocal declaration.
    # ------------------------------------------------------------------
    # Schema -> uuid lookup pour passer du schema_name (source de l'edge)
    # a l'UUID du tenant source.
    # / schema -> uuid lookup to map source schema_name to source tenant UUID.
    schema_to_uuid = {row["schema_name"]: row["tenant_id"] for row in tenant_counts}

    # Construction par UNION ALL : 1 sous-requete par schema tenant.
    # Chaque ligne donne (source_schema, target_uuid) ou target_uuid est
    # l'UUID du tenant fédéré (FederatedPlace.tenant_id).
    # / UNION ALL build: one sub-query per tenant schema.
    # Each row yields (source_schema, target_uuid).
    incoming_by_tenant = {}
    if tenant_schemas:
        from django.db import connection as _conn
        edge_parts = []
        edge_params = []
        for _tid, schema_name in tenant_schemas:
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
        cache_type=SEOCache.FEDERATION_INCOMING,
        tenant=None,
        defaults={"data": federation_incoming_data},
    )
    set_memcached_l1(SEOCache.FEDERATION_INCOMING, None, federation_incoming_data)

    # ------------------------------------------------------------------
    # Etape 6 : Nettoyage des entrees obsoletes (tenants supprimes/inactifs)
    # / Step 6: Clean up stale entries (deleted/inactive tenants)
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

    # Comptages remontes apres filtre "lieu vivant" — `lieux` est ce que
    # le public verra (marquee root, /lieux/, sitemap). `aggregate_events`
    # est ce qu'on aggrege apres filtre publish + futur sur les events.
    # / Counts after the "alive venue" filter — `lieux` is what the
    # public sees (root marquee, /lieux/, sitemap). `aggregate_events`
    # is what we aggregate after the publish + future event filter.
    nombre_de_lieux_vivants = len(lieux)
    nombre_de_events_publies = len(aggregate_events)
    logger.info(
        "Fin refresh_seo_cache : %d tenants actifs, %d events publies, "
        "%d lieux vivants / Done: %d active tenants, %d published events, "
        "%d alive venues",
        len(active_tenant_ids),
        nombre_de_events_publies,
        nombre_de_lieux_vivants,
        len(active_tenant_ids),
        nombre_de_events_publies,
        nombre_de_lieux_vivants,
    )

    return {
        "tenants": len(active_tenant_ids),
        "events": nombre_de_events_publies,
        "lieux": nombre_de_lieux_vivants,
    }
