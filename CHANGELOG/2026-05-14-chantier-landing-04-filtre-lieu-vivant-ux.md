# Chantier landing #04 — Filtre "lieu vivant" + UX "Voir tous" → explorer

**Date :** 2026-05-14
**Migration :** Non
**Contributeurs / Contributors :** JonasFW13 (Jonas)

**FR :** Le cache SEO listait tous les tenants ayant un domaine, sans
verifier s'il y avait quelque chose a voir/acheter chez eux. En prod
avec 375 tenants, le marquee, `/lieux/`, la carte explorer et le
sitemap pointaient vers des dizaines de pages quasi-vides — bruit UX
et crawl budget gaspille pour Google + bots LLM.

1. **Filtre "lieu vivant"** sur `AGGREGATE_LIEUX` et `SITEMAP_INDEX` :
   un tenant n'apparait que s'il a un domaine ET (au moins 1 event
   futur publie OU au moins 1 produit BILLET/FREERES/ADHESION publie).
   Implementation : `seo/services.py::get_active_tenants_with_counts()`
   ramene `event_count` + `product_count` par tenant en 1 seule requete
   SQL (UNION ALL avec sous-selects scalaires). `seo/tasks.py` applique
   le filtre `lieu_est_vivant` avant de remplir `lieux` et
   `sitemap_tenants`. `TENANT_SUMMARY` / `TENANT_EVENTS` (caches
   per-tenant) restent inchanges.
2. **Chiffres cles supprimes** : "X lieux", "Y events" sur la landing
   — vanity metrics SaaS qui jurent avec le ton commun cooperatif. Bloc
   `stats-row` retire du template. `GLOBAL_COUNTS` n'est plus genere
   (suppression de `get_global_event_count()` dans `seo/services.py` et
   du bloc de generation dans `tasks.py`). Constante
   `SEOCache.GLOBAL_COUNTS` laissee dans `choices` pour eviter une
   migration de schema sur du code mort.
3. **UX "Voir tous"** : les 2 boutons sous les marquees pointent
   maintenant vers `/explorer/` (carte + filtres, vue interactive)
   plutot que `/lieux/` et `/evenements/`. Ces deux pages restent
   indexables pour le SEO/ranking mais ne sont plus mises en avant
   dans la navigation humaine.

**EN :** SEO cache listed every tenant with a domain, no check if there
was anything to see/buy there. In prod with 375 tenants, the marquee,
`/lieux/`, the explorer map and the sitemap pointed to dozens of
near-empty pages — UX noise and wasted crawl budget for Google + LLM
bots. Added an "alive venue" filter, removed vanity counters on the
landing, redirected "See all" buttons to `/explorer/` for humans.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `seo/services.py` | `get_active_tenants_with_event_count()` → `get_active_tenants_with_counts()` (+ `product_count`). `get_global_event_count()` supprime. Constante `CATEGORIES_PRODUIT_LIEU_VIVANT = ("B","F","A")`. |
| `seo/tasks.py` | Filtre `lieu_est_vivant` sur `aggregate_lieux` + `sitemap_tenants`. Suppression du bloc `GLOBAL_COUNTS`. Log final reflete `lieux_vivants` au lieu de `lieux totaux`. |
| `seo/views.py` | `landing()` : suppression de `lieux_count`, `events_count`, lecture `GLOBAL_COUNTS`. |
| `seo/templates/seo/landing.html` | Bloc `stats-row` retire. 2 boutons "Voir tous" → `/explorer/`. |

### Migration / Migration
- **Migration necessaire / Migration required :** Non.
- Anciennes entrees `SEOCache(cache_type='global_counts')` deviennent du
  data mort, ignorees a la lecture. Nettoyage automatique au prochain
  refresh ? Non — la step 6 ne supprime que les entrees rattachees a un
  tenant disparu, pas les entrees globales obsoletes. Pas grave : 1 ligne.
