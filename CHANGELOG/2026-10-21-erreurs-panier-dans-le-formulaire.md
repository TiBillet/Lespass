# Refus du panier affichés dans le formulaire / Cart refusals shown inside the form

**Date :** 2026-10-21
**Migration :** Non

## Resume / Summary
**Quoi / What :** Une seule règle pour les trois formulaires (événement, adhésion, créneau de ressource) : **un refus s'affiche dans le formulaire, au-dessus des boutons ; un succès s'affiche en toast**. « Ajouter au panier » et « Ajouter au panier et payer » suivent maintenant la même règle que « Payer maintenant ». Le panneau reste ouvert, la saisie reste.
Le panier vérifie aussi les limites par personne sur la demande entière, dans le même ordre et avec les mêmes messages que la réservation directe (« Demandés : 20 » et non plus « 10 » pour 10 + 10 billets d'un même produit).
Les actions de la page panier (retirer, vider, code promo, payer depuis `/panier/`) gardent leur toast : il n'y a pas de formulaire où afficher l'erreur.
Si « Ajouter au panier et payer » ajoute l'article puis que le paiement est refusé, le message s'affiche dans le formulaire et le compteur du panier se met à jour (l'article reste au panier). Exception : si un AUTRE article du panier n'est plus valide au moment de payer, on renvoie vers la page panier, comme avant.

/ One rule for the three forms: refusal inside the form above the buttons, success as a toast. Cart limits are checked on the whole request, like direct booking. Cart page actions keep their toasts.
**Pourquoi / Why :** Le même refus s'affichait en toast (« Ajouter au panier ») ou dans le formulaire (« Payer maintenant »), avec des quantités différentes. Une erreur de créneau en ajout au panier (réponse 422 avec `hx-swap="none"`) ne s'affichait nulle part.
/ The same refusal showed as a toast or in the form depending on the button; slot errors on cart add were never shown.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/views.py` | `PanierMVT._refus_dans_le_formulaire()` ; `add_tickets_batch`, `add_membership`, `add_resource` l'utilisent ; `checkout(refus_dans_le_formulaire=...)` ; `add_tickets_batch` passe toute la demande |
| `BaseBillet/services_panier.py` | `validate_ticket_cart_limits` : demande entière, ordre et messages de `ReservationValidator` ; `add_ticket` : contrôle « quantité seule » retiré (couvert par la limite du tarif) |
| `BaseBillet/templates/commun/formulaires/reservation.html` | Boutons du panier : `hx-target="#reservation-erreurs"` |
| `BaseBillet/templates/commun/adhesion/form.html` | Boutons du panier : `hx-target="#adhesion-erreurs"` |
| `booking/templates/booking/partials/book_form.html` | Zone `#ressource-erreurs` au-dessus des boutons (erreurs directes et panier) ; boutons du panier la visent |
| `BaseBillet/templates/htmx/components/panier_scripts.html` | Le panneau ne se ferme que sur un toast de succès |
| `tests/pytest/test_panier_mvt.py` et 3 autres fichiers pytest, `tests/e2e/test_panier_flow.py` | Refus attendus dans le formulaire ; nouveaux tests (demande entière, « ajouter et payer », créneau invalide) |

i18n : 3 chaînes (messages de limite du panier, avec « déjà au panier ») déjà présentes dans les `.po` sans traduction EN — workflow i18n à lancer. L'entrée « Il ne reste que %(n)s place… » est marquée `fuzzy` avec une traduction fausse : à nettoyer.

---

## Comment tester (a la main) / Manual test
### Test 1 — événement
1. What the Funk (produit « Billet » limité à 1), 10 + 10, « Ajouter au panier » : message rouge au-dessus des boutons « Limite de 1 billet « Billet » par personne. Demandés : 20, déjà au panier : 0, déjà réservés : 0. », aucun toast, panneau ouvert.
2. « Payer maintenant » : même message, sans « déjà au panier ».
3. 1 billet, « Ajouter au panier » : toast vert, panneau fermé.
4. Rouvrir (recharger la page), 1 billet, « Ajouter au panier et payer » : refus dans le formulaire, « déjà au panier : 1 ».

### Test 2 — adhésion
1. Adhésion récurrente, « Ajouter au panier » : « Les adhésions récurrentes nécessitent un paiement direct… » dans le formulaire, aucun toast, prénom et nom gardés.

### Test 3 — créneau de ressource
1. Ajouter un créneau au panier (toast vert), recliquer le même créneau, « Ajouter au panier » : message de chevauchement au-dessus des boutons, panneau ouvert.

### Test 4 — page panier (inchangé)
1. Sur `/panier/`, code promo inconnu : toast d'erreur.
