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
