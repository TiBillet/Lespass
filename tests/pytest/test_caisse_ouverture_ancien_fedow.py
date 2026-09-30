"""
Tests de l'ouverture de la caisse : l'ancien Fedow dit si la carte primaire l'est encore.
/ Register opening tests: the old Fedow tells whether the primary card still is one.

LOCALISATION : tests/pytest/test_caisse_ouverture_ancien_fedow.py

RÈGLE MÉTIER TESTÉE (décision du mainteneur, 2026-09-30 : « comme LaBoutik V1 »)
L'ancien Fedow peut retirer une carte primaire sans prévenir la caisse (VOID de la carte,
carte déclarée perdue). À chaque ouverture de la caisse (`POST carte_primaire`), une fois
la carte primaire trouvée en local, la caisse lit la carte sur l'ancien Fedow
(`NFCcardFedow.retrieve`). L'ancien Fedow calcule `is_primary` pour le lieu qui signe la
requête. Donc :
1. `is_primary` vrai : la caisse s'ouvre comme avant, la carte primaire reste ;
2. `is_primary` faux : la caisse ne s'ouvre pas. La `CartePrimaire` locale est supprimée
   (en local seulement : l'ancien Fedow ne la connaît déjà plus comme primaire, aucun
   `set_primary`). Un avertissement est journalisé. L'écran dit que la carte n'est plus
   une carte primaire pour ce lieu, et qu'il faut prévenir un responsable ;
3. l'ancien Fedow ne répond pas, répond une erreur, répond quelque chose d'illisible, ou
   ne connaît pas la carte : la caisse ne s'ouvre pas, rien n'est supprimé, une erreur
   est journalisée avec sa cause. L'écran le dit, avec un message différent du point 2 ;
4. carte inconnue en local, ou carte non primaire en local : l'ancien Fedow n'est pas
   interrogé, message actuel ;
5. l'ancien Fedow reçoit le tag de la carte scannée, et aucun autre.
/ On each register opening, the old Fedow is asked whether the card is still primary.
Not primary: the local primary card is deleted (locally only) and the register stays
closed. Old Fedow unreachable, failing, unreadable or not knowing the card: the register
stays closed, nothing is deleted.

Référence V1 (lecture seule) : ../LaBoutik/webview/views.py (l.241-270).
Calcul de `is_primary` : ../Fedow/fedow_core/serializers.py (l.441-452, `CardSerializer`).
Fiche : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-B-caisse.md.

6. lieu NON relié à l'ancien Fedow (`can_fedow()` faux) : la caisse ne s'ouvre pas, rien
   n'est supprimé, une erreur est journalisée avec le tag, et le client `FedowAPI` n'est
   jamais créé (sa création lancerait `PlaceFedow.create_place()`, un appel réseau).
/ Venue not linked to the old Fedow: the register stays closed, nothing is deleted,
`FedowAPI` is never built.

L'ANCIEN FEDOW EST SIMULÉ, JAMAIS APPELÉ
Une garde (fixture automatique) fait échouer tout envoi réseau du client Fedow
(`fedow_connect.fedow_api._post` / `_get`). Deux niveaux de simulation :
- la caisse reçoit un faux `NFCcardFedow.retrieve` : il note chaque tag demandé, et rend
  la fiche de la carte (`is_primary` vrai ou faux), ou lève l'exception choisie ;
  `NFCcardFedow.set_primary` est remplacé par un faux qui note chaque appel ;
- le client lui-même (`NFCcardFedow.retrieve`) est testé contre un faux `_get` : il doit
  garder `is_primary` de la réponse, et refuser une réponse sans `is_primary`.
Le lieu est dit « relié » ou « non relié » par `FedowConfig.can_fedow`, simulé.

SIMULATIONS DE BASE
Chaque test est marqué `django_db` : la transaction est annulée à la fin (tests/PIEGES.md
13.1). La caisse est activée par `configuration_modifiee()`, jamais enregistrée
(tests/PIEGES.md 13.22). Le client de chaque test est créé dans le test (13.10).
Le point de vente de chaque test est VISIBLE (`hidden=False`) : l'ouverture de la caisse
ignore les points de vente cachés. Le rollback l'efface : aucun autre test ne le voit
(tests/PIEGES.md 9.41).

Lancer / Run : make test ARGS="tests/pytest/test_caisse_ouverture_ancien_fedow.py"
"""

import html
import json
import logging
import re
import uuid
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import requests
from django_tenants.utils import tenant_context

from fabriques_panier import configuration_modifiee, identifiant_unique
from fedow_connect.fedow_api import CarteInconnueDeFedow, FedowAPI, NFCcardFedow
from fedow_connect.models import FedowConfig
from laboutik.models import CartePrimaire, PointDeVente
from QrcodeCashless.models import CarteCashless
from test_caracterisation_en_ligne import creer_un_administrateur_du_lieu

pytestmark = pytest.mark.django_db

# Adresse de l'ouverture de la caisse (laboutik/views.py, CaisseViewSet.carte_primaire).
# / Register opening address.
URL_D_OUVERTURE_DE_LA_CAISSE = "/laboutik/caisse/carte_primaire/"

# Ce que l'écran dit quand l'ancien Fedow a retiré la carte primaire (point 2).
# / What the screen says when the old Fedow withdrew the primary card (point 2).
MESSAGE_CARTE_RETIREE = (
    "Cette carte n'est plus une carte primaire pour ce lieu. Prévenez un responsable."
)

# Début de ce que l'écran dit quand l'ancien Fedow ne peut pas confirmer la carte
# (point 3). / Start of what the screen says when the old Fedow cannot confirm the card.
DEBUT_DU_MESSAGE_VERIFICATION_IMPOSSIBLE = "Impossible de vérifier la carte primaire"

# Ce que l'écran dit quand le lieu n'est pas relié à l'ancien Fedow (point 6).
# / What the screen says when the venue is not linked to the old Fedow (point 6).
MESSAGE_LIEU_NON_RELIE = "Ce lieu n'est pas relié à Fedow : prévenez un responsable."


@pytest.fixture(autouse=True)
def _langue_par_defaut_apres_chaque_test():
    """Les vues activent une langue sans la remettre (tests/PIEGES.md, 10.5).
    / Views activate a language without resetting it."""
    from django.utils import translation

    yield
    translation.deactivate()


@pytest.fixture(autouse=True)
def aucun_appel_reseau_vers_l_ancien_fedow():
    """
    Garde : aucun test de ce fichier n'appelle le vrai ancien Fedow.
    Tout envoi réseau du client Fedow (`_post`, `_get`) échoue ici, et la liste des
    envois tentés doit être vide à la fin du test. Un test qui simule lui-même `_get`
    (les tests du client) remplace cette garde le temps de son bloc `with`.
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
        f"Envois réseau réels tentés vers l'ancien Fedow : {envois_reseau_tentes}"
    )


@pytest.fixture
def lieu(tenant):
    """
    Le lieu `lespass`, caisse activée, connexion posée sur son schéma pendant tout le test.
    La caisse n'est accessible que si le module caisse (et donc le module monnaie locale)
    est actif. On l'active EN MÉMOIRE : `configuration_modifiee()` ne sauve jamais la
    `Configuration`, dont le cache est partagé avec le serveur live.
    / The `lespass` venue, register switched on in memory only.
    """
    with tenant_context(tenant):
        with configuration_modifiee(module_caisse=True, module_monnaie_locale=True):
            yield SimpleNamespace(tenant=tenant)


# --------------------------------------------------------------------------
# Fabriques : la carte primaire du caissier, son point de vente, son client HTTP
# / Factories: the cashier's primary card, its point of sale, its HTTP client
# --------------------------------------------------------------------------


def creer_une_carte_nfc():
    """
    Une carte NFC. `tag_id` et `number` font 8 caractères hexadécimaux
    (tests/PIEGES.md 9.31), comme le demande l'ancien Fedow.
    / An NFC card, 8 hexadecimal characters.
    """
    identifiant_de_la_carte = identifiant_unique().upper()
    return CarteCashless.objects.create(
        tag_id=identifiant_de_la_carte,
        number=identifiant_de_la_carte,
        uuid=uuid.uuid4(),
    )


def preparer_la_caisse(lieu):
    """
    Une carte primaire en local, autorisée sur un point de vente visible, et le client
    HTTP d'un administrateur du lieu connecté, qui demande les écrans en français.
    / A local primary card allowed on a visible point of sale, and a logged-in venue
    admin client asking for French screens.
    """
    point_de_vente = PointDeVente.objects.create(
        name=f"TEST_ouverture_caisse {identifiant_unique()}",
        comportement=PointDeVente.DIRECT,
        service_direct=True,
        accepte_especes=True,
        hidden=False,
    )
    carte_du_caissier = creer_une_carte_nfc()
    carte_primaire = CartePrimaire.objects.create(
        carte=carte_du_caissier,
        edit_mode=False,
    )
    carte_primaire.points_de_vente.add(point_de_vente)

    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    client_du_caissier.defaults["HTTP_ACCEPT_LANGUAGE"] = "fr"
    return SimpleNamespace(
        point_de_vente=point_de_vente,
        carte_du_caissier=carte_du_caissier,
        carte_primaire=carte_primaire,
        client_du_caissier=client_du_caissier,
    )


def ouvrir_la_caisse(caisse, tag_id):
    """
    Le caissier pose une carte sur le lecteur de l'écran d'accueil de la caisse.
    / The cashier puts a card on the register's welcome-screen reader.
    """
    return caisse.client_du_caissier.post(
        URL_D_OUVERTURE_DE_LA_CAISSE,
        data={"tag_id": tag_id, "type_app": "desktop"},
    )


# --------------------------------------------------------------------------
# L'ancien Fedow, simulé
# / The old Fedow, faked
# --------------------------------------------------------------------------


def fiche_de_carte_de_l_ancien_fedow(tag_id, est_primaire):
    """
    La carte telle que l'ancien Fedow la décrit, données déjà validées par
    `CardValidator` (dont `is_primary`, calculé pour le lieu qui signe la requête).
    / The card as the old Fedow describes it (validated data, with `is_primary`).
    """
    return {
        "uuid": uuid.uuid4(),
        "qrcode_uuid": uuid.uuid4(),
        "first_tag_id": tag_id,
        "number_printed": tag_id,
        "is_wallet_ephemere": True,
        "is_primary": est_primaire,
        "wallet": {
            "uuid": uuid.uuid4(),
            "tokens": [],
            "get_name": "Portefeuille de la carte",
            "has_user_card": False,
        },
        "origin": {
            "place": {
                "uuid": uuid.uuid4(),
                "name": "Lieu",
                "wallet": uuid.uuid4(),
            },
            "generation": 1,
        },
    }


@contextmanager
def ancien_fedow_simule(est_primaire=True, erreur=None):
    """
    Le lieu est relié à l'ancien Fedow ; `NFCcardFedow.retrieve` et
    `NFCcardFedow.set_primary` sont simulés.
    / The venue is linked to the old Fedow; `retrieve` and `set_primary` are faked.

    - `est_primaire` : la valeur de `is_primary` rendue par l'ancien Fedow ;
    - `erreur` : une exception levée par `retrieve` à la place de la fiche (serveur
      injoignable, erreur HTTP, réponse illisible, `CarteInconnueDeFedow`).
    Rend `SimpleNamespace(tags_demandes, appels_a_set_primary)` :
    - `tags_demandes` : un tag par appel à `retrieve` ;
    - `appels_a_set_primary` : un `(tag_id, delete)` par appel à `set_primary`.
    """
    tags_demandes = []
    appels_a_set_primary = []

    def faux_retrieve(self, tag_id):
        tags_demandes.append(tag_id)
        if erreur is not None:
            raise erreur
        return fiche_de_carte_de_l_ancien_fedow(tag_id, est_primaire)

    def faux_set_primary(self, tag_id, delete=False):
        appels_a_set_primary.append((tag_id, delete))

    with patch.object(FedowConfig, "can_fedow", return_value=True):
        with patch.object(NFCcardFedow, "retrieve", new=faux_retrieve):
            with patch.object(NFCcardFedow, "set_primary", new=faux_set_primary):
                yield SimpleNamespace(
                    tags_demandes=tags_demandes,
                    appels_a_set_primary=appels_a_set_primary,
                )


# --------------------------------------------------------------------------
# Assistants de lecture
# / Reading helpers
# --------------------------------------------------------------------------


def la_caisse_s_ouvre(reponse):
    """Vrai si la réponse redirige vers un point de vente (en-tête `HX-Redirect`).
    / True when the response redirects to a point of sale."""
    adresse_de_redirection = reponse.get("HX-Redirect", "")
    return "point_de_vente" in adresse_de_redirection


def message_de_l_ecran(reponse):
    """
    Le texte du message d'erreur de l'écran d'accueil
    (`data-testid="caisse-carte-primaire-erreur"`), entités HTML décodées.
    / The welcome-screen error message text, HTML entities decoded.
    """
    contenu = reponse.content.decode()
    trouve = re.search(
        r'data-testid="caisse-carte-primaire-erreur"[^>]*>(.*?)</',
        contenu,
        re.DOTALL,
    )
    assert trouve is not None, f"Aucun message d'erreur à l'écran. Réponse : {contenu}"
    texte = html.unescape(trouve.group(1))
    return " ".join(texte.split())


def la_carte_primaire_existe_encore(caisse):
    """La carte primaire du caissier est-elle toujours en base ?
    / Is the cashier's primary card still in the database?"""
    return CartePrimaire.objects.filter(pk=caisse.carte_primaire.pk).exists()


def messages_journalises(caplog, niveau):
    """Les messages journalisés exactement à ce niveau.
    / The messages logged at exactly this level."""
    messages_trouves = []
    for enregistrement in caplog.records:
        if enregistrement.levelno == niveau:
            messages_trouves.append(enregistrement.getMessage())
    return messages_trouves


def verifier_le_message_de_verification_impossible(reponse):
    """
    L'écran dit que la carte n'a pas pu être vérifiée, et ne dit PAS qu'elle a été
    retirée : les deux situations ont deux messages différents.
    / The screen says the card could not be checked, and NOT that it was withdrawn.
    """
    message = message_de_l_ecran(reponse)
    assert message.startswith(DEBUT_DU_MESSAGE_VERIFICATION_IMPOSSIBLE), message
    assert message != MESSAGE_CARTE_RETIREE


# --------------------------------------------------------------------------
# 1 — L'ancien Fedow confirme la carte primaire
# / 1 — The old Fedow confirms the primary card
# --------------------------------------------------------------------------


def test_ouverture_carte_encore_primaire_pour_l_ancien_fedow_s_ouvre_comme_avant(lieu):
    """
    L'ancien Fedow répond `is_primary: true` : la caisse s'ouvre (redirection vers le
    point de vente), la carte primaire existe toujours, aucun `set_primary`.
    / Old Fedow says primary: the register opens, the primary card stays.
    """
    caisse = preparer_la_caisse(lieu)

    with ancien_fedow_simule(est_primaire=True) as faux_ancien_fedow:
        reponse = ouvrir_la_caisse(caisse, caisse.carte_du_caissier.tag_id)

    assert reponse.status_code == 200
    assert la_caisse_s_ouvre(reponse), reponse.content.decode()
    assert str(caisse.point_de_vente.uuid) in reponse["HX-Redirect"]
    assert la_carte_primaire_existe_encore(caisse)
    assert faux_ancien_fedow.appels_a_set_primary == []


# --------------------------------------------------------------------------
# 2 — L'ancien Fedow a retiré la carte primaire
# / 2 — The old Fedow withdrew the primary card
# --------------------------------------------------------------------------


def test_ouverture_carte_plus_primaire_pour_l_ancien_fedow_la_supprime_en_local(
    lieu, caplog
):
    """
    L'ancien Fedow répond `is_primary: false` : pas de redirection, l'écran dit que la
    carte n'est plus une carte primaire pour ce lieu (prévenir un responsable), la
    `CartePrimaire` locale n'existe plus, aucun `set_primary` (l'ancien Fedow l'a déjà
    retirée), un avertissement journalisé qui nomme la carte.
    La carte NFC elle-même reste : seule la carte primaire est supprimée.
    / Old Fedow says not primary: register closed, local primary card deleted, no
    `set_primary`, a warning logged. The NFC card itself stays.
    """
    caisse = preparer_la_caisse(lieu)
    tag_de_la_carte = caisse.carte_du_caissier.tag_id

    with ancien_fedow_simule(est_primaire=False) as faux_ancien_fedow:
        with caplog.at_level(logging.WARNING):
            reponse = ouvrir_la_caisse(caisse, tag_de_la_carte)

    assert reponse.status_code == 200
    assert not la_caisse_s_ouvre(reponse)

    assert message_de_l_ecran(reponse) == MESSAGE_CARTE_RETIREE

    assert not la_carte_primaire_existe_encore(caisse)
    assert CarteCashless.objects.filter(pk=caisse.carte_du_caissier.pk).exists()
    assert faux_ancien_fedow.appels_a_set_primary == []

    avertissements_sur_la_carte = []
    for message_journalise in messages_journalises(caplog, logging.WARNING):
        if tag_de_la_carte in message_journalise:
            avertissements_sur_la_carte.append(message_journalise)
    assert avertissements_sur_la_carte, (
        f"Aucun avertissement journalisé sur la carte {tag_de_la_carte}."
    )


# --------------------------------------------------------------------------
# 3 — L'ancien Fedow ne peut pas confirmer la carte
# / 3 — The old Fedow cannot confirm the card
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "erreur_de_l_ancien_fedow",
    [
        requests.ConnectionError("Ancien Fedow injoignable (simulé par le test)."),
        requests.Timeout("Ancien Fedow trop lent (simulé par le test)."),
        Exception("NFCcardFedow.retrieve ERRORS : 500 (simulé par le test)."),
        json.JSONDecodeError("Réponse illisible (simulé par le test)", "<html>", 0),
    ],
    ids=["injoignable", "delai_depasse", "erreur_http_500", "reponse_illisible"],
)
def test_ouverture_ancien_fedow_en_echec_refuse_sans_rien_supprimer(
    lieu, caplog, erreur_de_l_ancien_fedow
):
    """
    L'ancien Fedow ne répond pas, répond une erreur ou une réponse illisible : pas de
    redirection, l'écran dit que la carte n'a pas pu être vérifiée (message différent
    du point 2), la carte primaire existe toujours, une erreur journalisée qui nomme la
    carte et porte la cause réelle.
    / Old Fedow fails: register closed, nothing deleted, an error logged with the cause.
    """
    caisse = preparer_la_caisse(lieu)
    tag_de_la_carte = caisse.carte_du_caissier.tag_id

    with ancien_fedow_simule(erreur=erreur_de_l_ancien_fedow) as faux_ancien_fedow:
        with caplog.at_level(logging.WARNING):
            reponse = ouvrir_la_caisse(caisse, tag_de_la_carte)

    assert reponse.status_code == 200
    assert not la_caisse_s_ouvre(reponse)
    verifier_le_message_de_verification_impossible(reponse)
    assert la_carte_primaire_existe_encore(caisse)
    assert faux_ancien_fedow.appels_a_set_primary == []

    cause_de_l_echec = str(erreur_de_l_ancien_fedow)
    erreurs_avec_la_cause = []
    for message_journalise in messages_journalises(caplog, logging.ERROR):
        if (
            tag_de_la_carte in message_journalise
            and cause_de_l_echec in message_journalise
        ):
            erreurs_avec_la_cause.append(message_journalise)
    assert erreurs_avec_la_cause, (
        f"Aucune erreur journalisée avec la carte {tag_de_la_carte} "
        f"et la cause « {cause_de_l_echec} »."
    )


# --------------------------------------------------------------------------
# 4 — L'ancien Fedow ne connaît pas la carte
# / 4 — The old Fedow does not know the card
# --------------------------------------------------------------------------


def test_ouverture_carte_inconnue_de_l_ancien_fedow_refuse_sans_rien_supprimer(
    lieu, caplog
):
    """
    L'ancien Fedow répond 404 (`CarteInconnueDeFedow`) : comme une panne, pas de
    redirection, message « vérification impossible », rien n'est supprimé, une erreur
    journalisée qui nomme la carte et porte la cause.
    / Old Fedow does not know the card (404): same as a failure, nothing deleted.
    """
    caisse = preparer_la_caisse(lieu)
    tag_de_la_carte = caisse.carte_du_caissier.tag_id
    carte_inconnue = CarteInconnueDeFedow(
        f"Carte inconnue de Fedow : {tag_de_la_carte}"
    )

    with ancien_fedow_simule(erreur=carte_inconnue) as faux_ancien_fedow:
        with caplog.at_level(logging.WARNING):
            reponse = ouvrir_la_caisse(caisse, tag_de_la_carte)

    assert reponse.status_code == 200
    assert not la_caisse_s_ouvre(reponse)
    verifier_le_message_de_verification_impossible(reponse)
    assert la_carte_primaire_existe_encore(caisse)
    assert faux_ancien_fedow.appels_a_set_primary == []

    erreurs_sur_la_carte = []
    for message_journalise in messages_journalises(caplog, logging.ERROR):
        if tag_de_la_carte in message_journalise and "inconnue" in message_journalise:
            erreurs_sur_la_carte.append(message_journalise)
    assert erreurs_sur_la_carte, (
        f"Aucune erreur journalisée sur la carte inconnue {tag_de_la_carte}."
    )


# --------------------------------------------------------------------------
# 5 — Carte refusée en local : l'ancien Fedow n'est pas interrogé
# / 5 — Card refused locally: the old Fedow is not asked
# --------------------------------------------------------------------------


def test_ouverture_carte_inconnue_en_local_n_interroge_pas_l_ancien_fedow(lieu):
    """
    Carte absente de la base : message actuel « Carte inconnue », l'ancien Fedow n'est
    pas interrogé.
    / Card unknown locally: current message, old Fedow not asked.
    """
    caisse = preparer_la_caisse(lieu)
    tag_absent_de_la_base = identifiant_unique().upper()

    with ancien_fedow_simule(est_primaire=True) as faux_ancien_fedow:
        reponse = ouvrir_la_caisse(caisse, tag_absent_de_la_base)

    assert not la_caisse_s_ouvre(reponse)
    assert message_de_l_ecran(reponse) == "Carte inconnue"
    assert faux_ancien_fedow.tags_demandes == []


def test_ouverture_carte_non_primaire_en_local_n_interroge_pas_l_ancien_fedow(lieu):
    """
    Carte connue en base mais pas carte primaire : message actuel « Carte non
    primaire », l'ancien Fedow n'est pas interrogé.
    / Card known locally but not primary: current message, old Fedow not asked.
    """
    caisse = preparer_la_caisse(lieu)
    carte_d_un_client = creer_une_carte_nfc()

    with ancien_fedow_simule(est_primaire=True) as faux_ancien_fedow:
        reponse = ouvrir_la_caisse(caisse, carte_d_un_client.tag_id)

    assert not la_caisse_s_ouvre(reponse)
    assert message_de_l_ecran(reponse) == "Carte non primaire"
    assert faux_ancien_fedow.tags_demandes == []


# --------------------------------------------------------------------------
# 6 — L'ancien Fedow reçoit le tag de la carte scannée
# / 6 — The old Fedow receives the scanned card's tag
# --------------------------------------------------------------------------


def test_ouverture_l_ancien_fedow_recoit_le_tag_de_la_carte_scannee(lieu):
    """
    L'ancien Fedow est interrogé une fois, avec le tag de la carte scannée, et aucun
    autre. Une deuxième carte primaire existe dans le lieu : elle n'est pas demandée.
    / The old Fedow is asked once, with the scanned card's tag only.
    """
    caisse = preparer_la_caisse(lieu)
    autre_caisse = preparer_la_caisse(lieu)

    with ancien_fedow_simule(est_primaire=True) as faux_ancien_fedow:
        ouvrir_la_caisse(caisse, caisse.carte_du_caissier.tag_id)

    assert faux_ancien_fedow.tags_demandes == [caisse.carte_du_caissier.tag_id]
    assert autre_caisse.carte_du_caissier.tag_id not in faux_ancien_fedow.tags_demandes


# --------------------------------------------------------------------------
# 7 — Lieu non relié à l'ancien Fedow
# / 7 — Venue not linked to the old Fedow
# --------------------------------------------------------------------------


def test_ouverture_lieu_non_relie_a_l_ancien_fedow_refuse_sans_rien_supprimer(
    lieu, caplog
):
    """
    Lieu non relié à l'ancien Fedow (`can_fedow()` faux) : pas de redirection, l'écran
    dit que le lieu n'est pas relié à Fedow, la carte primaire existe toujours, une
    erreur journalisée qui nomme la carte. Le client `FedowAPI` n'est jamais créé (sa
    création lancerait `create_place`, un appel réseau), et la carte n'est pas lue.
    / Unlinked venue: register closed, nothing deleted, an error logged with the tag,
    `FedowAPI` never built, the card never read.
    """
    caisse = preparer_la_caisse(lieu)
    tag_de_la_carte = caisse.carte_du_caissier.tag_id
    construction_de_fedow_api = MagicMock(return_value=None)
    tags_demandes = []

    def faux_retrieve(self, tag_id):
        tags_demandes.append(tag_id)
        return fiche_de_carte_de_l_ancien_fedow(tag_id, est_primaire=True)

    with patch.object(FedowConfig, "can_fedow", return_value=False):
        with patch.object(FedowAPI, "__init__", construction_de_fedow_api):
            with patch.object(NFCcardFedow, "retrieve", new=faux_retrieve):
                with caplog.at_level(logging.WARNING):
                    reponse = ouvrir_la_caisse(caisse, tag_de_la_carte)

    assert reponse.status_code == 200
    assert not la_caisse_s_ouvre(reponse)
    assert message_de_l_ecran(reponse) == MESSAGE_LIEU_NON_RELIE
    assert la_carte_primaire_existe_encore(caisse)
    assert construction_de_fedow_api.call_count == 0
    assert tags_demandes == []

    erreurs_sur_la_carte = []
    for message_journalise in messages_journalises(caplog, logging.ERROR):
        if tag_de_la_carte in message_journalise:
            erreurs_sur_la_carte.append(message_journalise)
    assert erreurs_sur_la_carte, (
        f"Aucune erreur journalisée sur la carte {tag_de_la_carte}."
    )


# --------------------------------------------------------------------------
# Le client : `NFCcardFedow.retrieve` garde `is_primary`
# / The client: `NFCcardFedow.retrieve` keeps `is_primary`
# --------------------------------------------------------------------------


def reponse_json_de_l_ancien_fedow(tag_id, est_primaire):
    """
    Le corps JSON que l'ancien Fedow renvoie pour `GET card/<tag>/` (`CardSerializer`,
    ../Fedow/fedow_core/serializers.py l.441). `est_primaire=None` : sans `is_primary`.
    / The JSON body the old Fedow sends back. `None`: without `is_primary`.
    """
    corps = json.loads(
        json.dumps(fiche_de_carte_de_l_ancien_fedow(tag_id, est_primaire), default=str)
    )
    if est_primaire is None:
        del corps["is_primary"]
    return corps


@contextmanager
def lecture_reseau_simulee(corps_json):
    """
    Remplace l'envoi réseau `_get` du client Fedow : répond 200 avec `corps_json`, et
    note chaque chemin demandé.
    / Replaces the client's `_get`: answers 200 with the given body.
    """
    chemins_demandes = []

    def faux_get(*arguments, **arguments_nommes):
        chemins_demandes.append(arguments_nommes.get("path"))
        return SimpleNamespace(status_code=200, json=lambda: corps_json)

    with patch("fedow_connect.fedow_api._get", side_effect=faux_get):
        yield chemins_demandes


@pytest.mark.parametrize("est_primaire", [True, False])
def test_client_retrieve_garde_is_primary_de_l_ancien_fedow(lieu, est_primaire):
    """
    `NFCcardFedow.retrieve` rend `is_primary` tel que l'ancien Fedow l'a calculé.
    / `retrieve` returns `is_primary` as computed by the old Fedow.
    """
    tag_de_la_carte = identifiant_unique().upper()
    corps = reponse_json_de_l_ancien_fedow(tag_de_la_carte, est_primaire)

    with lecture_reseau_simulee(corps) as chemins_demandes:
        fiche = NFCcardFedow(fedow_config=MagicMock()).retrieve(tag_de_la_carte)

    assert chemins_demandes == [f"card/{tag_de_la_carte}"]
    assert fiche["is_primary"] is est_primaire


def test_client_retrieve_refuse_une_reponse_sans_is_primary(lieu):
    """
    L'ancien Fedow renvoie toujours `is_primary` : une réponse qui ne l'a pas est
    illisible, `retrieve` lève une exception (la caisse ne s'ouvre pas).
    / A response without `is_primary` is unreadable: `retrieve` raises.
    """
    tag_de_la_carte = identifiant_unique().upper()
    corps = reponse_json_de_l_ancien_fedow(tag_de_la_carte, est_primaire=None)

    with lecture_reseau_simulee(corps):
        with pytest.raises(Exception, match="is_primary"):
            NFCcardFedow(fedow_config=MagicMock()).retrieve(tag_de_la_carte)
