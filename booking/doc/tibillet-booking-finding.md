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

## §4. archived

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
(`start_datetime`, `slot_duration_minutes`, `slot_count`, etc.). Ce n'est
pas pratique pour un gestionnaire : il faut saisir une date/heure en ISO,
un nombre de minutes, un nombre de créneaux.

Amélioration future : remplacer le formulaire par un sélecteur de créneaux
calculés (liste déroulante des créneaux disponibles pour une ressource et
une date donnée). Le formulaire admin deviendrait alors cohérent avec
l'interface publique de réservation.

Le formulaire admin doit également permettre la saisie libre (free form) :
un gestionnaire doit pouvoir créer une réservation à n'importe quelle
heure et durée, indépendamment du WeeklyOpening — par exemple pour
bloquer une ressource lors d'un événement spécial. C'est explicitement
prévu par la spec §4.3 et §5 (Volunteer bookings bypass E validity rule).
Le sélecteur de créneaux calculés et la saisie libre doivent donc coexister
dans le même formulaire admin.

**Note (avril 2026) :** en v0.1, `Booking.status` n'a qu'une seule valeur
possible : `confirmed`. La question des transitions de statut ne se pose
donc plus pour l'instant. Elle redeviendra pertinente quand le panier et
le paiement seront intégrés (v0.2+).


## §7. archived

## §8. archived

## §9. archived

## §10. archived

## §11. archived

## §12. archived

## §13. archived

## §14. archived

## §15. archived

## §16. archived

## §16b. archived

## §17. archived

## §18. archived

## §19. archived

## §20. archived

## §21. archived

## §22. archived

## §23. archived
