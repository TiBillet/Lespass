# Chantier FEDERATION #01 — Explorer in-tenant + refactor JS prod / In-tenant explorer + production-grade JS refactor

**Date :** 2026-05-13
**Migration :** Non
**Contributeurs / Contributors :** JonasFW13 (Jonas)

**FR :** `/federation/` (Réseau local) sur chaque tenant rend maintenant l'explorer
(carte Leaflet + filtres) avec uniquement le tenant courant + ses FederatedPlace.
Le code de la carte est consolidé en source unique dans `seo/` (JS + CSS + widget
HTML + data builder), partagé avec le public `/explorer/`. Le JS a été refactoré
pour la prod : IIFE encapsulé (zéro pollution `window`), event delegation (zéro
`onclick=` inline), i18n via `data-i18n-*`, garde-fous défensifs (try/catch JSON,
DOM presence), Leaflet vendoré (plus de CDN externe unpkg.com), event Leaflet
`animationend` au lieu de `setTimeout(...,400)`. Marker visuel "Vous êtes ici"
pour le tenant courant.

**EN :** `/federation/` (Local network) on each tenant now renders the explorer
(Leaflet map + filters) limited to the current tenant + its FederatedPlace.
Map code is consolidated as a single source under `seo/` (JS + CSS + widget HTML +
data builder), shared with the public `/explorer/`. The JS has been refactored
for production: encapsulated IIFE (zero `window` pollution), event delegation
(zero inline `onclick=`), i18n via `data-i18n-*`, defensive guards (try/catch
JSON, DOM presence), vendored Leaflet (no external unpkg.com CDN), Leaflet
`animationend` event instead of `setTimeout(...,400)`. Visual "You are here"
marker for the current tenant.

**Fichiers :** voir `TECH DOC/SESSIONS/FEDERATION/03-explorer-federation-CHANGELOG.md`

---
