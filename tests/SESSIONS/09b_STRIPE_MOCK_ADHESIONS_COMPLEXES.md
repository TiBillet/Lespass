# Session 09b — Mock Stripe : adhesions complexes + crowds

## Statut : FAIT (2026-03-21)

## Depend de : 09a (fixture mock_stripe)

## Objectif

Convertir les adhesions multi-tarifs, prix zero, cycle complet, et les contributions crowds.

## Perimetre

| Fichier pytest | Tests | Source TS | Ce qu'il verifie |
|---|---|---|---|
| `test_stripe_membership_complex.py` | ~8 | PW 17,27,42 | Multi-tarifs, prix zero, cycle complet |
| `test_stripe_crowds.py` | 2 | PW 44 | Contribution crowds → Stripe → LigneArticle |

**Total : ~10 tests**

### Details

**test_stripe_membership_complex.py :**
- `test_free_price_multi_*` (4 tests, PW 17) — multi-tarifs prix libre, switch entre options
- `test_zero_price_free` (PW 42) — prix 0€ → pas de Stripe, confirmation directe
- `test_zero_price_paid` (PW 42) — prix libre > 0€ → Stripe
- `test_dynamic_form_full_cycle` (PW 27, 7 tests TS → 2 tests pytest) — cycle complet : creer produit + form fields + adherer + verifier

**test_stripe_crowds.py :**
- `test_crowds_contribution_stripe` (PW 44) — contribution → Stripe → LigneArticle
- `test_crowds_contribution_admin_verify` (PW 44) — verification admin apres paiement

## Verification

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_stripe_membership_complex.py -v -s --tb=long
docker exec lespass_django poetry run pytest tests/pytest/test_stripe_crowds.py -v -s --tb=long
docker exec lespass_django poetry run pytest tests/pytest/ --co -q | tail -1
# ~193 tests
```

## Ce qui a ete fait

### 2 fichiers crees

| Fichier | Tests | Resultat |
|---|---|---|
| `test_stripe_membership_complex.py` | 6 | 6 PASS |
| `test_stripe_crowds.py` | 2 | 2 PASS |

### Resultats

- **191 pytest** (183 + 8)
- **31 E2E** inchanges
- **8 passed en ~10s**

### Pieges resolus

1. **`custom_form` pas `custom_field`** : le champ JSONField sur Membership s'appelle `custom_form`, pas `custom_field`.
2. **`sale_origin="LP"` pas `"LS"`** : les contributions crowds creent des LigneArticle avec `sale_origin="LP"` (LESPASS), pas `"LS"`.

## Criteres de succes

- [x] 8 tests passent
- [x] Prix zero sans Stripe fonctionne
- [x] Pas de regression
