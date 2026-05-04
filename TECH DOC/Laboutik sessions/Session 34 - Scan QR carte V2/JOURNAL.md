# Journal Session 34 — Scan QR carte V2

**Date :** 2026-04-20
**Durée estimée :** 10h
**Durée réelle :** ~4h (subagent-driven, parallélisation efficace)
**Branche :** V2

## Étapes complétées

- [x] **Task 1** — 3 exceptions métier (`CarteIntrouvable`, `CarteDejaLiee`, `UserADejaCarte`) dans `fedow_core/exceptions.py`
- [x] **Task 2** — `CarteService.scanner_carte()` + `ScanResult` dataclass + 3 tests
- [x] **Task 3** — `CarteService.lier_a_user()` avec anti-vol + fusion + rattrapage adhésions + 7 tests
- [x] **Task 4** — `CarteService.declarer_perdue()` + 3 tests
- [x] **Task 5** — Dispatch V1/V2 dans `ScanQrCode.retrieve()`
- [x] **Task 6** — Dispatch V1/V2 dans `ScanQrCode.link()`
- [x] **Task 7** — Dispatch V1/V2 dans `lost_my_card()` + `admin_lost_my_card()` (classe `MyAccount`)
- [ ] **Task 8** — Tests E2E Playwright (repoussé à la fin, selon demande mainteneur)
- [x] **Task 9** — CHANGELOG + i18n FR/EN + docs (`A TESTER/scan-qr-carte-v2.md` + `fedow_core/CARTES.md`)
- [x] **Task 10** — Validation finale (pytest complet + test navigateur curl)

## Tests ajoutés

- **pytest DB-only** : 13 tests (`tests/pytest/test_scan_qr_carte_v2.py`)
  - 3 tests `scanner_carte` (vierge, idempotence, identifiée)
  - 7 tests `lier_a_user` (sans tokens, avec tokens, anti-vol, idempotence, refus autre user, rattrapage adhésions, multi-assets)
  - 3 tests `declarer_perdue` (nullify, preserve wallet user, autre user)
- **E2E Playwright** : à implémenter en Task 8 (repoussée)

## Test manuel validé

GET `https://lespass.tibillet.localhost/qr/<uuid>/` sur carte vierge :
- HTTP 200 ✅
- Formulaire `#linkform` rendu avec `hx-post="/qr/link/"` ✅
- `input type="hidden" name="qrcode_uuid"` avec UUID correct ✅
- En base : `wallet_ephemere` créé avec `origin=Lespass` et `name="Wallet ephemere carte <number>"` ✅

## Pièges rencontrés

### 1. PostgreSQL `FOR UPDATE` + outer join

`select_for_update().select_related("detail__origine", "user", "wallet_ephemere")` rejeté par PostgreSQL car `FOR UPDATE` ne peut pas s'appliquer sur le côté nullable d'un outer join.

**Fix** : retirer `select_related()` du verrou. Les FK se chargent à la demande. Documenté en commentaire bilingue dans `CarteService.lier_a_user()` (`fedow_core/services.py:1342-1347`).

### 2. Fixture `user_tout_neuf` et `connection.tenant`

`User.objects.create_user()` dans `AuthBillet` lit `connection.tenant` pour poser `client_source`. Sans `tenant_context`, échec avec `ValueError: Cannot assign FakeTenant`.

**Fix** : wrapping `with tenant_context(tenant_origine):` dans la fixture. Pattern existant dans `test_billetterie_pos.py`.

### 3. `get_request_ip` inexistant dans Lespass

Le plan référençait `get_request_ip(request)` mais cette helper n'existe pas dans le codebase Lespass (elle est côté serveur Fedow standalone).

**Fix** : fallback inline `request.META.get("REMOTE_ADDR", "0.0.0.0")`. Sans impact fonctionnel (le param `ip` a un default `"0.0.0.0"`).

## Architecture résultante

```
BaseBillet/views.py
  ScanQrCode
    ├── retrieve() ─── dispatch V1/V2
    │   ├── _retrieve_v1_legacy()       (FedowAPI HTTP)
    │   └── _retrieve_v2_fedow_core()   (CarteService.scanner_carte)
    ├── link()     ─── dispatch V1/V2
    │   ├── _link_v1_legacy()           (FedowAPI HTTP)
    │   └── _link_v2_fedow_core()       (CarteService.lier_a_user)
  MyAccount
    ├── lost_my_card()        ─┐
    └── admin_lost_my_card()  ─┼── _declare_lost_card_dispatch()
                               ├── _declare_lost_v1_legacy()     (FedowAPI HTTP)
                               └── _declare_lost_v2_fedow_core() (CarteService.declarer_perdue)

fedow_core/services.py
  CarteService
    ├── scanner_carte(carte, tenant_origine, ip)     → ScanResult
    ├── lier_a_user(qrcode_uuid, user, ip)           → CarteCashless
    │   └── délégue à WalletService.fusionner_wallet_ephemere() [Phase 0]
    │       └── TransactionService.creer(action=FUSION) [Phase 0]
    └── declarer_perdue(user, number_printed)        → CarteCashless

fedow_core/exceptions.py
  + CarteIntrouvable, CarteDejaLiee, UserADejaCarte
```

## Dispatch V1/V2

- Condition : `Configuration.get_solo().server_cashless` (lu dans `tenant_context(tenant_origine)`)
- `server_cashless` renseigné → **V1** (`fedow_connect` HTTP vers Fedow distant)
- `server_cashless` vide → **V2** (`fedow_core` DB direct)
- Les 2 systèmes de tokens sont disjoints (pas de pont entre DB locale et Fedow distant)

## Fichiers modifiés / créés

**Modifiés :**
- `fedow_core/exceptions.py` (+3 classes, ~40 lignes)
- `fedow_core/services.py` (+~200 lignes : imports + ScanResult + CarteService)
- `BaseBillet/views.py` (refactor 4 vues + 6 helpers, ~200 lignes)
- `CHANGELOG.md` (+entrée Session 34)
- `locale/fr/LC_MESSAGES/django.po` (+5 entrées traduites)
- `locale/en/LC_MESSAGES/django.po` (+5 entrées traduites)

**Créés :**
- `tests/pytest/test_scan_qr_carte_v2.py` (13 tests)
- `A TESTER et DOCUMENTER/scan-qr-carte-v2.md` (checklist manuelle)
- `fedow_core/CARTES.md` (doc technique)
- `TECH DOC/Laboutik sessions/Session 34 - Scan QR carte V2/SPEC_SCAN_QR_CARTE_V2.md`
- `TECH DOC/Laboutik sessions/Session 34 - Scan QR carte V2/PLAN.md`
- `TECH DOC/Laboutik sessions/Session 34 - Scan QR carte V2/JOURNAL.md` (ce fichier)

**Aucune migration Django.**

## Suite (roadmap C — bascule totale `fedow_connect/` → `fedow_core/`)

Les sessions suivantes continueront la bascule, dans cet ordre suggéré :

- **Session 35** — Wallet user + token retrieval (`retrieve_by_signature`, `get_total_fed_token`, `get_total_fiducial_and_all_federated_token`, `refund_fed_by_signature`)
- **Session 36** — Transactions list + history (`paginated_list_by_wallet_signature`, `list_by_asset`, `retrieve`, `get_from_hash`)
- **Session 37** — Adhésions + badges (`MembershipFedow.create`, `BadgeFedow.badge_in`)
- **Session 38** — Asset management + bank deposits (`AssetFedow`, `local_asset_bank_deposit`, `global_asset_bank_stripe_deposit`)
- **Session 39** — Bootstrap place (`PlaceFedow.create_place`, `link_cashless_to_place`, intégration `install.py`)
- **Session 40** — Décommissionnement `fedow_connect/` + extinction serveur Fedow standalone

## Message de commit suggéré

```
feat(fedow_core): Session 34 - scan QR carte V2 (CarteService)

- Ajoute CarteService dans fedow_core/services.py avec 3 methodes :
  scanner_carte, lier_a_user, declarer_perdue
- Ajoute 3 exceptions metier dans fedow_core/exceptions.py
- Dispatch V1/V2 dans BaseBillet.ScanQrCode + MyAccount.lost_my_card
  selon Configuration.server_cashless
- Aucune migration : CarteCashless schema inchange (Option 3 YAGNI)
- 13 tests pytest + CHANGELOG + i18n FR/EN + docs (fedow_core/CARTES.md,
  A TESTER/scan-qr-carte-v2.md)

Hors scope : E2E Playwright (Task 8 a finaliser), suppression fedow_connect/
(roadmap C session finale).
```

Le mainteneur décide du commit final. Aucune opération git effectuée par les subagents.
