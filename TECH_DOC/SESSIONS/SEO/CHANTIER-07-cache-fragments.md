# CHANTIER 07 — Cache SEO en fragments par tenant + agrégats par recombinaison

> **Hub :** [INDEX.md](INDEX.md) · [SPEC.md](SPEC.md)
> **Date :** 2026-06-01
> **Plan d'implémentation :** [PLAN-07-cache-fragments.md](PLAN-07-cache-fragments.md)
> **Contraintes projet :** aucune opération git de l'assistant · pas de
> `makemessages`/`compilemessages` auto · règle des 3 fichiers avant `check` + tests ·
> serveur tenu par le mainteneur dans byobu.

## 1. Contexte et objectif

`seo/tasks.py:refresh_seo_cache` recalcule **tout** le cache SEO en une passe :
fragments par tenant (`TENANT_SUMMARY`, `TENANT_EVENTS`) **et** agrégats globaux
(`AGGREGATE_EVENTS/LIEUX/POINTS`, `SITEMAP_INDEX`, `FEDERATION_INCOMING`), via des
requêtes `UNION ALL` cross-schema sur **tous** les schemas tenant.

Deux problèmes à l'échelle prod (≈ 500 tenants) :
1. **Le `UNION ALL` sur 500 schemas** (events, products, federatedplaces) est une requête
   géante que PostgreSQL planifie mal.
2. **Toute modif d'un seul event/adresse** (cf. CHANTIER carto, bug 4) ne peut être reflétée
   sans relancer ce recalcul intégral — beaucoup trop lourd avec 500 tenants et un volume
   élevé de `post_save`.

**Objectif :** rendre le cache SEO scalable à 500 tenants et permettre une mise à jour quasi
temps réel de la carto après modif, **sans** jamais recalculer les schemas des autres tenants.

## 2. Constat structurant (vérifié)

Les vues consomment **uniquement les agrégats** (`AGGREGATE_*`, `SITEMAP_INDEX`,
`FEDERATION_INCOMING`). Les fragments `TENANT_SUMMARY`/`TENANT_EVENTS` sont **écrits mais
jamais lus** (`get_seo_cache` n'est jamais appelé avec un `tenant_uuid`). Les fragments ne
servent donc que de **source intermédiaire** pour recomposer les agrégats.

➡️ Conséquence de conception : mettre à jour la carto = mettre à jour les **agrégats**. Le
fragment d'un tenant n'a d'intérêt que recombiné.

## 3. Architecture cible : producteur (fragments) / agrégateur (recombinaison)

Trois fonctions, granularité de recalcul découplée :

| Fonction | Rôle | Coût |
|---|---|---|
| `refresh_tenant_seo_cache(tenant_id)` | Recalcule les fragments d'**un** tenant : `TENANT_SUMMARY`, `TENANT_EVENTS`, **`TENANT_POINTS`** (nouveau) | 1 schema, léger |
| `rebuild_seo_aggregates()` | Recompose `AGGREGATE_EVENTS/LIEUX/POINTS` + `SITEMAP_INDEX` par **lecture des fragments + concat** | lecture `SEOCache` + Python, **0 cross-schema** |
| `refresh_seo_cache()` (existant) | Orchestrateur du **beat 4 h** : boucle `refresh_tenant_seo_cache` sur tous les tenants + `rebuild_seo_aggregates()` + `FEDERATION_INCOMING` + nettoyage stale | filet anti-dérive |

**`FEDERATION_INCOMING`** dépend des `FederatedPlace` (pas des events/adresses) → recalculé
**uniquement dans l'orchestrateur beat**, pas dans `rebuild_seo_aggregates` (sinon `UNION ALL`
federatedplace inutile à chaque rebuild).

## 4. Déclenchement et débounce (le cœur de la tenue à 500 tenants)

| Déclencheur | Action | Débounce |
|---|---|---|
| `post_save`/`post_delete` Event/PostalAddress du tenant X | `refresh_tenant_seo_cache(X)` | **par tenant** : lock `seo_refresh_tenant_{uuid}`, 60 s |
| idem (même signal) | `rebuild_seo_aggregates()` | **global** : lock `seo_rebuild_aggregates`, **180 s** |
| Celery beat | `refresh_seo_cache()` complet | 4 h |

**Principe :** la charge de `rebuild` est **bornée par le débounce global** (≤ 1 rebuild /
180 s = ≤ 20/h), **indépendamment** du volume de `post_save`. Aucun `post_save` ne déclenche
de recalcul cross-schema : seul le fragment du tenant concerné (1 schema) + une recombinaison.

**Ordonnancement** : le fragment (countdown court) est rafraîchi avant le rebuild (countdown
180 s) → le rebuild recombine des fragments à jour. Si un fragment est encore en file au
moment d'un rebuild, l'agrégat reflètera ce tenant au rebuild suivant ; le beat 4 h garantit
la cohérence finale (convergence éventuelle, acceptable pour du SEO).

## 5. Le nouveau fragment `TENANT_POINTS`

Nouveau `cache_type` sur `SEOCache` (ajout dans `CACHE_TYPE_CHOICES` → migration `alter`
no-op DB, comme `0002/0003`). `data = {"points": [...]}` : les points (PA géocodées) du
tenant, produits par `build_aggregate_points([(uuid, schema)], …)` (déjà capable de traiter
1 tenant). Intègre les fixes carto récents (`pa_id` préfixé `{uuid}:{pk}`, `image_url`,
`tenant_image_url`).

`AGGREGATE_POINTS` devient la **concaténation** des `TENANT_POINTS` (recombinaison).

## 6. Réutilisation des helpers existants

Les helpers de `seo/services.py` prennent déjà des **listes** de tenants → réutilisables pour
1 tenant : `get_events_for_tenants([t])`, `get_event_tags_for_tenants([t])`,
`build_tenant_config_data(client)`, `build_aggregate_points([t], …)`. Seul
`get_active_tenants_with_counts()` (sans paramètre) a besoin d'une variante 1-tenant (counts
events + products sur 1 schema).

`rebuild_seo_aggregates` réapplique le filtre « lieu vivant » (domaine + `event_count > 0` OU
`product_count > 0`) sur les fragments `TENANT_SUMMARY` pour `AGGREGATE_LIEUX` / `SITEMAP`.

## 7. Compatibilité

- **Vues inchangées** : mêmes `cache_type` consommés. Seul le **producteur** change.
- **Équivalence** : après refactor, `refresh_seo_cache()` complet doit produire des agrégats
  **identiques** à l'ancienne version (même contenu `AGGREGATE_*`). Test d'équivalence.
- **Migration** : seulement l'`alter` du champ `cache_type` (ajout `TENANT_POINTS`), no-op DB.

## 8. Tests (pytch, conteneur up)

1. `refresh_tenant_seo_cache(X)` n'écrit que `TENANT_SUMMARY/EVENTS/POINTS` **du tenant X**
   (pas les agrégats, pas les autres tenants).
2. `rebuild_seo_aggregates()` reconstruit `AGGREGATE_POINTS` = concat des `TENANT_POINTS`
   existants (et n'exécute **aucune** requête cross-schema — il lit `SEOCache`).
3. **Équivalence** : `refresh_seo_cache()` complet produit le même `AGGREGATE_*` qu'avant le
   refactor (snapshot des compteurs : tenants/events/lieux/points).
4. Débounce : 2 `post_save` rapprochés sur le même tenant → 1 seul `refresh_tenant` ; sur
   tenants différents → 1 seul `rebuild` global.

## 9. Hors scope

- `FEDERATION_INCOMING` reste sur le beat (pas de signal `FederatedPlace` dédié ici).
- Pas de rebuild incrémental (delta par tenant dans l'agrégat) : recombinaison complète, qui
  reste légère et est bornée par le débounce. À envisager seulement si le rebuild devient un
  point chaud mesuré.
