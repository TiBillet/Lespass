"""
Tests de non-regression : la SEMANTIQUE des tags d'un lieu federe.
/ Regression tests: the SEMANTICS of a federated place's tags.

LOCALISATION : tests/pytest/test_federation_tags_semantique.py
Voir SESSIONS/NEWSLETTER/CHANTIER-01-semantique-tags-federes.md

CE QUE CES TESTS PROTEGENT
--------------------------
`FederatedPlace` porte deux listes de tags. Les libelles de l'admin les decrivent
ainsi, et c'est la seule chose que le gestionnaire voit :

    tag_filter  -> n'afficher QUE les events portant un de ces tags
    tag_exclude -> NE PAS afficher les events portant un de ces tags

Le moteur de l'agenda (`EventMVT.federated_events_filter`) doit appliquer les tags
DANS CE SENS. Il a longtemps fait l'inverse, ce qui produisait une panne muette :
quand les deux listes etaient remplies, le lieu federe disparaissait entierement de
l'agenda (on excluait ce qu'on voulait voir, puis on ne gardait que ce qu'on voulait
cacher -> intersection vide). Aucune erreur, aucun avertissement : le lieu s'effacait.

Ces tests echouent si quelqu'un re-inverse le sens des deux filtres.

DEPENDANCE AU SEED
------------------
Ces tests sont en LECTURE SEULE et s'appuient sur les donnees de `demo_data_v2` :
le tenant `lespass` federe `chantefrein` et `la-maison-des-communs`. Ils se
re-declarent `skip` si le seed n'est pas en place, plutot que d'echouer a tort.
On ne cree rien en base : la suite tourne sur la base de DEV, une ecriture
cross-schema qui ne serait pas annulee corromprait les donnees de demonstration.
/ Read-only tests, based on the demo_data_v2 seed. They skip (not fail) if the seed
is absent. Nothing is written: the suite runs on the DEV database.
"""

import pytest
from django.test.client import Client as DjangoClient
from django_tenants.utils import tenant_context

from BaseBillet.models import Event, FederatedPlace
from Customers.models import Client


# ----------------------------------------------------------------------------
# Fixtures : base de dev + acces multi-tenant (meme pattern que
# test_federation_view_integration.py)
# / Dev DB + multi-tenant access (same pattern as test_federation_view_integration.py)
# ----------------------------------------------------------------------------

@pytest.fixture(scope="session")
def django_db_setup():
    # Reutilise la base de dev (pas de creation de test DB).
    # / Reuse dev DB (no test DB creation).
    pass


@pytest.fixture(autouse=True, scope="session")
def _enable_db_access(django_db_blocker):
    django_db_blocker.unblock()


@pytest.fixture
def tenant_lespass():
    tenant = Client.objects.filter(schema_name="lespass").first()
    if not tenant:
        pytest.skip("Seed demo_data_v2 absent : pas de tenant 'lespass'.")
    return tenant


@pytest.fixture
def http_client(tenant_lespass):
    domain = tenant_lespass.domains.first()
    return DjangoClient(HTTP_HOST=domain.domain)


def _lieu_federe(tenant_lespass, schema_du_voisin):
    """
    Recupere le FederatedPlace de `lespass` vers un voisin donne.
    / Get lespass' FederatedPlace pointing to a given neighbour.
    """
    with tenant_context(tenant_lespass):
        lieu = (
            FederatedPlace.objects
            .select_related("tenant")
            .prefetch_related("tag_filter", "tag_exclude")
            .filter(tenant__schema_name=schema_du_voisin)
            .first()
        )
    if not lieu:
        pytest.skip(f"Seed absent : lespass ne federe pas '{schema_du_voisin}'.")
    return lieu


def _noms_des_events_du_voisin_dans_lagenda(http_client, voisin):
    """
    Charge l'agenda de `lespass` et renvoie les noms des events QUI APPARTIENNENT
    au voisin. On croise avec les events reellement presents chez le voisin : la page
    melange les events de tous les lieux du reseau, et on ne veut juger que celui-ci.
    / Load lespass' agenda and return the names of the events BELONGING to `voisin`.
    """
    reponse = http_client.get("/event/")
    assert reponse.status_code == 200
    page = reponse.content.decode()

    with tenant_context(voisin):
        events_du_voisin = list(
            Event.objects.filter(published=True).prefetch_related("tag")
        )

    noms_affiches = set()
    for event in events_du_voisin:
        if event.name in page:
            noms_affiches.add(event.name)
    return noms_affiches, events_du_voisin


# ----------------------------------------------------------------------------
# tag_exclude : les events portant ces tags NE DOIVENT PAS apparaitre
# ----------------------------------------------------------------------------

@pytest.mark.django_db
def test_tag_exclude_retire_bien_les_events_tagues(http_client, tenant_lespass):
    """
    Un tag dans `tag_exclude` EXCLUT les events qui le portent.

    Le bug historique faisait l'inverse : `tag_exclude` n'affichait QUE ces events.
    Sur le seed, `lespass` exclut le tag 'reunion' de `chantefrein` : les reunions de
    Chantefrein etaient donc les SEULS events de Chantefrein visibles sur l'agenda.
    """
    lieu = _lieu_federe(tenant_lespass, "chantefrein")

    with tenant_context(tenant_lespass):
        slugs_exclus = {tag.slug for tag in lieu.tag_exclude.all()}
    if not slugs_exclus:
        pytest.skip("Seed absent : aucun tag_exclude sur lespass -> chantefrein.")

    noms_affiches, events_du_voisin = _noms_des_events_du_voisin_dans_lagenda(
        http_client, lieu.tenant
    )

    # Aucun event portant un tag exclu ne doit figurer sur l'agenda.
    # / No event carrying an excluded tag may appear on the agenda.
    with tenant_context(lieu.tenant):
        for event in events_du_voisin:
            slugs_de_levent = {tag.slug for tag in event.tag.all()}
            if slugs_de_levent & slugs_exclus:
                assert event.name not in noms_affiches, (
                    f"L'event '{event.name}' porte un tag exclu "
                    f"({slugs_de_levent & slugs_exclus}) et ne devrait PAS "
                    f"apparaitre sur l'agenda. Le sens de tag_exclude est inverse."
                )


# ----------------------------------------------------------------------------
# tag_filter : SEULS les events portant ces tags doivent apparaitre
# ----------------------------------------------------------------------------

@pytest.mark.django_db
def test_tag_filter_ne_garde_que_les_events_tagues(http_client, tenant_lespass):
    """
    Un tag dans `tag_filter` ne garde QUE les events qui le portent.

    Le bug historique faisait l'inverse : `tag_filter` excluait ces events. Combine a
    un `tag_exclude`, le voisin disparaissait completement de l'agenda.
    Sur le seed, `lespass` ne veut de `la-maison-des-communs` que le tag 'prix-libre'.
    """
    lieu = _lieu_federe(tenant_lespass, "la-maison-des-communs")

    with tenant_context(tenant_lespass):
        slugs_filtres = {tag.slug for tag in lieu.tag_filter.all()}
    if not slugs_filtres:
        pytest.skip("Seed absent : aucun tag_filter sur lespass -> la-maison-des-communs.")

    noms_affiches, events_du_voisin = _noms_des_events_du_voisin_dans_lagenda(
        http_client, lieu.tenant
    )

    # Tout event affiche de ce voisin DOIT porter un des tags filtres.
    # / Every displayed event from this neighbour MUST carry one of the filtered tags.
    with tenant_context(lieu.tenant):
        for event in events_du_voisin:
            if event.name not in noms_affiches:
                continue
            slugs_de_levent = {tag.slug for tag in event.tag.all()}
            assert slugs_de_levent & slugs_filtres, (
                f"L'event '{event.name}' (tags: {slugs_de_levent}) est affiche alors "
                f"qu'il ne porte aucun des tags de tag_filter ({slugs_filtres}). "
                f"Le sens de tag_filter est inverse."
            )


@pytest.mark.django_db
def test_le_voisin_filtre_par_tags_reste_visible(http_client, tenant_lespass):
    """
    La panne muette : quand `tag_filter` ET `tag_exclude` sont remplis, le voisin
    doit rester VISIBLE. Avec le moteur inverse, l'intersection etait vide et le lieu
    federe disparaissait entierement de l'agenda, sans aucun message.

    Ce test n'exige pas un nombre precis d'events : il exige qu'au moins un event
    eligible (portant un tag filtre, aucun tag exclu) soit bien affiche.
    """
    lieu = _lieu_federe(tenant_lespass, "la-maison-des-communs")

    with tenant_context(tenant_lespass):
        slugs_filtres = {tag.slug for tag in lieu.tag_filter.all()}
        slugs_exclus = {tag.slug for tag in lieu.tag_exclude.all()}
    if not (slugs_filtres and slugs_exclus):
        pytest.skip("Seed absent : les deux listes de tags ne sont pas remplies.")

    noms_affiches, events_du_voisin = _noms_des_events_du_voisin_dans_lagenda(
        http_client, lieu.tenant
    )

    # On calcule ce que le voisin DEVRAIT montrer, puis on verifie que l'agenda
    # en montre au moins un. / Compute what the neighbour SHOULD show.
    with tenant_context(lieu.tenant):
        eligibles = []
        for event in events_du_voisin:
            slugs_de_levent = {tag.slug for tag in event.tag.all()}
            porte_un_tag_filtre = bool(slugs_de_levent & slugs_filtres)
            porte_un_tag_exclu = bool(slugs_de_levent & slugs_exclus)
            if porte_un_tag_filtre and not porte_un_tag_exclu:
                eligibles.append(event.name)

    if not eligibles:
        pytest.skip("Seed : aucun event eligible chez ce voisin, rien a prouver.")

    assert noms_affiches, (
        f"Le lieu federe '{lieu.tenant.schema_name}' a disparu de l'agenda alors "
        f"qu'il a des events eligibles ({eligibles}). C'est la panne muette de "
        f"l'inversion des tags : tag_filter et tag_exclude se neutralisent."
    )
