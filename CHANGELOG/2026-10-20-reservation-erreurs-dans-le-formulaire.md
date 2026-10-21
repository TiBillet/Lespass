# Réservation : erreurs affichées dans le formulaire / Booking: errors shown inside the form

**Date :** 2026-10-20
**Migration :** Non

## Resume / Summary
**Quoi / What :**
- Réservation directe d'un événement (« Payer maintenant » / « Envoyer la demande ») : un refus (limite par personne, stock, jauge, adhésion requise, créneau déjà réservé…) s'affiche dans le formulaire, au-dessus des boutons, sans recharger la page. Les champs remplis restent.
- Messages du validateur réécrits en français, précis : nom du produit ou du tarif, limite, quantités demandées et déjà réservées, nom de l'adhésion requise.
- « Ajouter au panier » : un refus laisse désormais le panneau de réservation ouvert (il se fermait aussi sur une erreur).

/ Direct booking refusals are shown inside the form without reloading (filled fields kept). Validator messages rewritten (French source, names and quantities). Cart refusals keep the booking panel open.
**Pourquoi / Why :** Chaque refus rechargeait la page : la personne perdait toute sa saisie. Certains messages trompaient (« capacité maximale atteinte » pour une limite par personne).
/ Every refusal reloaded the page and wiped the form; some messages were misleading.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/views.py` | `EventMVT.reservation` : refus = partiel d'erreurs + `HX-Retarget: #reservation-erreurs`, plus de `HttpResponseClientRedirect` |
| `BaseBillet/templates/commun/formulaires/reservation_erreurs.html` | Nouveau partiel : liste des erreurs |
| `BaseBillet/templates/commun/formulaires/reservation.html` | Zone `#reservation-erreurs` dans le pied collant du formulaire |
| `BaseBillet/validators.py` | `ReservationValidator` : 14 messages réécrits (FR, noms, quantités) ; f-string dans `_()` de l'option corrigé |
| `BaseBillet/templates/htmx/components/panier_scripts.html` | Le panneau ne se ferme plus quand le panier refuse (toast de niveau `error`) |
| `tests/pytest/test_reservation_erreurs_dans_le_formulaire.py` | 3 tests (vue + messages) |

i18n : ~15 chaînes nouvelles (msgid FR) — workflow i18n à lancer.

Audit — non corrigé ici :
- Formulaire d'adhésion (`MembershipMVT.create`) : même défaut (messages + rechargement), et le message est passé en liste Python (`['…']` affiché tel quel).
- Panier : en ajout de plusieurs tarifs, le message de limite compte comme « déjà au panier » les billets du tarif précédent de la même demande (ex : « 0 confirmé(s) + 10 dans le panier » alors que le panier est vide après refus).
- Messages du validateur encore en anglais : code promo, montant libre, quantité invalide.

---

## Comment tester (a la main) / Manual test
### Test 1 — refus en réservation directe
1. Connecté, ouvrir un événement avec « billets limités à N par personne » (ex : What the Funk, 10).
2. Mettre 10 + 10 billets, cliquer « Payer maintenant ».
3. Attendu : message rouge au-dessus des boutons « Limite de 10 billets par personne pour cet événement. Demandés : 20, déjà réservés : 0. » ; le panneau reste ouvert, les quantités restent.
4. Corriger à 10 au total, renvoyer : le parcours continue normalement.

### Test 2 — refus panier
1. Même saisie (10 + 10), cliquer « Ajouter au panier ».
2. Attendu : toast d'erreur, le panneau reste ouvert, les quantités restent, le panier reste vide.
3. 1 billet, « Ajouter au panier » : toast de succès, le panneau se ferme.

### Test 3 — adhésion requise
1. Tarif réservé aux adhérents, compte sans adhésion à jour, « Payer maintenant ».
2. Attendu : message dans le formulaire qui nomme le tarif et l'adhésion requise.
