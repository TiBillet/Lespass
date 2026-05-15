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

## 9. Liens utiles

- Plan d'implémentation détaillé : `02-implementation-plan.md`
- Spec design originale : `01-design-spec.md`
- Follow-ups & must-have à explorer : `04-followups.md`
- Prompt prochaine session : `05-next-session-prompt.md`
- Spec widget GPS réutilisable : `../WIDGET_GEO/01-design-spec.md`
- Plan d'impl widget GPS : `../WIDGET_GEO/02-implementation-plan.md`
