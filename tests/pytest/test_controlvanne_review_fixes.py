"""
Tests de garde issus de la review critique du 2026-07-06 (CHANTIER-03).
/ Guard tests from the 2026-07-06 critical review (CHANTIER-03).

Réf : TECH_DOC/SESSIONS/CONTROLVANNE/REVIEW-2026-07-06-tour-critique.md
- C1 : double facturation sur pour_end concurrents (verrou session manquant)
- C3 : 500 au lieu d'un refus propre sur carte sans wallet résoluble
- I2 : swap de fût sans Stock inventaire → reservoir_ml périmé
- I3 : volume_ml négatif accepté par EventSerializer
- I4 : dernier_volume_ml pas mis à jour à la fermeture de session
"""
import json
import threading
import uuid
from decimal import Decimal
from unittest import mock

import pytest
from django.test import Client as DjangoClient
from django_tenants.utils import schema_context


# ─────────────────────────────────────────────────────────────────────
# Fixtures locales (pattern de test_controlvanne_billing, noms distincts
# pour ne pas entrer en collision sur la DB dev partagée)
# / Local fixtures (same pattern as test_controlvanne_billing, distinct
# names to avoid collisions on the shared dev DB)
# ─────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def rf_api_key(tenant):
    """TireuseAPIKey pour ces tests / TireuseAPIKey for these tests."""
    with schema_context(tenant.schema_name):
        from controlvanne.models import TireuseAPIKey

        _obj, key_string = TireuseAPIKey.objects.create_key(name="test-review-fixes")
        yield key_string
        TireuseAPIKey.objects.filter(name="test-review-fixes").delete()


@pytest.fixture(scope="module")
def rf_asset_tlf(tenant):
    """Premier asset TLF actif du tenant / First active TLF asset of the tenant."""
    with schema_context(tenant.schema_name):
        from fedow_core.models import Asset
        from AuthBillet.models import Wallet

        wallet_lieu, _ = Wallet.objects.get_or_create(
            origin=tenant,
            name=f"Wallet du lieu {tenant.schema_name}",
        )
        asset = (
            Asset.objects.filter(
                tenant_origin=tenant, category=Asset.TLF, archive=False
            )
            .order_by("name")
            .first()
        )
        if asset is None:
            asset = Asset.objects.create(
                name="TLF review fixes",
                currency_code="RFX",
                category=Asset.TLF,
                tenant_origin=tenant,
                wallet_origin=wallet_lieu,
            )
        return asset


@pytest.fixture
def rf_carte_avec_solde(tenant, rf_asset_tlf):
    """CarteCashless avec wallet éphémère et 10.00 EUR de solde TLF.
    / CarteCashless with ephemeral wallet and 10.00 EUR TLF balance."""
    with schema_context(tenant.schema_name):
        from QrcodeCashless.models import CarteCashless
        from AuthBillet.models import Wallet
        from fedow_core.models import Token

        tag_id = uuid.uuid4().hex[:8].upper()
        wallet_client = Wallet.objects.create(
            origin=tenant,
            name=f"Wallet review fixes {tag_id}",
        )
        carte = CarteCashless.objects.create(
            tag_id=tag_id,
            number=uuid.uuid4().hex[:8].upper(),
            wallet_ephemere=wallet_client,
        )
        Token.objects.create(wallet=wallet_client, asset=rf_asset_tlf, value=1000)
        return carte


@pytest.fixture
def rf_carte_sans_wallet(tenant):
    """CarteCashless SANS user et SANS wallet éphémère (carte vierge).
    / CarteCashless WITHOUT user and WITHOUT ephemeral wallet (blank card)."""
    with schema_context(tenant.schema_name):
        from QrcodeCashless.models import CarteCashless

        return CarteCashless.objects.create(
            tag_id=uuid.uuid4().hex[:8].upper(),
            number=uuid.uuid4().hex[:8].upper(),
        )


@pytest.fixture(scope="module")
def rf_tireuse(tenant):
    """TireuseBec avec fût à 5 EUR/L et réservoir suivi (non illimité).
    / TireuseBec with a 5 EUR/L keg and tracked reservoir (not unlimited)."""
    with schema_context(tenant.schema_name):
        from controlvanne.models import TireuseBec
        from BaseBillet.models import Product, Price
        from laboutik.models import PointDeVente

        # Nettoyage anti-collision DB dev (cf. piège documenté dans
        # test_controlvanne_billing) / Anti-collision cleanup on shared dev DB
        TireuseBec.objects.filter(nom_tireuse="Tireuse review fixes").delete()
        PointDeVente.objects.filter(name="Tireuse review fixes").delete()

        produit_fut, _ = Product.objects.get_or_create(
            name="Fut review fixes",
            categorie_article="U",
            defaults={"publish": True},
        )
        if not produit_fut.prices.filter(poids_mesure=True).exists():
            Price.objects.create(
                product=produit_fut,
                name="Litre",
                prix=Decimal("5.00"),
                poids_mesure=True,
            )

        tireuse = TireuseBec.objects.create(
            nom_tireuse="Tireuse review fixes",
            enabled=True,
            fut_actif=produit_fut,
            reservoir_illimite=True,
            reservoir_ml=Decimal("30000.00"),
        )
        if tireuse.point_de_vente:
            PointDeVente.objects.filter(pk=tireuse.point_de_vente_id).update(
                hidden=True
            )
        return tireuse


def _ouvrir_session(tenant, tireuse, carte):
    """Crée une RfidSession ouverte et autorisée (comme après un authorize).
    / Creates an open, authorized RfidSession (as after an authorize call)."""
    with schema_context(tenant.schema_name):
        from controlvanne.models import RfidSession

        return RfidSession.objects.create(
            tireuse_bec=tireuse,
            uid=carte.tag_id,
            carte=carte,
            authorized=True,
            allowed_ml_session=Decimal("2000.00"),
        )


# ─────────────────────────────────────────────────────────────────────
# C1 — Double facturation sur pour_end concurrents
# ─────────────────────────────────────────────────────────────────────


class TestC1DoubleFacturationConcurrente:
    def test_deux_pour_end_concurrents_facturent_une_seule_fois(
        self, tenant, rf_api_key, rf_tireuse, rf_carte_avec_solde
    ):
        """Deux pour_end simultanés (retry réseau du Pi) sur la même session :
        UNE seule facturation doit passer, l'autre doit être ignorée proprement.
        / Two simultaneous pour_end (Pi network retry) on the same session:
        exactly ONE billing must happen, the other must be cleanly ignored."""
        session = _ouvrir_session(tenant, rf_tireuse, rf_carte_avec_solde)

        with schema_context(tenant.schema_name):
            from BaseBillet.models import LigneArticle

            lignes_avant = LigneArticle.objects.filter(
                carte=rf_carte_avec_solde
            ).count()

        # Barrier : les 2 threads envoient leur POST exactement en même temps
        # / Barrier: both threads send their POST at the exact same time
        barriere = threading.Barrier(2)
        reponses = []
        erreurs = []

        def envoyer_pour_end():
            # Chaque thread a son propre client et sa propre connexion DB
            # / Each thread gets its own client and DB connection
            from django.db import connections

            try:
                client_http = DjangoClient(HTTP_HOST="lespass.tibillet.localhost")
                barriere.wait(timeout=10)
                reponse = client_http.post(
                    "/controlvanne/api/tireuse/event/",
                    data=json.dumps(
                        {
                            "tireuse_uuid": str(rf_tireuse.uuid),
                            "uid": rf_carte_avec_solde.tag_id,
                            "event_type": "pour_end",
                            "volume_ml": "250.00",
                        }
                    ),
                    content_type="application/json",
                    HTTP_AUTHORIZATION=f"Api-Key {rf_api_key}",
                )
                reponses.append(reponse.status_code)
            except Exception as erreur:
                erreurs.append(erreur)
            finally:
                connections.close_all()

        thread_a = threading.Thread(target=envoyer_pour_end)
        thread_b = threading.Thread(target=envoyer_pour_end)
        thread_a.start()
        thread_b.start()
        thread_a.join(timeout=30)
        thread_b.join(timeout=30)

        assert not erreurs, f"Erreurs dans les threads : {erreurs}"
        # Les deux appels doivent aboutir sans 500 (le concurrent est ignoré,
        # pas planté) / Both calls must succeed without a 500 (the concurrent
        # one is ignored, not crashed)
        assert all(code == 200 for code in reponses), f"Codes HTTP : {reponses}"

        with schema_context(tenant.schema_name):
            from BaseBillet.models import LigneArticle

            lignes_apres = LigneArticle.objects.filter(
                carte=rf_carte_avec_solde
            ).count()

        nombre_facturations = lignes_apres - lignes_avant
        assert nombre_facturations == 1, (
            f"{nombre_facturations} facturations pour UN tirage "
            f"(double débit client !) — session {session.pk}"
        )


# ─────────────────────────────────────────────────────────────────────
# C3 — Carte sans wallet résoluble : refus propre, pas d'exception
# ─────────────────────────────────────────────────────────────────────


class TestC3CarteSansWallet:
    def test_contexte_cashless_carte_vierge_retourne_none(
        self, tenant, rf_carte_sans_wallet, rf_asset_tlf
    ):
        """Carte sans user ni wallet éphémère, inconnue du Fedow legacy :
        obtenir_contexte_cashless doit retourner None (refus propre),
        PAS lever une Exception (qui devenait un 500 au POS tireuse).
        / Blank card unknown to legacy Fedow: obtenir_contexte_cashless must
        return None (clean refusal), NOT raise (which became a 500)."""
        with schema_context(tenant.schema_name):
            from controlvanne.billing import obtenir_contexte_cashless

            # Simule un Fedow legacy qui ne connaît pas la carte (ou can_fedow
            # False) / Simulates a legacy Fedow that doesn't know the card
            with mock.patch(
                "laboutik.views.obtenir_wallet_carte_depuis_fedow",
                return_value=None,
            ):
                contexte = obtenir_contexte_cashless(rf_carte_sans_wallet)

            assert contexte is None


# ─────────────────────────────────────────────────────────────────────
# I2 — Swap de fût sans Stock : le réservoir ne doit pas rester périmé
# ─────────────────────────────────────────────────────────────────────


class TestI2SwapFutSansStock:
    def test_swap_fut_sans_stock_remet_le_reservoir_a_zero(self, tenant):
        """Changer le fût actif vers un produit SANS Stock inventaire :
        reservoir_ml doit être remis à 0 (pas d'info = pas de réserve connue),
        pas conserver la valeur de l'ancien fût.
        / Swapping to a keg WITHOUT inventory Stock: reservoir_ml must reset
        to 0 (no info = no known reserve), not keep the old keg's value."""
        with schema_context(tenant.schema_name):
            from controlvanne.models import TireuseBec
            from BaseBillet.models import Product
            from laboutik.models import PointDeVente

            TireuseBec.objects.filter(nom_tireuse="Tireuse swap fut test").delete()
            PointDeVente.objects.filter(name="Tireuse swap fut test").delete()

            fut_a, _ = Product.objects.get_or_create(
                name="Fut swap A", categorie_article="U", defaults={"publish": True}
            )
            fut_b_sans_stock, _ = Product.objects.get_or_create(
                name="Fut swap B sans stock",
                categorie_article="U",
                defaults={"publish": True},
            )

            tireuse = TireuseBec.objects.create(
                nom_tireuse="Tireuse swap fut test",
                enabled=True,
                fut_actif=fut_a,
                reservoir_illimite=False,
                reservoir_ml=Decimal("150.00"),
            )
            if tireuse.point_de_vente:
                PointDeVente.objects.filter(pk=tireuse.point_de_vente_id).update(
                    hidden=True
                )

            # Swap vers un fût neuf qui n'a pas d'enregistrement Stock
            # / Swap to a fresh keg that has no Stock record
            tireuse.fut_actif = fut_b_sans_stock
            tireuse.save()
            tireuse.refresh_from_db()

            assert tireuse.reservoir_ml == Decimal("0.00"), (
                f"reservoir_ml={tireuse.reservoir_ml} : la valeur de l'ancien "
                f"fût a été conservée sur le nouveau fût"
            )


# ─────────────────────────────────────────────────────────────────────
# I3 — volume_ml négatif refusé par le serializer
# ─────────────────────────────────────────────────────────────────────


class TestI3VolumeNegatif:
    def test_volume_negatif_rejete(self):
        """Un Pi défaillant qui envoie volume_ml négatif doit être rejeté
        à la validation, pas propagé jusqu'au kiosk (« -100 cl »).
        / A faulty Pi sending negative volume_ml must be rejected at
        validation, not propagated to the kiosk ("-100 cl")."""
        from controlvanne.serializers import EventSerializer

        serializer = EventSerializer(
            data={
                "tireuse_uuid": str(uuid.uuid4()),
                "uid": "A1B2C3D4",
                "event_type": "pour_update",
                "volume_ml": "-100.00",
            }
        )
        assert not serializer.is_valid()
        assert "volume_ml" in serializer.errors


# ─────────────────────────────────────────────────────────────────────
# I4 — dernier_volume_ml mis à jour à la fermeture
# ─────────────────────────────────────────────────────────────────────


class TestI4DernierVolumeALaFermeture:
    def test_close_with_volume_met_a_jour_dernier_volume(
        self, tenant, rf_tireuse, rf_carte_avec_solde
    ):
        """Un tirage court sans pour_update : le volume affiché au kiosk
        (dernier_volume_ml) doit refléter le volume final, pas rester à 0.
        / A short pour without any pour_update: the kiosk-displayed volume
        (dernier_volume_ml) must reflect the final volume, not stay at 0."""
        session = _ouvrir_session(tenant, rf_tireuse, rf_carte_avec_solde)

        with schema_context(tenant.schema_name):
            session.close_with_volume(250.0)
            session.refresh_from_db()

            assert session.dernier_volume_ml == Decimal("250.00"), (
                f"dernier_volume_ml={session.dernier_volume_ml} : le kiosk "
                f"affichera 0 cl pour un tirage de 250 ml"
            )
