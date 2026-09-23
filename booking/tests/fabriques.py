"""
Fabriques des tests de l'app booking.
/ Factories for the booking app tests.

LOCALISATION : booking/tests/fabriques.py

Une ressource doit avoir un produit de catégorie « ressource » : `Resource.product` est
obligatoire. Les tests du moteur n'étudient pas les prix : ils reçoivent un produit avec un
seul tarif publié à 0 €. Une réservation y est donc gratuite, sans Stripe.
/ A resource needs a "resource" product (`Resource.product` is required). Engine tests don't
study prices: they get a product with a single published 0 € price (free booking, no Stripe).

Appeler à l'intérieur d'un schema_context(TENANT_SCHEMA), comme les autres fixtures.
/ Call inside a schema_context(TENANT_SCHEMA), like the other fixtures.
"""
from decimal import Decimal


def creer_produit_de_ressource(nom):
    """
    Crée un produit « ressource » et son tarif publié à 0 €. Rend le produit.
    Le nom porte le préfixe du fichier de test : le nettoyage le retrouve par ce préfixe.
    / Creates a resource product with its published 0 € price. Returns the product.
    The name carries the test file prefix, so the cleanup finds it.
    """
    from BaseBillet.models import Price, Product

    produit = Product.objects.create(name=nom, categorie_article=Product.RESOURCE)
    Price.objects.create(
        product=produit,
        name="Tarif gratuit",
        prix=Decimal("0.00"),
        publish=True,
    )
    return produit
