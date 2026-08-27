## Remboursement

### État actuel

Le système de remboursement a été réécrit pour être au même endroit et ne pas répeter de code. 
Avant les remboursements étaient créé depuis Basebillet.models.Reservation.cancel_and_refund_resa et depuis Basebillet.models.Reservation.cancel_and_refund_ticket.
En ajoutant l'application de booking, il y a un troisième lieu d'où les remboursements allaient pouvoir se faire : Booking.models.Booking.cancel_and_refund_booking.

Pour avoir un seul endroit avec le code qui gère le remboursement, j'ai créé le fichier `utils.py` dans `PaiementStripe`.
Ce fichier contient une seule fonction `partial_refund_payment` qui est appelé par les trois endroits nommés précédemment pour créer un remboursement.
Les commentaires expliquent toutes les spécificités de la fonction, comment préciser quelle quantité rembourser sur quelle ligne articles par exemple.


### À tester 

1. Il faut tester si la fonction partial_refund_payment fonctionne bien en lui passant des paramètres différent, en vérifiant le status des 
   `LigneArticle` qu'elle traite, et le status des `Paiement_Stripe`.

2. Il faut tester les 3 méthodes sus-nommé, et vérifier le status de leur `LigneArticle` est correcte :
    - `cancel_and_refund_resa`
    - `cancel_and_refund_ticket`
    - `cancel_and_refund_booking`

3. Créer des tests playwright pour tester le remboursement depuis le front pour des réservations et booking gratuit, payant. 
   Fait en une seule commande, plusieurs, etc. (voir "panier.md"). Fait avec le paiement direct (sans panier) ou avec le panier (voir "panier.md"). 
   Vérifier les états des `LigneArticle`, des `Booking`, des `Reservation`, des `Ticket` et des `Paiement_Stripe`

4. Tester si des paiements créés avant cette modification peuvent bien être remboursé.