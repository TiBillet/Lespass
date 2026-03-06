"""
Cree des donnees de test POS pour le tenant courant.
Categories, produits avec tarifs, et points de vente.
/ Creates test POS data for the current tenant.
Categories, products with prices, and points of sale.

LOCALISATION : laboutik/management/commands/create_test_pos_data.py

Usage :
    docker exec lespass_django poetry run python manage.py create_test_pos_data
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import connection
from django.utils.translation import gettext_lazy as _

from BaseBillet.models import CategorieProduct, Product, Price
from laboutik.models import PointDeVente


class Command(BaseCommand):
    help = "Cree des donnees de test POS (categories, produits, prix, points de vente) pour le tenant courant."

    def handle(self, *args, **options):
        tenant_name = connection.tenant.schema_name
        self.stdout.write(f"Tenant : {tenant_name}")

        # --- 2 categories de produits ---
        # / 2 product categories
        categorie_bar, _ = CategorieProduct.objects.get_or_create(
            name="Bar",
            defaults={
                "icon": "bi-cup-straw",
                "couleur_texte": "#FFFFFF",
                "couleur_fond": "#3B82F6",
                "poid_liste": 0,
            },
        )
        categorie_restauration, _ = CategorieProduct.objects.get_or_create(
            name="Restauration",
            defaults={
                "icon": "bi-egg-fried",
                "couleur_texte": "#FFFFFF",
                "couleur_fond": "#EF4444",
                "poid_liste": 1,
            },
        )
        self.stdout.write(f"  Categories : {categorie_bar}, {categorie_restauration}")

        # --- 5 produits POS avec prix ---
        # / 5 POS products with prices
        products_data = [
            {
                "name": "Biere",
                "methode_caisse": Product.VENTE,
                "categorie_pos": categorie_bar,
                "couleur_fond_pos": "#F59E0B",
                "couleur_texte_pos": "#000000",
                "icon_pos": "bi-cup",
                "prix": Decimal("5.00"),
            },
            {
                "name": "Coca",
                "methode_caisse": Product.VENTE,
                "categorie_pos": categorie_bar,
                "couleur_fond_pos": "#DC2626",
                "couleur_texte_pos": "#FFFFFF",
                "icon_pos": "bi-cup-straw",
                "prix": Decimal("3.00"),
            },
            {
                "name": "Pizza",
                "methode_caisse": Product.VENTE,
                "categorie_pos": categorie_restauration,
                "couleur_fond_pos": "#16A34A",
                "couleur_texte_pos": "#FFFFFF",
                "icon_pos": "bi-circle",
                "prix": Decimal("12.00"),
            },
            {
                "name": "Cafe",
                "methode_caisse": Product.VENTE,
                "categorie_pos": categorie_bar,
                "couleur_fond_pos": "#78350F",
                "couleur_texte_pos": "#FFFFFF",
                "icon_pos": "bi-cup-hot",
                "prix": Decimal("2.00"),
            },
            {
                "name": "Eau",
                "methode_caisse": Product.VENTE,
                "categorie_pos": categorie_bar,
                "couleur_fond_pos": "#0EA5E9",
                "couleur_texte_pos": "#FFFFFF",
                "icon_pos": "bi-droplet",
                "prix": Decimal("1.50"),
            },
        ]

        for product_data in products_data:
            prix_value = product_data.pop("prix")
            product, created = Product.objects.get_or_create(
                name=product_data["name"],
                defaults=product_data,
            )
            if created:
                # Cree le tarif associe (prix en euros, DecimalField)
                # / Create associated price (in euros, DecimalField)
                Price.objects.create(
                    product=product,
                    name=f"Tarif {product.name}",
                    prix=prix_value,
                )
                self.stdout.write(f"  Produit cree : {product.name} ({prix_value} EUR)")
            else:
                # Met a jour les champs POS si le produit existe deja
                # / Update POS fields if product already exists
                pos_fields_to_update = {
                    key: value for key, value in product_data.items()
                    if key != "name"
                }
                for field_name, field_value in pos_fields_to_update.items():
                    setattr(product, field_name, field_value)
                product.save(update_fields=list(pos_fields_to_update.keys()))
                self.stdout.write(f"  Produit mis a jour : {product.name}")

        # --- 2 points de vente ---
        # / 2 points of sale
        pdv_bar, _ = PointDeVente.objects.get_or_create(
            name="Bar",
            defaults={
                "comportement": PointDeVente.DIRECT,
                "service_direct": True,
                "afficher_les_prix": True,
                "accepte_especes": True,
                "accepte_carte_bancaire": True,
                "accepte_cheque": False,
                "accepte_commandes": False,
                "poid_liste": 0,
            },
        )
        pdv_restaurant, _ = PointDeVente.objects.get_or_create(
            name="Restaurant",
            defaults={
                "comportement": PointDeVente.DIRECT,
                "service_direct": True,
                "afficher_les_prix": True,
                "accepte_especes": True,
                "accepte_carte_bancaire": True,
                "accepte_cheque": False,
                "accepte_commandes": True,
                "poid_liste": 1,
            },
        )

        # Associe les produits aux points de vente
        # / Link products to points of sale
        all_pos_products = Product.objects.filter(methode_caisse__isnull=False)
        bar_products = all_pos_products.filter(categorie_pos=categorie_bar)
        restaurant_products = all_pos_products.filter(categorie_pos=categorie_restauration)

        pdv_bar.products.set(bar_products)
        pdv_bar.categories.set([categorie_bar])

        pdv_restaurant.products.set(all_pos_products)
        pdv_restaurant.categories.set([categorie_bar, categorie_restauration])

        self.stdout.write(f"  Points de vente : {pdv_bar} ({bar_products.count()} produits), "
                          f"{pdv_restaurant} ({all_pos_products.count()} produits)")

        self.stdout.write(self.style.SUCCESS("Donnees de test POS creees avec succes."))
