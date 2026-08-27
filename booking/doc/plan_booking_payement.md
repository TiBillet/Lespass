# Intégration booking × BaseBillet - Plan v0.2 : paiement


## 1. Domaine métier

### État des lieux BaseBillet

BaseBillet dispose d'un modèle `Product` qui représente tout
ce qui peut être vendu ou réservé sur la plateforme. Un
`Product` est typé par son champ `categorie_article` — billet
d'événement, adhésion, rechargement cashless, article de
caisse, etc. À chaque `Product` sont associés un ou plusieurs
`Price`, qui portent le montant, les conditions d'accès
(`adhesion_obligatoire`), les règles d'abonnement récurrent
et le délai de remboursement (`refund_deadline`).
Ce système est complet et utilisé en production pour tous les
modules existants.

BaseBillet dispose également d'un modèle `Commande` qui joue
le rôle de panier d'achat : il regroupe en une seule entité
plusieurs achats de `Reservation` ou `Membership`.

Une `Commande` passe par trois états principaux :

1. `DRAFT` — panier en cours de constitution
2. `PENDING` — paiement en attente de confirmation
3. `PAID` — paiement confirmé par Stripe

Elle peut aussi être `EXPIRED` si la session Stripe expire
sans paiement.


### État des lieux booking

Le but de ce module est de supporter la réservation dans des
lieux où il existe un contrat social basé sur des créneaux
horaires que les usagers se partagent. Les usagers s'engagent
à effectivement utiliser ce qu'ils réservent. Le lieu s'engage
à avoir la ressource effectivement disponible.

L'app booking dispose d'un modèle `Resource` qui représente
une entité réservable. Pour le moment, la réservation ne
dépend que de la logique interne de disponibilité. Les
`Resource` ont une `capacity`, le nombre d'utilisations
simultanées maximum.

Une `Resource` est associée à un `WeeklyOpening` qui définit
les créneaux de réservation pour une semaine. Cela permet de
définir des créneaux de durée libre à n'importe quel moment
de la semaine.

Une `Resource` est associée à un `Calendar` qui définit des
jours de fermeture et par conséquent les jours d'ouverture.

La combinaison des deux permet de calculer à la volée les
créneaux disponibles. La prise en compte des réservations
(`Booking`) permet de calculer la capacité effective à partir
de la `capacity` initiale.

Une réservation (`Booking`) est définie par :

- une date et une heure de début
- un nombre de créneaux réservés (`slot_count`), tous de même
  durée (`slot_duration_minutes`)
- et donc une date et une heure de fin
- pour une `Resource`
- et un utilisateur

Lorsqu'une réservation est créée par un utilisateur normal,
la logique garantit que les créneaux réservés existaient au
moment de la réservation et étaient disponibles.

Lorsqu'une réservation est créée par un administrateur,
elle est totalement libre. La logique est capable de
gérer ce cas.

Politique d'annulation : l'annulation n'est possible que
jusqu'à la durée `cancellation_deadline_hours` avant le
début de la réservation. Le but est de responsabiliser
les usagers et de simplifier la gestion du lieu. Une
réservation est un engagement entre les deux parties.


### Analyse

**Notion de ressource réservable**

Une `Resource` est sémantiquement un type de `Product`.
C'est une équivalence fonctionnelle : une ressource réservable
est quelque chose qui se vend, avec un nom, une description,
une image, un tarif et des conditions d'accès. BaseBillet
modélise déjà tout cela via `Product` et `Price`.


**Tarification d'une réservation**

Pour le moment, aucun cadre précis n'a été défini pour la
tarification des réservations.

Dans le cas d'usage de La Fabrique pour la découpeuse laser,
les choses sont très simples : les créneaux font 60 min et
sont facturés 15 € chacun. La réservation est obligatoire
pour les usagers normaux. À minima, il faut gérer ce cas ;
nous n'avons pas connaissance d'autres besoins d'utilisateurs
de TiBillet pour le moment.

On peut imaginer également des réservations gratuites et le
besoin de limiter la réservation aux membres avec une
adhésion en cours de validité.

Nous avons besoin de décider comment TiBillet va permettre
de configurer les tarifs (`Price`) et comment le prix d'une
réservation est calculé.

Deux propositions :

1. Tarif par créneau, le plus simple
2. Tarif par durée de référence, plus flexible

Dans le *Tarif par créneau* — le prix est fixé par unité de
créneau, indépendamment de sa durée.

```
total = prix_unitaire × slot_count
```

Exemple : 15 €/créneau, 3 créneaux → 45 €.

Argumentaire :

- on ne peut pas faire plus simple
- compatible avec le fonctionnement actuel, qui supporte
  également la gratuité et le filtrage par adhésion
- il y a une tension : dans les `WeeklyOpening` on est libre
  de définir des durées différentes, mais ce système ne
  permet pas de les prendre en compte. Si on choisit ce
  système, il serait plus cohérent d'interdire les durées de
  créneaux différentes pour une ressource donnée.

Dans le *Tarif par durée de référence* — le prix est fixé
pour une durée indivisible. Toute durée entamée est due.
On prend en compte la durée totale de la réservation pour
calculer le prix.

```
durée_totale = slot_count × slot_duration_minutes
total        = ceil(durée_totale / durée_référence) × prix_unitaire
```

Exemple : 15 €/60 min, 3 créneaux de 90 min →
`ceil(270 / 60) × 15 = 5 × 15 = 75 €`.

Argumentaire :

- on peut naturellement exprimer un tarif du type : 15 €/h
- flexibilité maximale possible en donnant un prix par
  minute, ex. 0,10 €/min
- la règle « Toute durée entamée est due » permet de calculer
  un prix dans tous les cas de figure, même si la durée
  totale n'est pas un multiple de la durée de référence.
  Les lieux peuvent configurer les `WeeklyOpening` afin que
  ce cas de figure n'arrive jamais
- ce tarif permet de gérer des durées de créneaux variables
  selon la granularité choisie par la durée de référence

*Arbitrage* : les deux systèmes sont suffisants pour La
Fabrique. Il faut arbitrer si on préfère la simplicité ou la
flexibilité.

TODO : **À ARBITRER**


**Politique d'annulation et de remboursement**

Pour La Fabrique, on souhaite interdire les annulations 48 h
avant le début. En cas de réclamation, cela sera géré
manuellement en dehors du système TiBillet. Pour les
annulations autorisées, l'idéal est que les usagers reçoivent
un remboursement par carte bancaire. Ainsi le travail bénévole
est minimisé et les usagers sont responsabilisés.

Tous les autres cas de remboursement devront se faire sur
place. C'est le cas où une personne a payé sur place et un
bénévole a créé la réservation via le panneau
d'administration. Du point de vue de TiBillet, cela équivaut
à une réservation sans paiement.

Dans le cas où une commande a été faite avec plusieurs achats,
par exemple un ticket pour un événement (initiation à la
menuiserie) et deux réservations laser distinctes, le besoin
est de pouvoir annuler séparément les achats.

Il y a une complexité supplémentaire : une réservation peut
être de 3 créneaux d'une heure (45 €). On peut imaginer
qu'un usager voudrait réduire à 2 créneaux et se faire
rembourser seulement 15 €. Pour le moment, nous proposons de
ne rembourser que les réservations complètes (ici 45 €, pour
les 3 créneaux). Charge à l'usager de reprendre une
réservation plus courte ensuite.

**v0.3+ — Remboursement partiel et annulation d'un item
dans une Commande**

TODO : **À DISCUTER**

Deux problèmes liés à traiter ensemble :

1. Annuler un seul `Booking` dans une `Commande` multi-items.
   BaseBillet rembourse aujourd'hui toujours le montant total
   d'un paiement Stripe. Il faudra calculer le montant exact
   du `Booking` à rembourser et déclencher un remboursement
   partiel Stripe.

2. Remboursement partiel d'un `Booking` multi-créneaux. Le
   prix étant calculable à la volée depuis `slot_count`,
   `slot_duration_minutes` et le `Price`, le montant à
   rembourser est toujours connaissable. Le chemin technique
   existe.

Une alternative aux remboursements Stripe est un système
d'avoir — un crédit utilisable lors d'une prochaine
réservation, validé manuellement par un bénévole. Plus simple
opérationnellement et cohérent avec la culture des tiers-lieux.


## 2. Modèle de données

### Décision centrale

BaseBillet existe depuis longtemps et gère déjà différents
types de produits et des tarifs associés.

L'app booking vient d'être ajoutée et introduit un type de
produit de manière indépendante.

Deux approches sont possibles :

1. Garder `Resource` dans booking, ajouter un tarif dédié aux
   ressources réservables et programmer de manière indépendante
2. Supprimer `Resource` au profit d'un nouveau type de
   `Product` et exploiter au mieux le `Price` existant et le
   code existant avec des mises à jour.

Un compromis entre les deux donne une entité représentée par
`Product`×`Resource`. Cela semble inadéquat. À minima, cela
pose un problème avec la vue d'administration qui serait
coupée en deux. BaseBillet a déjà une notion de proxy pour
les catégories de `Product` qui fonctionne.

Il semble plus logique de se diriger vers l'option 2 et de
conserver la cohérence existante. Il restera dans booking ce
qui est vraiment spécifique à la logique de réservation.

`Resource` disparaît. Une ressource réservable devient un
`Product` de type `RESSOURCE` dans BaseBillet. `Booking`
référence un `Product` au lieu d'une `Resource`.

TODO : **À VALIDER**

> La suite suppose que `Resource` devient un type de `Product`.

### Correspondance des champs Resource → Product

Les champs suivants de `Resource` ont un équivalent direct
sur `Product` :

- `name` → `Product.name`
- `description` → `Product.long_description`
- `image` → `Product.img`
- `cancellation_deadline_hours` → `Product.refund_deadline`
  (champ existant, même sémantique)

### Ce qui s'ajoute à Product

Quatre champs nullable, renseignés uniquement pour le type
`RESSOURCE` :

- `weekly_opening` (FK nullable → `WeeklyOpening`) — si null,
  aucun créneau n'est généré.
- `calendar` (FK nullable → `Calendar`) — si null, aucune
  fermeture n'est appliquée.
- `capacity` (entier, défaut 0)
- `booking_horizon_days` (entier, défaut 0)

### Ce qui s'ajoute à Price

Si on utilise uniquement le *Tarif par créneau*, il n'y a pas
de modification de `Price`. C'est le fonctionnement normal —
le nombre de créneaux devient une quantité dans le panier.

Si on implémente le *Tarif par durée de référence*, un seul
champ suffit :

- `duree_reference_minutes` (entier nullable) — si null,
  tarif classique ; si renseigné, tarif par durée de
  référence.

> Ce champ n'est pertinent que si le `Price` est associé à
> un `Product` de type `RESSOURCE`.

TODO : **À DISCUTER**


### Booking

`Booking.resource` (FK → `Resource`) devient
`Booking.product` (FK → `Product`).

`Booking.payment_ref` (string) devient
`Booking.commande` (FK nullable → `Commande`).

`Booking.status` : remplacer le statut actuel par
`DRAFT` (défaut), `CONFIRMED` et `CANCELED`, cohérent
avec la nomenclature `Commande` dans BaseBillet.

La logique de réservation n'est à modifier que de manière
superficielle : les `Booking` de statut `CANCELED` sont
traités comme inexistants (simple filtre dans la requête).

### ResourceGroup

Disparaît. Les `Tag` existants sur `Product` jouent ce rôle.

### Ce qui ne change pas

`Calendar` et `WeeklyOpening` restent dans `booking` —
BaseBillet n'en a pas besoin. La logique de génération de
créneaux reste dans `booking/booking_engine.py`.


## 3. Parcours utilisateur et tâches techniques

> **À compléter après validation des sections 1 et 2.**

**État des lieux BaseBillet** — l'admin `Product` est
générique, sans formulaire spécialisé pour `RESSOURCE`. La
page compte membre et le menu tenant n'ont pas d'entrée vers
booking.

**État des lieux booking** — 6 templates publics existent
(`home`, `resource`, `book`, `slot_unavailable`,
`my_bookings`, `cancel_booking`). Ils référencent `Resource`
et devront être mis à jour. Il manque un retour visuel sur
l'adhésion manquante et une page de transition vers le
paiement.

**Analyse** — la fusion `Resource` → `Product` nécessite un
`ModelAdmin` dédié pour le type `RESSOURCE`. Le flux de
paiement ajoute une étape de résumé avant le panier. Un
`Booking` `DRAFT` bloque le créneau immédiatement pour éviter
le sur-booking.

### 1. Lister les ressources (`home`)
Affiche les `Product` de type `RESSOURCE` avec nom, image,
description courte et tags. Lien `/booking/` à ajouter dans
le menu tenant.

### 2. Voir une ressource et ses créneaux (`resource`)
Affiche les détails du `Product` et la grille des créneaux
disponibles avec les tarifs calculés. Retour visuel si
l'adhésion est manquante.

### 3. Sélectionner un créneau (`book`)
Affiche le créneau sélectionné et le montant calculé. Crée
le `Booking` en `DRAFT` à la confirmation. Gère le cas où
le créneau devient indisponible entre la sélection et la
confirmation.

### 4. Résumé avant paiement (`booking_payment`)
Nouvelle page — affiche la ressource, le créneau et le
montant total. Redirige vers le panier ou supprime le
`Booking` `DRAFT` si l'utilisateur annule.

### 5. Panier TiBillet
Les `Booking` `DRAFT` apparaissent dans le panier aux côtés
des billets et adhésions. Retirer un booking supprime le
`Booking` `DRAFT`. Le paiement crée la `Commande` incluant
les `Booking` `DRAFT`. Point d'accroche à implémenter dans
BaseBillet.

### 6. Confirmation Stripe
Traitement serveur uniquement. BaseBillet passe les `Booking`
liés à la `Commande` de `DRAFT` à `CONFIRMED` via les signaux
existants. Point d'accroche à implémenter dans BaseBillet.

### 7. Mes réservations (`my_bookings`)
Liste les `Booking` `CONFIRMED` et `CANCELED` de l'utilisateur
avec le délai d'annulation restant. Lien vers l'annulation.
Un accès depuis la page compte membre BaseBillet est à prévoir.

### 8. Annulation
`DRAFT` → suppression réelle du `Booking`. `CONFIRMED` →
`CANCELED` si avant `refund_deadline`, remboursement Stripe
orchestré par BaseBillet. Annulation refusée après expiration
du délai.

### 9. Nettoyage automatique
Tâche Celery beat pour supprimer les `Booking` `DRAFT`
expirés (paniers abandonnés) et libérer les créneaux.
