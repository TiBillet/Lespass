# Widget carte adresse — Tests manuels

## Ce qui a été fait

Nouveau widget Django réutilisable pour saisir une adresse géolocalisée :
- Carte Leaflet avec barre de recherche intégrée (leaflet-geosearch).
- Suggestions live Nominatim côté navigateur (1 req/s par user, géré par la lib).
- Marqueur draggable avec géocodage inverse côté serveur (cache Redis 24h).
- 4 champs adresse séparés auto-remplis depuis le résultat Nominatim.
- Préfixe `identifiant_widget` pour permettre N widgets sur la même page.

Premier consommateur : refonte de la step 03_place du wizard onboard.

### Modifications

Cf. `CHANGELOG.md` section "Widget de saisie d'adresse géolocalisée" + spec
`TECH_DOC/SESSIONS/WIDGET_GEO/01-design-spec.md`.

## Tests à réaliser

### Préalable

```bash
# Restart byobu si tu as touché aux templatetags ou ajouté des routes URL
# (Django scanne ces ressources au démarrage, pas à chaud).

# Vérification serveur
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
docker exec -e API_KEY=dummy lespass_django bash -c "cd /DjangoFiles && poetry run python -m pytest tests/pytest/test_widget_*.py onboard/tests/ -q"
```

### Test 1 : Search live + auto-remplissage
1. Aller sur `/onboard/identity/` puis valider avec un email pour atterrir sur `/onboard/verify/`.
2. Saisir l'OTP (ou bypass DEBUG en dev).
3. Sur `/onboard/place/` : la carte Leaflet est affichée centrée sur la France.
4. Cliquer dans la barre de recherche en haut à droite de la carte → taper "10 rue de Rivoli Paris".
5. **Attendu :** suggestions live apparaissent en dessous de la barre.
6. Cliquer sur la 1re suggestion.
7. **Attendu :** marqueur draggable placé sur la carte, carte centrée dessus, et les 4 champs adresse en dessous se remplissent automatiquement (rue, code postal, ville, pays).

### Test 2 : Drag du marqueur (reverse geocode)
1. Sur `/onboard/place/` après Test 1.
2. Drag du marqueur de ~50 mètres.
3. **Attendu :** au drop, les 4 champs adresse se mettent à jour (nouveau quartier / nouvelle rue selon Nominatim). Pas de flash visuel sur la carte.
4. Vérifier dans DevTools Network : GET vers `https://nominatim.openstreetmap.org/reverse?lat=...&lon=...&format=json&addressdetails=1&accept-language=fr`, réponse 200 JSON avec `display_name` + `address`.

   **Note architecture (revert 2026-05-15)** : le reverse appelle Nominatim **direct depuis le navigateur** (pas de proxy serveur). Pas de cache mutualisé mais évite le problème multi-tenant routing.

### Test 3 : Click direct sur carte (sans search)
1. Sur `/onboard/place/` page fraîche.
2. Cliquer directement sur un point de la carte (sans utiliser la search).
3. **Attendu :** marqueur placé, fetch reverse, champs adresse remplis.

### Test 4 : Submit complet
1. Sur `/onboard/place/` après une search réussie.
2. Cliquer "Continuer".
3. **Attendu :** redirect vers `/onboard/descriptions/`. En DB :

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from django_tenants.utils import schema_context
from MetaBillet.models import WaitingConfiguration
with schema_context('meta'):
    wc = WaitingConfiguration.objects.order_by('-id').first()
    print('lat:', wc.latitude, 'lng:', wc.longitude, 'street:', wc.street_address)
"
```

### Test 5 : Resume (coords pré-remplies)
1. Aller sur `/onboard/descriptions/` puis revenir manuellement sur `/onboard/place/`.
2. **Attendu :** carte centrée sur l'adresse précédemment saisie, marqueur déjà placé, search bar vide (pas de re-geocode au load).

### Test 6 : Locale (anglais vs français)
1. Modifier la locale Django : `?lang=en` dans l'URL OU changer le `LANGUAGE_CODE` de la session.
2. Aller sur `/onboard/place/` → search "Brussels Belgium".
3. **Attendu :** `display_name` retourné en anglais ("Brussels, Belgium").
4. Repasser en `lang=fr` → search "Bruxelles Belgique" → "Bruxelles, Belgique".

### Test 7 : Réseau coupé pendant un drag
1. DevTools → Network → throttling → Offline.
2. Drag du marqueur.
3. **Attendu :** marqueur reste placé, hidden inputs lat/lng à jour, console.warn "reverse fetch error" loggué dans DevTools, **pas d'alert UI bruyant**.

### Test 8 : Throttle serveur
1. Faire 2 drags rapprochés (< 1s).
2. **Attendu :** le 2e POST vers `/widgets/geocode-reverse/` renvoie 429 (DRF AnonRateThrottle 1/s/IP). Côté UI, marqueur reste placé, lat/lng à jour, champs non re-remplis (gracieux dégradé).

### Test 9 : N widgets sur même page (cas hypothétique futur)
Pas testable directement aujourd'hui (le wizard n'a qu'un widget). À tester quand on intègrera dans Event admin avec un 2e identifiant_widget différent. Vérifier qu'aucun ID ne collisionne.

## Compatibilité

- Pas de migration DB.
- L'endpoint `POST /onboard/geocode/` est supprimé. Vérifier que rien (frontend, mobile, scripts externes) ne l'appelait — il était utilisé uniquement par l'ex-step 03_place.
- Le widget charge Leaflet + leaflet-geosearch via CDN unpkg. En cas de coupure réseau / firewall corporate qui bloque unpkg, la carte ne s'affiche pas (dégradation côté client uniquement).
- CDN unpkg sert l'ETag → cache navigateur OK.
