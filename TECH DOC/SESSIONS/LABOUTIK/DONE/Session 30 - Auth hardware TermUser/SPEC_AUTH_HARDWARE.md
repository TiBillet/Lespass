# SPEC — Authentification hardware via TermUser (Phase 1 : LaBoutik)

**Date :** 2026-04-15
**Statut :** Design validé, prêt pour plan d'implémentation
**Scope :** LaBoutik (POS PC + Android). Controlvanne hors scope (conçu compatible, implémenté plus tard).

---

## 1. Contexte et problème

### Situation actuelle

Deux catégories de machines se connectent au serveur Django Lespass :

- **Terminaux LaBoutik** (POS PC, tablettes Android) — caisses
- **Pi controlvanne** — tireuses connectées (hors scope cette phase)

Les deux passent par un appairage initial via `discovery/PairingDevice` (code PIN 6 chiffres), qui retourne une clé API (`LaBoutikAPIKey` ou `TireuseAPIKey`).

**Problème côté Laboutik :**
- Le client Android (Cordova) de Nicolas utilise `fetch()` avec header `Authorization: Api-Key` puis injecte le HTML de la réponse dans le DOM. Hack fragile.
- `window.location` ne peut pas transporter de headers HTTP personnalisés → nécessité d'un pont explicite.
- La signature RSA prévue dans le template `login_hardware.html` n'a jamais été implémentée côté backend. **Support RSA abandonné.**

**Décisions d'architecture prises :**
- Passer par **cookie de session Django** pour tous les appels métier
- Garder la clé API **uniquement** comme secret d'amorçage (trade-contre-cookie)
- Utiliser l'infrastructure `TibilletUser` existante (champ `espece`, proxy `TermUser`)
- Révocation via `user.is_active = False` (natif Django, instantané)

---

## 2. Décisions architecturales validées

| Décision | Valeur | Raison |
|---|---|---|
| Périmètre | LaBoutik seul (design compat Pi) | Rodage du pattern sur client demandeur |
| Type de terminal | Champ `terminal_role` sur `PairingDevice` + `TibilletUser` | Admin choisit au paring |
| Permission | Nouvelle `HasLaBoutikTerminalAccess` par-dessus | `HasLaBoutikAccess` V1 reste intouchée |
| Email TermUser | `<pairing_uuid>@terminals.local` | Filtrable, pas de confusion avec humain |
| Tenant scoping | Via `client_source` (champ existant) | Zéro nouveau champ |
| Relation API key ↔ user | `OneToOneField` nullable | Compat V1 + simplicité V2 |
| Migration clés existantes | FK nullable | Clés V1 restent valides sur chemin legacy |
| Session duration | 12h via `set_expiry()` par session | Hygiène, sans impacter admins humains |
| Hardware type | Hors scope (YAGNI) | On ajoutera quand un vrai besoin apparaît |
| Re-pairing | Via nouveau `PairingDevice` | Simple, pas de logique dédiée |

---

## 3. Architecture cible

### Flow complet

```
1. APPAIRAGE (une seule fois par appareil)

   Admin Unfold ─── crée ───► PairingDevice
                              { pin_code, terminal_role }

   Client ─── POST /api/discovery/claim/ ───► ClaimPinView
                                              ├─ valide PIN
                                              ├─ si role = LB : crée TermUser + LaBoutikAPIKey
                                              ├─ si role = TI : flow Tireuse (inchangé)
                                              └─ consomme PIN

   Client ◄── { server_url, api_key } ───

2. LOGIN HARDWARE (à chaque lancement d'app)

   Client ─── POST /laboutik/auth/bridge/ ───►  laboutik_auth_bridge
              Header: Authorization: Api-Key xxx  ├─ valide clé
                                                  ├─ si user is None : 400 (clé V1)
                                                  ├─ si not user.is_active : 401
                                                  ├─ login(request, term_user)
                                                  └─ session.set_expiry(12h)

   Client ◄── 204 No Content + Set-Cookie: sessionid=... ───

3. REQUÊTES MÉTIER (cookie automatique)

   Client ─── GET/POST /laboutik/* ───►  HasLaBoutikTerminalAccess
              Cookie: sessionid=...       ├─ V2 path : espece=TE + role=LB + client_source match
                                          └─ V1 fallback : délègue à HasLaBoutikAccess

4. RÉVOCATION (admin Unfold)

   Admin ─── bouton "Revoke terminal" ───► user.is_active = False
                                            ▼
                                   Toutes sessions ouvertes deviennent anonymes
                                   (AuthMiddleware.get_user retourne AnonymousUser)
```

### Principes

- Auth Django native exclusivement (`login()`, `AuthenticationMiddleware`, `is_active`)
- Zéro flag de session, zéro index inversé
- La clé API n'est utilisée que sur `/auth/bridge/` (secret d'amorçage)
- `HasLaBoutikAccess` V1 strictement intouchée (compatibilité legacy)
- `HasLaBoutikTerminalAccess` V2 enveloppe la V1 comme fallback

---

## 4. Modèles et migrations

### 4.1. `TibilletUser` (`AuthBillet/models.py`)

**Nouveaux champs :**

```python
ROLE_LABOUTIK = 'LB'
ROLE_TIREUSE  = 'TI'
ROLE_KIOSQUE  = 'KI'
TERMINAL_ROLE_CHOICES = (
    (ROLE_LABOUTIK, _('LaBoutik POS')),
    (ROLE_TIREUSE,  _('Connected tap')),
    (ROLE_KIOSQUE,  _('Kiosk / self-service')),
)

terminal_role = models.CharField(
    max_length=2,
    choices=TERMINAL_ROLE_CHOICES,
    null=True, blank=True,
    verbose_name=_("Terminal role"),
    help_text=_("Only set for espece=TE. Drives permission checks."),
)
```

**`TYPE_ANDR = 'AN'`** : **déprécié**, on ne s'en sert plus pour les nouveaux terminaux. Valeur enum conservée pour compat des données existantes (s'il y en a).

**Modification `TermUser.save()` :**

```python
class TermUser(TibilletUser):
    class Meta:
        proxy = True
        verbose_name = _("Terminal")
        verbose_name_plural = _("Terminals")

    objects = TermUserManager()

    def save(self, *args, **kwargs):
        if not self.pk:
            self.client_source = connection.tenant
        self.espece = TibilletUser.TYPE_TERM
        self.email = self.email.lower()
        super().save(*args, **kwargs)
```

**Migration :** `AddField terminal_role nullable` — zéro risque.

### 4.2. `PairingDevice` (`discovery/models.py`)

**Nouveau champ :**

```python
terminal_role = models.CharField(
    max_length=2,
    choices=TibilletUser.TERMINAL_ROLE_CHOICES,
    default=TibilletUser.ROLE_LABOUTIK,
    verbose_name=_("Terminal role"),
    help_text=_("Type of hardware role being paired"),
)
```

**Migration :** `AddField` avec default — zéro risque sur les rares `PairingDevice` existants non consommés.

### 4.3. `LaBoutikAPIKey` (`BaseBillet/models.py`)

**Nouveau champ :**

```python
class LaBoutikAPIKey(AbstractAPIKey):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='laboutik_api_key',
        null=True, blank=True,
        verbose_name=_("Terminal user"),
        help_text=_("TermUser linked (V2 bridge flow). Null for legacy V1 keys."),
    )

    class Meta:
        ordering = ("-created",)
        verbose_name = "LaBoutik API Key"
        verbose_name_plural = "LaBoutik API Keys"
```

**Migration :** `AddField user (OneToOneField, null=True)` — compat totale V1.

---

## 5. Endpoint `/laboutik/auth/bridge/`

### Vue (`laboutik/views.py`)

```python
from django.contrib.auth import login
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from rest_framework.throttling import AnonRateThrottle

from BaseBillet.models import LaBoutikAPIKey


@csrf_exempt
@require_POST
def laboutik_auth_bridge(request):
    """
    Pont d'authentification hardware : échange une clé API contre un cookie de session.
    / Hardware auth bridge: trades an API key for a session cookie.

    LOCALISATION : laboutik/views.py

    Flux :
    1. Client POST avec header Authorization: Api-Key xxx
    2. Validation de la clé (401 si invalide)
    3. Si la clé n'a pas de user lié (legacy V1) : 400
    4. Si user.is_active = False (révoqué) : 401
    5. django.contrib.auth.login() pose le cookie sessionid
    6. set_expiry(12h) — session courte par hygiène

    CSRF exempt : légitime car
    - la clé API joue l'auth forte pour cette seule requête
    - le client Cordova/WebView n'a pas encore de cookie CSRF
    - les requêtes suivantes (avec cookie session) auront la protection CSRF normale
    """
    auth_header = request.META.get('HTTP_AUTHORIZATION', '')
    if not auth_header.startswith('Api-Key '):
        return HttpResponse(status=401)

    api_key_string = auth_header[len('Api-Key '):].strip()
    if not api_key_string:
        return HttpResponse(status=401)

    try:
        api_key = LaBoutikAPIKey.objects.get_from_key(api_key_string)
    except LaBoutikAPIKey.DoesNotExist:
        return HttpResponse(status=401)

    if api_key.user is None:
        return HttpResponse(
            "Legacy API key, bridge flow not available. Please re-pair the device.",
            status=400,
        )

    term_user = api_key.user
    if not term_user.is_active:
        return HttpResponse(status=401)

    login(request, term_user)
    request.session.set_expiry(60 * 60 * 12)
    return HttpResponse(status=204)
```

### Throttle

Implémenter la vue comme `APIView` DRF (plutôt que fonction) pour exploiter `throttle_classes = [BridgeThrottle]` proprement, avec `BridgeThrottle(AnonRateThrottle)` de rate `10/min`. Le décorateur `@csrf_exempt` se met via `method_decorator` sur `dispatch`.

### URL (`laboutik/urls.py`)

```python
urlpatterns = [
    path("auth/bridge/", laboutik_auth_bridge, name="laboutik-auth-bridge"),
    # ... paths existants ...
] + router.urls
```

---

## 6. Permissions

### 6.1. `HasLaBoutikAccess` (`BaseBillet/permissions.py`) — INCHANGÉE

Cette classe reste strictement identique. Les clients V1 qui appellent l'API avec leur clé en header `Api-Key` continuent de fonctionner.

### 6.2. `HasLaBoutikTerminalAccess` — NOUVELLE

```python
from AuthBillet.models import TibilletUser


class HasLaBoutikTerminalAccess(permissions.BasePermission):
    """
    Permission V2 : accepte les TermUser authentifiés via le bridge (session),
    tout en gardant la compatibilité V1 via HasLaBoutikAccess en fallback.
    / V2 permission: accepts bridge-authenticated TermUsers (session),
    while keeping V1 compat via HasLaBoutikAccess fallback.
    """

    def has_permission(self, request, view):
        user = request.user

        # Chemin V2 : TermUser avec rôle LaBoutik lié à ce tenant
        # / V2 path: TermUser with LaBoutik role linked to this tenant
        if user and user.is_authenticated:
            if user.espece == TibilletUser.TYPE_TERM:
                if user.terminal_role == TibilletUser.ROLE_LABOUTIK:
                    if user.client_source_id == connection.tenant.pk:
                        return True

        # Fallback V1 : délègue (admin session OU header Api-Key)
        # / V1 fallback: delegate (admin session OR Api-Key header)
        return HasLaBoutikAccess().has_permission(request, view)
```

### 6.3. Stratégie d'adoption

| Route | Permission utilisée |
|---|---|
| Routes Laboutik V1 existantes | `HasLaBoutikAccess` (inchangée) |
| `/laboutik/auth/bridge/` | Aucune (AllowAny, valide la clé en interne) |
| Routes Laboutik V2 (futures ou migrées) | `HasLaBoutikTerminalAccess` |

**Migration progressive possible** : une route V1 peut être migrée vers V2 en changeant juste sa permission, sans casser les clients V1 (fallback intégré).

---

## 7. Flow claim modifié (`discovery/views.py`)

### `ClaimPinView.post()` refactorisé

```python
def post(self, request):
    serializer = PinClaimSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    pairing_device = serializer.device
    tenant_for_this_device = pairing_device.tenant

    primary_domain = tenant_for_this_device.get_primary_domain()
    if not primary_domain:
        return Response({"error": "Tenant configuration error."}, status=500)

    server_url = f"https://{primary_domain.domain}"
    tireuse_uuid = None

    try:
        with tenant_context(tenant_for_this_device):
            # Routage selon terminal_role du PairingDevice
            # / Routing based on PairingDevice.terminal_role
            from AuthBillet.models import TibilletUser

            if pairing_device.terminal_role == TibilletUser.ROLE_LABOUTIK:
                # Flow Laboutik V2 : création TermUser + clé liée
                # / Laboutik V2 flow: TermUser creation + linked key
                api_key_string = _create_laboutik_terminal(pairing_device)

            elif pairing_device.terminal_role == TibilletUser.ROLE_TIREUSE:
                # Flow Tireuse INCHANGÉ pour cette phase (hors scope)
                # / Tireuse flow UNCHANGED for this phase (out of scope)
                from controlvanne.models import TireuseBec, TireuseAPIKey
                tireuse = TireuseBec.objects.filter(pairing_device=pairing_device).first()
                if not tireuse:
                    raise ValueError("Pairing role TIREUSE but no TireuseBec linked")
                _key_obj, api_key_string = TireuseAPIKey.objects.create_key(
                    name=f"discovery-{pairing_device.uuid}"
                )
                tireuse_uuid = str(tireuse.uuid)

            else:
                # Rôle non encore implémenté (ex: Kiosque) — Phase suivante
                # / Role not yet implemented (e.g. Kiosk) — next phase
                return Response(
                    {"error": f"Terminal role '{pairing_device.terminal_role}' not yet implemented."},
                    status=status.HTTP_501_NOT_IMPLEMENTED,
                )

    except Exception as error:
        logger.error(f"Discovery claim failed: {error}")
        return Response({"error": "Failed to create device credentials."}, status=500)

    pairing_device.claim()

    response_data = {
        "server_url": server_url,
        "api_key": api_key_string,
        "device_name": pairing_device.name,
    }
    if tireuse_uuid:
        response_data["tireuse_uuid"] = tireuse_uuid

    return Response(response_data, status=200)
```

### Helper `_create_laboutik_terminal`

```python
def _create_laboutik_terminal(pairing_device):
    """
    Crée un TermUser (rôle LaBoutik ou Kiosque) et sa clé API liée.
    / Creates a TermUser (LaBoutik or Kiosk role) and its linked API key.

    LOCALISATION : discovery/views.py
    """
    from AuthBillet.models import TermUser, TibilletUser
    from BaseBillet.models import LaBoutikAPIKey

    email_synthetique = f"{pairing_device.uuid}@terminals.local"
    term_user = TermUser.objects.create(
        email=email_synthetique,
        terminal_role=pairing_device.terminal_role,
        accept_newsletter=False,
    )
    # espece=TE et client_source=tenant auto-posés par TermUser.save()
    # / espece=TE and client_source=tenant auto-set by TermUser.save()

    _key_obj, api_key_string = LaBoutikAPIKey.objects.create_key(
        name=f"discovery-{pairing_device.uuid}",
        user=term_user,
    )
    return api_key_string
```

---

## 8. Admin Unfold

### 8.1. `TermUserAdmin` (`Administration/admin_tenant.py`)

Nouvelle `ModelAdmin` pour le proxy `TermUser` :

- `list_display` : email tronqué, terminal_role, is_active, last_see, date_joined
- `list_filter` : terminal_role, is_active
- `search_fields` : email
- `readonly_fields` : tous sauf `is_active` (révocation)
- `has_add_permission` : False (terminaux créés via `/claim/` uniquement)
- `has_*_permission` autres : `TenantAdminPermissionWithRequest(request)`
- Action bulk : `revoke_terminals` → `queryset.update(is_active=False)`
- Bouton individuel via `change_form_before.html` : "Revoke this terminal"

### 8.2. Sidebar Unfold

Nouvelle entrée dans la section conditionnelle `module_caisse` :
```python
{
    "title": _("Terminals"),
    "link": reverse_lazy("admin:AuthBillet_termuser_changelist"),
}
```

### 8.3. `LaBoutikAPIKey` dans l'admin

**Non exposé.** La clé est un détail d'implémentation, liée au `TermUser` via OneToOne. Cycle de vie géré entièrement par le flow claim + révocation `is_active`.

---

## 9. Tests

### 9.1. Fixture `terminal_client` (conftest)

**Fichier :** `tests/pytest/conftest.py` (ajout)

```python
@pytest.fixture
def terminal_client(tenant):
    """
    Client Django authentifié comme TermUser Laboutik (session posée).
    / Django Client authenticated as a Laboutik TermUser (session set).

    Remplace auth_headers (header Api-Key) pour les tests V2.
    / Replaces auth_headers (Api-Key header) for V2 tests.
    """
    with tenant_context(tenant):
        term_user = TermUser.objects.create(
            email=f"{uuid4()}@terminals.local",
            terminal_role=TibilletUser.ROLE_LABOUTIK,
            accept_newsletter=False,
        )
    client = Client()
    client.force_login(term_user)
    return client
```

### 9.2. Nouveaux fichiers de test

**`tests/pytest/test_hardware_auth_bridge.py`** — 8 tests :
- Bridge avec clé valide → 204 + cookie
- Bridge avec clé invalide → 401
- Bridge avec clé sans user (V1) → 400
- Bridge avec user révoqué → 401
- Bridge sans header → 401
- Throttle après 10 requêtes → 429
- Flow E2E : bridge → requête métier → 200
- Révocation (is_active=False) → requête suivante 401/403

**`tests/pytest/test_discovery_claim_creates_termuser.py`** — 6 tests :
- Claim role=LB → TermUser role=LB, espece=TE
- Claim role=LB → LaBoutikAPIKey.user == TermUser
- Claim role=KI → TermUser role=KI
- Claim → TermUser.client_source == tenant
- Claim → email = `<uuid>@terminals.local`
- Claim role=TI → pas de LaBoutikAPIKey créé (flow Tireuse inchangé)

### 9.3. Migration des tests Laboutik existants

~80 tests pytest laboutik : find/replace mécanique
- `**auth_headers` → utilisation de `terminal_client`
- `client.post(url, data, **auth_headers)` → `terminal_client.post(url, data)`

Estimation : 1-2h de travail majoritairement mécanique.

### 9.4. Tests E2E Playwright

**`tests/e2e/test_laboutik_auth_bridge.py`** — 1 scénario complet simulant le flow Nicolas :
1. POST bridge avec header Api-Key
2. Navigation vers `/laboutik/caisse/`
3. Vérification affichage sans 401

### 9.5. Pièges à documenter dans `tests/PIEGES.md`

- `TermUser.save()` force `espece=TE` — tester avec espece explicite
- `LaBoutikAPIKey.user` OneToOne — une clé par user max
- `client.force_login()` ne pose pas `set_expiry(12h)` — utiliser le vrai bridge pour tester l'expiration

---

## 10. Documentation utilisateur

### 10.1. `CHANGELOG.md`

Nouvelle entrée :

```markdown
## X. Authentification hardware via TermUser / Hardware auth via TermUser

**Quoi / What:** Refactor de l'auth des terminaux LaBoutik (POS + Android) via
un pont `/laboutik/auth/bridge/` qui échange une clé API contre un cookie de
session Django. Création automatique d'un TermUser à l'appairage.

**Pourquoi / Why:** Simplifier le flow côté client (plus de hack HTML injection),
aligner avec le pattern Pi controlvanne, permettre une révocation instantanée
via is_active=False.

### Fichiers modifiés
| Fichier | Changement |
|---|---|
| AuthBillet/models.py | +terminal_role, +TERMINAL_ROLE_CHOICES, TermUser.save() |
| discovery/models.py | +terminal_role sur PairingDevice |
| discovery/views.py | ClaimPinView route selon terminal_role, crée TermUser |
| BaseBillet/models.py | LaBoutikAPIKey.user OneToOneField nullable |
| BaseBillet/permissions.py | +HasLaBoutikTerminalAccess (HasLaBoutikAccess inchangée) |
| laboutik/views.py | +laboutik_auth_bridge |
| laboutik/urls.py | +path auth/bridge/ |
| Administration/admin_tenant.py | +TermUserAdmin |

### Migration
- TibilletUser.terminal_role (nullable) : AddField
- PairingDevice.terminal_role (default LB) : AddField
- LaBoutikAPIKey.user (OneToOneField nullable) : AddField
```

### 10.2. `A TESTER et DOCUMENTER/hardware-auth-bridge.md`

Checklist manuelle (créer, claim, bridge, requête, révocation, re-pair).

### 10.3. Traductions

```bash
docker exec lespass_django poetry run django-admin makemessages -l fr
docker exec lespass_django poetry run django-admin makemessages -l en
# édition .po pour nouveaux strings
docker exec lespass_django poetry run django-admin compilemessages
```

---

## 11. Hors scope (phase suivante)

- **Controlvanne** : adoption du même pattern (TermUser avec `terminal_role=TI`, bridge dédié remplaçant `/auth-kiosk/`, permission `HasTireuseTerminalAccess` par-dessus `HasTireuseAccess`)
- **Kiosque** : rôle `KI` déjà dans les choices, pas d'implémentation
- **iOS / futurs hardware** : pas d'ajout `hardware_type` (YAGNI)
- **Audit log des logins** : pas de journal dédié (`user.last_login` natif Django suffit)
- **Migration des routes V1 Laboutik vers V2** : au cas par cas, pas global

---

## 12. Risques et limites

| Risque | Mitigation |
|---|---|
| Session 12h expire en plein service | `SESSION_SAVE_EVERY_REQUEST=True` refresh l'expiration à chaque requête — une caisse active ne se déconnecte pas |
| Clé API exposée dans logs nginx si header mal configuré | `Authorization` n'est pas loggué par défaut ; POST body non plus |
| Client Android en mode offline à `resume` | Le ré-auth échouera — prévoir UX explicite (écran "Hors ligne") |
| TermUser apparaît dans queries `TibilletUser.objects.all()` | Filtrer via proxy `HumanUser` ou par `espece=HU` là où c'est pertinent (newsletters, exports utilisateurs, etc.) |
| Tests E2E existants cassent (anciens `auth_headers`) | Fixture `terminal_client` documentée, migration find/replace balisée dans la spec |

---

## 13. Critères d'acceptation

- [ ] Un `PairingDevice` créé avec `terminal_role=LB` produit un `TermUser` avec `espece=TE`, `terminal_role=LB`, `client_source=tenant`
- [ ] `POST /laboutik/auth/bridge/` avec une clé valide retourne 204 et pose un cookie session
- [ ] Le cookie session permet ensuite d'accéder à `/laboutik/caisse/` sans header
- [ ] `user.is_active = False` bloque immédiatement les requêtes suivantes avec le cookie
- [ ] Un client V1 (clé sans user, header Api-Key) continue de fonctionner sur les routes V1
- [ ] `TermUserAdmin` dans Unfold liste les terminaux, filtre par rôle, permet révocation bulk + individuelle
- [ ] Les 80 tests pytest Laboutik passent (migration `auth_headers` → `terminal_client`)
- [ ] Les nouveaux tests (`test_hardware_auth_bridge.py`, `test_discovery_claim_creates_termuser.py`) passent
- [ ] Le test E2E Playwright simulant Nicolas passe
- [ ] Traductions FR/EN à jour

---

## 14. Dépendances

- Aucune dépendance Python nouvelle
- Aucune nouvelle app Django
- `rest_framework_api_key` (déjà installé) — pour `AbstractAPIKey.create_key(user=...)`
- `django.contrib.auth` (natif) — pour `login()`, `is_active`

---

## 15. Références

- Session précédente : cascade multi-asset NFC (Session 29)
- Pièges tests : `tests/PIEGES.md` sections 9.40-9.44
- Documentation Nicolas (Android client) : à coordonner
- Plan mono-repo : `TECH DOC/Laboutik sessions/PLAN_LABOUTIK.md`
