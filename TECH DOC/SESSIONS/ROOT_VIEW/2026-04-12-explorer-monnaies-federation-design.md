# Spec — Explorer : visualisation des monnaies et fédérations

**Date** : 2026-04-12
**App concernée** : `seo/` (page `/explorer/`)
**Statut** : Design validé, prêt pour implémentation

## Problème

La page `/explorer/` liste actuellement les monnaies fédérées (assets `fedow_core`) comme simples cards sans interaction ni représentation géographique. L'utilisateur ne comprend pas :
- Quels lieux acceptent telle ou telle monnaie
- Comment les monnaies fédèrent le réseau
- La différence entre une monnaie locale (1 lieu) et la monnaie fédérée TiBillet (tous les lieux)

## Objectifs UX

Deux intentions validées en brainstorming :
1. **Diversité** — chaque lieu a ses propres outils d'échange, on les rend visibles
2. **Perspective utilisateur** — "où puis-je utiliser X monnaie ?" comme filtre pratique

Le aha moment visé : *cliquer sur une monnaie éclaire les lieux qui l'acceptent et montre les liens entre eux*.

## Design

### Modèle de données (existant, à enrichir côté fixture)

- `fedow_core.Asset.tenant_origin` → le lieu "créateur" de la monnaie
- `fedow_core.Asset.federated_with` → M2M vers `Federation`
- `fedow_core.Federation.tenants` → M2M vers `Client` (tenants qui partagent la fédération)
- `fedow_core.Asset.category` → `TLF` (locale), `TNF` (cadeau), `TIM` (temps), `FED` (fédérée TiBillet), `FID` (fidélité)

**Calcul des lieux acceptants pour un asset** :

```
lieux_acceptants(asset) = {asset.tenant_origin} ∪ ⋃(f.tenants for f in asset.federated_with)
```

### Règle de représentation visuelle

Pour chaque asset, 3 cas selon la donnée :

| Cas | Condition | Visuel |
|-----|-----------|--------|
| **Local** | 1 seul lieu acceptant | Highlight du lieu, pas de lignes |
| **Fédération partielle** | Plusieurs lieux, avec `tenant_origin` | **Style C** : arcs courbes depuis origine vers lieux acceptants |
| **Fédération globale (TiBillet)** | `category == FED` | **Style B** : polygone translucide enveloppant tous les lieux |

### Interactions

**Sur la carte monnaie dans la liste** :
- Clic → active le mode "monnaie focus" : highlight + liaisons + dim des autres lieux (opacité 0.3)
- La carte Leaflet fit bounds sur les lieux acceptants
- Clic à nouveau sur la même monnaie → désactive, retour à l'état normal
- Clic sur une autre monnaie → remplace la sélection

**Sur chaque carte lieu** :
- Ajouter une ligne de badges monnaies acceptées (ex: `💰 Monnaie locale` `🎁 Cadeau` `🔗 TiBillet`)
- Clic sur un badge → même effet qu'un clic sur la carte monnaie correspondante
- Curseur pointer sur les badges pour indiquer qu'ils sont interactifs

**Filtres existants** :
- Filtre "Monnaies" : liste affiche uniquement les cards monnaie
- Filtre "Tous" : les monnaies apparaissent après lieux/events/adhésions (ordre inchangé)

### Composants UI

**Card monnaie enrichie** :
- Icône type (💰 local, 🎁 cadeau, ⏰ temps, 🔗 fédéré, ⭐ fidélité)
- Nom de l'asset
- Badge "Catégorie" (Monnaie locale / Cadeau / Temps / Fédéré / Fidélité)
- Meta : "Accepté par N lieu(x)" + nom du lieu origine si pertinent
- Clic → activation du mode focus monnaie

**Badges monnaies sur carte lieu** (nouveau) :
- Rangée de pills compactes après `.explorer-card-meta`
- Petit icône + nom court
- Couleur de fond selon catégorie (cohérente avec les badges catégorie globaux)
- `role="button"` + `cursor: pointer` + `onclick="focusOnAsset(assetUuid)"`

**Légende contextuelle** (nouveau) :
- Position : bas-gauche de la carte, overlay flottant
- Visible uniquement quand un asset est sélectionné
- Contenu : icône catégorie + nom monnaie + origine + nombre de lieux

Exemple :
> 🟢 **Temps (Lespass)** — partagée avec 2 lieux

### Rendu des liaisons Leaflet

**Style C — Arcs depuis origine** :
- Implémentation retenue : `L.polyline` avec un tableau de points formant une courbe (Bézier quadratique discrétisée en ~20 segments). Pas de plugin externe.
- Point de contrôle de la courbe : milieu `(origine, cible)` décalé orthogonalement vers le haut d'une distance proportionnelle à la distance entre les deux points (ex: 0.3 × distance)
- Couleur : vert palette TiBillet (`#259d49`) avec 0.7 opacity
- Épaisseur : 2px
- Un arc par couple `(origine, lieu_acceptant)` — origine exclue de la liste des cibles

**Style B — Polygone convex hull** :
- Calculer le convex hull des lieux acceptants (algorithme : `L.polygon` avec points triés)
- Couleur remplissage : `rgba(37, 157, 73, 0.22)`
- Contour : `#259d49`, stroke 1.5px

**Dimming des lieux non acceptants** :
- Les marqueurs Leaflet non concernés gardent leur position mais passent à opacity 0.3
- Via une classe CSS `.explorer-pin--dimmed`

### Enrichissement fixture `demo_data_v2`

État actuel : tous les 5 assets appartiennent à `lespass`, aucune fédération créée.

Cible pour la démo :
- Créer 2 `Federation` :
  - "Réseau TiBillet Lyon" → tous les tenants (lespass, chantefrein, le-coeur-en-or, la-maison-des-communs, le-reseau-des-lieux-en-reseau)
  - "Échange local" → 2 tenants (lespass, chantefrein)
- Assets (étendus ou répartis) :
  - **TiBillet (FED)** : lié à "Réseau TiBillet Lyon" → Style B (polygone global)
  - **Monnaie locale (TLF)** : reste origine lespass, non fédérée → Style local (highlight seul)
  - **Temps (TIM)** : origine lespass, liée à "Échange local" → Style C (arc vers chantefrein)
  - **Cadeau (TNF)** : origine lespass, non fédérée → Style local
  - **Fidélité (FID)** : origine lespass, non fédérée → Style local
- Créer 1 asset supplémentaire pour un autre lieu pour montrer la diversité :
  - Ex: "Monnaie Coeur" (TLF) origine `le-coeur-en-or`

### Pipeline cache SEO

Le cache `AGGREGATE_ASSETS` existe déjà mais contient seulement `uuid`, `name`, `category`. À enrichir avec :
- `tenant_origin_id` (uuid du tenant origine, ou null)
- `tenant_origin_name` (nom lisible)
- `accepting_tenant_ids` (liste des uuid des tenants acceptants)
- `accepting_count` (int, nombre de lieux)
- `is_federation_primary` (bool, true si `category == FED`)

Mise à jour côté `services.py:get_all_assets()` — 1 requête SQL avec jointures sur `fedow_core_asset`, `fedow_core_asset_federated_with`, `fedow_core_federation_tenants`.

### `build_explorer_data()` côté serveur

Chaque asset dans `data.assets` sera enrichi avec les nouveaux champs ci-dessus. Pas de transformation côté JS.

### `build_tenant_config_data()` côté serveur

Ajouter dans le `TENANT_SUMMARY` de chaque lieu : `accepted_assets` (liste des uuid des assets acceptés par ce tenant).

Ça permet au JS d'afficher les badges monnaies par lieu sans refaire le calcul inverse.

### Côté JS (`explorer.js`)

Nouvelles fonctions :
- `focusOnAsset(assetUuid)` — déclenche le mode focus monnaie
- `clearAssetFocus()` — restaure l'état normal
- `drawAssetLinks(asset)` — dispatch vers `drawArcs()` ou `drawHull()` selon le cas
- `drawArcs(originLatLng, targetsLatLng[])` — rendu style C
- `drawHull(latLngs[])` — rendu style B (convex hull)
- `renderAssetLegend(asset)` — affiche la légende contextuelle
- `computeConvexHull(points)` — algorithme Graham scan ou similaire

Nouvel état global :
- `activeAssetUuid` — uuid de l'asset sélectionné, ou null
- `assetLayerGroup` — L.layerGroup() pour contenir arcs/polygone (clear facile)

### Boundaries et découpage

- Code serveur (services, tasks, fixtures) : isolé, pas de dépendance JS
- Nouveau JS isolable dans un module `explorer-assets.js` chargé en plus d'`explorer.js`, OU section dédiée dans `explorer.js` (gardons le fichier unique pour rester cohérent avec l'existant, on découpera si la taille devient un problème)
- CSS : nouvelle section "Assets focus mode" dans `explorer.css` (dimming, légende, badges lieu)

## Découpage en phases d'implémentation

1. **Phase 1 — Données** : enrichir fixture + `services.get_all_assets()` + `build_tenant_config_data()` pour remonter les champs nécessaires. Rafraîchir le cache.
2. **Phase 2 — Badges monnaies sur cards lieu** : UI simple côté JS, pas de carte encore. Les badges sont cliquables mais ne font rien.
3. **Phase 3 — Mode focus monnaie sur la carte** : implémentation des styles B et C + dimming + légende + gestion de l'état `activeAssetUuid`.
4. **Phase 4 — Connexion badges ↔ focus** : le clic sur un badge lieu déclenche le focus monnaie correspondant.

## Hors scope

- Animation des arcs (validé : pas d'animation)
- Vue détail d'une monnaie (page dédiée) — gardé pour plus tard
- Historique de sélection / breadcrumb
- Responsive mobile spécifique pour la légende (positionnement standard, ajusté en CSS si besoin)

## Testing

- Pytest : nouveau test `tests/pytest/test_seo_explorer_assets.py` pour valider le contenu enrichi de `build_explorer_data()` et `build_tenant_config_data()`
- Playwright : ajouter un spec `tests/playwright/tests/34-explorer-assets-focus.spec.ts` (numéro à ajuster selon le dernier existant au moment de l'implémentation) qui clique sur une monnaie et vérifie l'apparition du layer de liaisons + la classe dimmed sur les marqueurs

## Points ouverts

Aucun. Design validé en brainstorming.
