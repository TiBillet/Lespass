"""
Tests C1 — helper `obtenir_solde_complet_carte` (interop FED au POS, lot C-C).
/ C1 tests — `obtenir_solde_complet_carte` helper (FED interop at POS, batch C-C).

LOCALISATION : tests/pytest/test_c1_solde_complet_carte.py

CE QUI EST TESTÉ / WHAT IS TESTED :
Au scan d'une carte au POS V2, on affiche le solde COMPLET : monnaies locales
(fedow_core, base locale) + solde FED du réseau fédéré (lu sur le Fedow distant).
Le solde FED est lu EN TEMPS RÉEL (sans cache) et dégradé en silence si Fedow ne
répond pas (la vente n'est jamais bloquée).
/ When a card is scanned at the V2 POS, we show the FULL balance: local currencies
(fedow_core) + FED network balance (read from the remote Fedow). The FED balance is
read in real time (no cache) and degraded silently if Fedow is unreachable.

Fedow est MOCKÉ (pas de réseau) : on patche les références importées dans
`laboutik.views` (`FedowConfig`, `FedowAPI`). Les soldes locaux viennent de la vraie
base fedow_core (DB dev partagée — pas de rollback, donc get_or_create + nettoyage).
/ Fedow is MOCKED (no network): we patch the references imported in `laboutik.views`.
Local balances come from the real fedow_core DB (shared dev DB — no rollback).
"""

import uuid as uuidlib
from unittest import mock

import pytest
from django_tenants.utils import tenant_context

from test_carte_liee_chez_fedow_fed_en_caisse import jeton_de_l_ancien_fedow

pytestmark = pytest.mark.django_db


def _suffix():
    """Suffixe court unique pour éviter les collisions de noms / tag_id.
    / Short unique suffix to avoid name / tag_id collisions."""
    return uuidlib.uuid4().hex[:6]


def _tag():
    """tag_id de carte de test : 8 caractères max (piège 9.31).
    / Test card tag_id: 8 chars max (pitfall 9.31)."""
    return f"C1{_suffix().upper()}"  # "C1" + 6 = 8 caractères


@pytest.fixture
def carte_liee(tenant):
    """Une CarteCashless liée à un user qui a déjà un wallet local (fedow_core).
    Nettoyée en fin de test (DB dev partagée, pas de rollback).
    / A CarteCashless linked to a user who already has a local wallet. Cleaned afterwards.
    """
    from AuthBillet.models import Wallet
    from AuthBillet.utils import get_or_create_user
    from QrcodeCashless.models import CarteCashless

    with tenant_context(tenant):
        user = get_or_create_user(f"c1-fed-{_suffix()}@tibillet.test", send_mail=False)
        # On garantit un wallet local pour le user (sinon _obtenir_ou_creer_wallet
        # créerait un éphémère et la carte ne serait pas vraiment « liée »).
        # / Ensure a local wallet for the user (otherwise an ephemeral one would be created).
        if not user.wallet:
            user.wallet = Wallet.objects.create(
                origin=tenant, name=f"C1 wallet {_suffix()}"
            )
            user.save()
        tag = _tag()
        carte = CarteCashless.objects.create(tag_id=tag, number=tag, user=user)

    yield {"tenant": tenant, "user": user, "wallet": user.wallet, "carte": carte}

    with tenant_context(tenant):
        from fedow_core.models import Token

        Token.objects.filter(wallet=user.wallet).delete()
        carte.delete()
        try:
            user.wallet.delete()
        except Exception:
            pass  # un objet lié peut protéger le wallet — best effort
        try:
            user.delete()
        except Exception:
            pass


@pytest.fixture
def carte_anonyme(tenant):
    """Une CarteCashless anonyme (sans user). Nettoyée en fin de test, y compris le
    wallet éphémère que le helper peut créer.
    / An anonymous CarteCashless (no user). Cleaned afterwards, including the ephemeral
    wallet the helper may create.
    """
    from QrcodeCashless.models import CarteCashless

    with tenant_context(tenant):
        tag = _tag()
        carte = CarteCashless.objects.create(tag_id=tag, number=tag)

    yield {"tenant": tenant, "carte": carte}

    with tenant_context(tenant):
        from fedow_core.models import Token

        carte.refresh_from_db()
        wallet_eph = carte.wallet_ephemere
        carte.wallet_ephemere = None
        carte.save(update_fields=["wallet_ephemere"])
        carte.delete()
        if wallet_eph is not None:
            Token.objects.filter(wallet=wallet_eph).delete()
            try:
                wallet_eph.delete()
            except Exception:
                pass


def fiche_de_la_carte_avec_du_fed(carte, fed_en_centimes):
    """
    La fiche d'une carte liée chez l'ancien Fedow (`NFCcard.retrieve`), dont le
    portefeuille porte `fed_en_centimes` de FED.
    / A linked card's old Fedow record, whose wallet holds `fed_en_centimes` of FED.
    """
    return {
        "first_tag_id": carte.tag_id,
        "is_wallet_ephemere": False,
        "wallet": {
            "uuid": uuidlib.uuid4(),
            "tokens": [jeton_de_l_ancien_fedow("FED", fed_en_centimes)],
        },
    }


def test_carte_liee_fedow_ok_lit_le_fed_frais(carte_liee):
    """Carte liée + Fedow OK : le helper lit le FED sur la fiche de la CARTE, en
    temps réel, et le marque disponible. La signature de la personne n'est jamais
    utilisée.
    / Linked card + Fedow OK: the helper reads FED on the CARD record, in real time,
    and marks it available. The person's signature is never used.
    """
    from laboutik.views import obtenir_solde_complet_carte

    with (
        mock.patch("laboutik.views.FedowConfig") as MockConfig,
        mock.patch("laboutik.views.FedowAPI") as MockAPI,
    ):
        MockConfig.get_solo.return_value.can_fedow.return_value = True
        lecture_de_la_carte = MockAPI.return_value.NFCcard.retrieve
        lecture_de_la_carte.return_value = fiche_de_la_carte_avec_du_fed(
            carte_liee["carte"], 500
        )  # 5,00 € en centimes

        with tenant_context(carte_liee["tenant"]):
            solde = obtenir_solde_complet_carte(carte_liee["carte"])

    assert solde["fed_disponible"] is True
    assert solde["fed_centimes"] == 500
    # Lecture fraîche, par la carte. / Fresh read, through the card.
    lecture_de_la_carte.assert_called_once_with(carte_liee["carte"].tag_id)
    MockAPI.return_value.wallet.get_total_fiducial_and_all_federated_token.assert_not_called()


def test_carte_liee_fedow_down_degrade_sans_bloquer(carte_liee):
    """Carte liée + Fedow injoignable (Exception) : dégradé silencieux — FED indisponible,
    fed_centimes=0, et AUCUNE exception ne remonte (la vente ne doit jamais être bloquée).
    / Linked card + Fedow unreachable: silent degrade — FED unavailable, 0 cents, no
    exception bubbles up (the sale must never be blocked).
    """
    from laboutik.views import obtenir_solde_complet_carte

    with (
        mock.patch("laboutik.views.FedowConfig") as MockConfig,
        mock.patch("laboutik.views.FedowAPI") as MockAPI,
    ):
        MockConfig.get_solo.return_value.can_fedow.return_value = True
        MockAPI.return_value.NFCcard.retrieve.side_effect = Exception("Fedow timeout")

        with tenant_context(carte_liee["tenant"]):
            solde = obtenir_solde_complet_carte(carte_liee["carte"])

    assert solde["fed_disponible"] is False
    assert solde["fed_centimes"] == 0
    # Le total se limite aux locaux (ici 0, pas de token créé).
    # / Total is limited to local balances (here 0, no token created).
    assert solde["total_centimes"] == solde["locaux_centimes"]


def test_carte_anonyme_lit_le_fed_de_sa_carte_sur_l_ancien_fedow(carte_anonyme):
    """Carte anonyme (sans user) : son wallet est résolu DEPUIS Fedow (wallet éphémère).
    Sans user, pas de signature RSA : la lecture par la personne
    (get_total_fiducial...) n'est jamais appelée. Le FED est lu sur la FICHE DE LA
    CARTE (`NFCcard.retrieve`, clé du lieu seule) : une carte anonyme peut porter du
    FED, rechargé à l'ancienne borne avec TPE ou par LaBoutik V1. Seul le FED compte :
    un lieu V2 n'émet ni n'accepte de monnaie locale legacy.
    / Anonymous card (no user): no RSA signature, so the per-person read is never
    called. The FED is read on the CARD record (place key only): an anonymous card may
    hold FED (old kiosk with card terminal, LaBoutik V1). Only FED counts.
    """
    from laboutik.views import obtenir_solde_complet_carte

    # uuid Fedow de la carte anonyme (wallet éphémère). On le garde pour le nettoyage.
    # / Fedow uuid of the anonymous card (ephemeral wallet). Kept for cleanup.
    wallet_uuid_fedow = str(uuidlib.uuid4())

    with (
        mock.patch("laboutik.views.FedowConfig"),
        mock.patch("laboutik.views.FedowAPI") as MockAPI,
    ):
        # Fedow connaît la carte : il renvoie un wallet éphémère (carte anonyme).
        # _obtenir_ou_creer_wallet va le miroir en local avec le MÊME uuid.
        # / Fedow knows the card: it returns an ephemeral wallet (anonymous card).
        # _obtenir_ou_creer_wallet mirrors it locally with the SAME uuid.
        MockAPI.return_value.NFCcard.card_tag_id_retrieve.return_value = {
            "wallet_uuid": wallet_uuid_fedow,
            "is_wallet_ephemere": True,
            "origin": {},
        }
        # La fiche de la carte chez l'ancien Fedow : 9,00 € de FED, et 4,00 € de la
        # monnaie d'un autre lieu, qui ne se dépense pas ici.
        # / The card record on the old Fedow: 9.00 € of FED, and 4.00 € of another
        # venue's currency, not spendable here.
        MockAPI.return_value.NFCcard.retrieve.return_value = {
            "first_tag_id": carte_anonyme["carte"].tag_id,
            "is_wallet_ephemere": True,
            "wallet": {
                "uuid": wallet_uuid_fedow,
                # Forme `TokenValidator` (fedow_connect/validators.py), la même que
                # tests/pytest/test_carte_liee_chez_fedow_fed_en_caisse.py.
                # / TokenValidator shape, same as the neighbouring test file.
                "tokens": [
                    jeton_de_l_ancien_fedow("FED", 900),
                    jeton_de_l_ancien_fedow("TLF", 400),
                ],
            },
        }
        # Lecture par la personne : elle ne doit JAMAIS être appelée (pas de user).
        # / Per-person read: must NEVER be called (no user).
        lecture_fed_par_signature = (
            MockAPI.return_value.wallet.get_total_fiducial_and_all_federated_token
        )

        with tenant_context(carte_anonyme["tenant"]):
            solde = obtenir_solde_complet_carte(carte_anonyme["carte"])

    assert solde["fed_disponible"] is True
    assert solde["fed_centimes"] == 900
    lecture_fed_par_signature.assert_not_called()
    MockAPI.return_value.NFCcard.retrieve.assert_called_with(
        carte_anonyme["carte"].tag_id
    )

    # Nettoyage du wallet éphémère miroir créé par la résolution Fedow.
    # / Cleanup of the mirror ephemeral wallet created by the Fedow resolution.
    with tenant_context(carte_anonyme["tenant"]):
        from AuthBillet.models import Wallet
        from fedow_core.models import Token

        carte_anonyme["carte"].refresh_from_db()
        wallet_eph = carte_anonyme["carte"].wallet_ephemere
        if wallet_eph is not None:
            carte_anonyme["carte"].wallet_ephemere = None
            carte_anonyme["carte"].save(update_fields=["wallet_ephemere"])
            Token.objects.filter(wallet=wallet_eph).delete()
            try:
                wallet_eph.delete()
            except Exception:
                pass
        # Filet de sécurité : supprimer un wallet orphelin au même uuid si présent.
        # / Safety net: delete an orphan wallet with the same uuid if present.
        Wallet.objects.filter(uuid=wallet_uuid_fedow).delete()


def test_tenant_sans_place_fedow_pas_de_lecture_fed(carte_liee):
    """Tenant sans place Fedow (can_fedow=False) : on ne lit PAS le FED et on n'instancie
    PAS FedowAPI (sinon l'instanciation déclencherait une création de place — effet de bord).
    / Tenant without a Fedow place (can_fedow=False): FED is not read and FedowAPI is NOT
    instantiated (instantiation would otherwise trigger a place creation side effect).
    """
    from laboutik.views import obtenir_solde_complet_carte

    with (
        mock.patch("laboutik.views.FedowConfig") as MockConfig,
        mock.patch("laboutik.views.FedowAPI") as MockAPI,
    ):
        MockConfig.get_solo.return_value.can_fedow.return_value = False

        with tenant_context(carte_liee["tenant"]):
            solde = obtenir_solde_complet_carte(carte_liee["carte"])

    assert solde["fed_disponible"] is False
    assert solde["fed_centimes"] == 0
    MockAPI.assert_not_called()


def test_total_additionne_locaux_et_fed(carte_liee):
    """Agrégation : total = monnaies locales (fedow_core) + FED réseau.
    Réutilise un asset TLF local existant (echec si la base dev n'en a pas).
    / Aggregation: total = local currencies (fedow_core) + FED network. Reuses an existing
    local TLF asset (fails if the dev DB has none).
    """
    from laboutik.views import obtenir_solde_complet_carte
    from fedow_core.models import Asset, Token

    with tenant_context(carte_liee["tenant"]):
        asset_tlf = (
            Asset.objects.filter(
                tenant_origin=carte_liee["tenant"], category=Asset.TLF, active=True
            )
            .order_by("name")
            .first()
        )
        if asset_tlf is None:
            pytest.fail(
                "Pas d'asset TLF local en base dev — lancer create_test_pos_data --schema=lespass"
            )
        # 1000 centimes (10,00 €) de monnaie locale sur le wallet de la carte.
        # / 1000 cents (€10.00) of local currency on the card's wallet.
        Token.objects.update_or_create(
            wallet=carte_liee["wallet"], asset=asset_tlf, defaults={"value": 1000}
        )

    with (
        mock.patch("laboutik.views.FedowConfig") as MockConfig,
        mock.patch("laboutik.views.FedowAPI") as MockAPI,
    ):
        MockConfig.get_solo.return_value.can_fedow.return_value = True
        MockAPI.return_value.NFCcard.retrieve.return_value = (
            fiche_de_la_carte_avec_du_fed(carte_liee["carte"], 500)
        )

        with tenant_context(carte_liee["tenant"]):
            solde = obtenir_solde_complet_carte(carte_liee["carte"])

    assert solde["locaux_centimes"] == 1000
    assert solde["fed_centimes"] == 500
    assert solde["total_centimes"] == 1500
    assert solde["fed_disponible"] is True
