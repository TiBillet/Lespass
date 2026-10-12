"""
Rapatriement depuis l'ancien Fedow des cartes inconnues en local.
/ Fetching from the old Fedow the cards unknown locally.

LOCALISATION : tests/pytest/test_rapatriement_carte_fedow.py

Spec : TECH_DOC/SESSIONS/QRCODECASHLESS/CHANTIER-02-rapatriement-cartes-fedow.md (§ 8).
Les numéros des tests (« test 5 ») renvoient à la matrice du § 8 de la spec.

Ce qui est testé :
- le service `QrcodeCashless.services.trouver_ou_rapatrier_la_carte` (§ 8.2) ;
- le correctif du 404 de `NFCcardFedow.retrieve` et ses effets sur les autres
  appelants (§ 8.3).

PIÈGES (tests/PIEGES.md) :
- CarteCashless est en SHARED_APPS : pas de FastTenantTestCase (9.30).
- Le service lit connection.tenant : tenant_context (vrai Client), jamais
  schema_context (9.1).
- tag_id et number sont uniques en base : valeurs neuves à chaque test (11.10).
- L'ancien Fedow est simulé par `patch.object(NFCcardFedow, "retrieve")`. Une garde
  fait échouer tout appel réseau réel (`_get`, `_post`).

Lancer / Run : make test ARGS="tests/pytest/test_rapatriement_carte_fedow.py"
"""

import logging
import uuid
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import requests
from django_tenants.utils import tenant_context

from AuthBillet.models import Wallet
from Customers.models import Client
from fedow_connect.fedow_api import CarteInconnueDeFedow, NFCcardFedow
from fedow_connect.models import FedowConfig
from laboutik.models import CartePrimaire
from QrcodeCashless.models import CarteCashless, Detail
from QrcodeCashless.services import (
    CarteDUnLieuNonMigre,
    FedowInjoignable,
    trouver_ou_rapatrier_la_carte,
)

pytestmark = pytest.mark.django_db

# Uuid de la place Fedow du lieu courant, dans la configuration simulée.
# / Fedow place uuid of the current venue, in the faked configuration.
UUID_DE_LA_PLACE_DU_LIEU_COURANT = uuid.uuid4()


# --------------------------------------------------------------------------
# Gardes et contexte
# / Guards and context
# --------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def aucun_appel_reseau_vers_l_ancien_fedow():
    """
    Garde : aucun test de ce fichier n'appelle le vrai ancien Fedow. Tout envoi
    réseau du client Fedow (`_post`, `_get`) échoue, et la liste des envois tentés
    doit être vide à la fin. Les tests du correctif 404 simulent eux-mêmes `_get`
    dans un bloc `with`, qui remplace cette garde le temps du bloc.
    / Guard: no test calls the real old Fedow.
    """
    envois_reseau_tentes = []

    def envoi_reseau_interdit(*arguments, **arguments_nommes):
        envois_reseau_tentes.append((arguments, arguments_nommes))
        raise AssertionError(
            "Appel réseau réel vers l'ancien Fedow interdit dans un test pytest."
        )

    with patch("fedow_connect.fedow_api._post", side_effect=envoi_reseau_interdit):
        with patch("fedow_connect.fedow_api._get", side_effect=envoi_reseau_interdit):
            yield

    assert envois_reseau_tentes == [], (
        f"Envois réseau réels tentés : {envois_reseau_tentes}"
    )


@pytest.fixture
def lieu(tenant):
    """
    Le lieu `lespass`, connexion posée sur son schéma pendant tout le test.
    / The `lespass` venue, connection set on its schema for the whole test.
    """
    with tenant_context(tenant):
        yield tenant


@pytest.fixture
def autre_lieu(tenant):
    """
    Un autre lieu, qui a un domaine principal. Son moteur est posé par le test
    (`passer_le_lieu_en_moteur`) : la transaction du test l'annule à la fin.
    / Another venue with a primary domain. Its engine is set by the test.
    """
    for lieu_candidat in Client.objects.exclude(
        schema_name__in=["public", tenant.schema_name]
    ):
        if lieu_candidat.get_primary_domain() is not None:
            return lieu_candidat
    pytest.fail("Aucun autre lieu avec un domaine principal dans la base de dev.")


def passer_le_lieu_en_moteur(lieu_a_modifier, moteur):
    """Pose le moteur de monnaie d'un lieu (annulé par la transaction du test).
    / Sets a venue's currency engine (rolled back with the test)."""
    Client.objects.filter(pk=lieu_a_modifier.pk).update(moteur_monnaie=moteur)


def tag_neuf():
    """Un tag NFC neuf : 8 caractères hexadécimaux majuscules (PIEGES 11.10).
    / A fresh NFC tag: 8 uppercase hexadecimal characters."""
    return uuid.uuid4().hex[:8].upper()


def creer_une_carte_locale(tag_id=None, number=None, uuid_du_qrcode=None):
    """Une carte NFC déjà présente en local. / An NFC card already stored locally."""
    tag_id = tag_id or tag_neuf()
    return CarteCashless.objects.create(
        tag_id=tag_id,
        number=number or tag_neuf(),
        uuid=uuid_du_qrcode or uuid.uuid4(),
    )


# --------------------------------------------------------------------------
# L'ancien Fedow, simulé
# / The old Fedow, faked
# --------------------------------------------------------------------------


def fiche_de_l_ancien_fedow(
    tag_id,
    uuid_de_la_place=UUID_DE_LA_PLACE_DU_LIEU_COURANT,
    lespass_domain=None,
    generation=1,
    est_primaire=False,
    number=None,
    uuid_du_qrcode=None,
    uuid_du_portefeuille=None,
):
    """
    La carte telle que l'ancien Fedow la décrit : données déjà validées par
    `CardValidator`. Par défaut, une carte émise par le lieu courant.
    / The card as the old Fedow describes it. By default, issued by the current venue.
    """
    return {
        "uuid": uuid.uuid4(),
        "qrcode_uuid": uuid_du_qrcode or uuid.uuid4(),
        "first_tag_id": tag_id,
        "number_printed": number or tag_neuf(),
        "is_wallet_ephemere": True,
        "is_primary": est_primaire,
        "wallet": {"uuid": uuid_du_portefeuille or uuid.uuid4(), "tokens": []},
        "origin": {
            "place": {
                "uuid": uuid_de_la_place,
                "name": "Lieu d'origine",
                "wallet": uuid.uuid4(),
                "lespass_domain": lespass_domain,
            },
            "generation": generation,
        },
    }


@contextmanager
def ancien_fedow_simule(
    fiche=None, erreur=None, lieu_relie=True, avant_de_repondre=None
):
    """
    La configuration Fedow du lieu et `NFCcardFedow.retrieve` sont simulées.
    / The venue's Fedow configuration and `NFCcardFedow.retrieve` are faked.

    - `fiche` : ce que `retrieve` rend ;
    - `erreur` : une exception levée par `retrieve` à la place de la fiche ;
    - `lieu_relie` : la valeur de `can_fedow()` ;
    - `avant_de_repondre` : une fonction appelée par `retrieve` avant de rendre la
      fiche (pour simuler les miroirs écrits par le CardValidator, ou un second scan).
    Rend `SimpleNamespace(tags_demandes)` : un tag par appel à `retrieve`.
    """
    tags_demandes = []
    configuration_simulee = SimpleNamespace(
        fedow_place_uuid=UUID_DE_LA_PLACE_DU_LIEU_COURANT,
        can_fedow=lambda: lieu_relie,
    )

    def faux_retrieve(self, tag_id):
        tags_demandes.append(tag_id)
        if erreur is not None:
            raise erreur
        if avant_de_repondre is not None:
            avant_de_repondre()
        return fiche

    with patch.object(FedowConfig, "get_solo", return_value=configuration_simulee):
        with patch.object(NFCcardFedow, "retrieve", new=faux_retrieve):
            yield SimpleNamespace(tags_demandes=tags_demandes)


def messages_journalises(caplog, niveau):
    """Les messages journalisés exactement à ce niveau. / Messages logged at this level."""
    messages_trouves = []
    for enregistrement in caplog.records:
        if enregistrement.levelno == niveau:
            messages_trouves.append(enregistrement.getMessage())
    return messages_trouves


# --------------------------------------------------------------------------
# § 8.2 — Sans appel réseau : carte locale, tag invalide, lieu non relié
# / No network call: local card, invalid tag, unlinked venue
# --------------------------------------------------------------------------


def test_1_carte_presente_en_local_renvoyee_sans_interroger_fedow(lieu):
    carte_locale = creer_une_carte_locale()

    with ancien_fedow_simule() as fedow:
        carte_trouvee = trouver_ou_rapatrier_la_carte(carte_locale.tag_id)

    assert carte_trouvee.pk == carte_locale.pk
    assert fedow.tags_demandes == []


def test_2_tag_en_minuscules_avec_espaces_normalise_puis_trouve_en_local(lieu):
    carte_locale = creer_une_carte_locale()
    tag_tel_que_lu = f"  {carte_locale.tag_id.lower()} "

    with ancien_fedow_simule() as fedow:
        carte_trouvee = trouver_ou_rapatrier_la_carte(tag_tel_que_lu)

    assert carte_trouvee.pk == carte_locale.pk
    assert fedow.tags_demandes == []


@pytest.mark.parametrize("tag_invalide", ["", None, "ABC1234", "ABCDEF123", "XYZINCON"])
def test_3_tag_invalide_refuse_sans_appel_reseau(lieu, tag_invalide):
    with ancien_fedow_simule(fiche=fiche_de_l_ancien_fedow("ABCDEF12")) as fedow:
        with pytest.raises(CarteCashless.DoesNotExist):
            trouver_ou_rapatrier_la_carte(tag_invalide)

    assert fedow.tags_demandes == []


def test_3_bis_carte_locale_au_tag_non_hexadecimal_toujours_trouvee(lieu):
    # Des cartes de test ou de démo portent un tag non hexadécimal. La recherche
    # locale passe AVANT le contrôle du format : elles restent trouvées.
    # / Local cards with a non-hex tag are still found (lookup before format check).
    tag_non_hexadecimal = f"XY{tag_neuf()[:6]}"
    carte_locale = creer_une_carte_locale(tag_id=tag_non_hexadecimal)

    with ancien_fedow_simule() as fedow:
        carte_trouvee = trouver_ou_rapatrier_la_carte(tag_non_hexadecimal)

    assert carte_trouvee.pk == carte_locale.pk
    assert fedow.tags_demandes == []


def test_4_lieu_non_relie_a_fedow_carte_inconnue_sans_appel_reseau(lieu):
    tag_id = tag_neuf()

    with ancien_fedow_simule(
        fiche=fiche_de_l_ancien_fedow(tag_id), lieu_relie=False
    ) as fedow:
        with pytest.raises(CarteCashless.DoesNotExist):
            trouver_ou_rapatrier_la_carte(tag_id)

    assert fedow.tags_demandes == []
    assert not CarteCashless.objects.filter(tag_id=tag_id).exists()


# --------------------------------------------------------------------------
# § 8.2 — Réponses de Fedow : inconnue, panne, fiche illisible
# / Fedow answers: unknown, outage, unreadable record
# --------------------------------------------------------------------------


def test_5_carte_inconnue_de_fedow_leve_does_not_exist_sans_ecriture(lieu):
    tag_id = tag_neuf()

    with ancien_fedow_simule(erreur=CarteInconnueDeFedow("404")) as fedow:
        with pytest.raises(CarteCashless.DoesNotExist):
            trouver_ou_rapatrier_la_carte(tag_id)

    assert fedow.tags_demandes == [tag_id]
    assert not CarteCashless.objects.filter(tag_id=tag_id).exists()


@pytest.mark.parametrize(
    "panne_de_fedow",
    [
        requests.exceptions.ConnectionError("connexion refusée"),
        requests.exceptions.Timeout("trop lent"),
        Exception("NFCcardFedow.retrieve ERRORS : 502"),
    ],
)
def test_6_fedow_en_panne_leve_fedow_injoignable_sans_ecriture(lieu, panne_de_fedow):
    tag_id = tag_neuf()

    with ancien_fedow_simule(erreur=panne_de_fedow):
        with pytest.raises(FedowInjoignable):
            trouver_ou_rapatrier_la_carte(tag_id)

    assert not CarteCashless.objects.filter(tag_id=tag_id).exists()


def test_7_fiche_fedow_illisible_leve_fedow_injoignable(lieu):
    tag_id = tag_neuf()
    erreurs_du_validateur = {
        "first_tag_id": ["Ensure this field has at least 8 characters."]
    }

    with ancien_fedow_simule(erreur=Exception(erreurs_du_validateur)):
        with pytest.raises(FedowInjoignable):
            trouver_ou_rapatrier_la_carte(tag_id)

    assert not CarteCashless.objects.filter(tag_id=tag_id).exists()


# --------------------------------------------------------------------------
# § 8.2 — Carte du lieu courant
# / Card of the current venue
# --------------------------------------------------------------------------


def test_8_carte_du_lieu_courant_creee_avec_les_identifiants_fedow_et_le_detail_existant(
    lieu,
):
    tag_id = tag_neuf()
    detail_existant = Detail.objects.create(origine=lieu, generation=7)
    fiche = fiche_de_l_ancien_fedow(tag_id, generation=7)

    with ancien_fedow_simule(fiche=fiche):
        carte_rapatriee = trouver_ou_rapatrier_la_carte(tag_id)

    carte_relue = CarteCashless.objects.get(pk=carte_rapatriee.pk)
    assert carte_relue.tag_id == tag_id
    assert carte_relue.number == fiche["number_printed"]
    assert carte_relue.uuid == fiche["qrcode_uuid"]
    assert carte_relue.detail_id == detail_existant.pk
    assert Detail.objects.filter(origine=lieu, generation=7).count() == 1


def test_9_carte_du_lieu_courant_sans_detail_de_cette_generation_cree_le_detail(lieu):
    tag_id = tag_neuf()
    generation_inedite = 31000
    assert not Detail.objects.filter(
        origine=lieu, generation=generation_inedite
    ).exists()

    with ancien_fedow_simule(
        fiche=fiche_de_l_ancien_fedow(tag_id, generation=generation_inedite)
    ):
        carte_rapatriee = trouver_ou_rapatrier_la_carte(tag_id)

    detail_cree = carte_rapatriee.detail
    assert detail_cree.origine_id == lieu.pk
    assert detail_cree.generation == generation_inedite
    domaine_du_lieu = lieu.get_primary_domain()
    assert detail_cree.base_url == f"https://{domaine_du_lieu.domain}/qr/"


def test_10_plusieurs_details_de_la_meme_generation_prend_le_premier_par_pk(lieu):
    tag_id = tag_neuf()
    premier_detail = Detail.objects.create(origine=lieu, generation=31001)
    Detail.objects.create(origine=lieu, generation=31001)

    with ancien_fedow_simule(fiche=fiche_de_l_ancien_fedow(tag_id, generation=31001)):
        carte_rapatriee = trouver_ou_rapatrier_la_carte(tag_id)

    assert carte_rapatriee.detail_id == premier_detail.pk


# --------------------------------------------------------------------------
# § 8.2 — Carte d'un autre lieu (décision D1)
# / Card of another venue (decision D1)
# --------------------------------------------------------------------------


def test_11_carte_d_un_autre_lieu_v2_rattachee_a_son_detail_existant(lieu, autre_lieu):
    passer_le_lieu_en_moteur(autre_lieu, Client.MOTEUR_V2)
    detail_de_l_autre_lieu = Detail.objects.create(origine=autre_lieu, generation=31002)
    tag_id = tag_neuf()
    fiche = fiche_de_l_ancien_fedow(
        tag_id,
        uuid_de_la_place=uuid.uuid4(),
        lespass_domain=autre_lieu.get_primary_domain().domain,
        generation=31002,
    )

    with ancien_fedow_simule(fiche=fiche):
        carte_rapatriee = trouver_ou_rapatrier_la_carte(tag_id)

    assert carte_rapatriee.detail_id == detail_de_l_autre_lieu.pk
    assert Detail.objects.filter(origine=autre_lieu, generation=31002).count() == 1


def test_12_carte_d_un_autre_lieu_v2_sans_detail_cree_le_detail_de_ce_lieu(
    lieu, autre_lieu
):
    passer_le_lieu_en_moteur(autre_lieu, Client.MOTEUR_V2)
    tag_id = tag_neuf()
    fiche = fiche_de_l_ancien_fedow(
        tag_id,
        uuid_de_la_place=uuid.uuid4(),
        lespass_domain=autre_lieu.get_primary_domain().domain,
        generation=31003,
    )

    with ancien_fedow_simule(fiche=fiche):
        carte_rapatriee = trouver_ou_rapatrier_la_carte(tag_id)

    assert carte_rapatriee.detail.origine_id == autre_lieu.pk
    assert carte_rapatriee.detail.generation == 31003
    assert not Detail.objects.filter(origine=lieu, generation=31003).exists()


def test_13_carte_d_un_lieu_legacy_refusee_sans_carte_ni_detail(lieu, autre_lieu):
    passer_le_lieu_en_moteur(autre_lieu, Client.MOTEUR_LEGACY)
    tag_id = tag_neuf()
    fiche = fiche_de_l_ancien_fedow(
        tag_id,
        uuid_de_la_place=uuid.uuid4(),
        lespass_domain=autre_lieu.get_primary_domain().domain,
        generation=31004,
    )

    with ancien_fedow_simule(fiche=fiche):
        with pytest.raises(CarteDUnLieuNonMigre):
            trouver_ou_rapatrier_la_carte(tag_id)

    assert not CarteCashless.objects.filter(tag_id=tag_id).exists()
    assert not Detail.objects.filter(generation=31004).exists()


def test_14_carte_sans_lespass_domain_refusee_sans_ecriture(lieu):
    tag_id = tag_neuf()
    fiche = fiche_de_l_ancien_fedow(
        tag_id, uuid_de_la_place=uuid.uuid4(), lespass_domain=None
    )
    nombre_de_details_avant = Detail.objects.count()

    with ancien_fedow_simule(fiche=fiche):
        with pytest.raises(CarteDUnLieuNonMigre):
            trouver_ou_rapatrier_la_carte(tag_id)

    assert not CarteCashless.objects.filter(tag_id=tag_id).exists()
    assert Detail.objects.count() == nombre_de_details_avant


def test_15_carte_avec_un_lespass_domain_inconnu_refusee_sans_ecriture(lieu):
    tag_id = tag_neuf()
    fiche = fiche_de_l_ancien_fedow(
        tag_id,
        uuid_de_la_place=uuid.uuid4(),
        lespass_domain=f"lieu-disparu-{tag_id.lower()}.tibillet.localhost",
    )
    nombre_de_details_avant = Detail.objects.count()

    with ancien_fedow_simule(fiche=fiche):
        with pytest.raises(CarteDUnLieuNonMigre):
            trouver_ou_rapatrier_la_carte(tag_id)

    assert not CarteCashless.objects.filter(tag_id=tag_id).exists()
    assert Detail.objects.count() == nombre_de_details_avant


def test_16_refus_legacy_ne_rattache_aucune_carte_au_lieu_legacy(lieu, autre_lieu):
    # La raison 6 du verrou de moteur (Customers/bascule_vers_v2.py) lit
    # exactement Detail.objects.filter(origine=lieu).exists().
    # / Reason 6 of the engine lock reads exactly this.
    passer_le_lieu_en_moteur(autre_lieu, Client.MOTEUR_LEGACY)
    nombre_de_details_du_lieu_legacy_avant = Detail.objects.filter(
        origine=autre_lieu
    ).count()
    tag_id = tag_neuf()
    fiche = fiche_de_l_ancien_fedow(
        tag_id,
        uuid_de_la_place=uuid.uuid4(),
        lespass_domain=autre_lieu.get_primary_domain().domain,
    )

    with ancien_fedow_simule(fiche=fiche):
        with pytest.raises(CarteDUnLieuNonMigre):
            trouver_ou_rapatrier_la_carte(tag_id)

    nombre_de_details_du_lieu_legacy_apres = Detail.objects.filter(
        origine=autre_lieu
    ).count()
    assert (
        nombre_de_details_du_lieu_legacy_apres == nombre_de_details_du_lieu_legacy_avant
    )


# --------------------------------------------------------------------------
# § 8.2 — Second scan, portefeuille, utilisateur
# / Second scan, wallet, user
# --------------------------------------------------------------------------


def test_17_second_scan_du_meme_tag_ne_demande_fedow_qu_une_fois(lieu):
    tag_id = tag_neuf()

    with ancien_fedow_simule(fiche=fiche_de_l_ancien_fedow(tag_id)) as fedow:
        premiere_carte = trouver_ou_rapatrier_la_carte(tag_id)
        seconde_carte = trouver_ou_rapatrier_la_carte(tag_id)

    assert premiere_carte.pk == seconde_carte.pk
    assert fedow.tags_demandes == [tag_id]


def test_18_portefeuille_miroir_sans_origine_recoit_le_lieu_courant(lieu):
    tag_id = tag_neuf()
    uuid_du_portefeuille = uuid.uuid4()

    def miroir_du_portefeuille_ecrit_par_le_card_validator():
        Wallet.objects.create(uuid=uuid_du_portefeuille, origin=None)

    fiche = fiche_de_l_ancien_fedow(tag_id, uuid_du_portefeuille=uuid_du_portefeuille)
    with ancien_fedow_simule(
        fiche=fiche,
        avant_de_repondre=miroir_du_portefeuille_ecrit_par_le_card_validator,
    ):
        trouver_ou_rapatrier_la_carte(tag_id)

    assert Wallet.objects.get(uuid=uuid_du_portefeuille).origin_id == lieu.pk


def test_19_portefeuille_miroir_qui_a_deja_une_origine_n_est_pas_modifie(
    lieu, autre_lieu
):
    tag_id = tag_neuf()
    uuid_du_portefeuille = uuid.uuid4()

    def miroir_du_portefeuille_deja_rattache():
        Wallet.objects.create(uuid=uuid_du_portefeuille, origin=autre_lieu)

    fiche = fiche_de_l_ancien_fedow(tag_id, uuid_du_portefeuille=uuid_du_portefeuille)
    with ancien_fedow_simule(
        fiche=fiche, avant_de_repondre=miroir_du_portefeuille_deja_rattache
    ):
        trouver_ou_rapatrier_la_carte(tag_id)

    assert Wallet.objects.get(uuid=uuid_du_portefeuille).origin_id == autre_lieu.pk


def test_20_carte_rapatriee_sans_utilisateur_ni_portefeuille_ephemere(lieu):
    tag_id = tag_neuf()

    with ancien_fedow_simule(fiche=fiche_de_l_ancien_fedow(tag_id)):
        carte_rapatriee = trouver_ou_rapatrier_la_carte(tag_id)

    carte_relue = CarteCashless.objects.get(pk=carte_rapatriee.pk)
    assert carte_relue.user_id is None
    assert carte_relue.wallet_ephemere_id is None


# --------------------------------------------------------------------------
# § 8.2 — Concurrence et collisions (savepoint)
# / Concurrency and collisions (savepoint)
# --------------------------------------------------------------------------


def test_21_double_scan_simultane_renvoie_la_carte_creee_entre_temps(lieu):
    tag_id = tag_neuf()
    fiche = fiche_de_l_ancien_fedow(tag_id)
    cartes_creees_par_l_autre_scan = []

    def l_autre_scan_cree_la_carte_pendant_la_lecture():
        cartes_creees_par_l_autre_scan.append(creer_une_carte_locale(tag_id=tag_id))

    with ancien_fedow_simule(
        fiche=fiche, avant_de_repondre=l_autre_scan_cree_la_carte_pendant_la_lecture
    ):
        carte_renvoyee = trouver_ou_rapatrier_la_carte(tag_id)

    assert carte_renvoyee.pk == cartes_creees_par_l_autre_scan[0].pk
    assert CarteCashless.objects.filter(tag_id=tag_id).count() == 1


def test_22_collision_de_numero_avec_une_autre_carte_locale(lieu, caplog):
    autre_carte = creer_une_carte_locale()
    tag_id = tag_neuf()
    fiche = fiche_de_l_ancien_fedow(tag_id, number=autre_carte.number)

    with caplog.at_level(logging.ERROR, logger="QrcodeCashless.services"):
        with ancien_fedow_simule(fiche=fiche):
            with pytest.raises(CarteCashless.DoesNotExist):
                trouver_ou_rapatrier_la_carte(tag_id)

    assert not CarteCashless.objects.filter(tag_id=tag_id).exists()
    autre_carte_relue = CarteCashless.objects.get(pk=autre_carte.pk)
    assert autre_carte_relue.tag_id == autre_carte.tag_id
    assert any(
        "collision" in message
        for message in messages_journalises(caplog, logging.ERROR)
    )


def test_23_collision_d_uuid_ne_casse_pas_la_transaction_englobante(lieu, caplog):
    # Le test tourne déjà dans un atomic (django_db) : si le savepoint manquait,
    # la requête ORM d'après lèverait « current transaction is aborted ».
    # / The test already runs inside an atomic block (django_db).
    autre_carte = creer_une_carte_locale()
    tag_id = tag_neuf()
    fiche = fiche_de_l_ancien_fedow(tag_id, uuid_du_qrcode=autre_carte.uuid)

    with caplog.at_level(logging.ERROR, logger="QrcodeCashless.services"):
        with ancien_fedow_simule(fiche=fiche):
            with pytest.raises(CarteCashless.DoesNotExist):
                trouver_ou_rapatrier_la_carte(tag_id)

    assert CarteCashless.objects.filter(pk=autre_carte.pk).exists()
    assert not CarteCashless.objects.filter(tag_id=tag_id).exists()
    assert any(
        "collision" in message
        for message in messages_journalises(caplog, logging.ERROR)
    )


def test_24_carte_primaire_chez_fedow_journalisee_sans_creer_de_carte_primaire(
    lieu, caplog
):
    tag_id = tag_neuf()

    with caplog.at_level(logging.INFO, logger="QrcodeCashless.services"):
        with ancien_fedow_simule(
            fiche=fiche_de_l_ancien_fedow(tag_id, est_primaire=True)
        ):
            carte_rapatriee = trouver_ou_rapatrier_la_carte(tag_id)

    assert not CartePrimaire.objects.filter(carte=carte_rapatriee).exists()
    messages_info = messages_journalises(caplog, logging.INFO)
    assert any("carte primaire chez Fedow" in message for message in messages_info)


# --------------------------------------------------------------------------
# § 8.3 — Correctif du 404 de NFCcardFedow.retrieve
# / Fix of NFCcardFedow.retrieve's 404
# --------------------------------------------------------------------------


def reponse_http_simulee(status_code, type_de_contenu):
    """Une réponse HTTP minimale, comme celle de `requests`. / A minimal HTTP response."""
    return SimpleNamespace(
        status_code=status_code,
        headers={"Content-Type": type_de_contenu},
        text="Carte inconnue",
    )


def configuration_fedow_reliee():
    """Une configuration Fedow reliée, sans aucune clé réelle (`_get` est simulé).
    / A linked Fedow configuration, no real key (`_get` is faked)."""
    return SimpleNamespace(
        fedow_place_uuid=UUID_DE_LA_PLACE_DU_LIEU_COURANT,
        can_fedow=lambda: True,
    )


def test_25_404_json_de_fedow_veut_dire_carte_inconnue(lieu):
    with patch(
        "fedow_connect.fedow_api._get",
        return_value=reponse_http_simulee(404, "application/json"),
    ):
        with pytest.raises(CarteInconnueDeFedow):
            NFCcardFedow(configuration_fedow_reliee()).retrieve(tag_neuf())


@pytest.mark.parametrize(
    "type_de_contenu", ["text/plain; charset=utf-8", "text/html", ""]
)
def test_26_404_hors_json_du_proxy_est_une_panne_pas_une_carte_inconnue(
    lieu, type_de_contenu
):
    with patch(
        "fedow_connect.fedow_api._get",
        return_value=reponse_http_simulee(404, type_de_contenu),
    ):
        with pytest.raises(Exception) as erreur_levee:
            NFCcardFedow(configuration_fedow_reliee()).retrieve(tag_neuf())

    assert not isinstance(erreur_levee.value, CarteInconnueDeFedow)


def test_27_admin_des_cartes_nfc_dit_fedow_injoignable_sur_un_404_du_proxy(lieu):
    from django import forms

    from QrcodeCashless.admin import _creer_ou_recuperer_la_carte_chez_fedow

    detail = Detail.objects.create(origine=lieu, generation=31005)
    tag_id = tag_neuf()

    with patch.object(FedowConfig, "can_fedow", return_value=True):
        with patch(
            "fedow_connect.fedow_api._get",
            return_value=reponse_http_simulee(404, "text/html"),
        ):
            with pytest.raises(forms.ValidationError) as erreur_levee:
                _creer_ou_recuperer_la_carte_chez_fedow(
                    tag_id, tag_id, uuid.uuid4(), detail
                )

    assert erreur_levee.value.code == "fedow_injoignable"


def test_28_vidage_ancien_fedow_echoue_sur_un_404_du_proxy_au_lieu_de_rien_vider(lieu):
    from laboutik.views import _vider_la_carte_sur_l_ancien_fedow

    carte_client = creer_une_carte_locale()

    with patch.object(FedowConfig, "can_fedow", return_value=True):
        with patch(
            "fedow_connect.fedow_api._get",
            return_value=reponse_http_simulee(404, "text/html"),
        ):
            with pytest.raises(Exception) as erreur_levee:
                _vider_la_carte_sur_l_ancien_fedow(carte_client, tag_neuf(), False)

    assert not isinstance(erreur_levee.value, CarteInconnueDeFedow)
