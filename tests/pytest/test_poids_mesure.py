"""
tests/pytest/test_poids_mesure.py — Tests poids/mesure : HMAC, modele, validation.
/ Tests for weight/volume sales: HMAC, model, validation.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_poids_mesure.py -v
"""

import sys

sys.path.insert(0, "/DjangoFiles")

import django

django.setup()

from unittest.mock import MagicMock


class TestHmacWeightQuantity:
    """Le HMAC doit inclure weight_quantity pour la conformite LNE exigence 8.
    / HMAC must include weight_quantity for LNE compliance requirement 8."""

    def _make_mock_ligne(self, weight_quantity=None):
        """Cree un mock de LigneArticle avec les champs necessaires au HMAC.
        / Creates a LigneArticle mock with the fields needed for HMAC."""
        ligne = MagicMock()
        ligne.uuid = "00000000-0000-0000-0000-000000000001"
        ligne.datetime = None
        ligne.amount = 980
        ligne.total_ht = 817
        ligne.qty = 1
        ligne.vat = 20.0
        ligne.payment_method = "CA"
        ligne.status = "V"
        ligne.sale_origin = "LB"
        ligne.weight_quantity = weight_quantity
        return ligne

    def test_hmac_avec_weight_quantity_different_de_sans(self):
        """Le HMAC d'une ligne avec weight_quantity=350 est different d'une ligne sans.
        / HMAC of a line with weight_quantity=350 differs from one without."""
        from laboutik.integrity import calculer_hmac

        ligne_sans = self._make_mock_ligne(weight_quantity=None)
        ligne_avec = self._make_mock_ligne(weight_quantity=350)

        cle = "test-secret-key"
        hmac_sans = calculer_hmac(ligne_sans, cle, "")
        hmac_avec = calculer_hmac(ligne_avec, cle, "")

        assert hmac_sans != hmac_avec, (
            "Le HMAC doit etre different quand weight_quantity change"
        )

    def test_hmac_weight_quantity_none_produit_hash_valide(self):
        """weight_quantity=None produit un HMAC hex de 64 caracteres.
        / weight_quantity=None produces a valid 64-char hex HMAC."""
        from laboutik.integrity import calculer_hmac

        ligne = self._make_mock_ligne(weight_quantity=None)
        cle = "test-secret-key"
        hmac_result = calculer_hmac(ligne, cle, "")

        assert len(hmac_result) == 64
        assert all(c in "0123456789abcdef" for c in hmac_result)

    def test_hmac_weight_quantity_deterministe(self):
        """Le meme weight_quantity produit toujours le meme HMAC.
        / Same weight_quantity always produces the same HMAC."""
        from laboutik.integrity import calculer_hmac

        ligne1 = self._make_mock_ligne(weight_quantity=350)
        ligne2 = self._make_mock_ligne(weight_quantity=350)
        cle = "test-secret-key"

        assert calculer_hmac(ligne1, cle, "") == calculer_hmac(ligne2, cle, "")

    def test_hmac_weight_quantities_differentes(self):
        """Des weight_quantity differentes produisent des HMAC differents.
        / Different weight_quantities produce different HMACs."""
        from laboutik.integrity import calculer_hmac

        ligne_350 = self._make_mock_ligne(weight_quantity=350)
        ligne_500 = self._make_mock_ligne(weight_quantity=500)
        cle = "test-secret-key"

        assert calculer_hmac(ligne_350, cle, "") != calculer_hmac(ligne_500, cle, "")


from django_tenants.utils import tenant_context
from Customers.models import Client

TENANT_SCHEMA = "lespass"


def _get_tenant():
    return Client.objects.get(schema_name=TENANT_SCHEMA)


class TestPoidsMesureValidation:
    """Validation admin : exclusions mutuelles poids_mesure / free_price / contenance.
    / Admin validation: mutual exclusions weight/free/contenance."""

    def test_poids_mesure_et_free_price_rejete(self, admin_client):
        """poids_mesure=True et free_price=True → erreur validation.
        / poids_mesure=True and free_price=True → validation error."""
        from Administration.admin.products import BasePriceInlineForm
        from BaseBillet.models import Product

        with tenant_context(_get_tenant()):
            product = Product.objects.filter(methode_caisse__isnull=False).first()
            assert product is not None

            form = BasePriceInlineForm(
                data={
                    "product": product.pk,
                    "name": "Test",
                    "prix": "10.00",
                    "free_price": True,
                    "poids_mesure": True,
                    "publish": True,
                    "order": 100,
                }
            )
            assert not form.is_valid(), "Le formulaire devrait etre invalide"
            assert "__all__" in form.errors

    def test_poids_mesure_et_contenance_rejete(self, admin_client):
        """poids_mesure=True et contenance renseignee → erreur validation.
        / poids_mesure=True and contenance set → validation error."""
        from Administration.admin.products import BasePriceInlineForm
        from BaseBillet.models import Product

        with tenant_context(_get_tenant()):
            product = Product.objects.filter(methode_caisse__isnull=False).first()

            form = BasePriceInlineForm(
                data={
                    "product": product.pk,
                    "name": "Test",
                    "prix": "10.00",
                    "free_price": False,
                    "poids_mesure": True,
                    "contenance": 50,
                    "publish": True,
                    "order": 100,
                }
            )
            assert not form.is_valid()
            assert "__all__" in form.errors
