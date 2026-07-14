# PLAN_LABOUTIK.md — Référence unifiée

> **Ce fichier est la source unique.** Les prompts et comptes-rendus de sessions sont archivés dans `PHASES/`.
>
> Dernière mise à jour : 2026-03-30 (conformité LNE : HMAC chain, clôtures J/M/A, total perpétuel, archivage fiscal, mode école — sessions 12-19 redécoupées)

---

## Sommaire

1. [Vision et statut actuel](#1-vision-et-statut-actuel)
2. [Architecture](#2-architecture)
3. [Modèles](#3-modèles)
4. [ViewSets et logique métier](#4-viewsets-et-logique-métier)
5. [Composants Cotton et JavaScript](#5-composants-cotton-et-javascript)
6. [Flux de paiement détaillés](#6-flux-de-paiement-détaillés)
7. [Mode restaurant (tables + commandes)](#7-mode-restaurant-tables--commandes)
8. [Clôture caisse](#8-clôture-caisse)
9. [UX — Interface POS](#9-ux--interface-pos)
10. [Admin Unfold](#10-admin-unfold)
11. [Tests](#11-tests)
12. [Décisions architecturales (toutes prises)](#12-décisions-architecturales-toutes-prises)
13. [Passages dangereux](#13-passages-dangereux)
14. [Règles de travail avec Claude Code](#14-règles-de-travail-avec-claude-code)
15. [Ce qui reste à faire](#15-ce-qui-reste-à-faire)

---

## 1. Vision et statut actuel

### Vision

Fusionner les 3 moteurs Django (Lespass + LaBoutik + Fedow) en **1 mono-repo**.

- **Avant** : 3 serveurs séparés, communication HTTP+RSA, 3 bases PostgreSQL, pas d'atomicité cross-service
- **Après** : 1 seul Django, accès DB direct, `transaction.atomic()` couvre tout, 1 déploiement

TiBillet devient un **Groupware coopératif** : chaque tenant active les modules dont il a besoin
(billetterie, adhésion, crowdfunding, caisse, monnaie locale).

### Statut par phase (branche `integration_laboutik`)

| Phase | Description | Statut |
|-------|-------------|--------|
| **-1** | Dashboard Groupware, `module_*`, sidebar conditionnelle, proxy models Product | ✅ TERMINÉE |
| **0** | `fedow_core` : Asset, Token, Transaction, Federation, services, admin, tests | ✅ TERMINÉE |
| **1** | Product unifié (8 champs POS, CategorieProduct, POSProduct proxy, Price.asset), 4 modèles laboutik, admin, données test | ✅ TERMINÉE |
| **2** | Remplacement des mocks : caisse depuis DB, paiement espèces/CB | ✅ TERMINÉE |
| **2.5** | POS Adhésion : wizard identification 6 chemins (NFC user/anonyme, email), fusion wallet, création/renouvellement Membership, multi-tarif, prix libre | ✅ TERMINÉE |
| **3 étape 1** | Paiement NFC cashless (`_payer_par_nfc` atomique) | ✅ TERMINÉE |
| **3 étape 2** | Recharges espèces/CB + sécurité (wallet éphémère, validation PV, garde NFC recharges) | ✅ TERMINÉE |
| **4** | Commandes restaurant (CommandeSauvegarde, tables) | ✅ TERMINÉE |
| **5** | Clôture caisse (ClotureCaisse, rapport JSON, email/PDF) | ✅ TERMINÉE |
| **UX** | 5 sessions de polish interface caisse (Sessions 1-5) | ✅ TERMINÉE |
| **① Refactoring Frontend** | Extraction CSS, footer Cotton `<c-footer>`, fix sécurité (XSS + prix libre), a11y | ⏳ **PROCHAIN** |
| **② Billetterie + Refonte typage** | Typage par article (pas PV), flow identification unifié, tuiles BI dans la grille, jauge, panier mixte | ✅ FAIT |
| **③ WebSocket** | Push serveur HTMX 2 ws, Daphne, badge test, broadcast jauge | ✅ FAIT |
| **④ Impression** | 4 backends (Cloud/LAN/Inner/Mock), ESC/POS builder, formatters, Celery async, bouton Imprimer, auto-print billets, MockBackend decode ESC/POS | ✅ FAIT |
| **⑤ Conformité LNE + Rapports** | Chaînage HMAC-SHA256, service de calcul, clôtures J/M/A, total perpétuel, mentions légales tickets, mode école, archivage fiscal, accès admin fiscale | ✅ FAIT (sessions 12-21) |
| **⑥ Menu Ventes** | Ticket X, liste ventes, corrections, fond de caisse, sortie espèces, ré-impression | ✅ FAIT (sessions 16-17) |
| **Inventaire** | Stock POS optionnel, décrémentation atomique, admin Unfold, MouvementStock, contenance, affichage visuel tuiles (3 états), OOB WebSocket | ✅ FAIT (sessions 23-25) |
| **Admin PriceInline** | 4 StackedInline par proxy (Ticket/Membership/POS/Base), champs conditionnels JS, labels contextuels | ✅ FAIT (session 26) |
| **⑦ Multi-Tarif + Poids/Mesure** | Overlay multi-clic dans `#products`, pavé numérique poids/mesure (GR/CL), `Price.poids_mesure`, `LigneArticle.weight_quantity`, HMAC LNE, suffixe `--N` montants variables, 9 E2E | ✅ FAIT (session 28) |
| **⑧ Multi-Asset** | Paniers mixtes EUR + tokens (à détailler avec le mainteneur) | ⏳ À DÉTAILLER |
| **⑨ Stress test (3.3)** | `verify_transactions` + `verify_integrity` (HMAC chain) + 2000 tx concurrentes | ⏳ À FAIRE |
| **⑩ Migration (6)** | Import données anciens tenants Fedow + LaBoutik | ⏳ À FAIRE |
| **⑪ Consolidation (7)** | Hashes, suppression fedow_connect | ⏳ À FAIRE |

### Conformité LNE — référentiel v1.7 (détail sessions 12-19)

> **Design spec** : `docs/superpowers/specs/2026-03-30-conformite-lne-caisse-design.md`
> **Référentiel LNE** : `~/Nextcloud/TiBillet/10.Certification LNE/referentiel-certification-systemes-caisse.pdf`
> **Objectif** : moyen terme (préparer le terrain technique, certification ultérieure)

| Session | Titre | Exigences LNE | Dépend de |
|---------|-------|---------------|-----------|
| **12** | Fondation HMAC + service de calcul | Ex.3, Ex.8 | — |
| **13** | Clôtures J/M/A + total perpétuel | Ex.6, Ex.7 | 12 |
| **14** | Mentions légales tickets + traçabilité impressions | Ex.3, Ex.9 | 12 |
| **15** | Mode école + exports admin | Ex.5 | 13, 14 |
| **16** | Menu Ventes : Ticket X + liste | — | 12 | ✅ FAIT |
| **17** | Corrections + fond/sortie de caisse | Ex.4 | 13, 16 | ✅ FAIT |
| **18** | Archivage fiscal + accès administration | Ex.10-12, Ex.15, Ex.19 | 13 |
| **19** | Envoi auto rapports + version | Ex.21 | 15, 18 |

**Décisions architecturales clés :**
- **Inaltérabilité** : chaînage HMAC-SHA256 sur chaque `LigneArticle` (clé Fernet par tenant)
- **Clôtures** : 3 niveaux (J/M/A) dans `ClotureCaisse`, M/A auto via Celery Beat
- **Total perpétuel** : dans `LaboutikConfiguration`, snapshot sur chaque clôture, jamais remis à 0
- **`datetime_ouverture`** : calculé auto = datetime 1ère vente après dernière clôture (pas de saisie)
- **Corrections** : opérations de +/- uniquement (CREDIT_NOTE). Post-clôture interdit
- **Mode école** : `sale_origin=LABOUTIK_TEST` + bandeau UI visible + tickets "SIMULATION"
- **Archivage** : CSV/JSON dans ZIP avec hash HMAC, max 1 an par archive

### Les 3 règles à ne jamais oublier

1. **Ne jamais casser** les vues BaseBillet qui utilisent `fedow_connect`
2. **Toujours filtrer par tenant** dans les queries fedow_core (`SHARED_APPS` = pas d'isolation auto)
3. **Tout en centimes (int)**, sauf `BaseBillet.Price.prix` qui reste DecimalField (euros)

---

## 2. Architecture

### Architecture actuelle (3 serveurs)

```
┌─────────────┐     HTTP/RSA      ┌─────────────┐
│   Lespass    │ ←───────────────→ │    Fedow     │
│ (billetterie │   fedow_connect   │ (portefeuille│
│  adhésions)  │                   │  fédéré)     │
└──────┬───────┘                   └──────────────┘
       │ Configuration.server_cashless      ↑ HTTP/RSA
       ▼                                    │
┌─────────────┐                             │
│  LaBoutik   │ ────────────────────────────┘
│  (caisse)   │
└─────────────┘
```

**Problèmes** : pas d'atomicité cross-service, RSA overhead, modèles dupliqués,
crash Fedow = tout le cashless tombe, 3 déploiements.

### Architecture cible (mono-repo)

```
┌──────────────────────────────────────────────────────┐
│                    Lespass v2                          │
│                                                        │
│  ┌────────────┐  ┌────────────┐  ┌──────────────┐     │
│  │ BaseBillet  │  │  laboutik  │  │  fedow_core  │     │
│  │(billetterie │  │  (caisse   │  │ (portefeuille│     │
│  │  adhésions) │  │    POS)    │  │  tokens)     │     │
│  └──────┬──────┘  └─────┬──────┘  └──────┬───────┘     │
│         └───────────────┼────────────────┘             │
│                    PostgreSQL (django-tenants)           │
│                                                        │
│  Apps shared : Customers, AuthBillet, fedow_core       │
│  Apps tenant : BaseBillet, laboutik, crowds, api_v2... │
└──────────────────────────────────────────────────────┘
```

**Avantage clé** : `transaction.atomic()` couvre Token (public) + LigneArticle (tenant)
car c'est la même connexion PostgreSQL. L'atomicité cross-schema est garantie.

### Coexistence V1 / V2

**Anciens tenants** (`server_cashless` renseigné) :
- V1 reste actif, rien ne change, rien ne casse
- Carte "Caisse V2" grisée dans le dashboard avec badge "V1 active"
- Migration optionnelle plus tard (Phase 6-7)

**Nouveaux tenants** (`server_cashless` vide) :
- V2 directe : `fedow_core` + `laboutik`, tout en DB direct
- Activent "Caisse & Restauration" depuis le dashboard Groupware
- `module_caisse=True` force `module_monnaie_locale=True`

**Règle de détection** :
```python
# V2 si :
module_monnaie_locale=True AND server_cashless IS NULL

# V1 si :
server_cashless IS NOT NULL
```

Les vues `laboutik` utilisent **toujours** `fedow_core` — elles sont nouvelles, pas de double-chemin `if use_fedow_core`.

### Multi-tenancy

`fedow_core` est dans `SHARED_APPS` (schema public). Les tables vivent dans le schema public.
Chaque modèle `fedow_core` a un champ `tenant` (FK → Customers.Client) pour le filtrage.

```python
# MAL — retourne les assets de TOUS les tenants
assets = Asset.objects.all()

# BIEN — filtre par tenant courant
assets = Asset.objects.filter(tenant_origin=connection.tenant)

# BIEN — via service (recommandé)
assets = AssetService.obtenir_assets_du_tenant(tenant=connection.tenant)
```

---

## 3. Modèles

### 3.1 `laboutik/models.py`

#### `LaboutikConfiguration` (SingletonModel)

Config globale de l'interface caisse. Une seule instance par tenant.

```
LaboutikConfiguration
└── taille_police_articles (SmallIntegerField, choices: 18/20/22/24/26/28, default=22)
    Injecté comme variable CSS --article-font-size dans articles.html
```

#### `PointDeVente`

```
PointDeVente
├── uuid (PK)
├── name (CharField unique)
├── icon (CharField, nullable)
├── comportement (CharField choices)
│   D = Direct (M2M products uniquement : bar, restaurant, etc.)
│   A = Adhésion (charge auto tous les produits adhésion + M2M)
│   C = Cashless (charge auto toutes les recharges + M2M)
│   T = Billetterie (construit les articles depuis les événements futurs + M2M)
│   V = Avancé / Advanced (mode commande restaurant — réservé, pas codé)
│   Le type du PV détermine le chargement automatique. Le M2M products est toujours chargé en plus.
├── service_direct (BooleanField, default=True)
├── afficher_les_prix (BooleanField, default=True)
├── accepte_especes (BooleanField, default=True)
├── accepte_carte_bancaire (BooleanField, default=True)
├── accepte_cheque (BooleanField, default=False)
├── accepte_commandes (BooleanField, default=False) — active le mode restaurant
├── poid_liste (SmallIntegerField, default=0)
├── hidden (BooleanField, default=False)
├── products (M2M → Product) — articles disponibles à ce PV
└── categories (M2M → CategorieProduct) — catégories disponibles
```

**Comportement ADHESION** : inclut dynamiquement tous les `Product(categorie_article=ADHESION, publish=True)` — pas de M2M, requête directe.

#### `CartePrimaire`

Carte NFC de l'opérateur de caisse. Son scan identifie le caissier et charge ses PV autorisés.

```
CartePrimaire
├── uuid (PK)
├── carte (OneToOne → QrcodeCashless.CarteCashless)
├── points_de_vente (M2M → PointDeVente)
├── edit_mode (BooleanField, default=False)
└── datetime (DateTimeField, auto_now_add)
```

#### `CategorieTable` + `Table`

```
CategorieTable
├── name (CharField unique)
└── icon (CharField, nullable)

Table
├── uuid (PK)
├── name (CharField unique)
├── categorie (FK → CategorieTable, SET_NULL)
├── poids (SmallIntegerField, default=0)
├── statut (CharField: L=Libre, O=Occupée, S=Servie)
├── ephemere (BooleanField, default=False)
├── archive (BooleanField, default=False)
├── position_top (IntegerField, nullable) — plan de salle
└── position_left (IntegerField, nullable) — plan de salle
```

#### `CommandeSauvegarde` + `ArticleCommandeSauvegarde`

```
CommandeSauvegarde
├── uuid (PK)
├── service (UUIDField, nullable) — identifiant du service en cours
├── responsable (FK → TibilletUser, SET_NULL)
├── table (FK → Table, SET_NULL, nullable)
├── datetime (DateTimeField, auto_now_add)
├── statut (OPEN/SERVED/PAID/CANCEL)
├── commentaire (TextField)
└── archive (BooleanField)

Cycle de vie : OPEN → SERVED → PAID (→ archive=True après clôture)
               OPEN → CANCEL

ArticleCommandeSauvegarde
├── commande (FK → CommandeSauvegarde)
├── product (FK → Product, PROTECT)
├── price (FK → Price, PROTECT)
├── qty (SmallIntegerField, default=1)
├── reste_a_payer (IntegerField, centimes) — 0 = pas encore facturé
├── reste_a_servir (SmallIntegerField)
└── statut (EN_ATTENTE/EN_COURS/PRET/SERVI/ANNULE)
```

#### `ClotureCaisse`

**GLOBALE au tenant** (pas par PV). Couvre tous les PV d'une soirée.
`point_de_vente` est informatif (d'où la clôture a été déclenchée). Nullable.
La ventilation par PV est dans `rapport_json['ventilation_par_pv']`.
Seul un gérant peut déclencher une clôture J.

```
ClotureCaisse
├── uuid (PK)
├── point_de_vente (FK → PointDeVente, SET_NULL, nullable) — informatif
├── responsable (FK → TibilletUser, SET_NULL)
├── datetime_ouverture (DateTimeField) — calculé auto (1ère vente après dernière clôture)
├── datetime_cloture (DateTimeField, default=timezone.now) — explicite
├── niveau (CharField J/M/A) — J=journalière, M=mensuelle, A=annuelle
├── numero_sequentiel (PositiveIntegerField) — par niveau, global au tenant
├── total_especes (IntegerField, centimes)
├── total_carte_bancaire (IntegerField, centimes)
├── total_cashless (IntegerField, centimes)
├── total_general (IntegerField, centimes)
├── total_perpetuel (IntegerField, centimes) — snapshot au moment de la clôture
├── nombre_transactions (IntegerField) — nb LigneArticle dans la période
├── hash_lignes (CharField 64) — SHA-256 des lignes couvertes
└── rapport_json (JSONField) — 13 clés dont ventilation_par_pv
```

### 3.2 `BaseBillet.Product` enrichi (Product unifié)

**Décision 16.9 : pas de modèle `ArticlePOS` séparé.** Le Product EST l'article de caisse.

```
Product (champs existants inchangés)
├── ...
├── methode_caisse (CharField choices, nullable) — NOUVEAU
│   VT = Vente       RE = Recharge euros     RC = Recharge cadeau
│   TM = Recharge temps   AD = Adhésion       CR = Retour consigne
│   VC = Vider carte  FR = Fractionné         BI = Billet
│   FD = Fidélité     null = pas un article de caisse
│
├── categorie_pos (FK → CategorieProduct, SET_NULL, nullable) — NOUVEAU
│   OBLIGATOIRE dans le formulaire admin (required=True)
├── couleur_texte_pos (CharField 7 hexa, nullable) — NOUVEAU
├── couleur_fond_pos (CharField 7 hexa, nullable) — NOUVEAU
├── fractionne (BooleanField, default=False) — NOUVEAU
├── besoin_tag_id (BooleanField, default=False) — NOUVEAU
└── icon_pos (CharField, nullable) — NOUVEAU
    Format : "fa-beer" (FontAwesome) ou "local_bar" (Material Symbols)
    Détection automatique : startswith("fa") → FA, sinon → MS
```

**Convention** : `methode_caisse IS NOT NULL` = produit disponible en caisse.

**Proxy `POSProduct(Product)`** : filtre sur `methode_caisse IS NOT NULL`. Zero migration (même table).

**Priorité couleurs dans `views.py`** :
```python
couleur_fond = product.couleur_fond_pos or categorie_pos.couleur_fond or fallback
couleur_texte = product.couleur_texte_pos or categorie_pos.couleur_texte or fallback
```

**Priorité icône** :
```python
icone = product.icon_pos or categorie_pos.icon or ''
icone_type = 'fa' if icone.startswith('fa') else 'ms'
```

### 3.3 `BaseBillet.CategorieProduct` (NOUVEAU)

Dans BaseBillet (pas laboutik) car réutilisable au-delà du POS.

```
CategorieProduct
├── uuid (PK)
├── name (CharField)
├── icon (CharField, nullable) — FA ou MS
├── couleur_texte (CharField, 7 hexa, nullable)
├── couleur_fond (CharField, 7 hexa, nullable)
├── poid_liste (SmallIntegerField, default=0)
├── tva (FK → BaseBillet.Tva, nullable)
└── cashless (BooleanField, default=False)
```

### 3.4 `BaseBillet.Price.asset` (NOUVEAU)

```
Price
├── ... (champs existants inchangés)
├── prix (DecimalField) — en euros SI asset=null, en unités de l'asset SI asset renseigné
└── asset (FK → fedow_core.Asset, nullable, blank=True) — NOUVEAU
    asset=null  → prix en EUR
    asset=TIM   → prix en tokens temps
```

**Conversion** (toujours) :
```python
montant_centimes = int(round(price.prix * 100))
# Ne JAMAIS faire : int(price.prix * 100) — tronque au lieu d'arrondir
# Ne JAMAIS passer par float intermédiaire
```

### 3.5 `fedow_core` (SHARED_APPS)

#### `Asset` — Monnaie/token

5 catégories : TLF (local fiduciaire), TNF (cadeau), FED (fédéré Stripe), TIM (temps), FID (fidélité).

```
Asset
├── uuid (PK)
├── name, currency_code (3 chars)
├── category (TLF/TNF/FED/TIM/FID)
├── wallet_origin (FK → Wallet)
├── tenant_origin (FK → Customers.Client)
├── pending_invitations (M2M → Customers.Client) — invités en attente
├── federated_with (M2M → Customers.Client) — membres actifs
├── active (BooleanField)
├── archive (BooleanField)
├── id_price_stripe (CharField, nullable) — pour FED (recharge Stripe)
└── created_at, last_update (DateTimeField)
```

#### `Token` — Solde d'un wallet pour un asset

```
Token
├── uuid (PK)
├── wallet (FK → Wallet)
├── asset (FK → Asset)
├── value (IntegerField, centimes)
└── UNIQUE_CONSTRAINT (wallet, asset)
```

#### `Transaction` — Historique immuable

```
Transaction
├── id (BigAutoField, PK) — auto-increment natif Django, référence humaine (#12345)
├── uuid (UUIDField, unique) — pour imports depuis l'ancien Fedow
├── hash (CharField 64, nullable, unique) — SHA256 individuel, calculé en Phase 3
├── migrated (BooleanField, default=False) — True pour les tx importées
├── sender (FK → Wallet)
├── receiver (FK → Wallet)
├── asset (FK → Asset)
├── amount (PositiveIntegerField, centimes)
├── action (choices: FIRST/CREATION/REFILL/SALE/QRCODE_SALE/FUSION/REFUND/VOID/DEPOSIT/TRANSFER)
├── card (FK → CarteCashless, nullable)
├── primary_card (FK → CarteCashless, nullable)
├── datetime (DateTimeField)
├── comment (TextField)
├── metadata (JSONField)
├── checkout_stripe (UUIDField, nullable) — UUID du Paiement_stripe (pas de FK cross-schema)
├── tenant (FK → Customers.Client) — filtrage cross-tenant
└── ip (GenericIPAddressField, default='0.0.0.0')
```

**10 types d'action** :

| Code | Nom | Sens | Usage |
|------|-----|------|-------|
| FIRST | Genesis | — | Premier bloc par asset |
| CREATION | Création | sender→receiver | Créer des tokens |
| REFILL | Recharge | sender→receiver | Recharger un wallet |
| SALE | Vente | sender→receiver | Paiement NFC (user → lieu) |
| QRCODE_SALE | Vente QR | sender→receiver | Paiement par QR code |
| FUSION | Fusion | sender→receiver | Fusionner wallet_ephemere → wallet user |
| REFUND | Remboursement | sender→— | Retour client |
| VOID | Annulation | sender→— | Vider une carte |
| DEPOSIT | Dépôt bancaire | sender→receiver | Retrait de circulation |
| TRANSFER | Virement | sender→receiver | Transfert direct |

#### `Federation` — Partage d'assets entre tenants

```
Federation
├── uuid (PK)
├── name (CharField unique)
├── description (TextField)
├── created_by (FK → Customers.Client) — tenant créateur
├── tenants (M2M → Customers.Client) — membres actifs
├── pending_tenants (M2M → Customers.Client) — invités en attente
└── assets (M2M → Asset)
```

### 3.6 Modèles enrichis existants

**`AuthBillet.Wallet`** : +`public_pem` (TextField, nullable), +`name` (CharField 100, nullable)

**`QrcodeCashless.CarteCashless`** : +`wallet_ephemere` (OneToOne → Wallet, nullable)

**3 états d'une carte** :

| État | `user` | `wallet_ephemere` | Signification |
|------|--------|-------------------|---------------|
| Anonyme neuve | None | None | Jamais utilisée |
| Anonyme avec solde | None | Wallet(...) | Rechargée, pas identifiée |
| Identifiée | TibilletUser(...) | None | User possède `user.wallet` |

---

## 4. ViewSets et logique métier

### 4.1 Routing (`laboutik/urls.py`)

```python
router = DefaultRouter()
router.register('caisse', CaisseViewSet, basename='caisse')
router.register('paiement', PaiementViewSet, basename='paiement')
router.register('commande', CommandeViewSet, basename='commande')
```

URLs résultantes :
```
/laboutik/caisse/            → CaisseViewSet.list()
/laboutik/paiement/          → PaiementViewSet
/laboutik/commande/          → CommandeViewSet
```

### 4.2 `CaisseViewSet`

Authentification : `HasLaBoutikAccess` (API key OU session admin).

| Action | URL | Template retourné |
|--------|-----|-------------------|
| `list()` | GET /caisse/ | `ask_primary_card.html` — attente scan carte primaire |
| `carte_primaire()` | POST /caisse/carte_primaire/ | Sélection PV ou redirect vers PV unique |
| `point_de_vente()` | GET /caisse/point_de_vente/<uuid>/ | `common_user_interface.html` — interface principale |
| `moyens_paiement()` | POST /caisse/moyens_paiement/ | `hx_display_type_payment.html` |
| `display_type_payment()` | GET /caisse/display_type_payment/ | Boutons de paiement |
| `payer()` | POST /caisse/payer/ | Route vers espèces/CB/NFC |
| `retour_carte()` | POST /caisse/retour_carte/ | `hx_card_feedback.html` — solde carte |
| `adhesion_choisir_identification()` | GET /paiement/adhesion_choisir_identification/ | Choix méthode identification adhésion |
| `lire_nfc_adhesion()` | GET /paiement/lire_nfc_adhesion/ | Écran attente scan NFC adhésion |
| `adhesion_formulaire()` | GET /paiement/adhesion_formulaire/ | Formulaire email/nom/prénom adhésion |
| `identifier_membre()` | POST /paiement/identifier_membre/ | Traitement identification (NFC ou formulaire) |

**`carte_primaire()` — flux** :
1. Valide via `CartePrimaireSerializer` (champ `tag_id`)
2. `CarteCashless.objects.get(tag_id=tag_id)` → `CartePrimaire.objects.get(carte=...)`
3. Si 1 PV → redirect `point_de_vente()` ; si plusieurs → écran de sélection
4. Si aucune `CartePrimaire` → message d'erreur

**`point_de_vente()` — flux** :
1. `PointDeVente.objects.prefetch_related('categories', 'products__prices').get(uuid=uuid_pv)`
2. `_construire_donnees_articles(pv)` → liste des articles avec couleurs/icones résolues
3. `LaboutikConfiguration.get_solo()` → variable CSS `--article-font-size`
4. Render `common_user_interface.html` avec le contexte complet

**`_construire_donnees_articles(pv)`** — construit la liste des articles pour le template :
```python
# Pour chaque product du PV :
article_dict = {
    'id': str(product.uuid),
    'name': product.name,
    'methode_caisse': product.methode_caisse,
    'couleur_backgr': couleur_fond,   # priorité: product > categorie > fallback
    'couleur_texte': couleur_texte,
    'icone': icone,
    'icone_type': 'fa' ou 'ms',
    'prix': [{'uuid': ..., 'prix': ..., 'asset_uuid': ...}, ...],
    'categorie_uuid': str(cat.uuid) if cat else 'default',
}
```

### 4.3 `PaiementViewSet`

Contient les méthodes de paiement et le flux adhésion (identification + création Membership).

| Action (@action) | URL | Description |
|--------|-----|-------------|
| `moyens_paiement()` | POST | Affiche les boutons de paiement (détecte mode adhésion) |
| `payer()` | POST | Route vers `_payer_par_nfc`, `_payer_par_especes`, `_payer_par_carte_bancaire` |
| `retour_carte()` | POST | Solde réel depuis `Token` |
| `adhesion_choisir_identification()` | GET | Choix méthode identification (NFC vs formulaire) |
| `lire_nfc_adhesion()` | GET | Écran attente scan NFC adhésion |
| `adhesion_formulaire()` | GET | Formulaire email/nom/prénom |
| `identifier_membre()` | POST | Traitement identification → écran confirmation |

| Helpers (privés) | Description |
|--------|-------------|
| `_payer_par_especes()` | Cash + calcul rendu de monnaie |
| `_payer_par_carte_bancaire()` | CB/chèque (mock en dev) |
| `_payer_par_nfc()` | NFC cashless via `fedow_core` (atomique) |
| `_creer_ligne_article()` | Crée `PriceSold + ProductSold + LigneArticle` |
| `_determiner_moyens_paiement()` | Détermine les moyens disponibles (exclut NFC si recharges) |
| `_panier_contient_recharges()` | Vérifie présence de RE/RC/TM dans le panier |
| `_creer_adhesions_depuis_panier()` | Crée les `Membership` depuis les articles adhésion |
| `_creer_ou_renouveler_adhesion()` | Crée ou renouvelle une adhésion pour un user |

**⚠️ `PriceSold + ProductSold`** : `LigneArticle.pricesold` pointe vers `PriceSold` (pas `Price` directement).
`PriceSold` pointe vers `ProductSold` (pas `Product`). Toute vente doit créer ces intermédiaires.

### 4.4 `CommandeViewSet`

| Action | Description |
|--------|-------------|
| `ouvrir_commande()` | Crée `CommandeSauvegarde` + lie à une table |
| `ajouter_articles()` | Ajoute des `ArticleCommandeSauvegarde` à une commande OPEN |
| `marquer_servie()` | Passe `CommandeSauvegarde.statut` → SERVED |
| `payer_commande()` | Réutilise les méthodes de paiement de `PaiementViewSet` |
| `annuler_commande()` | Passe → CANCEL, libère la table |

### 4.5 Serializers (`laboutik/serializers.py`)

**Règle stack-ccc** : tout POST est validé via un `serializers.Serializer`. Jamais `request.POST` brut.

| Serializer | Champs | Usage |
|------------|--------|-------|
| `CartePrimaireSerializer` | `tag_id` (CharField 8, uppercase) | Scan carte primaire |
| `ArticlePanierSerializer` | `uuid`, `qty` | 1 article dans le panier |
| `PanierSerializer` | `articles[]`, méthode statique `extraire_articles_du_post()` | Panier complet |
| `ArticleCommandeSerializer` | `product_uuid`, `price_uuid`, `qty` | Ligne de commande |
| `CommandeSerializer` | `table_uuid`, `articles[]` | Nouvelle commande |
| `ClotureSerializer` | `uuid_pv` (datetime_ouverture calculé auto) | Clôture |
| `AdhesionIdentificationSerializer` | `email`, `first_name`, `last_name`, `tag_id` | Identification client adhésion |
| `EnvoyerRapportSerializer` | `email`, `uuid_cloture` | Envoi rapport clôture |

**Format du panier (multi-tarif)** :
```
repid-<product_uuid>--<price_uuid>   → article standard
custom-<product_uuid>--<price_uuid>  → prix libre (montant dans le champ custom-*)
```

---

## 5. Composants Cotton et JavaScript

### 5.1 Composant `<c-read-nfc>`

Gère la lecture NFC et l'envoi du formulaire associé.

```html
<c-read-nfc
    id="nfc-container"
    event-manage-form="primaryCardManageForm"
    submit-url="ask_primary_card">
    <form id="form-nfc" class="hide"
          hx-post="ask_primary_card"
          hx-trigger="nfcResult"
          hx-target=".message-nfc"
          hx-swap="innerHTML">
        {% csrf_token %}
        <input id="nfc-tag-id" name="tag_id" />
    </form>
    <h1>{% translate "Attente carte primaire" %}</h1>
</c-read-nfc>
```

**Attributs** :
- `id` : référence le conteneur HTML principal (pour le bouton retour)
- `event-manage-form` : nom de l'événement qui gère l'insertion du tagId et l'envoi du formulaire
- `submit-url` : URL initiale du formulaire (peut être changée dynamiquement)

**Le handler `manageForm(event)`** reçoit des commandes via `event.detail.actionType` :
- `updateInput` : met à jour la valeur d'un input (`selector`, `value`)
- `postUrl` : change l'URL du formulaire HTMX (`value`)
- `submit` : déclenche l'envoi du formulaire

**Fichier JS** : `laboutik/static/js/nfc.js` — lecture NFC physique + simulation dev.

**Deux contextes d'utilisation** :
1. **Carte primaire** (`ask_primary_card.html`) : event `primaryCardManageForm`
2. **Interface POS** (`common_user_interface.html` + `addition.js`) : event `additionManageForm`

### 5.2 Composant `<c-articles>`

Affiche la grille d'articles du point de vente.

**Écoute** :
- `articlesRemove` — retire un article de la vue
- `articlesReset` — réinitialise la grille
- `articlesDisplayCategory` — filtre par catégorie

**Émet** :
- `articlesAdd` → vers `eventsOrganizer`

**Structure HTML d'une tuile** (`cotton/articles.html`) :
```
.article-container (data-testid="article-{uuid}")
├── .article-img-layer (si image)
├── .article-body-layer (flex row, position:absolute)
│   ├── .article-cat-icon (FA/MS icon, flex-shrink:0 — HORS du -webkit-box)
│   │   Badge catégorie haut-gauche (1.4rem, opacité 0.75)
│   └── .article-name-text (-webkit-line-clamp:3, min-width:0, 1.2rem)
├── .article-visual-layer (icône produit centrée, 0.38 * --bt-article-width)
├── .article-name-layer (nom en bas, au-dessus du footer)
├── .article-footer-layer (position:absolute, left+right SANS width:100%)
│   ├── .article-tarifs-pills (flex-wrap:wrap, max-height:62px, overflow:hidden)
│   │   └── .article-tarif-pill (1.1rem, tabular-nums, fond rgba(0,0,0,0.65))
│   │       .article-tarif-pill-libre (fond indigo, "? €")
│   └── .article-quantity (badge, masqué si qty=0)
├── .article-touch (absorbe le clic, déclenche feedback)
└── .article-lock-layer
```

**Breakpoints tuiles** :

| Viewport | `--bt-article-width` |
|----------|----------------------|
| < 600px | 130px |
| > 599px | 140px |
| > 1022px | 100px (dense) |
| > 1278px | 160px (Sunmi D3mini) |

**⚠️ Pièges CSS documentés** :
1. `<i class="fas">` DANS un container `-webkit-box` → pseudo-élément `::before` FA pas rendu. Toujours mettre l'icône FA comme sibling HORS du span lineclamp.
2. `position: absolute; left: Xpx; right: Xpx; width: 100%` → conflit. Avec left+right, la largeur est implicite.
3. `max-height` sur `.article-name-text` → coupe les hampes descendantes (g, p, y). Utiliser `-webkit-line-clamp`.
4. `calc(var(--bt-article-width) * 0.18)` pour les polices → donne la taille de la variable CSS, pas la taille rendue (1fr élargit la tuile). Utiliser des rem fixes.

**Double système d'icônes** :
- `startswith("fa")` → FontAwesome 5 : `<i class="fas fa-beer">`
- Sinon → Material Symbols Outlined : `<span class="material-symbols-outlined">local_bar</span>`
- Détection automatique dans `views.py` → `icone_type` passé au template

### 5.3 Composant `<c-addition>`

Panier d'achat (à droite de l'interface).

**Écoute** :
- `additionInsertArticle` — ajoute un article au panier
- `additionReset` — vide le panier
- `additionDisplayPaymentTypes` — déclenche l'affichage des modes de paiement
- `additionUpdateForm` — met à jour le formulaire

**Émet** :
- `additionRemoveArticle` → vers `eventsOrganizer`
- `additionTotalChange` → met à jour le bouton VALIDER

**Tous les événements passent par `eventsOrganizer`** via l'événement `organizerMsg`.

**Gestion multi-tarif** (`tarif.js`) :
- Quand un produit a plusieurs `Price` ou `free_price=True` → overlay de sélection
- Format clé dans le formulaire : `repid-<product_uuid>--<price_uuid>`
- Prix libre : `custom-<product_uuid>--<price_uuid>` + validation front (minimum) + validation back (serializer)
- **Amélioration prévue** : overlay non-bloquant (remplace la zone articles, pas #messages),
  quantités multiples sans fermer l'overlay. Voir section 15 "Amélioration Multi-Tarif".

### 5.4 Événements JS globaux

Tous les composants communiquent via l'`eventsOrganizer` dans `tibilletUtils.js`.

```
Clic article
  → articles.js:addArticle()
  → événement 'articlesAdd'
  → eventsOrganizer() (tibilletUtils.js)
  → si multi-tarif : tarif.js:showTarifOverlay()
  → sinon : addition.js:additionInsertArticle()
  → événement 'additionTotalChange'
  → updateBtValider() sur #bt-valider
```

**Clic VALIDER** :
```
Clic #bt-valider
  → événement 'additionDisplayPaymentTypes'
  → eventsOrganizer()
  → addition.js:additionDisplayPaymentTypes()
  → requête HTMX → hx_display_type_payment.html
```

**Fichiers JS** (`laboutik/static/laboutik/js/`) :
- `nfc.js` — lecture NFC physique + simulation dev
- `articles.js` — gestion de la grille d'articles, `manageKey()`, interception multi-tarif
- `addition.js` — panier, total, formulaire, `askManageAddition()` (confirmation espèces)
- `tibilletUtils.js` — `eventsOrganizer`, routage des événements, route `tarifSelection`
- `tarif.js` — overlay sélection de tarif, validation prix libre
- `categories.js` — gestion de la sidebar catégories, highlight actif

---

## 6. Flux de paiement détaillés

### 6.1 Paiement en espèces

```
POST /paiement/payer/ (méthode=especes)
  → PanierSerializer.valider()
  → _payer_par_especes()
    → calculer_total_addition(articles)
    → db_transaction.atomic():
        for article in articles:
            _creer_ligne_article(article, payment_method='CA')
    → calculer rendu de monnaie
  → hx_return_payment_success.html
```

**Écran espèces** (`hx_confirm_payment.html`) :
- "À encaisser : X,XX €" en 2.5rem
- Champ input : 80px height, 2rem font, autofocus, inputmode="decimal"
- Symbole "€" en suffixe
- "VALIDER" en majuscules
- `role="alert"` sur le message d'erreur
- Media query `@media (max-width: 600px)` : boutons empilés verticalement

**Écran succès** (`hx_return_payment_success.html`) :
- "Paiement réussi" (was "Transaction ok")
- Icône fa-check-circle 4rem + animation scale-in 300ms
- "Payé en espèce : X,XX €" (was "Total(espece)")
- Box monnaie à rendre : fond `--rouge07`, bordure `--warning00`, 2.5rem, fa-hand-holding-usd

### 6.2 Paiement CB / Chèque

Même flux que espèces, `payment_method='CC'` ou `'CH'`. Mock en dev (retourne toujours succès).

### 6.3 Paiement NFC cashless

```
POST /paiement/payer/ (méthode=nfc)
  → PanierSerializer.valider()
  → hx_read_nfc.html (attente scan carte client)
    → scan NFC → tag_id
  → _payer_par_nfc(tag_id, articles)
    → CarteCashless.objects.get(tag_id=tag_id)
    → WalletService.obtenir_solde_total(utilisateur)
    → si solde insuffisant → hx_funds_insufficient.html (montant manquant)
    → si solde OK :
        db_transaction.atomic():
            TransactionService.creer_vente(wallet_client, wallet_lieu, asset, montant, tenant)
            → WalletService.debiter(wallet_client, asset, montant)
            → WalletService.crediter(wallet_lieu, asset, montant)
            → Transaction.objects.create(action=SALE, ...)
            for article in articles:
                _creer_ligne_article(article, payment_method='NFC')
  → hx_return_payment_success.html
```

**⚠️ Atomicité** : `Token` (public schema) + `LigneArticle` (tenant schema) dans le même `transaction.atomic()`. Garanti par Django sur la même connexion PostgreSQL.

### 6.4 Recharge cashless

```
POST /caisse/retour_carte/ (mode recharge)
  → hx_read_nfc_recharge.html
    "Posez la carte du client sur le lecteur"
    Montant total affiché en 2rem bold
  → scan NFC → tag_id
  → valider CarteCashless + wallet_ephemere si anonyme
  → choisir moyen de recharge (espèces/CB)
  → db_transaction.atomic():
      TransactionService.creer_recharge(wallet_lieu, wallet_client, asset, montant, tenant)
      → sens inversé : sender=lieu, receiver=client
  → hx_card_feedback.html avec nouveau solde
```

**⚠️ Sécurité** : les recharges NFC (RE/RC/TM) ne peuvent pas être payées par NFC.
3 couches de protection dans `views.py` : `METHODES_RECHARGE`, `_panier_contient_recharges()`,
`_determiner_moyens_paiement()`, + garde finale dans `_payer_par_nfc()` (400 + message).

### 6.5 POS Adhésion — Wizard d'identification et paiement

**⚠️ État actuel** — sera modifié par la refonte typage (section 15). Le `comportement='A'`
sera supprimé. Les produits adhésion seront dans le M2M standard du PV.
Le flow d'identification reste identique (piloté par l'article, pas le PV).

Le POS Adhésion (`comportement='A'` actuellement) impose une
**identification du membre avant le paiement**. Le caissier ne peut pas créer d'adhésion
sans savoir à qui elle est rattachée. Cela se traduit par un wizard HTMX en 3-4 écrans
avec un arbre de décision à 6 chemins selon le moyen de paiement et le type de carte.

#### Chargement dynamique des produits

Le PV Adhésion **n'a PAS de M2M `products`** configuré. Les produits sont chargés
dynamiquement dans `_construire_donnees_articles()` :

```python
# Pour les PV de type ADHESION : ajouter dynamiquement les produits adhésion publiés
# / For ADHESION-typed POS: dynamically add published membership products
if point_de_vente_instance.comportement == PointDeVente.ADHESION:
    produits_adhesion = Product.objects.filter(
        categorie_article=Product.ADHESION, publish=True,
    ).select_related('categorie_pos').prefetch_related(prix_euros_prefetch)
    # Merge sans doublons (par uuid) — produits manuels prioritaires
    produits_par_uuid = {}
    for p in chain(produits_adhesion, produits_manuels):
        produits_par_uuid[str(p.uuid)] = p
    produits = sorted(produits_par_uuid.values(), key=lambda p: (p.poids or 0, p.name))
```

Les articles adhésion sont groupés dans `groupe_AD` dans le contexte template.
Le PV utilise le même template `common_user_interface.html` que le POS Direct (si `service_direct=True`).

#### Détection du mode adhésion

Quand le caissier clique VALIDER, `moyens_paiement()` détecte les articles adhésion :

```python
panier_a_adhesions = any(
    a['product'].categorie_article == Product.ADHESION
    for a in articles_panier
)
```

Si `panier_a_adhesions=True`, le template `hx_display_type_payment.html` affiche des
**boutons spéciaux** qui redirigent vers le wizard d'identification AVANT le paiement :
- **CASHLESS** → direct vers `lire_nfc_adhesion()` (la carte identifie le membre)
- **ESPÈCE / CB / CHÈQUE** → vers `adhesion_choisir_identification()` (choix NFC ou formulaire)

#### Arbre de décision — 6 chemins

```
Panier avec article(s) adhésion → clic VALIDER
  ↓
moyens_paiement() → panier_a_adhesions=True
  ↓
hx_display_type_payment.html (mode adhésion)
  │
  ├─ CASHLESS ──────────────────────────────────────────────────────────┐
  │   → lire_nfc_adhesion()                                             │
  │   → hx_read_nfc_adhesion.html (attente scan)                       │
  │   → scan NFC → POST identifier_membre(tag_id)                      │
  │      │                                                              │
  │      ├─ Chemin 1 : carte AVEC user                                  │
  │      │  → identifier_membre() trouve carte.user                     │
  │      │  → hx_adhesion_confirm.html (nom, email, solde wallet)       │
  │      │  → clic CONFIRMER → POST payer()                             │
  │      │                                                              │
  │      └─ Chemin 2 : carte ANONYME (pas de user)                      │
  │         → identifier_membre() trouve carte mais user=None           │
  │         → hx_adhesion_form.html (avec tag_id en champ caché)        │
  │         → saisie email/prénom/nom → POST identifier_membre()        │
  │         → get_or_create_user(email)                                 │
  │         → hx_adhesion_confirm.html                                  │
  │         → clic CONFIRMER → POST payer()                             │
  │                                                                     │
  ├─ ESPÈCE / CB / CHÈQUE ─────────────────────────────────────────────┐
  │   → adhesion_choisir_identification(?method=espece|cb|CH)           │
  │   → hx_adhesion_choose_id.html                                     │
  │      │                                                              │
  │      ├─ "Scanner une carte TiBillet"                                │
  │      │   → lire_nfc_adhesion()                                      │
  │      │   → hx_read_nfc_adhesion.html (attente scan)                │
  │      │   → scan NFC → POST identifier_membre(tag_id)               │
  │      │      │                                                       │
  │      │      ├─ Chemin 3 : carte AVEC user                           │
  │      │      │  → hx_adhesion_confirm.html (direct)                  │
  │      │      │  → clic CONFIRMER → POST payer()                      │
  │      │      │                                                       │
  │      │      └─ Chemin 4 : carte ANONYME                             │
  │      │         → hx_adhesion_form.html (tag_id caché)               │
  │      │         → saisie → hx_adhesion_confirm.html                  │
  │      │         → clic CONFIRMER → POST payer()                      │
  │      │                                                              │
  │      └─ "Saisir email / nom"                                        │
  │          → adhesion_formulaire(?method=...)                         │
  │          → hx_adhesion_form.html (formulaire vierge, pas de tag_id) │
  │          → saisie email + prénom + nom                              │
  │          → POST identifier_membre(email, prenom, nom)               │
  │          │                                                          │
  │          ├─ Chemin 5 : espèces + saisie email                       │
  │          │  → get_or_create_user(email)                             │
  │          │  → hx_adhesion_confirm.html                              │
  │          │  → clic CONFIRMER → POST payer()                         │
  │          │                                                          │
  │          └─ Chemin 5bis : CB + saisie email (même flow)             │
  │                                                                     │
  └─────────────────────────────────────────────────────────────────────┘
```

#### Actions ViewSet (PaiementViewSet)

| Action | Méthode | URL | Template retourné |
|--------|---------|-----|-------------------|
| `adhesion_choisir_identification()` | GET | `/paiement/adhesion_choisir_identification/?method=espece` | `hx_adhesion_choose_id.html` |
| `lire_nfc_adhesion()` | GET | `/paiement/lire_nfc_adhesion/?method=nfc` | `hx_read_nfc_adhesion.html` |
| `adhesion_formulaire()` | GET | `/paiement/adhesion_formulaire/?method=espece` | `hx_adhesion_form.html` |
| `identifier_membre()` | POST | `/paiement/identifier_membre/` | `hx_adhesion_confirm.html` ou `hx_adhesion_form.html` |

Le paramètre `method` est propagé à travers tout le wizard via des champs cachés
pour savoir quel moyen de paiement utiliser à la fin (espèce, CB, chèque, NFC).

#### Templates adhésion (4 fichiers)

| Template | Rôle | Éléments clés |
|----------|------|---------------|
| `hx_adhesion_choose_id.html` | Choix méthode d'identification | 2 boutons : "Scanner carte" / "Saisir email/nom" |
| `hx_read_nfc_adhesion.html` | Attente scan NFC | Composant `<c-read-nfc>`, champ caché `moyen_paiement` |
| `hx_adhesion_form.html` | Formulaire email/prénom/nom | Labels flottants, validation CSS, `tag_id` caché si carte anonyme |
| `hx_adhesion_confirm.html` | Résumé + bouton CONFIRMER | Email, nom (MAJUSCULES), solde wallet (si NFC), JS `confirmerAdhesion()` |

**`confirmerAdhesion()`** (JS dans `hx_adhesion_confirm.html`) :
1. Injecte les champs cachés `email_adhesion`, `prenom_adhesion`, `nom_adhesion`, `tag_id` dans `#addition-form`
2. Change l'URL HTMX du formulaire vers `/paiement/payer/`
3. Déclenche le submit du formulaire via `eventsOrganizer`

#### Logique `identifier_membre()` — le cœur du wizard

```python
POST /paiement/identifier_membre/
  ├─ Données reçues : tag_id (NFC) ET/OU email_adhesion + prenom + nom (form)
  │
  ├─ SI tag_id fourni :
  │   → CarteCashless.objects.get(tag_id=tag_id)
  │   → SI carte.user existe :
  │   │   → user identifié → hx_adhesion_confirm.html (avec solde wallet)
  │   └─ SI carte.user = None (anonyme) :
  │       → hx_adhesion_form.html (avec tag_id en champ caché)
  │
  ├─ SI email fourni ET pas encore de user :
  │   → AdhesionIdentificationSerializer.validate(email, prenom, nom)
  │   → get_or_create_user(email, send_mail=False)
  │   → update user.first_name / user.last_name si pas déjà renseignés
  │   → hx_adhesion_confirm.html
  │
  └─ SI rien fourni :
      → hx_adhesion_form.html (formulaire vierge)
```

**Validation** (`AdhesionIdentificationSerializer`) :
- `email_adhesion` : EmailField obligatoire
- `prenom_adhesion` : CharField obligatoire, max 200, non vide
- `nom_adhesion` : CharField obligatoire, max 200, non vide
- `tag_id` : CharField optionnel (champ caché)
- `moyen_paiement` : CharField optionnel (propagé)

#### Création des adhésions au paiement

Quand `payer()` est appelé avec les données d'identification injectées par `confirmerAdhesion()` :

**Espèces / CB / Chèque** :
```
payer() → _payer_en_especes() ou _payer_par_carte_ou_cheque()
  → _creer_lignes_articles(articles_normaux, moyen_paiement)
  → _creer_adhesions_depuis_panier(request, articles_panier, lignes_articles)
```

**NFC Cashless** :
```
payer() → _payer_par_nfc()
  → sépare articles_vente et articles_adhesion
  → vérifie solde total (ventes + adhésions)
  → db_transaction.atomic():
      TransactionService.creer_vente() pour les ventes
      TransactionService.creer_vente() pour les adhésions (débit TLF)
      _creer_lignes_articles(articles_adhesion)
      _creer_ou_renouveler_adhesion() × N articles
      ligne.membership = membership → save()
```

#### `_creer_adhesions_depuis_panier()` — logique métier

```python
def _creer_adhesions_depuis_panier(request, articles_panier, lignes_articles=None):
    # 1. Filtrer les articles adhésion du panier
    articles_adhesion = [a for a in articles_panier if a['product'].categorie_article == Product.ADHESION]

    # 2. Identification (priorité tag_id > email)
    tag_id → CarteCashless → carte.user
    email → get_or_create_user(email)
    if user is None → raise ValueError("Identification obligatoire")

    # 3. Fusion wallet éphémère (si carte NFC scannée)
    if tag_id and carte:
        WalletService.fusionner_wallet_ephemere(carte, user, tenant, ip)

    # 4. Créer/renouveler les adhésions
    for article in articles_adhesion:
        contribution = custom_amount (prix libre) or price.prix
        membership = _creer_ou_renouveler_adhesion(user, product, price, contribution, prenom, nom)
        ligne.membership = membership → save()  # rattacher à LigneArticle
```

#### `_creer_ou_renouveler_adhesion()` — création / renouvellement

```python
def _creer_ou_renouveler_adhesion(user, product, price, contribution_value, first_name, last_name):
    # Cherche une adhésion existante (user + price) non annulée
    existante = Membership.objects.filter(user=user, price=price).exclude(CANCELED).first()

    if existante:
        # RENOUVELER : mettre à jour last_contribution, status=LABOUTIK, recalculer deadline
        existante.last_contribution = now()
        existante.status = Membership.LABOUTIK
        existante.contribution_value = contribution
        existante.set_deadline()  # calcule la date d'expiration selon subscription_type
        return existante

    # CRÉER : nouvelle adhésion
    nouvelle = Membership.objects.create(
        user=user, price=price, status=Membership.LABOUTIK,
        last_contribution=now(), first_contribution=now(),
        contribution_value=contribution, first_name=prenom, last_name=nom,
    )
    nouvelle.set_deadline()
    return nouvelle
```

**Status** : `Membership.LABOUTIK` (distinct de `Membership.PAID` qui vient du web).

#### Fusion wallet éphémère → user.wallet

Déclenchée quand une carte NFC est scannée pendant l'identification :

```
WalletService.fusionner_wallet_ephemere(carte, user, tenant, ip)
  1. Crée user.wallet si inexistant
  2. Pour chaque Token du wallet_ephemère avec value > 0 → Transaction(FUSION)
     sender=wallet_ephemere, receiver=user.wallet
  3. Pose carte.user = user et carte.wallet_ephemere = None
  4. La carte devient "identifiée" (état 3 du tableau section 3.6)
```

Reproduit `LinkWalletCardQrCode.fusion()` de l'ancien Fedow (V1).

#### Tests

**Test E2E** : `tests/playwright/tests/laboutik/44-laboutik-adhesion-identification.spec.ts`

Teste les 6 chemins du wizard + les boutons retour :

| Test | Chemin | Flow |
|------|--------|------|
| chemin 1 | CASHLESS → NFC carte avec user → confirmation | Direct |
| chemin 2 | CASHLESS → NFC carte anonyme → formulaire → confirmation | Formulaire après NFC |
| chemin 3 | Espèce → scanner carte (user connu) → confirmation → payer | Complet avec paiement |
| chemin 4 | Espèce → scanner carte (anonyme) → formulaire → confirmation → payer | Complet avec fusion wallet |
| chemin 5 | Espèce → saisir email → confirmation → payer | Vérification DB (Membership créé) |
| chemin 5bis | CB → saisir email → confirmation → payer | Vérifie que CB route aussi |
| retour 1 | Bouton retour depuis écran identification | Ferme le layer |
| retour 2 | Bouton retour depuis formulaire email | Ferme le layer |

**Données de test** :
- Carte primaire : `DEMO_TAGID_CM='A49E8E2A'`
- Carte anonyme : `DEMO_TAGID_CLIENT1='52BE6543'` (reset avant/après tests)
- Carte jetable : `DEMO_TAGID_CLIENT3='D74B1B5D'` (user assigné en `beforeAll`, reset en `afterAll`)
- PV Adhésion : créé par `create_test_pos_data` avec `comportement=ADHESION`, `service_direct=True`

**⚠️ Ordre d'exécution** : chemin 2 DOIT tourner AVANT chemin 4 (chemin 2 enregistre la carte anonyme, chemin 4 la réutilise avec un user).

**`data-testid` des éléments du wizard** :

| Élément | data-testid |
|---------|-------------|
| Boutons paiement adhésion | `adhesion-btn-nfc`, `adhesion-btn-especes`, `adhesion-btn-cb`, `adhesion-btn-cheque` |
| Écran choix identification | `adhesion-choose-id` |
| Option scanner carte | `adhesion-choose-nfc` |
| Option saisir email | `adhesion-choose-email` |
| Formulaire email/nom | `adhesion-form` |
| Champ email | `adhesion-input-email` |
| Champ prénom | `adhesion-input-prenom` |
| Champ nom | `adhesion-input-nom` |
| Bouton valider formulaire | `adhesion-btn-valider` |
| Écran confirmation | `adhesion-confirm` |
| Info user confirmé | `adhesion-confirm-user` |
| Bouton confirmer | `adhesion-btn-confirmer` |
| Succès paiement | `paiement-succes` |

### 6.6 Retour carte (check carte)

```
POST /caisse/retour_carte/ (hors mode recharge)
  → scan NFC → tag_id
  → CarteCashless.objects.get(tag_id=tag_id)
  → WalletService.obtenir_tous_les_soldes(utilisateur)
  → Membership.objects.filter(user=utilisateur).actives()
  → hx_card_feedback.html
```

**Écran retour carte** (`hx_card_feedback.html`) :
- Icône fa-id-card 3rem en haut
- "Carte anonyme" + fa-user-secret (si `user=None`)
- "Carte avec nom" + email affiché (was "Carte fédérée")
- Icônes par type d'asset : TLF → fa-euro-sign, TNF → fa-gift, TIM → fa-clock, défaut → fa-coins
- Section adhésions avec fa-id-badge + deadline
- `data-testid` : `retour-carte-anonyme`, `retour-carte-nom`, `retour-carte-email`, `retour-carte-solde-N`, `retour-carte-adhesion-N`

---

## 7. Mode restaurant (tables + commandes)

### Activation

`PointDeVente.accepte_commandes = True` → active le mode restaurant pour ce PV.

### Interface tables (`views/tables.html`)

Affiche le plan de salle avec toutes les tables actives (non archivées).
Statut visuel : L (Libre) → fond neutre, O (Occupée) → fond coloré, S (Servie) → fond différent.

### Cycle de vie d'une commande

```
Ouvrir commande (CommandeViewSet.ouvrir_commande)
  → CommandeSauvegarde(statut=OPEN)
  → Table.statut = OCCUPEE

Ajouter articles (CommandeViewSet.ajouter_articles)
  → ArticleCommandeSauvegarde × N (statut=EN_ATTENTE)
  → Envoi à la cuisine (si configuré)

Marquer servie (CommandeViewSet.marquer_servie)
  → CommandeSauvegarde.statut = SERVED
  → Table.statut = SERVIE

Payer (CommandeViewSet.payer_commande)
  → Réutilise PaiementViewSet._payer_par_nfc/especes/cb
  → CommandeSauvegarde.statut = PAID
  → Table.statut = LIBRE
  → archive=True après clôture

Annuler (CommandeViewSet.annuler_commande)
  → CommandeSauvegarde.statut = CANCEL
  → Table.statut = LIBRE
```

**⚠️** Lire le front JS des tables AVANT de coder — le JS existe dans les templates laboutik.

---

## 8. Clôture caisse

### Déclenchement

```
POST /caisse/cloturer/ (CaisseViewSet ou action dédiée)
  → ClotureSerializer.valider()
  → db_transaction.atomic():
      LigneArticle.objects.filter(
          point_de_vente=pv,
          datetime__gte=datetime_ouverture
      ).aggregate(...)  → totaux par payment_method
      ClotureCaisse.objects.create(
          total_especes, total_carte_bancaire, total_cashless,
          total_general, nombre_transactions,
          rapport_json=_construire_rapport_json(lignes)
      )
  → Celery: envoyer_rapport_cloture(uuid_cloture)
```

### Rapport JSON

Structure du `rapport_json` :
```json
{
    "par_categorie": [{"categorie": "...", "total_centimes": 0, "produits": []}],
    "par_produit": [{"product": "...", "qty": 0, "total_centimes": 0}],
    "par_moyen_paiement": {"especes": 0, "carte_bancaire": 0, "cashless": 0},
    "commandes": [{"table": "...", "statut": "...", "total_centimes": 0}]
}
```

### Export

- **PDF** (`pdf.py`) : `generer_pdf_cloture()` via WeasyPrint
- **CSV** (`csv_export.py`) : export des lignes
- **Email** (`tasks.py`) : tâche Celery `envoyer_rapport_cloture()` — envoie PDF + CSV en pièce jointe

### Impression ticket (Phase Impression — à faire après WebSocket)

Stub `imprimer_billet()` (console logger) en attendant le vrai module.
Voir section 15 "Phase Impression" pour le plan complet :
- 2 backends : Sunmi Cloud (HTTPS) + Sunmi Inner (WebSocket D3mini/V2S)
- Celery pour impression async avec retry (fire-and-forget, jamais bloquant)
- Routage commande : `CategorieProduct.printer` FK → split par imprimante (cuisine, bar)
- Routage vente : `PointDeVente.printer` FK → imprimante du POS
- `PrinterConsumer` WebSocket dédié (`ws/printer/{uuid}/`) pour les Inner
- Architecture modulaire (pattern Strategy) pour ajouter d'autres marques

---

## 9. UX — Interface POS

### Design system

| Élément | Valeur |
|---------|--------|
| Police | Luciole-regular (FALC, inclusive) |
| Couleurs | Palette CSS variables (`--rouge01`..`--bleu11`, `--vert01`..`--vert05`) |
| Layout | Flexbox custom (`BF-ligne`, `BF-col`) + CSS Grid (addition) |
| Composants | Cotton templates |
| Responsive | 4 breakpoints (599px, 1022px, 1199px, 1278px Sunmi D3mini) |
| Icônes | FontAwesome 5.11 + Material Symbols Outlined (coexistence) |
| Tactile | `user-select: disabled`, `min-height 48px` par zone cliquable |

**Règles CSS transversales** :
1. Pas de framework CSS — tout en CSS custom (variables existantes)
2. Police Luciole : ne pas changer
3. `tabular-nums` sur tous les chiffres qui changent
4. `text-wrap: balance` sur les titres courts
5. Animations interruptibles : CSS `transition` pour les interactions
6. `data-testid` sur chaque nouvel élément interactif
7. `aria-live` sur les zones mises à jour dynamiquement

### Layout principal

```
┌──────────┬────────────────────────────────────┬──────────────┐
│ [Tous]   │  [Bière] [Coca] [Eau] [Jus] [Lim] │ QTE PROD PRIX│
│ [Bar]    │  [Caca]  [Cook] [VinR][VinB][Past] │              │
│ [Snacks] │  [Rech€] [RechC][RechT]            │  (panier)    │
│ [Vins]   │                                     │              │
├──────────┴────────────────────────────────────┴──────────────┤
│ [RESET]        [CHECK CARTE]           [VALIDER 0,00€]       │
└──────────────────────────────────────────────────────────────┘
```

Footer `data-testid` : `footer-reset`, `footer-check-carte`, `footer-valider`

### Couleurs des boutons de paiement

| Moyen | Variable CSS | data-testid |
|-------|-------------|-------------|
| CASHLESS | `--bleu03` (#0345ea) | `paiement-btn-cashless` |
| ESPÈCE | `--success` (#339448) | `paiement-btn-especes` |
| CB | `--bleu05` (#012584) | `paiement-btn-cb` |
| CHÈQUE | `--gris02` (#4d545a) | `paiement-btn-cheque` |
| OFFRIR | `--warning00` (#f5972b) + texte `--noir01` | `paiement-btn-offrir` |

### Sessions UX réalisées

| Session | Contenu | Statut |
|---------|---------|--------|
| **1** | Filtre catégorie + highlight + format total 2 décimales | ✅ |
| **2** | Tuiles articles (badge 0 caché, feedback tactile, pills multi-tarif, lisibilité nuit) | ✅ |
| **3** | Écrans paiement (couleurs boutons, confirmation espèces, succès, retour carte) | ✅ |
| **4** | Header (bordure verte), sidebar catégories, footer (tabular-nums), menu burger (slide-down + overlay) | ✅ |
| **5** | Responsive tablette Sunmi D3mini, zones tactiles | ✅ |

### Bugs corrigés

- BUG-1 : Filtre par catégorie (CRITIQUE) — implémenté dans `articles.js:articlesDisplayCategory()`
- BUG-2 : Total "6,5 €" → "6,50 €" — `floatformat:2` + `.toFixed(2)` dans `updateBtValider()`
- BUG-3 : "uuid_transaction =" en clair — supprimé de `hx_confirm_payment.html`

---

## 10. Admin Unfold

### Sidebar Caisse (conditionnelle sur `module_caisse`)

```
Caisse
├── Articles POS (POSProductAdmin)
├── Catégories (CategorieProductAdmin)
├── Points de vente (PointDeVenteAdmin)
├── Cartes primaires (CartePrimaireAdmin)
├── Tables (TableAdmin)
├── Commandes en cours (CommandeSauvegardeAdmin)
├── Clôtures (ClotureCaisseAdmin)
└── Paramètres POS (LaboutikConfigurationAdmin) → lien "POS settings" dans sidebar
```

### Sidebar Fedow (conditionnelle sur `module_monnaie_locale`)

```
Fedow
├── Monnaies et tokens (AssetAdmin — éditable)
├── Fédérations (FederationAdmin — éditable)
├── Transactions (TransactionAdmin — lecture seule)
└── Soldes (TokenAdmin — lecture seule)
```

### `POSProductAdmin`

- Formulaire `POSProductForm` : `categorie_pos` obligatoire (`required=True`)
- `PalettePickerWidget` : sélection couleurs fond/texte (paramétrable)
- `IconPickerWidget` : sélection icône (FA ou MS)
- Help_text TVA dynamique : affiche le taux de la catégorie

### `LaboutikConfigurationAdmin`

- Unique instance (singleton)
- Champ `taille_police_articles` (select)

### Flow invitation per-asset (AssetAdmin)

1. Créateur édite un Asset → autocomplete `pending_invitations` → ajoute un lieu
2. Lieu invité voit une carte "Invitations de partage d'assets" au-dessus de sa changelist
3. Il clique "Accepter" → déplace de `pending_invitations` vers `federated_with`

**⚠️ Piège Django admin M2M** : `save_related()` écrase les M2M avec les valeurs du formulaire.
Ne jamais faire `obj.m2m.add()` dans `save_model()` — le faire dans `save_related()` APRÈS `super()`.

---

## 11. Tests

### Tests pytest

| Fichier | Tests | Couvre |
|---------|-------|--------|
| `tests/pytest/test_fedow_core.py` | 8 | Models fedow_core, services, cross-tenant |
| `tests/pytest/test_pos_models.py` | ~15 | Modèles POS, CategorieProduct |
| `tests/pytest/test_pos_views_data.py` | 8 | `_construire_donnees_articles()`, couleurs, icônes, prix |
| `tests/pytest/test_caisse_navigation.py` | 6 | Navigation caisse (carte primaire, PV) |
| `tests/pytest/test_paiement_especes_cb.py` | 8 | Paiement espèces/CB |
| Total pytest | ~84 | Tous verts sur branche integration_laboutik |

### Tests Playwright

| Spec | Tests | Couvre |
|------|-------|--------|
| `29-admin-proxy-products.spec.ts` | 6 | Proxy admins, sidebar, modules |
| `31-admin-asset-federation.spec.ts` | 12 steps | Fédération d'assets cross-tenant |
| `33-admin-audit-fixes.spec.ts` | ? | Corrections audit admin |
| `45-laboutik-pos-tiles-visual.spec.ts` | 9 | Tuiles POS : couleurs, icônes, prix, menu, filtrage |

### Données de test

Commande : `docker exec lespass_django poetry run python manage.py create_test_pos_data`

Crée :
- 2 PointDeVente : "Bar" (DIRECT), "Adhésions" (ADHESION)
- ~15 POSProduct avec couleurs, icônes, catégories
- 2 produits adhésion (annuelle 3 tarifs dont prix libre, mensuelle 1 tarif)
- 3 CartePrimaire liées à CarteCashless de test

---

## 12. Décisions architecturales (toutes prises)

| # | Décision | Choix |
|---|----------|-------|
| 16.1 | fedow_core : SHARED_APPS ou TENANT_APPS ? | **SHARED_APPS** + champ `tenant` pour filtrage |
| 16.2 | Hash chain | **Simplifiée** : hash individuel (pas de chaîne), `id` BigAutoField |
| 16.3 | Prix en centimes ou DecimalField ? | **Centimes (int) partout**, sauf `Price.prix` (existant en prod) |
| 16.4 | GroupementBouton : modèle séparé ? | **Non** : `methode_caisse` suffit (groupe_pos supprimé) |
| 16.5 | Lien POS → Product | **Product unifié** (pas d'ArticlePOS séparé) |
| 16.6 | Wallet : où vit-il ? | **Enrichir `AuthBillet.Wallet`** (+public_pem, +name) |
| 16.7 | CarteCashless : enrichir ? | **Oui** : +`wallet_ephemere` seulement |
| 16.8 | Stripe Fedow | **Dans `Paiement_stripe`** (M2M `fedow_transactions` existant) |
| 16.9 | Product unifié vs ArticlePOS séparé | **Product unifié** (LigneArticle → PriceSold → ProductSold → Product) |

**Conversion prix** (règle absolue) :
```python
montant_centimes = int(round(price.prix * 100))
# JAMAIS : int(price.prix * 100)        → tronque
# JAMAIS : via float intermédiaire      → risque IEEE 754
```

---

## 13. Passages dangereux

### 13.1 Atomicité paiement cashless

Dans la même `transaction.atomic()` :
1. Débiter `Token` sender (public schema)
2. Créditer `Token` receiver (public schema)
3. Créer `Transaction` fedow_core (public schema)
4. Créer `LigneArticle` (tenant schema)

Django-tenants ne crée pas de connexion séparée → même connexion PostgreSQL → atomicité garantie.

### 13.2 Migration des Transaction (3 phases)

1. **Import** : UUID + hash original conservés, `migrated=True`, `id` auto-attribué
2. **Production** : sans calcul de hash, `id` auto-increment garanti
3. **Consolidation** : management command `recalculate_hashes` → `hash` NOT NULL + UNIQUE

⚠️ L'ancien hash (chaîne) et le nouveau hash (individuel) ne seront pas identiques. C'est attendu.

### 13.3 Federation cross-tenant

```python
# MAL — leak cross-tenant
assets = Asset.objects.all()

# BIEN
assets = AssetService.obtenir_assets_du_tenant(tenant=connection.tenant)
```

### 13.4 Double-écriture pendant la transition

Deux populations, deux chemins. Les vues `laboutik` utilisent **toujours** `fedow_core`.
Ne jamais écrire dans `fedow_connect` (HTTP) ET `fedow_core` (DB) en même temps pour le même tenant.

### 13.5 Multi-tarif pan mixtes (EUR + tokens)

Si le panier contient des articles dans des assets différents :
```
Bière     → 500 centimes (EUR)
Concert   → 500 centi-tokens (TIM)
Sandwich  → 800 centimes (EUR)
────────────────────────────────
Totaux : 13,00 EUR + 5 TIM
```

`PaiementViewSet.payer()` doit regrouper les articles par asset et payer chaque groupe séparément.
**⚠️ Le JS est le point le plus risqué.** Prévoir une session dédiée avec le mainteneur.

### 13.6 Recharges NFC interdites

Les méthodes `RE`/`RC`/`TM` (recharges) ne peuvent PAS être payées par NFC.

**3 couches de protection** (toutes dans `laboutik/views.py`) :
1. `METHODES_RECHARGE = (Product.RECHARGE_EUROS, Product.RECHARGE_CADEAU, Product.RECHARGE_TEMPS)` — constante
2. `_panier_contient_recharges(articles_panier)` — helper qui vérifie si le panier contient des recharges
3. `_determiner_moyens_paiement(pv, articles_panier)` — exclut `'nfc'` si `_panier_contient_recharges()` retourne True
4. Garde finale dans `_payer_par_nfc()` — retourne 400 + message "Les recharges ne peuvent pas être payées en cashless"

---

## 14. Règles de travail avec Claude Code

### Méthode

- **1 phase = 1-2 sessions max.** Ne jamais enchaîner 2 phases.
- **Règle des 3 fichiers** : max 3 fichiers modifiés avant de lancer check + tests
- **Anti-hallucination** : toujours `Read` avant `Edit`, vérifier les API Django dans la doc si doute
- **Anti-sur-ingénierie** : si le plan ne le mentionne pas, ne pas le faire
- **S'arrêter et demander** : avant de toucher `settings.py`, `urls`, `PaiementStripe`, `AuthBillet`, JS, ou ajouter une dépendance

### Modèles recommandés par tâche

| Tâche | Modèle |
|-------|--------|
| Modèles / services / sécurité | Opus |
| Vues / templates / tests | Sonnet |
| Fichiers simples | Haiku |

### Checkpoints sécurité obligatoires

- **Après Phase 0** : isolation tenant (pas de leak cross-tenant)
- **Après Phase 2** : permissions (HasLaBoutikAccess, pas d'accès sans auth)
- **Après Phase 3** : atomicité (un crash partiel ne laisse pas de solde incohérent) + stress test
- **Après Phase 6** : import (tous les UUID correspondent, `verify_transactions` passe)

### Stack-ccc — règles applicables ici

1. `viewsets.ViewSet` (jamais `ModelViewSet`)
2. `serializers.Serializer` pour toute validation POST (jamais `request.POST` brut)
3. HTML partials pour les réponses HTMX (jamais JSON pour l'UI)
4. `data-*` sur les éléments HTML pour les données statiques, HTMX partial pour les mises à jour
5. Commentaires FALC bilingues FR/EN sur tout nouveau code
6. `data-testid` sur chaque élément interactif
7. `aria-live="polite"` sur les zones dynamiques
8. `{% translate %}` + `makemessages/compilemessages` après chaque feature
9. CHANGELOG.md à jour
10. Fichier dans `A TESTER et DOCUMENTER/` pour chaque feature

### FALC — méthode de commentaire

```python
def process_payment(request):
    """
    Traite le paiement et crée la transaction
    / Processes payment and creates transaction

    LOCALISATION : laboutik/views.py

    FLUX :
    1. Valide le panier via PanierSerializer
    2. ...
    """
    # Récupère les articles du POST
    # / Gets articles from POST
    articles = PanierSerializer.extraire_articles_du_post(request.POST)
```

---

## 15. Ce qui reste à faire

### Phase Refactoring Frontend — CSS, footer Cotton, sécurité, a11y (PROCHAIN)

#### Constat (audit 2026-03-19)

Le backend est conforme stack-ccc (ViewSet, Serializer, HTML partials, i18n, FALC bilingue).
Les problèmes sont côté frontend : CSS inline massif, footer dupliqué dans 3 templates.

**Le backend NE CHANGE PAS.** Seuls les templates et fichiers CSS sont touchés.
**Le JS NE CHANGE PAS** (sauf fix XSS minimal). Modifications JS à discuter avec Nicolas.

#### Pourquoi en premier

- Le composant `<c-footer>` sera réutilisé par `billetterie.html` (Phase suivante)
- L'extraction CSS évite d'ajouter encore du style inline dans les nouveaux templates
- Les fix sécurité doivent être faits avant d'ajouter des features
- C'est low-risk : pas de changement de logique, les tests Playwright valident tout

#### 1. Extraction CSS — 2171 lignes inline → fichiers séparés

| Extraction | Lignes | Source | Destination |
|------------|--------|--------|-------------|
| Styles overlay | ~1060 | 14 partials `hx_*.html` (dupliqués) | `laboutik/static/css/overlay.css` |
| Styles articles | ~431 | `cotton/articles.html` | `laboutik/static/css/articles.css` |
| Styles addition | ~145 | `cotton/addition.html` | `laboutik/static/css/addition.css` |
| Styles header | ~138 | `cotton/header.html` | `laboutik/static/css/header.css` |
| Styles categories | ~93 | `cotton/categories.html` | `laboutik/static/css/categories.css` |
| Styles footer | ~300 | 3 views (dupliqués) | `laboutik/static/css/footer.css` |

**Chargement** : un seul `<link>` dans `base.html` pour un fichier concaténé ou par composant.
Les `<style>` blocks disparaissent des templates. Le HTML devient lisible.

**⚠️ Ne PAS changer les noms de classes CSS** — les tests Playwright utilisent certaines classes.
Extraire les styles, pas renommer.

#### 2. Extraction footer → composant Cotton `<c-footer>`

Le footer (RESET / CHECK CARTE / VALIDER) est hardcodé dans 3 templates avec 300 lignes
de CSS dupliqué (`common_user_interface.html`, `kiosk.html`, `tables.html`).

**Solution** : composant Cotton `<c-footer>` avec attributs pour les variantes :

```html
<!-- Usage dans common_user_interface.html -->
<c-footer show_reset="true" show_check_carte="true" show_valider="true" />

<!-- Usage dans kiosk.html -->
<c-footer show_reset="false" show_check_carte="true" show_valider="false" />
```

Le template `billetterie.html` (Phase suivante) utilisera `<c-footer>` dès sa création.

#### 3. JavaScript — on ne touche pas

Les fichiers JS (articles.js, addition.js, tarif.js, tibilletUtils.js, categories inline)
ont été développés par Nicolas. Toute modification sera discutée avec lui.

**Constat de l'audit (pour mémoire, pas d'action)** :
- Le filtrage par catégorie est du hide/show DOM pur → performant, pas besoin d'HTMX
- L'event bus (tibilletUtils.js) est fonctionnel même s'il pourrait être simplifié
- tarif.js construit l'overlay côté client → à revoir avec Nicolas si besoin

**Seules exceptions** (sécurité, changements minimaux) :
- Fix XSS dans tarif.js : `textContent` au lieu de `innerHTML` pour les données produit
- Validation prix libre côté serveur (ajout Python uniquement)

#### 4. Sécurité — 2 corrections

##### a. Validation prix libre côté serveur

`tarif.js` valide le montant minimum en client-only. Ajouter dans views.py :

```python
# Dans laboutik/views.py, _extraire_articles_du_panier()
if custom_amount_centimes is not None:
    prix_minimum_centimes = int(round(price.prix * 100))
    if custom_amount_centimes < prix_minimum_centimes:
        raise ValueError(_(
            f"Montant libre ({custom_amount_centimes/100:.2f}€) "
            f"inférieur au minimum ({prix_minimum_centimes/100:.2f}€)"
        ))
```

##### b. XSS dans tarif.js

L'overlay utilise `innerHTML` avec des noms de produits non sanitisés.
**Fix** : `textContent` pour les données dynamiques. Changement minimal, pas de modif logique.

#### 5. Accessibilité — 2 ajouts

| Élément | Fichier | Fix |
|---------|---------|-----|
| `#messages` | `hx_messages.html` | `aria-live="assertive"` |
| `#addition-list` | `cotton/addition.html` | `aria-live="polite"` |

#### Ordre d'implémentation

| Étape | Contenu | Impact tests |
|-------|---------|-------------|
| **1. Sécurité** | Validation prix libre serveur + fix XSS textContent | Aucun (ajout de validation) |
| **2. Accessibilité** | aria-live sur #messages et #addition-list | Aucun |
| **3. Extraction CSS** | overlay.css + composants → fichiers static/ | Aucun (classes identiques) |
| **4. Footer Cotton** | Extraire `<c-footer>` des 3 views | Playwright : vérifier data-testid |
| **5. Run tests** | Playwright complet + pytest | Valide que rien ne casse |

**Toutes ces étapes sont sans risque** pour les tests (pas de changement de logique).

#### Ce qui NE change PAS

- views.py, serializers.py, urls.py, modèles
- Le format POST (repid-*, custom-*)
- Les data-testid
- **Tout le JS** (modifications à discuter avec Nicolas)

---

### Refonte : typage par article, pas par point de vente

#### Constat

L'architecture actuelle type le **point de vente** (`PointDeVente.comportement`) pour
déterminer le contenu et le flux. Mais dans le code, les logiques métier sont déjà
pilotées par l'**article** (`Product.methode_caisse` et `categorie_article`) :

| Logique | Pilotée par | Pas par le PV |
|---------|-------------|---------------|
| Identification adhésion avant paiement | `categorie_article == ADHESION` dans le panier | ✅ |
| Garde NFC sur recharges | `methode_caisse in (RE, RC, TM)` | ✅ |
| Création Membership au paiement | `categorie_article == ADHESION` par article | ✅ |
| Séparation vente/adhésion en NFC | `categorie_article == ADHESION` par article | ✅ |

Le `comportement` du PV ne fait que 2 choses concrètes :
1. **KIOSK** → template différent (sera une app Django séparée — supprimé de laboutik)
2. **ADHESION** → charge dynamiquement les Products adhésion (devrait être géré par le M2M)

**Problème** : on ne peut pas créer un PV "Accueil" qui vend des goodies (VT) + recharges (RE)
+ adhésions (AD) + billets (BI). Il faudrait 4 PV séparés.

#### Décision

**`comportement` = mode d'interface, pas type de contenu.**

```
comportement :
  D = Direct (interface POS standard : grille + panier + footer)
  V = Avancé / Advanced (mode commande restaurant — réservé, pas codé tout de suite)
  (ADHESION, CASHLESS et KIOSK supprimés — KIOSK sera une app Django séparée)
```

Le **quoi** (ventes, adhésions, billets, recharges) est déterminé par les articles
dans le M2M `products` + `categories` du PV. Un PV peut contenir tous les types.

#### Règle UX : 1 panier = 1 client

Quand le panier contient des articles qui **nécessitent un client** (recharge, adhésion, billet),
le système demande **UNE SEULE identification**. Ce client est utilisé pour tout :
recharge → sa carte, adhésion → son user, billet → son email.

**Le `elif` mutuellement exclusif actuel** (`if recharge elif adhesion elif normal`) est remplacé
par un flow d'identification unifié basé sur `panier_necessite_client`.

```python
panier_necessite_client = (
    _panier_contient_recharges(articles_panier)   # RE/RC/TM → wallet client
    or panier_a_adhesions                          # AD → Membership(user)
    or panier_a_billets                            # BI → Ticket(user) + email optionnel
)
```

**Flow simplifié** (IMPLÉMENTÉ — session 05) :
```
SI panier_necessite_client = False :
  → flow normal (choix moyen → payer → succès)

SI panier_necessite_client = True :
  → écran identification : "SCANNER CARTE NFC" ou "SAISIR EMAIL/NOM"
  → client identifié
  → écran récapitulatif (article par article + total + boutons paiement)
  → clic bouton paiement (ESPÈCE / CB / CHÈQUE / CASHLESS)
  → paiement atomique
```

**Compromis accepté** : 1 panier = 1 client. Si le caissier veut recharger la carte du fils
et créer une adhésion pour la mère, il faut 2 paniers séparés. Ce cas est extrêmement rare.

**Cas spéciaux** :
- Panier avec SEULEMENT des recharges → scan NFC obligatoire (pas de formulaire email — une recharge nécessite une carte physique)
- Panier avec billets mais SANS adhésion ni recharge → formulaire email optionnel (pas de scan NFC nécessaire si paiement espèces)
- Panier avec adhésion + billets → l'identification faite pour l'adhésion sert aussi pour les billets (même user/email)

**Écran d'identification unifié** (`hx_identifier_client.html` — remplace les 3 flows séparés) :

```
┌──────────────────────────────────────────────────────────┐
│  👤 IDENTIFIER LE CLIENT                                  │
│                                                            │
│  Votre panier nécessite une identification :              │
│  • Recharge 10€ → créditera la carte du client            │
│  • Adhésion annuelle → sera rattachée au client           │
│  • Billet Concert → envoyé par email (optionnel)          │
│                                                            │
│  ┌────────────────────────┐  ┌────────────────────────┐   │
│  │  📱 SCANNER CARTE NFC  │  │  ✉️ SAISIR EMAIL/NOM  │   │
│  └────────────────────────┘  └────────────────────────┘   │
└──────────────────────────────────────────────────────────┘
```

Le texte explicatif s'adapte dynamiquement au contenu du panier.
Le bouton "Saisir email/nom" n'apparaît que si le panier n'a PAS de recharges
(une recharge nécessite une carte physique).

**Écran récapitulatif** (`hx_recapitulatif_client.html`) :

```
┌──────────────────────────────────────────────────────────┐
│  ✅ Marie Dupont — marie@example.com                      │
│  Carte : 52BE6543 │ Solde : 45,00€                       │
│                                                            │
│  Bière × 2                              7,00€             │
│  Recharge 10€ → carte Marie            10,00€             │
│  Adhésion annuelle → Marie             20,00€             │
│  Concert Rock → email marie@...        15,00€             │
│  ─────────────────────────────────────────────            │
│  TOTAL                                 52,00€             │
│                                                            │
│  ☐ Envoyer le billet par email                            │
│                                                            │
│  [ESPÈCE]  [CB]  [CHÈQUE]                                │
└──────────────────────────────────────────────────────────┘
```

#### Ce qui change

##### 1. Suppression de `ADHESION`, `CASHLESS` et `KIOSK` comme comportement

Migration : supprimer les choix `'A'`, `'C'` et `'K'` de `COMPORTEMENT_CHOICES`.
Les PV existants avec `comportement` autre que `'D'` passent à `'D'` (Direct).
Ajout de `AVANCE = 'V'` (mode commande restaurant — réservé, pas codé tout de suite).
KIOSK sera une app Django séparée dans le futur.

##### 2. Les produits adhésion rejoignent le M2M standard

Plus de chargement dynamique conditionnel. Les Products adhésion sont ajoutés au
M2M `products` du PV comme les autres articles (via l'admin ou le management command).

Le code `if pv.comportement == ADHESION: charger dynamiquement...` est supprimé.

##### 3. Le rendu des tuiles dépend de `methode_caisse`

La grille d'articles rend des tuiles **différentes selon le type d'article** :

| `methode_caisse` | Composant tuile | Taille dans le grid |
|------------------|----------------|---------------------|
| VT, RE, RC, TM, CR, VC, FR, FD | `<c-articles>` (carré standard) | 1 colonne |
| AD | `<c-articles>` (carré, badge adhésion) | 1 colonne |
| BI | `<c-billet-tuile>` (paysage, jauge event) | 2 colonnes (`grid-column: span 2`) |

Le CSS Grid gère le mélange via `grid-column: span 2` sur les tuiles BI.

##### 4. Le panier accepte des articles mixtes

Un seul panier peut contenir : T-shirt (VT) + Recharge 10€ (RE) + Adhésion (AD) + Billet (BI).

##### 5. Le flow de paiement s'adapte au contenu du panier

```
Panier mixte → clic VALIDER → moyens_paiement()
  → détecte panier_necessite_client (recharges, adhésions, billets)
  ↓
  SI panier_necessite_client = True :
    → écran identification : "SCANNER CARTE NFC" ou "SAISIR EMAIL/NOM"
    → client identifié
    → écran récapitulatif (montre ce qui sera fait pour chaque article)
    → choix moyen de paiement (espèces, CB, chèque — PAS NFC si recharges)
  SINON :
    → choix moyen de paiement directement (flow normal)
  ↓
  Paiement atomique :
    articles VT/RE/RC/TM/CR/VC → _creer_ligne_article()
    articles AD → _creer_ou_renouveler_adhesion() + LigneArticle
    articles BI → _creer_billets_depuis_panier() + Reservation + Ticket + LigneArticle
```

**L'identification est AVANT le choix de paiement** : plus logique UX — on sait d'abord
pour qui on paie, puis on choisit comment. L'identification est mutualisée : si le client
est identifié par NFC pour l'adhésion, le même user sert pour les billets et recharges.

##### 6. `CASHLESS` et `KIOSK` comme comportement → aussi supprimés

Le mode "cashless uniquement" est géré par les flags du PV :
`accepte_especes=False, accepte_carte_bancaire=False, accepte_cheque=False`.
Pas besoin d'un comportement dédié.

KIOSK sera une app Django séparée dans le futur (pas dans laboutik).
Le template `kiosk.html` (stub vide) et le code conditionnel dans views.py sont supprimés.

**Comportements restants** :
```python
COMPORTEMENT_CHOICES = [
    (DIRECT, _('Direct')),     # Interface POS standard (service direct)
    (AVANCE, _('Advanced')),   # Mode commande restaurant (réservé, pas codé)
]
```

#### Impact sur les phases planifiées

| Phase | Impact |
|-------|--------|
| **Billetterie** | Plus de template séparé `billetterie.html`. Les tuiles BI sont rendues dans la même grille avec `grid-column: span 2`. La sidebar filtre par catégorie normalement. |
| **Phase 2.5 (fait)** | Le wizard identification est déjà per-article. Garder tel quel, juste supprimer le check `comportement == ADHESION` pour le chargement dynamique. |
| **Multi-Tarif UX** | Pas d'impact — le multi-tarif est déjà per-article. |
| **tests Playwright** | Les tests 44-adhesion passent un `comportement=ADHESION` dans les fixtures → adapter pour `comportement=DIRECT` + M2M products. |

#### Migration

1. Ajouter les Products adhésion au M2M du PV "Adhésions" existant (create_test_pos_data)
2. Changer `comportement='A'` → `'D'` pour les PV existants
3. Supprimer les choix `'A'`, `'C'`, `'T'` de `COMPORTEMENT_CHOICES`
4. Supprimer le code `if pv.comportement == ADHESION: ...` dans views.py
5. Adapter les tests

**⚠️ Cette refonte est un prérequis de la Phase Billetterie.** Elle simplifie l'architecture
au lieu de l'ajouter. On la fait DANS le sprint Billetterie, pas en phase séparée.

---

### Phase BILLETTERIE — Articles billet dans la grille POS

#### Vision (mise à jour session 06)

Le PV de type `BILLETTERIE` ('T') construit ses articles depuis les **événements futurs**.
Pas de double typage des articles : le Product n'a pas besoin de `methode_caisse='BI'` pour
apparaître — c'est le type du PV qui détermine le chargement automatique.

Le composant Cotton `<c-billet-tuile>` rend les articles en paysage (2 colonnes, jauge, date).
Les articles du M2M `products` sont chargés en plus (goodies, boissons, etc.).
La sidebar catégories filtre normalement. Le panier accepte tout.

La seule différence : les articles billet déclenchent un formulaire email optionnel avant paiement
(comme les adhésions déclenchent le wizard d'identification).

#### Principe : le type du PV détermine le chargement, pas un flag sur l'article

Même logique que les adhésions : le PV `ADHESION` charge tous les `categorie_article=ADHESION`.
Le PV `BILLETTERIE` construit les articles depuis `Event.objects.filter(published=True, datetime__gte=now)`.
Le PV `CASHLESS` charge toutes les recharges. Le PV `DIRECT` charge uniquement le M2M.

Pas de `methode_caisse='BI'` nécessaire — les Products existants (`categorie_article=BILLET`)
sont automatiquement disponibles quand ils sont liés à un Event futur publié.

#### Ce qui reste identique

- `_creer_billets_depuis_panier()` reste identique
- Vérification atomique de la jauge au paiement
- Impression mockée (console logger)
- Tous les moyens de paiement disponibles (y compris NFC)

#### Ce qui change (vs. ancien plan)

1. **PV type `BILLETTERIE` ('T')** au lieu de `methode_caisse='BI'` sur chaque article
2. **Pas de template `billetterie.html`** — tuiles BI dans `common_user_interface.html`
3. **Le composant `<c-billet-tuile>`** est rendu dans le même grid que les tuiles standard
4. **`_construire_donnees_articles()`** détecte le type du PV pour charger depuis les events
5. **La grille CSS** utilise `grid-column: span 2` pour les tuiles BI (paysage)

#### Rendu mixte dans la grille

```
┌──────────┬────────────────────────────────────────┬───────────────┐
│ SIDEBAR  │ GRILLE (CSS Grid auto-fill)             │  PANIER       │
│          │                                          │               │
│ [Tous]   │  ┌────┐ ┌────┐ ┌────┐ ┌────┐           │               │
│ [Bar]    │  │Bière│ │Coca│ │Eau │ │Café│ ← carrées │               │
│ [Resto]  │  └────┘ └────┘ └────┘ └────┘           │               │
│ [Rechar.]│  ┌────┐ ┌────┐                          │               │
│ [Adhés.] │  │R10€│ │R20€│  ← carrées              │               │
│ [Billet.]│  └────┘ └────┘                          │               │
│          │  ┌────────────────────────────────────┐  │               │
│          │  │ 🎫 Concert Rock — 15 avr.          │  │               │
│          │  │    ████████░░ 42/50 — 15,00€       │  ← 2 colonnes  │
│          │  └────────────────────────────────────┘  │               │
│          │  ┌────────────────────────────────────┐  │               │
│          │  │ 🎫 Soirée Electro — 22 avr.        │  │               │
│          │  │    ████░░░░░░ 12/50 — 10,00€       │  ← 2 colonnes  │
│          │  └────────────────────────────────────┘  │               │
├──────────┴──────────────────────────────────────────┴───────────────┤
│ FOOTER                                                              │
└─────────────────────────────────────────────────────────────────────┘
```

Quand le caissier clique sur la catégorie "Billetterie", seules les tuiles BI s'affichent
(filtre CSS hide/show existant via `cat-{uuid}`). Les tuiles passent en grid 2 colonnes max.

#### Données d'un article billet — implémenté (session 06)

> **OBSOLÈTE** : le code ci-dessous utilisait `methode_caisse='BI'`. La version implémentée
> boucle sur les events futurs quand le PV est de type `BILLETTERIE` ('T').
> Voir `laboutik/views.py` : `_construire_donnees_articles()`, bloc `if est_pv_billetterie`.
> 1 tuile = 1 Price. ID = Price UUID. Jauge = Price.stock si défini, sinon Event.jauge_max.

Le template `articles.html` (ou un nouveau Cotton `billet_tuile.html` inclus conditionnellement)
teste `article.event` pour décider du rendu.

#### Flow de paiement avec billets dans un panier mixte

Identique au plan précédent, mais l'identification est **mutualisée** avec les adhésions :

```
SI panier_a_adhesions ET panier_a_billets :
  → 1 seul wizard identification (pas 2 successifs)
  → le user identifié sert pour les adhésions ET les billets
  → si email fourni : Reservation.to_mail=True pour les billets

SI panier_a_billets seulement (pas d'adhésion) :
  → formulaire email optionnel (plus léger que le wizard adhésion)
  → "ENVOYER LE BILLET" ou "PAYER SANS EMAIL"
```
liés aux événements actuels et futurs. Le caissier voit les événements dans la sidebar gauche,
les tarifs sous forme de tuiles paysage (max 2 par ligne), une jauge de places restantes.
Après paiement, l'impression est proposée et un email optionnel envoie le billet au client.

**Tous les moyens de paiement sont disponibles** (espèces, CB, chèque, NFC cashless).
Le NFC permet d'acheter des billets avec des tokens (monnaie temps, locale, etc.) grâce
au multi-tarif par asset — c'est un cas d'usage clé.

#### Prérequis et nettoyage

Les prototypes précédents ont été supprimés (tests, migrations orphelines, printer.py).
On part de zéro. Il n'y a **aucun code billetterie** dans views.py ni dans les templates.

Fichiers supprimés :
- `laboutik/migrations/0003_add_laboutik_configuration.py` (supprimé)
- `laboutik/migrations/0004_add_printer_billetterie.py` (supprimé)
- `laboutik/printer.py` (supprimé)
- `tests/pytest/test_billetterie_pos.py` (supprimé)
- `tests/playwright/tests/laboutik/46-laboutik-pos-billetterie.spec.ts` (supprimé)
- `laboutik/utils/mockData.py`, `dbJson.py`, `mockDb.json` (supprimés — nettoyage mock Phase 7 anticipé)

#### Principe : Products existants, pas de nouveaux modèles

**On réutilise les Products existants de billetterie** (`categorie_article=BILLET` ou `FREERES`).
Pas de double typage : pas besoin de `methode_caisse='BI'` pour apparaître dans le POS.
C'est le type du PV (`BILLETTERIE`) qui détermine le chargement depuis les events.

#### Backend — implémenté (session 06)

**1. Type PV `BILLETTERIE` ('T')** — migration 0005

**2. `_construire_donnees_articles()`** — quand le PV est BILLETTERIE :
- Charge les events futurs publiés (datetime >= now - 1 jour)
- Pour chaque event → chaque Product publié → chaque Price EUR → 1 article_dict
- ID unique par Price (pas Product) pour éviter les doublons dans le panier
- Jauge sur la tuile : Price.stock si défini, sinon Event.jauge_max
- Couleurs par event (palette cyclique 8 couleurs)
- Events sans produit publiés filtrés
- Les articles M2M du PV (Bière, Eau...) sont chargés en plus

**3. `_construire_donnees_categories()`** — events comme pseudo-catégories :
- Chaque event → dict avec `is_event: True`, date, jauge globale
- UUID de l'event = `id` de la pseudo-catégorie → filtre CSS `cat-{event_uuid}`
- Le JS existant (`articlesDisplayCategory`) fonctionne sans modification

**4. Pas de `_construire_donnees_evenements()` séparé** — la logique est intégrée
directement dans `_construire_donnees_articles()` pour simplifier.

**5. Moyens de paiement — TOUS disponibles (y compris NFC)**

Le NFC est un moyen valide pour acheter des billets (monnaie temps, locale, etc.).
Pas de masquage spécifique à la billetterie.

**6. `PaiementViewSet.payer()` — intercept BILLETTERIE avant les partials espèces**

Avant d'aller vers `hx_confirm_payment.html` (espèces) ou de payer directement (CB/NFC),
si `mode_billetterie=True` dans le state, afficher d'abord `hx_billetterie_email_form.html`.
Ensuite, appeler `_creer_billets_depuis_panier()` au lieu de `_creer_ligne_article()` seul.

**7. `PaiementViewSet._creer_billets_depuis_panier(articles, email, pv, operateur)` — nouveau**

```python
def _creer_billets_depuis_panier(articles, email_client, pv, operateur):
    """
    Crée les objets Reservation + Ticket + LigneArticle pour chaque article billet.
    / Creates Reservation + Ticket + LigneArticle objects for each ticket article.

    LOCALISATION : laboutik/views.py

    Pour chaque article du panier (type BILLET_POS) :
    1. Récupère ou crée l'utilisateur (get_or_create sur email si fourni)
    2. Crée ou récupère Reservation(event, user_commande)
    3. Crée ProductSold + PriceSold (intermédiaires obligatoires pour LigneArticle)
    4. Crée Ticket(reservation, pricesold, status='K', sale_origin='LB')
    5. Crée LigneArticle(pricesold, sale_origin='LB', payment_method=...)
    6. Si email fourni : Reservation.to_mail=True (déclenchera l'envoi par Celery)

    Toute la séquence dans db_transaction.atomic().

    CODES STATUS TICKET (BaseBillet.Ticket) :
    - 'C' = CREATED
    - 'N' = NOT_ACTIV (inactive)
    - 'K' = NOT_SCANNED (valide, non scanné) ← celui qu'on utilise
    - 'S' = SCANNED (valide, scanné)
    - 'R' = CANCELED

    ⚠️ Ne PAS confondre avec les anciens codes 'NS'/'SC' — les vrais codes sont des chars uniques.

    DÉPENDANCES MODÈLES :
    - BaseBillet.Reservation (user_commande FK, event FK, to_mail BooleanField)
    - BaseBillet.Ticket (status='K'=NOT_SCANNED)
    - BaseBillet.ProductSold (product FK, event FK, categorie_article)
    - BaseBillet.PriceSold (productsold FK, price FK, prix DecimalField)
    - BaseBillet.LigneArticle (pricesold FK, sale_origin, payment_method)
    """
```

**8. Jauge places restantes**

**Phase 1 (maintenant)** : HTMX polling toutes les 30s via partial `hx_jauge_event.html`.
Simple, sans dépendance WebSocket.

**Phase WebSocket (sprint suivant)** : remplacer le polling par un broadcast WebSocket
après chaque vente de billet. Voir section "Phase WebSocket" ci-dessous.

```python
# CaisseViewSet
@action(detail=False, methods=['GET'], url_path='jauge_event')
def jauge_event(self, request):
    """
    Retourne le partial HTML de jauge pour un événement.
    / Returns the gauge HTML partial for an event.

    Phase 1 : polling HTMX toutes les 30s.
    Phase WebSocket : sera déclenché par signal post-vente (remplacera le polling).
    """
    event_uuid = request.GET.get('event_uuid')
    # Calcule places_restantes, pourcentage, complet → render hx_jauge_event.html
```

**9. Impression — mock pour l'instant**

L'impression de billets est prévue mais **le module d'impression sera planifié après
le sprint WebSocket**. En attendant, une fonction stub :

```python
def imprimer_billet(ticket, point_de_vente):
    """
    Stub d'impression — sera remplacé par le vrai module d'impression (post-WebSocket).
    / Print stub — will be replaced by the real print module (post-WebSocket).

    LOCALISATION : laboutik/views.py (temporaire, déplacé dans laboutik/printer.py plus tard)
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.info(
        f"[IMPRESSION MOCK] Billet {ticket.uuid} — "
        f"Event: {ticket.reservation.event.name} — "
        f"PV: {point_de_vente.name}"
    )
```

Le vrai module d'impression (Epson TM20-III, Sunmi intégré, Sunmi Cloud) sera créé
dans une phase dédiée avec son propre modèle `Printer` + `LaboutikConfiguration` enrichi.

**10. Vérification atomique de la jauge au paiement**

Risque : 2 caissiers vendent le dernier billet simultanément → dépassement de jauge.

**Phase 1 (maintenant)** : vérification simple dans `_creer_billets_depuis_panier()` :
```python
with db_transaction.atomic():
    # Re-compter les tickets valides au moment du paiement
    # / Re-count valid tickets at payment time
    places_vendues = Ticket.objects.filter(
        reservation__event=event,
        status__in=[Ticket.NOT_SCANNED, Ticket.SCANNED],
    ).count()
    if event.jauge_max and (places_vendues + nb_billets_panier) > event.jauge_max:
        raise ValueError(_("Plus de places disponibles pour cet événement"))
    # ... créer les Tickets
```

**Phase WebSocket (sprint suivant)** : le broadcast post-vente met à jour la jauge
sur toutes les caisses en temps réel. Réduit fortement le risque de double-vente car
les caissiers voient l'état réel quasi-instantanément (< 1s vs 30s de polling).
Le verrou atomique reste obligatoire comme filet de sécurité.

#### Design UI — templates séparés (Cotton + partials HTMX)

**Principe** : minimum de JS. La sidebar filtre via HTMX (pas via JS pur).
Les tuiles sont des composants Cotton réutilisables. Les jauges sont des partials HTMX.

##### Layout général (dans `common_user_interface.html` — pas de template séparé)

```
┌──────────────────────────────────────────────────────────────────────┐
│  HEADER (c-header — identique aux autres vues)                       │
├──────────────┬───────────────────────────────────────┬───────────────┤
│  SIDEBAR     │  GRILLE (CSS Grid auto-fill)           │  ADDITION     │
│  (c-categor.)│                                        │  (panier)     │
│              │  ┌────┐ ┌────┐                         │               │
│  [Tous]      │  │Bière│ │Eau │ ← carrées (M2M)       │               │
│  [Bar]       │  └────┘ └────┘                         │               │
│  ──────      │  ┌────────────────────────────────────┐│               │
│  Concert Rock│  │ 🎫 Concert Rock — 15 avr.          ││               │
│  15 avr.     │  │    ████████░░ 8/50 — 15,00€        │← 2 colonnes   │
│  ████░░ 8/50 │  │    (Plein tarif)                   ││               │
│              │  └────────────────────────────────────┘│               │
│  Soirée Elec.│  ┌────────────────────────────────────┐│               │
│  22 avr.     │  │ 🎫 Concert Rock — 15 avr.          ││               │
│  ████░░ 4/50 │  │    ████████░░ 8/50 — 8,00€         │← 2 colonnes   │
│              │  │    (Tarif réduit)                   ││               │
│              │  └────────────────────────────────────┘│               │
│              │  ┌────────────────────────────────────┐│               │
│              │  │ 🎫 Soirée Electro — 22 avr.        ││               │
│              │  │    ████░░░░░░ 4/50 — 10,00€         │← 2 colonnes   │
│              │  └────────────────────────────────────┘│               │
├──────────────┴────────────────────────────────────────┴───────────────┤
│  FOOTER (c-footer — identique : RESET / CHECK CARTE / VALIDER)       │
└──────────────────────────────────────────────────────────────────────┘
```

**Décision sidebar (session 06)** : les events sont des **pseudo-catégories** dans `<c-categories>`
existant. Pas de sidebar dédiée, pas de template séparé, pas d'action HTMX supplémentaire.
Le filtre CSS existant (`cat-{uuid}`) fonctionne tel quel : chaque tuile billet porte `cat-{event_uuid}`.
Les catégories classiques (Bar, etc.) coexistent naturellement avec les events.
Le caissier peut filtrer "Bar" (articles classiques) ou "Concert Rock" (billets de cet event).

Les events apparaissent dans la sidebar avec date + mini-jauge, distingués visuellement par un
flag `is_event: True` dans le dict catégorie.

**Responsive** :
- Desktop (> 1022px) : sidebar catégories/events + grille + addition
- Tablette (599-1022px) : sidebar + grille (pas d'addition séparée)
- Mobile (< 599px) : grille pleine largeur + sidebar masquée

##### Architecture des templates (mise à jour session 06)

```
laboutik/templates/
├── cotton/
│   ├── billet_tuile.html          ← FAIT : composant Cotton tuile paysage (include)
│   ├── articles.html              ← MODIFIÉ : condition methode_caisse BI → billet_tuile
│   └── categories.html            ← À MODIFIER : ajouter rendu event (date + jauge) si is_event
├── laboutik/
│   └── partial/
│       └── hx_billetterie_email_form.html ← À CRÉER (session 07) : formulaire email avant paiement
```

Pas de `billetterie.html`, pas de `billet_sidebar_item.html`, pas de `hx_billetterie_grille.html`.
L'interface est `common_user_interface.html` avec les mêmes composants Cotton.

##### Composant Cotton : tuile tarif (`cotton/billet_tuile.html`)

```html
<!--
TUILE TARIF BILLETTERIE — composant Cotton réutilisable
1 tuile = 1 Price (tarif) d'un événement.
/ Ticketing rate tile — reusable Cotton component.
1 tile = 1 Price (rate) of an event.

LOCALISATION : laboutik/templates/cotton/billet_tuile.html

ATTRIBUTS :
  product_uuid, price_uuid, event_uuid — identifiants pour le panier et la jauge
  nom_tarif, nom_event — textes affichés
  prix_affichage — prix formaté côté Python ("15,00")
  free_price — bool, affiche "? €" si True
  url_image — URL de l'image du produit (nullable)
  couleur_backgr, couleur_texte — hex CSS
  icone, icone_type — icône FA ou MS
  disabled — bool, tuile grisée si complet
  currency_symbol — "€"
-->
<div class="billet-tuile{% if disabled %} billet-tuile-complet{% endif %}"
     data-uuid="{{ product_uuid }}"
     data-price-uuid="{{ price_uuid }}"
     data-event-uuid="{{ event_uuid }}"
     data-name="{{ nom_tarif }} — {{ nom_event }}"
     data-price="{{ prix_centimes }}"
     data-currency="{{ currency_symbol }}"
     data-group="billetterie"
     data-multi-tarif="false"
     {% if disabled %}data-disable="true"{% endif %}
     data-testid="billetterie-tuile-{{ price_uuid }}"
     style="background-color: {{ couleur_backgr }};"
     aria-label="{{ nom_tarif }} — {{ nom_event }}">

  {# Zone gauche : image ou icône de l'événement #}
  <div class="billet-tuile-media" aria-hidden="true">
    {% if url_image %}
    <img src="{{ url_image }}" alt="" class="billet-tuile-img" loading="lazy"
         onerror="this.style.display='none'">
    {% elif icone_type == "fa" %}
    <i class="fas {{ icone }}" style="color: {{ couleur_texte }};"></i>
    {% else %}
    <span class="material-symbols-outlined"
          style="color: {{ couleur_texte }};">{{ icone }}</span>
    {% endif %}
  </div>

  {# Zone droite : infos texte + slot jauge + prix #}
  <div class="billet-tuile-info">
    <div class="billet-tuile-nom-tarif"
         style="color: {{ couleur_texte }};">{{ nom_tarif }}</div>
    <div class="billet-tuile-nom-event"
         style="color: {{ couleur_texte }}; opacity: 0.7;">{{ nom_event }}</div>

    {# Slot pour la jauge — injecté par le parent #}
    {{ slot }}

    {# Prix en bas à droite #}
    <div class="billet-tuile-prix" style="color: {{ couleur_texte }};">
      {% if free_price %}
      <span aria-label="{% translate 'prix libre' %}">? {{ currency_symbol }}</span>
      {% else %}
      <span>{{ prix_affichage }} {{ currency_symbol }}</span>
      {% endif %}
    </div>
  </div>

  {# Badge quantité (masqué tant que qty=0) #}
  <div class="billet-tuile-badge">
    <span id="article-quantity-number-{{ product_uuid }}--{{ price_uuid }}"
          class="badge" aria-hidden="true">0</span>
  </div>

  {# Couches touch + lock (même pattern que articles.html) #}
  <div class="article-touch"></div>
  <div class="article-lock-layer{% if disabled %} article-lock-layer-complet{% endif %}"></div>
</div>
```

##### Partial HTMX : grille de tuiles (`hx_billetterie_grille.html`)

Rechargé quand on clique sur un événement dans la sidebar (filtre côté serveur, pas JS).

```html
<!--
GRILLE TUILES BILLETTERIE — partial HTMX rechargé par le filtre sidebar
/ Ticketing tiles grid — HTMX partial reloaded by sidebar filter

LOCALISATION : laboutik/templates/laboutik/partial/hx_billetterie_grille.html

Rechargé via :
  hx-get="{% url 'laboutik-caisse-grille_billetterie' %}?event_uuid=..."
  hx-target="#billetterie-grid"
  hx-swap="innerHTML"

Si event_uuid='all' → affiche tous les événements.
Si event_uuid=<uuid> → affiche uniquement les tuiles de cet événement.
-->
<div id="billetterie-grid" data-testid="billetterie-grid">
  {% for event in evenements %}
    {% for tuile in event.tuiles %}
      <c-billet-tuile
        product_uuid="{{ tuile.product_uuid }}"
        price_uuid="{{ tuile.price_uuid }}"
        event_uuid="{{ tuile.event_uuid }}"
        nom_tarif="{{ tuile.nom_tarif }}"
        nom_event="{{ tuile.nom_event }}"
        prix_centimes="{{ tuile.prix_centimes }}"
        prix_affichage="{{ tuile.prix_affichage }}"
        free_price="{{ tuile.free_price }}"
        asset_uuid="{{ tuile.asset_uuid|default:'' }}"
        url_image="{{ tuile.url_image|default:'' }}"
        couleur_backgr="{{ tuile.couleur_backgr }}"
        couleur_texte="{{ tuile.couleur_texte }}"
        icone="{{ tuile.icone }}"
        icone_type="{{ tuile.icone_type }}"
        disabled="{{ tuile.disabled }}"
        currency_symbol="{{ currency_data.symbol }}">

        {# Slot : jauge HTMX intégrée dans chaque tuile #}
        {% include "laboutik/partial/hx_jauge_event.html" with event=event %}
      </c-billet-tuile>
    {% endfor %}
  {% endfor %}
</div>
```

##### Sidebar : events comme pseudo-catégories (décision session 06, option B)

Les events sont des **pseudo-catégories** dans `<c-categories>` existant. Pas de sidebar dédiée,
pas de template séparé, pas d'action HTMX supplémentaire.

**Pourquoi** : le filtre CSS existant (`cat-{uuid}`) fonctionne déjà. Chaque tuile billet porte
`cat-{event_uuid}`. Le JS categories.js masque/affiche les tuiles. Le filtre est instantané
(CSS côté client, pas de round-trip serveur). Les catégories classiques (Bar, etc.) et les events
coexistent naturellement — le caissier peut filtrer "Bar" ou "Concert Rock".

**Implémentation** :
1. `_construire_donnees_categories()` : quand le PV est `BILLETTERIE`, ajouter les events futurs
   comme pseudo-catégories avec `is_event: True`, `date`, `jauge_max`, `places_vendues`, `pourcentage`
2. `cotton/categories.html` : `{% if cat.is_event %}` → afficher date + mini-jauge en plus du nom
3. Chaque tuile billet porte `cat-{event_uuid}` pour le filtre CSS

Pas de `grille_billetterie` action, pas de `hx_billetterie_grille.html`, pas de `billet_sidebar_item.html`.

##### Jauge statique (décision session 06)

Pas de polling HTMX 30s. La jauge est calculée au chargement (`_construire_donnees_articles()`).
Sera remplacée par WebSocket push en Phase 4 (voir INDEX.md).
Pas de `hx_jauge_event.html`.

##### Formulaire email (`hx_billetterie_email_form.html`)

Affiché après le choix du moyen de paiement (avant de déclencher le paiement effectif).

```
┌──────────────────────────────────────────────────────────────┐
│                       ✉ Envoyer le billet                    │
│                                                              │
│   ┌──────────────────────────────────────────────────┐       │
│   │  Email du client (optionnel)                     │       │
│   └──────────────────────────────────────────────────┘       │
│                                                              │
│   ┌──────────────────────────────────────────────────────┐   │
│   │  ✉  CONFIRMER ET ENVOYER                             │   │  ← vert
│   └──────────────────────────────────────────────────────┘   │
│   ┌──────────────────────────────────────────────────────┐   │
│   │  🎫  PAYER SANS EMAIL                                │   │  ← bleu
│   └──────────────────────────────────────────────────────┘   │
│                          [RETOUR]                            │
└──────────────────────────────────────────────────────────────┘
```

- Input email : label flottant, `inputmode="email"`, `autocomplete="email"`, 56px hauteur
- Bouton CONFIRMER ET ENVOYER : vert (`--success`), icône fa-envelope
- Bouton PAYER SANS EMAIL : bleu (`--bleu05`), icône fa-ticket-alt
- `data-testid` : `billetterie-email-form`, `billetterie-input-email`, `billetterie-btn-avec-email`, `billetterie-btn-sans-email`
- Les 2 boutons font un `hx-post` vers `payer()` avec ou sans le champ email

##### CSS commun billetterie

```css
/*
 * GRILLE BILLETTERIE — max 2 tuiles par ligne (format carte paysage)
 * / Ticketing grid — max 2 tiles per row (landscape card format).
 */
#billetterie-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  padding: 12px;
  align-content: start;
  overflow-y: auto;
  scrollbar-width: none;
}

@media (max-width: 599px) {
  #billetterie-grid {
    grid-template-columns: 1fr;
  }
}

/* --- Tuile tarif (rectangle paysage, 120px hauteur fixe) --- */

.billet-tuile {
  position: relative;
  width: 100%;
  height: 120px;
  display: flex;
  flex-direction: row;
  align-items: stretch;
  border-radius: 14px;
  overflow: hidden;
  cursor: pointer;
  transition: transform 100ms ease-in-out;
  font-family: "Luciole-regular", sans-serif;
}

.billet-tuile:active { transform: scale(0.97); }
.billet-tuile-complet { opacity: 0.45; cursor: not-allowed; }

.billet-tuile-media {
  flex-shrink: 0;
  width: 120px;
  height: 120px;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: rgba(0, 0, 0, 0.25);
  font-size: 3rem;
}

.billet-tuile-img { width: 100%; height: 100%; object-fit: cover; }

.billet-tuile-info {
  flex: 1;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  min-width: 0;
}

.billet-tuile-nom-tarif {
  font-size: 1.1rem; font-weight: bold;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

.billet-tuile-nom-event {
  font-size: 0.85rem;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  margin-top: 2px;
}

.billet-tuile-prix {
  font-size: 1.3rem; font-weight: bold;
  font-variant-numeric: tabular-nums;
  text-align: right; margin-top: 4px;
}

.billet-tuile-badge { position: absolute; top: 8px; right: 8px; z-index: 2; }

/* --- Jauge --- */

.billet-jauge-bar-container {
  height: 5px; width: 100%;
  background-color: rgba(255, 255, 255, 0.15);
  border-radius: 3px; overflow: hidden; margin-top: 4px;
}

.billet-jauge-bar {
  height: 100%; background-color: var(--vert01, #00e676);
  border-radius: 3px; transition: width 600ms ease;
}

.billet-jauge-bar-complet { background-color: var(--rouge01, #ff5252); }

.billet-jauge-label {
  font-size: 0.78rem; font-variant-numeric: tabular-nums;
  opacity: 0.75; display: block; margin-top: 3px;
}

.billet-jauge-label-complet {
  color: var(--rouge01, #ff5252); opacity: 1; font-weight: bold;
}

/* --- Sidebar événements --- */

#billetterie-sidebar {
  width: var(--cat-width);
  height: 100%; overflow-y: auto; scrollbar-width: none;
  padding: 8px 6px; display: flex; flex-direction: column; gap: 6px;
  background-color: var(--bleu11); flex-shrink: 0;
}

.billet-sidebar-item {
  display: flex; flex-direction: column; align-items: flex-start; gap: 2px;
  width: 100%; padding: 10px; border: none; border-radius: 10px;
  background-color: transparent; color: var(--blanc01); cursor: pointer;
  text-align: left; font-family: "Luciole-regular", sans-serif;
  transition: background-color 150ms ease; min-height: 48px;
}

.billet-sidebar-item:active,
.billet-sidebar-active {
  background-color: rgba(255, 255, 255, 0.1);
  border-left: 3px solid var(--vert01);
}

.billet-sidebar-nom {
  font-size: 0.9rem; font-weight: bold;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; width: 100%;
}

.billet-sidebar-date { font-size: 0.75rem; opacity: 0.6; }

.billet-sidebar-jauge {
  width: 100%; height: 4px;
  background-color: rgba(255, 255, 255, 0.15);
  border-radius: 2px; margin-top: 4px; overflow: hidden;
}

.billet-sidebar-jauge-bar {
  height: 100%; background-color: var(--vert01);
  border-radius: 2px; transition: width 300ms ease;
}

.billet-sidebar-places {
  font-size: 0.72rem; opacity: 0.7; font-variant-numeric: tabular-nums;
}

.billet-sidebar-complet { color: var(--rouge01); opacity: 1; }

@media (max-width: 599px) {
  #billetterie-sidebar { display: none; }
}
```

#### Fichiers à créer / modifier

| Fichier | Action | Contenu |
|---------|--------|---------|
| `laboutik/models.py` | Modifier | Migration refonte typage (suppr. ADHESION/CASHLESS/KIOSK, garder DIRECT + AVANCE 'V') |
| `laboutik/views.py` | Modifier | dispatch `point_de_vente()`, `_construire_donnees_evenements()`, `jauge_event()`, `grille_billetterie()`, `_creer_billets_depuis_panier()`, `imprimer_billet()` stub, modif `payer()` |
| `laboutik/templates/cotton/billet_tuile.html` | Créer | Composant Cotton tuile tarif |
| `laboutik/templates/cotton/billet_sidebar_item.html` | Créer | Composant Cotton item sidebar |
| `laboutik/templates/cotton/billet_tuile.html` | Créer | Composant Cotton tuile paysage (2 colonnes) |
| `laboutik/templates/laboutik/partial/hx_jauge_event.html` | Créer | Partial jauge HTMX |
| `laboutik/templates/laboutik/partial/hx_billetterie_grille.html` | Créer | Partial grille tuiles |
| `laboutik/templates/laboutik/partial/hx_billetterie_email_form.html` | Créer | Formulaire email |
| `laboutik/management/commands/create_test_pos_data.py` | Modifier | Ajouter PV BILLETTERIE + `methode_caisse='BI'` sur produits billet + event futur |
| `tests/pytest/test_billetterie_pos.py` | Créer | Tests : `_construire_donnees_evenements()`, `_creer_billets_depuis_panier()`, jauge atomique |
| `tests/playwright/tests/laboutik/46-laboutik-pos-billetterie.spec.ts` | Créer | Tests E2E : 7+ scénarios |

#### Ordre d'implémentation (mis à jour session 06)

1. ✅ **Types PV restaurés** : ADHESION, CASHLESS, BILLETTERIE (migration 0005)
2. ✅ **Tuiles billet** : composant Cotton, CSS responsive, couleurs par event
3. ✅ **Sidebar events** : pseudo-catégories dans `<c-categories>`, filtre CSS
4. ✅ **Chargement depuis events** : `_construire_donnees_articles()` pour PV BILLETTERIE
5. ⏳ **Paiement billet** (session 07) : `panier_a_billets`, `_creer_billets_depuis_panier()`, jauge atomique
6. ⏳ **Tests** (session 07) : pytest + E2E

#### Flux de vente complet

```
1. Scan carte primaire → point_de_vente (PV type BILLETTERIE)
2. Interface common_user_interface.html chargée
   - Sidebar : catégories classiques (Bar) + events comme pseudo-catégories (date + jauge)
   - Grille : articles M2M (Bière, Eau) en carrés + tuiles billet en paysage (2 col desktop, 1 col mobile)
   - 1 tuile = 1 Price, ID = Price UUID. Jauge statique (WebSocket phase 4)

3. Clic tuile → articles.js:addArticle(price_uuid, prix, nom, €) → addition (panier)
   (même système que le POS standard — articles.js réutilisé tel quel)

4. Clic VALIDER → moyens_paiement()
   → panier_a_billets détecté → identification client (email optionnel)
   → affiche tous les moyens de paiement (CASHLESS + ESPÈCE + CB + CHÈQUE)

5. Clic moyen de paiement → payer() détecte mode BILLETTERIE
   → render hx_billetterie_email_form.html

6a. CONFIRMER ET ENVOYER (avec email) :
   → hx-post vers payer() avec email_billetterie rempli
   → _creer_billets_depuis_panier() :
       vérification atomique jauge (count + compare dans atomic())
       get_or_create TibilletUser(email)
       Reservation(event, user_commande, to_mail=True)
       ProductSold + PriceSold
       Ticket(status='K', sale_origin='LB')
       LigneArticle(pricesold, sale_origin='LB', payment_method=CA/CC/CH/NFC)
   → Celery: envoyer_billet_email(reservation.uuid)
   → imprimer_billet() (mock console)
   → hx_return_payment_success.html

6b. PAYER SANS EMAIL :
   → hx-post vers payer() sans email_billetterie
   → idem mais user_commande=user_anonyme_pos, to_mail=False

7. Impression (mockée — console logger) :
   → Vrai module d'impression planifié après le sprint WebSocket
```

#### Points d'attention

- **PriceSold + ProductSold** : intermédiaires obligatoires pour LigneArticle. Lire ces modèles dans `BaseBillet/models.py` AVANT de coder `_creer_billets_depuis_panier()`.
- **Atomicité** : `db_transaction.atomic()` couvre vérification jauge + Reservation + Ticket + LigneArticle.
- **Jauge vs clôture** : la jauge utilise `event.valid_tickets_count()` (Ticket status `'K'` ou `'S'`), pas les `LigneArticle`. Cohérent avec le reste de BaseBillet.
- **Codes Ticket** : `'K'` = NOT_SCANNED, `'S'` = SCANNED, `'R'` = CANCELED. Chars uniques, pas de codes multi-lettres.
- **Pas de template filters custom** : tous les pourcentages et prix sont calculés côté Python dans `_construire_donnees_evenements()`.
- **NFC autorisé** : contrairement à l'ancienne version du plan, le NFC est un moyen de paiement valide en billetterie (multi-asset : monnaie temps, locale, etc.).
- **Pas de nouveaux Products** : on enrichit les Products existants (`categorie_article=BILLET`) avec `methode_caisse='BI'` via l'admin.
- **Impression mockée** : `logger.info()` pour l'instant. Module d'impression réel après le sprint WebSocket.

---

### Phase WebSocket — Push serveur temps réel via HTMX 2

#### Vision

Envoyer des **fragments de template HTML** du serveur vers le navigateur via WebSocket.
Pas de JSON, pas de framework JS — le serveur rend un template Django et l'envoie tel quel.
HTMX 2 reçoit le HTML et le swap dans le DOM grâce à `hx-swap-oob` et les `id` des éléments.

**C'est la même logique que les partials HTMX classiques, mais en push au lieu de poll.**

Cas d'usage immédiats :
1. **Jauge billetterie** : broadcast après chaque vente de billet → toutes les caisses
2. **Commandes restaurant** : notification cuisine → salle
3. **Impression Sunmi intégrée** : envoi du job d'impression via WebSocket
4. **Test de connexion** : animation au chargement de la caisse (preuve que ça marche)

#### Principe technique : HTMX 2 WebSocket Extension

**Extension** : `ws` (fournie par HTMX 2, fichier séparé `ext/ws.js`)
**Doc** : https://v2-0v2-0.htmx.org/extensions/web-sockets/

**Côté client** :
```html
<!-- Connexion WebSocket sur l'interface POS -->
<div hx-ext="ws" ws-connect="/ws/laboutik/{{ pv_uuid }}/">

  <!-- Zone qui sera mise à jour par le serveur -->
  <div id="billet-jauge-{{ event_uuid }}">
    ... contenu initial rendu côté serveur ...
  </div>

  <!-- Zone de notification (append) -->
  <div id="ws-notifications"></div>

</div>
```

**Côté serveur** (le consumer envoie du HTML brut) :
```python
# Le serveur rend un template Django et l'envoie tel quel
# / The server renders a Django template and sends it as-is
html = render_to_string("laboutik/partial/hx_jauge_event.html", context)

# Pour cibler un élément précis, on enveloppe avec hx-swap-oob
# / To target a specific element, wrap with hx-swap-oob
await self.send(text_data=f'<div id="billet-jauge-{event_uuid}" hx-swap-oob="true">{html}</div>')
```

**Comment ça marche** :
1. Le serveur envoie du HTML brut via WebSocket
2. HTMX parse le HTML reçu
3. Si un élément a un `id` qui existe dans le DOM → il est swappé (remplacé)
4. Si `hx-swap-oob="beforeend"` → le contenu est ajouté (append)
5. Pas de JS custom côté client — HTMX gère tout

**Événements HTMX disponibles** :
- `htmx:wsOpen` — connexion établie
- `htmx:wsClose` — connexion fermée
- `htmx:wsError` — erreur
- `htmx:wsBeforeMessage` — avant swap (annulable)
- `htmx:wsAfterMessage` — après swap
- Reconnexion automatique avec backoff exponentiel + jitter

#### Infrastructure existante (état actuel)

| Composant | État | Action requise |
|-----------|------|----------------|
| `daphne` dans SHARED_APPS | ✅ Installé (ligne 119 settings.py) | Aucune |
| `channels` dans pyproject.toml | ✅ `channels = {extras = ["daphne"], version = "^4"}` | Aucune |
| `channels-redis` | ✅ `channels-redis = "^4"` | Aucune |
| `ASGI_APPLICATION` | ✅ `"TiBillet.asgi.application"` | Aucune |
| `CHANNEL_LAYERS` | ✅ Redis backend sur `redis:6379` | Aucune |
| `TiBillet/asgi.py` | ✅ `ProtocolTypeRouter` HTTP + WebSocket | Modifier routing |
| Nginx upgrade headers | ✅ `proxy_set_header Upgrade $http_upgrade` | Aucune |
| `'channels'` dans INSTALLED_APPS | ❌ Commenté (ligne 144) | **Décommenter** |
| `wsocket/` app | ⚠️ POC chat — à remplacer | **Réécrire** |
| HTMX 2.0.6 | ✅ `laboutik/static/js/htmx@2.0.6.min.js` | Aucune |
| Extension `ws.js` | ❌ Pas incluse | **Télécharger** |
| `htmx@2.0.6.min.js` | ✅ Chargé dans `laboutik/base.html` (ligne 80) | Aucune |

**Constat** : 90% de l'infrastructure est déjà en place. Il manque principalement
le consumer, l'extension HTMX ws, et la logique de broadcast.

#### Stack Dev vs Prod

##### Dev (conteneur `lespass_django`)

Daphne remplace `runserver_plus`. Quand `daphne` est dans `INSTALLED_APPS`,
la commande `runserver` est **automatiquement remplacée** par la version ASGI de Daphne.
Donc `manage.py runserver` supporte déjà HTTP + WebSocket nativement.

```bash
# Lancement en dev (depuis Claude Code, run_in_background=true)
docker exec lespass_django poetry run python /DjangoFiles/manage.py runserver 0.0.0.0:8002

# Daphne est dans INSTALLED_APPS → runserver utilise automatiquement ASGI
# → HTTP + WebSocket sur le même port 8002
# → Pas besoin de lancer daphne séparément
```

**⚠️ Important** : `runserver_plus` (Werkzeug) ne supporte PAS ASGI.
Utiliser `runserver` standard (qui est remplacé par Daphne).

##### Prod (conteneur `lespass_django` + Nginx + Traefik)

**Architecture cible** : Daphne seul derrière Nginx (pas besoin de Gunicorn séparé).

Daphne gère HTTP + WebSocket sur le même port. Nginx proxy tout vers Daphne.
L'overhead HTTP de Daphne vs Gunicorn est négligeable pour notre charge (~100 req/s max).

Si plus tard la charge HTTP justifie un split :
- Nginx route `/ws/` → Daphne (WebSocket)
- Nginx route `/` → Gunicorn (HTTP)

Mais pour l'instant, Daphne seul simplifie le déploiement.

```
┌──────────────────────────────────────────────────────────┐
│ Traefik (TLS termination, routing par subdomain)         │
└────────────────────┬─────────────────────────────────────┘
                     │ :80
┌────────────────────▼─────────────────────────────────────┐
│ Nginx (lespass_nginx)                                     │
│                                                           │
│ proxy_pass http://lespass_django:8002;                     │
│ proxy_http_version 1.1;                                   │
│ proxy_set_header Upgrade $http_upgrade;      ← déjà fait  │
│ proxy_set_header Connection "upgrade";       ← déjà fait  │
└────────────────────┬─────────────────────────────────────┘
                     │ :8002
┌────────────────────▼─────────────────────────────────────┐
│ Daphne (ASGI)                                             │
│                                                           │
│ HTTP requests  → Django views (comme avant)               │
│ WS connections → ProtocolTypeRouter → LaboutikConsumer    │
│                                                           │
│ Commande prod :                                           │
│ daphne TiBillet.asgi:application -b 0.0.0.0 -p 8002      │
│        --proxy-headers --access-log /dev/stdout           │
└──────────────────────────────────────────────────────────┘
         │
    ┌────▼────┐
    │  Redis  │  ← channel layer (groupes WebSocket)
    └─────────┘
```

**Fichier de démarrage prod** (`start_prod.sh` ou dans docker-compose) :
```bash
# Migration + collectstatic + Daphne
poetry run python manage.py migrate_schemas --executor=multiprocessing
poetry run python manage.py collectstatic --noinput
poetry run daphne TiBillet.asgi:application \
    --bind 0.0.0.0 \
    --port 8002 \
    --proxy-headers \
    --access-log /dev/stdout \
    --verbosity 1
```

#### Test de connexion : animation au chargement de la caisse

Pour prouver que le WebSocket fonctionne, on ajoute un test visuel simple :
à la connexion WS, le serveur envoie un fragment HTML qui affiche une micro-animation
(un badge "connecté" vert qui apparaît puis disparaît après 2s).

##### Consumer : envoi du fragment HTML au connect

```python
# wsocket/consumers.py
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


class LaboutikConsumer(AsyncWebsocketConsumer):
    """
    Consumer WebSocket pour l'interface de caisse LaBoutik.
    / WebSocket consumer for the LaBoutik POS interface.

    LOCALISATION : wsocket/consumers.py

    Groupes :
    - laboutik-pv-{pv_uuid} : toutes les caisses ouvertes sur ce point de vente
    - laboutik-tenant-{tenant_pk} : toutes les caisses du tenant (notifications globales)

    Le serveur envoie du HTML brut. HTMX 2 (extension ws) parse et swap
    les fragments via id + hx-swap-oob.
    / Server sends raw HTML. HTMX 2 (ws extension) parses and swaps
    fragments via id + hx-swap-oob.
    """

    async def connect(self):
        # Extraire le PV UUID depuis l'URL
        # / Extract PV UUID from URL
        self.pv_uuid = self.scope["url_route"]["kwargs"]["pv_uuid"]

        # Nom du groupe pour ce point de vente
        # / Group name for this point of sale
        self.pv_group_name = f"laboutik-pv-{self.pv_uuid}"

        # Rejoindre le groupe du point de vente
        # / Join the point of sale group
        await self.channel_layer.group_add(
            self.pv_group_name, self.channel_name
        )

        await self.accept()

        # Envoyer le fragment HTML "connecté" au client
        # / Send the "connected" HTML fragment to client
        logger.info(f"[WS] Caisse connectée au PV {self.pv_uuid}")
        html_bienvenue = await sync_to_async(render_to_string)(
            "laboutik/partial/hx_ws_connected.html",
            {"pv_uuid": self.pv_uuid},
        )
        await self.send(text_data=html_bienvenue)

    async def disconnect(self, close_code):
        # Quitter le groupe
        # / Leave the group
        await self.channel_layer.group_discard(
            self.pv_group_name, self.channel_name
        )
        logger.info(f"[WS] Caisse déconnectée du PV {self.pv_uuid}")

    async def receive(self, text_data):
        # Pour l'instant, le client n'envoie rien (server-push uniquement)
        # / For now, client sends nothing (server-push only)
        pass

    # --- Handlers de groupe (appelés via channel_layer.group_send) ---

    async def jauge_update(self, event):
        """
        Reçoit un update de jauge depuis le groupe et le forward au client.
        / Receives a gauge update from the group and forwards to client.

        Appelé par : channel_layer.group_send(group, {"type": "jauge.update", "html": ...})
        """
        await self.send(text_data=event["html"])

    async def notification(self, event):
        """
        Reçoit une notification et l'ajoute au DOM du client.
        / Receives a notification and appends to client DOM.

        Appelé par : channel_layer.group_send(group, {"type": "notification", "html": ...})
        """
        await self.send(text_data=event["html"])
```

##### Template test : badge "connecté" (`hx_ws_connected.html`)

```html
<!--
BADGE CONNEXION WEBSOCKET — envoyé au connect, disparaît après 2s
/ WebSocket connection badge — sent on connect, fades after 2s

LOCALISATION : laboutik/templates/laboutik/partial/hx_ws_connected.html

Envoyé par : LaboutikConsumer.connect()
Cible : #ws-status (doit exister dans common_user_interface.html / billetterie.html)
Stratégie : hx-swap-oob="innerHTML" → remplace le contenu de #ws-status
-->
<div id="ws-status" hx-swap-oob="innerHTML">
  <div class="ws-connected-badge" data-testid="ws-connected-badge"
       aria-live="polite" role="status">
    <i class="fas fa-wifi" aria-hidden="true"></i>
    {% translate "Connecté" %}
  </div>
</div>

<style>
  .ws-connected-badge {
    position: fixed;
    top: 12px;
    right: 12px;
    z-index: 9999;
    background-color: var(--vert01, #00e676);
    color: var(--noir01, #1a1a2e);
    padding: 6px 14px;
    border-radius: 20px;
    font-size: 0.85rem;
    font-weight: bold;
    font-family: "Luciole-regular", sans-serif;
    display: flex;
    align-items: center;
    gap: 6px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
    animation: ws-badge-in 300ms ease-out, ws-badge-out 400ms ease-in 2s forwards;
  }

  @keyframes ws-badge-in {
    from { opacity: 0; transform: translateY(-10px) scale(0.9); }
    to   { opacity: 1; transform: translateY(0) scale(1); }
  }

  @keyframes ws-badge-out {
    from { opacity: 1; }
    to   { opacity: 0; pointer-events: none; }
  }
</style>
```

##### Routing WebSocket

```python
# wsocket/routing.py
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # Consumer POS LaBoutik — 1 connexion par caisse ouverte
    # / LaBoutik POS consumer — 1 connection per open register
    re_path(
        r'ws/laboutik/(?P<pv_uuid>[0-9a-f-]+)/$',
        consumers.LaboutikConsumer.as_asgi(),
    ),
]
```

##### Template côté client : connexion WS dans l'interface POS

Dans `common_user_interface.html` et `billetterie.html`, ajouter :

```html
<!-- Connexion WebSocket — extension HTMX 2 ws -->
<!-- Le ws-connect établit la connexion. Tout HTML reçu est swappé par id. -->
<div hx-ext="ws" ws-connect="/ws/laboutik/{{ pv_dict.uuid }}/">

  <!-- Zone d'état WebSocket (mise à jour par hx_ws_connected.html) -->
  <div id="ws-status"></div>

  <!-- Zone de notifications (append via hx-swap-oob="beforeend") -->
  <div id="ws-notifications" aria-live="polite"></div>

  <!-- ... reste de l'interface POS ... -->

</div>
```

**⚠️ Important** : l'attribut `hx-ext="ws"` doit être sur un élément **parent** de toutes
les zones ciblées par les `id`. Sinon HTMX ne cherchera pas les swaps OOB dans le DOM
en dehors de ce conteneur.

##### Fichier extension HTMX ws.js

Télécharger depuis le CDN HTMX et placer dans les static :

```bash
# Télécharger l'extension ws pour HTMX 2.0.6
curl -o laboutik/static/js/ext/ws.js \
  https://unpkg.com/htmx-ext-ws@2.0.2/ws.js
```

Charger dans `base.html` après htmx :
```html
<script src="{% static 'js/htmx@2.0.6.min.js' %}"></script>
<script src="{% static 'js/ext/ws.js' %}"></script>
```

#### Broadcast depuis les vues (server → client)

La clé : après une action (vente de billet, commande restaurant), le **view code**
envoie un message au groupe WebSocket via `channel_layer.group_send()`.
Le consumer reçoit le message et le forward au client.

##### Helper : envoyer du HTML rendu à un groupe

```python
# wsocket/broadcast.py
# Fonctions utilitaires pour envoyer des fragments HTML via WebSocket.
# Utility functions to send HTML fragments via WebSocket.
#
# LOCALISATION : wsocket/broadcast.py
#
# Usage depuis n'importe quel view code (sync) :
#   from wsocket.broadcast import broadcast_html
#   broadcast_html("laboutik-pv-{uuid}", "laboutik/partial/hx_jauge_event.html", context)

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.template.loader import render_to_string


def broadcast_html(group_name, template_name, context, message_type="notification"):
    """
    Rend un template Django et l'envoie à un groupe WebSocket.
    / Renders a Django template and sends it to a WebSocket group.

    LOCALISATION : wsocket/broadcast.py

    Args:
        group_name: nom du groupe Channels (ex: "laboutik-pv-{uuid}")
        template_name: chemin du template Django (ex: "laboutik/partial/hx_jauge_event.html")
        context: dict de contexte pour le template
        message_type: type de handler dans le consumer (default: "notification")
                      Doit correspondre à une méthode async du consumer
                      (ex: "jauge.update" → méthode jauge_update())
    """
    # Rendre le template en HTML
    # / Render the template to HTML
    html = render_to_string(template_name, context)

    # Envoyer au groupe via le channel layer Redis
    # / Send to group via Redis channel layer
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        group_name,
        {
            "type": message_type,
            "html": html,
        },
    )


def broadcast_jauge_event(pv_uuid, event_data):
    """
    Raccourci : envoie la jauge mise à jour d'un événement à toutes les caisses du PV.
    / Shortcut: sends the updated gauge of an event to all POS registers.

    LOCALISATION : wsocket/broadcast.py

    Appelé depuis laboutik/views.py après une vente de billet :
        broadcast_jauge_event(pv_uuid, event_data_dict)

    Args:
        pv_uuid: UUID du point de vente (str)
        event_data: dict avec uuid, pourcentage_remplissage, places_restantes, complet, jauge_max
    """
    group_name = f"laboutik-pv-{pv_uuid}"
    broadcast_html(
        group_name=group_name,
        template_name="laboutik/partial/hx_jauge_event.html",
        context={"event": event_data},
        message_type="jauge.update",
    )
```

##### Usage dans les vues (exemple billetterie)

```python
# Dans laboutik/views.py, après la création des billets :

from wsocket.broadcast import broadcast_jauge_event

def _creer_billets_depuis_panier(...):
    with db_transaction.atomic():
        # ... création Ticket + LigneArticle ...
        pass

    # APRÈS le commit (hors du atomic) — envoyer la mise à jour
    # / AFTER commit (outside atomic) — send the update
    for event_uuid in events_modifies:
        event_data = _calculer_donnees_jauge(event_uuid)
        broadcast_jauge_event(str(pv.uuid), event_data)
```

**⚠️ CRITIQUE** : le `broadcast_jauge_event()` doit être appelé **APRÈS** le `atomic()`,
pas dedans. Si le broadcast est dans le bloc atomique et qu'il y a un rollback,
les clients recevraient une jauge incorrecte.

#### Adaptation des templates billetterie (polling → WebSocket)

##### Avant (polling HTMX 30s)

```html
<div class="billet-tuile-jauge-wrapper"
     hx-get="{% url 'laboutik-caisse-jauge_event' %}?event_uuid={{ event.uuid }}"
     hx-trigger="every 30s"
     hx-swap="outerHTML">
```

##### Après (WebSocket push)

```html
<div id="billet-jauge-{{ event.uuid }}"
     class="billet-tuile-jauge-wrapper">
  {# Plus de hx-trigger polling — mis à jour par le WebSocket via hx-swap-oob #}
  {# No more polling hx-trigger — updated by WebSocket via hx-swap-oob #}
  {% include "laboutik/partial/hx_jauge_event.html" with event=event %}
</div>
```

Le partial `hx_jauge_event.html` est rendu côté serveur par `broadcast_jauge_event()`,
enveloppé dans `<div id="billet-jauge-{uuid}" hx-swap-oob="true">` par le consumer,
et HTMX swap l'élément existant automatiquement.

**L'action `jauge_event()` (GET) reste disponible** comme fallback si le WebSocket
est coupé. On peut ajouter un `hx-trigger="every 60s"` de secours plus tard si besoin.

#### Fichiers à créer / modifier

| Fichier | Action | Contenu |
|---------|--------|---------|
| `TiBillet/settings.py` | Modifier | Décommenter `'channels'` dans INSTALLED_APPS (ligne 144) |
| `wsocket/consumers.py` | **Réécrire** | `LaboutikConsumer` (remplace `ChatConsumer`) |
| `wsocket/routing.py` | **Réécrire** | Route `ws/laboutik/<pv_uuid>/` |
| `wsocket/broadcast.py` | **Créer** | `broadcast_html()`, `broadcast_jauge_event()` |
| `laboutik/static/js/ext/ws.js` | **Télécharger** | Extension HTMX 2 WebSocket |
| `laboutik/templates/laboutik/base.html` | Modifier | Charger `ext/ws.js` après `htmx@2.0.6` |
| `laboutik/templates/laboutik/partial/hx_ws_connected.html` | **Créer** | Badge animation "Connecté" |
| `laboutik/templates/laboutik/views/common_user_interface.html` | Modifier | Ajouter `hx-ext="ws" ws-connect` + `#ws-status` |
| `tests/pytest/test_websocket_laboutik.py` | **Créer** | Test connexion + réception HTML |
| `tests/playwright/tests/laboutik/47-laboutik-websocket.spec.ts` | **Créer** | Test E2E : badge animation visible |

#### Ordre d'implémentation

1. **Infrastructure** : décommenter `channels`, télécharger `ws.js`, charger dans `base.html`
2. **Consumer + routing** : `LaboutikConsumer` + route `ws/laboutik/<pv_uuid>/`
3. **Template test** : `hx_ws_connected.html` (badge animation)
4. **Connexion client** : ajouter `hx-ext="ws" ws-connect` dans `common_user_interface.html`
5. **Test manuel** : ouvrir la caisse → badge vert "Connecté" apparaît 2s → disparaît
6. **`broadcast.py`** : helper pour envoyer du HTML depuis les vues
7. **Intégration billetterie** : remplacer le polling par le broadcast dans `_creer_billets_depuis_panier()`
8. **Tests pytest** : connexion WebSocket, réception HTML, broadcast de groupe
9. **Tests Playwright** : badge visible, jauge mise à jour après vente

#### Points d'attention

- **`render_to_string` est sync** : dans le consumer (async), utiliser `sync_to_async(render_to_string)`.
  Dans les vues (sync), `render_to_string` fonctionne directement.
- **`broadcast` APRÈS le commit** : jamais dans le `atomic()`. Si rollback, le client
  recevrait un état incohérent. Appeler `broadcast_jauge_event()` après le bloc `with`.
- **`group_send` est async** : dans les vues sync, utiliser `async_to_sync(channel_layer.group_send)`.
  Le helper `broadcast.py` gère ça automatiquement.
- **Multi-tenancy** : le consumer tourne dans le scope ASGI, pas dans le scope tenant.
  Si on a besoin de filtrer par tenant, passer le `tenant_pk` dans l'URL ou le scope.
  Pour l'instant, le PV UUID suffit (un PV n'existe que dans un seul tenant).
- **Reconnexion** : gérée automatiquement par l'extension HTMX ws (backoff exponentiel + jitter).
  Pas de code JS custom nécessaire.
- **wsocket dans TENANT_APPS** : le consumer n'accède pas aux modèles tenant directement.
  Il reçoit du HTML déjà rendu par les vues (qui sont dans le bon schema tenant).
- **`runserver` vs `runserver_plus`** : avec Daphne dans INSTALLED_APPS, `runserver` est
  remplacé par la version ASGI. `runserver_plus` (Werkzeug) ne supporte PAS ASGI.
  **Utiliser `manage.py runserver` pour le dev WebSocket, pas `runserver_plus`.**

---

### Phase Impression — Module d'impression modulaire (après WebSocket)

#### Vision

Module d'impression pour la **gestion de tickets** dans 2 contextes :

1. **Tickets de commande** (restaurant) : une commande avec Bière + Pizza → le ticket Bière
   part sur l'imprimante du Bar, le ticket Pizza sur l'imprimante de la Cuisine.
   Routage par catégorie d'article vers l'imprimante assignée.

2. **Tickets de vente / billets** (POS) : après paiement, le récapitulatif s'imprime sur
   l'imprimante du point de vente (Inner intégrée ou Cloud déportée).

**Backends au lancement** :
- **Sunmi Cloud** (`SC`) : HTTPS vers l'API Sunmi Cloud (HMAC-SHA256) — imprimantes déportées
- **Sunmi Inner** (`SI`) : WebSocket Channels vers D3mini (57mm) et V2S (80mm) — intégrées

**Extensibilité** : pattern Strategy. Ajouter un backend = 1 fichier + 1 ligne dans un dict.

#### Prérequis

- Phase WebSocket terminée (Sunmi Inner utilise `LaboutikConsumer` + `PrinterConsumer`)
- `LaboutikConfiguration` enrichi avec `sunmi_app_id` et `sunmi_app_key` (chiffrés Fernet)
- Celery opérationnel (déjà en place pour `envoyer_rapport_cloture`)

#### Pourquoi Celery est obligatoire

L'impression **ne doit jamais bloquer le caissier**. Deux sources de latence/erreur :

- **Sunmi Cloud** : requête HTTPS vers `openapi.sunmi.com` (~200-500ms, timeout possible)
- **Sunmi Inner** : WebSocket peut être déconnecté (terminal éteint, réseau coupé)

Sans Celery, un timeout = le caissier attend 30s devant un écran bloqué.
Avec Celery, le job d'impression part en background avec retry automatique :

```python
# laboutik/printing/tasks.py
@shared_task(bind=True, max_retries=10, default_retry_delay=5)
def imprimer_async(self, printer_pk, ticket_data):
    """
    Tâche Celery d'impression avec retry automatique.
    / Celery print task with automatic retry.

    LOCALISATION : laboutik/printing/tasks.py

    Retry : backoff exponentiel (5s, 10s, 20s, 40s, ..., max 5min)
    Max retries : 10 (~30min de tentatives)
    """
    try:
        printer = Printer.objects.get(pk=printer_pk)
        backend = BACKENDS[printer.printer_type]()
        result = backend.print_ticket(printer, ticket_data)
        if not result["ok"]:
            raise Exception(result["error"])
        return result
    except Exception as exc:
        retry_delay = min(5 * (2 ** self.request.retries), 300)  # max 5min
        logger.warning(f"[PRINT] Échec impression {printer_pk}, retry dans {retry_delay}s : {exc}")
        raise self.retry(exc=exc, countdown=retry_delay)
```

**Point d'entrée depuis les vues** (fire-and-forget) :
```python
# Dans laboutik/views.py, après paiement :
from laboutik.printing.tasks import imprimer_async
imprimer_async.delay(printer.pk, ticket_data)
# Le caissier n'attend pas — la réponse revient immédiatement
```

#### Routage des tickets de commande — CategorieProduct → Printer

Dans l'ancien LaBoutik, le routage est : `Article → Categorie → GroupementCategorie → Printer`.
On simplifie : **`CategorieProduct` porte directement une FK vers `Printer`**.

```python
# Dans BaseBillet/models.py — CategorieProduct existant :
class CategorieProduct(models.Model):
    # ... champs existants (name, icon, couleur, etc.) ...

    printer = models.ForeignKey(
        'laboutik.Printer', on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name=_("Printer for order tickets"),
        help_text=_("Imprimante pour les tickets de commande de cette catégorie. "
                    "/ Printer for order tickets of this category.")
    )
```

**Routage d'une commande** :
```
Commande avec [Bière (cat: Bar), Pizza (cat: Cuisine), Eau (cat: Bar)]
  → grouper par CategorieProduct.printer :
    - Printer "Imprimante Bar"  → [Bière ×1, Eau ×1]
    - Printer "Imprimante Cuisine" → [Pizza ×1]
  → 2 tâches Celery lancées en parallèle
```

Si `CategorieProduct.printer = None` → pas d'impression pour cette catégorie.

**Pourquoi pas un modèle GroupeImpression séparé** : une indirection de plus sans gain.
La FK directe est plus FALC. Si un jour on a besoin de grouper plusieurs catégories
sur la même imprimante, on change juste la FK (toutes pointent vers le même Printer).

#### Identification des terminaux — pas de modèle Appareil

L'ancien modèle `Appareil` (device physique avec OneToOne User + pin_code + IP + type)
servait à 2 choses :
1. Identifier le terminal pour le WebSocket (channel = `user.uuid.hex`)
2. Stocker les métadonnées du device (IP, version, type)

Dans le nouveau système :
- Le terminal se connecte via `ws/printer/{printer_uuid}/` (route WebSocket dédiée)
- L'UUID du `Printer` **est** l'identifiant du device — pas besoin d'un modèle intermédiaire
- Les métadonnées (IP, version) ne sont pas nécessaires pour imprimer

**Consumer dédié aux imprimantes** (`PrinterConsumer`) :

```python
# wsocket/consumers.py
class PrinterConsumer(AsyncWebsocketConsumer):
    """
    Consumer WebSocket pour les imprimantes Sunmi Inner (D3mini, V2S).
    Chaque imprimante se connecte avec son UUID.
    / WebSocket consumer for Sunmi Inner printers (D3mini, V2S).
    Each printer connects with its UUID.

    LOCALISATION : wsocket/consumers.py

    Route : ws/printer/{printer_uuid}/
    Groupe : printer-{printer_uuid}
    """

    async def connect(self):
        self.printer_uuid = self.scope["url_route"]["kwargs"]["printer_uuid"]
        self.group_name = f"printer-{self.printer_uuid}"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        # Marquer l'imprimante comme connectée (optionnel)
        # / Mark printer as connected (optional)
        logger.info(f"[WS] Imprimante {self.printer_uuid} connectée")

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
        logger.info(f"[WS] Imprimante {self.printer_uuid} déconnectée")

    async def print_ticket(self, event):
        """
        Forward les commandes d'impression au terminal.
        / Forwards print commands to the terminal.
        """
        await self.send(text_data=json.dumps({
            "action": "print",
            "commands": event["commands"],
        }))
```

**Route WebSocket** :
```python
# wsocket/routing.py
websocket_urlpatterns = [
    re_path(r'ws/laboutik/(?P<pv_uuid>[0-9a-f-]+)/$', consumers.LaboutikConsumer.as_asgi()),
    re_path(r'ws/printer/(?P<printer_uuid>[0-9a-f-]+)/$', consumers.PrinterConsumer.as_asgi()),
]
```

**Envoi depuis le backend Inner** :
```python
# laboutik/printing/sunmi_inner.py
class SunmiInnerBackend(PrinterBackend):
    def print_ticket(self, printer, ticket_data):
        commands = _build_inner_commands(ticket_data, printer.paper_width)
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"printer-{printer.uuid}",  # le groupe = l'UUID de l'imprimante
            {
                "type": "print.ticket",
                "commands": commands,
            },
        )
```

**Comment le terminal sait quel UUID utiliser** :
1. L'admin crée un `Printer(type=SI, name="Cuisine")` → UUID auto-généré
2. L'admin note l'UUID (affiché dans l'admin Unfold)
3. L'app Android Sunmi est configurée avec cet UUID dans ses settings
4. Au démarrage, l'app se connecte à `ws/printer/{uuid}/`

#### Code legacy de référence

Le code de l'ancien LaBoutik est dans `OLD_REPOS/LaBoutik/epsonprinter/` :
- `sunmi_cloud_printer.py` — bibliothèque Sunmi Cloud complète (750+ lignes, ESC/POS)
- `tasks.py` — dispatch Celery + formatage des tickets (1000+ lignes)
- `models.py` — modèle Printer avec 4 types

**Ce qu'on reprend** :
- La classe `SunmiCloudPrinter` (signature HMAC, commandes ESC/POS, pushContent API)
- Le format JSON des commandes inner printer (`[{"type": "text", "value": "..."}, ...]`)
- Le pattern de dispatch par `printer_type`
- Le chiffrement Fernet pour `sunmi_app_id` / `sunmi_app_key`
- Le pattern Celery task avec retry exponentiel

**Ce qu'on NE reprend PAS** :
- Le backend Epson/Flask (pas de Pi pour l'instant)
- Le modèle `Appareil` (le Printer UUID suffit pour le WebSocket)
- Le consumer `ChatConsumer` (remplacé par `PrinterConsumer` dédié)
- Le `GroupementCategorie` (remplacé par FK directe `CategorieProduct.printer`)

#### Architecture fichiers

```
laboutik/printing/
├── __init__.py                → BACKENDS dict + imprimer() sync + imprimer_async() Celery
├── base.py                    → PrinterBackend interface
├── sunmi_cloud.py             → SunmiCloudBackend (HTTPS + HMAC)
├── sunmi_inner.py             → SunmiInnerBackend (WebSocket via PrinterConsumer)
├── sunmi_cloud_printer.py     → Bibliothèque ESC/POS Sunmi (copie nettoyée du legacy)
├── formatters.py              → Construction des tickets (indépendant du backend)
└── tasks.py                   → Celery tasks (imprimer_async, imprimer_commande)
```

#### Interface commune (`printing/base.py`)

```python
class PrinterBackend:
    """
    Interface commune pour tous les backends d'impression.
    / Common interface for all print backends.
    LOCALISATION : laboutik/printing/base.py
    """

    def can_print(self, printer):
        """Vérifie la configuration. Retourne (bool, str_erreur)."""
        raise NotImplementedError

    def print_ticket(self, printer, ticket_data):
        """Envoie un ticket. Retourne {"ok": bool, "error": str|None}."""
        raise NotImplementedError

    def print_test(self, printer):
        """Imprime un ticket de test."""
        raise NotImplementedError
```

#### Dispatch — 2 points d'entrée (`printing/__init__.py`)

```python
BACKENDS = {
    'SC': SunmiCloudBackend,
    'SI': SunmiInnerBackend,
}

def imprimer(printer, ticket_data):
    """
    Point d'entrée SYNC (pour tests et debug).
    En production, utiliser imprimer_async.delay().
    """
    backend = BACKENDS[printer.printer_type]()
    ok, error = backend.can_print(printer)
    if not ok:
        return {"ok": False, "error": error}
    return backend.print_ticket(printer, ticket_data)
```

#### Tâches Celery (`printing/tasks.py`)

```python
@shared_task(bind=True, max_retries=10)
def imprimer_async(self, printer_pk, ticket_data):
    """Impression d'un ticket avec retry. Fire-and-forget depuis les vues."""
    ...

@shared_task(bind=True, max_retries=10)
def imprimer_commande(self, commande_pk):
    """
    Impression d'une commande restaurant : split par catégorie → 1 ticket par imprimante.
    / Restaurant order printing: split by category → 1 ticket per printer.

    LOCALISATION : laboutik/printing/tasks.py

    FLUX :
    1. Charger CommandeSauvegarde + articles
    2. Grouper les articles par CategorieProduct.printer
    3. Pour chaque groupe : formatter_ticket_commande() → imprimer()
    4. Retry si une imprimante échoue (les autres ne sont pas affectées)
    """
    commande = CommandeSauvegarde.objects.get(pk=commande_pk)
    articles = commande.articles.select_related(
        'product__categorie_pos__printer'
    ).all()

    # Grouper par imprimante
    par_imprimante = {}
    for article in articles:
        printer = article.product.categorie_pos.printer if article.product.categorie_pos else None
        if printer and printer.active:
            par_imprimante.setdefault(printer.pk, []).append(article)

    # 1 ticket par imprimante
    for printer_pk, articles_groupe in par_imprimante.items():
        printer = Printer.objects.get(pk=printer_pk)
        ticket_data = formatter_ticket_commande(commande, articles_groupe, printer)
        result = imprimer(printer, ticket_data)
        if not result["ok"]:
            logger.warning(f"[PRINT] Échec commande {commande.uuid} → {printer.name} : {result['error']}")
```

**Appel depuis les vues** (CommandeViewSet.ouvrir_commande) :
```python
# Après création de la commande, fire-and-forget
from laboutik.printing.tasks import imprimer_commande
imprimer_commande.delay(str(commande.pk))
```

#### Modèle `Printer` (`laboutik/models.py`)

```python
class Printer(models.Model):
    """
    Imprimante thermique. Peut être assignée à un PV (ticket de vente)
    ou à une catégorie d'articles (ticket de commande).
    / Thermal printer. Can be assigned to a POS (sale ticket)
    or to an article category (order ticket).

    LOCALISATION : laboutik/models.py
    """

    SUNMI_CLOUD = 'SC'
    SUNMI_INNER = 'SI'
    PRINTER_TYPE_CHOICES = [
        (SUNMI_CLOUD, _('Sunmi Cloud')),
        (SUNMI_INNER, _('Sunmi Inner (D3mini / V2S)')),
    ]

    PAPER_80 = '80'
    PAPER_57 = '57'
    PAPER_WIDTH_CHOICES = [
        (PAPER_80, _('80mm')),
        (PAPER_57, _('57mm')),
    ]

    uuid = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    name = models.CharField(max_length=100, verbose_name=_("Name"))
    printer_type = models.CharField(max_length=2, choices=PRINTER_TYPE_CHOICES)
    paper_width = models.CharField(max_length=2, choices=PAPER_WIDTH_CHOICES, default=PAPER_80)

    # --- Sunmi Cloud ---
    sunmi_serial_number = models.CharField(max_length=100, null=True, blank=True,
        verbose_name=_("Sunmi serial number"))

    # --- Commun ---
    active = models.BooleanField(default=True)
```

**Pas de FK `point_de_vente` sur Printer** : la liaison se fait dans l'autre sens.
- Ticket de vente → `PointDeVente.printer` FK (nullable) vers Printer
- Ticket de commande → `CategorieProduct.printer` FK (nullable) vers Printer

```python
# Ajout dans PointDeVente :
printer = models.ForeignKey(
    Printer, on_delete=models.SET_NULL, null=True, blank=True,
    verbose_name=_("Receipt printer"),
    help_text=_("Imprimante pour les tickets de vente de ce PV")
)

# Ajout dans CategorieProduct (BaseBillet) :
printer = models.ForeignKey(
    'laboutik.Printer', on_delete=models.SET_NULL, null=True, blank=True,
    verbose_name=_("Order ticket printer"),
    help_text=_("Imprimante pour les tickets de commande de cette catégorie")
)
```

#### Champs ajoutés à `LaboutikConfiguration`

```python
sunmi_app_id = models.CharField(max_length=200, null=True, blank=True)
sunmi_app_key = models.CharField(max_length=200, null=True, blank=True)

def get_sunmi_app_id(self):
    if not self.sunmi_app_id:
        raise ValueError(_("Sunmi APP ID non configuré"))
    return fernet_decrypt(self.sunmi_app_id)

def set_sunmi_app_id(self, value):
    self.sunmi_app_id = fernet_encrypt(value)
    self.save(update_fields=['sunmi_app_id'])
# Idem pour app_key
```

**Chiffrement Fernet** : même pattern que l'ancien LaBoutik (`fedow_connect.utils`).

#### Bibliothèque SunmiCloudPrinter

Copie de `OLD_REPOS/LaBoutik/epsonprinter/sunmi_cloud_printer.py` dans
`laboutik/printing/sunmi_cloud_printer.py`, nettoyée :
- Supprimer numpy/PIL (pas d'images)
- Garder : signature HMAC, ESC/POS texte, QR code, barcode, coupe papier
- Docstrings FALC bilingues

#### Fichiers à créer / modifier

| Fichier | Action | Contenu |
|---------|--------|---------|
| `laboutik/printing/__init__.py` | Créer | `BACKENDS` dict + `imprimer()` |
| `laboutik/printing/base.py` | Créer | `PrinterBackend` interface |
| `laboutik/printing/sunmi_cloud.py` | Créer | `SunmiCloudBackend` (HTTPS + HMAC) |
| `laboutik/printing/sunmi_inner.py` | Créer | `SunmiInnerBackend` (WebSocket) |
| `laboutik/printing/sunmi_cloud_printer.py` | Copier + nettoyer | Bibliothèque ESC/POS |
| `laboutik/printing/formatters.py` | Créer | 4 formatters (vente, billet, commande, clôture) |
| `laboutik/printing/tasks.py` | Créer | `imprimer_async()`, `imprimer_commande()` |
| `laboutik/models.py` | Modifier | Modèle `Printer` + FK sur `PointDeVente` |
| `BaseBillet/models.py` | Modifier | FK `printer` sur `CategorieProduct` |
| `laboutik/models.py` | Modifier | `sunmi_app_id/key` sur `LaboutikConfiguration` |
| `laboutik/migrations/0003_*.py` | Créer | Migration Printer + champs |
| `BaseBillet/migrations/0203_*.py` | Créer | Migration CategorieProduct.printer FK |
| `wsocket/consumers.py` | Modifier | Ajouter `PrinterConsumer` |
| `wsocket/routing.py` | Modifier | Route `ws/printer/{printer_uuid}/` |
| `Administration/admin/laboutik.py` | Modifier | `PrinterAdmin` dans sidebar Caisse |
| `laboutik/views.py` | Modifier | Remplacer stub par `imprimer_async.delay()` |
| `tests/pytest/test_printing.py` | Créer | Tests backends mockés, routage, formatters |

#### Ordre d'implémentation

1. **Modèle `Printer`** + FK sur PointDeVente et CategorieProduct + LaboutikConfiguration + migrations
2. **`printing/base.py`** : interface `PrinterBackend`
3. **`printing/sunmi_cloud_printer.py`** : copie nettoyée du legacy
4. **`printing/sunmi_cloud.py`** : backend Cloud (HTTPS API)
5. **`printing/sunmi_inner.py`** : backend Inner (WebSocket)
6. **`wsocket/consumers.py` + `routing.py`** : `PrinterConsumer` + route dédiée
7. **`printing/formatters.py`** : construction des tickets (vente, commande, billet, clôture)
8. **`printing/tasks.py`** : tâches Celery (imprimer_async, imprimer_commande)
9. **`printing/__init__.py`** : dispatch
10. **Admin Unfold** : `PrinterAdmin`
11. **`laboutik/views.py`** : remplacer stub + appeler `imprimer_commande.delay()` dans CommandeViewSet
12. **Tests** : backends mockés, routage commande, formatters

#### Ajout futur d'un backend (ex: Epson)

1. Ajouter le type dans `Printer.PRINTER_TYPE_CHOICES` (ex: `EPSON = 'EP'`)
2. Créer `laboutik/printing/epson.py` implémentant `PrinterBackend`
3. Ajouter les champs spécifiques au `Printer` si nécessaire (ex: `flask_server_url`)
4. Enregistrer dans `BACKENDS` dict
5. Migration pour le nouveau choix + champs

**Aucun autre fichier à modifier** — dispatch, formatters, tasks et vues restent identiques.

#### Points d'attention

- **Celery obligatoire** : pas d'impression synchrone en production. `imprimer_async.delay()`
  est fire-and-forget, le caissier n'attend jamais.
- **Retry exponentiel** : 5s, 10s, 20s, ... max 5min. 10 retries max (~30min de tentatives).
- **Split commande** : chaque imprimante reçoit son ticket indépendamment. Un échec sur
  l'imprimante cuisine ne bloque pas l'imprimante bar.
- **Fernet** : credentials chiffrés. `FERNET_KEY` dans les env vars du conteneur.
- **PrinterConsumer séparé de LaboutikConsumer** : une imprimante cuisine n'est pas un POS.
  Elle a son propre consumer sur `ws/printer/{uuid}/`.
- **Pas de modèle Appareil** : l'UUID du Printer suffit. L'app Android stocke l'UUID
  dans ses settings et se connecte avec. Pas de pin_code, pas de pairing complexe.
- **Dots per line** : 384 (80mm) ou 240 (57mm). Le backend lit `printer.paper_width`.

---

### Amélioration Multi-Tarif — Overlay non-bloquant avec quantités

#### Contexte — ce qui existe

Le multi-tarif fonctionne déjà pour les adhésions et les prix libres.
Quand un article a plusieurs `Price` ou un prix libre (`free_price=True`), le clic ouvre
un overlay de sélection au lieu d'ajouter directement au panier.

**Chaîne d'événements actuelle** :
```
clic article (data-multi-tarif="true")
  → articles.js:manageKey() détecte multi_tarif
  → événement 'tarifSelection' via eventsOrganizer
  → tarif.js:tarifSelection() construit l'overlay dans #messages (innerHTML)
  → overlay plein écran avec boutons tarif (fixe) ou input (prix libre)
  → clic bouton tarif → tarifSelectFixed() ou tarifValidateFreePrix()
    → tarifClose() ferme l'overlay
    → addArticleWithPrice(uuid, priceUuid, prix, name, currency, customAmount)
    → événement 'articlesAdd' avec priceUuid
  → addition.js:additionInsertArticle() crée la ligne dans le panier
    → clé formulaire : repid-<uuid>--<priceUuid> (+ custom-* si prix libre)
```

**Format des données** :
- `data-tarifs='[{"price_uuid":"...", "name":"...", "prix_centimes":550, "free_price":false}]'`
- Formulaire POST : `repid-product_uuid--price_uuid=quantité` + `custom-product_uuid--price_uuid=montant_centimes`
- Backend parse via `PanierSerializer.extraire_articles_du_post()`

**Fichiers impliqués** :
- `laboutik/static/laboutik/js/tarif.js` — overlay, sélection, validation prix libre
- `laboutik/static/laboutik/js/articles.js` — détection multi-tarif, dispatch
- `laboutik/static/laboutik/js/addition.js` — ajout au panier, gestion quantités
- `laboutik/static/laboutik/js/tibilletUtils.js` — routage événements
- `laboutik/templates/cotton/articles.html` — `data-multi-tarif`, `data-tarifs` JSON
- `laboutik/serializers.py` — `extraire_articles_du_post()` (parse repid-* et custom-*)

#### Problème

L'overlay actuel est **modal et bloquant** :
1. Injecté dans `#messages` avec `innerHTML` → **masque tout** (panier invisible)
2. Après sélection, `tarifClose()` ferme l'overlay → **il faut recliquer** sur l'article
3. Pour le prix libre, il faut **re-saisir le montant** à chaque fois

**Cas d'usage cassé** : "3 billets prix libre à 5€" → l'utilisateur doit cliquer 3 fois
sur l'article, 3 fois ouvrir l'overlay, 3 fois taper "5" et valider. Inutilisable.

**Autre cas** : "2 bières demi + 1 bière pinte" → 3 clics + 3 sélections de tarif.
L'overlay devrait rester ouvert pour enchaîner.

#### Solution — overlay latéral non-bloquant

**Principe** : l'overlay de sélection de tarif remplace la **zone articles** (centre),
pas `#messages` ni tout l'écran. Le **panier reste visible** à droite.
Chaque clic sur un bouton tarif **incrémente la quantité** sans fermer l'overlay.

```
AVANT (modal bloquant) :
┌───────────────────────────────────────────────────────┐
│                 OVERLAY PLEIN ÉCRAN                     │
│   ┌─────────┐ ┌─────────┐ ┌─────────┐                 │
│   │  Demi   │ │  Pinte  │ │ ? libre │                 │
│   │ 3,50 €  │ │ 5,50 €  │ │ min 1€  │                 │
│   └─────────┘ └─────────┘ └─────────┘                 │
│                  [RETOUR]                               │
└───────────────────────────────────────────────────────┘

APRÈS (latéral, panier visible) :
┌──────────┬────────────────────────────┬───────────────┐
│ SIDEBAR  │ OVERLAY TARIF (remplace    │  PANIER       │
│ catégories│ la grille articles)        │  (visible)    │
│          │                            │               │
│          │  Bière — Choisir un tarif  │ 2× Demi 7,00€│
│          │  ┌─────────┐ ┌─────────┐  │ 1× Pinte 5,50│
│          │  │  Demi   │ │  Pinte  │  │               │
│          │  │ 3,50 €  │ │ 5,50 €  │  │ Total: 12,50€│
│          │  └─────────┘ └─────────┘  │               │
│          │  ┌─────────────────────┐  │               │
│          │  │  Prix libre min 1€  │  │               │
│          │  │  [   5,00  ] € [OK] │  │               │
│          │  └─────────────────────┘  │               │
│          │                            │               │
│          │  [← RETOUR aux articles]   │               │
├──────────┴────────────────────────────┴───────────────┤
│ [RESET]        [CHECK CARTE]           [VALIDER 12,50€]│
└───────────────────────────────────────────────────────┘
```

#### Changements techniques

##### 1. Cible de l'overlay : `#articles-zone` au lieu de `#messages`

```javascript
// AVANT (tarif.js) :
const messagesEl = document.querySelector('#messages')
messagesEl.innerHTML = `<div id="tarif-overlay">...</div>`

// APRÈS :
const articlesZone = document.querySelector('#articles-zone')
// Sauvegarder le contenu actuel pour le restaurer au retour
articlesZone._savedContent = articlesZone.innerHTML
articlesZone.innerHTML = `<div id="tarif-overlay">...</div>`
```

`#articles-zone` est le conteneur de la grille d'articles (zone centrale).
Le panier (`#addition`) et la sidebar catégories restent intacts.

##### 2. Clic tarif = incrément sans fermer

```javascript
// AVANT :
function tarifSelectFixed(uuid, priceUuid, prix, name, currency) {
    tarifClose()  // ← ferme l'overlay
    addArticleWithPrice(uuid, priceUuid, prix, name, currency)
}

// APRÈS :
function tarifSelectFixed(uuid, priceUuid, prix, name, currency) {
    // PAS de tarifClose() — l'overlay reste ouvert
    addArticleWithPrice(uuid, priceUuid, prix, name, currency)
    // Feedback visuel : flash vert sur le bouton cliqué
    flashButton(event.target)
}
```

Le caissier clique autant de fois qu'il veut sur "Demi" ou "Pinte".
Le panier se met à jour en temps réel à droite (quantité incrémentée).

##### 3. Prix libre : mémoriser le dernier montant

```javascript
// APRÈS : le champ input garde sa valeur après validation
function tarifValidateFreePrix(uuid, priceUuid, minCentimes, name, currency) {
    const inputEl = document.querySelector(`#tarif-free-amount-${priceUuid}`)
    const montant = parseFloat(inputEl.value)
    // ... validation ...
    addArticleWithPrice(uuid, priceUuid, montantCentimes, name, currency, montantCentimes)
    // NE PAS vider l'input — le montant reste pour le prochain clic OK
    flashButton(event.target)
}
```

Cas d'usage : "3 billets à 5€" → taper 5, cliquer OK 3 fois. Le champ garde "5".

##### 4. Bouton RETOUR restaure la grille

```javascript
function tarifClose() {
    const articlesZone = document.querySelector('#articles-zone')
    if (articlesZone._savedContent) {
        articlesZone.innerHTML = articlesZone._savedContent
        articlesZone._savedContent = null
    }
}
```

##### 5. Badge quantité sur le bouton tarif (optionnel)

Afficher un mini-badge sur chaque bouton tarif montrant combien sont déjà dans le panier :

```html
<button class="tarif-btn" onclick="tarifSelectFixed(...)">
    <div class="tarif-btn-label">Demi</div>
    <div class="tarif-btn-price">3,50 €</div>
    <span class="tarif-btn-badge" id="tarif-badge-{priceUuid}">2</span>
</button>
```

Mis à jour par `addArticleWithPrice()` après chaque ajout.

#### Ce qui ne change PAS

- Le backend (`serializers.py`, `views.py`) ne change pas — le format POST est identique
- `data-multi-tarif` et `data-tarifs` sur les tuiles restent identiques
- L'événement `articlesAdd` et `additionInsertArticle()` restent identiques
- Le calcul du total ne change pas
- Les tests backend (pytest) ne sont pas impactés

#### Fichiers à modifier

| Fichier | Changement |
|---------|------------|
| `laboutik/static/laboutik/js/tarif.js` | Cible `#articles-zone`, pas de `tarifClose()` après sélection, mémorisation prix libre |
| `laboutik/static/laboutik/js/tibilletUtils.js` | Modifier le routage `tarifSelection` → cible `#articles-zone` |
| `laboutik/templates/cotton/articles.html` | Ajouter `id="articles-zone"` sur le conteneur (si absent) |
| `tests/playwright/tests/laboutik/45-*` | Adapter les tests overlay (visible en même temps que le panier) |

#### Ordre d'implémentation

1. Vérifier que `#articles-zone` existe dans le DOM (ou l'ajouter)
2. Modifier `tarif.js` : cible, pas de fermeture auto, flash feedback, mémorisation input
3. Modifier `tibilletUtils.js` : routage événement
4. Ajouter badge quantité sur les boutons tarif
5. Tester manuellement : enchaîner 3 sélections du même tarif
6. Adapter les tests Playwright

#### Cas d'usage clés à tester

| Cas | Flow attendu |
|-----|-------------|
| 3 bières demi | Clic article → overlay → clic Demi ×3 → panier montre "3× Demi 10,50€" |
| 2 bières demi + 1 pinte | Clic article → overlay → clic Demi ×2, clic Pinte ×1 → panier montre 2 lignes |
| 3 billets prix libre à 5€ | Clic billet → overlay → saisir 5 → OK ×3 → panier montre "3× Billet 15,00€" |
| 1 billet à 5€ + 1 à 10€ | Clic billet → overlay → saisir 5 → OK → saisir 10 → OK → 2 lignes dans panier |
| Retour aux articles | Clic RETOUR → grille articles restaurée, panier intact |

---

### Phase Multi-Asset — Paniers mixtes EUR + tokens (à détailler avec le mainteneur)

#### Contexte

Le plan (section 13.5) décrit le cas d'un panier contenant des articles dans des assets différents
(ex: Bière en EUR + Concert en tokens TIM). Cette logique de regroupement par asset n'est **pas
encore implémentée** dans `PaiementViewSet.payer()`.

#### Ce qui devra être fait

- Regrouper les articles du panier par `Price.asset` (null=EUR, set=tokens)
- Payer chaque groupe séparément dans le même `transaction.atomic()`
- Gérer l'affichage : total par asset, pas un total unique en EUR
- Le JS d'addition devra afficher les totaux par asset (session dédiée avec le mainteneur)

#### Prérequis

- Phase Billetterie terminée (premier cas d'usage réel : billet en tokens temps)
- Phase WebSocket terminée (l'UX multi-asset nécessite un affichage dynamique)
- Phase Impression terminée

**⚠️ Le JS est le point le plus risqué** — session dédiée avec le mainteneur pour définir
l'UX du panier multi-asset. À détailler ensemble avant d'implémenter.

---

### Phase Rapports Comptables — Ticket Z enrichi + admin + exports + envoi automatique

#### Vision

Remplacer le rapport de clôture basique (Phase 5) par un **rapport comptable complet**
conforme aux obligations légales françaises, avec dashboard dans l'admin Unfold,
exports (PDF, CSV, Excel), et envoi automatique programmable.

**Document juridique** : le ticket Z est une pièce comptable obligatoire pour les
commerces en France. Il doit être conservé, numéroté séquentiellement, et contenir
les informations fiscales requises (TVA par taux, totaux par moyen de paiement, etc.).

#### Ce qui existe (Phase 5 — basique)

Le `rapport_json` actuel contient 5 sections :
- `par_moyen_paiement` : espèces, CB, NFC (totaux en centimes)
- `par_produit` : nom → {total, qty}
- `par_categorie` : nom → total
- `par_tva` : taux → {ttc, ht, tva}
- `commandes` : {total, annulees}

**Ce qui manque** (identifié par audit du legacy TicketZ V4 + obligations légales) :

#### Ce qui doit être ajouté

##### 1. Détail des ventes avec marge (inspiré de `table_detail_ventes`)

Pour chaque article vendu pendant la période, groupé par catégorie :

| Champ | Description |
|-------|-------------|
| nom_article | Nom du produit |
| prix_ttc | Prix de vente unitaire TTC |
| prix_ht | Prix unitaire HT (calculé) |
| taux_tva | Taux applicable |
| qty_vendus | Quantités vendues (paiements fiduciaires) |
| qty_offerts | Quantités offertes (paiements cadeau/gratuit) |
| qty_total | Total toutes méthodes |
| ca_ttc | Chiffre d'affaires TTC (qty_vendus × prix_ttc) |
| ca_ht | Chiffre d'affaires HT |
| total_tva | TVA collectée |

**Regroupement** : par `CategorieProduct`, avec sous-total par catégorie et total général.

**Simplification vs legacy** : on supprime les champs `prix_achat`, `cout_total`, `benefice`
(pas disponibles dans le nouveau modèle Product). Si le mainteneur veut la marge, on ajoutera
un champ `prix_achat` sur Product plus tard.

##### 2. Solde de caisse (fond de caisse)

Reconstitution du contenu théorique du tiroir-caisse :

```
Fond de caisse (montant initial configuré)
+ Ventes en espèces
+ Recharges cashless en espèces
+ Adhésions en espèces
- Remboursements en espèces
- Retours consigne en espèces
= Solde théorique du tiroir-caisse
```

Nécessite un champ `fond_de_caisse` dans `LaboutikConfiguration` (montant initial en centimes).

##### 3. Recharges cashless détaillées

Totaux par type de recharge × moyen de paiement :

| Type | Espèces | CB | Chèque | Total |
|------|---------|-----|--------|-------|
| Recharge euros (RE) | ... | ... | ... | ... |
| Recharge cadeau (RC) | ... | ... | ... | ... |
| Recharge temps (TM) | ... | ... | ... | ... |

##### 4. Adhésions détaillées

| Produit adhésion | Espèces | CB | NFC | Total | Nb créées | Nb renouvelées |
|-----------------|---------|-----|-----|-------|-----------|----------------|

##### 5. Remboursements et vides carte

Totaux des opérations de retour (VIDER_CARTE, RETOUR_CONSIGNE) par moyen de paiement.

##### 6. Métriques clients (habitus)

| Métrique | Calcul |
|----------|--------|
| Cartes NFC utilisées | COUNT(DISTINCT carte) sur LigneArticle de la période |
| Recharge médiane | Médiane des sommes de recharges par carte |
| Panier moyen cashless | Moyenne des dépenses cashless par carte |
| Nouvelles adhésions | COUNT des Membership créées pendant la période |
| Renouvellements | COUNT des Membership renouvelées |

**Optimisation vs legacy** : pas de boucle N+1 par carte. Utiliser des sous-requêtes
annotées (`Subquery`, `OuterRef`) ou des `values().annotate()` groupés.

##### 7. Billets de la soirée en cours

**Cas d'usage** : le soir d'un concert, le rapport doit montrer les billets vendus
pour CET événement, même si certains ont été vendus les jours précédents (en ligne).

| Événement | Billets vendus (total) | Vendus en caisse (période) | Vendus en ligne (avant) | Scannés |
|-----------|----------------------|---------------------------|------------------------|---------|

**Logique** :
```python
# Événements dont la date est dans la période de clôture
events_en_cours = Event.objects.filter(
    datetime__gte=datetime_ouverture,
    datetime__lte=datetime_cloture + timedelta(hours=6),  # marge pour les soirées tardives
)

for event in events_en_cours:
    total_billets = event.valid_tickets_count()  # méthode existante
    billets_caisse = Ticket.objects.filter(
        reservation__event=event,
        # LigneArticle liée au Ticket, sale_origin=LABOUTIK, dans la période
    ).count()
    billets_en_ligne = total_billets - billets_caisse
    billets_scannes = Ticket.objects.filter(
        reservation__event=event,
        status=Ticket.SCANNED,
    ).count()
```

##### 8. Synthèse des opérations (total général)

Tableau récapitulatif cross-type (comme `table_TOTAL_sop` du legacy) :

| Moyen | Ventes | Recharges | Adhésions | Remb. | Total |
|-------|--------|-----------|-----------|-------|-------|
| Espèces | ... | ... | ... | ... | ... |
| CB | ... | ... | ... | ... | ... |
| NFC | ... | ... | ... | ... | ... |
| Chèque | ... | ... | ... | ... | ... |
| **Total** | ... | ... | ... | ... | **...** |

##### 9. Informations légales obligatoires

Le rapport doit inclure :
- **SIREN/SIRET** de la structure (depuis `Configuration`)
- **Adresse** du lieu
- **Numéro séquentiel** du ticket Z (auto-incrémenté par PV)
- **Date et heure** d'ouverture et de clôture
- **Nom de l'opérateur** qui a clôturé
- **Nom du point de vente**
- **Mention "NF525"** si la caisse est certifiée (optionnel, champ config)

##### 10. Opérateurs

Liste des opérateurs ayant effectué des ventes pendant la période,
avec leur total respectif.

#### Architecture technique

##### Modèle `RapportComptable`

Remplacement progressif de `ClotureCaisse.rapport_json` par un modèle dédié
plus structuré. `ClotureCaisse` reste pour la clôture POS (fermer les tables,
annuler les commandes). Le `RapportComptable` est le document comptable.

```python
class RapportComptable(models.Model):
    """
    Rapport comptable (Ticket Z) — document juridique conservé.
    / Accounting report (Z-Ticket) — legal document, kept for audit.

    LOCALISATION : laboutik/models.py
    """
    uuid = models.UUIDField(primary_key=True, default=uuid4)
    cloture = models.OneToOneField(ClotureCaisse, on_delete=models.PROTECT, null=True, blank=True)
    numero_sequentiel = models.PositiveIntegerField()  # auto-incrémenté par PV
    point_de_vente = models.ForeignKey(PointDeVente, on_delete=models.PROTECT)
    responsable = models.ForeignKey(TibilletUser, on_delete=models.SET_NULL, null=True)
    datetime_debut = models.DateTimeField()
    datetime_fin = models.DateTimeField()

    # Totaux principaux (centimes)
    total_especes = models.IntegerField(default=0)
    total_carte_bancaire = models.IntegerField(default=0)
    total_cashless = models.IntegerField(default=0)
    total_cheque = models.IntegerField(default=0)
    total_general = models.IntegerField(default=0)
    nombre_transactions = models.IntegerField(default=0)

    # Rapport détaillé
    rapport_json = models.JSONField(default=dict)
    # Structure : voir ci-dessous

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('point_de_vente', 'numero_sequentiel')]
        ordering = ['-datetime_fin']
```

##### Service de calcul

```python
# laboutik/reports.py
class RapportComptableService:
    """
    Construit le rapport comptable complet à partir des LigneArticle.
    Inspiré de OLD_REPOS/LaBoutik/administration/ticketZ_V4.py, simplifié.
    / Builds the complete accounting report from LigneArticle records.

    LOCALISATION : laboutik/reports.py
    """

    def __init__(self, point_de_vente, datetime_debut, datetime_fin):
        self.pv = point_de_vente
        self.debut = datetime_debut
        self.fin = datetime_fin
        self.lignes = self._charger_lignes()

    def _charger_lignes(self):
        return LigneArticle.objects.filter(
            sale_origin=SaleOrigin.LABOUTIK,
            datetime__gte=self.debut,
            datetime__lte=self.fin,
            status=LigneArticle.VALID,
        ).select_related(
            'pricesold__productsold__product__categorie_pos',
            'carte',
        )

    def calculer_totaux_par_moyen(self): ...
    def calculer_detail_ventes(self): ...
    def calculer_tva(self): ...
    def calculer_solde_caisse(self): ...
    def calculer_recharges(self): ...
    def calculer_adhesions(self): ...
    def calculer_remboursements(self): ...
    def calculer_habitus(self): ...
    def calculer_billets_soiree(self): ...
    def calculer_synthese_operations(self): ...
    def calculer_operateurs(self): ...

    def generer_rapport_complet(self):
        """Point d'entrée unique. Retourne le dict complet pour rapport_json."""
        return {
            "totaux_par_moyen": self.calculer_totaux_par_moyen(),
            "detail_ventes": self.calculer_detail_ventes(),
            "tva": self.calculer_tva(),
            "solde_caisse": self.calculer_solde_caisse(),
            "recharges": self.calculer_recharges(),
            "adhesions": self.calculer_adhesions(),
            "remboursements": self.calculer_remboursements(),
            "habitus": self.calculer_habitus(),
            "billets_soiree": self.calculer_billets_soiree(),
            "synthese_operations": self.calculer_synthese_operations(),
            "operateurs": self.calculer_operateurs(),
            "infos_legales": self._infos_legales(),
        }
```

##### Admin Unfold — Dashboard Rapports

Section **"Ventes"** dans la sidebar admin avec :
- **Rapports comptables** : liste des Z-tickets avec filtres date/PV/opérateur
- **Vue détail** : rendu HTML du rapport complet (pas juste le JSON brut)
- **Actions** : télécharger PDF, télécharger CSV, télécharger Excel, renvoyer par email
- **Dashboard widget** : résumé du jour (CA, nb transactions, top produits)

##### Exports

| Format | Bibliothèque | Usage |
|--------|-------------|-------|
| **PDF** | WeasyPrint (existant) | Document formel, impression, archivage |
| **CSV** | csv stdlib (existant) | Import comptabilité |
| **Excel** | openpyxl | Import comptabilité avancé, mise en forme |

**Template PDF** : document A4 structuré avec :
- En-tête : logo, raison sociale, SIRET, adresse, n° séquentiel
- Sections tabulaires pour chaque partie du rapport
- Pied de page : date génération, mention légale

##### Envoi automatique (Celery Beat)

```python
# laboutik/tasks.py

@shared_task
def generer_et_envoyer_rapport_periodique(periodicite, tenant_schema):
    """
    Génère et envoie le rapport comptable pour la période écoulée.
    Appelé par Celery Beat selon la périodicité configurée.

    periodicite : 'daily', 'weekly', 'monthly', 'yearly'
    """
    with schema_context(tenant_schema):
        config = LaboutikConfiguration.get_solo()
        # Calculer début/fin selon la périodicité
        # Générer le rapport via RapportComptableService
        # Créer le RapportComptable en DB
        # Exporter PDF + CSV + Excel
        # Envoyer par email aux destinataires configurés
```

**Configuration dans LaboutikConfiguration** :
```python
# Champs ajoutés :
rapport_emails = ArrayField(EmailField(), default=list)  # destinataires
rapport_periodicite = CharField(choices=[
    ('daily', 'Quotidien'),
    ('weekly', 'Hebdomadaire'),
    ('monthly', 'Mensuel'),
    ('yearly', 'Annuel'),
], default='daily')
fond_de_caisse = IntegerField(default=0)  # montant initial tiroir-caisse (centimes)
```

**Celery Beat schedule** (dans settings.py ou admin) :
```python
CELERY_BEAT_SCHEDULE = {
    'rapport-quotidien': {
        'task': 'laboutik.tasks.generer_et_envoyer_rapport_periodique',
        'schedule': crontab(hour=4, minute=0),  # 4h du matin
        'args': ('daily',),
    },
}
```

#### Fichiers à créer / modifier

| Fichier | Action | Contenu |
|---------|--------|---------|
| `laboutik/reports.py` | **Créer** | `RapportComptableService` (calcul complet) |
| `laboutik/models.py` | Modifier | Modèle `RapportComptable` + champs `LaboutikConfiguration` |
| `laboutik/migrations/` | Créer | Migration RapportComptable + config |
| `Administration/admin/laboutik.py` | Modifier | `RapportComptableAdmin` dans sidebar "Ventes" |
| `laboutik/templates/admin/rapport_comptable_detail.html` | **Créer** | Vue détail HTML dans l'admin |
| `laboutik/templates/laboutik/pdf/rapport_comptable.html` | **Créer** | Template PDF A4 formel |
| `laboutik/pdf.py` | Modifier | `generer_pdf_rapport_comptable()` |
| `laboutik/csv_export.py` | Modifier | `generer_csv_rapport_comptable()` |
| `laboutik/excel_export.py` | **Créer** | `generer_excel_rapport_comptable()` (openpyxl) |
| `laboutik/tasks.py` | Modifier | `generer_et_envoyer_rapport_periodique()` + Celery Beat |
| `laboutik/views.py` | Modifier | Connecter `cloturer()` au `RapportComptableService` |
| `tests/pytest/test_rapport_comptable.py` | **Créer** | Tests du service de calcul |

#### Ordre d'implémentation

1. **Modèle `RapportComptable`** + champs config + migration
2. **`reports.py`** : service de calcul (toutes les méthodes)
3. **Tests pytest** : chaque méthode du service séparément
4. **Admin Unfold** : `RapportComptableAdmin` lecture seule + vue détail HTML
5. **PDF** : template A4 formel + `generer_pdf_rapport_comptable()`
6. **CSV** : export enrichi
7. **Excel** : `generer_excel_rapport_comptable()` (openpyxl)
8. **Intégration clôture** : `cloturer()` crée un `RapportComptable` automatiquement
9. **Envoi automatique** : Celery Beat task + configuration périodicité
10. **Tests E2E** : Playwright admin

#### Points d'attention

- **Numéro séquentiel** : `unique_together = (point_de_vente, numero_sequentiel)`.
  Auto-incrémenté par PV, jamais réutilisé même après suppression.
- **TVA** : calculer sur les totaux (pas ligne par ligne) pour correspondre aux
  obligations déclaratives. `HT = TTC / (1 + taux/100)`, arrondi au centime.
- **Habitus sans N+1** : utiliser `values('carte').annotate(total=Sum('amount'))`
  au lieu de boucler sur chaque carte individuellement.
- **Billets soirée** : la "soirée" peut déborder sur le lendemain (concert jusqu'à 3h).
  Utiliser `Event.datetime` + marge de 6h pour capturer l'événement en cours.
- **Immutabilité** : un `RapportComptable` créé ne doit **jamais** être modifié.
  Si erreur, créer un rapport correctif avec référence au rapport original.
- **openpyxl** : vérifier qu'il est dans `pyproject.toml` ou l'ajouter.
- **Celery Beat multi-tenant** : la tâche doit itérer sur les tenants actifs
  ou être programmée par tenant via l'admin.

---

### Phase Menu Ventes — Gestion des ventes côté caisse (tactile)

#### Vision

Un menu **"Ventes"** accessible depuis l'interface caisse (burger menu ou bouton footer)
qui donne au caissier un accès rapide et tactile à la gestion courante :
ticket X temporaire, clôture Z, liste des ventes avec corrections, fond de caisse,
et sortie de liquide pour dépôt bancaire.

**Deux interfaces complémentaires** :
- **Menu Ventes (caisse tactile)** : cette phase — pour le caissier sur le terrain
- **Admin Unfold "Ventes" (desktop)** : Phase Rapports Comptables — pour le gestionnaire

Les deux utilisent le même `RapportComptableService` (Phase Rapports Comptables).

#### Ticket X vs Ticket Z

| | Ticket X (temporaire) | Ticket Z (clôture) |
|---|---|---|
| **Quand** | N'importe quand en cours de service | En fin de journée |
| **Effet** | Aucun (lecture seule) | Ferme les tables, annule les commandes ouvertes |
| **Légal** | Pas une pièce comptable | Pièce comptable numérotée séquentiellement |
| **Impression** | Optionnelle | Obligatoire (archivage) |
| **Données** | Mêmes calculs que le Z, sur la période en cours | Idem, mais figé et enregistré en DB |
| **Modèle** | Pas de `RapportComptable` créé | Crée un `RapportComptable` + `ClotureCaisse` |

**Le Ticket X est un "aperçu" du Ticket Z** — même service de calcul, pas de commit.

#### Structure du menu Ventes

Accessible depuis le **burger menu** de l'interface caisse (en haut à gauche).
Chaque sous-menu est un écran HTMX (partial swap dans la zone centrale).

```
Menu Ventes (burger menu → section "Ventes")
│
├─ 📊 Récap' en cours (Ticket X)
│   Aperçu temps réel du service en cours — pas de clôture.
│   Sous-onglets : Toutes caisses │ Par point de vente │ Par moyen de paiement
│
├─ 🧾 Clôturer (Ticket Z)
│   Génère le rapport comptable officiel, ferme le service.
│   Impression + envoi email. Numéro séquentiel.
│
├─ 📋 Liste des ventes
│   Historique de toutes les transactions du service en cours.
│   Filtres : PV, moyen de paiement, opérateur.
│   Actions : corriger moyen de paiement, ré-imprimer ticket client.
│
├─ 💰 Fond de caisse
│   Saisir ou modifier le montant initial du tiroir-caisse.
│
└─ 🏦 Sortie de caisse
    Documenter un retrait d'espèces pour dépôt bancaire.
    Ventilation par coupure (billets 50€, 20€, 10€, 5€ + pièces).
```

#### 1. Récap' en cours (Ticket X)

Calcul identique au Ticket Z mais **sans créer de ClotureCaisse ni de RapportComptable**.
Le résultat est affiché à l'écran, avec option d'impression.

**3 vues** (onglets HTMX) :

##### a. Toutes caisses

Synthèse agrégée de tous les PV du tenant pour la période en cours.

```
┌──────────────────────────────────────────────────┐
│  📊 RÉCAP' EN COURS — Toutes caisses              │
│  Service depuis 08:00 — Il y a 4h32              │
│                                                    │
│  ┌──────────┬───────────┬─────────┬───────────┐   │
│  │ Espèces  │ CB        │ NFC     │ TOTAL     │   │
│  │ 245,00 € │ 1 230,50€ │ 890,00€ │ 2 365,50€│   │
│  └──────────┴───────────┴─────────┴───────────┘   │
│                                                    │
│  Transactions : 142  │  Cartes NFC : 47           │
│  Billets soirée : 23/50 (Concert Rock)             │
│                                                    │
│  [Par PV]  [Par moyen]  [Imprimer Ticket X]        │
└──────────────────────────────────────────────────┘
```

##### b. Par point de vente

Un bloc par PV avec ses totaux.

```
┌─ Bar ────────────────────────────────────────────┐
│  Espèces: 120€  │  CB: 450€  │  NFC: 380€       │
│  Transactions: 67  │  Total: 950€                 │
├─ Restaurant ─────────────────────────────────────┤
│  Espèces: 125€  │  CB: 780€  │  NFC: 510€       │
│  Transactions: 75  │  Total: 1 415€              │
└──────────────────────────────────────────────────┘
```

##### c. Par moyen de paiement

Détail croisé type d'opération × moyen.

```
┌──────────────┬──────────┬────────┬────────┬────────┐
│              │ Espèces  │ CB     │ NFC    │ Total  │
├──────────────┼──────────┼────────┼────────┼────────┤
│ Ventes       │ 200,00€  │ 900€   │ 700€   │ 1800€  │
│ Recharges    │ 45,00€   │ 280€   │ —      │ 325€   │
│ Adhésions    │ 0,00€    │ 50€    │ 140€   │ 190€   │
│ Remboursement│ -30,00€  │ —      │ —      │ -30€   │
├──────────────┼──────────┼────────┼────────┼────────┤
│ TOTAL        │ 215,00€  │ 1230€  │ 840€   │ 2285€  │
└──────────────┴──────────┴────────┴────────┴────────┘
```

**Actions ViewSet** :
```python
# CaisseViewSet
@action(detail=False, methods=['GET'], url_path='recap_en_cours')
def recap_en_cours(self, request):
    """Ticket X — récap' sans clôture."""
    vue = request.GET.get('vue', 'toutes')  # toutes, par_pv, par_moyen
    # Appelle RapportComptableService.generer_rapport_complet() sans sauvegarder
    ...
```

#### 2. Liste des ventes

Historique scrollable des transactions du service en cours.
Chaque ligne est cliquable pour voir le détail et agir.

```
┌──────────────────────────────────────────────────────────┐
│  📋 LISTE DES VENTES — depuis 08:00                       │
│                                                            │
│  Filtres : [Tous PV ▾] [Tous moyens ▾] [Tous opér. ▾]    │
│                                                            │
│  ┌─ 12:34 ─────────────────────────────────────────────┐  │
│  │ #127  Bière ×2, Pizza ×1    │  CB   │  22,50€      │  │
│  │ Bar — Opérateur: Marie      │       │  [Détail →]  │  │
│  └─────────────────────────────────────────────────────┘  │
│  ┌─ 12:31 ─────────────────────────────────────────────┐  │
│  │ #126  Adhésion annuelle ×1  │  ESP  │  20,00€      │  │
│  │ Adhésions — Marie           │       │  [Détail →]  │  │
│  └─────────────────────────────────────────────────────┘  │
│  ┌─ 12:28 ─────────────────────────────────────────────┐  │
│  │ #125  Coca ×3, Eau ×2      │  NFC  │  11,50€      │  │
│  │ Bar — Pierre                │       │  [Détail →]  │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                            │
│  [← Plus ancien]                           [Plus récent →] │
└──────────────────────────────────────────────────────────┘
```

**Vue détail d'une vente** (clic sur une ligne) :

```
┌──────────────────────────────────────────────────────────┐
│  🧾 VENTE #127 — 12:34 — Bar — Marie                     │
│                                                            │
│  Bière pression (Demi)    ×2    7,00€                     │
│  Pizza Margherita         ×1    8,50€                     │
│  ──────────────────────────────────────                   │
│  Total                          22,50€                    │
│  Payé en : Carte bancaire                                 │
│                                                            │
│  ┌────────────────────┐  ┌────────────────────┐           │
│  │ ✏️ Corriger moyen  │  │ 🖨️ Ré-imprimer    │           │
│  └────────────────────┘  └────────────────────┘           │
│                                                            │
│  [← Retour à la liste]                                    │
└──────────────────────────────────────────────────────────┘
```

##### Correction du moyen de paiement

**Uniquement pour espèces ↔ CB ↔ chèque.** Pas de modification du cashless ni des ventes en ligne
(ces transactions sont validées au moment du paiement et liées à des Transactions fedow_core).

```
┌──────────────────────────────────────────────────────────┐
│  ✏️ CORRIGER LE MOYEN DE PAIEMENT — Vente #127           │
│                                                            │
│  Moyen actuel : Carte bancaire                            │
│                                                            │
│  Changer en :                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐               │
│  │ ESPÈCES  │  │   CB ✓   │  │  CHÈQUE  │               │
│  └──────────┘  └──────────┘  └──────────┘               │
│                                                            │
│  Raison (obligatoire) :                                   │
│  ┌──────────────────────────────────────────┐             │
│  │ Erreur de saisie, client a payé en espèce │            │
│  └──────────────────────────────────────────┘             │
│                                                            │
│  [ANNULER]                    [CONFIRMER LA CORRECTION]    │
└──────────────────────────────────────────────────────────┘
```

**Backend** :
```python
# PaiementViewSet
@action(detail=False, methods=['POST'], url_path='corriger_moyen_paiement')
def corriger_moyen_paiement(self, request):
    """
    Corrige le moyen de paiement d'une vente passée.
    / Corrects the payment method of a past sale.

    RESTRICTIONS :
    - Uniquement espèces ↔ CB ↔ chèque (fiduciaires)
    - PAS de modification NFC (Transaction fedow_core liée)
    - PAS de modification vente en ligne
    - Raison obligatoire (traçabilité)
    - Log d'audit dans LigneArticle.metadata ou modèle dédié
    """
```

**Modèle de traçabilité** : chaque correction est enregistrée :
```python
class CorrectionPaiement(models.Model):
    """Trace d'audit pour les corrections de moyen de paiement."""
    uuid = models.UUIDField(primary_key=True, default=uuid4)
    ligne_article = models.ForeignKey(LigneArticle, on_delete=models.PROTECT)
    ancien_moyen = models.CharField(max_length=10)
    nouveau_moyen = models.CharField(max_length=10)
    raison = models.TextField()
    operateur = models.ForeignKey(TibilletUser, on_delete=models.SET_NULL, null=True)
    datetime = models.DateTimeField(auto_now_add=True)
```

##### Ré-impression ticket client

Reconstruit le ticket de vente à partir des `LigneArticle` liées à la commande
et l'envoie à l'imprimante via `imprimer_async.delay()`.

#### 3. Fond de caisse

Saisie du montant initial du tiroir-caisse en début de service.
Modifiable à tout moment (le dernier montant saisi fait foi).

```
┌──────────────────────────────────────────────────────────┐
│  💰 FOND DE CAISSE                                        │
│                                                            │
│  Montant actuel : 150,00 €                                │
│  Dernière modification : 08:02 par Marie                  │
│                                                            │
│  Nouveau montant :                                        │
│  ┌───────────────────────────────────┐                    │
│  │              150,00               │ €                  │
│  └───────────────────────────────────┘                    │
│  (inputmode="decimal", autofocus, 80px height)            │
│                                                            │
│  [ANNULER]                         [ENREGISTRER]           │
└──────────────────────────────────────────────────────────┘
```

**Stockage** : champ `fond_de_caisse` (IntegerField, centimes) sur `LaboutikConfiguration`
ou sur un modèle `ServiceCaisse` (si on veut l'historique par service).

#### 4. Sortie de caisse (retrait espèces pour dépôt bancaire)

Document de retrait avec ventilation par coupure. Crée une pièce justificative
pour le dépôt en banque.

```
┌──────────────────────────────────────────────────────────┐
│  🏦 SORTIE DE CAISSE — Retrait espèces                   │
│                                                            │
│  Ventilation des coupures :                               │
│  ┌────────────┬───────────┬───────────────┐              │
│  │ Coupure    │ Quantité  │ Sous-total    │              │
│  ├────────────┼───────────┼───────────────┤              │
│  │ 50 €       │ [  0  ]   │     0,00 €    │              │
│  │ 20 €       │ [  5  ]   │   100,00 €    │              │
│  │ 10 €       │ [  2  ]   │    20,00 €    │              │
│  │  5 €       │ [  0  ]   │     0,00 €    │              │
│  │  2 €       │ [  3  ]   │     6,00 €    │              │
│  │  1 €       │ [  2  ]   │     2,00 €    │              │
│  │ 0,50 €     │ [  4  ]   │     2,00 €    │              │
│  │ 0,20 €     │ [  0  ]   │     0,00 €    │              │
│  │ 0,10 €     │ [  0  ]   │     0,00 €    │              │
│  │ 0,05 €     │ [  0  ]   │     0,00 €    │              │
│  │ 0,02 €     │ [  0  ]   │     0,00 €    │              │
│  │ 0,01 €     │ [  0  ]   │     0,00 €    │              │
│  ├────────────┼───────────┼───────────────┤              │
│  │ TOTAL      │           │   130,00 €    │              │
│  └────────────┴───────────┴───────────────┘              │
│                                                            │
│  Note (optionnelle) :                                     │
│  ┌──────────────────────────────────────────┐             │
│  │ Dépôt banque semaine 12                   │            │
│  └──────────────────────────────────────────┘             │
│                                                            │
│  [ANNULER]         [IMPRIMER JUSTIFICATIF]  [ENREGISTRER] │
└──────────────────────────────────────────────────────────┘
```

**Modèle** :
```python
class SortieCaisse(models.Model):
    """
    Retrait d'espèces du tiroir-caisse pour dépôt bancaire.
    / Cash withdrawal from register for bank deposit.
    """
    uuid = models.UUIDField(primary_key=True, default=uuid4)
    point_de_vente = models.ForeignKey(PointDeVente, on_delete=models.PROTECT)
    operateur = models.ForeignKey(TibilletUser, on_delete=models.SET_NULL, null=True)
    datetime = models.DateTimeField(auto_now_add=True)
    montant_total = models.IntegerField()  # centimes
    ventilation = models.JSONField()
    # {"5000": 0, "2000": 5, "1000": 2, "500": 0, "200": 3, "100": 2,
    #  "50": 4, "20": 0, "10": 0, "5": 0, "2": 0, "1": 0}
    note = models.TextField(blank=True, default='')
```

**Impact sur le rapport comptable** :
Les `SortieCaisse` de la période apparaissent dans le solde de caisse :
```
Fond de caisse initial    150,00 €
+ Entrées espèces         245,00 €
- Sorties de caisse       -130,00 €   ← NOUVEAU
= Solde théorique         265,00 €
```

#### Responsive — desktop vs mobile

##### Desktop (> 1022px)

Le menu Ventes s'ouvre dans la **zone centrale** (comme l'overlay multi-tarif),
le panier reste visible à droite. Le caissier peut voir ses ventes tout en
ayant le contexte du panier en cours.

```
┌──────────┬────────────────────────────┬───────────────┐
│ MENU     │ CONTENU VENTES             │  PANIER       │
│ VENTES   │ (récap / liste / fond /    │  (visible)    │
│ (sidebar)│  sortie)                    │               │
│          │                            │               │
│ [Récap'] │  ... contenu actif ...     │               │
│ [Liste]  │                            │               │
│ [Fond]   │                            │               │
│ [Sortie] │                            │               │
│ [Clôture]│                            │               │
│          │                            │               │
│ [RETOUR] │                            │               │
├──────────┴────────────────────────────┴───────────────┤
│ FOOTER (identique)                                     │
└────────────────────────────────────────────────────────┘
```

##### Mobile (< 599px)

Menu plein écran, navigation par onglets en haut.

```
┌────────────────────────────────────┐
│ [←] VENTES                         │
├────────────────────────────────────┤
│ [Récap'] [Liste] [Fond] [Sortie]  │
├────────────────────────────────────┤
│                                    │
│  ... contenu actif plein écran ... │
│                                    │
│                                    │
└────────────────────────────────────┘
```

#### Actions ViewSet

| Action | Méthode | URL | Description |
|--------|---------|-----|-------------|
| `recap_en_cours()` | GET | `/caisse/recap_en_cours/?vue=toutes` | Ticket X (3 sous-vues) |
| `liste_ventes()` | GET | `/caisse/liste_ventes/?pv=&moyen=&page=` | Historique scrollable |
| `detail_vente()` | GET | `/caisse/detail_vente/?ligne_uuid=` | Détail d'une vente |
| `corriger_moyen_paiement()` | POST | `/paiement/corriger_moyen_paiement/` | Correction ESP↔CB↔CHQ |
| `reimprimer_ticket()` | POST | `/caisse/reimprimer_ticket/` | Ré-impression via Celery |
| `fond_de_caisse()` | GET/POST | `/caisse/fond_de_caisse/` | Saisie/modification |
| `sortie_de_caisse()` | GET/POST | `/caisse/sortie_de_caisse/` | Retrait avec ventilation |

#### Templates (partials HTMX)

| Template | Rôle |
|----------|------|
| `hx_ventes_menu.html` | Menu latéral ou onglets (HTMX swap zone centrale) |
| `hx_recap_en_cours.html` | Récap' Ticket X (3 sous-vues) |
| `hx_liste_ventes.html` | Liste paginée des transactions |
| `hx_detail_vente.html` | Détail d'une vente + actions |
| `hx_corriger_moyen.html` | Formulaire correction moyen de paiement |
| `hx_fond_de_caisse.html` | Formulaire fond de caisse |
| `hx_sortie_de_caisse.html` | Formulaire sortie avec ventilation coupures |

#### Modèles à créer

| Modèle | Rôle |
|--------|------|
| `CorrectionPaiement` | Trace d'audit des corrections (ancien/nouveau moyen, raison, opérateur) |
| `SortieCaisse` | Retrait espèces avec ventilation par coupure (JSON) |

#### Champs à ajouter

| Modèle | Champ | Type | Usage |
|--------|-------|------|-------|
| `LaboutikConfiguration` | `fond_de_caisse` | IntegerField (centimes) | Montant initial tiroir |

#### Ordre d'implémentation

1. **Modèles** : `CorrectionPaiement`, `SortieCaisse`, champ `fond_de_caisse` + migrations
2. **Actions ViewSet** : `recap_en_cours()`, `liste_ventes()`, `detail_vente()`
3. **Templates** : `hx_recap_en_cours.html`, `hx_liste_ventes.html`, `hx_detail_vente.html`
4. **Correction** : `corriger_moyen_paiement()` + `hx_corriger_moyen.html` + modèle audit
5. **Fond de caisse** : `fond_de_caisse()` + template
6. **Sortie de caisse** : `sortie_de_caisse()` + template + intégration rapport comptable
7. **Ré-impression** : `reimprimer_ticket()` → `imprimer_async.delay()`
8. **Menu navigation** : `hx_ventes_menu.html` (sidebar desktop, onglets mobile)
9. **Tests** : pytest (calculs, corrections, audit trail) + Playwright (navigation, UX)

#### Points d'attention

- **Correction limitée** : uniquement espèces ↔ CB ↔ chèque. Le NFC est lié à une Transaction
  fedow_core (débit/crédit wallet) — modifier le moyen créerait une incohérence comptable.
- **Traçabilité obligatoire** : chaque correction crée un `CorrectionPaiement` avec raison.
  Pas de modification silencieuse. L'ancien moyen est conservé pour l'audit.
- **Sortie de caisse dans le rapport** : le total des sorties est déduit du solde théorique
  du tiroir dans le rapport comptable (Ticket Z).
- **Pagination** : la liste des ventes peut être longue (festival = 500+ ventes/jour).
  Utiliser la pagination Django avec `hx-trigger="revealed"` pour le scroll infini HTMX.
- **Permissions** : les corrections et la clôture Z nécessitent une carte primaire avec
  `edit_mode=True`. La liste des ventes et le Ticket X sont accessibles à tout opérateur.

---

### Phase 3.3 — Stress test + verify_transactions

Prérequis de Phase 6-7 ET des checkpoints sécurité.

**Ce qui est prévu** :
- Management command `verify_transactions` :
  - Vérifie que la séquence globale n'a pas de trous
  - Vérifie que chaque Transaction a un sender/receiver/asset valide
  - Vérifie que la somme des Token correspond aux Transaction
  - Usage : `docker exec lespass_django poetry run python manage.py verify_transactions [--tenant=mon-lieu]`
- Stress test `tests/stress/test_charge_festival.py` : 4 tenants, 2000 tx concurrentes

### Phase 6 — Migration des données

- Management command `import_fedow_data` (dry-run par défaut, `--commit` pour appliquer)
- Management command `import_laboutik_data`
- Management command `verify_import`
- Ordre d'import Fedow : Asset → Wallet → Card → Token → Transaction → Federation
- Ordre d'import LaBoutik : CategorieProduct → Product (POS) → PointDeVente → CartePrimaire → Table → CommandeSauvegarde

### Phase 7 — Consolidation et nettoyage

- Management command `recalculate_hashes` → `hash` NOT NULL + UNIQUE
- ~~Supprimer `utils/mockData.py`, `utils/dbJson.py`, `utils/mockDb.json`~~ ✅ FAIT (nettoyage anticipé)
- `utils/method.py` nettoyé (seule `extraire_uuids_articles()` conservée, imports mock supprimés)
- Supprimer `fedow_connect/fedow_api.py` (remplacé par `fedow_core/services.py`)
- Supprimer `fedow_connect.Asset`, `fedow_connect.FedowConfig`
- Supprimer ou archiver `fedow_public.AssetFedowPublic`

### À définir avec le mainteneur

_(à compléter)_

---

## Annexe — Fichiers clés

| Fichier | Rôle |
|---------|------|
| `laboutik/models.py` | Modèles POS : PointDeVente, CartePrimaire, Table, Commandes, Clôture |
| `laboutik/views.py` | ViewSets : CaisseViewSet, PaiementViewSet, CommandeViewSet (~3100 lignes) |
| `laboutik/serializers.py` | Validation DRF de tous les POST |
| `laboutik/urls.py` | Routing DRF |
| `laboutik/tasks.py` | Celery : envoi rapport clôture |
| `laboutik/printing/` | Module d'impression modulaire (Phase Impression) |
| `laboutik/utils/method.py` | Extraction UUIDs articles depuis POST |
| `laboutik/utils/test_helpers.py` | `reset_carte()` pour les tests |
| `laboutik/management/commands/create_test_pos_data.py` | Données de test POS |
| `laboutik/templates/cotton/articles.html` | Grille d'articles (tuiles) |
| `laboutik/templates/cotton/addition.html` | Panier |
| `laboutik/templates/cotton/read_nfc.html` | Lecteur NFC |
| `laboutik/templates/cotton/categories.html` | Sidebar catégories |
| `laboutik/templates/cotton/footer.html` | Footer (RESET/CHECK CARTE/VALIDER) |
| `laboutik/templates/cotton/header.html` | Header + menu burger |
| `laboutik/templates/laboutik/views/common_user_interface.html` | Interface principale POS |
| `laboutik/templates/laboutik/partial/hx_*.html` | Partials HTMX (17 fichiers) |
| `laboutik/static/laboutik/js/nfc.js` | Lecture NFC + simulation dev |
| `laboutik/static/laboutik/js/articles.js` | Grille articles, manageKey() |
| `laboutik/static/laboutik/js/addition.js` | Panier, total, formulaire |
| `laboutik/static/laboutik/js/tibilletUtils.js` | eventsOrganizer |
| `laboutik/static/laboutik/js/tarif.js` | Overlay multi-tarif + prix libre |
| `fedow_core/models.py` | Asset, Token, Transaction, Federation |
| `fedow_core/services.py` | WalletService, TransactionService, AssetService |
| `Administration/admin/laboutik.py` | Admin Unfold POS |
| `tests/pytest/test_pos_views_data.py` | Tests unitaires vues POS |
| `tests/playwright/tests/laboutik/` | Tests E2E Playwright POS |
