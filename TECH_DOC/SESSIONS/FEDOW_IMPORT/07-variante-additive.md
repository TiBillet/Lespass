# Révision 07 — Variante additive : fedow_core local + interop FED legacy en ajout

Date : 2026-06-10
Statut : proposée par le mainteneur, analysée, **remplace le découpage de la
SPEC §6** dès confirmation.

## Le changement par rapport à la SPEC S5 initiale

La SPEC prévoyait de RECÂBLER la couche cashless du laboutik V2 (~35 call
sites `fedow_core` → `FedowAPI` HTTP). La variante additive **garde le proto
V2 intact** :

- `fedow_core` (V2) est porté avec laboutik et reste le moteur des **monnaies
  locales** (TLF locaux, cadeau, temps, fidélité) des nouveaux tenants —
  copier-coller, call sites intacts, tests V2 valides.
- L'interop Fedow legacy est **ajoutée** comme chemin supplémentaire,
  uniquement pour le **FED** : dans la cascade POS, le FED legacy est un
  **moyen de paiement externe** (statut TPE : échec HTTP = reste à payer,
  vente ouverte, pas de transaction distribuée).
- Le FED n'existe JAMAIS en local : pas de `bootstrap_fed_asset`, pas de
  `Client.FED` — garde-fou explicite contre le double réseau FED.

### Simplification du paiement FED legacy
Pour une carte legacy liée à un user, Lespass détient la clé RSA du user →
paiement FED via `FedowAPI.transaction.to_place_from_qrcode` (existant,
signé user). **Pas de handshake cashless requis** en première phase.
Cartes legacy anonymes (wallet éphémère) : « carte non liée » → complément
espèces/CB. Le handshake D1 (Lespass = serveur cashless) devient une
extension optionnelle ultérieure.

## Le prix : durcissement de fedow_core avant prod

`fedow_core` V2 entre en production → les findings confirmés de l'audit
(doc 02) redeviennent bloquants, à corriger en C-B :
- **B1** `verify_transactions` : règles débit/crédit désynchronisées,
  `--fix-tokens` sans verrou (corruption de soldes).
- **B2** garde sur `Asset.wallet_origin` (doit être un wallet de lieu).
- **M1** contrainte d'unicité partielle sur `Transaction.checkout_stripe`.
- **M2/M3** verrous dans `fusionner_wallet_ephemere` et
  `rembourser_en_especes` (reliquats orphelins) + catch `SoldeInsuffisant`
  dans les vues POS/admin.
- **M4** sérialisation de la création de Wallet user.
- (M5 asserts métier et M6 câblage fédération : à évaluer en C-B, peuvent
  suivre.)

## Points « pas du copier-coller » (rappel audit portage, à revérifier en C-A)

1. Migrations BaseBillet : JAMAIS copiées (collision 0204-0217) → porter les
   champs puis `makemigrations` frais 0219+. AuthBillet/QrcodeCashless/
   Customers/fedow_core : copiables telles quelles.
2. `BaseBillet/services_refund.py` à copier (requis par fedow_core/services).
3. Pas de bootstrap FED local (cf. garde-fou ci-dessus).
4. fedow_core + laboutik se portent ENSEMBLE (signal sans garde).
5. Settings : SHARED_APPS += fedow_core ; TENANT_APPS += laboutik, inventaire,
   discovery ; dep `django-cotton`.
6. Sidebar V1 déjà câblée sur les URLs admin fedow_core → réparée par le port.
7. Chemin Stripe `refill_federation`/`CASHLESS_REFILL` : hors scope (recharge
   FED en ligne = flux V1 existant).

## Découpage révisé

| Lot | Contenu | Estimation | Dépend de |
|---|---|---|---|
| **C-A** | Copier-coller du socle : fedow_core + laboutik + discovery + inventaire + services_refund + champs modèles (AuthBillet 0024/0025, Product/Price POS, CarteCashless, LaBoutikAPIKey) + settings + migrations + templates/static + clients. Livrable : caisse complète fonctionnelle (espèces/CB/cashless LOCAL) sur tenant de test, suite de tests V2 verte. | 1 grosse session (règle des 3 fichiers relâchée — transport) | — |
| **C-B** | Durcissement audit (B1, B2, M1-M4) + garde anti-FED-local + `manage.py check` sécurité multi-tenant | 1-2 sessions | C-A |
| **C-C** | Interop FED legacy additive : au scan, lookup carte legacy (FedowAPI), affichage solde FED, paiement FED « moyen externe » dans la cascade (cartes liées : signature user ; anonymes : complément) | 2-3 sessions | C-A |
| **C-D** | Onboarding/admin (activation module, création assets locaux), tests interop, tenant pilote | 1-2 sessions | C-B, C-C |

**Total : 6-8 sessions** (vs 15-22 pour le recâblage complet de la SPEC §6).
L'interop FED legacy (C-C) est le seul développement réellement nouveau.

## Conséquence sur les décisions de la SPEC

| Décision SPEC | Devenir |
|---|---|
| D1 (Lespass = serveur cashless, handshake) | **Différée** — non requise en première phase (signature user) |
| D2 (extension FedowAPI, 6 méthodes) | **Réduite** — seul le chemin FED (lookup carte + paiement w2w existant) |
| D3 (adhésions locales) | Inchangée (déjà implémentée) |
| D4/D5 (rapports locaux, AssetFedowPublic) | **Simplifiées** — fedow_core local rend les lectures directes possibles, AssetFedowPublic plus nécessaire pour le POS |
| D6 (cascade côté POS, échec = reste à payer) | Inchangée — appliquée au seul segment FED legacy |
