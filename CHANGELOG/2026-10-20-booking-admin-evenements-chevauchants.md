# Réservation : l'admin voit tous les événements d'un créneau / Booking: admin sees every event of a slot

**Date :** 2026-10-20
**Migration :** Non

## Resume / Summary
**Quoi / What :** Sur la page de réservation d'une ressource (front, vue admin), la case d'un créneau bloqué par plusieurs événements qui se chevauchent écrit le titre de chacun, un par ligne. Le détail (i) titre « Événements qui bloquent la ressource » au pluriel.
/ On the resource booking page (admin view), a slot blocked by several overlapping events lists every title, one per line.
**Pourquoi / Why :** La case n'écrivait que le titre du premier événement.
/ The cell only showed the first event's title.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `booking/views.py` | `infos_admin['libelle_court']` (texte) devient `infos_admin['libelles_de_la_case']` (liste : un titre par événement) |
| `booking/templates/booking/partials/resource_semaine.html` | Une ligne par libellé, grilles desktop et mobile |
| `booking/templates/booking/partials/infos_creneau_admin.html` | Titre au singulier ou pluriel selon le nombre d'événements |
| `tests/pytest/test_booking_calendrier_semaine.py` | Test : deux événements qui se chevauchent apparaissent dans la case |

i18n : 1 chaîne plurielle nouvelle (« Événement qui bloque la ressource » / « Événements qui bloquent la ressource ») — workflow i18n à lancer.

---

## Comment tester (a la main) / Manual test
1. Connecté en admin, ouvrir `https://lespass.tibillet.localhost/booking/5/resource/?semaine=2027-01-11` (données de démo : « Jardinage et plantation » et « Réunion d'équipe » se chevauchent le lundi 11/01).
2. La case 18h00 - 00h00 du lundi écrit les deux titres, l'un sous l'autre.
3. Clic sur la case : le détail liste les deux événements sous « Événements qui bloquent la ressource ».
4. En vue mobile : même chose dans la liste du jour.
5. Un créneau avec un seul événement garde « Événement qui bloque la ressource » au singulier.
