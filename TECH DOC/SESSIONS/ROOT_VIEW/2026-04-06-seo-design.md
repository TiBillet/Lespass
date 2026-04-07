# Design SEO — App `seo` + Améliorations réseau TiBillet

**Date :** 2026-04-06
**Branche :** V2
**Statut :** Validé

---

## 1. Objectif

Doter le réseau TiBillet d'une couche SEO complète :
- **ROOT tenant** (`tibillet.coop`) : landing page vitrine, pages agrégées (lieux, événements, adhésions), recherche cross-réseau, sitemap index cross-tenant
- **Chaque tenant** : canonical links, JSON-LD Organization/Product, sitemap enrichi (images), hreflang cross-langue
- **Cache performant** : task Celery toutes les 4h, données pré-calculées en DB (schema public) + Memcached L1. Les robots ne déclenchent jamais de requête cross-schema.

---

## 2. Architecture

### 2.1 — Nouvelle app `seo` (SHARED_APPS)

```
seo/
├── __init__.py
├── apps.py
├── models.py          # SEOCache (schema public)
├── tasks.py           # Celery periodic task (4h) + requêtes SQL cross-schema
├── views.py           # Vues ROOT : landing, /lieux/, /evenements/, /adhesions/, /recherche/
├── views_common.py    # Helpers partagés : canonical, JSON-LD builders
├── sitemap.py         # Sitemaps enrichis (remplace BaseBillet/sitemap.py)
├── urls.py            # URLs ROOT
├── templates/seo/     # Templates landing + pages agrégées
└── migrations/
```

### 2.2 — Flow des données

```
Celery (toutes les 4h)
  │
  ├─ Requête SQL cross-schema : tenants actifs + counts  (1 query)
  ├─ Requête SQL cross-schema : events des actifs         (1 query)
  ├─ Requête SQL cross-schema : adhésions des actifs      (1 query)
  ├─ ORM : Configuration par tenant actif                 (N queries, set_tenant)
  │
  └─► SEOCache (public schema, JSONField)
        │
        ├─► Memcached L1 (TTL 4h)
        │
        ├─► ROOT: landing, /lieux/, /evenements/, /adhesions/, sitemap index
        └─► Tenants: canonical fédéré, hreflang, events réseau
```

---

## 3. Modèle `SEOCache`

**App :** `seo` — **Schema :** `public` (SHARED_APPS)

```python
class SEOCache(models.Model):
    CACHE_TYPES = [
        ('tenant_summary', 'Résumé tenant (config, stats, domaine)'),
        ('tenant_events', 'Events publiés du tenant'),
        ('tenant_memberships', 'Adhésions publiées du tenant'),
        ('aggregate_events', 'Agrégat events réseau (ROOT)'),
        ('aggregate_memberships', 'Agrégat adhésions réseau (ROOT)'),
        ('aggregate_lieux', 'Agrégat lieux actifs (ROOT)'),
        ('sitemap_index', 'Sitemap index cross-tenant (ROOT)'),
    ]

    cache_type = CharField(max_length=30, choices=CACHE_TYPES, db_index=True)
    tenant = ForeignKey('Customers.Client', null=True, blank=True, on_delete=CASCADE)
    data = JSONField(default=dict)
    updated_at = DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('cache_type', 'tenant')]
```

**Contrainte :** `unique_together` garantit un seul enregistrement par couple `(cache_type, tenant)`. `tenant=null` pour les agrégats globaux.

### 3.1 — Contenu `data` par type

**`tenant_summary`** (1 par tenant actif) :
```json
{
  "name": "Maison du Craft",
  "domain": "maison-craft.tibillet.coop",
  "logo_url": "/media/...",
  "short_description": "Lieu culturel...",
  "language": "fr",
  "city": "Saint-Denis",
  "country": "RE",
  "event_count": 12,
  "membership_count": 3,
  "has_upcoming_events": true
}
```

**`tenant_events`** (1 par tenant actif) :
```json
{
  "events": [
    {
      "name": "Concert Jazz",
      "slug": "concert-jazz",
      "datetime": "2026-05-15T20:00:00",
      "end_datetime": "2026-05-15T23:00:00",
      "short_description": "...",
      "image_url": "/media/...",
      "social_card_url": "/media/...",
      "price_min": 500,
      "location": "Maison du Craft, Saint-Denis"
    }
  ]
}
```

**`tenant_memberships`** (1 par tenant actif) :
```json
{
  "memberships": [
    {
      "uuid": "550e8400-...",
      "name": "Adhésion annuelle",
      "short_description": "...",
      "image_url": "/media/...",
      "price": "15.00",
      "currency": "EUR"
    }
  ]
}
```

**`aggregate_events`** (1 seul, `tenant=null`) :
```json
{
  "events": [
    {
      "name": "Concert Jazz",
      "slug": "concert-jazz",
      "datetime": "2026-05-15T20:00:00",
      "tenant_domain": "maison-craft.tibillet.coop",
      "tenant_name": "Maison du Craft",
      "canonical_url": "https://maison-craft.tibillet.coop/event/concert-jazz/",
      "image_url": "...",
      "price_min": 500,
      "location": "Saint-Denis"
    }
  ]
}
```

**`aggregate_memberships`** et **`aggregate_lieux`** : même principe, fusion des données tenant avec `tenant_domain` et `canonical_url`.

**`sitemap_index`** (1 seul, `tenant=null`) :
```json
{
  "tenants": [
    {
      "domain": "maison-craft.tibillet.coop",
      "sitemap_url": "https://maison-craft.tibillet.coop/sitemap.xml",
      "updated_at": "2026-04-06T12:00:00"
    }
  ]
}
```

---

## 4. Celery task `refresh_seo_cache`

### 4.1 — Déclenchement

- `CELERY_BEAT_SCHEDULE` : toutes les 4h (`crontab(minute=0, hour='*/4')`)
- Management command `python manage.py refresh_seo_cache` pour lancement manuel
- Idempotent : `update_or_create` partout

### 4.2 — Requête SQL cross-schema optimisée

**Étape 1 — Identifier les tenants actifs (1 query) :**

Construction dynamique d'un `UNION ALL` sur tous les schemas tenants :

```sql
SELECT
    '{uuid}'::uuid AS tenant_id,
    (SELECT COUNT(*) FROM "{schema}"."BaseBillet_event"
     WHERE published = true AND datetime >= NOW()) AS event_count,
    (SELECT COUNT(*) FROM "{schema}"."BaseBillet_product"
     WHERE publish = true AND categorie_article = 'A') AS membership_count
UNION ALL
-- ... répété pour chaque schema tenant
```

Filtre Python : `event_count > 0 OR membership_count > 0`.

**Étape 2 — Données détaillées des actifs (2 queries) :**

```sql
-- Events
SELECT '{uuid}' AS tenant_id, e.name, e.slug, e.datetime, e.end_datetime,
       e.short_description
FROM "{schema}"."BaseBillet_event" e
WHERE e.published = true AND e.datetime >= NOW()
UNION ALL ...
ORDER BY datetime ASC

-- Adhésions
SELECT '{uuid}' AS tenant_id, p.uuid, p.name, p.short_description
FROM "{schema}"."BaseBillet_product" p
WHERE p.publish = true AND p.categorie_article = 'A'
UNION ALL ...
```

**Étape 3 — Configuration par tenant actif (N queries ORM) :**

`connection.set_tenant(client)` → `Configuration.get_solo()` pour logo, images, adresse, réseaux sociaux. Nécessaire pour les méthodes Python (`get_social_card()`).

**Étape 4 — Écriture :**

- `SEOCache.objects.update_or_create()` pour chaque entrée
- Invalide les clés Memcached correspondantes
- Écrit les nouvelles valeurs en Memcached (TTL 4h)

### 4.3 — Robustesse

- `try/except` par tenant — un tenant en erreur ne bloque pas les autres (log warning)
- Pas de lock — `update_or_create` est idempotent
- Pas de diff — réécriture complète à chaque cycle

---

## 5. Vues ROOT

### 5.1 — Landing page `/`

- Texte explicatif depuis `Configuration.get_solo()` du ROOT (`long_description`, Markdown)
- Chiffres clés du réseau (lieux, events, adhésions) depuis `SEOCache` agrégats
- Top 12 lieux actifs (logo, nom, ville, lien) triés par `event_count` décroissant
- Top 6 prochains events du réseau triés par date
- JSON-LD `Organization` (TiBillet coopérative)
- hreflang FR/EN

### 5.2 — `/lieux/`

- Source : `SEOCache(cache_type='aggregate_lieux')`
- Carte par lieu : logo, nom, ville, description courte, event count, lien tenant
- Tri : `event_count` décroissant
- JSON-LD `ItemList` avec `ListItem` type `Organization`

### 5.3 — `/evenements/`

- Source : `SEOCache(cache_type='aggregate_events')`
- Carte par event : image, titre, date, lieu, prix min, lien canonical vers tenant créateur
- Tri : date croissante
- Pagination : 20 par page
- JSON-LD `ItemList` avec `ListItem` type `Event`

### 5.4 — `/adhesions/`

- Source : `SEOCache(cache_type='aggregate_memberships')`
- Carte par adhésion : nom, description, prix, lieu, lien tenant
- JSON-LD `ItemList` avec `ListItem` type `Product`

### 5.5 — `/recherche/?q=...`

- Recherche en Python sur le contenu `SEOCache` en Memcached L1
- Champs : nom event, nom lieu/organisation, ville, nom adhésion
- Match partiel, insensible à la casse (`str.lower() in str.lower()`)
- Résultats groupés par type (events, lieux, adhésions)
- HTML server-side, compatible HTMX
- Pas de JSON-LD (page utilitaire)
- Pas d'Elasticsearch — le dataset est petit (centaines d'entrées max)

### 5.6 — URLs ROOT (`seo/urls.py`)

```
/                    → landing
/lieux/              → liste lieux
/evenements/         → liste events
/adhesions/          → liste adhésions
/recherche/          → recherche cross-réseau
/sitemap.xml         → sitemap index cross-tenant
/robots.txt          → robots.txt ROOT
```

---

## 6. Améliorations SEO par tenant

### 6.1 — `<link rel="canonical">`

Bloc `{% block canonical %}` dans `reunion/base.html` et `faire_festival/base.html`.
- Event local : canonical = domaine courant
- Event fédéré : canonical = domaine du tenant créateur (résolu depuis `SEOCache`)

### 6.2 — JSON-LD `Organization` par tenant

Dans le base template, sur toutes les pages :

```json
{
  "@context": "https://schema.org",
  "@type": "Organization",
  "name": "...",
  "url": "https://...",
  "logo": "...",
  "description": "...",
  "address": { "@type": "PostalAddress", "..." },
  "sameAs": ["https://facebook.com/...", "https://instagram.com/..."]
}
```

Source : `Configuration.get_solo()`.

### 6.3 — JSON-LD `Product/Offer` pour les adhésions

Sur la page détail adhésion :

```json
{
  "@context": "https://schema.org",
  "@type": "Product",
  "name": "...",
  "description": "...",
  "offers": {
    "@type": "Offer",
    "price": "15.00",
    "priceCurrency": "EUR",
    "availability": "https://schema.org/InStock"
  }
}
```

### 6.4 — hreflang cross-langue

Sur les events fédérés entre tenants de langues différentes :

```html
<link rel="alternate" hreflang="fr" href="https://tenant-fr.../event/slug/" />
<link rel="alternate" hreflang="en" href="https://tenant-en.../event/slug/" />
```

Le Celery task détecte les paires hreflang et les stocke dans `SEOCache`.

### 6.5 — Sitemap tenant enrichi

- `<lastmod>` basé sur `updated_at` (pas `created`)
- `<image:image>` pour les events avec image

```xml
<url>
  <loc>https://tenant.com/event/slug/</loc>
  <lastmod>2026-04-05</lastmod>
  <image:image>
    <image:loc>https://tenant.com/media/.../social_card.jpg</image:loc>
    <image:title>Concert Jazz</image:title>
  </image:image>
</url>
```

### 6.6 — `htmx/base.html` — PAS DE MODIFICATION

Vérifié : aucune page publique active n'utilise `htmx/base.html` directement. Les deux seuls templates qui l'étendent (`old_create_product.html`, `test_jinja.html`) sont commentés dans les URLs (code mort). Tous les templates publics utilisent `{% extends base_template %}` qui résout dynamiquement vers `reunion/base.html` ou `faire_festival/base.html` — templates qui ont déjà les meta tags SEO.

---

## 7. Cache — Stratégie deux niveaux

| Niveau | Backend | TTL | Rôle |
|--------|---------|-----|------|
| L1 | Memcached | 4h | Lecture rapide pour les vues |
| L2 | PostgreSQL (`SEOCache`) | Persistant | Source de vérité, survit aux restarts |

**Lecture :** Vue → Memcached (L1). Miss → `SEOCache` (L2) + recharge L1.
**Écriture :** Celery → `SEOCache` (L2) + invalide et recharge L1.

Clés Memcached : `seo:{cache_type}:{tenant_uuid}` ou `seo:{cache_type}:global` (pour `tenant=null`).

---

## 8. Ce qu'on ne fait PAS

- **Pas d'AMP** — obsolète
- **Pas d'Elasticsearch** — dataset trop petit
- **Pas de pages agrégées par tag/thématique sur le ROOT** — prématuré
- **Pas de requête cross-schema en temps réel** — tout passe par le cache
- **Pas de hreflang sur tenants indépendants** — uniquement events fédérés cross-langue
- **Pas de meta refresh / redirects SEO**

---

## 9. Tests

### 9.1 — pytest (`tests/pytest/test_seo.py`)

**Modèle :**
- `test_update_or_create_seo_cache`
- `test_unique_together_constraint`
- `test_global_cache_tenant_null`

**Celery task :**
- `test_refresh_seo_cache_populates_data`
- `test_refresh_seo_cache_skips_inactive_tenants`
- `test_refresh_seo_cache_cross_schema_query`
- `test_refresh_seo_cache_idempotent`

**Vues ROOT :**
- `test_landing_page_returns_200`
- `test_landing_page_json_ld_organization`
- `test_lieux_page_lists_active_tenants`
- `test_evenements_page_sorted_by_date`
- `test_recherche_by_event_name`
- `test_recherche_by_city`
- `test_recherche_empty_query`

**Sitemap ROOT :**
- `test_sitemap_index_lists_tenant_sitemaps`
- `test_robots_txt_references_sitemap`

**Améliorations tenant :**
- `test_canonical_link_local_event`
- `test_canonical_link_federated_event`
- `test_json_ld_organization_in_base_template`
- `test_json_ld_product_on_membership_detail`
- `test_sitemap_tenant_has_image_tags`

### 9.2 — Playwright E2E (`tests/playwright/tests/32-seo.spec.ts`)

- `test_root_landing_og_tags`
- `test_root_landing_social_card_image`
- `test_event_detail_structured_data`
- `test_sitemap_xml_accessible`
- `test_robots_txt_accessible`
- `test_search_finds_event`

---

## 10. Fichiers

### Nouveaux

| Fichier | Rôle |
|---------|------|
| `seo/__init__.py` | App init |
| `seo/apps.py` | AppConfig |
| `seo/models.py` | `SEOCache` |
| `seo/tasks.py` | Celery task + SQL cross-schema |
| `seo/views.py` | Vues ROOT |
| `seo/views_common.py` | Helpers canonical, JSON-LD builders |
| `seo/sitemap.py` | Sitemaps enrichis |
| `seo/urls.py` | URLs ROOT |
| `seo/templates/seo/base.html` | Base template ROOT |
| `seo/templates/seo/landing.html` | Landing page |
| `seo/templates/seo/lieux.html` | Page lieux |
| `seo/templates/seo/evenements.html` | Page events |
| `seo/templates/seo/adhesions.html` | Page adhésions |
| `seo/templates/seo/recherche.html` | Page recherche |
| `seo/migrations/0001_initial.py` | Migration |
| `tests/pytest/test_seo.py` | Tests pytest |
| `tests/playwright/tests/32-seo.spec.ts` | Tests E2E |

### Modifiés

| Fichier | Modification |
|---------|-------------|
| `TiBillet/settings.py` | `seo` dans SHARED_APPS + `CELERY_BEAT_SCHEDULE` |
| `TiBillet/urls_tenants.py` | Sitemap → `seo.sitemap` + URLs ROOT conditionnelles |
| `BaseBillet/templates/reunion/base.html` | Bloc canonical, JSON-LD Organization |
| `BaseBillet/templates/faire_festival/base.html` | Idem |
| `BaseBillet/templates/htmx/base.html` | ~~Pas de modification~~ — aucune page publique active ne l'utilise |
| `BaseBillet/templates/reunion/views/event/retrieve.html` | Canonical fédéré + hreflang |
| `BaseBillet/templates/faire_festival/views/event/retrieve.html` | Idem |
| `BaseBillet/templates/*/views/membership/retrieve.html` | JSON-LD Product |

### Dépréciés (remplacés)

| Fichier | Remplacé par |
|---------|-------------|
| `BaseBillet/sitemap.py` | `seo/sitemap.py` |
| `BaseBillet/views_robots.py` | `seo/views_common.py` |
