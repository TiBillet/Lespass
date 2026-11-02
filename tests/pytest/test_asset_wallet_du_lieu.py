"""
Un asset cree depuis l'admin appartient au wallet du lieu, jamais a celui d'un client.
/ An asset created from the admin belongs to the venue wallet, never to a customer's.

LOCALISATION : tests/pytest/test_asset_wallet_du_lieu.py

POURQUOI CE TEST / WHY THIS TEST
--------------------------------
Les ventes cashless creditent `asset.wallet_origin`. Si ce champ pointe vers le
wallet d'un client, les recettes du lieu arrivent sur sa carte, et il peut les
depenser. Les wallets des clients ont le meme `origin` que le lieu : seul le nom
`Lieu <schema>` distingue le wallet du lieu.
/ Cashless sales credit `asset.wallet_origin`. Customer wallets share the venue's
`origin`: only the name `Lieu <schema>` identifies the venue wallet.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_asset_wallet_du_lieu.py -q
"""

from uuid import UUID

import pytest
from django.test import RequestFactory
from django_tenants.utils import tenant_context

from Administration.admin_tenant import staff_admin_site
from AuthBillet.models import Wallet
from Customers.models import Client
from fedow_core.admin import AssetAdmin
from fedow_core.models import Asset


@pytest.mark.django_db
def test_un_asset_cree_depuis_l_admin_prend_le_wallet_du_lieu():
    """Un wallet client qui passe en tete du tri ne devient pas le wallet de l'asset.
    / A customer wallet sorted first does not become the asset's wallet."""
    lieu = Client.objects.get(schema_name="lespass")

    with tenant_context(lieu):
        # Ce wallet client a le plus petit UUID possible : il sort premier du tri.
        # / This customer wallet has the lowest possible UUID: it sorts first.
        wallet_client = Wallet.objects.create(uuid=UUID(int=1), origin=lieu)

        # Le test ne prouve quelque chose que si le wallet client sort bien premier.
        # / The test only proves something if the customer wallet really sorts first.
        if Wallet.objects.filter(origin=lieu).first() != wallet_client:
            pytest.fail(
                "Le wallet client ne sort pas premier : ce test ne prouverait rien."
            )

        nouvel_asset = Asset(
            name="Monnaie du test wallet du lieu",
            currency_code="TWL",
            category=Asset.TLF,
        )
        admin_des_assets = AssetAdmin(Asset, staff_admin_site)
        requete_admin = RequestFactory().post("/admin/")

        admin_des_assets.save_model(
            requete_admin, nouvel_asset, form=None, change=False
        )

        assert nouvel_asset.wallet_origin.name == "Lieu lespass"
