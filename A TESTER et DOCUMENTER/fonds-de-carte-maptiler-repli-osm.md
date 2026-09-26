# Fonds de carte unifiés MapTiler + repli automatique OSM France HOT

Spec : `TECH_DOC/SESSIONS/WIDGET_GEO/04-fonds-de-carte-maptiler-repli-osm.md`

## Ce qui a été fait

- Les 4 cartes Leaflet utilisent le même fond : **MapTiler** (`dataviz-v4`) si `MAPTILER_KEY`
  est configurée, sinon **OSM France HOT**.
  - widget adresse : onboard `/onboard/place/` et wizard évènement `/event/wizard/map/` ;
  - page évènement (« Voir la carte ») ;
  - explorer : `/explorer/` et `/federation/` ;
  - infos pratiques du skin Faire Festival.
- Plus aucun appel à CartoDB, donc plus de filigrane « API KEY REQUIRED ».
- **Repli automatique** sur HOT si MapTiler échoue (quota, clé ou origine refusée). Il se
  déclenche une seule fois, et jamais sur une tuile isolée en erreur parmi des tuiles réussies.
- Widget : quand on déplace le marqueur vers un point sans rue ni ville, la rue et la ville
  déjà saisies sont conservées. La recherche, elle, ne change pas de comportement.

## Tests à réaliser

### Avant la mise en prod
Vérifier dans le dashboard MapTiler que la clé autorise le domaine ROOT (onboard) et les
domaines des tenants. Sinon, repli HOT permanent.

### Test 1 : widget adresse (wizard évènement)
1. Connecté, aller sur « Proposer / Ajouter un évènement », saisir un **nouveau** lieu.
2. **Attendu :** carte avec tuiles MapTiler (style épuré, labels FR), sans filigrane.
3. Taper une adresse, puis appuyer sur **Entrée** → marqueur et champs remplis. Le
   formulaire n'est **pas** envoyé.
4. Taper une autre adresse et cliquer sur la **loupe** → idem.
5. Glisser le marqueur dans une rue voisine → rue, code postal et ville mis à jour.
6. Glisser le marqueur en pleine campagne → la rue précédente est **conservée**.

### Test 2 : même chose sur l'onboard
`/onboard/place/` (étape « Votre lieu ») : points 2 à 6.

### Test 3 : simulation du quota épuisé (DevTools)
1. Chrome DevTools → Network → clic droit sur une requête `api.maptiler.com` →
   **Block request domain**. Recharger la page.
2. **Attendu :** tuiles `tile.openstreetmap.fr` et, en console, un warning
   « MapTiler indisponible, bascule sur OSM France HOT ». **Aucune** exception `Uncaught …`.
   Les lignes rouges de chargement de tuiles sont attendues : requêtes bloquées, et
   `Tile error:` sur la page évènement (log déjà présent avant ce chantier).
3. À refaire sur la page évènement (« Voir la carte »), `/federation/`, `/explorer/` (ROOT),
   `/infos-pratiques/` (skin Faire Festival) et le widget.

## Tests automatisés

```bash
docker exec lespass_django poetry run pytest \
  tests/pytest/test_widget_carte_adresse_tiles.py \
  tests/pytest/test_event_map_tiles.py \
  onboard/tests/test_step_place.py \
  tests/pytest/test_event_wizard_unifie.py -q
```

Validé le 2026-09-26 avec le Chromium Playwright du conteneur :
- nominal, 429 et 403 isolé sur les 4 cartes (+ `/explorer/`) ;
- déplacement avec une nouvelle tuile en 403 ;
- synchro du widget (Entrée, loupe, drag avec reverse partiel) ;
- 0 exception de page dans tous les cas.

## Compatibilité

- Aucune migration, aucune vue modifiée.
- `/static` est servi en `no-cache` en prod : le nouveau JS est pris en compte dès le redémarrage.
