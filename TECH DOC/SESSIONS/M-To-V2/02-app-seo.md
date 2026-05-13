# Chantier 2 — Port de l'app `seo/` (landing ROOT lieux + events)

**Date :** 2026-05-13
**Statut :** Code porte. Visite HTTP bloquee par DB de dev vide (aucun Domain).
**Source d'inspiration :** `/home/jonas/TiBillet/dev/lespass-main/seo/` (branche V2)

## Objectif

Porter en V1 la landing page ROOT de V2 (page d'accueil agregee multi-tenants),
en **excluant volontairement** :

- les monnaies fedow_core (V1 utilise `fedow_public.AssetFedowPublic`)
- les adhesions (`BaseBillet.Product` categorie ADHESION)
- les initiatives crowdfunding (`crowds.Initiative`)

Resultat : un agregateur **lieux + evenements** uniquement.

## Decisions / Adaptations

| V2 (lespass-main) | V1 (Lespass) | Raison |
|---|---|---|
| 10 cache_types | **6 cache_types** | suppression TENANT_MEMBERSHIPS, AGGREGATE_MEMBERSHIPS, AGGREGATE_INITIATIVES, AGGREGATE_ASSETS |
| `get_all_assets()` (SQL fedow_core) | **supprime** | fedow_core absent de V1 main |
| `get_memberships_for_tenants()` | **supprime** | adhesions hors scope |
| `get_initiatives_for_tenants()` | **supprime** | initiatives hors scope |
| `get_global_counts()` (4 types) | **`get_global_event_count()`** | reduction au seul comptage events |
| `build_tenant_config_data()` + `accepted_asset_ids` | **sans `accepted_asset_ids`** | pas de fedow_core |
| `build_explorer_data()` (5 entites) | **`build_explorer_data()` lieux + events** | reduction du scope |
| URL `/adhesions/` + vue `adhesions()` | **supprimes** | hors scope |
| `seo/sitemap.py` (EventSitemap, ProductSitemap, StaticViewSitemap) | **NON porte** | V1 a deja `BaseBillet/sitemap.py` (tenant-scoped) qui couvre le besoin |
| `templates/seo/adhesions.html` | **supprime** | hors scope |
| `templates/seo/partials/json_ld_product.html` | **supprime** | non utilise meme en V2 |
| Recherche dans memberships | **supprimee** | hors scope |
| Explorer : pills 6 categories | **3 categories** (All/Lieux/Events) | hors scope |
| Explorer : focus monnaie (~600 lignes JS) | **supprime** | hors scope |
| Explorer : badges monnaie sur lieux | **supprime** | hors scope |
| Celery Beat via `CELERY_BEAT_SCHEDULE` settings | **`add_periodic_task()` dans `on_after_configure`** | pattern existant V1 (cf. `cron_morning`) |
| `from seo.tasks import refresh_seo_cache` direct | **wrapper `@app.task cron_refresh_seo_cache()`** | evite la race autodiscover/on_after_configure |
| `MetaBillet.urls` sur ROOT (redirige `tibillet.org`) | **`seo.urls`** | landing reelle plutot que redirect |
| `config.language` | **idem** | V1 a aussi `language` |
| `config.langue_defaut` (V2 deprecie) | n/a | jamais existe en V1 |

## Plan

- [x] 2.1 Squelette `seo/__init__.py`, `apps.py`, dossiers (management, migrations, templatetags, templates, static)
- [x] 2.2 `models.py` allege : `SEOCache` avec 6 `cache_types`
- [x] 2.3 `migrations/0001_initial.py` initial squashe (depend `Customers/0001_initial`)
- [x] 2.4 `services.py` allege : 6 fonctions au lieu de 9
- [x] 2.5 `views_common.py` : `get_seo_cache()`, `build_json_ld_organization()`, `build_json_ld_item_list()`, `robots_txt()`
- [x] 2.6 `views.py` : 5 vues (landing, lieux, evenements, recherche, explorer) + `sitemap_index_view`
- [x] 2.7 `urls.py` : 7 routes (pas de `/adhesions/`)
- [x] 2.8 `tasks.py` : `refresh_seo_cache()` allege (3 etapes pipeline au lieu de 8)
- [x] 2.9 `management/commands/refresh_seo_cache.py`
- [x] 2.10 `templatetags/seo_tags.py` : filtre `format_iso_date`
- [x] 2.11 Static : favicons + logos copies. `seo.css` copie tel quel. `explorer.css` copie tel quel (classes assets/memberships inutilisees mais inoffensives). `explorer.js` reecrit allege (~470 lignes au lieu de 1207).
- [x] 2.12 Templates : `base.html`, `landing.html`, `lieux.html`, `evenements.html`, `recherche.html`, `explorer.html`
- [x] 2.13 `TiBillet/settings.py` : `'seo'` ajoute dans `SHARED_APPS` (apres `'discovery'`)
- [x] 2.14 `TiBillet/urls_public.py` : `path('', include('seo.urls'))` remplace `include('MetaBillet.urls')`
- [x] 2.15 `TiBillet/celery.py` : wrapper `@app.task cron_refresh_seo_cache()` + `add_periodic_task` toutes les 4h
- [x] 2.16 Migrations appliquees (`migrate_schemas --shared`)
- [x] 2.17 `manage.py refresh_seo_cache` execute (renvoie 0 car DB vide)
- [ ] 2.18 Bootstrap DB de dev (a faire par le mainteneur via `install` ou demo command) puis re-test visuel `https://tibillet.localhost/`
- [ ] 2.19 Tests pytest (au moins 1 par vue : landing, lieux, evenements, recherche)

## Verifications passees

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
# System check identified no issues (0 silenced).

docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations seo --check --dry-run
# No changes detected in app 'seo'

docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --shared
# Applique sans erreur (table public.seo_seocache creee)

docker exec lespass_django poetry run python /DjangoFiles/manage.py refresh_seo_cache
# Termine : 0 tenants, 0 events, 0 lieux / Done
```

## Verifications a faire apres bootstrap DB

```bash
# 1. Verifier que des tenants existent
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from Customers.models import Client
print('Clients:', Client.objects.count())
"

# 2. Lancer le refresh
docker exec lespass_django poetry run python /DjangoFiles/manage.py refresh_seo_cache

# 3. Tester les 7 endpoints (depuis un navigateur sur le domaine public)
#    /                  → landing avec hero + chiffres + marquees
#    /lieux/            → grille des lieux
#    /evenements/       → events pagines (20/page)
#    /recherche/?q=...  → resultats lieux + events
#    /explorer/         → carte Leaflet + accordeon
#    /robots.txt        → text/plain avec Sitemap
#    /sitemap.xml       → application/xml index cross-tenant
```

## Couplage et impact sur le reste du codebase

### Fichiers MODIFIES (3)

| Fichier | Diff |
|---|---|
| `TiBillet/settings.py` | +1 ligne (`'seo'` dans SHARED_APPS) |
| `TiBillet/urls_public.py` | 1 ligne modifiee (`MetaBillet.urls` → `seo.urls`) |
| `TiBillet/celery.py` | +14 lignes (wrapper + periodic task) |

### Fichiers AJOUTES (~30)

```
seo/
  __init__.py, apps.py, models.py, services.py, views.py,
  views_common.py, tasks.py, urls.py
  migrations/__init__.py, 0001_initial.py
  management/__init__.py
  management/commands/__init__.py, refresh_seo_cache.py
  templatetags/__init__.py, seo_tags.py
  templates/seo/base.html, landing.html, lieux.html,
                evenements.html, recherche.html, explorer.html
  static/seo/seo.css, explorer.css, explorer.js,
              favicon.svg, favicon-192.png, apple-touch-icon.png,
              social-card.png, tibillet-logo-couleur.svg,
              tibillet-icone.svg
```

### Aucun fichier metier V1 touche

- `BaseBillet/views.py:index()` (vue tenant `/`) **inchange**
- `BaseBillet/sitemap.py` (tenant sitemap) **inchange**
- `BaseBillet/views_robots.py` (tenant robots) **inchange**
- `MetaBillet/` non supprime (au cas ou rollback necessaire, suffit de remettre `include('MetaBillet.urls')` dans urls_public.py)

## A NE PAS porter (volontairement exclu)

| Source V2 | Raison |
|---|---|
| `fedow_core` (modeles + admin + services) | trop couple a V2, V1 reste sur `fedow_public` + `fedow_connect` HTTP |
| `seo/sitemap.py` (V2) | V1 a deja `BaseBillet/sitemap.py` qui fait le meme job au niveau tenant |
| Adhesions sur landing/explorer/recherche | hors scope de cette etape — pourra etre rouvert si besoin |
| Initiatives crowdfunding sur landing/explorer | hors scope idem |
| Focus monnaie (convex hull + arcs Bezier) dans explorer.js | depend de fedow_core |
| Asset legend dans explorer | depend de fedow_core |
| Asset badges sur cards lieu | depend de fedow_core |

## Piege identifie : autodiscover Celery vs on_after_configure

Avec `tenant_schemas_celery.app.CeleryApp`, la signal `on_after_configure` se
declenche **avant** que `autodiscover_tasks()` ait fini de scanner les apps.
Resultat : `from seo.tasks import refresh_seo_cache` import bien la fonction
decoree, mais `.s()` la cherche dans le registry et leve
`celery.exceptions.NotRegistered: 'seo.tasks.refresh_seo_cache'`.

Solution adoptee : on definit un wrapper local `@app.task` qui delegue au
management command. Pattern deja utilise pour `cron_morning`.

```python
@app.task
def cron_refresh_seo_cache():
    call_command('refresh_seo_cache')
```

## Rollback

Pour revenir a l'etat ROOT V1 d'avant ce port :

1. Dans `TiBillet/urls_public.py` : remettre `path('', include('MetaBillet.urls'))`
2. Dans `TiBillet/settings.py` : retirer `'seo'` de SHARED_APPS
3. Dans `TiBillet/celery.py` : retirer le bloc `cron_refresh_seo_cache` + le periodic task
4. (Optionnel) `seo/` reste sur disque mais n'est plus charge. La table
   `public.seo_seocache` peut etre droppee par migration reverse.

## CHANGELOG

- 2026-05-13 : Port complet seo allege, code valide par `manage.py check`, migration appliquee, refresh execute (DB vide -> 0 resultats), HTTP visite bloquee par django-tenants (aucun Domain en DB).
