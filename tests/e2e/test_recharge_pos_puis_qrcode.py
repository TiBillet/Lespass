"""
tests/e2e/test_recharge_pos_puis_qrcode.py
La frontiere entre les deux moteurs de monnaie, mesuree sur les vrais services.
/ The boundary between the two currency engines, measured on the real services.

LOCALISATION : tests/e2e/test_recharge_pos_puis_qrcode.py

CE QUE CE FICHIER ETABLIT / WHAT THIS FILE ESTABLISHES
-------------------------------------------------------
Lespass fait tourner DEUX moteurs de monnaie, et ils ne se voient pas :

- La recharge au comptoir (caisse LaBoutik v2) credite le moteur LOCAL.
  `_executer_recharges` (laboutik/views.py) appelle
  `TransactionService.creer_recharge` de `fedow_core`. Le produit de recharge
  connait sa monnaie par `Product.asset`, une cle etrangere vers
  `fedow_core.Asset` — jamais vers `fedow_public.AssetFedowPublic`.

- Le paiement par QR code debite le Fedow DISTANT.
  `valid_payment` (BaseBillet/views.py) appelle
  `FedowAPI.transaction.to_place_from_qrcode`, et lit le solde depensable avec
  `get_total_fiducial_and_all_federated_token`, qui n'interroge que le Fedow.

Le PORTEFEUILLE est commun aux deux (meme uuid des deux cotes) ; ce sont les
MONNAIES qui different. Consequence, mesuree ici et non supposee : l'argent
charge sur une carte au comptoir n'est pas depensable par QR code.

/ Two currency engines that cannot see each other: the counter top-up credits
the LOCAL engine (fedow_core), the QR code payment debits the REMOTE Fedow.
The wallet is shared, the currencies are not. Money loaded at the counter
cannot be spent online.

CE TEST DOIT DEVENIR ROUGE LE JOUR OU LES DEUX MOTEURS CONVERGERONT.
C'est son role : il decrit une frontiere, pas une fatalite. Quand la recharge
au comptoir creditera aussi le Fedow distant (ou quand le QR code consultera
`fedow_core`), l'etape 6 tombera et il faudra reecrire ce fichier.
/ THIS TEST MUST TURN RED WHEN THE TWO ENGINES CONVERGE. That is its purpose.

CE QU'IL LAISSE DERRIERE LUI / WHAT IT LEAVES BEHIND
-----------------------------------------------------
Une vraie vente en especes, une vraie recharge sur le moteur local, un vrai
portefeuille cree sur le Fedow de developpement. Rien n'est annule : la caisse
n'a pas de marche arriere, et le Fedow non plus. A lancer sur un environnement
de developpement dont on accepte qu'il soit remue.

PREREQUIS / PREREQUISITES
--------------------------
- le serveur de developpement tourne et repond sur le domaine du tenant ;
- le Fedow est joignable (`FedowConfig.can_fedow()` vaut True) — sans lui, le
  portefeuille de l'adherent ne peut pas etre cree ;
- les donnees POS de test existent (fixture `ensure_pos_data`).

Lancement / Run:
    docker exec lespass_django poetry run pytest \
        /DjangoFiles/tests/e2e/test_recharge_pos_puis_qrcode.py -v
"""

import json
import re
import uuid as uuid_module

import pytest

# Montant de la recharge au comptoir, en centimes. Il correspond au tarif « 5 »
# du produit « Recharge Monnaie locale » seede par `create_test_pos_data`.
# / Counter top-up amount in cents, matching the seeded « 5 » rate.
MONTANT_DE_LA_RECHARGE_CENTIMES = 500

# Le tag de la carte client de ce fichier. Stable d'un run a l'autre (la carte
# est reutilisee), mais rattachee a un adherent NEUF a chaque execution : c'est
# le rattachement qui porte l'isolation, pas le tag.
# `CarteCashless.tag_id` et `.number` sont limites a 8 caracteres (PIEGES 9.31).
# / Stable card tag, re-attached to a FRESH member on every run. 8 chars max.
TAG_DE_LA_CARTE_CLIENT = "E2ERECH1"

# La carte primaire du caissier, seedee par `create_test_pos_data`. Elle a acces
# a tous les points de vente, dont « Cashless ».
# / The cashier's primary card, seeded by create_test_pos_data.
TAG_DE_LA_CARTE_PRIMAIRE = "A49E8E2A"

# Le point de vente qui porte les produits de recharge (comportement « C »).
# / The point of sale carrying the top-up products (behaviour « C »).
NOM_DU_POINT_DE_VENTE = "Cashless"

# La monnaie du comptoir, nommee explicitement. Plusieurs produits de recharge
# euros coexistent sur ce point de vente — les tests controlvanne y laissent un
# asset « [vc_test] TLF », dont le signal post_save d'Asset cree le produit de
# recharge et le rattache au PV. Un `.first()` sans `order_by` designerait donc
# un produit different selon l'ordre rendu par la base (PIEGES 9.97).
# / Name the counter currency explicitly: several euro top-up products coexist on
# this POS, so an unordered .first() would pick a different one run to run.
NOM_DE_LA_MONNAIE_DU_COMPTOIR = "Monnaie locale"


# ---------------------------------------------------------------------------
# Utilitaires
# ---------------------------------------------------------------------------


def _jeton_csrf(page):
    """Recupere le jeton CSRF depuis les cookies du navigateur.

    `page.request.post` ne joint pas l'en-tete CSRF automatiquement et les vues
    DRF refusent la requete sans lui. Une page du site doit donc avoir ete
    visitee avant, pour que le cookie soit pose.
    / page.request.post does not attach the CSRF header; DRF refuses without it.
    """
    for cookie in page.context.cookies():
        if cookie["name"] == "csrftoken":
            return cookie["value"]
    pytest.fail("Aucun cookie csrftoken : la page n'a pas ete visitee avant le POST.")


def _poster(page, chemin, donnees):
    """POST authentifie avec le jeton CSRF et le Referer attendu.
    / Authenticated POST with the CSRF token and expected Referer."""
    base = page.url.split("/")[0] + "//" + page.url.split("/")[2]
    return page.request.post(
        f"{base}{chemin}",
        form=donnees,
        headers={"X-CSRFToken": _jeton_csrf(page), "Referer": base + "/"},
    )


def _lire_json_marque(sortie, marqueur):
    """Extrait le JSON imprime par le shell Django derriere un marqueur.

    Le shell melange le JSON attendu avec les avertissements Django et les logs
    applicatifs. On repere donc la ligne par un marqueur explicite plutot que de
    parier sur la derniere ligne de la sortie.
    / Extracts the JSON printed by the Django shell behind an explicit marker,
    since the shell output is mixed with Django warnings and app logs.
    """
    for ligne in sortie.splitlines():
        if ligne.startswith(marqueur):
            return json.loads(ligne[len(marqueur) :])
    pytest.fail(
        f"Le shell Django n'a rien imprime derriere '{marqueur}'. "
        f"Sortie : {sortie[-500:]}"
    )


def _soldes_des_deux_moteurs(django_shell, email, asset_local_uuid):
    """Le solde de l'adherent dans CHAQUE moteur, lu a la source.

    - `local` : la somme de ses jetons `fedow_core.Token` pour la monnaie du
      comptoir. C'est ce que la caisse credite.
    - `distant` : ce que le Fedow accepte de laisser depenser, relu SANS cache
      (`use_cache=False`) — c'est exactement le nombre que consulte le paiement
      par QR code avant d'accepter ou de refuser.
    / The member's balance in EACH engine, read at the source. `distant` is read
    without cache: it is the very number the QR code payment checks.

    La monnaie est passee en parametre, jamais devinee : plusieurs produits de
    recharge euros coexistent dans la base de developpement (les tests
    controlvanne y laissent un asset « [vc_test] TLF », dont le signal
    `post_save` d'Asset cree le produit de recharge). Chercher « le » produit de
    recharge par sa methode de caisse leve `MultipleObjectsReturned` en suite
    complete, tout en marchant quand le fichier est lance seul.
    / The currency is passed in, never guessed: several euro top-up products
    coexist in the dev DB, so looking one up by payment method raises
    MultipleObjectsReturned in a full run while working file-in-isolation.
    """
    sortie = django_shell(
        "import json\n"
        "from AuthBillet.models import TibilletUser\n"
        "from fedow_connect.fedow_api import FedowAPI\n"
        "from fedow_core.models import Token\n"
        f"user = TibilletUser.objects.get(email='{email}')\n"
        "solde_local = sum(\n"
        "    t.value for t in Token.objects.filter(\n"
        f"        wallet=user.wallet, asset__uuid='{asset_local_uuid}'))\n"
        "solde_distant = FedowAPI().wallet.get_total_fiducial_and_all_federated_token(\n"
        "    user, use_cache=False)\n"
        "print('SOLDES_JSON=' + json.dumps({\n"
        "    'local': int(solde_local), 'distant': int(solde_distant)}))"
    )
    return _lire_json_marque(sortie, "SOLDES_JSON=")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def comptoir(django_shell, ensure_pos_data):
    """Le point de vente de recharge, son produit et son tarif, tels qu'ils sont.

    On ne fabrique rien : le parcours doit s'appuyer sur les objets que la caisse
    utilise reellement, sinon il ne prouve rien sur son cas d'usage. C'est aussi
    ce qui fait que ce test detecte un seed casse au lieu de le contourner.
    / Nothing is fabricated: the journey must rely on the objects the POS really
    uses. This is also what makes the test detect a broken seed.
    """
    sortie = django_shell(
        "import json\n"
        "from BaseBillet.models import Product\n"
        "from laboutik.models import PointDeVente\n"
        f"pv = PointDeVente.objects.filter(name='{NOM_DU_POINT_DE_VENTE}').first()\n"
        "produit = (pv.products.filter(\n"
        "    methode_caisse=Product.RECHARGE_EUROS,\n"
        f"    asset__name='{NOM_DE_LA_MONNAIE_DU_COMPTOIR}').first()\n"
        "           if pv else None)\n"
        "tarif = (produit.prices.filter(\n"
        f"    publish=True, asset__isnull=True, prix={MONTANT_DE_LA_RECHARGE_CENTIMES / 100}\n"
        ").first() if produit else None)\n"
        "print('COMPTOIR_JSON=' + json.dumps({\n"
        "    'pv_uuid': str(pv.uuid) if pv else None,\n"
        "    'produit_uuid': str(produit.uuid) if produit else None,\n"
        "    'produit_nom': produit.name if produit else None,\n"
        "    'tarif_uuid': str(tarif.uuid) if tarif else None,\n"
        "    'asset_local_uuid': str(produit.asset.uuid) if (produit and produit.asset) else None,\n"
        "    'asset_local_nom': produit.asset.name if (produit and produit.asset) else None,\n"
        "}))"
    )
    donnees = _lire_json_marque(sortie, "COMPTOIR_JSON=")

    if not donnees["pv_uuid"]:
        pytest.fail(
            f"Point de vente '{NOM_DU_POINT_DE_VENTE}' introuvable. Reseeder : "
            "docker exec lespass_django poetry run python manage.py "
            "tenant_command create_test_pos_data --schema=lespass"
        )
    if not donnees["produit_uuid"] or not donnees["tarif_uuid"]:
        pytest.fail(
            f"Aucun produit de recharge en '{NOM_DE_LA_MONNAIE_DU_COMPTOIR}' a "
            f"{MONTANT_DE_LA_RECHARGE_CENTIMES / 100} € sur le PV "
            f"'{NOM_DU_POINT_DE_VENTE}' : la caisse n'a rien a encaisser. "
            f"Trouve : {donnees}"
        )
    if not donnees["asset_local_uuid"]:
        pytest.fail(
            f"Le produit '{donnees['produit_nom']}' n'a pas de `Product.asset`. "
            "Sans lui, `_executer_recharges` ignore l'article en silence et "
            "aucune monnaie n'est creditee (PIEGES 9.98)."
        )
    return donnees


@pytest.fixture
def adherent_avec_carte(django_shell):
    """Un adherent tout neuf, porteur d'une carte NFC et d'un portefeuille Fedow.

    Le portefeuille est cree AUPRES DU FEDOW, pas localement : c'est lui qui fait
    foi, et `_obtenir_ou_creer_wallet` renvoie `carte.user.wallet` des que la
    carte porte un user. Les deux moteurs partagent donc bien le meme uuid de
    portefeuille — ce qui rend la mesure de la frontiere possible.
    / A fresh member with an NFC card and a Fedow wallet. The wallet is created
    AT THE FEDOW (it is the source of truth), so both engines share the same
    wallet uuid — which is what makes measuring the boundary possible.

    La carte est reutilisee d'un run a l'autre mais RATTACHEE a l'adherent neuf :
    pas d'accumulation de cartes dans la base de developpement, et aucune
    suppression — les teardowns qui suppriment des objets riches en cles
    etrangeres ont deja vide des tables ici (PIEGES 12.4).
    / The card is reused but re-attached to the fresh member: no card build-up,
    and no deletion — aggressive E2E teardowns have already emptied tables here.
    """
    adresse = f"e2e-comptoir-{uuid_module.uuid4().hex[:8]}@tibillet.test"

    sortie = django_shell(
        "import json\n"
        "from AuthBillet.utils import get_or_create_user\n"
        "from BaseBillet.models import CarteCashless\n"
        "from fedow_connect.fedow_api import FedowAPI\n"
        "from laboutik.utils.test_helpers import reset_carte\n"
        f"user = get_or_create_user('{adresse}', send_mail=False)\n"
        "user.email_valid = True\n"
        "user.save()\n"
        "FedowAPI().wallet.get_or_create_wallet(user)\n"
        "user.refresh_from_db()\n"
        # La carte est peut-etre restee rattachee a l'adherent du run precedent :
        # on la detache avant de la reprendre.
        # / The card may still carry the previous run's member: detach first.
        f"reset_carte('{TAG_DE_LA_CARTE_CLIENT}')\n"
        "carte, _cree = CarteCashless.objects.get_or_create(\n"
        f"    tag_id='{TAG_DE_LA_CARTE_CLIENT}',\n"
        f"    defaults={{'number': '{TAG_DE_LA_CARTE_CLIENT}'}})\n"
        "carte.user = user\n"
        "carte.save()\n"
        "print('ADHERENT_JSON=' + json.dumps({\n"
        "    'email': user.email,\n"
        "    'wallet_uuid': str(user.wallet.uuid) if user.wallet else None,\n"
        "}))"
    )
    donnees = _lire_json_marque(sortie, "ADHERENT_JSON=")

    if not donnees["wallet_uuid"]:
        pytest.fail(
            "L'adherent n'a pas de portefeuille : le Fedow n'a pas repondu. "
            "Verifier `FedowConfig.get_solo().can_fedow()`. Sans portefeuille, "
            "ni la recharge au comptoir ni le paiement par QR code n'ont de sens."
        )
    return donnees


# ---------------------------------------------------------------------------
# Le parcours
# ---------------------------------------------------------------------------


def test_une_recharge_au_comptoir_n_est_pas_depensable_par_qrcode(
    page,
    login_as,
    login_as_admin,
    django_shell,
    instant_serveur,
    rapports_comptables,
    comptoir,
    adherent_avec_carte,
):
    """Recharger une carte a la caisse, puis constater que le QR code ne voit rien.

    Chaque etape relit l'etat a la source — le moteur local pour la caisse, le
    Fedow pour le paiement en ligne, les services de rapport pour la comptabilite
    — jamais une variable de test.
    / Every step reads state at the source: the local engine for the POS, the
    Fedow for the online payment, the report services for accounting.
    """
    email = adherent_avec_carte["email"]

    # Borne basse des rapports comptables, posee AVANT toute action : la fenetre
    # ne contiendra que ce que ce test produit, et les montants seront exacts.
    # / Lower bound set BEFORE any action: the window will hold only what this
    # test produces, so the amounts can be asserted exactly.
    debut_de_la_mesure = instant_serveur()

    soldes_avant = _soldes_des_deux_moteurs(django_shell, email, comptoir['asset_local_uuid'])
    assert soldes_avant["local"] == 0, (
        f"L'adherent est neuf, son solde local devrait etre nul : {soldes_avant}"
    )
    assert soldes_avant["distant"] == 0, (
        f"L'adherent est neuf, son solde Fedow devrait etre nul : {soldes_avant}"
    )

    # --- 1. La caisse affiche bien l'article de recharge ---
    #
    # On ouvre la vraie interface, et pas seulement la vue de paiement : un
    # produit de recharge sans `Product.asset` disparait de la grille sans
    # aucune erreur (PIEGES 9.98). Encaisser sans avoir vu la tuile laisserait
    # passer ce cas.
    # / Open the real interface, not just the payment view: a top-up product
    # without `Product.asset` vanishes from the grid silently.
    login_as_admin(page)
    page.goto(
        f"/laboutik/caisse/point_de_vente/"
        f"?uuid_pv={comptoir['pv_uuid']}&tag_id_cm={TAG_DE_LA_CARTE_PRIMAIRE}"
    )
    page.locator("#products").wait_for(state="visible", timeout=15_000)

    tuile_de_recharge = page.locator(f'[data-uuid="{comptoir["produit_uuid"]}"]')
    assert tuile_de_recharge.count() > 0, (
        f"L'article '{comptoir['produit_nom']}' n'apparait pas dans la grille du "
        f"point de vente '{NOM_DU_POINT_DE_VENTE}'. Le caissier ne peut pas le "
        "vendre — verifier `Product.asset` et l'appartenance au point de vente."
    )

    # --- 2. Le caissier encaisse la recharge en especes ---
    reponse = _poster(
        page,
        "/laboutik/paiement/payer/",
        {
            "moyen_paiement": "espece",
            "total": str(MONTANT_DE_LA_RECHARGE_CENTIMES),
            "given_sum": "0",
            "uuid_pv": comptoir["pv_uuid"],
            "tag_id_cm": TAG_DE_LA_CARTE_PRIMAIRE,
            "tag_id": TAG_DE_LA_CARTE_CLIENT,
            f"repid-{comptoir['produit_uuid']}--{comptoir['tarif_uuid']}": "1",
        },
    )
    assert reponse.ok, (
        f"La caisse a refuse la recharge : {reponse.status} {reponse.text()[:400]}"
    )

    # --- 3. Le moteur LOCAL a credite le portefeuille ---
    soldes_apres = _soldes_des_deux_moteurs(django_shell, email, comptoir['asset_local_uuid'])
    assert soldes_apres["local"] == MONTANT_DE_LA_RECHARGE_CENTIMES, (
        f"Le moteur local n'a pas credite la monnaie du comptoir "
        f"('{comptoir['asset_local_nom']}') : "
        f"{soldes_avant['local']} → {soldes_apres['local']}, "
        f"attendu {MONTANT_DE_LA_RECHARGE_CENTIMES}."
    )

    # --- 4. La vente laisse la bonne trace comptable ---
    #
    # Le tiroir a recu des especes : la ligne doit le dire, et etre rattachee au
    # point de vente. Sans `point_de_vente`, la recharge sort du ticket Z du
    # comptoir alors que l'argent y est physiquement.
    # / The drawer received cash: the line must say so, and be attached to the
    # point of sale — otherwise the top-up escapes the counter's Z report.
    sortie = django_shell(
        "import json\n"
        "from BaseBillet.models import LigneArticle, PaymentMethod, SaleOrigin\n"
        "from AuthBillet.models import TibilletUser\n"
        f"user = TibilletUser.objects.get(email='{email}')\n"
        "ligne = LigneArticle.objects.filter(\n"
        "    wallet=user.wallet).order_by('-datetime').first()\n"
        "print('LIGNE_JSON=' + json.dumps({\n"
        "    'trouvee': bool(ligne),\n"
        "    'montant': int(ligne.amount) if ligne else None,\n"
        "    'moyen': ligne.payment_method if ligne else None,\n"
        "    'origine': ligne.sale_origin if ligne else None,\n"
        "    'statut': ligne.status if ligne else None,\n"
        "    'asset': str(ligne.asset) if (ligne and ligne.asset) else None,\n"
        "    'pv': ligne.point_de_vente.name if (ligne and ligne.point_de_vente) else None,\n"
        "}))"
    )
    ligne = _lire_json_marque(sortie, "LIGNE_JSON=")

    assert ligne["trouvee"], (
        "La recharge n'a laisse aucune LigneArticle : le portefeuille a ete "
        "credite sans contrepartie comptable."
    )
    assert ligne["montant"] == MONTANT_DE_LA_RECHARGE_CENTIMES, (
        f"Montant comptabilise faux : {ligne}"
    )
    assert ligne["moyen"] == "CA", (
        f"La recharge a ete payee en especes, la ligne doit porter CASH : {ligne}"
    )
    assert ligne["statut"] == "V", f"La ligne n'est pas validee : {ligne}"
    assert ligne["pv"] == NOM_DU_POINT_DE_VENTE, (
        f"La ligne n'est pas rattachee au point de vente encaisseur : {ligne}. "
        "Sans ce rattachement, la recharge sort du ticket Z du comptoir."
    )
    assert ligne["asset"] == comptoir["asset_local_uuid"], (
        f"La ligne ne designe pas la monnaie creditee : {ligne}, "
        f"attendu {comptoir['asset_local_uuid']}."
    )

    # --- 4bis. La recharge PESE sur le ticket de caisse ---
    #
    # C'est ici que se joue le vrai contrat, et pas dans l'existence de la ligne :
    # une vente parfaitement enregistree reste invisible du rapport si elle porte
    # une origine que celui-ci ne lit pas. C'est arrive aux remboursements de
    # carte et aux ventes de tireuse — la ligne existait dans les deux cas.
    # / The real contract: a perfectly recorded sale stays invisible to the report
    # if its origin is not read. That happened to card refunds and tap sales.
    comptes = rapports_comptables(debut_de_la_mesure, NOM_DU_POINT_DE_VENTE)

    assert comptes["caisse"]["especes"] == MONTANT_DE_LA_RECHARGE_CENTIMES, (
        f"Le ticket de caisse n'a pas vu les especes de la recharge : "
        f"{comptes['caisse']['especes']} au lieu de "
        f"{MONTANT_DE_LA_RECHARGE_CENTIMES}. Le tiroir a recu l'argent, le "
        "ticket Z l'ignore."
    )
    assert comptes["caisse"]["total_recharges"] == MONTANT_DE_LA_RECHARGE_CENTIMES, (
        f"La section « recharges » du rapport ne porte pas le bon montant : "
        f"{comptes['caisse']['total_recharges']} au lieu de "
        f"{MONTANT_DE_LA_RECHARGE_CENTIMES}. Le gestionnaire ne peut pas "
        "justifier la monnaie qu'il a emise."
    )
    assert comptes["caisse"]["solde_caisse"] == MONTANT_DE_LA_RECHARGE_CENTIMES, (
        f"Le solde attendu dans le tiroir n'a pas suivi : "
        f"{comptes['caisse']['solde_caisse']} au lieu de "
        f"{MONTANT_DE_LA_RECHARGE_CENTIMES}. Le caissier trouvera un ecart en "
        "comptant sa caisse."
    )

    # La recharge est un encaissement du comptoir : elle n'a rien a faire dans la
    # cloture comptable des ventes en ligne, qui exclut justement `LABOUTIK`.
    # L'y voir signalerait un DOUBLE COMPTAGE du meme euro.
    # / A counter sale must not also appear in the online closure, which excludes
    # LABOUTIK. Seeing it there would mean the same euro is counted twice.
    assert comptes["en_ligne"].get("total", 0) == 0, (
        f"La recharge du comptoir est aussi entree dans la cloture comptable en "
        f"ligne ({comptes['en_ligne']}) : le meme euro est compte deux fois."
    )

    # --- 5. LA FRONTIERE : le Fedow distant, lui, n'a rien vu ---
    assert soldes_apres["distant"] == soldes_avant["distant"], (
        "Le Fedow distant a bouge apres une recharge au comptoir : les deux "
        f"moteurs se sont rejoints ({soldes_avant['distant']} → "
        f"{soldes_apres['distant']}). C'est peut-etre une bonne nouvelle, mais "
        "ce fichier decrit la frontiere inverse — le reecrire."
    )

    # --- 6. L'encaisseur genere un QR code du montant exact recharge ---
    reponse = _poster(
        page,
        "/qrcodescanpay/generate_qrcode/",
        {
            "amount": str(MONTANT_DE_LA_RECHARGE_CENTIMES / 100),
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

    # --- 7. L'adherent le paie : refuse, son solde en ligne est nul ---
    login_as(page, email)
    page.goto("/my_account/")
    reponse = _poster(
        page,
        "/qrcodescanpay/valid_payment/",
        {
            "ligne_article_uuid_hex": uuid_de_la_demande,
        },
    )
    assert reponse.ok, (
        f"L'ecran de refus n'a meme pas pu etre rendu : "
        f"{reponse.status} {reponse.text()[:400]}"
    )

    ecran = reponse.text()
    assert "Insufficient Funds" in ecran or "Fonds insuffisants" in ecran, (
        f"Le paiement n'a pas ete refuse pour fonds insuffisants alors que le "
        f"solde en ligne de l'adherent est nul. Ecran rendu : {ecran[:600]}"
    )

    # --- 8. Le constat, chiffre ---
    #
    # C'est l'assertion qui porte tout le fichier : l'adherent detient bien la
    # somme au comptoir, et le paiement en ligne ne la voit pas.
    # / The assertion carrying the whole file: the member holds the money at the
    # counter, and the online payment does not see it.
    soldes_finaux = _soldes_des_deux_moteurs(django_shell, email, comptoir['asset_local_uuid'])
    assert soldes_finaux["local"] == MONTANT_DE_LA_RECHARGE_CENTIMES, (
        f"Le refus en ligne a consomme la monnaie du comptoir : {soldes_finaux}"
    )
    assert soldes_finaux["distant"] == 0, (
        f"Le solde en ligne n'est plus nul : {soldes_finaux}. La frontiere que "
        "ce fichier decrit n'existe plus — le reecrire."
    )

    # --- 9. Le refus n'a pas consomme la demande de paiement ---
    #
    # L'adherent doit pouvoir recharger son compte en ligne puis rescanner le
    # meme QR code. Une demande consommee par un refus le lui interdirait.
    # / A refusal must not consume the request: the member has to be able to top
    # up online and scan the same QR code again.
    # `LigneArticle.CREATED` vaut « O », pas « C » — « C » est CANCELED. On lit
    # donc la constante plutot que d'ecrire la lettre, qui se confond.
    # / LigneArticle.CREATED is "O", not "C" (that is CANCELED). Read the
    # constant rather than hard-coding the confusable letter.
    sortie = django_shell(
        "from BaseBillet.models import LigneArticle\n"
        f"ligne = LigneArticle.objects.filter(uuid='{uuid_de_la_demande}').first()\n"
        "print('EN_ATTENTE=' + str(bool(ligne) and ligne.status == LigneArticle.CREATED))\n"
        "print('STATUT=' + (ligne.status if ligne else 'ABSENTE'))"
    )
    assert "EN_ATTENTE=True" in sortie, (
        f"La demande de paiement n'est plus en attente apres un refus pour fonds "
        f"insuffisants : {sortie[-200:]}. L'adherent ne peut plus la payer meme "
        "apres avoir recharge."
    )
