"""
tests/e2e/test_parcours_fedow_reel.py
Le parcours monnaie → vente → remise en banque, contre le VRAI Fedow.
/ The currency → sale → bank deposit journey, against the REAL Fedow.

LOCALISATION : tests/e2e/test_parcours_fedow_reel.py

POURQUOI CE FICHIER EXISTE / WHY THIS FILE EXISTS
--------------------------------------------------
`tests/pytest/test_parcours_vente_fed_et_remise_en_banque.py` verifie la meme
chaine avec un Fedow simule. Il prouve que Lespass emet les bons appels dans le
bon ordre — pas que le Fedow y repond comme prevu.

Ce fichier-ci parle au Fedow reel. C'est le seul endroit du depot qui le fasse.

/ The pytest file checks the same chain against a simulated Fedow: it proves
Lespass makes the right calls, not that the Fedow answers as expected. This file
talks to the real Fedow — the only place in the repo that does.

CE QUE CES TESTS LAISSENT DERRIERE EUX / WHAT THESE TESTS LEAVE BEHIND
-----------------------------------------------------------------------
Rien n'est annule. Une vente debite un vrai portefeuille, et une remise en banque
VIDE le portefeuille du lieu pour la monnaie concernee — le Fedow n'a pas de
marche arriere. Ces tests sont donc a lancer en dernier, sur un Fedow de
developpement dont on accepte qu'il soit remue.

/ Nothing is rolled back. A sale debits a real wallet, and a bank deposit EMPTIES
the venue's wallet for that currency. Run these last, on a development Fedow.

PREREQUIS / PREREQUISITES
--------------------------
- le serveur de developpement tourne et repond sur le domaine du tenant ;
- le Fedow est joignable (`FedowConfig.can_fedow()` vaut True) ;
- pour le parcours Stripe uniquement : **`stripe listen` doit tourner**, sans
  quoi le webhook de confirmation n'arrive jamais et la recharge reste en
  attente. Ce test est ignore tant que `E2E_STRIPE_LISTEN=1` n'est pas pose.

Lancement / Run:
    docker exec lespass_django poetry run pytest \
        /DjangoFiles/tests/e2e/test_parcours_fedow_reel.py -v

    # avec le volet Stripe (apres avoir lance `stripe listen`) :
    docker exec -e E2E_STRIPE_LISTEN=1 lespass_django poetry run pytest \
        /DjangoFiles/tests/e2e/test_parcours_fedow_reel.py -v
"""

import re
import time
import uuid as uuid_module

import pytest

# Montant du parcours, en centimes. Volontairement petit : chaque execution
# consomme de la vraie monnaie sur le Fedow de developpement.
# / Journey amount in cents. Deliberately small: each run consumes real currency
# on the development Fedow.
MONTANT_DE_LA_VENTE_CENTIMES = 250

# Montant de la recharge federee, en euros. Le checkout fabrique par Fedow est
# a montant LIBRE : c'est le payeur qui le saisit sur la page Stripe.
# / The Fedow checkout is free-amount: the payer types it on the Stripe page.
MONTANT_DE_LA_RECHARGE_EUROS = '3'
MONTANT_DE_LA_RECHARGE_CENTIMES = 300

# La carte de test (4242 4242 4242 4242) est portee par la fixture partagee
# `fill_stripe_card` du conftest, avec les selecteurs de Stripe Checkout.
# / The test card lives in the shared fill_stripe_card fixture.


# ---------------------------------------------------------------------------
# Utilitaires
# ---------------------------------------------------------------------------


def _jeton_csrf(page):
    """Recupere le jeton CSRF depuis les cookies du navigateur.

    `page.request.post` ne joint pas automatiquement l'en-tete CSRF, et les
    vues DRF le refusent sans. Il faut donc avoir visite une page du site
    auparavant, pour que le cookie soit pose.
    / page.request.post does not attach the CSRF header automatically and DRF
    views refuse the request without it.
    """
    for cookie in page.context.cookies():
        if cookie['name'] == 'csrftoken':
            return cookie['value']
    pytest.fail("Aucun cookie csrftoken : la page n'a pas ete visitee avant le POST.")


def _poster(page, chemin, donnees):
    """POST authentifie avec le jeton CSRF et le Referer attendu.
    / Authenticated POST with the CSRF token and expected Referer."""
    base = page.url.split('/')[0] + '//' + page.url.split('/')[2]
    return page.request.post(
        f'{base}{chemin}',
        form=donnees,
        headers={'X-CSRFToken': _jeton_csrf(page), 'Referer': base + '/'},
    )


@pytest.fixture(scope='module')
def monnaie_locale_du_lieu(django_shell):
    """L'asset local fiduciaire du tenant, tel qu'il existe vraiment.

    On ne le fabrique pas : le parcours doit s'appuyer sur la monnaie que le
    lieu utilise reellement, sinon il ne prouve rien sur son cas d'usage.
    / We do not fabricate it: the journey must rely on the currency the venue
    actually uses.
    """
    sortie = django_shell(
        "from fedow_public.models import AssetFedowPublic\n"
        "from django.db import connection\n"
        "asset = AssetFedowPublic.objects.filter("
        "    origin=connection.tenant, category=AssetFedowPublic.TOKEN_LOCAL_FIAT"
        ").first()\n"
        "print('ASSET_UUID=' + (str(asset.uuid) if asset else 'AUCUN'))\n"
        "print('ASSET_NOM=' + (asset.name if asset else 'AUCUN'))"
    )
    correspondance = re.search(r'ASSET_UUID=(\S+)', sortie)
    if not correspondance or correspondance.group(1) == 'AUCUN':
        pytest.fail(
            "Aucune monnaie locale fiduciaire (AssetFedowPublic categorie TLF) "
            "sur ce tenant : tout le parcours de ce fichier en depend. Un tenant "
            "sans monnaie doit rendre le test ROUGE — un skip laisserait croire "
            "que le parcours monnaie locale est verifie."
        )

    nom = re.search(r'ASSET_NOM=(.+)', sortie)
    return {
        'uuid': correspondance.group(1),
        'nom': nom.group(1).strip() if nom else '',
    }


@pytest.fixture
def adherent_credite(django_shell, monnaie_locale_du_lieu):
    """Un adherent tout neuf, credite en monnaie locale par le vrai Fedow.

    Le credit passe par `refill_from_lespass_to_user_wallet` : le lieu envoie
    de sa monnaie vers le portefeuille de l'adherent. C'est la seule facon de
    provisionner un portefeuille sans passer par un paiement bancaire.
    / The credit goes through refill_from_lespass_to_user_wallet: the venue
    sends its currency to the member's wallet. The only way to fund a wallet
    without a bank payment.
    """
    adresse = f'e2e-fedow-{uuid_module.uuid4().hex[:8]}@tibillet.test'

    # Le Fedow reel EXIGE `ligne_article_uuid` dans les metadonnees d'une
    # recharge, et `rewarded_from_ticket_scanned` pour contourner sa validation
    # de vente (une recharge directe n'a pas de vente derriere elle). C'est le
    # meme contrat que respecte l'API v2 de recharge — un Fedow simule, lui,
    # accepterait n'importe quoi.
    # / The real Fedow REQUIRES ligne_article_uuid in a refill's metadata, plus
    # rewarded_from_ticket_scanned to bypass its sale validation. Same contract
    # the v2 refill API follows; a simulated Fedow would accept anything.
    sortie = django_shell(
        "from AuthBillet.utils import get_or_create_user\n"
        "from BaseBillet.models import (LigneArticle, PaymentMethod, Price, PriceSold,\n"
        "                               Product, ProductSold, SaleOrigin)\n"
        "from fedow_connect.fedow_api import FedowAPI\n"
        "from fedow_public.models import AssetFedowPublic\n"
        f"user = get_or_create_user('{adresse}', send_mail=False)\n"
        "user.email_valid = True\n"
        "user.save()\n"
        f"asset = AssetFedowPublic.objects.get(uuid='{monnaie_locale_du_lieu['uuid']}')\n"
        "produit, _c = Product.objects.get_or_create(\n"
        "    name='E2E recharge parcours fedow',\n"
        "    categorie_article=Product.RECHARGE_CASHLESS)\n"
        "tarif, _c = Price.objects.get_or_create(product=produit, name='E2E', prix=0)\n"
        "produit_vendu, _c = ProductSold.objects.get_or_create(product=produit)\n"
        "tarif_vendu, _c = PriceSold.objects.get_or_create(\n"
        "    productsold=produit_vendu, price=tarif, defaults={'prix': 0})\n"
        "ligne = LigneArticle.objects.create(\n"
        f"    pricesold=tarif_vendu, qty=1, amount={MONTANT_DE_LA_VENTE_CENTIMES * 2},\n"
        "    payment_method=PaymentMethod.FREE, status=LigneArticle.VALID,\n"
        "    sale_origin=SaleOrigin.API, asset=asset.uuid)\n"
        "api = FedowAPI()\n"
        "api.wallet.get_or_create_wallet(user)\n"
        "api.transaction.refill_from_lespass_to_user_wallet(\n"
        f"    user=user, amount={MONTANT_DE_LA_VENTE_CENTIMES * 2}, asset=asset,\n"
        "    metadata={'reason': 'E2E parcours fedow',\n"
        "              'ligne_article_uuid': str(ligne.uuid),\n"
        "              'rewarded_from_ticket_scanned': True},\n"
        ")\n"
        "user.refresh_from_db()\n"
        "print('SOLDE=' + str(api.wallet.get_total_fiducial_and_all_federated_token(user, use_cache=False)))"
    )

    solde = re.search(r'SOLDE=(\d+)', sortie)
    if not solde or int(solde.group(1)) < MONTANT_DE_LA_VENTE_CENTIMES:
        pytest.fail(
            f"Le credit n'a pas abouti sur le Fedow reel. Sortie : {sortie[-400:]}"
        )

    return {'email': adresse, 'solde_initial': int(solde.group(1))}


def _solde_federe(django_shell, email):
    """Le solde en monnaie federee d'un adherent, lu sur le Fedow reel.
    / A member's federated balance, read from the real Fedow."""
    sortie = django_shell(
        "from AuthBillet.models import TibilletUser\n"
        "from fedow_connect.fedow_api import FedowAPI\n"
        f"user = TibilletUser.objects.get(email='{email}')\n"
        "api = FedowAPI()\n"
        "print('SOLDE=' + str(api.wallet.get_total_fed_token(user)))"
    )
    trouve = re.search(r'SOLDE=(\d+)', sortie)
    return int(trouve.group(1)) if trouve else 0


def _solde_du_lieu(django_shell, uuid_asset):
    """Ce que le lieu detient de cette monnaie, lu sur le Fedow reel.
    / What the venue holds of this currency, read from the real Fedow."""
    sortie = django_shell(
        "import json\n"
        "from fedow_connect.fedow_api import FedowAPI\n"
        "api = FedowAPI()\n"
        f"donnees = api.asset.total_by_place_with_uuid(uuid='{uuid_asset}')\n"
        "donnees = json.loads(donnees) if isinstance(donnees, (str, bytes)) else (donnees or {})\n"
        "total = sum(l.get('total_value', 0) for l in donnees.get('total_by_place', []))\n"
        "print('TOTAL_LIEUX=' + str(total))"
    )
    trouve = re.search(r'TOTAL_LIEUX=(\d+)', sortie)
    return int(trouve.group(1)) if trouve else 0


# ---------------------------------------------------------------------------
# Le parcours en monnaie locale
# ---------------------------------------------------------------------------


def test_vente_en_monnaie_locale_puis_remise_en_banque(
    page, login_as, login_as_admin, admin_email, django_shell,
    monnaie_locale_du_lieu, adherent_credite,
):
    """Le parcours entier contre le Fedow reel.

    Chaque etape lit l'etat que la precedente a laisse SUR LE FEDOW, pas dans
    une variable de test. Si le Fedow ne debite pas, ne credite pas, ou ne
    retient pas la remise, une des assertions tombe.
    / Every step reads the state the previous one left ON THE FEDOW, not in a
    test variable.
    """
    uuid_asset = monnaie_locale_du_lieu['uuid']

    # --- 1. L'encaisseur genere un QR code ---
    login_as_admin(page)
    page.goto('/my_account/')
    reponse = _poster(page, '/qrcodescanpay/generate_qrcode/', {
        'amount': str(MONTANT_DE_LA_VENTE_CENTIMES / 100),
        'asset_type': 'EURO',
    })
    assert reponse.ok, f"Generation refusee : {reponse.status} {reponse.text()[:300]}"

    sortie = django_shell(
        "from BaseBillet.models import LigneArticle, SaleOrigin\n"
        "ligne = LigneArticle.objects.filter("
        "    sale_origin=SaleOrigin.QRCODE_MA, status=LigneArticle.CREATED"
        ").order_by('-datetime').first()\n"
        "print('LIGNE=' + (ligne.uuid.hex if ligne else 'AUCUNE'))"
    )
    trouve = re.search(r'LIGNE=(\S+)', sortie)
    assert trouve and trouve.group(1) != 'AUCUNE', "Le QR code n'a produit aucune demande."
    uuid_de_la_demande = trouve.group(1)

    solde_du_lieu_avant = _solde_du_lieu(django_shell, uuid_asset)

    # --- 2. L'adherent paie ---
    login_as(page, adherent_credite['email'])
    page.goto('/my_account/')
    reponse = _poster(page, '/qrcodescanpay/valid_payment/', {
        'ligne_article_uuid_hex': uuid_de_la_demande,
    })
    assert reponse.ok, f"Paiement refuse : {reponse.status} {reponse.text()[:300]}"

    # --- 3. Le Fedow reel a debite l'adherent ---
    sortie = django_shell(
        "from AuthBillet.models import TibilletUser\n"
        "from fedow_connect.fedow_api import FedowAPI\n"
        f"user = TibilletUser.objects.get(email='{adherent_credite['email']}')\n"
        "api = FedowAPI()\n"
        "print('SOLDE=' + str(api.wallet.get_total_fiducial_and_all_federated_token(user, use_cache=False)))"
    )
    solde_apres = int(re.search(r'SOLDE=(\d+)', sortie).group(1))
    assert solde_apres == adherent_credite['solde_initial'] - MONTANT_DE_LA_VENTE_CENTIMES, (
        f"Le Fedow n'a pas debite le bon montant : "
        f"{adherent_credite['solde_initial']} → {solde_apres}"
    )

    # --- 4. La vente est enregistree cote Lespass ---
    sortie = django_shell(
        "from BaseBillet.models import LigneArticle\n"
        f"ligne = LigneArticle.objects.filter(uuid='{uuid_de_la_demande}').first()\n"
        "print('STATUT=' + (ligne.status if ligne else 'ABSENTE'))\n"
        "print('MOYEN=' + (ligne.payment_method if ligne else 'ABSENT'))"
    )
    assert 'STATUT=V' in sortie, f"La vente n'est pas validee : {sortie[-300:]}"

    # --- 5. Le lieu detient la monnaie encaissee ---
    solde_du_lieu_apres_vente = _solde_du_lieu(django_shell, uuid_asset)
    assert solde_du_lieu_apres_vente >= solde_du_lieu_avant + MONTANT_DE_LA_VENTE_CENTIMES, (
        "Le Fedow n'a pas credite le lieu du montant encaisse."
    )

    # --- 6. Le gestionnaire voit la monnaie dans la ventilation ---
    login_as_admin(page)
    page.goto(f'/fedow/asset/{uuid_asset}/retrieve_bank_deposits/')
    assert page.locator('body').inner_text(), "La page des remises est vide."
    contenu_avant_remise = page.content()

    # --- 7. Il declenche la remise en banque ---
    sortie = django_shell(
        "from fedow_connect.models import FedowConfig\n"
        "print('WALLET_LIEU=' + str(FedowConfig.get_solo().fedow_place_wallet_uuid))"
    )
    wallet_du_lieu = re.search(r'WALLET_LIEU=(\S+)', sortie).group(1)

    reponse = _poster(
        page,
        f'/admin/fedow_public/assetfedowpublic/bank_deposit/{uuid_asset}/{wallet_du_lieu}/',
        {},
    )
    # Le code de retour ne dit RIEN du sort de la remise : la vue attrape les
    # erreurs du Fedow, pose un message, et renvoie dans tous les cas une
    # redirection HTMX. S'y fier laisserait passer une remise refusee.
    # / The status code says NOTHING about the deposit's fate: the view catches
    # Fedow errors, posts a message, and always returns an HTMX redirect.
    assert reponse.status in (200, 204, 302), (
        f"La remise en banque n'a meme pas abouti a la vue : "
        f"{reponse.status} {reponse.text()[:300]}"
    )

    # --- 8. Le Fedow reel a vide le portefeuille du lieu ---
    #
    # Le Fedow enregistre la remise puis recalcule ses totaux : la ventilation
    # peut mettre un instant a refleter la decrementation. On interroge donc
    # jusqu'a la voir, plutot que de parier sur un delai fixe.
    # / The Fedow records the deposit then recomputes its totals: the breakdown
    # may take a moment to reflect it. Poll instead of betting on a fixed delay.
    solde_du_lieu_apres_remise = solde_du_lieu_apres_vente
    for _tentative in range(10):
        solde_du_lieu_apres_remise = _solde_du_lieu(django_shell, uuid_asset)
        if solde_du_lieu_apres_remise < solde_du_lieu_apres_vente:
            break
        time.sleep(2)

    if solde_du_lieu_apres_remise >= solde_du_lieu_apres_vente:
        # La remise a echoue : le message pose par la vue dit pourquoi. Sans lui,
        # l'echec se resume a deux nombres identiques, et on ne sait pas si le
        # Fedow a refuse, si le portefeuille vise est le mauvais, ou si rien n'est
        # parti du tout.
        # / The deposit failed: the message posted by the view says why. Without
        # it, the failure is just two equal numbers.
        page.goto(f'/fedow/asset/{uuid_asset}/retrieve_bank_deposits/')
        message_affiche = page.locator('body').inner_text()[:500]
        pytest.fail(
            f"La remise n'a rien decremente cote Fedow : "
            f"{solde_du_lieu_apres_vente} → {solde_du_lieu_apres_remise}.\n"
            f"Portefeuille vise : {wallet_du_lieu}\n"
            f"Page apres remise : {message_affiche}"
        )

    # --- 9. La remise apparait dans l'historique affiche ---
    page.goto(f'/fedow/asset/{uuid_asset}/retrieve_bank_deposits/')
    contenu_apres_remise = page.content()
    assert contenu_apres_remise != contenu_avant_remise, (
        "La page affiche exactement la meme chose avant et apres la remise."
    )

    texte_de_la_page = page.locator('body').inner_text()
    assert 'Aucune remise en banque trouvée' not in texte_de_la_page, (
        "L'historique reste vide alors qu'une remise vient d'aboutir."
    )


def test_le_releve_de_transactions_repond_sur_le_fedow_reel(
    page, login_as_admin, monnaie_locale_du_lieu,
):
    """Le relevé d'une periode interroge vraiment le Fedow et rend un tableau.

    Ce test ne modifie rien : il verifie seulement que la route de relevé sait
    dialoguer avec le Fedow reel, ce que le fichier pytest ne peut pas prouver.
    / This test modifies nothing: it only checks the statement route can talk to
    the real Fedow, which the pytest file cannot prove.
    """
    from datetime import datetime, timedelta

    login_as_admin(page)
    page.goto(f"/fedow/asset/{monnaie_locale_du_lieu['uuid']}/retrieve_bank_deposits/")

    maintenant = datetime.now()
    reponse = _poster(page, '/fedow/asset/retrieve_transactions/', {
        'asset_uuid': monnaie_locale_du_lieu['uuid'],
        'start_date': (maintenant - timedelta(days=30)).strftime('%Y-%m-%dT%H:%M'),
        'end_date': maintenant.strftime('%Y-%m-%dT%H:%M'),
    })

    assert reponse.ok, f"Le releve a echoue : {reponse.status} {reponse.text()[:300]}"


# ---------------------------------------------------------------------------
# Le parcours en monnaie federee, via un vrai paiement Stripe
# ---------------------------------------------------------------------------


@pytest.mark.stripe_listen
def test_recharge_federee_par_carte_bancaire(
    page, login_as, django_shell, fill_stripe_card, soumettre_paiement_stripe,
):
    """Recharger son portefeuille en monnaie federee par carte.

    C'est le seul moyen d'obtenir de la monnaie federee : elle s'achete, elle ne
    se cree pas. Le Fedow fabrique la demande de paiement, Stripe encaisse, et
    le webhook credite le portefeuille.

    RAPPEL : sans `stripe listen`, le webhook n'arrive jamais et le solde reste
    a zero — le test echouerait pour une raison sans rapport avec le code.

    / Federated currency is bought, not created. The Fedow builds the payment
    request, Stripe collects, and the webhook credits the wallet. WITHOUT
    `stripe listen` the webhook never arrives.
    """
    adresse = f'e2e-fed-{uuid_module.uuid4().hex[:8]}@tibillet.test'
    django_shell(
        "from AuthBillet.utils import get_or_create_user\n"
        f"user = get_or_create_user('{adresse}', send_mail=False)\n"
        "user.email_valid = True\n"
        "user.save()"
    )

    login_as(page, adresse)
    page.goto('/my_account/balance/')

    # Il FAUT cliquer le bouton, et surtout pas viser la route directement :
    # `refill_wallet` ne renvoie pas une redirection HTTP mais un en-tete
    # `HX-Redirect`, que seul htmx sait suivre. Un `goto` sur cette route recoit
    # un 200 vide et n'arrive jamais chez Stripe.
    # / The button MUST be clicked: refill_wallet returns an HX-Redirect header,
    # not an HTTP redirect. Only htmx follows it; a direct goto gets an empty 200.
    # Solde AVANT : le point de comparaison. Sans lui, un solde positif a la fin
    # ne prouverait pas que c'est cette recharge qui l'a produit.
    # / Balance BEFORE: without it, a positive balance at the end would not prove
    # this refill produced it.
    solde_avant = _solde_federe(django_shell, adresse)

    bouton_de_recharge = page.locator('[hx-get="/my_account/refill_wallet"]')
    assert bouton_de_recharge.count() > 0, (
        "Le bouton de recharge est absent de la page solde. "
        "Verifier `Configuration.show_refill_button()` sur ce tenant."
    )
    bouton_de_recharge.first.click()

    page.wait_for_url(
        lambda url: 'checkout.stripe.com' in url,
        timeout=20_000,
        # Stripe garde des connexions ouvertes : `networkidle` n'y arrive jamais.
        # / Stripe keeps connections open: networkidle never settles there.
        wait_until='domcontentloaded',
    )

    # `fill_stripe_card` (conftest) sait deplier l'accordeon des moyens de
    # paiement, attendre le montage du formulaire React et remplir la carte de
    # test. Reecrire ces selecteurs a la main casse a chaque evolution de
    # Stripe Checkout.
    # / fill_stripe_card knows how to expand the payment-method accordion, wait
    # for the React form to mount and fill the test card.
    # Le formulaire est monte par React APRES l'arrivee sur la page : viser un
    # champ trop tot ne trouve rien du tout.
    # / The form is mounted by React AFTER arrival: targeting a field too early
    # finds nothing at all.
    champ_montant = page.locator('input#customUnitAmount')
    champ_montant.wait_for(state='visible', timeout=30_000)
    champ_montant.fill(MONTANT_DE_LA_RECHARGE_EUROS)

    fill_stripe_card(page, adresse)

    # Le nom du porteur est OBLIGATOIRE sur ce checkout : sans lui, Stripe
    # refuse la soumission SANS quitter la page (le clic sur « payer » ne
    # produit rien de visible). Or `fill_stripe_card` ne le remplit que si le
    # champ est deja monte a son passage — sur ce checkout fabrique par Fedow,
    # React le monte parfois apres. On le garantit donc ici, explicitement.
    # / The cardholder name is REQUIRED on this checkout: without it, Stripe
    # rejects the submission WITHOUT leaving the page. fill_stripe_card only
    # fills it if the field is already mounted when it runs — on this
    # Fedow-built checkout, React sometimes mounts it later. Guarantee it here.
    champ_nom_du_porteur = page.locator('input#billingName')
    champ_nom_du_porteur.wait_for(state='visible', timeout=30_000)
    if not champ_nom_du_porteur.input_value():
        champ_nom_du_porteur.fill('Douglas Adams')

    # `fill_stripe_card` REMPLIT la carte, elle ne soumet pas : la soumission
    # reste a la charge de l'appelant.
    # / fill_stripe_card FILLS the card but does not submit.
    #
    # La soumission demande de l'insistance sur ce checkout : voir la fixture
    # `soumettre_paiement_stripe` (conftest) et PIEGES 12.14.
    # / Submitting takes persistence here: see the fixture and PIEGES 12.14.
    soumettre_paiement_stripe(page)

    # On quitte la page de paiement — sans presumer de la destination : c'est
    # Fedow qui a fabrique ce checkout, donc c'est lui qui fixe l'adresse de
    # retour, et elle ne ramene pas forcement sur Lespass.
    # / Leave the payment page without assuming the destination: Fedow built this
    # checkout, so Fedow sets the return address.
    page.wait_for_url(
        lambda url: 'checkout.stripe.com' not in url,
        timeout=60_000,
        wait_until='domcontentloaded',
    )

    # Le credit arrive par le webhook, donc de facon asynchrone : on interroge
    # le solde en boucle plutot que de parier sur un delai fixe. Meme approche
    # que test_membership_manual_validation_stripe.py.
    # / The credit arrives via the webhook, asynchronously: poll the balance
    # instead of betting on a fixed delay.
    solde_credite = solde_avant
    for _tentative in range(20):
        solde_credite = _solde_federe(django_shell, adresse)
        if solde_credite != solde_avant:
            break
        time.sleep(3)

    assert solde_credite == solde_avant + MONTANT_DE_LA_RECHARGE_CENTIMES, (
        f"Le Fedow n'a pas credite le montant saisi. "
        f"Avant : {solde_avant}, apres : {solde_credite}, "
        f"attendu : {solde_avant + MONTANT_DE_LA_RECHARGE_CENTIMES}. "
        "Si le solde n'a pas bouge du tout, la cause la plus probable est que "
        "`stripe listen` ne tourne pas : le webhook de confirmation n'est alors "
        "jamais parvenu au Fedow."
    )
