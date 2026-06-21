# HANDOFF — Reprendre le chantier S6 dans une session propre

Date : 2026-06-11. Rédigé en clôture de la session de recherche + baseline.

## Prompt de démarrage suggéré pour la nouvelle session

> On reprend le chantier FEDOW_IMPORT (scénario S6 acté). Lis dans l'ordre :
> `TECH_DOC/SESSIONS/FEDOW_IMPORT/HANDOFF.md` (ce fichier),
> `ROADMAP.md` (les lots C-A → C-D), `TESTS-STRATEGIE.md`, puis la SPEC
> révisée. Puis tout les fichier.md dans le dossier FEDOW_IMPORT pour le contexte large du chantier. 
> Invoque les skills /djc et /unfold. On attaque le lot C-A
> (copier-coller du socle depuis ../lespass-main branche new_pairing_and_nfc).

---

## ⏩ MISE À JOUR 2026-06-20 — C-A réalisé (portage + admin) ⚠️ working tree, non committé sauf le transport initial

**C-A à ~90 %.** Le socle est porté, migré, les paiements espèces/CB passent, l'admin laboutik/inventaire fonctionne sur Chrome. Restent les checkpoints de validation (tests, doc, cashless local).

### Réalisé cette session
- **Portage** : AuthBillet (Wallet `public_pem`/`name`, `terminal_role`), QrcodeCashless (`wallet_ephemere`), `fedow_core`, `laboutik`, `inventaire` (copies conformes), BaseBillet (`CategorieProduct` + champs POS Product/Price + **6 champs LigneArticle** : point_de_vente, uuid_transaction, hmac_hash, previous_hmac, total_ht, weight_quantity), `services_refund.py`, **`wsocket/broadcast.py`** (dépendance transverse).
- **Settings/urls/perms** : SHARED += `fedow_core`, `django_cotton` ; TENANT += `laboutik`, `inventaire` ; loaders cotton ; `DEMO_TAGID_*` ; `urls_tenants` += laboutik/inventaire ; `BaseBillet/permissions.py` += `HasLaBoutikAccess`/`HasLaBoutikTerminalAccess` (+ imports `connection`).
- **Migrations** : BaseBillet **0220/0221/0222** + laboutik 0001 + inventaire 0001/0002, **appliquées** (--shared + --schema=lespass). `discovery` **NON porté** (reste version V1 antérieure, sans `terminal_role` — `check` OK).
- **Réconciliations S6** : comptabilité↔laboutik (`related_name='clotures_caisse_lb'` côté laboutik, car les 2 ont `ClotureCaisse`/`CompteComptable`/`MappingMoyenDePaiement` mais **modèles différents** — fusion = chantier futur dédié) ; `create_test_pos_data` sans `bootstrap_fed_asset` (pas de FED local).
- **Checkpoints C-A** : check 0 ✅ · migrate ✅ · makemigrations --check ✅ · **paiement espèce (CA) + CB (CC) testés sur Chrome**, LigneArticle statut `V` en base ✅.
- **Admin (demande mainteneur 2026-06-20)** : laboutik + inventaire **fonctionnels** sur Chrome (dashboard cartes POS/Inventory/monnaie, menu Inventaire, **58/59 changelists + change views OK**). Correctifs : POSProduct/Fut/Categorie activés (`products.py` réaligné sur la source), modules `laboutik.py`/`inventaire.py` branchés dans `admin_tenant.py`, `TermUser` minimal ajouté au monolithe, **dashboard rendu tolérant aux liens absents** (`_safe_rev`), templates copiés (`widgets/` palette+icon picker, `inventaire/`, `cloture/`, `comptable/`), `module_inventaire` activé + cartes dashboard décommentées, fix `__str__` de `comptabilite.MappingMoyenDePaiement` (bug pré-existant V1 : `get_payment_method_display()` sur champ sans `choices`).
- ⚠️ **Serveur** : un état de reload Daphne corrompu a nécessité un restart (`rsp`) ; les modifs de `admin_tenant.py`/`dashboard.py` reloadent proprement depuis.

### Reste pour CLÔTURER C-A (checkpoints 3, 5, 6 — à faire avant C-B)
- [ ] **Suite pytest + Playwright** portée verte — NON relancée. Risque réel : j'ai touché `BaseBillet/models.py`, `settings.py`, `urls_tenants.py`, `permissions.py`, et tout l'admin.
- [ ] **Cashless LOCAL** au POS (testé : espèces/CB seulement).
- [ ] **Non-régression V1** : un tenant `server_cashless` renseigné n'exécute aucun `fedow_core`.
- [ ] **Doc `A TESTER et DOCUMENTER/` + CHANGELOG**.

### Dette « chantier admin modulaire » (NOUVEAU lot à planifier)
- `admin_tenant.py` (**180 Ko monolithique**) à éclater vers `Administration/admin/*.py` comme lespass-main (12 modules manquants : cards, events, fedow, sales, users, membership, reservations, tags, settings_apps, crowds, configuration…).
- Apps **référencées par le dashboard mais absentes/incomplètes en V1** : `booking`, `controlvanne` (pas de `models.py`), `cards`/`QrcodeCashless` admin + `views_cards.py` — liens rendus `#` par la **tolérance temporaire** `_safe_rev`. À porter proprement OU retirer du `dashboard.py` V1.
- `TermUser` : alignement via `users.py` (gérer le doublon `HumanUser` déjà dans le monolithe).
- `fedow.py` (admin AssetFedowPublic) NON branché : doublon avec le monolithe `admin_tenant.py:3920` — à résoudre quand le monolithe sera vidé.

### Scope C-B précisé (diagnostic 2026-06-20)
- **C-A validé** : pytest **263 passed** (non-régression OK après tout le portage + admin).
- Les corrections **génériques B1/B2** de l'audit (verrous `select_for_update`, atomicité, `SoldeInsuffisant`, `tenant_origin`, UniqueConstraint FED) sont **déjà dans le code porté** (lespass-main durci) — validées par les 263 tests. **Ne PAS les refaire.**
- **P4 caduc** : garde anti-FED-local = absence de `Client.FED` (déjà le cas, `bootstrap_fed_asset` désactivé).
- ⚠️ **RÉVISION 2026-06-20 (décision mainteneur) : G1/G8 CADUQUES — NE PAS les implémenter.**
  La conception S6 est précisée : **chaque nouveau tenant (V1 ET V2) est connecté au Fedow**
  (`create_place` AUTOMATIQUE à la création, **pas d'opt-in / pas d'activation consciente**),
  car le tenant V2 a besoin d'un **place Fedow** pour accepter l'**asset fédéré (FED)** du réseau.
  La distinction V1/V2 n'est donc **PAS** « Fedow ou pas » (les deux y sont) mais **où vit la
  monnaie locale cashless** : `fedow_core` **LOCAL** (V2) vs Fedow distant (V1). Les gardes G1/G8
  (« couper Fedow si V2 ») étaient à l'envers → **retirées** : `create_tenant`, `install.py`,
  `signals.py` (send_membership + trigger_product_update) restaurés à l'original.
- **Conséquence : C-B = corrections GÉNÉRIQUES de l'audit** (verrous `select_for_update`,
  atomicité, `SoldeInsuffisant`, `tenant_origin`, UniqueConstraint FED), **déjà dans le code
  porté** (lespass-main durci) et **validées par pytest (262 passed, 1 skip)**. C-B est couvert
  par le portage — rien à « durcir » en plus côté dispatch.
- **Vérifié env V2** : `lespass` a `server_cashless=None`, `can_fedow()=True`, place Fedow créé
  (`96e9d347-…`), Fedow distant up (`fedow_django`/`nginx`/`memcached`). Le `create_place` auto
  fonctionne pour V2.
- **G10** (seul reste, doc only) : documenter les flux « V1-only par design S6 ».
- ⚠️ **Smoke Chrome post-reset** : Traefik a régénéré son certificat auto-signé → Chrome affiche
  « Erreur de confidentialité ». Accepter le cert manuellement (Avancé → Continuer) avant de
  re-tester l'admin/POS. Avant le reset, admin laboutik/inventaire + paiements espèce/CB étaient
  ✅ sur Chrome.
- ✅ **Smoke V2 post-reset (cert accepté)** : admin dashboard/laboutik/inventaire/POS products +
  POS caisse = **tous 200** (test client) ; admin V2 visuellement OK sur Chrome (« POS & restaurant »
  ON car V2). Recharge locale : modal tarif + ajout panier OK.
- ⚠️ **WS laboutik PORTÉ le 2026-06-20** (manque découvert via `No route found for ws/laboutik/<pv>/`
  en boucle dans byobu) : `wsocket/consumers.py` (LaboutikConsumer + PrinterConsumer, **+ ChatConsumer
  V1 conservé**) + `wsocket/routing.py` (routes `ws/chat/` + `ws/laboutik/` + `ws/printer/`).
  Sans ça, le POS n'a **aucun temps réel** (scan carte impossible). Après portage : `WebSocket CONNECT`
  OK. **Note** : `controlvanne.routing` (présent dans l'asgi de lespass-main) NON porté (app absente V1).
- ⚠️ **Scan carte en DEV** : pas un keyboard-wedge global — le POS utilise l'input
  **`#nfc-simu-manual-input`** (`laboutik/static/js/nfc.js`) / composant cotton `c-read-nfc`
  (`input-selector="#nfc-tag-id"`). Pour simuler un scan en dev : remplir cet input + submit
  (via `javascript_tool` ou cibler l'input précis), PAS taper sur la page.
- **ENV RESET 2026-06-20** : `docker down -v` (compose+laboutik séparé) → `up` sur `docker-compose.yml` (**laboutik intégré au code**, plus de service séparé) → `flush.sh`. **lespass renaît en V2** (`server_cashless` vide) = tenant V2 propre pour tester G1/G8.
- ⚠️ **Après le reset, refaire** : `migrate_schemas` (les migrations 0220-0222/laboutik/inventaire sont dans le working tree) → `create_test_pos_data --schema=lespass` → relancer le serveur (byobu) → re-smoke Chrome (admin + POS espèce/CB).

### Ensuite : C-B (ROADMAP §3) une fois l'env V2 prêt — implémenter G1/G8/G10 puis re-valider pytest + Chrome.

---

## État au moment du handoff

### Décision (ne pas re-débattre)
**Scénario S6 « hybride additif »** : aucune fusion, aucune migration de
données. Fedow standalone reste en prod (500 lieux + FED). On copie-colle
`fedow_core` + `laboutik` + `discovery` + `inventaire` depuis
`../lespass-main` (branche `new_pairing_and_nfc`) ; monnaies locales des
nouveaux tenants en DB locale ; tokens legacy acceptés au POS via
`FedowAPI.transaction.to_place_from_qrcode` (signature user, AUCUN handshake
cashless), cartes liées à un user seulement en phase 1. JAMAIS de FED local.
Genèse complète : docs 01→09 du hub (lire seulement si besoin d'arguments).

### Baseline tests : TOUT VERT (filet de non-régression posé)
- pytest : **229 passed** (226 + 3 nouveaux tests de garde)
- E2E Playwright TS (`tests/playwright/`, hôte, `yarn test:chromium:console
  --workers=1`) : **67-68 passed, 0 failed** (1 skip préexistant)
- E2E Playwright Python (`tests/e2e/`) : **8 passed**
- Commandes et pièges : `tests/PIEGES.md` (section session 2026-06-11) +
  `A TESTER et DOCUMENTER/baseline-tests-verts-fedow-import.md`

### Corrections livrées cette session (committées par le mainteneur au fil de l'eau)
1. ~30 tests réparés (refonte admin proxys non répercutée, hermétisme,
   outillage) — détail : CHANGELOG entrée 2026-06-11.
2. Bug wizard doublon → 500 : corrigé (atomic + message + images temp
   différées post-commit). Spec 21 réactivé.
3. Bug signaux muets sur proxys : corrigé (`PROXYS_PRODUCT` + test de garde
   `test_signaux_proxys_product.py`). Spec 37 sans contournement.
4. Review externe passée : verdict « ready with fixes », fixes appliqués.

### Prérequis vérifiés / à vérifier
- [x] drift Fedow : `reconcile_tokens` passé en prod (nuit 10-11/06) — le
  mainteneur a confirmé le passage ; si doute, requête §10.1 de
  `../Fedow/TECH_DEV/DRIFT/README.md`.
- [x] Fedow docker de dev : conteneur `fedow_django` tourne.
- [ ] Décision mainteneur : où vivent les dossiers clients
  (`laboutik_client_*`) — sans impact code.

## Le prochain travail : lot C-A (ROADMAP §2)

Copier-coller du socle, 1 grosse session, règle des 3 fichiers relâchée :
1. `pyproject.toml` : + `django-cotton` (seule dep manquante — installation
   poetry par le mainteneur). Settings : SHARED_APPS += `fedow_core` ;
   TENANT_APPS += `laboutik`, `inventaire`, `discovery`.
2. Copier tels quels : `fedow_core/`, `laboutik/`, `inventaire/`,
   `discovery/`, `BaseBillet/services_refund.py` + migrations copiables
   (AuthBillet 0024/0025, QrcodeCashless, fedow_core, inventaire, discovery).
3. ⚠️ **JAMAIS copier les migrations BaseBillet** (collision 0204-0217) :
   porter les champs (Product POS, Price.asset/non_fiduciaire/contenance/
   poids_mesure, CategorieProduct, LigneArticle POS, LaBoutikAPIKey) puis
   `makemigrations` frais 0219+.
4. Pas de bootstrap FED local (ni `Client.FED`, ni tenant `federation_fed`).
5. Checkpoints de sortie : `manage.py check` → `migrate_schemas` →
   `makemigrations --check` → suite pytest V2 portée verte → smoke Chrome
   caisse espèces/CB (`create_test_pos_data --schema=lespass`) →
   non-régression V1 → doc A TESTER + CHANGELOG.

## Environnement (rappels mainteneur)

- Serveur tenu par le mainteneur dans byobu (fenêtre 2 : pane 0 = claude,
  pane 1 = serveur, pane 2 = celery). Tests lançables dans la fenêtre 1.
  NE PAS lancer runserver (port occupé).
- Jamais d'opération git (le mainteneur committe au fil de l'eau).
- Tests : ne PAS lancer pytest et la suite Playwright en parallèle
  (courses pymemcache, cf. PIEGES).
- Playwright Python est installé dans le conteneur HORS pyproject
  (pip + install-deps chromium) — re-décision si conteneur reconstruit.
- Admin test : admin@admin.com. Check visuel :
  `https://lespass.tibillet.localhost/`.

## Pointeurs

| Quoi | Où |
|---|---|
| Feuille de route opérationnelle | `TECH_DOC/SESSIONS/FEDOW_IMPORT/ROADMAP.md` |
| Stratégie de tests + fixture « pont » | `TESTS-STRATEGIE.md` |
| Risques/garde-fous S6 (4 parades C-B) | `08-s6-creusage-profond.md` §2 |
| Audit fedow_core V2 (bugs B1/M1-M4 à corriger en C-B) | `02-audit-profond.md` + `02b` |
| Inventaire call sites laboutik→fedow_core | `06-revue-laboutik-new-pairing-estimation.md` §3 |
| Source à copier | `/home/jonas/TiBillet/dev/lespass-main` (branche `new_pairing_and_nfc`) |
| Fedow standalone (NE PAS TOUCHER) | `/home/jonas/TiBillet/dev/Fedow` |
