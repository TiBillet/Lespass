"""
Tests du libelle de prix commun (evenements, adhesions, ressources).
/ Tests of the shared price label (events, memberships, resources).

LOCALISATION : tests/pytest/test_libelle_prix.py

Code teste : BaseBillet/services_libelle_prix.py.

Les tarifs sont des faux objets (SimpleNamespace) : pas de base de donnees.
La fonction ne lit que prix, free_price, asset_id et non_fiduciaire.
/ Prices are fake objects: no database. Only four attributes are read.
"""

from decimal import Decimal
from types import SimpleNamespace

from django.utils import translation

from BaseBillet.models import Product
from BaseBillet.services_libelle_prix import (
    TYPE_ADHESION,
    TYPE_EVENEMENT,
    TYPE_RESSOURCE,
    libelle_prix,
    tarifs_publies_de_l_evenement,
)


def _tarif(
    montant,
    prix_libre=False,
    asset_id=None,
    non_fiduciaire=False,
    publie=True,
    archive=False,
):
    """
    Fabrique un faux tarif.
    / Builds a fake price.
    """
    return SimpleNamespace(
        prix=Decimal(montant),
        free_price=prix_libre,
        asset_id=asset_id,
        non_fiduciaire=non_fiduciaire,
        publish=publie,
        archived=archive,
    )


def _libelle_en_francais(tarifs, type_objet):
    with translation.override("fr"):
        return libelle_prix(tarifs, type_objet)


def test_un_prix_libre_a_zero_affiche_prix_libre():
    tarifs = [_tarif("0", prix_libre=True)]
    assert _libelle_en_francais(tarifs, TYPE_EVENEMENT) == "Prix libre"


def test_un_prix_libre_avec_minimum_affiche_le_minimum():
    tarifs = [_tarif("5", prix_libre=True)]
    assert _libelle_en_francais(tarifs, TYPE_ADHESION) == "Prix libre dès 5 €"


def test_des_tarifs_fixes_et_un_prix_libre_affichent_prix_libre_des_le_plus_bas():
    tarifs = [_tarif("10"), _tarif("15"), _tarif("8", prix_libre=True)]
    assert _libelle_en_francais(tarifs, TYPE_EVENEMENT) == "Prix libre dès 8 €"


def test_un_seul_tarif_affiche_son_montant():
    tarifs = [_tarif("12")]
    assert _libelle_en_francais(tarifs, TYPE_EVENEMENT) == "12 €"


def test_deux_tarifs_au_meme_montant_affichent_un_seul_montant():
    tarifs = [_tarif("12"), _tarif("12.00")]
    assert _libelle_en_francais(tarifs, TYPE_RESSOURCE) == "12 €"


def test_plusieurs_tarifs_affichent_le_min_et_le_max():
    tarifs = [_tarif("25"), _tarif("10"), _tarif("15")]
    assert _libelle_en_francais(tarifs, TYPE_EVENEMENT) == "De 10 à 25 €"


def test_un_evenement_sans_tarif_affiche_entree_libre():
    assert _libelle_en_francais([], TYPE_EVENEMENT) == "Entrée libre"


def test_une_adhesion_sans_tarif_affiche_gratuit():
    assert _libelle_en_francais([], TYPE_ADHESION) == "Gratuit"


def test_un_evenement_avec_des_tarifs_tous_a_zero_affiche_reservation_gratuite():
    tarifs = [_tarif("0"), _tarif("0")]
    assert _libelle_en_francais(tarifs, TYPE_EVENEMENT) == "Réservation gratuite"


def test_une_ressource_avec_des_tarifs_tous_a_zero_affiche_gratuit():
    tarifs = [_tarif("0"), _tarif("0")]
    assert _libelle_en_francais(tarifs, TYPE_RESSOURCE) == "Gratuit"

def test_des_tarifs_en_points_seulement_n_affichent_aucun_prix():
    tarifs = [_tarif("3", asset_id="un-asset"), _tarif("1", non_fiduciaire=True)]
    assert _libelle_en_francais(tarifs, TYPE_ADHESION) is None


def test_les_tarifs_en_points_sont_ignores_a_cote_des_tarifs_en_euros():
    tarifs = [_tarif("20"), _tarif("1", asset_id="un-asset")]
    assert _libelle_en_francais(tarifs, TYPE_ADHESION) == "20 €"


def test_les_centimes_s_affichent_a_la_francaise():
    tarifs = [_tarif("12.50")]
    assert _libelle_en_francais(tarifs, TYPE_EVENEMENT) == "12,50 €"


def test_seuls_les_tarifs_de_billetterie_publies_comptent_pour_un_evenement():
    # Un faux evenement : une billetterie, une adhesion obligatoire liee.
    # / A fake event: one ticket product, one linked membership product.
    produit_billet = SimpleNamespace(
        categorie_article=Product.BILLET,
        prices=SimpleNamespace(
            all=lambda: [
                _tarif("10"),
                _tarif("5", publie=False),
                _tarif("2", archive=True),
            ]
        ),
    )
    produit_adhesion = SimpleNamespace(
        categorie_article=Product.ADHESION,
        prices=SimpleNamespace(all=lambda: [_tarif("30")]),
    )
    evenement = SimpleNamespace(
        products=SimpleNamespace(all=lambda: [produit_billet, produit_adhesion]),
    )

    tarifs = tarifs_publies_de_l_evenement(evenement)

    assert [tarif.prix for tarif in tarifs] == [Decimal("10")]
