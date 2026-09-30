"""
tests/pytest/test_cloture_caisse.py — Tests Phase 5 : cloture de caisse.
tests/pytest/test_cloture_caisse.py — Tests Phase 5: cash register closure.

Couvre : ClotureCaisse, cloturer(), totaux, fermeture tables, rapport JSON.
Covers: ClotureCaisse, cloturer(), totals, table closure, JSON report.

SCHÉMA DÉDIÉ
La clôture couvre TOUT le lieu, depuis la dernière clôture du point de vente. Elle
compte toutes les lignes de caisse du lieu, et toutes ses sorties d'espèces. Sur la
base de dev partagée, elle compterait aussi ce que d'autres tests y ont laissé. Ce
fichier tourne donc dans un lieu qui ne contient que ses propres ventes
(`FastTenantTestCase`, tronc §8.5 du chantier 05). Chaque test annule sa transaction à
la fin : rien n'arrive dans la base de dev, et les totaux se vérifient à l'égalité.
/ Dedicated schema: the closure covers the whole venue, so it runs in a venue that only
holds this file's sales. Each test rolls back: nothing reaches the dev database.

Lancement / Run:
    make test ARGS="tests/pytest/test_cloture_caisse.py"
"""

import sys

# Le code Django est dans /DjangoFiles a l'interieur du conteneur.
# / Django code is in /DjangoFiles inside the container.
sys.path.insert(0, '/DjangoFiles')


import django

django.setup()

from decimal import Decimal  # noqa: E402

from django.db import connection  # noqa: E402
from django_tenants.test.cases import FastTenantTestCase  # noqa: E402
from django_tenants.test.client import TenantClient  # noqa: E402

from AuthBillet.models import TibilletUser  # noqa: E402
from BaseBillet.models import (  # noqa: E402
    CategorieProduct, Configuration, LigneArticle, PaymentMethod, Price, PriceSold,
    Product, ProductSold, SaleOrigin,
)
from laboutik.models import (  # noqa: E402
    ClotureCaisse, CommandeSauvegarde, PointDeVente, Table,
)


# Adresse de la clôture au comptoir (laboutik/urls.py).
# / Counter closure address.
URL_DE_LA_CLOTURE = '/laboutik/caisse/cloturer/'


def _creer_ligne_article_directe(produit, prix, montant_centimes, payment_method_code, dt=None, pv=None):
    """
    Cree une LigneArticle directement en base (sans passer par la vue).
    Creates a LigneArticle directly in DB (without going through the view).

    :param produit: Product
    :param prix: Price
    :param montant_centimes: int en centimes
    :param payment_method_code: PaymentMethod.CASH, .CC, .LOCAL_EURO, etc.
    :param dt: datetime optionnel (None = maintenant)
    :param pv: PointDeVente optionnel (None = pas de PV)
    """
    # ProductSold : snapshot du produit
    # / Product snapshot
    product_sold, _product_sold_cree = ProductSold.objects.get_or_create(
        product=produit,
        event=None,
        defaults={'categorie_article': produit.categorie_article},
    )
    # PriceSold : snapshot du prix
    # / Price snapshot
    price_sold, _price_sold_cree = PriceSold.objects.get_or_create(
        productsold=product_sold,
        price=prix,
        defaults={'prix': prix.prix},
    )
    ligne = LigneArticle.objects.create(
        pricesold=price_sold,
        qty=1,
        amount=montant_centimes,
        sale_origin=SaleOrigin.LABOUTIK,
        payment_method=payment_method_code,
        status=LigneArticle.VALID,
        point_de_vente=pv,
    )
    # Mettre a jour le datetime si specifie (auto_now_add ne permet pas de le setter)
    # / Update datetime if specified (auto_now_add prevents setting it)
    if dt is not None:
        LigneArticle.objects.filter(pk=ligne.pk).update(datetime=dt)
    return ligne


class TestClotureCaisse(FastTenantTestCase):
    """
    La clôture journalière déclenchée au comptoir, dans un lieu de test isolé.
    / The daily closure triggered at the counter, in an isolated test venue.
    """

    # Schéma et domaine propres à ce fichier : deux fichiers qui partageraient le même
    # schéma se marcheraient dessus. `Client.name` est unique et obligatoire.
    # / Schema and domain specific to this file. Client.name is unique and required.
    @classmethod
    def get_test_schema_name(cls):
        return 'test_cloture_caisse'

    @classmethod
    def get_test_tenant_domain(cls):
        return 'test-cloture-caisse.tibillet.localhost'

    @classmethod
    def setup_tenant(cls, tenant):
        """Champ requis sur Client. / Required field on Client."""
        tenant.name = 'Test Cloture Caisse'

    def setUp(self):
        """
        Un comptoir, un produit vendu en caisse avec son tarif, un admin connecté.
        / A counter, a register product with its price, a logged-in admin.
        """
        # Le rollback du test précédent a rendu le `search_path` au public.
        # / The previous test's rollback returned the search_path to public.
        connection.set_tenant(self.tenant)

        # Les routes de la caisse sont gardées par `module_caisse`, qui exige
        # `module_monnaie_locale`. Schéma dédié : on peut enregistrer la
        # configuration de CE lieu de test.
        # / Register routes are guarded by module_caisse, which requires
        # module_monnaie_locale. Dedicated schema: this venue's config can be saved.
        configuration = Configuration.get_solo()
        configuration.module_monnaie_locale = True
        configuration.module_caisse = True
        configuration.save()

        categorie = CategorieProduct.objects.create(name='Boissons test cloture')
        self.produit = Product.objects.create(
            name='Biere test cloture',
            categorie_article=Product.VENTE,
            methode_caisse=Product.VENTE,
            categorie_pos=categorie,
            publish=True,
        )
        self.prix = Price.objects.create(
            product=self.produit,
            name='Pinte',
            prix=Decimal('5.00'),
            publish=True,
        )
        self.point_de_vente = PointDeVente.objects.create(
            name='Comptoir test cloture',
            comportement=PointDeVente.DIRECT,
            service_direct=True,
            accepte_especes=True,
            accepte_carte_bancaire=True,
        )
        self.point_de_vente.products.add(self.produit)

        # `TibilletUser` vit dans le schéma public (SHARED_APPS). Il est créé dans la
        # transaction du test, donc annulé avec elle.
        # / TibilletUser lives in the public schema; created inside the test's
        # transaction, so rolled back with it.
        self.admin, _admin_cree = TibilletUser.objects.get_or_create(
            email='admin-test-cloture@tibillet.localhost',
            defaults={
                'username': 'admin-test-cloture@tibillet.localhost',
                'is_staff': True,
                'is_active': True,
            },
        )
        self.admin.client_admin.add(self.tenant)

        # Client HTTP routé vers le lieu de test, avec la session de l'admin.
        # / HTTP client routed to the test venue, with the admin session.
        self.client_http = TenantClient(self.tenant)
        self.client_http.force_login(self.admin)

        self.post_data = {'uuid_pv': str(self.point_de_vente.uuid)}

    def test_cloture_totaux_corrects(self):
        """
        Setup : creer 3 LigneArticle (1 espece 500c, 1 CB 1000c, 1 NFC 2000c).
        Action : cloturer().
        Verify : total_especes=500, total_cb=1000, total_nfc=2000, total_general=3500.
        """
        # Creer les 3 LigneArticle
        # / Create the 3 LigneArticle
        _creer_ligne_article_directe(self.produit, self.prix, 500, PaymentMethod.CASH)
        _creer_ligne_article_directe(self.produit, self.prix, 1000, PaymentMethod.CC)
        _creer_ligne_article_directe(self.produit, self.prix, 2000, PaymentMethod.LOCAL_EURO)

        # Appeler l'endpoint de cloture (datetime_ouverture est calcule automatiquement)
        # / Call the closure endpoint (datetime_ouverture is computed automatically)
        response = self.client_http.post(URL_DE_LA_CLOTURE, data=self.post_data)
        assert response.status_code == 200

        # Verifier que la ClotureCaisse a ete creee
        # / Verify that ClotureCaisse was created
        cloture = ClotureCaisse.objects.order_by('-datetime_cloture').first()
        assert cloture is not None
        assert cloture.total_especes == 500
        assert cloture.total_carte_bancaire == 1000
        assert cloture.total_cashless == 2000
        assert cloture.total_general == 3500

    def test_cloture_nombre_transactions(self):
        """
        Verify : nombre_transactions compte les lignes de la periode.
        """
        _creer_ligne_article_directe(self.produit, self.prix, 100, PaymentMethod.CASH)
        _creer_ligne_article_directe(self.produit, self.prix, 200, PaymentMethod.CC)
        _creer_ligne_article_directe(self.produit, self.prix, 300, PaymentMethod.LOCAL_EURO)

        response = self.client_http.post(URL_DE_LA_CLOTURE, data=self.post_data)
        assert response.status_code == 200

        cloture = ClotureCaisse.objects.order_by('-datetime_cloture').first()
        assert cloture is not None
        assert cloture.nombre_transactions == 3

    def test_cloture_ferme_tables(self):
        """
        Setup : 2 tables OCCUPEE + 1 vente (pour que la cloture ait quelque chose a cloturer).
        Action : cloturer().
        Verify : les 2 tables passent a LIBRE.
        """
        # Creer 2 tables OCCUPEE pour le test
        # / Create 2 OCCUPIED tables for the test
        table1 = Table.objects.create(name='Test Cloture T1', statut=Table.OCCUPEE)
        table2 = Table.objects.create(name='Test Cloture T2', statut=Table.OCCUPEE)

        # Il faut au moins une vente pour que la cloture fonctionne
        # / Need at least one sale for the closure to work
        _creer_ligne_article_directe(self.produit, self.prix, 100, PaymentMethod.CASH)

        response = self.client_http.post(URL_DE_LA_CLOTURE, data=self.post_data)
        assert response.status_code == 200

        # Recharger depuis la DB
        # / Reload from DB
        table1.refresh_from_db()
        table2.refresh_from_db()
        assert table1.statut == Table.LIBRE
        assert table2.statut == Table.LIBRE

    def test_cloture_rapport_json_complet(self):
        """
        Verify : rapport_json contient par_categorie, par_produit, par_moyen_paiement.
        """
        _creer_ligne_article_directe(self.produit, self.prix, 500, PaymentMethod.CASH)

        response = self.client_http.post(URL_DE_LA_CLOTURE, data=self.post_data)
        assert response.status_code == 200

        cloture = ClotureCaisse.objects.order_by('-datetime_cloture').first()
        assert cloture is not None
        rapport = cloture.rapport_json

        # Les 15 cles du RapportComptableService
        # / The 15 keys from RapportComptableService
        assert 'totaux_par_moyen' in rapport
        assert 'detail_ventes' in rapport
        assert 'offerts' in rapport
        assert 'non_monetaire' in rapport
        assert 'tva' in rapport
        assert 'solde_caisse' in rapport
        assert 'recharges' in rapport
        assert 'adhesions' in rapport
        assert 'remboursements' in rapport
        assert 'habitus' in rapport
        assert 'billets' in rapport
        assert 'synthese_operations' in rapport
        assert 'operateurs' in rapport
        assert 'ventilation_par_pv' in rapport
        assert 'infos_legales' in rapport

        # Verifier la structure totaux_par_moyen
        # / Verify totaux_par_moyen structure
        totaux = rapport['totaux_par_moyen']
        assert 'especes' in totaux
        assert 'carte_bancaire' in totaux
        assert 'cashless' in totaux

        # Verifier la structure TVA
        # / Verify TVA structure
        tva = rapport['tva']
        assert isinstance(tva, dict)
        for cle_taux, donnees_tva in tva.items():
            assert 'taux' in donnees_tva
            assert 'total_ttc' in donnees_tva
            assert 'total_ht' in donnees_tva
            assert 'total_tva' in donnees_tva

    def test_cloture_datetime_ouverture_auto(self):
        """
        Setup : creer une vente.
        Action : cloturer (sans datetime_ouverture dans le POST).
        Verify : la cloture a bien un datetime_ouverture et contient la vente.
        """
        # Creer une LigneArticle
        # / Create a LigneArticle
        _creer_ligne_article_directe(self.produit, self.prix, 777, PaymentMethod.CASH)

        response = self.client_http.post(URL_DE_LA_CLOTURE, data=self.post_data)
        assert response.status_code == 200

        # La cloture doit exister avec datetime_ouverture renseigne
        # / The closure must exist with datetime_ouverture set
        cloture = ClotureCaisse.objects.order_by('-datetime_cloture').first()
        assert cloture is not None
        assert cloture.datetime_ouverture is not None
        assert cloture.datetime_ouverture < cloture.datetime_cloture
        assert cloture.nombre_transactions == 1

    def test_double_cloture_meme_periode(self):
        """
        Action : cloturer 2 fois la meme periode.
        Verify : 2 ClotureCaisse creees.
        """
        _creer_ligne_article_directe(self.produit, self.prix, 100, PaymentMethod.CASH)

        nb_clotures_avant = ClotureCaisse.objects.count()

        # Premiere cloture
        # / First closure
        response1 = self.client_http.post(URL_DE_LA_CLOTURE, data=self.post_data)
        assert response1.status_code == 200

        # Creer une nouvelle vente pour la 2eme cloture
        # / Create a new sale for the 2nd closure
        _creer_ligne_article_directe(self.produit, self.prix, 200, PaymentMethod.CC)

        # Deuxieme cloture
        # / Second closure
        response2 = self.client_http.post(URL_DE_LA_CLOTURE, data=self.post_data)
        assert response2.status_code == 200

        # Verifier que 2 nouvelles clotures ont ete creees
        # / Verify that 2 new closures were created
        nb_clotures_apres = ClotureCaisse.objects.count()
        assert nb_clotures_apres == nb_clotures_avant + 2

    def test_cloture_annule_commandes_ouvertes(self):
        """
        Setup : 1 commande OPEN + 1 vente.
        Action : cloturer().
        Verify : la commande passe a CANCEL.
        """
        # Creer une commande OPEN pour le test
        # / Create an OPEN order for the test
        commande = CommandeSauvegarde.objects.create(
            statut=CommandeSauvegarde.OPEN,
            commentaire='Test cloture phase 5',
        )

        # Il faut au moins une vente pour que la cloture fonctionne
        # / Need at least one sale for the closure to work
        _creer_ligne_article_directe(self.produit, self.prix, 100, PaymentMethod.CASH)

        response = self.client_http.post(URL_DE_LA_CLOTURE, data=self.post_data)
        assert response.status_code == 200

        # Recharger la commande
        # / Reload the order
        commande.refresh_from_db()
        assert commande.statut == CommandeSauvegarde.CANCEL
