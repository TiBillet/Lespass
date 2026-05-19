"""
Tests smoke S1 — modele ClotureCaisse + admin Unfold.
/ Smoke tests S1 — ClotureCaisse model + Unfold admin.

LOCALISATION : tests/pytest/test_comptabilite_admin.py

S1 livre uniquement le squelette : modele, migration, admin liste vide,
entree sidebar. Ces tests verifient qu'on peut creer une cloture en base
et que la page admin se charge.
/ S1 only delivers the skeleton: model, migration, empty admin list,
sidebar entry. These tests verify we can create a closure and that
the admin page loads.

NOTE TECHNIQUE : ces tests reutilisent la base de donnees dev existante
(pattern V2 onboard — pas de test DB creee a chaque run). Obligatoire
car django-tenants necessite un schema tenant reel pour les modeles
TENANT_APPS.
/ TECHNICAL NOTE: these tests reuse the existing dev DB (onboard V2 pattern
— no test DB created per run). Required because django-tenants needs a real
tenant schema for TENANT_APPS models.
"""
import pytest
from django_tenants.utils import tenant_context


# ---------------------------------------------------------------------------
# Override : reutiliser la DB dev au lieu d'une test DB temporaire.
# / Override: reuse the dev DB instead of a temporary test DB.
# Meme pattern que onboard/tests/conftest.py.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def django_db_setup():
    """
    Pas de creation de test DB — on utilise la DB dev existante.
    / No test DB creation — we use the existing dev DB.
    """
    pass


@pytest.fixture(autouse=True, scope="session")
def _enable_db_access(django_db_blocker):
    """
    Desactive le bloqueur d'acces DB de pytest-django pour toute la session.
    / Disable pytest-django's DB access blocker for the whole session.
    """
    django_db_blocker.unblock()
    yield
    django_db_blocker.restore()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.django_db


def test_app_comptabilite_dans_installed_apps():
    """
    L'app comptabilite est bien chargee par Django (presente dans INSTALLED_APPS).
    / The comptabilite app is properly loaded by Django.
    """
    from django.apps import apps
    assert apps.is_installed("comptabilite"), (
        "L'app 'comptabilite' n'est pas dans INSTALLED_APPS"
    )


def test_modele_cloturecaisse_creation_minimale():
    """
    On peut creer une ClotureCaisse minimale dans un schema tenant.
    / We can create a minimal ClotureCaisse in a tenant schema.

    On utilise le tenant 'lespass' de la DB dev.
    / We use the 'lespass' tenant from the dev DB.
    """
    from Customers.models import Client
    tenant = Client.objects.exclude(schema_name="public").first()
    assert tenant is not None, "Aucun tenant non-public disponible pour le test"

    from django.utils import timezone
    from datetime import timedelta

    with tenant_context(tenant):
        from comptabilite.models import ClotureCaisse

        debut = timezone.now() - timedelta(days=1)
        fin = timezone.now()

        # Numero libre dynamique : evite la collision avec les clotures de
        # demo (fixture demo_data_v2 cree #1 et #2). On prend max+1.
        # / Pick max+1 to avoid collision with demo fixture closures.
        derniere = ClotureCaisse.objects.order_by("-numero_sequentiel").first()
        prochain_numero = (derniere.numero_sequentiel + 1) if derniere else 1

        cloture = ClotureCaisse.objects.create(
            niveau=ClotureCaisse.NIVEAU_JOURNALIER,
            numero_sequentiel=prochain_numero,
            datetime_debut=debut,
            datetime_fin=fin,
        )

        assert cloture.pk is not None
        assert cloture.numero_sequentiel == prochain_numero
        assert cloture.niveau == "J"
        assert cloture.total_general == 0
        assert cloture.rapport_json == {}

        # Nettoyage pour ne pas polluer la DB dev.
        # / Cleanup to avoid polluting the dev DB.
        cloture.delete()


def test_modele_cloturecaisse_unique_numero_sequentiel():
    """
    Le numero sequentiel est unique globalement par tenant.
    / Sequential number is globally unique per tenant.
    """
    from Customers.models import Client
    tenant = Client.objects.exclude(schema_name="public").first()
    assert tenant is not None, "Aucun tenant non-public disponible pour le test"

    from django.utils import timezone
    from datetime import timedelta
    from django.db import IntegrityError

    with tenant_context(tenant):
        from comptabilite.models import ClotureCaisse
        from django.db import transaction

        debut = timezone.now() - timedelta(days=2)
        fin1 = timezone.now() - timedelta(days=1)

        cloture1 = ClotureCaisse.objects.create(
            niveau="J", numero_sequentiel=9999,
            datetime_debut=debut, datetime_fin=fin1,
        )

        # La violation de contrainte casse la transaction courante.
        # On utilise un savepoint pour isoler l'echec et pouvoir continuer.
        # / The constraint violation breaks the current transaction.
        # Use a savepoint to isolate the failure and allow cleanup.
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                ClotureCaisse.objects.create(
                    niveau="H", numero_sequentiel=9999,  # meme numero / same number
                    datetime_debut=debut,
                    datetime_fin=timezone.now(),
                )

        # Nettoyage / Cleanup
        cloture1.delete()


# ============================================================================
# Tests admin — methodes du ClotureCaisseAdmin (sans pipeline Unfold).
# ============================================================================
#
# Pourquoi ne pas tester la page rendue via DjangoClient ?
# / Why not test the rendered page via DjangoClient?
#
# Le pipeline Unfold + DjangoClient + django-tenants a un bug global :
# un template d'Unfold (probablement dans app_list.html ou navigation_user.html)
# fait `{% if x.0 %}` sur une chaine vide quand l'auth passe par force_login
# au lieu du formulaire HTML. Toutes les URLs /admin/* plantent dans ce mode.
# Pas specifique a comptabilite : /admin/, /admin/BaseBillet/lignearticle/ aussi.
# En navigateur reel, ca passe. A investiguer plus tard (ticket "investiguer
# bug Unfold + DjangoClient + force_login").
#
# / The Unfold + DjangoClient + django-tenants pipeline has a global bug:
# / an Unfold template iterates `.0` on an empty string when auth goes through
# / force_login. All /admin/* URLs crash in this mode. Pre-existing bug, not
# / specific to comptabilite. Browser works fine. To investigate later.
#
# En attendant, on teste les *methodes* de l'admin directement avec
# RequestFactory. On couvre la logique (calcul du contexte, exports, URLs)
# sans le rendu complet de la sidebar Unfold.
# / Meanwhile we test the admin *methods* directly with RequestFactory.
# / Covers logic (context, exports, URLs) without full Unfold sidebar render.


@pytest.fixture
def admin_request_factory():
    """
    Fournit (request_factory, admin_instance, admin_user, tenant) pour les
    tests admin sans passer par DjangoClient.
    / Provides (factory, admin, user, tenant) for admin tests bypassing the client.
    """
    from django.test import RequestFactory
    from django.contrib.messages.storage.fallback import FallbackStorage
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.contrib.messages.middleware import MessageMiddleware
    from Customers.models import Client as TenantClient
    from AuthBillet.models import TibilletUser
    from comptabilite.admin import ClotureCaisseAdmin
    from comptabilite.models import ClotureCaisse
    from Administration.admin.site import staff_admin_site

    tenant = TenantClient.objects.filter(schema_name="lespass").first()
    if tenant is None:
        tenant = TenantClient.objects.exclude(schema_name="public").first()
    assert tenant is not None

    with tenant_context(tenant):
        admin_user, _ = TibilletUser.objects.get_or_create(
            email="admin@admin.com",
            defaults={
                "is_staff": True,
                "is_superuser": True,
                "is_active": True,
                "username": "admin",
            },
        )
        if not admin_user.is_staff:
            admin_user.is_staff = True
            admin_user.is_superuser = True
            admin_user.save()

    factory = RequestFactory()
    admin_instance = ClotureCaisseAdmin(ClotureCaisse, staff_admin_site)

    def _build_request(method="GET", path="/", data=None, query_string=""):
        url = path + ("?" + query_string if query_string else "")
        if method.upper() == "POST":
            request = factory.post(url, data=data or {})
        else:
            request = factory.get(url, data=data or {})
        request.user = admin_user
        # Session/messages middlewares attaches (pour les vues qui pourraient
        # poser des messages flash).
        # / Attach session & messages middlewares (for views that may add flash).
        SessionMiddleware(lambda r: None).process_request(request)
        request.session.save()
        request._messages = FallbackStorage(request)
        return request

    return _build_request, admin_instance, admin_user, tenant


# ============================================================================
# Permissions read-only
# ============================================================================

def test_admin_permissions_read_only():
    """
    Les 3 permissions destructives renvoient False (modele immuable).
    / The 3 destructive permissions return False (immutable model).
    """
    from comptabilite.admin import ClotureCaisseAdmin
    from comptabilite.models import ClotureCaisse
    from Administration.admin.site import staff_admin_site

    admin_instance = ClotureCaisseAdmin(ClotureCaisse, staff_admin_site)
    # has_add, has_change, has_delete : False quel que soit le request
    # / has_add, has_change, has_delete: always False
    assert admin_instance.has_add_permission(None) is False
    assert admin_instance.has_change_permission(None) is False
    assert admin_instance.has_delete_permission(None) is False


# ============================================================================
# URLs custom enregistrees (sidebar + exports)
# ============================================================================

def test_admin_urls_custom_enregistrees():
    """
    Verifie que get_urls() expose bien :
    - rapport-temps-reel/
    - <uuid>/exporter-csv/
    - <uuid>/exporter-excel/
    - <uuid>/exporter-pdf/
    - <uuid>/exporter-fec/
    - <uuid>/exporter-csv-comptable/
    / Verify get_urls() exposes all custom URLs.
    """
    from comptabilite.admin import ClotureCaisseAdmin
    from comptabilite.models import ClotureCaisse
    from Administration.admin.site import staff_admin_site

    admin_instance = ClotureCaisseAdmin(ClotureCaisse, staff_admin_site)
    noms_urls = {u.name for u in admin_instance.get_urls() if u.name}
    attendus = {
        "comptabilite_cloturecaisse_temps_reel",
        "comptabilite_cloturecaisse_csv",
        "comptabilite_cloturecaisse_excel",
        "comptabilite_cloturecaisse_pdf",
        "comptabilite_cloturecaisse_fec",
        "comptabilite_cloturecaisse_csv_comptable",
    }
    assert attendus.issubset(noms_urls), (
        f"URLs manquantes : {attendus - noms_urls}"
    )


# ============================================================================
# rapport_temps_reel : context + bornes (sans pipeline Unfold)
# ============================================================================

def _patch_render_to_capture_context():
    """
    Helper : remplace temporairement comptabilite.admin.render par un stub
    qui capture le 3e argument (context dict) sans rendre de template.
    Retourne (patched, captured) ou captured est un dict qu'on inspecte
    apres l'appel. Restaurer avec patched.stop().
    / Helper: patches comptabilite.admin.render to capture the context dict
    without rendering. Return (patcher, captured_dict).
    """
    from unittest.mock import patch
    from django.http import HttpResponse
    captured = {}

    def _fake_render(request, template_name, context=None, *args, **kwargs):
        captured["template"] = template_name
        captured["context"] = context or {}
        return HttpResponse("stub")

    # render() est importe en local dans la methode admin (django.shortcuts.render).
    # On patche directement la fonction source.
    # / render() is imported locally in the admin method (django.shortcuts.render).
    # / We patch the source function directly.
    patcher = patch("django.shortcuts.render", side_effect=_fake_render)
    patcher.start()
    return patcher, captured


def test_admin_rapport_temps_reel_context_bornes_par_defaut(admin_request_factory):
    """
    La vue rapport_temps_reel utilise les bornes par defaut
    [aujourd'hui 04:00 local, now()] quand aucun param n'est fourni.
    / The view uses default bounds when no params are given.
    """
    from datetime import timedelta
    from django.utils import timezone

    build_request, admin_instance, _, tenant = admin_request_factory
    request = build_request(path="/admin/comptabilite/cloturecaisse/rapport-temps-reel/")

    patcher, captured = _patch_render_to_capture_context()
    try:
        with tenant_context(tenant):
            admin_instance.rapport_temps_reel(request)
    finally:
        patcher.stop()

    assert captured["template"] == "comptabilite/views/rapport_temps_reel.html"
    ctx = captured["context"]
    assert "rapport" in ctx
    assert "datetime_debut" in ctx and "datetime_fin" in ctx
    assert "datetime_debut_input" in ctx and "datetime_fin_input" in ctx

    # debut par defaut : aujourd'hui 04:00 local (ou hier 04:00 si on est avant 4h)
    # / default start: today 04:00 local (or yesterday if before 4h)
    now_local = timezone.localtime()
    expected_debut = now_local.replace(hour=4, minute=0, second=0, microsecond=0)
    if expected_debut > now_local:
        expected_debut -= timedelta(days=1)
    assert ctx["datetime_debut"].hour == 4
    assert ctx["datetime_debut"].minute == 0
    # fin par defaut : now()
    assert (timezone.now() - ctx["datetime_fin"]).total_seconds() < 5


def test_admin_rapport_temps_reel_context_bornes_custom(admin_request_factory):
    """
    Les GET params datetime_debut / datetime_fin sont parses et reflechis
    dans le context (cles _input).
    / GET params are parsed and reflected in context (_input keys).
    """
    build_request, admin_instance, _, tenant = admin_request_factory
    request = build_request(
        path="/admin/comptabilite/cloturecaisse/rapport-temps-reel/",
        query_string="datetime_debut=2026-05-14T10:00&datetime_fin=2026-05-14T18:00",
    )

    patcher, captured = _patch_render_to_capture_context()
    try:
        with tenant_context(tenant):
            admin_instance.rapport_temps_reel(request)
    finally:
        patcher.stop()

    ctx = captured["context"]
    # Les inputs HTML5 utilisent le format YYYY-MM-DDTHH:MM
    # / HTML5 inputs use YYYY-MM-DDTHH:MM format
    assert ctx["datetime_debut_input"] == "2026-05-14T10:00"
    assert ctx["datetime_fin_input"] == "2026-05-14T18:00"


def test_admin_rapport_temps_reel_inverse_si_debut_apres_fin(admin_request_factory):
    """
    Garde-fou : si debut > fin (typo utilisateur), on les inverse.
    / Safety: if start > end (user typo), they get swapped.
    """
    build_request, admin_instance, _, tenant = admin_request_factory
    request = build_request(
        path="/admin/comptabilite/cloturecaisse/rapport-temps-reel/",
        # debut APRES fin / start AFTER end
        query_string="datetime_debut=2026-05-14T18:00&datetime_fin=2026-05-14T10:00",
    )

    patcher, captured = _patch_render_to_capture_context()
    try:
        with tenant_context(tenant):
            admin_instance.rapport_temps_reel(request)
    finally:
        patcher.stop()
    ctx = captured["context"]
    # Apres swap, debut == 10:00 et fin == 18:00
    # / After swap, start == 10:00 and end == 18:00
    assert ctx["datetime_debut_input"] == "2026-05-14T10:00"
    assert ctx["datetime_fin_input"] == "2026-05-14T18:00"


# ============================================================================
# changeform_view : context d'une cloture existante
# ============================================================================

def test_admin_changeform_injecte_cloture_et_rapport(admin_request_factory):
    """
    changeform_view sur une cloture existante injecte cloture + rapport
    pre-formate (euros) dans le context.
    / changeform_view injects cloture + pre-formatted rapport into context.
    """
    from datetime import timedelta
    from django.utils import timezone
    from comptabilite.models import ClotureCaisse
    from comptabilite.tasks import generer_cloture_pour_tenant

    build_request, admin_instance, _, tenant = admin_request_factory

    fin = timezone.now() - timedelta(days=200)
    debut = fin - timedelta(days=1)

    with tenant_context(tenant):
        # Cleanup ancien essai
        ClotureCaisse.objects.filter(
            datetime_debut=debut, datetime_fin=fin
        ).delete()

        cloture_uuid = generer_cloture_pour_tenant(
            schema_name=tenant.schema_name,
            niveau="J",
            datetime_debut_iso=debut.isoformat(),
            datetime_fin_iso=fin.isoformat(),
        )
        assert cloture_uuid is not None

    # On capture le context envoye a super().changeform_view via un stub
    # / Capture the context passed to super().changeform_view via a stub
    captured = {}

    class _StubAdmin:
        def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
            captured["extra_context"] = extra_context
            from django.http import HttpResponse
            return HttpResponse("stub")

    # On monkey-patche super() en remplacant la base class temporairement
    # / Monkey-patch the super() base class temporarily
    from django.contrib.admin.options import ModelAdmin as DjangoModelAdmin
    original = DjangoModelAdmin.changeform_view
    DjangoModelAdmin.changeform_view = _StubAdmin().changeform_view
    try:
        request = build_request(
            path=f"/admin/comptabilite/cloturecaisse/{cloture_uuid}/change/",
        )
        with tenant_context(tenant):
            admin_instance.changeform_view(request, object_id=str(cloture_uuid))
    finally:
        DjangoModelAdmin.changeform_view = original

    ctx = captured["extra_context"]
    assert "cloture" in ctx
    assert "rapport" in ctx
    assert "datetime_debut" in ctx
    assert "datetime_fin" in ctx
    # Cles pre-formatees en euros (templates Django ne savent pas diviser)
    # / Pre-formatted euros keys
    assert "cloture_total_general_euros" in ctx
    assert "cloture_total_ht_euros" in ctx
    assert "cloture_total_tva_euros" in ctx
    # Format "X.XX" (string)
    assert "." in ctx["cloture_total_general_euros"]

    # Cleanup
    with tenant_context(tenant):
        ClotureCaisse.objects.filter(uuid=cloture_uuid).delete()


# ============================================================================
# Templates : rendu standalone (sans pipeline Unfold)
# ============================================================================

def test_template_sections_rapport_rend_sans_erreur(admin_request_factory):
    """
    Le partial _sections_rapport.html se rend sans erreur avec un rapport
    pre-formate. Verifie que les 5 sections + leurs data-testid sont presents.
    / The _sections_rapport.html partial renders with a pre-formatted report.
    """
    from django.template.loader import render_to_string
    from comptabilite.services import enrichir_rapport_pour_affichage

    # Mini rapport realiste
    # / Realistic mini report
    rapport = {
        "totaux_par_moyen": {
            "SF": {"label": "Stripe", "total": 1500, "nb": 1},
            "total": 1500,
            "currency_code": "EUR",
        },
        "tva": {
            "20.00": {"taux": 20.0, "total_ttc": 1500, "total_ht": 1250, "total_tva": 250},
        },
        "detail_ventes": {},
        "remboursements": {
            "credit_notes": {"total": 0, "nb": 0},
            "refunded": {"total": 0, "nb": 0},
        },
        "infos_legales": {"organisation": "Test"},
    }
    rapport_enrichi = enrichir_rapport_pour_affichage(rapport)
    contenu = render_to_string(
        "comptabilite/admin/_sections_rapport.html",
        {"rapport": rapport_enrichi},
    )

    # Les 5 sections doivent etre presentes (par data-testid)
    # / All 5 sections must be present (via data-testid)
    for slug in [
        "totaux-par-moyen", "tva", "detail-ventes",
        "remboursements", "infos-legales",
    ]:
        assert f'data-testid="comptabilite-section-{slug}"' in contenu, (
            f"Section {slug} manquante dans le rendu"
        )
