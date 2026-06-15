# HANDOFF — Reprendre le chantier S6 dans une session propre

Date : 2026-06-11. Rédigé en clôture de la session de recherche + baseline.

## Prompt de démarrage suggéré pour la nouvelle session

> On reprend le chantier FEDOW_IMPORT (scénario S6 acté). Lis dans l'ordre :
> `TECH_DOC/SESSIONS/FEDOW_IMPORT/HANDOFF.md` (ce fichier),
> `ROADMAP.md` (les lots C-A → C-D), `TESTS-STRATEGIE.md`, puis la SPEC
> révisée. Puis tout les fichier.md dans le dossier FEDOW_IMPORT pour le contexte large du chantier. 
> Invoque les skills /djc et /unfold. On attaque le lot C-A
> (copier-coller du socle depuis ../lespass-main branche new_pairing_and_nfc).

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
