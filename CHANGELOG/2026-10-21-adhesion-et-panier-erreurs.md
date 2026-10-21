# Adhésion et panier : erreurs justes, saisie conservée / Membership and cart: accurate errors, input kept

**Date :** 2026-10-21
**Migration :** Non

## Resume / Summary
**Quoi / What :**
- Formulaire d'adhésion (« Payer maintenant » / « Envoyer ma demande ») : un refus s'affiche dans le formulaire, au-dessus des boutons, sans recharger la page. Plusieurs erreurs = une liste à puces (plus de `['…']`). Un nouvel envoi efface l'erreur précédente.
- Panier, ajout de plusieurs tarifs d'un coup : le message de limite compte juste. Les tarifs de la même demande sont « demandés », pas « déjà au panier ». Messages en français, avec le nom du produit ou du tarif, comme en réservation directe.

/ Membership form refusals are shown inside the form, without reloading. Cart batch add: limit messages count the current request as "requested", not "already in cart".
**Pourquoi / Why :** Un refus d'adhésion rechargeait la page (saisie perdue) et affichait une liste Python. En ajout groupé, le message annonçait « 10 dans le panier » alors que le panier restait vide.
/ A membership refusal reloaded the page and showed a Python list; the batch limit message reported tickets in the cart that were rolled back.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/views.py` | `MembershipMVT.create` : refus = partiel d'erreurs + `HX-Retarget: #adhesion-erreurs` ; `PanierMVT.add_tickets_batch` passe le panier d'avant la demande |
| `BaseBillet/templates/commun/adhesion/form.html` | Zone `#adhesion-erreurs` dans le pied ; `hx-on::before-request` la vide à chaque envoi |
| `BaseBillet/templates/commun/formulaires/reservation_erreurs.html` | Partiel partagé réservation + adhésion (commentaire) |
| `BaseBillet/services_panier.py` | `validate_ticket_cart_limits` : paramètre `items_du_panier_avant_la_demande`, messages FR (demandés / déjà au panier / déjà réservés), jauge ; `add_ticket` le transmet |
| `tests/pytest/test_adhesion_erreurs_dans_le_formulaire.py` | 2 tests (vue adhésion) |
| `tests/pytest/test_panier_mvt.py` | 2 tests (ajout groupé refusé, panier vide puis panier déjà rempli) |

i18n : ~4 chaînes nouvelles (msgid FR) — workflow i18n à lancer.

Suite le même jour : `CHANGELOG/2026-10-21-erreurs-panier-dans-le-formulaire.md` (refus du panier dans le formulaire, limites vérifiées sur la demande entière).

---

## Comment tester (a la main) / Manual test
### Test 1 — adhésion refusée
1. Ouvrir une adhésion, remplir le formulaire, provoquer un refus serveur (ex : adhésion limitée à 1 par personne déjà prise).
2. Attendu : message rouge au-dessus des boutons, la page ne se recharge pas, les champs restent.
3. Recliquer : le message disparaît pendant l'envoi.

### Test 2 — panier, ajout groupé
1. Connecté, What the Funk (10 par personne), 10 + 10 billets, « Ajouter au panier ».
2. Attendu : « Limite de 10 billets par personne pour cet événement. Demandés : 20, déjà au panier : 0, déjà réservés : 0. », panier vide, panneau ouvert.
3. Mettre 2 billets au panier, puis 5 + 5 : « Demandés : 10, déjà au panier : 2 ». Le panier garde ses 2 billets.
