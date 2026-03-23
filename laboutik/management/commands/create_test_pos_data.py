"""
Cree des donnees de test POS pour le tenant courant.
Categories, produits avec tarifs, points de vente, et cartes primaires (si TEST=1).
/ Creates test POS data for the current tenant.
Categories, products with prices, points of sale, and primary cards (if TEST=1).

LOCALISATION : laboutik/management/commands/create_test_pos_data.py

Icones : FontAwesome 5 Free (solid). Le champ icon contient le nom de l'icone
sans le prefixe "fas", par exemple "fa-beer".
Les templates laboutik utilisent <i class="fas {{ icon }}"></i>.
/ Icons: FontAwesome 5 Free (solid). The icon field contains the icon name
without the "fas" prefix, e.g. "fa-beer".
Laboutik templates use <i class="fas {{ icon }}"></i>.

Usage :
    docker exec lespass_django poetry run python manage.py create_test_pos_data
"""
import uuid as uuid_module
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection
from django.utils.translation import gettext_lazy as _
from django_tenants.utils import schema_context

from BaseBillet.models import CategorieProduct, Product, Price
from Customers.models import Client
from laboutik.models import CartePrimaire, PointDeVente
from QrcodeCashless.models import CarteCashless, Detail


class Command(BaseCommand):
    help = "Cree des donnees de test POS (categories, produits, prix, points de vente) pour le tenant courant."

    def handle(self, *args, **options):
        # Si on est deja dans un tenant_context (schema != "public"), on l'utilise.
        # Sinon (lancement standalone via docker exec), on prend le premier tenant non-public.
        # ATTENTION : "relation does not exist" = on est sur le schema public,
        # les tables TENANT_APPS (BaseBillet, laboutik…) n'y existent pas.
        # / If already inside a tenant_context (schema != "public"), use it.
        # Otherwise (standalone launch via docker exec), pick the first non-public tenant.
        # WARNING: "relation does not exist" = running on the public schema,
        # TENANT_APPS tables (BaseBillet, laboutik…) don't exist there.
        schema = connection.schema_name
        if schema == "public":
            first_tenant = Client.objects.exclude(schema_name="public").first()
            if not first_tenant:
                self.stderr.write(self.style.ERROR("Aucun tenant non-public trouve."))
                return
            schema = first_tenant.schema_name
            self.stdout.write(f"Schema public detecte, bascule vers le tenant : {schema}")

        with schema_context(schema):
            self.stdout.write(f"Tenant : {schema}")

            # --- 5 categories de produits ---
            # update_or_create pour mettre a jour l'icone meme si la categorie existait avant.
            # / update_or_create to also update the icon on already-existing categories.
            categorie_bar, _ = CategorieProduct.objects.update_or_create(
                name="Bar",
                defaults={
                    "icon": "fa-cocktail",
                    "couleur_texte": "#FFFFFF",
                    "couleur_fond": "#3B82F6",
                    "poid_liste": 0,
                },
            )
            categorie_restauration, _ = CategorieProduct.objects.update_or_create(
                name="Restauration",
                defaults={
                    "icon": "fa-utensils",
                    "couleur_texte": "#FFFFFF",
                    "couleur_fond": "#EF4444",
                    "poid_liste": 1,
                },
            )
            categorie_boissons_chaudes, _ = CategorieProduct.objects.update_or_create(
                name="Boissons chaudes",
                defaults={
                    "icon": "fa-coffee",
                    "couleur_texte": "#FFFFFF",
                    "couleur_fond": "#78350F",
                    "poid_liste": 2,
                },
            )
            categorie_snacks, _ = CategorieProduct.objects.update_or_create(
                name="Snacks",
                defaults={
                    "icon": "fa-cookie",
                    "couleur_texte": "#000000",
                    "couleur_fond": "#F59E0B",
                    "poid_liste": 3,
                },
            )
            categorie_vins, _ = CategorieProduct.objects.update_or_create(
                name="Vins & Spiritueux",
                defaults={
                    "icon": "fa-wine-glass-alt",
                    "couleur_texte": "#FFFFFF",
                    "couleur_fond": "#7C3AED",
                    "poid_liste": 4,
                },
            )
            categorie_cashless, _ = CategorieProduct.objects.update_or_create(
                name="Cashless",
                defaults={
                    "icon": "fa-wallet",
                    "couleur_texte": "#FFFFFF",
                    "couleur_fond": "#10B981",
                    "poid_liste": 5,
                },
            )
            self.stdout.write(
                f"  Categories : {categorie_bar}, {categorie_restauration}, "
                f"{categorie_boissons_chaudes}, {categorie_snacks}, {categorie_vins}, "
                f"{categorie_cashless}"
            )

            # --- Produits POS avec prix et icones ---
            # Chaque produit a une couleur de fond, une couleur de texte et une icone FontAwesome 5.
            # / POS products with prices and icons.
            # Each product has a background color, a text color and a FontAwesome 5 icon.
            products_data = [
                # --- Bar ---
                {
                    "name": "Biere",
                    "methode_caisse": Product.VENTE,
                    "categorie_pos": categorie_bar,
                    "couleur_fond_pos": "#F59E0B",
                    "couleur_texte_pos": "#000000",
                    "icon_pos": "fa-beer",
                    "prix": Decimal("5.00"),
                },
                {
                    "name": "Coca",
                    "methode_caisse": Product.VENTE,
                    "categorie_pos": categorie_bar,
                    "couleur_fond_pos": "#DC2626",
                    "couleur_texte_pos": "#FFFFFF",
                    "icon_pos": "fa-glass-whiskey",
                    "prix": Decimal("3.00"),
                },
                {
                    "name": "Eau",
                    "methode_caisse": Product.VENTE,
                    "categorie_pos": categorie_bar,
                    "couleur_fond_pos": "#0EA5E9",
                    "couleur_texte_pos": "#FFFFFF",
                    "icon_pos": "fa-tint",
                    "prix": Decimal("1.50"),
                },
                {
                    "name": "Jus d'orange",
                    "methode_caisse": Product.VENTE,
                    "categorie_pos": categorie_bar,
                    "couleur_fond_pos": "#F97316",
                    "couleur_texte_pos": "#000000",
                    "icon_pos": "fa-lemon",
                    "prix": Decimal("3.50"),
                },
                {
                    "name": "Limonade",
                    "methode_caisse": Product.VENTE,
                    "categorie_pos": categorie_bar,
                    "couleur_fond_pos": "#FBBF24",
                    "couleur_texte_pos": "#000000",
                    "icon_pos": "fa-glass-cheers",
                    "prix": Decimal("2.50"),
                },
                # --- Restauration ---
                {
                    "name": "Pizza",
                    "methode_caisse": Product.VENTE,
                    "categorie_pos": categorie_restauration,
                    "couleur_fond_pos": "#16A34A",
                    "couleur_texte_pos": "#FFFFFF",
                    "icon_pos": "fa-pizza-slice",
                    "prix": Decimal("12.00"),
                },
                {
                    "name": "Burger",
                    "methode_caisse": Product.VENTE,
                    "categorie_pos": categorie_restauration,
                    "couleur_fond_pos": "#B45309",
                    "couleur_texte_pos": "#FFFFFF",
                    "icon_pos": "fa-utensils",
                    "prix": Decimal("11.00"),
                },
                {
                    "name": "Sandwich",
                    "methode_caisse": Product.VENTE,
                    "categorie_pos": categorie_restauration,
                    "couleur_fond_pos": "#D97706",
                    "couleur_texte_pos": "#000000",
                    "icon_pos": "fa-bread-slice",
                    "prix": Decimal("8.00"),
                },
                {
                    "name": "Salade",
                    "methode_caisse": Product.VENTE,
                    "categorie_pos": categorie_restauration,
                    "couleur_fond_pos": "#22C55E",
                    "couleur_texte_pos": "#000000",
                    "icon_pos": "fa-leaf",
                    "prix": Decimal("7.00"),
                },
                # --- Boissons chaudes ---
                {
                    "name": "Cafe",
                    "methode_caisse": Product.VENTE,
                    "categorie_pos": categorie_boissons_chaudes,
                    "couleur_fond_pos": "#78350F",
                    "couleur_texte_pos": "#FFFFFF",
                    "icon_pos": "fa-coffee",
                    "prix": Decimal("2.00"),
                },
                {
                    "name": "The",
                    "methode_caisse": Product.VENTE,
                    "categorie_pos": categorie_boissons_chaudes,
                    "couleur_fond_pos": "#15803D",
                    "couleur_texte_pos": "#FFFFFF",
                    "icon_pos": "fa-mug-hot",
                    "prix": Decimal("2.50"),
                },
                {
                    "name": "Cappuccino",
                    "methode_caisse": Product.VENTE,
                    "categorie_pos": categorie_boissons_chaudes,
                    "couleur_fond_pos": "#92400E",
                    "couleur_texte_pos": "#FFFFFF",
                    "icon_pos": "fa-coffee",
                    "prix": Decimal("3.50"),
                },
                # --- Snacks ---
                {
                    "name": "Chips",
                    "methode_caisse": Product.VENTE,
                    "categorie_pos": categorie_snacks,
                    "couleur_fond_pos": "#EAB308",
                    "couleur_texte_pos": "#000000",
                    "icon_pos": "fa-cookie-bite",
                    "prix": Decimal("2.00"),
                },
                {
                    "name": "Cacahuetes",
                    "methode_caisse": Product.VENTE,
                    "categorie_pos": categorie_snacks,
                    "couleur_fond_pos": "#84CC16",
                    "couleur_texte_pos": "#000000",
                    "icon_pos": "fa-seedling",
                    "prix": Decimal("1.50"),
                },
                {
                    "name": "Cookies",
                    "methode_caisse": Product.VENTE,
                    "categorie_pos": categorie_snacks,
                    "couleur_fond_pos": "#D97706",
                    "couleur_texte_pos": "#FFFFFF",
                    "icon_pos": "fa-cookie",
                    "prix": Decimal("2.00"),
                },
                # --- Vins & Spiritueux ---
                {
                    "name": "Vin rouge",
                    "methode_caisse": Product.VENTE,
                    "categorie_pos": categorie_vins,
                    "couleur_fond_pos": "#7C3AED",
                    "couleur_texte_pos": "#FFFFFF",
                    "icon_pos": "fa-wine-glass-alt",
                    "prix": Decimal("5.00"),
                },
                {
                    "name": "Vin blanc",
                    "methode_caisse": Product.VENTE,
                    "categorie_pos": categorie_vins,
                    "couleur_fond_pos": "#D1FAE5",
                    "couleur_texte_pos": "#000000",
                    "icon_pos": "fa-wine-glass",
                    "prix": Decimal("5.00"),
                },
                {
                    "name": "Pastis",
                    "methode_caisse": Product.VENTE,
                    "categorie_pos": categorie_vins,
                    "couleur_fond_pos": "#FBBF24",
                    "couleur_texte_pos": "#000000",
                    "icon_pos": "fa-glass-whiskey",
                    "prix": Decimal("4.00"),
                },
                # --- Cashless : recharges ---
                # / Cashless: top-ups
                {
                    "name": "Recharge 10€",
                    "methode_caisse": Product.RECHARGE_EUROS,
                    "categorie_pos": categorie_cashless,
                    "couleur_fond_pos": "#10B981",
                    "couleur_texte_pos": "#FFFFFF",
                    "icon_pos": "fa-coins",
                    "prix": Decimal("10.00"),
                },
                {
                    "name": "Recharge 20€",
                    "methode_caisse": Product.RECHARGE_EUROS,
                    "categorie_pos": categorie_cashless,
                    "couleur_fond_pos": "#059669",
                    "couleur_texte_pos": "#FFFFFF",
                    "icon_pos": "fa-coins",
                    "prix": Decimal("20.00"),
                },
                {
                    "name": "Cadeau 5€",
                    "methode_caisse": Product.RECHARGE_CADEAU,
                    "categorie_pos": categorie_cashless,
                    "couleur_fond_pos": "#F472B6",
                    "couleur_texte_pos": "#FFFFFF",
                    "icon_pos": "fa-gift",
                    "prix": Decimal("5.00"),
                },
                {
                    "name": "Cadeau 10€",
                    "methode_caisse": Product.RECHARGE_CADEAU,
                    "categorie_pos": categorie_cashless,
                    "couleur_fond_pos": "#EC4899",
                    "couleur_texte_pos": "#FFFFFF",
                    "icon_pos": "fa-gift",
                    "prix": Decimal("10.00"),
                },
                {
                    "name": "Temps 1h",
                    "methode_caisse": Product.RECHARGE_TEMPS,
                    "categorie_pos": categorie_cashless,
                    "couleur_fond_pos": "#8B5CF6",
                    "couleur_texte_pos": "#FFFFFF",
                    "icon_pos": "fa-clock",
                    "prix": Decimal("1.00"),
                },
            ]

            for product_data in products_data:
                prix_value = product_data.pop("prix")
                # subscription_type est un champ de Price, pas de Product
                # / subscription_type is a Price field, not a Product field
                subscription_type = product_data.pop("subscription_type", Price.NA)
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
                        subscription_type=subscription_type,
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

            # --- Produits adhesion ---
            # Les produits adhesion ne sont PAS crees ici.
            # Ils sont crees par demo_data_v2.py (ou par l'admin dans l'interface).
            # Le PV de type ADHESION les charge dynamiquement via
            # Product.objects.filter(categorie_article=ADHESION, publish=True).
            # / Membership products are NOT created here.
            # They are created by demo_data_v2.py (or by admin in the interface).
            # The ADHESION-typed POS loads them dynamically.
            nb_adhesions = Product.objects.filter(
                categorie_article=Product.ADHESION, publish=True,
            ).count()
            self.stdout.write(f"  Adhesions existantes : {nb_adhesions} produit(s) publies")

            # --- 3 points de vente ---
            # update_or_create pour mettre a jour l'icone meme si le PDV existait avant.
            # get_or_create n'applique les defaults qu'a la creation.
            # / update_or_create to also update the icon on already-existing POS.
            # get_or_create only applies defaults on creation.
            pdv_bar, _ = PointDeVente.objects.update_or_create(
                name="Bar",
                defaults={
                    "icon": "fa-cocktail",
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
            pdv_restaurant, _ = PointDeVente.objects.update_or_create(
                name="Restaurant",
                defaults={
                    "icon": "fa-utensils",
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
            pdv_terrasse, _ = PointDeVente.objects.update_or_create(
                name="Terrasse",
                defaults={
                    "icon": "fa-umbrella-beach",
                    "comportement": PointDeVente.DIRECT,
                    "service_direct": False,
                    "afficher_les_prix": True,
                    "accepte_especes": True,
                    "accepte_carte_bancaire": True,
                    "accepte_cheque": False,
                    "accepte_commandes": True,
                    "poid_liste": 2,
                },
            )

            # PV Cashless : charge automatiquement les recharges (type CASHLESS)
            # Les articles du M2M sont charges en plus.
            # / Cashless POS: auto-loads top-up products (CASHLESS type)
            # M2M articles are loaded in addition.
            pdv_cashless, _ = PointDeVente.objects.update_or_create(
                name="Cashless",
                defaults={
                    "icon": "fa-wallet",
                    "comportement": PointDeVente.CASHLESS,
                    "service_direct": True,
                    "afficher_les_prix": True,
                    "accepte_especes": False,
                    "accepte_carte_bancaire": False,
                    "accepte_cheque": False,
                    "accepte_commandes": False,
                    "poid_liste": 3,
                },
            )

            # PV Adhesion : charge automatiquement tous les produits adhesion (type ADHESION)
            # Les articles du M2M sont charges en plus.
            # / Membership POS: auto-loads all membership products (ADHESION type)
            # M2M articles are loaded in addition.
            pdv_adhesion, _ = PointDeVente.objects.update_or_create(
                name="Adhesions",
                defaults={
                    "icon": "fa-id-card",
                    "comportement": PointDeVente.ADHESION,
                    "service_direct": True,
                    "afficher_les_prix": True,
                    "accepte_especes": True,
                    "accepte_carte_bancaire": True,
                    "accepte_cheque": False,
                    "accepte_commandes": False,
                    "poid_liste": 4,
                },
            )
            # Ajouter les produits adhesion publies au M2M du PV
            # / Add published membership products to the POS M2M
            produits_adhesion = Product.objects.filter(
                categorie_article=Product.ADHESION, publish=True
            )
            pdv_adhesion.products.add(*produits_adhesion)

            # PV Mix : article classique (Biere) + recharge (Recharge 10€) + 1 adhesion dediee.
            # Sert a tester les paniers mixtes (VT + RE + AD dans le meme panier).
            # On cree UN produit adhesion dedie "Adhesion Test Mix" pour ne pas
            # ratisser les centaines d'adhesions du tenant.
            # / Mix POS: classic article (Beer) + top-up (Recharge 10€) + 1 dedicated membership.
            # Used to test mixed carts (VT + RE + AD in the same cart).
            # We create ONE dedicated membership product "Adhesion Test Mix" to avoid
            # pulling in hundreds of tenant memberships.
            produit_adhesion_mix, created_adh_mix = Product.objects.get_or_create(
                name="Adhesion Test Mix",
                defaults={
                    "categorie_article": Product.ADHESION,
                    "publish": True,
                    "couleur_fond_pos": "#6366F1",
                    "couleur_texte_pos": "#FFFFFF",
                    "icon_pos": "fa-id-card",
                },
            )
            if created_adh_mix:
                Price.objects.create(
                    product=produit_adhesion_mix,
                    name="Annuelle Test",
                    prix=Decimal("20.00"),
                    subscription_type=Price.YEAR,
                )
                self.stdout.write(f"  Produit adhesion Mix cree : {produit_adhesion_mix.name}")

            pdv_mix, _ = PointDeVente.objects.update_or_create(
                name="Mix",
                defaults={
                    "icon": "fa-blender",
                    "comportement": PointDeVente.DIRECT,
                    "service_direct": True,
                    "afficher_les_prix": True,
                    "accepte_especes": True,
                    "accepte_carte_bancaire": True,
                    "accepte_cheque": False,
                    "accepte_commandes": False,
                    "poid_liste": 5,
                },
            )
            # Produits du PV Mix : Biere (VT) + Recharge 10€ (RE) + Adhesion Test Mix (AD)
            # .set() remplace tout le M2M — pas d'accumulation entre les runs.
            # / Mix POS products: Beer (VT) + Recharge 10€ (RE) + Adhesion Test Mix (AD)
            # .set() replaces the whole M2M — no accumulation between runs.
            produit_biere = Product.objects.filter(name="Biere", methode_caisse=Product.VENTE).first()
            produit_recharge_10 = Product.objects.filter(name="Recharge 10€", methode_caisse=Product.RECHARGE_EUROS).first()
            produits_mix = [p for p in [produit_biere, produit_recharge_10, produit_adhesion_mix] if p]
            pdv_mix.products.set(produits_mix)
            pdv_mix.categories.set([categorie_bar, categorie_cashless])

            # --- PV Billetterie (type BILLETTERIE) ---
            # Le PV de type BILLETTERIE construit ses articles depuis les events futurs.
            # Pas besoin de creer des Products billet ici — les events de demo_data_v2
            # fournissent les articles automatiquement.
            # Les articles M2M (Biere, Eau) sont charges en plus.
            # / BILLETTERIE POS builds articles from future events.
            # No need to create ticket Products here — demo_data_v2 events
            # provide articles automatically.
            # M2M articles (Beer, Water) are loaded in addition.
            categorie_billetterie, _ = CategorieProduct.objects.update_or_create(
                name="Billetterie",
                defaults={
                    "icon": "fa-ticket-alt",
                    "couleur_texte": "#FFFFFF",
                    "couleur_fond": "#7C3AED",
                    "poid_liste": 6,
                },
            )

            produit_eau = Product.objects.filter(name="Eau", methode_caisse=Product.VENTE).first()
            pdv_festival, _ = PointDeVente.objects.update_or_create(
                name="Accueil Festival",
                defaults={
                    "icon": "fa-ticket-alt",
                    "comportement": PointDeVente.BILLETTERIE,
                    "service_direct": True,
                    "afficher_les_prix": True,
                    "accepte_especes": True,
                    "accepte_carte_bancaire": True,
                    "accepte_cheque": False,
                    "accepte_commandes": False,
                    "poid_liste": 6,
                },
            )
            # Articles M2M : boissons classiques disponibles en plus des billets
            # / M2M articles: classic drinks available in addition to tickets
            produits_festival = [p for p in [produit_biere, produit_eau] if p]
            pdv_festival.products.set(produits_festival)
            pdv_festival.categories.set([categorie_billetterie, categorie_bar])

            self.stdout.write(
                f"  PV Accueil Festival (BILLETTERIE) : {pdv_festival.products.count()} articles M2M"
            )

            # Associe les produits aux points de vente
            # / Link products to points of sale
            all_pos_products = Product.objects.filter(methode_caisse__isnull=False)
            bar_products = all_pos_products.filter(
                categorie_pos__in=[categorie_bar, categorie_vins, categorie_snacks]
            )
            restaurant_products = all_pos_products.filter(
                categorie_pos__in=[categorie_restauration, categorie_boissons_chaudes]
            )
            cashless_products = all_pos_products.filter(
                categorie_pos=categorie_cashless,
            )

            # Bar : boissons froides, vins, snacks
            # / Bar: cold drinks, wines, snacks
            pdv_bar.products.set(bar_products)
            pdv_bar.categories.set([categorie_bar, categorie_vins, categorie_snacks])

            # Restaurant : plats et boissons chaudes
            # / Restaurant: dishes and hot drinks
            pdv_restaurant.products.set(restaurant_products)
            pdv_restaurant.categories.set([categorie_restauration, categorie_boissons_chaudes])

            # Terrasse : tout sauf les boissons chaudes et cashless
            # / Terrasse: everything except hot drinks and cashless
            terrasse_products = all_pos_products.filter(
                categorie_pos__in=[categorie_bar, categorie_restauration, categorie_vins, categorie_snacks]
            )
            pdv_terrasse.products.set(terrasse_products)
            pdv_terrasse.categories.set([categorie_bar, categorie_restauration, categorie_vins, categorie_snacks])

            # Cashless : recharges uniquement (les adhesions sont dans le PV Adhesion)
            # / Cashless: top-ups only (memberships are in the Adhesion POS)
            pdv_cashless.products.set(cashless_products)
            pdv_cashless.categories.set([categorie_cashless])

            self.stdout.write(
                f"  Points de vente : "
                f"{pdv_bar} ({bar_products.count()} produits), "
                f"{pdv_restaurant} ({restaurant_products.count()} produits), "
                f"{pdv_terrasse} ({terrasse_products.count()} produits), "
                f"{pdv_cashless} ({cashless_products.count()} produits), "
                f"{pdv_adhesion} ({pdv_adhesion.products.count()} produits), "
                f"{pdv_mix} ({pdv_mix.products.count()} produits), "
                f"{pdv_festival} ({pdv_festival.products.count()} produits)"
            )

            # --- Cartes primaires (uniquement en mode TEST) ---
            # Les cartes NFC de test permettent de simuler le scan en dev.
            # Les tag_id viennent de settings (DEMO_TAGID_*).
            # / Primary cards (TEST mode only)
            # Test NFC cards allow simulating scans in dev.
            if not settings.TEST:
                self.stdout.write("  Mode TEST inactif : pas de creation de cartes primaires.")
                self.stdout.write(self.style.SUCCESS("Donnees de test POS creees avec succes."))
                return

            self.stdout.write("  Mode TEST actif : creation des cartes primaires...")

            # Recuperer le vrai Client (pas FakeTenant) pour la FK Detail.origine
            # Detail et CarteCashless sont en SHARED_APPS (schema public).
            # / Get the real Client (not FakeTenant) for Detail.origine FK
            tenant_client = Client.objects.get(schema_name=connection.schema_name)

            # Un Detail (batch de cartes) pour regrouper les cartes de test
            # / A Detail (card batch) to group test cards
            detail_test, _ = Detail.objects.get_or_create(
                slug="test-pos-cards",
                defaults={
                    "base_url": "test.tibillet.localhost",
                    "generation": 1,
                    "origine": tenant_client,
                },
            )

            # Carte primaire (caissier/manager) — liee a tous les PV
            # / Primary card (cashier/manager) — linked to all POS
            tag_id_cm = getattr(settings, "DEMO_TAGID_CM", "A49E8E2A")
            carte_cm, created_cm = CarteCashless.objects.get_or_create(
                tag_id=tag_id_cm,
                defaults={
                    "uuid": uuid_module.uuid4(),
                    "number": tag_id_cm,
                    "detail": detail_test,
                },
            )
            carte_primaire_cm, _ = CartePrimaire.objects.get_or_create(
                carte=carte_cm,
                defaults={"edit_mode": True},
            )
            carte_primaire_cm.points_de_vente.set([pdv_bar, pdv_restaurant, pdv_terrasse, pdv_cashless, pdv_adhesion, pdv_mix, pdv_festival])
            if created_cm:
                self.stdout.write(f"  Carte primaire creee : {tag_id_cm} (tous les PV, edit_mode=True)")
            else:
                self.stdout.write(f"  Carte primaire existante : {tag_id_cm}")

            # 2 cartes client (pour tester les paiements NFC en Phase 3)
            # Les tag_id par defaut correspondent au .env de test.
            # / 2 client cards (for testing NFC payments in Phase 3)
            client_tags = [
                getattr(settings, "DEMO_TAGID_CLIENT1", "52BE6543"),
                getattr(settings, "DEMO_TAGID_CLIENT2", "33BC1DAA"),
            ]
            for tag_id_client in client_tags:
                carte_client, created_client = CarteCashless.objects.get_or_create(
                    tag_id=tag_id_client,
                    defaults={
                        "uuid": uuid_module.uuid4(),
                        "number": tag_id_client,
                        "detail": detail_test,
                    },
                )
                if created_client:
                    self.stdout.write(f"  Carte client creee : {tag_id_client}")
                else:
                    self.stdout.write(f"  Carte client existante : {tag_id_client}")

            # Carte client 3 "jetable" — remise a zero a chaque run en mode DEBUG.
            # Utilisee par les tests Playwright pour avoir une carte propre a chaque test.
            # En mode DEBUG, son user et son wallet_ephemere sont supprimes.
            # / Client card 3 "disposable" — reset on each run in DEBUG mode.
            # Used by Playwright tests to have a clean card for each test.
            # In DEBUG mode, its user and wallet_ephemere are removed.
            tag_id_client3 = getattr(settings, "DEMO_TAGID_CLIENT3", "D74B1B5D")
            carte_client3, created_client3 = CarteCashless.objects.get_or_create(
                tag_id=tag_id_client3,
                defaults={
                    "uuid": uuid_module.uuid4(),
                    "number": tag_id_client3,
                    "detail": detail_test,
                },
            )
            if created_client3:
                self.stdout.write(f"  Carte client 3 (jetable) creee : {tag_id_client3}")
            else:
                self.stdout.write(f"  Carte client 3 (jetable) existante : {tag_id_client3}")

            # Reset de la carte 3 en mode DEBUG
            # / Reset card 3 in DEBUG mode
            if settings.DEBUG:
                from laboutik.utils.test_helpers import reset_carte
                reset_carte(tag_id_client3)
                self.stdout.write(f"  Carte 3 remise a zero (DEBUG=True)")

            self.stdout.write(self.style.SUCCESS("Donnees de test POS creees avec succes."))
