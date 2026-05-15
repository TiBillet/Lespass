"""
URLs du wizard d'onboarding.
/ URLs for the onboarding wizard.

LOCALISATION: onboard/urls.py

Choix d'implementation (cf. djc / FALC) : on utilise `path(...)` direct
plutot que `DefaultRouter`. Le wizard n'expose pas de ressource REST
classique (pas de list/retrieve/create CRUD), il sert juste des partials
HTMX. Un router DRF generait des URLs deroutantes du type
`/onboard/onboard/` et ajouterait du bruit pour zero benefice.
/ Implementation choice (per djc/FALC): we use plain `path(...)` instead
of `DefaultRouter`. The wizard isn't a REST resource (no list/retrieve
CRUD), it just serves HTMX partials. A DRF router would generate
confusing URLs like `/onboard/onboard/` for no benefit.

Routes :
  - `/onboard/`              -> root (redirige vers la step courante)
  - `/onboard/identity/`     -> step 1 identite
  - `/onboard/verify/`       -> step 2 verification OTP (Task 11)
  - `/onboard/resend-otp/`   -> renvoi OTP (Task 11)
  - `/onboard/place/`        -> step 3 lieu + GPS (Task 12)
  - `/onboard/geocode/`      -> proxy Nominatim (Task 12, rate-limit 1/s)
  - `/onboard/descriptions/` -> step 4 descriptions + logo (Task 13)
  - `/onboard/events/`       -> step 5 brouillons d'events (Task 14, finalize)
  - `/onboard/events/add/`   -> ajoute un event draft (Task 14, HTMX)
  - `/onboard/events/<idx>/remove/` -> retire un event draft (Task 14, HTMX)
  - `/onboard/launch/`       -> step 6 lancement async (placeholder Task 15)

/ Routes:
  - `/onboard/`              -> root (redirect to current step)
  - `/onboard/identity/`     -> step 1 identity
  - `/onboard/verify/`       -> step 2 OTP verify (Task 11)
  - `/onboard/resend-otp/`   -> OTP resend (Task 11)
  - `/onboard/place/`        -> step 3 place + GPS (Task 12)
  - `/onboard/geocode/`      -> Nominatim proxy (Task 12, rate-limit 1/s)
  - `/onboard/descriptions/` -> step 4 descriptions + logo (Task 13)
  - `/onboard/events/`       -> step 5 event drafts (Task 14, finalize)
  - `/onboard/events/add/`   -> add an event draft (Task 14, HTMX)
  - `/onboard/events/<idx>/remove/` -> remove an event draft (Task 14, HTMX)
  - `/onboard/launch/`       -> step 6 async launch (placeholder Task 15)
"""

from django.urls import path

from onboard.views import OnboardViewSet


# Vues bindees explicitement : chaque path point sur une methode du ViewSet.
# Avantage : URLs nommees stables (`onboard-identity`, ...) qui resolvent
# depuis n'importe ou via `reverse()`. / Explicit view bindings: each path
# points to a ViewSet method. Stable named URLs reachable via `reverse()`.
onboard_root = OnboardViewSet.as_view({"get": "root"})
onboard_identity = OnboardViewSet.as_view({
    "get": "identity", "post": "identity",
})
onboard_verify = OnboardViewSet.as_view({
    "get": "verify", "post": "verify",
})
# Action de re-envoi de l'OTP — POST only (Task 11). URL distincte de
# `/onboard/verify/` pour rester explicite et permettre un binding HTMX
# direct. / OTP resend action — POST only (Task 11). Distinct URL from
# `/onboard/verify/` for clarity and easy HTMX binding.
onboard_resend_otp = OnboardViewSet.as_view({
    "post": "resend_otp",
})
onboard_place = OnboardViewSet.as_view({
    "get": "place", "post": "place",
})
# Endpoint geocode du wizard (Task 12) — POST only, partial HTMX.
# / Wizard geocode endpoint (Task 12) — POST only, HTMX partial.
onboard_geocode = OnboardViewSet.as_view({
    "post": "geocode_endpoint",
})
onboard_descriptions = OnboardViewSet.as_view({
    "get": "descriptions", "post": "descriptions",
})
onboard_events = OnboardViewSet.as_view({
    "get": "events", "post": "events",
})
# Sous-actions HTMX de la step 5 (Task 14). `events_add` et `events_remove`
# n'exposent que POST (HTMX partials). / Step 5 HTMX sub-actions (Task 14).
# `events_add` and `events_remove` expose POST only (HTMX partials).
onboard_events_add = OnboardViewSet.as_view({
    "post": "events_add",
})
onboard_events_remove = OnboardViewSet.as_view({
    "post": "events_remove",
})
onboard_launch = OnboardViewSet.as_view({
    "get": "launch", "post": "launch",
})
# Sous-actions HTMX de la step 6 (Task 15). `launch_status` est GET only
# (polled 2s), `launch_retry` est POST only (reset erreur + re-enqueue).
# / Step 6 HTMX sub-actions (Task 15). `launch_status` is GET only
# (polled 2s), `launch_retry` is POST only (reset error + re-enqueue).
onboard_launch_status = OnboardViewSet.as_view({
    "get": "launch_status",
})
onboard_launch_retry = OnboardViewSet.as_view({
    "post": "launch_retry",
})
# Magic link de reprise (Task 15). GET only, prend une signature URL-safe
# en parametre (TimestampSigner).
# / Resume magic link (Task 15). GET only, takes a URL-safe signature
# (TimestampSigner) as parameter.
onboard_resume = OnboardViewSet.as_view({
    "get": "resume",
})


urlpatterns = [
    path("onboard/", onboard_root, name="onboard-root"),
    path("onboard/identity/", onboard_identity, name="onboard-identity"),
    path("onboard/verify/", onboard_verify, name="onboard-verify"),
    # Resend OTP : POST only, partial HTMX. URL plate (pas sous /verify/)
    # car le ViewSet binde via `as_view({"post": "resend_otp"})` et le plan
    # impose ce chemin. / Resend OTP: POST only, HTMX partial. Flat URL
    # (not under /verify/) per plan spec + ViewSet binding.
    path("onboard/resend-otp/", onboard_resend_otp, name="onboard-resend-otp"),
    path("onboard/place/", onboard_place, name="onboard-place"),
    # Proxy Nominatim, rate-limite 1 req/s/IP (cf. GeocodeRateThrottle).
    # / Nominatim proxy, rate-limited 1 req/s/IP (cf. GeocodeRateThrottle).
    path("onboard/geocode/", onboard_geocode, name="onboard-geocode"),
    path("onboard/descriptions/", onboard_descriptions, name="onboard-descriptions"),
    path("onboard/events/", onboard_events, name="onboard-events"),
    # Sous-routes HTMX de la step 5 (Task 14). Ajouter + supprimer un
    # brouillon d'event. `<int:idx>` cote URLconf assure la conversion en
    # entier ; la regex `(?P<idx>\d+)` cote `url_path` du ViewSet declare
    # le meme parametre. / HTMX sub-routes for step 5 (Task 14). Add + remove
    # an event draft. `<int:idx>` casts to int; the ViewSet's `url_path`
    # regex `(?P<idx>\d+)` declares the same param.
    path("onboard/events/add/", onboard_events_add, name="onboard-events-add"),
    path(
        "onboard/events/<int:idx>/remove/",
        onboard_events_remove,
        name="onboard-events-remove",
    ),
    path("onboard/launch/", onboard_launch, name="onboard-launch"),
    # Sous-routes HTMX de la step 6 (Task 15). Endpoint polled toutes les
    # 2s par le container `#status`, et endpoint retry pour relancer la
    # task `create_tenant_from_draft` apres une erreur.
    # / HTMX sub-routes for step 6 (Task 15). Status endpoint polled every
    # 2s by the `#status` container, and retry endpoint to re-enqueue
    # `create_tenant_from_draft` after an error.
    path(
        "onboard/launch/status/",
        onboard_launch_status,
        name="onboard-launch-status",
    ),
    path(
        "onboard/launch/retry/",
        onboard_launch_retry,
        name="onboard-launch-retry",
    ),
    # Magic link de reprise (Task 15). Le segment `<signed>` capture la
    # signature URL-safe — pas de slash dans la signature
    # `TimestampSigner` (caracteres base64 + `:` + timestamp), donc
    # `<str:signed>` suffit. / Resume magic link (Task 15). The `<signed>`
    # segment captures the URL-safe signature. `TimestampSigner` produces
    # base64 + `:` + timestamp (no slash), so `<str:signed>` is enough.
    path(
        "onboard/resume/<str:signed>/",
        onboard_resume,
        name="onboard-resume",
    ),
]
