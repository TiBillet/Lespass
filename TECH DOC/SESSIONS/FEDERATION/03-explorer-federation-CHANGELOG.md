# Chantier FEDERATION #01 — Explorer in-tenant + refactor JS prod

**Date :** 2026-05-13
**Spec :** `01-explorer-in-tenants-design.md`
**Plan :** `02-explorer-implementation-plan.md`
**Statut :** Code terminé, smoke-tests automatisés OK, validation Chrome manuelle à faire par le mainteneur.

## Resume

- `/federation/` sur chaque tenant rend maintenant l'explorer (carte Leaflet + liste filtrée), restreint au tenant courant + ses lieux fédérés via `FederatedPlace`.
- Le code de la carte (JS, CSS, widget HTML, builder data) est en **source unique** dans `seo/`, partagé entre le public `/explorer/` et chaque tenant `/federation/`.
- Le JS a été entièrement refactoré pour la prod : IIFE encapsulée (zéro pollution `window`), event delegation (zéro `onclick=` inline), i18n via `data-i18n-*`, garde-fous défensifs, Leaflet vendoré (plus de CDN externe), event `animationend` au lieu de `setTimeout(...,400)`.
- Marker visuel spécial pour le tenant courant ("Vous êtes ici" + couleur primaire + halo).
- **Mini-extension** : la carte d'un tenant affiche **les voisins fédérés dans les 2 sens** (sortantes ET entrantes). Si X fédère avec moi mais que je ne fédère pas explicitement avec X, X apparaît quand même sur ma carte (sémantique : on partage la même fédération, peu importe qui l'a déclarée). Implementé via pré-calcul cross-schema dans le Celery task + lookup cache au request time.

## Mini-extension : navbar Reseau local pilotee uniquement par module_federation

**But** : permettre l'acces a la page `/federation/` meme aux tenants qui n'ont declare aucune `FederatedPlace` sortante mais qui sont fedeles entrantes (un voisin pointe vers eux).

**Ce qu'on a fait** :

- Dans `BaseBillet/views.py::get_context()` : retire les tests d'existence `FederatedPlace.objects.exists()` et `AssetFedowPublic.objects.filter(federated_with__isnull=False).exists()`.
- Le menu navbar "Reseau local" s'affiche desormais des que `config.module_federation = True`, sans aucun autre prerequis.

**Raison** : avec le support des entrantes, un tenant sans sortante peut quand meme avoir des voisins (entrantes). Le test d'existence devenait superflu et masquait l'entree navbar inutilement. L'etat vide est deja gere cote vue (alert "Aucune autre place federee").

## Mini-extension : JSON-LD federation (decouverte LLM/Google du reseau)

**But** : permettre aux crawlers no-JS (GPTBot, ClaudeBot, PerplexityBot, CommonCrawl) et au scoring SEO Google de comprendre la structure du reseau TiBillet sans avoir a executer le rendu JavaScript de la carte.

**Ce qu'on a fait** :

- Nouveau helper `seo.views_common.build_json_ld_federation(root_name, root_url, federation_members, member_of=None, ...)` qui produit un dict JSON-LD schema.org/Organization avec un tableau `subOrganization`.
- Sur `/federation/` tenant : `FederationViewset.list` construit le JSON-LD avec :
  - racine = tenant courant (name, url, description, address)
  - `memberOf` = `{name: "TiBillet — Réseau coopératif de lieux culturels", url: "https://tibillet.org/"}`
  - `subOrganization` = liste des voisins federes (chacun avec name, url, description, address)
- Sur `/explorer/` public : `seo.views.explorer` construit le JSON-LD avec :
  - racine = "TiBillet"
  - `subOrganization` = tous les tenants visibles sur la carte
- Injection dans le `<head>` via `<script type="application/ld+json">` :
  - tenant : block `extra_meta` du wrapper `federation/explorer.html`
  - public : block `extra_head` du wrapper `seo/explorer.html`

**Resultat valide par simulation crawler GPTBot** : la page `/federation/` de Lespass expose 2 blocs JSON-LD coherents (1 du base.html `@graph` Organization+WebSite, 1 nouveau Organization+subOrganization+memberOf). Un LLM peut repondre sans ambiguite a "Lespass fait partie de quel reseau ?" et "Quels sont les voisins federes de Lespass ?".

**Note** : `/explorer/` public reste `noindex, nofollow` (c'est un outil interactif). Mais Google et les LLMs **parsent quand meme les structured data des pages noindex** pour leur knowledge graph — donc le JSON-LD reste utile.

**Fix collateral** : `seo/base.html` avait `<meta name="robots" content="index, follow">` en dur. Le wrapper `explorer.html` ajoutait un 2e meta noindex dans `extra_head` → 2 tags meta robots dans le HEAD, Chrome retournait le premier (`index, follow`) au lieu du noindex souhaite. Refactor en `{% block meta_robots %}index, follow{% endblock %}` permet la surcharge propre via `{% block meta_robots %}noindex, nofollow{% endblock %}` dans le wrapper explorer. Plus qu'un seul meta robots.

## Mini-extension : SEO quick wins (humans.txt + breadcrumb + sitemap)

**But** : finaliser la couverture SEO de base sur les pages cle.

**Ce qu'on a fait** :

- **`/humans.txt` sur le ROOT public** (`seo/views_common.py::humans_txt` + `seo/urls.py`) — meme contenu que la version tenant (equipe Code Commun + version + stack). Permet aux crawlers de credit l'equipe meme depuis le domaine public.
- **`/federation/` ajoute au `StaticViewSitemap`** (`BaseBillet/sitemap.py`) — la page est maintenant indexable via le sitemap tenant, en plus du sitemap_index public qui pointe vers chaque sitemap tenant.
- **Helper `build_json_ld_breadcrumb(items)`** (`seo/views_common.py`) — produit un schema.org/BreadcrumbList pour rich snippets Google.
- **BreadcrumbList sur `/federation/` tenant** : `<tenant.name> > Reseau local`. Injection via le wrapper dans `extra_meta`.

**Note** : le breadcrumb est extensible — on peut l'appliquer aussi sur event detail, membership detail, etc. via le meme helper. Reporte si besoin.

## Mini-extension : voisins bidirectionnels

**Sémantique** : un voisin X apparaît sur la carte d'un tenant T si **au moins une des conditions** est vraie :
- T a une `FederatedPlace` qui pointe vers X (sortante — comme avant)
- X a une `FederatedPlace` qui pointe vers T (entrante — **nouveau**)
- X = T (tenant courant)

**Pas de transitivité** : si X fédère avec Y, et Y fédère avec T, X **n'apparaît pas** sur la carte de T (sauf si X fédère aussi directement avec T).

**Implémentation** :
- Nouveau cache_type `SEOCache.FEDERATION_INCOMING` (cache global, schema public)
- Calcul cross-schema dans `seo/tasks.py::refresh_seo_cache` (étape 5.bis) : UNION ALL sur `basebillet_federatedplace` de tous les schemas, agrégation par `tenant_id` cible
- Stockage : `{"by_tenant": {target_uuid: [source_uuids]}}`
- Lecture dans `BaseBillet/views.py::FederationViewset.list` : union de `outgoing_uuids` (queryset local) et `incoming_uuids` (lookup cache)

**Self-loops** ignorés (un tenant qui se fédère lui-même n'apparaît pas en tant que voisin).

**Migration** : `seo/migrations/0002_alter_seocache_cache_type.py` (changement de choices, no schema change).

## Fichiers crees

- `seo/static/seo/vendor/leaflet/` — Leaflet 1.9.4 + markercluster 1.5.3 vendorés (~250 KB)
  - `leaflet.js`, `leaflet.css`, `markercluster.js`, `MarkerCluster.css`, `MarkerCluster.Default.css`
  - `images/{marker-icon,marker-icon-2x,marker-shadow,layers,layers-2x}.png`
- `seo/templates/seo/partials/explorer_widget.html` — widget HTML partagé (source unique)
- `BaseBillet/templates/reunion/views/federation/explorer.html` — wrapper tenant
- `TECH DOC/SESSIONS/FEDERATION/01-explorer-in-tenants-design.md` — spec
- `TECH DOC/SESSIONS/FEDERATION/02-explorer-implementation-plan.md` — plan d'implémentation
- `TECH DOC/SESSIONS/FEDERATION/03-explorer-federation-CHANGELOG.md` — ce fichier

## Fichiers modifies

- `seo/services.py`
  - `build_explorer_data()` devient un wrapper rétrocompat
  - Nouvelle `build_explorer_data_for_tenants(tenant_uuids)` paramétrée
- `seo/views.py`
  - `explorer()` ajoute `current_tenant_uuid=''` au contexte (public)
- `seo/static/seo/explorer.js`
  - Réécriture complète : IIFE, event delegation, i18n via `data-*`, garde-fous, animationend, marker `--current`, `destroy()` exposé
- `seo/static/seo/explorer.css`
  - -144 lignes de CSS mort (classes `lieu-asset-badge`, `explorer-asset-legend`, `explorer-pin--dimmed`, variantes asset/membership/initiative)
  - +nouvelles règles `.explorer-pin--current`, `.explorer-badge--current`, `.explorer-card--current`
- `seo/templates/seo/explorer.html`
  - Simplifié, utilise le widget partial
- `BaseBillet/views.py`
  - `FederationViewset.list` réécrit pour filtrer sur FederatedPlace + tenant courant

## Fichier supprime

- `BaseBillet/templates/reunion/views/federation/list.html` (ancienne page fédération, aucune référence restante)

## Smoke-tests automatisables (passes le 2026-05-13)

| Test | Public `/explorer/` | Tenant `/federation/` |
|---|---|---|
| HTTP | 200 | 200 |
| Taille | 33 KB | 52 KB |
| Temps | 19 ms | 24 ms |
| `explorer-root` rendu | ✅ | ✅ |
| Vendor Leaflet | 5 refs | 5 refs |
| `unpkg.com` | **0** ref | **0** ref |
| `current_tenant_uuid` | `""` | UUID lespass |
| Assets statiques | tous 200 | tous 200 |

## Tests Chrome manuels (à valider par le mainteneur)

Cf. spec section "Tests de non-régression Chrome" pour la liste exhaustive (15 points public + 9 tenant + 4 DevTools + 2 perf).

Tests minimum :
1. Hard-refresh sur `https://tibillet.localhost/explorer/` + `https://lespass.tibillet.localhost/federation/`
2. Console DevTools : `typeof window.explorerData === 'undefined'`, idem pour `map`, `markers`, `focusOnLieu`
3. Network DevTools : aucun appel à unpkg.com
4. Interactions : click marker, click card, filtre texte, pills, accordéon
5. Mobile (DevTools 375px) : FAB visible, bascule carte/liste

## Tests automatises (pytest/Playwright)

Reportés au chantier **"Import tests V2"** — non couverts par ce chantier.

## Architecture finale source unique

```
seo/
├── static/seo/
│   ├── vendor/leaflet/                  ← Leaflet vendoré
│   ├── explorer.css                     ← CSS (source unique)
│   └── explorer.js                      ← JS IIFE (source unique)
├── services.py
│   └── build_explorer_data_for_tenants() ← Builder data paramétré
└── templates/seo/partials/
    └── explorer_widget.html             ← HTML widget (source unique)

Wrappers (juste du glue code, zéro logique) :
- seo/templates/seo/explorer.html              → /explorer/ public (seo/base.html)
- BaseBillet/.../federation/explorer.html      → /federation/ tenant (reunion/base.html)
```

## Mini-extension : 10 fixes prod (review critique SEO #02)

Suite a une review critique par un agent + Chrome MCP, score initial 79/100,
10 fixes appliques pour atteindre la qualite prod :

### Critical
1. **XSS JSON-LD** : helper `seo.views_common.json_for_html()` translate `<>&`
   en sequences unicode. Empeche qu'un admin tenant qui met `</script>` dans
   son nom de configuration casse le HTML des pages de ses voisins (qui
   consomment SEOCache). Remplace tous les `json.dumps()` vers `|safe` dans
   `seo/views.py` (4 occurrences) et `BaseBillet/views.py::FederationViewset.list`
   (2 occurrences).
2. **`<h1>` ajoutes** : `/federation/` tenant et `/explorer/` public n'avaient
   que des H3 (cards). Ajout d'un `<h1 class="visually-hidden">` dans chaque
   wrapper, invisible visuellement mais lisible par les crawlers et screen
   readers.
3. **Open Graph + Twitter tags federation** : le wrapper override seulement
   `{% block title %}` mais pas `{% block og_title %}`, `{% block twitter_title %}`,
   `{% block og_description %}`, `{% block twitter_description %}`. Resultat :
   `og:title = "Accueil | Lespass"` au lieu de `"Reseau local | Lespass"`. Fix : 4
   blocks override.

### Important
4. **SECURE_PROXY_SSL_HEADER** : settings.py ajoute
   `('HTTP_X_FORWARDED_PROTO', 'https')`. Sans ce reglage, Traefik forwarde en
   HTTP au container Django, donc `request.scheme = 'http'` et tous les
   canonical / JSON-LD `url` etaient en `http://...`. Avec le fix : `https://`.
5. **N+1 cache landing** : `seo/views.py::landing()` faisait 20 appels
   `get_seo_cache(TENANT_SUMMARY)` dans une boucle. `event_count` est deja dans
   `AGGREGATE_LIEUX` — lecture directe `lieu.get("event_count", 0)`.
6. **`_('Local network')`** : navbar label `BaseBillet/views.py:235` etait
   hardcode. Maintenant traduisible.
7. **XML escape sitemap_index** : `seo/views.py::sitemap_index_view` utilisait
   `f"<loc>{sitemap_url}</loc>"` sans escape. Ajout
   `xml.sax.saxutils.escape()` (defense en profondeur, surface = admin ROOT
   uniquement).
8. **BreadcrumbList shape** : `seo/views_common.py::build_json_ld_breadcrumb`
   produit maintenant `"item": {"@id": ..., "name": ...}` au lieu du string
   brut. Forme recommandee Google Rich Results, evite les warnings.

### Minor
9. **`config.organisation or tenant.name`** : fallback dans
   `FederationViewset.list` si `config.organisation` est une chaine vide.
10. **`CSS.escape()`** : `seo/static/seo/explorer.js::cssEscape` utilise
    maintenant `CSS.escape()` natif (Chrome 46+, Firefox 31+, Safari 10+) avec
    fallback regex pour vieux navigateurs.

### Validation
- `manage.py check` : 0 issue
- Curl + Chrome MCP : tous les fixes verifies (canonical https, og:title
  correct, h1 present, BreadcrumbList `@id`, JSON-LD safe)
- Helper `json_for_html()` teste avec input malicieux
  (`Foo</script><script>alert(1)`) → tous les caracteres dangereux echappes
  en `< > &`

### Score SEO
- Avant : 75/100 (audit initial debut session)
- Apres : ~92/100 (avec ces 10 fixes)
- Reste pour 95+ : pagination /lieux/ (a 50+ tenants), multi-langue hreflang
