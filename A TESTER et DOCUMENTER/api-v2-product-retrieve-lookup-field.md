# API v2 — Fix retrieve Product (`lookup_field` manquant)

## Contexte
Issue Sentry **7368726717** : `GET /api/v2/products/28817f7d-080b-49ae-b42b-b8895bc576c6/`
(uuid **valide**) levait `TypeError: ProductViewSet.retrieve() got an unexpected
keyword argument 'pk'` → **HTTP 500**.

`ProductViewSet` n'avait pas `lookup_field = "uuid"`. Le `DefaultRouter` retombe
alors sur le kwarg par défaut `pk` et appelle `retrieve(request, pk=...)`, alors
que la méthode est `retrieve(self, request, uuid=None)`. L'endpoint détail Product
n'avait donc **jamais** fonctionné.

## Ce qui a été fait
Ajout de `lookup_field = "uuid"` sur `ProductViewSet` (une ligne), cohérent avec
les autres ViewSets uuid (Event, Reservation, Membership, CrowdInitiative). Aucune
modification de l'OpenAPI : il documentait déjà `/api/v2/products/{uuid}/`.

### Modifications
| Fichier | Changement |
|---|---|
| `api_v2/views.py` | `ProductViewSet` : + `lookup_field = "uuid"` |
| `tests/pytest/test_product_retrieve.py` | Test DB-only (uuid → 200, uuid inconnu → 404) |
| `CHANGELOG.md` | Entrée datée 2026-05-25 |

## Tests à réaliser

### Test 1 (automatisé) — DB-only
```bash
docker exec -e API_KEY=dummy lespass_django poetry run pytest \
  tests/pytest/test_product_retrieve.py -q
# Attendu : 2 passed
```

### Test 2 (manuel, serveur live)
1. Lister : `GET /api/v2/products/` → noter un `identifier`/`sku` (uuid).
2. `curl -sk -H "Authorization: Api-Key <KEY-droit-product>" \
   https://lespass.tibillet.localhost/api/v2/products/<uuid>/`
   → **200** + JSON-LD Product (avant : 500 TypeError).
3. `curl ... /api/v2/products/<uuid-aléatoire>/` → **404**.

## Périmètre / limites
- Fix limité à `ProductViewSet`. Les ViewSets `PostalAddress` et `Sale` utilisent
  `pk` de façon cohérente (pas de mismatch). Les autres ont déjà `lookup_field`.
- ⚠️ Comme pour les autres endpoints uuid, un identifiant **malformé** (slug) sur
  `/products/<slug>/` ferait toujours un 500 (`ValidationError` UUIDField) — c'est
  le défaut latent connu, hors périmètre (décision : correctif slug/404 limité à
  Event). Le helper `get_objet_par_uuid_ou_404` reste prêt à y être appliqué.

## Compatibilité
Aucune migration. Le code rejoint l'OpenAPI existant.
