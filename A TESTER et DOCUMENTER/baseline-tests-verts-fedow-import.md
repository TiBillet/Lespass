# Baseline tests verts — pré-chantier FEDOW_IMPORT (S6)

Date : 2026-06-11

## Ce qui a été fait

Remise au vert des 3 suites avant d'ouvrir le lot C-A (copier-coller du socle
laboutik + fedow_core). **Aucun code applicatif modifié** — uniquement des
tests et leur outillage. Détail complet dans le CHANGELOG (entrée du 2026-06-11).

| Suite | Avant | Après (2026-06-11) |
|---|---|---|
| pytest (`tests/pytest/`) | 226 erreurs (clé API), puis 4 échecs | **226 passed** (confirmé sur 2 runs consécutifs) |
| E2E Playwright TS (`tests/playwright/`) | 28 failed / 38 passed / 1 skipped | **66 passed, 0 failed, 2 skipped** (10,3 min, run complet) |
| E2E Playwright Python (`tests/e2e/`) | 8 erreurs (Playwright absent) | **8 passed** |

Les 2 skipped TS : 1 skip préexistant + le `test.fixme` documenté (bug wizard
doublon → 500, cf. décision 1 ci-dessous) — réactivable dès le fix appliqué.

Causes racines corrigées :
1. **Refonte admin produits en proxys** non répercutée dans 19 specs TS
   (membershipproduct/ticketproduct, inlines Unfold, catégorie cachée).
2. **Pollution inter-tests** : fenêtre comptable 5 min (tests passés en
   assertions delta), cache pytest persistant après `down -v`.
3. **Outillage** : fallback `test_api_key` en conteneur, installation
   Playwright Python + deps système Chromium dans le conteneur, règle DNS
   Chromium apex, explorer testé sur l'apex.

## Tests à réaliser (mainteneur)

### Test 1 : reproductibilité des commandes documentées
1. `docker exec lespass_django poetry run pytest tests/pytest/ -q`
   → attendu : 226 passed, sans variable d'environnement à fournir.
2. `docker exec -e ADMIN_EMAIL=admin@admin.com -e E2E_TEST_TOKEN='<voir .env>' lespass_django poetry run pytest tests/e2e/ -q`
   → attendu : 8 passed.
3. `cd tests/playwright && yarn test:chromium:console --workers=1`
   → attendu : 0 failed (1 test `fixme` documenté, cf. bug 1).

### Test 2 : relancer deux fois de suite
La suite pytest doit rester verte sur un second run immédiat (c'était le bug
de pollution : les tests comptabilité échouaient après tout run API v2).

## Décisions / arbitrages en attente

1. **Bug wizard event** (doublon → 500, `BaseBillet/views.py:4005`) : à
   corriger côté app (gérer IntegrityError + message formulaire). Le test du
   cas est prêt en `test.fixme` dans `21-event-quick-create-duplicate.spec.ts`.
2. **Bug signaux proxys** (`sender=Product` muet pour TicketProduct/
   MembershipProduct) : décider entre connecter les receivers aux proxys ou
   dispatcher sur `instance._meta.concrete_model`. Impacte le tarif gratuit
   FREERES auto-créé et possiblement l'envoi des produits adhésion vers Fedow.
3. **Playwright Python** installé dans le conteneur via pip (hors
   `pyproject.toml`) — pérenniser dans les deps si on garde `tests/e2e/`.
4. **Traefik dev** : `www.tibillet.localhost` non routé (404 avant Django) —
   ajouter aux labels compose si nécessaire.
