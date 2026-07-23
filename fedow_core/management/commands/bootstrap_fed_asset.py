"""
Management command bootstrap_fed_asset.
Cree l'infrastructure minimale pour la recharge FED V2 :
- Tenant federation_fed (categorie Client.FED)
- Root wallet (pot central)
- Asset FED unique
- Product et Price de recharge (dans le schema federation_fed)

/ Creates minimal infrastructure for FED V2 refill:
- federation_fed tenant (Client.FED category)
- Root wallet (central pot)
- Unique FED Asset
- Refill Product and Price (in federation_fed schema)

LOCALISATION : fedow_core/management/commands/bootstrap_fed_asset.py

CHANTIER EN COURS — NE PAS LANCER AVANT LA MIGRATION.
/ WORK IN PROGRESS — DO NOT RUN BEFORE THE MIGRATION.

Cette commande prepare l'apres-migration, quand la monnaie federee du reseau
sera servie par le moteur local. Aujourd'hui elle est servie par le Fedow
distant, et un asset FED local serait pris pour elle par la cascade de paiement
du point de vente et par le remboursement en especes de la caisse.

Deux choses l'empechent de s'executer, et c'est voulu :

- `Asset.save()` leve `AssetFedLocalInterdit` sur la categorie FED, sauf si le
  reglage `FEDOW_AUTORISER_ASSET_FED_LOCAL` est actif ;
- `Client.FED`, utilise plus bas pour la categorie du tenant, n'existe pas
  encore dans `Customers.models.Client`.

Aucun appel automatique n'existe : ni entrypoint, ni cron, ni migration. Le seul
appel du depot, dans `create_test_pos_data.py`, est commente.

/ This command prepares the post-migration world. Today the federated currency
comes from the remote Fedow, and a local FED asset would be mistaken for it by
the POS cascade and the cash refund. Two things stop it from running, on
purpose: the guard in Asset.save(), and the missing Client.FED category. No
automatic caller exists.

Idempotent : peut etre lance plusieurs fois sans effet de bord.
/ Idempotent: can be run multiple times without side effects.

Usage (apres migration seulement / after migration only) :
    docker exec lespass_django poetry run python manage.py bootstrap_fed_asset
"""

import logging

from django.core.management.base import BaseCommand
from django_tenants.utils import tenant_context

from Customers.models import Client
from AuthBillet.models import Wallet
from fedow_core.models import Asset
from BaseBillet.models import Product, Price


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Bootstrap de l'infrastructure recharge FED V2 (tenant federation_fed + asset FED)"

    def handle(self, *args, **options):
        # 1. Tenant federation_fed (schema PostgreSQL auto-cree par django-tenants).
        # auto_create_schema=True sur Client cree le schema et lance migrate_schemas.
        # / 1. federation_fed tenant (auto-created by django-tenants via auto_create_schema=True).
        tenant, tenant_created = Client.objects.get_or_create(
            schema_name="federation_fed",
            defaults={
                "name": "Fédération FED",
                "categorie": Client.FED,
                "on_trial": False,
            },
        )
        if tenant_created:
            self.stdout.write(
                self.style.SUCCESS(
                    "Tenant federation_fed cree (schema PostgreSQL auto-genere)."
                )
            )
        else:
            self.stdout.write("Tenant federation_fed deja present, reutilise.")

        # 2. Root wallet (le "pot central" qui emet les tokens FED lors d'une REFILL).
        # Wallet est en SHARED_APPS, pas besoin de tenant_context pour la creation.
        # / 2. Root wallet (the "central pot" that emits FED tokens on REFILL).
        # Wallet is in SHARED_APPS, no tenant_context needed for creation.
        root_wallet, wallet_created = Wallet.objects.get_or_create(
            name="Pot central TiBillet FED",
            defaults={"origin": tenant},
        )
        if wallet_created:
            self.stdout.write(
                self.style.SUCCESS(f"Root wallet cree : {root_wallet.uuid}")
            )

        # 3. Asset FED unique. Asset est en SHARED_APPS.
        # Un seul Asset de categorie FED doit exister dans le systeme.
        # / 3. Unique FED Asset. Asset is in SHARED_APPS.
        # Only one Asset of category FED must exist in the system.
        asset_fed, asset_created = Asset.objects.get_or_create(
            category=Asset.FED,
            defaults={
                "name": "Euro fédéré TiBillet",
                "currency_code": "EUR",
                "wallet_origin": root_wallet,
                "tenant_origin": tenant,
            },
        )
        if asset_created:
            self.stdout.write(self.style.SUCCESS(f"Asset FED cree : {asset_fed.uuid}"))

        # 4. Product et Price de recharge (TENANT_APPS, dans federation_fed).
        # tenant_context est obligatoire pour acceder aux tables du schema federation_fed.
        # / 4. Refill Product and Price (TENANT_APPS, in federation_fed schema).
        # tenant_context is required to access federation_fed schema tables.
        with tenant_context(tenant):
            product, product_created = Product.objects.get_or_create(
                categorie_article=Product.RECHARGE_CASHLESS_FED,
                defaults={
                    "name": "Recharge monnaie fédérée",
                    "asset": asset_fed,
                },
            )
            if product_created:
                self.stdout.write(
                    self.style.SUCCESS(f"Product de recharge FED cree : {product.uuid}")
                )

            price, price_created = Price.objects.get_or_create(
                product=product,
                defaults={
                    "name": "Montant libre",
                    "prix": 0,
                    "asset": asset_fed,
                },
            )
            if price_created:
                self.stdout.write(
                    self.style.SUCCESS(f"Price de recharge FED cree : {price.uuid}")
                )

        self.stdout.write(self.style.SUCCESS("\nBootstrap FED V2 termine."))
