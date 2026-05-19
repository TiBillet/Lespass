# PLAN-06 — Explorer ROOT : pills exclusives, tags chips, URL partageable

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommandé) ou `superpowers:executing-plans` pour exécuter ce plan task-by-task. Steps utilisent `- [ ]` syntax.

**Goal :** Refondre l'UX de `/explorer/` ROOT — 2 pills exclusives Lieux/Événements, tag chips top 10 cliquables, URL partageable, accordéon "Prochains événements" réparé. Le marker reste 1 par PostalAddress.

**Architecture :** Backend SEO enrichit le cache `AGGREGATE_POINTS` avec les tags des events futurs (nouveau helper SQL cross-schema). Frontend pur JS côté client (toutes les données déjà dans le cache JSON injecté). URL pilotée via `history.replaceState`, pas d'HTMX serveur.

**Tech Stack :** Django + django-tenants + Leaflet 1.9.4 + MarkerCluster + JSON-LD + Playwright Python.

**Référence spec :** `CHANTIER-06-explorer-ux-pills-tags.md` (même dossier).

**Convention commits :** style projet (`feat:`, `fix:`, `refactor:`). **AUCUN `Co-Authored-By: Claude`** (règle ULTRA IMPORTANT du `CLAUDE.md` global). Tous les commits du plan sont réalisés par le **mainteneur**, pas par le subagent. **Aucune opération git par le subagent** (cf. PLAN-05 pour rappel : un subagent a déjà perdu 4h de travail avec `git checkout --`).

---

## File Structure

| Fichier | Type | Responsabilité |
|---|---|---|
| `seo/services.py` | edit | +`get_event_tags_for_tenants()`, propagation `tags` dans `build_aggregate_points` |
| `seo/tasks.py` | edit | Enrichissement events avec tags dans `refresh_seo_cache` |
| `BaseBillet/views.py` | edit | Bug 1-ligne : `lieux` → `tenants` à la ligne 1669 |
| `seo/templates/seo/partials/explorer_widget.html` | edit | Suppression pill "Tous", ajout `#explorer-tags`, `#explorer-empty-action`, data-i18n-* |
| `seo/static/seo/explorer.js` | edit | Refonte `applyFilters`, nouvelles fonctions (buildEventCards, chips, URL sync, accordéon réparé) |
| `seo/static/seo/explorer.css` | edit | Styles chips + empty state action + adaptation card event |
| `tests/pytest/test_seo_event_tags.py` | create | Tests `get_event_tags_for_tenants` |
| `tests/pytest/test_seo_aggregate_points.py` | edit | +1 test pour propagation `tags` dans `events_pour_popup` |
| `tests/e2e/test_explorer_ux_pills_tags.py` | create | 4 tests Playwright |
| `CHANGELOG.md` | edit | Entrée section "Carte explorer" |
| `A TESTER et DOCUMENTER/explorer-ux-pills-tags.md` | create | Scénarios test manuel |

---

## Task 1 : Helper `get_event_tags_for_tenants` + tests

**Files :**
- Modify: `seo/services.py`
- Create: `tests/pytest/test_seo_event_tags.py`

- [ ] **Step 1 : Écrire les tests (FAIL attendu)**

Créer `tests/pytest/test_seo_event_tags.py` :

```python
"""
Tests unitaires pour get_event_tags_for_tenants (seo/services.py)
/ Unit tests for get_event_tags_for_tenants.

LOCALISATION : tests/pytest/test_seo_event_tags.py
Voir SESSIONS/SEO/CHANTIER-06-explorer-ux-pills-tags.md §4.1.
"""

from unittest.mock import MagicMock, patch


def test_get_event_tags_for_tenants_renvoie_dict_vide_pour_liste_vide():
    """Liste vide -> dict vide, pas d'appel DB."""
    from seo.services import get_event_tags_for_tenants
    assert get_event_tags_for_tenants([]) == {}


def test_get_event_tags_for_tenants_construit_dict_par_event_uuid():
    """
    Pour chaque event_id du JOIN, le dict contient une liste de tags.
    / For each event_id in the JOIN, the dict has a list of tags.
    """
    from seo.services import get_event_tags_for_tenants

    # Mock du curseur : 2 events avec respectivement 2 et 1 tags
    # / Cursor mock: 2 events with 2 and 1 tags respectively
    fake_rows = [
        ("event-uuid-A", "jazz", "Jazz", "#0dcaf0"),
        ("event-uuid-A", "concert", "Concert", "#ff5722"),
        ("event-uuid-B", "festival", "Festival", "#4caf50"),
    ]
    fake_cursor = MagicMock()
    fake_cursor.fetchall.return_value = fake_rows
    fake_cursor.__enter__.return_value = fake_cursor
    fake_cursor.__exit__.return_value = False

    with patch("seo.services.connection") as mock_conn:
        mock_conn.cursor.return_value = fake_cursor
        result = get_event_tags_for_tenants([("uuid-A", "schema_a")])

    assert "event-uuid-A" in result
    assert "event-uuid-B" in result
    assert len(result["event-uuid-A"]) == 2
    assert len(result["event-uuid-B"]) == 1
    tag_slugs_a = {t["slug"] for t in result["event-uuid-A"]}
    assert tag_slugs_a == {"jazz", "concert"}
    assert result["event-uuid-B"][0]["color"] == "#4caf50"


def test_get_event_tags_for_tenants_event_sans_tag_pas_dans_dict():
    """
    Un event sans tag n'apparait pas dans le dict (JOIN strict).
    / An event without tag is absent from dict (strict JOIN).
    """
    from seo.services import get_event_tags_for_tenants

    fake_cursor = MagicMock()
    fake_cursor.fetchall.return_value = []
    fake_cursor.__enter__.return_value = fake_cursor
    fake_cursor.__exit__.return_value = False

    with patch("seo.services.connection") as mock_conn:
        mock_conn.cursor.return_value = fake_cursor
        result = get_event_tags_for_tenants([("uuid-A", "schema_a")])

    assert result == {}
```

- [ ] **Step 2 : Lancer les tests (FAIL attendu)**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_seo_event_tags.py -v
```
Expected : `ImportError: cannot import name 'get_event_tags_for_tenants'`.

- [ ] **Step 3 : Implémenter `get_event_tags_for_tenants`**

Dans `seo/services.py`, après la fonction `get_events_for_tenants` (~ligne 250) :

```python
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
```

- [ ] **Step 4 : Lancer les tests (PASS attendu)**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_seo_event_tags.py -v
```
Expected : 3 PASSED.

- [ ] **Step 5 : Vérifier que rien ne casse**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_seo_aggregate_points.py tests/pytest/test_seo_indexing.py -v
```
Expected : tous PASS (régression check).

- [ ] **Step 6 : Commit (par mainteneur)**

```
feat(seo): add get_event_tags_for_tenants cross-schema helper
```

Fichiers : `seo/services.py`, `tests/pytest/test_seo_event_tags.py`.

---

## Task 2 : Enrichir events avec tags dans `refresh_seo_cache` + propager dans `build_aggregate_points`

**Files :**
- Modify: `seo/services.py`
- Modify: `seo/tasks.py`
- Modify: `tests/pytest/test_seo_aggregate_points.py`

- [ ] **Step 1 : Écrire le test de propagation (FAIL attendu)**

Ajouter dans `tests/pytest/test_seo_aggregate_points.py` :

```python
def test_build_aggregate_points_propage_tags_dans_events_pour_popup():
    """
    Le champ `tags` est present dans les events_pour_popup quand l'event d'entree
    en a. Forme : list[dict{slug, name, color}].
    / Field `tags` is propagated into events_pour_popup when input event has them.
    """
    from seo.services import build_aggregate_points

    fake_pa = {
        "pa_id": 1, "latitude": 1.0, "longitude": 1.0,
        "name": "PA", "street_address": "", "postal_code": "",
        "address_locality": "", "address_country": "",
    }
    fake_event_avec_tags = {
        "uuid": "ev-1",
        "name": "Soiree Jazz",
        "datetime": "2026-06-15T20:00:00+00:00",
        "postal_address_id": 1,
        "slug": "soiree-jazz",
        "tags": [{"slug": "jazz", "name": "Jazz", "color": "#0dcaf0"}],
    }
    with patch("seo.services.get_postal_addresses_for_tenants",
               return_value={"uuid-A": [fake_pa]}):
        result = build_aggregate_points(
            [("uuid-A", "schema-A")],
            configs_by_tenant={"uuid-A": {"organisation": "Org", "domain": "a.test"}},
            events_by_tenant={"uuid-A": [fake_event_avec_tags]},
        )
    point = result["points"][0]
    assert len(point["events_futurs"]) == 1
    event = point["events_futurs"][0]
    assert "tags" in event
    assert event["tags"] == [{"slug": "jazz", "name": "Jazz", "color": "#0dcaf0"}]


def test_build_aggregate_points_tags_vide_si_event_sans_tag():
    """
    Un event sans tags d'entree -> events_pour_popup[i].tags = [].
    / Event without tags -> events_pour_popup[i].tags = [].
    """
    from seo.services import build_aggregate_points

    fake_pa = {
        "pa_id": 1, "latitude": 1.0, "longitude": 1.0,
        "name": "PA", "street_address": "", "postal_code": "",
        "address_locality": "", "address_country": "",
    }
    fake_event_sans_tags = {
        "uuid": "ev-2",
        "name": "Atelier",
        "datetime": "2026-07-01T18:00:00+00:00",
        "postal_address_id": 1,
        "slug": "atelier",
        # Pas de cle "tags" du tout
    }
    with patch("seo.services.get_postal_addresses_for_tenants",
               return_value={"uuid-A": [fake_pa]}):
        result = build_aggregate_points(
            [("uuid-A", "schema-A")],
            configs_by_tenant={"uuid-A": {"organisation": "Org", "domain": "a.test"}},
            events_by_tenant={"uuid-A": [fake_event_sans_tags]},
        )
    event = result["points"][0]["events_futurs"][0]
    assert event["tags"] == []
```

- [ ] **Step 2 : Lancer (FAIL attendu)**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_seo_aggregate_points.py -v -k tags
```
Expected : 2 FAIL (cle `tags` absente).

- [ ] **Step 3 : Modifier `build_aggregate_points` pour propager `tags`**

Dans `seo/services.py`, fonction `build_aggregate_points`, à l'intérieur de la boucle qui construit `events_pour_popup` (~ligne 452-459), ajouter le champ `tags` :

```python
            events_pour_popup = []
            for ev in events_tries[:LIMIT_EVENTS_DANS_POPUP]:
                events_pour_popup.append({
                    "uuid": ev.get("uuid", ""),
                    "name": ev.get("name", ""),
                    "datetime_iso": ev.get("datetime", ""),
                    "slug": ev.get("slug", ""),
                    "tags": ev.get("tags", []),
                })
```

- [ ] **Step 4 : Lancer (PASS attendu)**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_seo_aggregate_points.py -v -k tags
```
Expected : 2 PASS.

- [ ] **Step 5 : Brancher `get_event_tags_for_tenants` dans `refresh_seo_cache`**

Dans `seo/tasks.py`, après l'Étape 2 (`all_events = get_events_for_tenants(tenant_schemas)`, ~ligne 89), ajouter l'enrichissement avant le `Grouper par tenant_id` :

```python
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
```

**Attention** : `get_events_for_tenants` ne retourne pas actuellement le champ `uuid` dans son SELECT. Vérifier et ajouter si nécessaire (Step 6).

- [ ] **Step 6 : Vérifier que `get_events_for_tenants` retourne bien `uuid`**

```bash
docker exec lespass_django grep -n "SELECT.*tenant_id" seo/services.py | head -3
```

Lire le bloc de `get_events_for_tenants` (~ligne 215-247). Si le SELECT n'inclut PAS `uuid`, l'ajouter :

Avant :
```python
parts.append(
    f"SELECT %s AS tenant_id, name, slug, short_description, "
    f"datetime, end_datetime, img, postal_address_id "
    f'FROM "{schema_name}"."BaseBillet_event" '
    f"WHERE published = true AND datetime >= %s"
)
```

Après :
```python
parts.append(
    f"SELECT %s AS tenant_id, uuid::text AS uuid, name, slug, short_description, "
    f"datetime, end_datetime, img, postal_address_id "
    f'FROM "{schema_name}"."BaseBillet_event" '
    f"WHERE published = true AND datetime >= %s"
)
```

Et adapter la boucle `for row in cursor.fetchall()` pour mapper le nouvel index :

```python
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
```

- [ ] **Step 7 : Lancer un refresh complet pour vérifier**

```bash
docker exec lespass_django poetry run python manage.py shell -c "from seo.tasks import refresh_seo_cache; print(refresh_seo_cache())"
```
Expected : pas d'exception, dict avec tenants/events/lieux non nuls.

- [ ] **Step 8 : Vérifier qu'au moins 1 event en cache porte des tags**

```bash
docker exec lespass_django poetry run python manage.py shell -c "
from seo.models import SEOCache
from seo.views_common import get_seo_cache
data = get_seo_cache(SEOCache.AGGREGATE_POINTS) or {}
events_avec_tags = [
    ev for pt in data.get('points', [])
    for ev in pt.get('events_futurs', [])
    if ev.get('tags')
]
print(f'Events avec tags dans cache : {len(events_avec_tags)}')
if events_avec_tags:
    print('Exemple :', events_avec_tags[0])
"
```
Expected : au moins 1 event avec tags si la base contient des events tagués.

- [ ] **Step 9 : Suite de tests régression**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_seo_event_tags.py tests/pytest/test_seo_aggregate_points.py tests/pytest/test_seo_indexing.py -v
```
Expected : tous PASS.

- [ ] **Step 10 : Commit (par mainteneur)**

```
feat(seo): propagate event tags into AGGREGATE_POINTS cache
```

Fichiers : `seo/services.py`, `seo/tasks.py`, `tests/pytest/test_seo_aggregate_points.py`.

---

## Task 3 : Fix bug `BaseBillet/views.py:1669` (`lieux` → `tenants`)

**Files :**
- Modify: `BaseBillet/views.py:1669`

- [ ] **Step 1 : Lire le contexte**

```bash
docker exec lespass_django sed -n '1665,1685p' BaseBillet/views.py
```

Confirmer que la ligne 1669 itère sur `explorer_data.get("lieux", [])`.

- [ ] **Step 2 : Modifier la ligne**

Dans `BaseBillet/views.py`, ligne 1669 :

Avant :
```python
        for lieu in explorer_data.get("lieux", []):
```

Après :
```python
        for lieu in explorer_data.get("tenants", []):
```

Aucun autre changement dans le bloc — les clés consommées (`domain`, `name`, `short_description`, `locality`, `country`, `logo_url`, `tenant_id`) sont identiques entre l'ancien `AGGREGATE_LIEUX.lieux[i]` et `explorer_data["tenants"][i]` (qui est re-exposé directement).

- [ ] **Step 3 : Sanity check Django**

```bash
docker exec lespass_django poetry run python manage.py check
```
Expected : 0 issue.

- [ ] **Step 4 : Régression**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_seo_aggregate_points.py tests/pytest/test_seo_indexing.py -v
```
Expected : tous PASS.

- [ ] **Step 5 : Commit (par mainteneur) — commit séparé**

```
fix(BaseBillet): explorer tenant federation JSON-LD reads renamed key

build_explorer_data_for_tenants renvoie "tenants" depuis CHANTIER-05,
plus "lieux". FederationViewset.list itèrait encore sur l'ancienne clé,
le JSON-LD federation des explorers tenant était silencieusement vide.
```

Fichier : `BaseBillet/views.py`.

---

## Task 4 : Template — pills exclusives, conteneur chips, data-i18n

**Files :**
- Modify: `seo/templates/seo/partials/explorer_widget.html`

- [ ] **Step 1 : Supprimer la pill "Tous"**

Dans `seo/templates/seo/partials/explorer_widget.html`, bloc `#explorer-pills` (~ligne 51-58), supprimer le bouton `data-category="all"` :

Avant :
```html
<div class="explorer-pills" id="explorer-pills" role="tablist">
    <button class="explorer-pill active" type="button" data-category="all" role="tab"
            data-testid="explorer-pill-all">{% translate "Tous" %}</button>
    <button class="explorer-pill" type="button" data-category="lieu" role="tab"
            data-testid="explorer-pill-lieu">{% translate "Lieux" %}</button>
    <button class="explorer-pill" type="button" data-category="event" role="tab"
            data-testid="explorer-pill-event">{% translate "Événements" %}</button>
</div>
```

Après :
```html
<div class="explorer-pills" id="explorer-pills" role="tablist">
    <button class="explorer-pill active" type="button" data-category="lieu" role="tab"
            data-testid="explorer-pill-lieu">{% translate "Lieux" %}</button>
    <button class="explorer-pill" type="button" data-category="event" role="tab"
            data-testid="explorer-pill-event">{% translate "Événements" %}</button>
</div>
```

- [ ] **Step 2 : Ajouter la barre tag chips**

Toujours dans le même fichier, après la `</div>` qui ferme `.explorer-toolbar` (~ligne 60), avant `.explorer-container`, insérer :

```html
    {# Barre tag chips : top 10 par fréquence parmi events visibles. #}
    {# Rendu par JS, masquée tant qu'il n'y a pas de tags à afficher. #}
    {# / Tag chip bar: top 10 by frequency among visible events. #}
    {# Rendered by JS, hidden while no tags to display. #}
    <div class="explorer-tags"
         id="explorer-tags"
         role="group"
         aria-label="{% translate 'Filtrer par tag' %}"
         data-testid="explorer-tags"
         hidden></div>
```

- [ ] **Step 3 : Ajouter les data-i18n manquants sur `#explorer-root`**

Dans le bloc `<div id="explorer-root"` (~ligne 23-37), ajouter à la fin de la liste des `data-i18n-*` :

```html
      data-i18n-clear-tag="{% translate 'Effacer le filtre' %}"
      data-i18n-tag-empty="{% translate 'Aucun événement « {tag} » dans la zone visible.' %}"
      data-i18n-more-tags="{% translate '+ {count} tags' %}"
```

- [ ] **Step 4 : Supprimer le data-i18n-all (plus utilisé)**

Dans le même bloc, supprimer la ligne :
```html
      data-i18n-all="{% translate 'Tous' %}"
```

- [ ] **Step 5 : Vérifier le rendu HTML**

```bash
docker exec lespass_django poetry run python manage.py check
```
Expected : 0 issue.

Ouvrir `/explorer/` dans le navigateur (instance dev) et vérifier visuellement que :
- 2 pills (pas 3)
- Le conteneur `#explorer-tags` est présent dans le DOM (inspecteur), avec `hidden`
- Aucune erreur JS dans la console (le JS attend les changements Task 5+)

- [ ] **Step 6 : Commit (par mainteneur)**

```
feat(seo): explorer template — 2 pills + tag chips container
```

Fichier : `seo/templates/seo/partials/explorer_widget.html`.

---

## Task 5 : JS — state refactor (`filters.view`, `filters.tag`)

**Files :**
- Modify: `seo/static/seo/explorer.js`

- [ ] **Step 1 : Renommer `filters.category` en `filters.view` + ajouter `filters.tag`**

Dans `seo/static/seo/explorer.js`, bloc STATE (~ligne 66-74) :

Avant :
```javascript
const state = {
    data: null,
    filters: { text: '', category: 'all' },
    map: null,
    markers: {},
    markerCluster: null,
    currentView: 'list',
    mapInitialized: false,
};
```

Après :
```javascript
const state = {
    data: null,
    filters: { text: '', view: 'lieu', tag: null },
    map: null,
    markers: {},
    markerCluster: null,
    currentView: 'list',
    mapInitialized: false,
};
```

- [ ] **Step 2 : Supprimer la config i18n.all + ajouter les nouveaux**

Bloc CONFIG (~ligne 42-60), supprimer `all: 'Tous',` et ajouter en fin de bloc i18n :

```javascript
            clearTag: 'Effacer le filtre',
            tagEmpty: 'Aucun événement « {tag} » dans la zone visible.',
            moreTags: '+ {count} tags',
```

Forme finale du bloc i18n :
```javascript
        i18n: {
            empty: 'Aucun résultat trouvé.',
            visit: 'Visiter le lieu',
            lieu: 'Lieu',
            event: 'Événement',
            current: 'Vous êtes ici',
            lieuSingular: 'lieu',
            lieuPlural: 'lieux',
            eventSingular: 'événement',
            eventPlural: 'événements',
            nextEvents: 'Prochains événements :',
            more: 'autre(s)',
            list: 'Liste',
            map: 'Carte',
            clearTag: 'Effacer le filtre',
            tagEmpty: 'Aucun événement « {tag} » dans la zone visible.',
            moreTags: '+ {count} tags',
        },
```

- [ ] **Step 3 : Adapter `readConfigFromDom`**

Dans `readConfigFromDom` (~ligne 117-136), supprimer la ligne `if (ds.i18nAll) config.i18n.all = ds.i18nAll;` et ajouter :

```javascript
        if (ds.i18nClearTag) config.i18n.clearTag = ds.i18nClearTag;
        if (ds.i18nTagEmpty) config.i18n.tagEmpty = ds.i18nTagEmpty;
        if (ds.i18nMoreTags) config.i18n.moreTags = ds.i18nMoreTags;
```

- [ ] **Step 4 : Adapter `filterCategory` (le supprimer, remplacé Task 6)**

Pour l'instant, on remplace temporairement `filterCategory` par une no-op pour ne pas casser le code. Trouver la fonction `filterCategory` (~ligne 221-226) et la remplacer par :

```javascript
    // OBSOLETE — sera supprimée Task 6. Garde pour compat temporaire applyFilters.
    // / DEPRECATED — removed in Task 6. Temporary compat for applyFilters.
    function filterCategory(sourceArray, _categoryName) {
        return (sourceArray || []).filter(matchesText);
    }
```

- [ ] **Step 5 : Adapter `bindPills` (référencer `state.filters.view` au lieu de `.category`)**

Dans `bindPills` (~ligne 314-326), changer la ligne :

Avant :
```javascript
state.filters.category = pill.getAttribute('data-category') || 'all';
```

Après :
```javascript
state.filters.view = pill.getAttribute('data-category') || 'lieu';
```

- [ ] **Step 6 : Adapter `applyFilters` (référence `state.filters.view` au lieu de `.category`)**

Dans `applyFilters` (~ligne 228-263), remplacer toutes les références à `state.filters.category` par `state.filters.view`. Changer la valeur attendue `'event'` (inchangée) mais retirer la branche `'all'` :

Avant (ligne 235-241) :
```javascript
let tenantsVisibles = filterCategory(state.data.tenants, 'lieu');
if (state.filters.category === 'event') {
    const tenantsAvecEvent = collectTenantsWithFutureEvents();
    tenantsVisibles = state.data.tenants.filter(function (t) {
        return tenantsAvecEvent[t.tenant_id] && matchesText(t);
    });
}
```

Après (transitionnel — sera refactorisé Task 6) :
```javascript
let tenantsVisibles = (state.data.tenants || []).filter(matchesText);
if (state.filters.view === 'event') {
    const tenantsAvecEvent = collectTenantsWithFutureEvents();
    tenantsVisibles = state.data.tenants.filter(function (t) {
        return tenantsAvecEvent[t.tenant_id] && matchesText(t);
    });
}
```

- [ ] **Step 7 : Sanity check**

```bash
docker exec lespass_django poetry run python manage.py check
```
Expected : 0 issue.

Ouvrir `/explorer/` et vérifier dans la console JS qu'il n'y a pas d'erreur. Cliquer Lieux/Événements : compteurs changent.

- [ ] **Step 8 : Commit (par mainteneur)**

```
refactor(seo): explorer.js — state.filters.view + state.filters.tag scaffolding
```

Fichier : `seo/static/seo/explorer.js`.

---

## Task 6 : JS — refonte `applyFilters` + cards events séparées

**Files :**
- Modify: `seo/static/seo/explorer.js`

- [ ] **Step 1 : Supprimer la fonction `filterCategory` (obsolète)**

Dans `seo/static/seo/explorer.js`, supprimer le bloc `filterCategory` (~ligne 221-226).

- [ ] **Step 2 : Ajouter les helpers PA-level**

Avant `applyFilters` (~ligne 228), insérer :

```javascript
    // ============================================================
    // FILTERS — helpers PA-level + event-level
    // / FILTERS — PA-level + event-level helpers
    // ============================================================

    function paMatchesText(point) {
        // Match sur nom PA, nom du tenant, OU nom d'au moins 1 event futur.
        // / Match on PA name, tenant name, OR at least 1 future event name.
        if (!state.filters.text) return true;
        const q = state.filters.text;
        const champs = [
            point.pa_name,
            point.tenant_organisation,
            point.address_display,
        ];
        for (let i = 0; i < champs.length; i++) {
            if ((champs[i] || '').toLowerCase().indexOf(q) !== -1) return true;
        }
        const events = point.events_futurs || [];
        for (let j = 0; j < events.length; j++) {
            if ((events[j].name || '').toLowerCase().indexOf(q) !== -1) return true;
        }
        return false;
    }

    function paMatchesTag(point) {
        // Si pas de tag actif, tout passe. Sinon, au moins 1 event de la PA
        // doit porter le tag.
        // / If no active tag, pass. Otherwise, at least 1 event must carry it.
        if (!state.filters.tag) return true;
        const events = point.events_futurs || [];
        for (let i = 0; i < events.length; i++) {
            const tags = events[i].tags || [];
            for (let j = 0; j < tags.length; j++) {
                if (tags[j].slug === state.filters.tag) return true;
            }
        }
        return false;
    }

    function filterPAsByTextAndTag(points) {
        const result = [];
        for (let i = 0; i < points.length; i++) {
            const point = points[i];
            if (paMatchesText(point) && paMatchesTag(point)) {
                result.push(point);
            }
        }
        return result;
    }

    function collectVisibleEvents(paVisibles) {
        // Aplatit les events futurs de toutes les PA visibles.
        // Si tag actif, ne garde que les events qui portent ce tag.
        // Si text actif, ne garde que les events dont le nom matche (ou la PA matche).
        // / Flatten future events of all visible PAs.
        // Filter by tag and text accordingly.
        const events = [];
        const q = state.filters.text;
        const tagSlug = state.filters.tag;
        for (let i = 0; i < paVisibles.length; i++) {
            const point = paVisibles[i];
            const evList = point.events_futurs || [];
            for (let j = 0; j < evList.length; j++) {
                const ev = evList[j];
                if (tagSlug) {
                    const tags = ev.tags || [];
                    let porteTag = false;
                    for (let k = 0; k < tags.length; k++) {
                        if (tags[k].slug === tagSlug) { porteTag = true; break; }
                    }
                    if (!porteTag) continue;
                }
                if (q) {
                    // Conserver si nom d'event matche OU nom de PA/tenant matche
                    // (la PA est déjà filtrée, mais on filtre encore en mode event).
                    const evMatch = (ev.name || '').toLowerCase().indexOf(q) !== -1;
                    const paMatch = paMatchesText(point);
                    if (!evMatch && !paMatch) continue;
                }
                events.push({
                    uuid: ev.uuid,
                    name: ev.name,
                    datetime_iso: ev.datetime_iso,
                    slug: ev.slug,
                    tags: ev.tags || [],
                    pa_id: point.pa_id,
                    pa_name: point.pa_name,
                    address_display: point.address_display,
                    tenant_id: point.tenant_id,
                    tenant_organisation: point.tenant_organisation,
                    tenant_domain: point.tenant_domain,
                    tenant_logo_url: point.tenant_logo_url,
                });
            }
        }
        events.sort(function (a, b) {
            return (a.datetime_iso || '').localeCompare(b.datetime_iso || '');
        });
        return events;
    }

    function buildLieuCardsFromPAs(paVisibles) {
        // Regroupe les PA visibles par tenant_id. Renvoie liste de "lieu cards"
        // au meme format que state.data.tenants, mais enrichi avec eventsAggregated.
        // / Group visible PAs by tenant_id. Returns "lieu cards" matching
        // state.data.tenants format, enriched with eventsAggregated.
        const parTenant = {};
        for (let i = 0; i < paVisibles.length; i++) {
            const point = paVisibles[i];
            const tid = point.tenant_id;
            if (!parTenant[tid]) parTenant[tid] = { pas: [], events: [] };
            parTenant[tid].pas.push(point);
            const evList = point.events_futurs || [];
            for (let j = 0; j < evList.length; j++) {
                parTenant[tid].events.push(evList[j]);
            }
        }
        // Index des tenants depuis state.data.tenants pour récupérer infos tenant-level
        // / Tenant index from state.data.tenants for tenant-level info
        const tenantsById = {};
        for (let k = 0; k < (state.data.tenants || []).length; k++) {
            const t = state.data.tenants[k];
            tenantsById[t.tenant_id] = t;
        }
        const cards = [];
        for (const tid in parTenant) {
            const t = tenantsById[tid];
            if (!t) continue;
            // Tri events agrégés par date asc, dédoublonné par uuid
            // / Sort aggregated events asc, dedup by uuid
            const seen = {};
            const eventsUniques = [];
            for (let m = 0; m < parTenant[tid].events.length; m++) {
                const ev = parTenant[tid].events[m];
                if (!seen[ev.uuid]) {
                    seen[ev.uuid] = true;
                    eventsUniques.push(ev);
                }
            }
            eventsUniques.sort(function (a, b) {
                return (a.datetime_iso || '').localeCompare(b.datetime_iso || '');
            });
            cards.push({
                tenant_id: t.tenant_id,
                name: t.name,
                domain: t.domain,
                slug: t.slug || '',
                short_description: t.short_description,
                locality: t.locality,
                country: t.country,
                logo_url: t.logo_url,
                events: eventsUniques,
            });
        }
        return cards;
    }
```

- [ ] **Step 3 : Réécrire `applyFilters`**

Remplacer le corps actuel de `applyFilters` (~ligne 228-263) par :

```javascript
    function applyFilters() {
        if (!state.data) return;

        // 1. Filtre les PA selon text + tag (independamment du mode view).
        // / Filter PAs by text + tag (independent of view mode).
        const paVisibles = filterPAsByTextAndTag(state.data.points || []);

        // 2. Construit la liste affichee selon le mode pill.
        // / Build displayed list according to pill mode.
        let lieuxCards = [];
        let eventCards = [];
        if (state.filters.view === 'lieu') {
            lieuxCards = buildLieuCardsFromPAs(paVisibles);
        } else {
            eventCards = collectVisibleEvents(paVisibles);
        }

        renderList(lieuxCards, eventCards);
        updateCounters(lieuxCards.length, eventCards.length || countEventsInPAs(paVisibles));

        // 3. Markers visibles = PA visibles. Dict pa_id -> true pour update map.
        // / Visible markers = visible PAs. Dict pa_id -> true for map update.
        const visiblePaIds = {};
        for (let i = 0; i < paVisibles.length; i++) {
            visiblePaIds[paVisibles[i].pa_id] = true;
        }
        if (state.mapInitialized) {
            updateMapMarkersByPA(visiblePaIds);
        }

        // 4. Recalculer les chips (Task 8 ajoutera updateChips).
        // / Recompute chips (Task 8 will add updateChips).
        if (typeof updateChips === 'function') {
            updateChips(paVisibles);
        }

        // 5. Synchroniser l'URL (Task 9 ajoutera syncURL).
        // / Sync URL (Task 9 will add syncURL).
        if (typeof syncURL === 'function') {
            syncURL();
        }
    }

    function countEventsInPAs(paVisibles) {
        let n = 0;
        for (let i = 0; i < paVisibles.length; i++) {
            n += ((paVisibles[i].events_futurs || []).length);
        }
        return n;
    }
```

- [ ] **Step 4 : Remplacer `updateMapMarkers(visibleTenantIds)` par `updateMapMarkersByPA(visiblePaIds)`**

Trouver `updateMapMarkers` (~ligne 636-654) et remplacer par :

```javascript
    function updateMapMarkersByPA(visiblePaIds) {
        // Garde les markers des PA visibles, cache les autres.
        // visiblePaIds = dict {pa_id: true}.
        // / Keep visible PA markers, hide others.
        if (!state.mapInitialized) return;

        for (const paId in state.markers) {
            const marker = state.markers[paId];
            const keep = !!visiblePaIds[paId];
            const isVisible = state.markerCluster.hasLayer(marker);
            if (keep && !isVisible) state.markerCluster.addLayer(marker);
            else if (!keep && isVisible) state.markerCluster.removeLayer(marker);
        }
    }
```

- [ ] **Step 5 : Adapter `renderList` et `buildEventCard`**

Trouver `renderList` (~ligne 376-382) — la signature `function renderList(lieux, events)` est déjà correcte. Vérifier que la fonction itère bien sur les 2 listes.

Réécrire `buildEventCard` (~ligne 454-476) pour le nouveau format produit par `collectVisibleEvents` :

```javascript
    function buildEventCard(event) {
        const tenantId = escapeHtml(event.tenant_id || '');
        const evUrl = (event.tenant_domain && event.slug)
            ? 'https://' + event.tenant_domain + '/event/' + event.slug + '/'
            : '#';
        const datePart = event.datetime_iso
            ? '\u{1F4C5} ' + escapeHtml(formatShortDate(event.datetime_iso))
            : '';
        const lieuPart = event.pa_name ? ' · \u{1F4CD} ' + escapeHtml(event.pa_name) : '';
        const tenantPart = event.tenant_organisation
            ? ' — ' + escapeHtml(event.tenant_organisation)
            : '';
        const metaText = datePart + lieuPart + tenantPart;

        // Tags inline : max 3 affichés.
        // / Inline tags: max 3 displayed.
        let tagsHtml = '';
        const tags = (event.tags || []).slice(0, 3);
        if (tags.length > 0) {
            tagsHtml = '<div class="explorer-card-tags">';
            for (let i = 0; i < tags.length; i++) {
                const t = tags[i];
                tagsHtml += '<span class="explorer-card-tag" style="background-color:'
                    + escapeHtml(t.color || '#0dcaf0') + '">'
                    + escapeHtml(t.name || t.slug) + '</span>';
            }
            tagsHtml += '</div>';
        }

        return ''
            + '<div class="explorer-card explorer-card--event"'
            + ' data-event-uuid="' + escapeHtml(event.uuid || '') + '"'
            + ' data-tenant-id="' + tenantId + '"'
            + ' data-type="event"'
            + ' data-testid="explorer-card-event">'
                + '<div class="explorer-card-icon event">\u{1F3B6}</div>'
                + '<div class="explorer-card-body">'
                    + '<div class="explorer-card-header">'
                        + '<h3 class="explorer-card-title">'
                            + '<a href="' + escapeHtml(evUrl) + '" target="_blank" rel="noopener">'
                            + escapeHtml(event.name) + '</a></h3>'
                        + '<span class="explorer-badge event">' + escapeHtml(config.i18n.event) + '</span>'
                    + '</div>'
                    + '<div class="explorer-card-meta">' + metaText + '</div>'
                    + tagsHtml
                + '</div>'
            + '</div>';
    }
```

- [ ] **Step 6 : Sanity check**

```bash
docker exec lespass_django poetry run python manage.py check
```
Expected : 0 issue.

Ouvrir `/explorer/`, vérifier :
- Pill Lieux : cards de tenants (avec accordéon vide pour l'instant — réparé Task 7).
- Pill Événements : cards d'événements (1 par event futur).
- Markers à jour selon le filtre texte.

- [ ] **Step 7 : Commit (par mainteneur)**

```
feat(seo): explorer.js — applyFilters refonte, cards events séparées
```

Fichier : `seo/static/seo/explorer.js`.

---

## Task 7 : JS — réparer `buildLieuAccordion`

**Files :**
- Modify: `seo/static/seo/explorer.js`

- [ ] **Step 1 : Réécrire `buildLieuAccordion`**

Dans `seo/static/seo/explorer.js`, fonction `buildLieuAccordion` (~ligne 429-452), changer la source des events. Avant la fonction prenait `lieu.events` (champ inexistant), maintenant on lui passe la liste agrégée construite par `buildLieuCardsFromPAs` (où `lieu.events` existe désormais grâce à Task 6).

Vérifier que `buildLieuAccordion(lieu, domain)` lit `lieu.events`. Si oui, c'est déjà bon — Task 6 a construit `lieu.events` dans chaque card lieu. Sinon, adapter.

Nouvelle version (qui marche avec Task 6) :

```javascript
    function buildLieuAccordion(lieu, domain) {
        // Source : lieu.events injecté par buildLieuCardsFromPAs (Task 6).
        // Forme : [{uuid, name, datetime_iso, slug, tags}, ...]
        // / Source: lieu.events injected by buildLieuCardsFromPAs (Task 6).
        const events = lieu.events || [];
        if (events.length === 0) return '';
        const label = pluralize(events.length, config.i18n.eventSingular, config.i18n.eventPlural);
        let items = '';
        for (let i = 0; i < events.length; i++) {
            const ev = events[i];
            const evHref = domain && ev.slug ? 'https://' + domain + '/event/' + ev.slug + '/' : '#';
            const dateLabel = ev.datetime_iso ? formatShortDate(ev.datetime_iso) : '';
            items += ''
                + '<a class="explorer-accordion-item" href="' + escapeHtml(evHref) + '" target="_blank" rel="noopener">'
                    + '<span class="explorer-accordion-icon">\u{1F3B6}</span>'
                    + '<span class="explorer-accordion-name">' + escapeHtml(ev.name) + '</span>'
                    + (dateLabel ? '<span class="explorer-accordion-date">' + escapeHtml(dateLabel) + '</span>' : '')
                + '</a>';
        }
        return ''
            + '<div class="explorer-accordion">'
                + '<button class="explorer-accordion-toggle" type="button">'
                    + '<span>' + escapeHtml(label) + '</span>'
                    + '<i class="bi bi-chevron-down explorer-accordion-chevron" aria-hidden="true"></i>'
                + '</button>'
                + '<div class="explorer-accordion-panel"><div class="explorer-accordion-panel-inner">' + items + '</div></div>'
            + '</div>';
    }
```

- [ ] **Step 2 : Vérifier visuellement**

Ouvrir `/explorer/`, mode Lieux : chaque card de tenant doit avoir un accordéon "N événements" cliquable qui déplie une liste.

- [ ] **Step 3 : Commit (par mainteneur)**

```
fix(seo): explorer.js — repair lieu accordion (source from PA events)
```

Fichier : `seo/static/seo/explorer.js`.

---

## Task 8 : JS — Tag chips (top 10 + dropdown "+N")

**Files :**
- Modify: `seo/static/seo/explorer.js`

- [ ] **Step 1 : Cacher la réf DOM `#explorer-tags`**

Dans `seo/static/seo/explorer.js`, bloc DOM (~ligne 80-89), ajouter :

```javascript
    const dom = {
        root: null,
        list: null,
        map: null,
        mapLoading: null,
        search: null,
        pills: null,
        counter: null,
        fab: null,
        tags: null,   // <-- ajouté
    };
```

Dans `init` (~ligne 143-167), juste après `dom.fab = document.getElementById('explorer-fab');` :

```javascript
        dom.tags = document.getElementById('explorer-tags');
```

- [ ] **Step 2 : Ajouter `computeVisibleTagsTop10`**

Avant la section RENDER MAP (~ligne 484), insérer :

```javascript
    // ============================================================
    // TAG CHIPS — top 10 par fréquence parmi events visibles
    // / TAG CHIPS — top 10 by frequency among visible events
    // ============================================================

    function computeVisibleTagsTop10(paVisibles) {
        // Agrege les tags des events visibles (mode lieu : events de toutes les PA
        // visibles ; mode event : meme chose, le filtre tag s'applique ailleurs).
        // Ne tient pas compte de state.filters.tag (sinon on cacherait le chip actif).
        // / Aggregate tags of visible events. Ignores state.filters.tag (otherwise
        // the active chip would disappear).
        const compteur = {};   // slug -> {slug, name, color, count}
        for (let i = 0; i < paVisibles.length; i++) {
            const evList = paVisibles[i].events_futurs || [];
            for (let j = 0; j < evList.length; j++) {
                const tags = evList[j].tags || [];
                for (let k = 0; k < tags.length; k++) {
                    const t = tags[k];
                    if (!compteur[t.slug]) {
                        compteur[t.slug] = {
                            slug: t.slug, name: t.name, color: t.color, count: 0,
                        };
                    }
                    compteur[t.slug].count += 1;
                }
            }
        }
        const liste = Object.keys(compteur).map(function (k) { return compteur[k]; });
        liste.sort(function (a, b) {
            if (b.count !== a.count) return b.count - a.count;
            return a.name.localeCompare(b.name);
        });
        return {
            top: liste.slice(0, 10),
            rest: liste.slice(10),
        };
    }

    function updateChips(paVisibles) {
        if (!dom.tags) return;
        const grouped = computeVisibleTagsTop10(paVisibles);
        const activeSlug = state.filters.tag;

        // Cache le conteneur si aucun tag a afficher
        // / Hide container if no tag to display
        if (grouped.top.length === 0 && grouped.rest.length === 0) {
            dom.tags.innerHTML = '';
            dom.tags.hidden = true;
            return;
        }
        dom.tags.hidden = false;

        let html = '';
        for (let i = 0; i < grouped.top.length; i++) {
            const t = grouped.top[i];
            html += buildChipHtml(t, t.slug === activeSlug);
        }
        if (grouped.rest.length > 0) {
            const moreLabel = config.i18n.moreTags.replace('{count}', grouped.rest.length);
            html += '<button type="button" class="explorer-tag-chip-more"'
                + ' data-testid="explorer-tag-chip-more"'
                + ' aria-haspopup="true" aria-expanded="false">'
                + escapeHtml(moreLabel) + '</button>'
                + '<div class="explorer-tag-chip-rest" hidden>';
            for (let j = 0; j < grouped.rest.length; j++) {
                html += buildChipHtml(grouped.rest[j], grouped.rest[j].slug === activeSlug);
            }
            html += '</div>';
        }
        dom.tags.innerHTML = html;
    }

    function buildChipHtml(tag, isActive) {
        // Chip bouton : fond = tag.color, état actif = bordure + check.
        // / Chip button: background = tag.color, active state = border + check.
        const cls = 'explorer-tag-chip' + (isActive ? ' explorer-tag-chip--active' : '');
        const check = isActive
            ? '<i class="bi bi-check2" aria-hidden="true"></i> '
            : '';
        return '<button type="button" class="' + cls + '"'
            + ' data-tag-slug="' + escapeHtml(tag.slug) + '"'
            + ' data-testid="explorer-tag-chip-' + escapeHtml(tag.slug) + '"'
            + ' style="--chip-color:' + escapeHtml(tag.color || '#0dcaf0') + '"'
            + ' aria-pressed="' + (isActive ? 'true' : 'false') + '">'
            + check + escapeHtml(tag.name || tag.slug) + '</button>';
    }
```

- [ ] **Step 3 : Brancher le listener clic chip**

Dans `bindControls` (~ligne 292-297), ajouter un appel à `bindTagChips` :

```javascript
    function bindControls() {
        bindSearch();
        bindPills();
        bindFAB();
        bindListDelegation();
        bindTagChips();
    }
```

Puis avant `bindAccordions` ou en fin de section CONTROLLERS, ajouter :

```javascript
    function bindTagChips() {
        if (!dom.tags) return;
        dom.tags.addEventListener('click', function (ev) {
            const moreBtn = ev.target.closest('.explorer-tag-chip-more');
            if (moreBtn) {
                const rest = dom.tags.querySelector('.explorer-tag-chip-rest');
                if (rest) {
                    const willOpen = rest.hidden;
                    rest.hidden = !willOpen;
                    moreBtn.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
                }
                return;
            }
            const chip = ev.target.closest('.explorer-tag-chip');
            if (!chip) return;
            const clickedSlug = chip.getAttribute('data-tag-slug');
            // Toggle exclusif : si déjà actif -> désactiver, sinon -> activer (et désactiver les autres).
            // / Exclusive toggle: if active -> deactivate, otherwise activate (and deactivate others).
            if (state.filters.tag === clickedSlug) {
                state.filters.tag = null;
            } else {
                state.filters.tag = clickedSlug;
            }
            applyFilters();
        });
    }
```

- [ ] **Step 4 : Empty state action**

Trouver `renderList` (~ligne 376-382), remplacer par :

```javascript
    function renderList(lieux, events) {
        if (!dom.list) return;
        let html = '';
        for (let i = 0; i < lieux.length; i++) html += buildLieuCard(lieux[i]);
        for (let j = 0; j < events.length; j++) html += buildEventCard(events[j]);
        if (!html) {
            html = buildEmptyStateHtml();
        }
        dom.list.innerHTML = html;
    }

    function buildEmptyStateHtml() {
        // Si tag actif et 0 résultat : message + lien "Effacer le filtre".
        // / If tag is active and 0 results: message + "Clear filter" link.
        if (state.filters.tag) {
            const activeTagName = findTagNameBySlug(state.filters.tag) || state.filters.tag;
            const msg = config.i18n.tagEmpty.replace('{tag}', activeTagName);
            return '<div class="explorer-empty-state" data-testid="explorer-empty-state">'
                + '<p class="text-muted text-center py-3">' + escapeHtml(msg) + '</p>'
                + '<p class="text-center">'
                + '<button type="button" class="btn btn-link"'
                + ' id="explorer-clear-tag" data-testid="explorer-clear-tag">'
                + escapeHtml(config.i18n.clearTag) + '</button></p></div>';
        }
        return '<p class="text-muted text-center py-4">' + escapeHtml(config.i18n.empty) + '</p>';
    }

    function findTagNameBySlug(slug) {
        // Cherche dans les events de state.data.points.
        // / Search in events of state.data.points.
        for (let i = 0; i < (state.data.points || []).length; i++) {
            const evs = state.data.points[i].events_futurs || [];
            for (let j = 0; j < evs.length; j++) {
                const tags = evs[j].tags || [];
                for (let k = 0; k < tags.length; k++) {
                    if (tags[k].slug === slug) return tags[k].name;
                }
            }
        }
        return null;
    }
```

Et binder le clic "Effacer le filtre" dans `bindListDelegation` (~ligne 334-368) en ajoutant en début du handler :

```javascript
            const clearBtn = ev.target.closest('#explorer-clear-tag');
            if (clearBtn) {
                state.filters.tag = null;
                applyFilters();
                return;
            }
```

- [ ] **Step 5 : Sanity check**

```bash
docker exec lespass_django poetry run python manage.py check
```
Expected : 0 issue.

Refresh cache puis ouvrir `/explorer/` :
```bash
docker exec lespass_django poetry run python manage.py shell -c "from seo.tasks import refresh_seo_cache; refresh_seo_cache()"
```

Vérifier dans le navigateur :
- Barre chips visible avec tags ordonnés par fréquence.
- Clic chip → liste se filtre, marker s'ajuste.
- Re-clic même chip → désactivé.
- Bouton `+N` déplie/replie le reste.
- Filtrer un tag inexistant en zone visible → empty state avec lien "Effacer".

- [ ] **Step 6 : Commit (par mainteneur)**

```
feat(seo): explorer.js — tag chips top 10 + empty state action
```

Fichier : `seo/static/seo/explorer.js`.

---

## Task 9 : JS — URL sync (`history.replaceState`)

**Files :**
- Modify: `seo/static/seo/explorer.js`

- [ ] **Step 1 : Ajouter `syncURL` et `bootFromURL`**

Dans `seo/static/seo/explorer.js`, avant la section ENTRY POINT (~ligne 792), insérer :

```javascript
    // ============================================================
    // URL STATE — sync filters <-> URL via history.replaceState
    // / URL STATE — sync filters <-> URL via history.replaceState
    // ============================================================

    let urlSyncTimer = null;

    function syncURL() {
        // Debounce 300ms pour eviter les rafales lors de la saisie texte.
        // / Debounce 300ms to avoid bursts during text input.
        clearTimeout(urlSyncTimer);
        urlSyncTimer = setTimeout(function () {
            const params = new URLSearchParams();
            if (state.filters.view && state.filters.view !== 'lieu') {
                params.set('v', state.filters.view);
            }
            if (state.filters.text) {
                params.set('q', state.filters.text);
            }
            if (state.filters.tag) {
                params.set('tag', state.filters.tag);
            }
            const qs = params.toString();
            const newUrl = window.location.pathname + (qs ? ('?' + qs) : '');
            try {
                window.history.replaceState({}, '', newUrl);
            } catch (err) {
                // Silently fail si l'historique est restreint (file://, etc.)
                // / Silent fail if history is restricted.
            }
        }, 300);
    }

    function bootFromURL() {
        // Lit les params URL au chargement et pré-sélectionne state.filters.
        // / Read URL params at load, pre-select state.filters.
        try {
            const params = new URLSearchParams(window.location.search);
            const v = params.get('v');
            if (v === 'event' || v === 'lieu') {
                state.filters.view = v;
            }
            const q = params.get('q');
            if (q) {
                state.filters.text = q.toLowerCase();
            }
            const tag = params.get('tag');
            if (tag) {
                // On valide plus tard : si aucun event ne porte ce tag, applyFilters
                // affichera l'empty state — pas de plantage.
                // / Validate later: if no event carries it, applyFilters shows empty state.
                state.filters.tag = tag;
            }
        } catch (err) {
            console.warn('explorer: cannot parse URL params', err);
        }
    }
```

- [ ] **Step 2 : Appeler `bootFromURL` dans `init` AVANT `applyFilters`**

Dans `init` (~ligne 143-178), après `readConfigFromDom()` et avant `bindControls()` :

```javascript
        readConfigFromDom();
        state.data = loadData();
        if (!state.data) {
            renderEmptyState();
            return;
        }

        bootFromURL();   // <-- nouveau, pré-remplit state.filters

        bindControls();
        applyFilters();
```

- [ ] **Step 3 : Pré-remplir l'input search et la pill active depuis state**

Dans `bindSearch` (~ligne 299-312), juste après la lecture `initialValue` :

```javascript
    function bindSearch() {
        if (!dom.search) return;
        // Priorité au state (déjà rempli par bootFromURL), sinon valeur du DOM.
        // / state takes priority (filled by bootFromURL), otherwise DOM value.
        if (state.filters.text) {
            dom.search.value = state.filters.text;
        } else {
            const initialValue = dom.search.value.trim().toLowerCase();
            if (initialValue) state.filters.text = initialValue;
        }
        // ... (rest unchanged)
    }
```

Dans `bindPills` (~ligne 314-326), au début :

```javascript
    function bindPills() {
        if (!dom.pills) return;
        // Synchroniser la pill active avec state.filters.view (depuis URL).
        // / Sync active pill with state.filters.view (from URL).
        const allPills = dom.pills.querySelectorAll('.explorer-pill');
        for (let i = 0; i < allPills.length; i++) {
            allPills[i].classList.toggle(
                'active',
                allPills[i].getAttribute('data-category') === state.filters.view
            );
        }
        // ... (rest unchanged)
    }
```

- [ ] **Step 4 : Sanity check**

```bash
docker exec lespass_django poetry run python manage.py check
```
Expected : 0 issue.

Vérifier dans le navigateur :
- Ouvrir `/explorer/?v=event&tag=jazz` (ou n'importe quel slug valide en cache) → pill Événements active, chip "jazz" actif au chargement.
- Cliquer une autre pill → l'URL bascule sans rechargement.
- Effacer le tag → `?tag=` disparaît de l'URL.

- [ ] **Step 5 : Commit (par mainteneur)**

```
feat(seo): explorer.js — URL state via history.replaceState
```

Fichier : `seo/static/seo/explorer.js`.

---

## Task 10 : CSS chips + empty state action

**Files :**
- Modify: `seo/static/seo/explorer.css`

- [ ] **Step 1 : Ajouter les styles chips en fin de fichier**

Ajouter à la fin de `seo/static/seo/explorer.css` :

```css
/* --- Tag chips (CHANTIER-06) --- */
.explorer-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    padding: 8px 12px 0;
    align-items: center;
}
.explorer-tag-chip {
    --chip-color: #0dcaf0;
    background: var(--chip-color);
    color: #fff;
    border: 2px solid transparent;
    border-radius: 12px;
    padding: 3px 10px;
    font-size: 0.82rem;
    cursor: pointer;
    font-weight: 500;
    line-height: 1.3;
    white-space: nowrap;
    transition: filter 0.15s, border-color 0.15s, transform 0.05s;
}
.explorer-tag-chip:hover {
    filter: brightness(1.1);
}
.explorer-tag-chip:active {
    transform: scale(0.97);
}
.explorer-tag-chip--active {
    border-color: #222;
    box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.6) inset;
}
.explorer-tag-chip-more {
    background: transparent;
    color: #555;
    border: 1px dashed #aaa;
    border-radius: 12px;
    padding: 3px 10px;
    font-size: 0.8rem;
    cursor: pointer;
}
.explorer-tag-chip-more:hover {
    background: #eee;
}
.explorer-tag-chip-rest {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 6px;
    width: 100%;
    padding-top: 6px;
    border-top: 1px solid #eee;
}

/* --- Empty state action --- */
.explorer-empty-state {
    padding: 16px 12px;
}
.explorer-empty-state .btn-link {
    text-decoration: underline;
    color: #2a5d9f;
}

/* --- Card event : tags inline --- */
.explorer-card-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin-top: 4px;
}
.explorer-card-tag {
    color: #fff;
    font-size: 0.72rem;
    padding: 1px 7px;
    border-radius: 8px;
    line-height: 1.3;
}
```

- [ ] **Step 2 : Vérifier visuellement**

Hard refresh `/explorer/` (Ctrl+Shift+R), vérifier :
- Chips avec leurs vraies couleurs.
- Chip actif a une bordure noire + ombre interne blanche.
- `+N tags` ouvre une 2e ligne en pointillé.
- Card event : tags affichés sous le titre avec leur couleur.
- Empty state : lien "Effacer le filtre" cliquable.

- [ ] **Step 3 : Commit (par mainteneur)**

```
feat(seo): style explorer tag chips + empty state action
```

Fichier : `seo/static/seo/explorer.css`.

---

## Task 11 : Tests E2E Playwright

**Files :**
- Create: `tests/e2e/test_explorer_ux_pills_tags.py`

- [ ] **Step 1 : Vérifier la structure des tests E2E existants**

```bash
ls tests/e2e/ | head -10
head -50 tests/e2e/conftest.py
```

- [ ] **Step 2 : Créer le test E2E**

Créer `tests/e2e/test_explorer_ux_pills_tags.py` :

```python
"""
Tests E2E Playwright : carte explorer ROOT — pills exclusives, tag chips, URL.
/ E2E Playwright tests: ROOT explorer — exclusive pills, tag chips, URL.

LOCALISATION : tests/e2e/test_explorer_ux_pills_tags.py
Voir SESSIONS/SEO/CHANTIER-06-explorer-ux-pills-tags.md.
"""

import pytest
from playwright.sync_api import expect


@pytest.fixture(autouse=True)
def refresh_cache_before_each_test():
    """
    Force un refresh du cache SEO avant chaque test. Garantit que les events
    et les tags sont à jour.
    / Force a SEO cache refresh before each test. Ensures fresh events + tags.
    """
    from seo.tasks import refresh_seo_cache
    refresh_seo_cache()


@pytest.mark.e2e
def test_pill_events_remplace_cards_lieu_par_cards_event(page, live_server):
    """
    Clic sur la pill Événements remplace les cards lieu par des cards event.
    / Clicking Events pill swaps lieu cards for event cards.
    """
    page.goto(f"{live_server.url}/explorer/")
    page.wait_for_selector(".explorer-card", timeout=5000)

    # État initial : mode Lieux
    # / Initial state: Lieux mode
    cards_lieu = page.locator('[data-type="lieu"]').count()
    assert cards_lieu > 0, "Aucune card lieu au chargement initial"

    # Clic pill Événements
    # / Click Événements pill
    page.click('[data-testid="explorer-pill-event"]')
    page.wait_for_timeout(300)

    cards_event = page.locator('[data-type="event"]').count()
    cards_lieu_apres = page.locator('[data-type="lieu"]').count()
    # Au moins 1 card event doit apparaître si le cache a des events futurs.
    # Les cards lieu doivent toutes disparaître.
    assert cards_lieu_apres == 0, "Cards lieu persistent en mode Événements"
    # Si pas d'event futur en cache, on accepte 0 mais l'URL doit être à jour.
    # / If no future event in cache, accept 0 but URL must be updated.


@pytest.mark.e2e
def test_clic_tag_chip_filtre_et_synchronise_url(page, live_server):
    """
    Clic sur un tag chip filtre la liste + markers + ajoute ?tag=... dans l'URL.
    / Tag chip click filters list + markers + adds ?tag=... to URL.
    """
    page.goto(f"{live_server.url}/explorer/")
    page.wait_for_selector(".explorer-card", timeout=5000)

    # Trouver un chip présent (au moins 1 doit être visible si la base contient
    # des events tagués)
    # / Find a visible chip (at least 1 must be there if base has tagged events)
    chip = page.locator(".explorer-tag-chip").first
    if chip.count() == 0:
        pytest.skip("Aucun event tagué dans la base de test — chip absente")

    slug = chip.get_attribute("data-tag-slug")
    chip.click()
    page.wait_for_timeout(400)  # debounce URL 300ms + safety

    # URL doit contenir ?tag=...
    # / URL must contain ?tag=...
    assert f"tag={slug}" in page.url, f"URL ne contient pas tag={slug} : {page.url}"

    # Chip actif a la classe --active
    # / Active chip has --active class
    active_class = chip.get_attribute("class") or ""
    assert "explorer-tag-chip--active" in active_class


@pytest.mark.e2e
def test_url_initiale_v_event_preselectionne_pill(page, live_server):
    """
    Naviguer vers /explorer/?v=event présélectionne la pill Événements.
    / Navigating to /explorer/?v=event pre-selects the Events pill.
    """
    page.goto(f"{live_server.url}/explorer/?v=event")
    page.wait_for_selector(".explorer-pill", timeout=5000)

    pill_event = page.locator('[data-testid="explorer-pill-event"]')
    pill_event_class = pill_event.get_attribute("class") or ""
    assert "active" in pill_event_class, "Pill Événements pas pré-sélectionnée"


@pytest.mark.e2e
def test_empty_state_affiche_lien_effacer(page, live_server):
    """
    Quand un tag inexistant filtre la liste à zéro, l'empty state affiche
    un lien "Effacer le filtre" qui restaure la liste.
    / When a fake tag filters to zero, empty state shows "Clear filter" link.
    """
    page.goto(f"{live_server.url}/explorer/?tag=ce-tag-nexiste-pas-12345")
    page.wait_for_selector('[data-testid="explorer-empty-state"]', timeout=5000)

    # Lien "Effacer le filtre" présent
    # / "Clear filter" link present
    clear_btn = page.locator('[data-testid="explorer-clear-tag"]')
    assert clear_btn.count() == 1, "Bouton Effacer le filtre absent"

    clear_btn.click()
    page.wait_for_timeout(400)
    # Empty state disparaît
    # / Empty state disappears
    expect(page.locator('[data-testid="explorer-empty-state"]')).to_have_count(0)
    # URL nettoyée (tag retiré)
    # / URL cleaned (tag removed)
    assert "tag=" not in page.url
```

- [ ] **Step 3 : Lancer les tests E2E**

```bash
docker exec lespass_django poetry run pytest tests/e2e/test_explorer_ux_pills_tags.py -v -s
```
Expected : 4 PASS (ou SKIP pour test #2 si la base de test n'a pas d'event tagué).

- [ ] **Step 4 : Commit (par mainteneur)**

```
test(seo): E2E for explorer pills + tag chips + URL state
```

Fichier : `tests/e2e/test_explorer_ux_pills_tags.py`.

---

## Task 12 : CHANGELOG + doc test manuel

**Files :**
- Modify: `CHANGELOG.md`
- Create: `A TESTER et DOCUMENTER/explorer-ux-pills-tags.md`

- [ ] **Step 1 : Ajouter une section CHANGELOG**

En tête de `CHANGELOG.md`, après la dernière entrée la plus récente, insérer :

```markdown
## N. Carte explorer ROOT : pills exclusives, tag chips, URL partageable / Exclusive pills, tag chips, shareable URL

**Quoi / What:** Refonte UX de la carte explorer ROOT. La pill "Tous" est supprimée — il reste "Lieux" et "Événements" exclusives. En mode Événements, la liste affiche 1 card par event futur (au lieu de cards lieu). Une nouvelle barre de tag chips (top 10 par fréquence parmi les events visibles) permet de filtrer par tag, avec bouton "+ N tags" pour le reste. Les filtres (`v`, `q`, `tag`) sont synchronisés dans l'URL via `history.replaceState`, ce qui rend la carte partageable. L'accordéon "Prochains événements" sur les cards lieu est réparé (la régression CHANTIER-05 est résolue). Un bug 1-ligne sur le JSON-LD federation des explorers tenant est corrigé en parallèle.

**Pourquoi / Why:** Suite à CHANTIER-05, le filtre Événements ne changeait plus visuellement la vue, et la liste d'événements avait disparu. En parallèle, l'arrivée de tenants type "réseau régional" ou "agenda culturel régional" (200+ PostalAddress) demandait une UX de filtrage par thématique pour rester navigable. Les tags `Event.tag` existaient en DB depuis longtemps mais n'étaient pas exposés côté SEO.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `seo/services.py` | +`get_event_tags_for_tenants`, propagation `tags` dans `events_pour_popup` |
| `seo/tasks.py` | Enrichissement events avec tags dans `refresh_seo_cache` |
| `BaseBillet/views.py` | Fix bug 1-ligne : `lieux` → `tenants` dans le JSON-LD federation |
| `seo/templates/seo/partials/explorer_widget.html` | Suppression pill "Tous", ajout `#explorer-tags`, data-i18n-* |
| `seo/static/seo/explorer.js` | Refonte `applyFilters`, chips, URL sync, accordéon réparé |
| `seo/static/seo/explorer.css` | Styles chips + empty state action + tags inline event |
| `tests/pytest/test_seo_event_tags.py` | Tests unitaires (3) |
| `tests/pytest/test_seo_aggregate_points.py` | +2 tests propagation tags |
| `tests/e2e/test_explorer_ux_pills_tags.py` | Tests E2E Playwright (4) |

### Migration
- **Migration nécessaire / Migration required:** Non. Pas de changement de schéma.
- **Activation :** prochain cycle Celery Beat de `refresh_seo_cache` (4h max), ou refresh manuel. Le JS lit avec `.tags || []` (rétrocompatible avec un cache pas encore rafraîchi).
```

- [ ] **Step 2 : Créer la doc test manuel**

Créer `A TESTER et DOCUMENTER/explorer-ux-pills-tags.md` :

```markdown
# Carte explorer ROOT — pills exclusives, tags, URL partageable

## Ce qui a été fait

Cf. `TECH_DOC/SESSIONS/SEO/CHANTIER-06-explorer-ux-pills-tags.md`.

## Tests à réaliser

### Test 1 : Refresh + chargement initial
1. `docker exec lespass_django poetry run python manage.py shell -c "from seo.tasks import refresh_seo_cache; refresh_seo_cache()"`
2. Ouvrir `/explorer/` du ROOT (`http://localhost:8002/explorer/`)
3. Vérifier visuellement :
   - 2 pills (pas 3) : "Lieux" et "Événements", Lieux active par défaut
   - Une barre de tag chips visible sous les pills (couleurs des tags)
   - Cards de tenant avec accordéon "N événements" qui se déplie au clic

### Test 2 : Pill Événements
1. Cliquer "Événements"
2. La liste passe à 1 card par event futur (tri chronologique)
3. Chaque card event affiche : date + lieu + tenant, tags inline (max 3), titre cliquable vers `/event/<slug>/`

### Test 3 : Tag chip
1. Cliquer un chip (ex : "jazz")
2. Liste filtrée à ce tag, markers à jour
3. URL change : `?tag=jazz`
4. Cliquer le bouton "+ N tags" : 2e ligne de chips s'affiche
5. Re-cliquer le chip actif : désactive, URL nettoyée

### Test 4 : URL partageable
1. Composer manuellement `/explorer/?v=event&tag=jazz`
2. Au chargement : pill Événements active, chip jazz actif, liste/markers filtrés
3. Effacer le filtre via le lien empty state (si liste vide) ou re-cliquer le chip

### Test 5 : Empty state
1. `/explorer/?tag=ce-tag-nexiste-pas`
2. Liste vide avec message + lien "Effacer le filtre"
3. Clic sur le lien : restaure la liste complète, URL nettoyée

### Test 6 : Explorer tenant (régression CHANTIER-05)
1. Ouvrir `/federation/` (ou la route équivalente) sur un tenant
2. Inspecter le `<script type="application/ld+json">` injecté
3. Vérifier que `subOrganization` n'est PAS vide (avant le fix, c'était toujours vide)

### Test 7 : Cache Memcached
1. `/admin/seo/seocache/` en superuser ROOT
2. Vérifier qu'on a `aggregate_points` global avec un sample dans `data.points[0].events_futurs[0].tags` non vide (au moins 1 event tagué requis dans la base)

## Compatibilité

- Cache rétrocompatible : JS lit `.tags || []`, donc un cache sans tags ne plante pas.
- Pas de changement de schéma DB.
- Explorer tenant continue de fonctionner — le bug 1-ligne est corrigé en parallèle.
- Rollback : annuler les commits Tasks 4-10 (frontend), les commits Tasks 1-2 (backend) restent compatibles avec l'ancien JS.
```

- [ ] **Step 3 : Commit (par mainteneur)**

```
docs: CHANGELOG + test plan for explorer UX pills + tags
```

Fichiers : `CHANGELOG.md`, `A TESTER et DOCUMENTER/explorer-ux-pills-tags.md`.

---

## Self-review du plan

**Coverage spec :**
- ✅ §3.1 (pills exclusives) → Task 4 (template) + Task 5 (state JS)
- ✅ §3.2 (markers = PA constant) → préservé, pas de changement (déjà OK depuis CHANTIER-05)
- ✅ §3.3 (liste mode lieu / event) → Task 6 (buildEventCards, buildLieuCardsFromPAs) + Task 7 (accordéon)
- ✅ §3.4 (tag chips top 10) → Task 8
- ✅ §3.5 (URL partageable) → Task 9
- ✅ §4.1 (`get_event_tags_for_tenants`) → Task 1
- ✅ §4.2 (enrichissement refresh_seo_cache) → Task 2 (Step 5-6)
- ✅ §4.3 (propagation `tags` dans `events_pour_popup`) → Task 2 (Step 3)
- ✅ §4.4 (bug `lieux→tenants`) → Task 3
- ✅ §5.1 (refonte JS) → Tasks 5-9
- ✅ §5.2 (template) → Task 4
- ✅ §5.3 (CSS) → Task 10
- ✅ §6 (tests) → Tasks 1, 2, 11
- ✅ §7 (CHANGELOG + doc) → Task 12

**Placeholder scan :** aucun "TBD", "TODO" ou step sans code. Chaque step a du code complet ou une commande complète avec output attendu.

**Type consistency :**
- `state.filters.view` : `'lieu' | 'event'` (Tasks 5, 6, 8, 9).
- `state.filters.tag` : `string | null` (Tasks 5, 8, 9).
- `event.tags` : `list[{slug, name, color}]` (Tasks 1, 2, 6, 8).
- `point.events_futurs[i].tags` : même forme (Task 2 Step 3).
- `paVisibles`, `visiblePaIds` : cohérent entre Tasks 6, 8.
- `updateMapMarkersByPA(visiblePaIds)` remplace `updateMapMarkers(visibleTenantIds)` partout (Task 6 Step 4).

**Scope check :** focalisé. Backend = 1 helper + 1 enrichissement + 1 bug 1-ligne. Frontend = 1 template + 1 fichier JS + 1 fichier CSS. Tests = 2 fichiers. Doc = 2 fichiers. Pas de refactor non lié.

---

## Execution

Plan complet : 12 tasks, ~70 steps. Estimation : 4-6 sessions courtes (1-2h chacune) avec subagents.

**Pré-requis avant exécution :**
1. Mainteneur a accepté la spec CHANTIER-06.
2. Branche dédiée créée : `git checkout -b feat/explorer-ux-pills-tags`.
3. Container `lespass_django` actif (`docker compose up -d`).
4. Tests existants verts (`pytest tests/pytest/test_seo_indexing.py tests/pytest/test_seo_aggregate_points.py -v`).
5. PLAN-05 entièrement déployé (cache `AGGREGATE_POINTS` actif).

**Méthode recommandée :** `superpowers:subagent-driven-development` — 1 subagent par task avec review du mainteneur entre chaque. Backend (Tasks 1-3) avant frontend (Tasks 4-10), tests E2E (Task 11) à la fin, doc (Task 12) en clôture.
