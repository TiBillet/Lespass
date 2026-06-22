# Reproduction des tests Fedow + LaBoutik dans Lespass V1

Objectif : reproduire dans Lespass V1 (branche `main-fedow-import`) les scénarios couverts par
les tests de `../Fedow` et `../LaBoutik`.

## Constat d'architecture

- Les **51 tests Fedow** testent **l'API REST du serveur Fedow standalone** (endpoints `/card/`,
  `/wallet/`, `/transaction/`…). Lespass V1 a `fedow_core` en **version locale** (modèles + services,
  **pas l'API REST**) → ces tests **ne sont pas reproductibles littéralement**. La logique
  équivalente est couverte par `test_fedow_core.py` + `test_verify_transactions.py` + `test_integrity_hmac.py`.
- Le **méga-test LaBoutik** teste le POS V1 (appels HTTP à Fedow). Dans Lespass V2 le POS est
  intégré → les **scénarios** sont transposés via les tests POS de lespass-main (même architecture V2).

## Méthode retenue

Les tests sont **copiés depuis `../lespass-main`** (V2, même architecture que Lespass V1, source du
portage C-A) plutôt que réécrits depuis Fedow/LaBoutik V1.

## Résultat

**Couverture : 271 → 541 tests pytest, 0 échec.** ~26 fichiers copiés et passants :
`test_fedow_core`, `test_pos_models`, `test_pos_views_data`, `test_pos_vider_carte`,
`test_card_refund_service`, `test_billetterie_pos`, `test_paiement_especes_cb`, `test_cloture_caisse`,
`test_cloture_enrichie`, `test_cloture_export`, `test_inventaire`, `test_verify_transactions`,
`test_integrity_hmac`, `test_scan_qr_carte_v2`, `test_profils_csv_comptable`, `test_rapport_temps_reel`,
`test_caisse_navigation`, `test_asset_recharge_signal`, `test_stock_negatif`, `test_stock_visuel_pos`,
`test_menu_ventes`, `test_afficher_poids`, `test_poids_mesure`, `test_bank_transfer_service`,
`test_corrections_fond_sortie`, `test_export_comptable`.

## ⚠️ Fichiers à reprendre (NON copiés — échouent dans Lespass V1)

### Cause 1 — i18n (`LANGUAGE_CODE`)
lespass-main : `LANGUAGE_CODE='en'` ; Lespass V1 : `'fr'`. Les tests cherchent les strings EN
(« Payment successful »…) que le `.po` EN de Lespass V1 ne traduit pas (refactor i18n FR).
→ **`test_paiement_cashless`, `test_retour_carte_recharges`, `test_cascade_nfc`** (+ assertions de string).
**À faire (mainteneur)** : compiler les traductions EN des strings POS, OU adapter les assertions en FR.

### Cause 2 — features non portées en S6 (erreurs de collection / d'exécution)
- `test_panier_session`, `test_panier_mvt`, `test_panier_batch` — panier session V2
- `test_commande_model`, `test_commande_service`, `test_commande_post_save_paid` — modèle Commande
- `test_refill_service`, `test_refill_serializer`, `test_refill_webhook`,
  `test_traiter_paiement_cashless_refill` — recharge en ligne (CASHLESS_REFILL non porté, cf. ROADMAP A3)
- `test_mode_ecole` (`SaleOrigin.LABOUTIK_TEST` absent), `test_tokens_table_v2`,
  `test_transactions_table_v2`, `test_peut_recharger_v2`, `test_rapport_billetterie_service`,
  `test_archivage_fiscal`, `test_rapport_comptable`, `test_laboutik_securite_a11y`,
  `test_identification_unifiee`
→ **À faire** : porter la feature concernée OU adapter/retirer le test selon le scope S6.

## ⚠️ Effets de bord de la session (env dev)
- **Plan comptable chargé** : `charger_plan_comptable --schema=lespass --jeu=bar_resto` (16 comptes,
  9 mappings) + compte `41920000` (avances fédérées) + mapping `SF` → ce compte.
- **Crédits FED/TLF de test** sur jturbeaux (Fedow dev + fedow_core local) — remis à 0, mais
  **drift Fedow dev** résiduel → `reconcile_tokens` recommandé.
- Carte `FEDTST01`, produit `[TEST] Billet Concert FED` (archivé) en base.

## Piège rencontré (pour PIEGES.md)
`pytest -p no:cacheprovider` casse les tests qui utilisent `request.config.cache` (cache pytest
pour partager des données entre tests ordonnés : `test_event_*`, `test_crowd_*`). **Ne jamais
lancer la suite avec `-p no:cacheprovider`** — 93 « faux » échecs + 78 « erreurs » disparaissent sans.
