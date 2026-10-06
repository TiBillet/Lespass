"""
Le plan comptable dans l'admin : un seul menu, deux onglets, une aide par page.
/ The chart of accounts in the admin: one menu entry, two tabs, one help per page.

LOCALISATION : tests/pytest/test_admin_plan_comptable_aide_et_onglets.py

RÈGLES TESTÉES
- Le menu « Ventes & comptabilité » n'a qu'UNE entrée « Plan comptable ». Elle ouvre
  l'onglet « Gérer » (la balance) et reste marquée active sur les quatre pages du
  plan. Les trois listes de réglage ne sont plus dans le menu.
- La barre « Gérer / Configurer » (Administration/admin/dashboard.py,
  `_onglets_du_plan_comptable`) : « Gérer » est actif sur la balance, « Configurer »
  sur les trois listes (comptes, moyens de paiement, monnaies). Un second niveau
  (`sous_onglets_configurer.html`) relie les trois listes ; la page affichée porte
  `aria-current="page"`.
- Chaque page (balance et trois listes) a son aide FALC repliable, FERMÉE par défaut
  (`<details>` sans `open`), avec son titre et une phrase clé.
- Les numéros cités dans les aides existent dans le plan par défaut
  (laboutik/plan_comptable_par_defaut.py), et les exemples suivent les
  correspondances par défaut (espèces → 530000, CB → 512100, ...). L'exemple de la
  bière (5,00 € à 20 %) tombe juste : 4,17 € + 0,83 €.
- L'écran de la balance : une période sans clôture est vide, sans bouton CSV ; un
  refus du FEC s'affiche à la place du tableau ; réservé aux administrateurs.
  L'égalité de la balance avec le FEC est testée dans
  tests/pytest/test_fec_equilibre.py (schéma dédié, ventes écrites par le service).
/ One menu entry, Manage / Configure tabs, a closed FALC help on each page, numbers
from the default plan, empty and refused balance screens.

DONNÉES : le lieu `lespass` de la base de dev, en lecture ; chaque test est marqué
`django_db` (transaction annulée à la fin). L'administrateur est créé dans le test
(tests/PIEGES.md 13.10).
/ Dev `lespass` venue, read only; rolled back per test.

Lancer / Run : make test ARGS="tests/pytest/test_admin_plan_comptable_aide_et_onglets.py"
"""

import re
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from unittest.mock import patch

import pytest
from django.conf import settings
from django.test import Client as DjangoClient
from django.urls import reverse
from django.utils import translation
from django_tenants.utils import tenant_context

from fabriques_panier import creer_utilisateur
from laboutik.plan_comptable import CompteComptableManquant
from laboutik.plan_comptable_par_defaut import (
    COMPTE_PAR_DEFAUT,
    COMPTES_DU_PLAN_PAR_DEFAUT,
    CORRESPONDANCES_DES_MOYENS_PAR_DEFAUT,
)

pytestmark = pytest.mark.django_db

DOSSIER_DES_GABARITS_DU_PLAN = (
    Path(settings.BASE_DIR) / "Administration" / "templates" / "admin" / "comptable"
)

ADRESSE_DE_LA_BALANCE = "/admin/laboutik/comptecomptable/balance/"
ADRESSE_DES_COMPTES = "/admin/laboutik/comptecomptable/"
ADRESSE_DES_MOYENS = "/admin/laboutik/mappingmoyendepaiement/"
ADRESSE_DES_MONNAIES = "/admin/laboutik/mappingmonnaie/"

# Chaque page du plan : son adresse, le testid de son aide, une phrase clé de l'aide,
# l'onglet actif attendu, et le second niveau actif (None sur la balance).
# / Each plan page: address, help testid, key sentence, active tab, active sub-tab.
PAGES_DU_PLAN = [
    (
        ADRESSE_DE_LA_BALANCE,
        "aide-balance",
        "La balance, c'est le total de chaque tiroir sur une période.",
        "Gérer",
        None,
    ),
    (
        ADRESSE_DES_COMPTES,
        "aide-plan-comptable",
        "Un compte, c'est un tiroir avec un numéro.",
        "Configurer",
        "sous-onglet-comptes",
    ),
    (
        ADRESSE_DES_MOYENS,
        "aide-moyens-de-paiement",
        "Pour chaque façon de payer, cette page dit dans quel tiroir arrive l'argent.",
        "Configurer",
        "sous-onglet-moyens",
    ),
    (
        ADRESSE_DES_MONNAIES,
        "aide-monnaies",
        "Les monnaies des cartes cashless ne sont pas de l'argent qui rentre",
        "Configurer",
        "sous-onglet-monnaies",
    ),
]

# Les gabarits qui portent une aide. / The templates carrying a help.
GABARITS_AVEC_UNE_AIDE = [
    "balance.html",
    "changelist_before.html",
    "moyens_changelist_before.html",
    "monnaies_changelist_before.html",
]


@pytest.fixture(autouse=True)
def _langue_par_defaut_apres_chaque_test():
    """Les signaux activent la langue du lieu sans la remettre (tests/PIEGES.md, 10.5).
    / Signals activate the venue language without resetting it."""
    yield
    translation.deactivate()


@pytest.fixture
def navigateur_admin(tenant):
    """
    Un administrateur du lieu `lespass`, créé dans le test, connecté, en français.
    / A venue admin created in the test, logged in, in French.
    """
    with tenant_context(tenant):
        administrateur = creer_utilisateur(prenom="Admin", nom="Plan")
        administrateur.client_admin.add(tenant)
        navigateur = DjangoClient(
            HTTP_HOST="lespass.tibillet.localhost", HTTP_ACCEPT_LANGUAGE="fr"
        )
        navigateur.force_login(administrateur)
        yield navigateur


def onglets_de_la_barre_unfold(contenu_de_la_page):
    """
    Les onglets de la barre Unfold (`<nav id="tabs-items">`) : liste de
    (adresse, titre, actif).
    / The Unfold tab bar items: (href, title, active).
    """
    barre = re.search(r'<nav id="tabs-items".*?</nav>', contenu_de_la_page, re.S)
    if barre is None:
        return []
    onglets = []
    for adresse, classes, titre in re.findall(
        r'<a href="([^"]*)" class="([^"]*)"[^>]*>\s*(.*?)\s*</a>',
        barre.group(0),
        re.S,
    ):
        onglets.append((adresse, titre, "active" in classes.split()))
    return onglets


def bloc_de_l_aide(texte, testid_de_l_aide):
    """
    Le bloc d'une aide, de son `data-testid` à la fin de son `</details>`.
    / A help block, from its data-testid to the end of its </details>.
    """
    debut = texte.index(f'data-testid="{testid_de_l_aide}"')
    fin = texte.index("</details>", debut)
    return texte[debut:fin]


# --------------------------------------------------------------------------
# Le menu / The menu
# --------------------------------------------------------------------------


def liens_et_items_du_menu(elements_du_menu):
    """
    Tous les items de la barre latérale, sous-menus compris.
    / Every sidebar item, sub-menus included.
    """
    items = []
    for element in elements_du_menu:
        items.append(element)
        items.extend(liens_et_items_du_menu(element.get("items") or []))
    return items


@pytest.mark.parametrize(
    "adresse_de_la_page",
    [ADRESSE_DE_LA_BALANCE, ADRESSE_DES_COMPTES, ADRESSE_DES_MOYENS, ADRESSE_DES_MONNAIES],
)
def test_menu_une_seule_entree_plan_comptable_active_sur_les_quatre_pages(
    tenant, navigateur_admin, adresse_de_la_page
):
    """
    La barre latérale n'a qu'une entrée vers le plan comptable : « Plan comptable »,
    vers la balance. Aucune entrée vers les trois listes de réglage. Sur chaque page
    du plan, cette entrée est marquée active.
    / One sidebar entry, to the trial balance; none to the settings lists; marked
    active on each plan page.
    """
    from Administration.admin.dashboard import get_sidebar_navigation

    with tenant_context(tenant):
        requete = navigateur_admin.get(adresse_de_la_page).wsgi_request
        with translation.override("fr"):
            items_du_menu = liens_et_items_du_menu(get_sidebar_navigation(requete))

    entrees_vers_le_plan = []
    for item in items_du_menu:
        lien = str(item.get("link") or "")
        assert lien not in [ADRESSE_DES_COMPTES, ADRESSE_DES_MOYENS, ADRESSE_DES_MONNAIES], (
            lien
        )
        if lien.startswith(ADRESSE_DES_COMPTES):
            entrees_vers_le_plan.append(item)

    assert len(entrees_vers_le_plan) == 1, entrees_vers_le_plan
    entree_du_plan = entrees_vers_le_plan[0]
    assert str(entree_du_plan["link"]) == ADRESSE_DE_LA_BALANCE
    assert str(entree_du_plan["title"]) == "Plan comptable"
    assert entree_du_plan["active"] is True


def test_menu_plan_comptable_inactif_ailleurs(tenant, navigateur_admin):
    """
    Hors du plan (la liste des ventes), l'entrée « Plan comptable » n'est pas active.
    / Outside the plan, the entry is not active.
    """
    from Administration.admin.dashboard import get_sidebar_navigation

    with tenant_context(tenant):
        requete = navigateur_admin.get("/admin/BaseBillet/vente/").wsgi_request
        items_du_menu = liens_et_items_du_menu(get_sidebar_navigation(requete))

    for item in items_du_menu:
        if str(item.get("link") or "") == ADRESSE_DE_LA_BALANCE:
            assert item["active"] is False
            return
    pytest.fail("Entrée « Plan comptable » introuvable.")


# --------------------------------------------------------------------------
# Les onglets et l'aide de chaque page / Each page's tabs and help
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "adresse,testid_de_l_aide,phrase_cle,onglet_actif,sous_onglet_actif",
    PAGES_DU_PLAN,
)
def test_chaque_page_a_ses_onglets_et_son_aide_fermee(
    tenant,
    navigateur_admin,
    adresse,
    testid_de_l_aide,
    phrase_cle,
    onglet_actif,
    sous_onglet_actif,
):
    """
    Chaque page du plan : la barre « Gérer / Configurer », l'onglet attendu actif et
    lui seul ; sur les trois listes, le second niveau avec la page affichée en
    `aria-current="page"` ; l'aide présente, avec sa phrase clé, FERMÉE (`<details>`
    sans `open`).
    / Each plan page: the tab bar with the expected active tab; the sub-tabs on the
    lists; the help present and closed.
    """
    with tenant_context(tenant):
        reponse = navigateur_admin.get(adresse)
    assert reponse.status_code == 200
    contenu = reponse.content.decode()

    onglets = onglets_de_la_barre_unfold(contenu)
    assert onglets == [
        (ADRESSE_DE_LA_BALANCE, "Gérer", onglet_actif == "Gérer"),
        (ADRESSE_DES_COMPTES, "Configurer", onglet_actif == "Configurer"),
    ], onglets

    if sous_onglet_actif is None:
        assert 'data-testid="sous-onglets-configurer"' not in contenu
    else:
        for testid in ["sous-onglet-comptes", "sous-onglet-moyens", "sous-onglet-monnaies"]:
            balise = re.search(rf'<a [^>]*data-testid="{testid}"[^>]*>', contenu, re.S)
            assert balise is not None, testid
            porte_aria_current = 'aria-current="page"' in balise.group(0)
            assert porte_aria_current == (testid == sous_onglet_actif), testid

    aide = bloc_de_l_aide(contenu, testid_de_l_aide)
    balise_details = re.search(r"<details\b[^>]*>", aide)
    assert balise_details is not None
    assert "open" not in balise_details.group(0)
    assert "<summary" in aide
    assert phrase_cle in aide


def test_onglets_absents_d_une_fiche(tenant, navigateur_admin):
    """
    La barre « Gérer / Configurer » n'est que sur les listes et la balance, jamais sur
    une fiche (elle y cacherait les onglets des inlines).
    / The tab bar is never on a change form.
    """
    from laboutik.models import CompteComptable

    with tenant_context(tenant):
        compte = CompteComptable.objects.first()
        assert compte is not None
        reponse = navigateur_admin.get(f"{ADRESSE_DES_COMPTES}{compte.pk}/change/")
    assert reponse.status_code == 200
    assert onglets_de_la_barre_unfold(reponse.content.decode()) == []


# --------------------------------------------------------------------------
# Les numéros cités dans les aides / The numbers quoted in the helps
# --------------------------------------------------------------------------


def test_numeros_cites_dans_les_aides_existent_dans_le_plan_par_defaut():
    """
    Chaque numéro à 6 chiffres cité dans une aide est un compte du plan par défaut.
    / Every 6-digit number quoted in a help is a default plan account.
    """
    numeros_du_plan_par_defaut = set()
    for compte in COMPTES_DU_PLAN_PAR_DEFAUT:
        numeros_du_plan_par_defaut.add(compte["numero"])

    numeros_cites = set()
    for nom_du_gabarit in GABARITS_AVEC_UNE_AIDE:
        texte = (DOSSIER_DES_GABARITS_DU_PLAN / nom_du_gabarit).read_text()
        aide = texte[texte.index("<details") : texte.index("</details>")]
        numeros_cites.update(re.findall(r"\b\d{6}\b", aide))

    assert numeros_cites, "Aucun numéro cité : test sans objet."
    assert numeros_cites <= numeros_du_plan_par_defaut, (
        numeros_cites - numeros_du_plan_par_defaut
    )


def test_exemples_des_aides_suivent_les_correspondances_par_defaut():
    """
    Les exemples des aides disent le vrai : espèces → 530000, carte bancaire →
    512100, chèque → 511200, paiement en ligne (Stripe) → 517100, monnaie locale et
    jetons cadeau → 419100, monnaie fédérée → 467000, jeton dépensé → 707900, ventes
    → 707000, TVA à 20 % → 445711. Chaque numéro est cité dans l'aide de sa page.
    / The helps' examples match the default mappings, each quoted on its page.
    """
    numero_par_moyen = {}
    for correspondance in CORRESPONDANCES_DES_MOYENS_PAR_DEFAUT:
        numero_par_moyen[correspondance["moyen"]] = correspondance["numero"]
    assert numero_par_moyen["CA"] == "530000"
    assert numero_par_moyen["CC"] == "512100"
    assert numero_par_moyen["CH"] == "511200"
    assert numero_par_moyen["SN"] == "517100"
    assert numero_par_moyen["LE"] == "419100"
    assert numero_par_moyen["LG"] == "419100"
    assert COMPTE_PAR_DEFAUT["reseau_federe"] == "467000"
    assert COMPTE_PAR_DEFAUT["ventes_reglees_en_jetons"] == "707900"

    compte_par_numero = {}
    for compte in COMPTES_DU_PLAN_PAR_DEFAUT:
        compte_par_numero[compte["numero"]] = compte
    assert compte_par_numero["707000"]["nature"] == "VENTE"
    assert compte_par_numero["445711"]["taux_de_tva"] == "20.00"

    numeros_attendus_par_gabarit = {
        "moyens_changelist_before.html": ["530000", "512100", "511200", "517100"],
        "monnaies_changelist_before.html": ["419100", "467000", "707900"],
        "changelist_before.html": ["512100", "707000", "445711"],
        "balance.html": ["512100", "707000", "445711"],
    }
    for nom_du_gabarit, numeros_attendus in numeros_attendus_par_gabarit.items():
        texte = (DOSSIER_DES_GABARITS_DU_PLAN / nom_du_gabarit).read_text()
        aide = texte[texte.index("<details") : texte.index("</details>")]
        for numero in numeros_attendus:
            assert numero in aide, (nom_du_gabarit, numero)


def test_exemple_de_la_biere_tombe_juste():
    """
    La bière à 5,00 € TTC à 20 % : HT = arrondi(5,00 / 1,20) = 4,17 € ; TVA =
    5,00 − 4,17 = 0,83 € ; débit 5,00 = crédit 4,17 + 0,83. Les trois montants sont
    écrits dans les deux aides qui citent l'exemple.
    / The beer example adds up, and both helps quote its amounts.
    """
    hors_taxe = (Decimal("5.00") / Decimal("1.20")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    tva = Decimal("5.00") - hors_taxe
    assert hors_taxe == Decimal("4.17")
    assert tva == Decimal("0.83")
    assert hors_taxe + tva == Decimal("5.00")

    for nom_du_gabarit in ["changelist_before.html", "balance.html"]:
        texte = (DOSSIER_DES_GABARITS_DU_PLAN / nom_du_gabarit).read_text()
        for montant in ["5,00 €", "4,17 €", "0,83 €"]:
            assert montant in texte, (nom_du_gabarit, montant)


# --------------------------------------------------------------------------
# L'écran de la balance / The trial balance screen
# --------------------------------------------------------------------------


def test_balance_d_une_periode_sans_cloture_est_vide(tenant, navigateur_admin):
    """
    Une période sans clôture (janvier 2000) : le message « aucune écriture », ni
    tableau, ni bouton CSV.
    / A period without closure: the empty message, no table, no CSV button.
    """
    with tenant_context(tenant):
        reponse = navigateur_admin.get(
            f"{ADRESSE_DE_LA_BALANCE}?debut=2000-01-01&fin=2000-01-31"
        )
    assert reponse.status_code == 200
    contenu = reponse.content.decode()
    assert 'data-testid="balance-vide"' in contenu
    assert 'data-testid="balance-tableau"' not in contenu
    assert 'data-testid="balance-telecharger-csv"' not in contenu
    assert 'value="2000-01-01"' in contenu
    assert 'value="2000-01-31"' in contenu


def test_balance_affiche_le_refus_du_fec(tenant, navigateur_admin):
    """
    Quand le FEC refuse (ici un compte manquant simulé), l'écran affiche le message
    du refus à la place du tableau, et le CSV ramène à l'écran.
    / A FEC refusal is shown instead of the table; the CSV goes back to the screen.
    """
    refus = CompteComptableManquant("Le produit « Planche test » n'a pas de compte.")
    with patch(
        "Administration.admin.laboutik.balance_de_la_periode", side_effect=refus
    ):
        with tenant_context(tenant):
            reponse = navigateur_admin.get(ADRESSE_DE_LA_BALANCE)
            reponse_du_csv = navigateur_admin.get(f"{ADRESSE_DE_LA_BALANCE}csv/")
    contenu = reponse.content.decode()
    assert 'data-testid="balance-refus"' in contenu
    assert "Planche test" in contenu
    assert 'data-testid="balance-tableau"' not in contenu
    assert reponse_du_csv.status_code == 302
    assert reponse_du_csv["Location"].startswith(ADRESSE_DE_LA_BALANCE)


def test_balance_reservee_aux_administrateurs(tenant):
    """
    Un utilisateur connecté qui n'est pas administrateur du lieu n'ouvre ni la
    balance, ni son CSV.
    / A logged-in non-admin opens neither the balance nor its CSV.
    """
    with tenant_context(tenant):
        utilisateur = creer_utilisateur(prenom="Simple", nom="Visiteur")
        utilisateur.is_staff = True
        utilisateur.save()
        navigateur = DjangoClient(HTTP_HOST="lespass.tibillet.localhost")
        navigateur.force_login(utilisateur)
        for adresse in [ADRESSE_DE_LA_BALANCE, f"{ADRESSE_DE_LA_BALANCE}csv/"]:
            reponse = navigateur.get(adresse)
            assert reponse.status_code in (302, 403), (adresse, reponse.status_code)
            assert b"balance-periode" not in reponse.content


def test_adresses_du_plan_inchangees():
    """
    Les adresses vers lesquelles pointent « Plan complet ? », la règle 7 et les
    autres liens restent celles des trois listes (sous « Configurer »).
    / The links' target addresses are unchanged.
    """
    assert reverse("staff_admin:laboutik_comptecomptable_changelist") == ADRESSE_DES_COMPTES
    assert reverse("staff_admin:laboutik_mappingmoyendepaiement_changelist") == (
        ADRESSE_DES_MOYENS
    )
    assert reverse("staff_admin:laboutik_mappingmonnaie_changelist") == ADRESSE_DES_MONNAIES
    assert reverse("staff_admin:laboutik_comptecomptable_balance") == ADRESSE_DE_LA_BALANCE
