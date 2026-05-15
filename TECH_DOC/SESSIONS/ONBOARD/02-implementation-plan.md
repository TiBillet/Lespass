# Wizard Onboarding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remplacer le formulaire `/tenant/new/` par un wizard d'onboarding en 6 étapes, accessible depuis le tenant ROOT et n'importe quel tenant, avec OTP, persistance du brouillon, invitation par tenant existant, et création asynchrone du tenant final.

**Architecture:** Nouvelle app SHARED `onboard/` qui étend `MetaBillet.WaitingConfiguration` (data-only), crée un modèle `OnboardInvitation`, et expose un `OnboardViewSet` (DRF `ViewSet` explicite, pas ModelViewSet). Réutilise le pool existant `Client.objects.filter(categorie=WAITING_CONFIG)` pour la création finale via une task Celery `create_tenant_from_draft`. UX layout C : panneau pédagogique gauche + form droite, HTMX `hx-push-url=true` entre étapes, polling 2s sur status page de fin.

**Tech Stack:** Django 5 + django-tenants, DRF (Serializer + ViewSet), HTMX, Bootstrap 5, Leaflet (déjà vendoré dans `seo/static/seo/vendor/leaflet/`), Celery + Redis, bcrypt, Nominatim (proxy).

**Spec:** `docs/superpowers/specs/2026-05-14-wizard-onboarding-design.md`

---

## Phase A — Setup app & migrations

### Task 1 : Créer l'app `onboard` et l'enregistrer

**Files:**
- Create: `onboard/__init__.py` (vide)
- Create: `onboard/apps.py`
- Modify: `TiBillet/settings.py` (ajouter `'onboard'` dans `SHARED_APPS`)
- Create: `onboard/migrations/__init__.py` (vide)

- [ ] **Step 1 : Créer l'arborescence**

```bash
docker exec lespass_django mkdir -p /DjangoFiles/onboard/migrations /DjangoFiles/onboard/management/commands /DjangoFiles/onboard/templates/onboard/steps /DjangoFiles/onboard/templates/onboard/partials /DjangoFiles/onboard/static/onboard /DjangoFiles/onboard/tests
docker exec lespass_django touch /DjangoFiles/onboard/__init__.py /DjangoFiles/onboard/migrations/__init__.py /DjangoFiles/onboard/management/__init__.py /DjangoFiles/onboard/management/commands/__init__.py /DjangoFiles/onboard/tests/__init__.py
```

- [ ] **Step 2 : `onboard/apps.py`**

```python
"""
Configuration de l'app onboard.
/ Configuration of the onboard app.

LOCALISATION: onboard/apps.py
"""

from django.apps import AppConfig


class OnboardConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "onboard"
    verbose_name = "Onboard wizard"

    def ready(self):
        # On importe les signaux pour qu'ils soient connectes au demarrage.
        # / Import signals so they get wired up at startup.
        from onboard import signals  # noqa: F401
```

- [ ] **Step 3 : Stub `onboard/signals.py` (vide pour l'instant)**

```python
"""
Signaux Django de l'app onboard.
/ Django signals for the onboard app.

LOCALISATION: onboard/signals.py
"""
# Signaux a venir : connexion post_save pour appliquer modules_intent post-creation.
# / Signals coming: post_save hook to apply post-creation logic.
```

- [ ] **Step 4 : Ajouter `'onboard'` dans `SHARED_APPS` (`TiBillet/settings.py` ligne ~155, après `'seo'`)**

Edit existant : insérer `'onboard',` après la ligne `'seo',` dans le tuple `SHARED_APPS`.

- [ ] **Step 5 : Vérification**

Run: `docker exec lespass_django poetry run python /DjangoFiles/manage.py check`
Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 6 : Commit**

```bash
git add onboard/ TiBillet/settings.py
git commit -m "feat(onboard): scaffold app and register in SHARED_APPS"
```

---

### Task 2 : Migration data-only — étendre `MetaBillet.WaitingConfiguration`

**Files:**
- Modify: `MetaBillet/models.py`
- Create: `MetaBillet/migrations/000X_extend_waitingconfiguration.py` (numéro auto via makemigrations)

- [ ] **Step 1 : Ajouter les champs sur `MetaBillet.WaitingConfiguration`**

Localiser la classe `WaitingConfiguration` dans `MetaBillet/models.py` et ajouter, après les champs existants :

```python
# === Wizard d'onboarding (extension) ===
# Champs ajoutes pour porter tout le brouillon du wizard pas-a-pas.
# Tous nullable pour ne pas casser les anciens WC crees par /tenant/new/.
# / Onboarding wizard fields. All nullable so old WCs keep working.

first_name = models.CharField(
    max_length=60, blank=True, default="",
    verbose_name=_("First name"),
)
last_name = models.CharField(
    max_length=60, blank=True, default="",
    verbose_name=_("Last name"),
)
long_description = models.TextField(
    blank=True, default="",
    verbose_name=_("Long description"),
)
latitude = models.DecimalField(
    max_digits=9, decimal_places=6, null=True, blank=True,
    verbose_name=_("Latitude"),
)
longitude = models.DecimalField(
    max_digits=9, decimal_places=6, null=True, blank=True,
    verbose_name=_("Longitude"),
)
street_address = models.CharField(
    max_length=255, blank=True, default="",
    verbose_name=_("Street address"),
)
postal_code = models.CharField(
    max_length=20, blank=True, default="",
    verbose_name=_("Postal code"),
)
address_locality = models.CharField(
    max_length=120, blank=True, default="",
    verbose_name=_("City"),
)
address_country = models.CharField(
    max_length=80, blank=True, default="",
    verbose_name=_("Country"),
)
logo = StdImageField(
    upload_to="onboard_drafts/%Y/%m/", blank=True, null=True,
    variations={"med": (480, 480), "crop": (240, 240, True)},
    verbose_name=_("Logo"),
)
events_draft = models.JSONField(
    default=list, blank=True,
    verbose_name=_("Events draft"),
)
otp_hash = models.CharField(
    max_length=100, blank=True, default="",
    verbose_name=_("OTP bcrypt hash"),
)
otp_expires_at = models.DateTimeField(
    null=True, blank=True,
    verbose_name=_("OTP expires at"),
)
otp_attempts = models.PositiveSmallIntegerField(
    default=0,
    verbose_name=_("OTP wrong attempts"),
)
otp_resend_count = models.PositiveSmallIntegerField(
    default=0,
    verbose_name=_("OTP resend count"),
)

STEP_IDENTITY = "identity"
STEP_VERIFY = "verify"
STEP_PLACE = "place"
STEP_DESCRIPTIONS = "descriptions"
STEP_EVENTS = "events"
STEP_LAUNCH = "launch"
STEP_CHOICES = (
    (STEP_IDENTITY, _("Identity")),
    (STEP_VERIFY, _("Verify email")),
    (STEP_PLACE, _("Place location")),
    (STEP_DESCRIPTIONS, _("Descriptions")),
    (STEP_EVENTS, _("Events")),
    (STEP_LAUNCH, _("Launch")),
)
current_step = models.CharField(
    max_length=20, choices=STEP_CHOICES, default=STEP_IDENTITY,
    verbose_name=_("Current wizard step"),
)
invitation = models.ForeignKey(
    "onboard.OnboardInvitation", null=True, blank=True,
    on_delete=models.SET_NULL, related_name="used_by_drafts",
    verbose_name=_("Invitation used"),
)
error_message = models.TextField(
    blank=True, default="",
    verbose_name=_("Async task error"),
)
```

S'assurer que `StdImageField` est déjà importé en haut du fichier ; sinon ajouter `from stdimage import StdImageField`.

- [ ] **Step 2 : Générer la migration**

Run: `docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations MetaBillet`
Expected: `Migrations for 'MetaBillet': MetaBillet/migrations/000X_<auto-name>.py - Add field ...`

- [ ] **Step 3 : Appliquer la migration sur tous les schémas**

Run: `docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing`
Expected: migration appliquée sur les schémas qui contiennent MetaBillet (META et SHARED).

- [ ] **Step 4 : Vérifier que les anciens `/tenant/new/` flows ne sont pas cassés**

Run: `docker exec lespass_django poetry run pytest tests/pytest/ -k "tenant" -v`
Expected: pas de régression sur les tests existants liés à `WaitingConfiguration`.

- [ ] **Step 5 : Commit**

```bash
git add MetaBillet/
git commit -m "feat(onboard): extend WaitingConfiguration with wizard fields"
```

---

### Task 3 : Modèle `OnboardInvitation` + migration

**Files:**
- Create: `onboard/models.py`
- Create: `onboard/migrations/0001_initial.py` (via makemigrations)

- [ ] **Step 1 : Écrire le test du modèle**

Create `onboard/tests/test_models.py` :

```python
"""
Tests du modele OnboardInvitation.
/ Tests for OnboardInvitation model.

LOCALISATION: onboard/tests/test_models.py
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from Customers.models import Client
from AuthBillet.models import TibilletUser


@pytest.mark.django_db
def test_invitation_code_unique_and_auto_generated():
    """Une invitation cree un code unique automatiquement si pas fourni."""
    from onboard.models import OnboardInvitation
    from fedow_core.models import Federation

    tenant = Client.objects.exclude(categorie=Client.ROOT).first()
    user = TibilletUser.objects.first()
    fed = Federation.objects.create(name="Test fed", created_by=user)

    inv = OnboardInvitation.objects.create(
        federation=fed,
        invited_by_user=user,
        invited_by_tenant=tenant,
    )

    assert inv.code  # non vide
    assert len(inv.code) >= 10
    assert inv.expires_at > timezone.now() + timedelta(days=29)
    assert inv.used_at is None


@pytest.mark.django_db
def test_invitation_is_valid_method():
    """Une invitation expiree ou deja utilisee est marquee invalide."""
    from onboard.models import OnboardInvitation
    from fedow_core.models import Federation

    user = TibilletUser.objects.first()
    tenant = Client.objects.exclude(categorie=Client.ROOT).first()
    fed = Federation.objects.create(name="Fed2", created_by=user)

    valide = OnboardInvitation.objects.create(
        federation=fed, invited_by_user=user, invited_by_tenant=tenant,
    )
    assert valide.is_valid() is True

    valide.used_at = timezone.now()
    valide.save()
    assert valide.is_valid() is False

    perimee = OnboardInvitation.objects.create(
        federation=fed, invited_by_user=user, invited_by_tenant=tenant,
        expires_at=timezone.now() - timedelta(days=1),
    )
    assert perimee.is_valid() is False
```

- [ ] **Step 2 : Vérifier que le test échoue (le modèle n'existe pas encore)**

Run: `docker exec lespass_django poetry run pytest onboard/tests/test_models.py -v`
Expected: `ImportError: cannot import name 'OnboardInvitation' from 'onboard.models'`.

- [ ] **Step 3 : Écrire le modèle**

Create `onboard/models.py` :

```python
"""
Modeles de l'app onboard.
/ Models for the onboard app.

LOCALISATION: onboard/models.py

Pour l'instant, un seul modele : OnboardInvitation, qui represente un
code d'invitation cree par un tenant existant pour parrainer un nouveau
lieu. Le brouillon de wizard lui-meme est porte par MetaBillet.WaitingConfiguration
(etendu, cf. migration 0011 dans MetaBillet).
/ Single model for now: OnboardInvitation, an invitation code created
by an existing tenant to sponsor a new venue. The wizard draft itself
lives on MetaBillet.WaitingConfiguration (extended).
"""

import secrets
from datetime import timedelta

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


def _generate_invitation_code():
    """
    Genere un code d'invitation lisible (8 caracteres alphanumeriques).
    / Generate a readable invitation code (8 alphanumeric chars).
    """
    # secrets.token_urlsafe(6) produit ~8 caracteres URL-safe.
    return secrets.token_urlsafe(6)


def _default_expires_at():
    return timezone.now() + timedelta(days=30)


class OnboardInvitation(models.Model):
    """
    Code d'invitation cree par un tenant pour parrainer un nouveau lieu.
    Si le wizard est lance avec ce code (`?invite=<code>`), le nouveau
    tenant rejoint directement la federation indiquee (pas via pending).
    / Invitation code created by a tenant to sponsor a new venue.
    If the wizard starts with this code, the new tenant joins the
    federation directly (skips pending_tenants).
    """

    code = models.CharField(
        max_length=40, unique=True, db_index=True,
        default=_generate_invitation_code,
        verbose_name=_("Invitation code"),
    )
    federation = models.ForeignKey(
        "fedow_core.Federation",
        on_delete=models.CASCADE,
        related_name="onboard_invitations",
        verbose_name=_("Target federation"),
    )
    invited_by_user = models.ForeignKey(
        "AuthBillet.TibilletUser",
        on_delete=models.CASCADE,
        related_name="onboard_invitations_sent",
        verbose_name=_("Invited by user"),
    )
    invited_by_tenant = models.ForeignKey(
        "Customers.Client",
        on_delete=models.CASCADE,
        related_name="onboard_invitations_sent",
        verbose_name=_("Invited by tenant"),
    )
    email_invited = models.EmailField(
        null=True, blank=True,
        verbose_name=_("Invited email (optional)"),
    )
    used_at = models.DateTimeField(
        null=True, blank=True,
        verbose_name=_("Used at"),
    )
    expires_at = models.DateTimeField(
        default=_default_expires_at,
        verbose_name=_("Expires at"),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Onboard invitation")
        verbose_name_plural = _("Onboard invitations")

    def is_valid(self):
        """
        Renvoie True si l'invitation n'est pas utilisee et pas expiree.
        / True if the invitation has not been used and has not expired.
        """
        if self.used_at is not None:
            return False
        if self.expires_at <= timezone.now():
            return False
        return True

    def __str__(self):
        return f"Invitation {self.code} → {self.federation.name}"
```

- [ ] **Step 4 : Générer la migration**

Run: `docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations onboard`
Expected: `Migrations for 'onboard': onboard/migrations/0001_initial.py - Create model OnboardInvitation`

- [ ] **Step 5 : Appliquer**

Run: `docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing`

- [ ] **Step 6 : Vérifier que le test passe**

Run: `docker exec lespass_django poetry run pytest onboard/tests/test_models.py -v`
Expected: PASS sur les 2 tests.

- [ ] **Step 7 : Commit**

```bash
git add onboard/models.py onboard/migrations/ onboard/tests/test_models.py
git commit -m "feat(onboard): add OnboardInvitation model with auto code + expiry"
```

---

## Phase B — Services & tasks Celery

### Task 4 : Services OTP (`generate_otp`, `verify_otp`)

**Files:**
- Create: `onboard/services.py`
- Create: `onboard/tests/test_services_otp.py`

- [ ] **Step 1 : Test `generate_otp`**

```python
"""
Tests des helpers OTP (generation + verification).
/ Tests for OTP helpers (generation + verification).

LOCALISATION: onboard/tests/test_services_otp.py
"""

import re
from datetime import timedelta

import pytest
from django.utils import timezone


def test_generate_otp_returns_6_digits():
    from onboard.services import generate_otp

    otp_clair, otp_hash, expires_at = generate_otp()
    assert re.match(r"^\d{6}$", otp_clair)
    assert otp_hash.startswith("$2b$") or otp_hash.startswith("$2a$")  # bcrypt prefix
    assert expires_at > timezone.now()
    assert expires_at <= timezone.now() + timedelta(minutes=11)


def test_verify_otp_correct():
    from onboard.services import generate_otp, verify_otp

    clair, otp_hash, _ = generate_otp()
    assert verify_otp(clair, otp_hash) is True


def test_verify_otp_wrong():
    from onboard.services import generate_otp, verify_otp

    _, otp_hash, _ = generate_otp()
    assert verify_otp("000000", otp_hash) is False


def test_verify_otp_empty_hash_returns_false():
    from onboard.services import verify_otp

    assert verify_otp("123456", "") is False
```

- [ ] **Step 2 : Vérifier que les tests échouent**

Run: `docker exec lespass_django poetry run pytest onboard/tests/test_services_otp.py -v`
Expected: `ImportError`.

- [ ] **Step 3 : Implémenter `onboard/services.py`**

```python
"""
Services synchrones de l'app onboard.
Pour les tasks asynchrones (Celery), voir onboard/tasks.py.
/ Synchronous helpers for the onboard app.
Async Celery tasks live in onboard/tasks.py.

LOCALISATION: onboard/services.py
"""

import hashlib
import logging
import secrets
from datetime import timedelta

import bcrypt
import requests
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)


# === OTP ===

OTP_TTL = timedelta(minutes=10)


def generate_otp():
    """
    Genere un code OTP a 6 chiffres et son hash bcrypt.
    Renvoie (otp_clair, otp_hash, expires_at).
    Le clair doit etre envoye dans le mail ; seul le hash est stocke en DB.
    / Generate a 6-digit OTP + its bcrypt hash.
    Returns (otp_clair, otp_hash, expires_at).
    Plain code goes in the email ; only the hash is persisted.
    """
    otp_clair = f"{secrets.randbelow(1_000_000):06d}"
    otp_hash = bcrypt.hashpw(otp_clair.encode(), bcrypt.gensalt(rounds=10)).decode()
    expires_at = timezone.now() + OTP_TTL
    return otp_clair, otp_hash, expires_at


def verify_otp(saisi, otp_hash):
    """
    Verifie un code OTP saisi contre le hash bcrypt stocke.
    Retour : True si match, False sinon (y compris si hash vide).
    / Verify a submitted OTP against the stored bcrypt hash.
    Returns True on match, False otherwise (including empty hash).
    """
    if not otp_hash:
        return False
    try:
        return bcrypt.checkpw(saisi.encode(), otp_hash.encode())
    except (ValueError, TypeError):
        # Hash invalide / Invalid hash format
        return False
```

- [ ] **Step 4 : Vérifier**

Run: `docker exec lespass_django poetry run pytest onboard/tests/test_services_otp.py -v`
Expected: 4 PASS.

- [ ] **Step 5 : Commit**

```bash
git add onboard/services.py onboard/tests/test_services_otp.py
git commit -m "feat(onboard): add generate_otp/verify_otp services with bcrypt"
```

---

### Task 5 : Service `geocode` (proxy Nominatim avec cache Redis)

**Files:**
- Modify: `onboard/services.py` (append)
- Create: `onboard/tests/test_services_geocode.py`

- [ ] **Step 1 : Tests `geocode`**

```python
"""
Tests du proxy Nominatim.
/ Tests for the Nominatim geocode proxy.

LOCALISATION: onboard/tests/test_services_geocode.py
"""

from unittest.mock import patch, MagicMock

import pytest


def test_geocode_returns_lat_lng_on_success():
    from onboard.services import geocode

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = [
        {"lat": "48.8566", "lon": "2.3522", "display_name": "Paris, France"}
    ]
    with patch("onboard.services.requests.get", return_value=fake_response):
        result = geocode("Tour Eiffel, Paris")

    assert result == {
        "latitude": 48.8566,
        "longitude": 2.3522,
        "display_name": "Paris, France",
    }


def test_geocode_returns_none_when_no_result():
    from onboard.services import geocode

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = []
    with patch("onboard.services.requests.get", return_value=fake_response):
        result = geocode("Adresse inexistante xyz123")
    assert result is None


def test_geocode_returns_none_on_timeout():
    from onboard.services import geocode

    import requests
    with patch("onboard.services.requests.get", side_effect=requests.Timeout):
        result = geocode("Paris")
    assert result is None


def test_geocode_uses_cache_on_second_call(settings):
    from onboard.services import geocode
    from django.core.cache import cache
    cache.clear()

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = [
        {"lat": "1.0", "lon": "2.0", "display_name": "X"}
    ]
    with patch("onboard.services.requests.get", return_value=fake_response) as mock_get:
        geocode("Cache me")
        geocode("Cache me")  # 2e appel
        # Le mock n'a ete appele qu'1 fois grace au cache.
        # / The mock was called only once thanks to the cache.
        assert mock_get.call_count == 1
```

- [ ] **Step 2 : Vérifier que les tests échouent**

Run: `docker exec lespass_django poetry run pytest onboard/tests/test_services_geocode.py -v`
Expected: `ImportError` pour `geocode`.

- [ ] **Step 3 : Ajouter `geocode` dans `onboard/services.py`**

Append à la fin de `onboard/services.py` :

```python
# === Geocode Nominatim ===

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_USER_AGENT = "TiBillet-Onboard/1.0 (contact@tibillet.coop)"
NOMINATIM_TIMEOUT = 5  # seconds
GEOCODE_CACHE_TTL = 24 * 60 * 60  # 24h


def _geocode_cache_key(query):
    # SHA256 pour rester court et eviter les caracteres exotiques.
    # / SHA256 for short key and no exotic chars.
    h = hashlib.sha256(query.encode("utf-8")).hexdigest()
    return f"onboard:geocode:{h[:32]}"


def geocode(query):
    """
    Resout une adresse texte vers (latitude, longitude, display_name).
    Cache Redis 24h sur le hash de la query.
    Retourne None si pas de resultat, timeout, ou erreur reseau.
    / Resolve a text address to (latitude, longitude, display_name).
    Redis-cached 24h via query hash. Returns None on no result/timeout/error.
    """
    if not query or len(query.strip()) < 3:
        return None

    cache_key = _geocode_cache_key(query)
    cached = cache.get(cache_key)
    if cached is not None:
        # cached peut etre dict OU sentinel "no-result"
        return cached if cached != "no-result" else None

    try:
        response = requests.get(
            NOMINATIM_URL,
            params={"q": query, "format": "json", "limit": 1},
            headers={"User-Agent": NOMINATIM_USER_AGENT},
            timeout=NOMINATIM_TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.warning("Nominatim error for query %r : %s", query, exc)
        return None

    if response.status_code != 200:
        logger.warning("Nominatim status %d for %r", response.status_code, query)
        return None

    results = response.json()
    if not results:
        # On cache aussi les "pas de resultat" pour ne pas re-frapper Nominatim.
        # / Cache no-result too so we don't hammer Nominatim.
        cache.set(cache_key, "no-result", GEOCODE_CACHE_TTL)
        return None

    first = results[0]
    payload = {
        "latitude": float(first["lat"]),
        "longitude": float(first["lon"]),
        "display_name": first.get("display_name", ""),
    }
    cache.set(cache_key, payload, GEOCODE_CACHE_TTL)
    return payload
```

- [ ] **Step 4 : Tests passent**

Run: `docker exec lespass_django poetry run pytest onboard/tests/test_services_geocode.py -v`
Expected: 4 PASS.

- [ ] **Step 5 : Commit**

```bash
git add onboard/services.py onboard/tests/test_services_geocode.py
git commit -m "feat(onboard): add geocode service (Nominatim proxy + 24h Redis cache)"
```

---

### Task 6 : Celery tasks — `onboard_otp_mailer` et `onboard_ready_mailer`

**Files:**
- Create: `onboard/tasks.py`
- Create: `onboard/tests/test_tasks_mailers.py`

- [ ] **Step 1 : Tests des mailers**

```python
"""
Tests des tasks Celery onboard_otp_mailer + onboard_ready_mailer.
/ Tests for OTP and ready mailer Celery tasks.

LOCALISATION: onboard/tests/test_tasks_mailers.py
"""

from unittest.mock import patch

import pytest
from django.core import mail
from django_tenants.utils import schema_context

from MetaBillet.models import WaitingConfiguration


@pytest.mark.django_db
def test_onboard_otp_mailer_sends_email():
    from onboard.tasks import onboard_otp_mailer

    with schema_context("meta"):
        wc = WaitingConfiguration.objects.create(
            organisation="Test",
            email="user@example.com",
            dns_choice="tibillet.coop",
        )
        wc_uuid = str(wc.uuid)

    mail.outbox = []
    onboard_otp_mailer(wc_uuid=wc_uuid, otp_clair="123456")

    assert len(mail.outbox) == 1
    sent = mail.outbox[0]
    assert sent.to == ["user@example.com"]
    assert "123456" in sent.body


@pytest.mark.django_db
def test_onboard_ready_mailer_sends_email_with_admin_link():
    from onboard.tasks import onboard_ready_mailer
    from Customers.models import Client

    with schema_context("meta"):
        wc = WaitingConfiguration.objects.create(
            organisation="Test ready",
            email="ready@example.com",
            dns_choice="tibillet.coop",
        )
        # Simuler la fin de creation : on attache un tenant existant.
        tenant = Client.objects.exclude(categorie=Client.ROOT).first()
        wc.tenant = tenant
        wc.save()
        wc_uuid = str(wc.uuid)

    mail.outbox = []
    onboard_ready_mailer(wc_uuid=wc_uuid)

    assert len(mail.outbox) == 1
    sent = mail.outbox[0]
    assert sent.to == ["ready@example.com"]
    domain = tenant.get_primary_domain().domain
    assert domain in sent.body
```

- [ ] **Step 2 : Tests échouent**

Run: `docker exec lespass_django poetry run pytest onboard/tests/test_tasks_mailers.py -v`
Expected: `ImportError`.

- [ ] **Step 3 : Implémenter `onboard/tasks.py`**

```python
"""
Tasks Celery de l'app onboard.
/ Celery tasks for the onboard app.

LOCALISATION: onboard/tasks.py
"""

import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.translation import gettext as _
from django_tenants.utils import schema_context, tenant_context

from Customers.models import Client
from MetaBillet.models import WaitingConfiguration

logger = logging.getLogger(__name__)


@shared_task(name="onboard.tasks.onboard_otp_mailer")
def onboard_otp_mailer(wc_uuid, otp_clair):
    """
    Envoie l'email contenant le code OTP a saisir dans le wizard.
    / Send the email containing the OTP code to enter in the wizard.

    Le code clair n'est jamais persiste cote serveur (cf. otp_hash en DB).
    / The plain code is never persisted server-side.
    """
    with schema_context("meta"):
        wc = WaitingConfiguration.objects.get(uuid=wc_uuid)

    subject = _("Your TiBillet verification code: %(code)s") % {"code": otp_clair}
    text_body = render_to_string(
        "onboard/emails/otp_code.txt",
        {"otp": otp_clair, "wc": wc},
    )
    html_body = render_to_string(
        "onboard/emails/otp_code.html",
        {"otp": otp_clair, "wc": wc},
    )

    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@tibillet.coop"),
        to=[wc.email],
    )
    msg.attach_alternative(html_body, "text/html")
    msg.send(fail_silently=False)
    logger.info("OTP mail sent to %s for WC %s", wc.email, wc_uuid)


@shared_task(name="onboard.tasks.onboard_ready_mailer")
def onboard_ready_mailer(wc_uuid):
    """
    Envoie l'email "Votre espace est pret" apres la creation du tenant.
    Au cas ou l'utilisateur a ferme l'onglet avant la fin de la task.
    / Send the "Your space is ready" email after tenant creation,
    in case the user closed the tab before the async task finished.
    """
    with schema_context("meta"):
        wc = WaitingConfiguration.objects.select_related("tenant").get(uuid=wc_uuid)

    if not wc.tenant:
        logger.warning("ready_mailer called but WC %s has no tenant", wc_uuid)
        return

    primary_domain = wc.tenant.get_primary_domain().domain
    admin_url = f"https://{primary_domain}/admin/"

    subject = _("Your TiBillet space %(name)s is ready!") % {"name": wc.organisation}
    text_body = render_to_string(
        "onboard/emails/ready.txt",
        {"wc": wc, "admin_url": admin_url},
    )
    html_body = render_to_string(
        "onboard/emails/ready.html",
        {"wc": wc, "admin_url": admin_url},
    )

    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@tibillet.coop"),
        to=[wc.email],
    )
    msg.attach_alternative(html_body, "text/html")
    msg.send(fail_silently=False)
    logger.info("Ready mail sent to %s for tenant %s", wc.email, primary_domain)
```

- [ ] **Step 4 : Templates email (4 fichiers très simples)**

Create `onboard/templates/onboard/emails/otp_code.txt` :

```
{% load i18n %}{% blocktranslate %}Hello,

Your verification code to create your TiBillet space is:

{{ otp }}

It expires in 10 minutes.

If you did not request this, you can ignore this email.

— The TiBillet team{% endblocktranslate %}
```

Create `onboard/templates/onboard/emails/otp_code.html` :

```html
{% load i18n %}
<html><body style="font-family:system-ui,sans-serif">
<p>{% translate "Hello," %}</p>
<p>{% translate "Your verification code to create your TiBillet space is:" %}</p>
<p style="font-size:32px;font-weight:700;letter-spacing:8px;text-align:center;background:#f0f0f0;padding:16px;border-radius:8px">{{ otp }}</p>
<p>{% translate "It expires in 10 minutes." %}</p>
<p style="color:#666;font-size:13px">{% translate "If you did not request this, you can ignore this email." %}</p>
<p>— {% translate "The TiBillet team" %}</p>
</body></html>
```

Create `onboard/templates/onboard/emails/ready.txt` :

```
{% load i18n %}{% blocktranslate with name=wc.organisation %}Hello,

Your TiBillet space "{{ name }}" is ready!

Access your admin: {{ admin_url }}

You can now configure your modules, connect Stripe to start selling tickets, and publish your first events.

— The TiBillet team{% endblocktranslate %}
```

Create `onboard/templates/onboard/emails/ready.html` :

```html
{% load i18n %}
<html><body style="font-family:system-ui,sans-serif">
<p>{% translate "Hello," %}</p>
<p>{% blocktranslate with name=wc.organisation %}Your TiBillet space "{{ name }}" is ready!{% endblocktranslate %}</p>
<p><a href="{{ admin_url }}" style="background:#22c55e;color:#fff;padding:12px 24px;border-radius:6px;text-decoration:none">{% translate "Access your admin" %}</a></p>
<p style="color:#666;font-size:13px">{% translate "You can configure your modules, connect Stripe, and publish your first events." %}</p>
<p>— {% translate "The TiBillet team" %}</p>
</body></html>
```

- [ ] **Step 5 : Tests passent**

Run: `docker exec lespass_django poetry run pytest onboard/tests/test_tasks_mailers.py -v`
Expected: 2 PASS.

- [ ] **Step 6 : Commit**

```bash
git add onboard/tasks.py onboard/templates/onboard/emails/ onboard/tests/test_tasks_mailers.py
git commit -m "feat(onboard): add OTP + ready Celery mailers with email templates"
```

---

### Task 7 : Task `create_tenant_from_draft` (le cœur asynchrone)

**Files:**
- Modify: `onboard/tasks.py` (append)
- Create: `onboard/tests/test_create_tenant_task.py`

- [ ] **Step 1 : Tests de la task**

```python
"""
Tests de la task Celery create_tenant_from_draft.
/ Tests for the create_tenant_from_draft Celery task.

LOCALISATION: onboard/tests/test_create_tenant_task.py
"""

from unittest.mock import patch

import pytest
from django_tenants.utils import schema_context

from Customers.models import Client
from AuthBillet.models import TibilletUser
from MetaBillet.models import WaitingConfiguration


@pytest.mark.django_db
def test_create_tenant_from_draft_consumes_pool_slot():
    """Apres la task, wc.tenant est rempli avec un Client recategorise."""
    from onboard.tasks import create_tenant_from_draft

    with schema_context("meta"):
        wc = WaitingConfiguration.objects.create(
            organisation="Mon Lieu",
            email="user@example.com",
            dns_choice="tibillet.coop",
            email_confirmed=True,
        )
        uuid_str = str(wc.uuid)

    create_tenant_from_draft(wc_uuid=uuid_str)

    with schema_context("meta"):
        wc.refresh_from_db()
        assert wc.tenant is not None
        assert wc.tenant.categorie != Client.WAITING_CONFIG


@pytest.mark.django_db
def test_create_tenant_from_draft_is_idempotent():
    """2 appels successifs ne creent pas 2 tenants."""
    from onboard.tasks import create_tenant_from_draft

    with schema_context("meta"):
        wc = WaitingConfiguration.objects.create(
            organisation="Idem", email="idem@example.com",
            dns_choice="tibillet.coop", email_confirmed=True,
        )
        uuid_str = str(wc.uuid)

    create_tenant_from_draft(wc_uuid=uuid_str)
    with schema_context("meta"):
        wc.refresh_from_db()
        first_tenant_id = wc.tenant_id

    create_tenant_from_draft(wc_uuid=uuid_str)
    with schema_context("meta"):
        wc.refresh_from_db()
        assert wc.tenant_id == first_tenant_id  # pas re-cree


@pytest.mark.django_db
def test_create_tenant_from_draft_writes_error_when_no_pool():
    """Si pool vide, wc.error_message est rempli, pas d'exception non geree."""
    from onboard.tasks import create_tenant_from_draft

    with schema_context("meta"):
        # Vider le pool
        Client.objects.filter(categorie=Client.WAITING_CONFIG).delete()
        wc = WaitingConfiguration.objects.create(
            organisation="No pool", email="np@example.com",
            dns_choice="tibillet.coop", email_confirmed=True,
        )
        uuid_str = str(wc.uuid)

    create_tenant_from_draft(wc_uuid=uuid_str)

    with schema_context("meta"):
        wc.refresh_from_db()
        assert wc.tenant is None
        assert "pool" in wc.error_message.lower() or "slot" in wc.error_message.lower()


@pytest.mark.django_db
def test_create_tenant_from_draft_calls_ready_mailer_on_success():
    """La task envoie l'email "espace pret" a la fin."""
    from onboard.tasks import create_tenant_from_draft

    with schema_context("meta"):
        wc = WaitingConfiguration.objects.create(
            organisation="Mail test", email="mail@example.com",
            dns_choice="tibillet.coop", email_confirmed=True,
        )
        uuid_str = str(wc.uuid)

    with patch("onboard.tasks.onboard_ready_mailer.delay") as mock_mailer:
        create_tenant_from_draft(wc_uuid=uuid_str)
        mock_mailer.assert_called_once_with(wc_uuid=uuid_str)


@pytest.mark.django_db
def test_create_tenant_from_draft_attaches_to_invitation_federation():
    """Si wc.invitation existe, le tenant rejoint federation.tenants direct."""
    from onboard.tasks import create_tenant_from_draft
    from onboard.models import OnboardInvitation
    from fedow_core.models import Federation

    user = TibilletUser.objects.first()
    inviting_tenant = Client.objects.exclude(categorie=Client.ROOT).first()
    fed = Federation.objects.create(name="Test fed", created_by=user)

    with schema_context("meta"):
        inv = OnboardInvitation.objects.create(
            federation=fed, invited_by_user=user, invited_by_tenant=inviting_tenant,
        )
        wc = WaitingConfiguration.objects.create(
            organisation="Invité", email="inv@example.com",
            dns_choice="tibillet.coop", email_confirmed=True,
            invitation=inv,
        )
        uuid_str = str(wc.uuid)

    create_tenant_from_draft(wc_uuid=uuid_str)

    with schema_context("meta"):
        wc.refresh_from_db()
        inv.refresh_from_db()
        fed.refresh_from_db()
        assert wc.tenant in fed.tenants.all()
        assert wc.tenant not in fed.pending_tenants.all()
        assert inv.used_at is not None
        assert inv.used_by_drafts.filter(uuid=wc.uuid).exists()
```

- [ ] **Step 2 : Tests échouent**

Run: `docker exec lespass_django poetry run pytest onboard/tests/test_create_tenant_task.py -v`
Expected: `ImportError`.

- [ ] **Step 3 : Implémenter `create_tenant_from_draft` dans `onboard/tasks.py`** (append)

```python
@shared_task(
    name="onboard.tasks.create_tenant_from_draft",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=120,
    max_retries=3,
)
def create_tenant_from_draft(self, wc_uuid):
    """
    Cree le tenant final a partir d'une WaitingConfiguration finalisee.
    Idempotent : si wc.tenant est deja rempli, retourne immediatement.
    En cas d'echec apres 3 retries, ecrit l'erreur dans wc.error_message.
    / Create the final tenant from a finalized WaitingConfiguration.
    Idempotent: returns early if wc.tenant is already set.
    On 3-retry failure, writes the error in wc.error_message.
    """
    from django.db import transaction

    with schema_context("meta"):
        # Verrou pour eviter qu'une 2e task parallele cree un 2e tenant
        # / Lock to prevent a parallel task creating a second tenant
        with transaction.atomic():
            wc = WaitingConfiguration.objects.select_for_update().get(uuid=wc_uuid)
            if wc.tenant_id is not None:
                # Deja cree, idempotence garantie / Already created
                logger.info("create_tenant_from_draft: WC %s already has tenant, skipping", wc_uuid)
                return

        # 1. Pool check / Pool check
        pool_count = Client.objects.filter(categorie=Client.WAITING_CONFIG).count()
        if pool_count == 0:
            wc.error_message = (
                "No empty tenant slot available in the pool. "
                "An admin needs to run create_empty_tenant. "
                "/ Pas de slot disponible dans le pool. Un admin doit lancer "
                "create_empty_tenant."
            )
            wc.save(update_fields=["error_message"])
            logger.error("create_tenant_from_draft: no pool slot for WC %s", wc_uuid)
            return

    # 2. Creation du tenant via la chaine existante
    # / Tenant creation via existing chain
    try:
        new_tenant = wc.create_tenant()  # methode existante de WaitingConfiguration
    except Exception as exc:
        with schema_context("meta"):
            wc.refresh_from_db()
            wc.error_message = f"create_tenant() raised: {exc}"
            wc.save(update_fields=["error_message"])
        raise  # retry via autoretry_for

    # 3. Application des events draft dans le schema du nouveau tenant
    # / Apply draft events into the new tenant schema
    with tenant_context(new_tenant):
        from BaseBillet.models import Event
        for ev in wc.events_draft or []:
            try:
                Event.objects.create(
                    name=ev.get("name", "Sans titre")[:200],
                    datetime=ev.get("datetime"),
                    short_description=ev.get("description", "")[:280],
                    published=False,  # admin relit avant publication
                )
            except Exception as exc:
                logger.warning("Skipping event draft for WC %s: %s", wc_uuid, exc)

    # 4. Federation : si invitation, ajout direct dans tenants
    # / Federation: if invitation, add directly to tenants
    if wc.invitation_id:
        with schema_context("meta"):
            wc.refresh_from_db()
            inv = wc.invitation
        # La Federation est en SHARED, on opere en schema public sans tenant_context
        # / Federation is SHARED, we run in public schema
        from django.utils import timezone
        from django.db import connection
        with schema_context("public"):
            fed = inv.federation
            fed.tenants.add(new_tenant)
            inv.used_at = timezone.now()
            inv.save(update_fields=["used_at"])

    # 5. Email "espace pret" / Ready email
    onboard_ready_mailer.delay(wc_uuid=wc_uuid)
    logger.info("create_tenant_from_draft: success for WC %s → %s", wc_uuid, new_tenant.schema_name)
```

- [ ] **Step 4 : Tests passent**

Run: `docker exec lespass_django poetry run pytest onboard/tests/test_create_tenant_task.py -v`
Expected: 5 PASS.

- [ ] **Step 5 : Commit**

```bash
git add onboard/tasks.py onboard/tests/test_create_tenant_task.py
git commit -m "feat(onboard): add create_tenant_from_draft Celery task with retry + idempotence"
```

---

### Task 8 : Task `purge_stale_onboard_drafts` + Celery beat

**Files:**
- Modify: `onboard/tasks.py` (append)
- Modify: `TiBillet/celery.py` (ajouter au CELERY_BEAT_SCHEDULE) ou équivalent
- Create: `onboard/tests/test_purge_task.py`

- [ ] **Step 1 : Test**

```python
"""
Test de la task purge_stale_onboard_drafts.
/ Test for purge_stale_onboard_drafts.

LOCALISATION: onboard/tests/test_purge_task.py
"""

from datetime import timedelta

import pytest
from django.utils import timezone
from django_tenants.utils import schema_context

from MetaBillet.models import WaitingConfiguration


@pytest.mark.django_db
def test_purge_removes_old_unfinalized_drafts():
    from onboard.tasks import purge_stale_onboard_drafts

    with schema_context("meta"):
        old = WaitingConfiguration.objects.create(
            organisation="Old", email="old@x.com", dns_choice="tibillet.coop",
        )
        # Forcer une date ancienne via update (created_at = auto_now_add)
        WaitingConfiguration.objects.filter(uuid=old.uuid).update(
            created_at=timezone.now() - timedelta(days=31),
        )
        recent = WaitingConfiguration.objects.create(
            organisation="Recent", email="recent@x.com", dns_choice="tibillet.coop",
        )

    deleted = purge_stale_onboard_drafts()

    with schema_context("meta"):
        assert not WaitingConfiguration.objects.filter(uuid=old.uuid).exists()
        assert WaitingConfiguration.objects.filter(uuid=recent.uuid).exists()
    assert deleted >= 1
```

- [ ] **Step 2 : Implémenter** (append à `onboard/tasks.py`)

```python
@shared_task(name="onboard.tasks.purge_stale_onboard_drafts")
def purge_stale_onboard_drafts(ttl_days=30):
    """
    Supprime les brouillons de wizard non finalises (sans tenant) plus
    vieux que ttl_days jours. Appele par Celery beat (hebdomadaire).
    / Delete unfinalized wizard drafts (no tenant) older than ttl_days.
    Called by Celery beat (weekly).
    """
    from datetime import timedelta
    from django.utils import timezone

    threshold = timezone.now() - timedelta(days=ttl_days)
    with schema_context("meta"):
        qs = WaitingConfiguration.objects.filter(
            tenant__isnull=True,
            created_at__lt=threshold,
        )
        count = qs.count()
        qs.delete()
    logger.info("purge_stale_onboard_drafts: deleted %d stale drafts (older than %d days)", count, ttl_days)
    return count
```

- [ ] **Step 3 : Ajouter au Celery beat**

Localiser le fichier qui contient `CELERY_BEAT_SCHEDULE` ou `app.conf.beat_schedule` (probablement `TiBillet/celery.py`) et ajouter :

```python
"onboard_purge_stale_drafts": {
    "task": "onboard.tasks.purge_stale_onboard_drafts",
    "schedule": crontab(day_of_week=1, hour=3, minute=0),  # Lundi 3h UTC
},
```

(Si `crontab` n'est pas déjà importé, ajouter `from celery.schedules import crontab`.)

- [ ] **Step 4 : Test passe**

Run: `docker exec lespass_django poetry run pytest onboard/tests/test_purge_task.py -v`

- [ ] **Step 5 : Commit**

```bash
git add onboard/tasks.py onboard/tests/test_purge_task.py TiBillet/celery.py
git commit -m "feat(onboard): add purge_stale_onboard_drafts Celery beat task"
```

---

## Phase C — ViewSet wizard (steps + status + resume)

### Task 9 : `OnboardViewSet` squelette + URLs + helpers session

**Files:**
- Create: `onboard/views.py`
- Create: `onboard/urls.py`
- Modify: `TiBillet/urls.py` (include `onboard/urls.py`)

- [ ] **Step 1 : `onboard/urls.py`**

```python
"""
URLs de l'app onboard.
/ URLs for the onboard app.

LOCALISATION: onboard/urls.py
"""

from rest_framework.routers import DefaultRouter

from onboard.views import OnboardViewSet

router = DefaultRouter()
router.register(r"onboard", OnboardViewSet, basename="onboard")

urlpatterns = router.urls
```

- [ ] **Step 2 : `onboard/views.py` (squelette + helpers)**

```python
"""
Vues du wizard d'onboarding.
/ Onboarding wizard views.

LOCALISATION: onboard/views.py

ViewSet DRF explicite (pas ModelViewSet) : chaque etape est une @action,
nommee par l'URL qu'elle expose. Cf. djc / stack-ccc guidelines.
"""

import logging

from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django_tenants.utils import schema_context
from rest_framework import permissions, viewsets
from rest_framework.decorators import action

from MetaBillet.models import WaitingConfiguration

logger = logging.getLogger(__name__)

SESSION_KEY = "onboard_wc_uuid"


def _get_or_none_wc(request):
    """
    Lit l'UUID de WC depuis la session, renvoie le WC ou None.
    / Read WC uuid from session, return WC or None.
    """
    wc_uuid = request.session.get(SESSION_KEY)
    if not wc_uuid:
        return None
    with schema_context("meta"):
        try:
            return WaitingConfiguration.objects.get(uuid=wc_uuid)
        except WaitingConfiguration.DoesNotExist:
            return None


def _set_session_wc(request, wc):
    request.session[SESSION_KEY] = str(wc.uuid)
    request.session.modified = True


def _clear_session_wc(request):
    request.session.pop(SESSION_KEY, None)
    request.session.modified = True


class OnboardViewSet(viewsets.ViewSet):
    """
    Wizard d'onboarding nouveau tenant en 6 etapes.
    Toutes les actions sont en SHARED — accessibles depuis ROOT et tenants.
    / 6-step onboarding wizard for new tenants.
    All actions are SHARED — reachable from ROOT and any tenant.
    """

    permission_classes = [permissions.AllowAny]

    @action(detail=False, methods=["GET"], url_path="")
    def root(self, request):
        """
        GET /onboard/ — redirige vers la step courante du brouillon,
        ou /onboard/identity/ si pas de brouillon.
        / Redirect to current step of draft, or /identity/ if no draft.
        """
        wc = _get_or_none_wc(request)
        if wc is None:
            return redirect("onboard-identity")
        return redirect(f"onboard-{wc.current_step}")
```

- [ ] **Step 3 : Inclure dans `TiBillet/urls.py`**

Localiser `TiBillet/urls.py` et ajouter dans `urlpatterns` :

```python
path("", include("onboard.urls")),
```

- [ ] **Step 4 : Vérifier**

Run: `docker exec lespass_django poetry run python /DjangoFiles/manage.py check`
Expected: 0 issues.

Run: `curl -sI http://lespass.tibillet.localhost:8002/onboard/ | head -3`
Expected: HTTP 302 redirect.

- [ ] **Step 5 : Commit**

```bash
git add onboard/views.py onboard/urls.py TiBillet/urls.py
git commit -m "feat(onboard): scaffold OnboardViewSet with root redirect"
```

---

### Task 10 : Step 1 — Identity (serializer + view + invitation handling)

**Files:**
- Create: `onboard/serializers.py`
- Modify: `onboard/views.py` (append @action identity + create_identity)
- Create: `onboard/tests/test_step_identity.py`

- [ ] **Step 1 : Test**

```python
"""
Tests step 1 — identity.
LOCALISATION: onboard/tests/test_step_identity.py
"""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from django_tenants.utils import schema_context

from MetaBillet.models import WaitingConfiguration


@pytest.mark.django_db
def test_identity_get_renders_form():
    client = APIClient()
    response = client.get("/onboard/identity/")
    assert response.status_code == 200
    assert b"Cr" in response.content  # contient "Créer"/"Create" titre


@pytest.mark.django_db
def test_identity_post_creates_wc_and_redirects_to_verify():
    client = APIClient()
    response = client.post("/onboard/identity/", data={
        "email": "new@example.com",
        "email_confirm": "new@example.com",
        "first_name": "Jonas",
        "last_name": "Test",
        "name": "Mon Lieu",
        "dns_choice": "tibillet.coop",
        "cgu": "on",
    })
    assert response.status_code in (302, 303)
    with schema_context("meta"):
        wc = WaitingConfiguration.objects.filter(email="new@example.com").first()
    assert wc is not None
    assert wc.current_step == "verify"
    assert wc.otp_hash != ""
    assert wc.email_confirmed is False


@pytest.mark.django_db
def test_identity_post_with_invitation_attaches_it():
    from onboard.models import OnboardInvitation
    from fedow_core.models import Federation
    from Customers.models import Client
    from AuthBillet.models import TibilletUser

    user = TibilletUser.objects.first()
    inviting = Client.objects.exclude(categorie=Client.ROOT).first()
    fed = Federation.objects.create(name="Fed inv", created_by=user)
    with schema_context("meta"):
        inv = OnboardInvitation.objects.create(
            federation=fed, invited_by_user=user, invited_by_tenant=inviting,
        )

    client = APIClient()
    response = client.post(f"/onboard/identity/?invite={inv.code}", data={
        "email": "inv@example.com",
        "email_confirm": "inv@example.com",
        "first_name": "I",
        "last_name": "N",
        "name": "Lieu invité",
        "dns_choice": "tibillet.coop",
        "cgu": "on",
    })
    assert response.status_code in (302, 303)
    with schema_context("meta"):
        wc = WaitingConfiguration.objects.filter(email="inv@example.com").first()
    assert wc.invitation_id is not None
    assert wc.invitation.code == inv.code
```

- [ ] **Step 2 : Serializer**

Create `onboard/serializers.py` :

```python
"""
Serializers DRF du wizard d'onboarding.
/ DRF serializers for the onboarding wizard.

LOCALISATION: onboard/serializers.py

1 serializer par etape — validation explicite, pas de ModelSerializer.
/ One serializer per step — explicit validation, no ModelSerializer.
"""

import re

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers


DNS_CHOICES = ("tibillet.coop", "tibillet.re", "tibillet.fr")


class OnboardIdentitySerializer(serializers.Serializer):
    """
    Step 1 : email + confirmation + identite + nom du lieu + DNS + CGU.
    """
    email = serializers.EmailField(required=True)
    email_confirm = serializers.EmailField(required=True)
    first_name = serializers.CharField(max_length=60, required=True, allow_blank=False)
    last_name = serializers.CharField(max_length=60, required=True, allow_blank=False)
    name = serializers.CharField(max_length=120, required=True, allow_blank=False)
    dns_choice = serializers.ChoiceField(choices=DNS_CHOICES, default="tibillet.coop")
    cgu = serializers.BooleanField(required=True)

    def validate_cgu(self, value):
        if not value:
            raise serializers.ValidationError(_("You must accept the terms."))
        return value

    def validate_name(self, value):
        if len(value.strip()) < 3:
            raise serializers.ValidationError(_("Name must be at least 3 characters."))
        return value.strip()

    def validate(self, attrs):
        if attrs["email"].lower() != attrs["email_confirm"].lower():
            raise serializers.ValidationError({"email_confirm": _("Emails do not match.")})
        return attrs


class OnboardVerifySerializer(serializers.Serializer):
    """Step 2 : OTP 6 chiffres."""
    otp = serializers.RegexField(regex=r"^\d{6}$", required=True)


class OnboardPlaceSerializer(serializers.Serializer):
    """Step 3 : adresse + GPS + short description."""
    street_address = serializers.CharField(max_length=255, required=True)
    postal_code = serializers.CharField(max_length=20, required=True)
    address_locality = serializers.CharField(max_length=120, required=True)
    address_country = serializers.CharField(max_length=80, required=True)
    short_description = serializers.CharField(max_length=280, required=True)
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=True,
                                        min_value=-90, max_value=90)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=True,
                                         min_value=-180, max_value=180)


class OnboardDescriptionsSerializer(serializers.Serializer):
    """Step 4 : long description + logo (file)."""
    long_description = serializers.CharField(max_length=5000, required=True)
    logo = serializers.ImageField(required=False, allow_null=True)


class OnboardEventDraftSerializer(serializers.Serializer):
    """Sous-form : 1 event draft."""
    name = serializers.CharField(max_length=200, required=True)
    datetime = serializers.DateTimeField(required=True)
    description = serializers.CharField(max_length=2000, required=False, allow_blank=True)
```

- [ ] **Step 3 : Ajouter les actions GET et POST identity dans `onboard/views.py`**

Append à `OnboardViewSet` :

```python
    # === Step 1 — Identity ===

    @action(detail=False, methods=["GET", "POST"], url_path="identity")
    def identity(self, request):
        wc = _get_or_none_wc(request)

        # Lecture eventuelle d'un code d'invitation en query string
        # / Optionally read invitation code from query string
        invite_code = request.GET.get("invite", "").strip()
        invitation = None
        if invite_code:
            from onboard.models import OnboardInvitation
            with schema_context("meta"):
                invitation = OnboardInvitation.objects.filter(code=invite_code).first()
            if invitation and not invitation.is_valid():
                invitation = None  # silencieux ; le user continue sans invitation

        if request.method == "GET":
            initial = {}
            if wc:
                initial = {
                    "email": wc.email, "first_name": wc.first_name,
                    "last_name": wc.last_name, "name": wc.organisation,
                    "dns_choice": wc.dns_choice,
                }
            return render(request, "onboard/steps/01_identity.html", {
                "step": "identity",
                "initial": initial,
                "invitation": invitation,
            })

        # POST
        from onboard.serializers import OnboardIdentitySerializer
        from onboard.services import generate_otp
        from onboard.tasks import onboard_otp_mailer

        serializer = OnboardIdentitySerializer(data=request.data)
        if not serializer.is_valid():
            return render(request, "onboard/steps/01_identity.html", {
                "step": "identity",
                "errors": serializer.errors,
                "initial": request.data.dict(),
                "invitation": invitation,
            }, status=422)

        data = serializer.validated_data

        # Cas user authentifie + email_valid : skip OTP
        # / Authenticated user + verified email: skip OTP
        skip_otp = (
            request.user.is_authenticated
            and getattr(request.user, "email_valid", False)
            and request.user.email.lower() == data["email"].lower()
        )

        with schema_context("meta"):
            wc = WaitingConfiguration.objects.create(
                organisation=data["name"],
                email=data["email"],
                dns_choice=data["dns_choice"],
                first_name=data["first_name"],
                last_name=data["last_name"],
                email_confirmed=skip_otp,
                current_step="place" if skip_otp else "verify",
                invitation=invitation,
            )
            if not skip_otp:
                otp_clair, otp_hash, expires_at = generate_otp()
                wc.otp_hash = otp_hash
                wc.otp_expires_at = expires_at
                wc.save(update_fields=["otp_hash", "otp_expires_at"])
                onboard_otp_mailer.delay(wc_uuid=str(wc.uuid), otp_clair=otp_clair)

        _set_session_wc(request, wc)
        return redirect("onboard-place" if skip_otp else "onboard-verify")
```

- [ ] **Step 4 : Tests passent**

Run: `docker exec lespass_django poetry run pytest onboard/tests/test_step_identity.py -v`
Expected: 3 PASS.

- [ ] **Step 5 : Commit**

```bash
git add onboard/serializers.py onboard/views.py onboard/tests/test_step_identity.py
git commit -m "feat(onboard): step 1 identity (form + serializer + OTP send + invitation)"
```

---

### Task 11 : Step 2 — Verify OTP + resend

**Files:**
- Modify: `onboard/views.py` (append)
- Create: `onboard/tests/test_step_verify.py`

- [ ] **Step 1 : Test**

```python
"""
Tests step 2 — verify OTP.
LOCALISATION: onboard/tests/test_step_verify.py
"""

import pytest
from unittest.mock import patch
from rest_framework.test import APIClient
from django_tenants.utils import schema_context

from MetaBillet.models import WaitingConfiguration


def _create_wc_with_otp(client_api, otp_clair="123456"):
    from onboard.services import generate_otp
    from django.utils import timezone
    from datetime import timedelta
    # Hash genere a partir d'un OTP fixe pour le test
    import bcrypt
    otp_hash = bcrypt.hashpw(otp_clair.encode(), bcrypt.gensalt(rounds=4)).decode()
    with schema_context("meta"):
        wc = WaitingConfiguration.objects.create(
            organisation="Verify", email="v@x.com", dns_choice="tibillet.coop",
            otp_hash=otp_hash,
            otp_expires_at=timezone.now() + timedelta(minutes=10),
            current_step="verify",
        )
    session = client_api.session
    session["onboard_wc_uuid"] = str(wc.uuid)
    session.save()
    return wc


@pytest.mark.django_db
def test_verify_correct_otp_passes_to_place():
    client = APIClient()
    wc = _create_wc_with_otp(client, "123456")
    response = client.post("/onboard/verify/", data={"otp": "123456"})
    assert response.status_code in (302, 303)
    with schema_context("meta"):
        wc.refresh_from_db()
    assert wc.email_confirmed is True
    assert wc.current_step == "place"


@pytest.mark.django_db
def test_verify_wrong_otp_increments_attempts():
    client = APIClient()
    wc = _create_wc_with_otp(client, "123456")
    response = client.post("/onboard/verify/", data={"otp": "999999"})
    assert response.status_code == 422
    with schema_context("meta"):
        wc.refresh_from_db()
    assert wc.otp_attempts == 1
    assert wc.email_confirmed is False


@pytest.mark.django_db
def test_verify_locks_after_5_attempts():
    client = APIClient()
    wc = _create_wc_with_otp(client, "123456")
    with schema_context("meta"):
        WaitingConfiguration.objects.filter(uuid=wc.uuid).update(otp_attempts=5)
    response = client.post("/onboard/verify/", data={"otp": "123456"})
    assert response.status_code == 422
    assert b"locked" in response.content.lower() or b"verrou" in response.content.lower()


@pytest.mark.django_db
def test_resend_otp_regenerates():
    client = APIClient()
    wc = _create_wc_with_otp(client, "111111")
    with patch("onboard.tasks.onboard_otp_mailer.delay") as mock:
        response = client.post("/onboard/resend-otp/")
    assert response.status_code == 200
    mock.assert_called_once()
```

- [ ] **Step 2 : Append à `onboard/views.py`**

```python
    # === Step 2 — Verify OTP ===

    @action(detail=False, methods=["GET", "POST"], url_path="verify")
    def verify(self, request):
        wc = _get_or_none_wc(request)
        if wc is None:
            return redirect("onboard-identity")

        if request.method == "GET":
            return render(request, "onboard/steps/02_verify.html", {
                "step": "verify",
                "email": wc.email,
            })

        from django.utils import timezone
        from onboard.serializers import OnboardVerifySerializer
        from onboard.services import verify_otp

        serializer = OnboardVerifySerializer(data=request.data)
        if not serializer.is_valid():
            return render(request, "onboard/steps/02_verify.html", {
                "step": "verify", "email": wc.email,
                "errors": serializer.errors,
            }, status=422)

        if wc.otp_attempts >= 5:
            return render(request, "onboard/steps/02_verify.html", {
                "step": "verify", "email": wc.email,
                "errors": {"otp": ["Account locked: too many wrong attempts. / Verrouille."]},
            }, status=422)

        if wc.otp_expires_at is None or wc.otp_expires_at < timezone.now():
            return render(request, "onboard/steps/02_verify.html", {
                "step": "verify", "email": wc.email,
                "errors": {"otp": ["OTP expired. / Code expire."]},
            }, status=422)

        if not verify_otp(serializer.validated_data["otp"], wc.otp_hash):
            with schema_context("meta"):
                WaitingConfiguration.objects.filter(uuid=wc.uuid).update(
                    otp_attempts=wc.otp_attempts + 1,
                )
            return render(request, "onboard/steps/02_verify.html", {
                "step": "verify", "email": wc.email,
                "errors": {"otp": ["Wrong code. / Code incorrect."]},
            }, status=422)

        # OK : email confirme
        with schema_context("meta"):
            WaitingConfiguration.objects.filter(uuid=wc.uuid).update(
                email_confirmed=True,
                current_step="place",
                otp_hash="",  # purge le hash apres usage
                otp_expires_at=None,
            )
        # Cree le TibilletUser si pas encore en base
        from AuthBillet.utils import get_or_create_user
        get_or_create_user(wc.email, send_mail=False)
        return redirect("onboard-place")

    @action(detail=False, methods=["POST"], url_path="resend-otp")
    def resend_otp(self, request):
        wc = _get_or_none_wc(request)
        if wc is None:
            return HttpResponse(status=404)

        # Rate-limit Redis : max 3 / h / IP
        # / Redis rate-limit: max 3 per hour per IP
        from django.core.cache import cache
        ip = request.META.get("REMOTE_ADDR", "unknown")
        key = f"onboard:resend:{ip}"
        count = cache.get(key, 0)
        if count >= 3:
            return render(request, "onboard/partials/resend_blocked.html", status=429)
        cache.set(key, count + 1, 3600)

        from onboard.services import generate_otp
        from onboard.tasks import onboard_otp_mailer

        otp_clair, otp_hash, expires_at = generate_otp()
        with schema_context("meta"):
            WaitingConfiguration.objects.filter(uuid=wc.uuid).update(
                otp_hash=otp_hash, otp_expires_at=expires_at, otp_attempts=0,
                otp_resend_count=wc.otp_resend_count + 1,
            )
        onboard_otp_mailer.delay(wc_uuid=str(wc.uuid), otp_clair=otp_clair)
        return render(request, "onboard/partials/resend_sent.html")
```

- [ ] **Step 3 : Tests passent**

Run: `docker exec lespass_django poetry run pytest onboard/tests/test_step_verify.py -v`
Expected: 4 PASS.

- [ ] **Step 4 : Commit**

```bash
git add onboard/views.py onboard/tests/test_step_verify.py
git commit -m "feat(onboard): step 2 verify OTP + resend (bcrypt, lock 5 tries, throttle 3/h)"
```

---

### Task 12 : Step 3 — Place (form + geocode endpoint)

**Files:**
- Modify: `onboard/views.py` (append)
- Create: `onboard/tests/test_step_place.py`

- [ ] **Step 1 : Test**

```python
"""
Tests step 3 — place + geocode endpoint.
LOCALISATION: onboard/tests/test_step_place.py
"""

from unittest.mock import patch
import pytest
from rest_framework.test import APIClient
from django_tenants.utils import schema_context

from MetaBillet.models import WaitingConfiguration


def _create_wc_at_place(client_api):
    with schema_context("meta"):
        wc = WaitingConfiguration.objects.create(
            organisation="P", email="p@x.com", dns_choice="tibillet.coop",
            email_confirmed=True, current_step="place",
        )
    session = client_api.session
    session["onboard_wc_uuid"] = str(wc.uuid)
    session.save()
    return wc


@pytest.mark.django_db
def test_place_post_saves_address_and_advances_to_descriptions():
    client = APIClient()
    wc = _create_wc_at_place(client)
    response = client.post("/onboard/place/", data={
        "street_address": "1 rue Test",
        "postal_code": "97400",
        "address_locality": "St Denis",
        "address_country": "Réunion",
        "short_description": "Lieu de test",
        "latitude": "-20.88",
        "longitude": "55.45",
    })
    assert response.status_code in (302, 303)
    with schema_context("meta"):
        wc.refresh_from_db()
    assert wc.current_step == "descriptions"
    assert float(wc.latitude) == pytest.approx(-20.88, rel=1e-3)


@pytest.mark.django_db
def test_geocode_endpoint_returns_partial_with_coords():
    client = APIClient()
    _create_wc_at_place(client)
    fake = {"latitude": 48.85, "longitude": 2.35, "display_name": "Paris"}
    with patch("onboard.views.geocode", return_value=fake):
        response = client.post("/onboard/geocode/", data={"query": "Paris"})
    assert response.status_code == 200
    assert b"48.85" in response.content
```

- [ ] **Step 2 : Append à `onboard/views.py`**

```python
    # === Step 3 — Place ===

    @action(detail=False, methods=["GET", "POST"], url_path="place")
    def place(self, request):
        wc = _get_or_none_wc(request)
        if wc is None or not wc.email_confirmed:
            return redirect("onboard-identity")

        if request.method == "GET":
            return render(request, "onboard/steps/03_place.html", {
                "step": "place", "wc": wc,
            })

        from onboard.serializers import OnboardPlaceSerializer
        serializer = OnboardPlaceSerializer(data=request.data)
        if not serializer.is_valid():
            return render(request, "onboard/steps/03_place.html", {
                "step": "place", "wc": wc, "errors": serializer.errors,
                "initial": request.data.dict(),
            }, status=422)

        data = serializer.validated_data
        with schema_context("meta"):
            WaitingConfiguration.objects.filter(uuid=wc.uuid).update(
                street_address=data["street_address"],
                postal_code=data["postal_code"],
                address_locality=data["address_locality"],
                address_country=data["address_country"],
                short_description=data["short_description"],
                latitude=data["latitude"],
                longitude=data["longitude"],
                current_step="descriptions",
            )
        return redirect("onboard-descriptions")

    @action(detail=False, methods=["POST"], url_path="geocode")
    def geocode_endpoint(self, request):
        """Proxy Nominatim — renvoie un partial HTML avec coords ou erreur."""
        from onboard.services import geocode
        query = request.data.get("query", "")
        result = geocode(query)
        return render(request, "onboard/partials/geocode_result.html", {
            "result": result, "query": query,
        })
```

Note : ajouter `from onboard.services import geocode` n'est pas nécessaire en haut car on l'importe localement, mais le test patche `onboard.views.geocode` — donc on doit l'importer **au niveau module** :

Modifier les imports en haut de `onboard/views.py` :

```python
from onboard.services import geocode  # noqa: F401  (utilise dans geocode_endpoint, patche par les tests)
```

- [ ] **Step 3 : Tests passent**

Run: `docker exec lespass_django poetry run pytest onboard/tests/test_step_place.py -v`
Expected: 2 PASS.

- [ ] **Step 4 : Commit**

```bash
git add onboard/views.py onboard/tests/test_step_place.py
git commit -m "feat(onboard): step 3 place + Nominatim geocode endpoint"
```

---

### Task 13 : Step 4 — Descriptions (long desc + logo upload)

**Files:**
- Modify: `onboard/views.py` (append)
- Create: `onboard/tests/test_step_descriptions.py`

- [ ] **Step 1 : Test**

```python
"""
Tests step 4 — descriptions + logo.
LOCALISATION: onboard/tests/test_step_descriptions.py
"""

from io import BytesIO
import pytest
from PIL import Image
from rest_framework.test import APIClient
from django.core.files.uploadedfile import SimpleUploadedFile
from django_tenants.utils import schema_context

from MetaBillet.models import WaitingConfiguration


def _make_test_image():
    buf = BytesIO()
    Image.new("RGB", (100, 100), "red").save(buf, "JPEG")
    buf.seek(0)
    return SimpleUploadedFile("logo.jpg", buf.read(), "image/jpeg")


@pytest.mark.django_db
def test_descriptions_post_saves_long_desc_and_logo():
    client = APIClient()
    with schema_context("meta"):
        wc = WaitingConfiguration.objects.create(
            organisation="D", email="d@x.com", dns_choice="tibillet.coop",
            email_confirmed=True, current_step="descriptions",
        )
    session = client.session
    session["onboard_wc_uuid"] = str(wc.uuid)
    session.save()

    response = client.post("/onboard/descriptions/", data={
        "long_description": "Une longue description du lieu.",
        "logo": _make_test_image(),
    }, format="multipart")
    assert response.status_code in (302, 303)
    with schema_context("meta"):
        wc.refresh_from_db()
    assert wc.long_description == "Une longue description du lieu."
    assert wc.logo  # un fichier a ete sauvegarde
    assert wc.current_step == "events"
```

- [ ] **Step 2 : Append à `onboard/views.py`**

```python
    # === Step 4 — Descriptions ===

    @action(detail=False, methods=["GET", "POST"], url_path="descriptions")
    def descriptions(self, request):
        wc = _get_or_none_wc(request)
        if wc is None or not wc.email_confirmed:
            return redirect("onboard-identity")

        if request.method == "GET":
            return render(request, "onboard/steps/04_descriptions.html", {
                "step": "descriptions", "wc": wc,
            })

        from onboard.serializers import OnboardDescriptionsSerializer
        serializer = OnboardDescriptionsSerializer(data=request.data)
        if not serializer.is_valid():
            return render(request, "onboard/steps/04_descriptions.html", {
                "step": "descriptions", "wc": wc, "errors": serializer.errors,
            }, status=422)

        data = serializer.validated_data
        with schema_context("meta"):
            wc_db = WaitingConfiguration.objects.get(uuid=wc.uuid)
            wc_db.long_description = data["long_description"]
            if data.get("logo"):
                wc_db.logo = data["logo"]
            wc_db.current_step = "events"
            wc_db.save()
        return redirect("onboard-events")
```

- [ ] **Step 3 : Tests passent**

Run: `docker exec lespass_django poetry run pytest onboard/tests/test_step_descriptions.py -v`
Expected: 1 PASS.

- [ ] **Step 4 : Commit**

```bash
git add onboard/views.py onboard/tests/test_step_descriptions.py
git commit -m "feat(onboard): step 4 descriptions + logo upload"
```

---

### Task 14 : Step 5 — Events (add/remove sous-form HTMX)

**Files:**
- Modify: `onboard/views.py` (append)
- Create: `onboard/tests/test_step_events.py`

- [ ] **Step 1 : Test**

```python
"""
Tests step 5 — events draft (JSON dans wc.events_draft).
LOCALISATION: onboard/tests/test_step_events.py
"""

import pytest
from rest_framework.test import APIClient
from django_tenants.utils import schema_context

from MetaBillet.models import WaitingConfiguration


def _make_wc_at_events(client_api):
    with schema_context("meta"):
        wc = WaitingConfiguration.objects.create(
            organisation="E", email="e@x.com", dns_choice="tibillet.coop",
            email_confirmed=True, current_step="events",
        )
    session = client_api.session
    session["onboard_wc_uuid"] = str(wc.uuid)
    session.save()
    return wc


@pytest.mark.django_db
def test_events_add_appends_to_jsonfield():
    client = APIClient()
    wc = _make_wc_at_events(client)
    response = client.post("/onboard/events/add/", data={
        "name": "Concert 1",
        "datetime": "2026-12-01T20:00:00",
        "description": "Yay",
    })
    assert response.status_code == 200
    with schema_context("meta"):
        wc.refresh_from_db()
    assert len(wc.events_draft) == 1
    assert wc.events_draft[0]["name"] == "Concert 1"


@pytest.mark.django_db
def test_events_remove_by_index():
    client = APIClient()
    wc = _make_wc_at_events(client)
    with schema_context("meta"):
        wc.events_draft = [{"name": "A"}, {"name": "B"}]
        wc.save()
    response = client.post("/onboard/events/0/remove/")
    assert response.status_code == 200
    with schema_context("meta"):
        wc.refresh_from_db()
    assert len(wc.events_draft) == 1
    assert wc.events_draft[0]["name"] == "B"


@pytest.mark.django_db
def test_events_finalize_advances_to_launch_and_enqueues_task():
    from unittest.mock import patch
    client = APIClient()
    wc = _make_wc_at_events(client)
    with patch("onboard.tasks.create_tenant_from_draft.delay") as mock:
        response = client.post("/onboard/events/")
    assert response.status_code in (302, 303)
    with schema_context("meta"):
        wc.refresh_from_db()
    assert wc.current_step == "launch"
    mock.assert_called_once_with(wc_uuid=str(wc.uuid))
```

- [ ] **Step 2 : Append à `onboard/views.py`**

```python
    # === Step 5 — Events ===

    @action(detail=False, methods=["GET", "POST"], url_path="events")
    def events(self, request):
        wc = _get_or_none_wc(request)
        if wc is None or not wc.email_confirmed:
            return redirect("onboard-identity")

        if request.method == "GET":
            return render(request, "onboard/steps/05_events.html", {
                "step": "events", "wc": wc, "events_draft": wc.events_draft or [],
            })

        # POST = finalisation : on enqueue la task de creation, on passe step 6
        # / POST = finalize: enqueue tenant creation, move to step 6
        from onboard.tasks import create_tenant_from_draft
        with schema_context("meta"):
            WaitingConfiguration.objects.filter(uuid=wc.uuid).update(current_step="launch")
        # Idempotent: la task verifie elle-meme si wc.tenant_id est deja set.
        create_tenant_from_draft.delay(wc_uuid=str(wc.uuid))
        return redirect("onboard-launch")

    @action(detail=False, methods=["POST"], url_path="events/add")
    def events_add(self, request):
        wc = _get_or_none_wc(request)
        if wc is None or not wc.email_confirmed:
            return HttpResponse(status=403)

        from onboard.serializers import OnboardEventDraftSerializer
        serializer = OnboardEventDraftSerializer(data=request.data)
        if not serializer.is_valid():
            return render(request, "onboard/partials/event_row_form.html", {
                "errors": serializer.errors, "initial": request.data.dict(),
            }, status=422)

        new_event = {
            "name": serializer.validated_data["name"],
            "datetime": serializer.validated_data["datetime"].isoformat(),
            "description": serializer.validated_data.get("description", ""),
        }
        with schema_context("meta"):
            wc_db = WaitingConfiguration.objects.get(uuid=wc.uuid)
            wc_db.events_draft = (wc_db.events_draft or []) + [new_event]
            wc_db.save(update_fields=["events_draft"])
        return render(request, "onboard/partials/events_list.html", {
            "events_draft": wc_db.events_draft,
        })

    @action(detail=False, methods=["POST"], url_path=r"events/(?P<idx>\d+)/remove")
    def events_remove(self, request, idx=None):
        wc = _get_or_none_wc(request)
        if wc is None or not wc.email_confirmed:
            return HttpResponse(status=403)

        try:
            i = int(idx)
        except (TypeError, ValueError):
            return HttpResponse(status=400)

        with schema_context("meta"):
            wc_db = WaitingConfiguration.objects.get(uuid=wc.uuid)
            evs = wc_db.events_draft or []
            if 0 <= i < len(evs):
                evs.pop(i)
                wc_db.events_draft = evs
                wc_db.save(update_fields=["events_draft"])
        return render(request, "onboard/partials/events_list.html", {
            "events_draft": wc_db.events_draft,
        })
```

- [ ] **Step 3 : Tests passent**

Run: `docker exec lespass_django poetry run pytest onboard/tests/test_step_events.py -v`
Expected: 3 PASS.

- [ ] **Step 4 : Commit**

```bash
git add onboard/views.py onboard/tests/test_step_events.py
git commit -m "feat(onboard): step 5 events draft (HTMX add/remove + finalize enqueues task)"
```

---

### Task 15 : Step 6 — Launch + status + resume

**Files:**
- Modify: `onboard/views.py` (append)
- Create: `onboard/tests/test_step_launch.py`

- [ ] **Step 1 : Test**

```python
"""
Tests step 6 — launch + status polling + resume.
LOCALISATION: onboard/tests/test_step_launch.py
"""

import pytest
from rest_framework.test import APIClient
from django_tenants.utils import schema_context

from Customers.models import Client
from MetaBillet.models import WaitingConfiguration


def _make_wc_at_launch(client_api, with_tenant=False):
    with schema_context("meta"):
        wc = WaitingConfiguration.objects.create(
            organisation="L", email="l@x.com", dns_choice="tibillet.coop",
            email_confirmed=True, current_step="launch",
        )
        if with_tenant:
            wc.tenant = Client.objects.exclude(categorie=Client.ROOT).first()
            wc.save()
    session = client_api.session
    session["onboard_wc_uuid"] = str(wc.uuid)
    session.save()
    return wc


@pytest.mark.django_db
def test_launch_get_renders_page_with_carousel():
    client = APIClient()
    _make_wc_at_launch(client)
    response = client.get("/onboard/launch/")
    assert response.status_code == 200
    assert b"carrousel" in response.content.lower() or b"carousel" in response.content.lower()


@pytest.mark.django_db
def test_status_endpoint_progress_when_no_tenant():
    client = APIClient()
    _make_wc_at_launch(client)
    response = client.get("/onboard/launch/status/")
    assert response.status_code == 200
    assert b"every 2s" in response.content  # polling continue


@pytest.mark.django_db
def test_status_endpoint_done_when_tenant_set():
    client = APIClient()
    wc = _make_wc_at_launch(client, with_tenant=True)
    response = client.get("/onboard/launch/status/")
    assert response.status_code == 200
    assert b"every 2s" not in response.content  # polling s'arrete
    domain = wc.tenant.get_primary_domain().domain
    assert domain.encode() in response.content


@pytest.mark.django_db
def test_status_endpoint_error_when_error_message():
    client = APIClient()
    wc = _make_wc_at_launch(client)
    with schema_context("meta"):
        WaitingConfiguration.objects.filter(uuid=wc.uuid).update(
            error_message="Pool epuise",
        )
    response = client.get("/onboard/launch/status/")
    assert response.status_code == 200
    assert b"Pool epuise" in response.content or b"erreur" in response.content.lower()
```

- [ ] **Step 2 : Append à `onboard/views.py`**

```python
    # === Step 6 — Launch ===

    @action(detail=False, methods=["GET"], url_path="launch")
    def launch(self, request):
        wc = _get_or_none_wc(request)
        if wc is None or not wc.email_confirmed:
            return redirect("onboard-identity")
        return render(request, "onboard/steps/06_launch.html", {
            "step": "launch", "wc": wc,
        })

    @action(detail=False, methods=["GET"], url_path="launch/status")
    def launch_status(self, request):
        wc = _get_or_none_wc(request)
        if wc is None:
            return HttpResponse(status=404)
        with schema_context("meta"):
            wc.refresh_from_db()

        if wc.error_message:
            return render(request, "onboard/partials/status_error.html", {"wc": wc})
        if wc.tenant_id:
            admin_url = f"https://{wc.tenant.get_primary_domain().domain}/admin/"
            return render(request, "onboard/partials/status_done.html", {
                "wc": wc, "admin_url": admin_url,
            })
        return render(request, "onboard/partials/status_progress.html", {"wc": wc})

    @action(detail=False, methods=["POST"], url_path="launch/retry")
    def launch_retry(self, request):
        wc = _get_or_none_wc(request)
        if wc is None:
            return HttpResponse(status=404)
        with schema_context("meta"):
            WaitingConfiguration.objects.filter(uuid=wc.uuid).update(error_message="")
        from onboard.tasks import create_tenant_from_draft
        create_tenant_from_draft.delay(wc_uuid=str(wc.uuid))
        return render(request, "onboard/partials/status_progress.html", {"wc": wc})

    # === Resume via magic link ===

    @action(detail=False, methods=["GET"], url_path=r"resume/(?P<signed>[^/]+)")
    def resume(self, request, signed=None):
        from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
        signer = TimestampSigner()
        try:
            wc_uuid = signer.unsign(signed, max_age=7 * 24 * 3600)
        except (BadSignature, SignatureExpired):
            return render(request, "onboard/partials/resume_invalid.html", status=400)
        with schema_context("meta"):
            wc = WaitingConfiguration.objects.filter(uuid=wc_uuid).first()
        if wc is None:
            return render(request, "onboard/partials/resume_invalid.html", status=404)
        _set_session_wc(request, wc)
        return redirect(f"onboard-{wc.current_step}")
```

- [ ] **Step 3 : Tests passent**

Run: `docker exec lespass_django poetry run pytest onboard/tests/test_step_launch.py -v`
Expected: 4 PASS.

- [ ] **Step 4 : Commit**

```bash
git add onboard/views.py onboard/tests/test_step_launch.py
git commit -m "feat(onboard): step 6 launch + status polling + retry + resume magic link"
```

---

## Phase D — Templates

### Task 16 : Base wizard layout + progress panel

**Files:**
- Create: `onboard/templates/onboard/base_wizard.html`
- Create: `onboard/templates/onboard/partials/progress_panel.html`
- Create: `onboard/static/onboard/wizard.css`
- Create: `onboard/static/onboard/wizard.js`

- [ ] **Step 1 : `base_wizard.html`** (étend le base SEO pour réutiliser HTMX, CSRF, etc.)

```html
{% extends "seo/base.html" %}
{% load i18n static %}

{% block extra_head %}
<link rel="stylesheet" href="{% static 'onboard/wizard.css' %}">
{% endblock %}

{% block main_wrapper %}
<main class="onboard-wizard container-lg my-4" data-testid="onboard-wizard">
  <div class="row g-4">
    <!-- Panneau gauche (orientation) — collapse mobile via <details> -->
    <aside class="col-lg-5 onboard-panel-wrapper">
      <details open class="onboard-panel-collapse d-lg-none">
        <summary class="btn btn-outline-primary w-100 mb-3">{% translate "Voir les étapes" %}</summary>
        {% include "onboard/partials/progress_panel.html" %}
      </details>
      <div class="d-none d-lg-block">
        {% include "onboard/partials/progress_panel.html" %}
      </div>
    </aside>

    <!-- Formulaire (étape courante) -->
    <section class="col-lg-7" id="wizard-content" aria-live="polite">
      {% block step_content %}{% endblock %}
    </section>
  </div>
</main>
<script src="{% static 'onboard/wizard.js' %}" defer></script>
{% endblock main_wrapper %}
```

- [ ] **Step 2 : `partials/progress_panel.html`**

```html
{% load i18n %}
<div class="onboard-panel" data-testid="onboard-progress-panel">
  <div class="onboard-panel-header">
    <span class="onboard-panel-eyebrow">{% translate "CRÉER MON ESPACE" %}</span>
  </div>
  <ol class="onboard-panel-steps">
    {% with steps="identity,verify,place,descriptions,events,launch" %}
    {% with labels_fr="Identité,Vérification,Votre lieu,Description,Événements,C'est parti !" %}
    {% for s in steps|cut:" "|stringformat:"s"|cut:" "|cut:"" %}{% endfor %}
    {% endwith %}{% endwith %}
    {# liste statique pour eviter les acrobaties de templating #}
    <li class="onboard-step {% if step == 'identity' %}is-current{% elif step in 'verify,place,descriptions,events,launch' %}is-done{% endif %}" aria-current="{% if step == 'identity' %}step{% endif %}">
      <span class="onboard-step-num">1</span> {% translate "Identité" %}
      <small class="onboard-step-hint">{% translate "Qui es-tu et comment t'appelles ton lieu ?" %}</small>
    </li>
    <li class="onboard-step {% if step == 'verify' %}is-current{% elif step in 'place,descriptions,events,launch' %}is-done{% endif %}" aria-current="{% if step == 'verify' %}step{% endif %}">
      <span class="onboard-step-num">2</span> {% translate "Vérification" %}
      <small class="onboard-step-hint">{% translate "On t'envoie un code par email." %}</small>
    </li>
    <li class="onboard-step {% if step == 'place' %}is-current{% elif step in 'descriptions,events,launch' %}is-done{% endif %}" aria-current="{% if step == 'place' %}step{% endif %}">
      <span class="onboard-step-num">3</span> {% translate "Votre lieu" %}
      <small class="onboard-step-hint">{% translate "On localise ton lieu sur la carte." %}</small>
    </li>
    <li class="onboard-step {% if step == 'descriptions' %}is-current{% elif step in 'events,launch' %}is-done{% endif %}" aria-current="{% if step == 'descriptions' %}step{% endif %}">
      <span class="onboard-step-num">4</span> {% translate "Description" %}
      <small class="onboard-step-hint">{% translate "Texte long + logo." %}</small>
    </li>
    <li class="onboard-step {% if step == 'events' %}is-current{% elif step in 'launch' %}is-done{% endif %}" aria-current="{% if step == 'events' %}step{% endif %}">
      <span class="onboard-step-num">5</span> {% translate "Événements" %}
      <small class="onboard-step-hint">{% translate "Optionnel : déclare 0 à N événements." %}</small>
    </li>
    <li class="onboard-step {% if step == 'launch' %}is-current{% endif %}" aria-current="{% if step == 'launch' %}step{% endif %}">
      <span class="onboard-step-num">6</span> {% translate "C'est parti !" %}
      <small class="onboard-step-hint">{% translate "Découverte de TiBillet pendant la création." %}</small>
    </li>
  </ol>

  {% if invitation %}
  <div class="onboard-panel-invite" data-testid="onboard-invitation-badge">
    🎉 {% blocktranslate with name=invitation.invited_by_tenant.name %}Invité·e par {{ name }}{% endblocktranslate %}
  </div>
  {% endif %}

  {% if step != "identity" and step != "verify" %}
  <button type="button" class="btn btn-link btn-sm onboard-resume-later" data-testid="onboard-resume-later">
    {% translate "Reprendre plus tard" %}
  </button>
  {% endif %}
</div>
```

- [ ] **Step 3 : `static/onboard/wizard.css`** (minimal, mobile-first)

```css
/* Panneau gauche (orientation) — dégradé vert TiBillet
   / Left panel (orientation) — TiBillet green gradient */
.onboard-panel {
    background: linear-gradient(160deg, var(--bs-primary, #15803d), #166534);
    color: #fff;
    border-radius: 0.75rem;
    padding: 1.5rem;
    height: 100%;
}
.onboard-panel-eyebrow {
    font-size: 0.75rem;
    opacity: 0.7;
    letter-spacing: 0.1em;
}
.onboard-panel-steps {
    list-style: none;
    padding: 0;
    margin: 1rem 0 0;
}
.onboard-step {
    padding: 0.5rem 0;
    opacity: 0.4;
    display: flex;
    flex-direction: column;
}
.onboard-step.is-current { opacity: 1; font-weight: 600; }
.onboard-step.is-done { opacity: 0.65; }
.onboard-step-num {
    display: inline-block;
    width: 1.5em;
    text-align: center;
    margin-right: 0.5em;
}
.onboard-step-hint {
    display: block;
    font-size: 0.8rem;
    opacity: 0.85;
    margin-left: 2em;
    font-weight: 400;
}
.onboard-panel-invite {
    margin-top: 1rem;
    background: rgba(255,255,255,0.15);
    padding: 0.5rem 0.75rem;
    border-radius: 0.5rem;
    font-size: 0.85rem;
}
.onboard-resume-later {
    color: #fff;
    margin-top: 1rem;
    text-decoration: underline;
}

/* Carrousel d'info pendant l'attente / Info carousel during wait */
.onboard-carousel {
    background: var(--bs-tertiary-bg, #f8f9fa);
    border-radius: 0.75rem;
    padding: 1.5rem;
    min-height: 200px;
    position: relative;
}
.onboard-carousel-card { display: none; }
.onboard-carousel-card.is-active { display: block; }
```

- [ ] **Step 4 : `static/onboard/wizard.js`** (auto-tab OTP + carrousel)

```javascript
/**
 * Wizard onboarding — JS minimal.
 * / Onboarding wizard — minimal JS.
 *
 * LOCALISATION : onboard/static/onboard/wizard.js
 *
 * Roles :
 * 1. Auto-tab entre les 6 inputs OTP de l'étape 2
 * 2. Rotation auto du carrousel d'info à l'étape 6 (5s par card)
 * 3. Click sur "Reprendre plus tard" → modal simple via confirm + POST
 */
(function() {
    "use strict";

    // 1. Auto-tab OTP
    function setupOtpAutoTab() {
        const inputs = document.querySelectorAll('input[data-testid^="onboard-verify-otp-"]');
        if (inputs.length !== 6) return;
        inputs.forEach((input, idx) => {
            input.addEventListener("input", (e) => {
                if (e.target.value.length === 1 && idx < 5) {
                    inputs[idx + 1].focus();
                }
            });
            input.addEventListener("keydown", (e) => {
                if (e.key === "Backspace" && !e.target.value && idx > 0) {
                    inputs[idx - 1].focus();
                }
            });
        });
    }

    // 2. Rotation carrousel
    function setupCarousel() {
        const cards = document.querySelectorAll(".onboard-carousel-card");
        if (cards.length === 0) return;
        let i = 0;
        cards[i].classList.add("is-active");
        setInterval(() => {
            cards[i].classList.remove("is-active");
            i = (i + 1) % cards.length;
            cards[i].classList.add("is-active");
        }, 5000);
    }

    document.addEventListener("DOMContentLoaded", () => {
        setupOtpAutoTab();
        setupCarousel();
    });
})();
```

- [ ] **Step 5 : Commit**

```bash
git add onboard/templates/onboard/base_wizard.html onboard/templates/onboard/partials/progress_panel.html onboard/static/onboard/
git commit -m "feat(onboard): base wizard layout + progress panel + JS auto-tab + carousel rotation"
```

---

### Task 17 : Templates des étapes 1, 2

**Files:**
- Create: `onboard/templates/onboard/steps/01_identity.html`
- Create: `onboard/templates/onboard/steps/02_verify.html`
- Create: `onboard/templates/onboard/partials/resend_sent.html`
- Create: `onboard/templates/onboard/partials/resend_blocked.html`

- [ ] **Step 1 : `steps/01_identity.html`**

```html
{% extends "onboard/base_wizard.html" %}
{% load i18n %}
{% block step_content %}
<h1 class="onboard-h1">1. {% translate "Identité" %}</h1>
<p class="onboard-subtitle">{% translate "Crée ton compte pour commencer. On t'enverra un code par email à la prochaine étape." %}</p>

<form method="post" action="{% url 'onboard-identity' %}{% if invitation %}?invite={{ invitation.code }}{% endif %}" data-testid="onboard-identity-form" novalidate>
  {% csrf_token %}

  <div class="mb-3">
    <label for="id_first_name" class="form-label">{% translate "Prénom" %} *</label>
    <input id="id_first_name" name="first_name" type="text" class="form-control" required value="{{ initial.first_name|default:'' }}" data-testid="onboard-identity-first_name">
    {% if errors.first_name %}<div class="text-danger small">{{ errors.first_name|join:" " }}</div>{% endif %}
  </div>
  <div class="mb-3">
    <label for="id_last_name" class="form-label">{% translate "Nom" %} *</label>
    <input id="id_last_name" name="last_name" type="text" class="form-control" required value="{{ initial.last_name|default:'' }}" data-testid="onboard-identity-last_name">
    {% if errors.last_name %}<div class="text-danger small">{{ errors.last_name|join:" " }}</div>{% endif %}
  </div>
  <div class="mb-3">
    <label for="id_email" class="form-label">{% translate "Email" %} *</label>
    <input id="id_email" name="email" type="email" class="form-control" required value="{{ initial.email|default:'' }}" data-testid="onboard-identity-email">
    {% if errors.email %}<div class="text-danger small">{{ errors.email|join:" " }}</div>{% endif %}
  </div>
  <div class="mb-3">
    <label for="id_email_confirm" class="form-label">{% translate "Confirme ton email" %} *</label>
    <input id="id_email_confirm" name="email_confirm" type="email" class="form-control" required value="{{ initial.email_confirm|default:'' }}" data-testid="onboard-identity-email_confirm">
    {% if errors.email_confirm %}<div class="text-danger small">{{ errors.email_confirm|join:" " }}</div>{% endif %}
  </div>
  <div class="mb-3">
    <label for="id_name" class="form-label">{% translate "Nom de ton lieu" %} *</label>
    <input id="id_name" name="name" type="text" class="form-control" required value="{{ initial.name|default:'' }}" data-testid="onboard-identity-name">
    {% if errors.name %}<div class="text-danger small">{{ errors.name|join:" " }}</div>{% endif %}
  </div>
  <div class="mb-3">
    <label for="id_dns_choice" class="form-label">{% translate "Domaine" %}</label>
    <select id="id_dns_choice" name="dns_choice" class="form-select" data-testid="onboard-identity-dns_choice">
      <option value="tibillet.coop" {% if initial.dns_choice == 'tibillet.coop' %}selected{% endif %}>tibillet.coop</option>
      <option value="tibillet.re" {% if initial.dns_choice == 'tibillet.re' %}selected{% endif %}>tibillet.re</option>
      <option value="tibillet.fr" {% if initial.dns_choice == 'tibillet.fr' %}selected{% endif %}>tibillet.fr</option>
    </select>
  </div>
  <div class="form-check mb-3">
    <input type="checkbox" id="id_cgu" name="cgu" class="form-check-input" required data-testid="onboard-identity-cgu">
    <label for="id_cgu" class="form-check-label">{% translate "J'accepte les conditions d'utilisation." %} *</label>
    {% if errors.cgu %}<div class="text-danger small">{{ errors.cgu|join:" " }}</div>{% endif %}
  </div>

  <button type="submit" class="btn btn-primary btn-lg" data-testid="onboard-identity-next">
    {% translate "Continuer →" %}
  </button>
</form>
{% endblock %}
```

- [ ] **Step 2 : `steps/02_verify.html`**

```html
{% extends "onboard/base_wizard.html" %}
{% load i18n %}
{% block step_content %}
<h1 class="onboard-h1">2. {% translate "Vérification" %}</h1>
<p class="onboard-subtitle">
  {% blocktranslate %}On a envoyé un code à 6 chiffres à <strong>{{ email }}</strong>. Saisis-le ci-dessous.{% endblocktranslate %}
</p>

<form method="post" action="{% url 'onboard-verify' %}" data-testid="onboard-verify-form" novalidate>
  {% csrf_token %}
  <input type="hidden" name="otp" id="id_otp_hidden" />
  <div class="d-flex gap-2 mb-3 justify-content-center">
    {% for i in "012345" %}
    <input type="text" inputmode="numeric" maxlength="1" pattern="\d"
           class="form-control text-center"
           style="width:3rem;font-size:1.5rem;"
           data-testid="onboard-verify-otp-{{ i }}"
           oninput="document.getElementById('id_otp_hidden').value = Array.from(document.querySelectorAll('[data-testid^=onboard-verify-otp-]')).map(e=>e.value).join('');">
    {% endfor %}
  </div>
  {% if errors.otp %}<div class="text-danger small text-center mb-2">{{ errors.otp|join:" " }}</div>{% endif %}

  <div class="d-flex justify-content-between mt-3">
    <button type="button" class="btn btn-outline-secondary"
            hx-post="{% url 'onboard-resend-otp' %}" hx-target="#resend-status"
            data-testid="onboard-verify-resend">
      {% translate "Renvoyer le code" %}
    </button>
    <button type="submit" class="btn btn-primary" data-testid="onboard-verify-submit">
      {% translate "Vérifier" %}
    </button>
  </div>
  <div id="resend-status" class="mt-2"></div>
</form>
{% endblock %}
```

- [ ] **Step 3 : `partials/resend_sent.html`** et `resend_blocked.html`

```html
<!-- resend_sent.html -->
{% load i18n %}
<div class="alert alert-success" data-testid="onboard-resend-sent">{% translate "Nouveau code envoyé !" %}</div>
```

```html
<!-- resend_blocked.html -->
{% load i18n %}
<div class="alert alert-warning" data-testid="onboard-resend-blocked">{% translate "Trop de renvois. Réessaie dans 1 heure." %}</div>
```

- [ ] **Step 4 : Commit**

```bash
git add onboard/templates/onboard/steps/01_identity.html onboard/templates/onboard/steps/02_verify.html onboard/templates/onboard/partials/resend_sent.html onboard/templates/onboard/partials/resend_blocked.html
git commit -m "feat(onboard): templates steps 1 (identity) + 2 (verify OTP) + resend partials"
```

---

### Task 18 : Templates étapes 3 (place + carte Leaflet) + 4 (descriptions)

**Files:**
- Create: `onboard/templates/onboard/steps/03_place.html`
- Create: `onboard/templates/onboard/steps/04_descriptions.html`
- Create: `onboard/templates/onboard/partials/map_widget.html`
- Create: `onboard/templates/onboard/partials/geocode_result.html`

- [ ] **Step 1 : `steps/03_place.html`** (réutilise Leaflet vendoré dans `seo/static/seo/vendor/leaflet/`)

```html
{% extends "onboard/base_wizard.html" %}
{% load i18n static %}
{% block extra_head %}
{{ block.super }}
<link rel="stylesheet" href="{% static 'seo/vendor/leaflet/leaflet.css' %}">
{% endblock %}
{% block step_content %}
<h1 class="onboard-h1">3. {% translate "Votre lieu" %}</h1>
<p class="onboard-subtitle">{% translate "On va localiser ton lieu sur la carte du réseau. Tape ton adresse, la carte apparaît sous les champs." %}</p>

<form method="post" action="{% url 'onboard-place' %}" data-testid="onboard-place-form" novalidate>
  {% csrf_token %}

  <div class="mb-3">
    <label for="id_street_address" class="form-label">{% translate "Rue et numéro" %} *</label>
    <input id="id_street_address" name="street_address" type="text" class="form-control address-input"
           value="{{ wc.street_address|default:'' }}"
           hx-post="{% url 'onboard-geocode' %}" hx-trigger="change delay:1s"
           hx-target="#map-widget" hx-include="closest form"
           data-testid="onboard-place-street">
  </div>
  <div class="row">
    <div class="col-md-4 mb-3">
      <label for="id_postal_code" class="form-label">{% translate "Code postal" %}</label>
      <input id="id_postal_code" name="postal_code" type="text" class="form-control address-input" value="{{ wc.postal_code|default:'' }}" data-testid="onboard-place-postal">
    </div>
    <div class="col-md-8 mb-3">
      <label for="id_address_locality" class="form-label">{% translate "Ville" %}</label>
      <input id="id_address_locality" name="address_locality" type="text" class="form-control address-input" value="{{ wc.address_locality|default:'' }}" data-testid="onboard-place-city">
    </div>
  </div>
  <div class="mb-3">
    <label for="id_address_country" class="form-label">{% translate "Pays" %}</label>
    <input id="id_address_country" name="address_country" type="text" class="form-control address-input" value="{{ wc.address_country|default:'France' }}" data-testid="onboard-place-country">
  </div>

  <!-- Carte + marker draggable -->
  <div id="map-widget" class="mb-3">
    {% include "onboard/partials/map_widget.html" with latitude=wc.latitude longitude=wc.longitude %}
  </div>
  <input type="hidden" id="id_latitude" name="latitude" value="{{ wc.latitude|default:'' }}">
  <input type="hidden" id="id_longitude" name="longitude" value="{{ wc.longitude|default:'' }}">

  <div class="mb-3">
    <label for="id_short_description" class="form-label">{% translate "Description courte" %} *</label>
    <textarea id="id_short_description" name="short_description" rows="3" maxlength="280" class="form-control" data-testid="onboard-place-short_description">{{ wc.short_description|default:'' }}</textarea>
    <small class="text-muted">{% translate "280 caractères max." %}</small>
  </div>

  <div class="d-flex justify-content-between">
    <a href="{% url 'onboard-verify' %}" class="btn btn-link" data-testid="onboard-place-prev">← {% translate "Précédent" %}</a>
    <button type="submit" class="btn btn-primary" data-testid="onboard-place-next">{% translate "Continuer →" %}</button>
  </div>
</form>

<script src="{% static 'seo/vendor/leaflet/leaflet.js' %}"></script>
<script>
(function() {
    // Init carte avec marker draggable. Si on a deja des coords, marker la,
    // sinon carte vide centree sur France et marker pose au 1er click.
    const lat = parseFloat(document.getElementById('id_latitude').value);
    const lng = parseFloat(document.getElementById('id_longitude').value);
    const mapEl = document.getElementById('onboard-leaflet-map');
    if (!mapEl) return;
    const map = L.map(mapEl).setView(
        isNaN(lat) ? [46.6, 2.5] : [lat, lng],
        isNaN(lat) ? 5 : 14
    );
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap'
    }).addTo(map);

    let marker = null;
    function placeMarker(latlng) {
        if (!marker) {
            marker = L.marker(latlng, { draggable: true }).addTo(map);
            marker.on('dragend', () => updateCoords(marker.getLatLng()));
        } else {
            marker.setLatLng(latlng);
        }
        updateCoords(latlng);
    }
    function updateCoords(ll) {
        document.getElementById('id_latitude').value = ll.lat.toFixed(6);
        document.getElementById('id_longitude').value = ll.lng.toFixed(6);
    }
    if (!isNaN(lat) && !isNaN(lng)) placeMarker(L.latLng(lat, lng));
    map.on('click', (e) => placeMarker(e.latlng));

    // Reagit au partial geocode renvoye par HTMX
    document.body.addEventListener('htmx:afterSwap', (e) => {
        if (e.detail.target.id === 'map-widget') {
            const newLat = parseFloat(document.getElementById('geocode-lat')?.value);
            const newLng = parseFloat(document.getElementById('geocode-lng')?.value);
            if (!isNaN(newLat) && !isNaN(newLng)) {
                placeMarker(L.latLng(newLat, newLng));
                map.setView([newLat, newLng], 15);
            }
        }
    });
})();
</script>
{% endblock %}
```

- [ ] **Step 2 : `partials/map_widget.html`**

```html
{% load i18n %}
<div class="onboard-map-container" style="height:300px;border-radius:0.5rem;overflow:hidden;border:1px solid #ccc">
  <div id="onboard-leaflet-map" style="height:100%" data-testid="onboard-leaflet-map"></div>
</div>
<small class="text-muted">{% translate "Tape ton adresse au-dessus, la carte se centre automatiquement. Tu peux ensuite déplacer le marker pour ajuster." %}</small>
```

- [ ] **Step 3 : `partials/geocode_result.html`** (HTMX partial)

```html
{% load i18n %}
{% include "onboard/partials/map_widget.html" %}
{% if result %}
<input type="hidden" id="geocode-lat" value="{{ result.latitude }}">
<input type="hidden" id="geocode-lng" value="{{ result.longitude }}">
<div class="alert alert-success small mt-2" data-testid="onboard-geocode-success">
  📍 {{ result.display_name }}
</div>
{% else %}
<div class="alert alert-warning small mt-2" data-testid="onboard-geocode-fallback">
  {% translate "Service de géolocalisation indisponible — clique sur la carte pour positionner ton lieu." %}
</div>
{% endif %}
```

- [ ] **Step 4 : `steps/04_descriptions.html`**

```html
{% extends "onboard/base_wizard.html" %}
{% load i18n %}
{% block step_content %}
<h1 class="onboard-h1">4. {% translate "Description et logo" %}</h1>
<p class="onboard-subtitle">{% translate "Présente ton lieu en détail." %}</p>

<form method="post" action="{% url 'onboard-descriptions' %}" enctype="multipart/form-data" data-testid="onboard-descriptions-form">
  {% csrf_token %}
  <div class="mb-3">
    <label for="id_long_description" class="form-label">{% translate "Description longue" %} *</label>
    <textarea id="id_long_description" name="long_description" rows="8" maxlength="5000" class="form-control" data-testid="onboard-descriptions-long">{{ wc.long_description|default:'' }}</textarea>
    <small class="text-muted">{% translate "5000 caractères max." %}</small>
  </div>
  <div class="mb-3">
    <label for="id_logo" class="form-label">{% translate "Logo (optionnel)" %}</label>
    <input id="id_logo" name="logo" type="file" accept="image/jpeg,image/png,image/webp" class="form-control" data-testid="onboard-descriptions-logo">
    {% if wc.logo %}<small class="text-success">{% translate "Logo actuel :" %} {{ wc.logo.name }}</small>{% endif %}
  </div>

  <div class="d-flex justify-content-between">
    <a href="{% url 'onboard-place' %}" class="btn btn-link" data-testid="onboard-descriptions-prev">← {% translate "Précédent" %}</a>
    <button type="submit" class="btn btn-primary" data-testid="onboard-descriptions-next">{% translate "Continuer →" %}</button>
  </div>
</form>
{% endblock %}
```

- [ ] **Step 5 : Commit**

```bash
git add onboard/templates/onboard/steps/03_place.html onboard/templates/onboard/steps/04_descriptions.html onboard/templates/onboard/partials/map_widget.html onboard/templates/onboard/partials/geocode_result.html
git commit -m "feat(onboard): templates steps 3 (place + Leaflet draggable) + 4 (descriptions)"
```

---

### Task 19 : Templates étapes 5 (events) + 6 (launch + carrousel + status)

**Files:**
- Create: `onboard/templates/onboard/steps/05_events.html`
- Create: `onboard/templates/onboard/steps/06_launch.html`
- Create: `onboard/templates/onboard/partials/events_list.html`
- Create: `onboard/templates/onboard/partials/event_row_form.html`
- Create: `onboard/templates/onboard/partials/status_progress.html`
- Create: `onboard/templates/onboard/partials/status_done.html`
- Create: `onboard/templates/onboard/partials/status_error.html`

- [ ] **Step 1 : `steps/05_events.html`**

```html
{% extends "onboard/base_wizard.html" %}
{% load i18n %}
{% block step_content %}
<h1 class="onboard-h1">5. {% translate "Premiers événements" %}</h1>
<p class="onboard-subtitle">{% translate "Ajoute 0 ou plusieurs événements à publier dans ton espace. Tu pourras toujours en ajouter plus tard depuis l'admin." %}</p>

<div id="events-list">
  {% include "onboard/partials/events_list.html" %}
</div>

<button type="button" class="btn btn-outline-primary mb-3"
        hx-post="{% url 'onboard-events-add' %}" hx-target="#event-row-new" hx-swap="innerHTML"
        data-testid="onboard-events-add-button">
  + {% translate "Ajouter un événement" %}
</button>
<div id="event-row-new"></div>

<form method="post" action="{% url 'onboard-events' %}">
  {% csrf_token %}
  <div class="d-flex justify-content-between mt-4">
    <a href="{% url 'onboard-descriptions' %}" class="btn btn-link" data-testid="onboard-events-prev">← {% translate "Précédent" %}</a>
    <button type="submit" class="btn btn-primary" data-testid="onboard-events-finalize">{% translate "Lancer mon espace →" %}</button>
  </div>
</form>
{% endblock %}
```

- [ ] **Step 2 : `partials/events_list.html`**

```html
{% load i18n %}
{% for ev in events_draft %}
<div class="card mb-2" data-testid="onboard-event-{{ forloop.counter0 }}">
  <div class="card-body d-flex justify-content-between align-items-start">
    <div>
      <strong>{{ ev.name }}</strong>
      <small class="text-muted d-block">{{ ev.datetime }}</small>
      {% if ev.description %}<p class="mb-0 small">{{ ev.description|truncatechars:100 }}</p>{% endif %}
    </div>
    <button type="button" class="btn btn-sm btn-outline-danger"
            hx-post="{% url 'onboard-events-remove' idx=forloop.counter0 %}" hx-target="#events-list"
            data-testid="onboard-event-{{ forloop.counter0 }}-remove">× {% translate "Supprimer" %}</button>
  </div>
</div>
{% empty %}
<p class="text-muted small">{% translate "Aucun événement pour l'instant. C'est optionnel !" %}</p>
{% endfor %}
```

- [ ] **Step 3 : `partials/event_row_form.html`** (sous-form HTMX)

```html
{% load i18n %}
<form hx-post="{% url 'onboard-events-add' %}" hx-target="#events-list" hx-swap="innerHTML" data-testid="onboard-event-row-form">
  {% csrf_token %}
  <div class="card mb-2">
    <div class="card-body">
      <div class="row g-2">
        <div class="col-md-6">
          <input name="name" type="text" class="form-control" placeholder="{% translate 'Nom' %}" required>
          {% if errors.name %}<small class="text-danger">{{ errors.name|join:" " }}</small>{% endif %}
        </div>
        <div class="col-md-6">
          <input name="datetime" type="datetime-local" class="form-control" required>
          {% if errors.datetime %}<small class="text-danger">{{ errors.datetime|join:" " }}</small>{% endif %}
        </div>
        <div class="col-12">
          <textarea name="description" rows="2" class="form-control" placeholder="{% translate 'Description (optionnel)' %}"></textarea>
        </div>
        <div class="col-12 text-end">
          <button type="submit" class="btn btn-sm btn-primary">{% translate "Enregistrer" %}</button>
        </div>
      </div>
    </div>
  </div>
</form>
```

- [ ] **Step 4 : `steps/06_launch.html`** (carrousel + bouton)

```html
{% extends "onboard/base_wizard.html" %}
{% load i18n %}
{% block step_content %}
<h1 class="onboard-h1">🎉 {% blocktranslate with name=wc.organisation %}Bienvenue ! Ton espace {{ name }} arrive...{% endblocktranslate %}</h1>

<div id="launch-status" class="mb-4"
     hx-get="{% url 'onboard-launch-status' %}" hx-trigger="load, every 2s"
     hx-swap="outerHTML">
  {% include "onboard/partials/status_progress.html" with wc=wc %}
</div>

<h2 class="h4 mt-4">{% translate "Pendant ce temps, découvre TiBillet" %}</h2>
<div class="onboard-carousel" data-testid="onboard-info-carousel">
  <div class="onboard-carousel-card">
    <h3>{% translate "Adhésions et abonnements" %}</h3>
    <p>{% translate "Tu pourras gérer les adhésions à ton association et proposer des abonnements à tes membres." %}</p>
    <a href="https://tibillet.github.io/documentation_v3/" target="_blank" rel="noopener">{% translate "Documentation →" %}</a>
  </div>
  <div class="onboard-carousel-card">
    <h3>{% translate "Budget contributif" %}</h3>
    <p>{% translate "Lance des campagnes de financement participatif avec contribution adaptive et cascade multi-asset." %}</p>
    <a href="https://tibillet.github.io/documentation_v3/" target="_blank" rel="noopener">{% translate "Documentation →" %}</a>
  </div>
  <div class="onboard-carousel-card">
    <h3>{% translate "Booking de salle ou ressource" %}</h3>
    <p>{% translate "Permets à tes membres et au public de réserver tes salles ou ton matériel." %}</p>
    <a href="https://tibillet.github.io/documentation_v3/" target="_blank" rel="noopener">{% translate "Documentation →" %}</a>
  </div>
  <div class="onboard-carousel-card">
    <h3>{% translate "Mesure d'impact social via Grist" %}</h3>
    <p>{% translate "Connecte ton espace à la base ouverte du comité data des tiers-lieux pour mesurer ton impact." %}</p>
    <a href="https://tibillet.github.io/documentation_v3/" target="_blank" rel="noopener">{% translate "En savoir plus →" %}</a>
  </div>
  <div class="onboard-carousel-card">
    <h3>{% translate "Encaisser avec Stripe" %}</h3>
    <p>{% translate "Active Stripe Connect dans ton admin pour vendre des billets et adhésions en ligne." %}</p>
    <a href="https://tibillet.github.io/documentation_v3/" target="_blank" rel="noopener">{% translate "Documentation →" %}</a>
  </div>
  <div class="onboard-carousel-card">
    <h3>{% translate "Fédération de lieux" %}</h3>
    <p>{% translate "Ton lieu peut rejoindre le réseau coopératif TiBillet et partager son agenda avec d'autres structures." %}</p>
    <a href="https://tibillet.github.io/documentation_v3/" target="_blank" rel="noopener">{% translate "Documentation →" %}</a>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 5 : Partials status_progress / status_done / status_error**

```html
<!-- status_progress.html -->
{% load i18n %}
<div id="launch-status" class="alert alert-info d-flex align-items-center"
     hx-get="{% url 'onboard-launch-status' %}" hx-trigger="every 2s" hx-swap="outerHTML"
     data-testid="onboard-launch-status-progress">
  <div class="spinner-border spinner-border-sm me-2" role="status"><span class="visually-hidden">{% translate "Chargement..." %}</span></div>
  {% translate "Finalisation en cours…" %}
  <button class="btn btn-primary ms-auto disabled" disabled data-testid="onboard-launch-go">{% translate "Préparation..." %}</button>
</div>
```

```html
<!-- status_done.html -->
{% load i18n %}
<div id="launch-status" class="alert alert-success d-flex align-items-center"
     data-testid="onboard-launch-status-done">
  ✓ {% translate "Espace prêt — tu peux y aller !" %}
  <a href="{{ admin_url }}" class="btn btn-primary ms-auto" data-testid="onboard-launch-go">{% translate "Accéder à mon espace →" %}</a>
</div>
```

```html
<!-- status_error.html -->
{% load i18n %}
<div id="launch-status" class="alert alert-danger" data-testid="onboard-launch-status-error">
  ⚠️ {% translate "Une erreur est survenue, on a reçu une alerte. Tu peux réessayer ou nous contacter à contact@tibillet.coop." %}
  <pre class="small mt-2">{{ wc.error_message }}</pre>
  <form method="post" action="{% url 'onboard-launch-retry' %}" class="mt-2">
    {% csrf_token %}
    <button type="submit" class="btn btn-sm btn-outline-danger" data-testid="onboard-launch-retry">{% translate "Réessayer" %}</button>
  </form>
</div>
```

- [ ] **Step 6 : Commit**

```bash
git add onboard/templates/onboard/steps/05_events.html onboard/templates/onboard/steps/06_launch.html onboard/templates/onboard/partials/events_list.html onboard/templates/onboard/partials/event_row_form.html onboard/templates/onboard/partials/status_progress.html onboard/templates/onboard/partials/status_done.html onboard/templates/onboard/partials/status_error.html
git commit -m "feat(onboard): templates steps 5 (events HTMX) + 6 (launch carousel + status partials)"
```

---

## Phase E — Intégration

### Task 20 : Rediriger les boutons "Créer son espace" vers `/onboard/`

**Files:**
- Modify: `seo/templates/seo/landing.html`
- Modify: `BaseBillet/templates/reunion/partials/footer.html`
- Modify: `BaseBillet/templates/faire_festival/partials/footer.html`
- Modify: `BaseBillet/templates/htmx/components/navbar.html`

- [ ] **Step 1 : Landing root**

Localiser dans `seo/templates/seo/landing.html` le bouton `data-testid="hero-cta-create"` et remplacer le `href="https://tibillet.org"` par `href="/onboard/"`. Supprimer `target="_blank" rel="noopener"`.

- [ ] **Step 2 : Footers tenants (réutilise un grep)**

Run: `grep -rn "tenant/new" /home/jonas/TiBillet/dev/Lespass/BaseBillet/templates/`

Pour chaque occurrence, remplacer le `href="/tenant/new/"` par `href="/onboard/"`.

- [ ] **Step 3 : Vérifier que tout pointe vers `/onboard/`**

Run: `grep -rn "tenant/new\|tibillet.org\"" /home/jonas/TiBillet/dev/Lespass/seo/templates/ /home/jonas/TiBillet/dev/Lespass/BaseBillet/templates/ | grep -v "node_modules"`
Expected: aucune occurrence pour les boutons "Créer son espace".

- [ ] **Step 4 : Test manuel rapide via curl**

Run: `curl -s "https://tibillet.localhost/" | grep -A1 hero-cta-create | head -3`
Expected: `href="/onboard/"`.

- [ ] **Step 5 : Commit**

```bash
git add seo/templates/seo/landing.html BaseBillet/templates/
git commit -m "feat(onboard): point Créer son espace buttons to /onboard/"
```

---

### Task 21 : Admin Unfold — action "Inviter un nouveau lieu"

**Files:**
- Create: `onboard/admin.py`
- Modify: `Administration/admin_tenant.py` (si `FederationAdmin` est là — sinon créer custom admin pour `fedow_core.Federation`)

- [ ] **Step 1 : `onboard/admin.py`**

```python
"""
Admin Unfold pour OnboardInvitation.
/ Unfold admin for OnboardInvitation.

LOCALISATION: onboard/admin.py
"""

from django.contrib import admin
from unfold.admin import ModelAdmin

from onboard.models import OnboardInvitation


@admin.register(OnboardInvitation)
class OnboardInvitationAdmin(ModelAdmin):
    list_display = ("code", "federation", "invited_by_tenant", "email_invited", "used_at", "expires_at")
    list_filter = ("federation", "expires_at")
    search_fields = ("code", "email_invited")
    readonly_fields = ("code", "created_at", "used_at")
```

- [ ] **Step 2 : Ajouter une action sur l'admin Federation pour générer une invitation**

Localiser `FederationAdmin` (probablement `Administration/admin_tenant.py` ou `fedow_core/admin.py`) et ajouter une admin action :

```python
from onboard.models import OnboardInvitation

@admin.action(description=_("Generate onboard invitation"))
def generer_invitation_onboard(modeladmin, request, queryset):
    """
    Pour chaque federation selectionnee, cree une invitation onboard
    et affiche le code dans un message admin.
    / Generate an onboard invitation for each selected federation
    and show the code in an admin message.
    """
    from django.contrib import messages
    from django.db import connection
    for fed in queryset:
        inv = OnboardInvitation.objects.create(
            federation=fed,
            invited_by_user=request.user,
            invited_by_tenant=connection.tenant,
        )
        url = f"https://{connection.tenant.get_primary_domain().domain}/onboard/?invite={inv.code}"
        messages.success(request, f"Code: {inv.code} — Lien: {url}")

# Et dans FederationAdmin :
actions = [generer_invitation_onboard]
```

- [ ] **Step 3 : Vérifier dans l'admin**

Run: `docker exec lespass_django poetry run python /DjangoFiles/manage.py check`
Expected: 0 issues.

Manuel : se connecter à `/admin/`, aller dans Fedow → Federation, sélectionner une fédération, action "Generate onboard invitation" → message success avec code.

- [ ] **Step 4 : Commit**

```bash
git add onboard/admin.py Administration/
git commit -m "feat(onboard): Unfold admin for invitations + Federation action 'Generate invitation'"
```

---

### Task 22 : Management command `create_empty_tenant` (repeupler le pool)

**Files:**
- Create: `onboard/management/commands/create_empty_tenant.py`
- Create: `onboard/tests/test_create_empty_tenant_cmd.py`

- [ ] **Step 1 : Test**

```python
"""
Test du management command create_empty_tenant.
LOCALISATION: onboard/tests/test_create_empty_tenant_cmd.py
"""

import pytest
from django.core.management import call_command

from Customers.models import Client


@pytest.mark.django_db
def test_create_empty_tenant_adds_one_slot_to_pool():
    before = Client.objects.filter(categorie=Client.WAITING_CONFIG).count()
    call_command("create_empty_tenant")
    after = Client.objects.filter(categorie=Client.WAITING_CONFIG).count()
    assert after == before + 1
```

- [ ] **Step 2 : Implementer**

```python
"""
Management command pour ajouter un slot vide au pool de tenants.
/ Management command to add an empty slot to the tenant pool.

LOCALISATION: onboard/management/commands/create_empty_tenant.py

Usage : docker exec lespass_django poetry run python manage.py create_empty_tenant
"""

import secrets
from django.core.management.base import BaseCommand

from Customers.models import Client, Domain


class Command(BaseCommand):
    help = "Cree un tenant vide en categorie WAITING_CONFIG. / Create an empty WAITING_CONFIG tenant."

    def handle(self, *args, **options):
        # Genere un schema/name unique pour ne pas entrer en conflit
        # / Generate a unique schema/name to avoid conflicts
        slug = f"empty-{secrets.token_hex(4)}"
        tenant = Client.objects.create(
            schema_name=slug.replace("-", "_"),
            name=slug,
            categorie=Client.WAITING_CONFIG,
            on_trial=True,
        )
        # Domain technique, sera renomme a la prise de slot
        # / Technical domain, renamed when slot is taken
        Domain.objects.create(
            domain=f"{slug}.tibillet.coop",
            tenant=tenant,
            is_primary=True,
        )
        self.stdout.write(self.style.SUCCESS(f"Created empty tenant: {slug}"))
```

- [ ] **Step 3 : Tests passent**

Run: `docker exec lespass_django poetry run pytest onboard/tests/test_create_empty_tenant_cmd.py -v`

- [ ] **Step 4 : Commit**

```bash
git add onboard/management/ onboard/tests/test_create_empty_tenant_cmd.py
git commit -m "feat(onboard): management command create_empty_tenant to refill pool"
```

---

## Phase F — Tests E2E + docs

### Task 23 : Tests Playwright E2E (3 tests : golden / invitation / resume)

**Files:**
- Create: `tests/e2e/test_onboard_wizard.py`

- [ ] **Step 1 : Le test**

```python
"""
Tests E2E Playwright du wizard d'onboarding.
/ E2E Playwright tests for the onboarding wizard.

LOCALISATION: tests/e2e/test_onboard_wizard.py

Couvre :
1. Golden path : user anonyme, 6 etapes, arrive sur l'admin du nouveau tenant.
2. Invitation : ?invite=<code> → tenant cree rejoint la federation.
3. Resume magic link : reprend a la step 3 avec donnees pre-remplies.
"""

import re
import pytest
from playwright.sync_api import Page, expect
from django.utils.translation import gettext as _


@pytest.mark.django_db(transaction=True)
def test_onboard_golden_path(page: Page, live_server, intercept_emails):
    page.goto(f"{live_server.url}/onboard/identity/")
    # Step 1
    page.fill('[data-testid=onboard-identity-first_name]', "Test")
    page.fill('[data-testid=onboard-identity-last_name]', "User")
    page.fill('[data-testid=onboard-identity-email]', "test@example.com")
    page.fill('[data-testid=onboard-identity-email_confirm]', "test@example.com")
    page.fill('[data-testid=onboard-identity-name]', "Lieu test E2E")
    page.check('[data-testid=onboard-identity-cgu]')
    page.click('[data-testid=onboard-identity-next]')

    # Step 2 : recup OTP de l'email intercepte
    otp_code = intercept_emails.last_otp_code()
    for i, digit in enumerate(otp_code):
        page.fill(f'[data-testid=onboard-verify-otp-{i}]', digit)
    page.click('[data-testid=onboard-verify-submit]')

    # Step 3 : place
    page.fill('[data-testid=onboard-place-street]', "1 rue test")
    page.fill('[data-testid=onboard-place-postal]', "97400")
    page.fill('[data-testid=onboard-place-city]', "St Denis")
    page.fill('[data-testid=onboard-place-country]', "Réunion")
    page.fill('[data-testid=onboard-place-short_description]', "Description courte")
    # Forcer lat/lng via JS (skipping carte click)
    page.evaluate("document.getElementById('id_latitude').value = '-20.88'")
    page.evaluate("document.getElementById('id_longitude').value = '55.45'")
    page.click('[data-testid=onboard-place-next]')

    # Step 4
    page.fill('[data-testid=onboard-descriptions-long]', "Description longue détaillée")
    page.click('[data-testid=onboard-descriptions-next]')

    # Step 5 : skip events
    page.click('[data-testid=onboard-events-finalize]')

    # Step 6 : attend "go" actif
    expect(page.locator('[data-testid=onboard-launch-status-done]')).to_be_visible(timeout=15000)
    expect(page.locator('[data-testid=onboard-launch-go]')).to_be_enabled()
```

(Les 2 autres tests `test_onboard_with_invitation` et `test_onboard_resume_magic_link` suivent la même structure ; les écrire pleinement pendant l'implémentation.)

- [ ] **Step 2 : Lancer**

Run: `docker exec lespass_django poetry run pytest tests/e2e/test_onboard_wizard.py -v -s`
Expected: 1 test PASS (les 2 autres écrits dans la même session).

- [ ] **Step 3 : Compléter les 2 autres tests E2E**

Ajouter `test_onboard_with_invitation` et `test_onboard_resume_magic_link` sur le même pattern (~30 lignes chacun).

- [ ] **Step 4 : Commit**

```bash
git add tests/e2e/test_onboard_wizard.py
git commit -m "test(onboard): Playwright E2E for golden path + invitation + resume"
```

---

### Task 24 : CHANGELOG + A TESTER + i18n

**Files:**
- Modify: `CHANGELOG.md`
- Create: `A TESTER et DOCUMENTER/wizard-onboarding.md`
- Run: makemessages + compilemessages

- [ ] **Step 1 : Entry CHANGELOG.md**

Ajouter au top du `CHANGELOG.md` une section `## Wizard onboarding nouveau tenant` qui documente : nouvelle app `onboard/`, modèle `OnboardInvitation`, extension `WaitingConfiguration`, flow 6 étapes, OTP bcrypt, création async via Celery, mail "espace prêt", invitation cross-tenant, lien `/onboard/` depuis landing root + footers. Mentionner les migrations nécessaires (`MetaBillet 00XX_extend_waitingconfiguration` et `onboard 0001_initial`).

- [ ] **Step 2 : `A TESTER et DOCUMENTER/wizard-onboarding.md`**

Fichier de tests manuels avec :
- Scénario 1 — User anonyme, golden path
- Scénario 2 — User loggué avec email_valid=True → skip OTP
- Scénario 3 — Invitation par tenant existant
- Scénario 4 — Reprise via email magic link
- Scénario 5 — Pool vide → erreur + retry
- Commands DB de vérification (`Client.objects.filter(name="...").exists()`, etc.)

- [ ] **Step 3 : i18n**

Run:
```bash
docker exec lespass_django poetry run django-admin makemessages -l fr
docker exec lespass_django poetry run django-admin makemessages -l en
```

Éditer `locale/fr/LC_MESSAGES/django.po` et `locale/en/LC_MESSAGES/django.po` : remplir tous les `msgstr` ajoutés par cette feature. Supprimer les flags `#, fuzzy` mal placés.

Run:
```bash
docker exec lespass_django poetry run django-admin compilemessages
```

- [ ] **Step 4 : Vérification finale**

Run:
```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
docker exec lespass_django poetry run pytest onboard/ -v
docker exec lespass_django poetry run pytest tests/e2e/test_onboard_wizard.py -v -s
```

Expected: 0 issues + tous les tests PASS.

- [ ] **Step 5 : Commit final**

```bash
git add CHANGELOG.md "A TESTER et DOCUMENTER/wizard-onboarding.md" locale/
git commit -m "docs(onboard): CHANGELOG + manual test doc + i18n FR/EN"
```

---

## Récapitulatif

**24 tasks**, environ 80 commits granulaires, structurés en 6 phases :
- **A** (3 tasks) : Setup app + migrations modèles
- **B** (5 tasks) : Services OTP/geocode + 4 tasks Celery
- **C** (7 tasks) : ViewSet wizard step by step + status + resume
- **D** (4 tasks) : Templates (layout + 6 étapes + partials)
- **E** (3 tasks) : Intégration boutons + admin invitation + management command pool
- **F** (2 tasks) : Tests E2E + docs/i18n

**Couverture spec** :
- Architecture (spec §1) → tasks 1, 3, 9
- Flow 6 étapes (spec §2) → tasks 10-15
- UX layout C (spec §3) → tasks 16-19
- Persistance brouillon (spec §4) → tasks 9, 15
- Sécurité OTP / captcha / throttle (spec §5) → tasks 4, 11
- Validation DRF (spec §6) → tasks 10-15 via serializers
- Risques (spec §7) → tasks 7 (retry), 22 (pool)
- Tests (spec §8) → couvert dans toutes les tasks + task 23
- Scope in/out (spec §9-10) → respecté

Les modules toggles / Grist opt-in sont **hors scope wizard** (spec §10), reportés au dashboard admin.
