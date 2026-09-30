# laboutik : après « Fonds insuffisants », le paiement suivant passait sans nouveau scan de carte

**Date :** 2026-09-29
**Migration :** Non / No

## Résumé / Summary

**Quoi / What :** un panier en monnaie temps (ou en points) payé avec une carte
qui n'a pas assez de solde affiche « Fonds insuffisants ». Si on fermait la
popup puis on relançait le paiement, il passait tout de suite, avec l'ancienne
carte, sans la scanner à nouveau.
/ After an "insufficient funds" refusal, the next payment went through at once
with the previous card, without a new scan.

**Pourquoi / Why :** la lecture NFC remplit `#nfc-tag-id` dans `#addition-form`
et change son `hx-post` vers `/payer/`. La croix et le fond de
`hx_funds_insufficient.html` vidaient seulement `#messages`. Au clic suivant
sur VALIDER, `additionDisplayPaymentTypes()` soumettait le formulaire à
l'URL courante, donc `/payer/`, avec le tag de la carte : paiement direct.
Les autres popups (`hx_messages.html`, `hx_complement_paiement.html`)
appelaient déjà `initUrlAddition()` à la fermeture ; celle-ci non.
/ Closing only emptied `#messages`: the form kept the card tag and the `/payer/` URL.

**Correctif / Fix :** nouvelle fonction `abandonnerLePaiementRefuse()`
(`tibilletUtils.js`) appelée par la croix et le fond : remet l'URL sur
`moyens_paiement` et oublie le client et la carte lue
(`additionOublierLeClient`). Le prochain VALIDER redemande la carte.

## Revue des autres popups / Other popups reviewed

Critère : après une lecture NFC, la fermeture doit remettre l'URL sur
`moyens_paiement` (`initUrlAddition`). Sinon VALIDER reposte vers `/payer/`.
/ Rule: after an NFC read, closing must reset the URL.

| Popup | Etat / Status |
|---|---|
| `hx_card_feedback.html` (carte inconnue, check carte) | OK : formulaire propre `#form-check-nfc` dans `#messages`, vidé à la fermeture. `#addition-form` n'est pas touché. |
| `hx_messages.html` après NFC (`_payer_par_nfc`, `identifier_client`, `_executer_paiement_complementaire`, dont « Carte inconnue ») | OK : toutes passent `action = initUrlAddition();`. La carte périmée reste dans le formulaire, mais le prochain VALIDER repasse par `moyens_paiement`. Tout panier qui lit `tag_id` (recharge, adhésion, billet) passe par l'identification, qui l'efface. |
| `hx_complement_paiement.html` | OK : `initUrlAddition()` à la fermeture. |
| `hx_display_type_payment.html` (client identifié) | OK : `initUrlAddition()` à la fermeture. |
| `hx_return_payment_success.html` | OK : `manageReset()` vide tout le panier. |
| `hx_read_nfc.html`, `hx_lire_nfc_complement.html` | OK : fermés avant la lecture, l'URL n'a pas encore changé. |
| `_payer_en_especes` « Il y a une erreur ! » | **Corrigé** : pas d'`action`, l'URL restait sur `/payer/` et VALIDER renvoyait un paiement espèces direct. |

## Fichiers modifiés / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `laboutik/static/js/tibilletUtils.js` | Ajout de `abandonnerLePaiementRefuse()` |
| `laboutik/templates/laboutik/partial/hx_funds_insufficient.html` | Croix et fond appellent `abandonnerLePaiementRefuse()` |
| `laboutik/views.py` | `_payer_en_especes` : `action: initUrlAddition();` sur l'erreur « Il y a une erreur ! » |
| `tests/pytest/test_popups_paiement_v2.py` | Test : la fermeture de la popup appelle le reset |

## Tester / How to test

1. Caisse V2, panier avec un article en monnaie temps (ex : 5 T).
2. VALIDER → CASHLESS → scanner une carte avec moins de 5 T.
3. « Fonds insuffisants » s'affiche. Fermer la popup (croix ou fond).
4. VALIDER à nouveau : l'écran des moyens de paiement revient,
   puis la caisse redemande la carte. Aucun paiement n'est fait sans scan.
5. Idem en retirant un article pour que le solde suffise : la carte doit
   quand même être rescannée.

Test pytest : `pytest tests/pytest/test_popups_paiement_v2.py -v`.
