"""
E2E — Je perds ma carte, mon argent me suit (vraie recharge FED, vrai Fedow, vrais clics).
/ E2E — I lose my card, my money follows me (real FED top-up, real Fedow, real clicks).

LOCALISATION : tests/e2e/test_carte_perdue_recharge_fed.py

LE SCENARIO :
1. Un adherent tout neuf recharge son portefeuille en monnaie federee (FED) par carte
   bancaire : vrai Stripe Checkout, credit par le webhook de Fedow.
2. Il a une carte A, liee a son portefeuille chez Fedow ET dans Lespass.
3. La carte A est declaree perdue en CLIQUANT le bouton, une variante par bouton :
   - `mon_compte` : l'adherent, depuis « Mon compte » → « Ma carte » ;
   - `admin` : un admin du lieu, depuis la fiche de l'adherent.
   Le clic est un DOUBLE clic : une seule requete doit partir (`hx-disabled-elt`).
4. La carte A ne vaut plus rien pour lui : anonyme chez Fedow et dans Lespass, et la
   caisse V2 n'ouvre plus son portefeuille avec elle.
5. Il lie une carte B (Fedow puis Lespass, comme le parcours /qr).
6. Son solde FED est intact, la carte B ouvre son portefeuille, et la page « Solde » de
   « Mon compte » s'affiche (le tableau des monnaies repond).
Les etapes 2, 4 et 5 se font en base (`django_shell`) : ce qui est teste dans le
navigateur, c'est la recharge, le clic sur le bouton et l'affichage du solde.
/ Steps 2, 4, 5 run in the DB; the browser covers the top-up, the click and the balance page.

PREREQUIS : serveur de dev, Fedow de dev, et les deux `stripe listen` (Lespass et Fedow)
dans byobu. Sans eux, le webhook ne credite jamais : le test echoue (marqueur stripe_listen).
Chaque passage laisse chez le Fedow de dev un adherent, deux cartes et 3 € de FED de test.

Lancement / Run :
    make e2e ARGS="tests/e2e/test_carte_perdue_recharge_fed.py -v"
"""
import uuid as uuid_module

import pytest

from tests.e2e.test_parcours_fedow_reel import (
    _creer_une_carte_neuve_rattachee_des_deux_cotes,
    _lire_json_marque,
    _recharger_en_monnaie_federee_par_carte_bancaire,
    _solde_federe,
    _verifier_que_la_recharge_federee_est_creditee,
)


# Familles de tests : `make e2e-visible <famille>` (liste : make help, ou pytest.ini).
# / Test families: `make e2e-visible <family>` (list: make help, or pytest.ini).
pytestmark = [pytest.mark.monnaie]


def _etat_de_la_carte(django_shell, email, numero_carte):
    """
    Ce que les deux registres et la caisse V2 disent de la carte, pour cet adherent.
    / What both registries and the V2 POS say about the card, for this member.

    :return: dict {'anonyme_chez_fedow', 'wallet_fedow_de_la_carte', 'porteur_local_est_lui',
                   'caisse_v2_ouvre_son_portefeuille', 'wallet_de_l_adherent'}
    """
    sortie = django_shell(
        "import json\n"
        "from AuthBillet.models import TibilletUser\n"
        "from QrcodeCashless.models import CarteCashless\n"
        "from fedow_connect.fedow_api import FedowAPI\n"
        "from laboutik.views import _obtenir_ou_creer_wallet\n"
        f"user = TibilletUser.objects.get(email='{email}')\n"
        f"carte = CarteCashless.objects.get(number='{numero_carte}')\n"
        f"chez_fedow = FedowAPI().NFCcard.card_number_retrieve('{numero_carte}')\n"
        "wallet_ouvert = _obtenir_ou_creer_wallet(carte)\n"
        "print('ETAT_JSON=' + json.dumps({\n"
        "    'anonyme_chez_fedow': bool(chez_fedow and chez_fedow.get('is_wallet_ephemere')),\n"
        "    'wallet_fedow_de_la_carte': str(chez_fedow.get('wallet_uuid')) if chez_fedow else None,\n"
        "    'porteur_local_est_lui': carte.user_id == user.pk,\n"
        "    'caisse_v2_ouvre_son_portefeuille': str(wallet_ouvert.uuid) == str(user.wallet.uuid),\n"
        "    'wallet_de_l_adherent': str(user.wallet.uuid),\n"
        "}))"
    )
    return _lire_json_marque(sortie, 'ETAT_JSON=')


def _lier_une_carte_neuve_comme_le_parcours_qr(django_shell, email):
    """
    Une carte B neuve, connue de Fedow et de Lespass, liee comme le fait /qr : chez Fedow
    (`linkwallet_cardqrcode`) puis dans Lespass (`CarteService.lier_a_user`, qui refuse
    si l'adherent a encore une autre carte locale).
    / A fresh card B linked like /qr: Fedow, then Lespass (lier_a_user).

    :return: le numero imprime de la carte B
    """
    numero_carte = uuid_module.uuid4().hex[:8].upper()
    uuid_du_qrcode = uuid_module.uuid4()
    sortie = django_shell(
        "import json\n"
        "from AuthBillet.models import TibilletUser\n"
        "from QrcodeCashless.models import CarteCashless\n"
        "from fedow_connect.fedow_api import FedowAPI\n"
        "from fedow_core.services import CarteService\n"
        f"user = TibilletUser.objects.get(email='{email}')\n"
        "api = FedowAPI()\n"
        "api.NFCcard.create([{\n"
        f"    'first_tag_id': '{numero_carte}',\n"
        f"    'qrcode_uuid': '{uuid_du_qrcode}',\n"
        f"    'number_printed': '{numero_carte}',\n"
        "}])\n"
        "CarteCashless.objects.create(\n"
        f"    tag_id='{numero_carte}', number='{numero_carte}', uuid='{uuid_du_qrcode}')\n"
        f"api.NFCcard.linkwallet_cardqrcode(user=user, qrcode_uuid='{uuid_du_qrcode}')\n"
        "erreur = None\n"
        "try:\n"
        f"    CarteService.lier_a_user(qrcode_uuid='{uuid_du_qrcode}', user=user)\n"
        "except Exception as e:\n"
        "    erreur = f'{type(e).__name__} {e}'\n"
        "print('LIAISON_JSON=' + json.dumps({'erreur': erreur}))"
    )
    liaison = _lire_json_marque(sortie, 'LIAISON_JSON=')
    assert liaison['erreur'] is None, (
        f"La nouvelle carte {numero_carte} n'a pas pu etre liee dans Lespass : {liaison['erreur']}"
    )
    return numero_carte


def _double_clic_sur_le_bouton_carte_perdue(page, bouton, morceau_d_adresse):
    """
    Double clic sur le bouton « carte perdue » : UNE seule requete doit partir
    (`hx-disabled-elt="this"` desactive le bouton pendant la requete).
    / Double click: ONE request only must leave.
    """
    requetes_parties = []
    page.on("request", lambda requete: requetes_parties.append(requete.url)
            if morceau_d_adresse in requete.url else None)

    bouton.wait_for(state="visible", timeout=20_000)
    with page.expect_response(lambda reponse: morceau_d_adresse in reponse.url) as reponse_du_clic:
        bouton.dblclick()
    assert reponse_du_clic.value.status == 200, (
        f"Le bouton « carte perdue » a repondu {reponse_du_clic.value.status}."
    )
    page.wait_for_load_state("networkidle")
    assert len(requetes_parties) == 1, (
        f"Un double clic a envoye {len(requetes_parties)} requetes « carte perdue » au lieu d'une."
    )


def _declarer_perdue_depuis_mon_compte(page, login_as, login_as_admin, email, numero_carte):
    """L'adherent clique « carte perdue » dans « Mon compte » → « Ma carte ». / Holder clicks."""
    login_as(page, email)
    page.goto('/my_account/card/')
    morceau_d_adresse = f"/my_account/{numero_carte}/lost_my_card/"
    bouton = page.locator(f'[hx-get="{morceau_d_adresse}"]').first
    _double_clic_sur_le_bouton_carte_perdue(page, bouton, morceau_d_adresse)


def _declarer_perdue_depuis_l_admin(page, login_as, login_as_admin, email, numero_carte, uuid_adherent):
    """Un admin du lieu clique « carte perdue » sur la fiche de l'adherent. / Admin clicks."""
    login_as_admin(page)
    page.goto(f'/admin/AuthBillet/humanuser/{uuid_adherent}/change/')
    page.locator(f'[hx-get="/my_account/{uuid_adherent}/admin_my_cards/"]').click()
    morceau_d_adresse = f"/my_account/{uuid_adherent}:{numero_carte}/admin_lost_my_card/"
    bouton = page.locator(f'[hx-get="{morceau_d_adresse}"]').first
    _double_clic_sur_le_bouton_carte_perdue(page, bouton, morceau_d_adresse)


def _uuid_de_l_adherent(django_shell, email):
    sortie = django_shell(
        "import json\n"
        "from AuthBillet.models import TibilletUser\n"
        f"print('UUID_JSON=' + json.dumps(str(TibilletUser.objects.get(email='{email}').pk)))"
    )
    return _lire_json_marque(sortie, 'UUID_JSON=')


@pytest.mark.stripe_listen
@pytest.mark.parametrize("bouton_utilise", ["mon_compte", "admin"])
def test_carte_perdue_la_recharge_fed_suit_l_adherent_sur_sa_nouvelle_carte(
    page, login_as, login_as_admin, django_shell, fill_stripe_card, soumettre_paiement_stripe,
    bouton_utilise,
):
    """
    Recharge FED par carte bancaire, carte A perdue par un clic, carte B liee : le solde
    FED est intact et suit l'adherent ; la carte A n'ouvre plus son portefeuille.
    / FED top-up, card A lost by a click, card B linked: the FED balance follows the member.
    """
    # --- 1. Vraie recharge FED / Real FED top-up ---
    recharge = _recharger_en_monnaie_federee_par_carte_bancaire(
        page, login_as, django_shell, fill_stripe_card, soumettre_paiement_stripe,
    )
    _verifier_que_la_recharge_federee_est_creditee(recharge)
    email = recharge['email']
    solde_de_reference = recharge['solde_credite']

    # --- 2. La carte A, liee des deux cotes / Card A, linked on both sides ---
    carte_a = _creer_une_carte_neuve_rattachee_des_deux_cotes(django_shell, email)
    numero_carte_a = carte_a['tag_id']
    etat_avant = _etat_de_la_carte(django_shell, email, numero_carte_a)
    assert etat_avant['porteur_local_est_lui'] and etat_avant['caisse_v2_ouvre_son_portefeuille']

    # --- 3. Perte declaree par un double clic / Loss reported by a double click ---
    if bouton_utilise == "mon_compte":
        _declarer_perdue_depuis_mon_compte(page, login_as, login_as_admin, email, numero_carte_a)
    else:
        uuid_adherent = _uuid_de_l_adherent(django_shell, email)
        _declarer_perdue_depuis_l_admin(
            page, login_as, login_as_admin, email, numero_carte_a, uuid_adherent,
        )

    # --- 4. La carte A ne vaut plus rien pour lui / Card A is worthless to him ---
    etat_apres = _etat_de_la_carte(django_shell, email, numero_carte_a)
    assert etat_apres['anonyme_chez_fedow'], f"[{bouton_utilise}] Fedow rattache encore la carte A."
    assert not etat_apres['porteur_local_est_lui'], (
        f"[{bouton_utilise}] La carte A est encore liee a l'adherent dans Lespass."
    )
    assert not etat_apres['caisse_v2_ouvre_son_portefeuille'], (
        f"[{bouton_utilise}] Qui trouve la carte A depense le portefeuille de l'adherent."
    )

    # --- 5. Il lie une carte B / He links card B ---
    numero_carte_b = _lier_une_carte_neuve_comme_le_parcours_qr(django_shell, email)

    # --- 6. Son argent l'a suivi / His money followed him ---
    assert _solde_federe(django_shell, email) == solde_de_reference, (
        f"[{bouton_utilise}] Le solde FED a change avec la perte de la carte."
    )
    etat_de_b = _etat_de_la_carte(django_shell, email, numero_carte_b)
    assert etat_de_b['wallet_fedow_de_la_carte'] == etat_de_b['wallet_de_l_adherent']
    assert etat_de_b['porteur_local_est_lui'] and etat_de_b['caisse_v2_ouvre_son_portefeuille']

    # La page « Solde » s'affiche, avec son tableau des monnaies.
    # / The balance page shows, with its currency table.
    login_as(page, email)
    with page.expect_response(lambda reponse: "/my_account/tokens_table/" in reponse.url) as tableau:
        page.goto('/my_account/balance/')
    assert tableau.value.status == 200, (
        f"Le tableau des monnaies de « Mon compte » repond {tableau.value.status}."
    )
