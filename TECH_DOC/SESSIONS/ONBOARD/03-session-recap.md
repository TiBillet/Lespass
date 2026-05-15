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

## 7. Liens utiles

- Plan d'implémentation détaillé : `02-implementation-plan.md`
- Spec design originale : `01-design-spec.md`
- Follow-ups & must-have à explorer : `04-followups.md`
- Prompt prochaine session : `05-next-session-prompt.md`
