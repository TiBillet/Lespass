# Plan de fusion : Lespass + LaBoutik + Fedow → mono-repo v2

> Version majeure. Fusionner les trois moteurs Django en un seul mono-repo.
> Le front LaBoutik (templates, JS, cotton) est deja fait.
> Reste : modeles, backend, admin, retrait des mocks, internalisation de Fedow.
>
> Derniere mise a jour : 2026-02-28

---

## ⚠️ Points d'attention pour les sessions Claude Code

**Ce plan fait ~1600 lignes.** En debut de session, ne pas tout lire d'un coup.
Lire d'abord cette section + la phase en cours (section 15). Le reste est de la reference.

**Tests de validation par phase :** dans `memory/tests_validation.md` (fichier separe).

**Resume executif — ou on en est :**
- Branche : `integration_laboutik`
- Front LaBoutik : 100% fait (templates, JS, cotton)
- Backend : 100% mocke. Phase -1 terminee. Prochaine etape = Phase 0 (fedow_core)
- fedow_core : pas encore cree
- Toutes les decisions architecturales sont prises (section 16)

**Les 3 regles a ne jamais oublier :**
1. Ne jamais casser les vues BaseBillet qui utilisent `fedow_connect`
2. Toujours filtrer par tenant dans les queries fedow_core (SHARED_APPS = pas d'isolation auto)
3. Tout est en centimes (int), sauf `BaseBillet.Price.prix` qui reste en DecimalField (euros)

---

## Table des matieres

**Partie A — Vision d'ensemble**
1. [Architecture actuelle (3 serveurs)](#1-architecture-actuelle-3-serveurs)
2. [Architecture cible (mono-repo)](#2-architecture-cible-mono-repo)
3. [Ce qui change fondamentalement](#3-ce-qui-change-fondamentalement)
3.1. [TiBillet comme Groupware — activation modulaire](#31-tibillet-comme-groupware--activation-modulaire)
3.2. [Coexistence V1 / V2 — separation par population](#32-coexistence-v1--v2--separation-par-population)

**Partie B — Fedow : internalisation**
4. [Cartographie Fedow ancien → Lespass](#4-cartographie-fedow-ancien--lespass)
5. [Le moteur de transactions (hash chain)](#5-le-moteur-de-transactions-hash-chain)
6. [Remplacement de fedow_connect (HTTP → DB)](#6-remplacement-de-fedow_connect-http--db)
7. [Federation multi-tenant](#7-federation-multi-tenant)
8. [Multi-tarif par asset](#8-multi-tarif-par-asset-prix-en-eur-ou-en-tokens)

**Partie C — LaBoutik : backend**
9. [Cartographie LaBoutik ancien → Lespass](#9-cartographie-laboutik-ancien--lespass)
10. [Modeles a creer (laboutik + fedow_core)](#10-modeles-a-creer)
11. [Modeles existants a reutiliser](#11-modeles-existants-a-reutiliser)
12. [Remplacement des mocks — vue par vue](#12-remplacement-des-mocks--vue-par-vue)
13. [Admin Unfold](#13-admin-unfold)

**Partie D — Migration et strategie**
14. [Migration des donnees anciennes](#14-migration-des-donnees-anciennes)
15. [Ordre de travail (phases)](#15-ordre-de-travail-phases)
16. [Decisions architecturales](#16-decisions-architecturales-toutes-prises)
17. [Passages dangereux](#17-passages-dangereux)
17.8. [Stress test — 4 festivals de 25 000 personnes](#178-stress-test--4-festivals-de-25-000-personnes-en-simultane)

**Partie E — Methode de travail avec Claude Code**
18. [Regles d'execution — gardes-fous LLM](#18-regles-dexecution--gardes-fous-llm)
19. [Fichiers de reference](#19-fichiers-de-reference)

---

# PARTIE A — VISION D'ENSEMBLE

## 1. Architecture actuelle (3 serveurs)

```
┌─────────────┐     HTTP/RSA      ┌─────────────┐
│   Lespass    │ ←───────────────→ │    Fedow     │
│ (billetterie │   fedow_connect   │ (portefeuille│
│  adhesions)  │                   │  federe)     │
└──────┬───────┘                   └──────────────┘
       │                                  ↑
       │ Configuration.                   │ HTTP/RSA
       │ server_cashless                  │ fedow_connect
       │                                  │
       ▼                                  │
┌─────────────┐                           │
│  LaBoutik   │ ──────────────────────────┘
│  (caisse    │
│  cashless)  │
└─────────────┘

Chaque serveur = Django + PostgreSQL + ses propres modeles
Communication = HTTP REST + signatures RSA entre les 3
```

**Problemes :**
- 3 bases de donnees separees → pas de transactions atomiques cross-service
- Signatures RSA pour chaque requete → overhead + complexite
- Modeles dupliques (User, Wallet, CarteCashless existent dans les 3)
- Un crash Fedow = tout le cashless tombe
- Deploiement complexe (3 Docker, 3 configs, 3 migrations)

## 2. Architecture cible (mono-repo)

```
┌──────────────────────────────────────────────────┐
│                    Lespass v2                      │
│                                                    │
│  ┌────────────┐  ┌────────────┐  ┌──────────────┐ │
│  │ BaseBillet  │  │  laboutik  │  │  fedow_core  │ │
│  │(billetterie │  │  (caisse   │  │ (portefeuille│ │
│  │ adhesions)  │  │   POS)     │  │  tokens)     │ │
│  └──────┬──────┘  └─────┬──────┘  └──────┬───────┘ │
│         │               │                │          │
│         └───────────────┼────────────────┘          │
│                         │                           │
│                    PostgreSQL                        │
│                (django-tenants)                      │
│                                                    │
│  Apps shared : Customers, AuthBillet, fedow_core   │
│  Apps tenant : BaseBillet, laboutik, crowds...      │
└──────────────────────────────────────────────────┘
```

**Avantages :**
- 1 seule base → transactions atomiques (paiement + wallet + LigneArticle dans le meme commit)
- Plus de HTTP inter-service → acces DB direct
- Plus de RSA → auth interne
- 1 seul User model (TibilletUser)
- 1 seul deploiement

## 3. Ce qui change fondamentalement

| Avant | Apres | Impact |
|---|---|---|
| Fedow = serveur externe | `fedow_core` = app Django interne | **Gros refacto** |
| `fedow_connect/fedow_api.py` = client HTTP | Appels DB directs | Supprimer ~700 lignes de HTTP |
| RSA signatures inter-service | Plus necessaire | Supprimer crypto inter-service |
| `fedow_connect.Asset` = miroir cache | `fedow_core.Asset` = source de verite | Unifier les modeles |
| `fedow_public.AssetFedowPublic` = copie locale | `fedow_core.Asset` = source de verite | Supprimer le doublon |
| 3 User models | 1 seul `AuthBillet.TibilletUser` | Adapter les FK |
| Soldes via HTTP GET | `Token.objects.get(wallet=w, asset=a).value` | Direct DB |
| Transactions via HTTP POST | `Transaction.objects.create(...)` direct | Direct DB |
| Federation = M2M sur Fedow | Federation = M2M tenant-aware sur Lespass | Adapter a django-tenants |

### 3.1 TiBillet comme Groupware — activation modulaire

TiBillet n'est pas un monolithe ou tout est actif. C'est un **Groupware cooperatif** :
chaque tenant choisit les modules qu'il veut activer. Un tiers-lieu qui fait seulement
des concerts n'a pas besoin du module adhesion. Une AMAP n'a pas besoin de la billetterie.

**Modules activables depuis le dashboard admin Unfold :**

| Carte | Module Django | Description | Default |
|---|---|---|---|
| Agenda & Billetterie | `BaseBillet` (Event, Product, Price) | Evenements, reservation, vente en ligne | **Actif** |
| Adhesion & Abonnement | `BaseBillet` (Membership) | Gestion des membres, cotisations | Inactif |
| Budget contributif & Crowdfunding | `crowds` | Don, financement participatif, contribution adaptive | Inactif |
| Monnaie locale & Caisse alimentaire | `fedow_core` (Asset, Token, Transaction) | Portefeuille, tokens, paiement NFC | Inactif |
| Caisse & Restauration | `laboutik` (PointDeVente, ArticlePOS) | POS, tables, commandes, cloture | Inactif |
| Newsletter, Blog, Landing page | — | A venir | Futur |

**Techniquement :** des `BooleanField` sur `BaseBillet.Configuration` (singleton par tenant) :

```python
# BaseBillet/models.py — Configuration (django-solo)
module_billetterie = models.BooleanField(default=True)
module_adhesion = models.BooleanField(default=False)
module_crowdfunding = models.BooleanField(default=False)
module_monnaie_locale = models.BooleanField(default=False)
module_caisse = models.BooleanField(default=False)
```

**Impact sur l'interface admin :**

1. **Dashboard** : `dashboard_callback` lit les `module_*` et passe les cartes au template.
   Chaque carte affiche : nom du module, description courte, toggle actif/inactif.
2. **Sidebar Unfold** : les entrees de menu sont conditionnees par les modules actifs.
   Un tenant avec `module_adhesion=False` ne voit pas "Adhesions" dans la sidebar.
3. **URLs** : les URLs des modules inactifs retournent 404 (ou redirect vers dashboard).
   Pas de vue cachee accessible par URL directe.

**Dependances entre modules :**
- **Caisse REQUIERT Monnaie locale.** `module_caisse=True` force `module_monnaie_locale=True`.
  Le paiement NFC cashless est la raison d'etre de LaBoutik. Pas de caisse sans.
  Le `clean()` de Configuration doit imposer cette regle.
- Activer "Monnaie locale" sans "Caisse" = recharges en ligne uniquement. Possible.

### 3.2 Coexistence V1 / V2 — separation par population

Le dashboard Groupware resout le probleme de coexistence V1/V2 de maniere elegante :
**on ne migre pas les anciens tenants, on separe les populations.**

```
┌─────────────────────────────────────────────────────────┐
│  TENANTS EXISTANTS (server_cashless configure)          │
│                                                         │
│  → V1 : ancien Fedow + ancien LaBoutik (HTTP/RSA)      │
│  → Rien ne change. Rien ne casse. Jamais.               │
│  → module_caisse = False (carte grisee, "V1 active")    │
│  → Migration optionnelle PLUS TARD (Phase 6-7)          │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  NOUVEAUX TENANTS (pas de server_cashless)               │
│                                                         │
│  → V2 : fedow_core + laboutik, tout en DB direct        │
│  → Activent "Caisse & Restauration" depuis le dashboard │
│  → module_caisse = True, module_monnaie_locale = True   │
│  → Demarrent directement sur le nouveau systeme         │
└─────────────────────────────────────────────────────────┘
```

**Detection automatique :** si `Configuration.server_cashless` est renseigne,
la carte "Caisse V2" est grisee avec le message "Cashless V1 actif — migration requise".
Le tenant ne peut pas activer V2 tant que la migration n'est pas faite.

**Consequences sur le plan :**
- Phases 0-5 deviennent **immediatement livrables** en prod pour les nouveaux tenants
- Phase 6-7 (migration anciens tenants) reste necessaire mais **n'est plus bloquante**
- Le flag `use_fedow_core` est remplace par la logique :
  `module_monnaie_locale=True AND server_cashless IS NULL` → V2
  `server_cashless IS NOT NULL` → V1 (ancien systeme)
- Plus de double-chemin `if use_fedow_core` dans le nouveau code laboutik :
  les vues laboutik utilisent TOUJOURS fedow_core (elles sont nouvelles)

---

# PARTIE B — FEDOW : INTERNALISATION

## 4. Cartographie Fedow ancien → Lespass

### Modeles Fedow → ou vont-ils ?

| Modele Fedow (OLD_REPOS) | Destination Lespass v2 | Notes |
|---|---|---|
| `FedowUser` | **Supprimer** → `AuthBillet.TibilletUser` | Un seul User model. FK wallet via TibilletUser.wallet |
| `Wallet` | **Enrichir** → `AuthBillet.Wallet` | Deja existe dans AuthBillet. Ajouter `public_pem` et `name` (cf. decision 16.6). |
| `Asset` | **Creer** → `fedow_core.Asset` | Remplace `fedow_connect.Asset` + `fedow_public.AssetFedowPublic`. Source unique. |
| `Token` | **Creer** → `fedow_core.Token` | Solde d'un wallet pour un asset. `unique_together(wallet, asset)`. |
| `Transaction` | **Creer** → `fedow_core.Transaction` | LE modele critique. Hash chain, actions, montants. |
| `Card` | **Fusionner** → `QrcodeCashless.CarteCashless` | Enrichir avec `wallet_ephemere` seulement (cf. decision 16.7). |
| `Origin` | **Garder** simplifie | Batch de cartes (generation + lieu d'origine). |
| `Federation` | **Creer** → `fedow_core.Federation` | M2M entre tenants (Customers.Client) et assets. |
| `Place` | **Supprimer** → `Customers.Client` (tenant) | Chaque Place = un tenant django-tenants. |
| `Configuration` (singleton) | **Fusionner** → `BaseBillet.Configuration` | Ajouter primary_wallet, stripe keys Fedow, champs `module_*` (cf. section 3.1). |
| `CheckoutStripe` | **Fusionner** → `PaiementStripe` | Lespass gere deja Stripe. |
| `OrganizationAPIKey` | **Supprimer** | Plus besoin — auth interne. |
| `CreatePlaceAPIKey` | **Supprimer** | Lespass cree les tenants directement. |

### Modeles miroir a supprimer

Ces modeles etaient des copies locales du Fedow distant. Ils n'ont plus de raison d'etre :

| Modele miroir | Module | Pourquoi le supprimer |
|---|---|---|
| `fedow_connect.Asset` | `fedow_connect/models.py` | Remplace par `fedow_core.Asset` (source unique) |
| `fedow_public.AssetFedowPublic` | `fedow_public/models.py` | Idem — doublon du doublon |
| `fedow_connect.FedowConfig` | `fedow_connect/models.py` | Plus de serveur distant → plus de config de connexion |

## 5. Le moteur de transactions (hash chain)

### Pourquoi c'est critique

Le modele `Transaction` de Fedow est une **chaine de hachage** : chaque transaction inclut le hash de la precedente. C'est un mecanisme d'integrite (pas une vraie blockchain, mais un audit trail cryptographique).

### Comment ca marche

```
Transaction N :
  hash = SHA256(json({
    uuid_de_N,
    previous_transaction.uuid,
    previous_transaction.hash,    ← lien avec N-1
    sender.uuid,
    receiver.uuid,
    asset.uuid,
    amount,
    datetime,
    action,
    card,
    primary_card,
    metadata,
    comment,
    subscription_type
  }))
```

### Actions de transaction (10 types — v2)

BDG (badgeuse) et SUB (adhesion) sont retires.
Les adhesions sont gerees par `BaseBillet.Membership`, pas par des tokens.
La badgeuse etait une experimentation non aboutie.

| Code | Nom | Debit | Credit | Description |
|---|---|---|---|---|
| `FIRST` | Genesis | — | — | Premier bloc par asset (creation unique) |
| `CREATION` | Creation | sender | receiver | Creer des tokens (place → place ou checkout Stripe) |
| `REFILL` | Recharge | sender | receiver | Recharger un wallet (primary → user, via Stripe) |
| `SALE` | Vente | sender | receiver | Paiement cashless (user → place) |
| `QRCODE_SALE` | Vente QR | sender | receiver | Paiement par QR code (user → place) |
| `FUSION` | Fusion | sender | receiver | Fusionner wallet ephemere → wallet user |
| `REFUND` | Remboursement | sender | — | Retour (user → place, annulation) |
| `VOID` | Annulation | sender | — | Vider une carte (tout remettre a zero) |
| `DEPOSIT` | Depot bancaire | sender | receiver | Retrait de circulation (place → primary) |
| `TRANSFER` | Virement | sender | receiver | Transfert direct entre wallets |

### Decision : simplifier la hash chain (DECIDE)

**Choix retenu : hash par transaction (sans chaine) + numero sequentiel.**

Le `previous_transaction` (FK → self) est supprime. Chaque transaction a :
- un `hash` individuel (SHA256 de ses propres donnees, nullable pendant la migration)
- un `sequence_number` auto-incremente (BigIntegerField + sequence PostgreSQL) — ordonnancement global, detection de trous

Raisons :
- L'ancien Fedow verifiait rarement la chaine en pratique
- En mono-repo, PostgreSQL (ACID, WAL) garantit l'integrite
- Le `sequence_number` apporte : detection de trous, ordonnancement garanti, reference humaine pour les tickets/recus
- L'UUID reste la PK (indispensable pour les migrations/imports)

### Strategie de migration en 3 phases

**Phase 1 — Import (migration des donnees)**
- Importer les anciennes transactions avec leur UUID original et leur hash original
- Marquer `migrated=True` sur les transactions importees
- Les nouvelles transactions ont `hash=null`
- Le `sequence_number` est auto-attribue a l'import (ordre chronologique)

**Phase 2 — Production (le systeme tourne)**
- Tout fonctionne sans calcul de hash
- Le `sequence_number` s'incremente automatiquement
- Pas de verification de hash

**Phase 3 — Consolidation (quand tout est stable)**
- Management command `recalculate_hashes` : recalcule le hash individuel de chaque transaction
- Rendre le champ `hash` NOT NULL + UNIQUE
- Le hash sert alors de checksum d'integrite (pas de chaine)

## 6. Remplacement de fedow_connect (HTTP → DB)

### Ce que fait `fedow_connect/fedow_api.py` aujourd'hui

700 lignes de code qui font des requetes HTTP au serveur Fedow avec signatures RSA. Chaque methode = 1 appel HTTP.

### Comment ca se traduit en acces DB direct

| Appel HTTP actuel | Remplacement DB direct | Module |
|---|---|---|
| `WalletFedow.get_total_fiducial_and_all_federated_token(user)` | `Token.objects.filter(wallet=user.wallet).aggregate(Sum('value'))` | `fedow_core` |
| `WalletFedow.retrieve_by_signature(user)` | `Token.objects.filter(wallet=user.wallet).select_related('asset')` | `fedow_core` |
| `TransactionFedow.to_place_from_qrcode(user, amount, asset)` | `Transaction.objects.create(action=SALE, sender=user.wallet, receiver=place.wallet, ...)` + debit/credit Token | `fedow_core` |
| `TransactionFedow.refill_from_lespass_to_user_wallet(user, amount, asset)` | `Transaction.objects.create(action=REFILL, ...)` + credit Token | `fedow_core` |
| `NFCcardFedow.card_tag_id_retrieve(tag_id)` | `CarteCashless.objects.get(tag_id=tag_id)` | `QrcodeCashless` |
| `AssetFedow.get_accepted_assets()` | `Asset.objects.filter(active=True)` + federation filter | `fedow_core` |
| `MembershipFedow.create(membership)` | `BaseBillet.Membership.objects.create(...)` — plus geree par tokens | `BaseBillet` |
| `FederationFedow.create_fed(user, asset, place_added, place_origin)` | `Federation.assets.add(asset)` + `federation.tenants.add(client)` | `fedow_core` |

### Strategie de migration progressive

On ne peut pas tout casser d'un coup. Strategie en 3 etapes :

**Etape 1 : Creer `fedow_core` avec les modeles**
- `Asset`, `Token`, `Transaction`, `Federation`
- Enrichir `AuthBillet.Wallet` (ajouter `public_pem`, `name`)
- Migrations

**Etape 2 : Creer une couche de service `fedow_core/services.py`**
- Meme interface que `fedow_connect/fedow_api.py` mais avec du DB direct
- Les vues LaBoutik et BaseBillet appellent cette couche
- Pas de changement dans les vues

Le service suit le pattern FALC du skill `/django-htmx-readable` : methodes statiques explicites,
noms verbeux, commentaires bilingues. Chaque methode de `fedow_api.py` a son equivalent DB direct
dans `services.py` (cf. tableau ci-dessus).

**Etape 3 : Supprimer fedow_connect**
- Une fois que tout passe par `fedow_core/services.py`
- Supprimer `fedow_connect/fedow_api.py` (HTTP client)
- Supprimer `fedow_connect/utils.py` (RSA, sauf si garde pour autre chose)
- Supprimer `fedow_connect.Asset` et `fedow_connect.FedowConfig`
- Garder `fedow_connect/validators.py` si certains validateurs sont reutiles

## 7. Federation multi-tenant

### Comment ca marche dans l'ancien Fedow

```
Federation (M2M places + M2M assets)
  → Place A cree un Asset "Monnaie Locale"
  → Place A invite Place B dans la Federation
  → Place B accepte
  → Les cartes de Place A fonctionnent chez Place B pour cet Asset
```

### Comment ca se traduit avec django-tenants

Chaque "Place" = un `Customers.Client` (tenant). La federation = une relation cross-tenant.

**⚠️ PIEGE : django-tenants isole les schemas.** Un modele dans un schema ne voit pas les donnees d'un autre schema.

### DECISION PRISE : `fedow_core` dans `SHARED_APPS`

`fedow_core` est dans `SHARED_APPS`. Les tables vivent dans le schema public.

**Pourquoi :**
- Un utilisateur peut avoir des assets sur 15+ lieux differents
- La page "Mon compte" doit afficher tous ses tokens en une seule requete
- `Token.objects.filter(wallet=user.wallet)` → tous les soldes, tous les lieux, zero N+1
- Avec TENANT_APPS, il faudrait boucler sur chaque schema → cauchemar de performance

**Consequence :** Chaque modele fedow_core a un champ `tenant` (FK → Customers.Client) pour le filtrage. Toujours filtrer par tenant dans les vues tenant-scoped. Ne jamais faire `Asset.objects.all()` nu dans une vue.

```python
# MAL — retourne les assets de TOUS les tenants / BAD — returns ALL tenants' assets
assets = Asset.objects.all()

# BIEN — filtre par tenant courant / GOOD — filters by current tenant
assets_du_tenant = Asset.objects.filter(tenant_origin=connection.tenant)

# BIEN — assets federes (le tenant courant + ses federations)
# GOOD — federated assets (current tenant + its federations)
assets_accessibles = AssetService.obtenir_assets_accessibles(tenant=connection.tenant)

# BIEN — vue "Mon compte" (tous les lieux d'un user)
# GOOD — "My account" view (all places for one user)
tous_les_tokens = Token.objects.filter(wallet=user.wallet, asset__active=True)
```

## 8. Multi-tarif par asset (prix en EUR ou en tokens)

### Le besoin

Un produit peut avoir plusieurs tarifs dans des assets differents.
Exemple : une place de concert = 20€ **OU** 5 tokens temps.
L'acheteur choisit avec quel asset il paye.

### Comment ca s'integre dans les modeles existants

#### Sur `BaseBillet.Price` (billetterie en ligne)

Ajouter un champ `asset` optionnel :

```
Price
├── ... (champs existants inchanges)
├── prix (DecimalField) — montant dans l'asset (ou en EUR si asset=null)
└── asset (FK → fedow_core.Asset, nullable, blank=True) — NOUVEAU
```

- `asset=null` → prix en EUR (comportement actuel, rien ne casse)
- `asset=monnaie_temps` → prix libelle en tokens temps

Exemple concret :

```
Product "Concert Rock"
├── Price "Plein tarif"     → prix=20.00, asset=null       → 20 EUR
├── Price "Tarif temps"     → prix=5.00,  asset=TIM_asset  → 5 tokens temps
└── Price "Tarif reduit"    → prix=12.00, asset=null       → 12 EUR
```

Un Product peut avoir autant de Price qu'on veut avec des assets differents.
Le choix se fait au moment de l'achat (page produit ou panier).

#### Sur `laboutik.ArticlePOS` (caisse POS)

Le modele a deja `prix` (int centimes) et `fedow_asset` (FK → Asset, nullable).
Meme convention :

- `fedow_asset=null` → prix en centimes EUR
- `fedow_asset=monnaie_temps` → prix en unites de cet asset

Pour un article vendable en EUR **et** en TIM, creer 2 ArticlePOS
lies au meme Product :

```
ArticlePOS "Concert (€)"   → prix=2000, fedow_asset=null      → 20 EUR
ArticlePOS "Concert (TIM)" → prix=500,  fedow_asset=TIM_asset  → 5 tokens
```

C'est le plus FALC : pas de M2M, pas de modele intermediaire.
Le caissier voit 2 boutons. L'admin cree 2 articles.

### Paniers mixtes en caisse (multi-asset)

Si le panier contient des articles dans des assets differents :

```
Panier :
  Biere    → 500 (EUR)
  Concert  → 500 (TIM)
  Sandwich → 800 (EUR)
────────────────────────
Totaux : 13.00 EUR + 5 TIM
```

Le total n'est plus un seul nombre — c'est **un total par asset**.

Le paiement fractionne (qui existe deja dans le front) gere ce pattern :
1. Lecture NFC → debiter 5 TIM pour le concert
2. Reste 13€ → payer en especes ou CB

#### Impact sur `PaiementViewSet`

La methode `payer()` doit regrouper les articles par asset (dict `fedow_asset → liste d'articles`),
puis payer chaque groupe separement : EUR → especes/CB, tokens → TransactionService.creer_vente().

#### Impact sur le front (JS)

Le front doit :
1. Calculer les totaux par asset (pas juste un total global)
2. Afficher : "Total : 13€ + 5 TIM"
3. Au moment du paiement : proposer NFC pour les tokens, especes/CB pour les EUR

Le JS `addition.js` utilise deja Big.js pour les calculs. Il faut ajouter
un regroupement par `fedow_asset` dans le calcul du total.

**⚠️ C'est un changement front non trivial.** Le template `hx_display_type_payment.html`
doit aussi s'adapter (montrer quel montant sera debite en tokens vs en EUR).

### Migration : rien ne casse

L'ajout de `asset` sur Price est nullable. Tous les Price existants ont `asset=null` → EUR.
Aucune migration de donnees necessaire. Backward compatible a 100%.

---

# PARTIE C — LABOUTIK : BACKEND

## 9. Cartographie LaBoutik ancien → Lespass

| Ancien modele (OLD_REPOS/LaBoutik) | Destination Lespass v2 | Statut | Notes |
|---|---|---|---|
| `Configuration` (singleton, 40+ champs) | `BaseBillet.Configuration` | **Enrichir** | Ajouter : horaires, pied de ticket, prix adhesion, calcul adhesion, Sunmi printer config |
| `Articles` | `laboutik.ArticlePOS` + lien `BaseBillet.Product` | **Creer** | Couleur, icon, poid, methode, groupement |
| `Categorie` | `laboutik.CategorieArticlePOS` | **Creer** | Couleur, icon, TVA, poids |
| `PointDeVente` | `laboutik.PointDeVente` | **Creer** | Config PV, M2M articles/categories |
| `MoyenPaiement` | `fedow_core.Asset` | **Absorber** | Categories TLF/TNF/FED/TIM/FID (BDG et SUB retires) |
| `CarteCashless` | `QrcodeCashless.CarteCashless` | **Enrichir** | Ajouter `wallet_ephemere` seulement (cf. decision 16.7) |
| `Assets` (soldes) | `fedow_core.Token` | **Nouveau** | Token = solde d'un wallet pour un asset |
| `Membre` | `AuthBillet.TibilletUser` + `BaseBillet.Membership` | **Existe** | |
| `CarteMaitresse` | `laboutik.CarteMaitresse` | **Creer** | Carte responsable → PV autorises |
| `Table` + `CategorieTable` | `laboutik.Table` + `laboutik.CategorieTable` | **Creer** | Plan de salle restaurant |
| `CommandeSauvegarde` | `laboutik.CommandeSauvegarde` | **Creer** | Commandes en cours |
| `ArticleCommandeSauvegarde` | `laboutik.ArticleCommandeSauvegarde` | **Creer** | Lignes de commande |
| `ArticleVendu` | `BaseBillet.LigneArticle` | **Existe** | sale_origin=LABOUTIK, sended_to_laboutik |
| `ClotureCaisse` | `laboutik.ClotureCaisse` | **Creer** | Rapport fin de service |
| `Appareil` + `Appairage` | `BaseBillet.PairingDevice` + `LaBoutikAPIKey` | **Existe** | Discovery remplace RSA |
| `Couleur` | — | **Absorber** | Hexa directement sur les modeles |
| `Methode` | — | **Absorber** | Choices CharField sur ArticlePOS |
| `TauxTVA` | `BaseBillet.Tva` | **Existe** | |
| `Wallet` | `AuthBillet.Wallet` | **Existe** | A enrichir si necessaire |
| `Place` | `Customers.Client` | **Existe** | = tenant django-tenants |
| `ConfigurationStripe` | `PaiementStripe` | **Existe** | |

## 10. Modeles a creer

### 10.1 App `fedow_core` — Moteur de portefeuille

**⚠️ Nouvelle app Django** a creer. Remplace le serveur Fedow standalone.

```
fedow_core/
├── __init__.py
├── apps.py
├── models.py        ← Asset, Token, Transaction, Federation
├── services.py      ← Couche de service (remplace fedow_api.py)
├── admin.py         ← Admin Unfold
├── migrations/
└── management/
    └── commands/
        ├── import_fedow_data.py    ← Phase 6 : migration des donnees de l'ancien Fedow
        ├── recalculate_hashes.py   ← Phase 7 : recalcul des hash individuels
        └── verify_transactions.py  ← Verification integrite (sequence, soldes, tenant)
```

#### `Asset` — Monnaie/token

5 categories (v2). BDG (badgeuse) et SUB (adhesion) sont retires.
Les adhesions sont gerees par `BaseBillet.Membership`.

```
Asset
├── uuid (PK)
├── name (CharField, 100)
├── currency_code (CharField, 3) — "EUR", "TMP", etc.
├── category (CharField choices)
│   TLF = Token local fiduciaire (monnaie locale adossee EUR)
│   TNF = Token local cadeau (non fiduciaire)
│   FED = Fiduciaire federee (Stripe, unique dans le systeme)
│   TIM = Monnaie temps
│   FID = Points de fidelite
├── wallet_origin (FK → Wallet) — qui a cree cet asset
├── tenant_origin (FK → Customers.Client) — tenant createur
├── active (BooleanField, default=True)
├── archive (BooleanField, default=False)
├── id_price_stripe (CharField, nullable) — pour FED (recharge Stripe)
├── created_at (DateTimeField, auto_now_add)
└── last_update (DateTimeField, auto_now)
```

#### `Token` — Solde d'un wallet pour un asset

```
Token
├── uuid (PK)
├── wallet (FK → Wallet)
├── asset (FK → Asset)
├── value (IntegerField, default=0) — en centimes
└── UNIQUE CONSTRAINT (wallet, asset)
```

C'est LE modele qui repond a "combien a-t-il sur sa carte ?".
`Token.objects.filter(wallet=user.wallet)` → tous ses soldes.

#### `Transaction` — Historique immuable

```
Transaction
├── uuid (PK) — conserve pour migrations/imports
├── sequence_number (BigIntegerField, unique, editable=False) — auto-increment global via sequence PostgreSQL
├── hash (CharField, 64, nullable, unique) — SHA256 individuel (pas de chaine)
│   nullable pendant Phase 1-2, NOT NULL apres Phase 3
├── migrated (BooleanField, default=False) — True pour les transactions importees
├── sender (FK → Wallet)
├── receiver (FK → Wallet)
├── asset (FK → Asset)
├── amount (PositiveIntegerField) — en centimes
├── action (CharField choices) — SALE, REFILL, etc. (10 types, cf. annexe B)
├── card (FK → CarteCashless, nullable) — carte utilisee
├── primary_card (FK → CarteCashless, nullable) — carte maitresse
├── datetime (DateTimeField)
├── comment (TextField, blank=True)
├── metadata (JSONField, default=dict)
├── subscription_type (CharField, nullable) — legacy (SUBSCRIBE retire, conserve pour import)
├── subscription_start_datetime (DateTimeField, nullable)
├── checkout_stripe (FK → PaiementStripe, nullable)
├── tenant (FK → Customers.Client) — pour filtrage si SHARED_APP
└── ip (GenericIPAddressField, default='0.0.0.0')
```

**⚠️ Note technique sur `sequence_number` :**
En Django 4.2, `BigAutoField` ne peut etre que la PK. Comme `uuid` est la PK,
on utilise un `BigIntegerField` + une sequence PostgreSQL dans la migration :
```python
# Dans la migration Django / In the Django migration
migrations.RunSQL(
    "CREATE SEQUENCE IF NOT EXISTS fedow_core_transaction_seq;",
    "DROP SEQUENCE IF EXISTS fedow_core_transaction_seq;",
)
# Puis sur le champ / Then on the field
migrations.RunSQL(
    "ALTER TABLE fedow_core_transaction ALTER COLUMN sequence_number SET DEFAULT nextval('fedow_core_transaction_seq');",
    "ALTER TABLE fedow_core_transaction ALTER COLUMN sequence_number DROP DEFAULT;",
)
```
PostgreSQL gere l'auto-increment. Django voit un `BigIntegerField(unique=True, editable=False)`.
Le `sequence_number` est global (cross-tenant) car `fedow_core` est en SHARED_APPS.
Aucun verrou applicatif (`select_for_update`) — PostgreSQL gere la sequence tout seul.

**Pas de `sequence_par_asset`.** On a retire le compteur par asset pour eviter les verrous
cross-tenant sur les assets federes. L'audit humain se fait via `LigneArticle` (table VENTES
du lieu), pas via la table Transaction federee. La verification d'integrite de la sequence
globale se fait via un management command (cf. ci-dessous).

**Note :** `previous_transaction` (FK → self) est supprime. Le `sequence_number` le remplace.

**Le `save()` de Transaction doit :**
1. Valider les regles metier (solde suffisant, etc.)
2. Mettre a jour les Token (debit sender, credit receiver)
3. Etre dans une transaction DB atomique
4. Le `sequence_number` est auto-attribue par PostgreSQL (nextval)
5. Le hash est calcule en Phase 3 uniquement (management command `recalculate_hashes`)

**Verification d'integrite — management command `verify_transactions` :**

Pas de verrou a l'ecriture → on verifie apres coup, a la demande :
```python
# fedow_core/management/commands/verify_transactions.py
# Verifie que la sequence globale n'a pas de trous
# Verifie que chaque Transaction a un sender/receiver/asset valide
# Verifie que la somme des Token correspond aux Transaction
# Usage : docker exec lespass_django poetry run python manage.py verify_transactions
# Usage par tenant : manage.py verify_transactions --tenant=mon-lieu
```

L'audit comptable se fait sur `LigneArticle` (la table VENTES du lieu).
C'est cet objet qu'un humain ou un commissaire aux comptes verifie, pas Transaction.

#### `Federation` — Partage d'assets entre tenants

```
Federation
├── uuid (PK)
├── name (CharField, 100, unique)
├── description (TextField, blank=True)
├── tenants (M2M → Customers.Client)
└── assets (M2M → Asset)
```

### 10.2 App `laboutik` — Modeles POS

#### `PointDeVente`

```
PointDeVente
├── uuid (PK)
├── name (CharField, unique par tenant)
├── icon (CharField)
├── comportement (CharField choices: DIRECT/KIOSK/CASHLESS)
├── service_direct (BooleanField, default=True)
├── afficher_les_prix (BooleanField, default=True)
├── accepte_especes (BooleanField, default=True)
├── accepte_carte_bancaire (BooleanField, default=True)
├── accepte_cheque (BooleanField, default=False)
├── accepte_commandes (BooleanField, default=False)
├── poid_liste (SmallIntegerField, default=0)
├── hidden (BooleanField, default=False)
├── categories (M2M → CategorieArticlePOS)
└── articles (M2M → ArticlePOS)
```

#### `CategorieArticlePOS`

```
CategorieArticlePOS
├── uuid (PK)
├── name (CharField)
├── icon (CharField)
├── couleur_texte (CharField, 7) — hexa
├── couleur_fond (CharField, 7) — hexa
├── poid_liste (SmallIntegerField, default=0)
├── tva (FK → BaseBillet.Tva, nullable)
└── cashless (BooleanField, default=False)
```

#### `ArticlePOS`

```
ArticlePOS
├── uuid (PK)
├── product (FK → BaseBillet.Product, nullable) — lien catalogue
├── name (CharField)
├── prix (IntegerField) — en centimes
├── methode (CharField choices: VT/RE/RC/AD/CR/VC/FR/BI/FD)
├── couleur_texte (CharField, hexa)
├── couleur_fond (CharField, hexa)
├── icon (CharField, nullable)
├── poid_liste (SmallIntegerField)
├── categorie (FK → CategorieArticlePOS)
├── archive (BooleanField, default=False)
├── fractionne (BooleanField, default=False)
├── fedow_asset (FK → fedow_core.Asset, nullable)
├── moyens_paiement (CharField) — "espece|nfc|carte_bancaire"
├── besoin_tag_id (BooleanField, default=False)
└── groupe (CharField, nullable)
```

#### `CarteMaitresse`

```
CarteMaitresse
├── uuid (PK)
├── carte (OneToOne → QrcodeCashless.CarteCashless)
├── points_de_vente (M2M → PointDeVente)
├── edit_mode (BooleanField, default=False)
└── datetime (DateTimeField, auto_now_add)
```

#### `Table` + `CategorieTable`

```
CategorieTable
├── name (CharField, unique)
└── icon (CharField)

Table
├── uuid (PK)
├── name (CharField, unique par tenant)
├── categorie (FK → CategorieTable)
├── poids (SmallIntegerField, default=0)
├── statut (CharField: L=Libre, O=Occupee, S=Servie)
├── ephemere (BooleanField, default=False)
├── archive (BooleanField, default=False)
├── position_top (IntegerField, nullable)
└── position_left (IntegerField, nullable)
```

#### `CommandeSauvegarde` + `ArticleCommandeSauvegarde`

```
CommandeSauvegarde
├── uuid (PK)
├── service (UUIDField) — identifiant du service en cours
├── responsable (FK → TibilletUser)
├── table (FK → Table, nullable)
├── datetime (DateTimeField, auto_now_add)
├── statut (CharField: OPEN/SERVED/PAID/CANCEL)
├── commentaire (TextField, blank=True)
└── archive (BooleanField, default=False)

ArticleCommandeSauvegarde
├── commande (FK → CommandeSauvegarde)
├── article (FK → ArticlePOS)
├── qty (SmallIntegerField, default=1)
├── reste_a_payer (IntegerField) — en centimes
├── reste_a_servir (SmallIntegerField)
└── statut (CharField: EN_ATTENTE/EN_COURS/PRET/SERVI/ANNULE)
```

#### `ClotureCaisse`

```
ClotureCaisse
├── uuid (PK)
├── point_de_vente (FK → PointDeVente)
├── responsable (FK → TibilletUser)
├── datetime_ouverture (DateTimeField)
├── datetime_cloture (DateTimeField, auto_now_add)
├── total_especes (IntegerField) — en centimes
├── total_carte_bancaire (IntegerField) — en centimes
├── total_cashless (IntegerField) — en centimes
├── total_general (IntegerField) — en centimes
├── nombre_transactions (IntegerField)
└── rapport_json (JSONField)
```

## 11. Modeles existants a reutiliser

- `BaseBillet.LigneArticle` — ledger de ventes (sale_origin=LABOUTIK)
- `BaseBillet.Product` + `Price` — catalogue produits
- `BaseBillet.Membership` — adhesions (status=LABOUTIK)
- `QrcodeCashless.CarteCashless` — cartes NFC
- `BaseBillet.Configuration` — config tenant
- `AuthBillet.Wallet` — portefeuille utilisateur
- `BaseBillet.Tva` — taux TVA

## 12. Remplacement des mocks — vue par vue

### Fichiers impactes par phase

**Phase 2 (mocks → DB) — fichiers Python :**

| Fichier | Modification |
|---|---|
| `laboutik/views.py` | Remplacer tous les appels `mockData.*` par des queries ORM. C'est LE fichier central. |
| `laboutik/utils/method.py` | A terme supprimer (Phase 7). Pendant Phase 2, adapter pour lire la DB au lieu du JSON. |
| `laboutik/utils/mockData.py` | Ne plus importer. Les vues accedent directement aux modeles. |

**Phase 2 — templates potentiellement impactes :**

| Template | Raison |
|---|---|
| `laboutik/templates/laboutik/views/ask_primary_card.html` | Si les URLs HTMX changent |
| `laboutik/templates/laboutik/views/pv_route.html` | Donnees PV passees par context (pas par mock) |
| `laboutik/templates/laboutik/partial/hx_display_type_payment.html` | Context articles depuis DB |
| `laboutik/templates/laboutik/partial/hx_confirm_payment.html` | Idem |
| `laboutik/templates/laboutik/partial/hx_payment.html` | Idem |
| `laboutik/templates/laboutik/partial/hx_read_nfc.html` | Si URLs changent |
| `laboutik/templates/laboutik/partial/hx_card_feedback.html` | Solde reel depuis Token au lieu de mock |

**Phase 3 (integration fedow_core) — fichiers supplementaires :**

| Fichier | Modification |
|---|---|
| `fedow_core/services.py` | WalletService, TransactionService — creation en Phase 0, utilisation en Phase 3 |
| `laboutik/views.py` | Ajouter les imports fedow_core, appeler les services dans `_payer_par_nfc()` et `retour_carte()` |

**Multi-tarif (section 8) — hors phases 0-7, a planifier separement :**

| Fichier | Modification |
|---|---|
| `laboutik/static/laboutik/js/addition.js` | Regrouper les totaux par asset au lieu d'un total unique. ~800 lignes, changement delicat. |
| `laboutik/templates/laboutik/partial/hx_display_type_payment.html` | Afficher "Total : 13€ + 5 TIM" au lieu d'un seul total. |

**⚠️ Le JS est le point le plus risque.** Prevoir une session dediee avec le mainteneur pour cette partie.

### CaisseViewSet

#### `list()` — Page d'attente carte primaire
- OK tel quel (template statique + NFC).

#### `carte_primaire()` — Validation carte NFC
1. `CarteCashless.objects.get(tag_id=tag_id)`
2. `CarteMaitresse.objects.get(carte=carte_cashless)`
3. `carte_maitresse.points_de_vente.all()` → PV autorises
4. Si un seul PV → redirect ; si plusieurs → choix

#### `point_de_vente()` — Interface POS
1. `PointDeVente.objects.prefetch_related('categories', 'articles').get(uuid=uuid_pv)`
2. `stateJson` : `Configuration.get_solo()` + donnees PV
3. Tables si `accepte_commandes=True`

### PaiementViewSet

#### `moyens_paiement()` + `confirmer()`
- Meme logique, `ArticlePOS.objects.get(uuid=uuid)` au lieu de mock

#### `payer()` — Le gros morceau

##### `_payer_par_carte_ou_cheque()`
`transaction.atomic()` → boucle sur articles → `LigneArticle.create(sale_origin='LB', payment_method='CC')`.

##### `_payer_en_especes()`
Idem avec `payment_method='CA'`.

##### `_payer_par_nfc()` — Integration fedow_core

Flux : CarteCashless.get(tag_id) → carte.user.wallet → WalletService.obtenir_solde_total()
→ si suffisant : `transaction.atomic()` (TransactionService.creer_vente + LigneArticle.create)
→ si insuffisant : partial `hx_funds_insufficient` avec montant manquant.

#### `retour_carte()` — Vrai solde depuis fedow_core

WalletService.obtenir_solde_total(utilisateur) + Membership.objects.filter(user=utilisateur).

## 13. Admin Unfold

> **Note :** Le dashboard Groupware (cartes de modules) et la sidebar conditionnelle
> sont traites en Phase -1 (section 15). Cette section concerne uniquement
> l'enregistrement des modeles laboutik et fedow_core dans Unfold.

### Modeles laboutik

| Modele | Section menu |
|---|---|
| `PointDeVente` | LaBoutik > Points de vente |
| `CategorieArticlePOS` | LaBoutik > Categories |
| `ArticlePOS` | LaBoutik > Articles |
| `CarteMaitresse` | LaBoutik > Cartes maitresses |
| `Table` | LaBoutik > Tables |
| `CommandeSauvegarde` | LaBoutik > Commandes en cours |
| `ClotureCaisse` | LaBoutik > Clotures |

### Modeles fedow_core

| Modele | Section menu |
|---|---|
| `Asset` | Fedow > Monnaies et tokens |
| `Federation` | Fedow > Federations |
| `Transaction` | Fedow > Transactions (lecture seule) |
| `Token` | Fedow > Soldes (lecture seule, accessible via carte/user) |

---

# PARTIE D — MIGRATION ET STRATEGIE

## 14. Migration des donnees anciennes

### 14.1 Migration Fedow → fedow_core

L'ancien serveur Fedow a sa propre base PostgreSQL. Les donnees doivent etre importees.

**Strategie : management command `import_fedow_data`**

```
Ordre d'import (respecter les FK) :
1. Asset (monnaies) → fedow_core.Asset
2. Wallet (portefeuilles) → AuthBillet.Wallet (enrichir)
3. Card (cartes) → QrcodeCashless.CarteCashless (enrichir)
4. Token (soldes) → fedow_core.Token
5. Transaction (historique) → fedow_core.Transaction
6. Federation → fedow_core.Federation
```

**⚠️ Pieges :**
- Les UUID doivent etre preserves (PK de Fedow = PK dans Lespass)
- Les hash de Transaction doivent etre recalcules si le format change
- Les FedowUser doivent etre mappes aux TibilletUser existants (par email)
- Les Place doivent etre mappees aux Customers.Client (par domaine ou UUID)

### 14.2 Migration LaBoutik → laboutik

L'ancien LaBoutik a sa propre base PostgreSQL. Donnees a migrer :

```
Ordre d'import :
1. CategorieArticlePOS ← Categorie (+ Couleur inline)
2. ArticlePOS ← Articles (+ Methode inline, prix deja en centimes)
3. PointDeVente ← PointDeVente (+ M2M articles/categories)
4. CarteMaitresse ← CarteMaitresse (tag_id → CarteCashless)
5. Table ← Table (+ CategorieTable)
6. CommandeSauvegarde ← CommandeSauvegarde (si commandes en cours)
7. ArticleVendu → DEJA dans LigneArticle (via webhook historique)
```

**⚠️ Pieges :**
- Les CarteCashless de LaBoutik doivent matcher celles de Fedow (meme tag_id)
- Les MoyenPaiement de LaBoutik = les Asset de Fedow (mapper par UUID ou name)
- Les ArticleVendu ont un `hash_fedow` qui pointe vers Transaction de Fedow → verifier la correspondance

### 14.3 Script de verification post-migration

Apres chaque import, verifier :
- Somme des Token.value == somme attendue par asset
- Nombre de Transaction == nombre dans l'ancien Fedow
- Chaque CarteCashless a un wallet lie
- Chaque CarteMaitresse pointe vers une CarteCashless existante
- Les transactions importees ont `migrated=True` et un `sequence_number` croissant
- `manage.py verify_transactions` passe sans erreur

## 15. Ordre de travail (phases)

### Phase -1 — Dashboard Groupware (PREMIERE ETAPE) ✅ TERMINEE

Pas de dependance technique. Livrable immediatement sur la branche actuelle.
Habitue les utilisateurs a l'activation modulaire avant meme que la V2 soit prete.

1. ✅ Ajouter les champs `module_*` sur `BaseBillet.Configuration` (cf. section 3.1)
2. ✅ Migration : `migrate_schemas --executor=multiprocessing`
3. ✅ Creer le template dashboard Unfold avec les cartes de modules
4. ✅ `dashboard_callback` : lire les `module_*` et passer au template
5. ✅ Conditionner la sidebar Unfold : masquer les menus des modules inactifs
6. ⚠️ Garde-fou carte "Caisse V2" : la carte est grisee visuellement si `server_cashless` est renseigne
   (badge "V1 active", switch desactive). Mais le `clean()` de Configuration n'empeche PAS encore
   l'activation par code. A implementer en Phase 0 quand fedow_core et laboutik existent.
   Idem pour la contrainte `module_caisse → force module_monnaie_locale`.
7. ✅ Tests : `tests/playwright/tests/29-admin-proxy-products.spec.ts`

**Bonus realises (hors plan initial) :**

- **Proxy models Product** : `TicketProduct` et `MembershipProduct` (zero migration, meme table).
  Chaque proxy filtre par `categorie_article` et a son propre admin avec formulaire adapte.
  Le `ProductAdmin` original reste enregistre (autocomplete EventAdmin, URLs existantes).
- **Reorganisation sidebar** :
  - "Informations generales" : Tableau de bord, Parametres, Comptes utilisateur·ice
  - "Adhesions" (conditionnel `module_adhesion`) : Membership products, Subscriptions
  - "Billetterie" (conditionnel `module_billetterie`) : Ticket products, Carrousel, Codes promo, Tags, Adresses, Evenements, Reservations, Billets, Scan App
  - Suppression de la section "Utilisateur·ices" (comptes dans Infos generales, adhesions dans leur section)
  - Carrousel deplace de Infos generales vers Billetterie (utilise uniquement dans les templates event)
- **HX-Refresh** : apres toggle d'un module, la sidebar se recharge automatiquement

**Fichiers modifies :**

| Fichier | Modification |
|---|---|
| `BaseBillet/models.py` | 5 champs `module_*` sur Configuration + 2 proxy models (TicketProduct, MembershipProduct) |
| `Administration/admin_tenant.py` | `get_sidebar_navigation()` dynamique, `MODULE_FIELDS`, `_build_modules_context()`, `module_toggle` (HX-Refresh), proxy forms + admins |
| `TiBillet/settings.py` | SIDEBAR.navigation → callable string `"Administration.admin_tenant.get_sidebar_navigation"` |
| `Administration/templates/admin/dashboard.html` | Template cartes modules avec switches HTMX |
| `Administration/templates/admin/dashboard_module_modal.html` | Modal HTMX confirmation toggle |
| `Administration/templates/admin/index.html` | Include dashboard |
| `tests/playwright/tests/29-admin-proxy-products.spec.ts` | Tests proxy admins + sidebar (nouveau) |

### Phase 0 — fedow_core : fondations (PRIORITE MAXIMALE)

C'est le socle de tout. Sans fedow_core, pas de paiement cashless.

1. Creer l'app `fedow_core` (SHARED_APPS) avec `Asset`, `Token`, `Transaction`, `Federation`
2. `Transaction` : uuid PK + `sequence_number` (BigIntegerField + sequence PostgreSQL) + `hash` nullable
3. Ecrire `fedow_core/services.py` (WalletService, TransactionService, AssetService)
4. Migrations + tests unitaires (cf. MEMORY.md Phase 0)
5. Admin Unfold pour Asset, Token, Transaction
6. **Test securite** : verifier l'isolation tenant (pas de leak cross-tenant)

### Phase 1 — laboutik : modeles POS

7. Creer les modeles dans `laboutik/models.py` :
   - `PointDeVente`, `CategorieArticlePOS`, `ArticlePOS`
   - `CarteMaitresse`
   - `Table`, `CategorieTable`
8. Migrations
9. Admin Unfold
10. Donnees initiales (fixture ou management command)

### Phase 2 — laboutik : remplacement des mocks

11. `carte_primaire()` : CarteMaitresse + CarteCashless
12. `point_de_vente()` : charger depuis DB
13. `moyens_paiement()` + `confirmer()` : articles depuis DB
14. `_payer_par_carte_ou_cheque()` + `_payer_en_especes()` : creer LigneArticle

### Phase 3 — Integration fedow_core dans laboutik

15. `_payer_par_nfc()` : WalletService + TransactionService
16. `retour_carte()` : vrai solde depuis Token
17. Recharges (RE/RC) : TransactionService.creer_recharge()
18. Adhesions (AD) : TransactionService + Membership

### Phase 4 — Mode restaurant

19. Modeles : `CommandeSauvegarde`, `ArticleCommandeSauvegarde`
20. Vues : gestion commandes par table
21. Tables : mise a jour statuts

### Phase 5 — Cloture, rapports, Celery

22. `ClotureCaisse` : modele + vue
23. Rapport : calcul totaux par moyen de paiement
24. Taches Celery : cloture auto, rapport quotidien

### Phase 6 — Migration des donnees

25. Management command `import_fedow_data`
26. Management command `import_laboutik_data`
27. Script de verification
28. Tests sur un environnement de staging avec vraies donnees

### Phase 7 — Consolidation et nettoyage

29. Management command `recalculate_hashes` : recalcul des hash individuels sur toutes les transactions
30. Migration Django : `hash` NOT NULL + UNIQUE
31. Supprimer les mocks : `utils/mockData.py`, `utils/dbJson.py`, `utils/mockDb.json`, `utils/method.py`
32. Supprimer `fedow_connect/fedow_api.py` (remplace par fedow_core/services.py)
33. Supprimer `fedow_connect.Asset`, `fedow_connect.FedowConfig`
34. Supprimer ou archiver `fedow_public.AssetFedowPublic` (remplace par fedow_core.Asset)
35. Adapter les vues `fedow_public` pour utiliser `fedow_core.Asset`
36. Supprimer les templates/JS legacy
37. Tests Playwright complets

## 16. Decisions architecturales (toutes prises)

### ~~16.1 fedow_core : SHARED_APPS ou TENANT_APPS ?~~

**DECIDE : SHARED_APPS** avec champ `tenant` pour filtrage. Cf. section 7.

### ~~16.2 Hash chain : garder, simplifier ou supprimer ?~~

**DECIDE : Simplifier.** Hash individuel par transaction (pas de chaine), plus `sequence_number` auto-incremente.
Migration en 3 phases : import sans hash → production sans hash → recalcul des hash. Cf. section 5.

### ~~16.3 Prix en centimes ou DecimalField ?~~

**DECIDE : Centimes (int) partout.** Tous les nouveaux champs monetaires sont en `IntegerField` (centimes).
ArticlePOS.prix, Token.value, LigneArticle.amount, ClotureCaisse.total_*, ArticleCommandeSauvegarde.reste_a_payer — tout en centimes.

**⚠️ Seule exception :** `BaseBillet.Price.prix` reste un `DecimalField` (euros) — c'est un champ existant
en production, on ne le change pas. Quand on lit un `Price` pour creer un `ArticlePOS` lie,
il faut convertir : `int(price.prix * 100)`. Ne jamais mixer les unites sans conversion explicite.

### ~~16.4 GroupementBouton : modele separe ou champs sur ArticlePOS ?~~

**DECIDE : Champs directs** sur ArticlePOS (champ `groupe`). Pas de modele separe. KISS.

### ~~16.5 Lien ArticlePOS → Product~~

**DECIDE : FK nullable.** Un ArticlePOS peut exister sans Product (article POS-only).

### ~~16.6 Wallet : ou vit-il ?~~

**DECIDE : Option A — Enrichir `AuthBillet.Wallet`.**
Ajouter `public_pem` (TextField, nullable) et `name` (CharField, nullable).
Wallet est deja SHARED_APPS, deja OneToOne avec TibilletUser, deja FK sur LigneArticle.
Zéro migration de FK. FALC : `user.wallet` = un seul endroit.

### ~~16.7 CarteCashless : ou enrichir ?~~

**DECIDE : Enrichir `QrcodeCashless.CarteCashless` avec `wallet_ephemere` seulement.**
CarteCashless est deja en SHARED_APPS (schema public). Une carte = un enregistrement global.
Pas besoin de `primary_places` (le lieu d'origine est deja dans `detail.origine`).
Ajouter uniquement `wallet_ephemere` (OneToOne → Wallet, nullable) pour les cartes anonymes.
Quand le user s'identifie : Transaction FUSION (wallet_ephemere → user.wallet), puis wallet_ephemere = null.

### ~~16.8 Stripe Fedow : fusionner avec PaiementStripe ?~~

**DECIDE : Option A — Tout dans `Paiement_stripe` (BaseBillet).**
Le M2M `fedow_transactions` existe deja sur `Paiement_stripe`. Ajouter un `source` choice
(`CASHLESS_REFILL`). Flux : Stripe webhook → creer Transaction(REFILL) dans fedow_core → lier
via le M2M existant. Pas de nouveau modele, pas de nouveau endpoint webhook.

## 17. Passages dangereux

### 17.1 Atomicite des paiements cashless

Quand on paye en NFC, il faut dans la MEME transaction DB :
1. Debiter le Token du sender
2. Crediter le Token du receiver
3. Creer la Transaction Fedow
4. Creer la/les LigneArticle

Si une etape echoue, TOUT doit rollback. C'est l'avantage du mono-repo : `transaction.atomic()` couvre tout.

**⚠️ Note technique cross-schema :** `Transaction` + `Token` sont en SHARED_APPS (schema `public`).
`LigneArticle` est en TENANT_APPS (schema du tenant). `transaction.atomic()` couvre les deux
car c'est la meme connexion PostgreSQL, meme base, meme transaction DB. Django-tenants change
le `search_path` mais ne cree pas de connexion separee. L'atomicite cross-schema est garantie.

**⚠️ Dans l'ancien systeme, un crash entre l'appel HTTP a Fedow et la creation de LigneArticle = desynchronisation.** C'est un vrai probleme en prod. Le mono-repo le resout.

### 17.2 Migration des Transaction (strategie 3 phases)

**Phase 1 — Import :** Les anciennes transactions sont importees avec leur UUID original et leur hash original tel quel.
Le champ `migrated=True` les identifie. Le `sequence_number` est auto-attribue dans l'ordre chronologique.
Les nouvelles transactions creees apres l'import ont `hash=null` et `migrated=False`.

**Phase 2 — Production :** Le systeme tourne sans calcul de hash. Le `sequence_number` garantit l'ordonnancement.
Aucune verification de hash n'est effectuee. C'est la phase de stabilisation.

**Phase 3 — Consolidation :** Management command `recalculate_hashes` qui :
1. Parcourt toutes les transactions par `sequence_number`
2. Calcule le hash SHA256 individuel (pas de chaine) pour chacune
3. Met a jour le champ `hash`
4. Migration Django : rendre `hash` NOT NULL + UNIQUE

**⚠️ Point d'attention :** L'ancien hash (chaine) et le nouveau hash (individuel) ne seront pas identiques.
C'est normal et attendu. L'ancien hash est ecrase. L'integrite des donnees importees repose sur les UUID
(qui sont conserves) et le `sequence_number` (attribue a l'import).

### 17.3 Federation cross-tenant

Si `fedow_core` est dans SHARED_APPS : attention aux queries non filtrees. Un `Asset.objects.all()` dans une vue retournerait les assets de TOUS les tenants.

**Solution :** Toujours passer par les services qui filtrent par tenant :
```python
# MAL / BAD
assets = Asset.objects.all()

# BIEN / GOOD
assets = AssetService.obtenir_assets_du_tenant(tenant=connection.tenant)
```

### 17.4 Double-ecriture pendant la transition

Pendant la migration progressive, `fedow_connect` (HTTP) et `fedow_core` (DB) coexistent.
Il ne faut PAS ecrire dans les deux en meme temps.

**Deux populations, deux chemins (cf. section 3.2) :**

- **Nouveaux tenants** (`server_cashless` vide, `module_caisse=True`) :
  → utilisent TOUJOURS `fedow_core/services.py`. Pas de `fedow_connect`.
  → les vues `laboutik` appellent fedow_core directement. Pas de flag.

- **Anciens tenants** (`server_cashless` renseigne) :
  → continuent d'utiliser `fedow_connect/fedow_api.py` (HTTP vers ancien Fedow).
  → la carte "Caisse V2" est grisee dans leur dashboard.
  → migration optionnelle en Phase 6-7.

**Les vues existantes de BaseBillet** (page "Mon compte", soldes, etc.) qui appellent
`fedow_connect` doivent a terme etre adaptees. Pour les anciens tenants, elles continuent
d'appeler `fedow_connect`. Pour les nouveaux, elles appellent `fedow_core/services.py`.
La detection se fait par `Configuration.server_cashless` :

```python
# Dans une vue BaseBillet qui affiche les soldes / In a BaseBillet view showing balances
config = Configuration.get_solo()
if config.server_cashless:
    # V1 — ancien Fedow via HTTP
    solde = WalletFedow.get_total_fiducial_and_all_federated_token(user)
else:
    # V2 — fedow_core direct
    solde = WalletService.obtenir_solde_total(user)
```

Ce double-chemin n'existe que dans les vues BaseBillet existantes, pas dans laboutik (qui est 100% V2).

### 17.5 Webhooks Stripe

Les webhooks Stripe actuels pointent vers Fedow ET Lespass. Apres la fusion, il faut :
- Mettre a jour l'endpoint Stripe pour pointer vers Lespass uniquement
- Gerer les deux formats de webhook (ancien Fedow + nouveau Lespass) pendant la transition
- Tester le checkout cashless (recharge) de bout en bout

### 17.6 RSA keys des utilisateurs

L'ancien Fedow utilise les RSA keys pour signer les requetes user. En mono-repo, on n'en a plus besoin pour l'auth inter-service. Mais elles pourraient servir pour :
- Signature des transactions (audit trail)
- Auth des terminaux de caisse

**Decision :** Garder les RSA keys dans Wallet.public_pem pour l'audit, mais ne plus les utiliser pour l'auth.

### 17.7 Compatibilite production — les anciens serveurs restent allumes

**⚠️ REGLE NON NEGOCIABLE :**

Les 3 serveurs actuels (Lespass, Fedow, LaBoutik) continuent de tourner en production
pendant TOUTE la duree de l'integration. On ne touche a rien en prod tant que la migration
n'est pas terminee et validee pour chaque ancien tenant.

**Deux populations, deux vies (cf. section 3.2) :**

```
NOUVEAUX TENANTS (pas de server_cashless)
│  Activent les modules depuis le dashboard (Phase -1)
│  Phases 0-5 : chaque phase est immediatement utilisable en prod
│  Pas de migration, pas de feature flag — ils debutent sur V2

ANCIENS TENANTS (server_cashless configure)
│  V1 tourne normalement (ancien Fedow + ancien LaBoutik)
│  Carte "Caisse V2" grisee dans leur dashboard
│  Phase 6 (migration) quand on est prets — pas d'urgence
│  Phase 7 (nettoyage) quand TOUS les anciens sont migres

EXTINCTION DES ANCIENS SERVEURS
│  SEULEMENT quand plus aucun tenant n'a server_cashless renseigne
│  Ancien Fedow   : ETEINT
│  Ancien LaBoutik : ETEINT
│  Lespass         : Mono-repo v2 complet
```

**3 gardes-fous avant Phase 7 (checklist mainteneur) :**

1. ☐ **Plus aucun tenant avec `server_cashless` renseigne** — verifier :
   ```python
   from BaseBillet.models import Configuration
   from Customers.models import Client
   for client in Client.objects.exclude(schema_name='public'):
       with tenant_context(client):
           config = Configuration.get_solo()
           assert not config.server_cashless, f"Tenant {client.name} encore sur V1 !"
   ```

2. ☐ **Aucune transaction recente sur l'ancien Fedow** — verifier dans les logs
   de l'ancien serveur que plus aucune requete ne lui parvient depuis au moins 7 jours.

3. ☐ **Script de verification post-migration OK pour chaque ancien tenant** (cf. section 14.3) :
   sommes des Token, nombre de Transaction, CarteCashless liees, sequences continues.

**Rollback pour les anciens tenants (Phase 6) :**

Le rollback est possible UNIQUEMENT si aucune nouvelle transaction n'a ete
creee en mode `fedow_core` pour ce tenant.

**Procedure de rollback safe (par ancien tenant) :**
1. Verifier : `Transaction.objects.filter(migrated=False, tenant=client).count()` — si > 0, rollback IMPOSSIBLE
2. Si == 0 : remettre `server_cashless` dans Configuration, desactiver `module_caisse`
3. L'ancien Fedow reprend le relais pour ce tenant

**⚠️ Point de non-retour :**
Des qu'une transaction est creee en mode `fedow_core` (migrated=False), le tenant est
definitivement sur le nouveau systeme. C'est pourquoi la bascule doit etre precedee
d'une validation complete des donnees migrees (Phase 6, section 14.3).

**Pour les nouveaux tenants :** pas de rollback a prevoir. Ils n'ont jamais eu de V1.
S'ils desactivent le module caisse, les donnees restent en DB, le module est juste masque.

**Rappel pour les sessions Claude Code :**
Avant de travailler sur une Phase qui touche des vues ou des services, toujours verifier :
- "Est-ce que ce changement casse les vues BaseBillet qui utilisent `fedow_connect` ?"
- "Est-ce que l'ancien `fedow_connect/fedow_api.py` continue de fonctionner pour les anciens tenants ?"
- Si la reponse est non → s'arreter et en parler au mainteneur.

### 17.8 Stress test — 4 festivals de 25 000 personnes en simultane

**Scenario cible :** 4 lieux federes, 25 000 personnes chacun, ~100 000 utilisateurs actifs.
Chaque lieu a 20-30 terminaux POS. Pic : 2000 transactions/minute cross-tenant sur le meme asset federe.

**Pourquoi c'est critique :** `fedow_core` est en SHARED_APPS. La table `Transaction` est unique
(schema `public`). Tous les lieux ecrivent dans la meme table. La sequence PostgreSQL `sequence_number`
est globale. Si ca ne tient pas la charge, tout s'ecroule.

**Ce qu'on doit verifier :**

1. **Sequence PostgreSQL sous contention** — `nextval()` est-il un goulot ?
   PostgreSQL garantit que `nextval()` ne bloque pas (pas de verrou sur la sequence).
   Mais avec 2000 ecritures/minute, la sequence doit tenir.

2. **INSERT dans Transaction (SHARED_APPS)** — pas de verrou applicatif
   On a supprime `select_for_update`. Chaque INSERT est independant.
   Le seul point de serialisation est la contrainte UNIQUE sur `sequence_number`
   (geree par la sequence, pas de conflit possible).

3. **UPDATE sur Token (debit/credit)** — verrou par ligne
   Le `transaction.atomic()` verrouille les lignes Token du sender et du receiver.
   Si 2 terminaux debitent le meme wallet au meme moment → le 2e attend.
   C'est correct et voulu (on ne peut pas debiter deux fois le meme solde).
   Le verrou dure quelques millisecondes (pas de query lente dans le bloc).

4. **Leak cross-tenant** — le risque numero 1
   Sous charge, un dev pourrait etre tente de contourner les services pour "aller plus vite".
   Le stress test doit aussi verifier qu'aucune donnee ne fuit entre tenants.

**Protocole de stress test (Phase 3, apres les tests unitaires) :**

Fichier : `tests/stress/test_charge_festival.py`
- Prerequis : 4 tenants, 1 asset TLF federe, 500 wallets chacun, 1 PV avec 10 articles
- Outil : `concurrent.futures.ThreadPoolExecutor(max_workers=80)`
- Charge : 4 × 500 = 2000 transactions concurrentes
- Metriques : temps moyen < 50ms, P95 < 200ms, 0 deadlock, 0 erreur (hors solde insuffisant)
- Verifications : sum(Token.value) inchangee, `verify_transactions` OK, 0 leak cross-tenant

**Quand lancer ce test :**
- Apres Phase 3 (paiement cashless OK) — avant de deployer en prod
- En environnement de staging avec PostgreSQL 13+ (meme version que prod)
- Pas en CI (trop lent) — a lancer manuellement par le mainteneur

**Si le test echoue :**
- Temps moyen > 50ms → verifier les index, EXPLAIN ANALYZE sur les queries Transaction + Token
- Deadlocks → revoir l'ordre de verrouillage (toujours sender avant receiver, par UUID croissant)
- Leak cross-tenant → bug critique, arreter tout, corriger le service avant de continuer

---

# PARTIE E — METHODE DE TRAVAIL AVEC CLAUDE CODE

## 18. Regles d'execution — gardes-fous LLM

### Principe : une phase, une session, un modele

Chaque phase du plan (-1 a 7) = 1 a 2 sessions Claude Code max.
Ne JAMAIS enchainer deux phases dans la meme session.
A la fin de chaque phase : le mainteneur valide, puis on passe a la suivante.

### Quel modele pour quoi

| Tache | Modele | Raison |
|---|---|---|
| Design modeles, service layer atomique, migration commands | **Opus** | Raisonnement complexe, atomicite, pas le droit a l'erreur |
| Revue de securite (tenant isolation, permissions, failles) | **Opus** | Doit penser aux cas limites, attaques, oublis |
| Implementation vues/templates quand le plan est clair | **Sonnet** | Rapide, suffisant pour du code FALC bien cadre |
| Ecriture de tests a partir des specs | **Sonnet** | Pattern repetitif, bien defini |
| Creation fichiers simples, migrations, collectstatic | **Haiku** | Taches mecaniques, pas besoin de raisonnement profond |
| Debug d'un traceback precis | **Sonnet** | Lecture ciblee, reponse rapide |

### Regle des 3 fichiers

Ne JAMAIS modifier plus de 3 fichiers sans lancer la boucle de verification :
```bash
docker exec lespass_django poetry run python manage.py check
docker exec lespass_django poetry run python manage.py makemigrations --check --dry-run
# + lancer le test de la phase en cours
```

Si un des 3 echoue → corriger AVANT de toucher un autre fichier.

### Boucle de verification apres chaque changement

```
1. Modifier le code (max 3 fichiers)
2. manage.py check → erreur ? corriger
3. manage.py makemigrations --check → migration inattendue ? comprendre pourquoi
4. Lancer le test de la phase → rouge ? corriger
5. Verifier les logs du serveur (pas de traceback)
6. Seulement alors : passer au changement suivant
```

### Anti-hallucination

Les LLM inventent des API qui n'existent pas. Ca arrive surtout quand on code vite.

**Regles concretes :**
- Toujours lire le fichier existant AVANT de le modifier (Read tool)
- Ne jamais utiliser une methode Django/DRF sans l'avoir vue dans le codebase existant OU verifiee dans la doc officielle (WebSearch)
- En cas de doute sur un import ou une methode : ecrire un test minimal AVANT le code de prod
- Si le test echoue avec `AttributeError` ou `ImportError` → c'est une hallucination, chercher la vraie API

**Signaux d'alerte (le mainteneur doit recadrer si) :**
- Claude propose d'ajouter un fichier/classe/module qui n'est pas dans le plan
- Claude commence a "nettoyer" ou "ameliorer" du code adjacent
- Claude utilise un pattern jamais vu dans le codebase (metaclasse, signal, middleware custom)
- Claude enchaine plus de 5 fichiers sans lancer les tests

### Anti-sur-ingenierie

Le CLAUDE.md dit deja "zero sur-ingenierie". Concretement :

- **Si le plan ne le mentionne pas, ne pas le faire.** Pas de "tant qu'on y est".
- **Pas de docstring** sur du code qu'on n'a pas ecrit.
- **Pas de helper/utility** pour une operation utilisee une seule fois.
- **3 lignes similaires > 1 abstraction prematuree.**
- **Pas de gestion d'erreur speculative.** Si ca peut pas arriver, pas de try/except.

### Securite : checkpoints obligatoires

Tests detailles dans `memory/tests_validation.md`. Resume :

- **Phase 0** : test isolation cross-tenant (AssetService filtre bien, `.objects.all()` retourne tout)
- **Phase 2** : test permissions (sans API key → 403, mauvais tenant → 403, bonne cle → 200)
- **Phase 3** : test atomicite (echec paiement → solde/Transaction/LigneArticle inchanges) + stress test (section 17.8)
- **Phase 6** : test import (UUID importes ne collisionnent pas, migrated=True, tx locales intactes)

### Checklist securite Django (a lancer en fin de phase)

`manage.py check --deploy` + verif manuelle : permission_classes sur chaque ViewSet,
filtre tenant dans chaque service, pas de `.objects.all()` hors service, CSRF sur POST HTMX.

### Quand s'arreter et demander au mainteneur

Claude Code doit s'arreter et demander AVANT de :
- Modifier un fichier qui n'est pas dans le scope de la phase en cours
- Ajouter une dependance Python (pyproject.toml)
- Modifier settings.py, urls_tenants.py, ou urls_public.py
- Toucher a PaiementStripe, AuthBillet, ou Administration
- Ecrire du JS (laisser le mainteneur valider l'approche d'abord)
- Creer un nouveau module/app Django

### Guide pour le mainteneur — piloter Claude Code

**En debut de chaque session :**
```
On travaille sur la Phase X du plan laboutik/doc/PLAN_INTEGRATION.md
Lis le plan, lis le MEMORY.md, et dis-moi ce que tu comprends avant de coder.
```
Ca force Claude a relire le contexte et verifier l'alignement avant de produire du code.

**Commandes courtes pour recadrer :**
- **"Stop"** → arrete immediatement ce qu'il fait
- **"Plan"** → relit le plan et se recadre sur la tache en cours
- **"Trop"** → simplifie, en fait trop
- **"Test d'abord"** → ecrit le test avant le code de prod
- **"Pas dans le scope"** → revient sur la tache demandee

**Si Claude hallucine une API :**
```
Cette methode n'existe pas. Verifie dans la doc.
```

**Quand faire `/compact` (compression du contexte) :**
- En milieu de phase, apres beaucoup de lectures de fichiers (Read/Grep)
- Pour "nettoyer" le contexte sans perdre le fil de la session
- Claude Code le fait automatiquement a la limite, mais on peut forcer pour garder de la marge

**Quand faire `/clear` (reset complet) :**
- Quand on change de sujet completement
- Quand Claude boucle (meme erreur 3 fois)
- ⚠️ Perd tout le contexte de session. Le MEMORY.md est recharge mais pas le plan → repreciser la phase au redemarrage

**Quand changer de session (nouvelle conversation) :**
- Apres chaque phase validee — moment naturel de coupure
- Quand Claude propose des choses hors plan → signe de derive contextuelle
- Apres ~30 echanges substantiels (pas des oui/non)
- Quand Claude repete des erreurs deja corrigees

**Contexte etendu (1M tokens) :**
- Activation au lancement : `claude --model opus[1m]` (ou `sonnet[1m]` selon la phase)
- Activation en cours de session : `/model opus[1m]`
- Utile pour : Phase 0 (beaucoup de modeles), Phase 6 (migration, lire ancien + ecrire nouveau), revue de securite transverse
- Par defaut (200k) : suffisant pour les phases 1-5 et 7
- ⚠️ Plus de contexte = plus lent + plus cher (2x input, 1.5x output au-dela de 200k). Ne pas laisser active en permanence.

**Signaux d'alerte — le mainteneur doit intervenir si :**
- Claude modifie plus de 3 fichiers sans lancer de test
- Claude ajoute un fichier/classe/module pas dans le plan
- Claude "nettoie" ou "ameliore" du code adjacent
- Claude utilise un pattern jamais vu dans le codebase
- Claude est optimiste sur la complexite ("c'est simple, je fais tout d'un coup")

---

## 19. Fichiers de reference

### Ancien Fedow (OLD_REPOS/Fedow)

| Fichier | Contenu | Lignes |
|---|---|---|
| `fedow_core/models.py` | Tous les modeles (Asset, Token, Transaction, Wallet, Card, Federation, etc.) | ~1000 |
| `fedow_core/views.py` | Tous les ViewSets API (Transaction, Wallet, Card, Asset, Federation, Place, Stripe) | ~800 |
| `fedow_core/serializers.py` | Validateurs (TransactionW2W, CardCreate, HandshakeValidator, etc.) | ~500 |
| `fedow_core/utils.py` | RSA crypto, Fernet encryption, hashing | ~150 |
| `fedow_core/permissions.py` | HasAPIKey, HasKeyAndPlaceSignature, HasWalletSignature, etc. | ~200 |
| `fedow_core/management/commands/` | install, places, assets, federations, import_cards, demo_data | ~300 |
| `fedow_core/admin.py` | Admin pour tous les modeles | ~100 |

### Lespass actuel (fedow_connect + fedow_public)

| Fichier | Contenu | A faire |
|---|---|---|
| `fedow_connect/fedow_api.py` | Client HTTP Fedow (700 lignes) | Remplacer par fedow_core/services.py |
| `fedow_connect/models.py` | Asset miroir + FedowConfig singleton | Supprimer (remplace par fedow_core.Asset) |
| `fedow_connect/validators.py` | Validateurs de reponse Fedow | Garder/adapter pour services.py |
| `fedow_connect/utils.py` | RSA + Fernet crypto | Garder Fernet, RSA optionnel |
| `fedow_connect/views.py` | Webhook membership from Fedow | Adapter |
| `fedow_public/models.py` | AssetFedowPublic (doublon d'Asset) | Supprimer |
| `fedow_public/views.py` | Admin views bank deposits + transactions | Adapter vers fedow_core.Asset |

### Ancien LaBoutik (OLD_REPOS/LaBoutik)

| Fichier | Contenu |
|---|---|
| `APIcashless/models.py` | 28 modeles (2000+ lignes) |
| `webview/views.py` | Classe Commande — moteur de paiement (1500+ lignes) |
| `fedow_connect/fedow_api.py` | Client HTTP Fedow depuis LaBoutik |
| `administration/adminroot.py` | Admin root (13 modeles enregistres) |
| `APIcashless/tasks.py` | Taches Celery |

---

## Annexe A : Codes de transaction (methode article, v2 — 13 types)

BG (badgeuse) retire — experimentation non aboutie.

| Code | Nom | Description | NFC | PV |
|---|---|---|---|---|
| VT | Vente | Article standard | Non obligatoire | Tout |
| RE | Recharge euros | Crediter wallet fiat | Oui | Cashless |
| RC | Recharge cadeau | Crediter wallet cadeau | Oui | Cashless |
| TM | Recharge temps | Crediter wallet temps | Oui | Cashless |
| AD | Adhesion | Creer/renouveler Membership | Oui | Tout |
| CR | Retour consigne | Rembourser ecocup | Non | Tout |
| VC | Vider carte | Retirer tout le solde | Oui | Admin |
| VV | Void carte | Desactiver carte | Oui | Admin |
| FR | Fractionne | Paiement partiel | Dependra | Systeme |
| BI | Billet | Billet evenement | Optionnel | Billetterie |
| FD | Fidelite | Points fidelite | Non (auto) | Systeme |
| HB | Cashback | Retour cashback | Non (auto) | Systeme |
| TR | Transfert | Virement bancaire | Non | Admin |

## Annexe B : Actions de Transaction Fedow (v2 — 10 types)

BADGE et SUBSCRIBE retires. Les adhesions passent par `BaseBillet.Membership`.

| Code | Nom | sender | receiver | Description |
|---|---|---|---|---|
| FIRST | Genesis | — | — | Premier bloc par asset |
| CREATION | Creation | place | place | Creer des tokens |
| REFILL | Recharge | primary | user | Recharger wallet (Stripe) |
| SALE | Vente | user | place | Paiement cashless |
| QRCODE_SALE | Vente QR | user | place | Paiement QR code |
| FUSION | Fusion | ephemere | user | Fusionner wallet anonyme |
| REFUND | Remboursement | user | place | Annulation |
| VOID | Annulation | user | — | Vider carte |
| DEPOSIT | Depot | place | primary | Retrait circulation |
| TRANSFER | Virement | wallet | wallet | Transfert direct |
