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
alimentaire » : 100 MonaLocalim verses a chaque cotisation.

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
le paiement d'une adhesion). Les deux coexistent, et un tarif peut porter l'un
sans l'autre.
/ NOT to be confused with `reward_on_ticket_scanned`: same Fedow call, same
`fedow_reward_*` fields, different trigger.

POURQUOI CE FICHIER EXISTE / WHY THIS FILE EXISTS
---------------------------------------------------
Ce chemin n'avait aucun test, et il echoue en silence a trois niveaux :

- `TRIGGER_LigneArticlePaid_ActionByCategorie.__init__` (`triggers.py`) enveloppe
  l'appel du trigger dans `except Exception` + `logger.error` ;
- `trigger_A` avale de meme les erreurs de ses etapes ;
- la tache (`tasks.py`) finit par `except Exception` + `logger.error`.

Un versement rate laisse donc une adhesion **d'apparence normale**, et un adherent
qui croit disposer de son pouvoir d'achat. Seule la relecture du solde SUR LE
FEDOW le detecte.

Indice utile au diagnostic : quand `trigger_A` leve avant sa fin, la ligne de
vente **reste a PAID** au lieu de passer VALID (c'est la derniere chose qu'il
fait). Une ligne d'adhesion bloquee a PAID est donc le symptome visible d'un
trigger interrompu. Le test l'assert explicitement.

LA DEPENSE PASSE PAR LES BOUTONS DE « MON ESPACE » / THE SPEND GOES THROUGH THE BUTTONS
------------------------------------------------------------------------------------------
L'etape 4 se joue dans le navigateur, avec deux contextes, comme deux telephones :
- l'encaisseur (la `page` du test) : `/my_account/` → bouton « Initier un paiement »
  du bandeau → generateur → « Vérifier le paiement » ;
- l'adherent (un second contexte) : `/my_account/` → bouton « Scanner un QR code de
  paiement » sous « Ma carte » → scanner → page de validation → « Confirm Payment ».
Seule la camera est simulee : l'adherent ouvre le lien de paiement, qui est le contenu
exact du QR code. Pour une adresse du meme domaine, le scanner ne fait rien d'autre
(`scanner.html` : `window.location.href = scannedUrl`).
/ Step 4 runs in the browser with two contexts. Only the camera is simulated: the
member opens the payment link, which is the exact QR code content.

CE QU'IL LAISSE DERRIERE LUI / WHAT IT LEAVES BEHIND
------------------------------------------------------
Une adhesion payee et un versement reel de 100 MonaLocalim depuis le portefeuille
du lieu, a chaque execution. C'est une EMISSION de monnaie locale par le lieu
(il en est l'origine), pas un prelevement sur un stock fini — mais elle gonfle
l'encours du lieu run apres run. A lancer sur un Fedow de developpement.
L'adherent en depense ensuite 1,50 (vente par QR code au lieu).
/ A real membership and a real 100-unit issuance per run, then a 1.50 spend.
No rollback.

PREREQUIS / PREREQUISITES
--------------------------
- le serveur de developpement tourne ;
- Celery tourne : le versement passe par `.delay()` ;
- le Fedow est joignable ;
- le lieu `lespass` est en skin V2 (les boutons de l'etape 4 sont ceux de l'index
  V2). Sinon : `docker exec lespass_django poetry run python manage.py
  charger_site_lespass`.

Lancement / Run:
    docker exec lespass_django poetry run pytest \
        /DjangoFiles/tests/e2e/test_adhesion_recompense_puis_qrcode.py -v
"""

import json
import re
import time
import uuid as uuid_module
from urllib.parse import urlparse

import pytest
from playwright.sync_api import expect

from tests.e2e.conftest import BASE_URL, _capturer_la_page_en_echec

# Le produit et le tarif du cas d'usage, nommes explicitement. On ne cherche pas
# « un tarif qui porte une recompense » : plusieurs peuvent en porter, et le test
# doit dire lequel il verifie (PIEGES 12.13.bis).
# / Named explicitly: several prices may carry a reward, and the test must say
# which one it checks.
NOM_DU_PRODUIT = "Caisse de sécurité sociale alimentaire"
NOM_DU_TARIF = "Souscription mensuelle"

# Ce que l'adherent depense ensuite par QR code, en centimes. Volontairement une
# petite part de la recompense : un debit exact se distingue ainsi d'un
# portefeuille vide ou d'un versement approximatif.
# / A small share of the reward: an exact debit is thus distinguishable from an
# emptied wallet or an approximate transfer.
DEPENSE_EN_CENTIMES = 150


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
    / The shell output mixes JSON with warnings and logs.
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
    / Read ON THE FEDOW without cache.
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def lieu_en_skin_v2(django_shell):
    """Echoue, avec la consigne, si le lieu n'est pas en skin V2.

    Les boutons que l'etape 4 clique sont ceux de l'index V2 de « Mon espace ».
    Le skin se LIT en base, par `objects.first()`. Jamais `get_solo()` : il cree la
    ligne si elle manque, et passe par le cache memcached partage avec le serveur.
    Le test n'ecrit jamais le skin : c'est un reglage du lieu, pas du test.
    / Fails with what to do if the venue is not on the V2 skin. Read only, through
    objects.first(), never get_solo() (it creates the row and uses the shared cache).
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
    / Neither fabricated nor fixed up: the production configuration is what we
    want to check. A misconfigured price must fail this test, not be repaired.
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
        "    'prix': float(tarif.prix) if tarif else None,\n"
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
    # silently never pays. This is the only place that configuration is checked.
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

    donnees["montant_en_centimes"] = int(round(donnees["montant"] * 100))
    return donnees


@pytest.fixture
def adherent_en_attente_de_paiement(django_shell, tarif_de_la_caisse_alimentaire):
    """Un adherent tout neuf, dont l'adhesion attend son paiement.

    Neuf a chaque execution : un adherent reutilise porterait la recompense du run
    precedent, et « le solde a augmente de exactement X » ne distinguerait plus un
    versement d'un report.
    / Fresh on every run: a reused member would carry the previous run's reward.
    """
    adresse = f"e2e-cssa-{uuid_module.uuid4().hex[:8]}@tibillet.test"

    sortie = django_shell(
        "import json\n"
        "from AuthBillet.utils import get_or_create_user\n"
        "from BaseBillet.models import Membership, Price\n"
        "from fedow_connect.fedow_api import FedowAPI\n"
        f"user = get_or_create_user('{adresse}', send_mail=False)\n"
        "user.email_valid = True\n"
        "user.save()\n"
        # Le portefeuille doit exister AVANT le versement.
        # / The wallet must exist BEFORE the transfer.
        "FedowAPI().wallet.get_or_create_wallet(user)\n"
        "user.refresh_from_db()\n"
        f"tarif = Price.objects.get(uuid='{tarif_de_la_caisse_alimentaire['uuid']}')\n"
        # WAITING_PAYMENT : l'etat qu'exige `ajouter_paiement`, et celui d'une
        # adhesion prise au comptoir dont la cotisation n'est pas encore reglee.
        # / WAITING_PAYMENT: the state ajouter_paiement requires.
        "adhesion = Membership.objects.create(\n"
        "    user=user, price=tarif, first_name='E2E', last_name='Caisse',\n"
        "    status=Membership.WAITING_PAYMENT)\n"
        "print('ADHERENT_JSON=' + json.dumps({\n"
        "    'email': user.email,\n"
        "    'adhesion_pk': str(adhesion.pk),\n"
        "    'wallet_uuid': str(user.wallet.uuid) if user.wallet else None,\n"
        "}))"
    )
    donnees = _lire_json_marque(sortie, "ADHERENT_JSON=")

    if not donnees["wallet_uuid"]:
        pytest.fail(
            "L'adherent n'a pas de portefeuille : le Fedow n'a pas repondu. "
            "Verifier `FedowConfig.get_solo().can_fedow()`. Sans portefeuille, la "
            "recompense n'a nulle part ou aller."
        )
    return donnees


# ---------------------------------------------------------------------------
# Le parcours
# ---------------------------------------------------------------------------


def test_l_adhesion_payee_credite_le_portefeuille_puis_se_depense_par_qrcode(
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
    adherent_en_attente_de_paiement,
):
    """Cotiser, etre credite sur le vrai Fedow, puis depenser sa monnaie.

    Le paiement passe par la vraie route du gestionnaire — celle qu'il utilise
    quand une cotisation est reglee au comptoir en especes.
    / Payment goes through the manager's real route: the one used when a
    contribution is settled in cash at the counter.
    """
    email = adherent_en_attente_de_paiement["email"]
    adhesion_pk = adherent_en_attente_de_paiement["adhesion_pk"]
    recompense = tarif_de_la_caisse_alimentaire["montant_en_centimes"]

    # Borne basse des rapports comptables, posee avant toute action.
    # / Lower bound for the accounting reports, set before any action.
    debut_de_la_mesure = instant_serveur()

    solde_avant = _solde_depensable(django_shell, email)
    assert solde_avant == 0, (
        f"L'adherent vient d'etre cree, son solde devrait etre nul : {solde_avant}"
    )

    # --- 1. Le gestionnaire enregistre la cotisation, reglee en especes ---
    login_as_admin(page)
    page.goto("/admin/")
    reponse = _poster(
        page,
        f"/memberships/{adhesion_pk}/ajouter_paiement/",
        {
            "amount": str(tarif_de_la_caisse_alimentaire["prix"]),
            "payment_method": "CA",
        },
    )
    assert reponse.ok, (
        f"L'enregistrement du paiement a echoue : "
        f"{reponse.status} {reponse.text()[:400]}"
    )

    # --- 2. LE FEDOW REEL a credite l'adherent, du montant exact ---
    solde_apres_cotisation = _attendre_le_versement(django_shell, email, solde_avant)
    assert solde_apres_cotisation == solde_avant + recompense, (
        f"Le Fedow n'a pas verse la recompense d'adhesion : "
        f"{solde_avant} → {solde_apres_cotisation}, attendu {solde_avant + recompense}.\n"
        "Si le solde n'a pas bouge du tout : Celery arrete, Fedow injoignable, ou "
        "refus du Fedow — que le trigger et la tache avalent tous deux en silence. "
        "Les logs de `lespass_celery` portent la raison."
    )

    # --- 3. L'adhesion et sa ligne de vente sont dans l'etat attendu ---
    #
    # La ligne passe VALID en toute FIN de `trigger_A`. Une ligne restee a PAID
    # est donc le symptome visible d'un trigger interrompu en chemin — c'est le
    # seul signal exploitable, puisque l'exception est avalee.
    # / The line turns VALID at the very END of trigger_A. A line stuck at PAID
    # is the visible symptom of an interrupted trigger — the only usable signal.
    sortie = django_shell(
        "import json\n"
        "from BaseBillet.models import LigneArticle, Membership\n"
        f"adhesion = Membership.objects.get(pk='{adhesion_pk}')\n"
        "ligne = LigneArticle.objects.filter(\n"
        "    membership=adhesion).order_by('-datetime').first()\n"
        "recompense = (ligne.metadata or {}).get('fedow_reward') or {} if ligne else {}\n"
        "print('VENTE_JSON=' + json.dumps({\n"
        "    'uuid_ligne': str(ligne.uuid) if ligne else None,\n"
        "    'statut_ligne': ligne.status if ligne else None,\n"
        "    'montant_ligne': int(ligne.amount) if ligne else None,\n"
        "    'moyen': ligne.payment_method if ligne else None,\n"
        "    'statut_adhesion': adhesion.status,\n"
        "    'recompense_montant': recompense.get('amount'),\n"
        "    'recompense_asset': recompense.get('asset'),\n"
        "    'recompense_transaction': recompense.get('transaction_uuid'),\n"
        "}))"
    )
    vente = _lire_json_marque(sortie, "VENTE_JSON=")

    assert vente["statut_ligne"] == "V", (
        f"La ligne de vente de l'adhesion n'est pas validee : {vente}. Restee a "
        "'P', elle signale que `trigger_A` s'est interrompu avant sa derniere "
        "instruction — l'exception est avalee, ce statut est le seul indice."
    )
    assert vente["moyen"] == "CA", (
        f"La cotisation a ete reglee en especes, la ligne doit porter CASH : {vente}"
    )
    assert vente["recompense_transaction"], (
        f"La ligne ne porte aucune trace de versement : {vente}. Sans elle, "
        "un nouveau paiement sur la meme adhesion reverserait la recompense."
    )
    assert vente["recompense_montant"] == recompense, (
        f"La trace ne porte pas le montant verse : {vente}, attendu {recompense}."
    )
    assert vente["recompense_asset"] == tarif_de_la_caisse_alimentaire["asset_uuid"], (
        f"La trace ne designe pas la monnaie de recompense : {vente}, "
        f"attendu {tarif_de_la_caisse_alimentaire['asset_uuid']}."
    )

    # --- 4. L'adherent depense sa monnaie par QR code, par les boutons de « Mon espace » ---
    #
    # C'est ce qui donne son sens au versement : une recompense non depensable ne
    # cree aucun pouvoir d'achat.
    # Deux contextes de navigateur, comme deux telephones : l'encaisseur est la
    # `page` du test (deja connectee en admin a l'etape 1, et capturee par le
    # conftest en cas d'echec) ; l'adherent a son propre contexte.
    # / This is what gives the transfer its meaning. Two browser contexts, like two
    # phones: the cashier is the test `page`, the member has its own context.

    # 4.a L'encaisseur ouvre le generateur depuis le bandeau de « Mes responsabilites ».
    # / The cashier opens the generator from the "My responsibilities" banner.
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

    # 4.b Le QR code et le lien de paiement sont affiches.
    # / The QR code and the payment link are shown.
    bouton_copier_le_lien = page.locator("#copy-pay-link-btn")
    expect(bouton_copier_le_lien).to_be_visible()
    expect(
        page.locator("#qrcode-js").locator("canvas, img").filter(visible=True).first
    ).to_be_visible()

    # Le lien de paiement EST le contenu du QR code. L'uuid de la demande se lit
    # dedans : une demande creee par un test voisin ne peut pas etre prise a la place.
    # / The payment link IS the QR code content; the request uuid is read from it.
    lien_de_paiement = bouton_copier_le_lien.get_attribute("data-link") or ""
    trouve = re.search(r"/qrcodescanpay/([0-9a-f]{32})/process_qrcode$", lien_de_paiement)
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

    # 4.c Avant tout paiement, « Vérifier le paiement » repond « en attente ».
    # Sans ce controle, un bouton qui repondrait toujours « validé » passerait.
    # / Before any payment, the check answers "pending".
    zone_de_verification = page.locator("#check-payment-button")
    expect(zone_de_verification.locator("button")).to_contain_text("Vérifier le paiement")
    zone_de_verification.locator("button").click()
    expect(page.locator("#check-payment-button button")).to_contain_text(
        "Paiement en attente. Vérifier maintenant"
    )

    # 4.d L'adherent, sur son telephone : « Mon espace » → scanner → validation.
    # / The member, on their phone: "My space" → scanner → validation.
    contexte_de_l_adherent = browser.new_context(
        base_url=BASE_URL,
        ignore_https_errors=True,
    )
    page_de_l_adherent = contexte_de_l_adherent.new_page()
    parcours_de_l_adherent_termine = False
    try:
        login_as(page_de_l_adherent, email)
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
        # / Simulated: the camera. For a same-domain address the scanner only sets
        # window.location.href; check the domain, then open the link.
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
            f"vient de crediter {recompense} centimes. La monnaie versee par l'adhesion "
            "n'est donc pas depensable — verifier sa categorie Fedow."
        )
        # L'ecran « Paiement confirmé » : seul gabarit du parcours a en-tete vert.
        # / The "Payment Confirmed" screen: the only green-headed template here.
        expect(
            page_de_l_adherent.locator("#qrscanpay-container .card-header.bg-success")
        ).to_contain_text(re.compile(r"Payment Confirmed|Paiement confirmé"))
        parcours_de_l_adherent_termine = True
    finally:
        # La capture du conftest ne couvre que `page` : celle de l'adherent est
        # faite ici, seulement si son parcours s'est arrete en chemin.
        # / The conftest only captures `page`: capture the member's page here.
        if not parcours_de_l_adherent_termine:
            _capturer_la_page_en_echec(
                page_de_l_adherent, f"{request.node.nodeid}-adherent"
            )
        contexte_de_l_adherent.close()

    # 4.e L'encaisseur verifie : le paiement est valide.
    # / The cashier checks: the payment is validated.
    page.locator("#check-payment-button button").click()
    expect(page.locator("#check-payment-button")).to_contain_text("Paiement validé")

    # --- 5. Le Fedow a debite le montant exact ---
    solde_apres_depense = _solde_depensable(django_shell, email)
    assert solde_apres_depense == solde_apres_cotisation - DEPENSE_EN_CENTIMES, (
        f"Le Fedow n'a pas debite le bon montant : {solde_apres_cotisation} → "
        f"{solde_apres_depense}, attendu "
        f"{solde_apres_cotisation - DEPENSE_EN_CENTIMES}."
    )

    # --- 6. La depense est enregistree comme une vente ---
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
    # On situe CHAQUE ligne plutot que d'asserter un total : les lignes du
    # rapport en ligne arrivent aussi par webhook Stripe, donc de facon
    # asynchrone, et celui d'un test voisin peut tomber dans la meme fenetre.
    # / Locate EACH line instead of asserting a total: online-report lines also
    # arrive asynchronously, so a neighbouring test's webhook can land here.
    for intitule, uuid_de_la_ligne in (
        ("la cotisation", vente["uuid_ligne"]),
        ("la depense par QR code", uuid_de_la_demande),
    ):
        situation = rapports_qui_voient_la_ligne(uuid_de_la_ligne, debut_de_la_mesure)
        assert situation["en_ligne"], (
            f"La ligne de {intitule} ({uuid_de_la_ligne}) n'entre PAS dans la "
            "cloture comptable en ligne. Une vente que ni le ticket de caisse ni "
            "la cloture en ligne ne voient n'existe pour aucun comptable."
        )
        # Pas de verification « compte deux fois » : un seul rapport, et une vente
        # est soit d'un point de vente (caisse), soit en ligne, jamais les deux.
        # / No "counted twice" check: one report, a sale is in one scope only.

    # Le VERSEMENT de la recompense, lui, ne laisse aucune ecriture : le lieu
    # emet de la monnaie — une dette envers l'adherent — et rien ne l'enregistre
    # cote Lespass. Seules la metadata de la ligne et la transaction Fedow en
    # gardent trace.
    # On compte les lignes par leur VENTE, dont l'adherent est le client : une
    # ligne de vente ne porte ni carte ni portefeuille (Q-H2). Les deux ventes du
    # parcours sont mises de cote : la cotisation (sa ligne) et la depense par QR
    # code (son origine). Toute autre ligne d'une vente de l'adherent serait une
    # ecriture du versement.
    # / The transfer itself leaves no entry. Lines are counted through their sale,
    # whose client is the member (a line has no card nor wallet, Q-H2); the
    # contribution line and the QR code spend are set aside.
    sortie = django_shell(
        "from AuthBillet.models import TibilletUser\n"
        "from BaseBillet.models import LigneArticle, SaleOrigin\n"
        f"user = TibilletUser.objects.get(email='{email}')\n"
        "lignes = LigneArticle.objects.filter(vente__client=user).exclude(\n"
        "    sale_origin=SaleOrigin.QRCODE_MA).exclude(\n"
        f"    uuid='{vente['uuid_ligne']}')\n"
        "print('LIGNES_HORS_QRCODE=' + str(lignes.count()))"
    )
    assert "LIGNES_HORS_QRCODE=0" in sortie, (
        f"Une vente de l'adherent porte une ligne en plus de la cotisation et de "
        f"la depense par QR code : {sortie[-200:]}. Le versement de recompense "
        "n'ecrit aucune ecriture comptable : si une contrepartie existe, ce "
        "constat est a reecrire."
    )
