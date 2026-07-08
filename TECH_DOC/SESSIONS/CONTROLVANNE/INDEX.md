# CONTROLVANNE — Hub du chantier

App tireuse à bière connectée (paiement NFC via fedow_core local).
Importée par Mike depuis sa branche `controlvanne-merge` (version nettoyée,
chantiers de review appliqués), câblée dans Lespass le 2026-07-06.

## Documents

| Doc | Contenu | Statut |
|---|---|---|
| [CHANTIER-01-cablage-lespass.md](./CHANTIER-01-cablage-lespass.md) | Câblage complet : settings, urls, asgi/WS, migrations, tests, appairage TI, admin | ✅ FAIT 2026-07-06 (+ écarts documentés dans `A TESTER et DOCUMENTER/controlvanne-cablage.md`) |
| [CHANTIER-02-websockets-prod-supervisord.md](./CHANTIER-02-websockets-prod-supervisord.md) | WebSockets en prod : supervisord mono-conteneur (gunicorn+daphne+celery), nginx /ws/, fix AppRegistryNotReady, flush.sh conscient | ✅ FAIT 2026-07-06 (recette pre-prod restante) |
| [REVIEW-2026-07-06-tour-critique.md](./REVIEW-2026-07-06-tour-critique.md) | Tour critique complet (3 reviewers : monétaire, stock/signaux, vues/JS) : **3 Critical confirmés** (double facturation concurrente, pas de reconnexion WS kiosk, 500 carte sans wallet V2), 4 Important, 8 Minor → CHANTIER-03 | 2026-07-06 |
| [CHANTIER-03-fixes-review.md](./CHANTIER-03-fixes-review.md) | Fixes TDD des findings : C1+I1 (verrou session + atomic, test de concurrence 2 threads), C2 (reconnexion WS backoff + bandeau), C3 (refus propre), I2/I3/I4. Minor en dette | ✅ FAIT 2026-07-06 |
| `controlvanne/Synthese_merge_vs_chantiers.md` | Synthèse du merge de Mike : 6 chantiers de review vs 11 étapes, divergences, PRs déférées | Référence |

## Écarts au plan (découverts au câblage)

- Migration `0004` générée (`reservoir_illimite` hors migrations du merge).
- `SaleOrigin.TIREUSE` porté (BaseBillet 0226) — requis par `billing.py`.
- Fix `TermUserManager` (filtre `client_source`) — terminaux invisibles sinon.
- Menu « Terminaux hardware » → changelist PairingDevice (décision mainteneur) ;
  `terminal_role` exposé dans le form PairingDevice (LB/KI, TI auto-créé).

## Actions au merge de main-fedow-import (ne pas oublier)

- **Repointer la branche par défaut du client Pi** vers la branche stable :
  `controlvanne/Pi/install_pi.sh` (`DEFAULT_BRANCH`), `config/claim.sh`
  (défaut `GIT_BRANCH`), `Makefile` (fallback `DEFAULT_BRANCH`), et les URLs
  wget des deux README (`controlvanne/README.md` ×2, `controlvanne/Pi/README.md`).
  Actuellement : `main-fedow-import` (l'ancien défaut `V2` pointait le proto).

## Reste à faire (par priorité)

1. ~~**CHANTIER-02 — WebSocket prod**~~ ✅ **FAIT 2026-07-06** : supervisord
   mono-conteneur (gunicorn 8002 + daphne 7999 + celery), `location /ws/`
   dans `nginx_prod/lespass_prod.conf`, service celery retiré du compose
   pre-prod, fix `AppRegistryNotReady` dans asgi.py. Recette pre-prod à
   faire après rebuild : `A TESTER et DOCUMENTER/supervisor-websockets-prod.md`.
2. **PRs déférées de Mike** (cf. Synthese, section « PRs déférées ») :
   PR 2 balance estimée JS kiosk, PR 3 URL http:// Pi LAN en DEBUG,
   PR 4 AUTH_KIOSK complet (TermUser + django.login), simplification calibration.
3. **Tests E2E controlvanne** à porter depuis lespass-main
   (`test_controlvanne_admin.py`, `test_controlvanne_kiosk.py`).
4. ~~Smokes Chrome~~ ✅ faits en session (2026-07-06) : appairage LB/TI bout en
   bout, kiosk, WS, tirage complet avec facturation vérifiée en base.

## Specs Atomic

- « Spec — Integration controlvanne dans Lespass » (WebSocket, facturation fedow_core)
- « Spec — Phase 6 : Client Pi controlvanne » (appairage PIN, kiosk Chromium)
- « Spec — Simulateur Pi3 » (panneau debug `DEMO=1`)
