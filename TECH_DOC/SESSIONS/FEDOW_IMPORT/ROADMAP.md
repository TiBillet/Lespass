# ROADMAP — Scénario S6 : caisse V2 intégrée + interop Fedow legacy

Date : 2026-06-10 — **ACTÉ par le mainteneur**
Références : SPEC.md (décisions D1-D6, partiellement révisées), docs 07/08/09.
Branche de travail : `main-fedow-import`.

## 0. Le scénario en quatre phrases

1. Les **anciens tenants** (500 lieux) ne changent rien : LaBoutik V1 + Fedow
   standalone + `fedow_connect`, intouchés.
2. Les **nouveaux tenants** reçoivent la caisse intégrée (`laboutik`) avec
   leurs **monnaies locales en DB locale** (`fedow_core`, copié de lespass-main).
3. Les **tokens du réseau existant** (FED + assets fédérés legacy) sont
   acceptés au POS V2 via l'API du Fedow standalone — segment de cascade
   « moyen de paiement externe », signé par la clé RSA du user, **sans
   handshake cashless**. Phase 1 : cartes liées à un user uniquement.
4. **Jamais de FED local** : la monnaie fédérée reste exclusivement sur le
   legacy (pas de `bootstrap_fed_asset`, pas de tenant `federation_fed`).

## 1. Vue d'ensemble des lots

| Lot | Contenu | Statut (maj 2026-06-20) | Dépend de |
|---|---|---|---|
| C-A | Socle + champs BaseBillet + **admin laboutik/inventaire** | ✅ **FAIT** — pytest 262/263, admin (changelists + change views) + POS espèce/CB sur Chrome, env V2 connecté au Fedow (`can_fedow=True`, place créé) | — |
| C-B | Durcissement (audit + parades S6) | ✅ **COUVERT par le portage** — corrections génériques (verrous, atomicité, `SoldeInsuffisant`) validées pytest. **G1/G8 CADUQUES** (cf. §1bis) | C-A |
| C-C | **Interop FED au POS** (segment cascade transparent) | ⏳ **PROCHAIN LOT** | C-A, C-B |
| C-D | Onboarding, ops, pilote | ⏳ | C-B, C-C |
| **Dette** | **Admin modulaire** : `admin_tenant.py` (180 Ko) → modules ; booking/controlvanne/cards ; retrait `_safe_rev` | ⏳ **lot dédié** ([doc 12](./12-dette-admin-modulaire.md)) | C-A |

Prérequis transverses :
- [ ] **drift=0 confirmé** sur la prod Fedow (reconcile_tokens passé la nuit
  du 10-11/06 — requête §10.1 de `Fedow/TECH_DEV/DRIFT/README.md`). Bloquant
  pour le pilote (C-D), pas pour le dev.
- [ ] **Fedow docker de dev** opérationnel (flush.sh + demo_data) pour les
  tests C-C.
- [ ] Décision mainteneur : où vivent les dossiers clients
  (`laboutik_client_android_v2`, `laboutik_client_pi_desktop_v2`) — ce repo
  ou repo dédié. (Sans impact code.)

---

## 1bis. Compléments issus du creusage (docs 10 et 11)

Le creusage des zones ouvertes — relance des contre-expertises ([doc 10](./10-contre-expertises-relance-s6.md))
et spike sémantique du segment legacy ([doc 11](./11-spec-cc-segment-legacy.md)) — ajoute
les items suivants aux lots, **sans changer le découpage**.

### Pour C-A
- **G6 (doc 10)** — corriger le crash admin assets : entourer `get_accepted_assets()` d'un
  try/except non bloquant dans `AssetAdmin.get_queryset` (`admin_tenant.py:3981`) + masquer
  la section sidebar « Fédération » V1 pour les tenants V2. **Bug pré-existant** (touche
  déjà les tenants V1 si Fedow est down).
- **P3 (doc 10)** — `services_refund.py` est **couplé** aux constantes `Product.VIDER_CARTE`
  / `VIREMENT_RECU` (champs POS, étape A3) : les porter dans le même lot, sinon
  `AttributeError` au 1er remboursement/virement.
- **P4 (doc 10) — NE PAS porter `Client.FED`** : son absence **est** la garde anti-FED-local
  (étape A4), pas un manque. Finding retourné/caduc — ne pas le « corriger ».
- **Inventaire re-validé (point 5)** — **37 call sites** `fedow_core` dans `laboutik`,
  **valides en nature** (mêmes services/flux ; `creer_vente` 9 sites, `rembourser_en_especes`
  3 sites, + nouveau `utils/test_helpers.py`). ⚠️ `lespass-main` est en **dev actif** :
  cartographier au port **par symbole, jamais par ligne**, et **figer un commit de base** de
  `new_pairing_and_nfc`.

### Pour C-B — ⚠️ RÉVISÉ 2026-06-20 : G1/G8 CADUQUES, NE PAS LES IMPLÉMENTER
**Décision mainteneur (2026-06-20)** : **pas d'activation consciente** de Fedow —
**chaque nouveau tenant (V1 ET V2) est connecté au Fedow** (`create_place` AUTOMATIQUE à la
création), car un tenant V2 a besoin d'un **place Fedow** pour accepter l'**asset fédéré (FED)**
du réseau.
- **G1 et G8 sont CADUQUES.** Ils visaient à « couper Fedow si V2 » (ne pas instancier
  `FedowAPI()`, gardes `server_cashless` sur `send_membership_and_badge`/`trigger_product_update`).
  C'était **à l'envers**. Gardes implémentées puis **retirées** (`create_tenant`, `install.py`,
  `signals.py` restaurés à l'original, re-validé pytest 262). La distinction V1/V2 porte
  **uniquement sur où vit la monnaie locale cashless** : `fedow_core` LOCAL (V2) vs Fedow distant
  (V1) — dispatch déjà géré dans le code laboutik porté (`CaisseViewSet`).
- **C-B se résume aux corrections GÉNÉRIQUES de l'audit** (verrous `select_for_update`, atomicité,
  `SoldeInsuffisant`, `tenant_origin`, UniqueConstraint FED) — **déjà dans le code porté**
  (lespass-main durci) et **validées par pytest**. Rien à ajouter côté dispatch.
- **G10 (doc 10)** — seul reste (doc only) : documenter les flux « V1-only par design S6 ».

### Pour C-C
- **Spec actée → [doc 11](./11-spec-cc-segment-legacy.md) (révisée 2026-06-20).** Le FED est
  un **cran de cascade TRANSPARENT** (`TNF→TLF→FED`), **pas un bouton** : aucun geste opérateur.
  Solde lu en **temps réel (sans cache, `retrieve_by_signature` — pas `cached_…`)**, débit FED
  **à la validation** (ordre : FED HTTP d'abord, atomic local ensuite). Dépendance Fedow assumée
  → **dégradé** (locaux + espèces/CB) si Fedow down, jamais de blocage.
- **Appel Fedow SYSTÉMATIQUE à chaque transaction carte (doc 11 §4 + §4bis)** : on affiche le
  **solde complet (locaux + FED)** à chaque fois → impact **transversal** sur ~4 vues + ~3
  templates (`retour_carte`/`hx_card_feedback`, succès, récap, complément), enrichis via **un
  helper commun** `obtenir_solde_complet_carte`. **Aucun impact V1.** Coût : ~3 lectures Fedow +
  1 débit par vente carte avec FED → à monitorer.
- **Micro-extension `fedow_connect`** (validée) : variante de lecture **sans cache**
  (`retrieve_by_signature` direct ou `get_total_fiducial(..., use_cache=False)`).
- **Pont carte (doc 11 §5bis) — vérifié safe** : invariant `user.wallet.uuid == uuid_legacy`
  garanti par `get_or_create_wallet` + garde native « Wallet and member mismatch ». Cartes
  **liées** seulement ; **jamais de wallet éphémère miroir**.
- **FED partiel naturel** : il couvre ce qu'il peut (comme les locaux), le reste va en
  complément espèces/CB. Pas de seuil, pas de cas spécial — le **débit à la validation**
  garantit zéro débit FED orphelin (le FED n'est pas annulable).
- **Embranchement tranché (point 4, 2026-06-20)** : voie **S6 réseau unique** actée ; voie
  **V2-pure (FED local) écartée**. Confirme le §0 « jamais de FED local » et les findings
  P4/P5 (ne pas porter `Client.FED` / `bootstrap_fed_asset` / `CASHLESS_REFILL`).

### Pour C-D — ⚠️ handshake RÉVISÉ 2026-06-20
- **Handshake place du tenant V2 — RÉVISÉ (décision mainteneur)** : handshake **AUTOMATIQUE
  à la création** (PAS d'activation consciente). `create_place` reste appelé dans
  `create_tenant`/`install.py` pour **tous** les tenants (idempotent, garde « Place already
  created »). Le tenant V2 a son place Fedow dès sa création (vérifié : lespass `can_fedow=True`,
  place `96e9d347…`). **Plus de geste d'activation à coder.** Pas de handshake *cashless* en
  phase 1 (le cashless V2 est local `fedow_core`). ⚠️ Caduque aussi le « symétrique de G1 ».
- **G7 (doc 10)** — verrou `Onboard_laboutik` dans la **vue** (refus 409 si `module_caisse`/
  `module_monnaie_locale` actifs), pas dans `clean()` (que `save()` direct bypasse).
- **G5 (doc 10)** — corriger la FK `Price.fedow_reward_asset` (→ `fedow_core.Asset`) avant
  d'ouvrir les rewards aux nouveaux tenants.

---

## 2. C-A — Copier-coller du socle (1 grosse session)

Règle des 3 fichiers **relâchée** pour cette session (transport, pas
d'écriture). Source : `lespass-main` branche `new_pairing_and_nfc`.

### Étape A1 — Dépendances et settings
- `pyproject.toml` : + `django-cotton = "^2.6.1"` (seule dep manquante).
  Installation poetry par le mainteneur dans le conteneur.
- `TiBillet/settings.py` : `SHARED_APPS` += `fedow_core` ;
  `TENANT_APPS` += `laboutik`, `inventaire`, `discovery` ; `django_cotton`
  dans les apps ; loaders templates cotton si requis (copier la config V2).

### Étape A2 — Apps copiées telles quelles
- `fedow_core/` (models, services, exceptions, signals, admin, management,
  migrations — copiables telles quelles).
- `laboutik/` (~15 000 l. : models, views, serializers, urls, reports, fec,
  ventilation, archivage, integrity, printing/, utils/, templatetags/,
  management/, templates/, static/).
- `inventaire/`, `discovery/` (+ migrations).
- `BaseBillet/services_refund.py` (requis par fedow_core/services).
- Migrations **copiables** : AuthBillet 0024+0025, QrcodeCashless
  (wallet_ephemere), Customers, fedow_core, inventaire, discovery.

### Étape A3 — Champs BaseBillet portés À LA MAIN (⚠️ jamais copier ces migrations)
Collision 0204-0217 entre branches (audit B8). Porter les définitions puis
`makemigrations` frais en 0219+ :
- `Product` : champs POS (methode_caisse, categorie_pos, couleurs, icon,
  groupe_pos, `asset` FK fedow_core) — vérifier le diff exact avec V2.
- `CategorieProduct` (nouveau modèle).
- `Price` : `asset` FK, `non_fiduciaire`, `contenance`, `poids_mesure`.
- `LigneArticle` : champs POS (carte, wallet, weight_quantity…).
- `LaBoutikAPIKey`.
- Vérifier que les opérations proxy déjà jouées par V1 (0205) ne sont pas
  régénérées.
- `Paiement_stripe.CASHLESS_REFILL` : **NON porté** (recharge en ligne locale
  différée, hors phase 1).

### Étape A4 — Garde anti-FED-local (minimum vital, complété en C-B)
- Ne PAS exécuter `bootstrap_fed_asset` ; ne pas créer `Client.FED` ni le
  tenant `federation_fed`.

### Checkpoints de fin de C-A (obligatoires, dans l'ordre)
1. `manage.py check` : 0 issue.
2. `migrate_schemas` sur tous les schémas (DB de dev).
3. Suite pytest portée : tests fedow_core + laboutik verts
   (les tests V2 restent valides — gros avantage S6).
4. Smoke test Chrome (`https://lespass.tibillet.localhost/`) : caisse
   fonctionnelle **espèces/CB + cashless LOCAL** sur tenant de test
   (`create_test_pos_data --schema=lespass`).
5. Vérif non-régression V1 : un tenant existant simulé (server_cashless
   renseigné) n'exécute aucun code fedow_core (revue des points d'entrée).
6. Doc `A TESTER et DOCUMENTER/` + CHANGELOG.

---

## 3. C-B — Durcissement (2 sessions)

Corrections AVANT tout argent réel. Chaque garde naît avec son test pytest
(TDD). Références : audit 02/02b (B*, M*) + creusage 08 (§2).

### Session B1 — Le moteur
| # | Correction | Réf |
|---|---|---|
| 1 | `verify_transactions` : règles débit/crédit importées de services.py (plus de duplication), `--fix-tokens` sous `select_for_update` + atomic ; test « BANK_TRANSFER → 0 divergence » | B1 (bloquant) |
| 2 | Garde `Asset.wallet_origin` = wallet de lieu uniquement | B2 |
| 3 | UniqueConstraint partielle `Transaction.checkout_stripe` (action=RFL) + catch IntegrityError | M1 |
| 4 | **Règle wallet user** : création TOUJOURS via legacy d'abord (`get_or_create_wallet` HTTP) ; garde dans `fusionner_wallet_ephemere` (services.py:371) et `_obtenir_ou_creer_wallet` (laboutik) — un Wallet local à uuid aléatoire est réservé aux éphémères de carte et au wallet tenant | 08 §2.2 |

### Session B2 — Les flux
| # | Correction | Réf |
|---|---|---|
| 5 | `fusionner_wallet_ephemere` : verrou Token + carte, montant lu sous verrou | M2 |
| 6 | `rembourser_en_especes` : sélection tokens DANS l'atomic sous verrou + catch `SoldeInsuffisant` dans les 2 vues (toast « solde modifié, rescannez ») | M3 |
| 7 | Garde recharge : `asset.tenant_origin == tenant` dans `creer_recharge` | 08 §2.3 |
| 8 | Garde anti-FED-local : check Django (aucun `Asset.category == FED` en local) | 08 |
| 9 | `enregistrer_virement` : LigneArticle écrite dans le schéma du tenant cible (`tenant_context`) | M7 |
| 10 | Checkpoint sécurité multi-tenant : revue querysets admin fedow_core (list_filter non bornés, panel refund) | audit mineurs |

---

## 4. C-C — Interop legacy au POS (3-4 sessions)

Périmètre phase 1 : **cartes legacy liées à un user**. Anonymes → invitation
à lier la carte (flux `/qr/` existant) + complément espèces/CB.
Le client `fedow_connect` existant suffit : `card_tag_id_retrieve`,
`cached_retrieve_by_signature`, `get_total_fiducial_and_all_federated_token`,
`to_place_from_qrcode` — **aucune extension de FedowAPI requise en phase 1**.

### Session C1 — Lecture : pont carte + soldes
- Scan d'un tag_id inconnu de `CarteCashless` → lookup legacy
  (`card_tag_id_retrieve`) → si carte liée (wallet user connu) : création de
  la ligne CarteCashless **miroir** (uuid = qrcode_uuid legacy, user résolu
  par wallet uuid). **Jamais de wallet_ephemere miroir.**
- Affichage du dépensable legacy au scan (`retour_carte`) : appel
  `get_total_fiducial_and_all_federated_token` (cache 10 s), timeout court
  (~300 ms), dégradé silencieux si lent (soldes locaux affichés, legacy
  « indisponible »).
- Tests pytest avec mock FedowAPI + test manuel contre Fedow docker.

### Session C2 — Écriture : le segment dans la cascade
- `_payer_par_nfc` : après épuisement des assets locaux, si reste > 0 et
  carte liée et dépensable legacy > 0 → débit legacy
  `to_place_from_qrcode(amount=min(reste, dépensable))` **AVANT** le bloc
  atomic local. La cascade legacy elle-même (TLF fédérés puis FED) est faite
  côté serveur Fedow — le POS n'en connaît que le total.
- Échec/timeout HTTP → le montant repart en `total_complementaire`
  (écran complément existant : espèces/CB/2e carte). Pas de retry automatique.
- LigneArticle : `payment_method=STRIPE_FED` (PAS `LOCAL_EURO` : le FED réseau ≠ monnaie locale,
  fix compta 2026-06-21) + asset uuid legacy en référence. La chaîne compta (cascade, clôture,
  ventilation FEC) a été corrigée pour ventiler le FED à part (compte `SF` à configurer).
- Ordre anti-compensation : débit legacy d'abord (hors atomic), puis bloc
  atomic local ; si l'atomic échoue après débit legacy → toast + journal
  d'incident (cas rarissime : race locale) — procédure documentée.

### Session C3 — Cohérence carte + compléments
- `payer_complementaire` (2e carte NFC) : même segment legacy.
- Carte perdue : pour une carte à existence legacy, déclaration legacy
  D'ABORD (`lost_my_card_by_signature`) puis locale (`declarer_perdue`).
- Idempotence : pas de re-POST aveugle ; en cas de doute réseau, re-scan →
  les soldes font foi.
- Limitation actée et affichée : pas d'annulation automatique d'un débit
  legacy (geste commercial / procédure manuelle documentée).

### Session C4 (tampon) — E2E et polissage
- E2E Playwright contre Fedow docker : scan carte legacy liée → cascade
  local+legacy → clôture. Carte anonyme → invitation liaison → complément.
- Revue UX erreurs réseau (file du bar).

---

## 5. C-D — Onboarding, ops, pilote (2-3 sessions)

### Session D1 — Onboarding et verrous
- Activation caisse V2 dans le dashboard Groupware (module_caisse →
  module_monnaie_locale, code V2 existant).
- Création des assets locaux du tenant dans l'admin fedow_core (existant).
- **Verrou V1/V2** : `Onboard_laboutik` / `link_cashless_to_place` ne peut
  pas basculer un tenant à caisse V2 (et réciproquement) — flag explicite,
  transition par action admin consciente uniquement (finding audit).
- Appairage terminaux : test du flow PIN complet avec le client Pi/desktop
  (production-ready) ; l'Android reste un chantier séparé.

### Session D2 — Exploitation
- **Procédure backup/restore « ledger »** (08 §2.5) : dump dédié schéma
  public, export rejouable des transactions récentes, doc d'exploitation.
  Obligatoire avant le 1er tenant réel.
- Monitoring : sondes sur les endpoints legacy utilisés par le POS
  (latence/erreurs), alerte si indisponible.
- Vérification finale drift=0 (prérequis pilote).

### Session D3 — Pilote
- Tenant pilote réel : activation, assets locaux, lot de cartes locales,
  ventes réelles supervisées (local seul d'abord, puis segment legacy).
- Recette des critères d'acceptation (§6) + bilan → GO ouverture.

---

## 6. Critères d'acceptation (recette finale)

1. Un tenant neuf opère sa caisse complète sans aucun serveur externe
   (espèces/CB/cashless local).
2. Une carte du réseau existant **liée à un user** paie au POS V2 — preuve du
   réseau unique. Son débit est visible côté Fedow standalone.
3. Une carte legacy **anonyme** reçoit l'invitation de liaison et le
   complément espèces/CB ; aucun wallet miroir créé.
4. Adhésion vendue en caisse → `Membership` local immédiat, zéro asset SUB.
5. Coupure réseau en pleine vente : la vente aboutit en espèces/CB ; aucun
   double débit constaté après reprise.
6. Tenants V1 : zéro changement observable (échantillon de logs Fedow :
   aucun appel nouveau).
7. Clôture, ticket Z, export FEC corrects sur une journée mixte
   local + legacy + espèces + CB.
8. `verify_transactions` : 0 divergence sur le tenant pilote.

## 7. Règles de travail (rappel)

- 1 session = 1 focus ; max 3 fichiers avant check + tests (sauf C-A).
- Jamais d'opération git (mainteneur) ; jamais de `ruff format` sur fichiers
  existants ; serveur tenu par le mainteneur dans byobu.
- Chaque session : tests du domaine touché + CHANGELOG +
  doc `A TESTER et DOCUMENTER/`.
- S'arrêter et demander avant : settings.py (au-delà du C-A), urls racine,
  PaiementStripe, AuthBillet, dépendances nouvelles.

## 8. Ce qui est explicitement HORS scope (phase 2+, sur arbitrage)

- Recharge en ligne des monnaies locales (flux CASHLESS_REFILL à adapter).
- Cartes legacy anonymes au segment legacy (wallets éphémères miroir).
- Création de cartes « réseau » par un tenant V2 (exigerait le handshake
  cashless D1 + POST /card/ batch).
- Endpoint de remboursement d'un débit legacy (modification Fedow).
- Fédération de monnaies locales entre nouveaux tenants (câblage
  fedow_core.Federation — audit M6).
- Migration d'anciens tenants vers la caisse V2.
- Clients Android (chantier propre), recharge FED au POS.
