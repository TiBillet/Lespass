# Revue 06 — LaBoutik V2 (branche `new_pairing_and_nfc`) + estimation du câblage S5

Date : 2026-06-10
Source : revue complète de `lespass-main` basculé sur `new_pairing_and_nfc`
(3 agents d'exploration : serveur Django, clients matériels, validation des
hypothèses SPEC).

---

## 1. Ce que la branche apporte par rapport à `V2`

51 fichiers modifiés : 38 dans `laboutik/`, et **deux applications clientes
nouvelles** à la racine du repo.

### 1.1 Appairage des terminaux (PIN 6 chiffres)
- Nouvelle app **`discovery`** : modèle `PairingDevice` (PIN unique 6 chiffres,
  `terminal_role` ∈ {LB caisse, TI tireuse, KI kiosque}), endpoint public
  `POST /api/discovery/claim/` (throttle 10/min anti brute-force).
- `TibilletUser.terminal_role` (migration AuthBillet **0025**) + proxy
  **`TermUser`** (espèce TE, email synthétique `<uuid>@terminals.local`).
- **`LaBoutikAPIKey`** (BaseBillet) : clé API par terminal, liée au TermUser.
- Pont d'auth **`/laboutik/auth/bridge/`** : le client POSte sa clé API,
  reçoit une session et est redirigé vers la caisse.

### 1.2 Flux NFC de bout en bout
```
Carte NFC → client (plugin Cordova Android | RC522 GPIO Pi | ACR122U USB desktop)
         → tag_id remonte au navigateur (direct ou socket.io LOCAL au client Pi)
         → nfc.js remplit #nfc-tag-id et soumet le formulaire HTMX
         → POST /laboutik/paiement/payer/ {moyen_paiement:'nfc', tag_id}
         → serveur : CarteCashless par tag_id → cascade TNF→TLF→FED
         → TransactionService.creer_vente() par asset (fedow_core)
         → si solde insuffisant : écran complément (espèces/CB/2e carte)
```
Le socket.io du commit récent est **local au client Pi/desktop** (Node.js ↔
Chromium kiosk) — rien de socket.io côté Django.

### 1.3 Deux clients matériels
| Client | Stack | NFC | Impression | Maturité |
|---|---|---|---|---|
| `laboutik_client_android_v2` | Cordova 14, plugins custom | plugin `cordova-plugin-nfc-reader` | plugin Sunmi natif | **Prototype en chantier** (NFC/impression/signature APK en cours, todo.md) |
| `laboutik_client_pi_desktop_v2` | Node.js 24 + Chromium kiosk + socket.io local | RC522 (GPIO/SPI) ou ACR122U (USB) | thermique TCP (escpos) | **Production-ready** (readme d'install complet, modules propres) |

### 1.4 Verdict client — LE point clé pour S5
Les clients n'envoient au serveur que : un PIN (appairage), une clé API
(bridge), et des `tag_id`. Ils ne reçoivent que du HTML/JSON rendu par Django.
**Aucune notion de wallet/asset/token côté client.**
→ **Le recâblage S5 (fedow_core → FedowAPI HTTP) est totalement invisible
pour les clients. Zéro modification requise.**

## 2. Validation des hypothèses de la SPEC (point par point)

| Hypothèse SPEC | Verdict |
|---|---|
| `fedow_core` inchangé sur la branche | ✅ confirmé (`git diff` vide) |
| Call sites cashless identiques (creer_vente, creer_recharge, rembourser_en_especes, fusionner_wallet_ephemere) | ✅ confirmés, ~35 appels, lignes réactualisées (cf. § 3) |
| D3 adhésion locale | ✅ **déjà implémentée sur cette branche** : `retour_carte` lit `BaseBillet.Membership` en DB locale (views.py:7246-7256), aucun asset SUB consulté |
| D1 champs FedowConfig | ⚠️ comme prévu, les 4 champs n'existent pas en V1 — c'est le travail planifié du C-01 (pas un blocage nouveau) |
| Périmètre du portage | ⚠️ **élargi** : s'ajoutent `discovery` (appairage), `inventaire` (StockService, coquille vide en V1), champs AuthBillet 0024+0025 (wallet_name/public_pem + terminal_role), `LaBoutikAPIKey`, dépendance **`django-cotton`** (absente du pyproject V1 — seule dep Python manquante) |
| Tests | 23 tests laboutik dont **7 dépendent de fedow_core** → à réécrire contre le client HTTP (mock + Fedow docker de dev) |

## 3. Inventaire fedow_core réactualisé (branche `new_pairing_and_nfc`)

Imports : `laboutik/views.py:47-49`. ~35 appels :

| Service | Lignes (views.py) | Flux |
|---|---|---|
| `AssetService.obtenir_assets_accessibles` | 5542, 6505 | cascade (liste des assets) |
| `WalletService.obtenir_solde` | 5557, 5620, 5905, 6513, 6758, 6851, 7110, 7120 | soldes par asset |
| `WalletService.obtenir_total_en_centimes` | 6177, 6227, 6316, 6324 | totaux affichés |
| `WalletService.obtenir_tous_les_soldes` | 7220 | retour_carte (consultation) |
| `WalletService.fusionner_wallet_ephemere` | 4346 | adhésion NFC (liaison carte↔user) |
| `WalletService.rembourser_en_especes` + `get_or_create_wallet_tenant` | 7439, 7436 | vidage carte |
| `TransactionService.creer_vente` | 5793, 5821, 6651, 6681, 6980, 7010, 7033 | vente cascade + complément + 2e carte |
| `TransactionService.creer_recharge` | 4726 | recharge POS |
| lectures `Asset`/`Token` | reports.py:138/445/625, printing/formatters.py:228, views.py:7323 | rapports, tickets |
| fixtures | create_test_pos_data.py (~10 sites) | données de dev |

Nouveau cas découvert à couvrir en C-03 : le **paiement complémentaire
multi-cartes** (fonds insuffisants → complément espèces/CB/**2e carte NFC**,
views.py:6651-7033) — trois chemins de cascade au lieu d'un.

Note C-03 : `fusionner_wallet_ephemere` se traduit côté Fedow par
`linkwallet_card_number` (transaction FUSION), signée par la clé RSA du
*user* — que Lespass détient (`user.get_private_key()`). Pas de trou de
contrat.

## 4. Estimation du travail S5

Unité : **session** (selon la règle projet : 1 chantier = 1-2 sessions, max 3
fichiers modifiés avant check + tests). Le C-02 de la SPEC est éclaté en
3 sous-chantiers pour respecter cette règle.

| Chantier | Contenu | Estimation | Dépend de |
|---|---|---|---|
| **C-01** Client POS dans fedow_connect | 6 méthodes FedowAPI (D2), généralisation signature `_post`/`_get` (clé cashless), 4 champs FedowConfig + migration, handshake interne (D1), tests pytest contre Fedow docker | **2-3 sessions** | — |
| **C-02a** Socle données | `laboutik/models.py` (1 781 l.) + `inventaire` + `discovery` + champs AuthBillet (0024/0025 absorbés en migrations fraîches V1) + `LaBoutikAPIKey` + settings (TENANT_APPS, django-cotton) + admin | **2 sessions** | — |
| **C-02b** Socle vues/UI | `views.py` (~9 200 l.) + serializers + templates cotton + static JS (nfc.js, addition.js…) + urls. Livrable : caisse fonctionnelle en espèces/CB **sans cashless** | **2-3 sessions** | C-02a |
| **C-02c** Appairage & terminaux | discovery claim, TermUser, auth bridge, hébergement des 2 dossiers clients (aucune modif de leur code) | **1-2 sessions** | C-02a |
| **C-03** Câblage cashless | ~35 call sites → FedowAPI : scan/soldes, cascade + complément + 2e carte, recharge, vidage, fusion adhésion. UX erreur réseau + garde-fou idempotence | **3-4 sessions** | C-01, C-02b |
| **C-04** Adhésions | D3 déjà implémentée côté lecture ; vérifier la vente d'adhésion locale + purge des résidus assets SUB | **1 session** | C-02b |
| **C-05** Onboarding caisse V2 | activation module admin, handshake auto, verrou V1/V2 | **1-2 sessions** | C-01 |
| **C-06** Rapports / impression | reports.py ×3 + formatters ×1 + affichages soldes → AssetFedowPublic + données locales ; jamais d'HTTP en boucle de rendu | **1-2 sessions** | C-02b, C-03 |
| **C-07** Tests + pilote | réécriture des 7 tests fedow-dépendants (mock FedowAPI + Fedow docker), E2E complet (appairage → scan → cascade → clôture → vidage), tenant pilote | **2-3 sessions** | tous |

**Total estimé : 15 à 22 sessions.**
- Chemin critique : C-01 → C-03 → C-07.
- Parallélisable : C-01 (fedow_connect) et C-02a/b/c (portage) sont
  indépendants — deux personnes/pistes peuvent avancer de front.
- Les clients matériels ne sont PAS dans le chemin : le Pi/desktop est
  production-ready tel quel, l'Android est un chantier indépendant de S5
  (NFC/impression/signature APK encore en cours côté client).

### Aléas principaux de l'estimation
1. **C-03 est l'inconnue la plus grosse** : la sémantique exacte de
   `creer_vente`/`creer_recharge` (V2, centimes, wallet local) doit être mappée
   sur `transaction/` Fedow (V1, actions SALE/REFILL/CREATION, cartes
   obligatoires) — des écarts de contrat peuvent émerger (ex. la CREATION
   initiale d'un asset local avant le premier REFILL). Prévoir une session
   de spike au début de C-03.
2. **Le volume du C-02b** (9 200 lignes de vues) : le portage est mécanique
   mais long ; le risque est surtout les dépendances transverses non listées
   (wsocket broadcast, crowds ?) découvertes en cours de route.
3. La règle « max 3 fichiers avant tests » impose un rythme prudent sur
   C-02a/b — l'estimation le prend en compte.

## 5. Décisions à confirmer suite à la revue

1. **Les dossiers clients** (`laboutik_client_android_v2`,
   `laboutik_client_pi_desktop_v2`) sont-ils portés dans ce repo V1, ou
   restent-ils dans lespass-main / un repo dédié ? (Aucun impact code, c'est
   une décision d'hébergement git.)
2. La **migration AuthBillet 0024** (wallet_name, wallet_public_pem) vient
   avec le portage — elle recoupe la décision V2 « enrichir AuthBillet.Wallet ».
   OK pour l'absorber telle quelle en V1 ?
3. `django-cotton` entre dans les dépendances V1 (seul ajout Python). OK ?
