# CONTROLVANNE — Hub du chantier

App tireuse à bière connectée (paiement NFC via fedow_core local).
Importée par Mike depuis sa branche `controlvanne-merge` (version nettoyée,
chantiers de review appliqués), câblée dans Lespass le 2026-07-06.

## Documents

| Doc | Contenu | Statut |
|---|---|---|
| [CHANTIER-01-cablage-lespass.md](./CHANTIER-01-cablage-lespass.md) | Câblage complet : settings, urls, asgi/WS, migrations, tests, appairage TI, admin | ✅ FAIT 2026-07-06 (+ écarts documentés dans `A TESTER et DOCUMENTER/controlvanne-cablage.md`) |
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

1. **CHANTIER-02 — WebSocket prod** : supervisord mono-conteneur
   (gunicorn 8002 + daphne 7999 + celery), `location /ws/` nginx,
   retrait du service celery du compose. Pattern copié de `../LaBoutik`
   (`supervisor/`, `start_services.sh`).
2. **PRs déférées de Mike** (cf. Synthese, section « PRs déférées ») :
   PR 2 balance estimée JS kiosk, PR 3 URL http:// Pi LAN en DEBUG,
   PR 4 AUTH_KIOSK complet (TermUser + django.login), simplification calibration.
3. Smokes Chrome après restart serveur : WS `ws/rfid/`, kiosk DEMO,
   appairage bout en bout (cf. `A TESTER et DOCUMENTER/controlvanne-cablage.md`).

## Specs Atomic

- « Spec — Integration controlvanne dans Lespass » (WebSocket, facturation fedow_core)
- « Spec — Phase 6 : Client Pi controlvanne » (appairage PIN, kiosk Chromium)
- « Spec — Simulateur Pi3 » (panneau debug `DEMO=1`)
