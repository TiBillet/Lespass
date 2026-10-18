"""
La caisse retrouve la photo du prix (`PriceSold`) même quand le tarif en a plusieurs.
/ The register finds the price snapshot (`PriceSold`) even when the price has several.

LOCALISATION : tests/pytest/test_pricesold_cle_caisse.py

RÈGLE MÉTIER TESTÉE
Un `PriceSold` est une photo du prix au moment de la vente. Sa clé est
(produit vendu, tarif, prix). La billetterie en ligne crée une photo PAR MONTANT
(prix libre, code promo, prix modifié) : un même tarif peut donc avoir plusieurs
photos, et le modèle ne l'interdit pas.
La caisse cherche la photo AU PRIX CATALOGUE du tarif. Elle ne plante pas quand
d'autres photos existent à d'autres montants. Le montant réellement payé reste
sur la ligne (`LigneArticle.amount`).
/ A `PriceSold` key is (productsold, price, prix). Online sales create one snapshot
per amount. The register looks for the snapshot at the catalogue price and does not
crash when other snapshots exist.

D'OÙ VIENNENT LES VALEURS ATTENDUES
- un don à prix libre, minimum 1,00 € (le prix catalogue du tarif) ;
- deux photos déjà en base, à 5,00 € et 10,00 €, comme les laisse le site ;
- la caisse encaisse 5,00 € (500 centimes) : la ligne vaut 500, sa photo vaut 1,00 €.
/ Hand-computed values.

SIMULATIONS
Chaque test est marqué `django_db` : la transaction est annulée à la fin
(tests/PIEGES.md 13.1). La caisse est activée EN MÉMOIRE par
`configuration_modifiee()` (tests/PIEGES.md 13.22). Celery est simulé
(tests/PIEGES.md 13.4). La monnaie locale du lieu est en base locale (`fedow_core`) :
aucun appel réseau.
/ Rolled back per test; register module on in memory; Celery faked; no network call.

Lancer / Run : make test ARGS="tests/pytest/test_pricesold_cle_caisse.py"
"""

from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.utils import translation
from django_tenants.utils import tenant_context

from BaseBillet.models import PaymentMethod, PriceSold, ProductSold
from fabriques_panier import configuration_modifiee, taches_celery_enregistrees
from fabriques_vente import verifier_egalites
from test_caisse_ecrit_la_vente import (
    cle_de_panier,
    creer_un_article_de_caisse,
    nouvelle_cle_d_idempotence,
    payer_par_la_carte_du_client,
    payer_un_panier_compose_a_la_caisse,
    reglements_de_la_vente,
    retrouver_la_vente_de_la_cle,
    seul_article_de_la_vente,
)
from test_caracterisation_caisse import (
    creer_un_point_de_vente,
    creer_une_carte_nfc_chargee,
)
from test_caracterisation_en_ligne import creer_un_administrateur_du_lieu

pytestmark = pytest.mark.django_db


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


def creer_un_don_avec_deux_photos_vendues_en_ligne():
    """
    ÉTAT DE DÉPART : un don à prix libre (minimum 1,00 €) dont le tarif a déjà deux
    photos, à 5,00 € et à 10,00 €. C'est ce que laisse la billetterie en ligne
    (`ApiBillet/serializers.py`, `get_or_create_price_sold`) : une photo par montant.
    Le produit vendu est celui de la caisse : sans événement.
    / STARTING STATE: a free-price donation whose price already has two snapshots,
    at 5.00 € and 10.00 €, as online sales leave them.
    """
    don = creer_un_article_de_caisse(
        "don photos en ligne", prix_en_euros="1.00", taux_tva="20.00", prix_libre=True
    )
    produit_vendu = ProductSold.objects.create(
        product=don.produit,
        event=None,
        categorie_article=don.produit.categorie_article,
    )
    for montant_paye_en_ligne in ["5.00", "10.00"]:
        PriceSold.objects.create(
            productsold=produit_vendu,
            price=don.tarif,
            prix=Decimal(montant_paye_en_ligne),
        )
    return don


def champs_d_un_don_de_cinq_euros(don):
    """
    Le panier de la caisse : une ligne de don à 5,00 €, comme addition.js l'envoie.
    / The register cart: one 5.00 € donation line.
    """
    cle_de_la_ligne = cle_de_panier(don, numero_de_ligne=1)
    return {
        f"repid-{cle_de_la_ligne}": "1",
        f"custom-{cle_de_la_ligne}": "500",
    }


def test_paiement_nfc_retrouve_la_photo_au_prix_catalogue(lieu):
    """
    Un don à prix libre de 5,00 €, payé par la carte NFC du client (chemin cascade).
    Le tarif a déjà deux photos vendues en ligne. La caisse ne plante pas : la ligne
    vaut 500 et pointe vers la photo au prix catalogue (1,00 €).
    / A 5.00 € free-price donation paid by NFC card. The price already has two online
    snapshots. No crash: the line is 500 and uses the catalogue-price snapshot.
    """
    don = creer_un_don_avec_deux_photos_vendues_en_ligne()
    point_de_vente = creer_un_point_de_vente([don.produit])
    carte_du_client = creer_une_carte_nfc_chargee(lieu, solde_en_centimes=1000)
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    cle_d_idempotence = nouvelle_cle_d_idempotence()

    reponse = payer_par_la_carte_du_client(
        client_du_caissier,
        point_de_vente,
        champs_d_un_don_de_cinq_euros(don),
        carte_du_client,
        cle_d_idempotence,
    )

    assert reponse.status_code == 200
    vente = retrouver_la_vente_de_la_cle(cle_d_idempotence)
    article = seul_article_de_la_vente(vente)
    assert article.amount == 500
    assert article.pricesold.price == don.tarif
    assert article.pricesold.prix == Decimal("1.00")
    verifier_egalites(vente)


def test_paiement_cb_retrouve_la_photo_au_prix_catalogue(lieu):
    """
    Le même don de 5,00 €, payé par carte bancaire (chemin `_creer_lignes_articles`).
    La caisse ne plante pas et utilise la photo au prix catalogue (1,00 €).
    / The same 5.00 € donation paid by bank card: no crash, catalogue-price snapshot.
    """
    don = creer_un_don_avec_deux_photos_vendues_en_ligne()
    point_de_vente = creer_un_point_de_vente([don.produit])
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    cle_d_idempotence = nouvelle_cle_d_idempotence()

    reponse = payer_un_panier_compose_a_la_caisse(
        client_du_caissier,
        point_de_vente,
        champs_d_un_don_de_cinq_euros(don),
        moyen_de_paiement="carte_bancaire",
        cle_d_idempotence=cle_d_idempotence,
    )

    assert reponse.status_code == 200
    vente = retrouver_la_vente_de_la_cle(cle_d_idempotence)
    article = seul_article_de_la_vente(vente)
    assert article.amount == 500
    assert article.pricesold.prix == Decimal("1.00")
    assert reglements_de_la_vente(vente) == [(PaymentMethod.CC, 500)]
    verifier_egalites(vente)


def test_deux_ventes_en_caisse_partagent_la_meme_photo(lieu):
    """
    Deux dons encaissés en caisse sur le même tarif : la caisse crée la photo au prix
    catalogue une seule fois, puis la retrouve. Les photos vendues en ligne restent
    intactes.
    / Two register sales on the same price share one catalogue-price snapshot; the
    online snapshots stay untouched.
    """
    don = creer_un_don_avec_deux_photos_vendues_en_ligne()
    point_de_vente = creer_un_point_de_vente([don.produit])
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)

    for _numero_de_la_vente in range(2):
        reponse = payer_un_panier_compose_a_la_caisse(
            client_du_caissier,
            point_de_vente,
            champs_d_un_don_de_cinq_euros(don),
            moyen_de_paiement="carte_bancaire",
            cle_d_idempotence=nouvelle_cle_d_idempotence(),
        )
        assert reponse.status_code == 200

    prix_des_photos_du_tarif = sorted(
        PriceSold.objects.filter(price=don.tarif).values_list("prix", flat=True)
    )
    assert prix_des_photos_du_tarif == [
        Decimal("1.00"),
        Decimal("5.00"),
        Decimal("10.00"),
    ]
