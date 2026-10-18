# Caisse : le solde en euros affiché suit la cascade de paiement / Register: the displayed euro balance follows the payment cascade

**Date :** 2026-10-18
**Migration :** Non

## Resume / Summary
**Quoi / What :** nouvelle fonction `_soldes_de_la_cascade_fiduciaire(wallet, assets_accessibles)`
(`laboutik/views.py`) : les soldes qu'une carte peut dépenser en euros dans ce lieu (cadeau,
local, fédéré ; première monnaie accessible de chaque catégorie). Elle remplace les 3 copies
de la boucle de cascade (`_payer_par_nfc`, `payer_complementaire` carte 1 et 2ᵉ carte) et
calcule le total en euros de `obtenir_solde_complet_carte` (check carte, écran « Client
identifié »). La liste détaillée `tokens_locaux` garde tous les jetons.
/ New helper for the balances a card can spend in euros here; it replaces the 3 copies of the
cascade loop and computes the euro total of `obtenir_solde_complet_carte`.

**Pourquoi / Why :** le check carte additionnait TOUS les jetons du portefeuille et affichait
le résultat en € : le temps, les points de fidélité et la monnaie locale d'un lieu hors
fédération gonflaient le solde. Affichage seulement : le paiement ne dépensait déjà que la
cascade. Le paiement et l'affichage lisent maintenant le même calcul.
/ The card check summed ALL tokens and showed them in €. Display only: payment already used
the cascade. Payment and display now share one computation.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/views.py` | `_soldes_de_la_cascade_fiduciaire` (nouvelle) ; utilisée par `_payer_par_nfc`, `payer_complementaire` (carte 1, 2ᵉ carte) et `obtenir_solde_complet_carte` |
| `laboutik/views.py` | `identifier_client`, recharges offertes seules : suppression du calcul `solde_apres` (code mort, jamais lu par le gabarit) |
| `tests/pytest/test_identification_solde_reseau.py` | Nouveau test : 10 € local + temps + fidélité + monnaie hors fédération + 15 € réseau → total 25 € |
| `tests/pytest/test_c1_solde_complet_carte.py` | Le test du total lit la monnaie locale comme la cascade (première accessible) |

---

## Comment tester (a la main) / Manual test

### Test 1 — check carte avec temps et fidélité
1. Une carte avec 10 € de monnaie locale, du temps et des points de fidélité.
2. Check carte en caisse.
3. Attendu : le total en € vaut 10 € (+ le réseau éventuel). Le temps et les points
   s'affichent toujours dans la liste, sous leur nom.

### Test 2 — monnaie d'un lieu hors fédération
1. Une carte avec de la monnaie locale d'un autre lieu, non fédéré avec celui-ci.
2. Check carte.
3. Attendu : cette monnaie apparaît dans la liste, mais n'entre pas dans le total en €.

### Test 3 — paiement inchangé
1. Payer en NFC avec une carte cadeau + locale + réseau.
2. Attendu : même cascade qu'avant (cadeau, puis local, puis fédéré).

### E2E à surveiller
Les tests Playwright qui lisent `#cardSoldeVal` (check carte) avec une carte portant du temps
ou des points verront un total plus bas : c'est le comportement attendu.

### Automatique
`make test ARGS="tests/pytest/test_identification_solde_reseau.py tests/pytest/test_c1_solde_complet_carte.py"`
