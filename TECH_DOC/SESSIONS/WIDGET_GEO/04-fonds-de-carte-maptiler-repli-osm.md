# 04 — Fonds de carte unifiés MapTiler + repli dynamique OSM France HOT

**Date :** 2026-09-26
**Statut :** implémentée et validée (pytest + Chromium Playwright) — spec relue par Fable + Opus, corrections intégrées (cf. §9)
**Mise en prod visée :** aujourd'hui → priorité absolue : **ne rien casser**, garder le comportement actuel.

---

## 1. Contexte et historique (pourquoi on en est là)

| Date | Carte | Choix | Source |
|---|---|---|---|
| 2026-05-15 | Widget adresse (`static/widgets/widget_carte_adresse.js`) | CartoDB Voyager, sans clé | `WIDGET_GEO/01-design-spec.md` §3, `02-implementation-plan.md`. **Aucune justification documentée** du choix CartoDB (simple choix initial). |
| ? | Faire Festival (`faire_festival/views/infos_pratiques.html`) | CartoDB Positron, sans clé | commentaire : « sobre, élégant, gratuit pour usage non-commercial » |
| (CHANGELOG « Carte explorer ») | Explorer fédération (`seo/static/seo/explorer.js`) | MapTiler `dataviz-v4` si `MAPTILER_KEY`, sinon OSM France HOT | CHANGELOG l.589+ |
| 2026-07-16 | Page event (`reunion/views/event/partial/geoloc.html`) | Aligné sur l'explorer (Leaflet vendoré + MapTiler / HOT) après des 403 de `tile.openstreetmap.org` | CHANGELOG l.203+, `A TESTER et DOCUMENTER/carte-event-fond-et-adresse-principale.md` |

Problèmes constatés :
1. Les cartes CartoDB affichent le filigrane **« API KEY REQUIRED »** (CARTO exige désormais une clé).
2. Quand le quota MapTiler gratuit (100 000 req/mois) est épuisé, MapTiler renvoie 403/429 → **tuiles grises**, aucun repli (le repli HOT actuel n'est que **statique** : il ne joue que si la clé est absente).

Décisions mainteneur (2026-09-26) :
- (a) La carte Faire Festival est **incluse** dans la migration.
- (b) Le seuil de bascule doit **correspondre à la pratique en prod** (pas « 1 seule tuile en erreur »).
- (c) Au drag, un reverse partiel **n'écrase pas** un champ déjà rempli par une valeur vide.

---

## 2. Périmètre — les 4 cartes Leaflet du projet

Recensement exhaustif (`grep -ril "tileLayer\|maptiler\|cartocdn"` hors `www/static`, `vendor`, artefacts E2E) :

| # | Carte | Formulaire ? | Chargement Leaflet | Clé dispo aujourd'hui |
|---|---|---|---|---|
| 1 | Widget adresse `templates/widgets/widget_carte_adresse.html` + `static/widgets/widget_carte_adresse.js` | **OUI** — synchro marqueur ↔ champs | unpkg 1.9.4 | **non** |
| 2 | Page event `BaseBillet/templates/reunion/views/event/partial/geoloc.html` | non | vendoré 1.9.4 | oui (`get_context()` → `maptiler_key`) |
| 3 | Explorer `seo/static/seo/explorer.js` — 2 contextes : `/explorer/` (ROOT, `seo/views.py:396`) et `/federation/` (tenant, `BaseBillet/views.py:1795`) | non | vendoré 1.9.4 | oui (`data-maptiler-key`) |
| 4 | Faire Festival `BaseBillet/templates/faire_festival/views/infos_pratiques.html` | non | unpkg 1.9.4 (chargé dynamiquement) | oui (`get_context()` → `maptiler_key`) |

Le widget (#1) a **deux consommateurs**, qui doivent garder exactement le même comportement :
- `onboard/templates/onboard/steps/03_place.html` — wizard onboard, **schéma public (ROOT)**, `required=False`. Les vues onboard ne passent **pas** `maptiler_key`.
- `BaseBillet/templates/reunion/views/event/wizard/_form_carte.html` — wizard évènement (`step_map`), tenant, `required=True`.

La synchro formulaire ↔ marqueur n'existe **que** dans #1. Les cartes #2, #3 et #4 ne sont touchées que pour leur fond de carte.

Hors périmètre : Leaflet chargé depuis unpkg (#1, #4). On ne vendorise pas aujourd'hui, pour limiter le risque. Pas de SDK vectoriel.

---

## 3. Fournisseur de tuiles (identique partout)

- **Clé présente** → MapTiler :
  `https://api.maptiler.com/maps/dataviz-v4/{z}/{x}/{y}.png?key={KEY}&language=fr`
  options : `tileSize: 512, zoomOffset: -1, minZoom: 1, maxZoom: 20, crossOrigin: true`,
  attribution : `&copy; MapTiler &copy; OpenStreetMap contributors` (liens, identique à explorer/geoloc).
- **Clé absente** → OSM France HOT :
  `https://{s}.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png`, `subdomains: 'abc', maxZoom: 20`,
  attribution HOT / OSM France (identique à explorer/geoloc).

Constantes et options copiées **à l'identique** des deux implémentations existantes (explorer.js, geoloc.html).

### 3.1 Passage de la clé au widget (#1)

Les vues onboard n'ont pas `maptiler_key` dans le contexte. Pour ne **pas** toucher aux vues (onboard et wizard event), on ajoute un `simple_tag` dans le fichier existant `BaseBillet/templatetags/tibitags.py` :

```python
from django.conf import settings   # absent aujourd'hui de tibitags.py -> a AJOUTER

@register.simple_tag
def maptiler_key():
    """Cle MapTiler (settings.MAPTILER_KEY), vide si non configuree."""
    return getattr(settings, "MAPTILER_KEY", "")
```
On passe par `django.conf.settings` et **pas** par `from TiBillet.settings import ...`, sinon `override_settings` ne marche plus dans les tests.

Dans le template du widget : `{% load ... tibitags %}`, puis sur le conteneur :
`data-maptiler-key="{% maptiler_key %}"` (auto-échappé par Django).
Disponible sur ROOT : `BaseBillet` est dans `TENANT_APPS`, mais Django importe **tous** les modules `templatetags` des `INSTALLED_APPS` quand le moteur démarre. `tibitags` est donc déjà importé par chaque worker, et le tag ne touche pas la DB. Coût nul.
Ne lancer **ni** `ruff format` **ni** `ruff check --fix` sur `tibitags.py` (fichier existant).

Côté JS : `const cle_maptiler = container.dataset.maptilerKey || "";`.

#4 (Faire Festival) utilise `{{ maptiler_key|default:''|escapejs }}` comme geoloc.html, puisque la vue passe par `get_context()`.

---

## 4. Repli dynamique MapTiler → OSM France HOT

### 4.1 Comportement de Leaflet 1.9.4 (vérifié dans le source vendoré)

- `GridLayer._update` émet **`loading`** quand un nouveau lot de tuiles démarre (seulement si aucun lot n'est déjà en cours).
- `_tileReady(coords, err, tile)` : si `err`, émet **`tileerror`**. **Dans tous les cas**, la tuile est marquée `loaded`. En cas de succès seulement, émet `tileload`. Quand plus aucune tuile n'est en attente, émet **`load`**.
  → `load` part donc **aussi** quand toutes les tuiles du lot ont échoué.
- **Piège (relecture Fable)** : juste après `this.fire("load")`, `_tileReady` lit `this._map._fadeAnimated`. Si un handler `load` a fait `map.removeLayer(couche)`, `this._map` vaut `null` → **`TypeError` non capturé**. Retirer la couche **dans `tileerror`** ne pose pas de problème : l'événement est émis en tête de `_tileReady`, et `this._tiles[key]` a été vidé par `onRemove`.
  → **Règle : ne jamais retirer la couche de façon synchrone dans un handler.** On lève le flag tout de suite, et le retrait + l'ajout de HOT passent par `setTimeout(..., 0)`.
- Zoom pendant un lot : `_abortLoading` supprime les tuiles incomplètes sans passer par `_tileReady` (ni `tileerror` ni `tileload` fantômes). Tuiles hors bornes : filtrées par `_isValidTile`, jamais demandées.

### 4.2 Ce qui se passe en prod

- **Quota épuisé / clé invalide / origine refusée** → **toutes** les tuiles MapTiler répondent 403/429. Un lot entier échoue, sans une seule réussite.
- **Tuile isolée en erreur** (micro-coupure, 5xx ponctuel) → une erreur au milieu de réussites. Ça **ne doit pas** faire basculer, sinon l'utilisateur perd MapTiler pour toute la page à cause d'un incident sans gravité.
- **Cas mixte** : des tuiles déjà en cache HTTP navigateur se chargent, les nouvelles échouent (quota tombé en cours de mois). Le lot contient des réussites, alors que le service est bien KO.

### 4.3 Règle retenue (deux déclencheurs, une seule bascule)

Deux compteurs **cumulés** depuis la création de la couche : `tuiles_maptiler_ok` et `tuiles_maptiler_en_erreur`. Aucun compteur par lot : après le premier écran, un petit déplacement peut créer un lot d'**une seule** tuile, et une erreur ponctuelle ferait alors basculer (relectures Fable et Opus).

1. **Premier affichage entièrement en échec** : à `load`, si **aucune tuile MapTiler n'a jamais réussi** (`ok === 0`) et qu'au moins une a échoué → bascule. C'est le cas quota/clé/origine refusée à l'ouverture de la page. Il se déclenche dès le premier écran, quelle que soit la taille de la carte.
2. **Erreurs cumulées** : dès que le total d'erreurs atteint **`SEUIL_ERREURS_TUILES = 5`** → bascule. Ça couvre le quota épuisé en cours de visite et le cas mixte (cache). Une ou deux tuiles ratées dans une session normale ne déclenchent rien.

Bascule (une seule fois par carte, flag `bascule_osm_faite`, retrait **différé** — cf. §4.1) :
```js
function basculer_vers_osm() {
    if (bascule_osm_faite) { return; }
    bascule_osm_faite = true;
    console.warn("<nom carte>: MapTiler indisponible, bascule sur OSM France HOT");
    setTimeout(function () {
        map.removeLayer(couche_maptiler);
        creer_couche_osm().addTo(map);
    }, 0);
}
```
Si la clé est absente, on crée directement la couche OSM, sans écouteur ni repli.
Pas de repli « OSM → autre chose » : si HOT tombe aussi, la carte reste grise (comme aujourd'hui).

### 4.4 Implémentation : duplication assumée

Le même bloc (~25 lignes FALC) est copié dans les 4 cartes plutôt que factorisé dans un JS partagé, parce que les 4 pages chargent Leaflet différemment (vendoré / unpkg / chargement dynamique). Un fichier commun ajouterait une dépendance de chargement de plus (ordre des `<script>`) pour un gain faible. Chaque copie est commentée en FR/EN et renvoie à cette spec.

Spécificités :
- **geoloc.html** : on garde les écouteurs `loading`/`load` existants (console.log + `resize`). Le `tileerror` existant (console.error) est **conservé** sur les deux couches, pour garder le comportement actuel. Le compteur s'y ajoute sur la couche MapTiler. La couche OSM de repli reçoit aussi l'écouteur `load` → `resize` (même comportement d'affichage).
- **explorer.js** : on stocke la couche dans une variable locale (aujourd'hui elle est ajoutée directement). La logique marqueurs / cluster ne bouge pas.
- **infos_pratiques.html** : CartoDB Positron est remplacé par MapTiler / HOT + repli. `maxZoom` passe de 19 à 20 (MapTiler et HOT servent tous deux le niveau 20). Le marqueur custom ne change pas. Le rendu visuel change (Positron clair → dataviz-v4) : c'est accepté (décision a).

---

## 5. Widget adresse (#1) : ce qui change et ce qui NE change PAS

### 5.1 Change
1. Les constantes `URL_TUILES_CARTODB`, `SOUS_DOMAINES_CARTODB` et `ATTRIBUTION_TUILES` sont remplacées par les constantes MapTiler et HOT. La création de couche passe par la règle §3 + §4. L'en-tête du fichier (« CartoDB Voyager tiles ») est mis à jour.
2. Garde « non vide », limitée au **chemin reverse** (drag, clic carte, repli reverse après une recherche), conformément à la décision (c) qui porte sur le drag.
   `placer_marqueur_et_remplir_champs` reçoit un 5ᵉ paramètre booléen `ne_pas_ecraser_par_du_vide`. Seul `reverse_geocoder_et_remplir` le passe à `true`. Les autres appelants (recherche avant, `geosearch/showlocation`, pré-remplissage initial) ne le passent pas → `undefined` → **comportement strictement identique à aujourd'hui**.
   Quand il vaut `true` :
   - Rue : `(house_number + " " + road).trim()`, écrite seulement si non vide. Aujourd'hui, elle est écrite même vide.
   - Ville : `city || town || village || municipality`, écrite seulement si non vide. Aujourd'hui, elle est écrite même vide.
   - Code postal, pays, `input_adresse` : déjà gardés. Inchangés. lat/lng : toujours écrites.

   Pourquoi ne pas l'appliquer à la recherche avant (relecture Opus) : dans l'onboard, `street_address` est `required=True, allow_blank=False` (`onboard/serializers.py:218`). Aujourd'hui, une recherche vers un lieu sans rue **vide** le champ, et le 422 force l'utilisateur à le corriger. Garder l'ancienne rue ferait passer en silence une adresse incohérente. Ce comportement est conservé.

   Conséquence assumée (décision c) : après un drag, ou un repli reverse, vers un point où Nominatim ne renvoie ni `road` ni ville (champ, `pedestrian`/`footway`, `hamlet`), l'ancienne rue ou ville reste affichée alors que lat/lng ont changé. Elle part dans le POST si l'utilisateur ne la corrige pas.
   Pour le repli reverse qui suit une recherche : la recherche avant a déjà vidé la rue si elle n'en avait pas. La garde n'a donc d'effet qu'en l'absence de résultat reverse, et le champ vide reste vide, comme aujourd'hui.

### 5.2 Ne change PAS (invariants, vérifiés en relecture de diff)
- **P.WIDGET.1** : aucun `requestSubmit()` / `submit()`. Le keydown Entrée garde `preventDefault()` + `stopPropagation()`. Le bouton loupe injecté garde `type="button"`.
- **P.WIDGET.2** : `map.zoomControl.setPosition("topright")` est conservé. Le CSS `.pending { display:none }` n'est pas touché.
- **P.WIDGET.3** : le CSS `.reset { display:none }` n'est pas touché (`widget_carte_adresse.css` n'est pas modifié).
- **P.WIDGET.4** : `autoComplete: false` est conservé.
- Recherche : `lancer_recherche_nominatim` (placement + `setView(ZOOM_DETAIL)` + repli reverse si `!road || !postcode`). Inchangée.
- Drag / clic carte → `reverse_geocoder_et_remplir` (lat/lng tout de suite, puis reverse). Inchangé.
- Pré-remplissage initial (`data-lat/lng/adresse/rue/cp/ville-initiale`), recherche auto au load, rescan `htmx:afterSettle`, idempotence `data-widget-initialized`. Inchangés.
- Hidden inputs, `name=`, `data-testid`, `required`. Inchangés. Le seul ajout au template est l'attribut `data-maptiler-key`.

Vérification sur le cas Tiers-Lieux (`parties_initiales = {road, postcode, city}`, sans `house_number`) : rue = `road` → identique à avant quand `road` est non vide. Quand `road` est vide, le champ rue était déjà vide (valeur initiale du template). Le résultat est donc identique.

---

## 6. Tests

### 6.1 Automatisés (pytest, sans réseau)
- `tests/pytest/test_event_map_tiles.py` (existant, 2 tests), étendu : le HTML rendu contient les identifiants **propres au repli** (`SEUIL_ERREURS_TUILES`, `bascule_osm_faite`). Pas « HOT + tileerror » : c'est déjà présent aujourd'hui, le test ne prouverait rien. Les nouveaux commentaires ne doivent citer ni `unpkg.com` ni `https://tile.openstreetmap.org/{z}/{x}/{y}.png` (assertions existantes).
- `tests/pytest/test_widget_carte_adresse_tiles.py` (nouveau) :
  - rendu de `widgets/widget_carte_adresse.html` avec `override_settings(MAPTILER_KEY="MAcleDeTest123")` → `data-maptiler-key="MAcleDeTest123"` ;
  - `override_settings(MAPTILER_KEY="")` **explicite** (le `.env` de dev définit une clé) → `data-maptiler-key=""` ;
  - source `static/widgets/widget_carte_adresse.js` : contient `api.maptiler.com/maps/dataviz-v4`, `tile.openstreetmap.fr/hot`, `SEUIL_ERREURS_TUILES`, `bascule_osm_faite`, `autoComplete: false`, `type = "button"`, `setPosition("topright")` ; **ne contient pas** `requestSubmit` ni `cartocdn` ;
  - `seo/static/seo/explorer.js` et `infos_pratiques.html` : contiennent `SEUIL_ERREURS_TUILES` + `bascule_osm_faite` + HOT, et pas `cartocdn` ;
  - scan `cartocdn` sur les **4 fichiers nommés** uniquement. Un scan de tout le dépôt traverserait `.git`/`htmlcov` et passerait au rouge au premier `coverage html`.
- Vérification par mutation (règle projet) : on retire `data-maptiler-key` du template, puis le bloc de repli d'un JS → les tests doivent échouer → on restaure.
- `node --check` **depuis l'hôte** (node n'est pas dans `lespass_django`) sur `widget_carte_adresse.js` et `explorer.js`, et sur le `<script>` inline extrait du rendu de `geoloc.html` et de `infos_pratiques.html`.
- Non-régression : `onboard/tests/test_step_place.py` (rendu 422 du widget sur ROOT) et `tests/pytest/test_event_wizard_unifie.py` (GET de la carte côté tenant). Ils attrapent une 500 due au tag. E2E explorer (`test_explorer_markers_per_pa.py`, `test_explorer_adresse_dupliquee.py`), puis **suite complète**.
- **Trou assumé** : aucun E2E n'existe pour le widget. La synchro et le repli ne sont vérifiés en réel que par §6.2.

### 6.2 Navigateur (Playwright MCP, réel)
Sur `https://lespass.tibillet.localhost/` (clé MapTiler configurée en dev) :
Dans tous les scénarios, on écoute `page.on("pageerror")` et on exige **0 exception non capturée**. C'est le seul moyen d'attraper un `TypeError` Leaflet (§4.1).
1. Nominal : tuiles `api.maptiler.com`, aucune requête HOT, aucun filigrane. (Si l'origine dev n'est pas autorisée pour la clé, on verra le repli : le noter.)
2. Quota simulé : `page.route("**/api.maptiler.com/**", r => r.fulfill({status: 429}))` → bascule sur HOT au premier écran, **une seule fois** (une seule couche de tuiles dans le DOM), un warn console.
3. Erreur isolée : 1 tuile MapTiler en 403 au premier écran, les autres OK → **pas** de bascule. Puis un déplacement qui découvre 1 nouvelle tuile en 403 → toujours **pas** de bascule.
4. Widget (onboard `/onboard/place/` et wizard event) : recherche Entrée + loupe → marqueur + champs, et le formulaire parent n'est **pas** soumis. Drag → lat/lng + champs. Drag vers une zone sans rue → la rue précédente est conservée.
5. Page event (« Voir la carte »), explorer `/explorer/` (ROOT) et `/federation/` (tenant), infos pratiques Faire Festival : carte OK dans les cas 1 et 2, 0 exception non capturée (les erreurs de chargement de tuiles et le `Tile error:` de geoloc sont attendus).

---

## 7. Risques et parades

| Risque | Parade |
|---|---|
| `{% load tibitags %}` casse le rendu du widget sur ROOT (onboard) | Test de rendu 6.1 + test onboard existant + Playwright `/onboard/place/` |
| La bascule boucle ou empile les couches | Flag `bascule_osm_faite` + le repli ne réessaie jamais MapTiler + check « une seule couche HOT » (6.2.2) |
| Bascule intempestive sur une erreur isolée | Règle lot à 0 réussite + seuil cumulé 5 (6.2.3) |
| Régression de la synchro formulaire | Seul `placer_marqueur_et_remplir_champs` change (2 gardes) ; invariants §5.2 relus sur le diff ; Playwright 6.2.4 |
| Timeout réseau MapTiler sans réponse (pas de `tileerror`) | Hors périmètre : comportement inchangé (tuiles grises). |
| Clé exposée côté client | Déjà le cas (explorer/geoloc). Clé restreinte par domaine dans le dashboard MapTiler (CHANGELOG). |
| **Restriction de domaine MapTiler** | La clé est **déjà** servie sur le domaine ROOT (`/explorer/`) et sur tous les domaines tenants (page event, `/federation/`) : le widget et Faire Festival n'ajoutent aucune origine. Vérification de routine des « Allowed origins ». Une origine refusée donne des 403 → repli HOT (fonctionnel). |
| Session très longue (explorer) : 5 erreurs isolées cumulées → bascule d'un service sain | Assumé (on reste sur une carte HOT fonctionnelle), pour rester simple. |
| Cache navigateur de l'ancien JS | Aucun : `/static` est servi en `no-cache` (`nginx_prod/lespass_prod.conf`), le cache long ne vise que `vendor/` et les libs versionnées. `collectstatic` tourne au démarrage (`start.sh`). Ne rien modifier dans `www/static`. |

## 8. Fichiers modifiés

| Fichier | Changement |
|---|---|
| `BaseBillet/templatetags/tibitags.py` | + `from django.conf import settings` + `simple_tag` `maptiler_key` |
| `templates/widgets/widget_carte_adresse.html` | `{% load tibitags %}` + `data-maptiler-key` |
| `static/widgets/widget_carte_adresse.js` | MapTiler/HOT + repli ; garde non-vide rue/ville (chemin reverse seulement) |
| `BaseBillet/templates/reunion/views/event/partial/geoloc.html` | repli dynamique |
| `seo/static/seo/explorer.js` | repli dynamique |
| `BaseBillet/templates/faire_festival/views/infos_pratiques.html` | CartoDB → MapTiler/HOT + repli |
| `tests/pytest/test_event_map_tiles.py` | + assertions repli |
| `tests/pytest/test_widget_carte_adresse_tiles.py` | NOUVEAU |
| `CHANGELOG.md`, `A TESTER et DOCUMENTER/fonds-de-carte-maptiler-repli-osm.md` | doc |

Aucune migration. Aucune vue modifiée. Pas de `makemessages` (aucune nouvelle chaîne `_()` côté Python/template ; les `console.warn` JS ne sont pas traduits).

## 9. Relectures (2026-09-26) — corrections intégrées

| Relecteur | Point | Correction |
|---|---|---|
| Fable | BLOQUANT : `removeLayer` synchrone dans `load` → `TypeError` Leaflet | Retrait différé (`setTimeout 0`), §4.1 / §4.3 |
| Opus | BLOQUANT : `settings` non importé dans `tibitags.py` → `NameError` → 500 onboard + wizard | Import `django.conf.settings` + `getattr`, §3.1 |
| Fable + Opus | Règle « lot à 0 réussite » : un lot d'1 tuile après un déplacement fait basculer sur une erreur isolée | Règle 1 limitée à « aucune tuile n'a jamais réussi », §4.3 |
| Opus | La garde non-vide débordait sur la recherche avant (validation onboard contournée en silence) | Garde limitée au chemin reverse, §5.1 |
| Opus | Tests geoloc/explorer tautologiques ; scan cartocdn fragile ; `.env` dev avec clé | Identifiants propres au repli, 4 fichiers nommés, `override_settings("")`, §6.1 |
| Fable + Opus | `pageerror`, node sur l'hôte, JS inline, explorer ×2 contextes, restriction de domaine, cache | §6.1, §6.2, §7 |
