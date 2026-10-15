"""
tests/e2e/test_carte_liee_par_qrcode_fed_en_caisse.py
Une carte liee par QR code, rechargee en FED en ligne, puis utilisee a la caisse V2.
/ A card linked by QR code, topped up with FED online, then used at the V2 POS.

LOCALISATION : tests/e2e/test_carte_liee_par_qrcode_fed_en_caisse.py

POURQUOI CE FICHIER EXISTE / WHY THIS FILE EXISTS
--------------------------------------------------
Un lieu V2 peut avoir des cartes qui n'existent QUE chez l'ancien Fedow : aucune
`CarteCashless` locale ne leur correspond tant que la caisse ne les a pas scannees.
Ce fichier suit la vie d'une telle carte, contre le VRAI Fedow et le VRAI Stripe :

1. La personne scanne le QR code de sa carte (`GET /qr/<qrcode_uuid>/`,
   `ScanQrCode.retrieve`) : la carte est anonyme, le formulaire email s'affiche.
2. Elle donne son email (`POST /qr/link/`, `ScanQrCode.link`) : l'ancien Fedow lie
   la carte a son portefeuille (`linkwallet_cardqrcode`). Cote Lespass,
   `CarteService.lier_a_user` cherche la carte en local.
3. Elle recharge du FED en ligne : `/my_account/` → `refill_wallet` → Stripe
   Checkout → le FED arrive sur son portefeuille chez l'ancien Fedow.
4. Au bar, la caisse V2 scanne la carte. Elle lit le FED PAR LA CARTE
   (`lire_depensable_fed_frais`, `GET card/<tag>/`), et le debite par la carte et la
   carte primaire du caissier (`_debiter_legacy`, `POST transaction/`).
5. Le caissier rembourse le FED restant et reinitialise la carte (vidage, « RFD »).

L'ORDRE NE DOIT PAS COMPTER. Si la caisse scanne la carte AVANT la liaison par QR
code, la carte est rapatriee en local (`trouver_ou_rapatrier_la_carte`), puis la
liaison y pose l'adherent. Si la liaison vient D'ABORD, la carte n'existe pas encore
en local : la liaison fabrique sa copie locale avec l'adherent
(`relier_la_copie_locale_de_la_carte`, QrcodeCashless/services.py). Dans les deux cas,
la caisse voit et depense le FED.

/ Order must not matter: scan first or link first, the local card carries the member
and the POS reads and spends the FED through the card.

LES TROIS TESTS / THE THREE TESTS
----------------------------------
- A, le parcours reel (liaison, recharge par le bouton de « Mon espace », PUIS
  caisse : check carte, vente, remboursement). Les etapes 4 a 9 sont verifiees une
  par une, et TOUTES sont jouees meme si l'une casse : le message d'echec liste
  chaque etape rouge, la premiere en tete.
- B, le temoin (caisse D'ABORD, puis liaison, recharge, cafe). Il doit etre VERT : il
  prouve que le defaut depend de l'ordre.
- C, la carte ANONYME qui porte du FED de l'ancien systeme (borne avec TPE, LaBoutik
  V1 : portefeuille ephemere, sans adherent). La caisse doit afficher et debiter ce
  FED. Aucun moyen propre de fabriquer cette carte depuis le conteneur lespass_django
  n'existe aujourd'hui : le test est marque xfail, non joue, en attente de la borne
  (kiosk) V2.

CE QUE CES TESTS LAISSENT DERRIERE EUX / WHAT THESE TESTS LEAVE BEHIND
-----------------------------------------------------------------------
Rien n'est annule. Chaque passage cree, avec des identifiants neufs : une carte chez
l'ancien Fedow (il n'a pas de route de suppression), un adherent et son portefeuille,
un paiement Stripe de test de 3 €, la carte locale rapatriee, et (si le cafe passe)
une vente encaissee, numerotee et chainee avec 1,50 € de FED passes de l'adherent au
lieu, puis (test A) une vente de vidage qui rend le FED restant au lieu et
reinitialise la carte. Le point de vente « Comptoir cafe FED E2E » et son article sont reutilises d'un
passage a l'autre.

/ Nothing is rolled back: a card on the old Fedow, a member and wallet, a 3 € Stripe
test payment, the fetched local card and, if the coffee goes through, a chained sale.

PREREQUIS / PREREQUISITES
--------------------------
- le serveur de dev repond sur https://lespass.tibillet.localhost/ ;
- l'ancien Fedow de dev repond (`FedowConfig.get_solo().can_fedow()` vrai) ;
- les donnees POS de test existent (fixture `ensure_pos_data`, carte primaire A49E8E2A) ;
- **`stripe listen` doit tourner** (tests A et B, marqueur `stripe_listen`). Le credit
  FED a deux chemins : le webhook Stripe, et le retour du navigateur sur Lespass
  (`return_refill_wallet`, qui fait valider le paiement par l'ancien Fedow). Le
  marqueur suit la convention des parcours de recharge FED du depot.

LANCEMENT / RUN :
    make e2e ARGS="tests/e2e/test_carte_liee_par_qrcode_fed_en_caisse.py -v -s"
"""

import json
import re
import time
import uuid as uuid_module

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import expect

# La caisse debite le FED par la carte du client ET la carte primaire du caissier :
# celle-ci doit etre declaree a l'ancien Fedow (fixture partagee, etat remis a la fin).
# / The POS debits FED through the card AND the cashier's primary card, declared to
# the old Fedow (shared fixture, state restored afterwards).
from tests.e2e.test_parcours_fedow_reel import carte_primaire_declaree_a_l_ancien_fedow  # noqa: F401
from tests.e2e.test_parcours_fedow_reel import (
    CHEMIN_DE_L_APERCU_DU_VIDAGE,
    CHEMIN_DU_VIDAGE_DE_CARTE,
    _lire_la_vente_du_vidage,
    _poster,
    _verifier_le_vidage_par_l_ancien_fedow,
)


# Familles de tests : `make e2e-visible <famille>` (liste : make help, ou pytest.ini).
# / Test families: `make e2e-visible <family>` (list: make help, or pytest.ini).
pytestmark = [
    pytest.mark.qrcode,
    pytest.mark.caisse,
    pytest.mark.monnaie,
    pytest.mark.usefixtures("carte_primaire_declaree_a_l_ancien_fedow"),
]

# Le point de vente et l'article de ces tests. Le cafe coute moins que la recharge :
# il doit etre paye entierement en FED.
# / The POS and item of these tests. The coffee costs less than the top-up.
NOM_DU_COMPTOIR = "Comptoir cafe FED E2E"
NOM_DU_CAFE = "Cafe E2E FED"
PRIX_DU_CAFE_CENTIMES = 150

# Montant de la recharge FED en ligne. Le checkout fabrique par l'ancien Fedow est a
# montant LIBRE : la personne le saisit sur la page Stripe.
# / Online FED top-up amount. The Fedow checkout is free-amount.
MONTANT_DE_LA_RECHARGE_EUROS = "3"
MONTANT_DE_LA_RECHARGE_CENTIMES = 300

# La carte primaire du caissier, seedee par `create_test_pos_data`.
# / The cashier's primary card, seeded by create_test_pos_data.
TAG_DE_LA_CARTE_PRIMAIRE = "A49E8E2A"

# Le moyen de paiement comptable du FED (PaymentMethod.STRIPE_FED).
# / The accounting payment method for FED.
MOYEN_DE_PAIEMENT_DU_FED = "SF"


# ---------------------------------------------------------------------------
# Utilitaires
# ---------------------------------------------------------------------------


def _lire_json_marque(sortie, marqueur):
    """Extrait le JSON imprime par le shell Django derriere un marqueur.

    Le shell melange le JSON attendu avec les journaux applicatifs : on repere la
    ligne par un marqueur explicite.
    / Extracts the JSON printed by the Django shell behind an explicit marker.
    """
    for ligne in sortie.splitlines():
        if ligne.startswith(marqueur):
            return json.loads(ligne[len(marqueur) :])
    pytest.fail(
        f"Le shell Django n'a rien imprime derriere '{marqueur}'. "
        f"Sortie : {sortie[-800:]}"
    )


def _motif_du_montant(centimes):
    """Le motif d'un montant affiche en euros, « 1,50 » ou « 1.50 ».

    Le chiffre qui precede ne doit pas etre un chiffre : « 11,50 » ne vaut pas « 1,50 ».
    / The pattern of an amount displayed in euros. No digit just before it.
    """
    return re.compile(rf"(?<!\d){centimes // 100}[,.]{centimes % 100:02d}")


@pytest.fixture(scope="module")
def ancien_fedow_joignable(django_shell):
    """Echoue tout de suite si le lieu `lespass` n'est pas relie a l'ancien Fedow.

    Sans lui, aucune carte ne peut etre creee ni liee : tous les tests de ce fichier
    tomberaient pour une raison sans rapport avec ce qu'ils verifient.
    / Fails at once if the `lespass` venue is not linked to the old Fedow.
    """
    sortie = django_shell(
        "from fedow_connect.models import FedowConfig\n"
        "print('CAN_FEDOW=' + str(FedowConfig.get_solo().can_fedow()))"
    )
    if "CAN_FEDOW=True" not in sortie:
        pytest.fail(
            "Le lieu lespass n'est pas relie a l'ancien Fedow (can_fedow() faux) : "
            "verifier que le conteneur fedow_django tourne. Sortie : " + sortie[-400:]
        )


@pytest.fixture(scope="module")
def comptoir_du_cafe(django_shell, ensure_pos_data):
    """Cree (ou retrouve) un point de vente et un cafe a 1,50 €, ouvert a la carte primaire.

    Le point de vente est propre a ce fichier : aucun autre test n'y vend.
    / Creates (or finds) a POS and a 1.50 € coffee, reserved to this file.
    """
    prix_en_euros = f"{PRIX_DU_CAFE_CENTIMES / 100:.2f}"
    sortie = django_shell(
        "import json\n"
        "from decimal import Decimal\n"
        "from BaseBillet.models import Price, Product\n"
        "from laboutik.models import CartePrimaire, PointDeVente\n"
        "pv, _cree = PointDeVente.objects.get_or_create(\n"
        f"    name='{NOM_DU_COMPTOIR}',\n"
        "    defaults={'comportement': PointDeVente.DIRECT, 'service_direct': True,\n"
        "              'accepte_especes': True, 'accepte_carte_bancaire': True})\n"
        "article, _cree = Product.objects.get_or_create(\n"
        f"    name='{NOM_DU_CAFE}',\n"
        "    defaults={'methode_caisse': Product.VENTE})\n"
        "tarif, _cree = Price.objects.get_or_create(\n"
        "    product=article, name='Tasse',\n"
        f"    defaults={{'prix': Decimal('{prix_en_euros}')}})\n"
        "pv.products.add(article)\n"
        f"primaire = CartePrimaire.objects.filter(carte__tag_id='{TAG_DE_LA_CARTE_PRIMAIRE}').first()\n"
        "if primaire is not None:\n"
        "    primaire.points_de_vente.add(pv)\n"
        "print('COMPTOIR_JSON=' + json.dumps({\n"
        "    'pv_uuid': str(pv.uuid),\n"
        "    'article_uuid': str(article.uuid),\n"
        "    'tarif_centimes': int(round(tarif.prix * 100)),\n"
        "    'tarif_non_fiduciaire': bool(tarif.non_fiduciaire),\n"
        "    'primaire': primaire is not None,\n"
        "}))"
    )
    comptoir = _lire_json_marque(sortie, "COMPTOIR_JSON=")

    if not comptoir["primaire"]:
        pytest.fail(f"Carte primaire {TAG_DE_LA_CARTE_PRIMAIRE} introuvable (seed).")
    tarif_inattendu = (
        comptoir["tarif_centimes"] != PRIX_DU_CAFE_CENTIMES
        or comptoir["tarif_non_fiduciaire"]
    )
    if tarif_inattendu:
        pytest.fail(
            f"Le tarif de '{NOM_DU_CAFE}' n'est plus un prix en euros de "
            f"{PRIX_DU_CAFE_CENTIMES} centimes : {comptoir}. Quelqu'un l'a modifie "
            "dans la base de developpement."
        )
    return comptoir


# ---------------------------------------------------------------------------
# La carte, chez l'ancien Fedow et en local
# ---------------------------------------------------------------------------


def _creer_une_carte_neuve_chez_l_ancien_fedow_seulement(django_shell):
    """Cree une carte NEUVE chez l'ancien Fedow, emise par le lieu `lespass`, absente en local.

    Tag et numero : 8 hexadecimaux en majuscules (validateur de l'ancien Fedow,
    PIEGES 9.31). `qrcode_uuid` neuf. La carte est anonyme : portefeuille ephemere.
    On verifie, avant ET apres la creation, qu'aucune `CarteCashless` locale ne porte
    ce tag : sinon le test ne prouverait plus rien sur le rapatriement.
    / Creates a FRESH card on the old Fedow, issued by `lespass`, missing locally.

    :return: dict {'tag', 'qrcode_uuid'}
    """
    tag_de_la_carte = uuid_module.uuid4().hex[:8].upper()
    uuid_du_qrcode = str(uuid_module.uuid4())

    sortie = django_shell(
        "import json\n"
        "from django.db import connection\n"
        "from QrcodeCashless.models import CarteCashless\n"
        "from fedow_connect.fedow_api import FedowAPI\n"
        f"cartes_locales_avant = CarteCashless.objects.filter(tag_id='{tag_de_la_carte}').count()\n"
        "api = FedowAPI()\n"
        "api.NFCcard.create([{\n"
        f"    'first_tag_id': '{tag_de_la_carte}',\n"
        f"    'qrcode_uuid': '{uuid_du_qrcode}',\n"
        f"    'number_printed': '{tag_de_la_carte}',\n"
        "}])\n"
        f"fiche = api.NFCcard.qr_retrieve('{uuid_du_qrcode}')\n"
        "print('CARTE_JSON=' + json.dumps({\n"
        "    'cartes_locales_avant': cartes_locales_avant,\n"
        f"    'cartes_locales_apres': CarteCashless.objects.filter(tag_id='{tag_de_la_carte}').count(),\n"
        "    'connue_de_fedow': bool(fiche),\n"
        "    'ephemere': bool(fiche and fiche.get('is_wallet_ephemere')),\n"
        "    'domaine_d_origine': (fiche['origin']['place'].get('lespass_domain') if fiche else None),\n"
        "    'domaine_du_lieu': connection.tenant.get_primary_domain().domain,\n"
        "}))"
    )
    etat = _lire_json_marque(sortie, "CARTE_JSON=")

    assert etat["cartes_locales_avant"] == 0, (
        f"Le tag tire au sort {tag_de_la_carte} existe deja en local : relancer le test."
    )
    assert etat["connue_de_fedow"], (
        f"L'ancien Fedow ne connait pas la carte {tag_de_la_carte} qu'on vient de creer : {etat}"
    )
    assert etat["ephemere"], (
        f"La carte neuve n'est pas anonyme chez l'ancien Fedow (portefeuille ephemere attendu) : {etat}"
    )
    assert etat["domaine_d_origine"] == etat["domaine_du_lieu"], (
        f"La carte n'est pas emise par le lieu lespass : le scan du QR code "
        f"redirigerait ailleurs : {etat}"
    )
    assert etat["cartes_locales_apres"] == 0, (
        f"La creation chez l'ancien Fedow a cree la carte {tag_de_la_carte} en local : "
        "le parcours ne testerait plus une carte connue de l'ancien Fedow seulement."
    )
    return {"tag": tag_de_la_carte, "qrcode_uuid": uuid_du_qrcode}


def _lire_la_carte_locale(django_shell, tag_de_la_carte):
    """La `CarteCashless` locale du tag : existe-t-elle, et qui la porte ?
    / The local CarteCashless of the tag: does it exist, and who holds it?

    :return: dict {'existe', 'email_du_titulaire', 'wallet_ephemere'}
    """
    sortie = django_shell(
        "import json\n"
        "from QrcodeCashless.models import CarteCashless\n"
        f"carte = CarteCashless.objects.filter(tag_id='{tag_de_la_carte}').select_related('user').first()\n"
        "print('LOCALE_JSON=' + json.dumps({\n"
        "    'existe': carte is not None,\n"
        "    'email_du_titulaire': (carte.user.email if (carte and carte.user) else None),\n"
        "    'wallet_ephemere': (str(carte.wallet_ephemere_id) if (carte and carte.wallet_ephemere_id) else None),\n"
        "}))"
    )
    return _lire_json_marque(sortie, "LOCALE_JSON=")


def _fed_de_l_adherent_sans_cache(django_shell, email):
    """Le FED de l'adherent chez l'ancien Fedow, relu SANS cache (`retrieve_by_signature`).

    Le cache garderait la valeur d'avant la recharge ou d'avant le cafe.
    / The member's FED on the old Fedow, read WITHOUT cache.
    """
    sortie = django_shell(
        "from AuthBillet.models import TibilletUser\n"
        "from fedow_connect.fedow_api import FedowAPI\n"
        f"user = TibilletUser.objects.get(email='{email}')\n"
        "portefeuille = FedowAPI().wallet.retrieve_by_signature(user).validated_data\n"
        "federe = 0\n"
        "for jeton in portefeuille['tokens']:\n"
        "    if jeton['asset_category'] == 'FED':\n"
        "        federe += int(jeton['value'])\n"
        "print('FED=' + str(federe))"
    )
    trouve = re.search(r"FED=(\d+)", sortie)
    if not trouve:
        pytest.fail(f"Lecture du FED impossible chez l'ancien Fedow : {sortie[-400:]}")
    return int(trouve.group(1))


# ---------------------------------------------------------------------------
# Le parcours de la personne (navigateur)
# ---------------------------------------------------------------------------


def _lier_la_carte_par_son_qrcode(page, uuid_du_qrcode, email):
    """La personne scanne le QR code de sa carte et donne son email.

    Vrai parcours : `GET /qr/<uuid>/` affiche le formulaire (carte anonyme), le
    formulaire part en htmx sur `POST /qr/link/`, la vue renvoie vers `/qr/<uuid>/`,
    qui connecte la personne et l'envoie sur `/my_account`.
    / Real journey: the form shows, posts via htmx, the view sends back to /qr/<uuid>/
    which logs the person in and redirects to /my_account.
    """
    page.goto(f"/qr/{uuid_du_qrcode}/")
    formulaire = page.locator("#linkform")
    if formulaire.count() == 0:
        pytest.fail(
            f"Le scan du QR code n'affiche pas le formulaire email : la carte n'est pas "
            f"vue comme anonyme. Page : {page.url} — {page.locator('body').inner_text()[:500]}"
        )

    formulaire.locator("#link_email").fill(email)
    formulaire.locator("#confirm-email").fill(email)
    # Le lieu peut exiger le nom (`config.need_name`) : on remplit si les champs sont la.
    # / The venue may require the name: fill the fields when present.
    champ_prenom = formulaire.locator('input[name="firstname"]')
    if champ_prenom.count() > 0:
        champ_prenom.fill("Douglas")
        formulaire.locator('input[name="lastname"]').fill("Adams")
    formulaire.locator("#cgu").check()
    formulaire.locator('button[type="submit"]').click()

    try:
        page.wait_for_url(lambda url: "/my_account" in url, timeout=30_000)
    except PlaywrightTimeoutError:
        pytest.fail(
            "La liaison par QR code n'a pas abouti sur /my_account. "
            f"Page : {page.url} — {page.locator('body').inner_text()[:600]}"
        )

    # La liaison retire `email_valid` : tant que l'email n'est pas confirme, la page
    # solde n'offre pas la recharge. En dev, `ScanQrCode.retrieve` pose dans les
    # messages le lien de confirmation « TEST MODE » (`/emailconfirmation/<token>`),
    # celui que la personne recevrait par email. On le suit, comme elle le ferait.
    # / Linking clears email_valid: no top-up until the email is confirmed. In dev the
    # view posts the "TEST MODE" confirmation link in the messages: follow it.
    lien_de_confirmation = page.locator('a[href*="/emailconfirmation/"]')
    if lien_de_confirmation.count() == 0:
        pytest.fail(
            "Apres la liaison par QR code, la page n'affiche pas le lien de confirmation "
            "« TEST MODE » (/emailconfirmation/<token>) : impossible de confirmer l'email. "
            f"Page : {page.url} — {page.locator('body').inner_text()[:600]}"
        )
    page.goto(lien_de_confirmation.first.get_attribute("href"))


def _recharger_du_fed_en_ligne(
    page, django_shell, fill_stripe_card, soumettre_paiement_stripe, email
):
    """La personne connectee recharge du FED par carte bancaire (vrai Stripe Checkout).

    Le checkout est fabrique par l'ancien Fedow (montant libre). Il FAUT cliquer le
    bouton : `refill_wallet` renvoie un en-tete `HX-Redirect` que seul htmx suit.
    Le credit arrive par le webhook ou par le retour du navigateur : on relit le FED en
    boucle, sans cache, plutot que de parier sur un delai fixe.
    / The logged-in person tops up FED by card. Click the button (HX-Redirect). Poll
    the FED without cache.

    :return: dict {'avant', 'apres'} en centimes
    """
    fed_avant = _fed_de_l_adherent_sans_cache(django_shell, email)

    # Le skin V2 porte le bouton « Recharger » sur l'accueil de Mon espace
    # (`compte-recharger`) ; sa page solde n'en a pas.
    # / The V2 skin puts the "Top up" button on the My account home page.
    page.goto("/my_account/")
    bouton_de_recharge = page.locator('[data-testid="compte-recharger"]')
    if bouton_de_recharge.count() == 0:
        pytest.fail(
            "Le bouton « Recharger » (compte-recharger) est absent de /my_account/ pour "
            "la personne qui vient de lier sa carte. Verifier "
            "`Configuration.show_refill_button()` et le skin du lieu. "
            f"Page : {page.locator('body').inner_text()[:500]}"
        )
    bouton_de_recharge.first.click()

    page.wait_for_url(
        lambda url: "checkout.stripe.com" in url,
        timeout=20_000,
        # Stripe garde des connexions ouvertes : `networkidle` n'y arrive jamais (PIEGES 9.28).
        # / Stripe keeps connections open: networkidle never settles there.
        wait_until="domcontentloaded",
    )

    # Le formulaire est monte par React APRES l'arrivee sur la page.
    # / The form is mounted by React AFTER arrival.
    champ_montant = page.locator("input#customUnitAmount")
    champ_montant.wait_for(state="visible", timeout=30_000)
    champ_montant.fill(MONTANT_DE_LA_RECHARGE_EUROS)

    fill_stripe_card(page, email)

    # Le nom du porteur est OBLIGATOIRE sur ce checkout, et React le monte parfois apres
    # le passage de `fill_stripe_card` : on le garantit ici.
    # / The cardholder name is REQUIRED here and may be mounted late.
    champ_nom_du_porteur = page.locator("input#billingName")
    champ_nom_du_porteur.wait_for(state="visible", timeout=30_000)
    if not champ_nom_du_porteur.input_value():
        champ_nom_du_porteur.fill("Douglas Adams")

    # La soumission demande de l'insistance sur ce checkout (PIEGES 12.14).
    # / Submitting takes persistence here (PIEGES 12.14).
    soumettre_paiement_stripe(page)

    page.wait_for_url(
        lambda url: "checkout.stripe.com" not in url,
        timeout=60_000,
        wait_until="domcontentloaded",
    )

    fed_apres = fed_avant
    for _tentative in range(20):
        fed_apres = _fed_de_l_adherent_sans_cache(django_shell, email)
        if fed_apres != fed_avant:
            break
        time.sleep(3)

    return {"avant": fed_avant, "apres": fed_apres}


def _verifier_que_le_fed_est_credite(recharge):
    """L'ancien Fedow a credite exactement le montant saisi sur la page Stripe.
    / The old Fedow credited exactly the amount typed on the Stripe page."""
    attendu = recharge["avant"] + MONTANT_DE_LA_RECHARGE_CENTIMES
    assert recharge["apres"] == attendu, (
        f"PREPARATION — le FED n'a pas ete credite chez l'ancien Fedow : avant "
        f"{recharge['avant']}, apres {recharge['apres']}, attendu {attendu}. Si rien n'a "
        "bouge : `stripe listen` mort, ou retour du navigateur sur Lespass qui n'a pas "
        "fait valider le paiement par l'ancien Fedow (journal du serveur)."
    )


# ---------------------------------------------------------------------------
# La caisse (navigateur, lecteur NFC simule du mode demo)
# ---------------------------------------------------------------------------


def _scanner_la_carte(page, tag_de_la_carte):
    """Lecteur NFC simule du mode demo : saisie du tag, validee par Entree.
    / Demo mode's simulated NFC reader: type the tag, press Enter."""
    page.locator(".nfc-toggle-simu .touch").click()
    saisie_du_tag = page.locator("#nfc-simu-manual-input")
    saisie_du_tag.fill(tag_de_la_carte)
    saisie_du_tag.press("Enter")


def _check_carte(page, pos_page, tag_de_la_carte):
    """Le caissier ouvre la caisse, touche « CHECK CARTE » et scanne la carte.

    La caisse est rouverte a chaque fois : l'etat laisse par une etape precedente
    (ecran de paiement, fiche ouverte) ne gene pas celle-ci.
    / The cashier opens the POS, taps CARD CHECK and scans. The POS is reopened each
    time so a previous step's leftovers do not interfere.

    :return: dict {'erreur', 'anonyme', 'total', 'pastille_fed'} (textes affiches, ou None)
    """
    pos_page(page, NOM_DU_COMPTOIR)
    page.locator('[data-testid="addition-check-carte"]').click()
    _scanner_la_carte(page, tag_de_la_carte)

    fiche_de_la_carte = page.locator('[data-testid="retour-carte"]')
    expect(fiche_de_la_carte).to_be_visible()

    erreur = page.locator('[data-testid="retour-carte-erreur"]')
    pastille_fed = page.locator('[data-testid="retour-carte-solde-fed"]')
    total = page.locator('[data-testid="retour-carte-soldes"]')
    return {
        "erreur": erreur.inner_text() if erreur.count() > 0 else None,
        "anonyme": page.locator('[data-testid="retour-carte-anonyme"]').count() > 0,
        "total": total.inner_text() if total.count() > 0 else None,
        "pastille_fed": pastille_fed.inner_text() if pastille_fed.count() > 0 else None,
    }


def _payer_le_cafe_en_nfc(page, pos_page, comptoir, tag_de_la_carte):
    """Le caissier vend un cafe et le fait payer par la carte NFC du client.

    On attend l'un des trois ecrans possibles : succes, fonds insuffisants, ou
    complement de paiement. C'est l'appelant qui juge.
    / The cashier sells a coffee paid with the client's NFC card. We wait for one of
    the three possible screens: success, insufficient funds, or complement.

    :return: dict {'ecran': 'succes'|'insuffisant'|'complement', 'texte': str}
    """
    pos_page(page, NOM_DU_COMPTOIR)
    tuile_du_cafe = page.locator(f'[data-testid="article-{comptoir["article_uuid"]}"]')
    expect(tuile_du_cafe).to_be_visible()
    tuile_du_cafe.click()

    bouton_valider = page.locator('[data-testid="addition-valider"]')
    expect(bouton_valider).to_be_enabled()
    bouton_valider.click()
    page.locator('[data-testid="paiement-btn-cashless"]').click()
    _scanner_la_carte(page, tag_de_la_carte)

    ecran_de_succes = page.locator('[data-testid="paiement-succes"]')
    ecran_insuffisant = page.locator('[data-testid="paiement-nfc-insuffisant"]')
    ecran_de_complement = page.locator('[data-testid="complement-paiement"]')
    un_des_trois_ecrans = ecran_de_succes.or_(ecran_insuffisant).or_(
        ecran_de_complement
    )
    un_des_trois_ecrans.first.wait_for(state="visible", timeout=20_000)

    if ecran_de_succes.count() > 0 and ecran_de_succes.first.is_visible():
        return {"ecran": "succes", "texte": ecran_de_succes.first.inner_text()}
    if ecran_insuffisant.count() > 0 and ecran_insuffisant.first.is_visible():
        return {"ecran": "insuffisant", "texte": ecran_insuffisant.first.inner_text()}
    return {"ecran": "complement", "texte": ecran_de_complement.first.inner_text()}


def _uuid_du_portefeuille_de_l_adherent(django_shell, email):
    """L'uuid du portefeuille de l'adherent : l'emetteur attendu du remboursement.
    / The member's wallet uuid: the expected sender of the refund."""
    sortie = django_shell(
        "from AuthBillet.models import TibilletUser\n"
        f"user = TibilletUser.objects.get(email='{email}')\n"
        "print('PORTEFEUILLE=' + str(user.wallet.uuid))"
    )
    trouve = re.search(r"PORTEFEUILLE=(\S+)", sortie)
    if not trouve:
        pytest.fail(f"Portefeuille de {email} introuvable : {sortie[-400:]}")
    return trouve.group(1)


def _vider_la_carte_au_comptoir_du_cafe(page, pos_page, comptoir, tag_de_la_carte):
    """Le caissier scanne la carte (apercu), puis la rembourse et la reinitialise.

    On ouvre la vraie caisse pour poser la session et le cookie CSRF, puis on envoie
    les deux formulaires aux vraies routes, avec la carte primaire du caissier.
    « Rembourser et reinitialiser » envoie `vider_carte=true`.
    / The cashier scans the card (preview), then refunds and resets it.

    :return: tuple (reponse de l'apercu, reponse du vidage)
    """
    pos_page(page, NOM_DU_COMPTOIR)
    donnees_communes = {
        "tag_id": tag_de_la_carte,
        "tag_id_cm": TAG_DE_LA_CARTE_PRIMAIRE,
        "uuid_pv": comptoir["pv_uuid"],
    }
    reponse_de_l_apercu = _poster(page, CHEMIN_DE_L_APERCU_DU_VIDAGE, donnees_communes)
    donnees_du_vidage = dict(donnees_communes)
    donnees_du_vidage["vider_carte"] = "true"
    reponse_du_vidage = _poster(page, CHEMIN_DU_VIDAGE_DE_CARTE, donnees_du_vidage)
    return reponse_de_l_apercu, reponse_du_vidage


def _lire_la_vente_du_cafe(django_shell, tag_de_la_carte):
    """Les ventes (nature VENTE) de la carte, avec leurs reglements.

    La carte est neuve : au plus une vente doit exister, celle du cafe.
    / The card's sales (VENTE) with their payments. The card is fresh: at most one.
    """
    sortie = django_shell(
        "import json\n"
        "from BaseBillet.models_vente import Reglement, Vente\n"
        "ventes = list(Vente.objects.filter(\n"
        f"    nature=Vente.Nature.VENTE, carte__tag_id='{tag_de_la_carte}'))\n"
        "resultat = []\n"
        "for vente in ventes:\n"
        "    reglements = []\n"
        "    for reglement in Reglement.objects.filter(vente=vente).order_by('datetime'):\n"
        "        reglements.append({\n"
        "            'moyen': reglement.moyen,\n"
        "            'montant': reglement.montant,\n"
        "            'reference_externe': reglement.reference_externe,\n"
        "        })\n"
        "    resultat.append({'statut': vente.statut, 'numero': vente.numero,\n"
        "                     'reglements': reglements})\n"
        "print('VENTES_JSON=' + json.dumps(resultat))"
    )
    return _lire_json_marque(sortie, "VENTES_JSON=")


def _verifier_la_vente_du_cafe_payee_en_fed(ventes):
    """Une seule vente, REGLEE, numerotee, avec un reglement FED du prix du cafe.
    / One sale, settled, numbered, with one FED payment of the coffee price."""
    assert len(ventes) == 1, (
        f"Attendu : une vente du cafe pour cette carte neuve : {ventes}"
    )
    vente = ventes[0]
    assert vente["statut"] == "REGLEE", (
        f"La vente du cafe n'est pas encaissee : {vente}"
    )
    assert vente["numero"], f"La vente encaissee n'a pas de numero : {vente}"
    reglements_en_fed = [
        reglement
        for reglement in vente["reglements"]
        if reglement["moyen"] == MOYEN_DE_PAIEMENT_DU_FED
    ]
    assert [r["montant"] for r in reglements_en_fed] == [PRIX_DU_CAFE_CENTIMES], (
        f"Attendu : un reglement {MOYEN_DE_PAIEMENT_DU_FED} (FED) de "
        f"{PRIX_DU_CAFE_CENTIMES} centimes : {vente}"
    )
    assert reglements_en_fed[0]["reference_externe"], (
        f"Le reglement FED ne dit pas quelle transaction de l'ancien Fedow il copie : {vente}"
    )


# ---------------------------------------------------------------------------
# Test A — liaison par QR code, recharge en ligne, PUIS caisse
# ---------------------------------------------------------------------------


@pytest.mark.stripe_listen
def test_carte_liee_par_qrcode_puis_rechargee_en_fed_paie_un_cafe_a_la_caisse(
    page,
    pos_page,
    django_shell,
    fill_stripe_card,
    soumettre_paiement_stripe,
    ancien_fedow_joignable,
    comptoir_du_cafe,
):
    """Le parcours reel : QR code, email, recharge FED en ligne, puis cafe au bar.

    Etapes 1 a 3 : la preparation. Un echec y est une panne d'environnement ou de
    parcours, et arrete le test.
    Etapes 4 a 9 : les constats (carte locale, check carte, vente, debit, rescan,
    remboursement). Elles sont TOUTES jouees, meme si l'une casse : le message
    d'echec liste chaque etape rouge, la premiere en tete.

    / The real journey. Steps 1-3 prepare (a failure stops the test). Steps 4-9 are
    ALL played; the failure message lists every red step, the first one on top.
    """
    # --- 1. Une carte neuve, connue de l'ancien Fedow seulement ---
    carte = _creer_une_carte_neuve_chez_l_ancien_fedow_seulement(django_shell)
    tag_de_la_carte = carte["tag"]
    email = f"e2e-qr-fed-{uuid_module.uuid4().hex[:8]}@tibillet.test"

    # --- 2. La personne scanne le QR code et donne son email ---
    _lier_la_carte_par_son_qrcode(page, carte["qrcode_uuid"], email)

    # --- 3. Elle recharge du FED en ligne (vrai Stripe) ---
    recharge = _recharger_du_fed_en_ligne(
        page, django_shell, fill_stripe_card, soumettre_paiement_stripe, email
    )
    _verifier_que_le_fed_est_credite(recharge)
    fed_avant_le_cafe = recharge["apres"]

    etapes_rouges = []

    # --- 4. La liaison par QR code a rattache la carte en local ---
    carte_locale = _lire_la_carte_locale(django_shell, tag_de_la_carte)
    if not carte_locale["existe"]:
        etapes_rouges.append(
            f"ETAPE 4 — la carte {tag_de_la_carte} n'existe PAS en local apres la liaison "
            "par QR code. L'ancien Fedow a lie la carte, mais `CarteService.lier_a_user` "
            "n'a pas trouve de `CarteCashless` (CarteIntrouvable avale par ScanQrCode.link) "
            "et personne ne l'a rapatriee. Le scan suivant a la caisse creera une carte "
            f"SANS adherent : le FED de {email} sera invisible. {carte_locale}"
        )
    elif carte_locale["email_du_titulaire"] != email:
        etapes_rouges.append(
            f"ETAPE 4 — la carte {tag_de_la_carte} existe en local mais ne porte pas "
            f"l'adherent {email} : {carte_locale}"
        )

    # --- 5. CHECK CARTE : la fiche affiche le FED recharge ---
    try:
        fiche = _check_carte(page, pos_page, tag_de_la_carte)
        assert fiche["erreur"] is None, f"La fiche affiche une erreur : {fiche}"
        assert fiche["pastille_fed"] is not None, (
            "La fiche n'a pas de pastille « TiBillet » (FED) : la caisse ne lit pas le FED "
            f"de cette carte (carte anonyme pour elle ? {fiche['anonyme']}). Fiche : {fiche}"
        )
        assert _motif_du_montant(fed_avant_le_cafe).search(fiche["pastille_fed"]), (
            f"La pastille FED n'affiche pas {fed_avant_le_cafe} centimes : {fiche}"
        )
    except (AssertionError, PlaywrightTimeoutError) as erreur:
        etapes_rouges.append(
            f"ETAPE 5 — le check carte n'affiche pas le FED recharge : {erreur}"
        )

    # --- 6. Le cafe paye en NFC : ecran de succes, pas de complement ---
    try:
        paiement = _payer_le_cafe_en_nfc(
            page, pos_page, comptoir_du_cafe, tag_de_la_carte
        )
        assert paiement["ecran"] == "succes", (
            f"Le cafe paye par la carte tombe sur l'ecran « {paiement['ecran']} » au lieu "
            f"du succes : la caisse ne voit pas les {fed_avant_le_cafe} centimes de FED. "
            f"Ecran : {paiement['texte'][:400]}"
        )
    except (AssertionError, PlaywrightTimeoutError) as erreur:
        etapes_rouges.append(
            f"ETAPE 6 — le cafe n'est pas paye par le FED de la carte : {erreur}"
        )

    # --- 7. L'ancien Fedow a debite le FED, et la vente porte un reglement FED ---
    try:
        fed_apres_le_cafe = _fed_de_l_adherent_sans_cache(django_shell, email)
        assert fed_apres_le_cafe == fed_avant_le_cafe - PRIX_DU_CAFE_CENTIMES, (
            f"Le FED n'a pas baisse du prix du cafe chez l'ancien Fedow : "
            f"{fed_avant_le_cafe} → {fed_apres_le_cafe}, attendu "
            f"{fed_avant_le_cafe - PRIX_DU_CAFE_CENTIMES}."
        )
        _verifier_la_vente_du_cafe_payee_en_fed(
            _lire_la_vente_du_cafe(django_shell, tag_de_la_carte)
        )
    except AssertionError as erreur:
        etapes_rouges.append(f"ETAPE 7 — le debit FED ou la vente manque : {erreur}")

    # --- 8. Un nouveau check carte affiche le FED diminue ---
    fed_restant = fed_avant_le_cafe - PRIX_DU_CAFE_CENTIMES
    try:
        fiche_apres = _check_carte(page, pos_page, tag_de_la_carte)
        assert fiche_apres["pastille_fed"] is not None, (
            f"La fiche n'a pas de pastille FED apres le cafe : {fiche_apres}"
        )
        assert _motif_du_montant(fed_restant).search(fiche_apres["pastille_fed"]), (
            f"La pastille FED n'affiche pas les {fed_restant} centimes restants : {fiche_apres}"
        )
    except (AssertionError, PlaywrightTimeoutError) as erreur:
        etapes_rouges.append(
            f"ETAPE 8 — le rescan n'affiche pas le FED diminue : {erreur}"
        )

    # --- 9. REMBOURSEMENT : le caissier vide la carte, le FED restant revient au lieu ---
    try:
        reponse_de_l_apercu, reponse_du_vidage = _vider_la_carte_au_comptoir_du_cafe(
            page, pos_page, comptoir_du_cafe, tag_de_la_carte
        )
        _verifier_le_vidage_par_l_ancien_fedow(
            reponse_de_l_apercu,
            reponse_du_vidage,
            _lire_la_vente_du_vidage(django_shell, tag_de_la_carte),
            _uuid_du_portefeuille_de_l_adherent(django_shell, email),
            fed_restant,
            moyen_attendu=MOYEN_DE_PAIEMENT_DU_FED,
            categorie_attendue="FED",
        )
        fed_apres_le_remboursement = _fed_de_l_adherent_sans_cache(django_shell, email)
        assert fed_apres_le_remboursement == 0, (
            f"Il reste {fed_apres_le_remboursement} centimes de FED apres le vidage."
        )
    except (AssertionError, PlaywrightTimeoutError) as erreur:
        etapes_rouges.append(
            f"ETAPE 9 — le remboursement (vidage de la carte) n'a pas rendu les "
            f"{fed_restant} centimes de FED : {erreur}"
        )

    if etapes_rouges:
        pytest.fail(
            f"{len(etapes_rouges)} etape(s) rouge(s) sur 6 (carte {tag_de_la_carte}, "
            f"adherent {email}). La premiere est la cause probable :\n\n"
            + "\n\n".join(etapes_rouges)
        )


# ---------------------------------------------------------------------------
# Test B — temoin : la caisse scanne D'ABORD, puis liaison, recharge, cafe
# ---------------------------------------------------------------------------


@pytest.mark.stripe_listen
def test_temoin_carte_scannee_en_caisse_avant_la_liaison_par_qrcode_paie_un_cafe_en_fed(
    page,
    pos_page,
    django_shell,
    fill_stripe_card,
    soumettre_paiement_stripe,
    ancien_fedow_joignable,
    comptoir_du_cafe,
):
    """Meme carte neuve, ordre inverse : le check carte rapatrie la carte AVANT la liaison.

    La liaison par QR code trouve alors la carte locale et y pose l'adherent : le FED
    recharge en ligne est vu et debite par la caisse. Ce test doit etre VERT ; il prouve
    que le defaut du test A depend de l'ordre.
    / Same fresh card, reversed order: the card check fetches the card BEFORE the link.
    Must be GREEN: proves test A's defect depends on the order.
    """
    # --- 1. Une carte neuve, connue de l'ancien Fedow seulement ---
    carte = _creer_une_carte_neuve_chez_l_ancien_fedow_seulement(django_shell)
    tag_de_la_carte = carte["tag"]
    email = f"e2e-qr-fed-temoin-{uuid_module.uuid4().hex[:8]}@tibillet.test"

    # --- 2. CHECK CARTE d'abord : la carte est rapatriee, anonyme ---
    fiche_avant_liaison = _check_carte(page, pos_page, tag_de_la_carte)
    assert fiche_avant_liaison["erreur"] is None, (
        f"Le premier scan n'a pas rapatrie la carte : {fiche_avant_liaison}"
    )
    assert fiche_avant_liaison["anonyme"], (
        f"La carte rapatriee devrait etre anonyme : {fiche_avant_liaison}"
    )
    carte_locale = _lire_la_carte_locale(django_shell, tag_de_la_carte)
    assert carte_locale["existe"], (
        f"Le check carte n'a pas cree la carte locale : {carte_locale}"
    )
    assert carte_locale["email_du_titulaire"] is None, (
        f"La carte rapatriee porte deja un adherent : {carte_locale}"
    )

    # --- 3. Liaison par QR code : la carte locale recoit l'adherent ---
    _lier_la_carte_par_son_qrcode(page, carte["qrcode_uuid"], email)
    carte_locale = _lire_la_carte_locale(django_shell, tag_de_la_carte)
    assert carte_locale["email_du_titulaire"] == email, (
        f"La liaison par QR code n'a pas pose l'adherent sur la carte locale deja "
        f"rapatriee : {carte_locale}"
    )

    # --- 4. Recharge FED en ligne ---
    recharge = _recharger_du_fed_en_ligne(
        page, django_shell, fill_stripe_card, soumettre_paiement_stripe, email
    )
    _verifier_que_le_fed_est_credite(recharge)
    fed_avant_le_cafe = recharge["apres"]

    # --- 5. Le cafe paye en NFC est debite en FED ---
    paiement = _payer_le_cafe_en_nfc(page, pos_page, comptoir_du_cafe, tag_de_la_carte)
    assert paiement["ecran"] == "succes", (
        f"Le cafe tombe sur l'ecran « {paiement['ecran']} » : {paiement['texte'][:400]}"
    )

    fed_apres_le_cafe = _fed_de_l_adherent_sans_cache(django_shell, email)
    assert fed_apres_le_cafe == fed_avant_le_cafe - PRIX_DU_CAFE_CENTIMES, (
        f"Le FED n'a pas baisse du prix du cafe : {fed_avant_le_cafe} → {fed_apres_le_cafe}"
    )
    _verifier_la_vente_du_cafe_payee_en_fed(
        _lire_la_vente_du_cafe(django_shell, tag_de_la_carte)
    )


# ---------------------------------------------------------------------------
# Test C — carte ANONYME portant du FED de l'ancien systeme
# ---------------------------------------------------------------------------


def _fed_de_la_carte_anonyme_sans_cache(django_shell, tag_de_la_carte):
    """Le FED du portefeuille de la carte chez l'ancien Fedow (`GET card/<tag>`, sans cache).
    / The FED of the card's wallet on the old Fedow, uncached."""
    sortie = django_shell(
        "from fedow_connect.fedow_api import FedowAPI\n"
        f"fiche = FedowAPI().NFCcard.retrieve('{tag_de_la_carte}')\n"
        "federe = 0\n"
        "for jeton in (fiche.get('wallet') or {}).get('tokens') or []:\n"
        "    if jeton.get('asset_category') == 'FED':\n"
        "        federe += int(jeton.get('value') or 0)\n"
        "print('FED=' + str(federe))"
    )
    trouve = re.search(r"FED=(\d+)", sortie)
    if not trouve:
        pytest.fail(f"Lecture du FED de la carte impossible : {sortie[-400:]}")
    return int(trouve.group(1))


def _poser_du_fed_sur_le_portefeuille_ephemere_de_la_carte(
    django_shell, tag_de_la_carte
):
    """Poser du FED sur le portefeuille EPHEMERE d'une carte anonyme, chez l'ancien Fedow.

    AUCUN MOYEN PROPRE N'EXISTE AUJOURD'HUI depuis le conteneur lespass_django :
    - Le seul chemin de l'ancien Fedow qui credite du FED sur la carte elle-meme (et non
      sur le portefeuille d'un adherent) est celui de la borne V1 avec TPE :
      `StripeAPI.validate_stripe_reader_wise_pose_and_make_transaction`, declenche par
      le webhook Stripe `terminal.reader.action_succeeded` arrivant sur
      `<fedow>/webhook_stripe/`. Ce webhook est verifie avec le secret de l'ancien Fedow
      (`IsStripe`) : il faudrait un second `stripe listen` qui transmette a l'ancien
      Fedow, ce que l'environnement de dev n'a pas.
    - `refill_from_lespass_to_user_wallet` exige un adherent et refuse le FED (il ne
      transfere que les monnaies du lieu). `POST transaction/` (TransactionW2W) n'a
      aucune action qui cree du FED pour un lieu. La fusion (FUSION) ne va que du
      portefeuille ephemere vers celui d'un adherent, jamais l'inverse.
    - La borne V2 (module kiosk) credite la monnaie LOCALE (fedow_core), pas le FED.
    Ecrire directement dans la base de l'ancien Fedow serait bancal : le test ne
    prouverait plus rien sur un vrai parcours.
    / NO CLEAN WAY TODAY from the lespass_django container: the only remote path that
    credits FED to a card itself is the V1 TPE kiosk webhook, signed with the old
    Fedow's secret; nothing else creates FED for an anonymous card.
    """
    pytest.fail(
        f"PREPARATION IMPOSSIBLE — poser du FED sur la carte anonyme {tag_de_la_carte} : "
        "l'ancien Fedow ne credite du FED sur une carte sans adherent que par le webhook "
        "Stripe `terminal.reader.action_succeeded` de la borne V1 avec TPE "
        "(`validate_stripe_reader_wise_pose_and_make_transaction`), signe avec le secret "
        "de l'ancien Fedow : il faut un `stripe listen` dirige vers l'ancien Fedow, "
        "absent de cet environnement. Aucune autre route ne cree du FED pour une carte "
        "anonyme. Voir la docstring de "
        "`_poser_du_fed_sur_le_portefeuille_ephemere_de_la_carte` pour les options."
    )


# run=False : la preparation creerait une carte chez l'ancien Fedow, qui n'a pas de
# route de suppression, pour echouer ensuite a coup sur.
# / run=False: preparing would leave an undeletable card on the old Fedow, then fail.
@pytest.mark.xfail(
    run=False,
    reason=(
        "En attente de la borne (kiosk) V2 : aucun moyen de poser du FED sur une carte "
        "anonyme du Fedow de dev (voir _poser_du_fed_sur_le_portefeuille_ephemere_de_la_carte)."
    ),
)
def test_carte_anonyme_avec_du_fed_de_l_ancien_systeme_paie_un_cafe_a_la_caisse(
    page,
    pos_page,
    django_shell,
    ancien_fedow_joignable,
    comptoir_du_cafe,
):
    """Une carte ANONYME qui porte du FED (borne avec TPE, LaBoutik V1) paie a la caisse V2.

    CIBLE : le check carte affiche ce FED, et un cafe paye en NFC le debite chez
    l'ancien Fedow, par la carte et la carte primaire du caissier (`POST transaction/`).
    En xfail, non joue : aucun moyen propre de poser du FED sur une carte anonyme du
    Fedow de dev (voir `_poser_du_fed_sur_le_portefeuille_ephemere_de_la_carte`).

    / An ANONYMOUS card holding FED pays at the V2 POS. xfail, not run.
    """
    # --- 1. Une carte neuve et anonyme, connue de l'ancien Fedow seulement ---
    carte = _creer_une_carte_neuve_chez_l_ancien_fedow_seulement(django_shell)
    tag_de_la_carte = carte["tag"]

    # --- 2. Du FED sur son portefeuille ephemere ---
    _poser_du_fed_sur_le_portefeuille_ephemere_de_la_carte(
        django_shell, tag_de_la_carte
    )
    fed_avant_le_cafe = _fed_de_la_carte_anonyme_sans_cache(
        django_shell, tag_de_la_carte
    )
    assert fed_avant_le_cafe >= PRIX_DU_CAFE_CENTIMES, (
        f"PREPARATION — la carte anonyme ne porte pas assez de FED : {fed_avant_le_cafe}"
    )

    # --- 3. CHECK CARTE : la fiche (carte anonyme) affiche le FED ---
    fiche = _check_carte(page, pos_page, tag_de_la_carte)
    assert fiche["erreur"] is None, f"La fiche affiche une erreur : {fiche}"
    assert fiche["anonyme"], f"La carte devrait etre anonyme : {fiche}"
    assert fiche["pastille_fed"] is not None, (
        f"La fiche d'une carte anonyme n'affiche pas son FED : {fiche}"
    )
    assert _motif_du_montant(fed_avant_le_cafe).search(fiche["pastille_fed"]), (
        f"La pastille FED n'affiche pas {fed_avant_le_cafe} centimes : {fiche}"
    )

    # --- 4. Le cafe paye en NFC debite ce FED ---
    paiement = _payer_le_cafe_en_nfc(page, pos_page, comptoir_du_cafe, tag_de_la_carte)
    assert paiement["ecran"] == "succes", (
        f"Le cafe tombe sur l'ecran « {paiement['ecran']} » : {paiement['texte'][:400]}"
    )
    fed_apres_le_cafe = _fed_de_la_carte_anonyme_sans_cache(
        django_shell, tag_de_la_carte
    )
    assert fed_apres_le_cafe == fed_avant_le_cafe - PRIX_DU_CAFE_CENTIMES, (
        f"Le FED de la carte anonyme n'a pas baisse du prix du cafe : "
        f"{fed_avant_le_cafe} → {fed_apres_le_cafe}"
    )
    _verifier_la_vente_du_cafe_payee_en_fed(
        _lire_la_vente_du_cafe(django_shell, tag_de_la_carte)
    )
