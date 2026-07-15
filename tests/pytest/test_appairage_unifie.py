"""
Tests de l'appairage unifie : les trois roles suivent le meme pipeline.
/ Tests of unified pairing: all three roles follow the same pipeline.

LOCALISATION : tests/pytest/test_appairage_unifie.py

CE QUE CES TESTS PROTEGENT :

1. La tireuse etait le vilain petit canard : elle n'avait ni compte ni Terminal, et son
   PairingDevice lui servait d'identite durable. On ne pouvait donc pas la revoquer.
   Desormais elle suit le meme chemin qu'une caisse.

2. Un code PIN oublie dans l'admin restait reclamable indefiniment. Il expire maintenant.

PIEGE MULTI-TENANT :
On utilise tenant_context(), jamais schema_context() : schema_context pose un FakeTenant,
et TermUser.save() lit connection.tenant pour poser client_source.
"""
import uuid
from datetime import timedelta

import pytest
from django.utils import timezone
from django_tenants.utils import tenant_context

from Customers.models import Client as TenantClient
from discovery.models import PairingDevice


@pytest.fixture
def tenant_lespass():
    return TenantClient.objects.get(schema_name='lespass')


# --- La duree de vie du code PIN ---
# / The PIN's lifetime


@pytest.mark.django_db
def test_un_pin_frais_est_valide(tenant_lespass):
    """Un code PIN qui vient d'etre cree est reclamable. / A fresh PIN is claimable."""
    device = PairingDevice.objects.create(
        name="Caisse neuve",
        tenant=tenant_lespass,
        pin_code=PairingDevice.generate_unique_pin(),
        terminal_role='LB',
    )

    assert device.pin_est_expire() is False


@pytest.mark.django_db
def test_un_pin_trop_vieux_expire(tenant_lespass):
    """
    Un code PIN oublie dans l'admin cesse d'etre reclamable.
    Sans cela, un code affiche sur un ecran des semaines plus tot restait une porte
    ouverte — et il n'y a que 900 000 codes possibles.
    / A forgotten PIN stops being claimable. Otherwise it stays an open door.
    """
    device = PairingDevice.objects.create(
        name="Caisse oubliee",
        tenant=tenant_lespass,
        pin_code=PairingDevice.generate_unique_pin(),
        terminal_role='LB',
    )

    # On vieillit le code au-dela de sa duree de vie.
    # created_at porte auto_now_add : on force la valeur par un update() en base.
    # / We age the PIN past its lifetime. created_at is auto_now_add: force it via update().
    date_trop_ancienne = timezone.now() - PairingDevice.DUREE_DE_VIE_DU_PIN - timedelta(minutes=1)
    PairingDevice.objects.filter(pk=device.pk).update(created_at=date_trop_ancienne)
    device.refresh_from_db()

    assert device.pin_est_expire() is True


@pytest.mark.django_db
def test_le_claim_refuse_un_pin_expire(tenant_lespass):
    """Le claim refuse un code PIN expire. / The claim rejects an expired PIN."""
    from django.test import Client as HttpClient

    device = PairingDevice.objects.create(
        name="Caisse expiree",
        tenant=tenant_lespass,
        pin_code=PairingDevice.generate_unique_pin(),
        terminal_role='LB',
    )
    pin_expire = device.pin_code

    date_trop_ancienne = timezone.now() - PairingDevice.DUREE_DE_VIE_DU_PIN - timedelta(minutes=1)
    PairingDevice.objects.filter(pk=device.pk).update(created_at=date_trop_ancienne)

    # Le claim arrive sur le domaine PUBLIC : l'appareil ne connait pas encore son lieu.
    # / The claim lands on the PUBLIC domain: the device does not know its venue yet.
    reponse = HttpClient().post(
        '/api/discovery/claim/',
        data={'pin_code': str(pin_expire)},
        content_type='application/json',
        HTTP_HOST='tibillet.localhost',
    )

    assert reponse.status_code == 400

    # Et le code n'a evidemment pas ete consomme.
    # / And the PIN was of course not consumed.
    device.refresh_from_db()
    assert device.is_claimed is False


@pytest.mark.django_db
def test_regenerer_le_pin_redonne_un_code_valide(tenant_lespass):
    """
    Quand un code a expire, on en redemande un plutot que de tout recommencer.
    / When a PIN has expired, a fresh one is issued rather than starting over.
    """
    device = PairingDevice.objects.create(
        name="Caisse a relancer",
        tenant=tenant_lespass,
        pin_code=PairingDevice.generate_unique_pin(),
        terminal_role='LB',
    )
    ancien_code = device.pin_code

    date_trop_ancienne = timezone.now() - PairingDevice.DUREE_DE_VIE_DU_PIN - timedelta(minutes=1)
    PairingDevice.objects.filter(pk=device.pk).update(created_at=date_trop_ancienne)
    device.refresh_from_db()
    assert device.pin_est_expire() is True

    device.regenerer_le_pin()

    # On RELIT depuis la base : c'est le seul moyen de prouver que le nouveau created_at a
    # bien ete ecrit. Le champ porte auto_now_add, qui n'agit qu'a la creation de la ligne —
    # sans cette relecture, l'assertion passerait meme si la base avait ignore l'ecriture,
    # et le code resterait expire en vrai.
    # / Re-read from the DB: the only way to prove the new created_at was really written.
    device.refresh_from_db()

    assert device.pin_est_expire() is False
    assert device.pin_code != ancien_code


@pytest.mark.django_db
def test_on_ne_regenere_pas_le_pin_d_un_appareil_deja_appaire(tenant_lespass):
    """
    Un appairage deja consomme ne se regenere pas.
    Sinon l'appareil reapparaitrait « en attente » dans l'admin, avec un code qui
    echouerait a chaque fois — son compte existe deja, et son email est unique — pendant
    que l'ancien terminal continue de tourner.
    / An already-claimed pairing cannot be regenerated: it would show a PIN that always
    fails, while the old terminal keeps running.
    """
    device = PairingDevice.objects.create(
        name="Caisse deja appairee",
        tenant=tenant_lespass,
        pin_code=PairingDevice.generate_unique_pin(),
        terminal_role='LB',
    )
    device.claim()
    assert device.is_claimed is True

    with pytest.raises(ValueError):
        device.regenerer_le_pin()

    # L'appairage reste consomme, et sans code.
    # / The pairing stays consumed, with no PIN.
    device.refresh_from_db()
    assert device.is_claimed is True
    assert device.pin_code is None


# --- La tireuse suit le meme pipeline que les autres ---
# / The tap follows the same pipeline as the others


@pytest.mark.django_db
def test_creer_une_tireuse_fabrique_son_terminal_et_son_code_pin(tenant_lespass):
    """
    Une tireuse nait avec son Raspberry Pi (un Terminal) et le code PIN qui permettra de
    l'appairer. Le gestionnaire n'a qu'un objet a creer : la tireuse.
    / A tap is born with its Raspberry Pi (a Terminal) and the PIN to pair it.

    LE POINT IMPORTANT : la tireuse et son Pi sont DEUX objets. La tireuse porte le metier
    (fut, prix, historique) ; le Pi porte le materiel, et le materiel est jetable.
    """
    with tenant_context(tenant_lespass):
        from controlvanne.models import TireuseBec
        from laboutik.models import PointDeVente

        tireuse = TireuseBec.objects.create(
            nom_tireuse=f"Tireuse test {uuid.uuid4().hex[:6]}",
        )
        # Le signal cree aussi un point de vente : on le masque pour ne pas polluer les
        # autres tests qui prennent « le premier point de vente ».
        # / The signal also creates a POS: hide it so it does not pollute other tests.
        if tireuse.point_de_vente:
            PointDeVente.objects.filter(pk=tireuse.point_de_vente_id).update(hidden=True)

        # Le terminal existe, en attente de son appareil.
        # / The terminal exists, waiting for its device.
        assert tireuse.terminal is not None
        assert tireuse.terminal.terminal_role == 'TI'
        assert tireuse.terminal.est_appaire() is False

        code_pin = tireuse.terminal.code_pin_en_attente()
        assert code_pin is not None

    # Le code PIN designe le TERMINAL, pas la tireuse : c'est le materiel qu'on appaire.
    # / The PIN targets the TERMINAL, not the tap: hardware is what gets paired.
    appairage = PairingDevice.objects.get(cible_uuid=tireuse.terminal_id)
    assert appairage.pin_code == code_pin
    assert appairage.terminal_role == 'TI'


@pytest.mark.django_db
def test_revoquer_une_tireuse_coupe_sa_cle(tenant_lespass):
    """
    Une tireuse appairee se revoque comme une caisse : compte desactive ET cle coupee.
    C'etait impossible avant — la tireuse n'avait ni compte, ni cle rattachee a un compte.
    / A paired tap is revoked like a cash register. This was impossible before.
    """
    from django.test import Client as HttpClient

    from Administration.admin.laboutik import TerminalAdmin
    from Administration.admin.site import staff_admin_site

    with tenant_context(tenant_lespass):
        from controlvanne.models import TireuseBec
        from laboutik.models import PointDeVente

        tireuse = TireuseBec.objects.create(
            nom_tireuse=f"Tireuse a revoquer {uuid.uuid4().hex[:6]}",
        )
        if tireuse.point_de_vente:
            PointDeVente.objects.filter(pk=tireuse.point_de_vente_id).update(hidden=True)

    appairage = PairingDevice.objects.get(cible_uuid=tireuse.terminal_id)

    reponse = HttpClient().post(
        '/api/discovery/claim/',
        data={'pin_code': str(appairage.pin_code)},
        content_type='application/json',
        HTTP_HOST='tibillet.localhost',
    )
    assert reponse.status_code == 200

    with tenant_context(tenant_lespass):
        from controlvanne.models import TireuseAPIKey, TireuseBec
        from laboutik.models import Terminal

        tireuse.refresh_from_db()
        terminal_de_la_tireuse = tireuse.terminal
        assert terminal_de_la_tireuse is not None

        cle_avant = TireuseAPIKey.objects.get(user=terminal_de_la_tireuse.term_user)
        assert cle_avant.revoked is False
        assert terminal_de_la_tireuse.term_user.is_active is True

        # On revoque depuis l'admin, exactement comme le ferait le gestionnaire.
        # / Revoke from the admin, exactly as a manager would.
        admin_des_terminaux = TerminalAdmin(Terminal, staff_admin_site)
        admin_des_terminaux.message_user = lambda *args, **kwargs: None
        admin_des_terminaux.revoquer_les_terminaux(
            None, Terminal.objects.filter(pk=terminal_de_la_tireuse.pk),
        )

        terminal_de_la_tireuse.term_user.refresh_from_db()
        cle_apres = TireuseAPIKey.objects.get(pk=cle_avant.pk)

        # Les DEUX leviers : sans la revocation de la cle, il suffirait de reactiver le
        # compte pour que le Pi se reconnecte tout seul.
        # / BOTH levers: the key is stored on the device.
        assert terminal_de_la_tireuse.term_user.is_active is False
        assert cle_apres.revoked is True
