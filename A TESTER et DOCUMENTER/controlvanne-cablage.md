# Controlvanne : câblage complet + appairage terminaux depuis l'admin

Chantier : `TECH_DOC/SESSIONS/CONTROLVANNE/CHANTIER-01-cablage-lespass.md`

## Ce qui a été fait

L'app `controlvanne` (tireuse à bière connectée, version mergée de Mike) est
branchée : settings, URLs, WebSocket, migrations, admin, appairage. En bonus
(demande mainteneur) : l'appairage des terminaux se pilote depuis la
changelist TermUser.

### Modifications

| Fichier | Changement |
|---|---|
| `TiBillet/settings.py` | `'controlvanne'` ajouté aux TENANT_APPS |
| `TiBillet/urls_tenants.py` | `path('controlvanne/', ...)` (API Pi + kiosk + calibration) |
| `TiBillet/asgi.py` | Routes WS `ws/rfid/all/` + `ws/rfid/<uuid>/` décommentées |
| `controlvanne/migrations/0001_initial.py` | Dépendance réécrite : BaseBillet `0205` (lespass-main) → `0222` (nos migrations fraîches S6) |
| `controlvanne/migrations/0004_*.py` | **Générée** : `reservoir_illimite` + `reservoir_ml` (champs du modèle sans migration) |
| `BaseBillet/models.py` | `SaleOrigin.TIREUSE = "TI"` (migration 0226) — requis par `controlvanne/billing.py` |
| `discovery/views.py` | Flow d'appairage TI réactivé : claim → `TireuseAPIKey` + `tireuse_uuid` dans la réponse |
| `AuthBillet/models.py` | `TermUserManager` filtre par `client_source` (au lieu de `client_admin`) — les terminaux appairés sont enfin visibles, sans jamais passer `is_tenant_admin()` |
| `Administration/admin_tenant.py` | `TermUserAdmin` : 4 permissions complètes, `last_login`, add toujours interdit (un TermUser naît d'un claim) |
| `Administration/admin/dashboard.py` | Menu « Terminaux hardware → Terminals » pointe vers la changelist **PairingDevice** (le process d'appairage complet) au lieu de TermUser |
| `discovery/admin.py` | `terminal_role` exposé (liste + formulaire), TI exclu de la création manuelle, rôle figé après création |
| `Administration/admin/dashboard.py` | Carte `module_tireuse` décommentée dans MODULE_FIELDS (booking reste masqué) |
| `tests/pytest/test_controlvanne_{models,api,billing}.py` | **Portés** (36 tests) |
| `tests/pytest/test_discovery_claim_creates_termuser.py` + `test_discovery_pin_pairing.py` | **Portés** + 2 tests TI écrits (TDD) |

## Migration nécessaire : OUI (déjà appliquée en dev)

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing
```
(controlvanne 0001→0004 + BaseBillet 0226)

## Tests automatiques

```bash
# Ciblés (47 tests)
docker exec lespass_django poetry run pytest tests/pytest/test_controlvanne_models.py tests/pytest/test_controlvanne_api.py tests/pytest/test_controlvanne_billing.py tests/pytest/test_discovery_claim_creates_termuser.py tests/pytest/test_discovery_pin_pairing.py -v
# Suite complète — attendu : 689 passed, 0 failed (~46 errors de setup flaky préexistantes, connues)
docker exec lespass_django poetry run pytest tests/pytest/ -q
```

## Tests manuels (⚠️ redémarrer le serveur d'abord : Ctrl+C puis rsp)

### Test 1 : appairage d'un terminal caisse depuis l'admin
1. Sidebar admin → section « Terminaux hardware » → « Terminals »
   (mène à `https://lespass.tibillet.localhost/admin/discovery/pairingdevice/`).
   Compte admin du tenant — ⚠️ `admin@admin.com` n'a AUCUN `client_admin` en base,
   utiliser `jturbeaux@pm.me` ou `admin-test-*`.
2. « Ajouter » : nom + rôle (LaBoutik POS ou Kiosque — pas de Tireuse ici, c'est voulu)
   → PIN affiché en gros après enregistrement
3. La changelist montre le PIN, le rôle, l'état (réclamé ou non)
4. Simuler le claim : `curl -sk -X POST https://lespass.tibillet.localhost/api/discovery/claim/ -H "Content-Type: application/json" -d '{"pin_code": "<PIN>"}'` → 200 avec api_key
5. Rafraîchir : PIN vidé, « Claimed » coché ; le compte terminal apparaît dans
   `/admin/AuthBillet/termuser/` (accessible en URL directe)
6. Rejouer le même PIN → 400 (PIN consommé, refusé par la validation)

### Test 2 : appairage tireuse (TI)
1. Activer le module « Connected taps » sur le dashboard admin (carte avec toggle)
2. Admin → Tireuses (controlvanne) → créer une `TireuseBec` → le PairingDevice TI est auto-créé, PIN visible sur la fiche
3. Claim avec ce PIN → 200 avec `api_key` **et** `tireuse_uuid`
4. Un PairingDevice TI créé à la main (impossible via le form, mais possible en shell) sans TireuseBec → claim = 500, PIN non consommé

### Test 3 : module + kiosk + WebSocket
1. Dashboard : carte « Connected taps » (toggle + « Open kiosk »)
2. `/controlvanne/kiosk/` : liste des tireuses ; avec `DEMO=1` (défaut dev), panneau simulateur Pi
3. Logs byobu : `WebSocket CONNECT /ws/rfid/all/` (aucun `No route found for ws/rfid/`)
4. Changelists controlvanne (TireuseBec, Débitmètres, Cartes maintenance, Sessions RFID) : 200,
   liens du dashboard vivants (plus de `#`)

## Points d'attention / dettes signalées

- **makemessages à lancer** (mainteneur) : nouveaux msgids FR du bandeau
  (« Appairage de terminaux », etc.) + « Connected taps » (EN existant).
- **Bugs préexistants découverts, hors chantier** :
  1. `SaleOrigin.LABOUTIK_TEST` référencé par `laboutik/archivage.py:124` et
     `laboutik/views.py:4169,4393` mais absent du modèle (crash latent).
  2. Tout 500 sur le schéma public casse l'email d'erreur admin :
     le rapport `AdminEmailHandler` évalue les `reverse_lazy` de la SIDEBAR
     (settings.py:575) sous `urls_public` → `KeyError 'staff_admin'`.
  3. `admin@admin.com` sans `client_admin` : ne passe pas
     `TenantAdminPermissionWithRequest` (compte de test à re-provisionner ?).
- **PRs déférées de Mike** (voir `controlvanne/Synthese_merge_vs_chantiers.md`) :
  balance estimée JS kiosk, URL http:// Pi LAN en DEBUG, AUTH_KIOSK complet
  (TermUser + django.login), simplification calibration.
- **WebSocket en prod** : rien ne sert `/ws/` en prod (gunicorn WSGI) —
  CHANTIER-02 (supervisord mono-conteneur : gunicorn + daphne + celery).
