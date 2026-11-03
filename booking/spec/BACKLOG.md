# Backlog

- Docs : supprimer `booking/doc/` une fois son contenu spécifié ou abandonné.
- Formulaire de réservation : afficher distinctement les trois sortes de tarif : fixe (par heure), à prix libre avec son minimum (par heure), et gratuit (0 €).
- Pages de réservation : vérifier quelle image est affichée, celle de la ressource ou celle de son produit de ressource.
- Formulaire de réservation : retirer la gestion du stock épuisé des tarifs, que les tarifs de ressource ne déclenchent jamais.
- Formulaire de réservation : retirer la branche « Log in to access this rate. », qui ne s'affiche jamais puisque le formulaire exige d'être connecté.
- Formulaire de réservation : retirer la branche non HTMX de `book` (`booking/views/book.html` manquant) et son commentaire de repli périmé.
- Panier : afficher la ligne d'une ressource par créneau, comme le formulaire de réservation.
