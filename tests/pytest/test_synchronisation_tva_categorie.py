"""
tests/pytest/test_synchronisation_tva_categorie.py
Admin d'une categorie de caisse : bouton « Synchroniser la TVA ».
/ POS category admin: "Synchronize VAT" button.

LOCALISATION : tests/pytest/test_synchronisation_tva_categorie.py

CE QUI EST TESTE / WHAT IS TESTED
---------------------------------
Une categorie de caisse a une TVA par defaut, mais la TVA d'une vente vient de
l'ARTICLE (Product.tva), jamais de sa categorie. Le bouton de la fiche categorie
donne la TVA de la categorie a TOUS ses articles, apres une confirmation qui
explique l'effet (ventes deja enregistrees inchangees) et liste les articles qui
changent. Les articles des autres categories ne bougent pas.

Schema de test dedie : l'admin du lieu et ses categories sont crees par le test.
/ Dedicated test schema.

Lancement / Run:
    make test ARGS="tests/pytest/test_synchronisation_tva_categorie.py"
"""

import sys

# Le code Django vit dans /DjangoFiles a l'interieur du conteneur.
# / Django code lives in /DjangoFiles inside the container.
sys.path.insert(0, "/DjangoFiles")

import django  # noqa: E402

django.setup()

from decimal import Decimal  # noqa: E402

from django.db import connection  # noqa: E402
from django_tenants.test.cases import FastTenantTestCase  # noqa: E402
from django_tenants.test.client import TenantClient  # noqa: E402

from AuthBillet.models import TibilletUser  # noqa: E402
from BaseBillet.models import CategorieProduct, Configuration, Product, Tva  # noqa: E402


class TestSynchronisationTvaCategorie(FastTenantTestCase):
    """Bouton « Synchroniser la TVA » de la fiche d'une categorie de caisse.
    / "Synchronize VAT" button of a POS category page."""

    @classmethod
    def get_test_schema_name(cls):
        return "test_tva_categorie"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-tva-categorie.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        """`Client.name` est unique et obligatoire. / Client.name is unique."""
        tenant.name = "Test TVA categorie"

    def setUp(self):
        """Une categorie « Boissons » a 5,5 % avec trois articles (sans TVA, a 20 %,
        deja a 5,5 %) et une autre categorie avec un article a 20 %.
        / A 5.5 % category with three items, and another category."""
        connection.set_tenant(self.tenant)
        Configuration.get_solo().save()

        self.tva_reduite, _cree = Tva.objects.get_or_create(tva_rate=Decimal("5.50"))
        self.tva_normale, _cree = Tva.objects.get_or_create(tva_rate=Decimal("20.00"))

        self.boissons = CategorieProduct.objects.create(
            name="Boissons TVA", tva=self.tva_reduite
        )
        self.autre_categorie = CategorieProduct.objects.create(
            name="Snacks TVA", tva=self.tva_reduite
        )
        self.jus_sans_tva = Product.objects.create(
            name="Jus sans TVA", methode_caisse=Product.VENTE, categorie_pos=self.boissons
        )
        self.soda_a_vingt = Product.objects.create(
            name="Soda à 20", methode_caisse=Product.VENTE,
            categorie_pos=self.boissons, tva=self.tva_normale,
        )
        self.eau_deja_juste = Product.objects.create(
            name="Eau déjà juste", methode_caisse=Product.VENTE,
            categorie_pos=self.boissons, tva=self.tva_reduite,
        )
        self.chips_autre_categorie = Product.objects.create(
            name="Chips autre catégorie", methode_caisse=Product.VENTE,
            categorie_pos=self.autre_categorie, tva=self.tva_normale,
        )

        self.admin_du_lieu, _cree = TibilletUser.objects.get_or_create(
            email="admin-tva-categorie@tibillet.localhost",
            defaults={
                "username": "admin-tva-categorie@tibillet.localhost",
                "is_staff": True,
                "is_active": True,
            },
        )
        self.admin_du_lieu.client_admin.add(self.tenant)
        self.navigateur = TenantClient(self.tenant)
        self.navigateur.force_login(self.admin_du_lieu)

    def _url(self, categorie, fin):
        return f"/admin/BaseBillet/categorieproduct/{categorie.pk}/{fin}"

    def test_la_fiche_de_la_categorie_propose_le_bouton(self):
        """La fiche d'une categorie avec une TVA montre le bouton.
        / A category with a VAT shows the button."""
        reponse = self.navigateur.get(self._url(self.boissons, "change/"))

        contenu = reponse.content.decode()
        assert reponse.status_code == 200, contenu[:400]
        assert 'data-testid="categorie-synchroniser-tva"' in contenu

    def test_pas_de_bouton_sans_tva_de_categorie(self):
        """Une categorie sans TVA n'a rien a synchroniser : pas de bouton.
        / A category without VAT: no button."""
        self.boissons.tva = None
        self.boissons.save()

        reponse = self.navigateur.get(self._url(self.boissons, "change/"))

        assert reponse.status_code == 200
        assert 'data-testid="categorie-synchroniser-tva"' not in reponse.content.decode()

    def test_la_confirmation_explique_et_liste_les_articles_qui_changent(self):
        """Confirmation : les 2 articles qui changent (sans TVA, 20 %), pas celui
        deja a 5,5 % ; l'explication sur les ventes deja enregistrees.
        / Confirmation lists the 2 changing items and explains past sales."""
        reponse = self.navigateur.get(self._url(self.boissons, "synchroniser-tva/confirmer/"))

        contenu = reponse.content.decode()
        assert reponse.status_code == 200, contenu[:400]
        assert "Jus sans TVA" in contenu
        assert "Soda à 20" in contenu
        assert "Eau déjà juste" not in contenu
        assert "Chips autre catégorie" not in contenu
        assert "ventes déjà enregistrées" in contenu
        assert 'data-testid="categorie-synchroniser-tva-confirmer"' in contenu

    def test_confirmer_donne_la_tva_de_la_categorie_a_tous_ses_articles(self):
        """POST : les 3 articles de la categorie a 5,5 % ; l'article de l'autre
        categorie reste a 20 % ; la page se recharge.
        / POST: all 3 items at 5.5 %; the other category's item unchanged."""
        reponse = self.navigateur.post(self._url(self.boissons, "synchroniser-tva/"))

        assert reponse.status_code == 200, reponse.content.decode()[:400]
        assert reponse.headers.get("HX-Refresh") == "true"
        for article in [self.jus_sans_tva, self.soda_a_vingt, self.eau_deja_juste]:
            article.refresh_from_db()
            assert article.tva == self.tva_reduite, article.name
        self.chips_autre_categorie.refresh_from_db()
        assert self.chips_autre_categorie.tva == self.tva_normale

    def test_la_synchronisation_refuse_un_get(self):
        """La modification ne passe que par un POST.
        / The change only goes through a POST."""
        reponse = self.navigateur.get(self._url(self.boissons, "synchroniser-tva/"))

        assert reponse.status_code == 405
        self.soda_a_vingt.refresh_from_db()
        assert self.soda_a_vingt.tva == self.tva_normale

    def test_un_utilisateur_qui_n_est_pas_admin_du_lieu_est_refuse(self):
        """Un membre du staff qui n'administre pas ce lieu ne change rien.
        / A staff user who does not administer this venue changes nothing."""
        visiteur, _cree = TibilletUser.objects.get_or_create(
            email="staff-sans-lieu@tibillet.localhost",
            defaults={
                "username": "staff-sans-lieu@tibillet.localhost",
                "is_staff": True,
                "is_active": True,
            },
        )
        navigateur_du_visiteur = TenantClient(self.tenant)
        navigateur_du_visiteur.force_login(visiteur)

        reponse = navigateur_du_visiteur.post(self._url(self.boissons, "synchroniser-tva/"))

        assert reponse.status_code in (302, 403)
        self.soda_a_vingt.refresh_from_db()
        assert self.soda_a_vingt.tva == self.tva_normale

    def test_l_aide_de_la_tva_d_un_article_ne_promet_plus_l_heritage(self):
        """Fiche d'un article de caisse : l'aide dit que la vente prend la TVA de
        l'article, sinon celle du lieu (jamais celle de la categorie).
        / POS item page: help text no longer promises category inheritance."""
        from Administration.admin.products import POSProductForm

        formulaire = POSProductForm(instance=self.jus_sans_tva)

        aide = str(formulaire.fields["tva"].help_text)
        assert "Même TVA que la catégorie" not in aide
        assert "TVA par défaut du lieu" in aide
        assert "Synchroniser la TVA" in aide
