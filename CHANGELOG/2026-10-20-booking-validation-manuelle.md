# Réservation de ressource à validation manuelle / Resource booking with manual validation

**Date :** 2026-10-20
**Migration :** Oui — `booking 0009_booking_motif_du_refus` (fiche D) : nouveau champ `Booking.motif_du_refus`, texte d'aide du statut.

Spec : `TECH_DOC/SESSIONS/BOOKING/SPEC.md`. Chantier découpé en fiches A → E.

## Resume / Summary
**Quoi / What :** un tarif de ressource peut être « à validation manuelle ». Un clic sur un créneau crée alors une demande, que l'équipe valide ou refuse. Ensuite, la personne paie, ou reçoit une confirmation si c'est gratuit.
/ A resource price can require manual validation: a slot click creates a request that the team accepts or refuses, then the person pays (or is confirmed if free).

**Pourquoi / Why :** certains lieux veulent choisir qui réserve, comme pour les adhésions à validation manuelle (caisse sociale alimentaire).
/ Some venues want to choose who books, like manually validated memberships.

### Fiche A — la demande (faite)
| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin/products.py` | `ResourcePriceInline` : champ `manual_validation` dans les tarifs d'une ressource, avec un texte d'aide propre aux ressources |
| `Administration/admin/prices.py` | `PriceChangeForm` : le champ n'est plus caché pour un tarif de ressource |
| `booking/booking_engine.py` | `validate_new_booking` : tarif à validation manuelle → booking `ADMIN_WAITING`, vente ouverte, ligne `CREATED`, ni Stripe ni encaissement ; `ValueError` si appelé avec une commande du panier. Bloc gratuit extrait dans `confirmer_booking_gratuit`. `get_existing_bookings_for_resource` : une demande en attente occupe le créneau |
| `tests/pytest/test_booking_validation_manuelle.py` | 8 tests (demande, montant, prix libre, créneau retenu, garde-fou panier, gratuit inchangé, admin) |

### Fiche B — le parcours de la personne (faite)
| Fichier / File | Changement / Change |
|---|---|
| `booking/templates/booking/partials/book_form.html` | chaque tarif porte `data-manual-validation` ; un tarif à validation manuelle affiche « Envoyer la demande » et cache « Payer maintenant » et les boutons du panier, même quand le panier n'est pas vide |
| `booking/views.py` | `_book_post` : une demande redirige vers « Mes réservations » (`?new=<pk>`) avec un message, et lance les mails admin et personne après le commit. `cancel_confirm` : accepte une demande en attente, sans tenir compte du délai d'annulation |
| `booking/models.py` | `Booking.est_une_demande_non_payee`, `Booking.annulation_possible` ; `cancel_and_refund_booking` : une demande non payée annule sa vente et ses lignes, « Rien n'a été débité » |
| `booking/tasks.py` | nouvelles tâches `send_booking_request_admin`, `send_booking_request_user` ; `send_booking_cancellation_user(…, demande_non_payee=False)` |
| `BaseBillet/views.py` | « Mes réservations » et l'accueil du compte montrent les demandes en attente |
| `pages/templates/pages/{V2,classic}/vues/compte/bookings.html`, `pages/templates/pages/V2/vues/compte/index.html` | badge « Demande en attente de validation » ; bouton d'annulation selon `annulation_possible` |
| `tests/pytest/test_booking_validation_manuelle.py` | 8 tests de plus (formulaire, réponse et mails, compte, retrait après le délai, délai maintenu pour une réservation confirmée, trois mails) |

### Fiche C — le paiement d'une demande validée (faite)
| Fichier / File | Changement / Change |
|---|---|
| `booking/views.py` | nouvelle action `pay` (`GET /booking/<pk>/pay/`) : connexion exigée, booking de la personne seulement (sinon 404). Déjà payé → page d'info ; pas validé → 409 ; session Stripe ouverte → réutilisée ; session terminée → « paiement en cours » ; sinon nouvelle session |
| `booking/templates/booking/views/pay_info.html` | nouvelle page d'information (déjà payée, paiement en cours, lien plus valable) |
| `booking/booking_engine.py` | `get_checkout_stripe` laisse une demande validée en `ADMIN_VALID` (le créneau reste retenu sans limite de temps) ; nouvelle `expirer_la_session_stripe_ouverte(booking)` |
| `booking/models.py` | retirer une demande validée ferme d'abord sa session Stripe ouverte |
| `BaseBillet/triggers.py` | `trigger_C` ne réactive jamais un booking `ADMIN_CANCELED` ou `USER_CANCELED` : statut inchangé + `logger.error` (Sentry), remboursement à la main |
| `pages/templates/pages/{V2,classic}/vues/compte/bookings.html` | badge « Validée — à payer » et bouton « Payer » |
| `tests/pytest/test_booking_validation_manuelle.py` | 12 tests de plus (Stripe simulé) |

### Fiche D — la décision de l'admin (faite)
| Fichier / File | Changement / Change |
|---|---|
| `booking/models.py` + migration `0009` | champ `motif_du_refus` (lecture seule dans l'admin) ; texte d'aide du statut : un changement à la main n'envoie aucun mail ; `Booking.annuler_la_demande_non_payee(statut, motif)` partagée par le retrait de la personne et le refus admin |
| `booking/views.py` | actions POST `admin_accept` (payant → `ADMIN_VALID` ; gratuit → confirmé, vente encaissée à 0 ; `renvoyer_le_lien=true` → renvoi du mail) et `admin_refuse` (→ `ADMIN_CANCELED`, motif, session Stripe fermée, vente et ligne annulées, créneau libéré). Admin du lieu seulement (403), booking verrouillé, mails après le commit |
| `booking/serializers.py` | `MotifDuRefusSerializer` (facultatif, 2000 caractères au plus) |
| `booking/tasks.py` | nouvelles tâches `send_booking_accepted_user` (bouton « Payer ma réservation » ou « Voir mes réservations ») et `send_booking_refused_user` (motif affiché échappé) |
| `Administration/admin/resources.py`, `Administration/templates/admin/booking/actions_panel.html` | panneau « Demande de réservation » en haut de la fiche d'une demande non payée : Valider, Renvoyer le lien, Copier le lien, Refuser avec motif ; information sur l'adhésion exigée par le tarif |
| `tests/pytest/test_booking_validation_manuelle.py` | 13 tests de plus |

### Fiche E — récap du matin, test navigateur, doc (faite)
| Fichier / File | Changement / Change |
|---|---|
| `Administration/recap_quotidien.py` | « Nouvelles réservations de ressources » ne compte plus les demandes ; nouvelle rubrique « Demandes de réservation en attente » (tout le stock, « dont N nouvelles hier »), lien vers la liste filtrée sur ce statut |
| `TECH_DOC/SESSIONS/RECAP_QUOTIDIEN/SPEC.md` | tableau des rubriques à jour |
| `booking/doc/tibillet-booking-presentation_fr.md` | la validation manuelle est décrite (la réservation n'est plus « toujours directe ») |
| `tests/pytest/test_recap_quotidien.py` | 3 tests de plus |
| `tests/e2e/test_booking_validation_manuelle_stripe.py` | E2E : demande → validation admin → paiement Stripe réel → « Payé » dans le compte ; demande → refus avec motif |
| `pytest.ini` | la famille `validation_manuelle` couvre aussi les créneaux |

**Déploiement :** nouvelles tâches Celery → redémarrer Celery.

**À savoir :** le filtre « À vérifier » de la liste des ventes montre toute vente en attente depuis plus d'une heure sans paiement Stripe. Une demande en attente, ou validée mais jamais payée, y restera visible. C'est voulu.

---

## Comment tester (a la main) / Manual test

### Test 1 — le drapeau dans l'admin (fiche A)
1. Admin → Ressources → ouvrir le produit d'une ressource.
2. Dans les tarifs, une case « Validation manuelle » est présente, avec son texte d'aide.
3. Ouvrir la fiche d'un tarif de ressource seul (Tarifs) : la case est visible aussi.
4. Ouvrir un tarif de billetterie : la case reste cachée.

### Test 2 — la demande retient le créneau (fiche A)
1. Cocher « Validation manuelle » sur le tarif d'une ressource d'une place.
2. Sur le site, réserver un créneau avec ce tarif : pas de redirection vers Stripe.
3. Admin → Réservations : la réservation est en « Waiting for admin validation ».
4. Revenir sur le calendrier de la ressource : le créneau est occupé.

### Test 3 — la demande côté personne (fiche B)
1. Sur le site, ouvrir le créneau d'une ressource dont le tarif est à validation manuelle.
2. Le bouton s'appelle « Envoyer la demande », avec le texte « Cette réservation doit être acceptée par l'équipe ». Les boutons du panier sont cachés.
3. Envoyer : on arrive sur « Mes réservations », avec le message « Votre demande de réservation a été envoyée » et le badge « Demande en attente de validation ».
4. Deux mails partent : « Nouvelle demande de réservation » aux admins du lieu, « Votre demande de réservation est enregistrée » à la personne.
5. Cliquer « J'annule ma réservation » : message « Votre demande est annulée. Rien n'a été débité. », mail d'annulation avec le même texte, et le créneau redevient libre. Cela marche même quand le délai d'annulation de la ressource est dépassé.

### Test 4 — payer une demande validée (fiche C, en attendant l'admin de la fiche D)
1. Faire une demande (test 3), puis la passer en « Confirmed by admin, waiting for payment » à la main dans l'admin des réservations (champ statut).
2. « Mes réservations » : badge « Validée — à payer » et bouton « Payer ».
3. Cliquer « Payer » → Stripe. Revenir en arrière sans payer : la réservation garde son badge, le créneau reste occupé (même après 30 minutes).
4. Cliquer à nouveau « Payer » : c'est la même session Stripe (même URL).
5. Payer avec la carte 4242 4242 4242 4242 : la réservation passe en « Paid by user ».
6. Rouvrir `/booking/<pk>/pay/` : page « Cette réservation est déjà payée ».

### Test 5 — l'admin décide (fiche D)
1. Faire une demande (test 3). Admin → Réservations → ouvrir la demande : panneau « Demande de réservation » en haut.
2. « Valider la demande » : la fiche se recharge en « Confirmed by admin, waiting for payment », message de confirmation ; la personne reçoit « Votre demande de réservation est acceptée » avec le bouton « Payer ma réservation ».
3. Le panneau propose maintenant « Renvoyer le lien de paiement » et « Copier le lien ».
4. Sur une autre demande : « Refuser », taper un motif, « Confirmer le refus » : statut « Cancelled », motif visible dans la fiche, mail avec le motif, le créneau redevient libre.
5. Avec un tarif gratuit à validation manuelle : « Valider » confirme tout de suite (« Email verified »), mail « Votre réservation est confirmée ».

### Test 6 — le récap du matin (fiche E)
1. Laisser une demande en attente (test 3), puis lancer le récap du lieu le lendemain.
2. Rubrique « Demandes de réservation en attente » : la demande y est, avec « dont 1 nouvelle hier ». Elle n'est pas dans « Nouvelles réservations de ressources ».
3. Le lien de la rubrique ouvre la liste des réservations filtrée sur « Waiting for admin validation ».

### Verifs automatiques
- `docker exec lespass_django poetry run pytest tests/pytest/test_booking_validation_manuelle.py -v`
- `docker exec lespass_django poetry run pytest tests/pytest/test_recap_quotidien.py -v`
- `make e2e validation_manuelle` (exige `stripe listen`)
