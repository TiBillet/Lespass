# Tests du panier et parité avec / sans panier / Cart tests and with / without cart parity

**Date :** 2026-09-21
**Migration :** Non

## Résumé / Summary

**Quoi / What :** le panier (billets, adhésions, ressources) a maintenant ses tests : 289 tests
pytest (fonctions du panier, matérialisation en Commande, paiement d'une Commande mixte, vues
HTMX, et parité : chaque type d'achat donne le même résultat avec et sans panier), 6 E2E
(dont un vrai paiement Stripe et une vraie récompense monnaie Fedow). Les tests ont révélé des
bugs, corrigés ; les défauts non corrigés sont prouvés par des tests `xfail(strict=True)`.
`make coverage` mesure la couverture du code (couverture de `services_panier.py` : 28 → 78 %,
`services_commande.py` : 53 → 97 %).
/ The cart now has 289 pytest tests (9 strict xfail) and 6 E2E tests. Bugs found by the tests are fixed; the
remaining defects are proven by strict xfail tests. `make coverage` measures code coverage.

**Pourquoi / Why :** le panier est devenu le moteur d'achat principal et n'avait aucun test.
/ The cart became the main purchase engine and had no test.

### Bugs corrigés / Fixed bugs

| Réf. | Bug | Parcours |
|---|---|---|
| C5 | Un code promo remisait tous les produits billet de l'événement | les deux |
| C13 | Un prix libre ajouté deux fois au même événement était facturé au dernier montant | panier |
| C15 | On pouvait réserver une ressource au tarif (gratuit) d'une autre | les deux |
| C2 | L'adhésion obligatoire d'un tarif de ressource n'était pas vérifiée côté serveur | les deux |
| C10 | Adhésion gratuite par le panier : ni mail, ni récompense monnaie, ni rattachement au lieu | panier |
| C14 | Billet gratuit par le panier : billets envoyés deux fois | panier |
| C21 | Billet « payant » à 0 € : ouvrait un paiement Stripe en direct (désormais gratuit partout) | direct |
| C12 | Erreur 500 quand un connecté dépassait la limite par personne d'un événement | panier |
| C17 | Erreur 500 sur une quantité non numérique | panier |
| C16 | Le bouton « retirer » pouvait retirer le mauvais article | panier |
| C3 | Retirer puis remettre l'adhésion faisait refuser un panier valide | panier |
| C18 | Code promo inconnu, ou lié à un produit non choisi, ignoré sans message ; case newsletter perdue | panier |
| — | Ressource : tarif dépublié ou produit archivé accepté | direct |
| — | API v2 : billet « payant » à 0 € enregistré deux fois dans les ventes | API v2 |
| C27 | Événement « réservation gratuite » + billet payant (prix fixe ou libre) : billets activés et envoyés avant paiement, ou jamais activés après. Désormais envoyés ensemble, une fois, après le paiement ; rien si le paiement échoue | les deux, caisse |
| — | Panier : billet gratuit réservé aux adhérents activé même si le paiement de l'adhésion est abandonné | panier |
| — | Quantité démesurée (« 1e999999999 » ou « -1e999999999 ») : serveur bloqué plus de 20 s (possible sans compte) ; « Infinity » : erreur 500 | les deux |
| — | Prélèvement SEPA proposé pour un panier « adhésion payante + réservation gratuite » (billets bloqués jusqu'à 14 jours) | panier |
| — | Deux codes promo sur deux produits du même événement : le second billet facturé plein tarif | panier |
| — | Tarif repassé en prix fixe après l'ajout : le montant saisi restait facturé | panier |
| — | API v2 : réservation gratuite + billet à 0 € → ligne de vente de la réservation gratuite manquante | API v2 |
| C19 | Stocks : la quantité demandée n'était pas comptée (stock de 2, 1 vendu, 2 demandés : accepté) ; les paiements en cours non plus (deux acheteurs pour la dernière place) ; le stock d'une adhésion n'était jamais vérifié ; un créneau en attente de paiement n'était pas retenu | les deux |
| — | Paiement en cours : les places sont retenues 30 minutes partout (jauge, stocks, créneaux, caisse) ; la session Stripe expire au même moment | les deux |
| C26 | Formulaire billet : un champ « Code promo » par produit à codes, tous du même nom ; un code tapé dans le premier champ était perdu (plein tarif facturé). Désormais un seul champ par événement | les deux |
| — | Panier : la remise d'un code promo n'était pas affichée (plein tarif affiché, prix remisé facturé). Le panier affiche le prix barré, le prix remisé, le code, et un total égal au montant facturé | panier |
| — | Deux produits « réservation gratuite » dans la même commande directe : billets envoyés deux fois, webhook « réservation » envoyé deux fois. Désormais un seul envoi | direct, API v2 |
| C20 | Événement terminé ou archivé : billets encore vendables (sans date de fin : terminé 24 h après le début ; un événement dépublié reste réservable par lien direct). En direct, un festival commencé il y a plus d'un jour devenait impossible à réserver (filtre de date figé au démarrage du serveur). La caisse et l'API vendent jusqu'à la fin de l'événement | les deux, API v2 |
| C25 | Skin Faire Festival : aucun lien ni compteur du panier dans le menu | panier |
| C28 | Limite par personne en direct : « déjà acheté + demandé » n'était pas additionné | direct |
| C31 | Récompense monnaie et envoi à LaBoutik lancés avant la validation en base (récompense perdue au hasard) ; même règle pour l'envoi à LaBoutik des billets | les deux |

Billets à 0 € : leurs ventes sont désormais envoyées à LaBoutik, comme les autres (décision
du mainteneur).

Défauts prouvés et notés (non corrigés, voir le SPEC) : C22 prix libre sous 0,50 €, C23 limite par personne des adhésions au panier, C24 ressource à prix libre à 0 €, P16
booking gratuit direct. C29 (gabarit `booking/views/book.html` absent, erreur 500 sans HTMX)
est classé : inatteignable par un parcours normal.

### Fichiers modifiés / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/validators.py` | `TicketCreator` : code promo limité à son produit ; paiement décidé une fois par réservation ; réservation à 0 € validée sans Stripe (lignes via « payée ») ; `method_F` ne pose le statut gratuit que s'il décide du paiement et que la réservation est 100 % gratuite (C27) ; caisse mixte. `ReservationValidator` : quantité bornée, C20, C28 |
| `BaseBillet/models.py` | `Event.n_est_plus_en_vente()` (C20) |
| `BaseBillet/signals.py` | au paiement d'une Commande, ses réservations sans ligne de vente sont aussi validées |
| `BaseBillet/triggers.py` | récompense et envoi LaBoutik en `transaction.on_commit` (C31, `trigger_A` et `trigger_B`) |
| `pages/templates/pages/faire_festival/partials/navbar.html` | lien et compteur du panier (C25) |
| `BaseBillet/services_commande.py` | prix libre par item ; code promo par produit ; montant saisi seulement si le tarif est encore libre ; adhésion gratuite via `trigger_A` ; billets à 0 € via « payée » ; statut gratuit posé une seule fois ; newsletter |
| `BaseBillet/services_panier.py` | adhésions rejouées d'abord ; garde tarif/adhésion des ressources ; format du message de limite ; newsletter ; événement plus en vente refusé (C20) |
| `BaseBillet/views.py` | code promo inconnu ou d'un produit non choisi refusé ; quantité non numérique ou démesurée ignorée ; case newsletter lue |
| `BaseBillet/context_processors.py`, `htmx/components/panier_item.html` | rang réel de l'article pour le bouton « retirer » |
| `booking/booking_engine.py` | `validate_new_booking` : tarif de la ressource, publié, produit non archivé, adhésion active ou dans la même commande |
| `api_v2/serializers.py` | réservation gratuite : une ligne de vente par tarif, jamais deux |
| `Administration/management/commands/demo_data_v2.py`, `tests/e2e/conftest.py` | fixtures E2E du panier (adhésions payante / récurrente / à récompense, salle) |
| `Makefile`, `scripts/lancer_tests.sh`, `pyproject.toml`, `poetry.lock` | `make coverage` (`pytest-cov`) |
| `tests/pytest/fabriques_panier.py` + 5 fichiers `test_panier_*` / `test_commande_*` / `test_parite_*` | tests neufs |
| `tests/e2e/test_panier_flow.py` | 6 E2E |
| `tests/PIEGES.md` | section 13 ; 12.16 mis à jour (billet à 0 € : plus de Checkout, mais le catalogue Stripe reste appelé) |

i18n : 6 chaînes neuves (source française, dont 3 messages qui citaient « 15 minutes »,
paramétrés par `%(minutes)s`) et un msgid corrigé (`%(event)s`) → workflow de traduction à
lancer par le mainteneur. Les autres messages réutilisent des msgids existants.

---

## Comment tester (à la main) / Manual test

Se connecter sur `https://lespass.tibillet.localhost/` (compte de test `admin@admin.com`).

### Test 1 — code promo sur un événement à deux produits (C5)
1. Admin : un événement avec deux produits billet (A et B, 10 € chacun) et un code promo -50 %
   lié au produit A.
2. Front : prendre 1 A et 1 B avec le code, « Ajouter au panier », payer.
3. Attendu : Stripe affiche 15 € (A à 5 €, B à 10 €).

### Test 2 — prix libre ajouté deux fois (C13)
1. Événement à tarif prix libre : ajouter 1 billet à 10 €, puis 1 billet à 20 €.
2. Attendu : le panier affiche 30 €, Stripe facture 30 €.

### Test 3 — adhésion gratuite par le panier (C10)
1. Adhésion à 0 € : « Ajouter au panier » puis « Payer ».
2. Attendu : mail de confirmation reçu, l'adhérent apparaît dans l'admin du lieu ; si le tarif
   verse une récompense monnaie, le solde du portefeuille augmente.

### Test 4 — billet « payant » à 0 € (C21)
1. Tarif de catégorie billet payant à 0 € : « Payer maintenant » (sans panier).
2. Attendu : pas de page Stripe, réservation confirmée, billet dans « Mes réservations ».

### Test 5 — ressource (C2, C15)
1. Tarif de salle réservé aux adhérents : sans adhésion, la réservation est refusée (avec ou
   sans panier) ; avec l'adhésion dans le panier, elle passe.

### Test 6 — bouton « retirer » (C16)
1. Deux articles au panier ; dépublier ou supprimer le tarif du premier dans l'admin.
2. Recharger `/panier/` : un seul article affiché ; « retirer » enlève bien celui-là.

### Test 7 — événement gratuit + payant (C27)
1. Admin : un événement avec un produit « Réservation gratuite » et un produit billet à 10 €.
2. Front : prendre un billet de chaque, aller chez Stripe, revenir SANS payer.
3. Attendu : aucun mail, aucun billet dans « Mes réservations ».
4. Recommencer et payer : un seul mail, avec les deux billets actifs.

### Test 8 — skin Faire Festival (C25)
1. Admin : passer le thème du site en « Faire Festival ».
2. Ajouter un billet au panier : le bouton « Panier » du menu affiche le compteur à 1 et mène
   à `/panier/`.

### Test 10 — stocks (C19)
1. Tarif billet avec un stock de 2, 1 billet déjà vendu : en demander 2 est refusé, 1 passe.
2. Tarif d'adhésion avec un stock de 1, déjà pris : refusé (avec et sans panier).
3. Deux navigateurs : le premier va jusqu'à la page Stripe sur le dernier billet sans payer ;
   le second est refusé pendant 30 minutes, puis la place se libère.
4. Page Stripe laissée ouverte plus de 30 minutes : elle a expiré.
5. Repas limité : événement à jauge 100, deux produits exclusifs « avec repas » (stock 25)
   et « sans repas » (sans stock). Au plus 25 repas, au plus 100 personnes. Ne pas créer un
   produit « Repas » séparé : chaque personne occuperait deux places de la jauge.

### Test 11 — code promo (C26) et remise au panier
1. Événement avec deux produits billet ayant chacun un code promo : un seul champ « Code
   promo » s'affiche ; le code tapé est appliqué.
2. Au panier : le billet montre le prix barré, le prix remisé et le nom du code ; le total
   est celui que Stripe facture.

### Test 9 — événement terminé (C20)
1. Un événement fini hier : un billet laissé dans le panier est refusé au paiement.
2. Un festival commencé il y a 3 jours et fini demain : les billets restent en vente.
3. Un événement sans date de fin commencé il y a 2 h : encore en vente ; commencé il y a
   2 jours : refusé.
4. Un événement non publié, ouvert par son lien direct : réservable.

### Vérifications automatiques / Automated checks
- `make test` (pytest, 1609 passed, 9 xfailed au 2026-09-22), `make test-stripe`, `make e2e`,
  `make e2e-stripe` (`stripe listen` dans byobu).
- `make coverage FICHIERS="BaseBillet/services_panier.py,BaseBillet/services_commande.py"`.
- Avant les E2E du panier : `docker exec lespass_django poetry run python manage.py demo_data_v2 --e2e-only`.
