# Agenda et carte : les événements en cours restent affichés / Agenda and map: ongoing events stay listed

**Date :** 2026-10-20
**Migration :** Non

## Resume / Summary
**Quoi / What :** Un événement commencé dont la date de fin n'est pas passée (ex : une expo du 17 octobre au 1er novembre) reste visible :
- dans l'agenda du lieu (`/event/`) ;
- dans le filtre par jour de l'agenda (menu « Trier par date », skin faire_festival) : l'expo apparaît pour chaque jour qu'elle couvre, et le menu propose « aujourd'hui » plutôt que son jour de début passé ;
- sur la carte « Autour de nous » (`/federation/`), l'explorateur du réseau et les compteurs d'événements du cache SEO.

/ A started event whose end date has not passed stays visible in the agenda, its day filter, the network map, the explorer and the SEO event counts.
**Pourquoi / Why :** Tous ces filtres ne regardaient que la date de début : une expo de plusieurs semaines disparaissait dès son 2ᵉ jour, malgré sa date de fin.
/ All these filters only looked at the start date.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/views.py` | `EventMVT.federated_events_filter` : `début ≥ hier` OU `fin ≥ maintenant` ; filtre par jour = commence ce jour OU a commencé avant et finit ce jour ou après ; un jour choisi range tout sous ce jour ; menu des jours : une expo en cours compte pour aujourd'hui |
| `seo/services.py` | Les 4 requêtes SQL du cache (compteurs, événements, tags) : `datetime >= maintenant OR end_datetime >= maintenant` |
| `tests/pytest/test_agenda_evenement_en_cours.py` | 7 tests (agenda, filtre par jour, menu des jours, carte, compteur) |

Sans filtre de jour, l'événement en cours reste rangé sous sa date de début (en tête de l'agenda) ; sa carte affiche « Du … au … ».

Après déploiement :
- le cache de la page principale de l'agenda peut garder l'ancienne liste jusqu'à 1 h (ou jusqu'au prochain enregistrement d'un événement du lieu) ;
- la carte et l'explorateur lisent le cache SEO : l'expo y apparaît au prochain rafraîchissement de ce cache par la tâche Celery.

---

## Comment tester (a la main) / Manual test
### Test 1 — agenda
1. Admin : créer un événement publié qui a commencé il y a quelques jours, avec une date de fin dans le futur.
2. Ouvrir `/event/` : l'événement apparaît en tête de l'agenda.
3. Mettre une date de fin dans le passé : l'événement disparaît.
4. Un événement passé sans date de fin n'apparaît pas.

### Test 2 — filtre par jour (skin faire_festival)
1. Menu « Trier par date » : le jour d'aujourd'hui est proposé (pas le jour de début de l'expo).
2. Choisir un jour couvert par l'expo : elle est listée sous ce jour.
3. Choisir un jour après sa date de fin : elle n'est pas listée.

### Test 3 — carte et explorateur
1. Rafraîchir le cache SEO (tâche Celery du module seo).
2. `/federation/` : l'expo apparaît dans la liste des événements et dans la popup du lieu.
