# Carte page event (fond de carte) + une seule adresse principale

## Ce qui a été fait

### Tâche 1 — Fond de carte de la page évènement

Le partial `reunion/views/event/partial/geoloc.html` (bouton « Voir la carte » sur la page d'un
évènement) chargeait Leaflet depuis le CDN **unpkg** et ses tuiles depuis `tile.openstreetmap.org`.
Ce serveur renvoie des **403** selon l'origine/referer du navigateur (d'où les blocages sur Firefox
et pas sur Chrome).

On reprend maintenant le **même fond de carte que la carto réseau** (`/federation/`) :
- **Leaflet vendoré** en local (`seo/static/seo/vendor/leaflet/`), plus de CDN.
- **MapTiler** si `MAPTILER_KEY` est configurée, sinon **OpenStreetMap France (HOT)** — français,
  sans clé API, fonctionne en localhost, pas de 403.

Pour ça, `get_context()` (`BaseBillet/views.py`) expose désormais `maptiler_key` (utile à toutes les
pages, pas seulement l'event).

### Tâche 2 — Une seule adresse principale (`is_main`)

Dans l'admin des adresses postales, cocher « adresse principale » sur une adresse **décoche
automatiquement** toutes les autres du même lieu (la dernière cochée gagne). `PostalAddressAdmin.save_model()`
applique la bascule ; la requête tourne dans le schéma du tenant, donc c'est bien par lieu.

**Note :** `PostalAddress.is_main` n'est pas la même chose que `Configuration.postal_address` (l'adresse
principale lue par la carto/SEO). Ce correctif ne concerne que le booléen `is_main` de l'admin.

### Modifications

| Fichier | Changement |
|---|---|
| `BaseBillet/templates/reunion/views/event/partial/geoloc.html` | Leaflet vendoré + fond MapTiler/OSM France HOT |
| `BaseBillet/views.py` | `get_context()` : `maptiler_key` |
| `Administration/admin_tenant.py` | `PostalAddressAdmin.save_model()` : bascule `is_main` |

## Tests à réaliser

### Test 1 : carte de la page évènement (le bug remonté)

1. Ouvrir un évènement dont l'adresse a des coordonnées, ex.
   `https://lespass.tibillet.localhost/event/<slug>/`.
2. Déplier « Heure et lieu », cliquer sur **« Voir la carte »**.
3. **Attendu :** la carte s'affiche avec les tuiles (labels en français, style OSM France), un
   marqueur sur le lieu et un popup nom + adresse. Aucune tuile grise.
4. **Sur Firefox ET Chrome** : ouvrir la console → pas de `403`, pas de `tileerror` ; on doit voir
   `Tile layer loaded successfully`.
5. Si une `MAPTILER_KEY` est configurée sur l'instance : les tuiles viennent de `api.maptiler.com`
   (style dataviz-v4). Sinon, de `tile.openstreetmap.fr/hot`.

### Test 2 : une seule adresse principale

1. Admin → Adresses postales. Créer/éditer deux adresses.
2. Cocher **« adresse principale »** sur l'adresse A, enregistrer.
3. Cocher **« adresse principale »** sur l'adresse B, enregistrer.
4. **Attendu :** A n'est plus principale, B l'est. Une seule adresse principale dans la liste.
5. Enregistrer une adresse C **non** principale ne doit pas décocher B.

## Tests automatisés

```bash
docker exec lespass_django poetry run pytest \
  tests/pytest/test_event_map_tiles.py \
  tests/pytest/test_postal_address_is_main.py -q
```

- `test_event_map_tiles.py` : rend le partial et vérifie le bon fond (OSM France HOT / MapTiler),
  et l'absence d'unpkg + du gabarit de tuile `tile.openstreetmap.org`. Non-flaky (pas de réseau).
- `test_postal_address_is_main.py` : exerce `PostalAddressAdmin.save_model` et vérifie qu'il reste
  exactement une adresse principale après bascule.

## Compatibilité

- Aucune migration.
- Leaflet vendoré déjà présent (`seo/static/seo/vendor/leaflet/`), partagé avec la carto réseau.
- `get_context()` ajoute une clé au contexte : sans effet sur les pages qui ne l'utilisent pas.
