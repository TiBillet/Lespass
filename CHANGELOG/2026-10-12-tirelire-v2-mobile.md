# Tirelire V2 : un seul bouton, le scanner / V2 wallet: one button, the scanner

**Date :** 2026-10-12
**Migration :** Non

## Resume / Summary
**Quoi / What :**
- `/my_account/balance/` (skin V2) n'utilise plus le partiel du skin classic (grille Bootstrap + `square-btn`, rendus en grands ronds par le `.btn` V2).
- Un seul bouton : **« Scanner un QR code de paiement »** (il reste aussi sur `/my_account/`, sous « Ma carte »). Pleine largeur sur mobile. Email non validé : bouton gris désactivé. « Initier un paiement » reste sur `/my_account/` seulement.
- Retirés de la tirelire V2 : « Recharger en TiBillets », « Demander un remboursement » (et sa fenêtre), le texte sur le remboursement, « Voir le détail des monnaies ».
- **« Historique des transactions »** : bouton centré, avec icône.
- **Badge « Local » retiré** du tableau des monnaies (V2 et classic) : il n'était pas aligné et n'apporte rien au visiteur. L'admin (fiche portefeuille, `wallet_info.html`) garde le sien, qui lit toujours `is_local`.
- **Colonne « Dernière transaction » retirée** du tableau des monnaies (V2 et classic) : les monnaies locales (`fedow_core`) n'ont pas de date et affichaient « None ». La clé `last_transaction_datetime` des jetons locaux disparaît de `_agreger_tokens_locaux` ; leur clé `logo` devient `logo_url` (nom lu par le gabarit).
- La fenêtre de remboursement (`#refundPanel`) passe dans un partiel `tirelire_remboursement.html`, inclus par le skin classic, qui s'affiche comme avant. La variable `masquer_le_bouton_scanner` disparaît (plus aucun appelant).

/ V2 wallet page keeps only the scan button (full width on mobile); refill, refund and "show currency list" are gone; the history button is centred.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `pages/templates/pages/V2/vues/compte/balance.html` | bouton scanner seul, bouton d'historique |
| `pages/static/V2/css/V2.css` | section « Tirelire » (`.compte-tirelire*`, `.compte-historique*`) |
| `BaseBillet/templates/htmx/views/my_account/tirelire_remboursement.html` | nouveau : fenêtre de remboursement (skin classic) |
| `BaseBillet/templates/htmx/views/my_account/tirelire_section.html` | inclut la fenêtre ; skin classic seulement |
| `pages/templates/pages/{V2,classic}/vues/compte/partials/token_table.html` | colonne « Dernière transaction » et badge « Local » retirés |
| `tests/pytest/test_balance_soldes_et_recharge.py` | plus de badge « Local » dans le tableau |
| `BaseBillet/views.py` (`_agreger_tokens_locaux`) | clé de date retirée, `logo_url` |
| `tests/pytest/test_compte_cache_des_lieux.py` | test : plus de colonne ni de « None » |
| `tests/pytest/test_mon_espace_v2_boutons_qrcode.py` | règle V2 mise à jour + 2 tests (vérifiés par mutation) |

## Comment tester (a la main) / Manual test
1. En mobile, ouvrir `/my_account/balance/` : seul le bouton scanner, pleine largeur ; ni recharge, ni remboursement, ni « Voir le détail des monnaies » ; « Historique des transactions » centré.
2. Avec un email validé, le scanner est bleu et mène au scanner ; sinon il est gris.

`docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/test_mon_espace_v2_boutons_qrcode.py -q`
