"""
Calendrier d'une ressource : une semaine à la fois, rechargée en htmx.
/ Resource calendar: one week at a time, reloaded with htmx.

LOCALISATION : tests/pytest/test_booking_calendrier_semaine.py

Code testé / Tested code :
- booking/views.py : resource_page(), _semaine_affichee(), bug de minuit dans
  _build_calendar_weeks()
- booking/templates/booking/partials/resource_semaine.html

Spec : TECH_DOC/SESSIONS/TODO/BOOKING-pagination-htmx-calendrier.md

La ressource de test est ouverte tous les jours de 10 h à 18 h (créneaux d'une heure),
horizon de 28 jours (fabriques_panier.creer_ressource_avec_tarif).
Les dates sont calculées à partir du VRAI aujourd'hui, au fuseau du lieu : la vue n'a
pas de « maintenant » injectable, et patcher timezone.now toucherait tout Django.
Chaque test est marqué `django_db` : transaction annulée à la fin.
/ Dates come from the real today, in the venue timezone. Each test is rolled back.

Lancer / Run : make test ARGS="tests/pytest/test_booking_calendrier_semaine.py"
"""
import datetime
import re
from types import SimpleNamespace

import pytest
from django.test import Client, RequestFactory
from django.utils import timezone
from django_tenants.utils import tenant_context

from fabriques_panier import client_connecte, creer_ressource_avec_tarif, creer_utilisateur

pytestmark = pytest.mark.django_db

EN_TETE_DE_LA_ZONE = {"HTTP_HX_REQUEST": "true", "HTTP_HX_TARGET": "booking-calendrier-semaine"}


@pytest.fixture(autouse=True)
def _langue_par_defaut_apres_chaque_test():
    """Les tâches et signaux activent la langue du lieu sans la remettre (tests/PIEGES.md).
    / Tasks and signals activate the venue language without resetting it."""
    from django.utils import translation

    yield
    translation.deactivate()


def navigateur():
    """Client anonyme sur le lieu `lespass`, en français. / Anonymous client on `lespass`."""
    return Client(HTTP_HOST="lespass.tibillet.localhost", HTTP_ACCEPT_LANGUAGE="fr")


@pytest.fixture
def salle(tenant):
    """
    Une ressource ouverte tous les jours de 10 h à 18 h, et les repères de date du lieu.
    `salle.semaine(n)` rend le lundi dans n semaines.
    / A resource open every day 10-18, and the venue's date landmarks.
    """
    from BaseBillet.models import Configuration

    with tenant_context(tenant):
        location = creer_ressource_avec_tarif()
        fuseau_du_lieu = Configuration.get_solo().get_tzinfo()
        aujourd_hui = timezone.now().astimezone(fuseau_du_lieu).date()
        lundi_de_cette_semaine = aujourd_hui - datetime.timedelta(days=aujourd_hui.weekday())

        def semaine(nombre_de_semaines):
            return lundi_de_cette_semaine + datetime.timedelta(weeks=nombre_de_semaines)

        yield SimpleNamespace(
            ressource=location.ressource,
            tarif=location.tarif,
            fuseau_du_lieu=fuseau_du_lieu,
            aujourd_hui=aujourd_hui,
            semaine=semaine,
        )


def adresse_de_la_salle(salle, semaine=None):
    adresse = f"/booking/{salle.ressource.pk}/resource/"
    if semaine is not None:
        adresse += f"?semaine={semaine}"
    return adresse


def titre_affiche(page):
    """Le titre de la semaine affichée. / The displayed week title."""
    return re.search(r'data-testid="booking-calendar-week-label">([^<]*)<', page).group(1).strip()


def dates_des_creneaux_libres(page):
    """Les dates (AAAA-MM-JJ) des créneaux libres de la grille desktop.
    / Dates of the desktop grid's free slots."""
    dates = []
    for bloc in page.split('data-start-datetime="')[1:]:
        debut = bloc.split('"')[0]
        if 'data-testid="booking-calendar-slot-free"' in bloc.split(">")[0]:
            dates.append(datetime.date.fromisoformat(debut[:10]))
    return dates


# ---------------------------------------------------------------------------
# Choix de la semaine / Week choice
# ---------------------------------------------------------------------------

def test_sans_semaine_demandee_c_est_la_semaine_en_cours_sans_lien_precedent(salle):
    from booking.benevolat import titre_de_la_semaine

    page = navigateur().get(adresse_de_la_salle(salle)).content.decode()

    assert titre_affiche(page) == titre_de_la_semaine(salle.semaine(0))
    assert 'data-testid="booking-calendar-prev-week"' not in page
    assert 'data-testid="booking-calendar-next-week"' in page


def test_une_semaine_en_cours_vide_garde_sa_navigation_et_son_message(salle):
    """Une fermeture d'aujourd'hui à dimanche : la semaine en cours est vide, mais
    affichée quand même, avec le message et « Semaine suivante ».
    / Closed until Sunday: the empty current week still shows, with message and next link."""
    from booking.models import ClosedPeriod

    dimanche = salle.semaine(0) + datetime.timedelta(days=6)
    ClosedPeriod.objects.create(
        calendar=salle.ressource.calendar, start_date=salle.aujourd_hui, end_date=dimanche,
        label="Fermeture de test",
    )

    page = navigateur().get(adresse_de_la_salle(salle)).content.decode()

    assert 'data-testid="booking-calendar-empty-week"' in page
    assert "Aucun créneau cette semaine." in page
    assert 'id="booking-calendar"' in page
    assert 'data-testid="booking-calendar-next-week"' in page


def test_une_semaine_vide_demandee_garde_ses_deux_liens_et_son_message(salle):
    """Toute la semaine prochaine fermée, demandée par ?semaine= : message, deux liens de
    semaine, calendrier présent. Ne dépend pas du jour où le test tourne.
    / A fully closed week requested by ?semaine=: message, both links, calendar."""
    from booking.models import ClosedPeriod

    lundi = salle.semaine(1)
    ClosedPeriod.objects.create(
        calendar=salle.ressource.calendar, start_date=lundi,
        end_date=lundi + datetime.timedelta(days=6), label="Fermeture de test",
    )

    page = navigateur().get(adresse_de_la_salle(salle, lundi)).content.decode()

    assert 'data-testid="booking-calendar-empty-week"' in page
    assert 'id="booking-calendar"' in page
    assert 'data-testid="booking-calendar-prev-week"' in page
    assert 'data-testid="booking-calendar-next-week"' in page


def lien_de_semaine(page, testid):
    """Le href du lien de semaine (repli sans JS). / The week link href (no-JS fallback)."""
    return page.split(f'data-testid="{testid}"')[0].rsplit('href="', 1)[1].split('"')[0]


def test_un_mercredi_demande_donne_sa_semaine_et_son_lien_precedent_mene_a_la_semaine_en_cours(salle):
    """Semaine prochaine : son lien « précédente » existe (borne basse de D6) et mène
    à la semaine en cours. / Next week: its previous link leads to the current week."""
    from booking.benevolat import titre_de_la_semaine

    mercredi_de_la_semaine_prochaine = salle.semaine(1) + datetime.timedelta(days=2)

    page = navigateur().get(adresse_de_la_salle(salle, mercredi_de_la_semaine_prochaine)).content.decode()

    assert titre_affiche(page) == titre_de_la_semaine(salle.semaine(1))
    assert lien_de_semaine(page, "booking-calendar-prev-week").endswith(f"?semaine={salle.semaine(0)}")


def test_l_avant_derniere_semaine_a_un_lien_suivant_vers_la_derniere(salle):
    """Borne haute de D6 : sur l'avant-dernière semaine, « suivante » existe et mène à la
    dernière semaine réservable. / Upper bound of D6."""
    from booking.benevolat import lundi_de_la_semaine

    dernier_jour_reservable = salle.aujourd_hui + datetime.timedelta(
        days=salle.ressource.booking_horizon_days,
    )
    lundi_de_la_derniere_semaine = lundi_de_la_semaine(dernier_jour_reservable)
    lundi_de_l_avant_derniere_semaine = lundi_de_la_derniere_semaine - datetime.timedelta(days=7)

    page = navigateur().get(adresse_de_la_salle(salle, lundi_de_l_avant_derniere_semaine)).content.decode()

    assert lien_de_semaine(page, "booking-calendar-next-week").endswith(
        f"?semaine={lundi_de_la_derniere_semaine}"
    )


@pytest.mark.parametrize("valeur_illisible_ou_passee", ["abc", "2020-01-06"])
def test_une_semaine_illisible_ou_passee_retombe_sur_la_semaine_en_cours(salle, valeur_illisible_ou_passee):
    from booking.benevolat import titre_de_la_semaine

    page = navigateur().get(adresse_de_la_salle(salle, valeur_illisible_ou_passee)).content.decode()

    assert titre_affiche(page) == titre_de_la_semaine(salle.semaine(0))


def test_une_semaine_apres_l_horizon_donne_la_derniere_semaine_sans_lien_suivant(salle):
    from booking.benevolat import lundi_de_la_semaine, titre_de_la_semaine

    dernier_jour_reservable = salle.aujourd_hui + datetime.timedelta(
        days=salle.ressource.booking_horizon_days,
    )
    lundi_de_la_derniere_semaine = lundi_de_la_semaine(dernier_jour_reservable)

    page = navigateur().get(adresse_de_la_salle(salle, "2099-01-05")).content.decode()

    assert titre_affiche(page) == titre_de_la_semaine(lundi_de_la_derniere_semaine)
    assert 'data-testid="booking-calendar-next-week"' not in page


def test_la_fenetre_de_calcul_est_au_fuseau_du_lieu(salle):
    """
    Le moteur lit le fuseau dans window.start : une fenêtre en UTC décalerait les
    créneaux de la semaine en cours. On teste la fenêtre elle-même, car la semaine en
    cours peut n'avoir plus aucun créneau (dimanche soir).
    / The engine reads the timezone from window.start.
    """
    from booking.views import BookingViewSet

    requete = RequestFactory().get(adresse_de_la_salle(salle))
    with timezone.override(salle.fuseau_du_lieu):
        semaine = BookingViewSet()._semaine_affichee(requete, salle.ressource)

    debut_de_la_fenetre = semaine["fenetre"].start
    assert debut_de_la_fenetre.utcoffset() == datetime.datetime.now(salle.fuseau_du_lieu).utcoffset()
    assert str(debut_de_la_fenetre.tzinfo) == str(salle.fuseau_du_lieu)


# ---------------------------------------------------------------------------
# Contenu de la semaine / Week content
# ---------------------------------------------------------------------------

def test_la_page_ne_contient_que_les_creneaux_de_la_semaine(salle):
    """Semaine prochaine : 7 jours × 8 créneaux, tous dans cette semaine.
    / Next week: 7 days × 8 slots, all within that week."""
    lundi = salle.semaine(1)

    page = navigateur().get(adresse_de_la_salle(salle, lundi)).content.decode()

    dates = dates_des_creneaux_libres(page)
    assert len(dates) == 7 * 8
    for une_date in dates:
        assert lundi <= une_date <= lundi + datetime.timedelta(days=6)


def test_le_lien_de_semaine_recoit_la_zone_seule(salle):
    adresse = adresse_de_la_salle(salle, salle.semaine(1))

    zone = navigateur().get(adresse, **EN_TETE_DE_LA_ZONE).content.decode()
    page = navigateur().get(adresse).content.decode()

    assert "<html" not in zone
    assert zone.lstrip().startswith("<!--")
    assert 'id="booking-calendrier-semaine"' in zone
    assert 'data-testid="booking-resource-select"' not in zone
    assert "<html" in page
    assert 'data-testid="booking-resource-select"' in page


def test_un_creneau_qui_finit_a_minuit_tient_dans_la_grille(salle):
    """
    Chaque jour : une journée de 10 h à 18 h, puis une soirée de 18 h à minuit (comme la
    « Salle de résidence et concert » de la démo). La grille va de 10:00 à 24:00, soit
    29 lignes d'une demi-heure. Sans la correction, la soirée finissait « à 0 h » : la
    grille s'arrêtait à 18:00 (17 lignes) et la soirée débordait.
    Il faut les DEUX créneaux : seul, le créneau de minuit donne une heure de fin à 0,
    et le repli « 0 → 24 » de _build_calendar_weeks masque le bug.
    / A 10-18 slot plus an 18-24 slot: the grid runs 10:00 to 24:00 (29 rows).
    """
    from booking.models import OpeningEntry

    ouverture = salle.ressource.weekly_opening
    ouverture.opening_entries.update(slot_duration_minutes=480, slot_count=1)
    for jour_de_la_semaine in range(7):
        OpeningEntry.objects.create(
            weekly_opening=ouverture, weekday=jour_de_la_semaine,
            start_time=datetime.time(18, 0), slot_duration_minutes=360, slot_count=1,
        )

    page = navigateur().get(adresse_de_la_salle(salle, salle.semaine(1))).content.decode()

    assert page.count('data-testid="booking-calendar-hour-label"') == 29
    assert "24:00" in page
    # Vue mobile : une grille par jour, 7 jours × 29 lignes.
    # / Mobile view: one grid per day, 7 days × 29 rows.
    assert page.count('data-testid="booking-mobile-hour-label"') == 7 * 29


def test_une_suite_de_creneaux_s_arrete_au_dimanche_minuit(salle):
    """
    Décision du mainteneur (Q2) : une réservation de plusieurs créneaux d'affilée ne
    traverse pas le dimanche à minuit. Dimanche 23 h et lundi 0 h se suivent, mais dans
    la semaine du dimanche, le groupe s'arrête au lundi 0 h (data-group-end), et le
    créneau du lundi 0 h n'y apparaît pas.
    / A run of slots stops at Sunday midnight (data-group-end), Monday 0:00 is not shown.
    """
    from booking.models import OpeningEntry

    ouverture = salle.ressource.weekly_opening
    ouverture.opening_entries.all().delete()
    OpeningEntry.objects.create(
        weekly_opening=ouverture, weekday=OpeningEntry.SUNDAY,
        start_time=datetime.time(23, 0), slot_duration_minutes=60, slot_count=1,
    )
    OpeningEntry.objects.create(
        weekly_opening=ouverture, weekday=OpeningEntry.MONDAY,
        start_time=datetime.time(0, 0), slot_duration_minutes=60, slot_count=1,
    )
    lundi = salle.semaine(1)
    dimanche = lundi + datetime.timedelta(days=6)
    lundi_suivant = lundi + datetime.timedelta(days=7)

    page = navigateur().get(adresse_de_la_salle(salle, lundi)).content.decode()

    creneau_du_dimanche = page.split(f'data-start-datetime="{dimanche}T23:00:00"')[1].split(">")[0]
    assert f'data-group-end="{lundi_suivant}T00:00:00"' in creneau_du_dimanche
    assert f'data-start-datetime="{lundi_suivant}T00:00:00"' not in page


def test_un_creneau_au_panier_est_marque_dans_la_semaine(salle):
    lundi = salle.semaine(1)
    debut = datetime.datetime.combine(lundi, datetime.time(10, 0))
    client = client_connecte(creer_utilisateur())
    client.post(
        "/panier/add/resource/",
        {
            "resource": str(salle.ressource.pk),
            "price_uuid": str(salle.tarif.uuid),
            "start_datetime": debut.isoformat(),
            "end_time": (debut + datetime.timedelta(hours=1)).isoformat(),
            "firstname": "Ada",
            "lastname": "Lovelace",
        },
        HTTP_HX_REQUEST="true",
    )

    zone = client.get(adresse_de_la_salle(salle, lundi), **EN_TETE_DE_LA_ZONE).content.decode()

    creneau_au_panier = f'data-start-datetime="{debut.isoformat()}"'
    morceau = zone.split(creneau_au_panier)[1].split(">")[0]
    assert 'data-testid="booking-calendar-slot-cart"' in morceau


def test_un_creneau_bloque_par_un_evenement_est_complet(salle):
    from BaseBillet.models import Event

    lundi = salle.semaine(1)
    Event.objects.create(
        name="TEST concert dans la salle",
        datetime=timezone.make_aware(
            datetime.datetime.combine(lundi, datetime.time(10, 15)), salle.fuseau_du_lieu,
        ),
        end_datetime=timezone.make_aware(
            datetime.datetime.combine(lundi, datetime.time(10, 45)), salle.fuseau_du_lieu,
        ),
        ressource_bloquee=salle.ressource,
    )

    page = navigateur().get(adresse_de_la_salle(salle, lundi)).content.decode()

    assert page.count('data-testid="booking-calendar-slot-busy"') == 1
    assert len(dates_des_creneaux_libres(page)) == 7 * 8 - 1


# ---------------------------------------------------------------------------
# Infos admin : qui occupe le créneau / Admin info: who occupies the slot
# Code testé : booking/views.py, _ajouter_les_infos_admin_aux_creneaux()
#              booking/templates/booking/partials/infos_creneau_admin.html
# ---------------------------------------------------------------------------

def admin_du_lieu(tenant):
    """Un utilisateur admin du lieu `lespass`. / A venue admin user."""
    administrateur = creer_utilisateur(prenom="Admin", nom="DuLieu")
    administrateur.client_admin.add(tenant)
    return administrateur


def occuper_le_lundi_a_10h(salle):
    """
    Lundi prochain : un événement bloque 10 h - 11 h, une réservation occupe 11 h - 12 h.
    Rend (evenement, reservation).
    / Next Monday: an event blocks 10-11, a booking occupies 11-12.
    """
    from BaseBillet.models import Event
    from booking.models import Booking

    lundi = salle.semaine(1)
    dix_heures = timezone.make_aware(datetime.datetime.combine(lundi, datetime.time(10, 0)), salle.fuseau_du_lieu)
    onze_heures = timezone.make_aware(datetime.datetime.combine(lundi, datetime.time(11, 0)), salle.fuseau_du_lieu)

    evenement = Event.objects.create(
        name="TEST concert infos admin",
        datetime=dix_heures,
        end_datetime=onze_heures,
        jauge_max=80,
        ressource_bloquee=salle.ressource,
    )
    personne_qui_reserve = creer_utilisateur(prenom="Ada", nom="Lovelace")
    reservation = Booking.objects.create(
        resource=salle.ressource,
        user=personne_qui_reserve,
        start_datetime=onze_heures,
        slot_duration_minutes=60,
        slot_count=1,
        status=Booking.FREERES_USERACTIV,
    )
    return evenement, reservation


def test_un_admin_voit_l_evenement_et_la_reservation_qui_occupent_les_creneaux(salle, tenant):
    evenement, reservation = occuper_le_lundi_a_10h(salle)
    client = client_connecte(admin_du_lieu(tenant))

    page = client.get(adresse_de_la_salle(salle, salle.semaine(1))).content.decode()

    # Desktop et mobile : deux fenêtres de détail par créneau occupé.
    # / Desktop and mobile: two detail popovers per occupied slot.
    assert page.count('data-testid="booking-infos-creneau-admin"') == 4
    assert page.count('data-testid="booking-calendar-slot-infos-admin"') == 2
    # Créneaux complets : le bouton couvre tout le bloc (desktop et mobile).
    # / Full slots: the button covers the whole block (desktop and mobile).
    assert page.count("calendar-slot-infos-admin calendar-slot-infos-admin-bloc") == 4
    assert "TEST concert infos admin" in page
    assert "0 / 80" in page
    assert "Ada Lovelace" in page
    assert reservation.user.email in page


def test_un_admin_voit_dans_la_case_tous_les_evenements_qui_se_chevauchent(salle, tenant):
    # Lundi prochain, deux événements se chevauchent sur le créneau 10 h - 11 h.
    # La case doit écrire les DEUX titres, pas seulement le premier.
    # / Two events overlap the 10-11 slot: the cell must show BOTH titles.
    from BaseBillet.models import Event

    lundi = salle.semaine(1)

    def a_l_heure(heure, minute):
        return timezone.make_aware(
            datetime.datetime.combine(lundi, datetime.time(heure, minute)), salle.fuseau_du_lieu,
        )

    Event.objects.create(
        name="TEST premier evenement",
        datetime=a_l_heure(10, 0),
        end_datetime=a_l_heure(10, 40),
        jauge_max=50,
        ressource_bloquee=salle.ressource,
    )
    Event.objects.create(
        name="TEST second evenement",
        datetime=a_l_heure(10, 20),
        end_datetime=a_l_heure(11, 0),
        jauge_max=50,
        ressource_bloquee=salle.ressource,
    )
    client = client_connecte(admin_du_lieu(tenant))

    page = client.get(adresse_de_la_salle(salle, lundi)).content.decode()

    # Un seul créneau occupé, mais deux lignes dans sa case (desktop et mobile).
    # / One occupied slot, two lines in its cell (desktop and mobile).
    assert page.count('data-testid="booking-calendar-slot-busy"') == 1
    for titre in ["TEST premier evenement", "TEST second evenement"]:
        assert page.count(f'data-testid="booking-calendar-slot-occupant">{titre}</span>') == 1
        assert page.count(f'data-testid="booking-mobile-slot-occupant">{titre}</span>') == 1
    assert "Événements qui bloquent la ressource" in page


@pytest.mark.parametrize("connecte", [False, True])
def test_un_visiteur_ou_un_membre_non_admin_ne_voit_pas_qui_occupe_les_creneaux(salle, connecte):
    evenement, reservation = occuper_le_lundi_a_10h(salle)
    client = client_connecte(creer_utilisateur()) if connecte else navigateur()

    page = client.get(adresse_de_la_salle(salle, salle.semaine(1))).content.decode()

    assert page.count('data-testid="booking-calendar-slot-busy"') == 2
    assert 'data-testid="booking-infos-creneau-admin"' not in page
    assert "TEST concert infos admin" not in page
    assert reservation.user.email not in page
