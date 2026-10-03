"""
Tests pour comptabilite/services.py — RapportComptableService.
/ Tests for comptabilite/services.py — RapportComptableService.

LOCALISATION : tests/pytest/test_comptabilite_service.py

SCHÉMA DÉDIÉ
Le service lit les rapports du LIEU ENTIER sur une fenêtre de temps. Sur la base de dev
partagée, cette fenêtre contiendrait aussi ce que d'autres tests y ont laissé (avoirs
Stripe, ventes de l'API, serveur de dev). Ce fichier tourne donc dans un lieu qui ne
contient que ses propres lignes (`FastTenantTestCase`, tronc §8.5 du chantier 05).
Chaque test annule sa transaction à la fin : rien n'arrive dans la base de dev, et les
totaux se vérifient à l'égalité, sans « avant / après ».
/ Dedicated schema: the service reads the WHOLE venue over a time window, so this file
runs in a venue that only holds its own lines. Each test rolls back: nothing reaches the
dev database, and totals are asserted exactly, with no before/after delta.

Lancement / Run:
    make test ARGS="tests/pytest/test_comptabilite_service.py"
"""
import sys
import uuid
from datetime import timedelta
from decimal import Decimal

# Le code Django est dans /DjangoFiles a l'interieur du conteneur.
# / Django code is in /DjangoFiles inside the container.
sys.path.insert(0, '/DjangoFiles')

import django  # noqa: E402

django.setup()

from django.db import connection  # noqa: E402
from django.utils import timezone  # noqa: E402
from django_tenants.test.cases import FastTenantTestCase  # noqa: E402

from AuthBillet.models import TibilletUser  # noqa: E402
from BaseBillet.models import (  # noqa: E402
    Event, LigneArticle, Membership, PaymentMethod, Price, PriceSold, Product,
    ProductSold, Reservation, SaleOrigin,
)
from comptabilite.services import RapportComptableService  # noqa: E402


def _creer_ligne(**kwargs):
    """
    Cree une LigneArticle minimale dans le lieu de test courant.
    / Create a minimal LigneArticle in the current test venue.

    Defaults : amount=1000c, qty=1, status=VALID, payment_method=CASH,
    sale_origin=LESPASS, vat=0. Chaque appel cree son propre produit (nom unique),
    sauf si `pricesold` est passe.
    / Each call creates its own product (unique name), unless `pricesold` is given.
    """
    suffix = uuid.uuid4().hex[:8]
    product, _product_cree = Product.objects.get_or_create(
        name=f"TestProduct_{suffix}",
        defaults={"categorie_article": Product.BILLET},
    )
    price, _price_cree = Price.objects.get_or_create(
        product=product,
        name=f"TestPrice_{suffix}",
        defaults={"prix": Decimal("10.00")},
    )
    productsold, _productsold_cree = ProductSold.objects.get_or_create(
        product=product,
        categorie_article=product.categorie_article,
    )
    pricesold, _pricesold_cree = PriceSold.objects.get_or_create(
        productsold=productsold,
        price=price,
        defaults={"prix": Decimal("10.00")},
    )

    defaults = {
        "amount": 1000,
        "qty": Decimal("1"),
        "status": LigneArticle.VALID,
        "payment_method": PaymentMethod.CASH,
        "sale_origin": SaleOrigin.LESPASS,
        "vat": Decimal("0"),
        "pricesold": pricesold,
    }
    defaults.update(kwargs)
    return LigneArticle.objects.create(**defaults)


class TestRapportComptableService(FastTenantTestCase):
    """
    Les calculs du rapport comptable, dans un lieu de test isolé.
    / The accounting report computations, in an isolated test venue.
    """

    # Schéma et domaine propres à ce fichier : deux fichiers qui partageraient le même
    # schéma se marcheraient dessus. `Client.name` est unique et obligatoire.
    # / Schema and domain specific to this file. Client.name is unique and required.
    @classmethod
    def get_test_schema_name(cls):
        return 'test_comptabilite_service'

    @classmethod
    def get_test_tenant_domain(cls):
        return 'test-comptabilite-service.tibillet.localhost'

    @classmethod
    def setup_tenant(cls, tenant):
        """Champ requis sur Client. / Required field on Client."""
        tenant.name = 'Test Comptabilite Service'

    def setUp(self):
        """
        Se place dans le lieu de test et ouvre une fenêtre de 5 minutes autour de maintenant.
        / Switch to the test venue and open a 5-minute window around now.
        """
        # Le rollback du test précédent a rendu le `search_path` au public.
        # / The previous test's rollback returned the search_path to public.
        connection.set_tenant(self.tenant)

        self.fin = timezone.now() + timedelta(seconds=10)
        self.debut = self.fin - timedelta(minutes=5)

    # -----------------------------------------------------------------------
    # Tests B1
    # -----------------------------------------------------------------------

    def test_service_instanciation_ok(self):
        """
        Le service s'instancie sans erreur et expose un queryset.
        / The service instantiates without error and exposes a queryset.
        """
        from django.db.models import QuerySet
        service = RapportComptableService(self.debut, self.fin)
        assert isinstance(service.queryset, QuerySet)
        assert service.datetime_debut == self.debut
        assert service.datetime_fin == self.fin

    def test_base_queryset_filtre_status(self):
        """
        Le queryset de base ne garde que V/P/F/N (exclut UNPAID, CANCELED, etc.).
        / Base queryset only keeps V/P/F/N (excludes UNPAID, CANCELED, etc.).
        """
        l_valid = _creer_ligne(status=LigneArticle.VALID)
        l_paid = _creer_ligne(status=LigneArticle.PAID)
        _creer_ligne(status=LigneArticle.UNPAID)
        _creer_ligne(status=LigneArticle.CANCELED)

        service = RapportComptableService(self.debut, self.fin)
        pks_dans_qs = set(service.queryset.values_list("pk", flat=True))

        # Le lieu ne contient que nos 4 lignes : on attend exactement les 2 valides.
        # / The venue only holds our 4 lines: exactly the 2 valid ones are expected.
        assert pks_dans_qs == {l_valid.pk, l_paid.pk}

    def test_base_queryset_exclut_laboutik(self):
        """
        Une ligne avec sale_origin=LABOUTIK n'entre PAS dans le queryset V1.
        / A line with sale_origin=LABOUTIK is excluded from the V1 queryset.
        """
        l_lespass = _creer_ligne(sale_origin=SaleOrigin.LESPASS)
        _creer_ligne(sale_origin=SaleOrigin.LABOUTIK)

        service = RapportComptableService(self.debut, self.fin)
        pks_dans_qs = set(service.queryset.values_list("pk", flat=True))

        assert pks_dans_qs == {l_lespass.pk}

    def test_calculer_totaux_par_moyen_basique(self):
        """
        3 lignes (CASH 1000c, CC 2000c, STRIPE_FED 500c) → dict avec 3 cles +
        total + currency_code.
        / 3 lines (CASH 1000c, CC 2000c, STRIPE_FED 500c) → dict with 3 keys + total.
        """
        _creer_ligne(amount=1000, payment_method=PaymentMethod.CASH)
        _creer_ligne(amount=2000, payment_method=PaymentMethod.CC)
        _creer_ligne(amount=500, payment_method=PaymentMethod.STRIPE_FED)

        rapport = RapportComptableService(self.debut, self.fin).calculer_totaux_par_moyen()

        assert "CA" in rapport  # CASH code
        assert "CC" in rapport
        assert "SF" in rapport  # STRIPE_FED code
        assert rapport["CA"]["total"] == 1000
        assert rapport["CA"]["nb"] == 1
        assert rapport["CC"]["total"] == 2000
        assert rapport["SF"]["total"] == 500
        assert rapport["total"] == 3500
        assert rapport["currency_code"] == "EUR"

    def test_calculer_totaux_par_moyen_avec_qty_decimal(self):
        """
        Une ligne amount=1000c, qty=2 doit produire un total=2000c (Sum F*F).
        / A line amount=1000c, qty=2 must produce total=2000c (Sum F*F).
        """
        _creer_ligne(
            amount=1000,
            qty=Decimal("2"),
            payment_method=PaymentMethod.CASH,
        )

        rapport = RapportComptableService(self.debut, self.fin).calculer_totaux_par_moyen()

        # CASH code = 'CA'
        assert rapport["CA"]["total"] == 2000
        assert rapport["total"] == 2000

    # -----------------------------------------------------------------------
    # Tests B2 — TVA, remboursements, adhesions, billets, detail ventes
    # -----------------------------------------------------------------------

    def test_calculer_tva_par_taux(self):
        """
        2 lignes (vat=5.5%, vat=20%) → dict avec 2 cles "5.50" et "20.00".
        Chaque cle contient {taux, total_ttc, total_ht, total_tva}.
        / 2 lines (vat=5.5%, 20%) → dict with 2 keys "5.50" and "20.00".
        """
        _creer_ligne(amount=1055, vat=Decimal("5.5"))  # TTC 10.55
        _creer_ligne(amount=1200, vat=Decimal("20"))   # TTC 12.00

        rapport = RapportComptableService(self.debut, self.fin).calculer_tva()

        assert "5.50" in rapport
        assert "20.00" in rapport

        # 5.5% : ht = round(1055 * 100 / 105.5) = 1000, tva = 55
        assert rapport["5.50"]["total_ttc"] == 1055
        assert rapport["5.50"]["total_ht"] == 1000
        assert rapport["5.50"]["total_tva"] == 55

        # 20% : ht = round(1200 * 100 / 120) = 1000, tva = 200
        assert rapport["20.00"]["total_ttc"] == 1200
        assert rapport["20.00"]["total_ht"] == 1000
        assert rapport["20.00"]["total_tva"] == 200

    def test_calculer_remboursements_status_negatifs(self):
        """
        Une CREDIT_NOTE et une REFUNDED → dict avec credit_notes + refunded.
        / A CREDIT_NOTE and a REFUNDED → dict with credit_notes + refunded sub-keys.
        """
        _creer_ligne(amount=-500, status=LigneArticle.CREDIT_NOTE)
        _creer_ligne(amount=-300, status=LigneArticle.REFUNDED)

        rapport = RapportComptableService(self.debut, self.fin).calculer_remboursements()

        assert "credit_notes" in rapport
        assert "refunded" in rapport
        assert rapport["credit_notes"]["total"] == -500
        assert rapport["credit_notes"]["nb"] == 1
        assert rapport["refunded"]["total"] == -300
        assert rapport["refunded"]["nb"] == 1

    def test_calculer_adhesions_avec_membership(self):
        """
        1 ligne avec membership → dict 'detail' avec cle composite + total + nb.
        / 1 line with membership → dict with composite key + total + nb.
        """
        # Un user, un produit adhesion + prix, puis une Membership.
        # / A user, a membership product + price, then a Membership.
        suffix = uuid.uuid4().hex[:8]
        user, _user_cree = TibilletUser.objects.get_or_create(
            email=f"test_adh_{suffix}@example.com",
            defaults={"is_active": True, "username": f"test_adh_{suffix}"},
        )
        product, _product_cree = Product.objects.get_or_create(
            name=f"Adh_{suffix}",
            defaults={"categorie_article": Product.ADHESION},
        )
        price, _price_cree = Price.objects.get_or_create(
            product=product,
            name=f"Tarif_{suffix}",
            defaults={"prix": Decimal("15.00")},
        )
        productsold, _productsold_cree = ProductSold.objects.get_or_create(
            product=product,
            categorie_article=product.categorie_article,
        )
        pricesold, _pricesold_cree = PriceSold.objects.get_or_create(
            productsold=productsold, price=price,
            defaults={"prix": Decimal("15.00")},
        )
        membership = Membership.objects.create(
            user=user,
            price=price,
            contribution_value=Decimal("15.00"),
        )

        LigneArticle.objects.create(
            amount=1500, qty=Decimal("1"),
            status=LigneArticle.VALID,
            payment_method=PaymentMethod.STRIPE_FED,
            pricesold=pricesold,
            membership=membership,
        )

        rapport = RapportComptableService(self.debut, self.fin).calculer_detail_ventes()

        # Structure detail_ventes : cat_code -> {nom_categorie, articles: [{...}], total_ttc}
        # / detail_ventes structure: cat_code -> {nom_categorie, articles, total_ttc}
        assert "A" in rapport, "La categorie ADHESION (A) doit etre presente"
        cat_adh = rapport["A"]
        assert cat_adh["total_ttc"] == 1500
        # On retrouve notre produit dans la liste d'articles de la categorie
        # / Locate our product in the category's articles list
        articles_du_produit = [a for a in cat_adh["articles"] if a["nom_produit"] == product.name]
        assert len(articles_du_produit) == 1
        article = articles_du_produit[0]
        assert article["total_ttc"] == 1500
        assert article["qty_total"] == 1.0

    def test_calculer_billets_avec_reservation(self):
        """
        1 ligne avec reservation+event → dict 'detail' avec cle composite event/produit/tarif.
        / 1 line with reservation+event → dict with composite key event/produit/tarif.
        """
        suffix = uuid.uuid4().hex[:8]
        user, _user_cree = TibilletUser.objects.get_or_create(
            email=f"test_bil_{suffix}@example.com",
            defaults={"is_active": True, "username": f"test_bil_{suffix}"},
        )
        event = Event.objects.create(
            name=f"Concert_{suffix}",
            datetime=timezone.now() + timedelta(days=10),
        )
        product, _product_cree = Product.objects.get_or_create(
            name=f"Billet_{suffix}",
            defaults={"categorie_article": Product.BILLET},
        )
        price, _price_cree = Price.objects.get_or_create(
            product=product, name=f"Plein_{suffix}",
            defaults={"prix": Decimal("20.00")},
        )
        productsold, _productsold_cree = ProductSold.objects.get_or_create(
            product=product,
            categorie_article=product.categorie_article,
        )
        pricesold, _pricesold_cree = PriceSold.objects.get_or_create(
            productsold=productsold, price=price,
            defaults={"prix": Decimal("20.00")},
        )
        reservation = Reservation.objects.create(
            user_commande=user,
            event=event,
        )

        LigneArticle.objects.create(
            amount=2000, qty=Decimal("1"),
            status=LigneArticle.VALID,
            payment_method=PaymentMethod.STRIPE_FED,
            pricesold=pricesold,
            reservation=reservation,
        )

        rapport = RapportComptableService(self.debut, self.fin).calculer_detail_ventes()

        # Structure detail_ventes : cat_code -> {nom_categorie, articles, total_ttc}
        # / detail_ventes structure: cat_code -> {nom_categorie, articles, total_ttc}
        assert "B" in rapport, "La categorie BILLET (B) doit etre presente"
        cat_billet = rapport["B"]
        assert cat_billet["total_ttc"] == 2000
        articles_du_produit = [a for a in cat_billet["articles"] if a["nom_produit"] == product.name]
        assert len(articles_du_produit) == 1
        article = articles_du_produit[0]
        assert article["total_ttc"] == 2000
        assert article["qty_total"] == 1.0

    def test_calculer_detail_ventes_groupe_par_categorie(self):
        """
        Plusieurs lignes (BILLET + ADHESION) groupees par categorie d'article.
        / Multiple lines grouped by article category.
        """
        # 1 BILLET payant
        l_billet = _creer_ligne(
            amount=1000, qty=Decimal("1"),
            payment_method=PaymentMethod.STRIPE_FED, vat=Decimal("20"),
        )
        # 1 ligne offerte du meme type (vat=0)
        _creer_ligne(
            amount=0, qty=Decimal("1"),
            payment_method=PaymentMethod.FREE, vat=Decimal("0"),
            pricesold=l_billet.pricesold,  # meme produit pour grouper
        )

        rapport = RapportComptableService(self.debut, self.fin).calculer_detail_ventes()

        # La categorie est BILLET (defaut de _creer_ligne)
        assert Product.BILLET in rapport
        cat = rapport[Product.BILLET]
        assert isinstance(cat["articles"], list)
        # Le lieu ne contient que ce produit : la categorie a exactement 1 article.
        # / The venue only holds this product: the category has exactly 1 article.
        assert len(cat["articles"]) == 1
        article = cat["articles"][0]
        assert article["nom_produit"] == l_billet.pricesold.productsold.product.name
        assert article["qty_payants"] == 1.0
        assert article["qty_offerts"] == 1.0
        assert article["qty_total"] == 2.0
        assert article["total_ttc"] == 1000  # seul l_billet contribue (l_offert est 0)
        assert cat["total_ttc"] == 1000
        # Verifier qu'au moins total_ht et total_tva sont des int
        assert isinstance(article["total_ht"], int)
        assert isinstance(article["total_tva"], int)

    def test_calculer_detail_ventes_prix_libre_amount_zero_compte_comme_offert(self):
        """
        Cas du tarif "prix libre a partir de 0" : un user paye 10€, un autre 20€,
        un troisieme 0€. Tous gardent payment_method=STRIPE_NOFED car le code
        de creation de LigneArticle (validators.py:294) assigne ce mode par defaut
        pour TOUTES les lignes de reservation, meme a 0€.

        Sans le patch Q(amount=0) sur offert_flag, la vente a 0€ apparaitrait
        en "payants" (et serait invisible : qty=3, total=30€, offerts=0).
        Avec le patch : qty_payants=2, qty_offerts=1, total_ttc=30€.

        Verifie egalement qu'on reste sur UNE SEULE requete SQL (pas de N+1).

        / Free-priced tariff at 0: 3 sales (10€, 20€, 0€) all with STRIPE_NOFED.
        / Without the Q(amount=0) patch, the 0€ sale would land in 'payants' and
        / be invisible. With the patch: payants=2, offerts=1.
        / Also asserts only ONE SQL query (no N+1).
        """
        # 3 lignes sur le MEME pricesold (meme tarif prix libre)
        # / 3 lines on the SAME pricesold (same open-price tariff)
        l_10 = _creer_ligne(
            amount=1000, qty=Decimal("1"),
            payment_method=PaymentMethod.STRIPE_NOFED, vat=Decimal("0"),
        )
        _creer_ligne(
            amount=2000, qty=Decimal("1"),
            payment_method=PaymentMethod.STRIPE_NOFED, vat=Decimal("0"),
            pricesold=l_10.pricesold,
        )
        _creer_ligne(
            amount=0, qty=Decimal("1"),
            payment_method=PaymentMethod.STRIPE_NOFED, vat=Decimal("0"),
            pricesold=l_10.pricesold,
        )

        service = RapportComptableService(self.debut, self.fin)

        # On verifie qu'une seule requete SQL est emise par calculer_detail_ventes
        # (le CASE WHEN reste cote serveur — pas de N+1)
        # / Assert only one SQL query is emitted (CASE WHEN stays server-side)
        with self.assertNumQueries(1):
            rapport = service.calculer_detail_ventes()

        assert Product.BILLET in rapport
        cat = rapport[Product.BILLET]
        # Le lieu ne contient que ce produit : la categorie a exactement 1 article.
        # / The venue only holds this product: the category has exactly 1 article.
        assert len(cat["articles"]) == 1
        article = cat["articles"][0]
        assert article["nom_produit"] == l_10.pricesold.productsold.product.name

        # 2 payants (10€ + 20€), 1 offert (0€)
        # / 2 paid (10€ + 20€), 1 offered (0€)
        assert article["qty_payants"] == 2.0
        assert article["qty_offerts"] == 1.0
        assert article["qty_total"] == 3.0
        # TTC = 30€ (la vente a 0 n'apporte rien)
        assert article["total_ttc"] == 3000

    # -----------------------------------------------------------------------
    # Tests B3 — synthese, infos legales, hash, rapport complet
    # -----------------------------------------------------------------------

    def test_calculer_infos_legales_depuis_configuration(self):
        """
        Recupere les infos legales depuis Configuration.get_solo().
        / Recovers legal info from Configuration singleton.
        """
        infos = RapportComptableService(self.debut, self.fin).calculer_infos_legales()

        # 8 cles attendues
        for k in ("organisation", "adresse", "code_postal", "ville",
                  "siren", "tva_number", "email", "phone"):
            assert k in infos, f"Cle manquante : {k}"
            assert isinstance(infos[k], str), f"{k} doit etre str (vide ou non)"

    def test_calculer_hash_lignes_stable_et_change_avec_modif(self):
        """
        Meme queryset → meme hash. Modifier une ligne → hash different.
        / Same queryset → same hash. Modify a line → hash changes.
        """
        ligne = _creer_ligne(amount=1500)

        hash1 = RapportComptableService(self.debut, self.fin).calculer_hash_lignes()
        hash2 = RapportComptableService(self.debut, self.fin).calculer_hash_lignes()
        assert hash1 == hash2, "Meme queryset doit produire le meme hash"
        assert len(hash1) == 64, "SHA-256 hex = 64 chars"

        ligne.amount = 9999
        ligne.save()

        hash3 = RapportComptableService(self.debut, self.fin).calculer_hash_lignes()
        assert hash3 != hash1, "Modification d'une ligne doit changer le hash"

    def test_generer_rapport_complet_structure(self):
        """
        generer_rapport_complet() retourne dict avec EXACTEMENT 6 cles racine.
        / Returns dict with EXACTLY 6 root keys.
        """
        rapport = RapportComptableService(self.debut, self.fin).generer_rapport_complet()

        cles_attendues = {
            "totaux_par_moyen", "tva", "detail_ventes",
            "remboursements", "infos_legales", "meta",
        }
        assert set(rapport.keys()) == cles_attendues, (
            f"Cles inattendues. Reel : {set(rapport.keys())}"
        )
        # Verifier les 3 cles de meta
        assert "datetime_debut" in rapport["meta"]
        assert "datetime_fin" in rapport["meta"]
        assert "schema" in rapport["meta"]

    def test_generer_rapport_complet_serialisable_json(self):
        """
        json.dumps(rapport) doit fonctionner sans erreur.
        / json.dumps(rapport) must work without error.
        """
        import json
        _creer_ligne(amount=1000, vat=Decimal("20"))

        rapport = RapportComptableService(self.debut, self.fin).generer_rapport_complet()

        # Doit etre serialisable JSON sans crash
        payload = json.dumps(rapport)
        assert isinstance(payload, str)
        assert len(payload) > 100  # contenu non vide
