"""
tests/pytest/test_parcours_vente_fed_et_remise_en_banque.py
Le parcours complet : vendre en monnaie federee, puis remettre en banque.
/ The full journey: sell in federated currency, then deposit to the bank.

LOCALISATION : tests/pytest/test_parcours_vente_fed_et_remise_en_banque.py

CE QUI EST TESTE / WHAT IS TESTED
---------------------------------
Les fichiers voisins testent chaque etape ISOLEMENT, chacun avec son propre
Fedow simule. Une vente y est encaissee sans que rien ne la relie au depot
bancaire teste ailleurs : on verifie des morceaux, jamais la chaine.

Ce fichier verifie la CHAINE :

    l'adherent paie 12,50 € en monnaie federee par QR code
      → le lieu detient 12,50 € de plus
        → le gestionnaire le voit dans la ventilation par lieu
          → il declenche la remise en banque
            → le lieu ne detient plus rien
              → la remise apparait dans l'historique

/ The neighbouring files test each step in ISOLATION, each with its own mocked
Fedow. This one tests the CHAIN.

POURQUOI UN FEDOW A ETAT / WHY A STATEFUL FEDOW
------------------------------------------------
Un `MagicMock` renvoie ce qu'on lui dicte, sans memoire : avec lui, « le solde
vaut 0 apres la remise » ne prouve rien, puisque c'est le test qui l'a decide.

`FedowSimule` ci-dessous tient un vrai etat — soldes, transactions, remises — et
le fait evoluer comme le ferait le Fedow distant. Le test ne dicte que le point
de depart ; tout le reste decoule des appels que Lespass emet. Si Lespass oublie
de demander la remise, ou la demande sur le mauvais portefeuille, le solde final
ne tombe pas juste.

/ A MagicMock has no memory: "the balance is 0 after the deposit" would prove
nothing, since the test decided it. FedowSimule holds real state and evolves it
as the remote Fedow would. Only the starting point is dictated.

CE QUE CE FICHIER NE PROUVE PAS / WHAT IT DOES NOT PROVE
---------------------------------------------------------
Que le vrai Fedow se comporte comme `FedowSimule`. Il prouve que Lespass emet
les bons appels, dans le bon ordre, et rend compte fidelement de ce qu'on lui
repond.

Lancement / Run:
    docker exec lespass_django poetry run pytest \
        /DjangoFiles/tests/pytest/test_parcours_vente_fed_et_remise_en_banque.py -v
"""

import uuid as uuid_module
from datetime import timedelta
from unittest import mock

import pytest
from django.contrib import messages as niveaux_de_message
from django.contrib.messages import get_messages
from django.test import Client as DjangoClient
from django.utils import timezone
from django_tenants.utils import tenant_context

from AuthBillet.models import TibilletUser, Wallet
from BaseBillet.models import LigneArticle, PaymentMethod, SaleOrigin
from Customers.models import Client as TenantClient
from fedow_public.models import AssetFedowPublic

pytestmark = pytest.mark.django_db

PREFIXE_DE_TEST = 'TEST_parcours'

MONTANT_DE_LA_VENTE = 1250
SOLDE_INITIAL_DE_L_ADHERENT = 5000


# ---------------------------------------------------------------------------
# Le Fedow simule
# ---------------------------------------------------------------------------


class FedowSimule:
    """Un Fedow distant qui se souvient de ce qu'on lui a demande.

    Il n'imite pas tout le Fedow : seulement les quelques operations que ce
    parcours emprunte, avec la comptabilite minimale qui les relie entre elles —
    ce qu'un adherent detient, ce qu'un lieu a encaisse, ce qui a ete remis.
    / It mimics only the operations this journey uses, with the minimal
    bookkeeping that ties them together.
    """

    def __init__(self, solde_de_l_adherent, uuid_de_l_asset, nom_du_lieu):
        self.solde_de_l_adherent = solde_de_l_adherent
        self.uuid_de_l_asset = str(uuid_de_l_asset)
        self.nom_du_lieu = nom_du_lieu

        # Ce que le lieu a encaisse et pas encore remis en banque.
        # / What the venue collected and has not yet deposited.
        self.encaisse_par_le_lieu = 0
        self.remises_en_banque = []

        # Pour verifier ce que Lespass a demande, et non seulement le resultat.
        # / To check what Lespass asked for, not just the outcome.
        self.portefeuilles_remis = []

        self.wallet = _PortefeuilleSimule(self)
        self.transaction = _TransactionsSimulees(self)
        self.asset = _AssetsSimules(self)


class _PortefeuilleSimule:
    def __init__(self, fedow):
        self.fedow = fedow

    def get_or_create_wallet(self, user):
        """Le portefeuille de l'adherent, cree a la volee s'il n'en a pas.
        / The member's wallet, created on the fly if missing."""
        if user.wallet is None:
            user.wallet = Wallet.objects.create(name=f'Wallet {user.email}')
            user.save()
        return user.wallet, False

    def get_total_fiducial_and_all_federated_token(self, user, use_cache=True):
        """Ce que l'adherent peut depenser ici.
        / What the member can spend here."""
        return self.fedow.solde_de_l_adherent

    def local_asset_bank_deposit(self, user=None, wallet_to_deposit=None, asset=None):
        """Vide le portefeuille remis et enregistre la remise.

        C'est ce que fait le Fedow distant : il decremente, puis renvoie la
        transaction creee.
        / What the remote Fedow does: decrement, then return the transaction.
        """
        self.fedow.portefeuilles_remis.append(str(wallet_to_deposit))

        montant_remis = self.fedow.encaisse_par_le_lieu
        if montant_remis <= 0:
            raise Exception("Rien a remettre en banque sur ce portefeuille.")

        self.fedow.encaisse_par_le_lieu = 0
        self.fedow.remises_en_banque.append({
            'datetime': timezone.now(),
            'amount': montant_remis,
            'sender_name': self.fedow.nom_du_lieu,
        })
        return {'amount': montant_remis}


class _TransactionsSimulees:
    def __init__(self, fedow):
        self.fedow = fedow

    def to_place_from_qrcode(self, metadata=None, amount=None, asset_type=None, user=None):
        """Debite l'adherent et credite le lieu.
        / Debits the member and credits the venue."""
        if amount > self.fedow.solde_de_l_adherent:
            raise Exception("Solde insuffisant cote Fedow.")

        self.fedow.solde_de_l_adherent -= amount
        self.fedow.encaisse_par_le_lieu += amount
        return [{'asset': self.fedow.uuid_de_l_asset, 'amount': amount}]

    def list_by_asset(self, asset=None, user=None, start_date=None, end_date=None):
        return list(self.fedow.remises_en_banque)


class _AssetsSimules:
    def __init__(self, fedow):
        self.fedow = fedow

    def retrieve(self, uuid_asset):
        """La monnaie federee du reseau. / The network's federated currency."""
        return {'category': 'FED'}

    def total_by_place_with_uuid(self, uuid=None):
        """Ou se trouve la monnaie en circulation, a l'instant present.
        / Where the circulating currency sits right now."""
        return {
            'total_by_place': [
                {
                    'place_name': self.fedow.nom_du_lieu,
                    'total_value': self.fedow.encaisse_par_le_lieu,
                },
            ],
        }

    def retrieve_bank_deposits(self, asset=None):
        return list(self.fedow.remises_en_banque)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tenant():
    return TenantClient.objects.get(schema_name='lespass')


@pytest.fixture
def monnaie_federee(tenant):
    """Le miroir local de la monnaie federee du reseau.

    Une contrainte de base n'autorise qu'UN SEUL asset de categorie FED dans
    tout le systeme (`unique_primary_asset`) : la monnaie federee est unique par
    definition. On reutilise donc celui qui existe, et on n'en cree un que s'il
    n'y en a aucun — auquel cas on le retire ensuite.
    / A DB constraint allows only ONE FED asset system-wide: the federated
    currency is unique by definition. Reuse the existing one; create it only if
    absent, and remove it afterwards in that case.

    Le Fedow etant simule dans ce fichier, reutiliser l'asset reel ne touche
    aucune donnee distante : ce miroir ne sert qu'a resoudre les URL.
    / The Fedow is simulated here, so reusing the real asset touches no remote
    data: this mirror only serves to resolve the URLs.
    """
    asset_existant = AssetFedowPublic.objects.filter(
        category=AssetFedowPublic.STRIPE_FED_FIAT,
    ).first()
    if asset_existant is not None:
        yield asset_existant
        return

    portefeuille_origine = Wallet.objects.create(name=f'{PREFIXE_DE_TEST} origine')
    asset = AssetFedowPublic.objects.create(
        uuid=uuid_module.uuid4(),
        name=f'{PREFIXE_DE_TEST} TiBillet federe',
        currency_code='EUR',
        category=AssetFedowPublic.STRIPE_FED_FIAT,
        origin=tenant,
        wallet_origin=portefeuille_origine,
    )
    yield asset
    with tenant_context(tenant):
        AssetFedowPublic.objects.filter(pk=asset.pk).delete()
        try:
            portefeuille_origine.delete()
        except Exception:
            pass


@pytest.fixture
def portefeuille_du_lieu(tenant):
    """Le portefeuille qui encaisse, et qu'on remettra en banque.
    / The wallet that collects, and that will be deposited."""
    wallet = Wallet.objects.create(name=f'{PREFIXE_DE_TEST} lieu')
    yield wallet
    with tenant_context(tenant):
        try:
            wallet.delete()
        except Exception:
            pass


@pytest.fixture
def encaisseur(tenant):
    """Le membre habilite : il genere les QR codes ET gere le lieu.
    / The authorized member: generates QR codes AND manages the venue."""
    adresse = f'parcours-encaisseur-{uuid_module.uuid4().hex[:8]}@tibillet.localhost'
    with tenant_context(tenant):
        utilisateur = TibilletUser.objects.create(
            email=adresse, username=adresse, is_active=True, email_valid=True,
        )
        utilisateur.client_admin.add(tenant)
        utilisateur.initiate_payment.add(tenant)
    yield utilisateur
    with tenant_context(tenant):
        LigneArticle.objects.filter(metadata__icontains=adresse).delete()
        utilisateur.delete()


@pytest.fixture
def adherent(tenant):
    """Celui qui paie, avec un portefeuille approvisionne.
    / The payer, with a funded wallet."""
    adresse = f'parcours-adherent-{uuid_module.uuid4().hex[:8]}@tibillet.localhost'
    with tenant_context(tenant):
        utilisateur = TibilletUser.objects.create(
            email=adresse, username=adresse, is_active=True, email_valid=True,
        )
        utilisateur.wallet = Wallet.objects.create(name=f'{PREFIXE_DE_TEST} {adresse}')
        utilisateur.save()
    yield utilisateur
    with tenant_context(tenant):
        portefeuille = utilisateur.wallet
        LigneArticle.objects.filter(wallet=portefeuille).delete()
        utilisateur.delete()
        try:
            portefeuille.delete()
        except Exception:
            pass


@pytest.fixture
def nettoyer_les_ventes(tenant):
    """Retire les ventes du parcours, avant et apres.
    / Removes this journey's sales, before and after."""
    def _purger():
        with tenant_context(tenant):
            LigneArticle.objects.filter(
                sale_origin__in=[SaleOrigin.QRCODE_MA, SaleOrigin.NFC_MA],
                payment_method__in=[PaymentMethod.QRCODE_MA, PaymentMethod.STRIPE_FED],
            ).delete()

    _purger()
    yield
    _purger()


def _navigateur(utilisateur=None):
    client = DjangoClient(HTTP_HOST='lespass.tibillet.localhost')
    if utilisateur is not None:
        client.force_login(utilisateur)
    return client


def _patcher_tout_le_fedow(fedow_simule):
    """Branche le Fedow simule sur les TROIS points ou Lespass l'instancie.

    Les vues ne partagent pas le meme import : la vente l'importe dans sa
    methode (`fedow_connect.fedow_api`), la page des remises au niveau du module
    (`fedow_public.views`), et l'admin de meme (`Administration.admin_tenant`).
    N'en patcher qu'un laisserait une etape parler a un autre Fedow, et la
    chaine ne serait plus une chaine.
    / The views do not share the same import. Patching only one would let a step
    talk to a different Fedow, breaking the chain.
    """
    return [
        mock.patch('fedow_connect.fedow_api.FedowAPI', return_value=fedow_simule),
        mock.patch('fedow_public.views.FedowAPI', return_value=fedow_simule),
        mock.patch('Administration.admin_tenant.FedowAPI', return_value=fedow_simule),
    ]


# ---------------------------------------------------------------------------
# A. Le parcours complet
# ---------------------------------------------------------------------------


def test_une_vente_federee_puis_sa_remise_en_banque(
    tenant, monnaie_federee, portefeuille_du_lieu, encaisseur, adherent,
    nettoyer_les_ventes,
):
    """Le parcours entier, d'un bout a l'autre.

    Chaque etape part de l'etat laisse par la precedente. Aucune valeur n'est
    dictee en cours de route : seul le solde de depart l'est.
    / Every step starts from the state the previous one left. Only the starting
    balance is dictated.
    """
    fedow = FedowSimule(
        solde_de_l_adherent=SOLDE_INITIAL_DE_L_ADHERENT,
        uuid_de_l_asset=monnaie_federee.uuid,
        nom_du_lieu='Le Tiers Lustre',
    )
    patchs = _patcher_tout_le_fedow(fedow)
    for patch in patchs:
        patch.start()
    try:
        navigateur_encaisseur = _navigateur(encaisseur)

        # --- 1. L'encaisseur genere un QR code de 12,50 € ---
        reponse = navigateur_encaisseur.post(
            '/qrcodescanpay/generate_qrcode/',
            data={'amount': str(MONTANT_DE_LA_VENTE / 100), 'asset_type': 'EURO'},
        )
        assert reponse.status_code == 200

        with tenant_context(tenant):
            ligne_en_attente = LigneArticle.objects.filter(
                sale_origin=SaleOrigin.QRCODE_MA,
                status=LigneArticle.CREATED,
            ).order_by('-datetime').first()
        assert ligne_en_attente is not None, "Le QR code n'a produit aucune demande."

        # --- 2. L'adherent scanne et confirme ---
        reponse = _navigateur(adherent).post(
            '/qrcodescanpay/valid_payment/',
            data={'ligne_article_uuid_hex': ligne_en_attente.uuid.hex},
        )
        assert reponse.status_code == 200

        # La vente est enregistree en monnaie federee.
        # / The sale is recorded in federated currency.
        with tenant_context(tenant):
            vente = LigneArticle.objects.filter(
                sale_origin=SaleOrigin.QRCODE_MA,
                status=LigneArticle.VALID,
            ).first()
        assert vente is not None, "Le paiement n'a laisse aucune vente."
        assert vente.amount == MONTANT_DE_LA_VENTE
        assert vente.payment_method == PaymentMethod.STRIPE_FED

        # Cote Fedow, l'adherent a ete debite et le lieu credite.
        # / On the Fedow side, the member was debited and the venue credited.
        assert fedow.solde_de_l_adherent == SOLDE_INITIAL_DE_L_ADHERENT - MONTANT_DE_LA_VENTE
        assert fedow.encaisse_par_le_lieu == MONTANT_DE_LA_VENTE

        # --- 3. Le gestionnaire consulte la ventilation ---
        reponse = navigateur_encaisseur.get(
            f'/fedow/asset/{monnaie_federee.uuid}/retrieve_bank_deposits/',
        )
        assert reponse.status_code == 200
        contenu_avant_remise = reponse.content.decode()
        assert 'Le Tiers Lustre' in contenu_avant_remise
        # 12,50 € affiche en euros par le filtre du gabarit.
        # / 12.50 € displayed in euros by the template filter.
        assert '12.5' in contenu_avant_remise or '12,5' in contenu_avant_remise
        assert reponse.context['retrieve_bank_deposits'] == []

        # --- 4. Il declenche la remise en banque ---
        reponse = navigateur_encaisseur.post(
            f'/admin/fedow_public/assetfedowpublic/bank_deposit/'
            f'{monnaie_federee.uuid}/{portefeuille_du_lieu.uuid}/',
            HTTP_REFERER='https://lespass.tibillet.localhost/admin/',
        )
        niveaux = [message.level for message in get_messages(reponse.wsgi_request)]
        assert niveaux_de_message.SUCCESS in niveaux
        assert niveaux_de_message.ERROR not in niveaux

        # La demande est bien partie sur le portefeuille du lieu.
        # / The request did target the venue's wallet.
        assert fedow.portefeuilles_remis == [str(portefeuille_du_lieu.uuid)]

        # Le Fedow a decremente : le lieu ne detient plus rien.
        # / The Fedow decremented: the venue holds nothing anymore.
        assert fedow.encaisse_par_le_lieu == 0

        # --- 5. La page rend compte de la remise ---
        reponse = navigateur_encaisseur.get(
            f'/fedow/asset/{monnaie_federee.uuid}/retrieve_bank_deposits/',
        )
        contenu_apres_remise = reponse.content.decode()

        remises_affichees = reponse.context['retrieve_bank_deposits']
        assert len(remises_affichees) == 1
        assert remises_affichees[0]['amount'] == MONTANT_DE_LA_VENTE
        assert 'Le Tiers Lustre' in contenu_apres_remise
        # Le montant remis apparait dans l'historique.
        # / The deposited amount appears in the history.
        assert '12.5' in contenu_apres_remise or '12,5' in contenu_apres_remise
    finally:
        for patch in patchs:
            patch.stop()


def test_une_seconde_remise_sans_nouvelle_vente_est_refusee(
    tenant, monnaie_federee, portefeuille_du_lieu, encaisseur, adherent,
    nettoyer_les_ventes,
):
    """Remettre deux fois de suite ne cree pas d'argent.

    Apres une remise, le portefeuille du lieu est vide. Une seconde demande
    n'a rien a remettre : elle doit echouer, et surtout ne pas etre annoncee
    comme un succes au gestionnaire.
    / After a deposit the venue's wallet is empty. A second request has nothing
    to deposit and must not be announced as a success.
    """
    fedow = FedowSimule(
        solde_de_l_adherent=SOLDE_INITIAL_DE_L_ADHERENT,
        uuid_de_l_asset=monnaie_federee.uuid,
        nom_du_lieu='Le Tiers Lustre',
    )
    patchs = _patcher_tout_le_fedow(fedow)
    for patch in patchs:
        patch.start()
    try:
        navigateur_encaisseur = _navigateur(encaisseur)
        chemin_de_remise = (
            f'/admin/fedow_public/assetfedowpublic/bank_deposit/'
            f'{monnaie_federee.uuid}/{portefeuille_du_lieu.uuid}/'
        )

        # Une vente, puis une premiere remise.
        navigateur_encaisseur.post(
            '/qrcodescanpay/generate_qrcode/',
            data={'amount': str(MONTANT_DE_LA_VENTE / 100), 'asset_type': 'EURO'},
        )
        with tenant_context(tenant):
            ligne = LigneArticle.objects.filter(
                sale_origin=SaleOrigin.QRCODE_MA, status=LigneArticle.CREATED,
            ).order_by('-datetime').first()
        _navigateur(adherent).post(
            '/qrcodescanpay/valid_payment/',
            data={'ligne_article_uuid_hex': ligne.uuid.hex},
        )
        navigateur_encaisseur.post(
            chemin_de_remise, HTTP_REFERER='https://lespass.tibillet.localhost/admin/',
        )

        # Seconde remise, sans nouvelle vente entre les deux.
        #
        # Session neuve : les messages django s'empilent tant que personne ne les
        # affiche, et le succes de la premiere remise serait encore la. Avec une
        # session vierge, les seuls messages lus sont ceux de CETTE demande.
        # / A fresh session: django messages pile up until displayed, so the
        # first deposit's success would still be there.
        reponse = _navigateur(encaisseur).post(
            chemin_de_remise, HTTP_REFERER='https://lespass.tibillet.localhost/admin/',
        )

        niveaux = [message.level for message in get_messages(reponse.wsgi_request)]
        assert niveaux_de_message.ERROR in niveaux
        assert niveaux_de_message.SUCCESS not in niveaux
        assert len(fedow.remises_en_banque) == 1
    finally:
        for patch in patchs:
            patch.stop()


# ---------------------------------------------------------------------------
# B. Quand le Fedow ne repond plus
# ---------------------------------------------------------------------------
#
# Le Fedow est un service distant : il tombe, le reseau se coupe, la reponse
# tarde. Ces vues manipulent de l'argent ; leur comportement en panne doit etre
# connu, meme quand il n'est pas satisfaisant.


class _FedowEnPanne:
    """Un Fedow qui leve sur tout appel. / A Fedow raising on every call."""

    def __getattr__(self, nom):
        raise ConnectionError("Fedow injoignable")


def _fedow_dont_toutes_les_methodes_echouent():
    faux_fedow = mock.MagicMock()
    for chemin in [
        'asset.total_by_place_with_uuid',
        'asset.retrieve_bank_deposits',
        'transaction.list_by_asset',
        'wallet.local_asset_bank_deposit',
        'wallet.get_total_fiducial_and_all_federated_token',
        'wallet.get_or_create_wallet',
    ]:
        objet = faux_fedow
        *intermediaires, dernier = chemin.split('.')
        for morceau in intermediaires:
            objet = getattr(objet, morceau)
        getattr(objet, dernier).side_effect = ConnectionError("Fedow injoignable")
    return faux_fedow


def test_une_remise_en_banque_pendant_une_panne_fedow_est_annoncee_comme_echouee(
    tenant, monnaie_federee, portefeuille_du_lieu, encaisseur,
):
    """Le gestionnaire doit savoir que sa remise n'est pas partie.

    C'est le comportement le plus important en panne : ne surtout pas laisser
    croire que l'argent a ete remis. La vue attrape l'erreur et affiche un
    message.
    / The most important behaviour under failure: never suggest the money was
    deposited.
    """
    with mock.patch(
        'Administration.admin_tenant.FedowAPI',
        return_value=_fedow_dont_toutes_les_methodes_echouent(),
    ):
        reponse = _navigateur(encaisseur).post(
            f'/admin/fedow_public/assetfedowpublic/bank_deposit/'
            f'{monnaie_federee.uuid}/{portefeuille_du_lieu.uuid}/',
            HTTP_REFERER='https://lespass.tibillet.localhost/admin/',
        )

    niveaux = [message.level for message in get_messages(reponse.wsgi_request)]
    assert niveaux_de_message.ERROR in niveaux
    assert niveaux_de_message.SUCCESS not in niveaux


def test_la_page_des_remises_pendant_une_panne_fedow(
    tenant, monnaie_federee, encaisseur,
):
    """Comportement constate : la page ne survit pas a une panne du Fedow.

    `retrieve_bank_deposits` (vue) n'encadre aucun de ses deux appels distants.
    Une panne du Fedow y produit donc une erreur, la ou `tokens_table` du compte
    adherent, elle, se degrade en affichant ce qu'elle sait.

    Ce test DECRIT l'etat actuel. Il echouera le jour ou une garde sera posee :
    ce sera le signal de verifier ce que la page affiche alors au gestionnaire.

    / Observed behaviour: the page does not survive a Fedow outage, unlike the
    member's token table which degrades gracefully. This test DESCRIBES the
    current state and will fail once a guard is added.
    """
    with mock.patch(
        'fedow_public.views.FedowAPI',
        return_value=_fedow_dont_toutes_les_methodes_echouent(),
    ):
        with pytest.raises(ConnectionError):
            _navigateur(encaisseur).get(
                f'/fedow/asset/{monnaie_federee.uuid}/retrieve_bank_deposits/',
            )


def test_le_releve_de_transactions_pendant_une_panne_fedow(
    tenant, monnaie_federee, encaisseur,
):
    """Meme constat pour le releve de transactions.
    / Same observation for the transaction statement."""
    maintenant = timezone.now()

    with mock.patch(
        'fedow_public.views.FedowAPI',
        return_value=_fedow_dont_toutes_les_methodes_echouent(),
    ):
        with pytest.raises(ConnectionError):
            _navigateur(encaisseur).post(
                '/fedow/asset/retrieve_transactions/',
                data={
                    'asset_uuid': str(monnaie_federee.uuid),
                    'start_date': (maintenant - timedelta(days=7)).isoformat(),
                    'end_date': maintenant.isoformat(),
                },
            )


def test_un_paiement_par_qrcode_pendant_une_panne_fedow_ne_cree_pas_de_vente(
    tenant, encaisseur, adherent, nettoyer_les_ventes,
):
    """Si le Fedow tombe pendant le paiement, aucune vente n'est enregistree.

    C'est la garde qui compte : ne jamais enregistrer une vente que le Fedow
    n'a pas pu encaisser. L'inverse creerait de la recette sans contrepartie.
    / Never record a sale the Fedow could not collect: the opposite would create
    revenue with no counterpart.
    """
    fedow_qui_repond_puis_tombe = mock.MagicMock()
    fedow_qui_repond_puis_tombe.wallet.get_or_create_wallet.return_value = (
        adherent.wallet, False,
    )
    fedow_qui_repond_puis_tombe.wallet.get_total_fiducial_and_all_federated_token.return_value = (
        SOLDE_INITIAL_DE_L_ADHERENT
    )
    # Le solde est lisible, mais la transaction echoue.
    # / The balance reads fine, but the transaction fails.
    fedow_qui_repond_puis_tombe.transaction.to_place_from_qrcode.side_effect = (
        ConnectionError("Fedow injoignable")
    )

    with mock.patch(
        'fedow_connect.fedow_api.FedowAPI',
        return_value=fedow_qui_repond_puis_tombe,
    ):
        _navigateur(encaisseur).post(
            '/qrcodescanpay/generate_qrcode/',
            data={'amount': str(MONTANT_DE_LA_VENTE / 100), 'asset_type': 'EURO'},
        )
        with tenant_context(tenant):
            ligne = LigneArticle.objects.filter(
                sale_origin=SaleOrigin.QRCODE_MA, status=LigneArticle.CREATED,
            ).order_by('-datetime').first()

        _navigateur(adherent).post(
            '/qrcodescanpay/valid_payment/',
            data={'ligne_article_uuid_hex': ligne.uuid.hex},
        )

    # On interroge CETTE demande-la, et non l'ensemble des ventes par QR code du
    # tenant : la base de developpement en porte d'autres, laissees par les tests
    # de bout en bout qui tournent contre le vrai Fedow. Un comptage global ferait
    # echouer ce test pour des ventes qui ne le concernent pas.
    # / We query THIS request, not every QR code sale of the tenant: the dev
    # database holds others, left by the end-to-end tests running against the
    # real Fedow. A global count would fail on sales unrelated to this test.
    with tenant_context(tenant):
        assert not LigneArticle.objects.filter(
            uuid=ligne.uuid, status=LigneArticle.VALID,
        ).exists(), (
            "Le paiement a ete enregistre alors que le Fedow n'a pas pu encaisser."
        )
