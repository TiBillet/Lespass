# PLAN 07 — Cache SEO en fragments par tenant (implémentation)

> **For agentic workers :** exécution **inline** (executing-plans). Étapes en checkbox.
> **Spec :** [CHANTIER-07-cache-fragments.md](CHANTIER-07-cache-fragments.md).
> **Contraintes :** AUCUN git de l'assistant (remplacer « commit » par « → le mainteneur
> committe ») · pas de `makemessages` auto · règle des 3 fichiers avant `check` + tests ·
> serveur tenu par le mainteneur dans byobu.
> **Lancer pytch dans le conteneur :** injecter `API_KEY` (cf. fixture `_inject_cli_env`) :
> `KEY=$(docker exec -e TEST=1 lespass_django poetry run python manage.py test_api_key | tail -1)`
> puis `docker exec -e TEST=1 -e API_KEY="$KEY" lespass_django poetry run pytest …`

**Goal :** découper `refresh_seo_cache` en `refresh_tenant_seo_cache(tenant_id)` (fragments
d'1 tenant) + `rebuild_seo_aggregates()` (recombinaison) + orchestrateur beat, et brancher le
`post_save` sur le refresh ciblé + rebuild débouncés.

**Architecture :** producteur (fragments `TENANT_*` par tenant) / agrégateur (recombinaison
des fragments en `AGGREGATE_*`, zéro cross-schema). `FEDERATION_INCOMING` reste au beat.

**Tech Stack :** Django, django-tenants, Celery, `django.core.cache`, pytest.

---

## Structure des fichiers

| Fichier | Rôle dans ce chantier |
|---|---|
| `seo/models.py` | + `cache_type` `TENANT_POINTS` |
| `seo/services.py` | + `get_counts_for_tenant(schema_name)` (variante 1-tenant des counts) |
| `seo/tasks.py` | `refresh_tenant_seo_cache(tenant_id)`, `rebuild_seo_aggregates()`, `refresh_seo_cache()` réécrit en orchestrateur |
| `BaseBillet/signals.py` | signal → `refresh_tenant_seo_cache(tenant)` + `rebuild_seo_aggregates` débouncés |
| `tests/pytest/test_seo_cache_fragments.py` | tests fragments/rebuild/équivalence/débounce |

---

### Task 1 : `cache_type` `TENANT_POINTS` + migration

**Files :** Modify `seo/models.py` (bloc constantes + `CACHE_TYPE_CHOICES`)

- [ ] **1.1** Ajouter la constante après `TENANT_EVENTS` :
```python
    TENANT_POINTS = "tenant_points"
```
- [ ] **1.2** Ajouter le choix dans `CACHE_TYPE_CHOICES` (après la ligne `TENANT_EVENTS`) :
```python
        (TENANT_POINTS, _("Points (PA) for tenant")),
```
- [ ] **1.3** `docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations seo`
  (génère un `alter_seocache_cache_type`, no-op DB comme `0002/0003`).
- [ ] **1.4** `migrate_schemas --executor=multiprocessing` + `manage.py check` → 0 issue.
- [ ] **1.5** → le mainteneur committe.

---

### Task 2 : `get_counts_for_tenant(schema_name)` (services.py)

**Files :** Modify `seo/services.py` (après `get_active_tenants_with_counts`)

Réutilise la même logique de comptage (event futur publié + produits BILLET/FREERES/ADHESION)
mais sur **un seul** schema.

- [ ] **2.1** Ajouter :
```python
def get_counts_for_tenant(schema_name):
    """
    Compte, pour UN schema tenant, les events futurs publies et les produits
    "lieu vivant" (BILLET/FREERES/ADHESION) publies. Une requete sur 1 schema.
    / Per-tenant counts (1 schema): published future events + alive-venue products.

    Retourne / Returns: dict {"event_count": int, "product_count": int}
    """
    now = timezone.now()
    placeholders_categories = ", ".join(["%s"] * len(CATEGORIES_PRODUIT_LIEU_VIVANT))
    sql = (
        f"SELECT "
        f"(SELECT COUNT(*) FROM \"{schema_name}\".\"BaseBillet_event\" "
        f" WHERE published = true AND datetime >= %s) AS event_count, "
        f"(SELECT COUNT(*) FROM \"{schema_name}\".\"BaseBillet_product\" "
        f" WHERE publish = true AND categorie_article IN ({placeholders_categories})) AS product_count"
    )
    params = [now, *CATEGORIES_PRODUIT_LIEU_VIVANT]
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        row = cursor.fetchone()
    return {"event_count": row[0], "product_count": row[1]}
```
- [ ] **2.2** Test rapide en shell (conteneur up) :
```bash
docker exec lespass_django poetry run python manage.py shell -c \
"from seo.services import get_counts_for_tenant; print(get_counts_for_tenant('lespass'))"
```
Attendu : `{'event_count': N, 'product_count': M}` cohérent.
- [ ] **2.3** → le mainteneur committe.

---

### Task 3 : `refresh_tenant_seo_cache(tenant_id)` (tasks.py)

**Files :** Modify `seo/tasks.py`

Cette tâche calcule les **3 fragments** d'un tenant. Elle réutilise les helpers existants en
leur passant une liste d'**un** tenant. **Reprendre fidèlement** l'enrichissement events de
l'actuel `refresh_seo_cache` étape 4 (image_url crop, canonical_url, tenant_name).

- [ ] **3.1** Ajouter la tâche (le corps reprend, pour 1 tenant, les étapes 1-4 + points) :
```python
@shared_task(name="seo.tasks.refresh_tenant_seo_cache")
def refresh_tenant_seo_cache(tenant_id):
    """
    Recalcule les fragments SEO d'UN tenant : TENANT_SUMMARY, TENANT_EVENTS, TENANT_POINTS.
    Aucune ecriture d'agregat ici (cf. rebuild_seo_aggregates).
    / Recompute one tenant's SEO fragments. No aggregate writes here.
    """
    from django_tenants.utils import tenant_context  # noqa: F401 (cohérence)
    from seo.services import (
        build_stdimage_variation_url, build_tenant_config_data,
        get_counts_for_tenant, get_events_for_tenants, get_event_tags_for_tenants,
        build_aggregate_points, set_memcached_l1,
    )
    try:
        client = Client.objects.get(uuid=tenant_id)
    except Client.DoesNotExist:
        logger.warning("refresh_tenant_seo_cache: tenant %s introuvable", tenant_id)
        return
    if client.categorie in (Client.ROOT, Client.WAITING_CONFIG):
        return

    tenant_uuid = str(client.uuid)
    schema = client.schema_name
    tenant_schemas = [(tenant_uuid, schema)]

    counts = get_counts_for_tenant(schema)
    events = get_events_for_tenants(tenant_schemas)
    tags_par_event = get_event_tags_for_tenants(tenant_schemas)
    for ev in events:
        ev["tags"] = tags_par_event.get(ev.get("uuid", ""), [])

    config_data = build_tenant_config_data(client)
    tenant_domain = config_data.get("domain", "")
    tenant_name = config_data.get("organisation") or config_data.get("name", "")
    for ev in events:
        ev["image_url"] = build_stdimage_variation_url(ev.get("img", ""), variation="crop")
        slug = ev.get("slug", "")
        ev["canonical_url"] = f"https://{tenant_domain}/event/{slug}" if (tenant_domain and slug) else None
        ev["tenant_name"] = tenant_name

    # TENANT_SUMMARY (config + counts) / TENANT_EVENTS / TENANT_POINTS
    summary_data = {**config_data, **counts}
    SEOCache.objects.update_or_create(
        cache_type=SEOCache.TENANT_SUMMARY, tenant=client, defaults={"data": summary_data})
    set_memcached_l1(SEOCache.TENANT_SUMMARY, tenant_uuid, summary_data)

    events_data = {"events": events}
    SEOCache.objects.update_or_create(
        cache_type=SEOCache.TENANT_EVENTS, tenant=client, defaults={"data": events_data})
    set_memcached_l1(SEOCache.TENANT_EVENTS, tenant_uuid, events_data)

    # Points : build_aggregate_points pour 1 tenant (filtre vivant applique par l'appelant
    # via configs ; ici on passe la config telle quelle).
    points_data = build_aggregate_points(
        tenant_schemas, {tenant_uuid: config_data}, {tenant_uuid: events})
    SEOCache.objects.update_or_create(
        cache_type=SEOCache.TENANT_POINTS, tenant=client, defaults={"data": points_data})
    set_memcached_l1(SEOCache.TENANT_POINTS, tenant_uuid, points_data)

    return {"tenant": tenant_uuid, "events": len(events),
            "points": len(points_data.get("points", []))}
```
- [ ] **3.2** `manage.py check` → 0 issue.
- [ ] **3.3** Shell : `refresh_tenant_seo_cache('<uuid lespass>')` écrit bien les 3 fragments.
- [ ] **3.4** → le mainteneur committe.

---

### Task 4 : `rebuild_seo_aggregates()` (tasks.py)

**Files :** Modify `seo/tasks.py`

Recompose les agrégats **par lecture des fragments** `TENANT_*` (zéro cross-schema). Applique
le filtre « lieu vivant » (domaine + `event_count>0` OU `product_count>0`).

- [ ] **4.1** Ajouter :
```python
@shared_task(name="seo.tasks.rebuild_seo_aggregates")
def rebuild_seo_aggregates():
    """
    Recompose AGGREGATE_EVENTS/LIEUX/POINTS + SITEMAP_INDEX a partir des fragments
    TENANT_* (lecture SEOCache, zero cross-schema). Ne touche pas FEDERATION_INCOMING.
    / Recompose aggregates from TENANT_* fragments (no cross-schema).
    """
    from seo.services import set_memcached_l1

    summaries = {c.tenant_id: c.data for c in
                 SEOCache.objects.filter(cache_type=SEOCache.TENANT_SUMMARY).select_related(None)}
    events_frags = {c.tenant_id: c.data for c in
                    SEOCache.objects.filter(cache_type=SEOCache.TENANT_EVENTS)}
    points_frags = {c.tenant_id: c.data for c in
                    SEOCache.objects.filter(cache_type=SEOCache.TENANT_POINTS)}

    # AGGREGATE_EVENTS : concat de tous les events, tri date asc
    aggregate_events = []
    for data in events_frags.values():
        aggregate_events.extend(data.get("events", []))
    aggregate_events.sort(key=lambda e: e.get("datetime") or "")
    agg_events_data = {"events": aggregate_events}
    SEOCache.objects.update_or_create(
        cache_type=SEOCache.AGGREGATE_EVENTS, tenant=None, defaults={"data": agg_events_data})
    set_memcached_l1(SEOCache.AGGREGATE_EVENTS, None, agg_events_data)

    # AGGREGATE_POINTS : concat des points de tous les fragments
    aggregate_points = []
    for data in points_frags.values():
        aggregate_points.extend(data.get("points", []))
    agg_points_data = {"points": aggregate_points}
    SEOCache.objects.update_or_create(
        cache_type=SEOCache.AGGREGATE_POINTS, tenant=None, defaults={"data": agg_points_data})
    set_memcached_l1(SEOCache.AGGREGATE_POINTS, None, agg_points_data)

    # AGGREGATE_LIEUX + SITEMAP_INDEX : filtre "lieu vivant" sur les summaries
    lieux, sitemap_tenants = [], []
    for config in summaries.values():
        domaine = config.get("domain")
        vivant = bool(domaine) and ((config.get("event_count", 0) > 0) or (config.get("product_count", 0) > 0))
        if not vivant:
            continue
        tenant_uuid = config.get("tenant_id")
        lieux.append({
            "tenant_id": tenant_uuid,
            "name": config.get("organisation") or config.get("name", ""),
            "domain": domaine,
            "slug": config.get("slug", ""),
            "short_description": config.get("short_description", ""),
            "locality": config.get("locality", ""),
            "country": config.get("country", ""),
            "logo_url": config.get("logo_url"),
            "image_url": config.get("social_card_url"),
            "categorie": config.get("categorie", ""),
            "latitude": config.get("latitude"),
            "longitude": config.get("longitude"),
            "event_count": config.get("event_count", 0),
            "product_count": config.get("product_count", 0),
        })
        sitemap_tenants.append({
            "tenant_id": tenant_uuid, "domain": domaine,
            "name": config.get("organisation") or config.get("name", ""),
        })
    agg_lieux_data = {"lieux": lieux}
    SEOCache.objects.update_or_create(
        cache_type=SEOCache.AGGREGATE_LIEUX, tenant=None, defaults={"data": agg_lieux_data})
    set_memcached_l1(SEOCache.AGGREGATE_LIEUX, None, agg_lieux_data)

    sitemap_data = {"tenants": sitemap_tenants}
    SEOCache.objects.update_or_create(
        cache_type=SEOCache.SITEMAP_INDEX, tenant=None, defaults={"data": sitemap_data})
    set_memcached_l1(SEOCache.SITEMAP_INDEX, None, sitemap_data)

    return {"events": len(aggregate_events), "points": len(aggregate_points), "lieux": len(lieux)}
```
> ⚠️ **`config["tenant_id"]`** : `build_tenant_config_data` met déjà `tenant_id = str(client.uuid)`
> dans le dict (vérifié). On l'utilise plutôt que `c.tenant_id` (FK) pour rester sur l'UUID
> string déjà présent partout dans les agrégats.
- [ ] **4.2** `manage.py check` → 0 issue.
- [ ] **4.3** → le mainteneur committe.

---

### Task 5 : `refresh_seo_cache()` réécrit en orchestrateur (tasks.py)

**Files :** Modify `seo/tasks.py` (remplacer le corps de `refresh_seo_cache`)

Le beat 4 h : boucle `refresh_tenant_seo_cache` sur tous les tenants actifs +
`rebuild_seo_aggregates()` + recalcul `FEDERATION_INCOMING` (cross-schema, ici seulement) +
nettoyage stale. **Conserver tel quel** le bloc `FEDERATION_INCOMING` (étape 5.bis actuelle)
et le nettoyage stale.

- [ ] **5.1** Remplacer le corps :
```python
@shared_task(name="seo.tasks.refresh_seo_cache")
def refresh_seo_cache():
    """
    Beat 4h : recalcul integral. Boucle refresh_tenant_seo_cache(tous) + rebuild agregats
    + FEDERATION_INCOMING (cross-schema) + nettoyage stale. Filet anti-derive.
    / Full 4h rebuild: per-tenant fragments + aggregates + incoming edges + stale cleanup.
    """
    from django.db import connection as _conn
    excluded = [Client.ROOT, Client.WAITING_CONFIG]
    tenants = list(Client.objects.exclude(categorie__in=excluded))
    tenant_id_list = [str(t.uuid) for t in tenants]

    for t in tenants:
        refresh_tenant_seo_cache(str(t.uuid))   # appel direct (pas .delay) dans le beat

    rebuild_seo_aggregates()

    # FEDERATION_INCOMING : arretes entrantes (depend des FederatedPlace, cross-schema).
    # [REPRENDRE le bloc existant "Etape 5.bis" : construction edge_sql UNION ALL,
    #  incoming_by_tenant, update_or_create FEDERATION_INCOMING, set_memcached_l1]

    # Nettoyage stale : [REPRENDRE le bloc existant]
    stale_count = (SEOCache.objects.exclude(tenant__isnull=True)
                   .exclude(tenant__uuid__in=tenant_id_list).delete()[0])
    logger.info("Fin refresh_seo_cache : %d tenants", len(tenants))
    return {"tenants": len(tenants)}
```
> **À l'exécution** : copier fidèlement le bloc `FEDERATION_INCOMING` (l. ~332-391 actuelles)
> et le bloc nettoyage stale depuis l'ancienne version, sans les réécrire de mémoire.
- [ ] **5.2** `manage.py check` → 0 issue.
- [ ] **5.3** **Équivalence** : `refresh_seo_cache()` puis comparer les compteurs aux valeurs
  d'avant refactor (6 tenants / 20 events / 5 lieux / 4 points sur la dev DB).
- [ ] **5.4** → le mainteneur committe.

---

### Task 6 : signal débouncé ciblé tenant (signals.py)

**Files :** Modify `BaseBillet/signals.py` (remplacer `declencher_refresh_seo_cache`)

- [ ] **6.1** Remplacer le corps du receiver :
```python
@receiver(post_save, sender=Event)
@receiver(post_delete, sender=Event)
@receiver(post_save, sender=PostalAddress)
@receiver(post_delete, sender=PostalAddress)
def declencher_refresh_seo_cache(sender, instance, **kwargs):
    """
    Modif event/adresse -> recalcul du fragment SEO du tenant courant (Celery, debounce par
    tenant) + recomposition des agregats (Celery, debounce global). Jamais de recalcul des
    autres schemas. / Targeted per-tenant fragment refresh + global aggregate rebuild, debounced.
    """
    from django.core.cache import cache
    from django.db import connection
    from seo.tasks import refresh_tenant_seo_cache, rebuild_seo_aggregates

    tenant = getattr(connection, "tenant", None)
    tenant_uuid = str(getattr(tenant, "uuid", "")) if tenant else ""
    if not tenant_uuid:
        return

    # Debounce PAR TENANT : 1 refresh fragment / 60s / tenant.
    if cache.add(f"seo_refresh_tenant_{tenant_uuid}", "1", 60):
        refresh_tenant_seo_cache.apply_async(args=[tenant_uuid], countdown=30)

    # Debounce GLOBAL : 1 rebuild agregats / 180s (borne la charge a 500 tenants).
    if cache.add("seo_rebuild_aggregates", "1", 180):
        rebuild_seo_aggregates.apply_async(countdown=180)
```
> Le `countdown` fragment (30 s) < `countdown` rebuild (180 s) → le fragment est à jour quand
> le rebuild recombine.
- [ ] **6.2** `manage.py check` → 0 issue.
- [ ] **6.3** → le mainteneur committe.

---

### Task 7 : tests pytch

**Files :** Create `tests/pytest/test_seo_cache_fragments.py`

- [ ] **7.1** Écrire (réutilise la dev DB, schema lespass) :
```python
"""
Tests du cache SEO en fragments (CHANTIER-07).
/ Tests for the per-tenant SEO cache fragments.
LOCALISATION : tests/pytest/test_seo_cache_fragments.py
"""
import pytest
from Customers.models import Client


@pytest.fixture(scope="session")
def django_db_setup():
    pass


@pytest.fixture(autouse=True, scope="session")
def _enable_db_access(django_db_blocker):
    django_db_blocker.unblock()


@pytest.mark.django_db
def test_refresh_tenant_ecrit_les_3_fragments_du_tenant_seulement():
    from seo.tasks import refresh_tenant_seo_cache
    from seo.models import SEOCache
    lespass = Client.objects.get(schema_name="lespass")
    r = refresh_tenant_seo_cache(str(lespass.uuid))
    assert r["tenant"] == str(lespass.uuid)
    for ct in (SEOCache.TENANT_SUMMARY, SEOCache.TENANT_EVENTS, SEOCache.TENANT_POINTS):
        assert SEOCache.objects.filter(cache_type=ct, tenant=lespass).exists()


@pytest.mark.django_db
def test_rebuild_aggregate_points_est_concat_des_fragments():
    from seo.tasks import refresh_seo_cache, rebuild_seo_aggregates
    from seo.models import SEOCache
    refresh_seo_cache()  # peuple tous les fragments + agregats
    rebuild_seo_aggregates()
    frag_total = 0
    for c in SEOCache.objects.filter(cache_type=SEOCache.TENANT_POINTS):
        frag_total += len(c.data.get("points", []))
    agg = SEOCache.objects.get(cache_type=SEOCache.AGGREGATE_POINTS, tenant=None)
    assert len(agg.data.get("points", [])) == frag_total


@pytest.mark.django_db
def test_pa_id_uniques_dans_agregat():
    from seo.tasks import refresh_seo_cache
    from seo.models import SEOCache
    refresh_seo_cache()
    agg = SEOCache.objects.get(cache_type=SEOCache.AGGREGATE_POINTS, tenant=None)
    pa_ids = [p["pa_id"] for p in agg.data.get("points", [])]
    assert len(pa_ids) == len(set(pa_ids))  # zero collision cross-tenant
```
- [ ] **7.2** Lancer (avec `API_KEY` injecté, cf. en-tête) → 3 PASS.
- [ ] **7.3** Lancer la non-régression SEO :
  `pytest tests/pytest/test_seo_aggregate_points.py tests/pytest/test_seo_event_tags.py tests/pytest/test_federation_config.py tests/pytest/test_federation_view_integration.py -q`
- [ ] **7.4** → le mainteneur committe.

---

### Task 8 : Documentation

- [ ] **8.1** `CHANGELOG.md` : entrée « Cache SEO en fragments par tenant ».
- [ ] **8.2** `A TESTER et DOCUMENTER/seo-cache-fragments.md` : scénarios (refresh ciblé,
  rebuild, débounce, équivalence beat).
- [ ] **8.3** → le mainteneur committe.

---

## Self-review (couverture spec → plan)

| Exigence (CHANTIER-07 §) | Tâche |
|---|---|
| `TENANT_POINTS` (§5) | Task 1 |
| `refresh_tenant_seo_cache` (§3) | Task 3 (+ Task 2 pour counts 1-tenant) |
| `rebuild_seo_aggregates` recombinaison (§3) | Task 4 |
| Orchestrateur beat + FEDERATION_INCOMING au beat (§3) | Task 5 |
| Signal débouncé tenant + global (§4) | Task 6 |
| Vues inchangées / équivalence (§7) | Task 5.3, Task 7 |
| Tests (§8) | Task 7 |

Pas de placeholder de logique (les blocs « REPRENDRE » réfèrent à du code existant à copier
fidèlement à l'exécution, pas à inventer). Signatures cohérentes :
`refresh_tenant_seo_cache(tenant_id)`, `rebuild_seo_aggregates()`, `get_counts_for_tenant(schema_name)`.
