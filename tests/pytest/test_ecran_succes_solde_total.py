"""
L'écran de succès d'un paiement cashless affiche le vrai solde de la carte.
/ The cashless payment success screen shows the card's real balance.

LOCALISATION : tests/pytest/test_ecran_succes_solde_total.py

RÈGLE MÉTIER TESTÉE
Une carte peut porter de l'argent à deux endroits : les monnaies locales du lieu
(`fedow_core`, base locale) et le FED (ancien Fedow, serveur distant). Après une vente,
l'écran montre le détail de ce qui a été payé, monnaie par monnaie, FED compris, et le
solde total en euros de la carte : ce qu'elle peut encore dépenser ici.
/ A card may hold local currencies and FED. After a sale the screen shows what was paid
per currency, FED included, and the card's euro total.

LES CAS COUVERTS (café à 3,10 €)
1. Le local suffit : 5,00 € local + 45,00 € FED → total 46,90 €.
2. Local partiel, FED suffisant : 2,00 € + 10,00 € → total 8,90 €.
3. FED seul : 0 € + 10,00 € → total 6,90 €.
4. Local et FED insuffisants, le reste en espèces : 1,00 € + 1,00 € → total 0,00 €.
5. Local insuffisant, pas de FED, le reste en espèces : 1,00 € + 0 € → total 0,00 €.
6. Deux cartes : chaque carte a son propre total.
7. Fedow injoignable : la vente passe, l'écran le signale.
8. Lieu non relié à Fedow : rien à signaler.
9. Carte anonyme qui prend une adhésion : son portefeuille change pendant la vente,
   et le FED de l'adhérente compte dans le total.
10. La 2ᵉ carte paie en FED : sa ligne et son total comptent le débit.
/ Hand-computed values. Coffee at 3.10 €.

SIMULATIONS
Chaque test est marqué `django_db` : la transaction est annulée à la fin
(tests/PIEGES.md 13.1). La caisse est activée EN MÉMOIRE (13.22), Celery est simulé
(13.4), l'ancien Fedow est simulé PAR LA CARTE (`ancien_fedow_simule_par_carte`).
Le même parcours contre le VRAI Fedow et le VRAI Stripe est dans
tests/e2e/test_ecran_succes_solde_total_fedow_reel.py.
/ Rolled back per test. Old Fedow faked through the card. The real-Fedow journey is E2E.

Lancer / Run : make test ARGS="tests/pytest/test_ecran_succes_solde_total.py"
"""

import re
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.utils import translation
from django_tenants.utils import tenant_context

from AuthBillet.models import Wallet
from fabriques_panier import (
    configuration_modifiee,
    creer_adhesion,
    creer_utilisateur,
    taches_celery_enregistrees,
)
from fedow_connect.models import FedowConfig
from fedow_core.services import WalletService
from QrcodeCashless.models import CarteCashless
from test_caisse_ecrit_la_vente import (
    ancien_fedow_simule_par_carte,
    cle_de_panier,
    creer_un_article_de_caisse,
    creer_une_carte_nfc_d_un_membre_sans_solde_local,
    monnaie_locale_du_lieu,
    nouvelle_cle_d_idempotence,
    payer_le_reste_avec_une_deuxieme_carte,
    payer_le_reste_en_especes_ou_en_cb,
    payer_par_la_carte_du_client,
    tag_de_la_carte_primaire_du_caissier,
    transaction_fed_du_reseau,
)
from test_caracterisation_caisse import (
    creer_un_point_de_vente,
    creer_une_carte_nfc_chargee,
)
from test_caracterisation_en_ligne import creer_un_administrateur_du_lieu

pytestmark = pytest.mark.django_db

PRIX_DU_CAFE_EN_EUROS = "3.10"
PRIX_DU_CAFE_EN_CENTIMES = 310


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
                yield SimpleNamespace(tenant=tenant, taches_demandees=taches_demandees)


@pytest.fixture
def comptoir(lieu):
    """
    Un café à 3,10 €, son point de vente, le caissier et sa carte primaire.
    / A 3.10 € coffee, its point of sale, the cashier and the primary card.
    """
    cafe = creer_un_article_de_caisse(
        "cafe", prix_en_euros=PRIX_DU_CAFE_EN_EUROS, taux_tva="20.00"
    )
    point_de_vente = creer_un_point_de_vente([cafe.produit])
    return SimpleNamespace(
        cafe=cafe,
        point_de_vente=point_de_vente,
        client_du_caissier=creer_un_administrateur_du_lieu(lieu),
        tag_de_la_carte_primaire=tag_de_la_carte_primaire_du_caissier(point_de_vente),
    )


def payer_un_cafe(comptoir, carte, cle_d_idempotence=None):
    """
    Le client paie un café avec sa carte, par la vraie route de la caisse.
    / The customer pays a coffee by card, through the real route.
    """
    return payer_par_la_carte_du_client(
        comptoir.client_du_caissier,
        comptoir.point_de_vente,
        {f"repid-{cle_de_panier(comptoir.cafe)}": "1"},
        carte,
        cle_d_idempotence or nouvelle_cle_d_idempotence(),
        tag_id_carte_primaire=comptoir.tag_de_la_carte_primaire,
    )


def texte_de_l_element(contenu, identifiant_de_test):
    """
    Le texte de l'élément `data-testid`, balises retirées et espaces normalisés.
    Les montants s'écrivent avec des espaces insécables.
    / The element's text, tags stripped and spaces normalised.
    """
    trouve = re.search(
        rf'data-testid="{identifiant_de_test}"[^>]*>(.*?)</(?:b|div|tr)>',
        contenu,
        re.S,
    )
    assert trouve is not None, f"{identifiant_de_test} absent : {contenu[:1500]}"
    texte = re.sub(r"<[^>]+>", " ", trouve.group(1))
    texte = texte.replace("\xa0", " ").replace(" ", " ")
    return " ".join(texte.split())


def montant_du_complement(contenu, identifiant_de_test):
    """
    Un montant de l'écran du complément. Cet écran passe par `floatformat`, qui suit la
    langue active : point ou virgule. On le ramène à la virgule.
    / A complement screen amount: floatformat follows the language, normalised to comma.
    """
    return texte_de_l_element(contenu, identifiant_de_test).replace(".", ",")


def reste_a_payer_du_complement(contenu):
    """
    Le reste à payer annoncé par l'écran du complément, en virgule.
    / The remainder shown by the complement screen, with a comma.
    """
    trouve = re.search(
        r'<div[^>]*data-testid="complement-reste-a-payer"[^>]*>.*?<strong>([^<]*)</strong>',
        contenu,
        re.S,
    )
    assert trouve is not None, contenu[:1500]
    return trouve.group(1).replace("\xa0", " ").replace(".", ",")


def test_local_suffisant_le_total_compte_le_fed_qui_n_a_pas_servi(lieu, comptoir):
    """
    5,00 € de monnaie locale et 45,00 € de FED, un café à 3,10 € : le local paie tout.
    L'écran affiche un total de 46,90 €, sans le reste de 1,90 € en local.
    Le FED n'est pas débité.
    / 5.00 € local + 45.00 € FED: local pays all. Total 46.90 €, FED not debited.
    """
    carte = creer_une_carte_nfc_chargee(lieu, solde_en_centimes=500)

    with ancien_fedow_simule_par_carte({carte.tag_id: 4500}, {}) as faux_fedow:
        reponse = payer_un_cafe(comptoir, carte)

    contenu = reponse.content.decode()
    assert 'data-testid="paiement-succes"' in contenu, contenu[:800]
    assert "3,10 €" in texte_de_l_element(contenu, "paiement-carte1-debite")
    assert texte_de_l_element(contenu, "paiement-carte1-solde-total") == "46,90 €"
    # Le reste par monnaie n'est pas affiché : le détail est au check carte.
    # / The per-currency balance is hidden: the detail is on the card check.
    assert "1,90 €" not in contenu
    assert 'paiement-carte1-solde-apres' not in contenu
    assert faux_fedow.transaction.to_place.call_count == 0


def test_local_partiel_et_fed_suffisant_le_detail_montre_les_deux_monnaies(
    lieu, comptoir
):
    """
    2,00 € de monnaie locale et 10,00 € de FED, un café à 3,10 € : 2,00 € en local,
    1,10 € en FED. Le détail montre les deux monnaies. Le total vaut 8,90 €.
    / 2.00 € local + 10.00 € FED: 2.00 € local, 1.10 € FED. Both rows, total 8.90 €.
    """
    carte = creer_une_carte_nfc_chargee(lieu, solde_en_centimes=200)

    with ancien_fedow_simule_par_carte(
        {carte.tag_id: 1000}, {carte.tag_id: transaction_fed_du_reseau(110)}
    ):
        reponse = payer_un_cafe(comptoir, carte)

    contenu = reponse.content.decode()
    ligne_du_fed = texte_de_l_element(contenu, "solde-carte1-asset-2")
    assert "TiBillet" in ligne_du_fed and "− 1,10 €" in ligne_du_fed, ligne_du_fed
    assert texte_de_l_element(contenu, "paiement-carte1-solde-total") == "8,90 €"


def test_fed_seul_l_ecran_montre_la_carte(lieu, comptoir):
    """
    Une carte sans monnaie locale, avec 10,00 € de FED : le cadre de la carte s'affiche
    avec le montant payé, et le total vaut 6,90 €.
    / FED only: the card frame shows the paid amount. Total 6.90 €.
    """
    carte = creer_une_carte_nfc_d_un_membre_sans_solde_local(lieu)

    with ancien_fedow_simule_par_carte(
        {carte.tag_id: 1000},
        {carte.tag_id: transaction_fed_du_reseau(PRIX_DU_CAFE_EN_CENTIMES)},
    ):
        reponse = payer_un_cafe(comptoir, carte)

    contenu = reponse.content.decode()
    assert "3,10 €" in texte_de_l_element(contenu, "paiement-carte1-debite")
    assert texte_de_l_element(contenu, "paiement-carte1-solde-total") == "6,90 €"


def test_local_et_fed_insuffisants_le_reste_en_especes(lieu, comptoir):
    """
    1,00 € de monnaie locale et 1,00 € de FED, un café à 3,10 € : la carte paie 2,00 €,
    le client donne 1,10 € en espèces. Le détail montre les deux monnaies, et la carte
    est vide : total 0,00 €.
    / 1.00 € local + 1.00 € FED, 1.10 € in cash: both rows, total 0.00 €.
    """
    carte = creer_une_carte_nfc_chargee(lieu, solde_en_centimes=100)

    with ancien_fedow_simule_par_carte(
        {carte.tag_id: 100}, {carte.tag_id: transaction_fed_du_reseau(100)}
    ):
        reponse = payer_le_reste_en_especes_ou_en_cb(
            comptoir.client_du_caissier,
            comptoir.point_de_vente,
            {f"repid-{cle_de_panier(comptoir.cafe)}": "1"},
            carte,
            "espece",
            nouvelle_cle_d_idempotence(),
            tag_id_carte_primaire=comptoir.tag_de_la_carte_primaire,
        )

    contenu = reponse.content.decode()
    ligne_du_fed = texte_de_l_element(contenu, "solde-carte1-asset-2")
    assert "TiBillet" in ligne_du_fed and "− 1,00 €" in ligne_du_fed, ligne_du_fed
    assert texte_de_l_element(contenu, "paiement-carte1-solde-total") == "0,00 €"


def test_local_insuffisant_sans_fed_le_reste_en_especes(lieu, comptoir):
    """
    1,00 € de monnaie locale, une carte inconnue de l'ancien Fedow : la carte paie
    1,00 €, le client donne 2,10 € en espèces. Pas de ligne FED, total 0,00 €.
    / 1.00 € local, card unknown to the old Fedow, 2.10 € in cash. No FED row, total 0.
    """
    carte = creer_une_carte_nfc_chargee(lieu, solde_en_centimes=100)

    with ancien_fedow_simule_par_carte({}, {}):
        reponse = payer_le_reste_en_especes_ou_en_cb(
            comptoir.client_du_caissier,
            comptoir.point_de_vente,
            {f"repid-{cle_de_panier(comptoir.cafe)}": "1"},
            carte,
            "espece",
            nouvelle_cle_d_idempotence(),
        )

    contenu = reponse.content.decode()
    assert "TiBillet" not in contenu
    assert "1,00 €" in texte_de_l_element(contenu, "paiement-carte1-debite")
    assert texte_de_l_element(contenu, "paiement-carte1-solde-total") == "0,00 €"


def test_deux_cartes_chaque_carte_a_son_total(lieu, comptoir):
    """
    La carte 1 n'a que 2,00 € de FED. La carte 2 a 5,00 € de monnaie locale et 20,00 €
    de FED qui ne servent pas. Le café : 2,00 € en FED sur la carte 1, 1,10 € en local
    sur la carte 2. Totaux : 0,00 € et 23,90 €.
    / Card 1: 2.00 € FED. Card 2: 5.00 € local + 20.00 € unused FED. Totals 0 and 23.90.
    """
    carte_1 = creer_une_carte_nfc_d_un_membre_sans_solde_local(lieu)
    carte_2 = creer_une_carte_nfc_chargee(lieu, solde_en_centimes=500)

    with ancien_fedow_simule_par_carte(
        {carte_1.tag_id: 200, carte_2.tag_id: 2000},
        {carte_1.tag_id: transaction_fed_du_reseau(200)},
    ):
        reponse = payer_le_reste_avec_une_deuxieme_carte(
            comptoir.client_du_caissier,
            comptoir.point_de_vente,
            {f"repid-{cle_de_panier(comptoir.cafe)}": "1"},
            carte_1,
            carte_2,
            nouvelle_cle_d_idempotence(),
            tag_id_carte_primaire=comptoir.tag_de_la_carte_primaire,
        )

    contenu = reponse.content.decode()
    assert texte_de_l_element(contenu, "paiement-carte1-solde-total") == "0,00 €"
    assert texte_de_l_element(contenu, "paiement-carte2-solde-total") == "23,90 €"


def test_la_deuxieme_carte_paie_en_fed_son_total_compte_le_debit(lieu, comptoir):
    """
    La carte 1 a 2,00 € de monnaie locale. La carte 2 n'a que 10,00 € de FED. Le café :
    2,00 € en local sur la carte 1, 1,10 € en FED sur la carte 2. Totaux : 0,00 € et
    8,90 €.
    / Card 1: 2.00 € local. Card 2: 10.00 € FED, 1.10 € debited. Totals 0 and 8.90.
    """
    carte_1 = creer_une_carte_nfc_chargee(lieu, solde_en_centimes=200)
    carte_2 = creer_une_carte_nfc_d_un_membre_sans_solde_local(lieu)

    with ancien_fedow_simule_par_carte(
        {carte_1.tag_id: 0, carte_2.tag_id: 1000},
        {carte_2.tag_id: transaction_fed_du_reseau(110)},
    ):
        reponse = payer_le_reste_avec_une_deuxieme_carte(
            comptoir.client_du_caissier,
            comptoir.point_de_vente,
            {f"repid-{cle_de_panier(comptoir.cafe)}": "1"},
            carte_1,
            carte_2,
            nouvelle_cle_d_idempotence(),
            tag_id_carte_primaire=comptoir.tag_de_la_carte_primaire,
        )

    contenu = reponse.content.decode()
    assert texte_de_l_element(contenu, "paiement-carte1-solde-total") == "0,00 €"
    assert "1,10 €" in texte_de_l_element(contenu, "paiement-carte2-debite")
    assert texte_de_l_element(contenu, "paiement-carte2-solde-total") == "8,90 €"


def test_fedow_injoignable_la_vente_passe_et_l_ecran_le_signale(lieu, comptoir):
    """
    Le lieu est relié à l'ancien Fedow, qui ne répond pas. La vente en local passe,
    l'écran affiche le total local (1,90 €) et signale le réseau indisponible.
    / Linked venue, old Fedow down: the local sale goes through, the screen says so.
    """
    carte = creer_une_carte_nfc_chargee(lieu, solde_en_centimes=500)

    with patch.object(FedowConfig, "can_fedow", return_value=True):
        with patch(
            "laboutik.views.lire_depensable_fed_frais", return_value=(0, False)
        ):
            reponse = payer_un_cafe(comptoir, carte)

    contenu = reponse.content.decode()
    assert 'data-testid="paiement-succes"' in contenu, contenu[:800]
    assert texte_de_l_element(contenu, "paiement-carte1-solde-total") == "1,90 €"
    assert 'data-testid="paiement-carte1-reseau-indisponible"' in contenu


def test_lieu_non_relie_a_fedow_rien_a_signaler(lieu, comptoir):
    """
    Un lieu sans ancien Fedow : le total est le local, sans mention du réseau.
    / A venue without the old Fedow: local total, no network notice.
    """
    carte = creer_une_carte_nfc_chargee(lieu, solde_en_centimes=500)

    with patch.object(FedowConfig, "can_fedow", return_value=False):
        reponse = payer_un_cafe(comptoir, carte)

    contenu = reponse.content.decode()
    assert texte_de_l_element(contenu, "paiement-carte1-solde-total") == "1,90 €"
    assert 'data-testid="paiement-carte1-reseau-indisponible"' not in contenu


def test_ecran_du_complement_compte_le_fed_dans_le_paye_par_la_carte(lieu, comptoir):
    """
    1,00 € de monnaie locale et 1,00 € de FED, un café à 3,10 €. L'écran du complément
    annonce 2,00 € payés par la carte et 1,10 € de reste : 3,10 − 2,00 = 1,10.
    / 1.00 € local + 1.00 € FED: 2.00 € paid by card, 1.10 € left. The sum is right.
    """
    carte = creer_une_carte_nfc_chargee(lieu, solde_en_centimes=100)

    with ancien_fedow_simule_par_carte({carte.tag_id: 100}, {}) as faux_fedow:
        reponse = payer_un_cafe(comptoir, carte)

    contenu = reponse.content.decode()
    assert montant_du_complement(contenu, "complement-carte1-disponible") == "− 2,00 €"
    assert reste_a_payer_du_complement(contenu) == "1,10 €"
    # Rien n'est débité tant que le reste n'est pas réglé.
    # / Nothing is debited until the remainder is paid.
    assert faux_fedow.transaction.to_place.call_count == 0


def test_second_ecran_du_complement_compte_le_fed_de_la_premiere_carte(lieu, comptoir):
    """
    La carte 1 n'a que 2,00 € de FED, la carte 2 a 1,00 € de monnaie locale et pas de
    FED. Café à 3,10 € : le second écran annonce 2,00 € sur la carte 1, 1,00 € sur la
    carte 2, une pastille TiBillet à 2,00 €, et 0,10 € de reste.
    / Card 1: 2.00 € FED. Card 2: 1.00 € local. Second screen: 2.00 €, 1.00 €, a
    TiBillet pill and 0.10 € left.
    """
    carte_1 = creer_une_carte_nfc_d_un_membre_sans_solde_local(lieu)
    carte_2 = creer_une_carte_nfc_chargee(lieu, solde_en_centimes=100)

    with ancien_fedow_simule_par_carte({carte_1.tag_id: 200}, {}):
        reponse = payer_le_reste_avec_une_deuxieme_carte(
            comptoir.client_du_caissier,
            comptoir.point_de_vente,
            {f"repid-{cle_de_panier(comptoir.cafe)}": "1"},
            carte_1,
            carte_2,
            nouvelle_cle_d_idempotence(),
            tag_id_carte_primaire=comptoir.tag_de_la_carte_primaire,
        )

    contenu = reponse.content.decode()
    assert montant_du_complement(contenu, "complement-carte1-disponible") == "− 2,00 €"
    assert montant_du_complement(contenu, "complement-carte2-disponible") == "− 1,00 €"
    assert f"TiBillet ({carte_1.tag_id})" in contenu
    assert reste_a_payer_du_complement(contenu) == "0,10 €"


def test_carte_anonyme_qui_prend_une_adhesion_garde_le_bon_total(lieu):
    """
    Une carte anonyme porte 10,00 € de monnaie locale. Sa porteuse prend une adhésion
    à 5,00 : la vente lie la carte et fusionne son portefeuille éphémère dans celui de
    l'adhérente. Le solde lu après la vente est celui du NOUVEAU portefeuille : 5,00 €.
    / An anonymous card takes a membership: its ephemeral wallet merges into the
    member's. The balance read after the sale is the NEW wallet's: 5.00 €.
    """
    adhesion = creer_adhesion(prix="5.00")
    point_de_vente = creer_un_point_de_vente([adhesion.produit])
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    carte = creer_une_carte_nfc_chargee(lieu, solde_en_centimes=1000)
    adherente = creer_utilisateur(prenom="Ada", nom="Lovelace")
    adherente.wallet = Wallet.objects.create(
        name="TEST_ecran_succes wallet adherente", origin=lieu.tenant
    )
    adherente.save(update_fields=["wallet"])

    with ancien_fedow_simule_par_carte({carte.tag_id: 0}, {}):
        with patch("fedow_connect.services.declarer_wallet_user_a_fedow"):
            with patch(
                "laboutik.views._declarer_adherent_au_reseau",
                return_value={
                    "user": adherente,
                    "carte": carte,
                    "fusion_locale_autorisee": True,
                    "avertissements": [],
                },
            ):
                reponse = payer_par_la_carte_du_client(
                    client_du_caissier,
                    point_de_vente,
                    {
                        f"repid-{cle_de_panier(adhesion)}": "1",
                        "email_adhesion": adherente.email,
                        "prenom_adhesion": "Ada",
                        "nom_adhesion": "Lovelace",
                    },
                    carte,
                    nouvelle_cle_d_idempotence(),
                )

    contenu = reponse.content.decode()
    assert 'data-testid="paiement-succes"' in contenu, contenu[:800]
    assert CarteCashless.objects.get(pk=carte.pk).user == adherente
    solde_reel = WalletService.obtenir_solde(
        wallet=adherente.wallet, asset=monnaie_locale_du_lieu(lieu)
    )
    assert solde_reel == 500
    assert texte_de_l_element(contenu, "paiement-carte1-solde-total") == "5,00 €"


def test_carte_anonyme_qui_prend_une_adhesion_compte_le_fed_de_l_adherente(lieu):
    """
    Une carte anonyme porte 1,00 € de monnaie locale et 10,00 € de FED. L'adhérente a
    20,00 € de FED sur son compte. L'adhésion à 5,00 € se paie 1,00 € en local et 4,00 €
    en FED, puis Fedow rattache la carte au compte de l'adhérente : 6,00 € + 20,00 €.
    La ligne TiBillet montre 4,00 € et le total vaut 26,00 €.
    / An anonymous card (1.00 € local, 10.00 € FED) joins a member holding 20.00 € FED.
    The membership debits 4.00 € FED: the FED row shows 4.00 €, total 26.00 €.
    """
    adhesion = creer_adhesion(prix="5.00")
    point_de_vente = creer_un_point_de_vente([adhesion.produit])
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    tag_de_la_carte_primaire = tag_de_la_carte_primaire_du_caissier(point_de_vente)
    carte = creer_une_carte_nfc_chargee(lieu, solde_en_centimes=100)
    adherente = creer_utilisateur(prenom="Ada", nom="Lovelace")
    adherente.wallet = Wallet.objects.create(
        name="TEST_ecran_succes wallet adherente", origin=lieu.tenant
    )
    adherente.save(update_fields=["wallet"])

    with ancien_fedow_simule_par_carte(
        {carte.tag_id: 1000}, {carte.tag_id: transaction_fed_du_reseau(400)}
    ) as faux_fedow:
        fiche_de_la_carte = faux_fedow.NFCcard.retrieve(carte.tag_id)

        def fedow_rattache_la_carte_a_l_adherente(*arguments):
            # Le débit de 4,00 € vient de partir : la carte garde 6,00 €, rejoints par
            # les 20,00 € de l'adhérente.
            # / The 4.00 € debit just left: 6.00 € joined by the member's 20.00 €.
            fiche_de_la_carte["wallet"]["tokens"][0]["value"] = 2600
            return {
                "user": adherente,
                "carte": carte,
                "fusion_locale_autorisee": True,
                "avertissements": [],
            }

        with patch("fedow_connect.services.declarer_wallet_user_a_fedow"):
            with patch(
                "laboutik.views._declarer_adherent_au_reseau",
                side_effect=fedow_rattache_la_carte_a_l_adherente,
            ):
                reponse = payer_par_la_carte_du_client(
                    client_du_caissier,
                    point_de_vente,
                    {
                        f"repid-{cle_de_panier(adhesion)}": "1",
                        "email_adhesion": adherente.email,
                        "prenom_adhesion": "Ada",
                        "nom_adhesion": "Lovelace",
                    },
                    carte,
                    nouvelle_cle_d_idempotence(),
                    tag_id_carte_primaire=tag_de_la_carte_primaire,
                )

    contenu = reponse.content.decode()
    assert 'data-testid="paiement-succes"' in contenu, contenu[:800]
    ligne_du_fed = texte_de_l_element(contenu, "solde-carte1-asset-2")
    assert "TiBillet" in ligne_du_fed and "− 4,00 €" in ligne_du_fed, ligne_du_fed
    assert texte_de_l_element(contenu, "paiement-carte1-solde-total") == "26,00 €"
