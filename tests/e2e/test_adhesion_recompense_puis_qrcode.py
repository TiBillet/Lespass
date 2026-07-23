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
- `trigger_A` fait de meme autour de `fedowAPI.membership.create` ;
- la tache (`tasks.py`) finit par `except Exception` + `logger.error`.

Un versement rate laisse donc une adhesion **d'apparence normale**, et un adherent
qui croit disposer de son pouvoir d'achat. Seule la relecture du solde SUR LE
FEDOW le detecte.

Indice utile au diagnostic : quand `trigger_A` leve avant sa fin, la ligne de
vente **reste a PAID** au lieu de passer VALID (c'est la derniere chose qu'il
fait). Une ligne d'adhesion bloquee a PAID est donc le symptome visible d'un
trigger interrompu. Le test l'assert explicitement.

CE QU'IL LAISSE DERRIERE LUI / WHAT IT LEAVES BEHIND
------------------------------------------------------
Une adhesion payee et un versement reel de 100 MonaLocalim depuis le portefeuille
du lieu, a chaque execution. C'est une EMISSION de monnaie locale par le lieu
(il en est l'origine), pas un prelevement sur un stock fini — mais elle gonfle
l'encours du lieu run apres run. A lancer sur un Fedow de developpement.
/ A real membership and a real 100-unit issuance per run. No rollback.

PREREQUIS / PREREQUISITES
--------------------------
- le serveur de developpement tourne ;
- Celery tourne : le versement passe par `.delay()` ;
- le Fedow est joignable.

Lancement / Run:
    docker exec lespass_django poetry run pytest \
        /DjangoFiles/tests/e2e/test_adhesion_recompense_puis_qrcode.py -v
"""

import json
import re
import time
import uuid as uuid_module

import pytest

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

    # --- 4. L'adherent depense sa monnaie par QR code ---
    #
    # C'est ce qui donne son sens au versement : une recompense non depensable ne
    # cree aucun pouvoir d'achat.
    # / This is what gives the transfer its meaning: an unspendable reward creates
    # no purchasing power.
    reponse = _poster(
        page,
        "/qrcodescanpay/generate_qrcode/",
        {"amount": str(DEPENSE_EN_CENTIMES / 100), "asset_type": "EURO"},
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
        {"ligne_article_uuid_hex": uuid_de_la_demande},
    )
    assert reponse.ok, f"Le paiement a echoue : {reponse.status} {reponse.text()[:400]}"
    assert "Insufficient Funds" not in reponse.text(), (
        f"Le paiement a ete refuse pour fonds insuffisants alors que la cotisation "
        f"vient de crediter {recompense} centimes. La monnaie versee par l'adhesion "
        "n'est donc pas depensable — verifier sa categorie Fedow."
    )

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
        f"{comptes['caisse']}. Elle y ferait double emploi avec la cloture "
        "comptable en ligne."
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
        assert not situation["caisse"], (
            f"La ligne de {intitule} ({uuid_de_la_ligne}) entre AUSSI dans le "
            "ticket de caisse : le meme euro serait compte deux fois."
        )

    # Le VERSEMENT de la recompense, lui, ne laisse aucune ecriture : le lieu
    # emet de la monnaie — une dette envers l'adherent — et rien ne l'enregistre
    # cote Lespass. Seules la metadata de la ligne et la transaction Fedow en
    # gardent trace.
    # / The transfer itself leaves no entry: the venue issues currency (a debt
    # towards the member) with nothing recording it on the Lespass side.
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
        "ete ajoutee, il faut reecrire ce constat."
    )
