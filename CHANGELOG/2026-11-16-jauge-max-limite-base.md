# Jauge : une valeur trop grande est refusée proprement / Gauge: a too large value is rejected cleanly

**Date :** 2026-11-16
**Migration :** Non
**Sentry :** BILLETTERIE-COOP-VZ (`DataError: smallint out of range` sur `/event/wizard/event/`)

## Resume / Summary
**Quoi / What :**
- `Event.JAUGE_MAXIMALE_POSSIBLE = 32767` : la plus grande jauge que la base peut stocker (`jauge_max` est un `smallint` PostgreSQL).
- L'assistant de création d'évènement (`WizardEventSerializer`) refuse une jauge plus grande, avec le message « La jauge ne peut pas dépasser 32767 places. ». Le champ HTML porte aussi `max="32767"`.
- Même contrôle dans l'API v2 (`maximumAttendeeCapacity`, qui refuse aussi une valeur négative).
- API v2 : `offers.eligibleQuantity.maxValue` (→ `Event.max_per_user`) et `offers.returnPolicy.merchantReturnDays` (→ `Event.refund_deadline`) vont aussi dans des colonnes `smallint` positif. Hors de 0..32767, ils renvoient maintenant une erreur 400 sur `offers` au lieu d'une 500.
- Schéma OpenAPI : `minimum: 0` et `maximum: 32767` sur ces trois champs.
- `EventQuickCreateSerializer` est **mis en commentaire** (code mort) : aucune vue ne l'utilise depuis le remplacement de l'offcanvas par l'assistant unifié (commit `509d1e22`, 2026-05-19). Ses deux imports exclusifs (`typing`, `admin_clean_html`) aussi.

/ `Event.JAUGE_MAXIMALE_POSSIBLE = 32767`. The event wizard and API v2 `maximumAttendeeCapacity` reject a bigger gauge with a clear message instead of a 500.

**i18n :** 2 nouvelles chaînes (« La jauge ne peut pas dépasser {max_value} places. » et « %(champ)s doit être un nombre entier entre 0 et %(maximum)s. ») : workflow de traduction à lancer.

**Pourquoi / Why :** une jauge saisie au-delà de 32767 passait la validation et PostgreSQL refusait l'enregistrement : erreur 500, évènement non créé.
/ A gauge above 32767 passed validation and PostgreSQL refused the insert: 500 error.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/models.py` | Constante `Event.JAUGE_MAXIMALE_POSSIBLE` |
| `BaseBillet/validators.py` | `max_value` sur `WizardEventSerializer.jauge_max` ; `EventQuickCreateSerializer` et ses imports exclusifs mis en commentaire (code mort) |
| `api_v2/serializers.py` | `min_value=0`, `max_value` sur `maximumAttendeeCapacity` ; bornes de `offers` dans `EventCreateSerializer.validate()` ; constante `PLUS_GRANDE_VALEUR_D_UN_SMALLINT` |
| `api_v2/openapi-schema.yaml` | `minimum` / `maximum` sur `maximumAttendeeCapacity`, `maxValue`, `merchantReturnDays` |
| `BaseBillet/templates/fonctionnel/event_wizard/_events_inner.html` | `max="32767"` sur le champ jauge |
| `tests/pytest/test_jauge_max_limite_base.py` | 11 tests (nouveau) |

---

## Comment tester (a la main) / Manual test
### Test 1 — assistant, jauge trop grande
1. Ouvrir `/event/wizard/`, choisir un lieu.
2. Remplir un évènement avec une jauge de `40000`. Le navigateur bloque déjà (`max`).
3. Retirer l'attribut `max` dans l'inspecteur, renvoyer : message « La jauge ne peut pas dépasser 32767 places. », pas d'erreur 500.

### Test 2 — limite acceptée
1. Même parcours avec une jauge de `32767` : le brouillon est ajouté, l'évènement se crée.

### Test 3 — API v2
1. `POST /api/v2/events/` avec `"maximumAttendeeCapacity": 40000` → réponse 400 sur ce champ.
2. Même chose avec `-1` → 400.
3. `"offers": {"eligibleQuantity": {"maxValue": 40000}}` → 400 sur `offers`.

### Verifs automatiques
- `docker exec lespass_django poetry run pytest tests/pytest/test_jauge_max_limite_base.py -q`
