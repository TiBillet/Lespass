# Chantier SEO #01 — Decouverte LLM/Google du reseau federe / LLM and Google discovery of the federated network

**Date :** 2026-05-13
**Migration :** Oui (`seo/0002_alter_seocache_cache_type.py`)
**Contributeurs / Contributors :** JonasFW13 (Jonas)

**FR :** Trois axes pour rendre le reseau TiBillet visible aux LLMs (GPTBot,
ClaudeBot, PerplexityBot, CommonCrawl) et a Google.

1. **Voisins bidirectionnels** : la carte d'un tenant affiche les voisins
   declarations dans les 2 sens. Si X federate avec moi mais que je n'ai pas
   declare X dans mes `FederatedPlace`, X apparait quand meme. Pre-calcul
   cross-schema dans le Celery task `refresh_seo_cache`, stockage en
   `SEOCache.FEDERATION_INCOMING`. La navbar "Reseau local" est desormais
   pilotee uniquement par `config.module_federation`.

2. **JSON-LD federation** : nouvelle helper
   `seo.views_common.build_json_ld_federation()` qui produit un schema.org/
   Organization + `subOrganization` + `memberOf`. Injecte sur `/federation/`
   tenant (racine = tenant, subOrg = voisins federes, memberOf = reseau
   TiBillet) et sur `/explorer/` public (racine = TiBillet, subOrg = tous les
   tenants). Les crawlers no-JS recoivent immediatement la structure du
   reseau sans avoir besoin d'executer Leaflet. Fix collateral : `meta_robots`
   devient un `{% block %}` dans `seo/base.html`.

3. **Quick wins SEO** :
   - `/humans.txt` sur le ROOT public (manquait avant)
   - `/federation/` ajoute au `StaticViewSitemap` tenant
   - Helper `build_json_ld_breadcrumb()` + BreadcrumbList sur `/federation/`

**EN :** Three axes to make the TiBillet network visible to LLMs (GPTBot,
ClaudeBot, PerplexityBot, CommonCrawl) and Google.

1. **Bidirectional neighbors**: a tenant's map shows neighbors declared in
   both directions. If X federates with me but I haven't declared X in my
   `FederatedPlace`, X still appears. Cross-schema pre-computation in the
   `refresh_seo_cache` Celery task, stored in `SEOCache.FEDERATION_INCOMING`.
   The "Local network" navbar is now driven solely by `config.module_federation`.

2. **Federation JSON-LD**: new helper
   `seo.views_common.build_json_ld_federation()` produces a schema.org/
   Organization + `subOrganization` + `memberOf`. Injected on `/federation/`
   tenant (root = tenant, subOrg = federated neighbors, memberOf = TiBillet
   network) and on `/explorer/` public (root = TiBillet, subOrg = all
   tenants). No-JS crawlers immediately receive the network structure without
   executing Leaflet. Collateral fix: `meta_robots` becomes a `{% block %}`
   in `seo/base.html`.

3. **SEO quick wins**:
   - `/humans.txt` on public ROOT (was missing)
   - `/federation/` added to tenant `StaticViewSitemap`
   - `build_json_ld_breadcrumb()` helper + BreadcrumbList on `/federation/`

**Fichiers :** voir `TECH DOC/SESSIONS/FEDERATION/03-explorer-federation-CHANGELOG.md`

---
