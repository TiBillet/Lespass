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


# Débounce "trailing" du rebuild d'agrégats (cf. SESSIONS/SEO/CHANTIER-08).
# Le rebuild s'exécute ce nombre de secondes APRES la dernière modif
# (event/adresse), pas après la première. Garde la carte ~fraiche sans
# spammer le rebuild quand un éditeur enchaine plusieurs sauvegardes.
# / Trailing debounce of the aggregate rebuild: runs this many seconds AFTER
# the last change, not the first.
REBUILD_TRAILING_WINDOW = 15  # secondes / seconds

# Plafond "maxWait" anti-famine (cf. CHANTIER-08 §10). Sous un flux CONTINU de
# modifs (plus rapprochees que la fenetre trailing), l'echeance serait repoussee
# indefiniment et le rebuild ne partirait jamais avant le beat 4h. Le plafond
# garantit un rebuild au plus tard ce nombre de secondes apres la PREMIERE modif
# d'une serie, meme si les modifs continuent. Borne aussi la charge a
# <= 1 rebuild / REBUILD_MAXWAIT sous flux dense, quel que soit le nb de tenants.
# / "maxWait" cap against starvation: guarantees a rebuild at most this many
# seconds after the FIRST change of a burst, and bounds load under heavy flow.
REBUILD_MAXWAIT = 60  # secondes / seconds

# Tolérance pour le jitter d'ordonnancement Celery : si le rebuild se réveille
# à moins de cette marge de l'échéance, on considère l'échéance atteinte.
# / Tolerance for Celery scheduling jitter: deadline considered reached if the
# rebuild wakes up within this margin of it.
REBUILD_MARGE = 2  # secondes / seconds

# Clés du débounce GLOBAL du rebuild. Elles doivent être partagées par TOUS les
# schemas (le rebuild recombine tout le réseau, peu importe quel tenant le
# declenche). Comme le cache 'default' prefixe les cles par schema
# (django-tenants make_key, cf. CHANTIER-08 bug L1), on accede a ces cles sous
# schema_context("public") via les helpers _debounce_* ci-dessous.
# / Global rebuild debounce keys, shared across ALL schemas. Accessed under the
# public schema (see L1 bug) so they are not per-tenant prefixed.
CLE_ECHEANCE = "seo_rebuild_echeance"   # cible "trailing" : derniere modif + WINDOW
CLE_PLAFOND = "seo_rebuild_plafond"     # cible "maxWait" : premiere modif + MAXWAIT
CLE_PLANIFIE = "seo_rebuild_planifie"   # verrou : un rebuild "en vol"


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


def planifier_rebuild_agregats():
    """
    Débounce "trailing" : pousse l'échéance du rebuild et planifie une passe.
    / Trailing debounce: push the rebuild deadline and schedule one pass.

    LOCALISATION : seo/tasks.py

    Appelé par le signal post_save/post_delete Event/PostalAddress
    (cf. BaseBillet/signals.py:declencher_refresh_seo_cache). Chaque modif
    repousse l'échéance à maintenant + REBUILD_TRAILING_WINDOW. On ne planifie
    qu'UNE tâche rebuild par fenêtre (verrou seo_rebuild_planifie) ; cette tâche
    se replanifie elle-même si l'échéance a encore bougé (cf. rebuild_seo_aggregates),
    ce qui garantit qu'un rebuild s'exécute toujours APRES la dernière modif.
    / Called by the Event/PostalAddress post_save/post_delete signal. Each change
    pushes the deadline; only one rebuild task is scheduled per window, and it
    reschedules itself if the deadline moved again — guaranteeing a rebuild always
    runs AFTER the last change.
    """
    import time

    from django.core.cache import cache
    from django_tenants.utils import schema_context

    maintenant = time.time()

    # Toutes les cles du debounce sont GLOBALES (partagees par tous les schemas) :
    # on les manipule sous schema_context("public") pour neutraliser le prefixe
    # de schema applique par django-tenants (cf. CHANTIER-08 bug L1).
    # / All debounce keys are GLOBAL: manipulated under the public schema.
    with schema_context("public"):
        # Echeance "trailing" : repoussee a CHAQUE modif (derniere modif + WINDOW).
        # / Trailing deadline: pushed on every change.
        cache.set(CLE_ECHEANCE, maintenant + REBUILD_TRAILING_WINDOW, 3600)

        # Plafond "maxWait" : pose UNE SEULE FOIS (cache.add) au debut d'une serie.
        # Non repousse -> garantit un rebuild au plus tard MAXWAIT apres la 1ere modif.
        # / maxWait cap: set ONCE at the start of a burst, never pushed.
        cache.add(CLE_PLAFOND, maintenant + REBUILD_MAXWAIT, 3600)

        # Verrou : une seule tache rebuild "en vol". TTL large (> plafond + marge).
        # / Lock: a single rebuild in flight. TTL safely above the cap.
        nouveau_rebuild = cache.add(CLE_PLANIFIE, "1", REBUILD_MAXWAIT + 120)

    if nouveau_rebuild:
        rebuild_seo_aggregates.apply_async(countdown=REBUILD_TRAILING_WINDOW)


@shared_task(name="seo.tasks.rebuild_seo_aggregates")
def rebuild_seo_aggregates(force=False):
    """
    Recompose AGGREGATE_EVENTS / AGGREGATE_POINTS / AGGREGATE_LIEUX / SITEMAP_INDEX
    a partir des fragments TENANT_* (lecture SEOCache, ZERO cross-schema).
    Ne touche PAS FEDERATION_INCOMING (depend des FederatedPlace -> beat seulement).
    / Recompose aggregates from TENANT_* fragments (no cross-schema). Excludes incoming edges.

    Débounce "trailing" (cf. CHANTIER-08) : si une modif plus récente a repoussé
    l'échéance, on NE recombine PAS maintenant (le fragment du tenant n'est
    peut-être pas encore à jour) — on se replanifie pile à l'échéance et on rend
    la main. Le beat 4h passe force=True : il recombine toujours (filet anti-dérive).
    / Trailing debounce: if a more recent change pushed the deadline, do NOT
    recombine now; reschedule for the deadline and return. The 4h beat passes
    force=True and always recombines (safety net).
    """
    import time

    from django.core.cache import cache
    from django_tenants.utils import schema_context

    from seo.services import set_memcached_l1

    # Echeance retenue a l'entree du recombine, pour detecter une modif arrivee
    # PENDANT le recombine (cf. bloc de cloture en fin de fonction).
    # / Deadline captured at recombine entry, to detect a change landing DURING it.
    echeance_au_debut = None
    if not force:
        maintenant = time.time()
        # Cles globales -> lecture sous schema public (cf. planifier_rebuild_agregats).
        # / Global keys -> read under the public schema.
        with schema_context("public"):
            echeance = cache.get(CLE_ECHEANCE)
            plafond = cache.get(CLE_PLAFOND)

        # Moment effectif du rebuild = le PLUS TOT entre l'echeance "trailing"
        # (derniere modif + WINDOW) et le plafond "maxWait" (1ere modif + MAXWAIT).
        # Le plafond empeche la famine sous flux continu.
        # / Effective rebuild time = the EARLIEST of the trailing deadline and the
        # maxWait cap. The cap prevents starvation under continuous flow.
        cible = echeance
        if plafond is not None and (cible is None or plafond < cible):
            cible = plafond

        if cible is not None and maintenant < cible - REBUILD_MARGE:
            # Pas encore l'heure : on se replanifie pile a la cible et on rend la main.
            # / Not yet: reschedule exactly at the target and return.
            delai_restant = cible - maintenant
            rebuild_seo_aggregates.apply_async(countdown=delai_restant)
            return {"rescheduled": True, "countdown": delai_restant}

        # On va recombiner. Le verrou (CLE_PLANIFIE) reste TENU jusqu'a la fin du
        # recombine (libere dans le bloc de cloture) : aucun rebuild concurrent ne
        # demarre. On retient l'echeance courante : si une modif arrive PENDANT le
        # recombine, elle ne pourra ni se planifier (verrou tenu) ni etre incluse
        # (son fragment est a +5s) -> on la rattrapera en fin de fonction.
        # / Keep the lock HELD through the recombine; remember the deadline to catch
        # a change landing meanwhile (it can neither schedule nor be included).
        echeance_au_debut = echeance

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

    # Cloture du debounce (chemin signal uniquement). On libere le verrou + le
    # plafond APRES le recombine. Si l'echeance a bouge entre-temps, c'est qu'une
    # modif est arrivee pendant le recombine sans pouvoir se planifier (verrou tenu) :
    # on replanifie une passe pour la rattraper, au lieu d'attendre le beat 4h.
    # / Debounce close-out (signal path only): release lock + cap AFTER the recombine.
    # If the deadline moved meanwhile, a change couldn't schedule -> reschedule a pass.
    if not force:
        with schema_context("public"):
            echeance_apres = cache.get(CLE_ECHEANCE)
            cache.delete(CLE_PLANIFIE)
            cache.delete(CLE_PLAFOND)
        if echeance_apres is not None and echeance_apres != echeance_au_debut:
            planifier_rebuild_agregats()

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
    # force=True : le beat recombine toujours, sans tenir compte du débounce
    # trailing (filet anti-dérive). / force=True: the beat always recombines.
    aggregats = rebuild_seo_aggregates(force=True)

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
