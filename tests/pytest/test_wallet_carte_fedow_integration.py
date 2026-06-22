"""
Test d'INTÉGRATION RÉELLE (sans mock) — branchement de bout en bout entre la
résolution du wallet d'une carte NFC et le VRAI serveur Fedow.
/ REAL INTEGRATION test (no mock) — end-to-end wiring between the NFC card wallet
resolution and the REAL Fedow server.

LOCALISATION : tests/pytest/test_wallet_carte_fedow_integration.py

POURQUOI CE TEST / WHY THIS TEST :
`tests/pytest/test_wallet_carte_fedow.py` couvre la logique en MOCKANT FedowAPI :
il vérifie que `obtenir_wallet_carte_depuis_fedow` miroir bien le wallet, mais ne
prouve PAS que l'appel HTTP réel `card_tag_id_retrieve` fonctionne ni que le
miroir colle au wallet réel de Fedow. Ce test-ci appelle le VRAI Fedow (pas de
mock) pour valider le branchement complet : provisionner une carte dans Fedow,
puis vérifier que `_obtenir_ou_creer_wallet(carte)` renvoie un Wallet LOCAL dont
l'uuid == le wallet uuid renvoyé par Fedow.
/ test_wallet_carte_fedow.py mocks FedowAPI. This file calls the REAL Fedow (no
mock) to validate the full wiring: provision a card in Fedow, then check that
`_obtenir_ou_creer_wallet(carte)` returns a LOCAL Wallet whose uuid == the wallet
uuid returned by Fedow.

PRÉREQUIS / PREREQUISITES :
- Le serveur Fedow de dev tourne (container fedow_django) et la place Lespass est
  configurée (`FedowConfig.can_fedow()` vrai). Sinon : SKIP explicite, pas d'échec.
/ The dev Fedow server runs and the Lespass place is configured. Otherwise: SKIP.

NOTE DEBUG/SSL : pytest-django force DEBUG=False, ce qui active la vérification
SSL dans fedow_api (verify=bool(not settings.DEBUG)) — or le certificat Traefik de
dev est auto-signé. On réplique le runtime de dev (DEBUG=True → verify désactivé)
via override_settings(DEBUG=True), comme test_membership_card_wallet_fedow.py.
/ pytest-django forces DEBUG=False (enables SSL verification against the self-signed
dev cert). We replicate dev runtime (DEBUG=True → verify off), like the membership test.
"""

import uuid as uuidlib

import pytest
from django.test import override_settings
from django_tenants.utils import tenant_context


pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _suffix():
    """Suffixe court unique pour éviter les collisions de tag_id.
    / Short unique suffix to avoid tag_id collisions."""
    return uuidlib.uuid4().hex[:6]


def _tag():
    """tag_id de carte de test : 8 caractères max (piège 9.31).
    / Test card tag_id: 8 chars max (pitfall 9.31)."""
    return f"WI{_suffix().upper()}"  # "WI" + 6 = 8 caractères


@pytest.fixture
def carte_provisionnee_dans_fedow(tenant):
    """Provisionne une carte NFC RÉELLE dans Fedow (wallet éphémère, sans user) puis
    crée la CarteCashless locale correspondante. Skip explicite si Fedow indisponible.
    / Provisions a REAL anonymous NFC card in Fedow (ephemeral wallet) then creates
    the matching local CarteCashless. Explicit skip if Fedow is unavailable.

    Nettoyage : la CarteCashless locale et le Wallet miroir créé par la résolution.
    Côté Fedow la carte reste (pas d'endpoint de suppression simple) — pollution
    mineure de la base dev, tag_id unique par run.
    / Cleanup: local CarteCashless + mirror Wallet. The Fedow-side card remains
    (no simple delete endpoint) — minor dev DB noise, unique tag_id per run.
    """
    from django.conf import settings

    from fedow_connect.models import FedowConfig
    from fedow_connect.fedow_api import FedowAPI
    from QrcodeCashless.models import CarteCashless

    with override_settings(DEBUG=True), tenant_context(tenant):
        if not FedowConfig.get_solo().can_fedow():
            pytest.skip(
                "Fedow indisponible (can_fedow=False) — test d'intégration sauté."
            )

        # 1. On essaie de provisionner une carte fraîche dans le VRAI Fedow (sans
        # user → wallet éphémère). qrcode_uuid : 1er bloc = tag_id en minuscules,
        # reste = uuid v4 valide (convention demo_data_v2._handle_seed_cartes_simulateur).
        # / 1. Try to provision a fresh card in the REAL Fedow (no user → ephemeral).
        tag = _tag()
        cartes = [
            {
                "first_tag_id": tag,
                "qrcode_uuid": f"{tag.lower()}-0000-4000-8000-000000000000",
                "number_printed": tag,
            }
        ]
        try:
            FedowAPI().NFCcard.create(cartes)
        except Exception:
            # La place de ce Fedow n'autorise peut-être pas la création de carte
            # sans signature user (403). On retombe sur les cartes déjà provisionnées :
            # les tags du simulateur de démo (DEMO_TAGID_*), s'ils existent côté Fedow.
            # / This Fedow place may forbid card creation without a user signature (403).
            # Fall back to already-provisioned demo simulator cards (DEMO_TAGID_*).
            tag = None

        # 2. On vérifie que le tag choisi existe RÉELLEMENT côté Fedow. Si la création
        # a échoué ou n'a rien provisionné, on cherche un tag de démo qui résout.
        # / 2. Confirm the chosen tag REALLY exists on Fedow. Otherwise look for a demo tag.
        if tag is not None and FedowAPI().NFCcard.card_tag_id_retrieve(tag) is None:
            tag = None
        if tag is None:
            tags_demo = [
                getattr(settings, nom, None)
                for nom in (
                    "DEMO_TAGID_CM",
                    "DEMO_TAGID_CLIENT1",
                    "DEMO_TAGID_CLIENT2",
                    "DEMO_TAGID_CLIENT3",
                    "DEMO_TAGID_CLIENT4",
                )
            ]
            for tag_demo in tags_demo:
                if tag_demo and FedowAPI().NFCcard.card_tag_id_retrieve(tag_demo):
                    tag = tag_demo
                    break

        if tag is None:
            pytest.skip(
                "Aucune carte réelle disponible dans ce Fedow (création refusée et "
                "aucune carte de démo provisionnée) — test d'intégration sauté."
            )

        # La CarteCashless locale (anonyme, sans user) pointant le même tag_id.
        # get_or_create : un tag de démo peut déjà avoir sa CarteCashless locale.
        # / The local anonymous CarteCashless pointing at the same tag_id.
        carte, carte_creee_par_le_test = CarteCashless.objects.get_or_create(
            tag_id=tag, defaults={"number": tag}
        )

    yield {
        "tenant": tenant,
        "carte": carte,
        "tag": tag,
        "carte_creee_par_le_test": carte_creee_par_le_test,
    }

    # Nettoyage (DB dev partagée, pas de rollback). On ne supprime la CarteCashless
    # locale QUE si c'est le test qui l'a créée (un tag de démo réutilisé doit rester).
    # / Cleanup (shared dev DB, no rollback). Only delete the local CarteCashless if the
    # test created it (a reused demo tag must remain).
    with tenant_context(tenant):
        from fedow_core.models import Token

        carte.refresh_from_db()
        wallet_eph = carte.wallet_ephemere
        carte.wallet_ephemere = None
        carte.save(update_fields=["wallet_ephemere"])
        if carte_creee_par_le_test:
            carte.delete()
        if wallet_eph is not None:
            Token.objects.filter(wallet=wallet_eph).delete()
            try:
                wallet_eph.delete()
            except Exception:
                pass  # un objet lié peut protéger le wallet — best effort


@override_settings(DEBUG=True)
def test_obtenir_ou_creer_wallet_miroir_le_wallet_reel_de_fedow(
    carte_provisionnee_dans_fedow,
):
    """INTÉGRATION RÉELLE (sans mock) : après provisionnement d'une carte dans le VRAI
    Fedow, `_obtenir_ou_creer_wallet(carte)` interroge Fedow (appel HTTP réel) et
    renvoie un Wallet LOCAL dont l'uuid == le wallet_uuid réel renvoyé par Fedow.
    / REAL INTEGRATION (no mock): after provisioning a card in the REAL Fedow,
    `_obtenir_ou_creer_wallet(carte)` queries Fedow (real HTTP call) and returns a
    LOCAL Wallet whose uuid == the real wallet_uuid returned by Fedow.

    C'est ce test qui valide le BRANCHEMENT réseau de bout en bout : le mock de
    test_wallet_carte_fedow.py cacherait une URL cassée ou un schéma de réponse
    changé côté Fedow.
    / This test validates the end-to-end NETWORK wiring: the mock in
    test_wallet_carte_fedow.py would hide a broken URL or a changed Fedow schema.
    """
    from AuthBillet.models import Wallet
    from fedow_connect.fedow_api import FedowAPI
    from laboutik.views import _obtenir_ou_creer_wallet

    tenant = carte_provisionnee_dans_fedow["tenant"]
    carte = carte_provisionnee_dans_fedow["carte"]
    tag = carte_provisionnee_dans_fedow["tag"]

    with tenant_context(tenant):
        # 1. Source de vérité : on demande directement à Fedow le wallet_uuid réel
        # de la carte (appel HTTP réel, pas de mock).
        # / 1. Source of truth: ask the REAL Fedow for the card's real wallet_uuid.
        serialise_fedow = FedowAPI().NFCcard.card_tag_id_retrieve(tag)
        assert serialise_fedow is not None, (
            f"Fedow ne connaît pas la carte {tag} alors qu'on vient de la "
            "provisionner — le provisionnement ou le retrieve a échoué."
        )
        wallet_uuid_fedow = serialise_fedow["wallet_uuid"]

        # 2. Branchement testé : la résolution locale interroge Fedow (appel réel)
        # et miroir le wallet en local.
        # / 2. Wiring under test: the local resolution queries Fedow (real call)
        # and mirrors the wallet locally.
        wallet_local = _obtenir_ou_creer_wallet(carte)

        # 3. Le Wallet local renvoyé a le MÊME uuid que le wallet réel de Fedow.
        # Comparaison en str : get_or_create peut renvoyer l'uuid en str ou UUID.
        # / 3. The returned local Wallet has the SAME uuid as the real Fedow wallet.
        assert wallet_local is not None
        assert str(wallet_local.uuid) == str(wallet_uuid_fedow), (
            f"Le wallet local ({wallet_local.uuid}) ne miroir PAS le wallet réel "
            f"de Fedow ({wallet_uuid_fedow}) pour la carte {tag}."
        )

        # 4. Le miroir local existe bien en base avec cet uuid (un seul exemplaire).
        # / 4. The local mirror really exists in DB with that uuid (single instance).
        assert Wallet.objects.filter(uuid=wallet_uuid_fedow).count() == 1

        # 5. La carte anonyme a été rattachée à son wallet éphémère pour les prochains
        # scans (comportement de obtenir_wallet_carte_depuis_fedow sur carte sans user).
        # / 5. The anonymous card was attached to its ephemeral wallet for next scans.
        if serialise_fedow.get("is_wallet_ephemere"):
            carte.refresh_from_db()
            assert carte.wallet_ephemere is not None
            assert str(carte.wallet_ephemere.uuid) == str(wallet_uuid_fedow)
