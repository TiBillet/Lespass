"""
Tests de la vue publique de liste des ressources de réservation.
/ Tests for the public resource list view.

LOCALISATION : booking/tests/test_views_public.py

Couvre les cas définis dans le plan de test session 7 :
- Accès public sans authentification (spec §4.4)
- Retour HTML valide
- Filtre par tag via paramètre URL
- Ressource sans créneaux → grisée
- Créneau complet (capacité = 0) → marqué indisponible
- Ressources groupées → nom du groupe visible dans la page (spec §3.1.2)
- Ressource sans groupe → visible dans la section sans-groupe

/ Covers the test plan session 7 cases:
- Public access without authentication (spec §4.4)
- Valid HTML response
- Tag filtering via URL parameter
- Resource with no slots → greyed out
- Full slot (capacity = 0) → marked unavailable
- Grouped resources → group name visible in the page (spec §3.1.2)
- Resource without group → visible in the ungrouped section

Lancement / Run:
    docker exec lespass_django poetry run pytest \
        booking/tests/test_views_public.py -v
"""
import datetime
import sys
import os

sys.path.insert(0, '/DjangoFiles')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'TiBillet.settings')

import django
django.setup()

import pytest
from django.test import Client as DjangoClient
from django.utils import timezone
from django_tenants.utils import schema_context


TEST_PREFIX    = '[test_booking_views_public]'
TENANT_SCHEMA  = 'lespass'
HOST           = 'lespass.tibillet.localhost'
URL_PAGE_ACCUEIL = '/booking/'


# ─── Helpers ────────────────────────────────────────────────────────────────

def _prochain_jour_semaine(numero_jour):
    """
    Retourne la prochaine occurrence du jour de la semaine donné.
    / Returns the next occurrence of the given weekday.

    numero_jour suit la convention Python : 0 = lundi, 6 = dimanche.
    Si aujourd'hui est ce jour, retourne la semaine prochaine.
    / numero_jour follows Python convention: 0 = Monday, 6 = Sunday.
    If today is that weekday, returns next week.

    :param numero_jour: int — 0 (lundi) à 6 (dimanche)
    :return: datetime.date
    """
    aujourd_hui = datetime.date.today()
    jours_avant = numero_jour - aujourd_hui.weekday()
    if jours_avant <= 0:
        jours_avant += 7
    return aujourd_hui + datetime.timedelta(days=jours_avant)


# ─── Fixtures de session (héritage conftest.py) ──────────────────────────────

@pytest.fixture(scope="session")
def django_db_setup():
    """Pas de création de test database — utilise la base dev existante.
    / Skip test database creation — use the existing dev database.
    """
    pass


@pytest.fixture(autouse=True, scope="session")
def _enable_db_access_for_all(django_db_blocker):
    """Désactiver le bloqueur d'accès DB de pytest-django.
    / Disable pytest-django's database blocker.
    """
    django_db_blocker.unblock()
    yield
    django_db_blocker.restore()


# ─── Fixture : tenant ────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def tenant():
    """Le tenant 'lespass'. / The 'lespass' tenant."""
    from Customers.models import Client

    return Client.objects.get(schema_name=TENANT_SCHEMA)


# ─── Fixture : client HTTP anonyme ───────────────────────────────────────────

@pytest.fixture(scope="module")
def client_anonyme():
    """
    Client Django anonyme (non authentifié) configuré pour le tenant lespass.
    / Anonymous (unauthenticated) Django test client configured for the lespass tenant.

    L'en-tête HTTP_HOST route la requête vers le bon tenant dans l'architecture
    multi-tenant de TiBillet.
    / The HTTP_HOST header routes the request to the correct tenant in TiBillet's
    multi-tenant architecture.
    """
    return DjangoClient(HTTP_HOST=HOST)


# ─── Fixtures : données de test ──────────────────────────────────────────────

@pytest.fixture(scope="module")
def ressource_avec_tag_salle(tenant):
    """
    Ressource avec le tag 'salle' pour tester le filtre par tag.
    / Resource tagged 'salle' for tag filter tests.

    LOCALISATION : booking/tests/test_views_public.py
    """
    from booking.models import Calendar, WeeklyOpening, Resource

    with schema_context(TENANT_SCHEMA):
        calendrier, _cree = Calendar.objects.get_or_create(
            name=f'{TEST_PREFIX} Calendrier Salle',
        )
        planning_semaine, _cree = WeeklyOpening.objects.get_or_create(
            name=f'{TEST_PREFIX} Planning Salle',
        )
        ressource, _cree = Resource.objects.get_or_create(
            name=f'{TEST_PREFIX} Salle de Réunion',
            defaults={
                'calendar':        calendrier,
                'weekly_opening':  planning_semaine,
                'tags':            ['salle'],
            },
        )
        return ressource


@pytest.fixture(scope="module")
def ressource_avec_tag_machine(tenant):
    """
    Ressource avec le tag 'machine' pour tester que le filtre exclut les ressources
    qui ne correspondent pas au tag demandé.
    / Resource tagged 'machine' for testing that the filter excludes
    non-matching resources.

    LOCALISATION : booking/tests/test_views_public.py
    """
    from booking.models import Calendar, WeeklyOpening, Resource

    with schema_context(TENANT_SCHEMA):
        calendrier, _cree = Calendar.objects.get_or_create(
            name=f'{TEST_PREFIX} Calendrier Machine',
        )
        planning_semaine, _cree = WeeklyOpening.objects.get_or_create(
            name=f'{TEST_PREFIX} Planning Machine',
        )
        ressource, _cree = Resource.objects.get_or_create(
            name=f'{TEST_PREFIX} Imprimante 3D',
            defaults={
                'calendar':        calendrier,
                'weekly_opening':  planning_semaine,
                'tags':            ['machine'],
            },
        )
        return ressource


@pytest.fixture(scope="module")
def ressource_sans_creneaux(tenant):
    """
    Ressource sans créneaux disponibles : WeeklyOpening sans aucun OpeningEntry.
    / Resource with no available slots: WeeklyOpening with no OpeningEntry.

    LOCALISATION : booking/tests/test_views_public.py

    Un WeeklyOpening vide produit un ensemble E = {} (aucun créneau théorique).
    La ressource doit apparaître dans la page mais grisée (spec §4.4).
    / An empty WeeklyOpening produces E = {} (no theoretical slots).
    The resource must appear in the page but greyed out (spec §4.4).
    """
    from booking.models import Calendar, WeeklyOpening, Resource

    with schema_context(TENANT_SCHEMA):
        calendrier, _cree = Calendar.objects.get_or_create(
            name=f'{TEST_PREFIX} Calendrier Vide',
        )
        # Pas d'OpeningEntry ajouté — planning vide → aucun créneau.
        # / No OpeningEntry added — empty schedule → no slots.
        planning_semaine, _cree = WeeklyOpening.objects.get_or_create(
            name=f'{TEST_PREFIX} Planning Vide',
        )
        ressource, _cree = Resource.objects.get_or_create(
            name=f'{TEST_PREFIX} Ressource Sans Créneau',
            defaults={
                'calendar':       calendrier,
                'weekly_opening': planning_semaine,
            },
        )
        return ressource


@pytest.fixture(scope="module")
def ressource_avec_creneau_complet(tenant):
    """
    Ressource avec un seul créneau entièrement réservé : capacité 1, 1 réservation.
    / Resource with a single slot fully booked: capacity 1, 1 confirmed booking.

    LOCALISATION : booking/tests/test_views_public.py

    Le créneau est le prochain lundi à 10:00–11:00.
    Avec capacity=1 et 1 réservation confirmée, remaining_capacity=0.
    Ce créneau doit être marqué indisponible sur la page publique (spec §4.4).
    / The slot is next Monday at 10:00–11:00.
    With capacity=1 and 1 confirmed booking, remaining_capacity=0.
    This slot must be marked unavailable on the public page (spec §4.4).
    """
    from booking.models import (
        Calendar, WeeklyOpening, Resource, OpeningEntry, Booking,
    )
    from AuthBillet.models import TibilletUser

    with schema_context(TENANT_SCHEMA):
        utilisateur = (
            TibilletUser.objects.filter(is_superuser=True).first()
            or TibilletUser.objects.filter(is_active=True).first()
        )
        if utilisateur is None:
            raise RuntimeError(
                'Aucun utilisateur trouvé dans le tenant lespass. '
                'Veuillez créer un compte utilisateur.'
            )

        calendrier, _cree = Calendar.objects.get_or_create(
            name=f'{TEST_PREFIX} Calendrier Complet',
        )
        planning_semaine, _cree = WeeklyOpening.objects.get_or_create(
            name=f'{TEST_PREFIX} Planning Complet',
        )
        ressource, _cree = Resource.objects.get_or_create(
            name=f'{TEST_PREFIX} Ressource Complète',
            defaults={
                'calendar':       calendrier,
                'weekly_opening': planning_semaine,
                'capacity':       1,
            },
        )

        # Créneau récurrent : chaque lundi à 10:00, durée 60 min.
        # / Recurring slot: every Monday at 10:00, 60-minute duration.
        OpeningEntry.objects.get_or_create(
            weekly_opening=planning_semaine,
            weekday=0,  # Lundi / Monday
            start_time=datetime.time(10, 0),
            defaults={
                'slot_duration_minutes': 60,
                'slot_count':            1,
            },
        )

        # Réservation sur le prochain lundi.
        # Si la ressource a déjà des réservations de tests (run précédent sans
        # nettoyage), on les supprime d'abord pour recréer une réservation fraîche.
        # / Booking on next Monday.
        # If the resource already has test bookings (previous run without cleanup),
        # we delete them first to create a fresh booking.
        Booking.objects.filter(resource=ressource).delete()

        prochain_lundi   = _prochain_jour_semaine(numero_jour=0)  # 0 = lundi
        heure_debut      = datetime.time(10, 0)
        fuseau_horaire   = timezone.get_current_timezone()

        debut_datetime = timezone.make_aware(
            datetime.datetime.combine(prochain_lundi, heure_debut),
            fuseau_horaire,
        )
        Booking.objects.create(
            resource              = ressource,
            user                  = utilisateur,
            start_datetime        = debut_datetime,
            slot_duration_minutes = 60,
            slot_count            = 1,
            status                = Booking.STATUS_CONFIRMED,
        )

        return ressource


# ─── Fixture de nettoyage ────────────────────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def nettoyage_donnees_de_test(tenant):
    """
    Supprime toutes les données de test après le module.
    / Deletes all test data after the module.

    LOCALISATION : booking/tests/test_views_public.py

    Ordre de suppression (on_delete=PROTECT — pas de cascade) :
    Booking → Resource → OpeningEntry → WeeklyOpening → ClosedPeriod → Calendar
    / Deletion order (on_delete=PROTECT — no cascade):
    Booking → Resource → OpeningEntry → WeeklyOpening → ClosedPeriod → Calendar
    """
    yield

    with schema_context(TENANT_SCHEMA):
        from booking.models import (
            Booking, Resource, ResourceGroup, OpeningEntry, WeeklyOpening,
            ClosedPeriod, Calendar,
        )

        # Les Booking n'ont pas de champ 'name' — on filtre via la resource.
        # / Bookings have no 'name' field — filter via the resource.
        Booking.objects.filter(
            resource__name__startswith=TEST_PREFIX,
        ).delete()
        # Resource avant ResourceGroup : on_delete=PROTECT empêche l'inverse.
        # / Resource before ResourceGroup: on_delete=PROTECT prevents the reverse.
        Resource.objects.filter(name__startswith=TEST_PREFIX).delete()
        ResourceGroup.objects.filter(name__startswith=TEST_PREFIX).delete()
        OpeningEntry.objects.filter(
            weekly_opening__name__startswith=TEST_PREFIX,
        ).delete()
        WeeklyOpening.objects.filter(name__startswith=TEST_PREFIX).delete()
        ClosedPeriod.objects.filter(
            calendar__name__startswith=TEST_PREFIX,
        ).delete()
        Calendar.objects.filter(name__startswith=TEST_PREFIX).delete()


# ─── Tests ──────────────────────────────────────────────────────────────────

def test_resource_list_accessible_without_authentication(client_anonyme):
    """
    La page publique de liste des ressources est accessible sans authentification.
    / The public resource list page is accessible without authentication.

    LOCALISATION : booking/tests/test_views_public.py

    Spec §4.4 : « Accessible without login ».
    Un visiteur anonyme reçoit HTTP 200 — pas de redirection vers le login (301/302).
    / Spec §4.4: "Accessible without login".
    An anonymous visitor receives HTTP 200 — no redirect to login (301/302).
    """
    # Requête GET anonyme sur la liste des ressources.
    # / Anonymous GET request on the resource list.
    reponse = client_anonyme.get(URL_PAGE_ACCUEIL)

    # La page doit répondre 200, pas 302 (redirect vers login).
    # / Page must respond 200, not 302 (redirect to login).
    assert reponse.status_code == 200


def test_resource_list_returns_html_200(client_anonyme):
    """
    La vue retourne du HTML avec le statut 200.
    / The view returns HTML with status 200.

    LOCALISATION : booking/tests/test_views_public.py

    On vérifie que Content-Type est text/html et que la réponse
    contient une balise <html>.
    / Verifies Content-Type is text/html and the response contains
    an <html> tag.
    """
    reponse = client_anonyme.get(URL_PAGE_ACCUEIL)

    assert reponse.status_code == 200

    # Le Content-Type doit être text/html.
    # / Content-Type must be text/html.
    assert 'text/html' in reponse.get('Content-Type', '')

    # La réponse doit contenir une balise HTML racine.
    # / Response must contain a root HTML tag.
    contenu = reponse.content.decode('utf-8')
    assert '<html' in contenu


def test_resource_list_filters_by_tag(
    client_anonyme,
    ressource_avec_tag_salle,
    ressource_avec_tag_machine,
):
    """
    Le paramètre URL ?tag=<tag> filtre les ressources affichées.
    / The ?tag=<tag> URL parameter filters the displayed resources.

    LOCALISATION : booking/tests/test_views_public.py

    Spec §4.4 : « URL parameters allow filtering by tag ».
    Avec ?tag=salle, seule la ressource taguée 'salle' apparaît.
    La ressource taguée 'machine' ne doit pas être présente.
    / Spec §4.4: "URL parameters allow filtering by tag".
    With ?tag=salle, only the resource tagged 'salle' appears.
    The resource tagged 'machine' must not be present.
    """
    # Requête filtrée sur le tag 'salle'.
    # / Request filtered on the 'salle' tag.
    reponse = client_anonyme.get(URL_PAGE_ACCUEIL, {'tag': 'salle'})

    assert reponse.status_code == 200
    contenu = reponse.content.decode('utf-8')

    nom_salle   = ressource_avec_tag_salle.name    # '[test_...] Salle de Réunion'
    nom_machine = ressource_avec_tag_machine.name  # '[test_...] Imprimante 3D'

    # La ressource avec le tag 'salle' doit être présente dans la réponse.
    # / The resource with the 'salle' tag must be present in the response.
    assert nom_salle in contenu

    # La ressource avec le tag 'machine' ne doit PAS être présente.
    # / The resource with the 'machine' tag must NOT be present.
    assert nom_machine not in contenu


def test_resource_with_no_availability_appears_greyed_out(
    client_anonyme,
    ressource_sans_creneaux,
):
    """
    Une ressource sans créneaux disponibles apparaît dans la liste mais grisée.
    / A resource with no available slots appears in the list but greyed out.

    LOCALISATION : booking/tests/test_views_public.py

    Spec §4.4 : « Resources with no upcoming availability are shown but greyed out ».
    La ressource est présente (pas cachée), mais son card porte
    l'attribut data-testid="booking-resource-card-greyed".
    / Spec §4.4: "Resources with no upcoming availability are shown but greyed out".
    The resource is present (not hidden), but its card carries
    the attribute data-testid="booking-resource-card-greyed".
    """
    reponse = client_anonyme.get(URL_PAGE_ACCUEIL)

    assert reponse.status_code == 200
    contenu = reponse.content.decode('utf-8')

    nom_ressource = ressource_sans_creneaux.name

    # La ressource doit être visible dans la page (pas cachée).
    # / The resource must be visible in the page (not hidden).
    assert nom_ressource in contenu

    # La card doit porter le marqueur "grisée".
    # / The card must carry the "greyed out" marker.
    assert 'data-testid="booking-resource-card-greyed"' in contenu


def test_full_slot_appears_as_unavailable(
    client_anonyme,
    ressource_avec_creneau_complet,
):
    """
    Un créneau dont la capacité restante est 0 est affiché comme indisponible.
    / A slot with remaining capacity = 0 is displayed as unavailable.

    LOCALISATION : booking/tests/test_views_public.py

    Spec §4.4 : « Slots already full (remaining_capacity = 0) are shown as
    unavailable ».
    Le créneau est visible dans la page, mais porte l'attribut
    data-testid="booking-slot-unavailable".
    / Spec §4.4: "Slots already full (remaining_capacity = 0) are shown as
    unavailable".
    The slot is visible in the page, but carries the attribute
    data-testid="booking-slot-unavailable".
    """
    reponse = client_anonyme.get(URL_PAGE_ACCUEIL)

    assert reponse.status_code == 200
    contenu = reponse.content.decode('utf-8')

    nom_ressource = ressource_avec_creneau_complet.name

    # La ressource doit être présente dans la page.
    # / The resource must be present in the page.
    assert nom_ressource in contenu

    # Au moins un créneau doit être marqué indisponible.
    # / At least one slot must be marked unavailable.
    assert 'data-testid="booking-slot-unavailable"' in contenu


# ─── Fixture : groupe de ressources ─────────────────────────────────────────

@pytest.fixture(scope="module")
def groupe_avec_ressource(tenant):
    """
    Crée un ResourceGroup avec une ressource assignée.
    / Creates a ResourceGroup with one assigned resource.

    LOCALISATION : booking/tests/test_views_public.py

    Le groupe est purement présentationnel (spec §3.1.2) : la ressource
    est assignée via le FK group, sans logique de réservation sur le groupe.
    La ressource a un WeeklyOpening vide → aucun créneau, mais elle
    apparaît grisée sous le titre du groupe.
    / The group is purely presentational (spec §3.1.2): the resource is
    assigned via the group FK, with no booking logic on the group.
    The resource has an empty WeeklyOpening → no slots, but it appears
    greyed out under the group heading.
    """
    from booking.models import Calendar, WeeklyOpening, Resource, ResourceGroup

    with schema_context(TENANT_SCHEMA):
        groupe = ResourceGroup.objects.create(
            name=f'{TEST_PREFIX} Groupe Salles',
        )
        calendrier, _cree = Calendar.objects.get_or_create(
            name=f'{TEST_PREFIX} Calendrier Groupe',
        )
        planning_semaine, _cree = WeeklyOpening.objects.get_or_create(
            name=f'{TEST_PREFIX} Planning Groupe',
        )
        Resource.objects.get_or_create(
            name=f'{TEST_PREFIX} Ressource Du Groupe',
            defaults={
                'calendar':       calendrier,
                'weekly_opening': planning_semaine,
                'group':          groupe,
            },
        )
        return groupe


# ─── Tests : groupes de ressources ───────────────────────────────────────────

def test_group_name_appears_as_heading(client_anonyme, groupe_avec_ressource):
    """
    Le nom du ResourceGroup apparaît comme titre de section sur la page publique.
    / The ResourceGroup name appears as a section heading on the public page.

    LOCALISATION : booking/tests/test_views_public.py

    Spec §3.1.2 : « the public page shows resources grouped together ».
    Le nom du groupe doit être visible dans le HTML rendu.
    / Spec §3.1.2: "the public page shows resources grouped together".
    The group name must be visible in the rendered HTML.
    """
    reponse = client_anonyme.get(URL_PAGE_ACCUEIL)

    assert reponse.status_code == 200
    contenu = reponse.content.decode('utf-8')

    # Le nom du groupe doit apparaître comme titre de section.
    # / The group name must appear as a section heading.
    assert groupe_avec_ressource.name in contenu


def test_htmx_422_handler_present_in_response(client_anonyme):
    """
    Le gestionnaire htmx:beforeOnLoad est présent dans la réponse complète.
    / The htmx:beforeOnLoad handler is present in the full response.

    LOCALISATION : booking/tests/test_views_public.py

    Ce gestionnaire est déclaré dans les templates de base (reunion/base.html,
    faire_festival/base.html) et non dans les templates de vue booking (finding §17).
    Ce test vérifie que la factorisation est correcte : le HTML rendu par la
    vue inclut bien le gestionnaire hérité du template de base.
    / This handler is declared in the base templates (reunion/base.html,
    faire_festival/base.html) and not in the booking view templates (finding §17).
    This test verifies the refactoring is correct: the HTML rendered by the view
    includes the handler inherited from the base template.
    """
    reponse = client_anonyme.get(URL_PAGE_ACCUEIL)

    assert reponse.status_code == 200
    contenu = reponse.content.decode('utf-8')

    # Le gestionnaire doit être présent — hérité du template de base.
    # / The handler must be present — inherited from the base template.
    assert 'htmx:beforeOnLoad' in contenu


def test_ungrouped_resource_appears_individually(
    client_anonyme,
    ressource_sans_creneaux,
):
    """
    Une ressource sans groupe reste visible dans la section sans-groupe.
    / A resource without group remains visible in the ungrouped section.

    LOCALISATION : booking/tests/test_views_public.py

    Spec §3.1.2 : « A resource not assigned to any group is displayed
    individually on the public page ».
    Après la restructuration vue/template pour gérer les groupes, les
    ressources sans groupe doivent continuer à apparaître.
    / Spec §3.1.2: "A resource not assigned to any group is displayed
    individually on the public page".
    After refactoring view/template to handle groups, ungrouped resources
    must still appear.
    """
    reponse = client_anonyme.get(URL_PAGE_ACCUEIL)

    assert reponse.status_code == 200
    contenu = reponse.content.decode('utf-8')

    # La ressource sans groupe doit rester visible dans la page.
    # / The ungrouped resource must remain visible in the page.
    assert ressource_sans_creneaux.name in contenu
