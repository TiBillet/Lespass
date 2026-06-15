# CHANTIER 01 — Socle E2E Python + simplification Stripe

Statut : ✅ TERMINÉ (2026-06-11)

## Ce qui a été fait

1. **Socle force_login porté de la V2** :
   - `AuthBillet/views_test_only.py` (copie V2, triple garde-fou) ;
   - branchement dans `AuthBillet/urls.py` sous `if settings.DEBUG:` ;
   - le `.env` du main contenait déjà `E2E_TEST_TOKEN` et `ADMIN_EMAIL` ;
   - le `tests/e2e/conftest.py` du main était déjà une copie du socle V2
     (login_as, fill_stripe_card, django_shell…) — rien à fusionner.
   - Vérifié : 200 + sessionid avec le bon token, 404 avec un mauvais token.

2. **Vague 1 de migration TS → Python** (3 specs) :
   - 18 → `tests/e2e/test_reservation_validations.py` ;
   - 20 → `tests/e2e/test_membership_validations.py` ;
   - 28 → `tests/e2e/test_numeric_overflow_validation.py` (réécrit, pas en V2).

3. **Politique Stripe V2 appliquée** :
   - 17 tests pytest mockés portés (4 fichiers `test_stripe_*.py`) +
     fixture `mock_stripe` dans le conftest ;
   - 2 smoke E2E réels portés (`test_stripe_smoke.py`) ;
   - `test_stripe_checkout_url.py` NON porté (teste un champ modèle V2-only).

4. **Suppressions/fusions TS** (42 → 30 specs, ~11 min → ~7 min) :
   - migrés : 18, 20, 28 ;
   - doublons : 08, 12 (couverts par 27), 15 (couvert par 17 + mocks) ;
   - couverts par mock+smoke : 09, 10, 11, 13, 42, 44 ;
   - renumérotés : 21-event-quick-create→29, 35-resa-cancel→39, 35-explorer→40 ;
   - conservés volontairement : 04 (création admin récurrente), 17 (UI multi
     prix libre), 36 (SEPA), 43 (flow admin validation+Stripe riche).

## Bugs réels trouvés par la migration

1. **`min="{{ price.prix }}"` localisé** : en locale FR, Django rend
   `min="5,00"` (virgule) → attribut HTML invalide → la validation HTML5 du
   minimum ne fonctionnait pas. Corrigé avec `|unlocalize` dans
   `booking_form.html` (1×) et `membership/form.html` (2×).
2. **3 tests comptabilité fragiles** : assertions sur totaux absolus de
   catégorie (piège 9.60) — cassés dès que d'autres tests laissent des ventes
   en DB. Passés en delta / filtre par nom de produit unique.

## État final des suites (2026-06-11)

| Suite | Avant | Après |
|---|---|---|
| pytest DB-only | 229 tests, 49 s | **246 tests** (~51 s), tous verts |
| E2E Python | 8 tests, 17 s | **15 tests** (~1 min) : explorer 8 + validations 2 + overflow 2 + smoke Stripe 2 + (1 réservation) |
| Playwright TS | 42 specs, 10 min 54 | **30 specs** (~7 min estimé) |

## Reste à faire (chantiers suivants)

- CHANTIER-02 : vagues 2+ de migration TS→Python (crowds, admin) — voir
  PLAN_SIMPLIFICATION.md section 4.
- Vider `tests/django_test/` (2 rouges legacy).
- Marker `smoke` dans pytest.ini + `pytestmark` sur les fichiers essentiels.
- Test du flux paiement/scan QR code (priorité 1 de TESTS_RESTANTS.md).
- `poetry add --group dev pytest-cov` (décision mainteneur) — installé via
  pip dans le venv pour l'instant.
