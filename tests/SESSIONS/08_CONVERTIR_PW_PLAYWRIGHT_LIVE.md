# Session 08 — Convertir PW TS → Playwright Python (E2E live)

## Decoupage

Cette session a ete decoupee en 3 sous-sessions car la charge etait trop lourde
pour une seule passe (~8 fichiers TS, complexite variable).

| Sous-session | Perimetre | Statut |
|---|---|---|
| [08a](08a_PW_LIVE_BATCH_LEGER.md) | Validations JS, crowds, CSS POS (4 fichiers, 12 tests) | FAIT (2026-03-21) |
| [08b](08b_PW_LIVE_POS_PAIEMENT.md) | POS paiement + adhesion NFC (2 fichiers, ~16 tests) | A FAIRE |
| [08c](08c_PW_LIVE_CROSS_TENANT.md) | Federation cross-tenant (1 fichier, 1 test complexe) | A FAIRE |

08b et 08c sont independants l'un de l'autre (mais dependent de 08a pour les fixtures).

## Pourquoi E2E live ?

Ces tests necessitent un **vrai navigateur Chromium** car ils verifient :
- Validation HTML5 native (`setCustomValidity`, `validity.valid`)
- Web components custom (`bs-counter` avec `dispatchEvent`)
- Librairies JS tierces (SweetAlert2 popups)
- HTMX swaps et lifecycle (hx-post, hx-target, configRequest events)
- CSS inline et rendu visuel (`background-color` sur tuiles POS)
- JS vanilla (filtrage categorie via `display:none`)
- Navigation cross-subdomain + cookies per-domain

Les 178 tests pytest (sessions 01-07) couvrent la logique Python/Django.
Les tests E2E couvrent le comportement navigateur. Les deux sont complementaires.
