# Tarif « Ne peut pas être vendu seul » / Accompanied-only price

**Date :** 2026-11-27
**Migration :** Oui — `BaseBillet/migrations/0245_tarif_vendu_seulement_accompagne.py`
(`docker exec lespass_django poetry run python manage.py migrate_schemas --executor=standard`)

## Resume / Summary
**Quoi / What :** Un tarif de billet ou de pass peut être coché « Ne peut pas être vendu seul »
(exemple : un tarif enfant). Il s'achète seulement avec au moins un billet d'un tarif non coché,
pour le même événement, dans le même achat. Un pass compte sur chacun de ses événements. Contrôlé
au paiement du panier et en réservation directe ; ni en caisse, ni par l'API v2.
À l'annulation (client ou admin), quand une réservation n'a plus aucun billet d'un tarif non
coché, ses billets cochés sont annulés avec, en un seul remboursement Stripe ; refusé si l'un
d'eux est déjà scanné.
/ A ticket or pass price can be "accompanied-only" (e.g. a child price): it needs at least one
non-accompanied ticket for the same event in the same purchase. Checked at cart checkout and in
direct booking; not at the register nor through API v2. Cancelling the last companion
cancels the accompanied tickets too (one Stripe refund), refused if one is scanned.

**Pourquoi / Why :** Empêcher qu'un tarif réservé aux accompagnés (enfant, pass enfant) soit
acheté sans adulte.
/ Prevent an accompanied-only price (child, child pass) from being bought without an adult.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/models.py` | `Price.vendu_seulement_accompagne` ; cascade : `billets_annules_ensemble` (pass + billets cochés restés seuls), `verifier_qu_aucun_billet_lie_n_est_scanne` (remplace `verifier_qu_aucun_billet_du_pass_n_est_scanne`), `lignes_stripe_des_billets` (renommée, répartit plusieurs billets du même tarif), `reservations_concernees_par_l_annulation` (montant du mail), `cancel_and_refund_ticket` et `cancel_and_refund_resa` |
| `BaseBillet/migrations/0245_tarif_vendu_seulement_accompagne.py` | Migration du champ |
| `BaseBillet/services_panier.py` | `tarif_vendu_seul_dans_l_achat` (la règle, par événement), `message_de_tarif_vendu_seul`, `lignes_d_achat_du_panier` (un pass donne une ligne par événement) |
| `BaseBillet/services_commande.py` | Contrôle au paiement du panier (`materialiser`), après la revalidation : on peut ajouter l'enfant avant l'adulte |
| `BaseBillet/validators.py` | Contrôle en réservation directe (`ReservationValidator.validate`), seulement pour le site : ni l'admin, ni l'API v2, ni la caisse |
| `Administration/admin/products.py` | La case dans le tarif d'un produit billet et d'un pass |
| `tests/pytest/test_tarif_vendu_seulement_accompagne.py` | Nouveau : 14 tests (achat et cascade) |

### Note
- Un billet seul scanné reste annulable par l'admin (comme avant) ; seuls les billets annulés
  *avec* lui sont contrôlés. Un mail est envoyé pour le billet ou la réservation demandée,
  avec le montant total rendu (cascade comprise).

---

## Comment tester (a la main) / Manual test

### Test 1 — achat refusé puis accepté
1. Admin > produit billet d'un événement : ajouter un tarif « Moins de 12 ans », cocher
   « Ne peut pas être vendu seul ».
2. Sur le site, mettre seulement un billet « Moins de 12 ans » au panier, payer : refusé avec
   « Le tarif « Moins de 12 ans » ne peut pas être acheté seul : ajoutez un billet d'un autre
   tarif pour « … ». ».
3. Ajouter un billet plein tarif du même événement, payer : accepté.
4. « Payer maintenant » (réservation directe) avec seulement le tarif enfant : même refus.

### Test 2 — avec un pass
1. Un pass plein tarif samedi + dimanche, et le tarif enfant sur le samedi : enfant + pass au
   panier, accepté (le pass accompagne le samedi).
2. Cocher « Ne peut pas être vendu seul » sur le tarif du pass, avec un adulte seulement le
   samedi : refusé, le dimanche n'a pas d'accompagnant.

### Test 3 — annulation en cascade
1. Acheter 1 plein tarif + 1 « Moins de 12 ans » (payé par Stripe).
2. Mon compte : annuler le billet plein tarif. Le billet enfant est annulé aussi, un seul
   remboursement Stripe (les deux montants), le mail annonce le total.
3. Recommencer avec 2 plein tarif + 1 enfant : annuler un adulte laisse l'enfant valide.
4. Admin : marquer le billet enfant scanné, puis annuler le seul adulte : refusé avec
   « Un billet « Moins de 12 ans » de cet achat a déjà été scanné … ».

### Test 4 — tests automatiques
- `docker exec lespass_django poetry run pytest tests/pytest/test_tarif_vendu_seulement_accompagne.py -q`
- Attendu : 14 passed.
