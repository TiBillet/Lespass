# Doc Laboutik

## Ce qui a ete realise (branche `integration_laboutik`)

### Phase -1 — Dashboard Groupware ✅
Activation modulaire via `module_*` fields sur Configuration.
Dashboard Unfold avec cartes de modules (switches HTMX, modal confirmation, HX-Refresh).
Sidebar conditionnelle selon les modules actifs.

### Phase 0 — fedow_core fondations ✅
App `fedow_core` (SHARED_APPS) : Asset, Token, Transaction (id BigAutoField), Federation.
Services : WalletService, TransactionService, AssetService.
Flow invitation/acceptation d'assets et de lieux federes.
AuthBillet.Wallet enrichi (public_pem, name). CarteCashless enrichi (wallet_ephemere).

### Phase 1 — Modeles POS + Admin ✅
Product unifie : 8 champs POS, proxy POSProduct, CategorieProduct.
laboutik/models.py : PointDeVente, CartePrimaire, Table, CategorieTable.
Admin Unfold POSProductAdmin, CategorieProductAdmin, PointDeVenteAdmin.
Donnees de test : `manage.py create_test_pos_data`.

**Bonus Phase 1 — Design CSS des tuiles articles ✅**
Refonte `cotton/articles.html` : icone categorie + nom en flex-row, pills multi-tarif avec
`flex-wrap: wrap` + `max-height` (max 2 rangs), footer sans `width:100%`, texte ×2 lisible
la nuit sur un petit ecran. Voir la section "Bonus realises" de Phase 1 dans PLAN_INTEGRATION.md.
Regles CSS documentees dans `GUIDELINES.md` (section laboutik — UI et Design).

### Phase 2.5 — POS Adhesion (multi-tarif + prix libre) ✅
PointDeVente.comportement += ADHESION.
Multi-tarif : overlay JS `tarif.js` quand un produit a plusieurs Price ou `free_price`.
Prix libre : input avec minimum, validation front (tarif.js) + back (serializer).
Identification client : scan NFC ou formulaire email/nom/prenom.
Fusion wallet_ephemere → user.wallet via WalletService.fusionner_wallet_ephemere().

## Composants cotton

[<c-read-nfc>](https://nuage.codecommun.coop/f/3712)

## Plan detaille

Voir `laboutik/doc/PLAN_INTEGRATION.md` pour l'architecture complete, les decisions
prises, les phases restantes (2, 3, 4, 5, 6, 7) et les regles de travail avec Claude Code.

## Plan UX

Voir `laboutik/doc/UX/PLAN_UX_LABOUTIK.md` pour l'audit visuel et les sessions de polish
(Sessions 1-5 toutes terminees).
