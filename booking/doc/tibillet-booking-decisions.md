# Booking — Architecture Decisions

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
