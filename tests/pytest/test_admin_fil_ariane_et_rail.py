"""
Savoir ou l'on est : le rail et le fil d'Ariane sur une changelist.
/ Knowing where you are: the sidebar and the breadcrumb on a changelist.

LOCALISATION : tests/pytest/test_admin_fil_ariane_et_rail.py

CE QUE CES TESTS PROTEGENT
--------------------------
Depuis le passage a la navigation Domaines -> Modules, les pages d'un module
ont quitte le rail : seul le module y figure. Deux consequences etaient
restees non corrigees, et toutes deux echouent EN SILENCE — aucune erreur,
aucune 500, juste une interface qui ne dit plus ou l'on se trouve.

  1. LE RAIL. Sur /admin/BaseBillet/event/, plus rien n'etait surligne et
     aucun domaine n'etait deplie : la comparaison d'URL d'Unfold ne trouvait
     plus de lien correspondant a request.path.

  2. LE FIL D'ARIANE. Il ouvrait sur l'application Django
     (« Billetterie > Evenements »), un nom qui ressemble a un module sans en
     etre un, et dont le lien mene a /admin/BaseBillet/.

/ Both failure modes are silent: no error, just a UI that no longer says
  where you are.

LE PIEGE PRINCIPAL, couvert par test_la_page_du_module_reste_surlignee :
poser nous-memes la cle « active » DESACTIVE le calcul d'Unfold pour ce lien
(unfold/sites.py:377). Notre valeur doit donc aussi couvrir le cas qui
marchait deja — etre SUR la page du module.
/ Setting "active" ourselves disables Unfold's own computation: our value
  must also cover the case that already worked.

Meme pattern que les autres tests d'admin : base de dev vivante.
/ Same pattern as the other admin tests: live dev DB.
"""

import re

import pytest
from django.test import Client as HttpClient, RequestFactory
from django_tenants.utils import tenant_context

from Administration.admin import dashboard
from Administration.admin.site import staff_admin_site
from AuthBillet.models import TibilletUser
from Customers.models import Client


@pytest.fixture(scope="session")
def django_db_setup():
    # Reutilise la base de dev (pas de creation de test DB).
    # / Reuse the dev database.
    pass


@pytest.fixture
def lieu_avec_agenda(db):
    """
    Un lieu dont le module Agenda est actif.

    On ne se contente PAS du premier lieu venu : tous les tests ci-dessous
    portent sur le module Agenda, et un lieu qui ne l'a pas activerait des
    assertions vides. Un test qui se saute ne protege rien.
    / Skipping on the wrong venue would protect nothing.
    """
    for tenant in Client.objects.exclude(schema_name="public"):
        domaine = tenant.domains.first()
        if not domaine:
            continue
        with tenant_context(tenant):
            utilisateur = TibilletUser.objects.filter(is_superuser=True).first()
            if not utilisateur:
                continue
            sections = dashboard._construire_sections_modules(
                RequestFactory().get("/admin/")
            )
            slugs = {s.get("_slug") for s in sections}
        if "agenda" in slugs:
            return tenant, domaine.domain, utilisateur
    pytest.skip("Aucun lieu avec un superadmin et le module Agenda actif.")


@pytest.fixture
def navigateur(lieu_avec_agenda):
    """Un client HTTP deja connecte sur le lieu."""
    _tenant, domaine, utilisateur = lieu_avec_agenda
    client = HttpClient(HTTP_HOST=domaine)
    client.force_login(utilisateur)
    return client


def _rail(tenant, utilisateur, chemin):
    """
    L'etat du rail sur une page : ce qui est surligne, ce qui est deplie.
    / The sidebar state on a page: what is highlighted, what is expanded.

    On interroge get_sidebar_list() plutot que le HTML : c'est la donnee que
    le gabarit affiche, et elle se lit sans dependre des classes Tailwind.
    / We read the data the template renders, not volatile CSS classes.
    """
    requete = RequestFactory().get(chemin)
    requete.user = utilisateur
    with tenant_context(tenant):
        groupes = staff_admin_site.get_sidebar_list(requete)

    surlignes = [
        str(item["title"])
        for groupe in groupes
        for item in groupe.get("items", [])
        if item.get("active")
    ]
    deplies = [
        str(groupe.get("title") or "")
        for groupe in groupes
        if any(i.get("active") for i in groupe.get("items", [])) or groupe.get("ouvert")
    ]
    return surlignes, deplies


def _entrees_du_fil(html):
    """
    Les entrees du fil d'Ariane : (libelle, lien ou None).
    / The breadcrumb entries: (label, link or None).

    header_title.html rend chaque entree avec la classe « align-middle », en
    <a> si elle a un lien, en <span> sinon.
    """
    barre = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
    if not barre:
        return []

    entrees = []
    motif = r'<(a|span)([^>]*class="align-middle[^"]*"[^>]*)>(.*?)</\1'
    for balise, attributs, libelle in re.findall(motif, barre.group(1), re.S):
        lien = re.search(r'href="([^"]*)"', attributs)
        texte = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", libelle)).strip()
        entrees.append((texte, lien.group(1) if lien else None))
    return entrees


# --------------------------------------------------------------------------- #
# Volet 1 — le rail surligne le module courant                                 #
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_une_changelist_surligne_son_module(lieu_avec_agenda):
    """C'est la demande : voir ou l'on est depuis une changelist."""
    tenant, _domaine, utilisateur = lieu_avec_agenda
    surlignes, deplies = _rail(tenant, utilisateur, "/admin/BaseBillet/event/")

    assert surlignes == ["Agenda et Billetterie"], (
        "Une changelist doit surligner SON module, et lui seul."
    )
    assert "Lespass" in deplies, (
        "Le domaine du module courant doit etre deplie, sinon le lien "
        "surligne reste invisible."
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    "chemin",
    [
        "/admin/BaseBillet/event/",
        "/admin/BaseBillet/event/add/",
        "/admin/BaseBillet/event/?q=test",
    ],
)
def test_les_pages_filles_surlignent_le_meme_module(lieu_avec_agenda, chemin):
    """
    Une fiche, un ajout et une recherche restent « dans » le module.
    / A detail page, an add form and a search stay inside the module.
    """
    tenant, _domaine, utilisateur = lieu_avec_agenda
    surlignes, _ = _rail(tenant, utilisateur, chemin)
    assert surlignes == ["Agenda et Billetterie"]


@pytest.mark.django_db
def test_la_page_du_module_reste_surlignee(lieu_avec_agenda):
    """
    LE PIEGE. Ce cas marchait AVANT le correctif, grace au calcul d'Unfold.
    Poser la cle « active » nous-memes desactive ce calcul : si notre valeur
    ne couvrait que les changelists, on aurait repare un ecran en cassant un
    autre.
    / This case already worked; setting "active" ourselves could break it.
    """
    tenant, _domaine, utilisateur = lieu_avec_agenda
    surlignes, deplies = _rail(tenant, utilisateur, "/admin/module/agenda/")

    assert surlignes == ["Agenda et Billetterie"]
    assert "Lespass" in deplies


@pytest.mark.django_db
def test_une_page_de_section_autonome_garde_le_calcul_d_unfold(lieu_avec_agenda):
    """
    Les pages des sections autonomes sont de vrais liens de rail : Unfold les
    surligne deja tout seul. Le correctif ne doit pas s'en meler.
    / Standalone sections are real sidebar links; Unfold already handles them.
    """
    tenant, _domaine, utilisateur = lieu_avec_agenda
    surlignes, _ = _rail(tenant, utilisateur, "/admin/BaseBillet/configuration/")
    assert surlignes == ["Paramètres"]


@pytest.mark.django_db
def test_une_changelist_hors_module_ne_surligne_rien(lieu_avec_agenda):
    """
    31 changelists sur 82 ne figurent nulle part dans le rail. Il n'y a rien
    a y surligner — et surtout, rien ne doit planter.
    / 31 of 82 changelists appear nowhere in the sidebar: nothing to
      highlight, and above all nothing must crash.
    """
    tenant, _domaine, utilisateur = lieu_avec_agenda
    surlignes, _ = _rail(tenant, utilisateur, "/admin/BaseBillet/product/")
    assert surlignes == []


@pytest.mark.django_db
def test_aucune_page_n_appartient_a_deux_modules(lieu_avec_agenda):
    """
    L'invariant sur lequel repose tout le lot : une page a UN module.

    Verifie a la conception sur lespass / festival / meta. Si un rangement
    futur creait l'ambiguite, le rail surlignerait deux modules a la fois et
    le fil d'Ariane designerait un parent arbitraire. Ce test le dira.
    / The invariant the whole change rests on: one page, one module.
    """
    tenant, _domaine, _utilisateur = lieu_avec_agenda
    with tenant_context(tenant):
        sections = dashboard._construire_sections_modules(
            RequestFactory().get("/admin/")
        )

    proprietaire = {}
    doublons = []
    for section in sections:
        for page in section.get("items", []):
            lien = str(page.get("link") or "")
            if not lien.startswith("/admin/"):
                continue
            if lien in proprietaire:
                doublons.append((lien, proprietaire[lien], str(section.get("title"))))
            proprietaire[lien] = str(section.get("title"))

    assert not doublons, f"Pages rangees dans deux sections : {doublons}"


# --------------------------------------------------------------------------- #
# Volet 2 — le fil d'Ariane nomme le module                                    #
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_le_fil_d_ariane_nomme_le_module_et_non_l_application(navigateur):
    """
    « Billetterie > Evenements » devient « Agenda et Billetterie > Evenements ».
    """
    reponse = navigateur.get("/admin/BaseBillet/event/")
    assert reponse.status_code == 200
    entrees = _entrees_du_fil(reponse.content.decode())

    assert entrees, "Le fil d'Ariane a disparu."
    libelle, lien = entrees[0]
    assert libelle == "Agenda et Billetterie", (
        f"La premiere entree doit nommer le module, pas l'app Django : {entrees}"
    )
    assert lien == "/admin/module/agenda/"

    liens = [lien for _libelle, lien in entrees]
    assert "/admin/BaseBillet/" not in liens, (
        "Le lien vers la page de l'application Django doit avoir disparu."
    )


@pytest.mark.django_db
def test_la_cible_du_fil_d_ariane_repond(navigateur):
    """
    Un lien mort passerait un simple test de presence. On le suit.
    / A dead link would pass a mere presence test. Follow it.
    """
    entrees = _entrees_du_fil(
        navigateur.get("/admin/BaseBillet/event/").content.decode()
    )
    assert navigateur.get(entrees[0][1]).status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize(
    "chemin, entrees_attendues",
    [
        ("/admin/BaseBillet/event/", 2),  # module > modele
        ("/admin/BaseBillet/event/add/", 2),
    ],
)
def test_le_fil_d_ariane_garde_sa_longueur(navigateur, chemin, entrees_attendues):
    """
    La balise REMPLACE une entree : elle n'en ajoute ni n'en retire aucune.
    Un fil d'Ariane tronque serait pire que le defaut corrige.
    / The tag replaces one entry; it never adds nor removes any.
    """
    entrees = _entrees_du_fil(navigateur.get(chemin).content.decode())
    assert len(entrees) == entrees_attendues, entrees


@pytest.mark.django_db
def test_une_changelist_hors_module_garde_son_fil_d_ariane(navigateur):
    """
    Ce qui protege les 31 changelists sans module, et tout modele ajoute
    demain sans etre range : au moindre doute, on ne touche a rien.
    / What protects the 31 module-less changelists, and any model added
      tomorrow without being sorted.
    """
    entrees = _entrees_du_fil(
        navigateur.get("/admin/BaseBillet/configuration/").content.decode()
    )
    assert entrees[0] == ("Billetterie", "/admin/BaseBillet/"), (
        f"Le fil d'Ariane d'Unfold devait rester intact : {entrees}"
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    "chemin",
    ["/admin/", "/admin/module/agenda/", "/admin/domaine/lespass/"],
)
def test_les_pages_sans_modele_gardent_un_seul_titre(navigateur, chemin):
    """
    La balise est appelee sur TOUTES les pages d'admin. Sur celles qui n'ont
    pas de modele, header_title ne produit qu'une entree — le message
    d'accueil — qu'il ne faut surtout pas ecraser par un nom de module.
    / On model-less pages header_title yields a single "Welcome" entry, which
      must not be overwritten by a module name.
    """
    reponse = navigateur.get(chemin)
    assert reponse.status_code == 200
    html = reponse.content.decode()
    assert html.count("<h1") == 1
    assert len(_entrees_du_fil(html)) <= 1
