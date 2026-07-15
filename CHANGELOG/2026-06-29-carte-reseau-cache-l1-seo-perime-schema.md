# Carte réseau : cache L1 SEO périmé par schema (cause racine du retard ~4h) / SEO L1 cache stale per-schema

**Date :** 2026-06-29
**Migration :** Non / No

**Quoi / What :** Cause racine confirmée du symptôme « les nouveaux events/adresses
n'apparaissent qu'au bout de plusieurs heures ». Le cache L1 Memcached lu par les
pages publiques restait **périmé jusqu'au TTL (4 h)** même après le recalcul.

**Pourquoi / Why :** `CACHES['default']` utilise
`KEY_FUNCTION = django_tenants.cache.make_key`, qui **préfixe chaque clé de cache
par le schema courant** (isolation cache par tenant). Or les agrégats SEO sont
**globaux** (`tenant=None`, partagés par tout le réseau). Le worker Celery exécute
le rebuild dans le schema du tenant déclencheur → il écrivait la clé sous
`lespass:…:seo:aggregate_lieux`, **invisible** depuis le schema `public` (page ROOT
`/explorer/`) et les autres tenants. Chaque schema avait sa propre copie L1 ; seule
celle du schema déclencheur était fraîche. Les autres lisaient du périmé jusqu'au
TTL 4 h (ou un MISS). Vérifié : L1 lu valait 19 en `public`/`lespass` mais 15 en
`le-coeur-en-or`/`chantefrein` pour la même donnée globale.

**Fix / Fix :** Les helpers L1 SEO (`set_memcached_l1` / `get_memcached_l1`)
épinglent désormais le schema `public` (`with schema_context("public")`) autour de
l'opération cache. La clé n'est donc plus préfixée par le schema d'exécution : une
**seule entrée L1 globale** est partagée par le worker, la page ROOT et chaque
tenant. Vérifié de bout en bout (Chrome) : après création d'un event, L1 identique
sur tous les schemas (public = lespass = le-coeur-en-or) et carte ROOT à jour en
~20 s, **sans rebuild manuel**.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `seo/services.py` | `set_memcached_l1` / `get_memcached_l1` : `with schema_context("public")` autour du `cache.set` / `cache.get` (clé L1 globale, non préfixée par tenant) |
| `tests/pytest/test_seo_cache_fragments.py` | +1 test : agrégat global écrit dans un schema tenant lu identique depuis public + autre tenant |

### Migration
- **Migration nécessaire / Migration required :** Non / No. Les anciennes clés L1
  préfixées par tenant expirent seules (TTL 4 h) et ne sont plus lues.
