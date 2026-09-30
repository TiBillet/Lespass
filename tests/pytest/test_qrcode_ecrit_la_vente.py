"""
Tests du paiement par QR code et par carte NFC en ligne : le paiement écrit aussi sa
`Vente`, ses règlements, et les montants entiers de ses articles.
/ QR code and online NFC payment tests: the payment also writes its `Vente`, its
payments, and the whole-cent amounts of its items.

LOCALISATION : tests/pytest/test_qrcode_ecrit_la_vente.py

LE PARCOURS
1. Un encaisseur du lieu génère un QR code : une ligne « en attente » (la demande).
   Aucune vente n'existe encore.
2. L'adhérent confirme (`valid_payment`), ou l'encaisseur lit sa carte
   (`process_with_nfc`). La demande est réservée, puis l'ancien Fedow débite.
3. Tous les appels réseau passent AVANT la base : la catégorie de chaque monnaie
   débitée est lue sur l'ancien Fedow. Une erreur ici met la demande en échec
   (`FAILED`), sans aucune vente.
4. Une seule transaction de base : la demande est remplacée par une ligne par monnaie
   débitée (la première garde l'uuid de la demande), dans UNE vente encaissée
   (`REGLEE`, numérotée), d'origine « QR code » ou « NFC ». Un règlement par
   transaction de l'ancien Fedow, avec son uuid dans `reference_externe`.
5. Après la validation en base : les deux mails (au lieu, à l'adhérent). Aucun envoi à
   l'ancien LaBoutik.
/ Generate a request (no sale yet), confirm or tap a card, debit on the old Fedow,
every network call before the database, then one transaction writes the sale, its
parts and its payments; mails after commit, nothing sent to legacy LaBoutik.

RÈGLES MÉTIER TESTÉES
- La vente naît au paiement, jamais à la génération du QR code.
- Forme des lignes inchangée : `amount` = total payé, `qty` = la part de la monnaie
  (fraction de 1). Chaque part reçoit l'argent RÉEL débité dans sa monnaie
  (`total_catalogue`).
- Moyens : monnaie fédérée (FED) → « Stripe fédéré » (SF), monnaie locale (TLF) →
  « monnaie locale » (LE).
- Débit partiel : la vente enregistre ce qui a été réellement débité.
- L'anti-rejeu lit l'origine de la demande (`sale_origin`), plus son moyen de paiement.
/ The sale is born at payment; lines keep their shape; each part carries its real
debited money; partial debits are recorded as debited; the replay guard reads
`sale_origin`.

COMMENT CHAQUE TEST RETROUVE SA VENTE
Les tests tournent dans un schéma à eux (`FastTenantTestCase`), annulé à la fin de
chaque test : la seule vente du schéma est celle du test. Chaque test qui lit une vente
finit par `verifier_egalites(vente)` (tests/pytest/fabriques_vente.py). Le singleton
`LaboutikConfiguration` est créé à la main (tests/PIEGES.md 9.86) : il porte la clé de
l'empreinte des ventes.
/ Dedicated schema, rolled back after each test: the only sale is the test's own.

SIMULATIONS
- L'ancien Fedow est simulé : `fedow_connect.fedow_api.FedowAPI` pour la confirmation
  du QR code (la vue l'importe DANS la méthode), `BaseBillet.validators.FedowAPI` pour
  la lecture de carte. Ses transactions ont la forme de celles du vrai client
  (`TransactionValidator` : `uuid` et `asset` en `UUID`, `amount` en centimes). Tout
  envoi HTTP réel du client de l'ancien Fedow (`_get`, `_post`) fait échouer le test.
- Celery est simulé (`taches_celery_enregistrees`) : aucune tâche n'est envoyée au
  worker, on lit seulement leurs noms et leurs arguments.
- Les tâches demandées « après la validation en base » (`transaction.on_commit`) ne
  partent qu'avec `self.captureOnCommitCallbacks(execute=True)` (tests/PIEGES.md 13.1).
/ The old Fedow and Celery are faked; on_commit callbacks are captured explicitly.

CODE PARCOURU / CODE EXERCISED
- BaseBillet/views.py — QrCodeScanPay.generate_qrcode, valid_payment, process_with_nfc,
  check_payment ;
- BaseBillet/validators.py — QrCodeScanPayNfcValidator ;
- BaseBillet/services_vente.py — le service de vente.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-C-tireuse-qr.md (§2, §3, T2)
et CHANTIER-05-montants-entiers.md (§2).

Lancer / Run : make test ARGS="tests/pytest/test_qrcode_ecrit_la_vente.py"
"""

import uuid
from decimal import Decimal
from unittest import mock

from django.db import connection
from django.utils import translation
from django_tenants.test.cases import FastTenantTestCase
from django_tenants.test.client import TenantClient

from AuthBillet.models import TibilletUser, Wallet
from BaseBillet.models import LigneArticle, PaymentMethod, SaleOrigin
from BaseBillet.models_vente import Reglement, Vente
from fabriques_panier import (
    configuration_modifiee,
    noms_des_taches,
    taches_celery_enregistrees,
)
from fabriques_vente import verifier_egalites

# Montant demandé par le QR code, en centimes.
# / Amount requested by the QR code, in cents.
MONTANT_DEMANDE_EN_CENTIMES = 1250

URL_DE_LA_GENERATION_DU_QRCODE = "/qrcodescanpay/generate_qrcode/"
URL_DE_LA_CONFIRMATION_DU_PAIEMENT = "/qrcodescanpay/valid_payment/"
URL_DE_LA_LECTURE_DE_CARTE = "/qrcodescanpay/process_with_nfc/"

# Le message de la vue quand l'ancien Fedow échoue après la réservation de la demande :
# on ne sait pas ce qu'il a fait, la demande passe en échec. Le texte source est en
# français (msgid) ; le test le traduit dans la langue de la réponse.
# / The view's message when the old Fedow fails after the request is reserved.
MESSAGE_DEBIT_INCERTAIN = (
    "Le paiement n'a pas pu être confirmé. Demandez au lieu de vérifier votre "
    "portefeuille avant de réessayer."
)

# Les deux mails d'un paiement réussi : au lieu, puis à l'adhérent.
# / The two mails of a successful payment: to the venue, then to the member.
MAILS_D_UN_PAIEMENT_REUSSI = [
    "send_payment_success_admin",
    "send_payment_success_user",
]


def _chemin_de_verification(uuid_hex):
    """La route que l'écran de l'encaisseur interroge en boucle.
    / The route the collector's screen polls."""
    return f"/qrcodescanpay/{uuid_hex}/check_payment/"


def _transaction_de_l_ancien_fedow(uuid_de_la_monnaie, montant_en_centimes):
    """
    Une transaction telle que la rend le client de l'ancien Fedow après un débit
    (`TransactionValidator.validated_data`) : son uuid, sa monnaie, son montant.
    / A transaction as returned by the old Fedow client after a debit.
    """
    return {
        "uuid": uuid.uuid4(),
        "asset": uuid_de_la_monnaie,
        "amount": montant_en_centimes,
    }


def _fiches_des_monnaies(categories_par_monnaie):
    """
    Le faux `asset.retrieve` : rend la fiche de la monnaie demandée (sa catégorie).
    / The fake `asset.retrieve`: returns the requested currency's record.

    :param categories_par_monnaie: {uuid de la monnaie (UUID): "FED" / "TLF" / ...}
    """
    categories_par_uuid_texte = {}
    for uuid_de_la_monnaie, categorie in categories_par_monnaie.items():
        categories_par_uuid_texte[str(uuid_de_la_monnaie)] = categorie

    def fiche_de_la_monnaie(uuid_texte):
        return {"category": categories_par_uuid_texte[uuid_texte]}

    return fiche_de_la_monnaie


class TestPaiementQrCodeEcritLaVente(FastTenantTestCase):
    """
    Le paiement QR / NFC écrit sa vente, dans un schéma dédié (rollback à la fin de
    chaque test).
    / QR / NFC payment writes its sale, in a dedicated schema.
    """

    @classmethod
    def get_test_schema_name(cls):
        return "test_qrcode_vente"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-qrcode-vente.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        """`Client.name` est unique et obligatoire. / Client.name is unique."""
        tenant.name = "Test QR code écrit la vente"

    def setUp(self):
        """
        Le lieu du test, le singleton de la caisse, un encaisseur, Celery simulé, et
        l'interdiction de tout envoi réseau réel vers l'ancien Fedow.
        / Test venue, register singleton, a collector, faked Celery, no real network.
        """
        from laboutik.models import LaboutikConfiguration

        # Le rollback du test précédent a rendu le `search_path` au public.
        # / The previous test's rollback returned the search_path to public.
        connection.set_tenant(self.tenant)

        # Le singleton de la caisse doit exister en base (PIEGES 9.86) : il porte la
        # clé de l'empreinte des ventes.
        # / The register singleton must exist in the database: it holds the HMAC key.
        LaboutikConfiguration.get_solo().save()

        # Toutes les tâches Celery sont interceptées : on lit leurs noms, rien ne part.
        # / Every Celery task is intercepted: we read their names, nothing is sent.
        self.taches_demandees = self.enterContext(taches_celery_enregistrees())

        # Aucun envoi HTTP réel vers l'ancien Fedow : le test échoue s'il y en a un.
        # / No real HTTP call to the old Fedow: the test fails if one happens.
        envoi_reseau_interdit = AssertionError(
            "Appel réseau réel vers l'ancien Fedow interdit dans un test pytest."
        )
        self.enterContext(
            mock.patch(
                "fedow_connect.fedow_api._post", side_effect=envoi_reseau_interdit
            )
        )
        self.enterContext(
            mock.patch(
                "fedow_connect.fedow_api._get", side_effect=envoi_reseau_interdit
            )
        )

        self.encaisseur = self._creer_utilisateur("encaisseur-qr-vente")
        # Le droit `initiate_payment` distingue celui qui ENCAISSE de celui qui PAIE.
        # / The initiate_payment right distinguishes the collector from the payer.
        self.encaisseur.initiate_payment.add(self.tenant)
        self.navigateur_encaisseur = TenantClient(self.tenant)
        self.navigateur_encaisseur.force_login(self.encaisseur)

    # ------------------------------------------------------------------
    # Assistants / Helpers
    # ------------------------------------------------------------------

    def _creer_utilisateur(self, prefixe, avec_wallet=False):
        """
        Un utilisateur jetable, adresse confirmée, avec ou sans portefeuille local.
        `TibilletUser` vit en SHARED_APPS : l'adresse porte un suffixe unique.
        / A throwaway user with a confirmed address, with or without a local wallet.
        """
        adresse = f"{prefixe}-{uuid.uuid4().hex[:8]}@tibillet.localhost"
        utilisateur = TibilletUser.objects.create(
            email=adresse,
            username=adresse,
            is_active=True,
            email_valid=True,
        )
        if avec_wallet:
            utilisateur.wallet = Wallet.objects.create(name=f"Wallet {adresse}")
            utilisateur.save()
        return utilisateur

    def _navigateur_de(self, utilisateur):
        """Un client HTTP connecté sous cette identité.
        / An HTTP client logged in as this identity."""
        navigateur = TenantClient(self.tenant)
        navigateur.force_login(utilisateur)
        return navigateur

    def _generer_un_qrcode(self):
        """
        L'encaisseur génère un QR code de 12,50 €. Rend la demande (ligne « en
        attente »), retrouvée par l'uuid lu dans la page rendue.
        / The collector generates a 12.50 € QR code; returns the pending request.
        """
        reponse = self.navigateur_encaisseur.post(
            URL_DE_LA_GENERATION_DU_QRCODE,
            data={
                "amount": str(MONTANT_DEMANDE_EN_CENTIMES / 100),
                "asset_type": "EUR",
            },
        )
        assert reponse.status_code == 200, reponse.content.decode()[:400]
        uuid_de_la_demande = reponse.context["ligne_article_uuid_hex"]
        return LigneArticle.objects.get(uuid=uuid.UUID(uuid_de_la_demande))

    def _fedow_de_la_confirmation(self, transactions_du_debit, categories_par_monnaie):
        """
        L'ancien Fedow simulé pour la confirmation d'un QR code (`valid_payment`).
        Solde large ; le débit rend `transactions_du_debit`.
        / The faked old Fedow for a QR confirmation. Large balance.

        Le portefeuille rendu est un VRAI `Wallet` : la vue le pose sur les lignes
        (clé étrangère qui refuse un objet simulé).
        / The returned wallet is a REAL Wallet: the view stores it on the lines.
        """
        portefeuille_du_payeur = Wallet.objects.create(
            name=f"Wallet QR simule {uuid.uuid4().hex[:8]}"
        )
        faux_fedow = mock.MagicMock()
        faux_fedow.wallet.get_or_create_wallet.return_value = (
            portefeuille_du_payeur,
            False,
        )
        faux_fedow.wallet.get_total_fiducial_and_all_federated_token.return_value = (
            99999
        )
        faux_fedow.transaction.to_place_from_qrcode.return_value = transactions_du_debit
        faux_fedow.asset.retrieve.side_effect = _fiches_des_monnaies(
            categories_par_monnaie
        )
        return faux_fedow

    def _fedow_de_la_carte(self, payeur, transactions_du_debit, categories_par_monnaie):
        """
        L'ancien Fedow simulé pour une lecture de carte (`process_with_nfc`) : la
        carte est rattachée au portefeuille du payeur, le solde est large.
        / The faked old Fedow for a card read: card linked to the payer's wallet.
        """
        faux_fedow = mock.MagicMock()
        faux_fedow.NFCcard.card_tag_id_retrieve.return_value = {
            "wallet_uuid": str(payeur.wallet.uuid),
            "is_wallet_ephemere": False,
        }
        faux_fedow.wallet.get_total_fiducial_and_all_federated_token.return_value = (
            99999
        )
        faux_fedow.transaction.to_place_from_qrcode.return_value = transactions_du_debit
        faux_fedow.asset.retrieve.side_effect = _fiches_des_monnaies(
            categories_par_monnaie
        )
        return faux_fedow

    def _confirmer_le_paiement(self, payeur, demande, faux_fedow):
        """L'adhérent confirme le paiement du QR code.
        / The member confirms the QR code payment."""
        with mock.patch("fedow_connect.fedow_api.FedowAPI", return_value=faux_fedow):
            reponse = self._navigateur_de(payeur).post(
                URL_DE_LA_CONFIRMATION_DU_PAIEMENT,
                data={"ligne_article_uuid_hex": demande.uuid.hex},
            )
        return reponse

    def _lire_la_carte(self, tag_de_la_carte, demande, faux_fedow):
        """Le lecteur de l'encaisseur lit la carte de l'adhérent.
        / The collector's reader reads the member's card."""
        with mock.patch("BaseBillet.validators.FedowAPI", return_value=faux_fedow):
            reponse = self.navigateur_encaisseur.post(
                URL_DE_LA_LECTURE_DE_CARTE,
                data={
                    "tagSerial": tag_de_la_carte,
                    "ligne_article_uuid_hex": demande.uuid.hex,
                },
            )
        return reponse

    def _gabarits_de(self, reponse):
        """Les noms des gabarits rendus. / Names of the rendered templates."""
        noms = []
        for gabarit in reponse.templates:
            noms.append(gabarit.name or "")
        return noms

    def _message_traduit_comme_la_reponse(self, reponse, message_source):
        """
        Le message source (français), traduit dans la langue de la réponse.
        / The source message (French), translated into the response language.
        """
        langue_de_la_reponse = reponse.wsgi_request.LANGUAGE_CODE
        with translation.override(langue_de_la_reponse):
            return str(translation.gettext(message_source))

    # ------------------------------------------------------------------
    # 7 — Un QR code payé avec deux monnaies
    # ------------------------------------------------------------------

    def test_qr_paye_tlf_et_fed_deux_reglements_exacts(self):
        """
        Un QR code de 12,50 € est payé avec 5,00 € de monnaie locale (TLF) et 7,50 € de
        monnaie fédérée (FED). UNE vente « QR code » est encaissée (`REGLEE`,
        numérotée), au nom du payeur, sans carte, sans point de vente, sans opérateur.
        Elle a deux parts : chacune à `amount` = 1250, `qty` = sa fraction, et l'argent
        réel de sa monnaie (500 / 750). La première part garde l'uuid de la demande.
        Deux règlements : LE 500 et SF 750, chacun avec l'uuid de sa monnaie et l'uuid
        de sa transaction de l'ancien Fedow (`reference_externe`).
        / A 12.50 € QR code paid 5.00 TLF + 7.50 FED: one settled QR sale, two parts,
        two payments with the old Fedow transaction uuid.
        """
        demande = self._generer_un_qrcode()
        payeur = self._creer_utilisateur("qr-deux-monnaies")
        uuid_de_la_monnaie_locale = uuid.uuid4()
        uuid_de_la_monnaie_federee = uuid.uuid4()
        transaction_locale = _transaction_de_l_ancien_fedow(
            uuid_de_la_monnaie_locale, 500
        )
        transaction_federee = _transaction_de_l_ancien_fedow(
            uuid_de_la_monnaie_federee, 750
        )
        faux_fedow = self._fedow_de_la_confirmation(
            transactions_du_debit=[transaction_locale, transaction_federee],
            categories_par_monnaie={
                uuid_de_la_monnaie_locale: "TLF",
                uuid_de_la_monnaie_federee: "FED",
            },
        )

        reponse = self._confirmer_le_paiement(payeur, demande, faux_fedow)

        assert any(
            "payment_confirmation" in nom for nom in self._gabarits_de(reponse)
        ), self._gabarits_de(reponse)

        # La vente / The sale
        vente = Vente.objects.get()
        assert vente.origine == SaleOrigin.QRCODE_MA
        assert vente.nature == Vente.Nature.VENTE
        assert vente.statut == Vente.Statut.REGLEE
        assert vente.numero is not None
        assert vente.client_id == payeur.pk
        assert vente.carte_id is None
        assert vente.point_de_vente_id is None
        assert vente.operateur_id is None
        assert vente.total_ttc == MONTANT_DEMANDE_EN_CENTIMES

        # Les parts : forme inchangée, argent réel de chaque monnaie.
        # / The parts: unchanged shape, real money of each currency.
        parts_par_moyen = {}
        for part in vente.articles.all():
            parts_par_moyen[part.payment_method] = part
        assert sorted(parts_par_moyen.keys()) == sorted(
            [PaymentMethod.LOCAL_EURO, PaymentMethod.STRIPE_FED]
        )
        part_locale = parts_par_moyen[PaymentMethod.LOCAL_EURO]
        part_federee = parts_par_moyen[PaymentMethod.STRIPE_FED]
        assert part_locale.amount == MONTANT_DEMANDE_EN_CENTIMES
        assert part_federee.amount == MONTANT_DEMANDE_EN_CENTIMES
        assert part_locale.qty == Decimal("0.400000")
        assert part_federee.qty == Decimal("0.600000")
        assert part_locale.total_catalogue == 500
        assert part_federee.total_catalogue == 750
        assert part_locale.asset == uuid_de_la_monnaie_locale
        assert part_federee.asset == uuid_de_la_monnaie_federee
        assert part_locale.status == LigneArticle.VALID
        assert part_federee.status == LigneArticle.VALID
        assert part_locale.sale_origin == SaleOrigin.QRCODE_MA
        assert part_federee.sale_origin == SaleOrigin.QRCODE_MA
        # La part de la PREMIÈRE transaction débitée (ici la monnaie locale, rendue en
        # premier par l'ancien Fedow) garde l'uuid de la demande : l'écran de
        # l'encaisseur (`check_payment`) interroge cet uuid.
        # / The part of the FIRST debited transaction keeps the request uuid.
        assert part_locale.uuid == demande.uuid
        assert part_federee.uuid != demande.uuid

        # Plus aucune demande en attente ou en cours : tout est dans la vente.
        # / No pending or reserved request left: everything is in the sale.
        lignes_hors_vente = LigneArticle.objects.filter(
            sale_origin=SaleOrigin.QRCODE_MA, vente__isnull=True
        )
        assert lignes_hors_vente.count() == 0

        # Les règlements / The payments
        reglements_par_moyen = {}
        for reglement in vente.reglements.all():
            reglements_par_moyen[reglement.moyen] = reglement
        assert sorted(reglements_par_moyen.keys()) == sorted(
            [PaymentMethod.LOCAL_EURO, PaymentMethod.STRIPE_FED]
        )
        reglement_local = reglements_par_moyen[PaymentMethod.LOCAL_EURO]
        reglement_federe = reglements_par_moyen[PaymentMethod.STRIPE_FED]
        assert reglement_local.montant == 500
        assert reglement_federe.montant == 750
        assert reglement_local.asset == uuid_de_la_monnaie_locale
        assert reglement_federe.asset == uuid_de_la_monnaie_federee
        assert reglement_local.reference_externe == str(transaction_locale["uuid"])
        assert reglement_federe.reference_externe == str(transaction_federee["uuid"])
        # L'uuid distant va dans `reference_externe` : `fedow_transaction_uuid` est
        # réservé aux transactions `fedow_core` locales.
        # / The remote uuid goes to reference_externe; fedow_transaction_uuid is local only.
        assert reglement_local.fedow_transaction_uuid is None
        assert reglement_federe.fedow_transaction_uuid is None
        assert reglement_local.carte_id is None
        assert reglement_federe.carte_id is None

        verifier_egalites(vente)

    # ------------------------------------------------------------------
    # 8 — La vente naît au paiement
    # ------------------------------------------------------------------

    def test_qr_non_paye_aucune_vente(self):
        """
        Deux QR codes sont générés ; seul le second est payé. Il n'existe qu'UNE vente,
        celle du second. La demande du premier reste « en attente », hors de toute
        vente : générer un QR code ne crée jamais de vente.
        / Two QR codes, only the second one paid: exactly one sale, the unpaid request
        stays pending and outside any sale.
        """
        demande_jamais_payee = self._generer_un_qrcode()
        demande_payee = self._generer_un_qrcode()
        payeur = self._creer_utilisateur("qr-un-sur-deux")
        uuid_de_la_monnaie = uuid.uuid4()
        faux_fedow = self._fedow_de_la_confirmation(
            transactions_du_debit=[
                _transaction_de_l_ancien_fedow(
                    uuid_de_la_monnaie, MONTANT_DEMANDE_EN_CENTIMES
                )
            ],
            categories_par_monnaie={uuid_de_la_monnaie: "FED"},
        )

        self._confirmer_le_paiement(payeur, demande_payee, faux_fedow)

        assert Vente.objects.count() == 1
        vente = Vente.objects.get()
        uuids_des_parts = list(vente.articles.values_list("uuid", flat=True))
        assert uuids_des_parts == [demande_payee.uuid]

        demande_jamais_payee.refresh_from_db()
        assert demande_jamais_payee.status == LigneArticle.CREATED
        assert demande_jamais_payee.vente_id is None

        verifier_egalites(vente)

    # ------------------------------------------------------------------
    # 9 — Un paiement par carte NFC
    # ------------------------------------------------------------------

    def test_nfc_ma_une_vente_origine_nfc(self):
        """
        L'encaisseur lit la carte de l'adhérent pour un QR code de 12,50 €, payé en
        monnaie locale. UNE vente d'origine « NFC » est encaissée ; sa part porte
        l'origine NFC ; un règlement LE de 1250 avec l'uuid de la transaction de
        l'ancien Fedow. La réponse JSON du lecteur ne change pas.
        / A card read pays a 12.50 € QR code in local currency: one settled NFC sale,
        one LE payment with the remote transaction uuid; same JSON answer.
        """
        demande = self._generer_un_qrcode()
        payeur = self._creer_utilisateur("nfc-vente", avec_wallet=True)
        uuid_de_la_monnaie_locale = uuid.uuid4()
        transaction_locale = _transaction_de_l_ancien_fedow(
            uuid_de_la_monnaie_locale, MONTANT_DEMANDE_EN_CENTIMES
        )
        faux_fedow = self._fedow_de_la_carte(
            payeur,
            transactions_du_debit=[transaction_locale],
            categories_par_monnaie={uuid_de_la_monnaie_locale: "TLF"},
        )
        tag_sans_carte_locale = uuid.uuid4().hex[:8].upper()

        reponse = self._lire_la_carte(tag_sans_carte_locale, demande, faux_fedow)

        assert reponse.status_code == 202, reponse.content.decode()[:400]
        assert reponse.json()["status"] == "Paiement OK"
        assert reponse.json()["user_email"] == payeur.email
        assert Decimal(str(reponse.json()["amount_paid"])) == Decimal("12.50")

        vente = Vente.objects.get()
        assert vente.origine == SaleOrigin.NFC_MA
        assert vente.statut == Vente.Statut.REGLEE
        assert vente.numero is not None

        part = vente.articles.get()
        assert part.uuid == demande.uuid
        assert part.sale_origin == SaleOrigin.NFC_MA
        assert part.payment_method == PaymentMethod.LOCAL_EURO
        assert part.amount == MONTANT_DEMANDE_EN_CENTIMES
        assert part.qty == Decimal("1")
        assert part.total_catalogue == MONTANT_DEMANDE_EN_CENTIMES
        assert part.wallet_id == payeur.wallet.pk

        reglement = vente.reglements.get()
        assert reglement.moyen == PaymentMethod.LOCAL_EURO
        assert reglement.montant == MONTANT_DEMANDE_EN_CENTIMES
        assert reglement.asset == uuid_de_la_monnaie_locale
        assert reglement.reference_externe == str(transaction_locale["uuid"])

        verifier_egalites(vente)

    def test_nfc_vente_porte_la_carte_et_le_client(self):
        """
        La carte lue existe dans la base locale (`CarteCashless`, même tag). La vente
        porte cette carte et le payeur (le porteur de la carte), pas l'encaisseur. Le
        règlement porte la même carte.
        / The read card exists locally: the sale carries it and the payer (not the
        collector); the payment carries the same card.
        """
        from QrcodeCashless.models import CarteCashless

        demande = self._generer_un_qrcode()
        payeur = self._creer_utilisateur("nfc-carte-client", avec_wallet=True)
        tag_de_la_carte = uuid.uuid4().hex[:8].upper()
        carte_locale = CarteCashless.objects.create(
            tag_id=tag_de_la_carte,
            number=uuid.uuid4().hex[:8].upper(),
            user=payeur,
        )
        uuid_de_la_monnaie_federee = uuid.uuid4()
        faux_fedow = self._fedow_de_la_carte(
            payeur,
            transactions_du_debit=[
                _transaction_de_l_ancien_fedow(
                    uuid_de_la_monnaie_federee, MONTANT_DEMANDE_EN_CENTIMES
                )
            ],
            categories_par_monnaie={uuid_de_la_monnaie_federee: "FED"},
        )

        # Le lecteur envoie le tag en minuscules avec des deux-points : le validateur
        # le normalise avant de chercher la carte.
        # / The reader sends a lowercase tag with colons: the validator normalises it.
        tag_tel_que_lu = ":".join(
            tag_de_la_carte[position : position + 2].lower()
            for position in range(0, 8, 2)
        )
        reponse = self._lire_la_carte(tag_tel_que_lu, demande, faux_fedow)

        assert reponse.status_code == 202, reponse.content.decode()[:400]
        vente = Vente.objects.get()
        assert vente.carte_id == carte_locale.pk
        assert vente.client_id == payeur.pk
        assert vente.operateur_id is None
        reglement = vente.reglements.get()
        assert reglement.carte_id == carte_locale.pk

        verifier_egalites(vente)

    # ------------------------------------------------------------------
    # 10 — Erreur réseau APRÈS le débit : aucune vente, demande en échec
    # ------------------------------------------------------------------

    def test_qr_echec_reseau_apres_debit_aucune_vente_ligne_failed(self):
        """
        L'ancien Fedow débite, puis la lecture de la catégorie de la monnaie
        (`asset.retrieve`) échoue. Cette lecture a lieu AVANT la base : aucune ligne
        n'est recréée, aucune vente n'existe, la demande passe en échec (`FAILED`) et
        l'adhérent lit le même message que pour une erreur pendant le débit.
        / The debit succeeds, then reading the currency category fails, before the
        database: no line recreated, no sale, request FAILED, same message as a debit
        error.
        """
        demande = self._generer_un_qrcode()
        payeur = self._creer_utilisateur("qr-retrieve-ko")
        uuid_de_la_monnaie = uuid.uuid4()
        faux_fedow = self._fedow_de_la_confirmation(
            transactions_du_debit=[
                _transaction_de_l_ancien_fedow(
                    uuid_de_la_monnaie, MONTANT_DEMANDE_EN_CENTIMES
                )
            ],
            categories_par_monnaie={uuid_de_la_monnaie: "FED"},
        )
        faux_fedow.asset.retrieve.side_effect = ConnectionError("Fedow injoignable")

        reponse = self._confirmer_le_paiement(payeur, demande, faux_fedow)

        assert any("payment_error" in nom for nom in self._gabarits_de(reponse))
        message_attendu = self._message_traduit_comme_la_reponse(
            reponse, MESSAGE_DEBIT_INCERTAIN
        )
        assert str(reponse.context["error_message"]) == message_attendu
        assert faux_fedow.transaction.to_place_from_qrcode.call_count == 1

        lignes_du_qrcode = LigneArticle.objects.filter(sale_origin=SaleOrigin.QRCODE_MA)
        assert list(lignes_du_qrcode.values_list("uuid", flat=True)) == [demande.uuid]
        demande.refresh_from_db()
        assert demande.status == LigneArticle.FAILED
        assert Vente.objects.count() == 0
        assert Reglement.objects.count() == 0

    def test_nfc_echec_reseau_apres_debit_aucune_vente_ligne_failed(self):
        """
        Même règle par carte : débit fait, lecture de la catégorie en erreur. Aucune
        ligne recréée, aucune vente, demande en échec, réponse 500 avec le message
        d'un débit incertain.
        / Same rule for a card read: no line recreated, no sale, request FAILED,
        500 with the uncertain-debit message.
        """
        demande = self._generer_un_qrcode()
        payeur = self._creer_utilisateur("nfc-retrieve-ko", avec_wallet=True)
        uuid_de_la_monnaie = uuid.uuid4()
        faux_fedow = self._fedow_de_la_carte(
            payeur,
            transactions_du_debit=[
                _transaction_de_l_ancien_fedow(
                    uuid_de_la_monnaie, MONTANT_DEMANDE_EN_CENTIMES
                )
            ],
            categories_par_monnaie={uuid_de_la_monnaie: "TLF"},
        )
        faux_fedow.asset.retrieve.side_effect = ConnectionError("Fedow injoignable")

        reponse = self._lire_la_carte(uuid.uuid4().hex[:8].upper(), demande, faux_fedow)

        assert reponse.status_code == 500
        message_attendu = self._message_traduit_comme_la_reponse(
            reponse, MESSAGE_DEBIT_INCERTAIN
        )
        assert reponse.json()["detail"] == message_attendu
        assert faux_fedow.transaction.to_place_from_qrcode.call_count == 1

        lignes_du_qrcode = LigneArticle.objects.filter(
            sale_origin__in=[SaleOrigin.QRCODE_MA, SaleOrigin.NFC_MA]
        )
        assert list(lignes_du_qrcode.values_list("uuid", flat=True)) == [demande.uuid]
        demande.refresh_from_db()
        assert demande.status == LigneArticle.FAILED
        assert Vente.objects.count() == 0
        assert Reglement.objects.count() == 0

    # ------------------------------------------------------------------
    # 11 — Aucun envoi à l'ancien LaBoutik ; les mails après la validation en base
    # ------------------------------------------------------------------

    def test_qr_aucun_envoi_ancien_laboutik(self):
        """
        Un QR code payé avec deux monnaies : aucune tâche `send_sale_to_laboutik`
        demandée, même après la validation en base. Les deux mails (lieu, adhérent)
        sont demandés, et seulement APRÈS la validation en base (`on_commit`) : jamais
        un mail pour une vente qui n'existe pas.
        / A QR code paid with two currencies: no legacy LaBoutik task, even after
        commit; the two mails are requested, only after commit.
        """
        demande = self._generer_un_qrcode()
        payeur = self._creer_utilisateur("qr-sans-laboutik")
        uuid_de_la_monnaie_locale = uuid.uuid4()
        uuid_de_la_monnaie_federee = uuid.uuid4()
        faux_fedow = self._fedow_de_la_confirmation(
            transactions_du_debit=[
                _transaction_de_l_ancien_fedow(uuid_de_la_monnaie_locale, 500),
                _transaction_de_l_ancien_fedow(uuid_de_la_monnaie_federee, 750),
            ],
            categories_par_monnaie={
                uuid_de_la_monnaie_locale: "TLF",
                uuid_de_la_monnaie_federee: "FED",
            },
        )
        # On ne garde que les tâches demandées par la confirmation.
        # / Keep only the tasks requested by the confirmation.
        self.taches_demandees.clear()

        with self.captureOnCommitCallbacks(execute=True):
            reponse = self._confirmer_le_paiement(payeur, demande, faux_fedow)
            taches_avant_la_validation_en_base = noms_des_taches(self.taches_demandees)
        taches_apres_la_validation_en_base = noms_des_taches(self.taches_demandees)

        assert any("payment_confirmation" in nom for nom in self._gabarits_de(reponse))
        for nom_du_mail in MAILS_D_UN_PAIEMENT_REUSSI:
            assert nom_du_mail not in taches_avant_la_validation_en_base, (
                f"{nom_du_mail} demandé avant la validation en base : "
                f"{taches_avant_la_validation_en_base}"
            )
        assert taches_apres_la_validation_en_base == MAILS_D_UN_PAIEMENT_REUSSI

    def test_nfc_aucun_envoi_ancien_laboutik(self):
        """
        Même règle par carte : aucune tâche `send_sale_to_laboutik`, les deux mails
        seulement après la validation en base.
        / Same rule for a card read: no legacy LaBoutik task, mails only after commit.
        """
        demande = self._generer_un_qrcode()
        payeur = self._creer_utilisateur("nfc-sans-laboutik", avec_wallet=True)
        uuid_de_la_monnaie_locale = uuid.uuid4()
        uuid_de_la_monnaie_federee = uuid.uuid4()
        faux_fedow = self._fedow_de_la_carte(
            payeur,
            transactions_du_debit=[
                _transaction_de_l_ancien_fedow(uuid_de_la_monnaie_locale, 500),
                _transaction_de_l_ancien_fedow(uuid_de_la_monnaie_federee, 750),
            ],
            categories_par_monnaie={
                uuid_de_la_monnaie_locale: "TLF",
                uuid_de_la_monnaie_federee: "FED",
            },
        )
        self.taches_demandees.clear()

        with self.captureOnCommitCallbacks(execute=True):
            reponse = self._lire_la_carte(
                uuid.uuid4().hex[:8].upper(), demande, faux_fedow
            )
            taches_avant_la_validation_en_base = noms_des_taches(self.taches_demandees)
        taches_apres_la_validation_en_base = noms_des_taches(self.taches_demandees)

        assert reponse.status_code == 202, reponse.content.decode()[:400]
        for nom_du_mail in MAILS_D_UN_PAIEMENT_REUSSI:
            assert nom_du_mail not in taches_avant_la_validation_en_base, (
                f"{nom_du_mail} demandé avant la validation en base : "
                f"{taches_avant_la_validation_en_base}"
            )
        assert taches_apres_la_validation_en_base == MAILS_D_UN_PAIEMENT_REUSSI

    # ------------------------------------------------------------------
    # 12 — Refus de l'ancien Fedow pendant le débit
    # ------------------------------------------------------------------

    def test_qr_refus_fedow_aucune_vente(self):
        """
        L'ancien Fedow refuse le débit (il lève une erreur) : on ne sait pas ce qu'il a
        fait. La demande passe en échec (`FAILED`) et ne se paie plus jamais : une
        seconde confirmation ne rappelle pas l'ancien Fedow. Aucune vente, aucun
        règlement.
        / The old Fedow refuses the debit: request FAILED for good, a second
        confirmation does not call it again; no sale, no payment.
        """
        demande = self._generer_un_qrcode()
        payeur = self._creer_utilisateur("qr-refus")
        faux_fedow = self._fedow_de_la_confirmation(
            transactions_du_debit=[], categories_par_monnaie={}
        )
        faux_fedow.transaction.to_place_from_qrcode.side_effect = Exception(
            {"detail": "Solde insuffisant"}
        )

        premiere_reponse = self._confirmer_le_paiement(payeur, demande, faux_fedow)
        demande.refresh_from_db()
        statut_apres_la_premiere_confirmation = demande.status
        seconde_reponse = self._confirmer_le_paiement(payeur, demande, faux_fedow)

        assert any(
            "payment_error" in nom for nom in self._gabarits_de(premiere_reponse)
        )
        assert any("payment_error" in nom for nom in self._gabarits_de(seconde_reponse))
        assert statut_apres_la_premiere_confirmation == LigneArticle.FAILED
        demande.refresh_from_db()
        assert demande.status == LigneArticle.FAILED
        assert faux_fedow.transaction.to_place_from_qrcode.call_count == 1
        assert Vente.objects.count() == 0
        assert Reglement.objects.count() == 0

    # ------------------------------------------------------------------
    # Échec PENDANT l'écriture de la vente : rien n'est écrit, demande en échec
    # ------------------------------------------------------------------

    def test_qr_echec_ecriture_apres_debit_aucune_vente_ligne_failed(self):
        """
        L'ancien Fedow débite, puis l'encaissement de la vente échoue (égalité rompue,
        simulée). Tout est écrit dans UNE transaction de base : rien ne reste, ni
        vente, ni règlement, ni part. La demande passe en échec (`FAILED`) : le débit
        est fait, il ne se rejoue jamais. Une seconde confirmation ne rappelle pas
        l'ancien Fedow. L'adhérent lit le message d'erreur d'enregistrement.
        / The debit succeeds, then settling the sale fails: nothing is written, the
        request is FAILED, a second confirmation does not debit again.
        """
        from BaseBillet.services_vente import EgaliteDeVenteRompue

        demande = self._generer_un_qrcode()
        payeur = self._creer_utilisateur("qr-ecriture-ko")
        uuid_de_la_monnaie = uuid.uuid4()
        faux_fedow = self._fedow_de_la_confirmation(
            transactions_du_debit=[
                _transaction_de_l_ancien_fedow(
                    uuid_de_la_monnaie, MONTANT_DEMANDE_EN_CENTIMES
                )
            ],
            categories_par_monnaie={uuid_de_la_monnaie: "FED"},
        )

        with mock.patch(
            "BaseBillet.services_vente.encaisser_vente",
            side_effect=EgaliteDeVenteRompue("égalité rompue simulée"),
        ):
            premiere_reponse = self._confirmer_le_paiement(payeur, demande, faux_fedow)
            seconde_reponse = self._confirmer_le_paiement(payeur, demande, faux_fedow)

        assert any(
            "payment_error" in nom for nom in self._gabarits_de(premiere_reponse)
        )
        message_attendu = self._message_traduit_comme_la_reponse(
            premiere_reponse, "Error validating payment"
        )
        assert str(premiere_reponse.context["error_message"]) == message_attendu
        assert any("payment_error" in nom for nom in self._gabarits_de(seconde_reponse))
        assert faux_fedow.transaction.to_place_from_qrcode.call_count == 1

        lignes_du_qrcode = LigneArticle.objects.filter(sale_origin=SaleOrigin.QRCODE_MA)
        assert list(lignes_du_qrcode.values_list("uuid", flat=True)) == [demande.uuid]
        demande.refresh_from_db()
        assert demande.status == LigneArticle.FAILED
        assert Vente.objects.count() == 0
        assert Reglement.objects.count() == 0

    def test_nfc_echec_ecriture_apres_debit_aucune_vente_ligne_failed(self):
        """
        Même règle par carte : débit fait, encaissement en échec. Rien n'est écrit, la
        demande passe en échec, réponse 500 avec le message d'erreur d'enregistrement.
        / Same rule for a card read: nothing written, request FAILED, 500.
        """
        from BaseBillet.services_vente import EgaliteDeVenteRompue

        demande = self._generer_un_qrcode()
        payeur = self._creer_utilisateur("nfc-ecriture-ko", avec_wallet=True)
        uuid_de_la_monnaie = uuid.uuid4()
        faux_fedow = self._fedow_de_la_carte(
            payeur,
            transactions_du_debit=[
                _transaction_de_l_ancien_fedow(
                    uuid_de_la_monnaie, MONTANT_DEMANDE_EN_CENTIMES
                )
            ],
            categories_par_monnaie={uuid_de_la_monnaie: "TLF"},
        )

        with mock.patch(
            "BaseBillet.services_vente.encaisser_vente",
            side_effect=EgaliteDeVenteRompue("égalité rompue simulée"),
        ):
            reponse = self._lire_la_carte(
                uuid.uuid4().hex[:8].upper(), demande, faux_fedow
            )

        assert reponse.status_code == 500
        message_attendu = self._message_traduit_comme_la_reponse(
            reponse, "Error validating payment"
        )
        assert reponse.json()["detail"] == message_attendu
        assert faux_fedow.transaction.to_place_from_qrcode.call_count == 1

        lignes_du_qrcode = LigneArticle.objects.filter(
            sale_origin__in=[SaleOrigin.QRCODE_MA, SaleOrigin.NFC_MA]
        )
        assert list(lignes_du_qrcode.values_list("uuid", flat=True)) == [demande.uuid]
        demande.refresh_from_db()
        assert demande.status == LigneArticle.FAILED
        assert Vente.objects.count() == 0
        assert Reglement.objects.count() == 0

    # ------------------------------------------------------------------
    # TVA : le taux du lieu
    # ------------------------------------------------------------------

    def test_qr_tva_taux_du_lieu(self):
        """
        Le produit « vente par QR code » n'a pas de taux de TVA : chaque part porte le
        taux par défaut du lieu (ici 20 %). 12,50 € payés 5,00 € (TLF) + 7,50 € (FED) :
        HT 417 + TVA 83 = 500 ; HT 625 + TVA 125 = 750. HT + TVA = net sur chaque part.
        Le taux du lieu est posé en mémoire, jamais enregistré (tests/PIEGES.md 13.5).
        / The QR product has no VAT rate: each part carries the venue default (20 %).
        """
        demande = self._generer_un_qrcode()
        payeur = self._creer_utilisateur("qr-tva")
        uuid_de_la_monnaie_locale = uuid.uuid4()
        uuid_de_la_monnaie_federee = uuid.uuid4()
        faux_fedow = self._fedow_de_la_confirmation(
            transactions_du_debit=[
                _transaction_de_l_ancien_fedow(uuid_de_la_monnaie_locale, 500),
                _transaction_de_l_ancien_fedow(uuid_de_la_monnaie_federee, 750),
            ],
            categories_par_monnaie={
                uuid_de_la_monnaie_locale: "TLF",
                uuid_de_la_monnaie_federee: "FED",
            },
        )

        with configuration_modifiee(vat_taxe=Decimal("20.00")):
            self._confirmer_le_paiement(payeur, demande, faux_fedow)

        vente = Vente.objects.get()
        montants_par_moyen = {}
        for part in vente.articles.all():
            assert part.vat == Decimal("20.00")
            assert part.total_ht + part.total_tva == part.total_ttc
            montants_par_moyen[part.payment_method] = (part.total_ht, part.total_tva)
        assert montants_par_moyen == {
            PaymentMethod.LOCAL_EURO: (417, 83),
            PaymentMethod.STRIPE_FED: (625, 125),
        }

        verifier_egalites(vente)

    # ------------------------------------------------------------------
    # Débit partiel : la vente enregistre ce qui a été débité
    # ------------------------------------------------------------------

    def test_qr_debit_partiel_vente_du_montant_debite(self):
        """
        12,50 € demandés, l'ancien Fedow débite 5,00 € (TLF) + 7,00 € (FED). La vente
        vaut 12,00 € : chaque part porte le montant débité (`amount` = 1200), ses
        totaux 500 et 700, deux règlements 500 et 700. Les égalités tiennent.
        / 12.50 requested, 12.00 debited: the sale is worth 12.00, equalities hold.
        """
        demande = self._generer_un_qrcode()
        payeur = self._creer_utilisateur("qr-partiel")
        uuid_de_la_monnaie_locale = uuid.uuid4()
        uuid_de_la_monnaie_federee = uuid.uuid4()
        faux_fedow = self._fedow_de_la_confirmation(
            transactions_du_debit=[
                _transaction_de_l_ancien_fedow(uuid_de_la_monnaie_locale, 500),
                _transaction_de_l_ancien_fedow(uuid_de_la_monnaie_federee, 700),
            ],
            categories_par_monnaie={
                uuid_de_la_monnaie_locale: "TLF",
                uuid_de_la_monnaie_federee: "FED",
            },
        )

        self._confirmer_le_paiement(payeur, demande, faux_fedow)

        vente = Vente.objects.get()
        assert vente.statut == Vente.Statut.REGLEE
        assert vente.total_ttc == 1200

        totaux_des_parts = []
        for part in vente.articles.all():
            assert part.amount == 1200
            totaux_des_parts.append(part.total_catalogue)
        assert sorted(totaux_des_parts) == [500, 700]

        montants_des_reglements = []
        for reglement in vente.reglements.all():
            montants_des_reglements.append(reglement.montant)
        assert sorted(montants_des_reglements) == [500, 700]

        verifier_egalites(vente)

    # ------------------------------------------------------------------
    # T2 — L'anti-rejeu lit l'origine de la demande, plus son moyen de paiement
    # ------------------------------------------------------------------

    def test_anti_rejeu_qr_ne_lit_plus_payment_method(self):
        """
        La demande n'a plus de moyen de paiement « QR code » (le champ disparaît en
        fiche H), mais son origine reste « QR code ». Elle se paie une fois : vente
        encaissée. Une seconde confirmation est refusée sans rappeler l'ancien Fedow.
        / The request no longer carries the QR payment method, only the QR origin: it is
        paid once, a second confirmation is refused without a second debit.
        """
        demande = self._generer_un_qrcode()
        LigneArticle.objects.filter(pk=demande.pk).update(payment_method=None)
        payeur = self._creer_utilisateur("qr-t2")
        uuid_de_la_monnaie = uuid.uuid4()
        faux_fedow = self._fedow_de_la_confirmation(
            transactions_du_debit=[
                _transaction_de_l_ancien_fedow(
                    uuid_de_la_monnaie, MONTANT_DEMANDE_EN_CENTIMES
                )
            ],
            categories_par_monnaie={uuid_de_la_monnaie: "FED"},
        )

        premiere_reponse = self._confirmer_le_paiement(payeur, demande, faux_fedow)
        seconde_reponse = self._confirmer_le_paiement(payeur, demande, faux_fedow)

        assert any(
            "payment_confirmation" in nom for nom in self._gabarits_de(premiere_reponse)
        ), self._gabarits_de(premiere_reponse)
        assert any("payment_error" in nom for nom in self._gabarits_de(seconde_reponse))
        assert faux_fedow.transaction.to_place_from_qrcode.call_count == 1

        vente = Vente.objects.get()
        assert vente.statut == Vente.Statut.REGLEE
        verifier_egalites(vente)

    def test_anti_rejeu_nfc_ne_lit_plus_payment_method(self):
        """
        Même règle par carte (validateur ET réservation de la vue) : une demande
        d'origine « QR code » sans moyen de paiement « QR code » se paie une fois ; une
        seconde lecture de carte est refusée sans rappeler l'ancien Fedow.
        / Same rule for a card read (validator AND view reservation).
        """
        demande = self._generer_un_qrcode()
        LigneArticle.objects.filter(pk=demande.pk).update(payment_method=None)
        payeur = self._creer_utilisateur("nfc-t2", avec_wallet=True)
        uuid_de_la_monnaie = uuid.uuid4()
        faux_fedow = self._fedow_de_la_carte(
            payeur,
            transactions_du_debit=[
                _transaction_de_l_ancien_fedow(
                    uuid_de_la_monnaie, MONTANT_DEMANDE_EN_CENTIMES
                )
            ],
            categories_par_monnaie={uuid_de_la_monnaie: "TLF"},
        )
        tag_de_la_carte = uuid.uuid4().hex[:8].upper()

        premiere_reponse = self._lire_la_carte(tag_de_la_carte, demande, faux_fedow)
        seconde_reponse = self._lire_la_carte(tag_de_la_carte, demande, faux_fedow)

        assert premiere_reponse.status_code == 202, premiere_reponse.content.decode()[
            :400
        ]
        assert seconde_reponse.status_code == 400
        assert faux_fedow.transaction.to_place_from_qrcode.call_count == 1

        vente = Vente.objects.get()
        assert vente.statut == Vente.Statut.REGLEE
        verifier_egalites(vente)

    # ------------------------------------------------------------------
    # check_payment — l'écran de l'encaisseur annonce le paiement
    # ------------------------------------------------------------------

    def test_qr_paye_check_payment_annonce_le_paiement(self):
        """
        Après le paiement, l'écran de l'encaisseur interroge `check_payment` avec l'uuid
        de la DEMANDE (celui du QR code affiché). Il doit lire « payé » : c'est pourquoi
        la première part de la vente garde cet uuid.
        / After payment, the collector's screen polls check_payment with the REQUEST
        uuid and must read "paid".
        """
        demande = self._generer_un_qrcode()
        payeur = self._creer_utilisateur("qr-check")
        uuid_de_la_monnaie = uuid.uuid4()
        faux_fedow = self._fedow_de_la_confirmation(
            transactions_du_debit=[
                _transaction_de_l_ancien_fedow(
                    uuid_de_la_monnaie, MONTANT_DEMANDE_EN_CENTIMES
                )
            ],
            categories_par_monnaie={uuid_de_la_monnaie: "FED"},
        )
        self._confirmer_le_paiement(payeur, demande, faux_fedow)

        reponse = self.navigateur_encaisseur.get(
            _chemin_de_verification(demande.uuid.hex)
        )

        assert reponse.status_code == 200
        assert reponse.context["is_valid"] is True
