# Pass multi-événements / Multi-event pass

**Date :** 2026-11-20
**Migration :** Oui — `BaseBillet/migrations/0241_pass_multi_evenements.py` et `0243_proxy_pass_product.py` (proxy, aucune table) et `0244_pass_au_pluriel_invariable.py` (nom affiché, aucune requête SQL)
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
la limite des places et du stock de pass.
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
| `BaseBillet/migrations/0244_pass_au_pluriel_invariable.py` | Nom du modèle au pluriel « Pass » (aucune requête SQL) |
| `BaseBillet/services_pass.py` | Nouveau : `deplier_le_pass(produit, quantite)` |
| `BaseBillet/validators.py` | `TicketCreator(identifiants_des_passes=...)` : prix de la ligne du pass, identifiant sur chaque billet, refus d'un pass sans identifiants ou hors de ses événements, pas de code promo sur un pass |
| `BaseBillet/validators.py` (`ReservationValidator.validate`) | Refus d'un pass en réservation directe (et donc en API v2) : « s'achète par le panier » |
| `BaseBillet/services_panier.py` | Un pass au panier occupe une place sur chacun de ses événements (`_item_billet_couvre_l_evenement`) ; `add_ticket` vérifie l'événement, la disponibilité, les limites de tous les événements du pass, le stock commun et refuse un code promo ; le total compte la somme des prix par événement |
| `BaseBillet/services_commande.py` | `materialiser` déplie chaque pass en un item par événement, avec les mêmes identifiants, et le passe dans son propre `TicketCreator` |
| `BaseBillet/context_processors.py`, `BaseBillet/templates/htmx/components/panier_item.html` | Le panier affiche le nom du pass, son prix total et la liste de ses événements |
| `Administration/admin/products.py` | Nouvelle page `PassProductAdmin` (pose `est_un_pass=True`, inline `EvenementDuPassInline`, `save_related` → `synchroniser_le_produit_pass` : prix du tarif = somme, produit rattaché aux événements du pass et retiré des autres, messages) ; formulaire sans les champs réservés aux adhésions (descriptions, texte du bouton d'adhésion, mentions légales) ; `PassPriceInline` : tarif unique (`max_num = 1`, une ligne vierge tant qu'il n'y a pas de tarif), affiché après les événements du pass, prix en lecture seule, sans prix libre ni ordre, adhésion obligatoire possible (un tarif adhérent = un second pass), libellés « Nombre maximum de pass » / « Maximum de pass par personne », récompense au scan précisée « à chaque billet scanné » ; `PassProductForm.clean` : un seul tarif et au moins un non supprimé, pas de tarif ajouté à un pass gratuit (le sien est créé tout seul), au moins 2 événements avec leur prix. `TicketProductAdmin` / `TicketProductForm` inchangés par rapport à avant le chantier |
| `Administration/admin/products.py` (tarifs) | `compter_les_tarifs_envoyes` et `verifier_qu_il_reste_un_tarif`, utilisées par `PassProductForm` et `TicketProductForm` : refus d'enregistrer un produit billet ou un pass dont le dernier tarif est coché « supprimer » (la règle de `ProductAdminCustomForm` compte les tarifs affichés, même supprimés). Sauf un produit gratuit à sa création (tarif à 0 € créé par signal). Message commun existant « Merci d'ajouter au moins un tarif à ce produit. » |
| `BaseBillet/models.py` (`Price.stock_restant`) | Nombre de places libres du tarif (`None` = illimité) ; `out_of_stock` s'appuie dessus, même résultat qu'avant |
| `BaseBillet/services_panier.py` (`message_de_stock_insuffisant`) | Le refus d'ajout au panier pour stock insuffisant donne le nom du tarif et ce qu'il reste (« Il ne reste que 3 billets au tarif « Plein tarif ». », en pass pour un pass), ou dit que le tarif est épuisé, ou que les dernières places sont déjà dans le panier. Remplace « Ce tarif est épuisé. » pour les billets |
| `Administration/admin/dashboard.py` | Entrée « Pass » dans le menu Billetterie, rangée dans « Configurer » avec sa description |
| `Administration/management/commands/demo_data_v2.py` | Fixture E2E « E2E Test — Pass deux événements » (la page « Pass » a un objet à ouvrir) |
| `Administration/admin/products.py` (`EvenementDuPassInline.get_extra`) | Lignes d'événement vierges jusqu'à 2 : un nouveau pass en propose 2 |
| `Administration/templates/admin/product/evenements_du_pass_before.html` | Nouveau : envoi des événements déjà choisis à chaque recherche (`deja_choisis`), libellé « Ajouter un événement au pass » |
| `Administration/admin_tenant.py` | `evenements_affiches_par_defaut` (non archivés, à venir ou en cours) : utilisée par les filtres par défaut de la liste des événements et par `EventAdmin.get_search_results` pour le choix d'un événement du pass, qui retire aussi les événements déjà choisis (`deja_choisis`) |
| `Administration/admin/prices.py` | Le choix du produit d'un code promo exclut les passes |
| `BaseBillet/models.py` (annulation) | `cancel_and_refund_ticket` et `cancel_and_refund_resa` annulent tout le pass ; l'annulation d'origine devient `_annuler_et_rembourser_un_seul_billet` / `_annuler_et_rembourser_la_reservation_seule` ; `verifier_qu_aucun_billet_du_pass_n_est_scanne` refuse avant tout remboursement ; `Reservation.contient_des_billets_de_pass()` |
| `pages/templates/pages/{classic,V2}/vues/compte/reservations.html`, `.../partials/ticket_accordion.html` | La confirmation d'annulation prévient que tout le pass sera annulé |
| `BaseBillet/models.py` (`pass_est_vendable`) | Paramètre `vente_au_comptoir` : au comptoir, refus seulement si un événement du pass est terminé (au lieu de commencé) |
| `laboutik/views.py` | `_deplier_l_article_pass` vérifie aussi le stock de pass (message clair au caissier) ; `_extraire_articles_du_panier` déplie un pass (`_deplier_l_article_pass`) en un article par événement au prix de sa ligne ; `_creer_billets_depuis_panier` pose `pass_vendu` et le prix de la ligne sur chaque billet, et rattache chaque ligne de vente à sa réservation (liste de lignes par produit, au même prix unitaire) |
| `tests/pytest/test_pass_multi_evenements.py` | Nouveau : 63 tests |
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
- Admin : passer un pass existant de payant à gratuit lui ajoute un tarif à 0 € (signal du
  produit gratuit) en plus du sien.
- Le refus du dernier tarif supprimé ne vaut que pour les produits billets et les passes : la même
  faille existe pour les produits de caisse, les ressources et les fûts (règle commune de
  `ProductAdminCustomForm`), à voir avec le mainteneur.
- API v2 : hors périmètre.

---

## Comment tester (a la main) / Manual test

### Test 1 — créer un pass dans l'admin
1. Créer deux événements à venir (samedi, dimanche), chacun avec un billet « jour seul ».
2. Admin > Billetterie > Configurer > Pass : nouveau pass « Pass week-end », type « Billet »,
   un tarif « Pass 2 jours » (le prix ne se saisit pas). La page n'a ni descriptions, ni texte du
   bouton d'adhésion, ni mentions légales, ni prix libre. Les événements du pass sont avant le
   tarif, et une fois le tarif créé, le lien pour en ajouter un second disparaît.
3. La page propose déjà 2 lignes d'événement vierges et 1 ligne de tarif. Y mettre samedi
   (12 €) et dimanche (13 €), enregistrer une seule fois (pour un pass gratuit, laisser la ligne
   de tarif vide : son tarif à 0 € est créé tout seul). Le pass n'apparaît pas dans « Produits billetterie », et la fiche d'un
   produit billet n'a plus rien du pass.
   Le choix d'un événement ne propose que les événements de la liste admin par défaut
   (ni archivés, ni passés), et plus ceux déjà choisis dans une autre ligne. Cocher
   « supprimer » sur une ligne rend son événement de nouveau proposé.
4. Messages attendus : « Prix du pass : 25,00 € », « Le pass est maintenant proposé sur … » ×2.
5. Le tarif affiche 25 €. Sur la fiche de chaque événement, le produit pass est dans « Produits ».
6. Retirer le dimanche du pass, enregistrer : message « Le pass n'est plus proposé sur … ».
7. Ajouter un 2e tarif, ajouter un tarif à un pass gratuit, supprimer le tarif (corbeille), ou ne
   garder qu'un seul événement (ou un événement sans prix) : enregistrement refusé avec un message.
   S'il manque à la fois des événements et un tarif, le message sur les événements vient d'abord.
8. Code promo : le produit pass n'est pas proposé dans la liste des produits.
8bis. Sur un produit billet (« Produits billetterie »), supprimer son seul tarif à la corbeille puis
   enregistrer : refusé avec « Merci d'ajouter au moins un tarif à ce produit. ».
9. Mettre une adhésion dans « Abonnements requis » du tarif : sur le site, le pass est refusé au
   panier sans cette adhésion, et accepté si elle est dans le même panier.

### Test 2 — tests automatiques
- `docker exec lespass_django poetry run pytest tests/pytest/test_pass_multi_evenements.py -q`
- `docker exec lespass_django poetry run pytest tests/pytest/test_pass_multi_evenements_caisse.py -q`
- Attendu : 63 passed et 7 passed.

### Test 3 — achat par le panier
1. Partir du pass du Test 1 (samedi + dimanche).
2. Se connecter sur le site, ouvrir la page du samedi : le tarif « Pass 2 jours » apparaît.
3. Choisir 1 pass, cliquer « Ajouter au panier ». Le panier affiche le nom du pass, 25 €, et les
   deux événements.
4. Payer (carte de test Stripe). Vérifier : deux mails (un par événement), et dans l'admin deux
   réservations dans la même commande.
5. Refaire avec « Payer maintenant » : message « Le pass … s'achète par le panier ».
6. Mettre la jauge du dimanche à 0, puis tenter d'ajouter le pass depuis la page du samedi : refusé.
7. Mettre « Nombre maximum de pass » à 2, puis tenter d'en ajouter 3 au panier : « Il ne reste que
   2 pass au tarif « Pass 2 jours ». ». Même chose pour un billet normal (« … billets au tarif … »).

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
