"""
Tests des filtres template money (BaseBillet/templatetags/billet_filters.py).
Tests of money template filters.
"""
import pytest

from BaseBillet.templatetags.billet_filters import cents_to_euros, cents_to_asset


class FakeAsset:
    """Mock leger d'un Asset pour tester cents_to_asset sans toucher la DB."""
    def __init__(self, currency_code: str):
        self.currency_code = currency_code


class TestCentsToEuros:
    def test_montant_simple(self):
        assert cents_to_euros(12750) == "127,50 €"

    def test_zero(self):
        assert cents_to_euros(0) == "0,00 €"

    def test_none(self):
        assert cents_to_euros(None) == "0,00 €"

    def test_negatif(self):
        assert cents_to_euros(-500) == "-5,00 €"

    def test_milliers_espace_insecable(self):
        # 1 234,56 € avec espace insecable U+00A0
        assert cents_to_euros(123456) == "1\u00a0234,56 €"

    def test_negatif_avec_centimes(self):
        # -567 cents = -5,67 € (verification arithmetique entiere, pas de float)
        assert cents_to_euros(-567) == "-5,67 €"

    def test_negatif_milliers(self):
        # -123456 cents = -1 234,56 €
        assert cents_to_euros(-123456) == "-1\u00a0234,56 €"


class TestCentsToAsset:
    def test_asset_eur_affiche_symbole_euro(self):
        asset = FakeAsset(currency_code="EUR")
        assert cents_to_asset(12750, asset) == "127,50 €"

    def test_asset_tmp_affiche_code(self):
        asset = FakeAsset(currency_code="TMP")
        assert cents_to_asset(12750, asset) == "127,50 TMP"

    def test_asset_pts_affiche_code(self):
        asset = FakeAsset(currency_code="PTS")
        assert cents_to_asset(500, asset) == "5,00 PTS"

    def test_asset_none_fallback_euros(self):
        # Fallback : si asset = None, comportement euros par defaut
        assert cents_to_asset(12750, None) == "127,50 €"

    def test_zero_multi_currency(self):
        asset = FakeAsset(currency_code="TMP")
        assert cents_to_asset(0, asset) == "0,00 TMP"

    def test_none_montant_multi_currency(self):
        asset = FakeAsset(currency_code="PTS")
        assert cents_to_asset(None, asset) == "0,00 PTS"

    def test_negatif_multi_currency(self):
        asset = FakeAsset(currency_code="TMP")
        assert cents_to_asset(-500, asset) == "-5,00 TMP"

    def test_milliers_multi_currency(self):
        asset = FakeAsset(currency_code="TMP")
        assert cents_to_asset(123456, asset) == "1\u00a0234,56 TMP"

    def test_negatif_avec_centimes_multi_currency(self):
        asset = FakeAsset(currency_code="TMP")
        assert cents_to_asset(-567, asset) == "-5,67 TMP"
