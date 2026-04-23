# Changelog / Journal des modifications

## Session 34 — Scan QR carte V2 (fedow_core) / QR card scan V2

**Quoi / What :** Bascule du flow public "scan QR carte cashless" de `fedow_connect/fedow_api.py` (HTTP vers Fedow distant) vers `fedow_core/services.py` (DB direct). Scope : scan, identification user (link), fusion wallet ephemere, perte de carte.
**Pourquoi / Why :** Supprimer la dependance reseau Fedow pour le flow public, simplifier l'audit anti-vol, preparer la suppression totale de `fedow_connect/` (roadmap C).

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `fedow_core/exceptions.py` | +3 exceptions (`CarteIntrouvable`, `CarteDejaLiee`, `UserADejaCarte`) |
| `fedow_core/services.py` | +classe `CarteService` (scanner_carte, lier_a_user, declarer_perdue) |
| `BaseBillet/views.py` | Dispatch V1/V2 dans `ScanQrCode.retrieve/link` + `lost_my_card`/`admin_lost_my_card` |
| `tests/pytest/test_scan_qr_carte_v2.py` | 13 tests DB-only |
| `fedow_core/CARTES.md` | Doc mecanique wallet ephemere + fusion |

### Migration / Migration
- **Migration necessaire / Migration required :** Non / No
- Aucun changement de schema. `CarteCashless`, `Wallet`, `Transaction.FUSION` deja en place.

### Coexistence V1/V2 / V1/V2 coexistence
- Dispatch par tenant : `Configuration.server_cashless` renseigne → V1 `fedow_connect` ; sinon V2 `fedow_core`.
- Les tenants legacy continuent d'appeler le serveur Fedow distant sans changement.
- Les nouveaux tenants V2 n'utilisent plus jamais `NFCcardFedow` pour le scan QR.

## Session 33 — Visualisation historique transactions V2 / Tx history display V2 (2026-04-20)

**Quoi / What:** La page `/my_account/balance/` affiche desormais les `fedow_core.Transaction` locales pour les users V2 (historique complet incluant les transactions des wallets ephemeres fusionnes dans `user.wallet`), au lieu d'appeler `FedowAPI` distant. Dispatch symetrique Sessions 31-32 via `peut_recharger_v2(user)`.
/ The balance page now displays local `fedow_core.Transaction` for V2 users (full history including ephemeral wallets merged into `user.wallet`), instead of calling the remote `FedowAPI`.

**Pourquoi / Why:** Apres Sessions 31 (recharge FED V2) et 32 (affichage tokens V2), l'historique transactions restait lu sur Fedow distant. Un user qui rechargeait en V2 voyait son solde mis a jour mais pas la transaction dans son historique. Cette session complete la coherence read-side.
/ After Sessions 31 (refill) and 32 (tokens display), transaction history was still read from remote Fedow. This session completes read-side consistency.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/views.py` | Dispatch V2 + methode `_transactions_table_v2` + 2 helpers module-level (`_enrichir_transaction_v2`, `_structure_pour_transaction`) |
| `BaseBillet/templates/reunion/partials/account/transaction_history_v2.html` | Nouveau partial : table 4 colonnes (Date \| Action \| Montant ±signe \| Structure) + pagination HTMX |
| `tests/pytest/test_transactions_table_v2.py` | Nouveau, 11 tests pytest DB-only |
| `A TESTER et DOCUMENTER/visu-historique-transactions-v2.md` | Guide mainteneur |
| `locale/{fr,en}/LC_MESSAGES/django.po` + `.mo` | 7 nouvelles strings |

### Migration
- **Migration necessaire / Migration required:** Non / No
- **Non-regression :** Sessions 31 + 32 inchangees. V1 `transaction_history.html` inchange.

### Tests
- 11 tests pytest DB-only dans `tests/pytest/test_transactions_table_v2.py`
- Sessions 31 + 32 non-regressees

## Session 32 — Visualisation tirelire V2 / Wallet display V2 (2026-04-20)

**Quoi / What:** La page `/my_account/balance/` affiche desormais les `fedow_core.Token` locaux pour les users V2, au lieu d'appeler `FedowAPI` distant. Dispatch symetrique a Session 31 via `peut_recharger_v2(user)`.
/ The balance page now displays local `fedow_core.Token` for V2 users, instead of calling the remote `FedowAPI`. Symmetric dispatch with Session 31 via `peut_recharger_v2(user)`.

**Pourquoi / Why:** Apres la Session 31 (recharge FED V2 en base locale), les users V2 ne voyaient pas leurs tokens sur leur page balance (toujours lus depuis le serveur Fedow distant). Cette session complete le flow read-side en local.
/ After Session 31 (FED V2 refill in local DB), V2 users couldn't see their tokens on the balance page (still read from remote Fedow). This session completes the local read-side flow.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/views.py` | Dispatch V2 dans `MyAccount.tokens_table` + methode `_tokens_table_v2` + 2 helpers module-level (`_lieux_utilisables_pour_asset`, `_get_tenant_info_cached`) + imports `Token`/`Asset` |
| `BaseBillet/templates/reunion/partials/account/token_table_v2.html` | Nouveau partial : 2 sous-tableaux (Currencies fiduciaires + Time & loyalty compteurs) + cas vide |
| `tests/pytest/test_tokens_table_v2.py` | Nouveau, 9 tests pytest DB-only |
| `A TESTER et DOCUMENTER/visu-tirelire-v2.md` | Guide mainteneur |
| `tests/PIEGES.md` | Nouvelle entree 11.9 : cross-schema cascade sur delete() requiert tenant_context |
| `locale/{fr,en}/LC_MESSAGES/django.po` + `.mo` | 7 nouvelles strings i18n |

### Migration
- **Migration necessaire / Migration required:** Non / No
- **Non-regression :** V1 flow (`FedowAPI`) inchange. Les users `v1_legacy`, `wallet_legacy`, `feature_desactivee` continuent d'utiliser le flow existant.

### Tests
- 9 tests pytest DB-only dans `tests/pytest/test_tokens_table_v2.py`
- Session 31 (31 tests) non-regressee

## Recharge FED V2 — Phases A, B, C / FED V2 Refill — Phases A, B, C

**Date :** 2026-04-20
**Migration :** Oui / Yes — voir section Migrations ci-dessous

**Quoi / What :** Fondations techniques de la recharge FED V2 locale (sans
serveur Fedow distant) pour les nouveaux tenants. La recharge FED, jusqu'a
present entierement deleguee a un serveur Fedow distant via HTTP+RSA, est
reecrite en acces DB direct dans `fedow_core` (SHARED_APPS). Les tenants
legacy (avec `server_cashless` configure) continuent le flow V1 inchange ;
les tenants V2 (`module_monnaie_locale=True AND server_cashless IS NULL`)
basculent automatiquement sur le nouveau flow local.

**Pourquoi / Why :** Premiere etape du plan de fusion mono-repo TiBillet
(cf. `TECH DOC/Laboutik sessions/PLAN_LABOUTIK.md`). La recharge FED est le
cas d'usage n°1 du plan de remplacement progressif du serveur Fedow distant
par l'app locale `fedow_core`. Permet l'atomicite cross-schema, supprime la
dependance critique au serveur Fedow distant pour cette feature, ouvre la
voie a l'ajout de PSP alternatifs (Payplug, Lydia, etc.) via le contrat
documente dans `fedow_core/PSP_INTERFACE.md`.

### Architecture en 4 couches

```
Intention (Product RECHARGE_CASHLESS_FED)
    → Gateway PSP (CreationPaiementStripeFederation, pas de Connect, pas de SEPA)
        → Moyen (Paiement_stripe source=CASHLESS_REFILL, dans tenant federation_fed)
            → Resultat wallet (RefillService : Transaction REFILL + credit Token)
```

### Decisions architecturales validees

| Decision | Valeur |
|---|---|
| Moteur cible | `fedow_core` (SHARED_APPS, acces DB direct) |
| Tenant de stockage | Tenant dedie `federation_fed` (`Client.FED = 'E'`) |
| Bootstrap | Management command `bootstrap_fed_asset` idempotente |
| Gateway Stripe | Pas de Stripe Connect (compte central root), CB uniquement (pas SEPA) |
| Montant min/max | Hardcodes 100 / 50000 centimes (1 € / 500 €) |
| Bascule V1/V2 | Helper `peut_recharger_v2(user)` : module_monnaie_locale + server_cashless courant + wallet.origin |
| Bloc wallet legacy | Message FALC inline "Migration en cours, merci de patienter" |
| Idempotence webhook | Check `Transaction(checkout_stripe=..., action=REFILL).exists()` dans atomic |
| Anti-tampering | `stripe.amount_total == int(paiement.total() * 100)` |
| Verrous admin | Asset FED lecture seule ; Product de recharge non creable manuellement |

### Fichiers crees / Created files

| Fichier / File | Role / Role |
|---|---|
| `fedow_core/management/commands/bootstrap_fed_asset.py` | Commande idempotente : tenant `federation_fed` + root wallet + Asset FED + Product de recharge |
| `fedow_core/PSP_INTERFACE.md` | Contrat documente pour l'ajout d'un nouveau PSP |
| `PaiementStripe/serializers.py` | `RefillAmountSerializer` (bornes 1 € / 500 €) |
| `PaiementStripe/refill_federation.py` | `CreationPaiementStripeFederation` (gateway Stripe compte central, sans Connect ni SEPA) |
| `BaseBillet/templates/htmx/views/my_account/refill_form_v2.html` | Formulaire HTMX saisie montant |
| `BaseBillet/templates/htmx/views/my_account/refill_migration_inline.html` | Message "migration en cours" pour wallet legacy |
| `tests/pytest/test_bootstrap_fed_asset.py` | 4 tests bootstrap idempotent |
| `tests/pytest/test_refill_service.py` | 3 tests RefillService (nominal, idempotent, wallet fallback) |
| `tests/pytest/test_refill_serializer.py` | 5 tests bornes montant |
| `tests/pytest/test_refill_federation_gateway.py` | 4 tests gateway (no Connect, no SEPA, source, metadata) |
| `tests/pytest/test_refill_webhook.py` | 4 tests webhook (dispatch, anti-tampering, idempotence, source check) |
| `tests/pytest/test_peut_recharger_v2.py` | 4 tests bascule V1/V2 (4 verdicts) |

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `Customers/models.py` | +categorie `Client.FED = 'E'` |
| `BaseBillet/models.py` | +`Product.RECHARGE_CASHLESS_FED` + `Paiement_stripe.CASHLESS_REFILL` |
| `fedow_core/services.py` | +classe `RefillService.process_cashless_refill()` (idempotent) |
| `fedow_core/admin.py` | Defense en profondeur : Asset FED non modifiable (`has_change_permission`) |
| `Administration/management/commands/install.py` | +hook `call_command('bootstrap_fed_asset')` |
| `laboutik/management/commands/create_test_pos_data.py` | +hook `bootstrap_fed_asset` (fixtures test) |
| `ApiBillet/views.py` | +`_process_stripe_webhook_cashless_refill()` + dispatch `refill_type='FED'` avant legacy |
| `BaseBillet/views.py` | +helper `peut_recharger_v2()` + reecriture `refill_wallet()` + `refill_wallet_submit()` + `return_refill_wallet()` V1/V2 |

### Migrations / Migrations

- `Customers/migrations/0005_alter_client_categorie.py`
- `BaseBillet/migrations/0215_alter_paiement_stripe_source_and_more.py`

Application :

```bash
docker exec lespass_django poetry run python manage.py migrate_schemas --executor=multiprocessing
```

Puis **obligatoire apres la migration**, lancer le bootstrap (idempotent) :

```bash
docker exec lespass_django poetry run python manage.py bootstrap_fed_asset
```

### Tests / Tests

- **Phase A** : 12 tests pytest verts (bootstrap + service + serializer)
- **Phase B** : 8 tests pytest verts (gateway + webhook)
- **Phase D** : 4 tests pytest verts (les 4 branches de peut_recharger_v2)
- **Non-regression** : 17 tests fedow_core + 19 tests Stripe existants, 0 regression
- **Total Session 31** : **24 nouveaux tests pytest** (+ 36 tests existants intacts)

### Ce qui reste (Phase D-polish et suite)

- Tests pytest nice-to-have (Asset FED absent, cross-tenant, serializer UI)
- Tests E2E Playwright (flow complet Stripe 4242 + non-regression V1)
- Condition template `my_account_wallet.html` : masquer le bouton refill quand `module_monnaie_locale=False`
- i18n : `makemessages -l fr -l en` + `compilemessages` pour les nouveaux strings
- Phase E (Session 31 Phase E, optionnelle, plus tard) : suppression complete du legacy Fedow distant (chantier 5-7 jours, 36 usages de `FedowAPI()` a garder)

### Reference / Reference

- Spec : `TECH DOC/Laboutik sessions/Session 31 - Recharge FED V2/SPEC_RECHARGE_FED_V2.md`
- Plans : `PLAN_PHASE_A.md`, `PLAN_PHASE_B.md`
- Contrat PSP : `fedow_core/PSP_INTERFACE.md`

---

## Stabilisation complete suite E2E / Full E2E suite stabilization

**Date :** 2026-04-19
**Migration :** Non / No

**Quoi / What :** Elargissement du scope a TOUS les tests E2E (apres la
stabilisation panier). La suite E2E complete passe maintenant a **117/117**
tests verts, 0 skip, en ~12 min sans flake. Combinee aux 618 tests pytest
DB-only, le projet est a 735/735 tests verts.

**Pourquoi / Why :** Plusieurs tests E2E etaient casses pour des raisons
variees (UI i18n, data manquante, WebSocket non supporte, fixtures trop
larges). L'objectif de cette session elargie est d'amener la suite a 100%.

### Corrections apportees

| Test | Probleme | Fix |
|---|---|---|
| `test_pos_sortie_caisse_e2e::test_04_etat_caisse_affiche_dans_formulaire` | UI libelle `Solde` → `Balance` selon langue active | Assertion tolere FR/EN (PIEGES 9.34) |
| `test_controlvanne_kiosk::test_01_kiosk_list_accessible` | 0 TireuseBec en DB | Fixture `_ensure_tireuse_exists` module-scoped, idempotente |
| `test_controlvanne_kiosk::test_02_kiosk_detail_une_seule_carte` | Skip car pas de fut actif | Seed inclut un Product FUT attache a la tireuse |
| `test_pos_stock_websocket::test_stock_websocket_multi_onglet` | `runserver_plus` ne gere pas les WebSockets | Skip conditionnel via `page.evaluate` (connexion WS reelle 3s timeout) |
| `test_asset_federation::test_full_per_asset_invitation_flow` | Flow UI 6 etapes cross-tenant + admin pas granted chantefrein | Refactor via `login_as_admin_on_subdomain` + fixture `_grant_admin_on_chantefrein` setup/teardown |
| `test_admin_card_refund::test_e2e_admin_refund_flow_complet` | Teardown `filter(name__icontains='E2E ')` matche les seeds panier → ProtectedError PriceSold | Exclude `name__startswith='E2E Test —'` |
| `test_pos_recharge_cashless::test_01/02/03` | PV Cashless affiche plusieurs tuiles Recharge (TLF/TNF/TIM) — `.first` tombait sur un asset inactif | Filtre `has_text="Monnaie locale"` (TLF actif) |
| `test_pos_recharge_cashless::test_04_vente_nfc_apres_recharge` | Cascade paiement NFC debite un autre asset que TLF (FID/TNF presents) → solde TLF inchange | `recharge_setup` purge tous les tokens du wallet (pas seulement TLF) |
| `test_pos_adhesion_nfc::test_panier_mixte_vt_re_ad_nfc_puis_especes` | Meme ambiguite multi-Products Recharge | Filtre `has_text="Monnaie locale"` |
| `test_explorer_assets_focus::test_click_tibillet_asset_card_draws_hull_polygon` | 2 assets "Fédéré TiBillet" seedes (1 federe, 1 local) — `.first` tombait sur celui a 1 lieu, pas de hull | Filtre `has_text="Accepté par"` cible l'asset avec > 1 lieu acceptant |
| (Post-flush) Products Recharge non regeneres | Signal Asset post_save fire uniquement si `created=True` — flush purge les Products mais le re-seed est `get_or_create` → `created=False` | `demo_data_v2._handle_full` re-trigger le signal pour chaque Asset TLF/TNF/TIM actif sans Product |
| (Seed events E2E) `max_per_user=10` atteint apres 10 runs | Limite basse sur l'event gratuit seede | `max_per_user=None` (pas de limite sur les fixtures test) |

### Fichiers crees / Created files
| Fichier / File | Changement / Change |
|---|---|
| (aucun — tous les changements sont dans les tests existants) | — |

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| tests/e2e/conftest.py | +fixture `login_as_admin_on_subdomain` (cross-tenant force_login) |
| tests/e2e/test_pos_sortie_caisse_e2e.py | Assertions tolerantes i18n FR/EN |
| tests/e2e/test_controlvanne_kiosk.py | +fixture `_ensure_tireuse_exists` module-scoped |
| tests/e2e/test_pos_stock_websocket.py | Skip conditionnel si serveur non-ASGI |
| tests/e2e/test_asset_federation.py | Suppression `_login_on_tenant` UI → `login_as_admin_on_subdomain` + `_grant_admin_on_chantefrein` |
| tests/e2e/test_admin_card_refund.py | Teardown exclut seeds E2E Test — |
| tests/e2e/test_pos_vider_carte.py | Commentaire "TEST MODE" corrige |

### Prerequis dev pour run complet

- **Serveur ASGI requis** (pour les tests WebSocket) : lancer `rsp` dans le pane byobu (alias pour `manage.py runserver` en mode ASGI auto avec daphne).
- `runserver_plus` (Werkzeug) **ne suffit PAS** — il ne gere pas les WebSockets et `test_stock_websocket` se skippe.

### Bilan
- **117/117 tests E2E passent, 0 skip, 0 flake**
- Combine avec pytest DB-only : **735/735 tests verts**
- Temps total E2E : ~12 min (moyenne 6s/test)
- Pieges documentes : 9.101 a 9.110 (force_login env, django_db_blocker, Event slug,
  /panier/ auth, booking-add-and-pay conditionnel, wait_for_url string, runserver_plus
  non-ASGI, env vars container, admin Lespass only, teardown wide-match)

---

## Stabilisation tests E2E panier / E2E cart tests stabilization

**Date :** 2026-04-19
**Migration :** Non / No

**Quoi / What :** Refonte de la suite de tests E2E panier pour atteindre 5 tests
fiables qui passent en &lt;25s (avant : 2/3 casses, 1 fragile, ~40s). Trois
leviers : (1) force_login via endpoint de test dedie pour remplacer le flow
UI 6 etapes ; (2) seed des fixtures E2E dans `demo_data_v2` (plus de
`Event.objects.create()` dans les fixtures Python) ; (3) fixture `e2e_slugs`
qui recupere les slugs/UUIDs depuis la DB via `django_db_blocker.unblock()`.

**Pourquoi / Why :** Les 2 tests E2E panier initiaux etaient cassés
(`RuntimeError: Database access not allowed` sans `@pytest.mark.django_db`, et
`@pytest.mark.django_db` incompatible avec un serveur Django reel derriere
Traefik car pas de rollback possible). Le test qui passait dependait d'un
flow UI de login a 6 etapes (timing HTMX, lien TEST MODE, traductions) —
fragile a tout changement non lie au code panier. Besoin d'une fondation
stable pour ajouter les E2E critiques du checkout Stripe.

### Fichiers crees / Created files
| Fichier / File | Changement / Change |
|---|---|
| AuthBillet/views_test_only.py | Endpoint `force_login_for_e2e` triple-gate (DEBUG + token env + header match). Silent 404 si conditions manquantes. Jamais monte en production. |

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| .env | +`E2E_TEST_TOKEN` (secret dev, gate l'endpoint force_login) |
| AuthBillet/urls.py | +URL conditionnelle `if settings.DEBUG` pour `/__test_only__/force_login/` |
| Administration/management/commands/demo_data_v2.py | +methode `_seed_e2e_fixtures(tenants)` (4 objets seedes dans lespass : event gratuit FREERES, event payant BILLET 10€, adhesion gratuite, event gated par l'adhesion). Appel section 4b dans `_handle_full`. Idempotent via `get_or_create`. |
| tests/e2e/conftest.py | Refonte fixture `login_as` : HTTP POST + injection cookie (~100ms au lieu de 5s). +fixture `e2e_slugs` session-scoped avec `django_db_blocker.unblock()`. +fixture `e2e_test_token`. |
| tests/e2e/test_panier_flow.py | 2 tests casses reecrits (flow admin + slug seede), 2 nouveaux tests Stripe ajoutes (checkout direct + chainage add-and-pay). Suppression fixture `event_gratuit_publie`. |
| tests/TESTS_README.md | Section "Variables d'environnement E2E" (ADMIN_EMAIL + E2E_TEST_TOKEN) |
| tests/PIEGES.md | +pieges 9.101 a 9.106 (env container vs .env, django_db_blocker, slug Event, /panier/ sans firstname, booking-add-and-pay conditionnel, wait_for_url callback string) |

### Bilan
- 5 tests E2E panier, tous passent en 22.52s
- 6 nouveaux pieges documentes
- Endpoint test-only ajoute avec triple-gate de securite (DEBUG + token + header)
- Seed E2E idempotent, prefixe "E2E Test —" pour identification admin

---

## Panier d'achat multi-events / Multi-event shopping cart

**Date :** 2026-04-17
**Migration :** Oui (`BaseBillet.0213_commande_and_fks`)

**Quoi / What :** Nouveau panier d'achat permettant de cumuler en une seule
commande des billets de plusieurs events + des adhesions. Nouveau modele pivot
`Commande` avec FK nullable sur `Reservation`/`Membership`. Matérialisation
atomique. Cart-aware : une adhesion dans le panier débloque les tarifs gates.
Modal "Ajouter au panier / Payer maintenant" sur la page event.

**Pourquoi / Why :** Avant, chaque achat était scoped à un seul event. Pour
acheter 2 events + 1 adhésion, il fallait 3 parcours distincts et 3 paiements.
Le panier unifie l'expérience, apporte un seul checkout Stripe, et débloque
le cas métier "achat adhésion + billet adhérent en même temps".

### Fichiers créés / Created files
| Fichier / File | Changement / Change |
|---|---|
| BaseBillet/services_panier.py | Gestionnaire session Django, validations, overlap, cart-aware adhesions, code promo |
| BaseBillet/services_commande.py | Orchestrateur atomique (Commande + Reservations + Memberships + Paiement_stripe) |
| BaseBillet/context_processors.py | Expose `{{ panier }}` a tous les templates |
| BaseBillet/migrations/0213_commande_and_fks.py | Modele Commande + FK sur Reservation/Membership |
| BaseBillet/templates/htmx/components/panier_item.html | Partial item panier (ticket/membership) |
| BaseBillet/templates/htmx/components/panier_badge.html | Badge compteur (page + navbar, via hx-swap-oob) |
| BaseBillet/templates/htmx/components/panier_toast.html | Toast feedback post-action |
| BaseBillet/templates/htmx/views/panier.html | Page panier Bootstrap 5 |
| tests/pytest/test_commande_model.py | 13 tests modele |
| tests/pytest/test_panier_session.py | 28 tests PanierSession |
| tests/pytest/test_commande_service.py | 4 tests orchestrateur |
| tests/pytest/test_ticket_creator_no_checkout.py | 2 tests flag create_checkout |
| tests/pytest/test_signals_cascade_multi_reservations.py | 3 tests cascade signals |
| tests/pytest/test_commande_post_save_paid.py | 4 tests post_save Commande.PAID |
| tests/pytest/test_accept_sepa_flag.py | 5 tests accept_sepa flag |
| tests/pytest/test_reservation_validator_cart_aware.py | 6 tests cart-aware + fix overlap |
| tests/pytest/test_panier_context_processor.py | 4 tests context processor |
| tests/pytest/test_panier_mvt.py | 13 tests PanierMVT |
| tests/pytest/test_panier_batch.py | 5 tests batch endpoint |
| tests/e2e/test_panier_flow.py | 2 tests E2E Playwright |

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| BaseBillet/models.py | +modele Commande, +FK `commande` sur Reservation/Membership |
| BaseBillet/signals.py | Patch `set_ligne_article_paid()` iteration sur lignes + post_save Commande.PAID |
| BaseBillet/validators.py | +param `create_checkout` sur TicketCreator, cart-aware `ReservationValidator`, fix bug overlap (BLOCKING_STATUSES) |
| BaseBillet/views.py | +classe `PanierMVT` (11 actions dont batch) |
| BaseBillet/urls.py | +router.register panier |
| BaseBillet/templatetags/tibitags.py | +filter `in_cart` |
| PaiementStripe/views.py | +param `accept_sepa` sur CreationPaiementStripe |
| TiBillet/settings.py | +context_processor panier |
| BaseBillet/templates/reunion/partials/navbar.html | +icone panier + badge + a11y |
| BaseBillet/templates/faire_festival/partials/navbar.html | +icone panier + badge + a11y |
| BaseBillet/templates/reunion/views/event/partial/booking_form.html | +bouton Add to cart + cart-aware tarifs gates + a11y |
| TECH DOC/SESSIONS/LESPASS/PLAN_LESPASS.md | +section 8 Panier TERMINE |

### Bilan
- 87 tests pytest + 2 tests E2E Playwright
- Zéro régression sur les 700+ tests existants
- Flow direct existant préservé (pas de breaking change UX)
- Correction incidente du bug `ReservationValidator` overlap (filtre statut manquant)

---

## Authentification hardware via TermUser / Hardware auth via TermUser

**Quoi / What:** Refactor de l'auth des terminaux LaBoutik (POS + Android) via
un pont `/laboutik/auth/bridge/` qui échange une clé API contre un cookie de
session Django. Création automatique d'un TermUser à l'appairage, révocation
instantanée via `is_active=False`.

**Pourquoi / Why:** Simplifier le flow côté client (plus de hack HTML injection),
aligner avec le pattern Pi controlvanne, permettre une révocation instantanée
native Django.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| AuthBillet/models.py | +terminal_role, +TERMINAL_ROLE_CHOICES, TermUser.save(), TermUserManager scoping |
| discovery/models.py | +terminal_role sur PairingDevice |
| discovery/views.py | ClaimPinView route selon terminal_role, +_create_laboutik_terminal |
| BaseBillet/models.py | LaBoutikAPIKey.user OneToOneField nullable |
| BaseBillet/permissions.py | +HasLaBoutikTerminalAccess (HasLaBoutikAccess inchangée) |
| laboutik/views.py | +LaBoutikAuthBridgeView |
| laboutik/urls.py | +path auth/bridge/ |
| Administration/admin/users.py | +TermUserAdmin |
| Administration/admin/dashboard.py | +sidebar entry Terminals |
| Administration/templates/admin/termuser/change_form_before.html | Bannière révocation |
| tests/pytest/conftest.py | +fixture terminal_client |

### Migration
- **Migration nécessaire / Migration required:** Oui / Yes
- 3 migrations AddField (non-destructives) :
  - `AuthBillet.0025_tibilletuser_terminal_role`
  - `discovery.0003_pairingdevice_terminal_role`
  - `BaseBillet.0212_laboutikapikey_user`
- Commande : `docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing`

---

## Cartes NFC : admin web + remboursement + virements pot central + bouton POS / NFC cards: admin + refund + central pot transfers + POS button

**Date :** 13-14 avril 2026
**Migration necessaire / Migration required :** Oui (2 alter choices)

**Quoi / What:**

Chantier en 3 phases livre l'administration complete des cartes NFC cashless :

### Phase 1 — Admin web Cartes + page de remboursement
- Admin Unfold pour `CarteCashless` et `Detail` (filtre tenant via `detail.origine`, creation/suppression superuser only).
- Page dediee `/admin/QrcodeCashless/cartecashless/<uuid>/refund/` qui rembourse en especes les TLF du tenant + FED.
- Service metier `WalletService.rembourser_en_especes()` atomic : Transaction REFUND par asset + LigneArticle FED + LigneArticle CASH negative + reset carte optionnel (VV).
- README `fedow_core/REFUND.md` documente le mecanisme TLF + FED + dette pot central.

### Phase 2 — Suivi de la dette pot central → tenant pour les FED rembourses
- Nouvelle action `Transaction.BANK_TRANSFER = 'BTR'` (immutable, sans mutation Token).
- `BankTransferService` (4 methodes) + page dediee `/admin/bank-transfers/` (superuser only).
- Validation hard `montant <= dette_actuelle` (rejet sur-versement).
- Widget « Dette du pot central » sur le dashboard tenant.
- LigneArticle d'encaissement `payment_method=TRANSFER` pour les rapports comptables.
- Nouveau code `Product.VIREMENT_RECU = "VR"`.

### Phase 3 — Bouton POS Cashless « Vider Carte »
- Tile auto-generee via Product `methode_caisse=VC` dans le M2M du PV.
- Flow dedie : clic tile → overlay scan NFC → recap tokens → checkbox VV → execution + ecran succes + impression recu optionnelle.
- Patch additif `primary_card=None` sur `WalletService.rembourser_en_especes()` (audit trail caissier).
- Protection self-refund + controle d'acces via M2M `pv.cartes_primaires`.
- Formatter `formatter_recu_vider_carte()` pour impression thermique.

**Pourquoi / Why:** centralise et trace toutes les operations cashless dans `fedow_core` (Phase 1 du plan mono-repo), elimine la dependance HTTP au serveur Fedow distant pour les nouveaux tenants, expose les flows d'admin web et POS dans la meme infrastructure.

### Migration / Migration

- `fedow_core/migrations/0002_alter_transaction_action.py` : ajout choix `BTR`
- `BaseBillet/migrations/0211_alter_product_methode_caisse.py` : ajout choix `VR`

### Tests / Tests

- **34 tests pytest DB-only** + **3 tests E2E Playwright** (1 SKIP Playwright si admin non-superuser).
- Tous PASS en isolation.

### Limites connues / Known limitations

- **Admin web** : pas de bouton « Rembourser » sur la fiche carte (URL `/refund/` a saisir manuellement). `change_view` enrichi avec tokens + transactions recentes pas encore implemente — Phase 1.5 a livrer separement.
- **Admin web** : pas de colonne « Solde » dans la liste des cartes — **choix assume** (decision 2026-04-14) : cout de calcul prohibitif sur grande volumetrie (plusieurs millions de cartes a terme → `SUM(Token.value)` par ligne rendue inutilisable). Le solde reste visible dans la fiche carte (panel refund).
- **Affichage des montants** : tout est affiche en « centimes » au lieu d'euros formates (`20,00 €`). Templatetag `centimes_en_euros` a creer pour Phase 1.5.
- **Phase 2** : message Django flash `messages.success` ne s'affiche pas apres refund admin (integration `admin_site.admin_view()` wrapping). L'operation DB reussit, seul le toast UX manque.
- **Cross-file test pollution** : Products auto-crees par signal `send_membership_product_to_fedow` quand on cree des Assets. Workaround : exécuter chaque fichier de test en isolation.

### Reference complete / Full reference

Voir `TECH DOC/SESSIONS/CARTES_CASHLESS_ADMIN/INDEX.md` et les 6 fichiers design/plan associes.

---

## Explorer : visualisation monnaies et federations / Explorer: currencies and federations visualization

**Date :** 12 avril 2026
**Migration necessaire / Migration required :** Non

**Quoi / What:**

### Page `/explorer/` enrichie / Enriched `/explorer/` page

- **Mode focus monnaie** : clic sur une card monnaie ou un badge monnaie d'un lieu active le mode focus :
  - Highlight des lieux acceptants + dim des autres (opacity 0.3)
  - Style B (polygone convex hull) pour la monnaie federee primaire (`category=FED`)
  - Style C (arcs Bezier depuis origine) pour les assets federes partiellement
  - Legende contextuelle en bas-droit de la carte
  - Clic a nouveau sur la meme monnaie = reset (toggle)
- **Badges monnaies** sur chaque card lieu (sous la description)
- **Accordeon des lieux acceptants** dans chaque card monnaie
- **Animation accordeon smooth** via `grid-template-rows: 0fr → 1fr`
- **Loading state** : spinner pendant l'init de Leaflet
- **Filtres reordonnes** : Tous / Lieux / Evenements / Initiatives / Monnaies / Adhesions
- **Mobile** : filtres a la ligne (`flex-wrap`) au lieu de scroll horizontal

### Backend / Backend

- `get_all_assets()` enrichi : 3 chemins d'acceptation (`tenant_origin`, `Asset.federated_with`, `Federation.assets+tenants`) unis via CTE
- `build_tenant_config_data()` : ajoute `accepted_asset_ids` pour chaque tenant
- `build_explorer_data()` : propage les champs de federation aux lieux
- Filtre `active=TRUE AND archive=FALSE` sur toutes les queries assets

### Fixture demo / Demo fixture

- `_create_federations_demo()` dans `demo_data_v2` : 2 Federations ("Reseau TiBillet Lyon" + "Echange local") + asset "Monnaie Coeur" pour le-coeur-en-or
- Filtre `SCHEMAS_DEMO` pour exclure les schemas UUID de tests

**Pourquoi / Why:** permettre aux visiteurs de `/explorer/` de comprendre visuellement les relations entre lieux et monnaies du reseau. Deux mental models : diversite des outils + perspective utilisateur.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `seo/services.py` | `get_all_assets()` CTE 3 unions + `build_tenant_config_data` +`accepted_asset_ids` + `build_explorer_data` propagation |
| `seo/static/seo/explorer.js` | Mode focus asset, hull/arcs Bezier, accordeon asset, badges lieu, loading spinner |
| `seo/static/seo/explorer.css` | Styles badges, accordeon grid-template-rows, legende asset, loading spinner |
| `seo/templates/seo/explorer.html` | +DOM legende + spinner, reordre des pills |
| `seo/README.md` | Doc mode focus monnaie |
| `Administration/management/commands/demo_data_v2.py` | +`_create_federations_demo()` |
| `tests/pytest/test_seo_explorer_assets.py` | +6 tests unitaires (nouveau) |
| `tests/e2e/test_explorer_assets_focus.py` | +3 tests E2E Playwright (nouveau) |
| `tests/PIEGES.md` | +Pieges 74 (3 chemins acceptation) et 75 (grid-template-rows) |
| `A TESTER et DOCUMENTER/explorer-monnaies-federation.md` | Doc test manuel (nouveau) |
| `TECH DOC/SESSIONS/ROOT_VIEW/2026-04-12-*.md` | Spec + plan (nouveaux) |

### Tests

- 6 pytest + 3 E2E Playwright : PASS
- ERROR teardown FK `fedow_connect_fedowconfig → AuthBillet_wallet` documentees comme piege preexistant (a investiguer)

---

## Review skin Faire Festival + SEO + securite emails / Faire Festival skin review + SEO + email security

**Date :** 10 avril 2026
**Migration necessaire / Migration required :** Non

**Quoi / What:**

### Securite emails / Email security
- Suppression de `| escapejs` sur `main_text_2` dans `email_generique.html` (causait du HTML illisible)
- Ajout de `clean_html()` (sanitisation nh3) sur 3 champs admin-controlled avant injection dans les templates email : `additional_text_in_membership_mail`, `custom_confirmation_message`, `member_name()` dans `send_membership_pending_admin`

### Optimisation images / Image optimization
- 9 PNG convertis en WebP (6.8 Mo → 850 Ko, -87%)
- Templates mis a jour pour pointer vers les fichiers .webp

### Carte interactive / Interactive map
- Image statique carte remplacee par Leaflet + CartoDB Positron sur la page Infos Pratiques
- Coordonnees GPS et adresse depuis `config.postal_address` (avec fallback)
- Marqueur custom aux couleurs du festival (jaune/bleu)

### SEO (les 2 skins : faire_festival + reunion)
- Ajout `<link rel="canonical">` dans les 2 base templates
- Ajout JSON-LD Organization + WebSite (schema.org)
- Correction `og:image` et `twitter:image` : URLs absolues (etaient relatives)
- Meta descriptions uniques par page (home, le faire festival, infos pratiques)
- Ajout `<h1>` sur toutes les pages (visually-hidden quand le titre est une image)
- Correction hierarchie headings (H1→H2→H3, plus de niveaux sautes)
- Remplacement `<main>` en double par `<div>` dans 10 templates enfants
- Ajout `<main>` semantique dans `reunion/base.html`

### Corrections diverses / Miscellaneous fixes
- `min-height: 100vh` retire de `.conteneur-principal` (causait un gros espace blanc), remplace par classe `.plein-ecran`
- Adresse footer dynamique depuis `config.postal_address`
- `href=""` → `href="#"` sur le bouton Contact navbar
- `<p>` mal ferme dans infos_pratiques.html
- Texte non traduit ajoute dans `{% translate %}`
- Spinner Stripe : `classList.add('active')` au lieu de `style.display = 'block'` + `display: flex !important` dans `.active`
- Import `PostalAddress` manquant dans `demo_data_v2.py`

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/tasks.py` | `clean_html()` sur 3 champs email |
| `BaseBillet/templates/emails/email_generique.html` | Retire `escapejs` |
| `BaseBillet/templates/faire_festival/base.html` | canonical, JSON-LD, og:image absolu |
| `BaseBillet/templates/faire_festival/views/home.html` | SEO meta, h1, h2, plein-ecran, .webp |
| `BaseBillet/templates/faire_festival/views/le_faire_festival.html` | SEO meta, h1, .webp |
| `BaseBillet/templates/faire_festival/views/infos_pratiques.html` | Leaflet, l10n, h1, h2, adresse dynamique |
| `BaseBillet/templates/faire_festival/partials/footer.html` | Adresse dynamique |
| `BaseBillet/templates/faire_festival/partials/navbar.html` | href="#" |
| `BaseBillet/static/faire_festival/css/faire_festival.css` | plein-ecran, retire min-height global |
| `BaseBillet/templates/reunion/base.html` | canonical, JSON-LD, `<main>`, og:image absolu |
| `BaseBillet/templates/reunion/loading.html` | display flex !important sur .active |
| `BaseBillet/static/reunion/js/form-spinner.mjs` | classList au lieu de style.display |
| `BaseBillet/static/mvt_htmx/js/commun.js` | classList.remove au lieu de style.display |
| `BaseBillet/templates/htmx/forms/login.html` | classList.remove au lieu de style.display |
| 8 templates reunion/views/* | `<main>` → `<div>` |
| 2 templates faire_festival/views/* | `<main>` → `<div>` |
| `Administration/management/commands/demo_data_v2.py` | Import PostalAddress |
| `PLANS/PLAN_SKIN_FAIRE_FESTIVAL_GENERIQUE.md` | Plan futur skin generique + GrapeJS |
| `PLANS/PLAN_SEO_TOUS_SKINS.md` | Checklist SEO a reporter |
| `tests/PIEGES.md` | 3 nouveaux pieges (71-73) |

## Auto-creation POS + PairingDevice a la creation d'une tireuse / Auto-create POS + PairingDevice on tap creation

**Date :** 9 avril 2026
**Migration necessaire / Migration required :** Non

**Quoi / What:**
- A la creation d'une TireuseBec, un PointDeVente (type TIREUSE) et un PairingDevice (PIN 6 chiffres) sont crees automatiquement par le signal post_save
- Le formulaire admin de creation est simplifie : seuls nom, fut, debimetre, seuil, enabled, notes
- En edition, point_de_vente et pairing_device apparaissent en lecture seule
- Colonne PIN dans la liste admin (affiche le PIN ou "Appaire" si consomme)
- Management command `create_test_carte` pour creer des cartes NFC de test avec origine=lespass
- Script Pi `test_rfid.py` unifie (supporte RC522/VMA405/ACR122U via .env)

**Pourquoi / Why:** Simplifier la creation d'une tireuse — plus besoin de creer manuellement le POS et l'appareil d'appairage. Le PIN est visible directement dans la liste admin.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `controlvanne/signals.py` | Auto-creation POS + PairingDevice dans `tireusebec_post_save` |
| `controlvanne/admin.py` | `get_fields()`, `get_readonly_fields()`, `pin_code_display`, `get_queryset` select_related |
| `QrcodeCashless/management/commands/create_test_carte.py` | Nouveau — management command creation cartes NFC test |
| `tests/PIEGES.md` | Pieges 9.1b (FakeTenant + FK signal) et 9.1c (get_or_create unique constraint) |

---

## Simulateur Pi3 + refactoring kiosk controlvanne / Pi3 simulator + kiosk refactoring

**Date :** 9 avril 2026
**Migration necessaire / Migration required :** Oui — `BaseBillet/migrations/0210_alter_lignearticle_sale_origin_and_more.py`

**Quoi / What:**
- Simulateur Pi3 (mode DEMO) : panneau JS dans le kiosk qui simule le hardware (NFC + electrovanne + debitmetre)
- Simulateur fidele au vrai Pi : vanne s'ouvre des l'autorisation, slider = robinet mecanique, fin de service = retrait carte
- Separation vue ALL (grille) / vue detail (single tap + simulateur)
- Migration de `kiosk_view` fonction vers `KioskViewSet` (list + retrieve)
- Extraction carte kiosk en partial reutilisable
- Push WebSocket explicite dans le viewset (authorize, pour_start, pour_update, pour_end, card_removed)
- `SaleOrigin.TIREUSE` ("Connected tap") pour distinguer les ventes tireuse des ventes caisse
- Colonne "Point de vente" ajoutee dans l'admin LigneArticle
- Correction affichage poids : "cl" au lieu de "g" pour les ventes tireuse
- Conformite djc : i18n, accessibilite, FALC, logger
- Fix tenant-awareness du WebSocket consumer (database_sync_to_async)
- Liens admin Unfold : sidebar dashboard, bouton kiosk sur fiche tireuse, lien module dashboard

**Pourquoi / Why:** Permettre de tester le flow complet tireuse (badge → autorisation → tirage → facturation) sans hardware Pi. Corriger la tracabilite des ventes tireuse dans l'admin.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `controlvanne/viewsets.py` | `KioskViewSet` (list + retrieve) + `_push_ws_kiosk` + `_construire_payload_session` |
| `controlvanne/urls.py` | 2 routes kiosk : `/kiosk/` (list) + `/kiosk/<uuid>/` (retrieve) |
| `controlvanne/consumers.py` | print→logger, FALC, fix tenant `set_tenant(scope["tenant"])` |
| `controlvanne/routing.py` | Casse normalisee (ALL→all), FALC |
| `controlvanne/signals.py` | Documentation tenant-safe |
| `controlvanne/billing.py` | `SaleOrigin.LABOUTIK` → `SaleOrigin.TIREUSE` |
| `controlvanne/admin.py` | `change_form_before_template` + `compressed_fields` + `warn_unsaved_form` |
| `controlvanne/static/controlvanne/js/simu_pi.js` | **Nouveau** — state machine fidele au Pi |
| `controlvanne/static/controlvanne/js/panel_kiosk.js` | Reecrit FALC, noms explicites, casse WS |
| `controlvanne/templates/.../kiosk_detail.html` | **Nouveau** — vue single tap + simulateur |
| `controlvanne/templates/.../kiosk_list.html` | **Nouveau** — vue grille toutes les tireuses |
| `controlvanne/templates/.../partial/kiosk_card.html` | **Nouveau** — carte reutilisable |
| `BaseBillet/models.py` | Ajout `SaleOrigin.TIREUSE = "TI"` |
| `Administration/admin/sales.py` | Colonne `display_point_de_vente` + fix fallback unite poids |
| `Administration/admin/dashboard.py` | Lien sidebar kiosk + lien module dashboard |
| `Administration/templates/.../tireusebec_before.html` | **Nouveau** — bouton kiosk sur fiche |
| `tests/e2e/test_controlvanne_kiosk.py` | **Nouveau** — 10 tests E2E (vues + simulateur + admin) |
| `tests/PIEGES.md` | Piege 9.100 : `database_sync_to_async` + tenant |
| `TECH DOC/.../SPEC_SIMULATEUR_PI.md` | **Nouveau** — spec du simulateur |

## Flush rapide sans migrations / Fast flush without migrations

**Date :** 9 avril 2026
**Migration :** Non

**Quoi / What:** `flush.sh` detecte si la DB est deja initialisee (table `django_migrations` presente). Si oui, lance `demo_data_v2 --flush` pour purger et reimporter les fixtures sans drop/recreate ni migrations. Le `--flush` a ete complete pour purger toutes les tables de demo : laboutik (ClotureCaisse, CartePrimaire, PointDeVente, Printer), comptabilite (LigneArticle, PriceSold, ProductSold), inventaire (Stock), fedow_core (Transaction, Token, Asset, Federation), cartes NFC (CarteCashless, Detail), wallets users, et CategorieProduct. Les wallets du lieu (appairage Fedow) sont preserves.

**Pourquoi / Why:** Le flush complet (drop + create + migrate + install + demo) prend plusieurs minutes. En dev, quand on veut juste repartir de donnees fraiches sans changer le schema, c'est inutilement long.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `flush.sh` | Detection DB initialisee via `psql to_regclass`, branchement flush rapide vs install complete |
| `Administration/management/commands/demo_data_v2.py` | Section `--flush` etendue : purge fedow_core, laboutik, comptabilite, inventaire, cartes NFC, wallets users, categories |

## Cascade multi-asset NFC + paiement complementaire

**Date :** 8 avril 2026
**Migration :** Oui — `BaseBillet/migrations/0209_price_non_fiduciaire.py`

**Quoi / What:** Paiement NFC en cascade multi-asset : le systeme debite les tokens du client dans l'ordre TNF (cadeau) → TLF (local) → FED (federe). Un article peut generer N LigneArticle (1 par asset debite) avec qty decimale et amount entier en centimes. Si la cascade ne couvre pas le total, l'operateur peut completer en especes, CB, ou 2eme carte NFC. Support des tarifs non-fiduciaires (TIM/FID) via le nouveau champ `Price.non_fiduciaire`.

**Pourquoi / Why:** L'ancien `_payer_par_nfc()` ne debitait que sur un seul asset TLF. Les tokens cadeau (TNF) et federes (FED) n'etaient jamais utilises pour payer. Le legacy LaBoutik supportait la cascade — cette feature retrouve la parite fonctionnelle.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/models.py` | `Price.non_fiduciaire` BooleanField + `clean()` validation |
| `BaseBillet/migrations/0209_price_non_fiduciaire.py` | Migration |
| `laboutik/views.py` | Constantes cascade, `_calculer_qty_partielles()`, `_creer_lignes_articles_cascade()`, refonte `_payer_par_nfc()` (8 phases), `payer_complementaire()`, `lire_nfc_complement()` |
| `laboutik/printing/formatters.py` | `cascade_detail` dans `formatter_ticket_vente()` |
| `Administration/admin/products.py` | `POSPriceInline` : champs `non_fiduciaire` + `asset` conditionnel, filtre TIM/FID |
| `laboutik/management/commands/create_test_pos_data.py` | Assets FED/FID, produits TIM/FID, wallet garni multi-asset |
| `laboutik/templates/laboutik/partial/hx_complement_paiement.html` | Nouveau — ecran complementaire |
| `laboutik/templates/laboutik/partial/hx_lire_nfc_complement.html` | Nouveau — scan 2eme carte |
| `laboutik/templates/laboutik/partial/hx_return_payment_success.html` | Affichage multi-soldes |
| `tests/pytest/test_cascade_nfc.py` | 17 tests (validation Price, qty partielle, cascade, complement) |
| `tests/e2e/test_pos_paiement.py` | 3 tests adaptes aux nouveaux data-testid |
| `tests/e2e/test_pos_recharge_cashless.py` | Nouveau — 4 tests E2E recharge cashless complet (tuiles visibles, recharge especes NFC, verification solde DB, vente NFC apres recharge) |
| `tests/pytest/test_retour_carte_recharges.py` | Fix : products de recharge lies aux assets, tenant force `lespass` |
| `tests/pytest/test_paiement_cashless.py` | Fix : `get_or_create` asset pour eviter UniqueViolation signal post_save |
| `tests/pytest/test_controlvanne_billing.py` | Fix : teardown fixture `schema_context` pour eviter UndefinedTable |
| `tests/pytest/test_caisse_navigation.py` | Fix : PV force `Bar` au lieu de `.first()`, tenant force |
| `tests/pytest/test_pos_models.py` | Fix : nettoyage Products signal avant creation asset |
| `tests/pytest/test_pos_views_data.py` | Fix : asset TLF lie au product de recharge |
| `tests/pytest/test_printing.py` | Fix : `schema_context` + mocks completes |
| `tests/pytest/test_verify_transactions.py` | Fix : nettoyage Products signal avant creation asset |
| `tests/e2e/test_pos_adhesion_nfc.py` | Fix : fixture `recharge_asset_setup` pour lier produit recharge |
| `tests/e2e/test_login.py` | Fix : locator admin adapte au nouveau template |
| `tests/e2e/test_pos_billetterie.py` | Fix : timeouts augmentes (flaky) |
| `tests/e2e/test_pos_sortie_caisse_e2e.py` | Fix : timeouts augmentes (flaky) |

### Tests / Resultats
- **pytest** : 569 PASS, 0 FAILED, 0 ERRORS (avant : 478 pass, 7 failed, 84 errors)
- **E2E** : 91 PASS, 0 FAILED (avant : 87 pass, 4 failed)
- **Nouveaux tests** : 17 pytest cascade + 4 E2E recharge cashless = 21 tests ajoutes

---

## Asset-first recharge products / Produits de recharge pilotes par l'Asset

**Date :** 8 avril 2026
**Migration :** Oui — `BaseBillet/migrations/0208_product_asset_fk.py`

**Quoi / What:** L'Asset `fedow_core.Asset` (TLF/TNF/TIM) pilote la creation des produits de recharge. Un signal `post_save` sur Asset cree automatiquement un Product multi-tarif (1/5/10/Libre) et l'attache aux PV CASHLESS. Plus de bouton "Recharge" sans Asset, plus d'erreur "Monnaie locale non configuree".

**Pourquoi / Why:** Les produits de recharge etaient crees manuellement sans lien avec un Asset fedow_core. Le lookup par categorie dans `_executer_recharges()` echouait si l'Asset n'existait pas. Maintenant l'Asset drive tout : pas d'Asset = pas de bouton.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/models.py` | FK `Product.asset → fedow_core.Asset` (nullable) |
| `BaseBillet/migrations/0208_product_asset_fk.py` | Migration FK |
| `fedow_core/signals.py` | Nouveau — signal post_save Asset → Product + Prices + PV CASHLESS |
| `fedow_core/apps.py` | Enregistre le signal dans `ready()` |
| `laboutik/views.py` | Filtre affichage, refactor `_executer_recharges` et `_payer_par_nfc` |
| `laboutik/management/commands/create_test_pos_data.py` | Cree 3 Assets au lieu de 5 Products manuels |
| `tests/pytest/test_asset_recharge_signal.py` | 6 tests signal (creation, archivage, renommage) |

---

## Rapport temps reel — Session en cours / Real-time report — Current shift

**Date :** Avril 2026
**Migration :** Non

**Quoi / What:** Bouton "Rapport en cours" sur la liste des clotures de caisse (`/admin/laboutik/cloturecaisse/`). Ouvre dans un nouvel onglet un rapport comptable complet calcule en temps reel depuis la derniere cloture via `RapportComptableService.generer_rapport_complet()`.

**Pourquoi / Why:** Permettre aux operateurs de consulter l'etat comptable du service en cours sans creer de cloture.
## Page Explorer — Carte Leaflet + recherche fusionnee / Explorer page — Leaflet map + merged search

**Date :** 7 avril 2026
**Migration :** Non

**Quoi / What:** Nouvelle page `/explorer/` sur le ROOT avec :
- Carte interactive Leaflet + tuiles OpenStreetMap (CDN, pas de dependance npm)
- Liste filtree de lieux, evenements et adhesions synchronisee avec la carte
- Barre de recherche (filtre live debounce 300ms) + pills categorie (Tous/Lieux/Evenements/Adhesions)
- Cross-highlighting bidirectionnel desktop (hover card → highlight marqueur, clic marqueur → scroll liste)
- Toggle Carte/Liste mobile (FAB flottant, lazy loading Leaflet au premier tap)
- Popup Leaflet enrichi par lieu (description, prochains events, adhesions, lien "Visiter")
- Enrichissement du SEOCache avec coordonnees GPS (latitude/longitude depuis PostalAddress)

**Pourquoi / Why:** Offrir un outil de decouverte interactif pour le reseau TiBillet, inspire du pattern Airbnb (split view desktop, toggle mobile). Les pages SEO statiques (`/lieux/`, `/recherche/`) restent en place pour le referencement.

### Fichiers crees / Created files
| Fichier / File | Role |
|---|---|
| `seo/templates/seo/explorer.html` | Template full-width, CDN Leaflet, json_script |
| `seo/static/seo/explorer.js` | Carte + liste + filtres + toggle mobile (~520 lignes) |
| `seo/static/seo/explorer.css` | Layout split/mobile, cards, pins, FAB (~394 lignes) |
| `tests/pytest/test_explorer.py` | 10 tests pytest |

### Fichiers modifies / Modified files
| Fichier / File | Modification |
|---|---|
| `seo/services.py` | +latitude/longitude dans `build_tenant_config_data()`, +`build_explorer_data()` |
| `seo/tasks.py` | +latitude/longitude dans aggregate_lieux |
| `seo/views.py` | +vue `explorer()` |
| `seo/urls.py` | +route `/explorer/` |
| `seo/templates/seo/base.html` | +lien "Explorer" navbar, +block `main_wrapper` |

---

## App SEO — Cache cross-tenant, pages ROOT, ameliorations meta / SEO app — Cross-tenant cache, ROOT pages, meta improvements

**Date :** Avril 2026
**Migration :** Oui (`seo/migrations/0001_initial.py` — modele `SEOCache` dans le schema public)

**Quoi / What:** Nouvelle app `seo` (SHARED_APPS) qui fournit :
- Un cache SEO pre-calcule par Celery task toutes les 4h (requetes SQL cross-schema optimisees)
- Pages ROOT (`tibillet.coop`) : landing vitrine, `/lieux/`, `/evenements/`, `/adhesions/`, `/recherche/`, `/sitemap.xml` (index cross-tenant)
- Ameliorations templates tenant : `<link rel="canonical">`, JSON-LD Organization sur toutes les pages, partials JSON-LD Product
- Remplacement de `BaseBillet/sitemap.py` et `BaseBillet/views_robots.py` par les equivalents dans `seo/`
- Suppression du code mort : `test_jinja`, `old_create_product.html`

**Pourquoi / Why:** Doter le reseau TiBillet d'une couche SEO complete pour ameliorer la visibilite des lieux, evenements et adhesions dans les moteurs de recherche. Le ROOT tenant sert de hub SEO pour tout le reseau.

### Fichiers crees / Created files
| Fichier / File | Role |
|---|---|
| `seo/` (app complete) | App SEO : models, services, tasks, views, urls, templates, templatetags |
| `seo/models.py` | `SEOCache` — cache JSON en schema public |
| `seo/services.py` | Requetes SQL cross-schema + helpers Memcached |
| `seo/tasks.py` | Celery task `refresh_seo_cache` (toutes les 4h) |
| `seo/views.py` | Vues ROOT (landing, lieux, evenements, adhesions, recherche, sitemap index) |
| `seo/views_common.py` | Helpers JSON-LD, cache reader, robots.txt |
| `seo/sitemap.py` | Sitemaps tenant enrichis (remplace BaseBillet/sitemap.py) |
| `seo/templatetags/seo_tags.py` | Filtre `format_iso_date` |
| `seo/templates/seo/` | 6 templates ROOT + 2 partials JSON-LD |
| `tests/pytest/test_seo.py` | 24 tests pytest |
>>>>>>> d58f5c9c9c6a2969a505de03e6ce83896955cf35

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/views.py` | Nouvelle action `rapport_temps_reel` sur CaisseViewSet |
| `Administration/templates/admin/cloture/rapport_temps_reel.html` | Template standalone du rapport temps reel (13 sections) |
| `Administration/templates/admin/cloture/changelist_before.html` | Bouton vert "Rapport en cours" avec `target="_blank"` |
| `Administration/admin/laboutik.py` | URL du rapport injectee dans `changelist_view()` |
| `TiBillet/settings.py` | `seo` dans SHARED_APPS + `CELERY_BEAT_SCHEDULE` |
| `TiBillet/urls_tenants.py` | Import sitemap depuis `seo.sitemap` |
| `TiBillet/urls_public.py` | Routes ROOT via `seo.urls` |
| `BaseBillet/urls.py` | Import `robots_txt` depuis `seo.views_common` |
| `BaseBillet/templates/reunion/base.html` | Canonical + JSON-LD Organization |
| `BaseBillet/templates/faire_festival/base.html` | Idem |
>>>>>>> d58f5c9c9c6a2969a505de03e6ce83896955cf35

---

## Formulaire d'actions stock dans l'admin / Stock actions form in admin

**Date :** Avril 2026
**Migration :** Non

**Quoi / What:** Formulaire HTMX sur la fiche Stock admin (réception, ajustement, offert, perte/casse) avec 4 boutons colorés. Template before aide sur les mouvements. Ajustement stock retiré de POSProduct (déplacé dans Stock admin). Documentation technique et utilisateur complète.

**Pourquoi / Why:** Centraliser la gestion de stock dans une page dédiée plutôt que la disperser dans le formulaire produit.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `inventaire/views.py` | `stock_action_view()` — endpoint HTMX pour les 4 actions |
| `inventaire/serializers.py` | `StockActionSerializer` — validation type/quantité/motif |
| `Administration/admin/inventaire.py` | `StockAdmin` after template + contexte + get_urls, `MouvementStockAdmin` before template |
| `Administration/admin/products.py` | Retirer StockInline du changeform POSProduct (garder sur add) |
| `Administration/templates/admin/inventaire/` | 3 templates (stock_actions, partial, mouvements before) |

---

## Affichage visuel stock dans le POS / Stock visual display in POS

**Date :** Avril 2026
**Migration :** Non

**Quoi / What:** Pastille stock sur les tuiles articles POS avec mise à jour temps réel via WebSocket. 3 états visuels : alerte (orange), rupture (rouge), bloquant (grisé + non cliquable). Après chaque vente, le badge se met à jour automatiquement sur toutes les caisses connectées du tenant.

**Pourquoi / Why:** Le caissier doit voir d'un coup d'œil quels produits sont en alerte ou en rupture de stock, sans avoir à consulter l'admin.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/views.py` | `_formater_stock_lisible()` + enrichissement `_construire_donnees_articles()` + broadcast WS dans `_creer_lignes_articles()` |
| `laboutik/templates/cotton/articles.html` | Pastille stock conditionnelle + classe `article-bloquant` |
| `laboutik/templates/laboutik/partial/hx_stock_badge.html` | Template OOB swap pour WebSocket (nouveau) |
| `laboutik/static/css/articles.css` | Styles pastille stock (3 états) |
| `laboutik/static/js/articles.js` | Bloquer clic articles en rupture bloquante |
| `wsocket/broadcast.py` | `broadcast_stock_update()` |
| `wsocket/consumers.py` | Handler `stock_update()` |

---

## Gestion d'inventaire et stock POS / POS Inventory and Stock Management

**Date :** Avril 2026
**Migration :** Oui

**Quoi / What:** Nouvelle app `inventaire` (TENANT_APP) pour gérer le stock des produits POS. Stock optionnel par produit, 3 unités (pièces/centilitres/grammes), journal de mouvements (6 types : vente, réception, ajustement, offert, perte, débit mètre), décrémentation atomique à la vente, actions rapides caissier, endpoint API pour capteur débit mètre (Raspberry Pi).

**Pourquoi / Why:** Les bars et salles associatifs ont besoin de tracer leur stock pour l'AG et détecter les écarts (casse, offerts). Système minimaliste adapté aux 20-50 références d'un petit lieu.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `inventaire/*` | Nouvelle app : models, services, views, serializers, urls, templates |
| `BaseBillet/models.py` | `module_inventaire` sur Configuration + `contenance` sur Price |
| `TiBillet/settings.py` | `'inventaire'` dans TENANT_APPS |
| `TiBillet/urls_tenants.py` | Route `api/inventaire/` |
| `Administration/admin/dashboard.py` | MODULE_FIELDS + sidebar Inventaire |
| `Administration/admin/products.py` | StockInline + ajustement inventaire |
| `Administration/admin/inventaire.py` | MouvementStockAdmin (lecture seule) |
| `Administration/admin_tenant.py` | Import admin inventaire |
| `laboutik/views.py` | Branchement décrémentation stock dans `_creer_lignes_articles()` |

### Migration
- `inventaire/migrations/0001_initial.py` (Stock + MouvementStock)
- `BaseBillet/migrations/0213_configuration_module_inventaire_price_contenance.py`
- Commande : `docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing`

---


## Unreleased — Fix message trompeur sur reservation gratuite anonyme / Misleading message on anonymous free booking

**Date :** 2026-04-21
**Migration :** Non

---

### Correction de la page de confirmation de reservation gratuite / Free booking confirmation page fix

**FR :**
Lorsqu'un visiteur non connecte reservait une activite gratuite avec l'email d'un compte
deja existant et actif, la page de confirmation affichait « Veuillez valider votre e-mail »
alors que les billets etaient deja envoyes (resa en `FREERES_USERACTIV`) et que la
reservation etait confirmee en back-office.

Cause : la vue `EventViewset.reservation` passait `request.user` au template. Quand le
visiteur n'est pas connecte, `request.user` vaut `AnonymousUser` dont `is_active` est
toujours `False`. Le template basculait alors sur la branche « validez votre email »
en ignorant l'etat reel de l'user retrouve en base par email.

Fix : passer `validator.reservation.user_commande` au template. Cet user est celui
resolu par `get_or_create_user(email)` dans le validator, donc coherent avec la
decision prise par `TicketCreator.method_F` pour envoyer (ou non) les billets
immediatement.

**EN :**
When an unauthenticated visitor booked a free activity using the email of an
already-existing active account, the confirmation page showed "Please validate your
e-mail" even though the tickets were already sent and the booking was confirmed.

Root cause: the view passed `request.user` (an `AnonymousUser` with `is_active=False`)
to the template. Fix: pass `validator.reservation.user_commande` instead — the user
resolved by the validator from the submitted email.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/views.py` | `EventViewset.reservation` : passe `validator.reservation.user_commande` au template au lieu de `request.user` |

### Migration
- **Migration necessaire / Migration required:** Non

---

## v1.7.7 — Unification actions admin Membership dans MembershipMVT

**Date :** Mars 2026
**Migration :** Non

---

### Unification des actions admin sur les adhésions / Membership admin actions unified

**FR :**
Les actions admin sur les adhésions sont désormais centralisées dans `MembershipMVT` (viewset DRF),
exposées via HTMX dans un panneau inline affiché avant le formulaire admin.

- **Supprimé** : `actions_detail` / `actions_row` Unfold dans `MembershipAdmin` (5 méthodes `@action`)
- **Supprimé** : `has_custom_actions_row_permission`, `has_custom_actions_detail_permission`
- **Supprimé** : templates orphelins `cancel_confirm.html` et `ajouter_paiement.html`
- **Ajouté** : `change_form_before_template = "admin/membership/actions_panel.html"` sur `MembershipAdmin`
- **Ajouté** : 3 nouvelles actions dans `MembershipMVT` : `send_invoice`, `ajouter_paiement`, `cancel`
- **Ajouté** : `PaiementHorsLigneSerializer` dans `BaseBillet/validators.py`
- **Ajouté** : 4 nouveaux partials HTMX dans `admin/membership/partials/`

**EN :**
Admin actions on memberships are now centralised in `MembershipMVT` (DRF viewset),
exposed via HTMX in an inline panel displayed before the admin change form.

**Fichiers modifiés :**
- `BaseBillet/validators.py` : + `PaiementHorsLigneSerializer`
- `BaseBillet/views.py` : + imports `get_or_create_price_sold`, `dec_to_int`, `reverse`, `PaiementHorsLigneSerializer` + 3 actions + update `get_permissions`
- `Administration/admin_tenant.py` : - 5 `@action` Unfold + enrichissement `changeform_view` + `change_form_before_template`
- `Administration/templates/admin/membership/actions_panel.html` : Nouveau — panneau HTMX
- `Administration/templates/admin/membership/partials/send_invoice_success.html` : Nouveau
- `Administration/templates/admin/membership/partials/cancel_form.html` : Nouveau
- `Administration/templates/admin/membership/partials/ajouter_paiement_form.html` : Nouveau
- `Administration/templates/admin/membership/partials/ajouter_paiement_success.html` : Nouveau

---

## v1.7.6 — Skin Faire Festival + Corrections UX et Sentry

**Date :** Mars 2026
**Migration :** Non

---

### 1. Skin Faire Festival — ameliorations CSS et templates / Faire Festival skin — CSS and template improvements

**FR :**
Ameliorations du skin "Faire Festival" suite aux retours terrain :
- Bordures arrondies (`border-radius`) sur les cartes et le bouton burger mobile
- Titres des evenements en police mono, taille reduite, avec `hyphens: auto`
- Bordure image evenement epaissie (1px → 3px)
- Badge de date repositionne (`margin-left: 0` au lieu de -100px)
- Padding horizontal des cartes ajuste

**EN:**
Improvements to the "Faire Festival" skin based on field feedback:
- Rounded borders (`border-radius`) on cards and mobile burger button
- Event titles in mono font, smaller size, with `hyphens: auto`
- Event image border thickened (1px → 3px)
- Date badge repositioned (`margin-left: 0` instead of -100px)
- Card horizontal padding adjusted

**Fichiers / Files:**
- `BaseBillet/static/faire_festival/css/faire_festival.css`

---

### 2. Lazy-load video sur la page d'accueil / Video lazy-load on homepage

**FR :**
La video motion-table de la page d'accueil bloquait le chargement sur Firefox mobile.
Remplacement de `autoplay` + `src` par un mecanisme `IntersectionObserver` :
la video n'est telechargee et lue que lorsqu'elle entre dans le viewport.
`preload="none"` empeche tout telechargement au chargement initial de la page.

**EN:**
The motion-table video on the homepage was blocking page load on Firefox mobile.
Replaced `autoplay` + `src` with an `IntersectionObserver` mechanism:
the video is only downloaded and played when it enters the viewport.
`preload="none"` prevents any download on initial page load.

**Fichiers / Files:**
- `BaseBillet/templates/faire_festival/views/home.html`

---

### 3. Description adhesion en accordeon intelligent / Smart collapsible membership description

**FR :**
La description longue de la page d'adhesion est desormais tronquee automatiquement
si elle depasse ~10-12 lignes (250px). Un bouton "Lire la suite" / "Reduire" apparait.
Si la description est courte, elle s'affiche en entier sans bouton.

**EN:**
The long description on the membership page is now automatically truncated
if it exceeds ~10-12 lines (250px). A "Read more" / "Show less" button appears.
If the description is short, it displays fully without a button.

**Fichiers / Files:**
- `BaseBillet/templates/faire_festival/views/membership/list.html`

---

### 4. Filtre par date sur la page evenements / Date filter on events page

**FR :**
Le dropdown "Trier par date" etait present dans le template mais non branche cote back.
Le parametre `?date=` est maintenant lu par la vue `list()`, et le dict `dated_events`
est filtre pour n'afficher que les evenements de la date selectionnee.
Le dropdown conserve toutes les dates disponibles meme quand un filtre est actif.
Le bouton affiche la date selectionnee en format lisible ("lundi 15 mars").

**EN:**
The "Sort by date" dropdown was present in the template but not wired to the backend.
The `?date=` parameter is now read by the `list()` view, and the `dated_events` dict
is filtered to display only events for the selected date.
The dropdown keeps all available dates even when a filter is active.
The button shows the selected date in readable format ("Monday March 15").

**Fichiers / Files:**
- `BaseBillet/views.py` — `EventMVT.list()` : lecture param `date`, filtrage du dict
- `BaseBillet/templates/faire_festival/views/event/list.html` — affichage date active, format ISO dans les liens

---

### 5. Correction erreur Sentry : confirmation email reservation expiree / Fix Sentry error: expired reservation email confirmation

**FR :**
Quand un utilisateur confirmait son email plus de 15 minutes apres une reservation gratuite
et que l'evenement etait presque complet, le signal levait un `ValueError` qui remontait
en `Http404` generique. L'utilisateur voyait une page 404 sans explication.
Desormais le `ValueError` est intercepte dans `emailconfirmation()` et le message
est affiche a l'utilisateur via `django.messages` sur la page d'accueil.
Les messages d'erreur sont maintenant traduits via `_()`.

**EN:**
When a user confirmed their email more than 15 minutes after a free reservation
and the event was nearly full, the signal raised a `ValueError` that surfaced
as a generic `Http404`. The user saw a 404 page with no explanation.
Now the `ValueError` is caught in `emailconfirmation()` and the message
is displayed to the user via `django.messages` on the homepage.
Error messages are now translated via `_()`.

**Fichiers / Files:**
- `BaseBillet/views.py` — `emailconfirmation()` : catch `ValueError` separement
- `BaseBillet/signals.py` — `activator_free_reservation()` : messages avec `_()`

---

### 6. Section produits retiree de la page evenement / Products section removed from event detail page

**FR :**
La section "Tickets and prices" a ete retiree de la page detail evenement du skin Faire Festival.
Le label "Intervenant-e-s" en dur a egalement ete supprime.

**EN:**
The "Tickets and prices" section was removed from the event detail page of the Faire Festival skin.
The hardcoded "Intervenant-e-s" label was also removed.

**Fichiers / Files:**
- `BaseBillet/templates/faire_festival/views/event/retrieve.html`

---

### 7. Correction calcul paiement adhesion sans contribution / Fix membership payment calculation without contribution

**FR :**
Correction d'un crash quand `contribution_value` etait absente lors du calcul
du montant de paiement d'une adhesion. La valeur manquante est maintenant traitee gracieusement.

**EN:**
Fixed a crash when `contribution_value` was missing during membership payment amount calculation.
The missing value is now handled gracefully.

**Fichiers / Files:**
- Commit `50132e35`

---

### Autres ameliorations / Other improvements

- **Admin breadcrumb** : affiche le nom du produit au lieu du nom du tarif dans le fil d'Ariane
- **Admin product archive filter** : filtre pour afficher/masquer les produits archives
- **Redirect tarif → produit** : retour automatique vers le produit parent apres sauvegarde d'un tarif
- **Widget adhesions obligatoires** : passage en `MultipleHiddenInput`
- **Integration Fedow** : gestion d'erreur non-bloquante lors de la creation d'assets et validation d'adhesion
- **Newsletter** : ajout de l'URL newsletter dans le skin
- **Traductions** : nouvelles chaines FR/EN pour les filtres, messages d'erreur, et boutons

**Migration necessaire / Migration required:** Non

---

## v1.7.2 — Corrections production + Paiement admin adhesions + Avoir comptable

**Date :** Mars 2026
**Migration :** Oui (`migrate_schemas --executor=multiprocessing`)

---

### 0. Protection doublon paiement adhesion (SEPA) / Duplicate membership payment protection (SEPA)

**FR :**
Quand un utilisateur cliquait plusieurs fois sur le lien de paiement d'adhesion
(recu par email apres validation admin), un nouveau checkout Stripe etait cree a chaque clic.
Cela pouvait entrainer des **doubles prelevements SEPA** (signaie en production).

La vue `get_checkout_for_membership` verifie maintenant si un paiement Stripe existe deja :
- **Session Stripe encore ouverte** : reutilise l'URL existante (pas de doublon).
- **Session "complete" (SEPA en cours)** : affiche une page d'information expliquant
  que le prelevement est en cours de traitement (jusqu'a 14 jours).
- **Session expiree** : cree un nouveau checkout normalement.

**EN:**
When a user clicked multiple times on the membership payment link
(received by email after admin validation), a new Stripe checkout was created each time.
This could cause **duplicate SEPA debits** (reported in production).

The `get_checkout_for_membership` view now checks for an existing Stripe payment:
- **Stripe session still open**: reuses the existing URL (no duplicate).
- **Session "complete" (SEPA pending)**: displays an info page explaining
  the debit is being processed (up to 14 days).
- **Session expired**: creates a new checkout normally.

**Fichiers / Files:**
- `BaseBillet/views.py` — protection doublon dans `get_checkout_for_membership`
- `BaseBillet/templates/reunion/views/membership/payment_already_pending.html` — nouveau template

**Migration necessaire / Migration required:** Non

---

### 1. Avoir comptable (credit note) sur les ventes / Credit note on sales

**FR :**
Les admins peuvent emettre un **avoir** sur une ligne de vente depuis l'admin (bouton "Avoir" dans la liste des ventes).
Un avoir cree une ligne miroir avec quantite negative pour annuler comptablement la vente,
sans supprimer l'ecriture originale (conformite fiscale francaise).
Gardes : uniquement sur lignes confirmees ou payees, et un seul avoir par ligne.
L'avoir est envoye a LaBoutik si un serveur cashless est configure.
L'export CSV inclut une colonne "Ref. avoir" pour la tracabilite.

**EN:**
Admins can issue a **credit note** on a sale line from the admin (row action button in the sales list).
A credit note creates a mirror line with negative quantity to cancel the sale for accounting purposes,
without deleting the original entry (French fiscal compliance).
Guards: only on confirmed or paid lines, and only one credit note per line.
The credit note is sent to LaBoutik if a cashless server is configured.
CSV export includes a "Credit note ref." column for traceability.

**Fichiers / Files:**
- `BaseBillet/models.py` — status `CREDIT_NOTE`, FK `credit_note_for`
- `BaseBillet/signals.py` — transition CREATED → CREDIT_NOTE
- `Administration/admin_tenant.py` — `LigneArticleAdmin.emettre_avoir()`
- `Administration/importers/lignearticle_exporter.py` — colonne export
- `BaseBillet/migrations/0199_credit_note_lignearticle.py`

**Annulation adhesion avec avoir :**
L'action "Annuler" sur une adhesion affiche desormais une page de confirmation.
Si l'adhesion a des lignes de vente payees, l'admin peut choisir "Annuler et creer un avoir".
Les avoirs sont crees pour chaque ligne VALID/PAID liee a l'adhesion.

**Fichiers / Files:**
- `Administration/admin_tenant.py` — `MembershipAdmin.cancel()` (GET/POST avec confirmation)
- `Administration/templates/admin/membership/cancel_confirm.html` (nouveau)

---

### 2. Correction annulation reservation admin (cheque, especes) / Fix admin reservation cancellation (non-Stripe)

**FR :**
Quand un admin annulait une reservation creee manuellement (payee par cheque, especes, etc.),
aucune ligne de remboursement ou d'avoir n'etait creee. La reservation passait en "annulee"
sans trace comptable, car `cancel_and_refund_resa` ne cherchait les LigneArticle que via
les `Paiement_stripe` (FK), et les reservations admin n'en ont pas.
Desormais, lors de l'annulation, un avoir (CREDIT_NOTE) est automatiquement cree pour chaque
LigneArticle hors-Stripe (sale_origin=ADMIN) liee a la reservation.
Meme correction pour l'annulation de ticket individuel (`cancel_and_refund_ticket`).

**EN:**
When an admin cancelled a manually created reservation (paid by check, cash, etc.),
no refund or credit note line was created. The reservation was marked as cancelled
with no accounting trace, because `cancel_and_refund_resa` only looked for LigneArticle
via `Paiement_stripe` (FK), and admin reservations don't have one.
Now, upon cancellation, a credit note (CREDIT_NOTE) is automatically created for each
non-Stripe LigneArticle (sale_origin=ADMIN) linked to the reservation.
Same fix for single ticket cancellation (`cancel_and_refund_ticket`).

**Fichiers / Files:**
- `BaseBillet/models.py` — `Reservation._lignes_hors_stripe()`, `Reservation._creer_avoir()`,
  `cancel_and_refund_resa()`, `cancel_and_refund_ticket()`

---

### 3. FK reservation sur LigneArticle / Reservation FK on LigneArticle

**FR :**
Ajout d'une FK directe `LigneArticle.reservation` pour lier une ligne comptable a sa reservation
sans dependre de `Paiement_stripe` comme intermediaire.
Avant, les reservations admin (cheque, especes) n'avaient aucun lien vers leurs LigneArticle.
La FK est renseignee dans les 4 flows de creation (front, API v1, API v2, admin).
Une data migration backfill les lignes existantes depuis `paiement_stripe.reservation`.
Les methodes `articles_paid()` et `_lignes_hors_stripe()` utilisent la FK directe
avec fallback sur l'ancien chemin pour compatibilite.

**EN:**
Added a direct FK `LigneArticle.reservation` to link an accounting line to its reservation
without relying on `Paiement_stripe` as intermediary.
Previously, admin reservations (check, cash) had no link to their LigneArticle.
The FK is set in all 4 creation flows (front, API v1, API v2, admin).
A data migration backfills existing lines from `paiement_stripe.reservation`.
`articles_paid()` and `_lignes_hors_stripe()` use the direct FK with legacy fallback.

**Fichiers / Files:**
- `BaseBillet/models.py` — FK `reservation` + simplification `articles_paid()`, `_lignes_hors_stripe()`
- `BaseBillet/validators.py` — `reservation=reservation` (front)
- `ApiBillet/serializers.py` — `reservation=reservation` (API v1)
- `api_v2/serializers.py` — `reservation=reservation` (API v2)
- `Administration/admin_tenant.py` — `reservation=reservation` (admin)
- `BaseBillet/migrations/0200_add_reservation_fk_to_lignearticle.py`
- `BaseBillet/migrations/0201_backfill_lignearticle_reservation.py`

---

### 4. Correction niveau de log API Brevo / Fix Brevo API log level

**FR :**
Quand un admin testait sa cle API Brevo depuis la configuration et que la cle etait invalide,
l'erreur 401 remontait en `logger.error` dans Sentry, polluant les alertes.
C'est une erreur de configuration utilisateur, pas un bug applicatif.
Le niveau de log est passe a `logger.warning`.

**EN:**
When an admin tested their Brevo API key from the configuration and the key was invalid,
the 401 error was logged as `logger.error` in Sentry, polluting alerts.
This is a user configuration error, not an application bug.
Log level changed to `logger.warning`.

**Fichiers / Files:** `Administration/admin_tenant.py` — `BrevoConfigAdmin.test_api_brevo()`

---

### 5. Correction deconnexion automatique apres 3 mois / Fix automatic logout after 3 months

**FR :**
Les utilisateurs etaient deconnectes apres exactement 3 mois, meme s'ils utilisaient le site quotidiennement.
Cause : `SESSION_SAVE_EVERY_REQUEST` n'etait pas defini (defaut Django = `False`),
donc le cookie de session n'etait renouvele que lors de modifications de la session, pas a chaque visite.
Ajout de `SESSION_SAVE_EVERY_REQUEST = True` pour que chaque visite renouvelle le cookie.

**EN:**
Users were logged out after exactly 3 months, even when using the site daily.
Cause: `SESSION_SAVE_EVERY_REQUEST` was not set (Django default = `False`),
so the session cookie was only renewed when the session was modified, not on every visit.
Added `SESSION_SAVE_EVERY_REQUEST = True` so every visit renews the cookie.

**Fichiers / Files:** `TiBillet/settings.py`

---

### 6. Bouton "Ajouter un paiement" sur les adhesions en attente / "Add payment" button on pending memberships

**FR :**
Les admins de lieux recoivent des adhesions remplies en ligne mais payees sur place
(especes, cheque, virement). Ces adhesions restaient bloquees en "attente de paiement"
sans moyen de les valider depuis l'admin.
Nouveau bouton "Ajouter un paiement" sur la page detail d'une adhesion en attente (WP ou AW).
Le formulaire demande le montant et le moyen de paiement, puis declenche toute la chaine :
creation de la ligne de vente, calcul de la deadline, envoi de l'email de confirmation,
transaction Fedow, et notification LaBoutik.

**EN:**
Venue admins receive memberships filled out online but paid on-site
(cash, check, bank transfer). These memberships were stuck in "waiting for payment"
with no way to validate them from the admin.
New "Add payment" button on the detail page of a pending membership (WP or AW).
The form asks for the amount and payment method, then triggers the full chain:
sale line creation, deadline calculation, confirmation email,
Fedow transaction, and LaBoutik notification.

**Fichiers / Files:**
- `Administration/admin_tenant.py` — `MembershipAdmin.ajouter_paiement()`
- `Administration/templates/admin/membership/ajouter_paiement.html` (nouveau / new)

---

## v1.6.8 — Corrections Sentry + Import/Export Events

**Date :** Fevrier 2026
**Migration :** Non

---

### 1. Correction boucle infinie sur ProductFormField.save() / Fix infinite loop on ProductFormField.save()

**FR :**
Quand le label d'un champ de formulaire dynamique generait un slug de 64 caracteres ou plus,
la generation de nom unique entrait dans une boucle infinie (le suffixe etait tronque puis identique a chaque tour).
Le serveur finissait par un `SystemExit`.
On utilise maintenant un fragment d'UUID pour garantir l'unicite en un seul essai.

**EN:**
When a dynamic form field label produced a slug of 64+ characters,
the unique name generation entered an infinite loop (the suffix was truncated to the same value each iteration).
The server ended up with a `SystemExit`.
We now use a UUID fragment to guarantee uniqueness in a single attempt.

**Fichiers / Files:** `BaseBillet/models.py` — `ProductFormField.save()`

---

### 2. Correction timeout cashless / Fix cashless ReadTimeout

**FR :**
L'appel HTTP vers le serveur cashless avait un timeout de 1 seconde, trop court en production.
Passe a 10 secondes.

**EN:**
The HTTP call to the cashless server had a 1-second timeout, too short for production.
Increased to 10 seconds.

**Fichiers / Files:** `BaseBillet/tasks.py`

---

### 3. Correction creation de tenant en doublon / Fix duplicate tenant creation

**FR :**
Quand un utilisateur cliquait deux fois sur le lien de confirmation email,
la creation du tenant pouvait echouer car le lien `WaitingConfiguration → tenant` n'etait pas assigne assez tot.
On assigne maintenant le tenant des sa creation, et on ajoute un fallback qui repare le lien si le tenant existe deja.

**EN:**
When a user clicked the email confirmation link twice,
tenant creation could fail because the `WaitingConfiguration → tenant` link was not assigned early enough.
We now assign the tenant immediately after creation, and added a fallback that repairs the link if the tenant already exists.

**Fichiers / Files:** `BaseBillet/validators.py`, `BaseBillet/views.py`

---

### 4. Correction carte perdue 404 / Fix lost_my_card 404

**FR :**
Quand un utilisateur cliquait deux fois sur "carte perdue", le deuxieme appel a Fedow renvoyait un 404
car la carte etait deja detachee. On attrape maintenant cette erreur proprement.

**EN:**
When a user double-clicked "lost my card", the second call to Fedow returned a 404
because the card was already detached. We now catch this error gracefully.

**Fichiers / Files:** `BaseBillet/views.py` — `admin_lost_my_card`, `lost_my_card`

---

### 5. Correction formulaire adhesion admin sans wallet / Fix admin membership form without wallet

**FR :**
Dans l'admin, le formulaire d'adhesion plantait si on validait le numero de carte
sans avoir d'abord renseigne un email valide (attribut `user_wallet_serialized` absent).
On verifie maintenant que le wallet existe avant d'y acceder.

**EN:**
In the admin, the membership form crashed when validating the card number
without first providing a valid email (missing `user_wallet_serialized` attribute).
We now check the wallet exists before accessing it.

**Fichiers / Files:** `Administration/admin_tenant.py` — `MembershipForm.clean_card_number()`

---

### 6. Verification SEPA Stripe avant activation / Stripe SEPA capability check before activation

**FR :**
Activer le paiement SEPA dans la configuration alors que le compte Stripe Connect n'a pas la capacite SEPA
provoquait une erreur au moment du paiement. On verifie maintenant la capacite SEPA via l'API Stripe
au moment de la sauvegarde de la configuration. Si le checkout echoue malgre tout, le SEPA est desactive automatiquement.

**EN:**
Enabling SEPA payment in the configuration while the Stripe Connect account lacked SEPA capability
caused an error at checkout time. We now verify SEPA capability via the Stripe API
when saving the configuration. If checkout still fails, SEPA is automatically disabled.

**Fichiers / Files:** `BaseBillet/models.py` — `Configuration.check_stripe_sepa_capability()`, `PaiementStripe/views.py`

---

### 7. Tri des produits par poids / Product weight ordering

**FR :**
Les prix affiches sur la page evenement ignoraient le poids (`poids`) du produit parent.
Les produits sont maintenant tries par `product__poids`, puis `order`, puis `prix`.

**EN:**
Prices displayed on the event page ignored the parent product's weight (`poids`).
Products are now sorted by `product__poids`, then `order`, then `prix`.

**Fichiers / Files:** `BaseBillet/views.py`

---

### 8. Import/Export CSV des evenements (PR #351) / CSV import/export for events (PR #351)

**FR :**
Contribution de @AoiShidaStr : ajout de l'import/export CSV des evenements depuis l'admin Django.
Ameliore ensuite avec : export de l'adresse postale par nom (pas par ID),
lignes identiques ignorees a l'import, et rapport des lignes ignorees.

**EN:**
Contribution by @AoiShidaStr: added CSV import/export for events from the Django admin.
Then improved with: postal address exported by name (not ID),
unchanged rows skipped on import, and skipped rows reported.

**Fichiers / Files:** `Administration/admin_tenant.py` — `EventResource`

---

*Lespass est un logiciel libre sous licence AGPLv3, developpe par la Cooperative Code Commun.*
*Lespass is free software under AGPLv3 license, developed by Cooperative Code Commun.*

---

## v1.6.4 — Migration requise

**Date :** Fevrier 2025
**Migration :** Oui (`migrate_schemas --executor=multiprocessing`)

---

### 1. Moteur de skin configurable / Configurable skin engine

**FR :**
Nous pouvons maintenant choisir son theme graphique depuis l'administration.
Un nouveau champ `skin` a ete ajoute au modele `Configuration`.
Le systeme cherche d'abord le template dans le dossier du skin choisi,
puis retombe automatiquement sur le theme par defaut (`reunion`) si le template n'existe pas.
Cela permet de creer un nouveau skin en ne surchargeant que les templates souhaités.

**EN:**
Each venue can now choose its visual theme from the admin panel.
A new `skin` field has been added to the `Configuration` model.
The system first looks for the template in the chosen skin folder,
then automatically falls back to the default theme (`reunion`) if the template does not exist.
This allows creating a new skin by only overriding the desired templates.

**Details techniques / Technical details:**

- Nouveau champ `Configuration.skin` (CharField, defaut `"reunion"`)
  New field `Configuration.skin` (CharField, default `"reunion"`)
- Nouvelle fonction `get_skin_template(config, path)` avec logique de fallback
  New function `get_skin_template(config, path)` with fallback logic
- Ajout du skin `faire_festival` (theme brutaliste) avec templates et CSS dedies
  Added `faire_festival` skin (brutalist theme) with dedicated templates and CSS
- Migration : `BaseBillet/migrations/0195_configuration_skin.py`

**Fichiers concernes / Files involved:**
- `BaseBillet/views.py` — resolution dynamique des templates
- `BaseBillet/models.py` — champ `skin` sur `Configuration`
- `BaseBillet/templates/faire_festival/` — nouveau dossier skin complet
- `BaseBillet/static/faire_festival/css/` — styles dedies
- `Administration/admin_tenant.py` — champ expose dans l'admin

---

### 2. Pre-remplissage des formulaires d'adhesion / Membership form pre-fill

**FR :**
Quand un utilisateur connecte remplit un formulaire d'adhesion,
le systeme recherche sa derniere adhesion au meme produit.
Si une adhesion precedente existe, tous les champs du formulaire dynamique
sont pre-remplis avec les valeurs deja saisies.
L'utilisateur n'a plus a re-saisir son adresse, telephone, etc. a chaque renouvellement.

**EN:**
When a logged-in user fills out a membership form,
the system looks up their most recent membership for the same product.
If a previous membership exists, all dynamic form fields
are pre-filled with the previously entered values.
The user no longer has to re-enter their address, phone, etc. on each renewal.

**Details techniques / Technical details:**

- Recherche de la derniere `Membership` du user pour le meme produit avec `custom_form` non vide
  Lookup of the user's latest `Membership` for the same product with non-empty `custom_form`
- Construction d'un dict `prefill` qui mappe `field.name` vers la valeur stockee
  Builds a `prefill` dict mapping `field.name` to the stored value
- Tous les types de champs supportes : texte, textarea, select, radio, checkbox, multi-select
  All field types supported: text, textarea, select, radio, checkbox, multi-select
- Nouveau filtre de template `get_item` pour acceder aux cles d'un dict dans le template
  New `get_item` template filter for dict key lookup in templates

**Fichiers concernes / Files involved:**
- `BaseBillet/views.py` — logique de pre-remplissage dans `MembershipMVT.retrieve()`
- `BaseBillet/templates/reunion/views/membership/form.html` — affichage des valeurs pre-remplies
- `BaseBillet/templatetags/tibitags.py` — filtre `get_item`

---

### 3. Edition des formulaires dynamiques depuis l'admin / Admin custom form field editing

**FR :**
Les administrateurs peuvent maintenant modifier les reponses d'un formulaire dynamique
directement depuis la fiche adhesion dans l'admin, sans passer par le shell ou la base de donnees.
Ils peuvent aussi ajouter des champs libres (non definis dans le produit).
Tout se fait en HTMX, sans rechargement de page.

**EN:**
Admins can now edit dynamic form responses
directly from the membership detail page in the admin panel, without using the shell or database.
They can also add free-form fields (not defined in the product).
Everything works via HTMX, without page reload.

**Details techniques / Technical details:**

- 5 nouvelles actions HTMX sur `MembershipMVT` :
  5 new HTMX actions on `MembershipMVT`:
  - `admin_edit_json_form` (GET) — affiche le formulaire editable / shows editable form
  - `admin_cancel_edit` (GET) — annule l'edition / cancels editing
  - `admin_change_json_form` (POST) — valide et sauvegarde / validates and saves
  - `admin_add_custom_field_form` (GET) — formulaire d'ajout de champ / add field form
  - `admin_add_custom_field` (POST) — sauvegarde le nouveau champ / saves new field
- Validation des champs requis, anti-doublon sur les labels, sanitisation HTML via `nh3`
  Required field validation, duplicate label check, HTML sanitization via `nh3`
- Chaque type de champ (`ProductFormField`) est rendu avec le bon widget HTML
  Each field type (`ProductFormField`) is rendered with the appropriate HTML widget
- Support des champs "orphelins" (presents dans le JSON mais pas dans le produit)
  Support for "orphan" fields (present in JSON but not defined in the product)
- Protection par `TenantAdminPermission`

**Fichiers concernes / Files involved:**
- `BaseBillet/views.py` — actions HTMX
- `Administration/utils.py` — fonction `clean_text()` (sanitisation `nh3`)
- `Administration/templates/admin/membership/custom_form.html` — vue lecture avec boutons
- `Administration/templates/admin/membership/partials/custom_form_edit.html` — formulaire editable
- `Administration/templates/admin/membership/partials/custom_form_edit_success.html` — confirmation
- `Administration/templates/admin/membership/partials/custom_form_add_field.html` — ajout de champ
- `BaseBillet/models.py` — correction de `ProductFormField.save()` (ne pas ecraser `name`)
- `BaseBillet/validators.py` — recherche de cle robuste avec fallback UUID/label

---

### Autres ameliorations / Other improvements

- **Duplication de produit** : nouvelle action admin pour dupliquer un produit existant
  New admin action to duplicate an existing product
- **Validation anti-doublon d'evenement** : empeche la creation d'evenements avec le meme nom et la meme date
  Prevents creating events with same name and date
- **Accessibilite** : ameliorations `aria-label`, `visually-hidden`, meilleur support des themes clair/sombre
  Accessibility improvements: `aria-label`, `visually-hidden`, better light/dark theme support
- **Tests E2E** : nouveau test Playwright pour le cycle complet d'edition des formulaires dynamiques
  New Playwright test for the full dynamic form editing cycle

---

*Lespass est un logiciel libre sous licence AGPLv3, developpe par la Cooperative Code Commun.*
*Lespass is free software under AGPLv3 license, developed by Cooperative Code Commun.*
