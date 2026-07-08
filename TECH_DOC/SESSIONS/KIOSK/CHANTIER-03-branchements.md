# CHANTIER-03 — Branchements (module + sidebar + bridge KI) — Plan

**Goal :** activer le kiosk comme module Groupware et router les terminaux `KI` vers `/kiosk/`.

**Cadre :** fichiers sensibles (Configuration, admin/dashboard, bridge laboutik) — autorisés par le
mainteneur. Additif, non destructif.

## Global Constraints
- Subagents SANS git. Pas de `runserver`/`makemessages`. `docker exec lespass_django poetry run ...`.
- Tests `--api-key dummy`. FALC + i18n `_()` source FR. Skill `unfold` pour le style admin.

## Task 03 — les 4 branchements

**1. Champ `module_kiosk`** (`BaseBillet/models.py`, à côté de `module_tireuse` ~l.627) :
`BooleanField(default=False, ...)` avec `verbose_name`/`help_text` `_()` FR. Migration `makemigrations basebillet` + `migrate_schemas`.

**2. `MODULE_FIELDS`** (`Administration/admin/dashboard.py:800`) : ajouter l'entrée
`"module_kiosk": {"name": _("Kiosk / borne libre-service"), "icon": "storefront"}` (icône Material Symbols).

**3. Section sidebar "Kiosk"** (`Administration/admin/dashboard.py`, `get_sidebar_navigation`, pattern
`module_tireuse` l.488-500) : `if configuration.module_kiosk:` → section avec liens vers les changelists
admin kiosk : `staff_admin:kiosk_terminal_changelist`, `staff_admin:kiosk_stripelocation_changelist`,
`staff_admin:kiosk_paymentsintent_changelist` (via `reverse_lazy`, `permission` = admin_permission).

**4. Bridge KI** (`laboutik/views.py`, `LaBoutikAuthBridgeView`, l.9680) : remplacer le redirect final
en dur par un routage selon `term_user.terminal_role` :
```python
from AuthBillet.models import TibilletUser
if term_user.terminal_role == TibilletUser.ROLE_KIOSQUE:
    return HttpResponseRedirect("/kiosk/?type_app=" + type_app)
return HttpResponseRedirect("/laboutik/caisse?type_app=" + type_app)
```

**Tests** (`tests/pytest/test_kiosk_branchements.py`) :
- `module_kiosk` existe et défaut False.
- Bridge : un `TermUser(terminal_role=KI)` + `LaBoutikAPIKey` liée → POST `/laboutik/auth/bridge/` redirige vers `/kiosk/...` ; un `TermUser` LB → `/laboutik/caisse...`. (S'inspirer d'un test bridge existant si présent ; sinon test ciblé sur la logique.)

## Fin de chantier : review + correction Fable 5 (+ djc en passe finale).
