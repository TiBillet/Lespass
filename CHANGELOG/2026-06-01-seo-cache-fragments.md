# Cache SEO — fragments par tenant + agrégats par recombinaison

**Date :** 2026-06-01
**Migration :** Oui

> Spec : `TECH_DOC/SESSIONS/SEO/CHANTIER-07-cache-fragments.md` · Plan : `PLAN-07-…`.
> Implémenté et **vérifié** (conteneur up) : `check` OK, équivalence des agrégats OK,
> 28 tests pytch verts (SEO + fédération).

## Ce qui a été fait

Refonte de `seo/tasks.py` en **producteur / agrégateur** :
- `refresh_tenant_seo_cache(tenant_id)` : fragments d'1 tenant (`TENANT_SUMMARY`,
  `TENANT_EVENTS`, `TENANT_POINTS`). 1 schema.
- `rebuild_seo_aggregates()` : recompose `AGGREGATE_*` + `SITEMAP_INDEX` par recombinaison
  des fragments (zéro cross-schema).
- `refresh_seo_cache()` : orchestrateur beat 4 h (tous fragments + rebuild +
  `FEDERATION_INCOMING` + nettoyage stale).
- Signal `post_save`/`post_delete` Event/PostalAddress → `refresh_tenant_seo_cache(tenant)`
  (débounce **par tenant**, 60 s) + `rebuild_seo_aggregates` (débounce **global**, 180 s).

## Tests automatisés (vérifiés)

```bash
KEY=$(docker exec -e TEST=1 lespass_django poetry run python manage.py test_api_key | tail -1)
docker exec -e TEST=1 -e API_KEY="$KEY" lespass_django poetry run pytest \
  tests/pytest/test_seo_cache_fragments.py \
  tests/pytest/test_seo_aggregate_points.py tests/pytest/test_seo_event_tags.py \
  tests/pytest/test_federation_config.py tests/pytest/test_federation_view_integration.py -q
# -> 28 passed
```

## Tests manuels / vérifications

### Équivalence (déjà constatée sur la dev DB)
```bash
docker exec lespass_django poetry run python manage.py shell -c \
"from seo.tasks import refresh_seo_cache; print(refresh_seo_cache())"
# -> {'tenants': 6, 'events': 20, 'lieux': 5} ; AGGREGATE_POINTS = 4, 0 collision pa_id
```

### Refresh ciblé d'un tenant (ne touche que ses fragments)
```bash
docker exec lespass_django poetry run python manage.py shell -c \
"from seo.tasks import refresh_tenant_seo_cache; from Customers.models import Client; \
print(refresh_tenant_seo_cache(str(Client.objects.get(schema_name='lespass').uuid)))"
# -> {'tenant': '...', 'events': N, 'points': M, 'vivant': True}
```

### Débounce (en prod / avec worker Celery)
1. Modifier un event dans l'admin d'un tenant → vérifier dans les logs Celery qu'un
   `refresh_tenant_seo_cache(<uuid>)` est programmé (countdown 30 s) + un
   `rebuild_seo_aggregates` (countdown 180 s).
2. Modifier 3 events du **même** tenant en < 60 s → **un seul** `refresh_tenant` (débounce
   tenant). Modifier des events de tenants **différents** en < 180 s → **un seul** `rebuild`
   (débounce global).
3. La carto `/explorer/` et `/federation/` reflète la modif après le rebuild (~3 min).

## Points d'attention

- **`FEDERATION_INCOMING`** (arêtes entrantes) dépend des `FederatedPlace`, pas des
  events/adresses → recalculé **uniquement au beat 4 h** (pas sur post_save).
- **Débounce global = curseur charge/fraîcheur** : 180 s borne le rebuild à ≤ 20/h quel que
  soit le volume de modifs. Ajustable dans `BaseBillet/signals.py`.
- **Vues inchangées** : elles lisent les mêmes `AGGREGATE_*`. Seul le producteur a changé.
- **Worker Celery requis** pour le `apply_async(countdown=…)`. Le beat 4 h reste le filet.
