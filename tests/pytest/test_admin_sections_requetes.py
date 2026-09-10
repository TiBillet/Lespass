"""
Le cout en requetes des `list_sections` d'une changelist.
/ The query cost of a changelist's `list_sections`.

LOCALISATION : tests/pytest/test_admin_sections_requetes.py

CE QUE CES TESTS PROTEGENT
--------------------------
Unfold rend les sections **cote serveur, pour chaque ligne, a chaque
affichage** : `{% render_section %}` est a l'interieur de la boucle sur les
lignes (`unfold/templates/admin/change_list_results.html:57`), et
`x-show="rowOpen"` ne fait que CACHER cote navigateur du HTML deja produit.

Consequence : une section qui interroge la base coute une requete PAR LIGNE,
payee meme si personne ne deplie jamais rien. Mesure avant correctif :

    EventAdmin   21 lignes -> 75 requetes
    temoin sans section    -> 19 requetes

C'est le genre de defaut qui ne leve aucune erreur et n'apparait dans aucun
test fonctionnel : il se voit uniquement en COMPTANT les requetes. D'ou ce
fichier.
/ Sections are rendered server-side for every row on every load, so a querying
  section costs one query per row even if nobody ever expands it.

LE PIEGE A EVITER EN LISANT CES TESTS : ne pas les transformer en assertions
sur un nombre exact de requetes. Ce nombre depend des donnees du lieu et
bougerait a chaque evolution. Ce qui compte, et ce qu'on teste, c'est que le
cout **ne croisse pas avec le nombre de lignes**.
/ Do not assert an exact query count: assert that it does not grow with rows.

Meme pattern que les autres tests d'admin : base de dev vivante.
"""

import pytest
from django.db import connection
from django.test import Client as HttpClient, RequestFactory
from django.test.utils import CaptureQueriesContext
from django_tenants.utils import tenant_context

from AuthBillet.models import TibilletUser
from Customers.models import Client


# Cout d'une changelist SANS aucune section, mesure sur le lieu de dev :
# /admin/BaseBillet/configuration/ -> 19 requetes. Sert de base au calcul du
# cout par ligne. Approximatif par nature — d'ou le seuil large ci-dessous.
# / Baseline cost of a section-less changelist, measured on the dev venue.
_COUT_FIXE_D_UNE_CHANGELIST = 19


@pytest.fixture(scope="session")
def django_db_setup():
    # Reutilise la base de dev (pas de creation de test DB).
    # / Reuse the dev database.
    pass


@pytest.fixture
def lieu_avec_evenements(db):
    """
    Un lieu qui a AU MOINS deux evenements affichables.

    Avec zero ou une ligne, une N+1 est indiscernable d'un cout fixe : le test
    passerait sans rien prouver. On refuse donc de se rabattre sur un lieu
    vide.
    / With fewer than two rows an N+1 is indistinguishable from a fixed cost.
    """
    from BaseBillet.models import Event

    for tenant in Client.objects.exclude(schema_name="public"):
        domaine = tenant.domains.first()
        if not domaine:
            continue
        with tenant_context(tenant):
            utilisateur = TibilletUser.objects.filter(is_superuser=True).first()
            if not utilisateur:
                continue
            nombre = (
                Event.objects.exclude(categorie=Event.ACTION)
                .exclude(parent__isnull=False)
                .count()
            )
        if nombre >= 2:
            return tenant, domaine.domain, utilisateur
    pytest.skip("Aucun lieu avec un superadmin et au moins deux evenements.")


@pytest.fixture
def navigateur(lieu_avec_evenements):
    _tenant, domaine, utilisateur = lieu_avec_evenements
    client = HttpClient(HTTP_HOST=domaine)
    client.force_login(utilisateur)
    return client


def _requetes_et_lignes(navigateur, chemin):
    """Le nombre de requetes SQL et de lignes rendues pour une page."""
    navigateur.get(chemin)  # chauffe les caches (sessions, permissions)
    with CaptureQueriesContext(connection) as requetes:
        reponse = navigateur.get(chemin)
    assert reponse.status_code == 200, chemin
    return len(requetes), reponse.content.decode().count('class="data-row')


# --------------------------------------------------------------------------- #
# EventAdmin — ChildActionsSummaryTable                                        #
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_le_cout_restant_par_ligne_est_celui_qu_on_a_choisi(navigateur):
    """
    Test de constat, pas d'objectif : il FIGE ce qu'on a decide de ne pas
    corriger, pour qu'une aggravation se voie.

    Deux sections rendent la liste des evenements. On en a corrige UNE
    (ChildActionsSummaryTable). L'autre, EventPricesSummaryTable, reste a une
    requete par ligne **par decision** : elle repose sur
    `Event.pricesold_for_sections`, une property qui construit un queryset
    filtre sur `self` — impossible a precharger sans reecrire une requete a
    fenetres qui alimente un affichage comptable. Le risque ne valait pas le
    gain.
    / A characterization test: it pins the cost we deliberately kept, so that
      a regression becomes visible.

    Si ce test casse en HAUSSE, une nouvelle N+1 est apparue.
    Si il casse en BAISSE, quelqu'un a optimise : mettre a jour le chiffre.
    """
    requetes, lignes = _requetes_et_lignes(navigateur, "/admin/BaseBillet/event/")
    assert lignes > 0, "Aucune ligne affichee : le test ne prouverait rien."

    cout_par_ligne = (requetes - _COUT_FIXE_D_UNE_CHANGELIST) / lignes
    assert cout_par_ligne < 2.0, (
        f"{requetes} requetes pour {lignes} lignes, soit {cout_par_ligne:.1f} "
        "par ligne. Avant correctif c'etait ~2,7. Une nouvelle N+1 est apparue."
    )


@pytest.fixture
def evenement_avec_enfants(lieu_avec_evenements):
    """
    Un evenement portant DEUX evenements enfants.

    POURQUOI CETTE FIXTURE EXISTE. Sans enfant, la section se masque avant toute
    requete et l'assertion de cout devient une borne a zero : le test passait
    sans rien prouver. C'est precisement le chemin « avec enfants » qui gardait
    une requete par ligne.
    / Without children the section short-circuits and the assertion becomes a
      bound of zero: the test proved nothing about the path that still queried.

    `django_db` annule la transaction en fin de test : rien ne subsiste.
    """
    from BaseBillet.models import Event

    tenant, _domaine, utilisateur = lieu_avec_evenements
    with tenant_context(tenant):
        parent = (
            Event.objects.exclude(categorie=Event.ACTION)
            .filter(parent__isnull=True)
            .first()
        )
        assert parent is not None, "Aucun evenement racine sur ce lieu."
        for rang in range(2):
            Event.objects.create(
                name=f"Enfant {rang} (test)",
                datetime=parent.datetime,
                parent=parent,
                categorie=Event.ACTION,
            )
        yield tenant, utilisateur, parent


@pytest.mark.django_db
def test_un_evenement_AVEC_enfants_ne_coute_plus_de_requete_de_decision(
    evenement_avec_enfants,
):
    """
    Le chemin qui restait N+1. `children_pricesold_for_sections` refaisait son
    PROPRE `children.exists()`, apres celui qu'on venait d'eviter dans
    `render()` : la correction ne couvrait que les evenements sans enfant.
    / The path that stayed N+1: the property re-ran its own exists().
    """
    from Administration.admin_tenant import ChildActionsSummaryTable, EventAdmin
    from BaseBillet.models import Event

    tenant, utilisateur, parent = evenement_avec_enfants
    requete = RequestFactory().get("/admin/BaseBillet/event/")
    requete.user = utilisateur

    with tenant_context(tenant):
        from Administration.admin.site import staff_admin_site

        annote = (
            EventAdmin(Event, staff_admin_site)
            .get_queryset(requete)
            .get(pk=parent.pk)
        )
        assert annote.section_children_count == 2, "L'annotation ne voit pas les enfants."

        with CaptureQueriesContext(connection) as requetes:
            html = ChildActionsSummaryTable(requete, annote).render()

    # Une seule requete : celle qui recupere les billets a afficher. La requete
    # de DECISION (« y a-t-il des enfants ? ») doit avoir disparu, des deux
    # endroits ou elle se trouvait.
    # / One query only: fetching the tickets. Both decision queries must be gone.
    assert len(requetes) <= 1, (
        f"{len(requetes)} requetes pour UN evenement avec enfants : "
        "une requete de decision est revenue.\n"
        + "\n".join(q["sql"][:120] for q in requetes)
    )
    assert html, "La section devrait rendre quelque chose pour un event avec enfants."


@pytest.mark.django_db
def test_la_section_des_actions_ne_requete_plus_par_ligne(lieu_avec_evenements):
    """
    `ChildActionsSummaryTable.render()` faisait un `children.exists()` par
    ligne, uniquement pour decider de se masquer. Il lit desormais
    l'annotation posee par `EventAdmin.get_queryset()`.
    / The section used one exists() per row just to decide whether to hide.
    """
    from Administration.admin_tenant import ChildActionsSummaryTable, EventAdmin
    from BaseBillet.models import Event

    tenant, _domaine, utilisateur = lieu_avec_evenements
    requete = RequestFactory().get("/admin/BaseBillet/event/")
    requete.user = utilisateur

    with tenant_context(tenant):
        from Administration.admin.site import staff_admin_site

        admin = EventAdmin(Event, staff_admin_site)
        evenements = list(admin.get_queryset(requete)[:5])
        assert evenements, "Aucun evenement : le test ne prouverait rien."

        with CaptureQueriesContext(connection) as requetes:
            for evenement in evenements:
                ChildActionsSummaryTable(requete, evenement).render()

    # Ce test ne couvre que le chemin SANS enfant : la section se masque, et
    # cela doit coûter ZERO requete. Le chemin avec enfants est couvert par
    # test_un_evenement_AVEC_enfants_ne_coute_plus_de_requete_de_decision —
    # separer les deux est ce qui manquait, l'assertion melangee etant
    # satisfaite par une borne a zero des que la fixture n'avait pas d'enfant.
    # / This only covers the childless path; the other one has its own test.
    sans_enfant = [
        e for e in evenements if getattr(e, "section_children_count", 0) == 0
    ]
    assert sans_enfant, (
        "Aucun evenement sans enfant : ce test ne prouverait rien. "
        "Il lui faut precisement le cas qui doit se masquer sans requete."
    )
    avec_enfant = len(evenements) - len(sans_enfant)
    assert len(requetes) <= avec_enfant, (
        f"{len(requetes)} requetes pour {len(evenements)} evenements dont "
        f"{len(sans_enfant)} sans enfant : la requete de decision est revenue."
    )


@pytest.mark.django_db
def test_l_annotation_des_enfants_est_bien_posee(lieu_avec_evenements):
    """Sans l'annotation, la section retombe sur son ancien comportement."""
    from Administration.admin_tenant import EventAdmin
    from BaseBillet.models import Event

    tenant, _domaine, utilisateur = lieu_avec_evenements
    requete = RequestFactory().get("/admin/BaseBillet/event/")
    requete.user = utilisateur

    with tenant_context(tenant):
        from Administration.admin.site import staff_admin_site

        evenement = EventAdmin(Event, staff_admin_site).get_queryset(requete).first()
        assert hasattr(evenement, "section_children_count")
        # L'annotation doit dire la verite, pas seulement exister.
        # / The annotation must be correct, not merely present.
        assert evenement.section_children_count == evenement.children.count()


# --------------------------------------------------------------------------- #
# PageAdmin — SousPagesSection                                                 #
# --------------------------------------------------------------------------- #


@pytest.fixture
def arborescence_de_pages(lieu_avec_evenements):
    """
    Une page parente et TROIS sous-pages, chacune avec des blocs.

    On CREE les donnees au lieu de les chercher : sur le lieu de dev aucune
    page n'a de sous-page, et le test se sautait — or un test qui se saute ne
    protege rien. C'est exactement la N+1 imbriquee qu'on veut exposer.
    / Data is created, not looked up: the dev venue has no sub-pages, so the
      test skipped itself and protected nothing.

    `django_db` enveloppe le test dans une transaction annulee a la fin :
    rien ne subsiste dans la base de dev.
    / The transaction is rolled back; nothing persists.
    """
    from pages.models import Bloc, Page

    tenant, _domaine, _utilisateur = lieu_avec_evenements
    with tenant_context(tenant):
        parente = Page.objects.create(titre="Parente (test)", slug="parente-test")
        for rang in range(3):
            enfant = Page.objects.create(
                titre=f"Enfant {rang} (test)",
                slug=f"enfant-{rang}-test",
                parent=parente,
            )
            for numero in range(rang + 1):
                Bloc.objects.create(page=enfant, titre=f"Bloc {numero}")
        yield tenant, parente


@pytest.mark.django_db
def test_les_sous_pages_comptent_leurs_blocs_sans_n_plus_un(arborescence_de_pages):
    """
    `nb_blocs` faisait un `blocs.count()` PAR SOUS-PAGE : une N+1 imbriquee,
    invisible sur un lieu qui n'a que deux pages a plat.
    / A nested N+1, invisible on the current data.
    """
    tenant, parente = arborescence_de_pages
    with tenant_context(tenant):
        with CaptureQueriesContext(connection) as requetes:
            sous_pages = list(parente.enfants_pour_section)
            for sous_page in sous_pages:
                sous_page.nb_blocs_annote  # noqa: B018 — lecture de l'annotation

    assert len(sous_pages) == 3
    assert len(requetes) == 1, (
        f"{len(requetes)} requetes pour {len(sous_pages)} sous-pages : "
        "le comptage des blocs doit tenir en UNE requete."
    )


@pytest.mark.django_db
def test_le_nombre_de_blocs_annote_est_juste(arborescence_de_pages):
    """
    Optimiser en mentant sur le chiffre serait pire que la N+1 qu'on corrige.
    / Optimising while lying about the number would be worse than the N+1.
    """
    tenant, parente = arborescence_de_pages
    with tenant_context(tenant):
        for sous_page in parente.enfants_pour_section:
            assert sous_page.nb_blocs_annote == sous_page.blocs.count()


@pytest.mark.django_db
def test_la_section_rend_le_bon_nombre_de_blocs(arborescence_de_pages):
    """
    Le test qui relie l'optimisation a ce que voit l'utilisateur : la methode
    `nb_blocs` de la section doit rendre le meme chiffre qu'avant.
    / Ties the optimisation back to what the user actually sees.
    """
    from pages.admin import SousPagesSection

    tenant, parente = arborescence_de_pages
    with tenant_context(tenant):
        section = SousPagesSection(RequestFactory().get("/admin/pages/page/"), parente)
        rendus = {
            sous_page.titre: section.nb_blocs(sous_page)
            for sous_page in parente.enfants_pour_section
        }
        attendus = {
            sous_page.titre: sous_page.blocs.count()
            for sous_page in parente.enfants.all()
        }
    assert rendus == attendus
    assert sorted(rendus.values()) == [1, 2, 3]
