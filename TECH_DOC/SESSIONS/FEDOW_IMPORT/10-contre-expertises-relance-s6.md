# Recherche 10 — Relance des contre-expertises ⏳ (recadrées S6)

Date : 2026-06-20
Méthode : workflow multi-agents — 17 agents Sonnet adversariaux, un par finding,
lecture du code réel des **deux** repos (`lespass-main` branche `new_pairing_and_nfc`,
source à porter ; `Lespass` branche `main-fedow-import`, cible). Chaque agent devait
**réfuter** son finding sur le code actuel, puis le **re-trancher à la lumière de S6**.
Périmètre : les findings ⏳ (non contre-expertisés à l'audit, doc 02/02b) des dimensions
**gap-fonctionnel (10)** et **portage-V1 (7)**. La dimension **migration-données (6 ⏳)**
n'a pas été relancée — voir §6.

> Note de décompte : le doc 02 annonçait « 19 contre-expertises coupées ». L'annexe 02b
> contient en réalité **23 findings ⏳** de niveau bloquant/majeur (10 gap + 7 portage +
> 6 migration). Cette relance traite les **17** premiers ; les 6 de migration-données
> restent ⏳ (hors scope phase 1, non vérifiables ici).

---

## 1. Verdict global

**Aucun finding réfuté sur le fond.** 10 confirmés, 7 nuancés. La valeur de la relance
n'est pas dans l'infirmation mais dans le **reclassement à la lumière de S6** : sur
17 findings « bloquants/majeurs à traiter », il ne reste que **3 vrais bugs encore non
couverts**.

| Classement S6 | Nombre | Findings |
|---|---|---|
| **Bug à corriger** (non couvert ailleurs) | **3** | G1 (moitié), G6, G8 |
| Déjà couvert par la ROADMAP | 7 | G3, G7, G10, P1, P2, P3, P7 |
| Hors scope phase 1 | 6 | G2, G4, G5, G9, P5, P6 |
| Conforme au design S6 (finding caduc) | 1 | P4 |

Aucun finding ne remet en cause l'architecture S6. Trois findings ont changé de nature
par rapport à l'audit (P4 retourné, G1 scindé, G10 résolu) — détail §3.

---

## 2. Table des 17 verdicts

| Finding | Exactitude | Reclassement S6 | Sévérité revue | Lot |
|---|---|---|---|---|
| **G1** wallet user via Fedow distant | nuancé | **bug** (scindé en 2) | majeur | **C-B** |
| G2 badge/pointeuse absent en V2 | nuancé | hors scope ph.1 | mineur | — |
| G3 paiement QR/NFC caisse absent | confirmé | déjà couvert ROADMAP | mineur | C-C |
| G4 remboursement en ligne absent | confirmé | hors scope ph.1 | mineur | — |
| G5 rewards/gift absent + FK incohérente | confirmé | hors scope ph.1 (FK→C-D) | mineur | C-D |
| **G6** admin assets crashe sans Fedow | nuancé | **bug** (pré-existant) | majeur | **C-A** |
| G7 Onboard_laboutik bascule V2→V1 | nuancé | déjà couvert ROADMAP | mineur | C-D |
| **G8** adhésion admin/web encore 100% V1 | confirmé | **bug** | majeur | **C-B** |
| G9 import SUB/BDG + webhook fire-and-forget | nuancé | hors scope ph.1 | mineur | — |
| G10 comptabilité double | nuancé | déjà couvert (largt résolu) | mineur | C-B |
| P1 collision migrations 0204-0217 (B8) | confirmé | déjà couvert ROADMAP | bloquant | C-A |
| P2 signals importe laboutik (B9) | confirmé | déjà couvert ROADMAP | non-problème | C-A |
| P3 services_refund.py absent | confirmé | déjà couvert ROADMAP | majeur | C-A |
| **P4** Client.FED absent | nuancé | **conforme design S6 (caduc)** | non-problème | — |
| P5 CASHLESS_REFILL absent | confirmé | hors scope ph.1 | non-problème | — |
| P6 templates recharge htmx absents | nuancé | hors scope ph.1 | mineur | C-B |
| P7 sidebar NoReverseMatch latent | confirmé | déjà couvert ROADMAP | mineur | C-A |

---

## 3. Les reclassements à valeur (ce que la relance change vs l'audit du 10/06)

### 3.1 P4 s'est retourné — NE PAS porter Client.FED ⚠️
L'audit recommandait « porter la catégorie FED + `bootstrap_fed_asset` ». C'est **l'exact
inverse de S6** (qui interdit tout FED local : pas de `Client.FED`, pas de
`bootstrap_fed_asset`, pas de tenant `federation_fed` — c'est la **garde anti-FED-local**
de l'étape A4). Verdict de la contre-expertise : *« l'audit a confondu manque et garde
volontaire. Finding caduc. »* **À acter explicitement** pour que ce faux manque ne soit
pas « corrigé » pendant C-A. Même logique pour P5 (CASHLESS_REFILL) : son absence est
voulue (hors scope phase 1), pas un trou à combler.

### 3.2 G1 se scinde en deux
Le finding mélangeait deux chemins de nature opposée :
- **`create_tenant` / `install.py`** (V1 : `validators.py:1082-1083`, `install.py:201-202`)
  : instancier `FedowAPI()` déclenche un `create_place` HTTP + re-check `can_fedow()`
  **sans dispatch** → un tenant V2 ne peut pas être créé si Fedow est down. **Vrai bug.**
- **`MyAccount.dispatch`** (V1 : `views.py:749-751`) : `get_or_create_wallet` HTTP sans
  dispatch → **conforme au design S6** (parade 2.2 : le wallet user passe toujours par le
  legacy). Reste un sujet de **robustesse** (timeout court + dégradé au lieu d'un 500),
  pas de wallet local.

### 3.3 G10 (comptabilité double) largement résolu depuis l'audit ✅
`lespass-main` a reçu, **après** l'audit, des dispatches V1/V2 explicites sur tous les flux
de lecture (cartes, tokens, transactions) **et** de recharge FED. La double-écriture au
sens strict (un même euro écrit deux fois) n'existe plus. Les flux restants sans dispatch
sont soit protégés par `can_fedow()` (rewards, badges), soit conformes S6 (wallet via
legacy), soit hors scope phase 1 (QR pay, badge POS). Reste un seul point **documentaire** :
dresser la liste des flux « V1-only par design S6 » (à faire en C-B).

### 3.4 G2 (badge) surestimé
Le bouton `badge_in` est **commenté et `disabled`** dans les deux repos
(`punchclock.html:45-51`), le seul template avec l'appel actif
(`htmx/views/badge/list.html`) est **orphelin** (aucune vue ne le rend), et un appel direct
sur un tenant V2 sans `FedowConfig` **crashe au déchiffrement de la clé** avant tout appel
réseau — donc pas d'écriture silencieuse vers le Fedow distant. Risque réel faible.

---

## 4. Le net actionnable

### 4.1 Trois vrais bugs (nouveaux, non couverts ailleurs)

| Bug | Lot | Localisation V1 | Correction |
|---|---|---|---|
| 🔴 **G6** admin assets → 500 si Fedow down (**pré-existant**, touche déjà les V1) | **C-A** | `Administration/admin_tenant.py:3981-3996` (`AssetAdmin.get_queryset` → `get_accepted_assets()` sans try/except ; `fedow_api.py:180-189` raise) | try/except non bloquant dans `get_queryset` + masquer la section sidebar « Fédération » V1 pour les tenants V2 (garde `bool(server_cashless)`) |
| 🟠 **G1** création tenant V2 échoue si Fedow down | **C-B** | `BaseBillet/validators.py:1082-1083` + `Administration/management/commands/install.py:201-202` | dispatch : si `server_cashless` vide (tenant V2) → skip `FedowAPI()` + `can_fedow()`. (+ robustesse `MyAccount` : try/except timeout court au lieu d'un 500) |
| 🟠 **G8** adhésion admin/web sans garde | **C-B** | `admin_tenant.py:1310-1316` (`clean_email`) + `:1335` (`clean_card_number`) + `BaseBillet/triggers.py:190-194` (`trigger_A`) + `BaseBillet/signals.py:404-423` (`send_membership_and_badge_product_to_fedow`) | garde `if config.server_cashless:` sur `trigger_A` + signal produit ; try/except sur `cached_retrieve_by_signature` ; dispatcher `clean_card_number`. (`get_or_create_wallet` reste conforme S6.) |

### 4.2 Précisions de portage récupérées au passage
- **P3** : porter `BaseBillet/services_refund.py` seul ne suffit pas — les constantes
  `Product.VIDER_CARTE` / `VIREMENT_RECU` qu'il utilise sont **aussi** absentes de V1
  (champs POS, étape A3). Les deux portages sont **couplés dans C-A** (sinon `AttributeError`
  au premier remboursement/virement, après l'`ImportError` évité).
- **G5 → C-D** : la FK `Price.fedow_reward_asset` pointe vers `fedow_public.AssetFedowPublic`
  (V1) alors que `Price.asset` pointe vers `fedow_core.Asset` (V2) — un tenant V2 ne peut pas
  configurer un reward sur ses assets locaux. À corriger **avant** d'ouvrir les rewards aux
  nouveaux tenants (champ `fedow_reward_asset_v2` + dispatch des 2 tâches + portage de
  `WalletRefillViewSet`/gift vers `TransactionService`).
- **G7 → C-D** : le verrou `Onboard_laboutik` doit être dans la **vue**
  (`ApiBillet/views.py`), pas dans `Configuration.clean()` — `config.save()` direct
  bypasse `clean()`. Refus 409 si `module_caisse`/`module_monnaie_locale` actifs.

### 4.3 Confirmé hors scope phase 1 (aucune action C-A→C-D)
G2 (badge), G4 (refund en ligne), G9 (webhook V1 `fire-and-forget` réel mais **pré-existant**,
non aggravé par S6 — risque pour les tenants V1 uniquement), P5 (CASHLESS_REFILL),
P6 (templates recharge ; nuance : copier les 2 partials `reunion/*_v2.html` quand on portera
l'**affichage des soldes** locaux, distinct de la recharge).

### 4.4 Conforme / caduc — ne rien faire, ne pas « corriger »
- **P4** : `Client.FED` absent = **garde anti-FED-local voulue**. Ne pas porter.
- **G1 (moitié wallet)** : wallet user via legacy = parade 2.2, conforme.

---

## 5. Statut révisé des findings ⏳ (à reporter dans 02b)

| Finding 02b | Ancien | Nouveau statut |
|---|---|---|
| G1 (gap, BLOQUANT) | ⏳ | nuancé — bug partiel (create_tenant) C-B + moitié conforme S6 |
| G2 (gap) | ⏳ | nuancé — hors scope ph.1, risque surestimé |
| G3 (gap) | ⏳ | ✅ confirmé — déjà couvert ROADMAP C-C |
| G4 (gap) | ⏳ | ✅ confirmé — hors scope ph.1 |
| G5 (gap) | ⏳ | ✅ confirmé — hors scope ph.1, FK→C-D |
| G6 (gap) | ⏳ | nuancé — **bug pré-existant** C-A |
| G7 (gap) | ⏳ | nuancé — déjà couvert ROADMAP D1 |
| G8 (gap) | ⏳ | ✅ confirmé — **bug** C-B |
| G9 (gap) | ⏳ | nuancé — hors scope ph.1 (webhook V1 pré-existant) |
| G10 (gap) | ⏳ | nuancé — largement résolu depuis l'audit |
| P1 (portage, BLOQUANT) | ⏳ | ✅ confirmé — déjà couvert ROADMAP C-A |
| P2 (portage, BLOQUANT) | ⏳ | ✅ confirmé — non-problème (port ensemble) |
| P3 (portage) | ⏳ | ✅ confirmé — C-A (couplé constantes POS) |
| P4 (portage) | ⏳ | nuancé — **caduc**, conforme S6 |
| P5 (portage) | ⏳ | ✅ confirmé — hors scope ph.1 |
| P6 (portage) | ⏳ | nuancé — hors scope ph.1 |
| P7 (portage) | ⏳ | ✅ confirmé — déjà couvert ROADMAP C-A |

---

## 6. Ce qui n'a pas été relancé : migration-données (6 findings ⏳)

Non relancés par choix de périmètre :
- B7 — un seul Fedow sert deux instances (.coop / .re) + 31 places `lespass_domain='xxx.None'`
- `Transaction.tenant` NOT NULL vs ~27 700 transactions Fedow sans tenant naturel
- `bootstrap_fed_asset` crée un pot central à uuid neuf ≠ primary wallet Fedow
- 24 365 transactions référencent un CheckoutStripe Fedow sans équivalent V2
- wallets éphémères/orphelins porteurs de valeur (l'import ne peut se limiter aux users)
- assets locaux fédérés : l'unité minimale de migration est la fédération, pas le tenant

**Raison double** : (1) **hors scope phase 1** — S6 n'importe **aucune** donnée (le Fedow
standalone reste la source de vérité) ; (2) **non vérifiables ici** — ces findings citent
des chiffres de prod qui vivent dans `../Fedow` (SQLite), hors des working directories.

**À relancer si** la voie *V2-pure* (FED local neuf) est un jour choisie : ces 6 findings
sont alors les bloquants des phases ⑩⑪ (import des anciens tenants), comme l'acte le
garde-fou du doc 09.

---

## 7. Conséquences sur la ROADMAP

Items à intégrer (aucun ne remet en cause le découpage C-A→C-D) :

- **C-A** : + corriger **G6** (try/except `get_accepted_assets` + masquer section Fédération
  V1 pour tenants V2) ; rappel **P3** (services_refund **couplé** aux constantes POS) ;
  **acter P4 caduc** (ne pas porter `Client.FED` — c'est la garde anti-FED-local A4).
- **C-B** : + **G1** (dispatch `create_tenant`) ; + **G8** (gardes `server_cashless` sur
  `trigger_A` + signal + `clean_card_number`) ; + **G10** (documenter la liste des flux
  « V1-only par design S6 »).
- **C-D** : + **G5** (FK reward V2 avant d'ouvrir les rewards) ; confirmer **G7** (verrou
  `Onboard_laboutik` dans la vue, refus 409).
