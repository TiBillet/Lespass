# Booking — Architecture Decisions

> **Convention :** ce document est en ajout uniquement. Ne jamais
> renuméroter ni supprimer une section existante. Toujours ajouter à
> la fin.
> / **Convention:** append-only. Never renumber or remove an existing
> section. Always add at the end.

## 1. Annulation = suppression de la ligne Booking

**Source :** `booking/models.py` — classe `Booking`

L'annulation supprime la réservation. Pas de statut `cancelled`.

Risque : perte de traçabilité (litiges remboursement, analytics).
Migration future si besoin : ajouter `cancelled_at` (DateTimeField nullable).
Non-null = annulé, null = actif.

## 2. start_datetime est un DateTimeField timezone-aware

**Source :** `booking/models.py` — classe `Booking`

Le champ `start_datetime` est un `DateTimeField` (pas `DateField` + `TimeField`
séparés). TiBillet définit un fuseau horaire par tenant dans la configuration —
toutes les dates de réservation doivent être timezone-aware. `timezone.now()`
et `django.utils.timezone` sont les seuls outils à utiliser pour manipuler ce
champ.

## 3. Capacity = 0 autorisé

**Source :** `booking/models.py` — classe `Resource`

Capacity=0 désactive silencieusement les réservations sans toucher au
Calendar ni au WeeklyOpening. Le slot engine vérifie `remaining_capacity > 0`
— pas besoin d'un flag `is_active` séparé.

## 4. Tags sur Resource et ResourceGroup — JSONField provisoire

**Source :** `booking/models.py` — classes `Resource` et `ResourceGroup`

`tags = JSONField(default=list)` est un champ provisoire. Le système de tags
existant dans TiBillet (`BaseBillet.Tag`) est une vraie relation
`ManyToManyField` avec nom, slug et couleur — c'est ce qu'utilisent les
événements.

Migration future : remplacer le JSONField par un `ManyToManyField` vers
`BaseBillet.Tag`, comme sur `BaseBillet.Product`. Cela donnera un sélecteur
de tags dans l'admin et une cohérence avec le reste de la plateforme.

En attendant, le champ est masqué dans l'admin (non listé dans `fields`).

## 5. Traductions françaises du module booking — en attente

**Source :** `locale/fr/LC_MESSAGES/django.po`

Le fichier PO contient des conflits git non résolus qui empêchent
`makemessages` de fonctionner. Les chaînes du module booking (verbose names,
help texts, statuts) ne sont donc pas encore traduites en français.

Action future : une fois les conflits résolus en amont, lancer
`python manage.py makemessages -l fr` puis ajouter les traductions
manquantes dans `locale/fr/LC_MESSAGES/django.po` et recompiler avec
`compilemessages`.

## 6. Formulaire de réservation dans l'admin — ergonomie à améliorer

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
