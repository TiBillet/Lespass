"""
L'asset Fedow d'une adhesion n'est envoye que si le lieu a une caisse LaBoutik V1.
/ A membership's Fedow asset is only sent when the venue has a LaBoutik V1 POS.

LOCALISATION : tests/pytest/test_signal_asset_fedow_adhesion_v1.py

Code teste : BaseBillet/signals.py, send_membership_product_to_fedow.

- ADHESION : l'asset ne sert qu'a la vente au comptoir V1. Sans V1 (pas de
  `server_cashless` ni de `key_cashless`), le signal ne contacte pas Fedow.
- Tout autre produit (BADGE compris) : jamais envoye, meme avec une V1.

Le receiver est appele directement, sur un Product non enregistre. Configuration,
FedowConfig et AssetFedow sont simules : ni base, ni reseau.
/ The receiver is called directly on an unsaved Product; config and Fedow are mocked.
"""

from types import SimpleNamespace
from unittest import mock

from BaseBillet.models import Product
from BaseBillet.signals import send_membership_product_to_fedow


def _configuration_du_lieu(avec_laboutik_v1):
    """
    Une fausse Configuration, avec ou sans caisse LaBoutik V1.
    / A fake Configuration, with or without a LaBoutik V1 POS.
    """
    if avec_laboutik_v1:
        return SimpleNamespace(server_cashless="https://cashless.exemple.test", key_cashless="cle-de-test")
    return SimpleNamespace(server_cashless=None, key_cashless=None)


def _lancer_le_signal(produit, avec_laboutik_v1):
    """
    Lance le receiver et renvoie le faux AssetFedow, pour lire ses appels.
    / Runs the receiver and returns the fake AssetFedow, to read its calls.
    """
    with mock.patch("BaseBillet.signals.Configuration.get_solo",
                    return_value=_configuration_du_lieu(avec_laboutik_v1)), \
            mock.patch("BaseBillet.signals.FedowConfig.get_solo"), \
            mock.patch("BaseBillet.signals.AssetFedow") as faux_asset_fedow:
        faux_asset_fedow.return_value.get_or_create_membership_asset.return_value = (mock.MagicMock(), True)
        send_membership_product_to_fedow(sender=Product, instance=produit, created=True)
    return faux_asset_fedow


def test_adhesion_sans_laboutik_v1_n_envoie_rien_a_fedow():
    # Lieu sans V1 : aucun appel a Fedow pour une adhesion.
    # / Venue without V1: no Fedow call for a membership.
    adhesion = Product(name="Adhesion test", categorie_article=Product.ADHESION, archive=False)

    faux_asset_fedow = _lancer_le_signal(adhesion, avec_laboutik_v1=False)

    faux_asset_fedow.assert_not_called()


def test_adhesion_archivee_sans_laboutik_v1_n_archive_rien_sur_fedow():
    # Lieu sans V1 : l'archivage d'une adhesion ne contacte pas Fedow non plus.
    # / Venue without V1: archiving a membership does not call Fedow either.
    adhesion_archivee = Product(name="Adhesion test", categorie_article=Product.ADHESION, archive=True)

    faux_asset_fedow = _lancer_le_signal(adhesion_archivee, avec_laboutik_v1=False)

    faux_asset_fedow.assert_not_called()


def test_adhesion_avec_laboutik_v1_cree_l_asset_sur_fedow():
    # Lieu avec V1 : l'asset de l'adhesion est demande a Fedow.
    # / Venue with V1: the membership asset is requested from Fedow.
    adhesion = Product(name="Adhesion test", categorie_article=Product.ADHESION, archive=False)

    faux_asset_fedow = _lancer_le_signal(adhesion, avec_laboutik_v1=True)

    faux_asset_fedow.return_value.get_or_create_membership_asset.assert_called_once_with(adhesion)


def test_badge_avec_laboutik_v1_n_envoie_rien_a_fedow():
    # Le badge n'est jamais envoye a Fedow, meme sur un lieu avec V1.
    # / A badge is never sent to Fedow, even on a venue with V1.
    badge = Product(name="Badge test", categorie_article=Product.BADGE, archive=False)

    faux_asset_fedow = _lancer_le_signal(badge, avec_laboutik_v1=True)

    faux_asset_fedow.assert_not_called()
