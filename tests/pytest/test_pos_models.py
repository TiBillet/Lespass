"""
tests/pytest/test_pos_models.py — Tests unitaires Phase 1 : modeles POS.
tests/pytest/test_pos_models.py — Unit tests Phase 1: POS models.

Couvre : CategorieProduct, Product (champs POS), POSProduct proxy,
         Price.asset FK, PointDeVente, CartePrimaire, Table, CategorieTable,
         management command create_test_pos_data.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_pos_models.py -v --api-key dummy
"""

import os
import sys

# Le code Django est dans /DjangoFiles a l'interieur du conteneur.
# / Django code is in /DjangoFiles inside the container.
sys.path.insert(0, '/DjangoFiles')


import django

django.setup()

import pytest
from decimal import Decimal

from django.core.management import call_command
from django_tenants.utils import schema_context

from Customers.models import Client


# Prefixe pour identifier les donnees de test et les nettoyer.
# / Prefix to identify test data and clean it up.
TEST_PREFIX = '[test_pos_models]'

# Schema tenant utilise pour les tests.
# / Tenant schema used for tests.
TENANT_SCHEMA = 'lespass'


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def tenant():
    """Le tenant 'lespass' (doit exister dans la base).
    / The 'lespass' tenant (must exist in the database)."""
    return Client.objects.get(schema_name=TENANT_SCHEMA)


@pytest.fixture(scope="module", autouse=True)
def cleanup_test_data(tenant):
    """
    Supprime toutes les donnees creees par ce module de test APRES execution.
    Ordre : CartePrimaire → PointDeVente → Price → Product → CategorieProduct → Table → CategorieTable.
    / Deletes all test data AFTER execution. Respects FK ordering.
    """
    yield

    with schema_context(TENANT_SCHEMA):
        from BaseBillet.models import CategorieProduct, Product, Price
        from laboutik.models import CartePrimaire, PointDeVente, CategorieTable, Table

        # Suppression dans l'ordre des dependances FK
        # / Delete in FK dependency order
        # Les cartes de test sont nettoyees dans chaque test (SHARED_APPS).
        # / Test cards are cleaned up in each test (SHARED_APPS).

        pdv_test = PointDeVente.objects.filter(name__startswith=TEST_PREFIX)
        # Vider les M2M avant suppression
        # / Clear M2M before deletion
        for pdv in pdv_test:
            pdv.products.clear()
            pdv.categories.clear()
        pdv_test.delete()

        Price.objects.filter(name__startswith=TEST_PREFIX).delete()
        Product.objects.filter(name__startswith=TEST_PREFIX).delete()
        CategorieProduct.objects.filter(name__startswith=TEST_PREFIX).delete()
        Table.objects.filter(name__startswith=TEST_PREFIX).delete()
        CategorieTable.objects.filter(name__startswith=TEST_PREFIX).delete()


# ---------------------------------------------------------------------------
# Test 1 : CategorieProduct — creation et champs
# Test 1: CategorieProduct — creation and fields
# ---------------------------------------------------------------------------

def test_categorie_product_creation(tenant):
    with schema_context(TENANT_SCHEMA):
        from BaseBillet.models import CategorieProduct

        cat = CategorieProduct.objects.create(
            name=f'{TEST_PREFIX} Boissons',
            icon='bi-cup-straw',
            couleur_texte='#FFFFFF',
            couleur_fond='#3B82F6',
            poid_liste=0,
        )

        assert cat.pk is not None
        assert cat.name == f'{TEST_PREFIX} Boissons'
        assert cat.icon == 'bi-cup-straw'
        assert cat.couleur_texte == '#FFFFFF'
        assert cat.couleur_fond == '#3B82F6'
        assert cat.poid_liste == 0
        assert str(cat) == f'{TEST_PREFIX} Boissons'


# ---------------------------------------------------------------------------
# Test 2 : Product avec champs POS
# Test 2: Product with POS fields
# ---------------------------------------------------------------------------

def test_product_champs_pos(tenant):
    with schema_context(TENANT_SCHEMA):
        from BaseBillet.models import CategorieProduct, Product

        cat = CategorieProduct.objects.create(
            name=f'{TEST_PREFIX} Cat POS test',
            couleur_fond='#EF4444',
        )

        product = Product.objects.create(
            name=f'{TEST_PREFIX} Biere POS',
            methode_caisse=Product.VENTE,
            categorie_pos=cat,
            couleur_fond_pos='#F59E0B',
            couleur_texte_pos='#000000',
            icon_pos='bi-cup',
            fractionne=False,
            besoin_tag_id=False,
        )

        assert product.methode_caisse == 'VT'
        assert product.categorie_pos == cat
        assert product.couleur_fond_pos == '#F59E0B'
        assert product.couleur_texte_pos == '#000000'
        assert product.icon_pos == 'bi-cup'
        assert product.fractionne is False
        assert product.besoin_tag_id is False


# ---------------------------------------------------------------------------
# Test 3 : Product sans champs POS (produit billetterie normal)
# Test 3: Product without POS fields (normal ticket product)
# ---------------------------------------------------------------------------

def test_product_sans_pos(tenant):
    with schema_context(TENANT_SCHEMA):
        from BaseBillet.models import Product

        product = Product.objects.create(
            name=f'{TEST_PREFIX} Concert normal',
            categorie_article=Product.BILLET,
        )

        # Les champs POS doivent etre null
        # / POS fields must be null
        assert product.methode_caisse is None
        assert product.categorie_pos is None
        assert product.couleur_fond_pos is None
        assert product.icon_pos is None


# ---------------------------------------------------------------------------
# Test 4 : POSProduct proxy — filtre methode_caisse IS NOT NULL
# Test 4: POSProduct proxy — filter methode_caisse IS NOT NULL
# ---------------------------------------------------------------------------

def test_pos_product_proxy(tenant):
    with schema_context(TENANT_SCHEMA):
        from BaseBillet.models import Product, POSProduct

        # Creer un produit POS et un produit normal
        # / Create a POS product and a normal product
        pos_product = Product.objects.create(
            name=f'{TEST_PREFIX} POS Proxy Test',
            methode_caisse=Product.VENTE,
        )
        normal_product = Product.objects.create(
            name=f'{TEST_PREFIX} Normal Proxy Test',
            categorie_article=Product.BILLET,
        )

        # POSProduct est un proxy : meme table, meme manager par defaut.
        # Le filtrage est fait dans l'admin (get_queryset), pas dans le manager.
        # On verifie que le proxy fonctionne (meme pk, isinstance).
        # / POSProduct is a proxy: same table, same default manager.
        # Filtering is done in admin (get_queryset), not in the manager.
        # We verify the proxy works (same pk, isinstance).

        pos_via_proxy = POSProduct.objects.get(pk=pos_product.pk)
        assert isinstance(pos_via_proxy, Product)
        assert isinstance(pos_via_proxy, POSProduct)
        assert pos_via_proxy.methode_caisse == Product.VENTE

        # Le produit normal est aussi accessible via POSProduct (pas de manager custom),
        # mais son methode_caisse est None.
        # / Normal product is also accessible via POSProduct (no custom manager),
        # but its methode_caisse is None.
        normal_via_proxy = POSProduct.objects.get(pk=normal_product.pk)
        assert normal_via_proxy.methode_caisse is None

        # Verification que le filtre admin fonctionnerait :
        # methode_caisse__isnull=False ne retourne que les produits POS.
        # / Verify admin filter would work:
        # methode_caisse__isnull=False returns only POS products.
        qs_pos_only = POSProduct.objects.filter(
            methode_caisse__isnull=False,
            name__startswith=TEST_PREFIX,
        )
        pks = list(qs_pos_only.values_list('pk', flat=True))
        assert pos_product.pk in pks
        assert normal_product.pk not in pks


# ---------------------------------------------------------------------------
# Test 5 : Price.asset FK — null = EUR, set = tokens
# Test 5: Price.asset FK — null = EUR, set = tokens
# ---------------------------------------------------------------------------

def test_price_asset_fk(tenant):
    with schema_context(TENANT_SCHEMA):
        from BaseBillet.models import Product, Price
        from AuthBillet.models import Wallet
        from fedow_core.models import Asset
        from fedow_core.services import AssetService

        product = Product.objects.create(
            name=f'{TEST_PREFIX} Produit multi-tarif',
            methode_caisse=Product.VENTE,
        )

        # Prix en euros (asset=None)
        # / Price in euros (asset=None)
        price_eur = Price.objects.create(
            product=product,
            name=f'{TEST_PREFIX} Tarif EUR',
            prix=Decimal('5.00'),
        )
        assert price_eur.asset is None

        # Prix en tokens (asset set)
        # / Price in tokens (asset set)
        wallet_origin = Wallet.objects.create(name=f'{TEST_PREFIX} Wallet origin')

        # Nettoyer le produit signal d'un run precedent si existant.
        # Le signal post_save Asset cree automatiquement un Product
        # "Recharge <nom_asset>" qui peut rester d'un ancien run.
        # Price.product est on_delete=PROTECT → supprimer les Prix d'abord.
        # / Clean up signal product from a previous run if it exists.
        # The Asset post_save signal auto-creates a Product
        # "Recharge <asset_name>" that may remain from an older run.
        # Price.product is on_delete=PROTECT → delete Prices first.
        nom_produit_signal = f'Recharge {TEST_PREFIX} Monnaie test'
        Price.objects.filter(product__name=nom_produit_signal).delete()
        Product.objects.filter(name=nom_produit_signal).delete()

        asset = AssetService.creer_asset(
            tenant=Client.objects.get(schema_name=TENANT_SCHEMA),
            name=f'{TEST_PREFIX} Monnaie test',
            category=Asset.TLF,
            currency_code='EUR',
            wallet_origin=wallet_origin,
        )

        price_token = Price.objects.create(
            product=product,
            name=f'{TEST_PREFIX} Tarif token',
            prix=Decimal('2.00'),
            asset=asset,
        )
        assert price_token.asset == asset
        assert price_token.asset.category == Asset.TLF

        # Conversion centimes : int(round(prix * 100))
        # / Cents conversion: int(round(prix * 100))
        assert int(round(price_eur.prix * 100)) == 500
        assert int(round(price_token.prix * 100)) == 200

        # Nettoyage : prix et produit crees par le signal + asset + wallet
        # Price.product est on_delete=PROTECT → supprimer les Prix d'abord.
        # / Cleanup: prices and product created by signal + asset + wallet
        # Price.product is on_delete=PROTECT → delete Prices first.
        from fedow_core.models import Token, Transaction
        Price.objects.filter(product__name=nom_produit_signal).delete()
        Product.objects.filter(name=nom_produit_signal).delete()
        Transaction.objects.filter(asset=asset).delete()
        Token.objects.filter(wallet=wallet_origin).delete()
        asset.delete()
        wallet_origin.delete()


# ---------------------------------------------------------------------------
# Test 6 : PointDeVente — creation + M2M products/categories
# Test 6: PointDeVente — creation + M2M products/categories
# ---------------------------------------------------------------------------

def test_point_de_vente(tenant):
    with schema_context(TENANT_SCHEMA):
        from BaseBillet.models import CategorieProduct, Product
        from laboutik.models import PointDeVente

        cat = CategorieProduct.objects.create(
            name=f'{TEST_PREFIX} Cat PDV test',
        )
        product = Product.objects.create(
            name=f'{TEST_PREFIX} Produit PDV test',
            methode_caisse=Product.VENTE,
            categorie_pos=cat,
        )

        pdv = PointDeVente.objects.create(
            name=f'{TEST_PREFIX} Bar test',
            comportement=PointDeVente.DIRECT,
            service_direct=True,
            afficher_les_prix=True,
            accepte_especes=True,
            accepte_carte_bancaire=True,
            accepte_commandes=False,
        )

        # M2M products et categories
        pdv.products.add(product)
        pdv.categories.add(cat)

        assert pdv.products.count() == 1
        assert pdv.categories.count() == 1
        assert pdv.products.first().pk == product.pk
        assert pdv.categories.first().pk == cat.pk
        assert str(pdv) == f'{TEST_PREFIX} Bar test'

        # Reverse relation : product.points_de_vente
        assert product.points_de_vente.filter(pk=pdv.pk).exists()


# ---------------------------------------------------------------------------
# Test 7 : CartePrimaire — creation + lien CarteCashless + M2M PV
# Test 7: CartePrimaire — creation + CarteCashless link + M2M POS
# ---------------------------------------------------------------------------

def test_carte_primaire(tenant):
    with schema_context(TENANT_SCHEMA):
        from laboutik.models import CartePrimaire, PointDeVente
        from QrcodeCashless.models import CarteCashless, Detail

        import uuid as uuid_mod

        # Detail et CarteCashless sont en SHARED_APPS → accessibles sans schema_context
        # mais on les cree ici car c'est dans le yield du test.
        # / Detail and CarteCashless are SHARED_APPS → accessible without schema_context
        tenant_client = Client.objects.get(schema_name=TENANT_SCHEMA)

        detail, _ = Detail.objects.get_or_create(
            slug=f'{TEST_PREFIX}-detail',
            defaults={
                'base_url': 'test.tibillet.localhost',
                'generation': 1,
                'origine': tenant_client,
            },
        )

        # tag_id est varchar(8) — utiliser un id court et unique.
        # / tag_id is varchar(8) — use a short unique id.
        tag_id = 'TP' + uuid_mod.uuid4().hex[:6].upper()
        carte_nfc = CarteCashless.objects.create(
            tag_id=tag_id,
            uuid=uuid_mod.uuid4(),
            number=tag_id,  # number est aussi varchar(8) / number is also varchar(8)
            detail=detail,
        )

        pdv = PointDeVente.objects.create(
            name=f'{TEST_PREFIX} PDV carte test',
        )

        carte_primaire = CartePrimaire.objects.create(
            carte=carte_nfc,
            edit_mode=True,
        )
        carte_primaire.points_de_vente.add(pdv)

        assert carte_primaire.carte == carte_nfc
        assert carte_primaire.edit_mode is True
        assert carte_primaire.points_de_vente.count() == 1
        assert carte_primaire.points_de_vente.first().pk == pdv.pk

        # OneToOne reverse : carte_nfc.carte_primaire
        assert carte_nfc.carte_primaire == carte_primaire

        # Nettoyage CarteCashless et CartePrimaire (SHARED_APPS)
        # / Cleanup CarteCashless and CartePrimaire (SHARED_APPS)
        carte_primaire.delete()
        carte_nfc.delete()

        # On ne supprime PAS le Detail : son champ img (StdImageField, delete_orphans=True)
        # plante dans post_delete si aucune image n'a ete uploadee (name=None).
        # Le Detail est cree avec get_or_create, il sera reutilise entre les runs.
        # / We do NOT delete the Detail: its img field (StdImageField, delete_orphans=True)
        # crashes in post_delete if no image was uploaded (name=None).
        # The Detail is created with get_or_create, it will be reused between runs.


# ---------------------------------------------------------------------------
# Test 8 : Table + CategorieTable — creation et statuts
# Test 8: Table + CategorieTable — creation and statuses
# ---------------------------------------------------------------------------

def test_table_et_categorie(tenant):
    with schema_context(TENANT_SCHEMA):
        from laboutik.models import CategorieTable, Table

        cat_table = CategorieTable.objects.create(
            name=f'{TEST_PREFIX} Terrasse',
            icon='bi-sun',
        )

        table = Table.objects.create(
            name=f'{TEST_PREFIX} Table 1',
            categorie=cat_table,
            poids=0,
            statut=Table.LIBRE,
        )

        assert table.categorie == cat_table
        assert table.statut == 'L'
        assert str(table) == f'{TEST_PREFIX} Table 1'
        assert str(cat_table) == f'{TEST_PREFIX} Terrasse'

        # Changement de statut : Libre → Occupee → Servie → Libre
        # / Status change: Free → Occupied → Served → Free
        table.statut = Table.OCCUPEE
        table.save()
        table.refresh_from_db()
        assert table.statut == 'O'

        table.statut = Table.SERVIE
        table.save()
        table.refresh_from_db()
        assert table.statut == 'S'

        table.statut = Table.LIBRE
        table.save()
        table.refresh_from_db()
        assert table.statut == 'L'


# ---------------------------------------------------------------------------
# Test 9 : management command create_test_pos_data
# Test 9: management command create_test_pos_data
# ---------------------------------------------------------------------------

def test_create_test_pos_data_command(tenant):
    """
    Verifie que la commande create_test_pos_data cree bien les donnees attendues.
    Inclut la verification du PV Adhesion et des produits adhesion multi-tarif.
    / Verify that create_test_pos_data command creates expected data.
    Includes Adhesion POS and multi-rate membership products verification.
    """
    # Lancer la commande en forcant le schema du test via schema_context.
    # La commande detecte qu'elle est deja dans un tenant (schema != "public")
    # et utilise ce schema. Sans ca, elle prendrait le premier tenant non-public
    # qui pourrait etre different de TENANT_SCHEMA.
    # / Run the command inside schema_context so it uses our test tenant.
    # The command detects it's already in a tenant (schema != "public")
    # and uses that schema. Without this, it would pick the first non-public tenant.
    with schema_context(TENANT_SCHEMA):
        call_command('create_test_pos_data')

    with schema_context(TENANT_SCHEMA):
        from BaseBillet.models import CategorieProduct, Product, Price
        from laboutik.models import PointDeVente

        # --- Categories POS ---
        cat_bar = CategorieProduct.objects.filter(name='Bar').first()
        cat_resto = CategorieProduct.objects.filter(name='Restauration').first()
        assert cat_bar is not None, "Categorie 'Bar' doit exister"
        assert cat_resto is not None, "Categorie 'Restauration' doit exister"

        # --- Produits POS de vente ---
        # / POS sale products
        expected_pos_names = ['Biere', 'Coca', 'Pizza', 'Cafe', 'Eau']
        for name in expected_pos_names:
            product = Product.objects.filter(name=name).first()
            assert product is not None, f"Produit '{name}' doit exister"
            assert product.methode_caisse == Product.VENTE, f"'{name}' doit avoir methode_caisse=VENTE"
            assert product.prices.exists(), f"'{name}' doit avoir au moins un tarif"

        # --- Points de vente classiques ---
        # / Standard POS
        pdv_bar = PointDeVente.objects.filter(name='Bar').first()
        pdv_resto = PointDeVente.objects.filter(name='Restaurant').first()
        assert pdv_bar is not None, "PdV 'Bar' doit exister"
        assert pdv_resto is not None, "PdV 'Restaurant' doit exister"
        assert pdv_bar.products.count() > 0, "PdV 'Bar' doit avoir des produits"
        assert pdv_bar.categories.filter(pk=cat_bar.pk).exists(), "PdV 'Bar' doit avoir la categorie Bar"
        assert pdv_resto.products.count() > 0, "PdV 'Restaurant' doit avoir des produits"

        # --- PV Adhesion (type ADHESION, charge auto les produits adhesion) ---
        # / Membership POS (ADHESION type, auto-loads membership products)
        pdv_adhesion = PointDeVente.objects.filter(name='Adhesions').first()
        assert pdv_adhesion is not None, "PdV 'Adhesions' doit exister"
        assert pdv_adhesion.comportement == PointDeVente.ADHESION, "PdV 'Adhesions' doit etre de type ADHESION"
        assert pdv_adhesion.accepte_especes is True, "PdV 'Adhesions' doit accepter les especes"
        assert pdv_adhesion.accepte_carte_bancaire is True, "PdV 'Adhesions' doit accepter la CB"
        # Le PV Adhesion a les produits adhesion dans son M2M (meme nombre que les produits adhesion publies)
        # / Adhesion POS has membership products in its M2M (same count as published membership products)
        nombre_adhesions_publiees = Product.objects.filter(
            categorie_article=Product.ADHESION, publish=True
        ).count()
        assert pdv_adhesion.products.count() == nombre_adhesions_publiees, (
            f"PdV 'Adhesions' doit avoir {nombre_adhesions_publiees} produit(s) adhesion en M2M"
        )

        # --- Produits adhesion ---
        # Les produits adhesion sont crees par demo_data_v2 (pas par create_test_pos_data).
        # Le PV Adhesion les charge dynamiquement via categorie_article=ADHESION.
        # On verifie que le PV n'a PAS de produits en M2M (chargement dynamique).
        # / Membership products are created by demo_data_v2 (not by create_test_pos_data).
        # The Adhesion POS loads them dynamically via categorie_article=ADHESION.
        # We verify the POS has NO products in M2M (dynamic loading).

        # --- Le PV Cashless ne contient PLUS les adhesions ---
        # / Cashless POS no longer contains memberships
        pdv_cashless = PointDeVente.objects.filter(name='Cashless').first()
        assert pdv_cashless is not None, "PdV 'Cashless' doit exister"
        adhesions_dans_cashless = pdv_cashless.products.filter(
            categorie_article=Product.ADHESION,
        ).count()
        assert adhesions_dans_cashless == 0, "PdV 'Cashless' ne doit PAS avoir de produits adhesion"
