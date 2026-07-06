# CHANTIER-01 — Câblage de controlvanne dans Lespass

> **Pour les exécutants (session ou subagents) :** suivre les tâches dans l'ordre,
> cocher les étapes (`- [ ]`). Utiliser superpowers:executing-plans (inline) ou
> superpowers:subagent-driven-development (1 subagent par tâche).

**Date** : 2026-07-06
**Branche** : `main-fedow-import`
**Objectif** : brancher l'app `controlvanne` (tireuse à bière connectée) importée par
Mike (commit `f1308e8d`, version mergée de `controlvanne-merge`) : settings, URLs,
WebSocket, migrations, tests, appairage TI, dashboard admin.

**Architecture** : l'app est déjà sur le disque, complète et nettoyée (chantiers de
review appliqués, cf. `controlvanne/Synthese_merge_vs_chantiers.md`). Le travail est
du câblage pur + réactivation du flow d'appairage Tireuse dans `discovery`. Aucune
modification du code métier controlvanne.

**Références** :
- `controlvanne/Synthese_merge_vs_chantiers.md` — état du merge, PRs déférées
- Atomic : « Spec — Integration controlvanne dans Lespass », « Spec — Phase 6 :
  Client Pi controlvanne », « Spec — Simulateur Pi3 » (panneau debug `DEMO=1`)
- Source de comparaison : `/home/jonas/TiBillet/dev/lespass-main` (branche `new_pairing_and_nfc`)

## Contraintes globales (chaque tâche les inclut)

- **JAMAIS d'opération git** (add/commit/push/checkout/stash/reset/restore/clean).
  Le mainteneur committe. En fin de tâche : proposer le message de commit et s'arrêter.
- **Jamais de `ruff format`** sur un fichier existant.
- **Serveur tenu par le mainteneur dans byobu** (fenêtre 2, pane 1). Les modifs de
  `settings.py` / `asgi.py` exigent un **restart propre** (`Ctrl+C` puis `rsp`), pas
  un reload — demander au mainteneur.
- Tests : `docker exec lespass_django poetry run pytest tests/pytest/ -q` (~70 s).
  Ne PAS lancer pytest et Playwright en parallèle.
- Max 3 fichiers modifiés avant check + tests (tâche 1 : 4 fichiers, dérogation
  actée car câblage mécanique).
- `booking` est HORS SCOPE (porté sur une autre branche). Ne pas l'ajouter aux
  settings, ne pas décommenter sa carte dashboard.
- i18n : ne PAS lancer makemessages/compilemessages (mainteneur). Signaler les
  nouveaux msgids en fin de chantier.

## État vérifié au 2026-07-06 (ne pas re-vérifier)

- `controlvanne/` présent, 3 migrations, models complets (`TireuseAPIKey`,
  `TireuseBec`, `Debimetre`, `CarteMaintenance`, `RfidSession`, `SessionCalibration`,
  historiques, `ConfigurationTireuse`).
- Les 4 symboles importés par `controlvanne/billing.py` existent dans notre
  `laboutik/views.py` : `_obtenir_ou_creer_wallet` (l.1045), `ORDRE_CASCADE_FIDUCIAIRE`
  (l.3666), `MAPPING_ASSET_CATEGORY_PAYMENT_METHOD` (l.3672), `_calculer_qty_partielles`
  (l.3685). ✅
- `controlvanne/admin.py` s'enregistre sur `staff_admin_site`
  (`Administration/admin/site.py:81`) — auto-chargé dès que l'app est installée. ✅
- Les cartes dashboard tireuse existent déjà (`Administration/admin/dashboard.py:486-537`),
  rendues `#` par `_safe_rev` tant que l'admin n'est pas enregistré. ✅
- `Configuration.module_tireuse` existe (`BaseBillet/models.py:626`). ✅
- Settings `DEMO` / `DEMO_TAGID_*` déjà présents (l.624-634). ✅
- `rest_framework_api_key` déjà dans les apps (utilisé par `LaBoutikAPIKey`). ✅
- ⚠️ `controlvanne/migrations/0001_initial.py:16` dépend de
  `('BaseBillet', '0205_lignearticle_point_de_vente_and_more')` — **numérotation
  lespass-main**. Chez nous ce nom n'existe pas (notre 0205 =
  `futproduct_membershipproduct_posproduct`). Sans fix → `NodeNotFoundError` au migrate.
- ⚠️ `discovery/views.py` refuse le rôle TI (`raise ValueError("Tireuse pairing not
  available...")`) — à remplacer par le flow lespass-main.

---

## Tâche 1 — Câblage : settings + urls + asgi + fix dépendance migration

**Fichiers :**
- Modifier : `TiBillet/settings.py` (TENANT_APPS, ~l.206)
- Modifier : `TiBillet/urls_tenants.py` (~l.76)
- Modifier : `TiBillet/asgi.py` (l.10 et l.22)
- Modifier : `controlvanne/migrations/0001_initial.py` (l.16)

**Produit pour les tâches suivantes :** app installée + tables créées + routes HTTP
`/controlvanne/...` + routes WS `/ws/rfid/...` actives.

- [ ] **Étape 1.1 — settings.py : ajouter controlvanne aux TENANT_APPS**

Dans le tuple `TENANT_APPS`, après `'inventaire',` :

```python
    'laboutik',
    'inventaire',
    # Tireuses connectées (controlvanne) — paiement NFC via fedow_core local.
    # / Connected beer taps (controlvanne) — NFC payment via local fedow_core.
    'controlvanne',
```

- [ ] **Étape 1.2 — urls_tenants.py : exposer les routes controlvanne**

Après le bloc laboutik/inventaire (~l.76) :

```python
    # Tireuses connectées (controlvanne) — API Pi + kiosk + calibration
    # / Connected beer taps (controlvanne) — Pi API + kiosk + calibration
    path('controlvanne/', include('controlvanne.urls')),
```

- [ ] **Étape 1.3 — asgi.py : décommenter les routes WebSocket**

Ligne 10, remplacer :
```python
# from controlvanne.routing import websocket_urlpatterns as controlvanne_ws_urlpatterns
```
par :
```python
from controlvanne.routing import websocket_urlpatterns as controlvanne_ws_urlpatterns
```

Ligne 22, remplacer :
```python
                    # URLRouter(websocket_urlpatterns + controlvanne_ws_urlpatterns)
                    URLRouter(websocket_urlpatterns)
```
par :
```python
                    URLRouter(websocket_urlpatterns + controlvanne_ws_urlpatterns)
```

- [ ] **Étape 1.4 — fix de la dépendance migration**

`controlvanne/migrations/0001_initial.py` l.16, remplacer :
```python
        ('BaseBillet', '0205_lignearticle_point_de_vente_and_more'),
```
par :
```python
        # Dépendance réécrite pour ce repo : les champs POS de LigneArticle
        # (point_de_vente, etc.) vivent dans la 0222 (portage S6, migrations
        # fraîches — la 0205 de lespass-main n'existe pas ici).
        # / Dependency rewritten for this repo: LigneArticle POS fields live
        # in 0222 (S6 port, fresh migrations).
        ('BaseBillet', '0222_lignearticle_hmac_hash_lignearticle_point_de_vente_and_more'),
```

Justification : la 0001 crée des FK vers `BaseBillet.product`, `BaseBillet.lignearticle`
(+ `QrcodeCashless.cartecashless` 0021 ✅, `discovery` 0002 ✅, `laboutik` 0001 ✅).
Notre migration qui apporte `LigneArticle.point_de_vente` est la 0222.

- [ ] **Étape 1.5 — check**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```
Attendu : `System check identified no issues (0 silenced).`

- [ ] **Étape 1.6 — migrations**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing
docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations --check --dry-run
```
Attendu : les 3 migrations controlvanne appliquées sur les schémas tenant, et
`No changes detected` (aucune migration manquante).

- [ ] **Étape 1.7 — suite pytest complète (non-régression)**

```bash
docker exec lespass_django poetry run pytest tests/pytest/ -q
```
Attendu : même compte que la baseline (368 passed au 2026-07-06), 0 failed.

- [ ] **Étape 1.8 — restart serveur + smoke**

Demander au mainteneur un restart propre (`Ctrl+C` + `rsp` dans byobu — asgi.py et
settings.py ne sont pas hot-reloadés proprement, piège doc 12 « reload Daphne corrompu »).
Puis :

```bash
# Kiosk list : doit répondre (200 ou redirect auth, PAS 404)
curl -sk -o /dev/null -w "%{http_code}\n" https://lespass.tibillet.localhost/controlvanne/kiosk/
# Ping API tireuse (DRF router) : 401/403 attendu (clé API requise), PAS 404
curl -sk -o /dev/null -w "%{http_code}\n" https://lespass.tibillet.localhost/controlvanne/api/tireuse/ping/
```

Vérifier dans les logs byobu qu'aucun `No route found for ws/rfid/` n'apparaît quand
on ouvre la page kiosk dans Chrome (`https://lespass.tibillet.localhost/controlvanne/kiosk/`,
admin@admin.com) — le JS du kiosk ouvre `ws/rfid/all/`, on doit voir `WebSocket CONNECT`.

- [ ] **Étape 1.9 — proposer le commit au mainteneur**

Message suggéré : `feat(controlvanne): branche l'app dans settings, urls et asgi (routes WS rfid)`

---

## Tâche 2 — Port des tests pytest controlvanne

**Fichiers :**
- Créer : `tests/pytest/test_controlvanne_models.py` (copie de lespass-main)
- Créer : `tests/pytest/test_controlvanne_api.py` (copie)
- Créer : `tests/pytest/test_controlvanne_billing.py` (copie)

**Consomme :** l'app installée (tâche 1). **Produit :** filet de non-régression
pour les tâches 3-4.

- [ ] **Étape 2.1 — copier les 3 fichiers**

```bash
cp /home/jonas/TiBillet/dev/lespass-main/tests/pytest/test_controlvanne_models.py \
   /home/jonas/TiBillet/dev/lespass-main/tests/pytest/test_controlvanne_api.py \
   /home/jonas/TiBillet/dev/lespass-main/tests/pytest/test_controlvanne_billing.py \
   /home/jonas/TiBillet/dev/Lespass/tests/pytest/
```

Ils utilisent les fixtures standard (`tenant` — existe dans notre
`tests/pytest/conftest.py:221` — `schema_context`, `DjangoClient`) et leurs propres
fixtures locales (`cv_api_key`). Lire les 3 fichiers après copie : si une fixture ou
un import manque chez nous, l'adapter (pas de modification du code testé).

- [ ] **Étape 2.2 — lancer les tests controlvanne**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_controlvanne_models.py tests/pytest/test_controlvanne_api.py tests/pytest/test_controlvanne_billing.py -v
```
Attendu : tout vert. En cas d'échec : diagnostiquer (souvent : fixture de données POS
manquante → `create_test_pos_data --schema=lespass`, ou divergence de notre
`laboutik/views.py` en avance sur lespass-main). **Ne pas modifier le code métier
pour faire passer un test sans comprendre** — rapporter au mainteneur si doute.

- [ ] **Étape 2.3 — suite complète**

```bash
docker exec lespass_django poetry run pytest tests/pytest/ -q
```
Attendu : baseline + nouveaux tests, 0 failed.

- [ ] **Étape 2.4 — proposer le commit**

Message suggéré : `test(controlvanne): porte les 3 suites pytest (models, api, billing)`

---

## Tâche 3 — Appairage TI : réactiver le flow Tireuse dans discovery (TDD)

**Fichiers :**
- Créer : `tests/pytest/test_discovery_claim_creates_termuser.py` (copie de lespass-main)
- Créer : `tests/pytest/test_discovery_pin_pairing.py` (copie)
- Modifier : `discovery/views.py` (bloc de routage terminal_role, ~l.52-96, + réponse)

**Consomme :** `controlvanne.models.TireuseBec` / `TireuseAPIKey` (tâche 1).
**Produit :** `POST /api/discovery/claim/ {pin_code}` fonctionne pour le rôle TI et
renvoie `{server_url, api_key, device_name, tireuse_uuid}`.

- [ ] **Étape 3.1 — copier les tests discovery**

```bash
cp /home/jonas/TiBillet/dev/lespass-main/tests/pytest/test_discovery_claim_creates_termuser.py \
   /home/jonas/TiBillet/dev/lespass-main/tests/pytest/test_discovery_pin_pairing.py \
   /home/jonas/TiBillet/dev/Lespass/tests/pytest/
```

(`test_terminal_role_choices_sync.py` existe déjà chez nous — ne pas l'écraser.)

- [ ] **Étape 3.2 — lancer : les tests TI doivent ÉCHOUER**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_discovery_claim_creates_termuser.py tests/pytest/test_discovery_pin_pairing.py -v
```
Attendu : les tests des rôles LB/KI passent ; les tests impliquant le rôle TI
échouent (notre `views.py` lève `ValueError("Tireuse pairing not available...")`
→ réponse 500). C'est le rouge du TDD. Si TOUT passe, vérifier que les tests
couvrent bien le rôle TI avant de continuer.

- [ ] **Étape 3.3 — remplacer le bloc TI dans discovery/views.py**

Aligner sur lespass-main. Trois changements dans `ClaimPinView` :

**(a)** Le commentaire d'en-tête du bloc (~l.52-60) devient :

```python
        # Basculer dans le schéma du tenant pour créer les credentials.
        # Le type de credentials dépend du rôle du terminal (terminal_role) :
        # - LB (LaBoutik POS) : TermUser + LaBoutikAPIKey liée
        # - TI (Tireuse)      : TireuseAPIKey (flow inchangé)
        # - KI (Kiosque)      : TermUser + LaBoutikAPIKey liée (même pipeline que LB)
        # / Switch to tenant schema to create credentials.
        # Credential type depends on terminal_role:
        # - LB (LaBoutik POS): TermUser + linked LaBoutikAPIKey
        # - TI (Tireuse)     : TireuseAPIKey (unchanged flow)
        # - KI (Kiosk)       : TermUser + linked LaBoutikAPIKey (same pipeline as LB)
        tireuse_uuid = None
```

**(b)** Le bloc `elif pairing_device.terminal_role == TibilletUser.ROLE_TIREUSE:`
qui lève `ValueError("Tireuse pairing not available (controlvanne not ported)")`
est remplacé par :

```python
                elif pairing_device.terminal_role == TibilletUser.ROLE_TIREUSE:
                    # Flow Tireuse INCHANGÉ pour cette phase
                    # / Tireuse flow UNCHANGED for this phase
                    from controlvanne.models import TireuseBec, TireuseAPIKey
                    tireuse = TireuseBec.objects.filter(
                        pairing_device=pairing_device
                    ).first()
                    if not tireuse:
                        raise ValueError(
                            "Pairing role TIREUSE but no TireuseBec linked"
                        )
                    _key_obj, api_key_string = TireuseAPIKey.objects.create_key(
                        name=f"discovery-{pairing_device.uuid}"
                    )
                    tireuse_uuid = str(tireuse.uuid)
```

**(c)** La réponse finale (actuellement un `return Response({...})` inline) devient :

```python
        response_data = {
            "server_url": server_url,
            "api_key": api_key_string,
            "device_name": pairing_device.name,
        }
        # Si le device est lié à une tireuse, inclure l'UUID
        # / If the device is linked to a tap, include the UUID
        if tireuse_uuid:
            response_data["tireuse_uuid"] = tireuse_uuid

        return Response(response_data, status=status.HTTP_200_OK)
```

Le filet `else: raise ValueError(f"Unknown PairingDevice.terminal_role: ...")` est
conservé tel quel.

- [ ] **Étape 3.4 — lancer : les tests passent**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_discovery_claim_creates_termuser.py tests/pytest/test_discovery_pin_pairing.py tests/pytest/test_terminal_role_choices_sync.py -v
```
Attendu : tout vert.

- [ ] **Étape 3.5 — suite complète + commit**

```bash
docker exec lespass_django poetry run pytest tests/pytest/ -q
```
Message suggéré : `feat(discovery): réactive l'appairage des tireuses (TireuseAPIKey via claim PIN)`

---

## Tâche 4 — Dashboard : activer la carte module_tireuse

**Fichiers :**
- Modifier : `Administration/admin/dashboard.py` (~l.854-865, dict `MODULE_FIELDS`)

**Consomme :** admins controlvanne enregistrés (tâche 1). **Produit :** toggle
d'activation du module + carte dashboard avec liens vivants.

- [ ] **Étape 4.1 — décommenter le bloc module_tireuse dans MODULE_FIELDS**

Dans le dict `MODULE_FIELDS` (l.798), décommenter UNIQUEMENT le bloc tireuse
(laisser `module_booking` commenté — hors scope) :

```python
    # Tireuses connectees avec paiement NFC (controlvanne)
    # / Connected beer taps with NFC payment (controlvanne)
    "module_tireuse": {
        "name": _("Connected taps"),
        "description": _(
            "Connected beer tap management: RFID authorization, flow metering, kiosk display."
        ),
        "testid": "dashboard-card-tireuse",
        "link_url": "/controlvanne/kiosk/",
        "link_label": _("Open kiosk"),
        "link_icon": "fa-display",
    },
```

Note : `MODULE_FIELDS` sert à la fois de grille de cartes ET de whitelist du toggle
HTMX (`_build_modules_context` itère dessus) — décommenter suffit, pas d'autre câblage.

- [ ] **Étape 4.2 — check + smoke Chrome**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Puis sur `https://lespass.tibillet.localhost/` (admin@admin.com) :
1. Dashboard admin : la carte « Connected taps » apparaît avec son toggle.
2. Activer le module (modal de confirmation → HX-Refresh).
3. La section « Tireuses connectées » du dashboard (l.486-537) apparaît avec des
   liens VIVANTS (plus de `#` via `_safe_rev`) : TireuseBec, Débitmètres, Cartes
   maintenance, Sessions RFID.
4. Ouvrir chaque changelist controlvanne : 200, pas de crash.
5. Créer une `TireuseBec` de test via l'admin, puis ouvrir
   `/controlvanne/kiosk/` : la tireuse s'affiche. Avec `DEMO=1` (défaut en dev),
   le panneau simulateur Pi doit être visible (spec Atomic « Simulateur Pi3 »).

- [ ] **Étape 4.3 — test manuel de l'appairage TI de bout en bout**

1. Admin → discovery → créer un `PairingDevice` avec `terminal_role=TI` (noter le PIN).
2. Admin → controlvanne → lier la `TireuseBec` de test au `PairingDevice`
   (champ `pairing_device`).
3. Claim :
```bash
curl -sk -X POST https://lespass.tibillet.localhost/api/discovery/claim/ \
  -H "Content-Type: application/json" -d '{"pin_code": "<PIN>"}'
```
Attendu : 200 avec `{"server_url": ..., "api_key": ..., "device_name": ...,
"tireuse_uuid": ...}`. Rejouer le même PIN → 4xx (PIN consommé).

- [ ] **Étape 4.4 — suite pytest complète + commit**

```bash
docker exec lespass_django poetry run pytest tests/pytest/ -q
```
Message suggéré : `feat(admin): active la carte module_tireuse du dashboard`

---

## Tâche 5 — Documentation et clôture

**Fichiers :**
- Créer : `A TESTER et DOCUMENTER/controlvanne-cablage.md`
- Modifier : `CHANGELOG.md` (nouvelle entrée en tête)
- Modifier : `TECH_DOC/SESSIONS/FEDOW_IMPORT/ROADMAP.md` + `HANDOFF.md` (mise à jour
  d'état) ; créer `TECH_DOC/SESSIONS/CONTROLVANNE/INDEX.md`

- [ ] **Étape 5.1 — doc A TESTER**

Créer `A TESTER et DOCUMENTER/controlvanne-cablage.md` au format standard : tableau
des fichiers modifiés (tâches 1-4), scénarios de test manuels (= étapes 4.2 et 4.3
recopiées pas à pas), commandes pytest, note sur le restart serveur obligatoire.

- [ ] **Étape 5.2 — CHANGELOG**

Nouvelle entrée en tête, format projet (bilingue, tableau fichiers, flag migration
**Oui** : 3 migrations controlvanne appliquées sur les schémas tenant).

- [ ] **Étape 5.3 — mise à jour du hub FEDOW_IMPORT (docs en retard sur le code)**

- `ROADMAP.md` §1 : marquer C-C ✅ (C1 doc `c1-solde-complet-carte-fed.md` ;
  C2/C3 committés : `d8396a64`, `68188286`, `c3da37dc` — débit FED fin + fallback
  2e carte + tests) et ajouter une ligne « Lot controlvanne » ✅ pointant vers
  `TECH_DOC/SESSIONS/CONTROLVANNE/`.
- `HANDOFF.md` : bloc « MISE À JOUR 2026-07-06 » : C-C réalisé, controlvanne câblée,
  prochain = supervisor prod (chantier 2).
- Créer `TECH_DOC/SESSIONS/CONTROLVANNE/INDEX.md` : 3 lignes — lien vers ce chantier,
  vers `controlvanne/Synthese_merge_vs_chantiers.md`, et la liste des PRs déférées
  restantes (PR 2 balance estimée, PR 3 DEBUG IP LAN, PR 4 AUTH_KIOSK complet,
  simplification calibration).

- [ ] **Étape 5.4 — signaler au mainteneur**

- Les nouveaux msgids du dashboard (« Connected taps », etc.) → makemessages à
  lancer par le mainteneur.
- Message de commit suggéré : `docs(controlvanne): doc A TESTER + CHANGELOG + maj hub FEDOW_IMPORT`

---

## Hors scope de ce chantier (rappel)

- `booking` (autre branche).
- WebSockets en **prod** (supervisor mono-conteneur) → CHANTIER-02.
- PRs déférées de Mike : PR 2 (balance estimée JS kiosk), PR 3 (URL http:// Pi LAN
  en DEBUG), PR 4 (AUTH_KIOSK : TermUser + django.login pour le kiosk), simplification
  du flow calibration.
- Dette admin modulaire (`_safe_rev`, monolithe 180 Ko) → doc 12 FEDOW_IMPORT.
