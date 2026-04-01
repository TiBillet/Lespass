# LaBoutik — Index des tâches

> Suivi simplifié de l'avancement. Le détail complet est dans [`PLAN_LABOUTIK.md`](PLAN_LABOUTIK.md).
> Les comptes-rendus de sessions sont dans [`PHASES/`](PHASES/).
>
> Dernière mise à jour : 2026-04-01 (session 16 terminée)

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

### Refonte typage ✅ → Types PV restaurés (session 06)

Session 04 : suppression `KIOSK` de `comportement`, suppression `kiosk.html` et code conditionnel.
Session 06 : restauration des types PV `ADHESION` ('A'), `CASHLESS` ('C'), ajout `BILLETTERIE` ('T').

Le type du PV détermine le **chargement automatique** des articles :
- `DIRECT` ('D') : articles du M2M uniquement (bar, restaurant, etc.)
- `ADHESION` ('A') : charge auto tous les produits adhésion
- `CASHLESS` ('C') : charge auto toutes les recharges
- `BILLETTERIE` ('T') : construit les articles depuis les événements futurs
- `AVANCE` ('V') : mode commande restaurant (réservé, pas codé)

Les articles du M2M `products` sont **toujours chargés en plus** du chargement automatique.
Pas de double typage : l'article n'a pas besoin de `methode_caisse` pour apparaître — c'est le type du PV qui décide.

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

Le PV de type `BILLETTERIE` ('T') construit ses articles depuis les événements futurs.
Pas de double typage : pas de `methode_caisse='BI'`, c'est le type du PV qui décide.
1 tuile paysage = 1 Price d'un event. Jauge statique (WebSocket en phase 4).
Les events apparaissent comme pseudo-catégories dans la sidebar existante `<c-categories>`.
Sessions 06 + 07.

- [x] Types PV restaurés : `ADHESION`, `CASHLESS`, `BILLETTERIE` (migration 0005)
- [x] Composant Cotton `billet_tuile.html` (paysage, `grid-column: span 2`, jauge statique)
- [x] CSS `billet_tuile.css` + responsive mobile (portrait span 1 < 599px)
- [x] PV "Accueil Festival" (type BILLETTERIE) + articles M2M (Bière, Eau)
- [x] `_construire_donnees_articles()` : charge depuis events futurs quand PV BILLETTERIE (1 tuile = 1 Price)
- [x] `_construire_donnees_categories()` : events comme pseudo-catégories (date + mini-jauge)
- [x] `cotton/categories.html` : rendu event (date + jauge) si `is_event` + sidebar scrollable
- [x] Filtre sidebar par event (CSS JS existant, pas de modif JS)
- [x] Clic tuile → panier (classe `article-container` + ID composite `{event_uuid}__{price_uuid}`)
- [x] Jauge : Price.stock si défini, sinon Event.jauge_max
- [x] Couleurs par event (palette cyclique 8 couleurs)
- [x] Events sans produit filtrés de la grille et de la sidebar
- [x] Spinner loading-states (extension HTMX officielle, délai 400ms)
- [x] Navigation PV burger menu en hx-get (anti-blink)
- [x] Audit a11y : aria-hidden sur icônes, visually-hidden, aria-label jauge sidebar
- [x] `panier_a_billets` dans `panier_necessite_client` → écran identification "Billetterie" (session 07)
- [x] `_extraire_articles_du_panier()` : parser ID composite `__` pour BILLETTERIE (session 07)
- [x] `_creer_billets_depuis_panier()` : Reservation(VALID) + Ticket(NOT_SCANNED) + LigneArticle (atomique) (session 07)
- [x] Vérification atomique jauge (`select_for_update`) au paiement (session 07)
- [x] `imprimer_billet()` stub console logger (session 07)
- [x] `_envoyer_billets_par_email()` : webhook + email Celery avec PDF billets (session 07)
- [x] `LigneArticle.user_email()` : ajout branche `reservation.user_commande.email` (session 07)
- [x] `identifier_client()` récapitulatif : description "Billet {tarif} — {event}" (session 07)
- [x] Propagation `panier_a_billets` dans tous les templates HTMX (session 07)
- [x] 12 tests pytest (8 unitaires + 4 HTTP) + 5 tests E2E Playwright (session 07)
- [x] 218 tests pytest + 5 E2E billetterie (0 régression)

### 4. WebSocket ✅

Push serveur → navigateur via HTMX 2 extension `ws`. Daphne ASGI.
Sessions 08-09. Infrastructure complète, broadcast jauge billetterie, 8 tests pytest.

### 5. Impression ✅

Module modulaire Celery (fire-and-forget, retry exponentiel). 4 backends.
Sessions 10-11-12 (bouton).

- [x] Modèle `Printer` (SC/SI/LN/MK) + FK sur PointDeVente et CategorieProduct
- [x] `LaboutikConfiguration` : `sunmi_app_id` + `sunmi_app_key` (Fernet)
- [x] `PrinterBackend` interface (Strategy) dans `laboutik/printing/`
- [x] `SunmiCloudBackend` (HTTPS HMAC) + `SunmiLanBackend` (HTTP direct) + `SunmiInnerBackend` (WebSocket)
- [x] `MockBackend` : décode les vrais bytes ESC/POS en ASCII dans la console Celery
- [x] `PrinterConsumer` WebSocket dédié (`ws/printer/{printer_uuid}/`)
- [x] Copie nettoyée `sunmi_cloud_printer.py` (ESC/POS, sans numpy/PIL)
- [x] `escpos_builder.py` : construction ESC/POS factorisée (UTF-8 ON, QR code agrandi)
- [x] Formatters : vente, billet (QR signé RSA), commande, clôture
- [x] Celery : `imprimer_async()` + `imprimer_commande()` (split par catégorie)
- [x] Admin Unfold `PrinterAdmin` + entrée sidebar "Caisse LaBoutik"
- [x] Remplacer le stub `imprimer_billet()` par le vrai dispatch Celery
- [x] Bouton "Imprimer" sur l'écran de succès (HTMX POST)
- [x] Auto-print billets pour PV BILLETTERIE
- [x] `uuid_transaction` sur LigneArticle (regroupement pour ré-impression)
- [x] Endpoint `imprimer_ticket` (PaiementViewSet action)
- [x] Imprimante mock "Console (mock)" dans les données de test
- [x] 18 tests pytest impression + 5 tests bouton = 0 régression (252 tests total)

### 6. Conformité LNE + Rapports Comptables ← PROCHAIN

Conformité au référentiel LNE v1.7 (21 exigences). Design spec validé le 2026-03-30.
Sessions 12 à 19. Voir `docs/superpowers/specs/2026-03-30-conformite-lne-caisse-design.md`.

**Session 12 — Fondation HMAC + service de calcul** (Ex.3, Ex.8) ✅ FAIT
- [x] Clé HMAC par tenant (Fernet) dans LaboutikConfiguration
- [x] `hmac_hash` + `previous_hmac` + `total_ht` sur LigneArticle
- [x] FK `point_de_vente` sur LigneArticle (ventilation CA par PV)
- [x] `laboutik/integrity.py` : calculer_hmac(), verifier_chaine(), calculer_total_ht()
- [x] Chaînage HMAC intégré dans `_creer_lignes_articles()` + PV passé dans tous les appels
- [x] `RapportComptableService` (13 méthodes dont ventilation par PV) dans `laboutik/reports.py`
- [x] Management command `verify_integrity`
- [x] 15 tests pytest (8 intégrité + 7 rapport), 276 total, 0 régression

**Session 13 — Clôtures J/M/A + total perpétuel** (Ex.6, Ex.7) ✅ FAIT
- [x] Champs `niveau`, `numero_sequentiel`, `total_perpetuel`, `hash_lignes` sur ClotureCaisse
- [x] `datetime_cloture` : `default=timezone.now` (plus `auto_now_add`)
- [x] `datetime_ouverture` calculé auto (1ère vente après dernière clôture)
- [x] `ClotureSerializer` simplifié (plus de `datetime_ouverture`)
- [x] `cloturer()` connecté au RapportComptableService (rapport 13 clés)
- [x] **Clôture GLOBALE au tenant** (pas par PV). `point_de_vente` nullable/informatif
- [x] Numéro séquentiel atomique par niveau (`select_for_update`), global au tenant
- [x] Total perpétuel incrémenté atomiquement (`F()` expression), jamais remis à 0
- [x] Clôtures M/A automatiques (Celery Beat : M le 1er à 3h, A le 1er janv. à 4h)
- [x] Garde anti-doublon Celery (`exists()` avant `create()`)
- [x] Garde correction post-clôture (`ligne_couverte_par_cloture` filtre `niveau='J'`)
- [x] Admin Unfold enrichi avec badge intégrité
- [x] Fix bug affichage espèces (locale virgule → `|unlocalize` + conversion serveur)
- [x] 7 tests pytest nouveaux + 7 tests existants adaptés, 283 total, 0 régression

**Session 14 — Mentions légales tickets + traçabilité impressions** (Ex.3, Ex.9) ✅ FAIT
- [x] Modèle `ImpressionLog` (uuid PK, FK ligne_article/cloture/operateur/printer, type, duplicata, format)
- [x] `compteur_tickets` sur LaboutikConfiguration (incrémenté atomiquement avec `select_for_update`)
- [x] Ticket de vente enrichi : raison sociale, adresse, SIRET, TVA (ou art. 293 B), n° séquentiel (T-000001)
- [x] Ventilation TVA par taux (tableau HT/TVA/TTC) + totaux HT/TVA globaux
- [x] Mention "*** DUPLICATA ***" (gras, double hauteur+largeur) sur réimpressions
- [x] Traçabilité : `ImpressionLog` créé dans `imprimer_async()` via `impression_meta`
- [x] Détection duplicata par `uuid_transaction` (garde : pas de faux positif si uuid=None)
- [x] Builder ESC/POS étendu (sections legal, TVA breakdown, DUPLICATA)
- [x] `pied_ticket` personnalisé sur les tickets + dans l'admin
- [x] `ImpressionLogAdmin` lecture seule (audit log immutable)
- [x] Index `db_index=True` sur `ImpressionLog.uuid_transaction`
- [x] 8 tests pytest nouveaux, 291 total, 0 régression

**Session 15 — Mode école + exports admin** (Ex.5) ✅ FAIT
- [x] `sale_origin=LABOUTIK_TEST` dans SaleOrigin + `mode_ecole` BooleanField sur LaboutikConfiguration
- [x] Bandeau "MODE ECOLE — SIMULATION" conditionnel sur l'interface POS (header.html)
- [x] Ventes marquées `LABOUTIK_TEST` en mode école (`_creer_lignes_articles()`)
- [x] Tickets portent "*** SIMULATION ***" en mode école (formatter + escpos_builder)
- [x] Exclusion automatique du rapport de production (filtre exact `sale_origin=LABOUTIK`)
- [x] Vue détail HTML du rapport (13 sections structurées, pas JSON brut)
- [x] Export PDF A4 (WeasyPrint), CSV (délimiteur `;`), Excel (openpyxl, 1 onglet/section)
- [x] `mode_ecole` dans l'admin LaboutikConfiguration
- [x] 8 tests pytest nouveaux, 299 total, 0 régression

**Session 15b — Enrichissement rapports comptables** ✅ FAIT
- [x] Filtre template `|euros` : conversion centimes → affichage "127,50 €" (symbole via `Configuration.currency_code`)
- [x] `prix_achat` IntegerField sur Product (centimes, articles POS uniquement)
- [x] `calculer_totaux_par_moyen()` enrichi : `cashless_detail` (noms monnaies via `fedow_core.Asset`) + `currency_code`
- [x] `calculer_detail_ventes()` enrichi : `qty_vendus`/`qty_offerts`, `prix_achat_unit`, `cout_total`, `benefice`
- [x] `calculer_habitus()` enrichi : `depense_mediane`, `recharge_mediane`, `reste_moyenne`/`med_on_card` (via `fedow_core.Token`), `nouveaux_membres`
- [x] Template admin `cloture_detail.html` : 13 sections en tableaux structurés (plus de `pprint`), tout en euros, tout en `{% translate %}`
- [x] Template PDF aligné sur l'admin
- [x] i18n fieldsets admin (Période, Totaux, Détails)
- [x] 3 tests pytest nouveaux + 1 adapté, 302 total, 0 régression

**Session 16 — Menu Ventes : Ticket X + liste** ✅ FAIT
- [x] Entrée "VENTES" dans le burger menu POS (`hx-target="body"` + `hx-push-url`)
- [x] Page plein écran `ventes.html` (header + zone ventes, sans catégories/footer/WebSocket)
- [x] `recap_en_cours` (Ticket X) : 5 onglets (toutes, par PV, par moyen, détail articles, liste ventes)
- [x] `liste_ventes` : pagination SQL `GROUP BY COALESCE(uuid_transaction, uuid)` + `LIMIT/OFFSET` natif PostgreSQL
- [x] `detail_vente` : pattern **collapse** (clic ligne → détail s'ouvre en `<tr>` dessous, re-clic → ferme)
- [x] Fallback `uuid_transaction` → `uuid` (pk) pour les anciennes données sans uuid_transaction
- [x] `_construire_contexte_ventes()` : contexte header/PV/params pour toutes les vues Ventes
- [x] `_rendre_vue_ventes()` : détection `htmx.target` pour page complète vs partial interne
- [x] Colonne Chèque ajoutée dans `calculer_synthese_operations()` (service + template)
- [x] CSS `ventes.css` : thème sombre Luciole, responsive, `table-layout:fixed`, `font-variant-numeric:tabular-nums`
- [x] `stateJson` minimal dans le contexte ventes (fix `JSON.parse("")` crash dans base.html)
- [x] 9 tests pytest + 4 E2E Playwright, 311 pytest total, 0 régression

**Session 17 — Corrections + fond/sortie de caisse** (Ex.4)
- [ ] Correction ESP/CB/CHQ (NFC interdit, post-clôture interdit)
- [ ] Fond de caisse, sortie espèces avec ventilation

**Session 18 — Archivage fiscal + accès administration** (Ex.10-12, Ex.15, Ex.19)
- [ ] Export CSV/JSON avec hash HMAC, max 1 an par archive
- [ ] Management commands `archiver_donnees`, `verifier_archive`, `acces_fiscal`

**Session 19 — Envoi auto rapports + version** (Ex.21)
- [ ] Celery Beat envoi périodique
- [ ] Version visible dans l'interface POS

### 7. Menu Ventes (intégré dans sessions 16-17)

Voir sessions 16 et 17 ci-dessus.

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
