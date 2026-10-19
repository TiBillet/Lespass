# Tâche 2 — annulee_le posé à chaque annulation (DONE)

## Fait
- BaseBillet/models.py : `cancel_and_refund_resa` pose `self.annulee_le = timezone.now()` avant `status = CANCELED` ; `cancel_and_refund_ticket` pose `annulee_le` et `save(update_fields=["status", "annulee_le"])`.
- booking/models.py : `cancel_and_refund_booking` pose `annulee_le`.
- BaseBillet/views.py : `MembershipMVT.cancel` pose `annulee_le` dans la transaction.
- Administration/admin/resources.py : import `timezone` + `BookingAdmin.save_model` (change, "status" changé, statut annulé, annulee_le vide).
- Non touchés : signals.py, ApiBillet/views.py. Commentaires FALC FR + EN à chaque endroit.
- Test : classe `TestAnnuleeLe` (6 tests) dans tests/pytest/test_recap_quotidien.py.
  Le test « arrêt du renouvellement » est supprimé (MemoryError : MagicMock sur stripe/RootConfiguration), remplacé par une phrase dans la docstring de la classe (décision du coordinateur).

## TDD
Rouge (avant code) : 5 échecs sur 6, `test_l_annulation_automatique…` passait déjà (ligne « Non »).
Vert : `ulimit -v 8000000; pytest tests/pytest/test_recap_quotidien.py -v` -> 10 passed.
Ajustement : la vue cancel répond 204 + HX-Redirect (pas 200).

## Mutations (ligne retirée -> test rouge -> remise)
- resa (models.py:3647) -> test_annuler_une_reservation_pose_annulee_le rouge
- ticket (models.py:3824) -> test_annuler_le_dernier_billet rouge ; `update_fields=["status"]` seul -> rouge aussi
- booking (booking/models.py:770) -> test_annuler_un_booking rouge
- vue adhésion (views.py:5961) -> test_annuler_une_adhesion_par_l_admin rouge
- save_model (resources.py:193) -> test_annuler_un_booking_dans_l_admin rouge
Code restauré ; 6/6 verts à la fin.

## Tests existants (tous sous ulimit -v 8000000), verts
test_avoirs_ecrivent_la_vente 80, test_cancel_subscription 12, test_stripe_refund 19, test_caracterisation_annulations 5, test_stripe_reel_remboursement 4, test_mail_annulation_booking 1, test_admin_vente 49, test_lecteurs_montants_entiers 60.

## Commit suggéré
feat(recap): annulee_le posé à chaque annulation

## Doutes
Aucun chaîne `_()` ajoutée. Pas de ruff lancé. Aucune migration.
