# Recherche 01 — État des lieux : fusion Fedow → Lespass (`fedow_core`)

Date : 2026-06-10
Branche : `main-fedow-import`
Objectif : débroussailler le terrain avant tout plan d'implémentation.
Aucun code n'est écrit dans ce chantier pour l'instant.

---

## 1. Le but du chantier

Fusionner deux moteurs Django en un seul :

- **Fedow** (`../Fedow`) : proto-blockchain de monnaies locales fédérées.
  Serveur central standalone, SQLite, API REST signée RSA.
- **Lespass** (`./`) : moteur multi-tenant (django-tenants) d'adhésion,
  billetterie et gestion de wallet. Client HTTP de Fedow.

La fusion consiste à :

1. Importer la logique de Fedow comme app interne `fedow_core` en **SHARED_APPS**.
2. Supprimer l'API HTTP inter-service (`fedow_connect/fedow_api.py`, 1083 lignes)
   au profit d'appels Python directs (accès DB).
3. Importer les données de la base SQLite de Fedow dans PostgreSQL Lespass.
4. Garder les apps tampon (`fedow_public`) et legacy (`fedow_connect`)
   le temps de la migration.

---

## 2. Les TROIS sources de code en présence

C'est le point structurant de la recherche : il n'y a pas deux codebases, mais trois.

### 2.1 Fedow standalone (`../Fedow/fedow_core`) — le moteur en production

~5 460 lignes. C'est lui qui détient les données de prod (SQLite).

| Fichier | Lignes | Rôle |
|---|---|---|
| `models.py` | 1219 | Asset, Token, Transaction (chaînée SHA256), Wallet, Place, Card, Origin, Federation, FedowUser, CheckoutStripe, Configuration |
| `views.py` | 1731 | 8 ViewSets, ~40 endpoints, webhook Stripe |
| `serializers.py` | 1439 | Validators + serializers (logique métier dedans) |
| `permissions.py` | 273 | 6 classes : API key, signature RSA wallet, signature place, Stripe |
| `utils.py` | 205 | RSA 2048 PSS, Fernet, base64 |
| `signals.py` | 61 | FIRST transaction à la création d'asset, webhook adhésion vers Lespass |

Particularités :
- `AUTH_USER_MODEL = fedow_core.FedowUser` (email unique) — **clash** avec
  `AuthBillet.TibilletUser` lors de l'import.
- Transactions **chaînées** : `previous_transaction` FK + `hash` SHA256 du dict
  trié incluant le hash précédent. 13 actions (FIRST, SALE, CREATION, REFILL,
  TRANSFER, SUBSCRIBE, BADGE, FUSION, REFUND, VOID, DEPOSIT, QRCODE_SALE, CORRECTION),
  chacune avec ses assertions dans `Transaction.save()` (L. 559-788).
- Soldes dénormalisés dans `Token.value`, mis à jour par delta `F()`.

### 2.2 Lespass V1 (ce repo) — le client HTTP

- `fedow_connect/` (TENANT_APPS) : `FedowAPI` et ses 8 sous-classes
  (Wallet, Transaction, NFCcard, Asset, Membership, Badge, Place, Federation).
  `FedowConfig` (singleton tenant) stocke `fedow_place_uuid`,
  `fedow_place_admin_apikey` (Fernet), `fedow_place_wallet_uuid`.
  Expose 1 webhook entrant : `/fedow_connect/membership/` (adhésion vendue en caisse).
- `fedow_public/` (SHARED_APPS) : `AssetFedowPublic` (miroir public des assets,
  avec M2M de fédération `federated_with`/`pending_invitations` vers `Customers.Client`).
- `fedow_core/` : **vide** (seuls des `__pycache__` du prototype V2 traînent).
  Pas dans `settings.py`.
- `AuthBillet.Wallet` : modèle minimal `{uuid (pk, = uuid Fedow), origin (FK Client)}`.
  Le user signe ses requêtes vers Fedow avec sa paire RSA (`user.get_private_key()`).

### 2.3 Prototype V2 (`../lespass-main/fedow_core`, branche `V2`) — la réécriture

~3 680 lignes déjà écrites lors du chantier mono-repo V2 (avec laboutik) :

| Fichier | Lignes | Contenu |
|---|---|---|
| `models.py` | 776 | Asset (5 catégories), Token (centimes), Transaction, Federation |
| `services.py` | 1523 | AssetService, WalletService, TransactionService, BankTransferService, RefillService, CarteService, ScanResult |
| `admin.py` | 1052 | Admin Unfold |
| `signals.py`, `exceptions.py` | 322 | |
| + docs | | `CARTES.md`, `PSP_INTERFACE.md`, `REFUND.md` |

Décisions architecturales **déjà prises et documentées** dans ce prototype :
- `Transaction.id` = BigAutoField PK (remplace uuid-PK + sequence_number),
  `uuid` conservé en champ unique pour les imports depuis l'ancien Fedow.
- **Hash simplifié** : hash individuel par transaction, pas de chaînage
  `previous_transaction` (évite les forks, cf. § 5.2).
- **Centimes (int) partout** pour les montants.
- Pas de `fedow_core.Wallet` : on enrichit `AuthBillet.Wallet`
  (`public_pem`, `name`). Idem `QrcodeCashless.CarteCashless`
  (+ `wallet_ephemere`).
- `checkout_stripe` = UUIDField (pas FK) sur Transaction — FK cross-schema impossible.
- Migration hash en 3 phases : import (hash=null, migrated=True) → production →
  consolidation.
- Command `verify_transactions` pour l'intégrité.

**Question stratégique n°1 du chantier** : importer le `fedow_core` de Fedow
tel quel, ou repartir du `fedow_core` V2 (pattern services, plus FALC, pensé
multi-tenant) et écrire un importeur de données SQLite → PostgreSQL ?
Le prototype V2 est nettement plus proche de la cible "fusion des logiques
métiers" décrite par le mainteneur.

---

## 3. Cartographie des points de couture (Lespass → Fedow)

Liste exhaustive des call sites `FedowAPI` dans Lespass V1, groupés par flux.
Chaque ligne = un appel HTTP à remplacer par un appel de service interne.

### Flux et call sites

| # | Flux métier | Call sites principaux | Méthodes FedowAPI |
|---|---|---|---|
| 1 | **Adhésion** | `BaseBillet/triggers.py:192`, webhook `fedow_connect/views.py` (Membership_fwh) | `membership.create()`, `transaction.retrieve()` |
| 2 | **Recharge wallet (Stripe)** | `BaseBillet/views.py:1138,1155`, `ApiBillet/views.py:1068` | `wallet.get_federated_token_refill_checkout()`, `retrieve_from_refill_checkout()` |
| 3 | **Remboursement** | `BaseBillet/views.py:949-978` | `wallet.refund_fed_by_signature()`, `cached_retrieve_by_signature()` |
| 4 | **Carte NFC** (scan QR, liaison, perte) | `BaseBillet/views.py:437-460, 530-560, 784-830, 915-945`, `Administration/admin_tenant.py:1345`, `BaseBillet/validators.py:1086` | `NFCcard.qr_retrieve()`, `linkwallet_cardqrcode()`, `linkwallet_card_number()`, `retrieve_card_by_signature()`, `lost_my_card_by_signature()`, `card_tag_id_retrieve()` |
| 5 | **Badge / pointeuse** | `BaseBillet/views.py:2493` | `badge.badge_in()` |
| 6 | **Wallet & soldes** | `BaseBillet/views.py:378, 1017-1075`, `Administration/admin_tenant.py:1271-1272`, `BaseBillet/validators.py:1113` | `wallet.get_or_create_wallet()` (12 appels), `cached_retrieve_by_signature()` (9), `get_total_fiducial_and_all_federated_token()` (6), `transaction.paginated_list_by_wallet_signature()` |
| 7 | **Paiement QR code (caisse)** | `BaseBillet/views.py:1470-1540`, `Administration/management/commands/launch_payment.py` | `transaction.to_place_from_qrcode()`, `asset.retrieve()` |
| 8 | **Récompenses (rewards)** | `BaseBillet/tasks.py:1804, 1875`, `api_v2/views.py:573` (API gift refill) | `transaction.refill_from_lespass_to_user_wallet()` |
| 9 | **Fédération d'assets** | `Administration/admin_tenant.py:4006` | `federation.create_fed()` |
| 10 | **Assets** (création, archivage, listing) | `Administration/admin_tenant.py:3811-3880`, `install.py:203`, `batch_new_tenant.py:212` | `asset.get_or_create_token_asset()`, `archive_asset()`, `get_accepted_assets()` |
| 11 | **Onboarding cashless (LaBoutik)** | `ApiBillet/views.py:990` | `place.link_cashless_to_place()` |
| 12 | **Dépôt bancaire / virements** | `ApiBillet/views.py:1257` (webhook Stripe), `fedow_public/views.py:29-111` | `wallet.global_asset_bank_stripe_deposit()`, `asset.retrieve_bank_deposits()`, `total_by_place_with_uuid()`, `transaction.list_by_asset()` |

Modèles Lespass déjà couplés à Fedow (à conserver / faire pointer vers `fedow_core`) :
- `BaseBillet.Membership.asset_fedow` + `fedow_transactions` (M2M `FedowTransaction`)
- `BaseBillet.FedowTransaction` (trace locale : uuid, hash, datetime)
- `BaseBillet.Price.fedow_reward_*` (récompenses)
- `Paiement_stripe.fedow_transactions` (M2M)

### Ce qui disparaît avec la fusion

- Toute la crypto **inter-service** : signature RSA des requêtes HTTP, handshake,
  vérification croisée (`_post`/`_get` de `fedow_api.py`).
- Les validators de réponses HTTP (`fedow_connect/validators.py`).
- Le cache de wallet par HTTP (`cached_retrieve_by_signature`, TTL 10 s) —
  remplacé par des requêtes ORM directes.
- `FedowConfig` (les clés API n'ont plus de raison d'être… sauf § 5.3 LaBoutik).

---

## 4. Cartographie de l'API Fedow (surface à réimplémenter ou abandonner)

~40 endpoints répartis en 8 ViewSets (détail complet dans `Fedow/fedow_core/urls.py`
et `views.py`). Synthèse par consommateur :

| Consommateur | Endpoints | Devenir après fusion |
|---|---|---|
| **Lespass** (12 flux ci-dessus) | wallet/*, transaction/*, card/* (par signature), asset/*, place/, federation/ | → appels Python directs `fedow_core.services` |
| **LaBoutik V1** (caisse, cashless) | card/ (retrieve, refund, badge, set_primary, create batch), transaction/ (create SALE/REFILL), asset/, place/handshake | ⚠️ **À trancher** : LaBoutik V1 en prod parle à Fedow en HTTP signé. Voir § 5.3 |
| **Stripe** | `/webhook_stripe/` (checkout.session.completed, terminal.reader) | → à fusionner avec les webhooks `PaiementStripe` de Lespass |
| **Root/init** | `/root_tibillet_handshake/`, `/place/` (CanCreatePlace) | → disparaît (création de place = création de tenant) |

---

## 5. Points durs identifiés

### 5.1 Collisions de modèles (le cœur du problème)

| Concept | Fedow | Lespass | À arbitrer |
|---|---|---|---|
| **User** | `FedowUser` (AUTH_USER_MODEL, email unique) | `TibilletUser` (SHARED) | TibilletUser absorbe. Mapping par email à l'import. |
| **Wallet** | `Wallet` (pems RSA, O2O user/place) | `AuthBillet.Wallet` (uuid + origin) | Décision V2 : enrichir AuthBillet.Wallet, pas de doublon. Les uuid Fedow sont déjà les pk côté Lespass → import naturel. |
| **Place** | `Place` (stripe_connect, cashless keys, lespass_domain) | `Customers.Client` (tenant) + `Configuration` | Place ≈ tenant. Champs cashless → où ? |
| **Card** | `Card` (first_tag_id, qrcode_uuid, wallet_ephemere, primary_places) | `QrcodeCashless.CarteCashless` (SHARED, tag_id, uuid, number) | Décision V2 : enrichir CarteCashless (`wallet_ephemere`). Import par tag_id/uuid. |
| **Asset** | `Asset` (7 catégories : FED, TLF, TNF, TIM, FID, BDG, SUB) | `fedow_public.AssetFedowPublic` (miroir) + `fedow_connect.Asset` | V2 a tranché : 5 catégories (TLF, TNF, FED, TIM, FID) — BDG/SUB deviennent quoi ? Adhésions et badges étaient des assets dans Fedow ; Lespass a déjà `Membership`. |
| **Federation** | `Federation` (M2M places + assets) | `fedow_public` M2M `federated_with` + V1 `FederatedPlace` (UI explorer) | 3 systèmes de fédération à réconcilier. |
| **Config** | `Configuration` (singleton, stripe keys Fernet) | `Configuration` BaseBillet + `RootConfiguration` | Les clés Stripe primaires vivent déjà côté Lespass root. |

### 5.2 Intégrité de la chaîne de transactions (bug DRIFT)

`Fedow/TECH_DEV/DRIFT/README.md` (2026-06-09) documente deux bugs de prod majeurs :
- **Lost-update** sur `Token.value` (read-modify-write non atomique) :
  1 262,60 € de sous-paiement mesuré, soldes négatifs. Patch `F()` appliqué.
- **~320 forks** dans la chaîne de hash (deux transactions pointant le même
  `previous_transaction`).

Conséquences pour l'import :
- On ne peut PAS supposer que la chaîne de hash de la prod est vérifiable.
- La décision V2 (hash individuel sans chaînage + import en 3 phases avec
  `hash=null, migrated=True`) est précisément conçue pour ça. À confirmer.
- L'import des données devra peut-être passer par une commande `reconcile_tokens`
  (existe déjà côté Fedow) avant export.

### 5.3 LaBoutik V1 — le client qu'on oublie

Le serveur de caisse LaBoutik V1 en production parle à Fedow en HTTP
(handshake RSA, API key, endpoints card/transaction). Si Fedow standalone
s'éteint au profit de `fedow_core` dans Lespass, il faut choisir :

a) **Exposer une API de compatibilité** Fedow depuis Lespass (mêmes endpoints,
   mêmes signatures) pour que les LaBoutik V1 existants continuent de fonctionner ;
b) **Migrer LaBoutik en même temps** (hors scope probable — c'est le chantier V2) ;
c) **Coexistence par population** (décision déjà prise pour V2) : anciens tenants
   restent sur Fedow standalone V1, nouveaux tenants sur fedow_core. Les 3 anciens
   serveurs restent allumés tant qu'un ancien tenant est sur V1.

### 5.4 Fédération inter-instances

Fedow est un serveur **central** : il peut fédérer des places venant de
plusieurs instances Lespass distinctes. Une fois le moteur absorbé dans UNE
instance Lespass multi-tenant, la fédération devient interne à cette instance.
→ Vérifier qu'en prod, toutes les places du Fedow central correspondent bien
à des tenants de la même instance Lespass. Sinon, il faut un plan pour les autres.

### 5.5 Multi-tenant : qui voit quoi

Fedow n'a aucune notion de tenant : ses modèles sont globaux, le scoping se fait
par `request.place` (API key). En SHARED_APPS, le scoping devra être explicite
(FK tenant sur les assets/transactions ou filtrage par wallet d'origine).
Le prototype V2 a tranché : champ `tenant` FK pour filtrage. Attention aux leaks
cross-tenant dans l'admin (checkpoint sécurité obligatoire).

### 5.6 SQLite → PostgreSQL

- UUIDs partout côté Fedow : import direct possible en conservant les pk.
- `Transaction` V2 a un `id` BigAutoField : l'uuid Fedow va dans le champ `uuid`.
- Ordre d'import contraint par les FK : Users → Wallets → Places(→tenants) →
  Assets → Tokens → Cards → Transactions (ordonnées par datetime) → CheckoutStripe.
- Le webhook Stripe Fedow et les checkouts en cours au moment de la bascule
  sont un point de bascule sensible (fenêtre de gel à prévoir).

### 5.7 Contradiction documentaire à lever

`TECH_DOC/SESSIONS/M-To-V2/INDEX.md` acte que « fedow_core reste en V2
seulement — trop couplé à laboutik ». Le présent chantier **révise cette
décision** : l'import se fait maintenant dans V1 (branche `main-fedow-import`).
→ Mettre à jour l'INDEX M-To-V2 quand le chantier sera acté.

---

## 6. Acquis réutilisables

1. **Le prototype V2 complet** (`lespass-main/fedow_core`) : modèles, services,
   admin Unfold, exceptions, signaux, commands (`verify_transactions`,
   `bootstrap_fed_asset`), et toutes les décisions documentées (mémoire projet).
2. **Les tests** : `tests/pytest/test_fedow_core.py` (8 tests) et
   `tests/playwright/tests/31-admin-asset-federation.spec.ts` existent côté V2.
3. **Les commands Fedow** : `reconcile_tokens`, `import_cards`, `demo_data`
   donnent les patterns d'import/réconciliation.
4. **La doc FALC de l'API Fedow** (`Fedow/fedow_api_documentation.md`) : décrit
   le contrat fonctionnel complet — utile comme spec de non-régression.

---

## 6 bis. Addendum 2026-06-10 — la coexistence V1/V2 existe déjà dans lespass-main

Vérification faite dans `../lespass-main` (branche `V2`) : le pattern de
coexistence par population est **déjà implémenté et testé** :

- **Critère de dispatch** : `Configuration.server_cashless` renseigné → tenant
  V1 legacy (HTTP `fedow_connect`) ; vide → tenant V2 (`fedow_core` DB direct).
  Un nouveau tenant est donc V2 par défaut, sans action.
- **Pattern vue** : dispatch en tête de vue, ancien code intact dans
  `_xxx_v1_legacy()`, nouveau code dans `_xxx_v2_fedow_core()`
  (ex. `lespass-main/BaseBillet/views.py:414-457`, ScanQrCode).
- **Cas inter-population traité** : `peut_recharger_v2()`
  (`lespass-main/BaseBillet/views.py:805`) rend 4 verdicts dont
  `wallet_legacy` — un wallet créé chez un tenant V1 ne recharge pas via V2,
  message de migration à la place. Pas de pont entre moteurs.
- **Tests existants** : `test_peut_recharger_v2.py`, `test_tokens_table_v2.py`,
  `test_transactions_table_v2.py`, `test_scan_qr_carte_v2.py`.

Limites actées par ce design :
- pas de fédération cross-population (V1 fédère avec V1, V2 avec V2) ;
- double chemin Stripe pendant la transition (checkout Fedow distant vs
  `PaiementStripe` local) ;
- le serveur Fedow standalone reste allumé tant qu'il reste un tenant V1 →
  la migration des données SQLite se fait tenant par tenant à la bascule,
  pas en une fois (répond aussi à la question 5).

## 7. Questions ouvertes pour le mainteneur

1. **Source du code** : repartir du `fedow_core` V2 (services, FALC) et
   l'adapter à V1, ou porter le `fedow_core` de Fedow tel quel puis refactorer ?
   (La recherche penche nettement pour la base V2.)
   → **Orientation mainteneur 2026-06-10 : OK pour basculer sur la base V2.**
2. **LaBoutik V1** : API de compatibilité, coexistence par population, ou
   migration simultanée ? (cf. § 5.3)
   → **Orientation mainteneur 2026-06-10 : coexistence par population**
   (anciens tenants restent V1, nouveaux tenants V2 automatiquement).
   Le pattern existe déjà en V2, cf. § 6 bis.
3. **Périmètre des catégories d'asset** : BDG (badge) et SUB (adhésion) restent-ils
   des assets, ou sont-ils réabsorbés par `Membership`/produits Lespass ?
   → **Décision mainteneur 2026-06-10 : les adhésions et badges SORTENT des
   assets Fedow.** L'adhésion est gérée par `BaseBillet.Membership` directement.
   Reste à traiter : le devenir des tokens SUB/BDG existants à l'import des
   données, et le flux « adhésion vendue en caisse » pour les tenants V2
   (audit en cours, doc 02).
4. **Fédération** : on garde les 3 mécanismes (FederatedPlace UI,
   fedow_public M2M, fedow_core.Federation) pendant la transition, ou on
   converge tout de suite vers `fedow_core.Federation` ?
5. **Données de prod** : la bascule se fait-elle en une fois (gel + import + switch)
   ou par tenant (population) ?
6. **Stripe** : fusion des webhooks Fedow dans `PaiementStripe` — qui porte
   la clé Stripe primaire (RootConfiguration ?) et le `stripe_endpoint_secret` ?

---

## 8. Esquisse de découpage (à valider — PAS un plan)

0. **Recherche** (ce document) + arbitrages mainteneur sur les questions § 7.
1. **Socle** : porter `fedow_core` (modèles + services + admin) dans V1,
   SHARED_APPS, migrations, tests. Sans toucher aux flux existants.
2. **Couture par flux** : remplacer les call sites FedowAPI flux par flux
   (ordre suggéré : wallet/soldes → adhésion → recharge Stripe → cartes NFC →
   QR pay → rewards → fédération → dépôts bancaires). `fedow_connect` reste
   en fallback tant qu'un flux n'est pas basculé.
3. **Importeur de données** : command d'import SQLite Fedow → PostgreSQL
   (3 phases hash, réconciliation tokens, vérification d'intégrité).
4. **Compat LaBoutik** (selon arbitrage § 5.3).
5. **Décommissionnement** : suppression `fedow_connect`/`fedow_public`,
   extinction du serveur Fedow.
