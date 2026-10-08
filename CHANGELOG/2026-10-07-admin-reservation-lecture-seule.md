# Admin : fiche réservation en lecture seule, invitations root seulement / Admin: read-only booking page, root-only invitations

**Date :** 2026-10-07
**Migration :** Non

## Resume / Summary

**Quoi / What :** sur la page de modification d'une réservation (admin), tous les champs sont
en lecture seule : statut, personne qui réserve, évènement, options, `to_mail`, `mail_send`,
`mail_error`. La page d'ajout ne change pas.
/ On the booking change page, every field is read-only. The add page is unchanged.

**Pourquoi / Why :** le champ « Personne qui réserve » (`user_commande`) était une liste
déroulante de TOUS les utilisateurs de l'instance (`AuthBillet` est en SHARED_APPS). En prod,
la page mettait très longtemps à s'ouvrir, et un admin de lieu voyait les emails des
utilisateurs des autres lieux.
/ The buyer field rendered a select of every user of the instance: very slow page in
production, and a venue admin could see other venues' user emails.

**Même souci ailleurs / Same issue elsewhere :**
- Réservations de ressources (`BookingAdmin`) : le champ `user` passe en lecture seule.
  / Resource bookings: `user` is read-only.
- Invitations d'onboarding (`OnboardInvitationAdmin`) : réservées au root. La table est commune
  à tous les lieux (SHARED_APPS) et l'admin ne filtrait pas par lieu : un admin de lieu voyait
  les invitations de tous les lieux, et pouvait en créer au nom de n'importe quel lieu.
  / Onboarding invitations: root only (shared table, no tenant filter: cross-venue leak).

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin_tenant.py` | `ReservationAdmin.get_readonly_fields` : tous les champs en lecture seule quand `obj` existe |
| `tests/pytest/test_reservation_admin_envoi_mail.py` | + `test_aucun_champ_modifiable_sur_la_page_de_modification` |
| `Administration/admin/resources.py` | `BookingAdmin.readonly_fields = ["user"]` |
| `onboard/admin.py` | `OnboardInvitationAdmin` : 4 permissions en `RootPermissionWithRequest` |

---

## Comment tester (a la main) / Manual test

### Test 1 — page de modification
1. Admin → Réservations → ouvrir une réservation.
2. La page s'ouvre vite. Aucun champ n'est modifiable. L'email de l'acheteur s'affiche en texte.
3. Les boutons « Renvoyer les billets » / « Valider et envoyer par mail » marchent toujours.

### Test 2 — page d'ajout
1. Admin → Réservations → Ajouter.
2. Le formulaire d'ajout (email, tarif, quantité, moyen de paiement) est inchangé.

### Test 3 — réservation de ressource
1. Admin → Réservations de ressources → ouvrir une ligne (`/admin/booking/booking/`).
2. Le champ « user » s'affiche en texte, pas en liste déroulante.

### Test 4 — invitations d'onboarding
1. Connecté en admin de lieu (non superuser) : `/admin/onboard/onboardinvitation/` → accès refusé.
2. Connecté en root (superuser) : la liste s'affiche.

### Test automatique
```bash
docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/test_reservation_admin_envoi_mail.py -q
```
