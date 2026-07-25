# Carte page event : même fond que le réseau + une seule adresse principale / Event page map: same basemap as the network + a single main address

**Date :** 2026-07-16
**Migration :** Non

## Resume / Summary

### 1. La carte de la page évènement n'affichait plus les tuiles (403)

**Quoi / What :** sur la page d'un évènement, le bouton « Voir la carte » ouvrait
une carte qui restait parfois grise (tuiles non chargées), surtout sur Firefox.
/ On an event page, the "See the map" button opened a map that sometimes stayed
grey (tiles not loading), mostly on Firefox.

**Pourquoi / Why :** le partial de géolocalisation chargeait Leaflet depuis le CDN
**unpkg** et demandait ses tuiles à `tile.openstreetmap.org` — serveur à politique
d'usage stricte qui renvoie des **403** selon l'origine/referer du navigateur (d'où
la différence Firefox / Chrome). Leaflet est désormais **vendoré** dans
`pages/static/pages/vendor/leaflet/`, et le fond de carte est délégué au script
commun `static/cartes/tb_fond_de_carte.js` — celui qu'utilisent déjà le bloc
`CARTE_LEAFLET`, l'explorer du réseau et le widget de saisie d'adresse. Ce script
choisit MapTiler si une clé `MAPTILER_KEY` est configurée, sinon les tuiles
**OpenStreetMap France (HOT)** : en français, sans clé API, et sans 403.
/ The geolocation partial loaded Leaflet from the **unpkg** CDN and requested its
tiles from `tile.openstreetmap.org`, which returns **403** depending on the
browser's origin/referer. Leaflet is now **vendored** and the basemap is delegated
to the shared `tb_fond_de_carte.js` script (MapTiler with a key, OpenStreetMap
France HOT without).

La clé voyage par un attribut `data-maptiler-key` sur le conteneur de la carte,
jamais par une variable globale JavaScript. Elle est exposée à tous les gabarits
par le context processor `TiBillet.maptiler.maptiler_context`.
/ The key travels through a `data-maptiler-key` attribute, never a JS global.

### 2. Une seule adresse principale par lieu

**Quoi / What :** dans l'admin des adresses postales, on pouvait cocher « adresse
principale » (`is_main`) sur plusieurs adresses à la fois.
/ In the postal address admin, "main address" (`is_main`) could be ticked on
several addresses at once.

**Pourquoi / Why :** cocher une adresse comme principale **décoche désormais
automatiquement** les autres (la dernière cochée gagne). Une seule adresse
principale reste garantie par lieu, sans message d'erreur bloquant.
/ Ticking an address as main now **automatically unticks** the others (last one
wins). A single main address stays guaranteed per venue, with no blocking error.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `pages/templates/pages/classic/partials/evenement_geoloc.html` | Leaflet vendoré + appel à `tbPoserFondDeCarte()` au lieu d'unpkg + tile.openstreetmap.org |
| `BaseBillet/views.py` | `get_context()` expose `maptiler_key` (dispo pour toutes les pages) |
| `Administration/admin_tenant.py` | `PostalAddressAdmin.save_model()` : cocher `is_main` décoche les autres |
| `tests/pytest/test_event_map_tiles.py` | Nouveau — le partial charge Leaflet en local, appelle le fond de carte commun, et ne référence plus unpkg / tile.openstreetmap.org |
| `tests/pytest/test_postal_address_is_main.py` | Nouveau — une seule adresse principale après bascule |

---

## Comment tester (a la main) / Manual test

### Test 1 — la carte de l'évènement affiche bien ses tuiles

1. Ouvrir la page d'un évènement qui a une adresse postale géolocalisée.
2. Cliquer sur « Voir la carte ».
3. La carte s'affiche avec ses tuiles (pas de fond gris), en **Firefox comme en Chrome**.
4. Dans l'onglet Réseau du navigateur : aucune requête vers `unpkg.com` ni vers
   `tile.openstreetmap.org`. Les tuiles viennent de `api.maptiler.com` (si
   `MAPTILER_KEY` est configurée) ou de `tile.openstreetmap.fr/hot`.

### Test 2 — repli sans clé MapTiler

1. Retirer (ou vider) `MAPTILER_KEY` dans l'environnement, redémarrer le serveur.
2. Rouvrir la carte d'un évènement : elle s'affiche toujours, avec les tuiles
   OpenStreetMap France « Humanitarian ». Le repli est indispensable : une
   installation tierce sans compte MapTiler doit continuer à voir les cartes.

### Test 3 — une seule adresse principale

1. Admin → **Adresses postales** : cocher « adresse principale » sur l'adresse A,
   enregistrer.
2. Cocher « adresse principale » sur l'adresse B, enregistrer.
3. Rouvrir l'adresse A : la case est **décochée**. Aucun message d'erreur bloquant.

### Verifs automatisees / Automated checks

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_event_map_tiles.py -v
docker exec lespass_django poetry run pytest tests/pytest/test_postal_address_is_main.py -v
```
