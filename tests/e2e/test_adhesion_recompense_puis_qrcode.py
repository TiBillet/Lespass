"""
tests/e2e/test_adhesion_recompense_puis_qrcode.py
L'adhesion qui cree du pouvoir d'achat, contre le VRAI Fedow.
/ The membership that creates purchasing power, against the REAL Fedow.

LOCALISATION : tests/e2e/test_adhesion_recompense_puis_qrcode.py

LE CAS D'USAGE / THE USE CASE
-------------------------------
« Caisse de securite sociale alimentaire » : on adhere, et l'adhesion credite le
portefeuille de l'adherent en monnaie locale, qu'il depense ensuite chez les
producteurs du reseau. La cotisation ne finance pas un service — elle se
transforme en pouvoir d'achat.

C'est le tarif « Souscription mensuelle » du produit « Caisse de securite sociale
alimentaire » (recurrent, prix libre, 1 € minimum) : 100 MonaLocalim verses a
chaque cotisation.

LE MECANISME / THE MECHANISM
------------------------------
Trois champs, portes par le TARIF :

    Price.fedow_reward_enabled       le declencheur
    Price.fedow_reward_asset         la monnaie versee (fedow_public.AssetFedowPublic)
    Price.fedow_reward_amount        le montant, en unites de cette monnaie

Le versement part quand la ligne de vente de l'adhesion passe CREATED → PAID :

    BaseBillet/signals.py  ligne_article_paid → TRIGGER_LigneArticlePaid.trigger_A
      → BaseBillet/tasks.py  refill_from_lespass_to_user_wallet_from_price_solded
        → fedow_connect  transaction.refill_from_lespass_to_user_wallet

**A ne pas confondre** avec `Price.reward_on_ticket_scanned`, teste par
`test_recompense_au_scan_puis_qrcode.py` : meme sortie vers le Fedow, meme trio de
champs `fedow_reward_*`, mais un declencheur different (le scan d'un billet, pas
le paiement d'une adhesion).
/ NOT to be confused with `reward_on_ticket_scanned`: same Fedow call, different
trigger.

POURQUOI CE FICHIER EXISTE / WHY THIS FILE EXISTS
---------------------------------------------------
Ce chemin echoue en silence a trois niveaux :

- `TRIGGER_LigneArticlePaid_ActionByCategorie.__init__` (`triggers.py`) enveloppe
  l'appel du trigger dans `except Exception` + `logger.error` ;
- `trigger_A` avale de meme les erreurs de ses etapes ;
- la tache (`tasks.py`) finit par `except Exception` + `logger.error`.

Un versement rate laisse donc une adhesion **d'apparence normale**, et un adherent
qui croit disposer de son pouvoir d'achat. Seule la relecture du solde le detecte :
sur le Fedow, et dans « Mon espace » de l'adherent.

Indice utile au diagnostic : quand `trigger_A` leve avant sa fin, la ligne de
vente **reste a PAID** au lieu de passer VALID (c'est la derniere chose qu'il
fait). Les deux tests l'assertent.

LES DEUX TESTS / THE TWO TESTS
-------------------------------
Tout se joue dans le navigateur ; seules les verifications relisent la base et le
Fedow.

1. EN LIGNE : la personne adhere sur `/memberships/` (formulaire, prix libre de
   1 €) et paie sur le vrai Stripe Checkout (abonnement mensuel).
2. AU COMPTOIR : le gestionnaire saisit l'adhesion dans l'admin
   (`/admin/BaseBillet/membership/add/`), cotisation de 1 € reglee en especes. C'est
   le formulaire d'ajout qui enregistre la cotisation : une adhesion creee dans
   l'admin n'attend pas de paiement, le bouton « Enregistrer un paiement » de sa
   fiche n'apparait donc pas.

Puis, dans les deux cas, le meme parcours (`_voir_et_depenser_la_recompense`) :
- l'adherent ouvre « Mon espace » : le solde affiche les 100 MonaLocalim ;
- l'encaisseur (admin) : `/my_account/` → bouton « Initier un paiement » du
  bandeau → generateur → « Vérifier le paiement » ;
- l'adherent : `/my_account/` → « Scanner un QR code de paiement » → scanner →
  page de validation → « Confirm Payment » ;
- l'adherent revient sur « Mon espace » : le solde a baisse de 1,50.
Deux contextes de navigateur, comme deux telephones. Seule la camera est simulee :
l'adherent ouvre le lien de paiement, qui est le contenu exact du QR code. Pour une
adresse du meme domaine, le scanner ne fait rien d'autre
(`scanner.html` : `window.location.href = scannedUrl`).
/ Online (Stripe) or at the counter (admin, cash), then the same QR code spend.
Only the camera is simulated.

CE QU'ILS LAISSENT DERRIERE EUX / WHAT THEY LEAVE BEHIND
---------------------------------------------------------
A chaque execution, chaque test laisse un adherent neuf, une adhesion payee (1 €)
et un versement reel de 100 MonaLocalim depuis le portefeuille du lieu, puis une
depense de 1,50 par QR code. Le test en ligne laisse en plus un abonnement Stripe
de test actif. Le versement est une EMISSION de monnaie locale par le lieu, pas un
prelevement sur un stock fini — mais il gonfle l'encours du lieu run apres run. A
lancer sur un Fedow de developpement. Rien n'est annule.
/ A member, a paid membership, a real 100-unit issuance and a 1.50 spend per test;
the online test also leaves an active Stripe test subscription. No rollback.

PREREQUIS / PREREQUISITES
--------------------------
- le serveur de developpement tourne ;
- Celery tourne : le versement passe par `.delay()` ;
- le Fedow est joignable ;
- `stripe listen` tourne vers Lespass (test en ligne, marqueur `stripe_listen`) ;
- la recharge en ligne est active pour le lieu (`show_refill_button`) : sans carte
  liee, « Mon espace » n'affiche le solde qu'a cette condition ;
- le lieu `lespass` est en skin V2 (les boutons sont ceux de l'index V2). Sinon :
  `docker exec lespass_django poetry run python manage.py charger_site_lespass`.

LANCEMENT / RUN
----------------
    make e2e-visible ARGS="tests/e2e/test_adhesion_recompense_puis_qrcode.py"
"""

import json
import re
import time
import uuid as uuid_module
from urllib.parse import urlparse

import pytest
from playwright.sync_api import expect

from tests.e2e.conftest import BASE_URL, _capturer_la_page_en_echec


# Familles de tests : `make e2e-visible <famille>` (liste : make help, ou pytest.ini).
# / Test families: `make e2e-visible <family>` (list: make help, or pytest.ini).
pytestmark = [pytest.mark.adhesion, pytest.mark.qrcode, pytest.mark.monnaie]

# Le produit et le tarif du cas d'usage, nommes explicitement. On ne cherche pas
# « un tarif qui porte une recompense » : plusieurs peuvent en porter, et le test
# doit dire lequel il verifie (PIEGES 12.13.bis).
# / Named explicitly: several prices may carry a reward, and the test must say
# which one it checks.
NOM_DU_PRODUIT = "Caisse de sécurité sociale alimentaire"
NOM_DU_TARIF = "Souscription mensuelle"

# La cotisation, en euros : le minimum du prix libre.
# / The contribution, in euros: the free price minimum.
COTISATION_EN_EUROS = "1"

# Ce que l'adherent depense ensuite par QR code, en centimes. Volontairement une
# petite part de la recompense : un debit exact se distingue ainsi d'un
# portefeuille vide ou d'un versement approximatif.
# / A small share of the reward: an exact debit is thus distinguishable from an
# emptied wallet or an approximate transfer.
DEPENSE_EN_CENTIMES = 150


# ---------------------------------------------------------------------------
# Utilitaires
# ---------------------------------------------------------------------------


def _lire_json_marque(sortie, marqueur):
    """Extrait le JSON imprime par le shell Django derriere un marqueur.

    La sortie du shell melange le JSON attendu avec les avertissements Django et
    les logs applicatifs : on repere la ligne par un marqueur explicite plutot
    que de parier sur la derniere ligne.
    / The shell output mixes JSON with warnings and logs.
    """
    for ligne in sortie.splitlines():
        if ligne.startswith(marqueur):
            return json.loads(ligne[len(marqueur) :])
    pytest.fail(
        f"Le shell Django n'a rien imprime derriere '{marqueur}'. "
        f"Sortie : {sortie[-500:]}"
    )


def _motif_du_montant(centimes):
    """Le motif d'un montant affiche en euros, « 100,00 » ou « 100.00 ».

    Le chiffre qui precede ne doit pas etre un chiffre : « 1100,00 » ne vaut pas
    « 100,00 ».
    / The pattern of an amount displayed in euros. No digit just before it.
    """
    return re.compile(rf"(?<!\d){centimes // 100}[,.]{centimes % 100:02d}")


def _solde_depensable(django_shell, email):
    """Le solde depensable de l'adherent, relu SUR LE FEDOW sans cache.

    `use_cache=False` est indispensable : c'est le versement qui vient d'avoir
    lieu qu'on veut observer, pas la valeur memorisee avant lui.
    / Read ON THE FEDOW without cache.

    Le portefeuille de l'adherent neuf est cree par la tache Celery de recompense,
    juste avant le versement. Tant qu'elle n'a pas tourne, il n'existe pas : rien n'a
    encore ete verse, le solde est nul.
    / The new member's wallet is created by the Celery reward task, right before the
    transfer. Until it runs there is no wallet: nothing paid in yet, balance is zero.
    """
    sortie = django_shell(
        "from AuthBillet.models import TibilletUser\n"
        "from fedow_connect.fedow_api import FedowAPI\n"
        f"user = TibilletUser.objects.get(email='{email}')\n"
        "if user.wallet is None:\n"
        "    print('SOLDE=0')\n"
        "else:\n"
        "    print('SOLDE=' + str(\n"
        "        FedowAPI().wallet.get_total_fiducial_and_all_federated_token(\n"
        "            user, use_cache=False)))"
    )
    trouve = re.search(r"SOLDE=(\d+)", sortie)
    if not trouve:
        pytest.fail(f"Solde illisible depuis le Fedow. Sortie : {sortie[-400:]}")
    return int(trouve.group(1))


def _attendre_le_versement(django_shell, email, solde_de_depart, secondes=60):
    """Attend que le Fedow reflete le versement, ou rend le dernier solde lu.

    Le versement part par Celery (`.delay()`), et la tache commence elle-meme par
    un `sleep(1)`. On interroge en boucle plutot que de parier sur un delai fixe.
    / The transfer goes through Celery and the task starts with a sleep: poll.
    """
    solde = solde_de_depart
    for _tentative in range(secondes // 2):
        solde = _solde_depensable(django_shell, email)
        if solde != solde_de_depart:
            return solde
        time.sleep(2)
    return solde


def _attendre_le_solde_dans_mon_espace(page_de_l_adherent, centimes_attendus, secondes=40):
    """L'adherent ouvre « Mon espace » : le solde affiche `centimes_attendus`.

    La page lit le portefeuille avec un cache de 10 s
    (`cached_retrieve_by_signature`) : on la recharge jusqu'a voir le montant.
    / The page reads the wallet with a 10 s cache: reload until the amount shows.
    """
    motif = _motif_du_montant(centimes_attendus)
    texte_du_solde = None
    for _tentative in range(secondes // 4):
        page_de_l_adherent.goto("/my_account/")
        solde_affiche = page_de_l_adherent.get_by_test_id("compte-solde")
        expect(
            solde_affiche,
            "« Mon espace » n'affiche pas de solde. Sans carte liee, le solde n'est "
            "affiche que si la recharge en ligne est active (show_refill_button).",
        ).to_be_visible()
        texte_du_solde = solde_affiche.inner_text()
        if motif.search(texte_du_solde):
            return
        time.sleep(4)
    pytest.fail(
        f"« Mon espace » affiche « {texte_du_solde} » au lieu de "
        f"{centimes_attendus / 100:.2f} € apres {secondes} s."
    )


def _lire_la_ligne_de_l_adhesion(django_shell, email):
    """La derniere adhesion de l'adherent, sa ligne de vente et la trace du versement.
    / The member's latest membership, its sale line and the reward trace."""
    sortie = django_shell(
        "import json\n"
        "from BaseBillet.models import LigneArticle, Membership\n"
        "adhesion = Membership.objects.filter(\n"
        f"    user__email='{email}').order_by('-date_added').first()\n"
        "ligne = LigneArticle.objects.filter(\n"
        "    membership=adhesion).order_by('-datetime').first() if adhesion else None\n"
        "recompense = ((ligne.metadata or {}).get('fedow_reward') or {}) if ligne else {}\n"
        "print('VENTE_JSON=' + json.dumps({\n"
        "    'adhesion_trouvee': adhesion is not None,\n"
        "    'uuid_ligne': str(ligne.uuid) if ligne else None,\n"
        "    'statut_ligne': ligne.status if ligne else None,\n"
        "    'montant_ligne': int(ligne.amount) if ligne else None,\n"
        "    'moyen': ligne.payment_method if ligne else None,\n"
        "    'statut_adhesion': adhesion.status if adhesion else None,\n"
        "    'recompense_montant': recompense.get('amount'),\n"
        "    'recompense_asset': recompense.get('asset'),\n"
        "    'recompense_transaction': recompense.get('transaction_uuid'),\n"
        "}))"
    )
    return _lire_json_marque(sortie, "VENTE_JSON=")


def _verifier_la_ligne_de_l_adhesion(vente, tarif, moyen_attendu):
    """La ligne de l'adhesion est validee, au bon moyen, et porte la trace du versement.

    La ligne passe VALID en toute FIN de `trigger_A`. Une ligne restee a PAID est
    donc le symptome visible d'un trigger interrompu en chemin — c'est le seul
    signal exploitable, puisque l'exception est avalee.
    / The line turns VALID at the very END of trigger_A: PAID means interrupted.
    """
    assert vente["adhesion_trouvee"], f"Aucune adhesion en base : {vente}"
    assert vente["statut_ligne"] == "V", (
        f"La ligne de vente de l'adhesion n'est pas validee : {vente}. Restee a "
        "'P', elle signale que `trigger_A` s'est interrompu avant sa derniere "
        "instruction — l'exception est avalee, ce statut est le seul indice."
    )
    assert vente["moyen"] == moyen_attendu, (
        f"La ligne de l'adhesion devrait porter le moyen {moyen_attendu} : {vente}"
    )
    assert vente["recompense_transaction"], (
        f"La ligne ne porte aucune trace de versement : {vente}. Sans elle, "
        "un nouveau paiement sur la meme adhesion reverserait la recompense."
    )
    assert vente["recompense_montant"] == tarif["montant_en_centimes"], (
        f"La trace ne porte pas le montant verse : {vente}, "
        f"attendu {tarif['montant_en_centimes']}."
    )
    assert vente["recompense_asset"] == tarif["asset_uuid"], (
        f"La trace ne designe pas la monnaie de recompense : {vente}, "
        f"attendu {tarif['asset_uuid']}."
    )


def _verifier_que_la_recompense_est_versee(django_shell, email, tarif):
    """Attend le versement SUR LE FEDOW et verifie le montant exact.

    L'adherent est neuf : son solde de depart est nul.
    / Waits for the transfer ON THE FEDOW; the member is new, starting at 0.

    :return: le solde apres la cotisation, en centimes
    """
    solde_apres_cotisation = _attendre_le_versement(django_shell, email, 0)
    assert solde_apres_cotisation == tarif["montant_en_centimes"], (
        f"Le Fedow n'a pas verse la recompense d'adhesion : 0 → "
        f"{solde_apres_cotisation}, attendu {tarif['montant_en_centimes']}.\n"
        "Si le solde n'a pas bouge du tout : Celery arrete, Fedow injoignable, "
        "refus du Fedow, ou portefeuille jamais cree (`TibilletUser.wallet is None`) "
        "— que le trigger et la tache avalent tous deux en silence. "
        "Les logs de `lespass_celery` portent la raison."
    )
    return solde_apres_cotisation


def _voir_et_depenser_la_recompense(
    page, browser, request, login_as, login_as_admin, django_shell, email,
    solde_apres_cotisation,
):
    """L'adherent voit sa recompense dans « Mon espace », la depense par QR code, et
    voit son solde baisser.

    Deux contextes de navigateur, comme deux telephones : l'encaisseur est la `page`
    du test (connectee en admin ici, et capturee par le conftest en cas d'echec) ;
    l'adherent a son propre contexte, capture ici s'il s'arrete en chemin.
    / Two browser contexts, like two phones: the cashier is the test `page`, the
    member has their own context.

    :return: l'uuid de la demande de paiement (la ligne de vente du QR code)
    """
    # Payer par QR code exige une adresse validee : sinon le bouton « Scanner » est
    # grise. L'adherent la valide par le lien recu par mail ; le test pose ce drapeau,
    # car il ne lit pas la boite mail.
    # / Paying by QR code requires a validated email; the test sets the flag, as it
    # does not read the mailbox.
    django_shell(
        "from AuthBillet.models import TibilletUser\n"
        f"TibilletUser.objects.filter(email='{email}').update(email_valid=True)"
    )

    contexte_de_l_adherent = browser.new_context(
        base_url=BASE_URL,
        ignore_https_errors=True,
    )
    page_de_l_adherent = contexte_de_l_adherent.new_page()
    parcours_de_l_adherent_termine = False
    try:
        # a. L'adherent ouvre « Mon espace » : la recompense est sur son solde.
        # / a. The member opens "My space": the reward is on their balance.
        login_as(page_de_l_adherent, email)
        _attendre_le_solde_dans_mon_espace(page_de_l_adherent, solde_apres_cotisation)

        # b. L'encaisseur ouvre le generateur depuis le bandeau de « Mes responsabilites ».
        # / b. The cashier opens the generator from the "My responsibilities" banner.
        login_as_admin(page)
        page.goto("/my_account/")
        bouton_initier_un_paiement = page.get_by_test_id("compte-initier-paiement-bouton")
        expect(bouton_initier_un_paiement).to_be_visible()
        bouton_initier_un_paiement.click()
        page.wait_for_url("**/qrcodescanpay/get_generator/")

        champ_du_montant = page.locator("#amount")
        expect(champ_du_montant).to_be_visible()
        champ_du_montant.fill(f"{DEPENSE_EN_CENTIMES / 100:.2f}")
        # Seule la monnaie « EURO » est encaissable par QR code : c'est le choix par defaut.
        # / Only EURO can be collected by QR code: it is the default choice.
        expect(page.locator("#asset_type")).to_have_value("EURO")
        page.locator('form[action$="/generate_qrcode/"] button[type="submit"]').click()

        # c. Le QR code et le lien de paiement sont affiches.
        # / c. The QR code and the payment link are shown.
        bouton_copier_le_lien = page.locator("#copy-pay-link-btn")
        expect(bouton_copier_le_lien).to_be_visible()
        expect(
            page.locator("#qrcode-js").locator("canvas, img").filter(visible=True).first
        ).to_be_visible()

        # Le lien de paiement EST le contenu du QR code. L'uuid de la demande se lit
        # dedans : une demande creee par un test voisin ne peut pas etre prise a la place.
        # / The payment link IS the QR code content; the request uuid is read from it.
        lien_de_paiement = bouton_copier_le_lien.get_attribute("data-link") or ""
        trouve = re.search(
            r"/qrcodescanpay/([0-9a-f]{32})/process_qrcode$", lien_de_paiement
        )
        assert trouve, (
            f"Le lien de paiement ne porte pas l'uuid d'une demande : '{lien_de_paiement}'."
        )
        uuid_de_la_demande = trouve.group(1)

        sortie = django_shell(
            "import json\n"
            "from BaseBillet.models import LigneArticle, SaleOrigin\n"
            f"ligne = LigneArticle.objects.filter(uuid='{uuid_de_la_demande}').first()\n"
            "print('DEMANDE_JSON=' + json.dumps({\n"
            "    'trouvee': bool(ligne),\n"
            "    'en_attente': bool(ligne) and ligne.status == LigneArticle.CREATED,\n"
            "    'origine_qrcode': bool(ligne) and ligne.sale_origin == SaleOrigin.QRCODE_MA,\n"
            "    'montant': int(ligne.amount) if ligne else None,\n"
            "}))"
        )
        demande = _lire_json_marque(sortie, "DEMANDE_JSON=")
        assert demande == {
            "trouvee": True,
            "en_attente": True,
            "origine_qrcode": True,
            "montant": DEPENSE_EN_CENTIMES,
        }, f"Le lien ne designe pas la demande en attente du montant saisi : {demande}"

        # d. Avant tout paiement, « Vérifier le paiement » repond « en attente ».
        # Sans ce controle, un bouton qui repondrait toujours « validé » passerait.
        # / d. Before any payment, the check answers "pending".
        zone_de_verification = page.locator("#check-payment-button")
        expect(zone_de_verification.locator("button")).to_contain_text(
            "Vérifier le paiement"
        )
        zone_de_verification.locator("button").click()
        expect(page.locator("#check-payment-button button")).to_contain_text(
            "Paiement en attente. Vérifier maintenant"
        )

        # e. L'adherent, sur son telephone : « Mon espace » → scanner → validation.
        # / e. The member, on their phone: "My space" → scanner → validation.
        page_de_l_adherent.goto("/my_account/")
        bouton_scanner = page_de_l_adherent.get_by_test_id("compte-scanner-qrcode")
        expect(bouton_scanner).to_be_visible()
        bouton_scanner.click()
        page_de_l_adherent.wait_for_url("**/qrcodescanpay/get_scanner/")
        expect(page_de_l_adherent.locator("#start-button")).to_be_visible()

        # Ce qui est simule : la camera. Le lien de paiement est le contenu exact du
        # QR code ; pour une adresse du MEME domaine, le scanner fait seulement
        # `window.location.href = adresse` (scanner.html). On verifie donc d'abord
        # que le lien est bien du domaine du scanner, puis on l'ouvre.
        # / Simulated: the camera. Check the domain, then open the link.
        domaine_du_lien = urlparse(lien_de_paiement).hostname
        domaine_du_scanner = urlparse(page_de_l_adherent.url).hostname
        assert domaine_du_lien == domaine_du_scanner, (
            f"Le lien de paiement vise '{domaine_du_lien}', le scanner tourne sur "
            f"'{domaine_du_scanner}' : le scanner passerait par le relais de session "
            "entre lieux, que ce parcours ne simule pas."
        )
        page_de_l_adherent.goto(lien_de_paiement)

        formulaire_de_validation = page_de_l_adherent.locator(
            'form[hx-post$="/valid_payment/"]'
        )
        expect(
            formulaire_de_validation,
            "Pas de formulaire de validation : solde juge insuffisant, ou demande "
            "introuvable. La page de l'adherent est capturee dans tests/e2e/artefacts/.",
        ).to_be_visible()
        # Le montant demande, ecrit avec un point ou une virgule selon la langue.
        # / The requested amount, with a dot or a comma depending on the language.
        expect(page_de_l_adherent.locator("#qrscanpay-container")).to_contain_text(
            re.compile(r"1[.,]50\s*€")
        )

        with page_de_l_adherent.expect_response(
            lambda reponse_http: "/qrcodescanpay/valid_payment/" in reponse_http.url
        ) as reponse_attendue:
            formulaire_de_validation.locator('button[type="submit"]').click()
        reponse = reponse_attendue.value
        assert reponse.ok, (
            f"Le paiement a echoue : {reponse.status} {reponse.text()[:400]}"
        )
        assert "Insufficient Funds" not in reponse.text(), (
            f"Le paiement a ete refuse pour fonds insuffisants alors que la cotisation "
            f"vient de crediter {solde_apres_cotisation} centimes. La monnaie versee "
            "par l'adhesion n'est donc pas depensable — verifier sa categorie Fedow."
        )
        # L'ecran « Paiement confirmé » : seul gabarit du parcours a en-tete vert.
        # / The "Payment Confirmed" screen: the only green-headed template here.
        expect(
            page_de_l_adherent.locator("#qrscanpay-container .card-header.bg-success")
        ).to_contain_text(re.compile(r"Payment Confirmed|Paiement confirmé"))

        # f. L'encaisseur verifie : le paiement est valide.
        # / f. The cashier checks: the payment is validated.
        page.locator("#check-payment-button button").click()
        expect(page.locator("#check-payment-button")).to_contain_text("Paiement validé")

        # g. L'adherent revient sur « Mon espace » : son solde a baisse de 1,50.
        # / g. The member goes back to "My space": the balance dropped by 1.50.
        _attendre_le_solde_dans_mon_espace(
            page_de_l_adherent, solde_apres_cotisation - DEPENSE_EN_CENTIMES
        )
        parcours_de_l_adherent_termine = True
    finally:
        if not parcours_de_l_adherent_termine:
            _capturer_la_page_en_echec(
                page_de_l_adherent, f"{request.node.nodeid}-adherent"
            )
        contexte_de_l_adherent.close()

    # h. Le Fedow a debite le montant exact.
    # / h. The Fedow debited the exact amount.
    solde_apres_depense = _solde_depensable(django_shell, email)
    assert solde_apres_depense == solde_apres_cotisation - DEPENSE_EN_CENTIMES, (
        f"Le Fedow n'a pas debite le bon montant : {solde_apres_cotisation} → "
        f"{solde_apres_depense}, attendu "
        f"{solde_apres_cotisation - DEPENSE_EN_CENTIMES}."
    )

    # i. La depense est enregistree comme une vente.
    # / i. The spend is recorded as a sale.
    sortie = django_shell(
        "import json\n"
        "from BaseBillet.models import LigneArticle\n"
        f"ligne = LigneArticle.objects.filter(uuid='{uuid_de_la_demande}').first()\n"
        "print('DEPENSE_JSON=' + json.dumps({\n"
        "    'trouvee': bool(ligne),\n"
        "    'montant': int(ligne.amount) if ligne else None,\n"
        "    'validee': bool(ligne) and ligne.status == LigneArticle.VALID,\n"
        "}))"
    )
    depense = _lire_json_marque(sortie, "DEPENSE_JSON=")
    assert depense["trouvee"] and depense["validee"], (
        f"Le portefeuille a ete debite mais aucune vente validee n'existe en face : "
        f"{depense}. L'adherent perd sa monnaie sans contrepartie comptable."
    )
    assert depense["montant"] == DEPENSE_EN_CENTIMES, (
        f"La vente ne porte pas le montant debite : {depense}"
    )
    return uuid_de_la_demande


def _verifier_la_cloture_en_ligne(
    rapports_qui_voient_la_ligne, debut_de_la_mesure, uuid_ligne_adhesion,
    uuid_de_la_demande,
):
    """La cotisation et la depense par QR code entrent dans la cloture comptable en ligne.

    On situe CHAQUE ligne plutot que d'asserter un total : les lignes du rapport en
    ligne arrivent aussi par webhook Stripe, donc de facon asynchrone, et celui d'un
    test voisin peut tomber dans la meme fenetre.
    / Locate EACH line instead of asserting a total.
    """
    for intitule, uuid_de_la_ligne in (
        ("la cotisation", uuid_ligne_adhesion),
        ("la depense par QR code", uuid_de_la_demande),
    ):
        situation = rapports_qui_voient_la_ligne(uuid_de_la_ligne, debut_de_la_mesure)
        assert situation["en_ligne"], (
            f"La ligne de {intitule} ({uuid_de_la_ligne}) n'entre PAS dans la "
            "cloture comptable en ligne. Une vente que ni le ticket de caisse ni "
            "la cloture en ligne ne voient n'existe pour aucun comptable."
        )


def _verifier_que_le_versement_n_ecrit_aucune_vente(django_shell, email, uuid_ligne_adhesion):
    """Le VERSEMENT de la recompense ne laisse aucune ecriture.

    Le lieu emet de la monnaie — une dette envers l'adherent — et rien ne
    l'enregistre cote Lespass. Seules la metadata de la ligne et la transaction Fedow
    en gardent trace. On compte les lignes par leur VENTE, dont l'adherent est le
    client : une ligne de vente ne porte ni carte ni portefeuille (Q-H2). Les deux
    ventes du parcours sont mises de cote : la cotisation (sa ligne) et la depense
    par QR code (son origine).
    / The transfer itself leaves no entry; the two sales of the journey are set aside.
    """
    sortie = django_shell(
        "from AuthBillet.models import TibilletUser\n"
        "from BaseBillet.models import LigneArticle, SaleOrigin\n"
        f"user = TibilletUser.objects.get(email='{email}')\n"
        "lignes = LigneArticle.objects.filter(vente__client=user).exclude(\n"
        "    sale_origin=SaleOrigin.QRCODE_MA).exclude(\n"
        f"    uuid='{uuid_ligne_adhesion}')\n"
        "print('LIGNES_HORS_QRCODE=' + str(lignes.count()))"
    )
    assert "LIGNES_HORS_QRCODE=0" in sortie, (
        f"Une vente de l'adherent porte une ligne en plus de la cotisation et de "
        f"la depense par QR code : {sortie[-200:]}. Le versement de recompense "
        "n'ecrit aucune ecriture comptable : si une contrepartie existe, ce "
        "constat est a reecrire."
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def lieu_en_skin_v2(django_shell):
    """Echoue, avec la consigne, si le lieu n'est pas en skin V2.

    Les boutons de « Mon espace » que les tests cliquent sont ceux de l'index V2.
    Le skin se LIT en base, par `objects.first()`. Jamais `get_solo()` : il cree la
    ligne si elle manque, et passe par le cache memcached partage avec le serveur.
    Le test n'ecrit jamais le skin : c'est un reglage du lieu, pas du test.
    / Fails with what to do if the venue is not on the V2 skin. Read only.
    """
    sortie = django_shell(
        "from pages.models import ConfigurationSite\n"
        "configuration_du_site = ConfigurationSite.objects.first()\n"
        "print('SKIN=' + (configuration_du_site.skin if configuration_du_site\n"
        "                 else 'AUCUNE_CONFIGURATION'))"
    )
    trouve = re.search(r"SKIN=(\S+)", sortie)
    skin_du_lieu = trouve.group(1) if trouve else None
    if skin_du_lieu != "V2":
        pytest.fail(
            f"Le lieu 'lespass' n'est pas en skin V2 (lu : {skin_du_lieu}). Les "
            "boutons de paiement par QR code de ce parcours sont ceux de l'index V2. "
            "Remettre le skin : docker exec lespass_django poetry run python "
            "manage.py charger_site_lespass"
        )
    return skin_du_lieu


@pytest.fixture(scope="module")
def tarif_de_la_caisse_alimentaire(django_shell):
    """Le tarif du cas d'usage, tel qu'il est configure sur ce tenant.

    On ne le fabrique pas et on ne le corrige pas : c'est precisement la
    configuration de production qu'on veut verifier. Un tarif mal configure doit
    faire echouer ce test, pas etre repare par lui.
    / Neither fabricated nor fixed up: a misconfigured price must fail this test.
    """
    sortie = django_shell(
        "import json\n"
        "from BaseBillet.models import Price\n"
        "tarif = Price.objects.filter(\n"
        f"    product__name='{NOM_DU_PRODUIT}', name='{NOM_DU_TARIF}'\n"
        ").select_related('product', 'fedow_reward_asset').first()\n"
        "print('TARIF_JSON=' + json.dumps({\n"
        "    'trouve': bool(tarif),\n"
        "    'uuid': str(tarif.uuid) if tarif else None,\n"
        "    'uuid_du_produit': str(tarif.product.uuid) if tarif else None,\n"
        "    'prix': float(tarif.prix) if tarif else None,\n"
        "    'prix_libre': bool(tarif and tarif.free_price),\n"
        "    'recompense_active': bool(tarif and tarif.fedow_reward_enabled),\n"
        "    'asset_uuid': str(tarif.fedow_reward_asset.uuid)\n"
        "                  if (tarif and tarif.fedow_reward_asset) else None,\n"
        "    'asset_nom': tarif.fedow_reward_asset.name\n"
        "                 if (tarif and tarif.fedow_reward_asset) else None,\n"
        "    'asset_categorie': tarif.fedow_reward_asset.category\n"
        "                       if (tarif and tarif.fedow_reward_asset) else None,\n"
        "    'montant': float(tarif.fedow_reward_amount)\n"
        "               if (tarif and tarif.fedow_reward_amount) else None,\n"
        "}))"
    )
    donnees = _lire_json_marque(sortie, "TARIF_JSON=")

    if not donnees["trouve"]:
        pytest.fail(
            f"Le tarif '{NOM_DU_TARIF}' du produit '{NOM_DU_PRODUIT}' n'existe pas "
            "sur ce tenant. Reseeder : docker exec lespass_django poetry run "
            "python manage.py demo_data_v2"
        )

    # Les trois champs sont exiges ENSEMBLE par la tache : un tarif ou la case est
    # cochee mais dont l'asset ou le montant manque ne verse jamais rien, et RIEN
    # ne le signale. C'est le seul endroit ou cette configuration est verifiee.
    # / The task requires all three fields together: a half-configured price
    # silently never pays.
    manquants = [
        nom
        for nom, valeur in (
            ("fedow_reward_enabled", donnees["recompense_active"]),
            ("fedow_reward_asset", donnees["asset_uuid"]),
            ("fedow_reward_amount", donnees["montant"]),
        )
        if not valeur
    ]
    if manquants:
        pytest.fail(
            f"Le tarif '{NOM_DU_TARIF}' ne verse aucune recompense : "
            f"{', '.join(manquants)} manquant(s). La tache exige les TROIS champs "
            f"ensemble et se tait sinon. Configuration lue : {donnees}"
        )

    # La monnaie versee doit etre encaissable par QR code. `valid_payment` ne sait
    # traduire que FED et TLF en moyen de paiement comptable : une recompense en
    # monnaie temps ou cadeau serait creditee, puis debitee au paiement SANS
    # qu'aucune vente ne soit enregistree en face.
    # / The reward currency must be collectable by QR code: only FED and TLF are.
    if donnees["asset_categorie"] not in ("FED", "TLF"):
        pytest.fail(
            f"La recompense est versee en '{donnees['asset_nom']}', de categorie "
            f"'{donnees['asset_categorie']}'. Seules FED et TLF sont encaissables "
            "par QR code : l'adherent serait credite d'une monnaie qu'il ne peut "
            "pas depenser."
        )

    # Le parcours en ligne saisit un montant libre : le tarif doit en etre un.
    # / The online journey types a free amount: the price must be free.
    if not donnees["prix_libre"]:
        pytest.fail(
            f"Le tarif '{NOM_DU_TARIF}' n'est plus a prix libre : {donnees}. Le "
            "parcours en ligne saisit le montant de la cotisation."
        )

    donnees["montant_en_centimes"] = int(round(donnees["montant"] * 100))
    return donnees


# ---------------------------------------------------------------------------
# Test 1 — adhesion EN LIGNE, payee sur Stripe
# ---------------------------------------------------------------------------


@pytest.mark.stripe_listen
def test_adhesion_en_ligne_payee_par_stripe_credite_mon_espace_puis_se_depense_par_qrcode(
    page,
    browser,
    request,
    lieu_en_skin_v2,
    login_as,
    login_as_admin,
    django_shell,
    instant_serveur,
    rapports_qui_voient_la_ligne,
    fill_stripe_card,
    soumettre_paiement_stripe,
    tarif_de_la_caisse_alimentaire,
):
    """Adherer en ligne, payer sur Stripe, voir la recompense dans « Mon espace »,
    puis la depenser par QR code.
    / Join online, pay on Stripe, see the reward in "My space", spend it by QR code.
    """
    tarif = tarif_de_la_caisse_alimentaire
    email = f"e2e-cssa-ligne-{uuid_module.uuid4().hex[:8]}@tibillet.test"

    # Borne basse des rapports comptables, posee avant toute action.
    # / Lower bound for the accounting reports, set before any action.
    debut_de_la_mesure = instant_serveur()

    # --- 1. La personne ouvre l'adhesion sur la page publique ---
    page.goto("/memberships/")
    bouton_adherer = page.get_by_test_id(f"membership-open-{tarif['uuid_du_produit']}")
    expect(bouton_adherer).to_be_visible()
    bouton_adherer.click()
    page.wait_for_selector("#subscribePanel.show", state="visible", timeout=15_000)
    page.wait_for_selector("#membership-form", state="visible", timeout=10_000)

    # --- 2. Elle remplit le formulaire : identite, puis le montant libre ---
    page.locator("#membership-email").fill(email)
    page.locator("#confirm-email").fill(email)
    page.locator('#subscribePanel input[name="firstname"]').fill("E2E")
    page.locator('#subscribePanel input[name="lastname"]').fill("Caisse en ligne")
    champ_du_montant_libre = page.get_by_test_id(
        f"membership-custom-amount-{tarif['uuid']}"
    )
    expect(champ_du_montant_libre).to_be_visible()
    champ_du_montant_libre.fill(COTISATION_EN_EUROS)

    # --- 3. Elle paie sur le vrai Stripe Checkout (abonnement mensuel) ---
    page.locator("#membership-submit").click()
    page.wait_for_url(lambda url: "checkout.stripe.com" in url, timeout=40_000)
    # Stripe garde des connexions ouvertes : `networkidle` n'y arrive jamais (PIEGES 9.28).
    # / Stripe keeps connections open: networkidle never settles there.
    page.wait_for_load_state("domcontentloaded")
    fill_stripe_card(page, email)
    # La soumission demande de l'insistance sur ce checkout (PIEGES 12.14).
    # / Submitting takes persistence here (PIEGES 12.14).
    soumettre_paiement_stripe(page)
    page.wait_for_url(lambda url: "tibillet.localhost" in url, timeout=60_000)

    # --- 4. LE FEDOW REEL a credite l'adherent, du montant exact ---
    solde_apres_cotisation = _verifier_que_la_recompense_est_versee(
        django_shell, email, tarif
    )

    # --- 5. La ligne de l'adhesion : validee, payee par Stripe, versement trace ---
    # La PREMIERE echeance de l'abonnement est payee sur le Checkout : la ligne porte
    # « Stripe CB » (SN). Les echeances suivantes portent « Recurrent » (SR), voir
    # test_renouvellement_adhesion_recurrente.py.
    # / The FIRST instalment is paid on the Checkout (SN); renewals are SR.
    vente = _lire_la_ligne_de_l_adhesion(django_shell, email)
    _verifier_la_ligne_de_l_adhesion(vente, tarif, moyen_attendu="SN")

    # --- 6. « Mon espace » montre la recompense, qui se depense par QR code ---
    uuid_de_la_demande = _voir_et_depenser_la_recompense(
        page, browser, request, login_as, login_as_admin, django_shell, email,
        solde_apres_cotisation,
    )

    # --- 7. Ce que la comptabilite voit de ce parcours ---
    # Une cotisation payee en ligne et une depense par QR code : toutes deux dans la
    # cloture comptable en ligne. Aucune ne passe par le tiroir d'une caisse.
    # / An online contribution and a QR code spend: both in the online closure.
    _verifier_la_cloture_en_ligne(
        rapports_qui_voient_la_ligne, debut_de_la_mesure, vente["uuid_ligne"],
        uuid_de_la_demande,
    )
    _verifier_que_le_versement_n_ecrit_aucune_vente(
        django_shell, email, vente["uuid_ligne"]
    )


# ---------------------------------------------------------------------------
# Test 2 — adhesion AU COMPTOIR, saisie dans l'admin, reglee en especes
# ---------------------------------------------------------------------------


def test_adhesion_au_comptoir_saisie_dans_l_admin_credite_mon_espace_puis_se_depense_par_qrcode(
    page,
    browser,
    request,
    lieu_en_skin_v2,
    login_as,
    login_as_admin,
    django_shell,
    instant_serveur,
    rapports_comptables,
    rapports_qui_voient_la_ligne,
    tarif_de_la_caisse_alimentaire,
):
    """Le gestionnaire saisit l'adhesion dans l'admin, cotisation en especes ;
    l'adherent voit la recompense dans « Mon espace », puis la depense par QR code.
    / The manager enters the membership in the admin (cash); the member sees the
    reward in "My space", then spends it by QR code.
    """
    tarif = tarif_de_la_caisse_alimentaire
    email = f"e2e-cssa-comptoir-{uuid_module.uuid4().hex[:8]}@tibillet.test"

    # Borne basse des rapports comptables, posee avant toute action.
    # / Lower bound for the accounting reports, set before any action.
    debut_de_la_mesure = instant_serveur()

    # --- 1. Le gestionnaire ouvre le formulaire d'ajout d'adhesion ---
    login_as_admin(page)
    page.goto("/admin/BaseBillet/membership/add/")

    # --- 2. Il saisit la personne, le tarif, et la cotisation reglee en especes ---
    page.locator("#id_last_name").fill("Caisse au comptoir")
    page.locator("#id_first_name").fill("E2E")
    page.locator("#id_email").fill(email)
    # Le libelle du tarif annonce le declencheur : « ⚡ +100 MonaLocalim ».
    # / The price label announces the trigger.
    page.locator("#id_price").select_option(tarif["uuid"])
    expect(page.locator("#id_price option:checked")).to_contain_text("⚡")
    page.locator("#id_contribution").fill(COTISATION_EN_EUROS)
    page.locator("#id_payment_method").select_option("CA")

    # --- 3. Il enregistre : l'adhesion et sa vente sont ecrites ---
    page.locator('[name="_save"]').first.click()
    page.wait_for_load_state("domcontentloaded")
    expect(
        page.locator(".errornote, .errorlist"),
        "Le formulaire d'ajout d'adhesion a ete refuse.",
    ).to_have_count(0)
    assert "/membership/add/" not in page.url, (
        f"Le formulaire d'ajout est reste affiche : {page.url}"
    )

    # --- 4. LE FEDOW REEL a credite l'adherent, du montant exact ---
    solde_apres_cotisation = _verifier_que_la_recompense_est_versee(
        django_shell, email, tarif
    )

    # --- 5. La ligne de l'adhesion : validee, payee en especes, versement trace ---
    vente = _lire_la_ligne_de_l_adhesion(django_shell, email)
    _verifier_la_ligne_de_l_adhesion(vente, tarif, moyen_attendu="CA")

    # --- 6. « Mon espace » montre la recompense, qui se depense par QR code ---
    uuid_de_la_demande = _voir_et_depenser_la_recompense(
        page, browser, request, login_as, login_as_admin, django_shell, email,
        solde_apres_cotisation,
    )

    # --- 7. Ce que la comptabilite voit de ce parcours ---
    comptes = rapports_comptables(debut_de_la_mesure)

    # La cotisation est saisie a la main par un gestionnaire : elle porte
    # l'origine `ADMIN` et n'entre donc PAS dans le ticket de caisse — l'argent
    # n'est pas passe par le tiroir suivi par la cloture de service. Elle entre en
    # revanche dans la cloture comptable en ligne, avec la depense par QR code.
    # / A hand-entered contribution carries ADMIN and stays out of the register
    # ticket; it lands in the online closure, together with the QR code spend.
    assert comptes["caisse"]["especes"] == 0, (
        f"La cotisation saisie a la main est entree dans les especes du ticket "
        f"de caisse : {comptes['caisse']}. Aucun billet n'est pourtant entre "
        "dans le tiroir suivi par la cloture de service."
    )
    assert comptes["caisse"]["total_adhesions"] == 0, (
        f"La cotisation apparait dans la section adhesions du ticket de caisse : "
        f"{comptes['caisse']}. Saisie a la main, elle n'est la vente d'aucun "
        "point de vente."
    )
    _verifier_la_cloture_en_ligne(
        rapports_qui_voient_la_ligne, debut_de_la_mesure, vente["uuid_ligne"],
        uuid_de_la_demande,
    )
    _verifier_que_le_versement_n_ecrit_aucune_vente(
        django_shell, email, vente["uuid_ligne"]
    )
