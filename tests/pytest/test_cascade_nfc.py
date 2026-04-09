"""
Tests de la cascade multi-asset NFC — validation Price.non_fiduciaire + cascade NFC.
/ Tests for multi-asset NFC cascade — Price.non_fiduciaire validation + NFC cascade.

LOCALISATION : tests/pytest/test_cascade_nfc.py

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_cascade_nfc.py -v --tb=short
"""

import sys

sys.path.insert(0, "/DjangoFiles")

import django

django.setup()

from decimal import Decimal  # noqa: E402

import pytest  # noqa: E402
from django.core.exceptions import ValidationError  # noqa: E402
from django_tenants.utils import schema_context, tenant_context  # noqa: E402

from fedow_core.models import Asset, Token  # noqa: E402
from fedow_core.services import AssetService  # noqa: E402

from AuthBillet.models import Wallet  # noqa: E402
from BaseBillet.models import LigneArticle, PaymentMethod, Price, Product  # noqa: E402
from QrcodeCashless.models import CarteCashless  # noqa: E402
from laboutik.models import PointDeVente  # noqa: E402
from django.conf import settings  # noqa: E402


# Schema tenant utilisé pour les tests.
# / Tenant schema used for tests.
TENANT_SCHEMA = "lespass"


# --------------------------------------------------------------------------- #
#  Helpers cascade NFC                                                         #
# --------------------------------------------------------------------------- #


def _get_or_create_wallet_lieu(tenant_obj):
    """Récupère le wallet du lieu (via FedowConfig ou en crée un).
    / Gets the venue wallet (via FedowConfig or creates one)."""
    from fedow_connect.models import FedowConfig

    with schema_context(TENANT_SCHEMA):
        fedow_config = FedowConfig.get_solo()
        if fedow_config.wallet:
            return fedow_config.wallet
        wallet_lieu, _ = Wallet.objects.get_or_create(
            origin=tenant_obj,
            defaults={"name": f"[test_cascade] Lieu {tenant_obj.name}"},
        )
        return wallet_lieu


def _get_or_create_asset(tenant_obj, category, wallet_lieu, name=None, currency="EUR"):
    """Récupère ou crée un asset du tenant, en utilisant le même ordre
    que la cascade NFC (obtenir_assets_accessibles → order_by('name')).
    / Gets or creates a tenant asset, using the same ordering
    as the NFC cascade (obtenir_assets_accessibles → order_by('name'))."""
    # Utiliser obtenir_assets_accessibles pour retrouver exactement
    # le même asset que la cascade dans _payer_par_nfc().
    # / Use obtenir_assets_accessibles to find exactly
    # the same asset as the cascade in _payer_par_nfc().
    asset = (
        AssetService.obtenir_assets_accessibles(tenant_obj)
        .filter(
            category=category,
        )
        .first()
    )
    if asset is None:
        nom = name or f"Test {category}"
        asset = AssetService.creer_asset(
            tenant=tenant_obj,
            name=nom,
            category=category,
            currency_code=currency,
            wallet_origin=wallet_lieu,
        )
    return asset


def _set_solde(wallet, asset, montant_centimes):
    """Force le solde d'un wallet/asset à une valeur exacte.
    Met à jour le Token directement (pas de Transaction, juste pour les tests).
    / Forces a wallet/asset balance to an exact value.
    Updates Token directly (no Transaction, test-only)."""
    token, _ = Token.objects.get_or_create(
        wallet=wallet,
        asset=asset,
        defaults={"value": 0},
    )
    token.value = montant_centimes
    token.save(update_fields=["value"])


def _reset_tous_les_soldes_fiduciaires(wallet):
    """Remet à zéro TOUS les tokens fiduciaires (TNF, TLF, FED) du wallet.
    Nécessaire avant les tests de paiement complémentaire pour éviter que
    les soldes résiduels des autres tests ne faussent le recalcul de cascade.
    / Resets ALL fiduciary tokens (TNF, TLF, FED) of the wallet to zero.
    Needed before complement payment tests to prevent residual balances from
    other tests skewing the cascade recalculation."""
    CATEGORIES_FIDUCIAIRES = [Asset.TNF, Asset.TLF, Asset.FED]
    Token.objects.filter(
        wallet=wallet,
        asset__category__in=CATEGORIES_FIDUCIAIRES,
    ).update(value=0)


def _obtenir_wallet_pour_carte(carte, tenant_obj):
    """Récupère ou crée un wallet pour une carte de test.
    Même logique que _obtenir_ou_creer_wallet() dans views.py,
    mais appelé hors requête HTTP pour le setup de test.
    / Gets or creates a wallet for a test card.
    Same logic as _obtenir_ou_creer_wallet() in views.py,
    but called outside HTTP request for test setup."""
    if carte.user and carte.user.wallet:
        return carte.user.wallet
    if carte.wallet_ephemere:
        return carte.wallet_ephemere
    # Créer un wallet éphémère
    # / Create an ephemeral wallet
    wallet = Wallet.objects.create(
        name=f"[test_cascade] Éphémère {carte.tag_id}",
    )
    carte.wallet_ephemere = wallet
    carte.save(update_fields=["wallet_ephemere"])
    return wallet


def _get_premier_produit_vente_et_prix(point_de_vente):
    """Récupère le 1er produit VENTE du PV avec son 1er prix EUR.
    / Gets the first SALE product of the POS with its first EUR price."""
    produit = (
        point_de_vente.products.filter(methode_caisse=Product.VENTE)
        .order_by("poids")
        .first()
    )
    if produit is None:
        return None, None
    prix = (
        Price.objects.filter(product=produit, publish=True, asset__isnull=True)
        .order_by("order")
        .first()
    )
    return produit, prix


def _make_post_data(point_de_vente, produit, tag_id, quantite=1):
    """Construit les données POST pour un paiement NFC.
    / Builds POST data for an NFC payment."""
    prix = (
        Price.objects.filter(product=produit, publish=True, asset__isnull=True)
        .order_by("order")
        .first()
    )
    prix_centimes = int(round(prix.prix * 100))
    return {
        "uuid_pv": str(point_de_vente.uuid),
        "moyen_paiement": "nfc",
        "total": str(prix_centimes * quantite),
        "given_sum": "",
        "tag_id": tag_id,
        f"repid-{produit.uuid}": str(quantite),
    }


@pytest.mark.django_db
def test_65_non_fiduciaire_true_sans_asset_leve_validation_error(tenant):
    """non_fiduciaire=True sans asset → ValidationError."""
    from BaseBillet.models import Price, Product

    with tenant_context(tenant):
        produit = Product.objects.filter(methode_caisse=Product.VENTE).first()
        if not produit:
            pytest.skip("Pas de produit VT en base")
        prix = Price(
            product=produit,
            name="Test sans asset",
            prix=Decimal("1.00"),
            non_fiduciaire=True,
            asset=None,
        )
        with pytest.raises(ValidationError) as exc_info:
            prix.clean()
        assert "asset" in str(exc_info.value)


@pytest.mark.django_db
def test_66_non_fiduciaire_true_avec_asset_fiduciaire_leve_validation_error(tenant):
    """non_fiduciaire=True avec asset TLF → ValidationError."""
    from BaseBillet.models import Price, Product
    from fedow_core.models import Asset

    with tenant_context(tenant):
        produit = Product.objects.filter(methode_caisse=Product.VENTE).first()
        if not produit:
            pytest.skip("Pas de produit VT en base")
        asset_tlf = Asset.objects.filter(
            tenant_origin=tenant, category=Asset.TLF, active=True
        ).first()
        if not asset_tlf:
            pytest.skip("Pas d'asset TLF en base")

        prix = Price(
            product=produit,
            name="Test TLF interdit",
            prix=Decimal("1.00"),
            non_fiduciaire=True,
            asset=asset_tlf,
        )
        with pytest.raises(ValidationError):
            prix.clean()


@pytest.mark.django_db
def test_67_non_fiduciaire_true_avec_asset_tim_ok(tenant):
    """non_fiduciaire=True avec asset TIM → OK."""
    from BaseBillet.models import Price, Product
    from fedow_core.models import Asset

    with tenant_context(tenant):
        produit = Product.objects.filter(methode_caisse=Product.VENTE).first()
        if not produit:
            pytest.skip("Pas de produit VT en base")
        asset_tim = Asset.objects.filter(
            tenant_origin=tenant, category=Asset.TIM, active=True
        ).first()
        if not asset_tim:
            pytest.skip("Pas d'asset TIM en base")

        prix = Price(
            product=produit,
            name="Test TIM ok",
            prix=Decimal("1.00"),
            non_fiduciaire=True,
            asset=asset_tim,
        )
        prix.clean()  # Ne doit PAS lever d'exception


@pytest.mark.django_db
def test_68_non_fiduciaire_false_avec_asset_tim_ignore(tenant):
    """non_fiduciaire=False avec asset=TIM → pas d'erreur, asset ignoré."""
    from BaseBillet.models import Price, Product
    from fedow_core.models import Asset

    with tenant_context(tenant):
        produit = Product.objects.filter(methode_caisse=Product.VENTE).first()
        if not produit:
            pytest.skip("Pas de produit VT en base")
        asset_tim = Asset.objects.filter(
            tenant_origin=tenant, category=Asset.TIM, active=True
        ).first()
        if not asset_tim:
            pytest.skip("Pas d'asset TIM en base")

        prix = Price(
            product=produit,
            name="Test ignore",
            prix=Decimal("1.00"),
            non_fiduciaire=False,
            asset=asset_tim,
        )
        prix.clean()  # Ne doit PAS lever d'exception


# === Section B : qty partielle et amounts ===


@pytest.mark.django_db
def test_09_split_2_assets_somme_qty_exacte(tenant):
    """
    Split sur 2 assets : la somme des qty partielles == qty_totale exactement.
    / Split on 2 assets: sum of partial qty == total qty exactly.
    """
    from laboutik.views import _calculer_qty_partielles

    lignes = [
        {"amount_centimes": 100},
        {"amount_centimes": 300},
    ]
    prix_unitaire_centimes = 400
    qty_totale = Decimal("1")

    resultats = _calculer_qty_partielles(lignes, prix_unitaire_centimes, qty_totale)

    somme_qty = sum(r["qty"] for r in resultats)
    assert somme_qty == Decimal("1.000000")
    assert resultats[0]["qty"] == Decimal("0.250000")
    assert resultats[1]["qty"] == Decimal("0.750000")


@pytest.mark.django_db
def test_10_split_3_assets_derniere_prend_reste(tenant):
    """
    Split 3 assets : pas de .333333 infini. Dernière = reste.
    / Split 3 assets: no infinite .333333. Last = remainder.
    """
    from laboutik.views import _calculer_qty_partielles

    lignes = [
        {"amount_centimes": 100},
        {"amount_centimes": 100},
        {"amount_centimes": 100},
    ]
    prix_unitaire_centimes = 300
    qty_totale = Decimal("1")

    resultats = _calculer_qty_partielles(lignes, prix_unitaire_centimes, qty_totale)

    somme_qty = sum(r["qty"] for r in resultats)
    assert somme_qty == Decimal("1.000000")
    assert resultats[0]["qty"] == Decimal("0.333333")
    assert resultats[1]["qty"] == Decimal("0.333333")
    assert resultats[2]["qty"] == Decimal("0.333334")


@pytest.mark.django_db
def test_11_qty_superieure_a_1(tenant):
    """
    qty=3 (3 bières à 4€) splitté sur 2 assets.
    / qty=3 (3 beers at 4€) split on 2 assets.
    """
    from laboutik.views import _calculer_qty_partielles

    lignes = [
        {"amount_centimes": 400},
        {"amount_centimes": 800},
    ]
    prix_unitaire_centimes = 400
    qty_totale = Decimal("3")

    resultats = _calculer_qty_partielles(lignes, prix_unitaire_centimes, qty_totale)

    somme_qty = sum(r["qty"] for r in resultats)
    assert somme_qty == Decimal("3.000000")
    somme_amount = sum(lig["amount_centimes"] for lig in lignes)
    assert somme_amount == 1200


@pytest.mark.django_db
def test_12_article_1_centime(tenant):
    """
    Article à 1 centime splitté → pas de qty=0 ni amount=0.
    / 1-cent article split → no qty=0 or amount=0.
    """
    from laboutik.views import _calculer_qty_partielles

    lignes = [{"amount_centimes": 1}]
    prix_unitaire_centimes = 1
    qty_totale = Decimal("1")

    resultats = _calculer_qty_partielles(lignes, prix_unitaire_centimes, qty_totale)

    assert resultats[0]["qty"] == Decimal("1")
    assert resultats[0]["amount_centimes"] == 1


# ======================================================================== #
#  Section A : Cascade fiduciaire — cas normaux (tests via HTTP POST)      #
#  Section A: Fiduciary cascade — normal cases (tests via HTTP POST)       #
# ======================================================================== #

# Les tests utilisent le tag_id DEMO_TAGID_CLIENT1 (52BE6543 par défaut)
# créé par create_test_pos_data, qui a un wallet garni en TNF/TLF/FED.
# On force les soldes avec _set_solde() avant chaque test.
# / Tests use DEMO_TAGID_CLIENT1 tag (52BE6543 default) created by
# create_test_pos_data, with a wallet topped up in TNF/TLF/FED.
# We force balances with _set_solde() before each test.

TAG_ID_CASCADE = getattr(settings, "DEMO_TAGID_CLIENT1", "52BE6543")


@pytest.mark.django_db
def test_01_cascade_tnf_seul_suffit(tenant, admin_client):
    """TNF suffit pour tout → 1 LigneArticle, asset=TNF, payment_method=LG.
    / TNF sufficient for all → 1 LigneArticle, asset=TNF, payment_method=LG."""
    with schema_context(TENANT_SCHEMA):
        # Récupérer les objets de test
        # / Get test objects
        carte = CarteCashless.objects.get(tag_id=TAG_ID_CASCADE)
        wallet_client = _obtenir_wallet_pour_carte(carte, tenant)

        wallet_lieu = _get_or_create_wallet_lieu(tenant)
        asset_tnf = _get_or_create_asset(tenant, Asset.TNF, wallet_lieu, "Cadeau")
        asset_tlf = _get_or_create_asset(
            tenant, Asset.TLF, wallet_lieu, "Monnaie locale"
        )

        premier_pv = (
            PointDeVente.objects.filter(hidden=False).order_by("poid_liste").first()
        )
        produit, prix = _get_premier_produit_vente_et_prix(premier_pv)
        if not produit or not prix:
            pytest.skip("Pas de produit/prix de test")
        prix_centimes = int(round(prix.prix * 100))

        # Setup : TNF=1000 (assez), TLF=0
        # / Setup: TNF=1000 (enough), TLF=0
        _set_solde(wallet_client, asset_tnf, 1000)
        _set_solde(wallet_client, asset_tlf, 0)

        post_data = _make_post_data(premier_pv, produit, TAG_ID_CASCADE)
        response = admin_client.post("/laboutik/paiement/payer/", data=post_data)
        assert response.status_code == 200, response.content.decode()[:300]

        contenu = response.content.decode()
        assert "Paiement" in contenu or "Payment successful" in contenu, (
            f"Attendu succès, obtenu : {contenu[:300]}"
        )

        # Vérifier : 1 nouvelle LigneArticle avec asset=TNF
        # / Verify: 1 new LigneArticle with asset=TNF
        nouvelles_lignes = LigneArticle.objects.filter(
            carte=carte,
        ).order_by("-datetime")[:5]

        lignes_de_ce_paiement = [
            la
            for la in nouvelles_lignes
            if la.amount == prix_centimes and la.asset == asset_tnf.pk
        ]
        assert len(lignes_de_ce_paiement) >= 1, (
            f"Attendu au moins 1 LigneArticle TNF amount={prix_centimes}, "
            f"trouvé : {[(la.amount, la.asset, la.payment_method) for la in nouvelles_lignes[:5]]}"
        )

        ligne = lignes_de_ce_paiement[0]
        assert ligne.payment_method == PaymentMethod.LOCAL_GIFT


@pytest.mark.django_db
def test_02_cascade_tnf_plus_tlf(tenant, admin_client):
    """TNF insuffisant → split TNF + TLF.
    / TNF insufficient → split TNF + TLF."""
    with schema_context(TENANT_SCHEMA):
        carte = CarteCashless.objects.get(tag_id=TAG_ID_CASCADE)
        wallet_client = _obtenir_wallet_pour_carte(carte, tenant)

        wallet_lieu = _get_or_create_wallet_lieu(tenant)
        asset_tnf = _get_or_create_asset(tenant, Asset.TNF, wallet_lieu, "Cadeau")
        asset_tlf = _get_or_create_asset(
            tenant, Asset.TLF, wallet_lieu, "Monnaie locale"
        )

        premier_pv = (
            PointDeVente.objects.filter(hidden=False).order_by("poid_liste").first()
        )
        produit, prix = _get_premier_produit_vente_et_prix(premier_pv)
        if not produit or not prix:
            pytest.skip("Pas de produit/prix de test")
        prix_centimes = int(round(prix.prix * 100))

        # Setup : TNF=100 (1€), TLF=500 (5€) → Bière à 4€ doit splitter
        # / Setup: TNF=100 (1€), TLF=500 (5€) → Beer at 4€ should split
        _set_solde(wallet_client, asset_tnf, 100)
        _set_solde(wallet_client, asset_tlf, 500)

        # Générer un uuid_transaction unique pour repérer les lignes créées
        # / Generate unique uuid_transaction to identify created lines

        post_data = _make_post_data(premier_pv, produit, TAG_ID_CASCADE)
        response = admin_client.post("/laboutik/paiement/payer/", data=post_data)
        assert response.status_code == 200, response.content.decode()[:300]

        contenu = response.content.decode()
        assert "Paiement" in contenu or "Payment successful" in contenu, (
            f"Attendu succès, obtenu : {contenu[:300]}"
        )

        # Trouver les lignes les plus récentes pour cette carte
        # / Find most recent lines for this card
        derniers_lignes = list(
            LigneArticle.objects.filter(carte=carte).order_by("-datetime")[:10]
        )

        # Regrouper par uuid_transaction pour trouver celles de ce paiement
        # (les 2 lignes les plus récentes devraient avoir le même uuid_transaction)
        # / Group by uuid_transaction to find those from this payment
        if len(derniers_lignes) >= 2:
            uuid_tx = derniers_lignes[0].uuid_transaction
            lignes_paiement = [
                la for la in derniers_lignes if la.uuid_transaction == uuid_tx
            ]

            # Vérifier qu'il y a 2 lignes (1 TNF + 1 TLF)
            # / Verify there are 2 lines (1 TNF + 1 TLF)
            assert len(lignes_paiement) == 2, (
                f"Attendu 2 lignes (TNF+TLF), trouvé {len(lignes_paiement)} : "
                f"{[(la.amount, la.asset, la.payment_method) for la in lignes_paiement]}"
            )

            amounts = sorted([la.amount for la in lignes_paiement])
            assert amounts == [100, prix_centimes - 100], (
                f"Attendu amounts [100, {prix_centimes - 100}], obtenu {amounts}"
            )

            # La somme des qty doit faire 1.000000
            # / Sum of qty must be 1.000000
            somme_qty = sum(la.qty for la in lignes_paiement)
            assert somme_qty == Decimal("1.000000"), (
                f"Attendu sum(qty)=1.000000, obtenu {somme_qty}"
            )


@pytest.mark.django_db
def test_04_cascade_tlf_seul(tenant, admin_client):
    """Pas de TNF → TLF seul.
    / No TNF → TLF only."""
    with schema_context(TENANT_SCHEMA):
        carte = CarteCashless.objects.get(tag_id=TAG_ID_CASCADE)
        wallet_client = _obtenir_wallet_pour_carte(carte, tenant)

        wallet_lieu = _get_or_create_wallet_lieu(tenant)
        asset_tnf = _get_or_create_asset(tenant, Asset.TNF, wallet_lieu, "Cadeau")
        asset_tlf = _get_or_create_asset(
            tenant, Asset.TLF, wallet_lieu, "Monnaie locale"
        )

        premier_pv = (
            PointDeVente.objects.filter(hidden=False).order_by("poid_liste").first()
        )
        produit, prix = _get_premier_produit_vente_et_prix(premier_pv)
        if not produit or not prix:
            pytest.skip("Pas de produit/prix de test")
        prix_centimes = int(round(prix.prix * 100))

        # Setup : TNF=0, TLF=500 → tout sur TLF
        # / Setup: TNF=0, TLF=500 → all on TLF
        _set_solde(wallet_client, asset_tnf, 0)
        _set_solde(wallet_client, asset_tlf, 500)

        post_data = _make_post_data(premier_pv, produit, TAG_ID_CASCADE)
        response = admin_client.post("/laboutik/paiement/payer/", data=post_data)
        assert response.status_code == 200, response.content.decode()[:300]

        contenu = response.content.decode()
        assert "Paiement" in contenu or "Payment successful" in contenu, (
            f"Attendu succès, obtenu : {contenu[:300]}"
        )

        # Vérifier : 1 LigneArticle avec asset=TLF
        # / Verify: 1 LigneArticle with asset=TLF
        derniere_ligne = (
            LigneArticle.objects.filter(carte=carte).order_by("-datetime").first()
        )
        assert derniere_ligne is not None
        assert derniere_ligne.asset == asset_tlf.pk, (
            f"Attendu asset TLF ({asset_tlf.pk}), obtenu {derniere_ligne.asset}"
        )
        assert derniere_ligne.amount == prix_centimes
        assert derniere_ligne.payment_method == PaymentMethod.LOCAL_EURO


@pytest.mark.django_db
def test_08_aucun_asset_fiduciaire_actif(tenant, admin_client):
    """Aucun asset fiduciaire actif → rejet "Monnaie locale non configurée".
    / No active fiduciary asset → rejection "Monnaie locale non configurée".

    Ce test est complexe car il faudrait désactiver tous les assets du tenant.
    Pour l'instant, on laisse en pass.
    / This test is complex because it would require deactivating all tenant assets.
    For now, left as pass.
    """
    pass


# ======================================================================== #
#  Section E : Complémentaire espèces/CB                                   #
#  Section E: Cash/CC complement                                            #
# ======================================================================== #

TAG_ID_CASCADE_CLIENT2 = getattr(settings, "DEMO_TAGID_CLIENT2", "C63A0A4C")


@pytest.mark.django_db
def test_26_cascade_insuffisante_affiche_complement(tenant, admin_client):
    """Cascade insuffisante → écran complémentaire (status 200, template complement).
    / Insufficient cascade → complement screen (status 200, complement template)."""
    with schema_context(TENANT_SCHEMA):
        carte = CarteCashless.objects.get(tag_id=TAG_ID_CASCADE)
        wallet_client = _obtenir_wallet_pour_carte(carte, tenant)

        wallet_lieu = _get_or_create_wallet_lieu(tenant)
        asset_tnf = _get_or_create_asset(tenant, Asset.TNF, wallet_lieu, "Cadeau")
        asset_tlf = _get_or_create_asset(
            tenant, Asset.TLF, wallet_lieu, "Monnaie locale"
        )

        premier_pv = (
            PointDeVente.objects.filter(hidden=False).order_by("poid_liste").first()
        )
        produit, prix = _get_premier_produit_vente_et_prix(premier_pv)
        if not produit or not prix:
            pytest.skip("Pas de produit/prix de test")

        # Setup : TNF=50 (0.50€), TLF=50 (0.50€), total=1€ insuffisant pour 4€
        # / Setup: TNF=50 (0.50€), TLF=50 (0.50€), total=1€ not enough for 4€
        _set_solde(wallet_client, asset_tnf, 50)
        _set_solde(wallet_client, asset_tlf, 50)

        post_data = _make_post_data(premier_pv, produit, TAG_ID_CASCADE)
        response = admin_client.post("/laboutik/paiement/payer/", data=post_data)
        assert response.status_code == 200, response.content.decode()[:300]

        contenu = response.content.decode()

        # Doit contenir le template de complément, PAS l'ancien "Fonds insuffisants"
        # / Must contain the complement template, NOT the old "Insufficient funds"
        assert "complement-paiement" in contenu, (
            f"Attendu 'complement-paiement' dans la réponse, obtenu : {contenu[:500]}"
        )
        assert "Reste" in contenu or "payer" in contenu, (
            f"Attendu mention du reste à payer, obtenu : {contenu[:500]}"
        )

        # Doit contenir le tag_id de la carte
        # / Must contain card tag_id
        assert TAG_ID_CASCADE in contenu, f"Attendu {TAG_ID_CASCADE} dans la réponse"


@pytest.mark.django_db
def test_27_complement_especes(tenant, admin_client):
    """Complément espèces → lignes NFC + espèces, même uuid_transaction.
    / Cash complement → NFC lines + cash lines, same uuid_transaction."""
    with schema_context(TENANT_SCHEMA):
        carte = CarteCashless.objects.get(tag_id=TAG_ID_CASCADE)
        wallet_client = _obtenir_wallet_pour_carte(carte, tenant)

        wallet_lieu = _get_or_create_wallet_lieu(tenant)
        asset_tnf = _get_or_create_asset(tenant, Asset.TNF, wallet_lieu, "Cadeau")
        asset_tlf = _get_or_create_asset(
            tenant, Asset.TLF, wallet_lieu, "Monnaie locale"
        )

        premier_pv = (
            PointDeVente.objects.filter(hidden=False).order_by("poid_liste").first()
        )
        produit, prix = _get_premier_produit_vente_et_prix(premier_pv)
        if not produit or not prix:
            pytest.skip("Pas de produit/prix de test")
        prix_centimes = int(round(prix.prix * 100))

        # Reset tous les tokens fiduciaires pour isoler ce test des précédents.
        # / Reset all fiduciary tokens to isolate this test from previous ones.
        _reset_tous_les_soldes_fiduciaires(wallet_client)

        # Setup : TNF=100 (1€), TLF=100 (1€) → total NFC = 2€ < prix article
        # Le reste sera en espèces (prix article doit être > 200 centimes)
        # / Setup: TNF=100 (1€), TLF=100 (1€) → NFC total = 2€ < article price
        # Remainder will be cash (article price must be > 200 centimes)
        _set_solde(wallet_client, asset_tnf, 100)
        _set_solde(wallet_client, asset_tlf, 100)

        # POST le complément espèces directement
        # / POST the cash complement directly
        post_data = _make_post_data(premier_pv, produit, TAG_ID_CASCADE)
        post_data["tag_id_carte1"] = TAG_ID_CASCADE
        post_data["moyen_complement"] = "espece"
        post_data["cascade_carte1"] = "[]"
        post_data["total_nfc_carte1"] = "200"

        response = admin_client.post(
            "/laboutik/paiement/payer_complementaire/", data=post_data
        )
        assert response.status_code == 200, response.content.decode()[:500]

        contenu = response.content.decode()
        # Doit contenir l'écran de succès
        # / Must contain the success screen
        assert "paiement-succes" in contenu or "Paiement" in contenu, (
            f"Attendu succès, obtenu : {contenu[:500]}"
        )

        # Vérifier les lignes créées
        # / Verify created lines
        nouvelles_lignes = list(
            LigneArticle.objects.filter(carte=carte).order_by("-datetime")[:10]
        )

        # Trouver les lignes de ce paiement (les plus récentes avec même uuid_transaction)
        # / Find this payment's lines (most recent with same uuid_transaction)
        if nouvelles_lignes:
            uuid_tx = nouvelles_lignes[0].uuid_transaction
            lignes_paiement = [
                la for la in nouvelles_lignes if la.uuid_transaction == uuid_tx
            ]

            # Vérifier qu'il y a au moins 2 lignes (NFC + espèces)
            # / Verify at least 2 lines (NFC + cash)
            assert len(lignes_paiement) >= 2, (
                f"Attendu ≥2 lignes (NFC+espèces), trouvé {len(lignes_paiement)} : "
                f"{[(la.amount, la.payment_method, la.asset) for la in lignes_paiement]}"
            )

            # Vérifier qu'il y a au moins 1 ligne NFC (LG ou LE) et 1 ligne espèces (CA)
            # / Verify at least 1 NFC line (LG or LE) and 1 cash line (CA)
            lignes_nfc = [
                la
                for la in lignes_paiement
                if la.payment_method
                in (
                    PaymentMethod.LOCAL_GIFT,
                    PaymentMethod.LOCAL_EURO,
                )
            ]
            lignes_especes = [
                la for la in lignes_paiement if la.payment_method == PaymentMethod.CASH
            ]
            assert len(lignes_nfc) >= 1, (
                f"Attendu ≥1 ligne NFC, trouvé {len(lignes_nfc)}"
            )
            assert len(lignes_especes) >= 1, (
                f"Attendu ≥1 ligne espèces, trouvé {len(lignes_especes)}"
            )

            # Vérifier que le total des montants = prix article
            # / Verify total amounts = article price
            somme_amounts = sum(la.amount for la in lignes_paiement)
            assert somme_amounts == prix_centimes, (
                f"Attendu somme={prix_centimes}, obtenu {somme_amounts}"
            )

            # Les lignes espèces n'ont pas d'asset
            # / Cash lines have no asset
            for ligne_esp in lignes_especes:
                assert ligne_esp.asset is None, (
                    f"Ligne espèces ne doit pas avoir d'asset, trouvé {ligne_esp.asset}"
                )


@pytest.mark.django_db
def test_28_complement_carte_bancaire(tenant, admin_client):
    """Complément CB → lignes NFC + CB, même uuid_transaction.
    / CC complement → NFC lines + CC lines, same uuid_transaction."""
    with schema_context(TENANT_SCHEMA):
        carte = CarteCashless.objects.get(tag_id=TAG_ID_CASCADE)
        wallet_client = _obtenir_wallet_pour_carte(carte, tenant)

        wallet_lieu = _get_or_create_wallet_lieu(tenant)
        asset_tnf = _get_or_create_asset(tenant, Asset.TNF, wallet_lieu, "Cadeau")
        asset_tlf = _get_or_create_asset(
            tenant, Asset.TLF, wallet_lieu, "Monnaie locale"
        )

        premier_pv = (
            PointDeVente.objects.filter(hidden=False).order_by("poid_liste").first()
        )
        produit, prix = _get_premier_produit_vente_et_prix(premier_pv)
        if not produit or not prix:
            pytest.skip("Pas de produit/prix de test")

        # Reset tous les tokens fiduciaires pour isoler ce test des précédents.
        # / Reset all fiduciary tokens to isolate this test from previous ones.
        _reset_tous_les_soldes_fiduciaires(wallet_client)

        _set_solde(wallet_client, asset_tnf, 100)
        _set_solde(wallet_client, asset_tlf, 100)

        post_data = _make_post_data(premier_pv, produit, TAG_ID_CASCADE)
        post_data["tag_id_carte1"] = TAG_ID_CASCADE
        post_data["moyen_complement"] = "carte_bancaire"
        post_data["cascade_carte1"] = "[]"
        post_data["total_nfc_carte1"] = "200"

        response = admin_client.post(
            "/laboutik/paiement/payer_complementaire/", data=post_data
        )
        assert response.status_code == 200, response.content.decode()[:500]

        contenu = response.content.decode()
        assert "paiement-succes" in contenu or "Paiement" in contenu, (
            f"Attendu succès, obtenu : {contenu[:500]}"
        )

        # Vérifier la présence d'une ligne CB (CC)
        # / Verify presence of a CC line
        nouvelles_lignes = list(
            LigneArticle.objects.filter(carte=carte).order_by("-datetime")[:10]
        )
        if nouvelles_lignes:
            uuid_tx = nouvelles_lignes[0].uuid_transaction
            lignes_paiement = [
                la for la in nouvelles_lignes if la.uuid_transaction == uuid_tx
            ]
            lignes_cb = [
                la for la in lignes_paiement if la.payment_method == PaymentMethod.CC
            ]
            assert len(lignes_cb) >= 1, f"Attendu ≥1 ligne CB, trouvé {len(lignes_cb)}"


# ======================================================================== #
#  Section F : Complémentaire 2ème carte NFC                                #
#  Section F: 2nd NFC card complement                                       #
# ======================================================================== #


@pytest.mark.django_db
def test_36_meme_carte_rejet(tenant, admin_client):
    """2ème carte = même que la 1ère → rejet.
    / 2nd card = same as 1st → rejection."""
    with schema_context(TENANT_SCHEMA):
        carte = CarteCashless.objects.get(tag_id=TAG_ID_CASCADE)
        wallet_client = _obtenir_wallet_pour_carte(carte, tenant)

        wallet_lieu = _get_or_create_wallet_lieu(tenant)
        asset_tnf = _get_or_create_asset(tenant, Asset.TNF, wallet_lieu, "Cadeau")
        asset_tlf = _get_or_create_asset(
            tenant, Asset.TLF, wallet_lieu, "Monnaie locale"
        )

        premier_pv = (
            PointDeVente.objects.filter(hidden=False).order_by("poid_liste").first()
        )
        produit, prix = _get_premier_produit_vente_et_prix(premier_pv)
        if not produit or not prix:
            pytest.skip("Pas de produit/prix de test")

        # Reset tous les tokens fiduciaires pour isoler ce test des précédents.
        # / Reset all fiduciary tokens to isolate this test from previous ones.
        _reset_tous_les_soldes_fiduciaires(wallet_client)

        _set_solde(wallet_client, asset_tnf, 100)
        _set_solde(wallet_client, asset_tlf, 100)

        post_data = _make_post_data(premier_pv, produit, TAG_ID_CASCADE)
        post_data["tag_id_carte1"] = TAG_ID_CASCADE
        post_data["tag_id"] = TAG_ID_CASCADE  # Même carte !
        post_data["moyen_complement"] = "nfc"
        post_data["cascade_carte1"] = "[]"
        post_data["total_nfc_carte1"] = "200"

        response = admin_client.post(
            "/laboutik/paiement/payer_complementaire/", data=post_data
        )
        assert response.status_code == 200, response.content.decode()[:500]

        contenu = response.content.decode()
        # Doit contenir un message d'erreur (carte identique)
        # / Must contain error message (same card)
        assert (
            "même" in contenu.lower()
            or "same" in contenu.lower()
            or "warning" in contenu
        ), f"Attendu rejet carte identique, obtenu : {contenu[:500]}"


# ======================================================================== #
#  Section G : Rapports + impression enrichis                               #
#  Section G: Enriched reports + printing                                   #
# ======================================================================== #


@pytest.mark.django_db
def test_59_cashless_detail_par_asset(tenant, admin_client):
    """Après un paiement cascade TNF+TLF, cashless_detail contient le détail par asset.
    / After a TNF+TLF cascade payment, cashless_detail contains per-asset breakdown."""
    from django.utils import timezone as tz

    with schema_context(TENANT_SCHEMA):
        carte = CarteCashless.objects.get(tag_id=TAG_ID_CASCADE)
        wallet_client = _obtenir_wallet_pour_carte(carte, tenant)

        wallet_lieu = _get_or_create_wallet_lieu(tenant)
        asset_tnf = _get_or_create_asset(tenant, Asset.TNF, wallet_lieu, "Cadeau")
        asset_tlf = _get_or_create_asset(
            tenant, Asset.TLF, wallet_lieu, "Monnaie locale"
        )

        premier_pv = (
            PointDeVente.objects.filter(hidden=False).order_by("poid_liste").first()
        )
        produit, prix = _get_premier_produit_vente_et_prix(premier_pv)
        if not produit or not prix:
            pytest.skip("Pas de produit/prix de test")

        # Setup : TNF=100 (partiel), TLF=500 (complète le reste)
        # / Setup: TNF=100 (partial), TLF=500 (covers the rest)
        _set_solde(wallet_client, asset_tnf, 100)
        _set_solde(wallet_client, asset_tlf, 500)

        debut = tz.now()
        post_data = _make_post_data(premier_pv, produit, TAG_ID_CASCADE)
        response = admin_client.post("/laboutik/paiement/payer/", data=post_data)
        assert response.status_code == 200, response.content.decode()[:300]
        fin = tz.now()

        # Vérifier que 2 LigneArticle ont été créées (cascade TNF + TLF)
        # / Verify that 2 LigneArticle were created (TNF + TLF cascade)
        derniers_lignes = list(
            LigneArticle.objects.filter(
                carte=carte,
                datetime__gte=debut,
            ).order_by("-datetime")[:10]
        )
        assert len(derniers_lignes) >= 2, (
            f"Attendu au moins 2 LigneArticle cascade, trouvé {len(derniers_lignes)}"
        )

        # Trouver le uuid_transaction commun
        # / Find the common uuid_transaction
        uuid_tx = derniers_lignes[0].uuid_transaction
        assert uuid_tx is not None, "uuid_transaction doit être non null après cascade"

        # Instancier RapportComptableService sur la periode du paiement
        # / Instantiate RapportComptableService on the payment period
        from laboutik.reports import RapportComptableService

        service = RapportComptableService(
            point_de_vente=premier_pv,
            datetime_debut=debut,
            datetime_fin=fin,
        )
        totaux = service.calculer_totaux_par_moyen()

        # cashless_detail doit avoir au moins 1 entrée (TNF ou TLF ou les 2)
        # / cashless_detail must have at least 1 entry (TNF or TLF or both)
        cashless_detail = totaux.get("cashless_detail", [])
        assert len(cashless_detail) >= 1, (
            f"Attendu au moins 1 entrée dans cashless_detail, "
            f"obtenu {cashless_detail}. totaux={totaux}"
        )

        # Vérifier la structure de chaque entrée : nom + montant
        # / Verify structure of each entry: name + amount
        for entry in cashless_detail:
            assert "nom" in entry, f"Clé 'nom' absente dans {entry}"
            assert "montant" in entry, f"Clé 'montant' absente dans {entry}"
            assert isinstance(entry["montant"], int), (
                f"montant doit être int (centimes), obtenu {type(entry['montant'])}"
            )

        # La somme des montants dans cashless_detail doit égaler total_cashless
        # / Sum of amounts in cashless_detail must equal total_cashless
        somme_detail = sum(e["montant"] for e in cashless_detail)
        assert somme_detail == totaux["cashless"], (
            f"Somme cashless_detail {somme_detail} != total cashless {totaux['cashless']}"
        )
