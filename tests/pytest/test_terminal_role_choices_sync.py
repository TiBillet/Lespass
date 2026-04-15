"""
Garantit que les choices de terminal_role restent synchronisés entre
TibilletUser (source de vérité) et PairingDevice (duplication pour
éviter l'import circulaire discovery → AuthBillet → Customers → discovery).

/ Ensures that terminal_role choices stay in sync between TibilletUser
(source of truth) and PairingDevice (duplicated to avoid circular import).
"""
from AuthBillet.models import TibilletUser
from discovery.models import PairingDevice


def test_pairingdevice_terminal_role_choices_match_tibilletuser():
    """
    Les valeurs (clés) des choices doivent être identiques des deux côtés.
    / Choice values (keys) must be identical on both sides.
    """
    tibilletuser_values = {value for value, _label in TibilletUser.TERMINAL_ROLE_CHOICES}
    pairingdevice_field = PairingDevice._meta.get_field('terminal_role')
    pairingdevice_values = {value for value, _label in pairingdevice_field.choices}

    assert tibilletuser_values == pairingdevice_values, (
        f"TERMINAL_ROLE_CHOICES desync: "
        f"TibilletUser={tibilletuser_values} vs "
        f"PairingDevice={pairingdevice_values}. "
        f"Keep both lists in sync."
    )


def test_laboutik_role_constant_exists():
    """ROLE_LABOUTIK doit exister comme constante / ROLE_LABOUTIK must be a constant."""
    assert hasattr(TibilletUser, 'ROLE_LABOUTIK')
    assert TibilletUser.ROLE_LABOUTIK == 'LB'


def test_tireuse_role_constant_exists():
    assert hasattr(TibilletUser, 'ROLE_TIREUSE')
    assert TibilletUser.ROLE_TIREUSE == 'TI'


def test_kiosque_role_constant_exists():
    assert hasattr(TibilletUser, 'ROLE_KIOSQUE')
    assert TibilletUser.ROLE_KIOSQUE == 'KI'
