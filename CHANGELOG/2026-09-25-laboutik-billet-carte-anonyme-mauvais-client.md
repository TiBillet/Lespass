# LaBoutik : une carte anonyme reprenait le client de la vente précédente / LaBoutik: an anonymous card reused the previous sale's client

**Date :** 2026-09-25
**Migration :** Non

## Resume / Summary

**Quoi / What :** vente d'un billet avec une carte liée à une personne (Alice) : OK.
Juste après, vente d'un billet avec une carte **anonyme** : Alice réapparaissait, et
**c'est elle qui recevait les billets**.
/ After selling a ticket to a linked card's owner, the next sale with an anonymous card
  reused that owner: the wrong person got the tickets.

**Pourquoi / Why :** pendant un paiement, l'identité du client est rangée dans
`#addition-form` sous forme de champs cachés : `email_adhesion`, `prenom_adhesion`,
`nom_adhesion`, et la carte lue dans `tag_id`. « Nouvelle vente » (`additionReset()`)
ne retirait que les lignes du panier (`repid-*`, `custom-*`). À la vente suivante, la carte
anonyme n'a pas de propriétaire : `identifier_client()` puis la création des billets se
rabattent sur l'e-mail du formulaire (`if email and not user`)… qui était celui d'Alice.
Le serveur ne peut pas distinguer un e-mail périmé d'un e-mail fraîchement saisi : la
correction est donc côté navigateur.
/ Stale client fields stayed in #addition-form; the server fell back on the stale email.

**Correction / Fix :** `additionOublierLeClient()` (addition.js) retire `email_adhesion`,
`prenom_adhesion`, `nom_adhesion` et vide `tag_id`. Elle est appelée :
- à la remise à zéro du panier (« Nouvelle vente », vider le panier) — qui retire aussi le
  contexte du panier (`panier_a_billets`, `panier_a_adhesions`, `panier_a_recharges`,
  `moyens_paiement`) ;
- au début de chaque identification (`hx_display_type_payment.html`, message
  `additionManageForm` / `oublierLeClient`), car un parcours abandonné (popup fermée)
  ne passe pas par la remise à zéro.
/ Client fields are cleared on cart reset and at the start of every identification.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `laboutik/static/js/addition.js` | `CHAMPS_DU_CLIENT`, `CHAMPS_DU_CONTEXTE_DU_PANIER`, `additionOublierLeClient()` ; appel dans `additionReset()` ; action `oublierLeClient` dans `additionManageForm()` |
| `laboutik/templates/laboutik/partial/hx_display_type_payment.html` | Oubli du client au début de l'identification (mode cashless « C » et mode « identification requise ») |
| `tests/e2e/test_addition_oubli_du_client.py` | **Nouveau** : 6 tests navigateur (sans serveur) sur le vrai `cotton/addition.html` |

### Migration
- **Migration necessaire / Migration required:** Non

## Tests a realiser / How to test

### Automatiques
```bash
poetry run pytest tests/e2e/test_addition_oubli_du_client.py -v   # navigateur, sans serveur
```
Avec l'ancien `addition.js`, le scénario garde `alice@exemple.org` et `CARTEALICE` après
« Nouvelle vente » ; avec la correction, tout est effacé (vérifié le 2026-09-25).

### Test 1 : le scénario du bug
1. PV billetterie. Carte **A** liée à un compte (Alice). Carte **B** anonyme.
2. Ajouter un billet → Valider → Scanner une carte TiBillet → carte A → payer → **Nouvelle vente**.
3. Ajouter un billet → Valider → Scanner une carte TiBillet → carte **B**.
4. Attendu : **formulaire d'identification vide** (pas d'Alice). Saisir Bob → payer.
5. Admin → Réservations : le billet 1 est à Alice, le billet 2 à **Bob**.

### Test 2 : identification abandonnée
1. Billet → Valider → Saisir email / nom → saisir Alice → valider l'identification.
2. Fermer la popup de paiement **sans payer** (croix).
3. Valider à nouveau → Scanner la carte anonyme B.
4. Attendu : formulaire vide, pas d'Alice.

### Test 3 : pas de régression
Adhésion et recharge avec une carte liée : l'identité du client est toujours reprise
correctement (elle est rangée à nouveau après le scan).
