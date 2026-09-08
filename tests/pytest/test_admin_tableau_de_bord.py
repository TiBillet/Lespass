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


# --------------------------------------------------------------------------- #
# Ecarts corriges apres relecture de la maquette                               #
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_une_seule_balise_h1_par_page(navigateur):
    """
    Une page ne doit avoir qu'UN titre de niveau 1.

    Mes pages de domaine et de module en avaient deux : celui de la barre
    haute d'Unfold, et celui que mon gabarit ajoutait dans le contenu. Deux
    <h1>, c'est faux pour un lecteur d'ecran.
    / Two <h1> on one page is wrong for a screen reader.
    """
    import re

    for adresse in ["/admin/", "/admin/domaine/lespass/", "/admin/module/agenda/"]:
        contenu = navigateur.get(adresse).content.decode()
        titres = re.findall(r"<h1[^>]*>", contenu)
        assert len(titres) == 1, f"{adresse} a {len(titres)} <h1> au lieu d'un seul."


@pytest.mark.django_db
def test_la_barre_haute_et_le_contenu_ne_disent_pas_la_meme_chose(navigateur):
    """
    La barre haute d'Unfold sert de fil d'Ariane : elle porte le PARENT.
    Le contenu porte le titre de la page. Sinon le nom s'affiche deux fois.
    / Unfold's header carries the parent; the content carries the page title.
    """
    import re

    contenu = navigateur.get("/admin/module/agenda/").content.decode()
    barre_haute = re.search(r"<h1[^>]*>(.*?)</h1>", contenu, re.S).group(1)
    titre_du_contenu = re.search(
        r'<h2 class="tb-entete-titre"[^>]*>(.*?)</h2>', contenu, re.S
    ).group(1)

    def _texte(html):
        return " ".join(re.sub(r"<[^>]+>", " ", html).split())

    assert _texte(barre_haute) != _texte(titre_du_contenu)


@pytest.mark.django_db
def test_le_nom_du_lieu_apparait_sur_tous_les_types_de_page(navigateur):
    """
    Le haut du rail etait VIDE sur le tableau de bord, la page de domaine et
    la page de module, alors qu'une changelist affichait bien le nom.
    Le rail changeait donc d'aspect selon la page.

    Cause : ces trois gabarits etendaient base_simple.html, qui ne definit
    pas le bloc `branding`.
    / The three pages extended base_simple.html, which has no branding block.
    """
    for adresse in [
        "/admin/",
        "/admin/domaine/lespass/",
        "/admin/module/agenda/",
        "/admin/BaseBillet/event/",
    ]:
        contenu = navigateur.get(adresse).content.decode()
        assert 'id="site-name"' in contenu, f"{adresse} n'affiche pas le nom du lieu."


@pytest.mark.django_db
def test_le_nom_affiche_suit_le_nom_du_lieu(lieu_et_superadmin):
    """
    Le rail affiche le nom du lieu, et « TiBillet » quand ce nom est vide.

    On NE MUTE PAS la configuration ici : django-solo relit la base a chaque
    `get_solo()`, une modification en memoire serait donc ignoree — c'est le
    piege deja documente dans test_module_newsletter_activation.py. On lit
    donc les lieux tels qu'ils sont, et on verifie la regle sur chacun.
    / No mutation: django-solo re-reads the DB on every get_solo(), so an
      in-memory change would be ignored.
    """
    from Administration.admin.dashboard import nom_du_lieu

    lieux_verifies = 0
    for tenant in Client.objects.exclude(schema_name="public"):
        with tenant_context(tenant):
            organisation = Configuration.get_solo().organisation
            affiche = nom_du_lieu(None)

        attendu = organisation or "TiBillet"
        assert affiche == attendu, (
            f"Le lieu « {tenant.schema_name} » affiche {affiche!r} "
            f"alors qu'on attend {attendu!r}."
        )
        assert affiche, "Le rail ne doit jamais afficher un nom vide."
        lieux_verifies += 1

    assert lieux_verifies, "Aucun lieu à vérifier."


@pytest.mark.django_db
def test_le_nom_du_lieu_ne_fait_jamais_planter_l_admin(db):
    """
    La lecture peut echouer hors contexte de lieu (schema public). On ne
    fait pas tomber tout l'admin pour un titre de colonne.
    / Reading may fail outside a tenant context; never crash over a heading.
    """
    from unittest.mock import patch

    from Administration.admin import dashboard

    with patch.object(
        dashboard.Configuration, "get_solo", side_effect=RuntimeError("hors contexte")
    ):
        assert dashboard.nom_du_lieu(None) == "TiBillet"


@pytest.mark.django_db
def test_la_page_de_module_ramene_a_son_domaine(navigateur):
    """
    Sans lien de retour, on ne remonte d'un module que par la sidebar.
    / Without a back link, only the sidebar goes up a level.
    """
    contenu = navigateur.get("/admin/module/agenda/").content.decode()
    assert 'data-testid="module-page-retour"' in contenu
    assert "/admin/domaine/lespass/" in contenu


@pytest.mark.django_db
def test_la_liste_porte_la_categorie_ouverte(navigateur):
    """
    La categorie est posee sur la LISTE : c'est elle qui donne leur couleur
    aux pastilles d'icone, comme dans la maquette (vert / orange / bleu).
    / The category sits on the list and colours its icon tiles.
    """
    import re

    for categorie in ["gerer", "configurer"]:
        contenu = navigateur.get(
            f"/admin/module/agenda/?onglet={categorie}"
        ).content.decode()
        posees = re.findall(r'data-categorie="(\w+)"', contenu)
        assert posees == [categorie], f"attendu {categorie}, obtenu {posees}"


@pytest.mark.django_db
def test_chaque_page_listee_a_une_description_ou_rien(lieu_et_superadmin):
    """
    Une page absente du tableau des descriptions s'affiche SANS description.
    On n'invente pas de texte pour combler un trou.
    / A page missing from the table simply shows none: no filler text.
    """
    from django.test import RequestFactory

    from Administration.admin import dashboard

    tenant, _domaine, _utilisateur = lieu_et_superadmin
    requete = RequestFactory().get("/admin/")
    with tenant_context(tenant):
        sections = dashboard._construire_sections_modules(requete)
    carte = dashboard._carte_des_liens_vers_modeles()

    for section in sections:
        if not section.get("_slug"):
            continue
        par_categorie = dashboard._categoriser_les_pages(section["items"], carte)
        for pages in par_categorie.values():
            for page in pages:
                description = page.get("description")
                assert description is None or str(description).strip(), (
                    f"{page['title']} a une description vide : "
                    "mieux vaut aucune description qu'une chaîne vide."
                )


@pytest.mark.django_db
def test_toutes_les_pages_connues_ont_une_description(lieu_et_superadmin):
    """
    Le tableau des descriptions doit couvrir exactement celui des categories :
    ni page oubliee, ni description orpheline pour une page supprimee.
    / The description table must cover exactly the category table.
    """
    from Administration.admin.dashboard import (
        CATEGORIE_DES_PAGES,
        DESCRIPTION_DES_PAGES,
    )

    oubliees = sorted(set(CATEGORIE_DES_PAGES) - set(DESCRIPTION_DES_PAGES))
    orphelines = sorted(set(DESCRIPTION_DES_PAGES) - set(CATEGORIE_DES_PAGES))

    assert not oubliees, f"Pages sans description : {oubliees}"
    assert not orphelines, f"Descriptions sans page : {orphelines}"


@pytest.mark.django_db
def test_le_tableau_de_bord_a_son_propre_titre(navigateur):
    """
    Django appelait cette page « Site d'administration », ce qui ne dit rien
    de ce qu'on y trouve.
    / Django called it "Site administration", which says nothing.
    """
    contenu = navigateur.get("/admin/").content.decode()
    assert "Tableau de bord" in contenu
    assert 'data-testid="dashboard-header"' in contenu


@pytest.mark.django_db
def test_le_tableau_de_bord_est_une_entree_autonome_du_rail(lieu_et_superadmin):
    """
    La maquette met « Tableau de bord » tout en haut du rail, hors de tout
    groupe. Un groupe Unfold SANS titre ne rend que ses liens : c'est ainsi
    qu'on obtient une entree autonome.
    / A group with no title renders only its links.
    """
    from django.test import RequestFactory

    from Administration.admin.dashboard import get_sidebar_navigation

    tenant, _domaine, _utilisateur = lieu_et_superadmin
    requete = RequestFactory().get("/admin/")
    with tenant_context(tenant):
        navigation = get_sidebar_navigation(requete)

    premier = navigation[0]
    assert not premier.get("title"), "Le premier groupe devrait être sans titre."
    assert len(premier["items"]) == 1
    assert str(premier["items"][0]["title"]) == "Tableau de bord"


def _liens_du_menu_du_lieu(navigateur, adresse):
    """
    Les liens du menu qui s'ouvre sous le nom du lieu, dans l'ordre.
    / The links of the menu that opens under the venue name, in order.

    On se limite au bloc du menu : la classe des libelles sert aussi
    ailleurs dans la page, un comptage global donnerait n'importe quoi.
    / Scoped to the menu block: its label class is used elsewhere too.
    """
    import re

    contenu = navigateur.get(adresse).content.decode()
    debut = contenu.find('x-show="openDropdown"')
    assert debut > 0, f"Le menu du lieu est introuvable sur {adresse}."
    return re.findall(r'<a href="([^"]+)"', contenu[debut:debut + 1800])


@pytest.mark.django_db
def test_le_menu_du_lieu_ramene_a_son_site_public(navigateur, lieu_et_superadmin):
    """
    Le menu qui s'ouvre sous le nom du lieu doit d'abord proposer de revenir
    sur le site public du lieu. Il n'y avait qu'un lien vers tibillet.coop.

    Le lien est relatif (« / ») : le site public d'un lieu est la racine de
    SON domaine, donc c'est juste pour tous les lieux, sans fabriquer d'URL
    absolue.
    / The venue menu must first offer a way back to the venue's public site.
    """
    liens = _liens_du_menu_du_lieu(navigateur, "/admin/")
    assert liens, "Le menu du lieu est vide."
    assert liens[0] == "/", (
        f"Le premier lien du menu devrait ramener au site du lieu, pas {liens[0]!r}."
    )

    # Et ce lien doit vraiment mener quelque part.
    # / And that link must actually lead somewhere.
    _tenant, domaine, _utilisateur = lieu_et_superadmin
    assert HttpClient(HTTP_HOST=domaine).get("/").status_code == 200


@pytest.mark.django_db
def test_le_menu_du_lieu_mene_a_sa_page_d_identite(navigateur):
    """
    La maquette epingle un crayon au nom du lieu pour aller droit a sa
    configuration. On a renonce a forker le gabarit d'Unfold pour cela :
    l'entree vit dans le menu qui s'ouvre deja sous le nom.
    / We declined to fork Unfold's header for this; the entry lives in the
      menu that already opens under the venue name.

    Les deux entrees qui concernent LE LIEU sont groupees, le lien externe
    reste en dernier.
    / The two venue-related entries are grouped; the external link stays last.
    """
    from django.urls import reverse

    adresse_identite = reverse("staff_admin:BaseBillet_configuration_changelist")
    liens = _liens_du_menu_du_lieu(navigateur, "/admin/")

    assert liens == ["/", adresse_identite, "https://tibillet.coop"], (
        f"L'ordre du menu a changé : {liens}"
    )

    # Un lien mort passerait un simple test de presence.
    # / A dead link would pass a mere presence check.
    assert navigateur.get(adresse_identite).status_code == 200


@pytest.mark.django_db
def test_le_menu_du_lieu_est_le_meme_partout(navigateur):
    """
    Le menu doit etre identique sur les quatre types de page. C'est le defaut
    deja corrige une fois pour le nom du lieu, absent de trois ecrans : il ne
    doit pas revenir par une autre porte.
    / The menu must be identical on all four page types: the same defect was
      already fixed once for the venue name.
    """
    reference = None
    for adresse in [
        "/admin/",
        "/admin/domaine/lespass/",
        "/admin/module/agenda/",
        "/admin/BaseBillet/event/",
    ]:
        liens = _liens_du_menu_du_lieu(navigateur, adresse)
        if reference is None:
            reference = liens
        assert liens == reference, f"Le menu diffère sur {adresse} : {liens}"


# --------------------------------------------------------------------------- #
# La carte de la caisse : ses liens d'ouverture                                #
# --------------------------------------------------------------------------- #


@pytest.fixture
def lieu_avec_admin(db):
    """
    Un lieu qui a un ADMIN DU LIEU, et un client HTTP connecte comme lui.
    / A venue that has a venue admin, and a client logged in as them.

    On ne reutilise PAS la fixture du superadmin : elle rend le premier lieu
    qui a un superadmin, ce qui n'est pas forcement un lieu qui a un admin.
    Le premier essai le faisait, et les deux tests de cette regression se
    contentaient de passer en « skip » sans rien verifier.
    / Do not reuse the superadmin fixture: it returns the first venue with a
      superuser, which need not have a venue admin — the first attempt did,
      and both regression tests silently skipped.

    Le superadmin ne suffit pas non plus pour la caisse : elle exige un admin
    DU LIEU (ou un terminal appaire). Un superadmin qui n'administre pas ce
    lieu recoit un 403 — c'est voulu, pas un bug.
    / A superuser is not enough either: the POS wants a venue admin.
    """
    for tenant in Client.objects.exclude(schema_name="public"):
        domaine = tenant.domains.first()
        if not domaine:
            continue
        with tenant_context(tenant):
            admins = [
                utilisateur
                for utilisateur in TibilletUser.objects.all()[:200]
                if utilisateur.is_tenant_admin(tenant)
            ]
        if admins:
            client = HttpClient(HTTP_HOST=domaine.domain)
            client.force_login(admins[0])
            return tenant, client
    pytest.skip("Aucun lieu avec un admin de lieu.")


def _carte_de_la_caisse(tenant, **forcages):
    """
    La carte de la caisse, pour un etat donne.
    / The POS card, for a given state.

    On force la configuration EN MEMOIRE et on la sert via un patch : la
    base de dev est partagee, on n'y ecrit pas pour un test d'affichage.
    / The config is forced in memory and served through a patch: the dev DB
      is shared, we do not write to it for a display test.
    """
    from Administration.admin import dashboard

    with tenant_context(tenant):
        configuration = Configuration.get_solo()
        for champ, valeur in forcages.items():
            setattr(configuration, champ, valeur)
        with patch.object(
            dashboard.Configuration, "get_solo", staticmethod(lambda: configuration)
        ):
            cartes = dashboard._build_modules_context(configuration)

    return next(carte for carte in cartes if carte["type"] == "pos")


@pytest.mark.django_db
def test_la_caisse_active_affiche_son_lien_d_ouverture(lieu_avec_admin):
    """
    LE test de cette regression.

    La carte de la caisse portait un lien « Open POS ». Il a disparu quand la
    carte est devenue generique : plus aucun acces a la caisse depuis l'admin.
    / The POS card carried an "Open POS" link. It vanished when the card
      became generic, leaving no way into the POS from the admin.
    """
    tenant, navigateur_admin = lieu_avec_admin
    with tenant_context(tenant):
        if not Configuration.get_solo().module_caisse:
            pytest.skip("La caisse n'est pas active sur ce lieu.")

    import re

    contenu = navigateur_admin.get("/admin/").content.decode()
    assert 'data-testid="dashboard-card-pos-open-link"' in contenu, (
        "Le lien d'ouverture de la caisse a disparu du tableau de bord."
    )

    # Un lien mort passerait un simple test de presence.
    # / A dead link would pass a mere presence check.
    liens = re.findall(r'<a class="tb-carte-ouvrir"\s+href="([^"]+)"', contenu)
    assert liens, "Le lien est annoncé mais n'a pas d'adresse."
    assert navigateur_admin.get(liens[0]).status_code == 200, (
        f"Le lien mène à {liens[0]}, qui ne répond pas."
    )


@pytest.mark.django_db
def test_le_lien_de_la_caisse_est_aussi_sur_la_page_du_domaine(lieu_avec_admin):
    """
    La carte est la meme sur les deux ecrans : le lien doit suivre.
    / The card is shared by both screens: the link must follow.
    """
    tenant, navigateur_admin = lieu_avec_admin
    with tenant_context(tenant):
        if not Configuration.get_solo().module_caisse:
            pytest.skip("La caisse n'est pas active sur ce lieu.")

    contenu = navigateur_admin.get("/admin/domaine/laboutik/").content.decode()
    assert 'data-testid="dashboard-card-pos-open-link"' in contenu


@pytest.mark.django_db
def test_les_trois_etats_de_la_caisse_ont_le_bon_lien(lieu_et_superadmin):
    """
    Trois etats, trois comportements :
      - V2 active  -> l'interface de caisse, dans le meme onglet ;
      - V1 active  -> le serveur V1, dans un nouvel onglet (il est ailleurs) ;
      - eteinte    -> AUCUN lien. La permission de la caisse refuse toute
        route POS module eteint : un lien menerait droit a un 403.
    / Three states, three behaviours; none when the POS is off, because its
      permission denies every POS route then.
    """
    tenant, _domaine, _utilisateur = lieu_et_superadmin

    active = _carte_de_la_caisse(tenant, module_caisse=True, server_cashless="")
    assert active["state"] == "v2_active"
    assert active["lien_externe"], "La caisse V2 doit pouvoir s'ouvrir."
    assert active["externe_nouvel_onglet"] is False

    v1 = _carte_de_la_caisse(
        tenant, module_caisse=False, server_cashless="https://v1.exemple.test"
    )
    assert v1["state"] == "v1_active"
    assert v1["lien_externe"] == "https://v1.exemple.test"
    assert v1["externe_nouvel_onglet"] is True

    eteinte = _carte_de_la_caisse(tenant, module_caisse=False, server_cashless="")
    assert eteinte["state"] == "inactive"
    assert not eteinte["lien_externe"], (
        "Caisse éteinte : un lien mènerait à un 403."
    )


@pytest.mark.django_db
def test_un_lieu_en_v1_garde_un_acces_a_laboutik(lieu_et_superadmin):
    """
    Meme regression, autre etat : un lieu reste en V1 n'avait plus aucun
    acces a son interface depuis l'admin.
    / Same regression, other state: a venue still on V1 had lost every way in.
    """
    tenant, _domaine, _utilisateur = lieu_et_superadmin
    v1 = _carte_de_la_caisse(
        tenant, module_caisse=False, server_cashless="https://v1.exemple.test"
    )
    assert v1["testid_externe"] == "dashboard-card-pos-v1-link"
    assert str(v1["libelle_externe"])


# --------------------------------------------------------------------------- #
# Le depliage anime d'un groupe du rail                                        #
# --------------------------------------------------------------------------- #


def _conteneurs_de_sous_menu(navigateur, adresse):
    """
    Les conteneurs de sous-menu du rail, avec leur etat initial.
    / The sidebar's submenu wrappers, with their initial state.

    :return: liste de (ouvert_au_chargement, lie_a_alpine)
    """
    import re

    contenu = navigateur.get(adresse).content.decode()
    debut = contenu.find('id="nav-sidebar-apps"')
    assert debut > 0, f"Le rail est introuvable sur {adresse}."
    bloc = contenu[debut:contenu.find("navigation_user", debut)]

    return [
        (bool(ouvert), "x-bind" in attributs)
        for ouvert, attributs in re.findall(
            r'<div class="tb-sousmenu( tb-sousmenu-ouvert)?"([^>]*)>', bloc
        )
    ]


@pytest.mark.django_db
def test_le_sous_menu_n_utilise_plus_x_show(navigateur):
    """
    `x-show` bascule `display`, et `display` ne s'anime pas : c'est pour cela
    que le sous-menu surgissait d'un coup. Le conteneur anime sa hauteur a la
    place.
    / x-show toggles `display`, which cannot animate; hence the pop.
    """
    contenu = navigateur.get("/admin/").content.decode()
    assert 'x-show="navigationOpen"' not in contenu, (
        "x-show est de retour sur le sous-menu : l'animation ne jouera plus."
    )
    assert 'class="tb-sousmenu' in contenu


@pytest.mark.django_db
def test_les_liens_du_sous_menu_sont_toujours_rendus(navigateur, lieu_et_superadmin):
    """
    L'enveloppe ne doit rien avaler : tous les liens de modules restent la.
    / The wrapper must not swallow anything: every module link stays.
    """
    from django.test import RequestFactory

    from Administration.admin.dashboard import get_sidebar_navigation

    tenant, _domaine, _utilisateur = lieu_et_superadmin
    with tenant_context(tenant):
        navigation = get_sidebar_navigation(RequestFactory().get("/admin/"))

    contenu = navigateur.get("/admin/").content.decode()
    for groupe in navigation:
        for item in groupe["items"]:
            assert str(item["title"]) in contenu, (
                f"Le lien « {item['title']} » a disparu du rail."
            )


@pytest.mark.django_db
def test_les_groupes_non_repliables_restent_ouverts_sans_alpine(navigateur):
    """
    Les groupes non repliables n'ont PAS de x-data, donc pas de variable
    `navigationOpen`. Y poser une liaison Alpine leverait une erreur dans la
    console a chaque page.
    / Non-collapsible groups have no navigationOpen variable: binding to it
      would raise an Alpine error on every page.
    """
    conteneurs = _conteneurs_de_sous_menu(navigateur, "/admin/")
    sans_liaison = [(ouvert, lie) for ouvert, lie in conteneurs if not lie]

    assert sans_liaison, "Aucun groupe non repliable : test à revoir."
    for ouvert, _lie in sans_liaison:
        assert ouvert, "Un groupe non repliable doit être ouvert."


@pytest.mark.django_db
def test_le_rail_ne_s_anime_pas_au_chargement(navigateur):
    """
    Le groupe du module courant s'ouvre tout seul. Si la classe etait posee
    par Alpine APRES le premier rendu, le rail s'animerait a CHAQUE
    chargement de page — insupportable. Elle est donc posee cote serveur.
    / If Alpine set the class after first paint, the rail would animate on
      every page load. It is set server-side instead.
    """
    # Sur la page d'un module, le groupe de son domaine doit deja etre
    # ouvert dans le HTML rendu, sans attendre Alpine.
    # / On a module page, its domain group must already be open in the HTML.
    conteneurs = _conteneurs_de_sous_menu(navigateur, "/admin/module/agenda/")
    ouverts_et_lies = [ouvert for ouvert, lie in conteneurs if lie and ouvert]
    assert len(ouverts_et_lies) == 1, (
        "Le groupe du module courant devrait être déplié dans le HTML rendu."
    )

    # Sur le tableau de bord, aucun domaine n'est courant : tout est replie.
    # / On the dashboard no domain is current: everything is folded.
    conteneurs = _conteneurs_de_sous_menu(navigateur, "/admin/")
    assert not [ouvert for ouvert, lie in conteneurs if lie and ouvert]
