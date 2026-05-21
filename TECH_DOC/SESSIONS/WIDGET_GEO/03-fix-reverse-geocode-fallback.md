# 03 — Correctif : repli reverse-geocode quand la recherche par nom est incomplète

**Date :** 2026-05-21
**Fichier :** `static/widgets/widget_carte_adresse.js`

## Symptôme

Sur la page carte du wizard évènement (lieu pré-rempli avec le **nom** du lieu),
le marqueur se plaçait mais les champs adresse (rue / code postal / ville)
restaient partiellement vides. Une recherche manuelle d'une **adresse réelle**
remplissait bien tous les champs.

## Cause

La recherche **forward** (`/search`) par un **nom de lieu** (ex : « Café Test »)
renvoie souvent un **match flou** : un centroïde (ville / POI proche) dont le
dict `address` ne contient ni `road` ni `postcode`. Le remplissage des champs
dépendait de ce dict forward incomplet. Le code de la recherche auto (au load)
et de la recherche manuelle est **identique** (`lancer_recherche_nominatim`) —
la différence venait donc uniquement de la qualité du résultat selon la requête.

## Correctif

Le **drag du marqueur** faisait déjà un géocodage **inverse** (fiable : rue + CP +
ville garantis). On mutualise ce mécanisme et on l'utilise **en repli** :

- Extraction de la logique reverse dans un helper partagé
  `reverse_geocoder_et_remplir(lat, lng)` (utilisé par le drag ET le repli).
- Dans `lancer_recherche_nominatim`, après avoir placé le marqueur : si l'adresse
  forward est **incomplète** (`!address.road || !address.postcode`), on relance un
  reverse-geocode sur les coordonnées trouvées pour compléter les champs.

Conséquence : une recherche par nom remplit désormais les champs de façon fiable ;
une recherche d'adresse réelle (déjà complète) ne déclenche **pas** de requête
supplémentaire (respect de la politique Nominatim 1 req/s).

## Vérifié

`node --check` OK. Test Chrome : recherche par nom inventé → marqueur + champs
adresse complets après le repli reverse.
