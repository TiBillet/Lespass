# Synthèse merge controlvanne — état actuel vs chantiers dev_vps

**Date** : 2026-05-19
**Branche** : `controlvanne-merge` (sur base `origin/V2`)
**Source review** : `TECH DOC/SESSIONS/CONTROLVANNE/merge_dev_vps/` sur `dev_vps`

Ce document fait le lien entre les **6 chantiers de la review** (côté dev_vps) et les **11 étapes du merge** (côté `controlvanne-merge`). Il signale ce qui diverge et ce qui mérite attention avant la PR.

**Ordre de lecture** : les étapes sont présentées dans l'ordre chronologique du merge (0, 1, 2, … 10), pas par numéro de chantier review. Chaque étape concernée par un chantier est intitulée `Étape X / Chantier Y` pour faciliter le va-et-vient avec les `CHANTIER_*.md`.

---

## Mapping global

| Étape merge | Chantier review | Statut | Divergence |
|---|---|---|---|
| 0 — Créer branche | — | ✅ | — |
| 1 — Import controlvanne/ | — | ✅ | — |
| 2 — Fix asgi.py | — | ✅ | — |
| 3 — URLs discovery | — | ✅ | — |
| 4 — Fix DEBUG IP locale | — | ⏸️ Différée (PR 3) | Non bloquant prod |
| **5** | **Chantier 1 — LEGACY_FEDOW_V1** | ✅ | — |
| **6** | **Chantier 6 — CALIBRATION** | ⚠️ Partiel | Suppression OK, simplification non touchée |
| **7** | **Chantier 4 — BALANCE_ESTIMEE** | ⏸️ Différée (PR 2) | Suppression cassait l'UX kiosk |
| **8** | **Chantier 5 — PUSH_WS_REFUS** | ✅ | Option B + option i appliquées |
| **9** | **Chantier 2 — BILLING_REDONDANCE** | ✅ Option 3 | Scope élargi vs option 1 initiale |
| **10** | **Chantier 3 — AUTH_KIOSK** | ✅ Option minimale | 2/5 manques sécu reportés PR 4 |

---

## Étapes 0-4 — Préparation merge (hors chantiers review)

Ces étapes ne sont pas dans les chantiers de la review : elles concernent la préparation de la branche et 3 fixes infrastructure prérequis. Aucune ne modifie le comportement métier de Lespass en prod.

### Étape 0 — Créer branche `controlvanne-merge` depuis `origin/V2` ✅

`git checkout -b controlvanne-merge origin/V2`. Base partir de V2 propre, pas de dev_vps.

### Étape 1 — Importer `controlvanne/` depuis dev_vps ✅

`git checkout dev_vps -- controlvanne/`. Récupère le dossier entier en un commit, sans rien d'autre. Vérification que `git diff --cached --name-only | grep -v '^controlvanne/'` est vide.

### Étape 2 — Fix `TiBillet/asgi.py` (bug `AppRegistryNotReady`) ✅

**Pourquoi le fix existe** : dans V2, `channels` est dans `INSTALLED_APPS` et `CHANNEL_LAYERS` Redis est configuré, mais `asgi.py` plaçait les imports applicatifs (qui dépendent des models Django) **avant** l'appel à `get_asgi_application()`. Résultat : tout serveur ASGI (Daphne en dev, Uvicorn en prod cible) crashait au démarrage avec `AppRegistryNotReady` — Django n'est pas encore complètement initialisé quand les imports d'apps sont exécutés.

Le fix : déplacer `get_asgi_application()` AVANT les imports applicatifs. Ordre Django officiel respecté.

**Pourquoi ça n'impacte pas la prod actuelle** :
- Prod V2 d'aujourd'hui : `start.sh` lance `gunicorn TiBillet.wsgi` → mode WSGI strict → `asgi.py` n'est **jamais importé**, jamais exécuté
- Le bug était donc **dormant en prod** — invisible tant que personne n'essaye de passer en ASGI
- En dev par contre (`manage.py runserver` avec `daphne` dans `INSTALLED_APPS`), Django remplace runserver par daphne → daphne charge `asgi.py` → le bug se manifeste

**Conséquence du fix** :
- Dev : débloque `runserver` (qui maintenant utilise daphne sans crash)
- Prod : strictement aucun changement de comportement (asgi.py toujours non chargé)
- Prérequis pour **PR 1** (activation WebSockets en prod), qui bascule `start.sh` sur Uvicorn

### Étape 3 — Ajouter `api/discovery/` aux URLs tenants ✅

**Pourquoi le fix existe** : le Pi tireuse s'appaire via `POST /api/discovery/claim/ {pin_code}`. L'app `discovery` existe déjà en V2 (utilisée par laboutik pour les tablettes POS — c'est le même mécanisme PIN), avec ses models, ses views et son serializer. **Mais la route URL n'était pas exposée dans `urls_tenants.py`**. Sans elle, le Pi reçoit un 404 à `make claim PIN=<code>` et ne peut jamais s'appairer.

Le fix : ajout d'une ligne `path('api/discovery/', include('discovery.urls'))` dans `TiBillet/urls_tenants.py`.

**Pourquoi ça n'impacte pas le fonctionnement tibillet** :
- L'app `discovery` est déjà chargée dans `INSTALLED_APPS`, ses models migrés en DB, ses views chargées en mémoire — rien de neuf ne s'ajoute en bas de la pile
- On **ne fait qu'ajouter une route** : aucune modification de model, de view, de permission, de serializer
- Le flow d'appairage tablette laboutik (`/api/discovery/claim/` via la tablette POS) fonctionne exactement comme avant
- Le flow d'appairage tireuse devient possible — c'est un ajout de capacité, pas une modification d'existant

### Étape 4 — Fix DEBUG IP locale ⏸️ Différée → PR 3

Fix discovery côté Pi LAN : quand le Pi est sur le réseau local et que le serveur a `DEBUG=True`, l'URL retournée doit être `http://` (pas `https://`) car le serveur dev n'a pas de TLS. Non bloquant pour la prod (qui est toujours en HTTPS), reportée dans une PR séparée.

---

## Étape 5 / Chantier 1 — LEGACY_FEDOW_V1 ✅

**Plan chantier** : supprimer le bloc `try: from fedow_connect ... except` dans `controlvanne/billing.py:345-419` qui synchronise vers un `fedow_django` V1 inexistant en V2. ~70 lignes mortes.

**Réalisé** : ✅ conforme. Bloc supprimé, plus aucune référence à `fedow_connect` dans `controlvanne/` (sauf `script_dev/` untracked = hors merge).

**Divergence** : aucune.

---

## Étape 6 / Chantier 6 — CALIBRATION ⚠️ Partiel

**Plan chantier** :
1. Supprimer 4 templates orphelins (`partial_mesure.html`, `partial_recap.html`, `partial_vide.html`, `partial_confirmation.html`) — référencent des URLs inexistantes (-270 lignes)
2. Simplifier le flow : retirer le bouton "Ignorer", remplacer le `Set JS` `window.ignoredSessions`, retirer le polling 8s, faire hériter de `admin/base_site.html`

**Réalisé** :
- ✅ 4 templates supprimés du disque et commités (commit `f3e6ba67`)
- ❌ Polling 8s, bouton Ignorer, `extends "base.html"` → **non touchés**

**⚠️ Point d'attention** : la simplification du flow calibration reste à faire (PR séparée non priorisée — le code marche, juste plus complexe que nécessaire).

---

## Étape 7 / Chantier 4 — BALANCE_ESTIMEE ⏸️ Différée → PR 2

**Plan chantier** : supprimer le recalcul `calculer_solde_total_cascade` au `pour_update` (-5 à 7 queries SQL/sec).

**Réalisé** : ⏸️ **différé**, le recalcul reste en place.

**Raison du report** : sans recalcul serveur, la "balance estimée" pendant le tirage se fige côté kiosk. Solution propre = décrément JS côté client + sync au pour_end. C'est plus de travail que la suppression seule, donc reporté en **PR 2 post-merge** (`PRs_apres_merge_controlvanne.md`).

**⚠️ Point d'attention** : tant que la PR 2 n'est pas faite, le coût SQL/sec reste. Acceptable hors festival, à surveiller en pic.

---

## Étape 8 / Chantier 5 — PUSH_WS_REFUS ✅

**Plan chantier** : helper `_push_refus(tireuse, message, **extras)` unique, push pour cas 2 (carte inconnue) et 4 (carte maintenance pendant service), conserver cas 5-8. Décisions : option B (carte maintenance refusée pendant service) + option i (audit via LogEntry).

**Réalisé** : ✅ conforme, 6 appels `_push_refus()` dans `authorize()` avec `present:True` + `uid` en extras.

**Point notable** : `present:True` déclenche le CAS 1 dans `panel_kiosk.js` (message affiché 4s). Comportement conservé pour homogénéité UX.

---

## Étape 9 / Chantier 2 — BILLING_REDONDANCE ✅ Option 3

**Plan initial** : Option 1 minimum viable = juste corriger le `payment_method=LOCAL_EURO` uniforme par un mapping `TNF→LOCAL_GIFT`, `TLF/FED→LOCAL_EURO`.

**Réalisé** : Option 3 complète :
- Import depuis `laboutik.views` : `ORDRE_CASCADE_FIDUCIAIRE`, `MAPPING_ASSET_CATEGORY_PAYMENT_METHOD`, `_obtenir_ou_creer_wallet`, `_calculer_qty_partielles`
- **N LigneArticle** (une par asset débité) au lieu d'une seule fourre-tout
- Quantité partielle calculée proportionnellement (`Decimal("1")` réparti)

**Raison du changement de scope** : Option 1 corrigeait le bug LNE pour les paiements 100% TNF ou 100% TLF, mais pas pour les paiements mixtes (cascade TNF + TLF) — qui sont précisément le cas d'usage tireuse. Option 3 est la seule qui rapporte correctement les ventes mixtes dans la clôture LNE.

**⚠️ Point d'attention** : 4 imports depuis `laboutik.views` créent un couplage inter-app. Si laboutik refactore son views.py, controlvanne casse silencieusement. Pas une PR séparée prévue pour ça (le coût/bénéfice ne justifie pas d'extraire un module commun pour 4 helpers).

---

## Étape 10 / Chantier 3 — AUTH_KIOSK ✅ Option minimale (3/5 manques traités)

**Plan initial chantier** : aligner sur `LaBoutikAuthBridgeView` = 5 fixes (TermUser + throttle + session 12h + is_active check + iri_to_uri).

**Réalisé option minimale** : 4 fixes ne touchant pas l'architecture :
- Throttle local `KioskBridgeThrottle` (10/min)
- Session 12h
- `escape(iri_to_uri(next_url))` (HTML + IRI — plus que prévu, le `next_url` est dans un f-string HTML, pas un `HttpResponseRedirect`)
- Commentaire cache multi-worker

**Non fait dans ce merge → PR 4** :
- ❌ Création de `TermUser` lié à `TireuseAPIKey` (Phase 1 dans `discovery/views.py`)
- ❌ `django.login(request, term_user)` + check `is_active`
- ❌ `_verifier_authentification_kiosk()` → `request.user.is_authenticated`

**⚠️ Points d'attention** :
- **Throttle local et non import laboutik** : scope `controlvanne_kiosk_bridge` distinct de `laboutik_auth_bridge` → compteurs Redis indépendants
- **NUM_PROXIES prod à vérifier** (sinon `REMOTE_ADDR` = IP nginx → 10/min partagé pour tous les Pi)
- **Pi non aligné** : session 12h serveur vs cookie Chromium persistant → 403 après 12h, voir `V2 Pi.md` Action 1
- **Caveat** : on a ajouté `escape()` en plus du `iri_to_uri` recommandé par le chantier, parce que `KioskTokenView` utilise un meta-refresh HTML et pas `HttpResponseRedirect`

---

## Points d'attention avant la PR

| # | Sujet | Action |
|---|---|---|
| ⚠️ | NUM_PROXIES prod (impact throttle étape 10) | Vérification VPS — voir `V2 Pi.md` Action 3b |
| ⚠️ | Cache prod = Redis et pas LocMemCache | Vérification VPS — voir `V2 Pi.md` Action 3a |
| ⚠️ | Pi session 12h vs cookie Chromium persistant | Décider option (a) timer systemd ou (b) session 24h — `V2 Pi.md` Action 1 |
| ⚠️ | Docstring `backend_client.py:128` trompeuse | À corriger — `V2 Pi.md` Action 2 |
| ℹ️ | WS pas activé en prod (asgi.py OK, mais `start.sh` WSGI) | PR 1 post-merge |
| ℹ️ | READMEs : 7 modifs appliquées (`dev_vps` → `V2`, path `.env`, sécurité étape 10) | À commiter (toujours en working tree) |

---

## PRs déférées (post-merge)

Référence : `PRs_apres_merge_controlvanne.md`

| PR | Sujet | Chantier review lié |
|---|---|---|
| 1 | Activation WebSockets prod (`start.sh` ASGI) | Hors chantiers (prérequis posé par étape 2) |
| 2 | Balance estimée JS côté kiosk | Chantier 4 (étape 7 différée) |
| 3 | Fix discovery URL http:// pour Pi LAN | Hors chantiers (étape 4 différée) |
| **4** | **AUTH_KIOSK alignement complet (TermUser + django.login)** | **Chantier 3 (étape 10 partielle)** |
| 5 | RSA 1024 QR codes festival | Hors chantiers |
| 6 | WebSocket laboutik (wsocket) | Hors chantiers |

**Note** : l'ancienne PR 4 (APK LaBoutik Cordova, `PinCodeLaBoutikView` + `WvLoginHardwareView`) a été abandonnée — `dev_vps` étant une branche de tests aux dérives méthodologiques, ces endpoints ne sont pas portés vers V2. Voir `PRs_apres_merge_controlvanne.md` § "PRs explicitement abandonnées".

---

## Bilan vs chantiers

| Catégorie review | Cible chantiers | Réalisé dans le merge |
|---|---|---|
| 🚨 Bloquants | Chantiers 1 + 2 | ✅ Les 2 traités |
| ⚠️ Sécurité | Chantier 3 (5 fixes) | ✅ 3/5 traités (option minimale), 2/5 en PR 4 |
| 🟡 YAGNI | Chantiers 4 + 5 + 6 | 1/3 complet (5), 1/3 partiel (6), 1/3 différé (4) |

**Bilan en lignes** : la review estimait ~-750 lignes net si tous les chantiers étaient appliqués. Réalisé dans ce merge ≈ **-340 lignes** (chantiers 1+2 complets, chantier 6 partiel, chantier 5 conforme, chantiers 3+4 partiels). Le reste (~-410 lignes) dans les PRs post-merge.

---

## Documents Obsidian de référence

| Fichier | Rôle |
|---|---|
| `Chek liste prepa merge.md` | Checklist 11 étapes (source de vérité du merge) |
| `Etape9_billing_option3_checklist.md` | Détail étape 9 (Option 3 N LigneArticle) |
| `Etape10_auth_kiosk_checklist.md` | Détail étape 10 (option minimale + raisonnement throttle) |
| `V2 Pi.md` | 4 actions côté Pi post-merge |
| `Diff WS en dev et prod.md` | WS dev vs prod (contexte PR 1) |
| `PRs_apres_merge_controlvanne.md` | 7 PRs déférées |
| `note ÉTAPE 8 — ...` | Décisions étape 8 (option B + option i) |
| `PLAN_MERGE_CONTROLVANNE.md` | Plan initial (peut être obsolète sur étapes 9/10) |
| `checklist_merge_controlvanne.md` | Ancienne checklist (référence historique) |

CHANTIER_*.md sources : `origin/dev_vps:TECH DOC/SESSIONS/CONTROLVANNE/merge_dev_vps/`.
