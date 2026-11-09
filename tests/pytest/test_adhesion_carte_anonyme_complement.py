"""
Une adhésion payée par une carte anonyme, avec un complément, est bien enregistrée.
/ A membership paid by an anonymous card with a complement is really recorded.

LOCALISATION : tests/pytest/test_adhesion_carte_anonyme_complement.py

RÈGLE MÉTIER TESTÉE
La carte du client est anonyme et ne couvre pas tout le panier. Le caissier a saisi
l'e-mail de l'adhérente et règle le reste en espèces, en CB ou avec une 2ᵉ carte.
L'adhérente est celle de l'e-mail : elle est déclarée au réseau, la PREMIÈRE carte lui
est rattachée, et l'adhésion est créée à son nom.
/ The first card is anonymous and does not cover the cart. The member is the typed
email: declared to the network, the FIRST card is attached, the membership is created.

SIMULATIONS
`django_db` : la transaction est annulée à la fin (tests/PIEGES.md 13.1). La caisse est
activée EN MÉMOIRE (13.22), Celery est simulé (13.4), l'ancien Fedow est simulé PAR LA
CARTE (`ancien_fedow_simule_par_carte`). `declarer_wallet_user_a_fedow` est simulée.
Le même parcours contre le VRAI Fedow est dans
tests/e2e/test_adhesion_carte_anonyme_complement_fedow_reel.py.
/ Rolled back per test. Old Fedow faked through the card. The real journey is E2E.

Lancer / Run : make test ARGS="tests/pytest/test_adhesion_carte_anonyme_complement.py"
"""

import re
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.utils import translation
from django_tenants.utils import tenant_context

from AuthBillet.models import Wallet
from BaseBillet.models import LigneArticle, Membership, PaymentMethod, SaleOrigin
from BaseBillet.models_vente import Vente
from fabriques_panier import (
    configuration_modifiee,
    creer_adhesion,
    creer_utilisateur,
    taches_celery_enregistrees,
)
from fabriques_vente import verifier_egalites
from fedow_core.services import WalletService
from QrcodeCashless.models import CarteCashless
from test_caisse_ecrit_la_vente import (
    ancien_fedow_simule_par_carte,
    cle_de_panier,
    creer_une_carte_nfc_d_un_membre_sans_solde_local,
    monnaie_locale_du_lieu,
    nouvelle_cle_d_idempotence,
    payer_le_reste_apres_les_deux_cartes,
    payer_le_reste_avec_une_deuxieme_carte,
    payer_le_reste_en_especes_ou_en_cb,
    payer_par_la_carte_du_client,
    reglements_de_la_vente,
    tag_de_la_carte_primaire_du_caissier,
    transaction_fed_du_reseau,
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
def vente(tenant):
    """
    Une adhésion à 10,00 €, le point de vente, le caissier, sa carte primaire, et
    l'adhérente Ada, qui a déjà un portefeuille.
    / A 10.00 € membership, the POS, the cashier and the member, who has a wallet.
    """
    lieu = SimpleNamespace(tenant=tenant)
    with tenant_context(tenant):
        with configuration_modifiee(module_caisse=True, module_monnaie_locale=True):
            with taches_celery_enregistrees():
                adhesion = creer_adhesion(prix="10.00")
                point_de_vente = creer_un_point_de_vente([adhesion.produit])
                adherente = creer_utilisateur(prenom="Ada", nom="Lovelace")
                adherente.wallet = Wallet.objects.create(
                    name="TEST_adhesion_complement wallet adherente",
                    origin=tenant,
                )
                adherente.save(update_fields=["wallet"])
                yield SimpleNamespace(
                    lieu=lieu,
                    adhesion=adhesion,
                    point_de_vente=point_de_vente,
                    adherente=adherente,
                    client_du_caissier=creer_un_administrateur_du_lieu(lieu),
                    tag_de_la_carte_primaire=tag_de_la_carte_primaire_du_caissier(
                        point_de_vente
                    ),
                )


def champs_du_panier(vente, email=None):
    """
    Le panier et, si l'e-mail est donné, l'identification du formulaire de la caisse.
    / The cart and, when the email is given, the register form's identification.
    """
    champs = {f"repid-{cle_de_panier(vente.adhesion)}": "1"}
    if email is not None:
        champs["email_adhesion"] = email
        champs["prenom_adhesion"] = "Ada"
        champs["nom_adhesion"] = "Lovelace"
    return champs


def declaration_au_reseau_simulee():
    """
    La déclaration de l'adhérente à Fedow, sans appel réseau.
    / The member's Fedow declaration, with no network call.
    """
    return patch("fedow_connect.services.declarer_wallet_user_a_fedow")


def adhesion_enregistree_pour(vente, utilisateur):
    """
    L'adhésion de cette personne pour ce tarif, ou None.
    / That person's membership for this price, or None.
    """
    return Membership.objects.filter(
        user=utilisateur, price=vente.adhesion.tarif
    ).first()


def verifier_la_vente_et_l_adhesion(
    vente, client_attendu, carte_attendue, total_en_centimes, reglements_attendus
):
    """
    Relit en base la vente et l'adhésion. Il y a une seule ligne, une seule vente réglée
    et numérotée, avec son client, sa carte, son total et ses règlements. L'adhésion est
    unique, vendue en caisse, avec une échéance, et portée par la ligne.
    / Reads back the sale and the membership: one line, one settled numbered sale with
    its customer, card, total and payments, one till membership with a deadline.

    :param reglements_attendus: liste de paires (moyen, montant en centimes)
    :return: la Membership
    """
    ligne = LigneArticle.objects.get(pricesold__price=vente.adhesion.tarif)
    vente_ecrite = ligne.vente
    assert vente_ecrite.nature == Vente.Nature.VENTE
    assert vente_ecrite.statut == Vente.Statut.REGLEE
    assert vente_ecrite.numero is not None
    assert vente_ecrite.origine == SaleOrigin.LABOUTIK
    assert vente_ecrite.point_de_vente_id == vente.point_de_vente.pk
    assert vente_ecrite.client_id == client_attendu.pk
    assert vente_ecrite.carte_id == carte_attendue.pk
    assert vente_ecrite.total_ttc == total_en_centimes
    assert reglements_de_la_vente(vente_ecrite) == sorted(reglements_attendus)
    verifier_egalites(vente_ecrite)

    adhesion_vendue = Membership.objects.get(
        user=client_attendu, price=vente.adhesion.tarif
    )
    assert ligne.membership == adhesion_vendue
    assert adhesion_vendue.status == Membership.LABOUTIK
    assert adhesion_vendue.deadline is not None
    return adhesion_vendue


def solde_total_de_l_ecran(contenu, rang=1):
    """
    Le solde total affiché pour la carte, espaces normalisés.
    / The total shown for the card, spaces normalised.
    """
    trouve = re.search(
        rf'data-testid="paiement-carte{rang}-solde-total"[^>]*>([^<]*)</b>', contenu
    )
    assert trouve is not None, contenu[:1500]
    return " ".join(trouve.group(1).replace("\xa0", " ").replace(" ", " ").split())


def test_carte_anonyme_complement_en_especes_cree_l_adhesion(vente):
    """
    Une carte anonyme porte 4,00 € de monnaie locale, l'adhésion coûte 10,00 €. La carte
    paie 4,00 €, le caissier encaisse 6,00 € en espèces. L'adhésion est au nom d'Ada, sur
    la ligne de vente, Ada est la cliente de la vente et la carte lui est rattachée.
    / Anonymous card with 4.00 €, 10.00 € membership, 6.00 € in cash: membership on the
    sale line, Ada is the customer and the card is attached to her.
    """
    carte = creer_une_carte_nfc_chargee(vente.lieu, solde_en_centimes=400)
    cle_d_idempotence = nouvelle_cle_d_idempotence()

    with ancien_fedow_simule_par_carte({carte.tag_id: 0}, {}) as faux_fedow:
        with declaration_au_reseau_simulee() as declaration:
            premiere_reponse = payer_par_la_carte_du_client(
                vente.client_du_caissier,
                vente.point_de_vente,
                champs_du_panier(vente, vente.adherente.email),
                carte,
                cle_d_idempotence,
            )
            # L'écran du complément n'écrit rien : la carte n'est pas encore liée.
            # / The complement screen writes nothing: the card is not linked yet.
            contenu_du_complement = premiere_reponse.content.decode()
            assert 'data-testid="complement-paiement"' in contenu_du_complement
            assert faux_fedow.NFCcard.linkwallet_card_number.call_count == 0
            assert declaration.call_count == 0

            reponse = payer_le_reste_en_especes_ou_en_cb(
                vente.client_du_caissier,
                vente.point_de_vente,
                champs_du_panier(vente, vente.adherente.email),
                carte,
                "espece",
                cle_d_idempotence,
            )

    contenu = reponse.content.decode()
    assert 'data-testid="paiement-succes"' in contenu, contenu[:800]
    adhesion_vendue = adhesion_enregistree_pour(vente, vente.adherente)
    assert adhesion_vendue is not None
    ligne = LigneArticle.objects.get(pricesold__price=vente.adhesion.tarif)
    assert ligne.membership == adhesion_vendue
    assert ligne.vente.client == vente.adherente
    assert CarteCashless.objects.get(pk=carte.pk).user == vente.adherente
    assert faux_fedow.NFCcard.linkwallet_card_number.call_count == 1
    assert (
        WalletService.obtenir_solde(
            wallet=vente.adherente.wallet, asset=monnaie_locale_du_lieu(vente.lieu)
        )
        == 0
    )
    assert solde_total_de_l_ecran(contenu) == "0,00 €"
    verifier_la_vente_et_l_adhesion(
        vente,
        vente.adherente,
        carte,
        1000,
        [(PaymentMethod.LOCAL_EURO, 400), (PaymentMethod.CASH, 600)],
    )


def test_carte_anonyme_complement_avec_une_deuxieme_carte_d_un_autre_membre(vente):
    """
    La carte 1 est anonyme, avec 4,00 €. La carte 2 appartient à un autre membre et paie
    les 6,00 € restants. L'adhésion va à Ada (l'e-mail), jamais au titulaire de la carte
    2, et c'est la carte 1 qui lui est rattachée.
    / Card 1 is anonymous; card 2 belongs to another member and pays the rest. The
    membership goes to Ada, and card 1 is the one attached.
    """
    carte_1 = creer_une_carte_nfc_chargee(vente.lieu, solde_en_centimes=400)
    carte_2 = creer_une_carte_nfc_d_un_membre_sans_solde_local(vente.lieu)
    titulaire_de_la_carte_2 = carte_2.user
    titulaire_de_la_carte_2.wallet = Wallet.objects.create(
        name="TEST_adhesion_complement wallet carte 2", origin=vente.lieu.tenant
    )
    titulaire_de_la_carte_2.save(update_fields=["wallet"])
    WalletService.crediter(
        wallet=titulaire_de_la_carte_2.wallet,
        asset=monnaie_locale_du_lieu(vente.lieu),
        montant_en_centimes=2000,
    )

    with ancien_fedow_simule_par_carte({carte_1.tag_id: 0, carte_2.tag_id: 0}, {}):
        with declaration_au_reseau_simulee():
            reponse = payer_le_reste_avec_une_deuxieme_carte(
                vente.client_du_caissier,
                vente.point_de_vente,
                champs_du_panier(vente, vente.adherente.email),
                carte_1,
                carte_2,
                nouvelle_cle_d_idempotence(),
            )

    contenu = reponse.content.decode()
    assert 'data-testid="paiement-succes"' in contenu, contenu[:800]
    assert adhesion_enregistree_pour(vente, vente.adherente) is not None
    assert adhesion_enregistree_pour(vente, titulaire_de_la_carte_2) is None
    assert CarteCashless.objects.get(pk=carte_1.pk).user == vente.adherente
    assert CarteCashless.objects.get(pk=carte_2.pk).user == titulaire_de_la_carte_2
    verifier_la_vente_et_l_adhesion(
        vente,
        vente.adherente,
        carte_1,
        1000,
        [(PaymentMethod.LOCAL_EURO, 400), (PaymentMethod.LOCAL_EURO, 600)],
    )


def passer_l_adhesion_au_prix_libre(vente):
    """
    Remplace l'adhésion de la vente par une adhésion à prix libre, à 10,00 € minimum.
    / Replaces the sale's membership with a free-price one, 10.00 € minimum.
    """
    vente.adhesion = creer_adhesion(prix="10.00", prix_libre=True)
    vente.point_de_vente = creer_un_point_de_vente([vente.adhesion.produit])


def champs_du_panier_a_prix_libre(vente, montant_en_centimes):
    """
    Le panier d'une ligne à prix libre et l'identification du formulaire de la caisse.
    / The cart of a free-price line and the register form's identification.
    """
    cle_de_la_ligne = cle_de_panier(vente.adhesion, numero_de_ligne=1)
    return {
        f"repid-{cle_de_la_ligne}": "1",
        f"custom-{cle_de_la_ligne}": str(montant_en_centimes),
        "email_adhesion": vente.adherente.email,
        "prenom_adhesion": "Ada",
        "nom_adhesion": "Lovelace",
    }


@pytest.mark.parametrize(
    "moyen_du_reste, moyen_du_reglement",
    [("espece", PaymentMethod.CASH), ("carte_bancaire", PaymentMethod.CC)],
)
def test_complement_garde_le_prix_libre_le_prenom_et_le_nom(
    vente, moyen_du_reste, moyen_du_reglement
):
    """
    La cliente choisit 20,00 € pour une adhésion à prix libre. La carte anonyme paie
    4,00 €, le reste part en espèces ou en CB. L'adhésion garde 20,00 €, le prénom et le
    nom saisis.
    / The customer picks 20.00 €. The anonymous card pays 4.00 €, the rest in cash or by
    bank card. The membership keeps 20.00 € and the typed names.
    """
    passer_l_adhesion_au_prix_libre(vente)
    carte = creer_une_carte_nfc_chargee(vente.lieu, solde_en_centimes=400)

    with ancien_fedow_simule_par_carte({carte.tag_id: 0}, {}):
        with declaration_au_reseau_simulee():
            reponse = payer_le_reste_en_especes_ou_en_cb(
                vente.client_du_caissier,
                vente.point_de_vente,
                champs_du_panier_a_prix_libre(vente, 2000),
                carte,
                moyen_du_reste,
                nouvelle_cle_d_idempotence(),
            )

    contenu = reponse.content.decode()
    assert 'data-testid="paiement-succes"' in contenu, contenu[:800]
    adhesion_vendue = verifier_la_vente_et_l_adhesion(
        vente,
        vente.adherente,
        carte,
        2000,
        [(PaymentMethod.LOCAL_EURO, 400), (moyen_du_reglement, 1600)],
    )
    assert adhesion_vendue.contribution_value == Decimal("20.00")
    assert adhesion_vendue.first_name == "Ada"
    assert adhesion_vendue.last_name == "Lovelace"


def test_complement_avec_une_deuxieme_carte_garde_le_prix_libre_le_prenom_et_le_nom(
    vente,
):
    """
    La cliente choisit 20,00 €. La carte anonyme paie 4,00 €, une 2ᵉ carte paie 16,00 €.
    L'adhésion garde 20,00 €, le prénom et le nom saisis.
    / The customer picks 20.00 €, paid by two cards. The membership keeps the amount and
    the typed names.
    """
    passer_l_adhesion_au_prix_libre(vente)
    carte_1 = creer_une_carte_nfc_chargee(vente.lieu, solde_en_centimes=400)
    carte_2 = creer_une_carte_nfc_chargee(vente.lieu, solde_en_centimes=1600)

    with ancien_fedow_simule_par_carte({carte_1.tag_id: 0, carte_2.tag_id: 0}, {}):
        with declaration_au_reseau_simulee():
            reponse = payer_le_reste_avec_une_deuxieme_carte(
                vente.client_du_caissier,
                vente.point_de_vente,
                champs_du_panier_a_prix_libre(vente, 2000),
                carte_1,
                carte_2,
                nouvelle_cle_d_idempotence(),
            )

    contenu = reponse.content.decode()
    assert 'data-testid="paiement-succes"' in contenu, contenu[:800]
    adhesion_vendue = verifier_la_vente_et_l_adhesion(
        vente,
        vente.adherente,
        carte_1,
        2000,
        [(PaymentMethod.LOCAL_EURO, 400), (PaymentMethod.LOCAL_EURO, 1600)],
    )
    assert adhesion_vendue.contribution_value == Decimal("20.00")
    assert adhesion_vendue.first_name == "Ada"
    assert adhesion_vendue.last_name == "Lovelace"


def test_carte_deja_liee_avec_complement_garde_le_prix_libre_et_son_titulaire(vente):
    """
    La carte appartient déjà à un membre. Sans identité saisie, le membre choisit
    20,00 €, sa carte paie 4,00 €, le reste part en espèces. L'adhésion est à ce membre,
    à 20,00 €, et Fedow ne reçoit aucun rattachement.
    / The card already belongs to a member, no identity typed: the membership is theirs,
    at 20.00 €, and nothing is linked on Fedow.
    """
    passer_l_adhesion_au_prix_libre(vente)
    carte = creer_une_carte_nfc_d_un_membre_sans_solde_local(vente.lieu)
    titulaire = carte.user
    titulaire.wallet = Wallet.objects.create(
        name="TEST_adhesion_complement wallet carte liee", origin=vente.lieu.tenant
    )
    titulaire.save(update_fields=["wallet"])
    WalletService.crediter(
        wallet=titulaire.wallet,
        asset=monnaie_locale_du_lieu(vente.lieu),
        montant_en_centimes=400,
    )
    champs = champs_du_panier_a_prix_libre(vente, 2000)
    del champs["email_adhesion"]
    del champs["prenom_adhesion"]
    del champs["nom_adhesion"]

    with ancien_fedow_simule_par_carte({carte.tag_id: 0}, {}) as faux_fedow:
        with declaration_au_reseau_simulee() as declaration:
            reponse = payer_le_reste_en_especes_ou_en_cb(
                vente.client_du_caissier,
                vente.point_de_vente,
                champs,
                carte,
                "espece",
                nouvelle_cle_d_idempotence(),
            )

    contenu = reponse.content.decode()
    assert 'data-testid="paiement-succes"' in contenu, contenu[:800]
    adhesion_vendue = verifier_la_vente_et_l_adhesion(
        vente,
        titulaire,
        carte,
        2000,
        [(PaymentMethod.LOCAL_EURO, 400), (PaymentMethod.CASH, 1600)],
    )
    assert adhesion_vendue.contribution_value == Decimal("20.00")
    assert declaration.call_count == 0
    assert faux_fedow.NFCcard.linkwallet_card_number.call_count == 0


def test_deuxieme_carte_insuffisante_rien_n_est_lie_avant_la_fin_du_paiement(vente):
    """
    Carte 1 anonyme à 4,00 €, carte 2 anonyme à 3,00 € : il reste 3,00 €. Le 2ᵉ écran ne
    lie rien. Le caissier encaisse le reste en espèces : l'adhésion est créée, et les
    deux cartes sont débitées.
    / Both anonymous cards fall short: the second screen links nothing. The rest paid in
    cash creates the membership.
    """
    carte_1 = creer_une_carte_nfc_chargee(vente.lieu, solde_en_centimes=400)
    carte_2 = creer_une_carte_nfc_chargee(vente.lieu, solde_en_centimes=300)
    cle_d_idempotence = nouvelle_cle_d_idempotence()

    with ancien_fedow_simule_par_carte(
        {carte_1.tag_id: 0, carte_2.tag_id: 0}, {}
    ) as faux_fedow:
        with declaration_au_reseau_simulee():
            deuxieme_ecran = payer_le_reste_avec_une_deuxieme_carte(
                vente.client_du_caissier,
                vente.point_de_vente,
                champs_du_panier(vente, vente.adherente.email),
                carte_1,
                carte_2,
                cle_d_idempotence,
            )
            assert 'data-testid="complement-paiement"' in deuxieme_ecran.content.decode()
            assert faux_fedow.NFCcard.linkwallet_card_number.call_count == 0

            reponse = payer_le_reste_apres_les_deux_cartes(
                vente.client_du_caissier,
                vente.point_de_vente,
                champs_du_panier(vente, vente.adherente.email),
                carte_1,
                carte_2,
                "espece",
                cle_d_idempotence,
            )

    contenu = reponse.content.decode()
    assert 'data-testid="paiement-succes"' in contenu, contenu[:800]
    assert adhesion_enregistree_pour(vente, vente.adherente) is not None
    assert CarteCashless.objects.get(pk=carte_1.pk).user == vente.adherente
    assert faux_fedow.NFCcard.linkwallet_card_number.call_count == 1
    verifier_la_vente_et_l_adhesion(
        vente,
        vente.adherente,
        carte_1,
        1000,
        [
            (PaymentMethod.LOCAL_EURO, 400),
            (PaymentMethod.LOCAL_EURO, 300),
            (PaymentMethod.CASH, 300),
        ],
    )
    monnaie_locale = monnaie_locale_du_lieu(vente.lieu)
    assert (
        WalletService.obtenir_solde(wallet=vente.adherente.wallet, asset=monnaie_locale)
        == 0
    )
    assert (
        WalletService.obtenir_solde(
            wallet=CarteCashless.objects.get(pk=carte_2.pk).wallet_ephemere,
            asset=monnaie_locale,
        )
        == 0
    )


def test_carte_anonyme_sans_e_mail_le_complement_refuse_avant_tout_debit(vente):
    """
    Un envoi direct au complément, sans e-mail, pour une carte anonyme : refus avec un
    message, aucune monnaie débitée, aucune ligne, aucune adhésion.
    / Direct complement POST with no email: refused, nothing debited or written.
    """
    carte = creer_une_carte_nfc_chargee(vente.lieu, solde_en_centimes=400)

    with ancien_fedow_simule_par_carte({carte.tag_id: 0}, {}):
        reponse = payer_le_reste_en_especes_ou_en_cb(
            vente.client_du_caissier,
            vente.point_de_vente,
            champs_du_panier(vente),
            carte,
            "espece",
            nouvelle_cle_d_idempotence(),
        )

    assert reponse.status_code == 400, reponse.content.decode()[:500]
    assert not LigneArticle.objects.filter(
        pricesold__price=vente.adhesion.tarif
    ).exists()
    assert not Membership.objects.filter(price=vente.adhesion.tarif).exists()
    carte_relue = CarteCashless.objects.get(pk=carte.pk)
    assert carte_relue.user is None
    assert (
        WalletService.obtenir_solde(
            wallet=carte_relue.wallet_ephemere,
            asset=monnaie_locale_du_lieu(vente.lieu),
        )
        == 400
    )


def test_adherente_qui_a_deja_une_carte_l_ecran_le_signale(vente):
    """
    Ada possède déjà une carte. L'adhésion est créée, mais la carte scannée reste
    anonyme : l'écran de succès le dit au caissier.
    / Ada already owns a card: the membership is created, the scanned card stays
    anonymous, and the success screen says so.
    """
    autre_carte = creer_une_carte_nfc_d_un_membre_sans_solde_local(vente.lieu)
    CarteCashless.objects.filter(pk=autre_carte.pk).update(user=vente.adherente)
    carte = creer_une_carte_nfc_chargee(vente.lieu, solde_en_centimes=400)

    with ancien_fedow_simule_par_carte({carte.tag_id: 0}, {}) as faux_fedow:
        with declaration_au_reseau_simulee():
            reponse = payer_le_reste_en_especes_ou_en_cb(
                vente.client_du_caissier,
                vente.point_de_vente,
                champs_du_panier(vente, vente.adherente.email),
                carte,
                "espece",
                nouvelle_cle_d_idempotence(),
            )

    contenu = reponse.content.decode()
    assert 'data-testid="paiement-succes"' in contenu, contenu[:800]
    assert 'data-testid="alerte-adhesion-carte"' in contenu
    assert adhesion_enregistree_pour(vente, vente.adherente) is not None
    assert CarteCashless.objects.get(pk=carte.pk).user is None
    assert faux_fedow.NFCcard.linkwallet_card_number.call_count == 0


def test_le_total_compte_le_fed_de_l_adherente_apres_la_fusion(vente):
    """
    La carte anonyme porte 1,00 € de monnaie locale et 4,00 € de FED, Ada a 20,00 € de
    FED sur son compte. L'adhésion à 10,00 € : 1,00 € en local, 4,00 € en FED, 5,00 € en
    espèces. Fedow rattache ensuite la carte au compte d'Ada : le total affiche 20,00 €.
    / 1.00 € local + 4.00 € FED, Ada holds 20.00 € FED. After the merge the total is 20.
    """
    carte = creer_une_carte_nfc_chargee(vente.lieu, solde_en_centimes=100)

    with ancien_fedow_simule_par_carte(
        {carte.tag_id: 400}, {carte.tag_id: transaction_fed_du_reseau(400)}
    ) as faux_fedow:
        fiche_de_la_carte = faux_fedow.NFCcard.retrieve(carte.tag_id)

        def fedow_rattache_la_carte_a_ada(*arguments, **arguments_nommes):
            fiche_de_la_carte["wallet"]["tokens"][0]["value"] = 2000

        faux_fedow.NFCcard.linkwallet_card_number.side_effect = (
            fedow_rattache_la_carte_a_ada
        )
        with declaration_au_reseau_simulee():
            reponse = payer_le_reste_en_especes_ou_en_cb(
                vente.client_du_caissier,
                vente.point_de_vente,
                champs_du_panier(vente, vente.adherente.email),
                carte,
                "espece",
                nouvelle_cle_d_idempotence(),
                tag_id_carte_primaire=vente.tag_de_la_carte_primaire,
            )

    contenu = reponse.content.decode()
    assert 'data-testid="paiement-succes"' in contenu, contenu[:800]
    assert solde_total_de_l_ecran(contenu) == "20,00 €"
    verifier_la_vente_et_l_adhesion(
        vente,
        vente.adherente,
        carte,
        1000,
        [
            (PaymentMethod.LOCAL_EURO, 100),
            (PaymentMethod.STRIPE_FED, 400),
            (PaymentMethod.CASH, 500),
        ],
    )


def test_reseau_qui_refuse_apres_le_debit_fed_le_caissier_est_prevenu(vente):
    """
    Le FED de la carte vient d'être débité, puis la déclaration d'Ada au réseau échoue.
    Le FED ne s'annule pas : le caissier lit qu'il ne doit pas relancer le paiement, et
    aucune monnaie locale n'est débitée.
    / FED just debited, then the declaration fails: the cashier is told not to retry,
    and no local currency is debited.
    """
    carte = creer_une_carte_nfc_chargee(vente.lieu, solde_en_centimes=100)

    with ancien_fedow_simule_par_carte(
        {carte.tag_id: 400}, {carte.tag_id: transaction_fed_du_reseau(400)}
    ) as faux_fedow:
        with declaration_au_reseau_simulee() as declaration:
            declaration.side_effect = ConnectionError("Fedow injoignable")
            reponse = payer_le_reste_en_especes_ou_en_cb(
                vente.client_du_caissier,
                vente.point_de_vente,
                champs_du_panier(vente, vente.adherente.email),
                carte,
                "espece",
                nouvelle_cle_d_idempotence(),
                tag_id_carte_primaire=vente.tag_de_la_carte_primaire,
            )

    contenu = reponse.content.decode()
    assert reponse.status_code == 400, contenu[:500]
    assert "4.00 €" in contenu
    assert "Ne relancez pas" in contenu or "Do not retry" in contenu
    assert faux_fedow.transaction.to_place.call_count == 1
    assert not Membership.objects.filter(price=vente.adhesion.tarif).exists()
    assert not LigneArticle.objects.filter(
        pricesold__price=vente.adhesion.tarif
    ).exists()
    assert (
        WalletService.obtenir_solde(
            wallet=CarteCashless.objects.get(pk=carte.pk).wallet_ephemere,
            asset=monnaie_locale_du_lieu(vente.lieu),
        )
        == 100
    )
