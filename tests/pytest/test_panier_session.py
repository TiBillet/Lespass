"""
Tests du panier en session : `PanierSession` et ses fonctions de validation.
/ Session cart tests: `PanierSession` and its validation functions.

LOCALISATION : tests/pytest/test_panier_session.py

Code testé / Tested code : BaseBillet/services_panier.py

Chaque test est marqué `django_db` : pytest-django l'exécute dans une transaction annulée
à la fin. Les objets créés par les fabriques ne restent pas en base de dev.
/ Every test runs in a rolled-back transaction: factory objects do not stay in the dev DB.

Lancer / Run : make test ARGS="tests/pytest/test_panier_session.py"
"""

from decimal import Decimal
from types import SimpleNamespace

import pytest
from django_tenants.utils import tenant_context

from fabriques_panier import (
    ajouter_un_tarif,
    catalogue_stripe_simule,
    configuration_modifiee,
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
    """
    Le lieu `lespass`, avec Stripe (catalogue) et Celery simulés pendant tout le test.
    / The `lespass` venue, with the Stripe catalogue and Celery faked for the whole test.

    Créer un produit ou un événement demande déjà des tâches Celery et des appels Stripe :
    les simulations doivent être actives AVANT les fabriques.
    / Creating a product or an event already requests Celery tasks and Stripe calls.
    """
    with tenant_context(tenant):
        with catalogue_stripe_simule() as catalogue_stripe:
            with taches_celery_enregistrees() as taches_demandees:
                yield SimpleNamespace(
                    tenant=tenant,
                    catalogue_stripe=catalogue_stripe,
                    taches_demandees=taches_demandees,
                )


# --------------------------------------------------------------------------
# Tests témoins : un par grande fonction du panier
# / Smoke tests: one per main cart function
# --------------------------------------------------------------------------


def test_add_ticket_stocke_le_billet_dans_la_session(lieu):
    """Un billet ajouté est rangé dans la session, avec sa quantité.
    / An added ticket is stored in the session, with its quantity."""
    from BaseBillet.services_panier import PanierSession

    billetterie = creer_evenement_avec_tarif(prix="10.00")
    panier = PanierSession(requete_avec_session(creer_utilisateur()))

    panier.add_ticket(billetterie.evenement.uuid, billetterie.tarif.uuid, qty=2)

    items_du_panier = panier.items()
    assert len(items_du_panier) == 1
    assert items_du_panier[0]["type"] == "ticket"
    assert items_du_panier[0]["event_uuid"] == str(billetterie.evenement.uuid)
    assert items_du_panier[0]["price_uuid"] == str(billetterie.tarif.uuid)
    assert items_du_panier[0]["qty"] == 2
    assert panier.count() == 2


def test_add_membership_stocke_l_adhesion_dans_la_session(lieu):
    """Une adhésion ajoutée est rangée dans la session, avec prénom et nom nettoyés.
    / An added membership is stored in the session, with trimmed first and last names."""
    from BaseBillet.services_panier import PanierSession

    adhesion = creer_adhesion(prix="15.00")
    panier = PanierSession(requete_avec_session(creer_utilisateur()))

    panier.add_membership(
        adhesion.tarif.uuid, firstname="  Ada ", lastname=" Lovelace  "
    )

    items_du_panier = panier.items()
    assert len(items_du_panier) == 1
    assert items_du_panier[0]["type"] == "membership"
    assert items_du_panier[0]["price_uuid"] == str(adhesion.tarif.uuid)
    assert items_du_panier[0]["firstname"] == "Ada"
    assert items_du_panier[0]["lastname"] == "Lovelace"


def test_add_resource_stocke_le_creneau_et_estime_le_montant(lieu):
    """Un créneau de ressource ajouté est rangé avec son estimation : heures × tarif horaire.
    / An added resource slot is stored with its estimate: hours × hourly price."""
    from BaseBillet.services_panier import PanierSession

    location = creer_ressource_avec_tarif(prix="12.00")
    panier = PanierSession(requete_avec_session(creer_utilisateur()))

    panier.add_resource(
        resource_uuid=location.ressource.pk,
        price_uuid=location.tarif.uuid,
        start_datetime=location.debut_du_creneau,
        slot_duration_minutes=60,
        slot_count=2,
    )

    items_du_panier = panier.items()
    assert len(items_du_panier) == 1
    assert items_du_panier[0]["type"] == "resource"
    assert items_du_panier[0]["resource_uuid"] == str(location.ressource.pk)
    assert Decimal(items_du_panier[0]["total_estimation"]) == Decimal("24.00")


def test_revalidate_all_garde_intact_un_panier_toujours_valide(lieu):
    """Au paiement, un panier encore valide est rejoué sans erreur ni perte d'item.
    / At checkout, a still-valid cart is replayed with no error and no lost item."""
    from BaseBillet.services_panier import PanierSession

    billetterie = creer_evenement_avec_tarif(prix="10.00")
    adhesion = creer_adhesion(prix="15.00")
    panier = PanierSession(requete_avec_session(creer_utilisateur()))
    panier.add_membership(adhesion.tarif.uuid)
    panier.add_ticket(billetterie.evenement.uuid, billetterie.tarif.uuid, qty=1)

    erreurs_de_validation = panier.revalidate_all()

    assert erreurs_de_validation == []
    types_dans_le_panier = [item["type"] for item in panier.items()]
    assert types_dans_le_panier == ["membership", "ticket"]


def test_calcul_total_centimes_additionne_billets_adhesion_et_ressource(lieu):
    """Total en centimes : 2 billets à 10 € + adhésion à 15 € + 1 h de ressource à 12 €.
    / Total in cents: 2 tickets at 10 € + membership at 15 € + 1 hour of resource at 12 €."""
    from BaseBillet.services_panier import PanierSession

    billetterie = creer_evenement_avec_tarif(prix="10.00")
    adhesion = creer_adhesion(prix="15.00")
    location = creer_ressource_avec_tarif(prix="12.00")
    panier = PanierSession(requete_avec_session(creer_utilisateur()))
    panier.add_ticket(billetterie.evenement.uuid, billetterie.tarif.uuid, qty=2)
    panier.add_membership(adhesion.tarif.uuid)
    panier.add_resource(
        resource_uuid=location.ressource.pk,
        price_uuid=location.tarif.uuid,
        start_datetime=location.debut_du_creneau,
        slot_duration_minutes=60,
        slot_count=1,
    )

    assert panier.calcul_total_centimes() == 2000 + 1500 + 1200


# --------------------------------------------------------------------------
# Lecture, retrait, vidage
# / Reading, removing, clearing
# --------------------------------------------------------------------------


def test_un_panier_neuf_est_vide(lieu):
    """Un panier fraîchement créé ne contient rien.
    / A fresh cart holds nothing."""
    from BaseBillet.services_panier import PanierSession

    panier = PanierSession(requete_avec_session(creer_utilisateur()))

    assert panier.is_empty() is True
    assert panier.count() == 0
    assert panier.items() == []


def test_count_additionne_les_quantites_de_billets_et_une_par_adhesion(lieu):
    """3 billets + 2 billets + 1 adhésion : le badge affiche 6.
    / 3 tickets + 2 tickets + 1 membership: the badge shows 6."""
    from BaseBillet.services_panier import PanierSession

    concert = creer_evenement_avec_tarif(prix="10.00")
    adhesion = creer_adhesion(prix="15.00")
    panier = PanierSession(requete_avec_session(creer_utilisateur()))
    panier.add_ticket(concert.evenement.uuid, concert.tarif.uuid, qty=3)
    panier.add_ticket(concert.evenement.uuid, concert.tarif.uuid, qty=2)
    panier.add_membership(adhesion.tarif.uuid)

    assert panier.count() == 6


def test_remove_item_retire_l_item_du_rang_donne(lieu):
    """Retirer le rang 0 laisse le deuxième item.
    / Removing position 0 leaves the second item."""
    from BaseBillet.services_panier import PanierSession

    concert = creer_evenement_avec_tarif(prix="10.00")
    adhesion = creer_adhesion(prix="15.00")
    panier = PanierSession(requete_avec_session(creer_utilisateur()))
    panier.add_ticket(concert.evenement.uuid, concert.tarif.uuid, qty=1)
    panier.add_membership(adhesion.tarif.uuid)

    panier.remove_item(0)

    assert [item["type"] for item in panier.items()] == ["membership"]


def test_remove_item_avec_un_rang_invalide_ne_fait_rien(lieu):
    """Rang hors limites ou négatif : rien n'est retiré, aucune erreur.
    / Out-of-range or negative position: nothing removed, no error."""
    from BaseBillet.services_panier import PanierSession

    concert = creer_evenement_avec_tarif(prix="10.00")
    panier = PanierSession(requete_avec_session(creer_utilisateur()))
    panier.add_ticket(concert.evenement.uuid, concert.tarif.uuid, qty=1)

    panier.remove_item(99)
    panier.remove_item(-1)

    assert len(panier.items()) == 1


def test_clear_vide_tout_le_panier(lieu):
    """`clear()` retire billets et adhésions.
    / `clear()` removes tickets and memberships."""
    from BaseBillet.services_panier import PanierSession

    concert = creer_evenement_avec_tarif(prix="10.00")
    adhesion = creer_adhesion(prix="15.00")
    panier = PanierSession(requete_avec_session(creer_utilisateur()))
    panier.add_ticket(concert.evenement.uuid, concert.tarif.uuid, qty=2)
    panier.add_membership(adhesion.tarif.uuid)

    panier.clear()

    assert panier.is_empty() is True
    assert panier.count() == 0


def test_deux_paniers_sur_la_meme_session_voient_les_memes_items(lieu):
    """Le panier vit dans la session : une nouvelle instance relit ce qui a été ajouté.
    / The cart lives in the session: a new instance reads what was added."""
    from BaseBillet.services_panier import PanierSession

    concert = creer_evenement_avec_tarif(prix="10.00")
    requete = requete_avec_session(creer_utilisateur())
    PanierSession(requete).add_ticket(concert.evenement.uuid, concert.tarif.uuid, qty=2)

    assert PanierSession(requete).count() == 2


def test_adhesions_product_ids_ne_liste_que_les_produits_d_adhesion(lieu):
    """Adhésion + billet au panier : seul le produit de l'adhésion est listé.
    / Membership + ticket in the cart: only the membership product is listed."""
    from BaseBillet.services_panier import PanierSession

    concert = creer_evenement_avec_tarif(prix="10.00")
    adhesion = creer_adhesion(prix="15.00")
    panier = PanierSession(requete_avec_session(creer_utilisateur()))
    panier.add_membership(adhesion.tarif.uuid)
    panier.add_ticket(concert.evenement.uuid, concert.tarif.uuid, qty=1)

    assert panier.adhesions_product_ids() == [adhesion.produit.uuid]


# --------------------------------------------------------------------------
# add_ticket : refus
# / add_ticket: refusals
# --------------------------------------------------------------------------


def test_add_ticket_refuse_une_quantite_nulle(lieu):
    """Quantité 0 : refusée.
    / Quantity 0: refused."""
    from BaseBillet.services_panier import InvalidItemError, PanierSession

    concert = creer_evenement_avec_tarif(prix="10.00")
    panier = PanierSession(requete_avec_session(creer_utilisateur()))

    with pytest.raises(InvalidItemError):
        panier.add_ticket(concert.evenement.uuid, concert.tarif.uuid, qty=0)
    assert panier.is_empty()


def test_add_ticket_refuse_un_evenement_inconnu(lieu):
    """Événement introuvable : refusé.
    / Unknown event: refused."""
    import uuid

    from BaseBillet.services_panier import InvalidItemError, PanierSession

    panier = PanierSession(requete_avec_session(creer_utilisateur()))

    with pytest.raises(InvalidItemError):
        panier.add_ticket(uuid.uuid4(), uuid.uuid4(), qty=1)


def test_add_ticket_refuse_un_tarif_inconnu(lieu):
    """Tarif introuvable : refusé.
    / Unknown price: refused."""
    import uuid

    from BaseBillet.services_panier import InvalidItemError, PanierSession

    concert = creer_evenement_avec_tarif(prix="10.00")
    panier = PanierSession(requete_avec_session(creer_utilisateur()))

    with pytest.raises(InvalidItemError):
        panier.add_ticket(concert.evenement.uuid, uuid.uuid4(), qty=1)


def test_add_ticket_refuse_un_tarif_non_publie(lieu):
    """Tarif non publié : refusé.
    / Unpublished price: refused."""
    from BaseBillet.services_panier import InvalidItemError, PanierSession

    concert = creer_evenement_avec_tarif(prix="10.00")
    concert.tarif.publish = False
    concert.tarif.save()
    panier = PanierSession(requete_avec_session(creer_utilisateur()))

    with pytest.raises(InvalidItemError):
        panier.add_ticket(concert.evenement.uuid, concert.tarif.uuid, qty=1)


def test_add_ticket_refuse_un_produit_archive(lieu):
    """Produit archivé : refusé.
    / Archived product: refused."""
    from BaseBillet.services_panier import InvalidItemError, PanierSession

    concert = creer_evenement_avec_tarif(prix="10.00")
    concert.produit.archive = True
    concert.produit.save()
    panier = PanierSession(requete_avec_session(creer_utilisateur()))

    with pytest.raises(InvalidItemError):
        panier.add_ticket(concert.evenement.uuid, concert.tarif.uuid, qty=1)


def test_add_ticket_refuse_un_tarif_qui_n_est_pas_dans_l_evenement(lieu):
    """Tarif d'un produit non lié à l'événement : refusé.
    / Price of a product not linked to the event: refused."""
    from BaseBillet.services_panier import InvalidItemError, PanierSession

    concert = creer_evenement_avec_tarif(prix="10.00")
    autre_billetterie = creer_evenement_avec_tarif(prix="5.00")
    panier = PanierSession(requete_avec_session(creer_utilisateur()))

    with pytest.raises(InvalidItemError):
        panier.add_ticket(concert.evenement.uuid, autre_billetterie.tarif.uuid, qty=1)


def test_add_ticket_refuse_un_evenement_complet(lieu):
    """Jauge atteinte : l'événement est complet, refusé.
    / Capacity reached: the event is full, refused."""
    from BaseBillet.services_panier import InvalidItemError, PanierSession
    from fabriques_panier import creer_un_billet_deja_vendu

    concert = creer_evenement_avec_tarif(prix="10.00", jauge_max=1)
    creer_un_billet_deja_vendu(creer_utilisateur(), concert)
    panier = PanierSession(requete_avec_session(creer_utilisateur()))

    with pytest.raises(InvalidItemError):
        panier.add_ticket(concert.evenement.uuid, concert.tarif.uuid, qty=1)


@pytest.mark.parametrize("montant_saisi", [None, "2.00", "1000000.00"])
def test_add_ticket_prix_libre_refuse_un_montant_absent_trop_bas_ou_trop_haut(
    lieu, montant_saisi
):
    """Prix libre (minimum 5 €) : montant absent, sous le minimum ou démesuré, refusé.
    / Free price (minimum 5 €): missing, below minimum or absurd amount, refused."""
    from BaseBillet.services_panier import InvalidItemError, PanierSession

    concert = creer_evenement_avec_tarif(prix="5.00", prix_libre=True)
    panier = PanierSession(requete_avec_session(creer_utilisateur()))

    with pytest.raises(InvalidItemError):
        panier.add_ticket(
            concert.evenement.uuid,
            concert.tarif.uuid,
            qty=1,
            custom_amount=montant_saisi,
        )


def mettre_l_evenement_dans_l_etat(concert, etat_de_l_evenement):
    """
    Place l'événement de test dans un état de vente. Un événement sans date de fin est
    considéré terminé 24 heures après son début (Event.est_termine).
    / Puts the test event in a sales state.
    """
    from datetime import timedelta

    from django.utils import timezone

    evenement = concert.evenement
    maintenant = timezone.now()
    if etat_de_l_evenement == "termine":
        evenement.datetime = maintenant - timedelta(days=2)
        evenement.end_datetime = maintenant - timedelta(days=2) + timedelta(hours=2)
    elif etat_de_l_evenement == "commence_depuis_2_h_sans_date_de_fin":
        evenement.datetime = maintenant - timedelta(hours=2)
        evenement.end_datetime = None
    elif etat_de_l_evenement == "commence_depuis_2_jours_sans_date_de_fin":
        evenement.datetime = maintenant - timedelta(days=2)
        evenement.end_datetime = None
    elif etat_de_l_evenement == "commence_depuis_30_min_sans_date_de_fin":
        evenement.datetime = maintenant - timedelta(minutes=30)
        evenement.end_datetime = None
    elif etat_de_l_evenement == "en_cours_jusqu_a_demain":
        # Festival commencé il y a 3 jours, fini demain.
        # / Festival started 3 days ago, ending tomorrow.
        evenement.datetime = maintenant - timedelta(days=3)
        evenement.end_datetime = maintenant + timedelta(days=1)
    elif etat_de_l_evenement == "non_publie":
        evenement.published = False
    elif etat_de_l_evenement == "archive":
        evenement.archived = True
    evenement.save()


@pytest.mark.parametrize(
    "etat_de_l_evenement",
    ["termine", "commence_depuis_2_jours_sans_date_de_fin", "archive"],
)
def test_add_ticket_refuse_un_evenement_qui_n_est_plus_en_vente(
    lieu, etat_de_l_evenement
):
    """Événement terminé ou archivé : on ne peut plus y prendre de billet.
    / Ended or archived event: no ticket can be taken anymore."""
    from BaseBillet.services_panier import InvalidItemError, PanierSession

    concert = creer_evenement_avec_tarif(prix="10.00")
    mettre_l_evenement_dans_l_etat(concert, etat_de_l_evenement)
    panier = PanierSession(requete_avec_session(creer_utilisateur()))

    with pytest.raises(InvalidItemError):
        panier.add_ticket(concert.evenement.uuid, concert.tarif.uuid, qty=1)


@pytest.mark.parametrize(
    "etat_de_l_evenement",
    [
        "en_cours_jusqu_a_demain",
        "commence_depuis_30_min_sans_date_de_fin",
        "commence_depuis_2_h_sans_date_de_fin",
        "non_publie",
    ],
)
def test_add_ticket_accepte_un_evenement_commence_mais_pas_termine(
    lieu, etat_de_l_evenement
):
    """Événement commencé mais pas terminé (2e jour d'un festival ; sans date de fin, moins de
    24 h après le début) ou non publié (lien direct) : toujours en vente.
    / Started but not ended, or unpublished (direct link) event: still on sale."""
    from BaseBillet.services_panier import PanierSession

    concert = creer_evenement_avec_tarif(prix="10.00")
    mettre_l_evenement_dans_l_etat(concert, etat_de_l_evenement)
    panier = PanierSession(requete_avec_session(creer_utilisateur()))

    with configuration_modifiee(allow_concurrent_bookings=True):
        panier.add_ticket(concert.evenement.uuid, concert.tarif.uuid, qty=1)

    assert len(panier.items()) == 1


# --------------------------------------------------------------------------
# add_ticket : code promo porté par l'item
# / add_ticket: promo code carried by the item
# --------------------------------------------------------------------------


def creer_code_promo(produit, **champs):
    """Code promo -10 % lié au produit, nom unique.
    / -10 % promo code linked to the product, unique name."""
    from BaseBillet.models import PromotionalCode
    from fabriques_panier import identifiant_unique

    return PromotionalCode.objects.create(
        name=f"TEST_panier_code_{identifiant_unique()}",
        discount_rate=Decimal("10.00"),
        product=produit,
        **champs,
    )


def test_add_ticket_range_un_code_promo_valide_sur_l_item(lieu):
    """Code actif, utilisable et lié au produit : rangé sur l'item.
    / Active, usable code linked to the product: stored on the item."""
    from BaseBillet.services_panier import PanierSession

    concert = creer_evenement_avec_tarif(prix="10.00")
    code_promo = creer_code_promo(concert.produit)
    panier = PanierSession(requete_avec_session(creer_utilisateur()))

    panier.add_ticket(
        concert.evenement.uuid,
        concert.tarif.uuid,
        qty=1,
        promotional_code_name=code_promo.name,
    )

    assert panier.items()[0]["promotional_code_name"] == code_promo.name


@pytest.mark.parametrize(
    "defaut_du_code", ["inconnu", "inactif", "epuise", "autre_produit"]
)
def test_add_ticket_refuse_un_code_promo_inutilisable(lieu, defaut_du_code):
    """Code inconnu, inactif, épuisé ou lié à un autre produit : refusé.
    / Unknown, inactive, used-up or other-product code: refused."""
    from BaseBillet.services_panier import InvalidItemError, PanierSession

    concert = creer_evenement_avec_tarif(prix="10.00")
    if defaut_du_code == "inconnu":
        nom_du_code = "TEST_panier_CODE_INCONNU"
    elif defaut_du_code == "inactif":
        nom_du_code = creer_code_promo(concert.produit, is_active=False).name
    elif defaut_du_code == "epuise":
        nom_du_code = creer_code_promo(
            concert.produit, usage_limit=1, usage_count=1
        ).name
    else:
        autre_billetterie = creer_evenement_avec_tarif(prix="5.00")
        nom_du_code = creer_code_promo(autre_billetterie.produit).name
    panier = PanierSession(requete_avec_session(creer_utilisateur()))

    with pytest.raises(InvalidItemError):
        panier.add_ticket(
            concert.evenement.uuid,
            concert.tarif.uuid,
            qty=1,
            promotional_code_name=nom_du_code,
        )


# --------------------------------------------------------------------------
# add_ticket : chevauchement d'horaires (réglage du lieu)
# / add_ticket: time overlap (venue setting)
# --------------------------------------------------------------------------


def creer_deux_evenements_qui_se_chevauchent():
    """Deux événements le même jour : 20 h-22 h et 21 h-23 h.
    / Two events on the same day: 8-10 pm and 9-11 pm."""
    from django.utils import timezone

    from BaseBillet.models import Event

    concert = creer_evenement_avec_tarif(prix="10.00", jours_avant_l_evenement=5)
    debut_du_concert = concert.evenement.datetime
    spectacle = creer_evenement_avec_tarif(prix="8.00")
    Event.objects.filter(pk=spectacle.evenement.pk).update(
        datetime=debut_du_concert + timezone.timedelta(hours=1),
        end_datetime=debut_du_concert + timezone.timedelta(hours=3),
    )
    spectacle.evenement.refresh_from_db()
    return concert, spectacle


def test_add_ticket_refuse_un_evenement_qui_chevauche_un_autre_du_panier(lieu):
    """Lieu qui interdit les réservations simultanées : deux événements qui se chevauchent
    ne vont pas dans le même panier.
    / Venue forbidding concurrent bookings: two overlapping events cannot share a cart."""
    from BaseBillet.services_panier import InvalidItemError, PanierSession

    concert, spectacle = creer_deux_evenements_qui_se_chevauchent()
    panier = PanierSession(requete_avec_session(creer_utilisateur()))

    with configuration_modifiee(allow_concurrent_bookings=False):
        panier.add_ticket(concert.evenement.uuid, concert.tarif.uuid, qty=1)
        with pytest.raises(InvalidItemError):
            panier.add_ticket(spectacle.evenement.uuid, spectacle.tarif.uuid, qty=1)


@pytest.mark.parametrize(
    "statut_de_la_reservation_existante, minutes_ecoulees, refuse",
    [
        ("VALID", 60, True),
        ("UNPAID", 5, True),
        ("UNPAID", 20, True),
        ("UNPAID", 40, False),
    ],
)
def test_add_ticket_et_les_reservations_deja_en_base_qui_chevauchent(
    lieu, statut_de_la_reservation_existante, minutes_ecoulees, refuse
):
    """
    Lieu qui interdit les réservations simultanées. Une réservation validée qui chevauche
    bloque toujours ; une réservation non payée ne bloque que pendant 30 minutes.
    / A valid overlapping reservation always blocks; an unpaid one only for 30 minutes.
    """
    from django.utils import timezone

    from BaseBillet.models import Reservation
    from BaseBillet.services_panier import InvalidItemError, PanierSession

    acheteur = creer_utilisateur()
    concert, spectacle = creer_deux_evenements_qui_se_chevauchent()
    reservation_existante = Reservation.objects.create(
        user_commande=acheteur,
        event=concert.evenement,
        status=getattr(Reservation, statut_de_la_reservation_existante),
    )
    Reservation.objects.filter(pk=reservation_existante.pk).update(
        datetime=timezone.now() - timezone.timedelta(minutes=minutes_ecoulees)
    )
    panier = PanierSession(requete_avec_session(acheteur))

    with configuration_modifiee(allow_concurrent_bookings=False):
        if refuse:
            with pytest.raises(InvalidItemError):
                panier.add_ticket(spectacle.evenement.uuid, spectacle.tarif.uuid, qty=1)
        else:
            panier.add_ticket(spectacle.evenement.uuid, spectacle.tarif.uuid, qty=1)
            assert len(panier.items()) == 1


# --------------------------------------------------------------------------
# validate_ticket_cart_limits : limites par personne et jauge, panier compris
# / validate_ticket_cart_limits: per-person limits and capacity, cart included
# --------------------------------------------------------------------------


def test_limite_par_personne_de_l_evenement_compte_le_panier(lieu):
    """Maximum 4 par personne pour l'événement : 2 + 2 au panier, un 5e est refusé.
    / Event limit 4 per person: 2 + 2 in the cart, a 5th is refused."""
    from BaseBillet.services_panier import InvalidItemError, PanierSession

    concert = creer_evenement_avec_tarif(prix="10.00", max_par_personne_evenement=4)
    tarif_2 = ajouter_un_tarif(concert.produit, prix="10.00", nom="Plein 2")
    panier = PanierSession(requete_avec_session())
    panier.add_ticket(concert.evenement.uuid, concert.tarif.uuid, qty=2)
    panier.add_ticket(concert.evenement.uuid, tarif_2.uuid, qty=2)

    with pytest.raises(InvalidItemError):
        panier.add_ticket(concert.evenement.uuid, concert.tarif.uuid, qty=1)


def test_limite_par_personne_du_produit_compte_le_panier(lieu):
    """Maximum 3 par personne pour le produit (deux tarifs) : un 4e billet est refusé.
    / Product limit 3 per person (two prices): a 4th ticket is refused."""
    from BaseBillet.services_panier import InvalidItemError, PanierSession

    concert = creer_evenement_avec_tarif(prix="10.00", max_par_personne_produit=3)
    tarif_2 = ajouter_un_tarif(concert.produit, prix="10.00", nom="Plein 2")
    panier = PanierSession(requete_avec_session())
    panier.add_ticket(concert.evenement.uuid, concert.tarif.uuid, qty=2)
    panier.add_ticket(concert.evenement.uuid, tarif_2.uuid, qty=1)

    with pytest.raises(InvalidItemError):
        panier.add_ticket(concert.evenement.uuid, tarif_2.uuid, qty=1)


def test_limite_par_personne_du_tarif_compte_le_panier(lieu):
    """Maximum 2 par personne pour le tarif : un 3e est refusé.
    / Price limit 2 per person: a 3rd is refused."""
    from BaseBillet.services_panier import InvalidItemError, PanierSession

    concert = creer_evenement_avec_tarif(prix="10.00", max_par_personne_tarif=2)
    panier = PanierSession(requete_avec_session())
    panier.add_ticket(concert.evenement.uuid, concert.tarif.uuid, qty=2)

    with pytest.raises(InvalidItemError):
        panier.add_ticket(concert.evenement.uuid, concert.tarif.uuid, qty=1)


def test_une_quantite_pile_a_la_limite_est_acceptee(lieu):
    """Maximum 2 par tarif, demande de 2 : accepté (la limite est incluse).
    / Price limit 2, request for 2: accepted (the limit is inclusive)."""
    from BaseBillet.services_panier import PanierSession

    concert = creer_evenement_avec_tarif(prix="10.00", max_par_personne_tarif=2)
    panier = PanierSession(requete_avec_session())

    panier.add_ticket(concert.evenement.uuid, concert.tarif.uuid, qty=2)

    assert panier.count() == 2


def test_la_jauge_de_l_evenement_limite_la_quantite_demandee(lieu):
    """Jauge de 5, demande de 6 : refusé.
    / Capacity 5, request for 6: refused."""
    from BaseBillet.services_panier import InvalidItemError, PanierSession

    concert = creer_evenement_avec_tarif(prix="10.00", jauge_max=5)
    panier = PanierSession(requete_avec_session())

    with pytest.raises(InvalidItemError):
        panier.add_ticket(concert.evenement.uuid, concert.tarif.uuid, qty=6)


def test_limite_de_l_evenement_compte_les_billets_deja_achetes_et_le_panier(lieu):
    """
    Connecté, maximum 4 par personne : 2 billets déjà achetés + 2 au panier. Un 5e est
    refusé proprement (erreur de panier, pas d'erreur de format du message).
    / Logged in, limit 4: 2 bought + 2 in the cart. A 5th is refused cleanly.
    """
    from BaseBillet.services_panier import InvalidItemError, PanierSession
    from fabriques_panier import creer_un_billet_deja_vendu

    acheteur = creer_utilisateur()
    concert = creer_evenement_avec_tarif(prix="10.00", max_par_personne_evenement=4)
    creer_un_billet_deja_vendu(acheteur, concert)
    creer_un_billet_deja_vendu(acheteur, concert)
    tarif_2 = ajouter_un_tarif(concert.produit, prix="10.00", nom="Plein 2")
    panier = PanierSession(requete_avec_session(acheteur))

    # Réservations simultanées autorisées : le seul motif de refus possible est la limite.
    # / Concurrent bookings allowed: the per-person limit is the only possible refusal.
    with configuration_modifiee(allow_concurrent_bookings=True):
        panier.add_ticket(concert.evenement.uuid, tarif_2.uuid, qty=2)
        with pytest.raises(InvalidItemError):
            panier.add_ticket(concert.evenement.uuid, tarif_2.uuid, qty=1)


def test_le_stock_du_tarif_compte_ce_qui_est_deja_dans_le_panier(lieu):
    """Stock du tarif : 2. Un billet au panier, puis 2 de plus : refusé (1 + 2 > 2).
    / Price stock 2: one in the cart, then 2 more: refused."""
    from BaseBillet.services_panier import InvalidItemError, PanierSession

    concert = creer_evenement_avec_tarif(prix="10.00", stock_du_tarif=2)
    panier = PanierSession(requete_avec_session(creer_utilisateur()))

    with configuration_modifiee(allow_concurrent_bookings=True):
        panier.add_ticket(concert.evenement.uuid, concert.tarif.uuid, qty=1)
        with pytest.raises(InvalidItemError):
            panier.add_ticket(concert.evenement.uuid, concert.tarif.uuid, qty=2)


@pytest.mark.parametrize("minutes_ecoulees", [0, 20])
def test_la_jauge_compte_les_billets_en_cours_de_paiement(lieu, minutes_ecoulees):
    """
    Jauge de 10, un autre client a 8 billets en cours de paiement (depuis moins de 30 min) :
    2 billets passent, un 3e est refusé.
    / Capacity 10, another buyer has 8 tickets being paid (under 30 min): 2 pass, a 3rd is
    refused.
    """
    from django.utils import timezone

    from BaseBillet.models import PriceSold, ProductSold, Reservation, Ticket
    from BaseBillet.services_panier import InvalidItemError, PanierSession

    concert = creer_evenement_avec_tarif(prix="10.00", jauge_max=10)
    produit_vendu = ProductSold.objects.create(
        product=concert.produit, event=concert.evenement
    )
    tarif_vendu = PriceSold.objects.create(
        productsold=produit_vendu, price=concert.tarif, prix=concert.tarif.prix
    )
    reservation_en_cours = Reservation.objects.create(
        user_commande=creer_utilisateur(),
        event=concert.evenement,
        status=Reservation.UNPAID,
    )
    for _i in range(8):
        Ticket.objects.create(
            reservation=reservation_en_cours,
            pricesold=tarif_vendu,
            status=Ticket.CREATED,
        )
    Reservation.objects.filter(pk=reservation_en_cours.pk).update(
        datetime=timezone.now() - timezone.timedelta(minutes=minutes_ecoulees)
    )
    panier = PanierSession(requete_avec_session())
    panier.add_ticket(concert.evenement.uuid, concert.tarif.uuid, qty=2)

    with pytest.raises(InvalidItemError):
        panier.add_ticket(concert.evenement.uuid, concert.tarif.uuid, qty=1)


# --------------------------------------------------------------------------
# add_membership : refus
# / add_membership: refusals
# --------------------------------------------------------------------------


@pytest.mark.parametrize("sorte_d_adhesion", ["recurrente", "validation_manuelle"])
def test_add_membership_refuse_les_adhesions_hors_panier(lieu, sorte_d_adhesion):
    """Adhésion récurrente ou à validation manuelle : paiement direct seulement, refusée.
    / Recurring or manual-validation membership: direct payment only, refused."""
    from BaseBillet.services_panier import InvalidItemError, PanierSession

    if sorte_d_adhesion == "recurrente":
        adhesion = creer_adhesion(recurrente=True)
    else:
        adhesion = creer_adhesion(validation_manuelle=True)
    panier = PanierSession(requete_avec_session(creer_utilisateur()))

    with pytest.raises(InvalidItemError):
        panier.add_membership(adhesion.tarif.uuid)


def test_add_membership_refuse_la_meme_adhesion_deux_fois(lieu):
    """La même adhésion ne va qu'une fois dans le panier.
    / The same membership only goes once into the cart."""
    from BaseBillet.services_panier import InvalidItemError, PanierSession

    adhesion = creer_adhesion()
    panier = PanierSession(requete_avec_session(creer_utilisateur()))
    panier.add_membership(adhesion.tarif.uuid)

    with pytest.raises(InvalidItemError):
        panier.add_membership(adhesion.tarif.uuid)


def test_add_membership_refuse_un_tarif_qui_n_est_pas_une_adhesion(lieu):
    """Un tarif de billet envoyé comme adhésion : refusé.
    / A ticket price sent as a membership: refused."""
    from BaseBillet.services_panier import InvalidItemError, PanierSession

    concert = creer_evenement_avec_tarif(prix="10.00")
    panier = PanierSession(requete_avec_session(creer_utilisateur()))

    with pytest.raises(InvalidItemError):
        panier.add_membership(concert.tarif.uuid)


# --------------------------------------------------------------------------
# add_resource : refus
# / add_resource: refusals
# --------------------------------------------------------------------------


def ajouter_le_creneau(panier, location, tarif=None, debut=None, nombre_d_heures=1):
    """Ajoute un créneau de la ressource au panier.
    / Adds a resource slot to the cart."""
    panier.add_resource(
        resource_uuid=location.ressource.pk,
        price_uuid=(tarif or location.tarif).uuid,
        start_datetime=debut or location.debut_du_creneau,
        slot_duration_minutes=60,
        slot_count=nombre_d_heures,
    )


@pytest.mark.parametrize("defaut_du_tarif", ["recurrent", "validation_manuelle"])
def test_add_resource_refuse_les_tarifs_hors_panier(lieu, defaut_du_tarif):
    """Tarif de ressource récurrent ou à validation manuelle : refusé.
    / Recurring or manual-validation resource price: refused."""
    from BaseBillet.services_panier import InvalidItemError, PanierSession

    location = creer_ressource_avec_tarif()
    if defaut_du_tarif == "recurrent":
        location.tarif.recurring_payment = True
    else:
        location.tarif.manual_validation = True
    location.tarif.save()
    panier = PanierSession(requete_avec_session(creer_utilisateur()))

    with pytest.raises(InvalidItemError):
        ajouter_le_creneau(panier, location)


def test_add_resource_refuse_un_tarif_de_billet(lieu):
    """Tarif d'un produit billet envoyé pour une ressource : refusé.
    / A ticket product price sent for a resource: refused."""
    from BaseBillet.services_panier import InvalidItemError, PanierSession

    location = creer_ressource_avec_tarif()
    concert = creer_evenement_avec_tarif(prix="10.00")
    panier = PanierSession(requete_avec_session(creer_utilisateur()))

    with pytest.raises(InvalidItemError):
        ajouter_le_creneau(panier, location, tarif=concert.tarif)


def test_add_resource_refuse_le_tarif_d_une_autre_ressource(lieu):
    """Tarif (gratuit) d'une autre ressource : refusé.
    / Another resource's (free) price: refused."""
    from BaseBillet.services_panier import InvalidItemError, PanierSession

    salle_payante = creer_ressource_avec_tarif(prix="12.00")
    salle_gratuite = creer_ressource_avec_tarif(prix="0.00")
    panier = PanierSession(requete_avec_session(creer_utilisateur()))

    with pytest.raises(InvalidItemError):
        ajouter_le_creneau(panier, salle_payante, tarif=salle_gratuite.tarif)


def test_add_resource_refuse_un_creneau_hors_des_horaires_d_ouverture(lieu):
    """Créneau à 3 h du matin (ressource ouverte de 10 h à 18 h) : refusé.
    / Slot at 3 am (resource open 10 am-6 pm): refused."""
    from BaseBillet.services_panier import InvalidItemError, PanierSession

    location = creer_ressource_avec_tarif()
    panier = PanierSession(requete_avec_session(creer_utilisateur()))

    with pytest.raises(InvalidItemError):
        ajouter_le_creneau(
            panier, location, debut=location.debut_du_creneau.replace(hour=3)
        )


def test_add_resource_refuse_un_creneau_deja_dans_le_panier(lieu):
    """Le même créneau ajouté deux fois : le deuxième ajout est refusé.
    / The same slot added twice: the second add is refused."""
    from BaseBillet.services_panier import InvalidItemError, PanierSession

    location = creer_ressource_avec_tarif()
    panier = PanierSession(requete_avec_session(creer_utilisateur()))
    ajouter_le_creneau(panier, location)

    with pytest.raises(InvalidItemError):
        ajouter_le_creneau(panier, location)


def test_add_resource_a_tarif_adherent_refuse_sans_adhesion_et_accepte_avec(lieu):
    """Tarif de ressource réservé aux adhérents : refusé seul, accepté avec l'adhésion au panier.
    / Members-only resource price: refused alone, accepted with the membership in the cart."""
    from BaseBillet.services_panier import InvalidItemError, PanierSession

    location = creer_ressource_avec_tarif(prix="3.00")
    adhesion = creer_adhesion()
    location.tarif.adhesions_obligatoires.add(adhesion.produit)
    panier = PanierSession(requete_avec_session(creer_utilisateur()))

    with pytest.raises(InvalidItemError):
        ajouter_le_creneau(panier, location)

    panier.add_membership(adhesion.tarif.uuid)
    ajouter_le_creneau(panier, location)
    assert [item["type"] for item in panier.items()] == ["membership", "resource"]


# --------------------------------------------------------------------------
# Adhésion obligatoire et revalidation au paiement
# / Required membership and revalidation at checkout
# --------------------------------------------------------------------------


def preparer_un_billet_adherent():
    """Un événement dont le tarif exige une adhésion, et cette adhésion.
    / An event whose price requires a membership, and that membership."""
    concert = creer_evenement_avec_tarif(prix="5.00")
    adhesion = creer_adhesion()
    concert.tarif.adhesions_obligatoires.add(adhesion.produit)
    return concert, adhesion


def test_add_ticket_refuse_un_tarif_adherent_sans_adhesion(lieu):
    """Tarif adhérent, aucune adhésion ni en base ni au panier : refusé.
    / Members-only price, no membership in the DB nor in the cart: refused."""
    from BaseBillet.services_panier import InvalidItemError, PanierSession

    concert, _adhesion = preparer_un_billet_adherent()
    panier = PanierSession(requete_avec_session(creer_utilisateur()))

    with pytest.raises(InvalidItemError):
        panier.add_ticket(concert.evenement.uuid, concert.tarif.uuid, qty=1)


def test_add_ticket_accepte_un_tarif_adherent_si_l_adhesion_est_au_panier(lieu):
    """Tarif adhérent, adhésion déjà au panier : accepté.
    / Members-only price, membership already in the cart: accepted."""
    from BaseBillet.services_panier import PanierSession

    concert, adhesion = preparer_un_billet_adherent()
    panier = PanierSession(requete_avec_session(creer_utilisateur()))
    panier.add_membership(adhesion.tarif.uuid)

    panier.add_ticket(concert.evenement.uuid, concert.tarif.uuid, qty=1)

    assert panier.count() == 2


def test_retirer_l_adhesion_fait_refuser_le_tarif_adherent_au_paiement(lieu):
    """
    Adhésion + tarif adhérent, puis l'adhésion est retirée : au paiement, le tarif adhérent
    est refusé et retiré du panier (le « bug connu » est rattrapé ici).
    / Membership + members-only price, then the membership is removed: at checkout the price
    is refused and removed from the cart.
    """
    from BaseBillet.services_panier import PanierSession

    concert, adhesion = preparer_un_billet_adherent()
    panier = PanierSession(requete_avec_session(creer_utilisateur()))
    panier.add_membership(adhesion.tarif.uuid)
    panier.add_ticket(concert.evenement.uuid, concert.tarif.uuid, qty=1)
    panier.remove_item(0)

    erreurs_de_validation = panier.revalidate_all()

    assert len(erreurs_de_validation) == 1
    assert panier.is_empty()


def test_retirer_puis_remettre_l_adhesion_garde_le_panier_valide(lieu):
    """
    Adhésion + tarif adhérent, adhésion retirée puis remise (elle passe en fin de panier) :
    le panier reste valide au paiement.
    / Membership + members-only price, membership removed then re-added (now last): the cart
    stays valid at checkout.
    """
    from BaseBillet.services_panier import PanierSession

    concert, adhesion = preparer_un_billet_adherent()
    panier = PanierSession(requete_avec_session(creer_utilisateur()))
    panier.add_membership(adhesion.tarif.uuid)
    panier.add_ticket(concert.evenement.uuid, concert.tarif.uuid, qty=1)
    panier.remove_item(0)
    panier.add_membership(adhesion.tarif.uuid)

    erreurs_de_validation = panier.revalidate_all()

    assert erreurs_de_validation == []
    assert sorted(item["type"] for item in panier.items()) == ["membership", "ticket"]


def test_revalidate_all_retire_un_tarif_depublie_et_garde_le_reste(lieu):
    """Tarif dépublié entre l'ajout et le paiement : une erreur, l'item est retiré, l'autre reste.
    / Price unpublished between add and checkout: one error, item removed, the other stays."""
    from BaseBillet.services_panier import PanierSession

    concert = creer_evenement_avec_tarif(prix="10.00")
    adhesion = creer_adhesion()
    panier = PanierSession(requete_avec_session(creer_utilisateur()))
    panier.add_ticket(concert.evenement.uuid, concert.tarif.uuid, qty=1)
    panier.add_membership(adhesion.tarif.uuid)
    concert.tarif.publish = False
    concert.tarif.save()

    erreurs_de_validation = panier.revalidate_all()

    assert len(erreurs_de_validation) == 1
    assert [item["type"] for item in panier.items()] == ["membership"]


def test_revalidate_all_detecte_une_jauge_saturee_entre_l_ajout_et_le_paiement(lieu):
    """Jauge de 3, 2 billets au panier, puis 2 billets vendus à un autre : refusé au paiement.
    / Capacity 3, 2 tickets in the cart, then 2 sold to someone else: refused at checkout."""
    from BaseBillet.services_panier import PanierSession
    from fabriques_panier import creer_un_billet_deja_vendu

    concert = creer_evenement_avec_tarif(prix="10.00", jauge_max=3)
    panier = PanierSession(requete_avec_session())
    panier.add_ticket(concert.evenement.uuid, concert.tarif.uuid, qty=2)
    autre_acheteur = creer_utilisateur()
    creer_un_billet_deja_vendu(autre_acheteur, concert)
    creer_un_billet_deja_vendu(autre_acheteur, concert)

    erreurs_de_validation = panier.revalidate_all()

    assert len(erreurs_de_validation) == 1
    assert panier.is_empty()


def test_calcul_total_centimes_prend_le_montant_saisi_d_un_prix_libre(lieu):
    """Prix libre saisi à 12,50 € × 2 : 2 500 centimes.
    / Free price typed at 12.50 € × 2: 2,500 cents."""
    from BaseBillet.services_panier import PanierSession

    concert = creer_evenement_avec_tarif(prix="5.00", prix_libre=True)
    panier = PanierSession(requete_avec_session(creer_utilisateur()))
    panier.add_ticket(
        concert.evenement.uuid, concert.tarif.uuid, qty=2, custom_amount="12.50"
    )

    assert panier.calcul_total_centimes() == 2500
