# CHANTIER 04 — Vague 4 : specs adhésions migrés (agents Sonnet)

Statut : ✅ TERMINÉ (2026-06-11)

## Résultat : 11/11 verts (22 tests Python)

| Spec TS | Fichier Python | Tests | Verdict |
|---|---|---|---|
| 03-memberships | `test_memberships_admin_create.py` | 1 | ✅ |
| 04-membership-recurring | `test_membership_recurring_create.py` | 1 | ✅ premier coup |
| 05-membership-validation | `test_membership_validation_product.py` | 1 | ✅ premier coup |
| 06-membership-amap | `test_membership_amap.py` | 1 | ✅ premier coup |
| 07-fix-solidaire | `test_membership_fix_solidaire.py` | 1 | ✅ premier coup |
| 14-manual-validation | `test_membership_manual_validation.py` | 1 | ✅ premier coup |
| 17-free-price-multi | `test_membership_free_price_multi.py` | 4 | ✅ premier coup (Stripe réel ×4) |
| 22-recurring-cancel | `test_membership_recurring_cancel.py` | 1 | ✅ |
| 27-dynamic-form-full-cycle | `test_membership_dynamic_form_full_cycle.py` | 7 | ✅ premier coup |
| 36-sepa-duplicate-protection | `test_sepa_duplicate_protection.py` | 3 | ✅ premier coup |
| 43-manual-validation-stripe | `test_membership_manual_validation_stripe.py` | 1 | ✅ (vrai paiement Stripe) |

Les 11 specs TS sont supprimés. **Suite TS restante : 3 specs** (25, 29, 40 = vague 5).

## Coût

~592k tokens Sonnet pour 11 specs (≈54k/spec). Évolution :
vague 2 = 115k/spec (Fable ×2 agents) → vague 3 = 70k/spec → vague 4 = 54k/spec.
La cheat-sheet enrichie à chaque vague élimine les erreurs répétées
(8 specs sur 11 verts du premier coup).

## Pièges/découvertes notables des agents

1. **Proxy admin** : « Adhésion à validation sélective » vit sous le proxy
   `MembershipProduct`, invisible dans la changelist `Product` générique —
   navigation directe `/admin/BaseBillet/price/<uuid>/change/` via django_shell.
2. **L'API adhésion crée les users avec `is_active=False`** → activer via
   django_shell avant `login_as` (même piège que account-states en vague 2).
3. **`Paiement_stripe.total` est une méthode**, pas un champ — et la relation
   membership↔paiement est M2M (`m.stripe_paiement.add(p)`).
4. **Bouton save admin Unfold** : cibler `[name="_save"]`, pas
   `button:has-text("Save")` (texte traduit).
5. **Labels FR des statuts LigneArticle** : VALID s'affiche « Confirmé ».

## ⚠️ Constat interop V1 révélé par les tests (2026-06-11)

Les ventes d'adhésions de test déclenchent des **500 sur LaBoutik V1**
(`/api/salefromlespass`, `APIcashless/validator.py:181`) : le produit créé à
la volée côté Lespass n'existe pas comme `MoyenPaiement` chez LaBoutik et le
`.get()` n'est pas protégé. Côté Lespass c'est bénin (retry borné puis abandon
dans `send_sale_to_laboutik`), MAIS :

1. En prod V1, une adhésion vendue avant la synchro produit → vente **jamais
   transmise à la caisse** (`sended_to_laboutik=False`, aucune reprise).
2. Le fix du crash appartient au repo LaBoutik (attraper `DoesNotExist`,
   répondre 400 explicite). Amélioration possible côté Lespass : cron de
   reprise des lignes `sended_to_laboutik=False`.
3. Cette interop HTTP disparaît en V2 (fedow_core).

## Validation finale

- Suite E2E Python complète (~32 fichiers) relancée après la vague — voir
  résultat dans le récap de session.
- Vague 5 restante : 25-product-duplication-complex, 29-event-quick-create,
  40-explorer-markers-per-pa.
