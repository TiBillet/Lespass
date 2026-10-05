"""
Tests de l'archivage des tarifs : « supprimer » un tarif l'archive.
/ Price archiving tests: "deleting" a price archives it.

LOCALISATION : tests/pytest/test_price_archivage.py

Code testé / Tested code :
- BaseBillet/models.py : Price.delete(), Price.hard_delete(), Price.save()
- BaseBillet/services_panier.py, BaseBillet/validators.py
- Administration/admin/prices.py, Administration/admin/products.py

Un tarif déjà vendu ne peut pas être effacé : les ventes passées (PriceSold) pointent
vers lui. On l'archive : il reste en base, mais il n'est plus jamais affiché ni vendu.

Chaque test est marqué `django_db` : pytest-django l'exécute dans une transaction annulée
à la fin. Les objets créés par les fabriques ne restent pas en base de dev.
/ Every test runs in a rolled-back transaction: factory objects do not stay in the dev DB.

Lancer / Run : make test ARGS="tests/pytest/test_price_archivage.py"
"""

from types import SimpleNamespace

import pytest
from django_tenants.utils import tenant_context

from fabriques_panier import (
    catalogue_stripe_simule,
    creer_evenement_avec_tarif,
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
    """
    Le lieu `lespass`, avec Stripe (catalogue) et Celery simulés pendant tout le test.
    / The `lespass` venue, with the Stripe catalogue and Celery faked for the whole test.
    """
    with tenant_context(tenant):
        with catalogue_stripe_simule() as catalogue_stripe:
            with taches_celery_enregistrees() as taches_demandees:
                yield SimpleNamespace(
                    tenant=tenant,
                    catalogue_stripe=catalogue_stripe,
                    taches_demandees=taches_demandees,
                )


def requete_d_un_administrateur():
    """
    Requête minimale pour appeler une méthode de l'admin. Les droits ne sont pas testés ici.
    / Minimal request to call an admin method. Permissions are not tested here.
    """
    return requete_avec_session(creer_utilisateur())


# --------------------------------------------------------------------------
# Modèle : Price.delete(), Price.hard_delete(), Price.save()
# / Model
# --------------------------------------------------------------------------


def test_supprimer_un_tarif_le_garde_en_base(lieu):
    """delete() n'efface pas la ligne.
    / delete() does not remove the row."""
    from BaseBillet.models import Price

    concert = creer_evenement_avec_tarif(prix="10.00")

    concert.tarif.delete()

    assert Price.objects.filter(pk=concert.tarif.pk).exists()


def test_supprimer_un_tarif_le_marque_archive(lieu):
    """delete() passe archived à True.
    / delete() sets archived to True."""
    concert = creer_evenement_avec_tarif(prix="10.00")

    concert.tarif.delete()

    concert.tarif.refresh_from_db()
    assert concert.tarif.archived is True


def test_supprimer_un_tarif_le_depublie(lieu):
    """delete() passe publish à False : le tarif n'est plus en vente.
    / delete() sets publish to False."""
    concert = creer_evenement_avec_tarif(prix="10.00")

    concert.tarif.delete()

    concert.tarif.refresh_from_db()
    assert concert.tarif.publish is False


def test_enregistrer_un_tarif_archive_le_depublie_toujours(lieu):
    """save() avec archived=True force publish=False, même si on demande publish=True.
    / save() with archived=True forces publish=False."""
    concert = creer_evenement_avec_tarif(prix="10.00")

    concert.tarif.archived = True
    concert.tarif.publish = True
    concert.tarif.save()

    concert.tarif.refresh_from_db()
    assert concert.tarif.publish is False


def test_supprimer_un_tarif_deja_vendu_garde_la_vente_passee(lieu):
    """Le PriceSold d'une vente passée pointe toujours vers le tarif archivé.
    / The PriceSold of a past sale still points to the archived price."""
    from ApiBillet.serializers import get_or_create_price_sold
    from BaseBillet.models import PriceSold

    concert = creer_evenement_avec_tarif(prix="10.00")
    vente_passee = get_or_create_price_sold(concert.tarif, event=concert.evenement)

    concert.tarif.delete()

    vente_relue = PriceSold.objects.get(pk=vente_passee.pk)
    assert vente_relue.price.pk == concert.tarif.pk
    assert vente_relue.price.name == concert.tarif.name


def test_hard_delete_efface_vraiment_un_tarif_jamais_vendu(lieu):
    """hard_delete() efface la ligne (tests et nettoyages).
    / hard_delete() really removes the row."""
    from BaseBillet.models import Price

    concert = creer_evenement_avec_tarif(prix="10.00")
    identifiant_du_tarif = concert.tarif.pk

    concert.tarif.hard_delete()

    assert not Price.objects.filter(pk=identifiant_du_tarif).exists()


def test_un_produit_gratuit_recree_son_tarif_si_l_ancien_est_archive(lieu):
    """FREERES : le tarif à 0 € archivé ne bloque pas la création d'un nouveau tarif gratuit.
    / FREERES: an archived 0 € price does not block the creation of a new free price."""
    from BaseBillet.models import Product

    reservation_gratuite = creer_evenement_avec_tarif(prix="0.00", categorie=Product.FREERES)
    reservation_gratuite.tarif.delete()

    reservation_gratuite.produit.save()

    tarifs_gratuits_en_vente = reservation_gratuite.produit.prices.filter(prix=0, archived=False)
    assert tarifs_gratuits_en_vente.count() == 1


def test_tarifs_non_archives_ne_renvoie_pas_le_tarif_archive(lieu):
    """Product.tarifs_non_archives() cache le tarif archivé.
    / Product.tarifs_non_archives() hides the archived price."""
    concert = creer_evenement_avec_tarif(prix="10.00")

    concert.tarif.delete()

    assert concert.tarif not in concert.produit.tarifs_non_archives()


# --------------------------------------------------------------------------
# Vente : un tarif archivé est refusé
# / Sale: an archived price is refused
# --------------------------------------------------------------------------


def test_add_ticket_refuse_un_tarif_archive(lieu):
    """Panier : un tarif archivé est refusé.
    / Cart: an archived price is refused."""
    from BaseBillet.services_panier import InvalidItemError, PanierSession

    concert = creer_evenement_avec_tarif(prix="10.00")
    concert.tarif.delete()
    panier = PanierSession(requete_avec_session(creer_utilisateur()))

    with pytest.raises(InvalidItemError):
        panier.add_ticket(concert.evenement.uuid, concert.tarif.uuid, qty=1)


def test_api_v2_ne_propose_pas_le_tarif_archive(lieu):
    """API v2 : les offres d'un produit ne contiennent pas le tarif archivé.
    / API v2: a product's offers do not contain the archived price."""
    from api_v2.serializers import ProductSchemaSerializer

    concert = creer_evenement_avec_tarif(prix="10.00")
    concert.tarif.delete()

    produit_serialise = ProductSchemaSerializer(concert.produit).data

    assert str(concert.tarif.uuid) not in str(produit_serialise)


# --------------------------------------------------------------------------
# Admin : le bouton « Supprimer » archive
# / Admin: the "Delete" button archives
# --------------------------------------------------------------------------


def test_admin_la_page_de_confirmation_ne_bloque_pas_un_tarif_deja_vendu(lieu):
    """PriceAdmin.get_deleted_objects ne renvoie aucun objet protégé.
    / PriceAdmin.get_deleted_objects returns no protected object."""
    from Administration.admin.prices import PriceAdmin
    from Administration.admin.site import staff_admin_site
    from ApiBillet.serializers import get_or_create_price_sold
    from BaseBillet.models import Price

    concert = creer_evenement_avec_tarif(prix="10.00")
    get_or_create_price_sold(concert.tarif, event=concert.evenement)
    admin_des_tarifs = PriceAdmin(Price, staff_admin_site)

    resultat = admin_des_tarifs.get_deleted_objects(
        [concert.tarif], requete_d_un_administrateur()
    )
    objets_proteges = resultat[3]

    assert objets_proteges == []


def test_admin_la_suppression_groupee_archive_les_tarifs(lieu):
    """PriceAdmin.delete_queryset archive au lieu d'effacer.
    / PriceAdmin.delete_queryset archives instead of deleting."""
    from Administration.admin.prices import PriceAdmin
    from Administration.admin.site import staff_admin_site
    from BaseBillet.models import Price

    concert = creer_evenement_avec_tarif(prix="10.00")
    admin_des_tarifs = PriceAdmin(Price, staff_admin_site)

    admin_des_tarifs.delete_queryset(
        requete_d_un_administrateur(), Price.objects.filter(pk=concert.tarif.pk)
    )

    concert.tarif.refresh_from_db()
    assert concert.tarif.archived is True


def test_admin_la_liste_des_tarifs_cache_le_tarif_archive(lieu):
    """PriceAdmin.get_queryset ne renvoie pas le tarif archivé.
    / PriceAdmin.get_queryset does not return the archived price."""
    from Administration.admin.prices import PriceAdmin
    from Administration.admin.site import staff_admin_site
    from BaseBillet.models import Price

    concert = creer_evenement_avec_tarif(prix="10.00")
    concert.tarif.delete()
    admin_des_tarifs = PriceAdmin(Price, staff_admin_site)

    tarifs_affiches = admin_des_tarifs.get_queryset(requete_d_un_administrateur())

    assert not tarifs_affiches.filter(pk=concert.tarif.pk).exists()


def test_admin_la_fiche_produit_cache_le_tarif_archive(lieu):
    """L'inline des tarifs d'un produit ne renvoie pas le tarif archivé.
    / The product's price inline does not return the archived price."""
    from Administration.admin.products import BasePriceInline
    from Administration.admin.site import staff_admin_site
    from BaseBillet.models import Product

    concert = creer_evenement_avec_tarif(prix="10.00")
    concert.tarif.delete()
    inline_des_tarifs = BasePriceInline(Product, staff_admin_site)

    tarifs_affiches = inline_des_tarifs.get_queryset(requete_d_un_administrateur())

    assert not tarifs_affiches.filter(pk=concert.tarif.pk).exists()


def test_admin_la_case_supprimer_est_acceptee_sur_un_tarif_deja_vendu(lieu):
    """Inline : le contrôle « objets protégés » de Django est neutralisé.
    / Inline: Django's "protected objects" check is neutralised."""
    from django.core.exceptions import ValidationError

    from Administration.admin.products import BasePriceInline
    from Administration.admin.site import staff_admin_site
    from ApiBillet.serializers import get_or_create_price_sold
    from BaseBillet.models import Product

    concert = creer_evenement_avec_tarif(prix="10.00")
    get_or_create_price_sold(concert.tarif, event=concert.evenement)
    inline_des_tarifs = BasePriceInline(Product, staff_admin_site)
    classe_du_formset = inline_des_tarifs.get_formset(
        requete_d_un_administrateur(), concert.produit
    )

    formulaire_du_tarif = classe_du_formset.form(instance=concert.tarif)
    formulaire_du_tarif.cleaned_data = {"DELETE": True}

    try:
        formulaire_du_tarif.hand_clean_DELETE()
    except ValidationError:
        pytest.fail("La case « Supprimer » est refusée sur un tarif déjà vendu.")
