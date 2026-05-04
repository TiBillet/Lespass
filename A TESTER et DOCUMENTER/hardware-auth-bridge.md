# Authentification hardware via TermUser

## Ce qui a été fait

Refactor de l'auth des terminaux LaBoutik (POS + Android) via un pont
`/laboutik/auth/bridge/` qui échange une clé API contre un cookie de session
Django. Création automatique d'un TermUser à l'appairage.

### Modifications

| Fichier | Changement |
|---|---|
| `AuthBillet/models.py` | +terminal_role sur TibilletUser, TermUser.save() auto client_source, TermUserManager filtre sur client_source |
| `discovery/models.py` | +terminal_role sur PairingDevice |
| `discovery/views.py` | ClaimPinView crée un TermUser pour les rôles LB et KI, +helper _create_laboutik_terminal |
| `BaseBillet/models.py` | LaBoutikAPIKey.user OneToOneField nullable |
| `BaseBillet/permissions.py` | +HasLaBoutikTerminalAccess (HasLaBoutikAccess V1 inchangée) |
| `laboutik/views.py` | +LaBoutikAuthBridgeView (CSRF exempt, POST only, 10/min throttle, security logging) |
| `laboutik/urls.py` | +path auth/bridge/ |
| `Administration/admin/users.py` | +TermUserAdmin (lecture seule, bulk revoke action) |
| `Administration/admin/dashboard.py` | +sidebar entry "Terminals" (visible si module_caisse OR module_monnaie_locale OR module_tireuse) |
| `Administration/templates/admin/termuser/change_form_before.html` | Bannière info sur page détail |

## Tests à réaliser

### Test 1 : Appairage LaBoutik complet

1. Se connecter à `/admin/` comme admin tenant (admin@admin.com)
2. Activer `module_caisse` dans le Dashboard (si pas déjà fait)
3. Dans la sidebar, aller dans "Device pairing (PIN)"
4. Créer un nouveau PairingDevice avec :
   - `name`: "Test POS 1"
   - `terminal_role`: "LaBoutik POS"
5. Noter le PIN affiché
6. Dans un terminal, exécuter :
   ```bash
   curl -X POST https://lespass.tibillet.localhost/api/discovery/claim/ \
        -H "Content-Type: application/json" \
        -d '{"pin_code": PIN_ICI}'
   ```
7. Vérifier la réponse : `{ "server_url": "https://...", "api_key": "xxx", "device_name": "Test POS 1" }`
8. Dans l'admin, aller dans "Terminals" (nouvelle entrée sidebar)
9. Vérifier qu'un TermUser existe avec :
   - email : `<uuid>@terminals.local`
   - terminal_role : "LaBoutik POS"
   - is_active : True

### Test 2 : Bridge + accès caisse

1. Avec la clé obtenue au Test 1, faire :
   ```bash
   curl -X POST -c cookies.txt https://lespass.tibillet.localhost/laboutik/auth/bridge/ \
        -H "Authorization: Api-Key API_KEY_ICI"
   ```
2. Vérifier : status 204, fichier `cookies.txt` contient `sessionid=...`
3. Puis :
   ```bash
   curl -b cookies.txt https://lespass.tibillet.localhost/laboutik/caisse/
   ```
4. Vérifier : status 200 (HTML de la caisse)

### Test 3 : Révocation

1. Admin > Terminals > sélectionner le TermUser du Test 1
2. Dans le menu Actions en haut, choisir "Revoke selected terminals (is_active=False)" et cliquer "Go"
3. Alternative : cliquer sur le TermUser, voir la bannière de révocation, changer is_active=False manuellement et sauvegarder
4. Re-tenter `curl -b cookies.txt .../laboutik/caisse/`
5. Vérifier : redirection ou 401 (session devenue anonyme)

### Test 4 : Rôle Kiosque

1. Créer un PairingDevice role "Kiosk / self-service"
2. Claim le PIN
3. Vérifier qu'un TermUser role KI est créé (même flow que LB pour l'instant)

### Test 5 : Clé V1 orpheline (compat)

1. Créer manuellement une LaBoutikAPIKey sans user (via shell Django) :
   ```bash
   docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
   from django_tenants.utils import tenant_context
   from Customers.models import Client
   from BaseBillet.models import LaBoutikAPIKey
   t = Client.objects.get(schema_name='lespass')
   with tenant_context(t):
       key_obj, key_str = LaBoutikAPIKey.objects.create_key(name='test-legacy-v1', user=None)
       print('key:', key_str)
   "
   ```
2. Utiliser cette clé dans le header sur une route V1 (ex: `/laboutik/paiement/`)
3. Vérifier : accès accordé (fallback V1 via HasLaBoutikAccess)
4. Tenter `POST /laboutik/auth/bridge/` avec cette clé
5. Vérifier : 400 avec message "Legacy API key, bridge flow not available"

## Compatibilité

- Les routes Laboutik V1 existantes utilisent toujours `HasLaBoutikAccess` (inchangée). Une route (CaisseViewSet) a été migrée vers V2 `HasLaBoutikTerminalAccess`
- Les clients V1 (clés sans user, via header Api-Key) continuent de fonctionner sur les routes V1
- Seul le nouvel endpoint `/auth/bridge/` et CaisseViewSet utilisent le pattern V2 session

## Logs de sécurité

L'endpoint `/laboutik/auth/bridge/` logue :
- `logger.warning` : header manquant / clé vide / clé inconnue (IP incluse) / user révoqué (email inclus)
- `logger.info` : clé V1 legacy utilisée (nom de la clé) / session ouverte avec succès (email terminal)

Check ces logs en cas d'investigation sécurité.
