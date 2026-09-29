"""
Tests pytest pour la facturation tireuse (controlvanne/billing.py + viewsets.py).
/ Pytest tests for tap billing (controlvanne/billing.py + viewsets.py).

LOCALISATION : tests/pytest/test_controlvanne_billing.py

Couvre :
- TestCalculVolume : tests unitaires de calculer_volume_autorise_ml
- TestBillingIntegration : tests integration authorize + pour_end via API
"""

import uuid
from decimal import Decimal

import pytest
from django.test import Client as DjangoClient
from django_tenants.utils import schema_context


# ─────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def tireuse_api_key_billing(tenant, tireuse_billing):
    """Clé API du terminal de tireuse_billing (appairé comme par discovery).
    Une clé doit appartenir au terminal de la tireuse visée (audit, point 1.4).
    / API key of tireuse_billing's terminal (paired like discovery does)."""
    from fabriques_controlvanne import cle_api_de_la_tireuse

    return cle_api_de_la_tireuse(tenant, tireuse_billing)


@pytest.fixture(scope="session")
def billing_headers(tireuse_api_key_billing):
    """En-tetes HTTP auth pour les tests billing.
    / HTTP auth headers for billing tests."""
    return {"HTTP_AUTHORIZATION": f"Api-Key {tireuse_api_key_billing}"}


@pytest.fixture(scope="session")
def billing_client():
    """Client Django avec HTTP_HOST pour le tenant lespass.
    / Django client with HTTP_HOST for lespass tenant."""
    return DjangoClient(HTTP_HOST="lespass.tibillet.localhost")


@pytest.fixture(scope="session")
def asset_tlf(tenant):
    """Asset TLF actif pour le tenant lespass.
    / Active TLF asset for lespass tenant."""
    with schema_context(tenant.schema_name):
        from fedow_core.models import Asset
        from AuthBillet.models import Wallet

        # Wallet du lieu (wallet_origin de l'asset)
        wallet_lieu, _ = Wallet.objects.get_or_create(
            origin=tenant,
            name="Wallet lieu billing-test",
        )

        # filter().order_by("name").first() plutot que get_or_create(tenant_origin=,
        # category=, active=) : plusieurs assets TLF actifs peuvent deja exister
        # pour ce tenant (pollution inter-suites sur la DB dev partagee), et
        # get_or_create leverait MultipleObjectsReturned sur ce lookup ambigu.
        # order_by("name") aligne aussi la selection sur celle utilisee en prod
        # par AssetService.obtenir_assets_accessibles (ordre deterministe).
        # / filter().order_by("name").first() rather than get_or_create(...):
        # several active TLF assets may already exist for this tenant
        # (cross-suite pollution on the shared dev DB), and get_or_create would
        # raise MultipleObjectsReturned on this ambiguous lookup. order_by("name")
        # also matches prod's selection via AssetService.obtenir_assets_accessibles
        # (deterministic order).
        asset = Asset.objects.filter(
            tenant_origin=tenant,
            category=Asset.TLF,
            active=True,
        ).order_by("name").first()
        if not asset:
            asset = Asset.objects.create(
                tenant_origin=tenant,
                category=Asset.TLF,
                active=True,
                name="Monnaie locale test billing",
                currency_code="EUR",
                wallet_origin=wallet_lieu,
            )
        return asset


@pytest.fixture(scope="session")
def carte_avec_solde(tenant, asset_tlf):
    """CarteCashless avec wallet ephemere et 1000 centimes de solde TLF.
    / CarteCashless with ephemeral wallet and 1000 cents TLF balance."""
    with schema_context(tenant.schema_name):
        from QrcodeCashless.models import CarteCashless
        from AuthBillet.models import Wallet
        from fedow_core.models import Token

        # Tag unique par session pour eviter les conflits entre runs
        # tag_id et number : max 8 chars dans CarteCashless
        tag_id = uuid.uuid4().hex[:8].upper()
        number = uuid.uuid4().hex[:8].upper()

        wallet_client = Wallet.objects.create(
            origin=tenant,
            name=f"Wallet test billing {tag_id}",
        )

        carte = CarteCashless.objects.create(
            tag_id=tag_id,
            number=number,
            wallet_ephemere=wallet_client,
        )

        token, _ = Token.objects.get_or_create(
            wallet=wallet_client,
            asset=asset_tlf,
            defaults={"value": 1000},  # 10.00 EUR en centimes
        )
        # S'assurer que le solde est bien a 1000 (idempotent)
        if token.value != 1000:
            token.value = 1000
            token.save(update_fields=["value"])

        return carte


@pytest.fixture(scope="session")
def tireuse_billing(tenant):
    """TireuseBec avec Debimetre, Product(FUT), Price(5EUR/L, poids_mesure=True).
    / TireuseBec with Debimetre, Product(FUT), Price(5EUR/L, poids_mesure=True)."""
    with schema_context(tenant.schema_name):
        from controlvanne.models import TireuseBec, Debimetre
        from BaseBillet.models import Product, Price
        from laboutik.models import PointDeVente, Terminal

        # Nettoyer les doublons de runs precedents.
        # PIEGE : le signal post_save de TireuseBec nomme le PointDeVente auto-cree
        # avec instance.nom_tireuse tel quel (pas de prefixe "POS "). Sur la DB dev
        # partagee (pas de rollback entre runs pytest), supprimer la TireuseBec ne
        # supprime pas ce PointDeVente (FK porte par TireuseBec, pas l'inverse) —
        # il reste orphelin et bloque la recreation via la contrainte unique "name".
        # / TRAP: TireuseBec's post_save signal names the auto-created PointDeVente
        # with instance.nom_tireuse as-is (no "POS " prefix). On the shared dev DB
        # (no rollback between pytest runs), deleting the TireuseBec does not delete
        # this PointDeVente (FK is on TireuseBec, not the reverse) — it stays
        # orphaned and blocks recreation via the unique "name" constraint.
        Debimetre.objects.filter(name="Test billing debimetre").delete()
        TireuseBec.objects.filter(nom_tireuse="Tireuse billing test").delete()
        PointDeVente.objects.filter(name="Tireuse billing test").delete()
        # Le meme signal cree aussi un Terminal, qui porte lui aussi une
        # contrainte unique sur "name" et n'est PAS supprime avec la TireuseBec.
        # Sans ce nettoyage, le run suivant echoue en UniqueViolation sur
        # laboutik_terminal_name.
        # / The same signal also creates a Terminal, unique on "name" too, and
        # not deleted with the TireuseBec: the next run fails on UniqueViolation.
        Terminal.objects.filter(name="Tireuse billing test").delete()

        debimetre = Debimetre.objects.create(
            name="Test billing debimetre",
            flow_calibration_factor=6.5,
        )

        produit_fut, _ = Product.objects.get_or_create(
            name="Fut test billing",
            categorie_article="U",
            defaults={"publish": True},
        )

        # S'assurer qu'un Price poids_mesure existe pour ce produit
        if not produit_fut.prices.filter(poids_mesure=True).exists():
            Price.objects.create(
                product=produit_fut,
                name="Litre",
                prix=Decimal("5.00"),
                poids_mesure=True,
            )

        tireuse, _created = TireuseBec.objects.get_or_create(
            nom_tireuse="Tireuse billing test",
            defaults={
                "enabled": True,
                "fut_actif": produit_fut,
                "debimetre": debimetre,
                "reservoir_ml": Decimal("30000.00"),
            },
        )
        # Le signal post_save cree automatiquement un PointDeVente.
        # On le marque hidden pour ne pas polluer les tests menu_ventes.
        # / post_save signal auto-creates a PointDeVente. Mark it hidden.
        if tireuse.point_de_vente:
            PointDeVente.objects.filter(pk=tireuse.point_de_vente_id).update(
                hidden=True
            )

        return tireuse


# ─────────────────────────────────────────────────────────────────────
# TestCalculVolume — tests unitaires
# ─────────────────────────────────────────────────────────────────────


class TestCalculVolume:
    """Tests unitaires de calculer_volume_autorise_ml."""

    def test_01_formule_basique(self):
        """1000 centimes / 5 EUR/L = 200ml? Non: 1000cts / 500cts/L * 1000 = 2000ml."""
        from controlvanne.billing import calculer_volume_autorise_ml

        resultat = calculer_volume_autorise_ml(
            solde_centimes=1000,
            prix_litre_decimal=Decimal("5.00"),
            reservoir_disponible_ml=99999,
        )
        assert resultat == Decimal("2000.00"), f"Attendu 2000.00, obtenu {resultat}"

    def test_02_limite_par_reservoir(self):
        """Le solde permet 2000ml mais le reservoir n'a que 500ml."""
        from controlvanne.billing import calculer_volume_autorise_ml

        resultat = calculer_volume_autorise_ml(
            solde_centimes=1000,
            prix_litre_decimal=Decimal("5.00"),
            reservoir_disponible_ml=500,
        )
        assert resultat == Decimal("500.00"), f"Attendu 500.00, obtenu {resultat}"

    def test_03_solde_zero(self):
        """Solde 0 → volume 0."""
        from controlvanne.billing import calculer_volume_autorise_ml

        resultat = calculer_volume_autorise_ml(
            solde_centimes=0,
            prix_litre_decimal=Decimal("5.00"),
            reservoir_disponible_ml=99999,
        )
        assert resultat == Decimal("0.00"), f"Attendu 0.00, obtenu {resultat}"

    def test_04_prix_zero(self):
        """Prix 0 → protection division par zero → volume 0."""
        from controlvanne.billing import calculer_volume_autorise_ml

        resultat = calculer_volume_autorise_ml(
            solde_centimes=1000,
            prix_litre_decimal=Decimal("0.00"),
            reservoir_disponible_ml=99999,
        )
        assert resultat == Decimal("0.00"), f"Attendu 0.00, obtenu {resultat}"


# ─────────────────────────────────────────────────────────────────────
# TestBillingIntegration — tests via API
# ─────────────────────────────────────────────────────────────────────


class TestBillingIntegration:
    """Tests integration : authorize + pour_end via les endpoints API."""

    def test_05_authorize_avec_solde(
        self,
        billing_client,
        billing_headers,
        tireuse_billing,
        carte_avec_solde,
        tenant,
        asset_tlf,
    ):
        """Authorize retourne authorized=True, solde_centimes et allowed_ml calcule."""
        response = billing_client.post(
            "/controlvanne/api/tireuse/authorize/",
            data={
                "tireuse_uuid": str(tireuse_billing.uuid),
                "uid": carte_avec_solde.tag_id,
            },
            content_type="application/json",
            **billing_headers,
        )
        assert response.status_code == 200, (
            f"Status {response.status_code}: {response.json()}"
        )
        data = response.json()

        assert data["authorized"] is True, f"authorized devrait etre True: {data}"
        assert data["solde_centimes"] == 1000, (
            f"solde attendu 1000, obtenu {data.get('solde_centimes')}"
        )
        # 1000cts / 5EUR/L → 2000ml (reservoir 30L ne limite pas)
        assert data["allowed_ml"] == 2000.0, (
            f"allowed_ml attendu 2000.0, obtenu {data.get('allowed_ml')}"
        )

    def test_06_pour_end_cree_transaction(
        self,
        billing_client,
        billing_headers,
        tireuse_billing,
        carte_avec_solde,
        tenant,
        asset_tlf,
    ):
        """pour_end avec 500ml cree une Transaction, debite le wallet de 250cts."""
        # D'abord authorize pour creer une session ouverte
        resp_auth = billing_client.post(
            "/controlvanne/api/tireuse/authorize/",
            data={
                "tireuse_uuid": str(tireuse_billing.uuid),
                "uid": carte_avec_solde.tag_id,
            },
            content_type="application/json",
            **billing_headers,
        )
        assert resp_auth.status_code == 200
        assert resp_auth.json()["authorized"] is True

        # Ensuite pour_end avec 500ml
        resp_event = billing_client.post(
            "/controlvanne/api/tireuse/event/",
            data={
                "tireuse_uuid": str(tireuse_billing.uuid),
                "uid": carte_avec_solde.tag_id,
                "event_type": "pour_end",
                "volume_ml": "500.00",
            },
            content_type="application/json",
            **billing_headers,
        )
        assert resp_event.status_code == 200, (
            f"Status {resp_event.status_code}: {resp_event.json()}"
        )
        data = resp_event.json()

        # 500ml a 5EUR/L = 0.5L * 5EUR = 2.50 EUR = 250 centimes
        assert data.get("montant_centimes") == 250, (
            f"montant_centimes attendu 250, obtenu {data.get('montant_centimes')}"
        )
        assert "transaction_id" in data, f"transaction_id manquant dans {data}"

        # Verifier que le wallet a ete debite : 1000 - 250 = 750
        with schema_context(tenant.schema_name):
            from fedow_core.services import WalletService

            wallet_client = carte_avec_solde.wallet_ephemere
            solde = WalletService.obtenir_solde(wallet_client, asset_tlf)
            assert solde == 750, f"Solde attendu 750, obtenu {solde}"

    def test_07_authorize_fonds_insuffisants(
        self, billing_client, billing_headers, tireuse_billing, tenant, asset_tlf
    ):
        """Carte avec 0 centimes → authorized=False, message 'Insufficient funds'."""
        with schema_context(tenant.schema_name):
            from QrcodeCashless.models import CarteCashless
            from AuthBillet.models import Wallet
            from fedow_core.models import Token

            tag_id = uuid.uuid4().hex[:8].upper()
            number = uuid.uuid4().hex[:8].upper()

            wallet_zero = Wallet.objects.create(
                origin=tenant,
                name=f"Wallet zero {tag_id}",
            )
            carte_zero = CarteCashless.objects.create(
                tag_id=tag_id,
                number=number,
                wallet_ephemere=wallet_zero,
            )
            # Token a 0 centimes
            Token.objects.create(
                wallet=wallet_zero,
                asset=asset_tlf,
                value=0,
            )

        response = billing_client.post(
            "/controlvanne/api/tireuse/authorize/",
            data={
                "tireuse_uuid": str(tireuse_billing.uuid),
                "uid": tag_id,
            },
            content_type="application/json",
            **billing_headers,
        )
        assert response.status_code == 200, (
            f"Status {response.status_code}: {response.json()}"
        )
        data = response.json()

        assert data["authorized"] is False, f"authorized devrait etre False: {data}"
        assert data["solde_centimes"] == 0, (
            f"solde attendu 0, obtenu {data.get('solde_centimes')}"
        )

        # Nettoyage
        with schema_context(tenant.schema_name):
            carte_zero.delete()
            Token.objects.filter(wallet=wallet_zero).delete()
            wallet_zero.delete()

    def test_08_pour_end_reparti_sur_deux_monnaies_enregistre_le_montant_entier(
        self, billing_client, billing_headers, tireuse_billing, tenant,
    ):
        """Un tirage paye avec deux monnaies enregistre le prix entier du tirage.

        La carte porte 1,00 € de monnaie cadeau (TNF) et 10,00 € de monnaie
        locale (TLF). Un tirage de 500 ml a 5 €/L coute 2,50 € : la cascade prend
        1,00 € en cadeau puis 1,50 € en monnaie locale. Deux lignes, chacune au
        prix unitaire du tirage (250), la part de chaque monnaie dans qty. La
        somme des montants (amount x qty) vaut 250.
        / A pour paid with two currencies records the full pour price: two lines
        at the unit price, shares in qty, amounts summing to 250.

        Les monnaies sont celles que la facturation choisit elle-meme : la
        premiere de chaque categorie parmi les assets accessibles du lieu.
        / The currencies are those billing picks itself.
        """
        with schema_context(tenant.schema_name):
            from AuthBillet.models import Wallet
            from BaseBillet.models import LigneArticle, SaleOrigin
            from QrcodeCashless.models import CarteCashless
            from fedow_core.models import Asset, Token
            from fedow_core.services import AssetService

            assets_accessibles = AssetService.obtenir_assets_accessibles(tenant)
            asset_cadeau = assets_accessibles.filter(category=Asset.TNF).first()
            asset_local = assets_accessibles.filter(category=Asset.TLF).first()
            assert asset_cadeau is not None, "Aucun asset TNF accessible pour ce lieu."
            assert asset_local is not None, "Aucun asset TLF accessible pour ce lieu."

            tag_id = uuid.uuid4().hex[:8].upper()
            wallet_client = Wallet.objects.create(
                origin=tenant,
                name=f"Wallet test tirage reparti {tag_id}",
            )
            carte_deux_monnaies = CarteCashless.objects.create(
                tag_id=tag_id,
                number=uuid.uuid4().hex[:8].upper(),
                wallet_ephemere=wallet_client,
            )
            Token.objects.create(wallet=wallet_client, asset=asset_cadeau, value=100)
            Token.objects.create(wallet=wallet_client, asset=asset_local, value=1000)

        # La base de dev est partagee et ce test n'a pas de rollback : tout ce
        # qu'il cree (carte, wallet, tokens, transactions, lignes de vente) est
        # supprime a la fin, meme en cas d'echec. Ordre impose par les PROTECT :
        # lignes, transactions, tokens, carte, wallet.
        # / Shared dev DB, no rollback: everything created is deleted at the end,
        #   in the order imposed by PROTECT foreign keys.
        try:
            reponse_autorisation = billing_client.post(
                "/controlvanne/api/tireuse/authorize/",
                data={
                    "tireuse_uuid": str(tireuse_billing.uuid),
                    "uid": carte_deux_monnaies.tag_id,
                },
                content_type="application/json",
                **billing_headers,
            )
            assert reponse_autorisation.status_code == 200
            assert reponse_autorisation.json()["authorized"] is True

            reponse_fin = billing_client.post(
                "/controlvanne/api/tireuse/event/",
                data={
                    "tireuse_uuid": str(tireuse_billing.uuid),
                    "uid": carte_deux_monnaies.tag_id,
                    "event_type": "pour_end",
                    "volume_ml": "500.00",
                },
                content_type="application/json",
                **billing_headers,
            )
            assert reponse_fin.status_code == 200, reponse_fin.content.decode()[:400]
            assert reponse_fin.json().get("montant_centimes") == 250

            with schema_context(tenant.schema_name):
                lignes_du_tirage = list(
                    LigneArticle.objects.filter(
                        carte=carte_deux_monnaies,
                        sale_origin=SaleOrigin.TIREUSE,
                    )
                )

                assert len(lignes_du_tirage) == 2, (
                    f"Attendu 2 lignes (une par monnaie), obtenu {len(lignes_du_tirage)}"
                )
                for une_ligne in lignes_du_tirage:
                    assert une_ligne.amount == 250, (
                        f"amount doit etre le prix du tirage (250), obtenu {une_ligne.amount}"
                    )

                somme_des_qty = sum(Decimal(une_ligne.qty) for une_ligne in lignes_du_tirage)
                assert somme_des_qty == Decimal("1"), f"Somme des qty : {somme_des_qty}"

                somme_des_montants = sum(
                    Decimal(une_ligne.amount) * Decimal(une_ligne.qty)
                    for une_ligne in lignes_du_tirage
                )
                assert somme_des_montants == Decimal("250"), (
                    f"Montant enregistre {somme_des_montants}, attendu 250"
                )
        finally:
            with schema_context(tenant.schema_name):
                from fedow_core.models import Transaction

                LigneArticle.objects.filter(carte=carte_deux_monnaies).delete()
                Transaction.objects.filter(card=carte_deux_monnaies).delete()
                Transaction.objects.filter(sender=wallet_client).delete()
                Token.objects.filter(wallet=wallet_client).delete()
                carte_deux_monnaies.delete()
                wallet_client.delete()


# ─────────────────────────────────────────────────────────────────────
# TestSessionOrpheline — session restée ouverte (card_removed perdu)
# / Orphan session — left open (card_removed lost)
# ─────────────────────────────────────────────────────────────────────


class TestSessionOrpheline:
    """
    Une session reste ouverte si card_removed n'arrive jamais (Pi redémarré,
    coupure réseau, page du simulateur rechargée). Le badge suivant sur la
    même tireuse doit la fermer et facturer le dernier volume connu.
    / A session stays open if card_removed never arrives. The next badge on
    the same tap must close it and bill the last known volume.

    Code testé : _cloturer_sessions_orphelines (controlvanne/viewsets.py),
    appelée au début de authorize().
    """

    def test_08_badge_suivant_ferme_et_facture_la_session_orpheline(
        self, billing_client, billing_headers, tireuse_billing, tenant, asset_tlf
    ):
        """
        Scénario :
        1. Carte à 10,00 € badgée → session ouverte.
        2. pour_update à 200 ml, puis plus rien (ni pour_end, ni card_removed).
        3. Nouveau badge sur la même tireuse.
        Attendu : l'ancienne session est fermée avec 200 ml, 200 ml à 5 €/L
        = 1,00 € sont facturés, et le nouveau badge voit un solde de 9,00 €.
        """
        with schema_context(tenant.schema_name):
            from QrcodeCashless.models import CarteCashless
            from AuthBillet.models import Wallet
            from fedow_core.models import Token

            tag_id_de_la_carte = uuid.uuid4().hex[:8].upper()
            wallet_de_la_carte = Wallet.objects.create(
                origin=tenant,
                name=f"Wallet orpheline {tag_id_de_la_carte}",
            )
            CarteCashless.objects.create(
                tag_id=tag_id_de_la_carte,
                number=uuid.uuid4().hex[:8].upper(),
                wallet_ephemere=wallet_de_la_carte,
            )
            Token.objects.create(wallet=wallet_de_la_carte, asset=asset_tlf, value=1000)

        donnees_du_badge = {
            "tireuse_uuid": str(tireuse_billing.uuid),
            "uid": tag_id_de_la_carte,
        }

        # 1. Premier badge / First badge
        reponse_premier_badge = billing_client.post(
            "/controlvanne/api/tireuse/authorize/",
            data=donnees_du_badge,
            content_type="application/json",
            **billing_headers,
        )
        assert reponse_premier_badge.json()["authorized"] is True
        id_session_orpheline = reponse_premier_badge.json()["session_id"]

        # 2. 200 ml versés, puis le Pi « disparaît »
        # / 200 ml poured, then the Pi "disappears"
        reponse_versement = billing_client.post(
            "/controlvanne/api/tireuse/event/",
            data={**donnees_du_badge, "event_type": "pour_update", "volume_ml": "200.00"},
            content_type="application/json",
            **billing_headers,
        )
        assert reponse_versement.status_code == 200

        # 3. Nouveau badge sur la même tireuse / New badge on the same tap
        reponse_second_badge = billing_client.post(
            "/controlvanne/api/tireuse/authorize/",
            data=donnees_du_badge,
            content_type="application/json",
            **billing_headers,
        )
        donnees_second_badge = reponse_second_badge.json()
        assert donnees_second_badge["authorized"] is True

        with schema_context(tenant.schema_name):
            from controlvanne.models import RfidSession
            from fedow_core.services import WalletService

            session_orpheline = RfidSession.objects.get(pk=id_session_orpheline)
            assert session_orpheline.ended_at is not None, "La session orpheline doit être fermée"
            assert session_orpheline.volume_delta_ml == Decimal("200.00")

            # 200 ml à 5 €/L = 100 centimes débités / 100 cents debited
            solde_apres = WalletService.obtenir_solde(wallet_de_la_carte, asset_tlf)
            assert solde_apres == 900, f"Solde attendu 900, obtenu {solde_apres}"

        # Le nouveau badge voit le solde déjà débité / New badge sees the debited balance
        assert donnees_second_badge["solde_centimes"] == 900

        # Nettoyage : fermer la nouvelle session / Cleanup: close the new session
        billing_client.post(
            "/controlvanne/api/tireuse/event/",
            data={**donnees_du_badge, "event_type": "card_removed", "volume_ml": "0.00"},
            content_type="application/json",
            **billing_headers,
        )
