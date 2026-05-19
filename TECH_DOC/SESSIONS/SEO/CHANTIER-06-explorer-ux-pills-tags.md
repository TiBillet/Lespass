# CHANTIER-06 — Explorer ROOT : pills exclusives, tags chips, URL partageable

**Type :** Spec design (brainstorming validé). Suivi par PLAN-06.

**Pré-requis :** CHANTIER-05 (1 marker par PostalAddress) terminé côté backend SEO et JS markers. Cette spec reprend la pile de PLAN-05 et corrige les régressions UX visibles : plus de liste d'événements, filtre "Événements" sans effet visuel, accordéon "Prochains événements" cassé.

**Date :** 2026-05-19. **Auteur :** Jonas + Claude (brainstorming).

---

## 1. Contexte et problème

Depuis CHANTIER-05, la carte `/explorer/` du ROOT affiche bien 1 marker par PostalAddress. Mais la liste latérale et la barre de filtres ont régressé :

- La fonction `renderList(tenants, events)` est appelée avec `events = []` (toujours). Plus aucune card "Événement" n'apparaît.
- `buildLieuAccordion` lit `lieu.events` mais les "lieux" viennent de `AGGREGATE_LIEUX.lieux` qui n'a pas ce champ (les events sont dans `points[i].events_futurs`). L'accordéon "Prochains événements" ne s'affiche plus jamais.
- Le filtre "Événement" restreint juste la liste des tenants à ceux ayant ≥1 event futur, mais affiche toujours des cards "Lieu". Visuellement, cliquer "Événement" ne change rien.
- `BaseBillet/views.py:1669` itère sur `explorer_data.get("lieux", [])` alors que `build_explorer_data_for_tenants` renvoie désormais `{"points": [...], "tenants": [...]}`. Le JSON-LD federation des explorers tenant est silencieusement vide.

En parallèle, le mainteneur anticipe l'arrivée de tenants "réseau régional" / "agenda culturel régional" qui auront 200+ PostalAddress. L'UX actuelle (cards tenant uniquement) ne permet pas de naviguer dans ce volume.

## 2. Objectif

Refondre l'UX de l'explorer ROOT pour :

1. Rendre les filtres réellement actionnables : la pill change visiblement la vue.
2. Permettre la navigation par tags (chercher tous les événements "jazz" sur la carte).
3. Permettre le partage d'URL : copier-coller transmet l'état complet des filtres.
4. Préserver la cartographie 1 marker = 1 PostalAddress (anticipation 200+ PA).
5. Réparer l'accordéon "Prochains événements" sur les cards lieu.
6. Corriger la régression `BaseBillet/views.py:1669` (`lieux` → `tenants`).

Hors scope :
- Tags au niveau PostalAddress ou Tenant. Les tags vivent sur `Event` uniquement (modèle existant).
- HTMX serveur. Tout est piloté côté client à partir du cache JSON déjà injecté.
- Sync de la position carte (center, zoom) dans l'URL.
- Modifications de l'explorer tenant (`/federation/`) au-delà du bug 1-ligne.

## 3. Décisions UX

### 3.1 Pills (filtre vue)

- **2 boutons exclusifs** : "Lieux" et "Événements". La pill "Tous" est supprimée.
- **Mode par défaut au chargement** : `Lieux` (préserve le comportement historique pour les visiteurs sans query string).
- L'état actif est reflété dans l'URL via `?v=lieu` ou `?v=event` (omis si défaut).

### 3.2 Markers (carte)

Comportement constant et indépendant du mode pill :

- **1 marker = 1 PostalAddress** active du réseau.
- Un tenant avec 24 PA produit 24 markers, regroupés en clusters Leaflet selon le zoom.

Le mode pill change uniquement la liste et la présentation du popup :

- **Mode Lieux** : popup avec nom de la PA, adresse, tenant, accordéon "Événements futurs (N)" cliquable.
- **Mode Événements** : popup avec event en avant (titre, date, image si dispo, lien direct vers `/event/<slug>/`). Si la PA a plusieurs events, on liste les 5 prochains avec un compteur.

### 3.3 Liste latérale

Filtrage : `text` (recherche) + `tag` (chip actif) + `view` (pill).

- **Mode Lieux** : 1 card par tenant (regroupe ses PA visibles). L'accordéon "Prochains événements" est rempli depuis les `events_futurs` agrégés sur toutes les PA du tenant qui passent les filtres.
- **Mode Événements** : 1 card par event futur. Tri chronologique. Chaque card affiche nom, date, lieu (PA + tenant), tags portés (max 3 affichés), lien `/event/<slug>/`.

**Empty state** :
- Si `tag` actif et 0 résultat : `"Aucun événement « {tag_name} » dans la zone visible. [Effacer le filtre]"`. Le lien efface uniquement `tag` (préserve `text` et `view`).
- Sinon : `"Aucun résultat."`.

### 3.4 Tag chips

- **Source** : tags portés par les events visibles (après filtres `text` + `view`, sans le filtre `tag` lui-même pour éviter la récursion).
- **Tri** : descendant par fréquence (nombre d'events qui portent le tag).
- **Cap** : top 10 affichés. Si plus de 10, un bouton `+ N tags` déplie un dropdown avec le reste.
- **Visibilité** : dans les deux modes (Lieux et Événements). En mode Lieux, un tag actif retire les PA dont aucun event ne porte ce tag.
- **Exclusivité** : 1 seul tag actif à la fois. Cliquer un tag actif le désactive.
- **Style** : fond coloré (couleur du tag, champ `tag.color` existant). Actif = bordure renforcée + icône check.
- **Recalcul** : à chaque mute de `state.filters` (sauf mute de `tag` lui-même).

### 3.5 URL partageable

Format : `?v=lieu|event&q=...&tag=<slug>`.

- Clés omises si valeur par défaut (`v=lieu`, `q=""`, `tag=null`). Une carte sans filtre = URL nue `/explorer/`.
- Pilotage côté client via `history.replaceState`, **pas** d'HTMX serveur (toutes les données sont déjà dans le cache JSON injecté côté client).
- Debounce de 300ms sur les mutations rapides (saisie texte).
- Au chargement, lecture de `URLSearchParams`, validation, présélection. Slug de tag invalide ou inexistant : ignoré silencieusement.

## 4. Impact backend

Les tags ne sont **pas** présents dans le cache SEO actuel. Ce chantier les ajoute.

### 4.1 Nouveau helper `seo/services.py:get_event_tags_for_tenants`

Signature : `get_event_tags_for_tenants(tenant_schemas: list[tuple[str, str]]) -> dict[event_uuid_str, list[dict]]`.

Implémentation :
- 1 requête SQL UNION ALL cross-schema sur `BaseBillet_event_tag` JOIN `BaseBillet_tag`.
- Renvoie `{event_uuid: [{"slug": ..., "name": ..., "color": ...}, ...]}`.
- Pattern identique à `get_events_for_tenants` (f-string pour le nom de schema, paramétré pour les valeurs).

### 4.2 Enrichissement dans `seo/tasks.py:refresh_seo_cache`

Après l'Étape 2 (`get_events_for_tenants`) :
- Collecter tous les `event.uuid` retournés.
- Appeler `get_event_tags_for_tenants(tenant_schemas)`.
- Joindre côté Python : chaque event reçoit un champ `tags = [...]`.

### 4.3 Propagation dans `seo/services.py:build_aggregate_points`

Dans `events_pour_popup`, ajouter `"tags": ev.get("tags", [])`. Forme finale :

```json
{
  "uuid": "abc-123",
  "name": "Soirée Jazz",
  "datetime_iso": "2026-06-15T20:00:00+00:00",
  "slug": "soiree-jazz",
  "tags": [{"slug": "jazz", "name": "Jazz", "color": "#0dcaf0"}]
}
```

Impact volume : ~10-30 % de cache JSON en plus selon densité M2M. Acceptable.

### 4.4 Bug `BaseBillet/views.py:1669` (inclus)

```diff
- for lieu in explorer_data.get("lieux", []):
+ for lieu in explorer_data.get("tenants", []):
```

Les clés consommées (`domain`, `name`, `short_description`, `locality`, `country`, `logo_url`, `tenant_id`) sont identiques entre `AGGREGATE_LIEUX.lieux` et la clé `tenants` re-exposée par `build_explorer_data_for_tenants`. Aucun autre changement nécessaire.

## 5. Impact frontend

### 5.1 `seo/static/seo/explorer.js`

Sections impactées :

- **state** : ajouter `filters.view`, `filters.tag`. Renommer `filters.category` (actuellement `'all'|'lieu'|'event'`) en `filters.view` (`'lieu'|'event'`).
- **bindPills** : suppression de la 3e pill, défaut `view = 'lieu'`.
- **applyFilters** : refonte complète. Nouvelles fonctions :
  - `filterPAsByTextAndTag(points, filters)` — renvoie PA visibles selon `text` (match sur nom PA, nom tenant, nom d'event) et `tag` (au moins 1 event de la PA porte le tag).
  - `collectVisibleEvents(pa_visibles, filters)` — extrait les events futurs visibles.
  - `buildLieuCardsFromPAs(pa_visibles)` — regroupe par tenant pour le mode Lieux.
  - `buildEventCards(events_visibles)` — 1 card par event pour le mode Événements.
  - `computeVisibleTagsTop10(pa_visibles, filters)` — agrège tags, compte, trie, slice.
- **buildLieuAccordion** : réparée. Source des events = `events_futurs` agrégés sur les PA visibles du tenant, pas `lieu.events` (champ inexistant).
- **updateChips** : nouvelle fonction. Rend les chips top 10 + bouton `+N` si nécessaire.
- **renderEmptyState** : enrichi avec lien "Effacer le filtre" si `tag` actif.
- **syncURL** : nouvelle fonction. `URLSearchParams` + `history.replaceState`. Debounce 300ms.
- **bootFromURL** : nouvelle fonction. Lit l'URL initiale, présélectionne `filters`, déclenche `applyFilters`.

### 5.2 `seo/templates/seo/partials/explorer_widget.html`

- Suppression de la pill "Tous".
- Ajout d'un conteneur `#explorer-tags` (chips) sous la barre pills.
- Ajout d'un conteneur `#explorer-empty-action` pour le lien "Effacer le filtre" (rendu par JS).

### 5.3 `seo/static/seo/explorer.css`

- Suppression / refonte du style `.explorer-pill[data-category="all"]`.
- Nouveau bloc `.explorer-tags`, `.explorer-tag-chip`, `.explorer-tag-chip--active`, `.explorer-tag-chip-more`.
- Adaptation `.explorer-card--event` pour le rendu enrichi (image, tags inline).

## 6. Tests

| Type | Fichier | Cas |
|---|---|---|
| pytest | `tests/pytest/test_seo_event_tags.py` (nouveau) | `get_event_tags_for_tenants` renvoie bien les tags par event, regroupés par schema. |
| pytest | extension `tests/pytest/test_seo_aggregate_points.py` | `build_aggregate_points` propage le champ `tags` dans `events_pour_popup`. |
| E2E | `tests/e2e/test_explorer_ux_pills_tags.py` (nouveau) | 4 tests : (1) clic pill Événements remplace les cards lieu par cards event, (2) clic chip filtre liste+markers et met à jour l'URL, (3) URL initiale `?v=event&tag=jazz` présélectionne pill et chip, (4) empty state affiche le lien "Effacer le filtre" et le clic restaure la liste. |

Les tests JS unitaires purs ne sont pas prévus (pas de framework JS dans le projet — toute la couverture client passe par Playwright).

## 7. Migration et compatibilité

- **Migration DB** : aucune. Pas de changement de schéma.
- **Cache SEO** : un seul refresh suffit (`docker exec lespass_django poetry run python manage.py shell -c "from seo.tasks import refresh_seo_cache; refresh_seo_cache()"`). Les events_futurs gagnent un champ `tags`, mais le code JS lit avec `.tags || []` (rétrocompatible avec un cache non encore rafraîchi).
- **Explorer tenant** (`/federation/`) : continue de consommer `build_explorer_data_for_tenants`. La correction du bug `BaseBillet/views.py:1669` restaure le JSON-LD federation sans changer la structure. Pas d'autre modification.
- **Rollback** : possible. Suppression de `get_event_tags_for_tenants`, retour à l'ancien `explorer.js`. Le bug 1-ligne reste corrigé indépendamment.

## 8. Self-review

Vérifié :
- Aucun placeholder TBD/TODO.
- Cohérence interne : `filters.view` et `filters.tag` apparaissent dans les sections 3.1, 3.4, 3.5, 5.1 avec le même sens.
- Scope : focalisé. Pas de refactor non lié. Pas de feature hors objectif (tags sur PA, sync carte, HTMX serveur — tous explicitement hors scope §2).
- Ambiguïté : `q` cherche dans nom PA + nom tenant + nom d'event (explicité §5.1). Tag = exclusif, désactivable (§3.4). URL omet les clés par défaut (§3.5).
- Tags absents du cache : signalé §4. Pas un placeholder, c'est une décision technique.

## 9. Suite

PLAN-06 produit par writing-plans. Découpage indicatif :

1. Backend : `get_event_tags_for_tenants` + tests.
2. Backend : enrichissement `refresh_seo_cache` + propagation `build_aggregate_points` + tests.
3. Bug `BaseBillet/views.py:1669` (commit séparé).
4. Frontend : template (pills + chips conteneur).
5. Frontend : JS refonte `applyFilters`, `buildLieuAccordion` réparé.
6. Frontend : `buildEventCards`, `computeVisibleTagsTop10`, `updateChips`.
7. Frontend : `syncURL` + `bootFromURL`.
8. Frontend : CSS chips + empty state.
9. Tests E2E.
10. CHANGELOG + doc test manuel.
