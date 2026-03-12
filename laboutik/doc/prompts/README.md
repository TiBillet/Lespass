# Prompts Claude Code — Plan d'integration mono-repo v2

Chaque fichier = 1 prompt a copier-coller en debut de session Claude Code.
Un fichier = une etape = une session (ou demi-session).

## Progression

| Phase | Etape | Fichier | Statut | Tests |
|-------|-------|---------|--------|-------|
| **-1** | 1. Champs module_* | `phase-1_etape1_modeles_configuration.md` | **FAIT** | Shell Django : `Configuration.get_solo().module_billetterie` |
| **-1** | 2. Dashboard callback | `phase-1_etape2_dashboard_callback.md` | **FAIT** | Visuel : 5 cartes dans `/admin/`, data-testid OK |
| **-1** | 3. Sidebar conditionnelle | `phase-1_etape3_sidebar_conditionnelle.md` | **FAIT** | PW : `29-admin-proxy-products.spec.ts` (6 tests) |
| **0** | 1. Modeles fedow_core | `phase0_etape1_modeles_fedow_core.md` | **FAIT** | Shell : import Asset, Token, Transaction, Federation |
| **0** | 2. Services wallet | `phase0_etape2_services_wallet.md` | **FAIT** | Shell : import WalletService, TransactionService |
| **0** | 3. Admin + tests securite | `phase0_etape3_admin_tests_securite.md` | **FAIT** | pytest : 8 tests (`test_fedow_core.py`), PW : `31-admin-asset-federation.spec.ts` |
| **1** | 1. Modeles POS | `phase1_etape1_modeles_pos.md` | **FAIT** | Shell : CategorieProduct, POSProduct, Price.asset |
| **1** | 2. Admin + fixtures | `phase1_etape2_admin_fixtures.md` | **FAIT** | Admin : section "Caisse" visible, `create_test_pos_data` OK |
| **2** | 1. Caisse depuis DB | `phase2_etape1_caisse_depuis_db.md` | **FAIT** | pytest : 11 tests (`test_caisse_navigation.py`), PW : a ecrire |
| **2** | 2. Paiement especes/CB | `phase2_etape2_paiement_especes_cb.md` | **FAIT** | pytest : 7 tests (`test_paiement_especes_cb.py`), PW : a ecrire |
| **3** | 1. Paiement NFC | `phase3_etape1_paiement_nfc.md` | **FAIT** | pytest : 7 tests (`test_paiement_cashless.py`) |
| **3** | 2. Retour carte + recharges | `phase3_etape2_retour_carte_recharges.md` | A FAIRE | pytest |
| **3** | 3. Stress test | `phase3_etape3_stress_test.md` | A FAIRE | `tests/stress/test_charge_festival.py` |
| **4** | Commandes + tables | `phase4_commandes_tables.md` | **FAIT** | pytest : 9 tests (`test_commandes_tables.py`), PW : a ecrire |
| **5** | Cloture + rapports | `phase5_cloture_rapports.md` | **FAIT** | pytest : 7 tests (`test_cloture_caisse.py`), PW : a ecrire |
| **6** | Migration donnees | `phase6_migration.md` | A FAIRE | dry-run + verify_transactions |
| **7** | Consolidation | `phase7_consolidation.md` | A FAIRE | manage.py check + verify_transactions |

**Prochaine etape : Phase 3 etape 2** (retour carte + recharges) ou **Phase 6** (migration donnees)

## Comment utiliser

1. Ouvrir le fichier de l'etape en cours
2. Copier-coller le contenu comme premier message dans Claude Code
3. Laisser Claude lire le plan et confirmer sa comprehension AVANT de coder
4. Valider chaque etape avant de passer a la suivante

## Modele recommande par phase

| Phase | Modele | Raison |
|-------|--------|--------|
| Phase -1 | **Sonnet** | Django admin/templates, bien cadre |
| Phase 0, etapes 1-2 | **Opus** | Modeles critiques, atomicite, securite |
| Phase 0, etape 3 | **Sonnet** | Admin + tests, pattern repetitif |
| Phase 1 | **Sonnet** | Product unifie + modeles POS, admin |
| Phase 2 | **Sonnet** | Remplacement mocks, vues FALC |
| Phase 3, etapes 1-2 | **Opus** | Paiement atomique, integration fedow_core |
| Phase 3, etape 3 | **Sonnet** | Stress test (code de test) |
| Phase 4 | **Sonnet** | Commandes/tables, vues FALC |
| Phase 5 | **Sonnet** | Cloture/rapports |
| Phase 6 | **Opus** | Migration donnees, zero perte |
| Phase 7 | **Sonnet** | Nettoyage, consolidation |

## Ordre des fichiers

```
Phase -1 — Dashboard Groupware                          [FAIT]
  phase-1_etape1_modeles_configuration.md               [FAIT]
  phase-1_etape2_dashboard_callback.md                  [FAIT]
  phase-1_etape3_sidebar_conditionnelle.md              [FAIT]

Phase 0 — fedow_core : fondations                      [FAIT]
  phase0_etape1_modeles_fedow_core.md                   [FAIT]
  phase0_etape2_services_wallet.md                      [FAIT]
  phase0_etape3_admin_tests_securite.md                 [FAIT]

Phase 1 — Product unifie + modeles POS (decision 16.9) [FAIT]
  phase1_etape1_modeles_pos.md                          [FAIT]
  phase1_etape2_admin_fixtures.md                       [FAIT]

Phase 2 — Remplacement des mocks
  phase2_etape1_caisse_depuis_db.md                       [FAIT]
  phase2_etape2_paiement_especes_cb.md                    [FAIT]

Phase 3 — Integration fedow_core
  phase3_etape1_paiement_nfc.md
  phase3_etape2_retour_carte_recharges.md
  phase3_etape3_stress_test.md

Phase 4 — Mode restaurant                            [FAIT]
  phase4_commandes_tables.md                           [FAIT]

Phase 5 — Cloture et rapports                      [FAIT]
  phase5_cloture_rapports.md                         [FAIT]

Phase 6 — Migration des donnees
  phase6_migration.md

Phase 7 — Consolidation
  phase7_consolidation.md
```

## Tests par phase — ce qui est couvert et ce qui manque

### Phase -1 (FAIT)
- **Playwright** : `29-admin-proxy-products.spec.ts` — 6 tests (proxy admins + sidebar)
- **Shell Django** : verification manuelle des module_* fields

### Phase 0 (FAIT)
- **pytest** : `test_fedow_core.py` — 8 tests :
  1. `test_fedow_core_base` — creer Asset, Wallet, Token, crediter
  2. `test_id_auto_increment` — verifier id BigAutoField croissant
  3. `test_solde_insuffisant` — SoldeInsuffisant raise
  4. `test_pas_de_leak_cross_tenant` — isolation tenant
  5. `test_tenant_sur_transaction` — FK tenant correcte
  6. `test_pending_invitations` — invitation per-asset
  7. `test_accept_invitation` — acceptation d'invitation
  8. `test_visibilite_queryset_admin` — queryset admin filtre par tenant
- **Playwright** : `31-admin-asset-federation.spec.ts` — flow cross-tenant (12 steps)

### Phase 1 (FAIT)
- **Shell Django** : imports, meta fields, proxy checks
- **Admin** : section "Caisse" visible/cachee
- **Management command** : `create_test_pos_data` cree 5 products + 2 PV

### Phase 2, etape 1 (FAIT)
- **pytest** : `test_caisse_navigation.py` — 11 tests :
  - `TestCartePrimaireSerializer` (4 tests) : tag_id valide, vide, absent, espaces
  - `TestCartePrimaireVue` (4 tests) : carte valide → redirect, inconnue, non primaire, tag vide via vue
  - `TestPointDeVenteVue` (1 test) : vrais produits depuis DB
  - `TestSansAuthentification` (2 tests) : GET et POST sans auth → 403
- **Playwright** : `32-laboutik-caisse-db.spec.ts` (A ECRIRE)

### Phase 2, etape 2 (FAIT)
- **pytest** : `test_paiement_especes_cb.py` — 7 tests :
  - `TestPaiementEspeces` (1 test) : payer CA → LigneArticle(payment_method='CA', sale_origin='LB')
  - `TestPaiementCB` (1 test) : payer CB → LigneArticle(payment_method='CC')
  - `TestTotalCentimes` (1 test) : int(round(prix * 100)) == amount dans LigneArticle
  - `TestProductSoldPriceSold` (1 test) : ProductSold + PriceSold crees
  - `TestPanierVide` (1 test) : panier vide → aucune LigneArticle
  - `TestPaiementNFCDesactive` (1 test) : NFC → message "non disponible"
  - `TestPaiementAtomique` (1 test) : UUID inexistant → ignore, aucune ligne
- **Playwright** : `32-laboutik-caisse-db.spec.ts` (A ECRIRE)

### Phase 3 (A ECRIRE)
Tests prevus :
- **pytest** : `test_paiement_cashless.py`
  - `test_paiement_nfc_atomique` — solde suffisant → Transaction + Token + LigneArticle OK
  - `test_paiement_nfc_rollback_solde_insuffisant` — rien ne change si solde < montant
  - `test_paiement_nfc_rollback_si_erreur` — exception mid-bloc → tout rollback
  - `test_retour_carte_vrais_soldes` — Token.value == affichage
  - `test_recharge_euros` — REFILL + Token credite
  - `test_recharge_cadeau` — REFILL TNF + Token credite
- **Stress** : `tests/stress/test_charge_festival.py` — 4 tenants, 2000 transactions concurrentes
- **Prerequis** : creer `verify_transactions` management command AVANT le stress test

### Phase 4 (FAIT)
- **pytest** : `test_commandes_tables.py` — 9 tests :
  - `TestOuvrirCommande` (2 tests) : ouvrir commande Table L→O + validation articles vides
  - `TestAjouterArticles` (2 tests) : ajouter articles a commande OPEN + erreur si commande PAID
  - `TestMarquerServie` (1 test) : articles → SERVI, commande → SERVED
  - `TestPayerCommande` (1 test) : payer especes → PAID, Table → L, LigneArticle crees
  - `TestAnnulerCommande` (3 tests) : annuler → CANCEL + table reste O si autre commande + erreur si PAID
- **Playwright** : `34-laboutik-commandes.spec.ts` (A ECRIRE)

### Phase 5 (FAIT)
- **pytest** : `test_cloture_caisse.py` — 7 tests :
  - `TestClotureTotauxCorrects` (1 test) : 3 LigneArticle (especes 500c + CB 1000c + NFC 2000c) → totaux corrects
  - `TestClotureNombreTransactions` (1 test) : nombre_transactions >= 3
  - `TestClotureFermeTables` (1 test) : 2 tables OCCUPEE → LIBRE apres cloture
  - `TestClotureRapportJSON` (1 test) : rapport_json contient par_categorie, par_produit, par_moyen_paiement, commandes
  - `TestClotureFiltreDatetime` (1 test) : LigneArticle hier non comptee, LigneArticle maintenant comptee
  - `TestDoubleClotureMmePeriode` (1 test) : 2 clotures creees (pas de blocage)
  - `TestClotureAnnuleCommandes` (1 test) : commande OPEN → CANCEL apres cloture
- **Playwright** : `35-laboutik-cloture.spec.ts` (A ECRIRE)

### Phase 6 (A ECRIRE)
Tests prevus :
- **pytest** : `test_import_fedow.py` + `test_import_laboutik.py`
  - `test_dry_run_sans_ecriture` — count avant == count apres
  - `test_import_preserve_uuid` — UUID ancien Fedow == uuid dans Transaction
  - `test_import_migrated_true` — toutes les transactions importees ont migrated=True
  - `test_verify_transactions_post_import` — management command passe
  - `test_somme_tokens_coherente` — sum(Token.value) == attendu

### Phase 7 (A ECRIRE)
Tests prevus :
- **pytest** : `test_consolidation.py`
  - `test_recalculate_hashes` — toutes les transactions ont un hash non null apres
  - `test_hash_unique` — pas de doublons
  - `test_suppression_mocks_pas_import_casse` — manage.py check passe apres suppression

## Concordance avec la stack-ccc (skill /django-htmx-readable)

### Regles respectees dans les phases FAITES
- ViewSet (pas ModelViewSet) — OK
- FALC (commentaires bilingues) — OK
- data-testid sur les elements interactifs — OK (dashboard)
- i18n avec _() et {% translate %} — OK
- Inline styles dans admin Unfold (pas Tailwind custom) — OK
- CSRF sur body — OK

### Regles a verifier/appliquer dans les phases A FAIRE
- **Serializers DRF pour validation** : les POST de Phase 2 (carte_primaire, panier) DOIVENT utiliser des serializers.Serializer, pas request.POST direct
- **CHANGELOG** : chaque phase doit mettre a jour CHANGELOG.md
- **"A TESTER et DOCUMENTER/"** : chaque phase doit creer un fichier .md dans ce dossier
- **Workflow i18n** : apres chaque phase qui ajoute du texte visible, lancer makemessages + compilemessages
- **aria-live** : les zones HTMX dynamiques (resultats paiement, feedback carte) doivent avoir aria-live="polite"
- **data-testid** : chaque nouveau bouton/formulaire/zone dynamique doit avoir un data-testid

## Regles rappel

- **1 phase = 1-2 sessions max.** Ne jamais enchainer 2 phases.
- **Regle des 3 fichiers** : max 3 fichiers modifies avant check + tests.
- **Valider avec le mainteneur** entre chaque phase.
- **Ne jamais faire de git.** Le mainteneur s'en occupe.
- **Contexte etendu** (1M tokens) : recommande pour Phase 0 et Phase 6.
  Lancer avec `claude --model opus[1m]` (ou `sonnet[1m]` selon la phase).
  En cours de session : `/model opus[1m]`

## Points d'attention pour les phases restantes

### Prerequis manquants identifies
1. **`verify_transactions` management command** — mentionne dans Phase 3 (stress test) et Phase 6-7 mais jamais cree. A creer en Phase 3 etape 3 au plus tard.
2. **Wallet du lieu** — `_payer_par_nfc()` a besoin d'un wallet receiver (le lieu). Verifier si `Configuration.primary_wallet` existe ou doit etre ajoute.
3. **PriceSold / ProductSold** — LigneArticle pointe vers PriceSold (pas Price directement). Les vues de paiement doivent creer ces intermediaires. A documenter dans Phase 2 etape 2.
4. **Format dump JSON** (Phase 6) — pas defini. A specifier avec le mainteneur avant Phase 6.
5. **Script de generation du dump** depuis l'ancien Fedow/LaBoutik — pas prevu dans les prompts.

### Risques identifies
- **Multi-tarif (paniers mixtes EUR + tokens)** — impact JS `addition.js` (~800 lignes). Hors scope Phases 0-7 selon le plan, mais necessaire pour un POS complet. A planifier separement.
- **Front JS legacy** — les templates laboutik utilisent du JS qui attend des donnees mockees. Le remplacement en Phase 2 peut casser le JS si les noms de variables changent.
