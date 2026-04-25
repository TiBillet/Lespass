# Booking — Finding, Issues and Architecture Decisions

> **Convention :** ce document est en ajout uniquement. Ne jamais
> renuméroter ni supprimer une section existante. Toujours ajouter à
> la fin.
> / **Convention:** append-only. Never renumber or remove an existing
> section. Always add at the end.

## §1. Annulation = suppression de la ligne de la table Booking (Futur)

**Source :** `booking/models.py` — classe `Booking`

L'annulation supprime la réservation. Pas de statut `cancelled`.

Risque : perte de traçabilité (litiges remboursement, analytics).
Migration future si besoin : ajouter `cancelled_at` (DateTimeField nullable).
Non-null = annulé, null = actif.

À prendre en compte après la v1.


## §2. archived

## §3. archived


## §4. Tags sur Resource et ResourceGroup — JSONField provisoire (Futur)

**Source :** `booking/models.py` — classes `Resource` et `ResourceGroup`

`tags = JSONField(default=list)` est un champ provisoire. Le système de tags
existant dans TiBillet (`BaseBillet.Tag`) est une vraie relation
`ManyToManyField` avec nom, slug et couleur — c'est ce qu'utilisent les
événements.

Migration future : remplacer le JSONField par un `ManyToManyField` vers
`BaseBillet.Tag`, comme sur `BaseBillet.Product`. Cela donnera un sélecteur
de tags dans l'admin et une cohérence avec le reste de la plateforme.

En attendant, le champ est masqué dans l'admin (non listé dans `fields`).


## §5. Traductions françaises du module booking (en attente)

**Source :** `locale/fr/LC_MESSAGES/django.po`

Le fichier PO contient des conflits git non résolus qui empêchent
`makemessages` de fonctionner. Les chaînes du module booking (verbose names,
help texts, statuts) ne sont donc pas encore traduites en français.

Action future : une fois les conflits résolus en amont, lancer
`python manage.py makemessages -l fr` puis ajouter les traductions
manquantes dans `locale/fr/LC_MESSAGES/django.po` et recompiler avec
`compilemessages`.


## §6. Formulaire de réservation dans l'admin (Futur)

**Source :** `booking/admin.py` — classe `BookingAdmin`

Le formulaire actuel expose directement les champs bruts du modèle
(`start_datetime`, `slot_duration_minutes`, `slot_count`, etc.). Ce n'est pas
pratique pour un gestionnaire : il faut saisir une date/heure en ISO, un
nombre de minutes, un nombre de créneaux.

Amélioration future : remplacer le formulaire par un sélecteur de créneaux
calculés (liste déroulante des créneaux disponibles pour une ressource et une
date donnée, générée par le slot engine de la Session 5). Le formulaire
admin deviendrait alors cohérent avec l'interface publique de réservation.

Le champ `status` pose également problème : l'admin peut manuellement choisir
n'importe quel statut (`new`, `validated`, `confirmed`) sans passer par le
flux de paiement. Cela peut créer des incohérences (réservation marquée
`confirmed` sans paiement enregistré). À terme, le statut devrait être
en lecture seule dans l'admin, ou les transitions autorisées devraient être
limitées (ex : seul `confirmed → annulation` via suppression).


## §7. archived

## §8. archived

## §9. archived

## §10. archived

## §11. archived

## §12. archived

## §13. archived

## §14. archived

## §15 - problème de performance sur calcul de dispo

les réservations (Booking) peuvent avoir des durées arbitraires.
Dans le modèle, il y a juste le datetime du début. Donc
Pour calculer les créneaux libres, il faut charger la totalité
des réservations puis calculer leur datetime de fin.

On peut éviter cela en ajouter la datetime de fin de chaque
réservation en BDD. Attention : c'est une donnée qui sera redondante
avec la durée des slot et leur nombre.

**État actuel (avril 2026) :** `get_existing_bookings_for_resource` charge
toutes les réservations de la ressource sans filtre de date. L'ancien filtre
`start_datetime__date__range` était incomplet (manquait les réservations
démarrant avant la fenêtre mais s'étendant à l'intérieur). Une fois
`end_datetime` ajouté en base, réintroduire le filtre :
`start_datetime < window.end AND end_datetime > window.start`.

## §16 - problème début des créneaux à l'heure pret

Il faut prendre en compte l'heure dans la fenetre de calcul
des créneaux ouvert.

## §16 - manque des tags dans le fixture

Il faut ajouter les tags "salle" et "machine" par exemple.


## §17 - vue des réservations 

Y'a aucune raison pour que ca soit dans /my_account/my_resources/
plutot que /booking/SOMETHING

Suffit de mettre un lien dans /my_account qui amène vers la bonne
page de booking


## §18 - mise à jour vue des booking

ca ne se met pas à jour immédiatement lorsqu'on réserve plusieurs slots
seul le slot cliqué se màj. Les suivants non


## §19 — Annulation en un clic — confirmation obligatoire selon la spec

**Source :** `booking/templates/booking/views/my_bookings.html`

La spec §7.3 est explicite : "the action should require a deliberate step —
not a single accidental click." Le bouton "Annuler" actuel déclenche le
`hx-post` immédiatement au clic, sans confirmation.

Action future : ajouter une étape de confirmation avant l'envoi de la
requête HTMX. Options envisageables : modale Bootstrap, bouton bascule
inline (un clic = affiche "Êtes-vous sûr ? Confirmer / Annuler"), ou
`hx-confirm` natif HTMX (simple mais non stylisable).


## §20 — Deadline d'annulation non affichée sur la page mes-réservations

**Source :** `booking/templates/booking/views/my_bookings.html`,
`booking/views.py` — `my_bookings()`

La spec §7.3 : "The deadline must be visible without entering a
cancellation flow." Le template n'affiche que `resource.name` et
`start_datetime`. La deadline (calculée comme
`start_datetime − cancellation_deadline_hours`) n'est visible qu'en
cas d'échec de l'annulation (réponse 422), pas avant.

Action future : calculer la deadline par réservation dans la vue
`my_bookings()` (annoter le queryset ou construire une liste de
tuples `(booking, deadline)`) et l'afficher dans chaque ligne de la
liste, par exemple : "Annulation possible jusqu'au mer. 29/04 14:00".


## §21 — Panier affiché sur la page mes-réservations — choix UX à arbitrer

**Source :** `booking/templates/booking/booking_base.html`

`booking_base.html` inclut systématiquement `{% include "booking/partial/basket.html" %}`
en haut de toutes les vues du module, y compris `/booking/my-bookings/`.
La page mes-réservations est centrée sur les réservations `confirmed` ; le
panier (réservations `new`) n'est pas mentionné dans la spec §7.3 pour cette
vue.

Question ouverte : le panier doit-il apparaître sur la page
mes-réservations ? Arguments pour : cohérence visuelle dans le module,
le membre voit tout au même endroit. Arguments contre : charge cognitive
inutile sur une page de gestion, risque d'interaction concurrente entre
le bouton "Retirer du panier" et le bouton "Annuler" si les deux sont
déclenchés simultanément (requête abandon silencieuse via HX-Redirect).

Décision à prendre avec l'équipe avant la finalisation du template.


## §22 — Filtre "à venir" trop strict — réservations en cours et passées masquées

**Source :** `booking/views.py` — `my_bookings()`

Le queryset filtre `start_datetime__gt=now()` : une réservation disparaît
de la liste à la seconde où elle commence. Un membre qui a réservé une
salle de 14h à 16h ne la voit plus à 14h01, alors qu'il l'occupe encore.

La spec dit "upcoming confirmed bookings" sans définir le seuil précisément.
L'utilisateur souhaite également afficher les réservations passées récentes.

Action future : ajuster le filtre pour inclure les réservations en cours
et éventuellement un historique. Options :
- Filtrer par `end_datetime > now()` une fois `end_datetime` disponible en
  base (voir §15 sur la redondance) ;
- Ou séparer l'affichage : section "À venir / en cours" +
  section "Passées" (30 derniers jours par exemple), chacune avec son filtre.
- Le filtre actuel peut rester pour la section "à venir" mais une section
  "aujourd'hui" ou "en cours" devrait afficher les créneaux démarrés et
  non encore terminés.


## §23 — compute_slots appelé sans contrainte de date dans booking_form et cancel_form (résolu)

**Source :** `booking/views.py`

Les vues d'affichage du calendrier (`resource_detail`, listing) appellent
`compute_slots(ressource)` sans fenêtre — c'est correct, elles ont besoin
de tous les créneaux.

Les vues qui ne cherchaient qu'un seul créneau scannaient l'horizon entier
inutilement. Toutes résolues :

- **cancel_form** : ne fait plus appel à `compute_slots`. Reconstruit le
  `BookableInterval` depuis les paramètres GET — coût O(1).
- **booking_form** (avril 2026) : fenêtre `[start_datetime, fin de l'horizon)`.
  L'horizon complet est conservé car les créneaux consécutifs sont nécessaires
  pour calculer `max_slot_count`.
- **add_to_basket** (avril 2026) : fenêtre
  `[start_datetime, start_datetime + slot_duration_minutes)` — un seul
  créneau, coût O(1).

Rendu possible par l'introduction du paramètre `window: Interval` sur
`compute_slots`.
