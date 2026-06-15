# CHANTIER-05 — Carte explorer ROOT : 1 marker par PostalAddress

**Statut :** Spec valide, prete pour writing-plans
**Date :** 2026-05-17
**Priorite :** Moyen (visualisation enrichie suite import geoloc)
**App impactee :** `seo/`

---

## 1. Contexte

Apres l'import de 327 PostalAddress geolocalisees via l'outil `nominatim-review/` (143 CREATE + 184 UPDATE + 37 PROMOTE en adresse principale), la base Lespass contient maintenant beaucoup d'adresses precises. Mais la carte `/explorer/` du tenant ROOT n'affiche **qu'un seul marker par tenant**, positionne sur `Configuration.postal_address` (l'adresse principale).

Probleme : un tenant comme l'**Universite Populaire Villeurbanne** a 24 PostalAddress (24 lieux d'evenements differents a Lyon/Villeurbanne). Sur la carte ROOT, il n'apparait qu'a une seule position. Les 23 autres lieux sont invisibles.

**Demande utilisateur :** afficher 1 marker par PostalAddress active, avec un popup riche listant les events qui s'y deroulent.

## 2. Decisions (deja prises en brainstorming)

| Question | Decision |
|---|---|
| Nombre de markers par PA | **1 seul marker par PA**, popup riche listant tout |
| Quelles PA inclure | **Toutes les PA d'un tenant "vivant"** (>=1 event futur publie OU >=1 produit publie) |
| Strategie cache | **Nouveau `AGGREGATE_POINTS` dedie** (zero impact sur `AGGREGATE_LIEUX` et les autres vues) |
| Limite events dans popup | **Top 5 events futurs** + lien "voir tous (N)" si plus |

## 3. Architecture

### 3.1 Nouveau cache `SEOCache.AGGREGATE_POINTS`

Ajoute a `seo/models.py:SEOCache` :

```python
AGGREGATE_POINTS = "aggregate_points"
# dans CACHE_TYPE_CHOICES :
(AGGREGATE_POINTS, _("Aggregated PostalAddress points for explorer map")),
```

Structure stockee (1 entree globale, `tenant=None`) :

```json
{
  "points": [
    {
      "pa_id": 42,
      "latitude": -21.067,
      "longitude": 55.225,
      "pa_name": "La Raffinerie",
      "address_display": "86 Avenue de Bourbon, 97434 L'Hermitage Les Bains",
      "is_main_address": true,
      "tenant_id": "uuid",
      "tenant_schema": "raffinerie",
      "tenant_organisation": "La Raffinerie",
      "tenant_domain": "raffinerie.tibillet.org",
      "tenant_logo_url": "https://.../logo_med.jpg",
      "events_futurs": [
        {
          "uuid": "e1...",
          "name": "Concert X",
          "datetime_iso": "2026-05-24T20:00:00+00:00",
          "url": "https://raffinerie.tibillet.org/event/concert-x/"
        }
      ],
      "events_futurs_count_total": 1
    }
  ]
}
```

`address_display` est construit cote serveur (concatenation `street_address`, `postal_code`, `address_locality`, espaces propres, pas de virgules orphelines).

### 3.2 Service / Task

**Nouveau dans `seo/services.py`** :

```python
def get_postal_addresses_for_tenants(tenant_schemas):
    """
    Renvoie toutes les PostalAddress avec coords des tenants donnes,
    indexees par (tenant_id, pa_id), en 1 requete par tenant
    (tenant_context obligatoire).
    """
    # ...

def build_aggregate_points(tenant_schemas, configs_by_tenant,
                            events_by_tenant):
    """
    Construit la liste de points pour AGGREGATE_POINTS.
    Pour chaque tenant vivant : prend ses PA avec coords + regroupe
    ses events futurs par pa_id.
    """
    # ...
```

**Modification de `seo/tasks.py:refresh_seo_cache`** : ajout d'une etape 6 a la fin (apres l'ecriture de AGGREGATE_LIEUX) :

```python
# Etape 6 : AGGREGATE_POINTS (1 entree par PA active)
points_data = build_aggregate_points(
    tenant_schemas, configs_by_tenant, events_by_tenant
)
SEOCache.objects.update_or_create(
    cache_type=SEOCache.AGGREGATE_POINTS,
    tenant=None,
    defaults={"data": points_data},
)
set_memcached_l1(SEOCache.AGGREGATE_POINTS, None, points_data)
```

**Filtre "tenant vivant"** : reuse `tenant_counts` deja calcule a l'etape 1 (cf. `seo/tasks.py:58-83`). Un tenant est vivant si `event_count > 0 OR product_count > 0`.

### 3.3 Service explorer

**Modification de `seo/services.py:build_explorer_data_for_tenants`** :

Avant :
```python
def build_explorer_data_for_tenants(tenant_uuids):
    # Lit AGGREGATE_LIEUX (1 entree par tenant) et AGGREGATE_EVENTS,
    # filtre, retourne {"lieux": [...], "events": [...]}.
```

Apres :
```python
def build_explorer_data_for_tenants(tenant_uuids):
    """
    Lit AGGREGATE_POINTS (1 entree par PA active), filtre par tenant_id,
    retourne {"points": [...]}.
    """
    points_data = get_seo_cache(SEOCache.AGGREGATE_POINTS) or {}
    raw_points = points_data.get("points", [])
    uuids_set = set(tenant_uuids)
    points_filtres = [p for p in raw_points if p["tenant_id"] in uuids_set]
    return {"points": points_filtres}
```

**Compat retro** : `build_explorer_data()` continue de fonctionner (appelle `build_explorer_data_for_tenants` avec tous les tenant_ids). La signature de retour change : `lieux/events` → `points`. Tous les consommateurs de cette fonction sont dans `seo/` et seront adaptes en meme temps.

### 3.4 Frontend

**`seo/views.py:explorer`** : passe `explorer_data["points"]` au template (au lieu de `lieux`/`events`).

**`seo/templates/seo/explorer.html`** :
- Le `<script>` qui injecte le JSON-LD `ItemList` doit iterer sur `points` au lieu de `lieux` (chaque point = un `Place` schema.org).
- Le container `<div id="explorer-map" data-explorer-data="..."></div>` recoit le nouveau JSON.

**`seo/static/seo/explorer.js`** (changements localises) :

```js
// Avant : 1 marker par lieu (= 1 par tenant)
// Apres : 1 marker par point (= 1 par PA active)
state.points = explorerData.points || [];
state.points.forEach(point => {
    const lat = parseFloat(point.latitude);
    const lng = parseFloat(point.longitude);
    if (isNaN(lat) || isNaN(lng)) return;
    const marker = L.marker([lat, lng], { title: point.pa_name });
    marker.bindPopup(construirePopup(point));
    state.markerCluster.addLayer(marker);
});

function construirePopup(point) {
    // Construit le HTML du popup (voir mockup section 4)
    // Top 5 events + lien "voir tous (N)" si events_futurs_count_total > 5
}
```

La logique du panneau lateral (liste des lieux a gauche, si presente) doit aussi etre adaptee : 1 entree par point au lieu de par lieu, regroupable visuellement par `tenant_organisation` si besoin.

## 4. Mockup popup

```
+-----------------------------------+
| LA RAFFINERIE                     | <- pa_name (gras, h6)
| 86 Avenue de Bourbon              | <- address_display
| 97434 L'Hermitage Les Bains       |
|                                   |
| [logo] La Raffinerie -->          | <- lien tenant_domain
|                                   |   (logo_url miniature)
| Evenements futurs (3) :           | <- si events_futurs_count_total > 0
|  - Concert X — 24 mai 20h         | <- liens vers event.url
|  - Atelier Y — 1 juin             |
|  - Festival Z — 15 juin           |
|                                   |
|  (si > 5 : "Voir tous (N) -->")   |
+-----------------------------------+
```

Si pas d'events futurs → on omet la section "Événements futurs" entierement.

## 5. Fichiers modifies

| Fichier | Type | Changement |
|---|---|---|
| `seo/models.py` | edit | +1 constante `AGGREGATE_POINTS` dans `SEOCache` |
| `seo/services.py` | edit | +2 fonctions (`get_postal_addresses_for_tenants`, `build_aggregate_points`) ; refacto `build_explorer_data_for_tenants` |
| `seo/tasks.py` | edit | +Etape 6 dans `refresh_seo_cache` (appel `build_aggregate_points` + ecriture cache) |
| `seo/views.py` | edit | Passage de `explorer_data["points"]` au template (au lieu de `lieux`/`events`) |
| `seo/templates/seo/explorer.html` | edit | JSON-LD ItemList itere sur `points`, container HTML inchange |
| `seo/static/seo/explorer.js` | edit | Boucle sur `points`, construction du popup riche, panel lateral revu |
| `seo/static/seo/explorer.css` | edit | Styles pour le popup riche (logo miniature, liste events) |

## 6. Tests

**Tests pytest DB-only** (a creer dans `seo/tests/test_aggregate_points.py`) :

| Test | Verifie |
|---|---|
| `test_aggregate_points_inclut_pa_d_un_tenant_vivant_avec_event_futur` | Cas nominal : 1 PA, 1 event futur, le point apparait avec l'event |
| `test_aggregate_points_inclut_toutes_les_pa_d_un_tenant_vivant` | Tenant a 3 PA, toutes apparaissent (pas seulement la principale) |
| `test_aggregate_points_exclut_pa_sans_coords` | PA sans lat/lng skip |
| `test_aggregate_points_exclut_pa_de_tenant_mort` | Tenant sans event futur ni produit publie : aucune PA |
| `test_aggregate_points_events_limites_a_5_avec_count_total` | PA avec 12 events futurs : popup contient 5 + `events_futurs_count_total=12` |
| `test_aggregate_points_groupage_events_par_pa` | Tenant a 2 PA + 5 events repartis : chaque event va dans le bon point |
| `test_build_explorer_data_for_tenants_filtre_par_uuid` | Filtre tenant_uuids fonctionne |

**Tests E2E Playwright** (1 ajout dans `tests/e2e/test_explorer_root.py` si existant, sinon creer) :

| Test | Verifie |
|---|---|
| `test_explorer_affiche_un_marker_par_pa` | Apres seed avec 2 tenants (1 PA chacun + 1 tenant a 3 PA), 5 markers sur la carte |
| `test_popup_affiche_events_futurs` | Click sur marker d'une PA avec events futurs → popup contient les noms des events |

**Verifications manuelles** : se baser sur `tests/PIEGES.md` (cache SEO, `tenant_context` cross-schema).

## 7. Migration / rollout

- **Zero migration DB** : juste une nouvelle valeur dans un `CharField choices`.
- **Pas de breaking** : `AGGREGATE_LIEUX` et `AGGREGATE_EVENTS` restent intacts.
- **Activation** : prochain cycle `Celery Beat` de `refresh_seo_cache` (4h max). Pour activer immediat :
  ```bash
  docker exec lespass_django poetry run python manage.py shell -c \
    "from seo.tasks import refresh_seo_cache; refresh_seo_cache()"
  ```
- **Rollback** : supprimer la constante + la fonction. `AGGREGATE_POINTS` devient orphelin, la vue `/explorer/` retombera sur `{"points": []}` (carte vide mais pas d'erreur).

## 8. Risques + mitigations

| Risque | Mitigation |
|---|---|
| Performance : N tenants × tenant_context() pour PA + events = N requetes lourdes a l'etape 6 | Reuse `events_by_tenant` deja calcule a l'etape 2 (1 requete SQL UNION ALL). Les PA peuvent etre groupees pareil ou queryset par tenant : ~80 tenants vivants × 1 requete = OK |
| Carte trop chargee : ~300-400 markers vs ~80 aujourd'hui | `markerCluster` deja en place gere bien jusqu'a ~1000 markers. Test visuel a faire. |
| Cache obsolete si une PA est modifiee/supprimee entre 2 cycles Beat | Acceptable (max 4h decalage). Pour usage editorial fort, pourrait declencher le refresh sur signal `post_save` PostalAddress (out of scope). |
| URL `event.url` : reconstruction cote python | Utiliser `tenant.get_primary_domain() + reverse('event_detail', uuid=event.uuid)` cote backend, eviter de toucher au calcul cote JS. |
| Logo manquant pour certains tenants | Fallback : pas d'icone logo dans le popup, juste le nom du tenant en lien. |

## 9. Scope (in)

- Nouveau cache `AGGREGATE_POINTS`.
- Etape 6 dans `refresh_seo_cache`.
- Refacto `build_explorer_data_for_tenants` pour lire ce nouveau cache.
- Adaptation `seo/views.py:explorer`, `explorer.html`, `explorer.js`, `explorer.css`.
- Tests pytest + E2E.
- Entry CHANGELOG.md.
- Spec ce document + `A TESTER et DOCUMENTER/explorer-markers-per-pa.md`.

## 10. Scope (out — reporte)

- Toggle UI "Lieux / Evenements" (non choisi en brainstorming, on reste sur 1 carte unifiee).
- Markers d'event distincts (popup les contient deja).
- Refresh temps reel sur `post_save` PostalAddress / Event (overhead inutile).
- Filtres avances par categorie d'event sur la carte (peut etre ajoute apres).
- Affichage des PA pour tenants morts (carte historique).
- Modification de `AGGREGATE_LIEUX` (intact pour compat).

## 11. Journal d'avancement

- **2026-05-17** : spec creee suite a la session de geocoding (327 PA importees). Brainstorming valide les 4 decisions (1 marker/PA, tenant vivant, cache dedie, top 5 events).
