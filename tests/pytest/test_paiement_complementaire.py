"""
tests/pytest/test_paiement_complementaire.py — Paiement POS complémentaire (NFC + 2e moyen).

Couvre le flux « fonds insuffisants » : 1ère carte NFC partielle, puis complément
par espèce, CB, ou 2ème carte NFC. Met l'accent sur le cas CRITIQUE « 2ème carte
NFC insuffisante » : le paiement doit S'ARRÊTER (pas de 3ème étape), retour à
l'écran complément SANS le bouton 2ème carte, AUCUN débit, AUCUNE LigneArticle.

/ POS complementary payment flow (insufficient funds): 1st NFC card partial, then
complement by cash, CC, or 2nd NFC card. Focus on the CRITICAL case « 2nd NFC card
insufficient »: payment must STOP (no 3rd step), no debit, no LigneArticle.

Fedow est MOCKÉ (can_fedow=False) : la cascade reste 100% locale (TLF), sans réseau.
Les cartes sont liées à des users avec wallet local → _obtenir_ou_creer_wallet
retourne le wallet du user SANS appeler Fedow.
/ Fedow MOCKED (can_fedow=False): cascade stays 100% local (TLF), no network.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_paiement_complementaire.py -v
"""

import sys

sys.path.insert(0, '/DjangoFiles')

import django

django.setup()

import html
import re
from decimal import Decimal
from unittest import mock

from django.db import connection
from django_tenants.test.cases import FastTenantTestCase
from django_tenants.test.client import TenantClient

from AuthBillet.models import TibilletUser, Wallet
from BaseBillet.models import (
    CategorieProduct, Configuration, LigneArticle, PaymentMethod, Price, Product,
    SaleOrigin,
)
from QrcodeCashless.models import CarteCashless
from fedow_core.models import Asset, Token
from fedow_core.services import AssetService, WalletService
from laboutik.models import PointDeVente


def _extraire_hidden(contenu_html, nom_champ):
    """Extrait la valeur d'un <input type=hidden name=...> du HTML rendu.
    / Extracts a hidden input value from rendered HTML."""
    motif = re.compile(
        r'name="' + re.escape(nom_champ) + r'"\s+value="([^"]*)"'
    )
    correspondance = motif.search(contenu_html)
    if correspondance is None:
        return None
    # Le HTML échappe les guillemets du JSON en &quot; → on déséchappe.
    # / HTML escapes JSON quotes as &quot; → unescape.
    return html.unescape(correspondance.group(1))


def _extraire_reste(contenu_html):
    """Extrait le « reste à payer » (en euros, ex. '1.00') de l'écran complément.
    / Extracts the 'remaining to pay' amount from the complement screen."""
    motif = re.compile(
        r'complement-reste-a-payer.*?<strong>\s*([0-9.]+)\s*€', re.DOTALL
    )
    correspondance = motif.search(contenu_html)
    return correspondance.group(1) if correspondance else None


class TestPaiementComplementaire(FastTenantTestCase):
    """1 classe FastTenantTestCase = 1 schema isolé, rollback entre tests.
    / 1 FastTenantTestCase class = 1 isolated schema, rollback between tests."""

    @classmethod
    def get_test_schema_name(cls):
        return 'test_complement'

    @classmethod
    def get_test_tenant_domain(cls):
        return 'test-complement.tibillet.localhost'

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.name = 'Test Complément'

    def setUp(self):
        connection.set_tenant(self.tenant)

        # Module caisse actif (le garde HasLaBoutikTerminalAccess l'exige).
        # / Cash register module active (required by the guard).
        config = Configuration.get_solo()
        config.module_monnaie_locale = True
        config.module_caisse = True
        config.save()

        # Wallet du lieu (origine de l'asset) + asset monnaie locale TLF.
        # / Venue wallet (asset origin) + local currency asset TLF.
        self.wallet_lieu = Wallet.objects.create(
            origin=self.tenant, name='Wallet lieu test'
        )
        self.asset_tlf = AssetService.creer_asset(
            tenant=self.tenant,
            name='Monnaie locale test',
            category=Asset.TLF,
            currency_code='EUR',
            wallet_origin=self.wallet_lieu,
        )

        # Catégorie + produit « Vin blanc » à 5,00 € (prix EUR, asset=None).
        # / Category + « Vin blanc » product at 5.00 € (EUR price).
        self.categorie = CategorieProduct.objects.create(name='Vins')
        self.produit = Product.objects.create(
            name='Vin blanc',
            methode_caisse=Product.VENTE,
            categorie_pos=self.categorie,
        )
        self.prix = Price.objects.create(
            product=self.produit,
            name='Tarif Vin blanc',
            prix=Decimal('5.00'),
            publish=True,
        )

        # Point de vente Bar (espèces + CB acceptés).
        # / Bar POS (cash + CC accepted).
        self.pv = PointDeVente.objects.create(
            name='Bar',
            comportement=PointDeVente.DIRECT,
            service_direct=True,
            accepte_especes=True,
            accepte_carte_bancaire=True,
        )
        self.pv.products.add(self.produit)

        # 2 cartes clientes, chacune liée à un user avec wallet local.
        # / 2 client cards, each linked to a user with a local wallet.
        self.carte1, self.wallet1 = self._creer_carte_avec_wallet('CPL1AAAA', 'client1')
        self.carte2, self.wallet2 = self._creer_carte_avec_wallet('CPL2BBBB', 'client2')

        # Soldes : carte1 = 6,00 € TLF, carte2 = 8,00 € TLF.
        # / Balances: card1 = €6.00 TLF, card2 = €8.00 TLF.
        Token.objects.create(wallet=self.wallet1, asset=self.asset_tlf, value=600)
        Token.objects.create(wallet=self.wallet2, asset=self.asset_tlf, value=800)

        # Caissier : admin du tenant, session navigateur (bypass carte primaire).
        # / Cashier: tenant admin, browser session (bypasses primary card check).
        self.admin, _ = TibilletUser.objects.get_or_create(
            email='admin-complement@tibillet.localhost',
            defaults={
                'username': 'admin-complement@tibillet.localhost',
                'is_staff': True,
                'is_active': True,
            },
        )
        self.admin.client_admin.add(self.tenant)
        self.client_http = TenantClient(self.tenant)
        self.client_http.force_login(self.admin)

    def _creer_carte_avec_wallet(self, tag_id, prefixe_email):
        """Crée un user + wallet local + CarteCashless liée.
        / Creates a user + local wallet + linked CarteCashless."""
        user = TibilletUser.objects.create(
            email=f'{prefixe_email}-complement@tibillet.localhost',
            username=f'{prefixe_email}-complement@tibillet.localhost',
        )
        wallet = Wallet.objects.create(origin=self.tenant, name=f'Wallet {prefixe_email}')
        user.wallet = wallet
        user.save()
        carte = CarteCashless.objects.create(tag_id=tag_id, number=tag_id, user=user)
        return carte, wallet

    # ------------------------------------------------------------------ #
    #  Helpers HTTP
    # ------------------------------------------------------------------ #

    def _post_payer_nfc(self, tag_id, quantite):
        """POST /laboutik/paiement/payer/ moyen=nfc (1ère carte).
        / POST payer moyen=nfc (1st card)."""
        prix_centimes = int(round(self.prix.prix * 100))
        data = {
            'uuid_pv': str(self.pv.uuid),
            'moyen_paiement': 'nfc',
            'total': str(prix_centimes * quantite),
            'given_sum': '0',
            'tag_id': tag_id,
            f'repid-{self.produit.uuid}': str(quantite),
        }
        return self.client_http.post('/laboutik/paiement/payer/', data=data)

    def _post_complementaire_nfc(self, tag_id_carte2, tag_id_carte1,
                                 cascade_carte1, total_nfc_carte1, quantite):
        """POST /laboutik/paiement/payer_complementaire/ moyen_complement=nfc (2e carte).
        / POST payer_complementaire moyen_complement=nfc (2nd card)."""
        data = {
            'uuid_pv': str(self.pv.uuid),
            'moyen_complement': 'nfc',
            'tag_id': tag_id_carte2,
            'tag_id_carte1': tag_id_carte1,
            'cascade_carte1': cascade_carte1,
            'total_nfc_carte1': total_nfc_carte1,
            f'repid-{self.produit.uuid}': str(quantite),
        }
        return self.client_http.post(
            '/laboutik/paiement/payer_complementaire/', data=data
        )

    # ------------------------------------------------------------------ #
    #  Test : NFC1 + NFC2 insuffisante → STOP
    # ------------------------------------------------------------------ #

    def test_2e_carte_nfc_insuffisante_arrete_sans_debit_ni_ligne(self):
        """3 vins (15 €), carte1 TLF 6 € + carte2 TLF 8 € → 8 < reste 9 € : STOP.

        Le paiement s'arrête : retour à l'écran complément SANS le bouton 2e carte
        (pas de 3e étape), AUCUN débit (les 2 cartes gardent leur solde), AUCUNE
        LigneArticle, AUCUN ticket (paiement non finalisé).
        / 2nd card insufficient → STOP: complement screen without the 2nd-card
        button, no debit, no LigneArticle.
        """
        with (
            mock.patch('laboutik.views.FedowConfig') as MockConfig,
            mock.patch('laboutik.views.FedowAPI'),
        ):
            MockConfig.get_solo.return_value.can_fedow.return_value = False

            # --- Étape 1 : carte1 NFC, fonds insuffisants → écran complément ---
            reponse1 = self._post_payer_nfc(tag_id=self.carte1.tag_id, quantite=3)
            assert reponse1.status_code == 200
            contenu1 = reponse1.content.decode()
            assert 'data-testid="complement-paiement"' in contenu1, contenu1[:500]
            # La 2ème carte EST proposée à cette étape.
            assert 'data-testid="btn-complement-2eme-carte"' in contenu1
            # Reste à payer = 9,00 € (15 - 6 couverts par carte1).
            assert '9.00' in contenu1

            cascade_carte1 = _extraire_hidden(contenu1, 'cascade_carte1')
            total_nfc_carte1 = _extraire_hidden(contenu1, 'total_nfc_carte1')
            assert cascade_carte1 is not None

            # --- Étape 2 : complément carte2 NFC (8 € < 9 €) → insuffisant ---
            reponse2 = self._post_complementaire_nfc(
                tag_id_carte2=self.carte2.tag_id,
                tag_id_carte1=self.carte1.tag_id,
                cascade_carte1=cascade_carte1,
                total_nfc_carte1=total_nfc_carte1,
                quantite=3,
            )
            assert reponse2.status_code == 200
            contenu2 = reponse2.content.decode()

        # --- Le paiement S'ARRÊTE : écran complément SANS 2e carte (pas de 3e étape) ---
        assert 'data-testid="complement-paiement"' in contenu2
        assert 'data-testid="btn-complement-2eme-carte"' not in contenu2, (
            "Le bouton 2ème carte ne doit PLUS apparaître : pas de 3ème étape."
        )
        # Espèces / CB restent proposés pour solder le reste.
        assert 'data-testid="btn-complement-especes"' in contenu2

        # --- AUCUNE LigneArticle (paiement non finalisé) ---
        assert LigneArticle.objects.filter(
            sale_origin=SaleOrigin.LABOUTIK,
        ).count() == 0

        # --- Les 2 cartes gardent leur solde (aucun débit) ---
        assert WalletService.obtenir_solde(self.wallet1, self.asset_tlf) == 600
        assert WalletService.obtenir_solde(self.wallet2, self.asset_tlf) == 800

    # ------------------------------------------------------------------ #
    #  Test : NFC1 + espèce → succès, montants comptables corrects
    # ------------------------------------------------------------------ #

    def _post_complementaire_espece(self, tag_id_carte1, cascade_carte1,
                                    total_nfc_carte1, quantite):
        """POST payer_complementaire moyen_complement=espece.
        / POST payer_complementaire moyen_complement=espece."""
        data = {
            'uuid_pv': str(self.pv.uuid),
            'moyen_complement': 'espece',
            'tag_id_carte1': tag_id_carte1,
            'cascade_carte1': cascade_carte1,
            'total_nfc_carte1': total_nfc_carte1,
            f'repid-{self.produit.uuid}': str(quantite),
        }
        return self.client_http.post(
            '/laboutik/paiement/payer_complementaire/', data=data
        )

    def test_cloture_cascade_fractionnee_totaux_corrects(self):
        """Bug B, volet clôture : vente NFC fractionnée (6 € TLF + 9 € espèces).

        Le rapport comptable (RapportComptableService, qui agrège amount × qty avec
        arrondi au centime) doit donner : total 15 €, cashless 6 €, espèces 9 € —
        malgré les qty fractionnaires (1,2 et 1,8). Verrouille reports.py.
        / Cloture report with fractional qty must total 15 €, cashless 6 €, cash 9 €.
        """
        from django.utils import timezone
        from datetime import timedelta
        from laboutik.reports import RapportComptableService

        with (
            mock.patch('laboutik.views.FedowConfig') as MockConfig,
            mock.patch('laboutik.views.FedowAPI'),
        ):
            MockConfig.get_solo.return_value.can_fedow.return_value = False
            reponse1 = self._post_payer_nfc(tag_id=self.carte1.tag_id, quantite=3)
            contenu1 = reponse1.content.decode()
            cascade_carte1 = _extraire_hidden(contenu1, 'cascade_carte1')
            total_nfc_carte1 = _extraire_hidden(contenu1, 'total_nfc_carte1')
            self._post_complementaire_espece(
                tag_id_carte1=self.carte1.tag_id,
                cascade_carte1=cascade_carte1,
                total_nfc_carte1=total_nfc_carte1,
                quantite=3,
            )

        debut = timezone.now() - timedelta(hours=1)
        fin = timezone.now() + timedelta(hours=1)
        rapport = RapportComptableService(self.pv, debut, fin)
        totaux = rapport.calculer_totaux_par_moyen()

        # Totaux en centimes ENTIERS, malgré les qty 1,2 / 1,8.
        # / Integer-cent totals despite fractional qty 1.2 / 1.8.
        assert totaux["total"] == 1500, f"Total clôture attendu 1500, obtenu {totaux['total']}"
        assert totaux["cashless"] == 600, f"Cashless attendu 600, obtenu {totaux['cashless']}"
        assert totaux["especes"] == 900, f"Espèces attendu 900, obtenu {totaux['especes']}"

    def test_nfc1_puis_espece_montants_comptables_corrects(self):
        """3 vins (15 €), carte1 TLF 6 € + complément 9 € en espèces → succès.

        Vérifie le BUG suspecté du « 45 € » : la somme des LigneArticle doit être
        15,00 € (1500 centimes), PAS 45,00 € (3 × 15). Et carte1 est débitée de 6 €.
        / Checks the suspected « 45 € » bug: LigneArticle amounts must sum to 1500,
        not 4500. Card1 debited 6 €.
        """
        with (
            mock.patch('laboutik.views.FedowConfig') as MockConfig,
            mock.patch('laboutik.views.FedowAPI'),
        ):
            MockConfig.get_solo.return_value.can_fedow.return_value = False

            reponse1 = self._post_payer_nfc(tag_id=self.carte1.tag_id, quantite=3)
            contenu1 = reponse1.content.decode()
            cascade_carte1 = _extraire_hidden(contenu1, 'cascade_carte1')
            total_nfc_carte1 = _extraire_hidden(contenu1, 'total_nfc_carte1')

            reponse2 = self._post_complementaire_espece(
                tag_id_carte1=self.carte1.tag_id,
                cascade_carte1=cascade_carte1,
                total_nfc_carte1=total_nfc_carte1,
                quantite=3,
            )
            assert reponse2.status_code == 200

        lignes = LigneArticle.objects.filter(sale_origin=SaleOrigin.LABOUTIK)
        assert lignes.count() > 0, "Le paiement complet doit créer des LigneArticle."

        # La somme des montants = total panier = 1500 centimes (15 €), pas 4500 (45 €).
        # / Sum of amounts = cart total = 1500 cents (15 €), not 4500 (45 €).
        detail = [
            (ligne.amount, float(ligne.qty), ligne.payment_method)
            for ligne in lignes
        ]

        # COMPTABILITÉ : le total de ligne (LigneArticle.total = amount × qty,
        # convention unifiée) doit sommer au total panier = 1500 centimes (15 €).
        # / Accounting: line totals (amount × qty) must sum to 1500.
        total_compta = sum(ligne.total() for ligne in lignes)
        assert total_compta == 1500, (
            f"Total comptable (amount × qty) attendu 1500, obtenu {total_compta}. "
            f"Lignes (amount, qty, pm) = {detail}"
        )

        # QUANTITÉS : toutes positives et somme = 3 (régression du bug qty négative).
        # / Quantities: all positive and sum to 3 (negative-qty regression guard).
        assert all(ligne.qty > 0 for ligne in lignes), (
            f"Quantité négative ou nulle détectée : {detail}"
        )
        assert sum(ligne.qty for ligne in lignes) == 3

        # Carte1 débitée de ses 6 € TLF (solde 0 après).
        # / Card1 debited its 6 € TLF (balance 0 after).
        assert WalletService.obtenir_solde(self.wallet1, self.asset_tlf) == 0

    # ------------------------------------------------------------------ #
    #  Test : NFC1 + CB → succès
    # ------------------------------------------------------------------ #

    def _post_complementaire_cb(self, tag_id_carte1, cascade_carte1,
                                total_nfc_carte1, quantite):
        """POST payer_complementaire moyen_complement=carte_bancaire.
        / POST payer_complementaire moyen_complement=carte_bancaire."""
        data = {
            'uuid_pv': str(self.pv.uuid),
            'moyen_complement': 'carte_bancaire',
            'tag_id_carte1': tag_id_carte1,
            'cascade_carte1': cascade_carte1,
            'total_nfc_carte1': total_nfc_carte1,
            f'repid-{self.produit.uuid}': str(quantite),
        }
        return self.client_http.post(
            '/laboutik/paiement/payer_complementaire/', data=data
        )

    def test_nfc1_puis_cb_finalise_et_compta_correcte(self):
        """3 vins (15 €), carte1 TLF 6 € + complément 9 € en CB → succès.

        Compta = 15 € (Sum amount), une ligne au moins en CB, carte1 débitée.
        / Card1 6 € TLF + 9 € CC complement → success; accounting 15 €, a CC line.
        """
        with (
            mock.patch('laboutik.views.FedowConfig') as MockConfig,
            mock.patch('laboutik.views.FedowAPI'),
        ):
            MockConfig.get_solo.return_value.can_fedow.return_value = False

            reponse1 = self._post_payer_nfc(tag_id=self.carte1.tag_id, quantite=3)
            contenu1 = reponse1.content.decode()
            cascade_carte1 = _extraire_hidden(contenu1, 'cascade_carte1')
            total_nfc_carte1 = _extraire_hidden(contenu1, 'total_nfc_carte1')

            reponse2 = self._post_complementaire_cb(
                tag_id_carte1=self.carte1.tag_id,
                cascade_carte1=cascade_carte1,
                total_nfc_carte1=total_nfc_carte1,
                quantite=3,
            )
            assert reponse2.status_code == 200

        lignes = LigneArticle.objects.filter(sale_origin=SaleOrigin.LABOUTIK)
        assert sum(ligne.total() for ligne in lignes) == 1500
        assert all(ligne.qty > 0 for ligne in lignes)
        # Une part au moins réglée en CB (le complément 9 €).
        # / At least one part settled by CC (the 9 € complement).
        assert lignes.filter(payment_method=PaymentMethod.CC).exists()
        assert WalletService.obtenir_solde(self.wallet1, self.asset_tlf) == 0

    # ------------------------------------------------------------------ #
    #  Test : NFC1 + NFC2 suffisante → succès, les 2 cartes débitées
    # ------------------------------------------------------------------ #

    def test_nfc1_plus_nfc2_suffisante_finalise_et_debite_les_deux(self):
        """3 vins (15 €), carte1 TLF 6 € + carte2 TLF 9 € (couvre le reste) → succès.

        Le paiement se finalise (PAS de re-render complément), compta = 15 €, et
        les DEUX cartes sont débitées (carte1 → 0, carte2 → 0).
        / Card2 covers the 9 € remainder → success; accounting 15 €, BOTH cards
        debited (no complement re-render).
        """
        # Carte2 montée à 9,00 € TLF pour couvrir exactement le reste.
        # / Card2 topped up to 9.00 € TLF to cover the remainder exactly.
        Token.objects.filter(wallet=self.wallet2, asset=self.asset_tlf).update(value=900)

        with (
            mock.patch('laboutik.views.FedowConfig') as MockConfig,
            mock.patch('laboutik.views.FedowAPI'),
        ):
            MockConfig.get_solo.return_value.can_fedow.return_value = False

            reponse1 = self._post_payer_nfc(tag_id=self.carte1.tag_id, quantite=3)
            contenu1 = reponse1.content.decode()
            cascade_carte1 = _extraire_hidden(contenu1, 'cascade_carte1')
            total_nfc_carte1 = _extraire_hidden(contenu1, 'total_nfc_carte1')

            reponse2 = self._post_complementaire_nfc(
                tag_id_carte2=self.carte2.tag_id,
                tag_id_carte1=self.carte1.tag_id,
                cascade_carte1=cascade_carte1,
                total_nfc_carte1=total_nfc_carte1,
                quantite=3,
            )
            assert reponse2.status_code == 200
            contenu2 = reponse2.content.decode()

        # SUCCÈS : pas de re-render complément (plus de « reste à payer »).
        # / SUCCESS: not a complement re-render (no « remaining amount »).
        assert 'data-testid="complement-reste-a-payer"' not in contenu2

        lignes = LigneArticle.objects.filter(sale_origin=SaleOrigin.LABOUTIK)
        assert sum(ligne.total() for ligne in lignes) == 1500
        assert all(ligne.qty > 0 for ligne in lignes)

        # Les DEUX cartes sont débitées de leur TLF.
        # / BOTH cards debited their TLF.
        assert WalletService.obtenir_solde(self.wallet1, self.asset_tlf) == 0
        assert WalletService.obtenir_solde(self.wallet2, self.asset_tlf) == 0

    # ------------------------------------------------------------------ #
    #  Test : Bug B — le total de ligne (amount × qty) ne doit pas tripler
    # ------------------------------------------------------------------ #

    def test_full_nfc_total_ligne_correct_pas_de_45(self):
        """Bug B : paiement NFC complet de 3 vins (15 €), carte1 couvre tout en TLF.

        Le total de ligne `amount × qty` (affiché admin/ticket via LigneArticle.total)
        doit valoir 1500 (15 €), PAS 4500 (45 €). Le bug : la cascade stockait
        amount=montant total (1500) au lieu du prix unitaire (500), × qty=3 = 4500.
        / Full NFC payment: line total (amount × qty) must be 15 €, not 45 €.
        """
        Token.objects.filter(wallet=self.wallet1, asset=self.asset_tlf).update(value=1500)

        with (
            mock.patch('laboutik.views.FedowConfig') as MockConfig,
            mock.patch('laboutik.views.FedowAPI'),
        ):
            MockConfig.get_solo.return_value.can_fedow.return_value = False
            reponse = self._post_payer_nfc(tag_id=self.carte1.tag_id, quantite=3)
            assert reponse.status_code == 200

        lignes = LigneArticle.objects.filter(sale_origin=SaleOrigin.LABOUTIK)
        # Total affiché (admin/ticket) = somme des LigneArticle.total (= amount × qty).
        # / Displayed total = sum of LigneArticle.total (= amount × qty).
        total_affiche = sum(ligne.total() for ligne in lignes)
        assert total_affiche == 1500, (
            f"Total ligne attendu 1500 (15 €), obtenu {total_affiche}. "
            f"4500 = bug B (45 € : amount=total au lieu du prix unitaire)."
        )

    # ------------------------------------------------------------------ #
    #  Test : Bug C — le FED de carte1 doit être reporté dans la branche NFC
    # ------------------------------------------------------------------ #

    def test_carte1_fed_reporte_dans_complement_nfc(self):
        """Bug C : carte1 paie en FED legacy, complément 2e carte NFC.

        carte1 = 0 local + 6 € FED, carte2 = 8 € local, panier 15 €.
        Le FED de carte1 (6 €) doit être reporté dans le calcul : après carte2
        (8 € local), le reste à payer attendu = **1 €** (15 − 6 − 8), PAS 7 €.
        / Card1's FED must carry over into the NFC complement: remaining = 1 €.
        """
        # carte1 : 0 local (on vide son TLF), 6 € FED (mocké ci-dessous).
        # / Card1: 0 local TLF, 6 € FED (mocked below).
        Token.objects.filter(wallet=self.wallet1, asset=self.asset_tlf).update(value=0)

        user1_pk = self.carte1.user_id

        def fake_fed(user):
            # carte1 a 6 € de FED dépensable ; carte2 n'a pas de FED.
            # / Card1 has 6 € spendable FED; card2 has none.
            if user.pk == user1_pk:
                return (600, True)
            return (0, False)

        with (
            mock.patch('laboutik.views.lire_depensable_fed_frais', side_effect=fake_fed),
            mock.patch('laboutik.views.FedowConfig') as MockConfig,
            mock.patch('laboutik.views.FedowAPI'),
        ):
            MockConfig.get_solo.return_value.can_fedow.return_value = False

            reponse1 = self._post_payer_nfc(tag_id=self.carte1.tag_id, quantite=3)
            contenu1 = reponse1.content.decode()
            # Étape 1 : le FED de carte1 couvre 6 € → reste 9 €.
            assert '9.00' in contenu1
            cascade_carte1 = _extraire_hidden(contenu1, 'cascade_carte1')
            total_nfc_carte1 = _extraire_hidden(contenu1, 'total_nfc_carte1')

            reponse2 = self._post_complementaire_nfc(
                tag_id_carte2=self.carte2.tag_id,
                tag_id_carte1=self.carte1.tag_id,
                cascade_carte1=cascade_carte1,
                total_nfc_carte1=total_nfc_carte1,
                quantite=3,
            )
            contenu2 = reponse2.content.decode()

        # Reste à payer affiché après carte2 = 1,00 € (le FED de carte1 est reporté).
        # / Displayed remaining after card2 = 1.00 € (card1's FED carried over).
        reste = _extraire_reste(contenu2)
        assert reste == '1.00', (
            f"Reste attendu 1,00 € (le FED de carte1 doit être reporté), obtenu {reste}€. "
            f"7,00 € = bug C (FED de carte1 oublié dans la branche NFC)."
        )

    def test_carte1_fed_plus_carte2_finalise_le_paiement(self):
        """Bug C, chemin succès : carte1 (0 local + 6 € FED) + carte2 (9 € local) couvre tout.

        Le paiement se finalise : FED de carte1 **débité** (différé), carte2 débitée,
        compta = 15 €, et une part comptable en **STRIPE_FED** (le réseau).
        / Success path: card1 FED (deferred debit) + card2 local cover all → finalize.
        """
        FED_UUID = "33333333-3333-3333-3333-333333333333"
        Token.objects.filter(wallet=self.wallet1, asset=self.asset_tlf).update(value=0)
        Token.objects.filter(wallet=self.wallet2, asset=self.asset_tlf).update(value=900)
        user1_pk = self.carte1.user_id

        def fake_fed(user):
            if user.pk == user1_pk:
                return (600, True)
            return (0, False)

        def fake_debit_legacy(user, montant, uuid_tx):
            # Fedow renverrait une transaction FED du montant débité.
            # / Fedow would return a FED transaction for the debited amount.
            return [(FED_UUID, montant, PaymentMethod.STRIPE_FED)]

        with (
            mock.patch('laboutik.views.lire_depensable_fed_frais', side_effect=fake_fed),
            mock.patch('laboutik.views._debiter_legacy', side_effect=fake_debit_legacy),
            mock.patch('laboutik.views.FedowConfig') as MockConfig,
            mock.patch('laboutik.views.FedowAPI'),
        ):
            MockConfig.get_solo.return_value.can_fedow.return_value = False

            reponse1 = self._post_payer_nfc(tag_id=self.carte1.tag_id, quantite=3)
            contenu1 = reponse1.content.decode()
            cascade_carte1 = _extraire_hidden(contenu1, 'cascade_carte1')
            total_nfc_carte1 = _extraire_hidden(contenu1, 'total_nfc_carte1')

            reponse2 = self._post_complementaire_nfc(
                tag_id_carte2=self.carte2.tag_id,
                tag_id_carte1=self.carte1.tag_id,
                cascade_carte1=cascade_carte1,
                total_nfc_carte1=total_nfc_carte1,
                quantite=3,
            )
            assert reponse2.status_code == 200
            contenu2 = reponse2.content.decode()

        # Succès : pas de re-render complément.
        # / Success: no complement re-render.
        assert 'data-testid="complement-reste-a-payer"' not in contenu2

        lignes = LigneArticle.objects.filter(sale_origin=SaleOrigin.LABOUTIK)
        assert sum(ligne.total() for ligne in lignes) == 1500
        # Une part réglée par le réseau (FED de carte1).
        # / A part settled by the network (card1's FED).
        assert lignes.filter(payment_method=PaymentMethod.STRIPE_FED).exists()
        # Carte2 débitée de ses 9 € locaux.
        # / Card2 debited its 9 € local.
        assert WalletService.obtenir_solde(self.wallet2, self.asset_tlf) == 0
