# Événement : commentaire interne, comm' envoyée, ressource bloquée / Event: internal comment, communication sent, blocked resource

**Date :** 2026-10-18
**Migration :** Oui — `BaseBillet/migrations/0233_event_champs_internes_ressource_bloquee.py` (dépend de `booking/0001`, pas de `booking/0005`)
`docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --executor=standard`

## Resume / Summary
**Quoi / What :**
- `Event.commentaire_interne` (texte) et `Event.communication_envoyee` (case à cocher) : visibles seulement dans l'admin, section « Interne (non publié) ». « Comm' envoyée » est aussi une colonne cochable de la liste. / Two admin-only fields; "communication sent" is also an editable list column.
- `Event.ressource_bloquee` (ressource du module réservation, facultative) : les créneaux de la ressource qui chevauchent l'événement deviennent complets, et leur réservation est refusée. Champ visible seulement si le module réservation est actif ; la date de fin devient alors obligatoire. Un événement archivé ne bloque plus ; un événement non publié bloque déjà. / Overlapping slots of the resource become full; admin-only, booking module only; end date required.

**Pourquoi / Why :** suivre la comm' et laisser des notes d'équipe sans les publier ; empêcher la réservation de la salle de répétition pendant un concert qui s'y tient. / Track communication and team notes privately; prevent booking a room during an event held there.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/models.py` | 3 champs sur `Event` |
| `BaseBillet/migrations/0233_event_champs_internes_ressource_bloquee.py` | Migration (dépendance booking ramenée à `0001_initial`) |
| `Administration/admin_tenant.py` | Section « Interne (non publié) », colonne cochable, `EventAdmin.get_fieldsets()` (masque la ressource sans module réservation), `EventForm.clean()` (date de fin obligatoire) |
| `booking/booking_engine.py` | `get_event_intervals_blocking_resource()`, `slot_overlaps_a_blocked_interval()` ; `compute_slots()` met à 0 les créneaux bloqués (`validate_new_booking` en hérite) |
| `booking/tests/test_ressource_bloquee_par_evenement.py` | 4 tests : chevauchement, brouillon, archivé, réservation refusée |
| `tests/pytest/test_event_champs_internes.py` | 3 tests : API sans champs internes, date de fin obligatoire, champ masqué sans module |

---

## Comment tester (a la main) / Manual test
### Test 1 — champs internes
1. Admin > Événements > un événement : section « Interne (non publié) » en bas.
2. Écrire un commentaire, cocher « Comm' envoyée », enregistrer.
3. La page publique de l'événement et `/api/v2/events/` ne montrent ni le commentaire ni la case.
4. Dans la liste des événements, la colonne « Comm' envoyée » se coche directement, puis « Enregistrer ».

### Test 2 — ressource bloquée
1. Module réservation actif. Événement le lundi prochain 10 h 15 – 10 h 45, ressource « Petite salle ».
2. Sans date de fin : l'enregistrement est refusé (« Une date de fin est obligatoire pour bloquer une ressource. »).
3. Avec la date de fin : sur `/booking/`, page de la Petite salle, le créneau qui chevauche 10 h 15 – 10 h 45 apparaît complet ; les créneaux voisins restent réservables.
4. Archiver l'événement : le créneau redevient réservable.

### Test 3 — module réservation éteint
1. Paramètres : désactiver le module réservation.
2. Fiche événement : le champ « Ressource bloquée » a disparu ; les deux autres champs internes restent.

### Verifs automatiques
- `docker exec -w /DjangoFiles lespass_django poetry run pytest booking/tests/test_ressource_bloquee_par_evenement.py tests/pytest/test_event_champs_internes.py -q`
- Vérifiés par mutation (blocage désactivé : 3 tests tombent ; contrôle de la date de fin désactivé : 1 test tombe).
