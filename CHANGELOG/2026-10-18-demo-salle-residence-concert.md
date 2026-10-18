# Démo : salle de résidence et concert bloquée par les événements / Demo: residence & concert room blocked by events

**Date :** 2026-10-18
**Migration :** Non (s'appuie sur `BaseBillet/0233`, voir `2026-10-18-event-champs-internes-ressource-bloquee.md`)

## Resume / Summary
**Quoi / What :**
- Fixtures booking : nouvelle ressource « Salle de résidence et concert » (groupe « Salle de répét' », capacité 1, horizon 90 jours), ouverte tous les jours en deux créneaux : journée 10 h – 18 h (résidence) et soirée 18 h – minuit (concert). Tous les événements du lieu (hors tests E2E / API v2 / pytest) la bloquent. / New demo room, open daily (day + evening slots), blocked by every venue event.
- Fixtures événements (`demo_data_v2`) : date de fin = début + 3 h (événements et sous-événements) ; dates tirées entre +7 et +90 jours (au lieu de +180 / +540). / Demo events get an end (+3 h) and are drawn within the next 90 days.

**Pourquoi / Why :** montrer le blocage d'une ressource par la programmation dès le flush. Un événement sans fin ne bloque rien, et des événements à +6 mois tombaient hors de tout horizon de réservation raisonnable. / Showcase resource blocking right after a flush.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `booking/management/commands/create_booking_fixtures.py` | Planning « Résidence et concert », produit + tarif, ressource, `_bloquer_la_salle_de_concert_pendant_les_evenements()` ; exemple de lancement direct en `tenant_context` |
| `Administration/management/commands/demo_data_v2.py` | `end_datetime` = début + 3 h ; dates entre +7 et +90 jours |

### Limite connue / Known limitation
La page de réservation d'une ressource (`booking/views.py`, `resource_page`) calcule et dessine TOUT l'horizon d'un coup ; la navigation par semaine ne fait que masquer / afficher en JS. 90 jours × 2 créneaux/jour ≈ 2 Mo de HTML (550 jours ≈ 8,7 Mo). Chantier à prévoir : une semaine par requête HTMX.

---

## Comment tester (a la main) / Manual test
### Test 1 — après un flush
1. Lancer le flush de démo habituel.
2. Agenda : les événements tombent dans les 3 prochains mois ; chaque fiche affiche une heure de fin (début + 3 h).
3. `/booking/` → « Salle de résidence et concert » : les soirées des jours de concert sont complètes, les journées restent réservables.
4. Admin > un événement de démo > section « Interne » : « Ressource bloquée » = Salle de résidence et concert.

### Test 2 — idempotence
1. Relancer `create_booking_fixtures` dans le tenant (voir l'exemple en tête du fichier, `tenant_context`).
2. Le planning de la salle garde 14 entrées (2 par jour), pas de doublon de ressource.
