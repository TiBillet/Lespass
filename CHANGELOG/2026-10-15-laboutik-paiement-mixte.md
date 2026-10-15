# Paiement mixte à la caisse / Split payment at the POS

**Date :** 2026-10-15
**Migration :** Non

## Resume / Summary
**Quoi / What :** Nouvelle tuile MIXTE dans le choix du moyen de paiement de LaBoutik. Elle ouvre un écran de répartition (pavé numérique, une ligne par moyen, « reste à répartir ») pour encaisser un panier avec plusieurs moyens : espèces, CB, chèque. `payer()` accepte `moyen_paiement=mix` et écrit un `Reglement` par moyen sur la vente.
/ New MIXED tile in the POS payment choice. It opens a split screen (keypad, one row per method, "remaining") to collect a cart with several methods: cash, card, cheque. `payer()` accepts `moyen_paiement=mix` and writes one `Reglement` per method on the sale.

**Pourquoi / Why :** Un client paie souvent une partie en espèces et le reste en CB. Le modèle `Vente` acceptait déjà plusieurs règlements, mais la caisse n'en écrivait qu'un.
/ Customers often pay part in cash and the rest by card. The `Vente` model already accepted several payments; the POS wrote only one.

Limites de cette version / Limits of this version :
- pas de cashless dans le mix (TODO dans `MOYENS_DU_PAIEMENT_MIXTE`) ;
- pas de rendu de monnaie sur la part espèces (le caissier saisit le montant exact) ;
- tuile absente pour un panier gratuit, un retour de consigne, un panier en points ou un panier avec recharge.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/views.py` | `MOYENS_DU_PAIEMENT_MIXTE`, `_moyens_du_paiement_mixte()`, `RepartitionPaiementMixteSerializer`, action `repartir`, aiguillage `mix` dans `_executer_paiement`, paramètre `repartition_en_centimes` sur `_payer_par_carte_ou_cheque` et `_regler_et_encaisser_la_vente_de_caisse`, flag `paiement_mixte_possible` dans les deux contextes des tuiles |
| `laboutik/templates/laboutik/partial/_tuiles_paiement.html` | Tuile MIXTE (remplace le brouillon MIX en mode gérant) |
| `laboutik/templates/laboutik/partial/hx_paiement_mixte.html` | Nouveau : écran de répartition |
| `laboutik/static/css/paiement_mixte.css` | Nouveau : style des lignes de répartition |
| `tests/pytest/test_paiement_mixte.py` | Nouveau : 10 tests |

---

## Comment tester (a la main) / Manual test

### Test 1 — scénario nominal
1. Point de vente qui accepte espèces + CB (+ chèque).
2. Ajouter des articles pour 25 € → VALIDER.
3. La tuile **MIXTE** apparaît à côté d'ESPÈCE / CB / CHÈQUE. La toucher.
4. L'écran « Paiement mixte » affiche 25,00 € et une ligne par moyen ; la 1re ligne (espèce) est active (bord vert).
5. Taper `10` au pavé → la ligne espèce affiche 10 € ; « Reste à répartir » = 15,00 €. VALIDER est grisé.
6. Toucher la ligne CB, puis « Mettre le reste ici » → CB = 15,00 € ; reste = 0,00 € ; VALIDER s'active.
7. VALIDER → écran de succès « Payé en paiement mixte (espèce 10.00 € · carte bancaire 15.00 €) ».
8. Admin → Ventes : la vente a 2 règlements (CASH 1000, CC 1500).

### Test 2 — cas limites
- Montants qui dépassent le total : le reste passe en rouge, VALIDER reste grisé.
- Un seul moyen rempli (25 € en espèces) : VALIDER reste grisé.
- PV qui n'accepte qu'un moyen : pas de tuile MIXTE.
- Panier avec retour de consigne, recharge, ou en points : pas de tuile MIXTE.
- Annuler / croix / fond : retour au choix du moyen de paiement.
- Tiroir-caisse Sunmi : s'ouvre si une part est en espèces.

### Verifs DB / Playwright
- `poetry run pytest tests/pytest/test_paiement_mixte.py -v` (somme ≠ total, un seul moyen, moyen non accepté, montant négatif → 400 sans écriture).
- Scénario Playwright à écrire : saisie au pavé, bouton « Mettre le reste ici », activation de VALIDER (`data-testid` : `paiement-btn-mixte`, `mixte-ligne-<code>`, `mixte-reste`, `mixte-btn-reste`, `mixte-btn-valider`).
