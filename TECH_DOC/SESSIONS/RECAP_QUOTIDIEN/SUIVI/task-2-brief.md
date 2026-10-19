### Tâche 2 : `annulee_le` posé à chaque annulation

**Fichiers :**
- Modifier : `BaseBillet/models.py` — `Reservation.cancel_and_refund_resa` (vers la ligne 3633) et `Reservation.cancel_and_refund_ticket` (vers la ligne 3807, le `save(update_fields=["status"])` devient `update_fields=["status", "annulee_le"]`)
- Modifier : `booking/models.py` — `Booking.cancel_and_refund_booking` (vers la ligne 765)
- Modifier : `BaseBillet/views.py` — l'action `cancel` de l'annulation d'adhésion par un admin (vers la ligne 5959, `membership.status = Membership.ADMIN_CANCELED`)
- Modifier : `Administration/admin/resources.py` — **ajouter** `BookingAdmin.save_model` (il n'existe pas encore)
- **Ne pas toucher** : `BaseBillet/signals.py` (`activator_free_reservation` : annulation automatique d'une réservation gratuite sur un événement devenu complet), `ApiBillet/views.py` (arrêt du renouvellement d'une adhésion)
- Test : classe `TestAnnuleeLe`

**Interfaces — consomme :** les champs de la tâche 1. **Produit :** `annulee_le` fiable sur les trois modèles.

`BookingAdmin.save_model(self, request, obj, form, change)` : si `change`, que `"status" in form.changed_data`, que `obj.status in (Booking.ADMIN_CANCELED, Booking.USER_CANCELED)` et que `obj.annulee_le is None` → `obj.annulee_le = timezone.now()` ; puis `super().save_model(...)`.

- [ ] **Étape 1 : tests qui échouent**
  - `test_annuler_une_reservation_pose_annulee_le` : `reservation.cancel_and_refund_resa(annulation_par_l_admin=True)` sur une réservation gratuite à `moment` → `annulee_le == moment`.
  - `test_annuler_le_dernier_billet_pose_annulee_le` : `cancel_and_refund_ticket` sur l'unique billet → `annulee_le == moment`.
  - `test_annuler_un_booking_pose_annulee_le` : `cancel_and_refund_booking()` → `annulee_le == moment`, `status == Booking.USER_CANCELED`.
  - `test_annuler_un_booking_dans_l_admin_pose_annulee_le` : `BookingAdmin(Booking, staff_admin_site).save_model(request, booking, form, change=True)` (`staff_admin_site` : `Administration/admin/site.py`) avec un `form` factice dont `changed_data == ["status"]` et `booking.status = Booking.ADMIN_CANCELED` → `annulee_le == moment`.
  - `test_annuler_une_adhesion_par_l_admin_pose_annulee_le` : vue `MembershipMVT.cancel` (`BaseBillet/views.py`), URL `reverse("membership_mvt-cancel", kwargs={"pk": adhesion.pk})` = `/memberships/<uuid>/cancel/`. Admin : `creer_utilisateur()` puis `admin.client_admin.add(self.tenant)` et `client.force_login(admin)` (permission `TenantAdminPermission` : admin du lieu, actif, humain). POST `{"with_credit_note": "0"}` sur une adhésion **sans** ligne payée (sinon `moyen_rembourse` est exigé) → réponse `HX-Redirect`, `annulee_le == moment`.
  - `test_l_annulation_automatique_d_une_reservation_gratuite_ne_pose_pas_annulee_le` (documente la ligne « Non » de la spec §3.4) : utilisateur inactif ; `Event(jauge_max=0)` ; `Reservation(status=FREERES, to_mail=True, user_commande=utilisateur)` + un `Ticket` ; `Reservation.objects.filter(pk=…).update(datetime=<il y a 1 h>)` ; puis `utilisateur.is_active = True; utilisateur.save()` → `status == CANCELED` **et** `annulee_le is None`.
  - `test_l_arret_du_renouvellement_ne_pose_pas_annulee_le` : le chemin de `ApiBillet/views.py` (`membership.status = Membership.CANCELED`) → `annulee_le is None`.
- [ ] **Étape 2 : échec vérifié.**
- [ ] **Étape 3 : implémenter** — `self.annulee_le = timezone.now()` juste à côté de chaque `status = …CANCELED` listé.
- [ ] **Étape 4 : PASS**, puis relancer les tests existants des annulations : `tests/pytest/test_avoirs_ecrivent_la_vente.py`, `tests/pytest/test_cancel_subscription.py`, et `rg -l "cancel_and_refund" tests/pytest booking/tests` → tous verts.
- [ ] **Étape 5 : commit suggéré** : `feat(recap): annulee_le posé à chaque annulation`.

---

