# Phase 2 — Auth + API DRF controlvanne

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Le Raspberry Pi s'authentifie via clé API dédiée (`TireuseAPIKey`) et communique avec Django via un ViewSet DRF propre. L'auth kiosk crée une session Django sans exposer le token en query string. Les anciennes vues fonctionnelles sont supprimées.

**Architecture:** Clé API `TireuseAPIKey(AbstractAPIKey)` dans `controlvanne/models.py` — même pattern que `LaBoutikAPIKey` mais dédiée aux tireuses. Permission `HasTireuseAccess` vérifie cette clé OU session admin. `TireuseViewSet(viewsets.ViewSet)` avec 3 actions : `ping`, `authorize`, `event`. Discovery modifié pour créer une `TireuseAPIKey` (au lieu de `LaBoutikAPIKey`) quand le PairingDevice est lié à une tireuse.

**Tech Stack:** Django 4.x, DRF, django-tenants, djangorestframework-api-key, Django Channels (WebSocket existant)

**Spec de reference :** `TECH DOC/SESSIONS/CONTROLVANNE/SPEC_CONTROLVANNE.md` sections 2.5–2.7

**IMPORTANT :** Ne pas faire d'opérations git. Le mainteneur gère git.

---

## Vue d'ensemble des fichiers

| Fichier | Action | Rôle |
|---------|--------|------|
| `controlvanne/models.py` | Modifier | Ajouter `TireuseAPIKey(AbstractAPIKey)` |
| `controlvanne/permissions.py` | Créer | `HasTireuseAccess` (clé API tireuse OU session admin) |
| `controlvanne/serializers.py` | Réécrire | Serializers DRF : `PingSerializer`, `AuthorizeSerializer`, `EventSerializer` |
| `controlvanne/viewsets.py` | Créer | `TireuseViewSet` + `AuthKioskView` |
| `controlvanne/urls.py` | Réécrire | Router DRF + path auth-kiosk |
| `controlvanne/views.py` | Supprimer | Remplacé par viewsets.py |
| `controlvanne/forms.py` | Supprimer | Remplacé par serializers.py |
| `discovery/views.py` | Modifier | Créer `TireuseAPIKey` + renvoyer `tireuse_uuid` quand PairingDevice lié à une tireuse |
| `controlvanne/migrations/0002_tireuseapikey.py` | Créer | Migration pour TireuseAPIKey |
| `tests/pytest/test_controlvanne_api.py` | Créer | Tests pytest pour ViewSet + permission + auth kiosk |

---

## Ordre des tâches

1. Modèle `TireuseAPIKey` + migration
2. Permission `HasTireuseAccess`
3. Serializers DRF
4. `TireuseViewSet` (ping, authorize, event)
5. `AuthKioskView` (POST token → session cookie)
6. URLs (router DRF + auth-kiosk)
7. Discovery : créer `TireuseAPIKey` + renvoyer `tireuse_uuid`
8. Suppression anciennes vues/forms
9. Tests pytest
10. Vérification finale

---

### Tâche 1 : Modèle TireuseAPIKey + migration

**Fichiers :**
- Modifier : `controlvanne/models.py`

- [ ] **Step 1 : Ajouter TireuseAPIKey dans models.py**

Après le bloc d'imports au début du fichier, ajouter l'import :

```python
from rest_framework_api_key.models import AbstractAPIKey
```

Après la classe `Configuration` (singleton), ajouter :

```python
# ──────────────────────────────────────────────────────────────────────
# TireuseAPIKey — clé API dédiée aux Raspberry Pi des tireuses
# / TireuseAPIKey — API key dedicated to tap Raspberry Pi devices
# ──────────────────────────────────────────────────────────────────────

class TireuseAPIKey(AbstractAPIKey):
    """
    Clé API dédiée aux tireuses connectées (controlvanne).
    Même pattern que LaBoutikAPIKey mais pour les tireuses.
    Créée par discovery lors de l'appairage d'un Pi.
    / API key dedicated to connected taps (controlvanne).
    Same pattern as LaBoutikAPIKey but for taps.
    Created by discovery when pairing a Pi.
    LOCALISATION : controlvanne/models.py
    """

    class Meta:
        ordering = ("-created",)
        verbose_name = _("Tap API Key")
        verbose_name_plural = _("Tap API Keys")
```

- [ ] **Step 2 : Générer la migration**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations controlvanne --name tireuseapikey
```

- [ ] **Step 3 : Appliquer la migration**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing
```

- [ ] **Step 4 : Vérifier**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

---

### Tâche 2 : Permission HasTireuseAccess

**Fichiers :**
- Créer : `controlvanne/permissions.py`

- [ ] **Step 1 : Créer le fichier permissions.py**

```python
"""
Permissions DRF pour le module tireuse connectée (controlvanne).
/ DRF permissions for the connected tap module (controlvanne).

LOCALISATION : controlvanne/permissions.py

Pattern : même logique que HasLaBoutikAccess (BaseBillet/permissions.py)
mais avec TireuseAPIKey au lieu de LaBoutikAPIKey.
/ Pattern: same logic as HasLaBoutikAccess (BaseBillet/permissions.py)
but with TireuseAPIKey instead of LaBoutikAPIKey.
"""

import typing

from django.db import connection
from django.http import HttpRequest
from rest_framework.exceptions import PermissionDenied
from rest_framework_api_key.permissions import BaseHasAPIKey

from controlvanne.models import TireuseAPIKey


class HasTireuseAccess(BaseHasAPIKey):
    """
    Permission souple : accepte une clé API tireuse OU un admin tenant connecté.
    / Flexible permission: accepts a tap API key OR a logged-in tenant admin.

    Deux chemins d'accès / Two access paths :
    1. Clé API (header Authorization: Api-Key xxx) → Raspberry Pi de la tireuse
       API key (Authorization: Api-Key xxx header) → tap Raspberry Pi
    2. Session admin tenant (cookie sessionid) → accès navigateur pour debug/admin
       Tenant admin session (sessionid cookie) → browser access for debug/admin
    """
    model = TireuseAPIKey

    def has_permission(self, request: HttpRequest, view: typing.Any) -> bool:
        # Chemin 1 : admin tenant connecté via session navigateur
        # / Path 1: tenant admin logged in via browser session
        utilisateur = request.user
        if utilisateur and utilisateur.is_authenticated:
            est_admin_du_tenant = utilisateur.is_tenant_admin(connection.tenant)
            if est_admin_du_tenant:
                return True

        # Chemin 2 : clé API Tireuse (header Authorization: Api-Key xxx)
        # / Path 2: Tap API key (Authorization: Api-Key xxx header)
        key = self.get_key(request)
        if not key:
            raise PermissionDenied("Missing Tireuse API key or admin session.")

        try:
            api_key = TireuseAPIKey.objects.get_from_key(key)
        except TireuseAPIKey.DoesNotExist:
            raise PermissionDenied("Invalid Tireuse API key.")

        # Attacher la clé à la requête pour usage dans les vues
        # / Attach the key to the request for use in views
        request.tireuse_api_key = api_key
        return super().has_permission(request, view)
```

- [ ] **Step 2 : Vérifier l'import**

```bash
docker exec lespass_django poetry run python -c "from controlvanne.permissions import HasTireuseAccess; print('OK')"
```

---

### Tâche 3 : Serializers DRF

**Fichiers :**
- Réécrire : `controlvanne/serializers.py`

- [ ] **Step 1 : Réécrire serializers.py**

```python
"""
Serializers DRF pour le module tireuse connectée (controlvanne).
/ DRF serializers for the connected tap module (controlvanne).

LOCALISATION : controlvanne/serializers.py

Validation des données entrantes du Raspberry Pi.
Pas de ModelSerializer — serializers explicites (règle FALC).
/ Validation of incoming Raspberry Pi data.
No ModelSerializer — explicit serializers (FALC rule).
"""

from rest_framework import serializers
from django.utils.translation import gettext_lazy as _


class PingSerializer(serializers.Serializer):
    """
    Données du ping de connectivité.
    / Connectivity ping data.

    Le Pi envoie son UUID de tireuse pour confirmer l'association.
    / The Pi sends its tap UUID to confirm the association.
    """
    tireuse_uuid = serializers.UUIDField(
        required=False,
        help_text=_("UUID of the tap (optional, for association check)."),
    )


class AuthorizeSerializer(serializers.Serializer):
    """
    Données d'autorisation NFC : le Pi badge une carte et demande l'autorisation.
    / NFC authorization data: the Pi scans a card and requests authorization.
    """
    tireuse_uuid = serializers.UUIDField(
        help_text=_("UUID of the tap where the card was scanned."),
    )
    uid = serializers.CharField(
        max_length=32,
        help_text=_("NFC card UID (hex string from the reader)."),
    )


# Les types d'événement possibles pendant un service
# / Possible event types during a pour
EVENEMENT_CHOICES = [
    ("pour_start", _("Pour started")),
    ("pour_update", _("Pour update (volume)")),
    ("pour_end", _("Pour ended")),
    ("card_removed", _("Card removed")),
]


class EventSerializer(serializers.Serializer):
    """
    Événement en temps réel pendant un service (tirage de bière).
    / Real-time event during a pour (beer dispensing).

    Le Pi envoie des mises à jour de volume et de statut.
    / The Pi sends volume and status updates.
    """
    tireuse_uuid = serializers.UUIDField(
        help_text=_("UUID of the tap."),
    )
    uid = serializers.CharField(
        max_length=32,
        help_text=_("NFC card UID of the active session."),
    )
    event_type = serializers.ChoiceField(
        choices=EVENEMENT_CHOICES,
        help_text=_("Type of event."),
    )
    volume_ml = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        default=0,
        help_text=_("Cumulative volume served since session start (ml)."),
    )
```

- [ ] **Step 2 : Vérifier l'import**

```bash
docker exec lespass_django poetry run python -c "from controlvanne.serializers import PingSerializer, AuthorizeSerializer, EventSerializer; print('OK')"
```

---

### Tâche 4 : TireuseViewSet

**Fichiers :**
- Créer : `controlvanne/viewsets.py`

- [ ] **Step 1 : Créer viewsets.py avec les 3 actions + AuthKioskView**

```python
"""
ViewSet DRF pour le module tireuse connectée (controlvanne).
/ DRF ViewSet for the connected tap module (controlvanne).

LOCALISATION : controlvanne/viewsets.py

Endpoints du Raspberry Pi :
- ping      → test de connectivité + config tireuse
- authorize → badge NFC → autorisation de service
- event     → mise à jour volume/statut en temps réel

Auth kiosk :
- AuthKioskView → POST token API → cookie session Django (pour le navigateur kiosk)

Conformité djc : ViewSet (pas ModelViewSet), serializers DRF, pas de @csrf_exempt.
/ djc compliance: ViewSet (not ModelViewSet), DRF serializers, no @csrf_exempt.
"""

import logging
from decimal import Decimal

from django.contrib.auth import login
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from controlvanne.models import (
    CarteMaintenance,
    RfidSession,
    TireuseBec,
    TireuseAPIKey,
)
from controlvanne.permissions import HasTireuseAccess
from controlvanne.serializers import (
    AuthorizeSerializer,
    EventSerializer,
    PingSerializer,
)

logger = logging.getLogger(__name__)


class TireuseViewSet(viewsets.ViewSet):
    """
    API du Raspberry Pi pour les tireuses connectées.
    / Raspberry Pi API for connected taps.

    - ping()      → test connexion + config tireuse / connectivity test + tap config
    - authorize() → badge NFC → autorisation / NFC badge → authorization
    - event()     → volume/statut temps réel / real-time volume/status
    """

    permission_classes = [HasTireuseAccess]

    # ─── ping ─────────────────────────────────────────────────────────

    @action(detail=False, methods=["post"], url_path="ping", url_name="ping")
    def ping(self, request):
        """
        POST /controlvanne/api/tireuse/ping/
        Test de connectivité. Renvoie le statut et la config de la tireuse si UUID fourni.
        / Connectivity test. Returns status and tap config if UUID provided.
        """
        serializer = PingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        tireuse_uuid = serializer.validated_data.get("tireuse_uuid")
        if not tireuse_uuid:
            return Response({"status": "pong", "message": "Server online"})

        # Chercher la tireuse sur ce tenant / Find the tap on this tenant
        try:
            tireuse = TireuseBec.objects.get(uuid=tireuse_uuid)
        except TireuseBec.DoesNotExist:
            return Response(
                {"status": "error", "message": "Tap not found on this tenant."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response({
            "status": "pong",
            "tireuse": {
                "uuid": str(tireuse.uuid),
                "nom": tireuse.nom_tireuse,
                "enabled": tireuse.enabled,
                "liquid_label": tireuse.liquid_label,
                "prix_litre": str(tireuse.prix_litre),
                "reservoir_ml": float(tireuse.reservoir_ml),
                "reservoir_max_ml": tireuse.reservoir_max_ml,
                "seuil_mini_ml": float(tireuse.seuil_mini_ml),
                "calibration_factor": (
                    tireuse.debimetre.flow_calibration_factor
                    if tireuse.debimetre else None
                ),
            },
        })

    # ─── authorize ────────────────────────────────────────────────────

    @action(detail=False, methods=["post"], url_path="authorize", url_name="authorize")
    def authorize(self, request):
        """
        POST /controlvanne/api/tireuse/authorize/
        Badge NFC posé sur la tireuse. Vérifie la carte et autorise le service.
        / NFC badge placed on the tap. Checks the card and authorizes pouring.

        Phase 2 : identifie la carte et détecte les cartes maintenance.
        La vérification du solde wallet est prévue en Phase 3.
        / Phase 2: identifies the card and detects maintenance cards.
        Wallet balance check planned for Phase 3.
        """
        serializer = AuthorizeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        tireuse_uuid = serializer.validated_data["tireuse_uuid"]
        uid = serializer.validated_data["uid"]

        # Chercher la tireuse / Find the tap
        try:
            tireuse = TireuseBec.objects.get(uuid=tireuse_uuid)
        except TireuseBec.DoesNotExist:
            return Response(
                {"authorized": False, "message": "Tap not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not tireuse.enabled:
            return Response({"authorized": False, "message": "Tap is disabled."})

        # Chercher la carte NFC / Find the NFC card
        from QrcodeCashless.models import CarteCashless
        carte = CarteCashless.objects.filter(tag_id=uid).first()
        if not carte:
            return Response({"authorized": False, "message": "Unknown card."})

        # Vérifier si c'est une carte de maintenance / Check if it's a maintenance card
        carte_maintenance = None
        is_maintenance = False
        try:
            carte_maintenance = carte.carte_maintenance
            is_maintenance = True
        except CarteMaintenance.DoesNotExist:
            pass

        # Créer la session RFID / Create the RFID session
        session = RfidSession.objects.create(
            uid=uid,
            carte=carte,
            tireuse_bec=tireuse,
            label_snapshot=str(carte),
            liquid_label_snapshot=tireuse.liquid_label,
            is_maintenance=is_maintenance,
            carte_maintenance=carte_maintenance,
            produit_maintenance_snapshot=(
                carte_maintenance.produit if carte_maintenance else ""
            ),
            authorized=True,
            # Phase 3 : allowed_ml calculé depuis le solde wallet
            # / Phase 3: allowed_ml computed from wallet balance
            allowed_ml_session=tireuse.reservoir_ml if is_maintenance else Decimal("500.00"),
            volume_start_ml=Decimal("0.00"),
        )

        logger.info(
            f"Authorize: carte={uid} tireuse={tireuse.nom_tireuse} "
            f"maintenance={is_maintenance} session={session.pk}"
        )

        return Response({
            "authorized": True,
            "session_id": session.pk,
            "is_maintenance": is_maintenance,
            "allowed_ml": float(session.allowed_ml_session),
            "liquid_label": tireuse.liquid_label,
            "message": "Maintenance mode" if is_maintenance else "OK",
        })

    # ─── event ────────────────────────────────────────────────────────

    @action(detail=False, methods=["post"], url_path="event", url_name="event")
    def event(self, request):
        """
        POST /controlvanne/api/tireuse/event/
        Événement temps réel pendant un service (volume, fin de service, retrait carte).
        / Real-time event during a pour (volume, pour end, card removed).

        Phase 2 : met à jour la session + le réservoir + push WebSocket.
        La facturation (Transaction, LigneArticle) est prévue en Phase 3.
        / Phase 2: updates session + reservoir + WebSocket push.
        Billing (Transaction, LigneArticle) planned for Phase 3.
        """
        serializer = EventSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        tireuse_uuid = serializer.validated_data["tireuse_uuid"]
        uid = serializer.validated_data["uid"]
        event_type = serializer.validated_data["event_type"]
        volume_ml = serializer.validated_data.get("volume_ml", Decimal("0"))

        # Chercher la tireuse / Find the tap
        try:
            tireuse = TireuseBec.objects.get(uuid=tireuse_uuid)
        except TireuseBec.DoesNotExist:
            return Response(
                {"status": "error", "message": "Tap not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Chercher la session ouverte pour cette carte sur cette tireuse
        # / Find the open session for this card on this tap
        session = (
            RfidSession.objects
            .filter(tireuse_bec=tireuse, uid=uid, ended_at__isnull=True)
            .order_by("-started_at")
            .first()
        )
        if not session:
            return Response(
                {"status": "error", "message": "No open session for this card."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Traiter selon le type d'événement / Process by event type
        if event_type == "pour_update":
            session.volume_end_ml = volume_ml
            session.volume_delta_ml = volume_ml
            session.dernier_volume_ml = volume_ml
            session.save(update_fields=[
                "volume_end_ml", "volume_delta_ml", "dernier_volume_ml",
            ])

            # Décrémenter le réservoir de la tireuse / Decrement the tap reservoir
            tireuse.reservoir_ml = max(
                Decimal("0"),
                tireuse.reservoir_ml - volume_ml + session.volume_end_ml,
            )
            # Simplification : on stocke le volume cumulatif, pas le delta
            # Le Pi envoie le volume total depuis le début de la session
            # / Simplification: we store cumulative volume, not delta
            # The Pi sends total volume since session start

        elif event_type == "pour_start":
            session.volume_start_ml = volume_ml
            session.save(update_fields=["volume_start_ml"])

        elif event_type in ("pour_end", "card_removed"):
            session.close_with_volume(float(volume_ml))

            # Décrémenter le réservoir avec le volume final / Decrement reservoir with final volume
            if volume_ml > 0:
                tireuse.reservoir_ml = max(
                    Decimal("0"),
                    tireuse.reservoir_ml - Decimal(str(float(volume_ml))),
                )
                tireuse.save(update_fields=["reservoir_ml"])

            logger.info(
                f"Event {event_type}: carte={uid} tireuse={tireuse.nom_tireuse} "
                f"volume={volume_ml}ml session={session.pk}"
            )

        # Le push WebSocket est géré par le signal post_save de TireuseBec
        # / WebSocket push is handled by TireuseBec's post_save signal

        return Response({
            "status": "ok",
            "event_type": event_type,
            "session_id": session.pk,
            "volume_ml": float(volume_ml),
        })


# ──────────────────────────────────────────────────────────────────────
# AuthKioskView — POST token API → cookie session Django
# ──────────────────────────────────────────────────────────────────────

class AuthKioskView(APIView):
    """
    POST /controlvanne/auth-kiosk/
    Le Pi envoie sa clé API dans le header Authorization.
    Django vérifie la clé, crée une session, renvoie Set-Cookie.
    Le Pi récupère le cookie et lance Chromium avec ce cookie.
    / The Pi sends its API key in the Authorization header.
    Django verifies the key, creates a session, returns Set-Cookie.
    The Pi retrieves the cookie and launches Chromium with it.

    LOCALISATION : controlvanne/viewsets.py

    Le token ne doit pas fuiter en query string (logs, referer, historique navigateur).
    / The token must not leak in query string (logs, referer, browser history).
    """
    permission_classes = [HasTireuseAccess]

    def post(self, request):
        # La permission HasTireuseAccess a déjà vérifié la clé API
        # Si on arrive ici, l'accès est autorisé (clé valide ou admin session)
        # / HasTireuseAccess already verified the API key
        # If we reach here, access is authorized (valid key or admin session)

        # Créer une session Django anonyme (pas de User associé)
        # Le Pi utilise cette session pour le WebSocket et le kiosk
        # / Create an anonymous Django session (no User attached)
        # The Pi uses this session for WebSocket and kiosk
        if not request.session.session_key:
            request.session.create()

        # Marquer la session comme authentifiée pour le kiosk
        # / Mark the session as authenticated for the kiosk
        request.session["controlvanne_authenticated"] = True
        request.session.save()

        return Response({
            "status": "ok",
            "message": "Session created. Use the sessionid cookie for kiosk.",
            "session_key": request.session.session_key,
        })
```

- [ ] **Step 2 : Vérifier l'import**

```bash
docker exec lespass_django poetry run python -c "from controlvanne.viewsets import TireuseViewSet, AuthKioskView; print('OK')"
```

---

### Tâche 5 : URLs — router DRF + auth-kiosk

**Fichiers :**
- Réécrire : `controlvanne/urls.py`

- [ ] **Step 1 : Réécrire urls.py**

```python
"""
URLs du module tireuse connectée (controlvanne).
/ URLs for the connected tap module (controlvanne).

LOCALISATION : controlvanne/urls.py

Routes :
- /controlvanne/api/tireuse/ping/       → TireuseViewSet.ping
- /controlvanne/api/tireuse/authorize/  → TireuseViewSet.authorize
- /controlvanne/api/tireuse/event/      → TireuseViewSet.event
- /controlvanne/auth-kiosk/             → AuthKioskView (POST token → session cookie)
"""

from django.urls import path, include
from rest_framework import routers

from controlvanne.viewsets import TireuseViewSet, AuthKioskView

router = routers.DefaultRouter()
router.register(r"api/tireuse", TireuseViewSet, basename="controlvanne-tireuse")

urlpatterns = [
    # Auth kiosk : POST token API → cookie session Django
    # / Auth kiosk: POST API token → Django session cookie
    path("auth-kiosk/", AuthKioskView.as_view(), name="controlvanne-auth-kiosk"),

    # ViewSet DRF : ping, authorize, event
    path("", include(router.urls)),
]
```

- [ ] **Step 2 : Vérifier les URLs**

```bash
docker exec lespass_django poetry run python -c "
from django.urls import reverse
print(reverse('controlvanne-tireuse-ping'))
print(reverse('controlvanne-tireuse-authorize'))
print(reverse('controlvanne-tireuse-event'))
print(reverse('controlvanne-auth-kiosk'))
print('OK')
"
```

---

### Tâche 6 : Discovery — créer TireuseAPIKey quand PairingDevice lié à une tireuse

**Fichiers :**
- Modifier : `discovery/views.py`

- [ ] **Step 1 : Modifier ClaimPinView pour gérer les tireuses**

Dans `discovery/views.py`, remplacer le bloc `try/except` de création de clé API par une logique qui détecte si le PairingDevice est lié à une tireuse :

Ancien code (lignes 53-68) :
```python
        # Basculer dans le schéma du tenant pour créer la clé API LaBoutik
        # Switch to tenant schema to create the LaBoutik API key
        try:
            with tenant_context(tenant_for_this_device):
                laboutik_key, api_key_string = LaBoutikAPIKey.objects.create_key(
                    name=f"discovery-{pairing_device.uuid}"
                )
        except Exception as error:
            logger.error(
                f"Discovery claim: failed to create LaBoutikAPIKey "
                f"for tenant {tenant_for_this_device.name}: {error}"
            )
            return Response(
                {"error": "Failed to create device credentials."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
```

Nouveau code :
```python
        # Basculer dans le schéma du tenant pour créer la clé API
        # Le type de clé dépend de l'association du device :
        # - TireuseAPIKey si le PairingDevice est lié à une TireuseBec
        # - LaBoutikAPIKey sinon (terminal de caisse)
        # / Switch to tenant schema to create the API key
        # Key type depends on device association:
        # - TireuseAPIKey if PairingDevice is linked to a TireuseBec
        # - LaBoutikAPIKey otherwise (cash register terminal)
        tireuse_uuid = None
        try:
            with tenant_context(tenant_for_this_device):
                # Vérifier si une tireuse est liée à ce PairingDevice
                # / Check if a tap is linked to this PairingDevice
                from controlvanne.models import TireuseBec, TireuseAPIKey
                tireuse = TireuseBec.objects.filter(
                    pairing_device=pairing_device
                ).first()

                if tireuse:
                    _key_obj, api_key_string = TireuseAPIKey.objects.create_key(
                        name=f"discovery-tireuse-{pairing_device.uuid}"
                    )
                    tireuse_uuid = str(tireuse.uuid)
                else:
                    _key_obj, api_key_string = LaBoutikAPIKey.objects.create_key(
                        name=f"discovery-{pairing_device.uuid}"
                    )
        except Exception as error:
            logger.error(
                f"Discovery claim: failed to create API key "
                f"for tenant {tenant_for_this_device.name}: {error}"
            )
            return Response(
                {"error": "Failed to create device credentials."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
```

Puis modifier la réponse (lignes 78-82) :

Ancien code :
```python
        return Response({
            "server_url": server_url,
            "api_key": api_key_string,
            "device_name": pairing_device.name,
        }, status=status.HTTP_200_OK)
```

Nouveau code :
```python
        response_data = {
            "server_url": server_url,
            "api_key": api_key_string,
            "device_name": pairing_device.name,
        }
        # Si le device est lié à une tireuse, inclure l'UUID
        # / If the device is linked to a tap, include the UUID
        if tireuse_uuid:
            response_data["tireuse_uuid"] = tireuse_uuid

        return Response(response_data, status=status.HTTP_200_OK)
```

- [ ] **Step 2 : Vérifier la syntaxe**

```bash
docker exec lespass_django poetry run python -c "from discovery.views import ClaimPinView; print('OK')"
```

---

### Tâche 7 : Suppression anciennes vues/forms

**Fichiers :**
- Supprimer : `controlvanne/views.py`
- Supprimer : `controlvanne/forms.py`

- [ ] **Step 1 : Supprimer views.py et forms.py**

```bash
rm /home/jonas/TiBillet/dev/Lespass/controlvanne/views.py
rm /home/jonas/TiBillet/dev/Lespass/controlvanne/forms.py
```

- [ ] **Step 2 : Vérifier que le serveur démarre**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

---

### Tâche 8 : Tests pytest

**Fichiers :**
- Créer : `tests/pytest/test_controlvanne_api.py`

- [ ] **Step 1 : Créer le fichier de tests**

```python
"""
Tests de l'API tireuse connectée (controlvanne) — Phase 2.
/ Tests for the connected tap API (controlvanne) — Phase 2.

LOCALISATION : tests/pytest/test_controlvanne_api.py

Couvre :
- TireuseAPIKey : création et validation de clé
- HasTireuseAccess : permission clé API + session admin
- TireuseViewSet : ping, authorize, event
- AuthKioskView : POST token → session cookie
- Discovery : claim crée TireuseAPIKey quand tireuse liée

Utilise la base dev existante (django-tenants, pas de test DB).
/ Uses existing dev database (django-tenants, no test DB).
"""

import pytest
from decimal import Decimal

from django.test import Client as DjangoClient
from django_tenants.utils import schema_context


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def tireuse_api_key(tenant):
    """Crée une TireuseAPIKey pour les tests.
    / Creates a TireuseAPIKey for tests."""
    with schema_context(tenant.schema_name):
        from controlvanne.models import TireuseAPIKey
        _key_obj, key_string = TireuseAPIKey.objects.create_key(
            name="test-tireuse-key"
        )
        yield key_string
        # Nettoyage / Cleanup
        TireuseAPIKey.objects.filter(name="test-tireuse-key").delete()


@pytest.fixture(scope="session")
def tireuse_headers(tireuse_api_key):
    """En-têtes d'auth avec clé TireuseAPIKey.
    / Auth headers with TireuseAPIKey."""
    return {"HTTP_AUTHORIZATION": f"Api-Key {tireuse_api_key}"}


@pytest.fixture(scope="session")
def tireuse_client():
    """Client Django pour le tenant lespass.
    / Django client for the lespass tenant."""
    return DjangoClient(HTTP_HOST="lespass.tibillet.localhost")


@pytest.fixture(scope="session")
def test_tireuse(tenant):
    """Crée une TireuseBec de test avec un débitmètre.
    / Creates a test TireuseBec with a flow meter."""
    with schema_context(tenant.schema_name):
        from controlvanne.models import TireuseBec, Debimetre
        debimetre = Debimetre.objects.create(
            name="Test YF-S201",
            flow_calibration_factor=6.5,
        )
        tireuse = TireuseBec.objects.create(
            nom_tireuse="Test Tap Phase2",
            enabled=True,
            debimetre=debimetre,
            reservoir_ml=Decimal("5000.00"),
            seuil_mini_ml=Decimal("200.00"),
        )
        yield tireuse
        # Nettoyage / Cleanup
        tireuse.delete()
        debimetre.delete()


@pytest.fixture(scope="session")
def test_carte(tenant):
    """Récupère ou crée une CarteCashless de test.
    / Gets or creates a test CarteCashless."""
    with schema_context(tenant.schema_name):
        from QrcodeCashless.models import CarteCashless
        carte, _created = CarteCashless.objects.get_or_create(
            tag_id="TESTCV01",
            defaults={"number": "TESTCV01", "uuid_qrcode": "testcv01-uuid"},
        )
        yield carte


# ──────────────────────────────────────────────────────────────────────
# Tests : TireuseAPIKey
# ──────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestTireuseAPIKey:
    """Tests de création et validation de TireuseAPIKey.
    / Tests for TireuseAPIKey creation and validation."""

    def test_01_create_key(self, tenant):
        """On peut créer une clé et la valider.
        / Can create a key and validate it."""
        with schema_context(tenant.schema_name):
            from controlvanne.models import TireuseAPIKey
            _obj, key_string = TireuseAPIKey.objects.create_key(name="test-create")
            assert key_string is not None
            assert len(key_string) > 0
            # Vérifier que la clé est valide / Check the key is valid
            assert TireuseAPIKey.objects.is_valid(key_string)
            # Nettoyage / Cleanup
            TireuseAPIKey.objects.filter(name="test-create").delete()


# ──────────────────────────────────────────────────────────────────────
# Tests : Permission HasTireuseAccess
# ──────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestPermission:
    """Tests de la permission HasTireuseAccess.
    / Tests for HasTireuseAccess permission."""

    def test_02_ping_sans_auth_refuse(self, tireuse_client):
        """Requête sans auth → 403.
        / Request without auth → 403."""
        response = tireuse_client.post(
            "/controlvanne/api/tireuse/ping/",
            content_type="application/json",
            data="{}",
        )
        assert response.status_code == 403

    def test_03_ping_avec_cle_tireuse(self, tireuse_client, tireuse_headers):
        """Requête avec TireuseAPIKey → 200.
        / Request with TireuseAPIKey → 200."""
        response = tireuse_client.post(
            "/controlvanne/api/tireuse/ping/",
            content_type="application/json",
            data="{}",
            **tireuse_headers,
        )
        assert response.status_code == 200

    def test_04_ping_avec_laboutik_key_refuse(self, tireuse_client, auth_headers):
        """LaBoutikAPIKey ne doit PAS marcher sur l'endpoint tireuse → 403.
        / LaBoutikAPIKey must NOT work on the tap endpoint → 403."""
        response = tireuse_client.post(
            "/controlvanne/api/tireuse/ping/",
            content_type="application/json",
            data="{}",
            **auth_headers,
        )
        assert response.status_code == 403

    def test_05_ping_avec_admin_session(self, admin_client):
        """Admin tenant connecté via session → 200.
        / Tenant admin logged in via session → 200."""
        response = admin_client.post(
            "/controlvanne/api/tireuse/ping/",
            content_type="application/json",
            data="{}",
        )
        assert response.status_code == 200


# ──────────────────────────────────────────────────────────────────────
# Tests : TireuseViewSet
# ──────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestTireuseViewSet:
    """Tests du ViewSet tireuse.
    / Tests for the tap ViewSet."""

    def test_06_ping_simple(self, tireuse_client, tireuse_headers):
        """Ping sans UUID → pong.
        / Ping without UUID → pong."""
        response = tireuse_client.post(
            "/controlvanne/api/tireuse/ping/",
            content_type="application/json",
            data="{}",
            **tireuse_headers,
        )
        data = response.json()
        assert data["status"] == "pong"
        assert data["message"] == "Server online"

    def test_07_ping_avec_uuid(self, tireuse_client, tireuse_headers, test_tireuse):
        """Ping avec UUID → config de la tireuse.
        / Ping with UUID → tap config."""
        import json
        response = tireuse_client.post(
            "/controlvanne/api/tireuse/ping/",
            content_type="application/json",
            data=json.dumps({"tireuse_uuid": str(test_tireuse.uuid)}),
            **tireuse_headers,
        )
        data = response.json()
        assert data["status"] == "pong"
        assert data["tireuse"]["nom"] == "Test Tap Phase2"
        assert data["tireuse"]["enabled"] is True
        assert data["tireuse"]["calibration_factor"] == 6.5

    def test_08_ping_uuid_inexistant(self, tireuse_client, tireuse_headers):
        """Ping avec UUID invalide → 404.
        / Ping with invalid UUID → 404."""
        import json
        import uuid
        response = tireuse_client.post(
            "/controlvanne/api/tireuse/ping/",
            content_type="application/json",
            data=json.dumps({"tireuse_uuid": str(uuid.uuid4())}),
            **tireuse_headers,
        )
        assert response.status_code == 404

    def test_09_authorize_carte_inconnue(self, tireuse_client, tireuse_headers, test_tireuse):
        """Authorize avec UID inconnu → non autorisé.
        / Authorize with unknown UID → not authorized."""
        import json
        response = tireuse_client.post(
            "/controlvanne/api/tireuse/authorize/",
            content_type="application/json",
            data=json.dumps({
                "tireuse_uuid": str(test_tireuse.uuid),
                "uid": "CARTE_INEXISTANTE",
            }),
            **tireuse_headers,
        )
        data = response.json()
        assert data["authorized"] is False
        assert "Unknown card" in data["message"]

    def test_10_authorize_carte_valide(self, tireuse_client, tireuse_headers, test_tireuse, test_carte):
        """Authorize avec carte valide → autorisé + session créée.
        / Authorize with valid card → authorized + session created."""
        import json
        response = tireuse_client.post(
            "/controlvanne/api/tireuse/authorize/",
            content_type="application/json",
            data=json.dumps({
                "tireuse_uuid": str(test_tireuse.uuid),
                "uid": test_carte.tag_id,
            }),
            **tireuse_headers,
        )
        data = response.json()
        assert data["authorized"] is True
        assert data["is_maintenance"] is False
        assert "session_id" in data

    def test_11_event_pour_end(self, tireuse_client, tireuse_headers, test_tireuse, test_carte):
        """Event pour_end → session fermée.
        / Event pour_end → session closed."""
        import json
        from django_tenants.utils import schema_context
        from controlvanne.models import RfidSession

        # D'abord autoriser pour créer une session ouverte
        # / First authorize to create an open session
        tireuse_client.post(
            "/controlvanne/api/tireuse/authorize/",
            content_type="application/json",
            data=json.dumps({
                "tireuse_uuid": str(test_tireuse.uuid),
                "uid": test_carte.tag_id,
            }),
            **tireuse_headers,
        )

        # Envoyer pour_end / Send pour_end
        response = tireuse_client.post(
            "/controlvanne/api/tireuse/event/",
            content_type="application/json",
            data=json.dumps({
                "tireuse_uuid": str(test_tireuse.uuid),
                "uid": test_carte.tag_id,
                "event_type": "pour_end",
                "volume_ml": "250.00",
            }),
            **tireuse_headers,
        )
        data = response.json()
        assert data["status"] == "ok"
        assert data["event_type"] == "pour_end"

        # Vérifier que la session est fermée / Check session is closed
        with schema_context("lespass"):
            session = RfidSession.objects.filter(
                tireuse_bec=test_tireuse, uid=test_carte.tag_id
            ).order_by("-started_at").first()
            assert session.ended_at is not None
            assert session.volume_delta_ml == Decimal("250.00")


# ──────────────────────────────────────────────────────────────────────
# Tests : AuthKioskView
# ──────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestAuthKiosk:
    """Tests de l'auth kiosk (POST token → session cookie).
    / Tests for kiosk auth (POST token → session cookie)."""

    def test_12_auth_kiosk_sans_auth(self, tireuse_client):
        """Auth kiosk sans clé → 403.
        / Auth kiosk without key → 403."""
        response = tireuse_client.post(
            "/controlvanne/auth-kiosk/",
            content_type="application/json",
            data="{}",
        )
        assert response.status_code == 403

    def test_13_auth_kiosk_avec_cle(self, tireuse_client, tireuse_headers):
        """Auth kiosk avec clé → 200 + session_key.
        / Auth kiosk with key → 200 + session_key."""
        response = tireuse_client.post(
            "/controlvanne/auth-kiosk/",
            content_type="application/json",
            data="{}",
            **tireuse_headers,
        )
        data = response.json()
        assert response.status_code == 200
        assert data["status"] == "ok"
        assert "session_key" in data
        assert len(data["session_key"]) > 0
```

- [ ] **Step 2 : Lancer les tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_controlvanne_api.py -v --timeout=120
```

---

### Tâche 9 : Vérification finale

- [ ] **Step 1 : System check**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

- [ ] **Step 2 : Tests controlvanne**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_controlvanne_api.py -v --timeout=120
```

- [ ] **Step 3 : Non-régression complète**

```bash
docker exec lespass_django poetry run pytest tests/pytest/ -q --timeout=120
```

- [ ] **Step 4 : Vérifier les URLs DRF**

```bash
docker exec lespass_django poetry run python -c "
from django.urls import reverse
urls = [
    'controlvanne-tireuse-ping',
    'controlvanne-tireuse-authorize',
    'controlvanne-tireuse-event',
    'controlvanne-auth-kiosk',
]
for name in urls:
    print(f'{name} → {reverse(name)}')
print('Toutes les URLs OK')
"
```

---

## Résumé des fichiers modifiés

| Fichier | Changement |
|---------|------------|
| `controlvanne/models.py` | +`TireuseAPIKey(AbstractAPIKey)` |
| `controlvanne/permissions.py` | CRÉÉ — `HasTireuseAccess` |
| `controlvanne/serializers.py` | RÉÉCRIT — 3 serializers DRF |
| `controlvanne/viewsets.py` | CRÉÉ — `TireuseViewSet` + `AuthKioskView` |
| `controlvanne/urls.py` | RÉÉCRIT — router DRF + auth-kiosk |
| `controlvanne/views.py` | SUPPRIMÉ |
| `controlvanne/forms.py` | SUPPRIMÉ |
| `discovery/views.py` | Modifié — `TireuseAPIKey` quand tireuse liée |
| `controlvanne/migrations/0002_*.py` | Migration auto TireuseAPIKey |
| `tests/pytest/test_controlvanne_api.py` | CRÉÉ — 13 tests |

## Notes Phase 3

Le ViewSet est prêt pour la facturation. Points d'accroche :
- `authorize` : remplacer `allowed_ml_session=500` par le calcul depuis `WalletService.obtenir_solde()`
- `event(pour_end)` : ajouter `TransactionService.creer_vente()` + `LigneArticle` + `MouvementStock`
