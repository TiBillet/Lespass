# Explorer — visualisation des monnaies et fédérations — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permettre à un visiteur de `/explorer/` de voir quels lieux acceptent quelle monnaie, avec deux styles visuels selon la nature de la monnaie (arcs depuis l'origine pour une fédération partielle, polygone enveloppant pour la fédération globale TiBillet).

**Architecture:** Enrichissement du cache SEO (`AGGREGATE_ASSETS` + `TENANT_SUMMARY`) avec les relations asset↔tenants via les fédérations `fedow_core`. Côté JS, un mode "focus monnaie" qui dessine un layer Leaflet dédié (arcs ou polygone convex hull), dim les marqueurs non-acceptants, et affiche une légende contextuelle. Badges cliquables sur chaque card lieu pour déclencher le focus depuis le lieu.

**Tech Stack:** Django 4.2, django-tenants, Leaflet 1.9 + markercluster, vanilla JS, PostgreSQL JSONField, pytest, Playwright.

**Spec de référence:** `TECH DOC/SESSIONS/ROOT_VIEW/2026-04-12-explorer-monnaies-federation-design.md`

---

## Phase 1 — Données et cache

### Task 1 : Enrichir `get_all_assets()` avec les relations fédération

**Files:**
- Modify: `seo/services.py:520` (fonction `get_all_assets()`)
- Test: `tests/pytest/test_seo_explorer_assets.py` (nouveau fichier)

- [ ] **Step 1: Écrire le test qui échoue**

Créer `tests/pytest/test_seo_explorer_assets.py` :

```python
"""
Tests pour l'enrichissement des assets dans le cache SEO.
/ Tests for asset enrichment in SEO cache.
"""
import pytest
from django.db import connection
from django_tenants.utils import schema_context, tenant_context
from Customers.models import Client
from fedow_core.models import Asset, Federation


@pytest.mark.django_db(transaction=True)
def test_get_all_assets_returns_origin_and_accepting_tenants():
    """
    Vérifie que get_all_assets() retourne tenant_origin_id/name et accepting_tenant_ids.
    / Verify get_all_assets() returns tenant_origin_id/name and accepting_tenant_ids.
    """
    from seo.services import get_all_assets

    # On part du principe qu'il y a au moins 1 asset existant (fixture)
    # / Assume at least 1 existing asset (fixture)
    assets = get_all_assets()
    assert len(assets) > 0, "La fixture doit contenir des assets"

    for asset in assets:
        assert "uuid" in asset
        assert "name" in asset
        assert "category" in asset
        assert "tenant_origin_id" in asset
        assert "tenant_origin_name" in asset
        assert "accepting_tenant_ids" in asset
        assert "accepting_count" in asset
        assert "is_federation_primary" in asset
        assert isinstance(asset["accepting_tenant_ids"], list)
        assert isinstance(asset["accepting_count"], int)
        assert isinstance(asset["is_federation_primary"], bool)


@pytest.mark.django_db(transaction=True)
def test_asset_fed_is_federation_primary():
    """
    Les assets de catégorie FED sont marqués is_federation_primary=True.
    / FED category assets are flagged as federation primary.
    """
    from seo.services import get_all_assets

    assets = get_all_assets()
    fed_assets = [a for a in assets if a["category"] == "FED"]
    for asset in fed_assets:
        assert asset["is_federation_primary"] is True


@pytest.mark.django_db(transaction=True)
def test_asset_local_has_only_origin_in_accepting():
    """
    Un asset non fédéré a uniquement son tenant_origin dans accepting_tenant_ids.
    / Non-federated asset has only tenant_origin in accepting_tenant_ids.
    """
    from seo.services import get_all_assets

    assets = get_all_assets()
    for asset in assets:
        if asset["category"] != "FED" and asset["tenant_origin_id"]:
            # Asset local : seul le tenant origine doit être dans la liste
            # / Local asset: only the origin tenant should be in the list
            if asset["accepting_count"] == 1:
                assert asset["accepting_tenant_ids"] == [asset["tenant_origin_id"]]
```

- [ ] **Step 2: Lancer les tests pour confirmer l'échec**

Run: `docker exec lespass_django poetry run pytest tests/pytest/test_seo_explorer_assets.py -v`
Expected: FAIL avec `KeyError: 'tenant_origin_id'` ou similaire.

- [ ] **Step 3: Modifier `get_all_assets()` dans `seo/services.py`**

Remplacer entièrement la fonction `get_all_assets()` :

```python
def get_all_assets():
    """
    Recupere tous les assets fedow_core avec leurs relations de federation.
    1 requete SQL avec LEFT JOIN sur fedow_core_asset_federated_with + fedow_core_federation_tenants.
    / Fetch all fedow_core assets with their federation relations.
    Single SQL query with LEFT JOIN on federations and federation tenants.

    Retourne / Returns: list[dict] avec cles :
        uuid, name, category, tenant_origin_id, tenant_origin_name,
        accepting_tenant_ids (list), accepting_count (int), is_federation_primary (bool)
    """
    # On recupere en 1 requete :
    # - l'asset et son tenant_origin (via AuthBillet_wallet.ephemere_tenant ou direct FK)
    # - les federations liees (M2M federated_with)
    # - les tenants de chaque federation (M2M federation.tenants)
    # / Single query fetches:
    # - asset + its tenant_origin
    # - linked federations (M2M federated_with)
    # - tenants of each federation (M2M federation.tenants)
    sql = """
        SELECT
            a.uuid::text AS asset_uuid,
            a.name AS asset_name,
            a.category AS asset_category,
            c_origin.uuid::text AS origin_uuid,
            c_origin.name AS origin_name,
            ARRAY_REMOVE(ARRAY_AGG(DISTINCT c_fed.uuid::text), NULL) AS federated_tenant_uuids
        FROM "public"."fedow_core_asset" a
        LEFT JOIN "public"."Customers_client" c_origin ON a.tenant_origin_id = c_origin.uuid
        LEFT JOIN "public"."fedow_core_asset_federated_with" afw ON a.uuid = afw.asset_id
        LEFT JOIN "public"."fedow_core_federation_tenants" ft ON afw.federation_id = ft.federation_id
        LEFT JOIN "public"."Customers_client" c_fed ON ft.client_id = c_fed.uuid
        GROUP BY a.uuid, a.name, a.category, c_origin.uuid, c_origin.name
        ORDER BY a.name
    """

    results = []
    with connection.cursor() as cursor:
        cursor.execute(sql)
        for row in cursor.fetchall():
            asset_uuid, asset_name, asset_category, origin_uuid, origin_name, federated_ids = row

            # Union : tenant_origin + tenants federes = lieux acceptants
            # / Union: tenant_origin + federated tenants = accepting lieux
            accepting = set(federated_ids or [])
            if origin_uuid:
                accepting.add(origin_uuid)

            results.append({
                "uuid": asset_uuid,
                "name": asset_name,
                "category": asset_category,
                "tenant_origin_id": origin_uuid,
                "tenant_origin_name": origin_name,
                "accepting_tenant_ids": sorted(accepting),
                "accepting_count": len(accepting),
                "is_federation_primary": asset_category == "FED",
            })

    return results
```

- [ ] **Step 4: Vérifier le nom de colonne `tenant_origin_id`**

Run: `docker exec lespass_django poetry run python manage.py dbshell -c "\d fedow_core_asset"` pour confirmer le nom exact de la colonne FK tenant_origin. Si c'est différent (ex: `tenant_origin_id` vs `tenant_origin_uuid_id`), ajuster le SQL.

- [ ] **Step 5: Lancer les tests pour vérifier qu'ils passent**

Run: `docker exec lespass_django poetry run pytest tests/pytest/test_seo_explorer_assets.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add seo/services.py tests/pytest/test_seo_explorer_assets.py
git commit -m "feat(seo): enrichir get_all_assets avec origin et accepting tenants"
```

---

### Task 2 : Enrichir `build_tenant_config_data()` avec les assets acceptés

**Files:**
- Modify: `seo/services.py` (fonction `build_tenant_config_data`, ajouter `accepted_assets`)
- Test: `tests/pytest/test_seo_explorer_assets.py` (ajouter un test)

- [ ] **Step 1: Ajouter le test qui échoue**

Ajouter à `tests/pytest/test_seo_explorer_assets.py` :

```python
@pytest.mark.django_db(transaction=True)
def test_tenant_config_includes_accepted_assets():
    """
    Chaque tenant config doit inclure la liste des assets acceptes (uuid).
    / Each tenant config must include the list of accepted assets (uuid).
    """
    from seo.services import build_tenant_config_data

    tenant = Client.objects.exclude(schema_name="public").first()
    assert tenant is not None, "Fixture must have at least one tenant"

    data = build_tenant_config_data(tenant)
    assert "accepted_asset_ids" in data
    assert isinstance(data["accepted_asset_ids"], list)
```

- [ ] **Step 2: Lancer le test pour confirmer l'échec**

Run: `docker exec lespass_django poetry run pytest tests/pytest/test_seo_explorer_assets.py::test_tenant_config_includes_accepted_assets -v`
Expected: FAIL avec `KeyError: 'accepted_asset_ids'` ou absence du champ.

- [ ] **Step 3: Modifier `build_tenant_config_data()` dans `seo/services.py`**

**IMPORTANT : il y a 3 chemins d'acceptation pour un asset**, pas 2 (comme découvert en Task 1) :
1. `tenant_origin` (l'asset appartient au tenant)
2. `Asset.federated_with` (M2M directe Asset↔Client, table `fedow_core_asset_federated_with` avec cols `asset_id`, `client_id`)
3. `Federation.assets` + `Federation.tenants` (via groupe Federation — tables `fedow_core_federation_assets` et `fedow_core_federation_tenants`)

Dans la fonction existante `build_tenant_config_data(client)`, juste avant le `return data`, ajouter :

```python
    # Liste des uuid d'assets acceptes par ce tenant.
    # Trois chemins d'acceptation :
    # 1. tenant_origin == ce tenant
    # 2. via Asset.federated_with (M2M directe Asset↔Client)
    # 3. via Federation.assets + Federation.tenants (groupe)
    # / List of asset UUIDs accepted by this tenant.
    # Three acceptance paths:
    # 1. tenant_origin == this tenant
    # 2. via Asset.federated_with (direct Asset↔Client M2M)
    # 3. via Federation.assets + Federation.tenants (group)
    sql_accepted = """
        SELECT DISTINCT a.uuid::text
        FROM "public"."fedow_core_asset" a
        WHERE a.tenant_origin_id = %s AND a.active = TRUE AND a.archive = FALSE
        UNION
        SELECT DISTINCT afw.asset_id::text
        FROM "public"."fedow_core_asset_federated_with" afw
        JOIN "public"."fedow_core_asset" a ON afw.asset_id = a.uuid
        WHERE afw.client_id = %s AND a.active = TRUE AND a.archive = FALSE
        UNION
        SELECT DISTINCT fa.asset_id::text
        FROM "public"."fedow_core_federation_assets" fa
        JOIN "public"."fedow_core_federation_tenants" ft ON fa.federation_id = ft.federation_id
        JOIN "public"."fedow_core_asset" a ON fa.asset_id = a.uuid
        WHERE ft.client_id = %s AND a.active = TRUE AND a.archive = FALSE
    """
    accepted_ids = []
    with connection.cursor() as cursor:
        cursor.execute(sql_accepted, [str(client.uuid), str(client.uuid), str(client.uuid)])
        for row in cursor.fetchall():
            accepted_ids.append(row[0])
    data["accepted_asset_ids"] = sorted(accepted_ids)
```

**Vérifier les noms de tables réels** avec `\d` si besoin — les vrais noms sont `fedow_core_asset_federated_with` (cols `asset_id`, `client_id`) et `fedow_core_federation_assets` (cols `federation_id`, `asset_id`) et `fedow_core_federation_tenants` (cols `federation_id`, `client_id`).

- [ ] **Step 4: Lancer le test pour confirmer le PASS**

Run: `docker exec lespass_django poetry run pytest tests/pytest/test_seo_explorer_assets.py::test_tenant_config_includes_accepted_assets -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add seo/services.py tests/pytest/test_seo_explorer_assets.py
git commit -m "feat(seo): ajouter accepted_asset_ids dans build_tenant_config_data"
```

---

### Task 3 : Propager les nouveaux champs dans `build_explorer_data()`

**Files:**
- Modify: `seo/services.py` (fonction `build_explorer_data`)
- Test: `tests/pytest/test_seo_explorer_assets.py` (ajouter un test)

- [ ] **Step 1: Ajouter le test qui échoue**

```python
@pytest.mark.django_db(transaction=True)
def test_build_explorer_data_assets_have_federation_fields():
    """
    Les assets dans build_explorer_data() exposent les champs de federation.
    / Assets in build_explorer_data() expose federation fields.
    """
    from seo.services import build_explorer_data

    # Recharger le cache au prealable
    # / Reload cache first
    from django.core.management import call_command
    call_command("refresh_seo_cache")

    data = build_explorer_data()
    assert "assets" in data
    assert len(data["assets"]) > 0

    for asset in data["assets"]:
        assert "tenant_origin_id" in asset
        assert "tenant_origin_name" in asset
        assert "accepting_tenant_ids" in asset
        assert "accepting_count" in asset
        assert "is_federation_primary" in asset


@pytest.mark.django_db(transaction=True)
def test_build_explorer_data_lieux_have_accepted_assets():
    """
    Les lieux dans build_explorer_data() exposent accepted_asset_ids.
    / Lieux in build_explorer_data() expose accepted_asset_ids.
    """
    from seo.services import build_explorer_data
    from django.core.management import call_command
    call_command("refresh_seo_cache")

    data = build_explorer_data()
    assert "lieux" in data
    for lieu in data["lieux"]:
        assert "accepted_asset_ids" in lieu
        assert isinstance(lieu["accepted_asset_ids"], list)
```

- [ ] **Step 2: Lancer le test pour confirmer l'échec**

Run: `docker exec lespass_django poetry run pytest tests/pytest/test_seo_explorer_assets.py -v`
Expected: FAIL sur les 2 nouveaux tests.

- [ ] **Step 3: Vérifier le pipeline tasks.py**

Dans `seo/tasks.py`, vérifier que `tenant_summary` contient déjà tout le dict retourné par `build_tenant_config_data`. Si oui, `accepted_asset_ids` est déjà propagé automatiquement via `**config_data` (voir étape 5 du pipeline).

Lire `seo/tasks.py` ligne 124-135 :

```python
        summary_data = {
            **config_data,
            **counts,
        }
```

Le `**config_data` inclut déjà `accepted_asset_ids` car on l'a ajouté à `build_tenant_config_data`. Pas de modif nécessaire.

- [ ] **Step 4: Propager `accepted_asset_ids` dans `build_explorer_data()`**

Modifier `seo/services.py`, fonction `build_explorer_data()`, section "Index des lieux par tenant_id" :

```python
    lieux_by_tenant = {}
    for lieu in raw_lieux:
        if lieu.get("latitude") is None or lieu.get("longitude") is None:
            continue
        lieu_copy = dict(lieu)
        lieu_copy["events"] = []
        lieu_copy["memberships"] = []
        lieu_copy["initiatives"] = []
        # Les assets acceptes par ce lieu sont dans tenant_summary (cache).
        # / Accepted assets for this lieu come from tenant_summary cache.
        tenant_id = lieu["tenant_id"]
        summary = get_seo_cache(SEOCache.TENANT_SUMMARY, tenant_id) or {}
        lieu_copy["accepted_asset_ids"] = summary.get("accepted_asset_ids", [])
        lieux_by_tenant[tenant_id] = lieu_copy
```

Importer `get_seo_cache` en haut du fichier :

```python
from seo.views_common import get_seo_cache
```

(Attention aux imports circulaires — déjà fait dans `build_explorer_data`, mais ici au niveau module. Si ça crash, faire l'import local dans la fonction `build_explorer_data` comme pour `SEOCache`.)

- [ ] **Step 5: Rafraîchir le cache SEO**

Run: `docker exec lespass_django poetry run python manage.py refresh_seo_cache`
Expected: succès, pas d'erreur.

- [ ] **Step 6: Lancer les tests**

Run: `docker exec lespass_django poetry run pytest tests/pytest/test_seo_explorer_assets.py -v`
Expected: PASS sur tous les tests de la suite.

- [ ] **Step 7: Commit**

```bash
git add seo/services.py tests/pytest/test_seo_explorer_assets.py
git commit -m "feat(seo): propager accepted_asset_ids et federation fields dans build_explorer_data"
```

---

### Task 4 : Enrichir la fixture `demo_data_v2` avec fédérations réalistes

**Files:**
- Modify: `Administration/management/commands/demo_data_v2.py`

- [ ] **Step 1: Lire la section actuelle de création des assets dans demo_data_v2**

Run: `grep -n "fedow_core\|Asset\|Federation" /home/jonas/TiBillet/dev/Lespass/Administration/management/commands/demo_data_v2.py`

Repérer l'endroit où les assets sont créés. Si aucune création explicite d'assets n'existe (tout est fait par des signaux Django), on intervient après toute la création des tenants.

- [ ] **Step 2: Ajouter une méthode `_create_federations_demo` dans demo_data_v2**

Au niveau classe de la Command, après la méthode principale `_handle_full`, ajouter :

```python
    def _create_federations_demo(self):
        """
        Cree 2 federations demo et lie les assets pour une demo realiste.
        / Creates 2 demo federations and links assets for a realistic demo.

        - "Réseau TiBillet Lyon" : tous les tenants, asset FED principal
        - "Echange local" : 2 tenants, asset TIM (temps)
        """
        from fedow_core.models import Asset, Federation
        from Customers.models import Client

        tenants = list(Client.objects.exclude(schema_name="public"))
        if len(tenants) < 2:
            self.stdout.write("Pas assez de tenants pour creer les federations demo.")
            return

        # Federation globale : tous les tenants
        # / Global federation: all tenants
        fed_globale, _ = Federation.objects.get_or_create(
            name="Réseau TiBillet Lyon",
        )
        fed_globale.tenants.set(tenants)

        # Federation partielle : 2 tenants
        # / Partial federation: 2 tenants
        fed_partielle, _ = Federation.objects.get_or_create(
            name="Echange local",
        )
        fed_partielle.tenants.set(tenants[:2])

        # Lier les assets existants aux federations
        # / Link existing assets to federations
        asset_fed = Asset.objects.filter(category="FED").first()
        if asset_fed:
            asset_fed.federated_with.set([fed_globale])
            self.stdout.write(f"Asset {asset_fed.name} -> Reseau TiBillet Lyon")

        asset_tim = Asset.objects.filter(category="TIM").first()
        if asset_tim:
            asset_tim.federated_with.set([fed_partielle])
            self.stdout.write(f"Asset {asset_tim.name} -> Echange local")

        # Creer un asset supplementaire pour un autre lieu (diversite)
        # / Create an extra asset for another lieu (diversity)
        coeur = Client.objects.filter(schema_name="le-coeur-en-or").first()
        if coeur:
            Asset.objects.get_or_create(
                name="Monnaie Coeur",
                category="TLF",
                defaults={
                    "tenant_origin": coeur,
                    "currency_code": "MCO",
                    "active": True,
                },
            )
            self.stdout.write("Asset 'Monnaie Coeur' cree pour le-coeur-en-or")
```

- [ ] **Step 3: Appeler `_create_federations_demo` dans le flow principal**

Dans `_handle_full`, juste avant l'étape de refresh du cache SEO (cherche `refresh_seo_cache`), ajouter :

```python
        self._create_federations_demo()
```

- [ ] **Step 4: Re-générer les données demo**

Run: `docker exec lespass_django poetry run python manage.py demo_data_v2`
Expected: succès, messages "Asset ... -> Reseau TiBillet Lyon" affichés.

- [ ] **Step 5: Vérifier manuellement la donnée**

Run: `docker exec lespass_django poetry run python manage.py shell -c "
from fedow_core.models import Asset, Federation
for f in Federation.objects.all():
    print(f.name, '->', [t.schema_name for t in f.tenants.all()])
print('---')
for a in Asset.objects.all():
    print(a.name, a.category, 'origine=', a.tenant_origin.schema_name if a.tenant_origin else None, 'fed=', [f.name for f in a.federated_with.all()])
"`

Expected (ou équivalent selon l'ordre) :
```
Réseau TiBillet Lyon -> ['lespass', 'chantefrein', 'le-coeur-en-or', 'la-maison-des-communs', 'le-reseau-des-lieux-en-reseau']
Echange local -> ['lespass', 'chantefrein']
---
Monnaie locale TLF origine= lespass fed= []
Cadeau TNF origine= lespass fed= []
Temps TIM origine= lespass fed= ['Echange local']
Fédéré TiBillet FED origine= lespass fed= ['Réseau TiBillet Lyon']
Points fidélité FID origine= lespass fed= []
Monnaie Coeur TLF origine= le-coeur-en-or fed= []
```

- [ ] **Step 6: Rafraîchir le cache et valider avec pytest**

Run:
```bash
docker exec lespass_django poetry run python manage.py refresh_seo_cache
docker exec lespass_django poetry run pytest tests/pytest/test_seo_explorer_assets.py -v
```
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add Administration/management/commands/demo_data_v2.py
git commit -m "feat(demo): ajouter federations demo realistes pour l'explorer"
```

---

## Phase 2 — Badges monnaies sur cards lieu

### Task 5 : Afficher les badges monnaies sur chaque card lieu

**Files:**
- Modify: `seo/static/seo/explorer.js` (fonction `buildLieuCard`)
- Modify: `seo/static/seo/explorer.css` (nouveau bloc `.lieu-asset-badges`)

- [ ] **Step 1: Ajouter les données assets au JS via le config JSON**

Les données assets sont déjà dans `explorerData.assets`. Chaque asset a `accepting_tenant_ids`, chaque lieu a `accepted_asset_ids`. On va croiser côté JS.

Ajouter en haut de `explorer.js`, après la déclaration `var CATEGORIES = {...}` (ligne ~20), une nouvelle map pour l'affichage badge :

```javascript
// Icones compacts + libelles courts pour les badges monnaie sur les cards lieu.
// / Compact icons + short labels for asset badges on lieu cards.
var ASSET_BADGE_CONFIG = {
    TLF: { icon: '\u{1F4B0}', label: 'Monnaie locale' },
    TNF: { icon: '\u{1F381}', label: 'Cadeau' },
    TIM: { icon: '\u{23F0}', label: 'Temps' },
    FED: { icon: '\u{1F517}', label: 'Fédéré' },
    FID: { icon: '\u{2B50}', label: 'Fidélité' },
};
```

- [ ] **Step 2: Ajouter une fonction `buildLieuAssetBadges`**

Dans `explorer.js`, après la fonction `buildLieuCard` :

```javascript
/**
 * Construit la rangee de badges monnaies pour une card lieu.
 * Croise lieu.accepted_asset_ids avec explorerData.assets pour retrouver les donnees.
 * / Builds the asset badges row for a lieu card.
 * Cross-references lieu.accepted_asset_ids with explorerData.assets.
 */
function buildLieuAssetBadges(lieu) {
    var acceptedIds = lieu.accepted_asset_ids || [];
    if (acceptedIds.length === 0) return '';

    // Index rapide des assets par uuid / Quick asset lookup by uuid
    var assetsByUuid = {};
    for (var i = 0; i < explorerData.assets.length; i++) {
        assetsByUuid[explorerData.assets[i].uuid] = explorerData.assets[i];
    }

    var badges = '';
    for (var j = 0; j < acceptedIds.length; j++) {
        var asset = assetsByUuid[acceptedIds[j]];
        if (!asset) continue;
        var config = ASSET_BADGE_CONFIG[asset.category] || { icon: '\u{1F4B0}', label: asset.category };
        var uuidEscaped = escapeHtml(asset.uuid);
        badges += ''
            + '<button type="button" class="lieu-asset-badge" data-asset-uuid="' + uuidEscaped + '"'
            + ' onclick="handleAssetBadgeClick(event, \'' + uuidEscaped + '\')" title="' + escapeHtml(asset.name) + '">'
            + '<span class="lieu-asset-badge-icon">' + config.icon + '</span>'
            + '<span class="lieu-asset-badge-label">' + escapeHtml(config.label) + '</span>'
            + '</button>';
    }

    if (!badges) return '';
    return '<div class="lieu-asset-badges">' + badges + '</div>';
}

/**
 * Handler du clic sur un badge monnaie : empeche la propagation (pas de focus lieu)
 * et delegue a focusOnAsset. Sera implemente dans la Phase 3.
 * / Asset badge click handler: stops propagation and delegates to focusOnAsset.
 */
function handleAssetBadgeClick(event, assetUuid) {
    event.stopPropagation();
    // focusOnAsset sera defini en Phase 3. En Phase 2, log simple.
    // / focusOnAsset will be defined in Phase 3. For Phase 2, simple log.
    if (typeof focusOnAsset === 'function') {
        focusOnAsset(assetUuid);
    } else {
        console.log('[asset badge] clicked', assetUuid);
    }
}
```

- [ ] **Step 3: Intégrer les badges dans `buildLieuCard`**

Modifier `buildLieuCard` : insérer `buildLieuAssetBadges(lieu)` juste avant le return final. Trouver la ligne `+ buildAccordion(lieu, domain)` et ajouter une ligne avant :

```javascript
    return ''
        + '<div class="explorer-card explorer-card--lieu" data-lieu-id="' + tenantId + '" data-type="lieu">'
            + '<div class="explorer-card-focus" onclick="focusOnLieu(\'' + tenantId + '\')" role="button" tabindex="0" title="Voir sur la carte">'
                + logo
                + '<div class="explorer-card-body">'
                    + '<div class="explorer-card-header">'
                        + '<h3 class="explorer-card-title">' + escapeHtml(lieu.name) + '</h3>'
                        + '<span class="explorer-badge lieu">Lieu</span>'
                    + '</div>'
                    + meta
                    + desc
                    + buildLieuAssetBadges(lieu)
                + '</div>'
            + '</div>'
            + buildAccordion(lieu, domain)
            + '<div class="explorer-card-footer">'
                + '<a href="' + escapeHtml(href) + '" target="_blank" class="explorer-card-link">Visiter le lieu \u2192</a>'
            + '</div>'
        + '</div>';
```

- [ ] **Step 4: Ajouter les styles CSS pour les badges**

Dans `seo/static/seo/explorer.css`, après la section "Cards / Cards" (après la règle `.explorer-card-desc`) :

```css
/* ============================================================
 * Badges monnaies sur cards lieu / Asset badges on lieu cards
 * ============================================================ */
.lieu-asset-badges {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin-top: 8px;
}

.lieu-asset-badge {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 3px 8px;
    border: 1px solid rgba(0, 0, 0, 0.08);
    border-radius: 999px;
    background: rgba(0, 0, 0, 0.03);
    font-size: 11px;
    color: #555;
    cursor: pointer;
    transition: background 150ms, border-color 150ms, transform 150ms;
}

.lieu-asset-badge:hover {
    background: rgba(37, 157, 73, 0.08);
    border-color: rgba(37, 157, 73, 0.3);
    color: #259d49;
    transform: translateY(-1px);
}

.lieu-asset-badge--active {
    background: #259d49;
    border-color: #259d49;
    color: #fff;
}

.lieu-asset-badge-icon {
    font-size: 12px;
    line-height: 1;
}

.lieu-asset-badge-label {
    font-weight: 500;
}
```

- [ ] **Step 5: Collecter les statics et tester visuellement**

Run:
```bash
docker exec lespass_django poetry run python manage.py collectstatic --no-input
```

Puis recharger `/explorer/` dans le navigateur. Vérifier visuellement :
- Chaque card lieu a une rangée de petits badges sous la description
- Les badges affichent l'icône + le libellé (ex: "💰 Monnaie locale")
- Hover change la couleur vers vert TiBillet

- [ ] **Step 6: Commit**

```bash
git add seo/static/seo/explorer.js seo/static/seo/explorer.css
git commit -m "feat(explorer): ajouter badges monnaies sur les cards lieu"
```

---

## Phase 3 — Mode focus monnaie sur la carte

### Task 6 : State global + fonctions de base pour le mode focus

**Files:**
- Modify: `seo/static/seo/explorer.js` (ajout de variables + fonctions `focusOnAsset`, `clearAssetFocus`)

- [ ] **Step 1: Ajouter le state global pour le focus asset**

Dans `explorer.js`, après la ligne `var currentView = 'list';` (section Etat global), ajouter :

```javascript
// UUID de l'asset actuellement en mode focus, ou null.
// / UUID of currently focused asset, or null.
var activeAssetUuid = null;

// Layer group Leaflet pour contenir les arcs/polygone du mode focus.
// Vide = clear facile via clearLayers().
// / Leaflet layer group for focus mode arcs/polygon. Empty = easy clear via clearLayers().
var assetLayerGroup = null;
```

- [ ] **Step 2: Initialiser le layerGroup dans `initMap`**

Dans la fonction `initMap()`, juste après `markerClusterGroup = L.markerClusterGroup();` et avant `map.addLayer(markerClusterGroup);` :

```javascript
    markerClusterGroup = L.markerClusterGroup();
    map.addLayer(markerClusterGroup);

    // Layer group dedie au mode focus asset (arcs, hull).
    // Ajoute apres markerClusterGroup pour passer AU-DESSUS des markers.
    // / Dedicated layer group for asset focus mode (arcs, hull).
    // Added after markerClusterGroup to render ABOVE markers.
    assetLayerGroup = L.layerGroup();
    map.addLayer(assetLayerGroup);
```

- [ ] **Step 3: Ajouter `focusOnAsset` et `clearAssetFocus`**

En fin de fichier, avant `document.addEventListener('DOMContentLoaded', init);`, ajouter :

```javascript
// ============================================================
// Mode focus asset / Asset focus mode
// ============================================================

/**
 * Active le mode focus sur une monnaie : highlight des lieux acceptants,
 * dim des autres, dessin des liaisons (arcs ou polygone) sur la carte.
 * Si l'asset est deja actif, on desactive (toggle).
 * / Activate asset focus: highlight accepting lieux, dim others, draw links
 * (arcs or polygon) on map. If asset already active, deactivate (toggle).
 */
function focusOnAsset(assetUuid) {
    // Toggle : si meme asset clique 2 fois, on sort du mode focus.
    // / Toggle: same asset clicked twice exits focus mode.
    if (activeAssetUuid === assetUuid) {
        clearAssetFocus();
        return;
    }

    var asset = findAssetByUuid(assetUuid);
    if (!asset) return;

    // Init carte si pas encore fait / Init map if not done yet
    if (!mapInitialized) initMap();

    // Sur mobile, basculer en vue carte / On mobile, switch to map view
    if (window.innerWidth < 992 && currentView === 'list') toggleView();

    activeAssetUuid = assetUuid;
    applyDimming(asset.accepting_tenant_ids || []);
    drawAssetLinks(asset);
    renderAssetLegend(asset);
    refreshAssetBadgeActiveState();
    refreshMapMarkersForFocus(asset);
}

function clearAssetFocus() {
    activeAssetUuid = null;
    applyDimming(null);
    if (assetLayerGroup) assetLayerGroup.clearLayers();
    renderAssetLegend(null);
    refreshAssetBadgeActiveState();
    // Remettre les marqueurs a l'etat "applique filtres" / Reapply filters to markers
    applyFilters();
}

function findAssetByUuid(uuid) {
    if (!explorerData || !explorerData.assets) return null;
    for (var i = 0; i < explorerData.assets.length; i++) {
        if (explorerData.assets[i].uuid === uuid) return explorerData.assets[i];
    }
    return null;
}

/**
 * Applique la classe CSS dimmed aux marqueurs non acceptants.
 * Si acceptingIds est null, retire le dimming partout.
 * / Apply dimmed CSS class to non-accepting markers.
 * If acceptingIds is null, remove dimming everywhere.
 */
function applyDimming(acceptingIds) {
    var pinElements = document.querySelectorAll('.explorer-pin');
    if (!acceptingIds) {
        pinElements.forEach(function(el) { el.classList.remove('explorer-pin--dimmed'); });
        return;
    }
    var acceptingSet = {};
    for (var i = 0; i < acceptingIds.length; i++) acceptingSet[acceptingIds[i]] = true;
    pinElements.forEach(function(el) {
        var id = el.getAttribute('data-lieu-id');
        if (acceptingSet[id]) el.classList.remove('explorer-pin--dimmed');
        else el.classList.add('explorer-pin--dimmed');
    });
}

/**
 * Restaure les marqueurs sur la carte en mode focus : tous les lieux
 * (acceptants + dimmed) doivent rester visibles pour lire les liaisons.
 * / Refresh map markers in focus mode: all lieux (accepting + dimmed)
 * remain visible to read the connections.
 */
function refreshMapMarkersForFocus(asset) {
    if (!mapInitialized) return;
    // En mode focus, on affiche TOUS les lieux (pour que le dimming
    // ait du sens et que les connexions soient lisibles).
    // / In focus mode, we show ALL lieux (so dimming makes sense
    // and connections are readable).
    updateMapMarkers(explorerData.lieux);
    // Fit bounds sur les lieux acceptants uniquement pour zoomer dessus.
    // / Fit bounds on accepting lieux only to zoom on them.
    var acceptingLatLngs = [];
    for (var i = 0; i < asset.accepting_tenant_ids.length; i++) {
        var marker = markers[asset.accepting_tenant_ids[i]];
        if (marker) acceptingLatLngs.push(marker.getLatLng());
    }
    if (acceptingLatLngs.length > 0) {
        map.fitBounds(L.latLngBounds(acceptingLatLngs), { padding: [40, 40], maxZoom: 14 });
    }
}

/**
 * Met a jour la classe active sur les badges monnaie des cards lieu.
 * / Update active class on asset badges of lieu cards.
 */
function refreshAssetBadgeActiveState() {
    document.querySelectorAll('.lieu-asset-badge').forEach(function(badge) {
        var badgeUuid = badge.getAttribute('data-asset-uuid');
        badge.classList.toggle('lieu-asset-badge--active', badgeUuid === activeAssetUuid);
    });
}
```

- [ ] **Step 4: Ajouter les styles CSS pour le dimming**

Dans `explorer.css`, juste après la règle `.explorer-pin.selected` :

```css
/* Pin estompe en mode focus asset : les lieux qui n'acceptent pas */
/* la monnaie selectionnee apparaissent en retrait visuel.         */
/* / Dimmed pin in asset focus mode: lieux that do not accept the  */
/* selected currency fade visually.                                */
.explorer-pin--dimmed {
    opacity: 0.3;
    filter: grayscale(0.5);
}
```

- [ ] **Step 5: Test visuel intermédiaire**

Ajouter temporairement à la console navigateur (sur `/explorer/`) :

```javascript
focusOnAsset(explorerData.assets[0].uuid);
```

Vérifier :
- Les lieux non acceptants deviennent gris/estompés
- Pas encore de lignes sur la carte (la fonction `drawAssetLinks` n'existe pas encore — sera dans Task 7/8)
- Pas encore de légende (sera dans Task 9)

Si ça leve une erreur sur `drawAssetLinks`, c'est normal — on la crée à la tâche suivante.

- [ ] **Step 6: Commit**

```bash
git add seo/static/seo/explorer.js seo/static/seo/explorer.css
git commit -m "feat(explorer): state global pour le mode focus asset + dimming"
```

---

### Task 7 : Implémenter le style B — Polygone convex hull (fédération globale)

**Files:**
- Modify: `seo/static/seo/explorer.js`

- [ ] **Step 1: Ajouter l'algorithme convex hull**

Dans `explorer.js`, ajouter à la section "Mode focus asset" (en bas du fichier avant le DOMContentLoaded) :

```javascript
/**
 * Convex hull via algorithme de Graham scan (implementation simple).
 * / Convex hull via Graham scan algorithm (simple implementation).
 *
 * Retourne les points du hull dans l'ordre (pour tracer un polygone).
 * / Returns hull points in order (for polygon drawing).
 *
 * Entree : tableau de [lat, lng] / Input: array of [lat, lng]
 */
function computeConvexHull(points) {
    if (points.length < 3) return points.slice();

    // Trier par x puis y / Sort by x then y
    var sorted = points.slice().sort(function(a, b) {
        return a[1] - b[1] || a[0] - b[0];
    });

    // Fonction cross product pour tester le virage / Cross product for turn check
    function cross(o, a, b) {
        return (a[1] - o[1]) * (b[0] - o[0]) - (a[0] - o[0]) * (b[1] - o[1]);
    }

    // Lower hull
    var lower = [];
    for (var i = 0; i < sorted.length; i++) {
        while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], sorted[i]) <= 0) {
            lower.pop();
        }
        lower.push(sorted[i]);
    }

    // Upper hull
    var upper = [];
    for (var j = sorted.length - 1; j >= 0; j--) {
        while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], sorted[j]) <= 0) {
            upper.pop();
        }
        upper.push(sorted[j]);
    }

    // Concatener (en retirant les doublons en bout) / Concat without duplicates at ends
    lower.pop();
    upper.pop();
    return lower.concat(upper);
}
```

- [ ] **Step 2: Ajouter `drawHull`**

Ajouter juste après `computeConvexHull` :

```javascript
/**
 * Dessine un polygone translucide englobant les lieux acceptants (style B).
 * Utilise pour les assets federes primaires (TiBillet, category FED).
 * / Draws a translucent polygon around accepting lieux (style B).
 * Used for primary federated assets (TiBillet, category FED).
 */
function drawHull(latLngs) {
    if (!assetLayerGroup || latLngs.length < 2) return;

    // Si seulement 2 points, on trace juste une ligne epaisse
    // / If only 2 points, draw a thick line
    if (latLngs.length === 2) {
        L.polyline(latLngs, {
            color: '#259d49',
            weight: 3,
            opacity: 0.7,
        }).addTo(assetLayerGroup);
        return;
    }

    // 3+ points : convex hull / 3+ points: convex hull
    var pointsAsArray = latLngs.map(function(ll) { return [ll.lat, ll.lng]; });
    var hull = computeConvexHull(pointsAsArray);

    L.polygon(hull, {
        color: '#259d49',
        weight: 1.5,
        fillColor: '#259d49',
        fillOpacity: 0.22,
        opacity: 0.7,
    }).addTo(assetLayerGroup);
}
```

- [ ] **Step 3: Implémenter `drawAssetLinks` (dispatcher)**

Ajouter après `drawHull` :

```javascript
/**
 * Dispatcher selon la nature de l'asset :
 * - Federation primaire (FED, is_federation_primary) : polygone hull (drawHull)
 * - Asset federe partiellement avec origine : arcs (drawArcs) — Task 8
 * - Asset local (1 seul lieu) : pas de ligne
 * / Dispatcher based on asset nature:
 * - Primary federation (FED): hull polygon (drawHull)
 * - Partially federated with origin: arcs (drawArcs) — Task 8
 * - Local asset (1 lieu): no line
 */
function drawAssetLinks(asset) {
    if (!assetLayerGroup) return;
    assetLayerGroup.clearLayers();

    var acceptingIds = asset.accepting_tenant_ids || [];
    if (acceptingIds.length < 2) return;

    // Coordonnees des lieux acceptants / Coordinates of accepting lieux
    var latLngs = [];
    for (var i = 0; i < acceptingIds.length; i++) {
        var marker = markers[acceptingIds[i]];
        if (marker) latLngs.push(marker.getLatLng());
    }
    if (latLngs.length < 2) return;

    if (asset.is_federation_primary) {
        drawHull(latLngs);
    } else if (asset.tenant_origin_id) {
        // drawArcs sera implemente a la Task 8 / drawArcs implemented in Task 8
        if (typeof drawArcs === 'function') {
            drawArcs(asset.tenant_origin_id, acceptingIds);
        } else {
            // Fallback temporaire Task 7 : utiliser hull aussi
            // / Temporary Task 7 fallback: use hull
            drawHull(latLngs);
        }
    } else {
        drawHull(latLngs);
    }
}
```

- [ ] **Step 4: Test visuel — Style B (TiBillet)**

Collecter les statics, recharger la page, tester dans la console :

```javascript
var tibillet = explorerData.assets.find(function(a) { return a.is_federation_primary; });
focusOnAsset(tibillet.uuid);
```

Vérifier :
- Un polygone vert translucide englobe les lieux acceptants
- Les autres lieux sont dimmed (gris/estompés)
- La carte fit bounds sur la zone
- `focusOnAsset(tibillet.uuid)` à nouveau → tout se nettoie (clearAssetFocus)

- [ ] **Step 5: Commit**

```bash
git add seo/static/seo/explorer.js
git commit -m "feat(explorer): style B polygone hull pour federation globale"
```

---

### Task 8 : Implémenter le style C — Arcs depuis l'origine

**Files:**
- Modify: `seo/static/seo/explorer.js`

- [ ] **Step 1: Ajouter `drawArcs` avec courbe Bézier discrétisée**

Ajouter à `explorer.js`, à côté de `drawHull` :

```javascript
/**
 * Dessine des arcs courbes depuis le lieu origine vers chaque lieu acceptant (style C).
 * Implementation : L.polyline avec points d'une courbe de Bezier quadratique
 * discretisee (pas de plugin externe).
 * / Draws curved arcs from origin lieu to each accepting lieu (style C).
 * Uses L.polyline with points from a discretized quadratic Bezier curve (no plugin).
 *
 * @param {string} originId - tenant_id du lieu origine
 * @param {string[]} acceptingIds - tous les tenant_id acceptant (origine incluse, sera filtree)
 */
function drawArcs(originId, acceptingIds) {
    if (!assetLayerGroup) return;
    var originMarker = markers[originId];
    if (!originMarker) return;

    var originLatLng = originMarker.getLatLng();

    for (var i = 0; i < acceptingIds.length; i++) {
        var targetId = acceptingIds[i];
        if (targetId === originId) continue;  // skip origine
        var targetMarker = markers[targetId];
        if (!targetMarker) continue;

        var targetLatLng = targetMarker.getLatLng();
        var arcPoints = bezierArcPoints(originLatLng, targetLatLng, 20);

        L.polyline(arcPoints, {
            color: '#259d49',
            weight: 2,
            opacity: 0.7,
        }).addTo(assetLayerGroup);
    }
}

/**
 * Calcule les points d'une courbe de Bezier quadratique entre deux points.
 * Le point de controle est au milieu, decalé orthogonalement vers le "haut"
 * (ici en latitude) de 0.3 * distance.
 * / Computes points of a quadratic Bezier curve between two points.
 * Control point is at midpoint, offset orthogonally "upward" (latitude)
 * by 0.3 * distance.
 *
 * @param {L.LatLng} start
 * @param {L.LatLng} end
 * @param {number} segments - nombre de segments de la discretisation
 * @returns {L.LatLng[]} tableau de points sur la courbe
 */
function bezierArcPoints(start, end, segments) {
    var midLat = (start.lat + end.lat) / 2;
    var midLng = (start.lng + end.lng) / 2;
    var dLat = end.lat - start.lat;
    var dLng = end.lng - start.lng;
    var distance = Math.sqrt(dLat * dLat + dLng * dLng);

    // Vecteur orthogonal (rotation 90 degres) pour decaler le point de controle
    // / Orthogonal vector (90 deg rotation) to offset control point
    var offsetLat = -dLng * 0.3;  // ajout du -pour aller vers le nord
    var offsetLng = dLat * 0.3;

    var ctrlLat = midLat + offsetLat;
    var ctrlLng = midLng + offsetLng;

    var points = [];
    for (var i = 0; i <= segments; i++) {
        var t = i / segments;
        // Bezier quadratique : B(t) = (1-t)^2 * P0 + 2(1-t)t * P1 + t^2 * P2
        var it = 1 - t;
        var lat = it * it * start.lat + 2 * it * t * ctrlLat + t * t * end.lat;
        var lng = it * it * start.lng + 2 * it * t * ctrlLng + t * t * end.lng;
        points.push([lat, lng]);
    }
    return points;
}
```

- [ ] **Step 2: Test visuel — Style C (Temps)**

Collecter les statics, recharger. Dans la console :

```javascript
var temps = explorerData.assets.find(function(a) { return a.category === 'TIM'; });
focusOnAsset(temps.uuid);
```

Vérifier :
- Un arc courbe part du lieu origine (lespass) vers le lieu acceptant (chantefrein)
- Les 3 autres lieux sont dimmed
- Pas de polygone (c'est drawArcs, pas drawHull)

- [ ] **Step 3: Test — Asset local (1 lieu)**

```javascript
var cadeau = explorerData.assets.find(function(a) { return a.category === 'TNF'; });
focusOnAsset(cadeau.uuid);
```

Vérifier :
- Seul lespass est mis en valeur (non dimmed)
- Pas d'arc ni de polygone (1 seul lieu, pas de liaison)

- [ ] **Step 4: Commit**

```bash
git add seo/static/seo/explorer.js
git commit -m "feat(explorer): style C arcs Bezier depuis origine pour federation partielle"
```

---

### Task 9 : Légende contextuelle

**Files:**
- Modify: `seo/templates/seo/explorer.html` (ajouter le div legend)
- Modify: `seo/static/seo/explorer.js` (fonction `renderAssetLegend`)
- Modify: `seo/static/seo/explorer.css` (styles de la légende)

- [ ] **Step 1: Ajouter le DOM de la légende dans le template**

Dans `seo/templates/seo/explorer.html`, juste après `<div class="explorer-map" id="explorer-map"></div>` (à l'intérieur de `.explorer-container`) :

```html
    {# Legende contextuelle monnaie : affichee uniquement en mode focus asset #}
    {# / Contextual asset legend: visible only in asset focus mode #}
    <div class="explorer-asset-legend" id="explorer-asset-legend" hidden>
        <div class="explorer-asset-legend-content"></div>
        <button type="button" class="explorer-asset-legend-close"
                onclick="clearAssetFocus()"
                aria-label="{% translate 'Fermer' %}">&times;</button>
    </div>
```

- [ ] **Step 2: Implémenter `renderAssetLegend` dans JS**

Dans `explorer.js`, ajouter après `drawArcs` :

```javascript
/**
 * Affiche ou masque la legende contextuelle de l'asset actif.
 * Si asset est null, masque la legende.
 * / Shows or hides the active asset's contextual legend.
 * If asset is null, hides the legend.
 */
function renderAssetLegend(asset) {
    var legend = document.getElementById('explorer-asset-legend');
    if (!legend) return;

    if (!asset) {
        legend.hidden = true;
        return;
    }

    var config = ASSET_BADGE_CONFIG[asset.category] || { icon: '\u{1F4B0}', label: asset.category };
    var content = legend.querySelector('.explorer-asset-legend-content');

    var origineStr = asset.tenant_origin_name
        ? '<span class="explorer-asset-legend-origin">Origine : ' + escapeHtml(asset.tenant_origin_name) + '</span>'
        : '';
    var countStr = asset.accepting_count > 1
        ? '<span class="explorer-asset-legend-count">Partagée avec ' + (asset.accepting_count - 1) + ' autre(s) lieu(x)</span>'
        : '<span class="explorer-asset-legend-count">Utilisée localement</span>';

    content.innerHTML = ''
        + '<div class="explorer-asset-legend-title">'
            + '<span class="explorer-asset-legend-icon">' + config.icon + '</span>'
            + '<strong>' + escapeHtml(asset.name) + '</strong>'
        + '</div>'
        + '<div class="explorer-asset-legend-meta">'
            + '<span class="explorer-asset-legend-category">' + escapeHtml(config.label) + '</span>'
            + origineStr
            + countStr
        + '</div>';

    legend.hidden = false;
}
```

- [ ] **Step 3: Ajouter les styles CSS de la légende**

Dans `explorer.css`, à la fin du fichier (avant les media queries mobile) :

```css
/* ============================================================
 * Legende contextuelle asset (mode focus monnaie)
 * / Contextual asset legend (currency focus mode)
 * ============================================================ */
.explorer-asset-legend {
    position: absolute;
    bottom: 16px;
    left: 16px;
    z-index: 500;
    background: rgba(255, 255, 255, 0.95);
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    padding: 12px 16px;
    border-radius: 12px;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
    max-width: 280px;
    font-size: 12px;
    color: #333;
    display: flex;
    align-items: flex-start;
    gap: 8px;
}

.explorer-asset-legend-content {
    flex: 1;
}

.explorer-asset-legend-title {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 4px;
}

.explorer-asset-legend-icon {
    font-size: 16px;
}

.explorer-asset-legend-meta {
    display: flex;
    flex-direction: column;
    gap: 2px;
    font-size: 11px;
    color: #666;
}

.explorer-asset-legend-close {
    background: transparent;
    border: none;
    font-size: 18px;
    color: #999;
    cursor: pointer;
    padding: 0;
    width: 20px;
    height: 20px;
    line-height: 1;
}

.explorer-asset-legend-close:hover {
    color: #333;
}

/* Responsive mobile : la legende prend toute la largeur du bas */
/* / Mobile responsive: legend spans full width at bottom */
@media (max-width: 991.98px) {
    .explorer-asset-legend {
        left: 16px;
        right: 16px;
        bottom: 80px; /* au-dessus du FAB / above the FAB */
        max-width: none;
    }
}
```

- [ ] **Step 4: Test visuel**

Collecter, recharger, tester :

```javascript
focusOnAsset(explorerData.assets[0].uuid);
```

Vérifier :
- Légende apparaît en bas-gauche de la carte
- Icône + nom + catégorie + origine + "Partagée avec N lieux"
- Clic sur le × ferme le focus (reset complet)
- Responsive mobile : la légende s'étale en bas

- [ ] **Step 5: Commit**

```bash
git add seo/templates/seo/explorer.html seo/static/seo/explorer.js seo/static/seo/explorer.css
git commit -m "feat(explorer): legende contextuelle pour le mode focus monnaie"
```

---

### Task 10 : Rendre les cards monnaie cliquables → focusOnAsset

**Files:**
- Modify: `seo/static/seo/explorer.js` (fonction `buildFlatCard` pour les assets)

- [ ] **Step 1: Modifier `buildFlatCard` pour ajouter le clic sur les cards asset**

Dans `explorer.js`, localiser la fonction `buildFlatCard`. La logique actuelle exclut les assets du `focusable` (car pas de lieu parent). On change : pour les assets, on utilise `focusOnAsset(uuid)` à la place.

Remplacer la fonction entière :

```javascript
/**
 * Carte "plate" (event, membership, initiative, asset).
 * Clic = focus carte sur le lieu parent, sauf pour asset (focus carte sur la monnaie).
 * / Flat card (event, membership, initiative, asset).
 * Click = map focus on parent lieu, except for asset (map focus on the currency).
 */
function buildFlatCard(item, categoryName) {
    var cat = CATEGORIES[categoryName];
    var lieuId = escapeHtml(item.lieu_id || '');
    var assetUuid = escapeHtml(item.uuid || '');
    var desc = item.short_description
        ? '<div class="explorer-card-desc">' + escapeHtml(item.short_description) + '</div>'
        : '';

    // Action au clic selon le type / Click action by type
    var clickAttr = '';
    if (categoryName === 'asset' && assetUuid) {
        clickAttr = ' onclick="focusOnAsset(\'' + assetUuid + '\')" role="button" tabindex="0"';
    } else if (lieuId) {
        clickAttr = ' onclick="focusOnLieu(\'' + lieuId + '\')" role="button" tabindex="0"';
    }

    var lieuAttr = lieuId ? ' data-lieu-id="' + lieuId + '"' : '';
    var uuidAttr = assetUuid ? ' data-asset-uuid="' + assetUuid + '"' : '';

    return ''
        + '<div class="explorer-card"' + clickAttr + lieuAttr + uuidAttr + ' data-type="' + categoryName + '">'
            + '<div class="explorer-card-icon ' + cat.className + '">' + cat.icon + '</div>'
            + '<div class="explorer-card-body">'
                + '<div class="explorer-card-header">'
                    + '<h3 class="explorer-card-title">' + escapeHtml(item.name) + '</h3>'
                    + '<span class="explorer-badge ' + cat.className + '">' + cat.badge + '</span>'
                + '</div>'
                + '<div class="explorer-card-meta">' + escapeHtml(cat.meta(item)) + '</div>'
                + desc
            + '</div>'
        + '</div>';
}
```

- [ ] **Step 2: Mettre à jour `refreshAssetBadgeActiveState` pour inclure les cards asset**

Dans la fonction `refreshAssetBadgeActiveState` existante (Task 6), ajouter la gestion des cards `.explorer-card[data-asset-uuid]` :

```javascript
function refreshAssetBadgeActiveState() {
    // Badges monnaie sur les cards lieu / Asset badges on lieu cards
    document.querySelectorAll('.lieu-asset-badge').forEach(function(badge) {
        var badgeUuid = badge.getAttribute('data-asset-uuid');
        badge.classList.toggle('lieu-asset-badge--active', badgeUuid === activeAssetUuid);
    });
    // Cards monnaie dans la liste / Asset cards in the list
    document.querySelectorAll('.explorer-card[data-asset-uuid]').forEach(function(card) {
        var cardUuid = card.getAttribute('data-asset-uuid');
        card.classList.toggle('explorer-card--active', cardUuid === activeAssetUuid);
    });
}
```

- [ ] **Step 3: Ajouter le style CSS pour la card active**

Dans `explorer.css`, après la section badges :

```css
/* Card monnaie active dans la liste : highlight visuel. */
/* / Active currency card in the list: visual highlight. */
.explorer-card[data-type="asset"].explorer-card--active {
    border-color: #259d49;
    box-shadow: 0 0 0 2px rgba(37, 157, 73, 0.2), 0 4px 12px rgba(37, 157, 73, 0.15);
}
```

- [ ] **Step 4: Test visuel**

Collecter les statics, recharger, tester en mode desktop :
- Cliquer sur la pill "Monnaies"
- Cliquer sur la card "Fédéré TiBillet" → polygone enveloppant, tous les lieux highlighted
- La card a une bordure verte (état actif)
- Re-cliquer sur la même card → tout se reset

- [ ] **Step 5: Commit**

```bash
git add seo/static/seo/explorer.js seo/static/seo/explorer.css
git commit -m "feat(explorer): cards monnaie cliquables declenchent focusOnAsset"
```

---

## Phase 4 — Finalisation et tests E2E

### Task 11 : Test Playwright E2E

**Files:**
- Create: `tests/playwright/tests/34-explorer-assets-focus.spec.ts` (ajuster le numéro selon le dernier existant)

- [ ] **Step 1: Vérifier le dernier numéro de test existant**

Run: `ls /home/jonas/TiBillet/dev/Lespass/tests/playwright/tests/ | sort -V | tail -5`

Noter le dernier numéro (ex: 33) et utiliser le suivant (ex: 34) pour le fichier.

- [ ] **Step 2: Écrire le test Playwright**

Créer `tests/playwright/tests/34-explorer-assets-focus.spec.ts` :

```typescript
import { test, expect } from '@playwright/test';

test.describe('Explorer — Focus monnaie', () => {
    test.beforeEach(async ({ page }) => {
        await page.goto('https://www.tibillet.localhost/explorer/');
        await page.waitForLoadState('networkidle');
    });

    test('Click on TiBillet asset card draws hull polygon', async ({ page }) => {
        // Clic sur pill "Monnaies" / Click on "Monnaies" pill
        await page.getByRole('button', { name: 'Monnaies' }).click();

        // Clic sur la card "Fédéré TiBillet" / Click on "TiBillet" asset card
        const tibilletCard = page.locator('.explorer-card[data-type="asset"]').filter({ hasText: 'TiBillet' });
        await tibilletCard.click();

        // La card devient active / The card becomes active
        await expect(tibilletCard).toHaveClass(/explorer-card--active/);

        // La legende apparait / The legend appears
        await expect(page.locator('#explorer-asset-legend')).toBeVisible();
        await expect(page.locator('#explorer-asset-legend')).toContainText('TiBillet');

        // Un polygone SVG est dessine sur la carte / A SVG polygon is drawn on the map
        // Leaflet cree un <path> dans le layer pane
        const svgPaths = page.locator('.leaflet-overlay-pane svg path');
        await expect(svgPaths.first()).toBeVisible();
    });

    test('Click again on active asset card clears focus', async ({ page }) => {
        await page.getByRole('button', { name: 'Monnaies' }).click();
        const tibilletCard = page.locator('.explorer-card[data-type="asset"]').filter({ hasText: 'TiBillet' });
        await tibilletCard.click();
        await expect(tibilletCard).toHaveClass(/explorer-card--active/);

        // Clic a nouveau = toggle off
        await tibilletCard.click();
        await expect(tibilletCard).not.toHaveClass(/explorer-card--active/);
        await expect(page.locator('#explorer-asset-legend')).toBeHidden();
    });

    test('Click on asset badge on lieu card triggers focus', async ({ page }) => {
        // S'assurer qu'on est en mode "Tous"
        await page.getByRole('button', { name: 'Tous' }).click();

        // Trouver un badge monnaie sur une card lieu
        // / Find an asset badge on a lieu card
        const badge = page.locator('.lieu-asset-badge').first();
        await badge.click();

        // La legende doit apparaitre / Legend must appear
        await expect(page.locator('#explorer-asset-legend')).toBeVisible();
    });
});
```

- [ ] **Step 3: Lancer le test**

Run: `docker exec lespass_django poetry run pytest tests/e2e/test_explorer_assets_focus.py -v` (si on convertit en pytest Python)

OU pour Playwright direct :
```bash
cd /home/jonas/TiBillet/dev/Lespass/tests/playwright
yarn playwright test --project=chromium --headed --workers=1 tests/34-explorer-assets-focus.spec.ts
```

Expected: PASS sur les 3 tests.

- [ ] **Step 4: Commit**

```bash
git add tests/playwright/tests/34-explorer-assets-focus.spec.ts
git commit -m "test(explorer): E2E focus monnaie avec polygone et legende"
```

---

### Task 12 : Documentation et mise à jour du README

**Files:**
- Modify: `seo/README.md`
- Create: `A TESTER et DOCUMENTER/explorer-monnaies-federation.md`

- [ ] **Step 1: Mettre à jour `seo/README.md`**

Dans la section "Page Explorer (carte interactive)", ajouter les nouvelles fonctionnalités :

```markdown
- **Mode focus monnaie** : clic sur une card monnaie ou un badge monnaie d'un lieu active le mode focus :
  - Highlight des lieux acceptants + dim des autres (opacity 0.3)
  - Style B (polygone translucide) pour la monnaie fédérée primaire (TiBillet, `category=FED`)
  - Style C (arcs Bézier depuis origine) pour les assets fédérés partiellement
  - Légende contextuelle en bas-gauche
  - Clic à nouveau sur la même monnaie = reset (toggle)
```

Dans la section "Modele — `SEOCache`", préciser que les assets dans `AGGREGATE_ASSETS` sont enrichis avec `tenant_origin_id`, `tenant_origin_name`, `accepting_tenant_ids`, `accepting_count`, `is_federation_primary`.

Idem pour `TENANT_SUMMARY` : ajouter `accepted_asset_ids`.

- [ ] **Step 2: Créer le doc de test manuel**

Créer `A TESTER et DOCUMENTER/explorer-monnaies-federation.md` :

```markdown
# Explorer — Mode focus monnaie

## Ce qui a ete fait

Visualisation sur la carte `/explorer/` des relations entre lieux et monnaies federees.

### Modifications

| Fichier | Changement |
|---|---|
| `seo/services.py` | `get_all_assets()` enrichi, `build_tenant_config_data()` ajoute `accepted_asset_ids`, `build_explorer_data()` propage les champs |
| `seo/static/seo/explorer.js` | Mode focus asset : `focusOnAsset`, `drawHull`, `drawArcs`, `renderAssetLegend` |
| `seo/static/seo/explorer.css` | Styles badges monnaies, legende, pin dimmed, card active |
| `seo/templates/seo/explorer.html` | DOM legende contextuelle |
| `Administration/management/commands/demo_data_v2.py` | Federations demo + asset Monnaie Coeur |

## Tests a realiser

### Test 1 : Focus sur TiBillet (federation globale)
1. Aller sur `/explorer/`
2. Cliquer sur le pill "Monnaies"
3. Cliquer sur la card "Fédéré TiBillet"
4. **Verifier** : polygone vert translucide englobe tous les lieux
5. **Verifier** : la legende en bas-gauche affiche "TiBillet" + "Origine : Lespass" + "Partagée avec N lieux"
6. **Verifier** : la card est mise en valeur (bordure verte)
7. Cliquer a nouveau sur la card → tout se reset

### Test 2 : Focus sur asset federe partiellement (Temps)
1. Filtrer par "Monnaies"
2. Cliquer sur "Temps"
3. **Verifier** : arcs courbes depuis Lespass vers Chantefrein
4. **Verifier** : Le Coeur en or, La Maison des Communs, Le Réseau... sont dimmed

### Test 3 : Focus sur asset local (Cadeau)
1. Cliquer sur "Cadeau"
2. **Verifier** : uniquement Lespass est highlight, les autres sont dimmed
3. **Verifier** : pas d'arc ni de polygone (asset local a 1 lieu)

### Test 4 : Badge monnaie sur card lieu
1. Revenir sur "Tous"
2. Sur la card de "La Maison des Communs", cliquer sur le badge "🔗 Fédéré"
3. **Verifier** : meme effet que clic sur la card "TiBillet"

### Verifications base
```bash
docker exec lespass_django poetry run python manage.py shell -c "
from seo.services import build_explorer_data
data = build_explorer_data()
for a in data['assets']:
    print(a['name'], a['category'], 'origine=', a['tenant_origin_name'], 'accepte par', a['accepting_count'], 'lieu(x)')
"
```

## Compatibilite

- Le mode focus est additif : ne modifie pas les autres interactions (filtres, search, accordion lieu).
- Si `activeAssetUuid` est set, `applyFilters()` n'efface pas le focus — seul `clearAssetFocus()` le fait.
- Responsive mobile : la legende s'affiche en bas au-dessus du FAB.
```

- [ ] **Step 3: Commit**

```bash
git add seo/README.md "A TESTER et DOCUMENTER/explorer-monnaies-federation.md"
git commit -m "docs: documenter le mode focus monnaie de l'explorer"
```

---

## Self-review

### Spec coverage

- [x] Modèle de données exposé → Task 1
- [x] `accepted_asset_ids` côté tenant → Task 2
- [x] `build_explorer_data` enrichi → Task 3
- [x] Fixture enrichie (2 Federations + asset supplémentaire) → Task 4
- [x] Badges monnaies sur cards lieu → Task 5
- [x] State global + dimming → Task 6
- [x] Style B polygone hull → Task 7
- [x] Style C arcs Bézier → Task 8
- [x] Légende contextuelle → Task 9
- [x] Cards monnaie cliquables → Task 10
- [x] Tests E2E Playwright → Task 11
- [x] Documentation → Task 12

### Checks

- Noms de fonction cohérents : `focusOnAsset`, `clearAssetFocus`, `drawHull`, `drawArcs`, `drawAssetLinks`, `computeConvexHull`, `bezierArcPoints`, `renderAssetLegend`, `refreshAssetBadgeActiveState`, `refreshMapMarkersForFocus`, `applyDimming`, `findAssetByUuid`.
- Pas de placeholders `TODO` / `TBD` dans le plan.
- Commits groupés par cohérence (pas de commit unitaire par step).
- Chaque step contient le code exact nécessaire.

### Boundaries

- Phase 1 (data/cache) : complètement isolée du JS. Tests unitaires pytest.
- Phase 2 (badges) : UI simple, pas de dépendance sur Phase 3 (le clic `focusOnAsset` fallback sur un console.log).
- Phase 3 (focus mode) : ajoute les fonctions manquantes. Les badges deviennent fonctionnels.
- Phase 4 (E2E + docs) : vérification finale end-to-end.

Chaque phase laisse le système dans un état cohérent et testable.
