# Réservation gratuite : redirection, texte de validation, panier désactivable / Free booking: redirect, validation text, cart can be disabled

**Date :** 2026-10-20
**Migration :** Oui — `BaseBillet/migrations/0237_event_panier_desactive.py` (`manage.py migrate_schemas --executor=multiprocessing`)

## Resume / Summary
**Quoi / What :**
1. Réservation gratuite par un visiteur non connecté, avec l'e-mail d'un compte déjà validé : retour à la page de l'événement avec le toast « Réservation reçue ! Vos billets arrivent par e-mail. ». Un visiteur connecté va toujours sur « Mes réservations ».
2. Nouveau texte quand l'e-mail doit être validé (remerciement, mail de validation, places gardées N min, spams avec l'adresse de l'expéditeur, second mail avec les billets).
3. Nouveau champ `Event.panier_desactive` (faux par défaut), dans la section « Publier » de l'admin. Coché : aucun bouton panier dans le formulaire de réservation, seulement la réservation directe ; `PanierSession.add_ticket` refuse aussi les billets de cet événement (POST forgé, et rejoué au paiement par `revalidate_all`).

/ 1. Anonymous free booking with a validated email: back to the event page with a success toast (logged-in visitors still go to "my bookings"). 2. New email-validation text. 3. New `Event.panier_desactive` field (default False, admin "Publish" section): direct booking only, enforced server-side.

**Pourquoi / Why :** le visiteur non connecté était envoyé sur « Mes réservations », qui exige d'être connecté : deux toasts contradictoires (succès + « Connectez-vous »). Le texte de validation ne disait pas qu'un second mail apporte les billets. Certains événements ne doivent pas passer par le panier.
/ Anonymous visitors were sent to a login-only page (two contradictory toasts). The validation text did not mention the second email. Some events must not use the cart.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/views.py` | `EventMVT.reservation` : compte actif + visiteur non connecté → `event-detail` + toast ; contexte de `reservation_ok.html` : `adresse_d_expedition` (même règle que `CeleryMailerClass`, nom affiché retiré), plus de `user` |
| `BaseBillet/templates/fonctionnel/event/reservation_ok.html` | Nouveau texte ; branche « compte actif » retirée (la vue redirige ces comptes) ; `data-testid="reservation-ok-validation-email"` |
| `BaseBillet/models.py` | `Event.panier_desactive` |
| `BaseBillet/migrations/0237_event_panier_desactive.py` | Ajout du champ |
| `Administration/admin_tenant.py` | `panier_desactive` dans la section « Publish » d'EventAdmin |
| `BaseBillet/services_panier.py` | `add_ticket` refuse un événement dont le panier est désactivé |
| `BaseBillet/templates/commun/formulaires/reservation.html` | Panier désactivé : un seul bouton de réservation directe (« Payer maintenant » connecté, « Envoyer la demande » anonyme) |
| `tests/pytest/test_reservation_gratuite_redirection.py` | Nouveau : 3 cas de redirection, adresse de l'expéditeur, boutons panier selon l'option |
| `tests/pytest/test_panier_session.py` | `add_ticket` refuse un événement au panier désactivé |

Chaînes traduisibles ajoutées (msgid FR) : 10. Le workflow i18n est à lancer.

---

## Comment tester (a la main) / Manual test
### Test 1 — visiteur non connecté, e-mail déjà validé
1. Se déconnecter. Ouvrir un événement avec un tarif gratuit.
2. Réserver avec `admin@admin.com` (compte actif).
3. Attendu : retour sur la page de l'événement, UN seul toast « Réservation reçue ! Vos billets arrivent par e-mail. ». Le mail avec les billets arrive.

### Test 2 — visiteur connecté
1. Se connecter, réserver un billet gratuit.
2. Attendu : « Mes réservations », toast « Réservation validée ! … ».

### Test 3 — nouvel e-mail
1. Déconnecté, réserver avec un e-mail jamais utilisé.
2. Attendu : le panneau affiche « Merci beaucoup pour votre réservation ! » et les phrases qui suivent, dont « L'expéditeur sera <adresse> » (`DEFAULT_FROM_EMAIL`, sinon `EMAIL_HOST_USER`).

### Test 4 — panier désactivé
1. Admin → un événement → section « Publier » → cocher « Désactiver le panier ».
2. Connecté, avec un panier déjà non vide : ouvrir le formulaire de réservation de cet événement.
3. Attendu : un seul bouton « Payer maintenant », aucun bouton « Ajouter au panier ».
4. Déconnecté : un seul bouton « Envoyer la demande », pas de « Connectez-vous pour ajouter au panier ».
5. Décocher : les boutons panier reviennent.

### Verifs DB / Playwright
- `make test ARGS="tests/pytest/test_reservation_gratuite_redirection.py tests/pytest/test_panier_session.py"` → 77 passed.
