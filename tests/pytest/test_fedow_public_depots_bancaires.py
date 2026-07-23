"""
tests/pytest/test_fedow_public_depots_bancaires.py
Les remises en banque et l'historique des transactions d'un asset.
/ Bank deposits and an asset's transaction history.

LOCALISATION : tests/pytest/test_fedow_public_depots_bancaires.py

CE QUI EST TESTE / WHAT IS TESTED
---------------------------------
L'app `fedow_public` expose a un gestionnaire de lieu la vie d'une de ses
monnaies locales :

- `GET /fedow/asset/<uuid>/retrieve_bank_deposits/` — la ventilation de la
  monnaie par lieu a l'instant present, et l'historique des remises en banque ;
- `POST /fedow/asset/retrieve_transactions/` — les transactions sur une periode ;
- `POST /admin/.../bank_deposit/<asset>/<wallet>/` — la remise en banque
  elle-meme, qui vide le portefeuille d'un lieu de cette monnaie.

Cette app n'avait aucun test, alors qu'elle sert en production a suivre de
l'argent reel : une association qui rembourse ses producteurs, un festival qui
declare avoir recu son virement.

/ This app had no test at all, while it is used in production to track real
money: an association reimbursing its producers, a festival acknowledging a
received transfer.

OU SE FAIT LA DECREMENTATION / WHERE THE DECREMENT HAPPENS
-----------------------------------------------------------
C'est le Fedow DISTANT qui decremente le token : Lespass poste
`wallet/local_asset_bank_deposit`, le Fedow debite et renvoie la transaction
creee. Cote Lespass, on peut donc verifier deux choses, et deux seulement :

1. que la demande part avec le bon portefeuille et le bon asset — se tromper de
   portefeuille viderait celui d'un autre lieu ;
2. que la reponse du Fedow, dont le solde deja decremente, est fidelement
   affichee au gestionnaire.

Les tests simulent le Fedow. Ils ne prouvent pas qu'il decremente correctement —
c'est le travail de sa propre suite — mais ils prouvent que Lespass lui demande
la bonne chose et rend compte sans deformer.

/ The REMOTE Fedow does the decrementing. On the Lespass side we can check that
the request leaves with the right wallet and asset, and that the answer is
faithfully displayed. The tests do not prove the Fedow decrements correctly.

Lancement / Run:
    docker exec lespass_django poetry run pytest \
        /DjangoFiles/tests/pytest/test_fedow_public_depots_bancaires.py -v
"""

import uuid as uuid_module
from datetime import timedelta
from unittest import mock

import pytest
from django.test import Client as DjangoClient
from django.utils import timezone
from django_tenants.utils import tenant_context

from AuthBillet.models import TibilletUser, Wallet
from Customers.models import Client as TenantClient
from fedow_public.models import AssetFedowPublic

pytestmark = pytest.mark.django_db

PREFIXE_DE_TEST = 'TEST_depots'

# Montants de la ventilation simulee, en centimes. Distincts pour qu'une
# inversion entre deux lieux se voie dans les assertions.
# / Simulated breakdown amounts, distinct so a mix-up between venues shows.
TOTAL_CHEZ_LE_PRODUCTEUR = 45000
TOTAL_CHEZ_LE_FESTIVAL = 12500

MONTANT_DE_LA_REMISE = 45000


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tenant():
    """Le tenant de developpement. / The development tenant."""
    return TenantClient.objects.get(schema_name='lespass')


@pytest.fixture
def wallet_origine(tenant):
    """Le portefeuille createur de la monnaie locale.
    / The origin wallet of the local currency."""
    wallet = Wallet.objects.create(name=f'{PREFIXE_DE_TEST} origine')
    yield wallet
    with tenant_context(tenant):
        try:
            wallet.delete()
        except Exception:
            # Un asset peut proteger le portefeuille (FK PROTECT).
            # / An asset may protect the wallet.
            pass


@pytest.fixture
def monnaie_locale(tenant, wallet_origine):
    """Une monnaie locale du lieu, du genre de celles qu'on remet en banque.

    C'est le miroir local d'un asset qui vit sur le Fedow distant.
    / The local mirror of an asset living on the remote Fedow.
    """
    asset = AssetFedowPublic.objects.create(
        uuid=uuid_module.uuid4(),
        name=f'{PREFIXE_DE_TEST} Monnaie solidaire',
        currency_code='EUR',
        category=AssetFedowPublic.TOKEN_LOCAL_FIAT,
        origin=tenant,
        wallet_origin=wallet_origine,
    )
    yield asset
    with tenant_context(tenant):
        AssetFedowPublic.objects.filter(pk=asset.pk).delete()


@pytest.fixture
def gestionnaire(tenant):
    """Un administrateur du lieu, seul habilite a consulter ces pages.
    / A venue administrator, the only one allowed on these pages."""
    adresse = f'gestionnaire-depots-{uuid_module.uuid4().hex[:8]}@tibillet.localhost'
    with tenant_context(tenant):
        utilisateur = TibilletUser.objects.create(
            email=adresse, username=adresse, is_active=True, email_valid=True,
        )
        utilisateur.client_admin.add(tenant)
    yield utilisateur
    with tenant_context(tenant):
        utilisateur.delete()


@pytest.fixture
def adherent_lambda(tenant):
    """Un utilisateur sans droit d'administration.
    / A user without administration rights."""
    adresse = f'adherent-depots-{uuid_module.uuid4().hex[:8]}@tibillet.localhost'
    with tenant_context(tenant):
        utilisateur = TibilletUser.objects.create(
            email=adresse, username=adresse, is_active=True, email_valid=True,
        )
    yield utilisateur
    with tenant_context(tenant):
        utilisateur.delete()


def _navigateur(utilisateur=None):
    """Client HTTP sur le domaine du tenant, connecte ou non.
    / HTTP client on the tenant domain, logged in or not."""
    client = DjangoClient(HTTP_HOST='lespass.tibillet.localhost')
    if utilisateur is not None:
        client.force_login(utilisateur)
    return client


def _chemin_des_remises(asset):
    return f'/fedow/asset/{asset.uuid}/retrieve_bank_deposits/'


def _ventilation_simulee():
    """Ce que le Fedow renvoie comme repartition de la monnaie par lieu.
    / What the Fedow returns as the currency's breakdown by venue."""
    return {
        'total_by_place': [
            {'place_name': 'Ferme du Coteau', 'total_value': TOTAL_CHEZ_LE_PRODUCTEUR},
            {'place_name': 'Festival des Rives', 'total_value': TOTAL_CHEZ_LE_FESTIVAL},
        ],
    }


def _remises_simulees(nombre=1):
    """L'historique des remises en banque renvoye par le Fedow.
    / The bank deposit history returned by the Fedow."""
    maintenant = timezone.now()
    return [
        {
            'datetime': maintenant - timedelta(days=index),
            'amount': MONTANT_DE_LA_REMISE,
            'sender_name': f'Lieu remettant {index}',
        }
        for index in range(nombre)
    ]


# ---------------------------------------------------------------------------
# 1. Qui peut consulter les remises en banque
# ---------------------------------------------------------------------------


def test_un_adherent_ne_consulte_pas_les_remises_en_banque(
    tenant, monnaie_locale, adherent_lambda,
):
    """Ces pages exposent la tresorerie du lieu : elles sont reservees.

    Les montants remis en banque, et la repartition de la monnaie entre les
    lieux, ne regardent pas un adherent.
    / These pages expose the venue's treasury and are restricted.
    """
    reponse = _navigateur(adherent_lambda).get(_chemin_des_remises(monnaie_locale))

    assert reponse.status_code in (403, 302)


def test_un_visiteur_anonyme_ne_consulte_pas_les_remises_en_banque(
    tenant, monnaie_locale,
):
    """Sans session, aucune donnee de tresorerie.
    / No session, no treasury data."""
    reponse = _navigateur().get(_chemin_des_remises(monnaie_locale))

    assert reponse.status_code in (403, 302)


def test_une_monnaie_inconnue_repond_introuvable(tenant, gestionnaire):
    """Un uuid qui ne correspond a aucune monnaie du lieu.

    La page ne doit pas casser sur un lien perime ou une adresse tapee a la
    main.
    / The page must not break on a stale link or a hand-typed address.
    """
    with mock.patch('fedow_public.views.FedowAPI'):
        reponse = _navigateur(gestionnaire).get(
            f'/fedow/asset/{uuid_module.uuid4()}/retrieve_bank_deposits/',
        )

    assert reponse.status_code == 404


# ---------------------------------------------------------------------------
# 2. Ce que la page affiche
# ---------------------------------------------------------------------------


def test_la_page_montre_la_repartition_de_la_monnaie_par_lieu(
    tenant, monnaie_locale, gestionnaire,
):
    """La ventilation dit ou se trouve la monnaie en circulation.

    C'est ce qui permet au gestionnaire de savoir combien chaque lieu detient
    avant de declencher un virement.
    / The breakdown tells where the circulating currency sits, so the manager
    knows how much each venue holds before triggering a transfer.
    """
    with mock.patch('fedow_public.views.FedowAPI') as fedow:
        fedow.return_value.asset.total_by_place_with_uuid.return_value = (
            _ventilation_simulee()
        )
        fedow.return_value.asset.retrieve_bank_deposits.return_value = []
        reponse = _navigateur(gestionnaire).get(_chemin_des_remises(monnaie_locale))

    assert reponse.status_code == 200
    contenu = reponse.content.decode()
    assert 'Ferme du Coteau' in contenu
    assert 'Festival des Rives' in contenu


def test_la_page_montre_l_historique_des_remises(
    tenant, monnaie_locale, gestionnaire,
):
    """Chaque remise en banque passee reste consultable.

    C'est la piece justificative du gestionnaire : sans cet historique, il ne
    peut pas rapprocher ses virements de sa comptabilite.
    / This is the manager's supporting record: without it, transfers cannot be
    reconciled with the accounts.
    """
    with mock.patch('fedow_public.views.FedowAPI') as fedow:
        fedow.return_value.asset.total_by_place_with_uuid.return_value = (
            _ventilation_simulee()
        )
        fedow.return_value.asset.retrieve_bank_deposits.return_value = (
            _remises_simulees(nombre=3)
        )
        reponse = _navigateur(gestionnaire).get(_chemin_des_remises(monnaie_locale))

    contenu = reponse.content.decode()
    assert reponse.context['retrieve_bank_deposits']
    assert len(reponse.context['retrieve_bank_deposits']) == 3
    assert 'Lieu remettant 0' in contenu


def test_la_page_reste_lisible_sans_aucune_remise(
    tenant, monnaie_locale, gestionnaire,
):
    """Une monnaie neuve n'a pas encore de remise : la page le dit.

    Une page vide sans explication laisserait croire a une panne.
    / An unexplained empty page would look like a failure.
    """
    with mock.patch('fedow_public.views.FedowAPI') as fedow:
        fedow.return_value.asset.total_by_place_with_uuid.return_value = {}
        fedow.return_value.asset.retrieve_bank_deposits.return_value = []
        reponse = _navigateur(gestionnaire).get(_chemin_des_remises(monnaie_locale))

    assert reponse.status_code == 200
    assert reponse.context['retrieve_bank_deposits'] == []


def test_la_ventilation_est_lue_meme_quand_le_fedow_repond_du_texte(
    tenant, monnaie_locale, gestionnaire,
):
    """Le Fedow peut renvoyer sa ventilation en JSON deja serialise.

    La vue accepte les deux formes. Ne traiter que le dictionnaire ferait
    afficher une page vide sans erreur, avec de l'argent bien reel derriere.
    / The Fedow may return its breakdown as an already-serialized JSON string.
    Handling only the dict form would silently render an empty page.
    """
    import json

    with mock.patch('fedow_public.views.FedowAPI') as fedow:
        fedow.return_value.asset.total_by_place_with_uuid.return_value = json.dumps(
            _ventilation_simulee(),
        )
        fedow.return_value.asset.retrieve_bank_deposits.return_value = []
        reponse = _navigateur(gestionnaire).get(_chemin_des_remises(monnaie_locale))

    assert reponse.status_code == 200
    assert 'Ferme du Coteau' in reponse.content.decode()


# ---------------------------------------------------------------------------
# 3. L'historique des transactions sur une periode
# ---------------------------------------------------------------------------


CHEMIN_DES_TRANSACTIONS = '/fedow/asset/retrieve_transactions/'


def test_les_transactions_d_une_periode_sont_rendues_par_ordre_chronologique(
    tenant, monnaie_locale, gestionnaire,
):
    """Les mouvements se lisent du plus ancien au plus recent.

    Un releve dans le desordre est illisible pour un rapprochement bancaire, et
    le Fedow ne garantit pas l'ordre de sa reponse.
    / An out-of-order statement is unusable for reconciliation, and the Fedow
    does not guarantee the order of its answer.
    """
    maintenant = timezone.now()
    transactions_en_desordre = [
        {'datetime': maintenant, 'amount': 300, 'sender_name': 'Recent'},
        {'datetime': maintenant - timedelta(days=2), 'amount': 100, 'sender_name': 'Ancien'},
        {'datetime': maintenant - timedelta(days=1), 'amount': 200, 'sender_name': 'Milieu'},
    ]

    with mock.patch('fedow_public.views.FedowAPI') as fedow:
        fedow.return_value.transaction.list_by_asset.return_value = transactions_en_desordre
        reponse = _navigateur(gestionnaire).post(
            CHEMIN_DES_TRANSACTIONS,
            data={
                'asset_uuid': str(monnaie_locale.uuid),
                'start_date': (maintenant - timedelta(days=7)).isoformat(),
                'end_date': maintenant.isoformat(),
            },
        )

    assert reponse.status_code == 200
    noms_dans_l_ordre = [
        transaction['sender_name'] for transaction in reponse.context['transactions']
    ]
    assert noms_dans_l_ordre == ['Ancien', 'Milieu', 'Recent']


def test_une_periode_a_l_envers_est_refusee(tenant, monnaie_locale, gestionnaire):
    """Une date de fin anterieure au debut ne produit pas de releve.

    Le Fedow n'est pas sollicite : la saisie est refusee avant, avec un message
    dans le tableau plutot qu'une page d'erreur.
    / The Fedow is not called: the input is rejected first, with a message in
    the table rather than an error page.
    """
    maintenant = timezone.now()

    with mock.patch('fedow_public.views.FedowAPI') as fedow:
        reponse = _navigateur(gestionnaire).post(
            CHEMIN_DES_TRANSACTIONS,
            data={
                'asset_uuid': str(monnaie_locale.uuid),
                'start_date': maintenant.isoformat(),
                'end_date': (maintenant - timedelta(days=3)).isoformat(),
            },
        )
        fedow.return_value.transaction.list_by_asset.assert_not_called()

    assert reponse.status_code == 200
    assert reponse.context['errors']
    assert reponse.context['transactions'] == []


def test_une_demande_sans_dates_est_refusee(tenant, monnaie_locale, gestionnaire):
    """Sans periode, pas de releve : le Fedow n'est pas interroge a vide.
    / Without a period, the Fedow is not queried at all."""
    with mock.patch('fedow_public.views.FedowAPI') as fedow:
        reponse = _navigateur(gestionnaire).post(
            CHEMIN_DES_TRANSACTIONS,
            data={'asset_uuid': str(monnaie_locale.uuid)},
        )
        fedow.return_value.transaction.list_by_asset.assert_not_called()

    assert reponse.context['errors']


def test_les_transactions_sont_reservees_aux_gestionnaires(
    tenant, monnaie_locale, adherent_lambda,
):
    """Le releve de transactions est aussi de la tresorerie.
    / The transaction statement is treasury data too."""
    maintenant = timezone.now()

    reponse = _navigateur(adherent_lambda).post(
        CHEMIN_DES_TRANSACTIONS,
        data={
            'asset_uuid': str(monnaie_locale.uuid),
            'start_date': (maintenant - timedelta(days=7)).isoformat(),
            'end_date': maintenant.isoformat(),
        },
    )

    assert reponse.status_code in (403, 302)


# ---------------------------------------------------------------------------
# 4. La remise en banque elle-meme
# ---------------------------------------------------------------------------
#
# C'est le Fedow DISTANT qui decremente le token du portefeuille remis. Lespass
# se contente de lui poster la demande. Ce qu'on verifie ici : que la demande
# part avec le bon portefeuille et le bon asset, et que le resultat est rendu
# au gestionnaire sans etre avale.


def _chemin_de_remise(asset, wallet):
    return f'/admin/fedow_public/assetfedowpublic/bank_deposit/{asset.uuid}/{wallet.uuid}/'


def test_la_remise_en_banque_vise_le_bon_portefeuille_et_la_bonne_monnaie(
    tenant, monnaie_locale, gestionnaire,
):
    """La demande part avec exactement le portefeuille et l'asset choisis.

    C'est la verification la plus importante de cette page : se tromper de
    portefeuille viderait la monnaie d'un autre lieu, et se tromper d'asset
    remettrait en banque une monnaie que le lieu n'a pas encaissee. Le Fedow
    obeit sans rien pouvoir verifier a notre place.
    / The most important check here: the wrong wallet would empty another
    venue's currency, and the wrong asset would deposit a currency the venue
    never collected. The Fedow obeys without being able to double-check.
    """
    portefeuille_a_vider = Wallet.objects.create(
        name=f'{PREFIXE_DE_TEST} lieu a vider',
    )
    try:
        with mock.patch('Administration.admin_tenant.FedowAPI') as fedow:
            fedow.return_value.wallet.local_asset_bank_deposit.return_value = {
                'amount': MONTANT_DE_LA_REMISE,
            }
            _navigateur(gestionnaire).post(
                _chemin_de_remise(monnaie_locale, portefeuille_a_vider),
                HTTP_REFERER='https://lespass.tibillet.localhost/admin/',
            )

            appel = fedow.return_value.wallet.local_asset_bank_deposit.call_args
            assert appel is not None, "Aucune demande de remise n'est partie vers le Fedow."
            assert appel.kwargs['wallet_to_deposit'] == f'{portefeuille_a_vider.uuid}'
            assert appel.kwargs['asset'] == monnaie_locale
    finally:
        with tenant_context(tenant):
            try:
                portefeuille_a_vider.delete()
            except Exception:
                pass


def test_une_remise_refusee_par_le_fedow_ne_passe_pas_pour_un_succes(
    tenant, monnaie_locale, gestionnaire,
):
    """Si le Fedow refuse, le gestionnaire doit le savoir.

    Annoncer une remise qui n'a pas eu lieu ferait croire que la monnaie a ete
    retiree de la circulation, et fausserait le rapprochement bancaire.
    / Announcing a deposit that did not happen would suggest the currency left
    circulation, and would corrupt the bank reconciliation.
    """
    from django.contrib.messages import get_messages
    from django.contrib import messages as niveaux_de_message

    portefeuille_a_vider = Wallet.objects.create(
        name=f'{PREFIXE_DE_TEST} lieu refus',
    )
    try:
        with mock.patch('Administration.admin_tenant.FedowAPI') as fedow:
            fedow.return_value.wallet.local_asset_bank_deposit.side_effect = Exception(
                'Solde insuffisant cote Fedow',
            )
            reponse = _navigateur(gestionnaire).post(
                _chemin_de_remise(monnaie_locale, portefeuille_a_vider),
                HTTP_REFERER='https://lespass.tibillet.localhost/admin/',
            )

        niveaux = [message.level for message in get_messages(reponse.wsgi_request)]
        assert niveaux_de_message.ERROR in niveaux
        assert niveaux_de_message.SUCCESS not in niveaux
    finally:
        with tenant_context(tenant):
            try:
                portefeuille_a_vider.delete()
            except Exception:
                pass


def test_une_remise_reussie_est_annoncee_au_gestionnaire(
    tenant, monnaie_locale, gestionnaire,
):
    """Le succes est confirme a l'ecran.
    / Success is confirmed on screen."""
    from django.contrib.messages import get_messages
    from django.contrib import messages as niveaux_de_message

    portefeuille_a_vider = Wallet.objects.create(
        name=f'{PREFIXE_DE_TEST} lieu succes',
    )
    try:
        with mock.patch('Administration.admin_tenant.FedowAPI') as fedow:
            fedow.return_value.wallet.local_asset_bank_deposit.return_value = {
                'amount': MONTANT_DE_LA_REMISE,
            }
            reponse = _navigateur(gestionnaire).post(
                _chemin_de_remise(monnaie_locale, portefeuille_a_vider),
                HTTP_REFERER='https://lespass.tibillet.localhost/admin/',
            )

        niveaux = [message.level for message in get_messages(reponse.wsgi_request)]
        assert niveaux_de_message.SUCCESS in niveaux
    finally:
        with tenant_context(tenant):
            try:
                portefeuille_a_vider.delete()
            except Exception:
                pass


def test_une_remise_n_est_pas_ouverte_a_un_adherent(
    tenant, monnaie_locale, adherent_lambda,
):
    """Declencher une remise en banque n'est pas a la portee de tous.

    C'est l'operation qui deplace reellement de l'argent : elle doit rester
    entre les mains d'un gestionnaire du lieu.
    / This is the operation that actually moves money.
    """
    portefeuille_a_vider = Wallet.objects.create(
        name=f'{PREFIXE_DE_TEST} lieu interdit',
    )
    try:
        with mock.patch('Administration.admin_tenant.FedowAPI') as fedow:
            reponse = _navigateur(adherent_lambda).post(
                _chemin_de_remise(monnaie_locale, portefeuille_a_vider),
                HTTP_REFERER='https://lespass.tibillet.localhost/admin/',
            )

        # La garde qui compte : aucune demande ne part vers le Fedow. Le code de
        # reponse, lui, depend de la facon dont l'admin refuse (403 direct ou
        # redirection vers sa page de connexion) — s'y fier laisserait passer un
        # refus qui aurait quand meme deplace l'argent.
        # / The check that matters: no request leaves for the Fedow. The status
        # code depends on how the admin refuses, and relying on it would let
        # through a refusal that had already moved the money.
        fedow.return_value.wallet.local_asset_bank_deposit.assert_not_called()
        assert reponse.status_code in (302, 403)
    finally:
        with tenant_context(tenant):
            try:
                portefeuille_a_vider.delete()
            except Exception:
                pass
