"""
Le tableau de bord et la page d'un domaine.
/ The dashboard and a domain's landing page.

LOCALISATION : tests/pytest/test_admin_tableau_de_bord.py

CE QUE CES TESTS PROTEGENT
--------------------------
Le tableau de bord n'avait AUCUN test avant ce fichier. Il vient d'etre
reecrit : les cartes de module sont desormais rangees par domaine, les
modules eteints sont replies, et chaque domaine a sa propre page.

Trois choses peuvent casser sans bruit :
  1. une carte de module qui disparait — plus personne ne peut activer ce
     module ;
  2. un compteur « actifs / total » qui ment ;
  3. un interrupteur affiche sur une carte qui n'en a pas (module a venir,
     ou caisse en V1) : un bouton qui ne bascule rien.
/ Three silent failure modes: a card vanishing, a lying counter, a toggle
  shown on a card that has none.

Meme pattern que les autres tests d'admin : base de dev vivante.
/ Same pattern as the other admin tests: live dev DB.
"""

from unittest.mock import patch

import pytest
from django.test import Client as HttpClient, RequestFactory
from django.urls import reverse
from django_tenants.utils import tenant_context

from Administration.admin import dashboard
from AuthBillet.models import TibilletUser
from BaseBillet.models import Configuration
from Customers.models import Client


@pytest.fixture(scope="session")
def django_db_setup():
    # Reutilise la base de dev (pas de creation de test DB).
    # / Reuse the dev database.
    pass


@pytest.fixture
def lieu_et_superadmin(db):
    """Le premier lieu qui a un domaine ET un superadmin."""
    for tenant in Client.objects.exclude(schema_name="public"):
        domaine = tenant.domains.first()
        if not domaine:
            continue
        with tenant_context(tenant):
            utilisateur = TibilletUser.objects.filter(is_superuser=True).first()
        if utilisateur:
            return tenant, domaine.domain, utilisateur
    pytest.skip("Aucun lieu avec un domaine et un superadmin.")


@pytest.fixture
def navigateur(lieu_et_superadmin):
    """Un client HTTP deja connecte sur le lieu."""
    _tenant, domaine, utilisateur = lieu_et_superadmin
    client = HttpClient(HTTP_HOST=domaine)
    client.force_login(utilisateur)
    return client


def _contexte_du_tableau_de_bord(tenant):
    """Le contexte que le gabarit recoit. / The context the template receives."""
    with tenant_context(tenant):
        return dashboard.dashboard_callback(RequestFactory().get("/admin/"), {})


# --------------------------------------------------------------------------- #
# Le tableau de bord                                                           #
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_le_tableau_de_bord_repond(navigateur):
    """La page d'accueil de l'admin s'affiche. / The admin landing page loads."""
    assert navigateur.get("/admin/").status_code == 200


@pytest.mark.django_db
def test_aucune_carte_de_module_ne_disparait(lieu_et_superadmin):
    """
    LE test important : chaque module declare doit avoir sa carte.

    Une carte perdue, c'est un module qu'on ne peut plus activer — et rien
    ne le signale.
    / A lost card is a module nobody can enable any more, silently.
    """
    tenant, _domaine, _utilisateur = lieu_et_superadmin
    contexte = _contexte_du_tableau_de_bord(tenant)

    testids_affiches = {
        carte["testid"]
        for groupe in contexte["groupes_de_domaines"]
        for carte in groupe["cartes"]
    }

    for nom_du_champ, info in dashboard.MODULE_FIELDS.items():
        # La caisse a une carte a part, avec son propre identifiant.
        # / The POS has its own card with its own testid.
        attendu = "dashboard-card-pos" if nom_du_champ == "module_caisse" else info["testid"]
        assert attendu in testids_affiches, (
            f"Le module {nom_du_champ} n'a plus de carte sur le tableau de bord."
        )


@pytest.mark.django_db
def test_chaque_module_est_range_dans_un_domaine_connu(lieu_et_superadmin):
    """Aucune carte ne doit atterrir dans un domaine invente."""
    tenant, _domaine, _utilisateur = lieu_et_superadmin
    contexte = _contexte_du_tableau_de_bord(tenant)

    for groupe in contexte["groupes_de_domaines"]:
        assert groupe["cle"] in dashboard.DOMAINES


@pytest.mark.django_db
def test_les_compteurs_disent_vrai(lieu_et_superadmin):
    """
    « actifs / total » doit correspondre aux cartes reellement presentes.

    Le total ne compte QUE les modules reels : une carte « bientot
    disponible » n'a pas d'interrupteur, l'inclure promettrait un bouton
    qui n'existe pas.
    / The total counts real modules only.
    """
    tenant, _domaine, _utilisateur = lieu_et_superadmin
    contexte = _contexte_du_tableau_de_bord(tenant)

    for groupe in contexte["groupes_de_domaines"]:
        cartes_reelles = [c for c in groupe["cartes"] if c["type"] != "coming_soon"]
        cartes_allumees = [c for c in cartes_reelles if c["allume"]]

        assert groupe["total"] == len(cartes_reelles)
        assert groupe["actifs"] == len(cartes_allumees)
        assert groupe["actifs"] <= groupe["total"]


@pytest.mark.django_db
def test_le_compteur_de_modules_eteints_est_juste(lieu_et_superadmin):
    """La pastille de « Découvrir plus de modules » compte les modules eteints."""
    tenant, _domaine, _utilisateur = lieu_et_superadmin
    contexte = _contexte_du_tableau_de_bord(tenant)

    attendu = sum(
        groupe["total"] - groupe["actifs"]
        for groupe in contexte["groupes_de_domaines"]
    )
    assert contexte["modules_eteints"] == attendu


@pytest.mark.django_db
def test_une_carte_a_venir_n_a_pas_d_interrupteur(lieu_et_superadmin):
    """
    Un module annonce mais pas livre ne doit pas afficher d'interrupteur :
    ce serait un bouton qui ne bascule rien.
    / An announced-but-unshipped module must show no toggle.
    """
    tenant, _domaine, _utilisateur = lieu_et_superadmin
    contexte = _contexte_du_tableau_de_bord(tenant)

    cartes_a_venir = [
        carte
        for groupe in contexte["groupes_de_domaines"]
        for carte in groupe["cartes"]
        if carte["type"] == "coming_soon"
    ]
    assert cartes_a_venir, "Aucune carte « bientôt disponible » : test à revoir."
    for carte in cartes_a_venir:
        assert carte["montre_interrupteur"] is False


@pytest.mark.django_db
def test_une_carte_eteinte_ne_mene_nulle_part(lieu_et_superadmin):
    """
    Un module eteint n'a pas de page d'admin : sa carte ne doit pas etre un
    lien, sinon on tombe sur une 404.
    / A switched-off module has no admin page, so its card must not link.
    """
    tenant, _domaine, _utilisateur = lieu_et_superadmin
    contexte = _contexte_du_tableau_de_bord(tenant)

    for groupe in contexte["groupes_de_domaines"]:
        for carte in groupe["cartes"]:
            if not carte["allume"]:
                assert not carte.get("lien_du_module"), (
                    f"La carte {carte['testid']} est éteinte mais pointe quelque part."
                )


@pytest.mark.django_db
def test_le_bouton_d_idee_pointe_vers_un_contact(navigateur):
    """Le bouton « Proposer une idée » doit mener quelque part de reel."""
    contenu = navigateur.get("/admin/").content.decode()
    assert 'data-testid="dashboard-cta-lien"' in contenu
    assert "mailto:contact@tibillet.re" in contenu


@pytest.mark.django_db
def test_l_encart_des_taches_reste_hors_du_bloc_des_modules(navigateur):
    """
    L'encart « Ce qu'il reste à faire » doit s'afficher meme sans module,
    puisque c'est justement la qu'il sert le plus. Il est donc rendu AVANT
    le bloc des modules.
    / The SEO notice must render before the modules block.
    """
    contenu = navigateur.get("/admin/").content.decode()
    if 'data-testid="dashboard-taches-referencement"' not in contenu:
        pytest.skip("Ce lieu n'a aucune tâche de référencement en attente.")
    assert contenu.index('dashboard-taches-referencement') < contenu.index('id="dashboard-modules"')


# --------------------------------------------------------------------------- #
# La carte de la caisse : trois etats                                          #
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_la_caisse_en_v1_n_a_pas_d_interrupteur(lieu_et_superadmin):
    """
    En LaBoutik V1, la caisse ne se desactive pas depuis le tableau de bord.
    On montre son etat, pas un interrupteur qui mentirait.
    / In V1 the POS cannot be switched off from here.
    """
    tenant, _domaine, _utilisateur = lieu_et_superadmin
    with tenant_context(tenant):
        configuration = Configuration.get_solo()
        configuration.server_cashless = "https://exemple-v1.test"
        with patch.object(Configuration, "check_serveur_cashless", return_value=True):
            carte = dashboard._build_pos_card_context(configuration)

    assert carte["state"] == "v1_active"


@pytest.mark.django_db
def test_un_serveur_v1_injoignable_est_affiche_hors_ligne(lieu_et_superadmin):
    """
    Si le health-check echoue, la carte doit dire « hors ligne » — et surtout
    ne pas casser la page.
    / A failing health check must read as "offline", not blow up the page.
    """
    tenant, _domaine, _utilisateur = lieu_et_superadmin
    with tenant_context(tenant):
        configuration = Configuration.get_solo()
        configuration.server_cashless = "https://exemple-v1.test"
        configuration.key_cashless = "une-cle"
        with patch.object(
            Configuration, "check_serveur_cashless", side_effect=OSError("injoignable")
        ):
            carte = dashboard._build_pos_card_context(configuration)

    assert carte["v1_online"] is False


# --------------------------------------------------------------------------- #
# La page d'un domaine                                                         #
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_la_page_de_domaine_repond(navigateur):
    """Cliquer « Lespass » ouvre bien une page."""
    adresse = reverse("staff_admin:page_de_domaine", args=["lespass"])
    assert navigateur.get(adresse).status_code == 200


@pytest.mark.django_db
def test_un_domaine_inconnu_renvoie_404(navigateur):
    """Un identifiant farfelu ne doit pas faire planter l'admin."""
    adresse = reverse("staff_admin:page_de_domaine", args=["domaine-qui-nexiste-pas"])
    assert navigateur.get(adresse).status_code == 404


@pytest.mark.django_db
def test_tous_les_domaines_ont_une_page(navigateur):
    """Chaque domaine du rail doit mener quelque part."""
    for cle in dashboard.DOMAINES:
        adresse = reverse("staff_admin:page_de_domaine", args=[cle])
        reponse = navigateur.get(adresse)
        assert reponse.status_code == 200, f"Le domaine {cle} ne répond pas."


@pytest.mark.django_db
def test_la_page_de_domaine_montre_les_memes_cartes_que_le_tableau_de_bord(
    lieu_et_superadmin, navigateur
):
    """
    Les deux ecrans partagent la meme source : un module present sur le
    tableau de bord doit l'etre aussi sur la page de son domaine.
    / Both screens share one source of truth.
    """
    tenant, _domaine, _utilisateur = lieu_et_superadmin
    contexte = _contexte_du_tableau_de_bord(tenant)

    for groupe in contexte["groupes_de_domaines"]:
        adresse = reverse("staff_admin:page_de_domaine", args=[groupe["cle"]])
        contenu = navigateur.get(adresse).content.decode()
        for carte in groupe["cartes"]:
            assert f'data-testid="{carte["testid"]}"' in contenu, (
                f"{carte['testid']} manque sur la page du domaine {groupe['cle']}."
            )


@pytest.mark.django_db
def test_le_titre_du_domaine_est_cliquable_dans_la_sidebar(navigateur):
    """
    La maquette veut qu'on clique le nom du domaine dans le rail. C'est ce
    que permet la surcharge de unfold/helpers/app_list.html.
    / The domain title must be a link in the sidebar.
    """
    contenu = navigateur.get("/admin/").content.decode()
    assert 'data-testid="sidebar-domaine-lien"' in contenu
    assert "/admin/domaine/" in contenu


# --------------------------------------------------------------------------- #
# Regressions corrigees apres retour d'usage                                   #
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_la_modale_ne_cible_aucun_element_de_page(navigateur):
    """
    La modale de bascule ne doit declarer NI hx-target NI hx-swap.

    Elle en declarait un (`#dashboard-modules`) qui n'existe que sur le
    tableau de bord : depuis la page d'un domaine, htmx levait un
    « htmx:targetError » et n'envoyait jamais la requete — l'interrupteur
    ne faisait rien.

    La cible etait de toute facon inutile : la vue repond « HX-Refresh »
    avec un corps vide, donc rien n'est jamais echange.
    / The modal declared a target that only existed on the dashboard, so the
      toggle silently did nothing anywhere else. The target was useless
      anyway: the view answers HX-Refresh with an empty body.
    """
    adresse = (
        "/admin/BaseBillet/configuration/module-toggle-modal/module_newsletter/"
    )
    contenu = navigateur.get(adresse).content.decode()

    assert "hx-post=" in contenu, "La modale ne sait plus basculer le module."
    assert "hx-target=" not in contenu, (
        "La modale redeclare une cible : elle cassera sur toute page qui ne "
        "la contient pas."
    )


@pytest.mark.django_db
def test_l_interrupteur_bascule_depuis_n_importe_quelle_page(
    navigateur, lieu_et_superadmin
):
    """
    La bascule doit marcher depuis la page d'un domaine comme depuis le
    tableau de bord. C'est le meme POST : il repond HX-Refresh, donc il est
    indifferent a la page d'ou il part.
    / The toggle must work from any page: it answers HX-Refresh.
    """
    tenant, _domaine, _utilisateur = lieu_et_superadmin
    adresse = "/admin/BaseBillet/configuration/module-toggle/module_newsletter/"

    with tenant_context(tenant):
        avant = Configuration.get_solo().module_newsletter

    reponse = navigateur.post(adresse)
    assert reponse.status_code == 200
    assert reponse.headers.get("HX-Refresh") == "true"

    with tenant_context(tenant):
        apres = Configuration.get_solo().module_newsletter
    assert apres is not avant

    # On remet le module comme on l'a trouve.
    # / Put the module back the way we found it.
    navigateur.post(adresse)
    with tenant_context(tenant):
        assert Configuration.get_solo().module_newsletter is avant


@pytest.mark.django_db
def test_l_encart_beta_est_sur_sa_propre_ligne(navigateur):
    """
    L'encart « acces anticipe » doit occuper toute la largeur de la carte.

    Sans son conteneur, il se rangeait A COTE du texte des que la carte
    etait large — donc sur la page d'un domaine, ou les cartes prennent
    toute la largeur de l'ecran.
    / Without its wrapper the notice sat beside the text on wide cards.
    """
    contenu = navigateur.get("/admin/domaine/lespass/").content.decode()
    if "-beta-notice" not in contenu:
        pytest.skip("Aucun module en accès anticipé sur ce lieu.")
    assert 'class="tb-carte-beta"' in contenu


@pytest.mark.django_db
def test_l_encart_beta_n_a_plus_de_style_inline(navigateur):
    """
    L'encart etait ecrit en styles inline, avec le violet d'Unfold. Un style
    inline ne peut pas etre corrige depuis la feuille du projet : la marge
    basse qu'il imposait restait, et le violet contredisait le vert.
    / Inline styles cannot be overridden from the project stylesheet.
    """
    contenu = navigateur.get("/admin/").content.decode()
    assert "124,58,237" not in contenu, "Le violet d'Unfold traîne encore."


@pytest.mark.django_db
def test_le_sous_menu_du_domaine_est_deplie_sur_sa_page(navigateur):
    """
    Arriver sur la page d'un domaine avec son sous-menu ferme, c'est ne pas
    voir ou l'on se trouve.

    Unfold n'ouvre un groupe que si l'un de ses LIENS est actif. Le lien du
    domaine n'en est pas un — d'ou la cle « ouvert », lue par notre
    surcharge de app_list.html.
    / Unfold only opens a group when one of its items is active.
    """
    def _le_groupe_lespass_est_ouvert(adresse):
        contenu = navigateur.get(adresse).content.decode()
        morceaux = [
            m for m in contenu.split('x-data="{navigationOpen:')
            if "domaine/lespass" in m[:2000]
        ]
        assert morceaux, "Le groupe Lespass est introuvable dans la sidebar."
        return morceaux[0].lstrip().startswith("true")

    assert _le_groupe_lespass_est_ouvert("/admin/domaine/lespass/"), (
        "Le sous-menu devrait être déplié sur la page du domaine."
    )
