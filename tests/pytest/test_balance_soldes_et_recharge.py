"""
tests/pytest/test_balance_soldes_et_recharge.py
La page /my_account/balance/ : agregation des soldes, recharge, remboursement.
/ The /my_account/balance/ page: balance aggregation, refill, refund.

LOCALISATION : tests/pytest/test_balance_soldes_et_recharge.py

CE QUI EST TESTE / WHAT IS TESTED
---------------------------------
Cette page est l'endroit ou DEUX moteurs de monnaie se rencontrent pendant la
transition Fedow, et ou une erreur d'agregation ne casse rien visiblement :
elle affiche un solde faux, en double, ou en fait disparaitre un.

Les sources qui s'y melangent :

1. le FED du reseau, lu sur le Fedow distant (`is_stripe_primary=True`) ;
2. les monnaies locales d'autres collectifs (caisse sociale alimentaire, etc.),
   lues sur le meme Fedow distant et acceptees ici par federation ;
3. les assets du moteur local `fedow_core`, ajoutes par `_agreger_tokens_locaux`.

Les trois arrivent dans UNE seule liste de dictionnaires, rendue par un seul
tableau. Les tests couvrent le helper d'agregation, les vues qui le servent, le
remboursement en ligne, la recharge et son retour.

/ This page is where TWO currency engines meet during the Fedow transition. All
sources land in ONE list of dicts rendered by a single table.

POURQUOI PAS `mock_stripe` / WHY NOT `mock_stripe`
--------------------------------------------------
La fixture `mock_stripe` du conftest patche `stripe.checkout.Session.*`. Or ces
vues n'appellent JAMAIS Stripe directement : c'est Fedow qui parle a Stripe et
qui signe/verifie les metadonnees. On patche donc `BaseBillet.views.FedowAPI`.
/ These views never call Stripe directly: Fedow does. We patch FedowAPI.

Lancement / Run:
    docker exec lespass_django poetry run pytest \
        /DjangoFiles/tests/pytest/test_balance_soldes_et_recharge.py -v
"""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.contrib import messages as django_messages
from django.contrib.messages import get_messages
from django.test import Client
from django_tenants.utils import tenant_context

from AuthBillet.models import HumanUser, Wallet
from BaseBillet.models import Configuration
from BaseBillet.views import _agreger_tokens_locaux
from Customers.models import Client as TenantClient
from fedow_core.models import Asset, Token
from fedow_core.services import AssetService

# Prefixe pour reconnaitre et nettoyer les donnees de ce fichier.
# La base de dev est partagee et sans rollback.
# / Prefix to recognize and clean this file's data. Shared dev DB, no rollback.
PREFIXE_DE_TEST = 'TEST_balance'


# ---------------------------------------------------------------------------
# Fixtures et utilitaires
# ---------------------------------------------------------------------------


@pytest.fixture
def tenant():
    """Le tenant de developpement. / The development tenant."""
    return TenantClient.objects.get(schema_name="lespass")


def _client_navigateur():
    """Client de test pointant sur le domaine du tenant.
    / Test client aimed at the tenant domain."""
    return Client(HTTP_HOST="lespass.tibillet.localhost")


def _creer_humain(tenant, prefixe, email_valide=True):
    """Cree un HumanUser jetable dans le schema du tenant.
    / Creates a throwaway HumanUser inside the tenant schema.

    Chaque test cree le sien : la suite tourne sur la base de DEV, sans
    rollback. Un identifiant unique evite toute collision entre les runs.
    / Each test creates its own: the suite runs on the DEV database with no
    rollback. A unique id avoids collisions between runs.
    """
    identifiant_unique = f"{prefixe}_{uuid.uuid4().hex[:8]}@example.com"
    with tenant_context(tenant):
        return HumanUser.objects.create(
            email=identifiant_unique,
            username=identifiant_unique,
            email_valid=email_valide,
        )


def _creer_humain_avec_wallet(tenant, prefixe):
    """Un HumanUser dote d'un wallet local, pret a porter des Token fedow_core.
    / A HumanUser with a local wallet, ready to hold fedow_core Tokens.
    """
    utilisateur = _creer_humain(tenant, prefixe)
    with tenant_context(tenant):
        utilisateur.wallet = Wallet.objects.create(
            name=f'{PREFIXE_DE_TEST} wallet {uuid.uuid4().hex[:8]}',
            origin=tenant,
        )
        utilisateur.save()
    return utilisateur


def _supprimer_humain(tenant, utilisateur):
    """Nettoie un utilisateur de test et son wallet.

    L'ordre est impose par les FK PROTECT : les Token d'abord, puis
    l'utilisateur, puis son wallet. Tout se fait dans `tenant_context` car les
    cascades atteignent des tables de TENANT_APPS (`BaseBillet.LigneArticle`
    pour le wallet), absentes du schema public (PIEGES 11.9).
    / Order imposed by PROTECT FKs. Everything inside tenant_context because the
    cascades reach TENANT_APPS tables missing from the public schema.
    """
    with tenant_context(tenant):
        wallet = utilisateur.wallet
        if wallet is not None:
            Token.objects.filter(wallet=wallet).delete()
        utilisateur.delete()
        if wallet is not None:
            try:
                wallet.delete()
            except Exception:
                # Un objet metier peut proteger le wallet (FK PROTECT) : on
                # laisse la trace plutot que de casser le test.
                # / A business object may protect the wallet: leave it behind
                # rather than breaking the test.
                pass


def _niveaux_des_messages(response):
    """Renvoie les niveaux des messages django poses pendant la requete.
    / Returns the levels of the django messages set during the request.

    On lit le NIVEAU (SUCCESS / ERROR) et jamais le texte : les libelles passent
    par gettext, donc leur valeur depend de la langue active au moment du run.
    / We read the LEVEL, never the text: labels go through gettext.
    """
    return [message.level for message in get_messages(response.wsgi_request)]


def _config_factice(module_monnaie_locale=True, organisation="Le Tiers Lustre"):
    """Une configuration minimale pour `_agreger_tokens_locaux`.

    Le helper ne lit que deux attributs : `module_monnaie_locale` et
    `organisation`. Un objet simple suffit donc, et evite de modifier la
    Configuration reelle du tenant — que d'autres tests de la suite lisent.
    / The helper reads two attributes only, so a plain object is enough and
    avoids mutating the tenant's real Configuration, which other tests read.
    """
    return SimpleNamespace(
        module_monnaie_locale=module_monnaie_locale,
        organisation=organisation,
    )


def _token_distant(
    nom,
    valeur,
    categorie='TLF',
    est_stripe_primaire=False,
    asset_uuid=None,
    place_origin_uuid=None,
    places_federees=None,
):
    """Fabrique un dictionnaire de token tel que le Fedow distant le renvoie.

    On fabrique le dictionnaire A LA MAIN plutot que de faire passer un vrai
    payload dans `WalletValidator` : `AssetValidator.validate()` CREE un
    `AssetFedowPublic` en base quand l'uuid lui est inconnu, et
    `WalletValidator.validate()` cree un `Wallet`. Un test qui utiliserait le
    validateur polluerait donc la base a chaque run.
    / We build the dict BY HAND instead of running a real payload through
    WalletValidator: AssetValidator.validate() CREATES an AssetFedowPublic row
    for unknown uuids, and WalletValidator.validate() creates a Wallet.

    La forme suit `TokenValidator` / `AssetValidator` (fedow_connect/validators.py).
    """
    return {
        "uuid": str(uuid.uuid4()),
        "name": nom,
        "value": valeur,
        "asset_category": categorie,
        "last_transaction_datetime": None,
        "asset": {
            "uuid": str(asset_uuid or uuid.uuid4()),
            "name": nom,
            "category": categorie,
            "currency_code": "EUR",
            "is_stripe_primary": est_stripe_primaire,
            "place_origin": {"uuid": str(place_origin_uuid)} if place_origin_uuid else None,
            "place_uuid_federated_with": places_federees or [],
        },
    }


# ---------------------------------------------------------------------------
# A. _agreger_tokens_locaux — le point de jonction des deux moteurs
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_agregation_ne_fait_rien_sur_un_tenant_sans_monnaie_locale(tenant):
    """Module monnaie locale desactive : la liste distante ressort intacte.

    Sur un tenant qui n'a pas active le moteur local, les soldes vivent
    uniquement sur le Fedow distant. Y ajouter des tokens locaux afficherait des
    monnaies que le collectif n'utilise pas.
    / With the local engine disabled, balances live on the remote Fedow only.
    """
    utilisateur = _creer_humain_avec_wallet(tenant, "agreg_v1")
    try:
        tokens_distants = [_token_distant("Brouzouf", 1500)]

        resultat = _agreger_tokens_locaux(
            tokens_distants,
            utilisateur,
            _config_factice(module_monnaie_locale=False),
        )

        assert len(resultat) == 1
        assert resultat[0]["name"] == "Brouzouf"
    finally:
        _supprimer_humain(tenant, utilisateur)


@pytest.mark.django_db
def test_agregation_ne_fait_rien_sans_wallet(tenant):
    """Un utilisateur sans wallet n'a aucun solde local a ajouter.
    / A user without a wallet has no local balance to add."""
    utilisateur = _creer_humain(tenant, "agreg_sans_wallet")
    try:
        tokens_distants = [_token_distant("Brouzouf", 1500)]

        resultat = _agreger_tokens_locaux(
            tokens_distants,
            utilisateur,
            _config_factice(),
        )

        assert len(resultat) == 1
    finally:
        _supprimer_humain(tenant, utilisateur)


@pytest.mark.django_db
def test_agregation_avec_un_wallet_vide_ne_change_rien(tenant):
    """Wallet existant mais sans aucun Token : rien n'est ajoute.
    / Existing wallet with no Token: nothing is added."""
    utilisateur = _creer_humain_avec_wallet(tenant, "agreg_vide")
    try:
        resultat = _agreger_tokens_locaux([], utilisateur, _config_factice())

        assert resultat == []
    finally:
        _supprimer_humain(tenant, utilisateur)


@pytest.mark.django_db
def test_un_token_local_est_ajoute_et_marque_comme_local(tenant, asset_local_cadeau):
    """Un solde du moteur local apparait, marque `is_local`.

    Le marqueur `is_local` porte le badge « Local » du tableau, et
    `names_of_place_federated` vaut l'organisation courante pour que la ligne ne
    soit pas grisee : cette monnaie est bien utilisable ici.
    / The is_local flag drives the "Local" badge, and names_of_place_federated
    holds the current org so the row is not greyed out.
    """
    utilisateur = _creer_humain_avec_wallet(tenant, "agreg_local")
    try:
        with tenant_context(tenant):
            Token.objects.create(
                wallet=utilisateur.wallet,
                asset=asset_local_cadeau,
                value=2500,
            )

        resultat = _agreger_tokens_locaux(
            [],
            utilisateur,
            _config_factice(organisation="Le Tiers Lustre"),
        )

        assert len(resultat) == 1
        token_ajoute = resultat[0]
        assert token_ajoute["value"] == 2500
        assert token_ajoute["is_local"] is True
        assert token_ajoute["asset"]["is_stripe_primary"] is False
        assert token_ajoute["asset"]["names_of_place_federated"] == ["Le Tiers Lustre"]
    finally:
        _supprimer_humain(tenant, utilisateur)


@pytest.mark.django_db
@pytest.mark.parametrize("solde_nul_ou_negatif", [0, -500])
def test_un_token_local_sans_solde_positif_est_ignore(
    tenant, asset_local_cadeau, solde_nul_ou_negatif,
):
    """Solde a zero ou negatif : la ligne n'est pas affichee.

    Un solde a zero encombrerait la page ; un solde negatif (regularisation en
    cours) ne doit pas etre presente comme un avoir.
    / A zero balance would clutter the page; a negative one must not be shown as
    credit.
    """
    utilisateur = _creer_humain_avec_wallet(tenant, "agreg_zero")
    try:
        with tenant_context(tenant):
            Token.objects.create(
                wallet=utilisateur.wallet,
                asset=asset_local_cadeau,
                value=solde_nul_ou_negatif,
            )

        resultat = _agreger_tokens_locaux([], utilisateur, _config_factice())

        assert resultat == []
    finally:
        _supprimer_humain(tenant, utilisateur)


@pytest.mark.django_db
def test_un_asset_deja_affiche_par_le_fedow_distant_n_est_pas_redouble(
    tenant, asset_local_cadeau,
):
    """Si les deux moteurs portent le meme uuid d'asset, le distant l'emporte.

    ATTENTION — cette branche est INATTEIGNABLE en production : les uuid des
    deux moteurs sont independants (`fedow_core.Asset` les tire au hasard, et
    rien ne pousse un uuid local vers le Fedow distant). Le test force la
    coincidence pour verrouiller le comportement avant l'import de la phase
    suivante, qui pourrait conserver les uuid d'origine et rendre le cas reel.
    / This branch is UNREACHABLE in production: the two engines' uuids are
    independent. The test forces the collision to lock the behaviour ahead of
    the upcoming import, which may preserve original uuids.
    """
    utilisateur = _creer_humain_avec_wallet(tenant, "agreg_dedup")
    try:
        with tenant_context(tenant):
            Token.objects.create(
                wallet=utilisateur.wallet,
                asset=asset_local_cadeau,
                value=2500,
            )

        # Le token distant porte l'uuid de l'asset local.
        # / The remote token carries the local asset's uuid.
        tokens_distants = [
            _token_distant("Version distante", 700, asset_uuid=asset_local_cadeau.uuid),
        ]

        resultat = _agreger_tokens_locaux(
            tokens_distants,
            utilisateur,
            _config_factice(),
        )

        assert len(resultat) == 1
        assert resultat[0]["name"] == "Version distante"
        assert "is_local" not in resultat[0]
    finally:
        _supprimer_humain(tenant, utilisateur)


@pytest.mark.django_db
def test_l_agregation_modifie_la_liste_recue(tenant, asset_local_cadeau):
    """Le helper ajoute les tokens locaux DANS la liste qu'on lui passe.

    Il fait `tokens.append(...)` puis renvoie la meme liste : l'appelant qui
    garderait une reference sur sa liste d'origine la verrait grandir. Les deux
    vues du compte reaffectent le resultat, donc c'est sans consequence — mais
    un nouvel appelant qui l'ignorerait afficherait deux fois les memes soldes.
    / The helper appends into the list it receives and returns that same list.
    """
    utilisateur = _creer_humain_avec_wallet(tenant, "agreg_mutation")
    try:
        with tenant_context(tenant):
            Token.objects.create(
                wallet=utilisateur.wallet,
                asset=asset_local_cadeau,
                value=2500,
            )

        liste_initiale = []
        resultat = _agreger_tokens_locaux(
            liste_initiale,
            utilisateur,
            _config_factice(),
        )

        assert resultat is liste_initiale
        assert len(liste_initiale) == 1
    finally:
        _supprimer_humain(tenant, utilisateur)


# ---------------------------------------------------------------------------
# B. tokens_table — la vue qui sert le tableau des monnaies
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_le_tableau_affiche_les_monnaies_des_deux_moteurs(
    tenant, asset_local_cadeau, asset_local_monnaie,
):
    """Panorama complet : FED du reseau, monnaie d'un autre collectif, et locales.

    C'est le scenario de la transition : un adherent porte a la fois du FED, une
    monnaie de caisse sociale alimentaire d'un autre lieu, et deux monnaies du
    moteur local. Les quatre doivent apparaitre, les deux locales portant le
    badge dedie.
    / The transition scenario: FED, another venue's currency, and two local ones.
    """
    utilisateur = _creer_humain_avec_wallet(tenant, "tableau_panorama")
    try:
        with tenant_context(tenant):
            Token.objects.create(
                wallet=utilisateur.wallet, asset=asset_local_cadeau, value=2500,
            )
            Token.objects.create(
                wallet=utilisateur.wallet, asset=asset_local_monnaie, value=4200,
            )

        tokens_distants = [
            _token_distant("TiBillet", 1000, categorie='FED', est_stripe_primaire=True),
            _token_distant("Caisse sociale alimentaire", 5000, categorie='TLF'),
        ]

        client = _client_navigateur()
        client.force_login(utilisateur)

        with patch("BaseBillet.views.FedowAPI") as fedow_mocke:
            fedow_mocke.return_value.wallet.cached_retrieve_by_signature.return_value.validated_data = {
                "tokens": tokens_distants,
            }
            response = client.get("/my_account/tokens_table/")

        contenu = response.content.decode()
        assert response.status_code == 200
        assert "Caisse sociale alimentaire" in contenu
        assert asset_local_cadeau.name in contenu
        assert asset_local_monnaie.name in contenu
        # Le FED s'affiche sous le libelle « TiBillets » du gabarit, pas sous son
        # nom d'asset. / FED shows as the template's "TiBillets" label.
        assert "TiBillets" in contenu
        assert contenu.count('data-testid="token-badge-local"') == 2
    finally:
        _supprimer_humain(tenant, utilisateur)


@pytest.mark.django_db
def test_le_tableau_survit_a_une_panne_du_fedow_distant(tenant, asset_local_cadeau):
    """Fedow injoignable : les monnaies locales restent affichees.

    Le Fedow est un service distant. S'il tombe, l'adherent doit continuer de
    voir ce que le moteur local sait, plutot qu'une page d'erreur.
    / If the remote Fedow is down, local balances must still show.
    """
    utilisateur = _creer_humain_avec_wallet(tenant, "tableau_panne")
    try:
        with tenant_context(tenant):
            Token.objects.create(
                wallet=utilisateur.wallet, asset=asset_local_cadeau, value=2500,
            )

        client = _client_navigateur()
        client.force_login(utilisateur)

        with patch("BaseBillet.views.FedowAPI") as fedow_mocke:
            fedow_mocke.return_value.wallet.cached_retrieve_by_signature.side_effect = (
                ConnectionError("Fedow injoignable")
            )
            response = client.get("/my_account/tokens_table/")

        assert response.status_code == 200
        assert asset_local_cadeau.name in response.content.decode()
    finally:
        _supprimer_humain(tenant, utilisateur)


@pytest.mark.django_db
def test_le_tableau_survit_a_une_panne_de_l_agregation_locale(tenant):
    """Moteur local en echec : les monnaies distantes restent affichees.

    La symetrie de la garde precedente : chaque source est lue dans son propre
    filet, pour qu'une panne d'un cote n'emporte pas l'autre.
    / The mirror of the previous guard: each source has its own safety net.
    """
    utilisateur = _creer_humain_avec_wallet(tenant, "tableau_panne_locale")
    try:
        client = _client_navigateur()
        client.force_login(utilisateur)

        with (
            patch("BaseBillet.views.FedowAPI") as fedow_mocke,
            patch(
                "BaseBillet.views._agreger_tokens_locaux",
                side_effect=RuntimeError("base locale indisponible"),
            ),
        ):
            fedow_mocke.return_value.wallet.cached_retrieve_by_signature.return_value.validated_data = {
                "tokens": [_token_distant("Caisse sociale alimentaire", 5000)],
            }
            response = client.get("/my_account/tokens_table/")

        assert response.status_code == 200
        assert "Caisse sociale alimentaire" in response.content.decode()
    finally:
        _supprimer_humain(tenant, utilisateur)


@pytest.mark.django_db
def test_le_tableau_reste_affichable_si_les_deux_sources_tombent(tenant):
    """Les deux moteurs en echec : page vide, jamais d'erreur serveur.
    / Both engines down: empty table, never a server error."""
    utilisateur = _creer_humain_avec_wallet(tenant, "tableau_double_panne")
    try:
        client = _client_navigateur()
        client.force_login(utilisateur)

        with (
            patch("BaseBillet.views.FedowAPI") as fedow_mocke,
            patch(
                "BaseBillet.views._agreger_tokens_locaux",
                side_effect=RuntimeError("base locale indisponible"),
            ),
        ):
            fedow_mocke.return_value.wallet.cached_retrieve_by_signature.side_effect = (
                ConnectionError("Fedow injoignable")
            )
            response = client.get("/my_account/tokens_table/")

        assert response.status_code == 200
    finally:
        _supprimer_humain(tenant, utilisateur)


@pytest.mark.django_db
def test_les_adhesions_ne_sont_pas_dans_le_tableau_des_monnaies(tenant):
    """Un token d'adhesion (SUB) est ecarte : il a sa propre page.
    / A subscription token (SUB) is filtered out: it has its own page."""
    utilisateur = _creer_humain_avec_wallet(tenant, "tableau_sub")
    try:
        client = _client_navigateur()
        client.force_login(utilisateur)

        with patch("BaseBillet.views.FedowAPI") as fedow_mocke:
            fedow_mocke.return_value.wallet.cached_retrieve_by_signature.return_value.validated_data = {
                "tokens": [
                    _token_distant("Adhesion annuelle", 2000, categorie='SUB'),
                    _token_distant("Caisse sociale alimentaire", 5000),
                ],
            }
            response = client.get("/my_account/tokens_table/")

        contenu = response.content.decode()
        assert "Adhesion annuelle" not in contenu
        assert "Caisse sociale alimentaire" in contenu
    finally:
        _supprimer_humain(tenant, utilisateur)


@pytest.mark.django_db
def test_une_monnaie_non_acceptee_ici_est_grisee(tenant):
    """La monnaie d'un collectif non federe avec celui-ci s'affiche en grise.

    L'adherent la possede, mais ne peut pas la depenser ici. Le gabarit lui pose
    la classe `opacity-50` quand l'organisation courante n'est pas dans les
    lieux federes et que ce n'est pas le FED.
    / The member owns it but cannot spend it here: the template greys it out.
    """
    utilisateur = _creer_humain_avec_wallet(tenant, "tableau_grise")
    try:
        client = _client_navigateur()
        client.force_login(utilisateur)

        with patch("BaseBillet.views.FedowAPI") as fedow_mocke:
            fedow_mocke.return_value.wallet.cached_retrieve_by_signature.return_value.validated_data = {
                "tokens": [_token_distant("Monnaie lointaine", 5000)],
            }
            response = client.get("/my_account/tokens_table/")

        contenu = response.content.decode()
        assert "Monnaie lointaine" in contenu
        assert "opacity-50" in contenu
    finally:
        _supprimer_humain(tenant, utilisateur)


@pytest.mark.django_db
def test_le_fed_du_reseau_n_est_jamais_grise(tenant):
    """Le FED est depensable partout : sa ligne reste pleinement lisible.
    / FED is spendable everywhere: its row is never greyed out."""
    utilisateur = _creer_humain_avec_wallet(tenant, "tableau_fed")
    try:
        client = _client_navigateur()
        client.force_login(utilisateur)

        with patch("BaseBillet.views.FedowAPI") as fedow_mocke:
            fedow_mocke.return_value.wallet.cached_retrieve_by_signature.return_value.validated_data = {
                "tokens": [
                    _token_distant("TiBillet", 1000, categorie='FED', est_stripe_primaire=True),
                ],
            }
            response = client.get("/my_account/tokens_table/")

        assert "opacity-50" not in response.content.decode()
    finally:
        _supprimer_humain(tenant, utilisateur)


@pytest.mark.django_db
def test_le_tableau_est_ferme_aux_visiteurs_anonymes():
    """Sans session, pas de solde affiche.
    / No session, no balance shown."""
    client = _client_navigateur()

    with patch("BaseBillet.views.FedowAPI") as fedow_mocke:
        response = client.get("/my_account/tokens_table/")
        # Fedow ne doit jamais etre sollicite pour un anonyme.
        # / Fedow must never be called for an anonymous visitor.
        fedow_mocke.return_value.wallet.cached_retrieve_by_signature.assert_not_called()

    assert response.status_code != 200


# ---------------------------------------------------------------------------
# C. refund_online — seul le FED du reseau est remboursable en ligne
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_pas_de_remboursement_sans_portefeuille_federe(tenant):
    """Aucun token FED : on refuse, et Fedow n'est jamais sollicite.
    / No FED token: refused, and Fedow is never asked."""
    utilisateur = _creer_humain_avec_wallet(tenant, "refund_sans_fed")
    try:
        client = _client_navigateur()
        client.force_login(utilisateur)

        with patch("BaseBillet.views.FedowAPI") as fedow_mocke:
            fedow_mocke.return_value.wallet.cached_retrieve_by_signature.return_value.validated_data = {
                "tokens": [],
            }
            response = client.get("/my_account/refund_online/")
            fedow_mocke.return_value.wallet.refund_fed_by_signature.assert_not_called()

        assert django_messages.ERROR in _niveaux_des_messages(response)
    finally:
        _supprimer_humain(tenant, utilisateur)


@pytest.mark.django_db
def test_une_monnaie_locale_n_est_jamais_remboursee_en_ligne(tenant, asset_local_cadeau):
    """Cinquante euros de monnaie locale ne declenchent aucun remboursement.

    C'est la garde metier centrale de cette vue : seule la monnaie federee,
    rechargee en ligne par carte bancaire, peut repartir vers le compte
    bancaire. Une monnaie locale a ete versee au collectif, souvent en especes :
    la rembourser en ligne prendrait l'argent a un lieu pour le rendre a un
    autre.
    / The core business guard: only the federated currency, topped up online by
    card, can go back to a bank account. Local currency was paid to a venue.
    """
    utilisateur = _creer_humain_avec_wallet(tenant, "refund_locale")
    try:
        with tenant_context(tenant):
            Token.objects.create(
                wallet=utilisateur.wallet, asset=asset_local_cadeau, value=5000,
            )

        client = _client_navigateur()
        client.force_login(utilisateur)

        with patch("BaseBillet.views.FedowAPI") as fedow_mocke:
            # Le Fedow distant ne connait qu'une monnaie de caisse sociale : pas
            # de FED. / The remote Fedow only knows a local currency, no FED.
            fedow_mocke.return_value.wallet.cached_retrieve_by_signature.return_value.validated_data = {
                "tokens": [_token_distant("Caisse sociale alimentaire", 5000)],
            }
            response = client.get("/my_account/refund_online/")
            fedow_mocke.return_value.wallet.refund_fed_by_signature.assert_not_called()

        niveaux = _niveaux_des_messages(response)
        assert django_messages.ERROR in niveaux
        assert django_messages.SUCCESS not in niveaux
    finally:
        _supprimer_humain(tenant, utilisateur)


@pytest.mark.django_db
def test_pas_de_remboursement_si_le_solde_federe_est_vide(tenant):
    """Un FED a zero : rien a rembourser.
    / A FED at zero: nothing to refund."""
    utilisateur = _creer_humain_avec_wallet(tenant, "refund_vide")
    try:
        client = _client_navigateur()
        client.force_login(utilisateur)

        with patch("BaseBillet.views.FedowAPI") as fedow_mocke:
            fedow_mocke.return_value.wallet.cached_retrieve_by_signature.return_value.validated_data = {
                "tokens": [
                    _token_distant("TiBillet", 0, categorie='FED', est_stripe_primaire=True),
                ],
            }
            response = client.get("/my_account/refund_online/")
            fedow_mocke.return_value.wallet.refund_fed_by_signature.assert_not_called()

        assert django_messages.ERROR in _niveaux_des_messages(response)
    finally:
        _supprimer_humain(tenant, utilisateur)


@pytest.mark.django_db
def test_le_remboursement_accepte_porte_sur_le_seul_solde_federe(
    tenant, asset_local_cadeau,
):
    """Fedow accepte : succes, cache purge, et courriel du montant FED seul.

    Le montant annonce a l'adherent ne doit compter QUE le FED, meme s'il porte
    par ailleurs des monnaies locales. Annoncer le total ferait attendre un
    virement plus gros que celui qui arrivera.
    / The amount announced counts the FED only, even when local currencies are
    present. Announcing the total would promise a larger transfer than the real
    one.
    """
    utilisateur = _creer_humain_avec_wallet(tenant, "refund_ok")
    try:
        with tenant_context(tenant):
            Token.objects.create(
                wallet=utilisateur.wallet, asset=asset_local_cadeau, value=5000,
            )

        client = _client_navigateur()
        client.force_login(utilisateur)

        with (
            patch("BaseBillet.views.FedowAPI") as fedow_mocke,
            patch("BaseBillet.views.send_email_generique") as courriel_mocke,
            patch("BaseBillet.views.cache") as cache_mocke,
        ):
            fedow_mocke.return_value.wallet.cached_retrieve_by_signature.return_value.validated_data = {
                "tokens": [
                    _token_distant("TiBillet", 1200, categorie='FED', est_stripe_primaire=True),
                    _token_distant("Caisse sociale alimentaire", 5000),
                ],
            }
            fedow_mocke.return_value.wallet.refund_fed_by_signature.return_value = (
                202, MagicMock(),
            )
            response = client.get("/my_account/refund_online/")

        assert django_messages.SUCCESS in _niveaux_des_messages(response)
        cache_mocke.delete.assert_called_once_with(f"wallet_user_{utilisateur.wallet.uuid}")

        # Le montant du courriel provient du seul token FED (1200 centimes),
        # jamais du total avec la monnaie locale.
        # / The email amount comes from the FED token alone, never the total.
        courriel_mocke.delay.assert_called_once()
        contexte_du_courriel = courriel_mocke.delay.call_args.kwargs["context"]
        assert "12" in contexte_du_courriel["table_info"]["Montant remboursé"]
        assert "62" not in contexte_du_courriel["table_info"]["Montant remboursé"]
    finally:
        _supprimer_humain(tenant, utilisateur)


@pytest.mark.django_db
def test_un_refus_de_fedow_n_envoie_aucun_courriel(tenant):
    """Fedow n'accepte pas : avertissement, et surtout pas de confirmation.

    Annoncer un remboursement qui n'a pas eu lieu ferait attendre un virement
    qui n'arrivera jamais.
    / Announcing a refund that did not happen would promise a transfer that
    never arrives.
    """
    utilisateur = _creer_humain_avec_wallet(tenant, "refund_refuse")
    try:
        client = _client_navigateur()
        client.force_login(utilisateur)

        with (
            patch("BaseBillet.views.FedowAPI") as fedow_mocke,
            patch("BaseBillet.views.send_email_generique") as courriel_mocke,
        ):
            fedow_mocke.return_value.wallet.cached_retrieve_by_signature.return_value.validated_data = {
                "tokens": [
                    _token_distant("TiBillet", 1200, categorie='FED', est_stripe_primaire=True),
                ],
            }
            fedow_mocke.return_value.wallet.refund_fed_by_signature.return_value = (
                400, {"erreur": "refus"},
            )
            response = client.get("/my_account/refund_online/")
            courriel_mocke.delay.assert_not_called()

        niveaux = _niveaux_des_messages(response)
        assert django_messages.WARNING in niveaux
        assert django_messages.SUCCESS not in niveaux
    finally:
        _supprimer_humain(tenant, utilisateur)


# ---------------------------------------------------------------------------
# D. refill_wallet — la demande de recharge
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_la_recharge_renvoie_vers_l_adresse_de_paiement_donnee_par_fedow(tenant):
    """Fedow fournit une adresse de paiement : le navigateur y est envoye.

    C'est Fedow qui fabrique la demande de paiement et signe ses metadonnees ;
    Lespass ne fait que relayer l'adresse.
    / Fedow builds the payment request and signs its metadata; Lespass only
    relays the address.
    """
    utilisateur = _creer_humain_avec_wallet(tenant, "refill_ok")
    try:
        client = _client_navigateur()
        client.force_login(utilisateur)

        adresse_de_paiement = "https://checkout.stripe.com/c/pay/fake_session"
        with patch("BaseBillet.views.FedowAPI") as fedow_mocke:
            fedow_mocke.return_value.wallet.get_federated_token_refill_checkout.return_value = (
                adresse_de_paiement
            )
            response = client.get("/my_account/refill_wallet/")

        assert response["HX-Redirect"] == adresse_de_paiement
    finally:
        _supprimer_humain(tenant, utilisateur)


@pytest.mark.django_db
def test_la_recharge_indisponible_ramene_au_compte_avec_une_erreur(tenant):
    """Fedow ne fournit rien : message d'erreur, retour au compte.

    Cas reel : l'instance Fedow n'a pas de cle de paiement configuree. L'adherent
    doit comprendre que la recharge est indisponible, pas rester sur une page
    muette.
    / Real case: the Fedow instance has no payment key configured.
    """
    utilisateur = _creer_humain_avec_wallet(tenant, "refill_indispo")
    try:
        client = _client_navigateur()
        client.force_login(utilisateur)

        with patch("BaseBillet.views.FedowAPI") as fedow_mocke:
            fedow_mocke.return_value.wallet.get_federated_token_refill_checkout.return_value = None
            response = client.get("/my_account/refill_wallet/")

        assert response["HX-Redirect"] == "/my_account/"
        assert django_messages.ERROR in _niveaux_des_messages(response)
    finally:
        _supprimer_humain(tenant, utilisateur)


@pytest.mark.django_db
def test_la_recharge_est_fermee_aux_visiteurs_anonymes():
    """Sans session, aucune demande de paiement n'est fabriquee.
    / No session, no payment request is built."""
    client = _client_navigateur()

    with patch("BaseBillet.views.FedowAPI") as fedow_mocke:
        response = client.get("/my_account/refill_wallet/")
        fedow_mocke.return_value.wallet.get_federated_token_refill_checkout.assert_not_called()

    assert response.status_code != 200


# ---------------------------------------------------------------------------
# E. return_refill_wallet — le retour apres paiement de recharge
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_retour_recharge_wallet_confirme_par_fedow_affiche_un_succes(tenant):
    """Fedow confirme le paiement : message de succes et retour au compte.
    / Fedow confirms the payment: success message and back to the account."""
    utilisateur = _creer_humain(tenant, "retour_ok")
    try:
        client = _client_navigateur()
        client.force_login(utilisateur)

        # Fedow renvoie un wallet : la recharge est validee.
        # / Fedow returns a wallet: the refill is confirmed.
        with patch("BaseBillet.views.FedowAPI") as fedow_mocke:
            fedow_mocke.return_value.wallet.retrieve_from_refill_checkout.return_value = MagicMock()
            response = client.get(f"/my_account/{uuid.uuid4()}/return_refill_wallet/")

        assert response.status_code == 302
        assert response.url == "/my_account/"
        assert django_messages.SUCCESS in _niveaux_des_messages(response)
    finally:
        _supprimer_humain(tenant, utilisateur)


@pytest.mark.django_db
def test_retour_recharge_wallet_refuse_par_fedow_affiche_une_erreur(tenant):
    """Fedow ne confirme rien : message d'erreur, aucun succes annonce.

    C'est le cas ou la signature des metadonnees ne correspond pas.
    L'utilisateur ne doit surtout pas voir « recharge effectuee ».
    / Metadata signature mismatch: error message, and above all no success.
    """
    utilisateur = _creer_humain(tenant, "retour_ko")
    try:
        client = _client_navigateur()
        client.force_login(utilisateur)

        # Fedow renvoie None : paiement non verifie.
        # / Fedow returns None: payment not verified.
        with patch("BaseBillet.views.FedowAPI") as fedow_mocke:
            fedow_mocke.return_value.wallet.retrieve_from_refill_checkout.return_value = None
            response = client.get(f"/my_account/{uuid.uuid4()}/return_refill_wallet/")

        niveaux = _niveaux_des_messages(response)
        assert response.status_code == 302
        assert django_messages.ERROR in niveaux
        assert django_messages.SUCCESS not in niveaux
    finally:
        _supprimer_humain(tenant, utilisateur)


@pytest.mark.django_db
def test_retour_recharge_wallet_survit_a_une_panne_fedow(tenant):
    """Fedow est injoignable : erreur affichee, pas d'erreur serveur.

    Si le service distant tombe pendant le retour de paiement, l'utilisateur
    doit atterrir sur son compte avec un message, non sur une page d'erreur.
    / If the remote service fails during the payment return, the user lands on
    their account with a message, not on a 500 page.
    """
    utilisateur = _creer_humain(tenant, "retour_panne")
    try:
        client = _client_navigateur()
        client.force_login(utilisateur)

        with patch("BaseBillet.views.FedowAPI") as fedow_mocke:
            fedow_mocke.return_value.wallet.retrieve_from_refill_checkout.side_effect = (
                ConnectionError("Fedow injoignable")
            )
            response = client.get(f"/my_account/{uuid.uuid4()}/return_refill_wallet/")

        niveaux = _niveaux_des_messages(response)
        assert response.status_code == 302
        assert django_messages.ERROR in niveaux
        assert django_messages.SUCCESS not in niveaux
    finally:
        _supprimer_humain(tenant, utilisateur)


@pytest.mark.django_db
def test_retour_recharge_wallet_refuse_a_un_anonyme():
    """Un visiteur non connecte n'atteint pas le retour de recharge.
    / An anonymous visitor does not reach the refill return view."""
    client = _client_navigateur()

    with patch("BaseBillet.views.FedowAPI") as fedow_mocke:
        response = client.get(f"/my_account/{uuid.uuid4()}/return_refill_wallet/")
        # Fedow ne doit jamais etre sollicite pour un anonyme.
        # / Fedow must never be called for an anonymous visitor.
        fedow_mocke.return_value.wallet.retrieve_from_refill_checkout.assert_not_called()

    assert response.status_code != 200


# ---------------------------------------------------------------------------
# F. show_refill_button — l'affichage des boutons de recharge et remboursement
# ---------------------------------------------------------------------------


def test_le_masquage_explicite_l_emporte_sur_le_forcage():
    """`hide_refill_button` gagne, meme combine au forcage.

    C'est l'interrupteur de derniere instance d'un gestionnaire qui veut faire
    disparaitre la recharge de sa page, quoi qu'il arrive par ailleurs.
    / The manager's last-resort switch wins over everything else.
    """
    configuration = Configuration(
        hide_refill_button=True,
        force_show_refill_button=True,
        stripe_payouts_enabled=True,
    )

    assert configuration.show_refill_button() is False


def test_le_forcage_affiche_le_bouton_sans_compte_bancaire_actif():
    """`force_show_refill_button` passe outre l'etat du compte bancaire.

    Sert aux collectifs dont l'encaissement est verifie hors du canal habituel.
    / For collectives whose payouts are validated outside the usual channel.
    """
    configuration = Configuration(
        hide_refill_button=False,
        force_show_refill_button=True,
        stripe_payouts_enabled=False,
    )

    assert configuration.show_refill_button() is True


def test_sans_compte_bancaire_actif_le_bouton_disparait():
    """Pas d'encaissement possible : ni recharge, ni demande de remboursement.

    Le gabarit conditionne les deux au meme drapeau : on ne propose pas de
    rembourser ce qu'on ne sait pas encaisser.
    / The template ties both to this flag: we do not offer to refund what we
    cannot collect.
    """
    configuration = Configuration(
        hide_refill_button=False,
        force_show_refill_button=False,
        stripe_payouts_enabled=False,
    )

    assert configuration.show_refill_button() is False


def test_avec_un_compte_bancaire_actif_le_bouton_s_affiche():
    """Cas nominal d'un collectif qui encaisse en ligne.
    / Nominal case for a collective that collects online."""
    configuration = Configuration(
        hide_refill_button=False,
        force_show_refill_button=False,
        stripe_payouts_enabled=True,
    )

    assert configuration.show_refill_button() is True


# ---------------------------------------------------------------------------
# Assets locaux partages par les tests
# ---------------------------------------------------------------------------


@pytest.fixture
def wallet_du_lieu(tenant):
    """Wallet createur des assets locaux de ce fichier.
    / Origin wallet for this file's local assets."""
    wallet = Wallet.objects.create(
        name=f'{PREFIXE_DE_TEST} lieu {uuid.uuid4().hex[:8]}',
        origin=tenant,
    )
    yield wallet
    with tenant_context(tenant):
        try:
            wallet.delete()
        except Exception:
            pass


@pytest.fixture
def asset_local_cadeau(tenant, wallet_du_lieu):
    """Une monnaie cadeau du moteur local.
    / A gift currency from the local engine."""
    yield from _asset_local(tenant, wallet_du_lieu, 'Cadeau', Asset.TNF, 'EUR')


@pytest.fixture
def asset_local_monnaie(tenant, wallet_du_lieu):
    """Une monnaie locale fiduciaire du moteur local.
    / A local fiduciary currency from the local engine."""
    yield from _asset_local(tenant, wallet_du_lieu, 'Monnaie', Asset.TLF, 'EUR')


def _asset_local(tenant, wallet_du_lieu, libelle, categorie, code_devise):
    """Cree un asset local jetable et le nettoie ensuite.

    Le nom porte un suffixe unique : le signal post_save d'`Asset` cree un
    Product « Recharge {nom} » sous contrainte unique (categorie, nom), et le
    second run leverait une IntegrityError sans ce suffixe (PIEGES 9.96).
    / The name carries a unique suffix: a post_save signal creates a
    "Recharge {name}" Product under a unique constraint.

    La creation ET le nettoyage passent par `tenant_context`, pour deux raisons
    distinctes :

    - a la creation, le signal post_save d'`Asset` cherche
      `BaseBillet.CategorieProduct` pour fabriquer son Product de recharge.
      Cette table est une TENANT_APP : depuis le schema public, la requete leve
      `ProgrammingError: relation "BaseBillet_categorieproduct" does not exist`.
      Et rien ne garantit le schema courant : il depend du test precedent ;
    - a la suppression, la cascade atteint `BaseBillet.Product`, absent lui
      aussi du schema public (PIEGES 11.9).

    / Both creation and cleanup go through tenant_context: on creation the
    post_save signal looks up BaseBillet.CategorieProduct, and on delete the
    cascade reaches BaseBillet.Product — both TENANT_APPS tables missing from
    the public schema. The current schema depends on the previous test.
    """
    with tenant_context(tenant):
        asset = AssetService.creer_asset(
            tenant=tenant,
            name=f'{PREFIXE_DE_TEST} {libelle} {uuid.uuid4().hex[:8]}',
            category=categorie,
            currency_code=code_devise,
            wallet_origin=wallet_du_lieu,
        )

    yield asset

    with tenant_context(tenant):
        Token.objects.filter(asset=asset).delete()
        asset.delete()
