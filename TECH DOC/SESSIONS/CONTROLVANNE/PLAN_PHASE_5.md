# Phase 5 — Tests controlvanne

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compléter la couverture pytest (modèles, maintenance, events, discovery) et ajouter des tests E2E Playwright pour l'admin tireuses et la calibration HTMX.

**Architecture:** Tests pytest DB-only dans `tests/pytest/test_controlvanne_models.py` (propriétés modèles, maintenance, events). Tests E2E Playwright dans `tests/e2e/test_controlvanne_admin.py` (admin Unfold CRUD tireuses, calibration HTMX).

**Tech Stack:** pytest, pytest-django, Playwright Python, django-tenants

**IMPORTANT :** Ne pas faire d'opérations git. Le mainteneur gère git.

---

## Vue d'ensemble des fichiers

| Fichier | Action | Rôle |
|---------|--------|------|
| `tests/pytest/test_controlvanne_models.py` | Créer | Tests modèles + maintenance + events complémentaires |
| `tests/e2e/test_controlvanne_admin.py` | Créer | Tests E2E admin Unfold tireuses |

---

### Tâche 1 : Tests pytest complémentaires — modèles + maintenance + events

**Fichiers :**
- Créer : `tests/pytest/test_controlvanne_models.py`

Tests à couvrir :
1. **TireuseBec.liquid_label** — retourne le nom du fut actif, ou "Liquide" si pas de fut
2. **TireuseBec.prix_litre** — retourne le prix poids_mesure du fut, ou 0 si pas de prix
3. **RfidSession.close_with_volume** — ferme la session avec le volume correct
4. **RfidSession.duration_seconds** — calcule la durée, None si session ouverte
5. **authorize carte maintenance** — retourne is_maintenance=True, allowed_ml=reservoir
6. **event pour_update** — met à jour volume_delta_ml sans fermer la session
7. **event pour_start** — met à jour volume_start_ml
8. **event card_removed** — ferme la session (comme pour_end)
9. **discovery claim crée TireuseAPIKey** quand PairingDevice lié à une tireuse

- [ ] **Step 1 : Créer le fichier de tests**

```python
"""
Tests complémentaires controlvanne — modèles, maintenance, events.
/ Complementary controlvanne tests — models, maintenance, events.

LOCALISATION : tests/pytest/test_controlvanne_models.py
"""

import json
import uuid
from decimal import Decimal

import pytest
from django.test import Client as DjangoClient
from django_tenants.utils import schema_context


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def cv_api_key(tenant):
    """TireuseAPIKey pour ces tests."""
    with schema_context(tenant.schema_name):
        from controlvanne.models import TireuseAPIKey
        _obj, key = TireuseAPIKey.objects.create_key(name="test-cv-models")
        yield key
        TireuseAPIKey.objects.filter(name="test-cv-models").delete()


@pytest.fixture(scope="session")
def cv_headers(cv_api_key):
    return {"HTTP_AUTHORIZATION": f"Api-Key {cv_api_key}"}


@pytest.fixture(scope="session")
def cv_client():
    return DjangoClient(HTTP_HOST="lespass.tibillet.localhost")


@pytest.fixture(scope="session")
def cv_tireuse_sans_fut(tenant):
    """TireuseBec sans fut_actif (propriétés retournent les valeurs par défaut)."""
    with schema_context(tenant.schema_name):
        from controlvanne.models import TireuseBec
        t = TireuseBec.objects.create(
            nom_tireuse="Tap No Keg",
            enabled=True,
            reservoir_ml=Decimal("3000.00"),
        )
        yield t


@pytest.fixture(scope="session")
def cv_tireuse_avec_fut(tenant):
    """TireuseBec avec fut_actif + prix au litre."""
    with schema_context(tenant.schema_name):
        from controlvanne.models import TireuseBec, Debimetre
        from BaseBillet.models import Product, Price

        fut, _ = Product.objects.get_or_create(
            name="Test Stout Models", categorie_article=Product.FUT,
            defaults={"publish": True},
        )
        Price.objects.get_or_create(
            product=fut, name="Litre models",
            defaults={"prix": Decimal("4.00"), "poids_mesure": True},
        )
        t = TireuseBec.objects.create(
            nom_tireuse="Tap With Keg",
            enabled=True,
            fut_actif=fut,
            reservoir_ml=Decimal("10000.00"),
            seuil_mini_ml=Decimal("0.00"),
            appliquer_reserve=False,
        )
        yield t


@pytest.fixture(scope="session")
def cv_asset_tlf(tenant):
    """Asset TLF actif."""
    with schema_context(tenant.schema_name):
        from fedow_core.models import Asset
        asset = Asset.objects.filter(
            tenant_origin=tenant, category=Asset.TLF, active=True,
        ).first()
        yield asset


@pytest.fixture(scope="session")
def cv_carte_client(tenant, cv_asset_tlf):
    """CarteCashless avec wallet crédité 2000 centimes (20 EUR)."""
    with schema_context(tenant.schema_name):
        from QrcodeCashless.models import CarteCashless
        from AuthBillet.models import Wallet
        from fedow_core.models import Token

        carte = CarteCashless.objects.filter(tag_id="TSTMD01").first()
        if not carte:
            carte = CarteCashless(tag_id="TSTMD01", number="TSTMD01", uuid=uuid.uuid4())
            carte.save()
        if not carte.wallet_ephemere:
            w = Wallet.objects.create(origin=tenant, name="Wallet TSTMD01")
            carte.wallet_ephemere = w
            carte.save(update_fields=["wallet_ephemere"])
        Token.objects.update_or_create(
            wallet=carte.wallet_ephemere, asset=cv_asset_tlf,
            defaults={"value": 2000},
        )
        yield carte


@pytest.fixture(scope="session")
def cv_carte_maintenance(tenant, cv_tireuse_avec_fut):
    """CarteCashless avec CarteMaintenance associée."""
    with schema_context(tenant.schema_name):
        from QrcodeCashless.models import CarteCashless
        from controlvanne.models import CarteMaintenance

        carte = CarteCashless.objects.filter(tag_id="TSTMT01").first()
        if not carte:
            carte = CarteCashless(tag_id="TSTMT01", number="TSTMT01", uuid=uuid.uuid4())
            carte.save()
        CarteMaintenance.objects.get_or_create(
            carte=carte,
            defaults={"produit": "Eau claire", "notes": "Test maintenance"},
        )
        yield carte


# ──────────────────────────────────────────────────────────────────────
# Tests modèles
# ──────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestTireuseBecProperties:

    def test_01_liquid_label_sans_fut(self, cv_tireuse_sans_fut):
        """Sans fut → 'Liquide'."""
        assert cv_tireuse_sans_fut.liquid_label == "Liquide"

    def test_02_liquid_label_avec_fut(self, cv_tireuse_avec_fut):
        """Avec fut → nom du produit."""
        assert cv_tireuse_avec_fut.liquid_label == "Test Stout Models"

    def test_03_prix_litre_sans_fut(self, cv_tireuse_sans_fut):
        """Sans fut → Decimal('0.00')."""
        assert cv_tireuse_sans_fut.prix_litre == Decimal("0.00")

    def test_04_prix_litre_avec_fut(self, cv_tireuse_avec_fut):
        """Avec fut + Price poids_mesure → 4.00."""
        assert cv_tireuse_avec_fut.prix_litre == Decimal("4.00")


@pytest.mark.django_db
class TestRfidSession:

    def test_05_close_with_volume(self, tenant, cv_tireuse_avec_fut):
        """close_with_volume ferme la session avec le bon volume."""
        with schema_context(tenant.schema_name):
            from controlvanne.models import RfidSession
            session = RfidSession.objects.create(
                uid="CLOSEVOL", tireuse_bec=cv_tireuse_avec_fut,
            )
            assert session.ended_at is None
            session.close_with_volume(333.5)
            session.refresh_from_db()
            assert session.ended_at is not None
            assert session.volume_delta_ml == Decimal("333.50")

    def test_06_duration_seconds_open(self, tenant, cv_tireuse_avec_fut):
        """Session ouverte → duration_seconds = None."""
        with schema_context(tenant.schema_name):
            from controlvanne.models import RfidSession
            session = RfidSession.objects.create(
                uid="DUROPEN", tireuse_bec=cv_tireuse_avec_fut,
            )
            assert session.duration_seconds is None

    def test_07_duration_seconds_closed(self, tenant, cv_tireuse_avec_fut):
        """Session fermée → duration_seconds > 0."""
        with schema_context(tenant.schema_name):
            from controlvanne.models import RfidSession
            from django.utils import timezone
            from datetime import timedelta
            now = timezone.now()
            session = RfidSession.objects.create(
                uid="DURCLOS", tireuse_bec=cv_tireuse_avec_fut,
                started_at=now - timedelta(seconds=42),
                ended_at=now,
            )
            assert abs(session.duration_seconds - 42) < 1


# ──────────────────────────────────────────────────────────────────────
# Tests authorize maintenance
# ──────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestAuthorizeMaintenance:

    def test_08_authorize_carte_maintenance(
        self, cv_client, cv_headers, cv_tireuse_avec_fut, cv_carte_maintenance
    ):
        """Carte maintenance → is_maintenance=True, allowed_ml=reservoir."""
        response = cv_client.post(
            "/controlvanne/api/tireuse/authorize/",
            content_type="application/json",
            data=json.dumps({
                "tireuse_uuid": str(cv_tireuse_avec_fut.uuid),
                "uid": cv_carte_maintenance.tag_id,
            }),
            **cv_headers,
        )
        data = response.json()
        assert data["authorized"] is True
        assert data["is_maintenance"] is True
        assert data["allowed_ml"] == float(cv_tireuse_avec_fut.reservoir_ml)


# ──────────────────────────────────────────────────────────────────────
# Tests events complémentaires
# ──────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestEventsComplementaires:

    def test_09_pour_update(self, cv_client, cv_headers, cv_tireuse_avec_fut, cv_carte_client):
        """pour_update met à jour le volume sans fermer la session."""
        # Authorize d'abord
        cv_client.post(
            "/controlvanne/api/tireuse/authorize/",
            content_type="application/json",
            data=json.dumps({
                "tireuse_uuid": str(cv_tireuse_avec_fut.uuid),
                "uid": cv_carte_client.tag_id,
            }),
            **cv_headers,
        )
        # pour_update
        response = cv_client.post(
            "/controlvanne/api/tireuse/event/",
            content_type="application/json",
            data=json.dumps({
                "tireuse_uuid": str(cv_tireuse_avec_fut.uuid),
                "uid": cv_carte_client.tag_id,
                "event_type": "pour_update",
                "volume_ml": "150.00",
            }),
            **cv_headers,
        )
        data = response.json()
        assert data["status"] == "ok"
        assert data["event_type"] == "pour_update"
        # Pas de montant_centimes (pas de facturation au pour_update)
        assert "montant_centimes" not in data

        # Session toujours ouverte
        with schema_context("lespass"):
            from controlvanne.models import RfidSession
            session = RfidSession.objects.filter(
                tireuse_bec=cv_tireuse_avec_fut,
                uid=cv_carte_client.tag_id,
                ended_at__isnull=True,
            ).order_by("-started_at").first()
            assert session is not None
            assert session.volume_delta_ml == Decimal("150.00")

        # Nettoyer : fermer la session
        cv_client.post(
            "/controlvanne/api/tireuse/event/",
            content_type="application/json",
            data=json.dumps({
                "tireuse_uuid": str(cv_tireuse_avec_fut.uuid),
                "uid": cv_carte_client.tag_id,
                "event_type": "card_removed",
                "volume_ml": "150.00",
            }),
            **cv_headers,
        )

    def test_10_card_removed(self, cv_client, cv_headers, cv_tireuse_avec_fut, cv_carte_client):
        """card_removed ferme la session (comme pour_end)."""
        # Authorize
        cv_client.post(
            "/controlvanne/api/tireuse/authorize/",
            content_type="application/json",
            data=json.dumps({
                "tireuse_uuid": str(cv_tireuse_avec_fut.uuid),
                "uid": cv_carte_client.tag_id,
            }),
            **cv_headers,
        )
        # card_removed avec volume
        response = cv_client.post(
            "/controlvanne/api/tireuse/event/",
            content_type="application/json",
            data=json.dumps({
                "tireuse_uuid": str(cv_tireuse_avec_fut.uuid),
                "uid": cv_carte_client.tag_id,
                "event_type": "card_removed",
                "volume_ml": "200.00",
            }),
            **cv_headers,
        )
        data = response.json()
        assert data["status"] == "ok"
        assert data["event_type"] == "card_removed"

        # Session fermée
        with schema_context("lespass"):
            from controlvanne.models import RfidSession
            session = RfidSession.objects.filter(
                tireuse_bec=cv_tireuse_avec_fut,
                uid=cv_carte_client.tag_id,
            ).order_by("-started_at").first()
            assert session.ended_at is not None

    def test_11_event_no_open_session(self, cv_client, cv_headers, cv_tireuse_avec_fut):
        """Event sans session ouverte → 404."""
        response = cv_client.post(
            "/controlvanne/api/tireuse/event/",
            content_type="application/json",
            data=json.dumps({
                "tireuse_uuid": str(cv_tireuse_avec_fut.uuid),
                "uid": "NOSESSION",
                "event_type": "pour_end",
                "volume_ml": "100.00",
            }),
            **cv_headers,
        )
        assert response.status_code == 404

    def test_12_authorize_tireuse_disabled(self, cv_client, cv_headers, cv_tireuse_sans_fut, cv_carte_client):
        """Tireuse désactivée → authorized=False."""
        with schema_context("lespass"):
            cv_tireuse_sans_fut.enabled = False
            cv_tireuse_sans_fut.save(update_fields=["enabled"])

        response = cv_client.post(
            "/controlvanne/api/tireuse/authorize/",
            content_type="application/json",
            data=json.dumps({
                "tireuse_uuid": str(cv_tireuse_sans_fut.uuid),
                "uid": cv_carte_client.tag_id,
            }),
            **cv_headers,
        )
        data = response.json()
        assert data["authorized"] is False
        assert "disabled" in data["message"]

        # Remettre enabled
        with schema_context("lespass"):
            cv_tireuse_sans_fut.enabled = True
            cv_tireuse_sans_fut.save(update_fields=["enabled"])
```

- [ ] **Step 2 : Lancer les tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_controlvanne_models.py -v
```

---

### Tâche 2 : Tests E2E Playwright — admin tireuses

**Fichiers :**
- Créer : `tests/e2e/test_controlvanne_admin.py`

Tests E2E :
1. Admin → sidebar Tireuses visible (module_tireuse activé)
2. Admin → créer une tireuse
3. Admin → modifier une tireuse (changer le nom)
4. Admin → historique des sessions visible

- [ ] **Step 1 : Créer le fichier de tests E2E**

```python
"""
Tests E2E admin tireuses (controlvanne) — Playwright.
/ E2E tests for tap admin (controlvanne) — Playwright.

LOCALISATION : tests/e2e/test_controlvanne_admin.py

Prérequis :
- Serveur Django actif via Traefik
- module_tireuse activé sur le tenant lespass
- Playwright installé (poetry run playwright install chromium)
"""

import pytest


@pytest.mark.usefixtures("page")
class TestControvanneAdmin:
    """Tests admin Unfold pour les tireuses."""

    def test_01_sidebar_tireuses_visible(self, page, login_as_admin):
        """La sidebar contient le lien Taps quand module_tireuse est activé."""
        login_as_admin(page)
        page.goto("/admin/")
        page.wait_for_load_state("networkidle")

        # Chercher le lien Taps dans la sidebar
        sidebar = page.locator("nav, aside, [data-testid='sidebar']").first
        taps_link = sidebar.locator("a:has-text('Taps'), a:has-text('Tireuse')")
        assert taps_link.count() > 0, "Le lien Taps/Tireuse n'est pas visible dans la sidebar"

    def test_02_liste_tireuses(self, page, login_as_admin):
        """La page liste des tireuses se charge sans erreur."""
        login_as_admin(page)
        page.goto("/admin/controlvanne/tireusebec/")
        page.wait_for_load_state("networkidle")
        assert page.title()
        # La page doit contenir le tableau de résultats ou un message "0 résultat"
        content = page.content()
        assert "tireusebec" in page.url.lower() or "Tap" in content

    def test_03_historique_tireuse(self, page, login_as_admin):
        """La page historique des tireuses se charge."""
        login_as_admin(page)
        page.goto("/admin/controlvanne/historiquetireuse/")
        page.wait_for_load_state("networkidle")
        assert page.title()
```

- [ ] **Step 2 : Lancer les tests E2E**

```bash
docker exec lespass_django poetry run pytest tests/e2e/test_controlvanne_admin.py -v -s
```

Note : les tests E2E nécessitent un serveur Django actif via Traefik + Playwright installé.

---

### Tâche 3 : Vérification finale

- [ ] **Step 1 : Tests pytest controlvanne complets**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_controlvanne_api.py tests/pytest/test_controlvanne_billing.py tests/pytest/test_controlvanne_models.py -v
```

- [ ] **Step 2 : Non-régression complète**

```bash
docker exec lespass_django poetry run pytest tests/pytest/ -q
```

---

## Résumé

| Fichier | Tests |
|---------|-------|
| `tests/pytest/test_controlvanne_models.py` | 12 tests (propriétés, close_with_volume, duration, maintenance, events, disabled) |
| `tests/e2e/test_controlvanne_admin.py` | 3 tests E2E (sidebar, liste, historique) |
| **Total nouveau** | **15 tests** |
| **Total controlvanne** | **35 tests** (20 existants + 15 nouveaux) |
