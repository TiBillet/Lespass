# Admin événements : avertissement si le créneau est déjà occupé / Event admin: warning when the slot is taken

**Date :** 2026-10-20
**Migration :** Non

## Resume / Summary
**Quoi / What :** Après l'enregistrement d'un événement dans l'admin (création ou modification), des avertissements jaunes (`messages.warning`) signalent :
1. la ressource bloquée a déjà des réservations sur le créneau (noms des personnes) ;
2. la ressource bloquée est déjà bloquée par un autre événement ;
3. d'autres événements ont lieu sur le même créneau (sans répéter ceux du point 2).

L'enregistrement n'est jamais bloqué.
/ After saving an event in the admin, warnings flag existing bookings on the blocked resource, another event already blocking it, and other events in the same time slot. Saving is never blocked.
**Pourquoi / Why :** Repérer les doubles occupations sans empêcher l'admin de les assumer.
/ Spot double bookings without preventing the admin from accepting them.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin_tenant.py` | `EventAdmin._avertir_si_le_creneau_est_deja_occupe()`, appelée à la fin de `save_model()` |
| `tests/pytest/test_event_admin_avertissement_creneau.py` | 8 tests (passage par `save_model`, réservation, ressource bloquée, autre événement, sans date de fin, créneaux qui se suivent, actions bénévoles de l'événement, actions bénévoles d'un autre événement) |

Règles :
- Les filtres sont ceux du moteur de réservation (réservations actives, événements non archivés).
- La famille de l'événement (parent, actions bénévoles, sœurs) est ignorée.
- Les actions bénévoles des autres événements ne comptent pas comme « autres événements ».
- Un événement sans date de fin compte comme un instant : il chevauche un événement s'il commence pendant celui-ci ou à la même heure.
- Deux créneaux qui se suivent (10h-12h puis 12h-14h) ne se chevauchent pas.

i18n : 3 chaînes nouvelles — workflow i18n à lancer.

---

## Comment tester (a la main) / Manual test
### Test 1 — ressource déjà réservée
1. Réserver une ressource sur un créneau (front `/booking/`).
2. Admin → Événements → Ajouter : même date, « Ressource bloquée » = cette ressource, date de fin renseignée. Enregistrer.
3. L'événement est créé, un avertissement jaune cite la personne qui a réservé.

### Test 2 — ressource déjà bloquée par un événement
1. Créer un second événement qui bloque la même ressource sur un créneau qui chevauche le premier.
2. Un seul avertissement : « déjà bloquée sur ce créneau par : « … » ».

### Test 3 — autre événement sur le créneau
1. Créer un événement sans ressource, aux mêmes heures qu'un événement existant.
2. Avertissement « D'autres événements ont lieu sur ce créneau : « … » ».

### Test 4 — pas de faux positif
1. Créer un événement qui commence pile à la fin d'un autre : aucun avertissement.
2. Ajouter une action bénévole à un événement : aucun avertissement.
