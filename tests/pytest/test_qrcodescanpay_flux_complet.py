"""
tests/pytest/test_qrcodescanpay_flux_complet.py
Payer par QR code depuis « Ma tirelire » : generation et paiement.
/ Paying by QR code from the wallet page: generation and payment.

LOCALISATION : tests/pytest/test_qrcodescanpay_flux_complet.py

CE QUI EST TESTE / WHAT IS TESTED
---------------------------------
Le parcours complet, en trois routes :

1. `POST /qrcodescanpay/generate_qrcode/` — un membre habilite saisit un montant.
   Une `LigneArticle` est creee en attente, et son uuid devient le contenu du QR.
2. `GET /qrcodescanpay/<uuid_hex>/process_qrcode/` — l'adherent scanne. On lit son
   solde sur le Fedow et on lui montre l'ecran de validation, ou celui de fonds
   insuffisants.
3. `POST /qrcodescanpay/valid_payment/` — il confirme. La ligne en attente est
   **remplacee** par une ligne validee par transaction Fedow, dans une vente
   encaissee (le detail de la vente : tests/pytest/test_qrcode_ecrit_la_vente.py).

`tests/pytest/test_qrcodescanpay_permissions.py` couvre QUI a le droit d'ouvrir
ces ecrans. Ce fichier-ci couvre ce qui s'y passe.

/ The full journey in three routes: generate, scan, confirm. The permissions file
covers WHO may open these screens; this one covers what happens inside.

LES CAS D'UTILISATEUR / THE USER CASES
---------------------------------------
Le solde depensable vient du Fedow distant, et depend de trois choses
independantes : l'utilisateur a-t-il un portefeuille, porte-t-il de la monnaie
federee, et le Fedow repond-il ? Chaque combinaison mene a un ecran different, et
c'est ce qui est verifie ici.

FEDOW EST MOCKE / FEDOW IS MOCKED
----------------------------------
Ces vues parlent au Fedow distant par le reseau. Les vues l'importent
LOCALEMENT (`from fedow_connect.fedow_api import FedowAPI` a l'interieur de la
methode), donc le patch vise `fedow_connect.fedow_api.FedowAPI` et non un
attribut de `BaseBillet.views`.
/ The views import FedowAPI locally inside the method, so the patch targets
fedow_connect.fedow_api.FedowAPI, not an attribute of BaseBillet.views.

Lancement / Run:
    docker exec lespass_django poetry run pytest \
        /DjangoFiles/tests/pytest/test_qrcodescanpay_flux_complet.py -v
"""

import sys

# Le code Django vit dans /DjangoFiles a l'interieur du conteneur.
# / Django code lives in /DjangoFiles inside the container.
sys.path.insert(0, '/DjangoFiles')

import django  # noqa: E402

django.setup()

import json  # noqa: E402
import uuid as uuid_module  # noqa: E402
from decimal import Decimal  # noqa: E402
from unittest import mock  # noqa: E402

from django_tenants.test.cases import FastTenantTestCase  # noqa: E402
from django_tenants.test.client import TenantClient  # noqa: E402

from AuthBillet.models import TibilletUser, Wallet  # noqa: E402
from BaseBillet.models import (  # noqa: E402
    LigneArticle, PaymentMethod, SaleOrigin,
)
from BaseBillet.services_vente import (  # noqa: E402
    NOM_ECART_RECU_EN_MOINS, NOM_ECART_RECU_EN_PLUS,
)

# Montant du paiement demande, en centimes. Choisi pour qu'aucun solde de test
# ne tombe dessus par hasard.
# / Requested payment amount in cents, chosen so no test balance matches it.
MONTANT_DEMANDE_CENTIMES = 1250

CHEMIN_GENERATION = '/qrcodescanpay/generate_qrcode/'
CHEMIN_VALIDATION = '/qrcodescanpay/valid_payment/'


def _chemin_de_scan(uuid_hex):
    """L'URL que porte le QR code. / The URL carried by the QR code."""
    return f'/qrcodescanpay/{uuid_hex}/process_qrcode/'


class TestPayerParQrCode(FastTenantTestCase):
    """Generation, scan et confirmation, sur un schema isole.
    / Generation, scan and confirmation, on an isolated schema."""

    @classmethod
    def get_test_schema_name(cls):
        return 'test_qrcode_flux'

    @classmethod
    def get_test_tenant_domain(cls):
        return 'test-qrcode-flux.tibillet.localhost'

    @classmethod
    def setup_tenant(cls, tenant):
        """`Client.name` est unique et obligatoire. / Client.name is unique."""
        tenant.name = 'Test QR code'

    def setUp(self):
        """Un encaisseur habilite, un payeur, et un client HTTP pour chacun.
        / One authorized collector, one payer, and an HTTP client for each."""
        from django.db import connection

        from laboutik.models import LaboutikConfiguration

        # Le rollback du test precedent a rendu le `search_path` au public.
        # / The previous test's rollback returned the search_path to public.
        connection.set_tenant(self.tenant)

        # Un paiement reussi encaisse une vente : le singleton de la caisse doit
        # exister en base, il porte la cle de l'empreinte des ventes (PIEGES 9.86).
        # / A successful payment settles a sale: the register singleton must exist
        # in the database, it holds the sales HMAC key.
        LaboutikConfiguration.get_solo().save()

        self.encaisseur = self._creer_utilisateur('encaisseur-qr')
        # Le droit `initiate_payment` est ce qui distingue celui qui ENCAISSE de
        # celui qui PAIE. Sans lui, la generation renvoie 403.
        # / The initiate_payment right distinguishes the collector from the payer.
        self.encaisseur.initiate_payment.add(self.tenant)

        self.navigateur_encaisseur = TenantClient(self.tenant)
        self.navigateur_encaisseur.force_login(self.encaisseur)

    # ------------------------------------------------------------------
    # Utilitaires
    # ------------------------------------------------------------------

    def _creer_utilisateur(self, prefixe, email_valide=True, avec_wallet=False):
        """Un utilisateur jetable, avec ou sans portefeuille local.

        `TibilletUser` vit en SHARED_APPS : l'adresse porte un suffixe unique
        pour ne pas heurter un compte laisse par un autre schema de test.
        / TibilletUser lives in SHARED_APPS: the address carries a unique suffix.
        """
        adresse = f'{prefixe}-{uuid_module.uuid4().hex[:8]}@tibillet.localhost'
        utilisateur = TibilletUser.objects.create(
            email=adresse,
            username=adresse,
            is_active=True,
            email_valid=email_valide,
        )
        if avec_wallet:
            utilisateur.wallet = Wallet.objects.create(name=f'Wallet {adresse}')
            utilisateur.save()
        return utilisateur

    def _navigateur_de(self, utilisateur):
        """Un client HTTP connecte sous cette identite.
        / An HTTP client logged in as this identity."""
        navigateur = TenantClient(self.tenant)
        navigateur.force_login(utilisateur)
        return navigateur

    def _generer_un_qrcode(self, montant_centimes=MONTANT_DEMANDE_CENTIMES):
        """Fait generer un QR code par l'encaisseur, rend la ligne en attente.
        / Has the collector generate a QR code, returns the pending line."""
        reponse = self.navigateur_encaisseur.post(
            CHEMIN_GENERATION,
            data={
                'amount': str(montant_centimes / 100),
                'asset_type': 'EUR',
            },
        )
        assert reponse.status_code == 200, reponse.content.decode()[:400]

        ligne = LigneArticle.objects.filter(
            sale_origin=SaleOrigin.QRCODE_MA,
        ).order_by('-datetime').first()
        assert ligne is not None, "La generation n'a produit aucune ligne."
        return ligne

    def _fedow_qui_repond(self, solde_centimes, transactions=None, categorie_asset='FED'):
        """Un Fedow distant simule, avec le solde qu'on lui dicte.

        `get_total_fiducial_and_all_federated_token` est ce qui decide entre
        l'ecran de validation et celui de fonds insuffisants.
        / The mocked remote Fedow. Its balance decides between the validation
        screen and the insufficient-funds one.

        Le portefeuille rendu est un VRAI `Wallet` : la vue le pose sur
        `LigneArticle.wallet`, une cle etrangere qui refuse tout objet factice.
        / The returned wallet is a REAL Wallet: the view assigns it to
        LigneArticle.wallet, a foreign key that rejects any fake object.
        """
        faux_fedow = mock.MagicMock()
        portefeuille_reel = Wallet.objects.create(
            name=f'Wallet fedow simule {uuid_module.uuid4().hex[:8]}',
        )
        faux_fedow.wallet.get_or_create_wallet.return_value = (
            portefeuille_reel, False,
        )
        faux_fedow.wallet.get_total_fiducial_and_all_federated_token.return_value = (
            solde_centimes
        )
        faux_fedow.transaction.to_place_from_qrcode.return_value = transactions or []
        faux_fedow.asset.retrieve.return_value = {'category': categorie_asset}
        return faux_fedow

    # ------------------------------------------------------------------
    # 1. La generation du QR code
    # ------------------------------------------------------------------

    def test_la_generation_cree_une_ligne_en_attente(self):
        """Le QR code correspond a une ligne creee, mais pas encore encaissee.

        Tant que personne n'a scanne, aucun argent n'a bouge : la ligne doit
        rester en attente, sans quoi elle compterait dans le chiffre d'affaires.
        / Until someone scans, no money moved: the line must stay pending, or it
        would count towards revenue.
        """
        ligne = self._generer_un_qrcode()

        assert ligne.amount == MONTANT_DEMANDE_CENTIMES
        assert ligne.status == LigneArticle.CREATED
        assert ligne.payment_method == PaymentMethod.QRCODE_MA
        assert ligne.sale_origin == SaleOrigin.QRCODE_MA

    def test_la_generation_retient_qui_a_demande_le_paiement(self):
        """L'encaisseur est trace dans la ligne des sa creation.

        C'est la seule trace de QUI a demande cet encaissement : le payeur, lui,
        n'est connu qu'au moment du scan.
        / The only record of WHO requested this collection: the payer is only
        known at scan time.
        """
        ligne = self._generer_un_qrcode()

        metadonnees = json.loads(ligne.metadata)
        assert metadonnees['admin'] == self.encaisseur.email

    def test_la_generation_refuse_un_montant_absent(self):
        """Sans montant, pas de QR code.
        / No amount, no QR code."""
        lignes_avant = LigneArticle.objects.filter(
            sale_origin=SaleOrigin.QRCODE_MA,
        ).count()

        self.navigateur_encaisseur.post(
            CHEMIN_GENERATION, data={'asset_type': 'EUR'},
        )

        lignes_apres = LigneArticle.objects.filter(
            sale_origin=SaleOrigin.QRCODE_MA,
        ).count()
        assert lignes_apres == lignes_avant

    # ------------------------------------------------------------------
    # 2. Le scan — selon l'utilisateur qui scanne
    # ------------------------------------------------------------------

    def test_un_visiteur_non_connecte_est_envoye_se_connecter(self):
        """Le scan par un anonyme mene au login, avec retour prevu.

        Le QR code est affiche en public : n'importe qui peut le scanner. On ne
        renvoie donc pas une erreur, on invite a se connecter, et le parcours
        reprend ou il s'est arrete.
        / The QR code is publicly displayed: anyone may scan it. We invite them
        to log in and resume where they left off.
        """
        ligne = self._generer_un_qrcode()
        navigateur_anonyme = TenantClient(self.tenant)

        reponse = navigateur_anonyme.get(_chemin_de_scan(ligne.uuid.hex))

        assert reponse.status_code == 302
        assert '/login/login_fullpage' in reponse.url
        assert 'next=' in reponse.url

    def test_un_compte_sans_email_valide_ne_peut_pas_payer(self):
        """Payer engage de l'argent : l'adresse doit avoir ete confirmee.
        / Paying moves money: the address must have been confirmed."""
        ligne = self._generer_un_qrcode()
        payeur = self._creer_utilisateur('email-ko', email_valide=False)

        reponse = self._navigateur_de(payeur).get(_chemin_de_scan(ligne.uuid.hex))

        assert reponse.status_code == 302
        assert reponse.url == '/my_account/'

    def test_un_qrcode_inconnu_affiche_une_erreur_lisible(self):
        """Un uuid qui ne correspond a rien ne doit pas casser la page.

        Un QR code abime, perime ou fabrique par un tiers arrive ici. L'adherent
        doit lire un message, pas une page d'erreur serveur.
        / A damaged, stale or forged QR code lands here. The member must read a
        message, not a server error page.
        """
        payeur = self._creer_utilisateur('scan-inconnu')

        reponse = self._navigateur_de(payeur).get(
            _chemin_de_scan(uuid_module.uuid4().hex),
        )

        assert reponse.status_code == 200
        assert 'payment_error' in [gabarit.name or '' for gabarit in reponse.templates][0] \
            or b'QR' in reponse.content

    def test_un_qrcode_deja_paye_ne_peut_pas_etre_rejoue(self):
        """Scanner deux fois le meme QR code ne debite pas deux fois.

        C'est la garde anti-rejeu : le QR code reste affiche apres le paiement,
        et rien n'empeche un second adherent de le scanner.
        / The replay guard: the QR code stays visible after payment, and nothing
        stops a second member from scanning it.
        """
        ligne = self._generer_un_qrcode()
        LigneArticle.objects.filter(pk=ligne.pk).update(status=LigneArticle.VALID)
        payeur = self._creer_utilisateur('scan-rejeu')

        with mock.patch('fedow_connect.fedow_api.FedowAPI') as fedow:
            fedow.return_value = self._fedow_qui_repond(solde_centimes=99999)
            reponse = self._navigateur_de(payeur).get(_chemin_de_scan(ligne.uuid.hex))

        assert reponse.status_code == 200
        contenu = reponse.content.decode()
        assert 'already been processed' in contenu or 'deja' in contenu.lower()

    def test_un_payeur_sans_portefeuille_s_en_voit_creer_un(self):
        """Premier paiement d'un adherent : son portefeuille est cree a la volee.

        C'est le cas d'un compte tout neuf. Sans cette creation, le scan
        echouerait pour quelqu'un qui n'a jamais rien recharge.
        / A brand-new account: the wallet is created on the fly at scan time.
        """
        ligne = self._generer_un_qrcode()
        payeur_sans_portefeuille = self._creer_utilisateur('sans-wallet')
        assert payeur_sans_portefeuille.wallet is None

        faux_fedow = self._fedow_qui_repond(solde_centimes=0)
        with mock.patch('fedow_connect.fedow_api.FedowAPI') as fedow:
            fedow.return_value = faux_fedow
            reponse = self._navigateur_de(payeur_sans_portefeuille).get(
                _chemin_de_scan(ligne.uuid.hex),
            )

        assert reponse.status_code == 200
        faux_fedow.wallet.get_or_create_wallet.assert_called()

    def test_un_solde_suffisant_ouvre_l_ecran_de_validation(self):
        """Assez de monnaie : l'adherent peut confirmer.
        / Enough currency: the member may confirm."""
        ligne = self._generer_un_qrcode()
        payeur = self._creer_utilisateur('solde-ok', avec_wallet=True)

        with mock.patch('fedow_connect.fedow_api.FedowAPI') as fedow:
            fedow.return_value = self._fedow_qui_repond(
                solde_centimes=MONTANT_DEMANDE_CENTIMES + 500,
            )
            reponse = self._navigateur_de(payeur).get(_chemin_de_scan(ligne.uuid.hex))

        assert reponse.status_code == 200
        assert reponse.context['insufficient_funds'] is False
        assert reponse.context['amount'] == MONTANT_DEMANDE_CENTIMES

    def test_un_solde_insuffisant_est_annonce_des_le_scan(self):
        """Pas assez de monnaie : l'adherent le sait avant de confirmer.

        Le dire au scan plutot qu'apres la confirmation evite de lui faire
        croire que le paiement est parti.
        / Telling them at scan time avoids the impression that payment went
        through.
        """
        ligne = self._generer_un_qrcode()
        payeur = self._creer_utilisateur('solde-court', avec_wallet=True)

        with mock.patch('fedow_connect.fedow_api.FedowAPI') as fedow:
            fedow.return_value = self._fedow_qui_repond(
                solde_centimes=MONTANT_DEMANDE_CENTIMES - 1,
            )
            reponse = self._navigateur_de(payeur).get(_chemin_de_scan(ligne.uuid.hex))

        assert reponse.status_code == 200
        assert reponse.context['insufficient_funds'] is True

    def test_un_portefeuille_vide_ne_permet_pas_de_payer(self):
        """Aucune monnaie federee ni locale : le paiement est impossible.
        / No federated or local currency at all: payment is impossible."""
        ligne = self._generer_un_qrcode()
        payeur = self._creer_utilisateur('portefeuille-vide', avec_wallet=True)

        with mock.patch('fedow_connect.fedow_api.FedowAPI') as fedow:
            fedow.return_value = self._fedow_qui_repond(solde_centimes=0)
            reponse = self._navigateur_de(payeur).get(_chemin_de_scan(ligne.uuid.hex))

        assert reponse.context['insufficient_funds'] is True
        assert reponse.context['user_balance'] == 0

    # ------------------------------------------------------------------
    # 3. La confirmation du paiement
    # ------------------------------------------------------------------

    def test_un_paiement_confirme_remplace_la_ligne_en_attente(self):
        """La ligne en attente devient une vente validee.

        La vue SUPPRIME la ligne d'origine et en recree une par transaction
        Fedow, en conservant l'uuid pour la premiere. Une ligne en attente qui
        survivrait au paiement resterait encaissable une seconde fois.
        / The view DELETES the original line and recreates one per Fedow
        transaction, keeping the uuid for the first. A surviving pending line
        would remain collectable twice.
        """
        ligne = self._generer_un_qrcode()
        uuid_origine = ligne.uuid
        payeur = self._creer_utilisateur('paiement-ok', avec_wallet=True)

        with mock.patch('fedow_connect.fedow_api.FedowAPI') as fedow:
            fedow.return_value = self._fedow_qui_repond(
                solde_centimes=MONTANT_DEMANDE_CENTIMES + 500,
                transactions=[{
                    'uuid': uuid_module.uuid4(),
                    'asset': str(uuid_module.uuid4()),
                    'amount': MONTANT_DEMANDE_CENTIMES,
                }],
                categorie_asset='FED',
            )
            reponse = self._navigateur_de(payeur).post(
                CHEMIN_VALIDATION,
                data={'ligne_article_uuid_hex': uuid_origine.hex},
            )

        assert reponse.status_code == 200

        lignes = LigneArticle.objects.filter(sale_origin=SaleOrigin.QRCODE_MA)
        assert lignes.count() == 1
        ligne_payee = lignes.first()
        assert ligne_payee.status == LigneArticle.VALID
        assert ligne_payee.amount == MONTANT_DEMANDE_CENTIMES
        assert ligne_payee.uuid == uuid_origine

    def test_un_paiement_en_monnaie_federee_est_marque_comme_tel(self):
        """Payer en monnaie federee marque le reglement au moyen federe.

        Le moyen de paiement decide du poste comptable. Il vit sur le reglement de
        la vente, pas sur la ligne (Q-H2). Confondre monnaie
        federee et monnaie locale melangerait deux masses qui ne se remboursent
        pas de la meme facon.
        / The payment method decides the accounting heading. Mixing federated
        and local currency would blend two masses refunded differently.
        """
        ligne = self._generer_un_qrcode()
        payeur = self._creer_utilisateur('paiement-fed', avec_wallet=True)

        with mock.patch('fedow_connect.fedow_api.FedowAPI') as fedow:
            fedow.return_value = self._fedow_qui_repond(
                solde_centimes=MONTANT_DEMANDE_CENTIMES,
                transactions=[{
                    'uuid': uuid_module.uuid4(),
                    'asset': str(uuid_module.uuid4()),
                    'amount': MONTANT_DEMANDE_CENTIMES,
                }],
                categorie_asset='FED',
            )
            self._navigateur_de(payeur).post(
                CHEMIN_VALIDATION,
                data={'ligne_article_uuid_hex': ligne.uuid.hex},
            )

        ligne_payee = LigneArticle.objects.filter(
            sale_origin=SaleOrigin.QRCODE_MA,
        ).first()
        assert ligne_payee.payment_method is None
        assert ligne_payee.vente.reglements.get().moyen == PaymentMethod.STRIPE_FED

    def test_un_paiement_en_monnaie_locale_est_marque_comme_tel(self):
        """Payer en monnaie locale marque le reglement au moyen local.
        / Paying in local currency marks the payment with the local method."""
        ligne = self._generer_un_qrcode()
        payeur = self._creer_utilisateur('paiement-tlf', avec_wallet=True)

        with mock.patch('fedow_connect.fedow_api.FedowAPI') as fedow:
            fedow.return_value = self._fedow_qui_repond(
                solde_centimes=MONTANT_DEMANDE_CENTIMES,
                transactions=[{
                    'uuid': uuid_module.uuid4(),
                    'asset': str(uuid_module.uuid4()),
                    'amount': MONTANT_DEMANDE_CENTIMES,
                }],
                categorie_asset='TLF',
            )
            self._navigateur_de(payeur).post(
                CHEMIN_VALIDATION,
                data={'ligne_article_uuid_hex': ligne.uuid.hex},
            )

        ligne_payee = LigneArticle.objects.filter(
            sale_origin=SaleOrigin.QRCODE_MA,
        ).first()
        assert ligne_payee.payment_method is None
        assert ligne_payee.vente.reglements.get().moyen == PaymentMethod.LOCAL_EURO

    def test_un_paiement_reparti_sur_deux_monnaies_donne_une_ligne_et_deux_reglements(self):
        """La cascade peut puiser dans deux monnaies : une ligne, deux reglements.

        Un adherent paie 12,50 € avec 5 € de monnaie locale et 7,50 € de federee.
        Les deux masses restent distinctes en comptabilite par leurs REGLEMENTS ;
        l'article est UNE ligne au montant demande (D26).
        / Two currencies: one line at the requested amount, two payments.
        """
        ligne = self._generer_un_qrcode()
        payeur = self._creer_utilisateur('paiement-cascade', avec_wallet=True)

        with mock.patch('fedow_connect.fedow_api.FedowAPI') as fedow:
            fedow.return_value = self._fedow_qui_repond(
                solde_centimes=MONTANT_DEMANDE_CENTIMES,
                transactions=[
                    {'uuid': uuid_module.uuid4(), 'asset': str(uuid_module.uuid4()), 'amount': 500},
                    {'uuid': uuid_module.uuid4(), 'asset': str(uuid_module.uuid4()), 'amount': 750},
                ],
                categorie_asset='FED',
            )
            self._navigateur_de(payeur).post(
                CHEMIN_VALIDATION,
                data={'ligne_article_uuid_hex': ligne.uuid.hex},
            )

        self._verifier_une_ligne_et_ses_reglements(
            SaleOrigin.QRCODE_MA, MONTANT_DEMANDE_CENTIMES, [500, 750]
        )

    def _verifier_une_ligne_et_ses_reglements(
            self, origine, montant_demande_centimes, montants_debites):
        """Verifie qu'un paiement s'ecrit en UNE ligne et un reglement par monnaie.

        La ligne (hors article d'ecart d'encaissement) porte le montant DEMANDE,
        en quantite 1. Les reglements de sa vente portent l'argent debite dans
        chaque monnaie. Rend la ligne.
        / One line at the requested amount (qty 1), one payment per debited
        currency. Returns the line.
        """
        lignes_hors_ecart = LigneArticle.objects.filter(sale_origin=origine).exclude(
            pricesold__productsold__product__name__in=[
                NOM_ECART_RECU_EN_PLUS, NOM_ECART_RECU_EN_MOINS,
            ]
        )
        assert lignes_hors_ecart.count() == 1
        ligne = lignes_hors_ecart.get()
        assert ligne.amount == montant_demande_centimes
        assert ligne.qty == Decimal("1")

        montants_des_reglements = sorted(
            ligne.vente.reglements.values_list('montant', flat=True)
        )
        assert montants_des_reglements == sorted(montants_debites)
        return ligne

    def test_un_debit_partiel_enregistre_ce_qui_a_ete_paye(self):
        """Fedow debite moins que demande : la vente enregistre ce qui a ete paye.

        12,50 € demandes, 5,00 + 7,00 € debites. La ligne garde le montant demande
        (12,50 €), un article « Ecart d'encaissement — recu en moins » porte
        −0,50 € (D26) : la vente vaut 12,00 €, jamais un montant que personne n'a
        paye.
        / Fedow debits less than requested: the line keeps the requested amount, a
        "received less" gap item carries −0.50: the sale is worth what was paid.
        """
        ligne = self._generer_un_qrcode()
        payeur = self._creer_utilisateur('paiement-partiel', avec_wallet=True)

        with mock.patch('fedow_connect.fedow_api.FedowAPI') as fedow:
            fedow.return_value = self._fedow_qui_repond(
                solde_centimes=MONTANT_DEMANDE_CENTIMES,
                transactions=[
                    {'uuid': uuid_module.uuid4(), 'asset': str(uuid_module.uuid4()), 'amount': 500},
                    {'uuid': uuid_module.uuid4(), 'asset': str(uuid_module.uuid4()), 'amount': 700},
                ],
                categorie_asset='FED',
            )
            self._navigateur_de(payeur).post(
                CHEMIN_VALIDATION,
                data={'ligne_article_uuid_hex': ligne.uuid.hex},
            )

        ligne_payee = self._verifier_une_ligne_et_ses_reglements(
            SaleOrigin.QRCODE_MA, MONTANT_DEMANDE_CENTIMES, [500, 700]
        )
        article_d_ecart = ligne_payee.vente.articles.get(
            pricesold__productsold__product__name=NOM_ECART_RECU_EN_MOINS,
        )
        assert article_d_ecart.total_ttc == -50
        assert ligne_payee.vente.total_ttc == 1200

    def test_un_paiement_reparti_en_trois_parts_garde_tout_le_montant(self):
        """Trois debits inegaux : une ligne de 10 €, trois reglements exacts.

        10 € payes 3,33 + 3,33 + 3,34. Aucun centime ne disparait : la ligne vaut
        10 € et les trois reglements portent chacun leur montant exact.
        / Three unequal debits: one 10 € line, three exact payments.
        """
        ligne = self._generer_un_qrcode(montant_centimes=1000)
        payeur = self._creer_utilisateur('paiement-trois-parts', avec_wallet=True)

        with mock.patch('fedow_connect.fedow_api.FedowAPI') as fedow:
            fedow.return_value = self._fedow_qui_repond(
                solde_centimes=1000,
                transactions=[
                    {'uuid': uuid_module.uuid4(), 'asset': str(uuid_module.uuid4()), 'amount': 333},
                    {'uuid': uuid_module.uuid4(), 'asset': str(uuid_module.uuid4()), 'amount': 333},
                    {'uuid': uuid_module.uuid4(), 'asset': str(uuid_module.uuid4()), 'amount': 334},
                ],
                categorie_asset='FED',
            )
            self._navigateur_de(payeur).post(
                CHEMIN_VALIDATION,
                data={'ligne_article_uuid_hex': ligne.uuid.hex},
            )

        self._verifier_une_ligne_et_ses_reglements(
            SaleOrigin.QRCODE_MA, 1000, [333, 333, 334]
        )

    def test_un_solde_insuffisant_ne_consomme_pas_la_ligne(self):
        """Refuse pour fonds insuffisants : rien n'est encaisse, rien n'est perdu.

        L'encaisseur doit pouvoir laisser son QR code affiche : l'adherent qui
        recharge et rescanne doit pouvoir payer.
        / The collector may leave the QR code up: a member who tops up and
        rescans must still be able to pay.
        """
        ligne = self._generer_un_qrcode()
        payeur = self._creer_utilisateur('fonds-courts', avec_wallet=True)

        faux_fedow = self._fedow_qui_repond(
            solde_centimes=MONTANT_DEMANDE_CENTIMES - 100,
        )
        with mock.patch('fedow_connect.fedow_api.FedowAPI') as fedow:
            fedow.return_value = faux_fedow
            reponse = self._navigateur_de(payeur).post(
                CHEMIN_VALIDATION,
                data={'ligne_article_uuid_hex': ligne.uuid.hex},
            )

        assert reponse.status_code == 200
        faux_fedow.transaction.to_place_from_qrcode.assert_not_called()

        ligne.refresh_from_db()
        assert ligne.status == LigneArticle.CREATED

    def test_une_confirmation_sur_un_qrcode_inconnu_ne_cree_rien(self):
        """Un uuid fabrique ne doit pas produire de vente.
        / A forged uuid must not produce a sale."""
        payeur = self._creer_utilisateur('confirm-inconnu', avec_wallet=True)

        with mock.patch('fedow_connect.fedow_api.FedowAPI') as fedow:
            fedow.return_value = self._fedow_qui_repond(solde_centimes=99999)
            reponse = self._navigateur_de(payeur).post(
                CHEMIN_VALIDATION,
                data={'ligne_article_uuid_hex': uuid_module.uuid4().hex},
            )

        assert reponse.status_code == 200
        assert LigneArticle.objects.filter(
            sale_origin=SaleOrigin.QRCODE_MA,
            status=LigneArticle.VALID,
        ).count() == 0

    def test_une_confirmation_sans_email_valide_est_refusee(self):
        """La garde du scan vaut aussi a la confirmation.

        Sans elle, il suffirait d'appeler la route de confirmation directement
        pour contourner la verification faite a l'ecran precedent.
        / Without it, calling the confirmation route directly would bypass the
        check made on the previous screen.
        """
        ligne = self._generer_un_qrcode()
        payeur = self._creer_utilisateur('confirm-email-ko', email_valide=False)

        reponse = self._navigateur_de(payeur).post(
            CHEMIN_VALIDATION,
            data={'ligne_article_uuid_hex': ligne.uuid.hex},
        )

        assert reponse.status_code == 302
        assert reponse.url == '/my_account/'

        ligne.refresh_from_db()
        assert ligne.status == LigneArticle.CREATED

    # ------------------------------------------------------------------
    # 4. Les categories de monnaie acceptees au paiement
    # ------------------------------------------------------------------
    #
    # C'est le Fedow distant qui decide dans quelle(s) monnaie(s) il debite. La
    # vue traduit ensuite la categorie renvoyee en moyen de paiement comptable.
    # Elle n'en connait que DEUX : la monnaie federee et le token local
    # fiduciaire. Toute autre categorie tombe dans un `else` qui leve.
    #
    # / The remote Fedow decides which currencies to debit; the view maps the
    # returned category to an accounting payment method. It knows only TWO.

    def _payer_avec_un_asset_de_categorie(self, categorie):
        """Confirme un paiement que le Fedow dit avoir debite dans cette categorie.
        / Confirms a payment the Fedow says it debited in this category."""
        ligne = self._generer_un_qrcode()
        payeur = self._creer_utilisateur(f'asset-{categorie.lower()}', avec_wallet=True)

        with mock.patch('fedow_connect.fedow_api.FedowAPI') as fedow:
            fedow.return_value = self._fedow_qui_repond(
                solde_centimes=MONTANT_DEMANDE_CENTIMES,
                transactions=[{
                    'uuid': uuid_module.uuid4(),
                    'asset': str(uuid_module.uuid4()),
                    'amount': MONTANT_DEMANDE_CENTIMES,
                }],
                categorie_asset=categorie,
            )
            reponse = self._navigateur_de(payeur).post(
                CHEMIN_VALIDATION,
                data={'ligne_article_uuid_hex': ligne.uuid.hex},
            )
        return reponse

    def test_les_deux_seules_categories_acceptees_produisent_une_vente(self):
        """Monnaie federee et token local fiduciaire : les deux passent.
        / Federated currency and local fiduciary token: both go through."""
        for categorie, moyen_attendu in [
            ('FED', PaymentMethod.STRIPE_FED),
            ('TLF', PaymentMethod.LOCAL_EURO),
        ]:
            # Les ventes payées des tours précédents restent (un article d'une vente
            # réglée ne se supprime pas) : on les met de côté par leur uuid.
            # / Paid sales of previous rounds stay (a settled item is never
            # deleted): they are set aside by uuid.
            uuids_des_lignes_payees_avant = list(
                LigneArticle.objects.filter(
                    sale_origin=SaleOrigin.QRCODE_MA,
                    status=LigneArticle.VALID,
                ).values_list('uuid', flat=True)
            )

            self._payer_avec_un_asset_de_categorie(categorie)

            ligne_payee = LigneArticle.objects.filter(
                sale_origin=SaleOrigin.QRCODE_MA,
                status=LigneArticle.VALID,
            ).exclude(uuid__in=uuids_des_lignes_payees_avant).first()
            assert ligne_payee is not None, f"Categorie {categorie} : aucune vente creee."
            assert ligne_payee.vente.reglements.get().moyen == moyen_attendu

    def test_une_monnaie_non_fiduciaire_ne_produit_aucune_vente(self):
        """Cadeau, temps et fidelite ne sont pas traduits en moyen de paiement.

        La vue ne connait que la monnaie federee et le token local fiduciaire.
        Si le Fedow debite un bon cadeau, des heures de benevolat ou des points
        de fidelite, la traduction echoue AVANT toute ecriture en base : AUCUNE
        vente n'est enregistree — alors que le Fedow, lui, a debite le
        portefeuille. La demande passe en echec (FAILED) : elle ne se paie plus,
        et le lieu verifie a la main.

        Ce test DECRIT le comportement actuel. Il echouera le jour ou ces
        categories seront prises en charge : ce sera le signal qu'il faut
        verifier quel moyen de paiement leur est attribue.

        / The view knows only federated and local fiduciary currency. If the
        Fedow debits a gift token, volunteer hours or loyalty points, the mapping
        fails before any database write and NO sale is recorded — while the Fedow
        has debited the wallet. The request fails for good.
        This test DESCRIBES current behaviour.
        """
        for categorie_non_geree in ['TNF', 'TIM', 'FID']:
            LigneArticle.objects.filter(sale_origin=SaleOrigin.QRCODE_MA).delete()

            self._payer_avec_un_asset_de_categorie(categorie_non_geree)

            ventes = LigneArticle.objects.filter(
                sale_origin=SaleOrigin.QRCODE_MA,
                status=LigneArticle.VALID,
            )
            assert ventes.count() == 0, (
                f"La categorie {categorie_non_geree} est desormais traduite en "
                f"moyen de paiement : mettre a jour ce test et verifier lequel."
            )

            # Seule reste la demande, en echec. / Only the request remains, FAILED.
            statuts_des_lignes_du_qrcode = list(
                LigneArticle.objects.filter(
                    sale_origin=SaleOrigin.QRCODE_MA,
                ).values_list('status', flat=True)
            )
            assert statuts_des_lignes_du_qrcode == [LigneArticle.FAILED]

    # ------------------------------------------------------------------
    # 5. check_payment — l'encaisseur attend la confirmation
    # ------------------------------------------------------------------
    #
    # L'ecran du generateur interroge cette route en boucle pour savoir si le
    # QR code affiche a ete paye. C'est ce qui fait passer l'ecran du caissier
    # de « en attente » a « paiement recu ».
    # / The generator screen polls this route to learn whether the displayed QR
    # code has been paid.

    def _chemin_de_verification(self, uuid_hex):
        return f'/qrcodescanpay/{uuid_hex}/check_payment/'

    def test_un_paiement_en_attente_n_est_pas_annonce_comme_recu(self):
        """Tant que personne n'a paye, l'encaisseur doit continuer d'attendre.

        Annoncer un paiement recu trop tot ferait remettre la marchandise a
        quelqu'un qui n'a rien regle.
        / Announcing payment too early would hand over the goods to someone who
        has not paid.
        """
        ligne = self._generer_un_qrcode()

        reponse = self.navigateur_encaisseur.get(
            self._chemin_de_verification(ligne.uuid.hex),
        )

        assert reponse.status_code == 200
        assert reponse.context['is_valid'] is False

    def test_un_paiement_valide_est_annonce_a_l_encaisseur(self):
        """Une fois la vente enregistree, l'encaisseur voit la confirmation.
        / Once the sale is recorded, the collector sees the confirmation."""
        ligne = self._generer_un_qrcode()
        LigneArticle.objects.filter(pk=ligne.pk).update(status=LigneArticle.VALID)

        reponse = self.navigateur_encaisseur.get(
            self._chemin_de_verification(ligne.uuid.hex),
        )

        assert reponse.context['is_valid'] is True

    def test_la_verification_est_reservee_a_qui_peut_encaisser(self):
        """Un adherent lambda n'interroge pas l'etat des paiements d'autrui.

        Sans cette garde, n'importe qui pourrait sonder les uuid de paiement du
        lieu pour savoir lesquels ont ete regles.
        / Without this guard, anyone could probe the venue's payment uuids.
        """
        ligne = self._generer_un_qrcode()
        curieux = self._creer_utilisateur('curieux')

        reponse = self._navigateur_de(curieux).get(
            self._chemin_de_verification(ligne.uuid.hex),
        )

        assert reponse.status_code == 403

    # ------------------------------------------------------------------
    # 6. process_with_nfc — payer en presentant sa carte
    # ------------------------------------------------------------------
    #
    # Meme paiement que par QR code, mais l'adherent presente sa carte NFC au
    # lecteur du caissier au lieu de scanner avec son telephone. Tout est
    # verifie par `QrCodeScanPayNfcValidator` : format du tag, existence de la
    # carte, rattachement a un compte, et solde.
    # / Same payment, but the member taps their NFC card on the cashier's reader.

    CHEMIN_NFC = '/qrcodescanpay/process_with_nfc/'

    def _poster_une_lecture_nfc(self, tag, ligne, navigateur=None):
        """Simule la lecture d'une carte par le lecteur du caissier.
        / Simulates the cashier's reader picking up a card."""
        return (navigateur or self.navigateur_encaisseur).post(
            self.CHEMIN_NFC,
            data={
                'tagSerial': tag,
                'ligne_article_uuid_hex': ligne.uuid.hex,
            },
        )

    def _carte_fedow(self, wallet_uuid, est_ephemere=False):
        """La reponse du Fedow distant a une interrogation de carte.
        / The remote Fedow's answer when asked about a card."""
        return {
            'wallet_uuid': str(wallet_uuid),
            'is_wallet_ephemere': est_ephemere,
        }

    def test_un_tag_nfc_mal_forme_est_refuse(self):
        """Le tag doit faire huit caracteres hexadecimaux.

        Une lecture parasite, ou un lecteur mal configure, ne doit pas partir
        chercher une carte inexistante sur le Fedow.
        / A stray read must not go looking for a nonexistent card on the Fedow.
        """
        ligne = self._generer_un_qrcode()

        with mock.patch('BaseBillet.validators.FedowAPI'):
            reponse = self._poster_une_lecture_nfc('pas-un-tag', ligne)

        assert reponse.status_code == 400

    def test_une_carte_inconnue_du_fedow_est_refusee(self):
        """Une carte que le Fedow ne connait pas ne peut pas payer.
        / A card the Fedow does not know cannot pay."""
        ligne = self._generer_un_qrcode()

        with mock.patch('BaseBillet.validators.FedowAPI') as fedow:
            fedow.return_value.NFCcard.card_tag_id_retrieve.return_value = None
            reponse = self._poster_une_lecture_nfc('62FE1601', ligne)

        assert reponse.status_code == 400

    def test_une_carte_non_rattachee_a_un_compte_est_refusee(self):
        """Une carte anonyme ne peut pas servir a payer ici.

        Son portefeuille est ephemere : personne n'en repond. Le message invite
        a lier la carte en scannant le QR code au dos.
        / Its wallet is ephemeral: nobody owns it. The message invites linking
        the card by scanning the QR code on its back.
        """
        ligne = self._generer_un_qrcode()
        portefeuille_ephemere = Wallet.objects.create(name='Wallet ephemere NFC')

        with mock.patch('BaseBillet.validators.FedowAPI') as fedow:
            fedow.return_value.NFCcard.card_tag_id_retrieve.return_value = (
                self._carte_fedow(portefeuille_ephemere.uuid, est_ephemere=True)
            )
            reponse = self._poster_une_lecture_nfc('62FE1601', ligne)

        assert reponse.status_code == 400

    def test_un_paiement_deja_regle_n_est_pas_rejouable_par_carte(self):
        """La garde anti-rejeu vaut aussi pour le paiement par carte.

        Le validateur n'accepte qu'une ligne EN ATTENTE : une vente deja
        enregistree ne peut pas etre debitee une seconde fois en presentant une
        carte.
        / The validator only accepts a PENDING line, so a recorded sale cannot
        be charged twice by tapping a card.
        """
        ligne = self._generer_un_qrcode()
        LigneArticle.objects.filter(pk=ligne.pk).update(status=LigneArticle.VALID)

        payeur = self._creer_utilisateur('nfc-rejeu', avec_wallet=True)
        with mock.patch('BaseBillet.validators.FedowAPI') as fedow:
            fedow.return_value.NFCcard.card_tag_id_retrieve.return_value = (
                self._carte_fedow(payeur.wallet.uuid)
            )
            fedow.return_value.wallet.get_total_fiducial_and_all_federated_token.return_value = 99999
            reponse = self._poster_une_lecture_nfc('62FE1601', ligne)

        assert reponse.status_code == 400

    def test_un_solde_insuffisant_sur_la_carte_est_refuse(self):
        """Pas assez de monnaie sur la carte : le paiement n'est pas lance.

        Le refus vient du validateur, AVANT tout appel de transaction : rien
        n'est debite, et la ligne reste encaissable.
        / The refusal comes from the validator, BEFORE any transaction call.
        """
        ligne = self._generer_un_qrcode()
        payeur = self._creer_utilisateur('nfc-solde-court', avec_wallet=True)

        with mock.patch('BaseBillet.validators.FedowAPI') as fedow:
            fedow.return_value.NFCcard.card_tag_id_retrieve.return_value = (
                self._carte_fedow(payeur.wallet.uuid)
            )
            fedow.return_value.wallet.get_total_fiducial_and_all_federated_token.return_value = (
                MONTANT_DEMANDE_CENTIMES - 1
            )
            reponse = self._poster_une_lecture_nfc('62FE1601', ligne)

        assert reponse.status_code == 400

        ligne.refresh_from_db()
        assert ligne.status == LigneArticle.CREATED

    def test_un_paiement_par_carte_enregistre_la_vente(self):
        """Cas nominal : la carte paie, la vente est enregistree.

        Comme pour le QR code, la ligne en attente est remplacee par une ligne
        validee, et le moyen de paiement suit la monnaie debitee.
        / As with the QR code, the pending line is replaced by a validated one.
        """
        ligne = self._generer_un_qrcode()
        payeur = self._creer_utilisateur('nfc-ok', avec_wallet=True)

        with mock.patch('BaseBillet.validators.FedowAPI') as fedow:
            faux_fedow = fedow.return_value
            faux_fedow.NFCcard.card_tag_id_retrieve.return_value = (
                self._carte_fedow(payeur.wallet.uuid)
            )
            faux_fedow.wallet.get_total_fiducial_and_all_federated_token.return_value = (
                MONTANT_DEMANDE_CENTIMES
            )
            faux_fedow.transaction.to_place_from_qrcode.return_value = [{
                'uuid': uuid_module.uuid4(),
                'asset': str(uuid_module.uuid4()),
                'amount': MONTANT_DEMANDE_CENTIMES,
            }]
            faux_fedow.asset.retrieve.return_value = {'category': 'TLF'}
            # Le tag arrive du lecteur avec des deux-points : le validateur les
            # retire et met en majuscules avant d'interroger le Fedow.
            # / The reader sends colons; the validator strips and uppercases them.
            reponse = self._poster_une_lecture_nfc('62:FE:16:01', ligne)

        # 202 Accepted : le paiement est traite et la reponse est un JSON de
        # confirmation, pas une page. / 202 Accepted with a JSON confirmation.
        assert reponse.status_code == 202, reponse.content.decode()[:400]

        # Le paiement par carte est enregistre sous l'origine NFC, et non sous
        # celle du QR code : c'est le canal reellement emprunte qui compte, meme
        # si la demande de paiement, elle, est nee d'un QR code.
        # / Card payments are recorded under the NFC origin, not the QR code one:
        # what counts is the channel actually used.
        ventes = LigneArticle.objects.filter(
            sale_origin=SaleOrigin.NFC_MA,
            status=LigneArticle.VALID,
        )
        assert ventes.count() == 1
        assert ventes.first().vente.reglements.get().moyen == PaymentMethod.LOCAL_EURO

    def test_un_paiement_par_carte_reparti_enregistre_le_montant_entier(self):
        """La carte paie 12,50 € avec deux monnaies : 12,50 € sont enregistres.

        UNE ligne au montant demande, un reglement par monnaie. L'ecran du caissier
        annonce le montant paye en entier, pas la part de la derniere monnaie.
        / The card pays with two currencies: the full amount is recorded and
        announced to the cashier.
        """
        ligne = self._generer_un_qrcode()
        payeur = self._creer_utilisateur('nfc-reparti', avec_wallet=True)

        with mock.patch('BaseBillet.validators.FedowAPI') as fedow:
            faux_fedow = fedow.return_value
            faux_fedow.NFCcard.card_tag_id_retrieve.return_value = (
                self._carte_fedow(payeur.wallet.uuid)
            )
            faux_fedow.wallet.get_total_fiducial_and_all_federated_token.return_value = (
                MONTANT_DEMANDE_CENTIMES
            )
            faux_fedow.transaction.to_place_from_qrcode.return_value = [
                {'uuid': uuid_module.uuid4(), 'asset': str(uuid_module.uuid4()), 'amount': 500},
                {'uuid': uuid_module.uuid4(), 'asset': str(uuid_module.uuid4()), 'amount': 750},
            ]
            faux_fedow.asset.retrieve.return_value = {'category': 'TLF'}
            reponse = self._poster_une_lecture_nfc('62FE1601', ligne)

        assert reponse.status_code == 202, reponse.content.decode()[:400]
        assert float(reponse.json()['amount_paid']) == 12.50

        self._verifier_une_ligne_et_ses_reglements(
            SaleOrigin.NFC_MA, MONTANT_DEMANDE_CENTIMES, [500, 750]
        )

    def test_le_paiement_par_carte_retient_qui_a_presente_la_carte(self):
        """La lecture NFC laisse une trace : le tag, le lecteur, le porteur.

        Sans elle, une contestation de paiement ne pourrait etre rattachee ni a
        une carte ni a un caissier.
        / Without it, a disputed payment could be tied neither to a card nor to
        a cashier.
        """
        ligne = self._generer_un_qrcode()
        payeur = self._creer_utilisateur('nfc-trace', avec_wallet=True)

        with mock.patch('BaseBillet.validators.FedowAPI') as fedow:
            faux_fedow = fedow.return_value
            faux_fedow.NFCcard.card_tag_id_retrieve.return_value = (
                self._carte_fedow(payeur.wallet.uuid)
            )
            faux_fedow.wallet.get_total_fiducial_and_all_federated_token.return_value = (
                MONTANT_DEMANDE_CENTIMES
            )
            faux_fedow.transaction.to_place_from_qrcode.return_value = [{
                'uuid': uuid_module.uuid4(),
                'asset': str(uuid_module.uuid4()),
                'amount': MONTANT_DEMANDE_CENTIMES,
            }]
            faux_fedow.asset.retrieve.return_value = {'category': 'FED'}
            self._poster_une_lecture_nfc('62FE1601', ligne)

        vente = LigneArticle.objects.filter(
            sale_origin=SaleOrigin.NFC_MA,
            status=LigneArticle.VALID,
        ).first()
        metadonnees = vente.metadata
        if not isinstance(metadonnees, dict):
            metadonnees = json.loads(metadonnees)

        assert metadonnees['nfc']['tag_id'] == '62FE1601'
        assert metadonnees['nfc']['reader'] == self.encaisseur.email
        assert metadonnees['nfc']['user'] == payeur.email

    def test_le_paiement_par_carte_est_reserve_a_qui_peut_encaisser(self):
        """Seul un membre habilite peut declencher un paiement par carte.

        Sans cette garde, un adherent pourrait debiter la carte d'un autre en
        postant simplement le tag lu ailleurs.
        / Without this guard, a member could charge someone else's card by
        posting a tag read elsewhere.
        """
        ligne = self._generer_un_qrcode()
        curieux = self._creer_utilisateur('nfc-curieux')

        with mock.patch('BaseBillet.validators.FedowAPI'):
            reponse = self._poster_une_lecture_nfc(
                '62FE1601', ligne, navigateur=self._navigateur_de(curieux),
            )

        assert reponse.status_code == 403

    # ------------------------------------------------------------------
    # 7. Anti-rejeu : un QR code ne se paie qu'une fois
    # ------------------------------------------------------------------
    #
    # Fedow n'a pas de cle d'idempotence : chaque appel a
    # `to_place_from_qrcode` debite. La vue « reserve » donc la ligne
    # (CREATED -> UNPAID, en une requete atomique) juste avant le debit :
    # une seconde demande trouve 0 ligne a reserver et s'arrete.
    # / Fedow has no idempotency key: every call debits. The view reserves the
    # line (CREATED -> UNPAID, atomically) right before the debit.

    def _gabarits_de(self, reponse):
        """Les noms des gabarits rendus. / Names of the rendered templates."""
        return [gabarit.name or '' for gabarit in reponse.templates]

    def test_un_qrcode_deja_paye_ne_debite_pas_une_seconde_fois(self):
        """Deux confirmations du meme QR code : un seul debit.

        Deux ecrans de validation ouverts sur le meme QR code (deux onglets,
        ou deux adherents qui ont scanne avant le paiement) envoient chacun
        leur confirmation.
        / Two validation screens open on the same QR code each send a confirmation.
        """
        ligne = self._generer_un_qrcode()
        payeur = self._creer_utilisateur('rejeu-qr', avec_wallet=True)
        navigateur = self._navigateur_de(payeur)

        faux_fedow = self._fedow_qui_repond(
            solde_centimes=99999,
            transactions=[{
                'uuid': uuid_module.uuid4(),
                'asset': str(uuid_module.uuid4()),
                'amount': MONTANT_DEMANDE_CENTIMES,
            }],
        )
        with mock.patch('fedow_connect.fedow_api.FedowAPI') as fedow:
            fedow.return_value = faux_fedow
            premiere_reponse = navigateur.post(
                CHEMIN_VALIDATION, data={'ligne_article_uuid_hex': ligne.uuid.hex},
            )
            seconde_reponse = navigateur.post(
                CHEMIN_VALIDATION, data={'ligne_article_uuid_hex': ligne.uuid.hex},
            )

        assert any('payment_confirmation' in nom for nom in self._gabarits_de(premiere_reponse))
        assert faux_fedow.transaction.to_place_from_qrcode.call_count == 1
        assert any('payment_error' in nom for nom in self._gabarits_de(seconde_reponse))

    def test_une_ligne_qui_n_est_pas_un_qrcode_ne_peut_pas_etre_payee(self):
        """Seule une demande de paiement QR se paie par cette route.

        Une demande QR se reconnait a son ORIGINE (`sale_origin`). Sans ce filtre,
        un uuid de billet ou d'adhesion (origine « en ligne ») poste ici serait
        debite, supprime puis recree en vente QR.
        / A QR request is recognised by its ORIGIN. Without this filter, a ticket or
        membership uuid posted here would be debited, deleted and recreated as a
        QR sale.
        """
        ligne = self._generer_un_qrcode()
        LigneArticle.objects.filter(pk=ligne.pk).update(
            sale_origin=SaleOrigin.LESPASS,
        )
        payeur = self._creer_utilisateur('pas-un-qr', avec_wallet=True)

        faux_fedow = self._fedow_qui_repond(solde_centimes=99999)
        with mock.patch('fedow_connect.fedow_api.FedowAPI') as fedow:
            fedow.return_value = faux_fedow
            self._navigateur_de(payeur).post(
                CHEMIN_VALIDATION, data={'ligne_article_uuid_hex': ligne.uuid.hex},
            )

        faux_fedow.transaction.to_place_from_qrcode.assert_not_called()
        ligne.refresh_from_db()
        assert ligne.status == LigneArticle.CREATED

    def test_une_erreur_fedow_pendant_le_debit_bloque_le_qrcode(self):
        """Erreur reseau pendant le debit : le QR code n'est plus payable.

        On ne sait pas si Fedow a debite. Rendre la ligne payable risquerait un
        second debit : elle passe en echec, le lieu verifie a la main.
        / We do not know whether Fedow debited: the line fails, the venue checks.
        """
        ligne = self._generer_un_qrcode()
        payeur = self._creer_utilisateur('erreur-debit', avec_wallet=True)
        navigateur = self._navigateur_de(payeur)

        faux_fedow = self._fedow_qui_repond(solde_centimes=99999)
        faux_fedow.transaction.to_place_from_qrcode.side_effect = ConnectionError('Fedow injoignable')
        with mock.patch('fedow_connect.fedow_api.FedowAPI') as fedow:
            fedow.return_value = faux_fedow
            navigateur.post(CHEMIN_VALIDATION, data={'ligne_article_uuid_hex': ligne.uuid.hex})

            ligne.refresh_from_db()
            assert ligne.status == LigneArticle.FAILED

            navigateur.post(CHEMIN_VALIDATION, data={'ligne_article_uuid_hex': ligne.uuid.hex})

        assert faux_fedow.transaction.to_place_from_qrcode.call_count == 1

    def _reserver_la_ligne_pendant_la_lecture_du_solde(self, ligne):
        """Un faux « lire le solde » qui laisse une autre requete reserver la ligne.

        La lecture du solde a lieu APRES le chargement de la ligne et AVANT la
        reservation : c'est la fenetre ou une seconde requete (seconde lecture
        de carte, second ecran de validation) passe la ligne en UNPAID. Seule
        une reservation atomique en base, et non un test du statut deja lu en
        memoire, arrete alors le debit.
        / The balance read happens AFTER loading the line and BEFORE the
        reservation: another request reserves the line in between. Only an
        atomic reservation in the database stops the debit.
        """
        def solde_lu_pendant_qu_une_autre_requete_reserve(*args, **kwargs):
            LigneArticle.objects.filter(pk=ligne.pk).update(status=LigneArticle.UNPAID)
            return 99999
        return solde_lu_pendant_qu_une_autre_requete_reserve

    def test_une_lecture_de_carte_concurrente_ne_debite_pas(self):
        """Deux lectures NFC en meme temps : la seconde ne debite pas.

        Chaque clic sur « Lire la carte » ajoute un lecteur : un passage de
        carte peut envoyer deux requetes simultanees.
        / Each click adds a reader: one tap may send two simultaneous requests.
        """
        ligne = self._generer_un_qrcode()
        payeur = self._creer_utilisateur('nfc-concurrente', avec_wallet=True)

        with mock.patch('BaseBillet.validators.FedowAPI') as fedow:
            faux_fedow = fedow.return_value
            faux_fedow.NFCcard.card_tag_id_retrieve.return_value = (
                self._carte_fedow(payeur.wallet.uuid)
            )
            faux_fedow.wallet.get_total_fiducial_and_all_federated_token.side_effect = (
                self._reserver_la_ligne_pendant_la_lecture_du_solde(ligne)
            )
            reponse = self._poster_une_lecture_nfc('62FE1601', ligne)

        assert reponse.status_code == 409
        faux_fedow.transaction.to_place_from_qrcode.assert_not_called()

    def test_une_confirmation_concurrente_du_qrcode_ne_debite_pas(self):
        """Deux confirmations du meme QR code en meme temps : la seconde ne debite pas.
        / Two simultaneous confirmations of the same QR code: the second one does not debit.
        """
        ligne = self._generer_un_qrcode()
        payeur = self._creer_utilisateur('qr-concurrent', avec_wallet=True)

        faux_fedow = self._fedow_qui_repond(solde_centimes=99999)
        faux_fedow.wallet.get_total_fiducial_and_all_federated_token.side_effect = (
            self._reserver_la_ligne_pendant_la_lecture_du_solde(ligne)
        )
        with mock.patch('fedow_connect.fedow_api.FedowAPI') as fedow:
            fedow.return_value = faux_fedow
            reponse = self._navigateur_de(payeur).post(
                CHEMIN_VALIDATION, data={'ligne_article_uuid_hex': ligne.uuid.hex},
            )

        assert any('payment_error' in nom for nom in self._gabarits_de(reponse))
        faux_fedow.transaction.to_place_from_qrcode.assert_not_called()

    def test_une_erreur_fedow_pendant_un_paiement_par_carte_repond_proprement(self):
        """Erreur Fedow au debit par carte : une reponse lisible, ligne en echec.

        Le caissier voit un message dans sa fenetre, pas une erreur serveur.
        / The cashier sees a message in the popup, not a server error.
        """
        ligne = self._generer_un_qrcode()
        payeur = self._creer_utilisateur('nfc-erreur', avec_wallet=True)

        with mock.patch('BaseBillet.validators.FedowAPI') as fedow:
            faux_fedow = fedow.return_value
            faux_fedow.NFCcard.card_tag_id_retrieve.return_value = (
                self._carte_fedow(payeur.wallet.uuid)
            )
            faux_fedow.wallet.get_total_fiducial_and_all_federated_token.return_value = 99999
            faux_fedow.transaction.to_place_from_qrcode.side_effect = ConnectionError('Fedow injoignable')
            reponse = self._poster_une_lecture_nfc('62FE1601', ligne)

        assert reponse.status_code == 500
        assert reponse.json()['detail']
        ligne.refresh_from_db()
        assert ligne.status == LigneArticle.FAILED

    def test_un_qrcode_en_cours_de_paiement_n_affiche_pas_l_ecran_de_validation(self):
        """Scanner un QR code deja reserve : message « deja traite », ligne intacte.

        La garde passe AVANT l'ecriture des metadonnees : un scan tardif ne
        reecrit pas la ligne d'un paiement en cours ou deja fait.
        / The guard runs BEFORE the metadata write: a late scan leaves the line alone.
        """
        ligne = self._generer_un_qrcode()
        LigneArticle.objects.filter(pk=ligne.pk).update(status=LigneArticle.UNPAID)
        payeur = self._creer_utilisateur('scan-reserve')

        with mock.patch('fedow_connect.fedow_api.FedowAPI') as fedow:
            fedow.return_value = self._fedow_qui_repond(solde_centimes=99999)
            reponse = self._navigateur_de(payeur).get(_chemin_de_scan(ligne.uuid.hex))

        assert any('payment_error' in nom for nom in self._gabarits_de(reponse))
        ligne.refresh_from_db()
        assert ligne.status == LigneArticle.UNPAID
        assert 'scanner_email' not in (ligne.metadata or '')

    def test_une_erreur_apres_le_debit_par_carte_repond_proprement(self):
        """Debit fait, enregistrement rate : une reponse lisible, pas une erreur 500 brute.

        Ici, la lecture de la monnaie debitee echoue apres le debit.
        / Here, reading the debited currency fails after the debit.
        """
        ligne = self._generer_un_qrcode()
        payeur = self._creer_utilisateur('nfc-apres-debit', avec_wallet=True)

        with mock.patch('BaseBillet.validators.FedowAPI') as fedow:
            faux_fedow = fedow.return_value
            faux_fedow.NFCcard.card_tag_id_retrieve.return_value = (
                self._carte_fedow(payeur.wallet.uuid)
            )
            faux_fedow.wallet.get_total_fiducial_and_all_federated_token.return_value = 99999
            faux_fedow.transaction.to_place_from_qrcode.return_value = [{
                'uuid': uuid_module.uuid4(),
                'asset': str(uuid_module.uuid4()),
                'amount': MONTANT_DEMANDE_CENTIMES,
            }]
            faux_fedow.asset.retrieve.side_effect = Exception('Fedow injoignable')
            reponse = self._poster_une_lecture_nfc('62FE1601', ligne)

        assert reponse.status_code == 500
        assert reponse.json()['detail']
