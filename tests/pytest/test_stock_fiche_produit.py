"""
Tests de la section Stock des fiches produit (option A)
et de la colonne / filtre Stock de la liste (option B).
/ Tests for the product page Stock section (option A)
and the list Stock column / filter (option B).

LOCALISATION : tests/pytest/test_stock_fiche_produit.py

Code testé :
- inventaire/services.py : StockService.creer_stock_initial
- Administration/admin/stock_fiche_produit.py : section, sauvegarde, badge, filtre
- Administration/admin/products.py : POSProductAdmin (fieldsets, save_model, liste)

Base dev partagée (pas de rollback) : chaque test crée ses produits
avec un nom unique et les supprime à la fin.
/ Shared dev DB (no rollback): each test creates and deletes its own products.
"""

import uuid

import pytest
from django_tenants.utils import tenant_context

PREFIXE_NOM_PRODUIT = "TEST stock fiche"


@pytest.fixture
def produit_caisse_sans_stock(tenant):
    """
    Produit de caisse (méthode Vente) sans stock. Supprimé après le test.
    / POS product (sale method) without stock. Deleted after the test.
    """
    with tenant_context(tenant):
        from BaseBillet.models import Product

        produit = Product.objects.create(
            name=f"{PREFIXE_NOM_PRODUIT} {uuid.uuid4().hex[:8]}",
            methode_caisse=Product.VENTE,
        )

    yield produit

    with tenant_context(tenant):
        from BaseBillet.models import Product

        Product.objects.filter(pk=produit.pk).delete()


def _creer_stock(
    tenant,
    produit,
    quantite,
    seuil_alerte=None,
    unite="UN",
    autoriser_vente_hors_stock=True,
):
    """Crée un stock directement, sans mouvement. / Creates a stock, no movement."""
    with tenant_context(tenant):
        from inventaire.models import Stock

        return Stock.objects.create(
            product=produit,
            quantite=quantite,
            unite=unite,
            seuil_alerte=seuil_alerte,
            autoriser_vente_hors_stock=autoriser_vente_hors_stock,
        )


def _nombre_de_mouvements(tenant, produit):
    with tenant_context(tenant):
        from inventaire.models import MouvementStock

        return MouvementStock.objects.filter(stock__product=produit).count()


# ─────────────────────────────────────────────────────────────────────
# Service / Service
# ─────────────────────────────────────────────────────────────────────


class TestCreerStockInitial:
    def test_01_quantite_de_depart_creee_par_un_mouvement_reception(
        self, tenant, produit_caisse_sans_stock
    ):
        """12 pièces de départ → stock à 12 et 1 mouvement RE « Stock initial »."""
        with tenant_context(tenant):
            from inventaire.models import MouvementStock, TypeMouvement
            from inventaire.services import StockService

            stock = StockService.creer_stock_initial(
                product=produit_caisse_sans_stock,
                unite="UN",
                quantite_initiale=12,
                seuil_alerte=3,
            )

            assert stock.quantite == 12
            assert stock.seuil_alerte == 3
            mouvements = MouvementStock.objects.filter(stock=stock)
            assert mouvements.count() == 1
            mouvement = mouvements.first()
            assert mouvement.type_mouvement == TypeMouvement.RE
            assert mouvement.quantite == 12
            assert mouvement.quantite_avant == 0

    def test_02_quantite_zero_ne_cree_pas_de_mouvement(
        self, tenant, produit_caisse_sans_stock
    ):
        """0 de départ → stock à 0, aucun mouvement."""
        with tenant_context(tenant):
            from inventaire.services import StockService

            stock = StockService.creer_stock_initial(
                product=produit_caisse_sans_stock,
                unite="CL",
                quantite_initiale=0,
            )
            assert stock.quantite == 0
            assert stock.unite == "CL"

        assert _nombre_de_mouvements(tenant, produit_caisse_sans_stock) == 0


# ─────────────────────────────────────────────────────────────────────
# Sauvegarde de la section Stock / Stock section saving
# ─────────────────────────────────────────────────────────────────────


class TestEnregistrerSectionStock:
    def test_03_suivi_coche_cree_le_stock_et_le_mouvement(
        self, tenant, produit_caisse_sans_stock, admin_user
    ):
        """Case « Suivre le stock » cochée + 20 → stock à 20, 1 mouvement."""
        from types import SimpleNamespace

        with tenant_context(tenant):
            from Administration.admin.stock_fiche_produit import (
                enregistrer_section_stock,
            )

            enregistrer_section_stock(
                SimpleNamespace(user=admin_user),
                produit_caisse_sans_stock,
                {
                    "stock_suivi": True,
                    "stock_quantite_initiale": 20,
                    "stock_unite": "UN",
                    "stock_seuil_alerte": 5,
                    "stock_vente_hors_stock": False,
                },
            )
            produit_caisse_sans_stock.refresh_from_db()
            stock = produit_caisse_sans_stock.stock_inventaire
            assert stock.quantite == 20
            assert stock.seuil_alerte == 5
            assert stock.autoriser_vente_hors_stock is False

        assert _nombre_de_mouvements(tenant, produit_caisse_sans_stock) == 1

    def test_04_suivi_decoche_ne_cree_rien(
        self, tenant, produit_caisse_sans_stock, admin_user
    ):
        """Case décochée → pas de stock."""
        from types import SimpleNamespace

        with tenant_context(tenant):
            from Administration.admin.stock_fiche_produit import (
                enregistrer_section_stock,
                stock_du_produit_ou_none,
            )

            enregistrer_section_stock(
                SimpleNamespace(user=admin_user),
                produit_caisse_sans_stock,
                {"stock_suivi": False, "stock_quantite_initiale": 20},
            )
            produit_caisse_sans_stock.refresh_from_db()
            assert stock_du_produit_ou_none(produit_caisse_sans_stock) is None

    def test_05_reglages_modifies_sans_toucher_la_quantite(
        self, tenant, produit_caisse_sans_stock, admin_user
    ):
        """
        Stock existant : seuil et vente hors stock changent,
        la quantité (modifiée par une vente entre-temps) reste intacte.
        / Settings change, quantity (changed meanwhile) stays untouched.
        """
        from types import SimpleNamespace

        stock = _creer_stock(tenant, produit_caisse_sans_stock, quantite=10)

        with tenant_context(tenant):
            from Administration.admin.stock_fiche_produit import (
                enregistrer_section_stock,
            )
            from inventaire.models import Stock

            # Le produit garde en cache le stock à 10.
            # Une vente passe à 7 en base pendant que la page est ouverte.
            # / A sale sets 7 in DB while the page is open.
            produit_caisse_sans_stock.stock_inventaire
            Stock.objects.filter(pk=stock.pk).update(quantite=7)

            enregistrer_section_stock(
                SimpleNamespace(user=admin_user),
                produit_caisse_sans_stock,
                {
                    "stock_unite": "UN",
                    "stock_seuil_alerte": 4,
                    "stock_vente_hors_stock": False,
                },
            )
            stock.refresh_from_db()
            assert stock.quantite == 7
            assert stock.seuil_alerte == 4
            assert stock.autoriser_vente_hors_stock is False

        assert _nombre_de_mouvements(tenant, produit_caisse_sans_stock) == 0


# ─────────────────────────────────────────────────────────────────────
# Fiche produit dans l'admin / Product page in admin
# ─────────────────────────────────────────────────────────────────────


class TestFicheProduitSectionStock:
    def test_06_produit_sans_stock_affiche_la_case_suivre_le_stock(
        self, admin_client, produit_caisse_sans_stock
    ):
        """Pas de stock → case « Suivre le stock » + quantité de départ, pas de panneau."""
        reponse = admin_client.get(
            f"/admin/BaseBillet/posproduct/{produit_caisse_sans_stock.pk}/change/"
        )
        assert reponse.status_code == 200
        contenu = reponse.content.decode()
        assert 'id="section-stock"' in contenu
        assert 'name="stock_suivi"' in contenu
        assert 'name="stock_quantite_initiale"' in contenu
        assert 'data-testid="stock-actions-container"' not in contenu

    def test_07_produit_avec_stock_affiche_le_panneau_d_operations(
        self, admin_client, tenant, produit_caisse_sans_stock
    ):
        """
        Stock existant → réglages + panneau (4 boutons), pas de quantité de départ.
        Les champs d'opération ne sont rattachés à aucun formulaire.
        / Existing stock → settings + panel; operation inputs have no form owner.
        """
        _creer_stock(tenant, produit_caisse_sans_stock, quantite=42)

        reponse = admin_client.get(
            f"/admin/BaseBillet/posproduct/{produit_caisse_sans_stock.pk}/change/"
        )
        assert reponse.status_code == 200
        contenu = reponse.content.decode()
        assert 'data-testid="stock-actions-container"' in contenu
        assert 'data-testid="btn-reception"' in contenu
        assert 'form="stock-operations-hors-formulaire"' in contenu
        assert 'name="stock_seuil_alerte"' in contenu
        assert 'name="stock_quantite_initiale"' not in contenu

    def test_08_page_d_ajout_affiche_la_section_stock(self, admin_client):
        """Création d'un produit : section Stock présente, plus d'inline Stock."""
        reponse = admin_client.get("/admin/BaseBillet/posproduct/add/")
        assert reponse.status_code == 200
        contenu = reponse.content.decode()
        assert 'name="stock_suivi"' in contenu
        assert "stock_inventaire-TOTAL_FORMS" not in contenu

    def test_09_reception_depuis_le_panneau_ajoute_au_stock(
        self, admin_client, tenant, produit_caisse_sans_stock
    ):
        """
        Le panneau poste vers stock_action_view avec les champs du formulaire produit
        (dont le jeton CSRF) : la réception est enregistrée.
        / The panel posts along with the product form fields: reception recorded.
        """
        stock = _creer_stock(tenant, produit_caisse_sans_stock, quantite=5)

        reponse = admin_client.post(
            f"/admin/inventaire/stock/{stock.pk}/action/",
            data={
                "type_mouvement": "RE",
                "quantite": "10",
                "motif": "",
                "name": produit_caisse_sans_stock.name,
            },
        )
        assert reponse.status_code == 200
        contenu = reponse.content.decode()
        assert 'data-testid="stock-action-success"' in contenu
        # Lien vers les mouvements construit avec {% url %} / Link built with {% url %}
        assert "/admin/inventaire/mouvementstock/?stock__pk__exact=" in contenu

        with tenant_context(tenant):
            stock.refresh_from_db()
            assert stock.quantite == 15


# ─────────────────────────────────────────────────────────────────────
# Liste des produits : colonne et filtre / Product list: column and filter
# ─────────────────────────────────────────────────────────────────────


class TestColonneEtFiltreStock:
    def test_10_badge_selon_l_etat_du_stock(self, tenant, produit_caisse_sans_stock):
        """
        — sans stock ; « Épuisé » à 0 si la vente est bloquée ;
        quantité + lien vers #section-stock sinon.
        """
        from Administration.admin.stock_fiche_produit import (
            display_stock_produit_caisse,
        )

        with tenant_context(tenant):
            assert display_stock_produit_caisse(produit_caisse_sans_stock) == "—"

        stock = _creer_stock(
            tenant,
            produit_caisse_sans_stock,
            quantite=0,
            autoriser_vente_hors_stock=False,
        )
        with tenant_context(tenant):
            produit_caisse_sans_stock.refresh_from_db()
            html_du_badge = str(display_stock_produit_caisse(produit_caisse_sans_stock))
            assert "#section-stock" in html_du_badge
            assert "#991b1b" in html_du_badge  # rouge / red
            assert "Épuisé" in html_du_badge or "Out of stock" in html_du_badge

            from inventaire.models import Stock

            Stock.objects.filter(pk=stock.pk).update(quantite=42)
            produit_caisse_sans_stock.refresh_from_db()
            html_du_badge = str(display_stock_produit_caisse(produit_caisse_sans_stock))
            assert ">42<" in html_du_badge
            assert "#166534" in html_du_badge  # vert / green

    def test_15_badge_negatif_si_vente_hors_stock_autorisee(
        self, tenant, produit_caisse_sans_stock
    ):
        """
        Vente hors stock autorisée et stock à -12 : la pastille montre « -12 »
        (rouge), pas « Épuisé ». Même règle en centilitres : -150 → « -1.5 L ».
        / Out-of-stock sales allowed: badge shows the negative quantity.
        """
        from Administration.admin.stock_fiche_produit import (
            display_stock_produit_caisse,
        )

        stock = _creer_stock(
            tenant,
            produit_caisse_sans_stock,
            quantite=-12,
            autoriser_vente_hors_stock=True,
        )
        with tenant_context(tenant):
            produit_caisse_sans_stock.refresh_from_db()
            html_du_badge = str(display_stock_produit_caisse(produit_caisse_sans_stock))
            assert ">-12<" in html_du_badge
            assert "Épuisé" not in html_du_badge
            assert "#991b1b" in html_du_badge  # rouge / red

            from inventaire.models import Stock

            Stock.objects.filter(pk=stock.pk).update(quantite=-150, unite="CL")
            produit_caisse_sans_stock.refresh_from_db()
            html_du_badge = str(display_stock_produit_caisse(produit_caisse_sans_stock))
            assert ">-1.5 L<" in html_du_badge

    def test_16_regles_conditionnelles_de_la_section_stock_injectees(
        self, admin_client
    ):
        """
        La page d'ajout injecte les règles « stock_suivi == true » pour le JS
        inline_conditional_fields.js, et charge ce JS.
        / The add page injects the stock_suivi rules and loads the JS.
        """
        reponse = admin_client.get("/admin/BaseBillet/posproduct/add/")
        contenu = reponse.content.decode()
        assert 'id="inline-conditional-rules"' in contenu
        assert "__formulaire_principal__" in contenu
        assert "stock_suivi == true" in contenu
        assert "admin/js/inline_conditional_fields.js" in contenu

    def test_11_filtre_etat_du_stock(self, tenant, produit_caisse_sans_stock):
        """Chaque valeur du filtre ne garde que les produits dans cet état."""
        from BaseBillet.models import Product

        with tenant_context(tenant):
            produit_en_alerte = Product.objects.create(
                name=f"{PREFIXE_NOM_PRODUIT} alerte {uuid.uuid4().hex[:6]}",
                methode_caisse=Product.VENTE,
            )
            produit_ok = Product.objects.create(
                name=f"{PREFIXE_NOM_PRODUIT} ok {uuid.uuid4().hex[:6]}",
                methode_caisse=Product.VENTE,
            )
        _creer_stock(tenant, produit_en_alerte, quantite=2, seuil_alerte=5)
        _creer_stock(tenant, produit_ok, quantite=50, seuil_alerte=5)

        try:
            with tenant_context(tenant):
                from Administration.admin.stock_fiche_produit import EtatStockFilter

                produits_du_test = Product.objects.filter(
                    name__startswith=PREFIXE_NOM_PRODUIT
                )

                def filtrer(valeur):
                    filtre = EtatStockFilter(
                        None, {"etat_stock": valeur}, Product, None
                    )
                    return set(filtre.queryset(None, produits_du_test))

                assert filtrer("alerte") == {produit_en_alerte}
                assert filtrer("ok") == {produit_ok}
                assert produit_caisse_sans_stock in filtrer("non_suivi")
                assert produit_en_alerte not in filtrer("rupture")
        finally:
            with tenant_context(tenant):
                Product.objects.filter(
                    pk__in=[produit_en_alerte.pk, produit_ok.pk]
                ).delete()

    def test_12_liste_des_produits_de_caisse_affiche_la_colonne(
        self, admin_client, tenant, produit_caisse_sans_stock
    ):
        """La liste répond, avec le badge du produit et le filtre État du stock."""
        _creer_stock(tenant, produit_caisse_sans_stock, quantite=3)

        reponse = admin_client.get(
            "/admin/BaseBillet/posproduct/",
            {"q": produit_caisse_sans_stock.name},
        )
        assert reponse.status_code == 200
        contenu = reponse.content.decode()
        assert (
            f'data-testid="product-list-stock-{produit_caisse_sans_stock.pk}"'
            in contenu
        )
        assert "etat_stock" in contenu

    def test_13_liste_sans_requete_par_ligne(self, tenant):
        """get_queryset charge le stock avec le produit (select_related)."""
        from types import SimpleNamespace

        with tenant_context(tenant):
            from Administration.admin.site import staff_admin_site
            from BaseBillet.models import POSProduct

            admin_produits_caisse = staff_admin_site._registry[POSProduct]
            requete_fictive = SimpleNamespace(user=None, GET={}, path="/admin/")
            queryset = admin_produits_caisse.get_queryset(requete_fictive)
            assert "stock_inventaire" in queryset.query.select_related


class TestCreationProduitAvecStock:
    def test_14_creer_un_produit_avec_suivi_du_stock_via_l_admin(
        self, admin_client, tenant
    ):
        """
        POST de la page d'ajout avec « Suivre le stock » coché et 24 de départ :
        le produit, son stock (24) et 1 mouvement « Stock initial » sont créés.
        / Admin add POST with stock tracking: product, stock and 1 movement created.
        """
        from BaseBillet.models import Product

        nom_du_produit = f"{PREFIXE_NOM_PRODUIT} ajout {uuid.uuid4().hex[:6]}"
        reponse = admin_client.post(
            "/admin/BaseBillet/posproduct/add/",
            data={
                "name": nom_du_produit,
                "categorie_article": Product.NONE,
                "methode_caisse": Product.VENTE,
                "poids": "0",
                "prix_achat": "0",
                "publish": "on",
                "stock_suivi": "on",
                "stock_quantite_initiale": "24",
                "stock_unite": "UN",
                "stock_seuil_alerte": "6",
                "stock_vente_hors_stock": "on",
                "prices-TOTAL_FORMS": "0",
                "prices-INITIAL_FORMS": "0",
                "prices-MIN_NUM_FORMS": "0",
                "prices-MAX_NUM_FORMS": "1000",
                "_save": "Enregistrer",
            },
        )

        with tenant_context(tenant):
            produit_cree = Product.objects.filter(name=nom_du_produit).first()
            try:
                erreurs = (
                    reponse.context["adminform"].form.errors
                    if reponse.status_code == 200
                    else None
                )
                assert reponse.status_code == 302, erreurs
                assert produit_cree is not None
                stock = produit_cree.stock_inventaire
                assert stock.quantite == 24
                assert stock.seuil_alerte == 6
                assert stock.mouvements.count() == 1
            finally:
                if produit_cree is not None:
                    produit_cree.delete()
