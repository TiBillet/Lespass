# API v2 — `GET /events/{id}/` par uuid OU slug front (+ 404 propre)

**Date :** 2026-05-26
**Migration :** Non

## Contexte
Issue Sentry **7504311969** : un crawler (Python-urllib, « Spider », muni d'une
clé API valide avec droit `event`) appelait
`GET /api/v2/events/test-evenement-payant-pour-cb-260620-0900-7d51dee7/`,
soit le **slug** du contrôleur front à la place d'un **uuid**.

Le routeur DRF capture n'importe quelle chaîne (`[^/.]+`), donc la route atteignait
`EventViewSet.retrieve`, où `get_object_or_404(Event, uuid=<slug>)` faisait lever
une `ValidationError` à Django (conversion `UUIDField`) → **HTTP 500**.

## Ce qui a été fait
1. **`retrieve` accepte uuid OU slug front** via
   `get_event_par_identifiant_ou_404(identifiant)` (logique miroir d'`EventMVT.retrieve`,
   `BaseBillet/views.py`) :
   - uuid valide → lookup direct par uuid ;
   - sinon, slug → les 8 derniers hex = début de l'uuid → `uuid__startswith`
     (un `LIKE` texte, donc pas de `ValidationError`) ;
   - dernier recours → `slug__startswith` ;
   - rien ne correspond → `Http404`.
   - **Pas de filtre `published`** (comme le front). ⚠️ Un évènement non publié
     devient récupérable par l'API via son uuid/slug.
2. **`destroy` / `link-address`** restent uuid-only via `get_objet_par_uuid_ou_404`
   (404 propre si l'identifiant n'est pas un uuid valide).

### Modifications
| Fichier | Changement |
|---|---|
| `api_v2/views.py` | + `import re` ; helpers `get_objet_par_uuid_ou_404` + `get_event_par_identifiant_ou_404` ; `retrieve` résout uuid+slug ; `destroy`/`link_address` sur helper uuid-only |
| `tests/pytest/test_event_retrieve_invalid_uuid.py` | Test DB-only (4 cas) |
| `CHANGELOG.md` | Entrée datée 2026-05-25 |

## Tests à réaliser

### Test 1 (automatisé) — DB-only
```bash
docker exec -e API_KEY=dummy lespass_django poetry run pytest \
  tests/pytest/test_event_retrieve_invalid_uuid.py -q
# Attendu : 4 passed (uuid → 200, slug → 200, slug inconnu → 404, uuid inconnu → 404)
# API_KEY=dummy : satisfait le fixture autouse du conftest ; le test crée sa propre clé.
```

### Test 2 (manuel, serveur live) — slug front résolu
1. Lister : `GET /api/v2/events/` → noter un `identifier` (uuid) et le slug de
   l'évènement correspondant (page front `/event/<slug>/`).
2. `curl -sk -H "Authorization: Api-Key <KEY>" \
   https://lespass.tibillet.localhost/api/v2/events/<slug>/`
   → **200** + JSON-LD Event (même `identifier` que par uuid).
3. `curl ... /api/v2/events/<uuid>/` → **200** (inchangé).
4. `curl ... /api/v2/events/slug-bidon-aucun-match/` → **404** (avant : 500).

## Périmètre / limites
- **Event uniquement.** `Product`, `Reservation`, `Membership`, `Initiative`
  (et `Sale`, `PostalAddress`) gardent le **500 latent** sur un slug/identifiant
  malformé. Le helper `get_objet_par_uuid_ou_404` est prêt à y être appliqué.
- **À investiguer côté client** : le « spider » a une clé API valide et appelle
  avec un slug → il existe probablement une intégration qui construit des URLs
  `/api/v2/events/<slug>/`. Le correctif rend l'API compatible mais ne corrige pas
  l'appelant.

## Compatibilité
Aucune migration. Lookup par uuid inchangé (sauf le filtre `published` retiré).
Les uuid inconnus mais bien formés renvoyaient déjà 404 (inchangé).
