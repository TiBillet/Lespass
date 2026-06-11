# SPEC — Scénario S5 : LaBoutik V2 intégré à Lespass, branché sur Fedow distant

> ⚠️ **RÉVISÉ 2026-06-10 — le scénario acté final est S6** (hybride additif :
> fedow_core local pour les monnaies locales, interop legacy en ajout pour le
> FED/fédérés). Cette SPEC reste la référence pour les décisions D3-D6 et le
> contexte, mais le découpage opérationnel est remplacé par
> **[ROADMAP.md](./ROADMAP.md)** (lots C-A → C-D, 8-10 sessions).
> D1 (handshake cashless) et D2 (extension FedowAPI) sont DIFFÉRÉS — la
> phase 1 n'en a pas besoin (signature user, client existant). Cf. docs 07-09.

Date : 2026-06-10
Statut : remplacée par ROADMAP.md (S6) — conservée pour l'historique
Recherche amont : docs 01 à 05 + audit (02/02b) de ce hub.

> Note de cadrage : le hub s'appelle `FEDOW_IMPORT` pour l'historique, mais le
> chantier acté n'importe PAS Fedow. Fedow standalone reste en place, tel quel.
> Le chantier consiste à porter la caisse LaBoutik V2 dans ce repo et à la
> câbler sur le Fedow distant via HTTP.

---

## 1. Décision et architecture cible

```
                      ┌────────────────────────────────────────┐
                      │  Fedow standalone (inchangé)           │
                      │  fedow.tibillet.coop — SQLite          │
                      │  wallets, tokens, transactions, FED    │
                      └────────▲───────────────▲───────────────┘
                  HTTP + RSA   │               │   HTTP + RSA
              (inchangé)       │               │   (fedow_connect.FedowAPI,
                               │               │    étendu pour le POS)
        ┌──────────────────────┴───┐   ┌───────┴────────────────────────────┐
        │  LaBoutik V1 (serveurs   │   │  Lespass (ce repo)                 │
        │  externes, anciens       │   │  ├─ BaseBillet (flux existants V1) │
        │  tenants) — INTOUCHÉ     │   │  ├─ fedow_connect (client, étendu) │
        └──────────────────────────┘   │  └─ laboutik (POS V2, TENANT_APPS) │
                                       │     └─ caisse des NOUVEAUX tenants │
                                       └────────────────────────────────────┘
```

- **Un seul moteur monétaire** : le Fedow standalone. Un seul réseau FED,
  cartes partagées entre anciens et nouveaux lieux.
- **La caisse des nouveaux tenants** est l'app `laboutik` portée depuis
  `lespass-main` (~15 000 lignes), intégrée à ce repo en TENANT_APPS.
- **Sa couche cashless parle au Fedow distant** via `fedow_connect.FedowAPI`,
  étendu des méthodes POS manquantes.
- **Les adhésions ne passent plus par les assets Fedow** pour les tenants à
  caisse V2 : la caisse lit/écrit `BaseBillet.Membership` en DB locale.

## 2. Objectifs / Non-objectifs

### Objectifs
1. Les nouveaux tenants disposent d'une caisse complète (POS tactile, cashless
   NFC, clôtures, impression, comptabilité) intégrée à Lespass.
2. Leurs cartes/wallets vivent sur le Fedow existant : fédération native avec
   le réseau actuel.
3. Zéro régression pour l'existant : tenants V1, LaBoutik V1, instance `.re`,
   webhooks Stripe de Fedow — rien ne change pour eux.

### Non-objectifs (explicitement hors scope)
- ❌ Import de Fedow dans Lespass (code ou données) — voir doc 04 (S4) si un
  jour la phase infra est actée.
- ❌ Portage de `fedow_core` V2 (lespass-main) — ni modèles, ni services.
- ❌ Migration des tenants existants (ils restent sur LaBoutik V1).
- ❌ Couche d'abstraction « wallet provider » — le POS appelle `FedowAPI`
  directement, comme BaseBillet (anti sur-ingénierie ; un éventuel
  désamorçage S4 remplacera ces call sites comme les autres).
- ❌ Toute modification du serveur Fedow, sauf si un trou de contrat est
  découvert (à remonter au mainteneur avant d'agir).

## 3. Décisions de conception

### D1 — Lespass devient le « serveur cashless » de la place
Les endpoints POS de Fedow (vente, refund carte, badge, retrieve carte avec
tokens) exigent `HasKeyAndPlaceSignature` : une signature RSA par la clé du
*serveur cashless* enregistrée au handshake. Aujourd'hui ce rôle est tenu par
LaBoutik V1. Pour un tenant à caisse V2, **Lespass joue ce rôle** :
- au moment de l'activation de la caisse, Lespass exécute lui-même le flow
  `link_cashless_to_place` → `handshake` (les deux endpoints existent côté
  Fedow, le client `PlaceFedow.link_cashless_to_place` existe déjà) ;
- la paire RSA « cashless » du tenant et l'`OrganizationAPIKey` retournée sont
  stockées dans `FedowConfig` (nouveaux champs, chiffrés Fernet comme
  `fedow_place_admin_apikey`).

### D2 — Extension de `fedow_connect.FedowAPI` (pas de nouveau client)
`FedowAPI` couvre les flux Lespass mais pas les flux POS. Méthodes à ajouter
(toutes adossées à des endpoints Fedow existants et prouvés par LaBoutik V1) :

| Nouvelle méthode client | Endpoint Fedow | Permission |
|---|---|---|
| `NFCcard.retrieve_by_tag_id(tag_id)` (carte + tokens) | GET `/card/<first_tag_id>/` | HasKeyAndPlaceSignature |
| `transaction.sale_from_card(...)` (1 appel par asset de la cascade) | POST `/transaction/` (action SALE) | HasKeyAndPlaceSignature |
| `transaction.refill_card(...)` (recharge POS espèces/CB) | POST `/transaction/` (CREATION/REFILL) | HasKeyAndPlaceSignature |
| `NFCcard.refund_and_void(card, ...)` (vidage fin de festival) | POST `/card/refund` | HasKeyAndPlaceSignature |
| `NFCcard.badge(card, asset)` | POST `/card/badge` | HasKeyAndPlaceSignature |
| `place.handshake_cashless(temp_key)` (cf. D1) | POST `/place/handshake` | HasAPIKey (temp) |
| (option, lot de cartes) `NFCcard.create_batch(...)` | POST `/card/` | HasKeyAndPlaceSignature |

La signature utilise la clé cashless de D1 (pattern `_post`/`_get` existant,
paramètre de signature à généraliser : aujourd'hui ils signent avec la clé du
*user*, il faut pouvoir signer avec la clé cashless du tenant).

### D3 — Adhésions et badges hors assets Fedow (décision du 2026-06-10)
- Vérification d'adhésion au scan : requête locale `BaseBillet.Membership`
  (l'email/wallet du porteur de carte est résolu via le scan Fedow).
- Vente d'adhésion en caisse : création directe de `Membership` +
  `LigneArticle` en DB locale. **Plus de transaction SUB Fedow, plus de
  webhook `Membership_fwh`** pour les tenants à caisse V2.
- Le webhook `Membership_fwh` reste en place pour les tenants LaBoutik V1.
- Les badges « pointeuse » à valeur temps (TIM) restent des assets Fedow
  (c'est de la monnaie temps) ; le badge « contrôle d'accès » sans valeur
  utilise l'endpoint `/card/badge`.

### D4 — Rapports, clôtures, impression : données locales d'abord
Le POS enregistre déjà chaque vente en local (`LigneArticle`, moyens de
paiement). Les rapports/clôtures/tickets se construisent sur ces données
locales. Les lectures `fedow_core.Asset/Token` du code V2 (reports.py,
printing/formatters.py) sont remplacées par : libellés d'assets mis en cache
localement (cf. D5) + totaux croisés optionnels via l'API
(`retrieve_total_by_place`). Jamais d'appel HTTP dans une boucle de rendu de
ticket.

### D5 — Référentiel d'assets : `fedow_public.AssetFedowPublic`
Le POS a besoin de connaître les assets acceptés (libellés, catégories,
couleurs de boutons). On réutilise l'app tampon existante
`AssetFedowPublic` (SHARED_APPS), synchronisée via
`asset.get_accepted_assets()` (existant). Pas de nouveau modèle.

### D6 — La cascade de paiement reste côté POS
L'ordre de cascade (cadeau → local → FED) est décidé par le POS à partir des
tokens retournés au scan, puis exécuté en N appels `sale_from_card` (un par
asset), séquentiels. **En cas d'échec d'un appel au milieu de la cascade :
la vente reste ouverte avec un reste à payer** (même modèle qu'un TPE CB qui
échoue) — pas de compensation distribuée, pas de rollback cross-réseau.

## 4. Inventaire de recâblage (lespass-main → ce repo)

Call sites `fedow_core` du laboutik V2 relevés le 2026-06-10 :

| Flux POS | Code V2 actuel (lespass-main) | Cible S5 |
|---|---|---|
| Scan carte + soldes | `CarteService.scanner_carte`, `WalletService.obtenir_solde/obtenir_tous_les_soldes/obtenir_total_en_centimes` (views.py:5557-6324, 7220) | `NFCcard.retrieve_by_tag_id` (1 appel, tokens inclus dans la réponse) |
| Vente cascade | `TransactionService.creer_vente` ×8 sites (views.py:5793-7033) | `transaction.sale_from_card` par asset (D6) |
| Recharge POS | `TransactionService.creer_recharge` (views.py:4726) | `transaction.refill_card` |
| Adhésion vendue en caisse + fusion carte | `WalletService.fusionner_wallet_ephemere` (views.py:4346) | `Membership` local (D3) ; la liaison carte↔user reste le flux Lespass existant (`linkwallet_*`) |
| Remboursement/vidage | `WalletService.rembourser_en_especes`, `get_or_create_wallet_tenant` (views.py:7392-7439) | `NFCcard.refund_and_void` |
| Liste des assets | `AssetService.obtenir_assets_accessibles` (views.py:5542, 6505) | `AssetFedowPublic` local (D5) |
| Rapports/impression | lectures `Asset`/`Token` (reports.py:138-625, printing/formatters.py:228) | données locales + libellés `AssetFedowPublic` (D4) |
| Fixtures de dev | create_test_pos_data.py (~10 sites) | à réécrire contre un Fedow de dev (`flush.sh` Fedow + demo_data) |
| Webhook recharge en ligne | `RefillService.process_cashless_refill` (ApiBillet V2) | hors scope POS — la recharge en ligne reste le flux V1 existant (`get_federated_token_refill_checkout`) |

## 5. Garde-fous

1. **Aucune modification des flux V1** : `fedow_connect` est étendu par AJOUT
   uniquement ; les méthodes existantes et `FedowConfig` actuel ne changent pas
   de comportement. Les tenants LaBoutik V1 ne voient aucune différence.
2. **Onboarding verrouillé** (finding audit) : l'endpoint
   `Onboard_laboutik`/`link_cashless_to_place` ne doit pas pouvoir écraser le
   handshake cashless d'un tenant à caisse V2 (et inversement). Un tenant a UNE
   caisse : V1 externe OU V2 intégrée — flag explicite sur `FedowConfig`,
   transitions uniquement par action admin consciente.
3. **Idempotence des POST POS** : un timeout réseau suivi d'un retry ne doit
   pas créer une double vente. Avant tout retry automatique, vérification de
   la transaction via l'API (ou pas de retry automatique : l'opérateur rescanne
   et le POS réaffiche le solde). À trancher en conception détaillée du C-03.
4. **UX d'erreur réseau** : tout appel HTTP du POS a un timeout court, un
   message clair, et ne bloque jamais la vente espèces/CB (qui est 100 % locale).
5. **Pas d'appel HTTP dans les boucles** (rendu de grilles, tickets, rapports).
6. **drift=0 vérifié** : confirmer le résultat du `reconcile_tokens` passé en
   prod dans la nuit du 10-11/06 (requête §10.1 du doc DRIFT) avant le premier
   tenant pilote.

## 6. Découpage en chantiers

> **Révision 2026-06-10 (revue branche `new_pairing_and_nfc`, doc 06)** :
> le périmètre du portage s'élargit — s'ajoutent l'app `discovery` (appairage
> PIN des terminaux), l'app `inventaire` (StockService, coquille vide en V1),
> les champs AuthBillet 0024+0025 (wallet_name/public_pem, terminal_role +
> proxy TermUser), `LaBoutikAPIKey`, et la dépendance `django-cotton` (seul
> ajout Python). La décision D3 (adhésion locale au scan) est **déjà
> implémentée** sur cette branche. Les deux clients matériels
> (Android Cordova, Pi/desktop) ne sont PAS touchés par le câblage S5
> (ils n'échangent que PIN, clé API et tag_id contre du HTML).
> Estimation détaillée : doc 06 — **total 15 à 22 sessions**.

| # | Chantier | Contenu | Estimation | Dépend de |
|---|---|---|---|---|
| C-01 | **Client POS dans fedow_connect** | Nouvelles méthodes FedowAPI (D2), signature par clé cashless dans `_post`/`_get`, 4 champs FedowConfig + migration, handshake interne (D1). Tests pytest contre un Fedow de dev docker. | 2-3 sessions | — |
| C-02a | **Socle données** | `laboutik/models.py` + `inventaire` + `discovery` + champs AuthBillet (migrations fraîches V1) + `LaBoutikAPIKey` + settings (TENANT_APPS, django-cotton) + admin. | 2 sessions | — |
| C-02b | **Socle vues/UI** | `views.py` (~9 200 l.), serializers, templates cotton, static JS, urls. Livrable : caisse fonctionnelle espèces/CB SANS cashless. | 2-3 sessions | C-02a |
| C-02c | **Appairage & terminaux** | Endpoint discovery claim, TermUser, auth bridge ; hébergement des dossiers clients (aucune modif de leur code). | 1-2 sessions | C-02a |
| C-03 | **Câblage cashless du POS** | ~35 call sites → FedowAPI : scan/soldes, cascade de vente (D6) + complément + 2e carte NFC, recharge, vidage/refund, fusion adhésion (`linkwallet_card_number` signé par la clé user détenue par Lespass). UX erreur réseau + garde-fou idempotence. Spike de mapping sémantique en ouverture. | 3-4 sessions | C-01, C-02b |
| C-04 | **Adhésion au scan et en caisse** | D3 déjà en place côté lecture ; vérifier la vente d'adhésion locale, purger les résidus assets SUB. | 1 session | C-02b |
| C-05 | **Onboarding tenant caisse V2** | Activation de la caisse dans l'admin (module), handshake auto (D1), verrouillage V1/V2 (garde-fou 2), doc d'activation. | 1-2 sessions | C-01 |
| C-06 | **Rapports / clôtures / impression** | Recâblage lectures locales (D4), sync libellés assets (D5) — reports.py ×3, formatters ×1. | 1-2 sessions | C-02b, C-03 |
| C-07 | **E2E + recette pilote** | Réécriture des 7 tests fedow-dépendants (mock + Fedow docker), E2E complet (appairage → scan → cascade → clôture → vidage), tenant pilote réel. | 2-3 sessions | tous |

Chemin critique : C-01 → C-03 → C-07. C-01 et C-02a/b/c sont parallélisables.
Règle de session inchangée : 1 chantier = 1-2 sessions max, max 3 fichiers
modifiés avant check + tests, jamais deux chantiers enchaînés sans validation.

## 7. Critères d'acceptation du programme

1. Un tenant neuf peut activer sa caisse V2 et vendre en espèces/CB sans
   qu'aucun serveur LaBoutik externe n'existe pour lui.
2. Le même tenant, après handshake, encaisse en cashless une carte NFC du
   réseau existant (carte créée par un lieu V1) — et inversement, sa recharge
   est dépensable chez un lieu V1 : **preuve du réseau unique**.
3. Une adhésion vendue en caisse V2 apparaît immédiatement dans
   `BaseBillet.Membership` sans transaction SUB Fedow.
4. Coupure réseau pendant une vente : la vente reste ouverte, payable en
   espèces/CB ; aucun double débit après reprise.
5. Les suites existantes (pytest + E2E) restent vertes ; aucun appel Fedow
   nouveau dans les flux des tenants V1 (vérifiable par les logs Fedow).
6. Clôture de caisse et ticket s'impriment sans appel HTTP Fedow.

## 8. Risques résiduels

| Risque | Mitigation |
|---|---|
| Latence HTTP au scan (file au bar) | 1 seul appel par scan (carte+tokens), cache d'affichage, timeout court |
| Double débit sur retry réseau | Garde-fou 3 (pas de retry aveugle) |
| Fedow standalone = SPOF du POS V2 | Identique au statu quo LaBoutik V1 (prouvé en prod) ; vente espèces/CB toujours locale ; monitoring des endpoints à mettre en place |
| Trou de contrat API découvert en C-03 (flux POS V2 sans endpoint Fedow) | Remonter au mainteneur ; modification Fedow possible (on le garde) mais jamais silencieuse |
| Divergence future lespass-main ↔ ce repo sur laboutik | lespass-main devient référence morte pour laboutik après le port — à acter dans M-To-V2/INDEX |

## 9. Questions ouvertes (à trancher avant ou pendant C-01/C-02)

1. **Recharge en ligne des tenants caisse V2** : on reste sur le flux V1
   (`get_federated_token_refill_checkout`, checkout Stripe créé par Fedow) —
   confirmé ? (C'est l'option zéro-code, recommandée.)
2. **Lots de cartes** (`create_batch`) : géré depuis l'admin Lespass (nouvelle
   méthode C-01) ou on continue avec l'outillage actuel côté Fedow ?
3. **Monnaie temps (TIM) au POS V2** : dans le périmètre du C-03 ou différé ?
4. Dépendances techniques du port laboutik (impression escpos, websocket,
   cotton) : inventaire en début de C-02.
