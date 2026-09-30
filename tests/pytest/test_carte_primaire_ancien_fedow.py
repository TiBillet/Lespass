"""
Tests de la carte primaire déclarée à l'ancien Fedow.
/ Tests of the primary card declared to the old Fedow.

LOCALISATION : tests/pytest/test_carte_primaire_ancien_fedow.py

RÈGLE MÉTIER TESTÉE (décision du mainteneur, 2026-09-29 : « comme LaBoutik V1 »)
Le système est hybride : la MÊME carte primaire sert au Fedow local et à l'ancien Fedow.
L'ancien Fedow refuse un vidage signé par une carte qu'il ne connaît pas comme carte
primaire du lieu (« Primary card must be in place primary cards »). Donc :
1. créer une carte primaire la déclare à l'ancien Fedow (`POST card/set_primary`,
   `delete=False`), seulement si le lieu est relié à l'ancien Fedow ;
2. supprimer une carte primaire la retire de l'ancien Fedow (`delete=True`) ;
3. lieu non relié : aucun appel, le client `FedowAPI` n'est jamais créé ;
4. l'ancien Fedow refuse la déclaration : l'admin le voit en tête du formulaire (avec le
   code de la réponse), et rien n'est créé en local ;
5. carte déjà déclarée (réponse 208) : pas d'erreur ;
6. une commande de rattrapage déclare les cartes primaires déjà créées : `--a-blanc`
   (par défaut) liste sans rien appeler, `--appliquer` déclare chaque carte une fois.
/ The same primary card serves both Fedow servers. Creating one declares it to the old
Fedow, deleting one withdraws it, only when the venue is linked. A refusal is shown to
the admin and nothing is created locally. A catch-up command declares existing ones.

Référence V1 (lecture seule) : ../LaBoutik/APIcashless/signals.py (l.123-130),
../LaBoutik/fedow_connect/fedow_api.py (l.291, `NFCcard.set_primary`),
../Fedow/fedow_core/views.py (l.279, `CardAPI.set_primary`).
Fiche : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-B-caisse.md (§5, carte primaire).

LA FORME DU MÉCANISME (laboutik/carte_primaire_ancien_fedow.py)
- Des appels EXPLICITES, jamais un signal : le formulaire d'ajout de l'admin, la
  suppression de l'admin (unitaire et groupée), la commande `create_test_pos_data` et la
  commande de rattrapage. Une suppression par l'ORM (« vider et délier » à la caisse) ne
  rappelle pas l'ancien Fedow : son VOID a déjà retiré le lien lui-même.
- À l'ajout, la carte est d'abord lue sur l'ancien Fedow : une carte inconnue est
  refusée avec un message qui renvoie vers l'admin des cartes.
- La carte d'une carte primaire existante ne se change pas dans l'admin (lecture seule),
  et la modifier (mode gérant, points de vente) n'appelle pas l'ancien Fedow.
- Un retrait refusé par l'ancien Fedow garde la suppression locale et affiche un
  message d'erreur dans l'admin, avec le tag et le code.
- La commande de rattrapage `declarer_cartes_primaires_ancien_fedow` prend `--schema`,
  `--a-blanc` (par défaut) et `--appliquer`.
/ Explicit calls, never a signal. Unknown cards are refused at creation. The card is
read-only on change. A refused withdrawal keeps the local deletion and shows an error.

L'ANCIEN FEDOW EST SIMULÉ, JAMAIS APPELÉ
Une garde (fixture automatique) fait échouer tout envoi réseau du client Fedow
(`fedow_connect.fedow_api._post` / `_get`). Deux niveaux de simulation :
- le mécanisme reçoit un faux `NFCcardFedow.set_primary` qui note chaque appel
  (tag, delete) et répond comme le client : rien (200 / 205 / 208) ou une exception
  qui porte le code (400, 500) ;
- le client lui-même (`NFCcardFedow.set_primary`) est testé contre un faux envoi réseau
  (`_post` simulé) : route, corps, codes acceptés et refusés.
Le lieu est dit « relié » ou « non relié » par `FedowConfig.can_fedow`, simulé.

SIMULATIONS DE BASE
Chaque test est marqué `django_db` : la transaction est annulée à la fin
(tests/PIEGES.md 13.1). Les clients d'admin sont créés dans chaque test (13.10).

Lancer / Run : make test ARGS="tests/pytest/test_carte_primaire_ancien_fedow.py"
"""

import inspect
import uuid
from contextlib import contextmanager
from io import StringIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.conf import settings
from django.contrib import messages as django_messages
from django.core.management import call_command
from django.test import Client as ClientDeTestDjango
from django_tenants.utils import tenant_context

from AuthBillet.models import Wallet
from fabriques_panier import creer_utilisateur, identifiant_unique
from fedow_connect import fedow_api
from fedow_connect.fedow_api import CarteInconnueDeFedow, FedowAPI, NFCcardFedow
from fedow_connect.models import FedowConfig
from fedow_core.services import WalletService
from laboutik.models import CartePrimaire
from QrcodeCashless.models import CarteCashless, Detail
from test_caracterisation_en_ligne import creer_un_administrateur_du_lieu

pytestmark = pytest.mark.django_db

# Adresses de l'admin des cartes primaires (Administration/admin/laboutik.py).
# / Primary-card admin addresses.
URL_DE_LA_LISTE_DES_CARTES_PRIMAIRES = "/admin/laboutik/carteprimaire/"
URL_D_AJOUT_D_UNE_CARTE_PRIMAIRE = "/admin/laboutik/carteprimaire/add/"

# Nom proposé pour la commande de rattrapage (laboutik/management/commands/).
# / Proposed name of the catch-up command.
NOM_DE_LA_COMMANDE_DE_RATTRAPAGE = "declarer_cartes_primaires_ancien_fedow"

# La signature de l'envoi réseau du client Fedow, lue AVANT toute simulation : elle sert
# à relire les arguments d'un envoi simulé (chemin, données), par position ou par nom.
# / The Fedow client's network-send signature, read BEFORE any fake.
SIGNATURE_DE_L_ENVOI_A_FEDOW = inspect.signature(fedow_api._post)


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
    envois tentés doit être vide à la fin du test. Un test qui simule lui-même `_post`
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
    """Le lieu `lespass`, connexion posée sur son schéma pendant tout le test.
    / The `lespass` venue, connection set on its schema for the whole test."""
    with tenant_context(tenant):
        yield SimpleNamespace(tenant=tenant)


# --------------------------------------------------------------------------
# Fabriques : cartes du lieu, cartes primaires
# / Factories: venue cards, primary cards
# --------------------------------------------------------------------------


def creer_une_carte_du_lieu(lieu):
    """
    Une carte NFC émise par le lieu (`detail.origine`) : l'admin des cartes primaires ne
    propose que celles-là. `tag_id` et `number` font 8 caractères (tests/PIEGES.md 9.31).
    / An NFC card issued by the venue: the primary-card admin only offers those.
    """
    generation_de_cartes = Detail.objects.create(
        slug=f"test-carte-primaire-{identifiant_unique()}",
        base_url="test-carte-primaire.localhost",
        generation=1,
        origine=lieu.tenant,
    )
    identifiant_de_la_carte = identifiant_unique().upper()
    return CarteCashless.objects.create(
        tag_id=identifiant_de_la_carte,
        number=identifiant_de_la_carte,
        uuid=uuid.uuid4(),
        detail=generation_de_cartes,
    )


def creer_une_carte_primaire_en_base(lieu):
    """
    Une carte primaire écrite directement en base (sans passer par l'admin).
    / A primary card written straight to the database (not through the admin).
    """
    carte = creer_une_carte_du_lieu(lieu)
    return CartePrimaire.objects.create(carte=carte, edit_mode=False)


# --------------------------------------------------------------------------
# Simulations de l'ancien Fedow
# / Old Fedow fakes
# --------------------------------------------------------------------------


@contextmanager
def ancien_fedow_simule(reponse="acceptee"):
    """
    Le lieu est relié à l'ancien Fedow, et `NFCcardFedow.set_primary` est simulé.
    / The venue is linked to the old Fedow, and `set_primary` is faked.

    `reponse` :
    - "acceptee" : la déclaration ou le retrait passe (200 ou 205) ;
    - "refusee_400" / "refusee_500" : le client lève une exception qui porte le code ;
    - "carte_inconnue" : l'ancien Fedow ne connaît pas la carte. `retrieve` lève
      `CarteInconnueDeFedow` (404) ; `set_primary` lève une exception 500, comme le
      vrai serveur (`Card.objects.get` sans gestion d'absence).
    Rend la liste des appels à `set_primary` : un `(tag_id, delete)` par appel.
    / Returns the list of `set_primary` calls: one `(tag_id, delete)` per call.
    """
    appels_a_set_primary = []

    def faux_set_primary(self, tag_id, delete=False):
        appels_a_set_primary.append((tag_id, delete))
        if reponse == "refusee_400":
            raise Exception("card/set_primary refusé par l'ancien Fedow : 400")
        if reponse in ("refusee_500", "carte_inconnue"):
            raise Exception("card/set_primary refusé par l'ancien Fedow : 500")
        return None

    def faux_retrieve(self, tag_id):
        if reponse == "carte_inconnue":
            raise CarteInconnueDeFedow(f"Carte inconnue de Fedow : {tag_id}")
        return {"first_tag_id": tag_id, "is_primary": False}

    with patch.object(FedowConfig, "can_fedow", return_value=True):
        # `create=True` : la méthode `set_primary` n'existe pas encore dans le client.
        # / `create=True`: `set_primary` does not exist yet in the client.
        with patch.object(NFCcardFedow, "set_primary", new=faux_set_primary, create=True):
            with patch.object(NFCcardFedow, "retrieve", new=faux_retrieve):
                yield appels_a_set_primary


@contextmanager
def lieu_non_relie_a_l_ancien_fedow():
    """
    Le lieu n'est pas relié à l'ancien Fedow. Créer le client `FedowAPI` ou appeler
    `set_primary` est une faute : les deux sont notés.
    / The venue is not linked. Building `FedowAPI` or calling `set_primary` is recorded.
    Rend `(construction_de_fedow_api, appels_a_set_primary)`.
    """
    appels_a_set_primary = []

    def faux_set_primary(self, tag_id, delete=False):
        appels_a_set_primary.append((tag_id, delete))

    construction_de_fedow_api = MagicMock(return_value=None)
    with patch.object(FedowConfig, "can_fedow", return_value=False):
        with patch.object(FedowAPI, "__init__", construction_de_fedow_api):
            with patch.object(
                NFCcardFedow, "set_primary", new=faux_set_primary, create=True
            ):
                yield construction_de_fedow_api, appels_a_set_primary


def fausse_reponse_http(code):
    """Une réponse HTTP minimale, comme celle de `requests`.
    / A minimal HTTP response, like `requests`'."""
    return SimpleNamespace(
        status_code=code,
        content=b"",
        text="",
        json=lambda: {},
    )


@contextmanager
def envoi_reseau_simule(code_de_la_reponse):
    """
    Remplace l'envoi réseau `_post` du client Fedow : note chaque envoi (chemin,
    données) et répond `code_de_la_reponse`. Le lieu est relié.
    / Replaces the client's `_post`: records each send and answers the given code.
    Rend la liste des envois : un dict `{"path": …, "data": …}` par envoi.
    """
    envois = []

    def faux_post(*arguments, **arguments_nommes):
        arguments_lies = SIGNATURE_DE_L_ENVOI_A_FEDOW.bind(*arguments, **arguments_nommes)
        envois.append(
            {
                "path": arguments_lies.arguments.get("path"),
                "data": arguments_lies.arguments.get("data"),
            }
        )
        return fausse_reponse_http(code_de_la_reponse)

    with patch.object(FedowConfig, "can_fedow", return_value=True):
        with patch("fedow_connect.fedow_api._post", side_effect=faux_post):
            yield envois


# --------------------------------------------------------------------------
# Admin : ajout, modification, suppression
# / Admin: add, change, delete
# --------------------------------------------------------------------------


def ajouter_une_carte_primaire_par_l_admin(lieu, carte):
    """
    Poste le formulaire d'ajout de l'admin des cartes primaires, comme un gestionnaire.
    / Posts the primary-card admin add form, like a manager.
    """
    client_administrateur = creer_un_administrateur_du_lieu(lieu)
    return client_administrateur.post(
        URL_D_AJOUT_D_UNE_CARTE_PRIMAIRE,
        data={
            "carte": str(carte.pk),
            "edit_mode": "on",
            "points_de_vente": [],
        },
    )


def textes_des_erreurs_du_formulaire(reponse):
    """
    Les erreurs affichées dans le formulaire de l'admin, en un seul texte.
    / The errors shown in the admin form, as a single text.
    """
    assert reponse.status_code == 200, (
        f"Le formulaire devait être réaffiché avec une erreur (200), "
        f"reçu {reponse.status_code} : la carte primaire a été enregistrée."
    )
    formulaire = reponse.context["adminform"].form
    textes = []
    for liste_d_erreurs in formulaire.errors.values():
        for erreur in liste_d_erreurs:
            textes.append(str(erreur))
    return " ".join(textes)


def messages_d_erreur_affiches(reponse):
    """
    Les messages de niveau avertissement ou erreur rendus sur la page (texte seul).
    / Warning or error messages rendered on the page (text only).
    """
    textes = []
    for message in reponse.context["messages"]:
        if message.level >= django_messages.WARNING:
            textes.append(str(message))
    return textes


def test_ajout_par_l_admin_declare_la_carte_primaire_a_l_ancien_fedow(lieu):
    """
    Lieu relié : créer une carte primaire dans l'admin la déclare UNE fois à l'ancien
    Fedow, avec son tag et `delete=False`. La carte primaire est créée en local.
    / Linked venue: adding a primary card declares it once, with its tag, delete=False.
    """
    carte = creer_une_carte_du_lieu(lieu)

    with ancien_fedow_simule("acceptee") as appels_a_set_primary:
        reponse = ajouter_une_carte_primaire_par_l_admin(lieu, carte)

    assert reponse.status_code == 302, reponse.content.decode()[:800]
    assert CartePrimaire.objects.filter(carte=carte).exists()
    assert appels_a_set_primary == [(carte.tag_id, False)]


@pytest.mark.parametrize("reponse_de_l_ancien_fedow, code_attendu", [
    ("refusee_400", "400"),
    ("refusee_500", "500"),
])
def test_ajout_refuse_par_l_ancien_fedow_est_affiche_et_rien_n_est_cree(
    lieu, reponse_de_l_ancien_fedow, code_attendu
):
    """
    L'ancien Fedow refuse la déclaration : le formulaire est réaffiché avec une erreur
    qui donne le code de la réponse, et AUCUNE carte primaire n'est créée en local.
    Jamais une carte primaire acceptée ici et refusée là-bas sans que l'admin le sache.
    / Old Fedow refuses: the form shows an error with the code, nothing is created.
    """
    carte = creer_une_carte_du_lieu(lieu)

    with ancien_fedow_simule(reponse_de_l_ancien_fedow):
        reponse = ajouter_une_carte_primaire_par_l_admin(lieu, carte)

    texte_des_erreurs = textes_des_erreurs_du_formulaire(reponse)
    assert code_attendu in texte_des_erreurs, texte_des_erreurs
    assert not CartePrimaire.objects.filter(carte=carte).exists()


def test_ajout_d_une_carte_inconnue_de_l_ancien_fedow_est_refuse(lieu):
    """
    Carte inconnue de l'ancien Fedow : elle est lue d'abord (`retrieve` → 404), le
    formulaire est réaffiché avec une erreur, rien n'est créé en local, et `set_primary`
    n'est jamais appelé (le vrai serveur y répondrait une erreur 500 opaque).
    / Unknown card: read first, error shown, nothing created, `set_primary` never called.
    """
    carte = creer_une_carte_du_lieu(lieu)

    with ancien_fedow_simule("carte_inconnue") as appels_a_set_primary:
        reponse = ajouter_une_carte_primaire_par_l_admin(lieu, carte)

    texte_des_erreurs = textes_des_erreurs_du_formulaire(reponse)
    assert carte.tag_id in texte_des_erreurs, texte_des_erreurs
    assert not CartePrimaire.objects.filter(carte=carte).exists()
    assert appels_a_set_primary == []


def test_carte_inconnue_le_message_en_francais_renvoie_vers_l_admin_des_cartes(lieu):
    """
    Le message d'une carte inconnue de l'ancien Fedow, rendu en français, dit quoi
    faire : « créez-la d'abord dans l'admin des cartes ». Le navigateur demande le
    français (`Accept-Language: fr`).
    / The unknown-card message, rendered in French, says what to do.
    """
    carte = creer_une_carte_du_lieu(lieu)
    administrateur = creer_utilisateur(prenom="Admin", nom="Lieu")
    administrateur.client_admin.add(lieu.tenant)
    client_administrateur_en_francais = ClientDeTestDjango(
        HTTP_HOST="lespass.tibillet.localhost",
        HTTP_ACCEPT_LANGUAGE="fr",
    )
    client_administrateur_en_francais.force_login(administrateur)

    with ancien_fedow_simule("carte_inconnue"):
        reponse = client_administrateur_en_francais.post(
            URL_D_AJOUT_D_UNE_CARTE_PRIMAIRE,
            data={"carte": str(carte.pk), "edit_mode": "on", "points_de_vente": []},
        )

    texte_des_erreurs = textes_des_erreurs_du_formulaire(reponse)
    assert "créez-la d'abord dans l'admin des cartes" in texte_des_erreurs, (
        texte_des_erreurs
    )
    assert "créez-la d'abord dans l'admin des cartes" in reponse.content.decode().replace(
        "&#x27;", "'"
    )
    assert not CartePrimaire.objects.filter(carte=carte).exists()


def test_ajout_d_une_carte_deja_declaree_208_passe_sans_erreur(lieu):
    """
    Carte déjà déclarée sur l'ancien Fedow (réponse 208) : pas d'erreur, la carte
    primaire est créée. Ici le vrai client `set_primary` tourne, seul l'envoi réseau est
    simulé : un seul envoi, vers `card/set_primary`. La lecture préalable de la carte
    (`retrieve`) est simulée : la carte est connue.
    / Already declared (208): no error, created. Real client, faked network send.
    """
    carte = creer_une_carte_du_lieu(lieu)

    with envoi_reseau_simule(208) as envois:
        with patch.object(
            NFCcardFedow, "retrieve", return_value={"first_tag_id": carte.tag_id}
        ):
            reponse = ajouter_une_carte_primaire_par_l_admin(lieu, carte)

    assert reponse.status_code == 302, reponse.content.decode()[:800]
    assert CartePrimaire.objects.filter(carte=carte).exists()
    chemins_envoyes = [envoi["path"] for envoi in envois]
    assert chemins_envoyes == ["card/set_primary"]


def test_ajout_dans_un_lieu_non_relie_n_appelle_pas_l_ancien_fedow(lieu):
    """
    Lieu non relié à l'ancien Fedow : la carte primaire est créée en local, sans aucun
    appel ; le client `FedowAPI` n'est même pas créé.
    / Unlinked venue: created locally, no call, `FedowAPI` never built.
    """
    carte = creer_une_carte_du_lieu(lieu)

    with lieu_non_relie_a_l_ancien_fedow() as (construction_de_fedow_api, appels):
        reponse = ajouter_une_carte_primaire_par_l_admin(lieu, carte)

    assert reponse.status_code == 302, reponse.content.decode()[:800]
    assert CartePrimaire.objects.filter(carte=carte).exists()
    assert appels == []
    assert construction_de_fedow_api.call_count == 0


def test_modifier_le_mode_gerant_n_appelle_pas_l_ancien_fedow(lieu):
    """
    Modifier une carte primaire existante (mode gérant, points de vente) ne touche pas
    l'ancien Fedow : la carte déclarée ne change pas.
    / Editing an existing primary card (manager mode, points of sale) calls nothing.
    """
    carte_primaire = creer_une_carte_primaire_en_base(lieu)
    client_administrateur = creer_un_administrateur_du_lieu(lieu)

    with ancien_fedow_simule("acceptee") as appels_a_set_primary:
        reponse = client_administrateur.post(
            f"{URL_DE_LA_LISTE_DES_CARTES_PRIMAIRES}{carte_primaire.pk}/change/",
            data={
                "carte": str(carte_primaire.carte.pk),
                "edit_mode": "on",
                "points_de_vente": [],
            },
        )

    assert reponse.status_code == 302, reponse.content.decode()[:800]
    carte_primaire.refresh_from_db()
    assert carte_primaire.edit_mode is True
    assert appels_a_set_primary == []


def test_la_carte_d_une_carte_primaire_existante_ne_se_change_pas_dans_l_admin(lieu):
    """
    La carte NFC d'une carte primaire existante est en lecture seule dans l'admin :
    poster une autre carte ne la change pas, et l'ancien Fedow n'est pas appelé. Pour
    changer de carte, on supprime la carte primaire et on en crée une autre (chacune
    passe par la déclaration ou le retrait).
    / The NFC card of an existing primary card is read-only in the admin.
    """
    carte_primaire = creer_une_carte_primaire_en_base(lieu)
    carte_d_origine = carte_primaire.carte
    autre_carte = creer_une_carte_du_lieu(lieu)
    client_administrateur = creer_un_administrateur_du_lieu(lieu)

    with ancien_fedow_simule("acceptee") as appels_a_set_primary:
        client_administrateur.post(
            f"{URL_DE_LA_LISTE_DES_CARTES_PRIMAIRES}{carte_primaire.pk}/change/",
            data={
                "carte": str(autre_carte.pk),
                "edit_mode": "on",
                "points_de_vente": [],
            },
        )

    carte_primaire.refresh_from_db()
    assert carte_primaire.carte_id == carte_d_origine.pk
    assert appels_a_set_primary == []


def test_suppression_par_l_admin_retire_la_carte_primaire_de_l_ancien_fedow(lieu):
    """
    Lieu relié : supprimer une carte primaire dans l'admin la retire UNE fois de
    l'ancien Fedow (`delete=True`). La carte primaire disparaît en local.
    / Linked venue: deleting withdraws it once (delete=True), gone locally.
    """
    carte_primaire = creer_une_carte_primaire_en_base(lieu)
    tag_de_la_carte = carte_primaire.carte.tag_id
    client_administrateur = creer_un_administrateur_du_lieu(lieu)

    with ancien_fedow_simule("acceptee") as appels_a_set_primary:
        reponse = client_administrateur.post(
            f"{URL_DE_LA_LISTE_DES_CARTES_PRIMAIRES}{carte_primaire.pk}/delete/",
            data={"post": "yes"},
        )

    assert reponse.status_code == 302, reponse.content.decode()[:800]
    assert not CartePrimaire.objects.filter(pk=carte_primaire.pk).exists()
    assert appels_a_set_primary == [(tag_de_la_carte, True)]


def test_suppression_groupee_retire_chaque_carte_une_fois(lieu):
    """
    Suppression groupée (action « supprimer la sélection ») : chaque carte primaire est
    retirée une fois de l'ancien Fedow.
    / Bulk delete: each primary card is withdrawn once.
    """
    premiere_carte_primaire = creer_une_carte_primaire_en_base(lieu)
    seconde_carte_primaire = creer_une_carte_primaire_en_base(lieu)
    client_administrateur = creer_un_administrateur_du_lieu(lieu)

    with ancien_fedow_simule("acceptee") as appels_a_set_primary:
        reponse = client_administrateur.post(
            URL_DE_LA_LISTE_DES_CARTES_PRIMAIRES,
            data={
                "action": "delete_selected",
                "_selected_action": [
                    str(premiere_carte_primaire.pk),
                    str(seconde_carte_primaire.pk),
                ],
                "post": "yes",
            },
        )

    assert reponse.status_code == 302, reponse.content.decode()[:800]
    assert not CartePrimaire.objects.filter(
        pk__in=[premiere_carte_primaire.pk, seconde_carte_primaire.pk]
    ).exists()
    assert sorted(appels_a_set_primary) == sorted([
        (premiere_carte_primaire.carte.tag_id, True),
        (seconde_carte_primaire.carte.tag_id, True),
    ])


def test_retrait_refuse_par_l_ancien_fedow_est_affiche_dans_l_admin(lieu):
    """
    L'ancien Fedow refuse le retrait : la carte primaire est quand même supprimée en
    local (elle ne peut plus ouvrir la caisse), et la liste des cartes primaires affiche
    un message d'erreur qui nomme la carte et donne le code de la réponse.
    / Withdrawal refused: deleted locally anyway, an error message names the card and code.
    """
    carte_primaire = creer_une_carte_primaire_en_base(lieu)
    tag_de_la_carte = carte_primaire.carte.tag_id
    client_administrateur = creer_un_administrateur_du_lieu(lieu)

    with ancien_fedow_simule("refusee_400"):
        reponse = client_administrateur.post(
            f"{URL_DE_LA_LISTE_DES_CARTES_PRIMAIRES}{carte_primaire.pk}/delete/",
            data={"post": "yes"},
            follow=True,
        )

    assert reponse.status_code == 200
    assert not CartePrimaire.objects.filter(pk=carte_primaire.pk).exists()
    messages_d_erreur = messages_d_erreur_affiches(reponse)
    messages_qui_nomment_la_carte_et_le_code = []
    for texte in messages_d_erreur:
        if tag_de_la_carte in texte and "400" in texte:
            messages_qui_nomment_la_carte_et_le_code.append(texte)
    assert len(messages_qui_nomment_la_carte_et_le_code) == 1, messages_d_erreur
    assert tag_de_la_carte in reponse.content.decode()


def test_suppression_dans_un_lieu_non_relie_n_appelle_pas_l_ancien_fedow(lieu):
    """
    Lieu non relié : supprimer une carte primaire n'appelle rien ; le client
    `FedowAPI` n'est même pas créé.
    / Unlinked venue: deleting calls nothing, `FedowAPI` never built.
    """
    carte_primaire = creer_une_carte_primaire_en_base(lieu)
    client_administrateur = creer_un_administrateur_du_lieu(lieu)

    with lieu_non_relie_a_l_ancien_fedow() as (construction_de_fedow_api, appels):
        reponse = client_administrateur.post(
            f"{URL_DE_LA_LISTE_DES_CARTES_PRIMAIRES}{carte_primaire.pk}/delete/",
            data={"post": "yes"},
        )

    assert reponse.status_code == 302, reponse.content.decode()[:800]
    assert not CartePrimaire.objects.filter(pk=carte_primaire.pk).exists()
    assert appels == []
    assert construction_de_fedow_api.call_count == 0


# --------------------------------------------------------------------------
# « Vider et délier » une carte primaire à la caisse
# / "Empty and unlink" a primary card at the register
# --------------------------------------------------------------------------


def test_vider_et_delier_une_carte_primaire_ne_rappelle_pas_l_ancien_fedow(lieu):
    """
    « Vider et délier » (VOID) supprime la carte primaire en local
    (fedow_core/services.py, `rembourser_en_especes`). L'ancien Fedow a déjà retiré le
    lien primaire lui-même pendant son VOID (../Fedow/fedow_core/serializers.py,
    l.264-272). Aucun appel `set_primary` ne part, et surtout pas dans la transaction
    du vidage local : son échec annulerait le vidage local alors que l'ancien Fedow a
    déjà vidé la carte.
    / VOID deletes the primary card locally; the old Fedow already removed the link
    itself. No `set_primary` call, especially not inside the local emptying transaction.
    """
    carte_primaire_a_delier = creer_une_carte_primaire_en_base(lieu)
    carte_a_delier = carte_primaire_a_delier.carte
    carte_du_caissier = creer_une_carte_du_lieu(lieu)
    portefeuille_du_lieu = Wallet.objects.create(
        name=f"TEST_carte_primaire_ancien_fedow lieu {identifiant_unique()}",
        origin=lieu.tenant,
    )

    with ancien_fedow_simule("acceptee") as appels_a_set_primary:
        WalletService.rembourser_en_especes(
            carte=carte_a_delier,
            tenant=lieu.tenant,
            receiver_wallet=portefeuille_du_lieu,
            vider_carte=True,
            primary_card=carte_du_caissier,
            carte_videe_sur_l_ancien_fedow=True,
        )

    assert not CartePrimaire.objects.filter(carte=carte_a_delier).exists()
    assert appels_a_set_primary == []


# --------------------------------------------------------------------------
# Commandes : create_test_pos_data, rattrapage
# / Commands: create_test_pos_data, catch-up
# --------------------------------------------------------------------------


def test_create_test_pos_data_declare_la_carte_primaire_qu_il_cree(lieu):
    """
    `create_test_pos_data` (mode TEST) crée la carte primaire du simulateur
    (`DEMO_TAGID_CM`) si elle n'existe pas : il la déclare alors à l'ancien Fedow, une
    fois. La carte primaire de la base de dev est retirée DANS la transaction du test
    (annulée à la fin) pour que la commande la recrée.
    / The command creates the simulator primary card when absent, and declares it once.
    """
    assert settings.TEST, "create_test_pos_data ne crée les cartes qu'en mode TEST."
    tag_du_simulateur = settings.DEMO_TAGID_CM.upper().strip()
    CartePrimaire.objects.filter(carte__tag_id=tag_du_simulateur).delete()

    with ancien_fedow_simule("acceptee") as appels_a_set_primary:
        call_command("create_test_pos_data", schema=lieu.tenant.schema_name, stdout=StringIO())

    assert CartePrimaire.objects.filter(carte__tag_id=tag_du_simulateur).exists()
    assert appels_a_set_primary == [(tag_du_simulateur, False)]


def tags_des_cartes_primaires_du_lieu():
    """Les tags de toutes les cartes primaires du lieu courant, triés.
    / Tags of every primary card of the current venue, sorted."""
    tags = []
    for carte_primaire in CartePrimaire.objects.select_related("carte"):
        tags.append(carte_primaire.carte.tag_id)
    return sorted(tags)


def test_rattrapage_a_blanc_liste_les_cartes_sans_rien_appeler(lieu):
    """
    Commande de rattrapage sans option (`--a-blanc` par défaut) : elle liste les cartes
    primaires du lieu, et n'appelle rien (ni `set_primary`, ni création de `FedowAPI`).
    / Catch-up command, dry run by default: lists the cards, calls nothing.
    """
    premiere_carte_primaire = creer_une_carte_primaire_en_base(lieu)
    seconde_carte_primaire = creer_une_carte_primaire_en_base(lieu)
    sortie_de_la_commande = StringIO()

    construction_de_fedow_api = MagicMock(return_value=None)
    with ancien_fedow_simule("acceptee") as appels_a_set_primary:
        with patch.object(FedowAPI, "__init__", construction_de_fedow_api):
            call_command(
                NOM_DE_LA_COMMANDE_DE_RATTRAPAGE,
                schema=lieu.tenant.schema_name,
                stdout=sortie_de_la_commande,
            )

    texte_de_la_sortie = sortie_de_la_commande.getvalue()
    assert premiere_carte_primaire.carte.tag_id in texte_de_la_sortie
    assert seconde_carte_primaire.carte.tag_id in texte_de_la_sortie
    assert appels_a_set_primary == []
    assert construction_de_fedow_api.call_count == 0


def test_rattrapage_applique_declare_chaque_carte_primaire_une_fois(lieu):
    """
    `--appliquer` : chaque carte primaire du lieu est déclarée UNE fois à l'ancien
    Fedow, avec `delete=False`. Les cartes déjà déclarées répondent 208 : pas d'erreur
    (voir le test du client).
    / `--appliquer`: each primary card of the venue is declared once, delete=False.
    """
    creer_une_carte_primaire_en_base(lieu)
    creer_une_carte_primaire_en_base(lieu)
    tags_attendus = tags_des_cartes_primaires_du_lieu()

    with ancien_fedow_simule("acceptee") as appels_a_set_primary:
        call_command(
            NOM_DE_LA_COMMANDE_DE_RATTRAPAGE,
            schema=lieu.tenant.schema_name,
            appliquer=True,
            stdout=StringIO(),
        )

    tags_declares = sorted([tag for tag, _supprimer in appels_a_set_primary])
    assert tags_declares == tags_attendus
    for _tag, supprimer in appels_a_set_primary:
        assert supprimer is False


def test_rattrapage_dans_un_lieu_non_relie_ne_declare_rien_et_le_dit(lieu):
    """
    `--appliquer` dans un lieu non relié à l'ancien Fedow : aucun appel, le client
    `FedowAPI` n'est pas créé, et la sortie dit qu'il n'y a rien à déclarer.
    / Unlinked venue: no call, `FedowAPI` never built, the output says so.
    """
    creer_une_carte_primaire_en_base(lieu)
    sortie_de_la_commande = StringIO()

    with lieu_non_relie_a_l_ancien_fedow() as (construction_de_fedow_api, appels):
        call_command(
            NOM_DE_LA_COMMANDE_DE_RATTRAPAGE,
            schema=lieu.tenant.schema_name,
            appliquer=True,
            stdout=sortie_de_la_commande,
        )

    assert appels == []
    assert construction_de_fedow_api.call_count == 0
    assert "rien à déclarer" in sortie_de_la_commande.getvalue()


def test_rattrapage_applique_continue_apres_un_refus_et_le_signale(lieu):
    """
    `--appliquer` : un refus de l'ancien Fedow sur une carte n'arrête pas les autres.
    Chaque carte est tentée une fois, et la sortie nomme les cartes refusées.
    / A refusal on one card does not stop the others; refused cards are named.
    """
    carte_primaire_de_test = creer_une_carte_primaire_en_base(lieu)
    tags_attendus = tags_des_cartes_primaires_du_lieu()
    sortie_de_la_commande = StringIO()
    sortie_d_erreur_de_la_commande = StringIO()

    with ancien_fedow_simule("refusee_400") as appels_a_set_primary:
        call_command(
            NOM_DE_LA_COMMANDE_DE_RATTRAPAGE,
            schema=lieu.tenant.schema_name,
            appliquer=True,
            stdout=sortie_de_la_commande,
            stderr=sortie_d_erreur_de_la_commande,
        )

    tags_tentes = sorted([tag for tag, _supprimer in appels_a_set_primary])
    assert tags_tentes == tags_attendus
    texte_complet = (
        sortie_de_la_commande.getvalue() + sortie_d_erreur_de_la_commande.getvalue()
    )
    assert carte_primaire_de_test.carte.tag_id in texte_complet
    assert "400" in texte_complet


# --------------------------------------------------------------------------
# Le client `NFCcardFedow.set_primary` (envoi réseau simulé)
# / The `set_primary` client (faked network send)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("retirer, code_de_la_reponse", [
    (False, 200),
    (True, 205),
])
def test_client_set_primary_envoie_la_route_et_le_corps_de_v1(retirer, code_de_la_reponse):
    """
    Le client envoie `POST card/set_primary` avec `{"first_tag_id": …, "delete": …}`,
    comme LaBoutik V1. `delete` est un vrai booléen : l'ancien Fedow lit
    `request.data.get('delete')` tel quel, une chaîne « False » retirerait la carte.
    / Sends `POST card/set_primary` with `{first_tag_id, delete}`; `delete` is a real bool.
    """
    tag_de_la_carte = identifiant_unique().upper()
    client_des_cartes = NFCcardFedow(fedow_config=MagicMock())

    with envoi_reseau_simule(code_de_la_reponse) as envois:
        client_des_cartes.set_primary(tag_de_la_carte, delete=retirer)

    assert len(envois) == 1
    assert envois[0]["path"] == "card/set_primary"
    assert envois[0]["data"] == {"first_tag_id": tag_de_la_carte, "delete": retirer}
    assert envois[0]["data"]["delete"] is retirer


@pytest.mark.parametrize("code_de_la_reponse", [200, 205, 208])
def test_client_set_primary_accepte_200_205_208(code_de_la_reponse):
    """
    200 (déclarée), 205 (retirée), 208 (déjà déclarée) : aucune exception.
    / 200 (declared), 205 (withdrawn), 208 (already declared): no exception.
    """
    client_des_cartes = NFCcardFedow(fedow_config=MagicMock())

    with envoi_reseau_simule(code_de_la_reponse):
        client_des_cartes.set_primary(identifiant_unique().upper(), delete=False)


@pytest.mark.parametrize("code_de_la_reponse", [400, 403, 404, 500])
def test_client_set_primary_leve_une_exception_avec_le_code(code_de_la_reponse):
    """
    Toute autre réponse lève une exception dont le message contient le code : l'admin
    et la commande de rattrapage l'affichent tel quel.
    / Any other answer raises, the code is in the message.
    """
    client_des_cartes = NFCcardFedow(fedow_config=MagicMock())

    with envoi_reseau_simule(code_de_la_reponse):
        with pytest.raises(Exception) as exception_levee:
            client_des_cartes.set_primary(identifiant_unique().upper(), delete=False)

    assert str(code_de_la_reponse) in str(exception_levee.value)
