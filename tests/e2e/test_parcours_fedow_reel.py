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
  attente. Sans lui, le parcours Stripe echoue des sa preparation.

Lancement / Run (`stripe listen` doit tourner dans byobu) :
    make e2e ARGS="tests/e2e/test_parcours_fedow_reel.py -v"
"""

import json
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
    # La ligne payee ne porte pas de moyen (Q-H2) : le moyen se lit sur les
    # reglements de sa vente. Il est affiche pour le diagnostic.
    # / The paid line has no method (Q-H2): read it on its sale's payments.
    sortie = django_shell(
        "from BaseBillet.models import LigneArticle\n"
        f"ligne = LigneArticle.objects.filter(uuid='{uuid_de_la_demande}').first()\n"
        "print('STATUT=' + (ligne.status if ligne else 'ABSENTE'))\n"
        "moyens = []\n"
        "if ligne and ligne.vente_id:\n"
        "    for reglement in ligne.vente.reglements.all():\n"
        "        moyens.append(reglement.moyen)\n"
        "print('MOYEN=' + (','.join(sorted(moyens)) if moyens else 'ABSENT'))"
    )
    assert 'STATUT=V' in sortie, f"La vente n'est pas validee : {sortie[-300:]}"

    # --- 5. Le lieu detient la monnaie encaissee ---
    #
    # Le Fedow enregistre la transaction puis recalcule sa ventilation par lieu :
    # celle-ci peut mettre un instant a refleter l'encaissement. On interroge donc
    # jusqu'a la voir, plutot que de parier sur un delai fixe — meme precaution
    # que pour la remise en banque a l'etape 8. Une lecture unique passe quand le
    # fichier est lance seul et echoue en suite, ou le Fedow est plus sollicite.
    # / The Fedow records the transaction then recomputes its per-venue breakdown,
    # which may lag. Poll instead of betting on a fixed delay — same precaution as
    # step 8. A single read passes in isolation and fails in a full suite.
    attendu_pour_le_lieu = solde_du_lieu_avant + MONTANT_DE_LA_VENTE_CENTIMES
    solde_du_lieu_apres_vente = solde_du_lieu_avant
    for _tentative in range(10):
        solde_du_lieu_apres_vente = _solde_du_lieu(django_shell, uuid_asset)
        if solde_du_lieu_apres_vente >= attendu_pour_le_lieu:
            break
        time.sleep(2)

    assert solde_du_lieu_apres_vente >= attendu_pour_le_lieu, (
        f"Le Fedow n'a pas credite le lieu du montant encaisse : "
        f"{solde_du_lieu_avant} → {solde_du_lieu_apres_vente}, "
        f"attendu au moins {attendu_pour_le_lieu}."
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


def _recharger_en_monnaie_federee_par_carte_bancaire(
    page, login_as, django_shell, fill_stripe_card, soumettre_paiement_stripe,
):
    """Un adherent tout neuf recharge son portefeuille en monnaie federee par carte.

    C'est le seul moyen d'obtenir de la monnaie federee : elle s'achete, elle ne
    se cree pas. Le Fedow fabrique la demande de paiement, Stripe encaisse, et
    le webhook credite le portefeuille. `refill_from_lespass_to_user_wallet` ne
    peut pas la donner : le Fedow n'y accepte que les monnaies du lieu.

    L'assistant ne verifie rien : il rend le solde avant et le solde lu apres
    l'attente du webhook. C'est a l'appelant de les comparer.

    RAPPEL : sans `stripe listen`, le webhook n'arrive jamais et le solde reste
    a zero.

    / A fresh member tops up their wallet in federated currency by card. The
    only way to get it: it is bought, not created. The helper checks nothing: it
    returns the balance before and the balance read after waiting for the webhook.

    :return: dict {'email', 'solde_avant', 'solde_credite'} en centimes
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

    return {
        'email': adresse,
        'solde_avant': solde_avant,
        'solde_credite': solde_credite,
    }


def _verifier_que_la_recharge_federee_est_creditee(recharge):
    """Le Fedow a credite exactement le montant saisi sur la page Stripe.
    / The Fedow credited exactly the amount typed on the Stripe page."""
    solde_avant = recharge['solde_avant']
    solde_credite = recharge['solde_credite']
    assert solde_credite == solde_avant + MONTANT_DE_LA_RECHARGE_CENTIMES, (
        f"Le Fedow n'a pas credite le montant saisi. "
        f"Avant : {solde_avant}, apres : {solde_credite}, "
        f"attendu : {solde_avant + MONTANT_DE_LA_RECHARGE_CENTIMES}. "
        "Si le solde n'a pas bouge du tout, la cause la plus probable est que "
        "`stripe listen` ne tourne pas : le webhook de confirmation n'est alors "
        "jamais parvenu au Fedow."
    )


@pytest.mark.stripe_listen
def test_recharge_federee_par_carte_bancaire(
    page, login_as, django_shell, fill_stripe_card, soumettre_paiement_stripe,
):
    """Recharger son portefeuille en monnaie federee par carte.

    Le Fedow fabrique la demande de paiement, Stripe encaisse, et le webhook
    credite le portefeuille.

    RAPPEL : sans `stripe listen`, le webhook n'arrive jamais et le solde reste
    a zero — le test echouerait pour une raison sans rapport avec le code.

    / The Fedow builds the payment request, Stripe collects, and the webhook
    credits the wallet. WITHOUT `stripe listen` the webhook never arrives.
    """
    recharge = _recharger_en_monnaie_federee_par_carte_bancaire(
        page, login_as, django_shell, fill_stripe_card, soumettre_paiement_stripe,
    )
    _verifier_que_la_recharge_federee_est_creditee(recharge)


# ---------------------------------------------------------------------------
# La caisse encaisse les monnaies de l'ancien Fedow
# ---------------------------------------------------------------------------
#
# Le systeme est hybride. Une carte peut porter deux sortes de monnaie :
# - celles du moteur local (`fedow_core`), dans la base du lieu ;
# - celles de l'ancien Fedow, distant : la monnaie federee (FED) et la monnaie
#   locale du lieu qui y vit encore (TLF).
# Quand le moteur local ne couvre pas le panier, la caisse se tourne vers l'ancien
# Fedow (`lire_depensable_fed_frais`, puis `_debiter_legacy` qui appelle
# `to_place_from_qrcode`). Chaque transaction distante devient un reglement de la
# vente : son uuid va dans `reference_externe`, jamais dans `fedow_transaction_uuid`
# (reserve aux transactions du moteur local).
# / The system is hybrid. When the local engine does not cover the cart, the POS
# turns to the old remote Fedow. Each remote transaction becomes a payment of the
# sale: its uuid goes to reference_externe, never to fedow_transaction_uuid.

# Le point de vente et l'article de ces tests. L'article vaut exactement le montant
# du parcours : la recharge federee (3 €) et le credit en monnaie locale (5 €) le
# couvrent tous les deux.
# / The POS and item of these tests. The item costs exactly the journey amount.
NOM_DU_COMPTOIR_DE_L_ANCIEN_FEDOW = 'Comptoir ancien Fedow E2E'
NOM_DE_L_ARTICLE_DE_L_ANCIEN_FEDOW = 'Sirop E2E ancien Fedow'

# La carte primaire du caissier, seedee par `create_test_pos_data`.
# / The cashier's primary card, seeded by create_test_pos_data.
TAG_DE_LA_CARTE_PRIMAIRE = 'A49E8E2A'

# Les cartes client, une par test. `CarteCashless.tag_id` est limite a 8
# caracteres (PIEGES 9.31). Elles sont reutilisees d'un passage a l'autre mais
# rattachees a un adherent NEUF a chaque fois.
# / Client cards, one per test (8 chars max), re-attached to a FRESH member.
TAG_DE_LA_CARTE_EN_MONNAIE_FEDEREE = 'E2EFED01'
TAG_DE_LA_CARTE_EN_MONNAIE_LOCALE = 'E2ETLF01'


def _lire_json_marque(sortie, marqueur):
    """Extrait le JSON imprime par le shell Django derriere un marqueur.

    Le shell melange le JSON attendu avec les journaux applicatifs : on repere la
    ligne par un marqueur explicite.
    / Extracts the JSON printed by the Django shell behind an explicit marker.
    """
    for ligne in sortie.splitlines():
        if ligne.startswith(marqueur):
            return json.loads(ligne[len(marqueur):])
    pytest.fail(
        f"Le shell Django n'a rien imprime derriere '{marqueur}'. "
        f"Sortie : {sortie[-800:]}"
    )


@pytest.fixture(scope='module')
def comptoir_de_l_ancien_fedow(django_shell, ensure_pos_data):
    """Cree (ou retrouve) un point de vente et un article a 2,50 € payable en carte.

    Le point de vente est propre a ces tests : aucun autre test n'y vend, et la
    carte primaire du caissier y a acces.
    / Creates (or finds) a POS and a 2.50 € item, reserved to these tests.
    """
    prix_en_euros = f'{MONTANT_DE_LA_VENTE_CENTIMES / 100:.2f}'
    sortie = django_shell(
        "import json\n"
        "from decimal import Decimal\n"
        "from BaseBillet.models import Price, Product\n"
        "from laboutik.models import CartePrimaire, PointDeVente\n"
        "pv, _cree = PointDeVente.objects.get_or_create(\n"
        f"    name='{NOM_DU_COMPTOIR_DE_L_ANCIEN_FEDOW}',\n"
        "    defaults={'comportement': PointDeVente.DIRECT, 'service_direct': True,\n"
        "              'accepte_especes': True, 'accepte_carte_bancaire': True})\n"
        "article, _cree = Product.objects.get_or_create(\n"
        f"    name='{NOM_DE_L_ARTICLE_DE_L_ANCIEN_FEDOW}',\n"
        "    defaults={'methode_caisse': Product.VENTE})\n"
        "tarif, _cree = Price.objects.get_or_create(\n"
        "    product=article, name='Verre',\n"
        f"    defaults={{'prix': Decimal('{prix_en_euros}')}})\n"
        "pv.products.add(article)\n"
        f"primaire = CartePrimaire.objects.filter(carte__tag_id='{TAG_DE_LA_CARTE_PRIMAIRE}').first()\n"
        "if primaire is not None:\n"
        "    primaire.points_de_vente.add(pv)\n"
        "print('COMPTOIR_JSON=' + json.dumps({\n"
        "    'pv_uuid': str(pv.uuid),\n"
        "    'article_uuid': str(article.uuid),\n"
        "    'tarif_uuid': str(tarif.uuid),\n"
        "    'tarif_centimes': int(round(tarif.prix * 100)),\n"
        "    'tarif_non_fiduciaire': bool(tarif.non_fiduciaire),\n"
        "    'primaire': primaire is not None,\n"
        "}))"
    )
    comptoir = _lire_json_marque(sortie, 'COMPTOIR_JSON=')

    if not comptoir['primaire']:
        pytest.fail(f"Carte primaire {TAG_DE_LA_CARTE_PRIMAIRE} introuvable (seed).")
    if comptoir['tarif_centimes'] != MONTANT_DE_LA_VENTE_CENTIMES or comptoir['tarif_non_fiduciaire']:
        pytest.fail(
            f"Le tarif de '{NOM_DE_L_ARTICLE_DE_L_ANCIEN_FEDOW}' n'est plus un prix "
            f"en euros de {MONTANT_DE_LA_VENTE_CENTIMES} centimes : {comptoir}. "
            "Quelqu'un l'a modifie dans la base de developpement."
        )
    return comptoir


def _rattacher_une_carte_a_l_adherent(django_shell, email, tag_de_la_carte):
    """Rattache la carte du test a l'adherent, apres l'avoir remise a zero.

    Le portefeuille est demande au Fedow (`get_or_create_wallet`) : c'est lui qui
    fait foi, et `_obtenir_ou_creer_wallet` rend `carte.user.wallet` des que la
    carte porte un adherent. La carte peut encore porter l'adherent du passage
    precedent : `reset_carte` la detache d'abord.
    / Attaches the test card to the member after resetting it. The wallet comes
    from the Fedow, the source of truth.
    """
    sortie = django_shell(
        "import json\n"
        "from AuthBillet.models import TibilletUser\n"
        "from BaseBillet.models import CarteCashless\n"
        "from fedow_connect.fedow_api import FedowAPI\n"
        "from laboutik.utils.test_helpers import reset_carte\n"
        f"user = TibilletUser.objects.get(email='{email}')\n"
        "FedowAPI().wallet.get_or_create_wallet(user)\n"
        "user.refresh_from_db()\n"
        f"reset_carte('{tag_de_la_carte}')\n"
        "carte, _cree = CarteCashless.objects.get_or_create(\n"
        f"    tag_id='{tag_de_la_carte}',\n"
        f"    defaults={{'number': '{tag_de_la_carte}'}})\n"
        "carte.user = user\n"
        "carte.save()\n"
        "print('CARTE_JSON=' + json.dumps({\n"
        "    'wallet_uuid': str(user.wallet.uuid) if user.wallet else None,\n"
        "}))"
    )
    carte = _lire_json_marque(sortie, 'CARTE_JSON=')
    if not carte['wallet_uuid']:
        pytest.fail(
            "L'adherent n'a pas de portefeuille : le Fedow n'a pas repondu. "
            "Verifier `FedowConfig.get_solo().can_fedow()`."
        )
    return carte


def _soldes_des_deux_moteurs_de_l_adherent(django_shell, email):
    """Ce que l'adherent detient, lu a la source dans chaque moteur.

    - `federe` et `locale_ancien_fedow` : ses jetons FED et TLF sur l'ancien
      Fedow, relus SANS cache (`retrieve_by_signature`) — le cache garderait la
      valeur d'avant la vente.
    - `jetons_locaux` : la somme de ses jetons du moteur local `fedow_core`.
    - `transactions_locales` : le nombre de transactions du moteur local dont son
      portefeuille est l'emetteur.
    / What the member holds, read at the source in each engine, without cache.
    """
    sortie = django_shell(
        "import json\n"
        "from AuthBillet.models import TibilletUser\n"
        "from fedow_connect.fedow_api import FedowAPI\n"
        "from fedow_core.models import Token, Transaction\n"
        f"user = TibilletUser.objects.get(email='{email}')\n"
        "portefeuille = FedowAPI().wallet.retrieve_by_signature(user).validated_data\n"
        "federe = 0\n"
        "locale_ancien_fedow = 0\n"
        "for jeton in portefeuille['tokens']:\n"
        "    if jeton['asset_category'] == 'FED':\n"
        "        federe += int(jeton['value'])\n"
        "    if jeton['asset_category'] == 'TLF':\n"
        "        locale_ancien_fedow += int(jeton['value'])\n"
        "jetons_locaux = 0\n"
        "for jeton_local in Token.objects.filter(wallet=user.wallet):\n"
        "    jetons_locaux += int(jeton_local.value)\n"
        "transactions_locales = Transaction.objects.filter(sender=user.wallet).count()\n"
        "print('SOLDES_JSON=' + json.dumps({\n"
        "    'federe': federe,\n"
        "    'locale_ancien_fedow': locale_ancien_fedow,\n"
        "    'jetons_locaux': jetons_locaux,\n"
        "    'transactions_locales': transactions_locales,\n"
        "}))"
    )
    return _lire_json_marque(sortie, 'SOLDES_JSON=')


def _payer_l_article_en_nfc(page, pos_page, comptoir, tag_de_la_carte):
    """Le caissier ouvre la caisse et encaisse l'article avec la carte du client.

    On ouvre la vraie interface pour poser la session et le cookie CSRF, puis on
    envoie le formulaire de paiement a la vraie route, avec une cle d'idempotence
    comme le fait l'ecran des moyens de paiement. Cette cle devient la cle de la
    vente (`Vente.idempotency_key`) : c'est elle qui la retrouve en base.
    / The cashier opens the POS and charges the item with the client's card. The
    idempotency key becomes the sale's key: it finds the sale in the database.

    :return: tuple (reponse, cle_du_paiement)
    """
    pos_page(page, NOM_DU_COMPTOIR_DE_L_ANCIEN_FEDOW)
    tuile_de_l_article = page.locator(f'[data-testid="article-{comptoir["article_uuid"]}"]')
    assert tuile_de_l_article.count() > 0, (
        f"L'article '{NOM_DE_L_ARTICLE_DE_L_ANCIEN_FEDOW}' n'apparait pas dans la "
        f"grille du point de vente '{NOM_DU_COMPTOIR_DE_L_ANCIEN_FEDOW}'."
    )

    cle_du_paiement = str(uuid_module.uuid4())
    reponse = _poster(page, '/laboutik/paiement/payer/', {
        'moyen_paiement': 'nfc',
        'total': str(MONTANT_DE_LA_VENTE_CENTIMES),
        'given_sum': '0',
        'uuid_pv': comptoir['pv_uuid'],
        'tag_id_cm': TAG_DE_LA_CARTE_PRIMAIRE,
        'tag_id': tag_de_la_carte,
        'cle_idempotence_paiement': cle_du_paiement,
        f"repid-{comptoir['article_uuid']}--{comptoir['tarif_uuid']}": '1',
    })
    return reponse, cle_du_paiement


def _lire_la_vente_et_ses_transactions(django_shell, cle_du_paiement):
    """La vente du paiement, ses reglements, et chaque transaction relue sur l'ancien Fedow.

    Pour chaque reglement qui porte une `reference_externe`, on redemande la
    transaction au Fedow (`transaction/<uuid>`) : son existence, son montant, sa
    nature, son emetteur et sa monnaie viennent du Fedow, pas de la base du lieu.
    / The sale, its payments, and each transaction read back from the old Fedow.
    """
    sortie = django_shell(
        "import json\n"
        "from BaseBillet.models import LigneArticle\n"
        "from BaseBillet.models_vente import Reglement, Vente\n"
        "from BaseBillet.services_vente import MOYENS_OFFERTS\n"
        "from fedow_connect.fedow_api import FedowAPI\n"
        "from fedow_connect.models import FedowConfig\n"
        f"vente = Vente.objects.filter(idempotency_key='{cle_du_paiement}').first()\n"
        "resultat = {'trouvee': vente is not None}\n"
        "if vente is not None:\n"
        "    api = FedowAPI()\n"
        "    somme_catalogue = 0\n"
        "    somme_nets = 0\n"
        "    for ligne in LigneArticle.objects.filter(vente=vente):\n"
        "        somme_catalogue += ligne.total_catalogue\n"
        "        somme_nets += ligne.total_ttc\n"
        "    reglements = []\n"
        "    somme_reglements = 0\n"
        "    somme_reglements_hors_offert = 0\n"
        "    for reglement in Reglement.objects.filter(vente=vente).order_by('datetime'):\n"
        "        somme_reglements += reglement.montant\n"
        "        if reglement.moyen not in MOYENS_OFFERTS:\n"
        "            somme_reglements_hors_offert += reglement.montant\n"
        "        transaction_distante = None\n"
        "        if reglement.reference_externe:\n"
        "            lue = api.transaction.retrieve(reglement.reference_externe)\n"
        "            if isinstance(lue, dict) and lue.get('uuid'):\n"
        "                monnaie = lue.get('serialized_asset') or {}\n"
        "                categorie = monnaie.get('category')\n"
        "                if not categorie:\n"
        "                    categorie = api.asset.retrieve(str(lue['asset']))['category']\n"
        "                transaction_distante = {\n"
        "                    'uuid': str(lue['uuid']),\n"
        "                    'montant': int(lue['amount']),\n"
        "                    'action': lue['action'],\n"
        "                    'emetteur': str(lue['sender']),\n"
        "                    'destinataire': str(lue['receiver']),\n"
        "                    'categorie': categorie,\n"
        "                    'uuid_transaction_caisse': (lue.get('metadata') or {}).get('uuid_transaction'),\n"
        "                }\n"
        "        reglements.append({\n"
        "            'moyen': reglement.moyen,\n"
        "            'montant': reglement.montant,\n"
        "            'reference_externe': reglement.reference_externe,\n"
        "            'fedow_transaction_uuid': str(reglement.fedow_transaction_uuid) if reglement.fedow_transaction_uuid else None,\n"
        "            'transaction_distante': transaction_distante,\n"
        "        })\n"
        "    resultat.update({\n"
        "        'statut': vente.statut,\n"
        "        'numero': vente.numero,\n"
        "        'somme_catalogue': somme_catalogue,\n"
        "        'somme_nets': somme_nets,\n"
        "        'somme_reglements': somme_reglements,\n"
        "        'somme_reglements_hors_offert': somme_reglements_hors_offert,\n"
        "        'reglements': reglements,\n"
        "        'wallet_du_lieu': str(FedowConfig.get_solo().fedow_place_wallet_uuid),\n"
        "    })\n"
        "print('VENTE_JSON=' + json.dumps(resultat))"
    )
    return _lire_json_marque(sortie, 'VENTE_JSON=')


def _verifier_la_vente_encaissee_par_l_ancien_fedow(
    vente, cle_du_paiement, wallet_de_l_adherent, moyen_attendu, categorie_attendue,
):
    """Les verifications communes aux deux monnaies de l'ancien Fedow.

    - la vente est REGLEE et numerotee ;
    - chaque reglement porte le moyen attendu, une `reference_externe` et aucun
      `fedow_transaction_uuid` ;
    - chaque `reference_externe` designe une transaction qui EXISTE sur l'ancien
      Fedow, du meme montant, de la bonne monnaie, faite par `to_place_from_qrcode`
      (action « QRS ») depuis le portefeuille de l'adherent vers celui du lieu,
      pour ce paiement-ci ;
    - les deux egalites de la vente.
    / Checks shared by both old-Fedow currencies.
    """
    assert vente['trouvee'], f"Aucune vente pour la cle du paiement {cle_du_paiement}."
    assert vente['statut'] == 'REGLEE', f"La vente n'est pas encaissee : {vente}"
    assert vente['numero'], f"La vente encaissee n'a pas de numero : {vente}"

    assert vente['reglements'], f"La vente n'a aucun reglement : {vente}"
    for reglement in vente['reglements']:
        assert reglement['moyen'] == moyen_attendu, (
            f"Reglement au moyen {reglement['moyen']}, attendu {moyen_attendu} : {reglement}"
        )
        assert reglement['fedow_transaction_uuid'] is None, (
            "Un reglement de l'ancien Fedow ne doit pas porter "
            f"`fedow_transaction_uuid` (reserve au moteur local) : {reglement}"
        )
        assert reglement['reference_externe'], (
            f"Le reglement ne dit pas quelle transaction de l'ancien Fedow il copie : {reglement}"
        )

        transaction_distante = reglement['transaction_distante']
        assert transaction_distante is not None, (
            f"La transaction {reglement['reference_externe']} n'existe pas sur "
            f"l'ancien Fedow : {reglement}"
        )
        assert transaction_distante['montant'] == reglement['montant'], (
            f"Le reglement ne copie pas le montant de sa transaction : {reglement}"
        )
        assert transaction_distante['categorie'] == categorie_attendue, (
            f"La transaction n'est pas en {categorie_attendue} : {reglement}"
        )
        assert transaction_distante['action'] == 'QRS', (
            "La transaction n'a pas ete faite par `to_place_from_qrcode` "
            f"(action QRS attendue) : {reglement}"
        )
        assert transaction_distante['emetteur'] == wallet_de_l_adherent, (
            f"La transaction ne part pas du portefeuille de l'adherent : {reglement}"
        )
        assert transaction_distante['destinataire'] == vente['wallet_du_lieu'], (
            f"La transaction n'arrive pas au portefeuille du lieu : {reglement}"
        )
        assert transaction_distante['uuid_transaction_caisse'] == cle_du_paiement, (
            f"La transaction ne vient pas de ce paiement : {reglement}"
        )

    assert vente['somme_reglements'] == vente['somme_catalogue'], (
        f"Somme des reglements != somme des totaux catalogue : {vente}"
    )
    assert vente['somme_reglements_hors_offert'] == vente['somme_nets'], (
        f"Somme des reglements hors offert != somme des nets vendus : {vente}"
    )
    assert vente['somme_catalogue'] == MONTANT_DE_LA_VENTE_CENTIMES, (
        f"La vente ne porte pas le prix de l'article : {vente}"
    )


def test_caisse_encaisse_la_monnaie_locale_de_l_ancien_fedow(
    page, pos_page, django_shell, adherent_credite, comptoir_de_l_ancien_fedow,
):
    """Une carte qui porte la monnaie locale du lieu sur l'ancien Fedow paie a la caisse.

    L'adherent est credite en monnaie locale (TLF) sur l'ancien Fedow, et n'a rien
    dans le moteur local. La caisse doit donc passer par l'ancien Fedow : un
    reglement « LE » par transaction distante.

    COMMENT ON PROUVE QUE LA CASCADE PASSE PAR L'ANCIEN FEDOW :
    - le solde TLF de l'ancien Fedow baisse du prix, et les jetons locaux restent a 0 ;
    - le moteur local n'a enregistre aucune transaction depuis ce portefeuille ;
    - le reglement porte l'uuid d'une transaction de l'ancien Fedow d'action
      « QRS », que seul `to_place_from_qrcode` produit, et dont les metadonnees
      portent la cle de ce paiement ; son `fedow_transaction_uuid` est vide.
    Le moyen seul ne suffit pas : une monnaie locale du moteur local donne aussi
    « LE ».

    CE QUE LE TEST LAISSE DERRIERE LUI : une vente encaissee, numerotee et
    chainee sur le lieu ; 2,50 € de monnaie locale passes de l'adherent au lieu
    sur l'ancien Fedow. Rien n'est annule.

    / A card holding the venue's local currency on the old Fedow pays at the POS.
    The proof that the cascade goes through the old Fedow: remote TLF drops, no
    local transaction, a remote QRS transaction carrying this payment's key.
    """
    email = adherent_credite['email']
    carte = _rattacher_une_carte_a_l_adherent(
        django_shell, email, TAG_DE_LA_CARTE_EN_MONNAIE_LOCALE,
    )

    # L'adherent n'a QUE de la monnaie locale de l'ancien Fedow.
    # / The member holds ONLY old-Fedow local currency.
    soldes_avant = _soldes_des_deux_moteurs_de_l_adherent(django_shell, email)
    assert soldes_avant['locale_ancien_fedow'] >= MONTANT_DE_LA_VENTE_CENTIMES, soldes_avant
    assert soldes_avant['federe'] == 0, soldes_avant
    assert soldes_avant['jetons_locaux'] == 0, soldes_avant
    assert soldes_avant['transactions_locales'] == 0, soldes_avant

    reponse, cle_du_paiement = _payer_l_article_en_nfc(
        page, pos_page, comptoir_de_l_ancien_fedow, TAG_DE_LA_CARTE_EN_MONNAIE_LOCALE,
    )
    assert reponse.ok, f"La caisse a refuse le paiement : {reponse.status} {reponse.text()[:400]}"

    soldes_apres = _soldes_des_deux_moteurs_de_l_adherent(django_shell, email)
    assert soldes_apres['locale_ancien_fedow'] == (
        soldes_avant['locale_ancien_fedow'] - MONTANT_DE_LA_VENTE_CENTIMES
    ), f"L'ancien Fedow n'a pas debite le prix : {soldes_avant} → {soldes_apres}"
    assert soldes_apres['jetons_locaux'] == 0, (
        f"Le moteur local a bouge : {soldes_avant} → {soldes_apres}"
    )
    assert soldes_apres['transactions_locales'] == 0, (
        f"Le moteur local a enregistre une transaction : {soldes_avant} → {soldes_apres}"
    )

    vente = _lire_la_vente_et_ses_transactions(django_shell, cle_du_paiement)
    _verifier_la_vente_encaissee_par_l_ancien_fedow(
        vente, cle_du_paiement, carte['wallet_uuid'],
        moyen_attendu='LE', categorie_attendue='TLF',
    )


@pytest.mark.stripe_listen
def test_caisse_encaisse_du_fed_de_l_ancien_fedow(
    page, login_as, pos_page, django_shell, fill_stripe_card, soumettre_paiement_stripe,
    comptoir_de_l_ancien_fedow,
):
    """Une carte qui porte de la monnaie federee (FED) sur l'ancien Fedow paie a la caisse.

    Le FED s'achete : l'adherent recharge d'abord 3 € par carte bancaire (vrai
    Stripe, `stripe listen` requis). Il n'a ni monnaie locale sur l'ancien Fedow,
    ni jeton dans le moteur local. La caisse doit donc prendre le FED : un
    reglement « SF » par transaction distante.

    CE QUE LE TEST LAISSE DERRIERE LUI : un paiement Stripe de test de 3 €, une
    vente encaissee, numerotee et chainee sur le lieu, 2,50 € de FED passes de
    l'adherent au lieu sur l'ancien Fedow (0,50 € reste a l'adherent). Rien n'est
    annule.

    / A card holding federated currency on the old Fedow pays at the POS. FED is
    bought first by card (real Stripe). One "SF" payment per remote transaction.
    """
    recharge = _recharger_en_monnaie_federee_par_carte_bancaire(
        page, login_as, django_shell, fill_stripe_card, soumettre_paiement_stripe,
    )
    _verifier_que_la_recharge_federee_est_creditee(recharge)
    email = recharge['email']

    carte = _rattacher_une_carte_a_l_adherent(
        django_shell, email, TAG_DE_LA_CARTE_EN_MONNAIE_FEDEREE,
    )

    # L'adherent n'a QUE du FED.
    # / The member holds ONLY FED.
    soldes_avant = _soldes_des_deux_moteurs_de_l_adherent(django_shell, email)
    assert soldes_avant['federe'] >= MONTANT_DE_LA_VENTE_CENTIMES, soldes_avant
    assert soldes_avant['locale_ancien_fedow'] == 0, soldes_avant
    assert soldes_avant['jetons_locaux'] == 0, soldes_avant
    assert soldes_avant['transactions_locales'] == 0, soldes_avant

    reponse, cle_du_paiement = _payer_l_article_en_nfc(
        page, pos_page, comptoir_de_l_ancien_fedow, TAG_DE_LA_CARTE_EN_MONNAIE_FEDEREE,
    )
    assert reponse.ok, f"La caisse a refuse le paiement : {reponse.status} {reponse.text()[:400]}"

    soldes_apres = _soldes_des_deux_moteurs_de_l_adherent(django_shell, email)
    assert soldes_apres['federe'] == soldes_avant['federe'] - MONTANT_DE_LA_VENTE_CENTIMES, (
        f"L'ancien Fedow n'a pas debite le FED du prix : {soldes_avant} → {soldes_apres}"
    )
    assert soldes_apres['jetons_locaux'] == 0, (
        f"Le moteur local a bouge : {soldes_avant} → {soldes_apres}"
    )
    assert soldes_apres['transactions_locales'] == 0, (
        f"Le moteur local a enregistre une transaction : {soldes_avant} → {soldes_apres}"
    )

    vente = _lire_la_vente_et_ses_transactions(django_shell, cle_du_paiement)
    _verifier_la_vente_encaissee_par_l_ancien_fedow(
        vente, cle_du_paiement, carte['wallet_uuid'],
        moyen_attendu='SF', categorie_attendue='FED',
    )


# ---------------------------------------------------------------------------
# La caisse vide une carte qui porte de l'argent sur l'ancien Fedow
# ---------------------------------------------------------------------------
#
# « Vider carte » vide la carte sur l'ancien Fedow (`POST card/refund`) PUIS sur le
# moteur local, et ecrit une vente `VIDAGE_CARTE` sans article : un reglement
# positif par transaction de remboursement d'argent (uuid distant dans
# `reference_externe`), puis un reglement especes de moins le total. La somme vaut 0.
# `card/refund` exige que la carte primaire du caissier soit une carte primaire du
# lieu CONNUE DE L'ANCIEN FEDOW (../Fedow/fedow_core/serializers.py,
# `CardRefundOrVoidValidator`) : ces tests le prouvent, ou le refutent.
# / "Empty card" empties the old Fedow first, then the local engine, and writes a
# VIDAGE_CARTE sale. card/refund requires a primary card known to the old Fedow.

# Adresse de l'apercu et du vidage (laboutik/urls.py, PaiementViewSet).
# / Preview and emptying addresses.
CHEMIN_DE_L_APERCU_DU_VIDAGE = '/laboutik/paiement/vider_carte/preview/'
CHEMIN_DU_VIDAGE_DE_CARTE = '/laboutik/paiement/vider_carte/'


def _la_carte_primaire_est_primaire_sur_l_ancien_fedow(django_shell):
    """La carte primaire du seed est-elle carte primaire du lieu sur l'ancien Fedow ?

    Lecture sans cache (`_get` direct sur `card/<tag>`) : le champ `is_primary` de la
    reponse brute dit si la carte est primaire POUR LE LIEU qui demande
    (../Fedow/fedow_core/serializers.py, `CardSerializer.get_is_primary`). Le
    validateur de `fedow_connect` ne le garde pas : on lit la reponse brute.
    / Is the seed primary card a primary card of the venue on the old Fedow? Raw,
    uncached read of `is_primary`.
    """
    sortie = django_shell(
        "import json\n"
        "from fedow_connect.fedow_api import _get\n"
        "from fedow_connect.models import FedowConfig\n"
        f"reponse = _get(FedowConfig.get_solo(), path='card/{TAG_DE_LA_CARTE_PRIMAIRE}')\n"
        "print('PRIMAIRE_JSON=' + json.dumps({\n"
        "    'statut': reponse.status_code,\n"
        "    'is_primary': reponse.json().get('is_primary') if reponse.status_code == 200 else None,\n"
        "}))"
    )
    etat = _lire_json_marque(sortie, 'PRIMAIRE_JSON=')
    if etat['statut'] != 200:
        pytest.fail(
            f"Carte primaire {TAG_DE_LA_CARTE_PRIMAIRE} illisible sur l'ancien Fedow : {etat}"
        )
    return bool(etat['is_primary'])


@pytest.fixture
def carte_primaire_declaree_a_l_ancien_fedow(django_shell):
    """La carte primaire du seed est declaree a l'ancien Fedow le temps du test, puis
    l'etat trouve est remis.

    CONTRAT : au debut, on lit si la carte est primaire du lieu sur l'ancien Fedow ;
    puis on la declare (`declarer_la_carte_primaire_a_l_ancien_fedow` ; une reponse
    208 « deja declaree » est normale). A la fin, on remet l'etat trouve : une carte
    qui n'etait pas primaire est retiree (`retirer_la_carte_primaire_de_l_ancien_fedow`) ;
    une carte qui l'etait n'est pas touchee. Les tests peuvent donc passer plusieurs
    fois de suite sans gener les autres.
    / The seed primary card is declared to the old Fedow for the test, then the state
    found is restored: withdrawn if it was not primary, untouched if it was.

    :return: True si la carte etait primaire au debut
    """
    etait_primaire_au_debut = _la_carte_primaire_est_primaire_sur_l_ancien_fedow(django_shell)
    django_shell(
        "from QrcodeCashless.models import CarteCashless\n"
        "from laboutik.carte_primaire_ancien_fedow import declarer_la_carte_primaire_a_l_ancien_fedow\n"
        f"carte = CarteCashless.objects.get(tag_id='{TAG_DE_LA_CARTE_PRIMAIRE}')\n"
        "declarer_la_carte_primaire_a_l_ancien_fedow(carte)"
    )
    yield etait_primaire_au_debut
    if not etait_primaire_au_debut:
        django_shell(
            "from QrcodeCashless.models import CarteCashless\n"
            "from laboutik.carte_primaire_ancien_fedow import retirer_la_carte_primaire_de_l_ancien_fedow\n"
            f"carte = CarteCashless.objects.get(tag_id='{TAG_DE_LA_CARTE_PRIMAIRE}')\n"
            "retirer_la_carte_primaire_de_l_ancien_fedow(carte)"
        )


def _creer_une_carte_neuve_rattachee_des_deux_cotes(django_shell, email):
    """Fabrique une carte NFC NEUVE, connue de l'ancien Fedow, et la rattache a l'adherent.

    `card/refund` ne vide qu'une carte que l'ancien Fedow connait, et prend les jetons
    du portefeuille de son titulaire. Il faut donc, sur l'ancien Fedow : creer la carte
    (`NFCcard.create`), puis la lier au portefeuille de l'adherent
    (`linkwallet_card_number`). En local, la meme carte porte l'adherent.
    Une carte neuve a chaque passage : aucun etat herite d'un passage precedent (une
    carte deja liee a un autre adherent serait refusee par `linkwallet_card_number`).
    Le tag et le numero sont 8 caracteres hexadecimaux (validateur de l'ancien Fedow,
    PIEGES 9.31).
    / Builds a FRESH card known to the old Fedow and links it to the member on both
    sides. A fresh card each run: no state inherited from a previous run.

    :return: dict {'tag_id', 'wallet_uuid'}
    """
    tag_de_la_carte = uuid_module.uuid4().hex[:8].upper()
    uuid_du_qrcode = uuid_module.uuid4()
    sortie = django_shell(
        "import json\n"
        "from AuthBillet.models import TibilletUser\n"
        "from QrcodeCashless.models import CarteCashless\n"
        "from fedow_connect.fedow_api import FedowAPI\n"
        f"user = TibilletUser.objects.get(email='{email}')\n"
        "api = FedowAPI()\n"
        "api.wallet.get_or_create_wallet(user)\n"
        "user.refresh_from_db()\n"
        "api.NFCcard.create([{\n"
        f"    'first_tag_id': '{tag_de_la_carte}',\n"
        f"    'qrcode_uuid': '{uuid_du_qrcode}',\n"
        f"    'number_printed': '{tag_de_la_carte}',\n"
        "}])\n"
        f"api.NFCcard.linkwallet_card_number(user=user, card_number='{tag_de_la_carte}')\n"
        "carte = CarteCashless.objects.create(\n"
        f"    tag_id='{tag_de_la_carte}', number='{tag_de_la_carte}',\n"
        f"    uuid='{uuid_du_qrcode}', user=user)\n"
        "print('CARTE_JSON=' + json.dumps({\n"
        "    'tag_id': carte.tag_id,\n"
        "    'wallet_uuid': str(user.wallet.uuid) if user.wallet else None,\n"
        "}))"
    )
    carte = _lire_json_marque(sortie, 'CARTE_JSON=')
    if not carte['wallet_uuid']:
        pytest.fail(f"L'adherent n'a pas de portefeuille sur l'ancien Fedow : {sortie[-400:]}")
    return carte


def _vider_la_carte_a_la_caisse(page, pos_page, comptoir, tag_de_la_carte):
    """Le caissier scanne la carte (apercu), puis la vide et la reinitialise.

    On ouvre la vraie interface pour poser la session et le cookie CSRF, puis on
    envoie les deux formulaires aux vraies routes, avec la carte primaire du caissier.
    « Rembourser et reinitialiser » envoie `vider_carte=true` (VOID sur l'ancien Fedow).
    / The cashier scans the card (preview), then empties and resets it.

    :return: tuple (reponse de l'apercu, reponse du vidage)
    """
    pos_page(page, NOM_DU_COMPTOIR_DE_L_ANCIEN_FEDOW)
    donnees_communes = {
        'tag_id': tag_de_la_carte,
        'tag_id_cm': TAG_DE_LA_CARTE_PRIMAIRE,
        'uuid_pv': comptoir['pv_uuid'],
    }
    reponse_de_l_apercu = _poster(page, CHEMIN_DE_L_APERCU_DU_VIDAGE, donnees_communes)
    donnees_du_vidage = dict(donnees_communes)
    donnees_du_vidage['vider_carte'] = 'true'
    reponse_du_vidage = _poster(page, CHEMIN_DU_VIDAGE_DE_CARTE, donnees_du_vidage)
    return reponse_de_l_apercu, reponse_du_vidage


def _lire_la_vente_du_vidage(django_shell, tag_de_la_carte):
    """La vente `VIDAGE_CARTE` de la carte, ses reglements, et chaque transaction
    distante relue sur l'ancien Fedow (existence, montant, action, destinataire,
    monnaie : ils viennent du Fedow, pas de la base du lieu).
    / The card's VIDAGE_CARTE sale, its payments, and each remote transaction read
    back from the old Fedow.
    """
    sortie = django_shell(
        "import json\n"
        "from BaseBillet.models_vente import Reglement, Vente\n"
        "from fedow_connect.fedow_api import FedowAPI\n"
        "from fedow_connect.models import FedowConfig\n"
        "ventes = list(Vente.objects.filter(\n"
        f"    nature=Vente.Nature.VIDAGE_CARTE, carte__tag_id='{tag_de_la_carte}'))\n"
        "resultat = {'nombre_de_ventes': len(ventes)}\n"
        "if len(ventes) == 1:\n"
        "    vente = ventes[0]\n"
        "    api = FedowAPI()\n"
        "    reglements = []\n"
        "    for reglement in Reglement.objects.filter(vente=vente).order_by('datetime'):\n"
        "        transaction_distante = None\n"
        "        if reglement.reference_externe:\n"
        "            lue = api.transaction.retrieve(reglement.reference_externe)\n"
        "            if isinstance(lue, dict) and lue.get('uuid'):\n"
        "                transaction_distante = {\n"
        "                    'montant': int(lue['amount']),\n"
        "                    'action': lue['action'],\n"
        "                    'emetteur': str(lue['sender']),\n"
        "                    'destinataire': str(lue['receiver']),\n"
        "                    'categorie': api.asset.retrieve(str(lue['asset']))['category'],\n"
        "                }\n"
        "        reglements.append({\n"
        "            'moyen': reglement.moyen,\n"
        "            'montant': reglement.montant,\n"
        "            'reference_externe': reglement.reference_externe,\n"
        "            'fedow_transaction_uuid': str(reglement.fedow_transaction_uuid) if reglement.fedow_transaction_uuid else None,\n"
        "            'transaction_distante': transaction_distante,\n"
        "        })\n"
        "    resultat.update({\n"
        "        'statut': vente.statut,\n"
        "        'nombre_d_articles': vente.articles.count(),\n"
        "        'reglements': reglements,\n"
        "        'wallet_du_lieu': str(FedowConfig.get_solo().fedow_place_wallet_uuid),\n"
        "    })\n"
        "print('VIDAGE_JSON=' + json.dumps(resultat))"
    )
    return _lire_json_marque(sortie, 'VIDAGE_JSON=')


def _verifier_le_vidage_par_l_ancien_fedow(
    reponse_de_l_apercu, reponse_du_vidage, vente, wallet_de_l_adherent,
    montant_repris, moyen_attendu, categorie_attendue,
):
    """Les verifications communes aux deux monnaies de l'ancien Fedow.

    - l'apercu montre la partie « ancien Fedow » ;
    - le vidage rend l'ecran de succes (sinon : le corps de la reponse, qui dit
      pourquoi l'ancien Fedow a refuse — par exemple la carte primaire) ;
    - une seule vente `VIDAGE_CARTE`, REGLEE, sans article ;
    - un reglement `moyen_attendu` de +montant, dont la `reference_externe` designe
      une transaction qui EXISTE sur l'ancien Fedow : remboursement (« RFD »), du
      meme montant, de la bonne monnaie, du portefeuille de l'adherent vers celui du
      lieu ; aucun `fedow_transaction_uuid` ;
    - un reglement especes de −montant ; la somme des reglements vaut 0.
    / Checks shared by both old-Fedow currencies.
    """
    assert reponse_de_l_apercu.ok, (
        f"Apercu refuse : {reponse_de_l_apercu.status} {reponse_de_l_apercu.text()[:600]}"
    )
    assert 'data-testid="vider-carte-partie-ancien-fedow"' in reponse_de_l_apercu.text(), (
        f"L'apercu ne montre pas la partie de l'ancien Fedow : {reponse_de_l_apercu.text()[:800]}"
    )
    assert reponse_du_vidage.ok, (
        f"Vidage refuse : {reponse_du_vidage.status} {reponse_du_vidage.text()[:800]}"
    )
    assert 'data-testid="vider-carte-success"' in reponse_du_vidage.text(), (
        "Le vidage n'a pas abouti. Reponse de la caisse (si « L'ancien Fedow n'a pas "
        "pu vider la carte », lire le journal du serveur : `NFCcardFedow.refund "
        f"ERRORS` porte le corps de la reponse de l'ancien Fedow) : "
        f"{reponse_du_vidage.text()[:1200]}"
    )

    assert vente['nombre_de_ventes'] == 1, f"Attendu : une vente de vidage : {vente}"
    assert vente['statut'] == 'REGLEE', f"La vente de vidage n'est pas encaissee : {vente}"
    assert vente['nombre_d_articles'] == 0, f"La vente de vidage a des articles : {vente}"

    reglements_distants = []
    reglements_especes = []
    somme_des_reglements = 0
    for reglement in vente['reglements']:
        somme_des_reglements += reglement['montant']
        if reglement['moyen'] == 'CA':
            reglements_especes.append(reglement)
        else:
            reglements_distants.append(reglement)
    assert somme_des_reglements == 0, f"La somme des reglements ne vaut pas 0 : {vente}"
    assert [r['montant'] for r in reglements_especes] == [-montant_repris], (
        f"Attendu : un reglement especes de {-montant_repris} : {vente}"
    )
    assert len(reglements_distants) == 1, f"Attendu : un reglement distant : {vente}"

    reglement = reglements_distants[0]
    assert reglement['moyen'] == moyen_attendu, f"Moyen attendu {moyen_attendu} : {reglement}"
    assert reglement['montant'] == montant_repris, f"Montant attendu {montant_repris} : {reglement}"
    assert reglement['fedow_transaction_uuid'] is None, reglement
    transaction_distante = reglement['transaction_distante']
    assert transaction_distante is not None, (
        f"La transaction {reglement['reference_externe']} n'existe pas sur l'ancien Fedow : {reglement}"
    )
    assert transaction_distante['action'] == 'RFD', (
        f"La transaction n'est pas un remboursement (RFD) : {reglement}"
    )
    assert transaction_distante['montant'] == montant_repris, reglement
    assert transaction_distante['categorie'] == categorie_attendue, reglement
    assert transaction_distante['emetteur'] == wallet_de_l_adherent, reglement
    assert transaction_distante['destinataire'] == vente['wallet_du_lieu'], reglement


def test_caisse_vide_une_carte_avec_de_la_monnaie_locale_de_l_ancien_fedow(
    page, pos_page, django_shell, adherent_credite, comptoir_de_l_ancien_fedow,
    carte_primaire_declaree_a_l_ancien_fedow,
):
    """Une carte qui porte la monnaie locale du lieu sur l'ancien Fedow est videe a la caisse.

    L'adherent est credite en monnaie locale (TLF) sur l'ancien Fedow ; une carte
    neuve, connue de l'ancien Fedow, lui est rattachee. Le caissier la scanne puis la
    vide (« rembourser et reinitialiser »), avec la carte primaire de la caisse V2.

    CE QUE LE TEST PROUVE : l'ancien Fedow accepte la carte primaire de la caisse V2
    (`card/refund` exige une carte primaire du lieu), le solde distant tombe a 0
    (relu sans cache), et la vente `VIDAGE_CARTE` copie la vraie transaction de
    remboursement.

    CE QUE LE TEST LAISSE DERRIERE LUI : un adherent neuf et une carte neuve (sur le
    lieu et sur l'ancien Fedow), videe et deliee ; une vente de vidage encaissee,
    numerotee et chainee ; la monnaie locale de l'adherent revenue au lieu sur
    l'ancien Fedow. Rien n'est annule. La carte primaire du seed retrouve sur
    l'ancien Fedow l'etat trouve au debut (fixture `carte_primaire_declaree_a_l_ancien_fedow`).

    / A card holding the venue's local currency on the old Fedow is emptied at the
    POS. Proves the V2 primary card is accepted by the old Fedow.
    """
    email = adherent_credite['email']
    carte = _creer_une_carte_neuve_rattachee_des_deux_cotes(django_shell, email)

    soldes_avant = _soldes_des_deux_moteurs_de_l_adherent(django_shell, email)
    montant_repris = soldes_avant['locale_ancien_fedow']
    assert montant_repris > 0, soldes_avant
    assert soldes_avant['federe'] == 0, soldes_avant
    assert soldes_avant['jetons_locaux'] == 0, soldes_avant

    reponse_de_l_apercu, reponse_du_vidage = _vider_la_carte_a_la_caisse(
        page, pos_page, comptoir_de_l_ancien_fedow, carte['tag_id'],
    )
    vente = _lire_la_vente_du_vidage(django_shell, carte['tag_id'])
    _verifier_le_vidage_par_l_ancien_fedow(
        reponse_de_l_apercu, reponse_du_vidage, vente, carte['wallet_uuid'],
        montant_repris, moyen_attendu='LE', categorie_attendue='TLF',
    )

    soldes_apres = _soldes_des_deux_moteurs_de_l_adherent(django_shell, email)
    assert soldes_apres['locale_ancien_fedow'] == 0, (
        f"L'ancien Fedow n'a pas vide la monnaie locale : {soldes_avant} → {soldes_apres}"
    )
    assert soldes_apres['transactions_locales'] == 0, soldes_apres


@pytest.mark.stripe_listen
def test_caisse_vide_une_carte_avec_du_fed_de_l_ancien_fedow(
    page, login_as, pos_page, django_shell, fill_stripe_card, soumettre_paiement_stripe,
    comptoir_de_l_ancien_fedow, carte_primaire_declaree_a_l_ancien_fedow,
):
    """Une carte qui porte de la monnaie federee (FED) sur l'ancien Fedow est videe a la caisse.

    Le FED s'achete : l'adherent recharge d'abord 3 € par carte bancaire (vrai
    Stripe, `stripe listen` requis). Une carte neuve, connue de l'ancien Fedow, lui
    est rattachee ; le caissier la vide. Un reglement « SF ».

    CE QUE LE TEST LAISSE DERRIERE LUI : un paiement Stripe de test de 3 €, un
    adherent neuf et une carte neuve (sur le lieu et sur l'ancien Fedow), videe et
    deliee ; une vente de vidage encaissee, numerotee et chainee ; le FED de
    l'adherent revenu au lieu sur l'ancien Fedow. Rien n'est annule. La carte
    primaire du seed retrouve sur l'ancien Fedow l'etat trouve au debut.

    / A card holding FED on the old Fedow is emptied at the POS. One "SF" payment.
    """
    recharge = _recharger_en_monnaie_federee_par_carte_bancaire(
        page, login_as, django_shell, fill_stripe_card, soumettre_paiement_stripe,
    )
    _verifier_que_la_recharge_federee_est_creditee(recharge)
    email = recharge['email']
    carte = _creer_une_carte_neuve_rattachee_des_deux_cotes(django_shell, email)

    soldes_avant = _soldes_des_deux_moteurs_de_l_adherent(django_shell, email)
    montant_repris = soldes_avant['federe']
    assert montant_repris > 0, soldes_avant
    assert soldes_avant['locale_ancien_fedow'] == 0, soldes_avant
    assert soldes_avant['jetons_locaux'] == 0, soldes_avant

    reponse_de_l_apercu, reponse_du_vidage = _vider_la_carte_a_la_caisse(
        page, pos_page, comptoir_de_l_ancien_fedow, carte['tag_id'],
    )
    vente = _lire_la_vente_du_vidage(django_shell, carte['tag_id'])
    _verifier_le_vidage_par_l_ancien_fedow(
        reponse_de_l_apercu, reponse_du_vidage, vente, carte['wallet_uuid'],
        montant_repris, moyen_attendu='SF', categorie_attendue='FED',
    )

    soldes_apres = _soldes_des_deux_moteurs_de_l_adherent(django_shell, email)
    assert soldes_apres['federe'] == 0, (
        f"L'ancien Fedow n'a pas vide le FED : {soldes_avant} → {soldes_apres}"
    )
    assert soldes_apres['transactions_locales'] == 0, soldes_apres
