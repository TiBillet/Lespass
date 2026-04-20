"""
Tests du RefillAmountSerializer : validation des bornes (1 EUR / 500 EUR).
Tests for RefillAmountSerializer: amount boundary validation.

LOCALISATION : tests/pytest/test_refill_serializer.py

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_refill_serializer.py -v --api-key dummy
"""

import sys

sys.path.insert(0, "/DjangoFiles")

import django

django.setup()

from PaiementStripe.serializers import RefillAmountSerializer


def test_refill_serializer_accepte_borne_min():
    """100 centimes (1,00 EUR) est accepte."""
    serializer = RefillAmountSerializer(data={"amount_cents": 100})
    assert serializer.is_valid(), serializer.errors


def test_refill_serializer_accepte_borne_max():
    """50000 centimes (500,00 EUR) est accepte."""
    serializer = RefillAmountSerializer(data={"amount_cents": 50000})
    assert serializer.is_valid(), serializer.errors


def test_refill_serializer_rejette_sous_borne_min():
    """99 centimes est rejete."""
    serializer = RefillAmountSerializer(data={"amount_cents": 99})
    assert not serializer.is_valid()
    assert "amount_cents" in serializer.errors


def test_refill_serializer_rejette_au_dessus_borne_max():
    """50001 centimes est rejete."""
    serializer = RefillAmountSerializer(data={"amount_cents": 50001})
    assert not serializer.is_valid()
    assert "amount_cents" in serializer.errors


def test_refill_serializer_rejette_champ_manquant():
    """Absence de amount_cents est rejete."""
    serializer = RefillAmountSerializer(data={})
    assert not serializer.is_valid()
    assert "amount_cents" in serializer.errors
