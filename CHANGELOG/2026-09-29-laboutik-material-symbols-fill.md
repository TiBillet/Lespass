# laboutik : icônes Material Symbols pleines (FILL) / filled Material Symbols icons

**Date :** 2026-09-29
**Migration :** Non / No

## Résumé / Summary

**Quoi / What :** les icônes de la caisse s'affichent en version pleine (`FILL 1`).
LaBoutik charge maintenant sa propre police Material Symbols **variable**, en local.
/ LaBoutik now ships its own local variable Material Symbols font, icons are filled.

**Pourquoi / Why :** la police fournie par django-unfold est **statique**.
Elle n'a pas de table `fvar`, donc pas d'axe `FILL`.
Avec elle, `font-variation-settings: 'FILL' 1` était ignoré sans erreur.
La police variable de Google a les axes `FILL`, `wght`, `GRAD` et `opsz`.
/ Unfold's font is static (no FILL axis), so the setting was silently ignored.

La police a un nom de famille propre (`Material Symbols Laboutik`).
Elle n'entre pas en conflit avec le `@font-face` d'Unfold : l'admin ne change pas.
/ Distinct family name, no clash with Unfold's @font-face; admin unchanged.

Poids : environ 4 Mo (police complète, 6 646 glyphes). Chargée une fois, puis en cache.
/ ~4 MB, cached after first load.

## Fichiers modifiés / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `laboutik/static/fonts/material-symbols/MaterialSymbolsOutlined-variable.woff2` | Nouvelle police variable (google/material-design-icons, `variablefont/`) |
| `laboutik/static/fonts/material-symbols/LICENSE` | Licence Apache 2.0 de la police |
| `laboutik/static/css/components.css` | `@font-face` local + classe `.material-symbols-outlined` sur la nouvelle famille, `FILL 1` |
| `laboutik/templates/laboutik/base.html` | Suppression du `<link>` vers la police statique d'Unfold |

## Déploiement / Deployment

- `collectstatic` nécessaire (nouveau fichier statique). / New static file, run collectstatic.
