# LaBoutik — Index des tâches

> Suivi simplifié de l'avancement. Le détail complet est dans [`PLAN_LABOUTIK.md`](PLAN_LABOUTIK.md).
> Les comptes-rendus de sessions sont dans [`PHASES/`](PHASES/).
>
> Dernière mise à jour : 2026-03-23

---

## Fait

### Phase -1 — Dashboard Groupware ✅

5 champs `module_*` sur Configuration, dashboard Unfold avec switches HTMX,
sidebar conditionnelle (menus masqués si module inactif), proxy models Product
(TicketProduct, MembershipProduct).

### Phase 0 — fedow_core ✅

App `fedow_core` dans SHARED_APPS. Modèles Asset (5 catégories), Token (centimes),
Transaction (BigAutoField PK), Federation (M2M invitation/acceptation).
Services : AssetService, WalletService, TransactionService. 8 tests pytest +
test Playwright cross-tenant fédération.

### Phase 1 — Modèles POS + Admin ✅

Product unifié (8 champs POS, CategorieProduct, POSProduct proxy, Price.asset FK).
4 modèles laboutik : PointDeVente, CartePrimaire, Table, CategorieTable.
Admin Unfold complet. Management command `create_test_pos_data`.

### Phase 2 — Caisse depuis DB ✅

Remplacement des mocks par la vraie DB. Carte primaire → sélection PV → interface POS.
Paiement espèces et CB avec création LigneArticle + PriceSold + ProductSold.

### Phase 2.5 — POS Adhésion ✅

Wizard d'identification (6 chemins : NFC user connu, NFC anonyme, email/nom via formulaire).
Fusion wallet éphémère → user.wallet. Création/renouvellement Membership.
Multi-tarif et prix libre.
Test Playwright : `44-laboutik-adhesion-identification.spec.ts` (8 tests).

### Phase 3.1 — Paiement NFC cashless ✅

`_payer_par_nfc()` atomique via fedow_core. Débit Token + crédit wallet lieu +
Transaction + LigneArticle dans le même `transaction.atomic()`.

### Phase 3.2 — Recharges + sécurité ✅

Recharges espèces/CB (RE/RC/TM). Wallet éphémère pour cartes anonymes.
Garde NFC : les recharges ne peuvent pas être payées par NFC (3 couches de protection).

### Phase 4 — Mode restaurant ✅

CommandeSauvegarde + ArticleCommandeSauvegarde. Cycle de vie : OPEN → SERVED → PAID / CANCEL.
Tables avec statut (Libre/Occupée/Servie). CommandeViewSet (5 actions).

### Phase 5 — Clôture caisse ✅

ClotureCaisse avec totaux par moyen de paiement (centimes). Rapport JSON détaillé.
Export PDF (WeasyPrint), CSV, envoi email (Celery). Fermeture des tables et commandes.

### UX — 5 sessions de polish ✅

Filtre catégorie, feedback tactile, couleurs boutons paiement, écrans FALC
(confirmation espèces, succès, retour carte), responsive Sunmi D3mini (1278×800).

### Refonte typage ✅

Suppression `ADHESION`, `CASHLESS`, `KIOSK` de `comportement`. Migration vers `DIRECT` + `AVANCE`.
Produits adhésion dans M2M standard. Suppression `kiosk.html` et code conditionnel.
Tests Playwright adaptés (Session 04).

---

## À faire (dans l'ordre)

> **Principe de séquencement** : chaque phase produit des fondations réutilisées par les suivantes.
> Le refactoring CSS/footer est un prérequis de la billetterie (qui utilise `<c-footer>`).
> Le flow identification unifié est un prérequis de la billetterie (les billets utilisent le même flow).
> Le WebSocket est un prérequis de l'impression (Sunmi Inner).
> Les rapports comptables et le menu ventes partagent le même `RapportComptableService`.

### 1. Refactoring Frontend ← PROCHAIN

Nettoyage fondation. Pas de changement de logique. Pas de risque pour les tests.

- [ ] **Sécurité** : validation prix libre côté serveur + fix XSS `textContent` dans tarif.js
- [ ] **Accessibilité** : `aria-live` sur `#messages` et `#addition-list`
- [ ] **Extraction CSS** : 2171 lignes inline → fichiers `laboutik/static/css/` séparés
- [x] **Footer Cotton** : extraire `<c-footer>` de common_user_interface (fait — tables et kiosk inchangés)
- [ ] **Run tests** : Playwright complet + pytest — valider que rien ne casse

JS non touché (à discuter avec Nicolas). Backend non touché.

### 2. Flow identification unifié (1 panier = 1 client) ← EN COURS

Remplace le `elif` mutuellement exclusif (recharge / adhesion / normal) par un flow unifié.
L'identification se fait AVANT le choix de paiement (plus logique UX).
Session 05.

- [x] Flag `panier_necessite_client` dans `moyens_paiement()` (recharges + adhésions)
- [x] Écran identification intégré dans `hx_display_type_payment.html` (NFC + email adaptatif)
- [x] Template `hx_recapitulatif_client.html` (récap article par article + total + boutons paiement)
- [x] `elif` supprimé de `hx_display_type_payment.html`
- [x] `identifier_client()` reconstruit le panier + texte adaptatif par type d'article
- [x] Formulaire email soumet via `#addition-form` (les `repid-*` sont propagés)
- [x] Verrouillage JS par groupe supprimé (paniers mixtes VT+RE+AD autorisés)
- [x] PV "Mix" dans `create_test_pos_data` (Biere + Recharge 10€ + Adhesion Test Mix)
- [x] 28 tests pytest + 8 tests E2E adhesion + 8 E2E paiement = 0 échec
- [x] Vérification LigneArticle en DB (email, carte, payment_method, amount, qty)
- [x] Test E2E panier mixte sur PV "Mix" (VT+RE+AD → NFC → espèces → 3 LigneArticle vérifiées)

### 3. Billetterie

Les articles billet (`methode_caisse='BI'`) coexistent dans la grille standard.
Tuile paysage (2 colonnes CSS Grid) + jauge event.
Intégration dans le flow identification unifié (session 07 : `panier_a_billets`).
Sessions 06 + 07.

- [ ] `_construire_donnees_articles()` enrichi avec données event/jauge pour `methode_caisse='BI'`
- [ ] Composant Cotton `<c-billet-tuile>` (paysage, `grid-column: span 2`, jauge)
- [ ] Jauge places restantes (polling HTMX 30s → WebSocket plus tard)
- [ ] Ajout `panier_a_billets` dans `panier_necessite_client` + adaptation `hx_identifier_client.html`
- [ ] `_creer_billets_depuis_panier()` : Reservation + Ticket + LigneArticle (atomique)
- [ ] Vérification atomique jauge au paiement
- [ ] Impression mock (console logger)
- [ ] Tests pytest + Playwright

### 4. WebSocket

Push serveur → navigateur via HTMX 2 extension `ws`. Daphne ASGI.

- [ ] Décommenter `'channels'` dans INSTALLED_APPS
- [ ] Télécharger `ext/ws.js`, charger dans `base.html`
- [ ] `LaboutikConsumer` + route `ws/laboutik/{pv_uuid}/`
- [ ] Badge vert "Connecté" au chargement (test visuel)
- [ ] `wsocket/broadcast.py` : helper broadcast HTML
- [ ] Intégration billetterie : broadcast jauge après vente (remplace polling)
- [ ] Tests
- [ ] **Dev** : `manage.py runserver` (Daphne) — **pas** `runserver_plus`
- [ ] **Prod** : `daphne TiBillet.asgi:application` derrière Nginx

### 5. Impression

Module modulaire Celery (fire-and-forget, retry exponentiel). Sunmi Cloud + Inner.

- [ ] Modèle `Printer` (SC/SI) + FK sur PointDeVente et CategorieProduct
- [ ] `LaboutikConfiguration` : `sunmi_app_id` + `sunmi_app_key` (Fernet)
- [ ] `PrinterBackend` interface (Strategy) dans `laboutik/printing/`
- [ ] `SunmiCloudBackend` (HTTPS HMAC) + `SunmiInnerBackend` (WebSocket)
- [ ] `PrinterConsumer` WebSocket dédié (`ws/printer/{printer_uuid}/`)
- [ ] Copie nettoyée `sunmi_cloud_printer.py` (ESC/POS)
- [ ] Formatters : vente, billet, commande, clôture
- [ ] Celery : `imprimer_async()` + `imprimer_commande()` (split par catégorie)
- [ ] Admin Unfold `PrinterAdmin`
- [ ] Remplacer le stub `imprimer_billet()` par le vrai dispatch
- [ ] Tests

### 6. Rapports Comptables

Ticket Z enrichi — document comptable légal. Service de calcul partagé avec le Menu Ventes.

- [ ] Modèle `RapportComptable` (numéro séquentiel par PV)
- [ ] `laboutik/reports.py` : `RapportComptableService` (12 sections de calcul)
- [ ] Admin Unfold section "Ventes" avec vue détail HTML
- [ ] Export PDF (A4 formel), CSV, Excel (openpyxl)
- [ ] Envoi automatique (Celery Beat : quotidien/hebdo/mensuel/annuel)
- [ ] Config : `rapport_emails`, `rapport_periodicite`, `fond_de_caisse`
- [ ] Tests

### 7. Menu Ventes (caisse tactile)

Menu "Ventes" dans le burger menu POS. Consomme le même `RapportComptableService`.

- [ ] **Ticket X** : récap' en cours (3 sous-vues) — lecture seule, pas de clôture
- [ ] **Liste des ventes** : historique scrollable, filtres, pagination HTMX
- [ ] **Détail + correction** : corriger moyen paiement (ESP↔CB↔CHQ, pas NFC)
- [ ] **Ré-impression ticket** : reconstruit → `imprimer_async.delay()`
- [ ] **Fond de caisse** : saisie/modification montant initial
- [ ] **Sortie de caisse** : retrait espèces, ventilation par coupure, justificatif
- [ ] Modèles : `CorrectionPaiement` (audit), `SortieCaisse`
- [ ] Navigation : sidebar desktop, onglets mobile
- [ ] Tests

### 8. Multi-Tarif UX

Overlay non-bloquant avec quantités multiples. À discuter avec Nicolas (son code JS).

- [ ] Overlay dans `#articles-zone` — panier reste visible
- [ ] Clic tarif = incrément sans fermer
- [ ] Prix libre : mémorisation du dernier montant
- [ ] Badge quantité sur chaque bouton tarif

### 9. Multi-Asset

Paniers mixtes EUR + tokens. À détailler avec le mainteneur.

- [ ] Regrouper articles par `Price.asset` dans `payer()`
- [ ] Affichage multi-total (par asset) dans le panier
- [ ] Session dédiée pour l'UX

### 10. Stress test (Phase 3.3)

- [ ] Management command `verify_transactions` (séquence, soldes, tenant)
- [ ] Stress test : 4 tenants, 2000 tx concurrentes, 80 threads

### 11. Migration données (Phase 6)

- [ ] `import_fedow_data` (dry-run + commit)
- [ ] `import_laboutik_data`
- [ ] `verify_import`

### 12. Consolidation (Phase 7)

- [ ] `recalculate_hashes` → hash NOT NULL + UNIQUE
- [ ] Supprimer `fedow_connect/fedow_api.py`, `fedow_connect.Asset`, `fedow_connect.FedowConfig`
- [ ] Supprimer `fedow_public.AssetFedowPublic`
- [ ] Run complet pytest + Playwright
