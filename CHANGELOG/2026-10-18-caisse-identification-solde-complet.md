# Caisse : l'écran « Client identifié » affiche le solde complet / Register: full balance on the identified-client screen

**Date :** 2026-10-18
**Migration :** Non

## Resume / Summary
**Quoi / What :** l'écran « Client identifié » de la caisse (avant de payer une adhésion,
un billet ou une recharge) affiche le solde de la carte avec `obtenir_solde_complet_carte()` :
monnaies locales + argent du réseau (ancien Fedow), comme le « check carte ».
/ The identified-client screen shows the card balance with `obtenir_solde_complet_carte()`:
local currencies + network money, like the card check.

**Pourquoi / Why :** l'écran ne lisait que le portefeuille local. Une carte dont l'argent
est sur le réseau affichait « Solde : 0,00 € », alors que le paiement NFC (qui lit aussi
le réseau) était accepté. Remonté par un client de La Cabine (adhésion + café).
/ The screen only read the local wallet: a card with network money showed 0.00 € while
the NFC payment was accepted.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/views.py` | `PaiementViewSet.identifier_client` : les 2 lectures du solde (client identifié, recharge sur carte anonyme) passent par `obtenir_solde_complet_carte()` |
| `tests/pytest/test_identification_solde_reseau.py` | Nouveau : adhésion (local + réseau) et recharge sur carte anonyme (réseau seul) |

---

## Comment tester (a la main) / Manual test

### Test 1 — adhésion, argent sur le réseau
1. Prendre une carte dont l'argent est sur le réseau (le « check carte » affiche un montant,
   la monnaie locale du lieu est à 0).
2. En caisse : panier avec une adhésion → moyen « cashless » → scanner la carte.
3. Attendu : l'écran « Client identifié » affiche « Solde : <le montant du check carte> ».

### Test 2 — recharge sur carte anonyme
1. Une carte anonyme avec de l'argent sur le réseau.
2. Panier avec une recharge seule → scanner la carte.
3. Attendu : le solde affiché est celui du check carte, pas 0 €.

### Test 3 — réseau injoignable
1. Couper l'accès à l'ancien Fedow (ou un lieu non relié).
2. Attendu : l'écran s'affiche quand même, avec le solde local seulement (lecture dégradée
   en silence, comme le check carte).

### Automatique
`make test ARGS="tests/pytest/test_identification_solde_reseau.py"`
