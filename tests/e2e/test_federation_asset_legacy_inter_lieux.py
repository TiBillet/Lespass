"""
tests/e2e/test_federation_asset_legacy_inter_lieux.py
La federation d'une monnaie legacy (`AssetFedowPublic`) entre deux lieux, avec le VRAI Fedow.
/ Federating a legacy currency (`AssetFedowPublic`) between two venues, with the REAL Fedow.

LOCALISATION : tests/e2e/test_federation_asset_legacy_inter_lieux.py

Spec : TECH_DOC/SESSIONS/FEDOW_IMPORT/14-spec-tests-federation-inter-lieux.md §3, tests B et C.

LES LIEUX / THE VENUES
-----------------------
- `lespass` (moteur v2) : emet la monnaie ;
- `festival` (moteur legacy, sans `module_monnaie_locale`) : le profil des lieux du reseau
  CLAF, qui restent sur l'ancien Fedow. Il est invite, accepte, puis la monnaie y est
  depensee.

LE PARCOURS (test B) / THE JOURNEY (test B)
--------------------------------------------
B1. L'admin ne cree plus d'asset legacy (`has_add_permission` = False, decision du
    2026-10-06) : la page `/admin/fedow_public/assetfedowpublic/add/` est refusee. Le test
    cree l'asset TLF de `lespass` comme le faisait `save_model` (ligne en base, puis
    `get_or_create_token_asset` sur le Fedow) : on le relit sur le Fedow.
B2. Sur la fiche de l'asset, il invite `festival` (`pending_invitations`).
B3. L'admin de `festival` voit l'invitation au-dessus de sa liste et clique « ACCEPTER »
    (`AssetAdmin.accept_invitation`, qui appelle `create_fed` dans le contexte du lieu
    d'origine).
B4. En base, `festival` passe des invitations aux lieux federes ; sur le Fedow,
    `get_accepted_assets()` lance pour `festival` renvoie l'asset ; la liste de `lespass`
    montre « Festival » parmi les lieux federes.
    La fiche de l'asset n'est PAS rouverte ici : le Fedow garde sa ventilation par lieu en
    cache 30 s, une lecture trop tot fausserait la verification de la ventilation.

LA SUITE (test C, meme lancement, meme asset) / THE FOLLOW-UP (test C)
-----------------------------------------------------------------------
C1. Chez `lespass` : le produit adhesion E2E (un seul, reutilise par son nom ; il doit
    exister sur le Fedow) et un tarif neuf qui verse 5,00 de la monnaie du test.
C2. Un adherent neuf adhere chez `lespass` ; l'admin enregistre la cotisation en especes
    (`/memberships/<pk>/ajouter_paiement/`). On attend le versement SUR LE FEDOW (500
    jetons), puis on relit sans cache son solde depensable chez `festival` (500).
C3. L'admin de `festival` cree le QR code dans le navigateur (skin classic) :
    /my_account/ → « My wallet » → « Initiate a payment » → 1,50.
C4. L'adherent, connecte sur `lespass`, ouvre le scanner ; le lien d'un AUTRE lieu passe
    par le vrai relais de session `/login/<b64>/redirect_session_to_another_tenant/`. Il
    valide le paiement chez `festival` (« Payment Confirmed »). Seule la camera est simulee.
C5. Le Fedow a debite 150 jetons de la monnaie de `lespass` (reste 350).
C6. La vente est chez `festival` (validee, 150, moyen LOCAL_EURO), rien chez `lespass`.
C7. Fiche de l'asset chez `lespass` : `festival` est federe, sa ligne de ventilation vaut
    1,50 (reperee par le portefeuille du lieu dans l'adresse du bouton de remise).
C8. L'admin de `lespass` valide le retour en banque de la part de `festival` : la ligne
    revient a 0, le Fedow enregistre une remise de 150 depuis le portefeuille de
    `festival`, et `/fedow/asset/<uuid>/retrieve_bank_deposits/` l'affiche.

L'admin des E2E (`ADMIN_EMAIL`) est superuser : il administre les deux lieux. Chez
`festival`, il n'est pas dans `client_admin` : il voit « Initiate a payment » parce que la
regle suit la permission des routes du generateur (spec 10, D3).

LES CACHES DU FEDOW DE DEV / THE DEV FEDOW CACHES
--------------------------------------------------
Le Fedow de dev tourne avec TEST=1 : son cache est propre a chacun de ses 5 processus
(tests/PIEGES.md 9.116). La liste des monnaies acceptees par un lieu y reste 120 s, la
ventilation par lieu 30 s. Le test relit donc `get_accepted_assets()` jusqu'a 125 s (B4),
attend 125 s apres l'acceptation avant le paiement (C4), et recharge la fiche jusqu'a
~45 s (C7, C8). Un lancement dure environ 2 min 30.
/ The dev Fedow cache is per process: the test re-reads, waits and reloads accordingly.

CE QU'IL LAISSE DERRIERE LUI / WHAT IT LEAVES BEHIND
------------------------------------------------------
A chaque lancement, sur le Fedow de DEV, sans retour en arriere : un asset TLF
`E2E Fed legacy <suffixe>` et sa federation avec `festival`, un portefeuille d'adherent,
un versement de 500 jetons, un paiement de 150 chez `festival` et une remise en banque de
150. En base : l'asset legacy (garde, decision Q8), un tarif `E2E <suffixe>` du produit
« E2E Adhesion monnaie federee » (non publie), l'adherent `e2e-fed-<suffixe>@tibillet.test`
et son adhesion, la vente chez `festival`. A lancer sur un Fedow de developpement
uniquement, seul (jamais deux pytest en parallele).
/ Per run, on the DEV Fedow, no rollback: asset, federation, wallet, reward, payment,
bank deposit.

PREREQUIS / PREREQUISITES
--------------------------
- le serveur de developpement tourne, le Fedow de dev repond, Celery tourne (versement) ;
- moteurs de depart : `lespass` v2, `festival` legacy (fixture `moteurs_de_depart_verifies`) ;
- `lespass` et `festival` relies au Fedow (`FedowConfig.can_fedow()`), `festival` sans
  `module_monnaie_locale` (verifie au depart, echec explicite sinon).

Lancement / Run:
    make e2e ARGS="tests/e2e/test_federation_asset_legacy_inter_lieux.py"
"""

import base64
import json
import re
import time
import uuid

import pytest
from playwright.sync_api import expect

from tests.e2e.conftest import BASE_URL, DOMAIN, _capturer_la_page_en_echec

pytestmark = pytest.mark.e2e

LIEU_EMETTEUR = "lespass"
LIEU_FEDERE = "festival"
URL_DU_LIEU_FEDERE = f"https://{LIEU_FEDERE}.{DOMAIN}"
URL_DU_LIEU_EMETTEUR = f"https://{LIEU_EMETTEUR}.{DOMAIN}"
URL_DE_LA_LISTE_LEGACY = "/admin/fedow_public/assetfedowpublic/"
MARQUEUR_DU_RESULTAT = "RESULTAT_JSON="

# Test C : un seul produit adhesion E2E, reutilise d'un lancement a l'autre (chaque
# produit adhesion cree un asset sur le Fedow) ; un tarif neuf par lancement.
# / Test C: one reused E2E membership product; a fresh price per run.
NOM_DU_PRODUIT_ADHESION_E2E = "E2E Adhesion monnaie federee"
PRIX_DE_L_ADHESION = "10.00"
RECOMPENSE_DE_L_ADHESION = "5.00"
RECOMPENSE_EN_CENTIMES = 500
# Une petite part de la recompense : un debit exact se distingue d'un portefeuille vide.
# / A small share of the reward: an exact debit differs from an emptied wallet.
DEPENSE_EN_CENTIMES = 150

# Le Fedow garde en cache 120 s la liste des monnaies acceptees par un lieu
# (`Place.cached_federated_with`). Le Fedow de dev tourne avec TEST=1 : ce cache est
# propre a chacun de ses processus, et la creation d'une federation ne vide que celui
# qui la cree. 120 s, plus une marge.
# / The Fedow caches a venue's accepted assets for 120 s, per process on the dev Fedow.
DELAI_DU_CACHE_DES_FEDERATIONS_DU_FEDOW = 125


def _lire_en_base(django_shell, code_python, schema=LIEU_EMETTEUR):
    """
    Lance du code dans le lieu `schema` et renvoie le JSON qu'il imprime derriere le
    marqueur `RESULTAT_JSON=`. Le marqueur isole le resultat des autres impressions
    (le client Fedow peut ecrire sur la sortie standard).
    / Runs code in the `schema` venue and returns the JSON printed after the marker.
    """
    sortie = django_shell(code_python, schema=schema)
    for ligne in reversed(sortie.splitlines()):
        if ligne.startswith(MARQUEUR_DU_RESULTAT):
            return json.loads(ligne[len(MARQUEUR_DU_RESULTAT) :])
    pytest.fail(
        f"Le code lance dans `{schema}` n'a rien imprime derriere "
        f"{MARQUEUR_DU_RESULTAT!r}. Sortie : {sortie[-800:]}"
    )


def _jeton_csrf(page):
    """
    Le jeton CSRF pose par la derniere page visitee.
    / The CSRF token set by the last visited page.
    """
    for cookie in page.context.cookies():
        if cookie["name"] == "csrftoken":
            return cookie["value"]
    pytest.fail("Aucun cookie csrftoken : la page n'a pas ete visitee avant le POST.")


def _poster(page, chemin, donnees):
    """
    POST authentifie sur le lieu de la page courante, avec le jeton CSRF et le Referer.
    / Authenticated POST on the current page's venue, with CSRF token and Referer.
    """
    morceaux_de_l_url = page.url.split("/")
    base_du_lieu = morceaux_de_l_url[0] + "//" + morceaux_de_l_url[2]
    return page.request.post(
        f"{base_du_lieu}{chemin}",
        form=donnees,
        headers={"X-CSRFToken": _jeton_csrf(page), "Referer": base_du_lieu + "/"},
    )


def _jetons_de_l_asset_sur_le_fedow(django_shell, email, uuid_de_l_asset):
    """
    Les jetons que l'adherent detient de CETTE monnaie, relus sur le Fedow sans cache.
    / The member's tokens of THIS currency, read on the Fedow without cache.
    """
    return _lire_en_base(
        django_shell,
        "import json\n"
        "from AuthBillet.models import TibilletUser\n"
        "from fedow_connect.fedow_api import FedowAPI\n"
        f"user = TibilletUser.objects.get(email={email!r})\n"
        "portefeuille = FedowAPI().wallet.retrieve_by_signature(user).validated_data\n"
        "jetons = 0\n"
        "for token in portefeuille['tokens']:\n"
        f"    if str(token['asset']['uuid']) == {uuid_de_l_asset!r}:\n"
        "        jetons += int(token['value'])\n"
        "print('RESULTAT_JSON=' + json.dumps(jetons))\n",
    )


def _attendre_une_valeur(lire_la_valeur, valeur_attendue, secondes):
    """
    Relit une valeur toutes les 2 s jusqu'a la valeur attendue ; rend la derniere lue.
    / Re-reads a value every 2 s until it matches; returns the last value read.
    """
    valeur_lue = lire_la_valeur()
    fin_de_l_attente = time.monotonic() + secondes
    while valeur_lue != valeur_attendue and time.monotonic() < fin_de_l_attente:
        time.sleep(2)
        valeur_lue = lire_la_valeur()
    return valeur_lue


def _total_de_la_ligne_apres_rechargements(page, url_de_la_fiche, ligne, motif_attendu):
    """
    Recharge la fiche de l'asset jusqu'a ce que la colonne « Total » de `ligne` suive
    `motif_attendu`, pendant ~45 s au plus ; rend le dernier total lu (None si la ligne
    est absente). Le Fedow garde la ventilation par lieu en cache 30 s
    (`total_by_place_with_uuid`) : un seul chargement lirait une valeur perimee.
    / Reloads the asset page until the row total matches (~45 s max): the Fedow
    caches the per-venue breakdown for 30 s.
    """
    total_lu = None
    fin_de_l_attente = time.monotonic() + 45
    while True:
        page.goto(url_de_la_fiche)
        page.wait_for_load_state("networkidle")
        if ligne.count() > 0:
            total_lu = ligne.locator("td").nth(1).inner_text().strip()
            if motif_attendu.match(total_lu):
                return total_lu
        if time.monotonic() > fin_de_l_attente:
            return total_lu
        time.sleep(3)


def _etat_de_l_asset_legacy_en_base(django_shell, nom_de_l_asset):
    """
    L'asset legacy, ses invitations et ses lieux federes, lus en base (schema public).
    / The legacy asset, its invitations and federated venues, read from the DB.
    """
    return _lire_en_base(
        django_shell,
        "import json\n"
        "from fedow_public.models import AssetFedowPublic\n"
        f"asset = AssetFedowPublic.objects.filter(name={nom_de_l_asset!r}).first()\n"
        "if asset is None:\n"
        "    print('RESULTAT_JSON=' + json.dumps({'existe': False}))\n"
        "else:\n"
        "    print('RESULTAT_JSON=' + json.dumps({\n"
        "        'existe': True,\n"
        "        'uuid': str(asset.uuid),\n"
        "        'categorie': asset.category,\n"
        "        'lieu_d_origine': asset.origin.schema_name,\n"
        "        'invitations': sorted(asset.pending_invitations.values_list('schema_name', flat=True)),\n"
        "        'lieux_federes': sorted(asset.federated_with.values_list('schema_name', flat=True)),\n"
        "    }))\n",
    )


@pytest.fixture(scope="module")
def lieux_relies_au_fedow(django_shell, moteurs_de_depart_verifies):
    """
    Echoue, avec la consigne, si un des deux lieux n'est pas relie au Fedow, ou si
    `festival` a `module_monnaie_locale` allume (il ne jouerait plus le role d'un lieu
    CLAF, sur l'ancien Fedow seul).
    / Fails with what to do if a venue is not linked to Fedow, or if `festival` has the
    local currency module on.

    Lecture seule : `Configuration.objects.first()`, jamais `get_solo()`.
    / Read only, never get_solo().
    """
    for lieu in [LIEU_EMETTEUR, LIEU_FEDERE]:
        etat_du_lieu = _lire_en_base(
            django_shell,
            "import json\n"
            "from BaseBillet.models import Configuration\n"
            "from fedow_connect.models import FedowConfig\n"
            "configuration = Configuration.objects.first()\n"
            "configuration_fedow = FedowConfig.objects.first()\n"
            "print('RESULTAT_JSON=' + json.dumps({\n"
            "    'relie_au_fedow': bool(configuration_fedow and configuration_fedow.can_fedow()),\n"
            "    'monnaie_locale': bool(configuration and configuration.module_monnaie_locale),\n"
            "}))\n",
            schema=lieu,
        )
        if not etat_du_lieu["relie_au_fedow"]:
            pytest.fail(
                f"Le lieu `{lieu}` n'est pas relie au Fedow de dev (FedowConfig.can_fedow() "
                "faux). Relancer la demo (demo_data_v2) avec le Fedow de dev qui repond."
            )
        if lieu == LIEU_FEDERE and etat_du_lieu["monnaie_locale"]:
            pytest.fail(
                f"`{LIEU_FEDERE}` a le module « Monnaie locale » allume : il ne joue plus le "
                "role d'un lieu CLAF (ancien Fedow seul). L'eteindre dans son admin."
            )


@pytest.fixture
def nom_de_l_asset_legacy():
    """
    Un nom d'asset unique par lancement : la base et le Fedow de dev gardent les assets
    des lancements precedents. L'asset legacy n'est pas archive en fin de test (decision
    Q8 du suivi : on garde l'asset legacy).
    / A unique asset name per run; the legacy asset is kept (decision Q8).
    """
    return f"E2E Fed legacy {uuid.uuid4().hex[:6]}"


def test_parcours_monnaie_federee_entre_deux_lieux(
    page,
    browser,
    request,
    login_as,
    login_as_admin,
    login_as_admin_on_subdomain,
    django_shell,
    lieux_relies_au_fedow,
    nom_de_l_asset_legacy,
):
    """
    Une monnaie emise par `lespass` est federee avec `festival` (lieu legacy), sur le
    vrai Fedow.
    / A currency issued by `lespass` is federated with `festival` (legacy venue), on the
    real Fedow.
    """
    nom_de_l_asset = nom_de_l_asset_legacy

    # ------------------------------------------------------------------
    # B1. L'admin ne peut plus creer d'asset legacy : la page d'ajout est refusee.
    #     Le test cree l'asset TLF de `lespass` comme le faisait `save_model` ; il
    #     existe sur le Fedow.
    #     / The admin can no longer create a legacy asset; the test creates it like
    #     `save_model` did; it exists on the Fedow.
    # ------------------------------------------------------------------
    login_as_admin(page)
    reponse_de_la_page_d_ajout = page.goto(f"{URL_DE_LA_LISTE_LEGACY}add/")
    assert reponse_de_la_page_d_ajout.status == 403, (
        "La page d'ajout d'un asset legacy doit etre refusee (has_add_permission = False), "
        f"elle repond {reponse_de_la_page_d_ajout.status}."
    )

    creation = _lire_en_base(
        django_shell,
        "import json\n"
        "from django.db import connection\n"
        "from fedow_connect.fedow_api import FedowAPI\n"
        "from fedow_connect.models import FedowConfig\n"
        "from fedow_public.models import AssetFedowPublic\n"
        "configuration_fedow = FedowConfig.get_solo()\n"
        "asset = AssetFedowPublic.objects.create(\n"
        f"    name={nom_de_l_asset!r},\n"
        "    currency_code='EUR',\n"
        "    category=AssetFedowPublic.TOKEN_LOCAL_FIAT,\n"
        "    origin=connection.tenant,\n"
        "    wallet_origin=configuration_fedow.wallet,\n"
        ")\n"
        "_asset, cree = FedowAPI(fedow_config=configuration_fedow).asset.get_or_create_token_asset(asset)\n"
        "print('RESULTAT_JSON=' + json.dumps({'cree_sur_le_fedow': bool(cree)}))\n",
    )
    assert creation["cree_sur_le_fedow"], (
        f"L'asset legacy « {nom_de_l_asset} » existait deja sur le Fedow."
    )

    etat_apres_creation = _etat_de_l_asset_legacy_en_base(django_shell, nom_de_l_asset)
    assert etat_apres_creation["existe"], (
        f"L'asset legacy « {nom_de_l_asset} » n'existe pas en base apres sa creation."
    )
    assert etat_apres_creation["lieu_d_origine"] == LIEU_EMETTEUR
    uuid_de_l_asset = etat_apres_creation["uuid"]

    asset_lu_sur_le_fedow = _lire_en_base(
        django_shell,
        "import json\n"
        "from fedow_connect.fedow_api import FedowAPI\n"
        f"asset = FedowAPI().asset.retrieve(uuid={uuid_de_l_asset!r})\n"
        "print('RESULTAT_JSON=' + json.dumps({'uuid': str(asset['uuid']), 'nom': asset['name'],\n"
        "                  'categorie': asset['category']}))\n",
    )
    assert asset_lu_sur_le_fedow["uuid"] == uuid_de_l_asset
    assert asset_lu_sur_le_fedow["nom"] == nom_de_l_asset
    assert asset_lu_sur_le_fedow["categorie"] == "TLF"

    # ------------------------------------------------------------------
    # B2. Fiche de l'asset : l'admin de `lespass` invite `festival`.
    #     Autocompletion select2 de l'admin Django (tests/PIEGES.md).
    #     / Asset page: the `lespass` admin invites `festival`.
    # ------------------------------------------------------------------
    page.goto(f"{URL_DE_LA_LISTE_LEGACY}{uuid_de_l_asset}/change/")
    page.wait_for_load_state("networkidle")
    champ_de_recherche_des_invitations = page.locator(
        ".field-pending_invitations .select2-search__field"
    )
    expect(champ_de_recherche_des_invitations).to_be_visible(timeout=10000)
    champ_de_recherche_des_invitations.click()
    with page.expect_response(
        lambda reponse: (
            "/admin/autocomplete/" in reponse.url and "term=Festival" in reponse.url
        )
    ):
        champ_de_recherche_des_invitations.press_sequentially("Festival", delay=30)
    option_festival = page.locator(
        ".select2-results__option:not(.loading-results)", has_text="Festival"
    ).first
    expect(option_festival).to_be_visible(timeout=10000)
    option_festival.click()
    page.locator('button[name="_save"], input[name="_save"]').first.click()
    page.wait_for_load_state("networkidle")

    etat_apres_invitation = _etat_de_l_asset_legacy_en_base(
        django_shell, nom_de_l_asset
    )
    assert etat_apres_invitation["invitations"] == [LIEU_FEDERE], (
        f"Invitations en base : {etat_apres_invitation['invitations']}, attendu "
        f"[{LIEU_FEDERE!r}]."
    )
    assert etat_apres_invitation["lieux_federes"] == []

    # ------------------------------------------------------------------
    # B3. L'admin de `festival` voit l'invitation et clique « ACCEPTER ».
    #     / The `festival` admin sees the invitation and clicks "ACCEPT".
    # ------------------------------------------------------------------
    login_as_admin_on_subdomain(page, LIEU_FEDERE)
    page.goto(f"{URL_DU_LIEU_FEDERE}{URL_DE_LA_LISTE_LEGACY}")
    page.wait_for_load_state("networkidle")
    ligne_d_invitation = page.locator("div.py-3", has_text=nom_de_l_asset).first
    expect(ligne_d_invitation).to_be_visible(timeout=10000)
    expect(ligne_d_invitation).to_contain_text("Lespass")
    ligne_d_invitation.locator('button[type="submit"]').click()
    instant_de_la_federation = time.monotonic()
    page.wait_for_load_state("networkidle")

    # ------------------------------------------------------------------
    # B4. `festival` est federe : en base, sur le Fedow, et dans la liste de `lespass`.
    #     / `festival` is federated: in the DB, on the Fedow, in `lespass`'s list.
    # ------------------------------------------------------------------
    etat_apres_acceptation = _etat_de_l_asset_legacy_en_base(
        django_shell, nom_de_l_asset
    )
    assert etat_apres_acceptation["lieux_federes"] == [LIEU_FEDERE], (
        f"Apres le clic sur « ACCEPTER » chez `{LIEU_FEDERE}`, lieux federes en base : "
        f"{etat_apres_acceptation['lieux_federes']}, invitations : "
        f"{etat_apres_acceptation['invitations']}. Page affichee apres le clic : "
        f"{page.url}. Le formulaire du panneau doit poster vers "
        f"{URL_DE_LA_LISTE_LEGACY}accept_invitation/<uuid>/ "
        "(Administration/templates/admin/asset/asset_list_before.html)."
    )
    assert etat_apres_acceptation["invitations"] == []

    # Le Fedow de dev peut repondre depuis un processus dont le cache ignore encore la
    # federation (120 s, tests/PIEGES.md 9.116) : on relit jusqu'a ce delai.
    # / The dev Fedow may answer from a process whose cache predates the federation.
    def _l_asset_est_accepte_par_festival():
        assets_acceptes = _lire_en_base(
            django_shell,
            "import json\n"
            "from fedow_connect.fedow_api import FedowAPI\n"
            "assets = FedowAPI().asset.get_accepted_assets()\n"
            "print('RESULTAT_JSON=' + json.dumps(sorted(str(asset['uuid']) for asset in assets)))\n",
            schema=LIEU_FEDERE,
        )
        return uuid_de_l_asset in assets_acceptes

    assert _attendre_une_valeur(
        _l_asset_est_accepte_par_festival,
        valeur_attendue=True,
        secondes=DELAI_DU_CACHE_DES_FEDERATIONS_DU_FEDOW,
    ), (
        f"Le Fedow ne renvoie pas l'asset dans get_accepted_assets() de `{LIEU_FEDERE}`, "
        f"meme apres {DELAI_DU_CACHE_DES_FEDERATIONS_DU_FEDOW} s : la federation n'a pas "
        "ete creee sur le Fedow (create_fed)."
    )

    page.goto(f"{URL_DU_LIEU_EMETTEUR}{URL_DE_LA_LISTE_LEGACY}")
    page.wait_for_load_state("networkidle")
    ligne_chez_l_emetteur = page.locator(
        "#result_list tr", has_text=nom_de_l_asset
    ).first
    expect(ligne_chez_l_emetteur).to_be_visible(timeout=10000)
    expect(ligne_chez_l_emetteur).to_contain_text("Festival")
    expect(ligne_chez_l_emetteur).to_contain_text("Lespass")

    # ==================================================================
    # TEST C — le parcours complet entre les deux lieux, sur le meme asset.
    # / TEST C — the full journey between the two venues, on the same asset.
    # ==================================================================

    # ------------------------------------------------------------------
    # C1. Le tarif de test chez `lespass` : le produit adhesion E2E (reutilise par son
    #     nom, cree au premier lancement) et un tarif neuf qui verse la monnaie du test.
    #     Le produit doit exister sur le Fedow : sinon la recompense echoue en silence.
    #     / The test price: the reused E2E membership product and a fresh price.
    # ------------------------------------------------------------------
    suffixe_du_lancement = nom_de_l_asset.rsplit(" ", 1)[-1]
    tarif_de_test = _lire_en_base(
        django_shell,
        "import json\n"
        "from decimal import Decimal\n"
        "from BaseBillet.models import Price, Product\n"
        "from fedow_public.models import AssetFedowPublic\n"
        "from fedow_connect.fedow_api import FedowAPI\n"
        "produit = Product.objects.filter(\n"
        f"    name={NOM_DU_PRODUIT_ADHESION_E2E!r}, categorie_article=Product.ADHESION\n"
        ").first()\n"
        "if produit is None:\n"
        "    produit = Product.objects.create(\n"
        f"        name={NOM_DU_PRODUIT_ADHESION_E2E!r},\n"
        "        categorie_article=Product.ADHESION, publish=False)\n"
        "try:\n"
        "    FedowAPI().asset.retrieve(uuid=str(produit.uuid))\n"
        "    produit_sur_le_fedow = True\n"
        "except Exception:\n"
        "    produit_sur_le_fedow = False\n"
        "tarif = Price.objects.create(\n"
        f"    product=produit, name='E2E {suffixe_du_lancement}',\n"
        f"    prix=Decimal({PRIX_DE_L_ADHESION!r}), subscription_type=Price.YEAR,\n"
        "    publish=False, fedow_reward_enabled=True,\n"
        f"    fedow_reward_asset=AssetFedowPublic.objects.get(uuid={uuid_de_l_asset!r}),\n"
        f"    fedow_reward_amount=Decimal({RECOMPENSE_DE_L_ADHESION!r}))\n"
        "print('RESULTAT_JSON=' + json.dumps({\n"
        "    'uuid_du_produit': str(produit.uuid),\n"
        "    'produit_sur_le_fedow': produit_sur_le_fedow,\n"
        "    'uuid_du_tarif': str(tarif.uuid),\n"
        "}))\n",
    )
    assert tarif_de_test["produit_sur_le_fedow"], (
        f"Le produit adhesion « {NOM_DU_PRODUIT_ADHESION_E2E} » "
        f"({tarif_de_test['uuid_du_produit']}) n'existe pas sur le Fedow : la "
        "recompense echouerait en silence. Le signal post_save de Product "
        "(send_membership_and_badge_product_to_fedow, BaseBillet/signals.py) le cree : "
        "regarder les logs du serveur (« ERREUR Fedow »)."
    )

    # ------------------------------------------------------------------
    # C2. L'adhesion chez `lespass` : adherent neuf, cotisation enregistree en especes par
    #     l'admin. Le versement part par Celery : on attend de le voir SUR LE FEDOW.
    #     / Membership on `lespass`, paid in cash by the admin; wait for the reward.
    # ------------------------------------------------------------------
    email_de_l_adherent = f"e2e-fed-{suffixe_du_lancement}@tibillet.test"
    adherent = _lire_en_base(
        django_shell,
        "import json\n"
        "from AuthBillet.utils import get_or_create_user\n"
        "from BaseBillet.models import Membership, Price\n"
        "from fedow_connect.fedow_api import FedowAPI\n"
        f"user = get_or_create_user({email_de_l_adherent!r}, send_mail=False)\n"
        "user.email_valid = True\n"
        "user.save()\n"
        "FedowAPI().wallet.get_or_create_wallet(user)\n"
        "user.refresh_from_db()\n"
        f"tarif = Price.objects.get(uuid={tarif_de_test['uuid_du_tarif']!r})\n"
        "adhesion = Membership.objects.create(\n"
        "    user=user, price=tarif, first_name='E2E', last_name='Federation',\n"
        "    status=Membership.WAITING_PAYMENT)\n"
        "print('RESULTAT_JSON=' + json.dumps({\n"
        "    'adhesion_pk': str(adhesion.pk),\n"
        "    'wallet_uuid': str(user.wallet.uuid) if user.wallet else None,\n"
        "}))\n",
    )
    assert adherent["wallet_uuid"], (
        "L'adherent n'a pas de portefeuille : le Fedow de dev n'a pas repondu."
    )

    page.goto(f"{URL_DU_LIEU_EMETTEUR}/admin/")
    reponse_du_paiement = _poster(
        page,
        f"/memberships/{adherent['adhesion_pk']}/ajouter_paiement/",
        {"amount": PRIX_DE_L_ADHESION, "payment_method": "CA"},
    )
    assert reponse_du_paiement.ok, (
        f"L'enregistrement de la cotisation a echoue : {reponse_du_paiement.status} "
        f"{reponse_du_paiement.text()[:400]}"
    )

    solde_recu = _attendre_une_valeur(
        lambda: _jetons_de_l_asset_sur_le_fedow(
            django_shell, email_de_l_adherent, uuid_de_l_asset
        ),
        valeur_attendue=RECOMPENSE_EN_CENTIMES,
        secondes=60,
    )
    assert solde_recu == RECOMPENSE_EN_CENTIMES, (
        f"Le Fedow n'a pas verse la recompense de l'adhesion : {solde_recu} jetons de "
        f"« {nom_de_l_asset} », attendu {RECOMPENSE_EN_CENTIMES}. Celery arrete, Fedow "
        "injoignable ou refus du Fedow : les logs de `lespass_celery` disent pourquoi."
    )

    # Le solde DEPENSABLE chez `festival`, relu sans cache : il compte la monnaie de
    # `lespass` parce qu'elle est federee avec `festival`. La lecture rafraichit aussi
    # le cache de 10 s que relit `valid_payment` (fedow_connect/fedow_api.py).
    # / The spendable balance at `festival`, uncached; also refreshes the 10 s cache.
    solde_depensable_chez_festival = _lire_en_base(
        django_shell,
        "import json\n"
        "from AuthBillet.models import TibilletUser\n"
        "from fedow_connect.fedow_api import FedowAPI\n"
        f"user = TibilletUser.objects.get(email={email_de_l_adherent!r})\n"
        "solde = FedowAPI().wallet.get_total_fiducial_and_all_federated_token(\n"
        "    user, use_cache=False)\n"
        "print('RESULTAT_JSON=' + json.dumps(int(solde)))\n",
        schema=LIEU_FEDERE,
    )
    assert solde_depensable_chez_festival == RECOMPENSE_EN_CENTIMES, (
        f"Chez `{LIEU_FEDERE}`, le solde depensable de l'adherent vaut "
        f"{solde_depensable_chez_festival}, attendu {RECOMPENSE_EN_CENTIMES} : la "
        "monnaie de `lespass` n'est pas comptee chez le lieu federe."
    )

    # ------------------------------------------------------------------
    # C3. L'admin de `festival` cree le QR code, dans le navigateur (skin classic) :
    #     /my_account/ → « My wallet » → « Initiate a payment » → montant → valider.
    #     / The `festival` admin creates the QR code in the browser (classic skin).
    # ------------------------------------------------------------------
    page.goto(f"{URL_DU_LIEU_FEDERE}/my_account/")
    page.locator('a[href="/my_account/balance/"]').first.click()
    page.wait_for_url("**/my_account/balance/")
    bouton_initier_un_paiement = page.locator(
        'a[href$="/qrcodescanpay/get_generator/"]'
    )
    expect(bouton_initier_un_paiement).to_be_visible(timeout=10000)
    bouton_initier_un_paiement.click()
    page.wait_for_url("**/qrcodescanpay/get_generator/")
    page.locator("#amount").fill(f"{DEPENSE_EN_CENTIMES / 100:.2f}")
    expect(page.locator("#asset_type")).to_have_value("EURO")
    page.locator('form[action$="/generate_qrcode/"] button[type="submit"]').click()

    bouton_copier_le_lien = page.locator("#copy-pay-link-btn")
    expect(bouton_copier_le_lien).to_be_visible(timeout=10000)
    lien_de_paiement = bouton_copier_le_lien.get_attribute("data-link") or ""
    trouve = re.search(
        rf"^{re.escape(URL_DU_LIEU_FEDERE)}/qrcodescanpay/([0-9a-f]{{32}})/process_qrcode$",
        lien_de_paiement,
    )
    assert trouve, (
        f"Le lien de paiement ne vise pas une demande de `{LIEU_FEDERE}` : "
        f"'{lien_de_paiement}'."
    )
    uuid_de_la_demande = trouve.group(1)

    # ------------------------------------------------------------------
    # C4. L'adherent paie chez `festival`. Connecte sur `lespass`, il ouvre le scanner,
    #     qui pour une adresse d'un AUTRE lieu passe par le relais de session
    #     /login/<b64>/redirect_session_to_another_tenant/ (scanner.html). Seule la camera
    #     est simulee : le lien de paiement est le contenu du QR code.
    #     / The member pays at `festival` through the real cross-venue session relay.
    # ------------------------------------------------------------------
    # Le Fedow de dev garde 120 s, par processus, la liste des monnaies acceptees par
    # `festival` (tests/PIEGES.md 9.116). Avant ce delai, le debit peut etre refuse
    # (« Amount cannot exceed the total amount ») par un processus qui ne connait pas
    # encore la federation. On attend donc que 125 s se soient ecoulees depuis
    # l'acceptation (le temps deja passe par C1-C3 est deduit).
    # / The dev Fedow keeps festival's accepted assets 120 s per process: wait until
    # 125 s have passed since the acceptance.
    secondes_restantes = DELAI_DU_CACHE_DES_FEDERATIONS_DU_FEDOW - (
        time.monotonic() - instant_de_la_federation
    )
    if secondes_restantes > 0:
        time.sleep(secondes_restantes)

    contexte_de_l_adherent = browser.new_context(
        base_url=BASE_URL, ignore_https_errors=True
    )
    page_de_l_adherent = contexte_de_l_adherent.new_page()
    parcours_de_l_adherent_termine = False
    try:
        login_as(page_de_l_adherent, email_de_l_adherent)
        page_de_l_adherent.goto("/qrcodescanpay/get_scanner/")
        expect(page_de_l_adherent.locator("#start-button")).to_be_visible(timeout=10000)

        # Meme encodage que `base64UrlEncode` de scanner.html (base64url sans « = »).
        # / Same encoding as scanner.html's base64UrlEncode.
        lien_encode = (
            base64.urlsafe_b64encode(lien_de_paiement.encode("utf-8"))
            .decode("ascii")
            .rstrip("=")
        )
        page_de_l_adherent.goto(
            f"/login/{lien_encode}/redirect_session_to_another_tenant/"
        )
        # Django ajoute la barre finale (APPEND_SLASH) : « process_qrcode/ ».
        # / Django appends the trailing slash.
        page_de_l_adherent.wait_for_url(
            re.compile(re.escape(lien_de_paiement) + "/?$"), timeout=20000
        )

        formulaire_de_validation = page_de_l_adherent.locator(
            'form[hx-post$="/valid_payment/"]'
        )
        expect(
            formulaire_de_validation,
            "Pas de formulaire de validation chez festival : solde juge insuffisant "
            "(monnaie non federee ?) ou demande introuvable.",
        ).to_be_visible(timeout=10000)
        expect(page_de_l_adherent.locator("#qrscanpay-container")).to_contain_text(
            re.compile(r"1[.,]50\s*€")
        )
        with page_de_l_adherent.expect_response(
            lambda reponse_http: "/qrcodescanpay/valid_payment/" in reponse_http.url
        ) as reponse_attendue:
            formulaire_de_validation.locator('button[type="submit"]').click()
        reponse_de_validation = reponse_attendue.value
        assert reponse_de_validation.ok, (
            f"Le paiement a echoue : {reponse_de_validation.status} "
            f"{reponse_de_validation.text()[:400]}"
        )
        assert "Insufficient Funds" not in reponse_de_validation.text(), (
            "Paiement refuse pour fonds insuffisants chez `festival` : la monnaie de "
            "`lespass` n'y est pas depensable."
        )
        expect(
            page_de_l_adherent.locator("#qrscanpay-container .card-header.bg-success")
        ).to_contain_text(re.compile(r"Payment Confirmed|Paiement confirmé"))
        parcours_de_l_adherent_termine = True
    finally:
        if not parcours_de_l_adherent_termine:
            _capturer_la_page_en_echec(
                page_de_l_adherent, f"{request.node.nodeid}-adherent"
            )
        contexte_de_l_adherent.close()

    # ------------------------------------------------------------------
    # C5. Le Fedow a debite le montant exact, dans la monnaie de `lespass`.
    #     / The Fedow debited the exact amount, in `lespass`'s currency.
    # ------------------------------------------------------------------
    jetons_apres_paiement = _jetons_de_l_asset_sur_le_fedow(
        django_shell, email_de_l_adherent, uuid_de_l_asset
    )
    assert jetons_apres_paiement == RECOMPENSE_EN_CENTIMES - DEPENSE_EN_CENTIMES, (
        f"Jetons de « {nom_de_l_asset} » apres le paiement : {jetons_apres_paiement}, "
        f"attendu {RECOMPENSE_EN_CENTIMES - DEPENSE_EN_CENTIMES}."
    )

    # ------------------------------------------------------------------
    # C6. La vente est chez `festival`, au bon montant, payee en monnaie locale ; rien
    #     chez `lespass`.
    #     / The sale is recorded at `festival`; nothing at `lespass`.
    # ------------------------------------------------------------------
    code_de_lecture_de_la_vente = (
        "import json\n"
        "from BaseBillet.models import LigneArticle\n"
        f"ligne = LigneArticle.objects.filter(uuid={uuid_de_la_demande!r}).first()\n"
        "moyens = []\n"
        "assets_debites = []\n"
        "if ligne is not None and ligne.vente_id:\n"
        "    for reglement in ligne.vente.reglements.all():\n"
        "        moyens.append(reglement.moyen)\n"
        "if ligne is not None and isinstance(ligne.metadata, dict):\n"
        "    for transaction in ligne.metadata.get('transactions') or []:\n"
        "        assets_debites.append(str(transaction.get('asset')))\n"
        "print('RESULTAT_JSON=' + json.dumps({\n"
        "    'trouvee': ligne is not None,\n"
        "    'statut': ligne.status if ligne else None,\n"
        "    'montant': int(ligne.amount) if ligne else None,\n"
        "    'moyens': sorted(moyens),\n"
        "    'assets_debites': sorted(set(assets_debites)),\n"
        "}))\n"
    )
    vente_chez_festival = _lire_en_base(
        django_shell, code_de_lecture_de_la_vente, schema=LIEU_FEDERE
    )
    assert vente_chez_festival == {
        "trouvee": True,
        "statut": "V",
        "montant": DEPENSE_EN_CENTIMES,
        "moyens": ["LE"],
        "assets_debites": [uuid_de_l_asset],
    }, (
        f"La vente chez `{LIEU_FEDERE}` n'est pas celle attendue : {vente_chez_festival}. "
        "Attendu : validee, 150 centimes, moyen LOCAL_EURO ('LE'), monnaie de `lespass`."
    )
    vente_chez_lespass = _lire_en_base(
        django_shell, code_de_lecture_de_la_vente, schema=LIEU_EMETTEUR
    )
    assert vente_chez_lespass["trouvee"] is False, (
        f"La demande de paiement existe aussi chez `lespass` : {vente_chez_lespass}."
    )

    # ------------------------------------------------------------------
    # C7. La fiche de l'asset chez `lespass` : `festival` est federe, et sa ligne de la
    #     ventilation par lieu vaut le montant depense. La ligne est reperee par le
    #     portefeuille du lieu (`FedowConfig.wallet`), dans l'adresse du bouton de remise
    #     en banque. Le Fedow garde la ventilation 30 s en cache : on recharge jusqu'a
    #     ~45 s.
    #     / The asset page at `lespass`: festival's row equals the spent amount.
    # ------------------------------------------------------------------
    portefeuille_de_festival = _lire_en_base(
        django_shell,
        "import json\n"
        "from fedow_connect.models import FedowConfig\n"
        "print('RESULTAT_JSON=' + json.dumps(str(FedowConfig.objects.first().wallet.uuid)))\n",
        schema=LIEU_FEDERE,
    )
    url_de_la_fiche = (
        f"{URL_DU_LIEU_EMETTEUR}{URL_DE_LA_LISTE_LEGACY}{uuid_de_l_asset}/change/"
    )
    bouton_de_remise_de_festival = page.locator(
        f'button[hx-post$="/bank_deposit/{uuid_de_l_asset}/{portefeuille_de_festival}/"]'
    )
    ligne_de_festival = page.locator("tr", has=bouton_de_remise_de_festival)

    total_affiche_pour_festival = _total_de_la_ligne_apres_rechargements(
        page, url_de_la_fiche, ligne_de_festival, re.compile(r"^1[.,]50$")
    )
    assert re.match(r"^1[.,]50$", total_affiche_pour_festival or ""), (
        f"Ventilation de `{LIEU_FEDERE}` sur la fiche de l'asset : "
        f"'{total_affiche_pour_festival}', attendu 1.50 apres ~45 s de rechargements. "
        "Ligne absente = la ventilation ne connait pas le portefeuille du lieu."
    )
    # Champ « Lieux federes » en lecture seule : un `div.readonly` sans classe propre au
    # champ. Seul lui peut contenir « Festival » parmi les champs en lecture seule.
    # / Read-only "federated venues" field: the only read-only field that can say Festival.
    expect(page.locator("form .readonly", has_text="Festival").first).to_be_visible()
    nom_de_festival_sur_le_fedow = (
        ligne_de_festival.locator("td").first.inner_text().strip()
    )

    # ------------------------------------------------------------------
    # C8. La remise en banque : l'admin de `lespass` (lieu d'origine) valide le retour
    #     en banque de la part de `festival`. La ligne revient a 0, et la page des
    #     remises en banque montre celle de `festival`.
    #     / Bank deposit of festival's share by the origin venue.
    # ------------------------------------------------------------------
    with page.expect_response(
        lambda reponse_http: "/bank_deposit/" in reponse_http.url
    ) as reponse_de_remise:
        bouton_de_remise_de_festival.click()
    assert reponse_de_remise.value.ok, (
        f"La remise en banque a echoue : {reponse_de_remise.value.status}"
    )
    page.wait_for_load_state("networkidle")

    total_apres_remise = _total_de_la_ligne_apres_rechargements(
        page, url_de_la_fiche, ligne_de_festival, re.compile(r"^0([.,]00)?$")
    )
    assert re.match(r"^0([.,]00)?$", total_apres_remise or ""), (
        f"Apres la remise en banque, la ventilation de `{LIEU_FEDERE}` vaut "
        f"'{total_apres_remise}', attendu 0 (le Fedow a-t-il refuse la remise ?)."
    )

    remises_de_festival = _lire_en_base(
        django_shell,
        "import json\n"
        "from fedow_public.models import AssetFedowPublic\n"
        "from fedow_connect.fedow_api import FedowAPI\n"
        f"asset = AssetFedowPublic.objects.get(uuid={uuid_de_l_asset!r})\n"
        "remises = FedowAPI().asset.retrieve_bank_deposits(asset=asset)\n"
        "print('RESULTAT_JSON=' + json.dumps([\n"
        "    int(remise['amount']) for remise in remises\n"
        f"    if str(remise['sender']) == {portefeuille_de_festival!r}\n"
        "]))\n",
    )
    assert remises_de_festival == [DEPENSE_EN_CENTIMES], (
        f"Remises en banque du portefeuille de `{LIEU_FEDERE}` lues sur le Fedow : "
        f"{remises_de_festival}, attendu [{DEPENSE_EN_CENTIMES}]."
    )

    page.goto(
        f"{URL_DU_LIEU_EMETTEUR}/fedow/asset/{uuid_de_l_asset}/retrieve_bank_deposits/"
    )
    tableau_des_remises = page.locator("table").last
    expect(
        tableau_des_remises.locator("tr", has_text=nom_de_festival_sur_le_fedow).filter(
            has_text=re.compile(r"1[.,]50")
        )
    ).to_have_count(1)
