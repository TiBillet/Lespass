"""
Tests du context processor `panier_context` : le panier exposé à tous les gabarits.
/ Tests of the `panier_context` context processor: the cart exposed to every template.

LOCALISATION : tests/pytest/test_panier_context_processor.py

Code testé / Tested code : BaseBillet/context_processors.py

`{{ panier }}` alimente le badge de la barre de navigation et la page `/panier/` :
nombre d'items, total, détail enrichi (événement, tarif, ressource), adhésions du panier.
/ `{{ panier }}` feeds the navbar badge and the `/panier/` page.

Chaque test est marqué `django_db` : transaction annulée à la fin, rien ne reste en base.
Lancer / Run : make test ARGS="tests/pytest/test_panier_context_processor.py"
"""

from decimal import Decimal
from types import SimpleNamespace

import pytest
from django_tenants.utils import tenant_context

from fabriques_panier import (
    catalogue_stripe_simule,
    creer_adhesion,
    creer_evenement_avec_tarif,
    creer_ressource_avec_tarif,
    creer_utilisateur,
    requete_avec_session,
    taches_celery_enregistrees,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _langue_par_defaut_apres_chaque_test():
    """Les signaux activent la langue du lieu sans la remettre (tests/PIEGES.md, 10.5).
    / Signals activate the venue language without resetting it."""
    from django.utils import translation

    yield
    translation.deactivate()


@pytest.fixture
def lieu(tenant):
    """Le lieu `lespass`, avec Stripe (catalogue) et Celery simulés.
    / The `lespass` venue, with the Stripe catalogue and Celery faked."""
    with tenant_context(tenant):
        with catalogue_stripe_simule(), taches_celery_enregistrees():
            yield SimpleNamespace(tenant=tenant)


def test_un_panier_vide_expose_des_valeurs_nulles(lieu):
    """Panier vide : zéro item, total nul, aucune adhésion.
    / Empty cart: zero item, zero total, no membership."""
    from BaseBillet.context_processors import panier_context

    contexte = panier_context(requete_avec_session(creer_utilisateur()))

    assert contexte["panier"]["count"] == 0
    assert contexte["panier"]["is_empty"] is True
    assert contexte["panier"]["items_with_details"] == []
    assert contexte["panier"]["total_ttc"] == Decimal("0.00")
    assert contexte["panier"]["adhesions_product_ids"] == []


def test_un_billet_est_detaille_avec_son_evenement_et_son_rang(lieu):
    """2 billets à 10 € : compte 2, total 20 €, détail avec l'événement, le tarif et le rang.
    / 2 tickets at 10 €: count 2, total 20 €, detail with event, price and position."""
    from BaseBillet.context_processors import panier_context
    from BaseBillet.services_panier import PanierSession

    requete = requete_avec_session(creer_utilisateur())
    concert = creer_evenement_avec_tarif(prix="10.00")
    PanierSession(requete).add_ticket(concert.evenement.uuid, concert.tarif.uuid, qty=2)

    contexte = panier_context(requete)

    assert contexte["panier"]["count"] == 2
    assert contexte["panier"]["total_ttc"] == Decimal("20.00")
    detail = contexte["panier"]["items_with_details"][0]
    assert detail["type"] == "ticket"
    assert detail["event"] == concert.evenement
    assert detail["price"] == concert.tarif
    assert detail["qty"] == 2
    assert detail["index"] == 0


def test_une_adhesion_du_panier_debloque_son_produit(lieu):
    """Adhésion au panier : son produit figure dans `adhesions_product_ids` (tarifs adhérents).
    / Membership in the cart: its product is listed in `adhesions_product_ids`."""
    from BaseBillet.context_processors import panier_context
    from BaseBillet.services_panier import PanierSession

    requete = requete_avec_session(creer_utilisateur())
    adhesion = creer_adhesion(prix="15.00")
    PanierSession(requete).add_membership(adhesion.tarif.uuid)

    contexte = panier_context(requete)

    assert contexte["panier"]["count"] == 1
    assert adhesion.produit.uuid in contexte["panier"]["adhesions_product_ids"]
    assert contexte["panier"]["total_ttc"] == Decimal("15.00")


def test_une_ressource_est_detaillee_avec_son_creneau_et_son_estimation(lieu):
    """2 h de ressource à 12 € : détail avec la ressource, le début du créneau, 24 €.
    / 2 hours of resource at 12 €: detail with the resource, the slot start, 24 €."""
    from BaseBillet.context_processors import panier_context
    from BaseBillet.services_panier import PanierSession

    requete = requete_avec_session(creer_utilisateur())
    location = creer_ressource_avec_tarif(prix="12.00")
    PanierSession(requete).add_resource(
        resource_uuid=location.ressource.pk,
        price_uuid=location.tarif.uuid,
        start_datetime=location.debut_du_creneau,
        slot_duration_minutes=60,
        slot_count=2,
    )

    contexte = panier_context(requete)

    detail = contexte["panier"]["items_with_details"][0]
    assert detail["type"] == "resource"
    assert detail["resource"] == location.ressource
    assert detail["start_datetime"] == location.debut_du_creneau
    assert contexte["panier"]["total_ttc"] == Decimal("24.00")


def test_le_detail_du_panier_n_est_calcule_que_s_il_est_lu(lieu):
    """Le context processor tourne à CHAQUE rendu de page. Tant qu'un gabarit ne lit pas le
    détail des articles, il ne doit faire aucune requête : seule la page du panier le lit, et
    le badge de la barre de navigation se contente du nombre d'articles.
    / The context processor runs on EVERY render: it must not query the database until a
    template reads the item details, which only the cart page does."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from BaseBillet.context_processors import panier_context
    from BaseBillet.services_panier import PanierSession

    requete = requete_avec_session(creer_utilisateur())
    concert = creer_evenement_avec_tarif(prix="10.00")
    PanierSession(requete).add_ticket(concert.evenement.uuid, concert.tarif.uuid, qty=2)

    with CaptureQueriesContext(connection) as requetes_de_la_page:
        contexte = panier_context(requete)
        # Ce que lit le badge de la barre de navigation, sur toutes les pages.
        # / What the navbar badge reads, on every page.
        assert contexte["panier"]["count"] == 2
        assert contexte["panier"]["is_empty"] is False

    assert len(requetes_de_la_page.captured_queries) == 0

    # La page du panier, elle, lit le détail : il est calculé à ce moment-là.
    # / The cart page reads the details: they are computed then.
    with CaptureQueriesContext(connection) as requetes_du_detail:
        assert contexte["panier"]["items_with_details"][0]["event"] == concert.evenement
        assert contexte["panier"]["total_ttc"] == Decimal("20.00")

    assert len(requetes_du_detail.captured_queries) > 0


def test_une_requete_sans_session_rend_un_panier_vide_sans_planter(lieu):
    """Requête sans session (ex. admin public) : panier vide, le rendu ne casse pas.
    / Request without a session (e.g. public admin): empty cart, rendering does not break."""
    from BaseBillet.context_processors import panier_context

    class RequeteSansSession:
        pass

    contexte = panier_context(RequeteSansSession())

    assert contexte["panier"]["count"] == 0
    assert contexte["panier"]["is_empty"] is True
