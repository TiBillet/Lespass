# Session 07 — Convertir les tests Playwright TS → pytest Python (evenements, crowds, laboutik)

## Statut : FAIT (2026-03-21)

- 8 fichiers crees, 16 tests, tous passent
- Total : 178 tests pytest
- Temps d'execution : ~18s

## Fichiers crees

| Fichier | Tests | Source PW TS |
|---------|-------|-------------|
| `test_reservation_limits.py` | 3 | 19 |
| `test_event_quick_create.py` | 2 | 21 |
| `test_product_duplication.py` | 1 | 25 |
| `test_admin_reservation_cancel.py` | 2 | 35 |
| `test_event_adhesion_obligatoire.py` | 1 | 38 |
| `test_crowds_summary.py` | 1 | 24 |
| `test_discovery_pin_pairing.py` | 3 | 30 |
| `test_laboutik_securite_a11y.py` | 3 | 46 |

## Pieges rencontres

1. **`Event.save()` + FakeTenant** : `schema_context()` cree un `FakeTenant` sans `get_primary_domain()`. Solution : utiliser `tenant_context(tenant)` pour les tests qui creent des Events via ORM.
2. **`ProductSold` n'a pas de champ `name`** : le `__str__` utilise `self.product.name`, pas un champ propre. Creation simplifiee : `ProductSold.objects.create(product=product)`.
3. **Signal `send_membership_product_to_fedow`** : cree un "Tarif gratuit" automatiquement sur les produits FREERES. Les assertions de comptage de tarifs doivent etre relatives (`>= 3`) et non absolues (`== 3`).
4. **`admin_clean_html(None)` crashe** : le serializer `EventQuickCreateSerializer` passe `ld=None` a `nh3.clean()`. Solution : toujours envoyer `long_description=''` dans les POST de test.
5. **Routes publiques (discovery)** : les routes `/api/discovery/` sont dans `urls_public.py`. Le `DjangoClient` doit utiliser `HTTP_HOST='tibillet.localhost'` (domaine du schema public).

## Gaps reportes a session 10 (nettoyage)

Le plan identifiait 2 fichiers PW TS FastTenantTestCase non couverts par les sessions 05-07 :
- `99-theme_language.spec.ts` (§4.2, 3 tests) — pas inclus en session 05
- `42-membership-zero-price.spec.ts` (§4.1, 2 tests, mock Stripe) — pas inclus en session 06

→ A traiter en session 10 (nettoyage final).

## Verification

```bash
docker exec lespass_django poetry run pytest tests/pytest/ -v --tb=short
docker exec lespass_django poetry run pytest tests/pytest/ --co -q | tail -1
# 178 tests collected
```
