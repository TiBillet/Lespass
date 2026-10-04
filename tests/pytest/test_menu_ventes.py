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
from django.db import connection
from django.utils import timezone
from django_tenants.test.cases import FastTenantTestCase
from django_tenants.test.client import TenantClient
from django_tenants.utils import schema_context

from AuthBillet.models import TibilletUser
from BaseBillet.models import (
    Configuration, LigneArticle, Price, PriceSold, Product, ProductSold,
    SaleOrigin, PaymentMethod,
)
from Customers.models import Client
from fabriques_vente import (
    creer_tarif_vendu,
    fabriquer_vente_encaissee,
    verifier_egalites,
)
from laboutik.models import (
    LaboutikConfiguration, PointDeVente,
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
    # La commande remplit le lieu de son option --schema, jamais le schema
    # courant de la connexion. / The command fills its --schema venue.
    call_command('create_test_pos_data', schema=TENANT_SCHEMA)
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
    """Le point de vente « Bar », cree par create_test_pos_data.
    / The "Bar" point of sale, created by create_test_pos_data.

    Vise par son nom : trier par poid_liste ne suffit pas, d'autres tests laissent
    des points de vente a poid_liste 0 dans lespass, et l'ex aequo tombait au hasard.
    / Targeted by name: other tests leave poid_liste 0 points of sale behind."""
    with schema_context(TENANT_SCHEMA):
        return PointDeVente.objects.get(name="Bar")


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


# Le récapitulatif en cours et la liste des ventes ont besoin d'un service en
# cours : ils sont testés dans TestEcransVentesSurDesVentesReglees (schéma dédié,
# ventes réglées), plus bas. Totaux et point de vente du récap :
# test_rapport_temps_reel.py.
# / The current recap and the sales list need a current service: tested in
# TestEcransVentesSurDesVentesReglees (dedicated schema) below.


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
                pytest.fail("Fixture 'Cacahuetes en vrac' absente — create_test_pos_data ne la cree pas dans ce contexte")
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


# ---------------------------------------------------------------------------
# Tests propagation des parametres GET dans les URLs Ventes
# ---------------------------------------------------------------------------

# Parametres de test : faux tag de carte primaire et type d'app.
# / Test params: fake primary card tag and app type.
TAG_ID_CM_DE_TEST = 'A49E8E2A'
TYPE_APP_DE_TEST = 'sunmi'


@pytest.mark.usefixtures("test_data")
class TestParamsVentesPropages:
    """
    Les onglets Ventes font un hx-push-url. Chaque URL doit garder
    uuid_pv, tag_id_cm et type_app, sinon ils disparaissent de l'URL du navigateur.
    / Sales tabs push their URL. Each URL must keep uuid_pv, tag_id_cm and type_app.
    """

    # Boutons fond et sortie de caisse du récap : TestEcransVentesSurDesVentesReglees.
    # / Recap float and withdrawal buttons: TestEcransVentesSurDesVentesReglees.

    def test_fond_de_caisse_bouton_retour_garde_les_params(
        self, admin_user, tenant, premier_pv,
    ):
        """
        Le bouton Retour du Fond de caisse doit renvoyer vers le Ticket X avec les 3 params.
        / The Cash float Back button must go back to Ticket X with the 3 params.
        """
        with schema_context(TENANT_SCHEMA):
            client = _make_client(admin_user, tenant)
            response = client.get(
                f'/laboutik/caisse/fond-de-caisse/?uuid_pv={premier_pv.uuid}'
                f'&tag_id_cm={TAG_ID_CM_DE_TEST}&type_app={TYPE_APP_DE_TEST}'
            )
            assert response.status_code == 200
            contenu = response.content.decode('utf-8')
            assert (
                f'/laboutik/caisse/recap-en-cours/?uuid_pv={premier_pv.uuid}'
                f'&amp;tag_id_cm={TAG_ID_CM_DE_TEST}&amp;type_app={TYPE_APP_DE_TEST}'
            ) in contenu

    def test_sortie_de_caisse_formulaire_renvoie_tag_et_type_app(
        self, admin_user, tenant, premier_pv,
    ):
        """
        Le formulaire de Sortie de caisse doit renvoyer tag_id_cm et type_app en champs caches.
        / The Cash withdrawal form must send back tag_id_cm and type_app as hidden fields.
        """
        with schema_context(TENANT_SCHEMA):
            client = _make_client(admin_user, tenant)
            response = client.get(
                f'/laboutik/caisse/sortie-de-caisse/?uuid_pv={premier_pv.uuid}'
                f'&tag_id_cm={TAG_ID_CM_DE_TEST}&type_app={TYPE_APP_DE_TEST}'
            )
            assert response.status_code == 200
            contenu = response.content.decode('utf-8')
            assert f'name="tag_id_cm" value="{TAG_ID_CM_DE_TEST}"' in contenu
            assert f'name="type_app" value="{TYPE_APP_DE_TEST}"' in contenu


# ---------------------------------------------------------------------------
# Écrans Ventes sur des ventes réglées, en schéma dédié
# / Sales screens on settled sales, in a dedicated schema
# ---------------------------------------------------------------------------


class TestEcransVentesSurDesVentesReglees(FastTenantTestCase):
    """
    Les tests des écrans Ventes qui ont besoin d'un service en cours. Le service en
    cours commence à la fin de la dernière clôture journalière et n'existe que s'il
    y a une vente RÉGLÉE depuis : en base partagée, il dépendrait de l'état de la base
    de dev (une clôture faite par le filet automatique). Ici, le lieu ne contient que
    les ventes du test, écrites par le service de vente, et chaque test annule sa
    transaction.
    / Sales screen tests needing a current service: dedicated schema, settled sales
    written by the sale service.
    """

    @classmethod
    def get_test_schema_name(cls):
        return 'test_menu_ventes'

    @classmethod
    def get_test_tenant_domain(cls):
        return 'test-menu-ventes.tibillet.localhost'

    @classmethod
    def setup_tenant(cls, tenant):
        """`Client.name` est unique et obligatoire. / Client.name is unique."""
        tenant.name = 'Test menu ventes'

    def setUp(self):
        """
        Un comptoir, une pinte à 5,00 € et un demi à 3,00 €, un admin connecté.
        / A counter, a pint at 5.00 € and a half at 3.00 €, a logged-in admin.
        """
        # Le rollback du test précédent a rendu le `search_path` au public.
        # / The previous test's rollback returned the search_path to public.
        connection.set_tenant(self.tenant)

        # Le singleton de la caisse porte la clé des empreintes (tests/PIEGES.md 9.86).
        # / The register singleton carries the fingerprint key.
        LaboutikConfiguration.get_solo().save()

        configuration = Configuration.get_solo()
        configuration.module_monnaie_locale = True
        configuration.module_caisse = True
        configuration.rapport_emails = ''
        configuration.save()

        self.tarif_de_la_pinte = creer_tarif_vendu(
            nom="Pinte", prix_en_euros="5.00", taux_tva="20.00",
        )
        self.tarif_du_demi = creer_tarif_vendu(
            nom="Demi", prix_en_euros="3.00", taux_tva="20.00",
        )
        self.point_de_vente = PointDeVente.objects.create(
            name='Comptoir menu ventes',
            comportement=PointDeVente.DIRECT,
            service_direct=True,
            accepte_especes=True,
            accepte_carte_bancaire=True,
            hidden=True,
        )

        # `TibilletUser` vit dans le schéma public ; il est annulé avec le test.
        # / TibilletUser lives in the public schema; rolled back with the test.
        self.admin, _admin_cree = TibilletUser.objects.get_or_create(
            email='admin-test-menu-ventes@tibillet.localhost',
            defaults={
                'username': 'admin-test-menu-ventes@tibillet.localhost',
                'is_staff': True,
                'is_active': True,
            },
        )
        self.admin.client_admin.add(self.tenant)
        self.client_http = TenantClient(self.tenant)
        self.client_http.force_login(self.admin)

    def _vendre_en_especes(self, articles_vendus):
        """
        Une vente de caisse réglée en espèces, au comptoir du test : un article par
        couple (tarif, prix unitaire en centimes, quantité), toutes sur le même
        identifiant de paiement (un panier).
        / A settled cash register sale: one item per (price, unit price, quantity).
        """
        identifiant_du_paiement = uuid_module.uuid4()
        articles = []
        montant_total = 0
        for tarif_vendu, prix_unitaire, quantite in articles_vendus:
            articles.append({
                'pricesold': tarif_vendu,
                'quantite': Decimal(quantite),
                'prix_unitaire': prix_unitaire,
                'taux_tva': Decimal('20'),
                'payment_method': PaymentMethod.CASH,
                'status': LigneArticle.VALID,
                'uuid_transaction': identifiant_du_paiement,
                'point_de_vente': self.point_de_vente,
            })
            montant_total += prix_unitaire * quantite
        vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            point_de_vente=self.point_de_vente,
            articles=articles,
            reglements=[{'moyen': PaymentMethod.CASH, 'montant': montant_total}],
        )
        verifier_egalites(vente)
        return vente

    def test_recap_en_cours_aucune_vente(self):
        """
        Un lieu sans aucune vente : le récapitulatif en cours répond 200 et dit
        « aucune vente » (`data-testid="recap-aucune-vente"`).
        / A venue without any sale: the recap says "no sale".
        """
        response = self.client_http.get('/laboutik/caisse/recap-en-cours/')

        assert response.status_code == 200
        contenu = response.content.decode('utf-8')
        assert 'data-testid="recap-aucune-vente"' in contenu

    def test_liste_ventes_paginee(self):
        """
        Une vente réglée en espèces, puis la liste des ventes : 200, et le tableau
        des ventes (`data-testid="ventes-liste"`).
        / A settled cash sale, then the sales list: 200 and the sales table.
        """
        self._vendre_en_especes([(self.tarif_de_la_pinte, 500, 1)])

        response = self.client_http.get('/laboutik/caisse/liste-ventes/')

        assert response.status_code == 200
        contenu = response.content.decode('utf-8')
        assert 'data-testid="ventes-liste"' in contenu

    def test_liste_ventes_filtre_moyen(self):
        """
        Une vente réglée en espèces, puis la liste filtrée sur les espèces : 200, et
        le tableau des ventes.
        / A settled cash sale, then the list filtered on cash: 200 and the table.
        """
        self._vendre_en_especes([(self.tarif_de_la_pinte, 500, 1)])

        response = self.client_http.get(
            f'/laboutik/caisse/liste-ventes/?moyen={PaymentMethod.CASH}'
        )

        assert response.status_code == 200
        contenu = response.content.decode('utf-8')
        assert 'data-testid="ventes-liste"' in contenu

    def test_recap_en_cours_par_moyen(self):
        """
        Une vente réglée, puis recap-en-cours avec vue=par_moyen.
        Verifie : 200, contient le tableau synthese operations.
        / A settled sale, then recap-en-cours with vue=par_moyen.
        """
        self._vendre_en_especes([(self.tarif_de_la_pinte, 500, 1)])

        response = self.client_http.get('/laboutik/caisse/recap-en-cours/?vue=par_moyen')

        assert response.status_code == 200
        contenu = response.content.decode('utf-8')
        assert 'data-testid="recap-synthese-operations"' in contenu
        # Ce tableau lit les lignes de la caisse (recharges comprises, sans les
        # ventes en ligne) : son titre le dit, pour qu'on ne le confonde pas avec le
        # chiffre d'affaires par moyen du rapport.
        # / This table reads register lines: its title says so.
        assert "Lignes de caisse (hors ventes en ligne, recharges comprises)" in contenu

    def test_liste_ventes_total_qty_multiplie(self):
        """
        Bug 4 : 3 pintes a 5€ doivent afficher 15€ dans la liste, pas 5€.
        Le Sum doit etre amount * qty, pas amount seul.
        / Bug 4: 3 pints at 5€ must show 15€ in the list, not 5€.
        """
        # Une ligne qty=3, amount=500 : total reel 500 * 3 = 1500 centimes = 15€.
        # / One line qty=3, amount=500: real total 1500c = 15€.
        self._vendre_en_especes([(self.tarif_de_la_pinte, 500, 3)])

        response = self.client_http.get(
            f'/laboutik/caisse/liste-ventes/?pv={self.point_de_vente.uuid}'
            f'&moyen={PaymentMethod.CASH}'
        )

        assert response.status_code == 200
        contenu = response.content.decode('utf-8')
        assert '15,00' in contenu, (
            f"Total devrait inclure 15,00 € (3 x 5€), regression du bug 4. "
            f"Si '5,00' est la, le Sum(amount) ne multiplie pas par qty. "
            f"Contenu (extrait) : {contenu[:2000]}"
        )

    def test_liste_ventes_multi_lignes_qty(self):
        """
        Une transaction = 2 lignes (pinte qty=3 a 5€, demi qty=2 a 3€).
        Total reel = 15 + 6 = 21€. Verifie que le total agrege est correct.
        / One transaction = 2 lines; real total 21€.
        """
        # 3 × 500 + 2 × 300 = 2100 centimes = 21,00 €.
        # / 3 × 500 + 2 × 300 = 2100 cents.
        self._vendre_en_especes([
            (self.tarif_de_la_pinte, 500, 3),
            (self.tarif_du_demi, 300, 2),
        ])

        response = self.client_http.get(
            f'/laboutik/caisse/liste-ventes/?pv={self.point_de_vente.uuid}'
            f'&moyen={PaymentMethod.CASH}'
        )

        assert response.status_code == 200
        contenu = response.content.decode('utf-8')
        assert '21,00' in contenu, (
            "Total devrait inclure 21,00 € (3*5 + 2*3), regression du bug 4."
        )

    def test_recap_boutons_fond_et_sortie_de_caisse_gardent_les_params(self):
        """
        Le Ticket X doit passer les 3 params aux boutons Fond de caisse et Sortie de caisse.
        / Ticket X must pass the 3 params to the Cash float and Cash withdrawal buttons.
        """
        self._vendre_en_especes([(self.tarif_de_la_pinte, 500, 1)])

        response = self.client_http.get(
            f'/laboutik/caisse/recap-en-cours/?vue=toutes&uuid_pv={self.point_de_vente.uuid}'
            f'&tag_id_cm={TAG_ID_CM_DE_TEST}&type_app={TYPE_APP_DE_TEST}'
        )

        assert response.status_code == 200
        contenu = response.content.decode('utf-8')
        # Les params sont HTML-echappes dans les attributs (& devient &amp;)
        # / Params are HTML-escaped in attributes (& becomes &amp;)
        params_attendus = (
            f'uuid_pv={self.point_de_vente.uuid}&amp;tag_id_cm={TAG_ID_CM_DE_TEST}'
            f'&amp;type_app={TYPE_APP_DE_TEST}'
        )
        assert f'/laboutik/caisse/fond-de-caisse/?{params_attendus}' in contenu
        assert f'/laboutik/caisse/sortie-de-caisse/?{params_attendus}' in contenu
        # Les onglets (hx-push-url) gardent aussi type_app
        # / Tabs (hx-push-url) also keep type_app
        assert f'?vue=par_moyen&{params_attendus}' in contenu
