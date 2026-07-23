"""
tests/e2e/test_recompense_au_scan_puis_qrcode.py
La recompense en monnaie au scan d'un billet, contre le VRAI Fedow.
/ The currency reward on ticket scan, against the REAL Fedow.

LOCALISATION : tests/e2e/test_recompense_au_scan_puis_qrcode.py

LE MECANISME / THE MECHANISM
------------------------------
Trois champs, portes par le TARIF et non par le produit :

    Price.reward_on_ticket_scanned   le declencheur
    Price.fedow_reward_asset         la monnaie versee (fedow_public.AssetFedowPublic)
    Price.fedow_reward_amount        le montant, en unites de cette monnaie

Le versement part a la transition NOT_SCANNED → SCANNED du billet :

    BaseBillet/signals.py  PRE_SAVE_TRANSITIONS['TICKET'] → check_reward
      → BaseBillet/tasks.py  refill_from_lespass_to_user_wallet_from_ticket_scanned
        → fedow_connect  transaction.refill_from_lespass_to_user_wallet

C'est le cas d'usage « caisse de securite sociale alimentaire » : on s'inscrit,
et l'inscription cree du pouvoir d'achat en monnaie locale, depensable ensuite.
/ Three fields carried by the PRICE, not the product. Payment fires on the
ticket's NOT_SCANNED → SCANNED transition.

POURQUOI CE FICHIER EXISTE / WHY THIS FILE EXISTS
---------------------------------------------------
Aucun test ne couvrait ce chemin. Il verse de l'argent reel a des adherents et
traverse trois couches (signal, tache Celery, appel reseau au Fedow), dont deux
avalent leurs erreurs :

- `check_reward` (signals.py) enveloppe tout dans `except Exception` + log ;
- la tache (tasks.py) fait de meme.

Un versement qui echoue ne se voit donc NULLE PART : ni erreur a l'ecran, ni
billet en anomalie. L'adherent croit avoir ete credite, et ne l'est pas. Seul un
test qui relit le solde SUR LE FEDOW peut le detecter — c'est ce que fait ce
fichier.
/ Two layers swallow their exceptions and only log. A failed reward is visible
NOWHERE. Only reading the balance ON THE FEDOW can detect it.

CE QU'IL LAISSE DERRIERE LUI / WHAT IT LEAVES BEHIND
------------------------------------------------------
Un versement reel depuis le portefeuille du lieu vers celui d'un adherent neuf,
et une depense reelle par QR code. Le Fedow n'a pas de marche arriere. A lancer
sur un Fedow de developpement.
/ A real transfer from the venue's wallet, and a real spend. No rollback.

PREREQUIS / PREREQUISITES
--------------------------
- le serveur de developpement tourne ;
- Celery tourne : le versement passe par `.delay()`. Sans worker, le billet
  passe SCANNED et rien n'est jamais credite ;
- le Fedow est joignable, et le portefeuille du lieu detient assez de la monnaie
  de recompense pour payer les versements de ce test.

Lancement / Run:
    docker exec lespass_django poetry run pytest \
        /DjangoFiles/tests/e2e/test_recompense_au_scan_puis_qrcode.py -v
"""

import json
import re
import time
import uuid as uuid_module

import pytest

# Montant de la recompense, en unites de la monnaie (pas en centimes) : le champ
# `Price.fedow_reward_amount` est un montant « affiche », que la tache convertit
# en centimes (`int(dround(montant) * 100)`).
# / Reward amount in currency units, not cents: the task multiplies by 100.
RECOMPENSE_EN_UNITES = 2
RECOMPENSE_EN_CENTIMES = 200

# Ce que l'adherent depense ensuite par QR code. Volontairement INFERIEUR a la
# recompense : un debit exact se distingue ainsi d'un portefeuille vide.
# / Deliberately LOWER than the reward: an exact debit is thus distinguishable
# from an emptied wallet.
DEPENSE_EN_CENTIMES = 150

# La monnaie de recompense doit etre encaissable par QR code. `valid_payment` ne
# sait traduire que DEUX categories Fedow en moyen de paiement comptable : FED et
# TLF. Une recompense en monnaie temps (TIM) ou cadeau (TNF) serait creditee,
# puis debitee au paiement SANS qu'aucune vente ne soit enregistree en face
# (cf. CHANGELOG/2026-07-22-qrcode-flux-complet-et-deux-500.md).
# / The reward currency must be collectable by QR code: valid_payment only knows
# FED and TLF. A TIM or TNF reward would be debited with no sale recorded.
NOM_DE_LA_MONNAIE_DE_RECOMPENSE = "MonaLocalim"

# Les objets de scenario, crees une fois puis reutilises (get_or_create).
# / Scenario objects, created once then reused.
NOM_EVENT = "E2E Recompense — Chantier participatif"
NOM_PRODUIT = "E2E Recompense — Inscription"
NOM_TARIF = "E2E Recompense — Tarif recompense"


# ---------------------------------------------------------------------------
# Utilitaires
# ---------------------------------------------------------------------------


def _base_url(page):
    return page.url.split("/")[0] + "//" + page.url.split("/")[2]


def _jeton_csrf(page):
    """Le jeton CSRF pose par la derniere page visitee.
    / The CSRF token set by the last visited page."""
    for cookie in page.context.cookies():
        if cookie["name"] == "csrftoken":
            return cookie["value"]
    pytest.fail("Aucun cookie csrftoken : la page n'a pas ete visitee avant le POST.")


def _poster(page, chemin, donnees):
    """POST authentifie avec le jeton CSRF et le Referer attendu.
    / Authenticated POST with the CSRF token and expected Referer."""
    base = _base_url(page)
    return page.request.post(
        f"{base}{chemin}",
        form=donnees,
        headers={"X-CSRFToken": _jeton_csrf(page), "Referer": base + "/"},
    )


def _lire_json_marque(sortie, marqueur):
    """Extrait le JSON imprime par le shell Django derriere un marqueur.

    La sortie du shell melange le JSON attendu avec les avertissements Django et
    les logs applicatifs : on repere la ligne par un marqueur explicite plutot
    que de parier sur la derniere ligne.
    / The shell output mixes JSON with warnings and logs: find the line by an
    explicit marker rather than betting on the last line.
    """
    for ligne in sortie.splitlines():
        if ligne.startswith(marqueur):
            return json.loads(ligne[len(marqueur) :])
    pytest.fail(
        f"Le shell Django n'a rien imprime derriere '{marqueur}'. "
        f"Sortie : {sortie[-500:]}"
    )


def _solde_depensable(django_shell, email):
    """Le solde depensable de l'adherent, relu SUR LE FEDOW sans cache.

    `use_cache=False` est indispensable : c'est le versement qui vient d'avoir
    lieu qu'on veut observer, pas la valeur memorisee avant lui.
    / Read ON THE FEDOW without cache: we want the transfer that just happened,
    not the value memorised before it.
    """
    sortie = django_shell(
        "from AuthBillet.models import TibilletUser\n"
        "from fedow_connect.fedow_api import FedowAPI\n"
        f"user = TibilletUser.objects.get(email='{email}')\n"
        "print('SOLDE=' + str(\n"
        "    FedowAPI().wallet.get_total_fiducial_and_all_federated_token(\n"
        "        user, use_cache=False)))"
    )
    trouve = re.search(r"SOLDE=(\d+)", sortie)
    if not trouve:
        pytest.fail(f"Solde illisible depuis le Fedow. Sortie : {sortie[-400:]}")
    return int(trouve.group(1))


def _attendre_le_versement(django_shell, email, solde_de_depart, secondes=40):
    """Attend que le Fedow reflete le versement, ou rend le dernier solde lu.

    Le versement part par Celery (`.delay()`) : il est asynchrone, et la tache
    commence elle-meme par un `sleep(1)`. On interroge donc en boucle plutot que
    de parier sur un delai fixe.
    / The transfer goes through Celery and the task itself starts with a sleep:
    poll instead of betting on a fixed delay.
    """
    solde = solde_de_depart
    for _tentative in range(secondes // 2):
        solde = _solde_depensable(django_shell, email)
        if solde != solde_de_depart:
            return solde
        time.sleep(2)
    return solde


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def monnaie_de_recompense(django_shell):
    """La monnaie versee en recompense, telle qu'elle existe sur le Fedow.

    On ne la fabrique pas : verser une monnaie inventee ne prouverait rien sur
    le cas d'usage du lieu.
    / Not fabricated: rewarding an invented currency would prove nothing.
    """
    sortie = django_shell(
        "import json\n"
        "from fedow_public.models import AssetFedowPublic\n"
        "asset = AssetFedowPublic.objects.filter(\n"
        f"    name='{NOM_DE_LA_MONNAIE_DE_RECOMPENSE}').first()\n"
        "print('MONNAIE_JSON=' + json.dumps({\n"
        "    'uuid': str(asset.uuid) if asset else None,\n"
        "    'categorie': asset.category if asset else None,\n"
        "}))"
    )
    donnees = _lire_json_marque(sortie, "MONNAIE_JSON=")

    if not donnees["uuid"]:
        pytest.fail(
            f"La monnaie '{NOM_DE_LA_MONNAIE_DE_RECOMPENSE}' n'existe pas sur ce "
            "tenant : il n'y a rien a verser en recompense. Reseeder : docker "
            "exec lespass_django poetry run python manage.py demo_data_v2"
        )
    if donnees["categorie"] not in ("FED", "TLF"):
        pytest.fail(
            f"La monnaie de recompense est de categorie '{donnees['categorie']}'. "
            "Seules FED et TLF sont encaissables par QR code : une recompense "
            "dans une autre monnaie serait debitee sans qu'aucune vente ne soit "
            "enregistree en face."
        )
    return donnees


@pytest.fixture(scope="module")
def inscription_recompensee(django_shell, monnaie_de_recompense):
    """Un evenement et son tarif d'inscription, porteur d'une recompense.

    Les objets sont crees une fois puis reutilises : la base de developpement
    n'est pas reinitialisee entre les runs, et un teardown qui supprime des
    objets riches en cles etrangeres a deja vide des tables ici (PIEGES 12.4).
    / Objects are created once then reused: the dev DB is not reset between runs,
    and an aggressive teardown has already emptied tables here.
    """
    sortie = django_shell(
        "import json\n"
        "from datetime import timedelta\n"
        "from django.utils import timezone\n"
        "from BaseBillet.models import Event, Price, PriceSold, Product, ProductSold\n"
        "from fedow_public.models import AssetFedowPublic\n"
        f"asset = AssetFedowPublic.objects.get(uuid='{monnaie_de_recompense['uuid']}')\n"
        "event, _c = Event.objects.get_or_create(\n"
        f"    name='{NOM_EVENT}',\n"
        "    defaults={'datetime': timezone.now() + timedelta(days=30),\n"
        "              'published': True})\n"
        "produit, _c = Product.objects.get_or_create(\n"
        f"    name='{NOM_PRODUIT}', categorie_article=Product.FREERES)\n"
        "event.products.add(produit)\n"
        "tarif, _c = Price.objects.get_or_create(\n"
        f"    product=produit, name='{NOM_TARIF}', defaults={{'prix': 0}})\n"
        # On (re)pose la recompense a chaque run : c'est elle qui est testee, et
        # un tarif a moitie configure la rend inerte EN SILENCE (le code exige
        # les trois champs a la fois).
        # / Re-set the reward every run: a half-configured price makes it
        # SILENTLY inert, since the code requires all three fields together.
        "tarif.reward_on_ticket_scanned = True\n"
        "tarif.fedow_reward_asset = asset\n"
        f"tarif.fedow_reward_amount = {RECOMPENSE_EN_UNITES}\n"
        "tarif.save()\n"
        "produit_vendu, _c = ProductSold.objects.get_or_create(\n"
        "    product=produit, defaults={'categorie_article': produit.categorie_article})\n"
        "tarif_vendu, _c = PriceSold.objects.get_or_create(\n"
        "    productsold=produit_vendu, price=tarif, defaults={'prix': 0})\n"
        "print('INSCRIPTION_JSON=' + json.dumps({\n"
        "    'event_uuid': str(event.uuid),\n"
        "    'pricesold_uuid': str(tarif_vendu.uuid),\n"
        "}))"
    )
    return _lire_json_marque(sortie, "INSCRIPTION_JSON=")


@pytest.fixture
def adherent_inscrit(django_shell, inscription_recompensee):
    """Un adherent tout neuf, inscrit, avec un billet pas encore scanne.

    Neuf a chaque execution : un adherent reutilise porterait le solde de la
    recompense du run precedent, et l'assertion « le solde a augmente de
    exactement X » ne distinguerait plus un versement d'un report.
    / Fresh on every run: a reused member would carry the previous run's reward.
    """
    adresse = f"e2e-recompense-{uuid_module.uuid4().hex[:8]}@tibillet.test"

    sortie = django_shell(
        "import json\n"
        "from AuthBillet.utils import get_or_create_user\n"
        "from BaseBillet.models import Event, PriceSold, Reservation, Ticket\n"
        "from fedow_connect.fedow_api import FedowAPI\n"
        f"user = get_or_create_user('{adresse}', send_mail=False)\n"
        "user.email_valid = True\n"
        "user.save()\n"
        # Le portefeuille doit exister AVANT le versement : la tache de
        # recompense n'a pas de garde si le Fedow ne connait pas l'adherent.
        # / The wallet must exist BEFORE the transfer.
        "FedowAPI().wallet.get_or_create_wallet(user)\n"
        "user.refresh_from_db()\n"
        f"event = Event.objects.get(uuid='{inscription_recompensee['event_uuid']}')\n"
        f"tarif_vendu = PriceSold.objects.get(uuid='{inscription_recompensee['pricesold_uuid']}')\n"
        # `Reservation.objects.create(status=VALID)` ne declenche pas la machine
        # a etats (PIEGES 9.41) : pas d'envoi de billets par courriel ici, ce
        # qui est exactement ce qu'on veut — le sujet est la recompense.
        # / Creating a VALID reservation skips the state machine: no ticket
        # email, which is what we want here.
        "resa = Reservation.objects.create(\n"
        "    user_commande=user, event=event, status=Reservation.VALID)\n"
        "billet = Ticket.objects.create(\n"
        "    reservation=resa, pricesold=tarif_vendu, status=Ticket.NOT_SCANNED,\n"
        "    first_name='E2E', last_name='Recompense')\n"
        "print('ADHERENT_JSON=' + json.dumps({\n"
        "    'email': user.email,\n"
        "    'billet_pk': str(billet.pk),\n"
        "    'wallet_uuid': str(user.wallet.uuid) if user.wallet else None,\n"
        "}))"
    )
    donnees = _lire_json_marque(sortie, "ADHERENT_JSON=")

    if not donnees["wallet_uuid"]:
        pytest.fail(
            "L'adherent n'a pas de portefeuille : le Fedow n'a pas repondu. "
            "Verifier `FedowConfig.get_solo().can_fedow()`. Sans portefeuille, "
            "la recompense n'a nulle part ou aller."
        )
    return donnees


def _scanner_le_billet(page, billet_pk):
    """Scanne un billet par la vraie route admin, comme un gestionnaire.

    `TicketAdmin.scanner` redirige vers `request.META["HTTP_REFERER"]` sans
    valeur de repli : appeler cette route sans en-tete Referer leve une
    `KeyError` et repond 500. On le fournit donc explicitement.
    / TicketAdmin.scanner redirects to HTTP_REFERER with no fallback: calling it
    without a Referer header raises KeyError and answers 500.
    """
    base = _base_url(page)
    return page.request.get(
        f"{base}/admin/BaseBillet/ticket/{billet_pk}/scanner/",
        headers={"Referer": f"{base}/admin/BaseBillet/ticket/"},
    )


# ---------------------------------------------------------------------------
# Le parcours
# ---------------------------------------------------------------------------


def test_le_scan_du_billet_credite_puis_la_monnaie_se_depense_par_qrcode(
    page,
    login_as,
    login_as_admin,
    django_shell,
    instant_serveur,
    rapports_comptables,
    monnaie_de_recompense,
    inscription_recompensee,
    adherent_inscrit,
):
    """Scanner, etre credite sur le vrai Fedow, depenser, et ne pas etre credite deux fois.

    Chaque etape relit le solde SUR LE FEDOW. Les deux couches qui portent ce
    mecanisme avalent leurs exceptions : un versement rate est invisible partout
    ailleurs.
    / Every step re-reads the balance ON THE FEDOW. Both layers swallow their
    exceptions, so a failed transfer is invisible everywhere else.
    """
    email = adherent_inscrit["email"]
    billet_pk = adherent_inscrit["billet_pk"]

    # Borne basse des rapports comptables, posee avant toute action.
    # / Lower bound for the accounting reports, set before any action.
    debut_de_la_mesure = instant_serveur()

    solde_avant = _solde_depensable(django_shell, email)
    assert solde_avant == 0, (
        f"L'adherent vient d'etre cree, son solde devrait etre nul : {solde_avant}"
    )

    # --- 1. Le gestionnaire scanne le billet ---
    login_as_admin(page)
    page.goto("/admin/")
    reponse = _scanner_le_billet(page, billet_pk)
    assert reponse.status in (200, 302), (
        f"Le scan n'a pas abouti : {reponse.status} {reponse.text()[:300]}"
    )

    # --- 2. Le billet est passe scanne ---
    sortie = django_shell(
        "from BaseBillet.models import Ticket\n"
        f"billet = Ticket.objects.get(pk='{billet_pk}')\n"
        "print('SCANNE=' + str(billet.status == Ticket.SCANNED))"
    )
    assert "SCANNE=True" in sortie, (
        f"Le billet n'est pas passe a l'etat scanne : {sortie[-300:]}. Sans cette "
        "transition, le versement n'est jamais declenche."
    )

    # --- 3. LE FEDOW REEL a credite l'adherent, du montant exact ---
    solde_apres_scan = _attendre_le_versement(django_shell, email, solde_avant)
    assert solde_apres_scan == solde_avant + RECOMPENSE_EN_CENTIMES, (
        f"Le Fedow n'a pas verse la recompense attendue : "
        f"{solde_avant} → {solde_apres_scan}, attendu "
        f"{solde_avant + RECOMPENSE_EN_CENTIMES}.\n"
        "Si le solde n'a pas bouge du tout, les causes possibles sont : Celery "
        "arrete, le portefeuille du lieu vide de cette monnaie, ou un refus du "
        "Fedow — que `check_reward` et la tache avalent tous deux en silence. "
        "Les logs de `lespass_celery` portent la raison."
    )

    # --- 4. Le billet garde la trace du versement ---
    #
    # C'est cette trace qui interdit un second versement. Un versement qui
    # crediterait sans l'ecrire serait rejouable a chaque re-scan.
    # / This trace is what forbids a second transfer.
    sortie = django_shell(
        "import json\n"
        "from BaseBillet.models import Ticket\n"
        f"billet = Ticket.objects.get(pk='{billet_pk}')\n"
        "trace = (billet.metadata or {}).get('rewarded_from_ticket_scanned') or {}\n"
        "print('TRACE_JSON=' + json.dumps({\n"
        "    'montant': trace.get('amount'),\n"
        "    'asset': trace.get('asset'),\n"
        "    'transaction': trace.get('transaction_uuid'),\n"
        "}))"
    )
    trace = _lire_json_marque(sortie, "TRACE_JSON=")

    assert trace["transaction"], (
        f"Le billet ne porte aucune trace de versement : {trace}. Sans elle, un "
        "nouveau scan reverserait la recompense."
    )
    assert trace["montant"] == RECOMPENSE_EN_CENTIMES, (
        f"La trace ne porte pas le montant verse : {trace}"
    )
    assert trace["asset"] == monnaie_de_recompense["uuid"], (
        f"La trace ne designe pas la monnaie de recompense : {trace}, "
        f"attendu {monnaie_de_recompense['uuid']}."
    )

    # --- 5. L'adherent depense sa recompense par QR code ---
    reponse = _poster(
        page,
        "/qrcodescanpay/generate_qrcode/",
        {
            "amount": str(DEPENSE_EN_CENTIMES / 100),
            "asset_type": "EURO",
        },
    )
    assert reponse.ok, (
        f"Generation du QR code refusee : {reponse.status} {reponse.text()[:300]}"
    )

    sortie = django_shell(
        "from BaseBillet.models import LigneArticle, SaleOrigin\n"
        "ligne = LigneArticle.objects.filter(\n"
        "    sale_origin=SaleOrigin.QRCODE_MA, status=LigneArticle.CREATED\n"
        ").order_by('-datetime').first()\n"
        "print('DEMANDE=' + (ligne.uuid.hex if ligne else 'AUCUNE'))"
    )
    trouve = re.search(r"DEMANDE=(\S+)", sortie)
    assert trouve and trouve.group(1) != "AUCUNE", (
        "Le QR code n'a produit aucune demande de paiement en attente."
    )
    uuid_de_la_demande = trouve.group(1)

    login_as(page, email)
    page.goto("/my_account/")
    reponse = _poster(
        page,
        "/qrcodescanpay/valid_payment/",
        {
            "ligne_article_uuid_hex": uuid_de_la_demande,
        },
    )
    assert reponse.ok, f"Le paiement a echoue : {reponse.status} {reponse.text()[:400]}"
    assert "Insufficient Funds" not in reponse.text(), (
        "Le paiement a ete refuse pour fonds insuffisants alors que la "
        f"recompense de {RECOMPENSE_EN_CENTIMES} centimes couvre les "
        f"{DEPENSE_EN_CENTIMES} demandes. La monnaie versee n'est donc pas "
        "depensable — verifier sa categorie Fedow."
    )

    # --- 6. Le Fedow a debite le montant exact ---
    solde_apres_depense = _solde_depensable(django_shell, email)
    assert solde_apres_depense == solde_apres_scan - DEPENSE_EN_CENTIMES, (
        f"Le Fedow n'a pas debite le bon montant : "
        f"{solde_apres_scan} → {solde_apres_depense}, attendu "
        f"{solde_apres_scan - DEPENSE_EN_CENTIMES}."
    )

    # --- 7. La depense est enregistree comme une vente ---
    sortie = django_shell(
        "import json\n"
        "from BaseBillet.models import LigneArticle\n"
        f"ligne = LigneArticle.objects.filter(uuid='{uuid_de_la_demande}').first()\n"
        "print('VENTE_JSON=' + json.dumps({\n"
        "    'trouvee': bool(ligne),\n"
        "    'montant': int(ligne.amount) if ligne else None,\n"
        "    'validee': bool(ligne) and ligne.status == LigneArticle.VALID,\n"
        "    'moyen': ligne.payment_method if ligne else None,\n"
        "}))"
    )
    vente = _lire_json_marque(sortie, "VENTE_JSON=")
    assert vente["trouvee"] and vente["validee"], (
        f"Le portefeuille a ete debite mais aucune vente validee n'existe en "
        f"face : {vente}. L'adherent perd sa monnaie sans contrepartie comptable."
    )
    assert vente["montant"] == DEPENSE_EN_CENTIMES, (
        f"La vente ne porte pas le montant debite : {vente}"
    )

    # --- 7bis. Ce que la comptabilite voit de tout ce parcours ---
    #
    # Deux constats a verrouiller, aucun des deux evident.
    # / Two findings to lock down, neither obvious.
    comptes = rapports_comptables(debut_de_la_mesure)

    # a) Le VERSEMENT n'a laisse AUCUNE ecriture. Le lieu a emis de la monnaie —
    #    donc une dette envers l'adherent, a honorer chez ses producteurs — et
    #    rien ne l'enregistre cote Lespass. La seule trace est la metadata du
    #    billet et la transaction cote Fedow.
    #    L'asymetrie saute aux yeux au comptoir : une recharge CADEAU au point de
    #    vente, elle, ecrit bien une LigneArticle a moyen de paiement « offert ».
    # / The transfer leaves NO accounting entry: the venue issues currency (a debt
    #   towards the member) with nothing recording it. A GIFT top-up at the POS
    #   does write a line, with payment method "free" — hence the asymmetry.
    # On exclut par la CONSTANTE, jamais par le code a deux lettres : les codes
    # de `SaleOrigin` ne se devinent pas (`QRCODE_MA` vaut « QR », `LABOUTIK »
    # vaut « LB », `WEBHOOK` vaut « WK »). Une lettre inventee ne filtre rien et
    # l'assertion se met a mesurer autre chose.
    # / Exclude by CONSTANT, never by the two-letter code: SaleOrigin codes are
    # not guessable, and an invented one silently filters nothing.
    sortie = django_shell(
        "from AuthBillet.models import TibilletUser\n"
        "from BaseBillet.models import LigneArticle, SaleOrigin\n"
        f"user = TibilletUser.objects.get(email='{email}')\n"
        "lignes = LigneArticle.objects.filter(\n"
        "    wallet=user.wallet).exclude(sale_origin=SaleOrigin.QRCODE_MA)\n"
        "print('LIGNES_HORS_QRCODE=' + str(lignes.count()))"
    )
    assert "LIGNES_HORS_QRCODE=0" in sortie, (
        f"Le versement de recompense a laisse une ecriture comptable : "
        f"{sortie[-200:]}. Ce fichier decrit l'inverse — si une contrepartie a "
        "ete ajoutee, c'est une bonne nouvelle, mais il faut reecrire ce constat."
    )

    # b) La depense par QR code ne pese PAS sur le ticket de caisse, mais bien sur
    #    la cloture comptable en ligne. `QRCODE_MA` est hors de
    #    `ORIGINES_ENCAISSEES_PAR_LE_LIEU` tant que ces encaissements ne sont pas
    #    rattaches a un point de vente.
    # / The QR code spend does not weigh on the register ticket, but does on the
    #   online closure: QRCODE_MA is outside the venue-collected origins.
    assert comptes["caisse"]["especes"] == 0, (
        f"Une depense par QR code est entree dans les especes du ticket de "
        f"caisse : {comptes['caisse']}. Aucun billet n'est pourtant entre dans "
        "le tiroir."
    )
    assert comptes["en_ligne"].get("total", 0) == DEPENSE_EN_CENTIMES, (
        f"La cloture comptable en ligne ne porte pas la depense par QR code : "
        f"{comptes['en_ligne']} au lieu de {DEPENSE_EN_CENTIMES}. Elle "
        "n'apparait alors dans AUCUN des deux rapports."
    )

    # --- 8. Un SECOND scan ne reverse pas la recompense ---
    #
    # On remet le billet a « non scanne » pour reproduire la transition. C'est le
    # seul moyen de solliciter la garde d'idempotence : sans transition, le
    # signal ne part meme pas, et le test ne prouverait rien.
    # / Reset the ticket to unscanned to reproduce the transition. Without it the
    # signal never fires and the test would prove nothing about idempotency.
    solde_avant_rescan = solde_apres_depense
    django_shell(
        "from BaseBillet.models import Ticket\n"
        f"billet = Ticket.objects.get(pk='{billet_pk}')\n"
        "billet.status = Ticket.NOT_SCANNED\n"
        "billet.save()"
    )

    login_as_admin(page)
    page.goto("/admin/")
    reponse = _scanner_le_billet(page, billet_pk)
    assert reponse.status in (200, 302), (
        f"Le second scan n'a pas abouti : {reponse.status}"
    )

    # On laisse au versement le temps de partir s'il devait partir : conclure
    # trop tot ferait passer le test pour une bonne raison qui n'est pas la
    # garde, mais la lenteur de Celery.
    # / Give the transfer time to happen if it were going to: concluding too
    # early would pass for the wrong reason — Celery's latency, not the guard.
    solde_apres_rescan = _attendre_le_versement(
        django_shell,
        email,
        solde_avant_rescan,
        secondes=20,
    )
    assert solde_apres_rescan == solde_avant_rescan, (
        f"Un second scan a reverse la recompense : {solde_avant_rescan} → "
        f"{solde_apres_rescan}. La garde d'idempotence "
        "(`ticket.metadata['rewarded_from_ticket_scanned']`) ne protege plus : "
        "n'importe qui pouvant scanner peut se créditer en boucle."
    )
