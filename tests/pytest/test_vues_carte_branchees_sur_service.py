"""
tests/pytest/test_vues_carte_branchees_sur_service.py — Les vues carte ecrivent AUSSI cote Lespass.
tests/pytest/test_vues_carte_branchees_sur_service.py — Card views also write on the Lespass side.

POURQUOI / WHY :
`CarteService` (fedow_core/services.py) est entierement teste par
`tests/pytest/test_scan_qr_carte_v2.py` — mais ces tests appellent le SERVICE directement.
Ils restent verts meme si aucune vue ne l'appelle. C'est exactement ce qui est arrive : les
vues `lost_my_card` et `ScanQrCode.link` parlaient a Fedow sans jamais ecrire cote Lespass,
et 17 tests verts ne le voyaient pas.
/ CarteService is fully covered by test_scan_qr_carte_v2.py — but those tests call the SERVICE
directly and stay green even if no view calls it. That is precisely what happened.

Ces tests-ci couvrent la COUTURE : ils passent par l'URL reelle et verifient l'etat de la base
LOCALE. Fedow est mocke (frontiere reseau), donc un test vert prouve que la vue a bien fait sa
part du travail cote Lespass.
/ These tests cover the SEAM: they go through the real URL and check the LOCAL database state.

CE QUI EST EN JEU (test 1) : sans le detachement local, `CarteCashless.user` reste pose apres
une declaration de perte. Le point de vente resout alors la carte vers le wallet de son ancien
porteur (`_obtenir_ou_creer_wallet` rend `carte.user.wallet`) et signe la cascade avec sa cle :
qui trouve la carte depense le portefeuille de qui l'a perdue.
/ AT STAKE (test 1): without the local detach, whoever finds a lost card spends its former
holder's wallet.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_vues_carte_branchees_sur_service.py -q
"""

import uuid as uuid_module
from unittest import mock

import pytest
from django_tenants.utils import tenant_context

from Customers.models import Client


pytestmark = pytest.mark.django_db

TEST_PREFIX = "[test_vues_carte_branchees]"


def _tag():
    return f"VC{uuid_module.uuid4().hex[:6].upper()}"  # "VC" + 6 = 8 chars


@pytest.fixture
def carte_liee_a_un_user():
    """Une carte cliente liee a un user, cote Lespass, avec un wallet.
    / A user-linked client card on the Lespass side, holding a wallet.

    DB dev partagee, pas de rollback : nettoyage manuel en teardown.
    """
    from AuthBillet.models import Wallet, TibilletUser
    from QrcodeCashless.models import CarteCashless, Detail

    tenant = Client.objects.get(schema_name="lespass")
    tag = _tag()

    with tenant_context(tenant):
        detail, _detail_cree = Detail.objects.get_or_create(
            slug="test-vues-carte-branchees",
            defaults={"base_url": "test-vues.localhost", "generation": 1, "origine": tenant},
        )
        wallet = Wallet.objects.create(origin=tenant, name=f"{TEST_PREFIX} wallet")
        user = TibilletUser.objects.create(
            email=f"vues-{tag.lower()}@test.loc",
            username=f"vues-{tag.lower()}@test.loc",
            espece=TibilletUser.TYPE_HUM,
            client_source=tenant,
            is_active=True,
            email_valid=True,
            wallet=wallet,
        )
        carte = CarteCashless.objects.create(
            tag_id=tag, uuid=uuid_module.uuid4(), number=tag, detail=detail, user=user
        )

    yield {"tenant": tenant, "carte": carte, "user": user, "wallet": wallet}

    with tenant_context(tenant):
        CarteCashless.objects.filter(pk=carte.pk).delete()
        user.refresh_from_db()
        user.wallet = None
        user.save(update_fields=["wallet"])
        user.delete()
        Wallet.objects.filter(uuid=wallet.uuid).delete()


def test_lost_my_card_detache_la_carte_cote_lespass(carte_liee_a_un_user):
    """Declarer une carte perdue doit la detacher DANS LA BASE LESPASS, pas seulement chez Fedow.
    / Reporting a card lost must detach it IN THE LESPASS DATABASE, not only on Fedow.

    Tant que `CarteCashless.user` reste pose, la carte perdue continue d'ouvrir le
    portefeuille de son ancien porteur au point de vente.
    / While CarteCashless.user stays set, the lost card keeps opening its former holder's
    wallet at the POS.
    """
    from django.test import Client as DjangoClient
    from QrcodeCashless.models import CarteCashless

    tenant = carte_liee_a_un_user["tenant"]
    carte = carte_liee_a_un_user["carte"]
    user = carte_liee_a_un_user["user"]

    navigateur = DjangoClient(HTTP_HOST="lespass.tibillet.localhost")
    navigateur.force_login(user)

    # Fedow repond « detachement fait » ; on ne teste que la part Lespass.
    # / Fedow answers "detached"; we only test the Lespass side.
    api = mock.MagicMock()
    api.NFCcard.lost_my_card_by_signature.return_value = True

    with mock.patch("BaseBillet.views.FedowAPI", return_value=api):
        reponse = navigateur.get(f"/my_account/{carte.number}/lost_my_card/")

    assert reponse.status_code in (200, 204, 302), f"statut inattendu : {reponse.status_code}"
    assert api.NFCcard.lost_my_card_by_signature.called, "Fedow n'a pas ete prevenu."

    with tenant_context(tenant):
        carte_relue = CarteCashless.objects.get(pk=carte.pk)
        assert carte_relue.user_id is None, (
            "La carte est detachee chez Fedow mais TOUJOURS liee au user cote Lespass : "
            "le point de vente ouvrira encore le portefeuille de son ancien porteur."
        )
        assert carte_relue.wallet_ephemere_id is None


def test_lost_my_card_ne_detache_rien_si_fedow_refuse(carte_liee_a_un_user):
    """Si Fedow refuse le detachement, la carte doit rester liee cote Lespass.
    / If Fedow refuses, the card must stay linked on the Lespass side.

    Les deux bases doivent diverger le moins possible : un detachement local sans
    detachement Fedow laisserait la carte utilisable ailleurs sur le reseau.
    / A local detach without a Fedow detach would leave the card usable elsewhere.
    """
    from django.test import Client as DjangoClient
    from QrcodeCashless.models import CarteCashless

    tenant = carte_liee_a_un_user["tenant"]
    carte = carte_liee_a_un_user["carte"]
    user = carte_liee_a_un_user["user"]

    navigateur = DjangoClient(HTTP_HOST="lespass.tibillet.localhost")
    navigateur.force_login(user)

    api = mock.MagicMock()
    api.NFCcard.lost_my_card_by_signature.return_value = False  # Fedow refuse

    with mock.patch("BaseBillet.views.FedowAPI", return_value=api):
        navigateur.get(f"/my_account/{carte.number}/lost_my_card/")

    with tenant_context(tenant):
        carte_relue = CarteCashless.objects.get(pk=carte.pk)
        assert carte_relue.user_id == user.pk, (
            "La carte a ete detachee cote Lespass alors que Fedow a refuse : "
            "les deux bases divergent."
        )


@pytest.fixture
def carte_vierge_et_user_sans_carte():
    """Une carte NON liee et un user qui n'a aucune carte — l'etat d'avant un scan QR.
    / An UNLINKED card and a user with no card — the state before a QR scan.

    `CarteCashless.uuid` EST le qrcode_uuid : c'est par lui que la vue retrouve la carte.
    / CarteCashless.uuid IS the qrcode uuid: the view resolves the card by it.
    """
    from AuthBillet.models import Wallet, TibilletUser
    from QrcodeCashless.models import CarteCashless, Detail

    tenant = Client.objects.get(schema_name="lespass")
    tag = _tag()
    qrcode_uuid = uuid_module.uuid4()

    with tenant_context(tenant):
        detail, _detail_cree = Detail.objects.get_or_create(
            slug="test-vues-carte-branchees",
            defaults={"base_url": "test-vues.localhost", "generation": 1, "origine": tenant},
        )
        wallet = Wallet.objects.create(origin=tenant, name=f"{TEST_PREFIX} wallet lien")
        user = TibilletUser.objects.create(
            email=f"lien-{tag.lower()}@test.loc",
            username=f"lien-{tag.lower()}@test.loc",
            espece=TibilletUser.TYPE_HUM,
            client_source=tenant,
            is_active=True,
            email_valid=True,
            wallet=wallet,
        )
        carte = CarteCashless.objects.create(
            tag_id=tag, uuid=qrcode_uuid, number=tag, detail=detail, user=None
        )

    yield {"tenant": tenant, "carte": carte, "user": user,
           "wallet": wallet, "qrcode_uuid": qrcode_uuid}

    with tenant_context(tenant):
        CarteCashless.objects.filter(pk=carte.pk).delete()
        user.refresh_from_db()
        user.wallet = None
        user.save(update_fields=["wallet"])
        user.delete()
        Wallet.objects.filter(uuid=wallet.uuid).delete()


def test_le_parcours_qr_lie_la_carte_cote_lespass(carte_vierge_et_user_sans_carte):
    """Scanner son QR code et donner son email doit lier la carte DANS LA BASE LESPASS.
    / Scanning the QR code and giving an email must link the card IN THE LESPASS DATABASE.

    Fedow fusionne bien les wallets de son cote, mais sans `CarteCashless.user` la carte
    reste « anonyme » pour la caisse V2 : le solde federe est masque par le garde
    `if carte.user is not None` (laboutik/views.py), et l'adherent n'est pas identifiable
    au comptoir.
    / Fedow merges the wallets on its side, but without CarteCashless.user the card stays
    "anonymous" for the V2 POS.
    """
    from django.test import Client as DjangoClient
    from QrcodeCashless.models import CarteCashless

    tenant = carte_vierge_et_user_sans_carte["tenant"]
    carte = carte_vierge_et_user_sans_carte["carte"]
    user = carte_vierge_et_user_sans_carte["user"]
    wallet = carte_vierge_et_user_sans_carte["wallet"]
    qrcode_uuid = carte_vierge_et_user_sans_carte["qrcode_uuid"]

    def poser_le_wallet_du_user(user_appele):
        user_appele.wallet = wallet
        user_appele.save(update_fields=["wallet"])
        # created=True : evite la branche anti-vol de la vue, qui n'est pas l'objet du test.
        # / created=True: skips the view's anti-theft branch, not what we test here.
        return wallet, True

    api = mock.MagicMock()
    api.wallet.get_or_create_wallet.side_effect = poser_le_wallet_du_user
    api.NFCcard.linkwallet_cardqrcode.return_value = {
        "qrcode_uuid": str(qrcode_uuid),
        "number_printed": carte.number,
    }

    navigateur = DjangoClient(HTTP_HOST="lespass.tibillet.localhost")

    with mock.patch("BaseBillet.views.FedowAPI", return_value=api), \
            mock.patch("BaseBillet.views.get_or_create_user", return_value=user):
        reponse = navigateur.post(
            "/qr/link/",
            {
                "email": user.email,
                "emailConfirmation": user.email,
                "cgu": True,
                "qrcode_uuid": str(qrcode_uuid),
            },
        )

    assert reponse.status_code in (200, 204, 302), f"statut inattendu : {reponse.status_code}"
    assert api.NFCcard.linkwallet_cardqrcode.called, "Fedow n'a pas ete sollicite."

    with tenant_context(tenant):
        carte_relue = CarteCashless.objects.get(pk=carte.pk)
        assert carte_relue.user_id == user.pk, (
            "La carte est liee chez Fedow mais PAS cote Lespass : elle restera anonyme "
            "pour la caisse V2 (solde federe masque, adherent non identifiable)."
        )
