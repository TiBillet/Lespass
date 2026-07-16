# Carte explorer : markers synchronisés au mode « Événements » + barre de recherche resserrée / Explorer map: markers synced with "Events" mode + tightened search bar

**Date :** 2026-06-29
**Migration :** Non / No

**Quoi / What :** Sur la carte explorer, en mode « Événements », les markers ne
montrent plus que les lieux ayant au moins un événement visible (les lieux sans
événement à venir disparaissent de la carte). La barre de recherche et le toggle
« Lieux / Événements » forment un groupe compact **centré** (au lieu d'une barre
pleine largeur avec les boutons collés au bord). Le fondu dégradé qui estompait à
tort le bouton « Événements » est retiré.

**Pourquoi / Why :** Les markers réagissaient déjà aux filtres texte et tag (via
`updateMapMarkersByPA`), mais le toggle Lieux/Événements ne changeait que la liste
de gauche, pas les markers. Côté layout, la barre s'étirait sur toute la largeur
(boutons collés au bord), puis une 1ʳᵉ tentative laissait un grand vide au milieu.

**Fix / Fix :** Dans `applyFilters()`, la source des markers visibles dépend du
mode : en mode « événement », `visiblePaIds` est construit depuis les `pa_id` des
événements visibles (`eventCards`) au lieu de toutes les PA. CSS : le groupe
`.explorer-search-row` est borné (`max-width: 760px`) et **centré** (`margin: 0 auto`),
la barre (`flex:1` + `min-width:0`) remplit jusqu'au toggle (plus de vide) ; retrait
du `mask-image` (fondu droit) sur `.explorer-pills` qui estompait le bouton
« Événements » (toggle à 2 boutons → jamais de scroll) ; responsive mobile conservé.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `seo/static/seo/explorer.js` | `applyFilters` : markers = lieux avec events visibles en mode « événement » |
| `seo/static/seo/explorer.css` | groupe recherche+toggle borné et compact à gauche (responsive mobile conservé) |

### Migration
- **Migration nécessaire / Migration required :** Non / No (front statique).
- Note : vider le cache navigateur / hard reload pour récupérer les statiques.
