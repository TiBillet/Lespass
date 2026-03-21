"""
tests/pytest/test_pos_views_data.py — Tests unitaires des fonctions de construction
de donnees articles/categories pour l'interface caisse.
/ Unit tests for article/category data construction functions for the POS interface.

LOCALISATION : tests/pytest/test_pos_views_data.py

Couvre :
  - _construire_donnees_articles : couleurs (override produit / fallback categorie),
    icones (FA/MS/vide), icone_type, fallback icone categorie, bt_groupement,
    prix en centimes, categorie_dict avec icone_type
  - _construire_donnees_categories : detection icone_type FA/MS/vide
  - LaboutikConfiguration.get_solo() : singleton, valeurs par defaut

Prerequis / Prerequisites:
  - Base de donnees avec le tenant 'lespass' existant
  - Pas de create_test_pos_data requis (donnees creees et nettoyees ici)

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_pos_views_data.py -v --api-key dummy
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

from django_tenants.utils import schema_context

from Customers.models import Client


# Prefixe pour identifier les donnees de ce module et les nettoyer.
# / Prefix to identify this module's data and clean it up.
TEST_PREFIX = '[test_pos_views_data]'

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
    Supprime toutes les donnees creees par ce module APRES execution.
    Ordre FK : PointDeVente → Price → Product → CategorieProduct.
    / Deletes all data created by this module AFTER execution. FK order respected.
    """
    yield

    with schema_context(TENANT_SCHEMA):
        from BaseBillet.models import CategorieProduct, Product, Price
        from laboutik.models import PointDeVente

        # Vider les M2M avant suppression des PointDeVente
        # / Clear M2M before deleting PointDeVente
        pdv_tests = PointDeVente.objects.filter(name__startswith=TEST_PREFIX)
        for pdv in pdv_tests:
            pdv.products.clear()
            pdv.categories.clear()
        pdv_tests.delete()

        Price.objects.filter(name__startswith=TEST_PREFIX).delete()
        Product.objects.filter(name__startswith=TEST_PREFIX).delete()
        CategorieProduct.objects.filter(name__startswith=TEST_PREFIX).delete()


# ---------------------------------------------------------------------------
# Fonctions utilitaires pour les tests
# Utility functions for tests
# ---------------------------------------------------------------------------

def creer_pdv_avec_produit(nom_prefix, product, cat=None):
    """
    Cree un PointDeVente minimal et y ajoute le produit donne.
    Retourne le PDV cree.
    / Creates a minimal PointDeVente and adds the given product.
    Returns the created POS.
    """
    from laboutik.models import PointDeVente

    pdv = PointDeVente.objects.create(
        name=f'{TEST_PREFIX} PDV {nom_prefix}',
        comportement=PointDeVente.DIRECT,
    )
    pdv.products.add(product)
    if cat:
        pdv.categories.add(cat)
    return pdv


# ---------------------------------------------------------------------------
# Test 1 : Couleur — override produit prioritaire sur la categorie
# Test 1: Color — product override takes priority over category
# ---------------------------------------------------------------------------

def test_couleurs_override_produit(tenant):
    """
    Un produit avec couleur_fond_pos et couleur_texte_pos definis
    doit utiliser ces valeurs, pas celles de la categorie.
    / A product with defined couleur_fond_pos and couleur_texte_pos
    must use those values, not the category's.
    """
    with schema_context(TENANT_SCHEMA):
        from BaseBillet.models import CategorieProduct, Product, Price
        from laboutik.views import _construire_donnees_articles

        # Categorie avec ses propres couleurs — ne doivent PAS etre utilisees
        # / Category with its own colors — must NOT be used
        cat = CategorieProduct.objects.create(
            name=f'{TEST_PREFIX} Cat Override',
            couleur_fond='#AAAAAA',
            couleur_texte='#111111',
        )

        # Produit avec override couleur
        # / Product with color override
        product = Product.objects.create(
            name=f'{TEST_PREFIX} Override Couleur',
            methode_caisse=Product.VENTE,
            categorie_pos=cat,
            couleur_fond_pos='#F59E0B',
            couleur_texte_pos='#000000',
        )
        Price.objects.create(
            product=product,
            name=f'{TEST_PREFIX} Tarif Override',
            prix=Decimal('5.00'),
        )

        pdv = creer_pdv_avec_produit('Override Couleur', product, cat)
        articles = _construire_donnees_articles(pdv)

        # Chercher notre article dans la liste retournee
        # / Find our article in the returned list
        article = next((a for a in articles if a['name'] == f'{TEST_PREFIX} Override Couleur'), None)
        assert article is not None, "L'article doit etre dans la liste retournee"

        # Couleurs produit utilisees, pas celles de la categorie
        # / Product colors used, not category ones
        assert article['couleur_backgr'] == '#F59E0B', (
            f"couleur_backgr attendu '#F59E0B', obtenu '{article['couleur_backgr']}'"
        )
        assert article['couleur_texte'] == '#000000', (
            f"couleur_texte attendu '#000000', obtenu '{article['couleur_texte']}'"
        )


def test_couleurs_fallback_categorie(tenant):
    """
    Un produit SANS couleur propre doit heriter des couleurs de sa categorie.
    / A product WITHOUT own colors must inherit from its category.
    """
    with schema_context(TENANT_SCHEMA):
        from BaseBillet.models import CategorieProduct, Product, Price
        from laboutik.views import _construire_donnees_articles

        # Categorie avec couleurs — doivent etre utilisees en fallback
        # / Category with colors — must be used as fallback
        cat = CategorieProduct.objects.create(
            name=f'{TEST_PREFIX} Cat Fallback',
            couleur_fond='#7C3AED',
            couleur_texte='#FFFFFF',
        )

        # Produit SANS couleur propre (None ou chaine vide)
        # / Product WITHOUT own color (None or empty string)
        product = Product.objects.create(
            name=f'{TEST_PREFIX} Fallback Couleur',
            methode_caisse=Product.VENTE,
            categorie_pos=cat,
            couleur_fond_pos=None,
            couleur_texte_pos=None,
        )
        Price.objects.create(
            product=product,
            name=f'{TEST_PREFIX} Tarif Fallback',
            prix=Decimal('3.00'),
        )

        pdv = creer_pdv_avec_produit('Fallback Couleur', product, cat)
        articles = _construire_donnees_articles(pdv)

        article = next((a for a in articles if a['name'] == f'{TEST_PREFIX} Fallback Couleur'), None)
        assert article is not None

        # Couleurs de la categorie utilisees
        # / Category colors used
        assert article['couleur_backgr'] == '#7C3AED', (
            f"couleur_backgr attendu '#7C3AED' (categorie), obtenu '{article['couleur_backgr']}'"
        )
        assert article['couleur_texte'] == '#FFFFFF', (
            f"couleur_texte attendu '#FFFFFF' (categorie), obtenu '{article['couleur_texte']}'"
        )


# ---------------------------------------------------------------------------
# Test 2 : Icones — detection du systeme (FontAwesome vs Material Symbols)
# Test 2: Icons — system detection (FontAwesome vs Material Symbols)
# ---------------------------------------------------------------------------

def test_icone_fontawesome(tenant):
    """
    Une icone prefixee 'fa' (ex: 'fa-beer') doit donner icone_type='fa'.
    / A 'fa'-prefixed icon (e.g. 'fa-beer') must give icone_type='fa'.
    """
    with schema_context(TENANT_SCHEMA):
        from BaseBillet.models import CategorieProduct, Product, Price
        from laboutik.views import _construire_donnees_articles

        cat = CategorieProduct.objects.create(name=f'{TEST_PREFIX} Cat FA Icon')
        product = Product.objects.create(
            name=f'{TEST_PREFIX} Icone FA',
            methode_caisse=Product.VENTE,
            categorie_pos=cat,
            icon_pos='fa-beer',
        )
        Price.objects.create(product=product, name=f'{TEST_PREFIX} Tarif FA', prix=Decimal('4.00'))

        pdv = creer_pdv_avec_produit('Icone FA', product)
        articles = _construire_donnees_articles(pdv)

        article = next((a for a in articles if a['name'] == f'{TEST_PREFIX} Icone FA'), None)
        assert article is not None

        assert article['icone'] == 'fa-beer'
        assert article['icone_type'] == 'fa', (
            f"icone_type attendu 'fa', obtenu '{article['icone_type']}'"
        )


def test_icone_material_symbols(tenant):
    """
    Une icone Material Symbols sans prefixe 'fa' (ex: 'local_drink')
    doit donner icone_type='ms'.
    / A Material Symbols icon without 'fa' prefix (e.g. 'local_drink')
    must give icone_type='ms'.
    """
    with schema_context(TENANT_SCHEMA):
        from BaseBillet.models import CategorieProduct, Product, Price
        from laboutik.views import _construire_donnees_articles

        cat = CategorieProduct.objects.create(name=f'{TEST_PREFIX} Cat MS Icon')
        product = Product.objects.create(
            name=f'{TEST_PREFIX} Icone MS',
            methode_caisse=Product.VENTE,
            categorie_pos=cat,
            icon_pos='local_drink',
        )
        Price.objects.create(product=product, name=f'{TEST_PREFIX} Tarif MS', prix=Decimal('2.00'))

        pdv = creer_pdv_avec_produit('Icone MS', product)
        articles = _construire_donnees_articles(pdv)

        article = next((a for a in articles if a['name'] == f'{TEST_PREFIX} Icone MS'), None)
        assert article is not None

        assert article['icone'] == 'local_drink'
        assert article['icone_type'] == 'ms', (
            f"icone_type attendu 'ms', obtenu '{article['icone_type']}'"
        )


def test_icone_fallback_vers_categorie(tenant):
    """
    Un produit SANS icone propre (icon_pos vide) doit utiliser
    l'icone de sa categorie comme fallback.
    / A product WITHOUT its own icon (empty icon_pos) must use
    the category icon as fallback.
    """
    with schema_context(TENANT_SCHEMA):
        from BaseBillet.models import CategorieProduct, Product, Price
        from laboutik.views import _construire_donnees_articles

        # Categorie avec icone MS (le produit n'a pas d'icone propre)
        # / Category with MS icon (product has no own icon)
        cat = CategorieProduct.objects.create(
            name=f'{TEST_PREFIX} Cat Icon Fallback',
            icon='sports_bar',
        )
        product = Product.objects.create(
            name=f'{TEST_PREFIX} Icone Fallback Cat',
            methode_caisse=Product.VENTE,
            categorie_pos=cat,
            icon_pos='',
        )
        Price.objects.create(product=product, name=f'{TEST_PREFIX} Tarif Fallback Cat', prix=Decimal('5.00'))

        pdv = creer_pdv_avec_produit('Icone Fallback', product)
        articles = _construire_donnees_articles(pdv)

        article = next((a for a in articles if a['name'] == f'{TEST_PREFIX} Icone Fallback Cat'), None)
        assert article is not None

        # L'icone de la categorie est utilisee en fallback
        # / Category icon used as fallback
        assert article['icone'] == 'sports_bar'
        assert article['icone_type'] == 'ms', (
            f"icone_type attendu 'ms' (fallback categorie), obtenu '{article['icone_type']}'"
        )


def test_icone_vide_produit_et_categorie(tenant):
    """
    Produit ET categorie sans icone → icone vide, icone_type vide.
    / Product AND category without icon → empty icone, empty icone_type.
    """
    with schema_context(TENANT_SCHEMA):
        from BaseBillet.models import CategorieProduct, Product, Price
        from laboutik.views import _construire_donnees_articles

        cat = CategorieProduct.objects.create(
            name=f'{TEST_PREFIX} Cat Sans Icone',
            icon='',
        )
        product = Product.objects.create(
            name=f'{TEST_PREFIX} Sans Icone',
            methode_caisse=Product.VENTE,
            categorie_pos=cat,
            icon_pos='',
        )
        Price.objects.create(product=product, name=f'{TEST_PREFIX} Tarif Sans Icone', prix=Decimal('1.00'))

        pdv = creer_pdv_avec_produit('Sans Icone', product)
        articles = _construire_donnees_articles(pdv)

        article = next((a for a in articles if a['name'] == f'{TEST_PREFIX} Sans Icone'), None)
        assert article is not None

        assert article['icone'] == '', "icone doit etre vide"
        assert article['icone_type'] == '', "icone_type doit etre vide"


# ---------------------------------------------------------------------------
# Test 3 : Prix en centimes
# Test 3: Prices in cents
# ---------------------------------------------------------------------------

def test_prix_en_centimes(tenant):
    """
    Le champ 'prix' dans article_dict doit etre en centimes (int),
    jamais en euros. Conversion : int(round(prix_euros * 100)).
    / The 'prix' field in article_dict must be in cents (int),
    never in euros. Conversion: int(round(prix_euros * 100)).
    """
    with schema_context(TENANT_SCHEMA):
        from BaseBillet.models import CategorieProduct, Product, Price
        from laboutik.views import _construire_donnees_articles

        cat = CategorieProduct.objects.create(name=f'{TEST_PREFIX} Cat Prix')

        # Differents prix pour tester la conversion
        # / Different prices to test the conversion
        cas_de_test = [
            ('5.00', 500),
            ('12.50', 1250),
            ('1.50', 150),
            ('0.00', 0),
        ]

        for prix_eur_str, centimes_attendus in cas_de_test:
            prix_eur = Decimal(prix_eur_str)
            product = Product.objects.create(
                name=f'{TEST_PREFIX} Prix {prix_eur_str}',
                methode_caisse=Product.VENTE,
                categorie_pos=cat,
            )
            Price.objects.create(
                product=product,
                name=f'{TEST_PREFIX} Tarif {prix_eur_str}',
                prix=prix_eur,
            )

            pdv = creer_pdv_avec_produit(f'Prix {prix_eur_str}', product)
            articles = _construire_donnees_articles(pdv)

            article = next(
                (a for a in articles if a['name'] == f'{TEST_PREFIX} Prix {prix_eur_str}'), None
            )
            assert article is not None, f"Article '{prix_eur_str}' introuvable"
            assert article['prix'] == centimes_attendus, (
                f"Prix EUR {prix_eur_str} → attendu {centimes_attendus} centimes, "
                f"obtenu {article['prix']}"
            )


# ---------------------------------------------------------------------------
# Test 4 : bt_groupement — groupement automatique par methode_caisse
# Test 4: bt_groupement — automatic grouping by methode_caisse
# ---------------------------------------------------------------------------

def test_bt_groupement_par_methode_caisse(tenant):
    """
    Le groupement est calcule automatiquement depuis methode_caisse.
    Plus de champ groupe_pos : groupe_VT pour VENTE, groupe_RE pour RECHARGE_EUROS.
    / Grouping is computed automatically from methode_caisse.
    No more groupe_pos field: groupe_VT for VENTE, groupe_RE for RECHARGE_EUROS.
    """
    with schema_context(TENANT_SCHEMA):
        from BaseBillet.models import CategorieProduct, Product, Price
        from laboutik.models import PointDeVente
        from laboutik.views import _construire_donnees_articles

        cat = CategorieProduct.objects.create(name=f'{TEST_PREFIX} Cat Groupement')

        product_vente = Product.objects.create(
            name=f'{TEST_PREFIX} Groupement VENTE',
            methode_caisse=Product.VENTE,
            categorie_pos=cat,
        )
        Price.objects.create(product=product_vente, name=f'{TEST_PREFIX} Tarif VT', prix=Decimal('5.00'))

        product_recharge = Product.objects.create(
            name=f'{TEST_PREFIX} Groupement RECHARGE',
            methode_caisse=Product.RECHARGE_EUROS,
            categorie_pos=cat,
        )
        Price.objects.create(product=product_recharge, name=f'{TEST_PREFIX} Tarif RE', prix=Decimal('10.00'))

        pdv = PointDeVente.objects.create(
            name=f'{TEST_PREFIX} PDV Groupement',
            comportement=PointDeVente.DIRECT,
        )
        pdv.products.add(product_vente, product_recharge)

        articles = _construire_donnees_articles(pdv)

        art_vente = next((a for a in articles if 'VENTE' in a['name']), None)
        art_recharge = next((a for a in articles if 'RECHARGE' in a['name']), None)

        assert art_vente is not None
        assert art_recharge is not None

        # Groupement auto par methode_caisse (groupe_pos n'existe plus)
        # / Auto grouping by methode_caisse (groupe_pos no longer exists)
        assert art_vente['bt_groupement']['groupe'] == 'groupe_VT', (
            f"groupe attendu 'groupe_VT', obtenu '{art_vente['bt_groupement']['groupe']}'"
        )
        assert art_recharge['bt_groupement']['groupe'] == 'groupe_RE', (
            f"groupe attendu 'groupe_RE', obtenu '{art_recharge['bt_groupement']['groupe']}'"
        )


# ---------------------------------------------------------------------------
# Test 5 : categorie_dict — contient icone_type pour le badge haut-gauche
# Test 5: categorie_dict — contains icone_type for the top-left badge
# ---------------------------------------------------------------------------

def test_categorie_dict_contient_icone_type(tenant):
    """
    article_dict['categorie'] doit contenir 'icone_type' pour que le template
    puisse afficher le badge d'icone de categorie en haut a gauche de la tuile.
    / article_dict['categorie'] must contain 'icone_type' so the template
    can display the category icon badge at the top-left of the tile.
    """
    with schema_context(TENANT_SCHEMA):
        from BaseBillet.models import CategorieProduct, Product, Price
        from laboutik.views import _construire_donnees_articles

        # Categorie avec icone MS (wine_bar)
        # / Category with MS icon (wine_bar)
        cat = CategorieProduct.objects.create(
            name=f'{TEST_PREFIX} Cat Badge Icone',
            icon='wine_bar',
            couleur_fond='#7C3AED',
            couleur_texte='#FFFFFF',
        )
        product = Product.objects.create(
            name=f'{TEST_PREFIX} Produit Badge Icone',
            methode_caisse=Product.VENTE,
            categorie_pos=cat,
        )
        Price.objects.create(product=product, name=f'{TEST_PREFIX} Tarif Badge', prix=Decimal('5.00'))

        pdv = creer_pdv_avec_produit('Badge Icone', product, cat)
        articles = _construire_donnees_articles(pdv)

        article = next((a for a in articles if a['name'] == f'{TEST_PREFIX} Produit Badge Icone'), None)
        assert article is not None

        categorie = article['categorie']

        # La cle 'icone_type' doit etre presente pour le template articles.html
        # / Key 'icone_type' must be present for the articles.html template
        assert 'icone_type' in categorie, (
            "categorie_dict doit contenir 'icone_type' pour le badge haut-gauche de la tuile"
        )
        assert categorie['icone_type'] == 'ms', (
            f"'wine_bar' doit donner icone_type='ms', obtenu '{categorie['icone_type']}'"
        )
        assert categorie['icon'] == 'wine_bar'

        # Verifier aussi la cle 'couleur_backgr' (requise dans le template)
        # / Also check 'couleur_backgr' key (required in template)
        assert 'couleur_backgr' in categorie, "categorie_dict doit contenir 'couleur_backgr'"


# ---------------------------------------------------------------------------
# Test 6 : _construire_donnees_categories — detection icone_type FA / MS / vide
# Test 6: _construire_donnees_categories — icone_type detection FA / MS / empty
# ---------------------------------------------------------------------------

def test_construire_donnees_categories_icone_type(tenant):
    """
    _construire_donnees_categories doit ajouter 'icone_type' sur chaque categorie :
    - Icone FA (prefixe 'fa') → 'fa'
    - Icone MS (pas de prefixe 'fa') → 'ms'
    - Pas d'icone → fallback 'fa' avec 'fa-th'
    / _construire_donnees_categories must add 'icone_type' on each category:
    - FA icon (prefix 'fa') → 'fa'
    - MS icon (no 'fa' prefix) → 'ms'
    - No icon → fallback 'fa' with 'fa-th'
    """
    with schema_context(TENANT_SCHEMA):
        from BaseBillet.models import CategorieProduct
        from laboutik.models import PointDeVente
        from laboutik.views import _construire_donnees_categories

        cat_fa = CategorieProduct.objects.create(
            name=f'{TEST_PREFIX} Cat Liste FA',
            icon='fa-cocktail',
        )
        cat_ms = CategorieProduct.objects.create(
            name=f'{TEST_PREFIX} Cat Liste MS',
            icon='local_bar',
        )
        cat_vide = CategorieProduct.objects.create(
            name=f'{TEST_PREFIX} Cat Liste Vide',
            icon='',
        )

        pdv = PointDeVente.objects.create(
            name=f'{TEST_PREFIX} PDV Categories Liste',
            comportement=PointDeVente.DIRECT,
        )
        pdv.categories.add(cat_fa, cat_ms, cat_vide)

        categories = _construire_donnees_categories(pdv)

        # Trouver chaque categorie dans la liste retournee
        # / Find each category in the returned list
        dict_fa = next((c for c in categories if 'Liste FA' in c['name']), None)
        dict_ms = next((c for c in categories if 'Liste MS' in c['name']), None)
        dict_vide = next((c for c in categories if 'Liste Vide' in c['name']), None)

        assert dict_fa is not None, "Categorie FA introuvable"
        assert dict_ms is not None, "Categorie MS introuvable"
        assert dict_vide is not None, "Categorie Vide introuvable"

        # Icone FontAwesome : prefixe 'fa'
        # / FontAwesome icon: 'fa' prefix
        assert dict_fa['icone_type'] == 'fa', (
            f"'fa-cocktail' → icone_type='fa' attendu, obtenu '{dict_fa['icone_type']}'"
        )
        assert dict_fa['icon'] == 'fa-cocktail'

        # Icone Material Symbols : pas de prefixe 'fa'
        # / Material Symbols icon: no 'fa' prefix
        assert dict_ms['icone_type'] == 'ms', (
            f"'local_bar' → icone_type='ms' attendu, obtenu '{dict_ms['icone_type']}'"
        )
        assert dict_ms['icon'] == 'local_bar'

        # Categorie sans icone : fallback FA avec fa-th
        # / Category without icon: FA fallback with fa-th
        assert dict_vide['icone_type'] == 'fa', (
            f"Categorie vide → icone_type='fa' attendu (fallback), obtenu '{dict_vide['icone_type']}'"
        )
        assert dict_vide['icon'] == 'fa-th', (
            f"Categorie vide → icon='fa-th' attendu (fallback), obtenu '{dict_vide['icon']}'"
        )


# ---------------------------------------------------------------------------
# Test 7 : LaboutikConfiguration — singleton et valeurs par defaut
# Test 7: LaboutikConfiguration — singleton and default values
# ---------------------------------------------------------------------------

def test_laboutik_configuration_singleton(tenant):
    """
    LaboutikConfiguration.get_solo() doit toujours retourner la meme instance.
    La valeur par defaut de taille_police_articles est un int.
    / LaboutikConfiguration.get_solo() must always return the same instance.
    The default value of taille_police_articles is an int.
    """
    with schema_context(TENANT_SCHEMA):
        from laboutik.models import LaboutikConfiguration

        # Deux appels successifs doivent retourner le meme pk
        # / Two successive calls must return the same pk
        config_1 = LaboutikConfiguration.get_solo()
        config_2 = LaboutikConfiguration.get_solo()

        assert config_1.pk == config_2.pk, (
            "get_solo() doit retourner le meme singleton a chaque appel"
        )

        # taille_police_articles doit etre un int
        # / taille_police_articles must be an int
        assert isinstance(config_1.taille_police_articles, int), (
            "taille_police_articles doit etre un int"
        )

        # Verification du __str__
        # / __str__ check
        assert str(config_1) == "LaBoutik Configuration", (
            f"__str__ attendu 'LaBoutik Configuration', obtenu '{str(config_1)}'"
        )


# ---------------------------------------------------------------------------
# Test 8 : Donnees de test create_test_pos_data — couleurs et icones presentes
# Test 8: Test data create_test_pos_data — colors and icons present
# ---------------------------------------------------------------------------

def test_donnees_test_pos_couleurs_et_icones(tenant):
    """
    Apres create_test_pos_data, les produits ont des couleurs et des icones connues.
    Ce test relance la commande pour s'assurer que les donnees sont dans l'etat attendu
    (evite les faux echecs dus a une modification manuelle via l'admin).
    Biere : fond #F59E0B, texte #000000, icone fa-beer (type FA).
    Coca  : fond #DC2626, texte #FFFFFF, icone fa-glass-whiskey (type FA).
    / After create_test_pos_data, products have known colors and icons.
    This test re-runs the command to ensure data is in the expected state
    (avoids false failures due to manual admin changes).
    Biere: bg #F59E0B, text #000000, icon fa-beer (FA type).
    Coca: bg #DC2626, text #FFFFFF, icon fa-glass-whiskey (FA type).
    """
    from django.core.management import call_command

    # Relancer create_test_pos_data pour remettre les donnees dans l'etat connu
    # / Re-run create_test_pos_data to reset data to the known state
    with schema_context(TENANT_SCHEMA):
        call_command('create_test_pos_data')

    with schema_context(TENANT_SCHEMA):
        from laboutik.models import PointDeVente
        from laboutik.views import _construire_donnees_articles

        pdv_bar = PointDeVente.objects.filter(name='Bar').first()
        if pdv_bar is None:
            pytest.skip("PDV 'Bar' introuvable apres create_test_pos_data")

        articles = _construire_donnees_articles(pdv_bar)

        # --- Biere ---
        biere = next((a for a in articles if a['name'] == 'Biere'), None)
        if biere is not None:
            assert biere['couleur_backgr'] == '#F59E0B', (
                f"Biere : fond attendu '#F59E0B', obtenu '{biere['couleur_backgr']}'"
            )
            assert biere['couleur_texte'] == '#000000', (
                f"Biere : texte attendu '#000000', obtenu '{biere['couleur_texte']}'"
            )
            assert biere['icone'] == 'fa-beer'
            assert biere['icone_type'] == 'fa'
            # Prix : 5.00 EUR = 500 centimes
            assert biere['prix'] == 500, f"Biere : prix attendu 500 centimes, obtenu {biere['prix']}"

        # --- Coca ---
        coca = next((a for a in articles if a['name'] == 'Coca'), None)
        if coca is not None:
            assert coca['couleur_backgr'] == '#DC2626', (
                f"Coca : fond attendu '#DC2626', obtenu '{coca['couleur_backgr']}'"
            )
            assert coca['couleur_texte'] == '#FFFFFF', (
                f"Coca : texte attendu '#FFFFFF', obtenu '{coca['couleur_texte']}'"
            )
            assert coca['icone'] == 'fa-glass-whiskey'
            assert coca['icone_type'] == 'fa'
            # Prix : 3.00 EUR = 300 centimes
            assert coca['prix'] == 300, f"Coca : prix attendu 300 centimes, obtenu {coca['prix']}"
