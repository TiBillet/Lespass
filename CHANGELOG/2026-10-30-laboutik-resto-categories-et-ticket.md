# LaBoutik : mode restaurant aligné sur le service direct / Restaurant mode aligned with direct service

**Date :** 2026-10-30
**Migration :** Non

## Resume / Summary

**Quoi / What :** L'écran restaurant reprend la mise en page du service direct :
catégories en colonne à gauche, articles, ticket à droite. Les zones du bas ne sont plus
incluses, donc Check carte, CB / Espèces, Table et les touches de paiement sont cachés.
Dans le ticket, avec une table choisie : Vider, « Envoi prépa » et le bouton principal
« Ajouter à la table ». Sans table : Vider et VALIDER, qui ouvre les moyens de paiement.
/ The restaurant screen uses the direct-service layout. Bottom areas are no longer
included, so their keys are hidden. With a table, the ticket shows Empty, Send to prep
and Add to table; without a table, Empty and VALIDER.

**Pourquoi / Why :** Un seul écran de vente à connaître, et plus de place pour les
articles. Les touches cachées reviendront avec la suite du mode restaurant.
/ One sales layout to learn, more room for articles. Hidden keys will come back later.

**Encaisser la table / Pay the table :** dès qu'une table doit de l'argent, le bouton
« Encaisser la table » apparaît sous « Sur l'addition ». Il ouvre les moyens de paiement
de l'addition. Il reste grisé tant que le panier n'est pas vide, avec l'aide « Pour
encaisser, ajoutez le panier à la table ou videz-le ». En mobile, il faut ouvrir le ticket.
/ Once a table owes money, this button opens the payment methods for the bill. It stays
disabled until the cart is empty.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/templates/laboutik/views/restaurant_interface.html` | Structure `main` du service direct, zones du bas retirées, TODO |
| `laboutik/templates/cotton/addition_footer.html` | Boutons aussi en mode restaurant ; sans Check carte ; Envoi prépa et Ajouter à la table avec une table |
| `laboutik/templates/laboutik/partial/_addition_de_table.html`, `laboutik/static/css/addition_table.css` | Bouton « Encaisser la table » |
| `laboutik/static/js/addition.js` | Grise « Encaisser la table » tant que le panier n'est pas vide |
| `laboutik/static/css/addition.css` | Style `.addition-act-prepa` |
| `laboutik/static/css/restaurant_interface.css` | Retrait de la grille `#contenu` et des variables en double |
| `laboutik/static/js/footer.js`, `laboutik/views.py` | Commentaires |
| `laboutik/templates/laboutik/partial/win_bottom_left.html`, `win_bottom_right.html` | Commentaire : plus inclus pour l'instant |
| `tests/pytest/test_resto_addition_table.py`, `test_resto_touches_et_tables.py` | Tests adaptés au nouvel écran |

---

## Comment tester (a la main) / Manual test

Prérequis : PV « Terrasse » (`service_direct = False`, `accepte_commandes = True`).

### Test 1 — avec une table
1. Choisir une table : catégories à gauche, aucune zone en bas.
2. Bouton « Ajouter à la table » grisé tant que le panier est vide.
3. Ajouter un article, « Ajouter à la table » : popup, panier vidé, bandeau « Occupée ».
4. « Envoi prépa » : popup « Envoyé en préparation ». Un 2e appui : « Rien à envoyer ».
5. Filtrer par catégorie : les articles suivent.

### Test 1 bis — encaisser la table
1. Table libre : pas de bouton « Encaisser la table ».
2. Ajouter un article à la table : le bouton apparaît sous « Sur l'addition ».
3. Le toucher avec un panier vide : les moyens de paiement montrent le total de l'addition.
4. Ajouter un article au panier : le bouton se grise et l'aide s'affiche. Vider le
   panier ou l'ajouter à la table : le bouton redevient actif.
5. Après le paiement, OK ramène à la grille et la table est Libre.

### Test 2 — sans table
1. « Continuer sans table », ajouter un article.
2. VALIDER ouvre les moyens de paiement, et le paiement aboutit.

### Test 3 — largeurs
- 1100 px : « Ajouter à la table » reste lisible à côté de Vider et Envoi prépa.
- 360 px : ticket replié en bas, bandeau visible une fois ouvert, pastille de table.

### Verifs DB / Playwright
- `poetry run pytest tests/pytest/test_resto_addition_table.py tests/pytest/test_resto_touches_et_tables.py`
- Aucun E2E du mode restaurant pour l'instant.
