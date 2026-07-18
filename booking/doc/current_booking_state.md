## Booking

### État actuel

Actuellement l'application booking contient tout le nécessaire pour créer des `Resource` et de les réserver, gratuitement ou en payant, avec des prix libres et des adhésions requises.
L'application est également intégré avec le panier (sauf une petite partie, voir la partie "Manque" plus bas). Le remboursement fonctionne aussi.

### Manque

Pour l'instant les `Resource` avec `slot_type == Resource.DAY` ne sont pas entièrement pris en charge. 
Le template pour les afficher existe, mais pas les templates de réservation, ni la logique dans la vue, ni dans le panier.
La majorité des endroits qui demandent des modifications sont marqué des commentaires : `# TODO-FOR-DAY-BOOKING`

Il faut ajouter le fonctionnement pour la réservation (template et vue) et pour le panier.
Pour la réservation, il y a le comportement POST sans panier à faire. Globalement, il faut ajouter les vérifications et le calcul de créneaux par jour et non pas par heure.

