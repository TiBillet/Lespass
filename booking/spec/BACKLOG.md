# Backlog

- Docs : supprimer `booking/doc/` une fois son contenu spécifié ou abandonné.
- Pages de réservation : vérifier quelle image est affichée, celle de la ressource ou celle de son produit de ressource.
- Formulaire de réservation : retirer la gestion du stock épuisé des tarifs, que les tarifs de ressource ne déclenchent jamais.
- Formulaire de réservation : retirer la branche « Log in to access this rate. », qui ne s'affiche jamais puisque le formulaire exige d'être connecté.
- Formulaire de réservation : retirer la branche non HTMX de `book` (`booking/views/book.html` manquant) et son commentaire de repli périmé.
- Panier : rendre la ligne d'une ressource moins verbeuse et par créneau, comme le formulaire de réservation (par exemple « Ressource · 3 créneaux de 1h · 5 € / créneau ») : aujourd'hui la durée apparaît trois fois, le calcul est écrit en entier (« 3h * 5,00€/h = 15.00€ »), les formats de montant diffèrent, et « slot » n'est ni traduit ni accordé.
- Liste des ressources : le prix de la carte d'une ressource (« 10 € », `libelle_prix` posé par `BookingViewSet.list`) est ambigu, sans unité (par heure, par créneau ?) ni sorte de tarif.
- Formulaire de réservation : rendre plus visibles les contours gris trop pâles, surtout les boutons radio des tarifs, qu'on distingue à peine du fond.
- Réservation : afficher la durée des créneaux de façon plus lisible (en heures et minutes), et pas seulement en minutes.
- Réservation : un délai minimum avant le début d'un créneau, réglable par ressource dans l'admin, en deçà duquel le créneau ne peut plus être réservé (demande d'un utilisateur ; aujourd'hui seul un créneau commencé est refusé). À trancher : unité, valeur par défaut, affichage du créneau trop proche dans le calendrier, créneau payé trop tard depuis le panier.
- Admin : permettre aux administrateurs de réserver une ressource, y compris totalement en dehors des créneaux habituels (par exemple pour bloquer une ressource en travaux ; le moteur gère normalement déjà ce cas). S'inspirer de la réservation par l'admin de la billetterie, selon Jonas.
- Admin : créer par défaut un calendrier de fermeture vide (`Calendar`) et des créneaux hebdomadaires vides (`WeeklyOpening`), pour qu'une ressource puisse être créée dans l'admin sans les créer d'abord (`Resource.calendar` et `Resource.weekly_opening` sont obligatoires).
