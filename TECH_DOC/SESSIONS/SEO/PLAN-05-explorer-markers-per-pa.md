# PLAN-05 — Carte explorer ROOT : 1 marker par PostalAddress

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommande) ou `superpowers:executing-plans` pour executer ce plan task-by-task. Steps utilisent `- [ ]` syntax.

**Goal :** Afficher 1 marker par `PostalAddress` active sur `/explorer/` au lieu d'1 marker par tenant, avec popup riche listant les events futurs lies.

**Architecture :** Nouveau cache `SEOCache.AGGREGATE_POINTS` dedie (1 entree par PA active). Construit par `refresh_seo_cache` en parallele de `AGGREGATE_LIEUX` (qui reste intact pour ne pas casser les autres vues). Lu uniquement par `/explorer/`.

**Tech Stack :** Django + django-tenants + Leaflet 1.9.4 + MarkerCluster + JSON-LD.

**Reference spec :** `CHANTIER-05-explorer-markers-per-pa.md` (meme dossier).

**Convention commits :** style projet (`feat:`, `fix:`, `refactor:`, etc.). **AUCUN `Co-Authored-By: Claude`** (regle ULTRA IMPORTANT). Tous les commits du plan sont realises par le **mainteneur**, pas par le subagent.

---

## File Structure

| Fichier | Type | Responsabilite |
|---|---|---|
| `seo/models.py` | edit | +constante `SEOCache.AGGREGATE_POINTS` |
| `seo/services.py` | edit | +`get_postal_addresses_for_tenants()`, +`build_aggregate_points()`, refacto `build_explorer_data_for_tenants()` |
| `seo/tasks.py` | edit | +Etape 6 dans `refresh_seo_cache` (ecriture AGGREGATE_POINTS) |
| `seo/views.py` | edit | `explorer()` passe `points` au template |
| `seo/templates/seo/explorer.html` | edit | JSON-LD ItemList itere sur `points` |
| `seo/static/seo/explorer.js` | edit | Boucle sur `points`, popup riche |
| `seo/static/seo/explorer.css` | edit | Styles popup (logo miniature, liste events) |
| `tests/pytest/test_seo_aggregate_points.py` | create | Tests unitaires DB-only |
| `tests/e2e/test_explorer_markers_per_pa.py` | create | 2 tests Playwright |
| `CHANGELOG.md` | edit | Entry section "Carte explorer" |
| `A TESTER et DOCUMENTER/explorer-markers-per-pa.md` | create | Scenarios test manuel |

---

## Task 1: Constante cache `AGGREGATE_POINTS`

**Files:**
- Modify: `seo/models.py`

- [ ] **Step 1: Lire `seo/models.py` lignes ~20-40 pour reperer `CACHE_TYPE_CHOICES`**

Verifier la classe `SEOCache` et l'enum existante. Cible attendue (l'edit insere apres `AGGREGATE_LIEUX`).

- [ ] **Step 2: Ajouter la constante**

Dans `seo/models.py`, classe `SEOCache`, apres la ligne `AGGREGATE_LIEUX = "aggregate_lieux"` :

```python
    AGGREGATE_POINTS = "aggregate_points"
```

Et dans `CACHE_TYPE_CHOICES`, apres la ligne `(AGGREGATE_LIEUX, _("Aggregated active venues (ROOT)"))` :

```python
        (AGGREGATE_POINTS, _("Aggregated PostalAddress points for explorer map (ROOT)")),
```

- [ ] **Step 3: Verifier**

```bash
docker exec lespass_django poetry run python manage.py check
```
Expected : `System check identified no issues (0 silenced).`

- [ ] **Step 4: Commit (par mainteneur)**

```bash
git add seo/models.py
git commit -m "feat(seo): add AGGREGATE_POINTS cache type for per-PA markers"
```

---

## Task 2: Helper `get_postal_addresses_for_tenants` + tests

**Files:**
- Modify: `seo/services.py`
- Create: `tests/pytest/test_seo_aggregate_points.py`

- [ ] **Step 1: Ecrire le test (FAIL attendu)**

Creer `tests/pytest/test_seo_aggregate_points.py` :

```python
"""
Tests unitaires pour les helpers AGGREGATE_POINTS (seo/services.py)
/ Unit tests for the AGGREGATE_POINTS helpers.

LOCALISATION : tests/pytest/test_seo_aggregate_points.py
Voir SESSIONS/SEO/CHANTIER-05-explorer-markers-per-pa.md pour la spec.
"""

from decimal import Decimal

import pytest
from django_tenants.utils import tenant_context

from Customers.models import Client


@pytest.mark.django_db
def test_get_postal_addresses_for_tenants_renvoie_pa_avec_coords_seulement():
    """
    Une PA sans coords ne doit pas remonter. Une PA avec lat/lng remonte.
    / PA without coords doesn't show up. PA with lat/lng does.
    """
    from seo.services import get_postal_addresses_for_tenants
    from BaseBillet.models import PostalAddress

    tenant = Client.objects.exclude(schema_name="public").first()
    with tenant_context(tenant):
        pa_sans_coords = PostalAddress.objects.create(name="Sans coords")
        pa_avec_coords = PostalAddress.objects.create(
            name="Avec coords",
            latitude=Decimal("48.8566"),
            longitude=Decimal("2.3522"),
        )

    resultat = get_postal_addresses_for_tenants([(str(tenant.uuid), tenant.schema_name)])
    pa_ids = [pa["pa_id"] for pa in resultat.get(str(tenant.uuid), [])]
    assert pa_avec_coords.pk in pa_ids
    assert pa_sans_coords.pk not in pa_ids
```

- [ ] **Step 2: Lancer le test (verifier FAIL)**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_seo_aggregate_points.py::test_get_postal_addresses_for_tenants_renvoie_pa_avec_coords_seulement -v
```
Expected : `ImportError: cannot import name 'get_postal_addresses_for_tenants'`

- [ ] **Step 3: Implementer le helper**

Dans `seo/services.py`, apres `build_tenant_config_data` (~ligne 350) :

```python
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
```

- [ ] **Step 4: Lancer le test (verifier PASS)**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_seo_aggregate_points.py::test_get_postal_addresses_for_tenants_renvoie_pa_avec_coords_seulement -v
```
Expected : `PASSED`

- [ ] **Step 5: Commit (par mainteneur)**

```bash
git add seo/services.py tests/pytest/test_seo_aggregate_points.py
git commit -m "feat(seo): add get_postal_addresses_for_tenants helper with test"
```

---

## Task 3: Helper `build_aggregate_points` + tests

**Files:**
- Modify: `seo/services.py`
- Modify: `tests/pytest/test_seo_aggregate_points.py`

- [ ] **Step 1: Ecrire 3 tests (FAIL attendu)**

Ajouter dans `tests/pytest/test_seo_aggregate_points.py` :

```python
from decimal import Decimal
from django.utils import timezone


@pytest.mark.django_db
def test_build_aggregate_points_inclut_pa_avec_event_futur():
    """
    Une PA avec 1 event futur => le point apparait, events_futurs contient l'event.
    """
    from seo.services import build_aggregate_points
    from BaseBillet.models import PostalAddress, Event

    tenant = Client.objects.exclude(schema_name="public").first()
    tenant_uuid = str(tenant.uuid)
    schema = tenant.schema_name

    with tenant_context(tenant):
        pa = PostalAddress.objects.create(
            name="Lieu test", street_address="1 rue X",
            address_locality="Paris",
            latitude=Decimal("48.85"), longitude=Decimal("2.35"),
        )
        event = Event.objects.create(
            name="Concert X",
            datetime=timezone.now() + timezone.timedelta(days=7),
            postal_address=pa,
            published=True,
        )

    configs_by_tenant = {tenant_uuid: {"organisation": tenant.name, "domain": "test.local", "logo_url": None}}
    events_by_tenant = {tenant_uuid: [{"uuid": str(event.uuid), "name": event.name,
                                       "datetime_iso": event.datetime.isoformat(),
                                       "postal_address_id": pa.pk, "slug": "concert-x"}]}

    result = build_aggregate_points(
        [(tenant_uuid, schema)], configs_by_tenant, events_by_tenant
    )
    points = result["points"]
    assert len(points) == 1
    assert points[0]["pa_id"] == pa.pk
    assert len(points[0]["events_futurs"]) == 1
    assert points[0]["events_futurs"][0]["name"] == "Concert X"


@pytest.mark.django_db
def test_build_aggregate_points_limite_a_5_avec_count_total():
    """
    PA avec 12 events futurs => events_futurs == 5, events_futurs_count_total == 12.
    """
    from seo.services import build_aggregate_points
    from BaseBillet.models import PostalAddress

    tenant = Client.objects.exclude(schema_name="public").first()
    tenant_uuid = str(tenant.uuid)
    schema = tenant.schema_name

    with tenant_context(tenant):
        pa = PostalAddress.objects.create(
            name="PA Active",
            latitude=Decimal("48.85"), longitude=Decimal("2.35"),
        )

    configs_by_tenant = {tenant_uuid: {"organisation": tenant.name, "domain": "test.local", "logo_url": None}}
    fake_events = [
        {"uuid": f"e{i}", "name": f"Event {i}",
         "datetime_iso": (timezone.now() + timezone.timedelta(days=i)).isoformat(),
         "postal_address_id": pa.pk, "slug": f"event-{i}"}
        for i in range(1, 13)
    ]
    events_by_tenant = {tenant_uuid: fake_events}

    result = build_aggregate_points(
        [(tenant_uuid, schema)], configs_by_tenant, events_by_tenant
    )
    point = result["points"][0]
    assert len(point["events_futurs"]) == 5
    assert point["events_futurs_count_total"] == 12


@pytest.mark.django_db
def test_build_aggregate_points_exclut_tenants_morts():
    """
    Un tenant sans event futur ni produit publie n'a pas son tenant_uuid dans
    `configs_by_tenant_actifs` -> il est skip.
    """
    from seo.services import build_aggregate_points
    from BaseBillet.models import PostalAddress

    tenant = Client.objects.exclude(schema_name="public").first()
    tenant_uuid = str(tenant.uuid)
    schema = tenant.schema_name
    with tenant_context(tenant):
        PostalAddress.objects.create(
            name="PA mort", latitude=Decimal("48.85"), longitude=Decimal("2.35"),
        )

    # Tenant pas dans configs_by_tenant (= considere comme mort par l'appelant)
    result = build_aggregate_points([(tenant_uuid, schema)], {}, {})
    assert result["points"] == []
```

- [ ] **Step 2: Lancer les tests (verifier FAIL)**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_seo_aggregate_points.py -v -k build_aggregate_points
```
Expected : 3 tests FAIL avec `ImportError`

- [ ] **Step 3: Implementer `build_aggregate_points`**

Dans `seo/services.py`, apres `get_postal_addresses_for_tenants` :

```python
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

    # Recupere toutes les PA actives par tenant (1 dict par tenant_uuid)
    # / Get all active PAs per tenant
    tenants_vivants = [
        (uuid, schema) for uuid, schema in tenant_schemas if uuid in configs_by_tenant
    ]
    pa_par_tenant = get_postal_addresses_for_tenants(tenants_vivants)

    points = []
    for tenant_uuid, _schema in tenants_vivants:
        config = configs_by_tenant.get(tenant_uuid, {})
        pa_list = pa_par_tenant.get(tenant_uuid, [])
        events_du_tenant = events_by_tenant.get(tenant_uuid, [])

        # Index events par pa_id (1 event peut etre sur 1 seule PA)
        # / Index events by pa_id
        events_par_pa = {}
        for event in events_du_tenant:
            pa_id = event.get("postal_address_id")
            if pa_id is None:
                continue
            events_par_pa.setdefault(pa_id, []).append(event)

        # Pour chaque PA, on enrichit avec les events lies
        # / For each PA, enrich with linked events
        main_address_id = config.get("postal_address_id")
        for pa in pa_list:
            events_lies = events_par_pa.get(pa["pa_id"], [])
            events_tries = sorted(events_lies, key=lambda e: e["datetime_iso"])

            address_morceaux = [pa["street_address"], pa["postal_code"], pa["address_locality"]]
            address_morceaux_nettoyes = [m for m in address_morceaux if m]
            address_display = ", ".join(address_morceaux_nettoyes)

            points.append({
                "pa_id": pa["pa_id"],
                "latitude": pa["latitude"],
                "longitude": pa["longitude"],
                "pa_name": pa["name"] or pa["street_address"] or pa["address_locality"] or config.get("organisation", ""),
                "address_display": address_display,
                "is_main_address": (pa["pa_id"] == main_address_id),
                "tenant_id": tenant_uuid,
                "tenant_organisation": config.get("organisation", ""),
                "tenant_domain": config.get("domain", ""),
                "tenant_logo_url": config.get("logo_url"),
                "events_futurs": events_tries[:LIMIT_EVENTS_DANS_POPUP],
                "events_futurs_count_total": len(events_tries),
            })

    return {"points": points}
```

**Important** : il faut aussi ajouter `postal_address_id` aux dicts events fournis par `events_by_tenant`. Verifier que `seo/services.py:get_events_for_tenants` retourne bien ce champ. Si non, l'ajouter dans la SQL UNION ALL.

- [ ] **Step 4: Verifier `get_events_for_tenants` retourne postal_address_id**

```bash
docker exec lespass_django grep -n "postal_address_id\|event.postal_address" seo/services.py | head -10
```

Si absent, **ajouter `pa.postal_address_id` dans le SELECT** de `get_events_for_tenants` (ligne ~150 selon code actuel).

- [ ] **Step 5: Ajouter `postal_address_id` dans config_by_tenant**

Dans `seo/services.py:build_tenant_config_data` (~ligne 330), apres `data["country"] = config.postal_address.address_country or ""` :

```python
            # ID de la PostalAddress principale pour le flag is_main_address
            # / Main PostalAddress ID for the is_main_address flag
            data["postal_address_id"] = config.postal_address_id
```

- [ ] **Step 6: Lancer les tests (verifier PASS)**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_seo_aggregate_points.py -v -k build_aggregate_points
```
Expected : 3 PASSED

- [ ] **Step 7: Commit (par mainteneur)**

```bash
git add seo/services.py tests/pytest/test_seo_aggregate_points.py
git commit -m "feat(seo): add build_aggregate_points + per-PA event grouping"
```

---

## Task 4: Refacto `build_explorer_data_for_tenants`

**Files:**
- Modify: `seo/services.py`
- Modify: `tests/pytest/test_seo_aggregate_points.py`

- [ ] **Step 1: Ecrire le test (FAIL attendu)**

Ajouter dans `tests/pytest/test_seo_aggregate_points.py` :

```python
@pytest.mark.django_db
def test_build_explorer_data_for_tenants_filtre_par_uuid():
    """
    Le filtre par tenant_uuid ne renvoie que les points des tenants demandes.
    """
    from seo.services import build_explorer_data_for_tenants
    from seo.models import SEOCache

    # Seed le cache avec 3 points (2 tenants distincts)
    fake_cache = {"points": [
        {"pa_id": 1, "tenant_id": "uuid-A", "pa_name": "PA1", "latitude": 1.0, "longitude": 1.0,
         "address_display": "", "tenant_organisation": "A", "tenant_domain": "a.test",
         "tenant_logo_url": None, "is_main_address": True,
         "events_futurs": [], "events_futurs_count_total": 0},
        {"pa_id": 2, "tenant_id": "uuid-A", "pa_name": "PA2", "latitude": 2.0, "longitude": 2.0,
         "address_display": "", "tenant_organisation": "A", "tenant_domain": "a.test",
         "tenant_logo_url": None, "is_main_address": False,
         "events_futurs": [], "events_futurs_count_total": 0},
        {"pa_id": 3, "tenant_id": "uuid-B", "pa_name": "PA3", "latitude": 3.0, "longitude": 3.0,
         "address_display": "", "tenant_organisation": "B", "tenant_domain": "b.test",
         "tenant_logo_url": None, "is_main_address": True,
         "events_futurs": [], "events_futurs_count_total": 0},
    ]}
    SEOCache.objects.update_or_create(
        cache_type=SEOCache.AGGREGATE_POINTS, tenant=None, defaults={"data": fake_cache},
    )

    # Filtre uuid-A
    result = build_explorer_data_for_tenants(["uuid-A"])
    assert len(result["points"]) == 2
    assert {p["pa_id"] for p in result["points"]} == {1, 2}
```

- [ ] **Step 2: Lancer le test (verifier FAIL)**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_seo_aggregate_points.py::test_build_explorer_data_for_tenants_filtre_par_uuid -v
```
Expected : FAIL (la fonction renvoie encore `lieux`/`events`, pas `points`)

- [ ] **Step 3: Refacto `build_explorer_data_for_tenants` (lignes 363-426 de `seo/services.py`)**

Remplacer **entierement** la fonction par :

```python
def build_explorer_data_for_tenants(tenant_uuids):
    """
    Renvoie la liste des points geo pour la page explorer ROOT.
    Filtre par tenant_uuids fourni.
    / Returns the geo points list for the explorer ROOT page,
    filtered by provided tenant_uuids.

    Parametres / Parameters:
        tenant_uuids: list[str] — UUIDs des tenants a inclure.

    Retourne / Returns: {"points": [...]}
    """
    from seo.models import SEOCache
    from seo.views_common import get_seo_cache

    if not tenant_uuids:
        return {"points": []}

    uuids_set = set(tenant_uuids)
    points_data = get_seo_cache(SEOCache.AGGREGATE_POINTS) or {}
    raw_points = points_data.get("points", [])
    points_filtres = [p for p in raw_points if p.get("tenant_id") in uuids_set]
    return {"points": points_filtres}
```

Egalement adapter `build_explorer_data()` (juste apres) :

```python
def build_explorer_data():
    """
    Compat retro : appelle build_explorer_data_for_tenants() avec tous
    les tenant_ids presents dans AGGREGATE_POINTS.
    """
    from seo.models import SEOCache
    from seo.views_common import get_seo_cache

    points_data = get_seo_cache(SEOCache.AGGREGATE_POINTS) or {}
    raw_points = points_data.get("points", [])
    tenant_uuids = list({p.get("tenant_id") for p in raw_points if p.get("tenant_id")})
    return build_explorer_data_for_tenants(tenant_uuids)
```

- [ ] **Step 4: Lancer tous les tests pytest seo**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_seo_aggregate_points.py tests/pytest/test_seo_indexing.py -v
```
Expected : tous PASS

- [ ] **Step 5: Commit (par mainteneur)**

```bash
git add seo/services.py tests/pytest/test_seo_aggregate_points.py
git commit -m "refactor(seo): build_explorer_data reads AGGREGATE_POINTS"
```

---

## Task 5: Integration dans `refresh_seo_cache`

**Files:**
- Modify: `seo/tasks.py`
- Modify: `tests/pytest/test_seo_aggregate_points.py`

- [ ] **Step 1: Ecrire test smoke (FAIL attendu)**

Ajouter dans `tests/pytest/test_seo_aggregate_points.py` :

```python
@pytest.mark.django_db
def test_refresh_seo_cache_ecrit_aggregate_points():
    """
    Apres refresh, le cache AGGREGATE_POINTS existe en base.
    Test smoke (pas de verif contenu, juste presence).
    """
    from seo.tasks import refresh_seo_cache
    from seo.models import SEOCache

    SEOCache.objects.filter(cache_type=SEOCache.AGGREGATE_POINTS).delete()
    refresh_seo_cache()
    assert SEOCache.objects.filter(
        cache_type=SEOCache.AGGREGATE_POINTS, tenant=None
    ).exists()
```

- [ ] **Step 2: Lancer le test (FAIL attendu)**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_seo_aggregate_points.py::test_refresh_seo_cache_ecrit_aggregate_points -v
```
Expected : FAIL (cache non ecrit)

- [ ] **Step 3: Ajouter Etape 6 dans `refresh_seo_cache`**

Dans `seo/tasks.py:refresh_seo_cache`, **apres** l'ecriture `AGGREGATE_LIEUX` (~ligne 239) :

```python
    # ------------------------------------------------------------------
    # Etape 6 : AGGREGATE_POINTS (1 entree par PA active)
    # Construit la liste des points geo (1 par PostalAddress avec coords,
    # pour chaque tenant vivant) avec les events futurs lies.
    # / Step 6: AGGREGATE_POINTS (1 entry per active PA)
    # ------------------------------------------------------------------
    from seo.services import build_aggregate_points

    # Seuls les tenants vivants nous interessent (meme filtre que AGGREGATE_LIEUX)
    # / Only alive tenants (same filter as AGGREGATE_LIEUX)
    tenants_vivants_schemas = [
        (tenant_id, schema)
        for tenant_id, schema in tenant_schemas
        if (
            counts_by_tenant.get(tenant_id, {}).get("event_count", 0) > 0
            or counts_by_tenant.get(tenant_id, {}).get("product_count", 0) > 0
        )
    ]
    configs_vivants = {
        tid: configs_by_tenant[tid] for tid, _s in tenants_vivants_schemas
        if tid in configs_by_tenant
    }
    events_vivants = {
        tid: events_by_tenant.get(tid, []) for tid, _s in tenants_vivants_schemas
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
```

- [ ] **Step 4: Lancer le test (PASS attendu)**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_seo_aggregate_points.py::test_refresh_seo_cache_ecrit_aggregate_points -v
```
Expected : PASS

- [ ] **Step 5: Test smoke complet sur le projet**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_seo_aggregate_points.py tests/pytest/test_seo_indexing.py -v
```
Expected : tous PASS

- [ ] **Step 6: Commit (par mainteneur)**

```bash
git add seo/tasks.py tests/pytest/test_seo_aggregate_points.py
git commit -m "feat(seo): write AGGREGATE_POINTS cache in refresh_seo_cache"
```

---

## Task 6: Vue Django `explorer`

**Files:**
- Modify: `seo/views.py`

- [ ] **Step 1: Lire la fonction `explorer` (lignes 304-361 de `seo/views.py`)**

```bash
docker exec lespass_django sed -n '304,365p' seo/views.py
```

Reperer comment `explorer_data` est passe au template.

- [ ] **Step 2: Adapter la vue**

Dans `seo/views.py`, fonction `explorer` :

- Remplacer `for lieu in explorer_data.get("lieux", []):` (ligne ~326) par `for point in explorer_data.get("points", []):`
- Adapter la construction du `item_list_elements` JSON-LD : 1 entree par point avec name=`point["pa_name"]`, geo=lat/lng du point, url=`https://{point["tenant_domain"]}`

```python
    # Construction du JSON-LD ItemList : 1 element par point geo
    # / Build JSON-LD ItemList: 1 element per geo point
    item_list_elements = []
    for index, point in enumerate(explorer_data.get("points", []), start=1):
        item_list_elements.append({
            "@type": "ListItem",
            "position": index,
            "item": {
                "@type": "Place",
                "name": point["pa_name"],
                "address": point["address_display"],
                "geo": {
                    "@type": "GeoCoordinates",
                    "latitude": point["latitude"],
                    "longitude": point["longitude"],
                },
                "url": f"https://{point['tenant_domain']}" if point.get("tenant_domain") else None,
            },
        })
```

- [ ] **Step 3: Verifier**

```bash
docker exec lespass_django poetry run python manage.py check
```
Expected : OK

- [ ] **Step 4: Commit (par mainteneur)**

```bash
git add seo/views.py
git commit -m "feat(seo): explorer view passes points (1 per PA) to template"
```

---

## Task 7: Template `explorer.html` (JSON-LD ItemList + data attribute)

**Files:**
- Modify: `seo/templates/seo/explorer.html`

- [ ] **Step 1: Lire le template courant pour reperer le JSON injecte au JS**

```bash
docker exec lespass_django grep -n "explorer-data\|lieux\|explorer_data" seo/templates/seo/explorer.html | head -10
```

- [ ] **Step 2: Mettre a jour le data attribute**

Dans `seo/templates/seo/explorer.html`, remplacer `data-explorer-data=` ou variable similaire pour qu'elle reflete la nouvelle structure `{"points": [...]}`. Le template utilise `{{ explorer_data|json_script:"explorer-data" }}` ou pattern similaire — pas besoin de modifier si `explorer_data` est dejà passe entierement.

Cherche les references a `explorer_data.lieux` ou `explorer_data.events` dans le template et les supprime ou les remplace par `explorer_data.points`.

- [ ] **Step 3: Verifier le rendu HTML**

Lancer la page localement et inspecter le DOM :

```bash
curl -s http://localhost:8002/explorer/ | grep -o 'data-explorer-data[^>]*' | head -1 | python3 -c "import sys, json, urllib.parse; print(json.dumps(json.loads(sys.stdin.read().split(chr(39))[1]), indent=2)[:500])"
```

Verifier que la structure JSON contient `points` et plus `lieux/events`.

- [ ] **Step 4: Commit (par mainteneur)**

```bash
git add seo/templates/seo/explorer.html
git commit -m "feat(seo): explorer.html injects points data for new markers logic"
```

---

## Task 8: JS `explorer.js` — boucle sur `points` + popup riche

**Files:**
- Modify: `seo/static/seo/explorer.js`

- [ ] **Step 1: Lire les sections concernees**

Reperer la fonction qui itere sur `state.points` (~ligne 508-540) et celle qui construit les markers.

```bash
sed -n '500,545p' seo/static/seo/explorer.js
```

- [ ] **Step 2: Remplacer la boucle des markers**

Remplacer le bloc actuel (~ligne 511-540) par :

```javascript
        state.points.forEach(point => {
            const lat = parseFloat(point.latitude);
            const lng = parseFloat(point.longitude);
            if (isNaN(lat) || isNaN(lng)) return;

            // Marker simple, tooltip au survol = nom de l'adresse
            // / Simple marker, hover tooltip = PA name
            const marker = L.marker([lat, lng], { title: point.pa_name });
            marker.bindPopup(construirePopupHtml(point), {
                maxWidth: 320,
                className: 'explorer-popup',
            });
            state.markerCluster.addLayer(marker);
        });
```

- [ ] **Step 3: Ajouter la fonction `construirePopupHtml`**

Avant la boucle des markers, ajouter :

```javascript
    function construirePopupHtml(point) {
        // Construit le HTML du popup riche : adresse + tenant + events futurs.
        // / Builds the rich popup HTML.

        const escape = (s) => (s || '').replace(/[&<>"]/g, (c) =>
            ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'})[c]);

        let html = `<div class="explorer-popup-content">`;

        // Nom adresse (en gras) + adresse formatee
        html += `<h6 class="explorer-popup-title">${escape(point.pa_name)}</h6>`;
        if (point.address_display) {
            html += `<p class="explorer-popup-address">${escape(point.address_display)}</p>`;
        }

        // Tenant + lien (avec logo si dispo)
        if (point.tenant_domain) {
            const logoImg = point.tenant_logo_url
                ? `<img src="${escape(point.tenant_logo_url)}" alt="" class="explorer-popup-logo">`
                : '';
            html += `<p class="explorer-popup-tenant">${logoImg}
                <a href="https://${escape(point.tenant_domain)}" target="_blank" rel="noopener">
                    ${escape(point.tenant_organisation)} ↗
                </a></p>`;
        }

        // Events futurs (top 5)
        if (point.events_futurs && point.events_futurs.length > 0) {
            const total = point.events_futurs_count_total || point.events_futurs.length;
            html += `<p class="explorer-popup-events-label">📅 Événements futurs (${total})</p>`;
            html += `<ul class="explorer-popup-events-list">`;
            point.events_futurs.forEach(ev => {
                const dateAffichee = new Date(ev.datetime_iso).toLocaleDateString('fr-FR', {
                    day: 'numeric', month: 'short',
                });
                const url = ev.url || (point.tenant_domain
                    ? `https://${point.tenant_domain}/event/${ev.slug || ev.uuid}/`
                    : '#');
                html += `<li><a href="${escape(url)}" target="_blank" rel="noopener">
                    ${escape(ev.name)} — ${escape(dateAffichee)}
                </a></li>`;
            });
            html += `</ul>`;
            if (total > point.events_futurs.length) {
                const restants = total - point.events_futurs.length;
                html += `<p class="explorer-popup-events-more">
                    + ${restants} autre${restants > 1 ? 's' : ''}
                </p>`;
            }
        }

        html += `</div>`;
        return html;
    }
```

- [ ] **Step 4: Adapter la lecture du JSON**

Reperer l'endroit ou `explorerData.lieux` est utilise (~ligne 408 et autour) et le remplacer par `explorerData.points`.

```javascript
// Avant
state.points = explorerData.lieux || [];
// Apres
state.points = explorerData.points || [];
```

Supprimer aussi toute reference a `lieu.events` (les events sont maintenant dans `point.events_futurs`).

- [ ] **Step 5: Test manuel local**

```bash
# Forcer un refresh du cache
docker exec lespass_django poetry run python manage.py shell -c "from seo.tasks import refresh_seo_cache; refresh_seo_cache()"
# Ouvrir http://localhost:8002/explorer/ et verifier dans Chrome:
# - markers visibles
# - clic = popup riche avec adresse + tenant + events
```

- [ ] **Step 6: Commit (par mainteneur)**

```bash
git add seo/static/seo/explorer.js
git commit -m "feat(seo): explorer.js builds 1 marker per PA with rich popup"
```

---

## Task 9: CSS popup riche

**Files:**
- Modify: `seo/static/seo/explorer.css`

- [ ] **Step 1: Ajouter les styles popup en fin de fichier**

```css
/* --- Popup riche par PA (CHANTIER-05) --- */
.explorer-popup .leaflet-popup-content {
    margin: 12px 14px;
    line-height: 1.4;
}
.explorer-popup-title {
    font-weight: 600;
    font-size: 0.95rem;
    margin: 0 0 4px;
}
.explorer-popup-address {
    color: #666;
    font-size: 0.85rem;
    margin: 0 0 8px;
}
.explorer-popup-tenant {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 0.85rem;
    margin: 0 0 10px;
    padding-top: 6px;
    border-top: 1px solid #eee;
}
.explorer-popup-logo {
    width: 20px;
    height: 20px;
    border-radius: 3px;
    object-fit: cover;
}
.explorer-popup-events-label {
    font-size: 0.85rem;
    font-weight: 500;
    margin: 8px 0 4px;
    color: #555;
}
.explorer-popup-events-list {
    list-style: none;
    padding: 0;
    margin: 0 0 4px;
    font-size: 0.82rem;
}
.explorer-popup-events-list li {
    padding: 2px 0;
}
.explorer-popup-events-list a {
    color: #2a5d9f;
    text-decoration: none;
}
.explorer-popup-events-list a:hover {
    text-decoration: underline;
}
.explorer-popup-events-more {
    color: #888;
    font-size: 0.78rem;
    font-style: italic;
    margin: 4px 0 0;
}
```

- [ ] **Step 2: Verifier visuellement**

Recharger `/explorer/` avec hard refresh (Ctrl+Shift+R) et cliquer sur un marker.

- [ ] **Step 3: Commit (par mainteneur)**

```bash
git add seo/static/seo/explorer.css
git commit -m "feat(seo): style rich popup for per-PA markers"
```

---

## Task 10: Test E2E Playwright

**Files:**
- Create: `tests/e2e/test_explorer_markers_per_pa.py`

- [ ] **Step 1: Verifier la structure des tests E2E existants**

```bash
ls tests/e2e/ | head -5
head -40 tests/e2e/conftest.py
```

- [ ] **Step 2: Creer le test E2E**

```python
"""
Tests E2E Playwright : carte explorer ROOT avec 1 marker par PA.
/ E2E Playwright tests: ROOT explorer map with 1 marker per PA.

LOCALISATION : tests/e2e/test_explorer_markers_per_pa.py
Voir SESSIONS/SEO/CHANTIER-05-explorer-markers-per-pa.md.
"""

import pytest
from playwright.sync_api import expect


@pytest.mark.e2e
def test_explorer_affiche_markers_pour_pa_actives(page, live_server):
    """
    La carte explorer affiche des markers cluster pour les PA actives.
    Verifie qu'il y a au moins 1 marker apres chargement.
    / Explorer map shows cluster markers for active PAs.
    """
    # Force un refresh du cache avant le test
    from seo.tasks import refresh_seo_cache
    refresh_seo_cache()

    page.goto(f"{live_server.url}/explorer/")
    # Attendre que Leaflet ait fini d'initialiser
    page.wait_for_selector(".leaflet-marker-cluster, .leaflet-marker-icon", timeout=5000)

    # Au moins un cluster ou marker visible
    markers_visibles = page.locator(".leaflet-marker-cluster, .leaflet-marker-icon").count()
    assert markers_visibles >= 1, f"Aucun marker sur la carte (count={markers_visibles})"


@pytest.mark.e2e
def test_explorer_popup_contient_adresse_et_tenant(page, live_server):
    """
    Clic sur un marker -> popup avec nom PA + nom tenant.
    """
    from seo.tasks import refresh_seo_cache
    refresh_seo_cache()

    page.goto(f"{live_server.url}/explorer/")
    page.wait_for_selector(".leaflet-marker-icon", timeout=5000)

    # Zoomer au max pour eclater les clusters et avoir un vrai marker
    for _ in range(10):
        page.click(".leaflet-control-zoom-in")
        page.wait_for_timeout(100)

    page.click(".leaflet-marker-icon")
    page.wait_for_selector(".explorer-popup-content", timeout=3000)

    # Verifier presence du titre et au moins un element tenant ou adresse
    popup_html = page.inner_html(".explorer-popup-content")
    assert "explorer-popup-title" in popup_html
    assert "explorer-popup-tenant" in popup_html or "explorer-popup-address" in popup_html
```

- [ ] **Step 3: Lancer les tests E2E**

```bash
docker exec lespass_django poetry run pytest tests/e2e/test_explorer_markers_per_pa.py -v -s
```
Expected : 2 PASS

- [ ] **Step 4: Commit (par mainteneur)**

```bash
git add tests/e2e/test_explorer_markers_per_pa.py
git commit -m "test(seo): E2E tests for per-PA markers on explorer map"
```

---

## Task 11: CHANGELOG + doc test manuel

**Files:**
- Modify: `CHANGELOG.md`
- Create: `A TESTER et DOCUMENTER/explorer-markers-per-pa.md`

- [ ] **Step 1: Ajouter section CHANGELOG**

En tete de `CHANGELOG.md` (apres l'entree precedente la plus recente) :

```markdown
## N. Carte explorer ROOT : 1 marker par PostalAddress / 1 marker per PostalAddress

**Quoi / What:** Refonte du cache `AGGREGATE_POINTS` qui produit 1 entree par PA active (au lieu de 1 par tenant). La page `/explorer/` affiche maintenant 1 marker par adresse precise avec popup riche (nom PA, tenant, events futurs limites a top 5).

**Pourquoi / Why:** Suite a l'import de 327 PA geolocalisees, les tenants comme Universite Populaire Villeurbanne (24 adresses differentes) etaient invisibles. La carte ROOT devient une vraie cartographie des lieux du reseau, pas juste des sieges sociaux.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `seo/models.py` | +constante `SEOCache.AGGREGATE_POINTS` |
| `seo/services.py` | +`get_postal_addresses_for_tenants`, +`build_aggregate_points`, refacto `build_explorer_data_for_tenants` |
| `seo/tasks.py` | +Etape 6 dans `refresh_seo_cache` (ecriture AGGREGATE_POINTS) |
| `seo/views.py` | `explorer()` passe `points` au template |
| `seo/templates/seo/explorer.html` | JSON-LD ItemList itere sur `points` |
| `seo/static/seo/explorer.js` | Boucle sur `points`, popup HTML riche |
| `seo/static/seo/explorer.css` | Styles popup |
| `tests/pytest/test_seo_aggregate_points.py` | Tests unitaires (6) |
| `tests/e2e/test_explorer_markers_per_pa.py` | Tests E2E Playwright (2) |

### Migration
- **Migration necessaire / Migration required:** Non. Aucune migration DB. Juste une nouvelle valeur dans un `CharField choices`. Le cache `AGGREGATE_LIEUX` reste intact (consomme par d'autres vues).
- **Activation :** prochain cycle Celery Beat de `refresh_seo_cache` (4h max), ou manuel via shell.
```

- [ ] **Step 2: Creer la doc test manuel**

`A TESTER et DOCUMENTER/explorer-markers-per-pa.md` :

```markdown
# Carte explorer ROOT : 1 marker par PostalAddress

## Ce qui a ete fait

Cf. CHANTIER-05 dans `TECH_DOC/SESSIONS/SEO/`.

## Tests a realiser

### Test 1 : Force refresh + visualisation

1. Lancer `docker exec lespass_django poetry run python manage.py shell -c "from seo.tasks import refresh_seo_cache; refresh_seo_cache()"`
2. Ouvrir `/explorer/` du tenant ROOT (root local : `http://localhost:8002/explorer/`)
3. Compter visuellement (clusters inclus, zoomer) — verifier que c'est > nombre de tenants avant import (~80 → 300+)

### Test 2 : Popup sur Universite Populaire Villeurbanne

1. Aller sur `/explorer/` ROOT
2. Zoomer sur Villeurbanne/Lyon
3. Verifier ~24 markers (les 24 lieux d'events d'UPOP)
4. Cliquer un marker : popup affiche nom adresse + "Universite Populaire Villeurbanne" + events futurs si presents

### Test 3 : Cas tenant sans event futur

1. Identifier un tenant qui a 1 PA principale + 0 event futur (mais 1 produit publie)
2. Verifier qu'il apparait quand meme sur la carte (filtre "tenant vivant" inclut OR product_count > 0)
3. Popup : section "Evenements futurs" absente

### Test 4 : Cache memcached propre

1. Apres refresh, ouvrir Django admin /admin/seo/seocache/
2. Verifier qu'on a bien 2 lignes globales (tenant=None) : `aggregate_lieux` ET `aggregate_points`
3. Pas de regression sur `aggregate_lieux` (autre vues comme /lieux/ doivent continuer a fonctionner)

## Compatibilite

- `AGGREGATE_LIEUX` intact -> vues /lieu/<slug>/, /lieux/, recherche ROOT, JSON-LD sitemap fonctionnent comme avant.
- Rollback : supprimer la constante + la fonction (carte vide mais pas d'erreur).
```

- [ ] **Step 3: Commit (par mainteneur)**

```bash
git add CHANGELOG.md "A TESTER et DOCUMENTER/explorer-markers-per-pa.md"
git commit -m "docs: CHANGELOG + test plan for per-PA explorer markers"
```

---

## Self-review du plan

**Coverage spec :**
- ✅ Section 1 (semantique) → Tasks 7, 8, 9 (JS + CSS)
- ✅ Section 2 (cache structure) → Tasks 1, 2, 3
- ✅ Section 3.1-3.2 (cache + service) → Tasks 1, 2, 3, 5
- ✅ Section 3.3 (build_explorer_data) → Task 4
- ✅ Section 3.4 (frontend) → Tasks 6, 7, 8, 9
- ✅ Section 4 (mockup popup) → Task 8 (`construirePopupHtml`)
- ✅ Section 5 (fichiers modifies) → Tasks 1-9 couvrent tous
- ✅ Section 6 (tests) → Tasks 2, 3, 4, 5, 10
- ✅ Section 7 (rollout) → Task 11 (CHANGELOG)

**Placeholder scan :** OK, pas de "TBD", pas de "etc.", chaque step a code complet.

**Type consistency :** `pa_id` (int), `tenant_id` (str uuid), `events_futurs_count_total` (int) — coherent entre Task 3, 4, 7, 8.

**Eventual fix :** la fonction `get_events_for_tenants` doit retourner `postal_address_id` (Task 3 Step 4). Si elle ne le fait pas deja, c'est un sous-changement a faire dans Task 3.

---

## Execution

Plan complet : 11 tasks, ~50 steps. Estimation : 3-5 sessions courtes (1-2h chacune) avec subagents.

**Pre-requis avant execution :**
1. Mainteneur a accepte la spec CHANTIER-05.
2. Branche dediee creee : `git checkout -b feat/explorer-markers-per-pa`.
3. Container `lespass_django` actif (`docker compose up -d`).
4. Tests existants verts (`pytest tests/pytest/test_seo_indexing.py -v`).

**Methode recommandee :** `superpowers:subagent-driven-development` — 1 subagent par task avec review du mainteneur entre chaque.
