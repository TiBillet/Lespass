"""
E2E — Je perds ma carte, mon argent me suit (vraie recharge FED, vrai Fedow, vrais clics).
/ E2E — I lose my card, my money follows me (real FED top-up, real Fedow, real clicks).

LOCALISATION : tests/e2e/test_carte_perdue_recharge_fed.py

LE SCENARIO :
1. Un adherent tout neuf recharge son portefeuille en monnaie federee (FED) par carte
   bancaire : vrai Stripe Checkout, credit par le webhook de Fedow.
2. Il a une carte A, liee a son portefeuille chez Fedow ET dans Lespass, et des jetons
   locaux de `lespass` (Fedow V2) : monnaie locale, cadeau, temps, fidelite. Temoin :
   CHECK CARTE a la caisse V2, la fiche montre chaque monnaie locale a sa valeur, et le FED.
3. La carte A est declaree perdue en CLIQUANT le bouton, une variante par bouton :
   - `mon_compte` : l'adherent, depuis « Mon compte » → « Ma carte » (fenetre de
     confirmation SweetAlert) ;
   - `admin` : un admin du lieu, depuis la fiche de l'adherent.
   Le clic est un DOUBLE clic : une seule requete doit partir (`hx-disabled-elt`).
4. La carte A ne vaut plus rien pour lui : anonyme chez Fedow et dans Lespass, la caisse
   V2 n'ouvre plus son portefeuille. CHECK CARTE : carte anonyme, aucune pastille, pas de
   FED, total 0.
5. Une AUTRE personne lie la carte A par son QR code (vrai parcours /qr, dans le
   navigateur). Elle n'herite de rien : « Mon espace » affiche 0 €, sans cadeau ; aucun
   jeton chez l'ancien Fedow ni dans le Fedow V2. CHECK CARTE : la carte porte la
   nouvelle personne, aucune pastille, pas de FED, total 0.
6. L'adherent lie une carte B (Fedow puis Lespass, comme le parcours /qr).
7. Tous ses jetons l'ont suivi (FED et locaux), la carte B ouvre son portefeuille.
   CHECK CARTE sur la carte B : chaque monnaie locale a sa valeur, et le FED (pastille
   « TiBillet »). La page « Solde » de « Mon compte » s'affiche.
Joue dans le navigateur : la recharge, les quatre CHECK CARTE a la caisse V2, le clic sur
le bouton, la liaison de la carte A par l'autre personne et les pages « Mon espace » et
« Solde ». Le reste se lit en base (`django_shell`).
/ Steps 2, 4, 6, 7 are read in the DB; the browser covers the top-up, the click, the
other person's QR link and the account pages.

PREREQUIS : serveur de dev, Fedow de dev, les donnees POS de test (carte primaire
A49E8E2A), et les deux `stripe listen` (Lespass et Fedow) dans byobu. Sans eux, le webhook ne credite jamais : le test echoue (marqueur stripe_listen).
Chaque passage laisse chez le Fedow de dev deux personnes, deux cartes et 3 € de FED de
test, et dans `lespass` des jetons locaux crees pour l'adherent (sans vente en face).

Lancement / Run :
    make e2e ARGS="tests/e2e/test_carte_perdue_recharge_fed.py -v"
"""
import re
import uuid as uuid_module

import pytest
from playwright.sync_api import expect

from tests.e2e.conftest import BASE_URL
from tests.e2e.test_carte_liee_par_qrcode_fed_en_caisse import (
    _lier_la_carte_par_son_qrcode,
    _scanner_la_carte,
)
# Le check carte ouvre la vraie caisse V2 : un point de vente ouvert a la carte primaire
# du caissier, declaree a l'ancien Fedow (sinon l'ouverture retire la carte primaire).
# / The card check opens the real V2 POS: a POS open to the cashier's primary card,
# declared to the old Fedow.
from tests.e2e.test_parcours_fedow_reel import (  # noqa: F401
    NOM_DU_COMPTOIR_DE_L_ANCIEN_FEDOW,
    carte_primaire_declaree_a_l_ancien_fedow,
    comptoir_de_l_ancien_fedow,
)
from tests.e2e.test_parcours_fedow_reel import (
    _creer_une_carte_neuve_rattachee_des_deux_cotes,
    _lire_json_marque,
    _recharger_en_monnaie_federee_par_carte_bancaire,
    _solde_federe,
    _verifier_que_la_recharge_federee_est_creditee,
)


# Familles de tests : `make e2e-visible <famille>` (liste : make help, ou pytest.ini).
# / Test families: `make e2e-visible <family>` (list: make help, or pytest.ini).
pytestmark = [
    pytest.mark.monnaie,
    pytest.mark.site,
    pytest.mark.usefixtures(
        "carte_primaire_declaree_a_l_ancien_fedow", "comptoir_de_l_ancien_fedow",
    ),
]


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


# Les jetons locaux (Fedow V2 de `lespass`) poses sur le portefeuille de l'adherent, en
# centimes ou en unites. Des valeurs differentes : un jeton qui passerait d'un portefeuille
# a l'autre se reconnait a sa valeur.
# / Local tokens put on the member's wallet; distinct values, recognisable if they move.
JETONS_LOCAUX_DE_L_ADHERENT = {
    "TLF": 500,  # monnaie locale (euro) / local currency
    "TNF": 300,  # cadeau / gift
    "TIM": 200,  # temps / time
    "FID": 100,  # fidelite / loyalty
}


def _crediter_les_jetons_locaux(django_shell, email):
    """
    Credite l'adherent d'un jeton de chaque monnaie locale active de `lespass` (Fedow V2) :
    monnaie locale, cadeau, temps, fidelite. Le FED, lui, vient de la vraie recharge.
    / Credits one token of each active local currency of `lespass` (V2 engine).

    :return: dict {categorie: nom de la monnaie}, pour lire les pastilles du check carte
    """
    sortie = django_shell(
        "import json\n"
        "from django.db import connection, transaction\n"
        "from AuthBillet.models import TibilletUser\n"
        "from fedow_core.models import Asset\n"
        "from fedow_core.services import WalletService\n"
        f"user = TibilletUser.objects.get(email='{email}')\n"
        f"montants = {JETONS_LOCAUX_DE_L_ADHERENT!r}\n"
        "manquantes = []\n"
        "noms = {}\n"
        "with transaction.atomic():\n"
        "    for categorie, montant in montants.items():\n"
        "        asset = Asset.objects.filter(\n"
        "            tenant_origin=connection.tenant, category=categorie,\n"
        "            active=True, archive=False).exclude(name__startswith='[').first()\n"
        "        if asset is None:\n"
        "            manquantes.append(categorie)\n"
        "            continue\n"
        "        WalletService.crediter(user.wallet, asset, montant)\n"
        "        noms[categorie] = asset.name\n"
        "print('CREDIT_JSON=' + json.dumps({'manquantes': manquantes, 'noms': noms}))"
    )
    credit = _lire_json_marque(sortie, 'CREDIT_JSON=')
    if credit['manquantes']:
        pytest.fail(
            f"`lespass` n'a pas de monnaie active de categorie {credit['manquantes']} : "
            "reseeder (docker exec lespass_django poetry run python manage.py "
            "create_test_pos_data)."
        )
    return credit['noms']


def _jetons_locaux(django_shell, email):
    """
    Les jetons locaux (Fedow V2) du portefeuille d'une personne, par categorie.
    / A person's local tokens (V2 engine), by category.

    :return: dict {categorie: valeur}, sans les jetons a 0
    """
    sortie = django_shell(
        "import json\n"
        "from AuthBillet.models import TibilletUser\n"
        "from fedow_core.services import WalletService\n"
        f"user = TibilletUser.objects.get(email='{email}')\n"
        "jetons = {}\n"
        "if user.wallet is not None:\n"
        "    for token in WalletService.obtenir_tous_les_soldes(user.wallet):\n"
        "        if token.value:\n"
        "            categorie = token.asset.category\n"
        "            jetons[categorie] = jetons.get(categorie, 0) + token.value\n"
        "print('JETONS_JSON=' + json.dumps(jetons))"
    )
    return _lire_json_marque(sortie, 'JETONS_JSON=')


def _ce_que_la_caisse_voit_sur_la_carte(django_shell, numero_carte):
    """
    Ce que le check carte de la caisse V2 lit sur la carte : jetons locaux et FED.
    / What the V2 POS card check reads on the card: local tokens and FED.

    :return: dict {'jetons_locaux': {categorie: valeur}, 'fed_centimes': int}
    """
    sortie = django_shell(
        "import json\n"
        "from QrcodeCashless.models import CarteCashless\n"
        "from laboutik.views import obtenir_solde_complet_carte\n"
        f"carte = CarteCashless.objects.get(number='{numero_carte}')\n"
        "solde = obtenir_solde_complet_carte(carte)\n"
        "jetons = {}\n"
        "for jeton in solde['tokens_locaux']:\n"
        "    jetons[jeton['asset_category']] = jeton['value_euros']\n"
        "print('CAISSE_JSON=' + json.dumps({\n"
        "    'jetons_locaux': jetons, 'fed_centimes': solde['fed_centimes']}))"
    )
    return _lire_json_marque(sortie, 'CAISSE_JSON=')


def _qrcode_de_la_carte(django_shell, numero_carte):
    """L'uuid du QR code imprime sur la carte. / The card's printed QR code uuid."""
    sortie = django_shell(
        "import json\n"
        "from QrcodeCashless.models import CarteCashless\n"
        f"carte = CarteCashless.objects.get(number='{numero_carte}')\n"
        "print('QRCODE_JSON=' + json.dumps(str(carte.uuid)))"
    )
    return _lire_json_marque(sortie, 'QRCODE_JSON=')


def _jetons_chez_l_ancien_fedow(django_shell, email):
    """
    Tous les jetons du portefeuille d'une personne chez l'ancien Fedow (FED et monnaies
    legacy), relus SANS cache, par categorie.
    / All of a person's tokens on the old Fedow, read WITHOUT cache, by category.

    :return: dict {categorie: valeur}, sans les jetons a 0
    """
    sortie = django_shell(
        "import json\n"
        "from AuthBillet.models import TibilletUser\n"
        "from fedow_connect.fedow_api import FedowAPI\n"
        f"user = TibilletUser.objects.get(email='{email}')\n"
        "portefeuille = FedowAPI().wallet.retrieve_by_signature(user).validated_data\n"
        "jetons = {}\n"
        "for jeton in portefeuille['tokens']:\n"
        "    if jeton['value']:\n"
        "        categorie = jeton['asset_category']\n"
        "        jetons[categorie] = jetons.get(categorie, 0) + int(jeton['value'])\n"
        "print('JETONS_LEGACY_JSON=' + json.dumps(jetons))"
    )
    return _lire_json_marque(sortie, 'JETONS_LEGACY_JSON=')


def _motif_du_montant(unites):
    """Le motif d'un montant affiche avec deux decimales (« 5,00 » ou « 5.00 »), sans
    chiffre juste avant : « 15,00 » ne vaut pas « 5,00 ».
    / Pattern of an amount shown with two decimals, no digit just before it."""
    return re.compile(rf"(?<!\d){unites // 100}[,.]{unites % 100:02d}")


def _check_carte_a_la_caisse(page, pos_page, numero_carte):
    """
    Le caissier ouvre la caisse V2, touche « CHECK CARTE » et scanne la carte. Rend ce
    que la fiche affiche.
    / The cashier opens the V2 POS, taps CARD CHECK, scans the card. Returns the card sheet.

    :return: dict {'erreur', 'anonyme', 'total', 'pastilles': {nom: valeur affichee},
                   'fed', 'fed_indisponible'}
    """
    pos_page(page, NOM_DU_COMPTOIR_DE_L_ANCIEN_FEDOW)
    page.locator('[data-testid="addition-check-carte"]').click()
    _scanner_la_carte(page, numero_carte)

    fiche = page.locator('[data-testid="retour-carte"]')
    expect(fiche).to_be_visible()

    pastilles = {}
    for pastille in fiche.locator('li[data-testid^="retour-carte-solde-"]').all():
        if pastille.get_attribute("data-testid") == "retour-carte-solde-fed":
            continue
        nom = pastille.locator(".card-pastille-nom").inner_text().strip()
        pastilles[nom] = pastille.locator("b").inner_text().strip()

    erreur = fiche.locator('[data-testid="retour-carte-erreur"]')
    total = fiche.locator('[data-testid="retour-carte-soldes"]')
    fed = fiche.locator('[data-testid="retour-carte-solde-fed"]')
    return {
        "erreur": erreur.inner_text() if erreur.count() > 0 else None,
        "anonyme": fiche.locator('[data-testid="retour-carte-anonyme"]').count() > 0,
        "total": total.inner_text().strip() if total.count() > 0 else None,
        "pastilles": pastilles,
        "fed": fed.inner_text().strip() if fed.count() > 0 else None,
        "fed_indisponible": (
            fiche.locator('[data-testid="retour-carte-fed-indisponible"]').count() > 0
        ),
    }


def _verifier_la_fiche_de_l_adherent(fiche, noms_des_monnaies_locales, fed_attendu, moment):
    """
    La fiche du check carte montre l'adherent : une pastille par monnaie locale, a sa
    valeur, et la pastille FED (« TiBillet ») au montant attendu.
    / The card sheet shows the member: one pill per local currency, and the FED pill.
    """
    assert fiche["erreur"] is None and not fiche["anonyme"], f"{moment} : {fiche}"
    for categorie, montant in JETONS_LOCAUX_DE_L_ADHERENT.items():
        nom_de_la_monnaie = noms_des_monnaies_locales[categorie]
        valeur_affichee = fiche["pastilles"].get(nom_de_la_monnaie)
        assert valeur_affichee is not None, (
            f"{moment} : pas de pastille « {nom_de_la_monnaie} » ({categorie}) : {fiche}"
        )
        assert _motif_du_montant(montant).search(valeur_affichee), (
            f"{moment} : « {nom_de_la_monnaie} » affiche {valeur_affichee}, attendu "
            f"{montant / 100:.2f} : {fiche}"
        )
    assert fiche["fed"] and _motif_du_montant(fed_attendu).search(fiche["fed"]), (
        f"{moment} : le FED n'affiche pas {fed_attendu} : {fiche}"
    )
    assert fiche["fed"].startswith("TiBillet"), (
        f"{moment} : la pastille FED ne s'appelle pas « TiBillet » : {fiche}"
    )


def _verifier_une_fiche_a_zero(fiche, moment):
    """
    La fiche du check carte ne montre aucun jeton : ni pastille, ni FED, total a 0.
    Le FED doit etre LU (pas « indisponible ») : sinon un zero ne prouverait rien.
    / The card sheet shows no token, no FED, a zero total; FED must have been read.
    """
    assert fiche["erreur"] is None, f"{moment} : la fiche affiche une erreur : {fiche}"
    assert not fiche["fed_indisponible"], (
        f"{moment} : l'ancien Fedow n'a pas repondu, le zero du FED ne prouve rien : {fiche}"
    )
    assert fiche["pastilles"] == {}, f"{moment} : la fiche montre des jetons : {fiche}"
    assert fiche["fed"] is None, f"{moment} : la fiche montre du FED : {fiche}"
    assert _motif_du_montant(0).search(fiche["total"] or ""), (
        f"{moment} : le total de la fiche n'est pas 0 : {fiche}"
    )


def _double_clic_sur_le_bouton_carte_perdue(
    page, bouton, morceau_d_adresse, confirmation_sweetalert=False,
):
    """
    Double clic sur le bouton « carte perdue » : UNE seule requete doit partir
    (`hx-disabled-elt="this"` desactive le bouton pendant la requete).

    Dans « Mon espace » (skin V2), le bouton porte `hx-confirm` : le shell ouvre une
    fenetre SweetAlert, et la requete ne part qu'apres « Oui ». Le test clique donc
    sur « Oui », une fois (`confirmation_sweetalert=True`). Le bouton de l'admin n'a
    pas de confirmation.
    / Double click: ONE request only must leave. In "My space" (V2) the button opens
    a SweetAlert confirmation: the request leaves only after "Yes", clicked once.
    """
    requetes_parties = []
    page.on("request", lambda requete: requetes_parties.append(requete.url)
            if morceau_d_adresse in requete.url else None)

    bouton.wait_for(state="visible", timeout=20_000)
    with page.expect_response(lambda reponse: morceau_d_adresse in reponse.url) as reponse_du_clic:
        bouton.dblclick()
        if confirmation_sweetalert:
            bouton_oui = page.locator(".swal2-popup .swal2-confirm")
            bouton_oui.wait_for(state="visible", timeout=10_000)
            bouton_oui.click()
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
    _double_clic_sur_le_bouton_carte_perdue(
        page, bouton, morceau_d_adresse, confirmation_sweetalert=True,
    )


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
def test_carte_perdue_les_jetons_suivent_l_adherent_et_jamais_qui_reprend_la_carte(
    page, browser, login_as, login_as_admin, pos_page, django_shell, fill_stripe_card,
    soumettre_paiement_stripe, bouton_utilise,
):
    """
    Un adherent a des jetons de chaque type (FED, monnaie locale, cadeau, temps,
    fidelite). Sa carte A est declaree perdue par un clic, puis une AUTRE personne lie
    la carte A par son QR code : elle n'herite de rien. L'adherent lie une carte B : il
    retrouve tous ses jetons.
    / A member holds every kind of token. Card A is reported lost, then ANOTHER person
    links card A by its QR code and inherits nothing. Card B gives the member everything.
    """
    # --- 1. Vraie recharge FED / Real FED top-up ---
    recharge = _recharger_en_monnaie_federee_par_carte_bancaire(
        page, login_as, django_shell, fill_stripe_card, soumettre_paiement_stripe,
    )
    _verifier_que_la_recharge_federee_est_creditee(recharge)
    email = recharge['email']
    solde_de_reference = recharge['solde_credite']

    # --- 2. La carte A, liee des deux cotes, et les jetons locaux / Card A and local tokens ---
    carte_a = _creer_une_carte_neuve_rattachee_des_deux_cotes(django_shell, email)
    numero_carte_a = carte_a['tag_id']
    noms_des_monnaies_locales = _crediter_les_jetons_locaux(django_shell, email)
    jetons_locaux_de_reference = _jetons_locaux(django_shell, email)
    assert jetons_locaux_de_reference == JETONS_LOCAUX_DE_L_ADHERENT, (
        f"Jetons locaux de l'adherent neuf : {jetons_locaux_de_reference}, attendu "
        f"{JETONS_LOCAUX_DE_L_ADHERENT}."
    )
    etat_avant = _etat_de_la_carte(django_shell, email, numero_carte_a)
    assert etat_avant['porteur_local_est_lui'] and etat_avant['caisse_v2_ouvre_son_portefeuille']

    # Temoin : AVANT la perte, la caisse voit bien tous ses jetons sur la carte A. Sans ce
    # temoin, « la caisse ne voit rien » apres la perte ne prouverait rien.
    # / Control: BEFORE the loss, the POS sees all the tokens on card A.
    caisse_avant = _ce_que_la_caisse_voit_sur_la_carte(django_shell, numero_carte_a)
    assert caisse_avant['fed_centimes'] == solde_de_reference, caisse_avant
    assert set(caisse_avant['jetons_locaux']) == set(JETONS_LOCAUX_DE_L_ADHERENT), caisse_avant

    # CHECK CARTE a la caisse V2 : une pastille par monnaie locale, a sa valeur, et le FED.
    # / CARD CHECK at the V2 POS: one pill per local currency, at its value, and the FED.
    fiche_avant = _check_carte_a_la_caisse(page, pos_page, numero_carte_a)
    _verifier_la_fiche_de_l_adherent(
        fiche_avant, noms_des_monnaies_locales, solde_de_reference,
        "Check carte avant la perte",
    )

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
    caisse_apres_la_perte = _ce_que_la_caisse_voit_sur_la_carte(django_shell, numero_carte_a)
    assert caisse_apres_la_perte == {'jetons_locaux': {}, 'fed_centimes': 0}, (
        f"[{bouton_utilise}] Le check carte de la carte A perdue montre encore des jetons : "
        f"{caisse_apres_la_perte}"
    )
    # CHECK CARTE a la caisse V2 : la carte perdue est anonyme et vide.
    # / CARD CHECK at the V2 POS: the lost card is anonymous and empty.
    fiche_apres_la_perte = _check_carte_a_la_caisse(page, pos_page, numero_carte_a)
    assert fiche_apres_la_perte["anonyme"], (
        f"[{bouton_utilise}] Check carte apres la perte : la carte A n'est pas anonyme : "
        f"{fiche_apres_la_perte}"
    )
    _verifier_une_fiche_a_zero(
        fiche_apres_la_perte, f"[{bouton_utilise}] Check carte apres la perte"
    )

    # --- 5. Une AUTRE personne lie la carte A par son QR code (navigateur) ---
    #     / ANOTHER person links card A by its QR code (browser) ---
    email_de_qui_trouve = f"e2e-trouve-{uuid_module.uuid4().hex[:8]}@tibillet.test"
    contexte_de_qui_trouve = browser.new_context(base_url=BASE_URL, ignore_https_errors=True)
    try:
        page_de_qui_trouve = contexte_de_qui_trouve.new_page()
        _lier_la_carte_par_son_qrcode(
            page_de_qui_trouve, _qrcode_de_la_carte(django_shell, numero_carte_a),
            email_de_qui_trouve,
        )
        # Son « Mon espace » : la carte A, et un solde nul, sans cadeau.
        # / Their "My space": card A, a zero balance, no gift.
        page_de_qui_trouve.goto("/my_account/")
        expect(page_de_qui_trouve.get_by_test_id("compte-carte")).to_contain_text(numero_carte_a)
        expect(page_de_qui_trouve.get_by_test_id("compte-solde")).to_have_text(
            re.compile(r"^\s*0([.,]00)?\s*€\s*$")
        )
        assert page_de_qui_trouve.get_by_test_id("compte-solde-cadeau").count() == 0, (
            f"[{bouton_utilise}] Qui reprend la carte A voit un solde cadeau."
        )
    finally:
        contexte_de_qui_trouve.close()

    etat_chez_qui_trouve = _etat_de_la_carte(django_shell, email_de_qui_trouve, numero_carte_a)
    assert etat_chez_qui_trouve['porteur_local_est_lui'], etat_chez_qui_trouve
    assert etat_chez_qui_trouve['wallet_fedow_de_la_carte'] == (
        etat_chez_qui_trouve['wallet_de_l_adherent']
    ), etat_chez_qui_trouve
    assert _jetons_locaux(django_shell, email_de_qui_trouve) == {}, (
        f"[{bouton_utilise}] Qui reprend la carte A herite de jetons locaux de l'adherent."
    )
    assert _jetons_chez_l_ancien_fedow(django_shell, email_de_qui_trouve) == {}, (
        f"[{bouton_utilise}] Qui reprend la carte A herite de jetons chez l'ancien Fedow."
    )
    caisse_chez_qui_trouve = _ce_que_la_caisse_voit_sur_la_carte(django_shell, numero_carte_a)
    assert caisse_chez_qui_trouve == {'jetons_locaux': {}, 'fed_centimes': 0}, (
        f"[{bouton_utilise}] La caisse montre des jetons sur la carte A reprise : "
        f"{caisse_chez_qui_trouve}"
    )
    # CHECK CARTE a la caisse V2 : la carte A porte la nouvelle personne, et rien d'autre.
    # / CARD CHECK at the V2 POS: card A carries the new person, and nothing else.
    fiche_chez_qui_trouve = _check_carte_a_la_caisse(page, pos_page, numero_carte_a)
    assert not fiche_chez_qui_trouve["anonyme"], (
        f"[{bouton_utilise}] Check carte apres la reprise : la carte A est encore anonyme : "
        f"{fiche_chez_qui_trouve}"
    )
    _verifier_une_fiche_a_zero(
        fiche_chez_qui_trouve, f"[{bouton_utilise}] Check carte apres la reprise"
    )

    # --- 6. L'adherent lie une carte B / The member links card B ---
    numero_carte_b = _lier_une_carte_neuve_comme_le_parcours_qr(django_shell, email)

    # --- 7. Tous ses jetons l'ont suivi / All the member's tokens followed ---
    assert _solde_federe(django_shell, email) == solde_de_reference, (
        f"[{bouton_utilise}] Le solde FED a change avec la perte de la carte."
    )
    assert _jetons_locaux(django_shell, email) == jetons_locaux_de_reference, (
        f"[{bouton_utilise}] Les jetons locaux ont change avec la perte de la carte."
    )
    etat_de_b = _etat_de_la_carte(django_shell, email, numero_carte_b)
    assert etat_de_b['wallet_fedow_de_la_carte'] == etat_de_b['wallet_de_l_adherent']
    assert etat_de_b['porteur_local_est_lui'] and etat_de_b['caisse_v2_ouvre_son_portefeuille']
    caisse_sur_b = _ce_que_la_caisse_voit_sur_la_carte(django_shell, numero_carte_b)
    assert caisse_sur_b['fed_centimes'] == solde_de_reference, caisse_sur_b
    assert set(caisse_sur_b['jetons_locaux']) == set(JETONS_LOCAUX_DE_L_ADHERENT), caisse_sur_b

    # CHECK CARTE a la caisse V2 sur la carte B : la meme fiche qu'avant la perte, chaque
    # monnaie locale a sa valeur, et le FED (pastille « TiBillet »).
    # / CARD CHECK on card B: the same sheet as before the loss.
    fiche_de_b = _check_carte_a_la_caisse(page, pos_page, numero_carte_b)
    _verifier_la_fiche_de_l_adherent(
        fiche_de_b, noms_des_monnaies_locales, solde_de_reference,
        f"[{bouton_utilise}] Check carte sur la carte B",
    )

    # La page « Solde » s'affiche, avec son tableau des monnaies.
    # / The balance page shows, with its currency table.
    login_as(page, email)
    with page.expect_response(lambda reponse: "/my_account/tokens_table/" in reponse.url) as tableau:
        page.goto('/my_account/balance/')
    assert tableau.value.status == 200, (
        f"Le tableau des monnaies de « Mon compte » repond {tableau.value.status}."
    )
