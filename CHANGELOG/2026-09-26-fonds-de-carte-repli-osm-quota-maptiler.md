# Fond de carte : repli automatique OSM France si MapTiler échoue / Basemap: automatic OSM France fallback when MapTiler fails

**Date :** 2026-09-26
**Migration :** Non

## Resume / Summary

### 1. Repli automatique quand le quota MapTiler est épuisé

**Quoi / What :** toutes les cartes Leaflet passent par le fond commun
`tbPoserFondDeCarte()` (`static/cartes/tb_fond_de_carte.js`). Avec une clé MapTiler, la
carte bascule maintenant **une seule fois** sur les tuiles OpenStreetMap France HOT dans
deux cas :
- **aucune** tuile MapTiler n'a réussi au premier affichage (quota, clé ou origine refusée) ;
- **5** tuiles en erreur au total (quota épuisé en cours de visite).

Une tuile isolée en erreur, parmi des tuiles réussies, ne déclenche **rien**.
/ Every Leaflet map goes through the shared `tbPoserFondDeCarte()`. With a MapTiler key,
the map now switches ONCE to OSM France HOT tiles when no MapTiler tile ever loaded, or
after 5 tile errors.

**Pourquoi / Why :** quand le quota gratuit MapTiler (100 000 requêtes/mois) est dépassé,
MapTiler renvoie 403/429 et les cartes restaient **grises**. Le repli HOT n'existait que
si la clé était absente.
/ Over quota, MapTiler returns 403/429 and maps stayed grey: the HOT fallback only
applied when no key was set.

**Piège Leaflet 1.9.4 (P.WIDGET.5) :** retirer la couche dans un handler `load` fait lever
un `TypeError` (Leaflet lit `this._map` juste après `fire("load")`). Le retrait est donc
différé par `setTimeout(…, 0)`.

Le repli est écrit **une seule fois**, dans le fond commun. Il couvre : widget adresse
(onboard, wizard évènement), géoloc de la page évènement (classic et V2), bloc lieu
(classic, faire_festival, V2, V2 horizontal), accueil V2, explorer (`/explorer/`,
`/federation/`).
/ The fallback is written once, in the shared basemap, and covers every map.

### 2. Widget adresse : un géocodage inverse partiel n'efface plus la rue

**Quoi / What :** quand on déplace le marqueur (ou qu'on clique sur la carte) vers un
point où Nominatim ne renvoie ni rue ni ville, la rue et la ville déjà saisies sont
conservées.
/ Dragging the marker to a point without street or city keeps the values already typed.

**Pourquoi / Why :** sur le **chemin reverse** seulement (drag, clic carte, repli après
recherche), un champ n'est plus écrasé par une valeur vide. La **recherche** garde son
comportement : une recherche vers un lieu sans rue vide la rue, et la validation serveur
de l'onboard (rue obligatoire) force l'utilisateur à la corriger.
/ Only the reverse path keeps non-empty fields; forward search still blanks the street.

### 3. Clé MapTiler du widget par un tag de gabarit

**Quoi / What :** le widget lit la clé via le tag `{% maptiler_key %}` (`tibitags`).
/ The widget reads the key through the `{% maptiler_key %}` template tag.

**Pourquoi / Why :** le widget est rendu par un widget de formulaire, sans contexte de
requête : le context processor `maptiler_context` n'y est pas appliqué.
/ The widget renders without a request context, so the context processor does not run.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `static/cartes/tb_fond_de_carte.js` | Repli dynamique MapTiler → OSM France HOT ; `tbCreerCoucheOsmHot()` ; liste des appelants à jour |
| `BaseBillet/templatetags/tibitags.py` | `simple_tag` `maptiler_key` |
| `templates/widgets/widget_carte_adresse.html` | `{% load tibitags %}` + `data-maptiler-key="{% maptiler_key %}"` |
| `static/widgets/widget_carte_adresse.js` | Garde « non vide » rue / ville sur le chemin reverse |
| `tests/pytest/test_widget_carte_adresse_tiles.py` | Nouveau — clé passée au widget, repli présent dans le fond commun, chaque carte appelle `tbPoserFondDeCarte`, plus de `cartocdn`, garde-fous P.WIDGET |
| `tests/pytest/test_event_map_tiles.py` | La page évènement transmet la clé au fond commun |
| `tests/PIEGES.md` | + P.WIDGET.5 (retrait de couche dans `load`) |
| `TECH_DOC/SESSIONS/WIDGET_GEO/04-fonds-de-carte-maptiler-repli-osm.md` | Spec |

---

## Comment tester (a la main) / Manual test

### Avant la mise en prod
Vérifier dans le dashboard MapTiler que la clé autorise le domaine ROOT (onboard,
`/explorer/`) et les domaines des tenants. Sinon : repli HOT permanent (fonctionnel, mais
pas le style voulu).

### Test 1 — widget adresse (wizard évènement)
1. Connecté, aller sur « Proposer / Ajouter un évènement », saisir un **nouveau** lieu.
2. **Attendu :** carte avec tuiles MapTiler (style épuré, labels FR), sans filigrane.
3. Taper une adresse, puis appuyer sur **Entrée** → marqueur et champs remplis. Le
   formulaire n'est **pas** envoyé.
4. Taper une autre adresse et cliquer sur la **loupe** → idem.
5. Glisser le marqueur dans une rue voisine → rue, code postal et ville mis à jour.
6. Glisser le marqueur en pleine campagne → la rue précédente est **conservée**.

### Test 2 — même chose sur l'onboard
`/onboard/place/` (étape « Votre lieu ») : points 2 à 6.

### Test 3 — simulation du quota épuisé (DevTools)
1. Chrome DevTools → Network → clic droit sur une requête `api.maptiler.com` →
   **Block request domain**. Recharger la page.
2. **Attendu :** tuiles `tile.openstreetmap.fr` et, en console, un warning
   « tb_fond_de_carte : MapTiler indisponible, bascule sur OSM France HOT ». **Aucune**
   exception `Uncaught …`. Les lignes rouges des tuiles bloquées sont attendues.
3. À refaire sur : page évènement (« Voir la carte »), bloc lieu d'une page, accueil V2,
   `/federation/`, `/explorer/` (ROOT), et le widget.

### Tests automatisés
```bash
docker exec lespass_django poetry run pytest \
  tests/pytest/test_widget_carte_adresse_tiles.py \
  tests/pytest/test_event_map_tiles.py -q
```
