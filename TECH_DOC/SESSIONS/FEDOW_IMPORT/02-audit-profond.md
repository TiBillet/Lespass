# Audit profond 02 — Fusion Fedow → Lespass : chasse aux bugs et fausses routes

Date : 2026-06-10
Méthode : workflow multi-agents (42 agents, ~700 lectures de code) — 5 auditeurs
parallèles + contre-expertise adversariale de chaque finding bloquant/majeur.
Détail complet des 68 findings : [02b-audit-findings-detail.md](./02b-audit-findings-detail.md).

**Limite de l'audit** : 19 contre-expertises sur 37 ont été coupées par la limite
de session (essentiellement les dimensions gap-fonctionnel et portage-v1).
Les findings concernés sont marqués ⏳ dans l'annexe : à re-vérifier avant de
les traiter comme acquis. Relançables via reprise du workflow (résultats cachés).

---

## 1. Verdict global

**La route choisie (base V2 + coexistence par population) reste la bonne** :
le cœur financier du `fedow_core` V2 corrige réellement le bug DRIFT
(`crediter`/`debiter` sous `select_for_update` + `transaction.atomic`,
re-check de solde sous verrou, abandon du chaînage qui causait les 320 forks).
Aucun finding ne remet en cause l'architecture.

**MAIS l'audit impose trois corrections de trajectoire** avant d'écrire la spec :

1. **Le fedow_core V2 n'est pas portable tel quel** : 1 bloquant + 5 majeurs
   confirmés en concurrence/intégrité, 1 bloquant + plusieurs majeurs confirmés
   en isolation multi-tenant. Tous corrigeables, mais à corriger AVANT ou PENDANT
   le portage, pas après.
2. **La migration « tenant par tenant » ne tient pas telle quelle pour les données** :
   l'asset FED est un composant connexe global (46 127 transactions, 2 472 wallets
   avec solde, 22 places actives dont 4 sur l'instance `.re`). Il faut un plan en
   deux temps : tenants à assets purement locaux d'abord (sans leur token FED),
   puis bascule FED coordonnée en bloc.
3. **Le gap fonctionnel est plus grand que prévu** : la V2 actuelle dépend
   ENCORE du serveur Fedow distant pour créer les tenants et les wallets users,
   et 4 flux n'ont aucune branche V2. « Porter lespass-main » ne suffit pas :
   il faudra compléter.

---

## 2. Récapitulatif par dimension

| Dimension | Findings | Bloquants | Confirmés | Réfutés | Non vérifiés |
|---|---|---|---|---|---|
| Concurrence & intégrité | 14 | 1 | 6/6 | 0 | 8 (mineurs/info) |
| Isolation multi-tenant | 15 | 1 | 6/8 | 2 | 7 (mineurs/info) |
| Gap fonctionnel | 12 | 1 | 0 (⏳ limite) | — | 12 |
| Migration données | 14 | 4 | 4/4 vérifiés | 0 | 10 |
| Portage V1 | 13 | 2 | 0 (⏳ limite) | — | 13 |
| **Total** | **68** | **9** | **16** | **2** | |

---

## 3. Les 9 bloquants

### Confirmés par contre-expertise ✅

**B1 — `verify_transactions --fix-tokens` fabrique de la monnaie**
(`lespass-main/fedow_core/management/commands/verify_transactions.py:204`)
La commande de réconciliation duplique les règles débit/crédit de `services.py`
et les a désynchronisées (REFILL/BANK_TRANSFER). Sur un tenant ayant reçu un
virement, `--fix-tokens` créditerait le wallet du lieu du montant des virements
bancaires → création de monnaie fantôme par l'outil censé réconcilier. Écrit en
plus sans verrou (réintroduit le lost-update DRIFT). *L'outil qui validera
l'import des 500 lieux doit être irréprochable : à corriger en priorité 1.*

**B2 — `Asset.wallet_origin` peut pointer le wallet d'un client**
(isolation multi-tenant) Les ventes seraient créditées à un wallet user au lieu
du wallet du lieu. Garde-fou de modèle absent.

**B3 — L'asset FED est indécoupable tenant par tenant**
Tout lieu accepte FED automatiquement (`federated_with()` l.970 du Fedow
standalone). Migrer le solde FED d'un user pendant que d'autres lieux V1
l'acceptent encore = deux registres pour le même argent, double dépense
possible. → Migration FED **en bloc coordonné** (22 places actives + pot
central + 2 472 wallets), gel des transactions FED pendant l'import.

**B4 — Sémantique débit/crédit V1 ≠ V2 : import brut = soldes faux**
En V1, REFUND local et DEPOSIT ne créditent PAS le receiver ; le recalcul V2
compterait ces crédits → fausses créances systématiques (ex. re-créditer les
273 remises en banque). → Normaliser à l'import (receiver=None) selon la table
exacte du DRIFT README §8.1, puis exiger 0 divergence `verify_transactions`.

**B5 — `Token.value` non fiable tant que `reconcile_tokens` n'a pas tourné en prod**
Le patch F() est déployé mais la régularisation prod n'est PAS lancée
(0 transaction CORRECTION au 09/06, ~1 262 € de drift documenté). Prérequis dur :
réconcilier la prod Fedow, vérifier drift=0, PUIS exporter.

### Non contre-expertisés ⏳ (limite de session — à re-vérifier)

**B6 — La V2 exige toujours le Fedow distant pour créer tenants et wallets users**
(`lespass-main/BaseBillet/views.py:1059`, `validators.py:1059`, `install.py:197`)
`MyAccount.dispatch` appelle `FedowAPI().wallet.get_or_create_wallet()` en HTTP
sans dispatch → 500 sur `/my_account/` si Fedow est éteint. Contredit
directement « nouveaux tenants = V2 autonomes ». → Créer
`WalletService.get_or_create_wallet_user()` local + handshake optionnel.

**B7 — Un seul Fedow sert DEUX instances Lespass (.coop et .re)**
317 places `.coop`, 50 places `.re` (autre base de données !), 54 wallets actifs
sur les deux, 4 des 22 places FED en `.re`, et 31 places avec
`lespass_domain='xxx.None'` inmappables. → Décision mainteneur requise sur le
sort de l'instance `.re` avant de planifier la migration des données.

**B8 — Collision de numérotation des migrations BaseBillet 0204–0217**
Les deux branches ont créé des migrations différentes avec les mêmes numéros
(et des opérations qui se chevauchent : proxies POSProduct/MembershipProduct).
→ Ne JAMAIS copier les migrations BaseBillet V2 ; porter les champs puis
`makemigrations` frais en 0219+.

**B9 — `fedow_core/signals.py` importe `laboutik.models` sans garde**
(`lespass-main/fedow_core/signals.py:65`) laboutik est une coquille vide en V1 :
tout `save()` d'un Asset → `ModuleNotFoundError`. Le signal exige aussi des
champs Product POS absents de V1. → Guard ImportError ou désactivation du
signal en phase 1.

---

## 4. Majeurs confirmés (concurrence + tenant) — résumé

| # | Problème | Fichier | Correction |
|---|---|---|---|
| M1 | `process_cashless_refill` : idempotence par convention de caller, pas par contrainte DB → double crédit possible pour tout futur caller | `services.py:1208` | UniqueConstraint partielle sur `Transaction.checkout_stripe` |
| M2 | `fusionner_wallet_ephemere` : solde lu hors verrou puis wallet détaché → reliquat orphelin (argent client perdu). Le garde-fou V1 `amount == token.value` a disparu | `services.py:401` | Verrouiller Token + carte, monter la value fraîche |
| M3 | `rembourser_en_especes` : même classe de bug + `SoldeInsuffisant` non catchée au POS (500 brut) | `services.py:567` | Sélection des tokens sous atomic/verrou + catch dans les 2 vues |
| M4 | Création concurrente du Wallet user : doublons possibles, tokens invisibles | `services.py:371` | Contrainte d'unicité + get_or_create verrouillé |
| M5 | Les validations métier par action du `Transaction.save()` V1 (carte↔wallet, receiver=lieu, asset accepté/fédéré) ont disparu — plus de défense en profondeur | `services.py` (creer) | Réintroduire les asserts par action dans `TransactionService.creer` |
| M6 | Fédération non câblée : `federated_with` (admin V1) et `Federation.assets` (services V2) sont deux mécaniques disjointes ; asset FED invendable au POS par défaut | admin/services | Converger vers `fedow_core.Federation` + bootstrap FED |
| M7 | `enregistrer_virement` écrit la LigneArticle comptable dans le schéma courant au lieu du tenant cible | `services.py:1066` | `tenant_context(tenant_cible)` autour de l'écriture |
| M8 | `refund_online` sans aucun dispatch V1/V2 | `BaseBillet/views.py` | Ajouter le dispatch |
| M9 | `_obtenir_ou_creer_wallet` (POS) duplique `scanner_carte` sans verrou, origin=tenant scannant | laboutik | Mutualiser avec CarteService |

## 5. Findings réfutés par la contre-expertise ❌

- « Critère de dispatch incohérent `is not None` vs `bool()` » → réfuté en
  pratique (pas de valeur falsy non-None possible), reclassé mineur
  (harmonisation cosmétique au portage).
- « tokens_table/transactions_table : 500 sur tenant pur V2 » → non déclenchable
  actuellement ; point de vigilance pour le portage, pas un bug.

---

## 6. Ce que l'audit valide explicitement

- Chemin nominal débit/crédit : pas de lost-update (verrou ligne + re-check
  sous verrou + atomic). Le bug DRIFT est structurellement corrigé.
- Double remboursement simultané bloqué (rollback complet).
- Webhook recharge Stripe correctement sérialisé côté caller
  (verrou `Paiement_stripe` + re-check status + anti-tampering).
- Conversions montants conformes à la décision n°8 (`int(round(prix*100))`)
  sauf 2 résidus mineurs.
- UUID transactions Fedow sains (0 doublon) ; les 320 forks de chaîne ne
  bloquent PAS l'import puisque V2 abandonne le chaînage.
- Migrations AuthBillet/QrcodeCashless/Customers/fedow_core copiables telles
  quelles ; settings V1 : seul `SHARED_APPS += fedow_core` requis.
- Correspondance users Fedow↔Lespass saine (matching email, à faire
  insensible à la casse).

---

## 7. Conséquences sur le plan (révision de l'esquisse du doc 01 § 8)

L'ordre des phases doit intégrer les prérequis découverts :

0. **Prérequis prod (avant tout code)** : lancer `reconcile_tokens` sur la prod
   Fedow + vérifier drift=0 (B5) ; trancher le sort de l'instance `.re` (B7) ;
   cartographier les 31 places `lespass_domain=None`.
1. **Durcissement fedow_core V2** (avant ou pendant le portage) : B1, M1-M5
   — c'est du travail sur `services.py`/`verify_transactions.py`, testable
   unitairement, qui bénéficie aussi à lespass-main.
2. **Portage du socle** dans V1 : en respectant B8 (makemigrations frais) et
   B9 (signal découplé de laboutik), B2 (garde wallet_origin).
3. **Autonomie V2** : `get_or_create_wallet_user` local + handshake optionnel (B6)
   — condition pour que « nouveau tenant = V2 » soit vrai.
4. **Couture des flux** avec dispatch — y compris les 4 flux sans branche V2
   (badge, QR pay, refund online, rewards) et l'adhésion admin/web (⏳ à re-vérifier).
5. **Importeur de données** : normalisation sémantique V1→V2 (B4), wallets
   éphémères et orphelins inclus, validation `verify_transactions` = 0 divergence.
6. **Bascule FED en bloc** : gel + import coordonné des 22 places actives FED
   + pot central + tokens FED des wallets (B3).
7. Décommissionnement.

## 8. Actions de suivi immédiates

- [ ] Relancer les 19 contre-expertises coupées (reprise du workflow, résultats cachés).
- [ ] Arbitrage mainteneur : sort de l'instance `.re` (B7).
- [ ] Arbitrage mainteneur : corriger B1/M1-M5 directement dans lespass-main
      (bénéficie aux deux branches) ou pendant le portage V1 ?
- [ ] Puis : rédaction de la SPEC du chantier sur la base du § 7.
