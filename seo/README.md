# App `seo/` — Moteur de vue du tenant ROOT (landing page reseau)

## Objectif

L'app `seo/` sert la **landing page globale du reseau TiBillet**. Contrairement aux
pages de chaque tenant (qui vivent dans leur propre schema et affichent leurs events/adhesions),
cette app vit dans le **schema public** et **agrege les donnees de tous les tenants actifs**
en un seul site de decouverte.

Le visiteur arrive sur le domaine ROOT (ex: `tibillet.re`) et voit :
- une presentation de TiBillet (hero + philosophie + fonctionnalites)
- les lieux du reseau (avec carte interactive)
- les evenements a venir (tous tenants confondus, avec vignettes)
- les adhesions disponibles
- les initiatives (crowdfunding, budget contributif)
- les monnaies federees (TLF, TNF, TIM, FED, FID)
- un moteur de recherche transversal

Chaque lien pointe vers le site du tenant concerne (ex: `raffinerie.tibillet.re/event/mon-concert`).

## Architecture — 2 couches de cache

Les vues ne font **jamais** de requete SQL cross-schema en direct.
Tout passe par un cache a 2 niveaux :

```
                  ┌──────────────┐
  Vue (GET /)  →  │ L1 Memcached │  4h TTL
                  │  (en memoire)│
                  └──────┬───────┘
                         │ miss?
                  ┌──────▼───────┐
                  │  L2 SEOCache │  table PostgreSQL
                  │   (DB)       │  schema public
                  └──────┬───────┘
                         │ miss?
                         ▼
                       ∅ (liste vide)
```

**Pourquoi** : eviter les requetes SQL cross-schema (UNION ALL sur N schemas)
a chaque page view. Ces requetes sont couteuses et ne changent que rarement
(les events ne bougent pas toutes les secondes). Le refresh se fait en arriere-plan.

### Refresh du cache — tache Celery

Le cache est reconstruit **toutes les 4 heures** par la tache Celery Beat :

```
seo.tasks.refresh_seo_cache
```

Pipeline en 8 etapes :
1. **Comptes par tenant** — 1 requete SQL `UNION ALL` sur tous les schemas
2. **Evenements publies** — 1 requete SQL `UNION ALL` (events futurs + published) + champ `img` pour les vignettes
3. **Adhesions publiees** — 1 requete SQL `UNION ALL` (products avec categorie='A')
4. **Initiatives** — 1 requete SQL `UNION ALL` (initiatives non archivees, table `crowds_initiative`)
5. **Assets** — 1 requete SQL sur le schema public (monnaies federees, table `fedow_core_asset`)
6. **Config par tenant** — N requetes ORM (1 par tenant, via `tenant_context`)
7. **Enrichissement + ecriture par tenant** — events enrichis avec `image_url` (crop 480x270) et `canonical_url`, puis `SEOCache.update_or_create()` + Memcached L1
8. **Agregats globaux** — events + memberships + initiatives + assets + lieux + sitemap_index + global_counts
9. **Nettoyage** — suppression des entrees de tenants inactifs/supprimes

Lancement manuel : `python manage.py refresh_seo_cache`


## Modele — `SEOCache`

Un seul modele dans le schema public. 10 types de cache :

| Type | tenant | Contenu |
|------|--------|---------|
| `TENANT_SUMMARY` | FK client | Config + stats (domain, org, description, GPS, contacts, logo_url, accepted_asset_ids) |
| `TENANT_EVENTS` | FK client | `{"events": [...]}` du tenant — chaque event a `image_url`, `canonical_url`, `tenant_name` |
| `TENANT_MEMBERSHIPS` | FK client | `{"memberships": [...]}` du tenant |
| `AGGREGATE_EVENTS` | `null` | Tous les events de tous les tenants, tries par date, avec images |
| `AGGREGATE_MEMBERSHIPS` | `null` | Toutes les adhesions de tous les tenants |
| `AGGREGATE_LIEUX` | `null` | Lieux actifs (domain, GPS, description, logo) |
| `AGGREGATE_INITIATIVES` | `null` | Toutes les initiatives (crowdfunding, budget contributif) |
| `AGGREGATE_ASSETS` | `null` | Toutes les monnaies federees (TLF, TNF, TIM, FED, FID). Chaque asset a : tenant_origin_id, tenant_origin_name, accepting_tenant_ids, accepting_count, is_federation_primary |
| `SITEMAP_INDEX` | `null` | Liste des tenants avec domaine pour `sitemap.xml` |
| `GLOBAL_COUNTS` | `null` | Chiffres cles bruts (lieux, events, memberships, initiatives, assets) |

Contrainte unique : `(cache_type, tenant)` — 1 entree par type et par tenant.

Le champ `data` est un `JSONField` dont la structure depend du `cache_type`.


## Vues — 8 endpoints

| URL | Vue | Description |
|-----|-----|-------------|
| `/` | `landing()` | Page d'accueil : hero presentation TiBillet + philosophie + grille features + chiffres cles + marquee lieux + marquee events (avec vignettes) |
| `/lieux/` | `lieux()` | Grille de tous les lieux actifs (3 colonnes) |
| `/evenements/` | `evenements()` | Events pagines (20/page, 2 colonnes) |
| `/adhesions/` | `adhesions()` | Toutes les adhesions (4 colonnes) |
| `/recherche/?q=...` | `recherche()` | Recherche texte sur nom/localite/description |
| `/explorer/` | `explorer()` | Carte Leaflet interactive + liste filtree (noindex) |
| `/robots.txt` | `robots_txt()` | Robots.txt dynamique avec sitemap |
| `/sitemap.xml` | `sitemap_index_view()` | Index XML listant les sitemaps de chaque tenant |

Toutes les vues lisent depuis le cache `get_seo_cache()` — jamais de SQL direct.

### Landing page (`/`) — structure

1. **Hero** (style tibillet.org, full-width, fond tertiaire)
   - H1 avec mots-cles en gradient vert/bleu palette TiBillet (`#259d49` → `#4296cc`)
   - Logo TiBillet couleur (SVG depuis `seo/static/seo/tibillet-logo-couleur.svg`)
   - 2 CTA : "Explorer le reseau" (vert) + "Creer son espace" (vers tibillet.org)
2. **Philosophie** — 2 colonnes, texte inspire de la page `/fr/docs/presentation/philosophie/` et du discours de Jonas
3. **Fonctionnalites** — grille 3x2 (Adhesions, Billetterie, Agenda federe, Caisse, Cashless/NFC, Monnaie locale/temps)
4. **Chiffres cles** — 5 stats en `<span>` (pas `<h2>` — ce sont des valeurs, pas des titres semantiques)
5. **Marquee lieux** — bandeau infini horizontal, logos ou initiale coloree
6. **Marquee events** — bandeau infini horizontal, vignettes `crop` 480x270, date + lieu

### Page Explorer (carte interactive)

Split view : liste a gauche (55%) + carte Leaflet a droite (45%) sur desktop.
Sur mobile : liste par defaut, FAB pour basculer vers la carte.

- **Marker clustering** (Leaflet.markercluster) pour les lieux avec GPS
- **Tuiles CartoDB Voyager** (pas OSM direct — evite les erreurs "referer required" en localhost)
- **Filtres** : texte libre + 5 pills (Tous / Lieux / Events / Adhesions / Initiatives / Monnaies)
- **Cards lieu cliquables** : clic = focus carte (zoom sur marqueur + popup), pas d'ouverture de page
- **Accordeon dans chaque card lieu** : liste les events + adhesions + initiatives du lieu
- **Auto-ouverture accordeon desktop** : le clic sur un lieu ouvre aussi son accordeon
- **Focus carte via event/adhesion/initiative** : clic sur une card "plate" zoome sur le lieu parent
- **Monnaies** : cards cliquables déclenchant le mode focus monnaie (voir ci-dessous)
- **FAB mobile** : deplace dans `document.body` au chargement pour eviter les containing blocks parasites qui cassent `position: fixed`
- **`noindex, nofollow`** : pas indexe par les moteurs (page d'exploration, pas de SEO)
- **Mode focus monnaie** : clic sur une card monnaie ou un badge monnaie d'un lieu active le mode focus :
  - Highlight des lieux acceptants + dim des autres (opacity 0.3)
  - Style B (polygone translucide convex hull) pour la monnaie fédérée primaire (`category=FED`, ex: TiBillet)
  - Style C (arcs Bézier depuis origine) pour les assets fédérés partiellement
  - Légende contextuelle en bas-gauche (nom, catégorie, origine, nombre de lieux)
  - Clic à nouveau sur la même monnaie = reset (toggle)
- **Badges monnaies sur cards lieu** : chaque card lieu affiche les monnaies acceptées sous la description, cliquables pour déclencher le focus


## SEO — fonctionnalites implementees

### Meta tags (base.html)
- `<title>`, `<meta name="description">`, `<link rel="canonical">`
- Open Graph : `og:type`, `og:url`, `og:title`, `og:description`, `og:site_name`
- Twitter Card : `card=summary_large_image`, `twitter:url`, `twitter:title`
- `<meta name="robots">` configurable par vue (`index,follow` ou `noindex,nofollow`)

### JSON-LD structured data
3 builders dans `views_common.py` :
- `build_json_ld_organization()` — schema.org/Organization (landing, lieux)
- `build_json_ld_product()` — schema.org/Product avec Offer (adhesions)
- `build_json_ld_item_list()` — schema.org/ItemList avec positions (lieux, events, adhesions)

### Sitemap
- `sitemap.xml` : index qui pointe vers le `sitemap.xml` de chaque tenant
- Construit depuis le cache `SITEMAP_INDEX`

### Robots.txt
- Dynamique, inclut l'URL du sitemap
- `Allow: /` (tout le site est crawlable)


## Services — requetes SQL cross-schema

Fichier : `seo/services.py`

6 fonctions de lecture cross-schema (utilisees par la tache Celery, pas par les vues) :

| Fonction | Type SQL | Resultat |
|----------|----------|----------|
| `get_active_tenants_with_counts()` | UNION ALL | tenant_id + event_count + membership_count |
| `get_events_for_tenants(schemas)` | UNION ALL | name, slug, datetime, description, `img` par event |
| `get_memberships_for_tenants(schemas)` | UNION ALL | uuid, name, description par adhesion |
| `get_initiatives_for_tenants(schemas)` | UNION ALL | uuid, name, description, `budget_contributif` par initiative |
| `get_all_assets()` | Simple SELECT | uuid, name, category sur schema public (fedow_core) |
| `get_global_counts(schemas)` | UNION ALL | Comptages bruts events/memberships/initiatives/assets |
| `build_tenant_config_data(client)` | ORM + `tenant_context` | Config singleton (organisation, GPS, contacts, logo) |

Fonction helper pour les images :
- `build_stdimage_variation_url(img_path, variation="crop")` — construit l'URL d'une variation StdImageField (ex: `images/foo.jpg` → `/media/images/foo.crop.jpg`)

**Securite SQL** : les noms de schemas sont injectes via f-string (pas de `%s`),
mais c'est sur car `schema_name` provient de `Client.schema_name` en DB,
controle par l'admin, jamais par un input utilisateur. PostgreSQL ne permet pas
de parametriser les identifiants (noms de table/schema).

### Memcached helpers
- `set_memcached_l1(cache_type, tenant_uuid, data)` — ecrit avec TTL 4h
- `get_memcached_l1(cache_type, tenant_uuid)` — lit, retourne `None` si miss
- Cle : `seo:{cache_type}:{tenant_uuid|"global"}`


## Template tags

Fichier : `seo/templatetags/seo_tags.py`

| Filtre | Usage | Resultat |
|--------|-------|----------|
| `format_iso_date` | `{{ event.datetime\|format_iso_date }}` | "Lundi 13 octobre 2026, 10h39" |


## Arborescence

```
seo/
├── __init__.py
├── apps.py                  # AppConfig "seo"
├── models.py                # SEOCache (schema public)
├── views.py                 # 7 vues principales + sitemap_index
├── views_common.py          # get_seo_cache(), JSON-LD builders, robots.txt
├── services.py              # SQL cross-schema, Memcached, build_explorer_data
├── tasks.py                 # Celery task refresh_seo_cache (Beat = 4h)
├── urls.py                  # 8 URL patterns (app_name="seo")
├── sitemap.py               # Classes sitemap Django (EventSitemap, etc.)
├── templatetags/
│   └── seo_tags.py          # Filtre format_iso_date
├── templates/seo/
│   ├── base.html            # Template maitre (navbar, footer, meta SEO, JSON-LD)
│   ├── landing.html         # Accueil : chiffres + lieux + events
│   ├── lieux.html           # Grille lieux
│   ├── evenements.html      # Events pagines
│   ├── adhesions.html       # Adhesions
│   ├── recherche.html       # Recherche texte
│   ├── explorer.html        # Carte Leaflet interactive
│   └── partials/
│       ├── json_ld_organization.html
│       └── json_ld_product.html
├── static/seo/
│   ├── seo.css              # Styles communs (hero, philosophie, features, marquees, stats)
│   ├── explorer.css         # Split view desktop + mobile FAB + accordeon + badges categories
│   ├── explorer.js          # Client-side : carte Leaflet, filtres 5 categories, accordeon, focus carte
│   ├── tibillet-logo-couleur.svg  # Logo couleur TiBillet (depuis kit graphique)
│   └── tibillet-icone.svg   # Icone TiBillet (depuis kit graphique)
├── management/commands/
│   └── refresh_seo_cache.py # python manage.py refresh_seo_cache
└── migrations/
    └── 0001_initial.py      # Creation SEOCache
```


## Relation avec les autres apps

| App | Relation |
|-----|----------|
| `Customers` | `Client` = un tenant. `SEOCache.tenant` est une FK vers Client. |
| `BaseBillet` | `Event`, `Product`, `Configuration` sont lus en cross-schema par la tache Celery. Les vues ne les touchent jamais directement. |
| `django_tenants` | `tenant_context()` pour lire la Configuration de chaque tenant. |
| Frontend tenant | Les liens sur la landing pointent vers `https://{domain}/event/{slug}` — le site du tenant. |


## Points d'entree

1. **URL** : `TiBillet/urls_public.py` → `path('', include('seo.urls'))`
2. **Celery Beat** : `seo.tasks.refresh_seo_cache` toutes les 4 heures
3. **Management** : `python manage.py refresh_seo_cache`
4. **Fixture demo** : `demo_data_v2` appelle `refresh_seo_cache()` en etape 5
   (apres la creation des tenants, events, adhesions et donnees POS)

```bash
# Lancement manuel du cache SEO
docker exec lespass_django poetry run python manage.py refresh_seo_cache

# Resultat :
# Termine : 6 tenants, 20 events, 10 memberships / Done
```

Le cache est aussi reconstruit automatiquement a la fin de `demo_data_v2`,
pour que la landing page ROOT soit fonctionnelle immediatement apres l'installation.


## Design decisions

- **Pas de requete cross-schema dans les vues** : tout passe par le cache.
  Consequence : les donnees affichees peuvent avoir jusqu'a 4h de retard sur la realite.
  C'est acceptable pour une landing page de decouverte.

- **Stateless rebuild** : la tache Celery reconstruit TOUT a chaque run.
  Pas de diff, pas d'incremental. Simple, robuste, pas de desynchronisation.

- **JSON dans PostgreSQL** : le champ `data` est un `JSONField`.
  Pas de modele normalise pour les events/lieux caches.
  Avantage : pas de migration quand on ajoute un champ au cache.
  Inconvenient : pas de requete SQL sur les champs individuels.

- **Explorer = noindex** : la carte interactive est une feature d'exploration,
  pas une page SEO. Les moteurs indexent `/lieux/` et `/evenements/` a la place.

- **Pagination uniquement sur events** : les lieux et adhesions sont affiches
  en totalite (le reseau n'a pas des milliers de lieux). Les events sont pagines
  par 20 car ils peuvent etre nombreux.

- **Images events dans le cache via SQL direct** : le champ `img` de `Event`
  (StdImageField) contient le chemin de base. La vignette `.crop.jpg` (480x270)
  est construite via `build_stdimage_variation_url()` dans `tasks.py`, puis
  stockee comme `image_url` dans le cache. Pas de requete ORM pour obtenir les URLs.

- **Tuiles CartoDB Voyager** (pas OSM direct) : OSM bloque les tuiles quand le
  referer HTTP est absent (localhost, certains navigateurs avec referrer-policy strict).
  CartoDB n'a pas cette restriction et offre un style plus lisible.

- **FAB mobile deplace dans `document.body`** : certains ancetres (layout flex
  Bootstrap, main container) peuvent creer un "containing block" qui casse le
  `position: fixed` du FAB. En le deplacant en enfant direct de body au chargement,
  on garantit que `position: fixed` est relatif au viewport.

- **Les cards de l'explorer construites en JS** : exception a la regle FALC
  "Python serveur > JavaScript client". Justification : l'explorer charge toutes
  les donnees en une fois (pas de pagination), le rendu JS est plus rapide que
  N requetes HTMX. Si on ajoute beaucoup de donnees, passer a des partials HTMX.

- **Monnaies (assets) sans focus carte** : les assets fedow_core sont globaux
  (pas rattaches a un lieu physique). Leurs cards ne declenchent pas de focus carte.
