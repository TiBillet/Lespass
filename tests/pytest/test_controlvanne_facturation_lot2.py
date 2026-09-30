# ruff: noqa: F811
# F811 : les paramètres des tests portent le nom des fixtures importées de
# test_controlvanne_billing.py — c'est ainsi que pytest les injecte.
# / Test parameters are named after imported fixtures: that is how pytest injects them.
"""
Tests du lot 2 de l'audit du 2026-09-26 (facturation / argent des tireuses).
/ Tests for lot 2 of the 2026-09-26 audit (tap billing / money).

LOCALISATION : tests/pytest/test_controlvanne_facturation_lot2.py

- 2.1 : une erreur de base dans le décrément de stock ne casse plus la facture
- 2.2 : le réservoir est décrémenté en SQL, sur la valeur à jour
- 2.3 : les montants de l'écran sont calculés par le serveur (mêmes formules)
- 2.4 : un pour_update coûte peu de requêtes SQL
- 2.5 : une carte maintenance limitée à certaines tireuses est refusée ailleurs
- 2.6 : le refus sur tireuse désactivée est poussé au kiosk

Les fixtures « asset / tireuse / clé » viennent de test_controlvanne_billing.py.
Elles sont importées PAR LEUR NOM (pas de « import * »), sinon pytest
recollecterait les tests de ce fichier.
/ Fixtures imported by name from test_controlvanne_billing.py.
"""

import json
import uuid
from decimal import Decimal
from unittest import mock

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django_tenants.utils import tenant_context

from test_controlvanne_billing import (  # noqa: F401 (fixtures pytest)
    asset_tlf,
    billing_client,
    billing_headers,
    tireuse_api_key_billing,
    tireuse_billing,
)


# ─────────────────────────────────────────────────────────────────────
# Aides / Helpers
# ─────────────────────────────────────────────────────────────────────


def _nouvelle_carte(tenant, asset, solde_centimes):
    """
    Carte neuve avec un solde TLF, propre à un test (ne touche pas aux autres).
    / Fresh card with a TLF balance, private to one test.
    """
    with tenant_context(tenant):
        from AuthBillet.models import Wallet
        from fedow_core.models import Token
        from QrcodeCashless.models import CarteCashless

        tag_id = uuid.uuid4().hex[:8].upper()
        wallet = Wallet.objects.create(origin=tenant, name=f"Wallet lot2 {tag_id}")
        carte = CarteCashless.objects.create(
            tag_id=tag_id, number=uuid.uuid4().hex[:8].upper(), wallet_ephemere=wallet
        )
        Token.objects.create(wallet=wallet, asset=asset, value=solde_centimes)
    return carte


def _poster(client, headers, chemin, donnees):
    return client.post(
        f"/controlvanne/api/tireuse/{chemin}/",
        data=json.dumps(donnees),
        content_type="application/json",
        **headers,
    )


# ─────────────────────────────────────────────────────────────────────
# 2.3 — Fonctions d'argent communes / Shared money functions
# ─────────────────────────────────────────────────────────────────────


class TestFonctionsDArgent:
    def test_01_montant_en_centimes(self):
        """250 ml à 3,50 €/L = 0,875 € → 88 centimes (formule de la facture)."""
        from controlvanne.billing import calculer_montant_centimes

        assert calculer_montant_centimes(Decimal("250"), Decimal("3.50")) == 88
        assert calculer_montant_centimes(0, Decimal("3.50")) == 0
        assert calculer_montant_centimes(Decimal("250"), Decimal("0")) == 0

    def test_02_nombre_de_verres(self):
        """10,00 € à 5 €/L : un verre de 25 cl coûte 1,25 € → 8 verres."""
        from controlvanne.billing import calculer_nombre_de_verres

        assert calculer_nombre_de_verres(1000, Decimal("5.00")) == 8
        assert calculer_nombre_de_verres(1000, Decimal("0")) is None

    def test_03_formatage_des_euros(self):
        """1410 centimes → « 14,10 € » (ou « 14.10 € » selon la langue active)."""
        from controlvanne.billing import formater_euros

        texte = formater_euros(1410)
        assert texte.startswith("14") and "10" in texte and texte.endswith("€")


# ─────────────────────────────────────────────────────────────────────
# 2.1, 2.2, 2.3, 2.4 — parcours réel / real flow
# ─────────────────────────────────────────────────────────────────────


# Marque django_db : chaque test facture un tirage (ou ferme une session). La vente,
# ses règlements, les cartes et les débits créés par le test disparaissent au rollback
# de fin de test : aucun nettoyage à la main (une vente enregistrée protège la carte,
# le portefeuille et le point de vente contre la suppression).
# / django_db mark: each test bills a pour (or closes a session). The sale, its
# payments, the cards and the debits created by the test vanish on rollback: no manual
# cleanup (a recorded sale protects the card, wallet and POS from deletion).
@pytest.mark.django_db
class TestFacturationLot2:
    def test_04_erreur_de_stock_ne_casse_pas_la_facture(
        self, billing_client, billing_headers, tireuse_billing, tenant, asset_tlf
    ):
        """
        StockService lève une VRAIE erreur SQL (transaction Postgres cassée).
        Grâce au savepoint, la facture est quand même enregistrée (2.1).
        Avant, la requête suivante levait une erreur et tout était annulé.
        """
        from inventaire.models import Stock, UniteStock

        carte = _nouvelle_carte(tenant, asset_tlf, 1000)
        with tenant_context(tenant):
            fut = tireuse_billing.fut_actif
            if not Stock.objects.filter(product=fut).exists():
                Stock.objects.create(
                    product=fut,
                    quantite=0,
                    unite=UniteStock.CL,
                    seuil_alerte=0,
                    autoriser_vente_hors_stock=True,
                )

        def decrementer_en_cassant_la_transaction(**kwargs):
            # Vraie erreur Postgres : la transaction en cours est « aborted »
            # / Real Postgres error: the current transaction is aborted
            with connection.cursor() as curseur:
                curseur.execute("SELECT * FROM table_qui_n_existe_pas_lot2")

        donnees = {"tireuse_uuid": str(tireuse_billing.uuid), "uid": carte.tag_id}
        assert _poster(
            billing_client, billing_headers, "authorize", donnees
        ).json()["authorized"]
        with mock.patch(
            "inventaire.services.StockService.decrementer_pour_vente",
            side_effect=decrementer_en_cassant_la_transaction,
        ):
            reponse = _poster(
                billing_client,
                billing_headers,
                "event",
                {**donnees, "event_type": "pour_end", "volume_ml": "200.00"},
            )
        assert reponse.status_code == 200, reponse.content
        # 200 ml à 5 €/L = 1,00 € facturé / billed
        assert reponse.json()["montant_centimes"] == 100

    def test_05_reservoir_decremente_sur_la_valeur_a_jour(
        self, tireuse_billing, tenant, asset_tlf
    ):
        """
        La tireuse est lue à 5000 ml, puis la base passe à 4000 ml « dans son dos ».
        Fermer une session de 100 ml doit donner 3900 ml, pas 4900 ml (2.2).
        """
        from controlvanne.models import RfidSession, TireuseBec
        from controlvanne.viewsets import _cloturer_session_et_facturer

        carte = _nouvelle_carte(tenant, asset_tlf, 1000)
        with tenant_context(tenant):
            TireuseBec.objects.filter(pk=tireuse_billing.pk).update(
                reservoir_ml=Decimal("5000")
            )
            tireuse_perimee = TireuseBec.objects.get(pk=tireuse_billing.pk)
            TireuseBec.objects.filter(pk=tireuse_billing.pk).update(
                reservoir_ml=Decimal("4000")
            )
            session = RfidSession.objects.create(
                uid=carte.tag_id,
                carte=carte,
                tireuse_bec=tireuse_billing,
                authorized=True,
                is_maintenance=False,
            )
            _cloturer_session_et_facturer(tireuse_perimee, session, Decimal("100"))

            reservoir_final = TireuseBec.objects.get(pk=tireuse_billing.pk).reservoir_ml
            assert reservoir_final == Decimal("3900.00")
            # L'objet en mémoire est aussi à jour / In-memory object is fresh too
            assert tireuse_perimee.reservoir_ml == Decimal("3900.00")

    def test_06_montants_de_l_ecran_calcules_par_le_serveur(
        self, billing_client, billing_headers, tireuse_billing, tenant, asset_tlf
    ):
        """
        Les messages du kiosk portent solde_affiche, nombre_verres et
        prix_servi_*, calculés avec les formules de la facture (2.3).
        En fin de service, prix_servi_centimes = montant réellement facturé.
        """
        carte = _nouvelle_carte(tenant, asset_tlf, 1000)
        messages_envoyes = []

        def capturer(uuid_tireuse, payload, uuid_du_lieu):
            messages_envoyes.append(payload)

        donnees = {"tireuse_uuid": str(tireuse_billing.uuid), "uid": carte.tag_id}
        with mock.patch(
            "controlvanne.viewsets.pousser_aux_kiosks", side_effect=capturer
        ):
            _poster(billing_client, billing_headers, "authorize", donnees)
            _poster(
                billing_client,
                billing_headers,
                "event",
                {**donnees, "event_type": "pour_update", "volume_ml": "100.00"},
            )
            reponse_fin = _poster(
                billing_client,
                billing_headers,
                "event",
                {**donnees, "event_type": "pour_end", "volume_ml": "200.00"},
            )

        message_authorize, message_versement, message_fin = messages_envoyes[-3:]

        # Authorize : 10,00 € à 5 €/L → 8 verres de 25 cl
        assert message_authorize["nombre_verres"] == 8
        assert message_authorize["solde_affiche"].startswith("10")

        # pour_update : solde estimé = 1000 − prix de 100 ml (50 cts) = 950
        assert message_versement["balance"] == "9.50"
        assert message_versement["prix_servi_centimes"] == 50

        # pour_end : montant facturé = montant affiché ; solde relu après débit
        montant_facture = reponse_fin.json()["montant_centimes"]
        assert message_fin["session_done"] is True
        assert message_fin["prix_servi_centimes"] == montant_facture == 100
        assert message_fin["balance"] == "9.00"

    def test_07_pour_update_coute_peu_de_requetes(
        self, billing_client, billing_headers, tireuse_billing, tenant, asset_tlf
    ):
        """
        Un pour_update arrive environ chaque seconde : il doit rester sobre (2.4).
        18 requêtes avant l'audit, 8 après. On garde une petite marge (10).
        """
        carte = _nouvelle_carte(tenant, asset_tlf, 1000)
        donnees = {"tireuse_uuid": str(tireuse_billing.uuid), "uid": carte.tag_id}
        _poster(billing_client, billing_headers, "authorize", donnees)
        with CaptureQueriesContext(connection) as requetes:
            reponse = _poster(
                billing_client,
                billing_headers,
                "event",
                {**donnees, "event_type": "pour_update", "volume_ml": "120.00"},
            )
        assert reponse.status_code == 200
        assert len(requetes.captured_queries) <= 10, len(requetes.captured_queries)
        _poster(
            billing_client,
            billing_headers,
            "event",
            {**donnees, "event_type": "card_removed", "volume_ml": "0.00"},
        )


# ─────────────────────────────────────────────────────────────────────
# 2.5, 2.6 — refus affichés / refusals shown
# ─────────────────────────────────────────────────────────────────────

NOM_TIREUSE_LOT2 = "Tireuse lot2 maintenance test"


@pytest.fixture
def tireuse_desactivee_et_sa_cle(tenant):
    """
    Tireuse hors service (enabled=False) et sa clé API. Supprimées après le test.
    / Disabled tap and its API key. Deleted after the test.
    """
    from fabriques_controlvanne import cle_api_de_la_tireuse

    with tenant_context(tenant):
        from controlvanne.models import TireuseBec
        from laboutik.models import PointDeVente, Terminal

        TireuseBec.objects.filter(nom_tireuse=NOM_TIREUSE_LOT2).delete()
        PointDeVente.objects.filter(name=NOM_TIREUSE_LOT2).delete()
        Terminal.objects.filter(name=NOM_TIREUSE_LOT2).delete()
        tireuse = TireuseBec.objects.create(nom_tireuse=NOM_TIREUSE_LOT2, enabled=False)
    cle = cle_api_de_la_tireuse(tenant, tireuse)
    yield tireuse, {"HTTP_AUTHORIZATION": f"Api-Key {cle}"}
    with tenant_context(tenant):
        TireuseBec.objects.filter(pk=tireuse.pk).delete()
        PointDeVente.objects.filter(name=NOM_TIREUSE_LOT2).delete()
        Terminal.objects.filter(name=NOM_TIREUSE_LOT2).delete()


class TestRefusAffiches:
    def test_08_carte_maintenance_limitee_a_une_autre_tireuse(
        self, billing_client, tireuse_desactivee_et_sa_cle, tireuse_billing, tenant
    ):
        """
        Carte maintenance réservée à tireuse_billing → refusée sur une autre
        tireuse, avec un refus poussé au kiosk (2.5). Sans restriction → acceptée.
        """
        tireuse, headers = tireuse_desactivee_et_sa_cle
        with tenant_context(tenant):
            from controlvanne.models import CarteMaintenance
            from QrcodeCashless.models import CarteCashless

            tag_id = uuid.uuid4().hex[:8].upper()
            carte = CarteCashless.objects.create(
                tag_id=tag_id, number=uuid.uuid4().hex[:8].upper()
            )
            carte_maintenance = CarteMaintenance.objects.create(
                carte=carte, produit="Eau claire"
            )
            carte_maintenance.tireuses.add(tireuse_billing)

        messages_envoyes = []
        donnees = {"tireuse_uuid": str(tireuse.uuid), "uid": tag_id}
        try:
            with mock.patch(
                "controlvanne.viewsets.pousser_aux_kiosks",
                side_effect=lambda uuid_tireuse, payload, uuid_du_lieu: (
                    messages_envoyes.append(payload)
                ),
            ):
                reponse = _poster(billing_client, headers, "authorize", donnees)
            assert reponse.json()["authorized"] is False
            assert "not allowed" in reponse.json()["message"]
            assert messages_envoyes and messages_envoyes[-1]["authorized"] is False

            # Sans restriction, la même carte est acceptée (tireuse hors service)
            # / Without restriction, the same card is accepted
            with tenant_context(tenant):
                carte_maintenance.tireuses.clear()
            reponse = _poster(billing_client, headers, "authorize", donnees)
            assert reponse.json()["authorized"] is True
            assert reponse.json()["is_maintenance"] is True
            _poster(
                billing_client,
                headers,
                "event",
                {**donnees, "event_type": "card_removed", "volume_ml": "0.00"},
            )
        finally:
            with tenant_context(tenant):
                from controlvanne.models import RfidSession

                RfidSession.objects.filter(uid=tag_id).delete()
                CarteMaintenance.objects.filter(carte=carte).delete()
                CarteCashless.objects.filter(pk=carte.pk).delete()

    def test_09_tireuse_desactivee_pousse_le_refus_au_kiosk(
        self, billing_client, tireuse_desactivee_et_sa_cle, tenant, asset_tlf
    ):
        """Carte normale sur tireuse hors service → refus AFFICHÉ sur le kiosk (2.6)."""
        tireuse, headers = tireuse_desactivee_et_sa_cle
        carte = _nouvelle_carte(tenant, asset_tlf, 1000)
        messages_envoyes = []
        with mock.patch(
            "controlvanne.viewsets.pousser_aux_kiosks",
            side_effect=lambda uuid_tireuse, payload, uuid_du_lieu: (
                messages_envoyes.append(payload)
            ),
        ):
            reponse = _poster(
                billing_client,
                headers,
                "authorize",
                {"tireuse_uuid": str(tireuse.uuid), "uid": carte.tag_id},
            )
        assert reponse.json()["authorized"] is False
        assert "disabled" in reponse.json()["message"].lower()
        assert messages_envoyes, "le refus doit être poussé au kiosk"
        assert messages_envoyes[-1]["present"] is True
        assert messages_envoyes[-1]["authorized"] is False
