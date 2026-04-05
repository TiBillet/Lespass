# Phase 0 — Branchement minimal controlvanne dans Lespass

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** L'app controlvanne tourne dans Lespass : les modeles existent en base, l'admin Unfold affiche les tireuses, le WebSocket est branche, la sidebar est conditionnelle sur `module_tireuse`.

**Architecture:** On branche l'app existante telle quelle (avec ses modeles mock Card, Fut, etc.) pour avoir un truc qui tourne. Le refactoring des modeles vers CarteCashless/Product/fedow_core sera fait en Phase 1.

**Tech Stack:** Django 4.x, django-tenants, django-solo, Django Channels, Redis, Unfold admin

**Spec de reference :** `TECH DOC/SESSIONS/CONTROLVANNE/SPEC_CONTROLVANNE.md`

---

## Vue d'ensemble des taches

| Tache | Description | Fichiers principaux |
|-------|-------------|---------------------|
| 1 | Ajouter `module_tireuse` sur Configuration | `BaseBillet/models.py`, migration |
| 2 | Enregistrer controlvanne dans TENANT_APPS | `TiBillet/settings.py` |
| 3 | Brancher les URLs HTTP | `TiBillet/urls_tenants.py` |
| 4 | Brancher le WebSocket dans ASGI | `TiBillet/asgi.py`, `wsocket/routing.py` |
| 5 | Migrer l'admin sur staff_admin_site | `controlvanne/admin.py` |
| 6 | Ajouter la sidebar conditionnelle | `Administration/admin/dashboard.py` |
| 7 | Appliquer les migrations | commandes docker |
| 8 | Test de fumee manuel | verification admin + WebSocket |

---

### Tache 1 : Ajouter `module_tireuse` sur BaseBillet.Configuration

**Fichiers :**
- Modifier : `BaseBillet/models.py` (apres ligne 615, champ `module_inventaire`)
- Creer : migration BaseBillet

- [ ] **Step 1 : Ajouter le champ `module_tireuse`**

Dans `BaseBillet/models.py`, apres le bloc `module_inventaire` (ligne 615-618), ajouter :

```python
    module_tireuse = models.BooleanField(
        default=False,
        verbose_name=_("Connected tap module"),
        help_text=_("Enable connected beer tap management (controlvanne)."),
    )
```

- [ ] **Step 2 : Creer la migration**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations BaseBillet --name add_module_tireuse
```

Attendu : une migration avec `AddField` pour `module_tireuse`.

- [ ] **Step 3 : Verifier**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Attendu : `System check identified no issues.`

---

### Tache 2 : Enregistrer controlvanne dans TENANT_APPS

**Fichiers :**
- Modifier : `TiBillet/settings.py` (ligne 188, dans le tuple TENANT_APPS)

- [ ] **Step 1 : Ajouter controlvanne dans TENANT_APPS**

Dans `TiBillet/settings.py`, ajouter `'controlvanne'` a la fin du tuple `TENANT_APPS` (avant la parenthese fermante ligne 189) :

```python
TENANT_APPS = (
    # The following Django contrib apps must be in TENANT_APPS
    'django.contrib.contenttypes',
    'django.contrib.staticfiles',

    'rest_framework_api_key',
    # your tenant-specific apps
    'BaseBillet',
    'ApiBillet',
    'api_v2',
    'PaiementStripe',
    'wsocket',
    'tibrss',
    'fedow_connect',
    'crowds',
    'laboutik',
    'inventaire',
    'controlvanne',
)
```

- [ ] **Step 2 : Verifier que INSTALLED_APPS se construit correctement**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Attendu : `System check identified no issues.` (ou warnings existants, pas de nouvelle erreur).

---

### Tache 3 : Brancher les URLs HTTP

**Fichiers :**
- Modifier : `TiBillet/urls_tenants.py` (apres la ligne laboutik, ligne 49)

- [ ] **Step 1 : Ajouter l'include controlvanne**

Dans `TiBillet/urls_tenants.py`, ajouter apres la ligne `path('laboutik/', include('laboutik.urls')),` (ligne 49) :

```python
    path('controlvanne/', include('controlvanne.urls')),
```

- [ ] **Step 2 : Verifier la resolution des URLs**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Attendu : pas de nouvelle erreur. Les URLs controlvanne seront accessibles sous `/controlvanne/`.

---

### Tache 4 : Brancher le WebSocket dans ASGI

**Fichiers :**
- Modifier : `TiBillet/asgi.py` (lignes 24 et 35)

- [ ] **Step 1 : Importer les routes WebSocket controlvanne**

Dans `TiBillet/asgi.py`, ajouter l'import apres la ligne 24 (`from wsocket.routing import websocket_urlpatterns`) :

```python
from controlvanne.routing import websocket_urlpatterns as controlvanne_ws_urlpatterns
```

- [ ] **Step 2 : Combiner les routes dans le URLRouter**

Remplacer la ligne 35 :

```python
                AuthMiddlewareStack(URLRouter(websocket_urlpatterns))
```

par :

```python
                AuthMiddlewareStack(URLRouter(websocket_urlpatterns + controlvanne_ws_urlpatterns))
```

- [ ] **Step 3 : Verifier le fichier complet**

Le fichier `TiBillet/asgi.py` doit ressembler a :

```python
"""
Configuration ASGI — HTTP + WebSocket
/ ASGI configuration — HTTP + WebSocket

LOCALISATION : TiBillet/asgi.py

FLUX des connexions WebSocket :
1. AllowedHostsOriginValidator — verifie que l'origine est autorisee
2. WebSocketTenantMiddleware — resout le tenant depuis le hostname, set connection.tenant
3. AuthMiddlewareStack — resout la session Django (scope["user"])
4. URLRouter — route vers le consumer (wsocket/routing.py + controlvanne/routing.py)

FLUX des connexions HTTP :
1. django_asgi_app — traite par le middleware WSGI classique (TenantMainMiddleware inclus)
"""
import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

from wsocket.middlewares import WebSocketTenantMiddleware
from wsocket.routing import websocket_urlpatterns
from controlvanne.routing import websocket_urlpatterns as controlvanne_ws_urlpatterns

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "TiBillet.settings")

django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AllowedHostsOriginValidator(
            WebSocketTenantMiddleware(
                AuthMiddlewareStack(URLRouter(websocket_urlpatterns + controlvanne_ws_urlpatterns))
            )
        ),
    }
)
```

---

### Tache 5 : Migrer l'admin sur staff_admin_site

**Fichiers :**
- Modifier : `controlvanne/admin.py`

L'admin controlvanne utilise `@admin.register(Model)` (site par defaut).
Lespass utilise `staff_admin_site` pour l'admin tenant.

- [ ] **Step 1 : Ajouter l'import de staff_admin_site**

En haut de `controlvanne/admin.py`, ajouter apres les imports existants :

```python
from Administration.admin_tenant import staff_admin_site
from ApiBillet.permissions import TenantAdminPermissionWithRequest
```

- [ ] **Step 2 : Remplacer tous les `@admin.register(Model)` par `@admin.register(Model, site=staff_admin_site)`**

Chaque decorateur `@admin.register(...)` doit devenir `@admin.register(..., site=staff_admin_site)`.

Liste des changements (11 enregistrements) :

```python
@admin.register(Fut, site=staff_admin_site)
class FutAdmin(ModelAdmin):
    ...

@admin.register(HistoriqueFut, site=staff_admin_site)
class HistoriqueFutAdmin(ModelAdmin):
    ...

@admin.register(TireuseBec, site=staff_admin_site)
class TireuseBecAdmin(ModelAdmin):
    ...

@admin.register(Debimetre, site=staff_admin_site)
class DebitmetreAdmin(ModelAdmin):
    ...

@admin.register(Card, site=staff_admin_site)
class CardAdmin(ModelAdmin):
    ...

@admin.register(RfidSession, site=staff_admin_site)
class RfidSessionAdmin(ModelAdmin):
    ...

@admin.register(HistoriqueTireuse, site=staff_admin_site)
class HistoriqueTireuseAdmin(ModelAdmin):
    ...

@admin.register(HistoriqueCarte, site=staff_admin_site)
class HistoriqueCarteAdmin(ModelAdmin):
    ...

@admin.register(CarteMaintenance, site=staff_admin_site)
class CarteMaintenanceAdmin(ModelAdmin):
    ...

@admin.register(HistoriqueMaintenance, site=staff_admin_site)
class HistoriqueMaintenanceAdmin(ModelAdmin):
    ...

@admin.register(SessionCalibration, site=staff_admin_site)
class SessionCalibrationAdmin(ModelAdmin):
    ...

@admin.register(Configuration, site=staff_admin_site)
class ConfigurationAdmin(ModelAdmin):
    ...
```

- [ ] **Step 3 : Ajouter les permissions sur chaque ModelAdmin**

Ajouter ces 4 methodes sur chaque classe ModelAdmin (sauf celles qui ont deja `has_add_permission = False`, etc.) :

```python
    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)
```

Pour les ModelAdmin read-only (`HistoriqueTireuseAdmin`, `HistoriqueCarteAdmin`, `HistoriqueMaintenanceAdmin`, `SessionCalibrationAdmin`) qui ont deja `has_add_permission = False` et `has_change_permission = False`, ajouter uniquement `has_view_permission` et `has_delete_permission` en gardant les methodes existantes.

- [ ] **Step 4 : Verifier**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Attendu : pas d'erreur.

---

### Tache 6 : Ajouter la sidebar conditionnelle "Tireuses"

**Fichiers :**
- Modifier : `Administration/admin/dashboard.py` (apres le bloc `module_inventaire`, vers ligne 337)

- [ ] **Step 1 : Ajouter la section sidebar Tireuses**

Dans `Administration/admin/dashboard.py`, apres le bloc `module_inventaire` (apres la ligne 337 `)`), ajouter :

```python
    # --- module_tireuse : Tireuses connectees ---
    # / --- module_tireuse: Connected beer taps ---
    if configuration.module_tireuse:
        navigation.append(
            {
                "title": _("Tireuses"),
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": _("Taps"),
                        "icon": "local_bar",
                        "link": reverse_lazy(
                            "staff_admin:controlvanne_tireusebec_changelist"
                        ),
                        "permission": admin_permission,
                    },
                    {
                        "title": _("Kegs"),
                        "icon": "liquor",
                        "link": reverse_lazy(
                            "staff_admin:controlvanne_fut_changelist"
                        ),
                        "permission": admin_permission,
                    },
                    {
                        "title": _("Flow meters"),
                        "icon": "speed",
                        "link": reverse_lazy(
                            "staff_admin:controlvanne_debimetre_changelist"
                        ),
                        "permission": admin_permission,
                    },
                    {
                        "title": _("Cards"),
                        "icon": "credit_card",
                        "link": reverse_lazy(
                            "staff_admin:controlvanne_card_changelist"
                        ),
                        "permission": admin_permission,
                    },
                    {
                        "title": _("Maintenance cards"),
                        "icon": "build",
                        "link": reverse_lazy(
                            "staff_admin:controlvanne_cartemaintenance_changelist"
                        ),
                        "permission": admin_permission,
                    },
                    {
                        "title": _("Sessions"),
                        "icon": "history",
                        "link": reverse_lazy(
                            "staff_admin:controlvanne_rfidsession_changelist"
                        ),
                        "permission": admin_permission,
                    },
                    {
                        "title": _("Tap history"),
                        "icon": "timeline",
                        "link": reverse_lazy(
                            "staff_admin:controlvanne_historiquetireuse_changelist"
                        ),
                        "permission": admin_permission,
                    },
                    {
                        "title": _("Card history"),
                        "icon": "manage_search",
                        "link": reverse_lazy(
                            "staff_admin:controlvanne_historiquecarte_changelist"
                        ),
                        "permission": admin_permission,
                    },
                    {
                        "title": _("Maintenance history"),
                        "icon": "plumbing",
                        "link": reverse_lazy(
                            "staff_admin:controlvanne_historiquemaintenance_changelist"
                        ),
                        "permission": admin_permission,
                    },
                    {
                        "title": _("Calibration"),
                        "icon": "tune",
                        "link": reverse_lazy(
                            "staff_admin:controlvanne_sessioncalibration_changelist"
                        ),
                        "permission": admin_permission,
                    },
                    {
                        "title": _("Keg history"),
                        "icon": "swap_vert",
                        "link": reverse_lazy(
                            "staff_admin:controlvanne_historiquefut_changelist"
                        ),
                        "permission": admin_permission,
                    },
                    {
                        "title": _("Server configuration"),
                        "icon": "settings",
                        "link": reverse_lazy(
                            "staff_admin:controlvanne_configuration_changelist"
                        ),
                        "permission": admin_permission,
                    },
                ],
            }
        )
```

- [ ] **Step 2 : Verifier la syntaxe**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Attendu : pas d'erreur. Les `reverse_lazy` seront resolus au runtime — si un nom d'URL est incorrect, ca cassera a l'affichage de la sidebar (pas au check).

---

### Tache 7 : Appliquer les migrations

**Fichiers :** aucun a modifier (commandes uniquement)

- [ ] **Step 1 : Appliquer les migrations sur tous les schemas**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing
```

Attendu : les tables controlvanne sont creees dans chaque schema tenant. La migration BaseBillet ajoute `module_tireuse`. Les migrations controlvanne existantes (0001_initial, 0002_remove_nom_boisson) s'appliquent.

- [ ] **Step 2 : Verifier qu'il n'y a pas de migration manquante**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py showmigrations controlvanne
```

Attendu :
```
controlvanne
 [X] 0001_initial
 [X] 0002_remove_nom_boisson
```

---

### Tache 8 : Test de fumee manuel

**Fichiers :** aucun

- [ ] **Step 1 : Lancer le serveur**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py runserver_plus 0.0.0.0:8002
```

- [ ] **Step 2 : Verifier l'admin**

1. Aller sur l'admin Unfold du tenant (`https://<tenant>/admin/`)
2. Aller dans Parametres (Configuration)
3. Cocher "Connected tap module" et sauvegarder
4. Verifier que la section "Tireuses" apparait dans la sidebar
5. Cliquer sur "Taps" → la liste des TireuseBec doit s'afficher (vide)
6. Creer une TireuseBec de test

- [ ] **Step 3 : Verifier les URLs**

1. Aller sur `https://<tenant>/controlvanne/` → doit afficher le panel (vide, "Aucune tireuse definie")
2. Aller sur `https://<tenant>/controlvanne/api/rfid/ping` → doit repondre `{"status": "pong", "message": "Server online"}`

- [ ] **Step 4 : Verifier le WebSocket**

Ouvrir la console navigateur sur `https://<tenant>/controlvanne/` et verifier :
- Le JS tente de se connecter a `ws://<tenant>/ws/rfid/all/`
- Pas d'erreur 404 sur le WebSocket (la route est resolue)
- Si Redis tourne : connexion etablie (`WS Connecte sur /ws/rfid/all/`)

---

## Resume des fichiers modifies

| Fichier | Changement |
|---------|------------|
| `BaseBillet/models.py` | +1 champ `module_tireuse` sur Configuration |
| `BaseBillet/migrations/XXXX_add_module_tireuse.py` | migration auto-generee |
| `TiBillet/settings.py` | `'controlvanne'` dans TENANT_APPS |
| `TiBillet/urls_tenants.py` | `path('controlvanne/', include('controlvanne.urls'))` |
| `TiBillet/asgi.py` | import + concat des routes WS controlvanne |
| `controlvanne/admin.py` | `staff_admin_site` + permissions sur tous les ModelAdmin |
| `Administration/admin/dashboard.py` | section sidebar "Tireuses" conditionnelle |

Aucun fichier cree (hors migration auto-generee). Aucun fichier supprime.
