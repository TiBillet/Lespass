# Auth Hardware TermUser — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Authentifier les terminaux LaBoutik (POS + Android) via un TermUser Django et un pont `/laboutik/auth/bridge/` qui échange une clé API contre un cookie de session, tout en gardant `HasLaBoutikAccess` V1 intouchée.

**Architecture:** Ajout d'un `terminal_role` sur `TibilletUser` et `PairingDevice`, liaison `OneToOneField` nullable `LaBoutikAPIKey.user → TibilletUser`, nouvelle `HasLaBoutikTerminalAccess` par-dessus la V1 (fallback intégré), endpoint bridge qui fait un `django.contrib.auth.login()` natif. Révocation instantanée via `user.is_active=False`.

**Tech Stack:** Django 5 + DRF + django-tenants + rest_framework_api_key + Django sessions natives + Unfold admin.

**Spec de référence :** `TECH DOC/Laboutik sessions/Session 30 - Auth hardware TermUser/SPEC_AUTH_HARDWARE.md`

---

## File Structure

### Fichiers à CRÉER

| Chemin | Responsabilité |
|---|---|
| `tests/pytest/test_hardware_auth_bridge.py` | Tests du nouveau endpoint bridge |
| `tests/pytest/test_discovery_claim_creates_termuser.py` | Tests du flow claim modifié |
| `tests/e2e/test_laboutik_auth_bridge.py` | Test Playwright E2E du flow complet |
| `Administration/templates/admin/termuser/change_form_before.html` | Bouton "Revoke this terminal" dans admin Unfold |
| `A TESTER et DOCUMENTER/hardware-auth-bridge.md` | Checklist manuelle de test |

### Fichiers à MODIFIER

| Chemin | Changement |
|---|---|
| `AuthBillet/models.py` | +TERMINAL_ROLE_CHOICES, +terminal_role field, TermUser.save() |
| `AuthBillet/migrations/00XX_*.py` | Nouvelle migration AddField |
| `discovery/models.py` | +terminal_role sur PairingDevice |
| `discovery/migrations/00XX_*.py` | Nouvelle migration AddField |
| `discovery/views.py` | ClaimPinView route selon terminal_role, +helper _create_laboutik_terminal |
| `BaseBillet/models.py` | LaBoutikAPIKey.user OneToOneField nullable |
| `BaseBillet/migrations/00XX_*.py` | Nouvelle migration AddField |
| `BaseBillet/permissions.py` | +HasLaBoutikTerminalAccess (HasLaBoutikAccess inchangée) |
| `laboutik/views.py` | +LaBoutikAuthBridgeView (APIView DRF) |
| `laboutik/urls.py` | +path auth/bridge/ |
| `Administration/admin_tenant.py` | +TermUserAdmin + entrée sidebar Terminals |
| `tests/pytest/conftest.py` | +fixture terminal_client |
| `tests/PIEGES.md` | +pièges 9.45-9.47 |
| `CHANGELOG.md` | +entrée Auth hardware TermUser |

---

## Notes critiques pour l'implémenteur

**Contexte Django multi-tenant :**
- `TibilletUser` est dans `AuthBillet` (SHARED_APPS) → modifications sur le schéma `public`, visibles par tous les tenants
- `LaBoutikAPIKey` est dans `BaseBillet` (TENANT_APPS) → modifications par tenant
- `PairingDevice` est dans `discovery` (SHARED_APPS) → schéma `public`
- Toujours utiliser `migrate_schemas --executor=multiprocessing` pour appliquer les migrations

**Ne jamais toucher `HasLaBoutikAccess` :** cette permission V1 doit rester strictement identique. Seule `HasLaBoutikTerminalAccess` est nouvelle.

**Workflow Docker :** le projet tourne dans `docker exec lespass_django poetry run ...`. Tous les commandes de test et migrations passent par là.

**Git :** le mainteneur gère les commits manuellement. Les "Commit" steps dans ce plan indiquent **où** il est pertinent de committer, mais n'exécute pas `git commit`. Juste annoncer qu'un checkpoint de commit est atteint.

---

## Task 1 : Ajouter `terminal_role` sur `TibilletUser`

**Files:**
- Modify: `AuthBillet/models.py:148-170` (enum TYPE_* et ESPECE_CHOICES)
- Create: `AuthBillet/migrations/00XX_terminal_role.py` (via makemigrations)

- [ ] **Step 1 : Ajouter les choices et le champ dans le modèle**

Éditer `AuthBillet/models.py`, juste après les lignes 148-157 (enum `ESPECE_CHOICES`) :

```python
    TYPE_TERM, TYPE_HUM, TYPE_ANDR = 'TE', 'HU', 'AN'
    ESPECE_CHOICES = (
        (TYPE_TERM, _('Terminal')),
        (TYPE_ANDR, _('Android')),
        (TYPE_HUM, _('Human')),
    )

    espece = models.CharField(max_length=2,
                              choices=ESPECE_CHOICES,
                              default=TYPE_HUM)

    # Rôles des terminaux hardware (uniquement renseigné si espece=TE)
    # Hardware terminal roles (only set when espece=TE)
    ROLE_LABOUTIK = 'LB'
    ROLE_TIREUSE = 'TI'
    ROLE_KIOSQUE = 'KI'
    TERMINAL_ROLE_CHOICES = (
        (ROLE_LABOUTIK, _('LaBoutik POS')),
        (ROLE_TIREUSE, _('Connected tap')),
        (ROLE_KIOSQUE, _('Kiosk / self-service')),
    )

    terminal_role = models.CharField(
        max_length=2,
        choices=TERMINAL_ROLE_CHOICES,
        null=True, blank=True,
        verbose_name=_("Terminal role"),
        help_text=_("Only set for espece=TE. Drives permission checks."),
    )
```

- [ ] **Step 2 : Générer la migration**

Run : `docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations AuthBillet`

Expected : création d'un fichier `AuthBillet/migrations/00XX_terminal_role.py` avec `AddField` sur `terminal_role`.

- [ ] **Step 3 : Appliquer la migration sur tous les schémas**

Run : `docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing`

Expected : migration appliquée sur `public` et tous les tenants sans erreur.

- [ ] **Step 4 : Vérifier avec `manage.py check`**

Run : `docker exec lespass_django poetry run python /DjangoFiles/manage.py check`

Expected : `System check identified no issues (0 silenced).`

- [ ] **Step 5 : Checkpoint commit**

Commit suggéré : `feat(auth): add terminal_role field on TibilletUser`.

---

## Task 2 : Adapter `TermUser.save()` pour auto-remplir `client_source`

**Files:**
- Modify: `AuthBillet/models.py:351-365` (classe TermUser)

- [ ] **Step 1 : Écrire le test qui doit échouer**

Créer un test rapide dans un fichier temporaire ou dans le shell Django pour vérifier le comportement actuel :

Run :
```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from django_tenants.utils import schema_context
from AuthBillet.models import TermUser
with schema_context('lespass'):
    u = TermUser.objects.create(email='test-task2@terminals.local')
    print('client_source:', u.client_source)
    print('espece:', u.espece)
    u.delete()
"
```

Expected AVANT modif : `client_source: None` (c'est le bug qu'on corrige).

- [ ] **Step 2 : Modifier `TermUser.save()`**

Éditer `AuthBillet/models.py` ligne 359-365, remplacer la méthode `save()` par :

```python
class TermUser(TibilletUser):
    class Meta:
        proxy = True
        verbose_name = _("Terminal")
        verbose_name_plural = _("Terminals")

    objects = TermUserManager()

    def save(self, *args, **kwargs):
        # À la création : remplit client_source avec le tenant courant
        # / On creation: fills client_source with current tenant
        if not self.pk:
            self.client_source = connection.tenant

        # Force espece=TE systématiquement pour les TermUser
        # / Always force espece=TE for TermUsers
        self.espece = TibilletUser.TYPE_TERM
        self.email = self.email.lower()

        super().save(*args, **kwargs)
```

- [ ] **Step 3 : Re-lancer le test**

Run la même commande qu'au step 1.

Expected APRÈS modif : `client_source: <Client: lespass>` (objet Client, pas None).

- [ ] **Step 4 : Checkpoint commit**

Commit suggéré : `feat(auth): auto-fill client_source in TermUser.save()`.

---

## Task 3 : Ajouter `terminal_role` sur `PairingDevice`

**Files:**
- Modify: `discovery/models.py:9-92`
- Create: `discovery/migrations/00XX_terminal_role.py`

- [ ] **Step 1 : Ajouter le champ**

Éditer `discovery/models.py`, ajouter après le champ `pin_code` (ligne 45) :

```python
    # Rôle du terminal à appairer (détermine le type de TermUser + clé créés)
    # / Terminal role to pair (determines the TermUser type + key created)
    terminal_role = models.CharField(
        max_length=2,
        choices=[
            ('LB', _('LaBoutik POS')),
            ('TI', _('Connected tap')),
            ('KI', _('Kiosk / self-service')),
        ],
        default='LB',
        verbose_name=_("Terminal role"),
        help_text=_("Type of hardware role being paired"),
    )
```

**Note importante :** on duplique les choices ici plutôt que d'importer `TibilletUser.TERMINAL_ROLE_CHOICES` pour éviter un import circulaire (`discovery` → `AuthBillet` → `Customers` → `discovery`). Les valeurs doivent rester synchronisées manuellement. Le test de Task 10 vérifiera cette cohérence.

- [ ] **Step 2 : Générer la migration**

Run : `docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations discovery`

Expected : fichier `discovery/migrations/00XX_pairingdevice_terminal_role.py` avec `AddField` et default 'LB'.

- [ ] **Step 3 : Appliquer**

Run : `docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing`

Expected : migration appliquée.

- [ ] **Step 4 : Vérifier**

Run : `docker exec lespass_django poetry run python /DjangoFiles/manage.py check`

Expected : `0 issues`.

- [ ] **Step 5 : Checkpoint commit**

Commit suggéré : `feat(discovery): add terminal_role on PairingDevice`.

---

## Task 4 : Ajouter `user` OneToOne nullable sur `LaBoutikAPIKey`

**Files:**
- Modify: `BaseBillet/models.py:3132-3136`
- Create: `BaseBillet/migrations/00XX_laboutikapikey_user.py`

- [ ] **Step 1 : Ajouter la FK**

Éditer `BaseBillet/models.py` ligne 3129-3137, remplacer la classe `LaBoutikAPIKey` :

```python
### Pour terminaux LaBoutik (appairage via Discovery PIN)


class LaBoutikAPIKey(AbstractAPIKey):
    """
    Clé API LaBoutik liée à un TermUser (V2 flow bridge).
    / LaBoutik API key linked to a TermUser (V2 bridge flow).

    Le champ `user` est nullable pour compat V1 (clés créées avant le bridge).
    / The `user` field is nullable for V1 compat (keys created before bridge).
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='laboutik_api_key',
        null=True, blank=True,
        verbose_name=_("Terminal user"),
        help_text=_("TermUser linked (V2 bridge flow). Null for legacy V1 keys."),
    )

    class Meta:
        ordering = ("-created",)
        verbose_name = "LaBoutik API Key"
        verbose_name_plural = "LaBoutik API Keys"
```

- [ ] **Step 2 : Vérifier les imports nécessaires**

En haut de `BaseBillet/models.py`, s'assurer que :
- `from django.conf import settings` est présent
- `from django.utils.translation import gettext_lazy as _` est présent

Si absents, les ajouter. Sinon passer.

- [ ] **Step 3 : Générer la migration**

Run : `docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations BaseBillet`

Expected : fichier `BaseBillet/migrations/00XX_laboutikapikey_user.py` avec `AddField user (OneToOneField, null=True)`.

- [ ] **Step 4 : Appliquer**

Run : `docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing`

Expected : migration appliquée sur tous les tenants.

- [ ] **Step 5 : Vérifier**

Run : `docker exec lespass_django poetry run python /DjangoFiles/manage.py check`

Expected : `0 issues`.

- [ ] **Step 6 : Checkpoint commit**

Commit suggéré : `feat(laboutik): link LaBoutikAPIKey to TermUser via OneToOneField`.

---

## Task 5 : Helper `_create_laboutik_terminal` + test

**Files:**
- Modify: `discovery/views.py` (fin du fichier)
- Create: `tests/pytest/test_discovery_claim_creates_termuser.py`

- [ ] **Step 1 : Créer le fichier de test**

Créer `tests/pytest/test_discovery_claim_creates_termuser.py` :

```python
"""
Tests du flow discovery claim qui crée désormais un TermUser + LaBoutikAPIKey liée.
/ Tests of the discovery claim flow which now creates a TermUser + linked LaBoutikAPIKey.
"""
import uuid

import pytest
from django.test import Client
from django_tenants.utils import schema_context, tenant_context
from rest_framework import status

from AuthBillet.models import TermUser, TibilletUser
from BaseBillet.models import LaBoutikAPIKey
from Customers.models import Client as TenantClient
from discovery.models import PairingDevice


@pytest.fixture
def tenant():
    """Récupère le tenant lespass pour les tests / Gets the lespass tenant."""
    return TenantClient.objects.get(schema_name='lespass')


@pytest.fixture
def pairing_device_laboutik(tenant):
    """Crée un PairingDevice role LB (Laboutik POS) / Creates a LB-role PairingDevice."""
    device = PairingDevice.objects.create(
        name=f'Test POS {uuid.uuid4().hex[:6]}',
        tenant=tenant,
        pin_code=PairingDevice.generate_unique_pin(),
        terminal_role='LB',
    )
    yield device
    # Cleanup : supprimer le TermUser créé s'il existe
    # / Cleanup: delete the created TermUser if any
    with tenant_context(tenant):
        TermUser.objects.filter(email__contains=str(device.uuid)).delete()
    device.delete()


@pytest.fixture
def pairing_device_kiosque(tenant):
    """Crée un PairingDevice role KI (Kiosque) / Creates a KI-role PairingDevice."""
    device = PairingDevice.objects.create(
        name=f'Test Kiosque {uuid.uuid4().hex[:6]}',
        tenant=tenant,
        pin_code=PairingDevice.generate_unique_pin(),
        terminal_role='KI',
    )
    yield device
    with tenant_context(tenant):
        TermUser.objects.filter(email__contains=str(device.uuid)).delete()
    device.delete()


def _call_claim(pin):
    """Appelle POST /api/discovery/claim/ avec un PIN.
    / Calls POST /api/discovery/claim/ with a PIN."""
    client = Client(HTTP_HOST='tibillet.localhost')
    return client.post(
        '/api/discovery/claim/',
        data={'pin_code': pin},
        content_type='application/json',
    )


@pytest.mark.django_db(transaction=True)
class TestClaimCreatesTermUserLaboutik:
    def test_claim_role_LB_cree_termuser_espece_TE(self, pairing_device_laboutik, tenant):
        """PairingDevice(role=LB) → TermUser(espece=TE)."""
        response = _call_claim(pairing_device_laboutik.pin_code)
        assert response.status_code == status.HTTP_200_OK

        with tenant_context(tenant):
            term_user = TermUser.objects.get(email=f'{pairing_device_laboutik.uuid}@terminals.local')
            assert term_user.espece == TibilletUser.TYPE_TERM

    def test_claim_role_LB_cree_termuser_role_LB(self, pairing_device_laboutik, tenant):
        """PairingDevice(role=LB) → TermUser(terminal_role=LB)."""
        response = _call_claim(pairing_device_laboutik.pin_code)
        assert response.status_code == status.HTTP_200_OK

        with tenant_context(tenant):
            term_user = TermUser.objects.get(email=f'{pairing_device_laboutik.uuid}@terminals.local')
            assert term_user.terminal_role == 'LB'

    def test_claim_cle_api_liee_au_termuser(self, pairing_device_laboutik, tenant):
        """LaBoutikAPIKey.user == TermUser créé."""
        response = _call_claim(pairing_device_laboutik.pin_code)
        assert response.status_code == status.HTTP_200_OK

        with tenant_context(tenant):
            term_user = TermUser.objects.get(email=f'{pairing_device_laboutik.uuid}@terminals.local')
            assert hasattr(term_user, 'laboutik_api_key')
            assert term_user.laboutik_api_key is not None

    def test_claim_termuser_client_source_est_le_tenant(self, pairing_device_laboutik, tenant):
        """TermUser.client_source == tenant courant."""
        response = _call_claim(pairing_device_laboutik.pin_code)
        assert response.status_code == status.HTTP_200_OK

        with tenant_context(tenant):
            term_user = TermUser.objects.get(email=f'{pairing_device_laboutik.uuid}@terminals.local')
            assert term_user.client_source_id == tenant.pk

    def test_claim_termuser_email_synthetique(self, pairing_device_laboutik, tenant):
        """Email = '<pairing_uuid>@terminals.local'."""
        response = _call_claim(pairing_device_laboutik.pin_code)
        assert response.status_code == status.HTTP_200_OK

        expected_email = f'{pairing_device_laboutik.uuid}@terminals.local'
        with tenant_context(tenant):
            assert TermUser.objects.filter(email=expected_email).exists()

    def test_claim_role_KI_cree_termuser_role_KI(self, pairing_device_kiosque, tenant):
        """PairingDevice(role=KI) → TermUser(terminal_role=KI)."""
        response = _call_claim(pairing_device_kiosque.pin_code)
        assert response.status_code == status.HTTP_200_OK

        with tenant_context(tenant):
            term_user = TermUser.objects.get(email=f'{pairing_device_kiosque.uuid}@terminals.local')
            assert term_user.terminal_role == 'KI'
```

**Note sur les fixtures :** Le conftest existant fournit peut-être déjà un fixture `tenant`. Si un conflit survient au Step 3, renommer en `tenant_lespass` dans ce fichier.

- [ ] **Step 2 : Lancer les tests — ils doivent TOUS échouer**

Run : `docker exec lespass_django poetry run pytest tests/pytest/test_discovery_claim_creates_termuser.py -v`

Expected : FAIL (la vue n'a pas encore été modifiée, les TermUser ne sont pas créés).

- [ ] **Step 3 : Ajouter le helper `_create_laboutik_terminal` dans `discovery/views.py`**

Éditer `discovery/views.py`, ajouter à la fin du fichier :

```python
def _create_laboutik_terminal(pairing_device):
    """
    Crée un TermUser (rôle LaBoutik ou Kiosque) et sa clé API liée.
    / Creates a TermUser (LaBoutik or Kiosk role) and its linked API key.

    LOCALISATION : discovery/views.py

    Appelée dans tenant_context() par ClaimPinView.
    / Called inside tenant_context() by ClaimPinView.

    :param pairing_device: L'objet PairingDevice en cours de claim
    :return: La clé API string (à retourner au client)
    """
    from AuthBillet.models import TermUser
    from BaseBillet.models import LaBoutikAPIKey

    # Email synthétique : <pairing_uuid>@terminals.local
    # Format filtrable, jamais confondu avec un vrai email humain
    # / Synthetic email: <pairing_uuid>@terminals.local
    # Filterable format, never confused with a real human email
    email_synthetique = f"{pairing_device.uuid}@terminals.local"

    term_user = TermUser.objects.create(
        email=email_synthetique,
        terminal_role=pairing_device.terminal_role,
        accept_newsletter=False,
    )
    # espece=TE et client_source=tenant auto-posés par TermUser.save()
    # / espece=TE and client_source=tenant auto-set by TermUser.save()

    _key_obj, api_key_string = LaBoutikAPIKey.objects.create_key(
        name=f"discovery-{pairing_device.uuid}",
        user=term_user,
    )
    return api_key_string
```

- [ ] **Step 4 : Modifier `ClaimPinView.post()` pour router selon `terminal_role`**

Éditer `discovery/views.py`, remplacer le bloc try/except principal (lignes 62-88) par :

```python
        tireuse_uuid = None
        try:
            with tenant_context(tenant_for_this_device):
                # Routage selon terminal_role du PairingDevice
                # / Routing based on PairingDevice.terminal_role
                from AuthBillet.models import TibilletUser

                if pairing_device.terminal_role == TibilletUser.ROLE_LABOUTIK:
                    # Flow Laboutik V2 : TermUser + clé liée
                    # / Laboutik V2 flow: TermUser + linked key
                    api_key_string = _create_laboutik_terminal(pairing_device)

                elif pairing_device.terminal_role == TibilletUser.ROLE_TIREUSE:
                    # Flow Tireuse INCHANGÉ pour cette phase
                    # / Tireuse flow UNCHANGED for this phase
                    from controlvanne.models import TireuseBec, TireuseAPIKey
                    tireuse = TireuseBec.objects.filter(
                        pairing_device=pairing_device
                    ).first()
                    if not tireuse:
                        raise ValueError(
                            "Pairing role TIREUSE but no TireuseBec linked"
                        )
                    _key_obj, api_key_string = TireuseAPIKey.objects.create_key(
                        name=f"discovery-{pairing_device.uuid}"
                    )
                    tireuse_uuid = str(tireuse.uuid)

                else:
                    # Rôle non implémenté (ex: Kiosque en attente)
                    # / Role not yet implemented (e.g. Kiosk)
                    # Pour Kiosque, on crée quand même un TermUser (rôle KI)
                    # / For Kiosk, we still create a TermUser (role KI)
                    api_key_string = _create_laboutik_terminal(pairing_device)
        except Exception as error:
            logger.error(
                f"Discovery claim: failed to create credentials "
                f"for tenant {tenant_for_this_device.name}: {error}"
            )
            return Response(
                {"error": "Failed to create device credentials."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
```

**Note importante :** pour l'instant, `ROLE_KIOSQUE` utilise le même helper que `ROLE_LABOUTIK` (crée un `TermUser` + `LaBoutikAPIKey`). Cela permet aux tests kiosque de passer. Une implémentation spécifique kiosque arrivera dans une phase ultérieure.

- [ ] **Step 5 : Re-lancer les tests**

Run : `docker exec lespass_django poetry run pytest tests/pytest/test_discovery_claim_creates_termuser.py -v`

Expected : tous PASS (6 tests).

- [ ] **Step 6 : Vérifier que les tests discovery existants passent toujours**

Run : `docker exec lespass_django poetry run pytest tests/pytest/test_discovery_pin_pairing.py -v`

Expected : tous PASS (pas de régression).

- [ ] **Step 7 : Checkpoint commit**

Commit suggéré : `feat(discovery): create TermUser in claim flow for Laboutik role`.

---

## Task 6 : Endpoint `/laboutik/auth/bridge/` + tests

**Files:**
- Create: `tests/pytest/test_hardware_auth_bridge.py`
- Modify: `laboutik/views.py` (fin du fichier)
- Modify: `laboutik/urls.py`

- [ ] **Step 1 : Vérifier l'import existant dans `laboutik/urls.py`**

Run : `docker exec lespass_django grep -n "from laboutik.views import" /DjangoFiles/laboutik/urls.py | head -5`

Noter l'imports actuel pour l'étendre proprement au Step 5.

- [ ] **Step 2 : Créer le fichier de test**

Créer `tests/pytest/test_hardware_auth_bridge.py` :

```python
"""
Tests du pont d'authentification hardware /laboutik/auth/bridge/.
/ Tests of the hardware auth bridge /laboutik/auth/bridge/.
"""
import uuid

import pytest
from django.test import Client
from django_tenants.utils import tenant_context

from AuthBillet.models import TermUser, TibilletUser
from BaseBillet.models import LaBoutikAPIKey
from Customers.models import Client as TenantClient


@pytest.fixture
def tenant():
    return TenantClient.objects.get(schema_name='lespass')


@pytest.fixture
def termuser_with_key(tenant):
    """Crée un TermUser Laboutik avec une clé API liée.
    / Creates a Laboutik TermUser with a linked API key."""
    with tenant_context(tenant):
        term_user = TermUser.objects.create(
            email=f'{uuid.uuid4()}@terminals.local',
            terminal_role='LB',
            accept_newsletter=False,
        )
        _key, api_key_string = LaBoutikAPIKey.objects.create_key(
            name='test-bridge',
            user=term_user,
        )
    yield term_user, api_key_string
    with tenant_context(tenant):
        term_user.delete()  # CASCADE supprime aussi la clé


@pytest.fixture
def orphan_api_key(tenant):
    """Crée une LaBoutikAPIKey sans user lié (V1 legacy).
    / Creates a LaBoutikAPIKey without linked user (V1 legacy)."""
    with tenant_context(tenant):
        _key, api_key_string = LaBoutikAPIKey.objects.create_key(
            name='test-v1-legacy',
            user=None,
        )
    yield api_key_string
    with tenant_context(tenant):
        LaBoutikAPIKey.objects.filter(name='test-v1-legacy').delete()


def _post_bridge(api_key_string=None):
    """POST /laboutik/auth/bridge/ avec optionnel header Api-Key.
    / POST /laboutik/auth/bridge/ with optional Api-Key header."""
    client = Client(HTTP_HOST='lespass.tibillet.localhost')
    headers = {}
    if api_key_string:
        headers['HTTP_AUTHORIZATION'] = f'Api-Key {api_key_string}'
    return client, client.post('/laboutik/auth/bridge/', **headers)


@pytest.mark.django_db(transaction=True)
class TestHardwareAuthBridge:
    def test_bridge_avec_cle_valide_retourne_204(self, termuser_with_key):
        """Une clé valide retourne 204 No Content."""
        _term_user, api_key = termuser_with_key
        _client, response = _post_bridge(api_key)
        assert response.status_code == 204

    def test_bridge_avec_cle_valide_pose_cookie_sessionid(self, termuser_with_key):
        """Le bridge pose un cookie sessionid sur la réponse."""
        _term_user, api_key = termuser_with_key
        _client, response = _post_bridge(api_key)
        assert 'sessionid' in response.cookies

    def test_bridge_sans_header_authorization_retourne_401(self):
        """Header absent → 401."""
        _client, response = _post_bridge(None)
        assert response.status_code == 401

    def test_bridge_avec_cle_invalide_retourne_401(self):
        """Clé inexistante → 401."""
        _client, response = _post_bridge('AAAAAA.BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB')
        assert response.status_code == 401

    def test_bridge_avec_cle_sans_user_retourne_400(self, orphan_api_key):
        """Clé V1 (user=None) → 400 avec message explicite."""
        _client, response = _post_bridge(orphan_api_key)
        assert response.status_code == 400
        assert b'Legacy' in response.content or b'legacy' in response.content

    def test_bridge_avec_user_revoque_retourne_401(self, termuser_with_key, tenant):
        """TermUser.is_active=False → 401."""
        term_user, api_key = termuser_with_key
        with tenant_context(tenant):
            term_user.is_active = False
            term_user.save()
        _client, response = _post_bridge(api_key)
        assert response.status_code == 401

    def test_bridge_avec_get_retourne_405(self, termuser_with_key):
        """GET sur l'endpoint → 405 Method Not Allowed."""
        _term_user, api_key = termuser_with_key
        client = Client(HTTP_HOST='lespass.tibillet.localhost')
        response = client.get(
            '/laboutik/auth/bridge/',
            HTTP_AUTHORIZATION=f'Api-Key {api_key}',
        )
        assert response.status_code == 405

    def test_apres_bridge_requete_metier_passe_avec_cookie(self, termuser_with_key):
        """Flow E2E : bridge → GET /laboutik/caisse/ → 200."""
        _term_user, api_key = termuser_with_key
        client, response_bridge = _post_bridge(api_key)
        assert response_bridge.status_code == 204

        # Le client a maintenant son cookie sessionid automatiquement
        # / The client now has its sessionid cookie automatically
        response_caisse = client.get('/laboutik/caisse/')
        # L'endpoint existe : 200 attendu. Si 302 redirect, c'est aussi OK
        # (signifie que l'auth a passé et on rebondit vers la sélection PV)
        # / Endpoint exists: 200 expected. If 302 redirect, also OK (auth passed)
        assert response_caisse.status_code in (200, 302)
```

- [ ] **Step 3 : Lancer les tests — ils doivent TOUS échouer (endpoint absent)**

Run : `docker exec lespass_django poetry run pytest tests/pytest/test_hardware_auth_bridge.py -v`

Expected : tous FAIL avec 404 (endpoint non défini).

- [ ] **Step 4 : Créer la vue `LaBoutikAuthBridgeView` dans `laboutik/views.py`**

Ajouter à la fin de `laboutik/views.py` :

```python
from django.contrib.auth import login
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework.permissions import AllowAny
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView


class BridgeThrottle(AnonRateThrottle):
    """
    Anti-brute-force sur le bridge : 10 requêtes/minute par IP.
    / Brute-force protection on bridge: 10 req/min per IP.
    """
    rate = '10/min'
    scope = 'laboutik_auth_bridge'


@method_decorator(csrf_exempt, name='dispatch')
class LaBoutikAuthBridgeView(APIView):
    """
    Pont d'authentification hardware : échange une clé API contre un cookie session.
    / Hardware auth bridge: trades an API key for a session cookie.

    LOCALISATION : laboutik/views.py

    Flux :
    1. Client POST avec header Authorization: Api-Key xxx
    2. Validation de la clé (401 si invalide)
    3. Si la clé n'a pas de user lié (legacy V1) : 400
    4. Si user.is_active=False (révoqué) : 401
    5. django.contrib.auth.login() pose le cookie sessionid
    6. set_expiry(12h) — session courte par hygiène

    CSRF exempt : légitime car
    - la clé API joue l'auth forte pour cette seule requête
    - le client Cordova/WebView n'a pas encore de cookie CSRF
    - les requêtes suivantes (avec cookie session) auront la protection CSRF normale

    COMMUNICATION :
    Reçoit : Header Authorization: Api-Key <key>
    Émet : 204 No Content + Set-Cookie: sessionid=<key>
    Erreurs : 401 si clé absente/invalide/révoquée, 400 si clé V1, 429 si throttle
    """
    permission_classes = [AllowAny]
    throttle_classes = [BridgeThrottle]

    def post(self, request):
        # Extraction de la clé depuis le header Authorization
        # / Extract key from Authorization header
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if not auth_header.startswith('Api-Key '):
            return HttpResponse(status=401)

        api_key_string = auth_header[len('Api-Key '):].strip()
        if not api_key_string:
            return HttpResponse(status=401)

        # Validation de la clé
        # / Key validation
        from BaseBillet.models import LaBoutikAPIKey
        try:
            api_key = LaBoutikAPIKey.objects.get_from_key(api_key_string)
        except LaBoutikAPIKey.DoesNotExist:
            return HttpResponse(status=401)

        # Clé V1 sans user lié : non bridgeable
        # / V1 key without linked user: cannot be bridged
        if api_key.user is None:
            return HttpResponse(
                "Legacy API key, bridge flow not available. Please re-pair the device.",
                status=400,
            )

        # User révoqué ?
        # / User revoked?
        term_user = api_key.user
        if not term_user.is_active:
            return HttpResponse(status=401)

        # Login Django natif : pose le cookie sessionid
        # / Native Django login: sets sessionid cookie
        login(request, term_user)

        # Session courte pour les terminaux (12h)
        # / Short session for terminals (12h)
        request.session.set_expiry(60 * 60 * 12)

        return HttpResponse(status=204)
```

- [ ] **Step 5 : Brancher l'URL dans `laboutik/urls.py`**

Éditer `laboutik/urls.py`. Ajouter `LaBoutikAuthBridgeView` à l'import depuis `laboutik.views` (étendre la liste d'imports existante), puis ajouter dans `urlpatterns` AVANT `+ router.urls` :

```python
path("auth/bridge/", LaBoutikAuthBridgeView.as_view(), name="laboutik-auth-bridge"),
```

Si `urlpatterns` est défini par concaténation `... + router.urls`, l'ajout se fait dans la liste `[]`.

- [ ] **Step 6 : Re-lancer les tests**

Run : `docker exec lespass_django poetry run pytest tests/pytest/test_hardware_auth_bridge.py -v`

Expected : tous les tests PASS (8 tests).

- [ ] **Step 7 : Checkpoint commit**

Commit suggéré : `feat(laboutik): add auth bridge endpoint for hardware terminals`.

---

## Task 7 : Permission `HasLaBoutikTerminalAccess`

**Files:**
- Modify: `BaseBillet/permissions.py` (ajout en fin de fichier, sans toucher `HasLaBoutikAccess`)

- [ ] **Step 1 : Ajouter les imports nécessaires**

En haut de `BaseBillet/permissions.py`, après les imports existants :

```python
from rest_framework import permissions
```

Vérifier qu'il n'est pas déjà importé sous un autre alias.

- [ ] **Step 2 : Ajouter la classe `HasLaBoutikTerminalAccess`**

À la fin de `BaseBillet/permissions.py` :

```python
class HasLaBoutikTerminalAccess(permissions.BasePermission):
    """
    Permission V2 : accepte les TermUser authentifiés via le bridge (session),
    avec fallback V1 sur HasLaBoutikAccess (admin session OU header Api-Key).
    / V2 permission: accepts bridge-authenticated TermUsers (session),
    with V1 fallback on HasLaBoutikAccess (admin session OR Api-Key header).

    LOCALISATION : BaseBillet/permissions.py

    Utilisée sur les routes Laboutik V2 qui adoptent le pattern bridge→session.
    Les routes V1 legacy continuent d'utiliser HasLaBoutikAccess directement.
    / Used on V2 Laboutik routes that adopt the bridge→session pattern.
    Legacy V1 routes keep using HasLaBoutikAccess directly.
    """

    def has_permission(self, request, view):
        from AuthBillet.models import TibilletUser

        user = request.user

        # Chemin V2 : TermUser avec rôle LaBoutik lié à ce tenant
        # / V2 path: TermUser with LaBoutik role linked to this tenant
        if user and user.is_authenticated:
            if user.espece == TibilletUser.TYPE_TERM:
                if user.terminal_role == TibilletUser.ROLE_LABOUTIK:
                    if user.client_source_id == connection.tenant.pk:
                        return True

        # Fallback V1 : délègue à HasLaBoutikAccess (admin session OU header Api-Key)
        # / V1 fallback: delegate to HasLaBoutikAccess
        return HasLaBoutikAccess().has_permission(request, view)
```

- [ ] **Step 3 : Vérifier que `HasLaBoutikAccess` n'a PAS été modifiée**

Run : `docker exec lespass_django poetry run python /DjangoFiles/manage.py diffsettings | head -1` (juste un check rapide).

Lecture manuelle : ouvrir `BaseBillet/permissions.py`, vérifier que la classe `HasLaBoutikAccess` (lignes 82-118 d'origine) est toujours identique.

- [ ] **Step 4 : Vérifier `manage.py check`**

Run : `docker exec lespass_django poetry run python /DjangoFiles/manage.py check`

Expected : `0 issues`.

- [ ] **Step 5 : Ajouter un test rapide de la permission**

Ajouter à la fin de `tests/pytest/test_hardware_auth_bridge.py` :

```python
@pytest.mark.django_db(transaction=True)
class TestHasLaBoutikTerminalAccess:
    """Tests directs de la permission (sans HTTP) / Direct permission tests."""

    def test_permission_accepte_termuser_role_LB_du_tenant(self, termuser_with_key, tenant):
        """TermUser LB du bon tenant → accès accordé."""
        from unittest.mock import Mock
        from BaseBillet.permissions import HasLaBoutikTerminalAccess
        from django.db import connection as db_connection

        term_user, _api_key = termuser_with_key
        with tenant_context(tenant):
            request = Mock()
            request.user = term_user
            # Le middleware tenant aurait posé connection.tenant=tenant
            # Ici tenant_context fait le boulot
            perm = HasLaBoutikTerminalAccess()
            assert perm.has_permission(request, None) is True

    def test_permission_refuse_termuser_role_TI(self, tenant):
        """TermUser rôle Tireuse → pas d'accès Laboutik (fallback V1 aussi refuse)."""
        from unittest.mock import Mock
        from BaseBillet.permissions import HasLaBoutikTerminalAccess

        with tenant_context(tenant):
            tireuse_user = TermUser.objects.create(
                email=f'{uuid.uuid4()}@terminals.local',
                terminal_role='TI',
            )
            request = Mock()
            request.user = tireuse_user
            perm = HasLaBoutikTerminalAccess()
            try:
                result = perm.has_permission(request, None)
                # Fallback V1 peut lever PermissionDenied ou retourner False
                assert result is False or result is None
            except Exception as e:
                # PermissionDenied acceptable (c'est le comportement V1)
                assert 'Missing' in str(e) or 'Invalid' in str(e) or 'permission' in str(e).lower()
            finally:
                tireuse_user.delete()
```

- [ ] **Step 6 : Lancer les tests**

Run : `docker exec lespass_django poetry run pytest tests/pytest/test_hardware_auth_bridge.py -v`

Expected : tous PASS (10 tests au total).

- [ ] **Step 7 : Checkpoint commit**

Commit suggéré : `feat(permissions): add HasLaBoutikTerminalAccess with V1 fallback`.

---

## Task 8 : Fixture `terminal_client` dans conftest

**Files:**
- Modify: `tests/pytest/conftest.py`

- [ ] **Step 1 : Repérer la section des fixtures d'auth dans conftest**

Run : `docker exec lespass_django grep -n "auth_headers\|def.*tenant\|fixture" /DjangoFiles/tests/pytest/conftest.py | head -30`

Noter où sont les fixtures existantes pour y insérer la nouvelle.

- [ ] **Step 2 : Ajouter la fixture `terminal_client`**

Dans `tests/pytest/conftest.py`, ajouter à un endroit approprié (section fixtures d'auth) :

```python
@pytest.fixture
def terminal_client(tenant):
    """
    Client Django authentifié comme TermUser Laboutik (session posée).
    / Django Client authenticated as a Laboutik TermUser (session set).

    Remplace auth_headers (header Api-Key) pour les tests V2.
    / Replaces auth_headers (Api-Key header) for V2 tests.

    Usage :
        def test_something(terminal_client):
            response = terminal_client.get('/laboutik/caisse/')
            assert response.status_code == 200
    """
    import uuid
    from django.test import Client
    from django_tenants.utils import tenant_context
    from AuthBillet.models import TermUser

    with tenant_context(tenant):
        term_user = TermUser.objects.create(
            email=f'test-{uuid.uuid4()}@terminals.local',
            terminal_role='LB',
            accept_newsletter=False,
        )

    client = Client(HTTP_HOST=f'{tenant.schema_name}.tibillet.localhost')
    client.force_login(term_user)

    yield client

    # Cleanup
    with tenant_context(tenant):
        term_user.delete()
```

**Note :** si la fixture `tenant` n'existe pas dans le conftest existant, vérifier le nom exact utilisé pour récupérer le tenant de test (grep sur `schema_name='lespass'` dans `conftest.py`).

- [ ] **Step 3 : Vérifier que la fixture est découverte**

Run : `docker exec lespass_django poetry run pytest --fixtures tests/pytest/ 2>&1 | grep terminal_client`

Expected : ligne montrant `terminal_client` avec son docstring.

- [ ] **Step 4 : Tester la fixture avec un test minimal**

Ajouter en début de `tests/pytest/test_hardware_auth_bridge.py` :

```python
@pytest.mark.django_db(transaction=True)
def test_fixture_terminal_client_fonctionne(terminal_client):
    """Smoke test de la fixture / Smoke test of the fixture."""
    # Le client est authentifié, on peut faire une requête
    # / Client is authenticated, we can make a request
    response = terminal_client.get('/laboutik/caisse/')
    # On accepte 200 ou 302 (redirect vers sélection PV selon l'état)
    assert response.status_code in (200, 302)
```

Run : `docker exec lespass_django poetry run pytest tests/pytest/test_hardware_auth_bridge.py::test_fixture_terminal_client_fonctionne -v`

Expected : PASS.

- [ ] **Step 5 : Checkpoint commit**

Commit suggéré : `test(laboutik): add terminal_client fixture for V2 auth tests`.

---

## Task 9 : Admin Unfold — `TermUserAdmin`

**Files:**
- Modify: `Administration/admin_tenant.py`
- Create: `Administration/templates/admin/termuser/change_form_before.html`

- [ ] **Step 1 : Lire le fichier admin pour comprendre le pattern Unfold existant**

Run : `docker exec lespass_django grep -n "@admin.register\|class.*Admin.*ModelAdmin\|TenantAdminPermissionWithRequest" /DjangoFiles/Administration/admin_tenant.py | head -20`

Noter le pattern exact d'enregistrement utilisé dans le projet.

- [ ] **Step 2 : Créer le template du bouton de révocation**

Créer `Administration/templates/admin/termuser/change_form_before.html` :

```html
{% load i18n %}
{% if original and original.is_active %}
<div style="padding: 16px; background-color: #fef2f2; border: 1px solid #fca5a5; border-radius: 6px; margin-bottom: 24px;">
  <p style="margin: 0 0 12px 0; color: #7f1d1d; font-weight: 500;">
    {% translate "Revoking this terminal will log it out from all active sessions immediately. The device will need to be re-paired to regain access." %}
  </p>
  <form method="POST" action="{% url 'admin:AuthBillet_termuser_changelist' %}?revoke={{ original.pk }}">
    {% csrf_token %}
    <button type="submit" name="_revoke_single" value="{{ original.pk }}" style="background-color: #dc2626; color: white; padding: 8px 16px; border-radius: 6px; border: none; cursor: pointer; font-weight: 500;">
      {% translate "Revoke this terminal" %}
    </button>
  </form>
</div>
{% elif original and not original.is_active %}
<div style="padding: 16px; background-color: #fef3c7; border: 1px solid #fcd34d; border-radius: 6px; margin-bottom: 24px;">
  <p style="margin: 0; color: #78350f;">
    {% translate "This terminal is revoked (is_active=False). It can no longer authenticate." %}
  </p>
</div>
{% endif %}
```

- [ ] **Step 3 : Ajouter `TermUserAdmin` dans `admin_tenant.py`**

Ajouter à un endroit approprié (section admin users) :

```python
from AuthBillet.models import TermUser


@admin.register(TermUser, site=staff_admin_site)
class TermUserAdmin(ModelAdmin):
    """
    Admin Unfold pour les terminaux hardware (TermUser).
    / Unfold admin for hardware terminals (TermUser).

    LOCALISATION : Administration/admin_tenant.py

    - Lecture seule sur la plupart des champs (créés via /api/discovery/claim/)
    - Seul is_active est éditable (pour révoquer un terminal)
    - Action bulk et bouton individuel pour révocation
    """
    list_display = (
        'display_email_short',
        'terminal_role',
        'display_is_active',
        'last_see',
        'date_joined',
    )
    list_filter = ('terminal_role', 'is_active')
    search_fields = ('email',)

    readonly_fields = (
        'email', 'terminal_role', 'espece',
        'client_source', 'date_joined', 'last_see',
    )

    fieldsets = (
        (None, {
            'fields': ('email', 'terminal_role', 'espece', 'is_active'),
        }),
        (_('Tracking'), {
            'fields': ('client_source', 'date_joined', 'last_see'),
        }),
    )

    actions = ['revoke_terminals']

    change_form_before_template = 'admin/termuser/change_form_before.html'

    def has_add_permission(self, request):
        # Terminaux créés uniquement via le flow /api/discovery/claim/
        # / Terminals are only created via the /api/discovery/claim/ flow
        return False

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    @admin.display(description=_('Email'))
    def display_email_short(self, obj):
        """Tronque l'email UUID pour l'affichage / Truncates UUID email for display."""
        email_local_part = obj.email.split('@')[0]
        return email_local_part[:12] + '…' if len(email_local_part) > 12 else email_local_part

    @admin.display(description=_('Active'), boolean=True)
    def display_is_active(self, obj):
        return obj.is_active

    @admin.action(description=_('Revoke selected terminals (is_active=False)'))
    def revoke_terminals(self, request, queryset):
        """Action bulk : révoque les terminaux sélectionnés.
        / Bulk action: revokes selected terminals."""
        from django.contrib import messages
        count = queryset.update(is_active=False)
        self.message_user(
            request,
            _('%(count)d terminal(s) revoked. Their sessions are now anonymous.') % {'count': count},
            messages.SUCCESS,
        )
```

**Notes importantes :**
- `staff_admin_site` est le site admin utilisé dans le projet — vérifier le nom exact dans `admin_tenant.py`
- `TenantAdminPermissionWithRequest` est la fonction de permission standard du projet — importer si besoin
- Les helpers `display_email_short` et `display_is_active` sont des **méthodes** du ModelAdmin : conformément au piège documenté dans PIEGES.md ("Ne JAMAIS définir de helpers au niveau module sauf si nécessaire"), ici elles font référence à `obj`, donc méthodes OK.

- [ ] **Step 4 : Ajouter l'entrée sidebar Unfold**

Dans `TiBillet/settings.py` (ou l'endroit où `get_sidebar_navigation()` est défini — voir MEMORY.md : "sidebar conditionnelle `get_sidebar_navigation(request)` callable string dans settings.py") :

Trouver la section conditionnelle liée à `module_caisse` (ou une section générale "Informations générales") et ajouter :

```python
{
    "title": _("Terminals"),
    "link": reverse_lazy("admin:AuthBillet_termuser_changelist"),
    "icon": "tablet",  # Icône Unfold/Material, adapter si besoin
},
```

**Note :** l'emplacement exact dans la sidebar dépend de l'implémentation actuelle. Placer de préférence dans la section "Informations générales" ou sous "Caisse" si `module_caisse` actif. Si la logique de sidebar est dans `Administration/admin_tenant.py`, y aller.

- [ ] **Step 5 : Vérifier `manage.py check`**

Run : `docker exec lespass_django poetry run python /DjangoFiles/manage.py check`

Expected : `0 issues`.

- [ ] **Step 6 : Test manuel visuel**

Lancer le serveur et aller sur `/admin/` :

Run (en background) : `docker exec lespass_django poetry run python /DjangoFiles/manage.py runserver_plus 0.0.0.0:8002`

Dans le navigateur : se connecter à l'admin, vérifier que :
- L'entrée "Terminals" apparaît dans la sidebar
- La liste affiche les TermUsers existants (créés par les tests précédents — ou vide)
- Le filtre `terminal_role` fonctionne
- La page détail d'un TermUser affiche le bouton rouge "Revoke this terminal" (si `is_active=True`)

Si aucun TermUser existe : créer via shell :
```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from django_tenants.utils import schema_context
from AuthBillet.models import TermUser
with schema_context('lespass'):
    TermUser.objects.create(email='demo@terminals.local', terminal_role='LB')
"
```

- [ ] **Step 7 : Checkpoint commit**

Commit suggéré : `feat(admin): add TermUserAdmin with revocation button`.

---

## Task 10 : Test de cohérence choices `terminal_role`

**Files:**
- Create: `tests/pytest/test_terminal_role_choices_sync.py`

Ce test garantit que les choices de `PairingDevice.terminal_role` (dupliqués pour éviter l'import circulaire) restent synchronisés avec `TibilletUser.TERMINAL_ROLE_CHOICES`.

- [ ] **Step 1 : Créer le fichier**

Créer `tests/pytest/test_terminal_role_choices_sync.py` :

```python
"""
Garantit que les choices de terminal_role restent synchronisés entre
TibilletUser (source de vérité) et PairingDevice (duplication pour
éviter l'import circulaire discovery → AuthBillet).

/ Ensures that terminal_role choices stay in sync between TibilletUser
(source of truth) and PairingDevice (duplicated to avoid circular import).
"""
import pytest

from AuthBillet.models import TibilletUser
from discovery.models import PairingDevice


def test_pairingdevice_terminal_role_choices_match_tibilletuser():
    """
    Les valeurs (clés) des choices doivent être identiques des deux côtés.
    / Choice values (keys) must be identical on both sides.
    """
    tibilletuser_values = {value for value, _label in TibilletUser.TERMINAL_ROLE_CHOICES}
    pairingdevice_field = PairingDevice._meta.get_field('terminal_role')
    pairingdevice_values = {value for value, _label in pairingdevice_field.choices}

    assert tibilletuser_values == pairingdevice_values, (
        f"TERMINAL_ROLE_CHOICES desync: "
        f"TibilletUser={tibilletuser_values} vs "
        f"PairingDevice={pairingdevice_values}. "
        f"Keep both lists in sync."
    )


def test_laboutik_role_constant_exists():
    """ROLE_LABOUTIK doit exister comme constante / ROLE_LABOUTIK must be a constant."""
    assert hasattr(TibilletUser, 'ROLE_LABOUTIK')
    assert TibilletUser.ROLE_LABOUTIK == 'LB'


def test_tireuse_role_constant_exists():
    assert hasattr(TibilletUser, 'ROLE_TIREUSE')
    assert TibilletUser.ROLE_TIREUSE == 'TI'


def test_kiosque_role_constant_exists():
    assert hasattr(TibilletUser, 'ROLE_KIOSQUE')
    assert TibilletUser.ROLE_KIOSQUE == 'KI'
```

- [ ] **Step 2 : Lancer les tests**

Run : `docker exec lespass_django poetry run pytest tests/pytest/test_terminal_role_choices_sync.py -v`

Expected : tous PASS (4 tests).

- [ ] **Step 3 : Checkpoint commit**

Commit suggéré : `test: add sync check for terminal_role choices`.

---

## Task 11 : Migrer les tests Laboutik existants vers `terminal_client`

**Files:**
- Modify: tous les fichiers `tests/pytest/test_pos_*.py`, `test_caisse_*.py`, `test_paiement_*.py`, `test_laboutik_*.py` qui utilisent `auth_headers`

- [ ] **Step 1 : Inventorier les tests concernés**

Run : `docker exec lespass_django grep -rln "auth_headers\|Api-Key" /DjangoFiles/tests/pytest/test_*.py | grep -iE "pos|caisse|paiement|laboutik|cloture|retour_carte" | head -30`

Noter la liste des fichiers à traiter.

- [ ] **Step 2 : Pour CHAQUE fichier, appliquer la migration mécanique**

Pour chaque test dans la liste :

```python
# AVANT
def test_something(client, auth_headers):
    response = client.post('/laboutik/xxx/', data=..., **auth_headers)
    assert response.status_code == 200

# APRÈS
def test_something(terminal_client):
    response = terminal_client.post('/laboutik/xxx/', data=...)
    assert response.status_code == 200
```

**Patterns à chercher :**
- `def test_XXX(client, auth_headers)` → `def test_XXX(terminal_client)`
- `def test_XXX(api_client, auth_headers)` → `def test_XXX(terminal_client)`
- `client.get(url, **auth_headers)` → `terminal_client.get(url)`
- `client.post(url, data, **auth_headers)` → `terminal_client.post(url, data)`

**Attention :** certains tests utilisent `auth_headers` pour un cas V1 (clé API pure). Ces tests doivent **garder** `auth_headers`, ne pas les migrer. Si le test vérifie explicitement le header `Api-Key` (legacy V1), il reste inchangé.

Règle de décision : si le test teste une route V1 existante sans vérifier le header, migrer. Si le test teste explicitement le flow V1 (ex: `test_api_key_v1_still_works`), garder.

- [ ] **Step 3 : Lancer TOUS les tests pytest du domaine LaBoutik**

Run :
```bash
docker exec lespass_django poetry run pytest \
  tests/pytest/test_pos_*.py \
  tests/pytest/test_caisse_*.py \
  tests/pytest/test_paiement_*.py \
  tests/pytest/test_cloture_*.py \
  tests/pytest/test_retour_carte_*.py \
  tests/pytest/test_laboutik_*.py \
  -v --tb=short
```

Expected : tous PASS. Si certains échouent :
- Rollback le fichier concerné et migrer plus finement
- Vérifier le host HTTP (fixture `terminal_client` utilise `{schema_name}.tibillet.localhost`)
- Vérifier que `terminal_client` est bien utilisé (pas mélange avec `client`)

- [ ] **Step 4 : Lancer la suite pytest complète pour détecter les régressions**

Run : `docker exec lespass_django poetry run pytest tests/pytest/ -q --tb=short`

Expected : pas plus d'échecs qu'avant (note le nombre exact avant le refactor pour comparer).

- [ ] **Step 5 : Checkpoint commit**

Commit suggéré : `test: migrate laboutik tests to terminal_client fixture`.

---

## Task 12 : Test E2E Playwright

**Files:**
- Create: `tests/e2e/test_laboutik_auth_bridge.py`

- [ ] **Step 1 : Regarder le pattern Playwright existant**

Run : `docker exec lespass_django ls /DjangoFiles/tests/e2e/ | head -20`

Run : `docker exec lespass_django head -80 /DjangoFiles/tests/e2e/test_pos_articles.py` (ou n'importe quel test e2e existant, pour le pattern).

- [ ] **Step 2 : Créer le test**

Créer `tests/e2e/test_laboutik_auth_bridge.py` :

```python
"""
Test E2E Playwright du flow hardware bridge.
/ Playwright E2E test of the hardware bridge flow.

Simule le comportement du client Nicolas (Cordova/Android) :
1. POST /laboutik/auth/bridge/ avec header Api-Key
2. Vérifie que le cookie sessionid est posé
3. Navigue vers /laboutik/caisse/
4. Vérifie que la page s'affiche sans 401
"""
import uuid

import pytest
from django_tenants.utils import tenant_context


@pytest.mark.e2e
def test_flow_bridge_puis_caisse(page, tenant_lespass, ensure_pos_data):
    """
    Simule le flow complet : bridge → navigation → caisse accessible.
    / Full flow simulation: bridge → navigation → caisse accessible.
    """
    from AuthBillet.models import TermUser
    from BaseBillet.models import LaBoutikAPIKey

    # Setup : créer un TermUser + clé API
    # / Setup: create a TermUser + API key
    with tenant_context(tenant_lespass):
        term_user = TermUser.objects.create(
            email=f'e2e-bridge-{uuid.uuid4()}@terminals.local',
            terminal_role='LB',
            accept_newsletter=False,
        )
        _key_obj, api_key_string = LaBoutikAPIKey.objects.create_key(
            name='e2e-bridge-test',
            user=term_user,
        )

    try:
        # Step 1 : POST bridge via requête fetch dans le navigateur
        # / Step 1: POST bridge via browser fetch
        bridge_url = 'https://lespass.tibillet.localhost/laboutik/auth/bridge/'
        page.goto('https://lespass.tibillet.localhost/')

        result = page.evaluate("""async (args) => {
            const response = await fetch(args.url, {
                method: 'POST',
                headers: { 'Authorization': `Api-Key ${args.key}` },
                credentials: 'include',
            });
            return { status: response.status };
        }""", {"url": bridge_url, "key": api_key_string})

        assert result['status'] == 204, f"Bridge expected 204, got {result['status']}"

        # Step 2 : naviguer vers /laboutik/caisse/ avec le cookie déjà posé
        # / Step 2: navigate to /laboutik/caisse/ with cookie already set
        page.goto('https://lespass.tibillet.localhost/laboutik/caisse/')

        # Step 3 : vérifier que la page est accessible (pas de 401)
        # / Step 3: check that the page is accessible (no 401)
        # Le titre exact dépend de l'état de la caisse, on vérifie juste
        # qu'on n'est pas redirigé vers une page d'erreur d'auth
        # / Exact title depends on caisse state, we just check we're not
        # redirected to an auth error page
        content = page.content()
        assert '401' not in content
        assert 'Unauthorized' not in content
        assert 'Not Found' not in content
    finally:
        # Cleanup
        with tenant_context(tenant_lespass):
            term_user.delete()
```

- [ ] **Step 3 : Lancer le test E2E**

Prérequis : le serveur Django doit tourner via Traefik (voir `tests/TESTS_README.md`).

Run : `docker exec lespass_django poetry run pytest tests/e2e/test_laboutik_auth_bridge.py -v -s`

Expected : PASS.

Si échec :
- Vérifier que Playwright est installé : `docker exec lespass_django poetry run playwright install chromium`
- Vérifier que le serveur est bien démarré (fixture conftest E2E)
- Les noms des fixtures (`tenant_lespass`, `ensure_pos_data`) varient selon le conftest — adapter si besoin

- [ ] **Step 4 : Checkpoint commit**

Commit suggéré : `test(e2e): add Playwright test for hardware auth bridge`.

---

## Task 13 : Documentation utilisateur

**Files:**
- Create: `A TESTER et DOCUMENTER/hardware-auth-bridge.md`
- Modify: `CHANGELOG.md`
- Modify: `tests/PIEGES.md`

- [ ] **Step 1 : Créer le fichier A TESTER**

Créer `A TESTER et DOCUMENTER/hardware-auth-bridge.md` :

```markdown
# Authentification hardware via TermUser

## Ce qui a été fait

Refactor de l'auth des terminaux LaBoutik (POS + Android) via un pont
`/laboutik/auth/bridge/` qui échange une clé API contre un cookie de session
Django. Création automatique d'un TermUser à l'appairage.

### Modifications

| Fichier | Changement |
|---|---|
| `AuthBillet/models.py` | +terminal_role sur TibilletUser, TermUser.save() auto client_source |
| `discovery/models.py` | +terminal_role sur PairingDevice |
| `discovery/views.py` | ClaimPinView crée un TermUser pour les rôles LB et KI |
| `BaseBillet/models.py` | LaBoutikAPIKey.user OneToOneField nullable |
| `BaseBillet/permissions.py` | +HasLaBoutikTerminalAccess (HasLaBoutikAccess inchangée) |
| `laboutik/views.py` | +LaBoutikAuthBridgeView |
| `laboutik/urls.py` | +path auth/bridge/ |
| `Administration/admin_tenant.py` | +TermUserAdmin |

## Tests à réaliser

### Test 1 : Appairage LaBoutik complet

1. Se connecter à `/admin/` comme admin tenant
2. Aller dans "Discovery > Pairing devices"
3. Créer un nouveau PairingDevice avec :
   - `name`: "Test POS 1"
   - `terminal_role`: "LaBoutik POS"
4. Noter le PIN affiché
5. Dans un terminal, exécuter :
   ```bash
   curl -X POST https://lespass.tibillet.localhost/api/discovery/claim/ \
        -H "Content-Type: application/json" \
        -d '{"pin_code": PIN_ICI}'
   ```
6. Noter `api_key` dans la réponse
7. Dans l'admin, aller dans "Terminals" (nouvelle entrée)
8. Vérifier qu'un TermUser existe avec :
   - email : `<uuid>@terminals.local`
   - terminal_role : "LaBoutik POS"
   - is_active : True

### Test 2 : Bridge + accès caisse

1. Avec la clé obtenue au Test 1, faire :
   ```bash
   curl -X POST -c cookies.txt https://lespass.tibillet.localhost/laboutik/auth/bridge/ \
        -H "Authorization: Api-Key API_KEY_ICI"
   ```
2. Vérifier : status 204, fichier `cookies.txt` contient `sessionid=...`
3. Puis :
   ```bash
   curl -b cookies.txt https://lespass.tibillet.localhost/laboutik/caisse/
   ```
4. Vérifier : status 200 (HTML de la caisse)

### Test 3 : Révocation

1. Admin > Terminals > cliquer sur le TermUser du Test 1
2. Cliquer sur le bouton rouge "Revoke this terminal"
3. Re-tenter `curl -b cookies.txt .../laboutik/caisse/`
4. Vérifier : redirection ou 401 (session devenue anonyme)

### Test 4 : Rôle Kiosque (futur)

1. Créer un PairingDevice role "Kiosk / self-service"
2. Claim le PIN
3. Vérifier qu'un TermUser role KI est créé (même flow que LB pour l'instant)

### Test 5 : Clé V1 orpheline (compat)

1. Créer manuellement une LaBoutikAPIKey sans user (via shell Django)
2. Utiliser cette clé dans le header sur une route V1 (ex: `/laboutik/paiement/`)
3. Vérifier : accès accordé (fallback V1 via HasLaBoutikAccess)
4. Tenter `POST /laboutik/auth/bridge/` avec cette clé
5. Vérifier : 400 avec message "Legacy API key, bridge flow not available"

## Compatibilité

- Les routes Laboutik V1 existantes utilisent toujours `HasLaBoutikAccess` (inchangée)
- Les clients V1 (clés sans user) continuent de fonctionner sur ces routes
- Seul le nouvel endpoint `/auth/bridge/` et les futures routes V2 utiliseront `HasLaBoutikTerminalAccess`
```

- [ ] **Step 2 : Mettre à jour `CHANGELOG.md`**

Ajouter en HAUT du fichier `CHANGELOG.md` (le plus récent en premier) :

```markdown
## X. Authentification hardware via TermUser / Hardware auth via TermUser

**Quoi / What:** Refactor de l'auth des terminaux LaBoutik (POS + Android) via
un pont `/laboutik/auth/bridge/` qui échange une clé API contre un cookie de
session Django. Création automatique d'un TermUser à l'appairage, révocation
instantanée via `is_active=False`.

**Pourquoi / Why:** Simplifier le flow côté client (plus de hack HTML injection),
aligner avec le pattern Pi controlvanne, permettre une révocation instantanée
native Django.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| AuthBillet/models.py | +terminal_role, +TERMINAL_ROLE_CHOICES, TermUser.save() |
| discovery/models.py | +terminal_role sur PairingDevice |
| discovery/views.py | ClaimPinView route selon terminal_role, +_create_laboutik_terminal |
| BaseBillet/models.py | LaBoutikAPIKey.user OneToOneField nullable |
| BaseBillet/permissions.py | +HasLaBoutikTerminalAccess (HasLaBoutikAccess inchangée) |
| laboutik/views.py | +LaBoutikAuthBridgeView |
| laboutik/urls.py | +path auth/bridge/ |
| Administration/admin_tenant.py | +TermUserAdmin avec sidebar |
| tests/pytest/conftest.py | +fixture terminal_client |

### Migration
- **Migration nécessaire / Migration required:** Oui / Yes
- 3 migrations AddField (non-destructives) :
  - `AuthBillet.00XX_terminal_role`
  - `discovery.00XX_pairingdevice_terminal_role`
  - `BaseBillet.00XX_laboutikapikey_user`
- Commande : `docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing`
```

Remplacer `X` par le numéro chronologique suivant les entrées existantes.

- [ ] **Step 3 : Ajouter les pièges dans `tests/PIEGES.md`**

Ajouter à la fin de `tests/PIEGES.md` (les numéros exacts dépendent de l'existant, viser 9.45-9.47 ou adapter) :

```markdown
---

### Auth hardware TermUser (session 30, avril 2026)

**9.45 — `TermUser.save()` force `espece=TE` systématiquement.**
Si un test passe `espece='HU'` à `TermUser.objects.create(...)`, la valeur est
écrasée par `TYPE_TERM`. Pour tester un user humain, utiliser `HumanUser` ou
`TibilletUser` directement, pas le proxy `TermUser`.

**9.46 — `LaBoutikAPIKey.user` est `OneToOneField` : un user = une clé max.**
Deux `LaBoutikAPIKey.objects.create_key(user=same_user)` lèvent `IntegrityError`
sur la contrainte unique. En test, toujours créer un user dédié par clé.

**9.47 — `client.force_login(term_user)` ne pose PAS `set_expiry(12h)`.**
La fixture `terminal_client` utilise `force_login` pour la rapidité, mais
cela ne simule pas exactement le bridge. Pour tester l'expiration de session,
faire un vrai POST sur `/laboutik/auth/bridge/`.
```

- [ ] **Step 4 : Lancer les traductions**

Run :
```bash
docker exec lespass_django poetry run django-admin makemessages -l fr
docker exec lespass_django poetry run django-admin makemessages -l en
```

Expected : nouveaux msgid dans `locale/fr/LC_MESSAGES/django.po` et `locale/en/LC_MESSAGES/django.po`.

- [ ] **Step 5 : Éditer les .po pour remplir les msgstr**

Ouvrir `locale/fr/LC_MESSAGES/django.po` et `locale/en/LC_MESSAGES/django.po`, chercher les nouveaux msgid (Terminal role, LaBoutik POS, Connected tap, Kiosk / self-service, Revoke this terminal, etc.) et remplir les `msgstr`.

Pour le français, les msgstr probablement déjà corrects (même langue). Pour l'anglais, traduire si le msgid original est en français.

Supprimer les flags `#, fuzzy` s'il y en a.

- [ ] **Step 6 : Compiler les traductions**

Run : `docker exec lespass_django poetry run django-admin compilemessages`

Expected : génération des fichiers `.mo`.

- [ ] **Step 7 : Checkpoint commit**

Commit suggéré : `docs: add hardware auth bridge documentation and translations`.

---

## Task 14 : Validation finale — suite complète

- [ ] **Step 1 : Lancer la suite pytest complète**

Run : `docker exec lespass_django poetry run pytest tests/pytest/ -q --tb=short`

Expected : tous les tests passent (ou au minimum autant qu'avant le refactor — noter le delta si régression).

- [ ] **Step 2 : Lancer les tests E2E (si Traefik tourne)**

Run : `docker exec lespass_django poetry run pytest tests/e2e/test_laboutik_auth_bridge.py -v -s`

Expected : PASS.

- [ ] **Step 3 : Vérifier `manage.py check --deploy` si applicable**

Run : `docker exec lespass_django poetry run python /DjangoFiles/manage.py check`

Expected : `System check identified no issues (0 silenced).`

- [ ] **Step 4 : Test manuel navigateur**

1. Aller sur `https://lespass.tibillet.localhost/admin/`
2. Créer un PairingDevice (role LB)
3. Claim via curl (voir `A TESTER et DOCUMENTER/hardware-auth-bridge.md`)
4. Bridge + curl vers `/laboutik/caisse/`
5. Révoquer via admin, re-tester l'accès
6. Confirmer que tous les scénarios du fichier A TESTER passent

- [ ] **Step 5 : Ruff format et lint**

Run :
```bash
docker exec lespass_django poetry run ruff check --fix /DjangoFiles/AuthBillet/models.py /DjangoFiles/discovery/views.py /DjangoFiles/BaseBillet/permissions.py /DjangoFiles/laboutik/views.py /DjangoFiles/Administration/admin_tenant.py
docker exec lespass_django poetry run ruff format /DjangoFiles/AuthBillet/models.py /DjangoFiles/discovery/views.py /DjangoFiles/BaseBillet/permissions.py /DjangoFiles/laboutik/views.py /DjangoFiles/Administration/admin_tenant.py
```

- [ ] **Step 6 : Checkpoint commit final**

Commit suggéré : `chore: ruff format + final validation for auth hardware`.

---

## Récapitulatif des critères d'acceptation (spec §13)

- [ ] Un PairingDevice créé avec `terminal_role=LB` produit un TermUser avec `espece=TE`, `terminal_role=LB`, `client_source=tenant` (Tasks 1-5)
- [ ] `POST /laboutik/auth/bridge/` avec une clé valide retourne 204 et pose un cookie session (Task 6)
- [ ] Le cookie session permet ensuite d'accéder à `/laboutik/caisse/` sans header (Tasks 6, 8)
- [ ] `user.is_active=False` bloque immédiatement les requêtes suivantes avec le cookie (Task 6, 9)
- [ ] Un client V1 (clé sans user, header Api-Key) continue de fonctionner sur les routes V1 (Task 7, 11)
- [ ] `TermUserAdmin` dans Unfold liste les terminaux, filtre par rôle, permet révocation bulk + individuelle (Task 9)
- [ ] Les tests pytest Laboutik passent (migration auth_headers → terminal_client) (Task 11)
- [ ] Les nouveaux tests pytest passent (Tasks 5, 6, 7, 10)
- [ ] Le test E2E Playwright passe (Task 12)
- [ ] Traductions FR/EN à jour (Task 13)

---

## Hors scope (rappel)

- Controlvanne : implémentation du même pattern sur `TireuseAPIKey` — phase suivante
- Kiosque : rôle KI stocké mais pas d'UI dédiée — phase suivante (Task 5 Step 4 crée un TermUser KI qui fonctionne mais sans features spécifiques)
- iOS, hardware_type, audit log : YAGNI
- Migration des routes V1 Laboutik vers V2 : au cas par cas plus tard
