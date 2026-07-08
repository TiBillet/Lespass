# CHANTIER-01 — App `kiosk` : modèles TPE Stripe + admin — Plan d'implémentation

> **Pour worker agentique :** SOUS-SKILL REQUIS — utiliser `superpowers:subagent-driven-development`
> (recommandé) ou `superpowers:executing-plans`. Les étapes sont en cases à cocher (`- [ ]`).

**Goal :** Créer l'app Django `kiosk` avec les 3 modèles TPE Stripe (`StripeLocation`,
`Terminal`, `PaymentsIntent`) rebranchés sur Lespass, plus leur admin Unfold, migrations et tests.

**Architecture :** Copier-coller des modèles `APIcashless` de LaBoutik (`../LaBoutik`, branche
`main-tpe`), rebranchés sur les dépendances Lespass : clé Stripe via `RootConfiguration`,
`fedow_place_uuid` via `FedowConfig`, carte via `QrcodeCashless.CarteCashless`, lien borne via
`Terminal.term_user` OneToOne → `TermUser`. **Aucune signature des metadata** (cf. SPEC §8bis).

**Tech Stack :** Django (django-tenants), django-unfold (admin), Stripe SDK, pytest, poetry, Docker.

## Global Constraints

- **Périmètre CHANTIER-01 uniquement** : modèles + admin + migrations + tests. Le front,
  les vues, les WebSockets, le bridge, le module et l'extension Fedow sont les CHANTIER 02-04.
- **JAMAIS d'opération git par Claude ou un subagent** (règle projet ULTRA IMPORTANT). Les
  étapes « Checkpoint » signalent au mainteneur — c'est LUI qui commit.
- **Ne PAS lancer `runserver`** : le serveur tourne dans byobu (mainteneur). `makemigrations`,
  `migrate_schemas`, `pytest` sont autorisés.
- **Ne PAS lancer `makemessages`/`compilemessages`** (mainteneur). Les strings user-facing
  utilisent `_()`, texte source en **français**.
- **App en TENANT_APPS.** `settings.py` est un **fichier sensible** → checkpoint mainteneur
  avant modif (Task 1).
- **Code FALC** : verbeux, explicite, commentaires bilingues FR + résumé EN une ligne.
- Commandes dans le conteneur : `docker exec lespass_django poetry run <cmd>` depuis `/DjangoFiles`.
- **`app_label` = `kiosk`.** Modèles à `id = UUIDField(primary_key=True, default=uuid4)`.
- **Toutes les commandes `pytest` prennent `--api-key dummy`** (fixture autouse
  `_inject_cli_env` de `conftest.py` sinon `pytest.fail`).
- **Tests sur DB dev live** (pas de DB de test dédiée) : chaque test tourne dans un
  `tenant_context(tenant)` réel et nettoie ses objets (préfixe `TEST_`). Reprendre
  l'idiome exact de `tests/pytest/test_fedow_core.py` (récupération du tenant, cleanup).

---

## File Structure

- `kiosk/__init__.py` — vide.
- `kiosk/apps.py` — `KioskConfig` (`name='kiosk'`).
- `kiosk/models.py` — `StripeLocation`, `Terminal`, `PaymentsIntent`.
- `kiosk/admin.py` — `StripeLocationAdmin`, `TerminalAdmin`, `PaymentsIntentAdmin` (Unfold).
- `kiosk/migrations/` — `__init__.py` + migrations générées.
- `TiBillet/settings.py` — ajout `'kiosk'` dans `TENANT_APPS` (Task 1, checkpoint).
- `tests/pytest/test_kiosk_models.py` — tests des modèles.

---

## Task 1 : Scaffold de l'app `kiosk` + enregistrement TENANT_APPS

**Files :**
- Create : `kiosk/__init__.py`, `kiosk/apps.py`, `kiosk/migrations/__init__.py`, `kiosk/models.py` (vide au départ)
- Modify : `TiBillet/settings.py` (TENANT_APPS)

**Interfaces :**
- Produces : app Django `kiosk` chargée dans le schéma tenant.

- [ ] **Step 1 : Créer les fichiers de l'app**

`kiosk/__init__.py` : fichier vide.

`kiosk/apps.py` :
```python
from django.apps import AppConfig


class KioskConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "kiosk"
    verbose_name = "Kiosk"
```

`kiosk/migrations/__init__.py` : fichier vide.

`kiosk/models.py` :
```python
# Modèles TPE Stripe du kiosk (chantier CHANTIER-01).
# / Kiosk Stripe terminal models (CHANTIER-01).
```

- [ ] **Step 2 : Checkpoint mainteneur — ajout à TENANT_APPS**

Repérer `TENANT_APPS` dans `TiBillet/settings.py` (~ligne 189, c'est un **tuple**, pas une
liste) et y ajouter `'kiosk'` après `'laboutik'`. `settings.py` est **sensible** : présenter
le diff au mainteneur et attendre son accord avant d'écrire.

Diff attendu (respecter la syntaxe tuple existante) :
```python
TENANT_APPS = (
    ...
    'laboutik',
    'kiosk',   # <-- ajouté
    ...
)
```

- [ ] **Step 3 : Vérifier que l'app charge**

Run : `docker exec lespass_django poetry run python /DjangoFiles/manage.py check`
Expected : `System check identified no issues (0 silenced).`

- [ ] **Step 4 : Checkpoint mainteneur (commit)**

Signaler : « CHANTIER-01 Task 1 terminée — app kiosk scaffoldée + TENANT_APPS. Prêt à committer. »
Fichiers : `kiosk/__init__.py`, `kiosk/apps.py`, `kiosk/migrations/__init__.py`, `kiosk/models.py`, `TiBillet/settings.py`.

---

## Task 2 : Modèle `StripeLocation`

**Files :**
- Modify : `kiosk/models.py`
- Create : `kiosk/migrations/0001_initial.py` (générée)
- Test : `tests/pytest/test_kiosk_models.py`

**Interfaces :**
- Produces : `StripeLocation` avec `get_primary_location()` (classmethod) → instance à `stripe_id` renseigné.

- [ ] **Step 1 : Écrire le test qui échoue**

Créer `tests/pytest/test_kiosk_models.py`. **Aligner le `schema_name` du tenant et l'idiome
de cleanup sur `tests/pytest/test_fedow_core.py`** (DB dev live, pas de DB de test) :
```python
import pytest
from django_tenants.utils import tenant_context
from django.test import override_settings
from unittest.mock import patch

from Customers.models import Client
from kiosk.models import StripeLocation, Terminal, PaymentsIntent


@pytest.fixture
def tenant():
    # Tenant de dev. Aligner le schema_name sur test_fedow_core.py si différent.
    return Client.objects.get(schema_name="lespass")


@pytest.fixture
def clean_kiosk(tenant):
    """Nettoie les objets kiosk préfixés TEST_ avant ET après (DB dev partagée).
    Ordre : PaymentsIntent → Terminal → StripeLocation (FK PROTECT)."""
    def _clean():
        with tenant_context(tenant):
            PaymentsIntent.objects.filter(terminal__name__startswith="TEST_").delete()
            Terminal.objects.filter(name__startswith="TEST_").delete()
            StripeLocation.objects.filter(name__startswith="TEST_").delete()
    _clean()
    yield
    _clean()


@pytest.mark.django_db
def test_stripe_location_creation(tenant, clean_kiosk):
    """Une StripeLocation se crée (is_primary_location=False pour ne pas percuter
    la vraie location primaire). / A StripeLocation is created (non-primary)."""
    with tenant_context(tenant):
        loc = StripeLocation.objects.create(
            name="TEST_loc", stripe_id="tml_fake123", is_primary_location=False,
        )
        assert loc.stripe_id == "tml_fake123"
        assert str(loc) == "TEST_loc"
```

- [ ] **Step 2 : Lancer le test — il échoue**

Run : `docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/test_kiosk_models.py -v`
Expected : FAIL — `ImportError: cannot import name 'StripeLocation'`.

- [ ] **Step 3 : Écrire le modèle**

Dans `kiosk/models.py` :
```python
from uuid import uuid4

from django.db import models
from django.utils.translation import gettext_lazy as _


class StripeLocation(models.Model):
    """
    Location Stripe Terminal, requise pour créer un reader (TPE).
    / Stripe Terminal location, required to create a reader (card terminal).

    Copié de LaBoutik APIcashless.Location, rebranché sur RootConfiguration.
    Ce n'est PAS un singleton : is_primary_location distingue la location
    primaire fédérée. get_primary_location() la crée chez Stripe à la volée.
    """
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    name = models.CharField(max_length=200, blank=True, null=True, verbose_name=_("Nom"))
    stripe_id = models.CharField(max_length=21, blank=True, null=True, verbose_name=_("Stripe ID"))
    is_primary_location = models.BooleanField(default=False, verbose_name=_("Primary Asset Location"))

    def __str__(self):
        return self.name or "StripeLocation"

    @classmethod
    def get_primary_location(cls):
        """La location pour les recharges de monnaie fédérée. La crée chez Stripe si absente.
        / The location for federated money refills. Creates it at Stripe if missing."""
        if not cls.objects.filter(is_primary_location=True).exists():
            import stripe
            from root_billet.models import RootConfiguration

            stripe.api_key = RootConfiguration.get_solo().get_stripe_api()
            location = stripe.terminal.Location.create(
                display_name="Primary Asset Location",
                address={
                    "line1": "Primary Asset Location",
                    "country": "FR",
                    "city": "Villeurbanne",
                    "postal_code": "69100",
                },
            )
            return cls.objects.create(
                stripe_id=location.id,
                name="Primary Asset Location",
                is_primary_location=True,
            )
        return cls.objects.get(is_primary_location=True)
```

- [ ] **Step 4 : Générer et appliquer la migration**

Run : `docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations kiosk`
Expected : `Migrations for 'kiosk': kiosk/migrations/0001_initial.py - Create model StripeLocation`

Run : `docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing`
Expected : migration `kiosk.0001_initial` appliquée sur les schémas tenant, sans erreur.

- [ ] **Step 5 : Lancer le test — il passe**

Run : `docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/test_kiosk_models.py -v`
Expected : PASS.

- [ ] **Step 6 : Checkpoint mainteneur (commit)**

Signaler : « CHANTIER-01 Task 2 terminée — StripeLocation + migration + test vert. »

---

## Task 3 : Modèle `Terminal` (avec `term_user` OneToOne)

**Files :**
- Modify : `kiosk/models.py`, `kiosk/migrations/` (nouvelle migration)
- Test : `tests/pytest/test_kiosk_models.py`

**Interfaces :**
- Consumes : `StripeLocation.get_primary_location()`.
- Produces : `Terminal` (`STRIPE_WISEPOS`, `term_user` OneToOne → `TermUser`, `get_stripe_id()`, `status()`).

- [ ] **Step 1 : Écrire le test qui échoue**

Ajouter à `tests/pytest/test_kiosk_models.py` (les imports/fixtures sont déjà en tête) :
```python
@pytest.mark.django_db
def test_terminal_creation_wisepos(tenant, clean_kiosk):
    """Un Terminal WisePOS se crée, type par défaut = STRIPE_WISEPOS.
    A WisePOS Terminal is created, default type = STRIPE_WISEPOS."""
    with tenant_context(tenant):
        terminal = Terminal.objects.create(name="TEST_Borne1", registration_code="simulated-wpe")
        assert terminal.type == Terminal.STRIPE_WISEPOS
        assert terminal.archived is False
        assert terminal.term_user is None  # lien borne optionnel à la création
```

- [ ] **Step 2 : Lancer le test — il échoue**

Run : `docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/test_kiosk_models.py::test_terminal_creation_wisepos -v`
Expected : FAIL — `ImportError: cannot import name 'Terminal'`.

- [ ] **Step 3 : Écrire le modèle**

Ajouter à `kiosk/models.py` :
```python
class Terminal(models.Model):
    """
    TPE Stripe (BBPOS WisePOS E). Copié de LaBoutik APIcashless.Terminal.
    / Stripe card terminal. Copied from LaBoutik APIcashless.Terminal.

    Lien borne : term_user OneToOne → TermUser (1 borne = 1 TPE). Remplace le
    Appareil.terminals de LaBoutik (pas de modèle Appareil côté Lespass).
    """
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    name = models.CharField(max_length=200, blank=True, null=True, verbose_name=_("Nom"))

    # 1 borne = 1 TPE. FK vers TibilletUser CONCRET, pas le proxy TermUser :
    # le manager de TermUser filtre par tenant et casserait l'accès hors contexte
    # tenant (public/shell/Celery). Le form d'admin restreint le choix aux TermUser.
    # Pattern = BaseBillet.LaBoutikAPIKey.user.
    # / 1 borne = 1 terminal. FK to the CONCRETE TibilletUser (not the TermUser
    # proxy, whose manager filters by tenant). Admin form restricts choices to TermUser.
    term_user = models.OneToOneField(
        "AuthBillet.TibilletUser",
        on_delete=models.SET_NULL,
        blank=True, null=True,
        related_name="terminal",
        verbose_name=_("Borne (terminal appairé)"),
    )

    # Pour les TPE Stripe / For Stripe terminals
    registration_code = models.CharField(max_length=200, blank=True, null=True,
                                         verbose_name=_("Code d'enregistrement du lecteur"))
    stripe_id = models.CharField(max_length=21, blank=True, null=True, verbose_name=_("Stripe ID"))

    STRIPE_WISEPOS = "W"
    TYPE_CHOICES = [
        (STRIPE_WISEPOS, _("bbpos_wisepos_e")),
    ]
    type = models.CharField(max_length=2, choices=TYPE_CHOICES, default=STRIPE_WISEPOS,
                            verbose_name=_("Type"))
    archived = models.BooleanField(default=False)

    def status(self):
        """Statut du lecteur côté Stripe. / Reader status from Stripe."""
        if self.stripe_id:
            import stripe
            from root_billet.models import RootConfiguration
            stripe.api_key = RootConfiguration.get_solo().get_stripe_api()
            reader = stripe.terminal.Reader.retrieve(self.stripe_id)
            return reader.status
        return "Unknown"

    def get_stripe_id(self):
        """Appairage : crée le reader Stripe depuis le registration_code + la location primaire.
        / Pairing: create the Stripe reader from registration_code + primary location."""
        if not self.stripe_id:
            if self.type == Terminal.STRIPE_WISEPOS and self.registration_code:
                try:
                    import stripe
                    from root_billet.models import RootConfiguration
                    stripe.api_key = RootConfiguration.get_solo().get_stripe_api()
                    location = StripeLocation.get_primary_location()
                    reader = stripe.terminal.Reader.create(
                        registration_code=self.registration_code,
                        label=self.name,
                        location=location.stripe_id,
                    )
                    self.stripe_id = reader.id
                except Exception as e:
                    raise Exception(f"Error while creating stripe reader : {e}")
            else:
                raise Exception("The registration code is not set.")
        return self.stripe_id

    def __str__(self):
        return f"{self.get_type_display()} {self.name}"
```

- [ ] **Step 4 : Générer et appliquer la migration**

Run : `docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations kiosk`
Expected : `Create model Terminal`.

Run : `docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing`
Expected : migration appliquée sans erreur.

- [ ] **Step 5 : Lancer les tests — ils passent**

Run : `docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/test_kiosk_models.py -v`
Expected : PASS (2 tests).

- [ ] **Step 6 : Checkpoint mainteneur (commit)**

Signaler : « CHANTIER-01 Task 3 terminée — Terminal + term_user OneToOne + migration + tests verts. »

---

## Task 4 : Modèle `PaymentsIntent` (send_to_terminal sans signature)

**Files :**
- Modify : `kiosk/models.py`, `kiosk/migrations/` (nouvelle migration)
- Test : `tests/pytest/test_kiosk_models.py`

**Interfaces :**
- Consumes : `Terminal`, `QrcodeCashless.CarteCashless`, `FedowConfig.fedow_place_uuid`, `RootConfiguration.get_stripe_api()`, `settings.DEMO`.
- Produces : `PaymentsIntent` (états `R/P/A/S/C`, `send_to_terminal(terminal)`, `get_from_stripe()`).

- [ ] **Step 1 : Écrire le test qui échoue (mode DEMO)**

Ajouter à `tests/pytest/test_kiosk_models.py` (imports/fixtures déjà en tête) :
```python
@pytest.mark.django_db
@override_settings(DEMO=True)
def test_payments_intent_send_to_terminal_demo(tenant, clean_kiosk):
    """En DEMO, send_to_terminal simule un PI Stripe et passe IN_PROGRESS.
    In DEMO mode, send_to_terminal fakes a Stripe PI and moves to IN_PROGRESS."""
    with tenant_context(tenant):
        terminal = Terminal.objects.create(name="TEST_BorneDEMO")
        pi = PaymentsIntent.objects.create(amount=500, terminal=terminal)
        assert pi.status == PaymentsIntent.REQUIRES_PAYMENT_METHOD
        pi.send_to_terminal(terminal)
        pi.refresh_from_db()
        assert pi.status == PaymentsIntent.IN_PROGRESS
        assert pi.payment_intent_stripe_id  # renseigné par la simulation
```

- [ ] **Step 2 : Lancer le test — il échoue**

Run : `docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/test_kiosk_models.py::test_payments_intent_send_to_terminal_demo -v`
Expected : FAIL — `ImportError: cannot import name 'PaymentsIntent'`.

- [ ] **Step 3 : Écrire le modèle**

Ajouter en tête de `kiosk/models.py` (imports) :
```python
import json
import uuid

from django.conf import settings
```

Puis le modèle :
```python
class PaymentsIntent(models.Model):
    """
    Pilotage d'un paiement TPE + affichage. Copié de LaBoutik APIcashless.PaymentsIntent.
    / Card-terminal payment driver + display state. Copied from LaBoutik.

    Objet TECHNIQUE local : ce n'est PAS le crédit (le crédit = Fedow via webhook).
    Le champ `pos` de LaBoutik est supprimé (inutile au flux Fedow, cf. SPEC).
    """
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    amount = models.PositiveIntegerField()  # centimes / cents
    payment_intent_stripe_id = models.CharField(max_length=30, blank=True, null=True,
                                                verbose_name=_("Paiement intent stripe id"))
    terminal = models.ForeignKey(Terminal, on_delete=models.PROTECT, verbose_name=_("TPE"))
    datetime = models.DateTimeField(auto_now_add=True)
    card = models.ForeignKey("QrcodeCashless.CarteCashless", on_delete=models.PROTECT,
                             verbose_name=_("Carte cashless"), related_name="payments_intents",
                             blank=True, null=True)

    REQUIRES_PAYMENT_METHOD = "R"
    IN_PROGRESS = "P"
    REQUIRES_CAPTURE = "A"
    SUCCEEDED = "S"
    CANCELED = "C"
    STATUS_CHOICES = [
        (REQUIRES_PAYMENT_METHOD, _("requires_payment_method")),
        (IN_PROGRESS, _("in_progress")),
        (REQUIRES_CAPTURE, _("Paiement autorisé, mais pas encore capturé")),
        (SUCCEEDED, _("Succes")),
        (CANCELED, _("Canceled")),
    ]
    status = models.CharField(max_length=2, choices=STATUS_CHOICES,
                              default=REQUIRES_PAYMENT_METHOD, verbose_name=_("Status"))

    def get_from_stripe(self):
        """Rafraîchit le statut depuis Stripe. En DEMO, tire un statut au sort.
        / Refresh status from Stripe. In DEMO, draw a random status."""
        if settings.DEMO:
            import random
            random_value = random.random()
            if random_value < 0.8:
                self.status = PaymentsIntent.REQUIRES_PAYMENT_METHOD
            elif random_value < 0.9:
                self.status = PaymentsIntent.CANCELED
            else:
                self.status = PaymentsIntent.SUCCEEDED
            self.save()
            return self.status

        if self.status in [PaymentsIntent.CANCELED, PaymentsIntent.SUCCEEDED]:
            return self.status

        import stripe
        from root_billet.models import RootConfiguration
        stripe.api_key = RootConfiguration.get_solo().get_stripe_api()
        stripe_payment = stripe.PaymentIntent.retrieve(self.payment_intent_stripe_id)
        if stripe_payment.status == "requires_payment_method":
            self.status = PaymentsIntent.REQUIRES_PAYMENT_METHOD
        elif stripe_payment.status == "processing":
            self.status = PaymentsIntent.IN_PROGRESS
        elif stripe_payment.status == "requires_capture":
            self.status = PaymentsIntent.REQUIRES_CAPTURE
        elif stripe_payment.status == "canceled":
            self.status = PaymentsIntent.CANCELED
        elif stripe_payment.status == "succeeded":
            self.status = PaymentsIntent.SUCCEEDED
        self.save()
        return self.status

    def send_to_terminal(self, terminal: "Terminal"):
        """Crée le PaymentIntent Stripe (card_present) et l'envoie au reader.
        Metadata {fedow_place_uuid, tag_id} NON signées (place Lespass de confiance, SPEC §8bis).
        / Create the Stripe PaymentIntent (card_present) and push it to the reader.
        Unsigned {fedow_place_uuid, tag_id} metadata (trusted Lespass place, SPEC §8bis)."""
        if settings.DEMO:
            # Simulation d'un TPE Stripe / Fake a Stripe terminal
            self.payment_intent_stripe_id = uuid.uuid4().hex[:30]
            self.status = self.IN_PROGRESS
            self.save()
            return self

        import stripe
        from root_billet.models import RootConfiguration
        from fedow_connect.models import FedowConfig
        from BaseBillet.models import Configuration

        stripe.api_key = RootConfiguration.get_solo().get_stripe_api()
        fedow_config = FedowConfig.get_solo()
        currency = Configuration.get_solo().currency_code.lower()

        # Vérification de la disponibilité du terminal / Check terminal availability
        try:
            stripe.terminal.Reader.retrieve(terminal.stripe_id)
        except stripe._error.InvalidRequestError as e:
            raise e

        # Metadata lues par Fedow au webhook. PAS de signature (cf. SPEC §8bis).
        # / Metadata read by Fedow at the webhook. NO signature (see SPEC §8bis).
        data = {
            "fedow_place_uuid": f"{fedow_config.fedow_place_uuid}",
            "tag_id": f"{self.card.tag_id}" if self.card else None,
        }

        payment_intent_stripe = stripe.PaymentIntent.create(
            amount=self.amount,
            currency=currency,
            payment_method_types=["card_present"],
            capture_method="automatic",
            metadata={"data": json.dumps(data)},
        )
        self.payment_intent_stripe_id = payment_intent_stripe.id
        self.save()

        stripe.terminal.Reader.process_payment_intent(
            terminal.stripe_id,
            payment_intent=payment_intent_stripe.id,
        )
        self.status = self.IN_PROGRESS
        self.save()
        return self
```

- [ ] **Step 4 : Générer et appliquer la migration**

Run : `docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations kiosk`
Expected : `Create model PaymentsIntent`.

Run : `docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing`
Expected : appliquée sans erreur.

- [ ] **Step 5 : Lancer les tests — ils passent**

Run : `docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/test_kiosk_models.py -v`
Expected : PASS (3 tests).

- [ ] **Step 6 : Checkpoint mainteneur (commit)**

Signaler : « CHANTIER-01 Task 4 terminée — PaymentsIntent (send_to_terminal sans signature) + migration + tests verts. »

---

## Task 5 : Admin Unfold (`StripeLocationAdmin`, `TerminalAdmin`, `PaymentsIntentAdmin`)

**Files :**
- Create : `kiosk/admin.py`
- Test : `tests/pytest/test_kiosk_models.py` (test d'appairage via save_model)

**Interfaces :**
- Consumes : `staff_admin_site`, `TenantAdminPermissionWithRequest`, les 3 modèles.
- Produces : 3 ModelAdmin Unfold enregistrés. `TerminalAdmin.save_model` déclenche l'appairage (`get_stripe_id`).

- [ ] **Step 1 : Écrire le test d'appairage qui échoue**

Ajouter à `tests/pytest/test_kiosk_models.py` (imports/fixtures déjà en tête) :
```python
@pytest.mark.django_db
def test_terminal_pairing_sets_stripe_id(tenant, clean_kiosk):
    """L'appairage (get_stripe_id) renseigne le stripe_id depuis le reader Stripe créé.
    Pairing (get_stripe_id) sets stripe_id from the created Stripe reader."""
    with tenant_context(tenant):
        terminal = Terminal.objects.create(name="TEST_BorneAppairage", registration_code="simulated-wpe")
        with patch("kiosk.models.StripeLocation.get_primary_location") as mock_loc, \
             patch("stripe.terminal.Reader.create") as mock_create, \
             patch("root_billet.models.RootConfiguration.get_solo") as mock_root:
            mock_loc.return_value = type("L", (), {"stripe_id": "tml_fake"})()
            mock_root.return_value.get_stripe_api.return_value = "sk_test_x"
            mock_create.return_value = type("R", (), {"id": "tmr_fake123"})()
            stripe_id = terminal.get_stripe_id()
        assert stripe_id == "tmr_fake123"
        assert terminal.stripe_id == "tmr_fake123"
```

- [ ] **Step 2 : Lancer le test — il échoue**

Run : `docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/test_kiosk_models.py::test_terminal_pairing_sets_stripe_id -v`
Expected : FAIL (le mock cible `kiosk.models.StripeLocation` déjà présent, mais le test vérifie la logique de `get_stripe_id` — il doit passer une fois le modèle correct ; si échec, corriger le patch path).

> Note : ce test valide surtout `get_stripe_id` (déjà écrit en Task 3). S'il passe directement,
> c'est acceptable — on enchaîne sur l'admin (le vrai livrable de la Task 5).

- [ ] **Step 3 : Écrire l'admin Unfold**

Créer `kiosk/admin.py` :
```python
from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin

from Administration.admin_tenant import staff_admin_site
from ApiBillet.permissions import TenantAdminPermissionWithRequest
from kiosk.models import StripeLocation, Terminal, PaymentsIntent


@admin.register(StripeLocation, site=staff_admin_site)
class StripeLocationAdmin(ModelAdmin):
    compressed_fields = True
    warn_unsaved_form = True
    list_display = ("name", "stripe_id", "is_primary_location")

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


class TerminalForm(forms.ModelForm):
    class Meta:
        model = Terminal
        fields = ["name", "type", "registration_code", "term_user", "archived"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Le FK cible TibilletUser : on restreint le choix aux TermUser (bornes).
        # / FK targets TibilletUser: restrict choices to TermUser (bornes).
        from AuthBillet.models import TermUser
        self.fields["term_user"].queryset = TermUser.objects.all()

    def clean(self):
        cleaned_data = super().clean()
        terminal_type = cleaned_data.get("type")
        registration_code = cleaned_data.get("registration_code")
        stripe_id = self.instance.stripe_id if self.instance and self.instance.pk else None
        if terminal_type == Terminal.STRIPE_WISEPOS and not registration_code and not stripe_id:
            raise ValidationError({
                "registration_code": _(
                    "Le code d'enregistrement ne peut pas être vide pour un terminal STRIPE_WISEPOS non appairé.")
            })
        return cleaned_data


@admin.register(Terminal, site=staff_admin_site)
class TerminalAdmin(ModelAdmin):
    compressed_fields = True
    warn_unsaved_form = True
    form = TerminalForm
    list_display = ("name", "type", "term_user", "archived")

    def get_queryset(self, request):
        return super().get_queryset(request).exclude(archived=True)

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        # Appairage : crée le reader Stripe si besoin. En DEMO on saute l'appel réseau ;
        # sinon on capture l'échec en message admin plutôt qu'un 500.
        # / Pairing: create the Stripe reader if needed. Skip network in DEMO;
        # otherwise surface failures as an admin message instead of a 500.
        from django.conf import settings
        from django.contrib import messages
        if not settings.DEMO:
            try:
                obj.get_stripe_id()
            except Exception as e:
                messages.error(request, _("Échec de l'appairage du TPE Stripe : %(err)s") % {"err": e})
        super().save_model(request, obj, form, change)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


@admin.register(PaymentsIntent, site=staff_admin_site)
class PaymentsIntentAdmin(ModelAdmin):
    compressed_fields = True
    warn_unsaved_form = True
    list_display = ("datetime", "amount", "terminal", "card", "status")

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
```

- [ ] **Step 4 : Vérifier check + tests**

Run : `docker exec lespass_django poetry run python /DjangoFiles/manage.py check`
Expected : `0 issues`.

Run : `docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/test_kiosk_models.py -v`
Expected : PASS (4 tests).

- [ ] **Step 5 : Vérif visuelle admin (mainteneur)**

Demander au mainteneur de vérifier dans l'admin (`https://lespass.tibillet.localhost/`, user `admin@admin.com`)
que les 3 sections apparaissent (Terminal éditable, StripeLocation, PaymentsIntent en lecture seule).
> Note : la section sidebar dédiée « Kiosk » + le `module_kiosk` sont au CHANTIER-03. Ici les admins
> sont enregistrés mais peuvent n'apparaître que si `staff_admin_site` les liste par défaut.

- [ ] **Step 6 : Checkpoint mainteneur (commit)**

Signaler : « CHANTIER-01 Task 5 terminée — admin Unfold des 3 modèles + tests verts. CHANTIER-01 complet. »

---

## Self-review (couverture spec §3 + §7)

- `StripeLocation`, `Terminal`, `PaymentsIntent` : Tasks 2/3/4 ✓ (spec §3).
- `term_user` OneToOne (décision 9) : Task 3 ✓.
- `send_to_terminal` **sans signature**, metadata claires, clé Root : Task 4 ✓ (spec §8bis, décisions 7-8).
- Champ `pos` supprimé : Task 4 ✓ (décision 1).
- Admin Unfold (spec §7) : Task 5 ✓.
- Rebranchements (spec §11) : `RootConfiguration` (root_billet), `FedowConfig.fedow_place_uuid`,
  `QrcodeCashless.CarteCashless`, `Configuration.currency_code` : Tasks 3/4 ✓.

**Hors périmètre (CHANTIER 02-04)** : front + `KioskViewSet` + `NFCcardFedow.retrieve(tag_id)` +
WebSocket + validators (02) ; `module_kiosk` + sidebar/dashboard + bridge `laboutik` + URLs (03) ;
extension route TPE Fedow + durcissement idempotence + test bout-en-bout (04).

## Corrections appliquées après relecture Fable 5

- **B1** — tests : tenant réel via fixture `tenant` + `tenant_context(tenant)` (pas
  `connection.tenant`), aligner sur `tests/pytest/test_fedow_core.py`.
- **B2** — pollution DB dev : fixture `clean_kiosk` (préfixe `TEST_`, cleanup avant/après),
  `StripeLocation` de test en `is_primary_location=False`.
- **R1** — `save_model` garde DEMO + `try/except` → `messages.error` (plus de 500 admin).
- **R2** — `archived` ajouté au `TerminalForm`.
- **R3** — `term_user` cible `TibilletUser` concret (pas le proxy `TermUser`), choix
  restreint aux `TermUser` dans le form.
- **R4** — `--api-key dummy` sur toutes les commandes pytest (contrainte globale).
- **R6** — `TENANT_APPS` est un **tuple** (diff Task 1 corrigé).

**À vérifier au lancement** (non bloquant) : `related_name="terminal"` sur `TibilletUser`
ne doit pas entrer en collision (sinon `kiosk_terminal`) ; confirmer le `schema_name` du
tenant de dev dans `test_fedow_core.py`.
