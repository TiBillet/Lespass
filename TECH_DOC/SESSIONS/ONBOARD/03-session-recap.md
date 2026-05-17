# Onboard — Récap de session (2026-05-14 / 2026-05-15)

Bilan factuel de la session marathon qui a livré le wizard d'onboarding TiBillet sur la branche `main-wizard`.

**Point de départ** : commit `8d97c945` (Task 1 du plan — scaffold app `onboard/` + register SHARED_APPS).
**Point d'arrivée** : commit `bf062a6a` (wizard complet end-to-end, 22 tasks sur 24).

---

## 1. Vue d'ensemble

| Métrique | Valeur |
|---|---|
| Tasks complétées | 22 / 24 (Tasks 23 E2E et 24 CHANGELOG reportées) |
| Tests pytest | **52 passing / 2 skipped** (~3min total) |
| Fichiers créés | ~25 (modèles, vues, serializers, services, tasks Celery, templates, statics, tests) |
| Lignes de code | ~3500 LoC Python + ~1500 LoC templates + ~300 LoC CSS/JS |
| Modèles modifiés | `MetaBillet.WaitingConfiguration` (étendu) + nouveau `onboard.OnboardInvitation` |
| Migrations | 4 (MetaBillet 0013, 0014, 0015, 0016) + onboard 0001 |
| Skill ratings | djc ✅ / UI ✅ / UX ✅ / a11y ✅ |

---

## 2. Architecture livrée

### Backend
- **`onboard.OnboardInvitation`** : modèle SHARED_APPS pour les codes d'invitation parrainés.
- **`MetaBillet.WaitingConfiguration`** : étendu avec 14 champs wizard (identity, place, OTP, current_step, etc.).
- **`OnboardViewSet(viewsets.ViewSet)`** : 13 actions explicites (PAS de ModelViewSet, djc compliance).
- **`onboard.serializers`** : 6 serializers DRF (Identity / Verify / Place / Descriptions / EventDraft) — pas de Forms, pas de ModelSerializer.
- **`onboard.services`** : `generate_otp` / `verify_otp` (PBKDF2 via Django hashers, pas bcrypt) + `geocode` (proxy Nominatim avec cache Redis 24h + sentinel "no-result").
- **`onboard.tasks`** : 4 tasks Celery (`onboard_otp_mailer`, `onboard_ready_mailer`, `create_tenant_from_draft`, `purge_stale_onboard_drafts`).
- **`create_empty_tenant`** : management command pour repeupler le pool `WAITING_CONFIG`.
- **Admin Unfold** : `OnboardInvitationAdmin` enregistré sur `staff_admin_site`.

### Frontend
- **`base_wizard.html`** : layout 2 colonnes Bootstrap avec progress panel + content area.
- **6 step templates** (`01_identity` → `06_launch`) avec HTMX, data-testid, aria-live, i18n bilingues.
- **`progress_panel.html`** : étapes done cliquables (navigation libre), capsules numérotées, checkmarks CSS-only.
- **`wizard.css`** (~370 LoC) : variables locales (vert TiBillet), border-radius concentriques (16/10/8), box-shadow 3 couches, dark mode (`[data-bs-theme="dark"]`), reduce-motion, mobile-first.
- **`wizard.js`** : OTP auto-tab + paste handler + sync hidden, slug preview live (slugify FR), carrousel info 5s avec cleanup.
- **Carte Leaflet** : tile provider **CartoDB rastertiles/voyager** (OpenStreetMap renvoyait 403/404), marker draggable, intégration HTMX geocode.

### Infrastructure
- **Celery beat** : `cron_purge_stale_onboard_drafts` (Lundi 3h UTC, pattern `on_after_configure` + wrapper `@app.task` aligné sur `cron_morning`/`cron_refresh_seo_cache`).
- **DRF throttle** : `GeocodeRateThrottle(rate="1/second")` sur `/onboard/geocode/` (politique Nominatim).
- **Tests** : bascule complète vers pattern V2 (pytest-django + `django_db_setup = pass` + fixtures session-scope qui réutilisent la DB dev). Gain : 6+ min → ~3 min pour 52 tests.

---

## 3. Décisions techniques majeures (et leurs raisons)

| # | Décision | Justification |
|---|---|---|
| 1 | **PBKDF2 (Django hashers) au lieu de bcrypt** | bcrypt absent de `pyproject.toml`. PBKDF2 + TTL 10min + lock 5 essais = sécurité équivalente pour OTP 6 chiffres court-vivant. |
| 2 | **Tests via pytest-django + DB dev partagée** | Pattern V2 de `lespass-main`. Évite le setup multi-tenant lourd (6+ min) à chaque test run. Cleanup explicite via fixtures `cleanup_*`. |
| 3 | **`OnboardInvitation.federation` FK commentée** | `fedow_core` absent de `main-wizard` (mergera depuis `integration_laboutik`). TODO clair pour la post-merge. |
| 4 | **Pattern `path()` direct, pas DefaultRouter DRF** | DefaultRouter aurait généré `/onboard/onboard/` à cause de `basename + register("onboard", ...)`. Pattern explicite FALC. |
| 5 | **Claim Redis distribué dans `create_tenant_from_draft`** | `select_for_update` libère le lock dès la sortie de l'atomic — ne couvre PAS l'appel `wc.create_tenant()` (qui dure plusieurs min et fait du DDL non rollback-able). `cache.add(key, "1", timeout=300)` = mutex atomique cross-workers. |
| 6 | **OTP envoyé seulement sur clic explicite (Mod 1)** | Évite envoi auto à chaque visite. Donne le contrôle à l'utilisateur (corriger email avant d'envoyer). |
| 7 | **DEBUG bypass verify (Mod 2)** | Permet dev local sans worker Celery actif. Log warning explicite. Désactivé en prod. |
| 8 | **`get_client_ip` derrière proxy** | `REMOTE_ADDR` brut = IP du proxy Traefik → un seul attaquant bloquerait tous les resends. Utilise le helper `AuthBillet.utils.get_client_ip` (X-Forwarded-For aware). |
| 9 | **Re-enqueue à chaque GET launch (Mod 4)** | Robustesse : si Celery a perdu le message, refresh = retry. Idempotent via claim Redis. |
| 10 | **Polling 5 min max (Mod 5)** | Évite un onglet oublié qui poll pendant des heures. Au-delà, partial `status_timeout.html` avec bouton "Réessayer". |

---

## 4. Bugs trouvés en audit critique + status

### 🟢 Fixés cette session

| # | Bug | Sévérité | Détail |
|---|---|---|---|
| B1 | Race condition `select_for_update` | 🔴 BLOCKER | Double-clic = double tenant. Fixé via claim Redis. |
| B2 | Rate-limit `REMOTE_ADDR` brut | 🔴 BLOCKER | Tous users partagent même bucket derrière proxy. Fixé via `get_client_ip`. |
| Comment Django `{# ... #}` multi-ligne | 🟠 BUG | Le commentaire s'affichait en clair sur 8 templates. Sed batch → `{% comment %}...{% endcomment %}`. |
| Preview domaine `<slug>.<domaine>` strippé | 🟠 BUG | Navigateur strippait les "balises" HTML factices. JS dynamique `setupDomainPreview()` avec slugify. |
| Tile provider OpenStreetMap 403/404 | 🟠 BUG | Hotlink bloqué. Switch CartoDB `rastertiles/voyager`. |
| Tiles `@2x.png` blank | 🟠 BUG | Retina suffixe non supporté par tile. Retrait du `{r}`. |
| OTP copier-coller dans la 1e case | 🟠 BUG | Paste 6 chiffres → distribué sur 1 seule case. Listener `paste` qui split. |
| Inputs contraste insuffisant | 🟠 UX | Borders transparents + shadow trop subtile. Border 1px slate-300 + hover/focus. |
| Dark mode pauvre contraste | 🟠 UX | Inputs invisibles en dark. Palette slate-dark dédiée via `[data-bs-theme="dark"]`. |
| Bouton "Reprendre plus tard" sans action | 🟠 UX | Action non implémentée → trompeur. Retiré. |
| Date event ISO brute | 🟡 NICE | "2026-06-15T19:00:00+02:00" → "2026-06-15 à 19:00". |
| Champ image events | 🟡 FEATURE | Pas d'image possible. Ajouté ImageField + storage `onboard_drafts/<wc>/events/<uuid>.<ext>` + transfert vers `Event.img` à la création tenant + purge orphelins. |
| Description longue obligatoire | 🟡 UX | Forcée. Maintenant `required=False, allow_blank=True`. |
| Description courte ailleurs que logo | 🟡 UX | Étalé sur 2 pages. Fusion : tout sur step "Présentation". |
| `{# ... #}` resume_invalid standalone | 🟡 NICE | Étend `base_wizard.html`. |
| `clearInterval` carrousel manquant | 🟡 NICE | Ajout cleanup `beforeunload` + respect `prefers-reduced-motion`. |
| Magic link sans révocation | 🟠 SHOULD | Si `tenant_id` rempli, redirect launch (pas le wizard). |
| `step in 'verify,place,...'` substring fragile | 🟡 NICE | Comparaisons `or` explicites. |
| Bouton Précédent place → verify peu intuitif | 🟠 SHOULD | Pointe maintenant vers identity (OTP déjà consommé). |
| `{% blocktranslate %}Chiffre {{ i }}` sans `with` | 🟠 SHOULD | a11y screen reader cassé. Fix avec `with position=forloop.counter`. |
| Validation logo absente | 🟠 SHOULD | 5MB max + content_type whitelist (jpeg/png/webp). |
| Pas de back button sur Verify | 🟠 UX | Ajouté → identity. |
| Étapes du progress panel non-cliquables | 🟠 UX | is-done devient `<a>` cliquable couvrant tout le bloc. |

### 🟠 Non fixés (volontairement, hors scope ou nécessitent décisions)

| # | Bug / Question | Pourquoi reporté |
|---|---|---|
| S2 | `wc.create_tenant()` raise si Fedow non configuré | Touche `BaseBillet/validators.py` (zone sensible, hors onboard). À régler dans la fusion V2 quand `fedow_core` arrive. |
| Onglets multiples / sessions concurrentes | Pas vérifié. Plusieurs onglets pourraient pointer vers le même brouillon. | Cas edge, à explorer en E2E (Task 23). |

---

## 5. Tests

### Couverture pytest (52 tests)
- `test_models.py` (2) — OnboardInvitation
- `test_services_otp.py` (6) — generate / verify / edge cases
- `test_services_geocode.py` (5) — proxy Nominatim + cache
- `test_tasks_mailers.py` (3) — OTP mailer + ready mailer
- `test_create_tenant_task.py` (4 + 1 skip federation) — task creation tenant
- `test_purge_task.py` (2) — purge stale
- `test_viewset.py` (2) — root redirect + helpers
- `test_step_identity.py` (3) — identity GET/POST/invitation
- `test_step_verify.py` (5) — OTP correct/wrong/lock/resend + **DEBUG bypass**
- `test_step_place.py` (3) — place POST + geocode endpoint
- `test_step_descriptions.py` (3) — short + long + logo
- `test_step_events.py` (5) — add/remove/finalize + image
- `test_step_launch.py` (7) — page + status progress/done/error + retry + resume
- `test_create_empty_tenant_cmd.py` (2 + 1 skip slow) — management command

### Tests Playwright E2E
**Non écrits** (Task 23 reportée — sera fait avec le mainteneur sur une session dédiée).

---

## 6. Patterns réutilisables pour les futures sessions

### Bascule pytest pattern V2
1. Ajouter `pytest-django` + `pytest-asyncio` dans `pyproject.toml`.
2. Configurer `pytest.ini` avec `DJANGO_SETTINGS_MODULE = TiBillet.settings`.
3. Conftest local de l'app : `django_db_setup = pass` + `_enable_db_access_for_all` + fixtures cleanup function-scope.
4. Cleanup raw SQL pour les Client (cascade M2M cross-schema `BaseBillet_configuration_federated_with` qui crashe en schéma public).

### Multi-tenant + Celery + claim distribué
```python
from django.core.cache import cache

claim_key = f"my_app:claim:{wc_uuid}"
got_claim = cache.add(claim_key, "1", timeout=300)
if not got_claim:
    logger.info("Already being processed, skipping")
    return
try:
    # work...
except Exception:
    cache.delete(claim_key)
    raise
# Pas de cache.delete en happy path — laisser expirer (idempotence guarantee).
```

### djc bonnes pratiques validées
- ViewSet explicite avec méthodes nommées (PAS ModelViewSet).
- Serializer DRF (`serializers.Serializer`, PAS ModelSerializer pour les vues templates).
- `LOCALISATION:` dans docstrings de chaque fichier.
- Commentaires bilingues FR (FALC) / EN one-liner.
- `data-testid` partout, `aria-live="polite"` sur HTMX regions.
- i18n via `gettext_lazy as _` (Python) et `{% translate %}` / `{% blocktranslate %}` (templates).
- Cache keys avec tenant ID quand applicable.
- `schema_context("meta")` sur lectures/écritures WaitingConfiguration.

---

## 7. Session du 2026-05-15 (suite) — Refacto N1 + N3

Session courte de cleanup pendant qu'on est encore proche du code.
Préparation pour s'attaquer aux bloquants prod (F1+F2+F3) plus sereinement.

### N1 — Helpers de session (`onboard/views.py`)

Pattern dupliqué 6× éliminé :
```python
wc = _get_or_none_wc(request)
if wc is None or not wc.email_confirmed:
    return redirect("onboard-identity")
```

Devient (deux helpers explicites — choix FALC plutôt qu'un seul avec paramètre) :
- `_get_confirmed_wc_or_redirect(request)` → 4 vues navigationnelles (place GET/POST, descriptions GET/POST, events finalize, launch GET).
- `_get_confirmed_wc_or_404(request)` → 2 actions HTMX (events_add, events_remove) où un redirect 302 ne marche pas côté client.

Usage : `wc, redirect_response = _get_confirmed_wc_or_redirect(request); if redirect_response: return redirect_response`. Plus verbeux que le pattern original mais source unique de vérité pour la règle d'authentification du wizard.

### N3 — Templatetag `onboard_steps`

Création du module `onboard/templatetags/__init__.py` + `onboard_steps.py`. Deux `simple_tag` :
- `is_step_done(current_step, target_step)` — comparaison via `STEP_ORDER.index()`.
- `is_step_current(current_step, target_step)` — sucre syntaxique cohérent.

Constante `STEP_ORDER = ["identity", "verify", "place", "descriptions", "events", "launch"]` = source unique de vérité (à garder alignée sur `WaitingConfiguration.STEP_*` et `STEP_TO_URL_NAME`).

`progress_panel.html` refactoré : flags pré-calculés en haut du template (`{% is_step_current step 'identity' as identity_current %}` × 6 + `{% is_step_done %}` × 5), plus de chaînes `step == 'X' or step == 'Y' or ...` dans chaque `<li>`. Si on ajoute une étape demain, on touche **uniquement** `STEP_ORDER` + une `<li>`, plus 6 chaînes `or` à maintenir.

### Piège rencontré

Django scanne les `templatetags/` à l'init des apps, **pas à chaud**. La création d'un nouveau dossier `templatetags/` ne déclenche pas la re-collection des tag libraries par `runserver_plus` même avec auto-reload. Symptôme : `TemplateSyntaxError: 'onboard_steps' is not a registered tag library` sur la première requête après modif. Fix : restart manuel du serveur dev. Pytest n'a pas le problème (process neuf à chaque run).

### Tests

- `manage.py check` : 0 issue.
- `pytest onboard/tests/` : **52 passed / 2 skipped** (identique baseline, ~78s).

### Fichiers modifiés / créés

| Fichier | Type | Changement |
|---|---|---|
| `onboard/views.py` | Modifié | +2 helpers, 6 patterns refactorés |
| `onboard/templatetags/__init__.py` | NOUVEAU | (vide, requis par Django) |
| `onboard/templatetags/onboard_steps.py` | NOUVEAU | 2 simple_tags + STEP_ORDER |
| `onboard/templates/onboard/partials/progress_panel.html` | Modifié | Flags pré-calculés en haut, plus de chaînes `or` |

---

## 8. Session du 2026-05-15 (suite étendue) — Polish prod-ready

Session marathon de polish + features manquantes. ~9h de travail. **56 tests onboard passing / 2 skipped** (vs 52 au début).

### 8.1 UI / UX
| Item | Détail |
|---|---|
| Mobile : panneau étapes toujours visible | Suppression du `<details>` toggle dans `base_wizard.html`. CSS responsive : hints masqués sur mobile, padding réduit. |
| CGU : checkbox → switch Bootstrap 5 | `form-check form-switch` + `role="switch"` + lien `target_blank` vers la doc CGU/CGV |
| Domaine : select → boutons radios | Pattern Bootstrap `btn-check` × 2 (`tibillet.coop` / `tibillet.re`). Retrait `tibillet.fr` du serializer (`DNS_CHOICES`). JS adapté pour lire le radio coché. |
| Desktop : helper aligné au bouton Continuer | CSS flex column sur `.onboard-panel-wrapper` + `flex: 1` sur `.onboard-panel` |
| Step 1 : retrait du h1 dupliqué | Le titre "Créer votre espace TiBillet" était déjà dans l'eyebrow gauche. Test `b"Cr"` mis à jour vers `data-testid="onboard-identity-form"`. |
| Vouvoiement | Audit complet 8 fichiers : tous les `tu/ton/ta/tes` corrigés en `vous/votre/vos`. Bonus : "marker" → "marqueur". |

### 8.2 OTP refacto (annule Mod 1)
- **Décision inverse de Mod 1** : OTP envoyé automatiquement par `identity` POST (au lieu d'un clic explicite). UX standard Slack/Linear/Stripe.
- Helper centralisé `_generate_and_send_otp_for_wc(wc, is_resend=False)` réutilisé par `identity` POST + `resend_otp` action.
- Champ ajouté : `WaitingConfiguration.otp_sent_at` (DateTimeField nullable). Migration `MetaBillet 0014`.
- **Cooldown 60s** côté serveur : `resend_otp` rejette en 429 + partial `resend_cooldown.html` si `now - otp_sent_at < 60s`.
- **Timer JS** sur le bouton "Renvoyer le code" : décompte visuel "(60s)" → "(59s)" → ... avec icône `bi-hourglass-split`. Réagit à `htmx:afterRequest` (200 OU 429).
- Template `02_verify.html` simplifié : plus de branche `has_pending_otp` (label fixe "Renvoyer le code", message fixe "Un code à 6 chiffres a été envoyé à `<email>`").

### 8.3 Locale Nominatim FR
- `onboard/services.py::geocode` : ajout du param `accept-language=<lang>` (lit `get_language()` Django, fallback `"fr"`).
- Helper `_resoudre_langue_utilisateur(lang_explicite=None)` (FALC : split région).
- Cache key inclut maintenant la langue (évite collisions FR vs EN sur même query).

### 8.4 Widget carte adresse réutilisable (full client)
- **Spec + plan + implémentation** : voir `TECH_DOC/SESSIONS/WIDGET_GEO/01-design-spec.md` + `02-implementation-plan.md`.
- 3 fichiers nouveaux dans `templates/widgets/`, `static/widgets/` (`.html` + `.css` + `.js` vanilla IIFE).
- Helper validation : `BaseBillet/form_fields.py::AdresseGeolocaliseeField.extraire_depuis()`.
- Refonte step 03_place : utilise `{% include "widgets/widget_carte_adresse.html" with identifiant_widget="place" %}`. Suppression `map_widget.html`, `geocode_result.html`, action `geocode` + URL.
- **Architecture revert** : initialement spec validée en "Hybride" (search client + reverse via endpoint serveur). Bascule en **full client** après découverte d'un problème multi-tenant routing (route `BaseBillet/urls.py` pas dans `urls_public.py` → 404 sur ROOT). Suppression de `views_widgets.py` + `services_geocode.py` + 2 fichiers de tests. Trade-off : pas de cache mutualisé serveur, OK pour notre volume.
- Settings.py : `BASE_DIR / "templates"` ajouté à `TEMPLATES[0]['DIRS']`, `BASE_DIR / "static"` ajouté à `STATICFILES_DIRS`.

### 8.5 Validation unicité nom tenant (les 2 niveaux)
- **Step 1 (identity)** : `OnboardIdentitySerializer.validate_name` enrichi → `Client.objects.filter(name__iexact=...).exists()` dans `schema_context("public")`. UX : l'utilisateur apprend dès la step 1 que le nom est pris.
- **Step 6 (launch async)** : déjà couvert par `BaseBillet/validators.py::TenantCreateValidator.create_tenant` (ligne 952). Ajout de 2 tests régression pour assurer le no-regression.
- Tests :
  - `test_identity_post_existing_tenant_name_returns_422` : POST avec "LESPASS" (case différent du tenant existant `lespass`) → 422 + erreur sur `name`.
  - `test_create_tenant_from_draft_writes_error_when_name_taken_async` : race condition simulée → `wc.error_message` rempli.

### 8.6 Bug fixé : events_draft datetime string
- **Symptôme** : event saisi step 5 → tenant créé OK → 0 events dans le tenant admin.
- **Cause** : `events_draft` est un JSONField → `datetime` stocké en string ISO 8601. `Event.objects.create(datetime="...")` ne convertit PAS la string. `Event.save()` plante avec `'str' object has no attribute 'astimezone'` quand le post_save signal génère le slug. Le `try/except Exception` swallow l'erreur silencieusement.
- **Fix** : `datetime.fromisoformat(ev_datetime_brut)` AVANT `Event.objects.create(datetime=ev_datetime, ...)`.
- **Test** : `test_create_tenant_from_draft_creates_events_from_drafts_with_iso_datetime`.

### 8.7 Visibilité warnings creation events
- Champ ajouté : `WaitingConfiguration.events_creation_warnings` (TextField). Migration `MetaBillet 0015`.
- `onboard/tasks.py` : `logger.warning` → `logger.error` + inclut le contenu du draft dans le log + accumule dans `wc.events_creation_warnings`.
- `status_done.html` : alert orange sous le success message si warnings non-vides, avec liste des events skipped + suggestion de les recréer manuellement dans l'admin.
- Test : `test_create_tenant_from_draft_accumulates_warnings_for_broken_drafts` (1 valide + 1 cassé `datetime="not-a-date"`).

### 8.8 Fix overflow status_error
- `status_error.html` : ajout `white-space: pre-wrap; word-break: break-word; overflow-wrap: anywhere; max-height: 200px; overflow-y: auto` sur le `<pre>` qui affiche `wc.error_message`. Évite le débordement horizontal sur tracebacks longs.

### 8.9 Refacto N1 + N3 (cf. session précédente même jour)
Voir section 7 ci-dessus — déjà documenté.

### 8.10 Pièges découverts (à capitaliser)

| # | Piège | Détail |
|---|---|---|
| P1 | Conftest `tests/pytest/` exige `API_KEY=dummy` env var | Sinon `docker exec` interne échoue. Pour tests qui n'utilisent pas l'API : `docker exec -e API_KEY=dummy lespass_django bash -c "cd /DjangoFiles && poetry run python -m pytest ..."` |
| P2 | `django.test.Client(HTTP_HOST=...)` triggers django-tenants middleware DB lookup | Erreur "Database access not allowed" → utiliser `APIRequestFactory` pour les tests d'endpoint pure DRF |
| P3 | Django ne re-scanne pas les `templatetags/` ni les routes URL à chaud | Restart `runserver_plus` requis après ajout d'un nouveau templatetag ou d'une nouvelle URL |
| P4 | `Client.save()` (django-tenants) échoue hors du schema `public` | `_make_pool_slot` doit faire `with schema_context("public"): slot.save()` pour rester robuste après un test qui a posé un schema tenant |
| P5 | Browser bloque les fetch POST avec X-CSRFToken via `claude-in-chrome.javascript_tool` | Sécurité MCP. Tester l'endpoint avec curl côté serveur, ou simuler le flow via JS sans CSRF |
| P6 | URLs `BaseBillet/urls.py` ne sont accessibles QUE sur tenants (`urls_tenants.py`), pas ROOT (`urls_public.py`) | Si une feature doit être accessible sur ROOT (cas wizard onboard), ajouter explicitement la route dans `urls_public.py` OU mettre le ViewSet ailleurs. Cf. revert architecture widget. |
| P7 | `events_draft` JSONField stocke datetime en string ISO | `Event.objects.create(datetime="...")` ne convertit pas. Toujours `datetime.fromisoformat(...)` avant. |
| P8 | leaflet-geosearch crée 2 instances `.leaflet-control-geosearch` (1 placeholder invisible + 1 visible) | Normal, pas un bug. La navbar TiBillet a son propre input search vers `/explorer/` qui peut être visuellement confondu avec la search bar du widget. |

### 8.11 Métriques session

| Métrique | Avant | Après |
|---|---|---|
| Tests pytest onboard | 52 / 2 skipped | **56 / 2 skipped** |
| Tests pytest widget | 0 | 6 (form_field) — les 9 tests endpoint+service supprimés au revert architecture |
| Migrations | onboard 0001 + MetaBillet 0013 | + MetaBillet 0014 (otp_sent_at) + MetaBillet 0015 (events_creation_warnings) |
| Fichiers créés/modifiés | (cf. CHANGELOG.md) | ~30 |
| Bugs UX résolus | n/a | 12+ (overflow, OTP friction, mobile toggle, vouvoiement, etc.) |

---

## 9. Session du 2026-05-16 — Cleanup legacy + migration Stripe

Session de cleanup approfondi : suppression complète du flow legacy
`/tenant/new/` (remplacé par l'app `onboard/`), migration des 2 méthodes
Stripe Connect du tenant existant vers l'app dédiée `PaiementStripe/`,
et migration de l'admin Unfold `WaitingConfigAdmin` dans `onboard/admin.py`.

### 9.1 Audit préalable

Avant toute suppression : audit exhaustif via subagent Explore pour
identifier TOUT ce qui touche au flow legacy. Listing organisé en 11
sections (A–K) couvrant routes, vues, templates, tasks, admin,
management commands, signaux, tests, liens templates, modèles, validators.
Sortie : matrice "uniquement legacy / partagé / uniquement onboard /
ailleurs" pour chaque élément. Cette étape a évité 2 régressions :
- Le `Tenant` ViewSet contenait DEUX responsabilités disjointes : création
  tenant (legacy) + onboarding Stripe d'un tenant existant. Ne pas
  supprimer la classe entière en bloc.
- `send_to_ghost_email` task est utilisée AILLEURS que dans le flow
  legacy (inscription user normale) : à garder.

### 9.2 Migration Stripe `_from_config` → `PaiementStripe/`

| Avant | Après |
|---|---|
| `BaseBillet/views.py::Tenant.onboard_stripe_from_config()` | `PaiementStripe/views.py::StripeConnectOnboardingViewSet.onboard_from_config()` |
| `BaseBillet/views.py::Tenant.onboard_stripe_return_from_config()` | `PaiementStripe/views.py::StripeConnectOnboardingViewSet.onboard_return_from_config()` |
| URL `/tenant/onboard_stripe_from_config` | URL `/stripe/onboard/from_config/` |
| URL `/tenant/<id>/onboard_stripe_return_from_config/` | URL `/stripe/onboard/return_from_config/<id>/` |
| Template `reunion/views/tenant/after_onboard_stripe.html` | `PaiementStripe/templates/paiementstripe/after_onboard_stripe.html` |

URL branchée dans `TiBillet/urls_tenants.py` : `path('stripe/', include('PaiementStripe.urls'))`.

Mises à jour des références :
- `Administration/templates/admin/product/checkstripe_component.html:15`
  → `<a href="/stripe/onboard/from_config/">` (avant : `/tenant/onboard_stripe_from_config`).
- `BaseBillet/models.py::Configuration.onboard_stripe()` (ligne 757)
  → `https://{tenant_url}/stripe/onboard/from_config/`.

Spec du chantier futur (refacto large multi-providers, etc.) :
[`../MOYENS_PAIEMENT/01-stripe-migration-spec.md`](../MOYENS_PAIEMENT/01-stripe-migration-spec.md).

### 9.3 Migration `WaitingConfigAdmin` → `onboard/admin.py`

Déplacement complet de la classe `WaitingConfigAdmin` depuis
`Administration/admin_tenant.py:3402-3469` vers `onboard/admin.py` (à
côté de `OnboardInvitationAdmin` existant). Conservation de l'action
custom `create_tenant` (filet de sécurité : permet à un ROOT admin de
finaliser manuellement un brouillon bloqué).

Permissions inchangées : `RootPermissionWithRequest` (les `WaitingConfiguration`
vivent dans le schema `meta` partagé et contiennent des données
sensibles — OTP hashes, emails).

### 9.4 Suppressions

**Vues (`BaseBillet/views.py`)** :
- Classe `Tenant(viewsets.ViewSet)` entière (lignes 3623-3913, ~290 lignes).
  Contenait : `new`, `create_waiting_configuration`, `emailconfirmation_tenant`,
  `onboard_stripe`, `onboard_stripe_return`, `onboard_stripe_from_config`,
  `onboard_stripe_return_from_config`.
- Import correspondant retiré dans `BaseBillet/urls.py:14`
  (`router.register(r'tenant', base_view.Tenant)`).
- Import `new_tenant_mailer` et `new_tenant_after_stripe_mailer` retiré
  de l'import block de `BaseBillet/views.py:53`.

**Tasks Celery (`BaseBillet/tasks.py`)** :
- `new_tenant_mailer` (envoyait le magic-link de confirmation tenant).
- `new_tenant_after_stripe_mailer` (notifiait les superadmins post-Stripe
  onboarding).

**Validators (`BaseBillet/validators.py`)** :
- Partie `Serializer` de `TenantCreateValidator` (champs email,
  emailConfirmation, name, cgu, dns_choice, short_description, captcha
  x/y/answer + méthodes `validate_*`). La classe est désormais un simple
  conteneur pour la staticmethod `create_tenant()`, **toujours appelée**
  par `WaitingConfiguration.create_tenant()` → `onboard.tasks.create_tenant_from_draft`
  et `onboard.admin.WaitingConfigAdmin.create_tenant`.

**Templates** :
- Dossier complet `BaseBillet/templates/reunion/views/tenant/` :
  `new_tenant.html`, `create_waiting_configuration_THANKS.html`,
  `create_waiting_configuration_MAIL_CONFIRMED.html`,
  `after_onboard_stripe.html`, et `emails/welcome_email.html`,
  `emails/after_onboard_stripe_for_superadmin.html`, `emails/onboard_stripe.html`.
- Dossier complet `BaseBillet/templates/htmx/views/tenant/`
  (`new.html`, `onboard_stripe_return.html`).
- `BaseBillet/templates/htmx/forms/tenant_areas.html` + `_informations.html` + `_summary.html`
  (prototype HTMX 3-step jamais routé).
- `BaseBillet/templates/htmx/views/create_tenant.html` (parent du
  prototype HTMX, pointait vers les routes mortes `/tenant/areas/` etc.).
- `ApiBillet/templates/mails/creation_tenant.html` (vestige HTML 2015,
  non utilisé).

### 9.5 Audit final liens résiduels

`grep -rn '/tenant/'` après cleanup : **0 lien actif résiduel** dans les
templates / JS / Python. Les seules occurrences restantes sont des
commentaires/docstrings explicatifs documentant la migration (avec
référence à cette session et au chantier MOYENS_PAIEMENT).

### 9.6 À conserver (volontairement)

- `WaitingConfiguration` model (utilisé par `onboard/`).
- `TenantCreateValidator.create_tenant()` staticmethod (chaîne provisioning
  tenant, partagée entre onboard et l'admin manuel).
- `create_empty_tenant` management command (pool replenishment via cron
  hebdomadaire).
- `batch_new_tenant` management command (création batch CSV, indépendante).
- `send_to_ghost_email` task (utilisée aussi par inscription user normale).
- Champs orphelins de `WaitingConfiguration` (`id_acc_connect`,
  `laboutik_wanted`, `payment_wanted`, `site_web`, `twitter`, `facebook`,
  `instagram`, `map_img`, `carte_restaurant`, `img`, `fuseau_horaire`,
  `legal_documents`, `onboard_stripe_finished`) : laissés en place pour ne
  pas casser une éventuelle migration data ultérieure. Pourront être
  supprimés dans une migration dédiée.

### 9.7 Tests

- `manage.py check` : 0 issue.
- `pytest onboard/tests/` : **58 passed / 2 skipped** (baseline conservée).
- Aucun test pytest sur le flow legacy `/tenant/new/` (audit confirmé).

### 9.8 Fichiers modifiés / supprimés

| Action | Fichier |
|---|---|
| Créé | `PaiementStripe/templates/paiementstripe/after_onboard_stripe.html` |
| Modifié | `PaiementStripe/views.py` (+ `StripeConnectOnboardingViewSet`) |
| Modifié | `PaiementStripe/urls.py` (peuplé, branché) |
| Modifié | `TiBillet/urls_tenants.py` (+ include PaiementStripe) |
| Modifié | `Administration/templates/admin/product/checkstripe_component.html` |
| Modifié | `BaseBillet/models.py` (URL Stripe dans onboard_stripe()) |
| Modifié | `onboard/admin.py` (+ WaitingConfigAdmin migré) |
| Modifié | `Administration/admin_tenant.py` (suppression WaitingConfigAdmin) |
| Modifié | `BaseBillet/views.py` (suppression classe Tenant + import) |
| Modifié | `BaseBillet/urls.py` (suppression router.register tenant) |
| Modifié | `BaseBillet/tasks.py` (suppression 2 tasks legacy) |
| Modifié | `BaseBillet/validators.py` (slim TenantCreateValidator) |
| Créé | `TECH_DOC/SESSIONS/MOYENS_PAIEMENT/01-stripe-migration-spec.md` |
| Supprimé | `BaseBillet/templates/reunion/views/tenant/` (dossier complet) |
| Supprimé | `BaseBillet/templates/htmx/views/tenant/` (dossier complet) |
| Supprimé | `BaseBillet/templates/htmx/views/create_tenant.html` |
| Supprimé | `BaseBillet/templates/htmx/forms/tenant_areas.html` |
| Supprimé | `BaseBillet/templates/htmx/forms/tenant_informations.html` |
| Supprimé | `BaseBillet/templates/htmx/forms/tenant_summary.html` |
| Supprimé | `ApiBillet/templates/mails/creation_tenant.html` |

### 9.9 Audit critique post-cleanup + fixes

Apres le cleanup, audit de TOUT le code ecrit lors de la session
(verifications de bugs potentiels). 9 points identifies, 3 critiques
+ 1 moyen fixes immediatement.

**Fixes appliques (cf. `onboard/tasks.py`)** :

| BUG | Severite | Fix |
|---|---|---|
| #3 — PostalAddress crash propageait dans Celery autoretry → adresse jamais creee (idempotence early-return) | 🔴 CRITIQUE | `try/except` autour du bloc PostalAddress + `logger.error(exc_info=True)` (Sentry alerte). Admin doit creer manuellement si echec. |
| #4 — Claim Redis pas libere apres succes (5min) → `launch_retry` semblait sans effet | 🟠 MOYEN | `cache.delete(claim_key)` en fin de fonction succes. Idempotence reste assuree par `wc.tenant_id is not None` au debut. |
| #5 — `from django.db import transaction` jamais utilise | 🟡 FAIBLE | Import retire. |

**Points NON-fixes (audit confirme = pas un bug)** :

| Point | Verdict |
|---|---|
| SSO cross-tenant (lien tenant -> tenant) | Pattern OK pour usage futur cross-tenant. L'user finit bien loggue sur ROOT via 2 redirects (consume + re-generate sur tenant). |
| Primary domain garanti | `BaseBillet/validators.py:969-973` cree le Domain avec `is_primary=True`. `tenant.get_primary_domain()` ne peut pas retourner None apres `create_tenant()`. |
| User admin sur son tenant | `validators.py:990-994` fait `user.client_admin.add(tenant)` + `is_staff=True`. Magic-link logue correctement. |
| `email_valid=False` + loggue | Toutes les voies (`activate`, `_finalize_otp_success`) forcent email_valid=True. Cas pathologique tres rare. |
| `_finalize_otp_success` ne refresh pas `wc` | Pas d'impact : on retourne `user`, l'appelant fait `redirect()` immediat. |

### 9.10 Champs orphelins commentes

Sur demande mainteneur : ajout de blocs `# LEGACY 2026-05-16 — ...` sur
chaque champ orphelin de `MetaBillet.WaitingConfiguration`. Permet une
suppression propre via migration data future sans repasser par un audit.

Champs commentes :
- `id_acc_connect` (Stripe Connect ID, jadis rempli par Tenant.onboard_stripe)
- `laboutik_wanted`, `payment_wanted` (flags formulaire legacy)
- `site_web`, `legal_documents`, `twitter`, `facebook`, `instagram`
- `map_img`, `carte_restaurant`, `img` (images jamais uploadees)
- `fuseau_horaire`
- `onboard_stripe_finished`

Tous ces champs sont nullable / blank ou ont un default → la migration
data future pourra les retirer sans risque (sauf si du code accede a ces
champs ailleurs — `grep -rn` confirme : aucun acces actif).

### 9.11 Widget carte adresse — CSS final

Apres audit visuel + retours mainteneur sur le rendu, refonte du CSS
de `.leaflet-control-geosearch.leaflet-geosearch-bar` :

| Avant | Apres |
|---|---|
| Double encadrement (container + border interne input) | Un seul encadrement (container avec shadow) — input et bouton sans border |
| `width: 400px` (force par leaflet-geosearch) | `width: fit-content` + `min-width: 16rem` |
| `padding: 0.25rem` interne, gap entre input/bouton | `padding: 0` + `gap: 0` — input et bouton remplissent le container |
| Input + bouton de tailles differentes (30px vs 40px) | Aligne (40.79px tous les deux) via `height: auto !important` + `line-height: 1.5` |
| Bouton submit avec `border-radius: 0.5rem` independant | `border-radius: 0` — coins clippes par `overflow: hidden` du parent |
| Focus input : border verte | Focus input : `box-shadow: inset 0 0 0 2px #16a34a` (visuel propre sans border) |

Resultat visuel : container blanc compact, ombre douce, input gris clair
sans bord interne, bouton vert plein colle au bord droit. Plus de double
border, plus de zone blanche vide.

**Pieges decouverts** (ajoutes a `tests/PIEGES.md` section "Widget carte
adresse + leaflet-geosearch") :
- P.WIDGET.1 — `<form>` HTML5 imbrique cause boucle infinie au submit
- P.WIDGET.2 — Double instance `.leaflet-control-geosearch.pending` decale le zoom
- P.WIDGET.3 — Bouton `.reset` (×) en position absolute chevauche tout
- P.WIDGET.4 — `autoComplete: true` viole la politique Nominatim

---

## 10. Session du 2026-05-17 — Hotfix prod + polish landing + fix wizard

Session marathon avant push prod. **6 axes en parallèle**, tous bloquants ou
dégradants UX. Audit critique final : SAFE TO SHIP.

### 10.1 Hotfix prod : PostalAddress overflow longitude (Sentry #7486299113)

**Symptôme** : `DataError: numeric field overflow` sur création tenant pour
Xai (Pékin), longitude `116.364992`.

**Cause** : `PostalAddress.latitude/longitude` définis `DecimalField(max_digits=18, decimal_places=16)`.
18 - 16 = 2 chiffres avant la virgule, donc max ±99.99... → **toute longitude
hors [-99, +99] casse** (Asie, Pacifique, Amériques).

**Fix** : `DecimalField(max_digits=9, decimal_places=6)` (précision ~11 cm,
range ±999, cohérent avec `WaitingConfiguration.latitude/longitude` existant).
Migration `BaseBillet/0207_fix_postaladdress_latlng_precision.py`. Pas de perte
de données (toutes les valeurs déjà stockées tiennent forcément dans 9/6).

### 10.2 Réécriture mails OTP + ready

**Contexte** : `welcome_email.html` legacy (`/tenant/new/` flow supprimé
2026-05-16) avait un wording riche jamais réutilisé. Les mails `ready.html`
et `otp_code.html` du wizard étaient minimalistes ("Hello, your code is X").

**Fix `ready.html`** : reprise du wording chaleureux (super méga trop ravis,
liste "Informations importantes" avec URL publique + Stripe + canaux support,
liste "Voici ce que vous pouvez faire avec TiBillet", CTA documentation,
signature équipe coopérative). Adapté au contexte post-création : bouton
"ACCÉDER À MON ESPACE" (magic-link admin) au lieu de "CONFIRMER MA DEMANDE".

**Fix `otp_code.html`** : style aligné sur ready (table imbriquée, palette
`#009058`, Arial, eyebrow "Bienvenue dans la communauté TiBillet"). Capsule
vert clair encadrée avec code PIN en `Courier New 36px` letter-spacing 12px
(lisibilité mobile + copier-coller facile).

**Nouveau context var `instance_url`** dans `onboard_ready_mailer` : URL
publique du tenant (sans `/admin/`) affichée dans la liste "Informations
importantes".

### 10.3 Bug 1 : long_description + logo non transférés au tenant

**Symptôme** : utilisateur saisit description longue + upload logo dans le
wizard, mais après création du tenant, la `Configuration.long_description`
contient le texte par défaut "Bienvenue dans votre nouvel espace..." et
`Configuration.img` est vide.

**Cause** : `wc.create_tenant()` (chaîne BaseBillet legacy) ne copie PAS ces
champs (ils n'existaient pas dans `/tenant/new/`).

**Fix** : nouveau bloc "3ter" dans `create_tenant_from_draft` après le bloc
PostalAddress. Override `Configuration.long_description` avec `wc.long_description`
+ copie `wc.logo` (StdImageField sur `media/onboard_drafts/<wc_uuid>/`) vers
`Configuration.img` via `default_storage.open()` + `config.img.save()`
(régénère les variations StdImage). `try/except` sans re-raise (piège #23
idempotence Celery).

### 10.4 Bug 2 : first_name / last_name non répercutés sur le TibilletUser

**Symptôme** : user créé via `get_or_create_user(wc.email)` arrive sans
prénom ni nom dans son profil admin, alors qu'ils ont été saisis step 1.

**Fix** : dans `_finalize_otp_success`, après get_or_create_user + activation,
report `wc.first_name` → `user.first_name` et `wc.last_name` → `user.last_name`
SI le user n'a pas déjà ces champs (ne pas écraser un user existant qui
aurait personnalisé son profil).

### 10.5 Bug 3 : sujet mails OTP + ready en anglais non traduit

**Symptôme** : sujet mail OTP "%(code)s – your TiBillet verification code"
toujours en anglais, même pour un user FR.

**Cause** : workers Celery n'ont pas de `LocaleMiddleware`, donc `gettext`
tombe sur `settings.LANGUAGE_CODE` (`'en'` dans ce projet) au lieu de la
locale UI choisie par le user.

**Fix structurel** :
1. Nouveau champ `WaitingConfiguration.language` (CharField max 10).
   Migration `MetaBillet/0016_add_wc_language.py`.
2. POST identity capture `get_language()` → `wc.language`.
3. Mailers wrappent le rendu (subject + templates `.txt` / `.html`) dans
   `with translation.override(wc.language or "fr")`.

### 10.6 Bug 4 : retour formulaire 1 après OTP avec prénom/nom vides

**Symptôme** : après saisie OTP correcte, redirect vers step 1 (identity)
avec email pré-rempli mais prénom/nom vides — l'utilisateur croit avoir
perdu sa saisie.

**Cause** : `login()` dans `_finalize_otp_success` perd la clé
`onboard_wc_uuid` de la session (probablement `SESSION_SAVE_EVERY_REQUEST=True`
+ `cycle_key()` qui se marchent dessus côté backend session DB). Cascade :
1. POST verify OK → `login(request, user)` → **`onboard_wc_uuid` perdu**
2. Redirect `onboard-place` → `_get_or_none_wc()` retourne None → redirect
   `onboard-identity`
3. GET identity branche "Priorité 2" (user authentifié + pas de wc) →
   pré-remplit email depuis `request.user.email` mais first_name/last_name
   vides (user fraîchement créé n'a jamais ces champs).

**Fix défensif** : ré-écrire `_set_session_wc(request, wc)` après le
`login()`. No-op si la session a survécu, restaure le pointeur sinon.

### 10.7 Bug 5 : polling infini après status_error

**Symptôme** : page `/onboard/launch/` affichait bien le `status_error.html`
mais le polling continuait à tourner toutes les 2s indéfiniment.

**Cause** : double-couche de polling. Le parent `#status` portait
`hx-trigger="load, every 2s"` ET le partial enfant `status_progress.html`
portait aussi `hx-trigger="every 2s"`. Comme `hx-swap="innerHTML"` ne touche
PAS les attributs du parent, le polling parent continuait même quand le
partial swapped n'en avait plus.

**Fix** : retrait de `hx-get`, `hx-trigger`, `hx-swap` du parent `#status`.
Le polling est désormais entièrement piloté par le partial enfant
(`status_progress.html` inclus initialement en server-side via `{% include %}`).
Quand on swap vers `status_done`/`status_error`/`status_timeout` (sans
trigger), polling stop net.

### 10.8 Landing root : 4 nouvelles features + section roadmap

**Ajouts** dans la grille `features-grid` :
- **Données ouvertes** (`bi-database`) : API + schema.org / JSON-LD + licence ouverte
- **Logiciel libre AGPLv3** (`bi-code-slash`) : commun numérique, Coopérative Code Commun
- **Agenda participatif** (`bi-people`) : formulaire ouvert + fédération
- **Référencement et SEO** (`bi-search`) : JSON-LD + sitemap + métadonnées

**Nouvelle section roadmap** (accordéon `<details>` HTML5 natif, zéro JS) :
- Newsletter intégrée (`bi-envelope-paper`)
- Réseaux sociaux unifiés (`bi-megaphone`) avec lien Postiz
- Fédiverse et Mobilizon (`bi-globe2`)
- Économie en cascade (`bi-droplet-half`) avec lien cascade.coop
- CTA contrib vers `codecommun.tibillet.coop/contrib`

**CSS** : nouvelle section ROADMAP/FUTURE (~85 lignes), palette orange pour
icônes "futur" (vs vert pour features actuelles), chevron rotate sur
`details[open]`, `prefers-reduced-motion` respecté.

**Philo réécrite** : Coopérative Code Commun + travaux d'Elinor Ostrom
(ressource partagée + communauté vivante + gouvernance organisée). Wording
piochée dans Atomic (README V2 TiBillet, charte Code Commun).

### 10.9 SEO audit landing (3 fix critique/warning/opportunity)

- **Hiérarchie headings roadmap** : ajout `<h2 class="visually-hidden">`
  avant `<details>` (le `<summary>` est rôle `button`, pas heading → bots
  voyaient des `<h3>` orphelins après `<h2>` features)
- **`og:locale` manquant** : ajout `<meta property="og:locale" content="...">`
  avec mapping FR/EN (Facebook/LinkedIn servent maintenant la bonne variante
  régionale)
- **JSON-LD WebSite + SearchAction** : nouveau bloc qui pointe sur
  `/explorer/?q={search_term_string}` → éligible au **sitelinks searchbox**
  Google (zone de recherche directement dans les SERP)

**Hors scope** : `hreflang` non applicable (pas de `i18n_patterns`, toutes
les langues servent le même chemin).

### 10.10 Diagnostic pool WAITING_CONFIG

**Symptôme** : `relation "BaseBillet_configuration" does not exist` au moment
du `wc.create_tenant()`.

**Cause** : 4 slots du pool étaient à 0 tables (`CREATE SCHEMA` réussi mais
`migrate_schemas` jamais appliqué). Origine : `cron_morning` (Administration/management/commands/cron_morning.py)
fait `create_waiting_tenant()` puis `run_waiting_migrations()`. Si une
migration échoue, le `raise e` global bloque tous les schémas suivants → ils
restent vides.

**Fix proposé** (non appliqué, en attente arbitrage maintainer) : remplacer
le `raise` global par un `try/except` par schéma + accumulateur
`schemas_failed`. Action immédiate : drop des 4 slots vides + recréation via
`create_empty_tenant --count 4`.

### 10.11 Migration fantôme `0207_configuration_rapport_emails_and_more`

**Symptôme** : `IntegrityError: null value in column "rapport_emails"` lors
de `Configuration.get_solo()`.

**Cause** : DB locale dev avait été migrée à un moment sur la branche
`main-compta` (chantier COMPTABILITE) qui a une migration `0207_configuration_rapport_emails_and_more.py`.
Le checkout vers `main` a supprimé le fichier `.py` source mais a laissé la
colonne `rapport_emails NOT NULL` en BD + l'entrée dans `django_migrations`
de chaque schéma tenant. Donc `Configuration.get_solo()` génère un INSERT
sans valeur pour `rapport_emails` → viol contrainte NOT NULL.

**Fix appliqué par le maintainer** (côté BD, pas code) : rollback de la
migration fantôme sur tous les schémas tenant.

**Conflit numéro** : ma migration `0207_fix_postaladdress_latlng_precision`
prend le numéro 0207 — pas de conflit puisque `main-compta` est une branche
abandonnée (confirmé maintainer). Si elle redevient active, il faudra
renommer ma migration en 0208.

### 10.12 Audit critique final avant push prod

Subagent Explore (œil neuf) a relu les 15 fichiers modifiés. Verdict :
**SAFE TO SHIP**. Une seule remarque mineure non bloquante : le fallback
`get_language() or "fr"` privilégie le FR si LocaleMiddleware est
misconfiguré (acceptable, le FR est le marché primaire de TiBillet).

### 10.13 Fichiers modifiés (synthèse)

| Domaine | Fichier | Lignes touchées |
|---|---|---|
| Hotfix prod | `BaseBillet/models.py` | 261-281 |
| Hotfix prod | `BaseBillet/migrations/0207_fix_postaladdress_latlng_precision.py` | NEW |
| i18n mailers | `MetaBillet/models.py` | + champ `language` (lignes 295+) |
| i18n mailers | `MetaBillet/migrations/0016_add_wc_language.py` | NEW |
| Wizard | `onboard/views.py::_finalize_otp_success` | +25 lignes |
| Wizard | `onboard/views.py` POST identity | +10 lignes |
| Wizard | `onboard/tasks.py::onboard_otp_mailer` | translation.override |
| Wizard | `onboard/tasks.py::onboard_ready_mailer` | translation.override + instance_url |
| Wizard | `onboard/tasks.py::create_tenant_from_draft` | +80 lignes bloc 3ter |
| Wizard | `onboard/templates/onboard/steps/06_launch.html` | 75-105 (fix polling) |
| Mails | `onboard/templates/onboard/emails/ready.html` | full rewrite |
| Mails | `onboard/templates/onboard/emails/ready.txt` | full rewrite |
| Mails | `onboard/templates/onboard/emails/otp_code.html` | full rewrite |
| Mails | `onboard/templates/onboard/emails/otp_code.txt` | full rewrite |
| Landing | `seo/templates/seo/landing.html` | 3 sections |
| Landing | `seo/templates/seo/base.html` | + og:locale |
| Landing | `seo/views.py::landing` | + JSON-LD WebSite |
| Landing | `seo/static/seo/seo.css` | +85 lignes ROADMAP |

### 10.14 Tâches restantes pour le maintainer

1. **Appliquer les 2 migrations** :
   ```bash
   docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing
   ```
2. **Workflow i18n** (le maintainer le gère lui-même) : `makemessages -l fr -l en` + traduire les nouvelles strings dans `django.po` + `compilemessages`. Strings nouvelles principales :
   - Templates emails : Bienvenue dans la communauté TiBillet, Votre code de vérification, Vous avez demandé la création..., Votre espace TiBillet ... est prêt !, ACCÉDER À MON ESPACE, etc.
   - Landing : Données ouvertes, Logiciel libre AGPLv3, Agenda participatif, Référencement et SEO, Futur de TiBillet — chantiers en cours, Newsletter intégrée, Réseaux sociaux unifiés, Fédiverse et Mobilizon, Économie en cascade.
3. **Nettoyer le pool WAITING_CONFIG** : drop les 4 slots vides + relancer `create_empty_tenant --count 4`.
4. **Décider du fix `cron_morning`** : remplacer `raise` global par `try/except` par schéma (proposé section 10.10).

---

## 11. Liens utiles

- Plan d'implémentation détaillé : `02-implementation-plan.md`
- Spec design originale : `01-design-spec.md`
- Follow-ups & must-have à explorer : `04-followups.md`
- Prompt prochaine session : `05-next-session-prompt.md`
- Spec widget GPS réutilisable : `../WIDGET_GEO/01-design-spec.md`
- Plan d'impl widget GPS : `../WIDGET_GEO/02-implementation-plan.md`
- **Spec chantier Stripe future** : `../MOYENS_PAIEMENT/01-stripe-migration-spec.md`
