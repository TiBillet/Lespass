# LaBoutik : corrections du mode restaurant après review / Restaurant mode fixes after review

**Date :** 2026-10-30
**Migration :** Non

## Resume / Summary

**Quoi / What :**
- **« Ajouter à la table »** : le bouton envoie aussi le panier en préparation. Un seul
  appui commande et imprime. Le bouton « Envoi prépa » est retiré du ticket : il faisait
  la même chose. Des articles restés non envoyés partent avec le prochain ajout.
- **Articles sans préparation** : un article dont la catégorie n'a pas d'imprimante n'est
  jamais « à envoyer ». Il ne compte ni dans le badge, ni dans « Envoi prépa ».
- **Stock** : les articles commandés et non payés sont comptés comme réservés, pour toutes
  les ventes (tables et comptoir). Le stock réel ne bouge qu'au paiement. Une addition
  n'est plus jamais bloquée par le stock à l'encaissement.
- **Encaissement** : refusé tant qu'un article à préparer n'est pas envoyé.
- **Montant** : le prix est figé à la commande. Le total annoncé est comparé au total
  recalculé : un total changé pendant le paiement est refusé.
- **Panier à 0 €** : le bouton VALIDER gratuit remplace la liste des moyens de paiement,
  pour une table comme en service direct.
- **Table à 0 €** : elle s'encaisse. Une table qui ne doit rien peut aussi être supprimée
  (archivée).
- **Concurrence** : le paiement garde le verrou de la table. Une commande arrivée avant
  ce verrou fait refuser le paiement (« L'addition a changé »), une commande arrivée après
  ouvre sa propre vente et reste à payer. Une seule vente par table, et un 2e terminal
  reçoit un message au lieu d'une erreur 500.
- **Impression** : 3 nouveaux essais, sur la seule imprimante en échec, puis alerte aux
  caisses. Bouton « Réimprimer ». Une imprimante désactivée est signalée à l'envoi.
- **Check carte** : le bouton revient dans le ticket en mode restaurant.

/ Articles without a printer never wait to be sent. Unpaid ordered articles are counted as
reserved for every sale. Payment is refused while a dish is unsent. Prices are frozen at
order time and the announced total is checked. Zero bills can be paid, and tables owing
nothing can be deleted. Table locking, safe closing, a clear message instead of a 500.
Print retries, terminal alert, reprint button. Card check is back on the ticket.

**Pourquoi / Why :** La review du 30/10 a reproduit ces bugs : table impossible à encaisser,
plats payés jamais envoyés, montant encaissé différent de l'écran, table à 0 € bloquée.
/ The review reproduced these bugs on the table flow.

**Limites connues / Known limits :**
- L'imprimante d'une catégorie n'est pas réglable dans l'admin : chantier suivant, prioritaire.
- Une table oubliée immobilise son stock jusqu'au paiement ou au Z.
- Les badges de stock des tuiles affichent le stock réel, sans les réservations.
- L'alerte d'impression n'est pas conservée : une caisse hors ligne ne la voit pas.
- Les débits de l'ancien Fedow (NFC) restent à régulariser à la main si deux terminaux
  paient la même table au même instant.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/services_table.py` | Préparation, réservations, prix figé, verrous, clôture filtrée, suppression, réimpression |
| `laboutik/views.py` | Garde de stock, refus articles à envoyer et total changé, `reimprimer`, `supprimer_table`, retrait de `mode_restaurant` |
| `laboutik/printing/tasks.py` | Nouveaux essais par imprimante, alerte WebSocket |
| `laboutik/templates/laboutik/partial/hx_alerte_impression.html` | Nouveau : alerte d'impression |
| `laboutik/templates/laboutik/partial/_addition_de_table.html` | Sans préparation, Encaisser, Supprimer, Réimprimer |
| `laboutik/templates/laboutik/partial/hx_display_type_payment.html`, `cotton/addition.html` | Champ `total_attendu_addition` |
| `laboutik/templates/cotton/addition_footer.html`, `laboutik/static/css/addition.css` | Check carte de retour, Envoi prépa retiré |
| `laboutik/templates/laboutik/views/restaurant_interface.html`, `restaurant_interface.css` | Zone `#alerte-impression` |
| `laboutik/static/js/addition.js`, `partial/win_bottom_right.html` | Grisé, addition à 0 €, confirmation de suppression |
| `laboutik/static/css/addition_table.css` | Boutons de la table |
| `BaseBillet/services_vente.py` | Documentation de `annuler_vente` |
| `tests/pytest/test_resto_addition_table.py` | Nouveaux tests |

---

## Comment tester (a la main) / Manual test

Prérequis : une catégorie cuisine avec imprimante, une catégorie boissons sans imprimante.

### Test 1 — boissons
1. Ajouter 2 plats et 3 boissons, « Ajouter à la table » : ticket pour les plats seulement.
2. « Sur l'addition » : plats avec coche, boissons « sans préparation », aucun badge.
3. « Encaisser la table » est actif.

### Test 2 — stock (produit avec vente hors stock interdite, stock 4)
1. Commander 3 en table. Vendre 2 au comptoir : refus « 2 dans le panier, 1 en stock ».
2. Vendre 1 au comptoir : accepté. Encaisser la table : accepté.

### Test 3 — montant
1. Ouvrir les moyens de paiement d'une table sur le terminal A.
2. Ajouter un article depuis le terminal B.
3. Valider sur A : refus « L'addition a changé », Retour recharge l'écran.
4. Modifier un tarif après une commande : l'addition garde l'ancien prix.

### Test 4 — table à 0 € et suppression
1. Commander un article à 0 € : « Encaisser la table » est visible et propose VALIDER.
2. Table sans dette : « Supprimer la table », « Confirmer » : retour à la grille.
3. Table qui doit de l'argent : pas de bouton.

### Test 5 — impression
1. Couper l'imprimante, « Envoi prépa » : environ 90 s plus tard, l'alerte s'affiche en bas.
2. Rétablir, « Réimprimer » : le ticket sort.
3. Désactiver l'imprimante : l'envoi le signale tout de suite.

### Test 6 — largeurs et Check carte
- 1100 px et 360 px : Vider, Check carte et « Ajouter à la table » sur une rangée, lisibles.
  Check carte ouvre la lecture de carte.

### Verifs DB / Playwright
- `poetry run pytest tests/pytest/test_resto_addition_table.py tests/pytest/test_resto_touches_et_tables.py`
- Sélecteurs : `resto-addition-table-supprimer`, `resto-addition-table-reimprimer`,
  `resto-alerte-impression`, `resto-alerte-impression-message`, `addition-check-carte`.
- Aucun E2E du mode restaurant pour l'instant.
