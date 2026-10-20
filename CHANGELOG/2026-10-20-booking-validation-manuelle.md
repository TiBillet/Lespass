# Réservation de ressource à validation manuelle / Resource booking with manual validation

**Date :** 2026-10-20
**Migration :** Non pour l'instant (fiche A). La fiche D ajoutera `booking 0009_booking_motif_du_refus`.

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

**État intermédiaire (ne pas déployer entre deux fiches) :** après la fiche A, une demande faite sur le site affiche encore « Réservation créée avec succès ». Elle n'apparaît pas dans « Mes réservations » et aucun mail ne part. La fiche B corrige cela.

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

### Verifs automatiques
- `docker exec lespass_django poetry run pytest tests/pytest/test_booking_validation_manuelle.py -v`
