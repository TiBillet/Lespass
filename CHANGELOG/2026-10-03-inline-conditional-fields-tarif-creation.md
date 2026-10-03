# Champs conditionnels des tarifs ajoutés en création de produit / Conditional fields on prices added while creating a product

**Date :** 2026-10-03
**Migration :** Non

## Resume / Summary
**Quoi / What :** les règles conditionnelles des inlines tarif (`iteration` caché tant que « paiement récurrent » n'est pas coché, recharge Fedow, contenance/asset en caisse…) s'appliquent maintenant aux tarifs ajoutés avec « Ajouter un autre », donc aussi sur la page de création d'un produit (issue #408).
/ Inline price conditional rules now apply to rows added with "Add another", including on the product creation page (issue #408).

**Pourquoi / Why :** le script détectait les nouvelles lignes avec un `MutationObserver` limité aux enfants directs de `#prices-group`. Unfold insère la ligne plusieurs niveaux plus bas : elle n'était jamais configurée. Le script écoute désormais l'événement `formset:added` émis par Django.
/ The script watched only direct children of `#prices-group`, while Unfold nests new rows deeper. It now listens to Django's `formset:added` event.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/static/admin/js/inline_conditional_fields.js` | `MutationObserver` remplacé par un écouteur `formset:added` filtré sur le préfixe du formset |
| `tests/e2e/test_admin_tarif_champs_conditionnels_creation.py` | Nouveau test E2E : tarifs ajoutés sur la page de création d'une adhésion |
| `tests/PIEGES.md` | Piège 65 complété : `formset:added` plutôt qu'un `MutationObserver` sous Unfold |

---

## Comment tester (a la main) / Manual test
### Test 1 — création d'une adhésion
1. Admin → Adhésions → Ajouter un produit d'adhésion.
2. Cliquer sur « Ajouter un autre tarif ».
3. Attendu : « Itération » et « Engagement » sont cachés ; jeton et montant de recharge aussi.
4. Cocher « Paiement récurrent » → « Itération » apparaît (animation). Saisir 3 → « Engagement » apparaît.
5. Décocher « Paiement récurrent » → les deux disparaissent.

### Test 2 — plusieurs tarifs
1. Sur la même page, ajouter un 2e tarif.
2. Activer la recharge Fedow sur le 2e uniquement → seul le 2e affiche jeton et montant.

### Test 3 — non-régression en modification
1. Ouvrir une adhésion existante avec des tarifs : les règles s'appliquent comme avant.
2. Ajouter un tarif depuis cette page : les règles s'appliquent aussi à la nouvelle ligne.
3. Produit de caisse (POS) : la section Stock (formulaire principal) et « contenance »/« asset » des tarifs ajoutés se comportent correctement.

### Verifs DB / Playwright
- Aucune donnée en base (correctif 100 % JS).
- `pytest tests/e2e/test_admin_tarif_champs_conditionnels_creation.py` (2 tests).
