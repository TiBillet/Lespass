# TiBillet — Module de réservation de ressources partagées

par Joris Rehm, contact : joris@jirm.eu

Document de travail pour recueillir l'avis des structures intéressées.


## But

TiBillet devrait bientôt permettre de gérer la **réservation de ressources partagées** au
sein de votre lieu : salles de réunion, salles de répétitions musicale, postes de
coworking, machines de FabLab, matériel mis à disposition...


## Ce que vous pouvez configurer

En tant que bénévole gestionnaire, vous définissez :

- **Vos ressources** : donnez un nom, une description et une photo à chaque
  ressource. Vous pouvez les regrouper pour l'affichage (par exemple, "Salles de
  répétition" qui regroupe "Salle Verte", "Salle Rouge" et "Salle Rose").
  Où salle de coworking de 12 places, dans ce cas 12 adhérents peuvent se placer
  sur chaque crénaux.

- **Les horaires d'ouverture** : vous définissez un planning hebdomadaire par
  ressource (par exemple : lundi au vendredi, de 9h à 18h par tranches d'une heure).
  Ce planning est réutilisable entre plusieurs ressources similaires.

- **Le planning annuel** : indiquez les jours fermés ou toute période
  de fermeture. En dehors de ces périodes, la ressource est considérée comme
  disponible. On peut définir un seul planning pour toutes les ressources ou
  plusieurs selon les cas.

- **Période max de réservation** : limitez combien de jours à l'avance vos
  adhérents peuvent réserver (par exemple, pas plus de 28 jours).

- **Le délai d'annulation** : fixez jusqu'à quand une réservation peut être annulée
  (par exemple, jusqu'à 24h avant le début).

- **Le tarif** : gratuit, payant, ou réservé à un certain type d'adhésion. TiBillet
  utilise son système de paiement habituel (carte bancaire, wallet, cashless) et
  son système de définition de tarif.



## Ce que vivent vos adhérents

Vos adhérents accèdent à une **page de réservation**, intégrable sur votre
site web existant. Ils peuvent :

1. Parcourir vos ressources, filtrer par catégorie.
2. Consulter les créneaux disponibles sur un calendrier.
3. Choisir un créneau et le nombre de tranches souhaitées (ex. 2h = 2 tranches de
   1h).
4. Ajouter d'autres réservations au même panier si besoin.
5. Confirmer et payer.
6. Annuler leur réservation en autonomie, dans le délai que vous avez fixé.

La réservation est **directe** - pas de validation manuelle de votre part.


## Ce que vous gardez sous contrôle

- Vous visualisez toutes les réservations en cours dans votre interface
  d'administration.
- Vous pouvez annuler une réservation à la place d'un adhérent si besoin.
  Dans ce cas le remboursement est à faire manuellement.
- Vous pouvez créer vous-même une réservation exceptionnelle, en dehors des
  créneaux habituels (ex. bloquer une salle pour un événement ponctuel).
- En cas de changement de période de fermeture, c'est à vous de gérer les
  potentielles réservations à annuler.


## Ce qui n'est pas prévu dans cette première version

Pour rester simple et fiable, quelques limitations :

- Pas de réservations récurrentes automatique (ex. "tous les lundis à 10h").
- Pas de liste d'attente quand un créneau est complet.
- Pas de partage de ressources entre plusieurs associations du réseau TiBillet.
- Pas de gestion automatique d'un changement d'ouverture (par exemple : ouvertures
  différentes pendant les vacances)

