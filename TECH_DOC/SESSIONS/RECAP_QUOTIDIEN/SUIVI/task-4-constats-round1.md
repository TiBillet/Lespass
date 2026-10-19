# Tâche 4 — constats de la relecture, round 1 (à corriger)

## Importants
1. Le signe de l'argent rendu n'est vérifié par aucun test (tests/pytest/test_recap_quotidien.py vers 967, 974, 982 : `"6,00" in ligne` passe aussi pour « −6,00 € »). La mutation `euros_a_la_francaise(ligne_article.total_ttc)` (sans le moins, recap_quotidien.py ~435) laisse tout vert. Corriger : affirmer la fin exacte (`ligne.endswith("— 6,00 €")` ou équivalent selon le format réel) ET vérifier l'absence de signe moins (« − » U+2212 et « - »). Jouer la mutation.
2. Montants crowds toujours en « € » (recap_quotidien.py ~372 et ~384) alors que `Initiative.currency` peut valoir « heures », une monnaie locale… Décision : afficher dans la devise du projet avec `montant_a_la_francaise_dans_l_unite` (comptabilite/presentation.py ~148 — vérifie sa signature) ; « € » ou vide → euros comme aujourd'hui. Test avec `currency="heures"`.
3. `_rubrique_annulations` (~657-691) duplique la fin de `_construire_la_rubrique` (tri, coupe à 10, nombre_de_lignes_cachees, dict à 8 clés). Extraire `_dict_de_la_rubrique(cle, titre, est_un_stock, nombre, nombre_de_nouveaux, lignes, lien)` appelée par les deux.

## Conformité (spec §3.2 : « chaque ligne montre son statut »)
4. La ligne de budget n'affiche pas son état (`BudgetItem.state`), la contribution n'affiche pas son statut de paiement (`get_payment_status_display()`). Les ajouter.
5. Lien des `annulations` (~690) : décision du coordinateur = on garde la liste des réservations ; ajouter un commentaire FALC qui le dit (la rubrique mêle réservations, réservations de ressources et adhésions).

## Mineurs
6. Tri des annulations non testé : test avec une réservation annulée à 9h10 et une adhésion annulée à 15h10 → l'adhésion en premier. Mutation : retirer le tri.
7. Départage par `str(pk)` faux pour les pk entières (« 9 » avant « 10 ») : retirer ce départage, ou le remplacer par un départage stable correct, et corriger le commentaire.
8. FALC ~663-673 : remplacer les trois compréhensions à noms d'une lettre par une seule boucle `for objet, fonction_de_ligne, champ in lignes_montrees:` qui remplit un dict `{champ: [objets]}`.
9. Branche morte ~423 : `ProductSold.product` n'est jamais nul → `return produit_vendu.product.name or _("(sans nom)")`.
10. Couverture : tester les branches adhésion et booking de `_nom_de_l_objet_rembourse`, et faire vérifier par `test_annulations_reunit_reservations_bookings_et_adhesions` le nom de la ressource et celui du produit d'adhésion dans les lignes.
