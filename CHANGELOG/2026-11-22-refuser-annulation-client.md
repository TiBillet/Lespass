# Refuser l'annulation par le client / Refuse cancellation by the customer

**Date :** 2026-11-22
**Migration :** Oui — `BaseBillet/migrations/0242_event_annulation_par_le_client_desactivee.py`
(`docker exec lespass_django poetry run python manage.py migrate_schemas --executor=standard`)

## Resume / Summary
**Quoi / What :** Une case sur l'événement, « Refuser l'annulation par le client », bloque
l'annulation d'une réservation ou d'un billet depuis « Mon compte », payants ou gratuits.
L'annulation reste possible depuis l'administration. La mention « Billet daté, non échangeable et
non remboursable (sauf annulation ou report de l'événement par l'organisateur). » s'affiche dans le
formulaire de réservation, le panier et le mail de confirmation. Un pass est indivisible : un seul
de ses événements qui refuse bloque tout le pass.
/ A checkbox on the event blocks cancelling a booking or a ticket from "My account", paid or free.
The admin can still cancel. A notice is shown in the booking form, the cart and the confirmation
email. A pass is indivisible: one refusing event blocks the whole pass.

**Pourquoi / Why :** Certains événements n'acceptent pas d'annulation par l'acheteur. En cas de
force majeure, l'organisateur annule depuis l'administration.
/ Some events do not accept cancellation by the buyer; the organiser can still cancel.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/models.py` | `Event.annulation_par_le_client_desactivee`, `Event.MENTION_ANNULATION_REFUSEE` ; `Reservation.annulation_par_le_client_refusee()` et `Ticket.annulation_par_le_client_refusee()` ; refus dans `cancel_and_refund_resa` et `cancel_and_refund_ticket`, sauf pour l'admin |
| `BaseBillet/migrations/0242_event_annulation_par_le_client_desactivee.py` | Migration du champ |
| `Administration/admin_tenant.py` | La case, sous le délai de remboursement (section « Bookings ») |
| `pages/templates/pages/{classic,V2}/vues/compte/reservations.html`, `.../partials/ticket_accordion.html` | Le bouton d'annulation est remplacé par « Annulation en ligne impossible : contactez l'organisateur. » |
| `BaseBillet/templates/commun/formulaires/reservation.html` | La mention, au-dessus des boutons |
| `BaseBillet/context_processors.py`, `BaseBillet/templates/htmx/components/panier_item.html` | La mention sous chaque billet du panier concerné |
| `BaseBillet/templates/emails/buy_confirmation.html` | La mention dans le mail de confirmation |
| `tests/pytest/test_annulation_client_refusee.py` | Nouveau : 19 tests |

### Limites / Limits
- L'option s'applique aussi aux réservations déjà faites.
- La mention n'est ni sur le billet PDF, ni à la caisse, ni dans l'API v2.
- L'option est sur l'événement : elle vaut pour tous ses tarifs, gratuits compris.

---

## Comment tester (a la main) / Manual test

### Test 1 — scénario nominal
1. Admin > événement à venir > « Bookings » : cocher « Refuser l'annulation par le client ».
2. Page de l'événement > réserver : la mention est au-dessus des boutons.
3. Ajouter au panier : la mention est sous le billet.
4. Réserver. Le mail de confirmation contient « Conditions d'annulation » et la mention.
5. « Mon compte > Mes réservations » : pas de bouton d'annulation, ni sur la réservation ni sur le
   billet. Le texte « Annulation en ligne impossible : contactez l'organisateur. » les remplace.
6. Admin > Réservations : « Cancel and refund » annule la réservation.

### Test 2 — page restée ouverte
1. Case décochée, ouvrir « Mes réservations ». Cocher la case dans un autre onglet.
2. Cliquer « J'annule ma reservation » dans le premier onglet : message d'erreur, rien n'est annulé.

### Test 3 — pass
1. Pass samedi + dimanche, case cochée sur le samedi seulement.
2. Ajouter le pass depuis la page du dimanche : la mention est dans le panier.
3. Acheter le pass : ni le billet du samedi ni celui du dimanche ne s'annulent depuis le compte.

### Test 4 — tests automatiques
- `docker exec lespass_django poetry run pytest tests/pytest/test_annulation_client_refusee.py -q`
- Attendu : 19 passed.
