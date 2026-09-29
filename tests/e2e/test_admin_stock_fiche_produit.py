"""
Tests E2E : section Stock de la fiche produit de caisse (option A)
et colonne Stock de la liste (option B).
/ E2E tests: POS product page Stock section (A) and list Stock column (B).

LOCALISATION : tests/e2e/test_admin_stock_fiche_produit.py

Ce que pytest ne peut pas vérifier (pas de navigateur) :
- une réception depuis la fiche met à jour le stock affiché, sans recharger ;
- Entrée dans le champ Quantité ne soumet PAS le formulaire produit ;
- taper une quantité ne déclenche pas l'alerte « modifications non enregistrées » ;
- le badge de la liste ouvre la fiche sur #section-stock.
/ What pytest cannot check: HTMX swap, Enter key, unsaved warning, anchor link.

Code testé : Administration/admin/stock_fiche_produit.py,
Administration/templates/admin/inventaire/stock_actions*.html

LANCEMENT / RUN :
    docker exec lespass_django poetry run pytest tests/e2e/test_admin_stock_fiche_produit.py -v -s
"""

import uuid
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.e2e


@pytest.fixture
def produit_caisse_avec_stock(django_shell):
    """
    Produit de caisse avec 5 pièces en stock. Supprimé après le test.
    Base dev partagée : nom unique. Créé via le shell Django du tenant lespass.
    / POS product with 5 units in stock, created via the Django shell. Deleted after.
    """
    nom_du_produit = f"E2E stock fiche {uuid.uuid4().hex[:8]}"
    identifiant_du_produit = django_shell(
        "from BaseBillet.models import Product; "
        "from inventaire.models import Stock; "
        f"p = Product.objects.create(name='{nom_du_produit}', methode_caisse=Product.VENTE); "
        "Stock.objects.create(product=p, quantite=5, unite='UN'); "
        "print(p.pk)"
    ).splitlines()[-1]

    yield SimpleNamespace(pk=identifiant_du_produit, name=nom_du_produit)

    django_shell(
        "from BaseBillet.models import Product; "
        f"Product.objects.filter(pk='{identifiant_du_produit}').delete()"
    )


def test_reception_depuis_la_fiche_produit_met_a_jour_le_stock(
    page, login_as_admin, produit_caisse_avec_stock
):
    """
    Réception de 10 depuis la section Stock : le stock affiché passe de 5 à 15
    sans recharger la page.
    / Reception of 10 from the Stock section: shown stock goes 5 → 15, no reload.
    """
    login_as_admin(page)
    page.goto(
        f"/admin/BaseBillet/posproduct/{produit_caisse_avec_stock.pk}/change/#section-stock"
    )

    quantite_affichee = page.locator('[data-testid="stock-actuel-quantite"]')
    assert "5" in quantite_affichee.inner_text()

    page.locator('[data-testid="input-quantite-action"]').fill("10")
    page.locator('[data-testid="btn-reception"]').click()

    page.locator('[data-testid="stock-action-success"]').wait_for(timeout=10000)
    assert "15" in page.locator('[data-testid="stock-actuel-quantite"]').inner_text()
    # Toujours sur la fiche : le produit n'a pas été soumis
    # / Still on the product page: the product form was not submitted
    assert f"/{produit_caisse_avec_stock.pk}/change/" in page.url


def test_entree_dans_quantite_ne_soumet_pas_le_produit(
    page, login_as_admin, produit_caisse_avec_stock
):
    """
    Entrée dans le champ Quantité : aucune navigation, aucun mouvement.
    Aucune alerte « modifications non enregistrées » en quittant la page.
    / Enter in Quantity: no navigation, no movement, no unsaved warning.
    """
    login_as_admin(page)
    page.goto(f"/admin/BaseBillet/posproduct/{produit_caisse_avec_stock.pk}/change/")

    requetes_post_envoyees = []
    page.on(
        "request",
        lambda requete: (
            requetes_post_envoyees.append(requete.url)
            if requete.method == "POST"
            else None
        ),
    )

    champ_quantite = page.locator('[data-testid="input-quantite-action"]')
    champ_quantite.fill("3")
    champ_quantite.press("Enter")
    page.wait_for_timeout(800)

    assert requetes_post_envoyees == []
    assert f"/{produit_caisse_avec_stock.pk}/change/" in page.url

    # Unfold ouvrirait une boîte « quitter la page ? » si le formulaire était marqué modifié
    # / Unfold would open a "leave page?" dialog if the form were marked dirty
    boites_de_dialogue_ouvertes = []
    page.on(
        "dialog",
        lambda boite: (boites_de_dialogue_ouvertes.append(boite.type), boite.accept()),
    )
    page.goto("/admin/BaseBillet/posproduct/")
    assert boites_de_dialogue_ouvertes == []


def test_badge_de_la_liste_ouvre_la_section_stock(
    page, login_as_admin, produit_caisse_avec_stock
):
    """Clic sur le badge Stock de la liste → fiche produit, ancre #section-stock."""
    login_as_admin(page)
    page.goto(f"/admin/BaseBillet/posproduct/?q={produit_caisse_avec_stock.name}")

    badge = page.locator(
        f'[data-testid="product-list-stock-{produit_caisse_avec_stock.pk}"]'
    )
    assert "5" in badge.inner_text()
    badge.click()
    page.wait_for_url("**#section-stock")
    assert page.locator('[data-testid="product-section-stock"]').is_visible()
