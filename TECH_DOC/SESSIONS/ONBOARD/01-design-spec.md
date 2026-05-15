# Wizard d'onboarding nouveau tenant — Design

**Date :** 2026-05-14
**Statut :** Spec en attente de revue (puis writing-plans)
**Contexte :** Le bouton "Créer son espace" de la landing root pointe vers `https://tibillet.org` ou vers `/tenant/new/` (formulaire simple POST dans `BaseBillet.Tenant.create_waiting_configuration`). L'objectif est de remplacer ce flow par un wizard multi-étapes plus FALC, accessible depuis le tenant ROOT comme depuis n'importe quel tenant, avec persistance du brouillon et invitation possible par un tenant existant.

## 1. Architecture

### Nouvelle app : `onboard/` (SHARED_APPS)

```
onboard/
├── apps.py
├── urls.py                          # /onboard/<step>/
├── views.py                         # OnboardViewSet — 1 @action par étape
├── serializers.py                   # 1 Serializer DRF par étape
├── services.py                      # generate_otp(), verify_otp(), geocode() (helpers synchrones)
├── models.py                        # OnboardInvitation
├── tasks.py                         # onboard_otp_mailer, create_tenant_from_draft, onboard_ready_mailer, purge_stale_onboard_drafts
├── admin.py                         # OnboardInvitationAdmin (Unfold)
├── templates/onboard/
│   ├── base_wizard.html             # layout 2 colonnes (panneau + form)
│   ├── steps/
│   │   ├── 01_identity.html
│   │   ├── 02_verify.html
│   │   ├── 03_place.html
│   │   ├── 04_descriptions.html
│   │   ├── 05_events.html
│   │   └── 06_launch.html
│   └── partials/
│       ├── progress_panel.html
│       ├── map_widget.html
│       └── event_row.html
└── tests/
    ├── test_onboard_flow.py
    └── test_onboard_otp.py
```

### Modèles touchés

**`MetaBillet.WaitingConfiguration` — étendu (1 migration, tous champs nullable)** :
- `first_name`, `last_name` (CharField, max 60, nullable)
- `long_description` (TextField, nullable)
- `latitude`, `longitude` (DecimalField, 9.6, nullable)
- `address_locality`, `address_country`, `postal_code`, `street_address` (CharField, nullable)
- `logo` (StdImageField, nullable, upload_to=`onboard_drafts/%Y/%m/`)
- `events_draft` (JSONField, défaut `list`)
- `otp_hash` (CharField max 100, nullable — bcrypt du code à 6 chiffres)
- `otp_expires_at` (DateTimeField, nullable)
- `otp_attempts` (PositiveSmallIntegerField, défaut 0)
- `otp_resend_count` (PositiveSmallIntegerField, défaut 0)
- `current_step` (CharField max 20, choices `identity|verify|place|descriptions|events|launch`, défaut `identity`)
- `invitation` (FK `onboard.OnboardInvitation`, nullable)
- `error_message` (TextField, nullable) — rempli par `create_tenant_from_draft` si la task échoue, lu par `/onboard/launch/status/`

**Pas de `modules_intent` ni `grist_optin`** : l'activation des modules et l'opt-in Grist se font depuis le dashboard admin du tenant créé (déjà en place). La page launch se concentre sur la pédagogie (carrousel d'info) pendant l'attente.

**Nouveau modèle `onboard.OnboardInvitation` (SHARED_APPS) :**
```python
code             : CharField(max_length=40, unique=True, db_index=True)
federation       : ForeignKey('fedow_core.Federation', on_delete=CASCADE)
invited_by_user  : ForeignKey('AuthBillet.TibilletUser', on_delete=CASCADE)
invited_by_tenant: ForeignKey('Customers.Client', on_delete=CASCADE)
email_invited    : EmailField(null=True, blank=True)
used_by_wc       : ForeignKey('MetaBillet.WaitingConfiguration', null=True, blank=True, on_delete=SET_NULL)
used_at          : DateTimeField(null=True, blank=True)
expires_at       : DateTimeField()            # défaut now + 30j (par save())
created_at       : DateTimeField(auto_now_add=True)
```

**`Customers.Client` — non touché.** Pool `Client.objects.filter(categorie=WAITING_CONFIG)` réutilisé.

### Backend réutilisé

- `WaitingConfiguration.create_tenant()` — chaîne existante, testée en prod.
- `Client.objects.filter(categorie=WAITING_CONFIG)` — pool de tenants pré-créés.
- `new_tenant_mailer.delay()` — mail post-création contenant le lien Stripe Connect.
- `AuthBillet.utils.get_or_create_user()` — création/lookup de TibilletUser.
- `fedow_core.Federation` — ajout direct dans `tenants` (skip `pending_tenants`) si invitation.

### Routes

| URL | Méthode | Action |
|---|---|---|
| `/onboard/` | GET | Redirige vers `current_step` du brouillon ou `/onboard/identity/` |
| `/onboard/identity/` | GET, POST | Étape 1 : email + prénom/nom + nom du lieu + DNS + CGU (+ captcha si anonyme) |
| `/onboard/verify/` | GET, POST | Étape 2 : OTP 6 chiffres (sautée si user authentifié `email_valid=True`) |
| `/onboard/resend-otp/` | POST | Renvoie un nouveau OTP (max 3 / h / IP) |
| `/onboard/place/` | GET, POST | Étape 3 : adresse + carte Leaflet (lat/long) + description courte |
| `/onboard/geocode/` | POST | Proxy Nominatim (cache Redis 24h) |
| `/onboard/descriptions/` | GET, POST | Étape 4 : long description + logo |
| `/onboard/events/` | GET, POST | Étape 5 : 0..N events (HTMX add/remove) |
| `/onboard/events/add/` | POST | Renvoie partial event_row.html |
| `/onboard/events/<idx>/remove/` | POST | Supprime un event du JSON, renvoie liste |
| `/onboard/launch/` | GET, POST | Étape 6 : crée le tenant + CTAs modules/Stripe/Grist |
| `/onboard/resume/<signed_uuid>/` | GET | Magic link reprise brouillon (TimestampSigner, 7j) |

## 2. Flow complet

**Étape 1 — Identity** (`/onboard/identity/`)
- Champs : `email`, `email_confirm`, `first_name`, `last_name`, `name` (nom lieu), `dns_choice`, CGU.
- Captcha "answer" **uniquement si user anonyme** (skip si `request.user.is_authenticated`).
- Si `?invite=<code>` en query string : valide l'invitation (existante + non utilisée + non expirée), pré-affiche chip "🎉 Invité·e par <tenant>", attache à `wc.invitation`.
- Au POST :
  - Si user authentifié + `email_valid=True` : pré-remplit email/first_name/last_name, `email_confirmed=True` direct, `current_step='place'` → redirect `/onboard/place/`.
  - Sinon : crée WC avec `email_confirmed=False`, génère OTP 6 chiffres, `otp_hash = bcrypt(otp)`, `otp_expires_at = now+10min`, envoie mail `onboard_otp_mailer.delay(wc.uuid, otp_clair)`, redirect `/onboard/verify/`.
- Si email correspond à un WC existant non finalisé : page intercalaire "Brouillon trouvé, reprendre ?" (re-OTP obligatoire pour authentifier la reprise).

**Étape 2 — Verify** (`/onboard/verify/`)
- 6 inputs `inputmode=numeric maxlength=1` avec autofocus + auto-tab JS minimal.
- POST : `bcrypt.checkpw(saisie, wc.otp_hash)` + `now < otp_expires_at` + `otp_attempts < 5`.
- Si OK : `email_confirmed=True`, `current_step='place'`, redirect `/onboard/place/`. Crée aussi le `TibilletUser` si pas encore en base (`get_or_create_user(wc.email, send_mail=False)`).
- Si KO : incrémente `otp_attempts`, message inline. Au 5e échec, lock 30 min.
- Bouton "Renvoyer le code" → `/onboard/resend-otp/` (max 3/h/IP via Redis).

**Étape 3 — Place** (`/onboard/place/`)
- Champs : `street_address`, `postal_code`, `address_locality`, `address_country`, `short_description`.
- Géocodage auto : `htmx:trigger="change delay:1s from:.address-input"` → POST `/onboard/geocode/` → proxy Nominatim → renvoie partial `map_widget.html` avec marker positionné.
- **Règle invariante : le marker Leaflet est TOUJOURS `draggable: true`**, dans les 3 scénarios ci-dessous. Drag → `marker.on('dragend')` met à jour `#id_latitude` / `#id_longitude` (inputs cachés). C'est le pattern unique pour affiner la géolocalisation au mètre près.
  1. **Cas nominal** (Nominatim répond avec un bon match) : marker positionné automatiquement aux coords renvoyées, message "Affine la position en déplaçant le marker si besoin".
  2. **Cas mauvais match** (Nominatim répond mais imprécis, ex. au centre de la ville) : marker positionné quand même, message FALC "Déplace le marker pour positionner exactement ton lieu".
  3. **Cas fallback** (Nominatim down, timeout 5s, no result) : carte vide centrée France (ou pays via `Accept-Language`), bandeau jaune "Service de géolocalisation indisponible, clique sur la carte pour positionner ton lieu". `map.on('click')` pose le marker (draggable lui aussi).
- POST → sauvegarde lat/long, `current_step='descriptions'`. Validation serveur : lat/long obligatoires non null.

**Étape 4 — Descriptions** (`/onboard/descriptions/`)
- Champs : `long_description` (textarea + compteur), upload `logo` (StdImage + crop variation).
- Preview logo via HTMX `hx-trigger="change"` sur le file input.
- POST → sauvegarde, `current_step='events'`.

**Étape 5 — Events** (`/onboard/events/`)
- Bouton "Sauter cette étape" en haut (events optionnels).
- Bouton "Ajouter un événement" → HTMX `hx-post="/onboard/events/add/"` → injecte `partials/event_row.html` (form inline : nom, datetime, description, image).
- Bouton "× supprimer" sur chaque event → POST `/onboard/events/<idx>/remove/` → renvoie la liste mise à jour.
- Persistance : JSONField `wc.events_draft = [{name, datetime_iso, description, image_path}, ...]`.
- POST → `current_step='launch'` + **enqueue `create_tenant_from_draft.delay(wc.uuid)`** (idempotent : ne ré-enqueue pas si `wc.tenant_id` déjà set).

**Étape 6 — Launch** (`/onboard/launch/`)
- **Création tenant en tâche de fond** : déclenchée au POST de step 5, pas au GET de step 6. La page launch s'affiche **immédiatement** pendant que la task Celery `create_tenant_from_draft` provisionne le tenant (réutilise pool WAITING_CONFIG → renomme, change catégorie, instancie Configuration, crée events `published=False`, attache fédération si invitation, applique `wc.events_draft`). En pratique, ce travail prend qq secondes (pas de migrate à faire car le tenant du pool est déjà migré).
- **Page launch (GET)** affiche **immédiatement** :
  - Tête : "🎉 Bienvenue ! Ton espace `<nom_lieu>` arrive…" + indicateur de progression :
    - `⏳ Finalisation en cours…` (par défaut)
    - `✓ Espace prêt — tu peux y aller !` (une fois la task terminée)
  - **Carrousel d'info pédagogique** au centre de la page, qui défile automatiquement (5s par card, pause au survol, navigation `‹ ›` pour avancer/reculer). Le but : occuper l'attention pendant les qq secondes de création, et faire découvrir TiBillet. Cards (~6) :
    1. **Adhésions et abonnements** — "Tu pourras gérer les adhésions à ton association et proposer des abonnements à tes membres." + lien `Documentation`.
    2. **Budget contributif (crowds)** — "Lance des campagnes de financement participatif avec contribution adaptive et cascade multi-asset." + lien `Documentation`.
    3. **Booking de salle / ressource** — "Permets à tes membres et au public de réserver tes salles ou ton matériel." + lien `Documentation`.
    4. **Mesure d'impact social via Grist** — "Connecte ton espace à la base ouverte du comité data des tiers-lieux pour mesurer ton impact." + lien `En savoir plus`.
    5. **Encaisser avec Stripe** — "Active Stripe Connect dans ton admin pour vendre des billets et adhésions en ligne." + lien `Documentation`.
    6. **Fédération de lieux** — "Ton lieu peut rejoindre le réseau coopératif TiBillet et partager son agenda avec d'autres structures." + lien `Documentation`.
  - **Pas de toggles ni de cases à cocher sur cette page.** Les modules s'activent depuis le dashboard admin (`Administration` → cartes module, déjà en place). L'opt-in newsletter / Grist se fera depuis le dashboard également si l'utilisateur le souhaite.
  - **Bouton "Accéder à mon espace"** : `disabled` tant que `done=false` (style atténué + spinner inline + label "⏳ Préparation…"). Au `done`, le bouton s'active (label "Accéder à mon espace →") et son `href` est rempli avec `https://<new_tenant.primary_domain>/admin/`.
  - **Polling HTMX** sur le bandeau de statut + bouton : `hx-get="/onboard/launch/status/" hx-trigger="load, every 2s" hx-target="#launch-status" hx-swap="outerHTML"`. Le partial renvoyé inclut un `HX-Trigger: onboard-ready` event quand `done=true` ; le polling s'arrête automatiquement car le partial de done **ne contient plus l'attribut `hx-trigger="every 2s"`** (auto-stop natif HTMX, pas besoin de JS custom). Intervalle 2s = 1 req / 2s / user en step 6 : marginal côté serveur.
- **Mail "Votre espace est prêt"** : à la fin de la task `create_tenant_from_draft` (success), un mail `onboard_ready_mailer.delay(wc.uuid)` est envoyé à `wc.email` avec sujet "🎉 Ton espace TiBillet est prêt !" + lien vers `https://<new_tenant.primary_domain>/admin/`. **Utilité** : si l'utilisateur a fermé l'onglet pendant les qq secondes d'attente ou si la création a pris plus longtemps que prévu (Celery encombré), il peut y aller via le mail.
- **`/onboard/launch/status/`** (GET, polling endpoint) :
  - Si `wc.tenant_id is None` → retourne partial `status-progress.html` (⏳ + bouton disabled + `hx-trigger="every 2s"` pour continuer le polling).
  - Si `wc.tenant_id` set → retourne partial `status-done.html` (✓ + bouton actif avec href, **sans `hx-trigger`** → arrêt naturel du polling). Header `HX-Trigger: onboard-ready` pour permettre à du JS optionnel d'arrêter le carrousel ou autre.
  - Si la task a échoué (`wc.error_message` set par la task) → retourne partial `status-error.html` (FALC : "Une erreur est survenue, on a reçu une alerte. Tu peux réessayer ou nous contacter à `contact@tibillet.coop`.") + bouton "Réessayer" qui re-enqueue la task.

## 3. UX — Layout C (validé)

**Desktop ≥ 992px** : 2 colonnes Bootstrap `col-lg-5` (panneau gauche dégradé vert) + `col-lg-7` (formulaire).

**Mobile < 992px** : panneau collapsé dans un `<details>` natif au-dessus du formulaire.

**Panneau gauche** :
- Logo TiBillet + chip "Créer mon espace".
- Liste 5 étapes : icône (check / dot / lock) + label + ligne FALC.
- Pied : lien "Reprendre plus tard" (visible dès étape 3) + lien "Code d'invitation ?" (si non saisi).
- Badge "🎉 Invité·e par <tenant>" si invitation acceptée.

**Colonne droite** :
- H1 grand `"3. Votre lieu"` + sous-titre FALC.
- Champs Bootstrap 5 standards + `data-testid="onboard-<step>-<champ>"`.
- Erreurs HTTP 422 en HTML partial, affichage `aria-live="polite"`.
- Bas : `« Précédent »` + `« Continuer »` + "Sauter" (étape 5 uniquement).

**Carte étape 3 (Variante 1 validée)** : carte sous les champs adresse, lecture top-to-bottom, mobile-friendly. Marker draggable. Click sur carte = pose ou déplace.

**Transitions** : `hx-target="#wizard-content"`, `hx-swap="innerHTML transition:true"`, `hx-push-url="true"`. Bouton "Continuer" passe en disabled avec spinner inline. Overlay frosted glass seulement si > 400ms.

**A11y** : `aria-current="step"` sur étape courante. `aria-live="polite"` sur zone erreur. Focus visible. `prefers-reduced-motion` désactive transitions.

## 4. Persistance & reprise

**Source de vérité** : `WaitingConfiguration` en DB. La session Django ne porte QUE `request.session['onboard_wc_uuid']` (cookie signed).

**À chaque GET d'étape** :
1. Lit `wc_uuid` en session, charge le WC.
2. Vérifie que la step demandée correspond à `wc.current_step` ou est antérieure (revenir en arrière OK).
3. Pré-remplit le formulaire depuis le WC.
4. Panneau gauche affiche progression (cochées / courante / grisées).

**Reprise après fermeture navigateur** :
- Cas 1 : cookie session encore là → redirect vers `current_step`.
- Cas 2 : cookie perdu / autre appareil → étape 1 normale. Si l'user retape son email, on cherche `WaitingConfiguration.objects.filter(email=email, tenant__isnull=True).order_by('-created_at').first()`. Si trouvé : page intercalaire "Brouillon existe à l'étape X, créé il y a Y jours. Reprendre ou recommencer ?". Reprendre : re-OTP obligatoire + restaure session.

**Bouton "Reprendre plus tard"** (visible dès étape 3) : envoie magic link `/onboard/resume/<signed_uuid>/` (TimestampSigner, 7j) à l'email du WC. Clic → restaure session + redirect `current_step`, sans OTP.

**TTL** : 30 jours sans activité → cron `purge_stale_onboard_drafts` supprime WC + dossier `media/onboard_drafts/<wc_uuid>/`.

## 5. Sécurité & anti-abus

**Captcha** : étape 1 uniquement, skip si user authentifié.

**OTP** : `bcrypt(rounds=10)` hash en DB, jamais le clair. Expire 10 min. 5 tentatives max → lock 30 min. 3 renvois/h/IP via Redis (`onboard:resend:<ip>` TTL 3600s). `hmac.compare_digest` pour le compare. Skip OTP si user authentifié `email_valid=True`.

**Throttle DRF ScopedRateThrottle** :
- `identity` : 10 / h / IP
- `verify` : 30 / h / IP
- `resend-otp` : 3 / h / IP
- `launch` : 5 / h / IP

**Nominatim** : proxy serveur uniquement, User-Agent `TiBillet-Onboard/1.0 (contact@tibillet.coop)`, timeout 5s, cache Redis 24h sur SHA256 de la query, 1 req/s/IP côté serveur.

**Multi-tenant** : viewset SHARED, écritures WC dans META tenant via `tenant_context(meta)`. Pas de fuite cross-tenant.

**Upload images** : `media/onboard_drafts/<wc_uuid>/` pendant le brouillon, déplacé dans `media/<tenant_schema>/` à la création. Cron supprime les drafts orphelins.

**Logs** : `onboard.views` logger Python (info create_wc, verify_otp_success/fail, create_tenant_success/fail). OTP clair JAMAIS loggué. Sentry breadcrumb : étape courante + WC UUID (pas d'email en clair).

## 6. Validation côté DRF

1 serializer par étape, validations explicites :
- Email : `EmailField` + check anti-collision avec `TibilletUser.email` admin existant.
- OTP : regex `^\d{6}$`.
- DNS slug : regex `^[a-z0-9-]{3,30}$` + unicité contre `Customers.Domain.domain`.
- Lat/Long : bornes (-90/90, -180/180).
- Image : `StdImageField` (max 5 Mo, MIME jpg/png/webp).
- short_description : max 280 char. long_description : max 5000.
- Captcha "answer" : valeur attendue en session.

Erreurs renvoyées en HTML partial (HTTP 422) — pattern existant `BaseBillet/views.py:3649-3683`.

## 7. Risques + mitigations

| Risque | Mitigation |
|---|---|
| Pool WAITING_CONFIG vide en step 6 | Vue admin "Pool tenants" + cron alerte si <3 + auto-création d'un slot quand un est consommé (`post_save` Client). En cas d'épuisement au moment de la task async : task écrit `wc.error_message`, page launch affiche le message FALC, retry possible. |
| Task Celery `create_tenant_from_draft` échoue (exception, Celery down, DB locks…) | `bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3`. Si tous les retries échouent, `wc.error_message` rempli, alert Sentry, page launch affiche message FALC + bouton "Réessayer" qui re-enqueue. |
| User double-clique "Suivant" en step 5 → 2 tasks lancées en parallèle | Task vérifie `wc.tenant_id is None` au début (sous `select_for_update`), exit early sinon. Idempotence garantie. |
| User ferme l'onglet pendant la création async | Mail "Votre espace est prêt" envoyé par `onboard_ready_mailer.delay()` à la fin de la task `create_tenant_from_draft`. Le mail contient le lien admin du nouveau tenant, l'user le retrouve à tête reposée. |
| Spam wizard step 1 | Throttle 10/h/IP + captcha + cron purge 30j. |
| Nominatim down | Cache 24h + fallback marker manuel (click sur carte). Marker draggable dans tous les cas. |
| User loggué + invitation cross-tenant | Invitation lue depuis query string AVANT session. Attachée au WC peu importe le statut auth. |
| Migration WC enrichie casse anciens WC | Tous les nouveaux champs `null=True, blank=True`. Anciens path `/tenant/new/` fonctionnels. |
| Bouton "Créer son espace" depuis footer tenant T | Step 1 propose checkbox "Lier ce nouveau lieu à la fédération de <T>" (auto-invitation). |
| Stripe Connect non configuré dans `RootConfiguration` | Vérif au load step 6, cache bouton Stripe, message "Demandez à l'admin de la coop de finaliser la config Stripe". |

## 8. Tests

**pytest DB-only** (`onboard/tests/test_*.py`, ≥ 80% couverture) :
- `test_identity_creates_draft`
- `test_identity_skips_otp_for_authenticated_user_with_email_valid`
- `test_verify_otp_success` / `_wrong_code` / `_expired` / `_too_many_attempts`
- `test_resend_otp_throttle_3_per_hour`
- `test_place_geocode_proxy_caches_24h`
- `test_place_geocode_fallback_on_error`
- `test_descriptions_logo_upload_temp_storage`
- `test_events_add_remove_in_jsonfield`
- `test_launch_enqueues_async_task_at_step5_post`
- `test_launch_idempotent_double_post_step5`
- `test_create_tenant_from_draft_attaches_invitation_federation`
- `test_create_tenant_from_draft_creates_event_drafts_unpublished`
- `test_create_tenant_from_draft_no_pool_writes_error_message`
- `test_create_tenant_from_draft_sends_ready_mailer_on_success`
- `test_status_endpoint_returns_progress_then_done_stops_polling`
- `test_status_endpoint_returns_error_partial_when_task_failed`
- `test_launch_with_invitation_joins_federation_directly`
- `test_invitation_expired_falls_back_to_normal_creation`
- `test_resume_with_email_lookup_after_lost_session`
- `test_resume_with_magic_link`
- `test_purge_stale_drafts_management_command`

**E2E Playwright** (`tests/e2e/test_onboard_wizard.py`) :
- Golden path : 6 étapes complètes user anonyme.
- Invitation : `?invite=...` → vérification que tenant créé apparaît dans `Federation.tenants`.
- Resume : magic link → reprise step 3 avec données pré-remplies.

## 9. Scope (in)

- App `onboard/` SHARED_APPS.
- Migration data-only `MetaBillet.WaitingConfiguration` (+ champs nullable).
- Modèle + migration `onboard.OnboardInvitation`.
- Bouton "Créer son espace" landing root + footers tenants pointe sur `/onboard/`.
- Cron `purge_stale_onboard_drafts` (Celery beat hebdo).
- Management command `create_empty_tenant` pour repeupler le pool.
- Tests pytest + 3 Playwright.
- CHANGELOG.md + entry `A TESTER et DOCUMENTER/`.
- Workflow i18n.

## 10. Scope (out — reporté)

- Refonte de `WaitingConfiguration` en modèle natif (on étend, on ne refait pas).
- Suppression de `/tenant/new/` (kept en redirect, suppression dans session ultérieure).
- Signup user générique (création de compte sans tenant).
- Implémentation effective des 3 intégrations Grist / newsletter externe / booking salle — la page launch les présente dans le carrousel d'info mais l'activation se fait depuis le dashboard admin une fois le tenant créé.
- SSO/OAuth (Google, GitHub) sur step 1.
- Wizard PWA / mobile-native / push notifs.
