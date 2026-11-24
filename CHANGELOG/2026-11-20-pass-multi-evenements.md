# Pass multi-événements / Multi-event pass

**Date :** 2026-11-20
**Migration :** Oui — `BaseBillet/migrations/0241_pass_multi_evenements.py` et `0243_proxy_pass_product.py` (proxy, aucune table)
(`docker exec lespass_django poetry run python manage.py migrate_schemas --executor=standard`)

## Resume / Summary
**Quoi / What :** Un produit billet peut devenir un « pass » qui couvre plusieurs événements.
Chaque événement du pass a son prix dans le pass ; le prix du pass est la somme. Acheter un pass
fabrique un billet par événement, au prix de sa ligne, et tous ces billets portent le même
identifiant de pass. Cette livraison pose le modèle, le stock et la création des billets
(`TicketCreator`) et l'achat par le panier. La réservation directe refuse un pass et renvoie
vers le panier. L'admin des produits billets permet de créer un pass. Le pass est indivisible :
annuler un de ses billets, ou une réservation qui en contient, annule et rembourse tous les billets
du pass, chacun sur sa réservation. La caisse LaBoutik vend aussi le pass : un billet, une
réservation et une ligne de vente par événement. Au comptoir, le pass se vend encore après le
début du premier événement (vente à l'entrée), tant qu'aucun de ses événements n'est terminé, dans
la limite des places et du stock de passes.
/ A ticket product can become a "pass" covering several events, each with its own price; the
pass price is the sum. Buying a pass creates one ticket per event, all sharing one pass id. This
delivery adds the model, stock, ticket creation and cart purchase; direct booking refuses a pass
and points to the cart. The ticket product admin can create a pass. A pass is indivisible:
cancelling one ticket (or a reservation holding one) cancels and refunds the whole pass. The
LaBoutik register sells it too: one ticket, reservation and sale line per event. At the register
the pass still sells after the first event started, while no pass event is over (seats and pass
stock still apply).

**Pourquoi / Why :** Vendre un pass moins cher pour un événement sur plusieurs jours, tout en
gardant la vente de chaque jour à part. Les billets restent de vrais billets par événement : le
scan, la jauge, les PDF, les mails et les bilans fonctionnent sans changement.
/ Sell a cheaper multi-day pass while each day stays bookable alone. Tickets stay real per-event
tickets, so scan, gauge, PDF, mails and reports are unchanged.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/models.py` | `Product.est_un_pass`, `lignes_du_pass()`, `prix_total_du_pass()`, `pass_est_vendable()` ; modèle `EvenementDuPass` ; `Ticket.pass_vendu` ; `Price.out_of_stock()` compte des passes pour un tarif pass |
| `BaseBillet/migrations/0241_pass_multi_evenements.py` | Migration des trois ajouts |
| `BaseBillet/models.py` (proxy) | Proxy `PassProduct` (manager `est_un_pass=True`) ajouté à `PROXYS_PRODUCT` pour les signaux ; le manager de `TicketProduct` exclut les passes |
| `BaseBillet/migrations/0243_proxy_pass_product.py` | Proxy `PassProduct` (aucune table) |
| `BaseBillet/services_pass.py` | Nouveau : `deplier_le_pass(produit, quantite)` |
| `BaseBillet/validators.py` | `TicketCreator(identifiants_des_passes=...)` : prix de la ligne du pass, identifiant sur chaque billet, refus d'un pass sans identifiants ou hors de ses événements, pas de code promo sur un pass |
| `BaseBillet/validators.py` (`ReservationValidator.validate`) | Refus d'un pass en réservation directe (et donc en API v2) : « s'achète par le panier » |
| `BaseBillet/services_panier.py` | Un pass au panier occupe une place sur chacun de ses événements (`_item_billet_couvre_l_evenement`) ; `add_ticket` vérifie l'événement, la disponibilité, les limites de tous les événements du pass, le stock commun et refuse un code promo ; le total compte la somme des prix par événement |
| `BaseBillet/services_commande.py` | `materialiser` déplie chaque pass en un item par événement, avec les mêmes identifiants, et le passe dans son propre `TicketCreator` |
| `BaseBillet/context_processors.py`, `BaseBillet/templates/htmx/components/panier_item.html` | Le panier affiche le nom du pass, son prix total et la liste de ses événements |
| `Administration/admin/products.py` | Nouvelle page `PassProductAdmin` (pose `est_un_pass=True`, inline `EvenementDuPassInline`, `save_related` → `synchroniser_le_produit_pass` : prix du tarif = somme, produit rattaché aux événements du pass et retiré des autres, messages) ; `PassProductForm.clean` : un seul tarif, pas de prix libre, au moins 2 événements avec leur prix. `TicketProductAdmin` / `TicketProductForm` inchangés par rapport à avant le chantier |
| `Administration/admin/dashboard.py` | Entrée « Passes » dans le menu Billetterie |
| `Administration/management/commands/demo_data_v2.py` | Fixture E2E « E2E Test — Pass deux événements » (la page « Pass » a un objet à ouvrir) |
| `Administration/templates/admin/product/evenements_du_pass_before.html` | Nouveau : envoi des événements déjà choisis à chaque recherche (`deja_choisis`), libellé « Ajouter un événement au pass » |
| `Administration/admin_tenant.py` | `evenements_affiches_par_defaut` (non archivés, à venir ou en cours) : utilisée par les filtres par défaut de la liste des événements et par `EventAdmin.get_search_results` pour le choix d'un événement du pass, qui retire aussi les événements déjà choisis (`deja_choisis`) |
| `Administration/admin/prices.py` | Le choix du produit d'un code promo exclut les passes |
| `BaseBillet/models.py` (annulation) | `cancel_and_refund_ticket` et `cancel_and_refund_resa` annulent tout le pass ; l'annulation d'origine devient `_annuler_et_rembourser_un_seul_billet` / `_annuler_et_rembourser_la_reservation_seule` ; `verifier_qu_aucun_billet_du_pass_n_est_scanne` refuse avant tout remboursement ; `Reservation.contient_des_billets_de_pass()` |
| `pages/templates/pages/{classic,V2}/vues/compte/reservations.html`, `.../partials/ticket_accordion.html` | La confirmation d'annulation prévient que tout le pass sera annulé |
| `BaseBillet/models.py` (`pass_est_vendable`) | Paramètre `vente_au_comptoir` : au comptoir, refus seulement si un événement du pass est terminé (au lieu de commencé) |
| `laboutik/views.py` | `_deplier_l_article_pass` vérifie aussi le stock de passes (message clair au caissier) ; `_extraire_articles_du_panier` déplie un pass (`_deplier_l_article_pass`) en un article par événement au prix de sa ligne ; `_creer_billets_depuis_panier` pose `pass_vendu` et le prix de la ligne sur chaque billet, et rattache chaque ligne de vente à sa réservation (liste de lignes par produit, au même prix unitaire) |
| `tests/pytest/test_pass_multi_evenements.py` | Nouveau : 45 tests |
| `tests/pytest/test_pass_multi_evenements_caisse.py` | Nouveau : 7 tests (schéma `test_pass_caisse`) |

### Pas encore fait / Not done yet
- Formulaire de l'événement : masquer « Payer maintenant » quand un pass est choisi (aujourd'hui,
  le serveur refuse avec un message). Un visiteur non connecté, ou un événement avec
  `panier_desactive`, ne peut donc pas acheter de pass.
- Chevauchement d'horaires (`allow_concurrent_bookings=False`) : vérifié seulement sur l'événement
  où le pass est ajouté, pas sur les autres événements du pass.
- Annulation : un seul mail d'annulation part (celui du billet ou de la réservation cliqué),
  pas un par événement du pass.
- Annulation : si un remboursement Stripe réussit puis le suivant échoue, la base revient en
  arrière mais le premier remboursement Stripe reste fait (même risque qu'aujourd'hui pour une
  réservation à plusieurs lignes).
- Admin : le prix du tarif reste modifiable dans le formulaire, mais il est remplacé par la somme
  à l'enregistrement (message affiché).
- API v2 : hors périmètre.

---

## Comment tester (a la main) / Manual test

### Test 1 — créer un pass dans l'admin
1. Créer deux événements à venir (samedi, dimanche), chacun avec un billet « jour seul ».
2. Admin > Billetterie > Passes : nouveau pass « Pass week-end », type « Billet »,
   un tarif « Pass 2 jours » (prix quelconque).
3. Dans « Événements du pass », ajouter samedi (12 €) et dimanche (13 €), enregistrer une
   seule fois. Le pass n'apparaît pas dans « Produits billetterie », et la fiche d'un
   produit billet n'a plus rien du pass.
   Le choix d'un événement ne propose que les événements de la liste admin par défaut
   (ni archivés, ni passés), et plus ceux déjà choisis dans une autre ligne. Cocher
   « supprimer » sur une ligne rend son événement de nouveau proposé.
4. Messages attendus : « Prix du pass : 25,00 € », « Le pass est maintenant proposé sur … » ×2.
5. Le tarif affiche 25 €. Sur la fiche de chaque événement, le produit pass est dans « Produits ».
6. Retirer le dimanche du pass, enregistrer : message « Le pass n'est plus proposé sur … ».
7. Ajouter un 2e tarif, cocher « prix libre », ou ne garder qu'un seul événement (ou un événement
   sans prix) : enregistrement refusé avec un message.
8. Code promo : le produit pass n'est pas proposé dans la liste des produits.

### Test 2 — tests automatiques
- `docker exec lespass_django poetry run pytest tests/pytest/test_pass_multi_evenements.py -q`
- `docker exec lespass_django poetry run pytest tests/pytest/test_pass_multi_evenements_caisse.py -q`
- Attendu : 45 passed et 7 passed.

### Test 3 — achat par le panier
1. Partir du pass du Test 1 (samedi + dimanche).
2. Se connecter sur le site, ouvrir la page du samedi : le tarif « Pass 2 jours » apparaît.
3. Choisir 1 pass, cliquer « Ajouter au panier ». Le panier affiche le nom du pass, 25 €, et les
   deux événements.
4. Payer (carte de test Stripe). Vérifier : deux mails (un par événement), et dans l'admin deux
   réservations dans la même commande.
5. Refaire avec « Payer maintenant » : message « Le pass … s'achète par le panier ».
6. Mettre la jauge du dimanche à 0, puis tenter d'ajouter le pass depuis la page du samedi : refusé.

### Test 4 — annulation indivisible
1. Avec le pass acheté au Test 3, aller dans « Mon compte > Mes réservations ».
2. Cliquer « Annuler ce billet » sur le billet du dimanche : la confirmation dit que tout le pass
   sera annulé. Confirmer.
3. Les deux billets (samedi et dimanche) sont annulés, et Stripe rembourse 25 € (12 + 13).
4. Refaire un achat, scanner le billet du samedi, puis annuler le billet du dimanche : refusé
   (« Un billet de ce pass a déjà été scanné »), rien n'est annulé.
5. Admin : annuler la réservation du samedi avec remboursement : la réservation du dimanche du
   même pass est annulée aussi.

### Test 5 — vente en caisse
1. Ouvrir la caisse sur un point de vente « Billetterie ». Le pass apparaît dans les tuiles du
   samedi et du dimanche, à 25 €.
2. Vendre 1 pass depuis la tuile du samedi, en espèces, avec un email client.
3. Admin : deux réservations (samedi, dimanche), chacune avec un billet. La vente a deux lignes,
   12 € et 13 €. Deux mails de billets partent.
4. Annuler le billet du samedi depuis l'admin (remboursement espèces) : le dimanche est annulé
   aussi, avec un avoir sur chaque ligne.
5. Le samedi commencé (pas terminé), vendre un pass en caisse : accepté. En ligne au même moment,
   l'ajout du pass au panier est refusé.
6. Stock du tarif pass à 1, un pass déjà vendu : la caisse affiche « Plus de pass … disponible ».

### Verifs DB
- Après un achat : `Ticket.objects.filter(pass_vendu=<uuid>)` renvoie un billet par événement du pass.
