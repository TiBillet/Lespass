# Stratégie de caching : passer de l'ad-hoc au structuré

## Sources

- Talk DjangoCon US 2025 : "High Performance Django at Ten" — Peter Baumgartner (Lincoln Loop)
  - Résumé : https://www.better-simple.com/lunch-talks/2026/03/10/high-performance-django-at-ten/
  - Talk : https://2025.djangocon.us/talks/high-performance-django-at-ten-old-tricks-new-picks/
  - Livre gratuit : https://highperformancedjango.com/
- "Designing Data-Intensive Applications" — Martin Kleppmann : https://dataintensive.net/
- "Django Scalability Best Practices" — codezup.com : https://codezup.com/django-scalability-best-practices/
  - Confirme `@cache_page` sur les vues publiques + audit N+1 comme leviers prioritaires

## Constat actuel sur Lespass

L'infrastructure est en place mais la stratégie est fragmentée :

### Ce qui existe (et qui est bien fait)

- **Redis** actif pour Celery (broker + result backend) et Django Channels (WebSocket)
- **Memcached** comme cache Django par défaut (`PyMemcacheCache` sur port 11211)
- **Cache tenant-aware** via `django_tenants.cache.make_key` — isolation correcte
- **Cache objet** utilisé dans plusieurs modules :
  - `fedow_connect/fedow_api.py` : assets et wallets (TTL 24h et 10s)
  - `BaseBillet/models.py` : images et social cards (TTL 1h)
  - `crowds/views.py` : summaries et user sources (TTL 60s)
  - `api_v2/views.py` : listes et détails de ventes (TTL 60-120s)
- **Invalidation par signaux** dans `crowds/signals.py` et `BaseBillet/signals.py`
- **Cache invalidation dans les `save()`** des modèles pour les images

### Ce qui manque

| Couche | Status | Impact |
|---|---|---|
| **Fragment caching templates** (`{% cache %}`) | Absent | Les partials HTMX sont re-rendus à chaque requête même si les données n'ont pas changé |
| **HTTP caching** (`@cache_page`, `Cache-Control`) | Absent | Aucun cache navigateur, chaque page est re-générée côté serveur |
| **Sessions Redis** | Absent (DB-backed) | Chaque requête fait un SELECT sur la table sessions |
| **View-level caching** | Absent | Pas de `@cache_page` sur les vues publiques à fort trafic |
| **ETag / Conditional responses** | Absent | Le serveur renvoie tout même si rien n'a changé |
| **Convention de nommage des clés** | Partiel | Mélange de patterns (`config_get_med_{pk}`, `crowds:list:summary:{tenant_id}`, `api:sales:list:{schema}:...`) |

### Le problème des deux backends

Lespass utilise **Memcached pour le cache Django** et **Redis pour Celery + Channels**.
C'est deux services à maintenir pour deux usages. Baumgartner (High Performance Django)
recommande de consolider sur Redis qui fait tout : cache, broker, channels, sessions.

## Actions possibles

### 1. Consolider sur Redis (priorité haute)

Remplacer Memcached par Redis comme cache Django par défaut. Un seul service à maintenir.

```python
# TiBillet/settings.py — remplacer Memcached par Redis
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': 'redis://redis:6379/1',  # DB 1 pour le cache (DB 0 = Celery)
        'KEY_FUNCTION': 'django_tenants.cache.make_key',
        'REVERSE_KEY_FUNCTION': 'django_tenants.cache.reverse_key',
    }
}
```

Puis supprimer le service `lespass_memcached` du docker-compose.yml.

### 2. Sessions Redis (priorité haute)

Chaque requête HTTP fait un SELECT en base pour les sessions. Redis est plus rapide
et réduit la charge DB.

```python
# TiBillet/settings.py
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'
```

### 3. Fragment caching sur les templates HTMX (priorité moyenne)

Les partials HTMX qui ne changent pas souvent (listes d'événements, cartes,
navigation) peuvent être cachés au niveau du template :

```html
{% load cache %}

<!-- Cache le partial de la carte événement pendant 5 minutes, par tenant -->
<!-- / Cache event card partial for 5 min, per tenant -->
{% cache 300 event_card event.pk event.updated_at %}
    <div class="card" data-testid="event-card-{{ event.uuid }}">
        <h3>{{ event.name }}</h3>
        <span>{{ event.places_restantes }} {% translate "places restantes" %}</span>
    </div>
{% endcache %}
```

**Attention** : ne PAS cacher les éléments dynamiques (jauges temps réel, paniers,
formulaires). Seuls les éléments "quasi-statiques" sont candidats.

### 4. @cache_page sur les vues publiques (priorité moyenne)

Les pages publiques à fort trafic (liste d'événements, page d'accueil) peuvent
être cachées entièrement :

```python
from django.views.decorators.cache import cache_page

# Cache la page d'accueil publique pendant 2 minutes
# / Cache public homepage for 2 minutes
@cache_page(120)
def homepage(request):
    # ...
```

**Attention avec multi-tenant** : `cache_page` utilise l'URL comme clé.
Avec `django_tenants.cache.make_key`, le tenant est automatiquement inclus
dans la clé — donc OK pour notre stack.

### 5. Convention de nommage des clés cache (priorité basse)

Standardiser le format : `{module}:{objet}:{identifiant}:{tenant_schema}`

```python
# Convention actuelle (incohérente) :
cache_key = f"config_get_med_{pk}"              # BaseBillet
cache_key = f"crowds:list:summary:{tenant_id}"  # crowds
cache_key = f"api:sales:list:{schema}:..."      # api_v2

# Convention proposée :
cache_key = f"basebillet:config:media:{pk}"
cache_key = f"crowds:initiative:summary:{tenant_id}"
cache_key = f"api:sales:list:{tenant_id}:{start}:{end}"
```

## Fichiers concernés

| Fichier | Changement |
|---|---|
| `TiBillet/settings.py` | Remplacer Memcached par Redis, ajouter SESSION_ENGINE |
| `docker-compose.yml` | Supprimer service lespass_memcached |
| `requirements` / `pyproject.toml` | Vérifier que `redis` est dans les dépendances (déjà le cas via channels_redis) |
| Templates HTMX publics | Ajouter `{% cache %}` sur les partials quasi-statiques |
| Vues publiques (homepage, events list) | Ajouter `@cache_page` |
| Tous les fichiers avec `cache.set()` | Harmoniser les conventions de clés (optionnel) |

## Ordre de migration recommandé

1. **D'abord** : consolider sur Redis (remplacer Memcached) — changement infra simple
2. **Ensuite** : sessions Redis — changement config simple, gain immédiat
3. **Puis** : fragment caching templates — gains ciblés sur les pages à fort trafic
4. **Enfin** : convention de nommage — refactoring cosmétique, pas urgent

## Priorité

Moyenne-haute — la consolidation Redis est simple et élimine un service Docker.
Les sessions Redis réduisent la charge DB immédiatement. Le fragment caching
apportera des gains significatifs quand le trafic augmentera.
