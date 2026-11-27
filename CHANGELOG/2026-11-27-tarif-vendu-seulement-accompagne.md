# Tarif « Ne peut pas être vendu seul » / Accompanied-only price

**Date :** 2026-11-27
**Migration :** Oui — `BaseBillet/migrations/0245_tarif_vendu_seulement_accompagne.py`
(`docker exec lespass_django poetry run python manage.py migrate_schemas --executor=standard`)

## Resume / Summary
**Quoi / What :** Un tarif de billet ou de pass peut être coché « Ne peut pas être vendu seul »
(exemple : un tarif enfant). Il s'achète seulement avec au moins un billet d'un tarif non coché,
pour le même événement, dans le même achat. Un pass compte sur chacun de ses événements. Contrôlé
au paiement du panier et en réservation directe ; ni en caisse, ni par l'API v2.
/ A ticket or pass price can be "accompanied-only" (e.g. a child price): it needs at least one
non-accompanied ticket for the same event in the same purchase. Checked at cart checkout and in
direct booking; not at the register nor through API v2.

**Pourquoi / Why :** Empêcher qu'un tarif réservé aux accompagnés (enfant, pass enfant) soit
acheté sans adulte.
/ Prevent an accompanied-only price (child, child pass) from being bought without an adult.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/models.py` | `Price.vendu_seulement_accompagne` |
| `BaseBillet/migrations/0245_tarif_vendu_seulement_accompagne.py` | Migration du champ |
| `BaseBillet/services_panier.py` | `tarif_vendu_seul_dans_l_achat` (la règle, par événement), `message_de_tarif_vendu_seul`, `lignes_d_achat_du_panier` (un pass donne une ligne par événement) |
| `BaseBillet/services_commande.py` | Contrôle au paiement du panier (`materialiser`), après la revalidation : on peut ajouter l'enfant avant l'adulte |
| `BaseBillet/validators.py` | Contrôle en réservation directe (`ReservationValidator.validate`), seulement pour le site : ni l'admin, ni l'API v2, ni la caisse |
| `Administration/admin/products.py` | La case dans le tarif d'un produit billet et d'un pass |
| `tests/pytest/test_tarif_vendu_seulement_accompagne.py` | Nouveau : 7 tests |

### Pas encore fait / Not done yet
- Annulation en cascade : quand tous les billets non cochés d'un achat sont annulés pour un
  événement, annuler aussi les billets cochés de cet achat sur cet événement (client et admin),
  et refuser si l'un d'eux est scanné.

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

### Test 3 — tests automatiques
- `docker exec lespass_django poetry run pytest tests/pytest/test_tarif_vendu_seulement_accompagne.py -q`
- Attendu : 7 passed.
