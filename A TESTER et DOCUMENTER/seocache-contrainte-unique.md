# Fix SEOCache : doublons d'agrégats au flush (contrainte unique partielle)

## Ce qui a été fait

Le flush crashait systématiquement en fin de parcours
(`seo.models.SEOCache.MultipleObjectsReturned` dans `refresh_seo_cache`).

**Cause racine :** `unique_together = [("cache_type", "tenant")]` ne protège pas
les lignes d'agrégats globaux (`tenant=None`) car PostgreSQL considère les NULL
comme distincts dans un index unique. Pendant le flush, le worker Celery (rebuilds
déclenchés par les signaux du seed `demo_data_v2`) et la commande manuelle
`refresh_seo_cache` de `flush.sh` (qui appelle `rebuild_seo_aggregates(force=True)`
en bypassant le verrou debounce) écrivaient en même temps → `update_or_create`
créait des doublons → tous les rebuilds suivants crashaient.

**Fix :** deux `UniqueConstraint` partielles (compatibles PostgreSQL 13, qui ne
connaît pas `NULLS NOT DISTINCT`) :
- `(cache_type, tenant)` unique quand `tenant` est non-null ;
- `cache_type` unique quand `tenant` est null.
En cas de course, le `create` perdant lève `IntegrityError`, que `get_or_create`
rattrape nativement en relisant la ligne.

### Modifications
| Fichier | Changement |
|---|---|
| `seo/models.py` | `unique_together` → `Meta.constraints` (2 contraintes partielles) |
| `seo/migrations/0005_alter_seocache_unique_together_and_more.py` | RunPython de dédoublonnage (garde la ligne la plus récente par groupe) puis AddConstraint ×2 |

## Tests à réaliser

### Test 1 : flush complet (le scénario qui crashait)
1. `docker compose down -v && docker compose up -d`
2. `docker exec -ti lespass_django bash` puis `./flush.sh`
3. Attendu : le flush va au bout, `refresh_seo_cache` affiche
   « Termine : N tenants, X events, Y lieux / Done » sans traceback.

### Test 2 : course volontaire
```bash
docker exec lespass_django bash -c "cd /DjangoFiles && \
  (poetry run python manage.py refresh_seo_cache & \
   poetry run python manage.py refresh_seo_cache & wait)"
```
Attendu : les deux se terminent sans `MultipleObjectsReturned`.

### Vérification en base
```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from django_tenants.utils import schema_context
with schema_context('public'):
    from seo.models import SEOCache
    from django.db.models import Count
    print(list(SEOCache.objects.values('cache_type','tenant_id')
        .annotate(n=Count('id')).filter(n__gt=1)))"
```
Attendu : `[]` (aucun doublon).

## Vérifications déjà réalisées (session 2026-07-03)
- Migration appliquée sur la base de dev : 5 doublons supprimés, contraintes posées.
- 2 × `refresh_seo_cache` en parallèle : 0 traceback, 0 doublon.
- `tests/pytest/test_seo_cache_fragments.py` : 13 passed.
- `manage.py check` 0 issue, ruff propre sur les 2 fichiers.

## Compatibilité
- La migration dédoublonne AVANT de poser les contraintes : applicable sur une base
  qui contient déjà des doublons (prod incluse). On garde la ligne la plus récente —
  c'est du cache, il se reconstruit seul (beat toutes les 4 h ou commande manuelle).
