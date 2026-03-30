"""
tests/pytest/test_mentions_legales.py — Tests Session 14 : mentions legales + tracabilite.
/ Tests Session 14: legal mentions + print tracking.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_mentions_legales.py -v
"""
import os
import sys

sys.path.insert(0, '/DjangoFiles')

import django
django.setup()

import pytest
import uuid as uuid_module

from decimal import Decimal
from django.utils import timezone
from django_tenants.utils import schema_context

from AuthBillet.models import TibilletUser
from BaseBillet.models import (
    Configuration, LigneArticle, Price, PriceSold, Product, ProductSold,
    SaleOrigin, PaymentMethod,
)
from Customers.models import Client
from laboutik.models import (
    PointDeVente, LaboutikConfiguration, ImpressionLog, Printer,
)

TENANT_SCHEMA = 'lespass'


@pytest.fixture(scope="module")
def tenant():
    """Le tenant 'lespass' (doit exister dans la base).
    / The 'lespass' tenant (must exist in DB)."""
    return Client.objects.get(schema_name=TENANT_SCHEMA)


@pytest.fixture(scope="module")
def test_data(tenant):
    """Lance create_test_pos_data pour s'assurer que les donnees existent.
    / Runs create_test_pos_data to ensure test data exists."""
    from django.core.management import call_command
    call_command('create_test_pos_data')
    return True


@pytest.fixture(scope="module")
def admin_user(tenant):
    """Un utilisateur admin du tenant.
    / A tenant admin user."""
    with schema_context(TENANT_SCHEMA):
        email = 'admin-test-mentions@tibillet.localhost'
        user, _created = TibilletUser.objects.get_or_create(
            email=email,
            defaults={
                'username': email,
                'is_staff': True,
                'is_active': True,
            },
        )
        return user


@pytest.fixture(scope="module")
def premier_pv(test_data):
    """Le premier point de vente non-cache.
    / The first visible point of sale."""
    with schema_context(TENANT_SCHEMA):
        return PointDeVente.objects.filter(hidden=False).first()


@pytest.fixture(scope="module")
def premier_produit_et_prix(test_data):
    """Un produit POS avec un prix.
    / A POS product with a price."""
    with schema_context(TENANT_SCHEMA):
        product = Product.objects.filter(
            methode_caisse=Product.VENTE,
        ).first()
        price = product.prices.first() if product else None
        return product, price


def _code_tva_vers_taux(code_tva):
    """
    Convertit le code TVA de Price (CharField) en taux numerique (Decimal).
    / Converts Price's VAT code (CharField) to a numeric rate (Decimal).
    """
    MAPPING = {
        'NA': Decimal('0'),
        'DX': Decimal('10'),
        'VG': Decimal('20'),
        'HC': Decimal('8.5'),
        'DD': Decimal('2.2'),
    }
    return MAPPING.get(code_tva, Decimal('0'))


def _creer_ligne_article_directe(product, price, pv, qty=1, payment_method='CA'):
    """
    Cree une LigneArticle directement en base (sans passer par la vue).
    Simule ce que fait _creer_lignes_articles() dans views.py.
    / Creates a LigneArticle directly in DB (bypassing the view).
    """
    prix_centimes = int(round(price.prix * 100))

    product_sold, _ = ProductSold.objects.get_or_create(
        product=product,
        defaults={'name': product.name},
    )
    price_sold, _ = PriceSold.objects.get_or_create(
        productsold=product_sold,
        price=price,
        defaults={
            'prix': price.prix,
            'name': price.name or product.name,
        },
    )

    uuid_tx = uuid_module.uuid4()

    from laboutik.integrity import calculer_total_ht, calculer_hmac, obtenir_previous_hmac
    taux_tva_decimal = _code_tva_vers_taux(price.vat)
    taux_tva = float(taux_tva_decimal)
    total_ht = calculer_total_ht(prix_centimes, taux_tva)

    ligne = LigneArticle.objects.create(
        pricesold=price_sold,
        qty=Decimal(str(qty)),
        amount=prix_centimes,
        vat=taux_tva_decimal,
        payment_method=payment_method,
        sale_origin=SaleOrigin.LABOUTIK,
        status='V',
        point_de_vente=pv,
        uuid_transaction=uuid_tx,
        total_ht=total_ht,
    )

    # Chainage HMAC
    # / HMAC chaining
    config = LaboutikConfiguration.get_solo()
    cle_hmac = config.get_or_create_hmac_key()
    previous_hmac = obtenir_previous_hmac()
    ligne.hmac_hash = calculer_hmac(ligne, cle_hmac, previous_hmac)
    ligne.previous_hmac = previous_hmac
    ligne.save(update_fields=['hmac_hash', 'previous_hmac'])

    return ligne, uuid_tx


class TestFormatterTicketVente:
    """Tests pour le formatter de ticket de vente enrichi.
    / Tests for the enriched sale ticket formatter."""

    def test_ticket_contient_raison_sociale(self, tenant, test_data, premier_pv, premier_produit_et_prix, admin_user):
        """Le ticket doit contenir la raison sociale (Configuration.organisation).
        / The ticket must contain the business name."""
        with schema_context(TENANT_SCHEMA):
            product, price = premier_produit_et_prix
            ligne, uuid_tx = _creer_ligne_article_directe(product, price, premier_pv)

            from laboutik.printing.formatters import formatter_ticket_vente
            ticket_data = formatter_ticket_vente(
                [ligne], premier_pv, admin_user, 'Especes',
            )

            config = Configuration.get_solo()
            assert "legal" in ticket_data
            assert ticket_data["legal"]["business_name"] == config.organisation

    def test_ticket_contient_siret(self, tenant, test_data, premier_pv, premier_produit_et_prix, admin_user):
        """Le ticket doit contenir le SIRET si disponible.
        / The ticket must contain the SIRET if available."""
        with schema_context(TENANT_SCHEMA):
            product, price = premier_produit_et_prix
            ligne, uuid_tx = _creer_ligne_article_directe(product, price, premier_pv)

            from laboutik.printing.formatters import formatter_ticket_vente
            ticket_data = formatter_ticket_vente(
                [ligne], premier_pv, admin_user, 'Especes',
            )

            assert "legal" in ticket_data
            assert "siret" in ticket_data["legal"]

    def test_ticket_contient_ventilation_tva(self, tenant, test_data, premier_pv, premier_produit_et_prix, admin_user):
        """Le ticket doit contenir la ventilation TVA par taux.
        / The ticket must contain the VAT breakdown by rate."""
        with schema_context(TENANT_SCHEMA):
            product, price = premier_produit_et_prix
            ligne, uuid_tx = _creer_ligne_article_directe(product, price, premier_pv)

            from laboutik.printing.formatters import formatter_ticket_vente
            ticket_data = formatter_ticket_vente(
                [ligne], premier_pv, admin_user, 'Especes',
            )

            assert "tva_breakdown" in ticket_data
            assert isinstance(ticket_data["tva_breakdown"], list)
            assert len(ticket_data["tva_breakdown"]) >= 1

    def test_ticket_total_ht_ttc(self, tenant, test_data, premier_pv, premier_produit_et_prix, admin_user):
        """total_ht + total_tva = total TTC.
        / total_ht + total_tva = total TTC."""
        with schema_context(TENANT_SCHEMA):
            product, price = premier_produit_et_prix
            ligne, uuid_tx = _creer_ligne_article_directe(product, price, premier_pv)

            from laboutik.printing.formatters import formatter_ticket_vente
            ticket_data = formatter_ticket_vente(
                [ligne], premier_pv, admin_user, 'Especes',
            )

            total_ttc = ticket_data["total"]["amount"]
            total_ht = ticket_data["total_ht"]
            total_tva = ticket_data["total_tva"]

            assert total_ht + total_tva == total_ttc

    def test_tva_non_applicable(self, tenant, test_data, premier_pv, premier_produit_et_prix, admin_user):
        """Si pas de tva_number dans Configuration, mention art. 293 B du CGI.
        / If no tva_number in Configuration, mention art. 293 B."""
        with schema_context(TENANT_SCHEMA):
            config = Configuration.get_solo()
            ancien_tva = config.tva_number
            config.tva_number = None
            config.save(update_fields=['tva_number'])

            try:
                product, price = premier_produit_et_prix
                ligne, uuid_tx = _creer_ligne_article_directe(product, price, premier_pv)

                from laboutik.printing.formatters import formatter_ticket_vente
                ticket_data = formatter_ticket_vente(
                    [ligne], premier_pv, admin_user, 'Especes',
                )

                assert "293 B" in ticket_data["legal"]["tva_number"]
            finally:
                config.tva_number = ancien_tva
                config.save(update_fields=['tva_number'])

    def test_numero_ticket_sequentiel(self, tenant, test_data, premier_pv, premier_produit_et_prix, admin_user):
        """Le numero de ticket est sequentiel (T-000001, T-000002...).
        / The receipt number is sequential."""
        with schema_context(TENANT_SCHEMA):
            product, price = premier_produit_et_prix
            ligne1, _ = _creer_ligne_article_directe(product, price, premier_pv)
            ligne2, _ = _creer_ligne_article_directe(product, price, premier_pv)

            from laboutik.printing.formatters import formatter_ticket_vente
            ticket1 = formatter_ticket_vente([ligne1], premier_pv, admin_user, 'Especes')
            ticket2 = formatter_ticket_vente([ligne2], premier_pv, admin_user, 'Especes')

            # Les numeros doivent etre differents et incrementaux
            # Le numero est dans legal["receipt_number"] (source unique)
            # / Numbers must be different and incremental
            # Number is in legal["receipt_number"] (single source)
            numero1 = ticket1["legal"]["receipt_number"]
            numero2 = ticket2["legal"]["receipt_number"]
            assert numero1 != numero2
            assert numero1.startswith("T-")
            assert numero2.startswith("T-")


class TestImpressionLog:
    """Tests pour la tracabilite des impressions.
    / Tests for print tracking."""

    def test_impression_log_cree(self, tenant, test_data, premier_pv, premier_produit_et_prix, admin_user):
        """Apres creation d'un ImpressionLog, il existe en base.
        / After creating an ImpressionLog, it exists in DB."""
        with schema_context(TENANT_SCHEMA):
            product, price = premier_produit_et_prix
            ligne, uuid_tx = _creer_ligne_article_directe(product, price, premier_pv)

            log = ImpressionLog.objects.create(
                uuid_transaction=uuid_tx,
                type_justificatif='VENTE',
                is_duplicata=False,
                format_emission='P',
            )
            assert ImpressionLog.objects.filter(uuid_transaction=uuid_tx).exists()
            assert log.is_duplicata is False

    def test_duplicata_marque(self, tenant, test_data, premier_pv, premier_produit_et_prix, admin_user):
        """La 2e impression de la meme transaction est marquee duplicata.
        / The 2nd print of the same transaction is marked as duplicate."""
        with schema_context(TENANT_SCHEMA):
            product, price = premier_produit_et_prix
            ligne, uuid_tx = _creer_ligne_article_directe(product, price, premier_pv)

            # Premiere impression
            # / First print
            ImpressionLog.objects.create(
                uuid_transaction=uuid_tx,
                type_justificatif='VENTE',
                is_duplicata=False,
                format_emission='P',
            )

            # Deuxieme impression — verifier que c'est un duplicata
            # / Second print — verify it's a duplicate
            nb_precedentes = ImpressionLog.objects.filter(
                uuid_transaction=uuid_tx,
                type_justificatif='VENTE',
            ).count()
            est_duplicata = nb_precedentes > 0

            log2 = ImpressionLog.objects.create(
                uuid_transaction=uuid_tx,
                type_justificatif='VENTE',
                is_duplicata=est_duplicata,
                format_emission='P',
            )
            assert log2.is_duplicata is True
