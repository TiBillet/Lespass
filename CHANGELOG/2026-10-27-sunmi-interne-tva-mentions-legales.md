# Ticket Sunmi interne : TVA, mentions légales, simulation, QR code / Sunmi built-in receipt: VAT, legal mentions, simulation, QR code

**Date :** 2026-10-27
**Migration :** Non

## Resume / Summary
**Quoi / What :** l'imprimante interne des tablettes Sunmi (V3 Mix, type `SI`) imprime maintenant la ventilation TVA (tableau par taux, Total HT, Total TVA), les mentions légales (raison sociale, adresse, SIRET, n° de TVA) et le bandeau « *** SIMULATION *** » du mode école. Son QR code sort enfin : le serveur envoyait le type `qrcode`, l'application Android attend `qrCode`.
/ The Sunmi built-in printer now prints the VAT breakdown, the legal mentions and the training-mode SIMULATION banner. Its QR code now prints: the server sent type `qrcode`, the Android app expects `qrCode`.

**Pourquoi / Why :** retour d'un lieu : « le ticket de l'innerprinter du SUNMI v3 mix ne sort pas la TVA ». Le ticket part en ESC/POS pour les imprimantes réseau/cloud/mock et en commandes JSON pour la Sunmi interne ; ces blocs n'existaient que côté ESC/POS. Ce sont des exigences LNE (3 et 5) : sans eux, un ticket sorti sur V3 Mix n'est pas conforme.
/ A venue reported missing VAT on V3 Mix receipts. These blocks only existed in the ESC/POS path; they are LNE requirements.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/printing/sunmi_inner.py` | Blocs mentions légales, SIMULATION, ventilation TVA ; séparateur après DUPLICATA ; QR code `qrCode` + `modulesize` + centré |
| `tests/pytest/test_ticket_client_imprime.py` | Test de parité ligne à ligne Sunmi interne ↔ ESC/POS sur un ticket complet ; test du format du QR code |

Aucune mise à jour de l'application Android : seules des commandes `text` et `qrCode`, déjà lues par `manageSunmiPrint.js`.
/ No Android app update needed.

Suite (passer la Sunmi interne en ESC/POS brut, une seule traduction) : `TECH_DOC/SESSIONS/TODO/IMPRESSION-sunmi-interne-escpos-brut.md`.

---

## Comment tester (a la main) / Manual test

### Test 1 — sur une V3 Mix (le seul test qui compte pour le papier)
1. Terminal appairé avec une imprimante de type « Sunmi Inner ».
2. Vendre un article avec TVA, payer, cliquer « Imprimer ».
3. Attendu : sous le total, le tableau `TVA%  HT  TVA  TTC`, puis `Total HT` et `Total TVA` ; en haut, raison sociale / adresse / SIRET / TVA du lieu (si renseignés dans la configuration).
4. Vérifier que les lignes du tableau TVA tiennent sur la largeur du papier (32 caractères).

### Test 2 — mode école
1. Activer le mode école dans la configuration LaBoutik.
2. Imprimer un ticket : « *** SIMULATION *** » en haut.

### Test 3 — QR code
1. Imprimer un billet vendu en caisse (ticket avec QR code) sur la V3 Mix.
2. Attendu : le QR code sort, centré, et se scanne.

### Verifs automatiques
- `docker exec lespass_django poetry run pytest tests/pytest/test_ticket_client_imprime.py -q`
