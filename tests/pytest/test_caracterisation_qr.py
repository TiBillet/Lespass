"""
Tests de caractérisation : le paiement par QR code depuis « Ma tirelire » (parcours P10,
trou T2), en complément de `test_qrcodescanpay_flux_complet.py`.
/ Characterization tests: paying by QR code from the wallet page (flow P10, gap T2),
on top of `test_qrcodescanpay_flux_complet.py`.

LOCALISATION : tests/pytest/test_caracterisation_qr.py

À QUOI SERVENT CES TESTS
Un test de caractérisation FIGE le comportement d'aujourd'hui. Il ne dit pas si ce
comportement est bon : il dit « voilà ce que fait le code ». Il est vert sur le code
actuel. S'il tombe pendant le chantier 05 « montants entiers », c'est qu'une logique
métier a changé sans le vouloir : on s'arrête et on pose la question au mainteneur.
/ A characterization test FREEZES today's behaviour. It is green on the current code.
If it fails during chantier 05, a business rule changed by accident: stop and ask.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-A2-caracterisation.md
Détail des parcours : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-machine-a-etats.md (§4, §6).

LE PARCOURS
1. Un encaisseur du lieu génère un QR code pour un montant : une ligne de vente est
   créée « en attente » (`O`).
2. L'adhérent confirme le paiement : la ligne est réservée (`U`), Fedow débite son
   portefeuille, puis la ligne est SUPPRIMÉE et recréée validée (`V`), UNE fois quel
   que soit le nombre de monnaies débitées (Q-H3). Rien n'est envoyé à
   l'ancien LaBoutik ; deux mails partent (au lieu, à l'adhérent).
3. Si Fedow répond par une erreur, la ligne passe « échouée » (`D`) et ne se paie plus.
/ 1. A collector generates a QR code: a pending line. 2. The member confirms: the line
is reserved, Fedow debits, the line is recreated VALID once, nothing is sent to legacy
LaBoutik, two mails. 3. A Fedow error fails the line for good.

CE QUE CES TESTS REGARDENT (et rien d'autre)
- les statuts des lignes de vente, relus en base ;
- les appels au débit Fedow (simulé) : leur nombre ;
- les tâches Celery demandées : leur nom et leurs arguments.
Ils ne lisent JAMAIS directement sur la ligne un champ que le chantier retire
(`payment_method`, `asset`, `wallet`…).
/ They only read line statuses, Fedow debit calls and requested Celery tasks.

CODE PARCOURU / CODE EXERCISED
- BaseBillet/views.py — QrCodeScanPay.generate_qrcode (la demande),
  QrCodeScanPay.valid_payment (la confirmation, l'anti-rejeu, la recréation).

SIMULATIONS
Chaque test est marqué `django_db` : la transaction est annulée à la fin, rien ne reste
en base de dev. Fedow et Celery sont simulés : aucun appel réseau, aucune tâche envoyée
au worker. La vue importe Fedow DANS la méthode : le patch vise donc
`fedow_connect.fedow_api.FedowAPI`.
/ Rolled-back transaction per test. Fedow and Celery are faked. The view imports FedowAPI
inside the method, so the patch targets `fedow_connect.fedow_api.FedowAPI`.

L'assistant `etat_metier()` vient du premier fichier de caractérisation,
`test_caracterisation_en_ligne.py`.
/ `etat_metier()` comes from the first characterization file.

Lancer / Run : make test ARGS="tests/pytest/test_caracterisation_qr.py"
"""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django_tenants.utils import tenant_context

from AuthBillet.models import TibilletUser, Wallet
from BaseBillet.models import LigneArticle
from fabriques_panier import (
    client_connecte,
    creer_utilisateur,
    identifiant_unique,
    taches_celery_enregistrees,
)
from test_caracterisation_en_ligne import arguments_des_taches, etat_metier

pytestmark = pytest.mark.django_db

# Adresses du paiement par QR code (BaseBillet/urls.py).
# / QR code payment addresses.
URL_DE_LA_GENERATION_DU_QRCODE = "/qrcodescanpay/generate_qrcode/"
URL_DE_LA_CONFIRMATION_DU_PAIEMENT = "/qrcodescanpay/valid_payment/"

# Montant demandé par le QR code, en centimes.
# / Amount requested by the QR code, in cents.
MONTANT_DEMANDE_EN_CENTIMES = 1250


@pytest.fixture(autouse=True)
def _langue_par_defaut_apres_chaque_test():
    """Les signaux activent la langue du lieu sans la remettre (tests/PIEGES.md, 10.5).
    / Signals activate the venue language without resetting it."""
    from django.utils import translation

    yield
    translation.deactivate()


@pytest.fixture
def lieu(tenant):
    """
    Le lieu `lespass`, avec Celery simulé pendant tout le test.
    / The `lespass` venue, with Celery faked for the whole test.

    `taches_demandees` se remplit au fil du test : une paire (nom court, arguments) par
    tâche demandée.
    / `taches_demandees` fills up during the test: one (short name, args) pair per task.
    """
    with tenant_context(tenant):
        with taches_celery_enregistrees() as taches_demandees:
            yield SimpleNamespace(tenant=tenant, taches_demandees=taches_demandees)


# --------------------------------------------------------------------------
# Les deux personnes du parcours, et Fedow
# / The two people of the flow, and Fedow
# --------------------------------------------------------------------------


def creer_un_encaisseur(lieu):
    """
    Le client HTTP d'un encaisseur : il a le droit d'initier un paiement dans ce lieu
    (`initiate_payment`). Sans ce droit, la génération du QR code répond 403.
    / The collector's HTTP client: allowed to initiate payments in this venue.
    """
    encaisseur = creer_utilisateur(prenom="Encaisseur", nom="QR")
    encaisseur.initiate_payment.add(lieu.tenant)
    return client_connecte(encaisseur)


def creer_un_payeur():
    """
    Un adhérent qui paie, adresse e-mail confirmée : la confirmation d'un paiement la
    refuse sinon. On la pose par `update()`, état de départ sans signal
    (tests/PIEGES.md 12.17).
    / A paying member with a confirmed e-mail (required to confirm a payment).
    """
    payeur = creer_utilisateur(prenom="Ada", nom="Payeuse")
    TibilletUser.objects.filter(pk=payeur.pk).update(email_valid=True)
    payeur.refresh_from_db()
    return payeur


def generer_un_qrcode(client_de_l_encaisseur):
    """
    L'encaisseur génère un QR code de 12,50 € en euros. Rend la ligne de vente créée
    « en attente » : son uuid est le contenu du QR code.
    La ligne est retrouvée par son uuid, lu dans la page rendue.
    / The collector generates a 12.50 € QR code. Returns the pending sale line, found by
    the uuid read in the rendered page.
    """
    reponse = client_de_l_encaisseur.post(
        URL_DE_LA_GENERATION_DU_QRCODE,
        {"amount": str(MONTANT_DEMANDE_EN_CENTIMES / 100), "asset_type": "EUR"},
    )
    assert reponse.status_code == 200
    uuid_de_la_demande = reponse.context["ligne_article_uuid_hex"]
    return LigneArticle.objects.get(uuid=uuid.UUID(uuid_de_la_demande))


def confirmer_le_paiement(client_du_payeur, demande_de_paiement):
    """L'adhérent confirme le paiement du QR code (bouton de l'écran de validation).
    / The member confirms the QR code payment."""
    return client_du_payeur.post(
        URL_DE_LA_CONFIRMATION_DU_PAIEMENT,
        {"ligne_article_uuid_hex": demande_de_paiement.uuid.hex},
    )


def fedow_simule(transactions_du_debit, monnaies_du_fedow):
    """
    Un Fedow distant simulé, dont le solde couvre largement le paiement.
    / A faked remote Fedow, whose balance largely covers the payment.

    `transactions_du_debit` : ce que Fedow rend quand il débite, une transaction par
    monnaie (`{"uuid": uuid, "asset": uuid, "amount": centimes}`).
    `monnaies_du_fedow` : la fiche de chaque monnaie, par uuid (`{"category": "TLF"}`).
    / `transactions_du_debit`: one transaction per currency. `monnaies_du_fedow`: each
    currency's record, by uuid.

    Le portefeuille rendu est un VRAI `Wallet` : la vue le pose sur la ligne de vente,
    une clé étrangère qui refuse un objet simulé.
    / The returned wallet is a REAL Wallet: the view stores it on the sale line.
    """
    portefeuille_du_payeur = Wallet.objects.create(
        name=f"TEST_caracterisation portefeuille {identifiant_unique()}"
    )
    faux_fedow = MagicMock()
    faux_fedow.wallet.get_or_create_wallet.return_value = (
        portefeuille_du_payeur,
        False,
    )
    faux_fedow.wallet.get_total_fiducial_and_all_federated_token.return_value = 99999
    faux_fedow.transaction.to_place_from_qrcode.return_value = transactions_du_debit
    faux_fedow.asset.retrieve.side_effect = monnaies_du_fedow.get
    return faux_fedow


# --------------------------------------------------------------------------
# P10 — Un paiement débité sur deux monnaies
# / P10 — A payment debited from two currencies
# --------------------------------------------------------------------------


def test_qr_deux_monnaies_aucun_envoi_laboutik_et_deux_mails(
    lieu, django_capture_on_commit_callbacks
):
    """
    P10 : l'adhérent confirme un QR code de 12,50 €. Fedow débite 5 € de monnaie locale
    et 7,50 € de monnaie fédérée. La demande est remplacée par UNE ligne validée
    (`V`), quel que soit le nombre de monnaies (Q-H3).
    Tâches : AUCUN envoi à l'ancien LaBoutik (débranché pour le QR code), puis le mail
    au lieu et le mail à l'adhérent, avec le montant demandé en centimes.
    / P10: a 12.50 € QR code paid with 5 € local + 7.50 € federated currency. One VALID
    line. Tasks: nothing sent to legacy LaBoutik, then the two mails.
    """
    client_de_l_encaisseur = creer_un_encaisseur(lieu)
    payeur = creer_un_payeur()
    client_du_payeur = client_connecte(payeur)
    uuid_de_la_monnaie_locale = str(uuid.uuid4())
    uuid_de_la_monnaie_federee = str(uuid.uuid4())
    faux_fedow = fedow_simule(
        transactions_du_debit=[
            {"uuid": uuid.uuid4(), "asset": uuid_de_la_monnaie_locale, "amount": 500},
            {"uuid": uuid.uuid4(), "asset": uuid_de_la_monnaie_federee, "amount": 750},
        ],
        monnaies_du_fedow={
            uuid_de_la_monnaie_locale: {"category": "TLF"},
            uuid_de_la_monnaie_federee: {"category": "FED"},
        },
    )
    demande_de_paiement = generer_un_qrcode(client_de_l_encaisseur)
    # On ne garde que les tâches demandées par la confirmation.
    # / Keep only the tasks requested by the confirmation.
    lieu.taches_demandees.clear()

    with patch("fedow_connect.fedow_api.FedowAPI", return_value=faux_fedow):
        with django_capture_on_commit_callbacks(execute=True):
            reponse = confirmer_le_paiement(client_du_payeur, demande_de_paiement)

    assert reponse.status_code == 200
    taches_de_la_confirmation = lieu.taches_demandees
    etat_attendu = {
        "taches": [
            "send_payment_success_admin",
            "send_payment_success_user",
        ],
    }
    assert etat_metier(taches_demandees=taches_de_la_confirmation) == etat_attendu
    assert faux_fedow.transaction.to_place_from_qrcode.call_count == 1

    # La ligne recréée, une seule pour les deux monnaies, validée. Elle garde l'uuid de
    # la demande ; c'est l'unique article de la vente.
    # / The single recreated line, VALID. It keeps the request uuid; the sale's only
    # item.
    premiere_ligne_recreee = LigneArticle.objects.get(uuid=demande_de_paiement.uuid)
    statuts_des_lignes_recreees = []
    for ligne in premiere_ligne_recreee.vente.articles.all():
        statuts_des_lignes_recreees.append(ligne.status)
    assert sorted(statuts_des_lignes_recreees) == [
        LigneArticle.VALID,
    ]

    # Les deux mails : au lieu, puis à l'adhérent, avec le montant en centimes.
    # Arguments : (montant, date, lieu, e-mail) et (e-mail, montant, date, lieu).
    # / The two mails: to the venue, then to the member, with the amount in cents.
    mail_au_lieu = arguments_des_taches(
        taches_de_la_confirmation, "send_payment_success_admin"
    )[0]
    mail_a_l_adherent = arguments_des_taches(
        taches_de_la_confirmation, "send_payment_success_user"
    )[0]
    assert mail_au_lieu[0] == 1250
    assert mail_au_lieu[3] == payeur.email
    assert mail_a_l_adherent[0] == payeur.email
    assert mail_a_l_adherent[1] == 1250


# --------------------------------------------------------------------------
# P10 / T2 — Fedow en erreur pendant le débit, puis nouvel essai
# / P10 / T2 — Fedow fails during the debit, then a new attempt
# --------------------------------------------------------------------------


def test_qr_echec_fedow_ligne_en_echec_rejeu_refuse(
    lieu, django_capture_on_commit_callbacks
):
    """
    P10, T2 : la demande de paiement est « en attente » (`O`). L'adhérent confirme, et
    Fedow répond par une erreur pendant le débit : on ne sait pas s'il a débité. La
    ligne passe « échouée » (`D`). L'adhérent confirme une seconde fois : refusé, Fedow
    n'est PAS rappelé (un seul débit demandé en tout), la ligne reste `D`. Aucune tâche
    n'est demandée : ni envoi à l'ancien LaBoutik, ni mail.
    Le refus vient de la réservation de la ligne, qui ne prend qu'une demande QR encore
    « en attente » (filtre sur le moyen de paiement « QR code », voir T2).
    Reste vert en H : T2 remplace ce filtre, le comportement ne change pas.
    / P10, T2: Fedow errors during the debit: the line FAILS. A second confirmation is
    refused without calling Fedow again. No task requested.
    """
    client_de_l_encaisseur = creer_un_encaisseur(lieu)
    payeur = creer_un_payeur()
    client_du_payeur = client_connecte(payeur)
    faux_fedow = fedow_simule(transactions_du_debit=[], monnaies_du_fedow={})
    faux_fedow.transaction.to_place_from_qrcode.side_effect = ConnectionError(
        "Fedow injoignable"
    )
    demande_de_paiement = generer_un_qrcode(client_de_l_encaisseur)
    assert demande_de_paiement.status == LigneArticle.CREATED
    # On ne garde que les tâches demandées par les deux confirmations.
    # / Keep only the tasks requested by the two confirmations.
    lieu.taches_demandees.clear()

    with patch("fedow_connect.fedow_api.FedowAPI", return_value=faux_fedow):
        with django_capture_on_commit_callbacks(execute=True):
            premiere_reponse = confirmer_le_paiement(
                client_du_payeur, demande_de_paiement
            )
            demande_de_paiement.refresh_from_db()
            statut_apres_la_premiere_confirmation = demande_de_paiement.status

            deuxieme_reponse = confirmer_le_paiement(
                client_du_payeur, demande_de_paiement
            )

    assert premiere_reponse.status_code == 200
    assert deuxieme_reponse.status_code == 200
    assert statut_apres_la_premiere_confirmation == LigneArticle.FAILED
    demande_de_paiement.refresh_from_db()
    assert demande_de_paiement.status == LigneArticle.FAILED
    assert faux_fedow.transaction.to_place_from_qrcode.call_count == 1
    assert etat_metier(taches_demandees=lieu.taches_demandees) == {"taches": []}
