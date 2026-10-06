"""
tests/e2e/test_federation_asset_fedow_core.py
La federation d'un asset entre deux lieux du moteur V2 (`fedow_core`), dans l'admin.
/ Federating an asset between two V2-engine venues (`fedow_core`), in the admin.

LOCALISATION : tests/e2e/test_federation_asset_fedow_core.py

Spec : TECH_DOC/SESSIONS/FEDOW_IMPORT/14-spec-tests-federation-inter-lieux.md §3, test A.
Portage de l'ancien test Playwright `31-admin-asset-federation.spec.ts` (supprime par le
commit 35dc0cc1). Il visait `chantefrein`, qui n'existe plus : le second lieu est ici
`le-coeur-en-or`.
/ Port of the old Playwright test; the second venue is now `le-coeur-en-or`.

LE PARCOURS / THE JOURNEY
--------------------------
1. L'admin de `lespass` cree un asset TLF dans `/admin/fedow_core/asset/add/`.
   Le signal `post_save` d'Asset (`fedow_core/signals.py`) cree dans la caisse de
   `lespass` un produit « Recharge <nom> » et ses 4 tarifs (1, 5, 10, Libre).
2. Sur la fiche de l'asset, il cherche `Festival` dans l'autocompletion des invitations :
   `festival` est un lieu legacy (ancien Fedow), il n'est PAS propose
   (`TenantAdmin.get_search_results`, Administration/admin_tenant.py). Puis il invite
   `le-coeur-en-or`.
3. La liste, filtree par nom (`?q=`), montre « Lespass » dans « Lieux federes », pas
   encore « Le Coeur en or » : une invitation n'est pas une federation.
4. L'admin de `le-coeur-en-or` voit l'invitation au-dessus de sa liste et l'accepte
   (`AssetAdmin.accept_asset_invitation`).
5. Les deux lieux voient l'asset, avec les deux noms dans « Lieux federes ». Chez
   `le-coeur-en-or`, la fiche est en lecture seule (seul le createur modifie).
6. L'asset est archive (en base, par `save()` : l'admin n'a pas de bouton d'archivage).
   Le signal archive aussi le produit « Recharge <nom> » de la caisse de `lespass`.

L'admin des E2E (`ADMIN_EMAIL`) est superuser : il administre les deux lieux.

PAS DE FEDOW DISTANT / NO REMOTE FEDOW
---------------------------------------
Tout se passe dans la base (`fedow_core`, schema public, et la caisse de `lespass`).
Rien n'est envoye au Fedow distant.

CE QU'IL LAISSE DERRIERE LUI / WHAT IT LEAVES BEHIND
------------------------------------------------------
Un asset ARCHIVE `E2E Fed V2 <suffixe>` (federe avec `le-coeur-en-or`) et son produit
de recharge ARCHIVE dans la caisse de `lespass`, a chaque lancement. L'archivage passe
aussi en fin de fixture, meme si le test echoue en route : la caisse de `lespass` ne
se remplit pas de produits de recharge.
/ An ARCHIVED asset and its ARCHIVED top-up product per run, even on failure.

PREREQUIS / PREREQUISITES
--------------------------
- le serveur de developpement tourne ;
- moteurs de monnaie de depart : `lespass` et `le-coeur-en-or` en v2, `festival` en
  legacy (fixture `moteurs_de_depart_verifies`, echec explicite sinon) ;
- `module_monnaie_locale` allume sur `lespass` et `le-coeur-en-or` (verifie au depart).

Lancement / Run:
    make e2e ARGS="tests/e2e/test_federation_asset_fedow_core.py"
"""

import json
import re
import uuid

import pytest
from playwright.sync_api import expect

from tests.e2e.conftest import DOMAIN

pytestmark = pytest.mark.e2e

# Les deux lieux du moteur V2, et le lieu legacy qui ne doit jamais etre propose.
# / The two V2 venues, and the legacy venue that must never be offered.
LIEU_CREATEUR = "lespass"
LIEU_INVITE = "le-coeur-en-or"
LIEU_LEGACY = "festival"

URL_DU_LIEU_INVITE = f"https://{LIEU_INVITE}.{DOMAIN}"
URL_DU_LIEU_CREATEUR = f"https://{LIEU_CREATEUR}.{DOMAIN}"

# Les tarifs que le signal cree pour un produit de recharge (fedow_core/signals.py).
# / The prices the signal creates for a top-up product.
NOMS_DES_TARIFS_DE_RECHARGE_ATTENDUS = ["1", "5", "10", "Libre"]


def _lire_en_base(django_shell, code_python, schema=LIEU_CREATEUR):
    """
    Lance du code dans le lieu `schema` et renvoie le JSON qu'il imprime sur sa
    derniere ligne.
    / Runs code in the `schema` venue and returns the JSON printed on its last line.
    """
    sortie = django_shell(code_python, schema=schema)
    derniere_ligne = sortie.strip().splitlines()[-1]
    return json.loads(derniere_ligne)


def _etat_de_l_asset_en_base(django_shell, nom_de_l_asset):
    """
    L'asset, ses invitations, ses lieux federes et son produit de recharge, lus en base.
    / The asset, its invitations, federated venues and top-up product, read from the DB.

    Asset est en SHARED_APPS (schema public) ; le produit est dans la caisse de `lespass`.
    / Asset lives in the public schema; the product lives in `lespass`'s POS.
    """
    return _lire_en_base(
        django_shell,
        "import json\n"
        "from fedow_core.models import Asset\n"
        "from BaseBillet.models import Product\n"
        "from laboutik.models import PointDeVente\n"
        f"asset = Asset.objects.filter(name={nom_de_l_asset!r}).first()\n"
        "if asset is None:\n"
        "    print(json.dumps({'existe': False}))\n"
        "else:\n"
        "    produit = Product.objects.filter(asset=asset).first()\n"
        "    pv_cashless = PointDeVente.objects.filter(comportement=PointDeVente.CASHLESS)\n"
        "    print(json.dumps({\n"
        "        'existe': True,\n"
        "        'uuid': str(asset.uuid),\n"
        "        'categorie': asset.category,\n"
        "        'archive': asset.archive,\n"
        "        'lieu_createur': asset.tenant_origin.schema_name,\n"
        "        'invitations': sorted(asset.pending_invitations.values_list('schema_name', flat=True)),\n"
        "        'lieux_federes': sorted(asset.federated_with.values_list('schema_name', flat=True)),\n"
        "        'produit': None if produit is None else {\n"
        "            'nom': produit.name,\n"
        "            'methode_caisse': produit.methode_caisse,\n"
        "            'archive': produit.archive,\n"
        "            'tarifs': sorted(produit.prices.values_list('name', flat=True)),\n"
        "            'pv_cashless_sans_le_produit': pv_cashless.exclude(products=produit).count(),\n"
        "            'pv_cashless': pv_cashless.count(),\n"
        "        },\n"
        "    }))\n",
    )


@pytest.fixture(scope="module")
def lieux_v2_avec_monnaie_locale(django_shell, moteurs_de_depart_verifies):
    """
    Echoue, avec la consigne, si `module_monnaie_locale` est eteint sur un des deux
    lieux V2 (prerequis de l'ancien test : la page des assets en depend).
    / Fails with what to do if the local currency module is off on a V2 venue.

    Lecture seule, par `Configuration.objects.first()` (jamais `get_solo()`, qui cree
    la ligne et passe par le cache partage avec le serveur).
    / Read only, never get_solo().
    """
    for lieu in [LIEU_CREATEUR, LIEU_INVITE]:
        etat_du_lieu = _lire_en_base(
            django_shell,
            "import json\n"
            "from BaseBillet.models import Configuration\n"
            "configuration = Configuration.objects.first()\n"
            "print(json.dumps({'monnaie_locale': bool(configuration and "
            "configuration.module_monnaie_locale)}))\n",
            schema=lieu,
        )
        if not etat_du_lieu["monnaie_locale"]:
            pytest.fail(
                f"Le module « Monnaie locale » est eteint sur `{lieu}`. Ce test federe un "
                "asset fedow_core entre deux lieux V2 qui l'ont allume. L'allumer dans "
                f"l'admin de `{lieu}` (tableau de bord, carte « Monnaie locale »)."
            )


@pytest.fixture
def nom_de_l_asset_archive_en_fin_de_test(django_shell, lieux_v2_avec_monnaie_locale):
    """
    Un nom d'asset unique par lancement. En fin de test, l'asset est archive, que le
    test ait reussi ou non.
    / A unique asset name per run. The asset is archived at teardown, pass or fail.

    L'archivage passe par `save()` DANS le lieu `lespass` (django_shell pose le vrai
    lieu) : le signal `post_save` d'Asset propage `archive` au produit de recharge.
    Dans le schema public, le signal ne fait rien et le produit resterait en caisse.
    / Archive through save() inside `lespass`, so the signal archives the product too.

    Les invitations en attente sont retirees aussi : le panneau d'invitations de
    `le-coeur-en-or` liste les assets ou il est invite, archives compris
    (`AssetAdmin.changelist_view`). Un test arrete avant l'acceptation y laisserait
    une invitation morte.
    / Pending invitations are cleared too: the invitations panel lists archived assets.
    """
    suffixe_unique = uuid.uuid4().hex[:6]
    nom_de_l_asset = f"E2E Fed V2 {suffixe_unique}"

    yield nom_de_l_asset

    django_shell(
        "from fedow_core.models import Asset\n"
        f"for asset in Asset.objects.filter(name={nom_de_l_asset!r}):\n"
        "    asset.pending_invitations.clear()\n"
        "    if not asset.archive:\n"
        "        asset.archive = True\n"
        "        asset.save()\n",
        schema=LIEU_CREATEUR,
    )


def test_federation_d_un_asset_fedow_core_entre_deux_lieux_v2(
    page,
    login_as_admin,
    login_as_admin_on_subdomain,
    django_shell,
    nom_de_l_asset_archive_en_fin_de_test,
):
    """
    Un asset TLF cree par `lespass` est partage avec `le-coeur-en-or` : invitation,
    acceptation, puis les deux lieux le voient. `festival` (legacy) n'est jamais propose.
    / A TLF asset created by `lespass` is shared with `le-coeur-en-or`; `festival`
    (legacy) is never offered.
    """
    nom_de_l_asset = nom_de_l_asset_archive_en_fin_de_test
    url_de_la_liste_filtree = (
        f"/admin/fedow_core/asset/?q={nom_de_l_asset.replace(' ', '+')}"
    )

    # ------------------------------------------------------------------
    # 1. L'admin de `lespass` cree l'asset TLF.
    #    / The `lespass` admin creates the TLF asset.
    # ------------------------------------------------------------------
    login_as_admin(page)
    page.goto("/admin/fedow_core/asset/add/")
    page.wait_for_load_state("networkidle")
    page.locator('input[name="name"]').fill(nom_de_l_asset)
    page.locator('input[name="currency_code"]').fill("EUR")
    page.locator('select[name="category"]').select_option("TLF")
    page.locator('button[name="_save"], input[name="_save"]').first.click()
    page.wait_for_load_state("networkidle")

    etat_apres_creation = _etat_de_l_asset_en_base(django_shell, nom_de_l_asset)
    assert etat_apres_creation["existe"], (
        f"L'asset « {nom_de_l_asset} » n'existe pas en base apres l'enregistrement du "
        "formulaire d'ajout. Regarder la capture : erreur de formulaire ?"
    )
    assert etat_apres_creation["categorie"] == "TLF"
    assert etat_apres_creation["lieu_createur"] == LIEU_CREATEUR, (
        "Le lieu createur doit etre celui de l'admin (AssetAdmin.save_model)."
    )

    # Le signal post_save a mis la recharge en caisse : un produit, 4 tarifs, tous les
    # points de vente CASHLESS.
    # / The post_save signal put the top-up in the POS: one product, 4 prices.
    produit_de_recharge = etat_apres_creation["produit"]
    assert produit_de_recharge is not None, (
        "Aucun produit de recharge cree dans la caisse de `lespass` : le signal "
        "post_save d'Asset (fedow_core/signals.py) n'a pas tourne dans le lieu."
    )
    assert produit_de_recharge["nom"] == f"Recharge {nom_de_l_asset}"
    assert produit_de_recharge["methode_caisse"] == "RE"
    assert produit_de_recharge["archive"] is False
    assert produit_de_recharge["tarifs"] == sorted(
        NOMS_DES_TARIFS_DE_RECHARGE_ATTENDUS
    ), (
        f"Tarifs du produit de recharge : {produit_de_recharge['tarifs']}, attendus "
        f"{NOMS_DES_TARIFS_DE_RECHARGE_ATTENDUS} (TARIFS_DEFAUT, fedow_core/signals.py)."
    )
    # Sans point de vente CASHLESS, « 0 point de vente sans le produit » serait vrai
    # par construction : on exige d'abord qu'il y en ait au moins un.
    # / Without a CASHLESS POS, "0 POS without the product" would be trivially true.
    assert produit_de_recharge["pv_cashless"] >= 1, (
        "`lespass` n'a aucun point de vente CASHLESS : la verification suivante ne "
        "prouverait rien. La demo doit en creer un."
    )
    assert produit_de_recharge["pv_cashless_sans_le_produit"] == 0, (
        "Le produit de recharge doit etre dans tous les points de vente CASHLESS de "
        f"`lespass` ({produit_de_recharge['pv_cashless']} au total)."
    )
    uuid_de_l_asset = etat_apres_creation["uuid"]

    # ------------------------------------------------------------------
    # 2. Fiche de l'asset : `festival` (legacy) n'est pas propose, puis on invite
    #    `le-coeur-en-or`. Le champ est une autocompletion select2 de l'admin Django.
    #    / Asset page: `festival` (legacy) is not offered, then invite `le-coeur-en-or`.
    # ------------------------------------------------------------------
    page.goto(url_de_la_liste_filtree)
    page.wait_for_load_state("networkidle")
    lien_vers_la_fiche = page.locator("#result_list a", has_text=nom_de_l_asset).first
    expect(lien_vers_la_fiche).to_be_visible(timeout=10000)
    lien_vers_la_fiche.click()
    page.wait_for_load_state("networkidle")

    champ_de_recherche_des_invitations = page.locator(
        ".field-pending_invitations .select2-search__field"
    )
    expect(champ_de_recherche_des_invitations).to_be_visible(timeout=5000)
    options_de_l_autocompletion = page.locator(
        ".select2-results__option:not(.loading-results)"
    )

    # 2a. `Festival` : la reponse de l'autocompletion ne le contient pas, la liste
    #     deroulante ne le montre pas.
    #     / `Festival`: neither the autocomplete response nor the dropdown offers it.
    champ_de_recherche_des_invitations.click()
    with page.expect_response(
        lambda reponse: (
            "/admin/autocomplete/" in reponse.url and "term=Festival" in reponse.url
        )
    ) as reponse_pour_festival:
        champ_de_recherche_des_invitations.press_sequentially("Festival", delay=30)
    lieux_proposes_pour_festival = [
        resultat["text"] for resultat in reponse_pour_festival.value.json()["results"]
    ]
    assert "Festival" not in lieux_proposes_pour_festival, (
        f"L'autocompletion des invitations propose `{LIEU_LEGACY}`, un lieu legacy : "
        f"{lieux_proposes_pour_festival}. Garde attendue dans "
        "TenantAdmin.get_search_results (Administration/admin_tenant.py)."
    )
    expect(options_de_l_autocompletion.filter(has_text="Festival")).to_have_count(0)

    # 2b. `Le Coeur en or` : propose, on le choisit, on enregistre.
    #     / `Le Coeur en or`: offered, picked, saved.
    champ_de_recherche_des_invitations.fill("")
    with page.expect_response(
        lambda reponse: (
            "/admin/autocomplete/" in reponse.url and "term=Coeur" in reponse.url
        )
    ):
        champ_de_recherche_des_invitations.press_sequentially("Coeur", delay=30)
    option_le_coeur_en_or = options_de_l_autocompletion.filter(
        has_text=re.compile(r"Le Coeur en or", re.IGNORECASE)
    ).first
    expect(option_le_coeur_en_or).to_be_visible(timeout=10000)
    option_le_coeur_en_or.click()
    page.locator('button[name="_save"], input[name="_save"]').first.click()
    page.wait_for_load_state("networkidle")

    etat_apres_invitation = _etat_de_l_asset_en_base(django_shell, nom_de_l_asset)
    assert etat_apres_invitation["invitations"] == [LIEU_INVITE], (
        f"Invitations en base : {etat_apres_invitation['invitations']}, attendu "
        f"[{LIEU_INVITE!r}]. Le formulaire a-t-il enregistre le champ ?"
    )
    assert etat_apres_invitation["lieux_federes"] == []

    # ------------------------------------------------------------------
    # 3. La liste de `lespass` : « Lespass » federe, pas encore « Le Coeur en or ».
    #    / `lespass` list: "Lespass" only, the invitation is not a federation yet.
    # ------------------------------------------------------------------
    page.goto(url_de_la_liste_filtree)
    page.wait_for_load_state("networkidle")
    ligne_chez_le_createur = page.locator(
        "#result_list tr", has_text=nom_de_l_asset
    ).first
    expect(ligne_chez_le_createur).to_be_visible(timeout=10000)
    expect(ligne_chez_le_createur).to_contain_text("Lespass")
    expect(ligne_chez_le_createur).not_to_contain_text("Le Coeur en or")

    # ------------------------------------------------------------------
    # 4. L'admin de `le-coeur-en-or` voit l'invitation et l'accepte.
    #    / The `le-coeur-en-or` admin sees the invitation and accepts it.
    # ------------------------------------------------------------------
    login_as_admin_on_subdomain(page, LIEU_INVITE)
    page.goto(f"{URL_DU_LIEU_INVITE}/admin/fedow_core/asset/")
    page.wait_for_load_state("networkidle")

    ligne_d_invitation = page.locator(
        f'[data-testid="asset-invitation-{uuid_de_l_asset}"]'
    )
    expect(ligne_d_invitation).to_be_visible(timeout=10000)
    expect(ligne_d_invitation).to_contain_text(nom_de_l_asset)
    expect(ligne_d_invitation).to_contain_text("Lespass")
    page.locator(f'[data-testid="btn-accept-asset-{uuid_de_l_asset}"]').click()
    page.wait_for_load_state("networkidle")
    expect(
        page.get_by_text(re.compile(rf"Invitation accept.*{re.escape(nom_de_l_asset)}"))
    ).to_be_visible(timeout=10000)
    expect(ligne_d_invitation).to_have_count(0)

    etat_apres_acceptation = _etat_de_l_asset_en_base(django_shell, nom_de_l_asset)
    assert etat_apres_acceptation["invitations"] == [], (
        "Apres l'acceptation, `le-coeur-en-or` doit quitter les invitations en attente."
    )
    assert etat_apres_acceptation["lieux_federes"] == [LIEU_INVITE], (
        f"Lieux federes en base : {etat_apres_acceptation['lieux_federes']}, attendu "
        f"[{LIEU_INVITE!r}] (AssetAdmin.accept_asset_invitation)."
    )

    # ------------------------------------------------------------------
    # 5. Les deux lieux voient l'asset, avec les deux noms. Chez le lieu invite, la
    #    fiche est en lecture seule.
    #    / Both venues see the asset with both names; read-only for the invited venue.
    # ------------------------------------------------------------------
    page.goto(f"{URL_DU_LIEU_INVITE}{url_de_la_liste_filtree}")
    page.wait_for_load_state("networkidle")
    ligne_chez_l_invite = page.locator("#result_list tr", has_text=nom_de_l_asset).first
    expect(ligne_chez_l_invite).to_be_visible(timeout=10000)
    expect(ligne_chez_l_invite).to_contain_text("Lespass")
    expect(ligne_chez_l_invite).to_contain_text("Le Coeur en or")

    page.locator("#result_list a", has_text=nom_de_l_asset).first.click()
    page.wait_for_load_state("networkidle")
    # Fiche en lecture seule : le nom est un texte (`div.readonly`), pas un champ.
    # / Read-only page: the name is plain text, not an input.
    expect(
        page.locator("#asset_form .readonly", has_text=nom_de_l_asset).first
    ).to_be_visible()
    expect(page.locator('input[name="name"]')).to_have_count(0)
    expect(page.locator('button[name="_save"], input[name="_save"]')).to_have_count(0)

    # La session de `lespass` est toujours la (cookie par sous-domaine).
    # / The `lespass` session is still there (per-subdomain cookie).
    page.goto(f"{URL_DU_LIEU_CREATEUR}{url_de_la_liste_filtree}")
    page.wait_for_load_state("networkidle")
    ligne_chez_le_createur = page.locator(
        "#result_list tr", has_text=nom_de_l_asset
    ).first
    expect(ligne_chez_le_createur).to_be_visible(timeout=10000)
    expect(ligne_chez_le_createur).to_contain_text("Lespass")
    expect(ligne_chez_le_createur).to_contain_text("Le Coeur en or")

    # ------------------------------------------------------------------
    # 6. Archivage de l'asset : le produit de recharge est archive avec lui.
    #    La fixture archive aussi en fin de test ; ici on VERIFIE la propagation.
    #    / Archiving the asset archives its top-up product too.
    # ------------------------------------------------------------------
    django_shell(
        "from fedow_core.models import Asset\n"
        f"asset = Asset.objects.get(uuid={uuid_de_l_asset!r})\n"
        "asset.archive = True\n"
        "asset.save()\n",
        schema=LIEU_CREATEUR,
    )
    etat_apres_archivage = _etat_de_l_asset_en_base(django_shell, nom_de_l_asset)
    assert etat_apres_archivage["archive"] is True
    assert etat_apres_archivage["produit"]["archive"] is True, (
        f"L'asset est archive mais son produit « Recharge {nom_de_l_asset} » reste en "
        "caisse chez `lespass` : le signal post_save d'Asset (fedow_core/signals.py) "
        "doit propager l'archivage au produit."
    )

    page.goto(f"{URL_DU_LIEU_CREATEUR}{url_de_la_liste_filtree}")
    page.wait_for_load_state("networkidle")
    expect(page.locator("#result_list tr", has_text=nom_de_l_asset)).to_have_count(0)
