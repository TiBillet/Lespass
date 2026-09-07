# Reseau V2 : page au style « Autour du lieu » + filtre par type de lieu et distance / V2 Network page: mockup style + venue type filter and distance

**Date :** 2026-08-31
**Migration :** Non

## Resume / Summary
**Quoi / What :** La page Réseau (`/federation/`, skin V2) adopte la maquette
`pages/TEMP/autour-du-lieu.html` : en-tête de page (eyebrow/titre/intro), layout
2 colonnes (recherche + filtres + cartes à gauche, carte dans un `.map-panel` à
droite avec bouton « Réseau TiBillet »), cartes au look `.place-card`. Le moteur
explorer (recherche, pills Lieux/Événements, tag chips, carte Leaflet, accordéons
événements) est **conservé**. Nouveautés : filtre par **type de lieu**
(`Client.categorie`, pills affichées en vue Lieux) et **distance à vol d'oiseau**
sur chaque carte lieu (« 📍 X km » / « 📍 Sans lieu fixe »).
/ The Network page (V2 skin) adopts the autour-du-lieu mockup while keeping the
explorer engine. New: venue type filter (Client.categorie) and straight-line
distance on each venue card.

**Pourquoi / Why :** Refonte graphique V2 demandée par la maquette. Le type de
lieu et la distance n'existaient pas dans `explorer_data` : ils sont enrichis
côté serveur, uniquement pour cette page.

**Isolation des impacts :** l'enrichissement n'est fait que dans
`FederationViewset.list`. Le JS ne rend le badge type, les pills de type et la
distance QUE si les clés existent → la page publique `/explorer/` est inchangée ;
le skin classic garde sa coquille (`explorer_widget.html`) et ne voit que le
badge/distance en plus (styles de base ajoutés à `explorer.css`).
/ The enrichment only happens in the tenant Network view. The JS renders the new
elements only when the keys exist → public /explorer/ is unchanged; the classic
skin keeps its shell and only gains the badge/distance.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/views.py` | Nouveaux helpers module-level `_distance_km_haversine()` et `_enrichir_explorer_data_avec_type_et_distance()` (1 requête `Client` SHARED_APPS, garde anti-UUID invalides, clé `distance_km` absente si origine non géocodée) ; appel dans `FederationViewset.list` après `appliquer_options_federation` |
| `pages/templates/pages/V2/vues/reseau.html` | Coquille réécrite au style maquette (page-header, around-layout, search-bar, filter-tabs, results-line, map-panel) en conservant tous les ids/data-* attendus par `explorer.js` ; n'inclut plus `seo/partials/explorer_widget.html` ; bouton « Réseau TiBillet » → tibillet.coop/explorer ; nouveau conteneur `#explorer-type-pills` ; FAB mobile conservé |
| `seo/static/seo/explorer.js` | `state.filters.typeLieu` + pills de type générées depuis les catégories présentes (`renderTypePills`, visibles seulement en vue Lieux, reset au passage en vue Événements) ; filtre `paMatchesTypeLieu` ; badge type + distance dans `buildLieuCard` (rendus seulement si données enrichies) ; helper `formatDistanceKm` (locale du document) ; 2 chaînes i18n (`data-i18n-tout`, `data-i18n-sans-lieu-fixe`) |
| `seo/static/seo/explorer.css` | Styles de base `.explorer-badge--type` et `.explorer-card-dist` (pour le skin classic) |
| `pages/static/V2/css/V2.css` | Section « PAGE RESEAU » : overrides préfixés `#explorer-root` (grille 2 colonnes, carte dans map-panel, pills tag-pill, cards place-card, mobile FAB) |
| `tests/pytest/test_federation_enrichissement.py` | 6 tests : haversine (nominal + zéro), enrichissement catégorie+distance, point sans coordonnées → `None`, clé absente sans origine géocodée, robustesse UUID invalides |

### Correctifs post-livraison (retour terrain) / Post-delivery fixes
Appliqués le même jour après recette visuelle :
1. **Tag chips masquées en vue Lieux** — elles n'apparaissent plus qu'en vue
   Événements (symétrique avec les pills de type). Le tag actif est
   **réinitialisé** au passage en vue Lieux et au boot si l'URL porte `?tag=`
   avec la vue par défaut (sinon filtre invisible). Règle appliquée uniquement
   quand `#explorer-type-pills` existe (page Réseau V2) : `/explorer/` public et
   le skin classic conservent les chips dans les 2 vues.
2. **Compteur en vue Événements** — « X lieux » affichait 0 (cartes lieux non
   construites) ; on compte désormais les PA visibles (= lieux avec au moins un
   événement visible), cohérent avec les marqueurs de la carte.
3. **Tenant courant en premier** — tri stable dans `buildLieuCardsFromPAs`, la
   carte « Vous êtes ici » remonte en tête sans perturber le tri configuré
   (`tri_des_lieux`). No-op sur la page publique.
4. **Couleurs « Vous êtes ici »** — bordure de la carte et badge passent de
   `--bs-primary` (bleu Bootstrap) à `--color-primary` du skin V2 (overrides
   préfixés `#explorer-root`, `!important` requis sur la bordure).
/ Same-day fixes after visual review: tag chips hidden in Venues view (with tag
reset), venue counter fixed in Events view, current venue card first, "You are
here" colours switched to the skin primary colour.

### Choix d'implementation / Implementation notes
- Le filtre type utilise `Client.categorie` (Artiste, Scène, Festival, Tourneur,
  Producteur, Agenda culturel) — les types de la maquette (Tiers-lieu, Collectif…)
  n'existent pas en base.
- « Ce qu'on a fait ensemble » et les tags de relation de la maquette : abandonnés
  (aucune donnée correspondante).
- La clé `distance_km` n'existe que si l'adresse du tenant courant est géocodée :
  sinon le JS afficherait « Sans lieu fixe » sur tous les lieux à tort.
- Les pills de type ne sont pas synchronisées dans l'URL (contrairement à
  vue/recherche/tag) — choix de simplicité.
- Traductions : nouvelles chaînes `_()`/`{% translate %}` (Nos relations, Autour
  de…, Sur la carte, Réseau TiBillet, Tout, Sans lieu fixe…) — workflow
  makemessages/compilemessages à lancer (non fait dans cette session).

---

## Comment tester (a la main) / Manual test

### Test 1 — page Reseau V2 nominale
1. Tenant avec skin V2 + quelques FederatedPlace, adresse géocodée.
2. Ouvrir `/federation/`.
3. Vérification attendue : en-tête « Autour de … », layout 2 colonnes, cartes
   au look place-card avec badge de type (Scène, Festival…) et distance « 📍 X km »,
   carte Leaflet à droite dans le panneau avec la toolbar « Sur la carte » +
   bouton « Réseau TiBillet » (ouvre tibillet.coop/explorer dans un nouvel onglet).
4. Recherche texte, pills Lieux/Événements, tag chips et accordéons événements :
   fonctionnement identique à avant.

### Test 2 — filtre par type de lieu
1. En vue **Lieux** : une rangée de pills « Tout · Festival · Scène … » apparaît
   (seulement les catégories présentes dans les données). **Les chips de tags
   sont masquées dans cette vue.**
2. Cliquer « Festival » : seules les cartes/marqueurs des festivals restent ;
   le compteur se met à jour.
3. Passer en vue **Événements** : la rangée de pills de type disparaît, le filtre
   est réinitialisé (tous les événements visibles), **les chips de tags
   apparaissent** et fonctionnent comme avant. Le compteur affiche « N lieux · M événements »
   avec N = lieux ayant au moins un événement visible (jamais 0 quand des événements sont listés).
4. Retour en vue **Lieux** : un éventuel tag actif en vue Événements est réinitialisé au retour (pas de filtre
   invisible).

### Test 3 — distance et cas limites
1. Lieu fédéré sans adresse (option « afficher lieux sans adresse » active) :
   carte affichée avec « 📍 Sans lieu fixe ».
2. Tenant courant SANS coordonnées GPS sur son adresse : aucune distance ni
   « Sans lieu fixe » affichés (badge de type toujours présent).

### Test 4 — pas de régression
1. Page publique `/explorer/` (tenant root) : aucune pill de type, aucun badge
   type, aucune distance — comportement identique à avant.
2. Skin classic `/federation/` : coquille historique conservée.
3. Mobile (< 992px) : liste visible, FAB « Carte » bascule sur la carte plein
   écran ; clic sur une carte lieu bascule aussi sur la carte.

### Test 5 — tenant courant mis en avant
1. La première carte de la liste est le lieu courant : bordure verte (couleur primaire du
   skin), badge « Vous êtes ici » de la même couleur, pas de bleu Bootstrap.
2. Charger `?tag=xxx` sans `v=event` : le tag est ignoré (reset au boot), les
   lieux s'affichent non filtrés.

### Verifs automatiques
- `docker exec lespass_django poetry run pytest tests/pytest/test_federation_enrichissement.py -v`
- `docker exec lespass_django poetry run pytest tests/pytest/test_federation_view_integration.py tests/pytest/test_federation_config.py -v`
- Vérification visuelle Chrome avant les tests (règle CSS), y compris navigation
  HTMX aller-retour depuis l'accueil.
