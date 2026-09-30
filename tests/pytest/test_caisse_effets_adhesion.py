"""
Tests des effets d'une adhésion vendue à la CAISSE : facture par mail, récompense en
monnaie, rattachement de l'adhérent au lieu, échéance au renouvellement.
/ Tests of the effects of a membership sold at the CASH REGISTER: invoice mail, currency
reward, member attached to the venue, deadline on renewal.

LOCALISATION : tests/pytest/test_caisse_effets_adhesion.py

RÈGLE MÉTIER TESTÉE
Une adhésion payée a les mêmes effets en ligne et en caisse, par un seul code
(BaseBillet/triggers.py). La caisse ajoute une contrainte : elle crée l'adhésion DANS la
transaction du paiement. Toute tâche Celery (facture, newsletter, récompense) est donc
demandée APRÈS la validation en base : le worker Celery a sa propre connexion et ne
verrait pas une adhésion encore en cours d'écriture.
La caisse V2 n'envoie rien à l'ancien LaBoutik (`send_sale_to_laboutik`).
/ A paid membership has the same effects online and at the register, through one single
piece of code. At the register, every Celery task is requested AFTER the commit. The V2
register sends nothing to legacy LaBoutik.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-B-caisse.md §2 bis.

CODE PARCOURU / CODE EXERCISED
- laboutik/views.py — PaiementViewSet.payer, _payer_en_especes, _payer_par_nfc,
  PaiementViewSet.payer_complementaire (complément en espèces, seconde carte),
  _creer_adhesions_depuis_panier, _creer_ou_renouveler_adhesion,
  _appliquer_les_effets_d_une_adhesion_vendue_en_caisse ;
- BaseBillet/triggers.py — les effets communs d'une adhésion payée ;
- BaseBillet/tasks.py — send_membership_invoice_to_email (exécutée pour de vrai dans
  `test_facture_de_l_adhesion_caisse_part_au_bon_destinataire`).

SIMULATIONS
Chaque test est marqué `django_db` : la transaction est annulée à la fin (tests/PIEGES.md
13.1). La caisse est activée par `configuration_modifiee()`, jamais enregistrée
(tests/PIEGES.md 13.22). Fedow et Celery sont simulés : aucun appel réseau, aucune tâche
envoyée au worker (tests/PIEGES.md 13.4). Les tâches lancées en `transaction.on_commit`
sont exécutées par `django_capture_on_commit_callbacks(execute=True)` (tests/PIEGES.md
13.14).
/ Rolled-back transaction per test. The register module is switched on in memory only.
Fedow and Celery are faked. on_commit tasks are run by the capture fixture.

Lancer / Run : make test ARGS="tests/pytest/test_caisse_effets_adhesion.py"
"""

import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django_tenants.utils import tenant_context

from AuthBillet.models import Wallet
from BaseBillet.models import LigneArticle, Membership
from BaseBillet.tasks import send_membership_invoice_to_email
from fabriques_panier import (
    configuration_modifiee,
    creer_adhesion,
    creer_une_adhesion_active,
    creer_utilisateur,
    identifiant_unique,
    noms_des_taches,
    taches_celery_enregistrees,
)
from fedow_connect.models import FedowConfig
from fedow_core.models import Asset, Token
from fedow_core.services import AssetService
from QrcodeCashless.models import CarteCashless
from test_caracterisation_caisse import (
    creer_un_point_de_vente,
    creer_une_carte_nfc_chargee,
    payer_a_la_caisse,
)
from test_caracterisation_en_ligne import (
    arguments_des_taches,
    creer_un_administrateur_du_lieu,
)

pytestmark = pytest.mark.django_db

# Les noms courts des tâches Celery regardées par ces tests.
# / Short names of the Celery tasks these tests look at.
TACHE_DE_LA_FACTURE = "send_membership_invoice_to_email"
TACHE_DE_LA_RECOMPENSE = "refill_from_lespass_to_user_wallet_from_price_solded"
TACHE_D_ENVOI_A_L_ANCIEN_LABOUTIK = "send_sale_to_laboutik"
TACHE_DU_WEBHOOK_D_ADHESION = "webhook_membership"


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
    Le lieu `lespass`, caisse activée, avec Celery simulé pendant tout le test.
    / The `lespass` venue, register switched on, with Celery faked for the whole test.

    La caisse n'est accessible que si le module caisse (et donc le module monnaie
    locale) est actif. On l'active EN MÉMOIRE : `configuration_modifiee()` ne sauve
    jamais la `Configuration`, dont le cache est partagé avec le serveur live.
    / The register needs its module on. It is switched on in memory only.

    `taches_demandees` se remplit au fil du test : une paire (nom court, arguments) par
    tâche demandée.
    / `taches_demandees` fills up during the test: one (short name, args) pair per task.
    """
    with tenant_context(tenant):
        with configuration_modifiee(module_caisse=True, module_monnaie_locale=True):
            with taches_celery_enregistrees() as taches_demandees:
                yield SimpleNamespace(
                    tenant=tenant,
                    taches_demandees=taches_demandees,
                )


# --------------------------------------------------------------------------
# Gestes du caissier
# / Cashier actions
# --------------------------------------------------------------------------


def vendre_l_adhesion_a_la_caisse(
    client_du_caissier,
    point_de_vente,
    adhesion,
    moyen_de_paiement,
    autres_champs,
):
    """
    Le caissier vend une adhésion, par la vraie route de paiement de la caisse.
    / The cashier sells a membership, through the real register payment route.

    La caisse déclare l'adhérent au réseau Fedow avant d'enregistrer l'adhésion
    (laboutik/views.py, `_declarer_adherent_au_reseau`). Le lieu est dit « branché à
    Fedow », et la déclaration est simulée : aucun appel réseau.
    / The register declares the member to Fedow first: the venue is said to be
    connected, and the declaration is faked.

    `moyen_de_paiement` : "espece" ou "nfc".
    `autres_champs` : e-mail et nom de l'adhérent, ou `tag_id` de sa carte.
    """
    with patch.object(FedowConfig, "can_fedow", return_value=True):
        with patch("fedow_connect.services.declarer_wallet_user_a_fedow"):
            return payer_a_la_caisse(
                client_du_caissier,
                point_de_vente,
                adhesion,
                quantite=1,
                moyen_de_paiement=moyen_de_paiement,
                autres_champs=autres_champs,
            )


def champs_de_l_adherente(adherente):
    """Les champs que le caissier remplit pour identifier l'adhérente.
    / The fields the cashier fills in to identify the member."""
    return {
        "email_adhesion": adherente.email,
        "prenom_adhesion": "Ada",
        "nom_adhesion": "Lovelace",
    }


def creer_la_carte_de_l_adherente_en_deux_monnaies(lieu, adherente):
    """
    ÉTAT DE DÉPART : une carte NFC rattachée à l'adhérente. Son portefeuille porte
    10,00 € de monnaie cadeau et 50,00 € de monnaie locale.
    / STARTING STATE: an NFC card linked to the member, holding 10.00 € of gift currency
    and 50.00 € of local currency.

    La caisse paie en cascade : d'abord la monnaie cadeau, puis la monnaie locale
    (laboutik/views.py `ORDRE_CASCADE_FIDUCIAIRE`). Une adhésion à 20 € est donc payée
    en deux morceaux : 10 € cadeau + 10 € locale, soit deux lignes de vente.
    / The register pays in cascade: gift first, then local. A 20 € membership is paid in
    two parts, hence two sale lines.

    Pour chaque monnaie, la caisse lit la PREMIÈRE du lieu dans sa catégorie : on crédite
    la carte dans cette monnaie-là, lue par la même requête (tests/PIEGES.md 9.97).
    / For each currency the register reads the FIRST one of its category: the card is
    credited in that very currency, read by the same query.

    La carte porte déjà l'adhérente : la caisse l'identifie par sa carte, sans lier de
    carte chez Fedow.
    / The card already carries the member: the register identifies her by it.
    """
    monnaies_du_lieu = AssetService.obtenir_assets_accessibles(lieu.tenant)
    monnaie_cadeau = monnaies_du_lieu.filter(category=Asset.TNF).first()
    monnaie_locale = monnaies_du_lieu.filter(category=Asset.TLF).first()

    portefeuille_de_l_adherente = Wallet.objects.create(
        name=f"TEST_effets_adhesion carte {identifiant_unique()}",
        origin=lieu.tenant,
    )
    adherente.wallet = portefeuille_de_l_adherente
    adherente.save(update_fields=["wallet"])

    identifiant_de_la_carte = identifiant_unique().upper()
    carte = CarteCashless.objects.create(
        tag_id=identifiant_de_la_carte,
        number=identifiant_de_la_carte,
        uuid=uuid.uuid4(),
        user=adherente,
    )
    Token.objects.create(
        wallet=portefeuille_de_l_adherente,
        asset=monnaie_cadeau,
        value=1000,
    )
    Token.objects.create(
        wallet=portefeuille_de_l_adherente,
        asset=monnaie_locale,
        value=5000,
    )
    return carte


def creer_la_carte_de_l_adherente_avec_10_euros(lieu, adherente):
    """
    ÉTAT DE DÉPART : une carte NFC rattachée à l'adhérente, qui porte 10,00 € de
    monnaie locale. Elle ne suffit pas pour une adhésion à 20 € : la caisse propose
    alors de compléter (espèces, carte bancaire ou seconde carte).
    / STARTING STATE: an NFC card linked to the member, holding 10.00 € of local
    currency. Not enough for a 20 € membership: the register offers a complement.

    La caisse lit la PREMIÈRE monnaie locale du lieu : on crédite la carte dans
    celle-là, lue par la même requête (tests/PIEGES.md 9.97).
    / The register reads the FIRST local currency: the card is credited in it.
    """
    monnaie_locale = (
        AssetService.obtenir_assets_accessibles(lieu.tenant)
        .filter(category=Asset.TLF)
        .first()
    )
    portefeuille_de_l_adherente = Wallet.objects.create(
        name=f"TEST_effets_adhesion carte {identifiant_unique()}",
        origin=lieu.tenant,
    )
    adherente.wallet = portefeuille_de_l_adherente
    adherente.save(update_fields=["wallet"])

    identifiant_de_la_carte = identifiant_unique().upper()
    carte = CarteCashless.objects.create(
        tag_id=identifiant_de_la_carte,
        number=identifiant_de_la_carte,
        uuid=uuid.uuid4(),
        user=adherente,
    )
    Token.objects.create(
        wallet=portefeuille_de_l_adherente,
        asset=monnaie_locale,
        value=1000,
    )
    return carte


def completer_le_paiement_de_l_adhesion(
    client_du_caissier, point_de_vente, adhesion, champs_du_complement
):
    """
    Le caissier complète un paiement par carte NFC trop peu chargée, par la vraie route
    du complément (`/laboutik/paiement/payer_complementaire/`). Le panier est renvoyé,
    comme le fait l'écran de complément (il inclut #addition-form).
    / The cashier completes an under-funded NFC payment through the real complement
    route. The cart is sent again, as the complement screen does.

    `champs_du_complement` : `tag_id_carte1` et `moyen_complement` ("espece" ou "nfc"),
    plus `tag_id` de la seconde carte pour "nfc".
    """
    donnees_du_formulaire = {
        "uuid_pv": str(point_de_vente.uuid),
        f"repid-{adhesion.produit.uuid}--{adhesion.tarif.uuid}": "1",
        "given_sum": "",
    }
    donnees_du_formulaire.update(champs_du_complement)
    return client_du_caissier.post(
        "/laboutik/paiement/payer_complementaire/", donnees_du_formulaire
    )


# --------------------------------------------------------------------------
# Les tests
# / The tests
# --------------------------------------------------------------------------


def test_adhesion_caisse_especes_demande_facture_et_recompense(
    lieu, django_capture_on_commit_callbacks
):
    """
    Le caissier vend une adhésion à 20 € en espèces à une adhérente sans nom ni prénom,
    identifiée par son e-mail.
    Résultat :
    - la facture par mail est demandée, pour cette adhésion ;
    - la récompense en monnaie est demandée, pour la ligne de vente de l'adhésion ;
    - RIEN n'est envoyé à l'ancien LaBoutik ;
    - l'adhérente est rattachée au lieu (visible dans l'admin et dans « Mon compte ») ;
    - elle reçoit le nom et le prénom saisis pour l'adhésion.
    / Cash membership sale: invoice and reward requested, nothing sent to legacy LaBoutik,
    member attached to the venue and given the membership's names.
    """
    adherente = creer_utilisateur(prenom="", nom="")
    adhesion = creer_adhesion(prix="20.00")
    point_de_vente = creer_un_point_de_vente([adhesion.produit])
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    # On ne garde que les tâches demandées par la vente.
    # / Keep only the tasks requested by the sale.
    lieu.taches_demandees.clear()

    with django_capture_on_commit_callbacks(execute=True):
        reponse = vendre_l_adhesion_a_la_caisse(
            client_du_caissier,
            point_de_vente,
            adhesion,
            moyen_de_paiement="espece",
            autres_champs=champs_de_l_adherente(adherente),
        )

    assert reponse.status_code == 200
    adhesion_vendue = Membership.objects.get(user=adherente, price=adhesion.tarif)
    ligne_de_l_adhesion = LigneArticle.objects.get(
        pricesold__price=adhesion.tarif, membership=adhesion_vendue
    )

    assert arguments_des_taches(lieu.taches_demandees, TACHE_DE_LA_FACTURE) == [
        (str(adhesion_vendue.uuid),)
    ]
    assert arguments_des_taches(lieu.taches_demandees, TACHE_DE_LA_RECOMPENSE) == [
        (ligne_de_l_adhesion.pk,)
    ]
    assert (
        arguments_des_taches(lieu.taches_demandees, TACHE_D_ENVOI_A_L_ANCIEN_LABOUTIK)
        == []
    )

    adherente.refresh_from_db()
    assert lieu.tenant in adherente.client_achat.all()
    assert adherente.first_name == "Ada"
    assert adherente.last_name == "Lovelace"


def test_adhesion_caisse_nfc_demande_facture_et_recompense_une_fois(
    lieu, django_capture_on_commit_callbacks
):
    """
    Le caissier vend une adhésion à 20 €, payée avec la carte NFC de l'adhérente. La
    carte porte 10 € de monnaie cadeau et 50 € de monnaie locale : la caisse paie en
    cascade, et crée DEUX lignes de vente pour la même adhésion.
    Résultat : UNE seule facture et UNE seule récompense, pour la ligne qui porte
    l'adhésion. Rien n'est envoyé à l'ancien LaBoutik. L'adhérente est rattachée au lieu.
    / NFC cascade payment: two sale lines for one membership, yet ONE invoice and ONE
    reward, for the line that carries the membership. Nothing sent to legacy LaBoutik.
    The member is attached to the venue.
    """
    adherente = creer_utilisateur(prenom="Ada", nom="Lovelace")
    adhesion = creer_adhesion(prix="20.00")
    point_de_vente = creer_un_point_de_vente([adhesion.produit])
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    carte_de_l_adherente = creer_la_carte_de_l_adherente_en_deux_monnaies(
        lieu, adherente
    )
    lieu.taches_demandees.clear()

    with django_capture_on_commit_callbacks(execute=True):
        reponse = vendre_l_adhesion_a_la_caisse(
            client_du_caissier,
            point_de_vente,
            adhesion,
            moyen_de_paiement="nfc",
            autres_champs={"tag_id": carte_de_l_adherente.tag_id},
        )

    assert reponse.status_code == 200
    # Le parcours en cascade a bien eu lieu : deux lignes pour une adhésion. Sans
    # elles, « une seule facture » ne prouverait rien.
    # / The cascade did happen: two lines for one membership.
    assert LigneArticle.objects.filter(pricesold__price=adhesion.tarif).count() == 2

    adhesion_vendue = Membership.objects.get(user=adherente, price=adhesion.tarif)
    ligne_qui_porte_l_adhesion = LigneArticle.objects.get(
        pricesold__price=adhesion.tarif, membership=adhesion_vendue
    )
    assert arguments_des_taches(lieu.taches_demandees, TACHE_DE_LA_FACTURE) == [
        (str(adhesion_vendue.uuid),)
    ]
    assert arguments_des_taches(lieu.taches_demandees, TACHE_DE_LA_RECOMPENSE) == [
        (ligne_qui_porte_l_adhesion.pk,)
    ]
    assert (
        arguments_des_taches(lieu.taches_demandees, TACHE_D_ENVOI_A_L_ANCIEN_LABOUTIK)
        == []
    )

    # Identifiée par sa carte, l'adhérente ne passe pas par `get_or_create_user` (qui
    # rattache au lieu lors d'une identification par e-mail) : seul l'effet commun de
    # l'adhésion la rattache au lieu.
    # / Identified by her card, the member skips get_or_create_user: only the shared
    # membership effect attaches her to the venue.
    assert lieu.tenant in adherente.client_achat.all()


def test_adhesion_caisse_complement_demande_facture_et_recompense(
    lieu, django_capture_on_commit_callbacks
):
    """
    Le caissier vend une adhésion à 20 €. La carte NFC de l'adhérente ne porte que 10 € :
    la caisse affiche l'écran de complément, et le caissier règle les 10 € restants en
    espèces (`_executer_paiement_complementaire`, branche espèces / CB).
    Résultat : une facture et une récompense, pour la ligne qui porte l'adhésion ; rien
    n'est envoyé à l'ancien LaBoutik ; l'adhérente est rattachée au lieu.
    / 20 € membership, the member's card holds 10 €: the rest is paid in cash through
    the complement route. One invoice, one reward, nothing to legacy LaBoutik, member
    attached to the venue.
    """
    adherente = creer_utilisateur(prenom="Ada", nom="Lovelace")
    adhesion = creer_adhesion(prix="20.00")
    point_de_vente = creer_un_point_de_vente([adhesion.produit])
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    carte_de_l_adherente = creer_la_carte_de_l_adherente_avec_10_euros(lieu, adherente)
    lieu.taches_demandees.clear()

    # Le lieu est dit « hors réseau Fedow » : la caisse ne lit pas le solde du réseau
    # (`lire_depensable_fed_frais`), aucun appel réseau. Le complément ne déclare pas
    # l'adhérente au réseau : elle est identifiée par sa carte.
    # / The venue is said to be off the Fedow network: no network balance read.
    with patch.object(FedowConfig, "can_fedow", return_value=False):
        with django_capture_on_commit_callbacks(execute=True):
            reponse_de_la_carte = payer_a_la_caisse(
                client_du_caissier,
                point_de_vente,
                adhesion,
                quantite=1,
                moyen_de_paiement="nfc",
                autres_champs={"tag_id": carte_de_l_adherente.tag_id},
            )
            reponse_du_complement = completer_le_paiement_de_l_adhesion(
                client_du_caissier,
                point_de_vente,
                adhesion,
                champs_du_complement={
                    "moyen_complement": "espece",
                    "tag_id_carte1": carte_de_l_adherente.tag_id,
                },
            )

    # La carte ne suffit pas : la caisse propose bien le complément.
    # / The card is not enough: the register does offer the complement.
    assert reponse_de_la_carte.status_code == 200
    assert 'data-testid="complement-paiement"' in reponse_de_la_carte.content.decode()
    assert reponse_du_complement.status_code == 200
    # Deux lignes : 10 € par la carte, 10 € en espèces.
    # / Two lines: 10 € by card, 10 € in cash.
    assert LigneArticle.objects.filter(pricesold__price=adhesion.tarif).count() == 2

    adhesion_vendue = Membership.objects.get(user=adherente, price=adhesion.tarif)
    ligne_qui_porte_l_adhesion = LigneArticle.objects.get(
        pricesold__price=adhesion.tarif, membership=adhesion_vendue
    )
    assert arguments_des_taches(lieu.taches_demandees, TACHE_DE_LA_FACTURE) == [
        (str(adhesion_vendue.uuid),)
    ]
    assert arguments_des_taches(lieu.taches_demandees, TACHE_DE_LA_RECOMPENSE) == [
        (ligne_qui_porte_l_adhesion.pk,)
    ]
    assert (
        arguments_des_taches(lieu.taches_demandees, TACHE_D_ENVOI_A_L_ANCIEN_LABOUTIK)
        == []
    )
    assert lieu.tenant in adherente.client_achat.all()


def test_adhesion_caisse_seconde_carte_demande_facture_et_recompense(
    lieu, django_capture_on_commit_callbacks
):
    """
    Le caissier vend une adhésion à 20 €. La carte NFC de l'adhérente ne porte que 10 € :
    la caisse affiche l'écran de complément, et le caissier règle les 10 € restants avec
    une seconde carte, anonyme et chargée (`_executer_paiement_complementaire`, branche
    seconde carte). L'adhésion va au porteur de la première carte.
    Résultat : une facture et une récompense, pour la ligne qui porte l'adhésion ; rien
    n'est envoyé à l'ancien LaBoutik ; l'adhérente est rattachée au lieu.
    / 20 € membership, the member's card holds 10 €: the rest is paid with a second,
    anonymous card. One invoice, one reward, nothing to legacy LaBoutik, member attached
    to the venue.
    """
    adherente = creer_utilisateur(prenom="Ada", nom="Lovelace")
    adhesion = creer_adhesion(prix="20.00")
    point_de_vente = creer_un_point_de_vente([adhesion.produit])
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    carte_de_l_adherente = creer_la_carte_de_l_adherente_avec_10_euros(lieu, adherente)
    seconde_carte = creer_une_carte_nfc_chargee(lieu, solde_en_centimes=5000)
    lieu.taches_demandees.clear()

    # Le lieu est dit « hors réseau Fedow » : aucun appel réseau (voir le test du
    # complément en espèces).
    # / The venue is said to be off the Fedow network: no network call.
    with patch.object(FedowConfig, "can_fedow", return_value=False):
        with django_capture_on_commit_callbacks(execute=True):
            reponse_de_la_carte = payer_a_la_caisse(
                client_du_caissier,
                point_de_vente,
                adhesion,
                quantite=1,
                moyen_de_paiement="nfc",
                autres_champs={"tag_id": carte_de_l_adherente.tag_id},
            )
            reponse_de_la_seconde_carte = completer_le_paiement_de_l_adhesion(
                client_du_caissier,
                point_de_vente,
                adhesion,
                champs_du_complement={
                    "moyen_complement": "nfc",
                    "tag_id_carte1": carte_de_l_adherente.tag_id,
                    "tag_id": seconde_carte.tag_id,
                },
            )

    assert reponse_de_la_carte.status_code == 200
    assert 'data-testid="complement-paiement"' in reponse_de_la_carte.content.decode()
    assert reponse_de_la_seconde_carte.status_code == 200
    # Deux lignes : 10 € par chaque carte.
    # / Two lines: 10 € from each card.
    assert LigneArticle.objects.filter(pricesold__price=adhesion.tarif).count() == 2

    adhesion_vendue = Membership.objects.get(user=adherente, price=adhesion.tarif)
    ligne_qui_porte_l_adhesion = LigneArticle.objects.get(
        pricesold__price=adhesion.tarif, membership=adhesion_vendue
    )
    assert arguments_des_taches(lieu.taches_demandees, TACHE_DE_LA_FACTURE) == [
        (str(adhesion_vendue.uuid),)
    ]
    assert arguments_des_taches(lieu.taches_demandees, TACHE_DE_LA_RECOMPENSE) == [
        (ligne_qui_porte_l_adhesion.pk,)
    ]
    assert (
        arguments_des_taches(lieu.taches_demandees, TACHE_D_ENVOI_A_L_ANCIEN_LABOUTIK)
        == []
    )
    assert lieu.tenant in adherente.client_achat.all()


def test_adhesion_caisse_renouvelee_echeance_posee_une_fois(
    lieu, django_capture_on_commit_callbacks
):
    """
    L'adhérente a déjà une adhésion en cours, qui finit dans 30 jours. Le caissier la
    renouvelle en espèces (adhésion annuelle).
    Résultat : l'adhésion existante est renouvelée (pas de seconde adhésion) ; son
    échéance est posée une fois, par les effets communs, et prolongée d'un an ; une
    facture et une récompense sont demandées.
    Deux webhooks d'adhésion sortants partent, comme au renouvellement en ligne :
    l'adhésion est enregistrée deux fois (mise à jour, puis échéance), et chaque
    enregistrement d'une adhésion qui a une échéance demande un webhook
    (BaseBillet/signals.py, `create_lignearticle_if_membership_created_on_admin`). Ce
    doublon est le bug n°2 de TECH_DOC/SESSIONS/TODO/BUGS-constats-chantier-05.md, à
    corriger pour tous les canaux à la fois ; ce test le fige.
    / Renewal at the register: the existing membership is renewed, its deadline set once
    and extended by a year, one invoice and one reward requested. Two outgoing membership
    webhooks, as online renewal: bug #2 of the chantier 05 TODO, frozen here.
    """
    adherente = creer_utilisateur(prenom="Ada", nom="Lovelace")
    adhesion = creer_adhesion(prix="20.00")
    adhesion_en_cours = creer_une_adhesion_active(
        adherente, adhesion, jours_restants=30
    )
    echeance_avant_le_renouvellement = adhesion_en_cours.deadline
    point_de_vente = creer_un_point_de_vente([adhesion.produit])
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    lieu.taches_demandees.clear()

    with django_capture_on_commit_callbacks(execute=True):
        reponse = vendre_l_adhesion_a_la_caisse(
            client_du_caissier,
            point_de_vente,
            adhesion,
            moyen_de_paiement="espece",
            autres_champs=champs_de_l_adherente(adherente),
        )

    assert reponse.status_code == 200
    assert Membership.objects.filter(user=adherente, price=adhesion.tarif).count() == 1

    # L'échéance est prolongée : un an après aujourd'hui, bien au-delà des 30 jours qui
    # restaient.
    # / The deadline is extended: one year from today, well beyond the 30 days left.
    adhesion_en_cours.refresh_from_db()
    echeance_minimale_attendue = echeance_avant_le_renouvellement + timedelta(days=300)
    assert adhesion_en_cours.deadline > echeance_minimale_attendue

    ligne_du_renouvellement = LigneArticle.objects.get(
        pricesold__price=adhesion.tarif, membership=adhesion_en_cours
    )
    assert arguments_des_taches(lieu.taches_demandees, TACHE_DE_LA_FACTURE) == [
        (str(adhesion_en_cours.uuid),)
    ]
    assert arguments_des_taches(lieu.taches_demandees, TACHE_DE_LA_RECOMPENSE) == [
        (ligne_du_renouvellement.pk,)
    ]
    # Doublon figé : bug n°2 du TODO du chantier 05.
    # / Frozen duplicate: bug #2 of the chantier 05 TODO.
    assert arguments_des_taches(lieu.taches_demandees, TACHE_DU_WEBHOOK_D_ADHESION) == [
        (adhesion_en_cours.pk,),
        (adhesion_en_cours.pk,),
    ]


def test_facture_de_l_adhesion_caisse_part_au_bon_destinataire(
    lieu, django_capture_on_commit_callbacks, mailoutbox
):
    """
    Le caissier vend une adhésion en espèces. On EXÉCUTE la tâche de facture demandée par
    la caisse, avec ses vrais arguments (appel direct, pas `.delay`).
    Résultat : un mail part, à l'adresse de l'adhérente, avec le lien vers la facture de
    CETTE adhésion (BaseBillet/tasks.py `context_for_membership_email`, bouton
    « REQUEST RECEIPT »). Le mail est lu dans `mailoutbox` (pytest-django).
    / The invoice task requested by the register is RUN with its real arguments: one mail,
    to the member's address, with the link to THIS membership's invoice.
    """
    adherente = creer_utilisateur(prenom="Ada", nom="Lovelace")
    adhesion = creer_adhesion(prix="20.00")
    point_de_vente = creer_un_point_de_vente([adhesion.produit])
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    lieu.taches_demandees.clear()

    with django_capture_on_commit_callbacks(execute=True):
        vendre_l_adhesion_a_la_caisse(
            client_du_caissier,
            point_de_vente,
            adhesion,
            moyen_de_paiement="espece",
            autres_champs=champs_de_l_adherente(adherente),
        )

    demandes_de_facture = arguments_des_taches(
        lieu.taches_demandees, TACHE_DE_LA_FACTURE
    )
    assert len(demandes_de_facture) == 1
    arguments_de_la_facture = demandes_de_facture[0]

    # La tâche attend une seconde avant de relire l'adhésion : l'attente est simulée.
    # / The task waits one second before reading the membership: the wait is faked.
    with patch("BaseBillet.tasks.time.sleep"):
        send_membership_invoice_to_email(*arguments_de_la_facture)

    adhesion_vendue = Membership.objects.get(user=adherente, price=adhesion.tarif)
    assert len(mailoutbox) == 1
    mail_de_la_facture = mailoutbox[0]
    assert mail_de_la_facture.to == [adherente.email]
    contenu_html_du_mail = mail_de_la_facture.alternatives[0][0]
    assert f"/memberships/{adhesion_vendue.pk}/invoice/" in contenu_html_du_mail


def test_adhesion_caisse_taches_demandees_apres_la_validation(
    lieu, django_capture_on_commit_callbacks
):
    """
    La caisse crée l'adhésion DANS la transaction du paiement. Tant que la transaction
    n'est pas validée en base, AUCUNE tâche Celery n'est demandée : le worker, qui a sa
    propre connexion, ne trouverait pas l'adhésion.
    On capture les actions « après validation » sans les exécuter : la liste des tâches
    demandées reste vide. On les exécute ensuite : la facture et la récompense sont
    demandées.
    / The register creates the membership INSIDE the payment transaction. No Celery task
    is requested before the commit. Captured on_commit callbacks are not run: no task.
    Once run: invoice and reward are requested.
    """
    adherente = creer_utilisateur(prenom="Ada", nom="Lovelace")
    adhesion = creer_adhesion(prix="20.00")
    point_de_vente = creer_un_point_de_vente([adhesion.produit])
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    lieu.taches_demandees.clear()

    # Les actions « après validation » sont capturées, PAS exécutées.
    # / on_commit callbacks are captured, NOT run.
    with django_capture_on_commit_callbacks() as actions_apres_la_validation:
        reponse = vendre_l_adhesion_a_la_caisse(
            client_du_caissier,
            point_de_vente,
            adhesion,
            moyen_de_paiement="espece",
            autres_champs=champs_de_l_adherente(adherente),
        )

    assert reponse.status_code == 200
    assert noms_des_taches(lieu.taches_demandees) == []

    # La validation en base a lieu : on exécute les actions capturées. Une action peut en
    # demander une autre « après validation » : la seconde capture l'exécute aussi.
    # / The commit happens: run the captured callbacks. A callback may register another
    # one: the second capture runs it too.
    with django_capture_on_commit_callbacks(execute=True):
        for action_apres_la_validation in actions_apres_la_validation:
            action_apres_la_validation()

    noms_des_taches_apres_la_validation = noms_des_taches(lieu.taches_demandees)
    assert TACHE_DE_LA_FACTURE in noms_des_taches_apres_la_validation
    assert TACHE_DE_LA_RECOMPENSE in noms_des_taches_apres_la_validation
