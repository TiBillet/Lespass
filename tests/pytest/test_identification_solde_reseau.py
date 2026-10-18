"""
L'écran « Client identifié » de la caisse affiche le solde COMPLET de la carte.
/ The register's "identified client" screen shows the card's FULL balance.

LOCALISATION : tests/pytest/test_identification_solde_reseau.py

RÈGLE MÉTIER TESTÉE
Une carte peut porter deux sortes d'argent : les monnaies locales du lieu
(`fedow_core`, base locale) et l'argent du réseau (ancien Fedow, serveur distant).
Le paiement NFC dépense les deux. L'écran « Client identifié »
(`PaiementViewSet.identifier_client`), affiché avant de payer une adhésion, un billet
ou une recharge, montre donc la somme des deux, comme le « check carte »
(`obtenir_solde_complet_carte`).
/ A card may hold local currencies and network money; the NFC payment spends both, so
the identification screen shows both, like the card check.

Le total en euros suit la cascade de paiement (`_soldes_de_la_cascade_fiduciaire`) :
le temps, la fidélité et la monnaie locale d'un lieu hors fédération n'y entrent pas.
/ The euro total follows the payment cascade: no time, loyalty or non-federated money.

D'OÙ VIENNENT LES VALEURS ATTENDUES
- adhérente : 10,00 € de monnaie locale + 15,00 € sur le réseau = 25,00 € ;
- carte anonyme : 0 € de monnaie locale + 15,00 € sur le réseau = 15,00 € ;
- même adhérente avec en plus 5 h de temps, 300 points et 20,00 € d'un autre lieu :
  toujours 25,00 €.
/ Hand-computed values.

SIMULATIONS
Chaque test est marqué `django_db` : la transaction est annulée à la fin
(tests/PIEGES.md 13.1). La caisse est activée EN MÉMOIRE par
`configuration_modifiee()` (tests/PIEGES.md 13.22). Celery est simulé
(tests/PIEGES.md 13.4). La lecture de l'argent du réseau
(`laboutik.views.lire_depensable_fed_frais`) est simulée : aucun appel réseau.
/ Rolled back per test; register module on in memory; Celery faked; the network
balance read is faked.

Lancer / Run : make test ARGS="tests/pytest/test_identification_solde_reseau.py"
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.utils import translation
from django_tenants.utils import tenant_context

from AuthBillet.models import Wallet
from BaseBillet.models import Product
from Customers.models import Client
from fabriques_panier import (
    configuration_modifiee,
    creer_adhesion,
    creer_utilisateur,
    identifiant_unique,
    taches_celery_enregistrees,
)
from fedow_core.models import Asset, Token
from laboutik.views import obtenir_solde_complet_carte
from test_caisse_ecrit_la_vente import (
    URL_DE_L_IDENTIFICATION_DU_CLIENT,
    cle_de_panier,
    creer_un_article_de_caisse,
    monnaie_locale_du_lieu,
)
from test_caisse_effets_adhesion import creer_la_carte_de_l_adherente_avec_10_euros
from test_caracterisation_caisse import (
    creer_un_point_de_vente,
    creer_une_carte_nfc_chargee,
)
from test_caracterisation_en_ligne import creer_un_administrateur_du_lieu

pytestmark = pytest.mark.django_db

# Argent de la carte sur le réseau (ancien Fedow), en centimes : 15,00 €.
# / The card's network money (old Fedow), in cents: 15.00 €.
ARGENT_DU_RESEAU_EN_CENTIMES = 1500


@pytest.fixture(autouse=True)
def _langue_par_defaut_apres_chaque_test():
    """Les signaux activent la langue du lieu sans la remettre (tests/PIEGES.md, 10.5).
    / Signals activate the venue language without resetting it."""
    yield
    translation.deactivate()


@pytest.fixture
def lieu(tenant):
    """
    Le lieu `lespass`, caisse activée EN MÉMOIRE, avec Celery simulé pendant tout le
    test (tests/PIEGES.md 13.22).
    / The `lespass` venue, register on in memory, Celery faked for the whole test.
    """
    with tenant_context(tenant):
        with configuration_modifiee(module_caisse=True, module_monnaie_locale=True):
            with taches_celery_enregistrees() as taches_demandees:
                yield SimpleNamespace(
                    tenant=tenant,
                    taches_demandees=taches_demandees,
                )


def identifier_le_client_par_sa_carte(
    client_du_caissier, point_de_vente, article, carte, drapeaux_du_panier
):
    """
    Le caissier scanne la carte du client sur l'écran d'identification, avec un panier
    d'un article. L'argent du réseau de la carte vaut ARGENT_DU_RESEAU_EN_CENTIMES.
    / The cashier scans the client's card on the identification screen, one-item cart.
    """
    donnees_du_formulaire = {
        "uuid_pv": str(point_de_vente.uuid),
        "tag_id": carte.tag_id,
        "moyens_paiement": "nfc",
        f"repid-{cle_de_panier(article)}": "1",
    }
    donnees_du_formulaire.update(drapeaux_du_panier)
    with patch(
        "laboutik.views.lire_depensable_fed_frais",
        return_value=(ARGENT_DU_RESEAU_EN_CENTIMES, True),
    ):
        return client_du_caissier.post(
            URL_DE_L_IDENTIFICATION_DU_CLIENT, donnees_du_formulaire
        )


def test_adhesion_le_solde_affiche_compte_l_argent_du_reseau(lieu):
    """
    Une adhésion, l'adhérente identifiée par sa carte : 10,00 € de monnaie locale et
    15,00 € sur le réseau. L'écran affiche un solde de 25,00 €.
    / A membership, member identified by card: 10.00 € local + 15.00 € network.
    The screen shows 25.00 €.
    """
    adherente = creer_utilisateur(prenom="Ada", nom="Lovelace")
    adhesion = creer_adhesion(prix="5.00")
    point_de_vente = creer_un_point_de_vente([adhesion.produit])
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    carte_de_l_adherente = creer_la_carte_de_l_adherente_avec_10_euros(lieu, adherente)

    reponse = identifier_le_client_par_sa_carte(
        client_du_caissier,
        point_de_vente,
        adhesion,
        carte_de_l_adherente,
        {"panier_a_adhesions": "True"},
    )

    assert reponse.status_code == 200
    assert reponse.context["user_solde"] == 25.0


def creer_une_monnaie(nom, categorie, code_devise, lieu_d_origine):
    """
    Une monnaie (`Asset`) créée par `lieu_d_origine`, dans aucune fédération.
    / A currency created by `lieu_d_origine`, in no federation.
    """
    portefeuille_du_lieu = Wallet.objects.create(
        origin=lieu_d_origine,
        name=f"TEST_identification monnaie {identifiant_unique()}",
    )
    return Asset.objects.create(
        name=f"TEST_identification {nom} {identifiant_unique()}",
        currency_code=code_devise,
        category=categorie,
        wallet_origin=portefeuille_du_lieu,
        tenant_origin=lieu_d_origine,
    )


def test_le_total_en_euros_ne_compte_que_ce_que_la_cascade_depense(lieu):
    """
    La carte de l'adhérente porte 10,00 € de monnaie locale du lieu, 5 h de temps,
    300 points de fidélité et 20,00 € de la monnaie locale d'un AUTRE lieu, hors de
    toute fédération. Le réseau porte 15,00 €.
    Le total en euros vaut 10,00 € + 15,00 € = 25,00 € : ce que la cascade de
    paiement dépenserait ici. Le temps, les points et la monnaie de l'autre lieu
    restent dans la liste détaillée (`tokens_locaux`).
    / 10.00 € local + 5 h time + 300 points + 20.00 € of a non-federated venue's
    currency, and 15.00 € on the network. Euro total = 25.00 €; the others stay in
    the detailed list.
    """
    adherente = creer_utilisateur(prenom="Ada", nom="Lovelace")
    carte_de_l_adherente = creer_la_carte_de_l_adherente_avec_10_euros(lieu, adherente)
    portefeuille_de_l_adherente = adherente.wallet

    monnaie_temps = creer_une_monnaie("temps", Asset.TIM, "TMP", lieu.tenant)
    monnaie_fidelite = creer_une_monnaie("fidelite", Asset.FID, "PTS", lieu.tenant)
    autre_lieu = Client.objects.exclude(
        schema_name__in=["public", lieu.tenant.schema_name]
    ).first()
    assert autre_lieu is not None, "Il faut un deuxième lieu dans la base de dev."
    monnaie_d_un_lieu_hors_federation = creer_une_monnaie(
        "locale autre lieu", Asset.TLF, "EUR", autre_lieu
    )
    Token.objects.create(
        wallet=portefeuille_de_l_adherente, asset=monnaie_temps, value=500
    )
    Token.objects.create(
        wallet=portefeuille_de_l_adherente, asset=monnaie_fidelite, value=30000
    )
    Token.objects.create(
        wallet=portefeuille_de_l_adherente,
        asset=monnaie_d_un_lieu_hors_federation,
        value=2000,
    )

    with patch(
        "laboutik.views.lire_depensable_fed_frais",
        return_value=(ARGENT_DU_RESEAU_EN_CENTIMES, True),
    ):
        solde = obtenir_solde_complet_carte(carte_de_l_adherente)

    assert solde["locaux_centimes"] == 1000
    assert solde["total_centimes"] == 2500
    categories_de_la_liste_detaillee = []
    for jeton in solde["tokens_locaux"]:
        categories_de_la_liste_detaillee.append(jeton["asset_category"])
    assert sorted(categories_de_la_liste_detaillee) == sorted(
        [Asset.TLF, Asset.TIM, Asset.FID, Asset.TLF]
    )


def test_recharge_carte_anonyme_le_solde_affiche_compte_l_argent_du_reseau(lieu):
    """
    Une recharge seule, sur une carte anonyme sans monnaie locale mais avec 15,00 € sur
    le réseau. L'écran affiche un solde de 15,00 €.
    / A top-up on an anonymous card: no local money, 15.00 € on the network.
    The screen shows 15.00 €.
    """
    recharge = creer_un_article_de_caisse(
        "recharge euros",
        prix_en_euros="10.00",
        taux_tva="20.00",
        methode_caisse=Product.RECHARGE_EUROS,
        asset=monnaie_locale_du_lieu(lieu),
    )
    point_de_vente = creer_un_point_de_vente([recharge.produit])
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    carte_anonyme = creer_une_carte_nfc_chargee(lieu, solde_en_centimes=0)

    reponse = identifier_le_client_par_sa_carte(
        client_du_caissier,
        point_de_vente,
        recharge,
        carte_anonyme,
        {"panier_a_recharges": "True"},
    )

    assert reponse.status_code == 200
    assert reponse.context["user_solde"] == 15.0
