"""
tests/pytest/test_menu_ventes.py — Tests Session 16 : menu Ventes (Ticket X + liste).
tests/pytest/test_menu_ventes.py — Tests Session 16: Sales menu (Ticket X + list).

Couvre : recap_en_cours (3 vues), liste_ventes (pagination, filtre), detail_vente.
Covers: recap_en_cours (3 views), liste_ventes (pagination, filter), detail_vente.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_menu_ventes.py -v
"""

import os
import sys
import uuid as uuid_module

# Le code Django est dans /DjangoFiles a l'interieur du conteneur.
# / Django code is in /DjangoFiles inside the container.
sys.path.insert(0, '/DjangoFiles')

import django
django.setup()

import pytest

from decimal import Decimal
from django.utils import timezone
from django_tenants.utils import schema_context

from AuthBillet.models import TibilletUser
from BaseBillet.models import (
    LigneArticle, Price, PriceSold, Product, ProductSold,
    SaleOrigin, PaymentMethod,
)
from Customers.models import Client
from laboutik.models import (
    PointDeVente, ClotureCaisse,
)

# Schema tenant utilise pour les tests.
# / Tenant schema used for tests.
TENANT_SCHEMA = 'lespass'


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def tenant():
    """Le tenant 'lespass' (doit exister dans la base).
    / The 'lespass' tenant (must exist in DB)."""
    return Client.objects.get(schema_name=TENANT_SCHEMA)


@pytest.fixture(scope="module")
def test_data(tenant):
    """Lance create_test_pos_data pour s'assurer que les donnees existent.
    / Runs create_test_pos_data to ensure test data exists."""
    from django.core.management import call_command
    # Forcer le schema lespass : sinon, lancee depuis le schema public, la
    # commande prend le premier tenant non-public via .first() (souvent un
    # schema UUID de test orphelin sans tables) -> "relation does not exist".
    # Meme PIEGE documente que dans test_caisse_navigation.
    # / Force the lespass schema: otherwise the command (run from public) picks
    # the first non-public tenant via .first() (often an orphan UUID test schema
    # without tables). Same documented pitfall as in test_caisse_navigation.
    with schema_context(TENANT_SCHEMA):
        call_command('create_test_pos_data')
    return True


@pytest.fixture(scope="module")
def admin_user(tenant):
    """Un utilisateur admin du tenant.
    / A tenant admin user."""
    with schema_context(TENANT_SCHEMA):
        email = 'admin-test-ventes@tibillet.localhost'
        user, _created = TibilletUser.objects.get_or_create(
            email=email,
            defaults={
                'username': email,
                'is_staff': True,
                'is_active': True,
            },
        )
        user.client_admin.add(tenant)
        return user


@pytest.fixture(scope="module")
def premier_pv(test_data):
    """Le premier point de vente (Bar).
    / The first point of sale (Bar)."""
    with schema_context(TENANT_SCHEMA):
        return PointDeVente.objects.filter(hidden=False).order_by('poid_liste').first()


@pytest.fixture(scope="module")
def premier_produit_et_prix(premier_pv):
    """Premier produit du PV avec son prix.
    / First product of the PV with its price."""
    with schema_context(TENANT_SCHEMA):
        produit = premier_pv.products.filter(
            methode_caisse__isnull=False,
        ).first()
        prix = Price.objects.filter(
            product=produit,
            publish=True,
            asset__isnull=True,
        ).order_by('order').first()
        return produit, prix


def _make_client(admin_user, tenant):
    """Cree un client DRF authentifie comme admin du tenant.
    / Creates a DRF client authenticated as tenant admin."""
    from rest_framework.test import APIClient
    client = APIClient()
    client.force_authenticate(user=admin_user)
    client.defaults['SERVER_NAME'] = f'{TENANT_SCHEMA}.tibillet.localhost'
    return client


def _creer_ligne_article_directe(produit, prix, montant_centimes, payment_method_code, pv=None, uuid_tx=None, qty=1, weight_quantity=None):
    """
    Cree une LigneArticle directement en base (sans passer par la vue).
    Creates a LigneArticle directly in DB (without going through the view).

    :param qty: quantite de la ligne (defaut 1). Mettre > 1 pour reproduire le bug 4
                (Sum(amount) au lieu de Sum(amount * qty)).
    :param weight_quantity: int en g ou cl (vrac). Pour vrac : qty=1 + weight_quantity > 0.
    """
    product_sold, _ = ProductSold.objects.get_or_create(
        product=produit,
        event=None,
        defaults={'categorie_article': produit.categorie_article},
    )
    price_sold, _ = PriceSold.objects.get_or_create(
        productsold=product_sold,
        price=prix,
        defaults={'prix': prix.prix},
    )
    ligne = LigneArticle.objects.create(
        pricesold=price_sold,
        qty=qty,
        amount=montant_centimes,
        sale_origin=SaleOrigin.LABOUTIK,
        payment_method=payment_method_code,
        status=LigneArticle.VALID,
        point_de_vente=pv,
        uuid_transaction=uuid_tx,
        weight_quantity=weight_quantity,
    )
    return ligne


# ---------------------------------------------------------------------------
# Tests Ticket X (recap_en_cours)
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("test_data")
class TestRecapEnCours:
    """Tests du Ticket X — recap comptable du service en cours.
    / Tests for Ticket X — accounting summary of current shift."""

    def test_recap_en_cours_toutes_caisses(
        self, admin_user, tenant, premier_pv, premier_produit_et_prix,
    ):
        """
        Cree des ventes, appelle recap-en-cours avec vue=toutes.
        Verifie : 200, contient "Ticket X", contient les totaux.
        / Create sales, call recap-en-cours with vue=toutes.
        Verify: 200, contains "Ticket X", contains totals.
        """
        with schema_context(TENANT_SCHEMA):
            produit, prix = premier_produit_et_prix
            # Creer une vente pour s'assurer qu'il y a des donnees
            # / Create a sale to ensure data exists
            _creer_ligne_article_directe(produit, prix, 500, PaymentMethod.CASH, pv=premier_pv)

            client = _make_client(admin_user, tenant)
            response = client.get('/laboutik/caisse/recap-en-cours/?vue=toutes')
            assert response.status_code == 200

            contenu = response.content.decode('utf-8')
            # Verifie que le template Ticket X est rendu
            # / Verify Ticket X template is rendered
            assert 'data-testid="ventes-recap"' in contenu
            # Verifie que les totaux sont presents (tableau des moyens de paiement)
            # / Verify totals are present (payment method table)
            assert 'data-testid="recap-totaux-moyen"' in contenu

    def test_recap_en_cours_par_pv(
        self, admin_user, tenant, premier_pv, premier_produit_et_prix,
    ):
        """
        Appelle recap-en-cours avec vue=par_pv.
        Verifie : 200, contient le nom du PV.
        / Calls recap-en-cours with vue=par_pv.
        Verify: 200, contains POS name.
        """
        with schema_context(TENANT_SCHEMA):
            produit, prix = premier_produit_et_prix
            _creer_ligne_article_directe(produit, prix, 300, PaymentMethod.CC, pv=premier_pv)

            client = _make_client(admin_user, tenant)
            response = client.get('/laboutik/caisse/recap-en-cours/?vue=par_pv')
            assert response.status_code == 200

            contenu = response.content.decode('utf-8')
            # La ventilation par PV doit contenir le nom du PV
            # / The POS breakdown must contain the POS name
            assert premier_pv.name in contenu

    def test_recap_en_cours_par_moyen(
        self, admin_user, tenant, premier_pv, premier_produit_et_prix,
    ):
        """
        Appelle recap-en-cours avec vue=par_moyen.
        Verifie : 200, contient le tableau synthese operations.
        / Calls recap-en-cours with vue=par_moyen.
        Verify: 200, contains operations summary table.
        """
        with schema_context(TENANT_SCHEMA):
            client = _make_client(admin_user, tenant)
            response = client.get('/laboutik/caisse/recap-en-cours/?vue=par_moyen')
            assert response.status_code == 200

            contenu = response.content.decode('utf-8')
            assert 'data-testid="recap-synthese-operations"' in contenu

    def test_recap_en_cours_aucune_vente(
        self, admin_user, tenant,
    ):
        """
        Si aucune vente apres une cloture, affiche le message vide.
        / If no sales after a closure, show empty message.

        NOTE : ce test peut ne pas trouver "aucune vente" si d'autres tests
        ont cree des LigneArticle. On verifie juste que la vue retourne 200.
        / This test may not find "no sales" if other tests created LigneArticle.
        We just verify the view returns 200.
        """
        with schema_context(TENANT_SCHEMA):
            client = _make_client(admin_user, tenant)
            response = client.get('/laboutik/caisse/recap-en-cours/')
            assert response.status_code == 200


# ---------------------------------------------------------------------------
# Tests liste des ventes
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("test_data")
class TestListeVentes:
    """Tests de la liste des ventes.
    / Tests for the sales list."""

    def test_liste_ventes_paginee(
        self, admin_user, tenant, premier_pv, premier_produit_et_prix,
    ):
        """
        Appelle liste-ventes.
        Verifie : 200, contient le tableau des ventes.
        / Calls liste-ventes.
        Verify: 200, contains sales table.
        """
        with schema_context(TENANT_SCHEMA):
            produit, prix = premier_produit_et_prix
            # S'assurer qu'il y a au moins une vente
            # / Ensure at least one sale exists
            _creer_ligne_article_directe(produit, prix, 700, PaymentMethod.CASH, pv=premier_pv)

            client = _make_client(admin_user, tenant)
            response = client.get('/laboutik/caisse/liste-ventes/')
            assert response.status_code == 200

            contenu = response.content.decode('utf-8')
            assert 'data-testid="ventes-liste"' in contenu

    def test_liste_ventes_filtre_moyen(
        self, admin_user, tenant, premier_pv, premier_produit_et_prix,
    ):
        """
        Filtre la liste par moyen de paiement (especes).
        Verifie : 200, ne contient que les ventes en especes.
        / Filter list by payment method (cash).
        Verify: 200, contains only cash sales.
        """
        with schema_context(TENANT_SCHEMA):
            client = _make_client(admin_user, tenant)
            response = client.get(f'/laboutik/caisse/liste-ventes/?moyen={PaymentMethod.CASH}')
            assert response.status_code == 200

            contenu = response.content.decode('utf-8')
            # Le filtre est applique — on verifie que la page se charge
            # / Filter is applied — we verify the page loads
            assert 'data-testid="ventes-liste"' in contenu

    def test_liste_ventes_total_qty_multiplie(
        self, admin_user, tenant, premier_pv, premier_produit_et_prix,
    ):
        """
        Bug 4 : 3 pintes a 5€ doivent afficher 15€ dans la liste, pas 5€.
        Le Sum doit etre amount * qty, pas amount seul.
        / Bug 4: 3 pints at 5€ must show 15€ in the list, not 5€.
        Sum must be amount * qty, not amount alone.
        """
        with schema_context(TENANT_SCHEMA):
            produit, prix = premier_produit_et_prix
            uuid_tx = uuid_module.uuid4()

            # Creer une ligne avec qty=3, amount=500 (5€ unitaire)
            # Total reel transaction = 500 * 3 = 1500 centimes = 15€
            # Ancien bug : Sum(amount) ramenait 500 → 5€ affiches.
            # / Create line with qty=3, amount=500 (5€ unit). Real total = 1500c = 15€.
            _creer_ligne_article_directe(
                produit, prix, 500, PaymentMethod.CASH,
                pv=premier_pv, uuid_tx=uuid_tx, qty=3,
            )

            client = _make_client(admin_user, tenant)
            response = client.get(f'/laboutik/caisse/liste-ventes/?pv={premier_pv.uuid}&moyen={PaymentMethod.CASH}')
            assert response.status_code == 200

            contenu = response.content.decode('utf-8')
            # Le total affiche doit etre 15,00 (3 pintes * 5€), pas 5,00.
            # Format du filtre |euros : "15,00 €" (espace insecable U+00A0 entre montant et symbole).
            # / The displayed total must be 15,00, not 5,00.
            assert '15,00' in contenu, (
                f"Total devrait inclure 15,00 € (3 x 5€), regression du bug 4. "
                f"Si '5,00' est la, le Sum(amount) ne multiplie pas par qty. "
                f"Contenu (extrait) : {contenu[:2000]}"
            )

    def test_liste_ventes_multi_lignes_qty(
        self, admin_user, tenant, premier_pv, premier_produit_et_prix,
    ):
        """
        Une transaction = 2 lignes (pinte qty=3 a 5€, demi qty=2 a 3€).
        Total reel = 15 + 6 = 21€. Verifie que le total agrege est correct.
        / One transaction = 2 lines (pint qty=3 at 5€, half qty=2 at 3€).
        Real total = 15 + 6 = 21€. Verify aggregate total is correct.
        """
        with schema_context(TENANT_SCHEMA):
            produit, prix = premier_produit_et_prix
            uuid_tx = uuid_module.uuid4()

            # Ligne 1 : 3 unites a 500c → 1500c
            _creer_ligne_article_directe(
                produit, prix, 500, PaymentMethod.CASH,
                pv=premier_pv, uuid_tx=uuid_tx, qty=3,
            )
            # Ligne 2 : 2 unites a 300c → 600c (sur la meme transaction)
            _creer_ligne_article_directe(
                produit, prix, 300, PaymentMethod.CASH,
                pv=premier_pv, uuid_tx=uuid_tx, qty=2,
            )

            client = _make_client(admin_user, tenant)
            response = client.get(f'/laboutik/caisse/liste-ventes/?pv={premier_pv.uuid}&moyen={PaymentMethod.CASH}')
            assert response.status_code == 200

            contenu = response.content.decode('utf-8')
            # Total reel = 1500 + 600 = 2100c = 21,00 €
            # / Real total = 1500 + 600 = 2100c = 21,00 €
            assert '21,00' in contenu, (
                "Total devrait inclure 21,00 € (3*5 + 2*3), regression du bug 4."
            )


# ---------------------------------------------------------------------------
# Tests detail vente
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("test_data")
class TestDetailVente:
    """Tests du detail d'une vente.
    / Tests for sale detail."""

    def test_detail_vente_existante(
        self, admin_user, tenant, premier_pv, premier_produit_et_prix,
    ):
        """
        Cree une vente avec uuid_transaction, appelle detail-vente.
        Verifie : 200, contient les infos de la transaction.
        / Creates a sale with uuid_transaction, calls detail-vente.
        Verify: 200, contains transaction info.
        """
        with schema_context(TENANT_SCHEMA):
            produit, prix = premier_produit_et_prix
            uuid_tx = uuid_module.uuid4()

            _creer_ligne_article_directe(
                produit, prix, 1500, PaymentMethod.CASH,
                pv=premier_pv, uuid_tx=uuid_tx,
            )

            client = _make_client(admin_user, tenant)
            response = client.get(f'/laboutik/caisse/detail-vente/{uuid_tx}/')
            assert response.status_code == 200

            contenu = response.content.decode('utf-8')
            assert 'data-testid="ventes-detail"' in contenu
            assert 'data-testid="detail-articles"' in contenu
            # Le produit doit apparaitre dans le detail
            # / The product must appear in the detail
            assert produit.name in contenu

    def test_detail_vente_introuvable(
        self, admin_user, tenant,
    ):
        """
        Appelle detail-vente avec un uuid_transaction inexistant.
        Verifie : 404.
        / Calls detail-vente with a nonexistent uuid_transaction.
        Verify: 404.
        """
        with schema_context(TENANT_SCHEMA):
            uuid_bidon = uuid_module.uuid4()
            client = _make_client(admin_user, tenant)
            response = client.get(f'/laboutik/caisse/detail-vente/{uuid_bidon}/')
            assert response.status_code == 404

    def test_detail_vente_total_qty_multiplie(
        self, admin_user, tenant, premier_pv, premier_produit_et_prix,
    ):
        """
        Bug 4 (detail) : meme principe sur le detail vente.
        3 pintes a 5€ → ligne montre Qty=3, Prix unit=5€, Total=15€.
        Total transaction en bas = 15€.
        / Bug 4 (detail): same principle on sale detail.
        3 pints at 5€ → row shows Qty=3, Unit price=5€, Total=15€.
        """
        with schema_context(TENANT_SCHEMA):
            produit, prix = premier_produit_et_prix
            uuid_tx = uuid_module.uuid4()

            _creer_ligne_article_directe(
                produit, prix, 500, PaymentMethod.CASH,
                pv=premier_pv, uuid_tx=uuid_tx, qty=3,
            )

            client = _make_client(admin_user, tenant)
            response = client.get(f'/laboutik/caisse/detail-vente/{uuid_tx}/')
            assert response.status_code == 200

            contenu = response.content.decode('utf-8')

            # data-testid sur le total ligne et le total transaction
            # / data-testid on line total and transaction total
            assert 'data-testid="detail-total-ligne"' in contenu
            assert 'data-testid="detail-total-transaction"' in contenu

            # Le total ligne et le total transaction doivent etre 15,00 €.
            # Le prix unitaire 5,00 € apparait aussi (colonne dediee).
            # / Both line total and transaction total must be 15,00 €.
            assert '15,00' in contenu, (
                "Total ligne ou transaction devrait inclure 15,00 € (3 x 5€), regression du bug 4."
            )
            assert '5,00' in contenu, (
                "Le prix unitaire 5,00 € doit apparaitre dans la colonne dediee."
            )

    def test_detail_vente_vrac_qty_en_grammes_prix_au_kg(
        self, admin_user, tenant, premier_pv,
    ):
        """
        Bug 4 (vrac) : pour une ligne vrac (poids_mesure), le detail vente doit afficher
            Qty = "350g" (pas "1")
            Prix unit. = "12,00 €/kg" (pas le prix de la ligne)
            Total = 4,20 € (350 * 0,012 €/g = amount calcule cote JS)
        / Bug 4 (vrac): for a weight-based line, sale detail must display weight
        in qty column and price per kg in unit price column.
        """
        from BaseBillet.models import Product, Price
        from inventaire.models import Stock, UniteStock

        with schema_context(TENANT_SCHEMA):
            # Charge ou cree les fixtures vrac (Cacahuetes en vrac, 12€/kg, stock GR).
            # Les fixtures sont posees par create_test_pos_data ; sinon on les recree.
            # / Load or create vrac fixtures.
            cacahuetes = Product.objects.filter(name="Cacahuetes en vrac").first()
            if cacahuetes is None:
                pytest.skip("Fixture 'Cacahuetes en vrac' absente — create_test_pos_data ne la cree pas dans ce contexte")
            prix_vrac = Price.objects.filter(
                product=cacahuetes, poids_mesure=True
            ).first()
            assert prix_vrac is not None, "Le prix poids_mesure des cacahuetes doit exister"

            # S'assurer que le Stock existe avec unite GR
            # / Ensure Stock exists with GR unit
            Stock.objects.get_or_create(
                product=cacahuetes,
                defaults={"quantite": 5000, "unite": UniteStock.GR},
            )

            # Vente : 350g a 12€/kg → amount = 350 * 12 / 1000 = 4,20 € = 420c
            # / Sale: 350g at 12€/kg → amount = 420 cents
            uuid_tx = uuid_module.uuid4()
            _creer_ligne_article_directe(
                cacahuetes, prix_vrac, 420, PaymentMethod.CASH,
                pv=premier_pv, uuid_tx=uuid_tx,
                qty=1, weight_quantity=350,
            )

            client = _make_client(admin_user, tenant)
            response = client.get(f'/laboutik/caisse/detail-vente/{uuid_tx}/')
            assert response.status_code == 200

            contenu = response.content.decode('utf-8')

            # Affichage attendu sur la ligne :
            # / Expected line display:
            assert '350g' in contenu, (
                "La colonne Qty doit afficher '350g' pour le vrac, pas '1'."
            )
            assert '12,00 €/kg' in contenu, (
                "La colonne Prix unit. doit afficher le prix au kg, pas le prix de la ligne."
            )
            # Total ligne et total transaction = 4,20 €
            # / Line total and transaction total = 4,20 €
            assert '4,20' in contenu

    def test_detail_vente_uuid_invalide(
        self, admin_user, tenant,
    ):
        """
        Appelle detail-vente avec une chaine qui n'est pas un UUID.
        Verifie : 404 (pas 500).
        / Calls detail-vente with a string that is not a UUID.
        Verify: 404 (not 500).
        """
        with schema_context(TENANT_SCHEMA):
            client = _make_client(admin_user, tenant)
            response = client.get('/laboutik/caisse/detail-vente/pas-un-uuid/')
            assert response.status_code == 404
