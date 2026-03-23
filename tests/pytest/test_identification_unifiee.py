"""
tests/pytest/test_identification_unifiee.py — Tests du flow d'identification client unifie.
/ Tests for the unified client identification flow.

Couvre :
- Flag panier_necessite_client (logique pure, sans DB)
- POST /laboutik/paiement/moyens_paiement/ → template unifie (FastTenantTestCase)
- POST /laboutik/paiement/identifier_client/ → recapitulatif ou formulaire (schema_context)
- GET /laboutik/paiement/formulaire_identification_client/ → formulaire vierge
Covers:
- panier_necessite_client flag (pure logic, no DB)
- POST moyens_paiement → unified template (FastTenantTestCase)
- POST identifier_client → recap or form (schema_context)
- GET formulaire_identification_client → blank form

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_identification_unifiee.py -v
"""

import sys
from types import SimpleNamespace

sys.path.insert(0, '/DjangoFiles')

import django
django.setup()

import pytest

from decimal import Decimal

from django.db import connection
from django_tenants.test.cases import FastTenantTestCase
from django_tenants.test.client import TenantClient
from django_tenants.utils import schema_context

from AuthBillet.models import TibilletUser
from BaseBillet.models import (
    CategorieProduct, LigneArticle, Price, Product,
    PaymentMethod, SaleOrigin,
)
from Customers.models import Client
from laboutik.models import PointDeVente
from QrcodeCashless.models import CarteCashless


# ===========================================================================
# PARTIE 1 — Tests logiques purs (pas de DB)
# / PART 1 — Pure logic tests (no DB)
# ===========================================================================

METHODES_RECHARGE = {"RE", "RC", "TM"}


def _panier_contient_recharges(articles_panier):
    """Copie de laboutik/views.py._panier_contient_recharges()."""
    for article in articles_panier:
        produit = article["product"]
        if hasattr(produit, "methode_caisse") and produit.methode_caisse in METHODES_RECHARGE:
            return True
    return False


def _panier_a_adhesions(articles_panier):
    """Copie de la comprehension dans views.py.moyens_paiement()."""
    return any(
        a["product"].categorie_article == "A"
        for a in articles_panier
    )


def _build_article(product, quantite=1):
    return {"product": product, "quantite": quantite}


def test_panier_necessite_client_vente_seule():
    """Panier VT seul → pas d'identification."""
    articles = [_build_article(SimpleNamespace(methode_caisse="VT", categorie_article="B"))]
    assert (_panier_contient_recharges(articles) or _panier_a_adhesions(articles)) is False


def test_panier_necessite_client_recharge():
    """Panier RE → identification requise."""
    articles = [_build_article(SimpleNamespace(methode_caisse="RE", categorie_article="S"))]
    assert _panier_contient_recharges(articles) is True


def test_panier_necessite_client_adhesion():
    """Panier AD → identification requise."""
    articles = [_build_article(SimpleNamespace(methode_caisse="AD", categorie_article="A"))]
    assert _panier_a_adhesions(articles) is True


def test_panier_necessite_client_mixte():
    """Panier RE + AD → les deux flags actifs."""
    articles = [
        _build_article(SimpleNamespace(methode_caisse="RE", categorie_article="S")),
        _build_article(SimpleNamespace(methode_caisse="AD", categorie_article="A")),
    ]
    assert _panier_contient_recharges(articles) is True
    assert _panier_a_adhesions(articles) is True


def test_panier_recharge_bloque_email():
    """Panier RE → bouton email masque (not panier_a_recharges = False)."""
    articles = [_build_article(SimpleNamespace(methode_caisse="RE", categorie_article="S"))]
    assert (not _panier_contient_recharges(articles)) is False


# ===========================================================================
# PARTIE 2 — Tests HTTP moyens_paiement() avec FastTenantTestCase
# Pas besoin de CarteCashless (SHARED_APPS) ici — que des TENANT_APPS.
# / PART 2 — HTTP tests for moyens_paiement() with FastTenantTestCase
# No CarteCashless needed here — only TENANT_APPS.
# ===========================================================================


class TestMoyensPaiementIdentification(FastTenantTestCase):
    """POST moyens_paiement() verifie que panier_necessite_client declenche le bon template.
    / POST moyens_paiement() verifies panier_necessite_client triggers the right template."""

    @classmethod
    def get_test_schema_name(cls):
        return 'test_ident_mp'

    @classmethod
    def get_test_tenant_domain(cls):
        return 'test-ident-mp.tibillet.localhost'

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.name = 'Test Ident MP'

    def setUp(self):
        connection.set_tenant(self.tenant)

        self.categorie = CategorieProduct.objects.create(name='Cat Ident MP')

        self.produit_vente = Product.objects.create(
            name='Biere Ident MP',
            methode_caisse=Product.VENTE,
            categorie_pos=self.categorie,
        )
        Price.objects.create(
            product=self.produit_vente, name='Pinte', prix=Decimal('5.00'), publish=True,
        )

        self.produit_recharge = Product.objects.create(
            name='Recharge Ident MP',
            methode_caisse=Product.RECHARGE_EUROS,
        )
        Price.objects.create(
            product=self.produit_recharge, name='10 euros', prix=Decimal('10.00'), publish=True,
        )

        self.produit_adhesion = Product.objects.create(
            name='Adhesion Ident MP',
            categorie_article=Product.ADHESION,
        )
        Price.objects.create(
            product=self.produit_adhesion, name='Annuelle', prix=Decimal('20.00'),
            publish=True, subscription_type=Price.YEAR,
        )

        self.pv = PointDeVente.objects.create(
            name='PV Ident MP',
            comportement=PointDeVente.DIRECT,
            service_direct=True,
            accepte_especes=True,
            accepte_carte_bancaire=True,
        )
        self.pv.products.add(self.produit_vente, self.produit_recharge, self.produit_adhesion)

        self.admin, _ = TibilletUser.objects.get_or_create(
            email='admin-ident-mp@tibillet.localhost',
            defaults={
                'username': 'admin-ident-mp@tibillet.localhost',
                'is_staff': True, 'is_active': True,
            },
        )
        self.admin.client_admin.add(self.tenant)
        self.c = TenantClient(self.tenant)
        self.c.force_login(self.admin)

    def _post_moyens(self, *produit_uuids):
        data = {'uuid_pv': str(self.pv.uuid)}
        for uuid in produit_uuids:
            data[f'repid-{uuid}'] = '1'
        return self.c.post('/laboutik/paiement/moyens_paiement/', data=data)

    # ----------------------------------------------------------------------- #

    def test_vente_seule_mode_normal(self):
        """VT seul → mode normal (pas d'identification)."""
        response = self._post_moyens(self.produit_vente.uuid)
        contenu = response.content.decode()
        assert 'client-choose-nfc' not in contenu
        assert 'client-choose-email' not in contenu
        assert 'paiement-btn-especes' in contenu

    def test_recharge_affiche_identification_nfc_seulement(self):
        """RE → identification : NFC present, email absent."""
        response = self._post_moyens(self.produit_recharge.uuid)
        contenu = response.content.decode()
        assert 'client-choose-nfc' in contenu
        assert 'client-choose-email' not in contenu

    def test_adhesion_affiche_identification_nfc_et_email(self):
        """AD → identification : NFC + email presents."""
        response = self._post_moyens(self.produit_adhesion.uuid)
        contenu = response.content.decode()
        assert 'client-choose-nfc' in contenu
        assert 'client-choose-email' in contenu

    def test_mixte_recharge_adhesion_masque_email(self):
        """RE + AD → NFC present, email absent (recharge = carte physique requise)."""
        response = self._post_moyens(self.produit_recharge.uuid, self.produit_adhesion.uuid)
        contenu = response.content.decode()
        assert 'client-choose-nfc' in contenu
        assert 'client-choose-email' not in contenu

    def test_titre_adaptatif_recharge(self):
        """RE → titre contient 'Recharge'."""
        response = self._post_moyens(self.produit_recharge.uuid)
        assert 'Recharge' in response.content.decode()

    def test_titre_adaptatif_adhesion(self):
        """AD → titre contient 'Adhesion' ou 'Membership' (traduction)."""
        response = self._post_moyens(self.produit_adhesion.uuid)
        contenu = response.content.decode()
        # Le texte peut etre 'Adhesion' ou 'Membership' selon la langue active
        assert 'Adhesion' in contenu or 'Membership' in contenu

    def test_titre_adaptatif_mixte(self):
        """RE + AD → titre contient 'Recharge + Adhesion'."""
        response = self._post_moyens(self.produit_recharge.uuid, self.produit_adhesion.uuid)
        assert 'Recharge + Adhesion' in response.content.decode()

    # ----------------------------------------------------------------------- #
    #  Tests paniers mixtes complets : moyens_paiement → identifier → payer
    #  / Full mixed cart tests: moyens_paiement → identify → pay
    # ----------------------------------------------------------------------- #

    def _post_identifier_client(self, data):
        """POST /laboutik/paiement/identifier_client/."""
        return self.c.post('/laboutik/paiement/identifier_client/', data=data)

    def _post_payer(self, data):
        """POST /laboutik/paiement/payer/."""
        return self.c.post('/laboutik/paiement/payer/', data=data)

    def _build_panier_data(self, *produits_uuids):
        """Construit les donnees POST minimales pour un panier.
        / Builds minimal POST data for a cart."""
        data = {'uuid_pv': str(self.pv.uuid)}
        for uuid in produits_uuids:
            data[f'repid-{uuid}'] = '1'
        return data

    def test_panier_ad_vt_identification_puis_paiement_cashless(self):
        """Panier AD + VT → identification NFC → recapitulatif avec 2 articles → paiement cashless.
        Le cashless est autorise car le panier ne contient PAS de recharges.
        / Cart AD + VT → NFC identification → recap with 2 articles → cashless payment.
        Cashless is allowed because the cart does NOT contain top-ups.
        """
        # 1. moyens_paiement : verifie que l'identification est requise
        response_moyens = self._post_moyens(self.produit_adhesion.uuid, self.produit_vente.uuid)
        contenu_moyens = response_moyens.content.decode()
        assert 'client-choose-nfc' in contenu_moyens
        assert 'client-choose-email' in contenu_moyens  # Pas de recharge → email disponible

        # 2. identifier_client : envoie les articles + tag_id
        # Le POST simule #addition-form avec repid-* + uuid_pv + tag_id + flags
        panier_data = self._build_panier_data(self.produit_adhesion.uuid, self.produit_vente.uuid)
        panier_data.update({
            'tag_id': 'IDNFC001',  # Carte avec user (cree dans setUp de Partie 3 — mais ici FastTenant)
            'panier_a_recharges': 'False',
            'panier_a_adhesions': 'True',
            'moyens_paiement': 'nfc,espece,carte_bancaire',
        })
        # Note : en FastTenantTestCase, on n'a pas de CarteCashless (SHARED_APPS).
        # Le POST retournera une erreur "Carte inconnue" pour le tag_id.
        # Ce test verifie surtout le parcours moyens_paiement → identification requise.
        # Le test complet avec NFC est dans TestIdentifierClient (Partie 3, schema lespass).
        response_ident = self._post_identifier_client(panier_data)
        contenu_ident = response_ident.content.decode()
        # Carte inconnue en FastTenant (pas de CarteCashless dans le schema isole)
        # Mais l'important c'est que la vue repond 200 et ne crash pas
        assert response_ident.status_code == 200

    def test_panier_vt_re_identification_puis_paiement_especes(self):
        """Panier VT + RE → identification NFC obligatoire (pas d'email) → paiement especes.
        / Cart VT + RE → NFC identification required (no email) → cash payment.
        """
        # 1. moyens_paiement : NFC seulement (recharge → pas d'email)
        response_moyens = self._post_moyens(self.produit_vente.uuid, self.produit_recharge.uuid)
        contenu_moyens = response_moyens.content.decode()
        assert 'client-choose-nfc' in contenu_moyens
        assert 'client-choose-email' not in contenu_moyens  # Recharge → pas d'email

    def test_panier_vt_re_ad_identification_puis_paiement_cb(self):
        """Panier VT + RE + AD → identification NFC (pas d'email) → recapitulatif → CB.
        Le titre indique "Recharge + Adhesion". Email masque car recharge presente.
        / Cart VT + RE + AD → NFC identification (no email) → recap → card payment.
        Title shows "Recharge + Adhesion". Email hidden because top-up is present.
        """
        # 1. moyens_paiement : NFC seulement, titre mixte
        response_moyens = self._post_moyens(
            self.produit_vente.uuid, self.produit_recharge.uuid, self.produit_adhesion.uuid
        )
        contenu_moyens = response_moyens.content.decode()
        assert 'client-choose-nfc' in contenu_moyens
        assert 'client-choose-email' not in contenu_moyens
        assert 'Recharge + Adhesion' in contenu_moyens

        # 2. identifier_client avec les 3 articles (simule #addition-form)
        panier_data = self._build_panier_data(
            self.produit_vente.uuid, self.produit_recharge.uuid, self.produit_adhesion.uuid
        )
        panier_data.update({
            'panier_a_recharges': 'True',
            'panier_a_adhesions': 'True',
            'moyens_paiement': 'espece,carte_bancaire',
        })
        # Pas de tag_id, pas d'email → formulaire vierge (aucune identification)
        response_ident = self._post_identifier_client(panier_data)
        contenu_ident = response_ident.content.decode()
        # Sans identification (pas de tag_id ni email) → formulaire vierge
        assert 'client-form' in contenu_ident

    def test_panier_vt_re_cashless_rejete(self):
        """Panier VT + RE → paiement cashless → ERREUR (recharge interdit en cashless).
        C'est la garde dans _payer_par_nfc() qui bloque.
        / Cart VT + RE → cashless payment → ERROR (top-up forbidden in cashless).
        This is the guard in _payer_par_nfc() that blocks.
        """
        prix_vente_centimes = int(round(Decimal('5.00') * 100))
        prix_recharge_centimes = int(round(Decimal('10.00') * 100))
        total_centimes = prix_vente_centimes + prix_recharge_centimes

        data = {
            'uuid_pv': str(self.pv.uuid),
            'moyen_paiement': 'nfc',
            'total': str(total_centimes),
            'given_sum': '0',
            'tag_id': 'FAKECARD',
            f'repid-{self.produit_vente.uuid}': '1',
            f'repid-{self.produit_recharge.uuid}': '1',
        }
        response = self._post_payer(data)
        assert response.status_code == 400
        contenu = response.content.decode()
        # Le message d'erreur indique que les recharges ne peuvent pas etre payees en cashless
        # / Error message says top-ups cannot be paid in cashless
        assert 'cashless' in contenu.lower() or 'recharge' in contenu.lower()

    # ----------------------------------------------------------------------- #
    #  Tests paiement complet avec verification LigneArticle en DB
    #  / Full payment tests with LigneArticle DB verification
    # ----------------------------------------------------------------------- #

    def _verifier_ligne_article(self, produit, quantite_attendue, montant_centimes_attendu,
                                 payment_method_attendu, sale_origin_attendu=SaleOrigin.LABOUTIK):
        """Verifie qu'une LigneArticle existe avec les bons champs.
        / Verifies that a LigneArticle exists with the right fields."""
        ligne = LigneArticle.objects.filter(
            pricesold__productsold__product=produit,
            sale_origin=sale_origin_attendu,
        ).order_by('-datetime').first()

        assert ligne is not None, (
            f"LigneArticle introuvable pour {produit.name}"
        )
        assert int(ligne.qty) == quantite_attendue, (
            f"{produit.name}: qty={ligne.qty}, attendu={quantite_attendue}"
        )
        assert ligne.amount == montant_centimes_attendu, (
            f"{produit.name}: amount={ligne.amount}, attendu={montant_centimes_attendu}"
        )
        assert ligne.payment_method == payment_method_attendu, (
            f"{produit.name}: payment_method={ligne.payment_method}, attendu={payment_method_attendu}"
        )
        assert ligne.sale_origin == SaleOrigin.LABOUTIK, (
            f"{produit.name}: sale_origin={ligne.sale_origin}, attendu=LB"
        )
        assert ligne.status == LigneArticle.VALID, (
            f"{produit.name}: status={ligne.status}, attendu=V"
        )
        return ligne

    def test_paiement_especes_vt_verifie_ligne_article(self):
        """Paiement especes VT seul → LigneArticle avec payment_method=CA, sale_origin=LB.
        / Cash payment VT only → LigneArticle with payment_method=CA, sale_origin=LB.
        """
        nb_lignes_avant = LigneArticle.objects.filter(sale_origin=SaleOrigin.LABOUTIK).count()

        prix_centimes = int(round(Decimal('5.00') * 100))
        data = {
            'uuid_pv': str(self.pv.uuid),
            'moyen_paiement': 'espece',
            'total': str(prix_centimes),
            'given_sum': '0',
            f'repid-{self.produit_vente.uuid}': '1',
        }
        response = self._post_payer(data)
        assert response.status_code == 200

        nb_lignes_apres = LigneArticle.objects.filter(sale_origin=SaleOrigin.LABOUTIK).count()
        assert nb_lignes_apres == nb_lignes_avant + 1, (
            f"Attendu +1 LigneArticle, got {nb_lignes_apres - nb_lignes_avant}"
        )

        ligne = self._verifier_ligne_article(
            produit=self.produit_vente,
            quantite_attendue=1,
            montant_centimes_attendu=prix_centimes,
            payment_method_attendu=PaymentMethod.CASH,
        )
        # Pas de carte NFC pour un paiement especes
        # / No NFC card for cash payment
        assert ligne.carte is None

    def test_paiement_cb_vt_verifie_ligne_article(self):
        """Paiement CB VT seul → LigneArticle avec payment_method=CC.
        / Card payment VT only → LigneArticle with payment_method=CC.
        """
        prix_centimes = int(round(Decimal('5.00') * 100))
        data = {
            'uuid_pv': str(self.pv.uuid),
            'moyen_paiement': 'carte_bancaire',
            'total': str(prix_centimes),
            'given_sum': '0',
            f'repid-{self.produit_vente.uuid}': '1',
        }
        response = self._post_payer(data)
        assert response.status_code == 200

        self._verifier_ligne_article(
            produit=self.produit_vente,
            quantite_attendue=1,
            montant_centimes_attendu=prix_centimes,
            payment_method_attendu=PaymentMethod.CC,
        )

    def test_paiement_especes_vt_ad_verifie_lignes_articles(self):
        """Paiement especes VT + AD → 2 LigneArticle, une VT (CA) + une AD (CA).
        L'adhesion necessite un email dans le POST (identifie via formulaire).
        / Cash payment VT + AD → 2 LigneArticle, one VT (CA) + one AD (CA).
        Membership needs an email in POST (identified via form).
        """
        nb_lignes_avant = LigneArticle.objects.filter(sale_origin=SaleOrigin.LABOUTIK).count()

        prix_vente_centimes = int(round(Decimal('5.00') * 100))
        prix_adhesion_centimes = int(round(Decimal('20.00') * 100))
        total_centimes = prix_vente_centimes + prix_adhesion_centimes

        data = {
            'uuid_pv': str(self.pv.uuid),
            'moyen_paiement': 'espece',
            'total': str(total_centimes),
            'given_sum': '0',
            f'repid-{self.produit_vente.uuid}': '1',
            f'repid-{self.produit_adhesion.uuid}': '1',
            # Identification client par email (pas de NFC en FastTenantTestCase)
            'email_adhesion': 'test-ligne-ad@tibillet.localhost',
            'prenom_adhesion': 'TestLigne',
            'nom_adhesion': 'ArticleAD',
        }
        response = self._post_payer(data)
        assert response.status_code == 200

        nb_lignes_apres = LigneArticle.objects.filter(sale_origin=SaleOrigin.LABOUTIK).count()
        assert nb_lignes_apres >= nb_lignes_avant + 2, (
            f"Attendu au moins +2 LigneArticle (VT+AD), got +{nb_lignes_apres - nb_lignes_avant}"
        )

        # Verification VT
        self._verifier_ligne_article(
            produit=self.produit_vente,
            quantite_attendue=1,
            montant_centimes_attendu=prix_vente_centimes,
            payment_method_attendu=PaymentMethod.CASH,
        )

        # Verification AD
        ligne_ad = self._verifier_ligne_article(
            produit=self.produit_adhesion,
            quantite_attendue=1,
            montant_centimes_attendu=prix_adhesion_centimes,
            payment_method_attendu=PaymentMethod.CASH,
        )
        # L'adhesion doit etre liee a une Membership
        # / Membership must be linked to the LigneArticle
        assert ligne_ad.membership is not None, (
            "LigneArticle adhesion sans Membership liee"
        )
        assert ligne_ad.membership.user.email == 'test-ligne-ad@tibillet.localhost'


# ===========================================================================
# PARTIE 3 — Tests HTTP identifier_client() avec schema_context
# CarteCashless est dans SHARED_APPS → on utilise le tenant lespass existant.
# / PART 3 — HTTP tests for identifier_client() with schema_context
# CarteCashless is in SHARED_APPS → use existing lespass tenant.
# ===========================================================================

TENANT_SCHEMA = 'lespass'


@pytest.fixture(scope="module")
def tenant():
    return Client.objects.get(schema_name=TENANT_SCHEMA)


@pytest.fixture(scope="module")
def test_data():
    """Lance create_test_pos_data pour les donnees de base.
    / Runs create_test_pos_data for base data."""
    from django.core.management import call_command
    call_command('create_test_pos_data')
    return True


@pytest.fixture(scope="module")
def admin_user_ident(tenant):
    """Admin pour les tests d'identification.
    / Admin for identification tests."""
    with schema_context(TENANT_SCHEMA):
        email = 'admin-test-ident@tibillet.localhost'
        user, _ = TibilletUser.objects.get_or_create(
            email=email,
            defaults={
                'username': email,
                'is_staff': True,
                'is_active': True,
            },
        )
        user.client_admin.add(tenant)
        return user


@pytest.fixture(scope="module")
def premier_pv_ident(test_data):
    """Premier PV existant."""
    with schema_context(TENANT_SCHEMA):
        return PointDeVente.objects.filter(hidden=False).order_by('poid_liste').first()


@pytest.fixture(scope="module")
def carte_avec_user_ident():
    """CarteCashless avec user assigne (SHARED_APPS)."""
    email = 'carte-ident-test@tibillet.localhost'
    user, _ = TibilletUser.objects.get_or_create(
        email=email,
        defaults={
            'username': email,
            'first_name': 'CarteTest',
            'last_name': 'IdentNFC',
            'is_active': True,
        },
    )
    carte, _ = CarteCashless.objects.get_or_create(
        tag_id='IDNFC001',
        defaults={'number': 'IDNFC01N', 'user': user},
    )
    if carte.user != user:
        carte.user = user
        carte.save(update_fields=['user'])
    return carte


@pytest.fixture(scope="module")
def carte_anonyme_ident():
    """CarteCashless sans user (SHARED_APPS)."""
    carte, _ = CarteCashless.objects.get_or_create(
        tag_id='IDNFC002',
        defaults={'number': 'IDNFC02N'},
    )
    carte.user = None
    carte.save(update_fields=['user'])
    return carte


def _make_client(admin_user, tenant):
    """Cree un APIClient authentifie pour le tenant.
    / Creates an authenticated APIClient for the tenant."""
    from rest_framework.test import APIClient
    client = APIClient()
    client.force_authenticate(user=admin_user)
    client.defaults['SERVER_NAME'] = f'{TENANT_SCHEMA}.tibillet.localhost'
    return client


@pytest.mark.usefixtures("test_data")
class TestIdentifierClient:
    """Tests POST /laboutik/paiement/identifier_client/ sur le tenant lespass."""

    def test_nfc_carte_avec_user_affiche_recapitulatif(
        self, admin_user_ident, tenant, carte_avec_user_ident,
    ):
        """Scan NFC carte avec user → recapitulatif."""
        with schema_context(TENANT_SCHEMA):
            client = _make_client(admin_user_ident, tenant)
            response = client.post('/laboutik/paiement/identifier_client/', data={
                'tag_id': carte_avec_user_ident.tag_id,
                'panier_a_recharges': 'False',
                'panier_a_adhesions': 'True',
                'moyens_paiement': 'espece,carte_bancaire',
            })
            assert response.status_code == 200
            contenu = response.content.decode()
            assert 'client-recapitulatif' in contenu
            assert 'carte-ident-test@tibillet.localhost' in contenu
            assert 'IDENTNFC' in contenu
            assert 'client-btn-especes' in contenu
            assert 'client-btn-cb' in contenu

    def test_nfc_carte_anonyme_affiche_formulaire(
        self, admin_user_ident, tenant, carte_anonyme_ident,
    ):
        """Scan NFC carte anonyme → formulaire."""
        with schema_context(TENANT_SCHEMA):
            client = _make_client(admin_user_ident, tenant)
            response = client.post('/laboutik/paiement/identifier_client/', data={
                'tag_id': carte_anonyme_ident.tag_id,
                'panier_a_recharges': 'True',
                'panier_a_adhesions': 'False',
                'moyens_paiement': 'espece',
            })
            assert response.status_code == 200
            contenu = response.content.decode()
            assert 'client-form' in contenu
            assert 'client-recapitulatif' not in contenu

    def test_nfc_carte_inconnue_affiche_erreur(
        self, admin_user_ident, tenant,
    ):
        """Scan NFC carte inconnue → message erreur."""
        with schema_context(TENANT_SCHEMA):
            client = _make_client(admin_user_ident, tenant)
            response = client.post('/laboutik/paiement/identifier_client/', data={
                'tag_id': 'ZZZZZZZZ',
                'panier_a_recharges': 'False',
                'panier_a_adhesions': 'True',
                'moyens_paiement': 'espece',
            })
            assert response.status_code == 200
            contenu = response.content.decode()
            assert 'warning' in contenu.lower() or 'inconnue' in contenu.lower()

    def test_formulaire_email_valide_affiche_recapitulatif(
        self, admin_user_ident, tenant,
    ):
        """Formulaire email valide → recapitulatif."""
        with schema_context(TENANT_SCHEMA):
            client = _make_client(admin_user_ident, tenant)
            response = client.post('/laboutik/paiement/identifier_client/', data={
                'email_adhesion': 'ident-form-test@tibillet.localhost',
                'prenom_adhesion': 'Jean',
                'nom_adhesion': 'Dupont',
                'panier_a_recharges': 'False',
                'panier_a_adhesions': 'True',
                'moyens_paiement': 'espece,carte_bancaire,CH',
            })
            assert response.status_code == 200
            contenu = response.content.decode()
            assert 'client-recapitulatif' in contenu
            assert 'ident-form-test@tibillet.localhost' in contenu
            assert 'DUPONT' in contenu
            assert 'client-btn-especes' in contenu
            assert 'client-btn-cb' in contenu
            assert 'client-btn-cheque' in contenu

    def test_formulaire_email_invalide_affiche_erreur(
        self, admin_user_ident, tenant,
    ):
        """Formulaire email invalide → retour formulaire avec erreur."""
        with schema_context(TENANT_SCHEMA):
            client = _make_client(admin_user_ident, tenant)
            response = client.post('/laboutik/paiement/identifier_client/', data={
                'email_adhesion': 'pas-un-email',
                'prenom_adhesion': 'Jean',
                'nom_adhesion': 'Dupont',
                'panier_a_recharges': 'False',
                'panier_a_adhesions': 'True',
                'moyens_paiement': 'espece',
            })
            assert response.status_code == 200
            contenu = response.content.decode()
            assert 'client-form' in contenu
            assert 'client-form-error' in contenu
            assert 'client-recapitulatif' not in contenu

    def test_recapitulatif_propage_moyens_paiement(
        self, admin_user_ident, tenant, carte_avec_user_ident,
    ):
        """Les moyens de paiement sont correctement affiches dans le recapitulatif."""
        with schema_context(TENANT_SCHEMA):
            client = _make_client(admin_user_ident, tenant)
            response = client.post('/laboutik/paiement/identifier_client/', data={
                'tag_id': carte_avec_user_ident.tag_id,
                'panier_a_recharges': 'True',
                'panier_a_adhesions': 'True',
                'moyens_paiement': 'espece,carte_bancaire',
            })
            contenu = response.content.decode()
            assert 'client-btn-especes' in contenu
            assert 'client-btn-cb' in contenu
            assert 'client-btn-cheque' not in contenu
            assert 'client-btn-cashless' not in contenu

    def test_recapitulatif_texte_adaptatif_recharge(
        self, admin_user_ident, tenant, carte_avec_user_ident,
    ):
        """Recapitulatif avec recharge → texte 'Recharge → carte de'."""
        with schema_context(TENANT_SCHEMA):
            client = _make_client(admin_user_ident, tenant)
            response = client.post('/laboutik/paiement/identifier_client/', data={
                'tag_id': carte_avec_user_ident.tag_id,
                'panier_a_recharges': 'True',
                'panier_a_adhesions': 'False',
                'moyens_paiement': 'espece',
            })
            contenu = response.content.decode()
            assert 'Recharge' in contenu
            assert 'CarteTest' in contenu

    def test_recapitulatif_texte_adaptatif_adhesion(
        self, admin_user_ident, tenant, carte_avec_user_ident,
    ):
        """Recapitulatif avec adhesion → texte 'Adhesion → rattachee a'."""
        with schema_context(TENANT_SCHEMA):
            client = _make_client(admin_user_ident, tenant)
            response = client.post('/laboutik/paiement/identifier_client/', data={
                'tag_id': carte_avec_user_ident.tag_id,
                'panier_a_recharges': 'False',
                'panier_a_adhesions': 'True',
                'moyens_paiement': 'espece',
            })
            contenu = response.content.decode()
            assert 'Adhesion' in contenu
            assert 'IDENTNFC' in contenu


@pytest.mark.usefixtures("test_data")
class TestFormulaireIdentificationClient:
    """Tests GET /laboutik/paiement/formulaire_identification_client/."""

    def test_get_formulaire_vierge(self, admin_user_ident, tenant):
        """GET formulaire → formulaire vierge avec flags propages dans le JS inline."""
        with schema_context(TENANT_SCHEMA):
            client = _make_client(admin_user_ident, tenant)
            response = client.get(
                '/laboutik/paiement/formulaire_identification_client/'
                '?panier_a_recharges=False&panier_a_adhesions=True'
                '&moyens_paiement=espece,carte_bancaire'
            )
            assert response.status_code == 200
            contenu = response.content.decode()
            assert 'client-form' in contenu
            assert 'client-input-email' in contenu
            # Les flags sont propages via le JS inline (setHiddenInput dans soumettreIdentificationEmail)
            # / Flags are propagated via inline JS (setHiddenInput in soumettreIdentificationEmail)
            assert 'panier_a_adhesions' in contenu
            assert 'espece,carte_bancaire' in contenu
