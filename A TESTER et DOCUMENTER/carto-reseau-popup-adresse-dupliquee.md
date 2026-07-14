# Carte du réseau — popup d'un lieu à l'adresse dupliquée

## Ce qui a été fait

Bug remonté : « les événements d'un lieu fédéré ne remontent pas ; on voit bien le marqueur sur
la carte, mais exactement la même adresse existe aussi dans les `PostalAddress` du lieu qui
affiche la carte — est-ce que ça ferait conflit ? »

**Réponse : pas de conflit de données.** `pa_id` est préfixé par l'UUID du tenant
(`"<tenant_uuid>:<pk>"`) et les événements sont indexés par adresse à l'intérieur de la boucle par
tenant. Deux lieux à la même adresse restent deux points distincts, chacun avec ses événements.

Le vrai problème était dans la carte : `marker.openPopup()` ne fait **rien** sur un marqueur
enfermé dans un cluster Leaflet, et deux adresses aux coordonnées identiques restent clusterisées
à **tous** les zooms. Le clic zoomait puis ouvrait un popup dans le vide.

Second bug trouvé au passage : le clic sur un lieu visait une adresse **au hasard** parmi les
siennes, au lieu de son adresse principale.

### Modifications

| Fichier | Changement |
|---|---|
| `seo/static/seo/explorer.js` | `focusOnLieu()` / `focusOnPA()` utilisent `markerCluster.zoomToShowLayer()` (zoome, ou *spiderfy* si les coordonnées sont identiques, puis ouvre le popup). Le marqueur visé est choisi parmi ceux réellement présents dans le cluster (les filtres texte/tag en retirent). Le surlignage du pin attend l'ouverture du cluster. |
| `seo/services.py` | `build_tenant_config_data()` expose `postal_address_id` (le flag `is_main_address` valait toujours `false`). `get_postal_addresses_for_tenants()` trie par `pk` (sans tri, PostgreSQL rend un ordre arbitraire qui dérive). |

**Décision de conception :** on ne supprime aucun marqueur en doublon et on n'en priorise aucun.
Deux structures fédérées peuvent réellement partager un bâtiment ; masquer le marqueur « sans
événement » ferait disparaître le lieu de la **liste** aussi (les cartes-lieu sont construites à
partir des points). C'est au gestionnaire de faire le ménage dans ses adresses s'il y a doublon.

## Prérequis

**Le cache SEO doit être reconstruit** — les fragments existants portent `is_main_address: false` :

```bash
docker exec lespass_django poetry run python manage.py shell -c \
  "from seo.tasks import refresh_seo_cache; refresh_seo_cache()"
```

## Tests à réaliser

### Test 1 : deux lieux à la même adresse (le bug remonté)

1. Dans l'admin du tenant qui affiche la carte, créer une `PostalAddress` avec les coordonnées
   **exactes** de l'adresse d'un lieu fédéré.
2. Reconstruire le cache SEO (commande ci-dessus).
3. Ouvrir `/federation/` sur ce tenant.
4. La carte affiche un cluster « 2 » à cet endroit.
5. Cliquer sur la **carte du lieu fédéré** dans la liste de gauche.
6. **Attendu :** le cluster s'écarte (spiderfy, les deux pins deviennent visibles côte à côte) et
   le popup du lieu fédéré s'ouvre, listant ses événements.
   *Avant le correctif : aucun popup ne s'ouvrait.*

### Test 2 : adresse principale

1. Prendre un lieu ayant **plusieurs** adresses (ex. `lespass` en dev).
2. Cliquer sur sa carte dans la liste.
3. **Attendu :** le popup ouvert est celui de l'adresse renseignée dans sa Configuration
   (l'adresse principale), pas une autre.

### Test 3 : mode « Événements »

1. Basculer sur la pilule **Événements**.
2. Cliquer sur la carte d'un événement du lieu fédéré.
3. **Attendu :** le popup de l'adresse de cet événement s'ouvre, avec ses événements.

### Test 4 : filtres

1. Filtrer par tag ou par texte de façon à masquer certains lieux.
2. Cliquer sur un lieu encore visible.
3. **Attendu :** le popup s'ouvre normalement, aucune erreur JS en console.
   *(Sans le garde `hasLayer`, `zoomToShowLayer()` lève un `TypeError` sur un marqueur retiré du
   cluster par un filtre.)*

## Tests automatisés

```bash
# pytest — services SEO (13 tests)
docker exec lespass_django poetry run pytest tests/pytest/test_seo_aggregate_points.py -q

# E2E — reproduit le bug dans un vrai navigateur (2 tests)
docker exec lespass_django poetry run pytest tests/e2e/test_explorer_adresse_dupliquee.py -q
```

Le test E2E crée lui-même l'adresse dupliquée, reconstruit le cache, vérifie l'ouverture du popup,
puis **supprime l'adresse et reconstruit le cache**. Il a été validé « en négatif » : sans le
correctif, il échoue bien sur l'absence de popup.

## Compatibilité

- Aucune migration.
- `zoomToShowLayer()` est fourni par la version de Leaflet.markercluster déjà vendorée
  (`seo/static/seo/vendor/leaflet/markercluster.js`). Un repli vers l'ancien comportement subsiste
  si la lib est absente.
- Le widget carte est **partagé** entre `/explorer/` (ROOT public) et `/federation/` (tenant) :
  les deux pages bénéficient du correctif.
