# Page événement V2 : retrait du talon et du bouton agenda / V2 event page: ticket stub and calendar button removed

**Date :** 2026-10-20
**Migration :** Non

## Resume / Summary
**Quoi / What :** sur la page événement du skin V2, le talon (prix et places restantes au-dessus du bouton de réservation) et le bouton « Je veux ajouter l'événement à mon agenda » (téléchargement ICS) sont retirés. Seul le bouton de réservation reste.
/ On the V2 event page, the ticket stub (price and seats left) and the "add to my calendar" (ICS) button are removed. Only the booking button remains.

**Pourquoi / Why :** le talon affichait une fourchette de prix fausse quand l'événement a plusieurs produits. Le bouton agenda sera reposé ailleurs plus tard.
/ The stub showed a wrong price range when an event has several products. The calendar button will be placed elsewhere later.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `pages/templates/pages/V2/partials/reservation_declencheur.html` | Retrait du `<dl class="talon">` et du lien `download_ics()` |
| `pages/static/V2/css/V2.css` | Retrait des règles `.talon*` devenues mortes ; bouton de réservation centré (`margin-inline: auto` sur `.reservation-declencheur`) |
| `pages/templates/pages/V2/vues/evenement.html` | TODO sur le script ICS : la fonction `download_ics()` reste en place, sans bouton qui l'appelle |

`Event.places_restantes()` (utilisée par la vue détail) et `Event.jauge_presque_pleine()` (plus utilisée par aucun gabarit) restent dans `BaseBillet/models.py`.

---

## Comment tester (a la main) / Manual test
### Test 1 — page événement V2
1. Ouvrir un événement d'un lieu en skin V2 (ex. `https://la-maison-des-communs.tibillet.localhost/event/…`).
2. Attendu : sous l'en-tête, uniquement le bouton de réservation. Pas de cadre « Par billet / Places restantes », pas de bouton « ajouter à mon agenda ».
3. Cliquer sur le bouton de réservation : le panneau latéral s'ouvre comme avant.

### Test 2 — événement à plusieurs produits
1. Ouvrir un événement avec plusieurs produits à prix différents.
2. Attendu : aucune fourchette de prix affichée au-dessus du bouton.
