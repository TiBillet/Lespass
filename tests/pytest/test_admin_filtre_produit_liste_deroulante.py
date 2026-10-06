"""
Dans l'admin, le filtre « Produit » est une liste déroulante avec recherche.
/ In the admin, the "Product" filter is a searchable dropdown.

LOCALISATION : tests/pytest/test_admin_filtre_produit_liste_deroulante.py

Code testé / Tested code : Administration/admin_tenant.py
- MembershipPublishedFilter (liste des adhésions)
- EventFutureFilter, EventPastFilter, EventArchivedFilter (réservations et billets)

Avant : tous les produits étaient affichés les uns sous les autres dans le panneau de
filtres. Maintenant : un seul champ <select> (Unfold DropdownFilter).
/ Before: every product was listed as a link. Now: a single <select> field.

Lancer / Run : make test ARGS="tests/pytest/test_admin_filtre_produit_liste_deroulante.py"
"""

import pytest
from django.urls import reverse
from django_tenants.utils import tenant_context

pytestmark = pytest.mark.django_db


def test_la_liste_des_adhesions_affiche_le_filtre_produit_en_liste_deroulante(
    admin_client, tenant
):
    """La page contient un <select name="price">, pas une liste de liens.
    / The page holds a <select name="price">, not a list of links."""
    with tenant_context(tenant):
        reponse = admin_client.get(reverse("staff_admin:BaseBillet_membership_changelist"))

    assert reponse.status_code == 200
    contenu = reponse.content.decode()
    assert '<select name="price"' in contenu


def test_la_liste_des_adhesions_se_filtre_par_produit(admin_client, tenant):
    """Choisir un produit dans la liste déroulante filtre la page sans erreur.
    / Picking a product in the dropdown filters the page without error."""
    from BaseBillet.models import MembershipProduct

    with tenant_context(tenant):
        produit = MembershipProduct.objects.filter(archive=False).first()
        url = reverse("staff_admin:BaseBillet_membership_changelist")
        reponse = admin_client.get(url, {"price": str(produit.pk)})

    assert reponse.status_code == 200
    contenu = reponse.content.decode()
    assert f'<option value="{produit.pk}" selected>' in contenu


@pytest.fixture
def evenements_de_chaque_sorte(tenant):
    """
    Un événement à venir, un passé et un archivé : un filtre sans aucun choix n'est pas
    affiché par l'admin, il faut donc au moins un événement de chaque sorte.
    / One upcoming, one past and one archived event: a filter with no choice is hidden.
    """
    from fabriques_panier import (
        catalogue_stripe_simule,
        creer_evenement_avec_tarif,
        taches_celery_enregistrees,
    )

    with tenant_context(tenant):
        with catalogue_stripe_simule():
            with taches_celery_enregistrees():
                creer_evenement_avec_tarif(jours_avant_l_evenement=7)
                creer_evenement_avec_tarif(jours_avant_l_evenement=-7)
                evenement_archive = creer_evenement_avec_tarif().evenement
                evenement_archive.archived = True
                evenement_archive.save()
                yield


@pytest.mark.parametrize("nom_de_la_liste", ["reservation", "ticket"])
@pytest.mark.parametrize(
    "parametre_du_filtre", ["event_future", "event_past", "event_archived"]
)
def test_les_filtres_par_evenement_sont_des_listes_deroulantes(
    admin_client, tenant, evenements_de_chaque_sorte, nom_de_la_liste, parametre_du_filtre
):
    """Réservations et billets : chaque filtre par événement est un <select>.
    / Reservations and tickets: each event filter is a <select>."""
    url = reverse(f"staff_admin:BaseBillet_{nom_de_la_liste}_changelist")
    reponse = admin_client.get(url)

    assert reponse.status_code == 200
    contenu = reponse.content.decode()
    assert f'<select name="{parametre_du_filtre}"' in contenu


def test_la_liste_des_reservations_se_filtre_par_evenement(admin_client, tenant):
    """Choisir un événement dans la liste déroulante filtre la page sans erreur.
    / Picking an event in the dropdown filters the page without error."""
    from BaseBillet.models import Event

    with tenant_context(tenant):
        evenement = Event.objects.filter(archived=False).order_by("-datetime").first()
        url = reverse("staff_admin:BaseBillet_reservation_changelist")
        reponse_futur = admin_client.get(url, {"event_future": str(evenement.pk)})
        reponse_passe = admin_client.get(url, {"event_past": str(evenement.pk)})

    assert reponse_futur.status_code == 200
    assert reponse_passe.status_code == 200


# --------------------------------------------------------------------------
# Filtres sur une relation passés en liste déroulante (RelatedDropdownFilter)
# / Relation filters switched to a dropdown
# --------------------------------------------------------------------------

LISTES_AVEC_UN_FILTRE_DE_RELATION_EN_LISTE_DEROULANTE = [
    "BaseBillet_promotionalcode",
    "BaseBillet_posproduct",
    "laboutik_historiquefonddecaisse",
    "crowds_initiative",
    "fedow_core_token",
    "fedow_core_transaction",
    "controlvanne_rfidsession",
    "controlvanne_historiquetireuse",
    "controlvanne_historiquecarte",
    "controlvanne_historiquemaintenance",
    "controlvanne_sessioncalibration",
]


@pytest.mark.parametrize(
    "nom_de_la_liste", LISTES_AVEC_UN_FILTRE_DE_RELATION_EN_LISTE_DEROULANTE
)
def test_les_listes_avec_un_filtre_de_relation_s_affichent(
    admin_client, tenant, nom_de_la_liste
):
    """La liste s'affiche sans erreur avec son filtre en liste déroulante.
    / The changelist renders without error with its dropdown filter.

    On ne cherche pas le <select> : l'admin cache un filtre de relation quand il
    a moins de deux choix (ex : une seule tireuse en base).
    / No <select> assertion: a relation filter with fewer than two choices is hidden.
    """
    with tenant_context(tenant):
        reponse = admin_client.get(reverse(f"staff_admin:{nom_de_la_liste}_changelist"))

    assert reponse.status_code == 200


def test_la_liste_des_codes_promo_affiche_le_filtre_produit_en_liste_deroulante(
    admin_client, tenant
):
    """Codes promo : le filtre « produit » est un <select>.
    / Promo codes: the "product" filter is a <select>."""
    with tenant_context(tenant):
        reponse = admin_client.get(
            reverse("staff_admin:BaseBillet_promotionalcode_changelist")
        )

    contenu = reponse.content.decode()
    assert '<select name="product__uuid__exact"' in contenu


# --------------------------------------------------------------------------
# La liste à plat de tous les blocs n'est jamais affichée
# / The flat list of all blocks is never shown
# --------------------------------------------------------------------------


def test_la_liste_des_blocs_renvoie_vers_la_liste_des_pages(admin_client, tenant):
    """`/admin/pages/bloc/` redirige vers la liste des pages.
    / `/admin/pages/bloc/` redirects to the page list."""
    with tenant_context(tenant):
        reponse = admin_client.get(reverse("staff_admin:pages_bloc_changelist"))
        url_de_la_liste_des_pages = reverse("staff_admin:pages_page_changelist")

    assert reponse.status_code == 302
    assert reponse.url == url_de_la_liste_des_pages


# --------------------------------------------------------------------------
# Filtres à choix fixes passés en liste déroulante (ChoicesDropdownFilter)
# / Fixed-choice filters switched to a dropdown
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "nom_de_la_liste, nom_du_champ",
    [
        ("BaseBillet_posproduct", "methode_caisse__exact"),
        ("booking_booking", "status__exact"),
        ("fedow_core_transaction", "action__exact"),
    ],
)
def test_les_filtres_a_choix_fixes_sont_des_listes_deroulantes(
    admin_client, tenant, nom_de_la_liste, nom_du_champ
):
    """Méthode de caisse, statut d'une réservation de ressource, action d'une
    transaction : chaque filtre est un <select>.
    / Each fixed-choice filter is a <select>."""
    with tenant_context(tenant):
        reponse = admin_client.get(reverse(f"staff_admin:{nom_de_la_liste}_changelist"))

    assert reponse.status_code == 200
    contenu = reponse.content.decode()
    assert f'<select name="{nom_du_champ}"' in contenu
