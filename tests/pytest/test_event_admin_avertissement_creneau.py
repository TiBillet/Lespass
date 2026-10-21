"""
Admin des événements : avertissements quand le créneau est déjà occupé.
/ Event admin: warnings when the time slot is already taken.

LOCALISATION : tests/pytest/test_event_admin_avertissement_creneau.py

Code testé : Administration/admin_tenant.py, EventAdmin._avertir_si_le_creneau_est_deja_occupe()
appelée par EventAdmin.save_model() juste après l'enregistrement.

Ce sont des avertissements (messages.warning), jamais des erreurs : l'événement est
enregistré quoi qu'il arrive.

Les dates sont en 2035 : loin des événements de démo du tenant, qui pourraient
sinon chevaucher ceux des tests (l'avertissement 3 regarde TOUS les événements).
Chaque test est marqué `django_db` : transaction annulée à la fin.
"""
import datetime

import pytest
from django.contrib import messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory
from django.utils import timezone
from django_tenants.utils import tenant_context

from fabriques_panier import creer_ressource_avec_tarif, creer_utilisateur

pytestmark = pytest.mark.django_db

JOUR_DES_TESTS = datetime.date(2035, 3, 5)


@pytest.fixture
def lieu(tenant):
    """Le tenant courant, avec une ressource réservable. / The tenant, with a bookable resource."""
    with tenant_context(tenant):
        yield creer_ressource_avec_tarif().ressource


def a_l_heure(heure, minute=0):
    """Le jour des tests à l'heure donnée, au fuseau du lieu. / Test day at the given time."""
    from BaseBillet.models import Configuration

    fuseau_du_lieu = Configuration.get_solo().get_tzinfo()
    return timezone.make_aware(
        datetime.datetime.combine(JOUR_DES_TESTS, datetime.time(heure, minute)), fuseau_du_lieu,
    )


def creer_evenement(nom, debut, fin=None, ressource=None, parent=None):
    from BaseBillet.models import Event

    return Event.objects.create(
        name=nom,
        datetime=debut,
        end_datetime=fin,
        jauge_max=50,
        ressource_bloquee=ressource,
        parent=parent,
    )


def avertissements_apres_enregistrement(evenement):
    """
    Lance la vérification de l'admin sur l'événement et rend les textes des
    avertissements produits.
    / Runs the admin check on the event and returns the warning texts.
    """
    from Administration.admin_tenant import EventAdmin, staff_admin_site
    from BaseBillet.models import Event

    requete = RequestFactory().post("/admin/BaseBillet/event/add/")
    requete.session = {}
    requete._messages = FallbackStorage(requete)

    EventAdmin(Event, staff_admin_site)._avertir_si_le_creneau_est_deja_occupe(requete, evenement)

    textes = []
    for message in requete._messages:
        assert message.level == messages.WARNING
        textes.append(str(message))
    return textes


def test_l_enregistrement_dans_l_admin_declenche_l_avertissement(lieu):
    # Passe par save_model, le vrai point d'entrée de l'admin : sans l'appel à la
    # vérification dans save_model, aucun avertissement n'apparaîtrait.
    # / Goes through save_model, the admin's real entry point.
    from Administration.admin_tenant import EventAdmin, staff_admin_site
    from BaseBillet.models import Event

    creer_evenement("TEST marché", a_l_heure(9), a_l_heure(11))
    evenement = creer_evenement("TEST concert", a_l_heure(10), a_l_heure(12))

    requete = RequestFactory().post("/admin/BaseBillet/event/add/")
    requete.session = {}
    requete._messages = FallbackStorage(requete)
    EventAdmin(Event, staff_admin_site).save_model(requete, evenement, form=None, change=True)

    avertissements = [str(message) for message in requete._messages]
    assert len(avertissements) == 1
    assert "TEST marché" in avertissements[0]


def test_les_actions_benevoles_d_un_autre_evenement_ne_donnent_aucun_avertissement(lieu):
    from BaseBillet.models import Event

    autre_evenement = creer_evenement("TEST marché", a_l_heure(8), a_l_heure(18))
    action_de_l_autre_evenement = creer_evenement(
        "TEST buvette du marché", a_l_heure(10), a_l_heure(12), parent=autre_evenement,
    )
    Event.objects.filter(pk=action_de_l_autre_evenement.pk).update(categorie=Event.ACTION)
    evenement = creer_evenement("TEST concert", a_l_heure(10), a_l_heure(12))

    avertissements = avertissements_apres_enregistrement(evenement)

    # Seul le marché lui-même est cité, pas son action bénévole.
    # / Only the market itself is cited, not its volunteer action.
    assert len(avertissements) == 1
    assert "TEST marché" in avertissements[0]
    assert "TEST buvette du marché" not in avertissements[0]


def test_une_ressource_deja_reservee_sur_le_creneau_donne_un_avertissement(lieu):
    from booking.models import Booking

    personne_qui_reserve = creer_utilisateur(prenom="Ada", nom="Lovelace")
    Booking.objects.create(
        resource=lieu,
        user=personne_qui_reserve,
        start_datetime=a_l_heure(10),
        slot_duration_minutes=60,
        slot_count=1,
        status=Booking.FREERES_USERACTIV,
    )
    evenement = creer_evenement("TEST concert", a_l_heure(10, 30), a_l_heure(12), ressource=lieu)

    avertissements = avertissements_apres_enregistrement(evenement)

    assert len(avertissements) == 1
    assert "déjà réservée" in avertissements[0]
    assert "Ada Lovelace" in avertissements[0]


def test_une_ressource_deja_bloquee_par_un_autre_evenement_donne_un_seul_avertissement(lieu):
    creer_evenement("TEST répétition", a_l_heure(9), a_l_heure(11), ressource=lieu)
    evenement = creer_evenement("TEST concert", a_l_heure(10), a_l_heure(12), ressource=lieu)

    avertissements = avertissements_apres_enregistrement(evenement)

    # L'autre événement est cité pour la ressource, pas une seconde fois comme
    # « autre événement sur le créneau ».
    # / Cited once, for the resource, not again as "another event".
    assert len(avertissements) == 1
    assert "déjà bloquée" in avertissements[0]
    assert "TEST répétition" in avertissements[0]


def test_un_autre_evenement_sur_le_meme_creneau_donne_un_avertissement(lieu):
    creer_evenement("TEST marché", a_l_heure(9), a_l_heure(11))
    evenement = creer_evenement("TEST concert", a_l_heure(10), a_l_heure(12))

    avertissements = avertissements_apres_enregistrement(evenement)

    assert len(avertissements) == 1
    assert "D'autres événements" in avertissements[0]
    assert "TEST marché" in avertissements[0]


def test_un_evenement_sans_date_de_fin_a_la_meme_heure_donne_un_avertissement(lieu):
    creer_evenement("TEST marché", a_l_heure(10))
    evenement = creer_evenement("TEST concert", a_l_heure(10))

    avertissements = avertissements_apres_enregistrement(evenement)

    assert len(avertissements) == 1
    assert "TEST marché" in avertissements[0]


def test_des_creneaux_qui_se_suivent_sans_se_chevaucher_ne_donnent_aucun_avertissement(lieu):
    from booking.models import Booking

    Booking.objects.create(
        resource=lieu,
        user=creer_utilisateur(),
        start_datetime=a_l_heure(9),
        slot_duration_minutes=60,
        slot_count=1,
        status=Booking.FREERES_USERACTIV,
    )
    creer_evenement("TEST répétition", a_l_heure(8), a_l_heure(10), ressource=lieu)
    creer_evenement("TEST marché", a_l_heure(12), a_l_heure(14))
    evenement = creer_evenement("TEST concert", a_l_heure(10), a_l_heure(12), ressource=lieu)

    assert avertissements_apres_enregistrement(evenement) == []


def test_les_actions_benevoles_de_l_evenement_ne_donnent_aucun_avertissement(lieu):
    from BaseBillet.models import Event

    parent = creer_evenement("TEST festival", a_l_heure(10), a_l_heure(18))
    premiere_action = creer_evenement("TEST buvette", a_l_heure(10), a_l_heure(12), parent=parent)
    creer_evenement("TEST billetterie", a_l_heure(11), a_l_heure(13), parent=parent)
    Event.objects.filter(pk__in=[premiere_action.pk]).update(categorie=Event.ACTION)

    # Ni le parent face à ses actions, ni une action face à son parent et ses sœurs.
    # / Neither the parent against its actions, nor an action against its family.
    assert avertissements_apres_enregistrement(parent) == []
    assert avertissements_apres_enregistrement(premiere_action) == []
